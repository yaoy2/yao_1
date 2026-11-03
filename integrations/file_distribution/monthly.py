"""Recognize actual monthly report sheets without using file timestamps."""

from dataclasses import dataclass
from pathlib import Path
import re

from .models import Decision
from .readers import Sheet, col_number, normalized, read_workbook, row_number


MONTHLY_HINT = re.compile(r"月报|院报|工作总结.*计划|重点工作总结")
M = r"(?:0?[1-9]|1[0-2])"
PERIOD = re.compile(
    rf"(?<!\d)(?:(?P<year>20\d{{2}})年)?(?P<months>{M}(?:[-、,至到]{M})?)"
    r"月?(?:份)?(?:重点)?(?:工作)?(?P<action>总结|完成情况|计划)"
)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", normalized(text))


def _months(value: str) -> tuple[int, ...]:
    numbers = [int(n) for n in re.findall(r"\d+", value)]
    if len(numbers) == 2 and re.search(r"[-至到]", value):
        if numbers[0] > numbers[1]:
            return ()
        return tuple(range(numbers[0], numbers[1] + 1))
    return tuple(dict.fromkeys(numbers))


def _period_labels(text: str) -> list[tuple[str, tuple[int, ...], int | None]]:
    return [
        ("plan" if m["action"] == "计划" else "summary", _months(m["months"]), int(m["year"]) if m["year"] else None)
        for m in PERIOD.finditer(_compact(text))
    ]


def _name_hints(name: str) -> list[tuple[tuple[int, ...], int | None]]:
    labels = _period_labels(name)
    summaries = [months for action, months, _ in labels if action == "summary"]
    plans = [months[0] for action, months, _ in labels if action == "plan" and months]
    if summaries:
        return [(months, plans[0] if len(set(plans)) == 1 else None) for months in summaries]
    stem = Path(_compact(name)).stem
    # The normalized name explicitly labels the summary month/range, not a summary-plan pair.
    named_period = re.search(rf"-({M}(?:-{M})?)月-[^-]+$", stem)
    if named_period:
        return [(_months(named_period[1]), None)]
    # Historic compact form: 78-9 means July/August summary and September plan.
    if re.search(r"(?<!\d)78-9(?:月)?(?!\d)", stem):
        return [((7, 8), 9)]
    pair = re.search(rf"(?<!\d)({M})-({M})(?:月)?(?!\d)", stem)
    if pair:
        first, last = map(int, pair.groups())
        if first < last:
            return [((first,), last), (tuple(range(first, last)), last), (tuple(range(first, last + 1)), None)]
        if first == 12 and last == 1:
            return [((12,), 1)]
        return []
    single = re.search(rf"(?<!\d)({M})月", stem)
    return [((int(single[1]),), None)] if single else []


def _matches(hints, summaries, plans) -> bool:
    if not hints:
        return True
    return any(months in summaries and (plan is None or any(p and p[0] == plan for p in plans)) for months, plan in hints)


def _period_name(months: tuple[int, ...]) -> str:
    if len(months) == 1:
        return f"{months[0]:02d}月"
    return f"{months[0]:02d}-{months[-1]:02d}月"


@dataclass
class Profile:
    sheet: Sheet
    labels: list[tuple[str, tuple[int, ...], int | None]]
    column_labels: list[tuple[str, tuple[int, ...], int | None]]
    data_columns: set[int]

    def values(self, action: str, *, columns: bool = False) -> set[tuple[int, ...]]:
        return {months for kind, months, _ in (self.column_labels if columns else self.labels) if kind == action and months}

    def has_data(self) -> bool:
        return bool(self.data_rows())

    def data_rows(self) -> set[int]:
        return {
            row_number(address) for address, text in self.sheet.cells.items()
            if row_number(address) >= 3 and col_number(address) in self.data_columns
            and text.strip() and not re.fullmatch(r"(?:请填写|待填写|待填|[-—/\s]|[xX某]){1,12}", text)
        }


def _profile(sheet: Sheet) -> Profile:
    labels, column_labels, data_columns = [], [], set()
    for address, text in sheet.cells.items():
        row = row_number(address)
        if row > 2:
            continue
        found = _period_labels(text)
        labels.extend(found)
        if row == 2 and found:
            column_labels.extend(found)
            data_columns.add(col_number(address))
    return Profile(sheet, labels, column_labels, data_columns)


def _identity_cell(sheet: Sheet, column: str, row: int) -> str:
    address = f"{column}{row}"
    if address in sheet.cells:
        return _compact(sheet.cells[address])
    # Fill only genuine merged cells, never carry a different person's unit into an empty row.
    for merged in sheet.merged_ranges:
        first, last = merged.split(":")
        if (col_number(first) <= col_number(address) <= col_number(last)
                and row_number(first) <= row <= row_number(last)):
            return _compact(sheet.cells.get(first, ""))
    return ""


def _academy_name(profiles: list[Profile], name: str, period: str, extension: str) -> tuple[str, str, str]:
    identities, roster, groups = set(), set(), set()
    for profile in profiles:
        if not profile.has_data():
            continue
        headers = {address.rstrip("0123456789"): _compact(text)
                   for address, text in profile.sheet.cells.items() if row_number(address) == 2}
        deputy = "副院长" in headers.values()
        groups.add("副院长" if deputy else "系主任管理中心")
        people_columns = [column for column, text in headers.items() if text in {"人员", "姓名", "填报人", "负责人"}]
        if not people_columns and deputy:
            people_columns = [column for column, text in headers.items() if text == "副院长"]
        unit_columns = [column for column, text in headers.items()
                        if text in {"系/部/中心", "单位", "部门"} or re.search(r"系.*部.*中心|管理中心.*学工", text)]
        if len(people_columns) != 1 or (not deputy and len(unit_columns) != 1):
            raise ValueError("未找到唯一的人员/单位列，无法统一命名，保留原处待核对")
        for row in {row_number(address) for address in profile.sheet.cells if row_number(address) >= 3}:
            person = _identity_cell(profile.sheet, people_columns[0], row)
            if person and len(person) <= 32:
                roster.add(person)
        for row in profile.data_rows():
            person = _identity_cell(profile.sheet, people_columns[0], row)
            unit = "副院长" if deputy else _identity_cell(profile.sheet, unit_columns[0], row)
            unit = re.sub(r"(?:副主任|主任)$", "", unit)
            unit = {"健服系": "健康服务与管理系"}.get(unit, unit)
            if (not re.fullmatch(r"[\u3400-\u9fffA-Za-z·・.]{2,32}", person)
                    or re.fullmatch(r"(?:请填写|待填写|待填|[xX某]){1,12}", person)
                    or person in {"人员", "姓名", "负责人", "填报人"}):
                raise ValueError("当期填写行缺少明确的单人人名，无法统一命名，保留原处待核对")
            if (not re.fullmatch(r".+(?:系|部|中心)|学工|副院长", unit)
                    or re.search(r'[<>:"/\\|?*\x00-\x1f]', unit)):
                raise ValueError("当期填写行缺少明确的系部/管理中心，无法统一命名，保留原处待核对")
            identities.add((unit, person))
    if len(groups) != 1:
        raise ValueError("当期同时包含副院长和系主任管理中心，汇总类别不唯一，保留原处待核对")
    named_people = {person for person in roster if person in _compact(name)}
    actual_people = {person for _, person in identities}
    if named_people and named_people != actual_people:
        raise ValueError("文件名人名与当期实际填写人员不一致，保留原处待核对")
    if len(identities) > len(actual_people):
        raise ValueError("同一人员的当期单位不唯一，保留原处待核对")
    if len(identities) > 1 or "汇总" in name:
        group = next(iter(groups))
        return f"【健康学院】学院月报-{group}{extension}", group, "汇总表按报送类别统一命名"
    unit, person = next(iter(identities))
    return f"【健康学院】学院月报-{unit}-{period}-{person}{extension}", unit, "按当期实际填写行核对单位和人名"


def _root_year(root: Path) -> int | None:
    found = re.fullmatch(r"ding(20\d{2})", root.name, re.I)
    return int(found[1]) if found else None


def _validate_period(summaries, plans, years, root_year, hints, *, plan_years=None, name="") -> str:
    if len(summaries) != 1 or len(plans) != 1:
        return "当期标题、总结列或计划列的月份缺失/互相冲突，保留原处待核对"
    summary, plan = next(iter(summaries)), next(iter(plans))
    years = set(years)
    plan_years = set(plan_years or ())
    name_labels = _period_labels(name)
    name_summary_years = {y for action, _, y in name_labels if action == "summary" and y}
    name_plan_years = {y for action, _, y in name_labels if action == "plan" and y}
    if not name_summary_years and not name_plan_years:
        # E.g. 学院院报-2025年10月; do not interpret an arbitrary download timestamp.
        name_summary_years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})年", name)}
    years.update(name_summary_years)
    plan_years.update(name_plan_years)
    if not summary or not plan or tuple(range(summary[0], summary[-1] + 1)) != summary:
        return "总结月份不是明确的连续报送期，保留原处待核对"
    if plan[0] != summary[-1] % 12 + 1:
        return "总结期与计划期未正常衔接，保留原处待核对"
    if len(years) > 1:
        return "当期总结年份互相冲突，保留原处待核对"
    if root_year and years and years != {root_year}:
        return f"材料总结年份与 Ding{root_year} 不符，保留原处待核对"
    if not years and root_year is None:
        return "表内未写总结年份，根目录也未标明年份，保留原处待核对"
    summary_year = next(iter(years)) if years else root_year
    expected_plan_year = summary_year + int(summary[-1] == 12 and plan[0] == 1)
    if plan_years and plan_years != {expected_plan_year}:
        return "计划年份与总结期不符，保留原处待核对"
    if not _matches(hints, summaries, plans):
        return "文件名报送期与当期工作表不一致，保留原处待核对"
    return ""


def _school(name: str, sheets: list[Sheet], year: int | None) -> Decision:
    labels = [label for sheet in sheets for label in _profile(sheet).labels]
    summaries = {months for action, months, _ in labels if action == "summary" and months}
    plans = {months for action, months, _ in labels if action == "plan" and months}
    years = {y for action, _, y in labels if action == "summary" and y}
    plan_years = {y for action, _, y in labels if action == "plan" and y}
    reason = _validate_period(summaries, plans, years, year, _name_hints(name), plan_years=plan_years, name=name)
    if reason:
        return Decision("review", "校办月报", reason=reason)
    populated = False
    recognized_headers = False
    for sheet in sheets:
        columns = {
            col_number(address): row_number(address) for address, text in sheet.cells.items()
            if row_number(address) <= 5 and _compact(text) in {"工作项目", "工作计划", "实际完成情况", "计划完成目标(量化)"}
        }
        recognized_headers |= bool(columns)
        if any(col_number(address) in columns and row_number(address) > columns[col_number(address)] and text.strip() for address, text in sheet.cells.items()):
            populated = True
    if not recognized_headers:
        return Decision("review", "校办月报", reason="未找到校办报表项目/计划/完成情况栏，保留原处待核对")
    if not populated:
        return Decision("skip", "校办月报", reason="当期表格没有实际填写内容，按空白模板保留原处")
    if re.search(r"模板|模版|[Xx]{2,}学院", name):
        return Decision("review", "校办月报", reason="文件仍带模板标记但已有内容，请核对是否为正式报表")
    period = _period_name(next(iter(summaries)))
    return Decision("ready", "校办月报", period, relative_dir=f"月报/{period}/校办月报", reason="已核对校办报表总结期、计划期及实际填写内容")


def classify_monthly(path: Path, root: Path) -> Decision:
    name = normalized(path.name)
    if not MONTHLY_HINT.search(name):
        return Decision("ignored")
    if name.startswith("~$") or path.suffix.lower() in {".tmp", ".bat", ".cmd", ".ps1", ".py", ".exe"}:
        return Decision("ignored")
    if re.search(r"进度表|教学质量|质量工作月报|报送通知|提交统计|收集情况", name):
        return Decision("skip", reason="进度表、通知或教学质量月报，不属于本次两类月报")
    if path.suffix.lower() != ".xlsx":
        return Decision("review", reason="月报需核对当期Excel工作表；此格式请另存为xlsx后重试")
    try:
        sheets = [sheet for sheet in read_workbook(path) if not sheet.hidden and sheet.cells]
    except Exception as exc:
        return Decision("review", reason=f"无法读取月报工作表（{type(exc).__name__}），保留原处")
    if not sheets:
        return Decision("skip", reason="没有可读取的月报内容")
    year = _root_year(root)
    headline = " ".join(sheet.cells.get("A1", "") for sheet in sheets)
    school = bool(re.search(r"重点工作总结.*工作计划", name)) or any(sheet.name == "月度重点工作总结" for sheet in sheets)
    academy = bool(re.search(r"学院月报|学院院报", name)) or bool(re.search(r"健康.*学院", name + headline))
    if school:
        return _school(name, sheets, year)
    if not academy:
        return Decision("skip", reason="其他业务月报，不属于校办月报或学院月报")
    profiles = []
    for sheet in sheets:
        headers = " ".join(text for address, text in sheet.cells.items() if row_number(address) <= 2)
        if "副院长" in headers or ("人员" in headers and re.search(r"系.*部.*中心|管理中心|学工", headers)):
            profiles.append(_profile(sheet))
    if not profiles:
        return Decision("review", "学院月报", reason="未找到副院长或系部/管理中心/学工月报表头")
    hints = _name_hints(name)
    if hints:
        selected = [p for p in profiles if _matches(hints, p.values("summary", columns=True) or p.values("summary"), p.values("plan", columns=True) or p.values("plan"))]
        # A conflicting title may be the only part updated in a copied template.
        if not selected:
            selected = [p for p in profiles if _matches(hints, p.values("summary"), p.values("plan"))]
    else:
        selected = profiles
    if not selected:
        return Decision("review", "学院月报", reason="文件名报送期与表内总结/计划不符，保留原处待核对")
    labels = [label for profile in selected for label in profile.labels]
    summaries = {months for action, months, _ in labels if action == "summary" and months}
    plans = {months for action, months, _ in labels if action == "plan" and months}
    years = {y for action, _, y in labels if action == "summary" and y}
    plan_years = {y for action, _, y in labels if action == "plan" and y}
    reason = _validate_period(summaries, plans, years, year, hints, plan_years=plan_years, name=name)
    if reason:
        return Decision("review", "学院月报", reason=reason)
    if not any(p.has_data() for p in selected):
        return Decision("skip", "学院月报", reason="当期工作表未填写；旧月份内容不算本期月报")
    if re.search(r"模板|模版", name):
        return Decision("review", "学院月报", reason="文件仍带模板标记但已有内容，请核对是否为正式报表")
    period = _period_name(next(iter(summaries)))
    try:
        target_name, group, naming_note = _academy_name(selected, name, period, path.suffix)
    except ValueError as exc:
        return Decision("review", "学院月报", reason=str(exc))
    return Decision("ready", "学院月报", period, group, f"月报/{period}/学院月报",
                    f"已核对当期总结/计划；{naming_note}；整份保存，保留其他历史工作表", target_name=target_name)
