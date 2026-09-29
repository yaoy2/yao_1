"""Read-only monthly calendar markup for the existing todo records."""

import calendar
import re
from collections import defaultdict
from datetime import date, datetime
from html import escape


CALENDAR_CSS = """
<style>
.todo-calendar { color: var(--colors-ink, #1d1d1f); font-size: .82rem; }
.todo-calendar-scroll { overflow-x: auto; }
.todo-calendar-grid {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    min-width: 560px;
    gap: 1px;
    border: 1px solid var(--colors-hairline, #e0e0e0);
    border-radius: 8px;
    overflow: hidden;
    background: var(--colors-hairline, #e0e0e0);
}
.todo-calendar-weekday {
    padding: .3rem;
    text-align: center;
    color: var(--colors-ink-muted-48, #6e6e73);
    background: var(--colors-canvas-parchment, #f5f5f7);
}
.todo-calendar-day {
    min-width: 0;
    min-height: 66px;
    padding: .3rem;
    background: var(--colors-canvas, #fff);
}
.todo-calendar-day.empty { background: var(--colors-surface-pearl, #fafafc); }
.todo-calendar-day.today { box-shadow: inset 0 0 0 1px var(--colors-primary, #0066cc); }
.todo-calendar-date { display: block; padding: 0 .2rem .15rem; font-size: .75rem; }
.todo-calendar-day.today .todo-calendar-date { color: var(--colors-primary, #0066cc); font-weight: 600; }
.todo-calendar .todo-calendar-task { margin: .15rem 0 0; }
.todo-calendar .todo-calendar-task > summary {
    display: block;
    padding: .22rem .3rem;
    border-radius: 4px;
    background: var(--colors-primary-soft, #eef5fc);
    color: var(--colors-primary, #0066cc);
    cursor: pointer;
    list-style: none;
    line-height: 1.4;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.todo-calendar .todo-calendar-task > summary::-webkit-details-marker { display: none; }
.todo-calendar .todo-calendar-task.done > summary {
    background: var(--colors-canvas-parchment, #f5f5f7);
    color: var(--colors-ink-muted-48, #6e6e73);
}
.todo-calendar .todo-calendar-task.done .todo-calendar-name { text-decoration: line-through; }
.todo-calendar summary:focus-visible { outline: 2px solid var(--colors-primary, #0066cc); outline-offset: -2px; }
.todo-calendar .todo-calendar-task[open] > summary { white-space: normal; overflow-wrap: anywhere; }
.todo-calendar-detail {
    padding: .4rem .3rem;
    max-height: 240px;
    overflow: auto;
    overflow-wrap: anywhere;
    line-height: 1.5;
    border-bottom: 1px solid var(--colors-hairline, #e0e0e0);
}
.todo-calendar-content { white-space: pre-wrap; margin-bottom: .35rem; }
.todo-calendar-meta { color: var(--colors-ink-muted-48, #6e6e73); font-size: .75rem; }
.todo-calendar-undated { margin-top: .5rem; }
.todo-calendar-undated > summary { cursor: pointer; color: var(--colors-ink-muted-48, #6e6e73); }
.todo-calendar-undated-items { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .35rem; }
</style>
"""


def shift_month(month, offset):
    """Return the first day of the month, including across year boundaries."""
    year, month_index = divmod(month.year * 12 + month.month - 1 + offset, 12)
    return date(year, month_index + 1, 1)


def calendar_title(content, limit=14):
    """Shorten the display label only; the detail retains the original content."""
    text = " ".join(str(content or "").split())
    without_date = re.sub(
        r"^(?:(?:\d{4}年)?\d{1,2}月\d{1,2}[日号]|"
        r"(?:\d{4}[-/.])?\d{1,2}[-/.]\d{1,2}|今天|明天|后天)(?:之前|以前|前)?[，,：:\s]*",
        "",
        text,
    )
    text = without_date or text or "未命名待办"
    return text if len(text) <= limit else text[:limit] + "…"


def _due_date(value):
    try:
        return datetime.strptime(str(value or ""), "%Y-%m-%d").date()
    except ValueError:
        return None


def _task_html(record):
    content = str(record.get("content") or "")
    done = record.get("status") == "done"
    status = "已完成" if done else "未完成"
    title = escape(calendar_title(content))
    name = f'<s class="todo-calendar-name">{title}</s>' if done else f'<span class="todo-calendar-name">{title}</span>'
    due = " ".join(str(record.get(key) or "").strip() for key in ("due_date", "due_time")).strip()
    metadata = [f"状态：{status}", f"截止：{due or '未设置'}"]
    if record.get("record_date"):
        metadata.append(f"发布日期：{record['record_date']}")
    if done and record.get("completed_at"):
        metadata.append(f"完成时间：{record['completed_at']}")
    meta_html = "".join(f"<div>{escape(value)}</div>" for value in metadata)
    task_class = "todo-calendar-task done" if done else "todo-calendar-task"
    return (
        f'<details class="{task_class}" name="todo-calendar-detail">'
        f'<summary title="{escape(content, quote=True)}" aria-label="查看详情：{escape(content, quote=True)}（{status}）">{name}</summary>'
        f'<div class="todo-calendar-detail"><div class="todo-calendar-content">{escape(content)}</div>'
        f'<div class="todo-calendar-meta">{meta_html}</div></div></details>'
    )


def render_calendar_html(records, month, *, today):
    """Render a calendar without changing records, files, or completion state."""
    by_date = defaultdict(list)
    undated = []
    for record in records:
        # Match the list view: completed tasks remain visible after archiving.
        if record.get("status") == "deleted" or (record.get("is_archived") and record.get("status") != "done"):
            continue
        due = _due_date(record.get("due_date"))
        if due is None:
            undated.append(record)
        else:
            by_date[due].append(record)

    parts = [CALENDAR_CSS, '<div class="todo-calendar"><div class="todo-calendar-scroll">',
             f'<div class="todo-calendar-grid" aria-label="{month.year}年{month.month}月任务日历">']
    parts.extend(f'<div class="todo-calendar-weekday">周{day}</div>' for day in "一二三四五六日")
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(month.year, month.month):
        for day in week:
            if not day:
                parts.append('<div class="todo-calendar-day empty" aria-hidden="true"></div>')
                continue
            day_date = date(month.year, month.month, day)
            classes = "todo-calendar-day today" if day_date == today else "todo-calendar-day"
            day_label = f"{day} · 今天" if day_date == today else str(day)
            parts.append(f'<div class="{classes}" data-date="{day_date.isoformat()}"><time class="todo-calendar-date" datetime="{day_date.isoformat()}">{day_label}</time>')
            day_records = sorted(by_date.get(day_date, []), key=lambda item: (
                item.get("status") == "done", str(item.get("due_time") or "99:99")
            ))
            parts.extend(_task_html(record) for record in day_records)
            parts.append("</div>")
    parts.append("</div></div>")
    if undated:
        parts.append(f'<details class="todo-calendar-undated"><summary>未设有效截止日期（{len(undated)}）</summary><div class="todo-calendar-undated-items">')
        parts.extend(_task_html(record) for record in undated)
        parts.append("</div></details>")
    parts.append("</div>")
    return "".join(parts)
