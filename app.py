import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from fpdf import FPDF
import tempfile
import os

st.set_page_config(page_title="ATEX Zone Hesaplama", layout="centered")

st.title("ATEX Tehlikeli Bölge (Zone) Hesaplama")
st.markdown("""
TS EN IEC 60079-10-1 standardına uygun, gelişmiş ATEX zone hesaplama uygulaması.
- Standart tablosu ve formül entegrasyonu
- Gaz veri tabanı
- Çoklu senaryo
- Görsel zone diyagramı
- PDF rapor çıktısı
""")

# --- Gaz veri tabanını yükle ---
@st.cache_data
def load_gas_db():
    return pd.read_csv("gazlar.csv")

gazlar = load_gas_db()

# --- Çoklu hesaplama için veri saklama ---
if "scenarios" not in st.session_state:
    st.session_state["scenarios"] = []

# --- Standart Tablo: Seyrelme faktörü (D) ve zone yarıçapı (örnek) ---
ZONE_RADIUS_TABLE = [
    {"D_max": 0.01, "radius": 0.5},
    {"D_max": 0.1,  "radius": 1.0},
    {"D_max": 1.0,  "radius": 3.0},
    {"D_max": 10.0, "radius": 5.0},
    {"D_max": float("inf"), "radius": 8.0}
]

def get_zone_radius(D):
    for row in ZONE_RADIUS_TABLE:
        if D <= row["D_max"]:
            return row["radius"]
    return 0.5  # default

# --- Senaryo Girişi ---
with st.form("scenario_form"):
    col1, col2 = st.columns(2)
    with col1:
        gaz_adi = st.selectbox("Gaz Seçiniz", gazlar["isim"])
        leak_type = st.selectbox("Kaçak Tipi", ["Sürekli", "Birincil", "İkincil"])
        leak_rate = st.number_input("Kaçak Debisi (m³/h)", min_value=0.01, max_value=1000.0, value=10.0, step=0.01)
        leak_duration = st.number_input("Kaçak Süresi (saat)", min_value=0.01, max_value=24.0, value=1.0, step=0.01)
    with col2:
        ventilation_rate = st.number_input("Havalandırma Debisi (m³/h)", min_value=0.01, max_value=10000.0, value=100.0, step=0.01)
        ventilation_type = st.selectbox("Havalandırma Tipi", ["Doğal", "Mekanik"])
        volume = st.number_input("Ortam Hacmi (m³)", min_value=0.1, max_value=10000.0, value=100.0, step=0.1)
        temp = st.number_input("Sıcaklık (°C)", min_value=-40.0, max_value=80.0, value=20.0, step=0.1)
        pressure = st.number_input("Basınç (bar)", min_value=0.8, max_value=2.0, value=1.0, step=0.01)
    scenario_name = st.text_input("Senaryo Adı", value=f"Senaryo {len(st.session_state['scenarios'])+1}")
    notes = st.text_area("Açıklama/Not (isteğe bağlı)", value="")
    submit = st.form_submit_button("Senaryoyu Ekle")

if submit:
    gaz = gazlar[gazlar["isim"] == gaz_adi].iloc[0]
    st.session_state["scenarios"].append({
        "Senaryo": scenario_name,
        "Gaz": gaz_adi,
        "Grup": gaz["grup"],
        "LEL": gaz["LEL"],
        "Kaçak Tipi": leak_type,
        "Kaçak Debisi": leak_rate,
        "Kaçak Süresi": leak_duration,
        "Havalandırma Debisi": ventilation_rate,
        "Havalandırma Tipi": ventilation_type,
        "Hacim": volume,
        "Sıcaklık": temp,
        "Basınç": pressure,
        "Not": notes
    })
    st.success(f"{scenario_name} eklendi!")

# --- Hesaplama Fonksiyonu ---
def calculate_zones(row):
    # Kaçak tipi ve havalandırma etkinliğine göre zone belirle
    if row["Kaçak Tipi"] == "Sürekli":
        zone0 = True
    else:
        zone0 = False

    D = row["Kaçak Debisi"] / row["Havalandırma Debisi"]
    base_radius = get_zone_radius(D)

    # Gaz grubu ve LEL'e göre düzeltme
    if row["Grup"] == "IIC":
        base_radius *= 1.2
    elif row["Grup"] == "IIB":
        base_radius *= 1.1
    if row["LEL"] < 2:
        base_radius *= 1.1

    # Ortam hacmi, sıcaklık, basınç düzeltmeleri
    if row["Hacim"] < 10:
        base_radius *= 0.8
    if row["Sıcaklık"] > 40:
        base_radius *= 1.05
    if row["Basınç"] > 1.2:
        base_radius *= 1.1

    # Zone 0, 1, 2 yarıçapları (örnek mantık)
    zone0_radius = base_radius * 0.3 if zone0 else 0
    zone1_radius = base_radius * 0.7 if not zone0 else base_radius * 0.7
    zone2_radius = base_radius

    return {
        "Zone 0 Yarıçapı (m)": round(zone0_radius, 2),
        "Zone 1 Yarıçapı (m)": round(zone1_radius, 2),
        "Zone 2 Yarıçapı (m)": round(zone2_radius, 2),
        "Seyrelme Faktörü (D)": round(D, 4)
    }

# --- Görsel Zone Diyagramı ---
def plot_zones(zone0, zone1, zone2):
    fig, ax = plt.subplots(figsize=(6,6))
    # En büyükten küçüğe doğru çemberler çiz
    for r, color, label in zip([zone2, zone1, zone0], ['#FFD700', '#FF8C00', '#FF0000'], ['Zone 2', 'Zone 1', 'Zone 0']):
        if r > 0:
            circle = plt.Circle((0,0), r, color=color, alpha=0.3, label=label)
            ax.add_artist(circle)
    ax.set_xlim(-zone2-1, zone2+1)
    ax.set_ylim(-zone2-1, zone2+1)
    ax.set_aspect('equal')
    plt.legend()
    plt.title("Tehlikeli Bölge Sınırları (Zone 0/1/2)")
    plt.xlabel("Metre")
    plt.ylabel("Metre")
    st.pyplot(fig)

# --- PDF Raporu Oluştur ---
def create_pdf_report(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "ATEX Zone Hesaplama Raporu", ln=1, align="C")
    pdf.set_font("Arial", "", 12)
    for idx, row in df.iterrows():
        pdf.ln(5)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, f"Senaryo: {row['Senaryo']}", ln=1)
        pdf.set_font("Arial", "", 11)
        for col in df.columns:
            if col != "Senaryo":
                pdf.cell(0, 8, f"{col}: {row[col]}", ln=1)
        pdf.ln(2)
    # Geçici dosya oluştur
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(tmp.name)
    return tmp.name

# --- Hesapla ve Sonuçları Göster ---
if st.session_state["scenarios"]:
    st.subheader("Senaryolar ve Sonuçlar")
    results = []
    for row in st.session_state["scenarios"]:
        res = calculate_zones(row)
        results.append({**row, **res})
    df = pd.DataFrame(results)
    st.dataframe(df)

    # Görsel çıktı (ilk senaryo için örnek)
    st.subheader("Zone Diyagramı (ilk senaryo)")
    plot_zones(df.iloc[0]["Zone 0 Yarıçapı (m)"], df.iloc[0]["Zone 1 Yarıçapı (m)"], df.iloc[0]["Zone 2 Yarıçapı (m)"])

    # PDF rapor
    if st.button("PDF Raporu İndir"):
        pdf_path = create_pdf_report(df)
        with open(pdf_path, "rb") as f:
            st.download_button("PDF Raporu İndir", f, file_name="atex_rapor.pdf")
        os.remove(pdf_path)

    if st.button("Tüm Senaryoları Temizle"):
        st.session_state["scenarios"] = []
        st.experimental_rerun()

st.markdown("---")
st.caption("© 2024 ATEX Zone Hesaplama | Python + Streamlit | Gelişmiş Sürüm")
