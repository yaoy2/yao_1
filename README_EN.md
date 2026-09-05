# yao_1 | Academic Administration Command Center

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_svg.svg)](https://yao-1.streamlit.app/)

**Languages**: English | [简体中文](README_ZH-CN.md)
**Change logs**: [English](CHANGELOG_EN.md) | [中文](CHANGELOG_ZH-CN.md)

> 前方没有胜利，挺住意味一切。

A Streamlit toolbox for everyday faculty administration, teaching assessment, knowledge capture, and project showcases. This repository also contains five independent subprojects, each with its own operating instructions and data boundaries.

## Where to Start

- **Use the toolbox**: open the [online app](https://yao-1.streamlit.app/). The homepage has Administration, Teaching, Personal, and archived sections.
- **Start a grading task**: read M18 first, then create the formal task in M17.
- **Archive WeChat articles or local files**: use the local `启动微信归档窗口.bat` launcher after reading the [WeChat archiving guide](docs/guides/wechat-archiver.md).
- **Configure Recorder scanning**: follow the [local setup and migration guide](docs/guides/ding_minutes_L_setup.md), confirming the target folder before running.
- **Understand the workspace**: see the [documentation index](docs/README.md) and [repository map](docs/repository-structure.md).
- **Browse the source**: [GitHub repository](https://github.com/yaoy2/yao_1).

## Local Installation, Launch, and Checks

Use Windows with a working Python 3 installation and network access for the initial setup. [requirements.txt](requirements.txt) defines the runtime dependencies: Streamlit serves the app, spreadsheet/document libraries handle Excel, Word, and PDF files, and Playwright supports local WeChat article retrieval.

1. Get the repository:
   ```powershell
   git clone https://github.com/yaoy2/yao_1.git
   cd yao_1
   ```
2. Double-click `首次安装.bat` to create the repository's `.venv` and install runtime and test dependencies.
3. Double-click `启动YaoYao工具箱.bat` to launch the main app.
4. Double-click `运行测试.bat` to check the main app. If it fails, retain the error output and distinguish missing dependencies from a failing feature check.

You can also check the main app explicitly from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
```

The main application's test scope is `tests/`. Run independent subproject tests through their own documented entry points; do not mix them through an unscoped root pytest run. Development verification uses tests, syntax checks, and pure-function checks; repository rules prohibit starting a local Streamlit service merely for a preview.

The dedicated WeChat window uses `http://localhost:8502`, separately from the main toolbox. It uses the installed Microsoft Edge browser and does not require a separate Playwright Chromium installation. This window performs archiving; the toolbox's M07 page explains the workflow.

## Twenty-Two Current Tool Modules

Module numbers preserve introduction order and are intentionally discontinuous. There are **22 entries: Administration 6, Teaching 2, Personal 7, and archived 7**. Fifteen belong to the current sections; seven remain for historical reference. [hello.py](hello.py) is the source of truth for sections and page entries. There is no fixed second-page placement or featured-card section.

### Administration

| ID | Module | Purpose and boundary |
| --- | --- | --- |
| M20 | Ding2026 File Transfer and Distribution | Read-only desensitized aggregate status, manual distribution, transfer review, and five archive timelines; no connection to real material folders. |
| M15 | Email Notice Editor | Notice parsing, layout preview, and export; the [standalone HTML editor](assets/email_notice_editor.html) can be downloaded and used offline. |
| M14 | Todo List | Chinese due-date/time recognition, search, soft archiving, local backup, and GitHub synchronization; requires the shared access password. |
| M11 | Recorder Notes | Registers Word transcripts, retains source text, uses DeepSeek for rewriting, and stores remarks; password-protected, with scheduled scanning handled locally. |
| M08 | Budget Tracker | Expense and reimbursement tracking, category balances, ledger export, and recovery backups; requires the shared access password. |
| M06 | Schedule Browser | Searches timetable Excel data and JSON caches by teacher, department, weekday, and other fields. |

### Teaching

| ID | Module | Purpose and boundary |
| --- | --- | --- |
| M18 | Grade Workbench Guide | Explains the workflow, scoring definitions, file locations, cross-computer state, and common questions. |
| M17 | Teaching Grade Workbench | Manages rosters, group roadshow/report source scores, personal coefficients, and adjustment layers; validates and exports review workbooks without rewriting original group scores. |

### Personal

| ID | Module | Purpose and boundary |
| --- | --- | --- |
| M23 | docker-monitor | Read-only 2×2 view of four Docker tasks: TrendRadar, GLM promotions, AIHOT increments, and Amazon.de GPU quotes. |
| M22 | GPT Planner · Luna Executor | Read-only description of Sol orientation, Luna execution, and ChatGPT Web planning/review; the page does not call models or execute tasks. |
| M21 | Awesome Design MD | Searches, selects, and displays 74 brand design references; local and deployed pages share the same pinned asset snapshot. |
| M19 | Concept Fable Gallery | Searches and displays Chinese fables, definitions, and story mappings stored in `data/concept_fables.json`; the page is read-only. |
| M10 | Web Memo | Captures ideas, quotations, and material with tags, palettes, ordering, hiding, Markdown/PDF export, and GitHub backup merging. |
| M09 | Color Palette Preview | Displays palettes and usage examples from `data/color_palettes.md`, also the source of memo-card colors. |
| M07 | WeChat Archiver | Explains raw / faculty / course / competition routes; retrieval and local copying use the dedicated local window, while IMA upload belongs to a separate workflow. |

M20, M22, and M23 are documentation or showcase pages: opening them does not start the corresponding external projects. TrendRadar remains a separate local container; the other three M23 tasks live in the independent private [docker-monitor repository](https://github.com/yaoy2/docker-monitor), sharing one DingTalk channel. Amazon.de quotes are described as a EUR list price plus a CNY estimate using `EUR × 1.13 × 7.79 + 150`. The page never accesses the network, starts containers, reads local state or live prices, or sends DingTalk messages.

### archived: Historical Entries

| ID | Module | Status |
| --- | --- | --- |
| M16 | Legacy Report Grading and Grade Linkage | Replaced by M17; do not create formal grading tasks here. |
| M13 | LLM Budget Tracker | Archived; balance and account-management implementation retained for reference. |
| M05 | Universal Merger | Retired implementation retained. |
| M04 | Word Reaper | Retired implementation retained. |
| M03 | Roster Checker | Retired implementation retained. |
| M02 | File Comparator | Retired implementation retained. |
| M01 | Report Grading | The old prompt-based scoring workflow is deprecated. |

These entries retain source code and red-cross status; their presence does not make them recommended current workflows. M12 was removed. Historical stock-related M19 log entries refer to a different project from today's Concept Fable Gallery.

## Five Independent Subprojects

| Subproject | Current purpose and status | Entry point |
| --- | --- | --- |
| Deepself | Implemented personal-expression research, a writing Skill, and a standalone reply tool; original social posts, screenshots, and private reports stay local. | [Project guide](Deepself/README.md); `Deepself/启动Deepself对话框.bat` |
| Zhongshengshi | Next.js multi-model roundtable proof of concept, paused since 2026-08-11; source and verification records retained. | [Project guide](zhongshengshi/README.md) |
| Codex → Grok Builder | Controlled Codex planning, Grok Build implementation, and Codex acceptance workflow. | [English guide](codex-grok-builder/README_EN.md) |
| GPT Planner · Luna Executor | Controlled Sol / Luna / ChatGPT Web collaboration Skill; M22 only explains the workflow. | [Skill and execution boundaries](gpt-planner-luna-executor/SKILL.md) |
| 115 AI Organizer | Read-only scanning, classification reports, and human review; directory creation, renaming, and moving require approval, a verified manifest, and a matching confirmation code. No deletion interface. | [Project guide and latest handoff](115-ai-organizer/README.md) |

These subprojects have their own launch, dependency, and permission requirements. Cloning this repository does not start them or enable monitoring, archiving, or cloud-drive organization.

## Storage, Recovery, and Another Computer

Streamlit Cloud and the local computer are separate runtime environments. The deployed app cannot read this computer's folders or environment variables. A `git pull` retrieves committed files; it does not restore ignored databases, credentials, or private material.

| Feature | Main storage | Recovery and migration |
| --- | --- | --- |
| M08 Budget | `data/budget.db`; `budget_ledger_backup.md/.xlsx` | An empty database can restore from the local Markdown backup; configured GitHub synchronization writes the Markdown backup remotely. |
| M10 Memos | `data/web_memos.db`; `web_memos_backup.md` | Supports backup restoration; configured synchronization merges remote records and protects existing remote content. |
| M14 Todos | `data/todos.db`; `todo_items_backup.md` | Supports backup restoration and remote-record merging when configured; completed items remain through soft archiving. |
| M11 Recorder | `data/ding_minutes.db`; `ding_minutes_cloud.json` | Local scanning stores source text and rewrites; the deployed page reads the cloud export and can synchronize remarks. Consult the migration guide first. |
| M17 Grading | `data/grade_workbench/tasks/<task-ID>/task.db` and task attachments | No automatic GitHub synchronization; retain the complete task directory when migrating and export review workbooks separately. |

`data/` contains business records, not disposable caches. Remote GitHub backups are the meeting point for dynamic data: synchronize before editing local backups, merge conflicts, and never overwrite current records with stale or empty files. Export important material regularly and keep an additional controlled backup.

## Credentials, External Services, and Local Boundaries

- **Shared password**: M08, M11, and M14 use Streamlit Secrets `budget_password` / `[budget].password`; local execution also accepts the `BUDGET_PASSWORD` environment variable.
- **AI rewriting**: Recorder accepts Secrets or local `DEEPSEEK_API_KEY`. Transcript content is sent to the configured API provider when rewriting is requested. Without a key, source text can be registered without generating an AI rewrite.
- **GitHub backup**: enabling `GITHUB_BACKUP_TOKEN` through Secrets or the local environment sends relevant backup content to the configured repository. A local save alone does not mean the data is backed up across computers.
- **Local archiving**: WeChat retrieval accesses articles over the network and writes results to confirmed folders. GoogleDrive or similar sync clients may then upload those files. Check destinations before use; do not automatically fill sensitive paths.
- **Deepself**: submitted messages and the abstract style profile pass through the chosen model provider; the app does not read or upload private source posts.
- **Credential handling**: keep real keys in Secrets, environment variables, or the subproject's designated local credential location, never in source code, commits, or logs.

## Documentation and Maintenance

- [Documentation index](docs/README.md): current guides, historical designs, and visual previews.
- [Repository map](docs/repository-structure.md): responsibilities of the main app, subprojects, assets, dynamic data, and generated folders.
- [WeChat archiving guide](docs/guides/wechat-archiver.md) / [Recorder setup and migration](docs/guides/ding_minutes_L_setup.md).
- [English Change Log](CHANGELOG_EN.md) / [中文更新日志](CHANGELOG_ZH-CN.md): actual changes, failed attempts, and corrections.

`README.md` mirrors `README_EN.md`; `CHANGELOG.md` mirrors `CHANGELOG_EN.md`. Keep current behavior descriptions aligned across languages. Historical design documents do not override current code and repository rules.

## License

There is no standalone root `LICENSE` yet; reuse permissions must be established separately. Third-party design assets retain their own [provenance](assets/awesome-design-md/SOURCE.md) and licenses independently of the repository's root licensing status.
