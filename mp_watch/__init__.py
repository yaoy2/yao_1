# -*- coding: utf-8 -*-
"""微信公众号监控：免费发现源轮询 + 复用 wechat_core 全文归档。

所有配置、状态、日志默认落在本仓库（E 盘项目目录）内，不写 C 盘用户目录。
"""

from .runner import run_watch

__all__ = ["run_watch"]
