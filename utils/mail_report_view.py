"""Readable HTML for saved mail reports, without activating mail-supplied markup."""

import re
from datetime import datetime, timedelta, timezone
from html import escape


REPORT_CSS = """
.mail-report {max-width:1120px; color:inherit; font-size:.9rem; line-height:1.65;}
.mail-report h3 {font-size:1rem; font-weight:650; margin:1.05rem 0 .5rem; padding:0;}
.mail-report p {margin:.25rem 0 .65rem;}
.mail-report .mail-report-note {color:#64748b; font-size:.8rem; margin:0 0 .7rem;}
.mail-report table {width:100%; border-collapse:collapse; table-layout:fixed; margin:.4rem 0 .9rem;}
.mail-report th {text-align:left; font-size:.8rem; font-weight:600; background:#f4f6f8; color:#475569;}
.mail-report th, .mail-report td {padding:.65rem .8rem; border:1px solid #e4e8ed; vertical-align:top; overflow-wrap:anywhere;}
.mail-report th:first-child {width:32%;}
.mail-report td strong {font-weight:600;}
.mail-report .mail-category {display:block; color:#64748b; font-size:.76rem; margin-top:.2rem;}
.mail-report article {border:1px solid #e4e8ed; border-radius:9px; padding:.75rem .9rem; margin:.55rem 0;}
.mail-report .mail-action-title {display:flex; align-items:baseline; flex-wrap:wrap; gap:.35rem .6rem; margin-bottom:.45rem;}
.mail-report .mail-action-title strong {font-weight:650;}
.mail-report .mail-action-state {background:#f3f4f6; border-radius:5px; color:#596579; padding:.1rem .4rem; font-size:.75rem;}
.mail-report dl {display:grid; grid-template-columns:1.1fr 1fr 1fr; gap:.55rem .9rem; margin:0;}
.mail-report dl div {min-width:0; overflow-wrap:anywhere;}
.mail-report dt {font-size:.76rem; color:#64748b; font-weight:400; margin:0 0 .1rem;}
.mail-report dd {margin:0; font-size:.85rem;}
.mail-report .mail-deadline dd {font-weight:600;}
.mail-report .mail-requirement {grid-column:1 / -1; border-top:1px solid #eef0f3; padding-top:.5rem;}
.mail-report .mail-report-audit {border-top:1px solid #e4e8ed; margin-top:1rem; padding-top:.55rem; color:#64748b; font-size:.8rem;}
.mail-report .mail-report-audit summary {cursor:pointer; font-weight:500;}
.mail-report .mail-report-audit p {margin:.4rem 0;}
.mail-status-bar {display:flex; align-items:center; flex-wrap:wrap; gap:.45rem 1rem; margin:.2rem 0; font-size:.82rem; color:#596579;}
.mail-status-bar .mail-status-chip {background:#edf2f7; color:#40556e; border-radius:5px; padding:.2rem .5rem; font-weight:600;}
.mail-status-bar .mail-attachment-pending {color:#946200;}
@media (max-width:680px) {
  .mail-report th, .mail-report td {padding:.5rem;}
  .mail-report dl {grid-template-columns:1fr; gap:.45rem;}
  .mail-report article {padding:.65rem .7rem;}
}
"""


def _text(value):
    # Encode Markdown punctuation too: the host uses Markdown to deliver this
    # fixed HTML, and must never reinterpret a mail-derived link or image.
    text = escape(str(value or ""), quote=True)
    for char in "!*_[]`()":
        text = text.replace(char, f"&#{ord(char)};")
    return text.replace("\n", "<br>")


def report_title(report):
    title = str(report.get("title") or "邮件报告")
    report_date = str(report.get("date") or "")
    if not report_date:
        return title
    if title.startswith(report_date + " "):
        title = title[len(report_date):].strip()
    return f"{report_date} · {title}"


def _action_html(line):
    match = re.fullmatch(
        r"- \*\*(.+?)\*\*｜截止：(.*?)｜责任：(.*?)｜要求：(.*?)｜提交至：(.*)",
        line, re.DOTALL,
    )
    if not match:
        return None
    heading, deadline, owner, requirement, recipient = match.groups()
    parts = heading.split(" · ")
    badges = []
    while len(parts) > 1 and parts[0] in {"待处理", "进行中", "待确认", "已逾期", "今日到期", "时间待确认"}:
        badges.append(parts.pop(0))
    title = " · ".join(parts)
    state = '<span class="mail-action-state">' + _text(" · ".join(badges)) + "</span>" if badges else ""
    fields = "".join(
        f'<div class="{css}"><dt>{label}</dt><dd>{_text(value) or "待确认"}</dd></div>'
        for label, value, css in (
            ("截止时间", deadline, "mail-deadline"),
            ("责任对象", owner, "mail-owner"),
            ("提交至", recipient, "mail-recipient"),
            ("具体要求", requirement, "mail-requirement"),
        )
    )
    return f'<article><div class="mail-action-title"><strong>{_text(title)}</strong>{state}</div><dl>{fields}</dl></article>'


def _audit_text(text):
    match = re.fullmatch(r"未完成附件：(\d+)；最近成功游标：(.*)。", text)
    if not match:
        return text
    count, through = match.groups()
    if through == "尚无":
        return f"附件待补：{count} 份。尚未完成首次完整检查。"
    try:
        moment = datetime.fromisoformat(through.replace("Z", "+00:00"))
        if moment.tzinfo is not None:
            moment = moment.astimezone(timezone(timedelta(hours=8)))
        through = moment.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        pass
    return f"附件待补：{count} 份。已完整检查至：{through}。"


def report_body_html(markdown):
    """Format the historical report itself; never substitute today's task state."""
    content, audit, mail_rows = [], [], []
    section = ""

    def flush_mail_table():
        if mail_rows:
            content.append('<table><thead><tr><th>邮件事项</th><th>内容摘要</th></tr></thead><tbody>'
                           + "".join(mail_rows) + "</tbody></table>")
            mail_rows.clear()

    # Join wrapped paragraphs, while retaining the generator's section and item
    # boundaries. Unknown text is always kept as inert text.
    blocks = []
    for raw in str(markdown or "").splitlines():
        line = raw.strip()
        if not line:
            blocks.append("")
        elif (blocks and blocks[-1]
              and not blocks[-1].startswith(("# ", "## ", "统计时间：", "覆盖状态："))
              and not line.startswith(("# ", "## ", "- ", "统计时间：", "覆盖状态："))):
            blocks[-1] += "\n" + line
        else:
            blocks.append(line)

    for line in blocks:
        if not line:
            continue
        if not section and (line.startswith("# ") or line.startswith("统计时间：")):
            continue  # The report expander already provides its title and times.
        if line.startswith("覆盖状态："):
            note = line.removeprefix("覆盖状态：").strip()
            note = {
                "归档尚未覆盖完整统计窗口，以下仅为已读取内容。": "仅包含已读取的邮件，该时段尚未检查完整。",
                "本统计窗口已核验完整。": "该时段已检查完整。",
            }.get(note, note)
            content.append('<p class="mail-report-note">' + _text(note) + "</p>")
            continue
        if line.startswith("## "):
            flush_mail_table()
            section = line[3:].strip()
            if section != "采集核对":
                label = {"邮件概览": "邮件概览", "待处理与时间节点": "需要处理"}.get(section, section)
                content.append("<h3>" + _text(label) + "</h3>")
            continue
        if section == "采集核对":
            audit.append("<p>" + _text(_audit_text(line)) + "</p>")
            continue
        if section == "邮件概览":
            message = re.fullmatch(r"- \[([^\]\n]+)\] (.*)", line, re.DOTALL)
            if message:
                category, text = message.groups()
                subject, separator, summary = text.partition("：")
                mail_rows.append('<tr><td><strong>' + _text(subject) + '</strong><span class="mail-category">'
                                 + _text(category) + "</span></td><td>" + _text(summary if separator else "摘要待整理") + "</td></tr>")
                continue
        flush_mail_table()
        action = _action_html(line) if section == "待处理与时间节点" else None
        content.append(action or "<p>" + _text(line.removeprefix("- ")) + "</p>")
    flush_mail_table()
    if audit:
        content.append('<details class="mail-report-audit"><summary>查看采集详情</summary>' + "".join(audit) + "</details>")
    if not content:
        content.append("<p>此报告尚未提供正文。</p>")
    return '<div class="mail-report">' + "".join(content) + "</div>"
