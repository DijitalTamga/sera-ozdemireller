import os
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv
from sera_core import (
    process_document, gemini_v45_expense_analyze, 
    masraf_kaydet_excel, is_duplicate_expense,
    get_current_balance, update_balance, SIRKET_ARSIV_YOLU
)

# --- YAPILANDIRMA ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTH_USER = os.getenv("AUTHORIZED_USER_ID")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # Yetki Kontrolü
    if AUTH_USER and user_id != AUTH_USER:
        await update.message.reply_text("⛔ Üzgünüm, bu botu kullanma yetkiniz yok.")
        return

    # Fotoğrafı Al
    photo_file = await update.message.photo[-1].get_file()
    img_bytes = await photo_file.download_as_bytearray()
    
    msg = await update.message.reply_text("🧠 Börte fişi inceliyor, lütfen bekleyin...")
    
    try:
        # 1. OCR ve AI Analiz
        # process_document beklediği format için io.BytesIO kullanalım
        import io
        img_io = io.BytesIO(img_bytes)
        ham_metin = process_document(img_io, is_path=False, use_enhancement=True)
        
        # 2. Expense Analizi
        data = gemini_v45_expense_analyze(ham_metin, image_data=img_bytes)
        
        if "error" in data:
            await msg.edit_text(f"❌ Analiz Hatası: {data['error']}")
            return
            
        tarih = data.get("tarih", "Bilinmiyor")
        tutar = data.get("tutar", 0)
        isletme = data.get("isletme_adi", "Bilinmiyor")
        kategori = data.get("kategori", "Muhtelif")

        # 3. Mükerrer Kontrolü
        if is_duplicate_expense(tarih, tutar, isletme):
            await msg.edit_text(f"⚠️ Bu fiş zaten kayıtlı! ({isletme} - {tutar} TL)")
            return

        # 4. Kayıt İşlemi
        # Klasör hazırla
        t_dir = os.path.join(SIRKET_ARSIV_YOLU, "MUHASEBE")
        if not os.path.exists(t_dir): os.makedirs(t_dir)
        
        from datetime import datetime
        file_name = f"TELE_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        file_path = os.path.join(t_dir, file_name)
        
        with open(file_path, "wb") as f:
            f.write(img_bytes)
            
        veri = {
            "tarih": tarih,
            "tutar": tutar,
            "isletme_adi": isletme,
            "kategori": kategori,
            "dosya_yolu": file_path
        }
        
        if masraf_kaydet_excel(veri):
            # Bakiyeyi güncelle
            yeni_bakiye = update_balance(tutar)
            
            response = (
                f"✅ **Masraf Başarıyla Kaydedildi!**\n\n"
                f"🏢 **İşletme:** {isletme}\n"
                f"📅 **Tarih:** {tarih}\n"
                f"💰 **Tutar:** {tutar} TL\n"
                f"📂 **Kategori:** {kategori}\n\n"
                f"🏦 **Güncel Bakiye:** {yeni_bakiye:,.2f} TL"
            )
            await msg.edit_text(response, parse_mode="Markdown")
        else:
            await msg.edit_text("❌ Kayıt sırasında bir hata oluştu.")

    except Exception as e:
        logging.error(f"Telegram İşlem Hatası: {e}")
        await msg.edit_text(f"❌ Beklenmedik bir hata oluştu: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_info = f"Merhaba! Ben Börte. 🤖\nLütfen bir fiş fotoğrafı gönderin. User ID: {update.effective_user.id}"
    await update.message.reply_text(user_info)

if __name__ == '__main__':
    if not TOKEN or TOKEN == "TOKEN_BURAYA_GELECEK":
        print("HATA: Lütfen .env dosyasındaki TELEGRAM_BOT_TOKEN alanını doldurun!")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(MessageHandler(filters.COMMAND & filters.Regex("/start"), start))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        print("🤖 Börte Telegram Botu Başlatıldı...")
        app.run_polling()
