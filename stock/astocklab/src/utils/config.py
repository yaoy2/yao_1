from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class StockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    exchange: str
    full_code: str
    name: str
    benchmark_code: str
    benchmark_name: str
    benchmark_codes: list[str] = Field(default_factory=list)
    enabled: bool = True


class BenchmarkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    exchange: str
    full_code: str
    name: str
    role: str
    enabled: bool = True


class WatchlistConfig(BaseModel):
    timezone: str
    benchmarks: list[BenchmarkConfig] = Field(default_factory=list)
    stocks: list[StockConfig]

    def enabled_benchmarks_for(self, stock: StockConfig) -> list[BenchmarkConfig]:
        """Return enabled benchmarks configured for one stock."""
        requested = set(stock.benchmark_codes or [stock.benchmark_code])
        return [item for item in self.benchmarks if item.enabled and item.code in requested]


class AIChainNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    stage: str
    industry: str
    subindustry: str
    field: str
    direction: str
    order: int
    name: str
    source_name: str
    source_code: str
    description: str
    enabled: bool = True


class AIChainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str
    history_start: str
    profile_refresh_limit: int = 500
    stock_history_refresh_limit: int = 60
    stock_minute_refresh_limit: int = 20
    constituent_page_limit: int = 5
    nodes: list[AIChainNodeConfig]


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a UTF-8 YAML file and require a mapping at the root."""
    with path.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle)
    if not isinstance(content, dict):
        raise ValueError(f"配置文件根节点必须是字典: {path}")
    return content


def load_watchlist() -> WatchlistConfig:
    """Load and validate the stock watchlist."""
    return WatchlistConfig.model_validate(load_yaml(PROJECT_ROOT / "config" / "watchlist.yaml"))


def load_settings() -> dict[str, Any]:
    """Load settings and resolve configured paths under the project root."""
    settings = load_yaml(PROJECT_ROOT / "config" / "settings.yaml")
    resolved = dict(settings)
    resolved["resolved_paths"] = {
        key: (PROJECT_ROOT / value).resolve()
        for key, value in settings["paths"].items()
    }
    for path in resolved["resolved_paths"].values():
        if PROJECT_ROOT not in path.parents and path != PROJECT_ROOT:
            raise ValueError(f"配置路径超出项目目录: {path}")
    return resolved


def load_ai_chain() -> AIChainConfig:
    """Load and validate the curated A-share AI industry chain."""
    config = AIChainConfig.model_validate(
        load_yaml(PROJECT_ROOT / "config" / "ai_industry_chain.yaml")
    )
    node_ids = [node.node_id for node in config.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("AI产业链节点ID存在重复。")
    allowed_stages = {
        "upstream", "midstream", "downstream", "application"
    }
    invalid = sorted({
        node.stage for node in config.nodes if node.stage not in allowed_stages
    })
    if invalid:
        raise ValueError(f"AI产业链存在无效阶段: {invalid}")
    return config
