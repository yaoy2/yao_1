import json
import os
import re
import sqlite3
from io import BytesIO
from datetime import datetime


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT_DIR, "data", "web_memos.db")
PALETTES_PATH = os.path.join(ROOT_DIR, "data", "color_palettes.md")

DEFAULT_PALETTE = {
    "id": 0,
    "name": "默认色卡",
    "colors": ["#1B3A5C", "#4A90D9", "#E8F0FE"],
}


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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


def classify_content(content):
    text = content.strip()
    lowered = text.lower()
    tags = []

    if any(word in text for word in ["段子", "哈哈", "笑死", "吐槽"]):
        category = "段子"
    elif any(word in text for word in ["金句", "一句", "格言", "警句"]) or text.startswith(("“", "\"")):
        category = "金句"
    elif any(word in lowered for word in ["ai", "llm", "chatgpt", "codex"]) or any(word in text for word in ["工具", "自动化", "模型"]):
        category = "观点"
    else:
        category = "摘录"

    keyword_tags = [
        ("会议", "会议"),
        ("行政", "行政日常"),
        ("汇报", "汇报素材"),
        ("写作", "写作素材"),
        ("沟通", "沟通"),
        ("AI", "AI"),
        ("ai", "AI"),
        ("工具", "工具建设"),
        ("学生", "学生工作"),
        ("竞赛", "竞赛"),
    ]
    for needle, tag in keyword_tags:
        if needle in content and tag not in tags:
            tags.append(tag)

    if category not in tags:
        tags.insert(0, category)

    return category, tags[:5]


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


def add_memo(memo_date, content, classify=True):
    content = content.strip()
    if not content:
        raise ValueError("content cannot be empty")

    category, tags = classify_content(content) if classify else ("待整理", ["待整理"])
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
