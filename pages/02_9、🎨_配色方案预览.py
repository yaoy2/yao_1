import streamlit as st
import streamlit.components.v1 as components
import re
import os
from html import escape
from utils.ui_theme import render_home_link

st.set_page_config(page_title="配色方案预览", page_icon="🎨", layout="wide")
render_home_link()

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


def get_contrast_color(hex_code: str) -> str:
    r, g, b = int(hex_code[1:3], 16), int(hex_code[3:5], 16), int(hex_code[5:7], 16)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return "#ffffff" if lum < 140 else "#172033"


def role_for_color(index: int) -> tuple[str, str]:
    roles = [
        ("主色", "标题 / 大面积背景 / 高级感主体"),
        ("辅助色", "分割线 / 标签 / 次级区块"),
        ("背景色", "正文底色 / 留白 / PPT 页面背景"),
    ]
    if index < len(roles):
        return roles[index]
    return (f"点缀色{index - 2}", "强调数字 / 图标 / 小面积提示")


def render_palette_showcase(pal: dict) -> str:
    pairs = pal.get("pairs", [])
    colors = pal.get("colors", [])
    if not colors:
        return '<div style="padding:24px;border:1px solid #ddd;border-radius:12px;">暂无颜色数据</div>'

    main = colors[0]
    secondary = colors[1] if len(colors) > 1 else colors[0]
    background = colors[2] if len(colors) > 2 else "#F8F6F2"
    main_name = pairs[0]["name"] if pairs and pairs[0].get("name") else "主色"
    scene = escape(pal.get("scene") or "PPT、海报、视觉参考")
    palette_name = escape(pal.get("name") or "未命名配色")
    fg_main = get_contrast_color(main)
    fg_secondary = get_contrast_color(secondary)
    fg_background = get_contrast_color(background)

    color_rows = ""
    for i, color in enumerate(colors):
        role, usage = role_for_color(i)
        cname = pairs[i]["name"] if i < len(pairs) and pairs[i].get("name") else role
        fg = get_contrast_color(color)
        color_rows += f"""
        <div class="palette-row" style="background:{color};color:{fg};">
          <div>
            <div class="palette-role">{escape(role)}</div>
            <div class="palette-name">{escape(cname)}</div>
          </div>
          <div class="palette-meta">
            <div class="palette-hex">{escape(color)}</div>
            <div class="palette-usage">{escape(usage)}</div>
          </div>
        </div>
        """

    return f"""
    <style>
      .palette-showcase {{
        max-width: 460px;
        margin: 0 auto 10px;
        padding: 7px;
        border-radius: 20px;
        background: #050505;
        box-shadow: 0 10px 28px rgba(15, 23, 42, .18);
      }}
      .palette-showcase * {{
        box-sizing: border-box;
      }}
      .palette-hero {{
        position: relative;
        height: 146px;
        overflow: hidden;
        border-radius: 16px;
        padding: 14px 18px;
        background: {main};
        color: {fg_main};
      }}
      .palette-kicker {{
        display: inline-flex;
        padding: 3px 9px;
        border: 1.5px solid currentColor;
        border-radius: 11px;
        font-size: 10px;
        font-weight: 800;
        opacity: .86;
      }}
      .palette-title {{
        margin-top: 12px;
        font-size: clamp(22px, 3.4vw, 31px);
        line-height: 1.05;
        font-weight: 900;
        letter-spacing: 0;
      }}
      .palette-subtitle {{
        margin-top: 5px;
        font-size: 12px;
        font-weight: 800;
      }}
      .palette-script {{
        position: absolute;
        right: 18px;
        top: 56px;
        font-family: Georgia, "Times New Roman", serif;
        font-size: clamp(36px, 5.4vw, 50px);
        font-style: italic;
        line-height: 1;
        color: {background};
        opacity: .96;
      }}
      .palette-main-code {{
        position: absolute;
        right: 18px;
        bottom: 14px;
        text-align: right;
        font-size: 13px;
        font-weight: 900;
      }}
      .palette-scene {{
        position: absolute;
        left: 18px;
        bottom: 15px;
        max-width: 55%;
        font-size: 10px;
        font-weight: 800;
      }}
      .palette-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        height: 46px;
        margin-top: 6px;
        padding: 7px 16px;
        border-radius: 12px;
      }}
      .palette-role {{
        font-size: 10px;
        font-weight: 900;
        opacity: .72;
      }}
      .palette-name {{
        margin-top: 1px;
        font-size: 15px;
        font-weight: 900;
      }}
      .palette-meta {{
        text-align: right;
      }}
      .palette-hex {{
        font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
        font-size: 14px;
        font-weight: 900;
      }}
      .palette-usage {{
        margin-top: 1px;
        font-size: 9px;
        font-weight: 800;
        opacity: .82;
      }}
      .palette-application {{
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        gap: 6px;
        margin-top: 6px;
        padding: 7px;
        border-radius: 12px;
        background: {background};
        color: {fg_background};
      }}
      .palette-app-item {{
        height: 34px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 9px;
        text-align: center;
        font-size: 10px;
        font-weight: 900;
      }}
      @media (max-width: 700px) {{
        .palette-showcase {{ max-width: 430px; padding: 7px; border-radius: 19px; }}
        .palette-hero {{ height: 142px; padding: 14px 16px; }}
        .palette-script {{ right: 16px; top: 56px; }}
        .palette-main-code {{ right: 16px; bottom: 14px; font-size: 13px; }}
        .palette-scene {{ left: 16px; bottom: 15px; max-width: 58%; font-size: 10px; }}
        .palette-row {{ height: 46px; padding: 7px 14px; }}
        .palette-meta {{ text-align: right; }}
        .palette-application {{ grid-template-columns: 1fr; }}
      }}
      @media (max-width: 420px) {{
        .palette-row {{ height: 56px; align-items: flex-start; flex-direction: column; }}
        .palette-meta {{ text-align: left; }}
      }}
    </style>

    <div class="palette-showcase">
      <div class="palette-hero">
        <div class="palette-kicker">配色灵感 · 审美参考</div>
        <div class="palette-title">高级感配色</div>
        <div class="palette-subtitle">（{palette_name}）</div>
        <div class="palette-script">Color</div>
        <div class="palette-scene">{scene}</div>
        <div class="palette-main-code">{escape(main)}<br>{escape(main_name)}</div>
      </div>
      {color_rows}
      <div class="palette-application">
        <div class="palette-app-item" style="background:{main};color:{fg_main};">PPT 标题条</div>
        <div class="palette-app-item" style="background:{secondary};color:{fg_secondary};">图表强调</div>
        <div class="palette-app-item" style="background:{background};color:{fg_background};border:1px solid rgba(23,32,51,.14);">正文背景</div>
      </div>
    </div>
    """


def render_palette_code(parts: list[str]) -> str:
    code_text = " + ".join(parts)
    return f"""
    <div style="max-width:500px;margin:0 auto;">
      <pre style="box-sizing:border-box;width:100%;margin:0;padding:12px 14px;border-radius:10px;
        background:#f6f8fa;color:#172033;border:1px solid #e5e7eb;white-space:pre-wrap;
        overflow-wrap:anywhere;font-size:13px;line-height:1.45;
        font-family:ui-monospace,SFMono-Regular,Consolas,monospace;">{escape(code_text)}</pre>
    </div>
    """


# 读取数据
with open(PALETTES_PATH, "r", encoding="utf-8") as f:
    raw_text = f.read()

palettes = parse_palettes(raw_text)

# ── 左侧选择 + 右侧预览 ──
col_sel, col_preview = st.columns([1, 2])

with col_sel:
    st.title("🎨 配色方案预览")
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
    components.html(render_palette_showcase(pal), height=470, scrolling=False)

    # ── 色号文字区 ──
    parts = []
    for i, c in enumerate(pal["colors"]):
        if i < len(pal["pairs"]) and pal["pairs"][i]["name"]:
            parts.append(f"{pal['pairs'][i]['name']} {c}")
        else:
            parts.append(c)
    st.markdown(render_palette_code(parts), unsafe_allow_html=True)

# ── 底部：原始 Markdown ──
st.markdown("---")
with st.expander("📄 查看完整配色方案库（color_palettes.md）", expanded=False):
    st.markdown(raw_text)
