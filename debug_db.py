import sqlite3
import os

# Sera_OCR/_internal dizinindeki veritabanini bulmaya calis
DB_PATH = r"C:\Users\Nurettin Ö\Desktop\Sera_OCR\_internal\arsiv_hafizasi.db"

def diagnose():
    if not os.path.exists(DB_PATH):
        print(f"HATA: Veritabani bulunamadi: {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print("--- TABLOLAR ---")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        for t in tables:
            print(f"Tablo: {t[0]}")
            
        print("\n--- KULLANICILAR (kullanicilar) ---")
        try:
            cursor.execute("SELECT username, role, ad_soyad FROM kullanicilar")
            users = cursor.fetchall()
            for u in users:
                print(f"User: {u[0]} | Role: {u[1]} | Name: {u[2]}")
        except Exception as e:
            print(f"kullanicilar tablosu okunamadi: {e}")

        print("\n--- KASALAR ---")
        try:
            cursor.execute("SELECT kasa_adi, owner_username, bakiye FROM kasalar")
            vaults = cursor.fetchall()
            for v in vaults:
                print(f"Kasa: {v[0]} | Owner: {v[1]} | Bal: {v[2]}")
        except Exception as e:
            print(f"kasalar tablosu okunamadi: {e}")

        conn.close()
    except Exception as e:
        print(f"Genel Hata: {e}")

if __name__ == "__main__":
    diagnose()
