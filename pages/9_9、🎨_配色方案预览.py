import streamlit as st
import re
import os

st.set_page_config(page_title="配色方案预览", page_icon="🎨", layout="wide")

PALETTES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "color_palettes.md")


def parse_palettes(text: str) -> list[dict]:
    palettes = []
    blocks = re.split(r"(?=\n## \d+[、.])", text)
    for block in blocks:
        m = re.match(r"\n## (\d+)[、.]\s*(.+?)$", block, re.MULTILINE)
        if not m:
            continue
        pid = int(m.group(1))
        name = m.group(2).strip()

        # 解析颜色名+色号对，如 "飞燕草蓝 #8899A9"
        color_line = ""
        for line in block.split("\n"):
            if "#" in line and not line.strip().startswith("##") and "场景" not in line and "来源" not in line:
                color_line = line.strip().lstrip("- ").strip()
                break

        pairs = []
        for part in color_line.split("+"):
            part = part.strip()
            hex_m = re.search(r"(#[0-9A-Fa-f]{6})", part)
            if hex_m:
                hex_code = hex_m.group(1)
                cname = part.replace(hex_code, "").strip()
                pairs.append({"name": cname, "hex": hex_code})

        colors = [p["hex"] for p in pairs]

        scene = ""
        source = ""
        sm = re.search(r"- 场景[：:]\s*(.+)$", block, re.MULTILINE)
        if sm:
            scene = sm.group(1).strip()
        srcm = re.search(r"- 来源[：:]\s*(.+)$", block, re.MULTILINE)
        if srcm:
            source = srcm.group(1).strip()
        palettes.append({
            "id": pid, "name": name, "colors": colors, "pairs": pairs,
            "scene": scene, "source": source, "raw": block.strip(),
        })
    return palettes


def color_text(hex_code: str) -> str:
    r, g, b = int(hex_code[1:3], 16), int(hex_code[3:5], 16), int(hex_code[5:7], 16)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    fg = "#ffffff" if lum < 140 else "#000000"
    return f'<span style="background:{hex_code};color:{fg};padding:6px 14px;margin:2px;border-radius:4px;font-family:monospace;font-weight:bold">{hex_code}</span>'


# 读取数据
with open(PALETTES_PATH, "r", encoding="utf-8") as f:
    raw_text = f.read()

palettes = parse_palettes(raw_text)

st.title("🎨 配色方案预览")

# ── 左侧选择 + 右侧预览 ──
col_sel, col_preview = st.columns([1, 2])

with col_sel:
    st.subheader("选择方案")
    options = [f"{p['id']}、{p['name']}" for p in palettes]
    selected = st.selectbox("编号", options, label_visibility="collapsed")
    sel_id = int(selected.split("、")[0])
    pal = next(p for p in palettes if p["id"] == sel_id)

    st.markdown(f"**{pal['name']}**")
    if pal["scene"]:
        st.caption(f"场景：{pal['scene']}")
    if pal["source"]:
        st.caption(f"来源：{pal['source']}")

    # 色卡色块
    st.markdown("---")
    pairs = pal.get("pairs", [])
    cols = st.columns(len(pal["colors"]))
    for i, c in enumerate(pal["colors"]):
        with cols[i]:
            label = pairs[i]["name"] if i < len(pairs) and pairs[i]["name"] else f"色{i+1}"
            st.color_picker(label, c, disabled=True, key=f"cp_{sel_id}_{i}")

with col_preview:
    st.subheader("色卡预览")

    # ── 公众号同款竖条色卡 ──
    strips = ""
    for i, c in enumerate(pal["colors"]):
        cname = pal["pairs"][i]["name"] if i < len(pal["pairs"]) else ""
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        fg = "#ffffff" if lum < 140 else "#222222"
        label = f"{cname}<br>{c}" if cname else c
        strips += (
            f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;'
            f"padding-bottom:14px;background:{c};min-height:220px;"
            f'font-size:12px;font-weight:600;color:{fg};line-height:1.6;text-align:center">'
            f"{label}</div>"
        )
    st.markdown(
        f'<div style="display:flex;gap:4px;border-radius:12px;overflow:hidden;'
        f"box-shadow:0 2px 12px rgba(0,0,0,.15);margin:12px 0\">{strips}</div>",
        unsafe_allow_html=True,
    )

    # ── 色号文字区 ──
    parts = []
    for i, c in enumerate(pal["colors"]):
        if i < len(pal["pairs"]) and pal["pairs"][i]["name"]:
            parts.append(f"{pal['pairs'][i]['name']} {c}")
        else:
            parts.append(c)
    st.code(" + ".join(parts), language=None)

# ── 底部：原始 Markdown ──
st.markdown("---")
with st.expander("📄 查看完整配色方案库（color_palettes.md）", expanded=False):
    st.markdown(raw_text)
