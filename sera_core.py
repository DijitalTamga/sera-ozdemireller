import os
import sqlite3
import hashlib
import re
import io
import json
import pandas as pd
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
from dotenv import load_dotenv
from google import genai
from google.genai import types
import requests
import streamlit as st
import logging
import base64
import traceback

def base64_encode_file(file_path):
    """Dosyayı base64 formatına çevirir (Önizleme için)"""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# --- YAPILANDIRMA YÜKLE ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=ENV_PATH, override=True)

# --- AYARLAR (v81: Cloud + Lokal Uyumlu) ---
# st.secrets (Streamlit Cloud) → os.getenv (.env) → fallback
def _get_secret(key, fallback=""):
    """st.secrets (cloud) veya os.getenv (local) üzerinden değer okur"""
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return val
    except Exception:
        pass
    return os.getenv(key, fallback)

# Tesseract Yolu: Linux/Cloud'da 'tesseract', Windows'ta tam yol
TESSERACT_PATH = _get_secret('TESSERACT_PATH') or os.getenv('TESSERACT_PATH')
if not TESSERACT_PATH:
    if os.name == 'nt': # Windows
        TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    else: # Linux / Cloud
        TESSERACT_PATH = 'tesseract'

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# Veritabanı ve Arşiv Yolları
DB_NAME = os.path.join(BASE_DIR, _get_secret('DB_NAME') or os.getenv('DB_NAME', "arsiv_hafizasi.db"))
SIRKET_ARSIV_YOLU = _get_secret('ARSIV_YOLU') or os.getenv('ARSIV_YOLU', os.path.join(BASE_DIR, "arsiv"))

# v81: Gemini API Key - Streamlit Secrets → .env → hardcode
GEMINI_API_KEY = _get_secret('GEMINI_API_KEY') or os.getenv('GEMINI_API_KEY', "")

# --- v56: YENİ SDK YAPILANDIRMASI ---
if not GEMINI_API_KEY:
    GEMINI_API_KEY = "AIzaSyBWv98AMAeRbc3CJMpHFPpcu8fdlXMkc0Q"

# --- v58: MODEL KEŞİF (API DISCOVERY) ---
def list_available_models(api_key):
    """API anahtarı ile erişilebilen tüm modelleri listeler"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        res = requests.get(url, timeout=10)
        return res.json()
    except Exception as e:
        return {"error": str(e)}

def clean_json_string(text):
    """v50: Regex ile sadece { } arasını çekip temizleyen kusursuz filtre"""
    try:
        # Regex ile sadece ilk { ve son } arasını al
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json_str
        return text.strip()
    except:
        return text.strip()

# --- LOGLAMA SİSTEMİ ---
def setup_logging():
    logging.basicConfig(
        filename='sera_sistem.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        encoding='utf-8'
    )

def log_activity(mesaj, seviye="INFO"):
    setup_logging()
    if seviye == "INFO":
        logging.info(mesaj)
    elif seviye == "WARNING":
        logging.warning(mesaj)
    elif seviye == "ERROR":
        logging.error(mesaj)

# --- TÜRKÇE KARAKTER NORMALİZASYONU ---
def tr_lower(metin):
    if not metin: return ""
    duzeltmeler = {'İ': 'i', 'I': 'ı', 'Ş': 'ş', 'Ğ': 'ğ', 'Ü': 'ü', 'Ö': 'ö', 'Ç': 'ç'}
    for buyuk, kucuk in duzeltmeler.items():
        metin = metin.replace(buyuk, kucuk)
    return metin.lower().strip()

def tr_normalize(metin):
    """Arama için metni tamamen standartlaştırır"""
    if not metin: return ""
    metin = tr_lower(metin)
    # Gereksiz boşlukları ve karakterleri temizle
    metin = re.sub(r'\s+', ' ', metin)
    return metin.strip()

# --- VERİTABANI İŞLEMLERİ ---
def get_db_connection():
    return sqlite3.connect(DB_NAME)

def db_init():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Kullanıcılar Tablosu (v68: role ve telegram_id eklendi)
    c.execute('''CREATE TABLE IF NOT EXISTS kullanicilar 
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT, ad_soyad TEXT, birim TEXT, telegram_id TEXT)''')
    
    # Sütun kontrolü ve eksik sütun ekleme (Bakım Modu - v68.10)
    c.execute("PRAGMA table_info(kullanicilar)")
    cols_users = [col[1] for col in c.fetchall()]
    if 'telegram_id' not in cols_users:
        c.execute("ALTER TABLE kullanicilar ADD COLUMN telegram_id TEXT")
    if 'role' not in cols_users:
        c.execute("ALTER TABLE kullanicilar ADD COLUMN role TEXT")
    if 'ad_soyad' not in cols_users:
        c.execute("ALTER TABLE kullanicilar ADD COLUMN ad_soyad TEXT")
    
    # Kategoriler tablosu
    c.execute('CREATE TABLE IF NOT EXISTS kategoriler (kat_ad TEXT PRIMARY KEY)')
    
    # Belgeler tablosu (Gelişmiş)
    c.execute('''CREATE TABLE IF NOT EXISTS belgeler 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  dosya_adi TEXT, 
                  kategori TEXT, 
                  yukleyen TEXT, 
                  tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                  tc_no TEXT, 
                  ham_metin TEXT, 
                  isim_eslesme TEXT, 
                  dosya_yolu TEXT)''')
    
    # Log Tablosu (Dashboard için)
    c.execute('''CREATE TABLE IF NOT EXISTS sistem_loglari 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                  islem TEXT, 
                  kullanici TEXT, 
                  detay TEXT)''')
    
    # Masraflar Tablosu (Feature 4: SQLite Migration)
    c.execute('''CREATE TABLE IF NOT EXISTS masraflar 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  harcama_tarihi TEXT, 
                  tutar REAL, 
                  isletme_adi TEXT, 
                  kategori TEXT, 
                  dosya_yolu TEXT, 
                  kayit_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  is_verified INTEGER DEFAULT 0)''')

    # Sütun kontrolü ve eksik sütun ekleme (v68.14: masraflar -> kasa_adi)
    c.execute("PRAGMA table_info(masraflar)")
    cols_masraflar = [col[1] for col in c.fetchall()]
    if 'kasa_adi' not in cols_masraflar:
        c.execute("ALTER TABLE masraflar ADD COLUMN kasa_adi TEXT")
    
    # Öğrenme Hafızası (Feature 5: Human-in-the-Loop)
    c.execute('''CREATE TABLE IF NOT EXISTS ogrenme_hafizasi 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  ham_metin TEXT, 
                  isletme_adi_dogru TEXT, 
                  tutar_dogru REAL, 
                  tarih_dogru TEXT,
                  kategori_dogru TEXT)''')
    
    # Kasalar Tablosu (v68: owner_username eklendi)
    c.execute('''CREATE TABLE IF NOT EXISTS kasalar 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  kasa_adi TEXT, 
                  owner_username TEXT,
                  bakiye REAL DEFAULT 0)''')
    
    # Sütun kontrolü ve eksik sütun ekleme (Bakım Modu - v68.2)
    c.execute("PRAGMA table_info(kasalar)")
    cols_kasalar = [col[1] for col in c.fetchall()]
    if 'owner_username' not in cols_kasalar:
        c.execute("ALTER TABLE kasalar ADD COLUMN owner_username TEXT")
    
    # v68.12: Daha güvenli bir güncelleme stratejisi (Persistence Fix)
    cords = [
        ("engin.demirel", "Engin Demirel"),
        ("abidin.ozcan", "Abidin Özcan"),
        ("yusuf.demir", "Yusuf Ziya Demir"),
        ("nurettin.ozcan", "Nurettin Özcan")
    ]
    for usr, name in cords:
        # Sadece yoksa ekle (INSERT OR IGNORE)
        c.execute("INSERT OR IGNORE INTO kullanicilar (username, ad_soyad, role, birim) VALUES (?,?,?,?)", 
                  (usr, name, "Koordinatör" if usr != "nurettin.ozcan" else "Admin", "Saha" if usr != "nurettin.ozcan" else "Merkez"))
        # Rol ve isim gibi "sistem verilerini" GÜNCELLE ama telegram_id/password dokunma
        c.execute("UPDATE kullanicilar SET ad_soyad=?, role=?, birim=? WHERE username=?",
                  (name, "Koordinatör" if usr != "nurettin.ozcan" else "Admin", "Saha" if usr != "nurettin.ozcan" else "Merkez", usr))
        
        c.execute("INSERT OR IGNORE INTO kasalar (kasa_adi, owner_username) SELECT ?, ? WHERE NOT EXISTS (SELECT 1 FROM kasalar WHERE owner_username=?)",
                  (f"Kasa {name}", usr, usr))

    # Tüm kullanıcılara varsayılan şifre tanımla (12313) - v68.1
    default_hash = hashlib.sha256("12313".encode()).hexdigest()
    c.execute("UPDATE kullanicilar SET password = ? WHERE password IS NULL OR password = ''", (default_hash,))
    
    conn.commit()
    conn.close()

def notify_user_telegram(username, amount, desc="Kasa Girişi"):
    """Kullanıcıya para girişi yapıldığında bildirim gönderir (v68.12)"""
    try:
        conn = get_db_connection()
        user_res = conn.execute("SELECT telegram_id, ad_soyad FROM kullanicilar WHERE username=?", (username,)).fetchone()
        conn.close()
        
        if user_res and user_res[0]:
            tid = user_res[0]
            name = user_res[1]
            # v88:_get_secret ile her ortamda (Local/Cloud) tokeni bul
            token = _get_secret("TELEGRAM_BOT_TOKEN")
            if not token: 
                log_activity(f"Bildirim Hatasi: BOT_TOKEN eksik", "ERROR")
                return False
            
            message = (
                f"💰 **Bakiye Girişi Algılandı!**\n\n"
                f"👤 **Alıcı:** {name}\n"
                f"💵 **Tutar:** {amount:,.2f} TL\n"
                f"📝 **Açıklama:** {desc}\n\n"
                f"Hayırlı bereketler dileriz! ✨"
            )
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            resp = requests.post(url, json={"chat_id": tid, "text": message, "parse_mode": "Markdown"}, timeout=10)
            if resp.status_code == 200:
                log_activity(f"Telegram Bildirimi Gonderildi: {username}")
                return True
            else:
                log_activity(f"Telegram API Hatasi: {resp.text}", "ERROR")
                return False
        else:
            log_activity(f"Bildirim Hatasi: Kullanici ({username}) Telegram ID bulunamadi", "WARNING")
    except Exception as e:
        log_activity(f"Bildirim Hatası: {e}", "ERROR")
    return False

def gelir_kaydet_excel(username, amount, desc="Kasa Girişi", kasa_adi="Bilinmiyor"):
    """Para girişlerini (Gelir) Excel dosyasına ekler (v68.13)"""
    from datetime import datetime
    excel_path = os.path.join(BASE_DIR, "masraf_arsivi.xlsx")
    cols = ["Harcama Tarihi", "Harcama Tutarı", "Harcama Açıklaması", "Kategori", "Belge_Yolu", "Kayıt_Tarihi", "İşlem Yapılan Kasa"]
    try:
        if not os.path.exists(excel_path):
            df = pd.DataFrame(columns=cols)
        else:
            df = pd.read_excel(excel_path)
            
        yeni_satir = {
            "Harcama Tarihi": datetime.now().strftime("%Y-%m-%d"),
            "Harcama Tutarı": amount,
            "Harcama Açıklaması": f"KASA GİRDİSİ: {desc} (Alıcı: {username})",
            "Kategori": "GELİR / KASA GİRİŞİ",
            "Belge_Yolu": "BANKA/NAKİT",
            "Kayıt_Tarihi": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "İşlem Yapılan Kasa": kasa_adi
        }
        df = pd.concat([df, pd.DataFrame([yeni_satir])], ignore_index=True)
        df.to_excel(excel_path, index=False)
        return True
    except Exception as e:
        log_activity(f"Excel Gelir Kayıt Hatası: {e}", "ERROR")
        return False

def db_log(islem, kullanici, detay=""):
    try:
        conn = get_db_connection()
        conn.execute("INSERT INTO sistem_loglari (islem, kullanici, detay) VALUES (?,?,?)", (islem, kullanici, detay))
        conn.commit()
        conn.close()
    except: pass
    log_activity(f"[{kullanici}] {islem}: {detay}")

# --- AI ANALİZ (GEMINI) ---
def analyze_with_gemini(text, prompt="Bu belge nedir? Özetle."):
    """v60: Future Ready (gemini-2.0-flash)"""
    if not GEMINI_API_KEY: return "API Key Eksik"
    
    # Metod 1: SDK (Keşifteki modele göre)
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=f"{prompt}\n\nMetin:\n{text}"
        )
        return response.text
    except Exception as e:
        print(f"v60 SDK Hatası: {e}")
        # Metod 2: Direct REST (v1beta + gemini-flash-latest)
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
            headers = {'Content-Type': 'application/json'}
            payload = {"contents": [{"parts": [{"text": f"{prompt}\n\nMetin:\n{text}"}]}]}
            res = requests.post(url, headers=headers, json=payload, timeout=30)
            return res.json()['candidates'][0]['content']['parts'][0]['text']
        except Exception as e2:
            return f"v60 Kritik Hata: {e2}"

# --- V43: GELİŞMİŞ VERİ TEMİZLEME (SCRUBBING) ---
def scrub_ocr_text(text):
    """OCR metni içindeki gürültüleri temizler ve standardize eder"""
    if not text: return ""
    
    # 1. Gelişmiş Filtre: Sadece Harf, Rakam, Boşluk ve bazı noktalama işaretlerini koru
    # Diğer her şeyi boşlukla değiştirerek kelime birleşmesini önle
    text = re.sub(r'[^a-zA-Z0-9çğıöşüÇĞİÖŞÜ\.\,\-\s\(\)\/]', ' ', text)
    
    # 2. Hatalı okunan karakterleri düzelt (Sık karşılaşılan OCR hataları)
    replacements = {
        r'\biKamet\b': 'İkamet',
        r'\bT\.C\.\b': 'TC',
        r'\bS\.N\b': 'SN',
        r'\blari\b': 'ları'
    }
    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        
    # 3. Fazla boşlukları temizle
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    
    return text.strip()

# --- V43: AKILLI ÖN-ANALİZÖR (JSON ANALİZYÖR) ---
def gemini_v43_analyze(text):
    """Gemini 1.5 Flash kullanarak metinden yapılandırılmış JSON çıkarır"""
    if not GEMINI_API_KEY:
        return {"error": "API Key Missing"}
        
    prompt = """
    Aşağıdaki OCR metnini analiz et ve sonucu SADECE geçerli bir JSON formatında döndür. 
    Lütfen başka açıklama ekleme. JSON yapısı şu şekilde olmalı:
    {
      "belge_tipi": "Belge türü (Fatura, Ruhsat, Karar, Kasko, Kimlik vb.)",
      "kurum": "Belgeyi düzenleyen kurum veya ilgili şirket adı",
      "kritik_tarih": "Belge içindeki en önemli tarih (vade, bitiş, düzenleme - YYYY-MM-DD)",
      "ozet": "Belgenin 1 cümlelik özeti",
      "kategori_tahmini": "MUHASEBE, SÖZLEŞME / HUKUK, PERSONEL / İK, TEKNİK / PROJE, RESMİ YAZI kategorilerinden biri"
    }
    """
    
    # Metod 1: SDK
    raw_ans = ""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        cleaned_text = scrub_ocr_text(text)
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=f"{prompt}\n\nMetin:\n{cleaned_text}"
        )
        raw_ans = response.text
    except Exception as e:
        print(f"v60 SDK v43 Hatası: {e}")
        # Metod 2: Direct REST (gemini-flash-latest)
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
            headers = {'Content-Type': 'application/json'}
            payload = {"contents": [{"parts": [{"text": f"{prompt}\n\nMetin:\n{cleaned_text}"}]}]}
            res = requests.post(url, headers=headers, json=payload, timeout=30)
            raw_data = res.json()
            if 'candidates' in raw_data:
                raw_ans = raw_data['candidates'][0]['content']['parts'][0]['text']
        except Exception as e2:
            print(f"v60 Kritik v43 Hatası: {e2}")

    if not raw_ans:
        return {"belge_tipi": "Hata", "ozet": "Analiz Yapılamadı", "raw_response": "AI boş yanıt döndürdü."}

    try:
        raw_json = clean_json_string(raw_ans)
        data = json.loads(raw_json)
        data["raw_response"] = raw_ans # Debug için ekle
        return data
    except Exception as e3:
        return {"belge_tipi": "Bilinmiyor", "ozet": "JSON Hatası", "raw_response": raw_ans}

# --- GÖRÜNTÜ İYLEŞTİRME VE OCR ---
def enhance_image(img):
    """OpenCV ile görüntüyü OCR için netleştirir"""
    if not HAS_CV2: return img
    
    # PIL'den OpenCV formatına çevir
    open_cv_image = np.array(img)
    if len(open_cv_image.shape) == 3:
        open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2GRAY)
    
    # Adaptive Thresholding ile metni belirginleştir
    enhanced = cv2.adaptiveThreshold(
        open_cv_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    return Image.fromarray(enhanced)

def process_document(file_source, is_path=True, use_enhancement=False):
    """Belgeyi okur ve metni çıkarır (V40 OCR Mantığı)"""
    tam_metin = ""
    
    try:
        if is_path:
            if file_source.lower().endswith(".pdf"):
                doc = fitz.open(file_source)
                for page in doc:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_data = pix.tobytes("png")
                    img = Image.open(io.BytesIO(img_data))
                    if use_enhancement: img = enhance_image(img)
                    tam_metin += pytesseract.image_to_string(img, lang='tur', config='--psm 6') + "\n"
                doc.close()
            else:
                img = Image.open(file_source)
                if use_enhancement: img = enhance_image(img)
                tam_metin = pytesseract.image_to_string(img, lang='tur')
        else:
            # Streamlit UploadedFile (bytes) durumu
            file_bytes = file_source.read()
            # PDF kontrolü (İmza bazlı)
            if file_bytes.startswith(b"%PDF"):
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                for page in doc:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_data = pix.tobytes("png")
                    img = Image.open(io.BytesIO(img_data))
                    if use_enhancement: img = enhance_image(img)
                    tam_metin += pytesseract.image_to_string(img, lang='tur', config='--psm 6') + "\n"
                doc.close()
            else:
                img = Image.open(io.BytesIO(file_bytes))
                if use_enhancement: img = enhance_image(img)
                tam_metin = pytesseract.image_to_string(img, lang='tur')
                
    except Exception as e:
        log_activity(f"OCR Hatası: {e}", "ERROR")
        return ""
        
    return tam_metin

# --- BİLGİ ÇIKARMA (RegEx - V40 & V41) ---
def extract_dates(text):
    """Metin içindeki tarihleri bulur (V41)"""
    # DD.MM.YYYY veya DD/MM/YYYY formatları
    date_patterns = [
        r'\b\d{1,2}[\.\/]\d{1,2}[\.\/]\d{4}\b',
        r'\b\d{4}[\-\/]\d{1,2}[\-\/]\d{1,2}\b'
    ]
    dates = []
    for pattern in date_patterns:
        found = re.findall(pattern, text)
        dates.extend(found)
    return dates

def predict_category(text):
    """Metin içeriğine göre kategori tahmini yapar (V41)"""
    text_norm = tr_normalize(text)
    
    # Kategori bazlı anahtar kelimeler
    keywords = {
        "MUHASEBE": ["fatura", "fatura no", "ıban", "tutar", "kdv", "ödeme", "makbuz", "gelir", "gider"],
        "SÖZLEŞME / HUKUK": ["sözleşme", "taraflar", "madde", "hüküm", "tebliğ", "ihtar", "vekalet", "dava"],
        "PERSONEL / İK": ["özlük", "bordro", "izin", "sicil", "kimlik", "nüfus", "pasaport", "personel"],
        "TEKNİK / PROJE": ["proje", "şartname", "analiz", "teknik", "çizim", "plan", "keşif"],
        "RESMİ YAZI": ["sayı:", "konu:", "ilgi:", "arz ederim", "rica ederim", "valilik", "belediye"]
    }
    
    for kat, keys in keywords.items():
        if any(key in text_norm for key in keys):
            return kat
            
    return "Genel Arşiv"

def extract_v40_info(text):
    """Metin içinden TC ve İsim tahmin eder"""
    info = {"tc": "", "isim": "", "kategori": predict_category(text), "tarihler": extract_dates(text)}
    
    # 1. TC Kimlik No Bulma (11 Haneli sayı, 0 ile başlamaz, algoritma kontrolü basitleştirilmiş)
    tc_match = re.search(r'\b[1-9][0-9]{10}\b', text)
    if tc_match:
        info["tc"] = tc_match.group(0)
    
    # 2. İsim Bulma (Geliştirilmiş)
    name_patterns = [
        r"(?:AD[I]?\s*SOYAD[I]?|İSİM|MÜŞTERİ|AD SOYAD)\s*[:\-]?\s*([A-ZÇĞİÖŞÜ ]{3,35})",
        r"([A-ZÇĞİÖŞÜ]{2,25}\s[A-ZÇĞİÖŞÜ]{2,25}(?:\s[A-ZÇĞİÖŞÜ]{2,25})?)", # 2 veya 3 kelimeli büyük harf isimler
        r"Sayın\s*([A-ZÇĞİÖŞÜ ]{3,35})"
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            cand = match.group(1).strip() if len(match.groups()) > 0 else match.group(0).strip()
            if all(c.isalpha() or c.isspace() for c in cand):
                info["isim"] = cand
                break
                
    return info

# --- V45: MASRAF KAYIT VE EXCEL ENTEGRASYONU ---
# --- V67: GENİŞLETİLMİŞ MASRAF İŞLEMLERİ (Feature 2 & 4) ---
def is_duplicate_expense(tarih, tutar, isletme_adi):
    """Mükerrer kayıt kontrolü (Feature 2)"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        # Aynı işletme, aynı tarih ve aynı tutar varsa mükerrer kabul et
        c.execute("SELECT id FROM masraflar WHERE harcama_tarihi = ? AND tutar = ? AND isletme_adi = ?", 
                  (tarih, float(tutar) if tutar else 0, isletme_adi))
        res = c.fetchone()
        conn.close()
        return res is not None
    except Exception as e:
        log_activity(f"Mükerrer Kontrol Hatası: {e}", "ERROR")
        return False

def save_expense_to_sql(veri_dict, kasa_adi="Bilinmiyor"):
    """Masrafı SQLite veritabanına kaydeder (v68.14: kasa_adi eklendi)"""
    try:
        conn = get_db_connection()
        conn.execute("""INSERT INTO masraflar (harcama_tarihi, tutar, isletme_adi, kategori, dosya_yolu, kasa_adi) 
                     VALUES (?,?,?,?,?,?)""", 
                     (veri_dict.get("tarih", ""), 
                      float(veri_dict.get("tutar", 0)) if veri_dict.get("tutar") else 0, 
                      veri_dict.get("isletme_adi", ""), 
                      veri_dict.get("kategori", "Muhtelif"), 
                      veri_dict.get("dosya_yolu", ""),
                      kasa_adi))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log_activity(f"SQL Masraf Kayıt Hatası: {e}", "ERROR")
        return False

def get_current_balance(username=None):
    """v68: Belirli bir kullanıcının veya toplam kasaların bakiyesini getirir"""
    try:
        conn = get_db_connection()
        if username:
            res = conn.execute("SELECT bakiye FROM kasalar WHERE owner_username=?", (username,)).fetchone()
        else:
            res = conn.execute("SELECT SUM(bakiye) FROM kasalar").fetchone()
        conn.close()
        return float(res[0]) if res and res[0] is not None else 0.0
    except: return 0.0

def update_balance(amount, username, is_expense=True):
    """v68: Belirli bir kullanıcının bakiyesini günceller"""
    try:
        conn = get_db_connection()
        current = get_current_balance(username)
        new_balance = current - float(amount) if is_expense else current + float(amount)
        conn.execute("UPDATE kasalar SET bakiye = ? WHERE owner_username=?", (new_balance, username))
        conn.commit()
        conn.close()
        return new_balance
    except: return 0.0

def get_user_by_telegram_id(tid):
    """Telegram ID üzerinden kullanıcı bilgilerini getirir (v68)"""
    try:
        conn = get_db_connection()
        res = conn.execute("SELECT username, ad_soyad, role FROM kullanicilar WHERE telegram_id=?", (str(tid),)).fetchone()
        conn.close()
        return res if res else None
    except: return None

def set_telegram_id(username, tid):
    """Kullanıcının Telegram ID'sini kaydeder (v68)"""
    try:
        conn = get_db_connection()
        cursor = conn.execute("UPDATE kullanicilar SET telegram_id = ? WHERE username=?", (str(tid), username))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0
    except: return False

def save_ai_correction(ham_metin, isletme_dogru, tutar_dogru, tarih_dogru, kategori_dogru):
    """AI hatalarını düzeltmek için hafızaya kaydeder (Feature 5)"""
    try:
        conn = get_db_connection()
        conn.execute('''INSERT INTO ogrenme_hafizasi 
                     (ham_metin, isletme_adi_dogru, tutar_dogru, tarih_dogru, kategori_dogru) 
                     VALUES (?,?,?,?,?)''', 
                     (ham_metin, isletme_dogru, float(tutar_dogru) if tutar_dogru else 0, tarih_dogru, kategori_dogru))
        conn.commit()
        conn.close()
        return True
    except: return False

def get_ai_examples():
    """Hafızadaki düzeltmeleri örnek olarak getirir"""
    try:
        conn = get_db_connection()
        res = conn.execute("SELECT ham_metin, isletme_adi_dogru, tutar_dogru, tarih_dogru, kategori_dogru FROM ogrenme_hafizasi ORDER BY id DESC LIMIT 3").fetchall()
        conn.close()
        examples_str = ""
        for i, row in enumerate(res):
            examples_str += f"\nÖrnek {i+1}:\nMetin: {row[0][:200]}...\nÇıktı: {{\"isletme_adi\": \"{row[1]}\", \"tarih\": \"{row[3]}\", \"tutar\": {row[2]}, \"kategori\": \"{row[4]}\"}}\n"
        return examples_str
    except: return ""

def masraf_kaydet_excel(veri_dict, kasa_adi="Bilinmiyor"):
    """Harcama verilerini Excel dosyasına ekler (v68.14: kasa_adi eklendi)"""
    from datetime import datetime
    excel_path = os.path.join(BASE_DIR, "masraf_arsivi.xlsx")
    cols = ["Harcama Tarihi", "Harcama Tutarı", "Harcama Açıklaması", "Kategori", "Belge_Yolu", "Kayıt_Tarihi", "İşlem Yapılan Kasa"]
    
    try:
        # Önce SQL'e yaz
        save_expense_to_sql(veri_dict, kasa_adi)
        
        if not os.path.exists(excel_path):
            df = pd.DataFrame(columns=cols)
            df.to_excel(excel_path, index=False)
        else:
            df = pd.read_excel(excel_path)
            
        # Yeni satır hazırla
        yeni_satir = {
            "Harcama Tarihi": veri_dict.get("tarih", ""),
            "Harcama Tutarı": veri_dict.get("tutar", ""),
            "Harcama Açıklaması": veri_dict.get("isletme_adi", ""),
            "Kategori": veri_dict.get("kategori", "Muhtelif"),
            "Belge_Yolu": veri_dict.get("dosya_yolu", ""),
            "Kayıt_Tarihi": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "İşlem Yapılan Kasa": kasa_adi
        }
        
        df = pd.concat([df, pd.DataFrame([yeni_satir])], ignore_index=True)
        df.to_excel(excel_path, index=False)
        return True
    except Exception as e:
        log_activity(f"Excel Kayıt Hatası: {e}", "ERROR")
        return False

# --- V47: HARCAMA ODAKLI AI ANALİZÖR (Gelişmiş) ---
def gemini_v45_expense_analyze(text, image_data=None):
    """v63: Multimodal (Görsel + Metin) Analizör (v67 Learning Ready)"""
    if not GEMINI_API_KEY:
        return {"error": "API Key Missing"}
        
    examples = get_ai_examples()
    
    prompt = f"""
    Sen bir harcama analiz uzmanısın. Ekteki görseli (veya metni) incele. 
    İşletme adını, fiş tarihini ve toplam tutarı ayıkla.
    
    KURALLAR:
    1. Tutar hanesinde virgül (,) varsa nokta (.) olarak düşün. (Örn: 350,50 -> 350.50)
    2. SADECE sayısal tutarı döndür, TL yazma.
    3. JSON formatı DıŞıNDA hiçbir metin ekleme.
    
    JSON yapısı:
    {{
      "isletme_adi": "İşletme adı",
      "tarih": "YYYY-MM-DD",
      "tutar": 350.50,
      "kategori": "Yemek, Akaryakıt, Konaklama, Muhtelif seçeneklerinden biri"
    }}
    
    Aşağıdaki örnekler senin geçmişte yaptığın hatalardan öğrenmen içindir:
    {examples}
    
    Eğer bilgiyi bulamazsan null yerine en yakın tahmini yap veya 'Bilinmiyor' yaz.
    """
    
    # Metod 1: SDK (v66: 1.5-flash + Base64 Manual Part)
    raw_ans = ""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        parts = []
        if image_data:
            import base64
            img_b64 = base64.b64encode(image_data).decode('utf-8')
            mime = "application/pdf" if image_data.startswith(b"%PDF") else "image/jpeg"
            parts.append(types.Part.from_bytes(data=image_data, mime_type=mime))
        
        parts.append(types.Part.from_text(text=prompt))
        
        # v66: En stabil model (gemini-1.5-flash)
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=parts,
            config=types.GenerateContentConfig(temperature=0.0)
        )
        raw_ans = response.text
    except Exception as e:
        print(f"v66 SDK Hatası: {e}")
        # Metod 2: Backup model (gemini-2.0-flash-exp)
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash-exp',
                contents=parts,
                config=types.GenerateContentConfig(temperature=0.0)
            )
            raw_ans = response.text
        except Exception as e2:
            print(f"v66 Backup Hatası: {e2}")
            # Metod 3: Direct REST Fallback (Sadece Metin)
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
                headers = {'Content-Type': 'application/json'}
                payload = {"contents": [{"parts": [{"text": f"{prompt}\n\nMetin:\n{text}"}]}]}
                res = requests.post(url, headers=headers, json=payload, timeout=30)
                raw_data = res.json()
                if 'candidates' in raw_data:
                    raw_ans = raw_data['candidates'][0]['content']['parts'][0]['text']
            except Exception as e3:
                print(f"v66 Kritik Hata: {e3}")

    if not raw_ans:
        return {"error": "Analiz başarısız", "raw_response": "AI boş yanıt döndürdü."}

    try:
        raw_json = clean_json_string(raw_ans)
        data = json.loads(raw_json)
        data["raw_response"] = raw_ans
        return data
    except Exception as e3:
        return {
            "error": "JSON Ayrıştırma Hatası", 
            "isletme_adi": "Bilinmiyor", 
            "raw_response": raw_ans
        }
