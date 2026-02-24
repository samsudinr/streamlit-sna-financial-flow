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
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "admin123")

# =====================
# HELPER FUNCTIONS (MinIO)
# =====================
def upload_to_minio(file, bucket, name):
    try:
        s3_client.upload_fileobj(file, bucket, name)
        return True
    except Exception as e:
        st.error(f"Upload Error: {e}")
        return False

def get_minio_file_list(bucket):
    try:
        response = s3_client.list_objects_v2(Bucket=bucket)
        if 'Contents' in response:
            return [obj['Key'] for obj in response['Contents']]
        return []
    except Exception as e:
        print(f"Error listing files: {e}")
        return []

def format_miliar(val):
    """Fungsi untuk memformat angka ke label Juta/Miliar"""
    if abs(val) >= 1_000_000_000:
        return f"{val / 1_000_000_000:.2f} Miliar"
    elif abs(val) >= 1_000_000:
        return f"{val / 1_000_000:.2f} Juta"
    return f"{val:,.0f}"

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
        
        if object_name.lower().endswith('.csv'):
            try:
                # Coba utf-8 dulu, jika gagal gunakan latin1
                return pd.read_csv(BytesIO(content), sep=";", encoding='utf-8')
            except UnicodeDecodeError:
                return pd.read_csv(BytesIO(content), sep=";", encoding='ISO-8859-1')
        else:
            # Untuk .xlsx tidak ada urusan dengan encoding utf-8
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
# CONFIG & LAYOUT
# =====================
st.set_page_config(layout="wide", page_title="Financial Flow Network")

# SIDEBAR UTAMA
st.sidebar.title("🚀 Control Panel")
menu_utama = st.sidebar.selectbox("Pilih Menu", ["Analisis Network", "Folder Manager"])

# ==========================================
# MENU 1: MINIO MANAGER (LOGIN & UPLOAD)
# ==========================================
if menu_utama == "Folder Manager":
    st.title("📂 Folder Storage Manager")
    
# --- SECTION A: BUCKET MANAGEMENT ---
    st.header("🗄️ Folder Management")
    col1, col2 = st.columns(2)
    
    with col1:
        new_bucket = st.text_input("Nama Folder Baru")
        if st.button("➕ Create Folder"):
            if new_bucket:
                s3_client.create_bucket(Bucket=new_bucket.lower().replace(" ", "-"))
                st.success(f"Folder '{new_bucket}' dibuat!")
                st.rerun()

    with col2:
        # List semua bucket untuk opsi hapus
        buckets = [b['Name'] for b in s3_client.list_buckets()['Buckets']]
        bucket_to_delete = st.selectbox("Pilih Folder untuk Dihapus", ["---"] + buckets)
        if st.button("🗑️ Delete Folder") and bucket_to_delete != "---":
            try:
                s3_client.delete_bucket(Bucket=bucket_to_delete)
                st.warning(f"Folder '{bucket_to_delete}' dihapus!")
                st.rerun()
            except Exception as e:
                st.error("Pastikan bucket kosong sebelum dihapus!")

    st.divider()

    # --- SECTION B: FILE MANAGEMENT ---
    st.header("📄 File Management")
    target_bucket = st.selectbox("Pilih Bucket untuk Kelola File", buckets)
    
    # Fitur Upload
    with st.expander("📤 Upload File Baru"):
        up_file = st.file_uploader("Pilih CSV/Excel", type=["csv", "xlsx"])
        if up_file and st.button("🚀 Upload"):
            if upload_to_minio(up_file, target_bucket, up_file.name):
                st.success("Berhasil!")
                st.rerun()

    # List dan Delete File
    files = get_minio_file_list(target_bucket)
    if files:
        st.subheader(f"Daftar File di '{target_bucket}'")
        for f in files:
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.text(f"📄 {f}")
            # Tombol Download
            obj = s3_client.get_object(Bucket=target_bucket, Key=f)
            c2.download_button("Download", data=obj['Body'].read(), file_name=f, key=f"dl_{f}", use_container_width=True)
            # Tombol Delete
            if c3.button("🗑️ Hapus", key=f"del_{f}", use_container_width=True, help=f"Hapus permanen {f}"):
                s3_client.delete_object(Bucket=target_bucket, Key=f)
                st.warning(f"File {f} terhapus!")
                st.rerun()
    else:
        st.info("Folder ini kosong.")
    
    st.stop() # Berhenti agar menu Analisis tidak muncul di bawahnya


# =====================
# CONFIG & SETUP
# =====================    

st.title("💸 Financial Flow Network & Storage")

# Sidebar tetap untuk konfigurasi sumber data
st.sidebar.header("📁 Data Management")

# 1. FITUR BARU: CREATE BUCKET (DI AWAL)
with st.sidebar.expander("🆕 Create New Project", expanded=False):
    new_bucket_name = st.text_input("Nama Folder Data Storage Baru")
    if st.button("➕ Buat Folder"):
        if new_bucket_name:
            try:
                s3_client.create_bucket(Bucket=new_bucket_name.lower().replace(" ", "-"))
                st.success(f"Folder '{new_bucket_name}' berhasil dibuat!")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal membuat Folder: {e}")
        else:
            st.warning("Masukkan nama Folder!")

st.sidebar.divider()

# 2. DAFTAR BUCKET (NAVIGASI UTAMA)
st.sidebar.subheader("🗄️ Pilih Folder (Create folder baru jika ingin memisahkan data source)")
try:
    response = s3_client.list_buckets()
    all_buckets = [b['Name'] for b in response['Buckets']]
    
    # Pilih bucket (default ke 'data-sources')
    default_idx = all_buckets.index("data-sources") if "data-sources" in all_buckets else 0
    selected_bucket = st.sidebar.selectbox("Pilih Storage Unit", all_buckets, index=default_idx)
    
    # 3. UPLOAD FILE (KE BUCKET YANG DIPILIH)
    with st.sidebar.expander(f"📤 Upload ke Folder Default '{selected_bucket}'", expanded=False):
        up_file = st.file_uploader("Pilih CSV/Excel", type=["csv", "xlsx"])
        if up_file and st.button("🚀 Upload Sekarang"):
            if upload_to_minio(up_file, selected_bucket, up_file.name):
                st.success(f"Berhasil upload ke {selected_bucket}!")
                st.rerun()

    # 4. DAFTAR FILES (OTOMATIS)
    st.sidebar.subheader(f"📂 File di '{selected_bucket}'")
    file_list = get_minio_file_list(selected_bucket)

    if file_list:
        selected_file = st.sidebar.selectbox("Pilih file untuk dianalisis", file_list)
        
        if st.sidebar.button("📊 Proses Data Ini"):
            loaded_df = load_data_from_minio(selected_bucket, selected_file)
            if not loaded_df.empty:
                # Simpan ke session_state untuk mencegah NameError
                st.session_state['df'] = clean_financial_data(loaded_df)
                st.session_state['current_file'] = selected_file
                st.success(f"Data '{selected_file}' siap!")
            else:
                st.error("Isi file tidak terbaca.")
    else:
        st.sidebar.warning(f"Bucket '{selected_bucket}' masih kosong.")

except Exception as e:
    st.sidebar.error(f"Gagal memuat data MinIO: {e}")

# ==========================================
# BAGIAN VISUALISASI & ANALISIS
# ==========================================
# Pastikan visualisasi hanya berjalan jika 'df' sudah ada di session_state
if 'df' in st.session_state:
    df = st.session_state['df']
    st.info(f"📋 Menganalisis File: **{st.session_state['current_file']}**")

    # Contoh penggunaan data agar tidak NameError
    st.write("### Preview Data Terpilih")
    st.dataframe(df.head())

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
    
    # --- LANJUTKAN KODE SNA / NETWORK ANDA DI SINI ---
    # all_entities = sorted(list(set(df["PEMILIK REKENING"].unique()) | ...))
    # dst...
else:
    st.info("Silakan pilih bucket dan file dari sidebar, lalu klik 'Proses Data Ini'.")

def format_miliar(val):
    if abs(val) >= 1_000_000_000:
        return f"{val / 1_000_000_000:.2f} Miliar"
    elif abs(val) >= 1_000_000:
        return f"{val / 1_000_000:.2f} Juta"
    return f"{val:,.0f}"



# SAVE AND RENDER
# path = "link_analysis_live.html"
# net.save_graph(path)

# # =====================
# # RENDER DENGAN CONTAINER (SOLUSI FIX)
# # =====================
# with open(path, 'r', encoding='utf-8') as f:
#     html_data = f.read()
    
#     # Gunakan container kosong untuk menampung komponen
#     # Ini akan menggantikan visualisasi lama dengan yang baru setiap kali script rerun
#     graph_container = st.container()
#     with graph_container:
#         components.html(html_data, height=850)


# GANTI BAGIAN save_graph LAMA DENGAN INI:
try:
    # Jangan gunakan path fisik jika memungkinkan, gunakan temporary path
    tmp_path = "link_analysis_live.html"
    net.save_graph(tmp_path)
    
    with open(tmp_path, 'r', encoding='utf-8') as f:
        html_data = f.read()
    
    # Tampilkan menggunakan komponen streamlit
    components.html(html_data, height=800, scrolling=True)
except Exception as e:
    st.error(f"Gagal generate grafik: {e}")