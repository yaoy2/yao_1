"""LLM 各厂商余额查询模块"""

from .base import BaseProvider, BalanceResult
from .deepseek import DeepSeekProvider
from .kimi import KimiProvider

# 支持自动查询的厂商
PROVIDERS = {
    "deepseek": DeepSeekProvider(),
    "kimi": KimiProvider(),
}

# 不支持自动查询的厂商（仅提供链接跳转 + 手动录入）
MANUAL_PROVIDERS = {
    "mimo": {
        "name": "小米 MiMo",
        "console_url": "https://platform.xiaomimimo.com/#/console/balance",
    },
    "chatgpt": {
        "name": "ChatGPT Plus",
        "console_url": "https://chat.openai.com/#settings/subscription",
    },
}

__all__ = ["PROVIDERS", "MANUAL_PROVIDERS", "BaseProvider", "BalanceResult"]
