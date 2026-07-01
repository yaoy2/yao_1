from html import escape


def text_to_body_html(body_text):
    lines = [line.strip() for line in str(body_text or "").splitlines() if line.strip()]
    return "\n".join(f"<p>{escape(line)}</p>" for line in lines)


def format_chinese_date(date_value):
    if not date_value:
        return ""
    parts = str(date_value).split("-")
    if len(parts) != 3:
        return str(date_value)
    year, month, day = parts
    return f"{int(year)}年{int(month)}月{int(day)}日"


def _normalize_number(value, default, min_value, max_value, decimals=0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    number = min(max(number, min_value), max_value)
    if decimals:
        return round(number, decimals)
    return int(round(number))


def build_notice_html(
    header,
    subject,
    number,
    unit,
    date_value,
    body_html,
    font_family="仿宋, FangSong, serif",
    font_size="19px",
    line_height=1.8,
    indent="2em",
    table_width_pt=521.3,
    header_height_px=58,
):
    header_text = escape(header or "成都东软学院健康医疗科技学院")
    subject_text = escape(subject or "通知")
    number_text = escape(number or "")
    unit_text = escape(unit or "")
    date_text = escape(format_chinese_date(date_value))
    width_pt = _normalize_number(table_width_pt, 521.3, 360, 700, decimals=1)
    detail_width_pt = max(width_pt - 74, 200)
    header_height = _normalize_number(header_height_px, 58, 40, 120)
    line_height_value = _normalize_number(line_height, 1.8, 1, 3, decimals=1)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{subject_text}</title>
    <style>
        body {{ margin: 0; font-family: '微软雅黑', sans-serif; background: #fff; }}
        p {{ margin: 0; }}
        img {{ max-width: 100%; height: auto; box-sizing: border-box; }}
        @media print {{ table {{ page-break-inside: avoid; }} body {{ margin: 0; }} }}
    </style>
</head>
<body>
    <div align="center" style="line-height:1.43;">
        <table border="1" cellspacing="0" style="width:{width_pt:g}pt;border-collapse:collapse">
            <tbody>
                <tr>
                    <td colspan="2" style="border:1pt double double solid #4472c4;background:#2f5496;padding:3.75pt;width:{width_pt:g}pt;height:{header_height}px">
                        <p style="text-align:center;line-height:15.75pt;margin:0;">
                            <span style="font-family:华文中宋;font-size:22pt;color:#fff"><b>{header_text}</b></span>
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="border:1pt solid solid solid double #4472c4;padding:3.75pt;width:74pt;height:37px">
                        <p style="text-align:center;margin:0;">
                            <span style="font-family:宋体;font-size:14pt;color:#004898"><b>通知主题</b></span>
                        </p>
                    </td>
                    <td style="border:1pt solid double solid #4472c4;padding:3.75pt;width:{detail_width_pt:.1f}pt;height:37px">
                        <p style="text-align:justify;line-height:15.75pt;margin:0 0 0 6.6pt">
                            <b><span style="font-family:宋体;color:#333;font-size:14pt">{subject_text}</span></b>
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="border:1pt solid solid solid double #4472c4;padding:3.75pt;width:74pt;height:37px">
                        <p style="text-align:center;margin:0;">
                            <span style="font-family:宋体;font-size:14pt;color:#004898"><b>通知编号</b></span>
                        </p>
                    </td>
                    <td style="border:1pt solid double solid #4472c4;padding:3.75pt;width:{detail_width_pt:.1f}pt;height:37px">
                        <p style="text-align:justify;line-height:15.75pt;margin:0 0 0 6.6pt;">
                            <span style="font-family:宋体;font-size:14pt;color:#333"><b>{number_text}</b></span>
                        </p>
                    </td>
                </tr>
                <tr>
                    <td colspan="2" style="border:1pt solid double #4472c4;padding:3.75pt;vertical-align:top;width:{width_pt:g}pt;height:20px">
                        <p style="text-align:center;margin:0;">
                            <span style="font-family:华文中宋;font-size:14pt;color:#004898"><b>通 知 内 容</b></span>
                        </p>
                    </td>
                </tr>
                <tr>
                    <td colspan="2" style="border:1pt solid double #4472c4;padding:3.75pt 30px;vertical-align:top;width:{width_pt:g}pt;min-height:95px">
                        <div style="font-family:{escape(font_family)}; font-size:{escape(font_size)}; line-height:{line_height_value:g}; text-align:justify; text-indent:{escape(indent)}; color:#000000; overflow:hidden;">
                            {body_html or ""}
                        </div>
                        <div style="text-align:right; margin-top:20px; font-family:仿宋, FangSong, serif; font-size:19px; color:#000000; line-height:1.8;">
                            <p style="margin:0;"><b>{unit_text}</b></p>
                            <p style="margin:0;"><b>{date_text}</b></p>
                        </div>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
</body>
</html>"""
