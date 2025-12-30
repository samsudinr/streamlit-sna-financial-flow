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

st.sidebar.header("🏦 Bank Legend")

for bank, cfg in BANK_CFG.get("banks", {}).items():
    st.sidebar.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:8px;">
            <div style="
                width:14px;
                height:14px;
                background:{cfg.get('color', '#999')};
                border-radius:50%;
            "></div>
            <span>{bank.upper()}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

st.sidebar.markdown("---")

# st.sidebar.header("🔍 Focus Analysis")
# search_id = st.sidebar.text_input("Cari Account ID (Bank|Norek)", "").strip().upper()

# Tombol untuk reset pencarian
# if st.sidebar.button("Clear Search"):
#     search_id = ""

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

nodes = []
base_dir = Path(__file__).resolve().parent

node_ids = pd.unique(edge_summary[["source", "target"]].values.ravel())


# mutasi_out = edge_df.sort_values('date', ascending=False).groupby('source').apply(
#     lambda x: "".join([
#         f"<div>• {row['date'].strftime('%d/%m/%y')}: <span style='color:#e74c3c;'>-Rp{row['value']:,.0f}</span></div>" 
#         for _, row in x.head(5).iterrows()
#     ])
# ).to_dict()

# # 2. Rangkuman Mutasi Masuk (Target)
# mutasi_in = edge_df.sort_values('date', ascending=False).groupby('target').apply(
#     lambda x: "".join([
#         f"<div>• {row['date'].strftime('%d/%m/%y')}: <span style='color:#27ae60;'>+Rp{row['value']:,.0f}</span></div>" 
#         for _, row in x.head(5).iterrows()
#     ])
# ).to_dict()

for nid in node_ids:
    style = node_style(nid)
    is_searched = search_id.lower() in nid.lower() if search_id else False

    short_label = nid.split("|")[0].upper()

    bank_name, norek = nid.split("|") if "|" in nid else (nid, "-")
    total_val = node_weight.get(nid, 0)

    # detail_in = mutasi_in.get(nid, "<i>Tidak ada mutasi masuk</i>")
    # detail_out = mutasi_out.get(nid, "<i>Tidak ada mutasi keluar</i>")

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
    }

    if node_image:
        node_kwargs["image"] = node_image
        node_kwargs["shape"] = "circularImage"
    else:
        node_kwargs["shape"] = "dot"
    
    nodes.append(Node(**node_kwargs))

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
    # label = (
    #     f"{row.date.strftime('%d/%m/%Y')}\nRp{row.value:,.0f}"
    #     for row in [row] if pd.notna(row.date) else [row] # Logika label Anda
    # )
    edges.append(
        Edge(
            source=row.source,
            target=row.target,
            label=label,
            # color=style_src.get("color", "#999999"),
            # color=node_style(row.source).get("color", "#999999"),
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
physics_enabled = True
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
                "nodeSpacing": 200,
                "treeSpacing": 200,
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
                "type": "curvedCW",
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

# agraph(nodes=nodes, edges=edges, config=config)
selected_node_id = agraph(nodes=nodes, edges=edges, config=config)

# 2. Logika Menampilkan Detail di Sidebar atau Kolom Terpisah
# -----------------------------------------------------
if selected_node_id:
    # Parsing ID (Contoh: BCA|123456)
    bank_name, norek = selected_node_id.split("|") if "|" in selected_node_id else (selected_node_id, "-")
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("📋 Account Properties")
    
    # Menampilkan Detail dengan format rapi (mirip gambar referensi Anda)
    with st.sidebar.container():
        st.write(f"**Institusi:** {bank_name}")
        st.write(f"**No. Rekening:** {norek}")
        
        # Ambil total mutasi dari data yang sudah dihitung sebelumnya
        total_val = node_weight.get(selected_node_id, 0)
        st.write(f"**Total Mutasi:** Rp{total_val:,.0f}")
        
        # Tampilkan Uraian Mutasi dalam Expander
        with st.sidebar.expander("🔴 Mutasi Keluar (Recent 5)", expanded=True):
            # Ambil dari dictionary mutasi_out yang kita buat sebelumnya
            # Kita bersihkan tag HTML-nya karena di st.write tidak perlu
            rincian_out = edge_df[edge_df['source'] == selected_node_id].head(5)
            for _, row in rincian_out.iterrows():
                st.caption(f"• {row['date'].strftime('%d/%m/%y')}: Rp{row['value']:,.0f}")

        with st.sidebar.expander("🟢 Mutasi Masuk (Recent 5)", expanded=True):
            rincian_in = edge_df[edge_df['target'] == selected_node_id].head(5)
            for _, row in rincian_in.iterrows():
                st.caption(f"• {row['date'].strftime('%d/%m/%y')}: Rp{row['value']:,.0f}")
else:
    st.sidebar.info("💡 Klik pada salah satu Node untuk melihat rincian mutasi.")
