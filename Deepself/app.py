from __future__ import annotations

import streamlit as st

try:
    from Deepself.deepself_chat import (
        PROVIDERS,
        ChatAPIError,
        generate_reply,
        get_api_key,
        provider_statuses,
    )
except ModuleNotFoundError:
    from deepself_chat import (
        PROVIDERS,
        ChatAPIError,
        generate_reply,
        get_api_key,
        provider_statuses,
    )


st.set_page_config(page_title="Deepself 对话框", page_icon="💬", layout="centered")


def _secrets():
    try:
        return st.secrets
    except Exception:
        return None


def _run_reply(provider_key: str, model: str, tone: str, messages: list[dict[str, str]]) -> str:
    api_key = get_api_key(provider_key, secrets=_secrets())
    if not api_key:
        raise ChatAPIError(f"未配置 {PROVIDERS[provider_key].label} API Key。")
    return generate_reply(
        provider_key,
        api_key=api_key,
        model=model,
        messages=messages,
        tone=tone,
    )


if "deepself_messages" not in st.session_state:
    st.session_state.deepself_messages = []

st.title("Deepself · 像我一样回复")
st.caption("把对方的话、聊天背景或您想表达的意思发进来，得到一条可直接发送的回复。")

with st.sidebar:
    st.subheader("模型设置")
    provider_key = st.selectbox(
        "供应商",
        options=list(PROVIDERS),
        format_func=lambda key: PROVIDERS[key].label,
    )
    spec = PROVIDERS[provider_key]
    model = st.text_input("模型", value=spec.default_model, key=f"model_{provider_key}")

    statuses = provider_statuses(secrets=_secrets())
    st.caption("密钥状态")
    for key, configured in statuses.items():
        marker = "已配置" if configured else "未配置"
        st.write(f"{PROVIDERS[key].label}：{marker}")

    if st.button("清空当前对话", use_container_width=True):
        st.session_state.deepself_messages = []
        st.rerun()

    with st.expander("密钥名称"):
        st.write("DeepSeek：`DEEPSEEK_API_KEY`")
        st.write("Kimi：`MOONSHOT_API_KEY` 或 `KIMI_API_KEY`")
        st.write("GLM：`GLM_API_KEY` 或 `ZHIPU_API_KEY`")
        st.caption("密钥只从环境变量或 Streamlit Secrets 读取，不会写进聊天记录。")

messages: list[dict[str, str]] = st.session_state.deepself_messages
for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

configured_key = get_api_key(provider_key, secrets=_secrets())
if not configured_key:
    st.info(f"当前未配置 {spec.label} API Key。配置后刷新页面即可使用。")

user_text = st.chat_input("输入对方发来的消息、背景或您的回复意图……")
if user_text:
    messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)
    with st.chat_message("assistant"):
        try:
            with st.spinner(f"正在让 {spec.label} 起草回复……"):
                reply = _run_reply(provider_key, model, "标准", messages)
            st.markdown(reply)
            messages.append({"role": "assistant", "content": reply})
        except (ChatAPIError, ValueError) as exc:
            st.error(str(exc))

if messages and messages[-1]["role"] == "assistant":
    st.divider()
    st.caption("调整最新回复")
    columns = st.columns(3)
    tone_labels = (("克制", "更克制"), ("标准", "更自然"), ("锋利", "更锋利"))
    for column, (tone, label) in zip(columns, tone_labels):
        if column.button(label, use_container_width=True, key=f"rewrite_{tone}"):
            source_messages = messages[:-1]
            try:
                with st.spinner(f"正在生成{label}的版本……"):
                    replacement = _run_reply(provider_key, model, tone, source_messages)
                messages[-1] = {"role": "assistant", "content": replacement}
                st.rerun()
            except (ChatAPIError, ValueError) as exc:
                st.error(str(exc))

    with st.expander("复制最新回复"):
        st.code(messages[-1]["content"], language=None)

st.caption("当前对话仅保存在本次页面会话；发送给模型的内容仍受对应 API 服务商的数据政策约束。")
