import streamlit as st
import pandas as pd
from streamlit_agraph import Node, Edge, Config, agraph

st.set_page_config(layout="wide")
st.title("💸 Financial Flow Network (Hierarchical)")

# ======================
# LOAD DATA
# ======================
df = pd.read_csv("dataset/data.csv", sep=";")

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

# ======================
# EDGES
# ======================
edges_raw = []

for _, r in df.iterrows():
    if r["JENIS TRANSAKSI"] in ["TRANSFER KELUAR", "PAYMENT"]:
        edges_raw.append({
            "source": make_node(r["BANK"], r["NO REK"]),
            "target": make_node(r["BANK LAWAN"], r["NO REK LAWAN"]),
            "value": parse_amount(r["MUTASI"])
        })

edge_df = pd.DataFrame(edges_raw)

# ======================
# NODE METRICS
# ======================
node_weight = (
    edge_df.groupby("source")["value"]
    .sum()
    .rename("size")
)

node_ids = pd.unique(edge_df[["source", "target"]].values.ravel())

node_df = pd.DataFrame({"id": node_ids})
node_df["label"] = node_df["id"]
node_df["size"] = node_df["id"].map(node_weight).fillna(1)
node_df["size"] = (node_df["size"] / node_df["size"].max()) * 30 + 10

node_df["color"] = node_df["id"].apply(
    lambda x: "#e45756" if x.startswith("CASH") else "#4c78a8"
)

# ======================
# STREAMLIT FILTER
# ======================
min_value = st.sidebar.number_input(
    "Minimum Transaction Value",
    value=10_000_000
)

edge_df = edge_df[edge_df["value"] >= min_value]

# ======================
# BUILD GRAPH
# ======================
nodes = [
    Node(
        id=row.id,
        label=row.label,
        size=int(row.size),
        color=row.color
    )
    for row in node_df.itertuples()
]

edges = [
    Edge(
        source=row.source,
        target=row.target,
        label=f"{row.value:,.0f}",
        width=max(1, row.value / edge_df["value"].max() * 5)
    )
    for row in edge_df.itertuples()
]

# ======================
# HIERARCHICAL CONFIG
# ======================
config = Config(
    width="100%",
    height=800,
    directed=True,
    physics=False,
    hierarchical=True,
    nodeHighlightBehavior=True,
    collapsible=True
)

agraph(nodes=nodes, edges=edges, config=config)
