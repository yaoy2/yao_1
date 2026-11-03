"""Serializable preview and result types shared by the engine and desktop UI."""

from dataclasses import asdict, dataclass, field


STATUS_LABELS = {
    "ready": "可分发", "review": "待核对", "skip": "跳过",
    "duplicate": "内容重复", "collision": "同名冲突", "changed": "文件已变化",
    "moved": "已分发", "copied": "已补齐副本", "error": "失败", "ignored": "不在范围内",
}
MODE_LABELS = {"monthly": "月报分发", "weekly": "纪要考勤分发", "invoice": "发票归档"}
RULE_LABELS = {"minutes": "会议纪要", "attendance": "考勤记录", "monthly": "月报", "invoice": "发票"}
MODE_RULES = {"monthly": ("monthly",), "weekly": ("minutes", "attendance"), "invoice": ("invoice",)}


def selected_rules(selection) -> tuple[str, ...]:
    values = MODE_RULES.get(selection, (selection,)) if isinstance(selection, str) else tuple(selection)
    if not values or any(value not in RULE_LABELS for value in values):
        raise ValueError("请至少选择一项有效的分发规则")
    return tuple(key for key in RULE_LABELS if key in values)


@dataclass(frozen=True)
class Decision:
    status: str
    kind: str = ""
    period: str = ""
    department: str = ""
    relative_dir: str = ""
    reason: str = ""
    target_name: str = ""
    week_label: str = ""
    summary_relative_dir: str = ""


@dataclass
class PlanItem:
    name: str
    source: str
    destination: str = ""
    status: str = "review"
    kind: str = ""
    period: str = ""
    department: str = ""
    reason: str = ""
    sha256: str = ""
    size: int = 0
    mtime_ns: int = 0
    creation_time_ns: int = 0
    week_label: str = ""
    summary_destination: str = ""


@dataclass
class Plan:
    root: str
    mode: str
    created_at: str
    plan_id: str
    scanned_count: int = 0
    items: list[PlanItem] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    calendar_period: str = ""
    start_date: str = ""
    end_time: str = ""
    date_excluded_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutionResult:
    items: list[PlanItem]
    log_path: str

    @property
    def moved(self) -> int:
        return sum(item.status == "moved" for item in self.items)

    @property
    def copied(self) -> int:
        return sum(item.status == "copied" for item in self.items)


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    completed: int
    total: int
    message: str
    item: PlanItem | None = None
