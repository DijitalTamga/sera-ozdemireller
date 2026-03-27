import os
import asyncio
import logging
import io
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler, 
    CommandHandler, filters, ConversationHandler, CallbackQueryHandler
)
from dotenv import load_dotenv
from sera_core import (
    process_document, gemini_v45_expense_analyze, 
    masraf_kaydet_excel, is_duplicate_expense,
    get_current_balance, update_balance, SIRKET_ARSIV_YOLU,
    get_user_by_telegram_id
)

# --- DURUMLAR ---
WAIT_CONFIRM = 1

# --- YAPILANDIRMA ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTH_USER = os.getenv("AUTHORIZED_USER_ID") # Eğer tek kişiyse, yoksa DB kontrolü yapılır

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- YARDIMCI BUTONLAR ---
def main_menu_keyboard():
    keyboard = [
        ["💰 Masraf Girişi (Foto)", "📊 Bütçe Durumu"],
        ["🏦 Kasa Bakiyem", "❓ Yardım"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- KOMUTLAR VE MESAJLAR ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    
    # DB'den kullanıcıyı tanı
    user_data = get_user_by_telegram_id(uid)
    name = user_data[1] if user_data else user.first_name
    
    welcome_text = (
        f"🤖 **Hoş Geldin, {name}!**\n\n"
        f"Ben Sera-Bilgin'in Telegram asistanıyım. Harcamalarınızı yönetmem için bana bir fiş fotoğrafı gönderebilir "
        f"veya aşağıdaki butonları kullanabilirsiniz."
    )
    await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user_data = get_user_by_telegram_id(uid)
    
    if user_data:
        username = user_data[0]
        name = user_data[1]
        bakiye = get_current_balance(username)
        await update.message.reply_text(f"💰 **{name}**, güncel kasan: `{bakiye:,.2f} TL`", parse_mode="Markdown")
    else:
        # Genel bakiye (Admin?)
        bakiye = get_current_balance()
        await update.message.reply_text(f"🏦 **Toplam Kasa Bakiyesi:** `{bakiye:,.2f} TL`", parse_mode="Markdown")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # Fotoğrafı Al
    photo_file = await update.message.photo[-1].get_file()
    img_bytes = await photo_file.download_as_bytearray()
    
    msg = await update.message.reply_text("🧠 Börte fişi inceliyor, lütfen bekleyin...", reply_markup=ReplyKeyboardRemove())
    
    try:
        # 1. OCR ve AI Analiz
        img_io = io.BytesIO(img_bytes)
        ham_metin = "" # Opsiyonel: Tesseract metni bura gelebilir
        
        # 2. Expense Analizi (Multimodal Gemini)
        data = gemini_v45_expense_analyze(ham_metin, image_data=img_bytes)
        
        if "error" in data:
            await msg.delete()
            await update.message.reply_text(f"❌ Analiz Hatası: {data['error']}\nLütfen tekrar deneyin.", reply_markup=main_menu_keyboard())
            return ConversationHandler.END
            
        tarih = data.get("tarih", "Bilinmiyor")
        tutar = data.get("tutar", 0)
        isletme = data.get("isletme_adi", "Bilinmiyor")
        kategori = data.get("kategori", "Muhtelif")

        # Geçersiz tutar kontrolü (0 TL sorunu fix)
        if tutar is None or tutar == 0:
            await msg.delete()
            await update.message.reply_text(
                "⚠️ **Üzgünüm, tutarı okuyamadım.**\nLütfen fişin daha net bir fotoğrafını gönderin veya bilgileri kontrol edin.",
                reply_markup=main_menu_keyboard()
            )
            return ConversationHandler.END

        # Veriyi context'e sakla
        context.user_data['pending_expense'] = {
            "tarih": tarih,
            "tutar": tutar,
            "isletme_adi": isletme,
            "kategori": kategori,
            "img_bytes": img_bytes
        }

        # 3. Mükerrer Kontrolü
        warning = ""
        if is_duplicate_expense(tarih, tutar, isletme):
            warning = "⚠️ **DİKKAT:** Bu fiş sistemde zaten kayıtlı görünüyor!\n\n"

        # 4. Onay Butonları
        response = (
            f"{warning}"
            f"🔍 **BÖRTE ANALİZ SONUCU:**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🏢 **İşletme:** {isletme}\n"
            f"💰 **Tutar:** `{tutar} TL`\n"
            f"📅 **Tarih:** {tarih}\n"
            f"📂 **Kategori:** {kategori}\n\n"
            f"Bilgiler doğru mu? Kaydedilsin mi?"
        )
        
        reply_keyboard = [["✅ Onay", "❌ İptal"]]
        await msg.delete()
        await update.message.reply_text(
            response, 
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return WAIT_CONFIRM

    except Exception as e:
        logging.error(f"Telegram İşlem Hatası: {e}")
        await update.message.reply_text(f"❌ Beklenmedik bir hata oluştu: {str(e)}", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

async def confirm_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data.get('pending_expense')
    uid = str(update.effective_user.id)
    user_info = get_user_by_telegram_id(uid)
    username = user_info[0] if user_info else "Bilinmiyor"
    kasa_adi = f"Kasa {user_info[1]}" if user_info else "Bilinmiyor"

    if not user_data:
        await update.message.reply_text("⚠️ Zaman aşımı veya veri kaybı. Lütfen tekrar deneyin.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    try:
        # Kayıt İşlemi
        t_dir = os.path.join(SIRKET_ARSIV_YOLU, "MUHASEBE")
        if not os.path.exists(t_dir): os.makedirs(t_dir)
        
        file_name = f"TELE_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        file_path = os.path.join(t_dir, file_name)
        
        with open(file_path, "wb") as f:
            f.write(user_data['img_bytes'])
            
        user_data['dosya_yolu'] = file_path
        
        if masraf_kaydet_excel(user_data, kasa_adi=kasa_adi):
            # Bakiyeyi güncelle
            yeni_bakiye = update_balance(user_data['tutar'], username=username)
            
            await update.message.reply_text(
                f"✅ **Kayıt Tarihe Geçti!**\n💰 Kalan Bakiyen: `{yeni_bakiye:,.2f} TL`", 
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
        else:
            await update.message.reply_text("❌ Excel kaydı sırasında bir hata oluştu.", reply_markup=main_menu_keyboard())

    except Exception as e:
        await update.message.reply_text(f"❌ Kayıt Hatası: {str(e)}", reply_markup=main_menu_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ İşlem iptal edildi.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

if __name__ == '__main__':
    if not TOKEN:
        print("❌ HATA: TELEGRAM_BOT_TOKEN eksik! .env dosyasını kontrol edin.")
    else:
        # v83: drop_pending_updates=True ile eski mesajları temizleyerek başla
        app = ApplicationBuilder().token(TOKEN).build()
        
        conv_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.PHOTO, handle_photo),
                MessageHandler(filters.Regex("^💰 Masraf Girişi"), lambda u, c: u.message.reply_text("Lütfen bir fiş fotoğrafı gönderin.")),
                MessageHandler(filters.Regex("^📊 Bütçe Durumu|^🏦 Kasa Bakiyem"), show_balance),
            ],
            states={
                WAIT_CONFIRM: [
                    MessageHandler(filters.Regex("^✅ Onay$"), confirm_expense),
                    MessageHandler(filters.Regex("^❌ İptal$"), cancel_expense),
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel_expense)],
            allow_reentry=True
        )
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("menu", start)) # /menu alternatifi
        app.add_handler(MessageHandler(filters.Regex("📊 Bütçe Durumu|🏦 Kasa Bakiyem"), show_balance))
        app.add_handler(conv_handler)
        
        print("\n" + "="*40)
        print("🚀 SERA-BILGIN TELEGRAM BOT v83 CANLI!")
        print("Sistem: Butonlu Arayüz + Onay Mekanizması")
        print("Durum: Hazır ve Mesaj Bekliyor...")
        print("="*40 + "\n")
        
        app.run_polling(drop_pending_updates=True)
