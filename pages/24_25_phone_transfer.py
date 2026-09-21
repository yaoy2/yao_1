"""M25: Photos share uploads and encrypted browser relay, saved by L's browser."""

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
        "2. 手机扫描绑定二维码，点 **下载快捷指令**，打开下载项并确认添加；返回网页点 **自动绑定 L**。"
        "无需手填地址或逐项添加操作。首次使用按系统提示允许访问 iCloud Drive 和网络。\n"
        "3. 以后从 **照片 App → 选择照片 → 分享 → 发送到办公电脑 L** 发起，"
        "无需先打开手机网页或导出到“文件”。网页选照片和普通文件仍可作为备用入口。\n"
        "4. 保持 L 的接收页面打开；可用 **独立接收窗口** 留一个标签页，其他标签页照常使用工具箱。\n\n"
        "**画质与格式：**本工具逐字节传输并校验系统交出的文件，不缩放、压缩或转换。"
        "从相册分享时，在“选项”中选 **当前**；快捷指令不添加转换或缩放操作。"
        "网页选图时若出现格式或大小选项，选择 **当前** 和 **实际大小／原始大小**。"
        "网页已声明接受 HEIC、HEIF、JPEG、PNG 等照片格式，但无法强制关闭 iPhone 系统的格式转换；"
        "因此不能保证每个 iOS 版本交出的都是相机原始字节。实况照片可能只提供静态图。\n\n"
        "单个文件最多 **200 MiB**。只在电脑完成写入、重新读取并校验通过后报告送达。"
        "接收页关闭、浏览器休眠或电脑断网时不能接收；重新打开后会尝试恢复，"
        "浏览器可能要求再次授权文件夹。**快捷指令发送：**通过 HTTPS 上传至工具箱临时中转，"
        "L 保存并校验后清理临时副本；未完成副本约 10 分钟后过期清理，不写 GitHub。"
        "**网页发送：**使用浏览器之间的加密分块通道。"
    )
