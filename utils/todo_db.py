import os
import re
import sqlite3
from datetime import date, datetime, timedelta


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT_DIR, "data", "todos.db")
BACKUP_MD_PATH = os.path.join(ROOT_DIR, "data", "todo_items_backup.md")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS todo_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            record_date TEXT NOT NULL,
            due_date TEXT NOT NULL DEFAULT '',
            due_time TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            is_archived INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    should_restore = _count_records(conn) == 0 and os.path.exists(BACKUP_MD_PATH)
    migration_version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    if should_restore:
        restore_from_markdown_backup()
    if migration_version < 1:
        split_multiline_todos()
        conn = get_connection()
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()
    sync_backup_file()


def _count_records(conn):
    row = conn.execute("SELECT COUNT(*) AS total FROM todo_items").fetchone()
    return int(row["total"] or 0)


def has_local_todos():
    if not os.path.exists(DB_PATH):
        return False
    conn = None
    try:
        conn = get_connection()
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'todo_items'"
        ).fetchone()
        if not table:
            return False
        return _count_records(conn) > 0
    except sqlite3.Error:
        return False
    finally:
        if conn is not None:
            conn.close()


def add_todo(content, record_date=None, due_date=None, due_time=None):
    content = str(content or "").strip()
    if not content:
        raise ValueError("content cannot be empty")

    today = date.today()
    extracted_date, extracted_time = extract_due_fields(content, today)
    record_date = str(record_date or today.isoformat())
    due_date = _normalize_date_text(due_date) or extracted_date
    due_time = _normalize_time_text(due_time) or extracted_time
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO todo_items
            (content, record_date, due_date, due_time, status, is_archived, completed_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'pending', 0, '', ?, ?)
        """,
        (content, record_date, due_date, due_time, now, now),
    )
    conn.commit()
    record_id = cur.lastrowid
    conn.close()
    sync_backup_file()
    return record_id


def add_todos_from_text(content, record_date=None, due_date=None, due_time=None):
    items = split_todo_text(content)
    if not items:
        raise ValueError("content cannot be empty")
    return [add_todo(item, record_date=record_date, due_date=due_date, due_time=due_time) for item in items]


def split_todo_text(content):
    items = []
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lstrip("#").strip() in {"今日重点待办", "待办", "待办清单"}:
            continue
        line = re.sub(r"^[-*•]\s+", "", line)
        line = re.sub(r"^\d+[.)、]\s*", "", line)
        line = re.sub(r"^\[[ xX]\]\s*", "", line)
        line = line.strip()
        if line and line not in items:
            items.append(line)
    return items


def split_multiline_todos():
    records = get_todos(view="all")
    changed = 0
    for record in records:
        if record.get("is_archived"):
            continue
        content = str(record.get("content") or "")
        items = split_todo_text(content)
        if len(items) <= 1:
            continue
        for item in items:
            _insert_todo_record(
                {
                    "content": item,
                    "record_date": record.get("record_date"),
                    "due_date": record.get("due_date"),
                    "due_time": record.get("due_time"),
                    "status": record.get("status") or "pending",
                    "is_archived": bool(record.get("is_archived")),
                    "completed_at": record.get("completed_at") or "",
                    "created_at": record.get("created_at"),
                    "updated_at": record.get("updated_at"),
                }
            )
        archive_todo(record["id"])
        changed += 1
    return changed


def update_todo(record_id, content=None, due_date=None, due_time=None):
    fields = []
    values = []
    if content is not None:
        content = str(content).strip()
        if not content:
            raise ValueError("content cannot be empty")
        fields.append("content = ?")
        values.append(content)
    if due_date is not None:
        fields.append("due_date = ?")
        values.append(_normalize_date_text(due_date))
    if due_time is not None:
        fields.append("due_time = ?")
        values.append(_normalize_time_text(due_time))
    if not fields:
        return 0
    fields.append("updated_at = ?")
    values.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    values.append(record_id)

    conn = get_connection()
    cur = conn.execute(f"UPDATE todo_items SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    changed = cur.rowcount
    conn.close()
    if changed:
        sync_backup_file()
    return changed


def complete_todo(record_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cur = conn.execute(
        """
        UPDATE todo_items
        SET status = 'done', is_archived = 1, completed_at = ?, updated_at = ?
        WHERE id = ? AND status != 'done'
        """,
        (now, now, record_id),
    )
    conn.commit()
    changed = cur.rowcount
    conn.close()
    if changed:
        sync_backup_file()
    return changed


def archive_todo(record_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cur = conn.execute(
        """
        UPDATE todo_items
        SET is_archived = 1, updated_at = ?
        WHERE id = ?
        """,
        (now, record_id),
    )
    conn.commit()
    changed = cur.rowcount
    conn.close()
    if changed:
        sync_backup_file()
    return changed


def delete_todo(record_id):
    conn = get_connection()
    cur = conn.execute("DELETE FROM todo_items WHERE id = ?", (record_id,))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    if changed:
        sync_backup_file()
    return changed


def reopen_todo(record_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cur = conn.execute(
        """
        UPDATE todo_items
        SET status = 'pending', is_archived = 0, completed_at = '', updated_at = ?
        WHERE id = ?
        """,
        (now, record_id),
    )
    conn.commit()
    changed = cur.rowcount
    conn.close()
    if changed:
        sync_backup_file()
    return changed


def get_todos(keyword=None, view="active"):
    conn = get_connection()
    conditions = []
    values = []
    if view == "active":
        conditions.append("is_archived = 0")
    elif view == "archived":
        conditions.append("is_archived = 1")
    elif view == "list":
        conditions.append("(is_archived = 0 OR status = 'done')")
    elif view != "all":
        raise ValueError("view must be active, archived, all, or list")

    keyword = str(keyword or "").strip()
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            "(content LIKE ? OR record_date LIKE ? OR due_date LIKE ? OR due_time LIKE ? OR status LIKE ?)"
        )
        values.extend([like, like, like, like, like])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""
        SELECT * FROM todo_items
        {where}
        ORDER BY is_archived ASC, datetime(created_at) DESC, id DESC
        """,
        values,
    ).fetchall()
    conn.close()
    return [_record_from_row(row) for row in rows]


def _record_from_row(row):
    item = dict(row)
    item["is_archived"] = bool(item.get("is_archived", 0))
    return item


def extract_due_fields(text, base_date=None):
    base_date = base_date or date.today()
    text = str(text or "")
    due_date = _extract_due_date(text, base_date)
    due_time = _extract_due_time(text)
    return due_date, due_time


def _extract_due_date(text, base_date):
    absolute = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", text)
    if absolute:
        return _safe_date(int(absolute.group(1)), int(absolute.group(2)), int(absolute.group(3)))

    month_day = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})日?", text)
    if month_day:
        month = int(month_day.group(1))
        day = int(month_day.group(2))
        year = base_date.year
        parsed = _date_or_none(year, month, day)
        if parsed and parsed < base_date:
            parsed = _date_or_none(year + 1, month, day)
        return parsed.isoformat() if parsed else ""

    relative_days = {
        "今天": 0,
        "明天": 1,
        "后天": 2,
        "大后天": 3,
    }
    for word, offset in relative_days.items():
        if word in text:
            return (base_date + timedelta(days=offset)).isoformat()

    weekday_match = re.search(r"(下周|本周|这周|周|星期)([一二三四五六日天])", text)
    if weekday_match:
        prefix = weekday_match.group(1)
        target = "一二三四五六日天".index(weekday_match.group(2))
        if target == 7:
            target = 6
        current = base_date.weekday()
        delta = target - current
        if prefix == "下周":
            delta += 7
            if delta <= 0:
                delta += 7
        elif delta < 0:
            delta += 7
        return (base_date + timedelta(days=delta)).isoformat()

    return ""


def _extract_due_time(text):
    colon = re.search(r"(?<!\d)([01]?\d|2[0-3])[:：]([0-5]\d)(?!\d)", text)
    if colon:
        return f"{int(colon.group(1)):02d}:{int(colon.group(2)):02d}"

    chinese = re.search(r"(上午|早上|下午|晚上|中午)?\s*(\d{1,2})\s*点\s*(半|[0-5]?\d分?)?", text)
    if not chinese:
        return ""
    period = chinese.group(1) or ""
    hour = int(chinese.group(2))
    minute_text = chinese.group(3) or ""
    minute = 30 if minute_text == "半" else int(re.sub(r"\D", "", minute_text) or 0)
    if period in ("下午", "晚上") and hour < 12:
        hour += 12
    if period == "中午" and hour < 11:
        hour += 12
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"
    return ""


def _safe_date(year, month, day):
    parsed = _date_or_none(year, month, day)
    return parsed.isoformat() if parsed else ""


def _date_or_none(year, month, day):
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _normalize_date_text(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return ""
    parsed = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    if not parsed:
        return text
    return _safe_date(int(parsed.group(1)), int(parsed.group(2)), int(parsed.group(3)))


def _normalize_time_text(value):
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    text = str(value).strip()
    if not text:
        return ""
    matched = re.match(r"^(\d{1,2})[:：](\d{1,2})$", text)
    if not matched:
        return text
    hour = int(matched.group(1))
    minute = int(matched.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"
    return ""


def build_markdown_backup(records=None):
    records = get_todos(view="all") if records is None else records
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 待办清单备份",
        "",
        f"- 生成时间：{generated_at}",
        f"- 记录数量：{len(records)}",
        "",
    ]
    for record in records:
        lines.extend(
            [
                f"## TODO-{int(record.get('id') or 0)}",
                "",
                f"- 发布日期：{record.get('record_date', '')}",
                f"- 截止日期：{record.get('due_date', '')}",
                f"- 截止时间：{record.get('due_time', '')}",
                f"- 状态：{record.get('status', 'pending')}",
                f"- 归档：{'是' if record.get('is_archived') else '否'}",
                f"- 完成时间：{record.get('completed_at', '')}",
                f"- 创建时间：{record.get('created_at', '')}",
                f"- 更新时间：{record.get('updated_at', '')}",
                "",
                "### 内容",
                "",
                str(record.get("content", "")).strip(),
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def write_markdown_backup(records=None, path=None):
    path = BACKUP_MD_PATH if path is None else path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as backup_file:
        backup_file.write(build_markdown_backup(records))
    return path


def sync_backup_file():
    return write_markdown_backup(get_todos(view="all"))


def parse_markdown_backup(text):
    records = []
    chunks = re.split(r"\n## TODO-", "\n" + str(text or ""))
    for chunk in chunks[1:]:
        lines = chunk.splitlines()
        if not lines:
            continue
        record_id = _coerce_int(lines[0].strip())
        meta = {
            "id": record_id,
            "record_date": "",
            "due_date": "",
            "due_time": "",
            "status": "pending",
            "is_archived": False,
            "completed_at": "",
            "created_at": "",
            "updated_at": "",
            "content": "",
        }
        content_lines = []
        in_content = False
        for line in lines[1:]:
            if line.strip() == "### 内容":
                in_content = True
                continue
            if in_content:
                content_lines.append(line)
                continue
            _read_backup_meta_line(meta, line)
        meta["content"] = "\n".join(content_lines).strip()
        if meta["content"] and meta["record_date"]:
            records.append(meta)
    return records


def _read_backup_meta_line(meta, line):
    fields = {
        "- 发布日期：": "record_date",
        "- 截止日期：": "due_date",
        "- 截止时间：": "due_time",
        "- 状态：": "status",
        "- 完成时间：": "completed_at",
        "- 创建时间：": "created_at",
        "- 更新时间：": "updated_at",
    }
    for prefix, key in fields.items():
        if line.startswith(prefix):
            meta[key] = line.replace(prefix, "", 1).strip()
            return
    if line.startswith("- 归档："):
        meta["is_archived"] = line.replace("- 归档：", "", 1).strip() == "是"


def restore_from_markdown_backup(path=None):
    path = BACKUP_MD_PATH if path is None else path
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as backup_file:
        records = parse_markdown_backup(backup_file.read())
    return import_todo_records(records, write_backup=False)


def has_markdown_backup_records(path=None):
    path = BACKUP_MD_PATH if path is None else path
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as backup_file:
        return bool(parse_markdown_backup(backup_file.read()))


def import_todo_records(records, write_backup=True):
    existing = set()
    for record in get_todos(view="all"):
        existing.update(_todo_identities(record))
    inserted = 0
    for record in reversed(records or []):
        identities = _todo_identities(record)
        if not identities or existing.intersection(identities):
            continue
        _insert_todo_record(record)
        existing.update(identities)
        inserted += 1
    if inserted and write_backup:
        sync_backup_file()
    return inserted


def _insert_todo_record(record):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = str(record.get("status") or "pending")
    is_archived = bool(record.get("is_archived") or status == "done")
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO todo_items
            (content, record_date, due_date, due_time, status, is_archived, completed_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(record.get("content", "")).strip(),
            str(record.get("record_date") or date.today().isoformat()),
            _normalize_date_text(record.get("due_date")),
            _normalize_time_text(record.get("due_time")),
            status,
            1 if is_archived else 0,
            str(record.get("completed_at") or ""),
            str(record.get("created_at") or now),
            str(record.get("updated_at") or now),
        ),
    )
    conn.commit()
    conn.close()


def _todo_identities(record):
    identities = set()
    record_id = _coerce_int(record.get("id"))
    if record_id:
        identities.add(("id", record_id))
    content_key = (
        str(record.get("record_date", "")).strip(),
        _normalize_content(record.get("content", "")),
    )
    if content_key[0] and content_key[1]:
        identities.add(content_key)
    return identities


def _normalize_content(content):
    return re.sub(r"\s+", "", str(content or ""))


def _coerce_int(value):
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0
