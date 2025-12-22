import streamlit as st
import pandas as pd
from streamlit_agraph import Node, Edge, Config, agraph

# ======================
# PAGE
# ======================
st.set_page_config(layout="wide")
st.title("💸 Financial Flow Network (Hierarchical)")

# ======================
# LOAD DATA
# ======================
df = pd.read_csv("dataset/data.csv", sep=";")

df["TGL/TRANS"] = (
    df["TGL/TRANS"]
    .astype(str)
    .str.strip()
    .pipe(pd.to_datetime, format="%d/%m/%Y", errors="coerce")
)

# ======================
# NODE LOGIC
# ======================
def make_node(bank, norek):
    bank = str(bank).strip().upper()
    norek = str(norek).strip()
    if bank in ["", "-", "EMPTY", "NAN"] or norek in ["", "-", "EMPTY", "NAN"]:
        return "CASH|KAS_BESAR"
    return f"{bank}|{norek}"

def node_role(node_id):
    if node_id.startswith("CASH"):
        return "cash"
    if any(x in node_id for x in ["MANDIRI|3", "BNI|321", "BANK INI"]):
        return "hub"
    if any(x in node_id for x in ["EDC", "AFK", "GSM"]):
        return "merchant"
    return "normal"

def node_style(node_id):
    role = node_role(node_id)
    if role == "cash":
        return "#f2cf5b", 36
    if role == "hub":
        return "#e45756", 30
    if role == "merchant":
        return "#2f2f2f", 22
    return "#b279ff", 18

def parse_amount(x):
    if pd.isna(x):
        return 0
    return float(str(x).replace(".", "").replace(",", "."))

# ======================
# BUILD EDGES
# ======================
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

# ======================
# FILTER
# ======================
min_value = st.sidebar.number_input(
    "Minimum Transaction Value",
    value=10_000_000,
    step=1_000_000
)

edge_df = edge_df[edge_df["value"] >= min_value]

# ======================
# NODES
# ======================
node_ids = pd.unique(edge_df[["source", "target"]].values.ravel())

nodes = []
for node_id in node_ids:
    color, size = node_style(node_id)
    nodes.append(
        Node(
            id=node_id,
            label=node_id,
            size=size + 6,
            color=color,
            shape="dot",
            font={
                "size": 16,         # ⬅️ label lebih besar
                "face": "arial",
                "color": "#000000"
            }
        )
    )

# ======================
# EDGES
# ======================
max_value = edge_df["value"].max() or 1

edges = []
for r in edge_df.itertuples():
    label = (
        f"{r.date.strftime('%d/%m/%Y')}\nRp{r.value:,.0f}"
        if pd.notna(r.date)
        else f"Rp{r.value:,.0f}"
    )

    edges.append(
        Edge(
            source=r.source,
            target=r.target,
            label=label,
            width=max(2, r.value / max_value * 5)
        )
    )

# ======================
# GRAPH CONFIG
# ======================
config = Config(
    width="100%",
    height=850,
    directed=True,

    physics=False,
    hierarchical=True,

    physics_config={
        "barnesHut": {
            "gravitationalConstant": -1800,
            "centralGravity": 0.15,
            "springLength": 70,
            "springConstant": 0.05,
            "damping": 0.35
        }
    },

    nodes={
        "shape": "dot",
        "font": {
            "size": 14,
            "multi": True
        }
    },

    edges={
        "smooth": {
            "type": "dynamic"
        },
        "arrows": {
            "to": {"enabled": True, "scaleFactor": 1.1}
        }
    },

    interaction={
        "hover": True,
        "zoomView": True
    }
)



agraph(nodes=nodes, edges=edges, config=config)
