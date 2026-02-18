import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network
from pathlib import Path
import os
import boto3
from io import BytesIO

# =====================
# MINIO CONFIG
# =====================
# Jika di Docker, gunakan nama service 'minio'. Jika lokal, gunakan 'localhost'
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minio")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minio123")

s3_client = boto3.client(
    's3',
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    region_name='us-east-1'
)

@st.cache_data
def load_data_from_minio(bucket_name, object_name):
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=object_name)
        content = response['Body'].read()
        if object_name.endswith('.csv'):
            return pd.read_csv(BytesIO(content), sep=";")
        else:
            return pd.read_excel(BytesIO(content))
    except Exception as e:
        st.error(f"Gagal mengambil data dari MinIO: {e}")
        return pd.DataFrame()

# Modifikasi fungsi load_data yang lama agar tetap fleksibel
@st.cache_data
def load_data_local(uploaded_file=None, sep=";"):
    if uploaded_file is not None:
        file_name = uploaded_file.name
        if file_name.endswith('.csv'):
            try:
                # Coba UTF-8 dulu (Standar)
                df = pd.read_csv(uploaded_file, sep=sep, encoding='utf-8')
            except UnicodeDecodeError:
                # Jika gagal, coba encoding Windows/Excel
                # 'ISO-8859-1' atau 'cp1252' biasanya berhasil untuk file dari Excel
                uploaded_file.seek(0) # Reset pointer file ke awal
                df = pd.read_csv(uploaded_file, sep=sep, encoding='ISO-8859-1')
        elif file_name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(uploaded_file)
        else:
            st.error("Format file tidak didukung!")
            return pd.DataFrame()
    else:
        base_dir = Path(__file__).resolve().parent
        data_path_csv = base_dir / "dataset" / "data.csv"
        data_path_xlsx = base_dir / "dataset" / "data.xlsx"

        if data_path_csv.exists():
            df = pd.read_csv(data_path_csv, sep=";")
        elif data_path_xlsx.exists():
            df = pd.read_excel(data_path_xlsx)
        else:
            return pd.DataFrame()


    if not df.empty:
        df["MUTASI"] = df["MUTASI"].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)
        df["TGL/TRANS"] = pd.to_datetime(df["TGL/TRANS"], dayfirst=True, errors="coerce")
        df["PEMILIK REKENING"] = df["PEMILIK REKENING"].fillna("UNKNOWN").astype(str)
        df["NAMA LAWAN"] = df["NAMA LAWAN"].fillna("UNKNOWN").astype(str)
    return df

def clean_financial_data(df):
    if df.empty: return df
    # Logika pembersihan Anda
    df["MUTASI"] = df["MUTASI"].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)
    df["TGL/TRANS"] = pd.to_datetime(df["TGL/TRANS"], dayfirst=True, errors="coerce")
    df["PEMILIK REKENING"] = df["PEMILIK REKENING"].fillna("UNKNOWN").astype(str)
    df["NAMA LAWAN"] = df["NAMA LAWAN"].fillna("UNKNOWN").astype(str)
    return df


# =====================
# CONFIG & SETUP
# =====================
st.set_page_config(layout="wide", page_title="Financial Flow Network")

def format_miliar(val):
    if abs(val) >= 1_000_000_000:
        return f"{val / 1_000_000_000:.2f} Miliar"
    elif abs(val) >= 1_000_000:
        return f"{val / 1_000_000:.2f} Juta"
    return f"{val:,.0f}"
    

st.title("💸 Financial Flow Network (Live Interaktif)")
# st.info(f"Status Visualisasi: **{layout_type}** | Gravitasi: **{central_gravity}** | Spring: **{spring_length}**")

# SIDEBAR: DATA SOURCE
st.sidebar.header("📁 Data Source")
source_type = st.sidebar.radio("Pilih Sumber Data", ["Upload Manual", "MinIO Storage"])

df = pd.DataFrame()

if source_type == "Upload Manual":
    uploaded_file = st.sidebar.file_uploader("Upload CSV atau Excel", type=["csv", "xlsx", "xls"])
    sep = ";"
    if uploaded_file and uploaded_file.name.endswith('.csv'):
        sep = st.sidebar.selectbox("Separator CSV", [";", ",", "|"], index=0)
    df = load_data_local(uploaded_file, sep=sep) # Gunakan logika fungsi lama Anda
    df = clean_financial_data(df)

else:
    bucket_input = st.sidebar.text_input("Bucket Name", value="my-bucket")
    file_input = st.sidebar.text_input("File Path (Object Name)", value="dataset/data.csv")
    if st.sidebar.button("Load dari MinIO"):
        df = load_data_from_minio(bucket_input, file_input)
        df = clean_financial_data(df)
    else:
        st.info("Masukkan detail bucket dan klik Load.")
        st.stop()

# df = load_data(uploaded_file, sep=separator)

if df.empty:
    st.warning("⚠️ Dataset tidak ditemukan.")
    st.stop()

# =====================
# SIDEBAR: FILTERS
# =====================

all_entities = sorted(list(set(df["PEMILIK REKENING"].unique()) | set(df["NAMA LAWAN"].unique())))
search_id = st.sidebar.selectbox("Pilih Account ID", [""] + all_entities)
min_value = st.sidebar.number_input("Minimum Transaction Value", min_value=0, value=10_000_000)

# 1. FILTER DATA (Sesuai input user)
df_filtered = df[df["MUTASI"] >= min_value].copy()
if search_id:
    df_filtered = df_filtered[(df_filtered["PEMILIK REKENING"] == search_id) | (df_filtered["NAMA LAWAN"] == search_id)]

# =====================
# 2. TARO DI SINI (AGREGASI)
# =====================
df_grouped = df_filtered.groupby(["PEMILIK REKENING", "NAMA LAWAN"]).agg({
    "MUTASI": "sum",
    "TGL/TRANS": "count" 
}).reset_index()
df_grouped.rename(columns={"TGL/TRANS": "FREKUENSI"}, inplace=True)
# TAMBAHKAN BARIS INI:
# Ini penting untuk menentukan warna node (Biru untuk pengirim)
node_sums = df_grouped.groupby("PEMILIK REKENING")["MUTASI"].sum().to_dict()

# ==========================================
# 2. FILTER TARGET & PECAH TRANSAKSI
# ==========================================
st.sidebar.header("🔍 Focus Analysis")
selected_target = "Semua"
break_down = False

if search_id:
    st.sidebar.markdown("---")
    # Ambil daftar lawan transaksi khusus untuk ID yang dicari
    potential_targets = sorted(list(set(
        df_grouped[df_grouped["PEMILIK REKENING"] == search_id]["NAMA LAWAN"].unique()
    ) | set(
        df_grouped[df_grouped["NAMA LAWAN"] == search_id]["PEMILIK REKENING"].unique()
    )))
    
    selected_target = st.sidebar.selectbox("Filter Lawan Transaksi Specific", ["Semua"] + potential_targets)
    break_down = st.sidebar.checkbox("Pecah Transaksi (Tampilkan Detail)", value=False)

# --- LOGIKA PENENTUAN DATA YANG DIGAMBAR (df_plot) ---
if search_id:
    if selected_target != "Semua":
        if break_down:
            # MODE PECAH: Ambil data mentah per baris dari df_filtered
            df_plot = df_filtered[
                ((df_filtered["PEMILIK REKENING"] == search_id) & (df_filtered["NAMA LAWAN"] == selected_target)) |
                ((df_filtered["PEMILIK REKENING"] == selected_target) & (df_filtered["NAMA LAWAN"] == search_id))
            ].copy()
            df_plot["FREKUENSI"] = 1 # Set 1 karena sudah dipecah per baris
        else:
            # MODE FILTER TARGET (Agregasi): Ambil dari df_grouped
            df_plot = df_grouped[
                ((df_grouped["PEMILIK REKENING"] == search_id) & (df_grouped["NAMA LAWAN"] == selected_target)) |
                ((df_grouped["PEMILIK REKENING"] == selected_target) & (df_grouped["NAMA LAWAN"] == search_id))
            ]
    else:
        # Tampilkan semua lawan transaksi untuk Account ID tersebut
        df_plot = df_grouped[(df_grouped["PEMILIK REKENING"] == search_id) | (df_grouped["NAMA LAWAN"] == search_id)]
else:
    # Jika tidak ada yang dicari, tampilkan semua (Global View)
    df_plot = df_grouped

# =====================
# SIDEBAR: PHYSICS (RESPONSIVE)
# =====================
st.sidebar.header("🎨 Visual Layout")
layout_type = st.sidebar.selectbox("Jenis Visual", ["Force Directed", "Hierarchical (Top-Down)", "Hierarchical (Left-Right)"])

st.sidebar.subheader("🧲 Physics Configuration")
physics_enabled = st.sidebar.checkbox("Enable Physics", value=True)
central_gravity = st.sidebar.slider("Central Gravity", 0.0, 5.0, 0.5, 0.1)
spring_length = st.sidebar.slider("Spring Length", 50, 1000, 250, 10)
node_distance = st.sidebar.slider("Node Distance", 50, 1000, 200, 10)

# =====================
# BUILD PYVIS
# =====================
# Key unik berdasarkan konfigurasi untuk memaksa refresh komponen
net_id = f"graph_{layout_type}_{physics_enabled}_{central_gravity}_{spring_length}_{node_distance}"

# net = Network(height="1000px", width="100%", bgcolor="#0f172a", font_color="white", directed=True)
net = Network(height="1000px", width="100%", bgcolor="#ffffff", font_color="#333333", directed=True)

if "Hierarchical" in layout_type:
    direction = "UD" if "Top-Down" in layout_type else "LR"
    net.set_options(f"""
    {{
      "edges": {{
        "font": {{ "align": "top", "size": 12, "strokeWidth": 3, "strokeColor": "#0f172a" }},
        "smooth": {{ "enabled": true, "type": "curvedCW", "roundness": 0.15 }}
      }},
      "layout": {{
        "hierarchical": {{
          "enabled": true,
          "direction": "{direction}",
          "sortMethod": "hubsize",
          "levelSeparation": 450,
          "nodeSpacing": 400
        }}
      }},
      "physics": {{
        "enabled": true,
        "hierarchicalRepulsion": {{ "nodeDistance": 400, "centralGravity": 0.0 }},
        "solver": "hierarchicalRepulsion"
      }}
    }}
    """)
else:
    net.set_options(f"""
    {{
      "edges": {{
        "font": {{
          "align": "top",
          "size": 11,
          "strokeWidth": 3,
          "strokeColor": "#0f172a"
        }},
        "smooth": {{
          "enabled": true,
          "type": "curvedCW",
          "roundness": 0.2
        }}
      }},
      "physics": {{
        "enabled": {str(physics_enabled).lower()},
        "forceAtlas2Based": {{
          "gravitationalConstant": -100,
          "centralGravity": 0.01,
          "springLength": {spring_length},
          "springConstant": 0.08
        }},
        "solver": "forceAtlas2Based"
      }}
    }}
    """)
    
added_nodes = set()

# Gunakan df_grouped hasil agregasi
for i, (_, row) in enumerate(df_plot.iterrows()):
    src, tgt = str(row["PEMILIK REKENING"]), str(row["NAMA LAWAN"])
    total_val = row["MUTASI"]  # Kita gunakan nama total_val agar jelas ini hasil jumlah
    freq = row.get("FREKUENSI", 1)
    
    # 1. Tambahkan/Cek Nodes
    for nid in [src, tgt]:
        if nid not in added_nodes:
            is_focus = (nid == search_id)
            # Logika warna: Biru jika dia pengirim (ada di node_sums), Hijau jika penerima murni
            net.add_node(
                nid, 
                label=nid, 
                color="#dc2626" if is_focus else ("#2563eb" if nid in node_sums else "#16a34a"),
                size=30 if is_focus else 15,
                shape="dot",
                font={'color': '#333333', 'size': 14, 'strokeWidth': 2, 'strokeColor': '#ffffff'},
                title=f"Entity: {nid}"
            )
            added_nodes.add(nid)

    # 2. Tambahkan Edge (Gunakan total_val untuk value)
    label_text = f"{format_miliar(total_val)}"
    if not break_down and freq > 1:
        label_text += f" | {freq}x transaksi"
    
    # Jika mode pecah, berikan roundness yang berbeda untuk setiap garis agar tidak tumpang tindih
    curve_type = "curvedCW" if src <= tgt else "curvedCCW"


    base_roundness = 0.15
    if break_down:
        # Menambah lengkungan setiap garis berdasarkan urutan transaksi
        edge_roundness = base_roundness + (i * 0.2) 
    else:
        edge_roundness = base_roundness
    
    # Menentukan warna garis berdasarkan arah (Logika yang Anda minta sebelumnya)
    if search_id:
        if src == search_id: edge_color = "#FF3366" 
        elif tgt == search_id: edge_color = "#22FF88"
        else: edge_color = "44CCFF"
    else:
        edge_color = "rgba(200, 200, 200, 0.5)"

    # Perhatikan: value=total_val (Bukan value=val)
    net.add_edge(
        src, tgt, 
        value=total_val, 
        label=label_text, 
        color=edge_color,
        width=2 if break_down else max(2, min(total_val / 100_000_000, 15)),
        arrows="to",
        font={'size': 10, 'color': '#333333', 'strokeWidth': 2, 'strokeColor': '#ffffff'}, # Label putih pinggirannya agar terbaca
        smooth={'enabled': True, 'type': curve_type, 'roundness': edge_roundness}
    )

# SAVE AND RENDER
path = "link_analysis_live.html"
net.save_graph(path)

# =====================
# RENDER DENGAN CONTAINER (SOLUSI FIX)
# =====================
with open(path, 'r', encoding='utf-8') as f:
    html_data = f.read()
    
    # Gunakan container kosong untuk menampung komponen
    # Ini akan menggantikan visualisasi lama dengan yang baru setiap kali script rerun
    graph_container = st.container()
    with graph_container:
        components.html(html_data, height=1250)


