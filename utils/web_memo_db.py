import json
import os
import re
import sqlite3
from io import BytesIO
from datetime import datetime
from html import escape


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT_DIR, "data", "web_memos.db")
PALETTES_PATH = os.path.join(ROOT_DIR, "data", "color_palettes.md")
BACKUP_MD_PATH = os.path.join(ROOT_DIR, "data", "web_memos_backup.md")

DEFAULT_PALETTE = {
    "id": 0,
    "name": "默认色卡",
    "colors": ["#1B3A5C", "#4A90D9", "#E8F0FE"],
}

DEFAULT_TAGS = [
    "摘录",
    "观点",
    "待办",
    "写作素材",
    "工作记录",
    "工具想法",
    "金句",
    "行政日常",
    "学生工作",
    "竞赛",
]


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def has_local_memos():
    if not os.path.exists(DB_PATH):
        return False
    conn = None
    try:
        conn = get_connection()
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'web_memos'"
        ).fetchone()
        if not table:
            return False
        row = conn.execute("SELECT COUNT(*) AS total FROM web_memos").fetchone()
        return int(row["total"] or 0) > 0
    except sqlite3.Error:
        return False
    finally:
        if conn is not None:
            conn.close()


def init_db():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS web_memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memo_date TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '待整理',
            tags_json TEXT NOT NULL DEFAULT '[]',
            palette_id INTEGER NOT NULL DEFAULT 0,
            palette_name TEXT NOT NULL DEFAULT '',
            palette_colors_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    if get_memo_count() > 0:
        sync_backup_file()
    else:
        restore_from_markdown_backup()


def parse_palettes(text=None):
    if text is None:
        if not os.path.exists(PALETTES_PATH):
            return [DEFAULT_PALETTE]
        with open(PALETTES_PATH, "r", encoding="utf-8") as f:
            text = f.read()

    palettes = []
    blocks = re.split(r"(?=\n##\s*\d+)", "\n" + text)
    for block in blocks:
        title = re.search(r"\n##\s*(\d+)[、.．]?\s*(.+)", block)
        if not title:
            continue
        colors = re.findall(r"#[0-9A-Fa-f]{6}", block)
        if not colors:
            continue
        palettes.append(
            {
                "id": int(title.group(1)),
                "name": title.group(2).strip(),
                "colors": colors[:3],
            }
        )
    return palettes or [DEFAULT_PALETTE]


def pick_palette(index, palettes=None):
    palettes = palettes or parse_palettes()
    if not palettes:
        return DEFAULT_PALETTE
    return palettes[index % len(palettes)]


def split_tags(text):
    if not text:
        return []
    parts = re.split(r"[、,，\s]+", str(text))
    return normalize_tags(parts)


def normalize_tags(tags):
    normalized = []
    for tag in tags or []:
        tag = str(tag).strip()
        if tag and tag not in normalized:
            normalized.append(tag)
    return normalized


def merge_tags(*tag_groups, limit=8):
    merged = []
    for group in tag_groups:
        for tag in group or []:
            tag = str(tag).strip()
            if tag and tag not in merged:
                merged.append(tag)
    return merged[:limit]


def classify_content(content):
    text = content.strip()
    lowered = text.lower()
    tags = []

    if any(word in text for word in ["待办", "TODO", "todo", "记得", "跟进", "安排", "需要处理", "明天"]):
        category = "待办"
    elif any(word in text for word in ["段子", "哈哈", "笑死", "吐槽"]):
        category = "段子"
    elif any(word in text for word in ["金句", "一句", "格言", "警句"]) or text.startswith(("“", "\"")):
        category = "金句"
    elif any(word in lowered for word in ["ai", "llm", "chatgpt", "codex"]) or any(word in text for word in ["工具", "自动化", "模型", "页面", "功能"]):
        category = "工具想法"
    elif any(word in text for word in ["我觉得", "我认为", "本质", "原则", "判断", "思考", "复盘"]):
        category = "观点"
    elif any(word in text for word in ["通知", "新闻稿", "汇报", "讲话稿", "方案", "材料", "标题"]):
        category = "写作素材"
    elif any(word in text for word in ["会议", "流程", "学院", "行政", "课表", "报销", "预算"]):
        category = "工作记录"
    else:
        category = "摘录"

    keyword_tags = [
        ("会议", "会议"),
        ("行政", "行政日常"),
        ("汇报", "写作素材"),
        ("通知", "写作素材"),
        ("新闻稿", "写作素材"),
        ("写作", "写作素材"),
        ("沟通", "沟通"),
        ("AI", "AI"),
        ("ai", "AI"),
        ("工具", "工具想法"),
        ("自动化", "工具想法"),
        ("学生", "学生工作"),
        ("竞赛", "竞赛"),
        ("预算", "预算管理"),
        ("报销", "预算管理"),
        ("课表", "教学协调"),
    ]
    for needle, tag in keyword_tags:
        if needle in content and tag not in tags:
            tags.append(tag)

    if category not in tags:
        tags.insert(0, category)

    return category, tags[:6]


def _record_from_row(row):
    item = dict(row)
    item["tags"] = json.loads(item.pop("tags_json") or "[]")
    item["palette_colors"] = json.loads(item.pop("palette_colors_json") or "[]")
    return item


def get_memo_count():
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) AS total FROM web_memos").fetchone()
    conn.close()
    return int(row["total"] or 0)


def add_memo(memo_date, content, classify=True, manual_tags=None):
    content = content.strip()
    if not content:
        raise ValueError("content cannot be empty")

    category, tags = classify_content(content) if classify else ("待整理", ["待整理"])
    tags = merge_tags(tags, manual_tags)
    palette = pick_palette(get_memo_count())
    colors = palette.get("colors") or DEFAULT_PALETTE["colors"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO web_memos
            (memo_date, content, category, tags_json, palette_id, palette_name, palette_colors_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(memo_date),
            content,
            category,
            json.dumps(tags, ensure_ascii=False),
            int(palette.get("id", 0)),
            str(palette.get("name", "")),
            json.dumps(colors[:3], ensure_ascii=False),
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    sync_backup_file()


def _insert_memo_record(record):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    palette = pick_palette(get_memo_count())
    colors = palette.get("colors") or DEFAULT_PALETTE["colors"]
    tags = record.get("tags") or []
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO web_memos
            (memo_date, content, category, tags_json, palette_id, palette_name, palette_colors_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(record.get("memo_date", "")),
            str(record.get("content", "")).strip(),
            str(record.get("category", "待整理") or "待整理"),
            json.dumps(tags, ensure_ascii=False),
            int(palette.get("id", 0)),
            str(record.get("palette_name") or palette.get("name", "")),
            json.dumps(colors[:3], ensure_ascii=False),
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()


def _memo_identity(record):
    return (
        str(record.get("memo_date", "")).strip(),
        str(record.get("content", "")).strip(),
    )


def import_memo_records(records):
    existing_keys = {_memo_identity(record) for record in get_memos()}
    inserted = 0
    for record in reversed(records or []):
        key = _memo_identity(record)
        if not key[0] or not key[1] or key in existing_keys:
            continue
        _insert_memo_record(record)
        existing_keys.add(key)
        inserted += 1
    if inserted:
        sync_backup_file()
    return inserted


def get_memos(category=None, keyword=None):
    conn = get_connection()
    conditions = []
    values = []
    if category and category != "全部":
        conditions.append("category = ?")
        values.append(category)
    if keyword:
        conditions.append("content LIKE ?")
        values.append(f"%{keyword}%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM web_memos {where} ORDER BY memo_date DESC, id DESC",
        values,
    ).fetchall()
    conn.close()
    return [_record_from_row(row) for row in rows]


def get_categories():
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT category FROM web_memos ORDER BY category").fetchall()
    conn.close()
    return [row["category"] for row in rows]


def get_all_tags():
    conn = get_connection()
    rows = conn.execute("SELECT tags_json FROM web_memos").fetchall()
    conn.close()
    tags = list(DEFAULT_TAGS)
    for row in rows:
        try:
            tags.extend(json.loads(row["tags_json"] or "[]"))
        except json.JSONDecodeError:
            continue
    return sorted(normalize_tags(tags))


def build_markdown_export(records):
    lines = ["# 灵感便签盒", ""]
    for record in records:
        tags = record.get("tags") or []
        tag_text = "、".join(tags) if tags else "无"
        lines.extend(
            [
                f"## {record.get('memo_date', '')}",
                "",
                str(record.get("content", "")).strip(),
                "",
                f"- 分类：{record.get('category', '待整理')}",
                f"- 标签：{tag_text}",
                f"- 色卡：{record.get('palette_name', '') or '默认色卡'}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def build_markdown_backup(records=None):
    records = get_memos() if records is None else records
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return "\n".join(
        [
            "# 灵感便签盒备份",
            "",
            f"- 生成时间：{generated_at}",
            f"- 记录数量：{len(records)}",
            "",
            build_markdown_export(records).strip(),
            "",
        ]
    )


def write_markdown_backup(records=None, path=None):
    path = BACKUP_MD_PATH if path is None else path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as backup_file:
        backup_file.write(build_markdown_backup(records))
    return path


def sync_backup_file():
    write_markdown_backup(get_memos())
    return BACKUP_MD_PATH


def parse_markdown_backup(text):
    records = []
    chunks = re.split(r"\n##\s+", "\n" + text)
    for chunk in chunks[1:]:
        lines = chunk.splitlines()
        if not lines:
            continue
        memo_date = lines[0].strip()
        content_lines = []
        category = "待整理"
        tags = []
        palette_name = ""
        for line in lines[1:]:
            if line.startswith("- 分类："):
                category = line.replace("- 分类：", "", 1).strip() or "待整理"
            elif line.startswith("- 标签："):
                tag_text = line.replace("- 标签：", "", 1).strip()
                tags = [] if tag_text == "无" else [tag.strip() for tag in tag_text.split("、") if tag.strip()]
            elif line.startswith("- 色卡："):
                palette_name = line.replace("- 色卡：", "", 1).strip()
            elif not line.startswith("- "):
                content_lines.append(line)
        content = "\n".join(content_lines).strip()
        if memo_date and content:
            records.append(
                {
                    "memo_date": memo_date,
                    "content": content,
                    "category": category,
                    "tags": tags,
                    "palette_name": palette_name,
                }
            )
    return records


def restore_from_markdown_backup(path=None):
    path = BACKUP_MD_PATH if path is None else path
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as backup_file:
        records = parse_markdown_backup(backup_file.read())
    for record in reversed(records):
        _insert_memo_record(record)
    return len(records)


def has_markdown_backup_records(path=None):
    path = BACKUP_MD_PATH if path is None else path
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as backup_file:
        return bool(parse_markdown_backup(backup_file.read()))


def _normalize_palette_colors(record):
    colors = record.get("palette_colors") or DEFAULT_PALETTE["colors"]
    colors = list(colors)
    while len(colors) < 3:
        colors.append(colors[-1])
    return colors[:3]


def build_memo_card_html(record):
    main, accent, bg = _normalize_palette_colors(record)
    tags = record.get("tags") or []
    tag_html = "".join(
        f'<span class="memo-tag {"memo-tag-main" if i == 0 else ""}">{escape(str(tag))}</span>'
        for i, tag in enumerate(tags)
    )
    bg_style = f"linear-gradient(135deg, {bg} 0%, #ffffff 78%)"
    return f"""
    <article class="memo-card" style="--main:{main};--accent:{accent};--accent-soft:{accent}33;background:{bg_style};">
      <div class="memo-card-top">
        <div class="memo-date">{escape(record.get("memo_date", ""))}</div>
        <div class="memo-palette">{escape(record.get("palette_name", "") or "默认色卡")}</div>
      </div>
      <div class="memo-content">{escape(record.get("content", ""))}</div>
      <div class="memo-tags">{tag_html}</div>
    </article>
    """


def build_memo_cards_html(records):
    columns = _split_records_into_columns(records, 3)
    column_html = "".join(
        '<div class="memo-card-column">'
        + "".join(build_memo_card_html(record) for record in column)
        + "</div>"
        for column in columns
    )
    return f"""
    <style>
    body {{
        margin: 0;
        font-family: "Microsoft YaHei", Arial, sans-serif;
        color: #182230;
    }}
    .memo-card-grid {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        column-gap: .82rem;
        align-items: start;
    }}
    .memo-card-column {{
        display: flex;
        flex-direction: column;
        gap: .82rem;
    }}
    .memo-card {{
        position: relative;
        width: 100%;
        box-sizing: border-box;
        min-height: 168px;
        padding: .95rem .95rem .85rem 1.08rem;
        margin: 0;
        border: 1px solid rgba(24,34,48,.1);
        border-radius: 8px;
        box-shadow: 0 10px 24px rgba(24,34,48,.055);
        overflow: hidden;
    }}
    .memo-card::before {{
        content: "";
        position: absolute;
        inset: 0 auto 0 0;
        width: 6px;
        background: linear-gradient(180deg, var(--main), var(--accent));
    }}
    .memo-card::after {{
        content: "";
        position: absolute;
        right: -24px;
        top: -24px;
        width: 86px;
        height: 86px;
        border-radius: 50%;
        background: var(--accent-soft);
    }}
    .memo-card-top {{
        position: relative;
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: .6rem;
        margin-bottom: .7rem;
    }}
    .memo-date {{
        color: var(--main);
        font-size: .82rem;
        font-weight: 800;
        line-height: 1.35;
    }}
    .memo-palette {{
        font-size: .72rem;
        color: #667085;
        background: rgba(255,255,255,.75);
        border: 1px solid rgba(24,34,48,.08);
        border-radius: 999px;
        padding: .22rem .5rem;
    }}
    .memo-content {{
        position: relative;
        color: #182230;
        font-size: .94rem;
        line-height: 1.72;
        white-space: pre-wrap;
    }}
    .memo-tags {{
        position: relative;
        margin-top: .75rem;
        display: flex;
        gap: .38rem;
        flex-wrap: wrap;
    }}
    .memo-tag {{
        font-size: .74rem;
        background: rgba(255,255,255,.78);
        color: #344054;
        border: 1px solid rgba(24,34,48,.08);
        border-radius: 999px;
        padding: .16rem .48rem;
    }}
    .memo-tag-main {{
        color: var(--main);
        font-weight: 700;
    }}
    @media (max-width: 980px) {{
        .memo-card-grid {{
            grid-template-columns: 1fr;
        }}
    }}
    </style>
    <div class="memo-card-grid">{column_html}</div>
    """


def estimate_memo_cards_height(records):
    columns = _split_records_into_columns(records, 3)
    tallest_column = max(
        (sum(_estimate_memo_card_height(record) for record in column) + max(0, len(column) - 1) * 14)
        for column in columns
    )
    return min(2400, max(260, tallest_column + 34))


def _split_records_into_columns(records, column_count):
    columns = [[] for _ in range(column_count)]
    for index, record in enumerate(records):
        columns[index % column_count].append(record)
    return columns


def _estimate_memo_card_height(record):
    content = str(record.get("content", ""))
    visual_lines = 0
    for line in content.splitlines() or [""]:
        visual_lines += max(1, (len(line) + 17) // 18)
    tag_rows = 1 if record.get("tags") else 0
    return 122 + visual_lines * 28 + tag_rows * 30


def build_printable_html(records):
    blocks = []
    for record in records:
        tags = "、".join(record.get("tags") or [])
        blocks.append(
            f"""
            <article>
              <div class="date">{record.get('memo_date', '')}</div>
              <p>{_escape_html(record.get('content', ''))}</p>
              <div class="meta">分类：{_escape_html(record.get('category', '待整理'))} ｜ 标签：{_escape_html(tags)}</div>
            </article>
            """
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>灵感便签盒导出</title>
<style>
body {{ font-family: "Microsoft YaHei", Arial, sans-serif; color: #182230; line-height: 1.7; margin: 42px; }}
h1 {{ font-size: 28px; }}
article {{ break-inside: avoid; border-bottom: 1px solid #e5e7eb; padding: 18px 0; }}
.date {{ font-weight: 700; color: #1B3A5C; }}
.meta {{ color: #667085; font-size: 13px; }}
@media print {{ body {{ margin: 22mm; }} }}
</style>
</head>
<body>
<h1>灵感便签盒</h1>
{''.join(blocks)}
</body>
</html>"""


def build_pdf_export(records):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    font_name = _register_pdf_font()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "MemoTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=20,
        leading=26,
        spaceAfter=10,
    )
    date_style = ParagraphStyle(
        "MemoDate",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=18,
        textColor="#1B3A5C",
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "MemoBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=18,
        spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "MemoMeta",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9,
        leading=14,
        textColor="#667085",
        spaceAfter=8,
    )

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    story = [Paragraph("灵感便签盒", title_style), Spacer(1, 4)]
    for record in records:
        tags = "、".join(record.get("tags") or [])
        story.append(Paragraph(_escape_html(record.get("memo_date", "")), date_style))
        story.append(Paragraph(_escape_html(record.get("content", "")).replace("\n", "<br/>"), body_style))
        story.append(
            Paragraph(
                _escape_html(
                    f"分类：{record.get('category', '待整理')} ｜ 标签：{tags} ｜ 色卡：{record.get('palette_name', '') or '默认色卡'}"
                ),
                meta_style,
            )
        )
    doc.build(story)
    return buffer.getvalue()


def _register_pdf_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            font_name = "MemoChineseFont"
            if font_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(font_name, path))
            return font_name
    return "Helvetica"


def _escape_html(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
