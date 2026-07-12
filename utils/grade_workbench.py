from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any

import pandas as pd


@dataclass
class ScoreSettings:
    other_weight: float = 0.60
    pitch_weight: float = 0.20
    report_weight: float = 0.20
    global_adjustment: float = 0.0
    global_adjustment_reason: str = ""
    coefficient_min: float = 0.0
    coefficient_max: float = 1.0
    rounding: str = "四舍五入为整数"
    score_floor: float = 0.0
    score_cap: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any] | None) -> "ScoreSettings":
        values = values or {}
        defaults = cls()
        payload: dict[str, Any] = {}
        for key in defaults.to_dict():
            payload[key] = values.get(key, getattr(defaults, key))
        for key in (
            "other_weight",
            "pitch_weight",
            "report_weight",
            "global_adjustment",
            "coefficient_min",
            "coefficient_max",
            "score_floor",
            "score_cap",
        ):
            payload[key] = float(payload[key])
        payload["global_adjustment_reason"] = str(payload["global_adjustment_reason"] or "")
        return cls(**payload)


STUDENT_COLUMNS = [
    "student_no",
    "name",
    "class_name",
    "group_code",
    "other_score",
    "coefficient",
    "individual_adjustment",
    "adjustment_reason",
]

GROUP_COLUMNS = [
    "group_code",
    "project_name",
    "pitch_score",
    "report_score",
    "group_adjustment",
    "adjustment_reason",
    "score_comment",
]


def empty_students() -> pd.DataFrame:
    return pd.DataFrame(columns=STUDENT_COLUMNS)


def empty_groups() -> pd.DataFrame:
    return pd.DataFrame(columns=GROUP_COLUMNS)


def _number(value: Any, default: float = 0.0) -> float:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return default
    return float(value)


def round_score(value: float, mode: str) -> float:
    decimal_value = Decimal(str(value))
    if mode == "保留一位小数":
        return float(decimal_value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    if mode == "向下取整":
        return float(decimal_value.quantize(Decimal("1"), rounding=ROUND_DOWN))
    return float(decimal_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def normalize_students(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in STUDENT_COLUMNS:
        if column not in result.columns:
            result[column] = "" if column in {"student_no", "name", "class_name", "group_code", "adjustment_reason"} else 0.0
    result = result[STUDENT_COLUMNS]
    for column in ("student_no", "name", "class_name", "group_code", "adjustment_reason"):
        result[column] = result[column].fillna("").astype(str).str.strip()
    for column, default in (("other_score", 0.0), ("coefficient", 1.0), ("individual_adjustment", 0.0)):
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(default)
    return result


def normalize_groups(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in GROUP_COLUMNS:
        if column not in result.columns:
            result[column] = "" if column in {"group_code", "project_name", "adjustment_reason", "score_comment"} else 0.0
    result = result[GROUP_COLUMNS]
    for column in ("group_code", "project_name", "adjustment_reason", "score_comment"):
        result[column] = result[column].fillna("").astype(str).str.strip()
    for column in ("pitch_score", "report_score", "group_adjustment"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def sync_groups_from_students(students: pd.DataFrame, groups: pd.DataFrame) -> pd.DataFrame:
    students = normalize_students(students)
    groups = normalize_groups(groups)
    codes = sorted(code for code in students["group_code"].unique() if code)
    existing = {row["group_code"]: row for _, row in groups.iterrows()}
    rows = []
    for code in codes:
        if code in existing:
            rows.append(existing[code].to_dict())
        else:
            rows.append({
                "group_code": code,
                "project_name": "",
                "pitch_score": None,
                "report_score": None,
                "group_adjustment": 0.0,
                "adjustment_reason": "",
                "score_comment": "",
            })
    return normalize_groups(pd.DataFrame(rows, columns=GROUP_COLUMNS)) if rows else empty_groups()


def calculate_results(
    students: pd.DataFrame,
    groups: pd.DataFrame,
    settings: ScoreSettings,
) -> pd.DataFrame:
    students = normalize_students(students)
    groups = normalize_groups(groups)
    group_lookup = groups.set_index("group_code").to_dict("index") if not groups.empty else {}
    rows: list[dict[str, Any]] = []
    for _, student in students.iterrows():
        group = group_lookup.get(student["group_code"], {})
        pitch_raw = _number(group.get("pitch_score"), 0.0)
        report_raw = _number(group.get("report_score"), 0.0)
        coefficient = _number(student["coefficient"], 1.0)
        pitch_personal = round_score(pitch_raw * coefficient, settings.rounding)
        report_personal = round_score(report_raw * coefficient, settings.rounding)
        other_contribution = _number(student["other_score"]) * settings.other_weight
        pitch_contribution = pitch_personal * settings.pitch_weight
        report_contribution = report_personal * settings.report_weight
        group_adjustment = _number(group.get("group_adjustment"), 0.0)
        individual_adjustment = _number(student["individual_adjustment"], 0.0)
        adjustment_total = settings.global_adjustment + group_adjustment + individual_adjustment
        before_limit = other_contribution + pitch_contribution + report_contribution + adjustment_total
        limited = min(settings.score_cap, max(settings.score_floor, before_limit))
        final_score = round_score(limited, settings.rounding)
        rows.append({
            "student_no": student["student_no"],
            "name": student["name"],
            "class_name": student["class_name"],
            "group_code": student["group_code"],
            "other_score": _number(student["other_score"]),
            "pitch_raw": pitch_raw,
            "report_raw": report_raw,
            "coefficient": coefficient,
            "pitch_personal": pitch_personal,
            "report_personal": report_personal,
            "global_adjustment": settings.global_adjustment,
            "group_adjustment": group_adjustment,
            "individual_adjustment": individual_adjustment,
            "adjustment_total": adjustment_total,
            "score_before_limit": round(before_limit, 4),
            "final_score": final_score,
            "adjustment_reason": student["adjustment_reason"],
        })
    return pd.DataFrame(rows)


def validate_all(
    students: pd.DataFrame,
    groups: pd.DataFrame,
    settings: ScoreSettings,
) -> pd.DataFrame:
    students = normalize_students(students)
    groups = normalize_groups(groups)
    issues: list[dict[str, str]] = []

    def add(level: str, category: str, message: str) -> None:
        issues.append({"level": level, "category": category, "message": message})

    weights = settings.other_weight + settings.pitch_weight + settings.report_weight
    if abs(weights - 1.0) > 1e-9:
        add("错误", "权重", f"三个成绩权重合计为 {weights:.4f}，必须等于 1。")
    if settings.score_floor >= settings.score_cap:
        add("错误", "范围", "成绩下限必须小于成绩上限。")
    if settings.coefficient_min > settings.coefficient_max:
        add("错误", "系数", "系数下限不能大于系数上限。")
    if settings.global_adjustment != 0 and not settings.global_adjustment_reason.strip():
        add("警告", "调整", "存在全体统一调整，但尚未填写调整原因。")
    if students.empty:
        add("错误", "花名册", "尚未导入学生花名册。")
        return pd.DataFrame(issues)

    blank_no = students[students["student_no"] == ""]
    blank_name = students[students["name"] == ""]
    blank_group = students[students["group_code"] == ""]
    if not blank_no.empty:
        add("错误", "花名册", f"有 {len(blank_no)} 名学生缺少学号。")
    if not blank_name.empty:
        add("错误", "花名册", f"有 {len(blank_name)} 名学生缺少姓名。")
    if not blank_group.empty:
        add("错误", "分组", f"有 {len(blank_group)} 名学生尚未分组。")
    duplicate_no = students[students["student_no"].duplicated(keep=False) & (students["student_no"] != "")]
    if not duplicate_no.empty:
        add("错误", "花名册", f"发现重复学号：{', '.join(sorted(duplicate_no['student_no'].unique()))}")

    group_codes = set(groups["group_code"])
    student_codes = set(students.loc[students["group_code"] != "", "group_code"])
    missing_groups = sorted(student_codes - group_codes)
    if missing_groups:
        add("错误", "分组", f"以下小组没有组级评分记录：{', '.join(missing_groups)}")
    duplicate_groups = groups[groups["group_code"].duplicated(keep=False) & (groups["group_code"] != "")]
    if not duplicate_groups.empty:
        add("错误", "分组", f"发现重复小组记录：{', '.join(sorted(duplicate_groups['group_code'].unique()))}")

    for _, row in groups.iterrows():
        code = row["group_code"] or "未命名小组"
        for column, label in (("pitch_score", "路演"), ("report_score", "报告")):
            value = row[column]
            if pd.isna(value):
                add("错误", "原始分", f"{code}缺少{label}原始分。")
            elif not 0 <= float(value) <= 100:
                add("错误", "原始分", f"{code}的{label}原始分 {value} 超出 0—100。")
        if _number(row["group_adjustment"]) != 0 and not row["adjustment_reason"]:
            add("警告", "调整", f"{code}存在小组调整，但未填写原因。")

    bad_coefficients = students[
        (students["coefficient"] < settings.coefficient_min)
        | (students["coefficient"] > settings.coefficient_max)
    ]
    if not bad_coefficients.empty:
        add("错误", "系数", f"有 {len(bad_coefficients)} 名学生的系数超出允许范围。")
    bad_other = students[(students["other_score"] < 0) | (students["other_score"] > 100)]
    if not bad_other.empty:
        add("错误", "其他成绩", f"有 {len(bad_other)} 名学生的其他考核成绩超出 0—100。")
    missing_reasons = students[(students["individual_adjustment"] != 0) & (students["adjustment_reason"] == "")]
    if not missing_reasons.empty:
        add("警告", "调整", f"有 {len(missing_reasons)} 名学生存在个别调整但未填写原因。")

    if not issues:
        add("通过", "总体验证", "全部硬校验通过，可以生成审核工作簿。")
    return pd.DataFrame(issues)


def has_errors(validation: pd.DataFrame) -> bool:
    return not validation.empty and bool((validation["level"] == "错误").any())
