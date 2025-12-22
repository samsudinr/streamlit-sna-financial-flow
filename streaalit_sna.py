import streamlit as st
import pandas as pd
from st_link_analysis import st_link_analysis
from streamlit_agraph import Node, Edge, Config

st.set_page_config(layout="wide")

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
# LINKS
# ======================
links = []

for _, r in df.iterrows():
    if r["JENIS TRANSAKSI"] in ["TRANSFER KELUAR", "PAYMENT"]:
        links.append({
            "source": make_node(r["BANK"], r["NO REK"]),
            "target": make_node(r["BANK LAWAN"], r["NO REK LAWAN"]),
            "value": parse_amount(r["MUTASI"])
        })

link_df = pd.DataFrame(links)

# ======================
# NODES
# ======================
nodes = pd.unique(link_df[["source", "target"]].values.ravel())

node_df = pd.DataFrame(nodes, columns=["id"])
node_df["label"] = node_df["id"]
node_df["group"] = node_df["id"].apply(
    lambda x: "cash" if x.startswith("CASH") else "account"
)

nodes = [
    Node(
        id=row["id"],
        label=row["label"],
        size=int(row["size"]),
        color=row["color"]
    )
    for _, row in node_df.iterrows()
]


# ======================
# FILTER
# ======================
min_value = st.sidebar.number_input(
    "Minimum Transaction",
    value=10_000_000
)

link_df = link_df[link_df["value"] >= min_value]
edges = [
    Edge(
        source=row["from"],
        target=row["to"],
        label=f"{row['weight']:,.0f}",
        width=max(1, row["weight"] / edge_df["weight"].max() * 5)
    )
    for _, row in edge_df.iterrows()
]
st.set_page_config(layout="wide")
st.title("Financial Flow Network (Hierarchical)")

agraph(
    nodes=nodes,
    edges=edges,
    config=config
)

# ======================
# GRAPH (HIERARCHY)
# ======================
# st_link_analysis(node_df, link_df)
config = Config(
    width="100%",
    height=800,
    directed=True,
    physics=False,               # ⬅️ MATIKAN FORCE
    hierarchical=True,           # ⬅️ MODE HIERARKI
    nodeHighlightBehavior=True,
    highlightColor="#F7A7A6",
    collapsible=True
)

