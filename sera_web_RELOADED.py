# Sera-Bilgin Arşiv Sistemi - v86 (Cache Fix)
import streamlit as st
import hashlib
import os
import pandas as pd
import io
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from sera_core import (
    db_init, get_db_connection, tr_lower, tr_normalize, 
    process_document, extract_v40_info, SIRKET_ARSIV_YOLU,
    db_log, analyze_with_gemini, base64_encode_file,
    gemini_v43_analyze, scrub_ocr_text,
    masraf_kaydet_excel, gemini_v45_expense_analyze,
    list_available_models, GEMINI_API_KEY,
    is_duplicate_expense, save_expense_to_sql,
    save_ai_correction, update_balance
)

# --- VERİTABANI BAŞLAT ---
db_init()

# --- ARAYÜZ AYARLARI ---
st.set_page_config(page_title="SERA-BİLGİN ANALİTİK", layout="wide", page_icon="🧠")

# v71: SERA.AI - SOFTER ANTIGRAVITY CSS
def apply_antigravity_styles():
    st.markdown("""
    <style>
    /* 1. Global Reset & Theme (v71: Softer & Turkish) */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;600;900&display=swap');
    
    :root {
        --bg-obsidian: #0f172a;
        --neon-cyan: #22d3ee;
        --deep-violet: #8b5cf6;
        --glass-bg: rgba(30, 41, 59, 0.4);
        --glass-border: rgba(255, 255, 255, 0.1);
    }

    html, body, [data-testid="stAppViewContainer"] {
        background-color: var(--bg-obsidian) !important;
        font-family: 'Outfit', sans-serif !important;
        color: #f1f5f9 !important;
    }

    /* 2. Glassmorphism & Soft Panels */
    [data-testid="stSidebar"], .stExpander, div[data-testid="stForm"] {
        background: var(--glass-bg) !important;
        backdrop-filter: blur(20px) saturate(160%) !important;
        border: 1px solid var(--glass-border) !important;
        border-radius: 16px !important;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1) !important;
    }

    /* 3. Blinking SERA.AI Effect */
    @keyframes blink {
        0%, 100% { opacity: 1; text-shadow: 0 0 20px var(--neon-cyan); }
        50% { opacity: 0.4; text-shadow: none; }
    }
    .sera-ai-logo {
        animation: blink 2s linear infinite;
        font-weight: 900;
        letter-spacing: 4px;
        color: var(--neon-cyan);
    }

    /* Footer Design */
    .st-footer {
        position: fixed;
        bottom: 0px;
        left: 0;
        width: 100%;
        text-align: center;
        padding: 10px;
        background: rgba(15, 23, 42, 0.8);
        border-top: 1px solid var(--glass-border);
        font-size: 0.8rem;
        color: #94a3b8;
        z-index: 1000;
        letter-spacing: 1px;
    }

    /* 4. Neon Buttons (Turkish) */
    .stButton > button {
        background: linear-gradient(135deg, var(--deep-violet) 0%, #6d28d9 100%) !important;
        border: 1px solid var(--glass-border) !important;
        color: white !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
    }

    /* Kasa Girişi - Yeşil Buton */
    .giris-btn > button {
        background: linear-gradient(135deg, #16a34a 0%, #15803d 100%) !important;
        border: 1px solid rgba(34,197,94,0.4) !important;
        color: white !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        box-shadow: 0 0 15px rgba(34,197,94,0.25) !important;
    }
    .giris-btn > button:hover {
        box-shadow: 0 0 25px rgba(34,197,94,0.5) !important;
        transform: translateY(-2px);
    }

    /* Kasa Çıkışı - Kırmızı Buton */
    .cikis-btn > button {
        background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%) !important;
        border: 1px solid rgba(239,68,68,0.4) !important;
        color: white !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        box-shadow: 0 0 15px rgba(239,68,68,0.25) !important;
    }
    .cikis-btn > button:hover {
        box-shadow: 0 0 25px rgba(239,68,68,0.5) !important;
        transform: translateY(-2px);
    }

    /* 6. High-Tech Typography (Turkish Focus) */
    h1, h2, h3 {
        background: linear-gradient(90deg, #fff, var(--neon-cyan));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 900 !important;
    }

    /* Sidebar Logo Fix */
    [data-testid="stSidebarNav"]::before {
        content: "SERA.AI 👁️ OS";
        margin-left: 20px;
        margin-top: 20px;
        font-size: 1.4rem;
        font-weight: 900;
        color: var(--neon-cyan);
        letter-spacing: 2px;
    }
    /* 7. Input Label Focus (v74) */
    div[data-baseweb="input"] {
        background: rgba(255, 255, 255, 0.1) !important;
        border: 1px solid rgba(34, 211, 238, 0.2) !important;
        color: white !important;
        border-radius: 10px !important;
    }
    label[data-testid="stWidgetLabel"] p {
        color: #ffffff !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        letter-spacing: 1px;
    }

    /* Professional Logo Style (v74) */
    .premium-logo {
        font-family: 'Outfit', sans-serif;
        font-weight: 900;
        font-size: 4rem;
        background: linear-gradient(135deg, #fff 0%, var(--neon-cyan) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 0 0 30px rgba(34, 211, 238, 0.3);
        margin-bottom: 0px;
    }
    .eye-icon {
        font-size: 3rem;
        filter: drop-shadow(0 0 10px var(--neon-cyan));
        margin-left: 10px;
        vertical-align: middle;
    }
    
    /* 8. Tabs Styling (v77: High Contrast) */
    button[data-baseweb="tab"] {
        color: #ffffff !important;
        opacity: 0.7;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: var(--neon-cyan) !important;
        opacity: 1;
        font-weight: 900 !important;
        border-bottom-color: var(--neon-cyan) !important;
    }
    button[data-baseweb="tab"] p {
        color: inherit !important;
        font-weight: 700 !important;
        font-size: 1.1rem !important;
    }
    
    /* 9. Metric Styling (v78: High Contrast) */
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-weight: 900 !important;
        font-size: 2rem !important;
        text-shadow: 0 0 10px rgba(255,255,255,0.2) !important;
    }
    [data-testid="stMetricLabel"] {
        color: var(--neon-cyan) !important;
        font-weight: 700 !important;
        opacity: 0.9 !important;
        letter-spacing: 1px;
    }

    /* 10. Kasa Card Styling (v79: Corporate Groupbox) */
    .kasa-card {
        background: rgba(30, 41, 59, 0.5) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 15px !important;
        padding: 20px !important;
        margin-bottom: 20px !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2) !important;
        transition: transform 0.3s ease !important;
    }
    .kasa-card:hover {
        transform: translateY(-5px) !important;
        border-color: var(--neon-cyan) !important;
    }
    .kasa-card-header {
        font-size: 1.2rem;
        font-weight: 900;
        color: var(--neon-cyan);
        margin-bottom: 10px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        padding-bottom: 5px;
    }
    .kasa-card-info {
        font-size: 0.85rem;
        color: #f1f5f9 !important; /* v80: Daha okunaklı beyaz */
        margin-bottom: 5px;
    }

    /* 11. Table & DataFrame Styling (v80: True Dark Mode) */
    [data-testid="stDataFrame"], [data-testid="stTable"], table {
        background-color: transparent !important;
        color: #ffffff !important;
    }
    th {
        background-color: rgba(34, 211, 238, 0.2) !important;
        color: var(--neon-cyan) !important;
    }
    td {
        background-color: rgba(255, 255, 255, 0.05) !important;
        color: #ffffff !important;
    }
    
    /* Input Labels Readability (v80) */
    label[data-testid="stWidgetLabel"] p {
        color: #ffffff !important;
        font-weight: 800 !important;
        text-shadow: 1px 1px 2px black;
    }
    /* Slide-In Başarı Animasyonu */
    @keyframes slideInDown {
        0%   { transform: translateY(-60px) scale(0.95); opacity: 0; }
        60%  { transform: translateY(8px)   scale(1.02); opacity: 1; }
        100% { transform: translateY(0px)   scale(1);    opacity: 1; }
    }
    @keyframes fadeOut {
        0%   { opacity: 1; }
        80%  { opacity: 1; }
        100% { opacity: 0; }
    }
    .islem-basarili {
        animation: slideInDown 0.55s cubic-bezier(.22,.68,0,1.2) forwards;
        border-radius: 16px;
        padding: 28px 36px;
        text-align: center;
        font-family: 'Outfit', sans-serif;
        font-size: 1.6rem;
        font-weight: 900;
        letter-spacing: 2px;
        margin: 24px 0;
        box-shadow: 0 8px 32px rgba(0,0,0,0.35);
    }
    .islem-basarili.giris {
        background: linear-gradient(135deg, rgba(22,163,74,0.25), rgba(21,128,61,0.4));
        border: 2px solid rgba(34,197,94,0.6);
        color: #4ade80;
        text-shadow: 0 0 20px rgba(34,197,94,0.6);
    }
    .islem-basarili.cikis {
        background: linear-gradient(135deg, rgba(220,38,38,0.25), rgba(185,28,28,0.4));
        border: 2px solid rgba(239,68,68,0.6);
        color: #f87171;
        text-shadow: 0 0 20px rgba(239,68,68,0.6);
    }
    .islem-detay {
        font-size: 1rem;
        font-weight: 500;
        margin-top: 10px;
        opacity: 0.85;
        letter-spacing: 0.5px;
    }
    </style>
    """, unsafe_allow_html=True)
    # Global Footer
    st.markdown("<div class='st-footer'>Powered By Nurettin ÖZCAN</div>", unsafe_allow_html=True)

apply_antigravity_styles()
st.sidebar.code("v86 - SERA.AI 👁️ - " + datetime.now().strftime("%H:%M:%S"))

with st.sidebar.expander("🔍 Model Keşif Paneli"):
    if st.button("Mevcut Modelleri Listele"):
        models = list_available_models(GEMINI_API_KEY)
        st.json(models)

if 'logged_in' not in st.session_state: 
    st.session_state['logged_in'] = False

# --- 🔒 GİRİŞ EKRANI (v74: PREMIUM EDITION) ---
if not st.session_state['logged_in']:
    if 'anim_shown' not in st.session_state:
        st.markdown("""
        <div style='text-align: center; padding: 100px;' class='hero-animate'>
            <div class='premium-logo'>SERA.AI <span class='eye-icon'>👁️</span></div>
            <h2 style='color: var(--deep-violet); font-size: 2rem; letter-spacing: 8px; margin-top: -20px;'>ÖZDEMİRELLER</h2>
            <p style='margin-top: 20px; color: #ffffff; opacity: 0.6;'>Elektronik Arşiv & Görsel Zeka Sistemi</p>
        </div>
        """, unsafe_allow_html=True)
        st.session_state['anim_shown'] = True
        import time; time.sleep(1.8)
        st.rerun()

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<div class='levitate-box' style='padding: 30px; background: rgba(15, 23, 42, 0.6); border-radius: 20px; border: 1px solid rgba(255,255,255,0.1);'>", unsafe_allow_html=True)
        st.markdown("<div style='text-align: center; margin-bottom: 30px;'>", unsafe_allow_html=True)
        st.markdown("<span class='premium-logo' style='font-size: 2.5rem;'>SERA.AI</span><span class='eye-icon' style='font-size: 2rem;'>👁️</span>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        u_name = st.text_input("👤 KULLANICI ADI", placeholder="Kullanıcı adınızı girin...")
        st.write("") # Boşluk
        p_word = st.text_input("🔑 ERİŞİM ŞİFRESİ", type='password', placeholder="••••••••")
        
        st.markdown("<div style='margin-top: 25px;'>", unsafe_allow_html=True)
        if st.button("SİSTEME GİRİŞİ ONAYLA", use_container_width=True):
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT password, role, ad_soyad, birim FROM kullanicilar WHERE username=?", (u_name,))
            data = c.fetchone()
            conn.close()
            if data and hashlib.sha256(p_word.encode()).hexdigest() == data[0]:
                st.session_state.update({
                    'logged_in': True, 'u_full': data[2], 'u_role': data[1], 
                    'u_birim': data[3], 'u_name': u_name
                })
                db_log("Sisteme Giriş Yapıldı", u_name)
                st.rerun()
            else: 
                st.error("❌ ERİŞİM REDDEDİLDİ: GEÇERSİZ KİMLİK BİLGİLERİ")
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<p style='margin-top: 30px; text-align: center; color: #64748b; font-size: 0.8rem;'>Powered By Nurettin ÖZCAN</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
else:
    # --- YAN MENÜ ---
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state['u_full']}")
        st.info(f"🏢 {st.session_state['u_birim']} - {st.session_state['u_role']}")
        
        # V41: API Anahtarı Kontrolü
        from sera_core import GEMINI_API_KEY
        if not GEMINI_API_KEY:
            st.warning("⚠️ GEMINI_API_KEY bulunamadı! AI özellikleri (Özetleme, Asistan) devre dışı.")
        
        menu_options = ["🔍 Arşivde Ara", "📤 Evrak Yükle & Analiz (V40)", "💰 Masraf Süreci / Fiş Yükle"]
        if st.session_state['u_role'] in ["Ön Muhasebe", "Admin"]:
            menu_options.append("💸 Kasa İşlemleri")
        menu_options.append("⚙️ Yönetim Paneli")
        
        choice = st.selectbox("İşlem Menüsü", menu_options)
        st.divider()
        if st.button("🔴 GÜVENLİ ÇIKIŞ", use_container_width=True):
            db_log("Güvenli Çıkış Yapıldı", st.session_state['u_name'])
            st.session_state['logged_in'] = False
            st.rerun()

    # --- 🔍 MODÜL 1: GELİŞMİŞ ARAMA ---
    if choice == "🔍 Arşivde Ara":
        st.header("🔍 Akıllı Arşiv Taraması")
        
        c1, c2 = st.columns([3, 1])
        with c1:
            ara_input = st.text_input("Kişi, TC veya Kelime Yazın...")
        with c2:
            st.write("") # Boşluk
            st.write("")
            report_btn = st.button("📊 Excel Raporu Al", use_container_width=True)
        
        # V41: Boş aramada tüm listeyi getir
        if True: # Her zaman kontrol et
            conn = get_db_connection()
            df_all = pd.read_sql_query("SELECT * FROM belgeler ORDER BY tarih DESC", conn)
            conn.close()
            
            if not df_all.empty:
                # DEBUG: Veritabanı içeriğini kontrol et (Sadece Admin görebilir)
                with st.expander("🛠️ Debug: Veritabanı Ham Veri"):
                    st.write("Veritabanındaki dosyalar:")
                    st.write(df_all[["dosya_adi", "tc_no", "kategori"]])
                    st.write(f"Aranan Terim: [{ara_input}]")

                if ara_input:
                    # v50: KESİN ÇÖZÜM ARAMA (Pandas tabanlı hassas arama)
                    ara_clean = tr_lower(ara_input).strip()
                    mask = (
                        df_all['dosya_adi'].str.contains(ara_clean, na=False, case=False) |
                        df_all['ham_metin'].str.contains(ara_clean, na=False, case=False) |
                        df_all['isim_eslesme'].str.contains(ara_clean, na=False, case=False) |
                        df_all['tc_no'].str.contains(ara_clean, na=False, case=False)
                    )
                    df = df_all[mask]
                else:
                    df = df_all
                
                if report_btn and not df.empty:
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.drop(columns=['ham_metin']).to_excel(writer, index=False, sheet_name='Arşiv Raporu')
                    st.download_button(
                        label="📥 Excel Dosyasını İndir",
                        data=output.getvalue(),
                        file_name=f"sera_arsiv_raporu_{datetime.now().strftime('%d%m%Y')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
                if not df.empty:
                    st.success(f"🗄️ Arşivde toplam {len(df_all)} belge var. {f'({len(df)} sonuç gösteriliyor)' if ara_input else ''}")
                    
                    # v71/v76: KLASÖR + SEÇİM YAPISI (Kategoriye göre grupla ve performans artır)
                    categories = df['kategori'].unique()
                    for cat in categories:
                        cat_df = df[df['kategori'] == cat]
                        with st.expander(f"📁 {cat} ({len(cat_df)} Belge)"):
                            # v76: Klasör içinde seçim kutusu (Kasılmayı engeller)
                            doc_names = cat_df['dosya_adi'].tolist()
                            sel_doc_name = st.selectbox(f"İncelemek istediğiniz belgeyi seçin ({cat})", ["--- Seçiniz ---"] + doc_names, key=f"sel_{cat}")
                            
                            if sel_doc_name != "--- Seçiniz ---":
                                row = cat_df[cat_df['dosya_adi'] == sel_doc_name].iloc[0]
                                
                                st.markdown(f"📄 **{row['dosya_adi']}** | 🗓️ {row['tarih']}")
                                col_det1, col_det2 = st.columns([1, 1])
                                with col_det1:
                                    st.write(f"👤 {row['isim_eslesme'] or 'Bilinmiyor'} | TC: {row['tc_no'] or '-'}")
                                with col_det2:
                                    if row['dosya_yolu'] and os.path.exists(row['dosya_yolu']):
                                        with open(row['dosya_yolu'], "rb") as f:
                                            st.download_button(f"📥 İndir", f, file_name=row['dosya_adi'], key=f"dl_{row['id']}")
                                
                                st.divider()
                                # --- 👁️ BELGE ÖNİZLEME (V42) ---
                                st.markdown("### 👁️ Belge Önizleme")
                                if row['dosya_yolu'] and os.path.exists(row['dosya_yolu']):
                                    if row['dosya_adi'].lower().endswith(('.pdf')):
                                        base64_pdf = base64_encode_file(row['dosya_yolu'])
                                        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
                                        st.markdown(pdf_display, unsafe_allow_html=True)
                                    elif row['dosya_adi'].lower().endswith(('.png', '.jpg', '.jpeg')):
                                        st.image(row['dosya_yolu'], use_container_width=True)
                                
                                # --- 📝 BİLGİ GÜNCELLEME (v76: Unique Key Fix) ---
                                if st.session_state['u_role'] in ['Admin', 'Yönetici']:
                                    with st.expander("🛠️ Bilgileri Güncelle"):
                                        with st.form(key=f"edit_form_{cat}_{row['id']}"):
                                            new_isim = st.text_input("👤 İlgili İsim", value=row['isim_eslesme'])
                                            new_tc = st.text_input("🔢 TC No", value=row['tc_no'])
                                            conn = get_db_connection()
                                            kats = [r[0] for r in conn.execute("SELECT kat_ad FROM kategoriler").fetchall()]
                                            conn.close()
                                            new_kat = st.selectbox("📁 Kategori", kats, index=kats.index(row['kategori']) if row['kategori'] in kats else 0)
                                            
                                            if st.form_submit_button("✅ Değişiklikleri Kaydet"):
                                                conn = get_db_connection()
                                                conn.execute("UPDATE belgeler SET isim_eslesme=?, tc_no=?, kategori=? WHERE id=?", 
                                                             (new_isim, new_tc, new_kat, row['id']))
                                                conn.commit()
                                                conn.close()
                                                db_log("Belge Bilgileri Güncellendi", st.session_state['u_name'], f"Dosya ID: {row['id']}")
                                                st.success("Bilgiler güncellendi!")
                                                st.rerun()
                                
                                # AI ASİSTAN MODÜLÜ
                                st.markdown("### 🤖 SERA.AI ASİSTAN")
                                ai_soru = st.text_input(f"Belge hakkında soru sorun:", key=f"ai_q_{row['id']}")
                                if ai_soru:
                                    with st.spinner("🧠 AI Düşünüyor..."):
                                        cevap = analyze_with_gemini(row['ham_metin'], ai_soru)
                                        st.info(cevap)
                            else:
                                st.info("Lütfen detaylarını görmek istediğiniz bir belge seçin.")

                else: 
                    st.warning("Eşleşen sonuç bulunamadı.")
            else:
                st.info("🗄️ Arşiv henüz boş. 'Evrak Yükle' veya 'Sera-Bilgin' tarayıcısını kullanarak belge ekleyebilirsiniz.")

    # --- 📤 MODÜL 2: V40 AI ANALİZLİ YÜKLEME ---
    elif choice == "📤 Evrak Yükle & Analiz (V40)":
        st.header("🧠 V40 Yapay Zeka Analiz Merkezi")
        
        tab_tek, tab_toplu = st.tabs(["📄 Tekli Yükleme", "📚 Toplu Arşivleme"])
        
        with tab_tek:
            c1, c2 = st.columns([1, 1])
            with c1:
                file = st.file_uploader("Belge Seçin", type=['pdf', 'png', 'jpg', 'jpeg'], key="single_upload")
                use_enhance = st.checkbox("🔍 Görüntü İyileştirme", value=True, key="en_single")
                
            if file:
                with st.spinner("🧠 Belge analiz ediliyor (v43 Akıllı Analiz)..."):
                    ham_metin = process_document(file, is_path=False, use_enhancement=use_enhance)
                    # V43: Gelişmiş JSON Analizi
                    v43_data = gemini_v43_analyze(ham_metin)
                    extracted = extract_v40_info(ham_metin) # Fallback ve RegEx uyumu için devam
                
                st.success("✅ v43 Akıllı Analiz Tamamlandı!")
                with st.form("kayit_formu_single"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        conn = get_db_connection()
                        kats = [r[0] for r in conn.execute("SELECT kat_ad FROM kategoriler").fetchall()]
                        conn.close()
                        
                        # V43: Otomatik Kategori Seçimi (Gemini Tahmini Öncelikli)
                        current_kat = v43_data.get("kategori_tahmini", extracted["kategori"])
                        default_index = kats.index(current_kat) if current_kat in kats else 0
                        v_kat = st.selectbox("📌 Kategori", kats if kats else ["Genel Arşiv"], index=default_index)
                        
                        # V43: Akıllı İsim ve Kurum Birleşimi
                        v_ad = st.text_input("📝 Evrak Adı", value=f"{v43_data.get('belge_tipi', 'Belge')} - {v43_data.get('kurum', '')} - {file.name}")
                    with col_b:
                        v_tc = st.text_input("🔢 Tespit Edilen TC", value=extracted["tc"])
                        v_isim = st.text_input("👤 İlgili / Kurum", value=v43_data.get("kurum", extracted["isim"]))
                    
                    # V43: Özet ve Kritik Tarih Bilgisi
                    st.info(f"📋 **AI Özeti:** {v43_data.get('ozet', 'Özet çıkarılamadı.')}")
                    if v43_data.get("kritik_tarih"):
                        st.warning(f"⏰ **Kritik Tarih Tespit Edildi:** {v43_data.get('kritik_tarih')}")
                    
                    # V41: Tarih Uyarıları
                    if extracted["tarihler"]:
                        st.warning(f"⚠️ Belge içerisinde şu tarihler tespit edildi: {', '.join(extracted['tarihler'])}. Tarih takibi gerekebilir!")
                    
                    if st.form_submit_button("💾 ARŞİVE KAYDET", use_container_width=True):
                        try:
                            # V42.1: Kategori adındaki geçersiz karakterleri temizle (/, \ gibi)
                            v_kat_safe = v_kat.replace("/", "-").replace("\\", "-")
                            target_dir = os.path.join(SIRKET_ARSIV_YOLU, v_kat_safe)
                            if not os.path.exists(target_dir): os.makedirs(target_dir)
                            f_path = os.path.join(target_dir, v_ad)
                            with open(f_path, "wb") as f: f.write(file.getbuffer())
                            
                            conn = get_db_connection()
                            conn.execute("INSERT INTO belgeler (dosya_adi, kategori, yukleyen, tc_no, ham_metin, isim_eslesme, dosya_yolu) VALUES (?,?,?,?,?,?,?)",
                                         (v_ad, v_kat, st.session_state['u_full'], v_tc, ham_metin, v_isim, f_path))
                            conn.commit()
                            conn.close()
                            db_log("Yeni Belge Eklendi", st.session_state['u_name'], v_ad)
                            # V45 AUTO-TRIGGER KALDIRILDI (Artık v46 Masraf Menüsü Kullanılacak)
                            # if v_kat == "MUHASEBE" or "fatura" in v_ad.lower() or "fiş" in v_ad.lower():
                            #     expense_data = gemini_v45_expense_analyze(ham_metin)
                            #     masraf_kaydet_excel(expense_data)
                            
                            st.balloons(); st.success("Arşivlendi!")
                        except Exception as e: st.error(f"Hata: {e}")

        with tab_toplu:
            st.info("Birden fazla dosyayı sürükleyip bırakın. Sistem hepsini otomatik analiz edip 'Genel Arşiv' kategorisine kaydedecektir.")
            files = st.file_uploader("Toplu Belgeler", type=['pdf', 'png', 'jpg', 'jpeg'], accept_multiple_files=True)
            if files and st.button("🚀 TOPLU İŞLEMEYİ BAŞLAT"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, f in enumerate(files):
                    status_text.text(f"İşleniyor ({i+1}/{len(files)}): {f.name}")
                    ham_metin = process_document(f, is_path=False, use_enhancement=True)
                    # V43: Toplu İşlemde Akıllı Analiz
                    v43_data = gemini_v43_analyze(ham_metin)
                    
                    v_kat_auto = v43_data.get("kategori_tahmini", "Genel Arşiv")
                    # V42.1: Kategori adındaki geçersiz karakterleri temizle
                    v_kat_safe = v_kat_auto.replace("/", "-").replace("\\", "-")
                    target_dir = os.path.join(SIRKET_ARSIV_YOLU, v_kat_safe)
                    if not os.path.exists(target_dir): os.makedirs(target_dir)
                    
                    # Evrak Adı Formatı (v43)
                    v43_ad = f"{v43_data.get('belge_tipi', 'Belge')} - {v43_data.get('kurum', '')} - {f.name}"
                    
                    f_path = os.path.join(target_dir, f.name) # Orijinal ismi koruyalım ama DB'ye v43 adıyla kaydedelim
                    with open(f_path, "wb") as save_f: save_f.write(f.getbuffer())
                    
                    conn = get_db_connection()
                    conn.execute("INSERT INTO belgeler (dosya_adi, kategori, yukleyen, tc_no, ham_metin, isim_eslesme, dosya_yolu) VALUES (?,?,?,?,?,?,?)",
                                 (v43_ad, v_kat_auto, st.session_state['u_full'], "Bilinmiyor", ham_metin, v43_data.get("kurum", "Bilinmiyor"), f_path))
                    conn.commit(); conn.close()
                    
                    # V45 AUTO-TRIGGER KALDIRILDI
                    # if v_kat_auto == "MUHASEBE" or ...
                    
                    progress_bar.progress((i + 1) / len(files))
                
                db_log("Toplu Yükleme Yapıldı", st.session_state['u_name'], f"{len(files)} dosya")
                st.success("Tüm dosyalar başarıyla işlendi!")

    # --- 💰 MODÜL 4: V46 ÖZEL MASRAF SÜRECİ ---
    elif choice == "💰 Masraf Süreci / Fiş Yükle":
        st.header("💰 Akıllı Masraf Yönetimi")
        st.info("Fiş veya fatura görselini yükleyin. AI verileri ayıklayacak ve onayınızdan sonra Excel'e kaydedecektir.")
        
        m_file = st.file_uploader("Fiş/Fatura Seçin", type=['pdf', 'png', 'jpg', 'jpeg'], key="msrf_up")
        # v70: OCR Tarama Animasyonu Overlay
        if m_file:
            st.markdown("<div class='scanner-line'></div>", unsafe_allow_html=True)
            with st.spinner("⏳ HOLOGRAPHIC SCANNING IN PROGRESS..."):
                m_metin = process_document(m_file, is_path=False, use_enhancement=True)
                # v63: Multimodal Geçiş (Görseli doğrudan gönder)
                m_data = gemini_v45_expense_analyze(m_metin, image_data=m_file.getvalue())
            
            # v47 Hata Takibi
            if "error" in m_data:
                st.error(f"⚠️ Analiz sırasında teknik bir hata oluştu: {m_data['error']}")
            
            with st.expander("🔍 Gemini Ham Yanıtı (Hata Ayıklama İçin)"):
                st.code(m_data.get("raw_response", "Yanıt boş veya alınamadı."))
            
            st.success("✅ Veriler Hazır!")
            with st.form("msrf_onay_form"):
                # v47: 4 Kolonlu Yapı
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    f_tarih = st.text_input("📅 Harcama Tarihi", value=m_data.get("tarih", ""))
                with c2:
                    f_tutar = st.text_input("💰 Toplam Tutar", value=m_data.get("tutar", ""))
                with c3:
                    f_desc = st.text_input("📝 Harcama Açıklaması", value=m_data.get("isletme_adi", ""))
                with c4:
                    cat_list = ["Yemek", "Akaryakıt", "Konaklama", "Muhtelif"]
                    # Gemini kategori tahmini uyumu
                    m_cat_guess = m_data.get("kategori", "Muhtelif")
                    try: 
                        idx = cat_list.index(m_cat_guess)
                    except: 
                        idx = 3 # Muhtelif
                    f_cat = st.selectbox("📂 Harcama Kategorisi", options=cat_list, index=idx)
                
                # v67: Mükerrer Kontrolü (Feature 2)
                is_dup = is_duplicate_expense(f_tarih, f_tutar, f_desc)
                if is_dup:
                    st.warning("⚠️ DİKKAT: Bu fiş (Tarih, Tutar ve İşletme bazında) daha önce kaydedilmiş görünüyor!")
                
                onsave = st.form_submit_button("✅ ONAYLA VE EXCEL'E KAYDET", use_container_width=True)
                
                if onsave:
                    if is_dup:
                        st.error("Mükerrer kayıt engellendi. Eğer yine de kaydetmek isterseniz lütfen açıklama kısmına küçük bir not ekleyin.")
                    else:
                        # Fiziksel dosyayı da MUHASEBE klasörüne kaydet
                        t_dir = os.path.join(SIRKET_ARSIV_YOLU, "MUHASEBE")
                        if not os.path.exists(t_dir): os.makedirs(t_dir)
                        m_path = os.path.join(t_dir, f"MSRF_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{m_file.name}")
                        with open(m_path, "wb") as mf: mf.write(m_file.getbuffer())
                        
                        # Excel'e yaz (v68.14: kasa_adi eklendi)
                        kasa_adi = f"Kasa {st.session_state['u_full']}"
                        veri = {"tarih": f_tarih, "tutar": f_tutar, "isletme_adi": f_desc, "kategori": f_cat, "dosya_yolu": m_path}
                        if masraf_kaydet_excel(veri, kasa_adi):
                            # v67: Human-in-the-Loop Öğrenme (Feature 5)
                            # AI tahmini ile kullanıcı girişi farklıysa "hafızaya" kaydet
                            if (f_desc != m_data.get("isletme_adi") or 
                                f_tarih != m_data.get("tarih") or 
                                str(f_tutar) != str(m_data.get("tutar")) or 
                                f_cat != m_data.get("kategori")):
                                save_ai_correction(m_metin, f_desc, f_tutar, f_tarih, f_cat)
                            
                            # v68: Bakiyeyi güncelle (Kullanıcıya özel kasa)
                            yeni_bakiye = update_balance(f_tutar, st.session_state['u_name'])
                            
                            # Aynı zamanda veritabanına (belgeler tablosuna) da sessizce kaydet (Arşiv bütünlüğü için)
                            conn = get_db_connection()
                            conn.execute("INSERT INTO belgeler (dosya_adi, kategori, yukleyen, tc_no, ham_metin, isim_eslesme, dosya_yolu) VALUES (?,?,?,?,?,?,?)",
                                         (os.path.basename(m_path), "MUHASEBE", st.session_state['u_full'], "Bilinmiyor", m_metin, f_desc, m_path))
                            conn.commit(); conn.close()
                            
                            st.balloons()
                            st.success(f"📌 Harcama Kaydedildi! Güncel Kasa: {yeni_bakiye:,.2f} TL")
                            db_log("Masraf Kaydı Yapıldı", st.session_state['u_name'], f"{f_tutar} - {f_desc}")
                        else:
                            st.error("Excel kaydı sırasında bir hata oluştu.")

    elif choice == "💸 Kasa İşlemleri":
        st.header("💸 Kasa ve Finans Kontrol Merkezi")
        
        tab_giris, tab_cikis, tab_yeni = st.tabs(["💚 Kasa Girişi", "🔴 Kasa Çıkış İşlemi", "🏦 Yeni Kasa Tanımla"])
        
        with tab_giris:
            st.info("Bu ekrandan koordinatörlerin kasalarına para girişi yapabilirsiniz.")
            conn = get_db_connection()
            df_kasalar = pd.read_sql_query("SELECT id, kasa_adi, owner_username, bakiye FROM kasalar", conn).fillna(0)
            conn.close()
            
            with st.form("kasa_giris_form_v86"):
                selected_kasa = st.selectbox("🎯 Hedef Kasa Seçin", options=df_kasalar['kasa_adi'].tolist())
                giris_tutari = st.number_input("💰 Giriş Tutarı (TL)", min_value=1.0, step=100.0)
                aciklama = st.text_input("📝 İşlem Açıklaması", value="Kasa Girişi")
                # v85: Submit butonunu div dışına çıkar (Missing Submit Button fix)
                submit = st.form_submit_button("💚 Kasa Girişi", use_container_width=True)
                
                if submit:
                    target_user = df_kasalar[df_kasalar['kasa_adi'] == selected_kasa]['owner_username'].iloc[0]
                    new_bal = update_balance(giris_tutari, target_user, is_expense=False)
                    
                    from sera_core import notify_user_telegram, gelir_kaydet_excel
                    gelir_kaydet_excel(target_user, giris_tutari, aciklama, selected_kasa)
                    notify_user_telegram(target_user, giris_tutari, aciklama)
                    db_log("Kasa Girişi", st.session_state['u_name'], f"{giris_tutari} TL -> {selected_kasa}")

                    st.markdown(f"""
                    <div class='islem-basarili giris'>
                        ✅ İşlem Başarılı
                        <div class='islem-detay'>
                            💰 {giris_tutari:,.2f} TL &nbsp;→&nbsp; {selected_kasa}<br>
                            🏦 Yeni Bakiye: <strong>{new_bal:,.2f} TL</strong>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    import time; time.sleep(2)
                    st.rerun()

        with tab_cikis:
            st.info("Bu ekrandan kasadan manuel gider çıkışı yapabilirsiniz. İşlem doğrudan Excel'e ve kasaya işlenir.")
            conn = get_db_connection()
            df_kasalar_c = pd.read_sql_query("SELECT id, kasa_adi, owner_username, bakiye FROM kasalar", conn).fillna(0)
            conn.close()

            with st.form("kasa_cikis_form_v86"):
                col1, col2 = st.columns(2)
                with col1:
                    selected_kasa_c = st.selectbox("🎯 Hedef Kasa Seçin", options=df_kasalar_c['kasa_adi'].tolist(), key="cikis_kasa")
                    cikis_tutari = st.number_input("💸 Çıkış Tutarı (TL)", min_value=1.0, step=10.0, key="cikis_tutar")
                with col2:
                    gider_turu = st.selectbox("📂 Gider Türü", options=["Yemek", "Akaryakıt", "Konaklama", "Muhtelif"], key="cikis_tur")
                    cikis_aciklama = st.text_input("📝 İşlem Açıklaması", key="cikis_aciklama")
                
                # Seçilen kasanın mevcut bakiyesini göster
                if not df_kasalar_c.empty:
                    secilen_bakiye = df_kasalar_c[df_kasalar_c['kasa_adi'] == selected_kasa_c]['bakiye'].iloc[0]
                    st.info(f"ℹ️ Seçili Kasa Güncel Bakiyesi: **{secilen_bakiye:,.2f} TL**")
                
                # v85: Submit butonunu div dışına çıkar
                submit_c = st.form_submit_button("🔴 Kasa Çıkışı Yap", use_container_width=True)

                if submit_c:
                    target_user_c = df_kasalar_c[df_kasalar_c['kasa_adi'] == selected_kasa_c]['owner_username'].iloc[0]
                    
                    # 1. Bakiyeyi güncelle (SQLite - güvenilir)
                    new_bal_c = update_balance(cikis_tutari, target_user_c, is_expense=True)
                    
                    # 2. Masraf kaydı yaz
                    veri_c = {
                        "tarih": datetime.now().strftime("%Y-%m-%d"),
                        "tutar": cikis_tutari,
                        "isletme_adi": cikis_aciklama or f"Manuel Cikis ({gider_turu})",
                        "kategori": gider_turu,
                        "dosya_yolu": "MANUEL GIRIS"
                    }
                    excel_ok_c = masraf_kaydet_excel(veri_c, selected_kasa_c)
                    if not excel_ok_c:
                        # Fallback: Excel yazma basarisiz olsa da SQLite kaydi garantile
                        from sera_core import save_expense_to_sql
                        save_expense_to_sql(veri_c, selected_kasa_c)
                    
                    kayit_durum = "OK" if excel_ok_c else "FALLBACK-SQL"
                    db_log("Kasa Cikisi", st.session_state['u_name'], f"{cikis_tutari} TL ({gider_turu}) <- {selected_kasa_c} | Excel:{kayit_durum}")

                    uyari_html = ""
                    if not excel_ok_c:
                        uyari_html = "<br><small style='color:#fbbf24'>&#9888; Excel yazılamadı, veritabanına kaydedildi</small>"

                    st.markdown(f"""
                    <div class='islem-basarili cikis'>
                        &#9989; İşlem Başarılı
                        <div class='islem-detay'>
                            &#128308; {cikis_tutari:,.2f} TL çıkışı yapıldı &nbsp;—&nbsp; {gider_turu}<br>
                            &#127974; {selected_kasa_c} Yeni Bakiye: <strong>{new_bal_c:,.2f} TL</strong>
                            {uyari_html}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    import time; time.sleep(2)
                    st.rerun()

        with tab_yeni:
            st.subheader("🛠️ Manuel Kasa Tanımlama")
            st.info("Sistemde kayıtlı bir kullanıcıya manuel olarak yeni bir kasa atayabilirsiniz.")
            
            with st.form("yeni_kasa_form"):
                n_kasa_ad = st.text_input("Kasa Adı (Örn: Saha Gider Kasası)")
                conn = get_db_connection()
                users_df = pd.read_sql_query("SELECT username, ad_soyad FROM kullanicilar", conn)
                conn.close()
                n_kasa_owner = st.selectbox("İlgili Kullanıcı", options=users_df['username'].tolist(), 
                                            format_func=lambda x: f"{x} ({users_df[users_df['username']==x]['ad_soyad'].iloc[0]})")
                n_kasa_bal = st.number_input("Başlangıç Bakiyesi (TL)", min_value=0.0, step=1000.0)
                
                n_kasa_submit = st.form_submit_button("KASAYI OLUŞTUR VE KAYDET", use_container_width=True)
                if n_kasa_submit:
                    if n_kasa_ad:
                        conn = get_db_connection()
                        conn.execute("INSERT OR IGNORE INTO kasalar (kasa_adi, owner_username, bakiye) VALUES (?,?,?)",
                                     (n_kasa_ad, n_kasa_owner, n_kasa_bal))
                        conn.commit()
                        conn.close()
                        st.success(f"✅ {n_kasa_ad} başarıyla oluşturuldu!")
                        db_log("Manuel Kasa Açıldı", st.session_state['u_name'], f"{n_kasa_ad} ({n_kasa_owner})")
                        st.rerun()
                    else:
                        st.error("Lütfen bir kasa ismi girin!")

    # --- ⚙️ MODÜL 3: YÖNETİM PANELİ ---
    elif choice == "⚙️ Yönetim Paneli":
        st.header("⚙️ Kurumsal Sistem Ayarları")
        t1, t2, t3 = st.tabs(["👥 Personel Yönetimi", "📂 Kategori Sistemi", "📈 Aktivite Dashboard"])
        
        with t1:
            st.subheader("Aktif Personel Listesi")
            conn = get_db_connection()
            st.dataframe(pd.read_sql_query("SELECT ad_soyad, birim, role, username FROM kullanicilar", conn), use_container_width=True)
            with st.expander("➕ Yeni Personel Tanımla"):
                n_ad = st.text_input("Tam Ad Soyad", placeholder="Örn: Nurettin Özcan")
                n_un = st.text_input("Kullanıcı Adı", placeholder="nurettin.ozcan")
                n_ps = st.text_input("Şifre", type='password')
                c_col1, c_col2 = st.columns(2)
                with c_col1:
                    n_rol = st.selectbox("Yetki", ["Personel", "Koordinatör", "Yönetici", "Admin"])
                with c_col2:
                    n_birim = st.text_input("Birim", value="Genel")
                
                st.divider()
                # v77: Kasa Entegrasyonu
                n_kasa_ac = st.checkbox("🏦 Bu kullanıcı için otomatik kasa açılışı yapılsın mı?", value=True)
                if n_kasa_ac:
                    n_kasa_ad = st.text_input("Açılacak Kasa İsmi", value=f"Kasa {n_ad}")
                
                if st.button("KAYDI TAMAMLA VE SİSTEME EKLE", use_container_width=True):
                    if n_un and n_ps and n_ad:
                        hashed_pw = hashlib.sha256(n_ps.encode()).hexdigest()
                        conn = get_db_connection()
                        # Kullanıcıyı Ekle
                        conn.execute("INSERT OR IGNORE INTO kullanicilar (username, password, role, ad_soyad, birim) VALUES (?,?,?,?,?)", 
                                     (n_un, hashed_pw, n_rol, n_ad, n_birim))
                        
                        # Eğer Kasa Seçiliyse Kasayı da Ekle
                        if n_kasa_ac:
                            conn.execute("INSERT OR IGNORE INTO kasalar (kasa_adi, owner_username, bakiye) VALUES (?,?,?)",
                                         (n_kasa_ad, n_un, 0.0))
                            db_log("Yeni Kasa Açıldı", st.session_state['u_name'], f"{n_kasa_ad} ({n_un})")
                        
                        conn.commit()
                        conn.close()
                        db_log("Yeni Personel Eklendi", st.session_state['u_name'], f"{n_ad} ({n_un})")
                        st.success(f"✅ {n_ad} sisteme başarıyla eklendi!")
                        if n_kasa_ac: st.info(f"🏦 {n_kasa_ad} aktif edildi.")
                        st.rerun()
                    else:
                        st.error("Lütfen tüm alanları doldurun!")
            conn.close()
            
        with t2:
            st.subheader("Kurumsal Arşiv Kategorileri")
            conn = get_db_connection()
            n_kat = st.text_input("Yeni Kategori Adı")
            if st.button("Kategori Ekle"):
                conn.execute("INSERT OR IGNORE INTO kategoriler VALUES (?)", (n_kat,))
                conn.commit(); st.rerun()
            st.table(pd.read_sql_query("SELECT * FROM kategoriler", conn))
            conn.close()

        with t3:
            st.subheader("📊 Sistem Aktivite Günlüğü")
            conn = get_db_connection()
            df_logs = pd.read_sql_query("SELECT * FROM sistem_loglari ORDER BY tarih DESC LIMIT 100", conn)
            st.dataframe(df_logs, use_container_width=True)
            
            # --- Feature 3: Gelişmiş Kurumsal Finansal Dashboard (v79) ---
            st.divider()
            st.subheader("🏢 Kurumsal Kasa Analitiği (v79)")
            
            df_masraflar = pd.read_sql_query("SELECT * FROM masraflar", conn).fillna(0)
            df_kasalar = pd.read_sql_query("SELECT * FROM kasalar", conn).fillna(0)
            
            if not df_kasalar.empty:
                # 2'li grid yapısı
                cols = st.columns(2)
                for i, (_, k_row) in enumerate(df_kasalar.iterrows()):
                    k_name = k_row['kasa_adi']
                    with cols[i % 2]:
                        st.markdown(f"""
                        <div class='kasa-card'>
                            <div class='kasa-card-header'>🏦 {k_name}</div>
                        """, unsafe_allow_html=True)
                        
                        # Son para yatırma tarihini bul
                        last_log = conn.execute("SELECT tarih FROM sistem_loglari WHERE islem='Kasa Girişi' AND detay LIKE ? ORDER BY tarih DESC LIMIT 1", 
                                               (f"%-> {k_name}",)).fetchone()
                        last_date = last_log[0] if last_log else "İşlem Yok"
                        
                        # Kasaya özel harcamalar
                        k_masraf = df_masraflar[df_masraflar['kasa_adi'] == k_name]
                        
                        m1, m2 = st.columns([1, 1.2])
                        with m1:
                            st.metric("Güncel Bakiye", f"{k_row['bakiye']:,.2f} TL")
                            st.markdown(f"<div class='kasa-card-info'>🕒 Son Giriş: {last_date}</div>", unsafe_allow_html=True)
                            st.markdown(f"<div class='kasa-card-info'>📊 Toplam Fiş: {len(k_masraf)} Adet</div>", unsafe_allow_html=True)
                        
                        with m2:
                            if not k_masraf.empty:
                                # v85: Narwhals Hatası için Plotly Graph Objects (GO) Geçişi
                                try:
                                    k_plot_df = k_masraf[['tutar', 'kategori']].copy()
                                    k_plot_df['tutar'] = pd.to_numeric(k_plot_df['tutar'], errors='coerce').fillna(0)
                                    k_plot_summary = k_plot_df.groupby('kategori')['tutar'].sum().reset_index()
                                    
                                    if not k_plot_summary.empty and k_plot_summary['tutar'].sum() > 0:
                                        fig_k = go.Figure(data=[go.Pie(
                                            labels=k_plot_summary['kategori'],
                                            values=k_plot_summary['tutar'],
                                            hole=.6,
                                            marker=dict(colors=px.colors.sequential.Tealgrn),
                                            textinfo='none' # İçeride metin olmasın, küçük alan
                                        )])
                                        fig_k.update_layout(
                                            showlegend=False, height=150, margin=dict(t=0, b=0, l=0, r=0),
                                            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                            font=dict(color="white")
                                        )
                                        st.plotly_chart(fig_k, use_container_width=True, config={'displayModeBar': False})
                                    else:
                                        st.caption("Grafik için veri yetersiz.")
                                except Exception as pie_err:
                                    st.error(f"GO Hatası: {pie_err}")
                            else:
                                st.caption("Henüz harcama verisi yok.")
                                
                        st.markdown("</div>", unsafe_allow_html=True)
            
            if not df_masraflar.empty:
                st.divider()
                st.subheader("💰 Genel Harcama Analitiği")
                # 3 Kolonlu Metrikler
                m1, m2, m3 = st.columns(3)
                with m1:
                    total_spent = df_masraflar['tutar'].sum()
                    st.metric("Toplam Harcama", f"{total_spent:,.2f} TL")
                with m2:
                    avg_spent = df_masraflar['tutar'].mean()
                    st.metric("Ortalama Fiş", f"{avg_spent:,.2f} TL")
                with m3:
                    count_spent = len(df_masraflar)
                    st.metric("Toplam Fiş Adedi", count_spent)
                
                st.divider()
                
                # Grafik Alanı (v84: Plotly 6+ & Python 3.14 Fix)
                g1, g2 = st.columns(2)
                with g1:
                    st.markdown("##### 🍰 Kategori Dağılımı")
                    try:
                        k_dist = df_masraflar[['tutar', 'kategori']].copy()
                        k_dist['tutar'] = pd.to_numeric(k_dist['tutar'], errors='coerce').fillna(0)
                        k_dist_summary = k_dist.groupby('kategori')['tutar'].sum().reset_index()
                        
                        fig_pie = go.Figure(data=[go.Pie(
                            labels=k_dist_summary['kategori'],
                            values=k_dist_summary['tutar'],
                            hole=0.4,
                            marker=dict(colors=px.colors.sequential.RdBu)
                        )])
                        fig_pie.update_layout(
                            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            font=dict(color="white"),
                            legend=dict(font=dict(color="white"))
                        )
                        st.plotly_chart(fig_pie, use_container_width=True)
                    except Exception as e:
                        st.error(f"Genel Grafik Hatası: {e}")

                with g2:
                    st.markdown("##### 📈 Aylık Harcama Trendi")
                    try:
                        trend_df = df_masraflar[['harcama_tarihi', 'tutar']].copy()
                        trend_df['harcama_tarihi'] = pd.to_datetime(trend_df['harcama_tarihi'])
                        trend_df['ay_yil'] = trend_df['harcama_tarihi'].dt.strftime('%Y-%m')
                        trend_df['tutar'] = pd.to_numeric(trend_df['tutar'], errors='coerce').fillna(0)
                        
                        aylik_harcama = trend_df.groupby('ay_yil')['tutar'].sum().reset_index().sort_values('ay_yil')
                        
                        if not aylik_harcama.empty:
                            fig_line = go.Figure(data=go.Scatter(
                                x=aylik_harcama['ay_yil'],
                                y=aylik_harcama['tutar'],
                                mode='lines+markers',
                                line=dict(color='#22D3EE', width=3),
                                marker=dict(size=8)
                            ))
                            fig_line.update_layout(
                                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                yaxis_title="TL", xaxis_title="Ay",
                                font=dict(color="white"),
                                xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)')
                            )
                            st.plotly_chart(fig_line, use_container_width=True)
                        else:
                            st.caption("Trend verisi bulunamadı.")
                    except Exception as e:
                        st.error(f"Trend GO Hatası: {e}")
            else:
                st.info("Henüz grafik oluşturulacak kadar masraf verisi bulunmuyor.")
            
            conn.close()
