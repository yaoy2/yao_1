# Your first notice / 第一份通知

[Get started](getting-started.md) · [Standalone editor](../../assets/email_notice_editor.html)

This walkthrough uses fictional content. The editor formats a notice for human review; it does not distribute messages.

## 1. Open a local copy

Download `assets/email_notice_editor.html` with GitHub's **Download raw file** action and open the saved file in a desktop browser. The file has no external JavaScript or stylesheet dependency.

## 2. Paste this fictional notice

```text
关于开展教学工具体验活动的通知

示例通知〔2026〕12号

各位老师：
本通知仅用于演示，不对应真实活动。
一、体验内容
使用虚构材料体验通知排版与成绩复核。
二、提交方式
无需提交任何个人信息或真实教学记录。

示例学院教学办公室
2026年9月23日
```

Click **一键识别并填入**. Review the subject, body, issuing unit, and date.

## 3. Review the institution fields

The current editor was built for a specific college. Its header and notice-number prefix still use that institution's defaults, and the number is rebuilt from the recognized digits. The year is also template-specific.

Change editable institution fields to **示例学院（演示）** before inspecting the result. The notice-number prefix is not fully configurable in the current interface; do not send an exported sample as an actual institutional notice. Generalizing these defaults is a [planned improvement](roadmap.md).

中文：识别正文不等于机构字段已全部替换。当前文号前缀仍沿用原模板，示例输出只用于体验；正式使用前需逐项核对。

## 4. Preview and save

Check that the body remains readable, the date is `2026-09-23`, and the signing unit matches the sample. Choose **保存HTML文件**, then reopen the downloaded result to check it.

The editor itself does not send mail. Sending or publishing the exported content is a separate action.

## Implementation and checks

- [Python field parser](../../utils/email_notice_parser.py)
- [HTML renderer](../../utils/email_notice_renderer.py)
- [Standalone-file and JavaScript parser tests](../../tests/test_email_notice_standalone_html.py)
- [Python parser tests](../../tests/test_email_notice_parser.py)

The standalone file and Streamlit page are separate entry points. Keep their parsing behavior aligned when contributing.
