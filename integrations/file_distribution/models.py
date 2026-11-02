"""Serializable preview and result types shared by the engine and desktop UI."""

from dataclasses import asdict, dataclass, field


STATUS_LABELS = {
    "ready": "可分发", "review": "待核对", "skip": "跳过",
    "duplicate": "内容重复", "collision": "同名冲突", "changed": "文件已变化",
    "moved": "已分发", "error": "失败", "ignored": "不在范围内",
}
MODE_LABELS = {"monthly": "月报分发", "weekly": "纪要考勤分发", "invoice": "发票归档"}


@dataclass(frozen=True)
class Decision:
    status: str
    kind: str = ""
    period: str = ""
    department: str = ""
    relative_dir: str = ""
    reason: str = ""


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


@dataclass
class Plan:
    root: str
    mode: str
    created_at: str
    plan_id: str
    scanned_count: int = 0
    items: list[PlanItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutionResult:
    items: list[PlanItem]
    log_path: str

    @property
    def moved(self) -> int:
        return sum(item.status == "moved" for item in self.items)
