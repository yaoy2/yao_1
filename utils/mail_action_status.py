"""Shared mail task states and their user-facing labels."""

STATUS_LABELS = {
    "needs_confirmation": "待确认",
    "pending": "需处理",
    "in_progress": "处理中",
    "done": "已处理",
    "no_action": "无需处理",
    "out_of_scope": "不属本人业务",
}

ALL_STATUSES = frozenset(STATUS_LABELS)
ACTIVE_STATUSES = frozenset({"needs_confirmation", "pending", "in_progress"})
ARCHIVED_STATUSES = frozenset({"done", "no_action", "out_of_scope"})
