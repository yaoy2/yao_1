"""M25: encrypted, memory-only relay; the L browser writes original files."""

import streamlit as st

from utils.ui_theme import render_home_link
from utils.phone_transfer_relay import RelayBroker
from utils.phone_transfer_component import declare_transfer_component


st.set_page_config(page_title="M25 · 随手传", page_icon="📲", layout="wide")
render_home_link()
st.title("📲 随手传")
st.caption("手机发送，办公电脑 L 自动保存。无需同一个 Wi-Fi。")

transfer = declare_transfer_component()


@st.cache_resource
def shared_relay():
    return RelayBroker()


@st.fragment(run_every=1.0)
def transfer_panel():
    # Read the last widget value BEFORE rendering, so an input rerun delivers
    # its reply immediately. A fixed key keeps the component iframe mounted.
    request = st.session_state.get("phone-transfer-v1")
    response = shared_relay().exchange(request) if isinstance(request, dict) else None
    request_id = request.get("request_id") if isinstance(request, dict) else None
    transfer(relay=response, request_id=request_id, key="phone-transfer-v1", default=None)


transfer_panel()

with st.expander("首次使用与原图说明"):
    st.markdown(
        "1. 在办公电脑 L 的 **Edge 或 Chrome** 打开本页，点 **设为办公电脑 L**，选择保存文件夹。\n"
        "2. 手机扫描绑定二维码，之后收藏手机页面即可，绑定信息保存在各自的浏览器中。\n"
        "3. 保持 L 的接收页面打开；可用 **独立接收窗口** 留一个标签页，其他标签页照常使用工具箱。\n\n"
        "**原图：**本工具逐字节传输并校验，不缩放、压缩或转换照片。"
        "iPhone 从相册交给浏览器时可能转换格式；若要求相机原件，先在照片中"
        "选择 **导出未修改的原片** 到“文件”，再从“文件”选取，实况照片的图片与视频一起发送。\n\n"
        "单个文件最多 **200 MiB**。只在电脑完成写入、重新读取并校验通过后报告送达。"
        "接收页关闭、浏览器休眠或电脑断网时不能接收；重新打开后会尝试恢复，"
        "浏览器可能要求再次授权文件夹。传输分块在手机加密，经工具箱临时转送，"
        "由 L 解密保存；服务器只暂存少量密文，不保存完整文件，也不写入 GitHub。"
    )
