import sqlite3
import os
from datetime import datetime
from openpyxl import Workbook

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "budget.db")
BACKUP_MD_PATH = os.path.join(os.path.dirname(DB_PATH), "budget_ledger_backup.md")
BACKUP_XLSX_PATH = os.path.join(os.path.dirname(DB_PATH), "budget_ledger_backup.xlsx")

BACKUP_COLUMNS = [
    ("id", "ID"),
    ("record_date", "日期"),
    ("category", "类别"),
    ("unit", "使用单位"),
    ("spender", "支出人"),
    ("description", "支出明细"),
    ("amount", "金额"),
    ("reimbursement_status", "报销状态"),
    ("created_at", "创建时间"),
    ("updated_at", "更新时间"),
]


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expense_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_date TEXT NOT NULL,
            category TEXT NOT NULL,
            unit TEXT NOT NULL DEFAULT '',
            spender TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            amount REAL NOT NULL,
            reimbursement_status TEXT NOT NULL DEFAULT '未报销',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    # migrate: add unit column if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(expense_records)").fetchall()]
    if "unit" not in cols:
        conn.execute("ALTER TABLE expense_records ADD COLUMN unit TEXT NOT NULL DEFAULT ''")
    if "spender" not in cols:
        conn.execute("ALTER TABLE expense_records ADD COLUMN spender TEXT NOT NULL DEFAULT ''")
    conn.commit()
    should_restore = _count_records(conn) == 0 and os.path.exists(BACKUP_MD_PATH)
    conn.close()
    if should_restore:
        restore_from_markdown_backup()
    sync_backup_files()


def add_record(record_date, category, unit, spender, description, amount, status="未报销"):
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO expense_records
            (record_date, category, unit, spender, description, amount, reimbursement_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (record_date, category, unit, spender, description, amount, status, now, now),
    )
    conn.commit()
    conn.close()
    sync_backup_files()


def update_record(record_id, record_date=None, category=None, unit=None, spender=None, description=None, amount=None, status=None):
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fields = []
    values = []
    if record_date is not None:
        fields.append("record_date = ?")
        values.append(record_date)
    if category is not None:
        fields.append("category = ?")
        values.append(category)
    if unit is not None:
        fields.append("unit = ?")
        values.append(unit)
    if spender is not None:
        fields.append("spender = ?")
        values.append(spender)
    if description is not None:
        fields.append("description = ?")
        values.append(description)
    if amount is not None:
        fields.append("amount = ?")
        values.append(amount)
    if status is not None:
        fields.append("reimbursement_status = ?")
        values.append(status)
    fields.append("updated_at = ?")
    values.append(now)
    values.append(record_id)
    conn.execute(f"UPDATE expense_records SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    sync_backup_files()


def set_status(record_id, status):
    update_record(record_id, status=status)


def get_all_records():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM expense_records ORDER BY record_date DESC, id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def replace_all_records(records):
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM expense_records")
        for record in records:
            amount = float(record["amount"])
            if amount <= 0:
                raise ValueError("amount must be greater than 0")
            created_at = record.get("created_at") or now
            updated_at = record.get("updated_at") or now
            conn.execute(
                """
                INSERT INTO expense_records
                    (record_date, category, unit, spender, description, amount, reimbursement_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record["record_date"]),
                    str(record["category"]),
                    str(record.get("unit", "")),
                    str(record.get("spender", "")),
                    str(record.get("description", "")),
                    amount,
                    str(record.get("reimbursement_status", "未报销")),
                    str(created_at),
                    str(updated_at),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    sync_backup_files()


def _count_records(conn):
    row = conn.execute("SELECT COUNT(*) AS total FROM expense_records").fetchone()
    return int(row["total"] if isinstance(row, sqlite3.Row) else row[0])


def _format_backup_value(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _escape_markdown_table_value(value):
    return _format_backup_value(value).replace("|", "\\|").replace("\n", " ")


def _fetch_backup_records():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM expense_records ORDER BY record_date DESC, id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def build_markdown_backup(records=None):
    records = _fetch_backup_records() if records is None else records
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    headers = [label for _, label in BACKUP_COLUMNS]
    lines = [
        "# 预算速记台账备份",
        "",
        f"- 生成时间：{generated_at}",
        f"- 记录数量：{len(records)}",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for record in records:
        values = [_escape_markdown_table_value(record.get(key, "")) for key, _ in BACKUP_COLUMNS]
        lines.append("| " + " | ".join(values) + " |")
    lines.append("")
    return "\n".join(lines)


def _split_markdown_table_row(line):
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    cells = []
    current = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def parse_markdown_backup(text):
    records = []
    label_to_key = {label: key for key, label in BACKUP_COLUMNS}
    headers = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = _split_markdown_table_row(stripped)
        if not headers:
            headers = cells
            continue
        row = dict(zip(headers, cells))
        if not row.get("日期") or not row.get("类别") or not row.get("金额"):
            continue
        record = {}
        for label, value in row.items():
            key = label_to_key.get(label)
            if key:
                record[key] = value
        try:
            record["amount"] = float(record.get("amount", 0))
        except (TypeError, ValueError):
            continue
        if record["amount"] <= 0:
            continue
        records.append(record)
    return records


def restore_from_markdown_backup(path=None):
    path = BACKUP_MD_PATH if path is None else path
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as backup_file:
        records = parse_markdown_backup(backup_file.read())
    if not records:
        return 0
    replace_all_records(records)
    return len(records)


def write_markdown_backup(records=None, path=None):
    path = BACKUP_MD_PATH if path is None else path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = build_markdown_backup(records)
    with open(path, "w", encoding="utf-8", newline="\n") as backup_file:
        backup_file.write(content)
    return path


def write_excel_backup(records=None, path=None):
    path = BACKUP_XLSX_PATH if path is None else path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    records = _fetch_backup_records() if records is None else records
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "预算流水"
    sheet.append([label for _, label in BACKUP_COLUMNS])
    for record in records:
        row = []
        for key, _ in BACKUP_COLUMNS:
            value = record.get(key, "")
            if key == "amount" and value not in ("", None):
                value = float(value)
            row.append(value)
        sheet.append(row)
    workbook.save(path)
    return path


def sync_backup_files():
    records = _fetch_backup_records()
    write_markdown_backup(records)
    write_excel_backup(records)
    return {"markdown": BACKUP_MD_PATH, "excel": BACKUP_XLSX_PATH}


def get_filtered_records(month=None, category=None, status=None, keyword=None):
    conn = get_connection()
    conditions = []
    values = []
    if month:
        conditions.append("strftime('%Y-%m', record_date) = ?")
        values.append(month)
    if category:
        conditions.append("category = ?")
        values.append(category)
    if status:
        conditions.append("reimbursement_status = ?")
        values.append(status)
    if keyword:
        conditions.append("(description LIKE ? OR spender LIKE ?)")
        values.extend([f"%{keyword}%", f"%{keyword}%"])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM expense_records {where} ORDER BY record_date DESC, id DESC", values
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_category_summary():
    conn = get_connection()
    rows = conn.execute("""
        SELECT category,
               SUM(CASE WHEN reimbursement_status = '已报销' THEN amount ELSE 0 END) as reimbursed,
               SUM(CASE WHEN reimbursement_status = '未报销' THEN amount ELSE 0 END) as unreimbursed
        FROM expense_records
        WHERE reimbursement_status != '作废'
        GROUP BY category
    """).fetchall()
    conn.close()
    return {r["category"]: {"reimbursed": r["reimbursed"], "unreimbursed": r["unreimbursed"]} for r in rows}


def get_total_summary():
    conn = get_connection()
    row = conn.execute("""
        SELECT
            SUM(CASE WHEN reimbursement_status = '已报销' THEN amount ELSE 0 END) as total_reimbursed,
            SUM(CASE WHEN reimbursement_status = '未报销' THEN amount ELSE 0 END) as total_unreimbursed
        FROM expense_records
    """).fetchone()
    conn.close()
    return {
        "total_reimbursed": row["total_reimbursed"] or 0,
        "total_unreimbursed": row["total_unreimbursed"] or 0,
    }


def get_unit_summary_by_category(category):
    conn = get_connection()
    rows = conn.execute("""
        SELECT unit,
               SUM(CASE WHEN reimbursement_status = '已报销' THEN amount ELSE 0 END) as reimbursed,
               SUM(CASE WHEN reimbursement_status = '未报销' THEN amount ELSE 0 END) as unreimbursed
        FROM expense_records
        WHERE category = ? AND reimbursement_status != '作废'
        GROUP BY unit
        ORDER BY (reimbursed + unreimbursed) DESC
    """, (category,)).fetchall()
    conn.close()
    return [
        {"unit": r["unit"], "reimbursed": r["reimbursed"], "unreimbursed": r["unreimbursed"]}
        for r in rows
    ]


def get_category_unit_pivot():
    conn = get_connection()
    rows = conn.execute("""
        SELECT category, unit,
               SUM(amount) as total
        FROM expense_records
        WHERE reimbursement_status != '作废'
        GROUP BY category, unit
    """).fetchall()
    conn.close()
    return {(r["category"], r["unit"]): r["total"] for r in rows}
