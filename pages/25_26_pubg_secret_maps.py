"""M26：PUBG 高清密室位置图。"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from utils.pubg_map_viewer import build_map_viewer
from utils.pubg_secret_maps import SOURCE_CHECKED_ON, load_catalog, load_map_image
from utils.ui_theme import render_home_link


st.set_page_config(page_title="PUBG 密室地图", page_icon="🗺️", layout="wide")
render_home_link()
st.markdown("### 🗺️ PUBG 密室地图 · M26")

try:
    catalog = load_catalog()
except (OSError, ValueError):
    st.error("地图目录暂时无法读取，请稍后重试。")
    st.stop()

if not catalog:
    st.info("暂时没有可展示的位置图。")
    st.stop()

maps_by_id = {item["id"]: item for item in catalog}
map_ids = list(maps_by_id)
map_col, image_col = st.columns([3, 2])
with map_col:
    selected_map_id = st.selectbox(
        "地图",
        options=map_ids,
        index=map_ids.index("erangel") if "erangel" in maps_by_id else 0,
        format_func=lambda map_id: maps_by_id[map_id]["name"],
        key="pubg_secret_map",
    )

selected_map = maps_by_id[selected_map_id]
images_by_id = {item["id"]: item for item in selected_map["images"]}
if not images_by_id:
    st.warning("这张地图的位置图暂时不可用。")
    st.stop()

with image_col:
    if len(images_by_id) > 1:
        selected_image_id = st.selectbox(
            "位置图",
            options=list(images_by_id),
            format_func=lambda image_id: images_by_id[image_id]["label"],
            key=f"pubg_secret_image_{selected_map_id}",
        )
    else:
        selected_image_id = next(iter(images_by_id))

selected_image = images_by_id[selected_image_id]
crop_box = (
    tuple(selected_image["display_crop"]) if selected_image.get("display_crop") else None
)
display_width, display_height = (
    crop_box[2:] if crop_box else (selected_image["width"], selected_image["height"])
)
st.caption(f"{selected_map['kind']} · {selected_map['access_note']}")
st.caption(
    f"{selected_image['label']} · "
    f"{display_width:,} × {display_height:,} 像素"
)

image_bytes = None
try:
    image_bytes = load_map_image(selected_image_id)
    viewer = build_map_viewer(
        image_bytes,
        selected_image["mime_type"],
        f"{selected_map['name']} · {selected_image['label']}",
        crop_box=crop_box,
    )
except (OSError, ValueError):
    image_bytes = None
    st.warning("位置图暂时无法加载，可通过下方链接查看原图或来源页面。")
else:
    if hasattr(st, "iframe"):
        st.iframe(viewer, height="content")
    else:
        # Compatibility with older deployments within the supported 1.x range.
        components.html(viewer, height=650, scrolling=False)

if selected_image["legend"]:
    st.caption(f"图例：{selected_image['legend']}")

download_col, original_col, source_col = st.columns(3)
with download_col:
    if image_bytes is not None:
        st.download_button(
            "下载来源原图",
            data=image_bytes,
            file_name=Path(selected_image["filename"]).name,
            mime=selected_image["mime_type"],
            key=f"pubg_download_{selected_image_id}",
        )
with original_col:
    st.link_button("打开网络原图 ↗", selected_image["original_url"])
with source_col:
    st.link_button("查看图源页面 ↗", selected_image["source_url"])

with st.expander("来源与版本说明"):
    st.write(f"来源 / 作者：{selected_image['author']}")
    st.write(selected_image["source_note"])
    st.caption(
        f"资料收录核对日期：{SOURCE_CHECKED_ON}。点位来自社区图，未做游戏内逐点复核；"
        "游戏更新可能调整点位与进入方式。图片版权归原作者及 PUBG / KRAFTON 所有。"
    )
    if selected_map.get("mechanics_url"):
        st.link_button("官方机制说明 ↗", selected_map["mechanics_url"])

st.caption(
    "范围：收录六张地图的固定密室位置图；按要求排除帕拉莫和卡拉金。"
    "萨诺物资卡车、褐湾物资箱等不属于本次固定密室图。"
)
