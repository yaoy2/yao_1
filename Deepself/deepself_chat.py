from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import requests


PROJECT_DIR = Path(__file__).resolve().parent
SKILL_DIR = PROJECT_DIR / "skill" / "write-like-sir"
STYLE_PROFILE_PATH = SKILL_DIR / "references" / "style-profile.md"
CHAT_PROFILE_PATH = SKILL_DIR / "references" / "chat-reply.md"


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    api_url: str
    default_model: str
    env_keys: tuple[str, ...]
    secret_keys: tuple[str, ...]
    secret_sections: tuple[str, ...]


PROVIDERS: dict[str, ProviderSpec] = {
    "deepseek": ProviderSpec(
        key="deepseek",
        label="DeepSeek",
        api_url="https://api.deepseek.com/chat/completions",
        default_model="deepseek-v4-flash",
        env_keys=("DEEPSEEK_API_KEY",),
        secret_keys=("DEEPSEEK_API_KEY", "deepseek_api_key"),
        secret_sections=("deepseek",),
    ),
    "kimi": ProviderSpec(
        key="kimi",
        label="Kimi",
        api_url="https://api.moonshot.cn/v1/chat/completions",
        default_model="kimi-k2.6",
        env_keys=("MOONSHOT_API_KEY", "KIMI_API_KEY"),
        secret_keys=("MOONSHOT_API_KEY", "KIMI_API_KEY", "moonshot_api_key", "kimi_api_key"),
        secret_sections=("moonshot", "kimi"),
    ),
    "glm": ProviderSpec(
        key="glm",
        label="GLM",
        api_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        default_model="glm-5.3",
        env_keys=("GLM_API_KEY", "ZHIPU_API_KEY"),
        secret_keys=("GLM_API_KEY", "ZHIPU_API_KEY", "glm_api_key", "zhipu_api_key"),
        secret_sections=("glm", "zhipu"),
    ),
}


class ChatAPIError(RuntimeError):
    """A user-safe API error that never includes credentials or prompt text."""


def _mapping_get(mapping: Any, key: str) -> Any:
    if mapping is None:
        return None
    try:
        return mapping.get(key)
    except Exception:
        try:
            return mapping[key]
        except Exception:
            return None


def _clean_secret(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def get_api_key(
    provider_key: str,
    *,
    secrets: Mapping[str, Any] | Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    spec = PROVIDERS[provider_key]
    environ = os.environ if environ is None else environ

    for key in spec.secret_keys:
        value = _clean_secret(_mapping_get(secrets, key))
        if value:
            return value

    for section_name in spec.secret_sections:
        section = _mapping_get(secrets, section_name)
        value = _clean_secret(_mapping_get(section, "api_key"))
        if value:
            return value

    for key in spec.env_keys:
        value = _clean_secret(_mapping_get(environ, key))
        if value:
            return value
    return None


def provider_statuses(
    *,
    secrets: Mapping[str, Any] | Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, bool]:
    return {
        key: bool(get_api_key(key, secrets=secrets, environ=environ))
        for key in PROVIDERS
    }


def load_prompt_profiles() -> tuple[str, str]:
    return (
        STYLE_PROFILE_PATH.read_text(encoding="utf-8").strip(),
        CHAT_PROFILE_PATH.read_text(encoding="utf-8").strip(),
    )


def build_system_prompt(style_profile: str, chat_profile: str, tone: str = "标准") -> str:
    tone = tone if tone in {"克制", "标准", "锋利"} else "标准"
    return f"""你是 Sir 的中文回复起草助手，不是 Sir 本人。

任务：根据用户给出的对方消息、语境、事实或修改要求，生成一条 Sir 可以直接发送的回复。

硬性要求：
1. 只输出回复正文，不解释写法，不加标题、引号或“可以这样回复”。
2. 不虚构事实、经历、关系、时间、数字、承诺或他人动机。
3. 不把朋友圈原文或风格分析透露给对话对象。
4. 当前强度为“{tone}”。短消息优先自然简短，不为展示文风强行写成长文。
5. 如果输入涉及正式公文、法律、医疗或其他高风险决定，保持克制并指出需要人工确认的关键边界。

以下是抽象后的表达画像，不包含朋友圈原文：

{style_profile}

以下是聊天回复规则：

{chat_profile}
""".strip()


def trim_history(
    messages: Sequence[Mapping[str, Any]],
    *,
    max_messages: int = 16,
    max_characters: int = 12000,
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "")).strip()
        content = str(message.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            cleaned.append({"role": role, "content": content})

    selected: list[dict[str, str]] = []
    used_characters = 0
    for message in reversed(cleaned[-max_messages:]):
        length = len(message["content"])
        if selected and used_characters + length > max_characters:
            break
        selected.append(message)
        used_characters += length
    return list(reversed(selected))


def build_request_payload(
    *,
    model: str,
    messages: Sequence[Mapping[str, Any]],
    system_prompt: str,
    max_tokens: int = 900,
) -> dict[str, Any]:
    model = str(model).strip()
    if not model:
        raise ValueError("模型名称不能为空")
    history = trim_history(messages)
    if not history or history[-1]["role"] != "user":
        raise ValueError("对话最后一条必须是用户消息")
    return {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, *history],
        "max_tokens": int(max_tokens),
        "stream": False,
    }


def _http_error_message(provider: ProviderSpec, status_code: int) -> str:
    if status_code == 400:
        return f"{provider.label} 拒绝了请求，请检查模型名称或输入长度。"
    if status_code in {401, 403}:
        return f"{provider.label} 鉴权失败，请检查对应 API Key。"
    if status_code == 429:
        return f"{provider.label} 当前额度不足或请求过于频繁。"
    if status_code >= 500:
        return f"{provider.label} 服务暂时异常，请稍后重试。"
    return f"{provider.label} 请求失败（HTTP {status_code}）。"


def call_chat_completion(
    provider_key: str,
    *,
    api_key: str,
    model: str,
    messages: Sequence[Mapping[str, Any]],
    system_prompt: str,
    timeout: int = 120,
    post: Any = requests.post,
) -> str:
    spec = PROVIDERS[provider_key]
    if not _clean_secret(api_key):
        raise ChatAPIError(f"未配置 {spec.label} API Key。")

    payload = build_request_payload(
        model=model,
        messages=messages,
        system_prompt=system_prompt,
    )
    try:
        response = post(
            spec.api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise ChatAPIError(f"{spec.label} 响应超时，请稍后重试。") from exc
    except requests.RequestException as exc:
        raise ChatAPIError(f"无法连接 {spec.label}，请检查网络或代理。") from exc

    if response.status_code >= 400:
        raise ChatAPIError(_http_error_message(spec, response.status_code))

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ChatAPIError(f"{spec.label} 返回格式异常。") from exc
    content = str(content).strip()
    if not content:
        raise ChatAPIError(f"{spec.label} 返回了空回复。")
    return content


def generate_reply(
    provider_key: str,
    *,
    api_key: str,
    model: str,
    messages: Sequence[Mapping[str, Any]],
    tone: str = "标准",
    timeout: int = 120,
    post: Any = requests.post,
) -> str:
    style_profile, chat_profile = load_prompt_profiles()
    prompt = build_system_prompt(style_profile, chat_profile, tone=tone)
    return call_chat_completion(
        provider_key,
        api_key=api_key,
        model=model,
        messages=messages,
        system_prompt=prompt,
        timeout=timeout,
        post=post,
    )
