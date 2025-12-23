import streamlit as st
import pandas as pd
from streamlit_agraph import Node, Edge, Config, agraph
import yaml
from pathlib import Path

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(
    page_title="Financial Flow Network",
    layout="wide"
)

st.title("💸 Financial Flow Network (Hierarchical)")

# =====================================================
# LOAD BANK CONFIG (SAFE PATH)
# =====================================================
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

# =====================================================
# SIDEBAR LEGEND
# =====================================================
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

# =====================================================
# LOAD DATA
# =====================================================
@st.cache_data
def load_data():
    base_dir = Path(__file__).resolve().parent
    data_path = base_dir / "dataset" / "data.csv"

    if not data_path.exists():
        st.error(f"Dataset tidak ditemukan: {data_path}")
        st.stop()

    df = pd.read_csv(data_path, sep=";")
    df["TGL/TRANS"] = pd.to_datetime(
        df["TGL/TRANS"],
        format="%d/%m/%Y",
        errors="coerce"
    )
    return df

df = load_data()

# =====================================================
# HELPER FUNCTIONS
# =====================================================
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

# def node_style(node_id: str):
#     node_id = node_id.lower()
#     banks = BANK_CFG.get("banks", {})
#     default = BANK_CFG.get("default", {
#         "color": "#999999",
#         "shape": "dot",
#         "icon": None
#     })

#     for bank, style in banks.items():
#         if node_id.startswith(bank.lower()):
#             return style

#     return default
# def node_style(node_id: str):
#     node_id = node_id.upper() # Ubah ke upper untuk konsistensi
#     banks = BANK_CFG.get("banks", {})
    
#     # Cek setiap bank di config
#     for bank_name, style in banks.items():
#         if node_id.startswith(bank_name.upper()):
#             return style
            
#     return BANK_CFG.get("default", {"color": "#999999"})

def node_style(node_id: str):
    # node_id contohnya: "BCA|123456"
    bank_part = node_id.split("|")[0].upper() 
    banks = BANK_CFG.get("banks", {})
    
    for key, style in banks.items():
        if key.upper() == bank_part:
            return style
            
    return BANK_CFG.get("default", {"color": "#999999", "shape": "dot"})

# =====================================================
# BUILD EDGES
# =====================================================
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
edge_summary = edge_df.groupby(["source", "target"]).agg({
    "value": "sum",
    "date": "max"
}).reset_index()
# =====================================================
# SIDEBAR FILTER
# =====================================================
min_value = st.sidebar.number_input(
    "Minimum Transaction Value",
    min_value=0,
    value=10_000_000,
    step=1_000_000
)

edge_df = edge_df[edge_df["value"] >= min_value]

if edge_df.empty:
    st.warning("Tidak ada transaksi setelah filter")
    st.stop()

# =====================================================
# NODE METRICS
# =====================================================
node_weight = (
    edge_df.groupby("source")["value"]
    .sum()
    .rename("size")
)

node_ids = pd.unique(edge_df[["source", "target"]].values.ravel())

node_df = pd.DataFrame({"id": node_ids})
node_df["size"] = node_df["id"].map(node_weight).fillna(1)
node_df["size"] = (node_df["size"] / node_df["size"].max()) * 30 + 10

# =====================================================
# BUILD NODES
# =====================================================
# nodes = []

# for row in node_df.itertuples():
#     style = node_style(row.id)

#     nodes.append(
#         Node(
#             id=row.id,
#             label=row.id.split("|")[0].upper(),
#             title=row.id,
#             size=int(row.size),
#             color=style.get("color", "#999999"),
#             shape=style.get("shape", "dot"),
#             icon=style.get("icon")
#         )
#     )
nodes = []
# Ambil ID unik dari source & target di data yang sudah difilter
node_ids = pd.unique(edge_summary[["source", "target"]].values.ravel())

for nid in node_ids:
    style = node_style(nid)
    # Tampilkan label singkat saja (Nama Bank) agar tidak menutupi bulatan
    short_label = nid.split("|")[0].upper()
    
    nodes.append(
        Node(
            id=nid,
            label=short_label,
            title=nid, # Detail norek muncul saat kursor menempel (tooltip)
            size=25,   # Ukuran bulatan diperbesar agar terlihat
            color=style.get("color", "#999999"),
            shape="dot"
        )
    )
# =====================================================
# BUILD EDGES (VISUAL)
# =====================================================
max_value = edge_df["value"].max() or 1

# edges = []

# for row in edge_df.itertuples():
#     label = (
#         f"{row.date.strftime('%d-%m-%Y')}\nRp{row.value:,.0f}"
#         if pd.notna(row.date)
#         else f"Rp{row.value:,.0f}"
#     )
#     style_source = node_style(row.source)
#     edge_color = style_source.get("color", "#999999")
#     edges.append(
#         Edge(
#             source=row.source,
#             target=row.target,
#             label=label,
#             width=max(1, row.value / max_value * 5),
#             color=edge_color  # Tambahkan baris ini!
#         )
#     )
edges = []
max_val = edge_summary["value"].max() or 1

for row in edge_summary.itertuples():
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
            label=label,
            # Gunakan warna dari bank pengirim agar alur terlihat jelas
            color=style_src.get("color", "#999999"),
            width=max(2, (row.value / max_val) * 10),
            # Aktifkan panah di sini
            arrows="to" 
        )
    )
    # edges.append(
    #     Edge(
    #         source=row.source,
    #         target=row.target,
    #         label=label,
    #         width=max(1, row.value / max_value * 5)
    #     )
    # )

# =====================================================
# GRAPH CONFIG
# =====================================================
# config = Config(
#     width="100%",
#     height=800,
#     directed=True,
#     physics=True, # Aktifkan agar node saling menjauh (tidak menumpuk)
#     hierarchical=True, # Matikan ini jika datanya bukan pohon (tree)
#     nodeHighlightBehavior=True,
#     highlightColor="#F7A7A7",
#     collapsible=False,
#     # Pengaturan tambahan agar teks tidak menumpuk
#     physics_config={
#         "barnesHut": {
#             "gravitationalConstant": -3000,
#             "centralGravity": 0.3,
#             "springLength": 150
#         }
#     }
# )

config = Config(
    width="100%",
    height=800,
    directed=True,
    physics=True,         # Pastikan True
    hierarchical=True,   # Matikan Hierarchical agar node menyebar secara organik
    nodeHighlightBehavior=True,
    
    physics_config={
        "barnesHut": {
            "gravitationalConstant": -8000, # Nilai negatif lebih besar = dorongan antar node lebih kuat
            "centralGravity": 0.1,          # Nilai kecil = node tidak terlalu menumpuk di tengah
            "springLength": 300,            # Panjang garis penghubung diperbesar
            "springConstant": 0.04,
            "avoidOverlap": 1               # Memaksa node untuk tidak tumpuk tindih
        },
        "solver": "barnesHut"
    }
)
# =====================================================
# RENDER GRAPH
# =====================================================
agraph(nodes=nodes, edges=edges, config=config)
