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
        f"🤖 **Hoş Geldin, {name}! (v87)**\n\n"
        f"Ben Sera-Bilgin'in asistanıyım. Harcamalarını yönetmem için bana bir fiş fotoğrafı gönderebilir "
        f"veya aşağıdaki butonları kullanabilirsin."
    )
    print(f"DEBUG: Start komutu kullanıldı. Kullanıcı: {name} ({uid})")
    await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user_data = get_user_by_telegram_id(uid)
    
    print(f"DEBUG v88: Bakiye sorgusu. UID: {uid}")
    if user_data:
        username, name, role = user_data
        bakiye = get_current_balance(username)
        print(f"DEBUG v88: Kullanici:{username} Bakiye:{bakiye}")
        await update.message.reply_text(f"💰 **{name} (v88)**\nKullanıcı: `{username}`\nGüncel Kasan: `{bakiye:,.2f} TL`", parse_mode="Markdown")
    else:
        print(f"DEBUG v88: Kayitsiz Kullanici UID: {uid}")
        bakiye = get_current_balance()
        await update.message.reply_text(f"🏦 **Toplam Sistem Kasası (v88):** `{bakiye:,.2f} TL`", parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "❓ **Nasıl Kullanılır?**\n\n"
        "1. **Masraf Kaydı:** Bana doğrudan bir fiş fotoğrafı gönderin. Börte analiz eder ve sizden onay ister.\n"
        "2. **Bakiye Sorgusu:** 'Bakiye' butonuna basın veya /bakiye yazın.\n"
        "3. **Yardım:** Bu mesajı görmek için /yardım yazın."
    )
    await update.message.reply_text(help_text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Fotoğrafı Al
    photo_file = await update.message.photo[-1].get_file()
    img_bytes = await photo_file.download_as_bytearray()
    
    msg = await update.message.reply_text("🧠 Börte fişi inceliyor, lütfen bekleyin...", reply_markup=ReplyKeyboardRemove())
    
    try:
        data = gemini_v45_expense_analyze("", image_data=img_bytes)
        
        if "error" in data:
            await msg.delete()
            await update.message.reply_text(f"❌ Analiz Hatası: {data['error']}", reply_markup=main_menu_keyboard())
            return ConversationHandler.END
            
        tarih = data.get("tarih", "Bilinmiyor")
        tutar = data.get("tutar", 0)
        isletme = data.get("isletme_adi", "Bilinmiyor")
        kategori = data.get("kategori", "Muhtelif")

        if tutar is None or tutar == 0:
            await msg.delete()
            await update.message.reply_text("⚠️ **Tutar okunamadı.** Lütfen daha net bir fotoğraf gönderin.", reply_markup=main_menu_keyboard())
            return ConversationHandler.END

        context.user_data['pending_expense'] = {
            "tarih": tarih, "tutar": tutar, "isletme_adi": isletme, 
            "kategori": kategori, "img_bytes": img_bytes
        }

        warning = "⚠️ **Mükerrer Kayıt Riski!**\n" if is_duplicate_expense(tarih, tutar, isletme) else ""
        
        response = (
            f"{warning}"
            f"🔍 **BÖRTE ANALİZ SONUCU:**\n"
            f"🏢 **İşletme:** {isletme}\n"
            f"💰 **Tutar:** `{tutar} TL`\n"
            f"📅 **Tarih:** {tarih}\n\n"
            f"Onaylıyor musunuz?"
        )
        
        reply_keyboard = [["✅ Onay", "❌ İptal"]]
        await msg.delete()
        await update.message.reply_text(response, parse_mode="Markdown", 
                                       reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
        return WAIT_CONFIRM

    except Exception as e:
        logging.error(f"Hata: {e}")
        await update.message.reply_text("❌ İşlem sırasında bir hata oluştu.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

async def confirm_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('pending_expense')
    uid = str(update.effective_user.id)
    user_info = get_user_by_telegram_id(uid)
    
    if not data:
        await update.message.reply_text("⚠️ Veri kaybı. Lütfen tekrar foto gönderin.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    try:
        t_dir = os.path.join(SIRKET_ARSIV_YOLU, "MUHASEBE")
        if not os.path.exists(t_dir): os.makedirs(t_dir)
        f_path = os.path.join(t_dir, f"TELE_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
        
        with open(f_path, "wb") as f: f.write(data['img_bytes'])
        data['dosya_yolu'] = f_path
        
        username = user_info[0] if user_info else "Bilinmiyor"
        kasa_adi = f"Kasa {user_info[1]}" if user_info else "Genel Kasa"

        if masraf_kaydet_excel(data, kasa_adi=kasa_adi):
            yeni_bakiye = update_balance(data['tutar'], username=username)
            await update.message.reply_text(f"✅ **Kaydedildi!**\n💰 Kalan: `{yeni_bakiye:,.2f} TL`", 
                                           parse_mode="Markdown", reply_markup=main_menu_keyboard())
        else:
            await update.message.reply_text("❌ Kayıt yapılamadı.", reply_markup=main_menu_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Hata: {e}", reply_markup=main_menu_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ İptal edildi.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    print(f"DEBUG: Bilinmeyen mesaj: {text}")
    
    if any(x in text for x in ["masraf", "fiş", "fiş", "fatura"]):
        await update.message.reply_text("💰 **Masraf kaydı için lütfen fişin fotoğrafını gönderin.**", parse_mode="Markdown", reply_markup=main_menu_keyboard())
    elif any(x in text for x in ["kasa", "bakiye", "para", "durum"]):
        await show_balance(update, context)
    else:
        await update.message.reply_text("🤖 Beni mi çağırdınız? İşlem yapmak için aşağıdaki menüyü kullanabilirsiniz.", reply_markup=main_menu_keyboard())

if __name__ == '__main__':
    if not TOKEN:
        print("HATA: TOKEN EXCEL")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        
        # v87: Konuşma Yöneticisi (Fotoğraf -> Onay)
        conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.PHOTO, handle_photo)],
            states={
                WAIT_CONFIRM: [
                    MessageHandler(filters.Regex("^(✅ Onay|Onay|onay)$"), confirm_expense),
                    MessageHandler(filters.Regex("^(❌ İptal|İptal|iptal)$"), cancel_expense),
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel_expense), MessageHandler(filters.TEXT, cancel_expense)],
            allow_reentry=True
        )
        
        # Temel Komutlar
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("menu", start))
        app.add_handler(CommandHandler(["bakiye", "kasa"], show_balance))
        app.add_handler(CommandHandler(["yardim", "help", "yardım"], help_command))
        
        # Metin tabanlı yakalayıcılar (v87 Esneklik)
        app.add_handler(MessageHandler(filters.Regex(r"(?i)masraf|fiş|fiş|fatura"), 
                        lambda u, c: u.message.reply_text("📷 Lütfen masraf fişinin fotoğrafını buraya gönderin.")))
        app.add_handler(MessageHandler(filters.Regex(r"(?i)bakiye|kasa|durum"), show_balance))
        
        app.add_handler(conv_handler)
        
        # Diğer Her Şey (Catch-all)
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_unknown))
        
        print("\n" + "="*40)
        print("🚀 SERA-BILGIN TELEGRAM BOT v87.0 CANLI!")
        print("Mod: Süper Kararlılık (Esnek Komutlar)")
        print("="*40 + "\n")
        
        app.run_polling(drop_pending_updates=True)
