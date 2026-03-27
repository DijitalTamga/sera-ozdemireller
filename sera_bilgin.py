import os
import sqlite3
import argparse
from datetime import datetime
from sera_core import process_document, get_db_connection, SIRKET_ARSIV_YOLU, log_activity

def belge_tara(use_enhancement=False):
    # Arşiv yolu kontrolü
    if not os.path.exists(SIRKET_ARSIV_YOLU):
        print(f"❌ HATA: Arşiv yolu bulunamadı: {SIRKET_ARSIV_YOLU}")
        log_activity(f"Arşiv yolu bulunamadı: {SIRKET_ARSIV_YOLU}", "ERROR")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    
    print(f"🔍 Arşiv Taraması Başlatıldı: {SIRKET_ARSIV_YOLU}")
    print(f"✨ Görüntü İyileştirme: {'AÇIK' if use_enhancement else 'KAPALI'}")
    
    toplam_dosya = 0
    yeni_eklenen = 0
    hata_sayisi = 0
    
    for root, dirs, files in os.walk(SIRKET_ARSIV_YOLU):
        for file in files:
            if file.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
                toplam_dosya += 1
                cursor.execute("SELECT id FROM belgeler WHERE dosya_adi=?", (file,))
                if cursor.fetchone(): 
                    continue
                
                print(f"🔄 Hafızaya Alınıyor: {file}", end="\r")
                yol = os.path.join(root, file)
                
                try:
                    tam_metin = process_document(yol, is_path=True, use_enhancement=use_enhancement)
                    
                    if tam_metin.strip():
                        tarih_str = datetime.now().strftime("%d.%m.%Y %H:%M")
                        cursor.execute("""INSERT INTO belgeler 
                                      (dosya_adi, tarih, ham_metin, dosya_yolu, kategori) 
                                      VALUES (?, ?, ?, ?, ?)""", 
                                     (file, tarih_str, tam_metin, yol, "Genel Arşiv"))
                        conn.commit()
                        yeni_eklenen += 1
                    else:
                        print(f"⚠️ Uyarı: {file} içeriği boş veya okunamadı.           ")
                        
                except Exception as e:
                    print(f"❌ Okuma Hatası ({file}): {e}           ")
                    hata_sayisi += 1
    
    conn.close()
    
    print("\n" + "="*30)
    print(f"📊 TARAMA ÖZETİ")
    print(f"📁 Toplam Taranan Belge: {toplam_dosya}")
    print(f"✅ Yeni Eklenen: {yeni_eklenen}")
    print(f"❌ Hata Sayısı: {hata_sayisi}")
    print("="*30)
    log_activity(f"Bağımsız tarama tamamlandı. Yeni: {yeni_eklenen}, Hata: {hata_sayisi}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sera-Bilgin Arşiv Tarayıcı")
    parser.add_argument("--enhance", action="store_true", help="Görüntü iyileştirmeyi etkinleştir")
    args = parser.parse_args()
    
    belge_tara(use_enhancement=args.enhance)
