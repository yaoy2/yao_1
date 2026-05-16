import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "budget.db")


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
    conn.commit()
    conn.close()


def add_record(record_date, category, unit, description, amount, status="未报销"):
    conn = get_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO expense_records (record_date, category, unit, description, amount, reimbursement_status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (record_date, category, unit, description, amount, status, now, now),
    )
    conn.commit()
    conn.close()


def update_record(record_id, record_date=None, category=None, unit=None, description=None, amount=None, status=None):
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


def set_status(record_id, status):
    update_record(record_id, status=status)


def get_all_records():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM expense_records ORDER BY record_date DESC, id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
        conditions.append("description LIKE ?")
        values.append(f"%{keyword}%")
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
