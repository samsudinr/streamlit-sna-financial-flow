import streamlit as st
import pandas as pd
from streamlit_agraph import Node, Edge, Config, agraph
import yaml
from pathlib import Path
import base64


st.set_page_config(
    page_title="Financial Flow Network",
    layout="wide"
)

st.title("💸 Financial Flow Network (Hierarchical)")


@st.cache_data
def load_data(uploaded_file, sep=";"):
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file, sep=sep)
    else:
        base_dir = Path(__file__).resolve().parent
        data_path = base_dir / "dataset" / "data.csv"
        if not data_path.exists():
            return pd.DataFrame() 
        df = pd.read_csv(data_path, sep=";")

    # Pembersihan data (Cleaning)
    if not df.empty:
        df["TGL/TRANS"] = pd.to_datetime(
            df["TGL/TRANS"],
            format="%d/%m/%Y",
            errors="coerce"
        )
    return df

st.sidebar.header("📁 Data Source")

uploaded_file = st.sidebar.file_uploader("Upload CSV Transaksi", type=["csv"])
separator = st.sidebar.selectbox("Separator CSV", [";", ",", "|"], index=0)

df = load_data(uploaded_file, sep=separator)

@st.cache_resource
def load_bank_config():
    base_dir = Path(__file__).resolve().parent
    cfg_path = base_dir / "config" / "bank_nodes.yaml"

    if not cfg_path.exists():
        st.error(f"Config file tidak ditemukan: {cfg_path}")
        st.stop()

    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

BANK_CFG = load_bank_config()

def make_node(bank, norek):
    bank = str(bank).strip().upper()
    norek = str(norek).strip()

    if bank in ["", "-", "EMPTY", "NAN"] or norek in ["", "-", "EMPTY", "NAN"]:
        return "CASH|KAS_BESAR"

    return f"{bank}|{norek}"

def parse_amount(x):
    if pd.isna(x):
        return 0
    return float(str(x).replace(".", "").replace(",", "."))

def node_style(node_id: str):
    # node_id contohnya: "BCA|123456"
    bank_part = node_id.split("|")[0].upper() 
    banks = BANK_CFG.get("banks", {})
    
    for key, style in banks.items():
        if key.upper() == bank_part:
            return style
            
    return BANK_CFG.get("default", {"color": "#999999", "shape": "dot"})

edges_raw = []

for _, r in df.iterrows():
    if r["JENIS TRANSAKSI"] in ["TRANSFER KELUAR", "PAYMENT"]:
        edges_raw.append({
            "source": make_node(r["BANK"], r["NO REK"]),
            "target": make_node(r["BANK LAWAN"], r["NO REK LAWAN"]),
            "value": parse_amount(r["MUTASI"]),
            "date": r["TGL/TRANS"]
        })

edge_df = pd.DataFrame(edges_raw)

if edge_df.empty:
    st.warning("Tidak ada transaksi yang bisa divisualisasikan")
    st.stop()

min_value = st.sidebar.number_input(
    "Minimum Transaction Value",
    min_value=0,
    value=10_000_000,
    step=1_000_000
)

edge_df = edge_df[edge_df["value"] >= min_value]

# 2. Ganti text_input kamu dengan selectbox agar tidak ada typo
st.sidebar.header("🔍 Focus Analysis")
available_ids = sorted(pd.unique(edge_df[["source", "target"]].values.ravel()))

search_id = st.sidebar.selectbox(
    "Pilih atau Ketik Account ID", 
    options=[""] + available_ids,
    index=0,
    key="search_box"
)

if st.sidebar.button("Clear Search", key="btn_clear_search"):
    st.rerun() # Mengulang script agar selectbox balik ke awal
# ---------------------

# Lanjut ke logika filter pencarian (kode yang sudah kamu punya)
if search_id:
    # Timpa edge_df dengan hasil filter pencarian
    edge_df = edge_df[
        (edge_df["source"].str.contains(search_id, case=False, na=False, regex=False)) | 
        (edge_df["target"].str.contains(search_id, case=False, na=False, regex=False))
    ].copy()
    
    if edge_df.empty:
        st.sidebar.error(f"❌ ID '{search_id}' tidak ditemukan.")
    else:
        st.sidebar.success(f"✅ Menampilkan koneksi untuk: {search_id}")

def assign_levels_by_date(df):
    # Urutkan berdasarkan kolom 'date' (karena ini edge_df)
    levels = {}
    current_level = 0

    for _, row in df.sort_values("date").iterrows():
        if row["source"] not in levels:
            levels[row["source"]] = current_level
        if row["target"] not in levels:
            levels[row["target"]] = current_level + 1
        current_level += 1

    return levels

def assign_levels_lr_time(df):
    df = df.sort_values("date")
    levels = {}
    max_level = 4  # BATASI

    for _, r in df.iterrows():
        if r["source"] not in levels:
            levels[r["source"]] = 0
        if r["target"] not in levels:
            levels[r["target"]] = min(levels[r["source"]] + 1, max_level)

    return levels

def assign_levels_lr(df):
    sources = set(df["source"])
    targets = set(df["target"])

    roots = sources - targets
    sinks = targets - sources
    intermediates = sources & targets

    levels = {}

    for n in roots:
        levels[n] = 0
    for n in intermediates:
        levels[n] = 1
    for n in sinks:
        levels[n] = 2

    return levels

def assign_levels_topdown(df, root_nodes):
    from collections import deque

    levels = {}
    queue = deque()

    for r in root_nodes:
        levels[r] = 0
        queue.append(r)

    while queue:
        node = queue.popleft()
        for _, row in df[df["source"] == node].iterrows():
            tgt = row["target"]
            if tgt not in levels:
                levels[tgt] = levels[node] + 1
                queue.append(tgt)

    return levels


edge_summary = edge_df.groupby(["source", "target"]).agg({
    "value": "sum",
    "date": "max"
}).reset_index()

node_ids = pd.unique(edge_df[["source", "target"]].values.ravel())

node_weight = (
    edge_df.groupby("source")["value"]
    .sum()
    .rename("size")
)

node_df = pd.DataFrame({"id": node_ids})
node_df["size"] = node_df["id"].map(node_weight).fillna(1)
node_df["size"] = (node_df["size"] / node_df["size"].max()) * 30 + 10

def get_base64_image(image_path):
    import base64
    try:
        if image_path and Path(image_path).exists():
            with open(image_path, "rb") as img_file:
                return f"data:image/png;base64,{base64.b64encode(img_file.read()).decode()}"
    except:
        return None
    return None

max_value = edge_df["value"].max() or 1

edges = []
max_val = edge_summary["value"].max() or 1

for row in edge_summary.itertuples():
    bank_color = node_style(row.source).get("color", "#999999")
    style_src = node_style(row.source)
    label = (
        f"{row.date.strftime('%d/%m/%Y')}\nRp{row.value:,.0f}"
        if pd.notna(row.date)
        else f"Rp{row.value:,.0f}"
    )
    edges.append(
        Edge(
            source=row.source,
            target=row.target,
            label=f"Rp{row.value:,.0f}",
            title=f"Tanggal: {row.date.strftime('%d/%m/%Y')}",
            color={
                "color": "rgba(200, 200, 200, 0.2)", 
                "highlight": bank_color,
                "hover": bank_color,
                "inherit": False # Penting agar tidak mengikuti warna node secara otomatis
            },
            width=max(2, (row.value / max_val) * 10),
            arrows="to" ,
            smooth={"type": "curvedCW", "roundness": 0.4}
        )
    )

st.sidebar.header("🎨 Visual Layout")
layout_type = st.sidebar.selectbox(
    "Pilih Jenis Visual", 
    [
        "Hirarki (Top-Down)", 
        "Hirarki (Left-Right)", 
        "Jaring Bebas (Force Directed)",
        "Melingkar (Circular)",
        "Menyebar (Radial/Hub-Centric)"
    ]
)

# Inisialisasi variabel default
is_hierarchical = False
direction = "UD"
physics_enabled = False if "Hirarki" in layout_type else True
solver = "forceAtlas2Based" # Default solver
opts = {} # Wadah untuk setting spesifik

if "Hirarki" in layout_type:
    is_hierarchical = True
    direction = "UD" if "Top-Down" in layout_type else "LR"
    physics_enabled = False
    # Hirarki tidak butuh setting physics tambahan
elif "Melingkar" in layout_type:
    solver = "repulsion"
    opts = {
        "repulsion": {
            "centralGravity": 0.1,
            "nodeDistance": 1000, # Angka besar untuk memaksa bentuk cincin
        }
    }
elif "Menyebar" in layout_type:
    solver = "forceAtlas2Based"
    opts = {
        "forceAtlas2Based": {
            "centralGravity": 3.0, # Angka tinggi untuk menarik semua ke pusat
            "springLength": 100,
            "gravitationalConstant": -500,
            "avoidOverlap": 1
        }
    }
else: # Jaring Bebas (Force Directed)
    solver = "barnesHut"
    opts = {
        "barnesHut": {
            "gravitationalConstant": -8000,
            "centralGravity": 0.1,
            "springLength": 300,
            "avoidOverlap": 1
        }
    }

nodes = []
base_dir = Path(__file__).resolve().parent

node_ids = pd.unique(edge_summary[["source", "target"]].values.ravel())
# Panggil fungsi ini sebelum membuat objek Node
if layout_type == "Hirarki (Top-Down)":
    roots = set(edge_df["source"]) - set(edge_df["target"])
    node_levels = assign_levels_topdown(edge_df, roots)

elif layout_type == "Hirarki (Left-Right)":
    node_levels = assign_levels_lr(edge_df)

elif layout_type == "Timeline":
    node_levels = assign_levels_lr_time(edge_df)

else:
    node_levels = {}

for nid in node_ids:
    style = node_style(nid)
    is_searched = search_id.lower() in nid.lower() if search_id else False

    short_label = nid.split("|")[0].upper()

    bank_name, norek = nid.split("|") if "|" in nid else (nid, "-")
    total_val = node_weight.get(nid, 0)

    hover_info = (
        f"INSTITUSI: {bank_name}\n"
        f"NO. REKENING: {norek}\n"
        f"TOTAL MUTASI: Rp{total_val:,.0f}"
    )

    local_path = style.get("image_file")
    node_image = None
    if local_path:
        full_path = base_dir / local_path
        node_image = get_base64_image(full_path)

    node_kwargs = {
        "id": nid,
        "label": short_label,
        "title": hover_info,
        "size": 25,
        "borderWidth": 4 if is_searched else 1,
        "color": style.get("color", "#999999"),
        "shape": "circularImage" if node_image else "dot"
    }
    if is_hierarchical and nid in node_levels:
        node_kwargs["level"] = node_levels[nid]

    if node_image:
        node_kwargs["image"] = node_image
        node_kwargs["shape"] = "circularImage"
    else:
        node_kwargs["shape"] = "dot"
    
    nodes.append(Node(**node_kwargs))

config = Config(
    width="100%",
    height=800,
    directed=True,
    physics=physics_enabled,   
    hierarchical=is_hierarchical,
    nodeHighlightBehavior=True,
    # Hapus physics_config lama agar tidak membingungkan mesin vis.js
    extra_options={
        "layout": {
            "hierarchical": {
                "enabled": is_hierarchical,
                "direction": direction,
                "sortMethod": "directed",
                "nodeSpacing": 400,
                "treeSpacing": 250,
                "levelSeparation": 600,
                "blockShifting": True,
                "edgeMinimization": True,
                "parentCentralization": True
            }
        },
        "interaction": {
            "hover": True,
            "selectConnectedEdges": True,
            "navigationButtons": True
        },
        "edges": {
            "font": {
                "size": 12,
                "align": "top",
                "strokeWidth": 3,
                "strokeColor": "#ffffff"
            },
            "smooth": {
                "enabled": True,
                "type": "cubicBezier",
                "roundness": 0.5
            }
        },
        "physics": {
            "enabled": physics_enabled,
            "solver": solver, # Mengambil dari variabel di atas
            **opts,           # Memasukkan dictionary setting spesifik
            "stabilization": {"enabled": True, "iterations": 200}
        }
    }
)

if nodes:
    for n in nodes:
        # Tambahkan spasi yang berbeda untuk tiap arah agar data dianggap baru
        if direction == "LR":
            n.label = n.label + " "  # Tambah 1 spasi
        else:
            n.label = n.label.strip()

# Buat placeholder kosong
placeholder = st.empty()


selected_node_id = agraph(nodes=nodes, edges=edges, config=config)

if selected_node_id and isinstance(selected_node_id, str):

    bank_name, norek = selected_node_id.split("|")

    st.sidebar.markdown("---")
    st.sidebar.subheader("📋 Account Properties")

    total_val = node_weight.get(selected_node_id, 0)
    st.sidebar.write(f"**Institusi:** {bank_name}")
    st.sidebar.write(f"**No Rekening:** {norek}")
    st.sidebar.write(f"**Total Mutasi:** Rp{total_val:,.0f}")

    # =========================
    # BUAT TABEL MUTASI
    # =========================
    tx_df = edge_df[
        (edge_df["source"] == selected_node_id) |
        (edge_df["target"] == selected_node_id)
    ].copy()

    if tx_df.empty:
        st.sidebar.info("Tidak ada mutasi untuk akun ini.")
    else:
        # Tandai arah transaksi
        tx_df["Arah"] = tx_df.apply(
            lambda r: "KELUAR" if r["source"] == selected_node_id else "MASUK",
            axis=1
        )

        tx_df["Dari"] = tx_df["source"]
        tx_df["Ke"] = tx_df["target"]

        tx_df = (
            tx_df[["date", "Arah", "Dari", "Ke", "value"]]
            .sort_values("date", ascending=False)
            .rename(columns={
                "date": "Tanggal",
                "value": "Nominal"
            })
        )

        # Format kolom
        tx_df["Tanggal"] = tx_df["Tanggal"].dt.strftime("%d/%m/%Y")
        tx_df["Nominal"] = tx_df["Nominal"].apply(lambda x: f"Rp{x:,.0f}")

        st.sidebar.markdown("### 📑 Riwayat Mutasi")

        st.sidebar.dataframe(
            tx_df,
            use_container_width=True,
            height=300
        )

        # Optional: download CSV
        st.sidebar.download_button(
            "⬇️ Download CSV",
            tx_df.to_csv(index=False),
            file_name=f"mutasi_{bank_name}_{norek}.csv",
            mime="text/csv"
        )
