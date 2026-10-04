# Module catalog / 模块目录

[Project home](../../README.md) · [Repository map](../repository-structure.md) · [Getting started](getting-started.md)

The registry in [hello.py](../../hello.py) is authoritative. There are **27 entries: 16 in current sections and 11 archived**. Some current entries are documentation or read-only showcases; each row states its actual boundary.

| Section | Entries |
| --- | --- |
| Administration | 5 |
| Teaching | 1 |
| Personal | 10 |
| Archived | 11 |

| ID | Section | Status | Entry point | Behavior and requirements |
| --- | --- | --- | --- | --- |
| M28 | Personal | Current | [Newspaper](../../pages/27_28_newspaper.py) | Aggregates public news, official AI RSS and literary/film coverage with original source links and publication dates. Browser-local recommendations learn from reading and explicit feedback while reserving cross-topic and discovery slots. Public articles use extracted text where available; official AI feeds remain attributed summaries with original links. Clippings, notes and recommendation preferences stay in the current browser; cross-device synchronization is not connected. |
| M27 | Personal | Current | [众声室](../../pages/26_27_ai_discussion_room.py) | Opens the local Codex / Claude / Grok discussion room. Requires the local launcher and signed-in CLI tools; unavailable participants are skipped. The hosted page does not run CLI tools or hold chat sessions. |
| M26 | Personal | Current | [PUBG 密室地图](../../pages/25_26_pubg_secret_maps.py) | Views bundled map images with zoom, pan, and original-image download. Paramo and Karakin are excluded. |
| M25 | Administration | Current | [随手传](../../pages/24_25_phone_transfer.py) | Paired phone-to-desktop transfer; the receiving desktop page must remain open. Requires configured transfer services. |
| M24 | Archived | Archived | [邮件工作台](../../pages/23_24_mail_workbench.py) | Retired from navigation; retained for historical reference. Current mail todos follow the Edge-based workflow. |
| M23 | Personal | Current | [docker-monitor](../../pages/22_23_docker_monitor.py) | Read-only showcase of three independent tasks: TrendRadar, AIHOT, and Amazon.de GPU quotes. Does not run containers or fetch live prices. |
| M22 | Personal | Current | [Planner-Executor](../../pages/21_22_gpt_planner_luna_executor.py) | Explains development-assistant routes and recorded evaluations; does not create agents or call models. |
| M21 | Personal | Current | [Awesome Design MD](../../pages/20_21_awesome_design_md.py) | Browses 74 pinned design references with retained source attribution and third-party licensing. |
| M20 | Archived | Archived | [Ding2026 文件中转发放系统](../../pages/19_20_ding2026.py) | Retired. Former functionality and statistics are no longer active; the page only shows retirement information. |
| M19 | Personal | Current | [概念寓言馆](../../pages/18_19_concept_fables.py) | Searches and reads stored fables and concept mappings; the page does not write entries. |
| M18 | Teaching | Current | [评分工作台使用说明](../../pages/17_18_grade_workbench_guide.py) | Historical guide for the retired M16/M17 workflows and retained data locations. |
| M17 | Archived | Archived | [教学评分工作台](../../pages/16_17_grade_workbench.py) | Retired. The page only shows retirement information; task creation, data editing, scoring, and export are disabled. Source code, tasks, inputs, and outputs are retained. |
| M16 | Archived | Archived | [旧版报告评分与成绩联动](../../pages/15_16_report_grader.py) | Retired. The page only shows retirement information; report import, scoring, and gradebook generation are disabled. Historical source code and materials are retained. |
| M15 | Administration | Current | [邮件通知编辑器](../../pages/15_0_email_notice.py) | Parses, previews, and exports notices. The [single-file editor](../../assets/email_notice_editor.html) works offline. Institution defaults still require review. |
| M14 | Administration | Current | [待办清单](../../pages/14_todos.py) | Chinese deadline recognition, search, soft archiving, backups, and configured GitHub synchronization. Shared access required; chat operations use conflict/retry checks. |
| M13 | Archived | Archived | [LLM 余额管理](../../pages/00_13_llm_budget.py) | Retained historical balance/account implementation. |
| M11 | Archived | Archived | [Recorder_笔记](../../pages/02_11_recorder.py) | Retired. The page only shows retirement information; scan, export, and synchronization entry points are disabled. Existing records and backups are retained. |
| M10 | Personal | Current | [灵感便签盒](../../pages/03_10_memos.py) | Notes, tags, colors, ordering, Markdown/PDF export, and configured GitHub backup merging. |
| M09 | Personal | Current | [配色方案预览](../../pages/04_9_palette.py) | Reads reusable palettes and examples. |
| M08 | Administration | Current | [预算速记台账](../../pages/05_8_budget.py) | Tracks expenses, reimbursements, category balances, export, and recovery backups. Shared access required. |
| M07 | Personal | Current | [微信归档](../../pages/06_7_wechat.py) | Explains the local archiving workflow; actual retrieval/copying uses the dedicated window. IMA upload is separate. |
| M06 | Administration | Current | [课表查询-2026-2027-1](../../pages/07_6_schedule.py) | Searches configured timetable workbooks/JSON by teacher, department, weekday, and related fields. |
| M05 | Archived | Archived | [万能合并机](../../pages/08_5_merger❌.py) | Retired implementation. |
| M04 | Archived | Archived | [Word 收割机](../../pages/09_4_word❌.py) | Retired implementation. |
| M03 | Archived | Archived | [名单核对](../../pages/10_3_checker❌.py) | Retired implementation. |
| M02 | Archived | Archived | [文件比对](../../pages/11_2_compare❌.py) | Retired implementation. |
| M01 | Archived | Archived | [报告评分](../../pages/12_1_scoring❌.py) | The former prompt-based scoring workflow is deprecated. |

M12 was removed. Module numbers preserve introduction order and are intentionally discontinuous. Independent subprojects are described separately in the [project overview](../../README.md).

中文：行政 5、教学 1、个人 10、归档 11；M11、M16、M17、M20、M24 已停用，M28 聚合公开新闻并在浏览器保存剪报，尚无跨设备同步；M27 为本机 AI 群聊入口，M25 需要本地组件，M26 查看仓库内地图图片，M23 当前只介绍三项任务。展示页不代表主库已经运行对应的外部系统。
