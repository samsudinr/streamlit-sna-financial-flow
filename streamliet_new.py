import streamlit as st
import pandas as pd
from streamlit_agraph import Node, Edge, Config, agraph
import yaml
from pathlib import Path
import base64
import random

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

def make_entity(name):
    name = str(name).strip().upper()

    if name in ["", "-", "EMPTY", "NAN"]:
        return "KAS BESAR"

    return name

def format_miliar(val):
    if abs(val) >= 1_000_000_000:
        return f"{val / 1_000_000_000:.2f} Miliar"
    elif abs(val) >= 1_000_000:
        return f"{val / 1_000_000:.2f} Juta"
    return f"{val:,.0f}"

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
            "source": make_entity(r["PEMILIK REKENING"]),
            "target": make_entity(r["NAMA LAWAN"]),
            "value": parse_amount(r["MUTASI"]),
            "date": r["TGL/TRANS"],
            "bank_src": r["BANK"],
            "bank_tgt": r["BANK LAWAN"],
            "rek_src": r["NO REK"],
            "rek_tgt": r["NO REK LAWAN"],
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

# def assign_stair_lr(df, x_step=250, y_step=140):
#     from collections import defaultdict, deque

#     sources = set(df["source"])
#     targets = set(df["target"])
#     roots = list(sources - targets) or [df["source"].iloc[0]]

#     level_map = {}
#     level_nodes = defaultdict(list)

#     queue = deque([(r, 0) for r in roots])

#     while queue:
#         node, lvl = queue.popleft()
#         if node not in level_map:
#             level_map[node] = lvl
#             level_nodes[lvl].append(node)

#             children = df[df["source"] == node]["target"].unique()
#             for c in children:
#                 queue.append((c, lvl + 1))

#     positions = {}
#     for lvl, nodes in level_nodes.items():
#         for idx, n in enumerate(nodes):
#             x = lvl * x_step
#             y = idx * y_step
#             positions[n] = (x, y)

#     return positions

def assign_stair_lr(df):
    from collections import deque
    sources = set(df["source"])
    targets = set(df["target"])
    roots = list(sources - targets) or [df["source"].iloc[0]]

    level_map = {}
    queue = deque([(r, 0) for r in roots])

    while queue:
        node, lvl = queue.popleft()
        if node not in level_map:
            level_map[node] = lvl
            children = df[df["source"] == node]["target"].unique()
            for c in children:
                queue.append((c, lvl + 1))
    return level_map


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

def compute_node_degree(df):
    from collections import Counter
    c = Counter()
    for _, r in df.iterrows():
        c[r["source"]] += 1
        c[r["target"]] += 1
    return c

def assign_staircase_levels(df):
    # Urutkan berdasarkan tanggal agar tangga mengikuti alur waktu transaksi
    df_sorted = df.sort_values("date")
    all_nodes = []
    for _, row in df_sorted.iterrows():
        if row["source"] not in all_nodes: 
            all_nodes.append(row["source"])
        if row["target"] not in all_nodes: 
            all_nodes.append(row["target"])
    
    # Memberikan level 0, 1, 2, 3... secara unik
    return {node: i for i, node in enumerate(all_nodes)}

def assign_stair_positions(df, x_step=280, y_step=140):
    from collections import defaultdict, deque

    degree = compute_node_degree(df)

    sources = set(df["source"])
    targets = set(df["target"])
    roots = list(sources - targets) or [df["source"].iloc[0]]

    level_nodes = defaultdict(list)
    visited = set()

    queue = deque([(r, 0) for r in roots])

    while queue:
        node, lvl = queue.popleft()
        if node in visited:
            continue
        visited.add(node)

        # 🔥 node besar naik ke level sendiri
        if degree[node] > 8:
            lvl += 1

        level_nodes[lvl].append(node)

        for c in df[df["source"] == node]["target"].unique():
            queue.append((c, lvl + 1))

    positions = {}
    for lvl, nodes in level_nodes.items():
        for i, n in enumerate(nodes):
            x = lvl * x_step
            y = i * y_step
            positions[n] = (x, y)

    return positions

def assign_levels_proper_hierarchy(df):
    from collections import deque
    
    # Tentukan root (node yang hanya mengirim, tidak menerima)
    sources = set(df["source"])
    targets = set(df["target"])
    roots = sources - targets
    
    # Jika tidak ada root murni (ada loop), ambil node pertama sebagai starting point
    if not roots:
        roots = [df["source"].iloc[0]]

    levels = {}
    queue = deque([(root, 0) for root in roots])
    
    while queue:
        node, lvl = queue.popleft()
        if node not in levels:
            levels[node] = lvl
            # Cari semua target yang dikirim oleh node ini
            children = df[df["source"] == node]["target"].unique()
            for child in children:
                queue.append((child, lvl + 1))
    
    # Berikan level default untuk node yang mungkin terlewat
    all_nodes = pd.unique(df[["source", "target"]].values.ravel())
    for n in all_nodes:
        if n not in levels:
            levels[n] = max(levels.values()) + 1 if levels else 0
            
    return levels

def assign_levels_proper_hierarchy(df):
    from collections import deque
    
    # Identifikasi Root (node yang hanya mengirim, tidak pernah menerima)
    sources = set(df["source"])
    targets = set(df["target"])
    roots = sources - targets
    
    # Jika ada loop/siklus, ambil node dengan transaksi terbesar sebagai root
    if not roots:
        roots = [df.groupby("source")["value"].sum().idxmax()]

    levels = {}
    queue = deque([(root, 0) for root in roots])
    visited = set()
    
    while queue:
        node, lvl = queue.popleft()
        if node not in visited:
            visited.add(node)
            # Ambil level tertinggi jika sebuah node punya banyak parent
            levels[node] = max(levels.get(node, 0), lvl)
            
            # Cari anak-anaknya
            children = df[df["source"] == node]["target"].unique()
            for child in children:
                queue.append((child, lvl + 1))
    
    return levels

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
    label_miliar = format_miliar(row.value)
    edges.append(
        Edge(
            source=row.source,
            target=row.target,
            # label=f"Rp{row.value:,.0f}",
            label=label_miliar,
            # title=f"Tanggal: {row.date.strftime('%d/%m/%Y')}",
            title=(
                f"Dari: {row.source}\n"
                f"Ke: {row.target}\n"
                f"Nominal: Rp{row.value:,.0f}"
            ),
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
    is_hierarchical = True
    direction = "UD"
    physics_enabled = True
    opts = {
        "barnesHut": {
            "gravitationalConstant": -30000,
            "centralGravity": 0.05,
            "springLength": 500,
            "avoidOverlap": 1
        }
    }


base_dir = Path(__file__).resolve().parent

node_ids = pd.unique(edge_summary[["source", "target"]].values.ravel())
# Panggil fungsi ini sebelum membuat objek Node
if layout_type == "Hirarki (Top-Down)":
    roots = set(edge_df["source"]) - set(edge_df["target"])
    node_levels = assign_levels_topdown(edge_df, roots)
    # node_levels = assign_levels_proper_hierarchy(edge_df)

elif layout_type == "Hirarki (Left-Right)":
    node_levels = assign_stair_lr(edge_df)

elif layout_type == "Timeline":
    node_levels = assign_stair_lr_time(edge_df)

else:
    node_levels = {}

nodes = []
for i, nid in enumerate(node_ids):
    style = node_style(nid)
    is_searched = search_id.lower() in nid.lower() if search_id else False

    short_label = nid.split("|")[0].upper()

    # bank_name, norek = nid.split("|") if "|" in nid else (nid, "-")
    bank_name, norek = nid.split("|") if "|" in nid else (nid, "-")
    entity_name = nid
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
        "label": nid.split("|")[0],
        "title": hover_info, # Saran: isi title dengan hover_info agar informatif
        "size": 7,
        "font": {"size": 9, "multi": True},
        "borderWidth": 4 if is_searched else 1,
        "color": style.get("color", "#999999"),
    }

    if is_hierarchical and node_levels and nid in node_levels:
        base_level = node_levels[nid]
        
    # LOGIKA GARIS PANJANG/PENDEK:
        if base_level > 0:
            # Gunakan random atau logika genap/ganjil agar berstektur
            # offset = random.choice([1.0, 2, 4]) # 0=normal, 1=lebih panjang
            group_offset = (i % 5) * 0.8
            # offset = 4
            node_kwargs["level"] = base_level + group_offset
        else:
            node_kwargs["level"] = base_level
    if node_image:
        node_kwargs["image"] = node_image
        node_kwargs["shape"] = "circularImage"
    else:
        node_kwargs["shape"] = "dot"            
    nodes.append(Node(**node_kwargs))

config = Config(
    width=2000,
    height=3000,
    directed=True,
    physics=physics_enabled,  # Wajib False untuk layout tangga yang stabil
    physics_config={
        "repulsion": {
            "nodeDistance": 250,   # jarak minimum antar node
            "centralGravity": 0.1,
            "springLength": 300,
            "springConstant": 0.05
        }
    },
    hierarchical=is_hierarchical,
    extra_options={
        "layout": {
            "hierarchical": {
                "enabled": is_hierarchical,
                "direction": direction,
                "sortMethod": "directed",
                "levelSeparation": 600, # jarak antar level (VERTIKAL)
                "nodeSpacing": 1000, # jarak node dalam 1 level (HORIZONTAL)
                "treeSpacing": 500,
                "blockShifting": True,       # Mencegah node ditarik kembali ke tengah
                "edgeMinimization": True,    # Mencegah garis bertumpuk
                "parentCentralization": False # Mencegah anak tangga sejajar di bawah induk
            }
        },
        "physics": {
            "enabled": physics_enabled,
            "solver": solver, # Mengambil dari variabel di atas
            **opts,           # Memasukkan dictionary setting spesifik
            # "stabilization": {"enabled": True, "iterations": 200}
        },
        "edges": {
            "smooth": {
                "enabled": True,
                "type": "cubicBezier", 
                "forceDirection": "vertical",
                "roundness": 0.5
            },
            "font": {
                "size": 7, ## <-- Kecilkan angka ini
                "align": "vertical", # Menaruh teks di atas garis agar lebih rapi
                "vadjust": 0, # Mengatur jarak vertikal teks agar tidak menempel garis
                "background": "none", # Memberi background transparan agar terbaca
                "strokeWidth": 2,    # Hilangkan stroke jika tulisan terlalu kecil
                "strokeColor": "#ffffff",
                "color": "#34495e"
            }
        },
        "interaction": {
            "hover": True,
            "multiselect": True,
            "dragNodes": True
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

if "expanded_entities" not in st.session_state:
    st.session_state.expanded_entities = set()
    st.rerun()

st.markdown("### ⬇️ Download Visual SNA")

format_choice = st.selectbox(
    "Pilih format file",
    ["PNG", "JPG", "PDF"],
    key="download_format"
)

st.components.v1.html(f"""
<div style="margin-top:10px;">
  <button style="
      padding:10px 20px;
      background:#2E86DE;
      color:white;
      border:none;
      border-radius:6px;
      cursor:pointer;
      font-size:14px;"
      onclick="downloadGraph()">
      Download Graph
  </button>
</div>

<script>
function downloadGraph() {{
    const canvas = document.querySelector("canvas");
    if (!canvas) {{
        alert("Graph belum siap");
        return;
    }}

    const format = "{format_choice.lower()}";
    let mime = "image/png";
    let filename = "sna_graph.png";

    if (format === "jpg") {{
        mime = "image/jpeg";
        filename = "sna_graph.jpg";
    }}

    if (format === "pdf") {{
        const imgData = canvas.toDataURL("image/png");
        const pdfWindow = window.open("");
        pdfWindow.document.write(`
            <html>
              <head><title>SNA Graph</title></head>
              <body style="margin:0">
                <img src="${{imgData}}" style="width:100%">
                <script>
                  window.onload = function() {{
                    window.print();
                  }}
                </script>
              </body>
            </html>
        `);
        return;
    }}

    const link = document.createElement("a");
    link.download = filename;
    link.href = canvas.toDataURL(mime);
    link.click();
}}
</script>
""", height=120)


# if selected_node_id and isinstance(selected_node_id, str):
if selected_node_id:
    # bank_name, norek = selected_node_id.split("|")
    if selected_node_id in st.session_state.expanded_entities:
        st.session_state.expanded_entities.remove(selected_node_id)
    else:
        st.session_state.expanded_entities.add(selected_node_id)

    if "|" in selected_node_id:
        # bank_name, norek = selected_node_id.split("|", 1)
        parts = selected_node_id.split("|", 1)
        bank_name = parts[0]
        norek = parts[1]
    else:
        # bank_name, norek = selected_node_id, "-"
        bank_name = selected_node_id
        norek = "-"

    st.sidebar.markdown("---")
    st.sidebar.subheader("📋 Account Properties")

    total_val = node_weight.get(selected_node_id, 0)
    st.sidebar.write(f"**Institusi:** {bank_name}")
    st.sidebar.write(f"**No Rekening:** {norek}")
    st.sidebar.write(f"**Total Mutasi:** Rp{total_val:,.0f} ({format_miliar(total_val)})")
    # st.sidebar.write(f"**Total Mutasi:** Rp{total_val:,.0f}")

    tx_df = edge_df[
        (edge_df["source"] == selected_node_id) |
        (edge_df["target"] == selected_node_id)
    ].copy()

    if not tx_df.empty:
        tx_df["Arah"] = tx_df.apply(
            lambda r: "KELUAR" if r["source"] == selected_node_id else "MASUK", axis=1
        )
        tx_df = tx_df[["date", "Arah", "source", "target", "value"]].sort_values("date", ascending=False)
        tx_df["value"] = tx_df["value"].apply(lambda x: f"Rp{x:,.0f}")
        
        st.sidebar.dataframe(tx_df, use_container_width=True)
