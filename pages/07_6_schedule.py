import html
import json
from pathlib import Path
from collections import defaultdict

import pandas as pd
import streamlit as st
from utils.ui_theme import render_home_link


st.set_page_config(page_title="课表查询-2026-2027-1", page_icon="📚", layout="wide")
render_home_link()

# ── 路径配置（相对于项目根目录）───────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

SCHEDULE_TERM = "2026-2027-1"
SCHEDULE_CACHE_PATH = DATA_DIR / "schedule_cache.json"
CATEGORY_CACHE_PATH = DATA_DIR / "teacher_category_cache.json"
SCHEDULE_METADATA_PATH = DATA_DIR / "schedule_metadata.json"

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五"]
PERIODS = list(range(1, 15))
CATEGORY_ORDER = ["医学信息工程系", "健康服务与管理系", "医学影像技术系", "院内其余老师"]
COUNCIL_MEMBERS = {
    "郭洋",
    "张勇",
    "杜萌泽",
    "许文博",
    "张朵",
    "姚雨廷",
    "周雨薇",
    "庞晨昕",
    "魏勇",
    "李娇阳",
    "高冬",
    "刘冬雪",
    "高静",
    "易文静",
    "龚雨晴",
    "智靖雅",
    "文海洋",
    "熊亮宇",
    "魏邦明",
    "刘宇鹏",
    "古彬",
}


# ── 缓存读取 ──────────────────────────────────────────────
def _load_cache(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── 本学期课表数据 ────────────────────────────────────────
def load_schedule_records() -> list[dict]:
    """仅读取已导入的本学期数据，避免旧 Excel 重新覆盖课表。"""
    cached = _load_cache(SCHEDULE_CACHE_PATH)
    if not isinstance(cached, list):
        return []
    return [rec for rec in cached if rec.get("term") == SCHEDULE_TERM]


def record_matches_filter(rec: dict, selected_filter: str) -> bool:
    if selected_filter == "全部教师":
        return True
    if selected_filter == "院务会":
        return any(t in COUNCIL_MEMBERS for t in rec["teachers"])
    return selected_filter in rec["teachers"]


def build_teacher_category_map(records: list[dict]) -> dict[str, str]:
    """沿用 M06 教师分组，未收录教师放入院内其余老师。"""
    cached = _load_cache(CATEGORY_CACHE_PATH) or {}
    return {teacher: cached.get(teacher, "院内其余老师") for rec in records for teacher in rec["teachers"]}


def build_period_grid(records: list[dict], selected_filter: str) -> dict[str, dict[int, list[dict]]]:
    grid: dict[str, dict[int, list[dict]]] = {d: {p: [] for p in PERIODS} for d in WEEKDAYS}
    for rec in records:
        if rec["weekday"] not in WEEKDAYS:
            continue
        if not record_matches_filter(rec, selected_filter):
            continue
        for p in range(rec["start_period"], rec["end_period"] + 1):
            if p in PERIODS:
                grid[rec["weekday"]][p].append(rec)
    return grid


def _card_html(rec: dict) -> str:
    teacher_full = html.escape(rec["teacher_label"])
    teacher_short = html.escape(rec["teacher_label"][:3])
    course = html.escape(rec["course"])
    cls = html.escape(rec["class_group"]) if rec["class_group"] else "未标注班级"
    room = html.escape(rec["classroom"]) if rec["classroom"] else "未标注教室"
    source = html.escape(rec["sheet"])
    period_text = f"第{rec['start_period']}-{rec['end_period']}节"
    weeks = html.escape(rec.get("week_text") or "原文未完整列出")
    teaching_type = html.escape(rec.get("teaching_type") or "未标注")
    source_note = "<div>原表信息已省略，未列出内容请核对教务课表。</div>" if rec.get("source_truncated") else ""
    return (
        "<div class='teacher-card'>"
        "<details>"
        "<summary class='teacher-summary'>"
        f"<div class='teacher-name'>{teacher_short}</div>"
        "</summary>"
        "<div class='teacher-detail'>"
        f"<div><span class='k'>教师</span> {teacher_full}</div>"
        f"<div><span class='k'>课程</span> {course}</div>"
        f"<div><span class='k'>节次</span> {period_text}</div>"
        f"<div><span class='k'>周次</span> {weeks}</div>"
        f"<div><span class='k'>类型</span> {teaching_type}</div>"
        f"<div><span class='k'>教室</span> {room}</div>"
        f"<div><span class='k'>班级</span> {cls}</div>"
        f"<div><span class='k'>来源</span> {source}</div>"
        f"{source_note}"
        "</div>"
        "</details>"
        "</div>"
    )


def render_grid(grid: dict[str, dict[int, list[dict]]], teacher_category_map: dict[str, str]) -> None:
    table_style = """
    <style>
        .tb-wrap {overflow-x:auto;}
        table.tb {border-collapse:collapse; width:100%; min-width:1200px; background:var(--colors-canvas);}
        .tb th, .tb td {border:1px solid var(--colors-hairline); vertical-align:top; padding:8px;}
        .tb th {background:var(--colors-canvas-parchment); font-weight: 600; color:var(--colors-ink);}
        .period-col {width:96px; min-width:96px; text-align:center; background:var(--colors-surface-pearl); font-weight: 600;}
        .period-time {margin-top:4px; font-size:11px; font-weight:400; line-height:1.35; color:var(--colors-ink-muted-80); white-space:nowrap; font-variant-numeric:tabular-nums;}
        .dept-grid {display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:6px;}
        .dept-col {min-width:0;}
        .teacher-card {display:block; width:100%; margin:4px 0; border:1px solid var(--colors-primary-soft); background:var(--colors-surface-pearl); border-radius:8px; font-size:12px;}
        .teacher-card details {display:block;}
        .teacher-summary {list-style:none; cursor:pointer; padding:6px 7px;}
        .teacher-summary::-webkit-details-marker {display:none;}
        .teacher-name {font-size:12px; font-weight: 600; color:var(--colors-primary); line-height:1.2; text-align:center; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
        .teacher-detail {font-size:11px; color:var(--colors-ink-muted-80); border-top:1px solid var(--colors-hairline); padding:6px 7px; line-height:1.4; word-break:break-all;}
        .teacher-detail .k {display:inline-block; min-width:28px; color:var(--colors-ink-muted-48);}
        @media (max-width: 1280px) {.dept-grid {grid-template-columns:repeat(4, minmax(0, 1fr));}}
        </style>
    """
    st.markdown(table_style, unsafe_allow_html=True)
    period_times = (_load_cache(SCHEDULE_METADATA_PATH) or {}).get("period_times", {})
    rows = []
    for p in PERIODS:
        time_text = html.escape(period_times.get(str(p), "时间未标注"))
        row = [f"<td class='period-col'><div>第{p}节</div><div class='period-time'>{time_text}</div></td>"]
        for d in WEEKDAYS:
            items = grid[d][p]
            if not items:
                row.append("<td style='color:#94a3b8;'>-</td>")
            else:
                cell_unique: dict[tuple, dict] = {}
                for rec in items:
                    ckey = (
                        tuple(sorted(rec["teachers"])), rec["course"], rec.get("course_code"),
                        rec["start_period"], rec["end_period"], rec.get("week_text"),
                        rec.get("teaching_type"), rec["classroom"], rec["class_group"],
                        rec.get("student_count"), rec.get("source_truncated"),
                    )
                    if ckey not in cell_unique:
                        cell_unique[ckey] = rec.copy()
                    else:
                        existing = cell_unique[ckey]
                        for field in ["classroom", "class_group", "sheet"]:
                            v1 = set(str(existing.get(field, "")).split("、"))
                            v2 = set(str(rec.get(field, "")).split("、"))
                            existing[field] = "、".join(sorted({x.strip() for x in (v1 | v2) if x.strip()}))

                grouped = defaultdict(list)
                for rec in cell_unique.values():
                    cat = "院内其余老师"
                    for t in rec["teachers"]:
                        if t in teacher_category_map:
                            cat = teacher_category_map[t]
                            break
                    if cat not in CATEGORY_ORDER:
                        cat = "院内其余老师"
                    grouped[cat].append(rec)

                col_html = []
                for cat in CATEGORY_ORDER:
                    cards = "".join(_card_html(rec) for rec in grouped.get(cat, []))
                    col_html.append(f"<div class='dept-col'>{cards}</div>")
                row.append("<td><div class='dept-grid'>" + "".join(col_html) + "</div></td>")
        rows.append("<tr>" + "".join(row) + "</tr>")

    header = "".join(f"<th>{d}</th>" for d in WEEKDAYS)
    html_table = (
        "<div class='tb-wrap'><table class='tb'>"
        "<thead><tr><th class='period-col'>节次</th>" + header + "</tr></thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )
    st.markdown(html_table, unsafe_allow_html=True)


# ── 主页面 ────────────────────────────────────────────────
st.title("📚 课表查询-2026-2027-1")
st.caption("健康医疗科技学院 · 2026—2027 学年第一学期，支持全院总课表与按教师查询。")

records = load_schedule_records()

if not records:
    st.error("未找到 2026—2027 学年第一学期课表数据，请重新导入本学期教师课表。")
    st.stop()

teacher_set = sorted({t for rec in records for t in rec["teachers"] if t.strip()})
selected_filter = st.selectbox("按教师查询", ["全部教师", "院务会"] + teacher_set, index=0)
teacher_category_map = build_teacher_category_map(records)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("识别课程记录", len(records))
with col2:
    st.metric("教师人数", len(teacher_set))
with col3:
    matched = [rec for rec in records if record_matches_filter(rec, selected_filter)]
    st.metric("当前筛选记录", len(matched))

st.markdown("### 总课表（周一至周五，第1节至第14节）")
metadata = _load_cache(SCHEDULE_METADATA_PATH) or {}
if metadata.get("truncated_source_cells"):
    st.caption(
        f"原表有 {metadata['truncated_source_cells']} 个单元格的信息已被省略，相关课程已保留提示；"
        "点击教师姓名查看周次、班级和教室。"
    )
grid = build_period_grid(records, selected_filter)
render_grid(grid, teacher_category_map)

if selected_filter != "全部教师":
    title = f"{selected_filter} 的课程明细"
    if selected_filter == "院务会":
        title = "院务会成员课程明细"
    st.markdown(f"### {title}")
    details = []
    for rec in sorted(matched, key=lambda item: (WEEKDAYS.index(item["weekday"]), item["start_period"], item["course"])):
        details.append(
            {
                "星期": rec["weekday"],
                "节次": f"{rec['start_period']}-{rec['end_period']}",
                "课程": rec["course"],
                "周次": rec.get("week_text") or "原文未完整列出",
                "类型": rec.get("teaching_type") or "未标注",
                "教师": rec["teacher_label"],
                "教室": rec["classroom"],
                "班级": rec["class_group"],
                "来源": rec["sheet"],
                "备注": "原表信息已省略" if rec.get("source_truncated") else "",
            }
        )
    if details:
        st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)
    else:
        st.info("本学期课表中没有该筛选条件下的课程。")
