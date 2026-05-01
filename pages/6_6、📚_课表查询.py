import html
import re
from pathlib import Path
from collections import defaultdict

import pandas as pd
import streamlit as st


st.set_page_config(page_title="课表查询", page_icon="📚", layout="wide")

EXCEL_PATH = Path(
    r"E:\GoogleDrive\Ding2026\健康医疗科技学院2025-2026学年第二学期（理论）课表汇总表(1).xlsx"
)
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五"]
PERIODS = list(range(1, 11))
CATEGORY_ORDER = ["医学信息工程系", "健康服务与管理系", "医学影像技术系", "院内其余老师"]
TEACHER_CATEGORY_EXCEL_PATH = Path(
    r"E:\GoogleDrive\Ding2026\健康医疗科技学院2025-2026学年第二学期（理论）课表汇总表.xlsx"
)
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
WEEKDAY_PATTERN = re.compile(r"星期[一二三四五]")
ENTRY_PATTERN = re.compile(r"【\d+】.*?(?=【\d+】|$)", re.S)
RANGE_PATTERN = re.compile(r"(\d{1,2})\s*-\s*(\d{1,2})\s*节")
SINGLE_PATTERN = re.compile(r"(?<!-)(\d{1,2})\s*节")
WEEK_MARKER_PATTERN = re.compile(r"（\d{1,2}\s*-\s*\d{1,2}周）")
CLASSROOM_PATTERN = re.compile(r"\b([A-Z]{1,2}\d{3,4}[A-Za-z0-9]*)\b")
HEAD_PREFIX_PATTERN = re.compile(r"^【\d+】\s*")
TAIL_COUNT_PATTERN = re.compile(r"\s*人数[:：]\s*\d+\s*$")
COURSE_HINT_PATTERN = re.compile(
    r"(学|课程|原理|技术|基础|教育|营销|英语|法规|计划|管理|心理|影像|数据|检查|操作|艺术|创业|Java|Python|Arduino)"
)


def _normalize_text(value: object) -> str:
    text = str(value).replace("\r", "\n").replace("\u3000", " ").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text


def _extract_weekday_columns(df: pd.DataFrame) -> dict[int, str]:
    weekday_columns: dict[int, str] = {}
    for col in df.columns:
        for val in df[col].dropna():
            match = WEEKDAY_PATTERN.search(str(val))
            if match:
                day = match.group(0)
                if day in WEEKDAYS:
                    weekday_columns[col] = day
                break
    return weekday_columns


def _extract_entries(cell_text: str) -> list[str]:
    if "【" not in cell_text or "节" not in cell_text:
        return []
    entries = [seg.strip() for seg in ENTRY_PATTERN.findall(cell_text)]
    if entries:
        return entries
    return [cell_text.strip()]


def _looks_like_course_token(token: str) -> bool:
    if not token:
        return False
    if re.search(r"[A-Za-z]", token):
        return True
    return bool(COURSE_HINT_PATTERN.search(token))


def _parse_teachers_and_course(head_text: str) -> tuple[list[str], str]:
    cleaned = WEEK_MARKER_PATTERN.sub("", head_text)
    cleaned = re.sub(r"（兼职[^）]*）", "", cleaned)
    cleaned = re.sub(r"（暂未确定[^）]*）", "", cleaned)
    cleaned = cleaned.replace("（下）", "")
    cleaned = cleaned.replace("，", "、")
    cleaned = cleaned.replace(",", "、")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    tokens: list[str] = []
    for part in cleaned.split(" "):
        if "、" in part:
            tokens.extend([x.strip() for x in part.split("、") if x.strip()])
        else:
            token = part.strip()
            if token:
                tokens.append(token)
    teachers: list[str] = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx].strip()
        if _looks_like_course_token(token):
            break
        if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", token):
            teachers.append(token)
            idx += 1
            continue
        break
    if not teachers and tokens:
        teachers = [tokens[0]]
        idx = 1
    course = " ".join(tokens[idx:]).strip() or "未识别课程"
    return teachers, course


def _parse_entry(entry: str, day: str, sheet_name: str) -> list[dict]:
    norm = _normalize_text(entry)
    period_ranges = [(int(a), int(b)) for a, b in RANGE_PATTERN.findall(norm)]
    if not period_ranges:
        singles = [int(x) for x in SINGLE_PATTERN.findall(norm)]
        period_ranges = [(x, x) for x in singles]
    if not period_ranges:
        return []

    stripped = HEAD_PREFIX_PATTERN.sub("", norm)
    first_period_match = RANGE_PATTERN.search(stripped) or SINGLE_PATTERN.search(stripped)
    head = stripped
    tail = ""
    if first_period_match:
        head = stripped[: first_period_match.start()].strip()
        tail = stripped[first_period_match.end() :].strip()

    teachers, course = _parse_teachers_and_course(head)
    teachers = sorted(list(set(teachers)))  # 去重并排序，确保姓名顺序一致
    classroom_match = CLASSROOM_PATTERN.search(tail)
    classroom = classroom_match.group(1) if classroom_match else ""
    class_group = tail[classroom_match.end() :].strip() if classroom_match else tail
    class_group = TAIL_COUNT_PATTERN.sub("", class_group).strip()

    teacher_label = "、".join(teachers)
    records: list[dict] = []
    for start, end in period_ranges:
        if start > end:
            start, end = end, start
        records.append(
            {
                "sheet": sheet_name,
                "weekday": day,
                "start_period": start,
                "end_period": end,
                "teachers": teachers,
                "teacher_label": teacher_label,
                "course": course,
                "classroom": classroom,
                "class_group": class_group,
                "raw": norm,
            }
        )
    return records


@st.cache_data(show_spinner=False)
def load_schedule_records(excel_path: str) -> list[dict]:
    xls = pd.ExcelFile(excel_path)
    all_records: list[dict] = []
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, dtype=str).fillna("")
        weekday_columns = _extract_weekday_columns(df)
        if not weekday_columns:
            continue

        for col_idx, day in weekday_columns.items():
            for cell in df[col_idx].tolist():
                text = _normalize_text(cell)
                if not text:
                    continue
                for entry in _extract_entries(text):
                    all_records.extend(_parse_entry(entry, day, sheet_name))

    unique_records: dict[tuple, dict] = {}
    for rec in all_records:
        # 更加宽松的去重 Key：只要 星期、节次、教师列表、课程 相同，就视为同一条记录
        # 教师列表转为 sorted tuple 以处理顺序不一致的情况
        key = (
            rec["weekday"],
            rec["start_period"],
            rec["end_period"],
            tuple(sorted(rec["teachers"])),
            rec["course"],
        )
        if key not in unique_records:
            unique_records[key] = rec
        else:
            # 如果 Key 已存在，则合并 教室、班级 和 来源
            existing = unique_records[key]

            # 合并来源 Sheet
            existing_sheets = set(str(existing.get("sheet", "")).split("、"))
            new_sheets = set(str(rec.get("sheet", "")).split("、"))
            existing["sheet"] = "、".join(sorted({s.strip() for s in (existing_sheets | new_sheets) if s.strip()}))

            # 合并教室
            existing_rooms = set(str(existing.get("classroom", "")).split("、"))
            new_rooms = set(str(rec.get("classroom", "")).split("、"))
            existing["classroom"] = "、".join(sorted({r.strip() for r in (existing_rooms | new_rooms) if r.strip()}))

            # 合并班级
            existing_groups = set(str(existing.get("class_group", "")).split("、"))
            new_groups = set(str(rec.get("class_group", "")).split("、"))
            existing["class_group"] = "、".join(sorted({g.strip() for g in (existing_groups | new_groups) if g.strip()}))

    return list(unique_records.values())


def record_matches_filter(rec: dict, selected_filter: str) -> bool:
    if selected_filter == "全部教师":
        return True
    if selected_filter == "院务会":
        return any(t in COUNCIL_MEMBERS for t in rec["teachers"])
    return selected_filter in rec["teachers"]


def _category_from_sheet_name(sheet_name: str) -> str | None:
    for cat in CATEGORY_ORDER:
        if cat in sheet_name:
            return cat
    return None


@st.cache_data(show_spinner=False)
def build_teacher_category_map(records: list[dict], category_excel_path: str) -> dict[str, str]:
    teacher_set = sorted({t for rec in records for t in rec["teachers"] if t.strip()})
    score: dict[str, dict[str, int]] = {t: {c: 0 for c in CATEGORY_ORDER} for t in teacher_set}

    # 优先用已解析课表中的来源sheet做一次归类打分
    for rec in records:
        cat = _category_from_sheet_name(str(rec.get("sheet", "")))
        if not cat:
            continue
        for t in rec["teachers"]:
            if t in score:
                score[t][cat] += 2

    # 再从“教师系部分类”Excel中做精确匹配加权
    category_file = Path(category_excel_path)
    if category_file.exists():
        xls = pd.ExcelFile(str(category_file))
        for sheet_name in xls.sheet_names:
            cat = _category_from_sheet_name(sheet_name)
            if not cat:
                continue
            df = pd.read_excel(str(category_file), sheet_name=sheet_name, header=None, dtype=str).fillna("")
            text_blob = " ".join(df.astype(str).values.flatten().tolist())
            for teacher in teacher_set:
                if teacher and teacher in text_blob:
                    score[teacher][cat] += 5

    teacher_category: dict[str, str] = {}
    for teacher in teacher_set:
        best = max(score[teacher], key=score[teacher].get)
        teacher_category[teacher] = best if score[teacher][best] > 0 else "院内其余老师"
    return teacher_category


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
        f"<div><span class='k'>教室</span> {room}</div>"
        f"<div><span class='k'>班级</span> {cls}</div>"
        f"<div><span class='k'>来源</span> {source}</div>"
        "</div>"
        "</details>"
        "</div>"
    )


def render_grid(grid: dict[str, dict[int, list[dict]]], teacher_category_map: dict[str, str]) -> None:
    table_style = """
    <style>
      .tb-wrap {overflow-x:auto;}
      table.tb {border-collapse:collapse; width:100%; min-width:1200px; background:#ffffff;}
      .tb th, .tb td {border:1px solid #dbe4f0; vertical-align:top; padding:8px;}
      .tb th {background:#f1f5f9; font-weight:700; color:#0f172a;}
      .period-col {width:78px; text-align:center; background:#f8fafc; font-weight:700;}
      .dept-grid {display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:6px;}
      .dept-col {min-width:0;}
      .teacher-card {display:block; width:100%; margin:4px 0; border:1px solid #dbeafe; background:#f8fbff; border-radius:8px; font-size:12px;}
      .teacher-card details {display:block;}
      .teacher-summary {list-style:none; cursor:pointer; padding:6px 7px;}
      .teacher-summary::-webkit-details-marker {display:none;}
      .teacher-name {font-size:12px; font-weight:700; color:#0b4b8c; line-height:1.2; text-align:center; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
      .teacher-detail {font-size:11px; color:#334155; border-top:1px solid #e5effb; padding:6px 7px; line-height:1.4; word-break:break-all;}
      .teacher-detail .k {display:inline-block; min-width:28px; color:#64748b;}
      @media (max-width: 1280px) {.dept-grid {grid-template-columns:repeat(4, minmax(0, 1fr));}}
    </style>
    """
    st.markdown(table_style, unsafe_allow_html=True)
    rows = []
    for p in PERIODS:
        row = [f"<td class='period-col'>第{p}节</td>"]
        for d in WEEKDAYS:
            items = grid[d][p]
            if not items:
                row.append("<td style='color:#94a3b8;'>-</td>")
            else:
                # 在格子渲染前进行最后一次去重合并，处理因原始记录时段跨度不同导致的重复显示
                cell_unique: dict[tuple, dict] = {}
                for rec in items:
                    # 以教师列表和课程作为格子内的唯一标识
                    ckey = (tuple(sorted(rec["teachers"])), rec["course"])
                    if ckey not in cell_unique:
                        cell_unique[ckey] = rec.copy()
                    else:
                        # 合并元数据
                        existing = cell_unique[ckey]
                        for field in ["classroom", "class_group", "sheet"]:
                            v1 = set(str(existing.get(field, "")).split("、"))
                            v2 = set(str(rec.get(field, "")).split("、"))
                            existing[field] = "、".join(sorted({x.strip() for x in (v1 | v2) if x.strip()}))

                grouped = defaultdict(list)
                for rec in cell_unique.values():
                    # 多教师记录时，按第一个可识别教师归类；没有则归“院内其余老师”
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


st.title("📚 健康医疗科技学院课表查询")
st.caption("固定读取本学期课表文件（全部工作表），支持全院总课表与按教师查询。")

if not EXCEL_PATH.exists():
    st.error(f"未找到课表文件：{EXCEL_PATH}")
    st.stop()

try:
    records = load_schedule_records(str(EXCEL_PATH))
except Exception as exc:
    st.error(f"读取课表失败：{exc}")
    st.stop()

if not records:
    st.warning("未从 Excel 中识别到有效课程记录，请检查原始表格结构。")
    st.stop()

teacher_set = sorted({t for rec in records for t in rec["teachers"] if t.strip()})
selected_filter = st.selectbox("按教师查询", ["全部教师", "院务会"] + teacher_set, index=0)
teacher_category_map = build_teacher_category_map(records, str(TEACHER_CATEGORY_EXCEL_PATH))

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("识别课程记录", len(records))
with col2:
    st.metric("教师人数", len(teacher_set))
with col3:
    matched = [rec for rec in records if record_matches_filter(rec, selected_filter)]
    st.metric("当前筛选记录", len(matched))

st.markdown("### 总课表（周一至周五，第1节至第10节）")
grid = build_period_grid(records, selected_filter)
render_grid(grid, teacher_category_map)

if selected_filter != "全部教师":
    title = f"{selected_filter} 的课程明细"
    if selected_filter == "院务会":
        title = "院务会成员课程明细"
    st.markdown(f"### {title}")
    details = []
    for rec in matched:
        details.append(
            {
                "星期": rec["weekday"],
                "节次": f"{rec['start_period']}-{rec['end_period']}",
                "课程": rec["course"],
                "教师": rec["teacher_label"],
                "教室": rec["classroom"],
                "班级": rec["class_group"],
                "来源Sheet": rec["sheet"],
            }
        )
    detail_df = pd.DataFrame(details).sort_values(["星期", "节次", "课程"], kind="stable")
    st.dataframe(detail_df, use_container_width=True, hide_index=True)
