# yao_1 | Academic Administration Command Center

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_svg.svg)](https://yao-1.streamlit.app/)

**Language**: English | [Simplified Chinese](README_ZH-CN.md)
**Change Log**: [English](CHANGELOG_EN.md) | [中文](CHANGELOG_ZH-CN.md)

> **"There is no victory ahead; holding the line is everything."**

`yao_1` is a Streamlit toolkit for the day-to-day work of a college-level academic office. It covers to-do tracking, document processing, roster checks, schedule lookup, budget tracking, WeChat article archiving, color-palette reference, web memos, and DingTalk recorder note cleanup.

The project is built around real administrative, teaching-support, competition-guidance, and knowledge-management workflows. The default design preference is local-first, simple, maintainable, and practical enough to become a stable button instead of a one-off script.

---

## Repository Structure

This repository contains one main application and five independent subprojects.

- **Main application**: the Streamlit / YaoYao toolbox at the repository root. The entry points are `hello.py` and `启动YaoYao工具箱.bat`. Internal directories such as `pages/`, `utils/`, `scripts/`, `config/`, `assets/`, and `tests/` belong to this application; they are not separate subprojects.
- **Deepself** ([`Deepself/`](Deepself/README.md)): an initialized independent subproject. Goals, scope, and implementation are not defined yet.
- **Zhongshengshi** ([`zhongshengshi/`](zhongshengshi/README.md)): a paused independent Next.js multi-model roundtable proof of concept. Active development and deployment stopped on 2026-08-11.
- **Grok Builder** ([`codex-grok-builder/`](codex-grok-builder/README.md)): an active independent Codex skill that runs a controlled Codex-plan / Grok-implement loop.
- **GPT Planner · Luna Executor** ([`gpt-planner-luna-executor/`](gpt-planner-luna-executor/SKILL.md)): an independent Codex skill for the controlled Sol / Luna / ChatGPT Web collaboration workflow.
- **115 AI Organizer** ([`115-ai-organizer/`](115-ai-organizer/README.md)): an independent read-only 115-drive organization project with its own application package and test entry point.

---

## Current Entry Points

- **Online app**: [yao-1.streamlit.app](https://yao-1.streamlit.app/)
- **Repository**: [github.com/yaoy2/yao_1](https://github.com/yaoy2/yao_1)
- **docker-monitor (M23)**: a read-only 2×2 view of four local Docker tasks (TrendRadar, GLM promo radar, AIHOT increments, Amazon.de GPU quotes with EUR list price plus CNY estimate). Real monitoring lives in [yaoy2/docker-monitor](https://github.com/yaoy2/docker-monitor) and the local TrendRadar container; the deployed page never runs the monitors.
- **GPT Planner · Luna Executor (M22)**: a read-only explanation of the controlled Sol planning, Luna execution, and ChatGPT Web planning/review workflow.
- **Awesome Design MD (M21)**: read-only browsing of 74 bundled brand `DESIGN.md` references; local and deployed pages use the same pinned asset snapshot.
- **Ding2026 File Transfer and Distribution (M20)**: presents desensitized aggregate status, manual distribution, transfer review, five archive timelines, and rollback boundaries without connecting to real material folders.
- **Concept Fable Gallery (M19)**: turns abstract concepts into searchable Chinese fables with definitions and story mappings.
- **Grade Workbench Guide (M18)**: explains the M17 workflow, score definitions, file locations, cross-computer status, and common questions.
- **Teaching Grade Workbench (M17)**: manages rosters, group roadshow/report source scores, contribution coefficients, adjustment layers, validation, and review-workbook export.
- **Legacy Grade Linkage (M16)**: replaced by M17 and marked with a red cross for historical reference; it remains between M17 and M15 in module-number order.
- **Todo List**: the 14th locked tool panel. It records tasks newest-first, extracts common Chinese date/time hints, supports search, soft-archives completed tasks, and keeps `data/todo_items_backup.md` as a GitHub-syncable recovery file.
- **LLM Budget Tracker**: the 13th tool panel, showing balances for supported LLM providers, including Gemini, and keeping editable login-account and expiration-date labels in `data/llm_budget_accounts.json`.
- **Home style**: a compact home surface organized by Administration, Teaching, Personal, and archived sections; module cards and featured entries come from `hello.py` metadata.
- **Navigation order**: module codes and sections in `hello.py` are the single source of truth, independent of page filename prefixes or special insertion rules.
- **Repository map**: [`docs/repository-structure.md`](docs/repository-structure.md) records the boundaries between the main app, independent subprojects, read-only assets, and local generated state.

---

## Zhongshengshi MVP

`zhongshengshi/` is the local Web MVP for "众声室". It validates the core roundtable flow before deciding whether to adapt the tool into the existing Streamlit toolbox.

Completed so far:

- Created an isolated Next.js + TypeScript + Tailwind CSS subproject.
- Built the single-page structure: topic input, seat-pool paste area, seat selection, provider status, seat assignment, and roundtable control placeholders.
- Added seat-pool JSON parsing with support for common Chinese and English field names.
- Added 4-to-6 seat selection validation.
- Added DeepSeek, MiMo, and Kimi provider configuration status. API keys are read only from `.env.local` / server environment variables and are not returned to the browser.
- Added a basic OpenAI-compatible Chat Completions adapter so incompatible providers can be swapped later.
- Added automatic seat assignment: each model gets at most two seats, with keyword preferences for DeepSeek, MiMo, and Kimi.
- Added `/api/roundtable/run`, which can run the original structured opening/debate flow and the newer `freechat` mode used by the page by default.
- Added a prompt builder using seat name, type, core concern, typical questions, must-do / must-not-do rules, likely opponents, blind spots, speaking style, example preference, and seat-specific prompts.
- Added a mock provider for local verification and tests without spending real API calls. Real providers still run through server-side environment variables and OpenAI-compatible Chat Completions calls.
- The frontend now displays run status, provider status, error logs, and the full transcript as a message stream. A failed provider or seat call does not stop the rest of the roundtable.
- The page now includes a "Project Manual / User Guide" section covering the fastest local workflow, real-provider setup, seat-pool format, result interpretation, and current limits.
- Added compact seat-pool support: the runtime only needs a `seats` array, with each seat containing `seat_name`, `type`, `core_concern`, `typical_questions`, `must_do`, `must_not_do`, and `speaking_style`.
- Added a "Load sample seat pool" button backed by the `low_relevance_competition` preset. It fills the topic and six compact seats, then hides the long JSON after parsing so the user works from seat cards.
- Added browser-local draft recovery for the topic, seat pool, parsed seats, selected seats, seat assignments, mock mode, and JSON editor state, so a page reload or development-server Fast Refresh does not force the user to rebuild the setup from scratch.
- Reworked mock-provider output and real-model prompt quality rules: mock mode is now clearly positioned as a flow test and no longer emits plumbing-test filler; real prompts explicitly forbid topic repetition, generic "balanced view" answers, and agreement without a concrete target.
- Added `freechat` roundtable mode: the page now asks seats to speak in short, conversational turns, respond to nearby messages, interrupt or add concrete distinctions, and avoid predictable one-seat-after-another essays.
- Redesigned the transcript as a roundtable chat room: each message is shown as a chronological social-chat bubble with a role avatar and `seat name - model name` speaker label.

Local run:

```powershell
cd zhongshengshi
npm install
Copy-Item .env.local.example .env.local
npm run dev
```

The page enables "mock provider" by default for local verification. Mock mode only checks the workflow and does not represent real discussion quality. To call real models and evaluate roundtable output quality, turn it off and configure at least two providers in `.env.local`.

`.env.local` fields:

```text
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=
DEEPSEEK_MODEL=

MIMO_API_KEY=
MIMO_BASE_URL=
MIMO_MODEL=

KIMI_API_KEY=
KIMI_BASE_URL=
KIMI_MODEL=
```

Compatibility note: legacy `MINIMAX_API_KEY` / `MINIMAX_BASE_URL` / `MINIMAX_MODEL` values are still read as Kimi fallback values, but new setups should use `KIMI_*`.

Current limits:

- The page now defaults to a lightweight `freechat` message flow; the older opening/debate path remains available in the engine for tests and later comparison.
- Speaker selection is still rules-based, not a real model-driven moderator. True autonomous turn-taking, speech-value evaluation, missing-view detection, final summary, and persistence are still pending.
- Real providers use OpenAI-compatible Chat Completions by default. Any incompatible provider will need its own adapter extension.

Development was paused on 2026-08-11. The source, tests, and proof-of-concept result remain available, but moderator models, persistence, summarization, and deployment will not be expanded unless a concrete new need appears. See [`zhongshengshi/README.md`](zhongshengshi/README.md) for the durable project record.

---

## Twenty-Two Current Tool Modules

Module numbers track launch order, so the current sequence is no longer continuous. Homepage order and sections come from metadata in `hello.py`. Red-cross modules are retained for history only and should not be used for new work.

### 1. Report Grading System

- **Use case**: batch grading for final projects, lab reports, and similar submissions.
- **What it does**: extracts text and image counts from Word/PDF files, then supports AI-assisted grading and score aggregation.

### 2. File Comparator

- **Use case**: checking whether student-submitted filenames match roster requirements and finding missing submissions.
- **What it does**: compares a roster with a target folder in real time, identifies missing files, wrong submissions, and naming anomalies, and supports dynamic header detection.

### 3. Roster Checker

- **Use case**: aligning administrative summary sheets with a standard roster.
- **What it does**: compares custom Excel ranges, such as `C2:C52`, and returns overlapping and different names between two lists.

### 4. Word Reaper

- **Use case**: extracting structured data from graduation registration forms, political review forms, and other complex Word tables.
- **What it does**: performs batch extraction, separates undergraduate and graduate data, recognizes merged cells, and exports a clean Excel summary.

### 5. Universal Merger

- **Use case**: merging many documents or archiving many spreadsheets.
- **What it does**:
  - **Documents**: merges dozens of Word/PDF files into one Word document, including logic for PDFs with copy restrictions.
  - **Spreadsheets**: merges multiple Excel files into one workbook with multiple sheets.

### 6. Schedule Browser

- **Use case**: fast internal schedule lookup for the college.
- **What it does**: reads cached schedule data from JSON and supports searches by teacher, department, weekday, teaching week, and class period.
- **Data refresh**: place a new Excel file in `data/`, refresh the page, and the cache is regenerated automatically.

### 7. WeChat Archiver

- **Use case**: permanently saving useful WeChat public-account articles, teaching cases, competition notices, and research references.
- **What it does**:
  - **Four archive routes**: `raw`, college, research-topic, and competition archives.
  - **Playwright browser capture**: opens WeChat articles in a real browser context to capture dynamically rendered content.
  - **Local image storage**: downloads article images into local `assets` folders to avoid hotlinking issues.
  - **Local file archiving**: copies research-topic and competition files into the corresponding Google Drive directory; IMA uploads remain handled by WorkBuddy.
  - **Fixed local port**: the local archiver uses `http://localhost:8502`, separate from the main toolbox on `8501`.
  - **Note**: this module is a local script; the online app only displays the feature entry.

### 8. Budget Tracker

- **Use case**: quickly recording and monitoring annual college budget spending.
- **What it does**:
  - **Quick entry**: select category and unit, enter spender, details, and amount, then save.
  - **Live dashboard**: shows category balances and spending by unit.
  - **Status management**: each expense can be marked as pending reimbursement, reimbursed, or voided.
  - **Cross analysis**: category-by-unit pivot table for comparing budget distribution.
  - **Export**: exports all or filtered ledger records to Excel.
  - **Hard backup**: saves and restores through `data/budget_ledger_backup.md` and `data/budget_ledger_backup.xlsx`.
  - **Special category**: `year-end bonus reserve` accumulates actual spending without participating in fixed-budget balance calculations.

### 9. Color Palette Preview

- **Use case**: color references for slides, posters, and lightweight visual design.
- **What it does**: reads palette data from local Markdown and displays each palette through mood blocks, color roles, and PPT-style application previews.
- **Data**: palettes live in `data/color_palettes.md`; this file is also the live color source for Web Memo cards.

### 10. Web Memo

- **Use case**: quickly capturing temporary ideas, excerpts, TODOs, writing material, work notes, and tool concepts.
- **What it does**:
  - **Fast capture**: saves memo content with the current date.
  - **Tag management**: supports both existing and new tags.
  - **Auto classification**: assigns initial categories such as excerpt, opinion, TODO, writing material, work record, tool idea, and quote.
  - **Waterfall layout**: cards are displayed in three columns, newest first; the card face shows a poster-like excerpt while full content stays inside an expander.
  - **Card actions**: each memo supports move up, move down, edit, and hide actions.
  - **Safe deletion**: hiding a memo removes it from the default list but keeps it in the GitHub backup ledger.
  - **Live palette mapping**: memo cards use the current palettes from `data/color_palettes.md` instead of frozen palette snapshots saved at memo creation time. The background always uses the least-saturated palette color; title and accent use the remaining two; body text adapts to background luminance. The memo display pool skips glare-prone palettes such as "樱桃苏打" and "橘子派对" while keeping their original color values in the palette library.
  - **GitHub backup**: saves to `data/web_memos_backup.md` through `GITHUB_BACKUP_TOKEN`; startup restores and merges from the remote backup before writing, preventing empty environments from overwriting existing remote memos.
  - **Export**: supports Markdown and PDF export.

### 11. Recorder Notes

- **Use case**: cleaning up DingTalk recorder transcripts, meeting discussions, interviews, seminars, and other spoken materials.
- **What it does**:
  - **Daily scan**: with Windows Task Scheduler, scans `C:\Users\Yao\Downloads` at 19:00 for new `export_*.docx`, `dt*.docx`, and files whose names contain `原文`.
  - **Original retention**: extracts Word text and stores filename, path, creation time, modification time, and processing status.
  - **AI cleanup**: calls DeepSeek to turn spoken transcripts into reusable notes, without forcing a rigid meeting-minutes template.
  - **Manual notes**: supports remarks for purpose, handling decision, and follow-up actions.
  - **Access lock**: reuses the Budget Tracker password from `budget_password`, `[budget].password`, or local `BUDGET_PASSWORD`.
  - **Migration guide**: L-laptop setup is documented in `docs/ding_minutes_L_setup.md`.

### 13. LLM Budget Tracker

- **Use case**: tracking LLM API balances and subscription-plan spending across DeepSeek, Kimi, MiMo, ChatGPT, and Gemini.
- **What it does**:
  - **Automatic balances**: reads configured API keys from Streamlit Secrets and queries supported providers.
  - **Manual balances**: keeps manual balance entries for providers that do not expose a supported balance API.
  - **Login-account labels**: each provider card has an editable account field for an email or phone number, with the input and save button kept on the same row.
  - **Expiration labels**: each provider can store a manual `expiration date: yy_mm_dd` value below the account field, saved with the account in `data/llm_budget_accounts.json`.
  - **GitHub backup**: when `GITHUB_BACKUP_TOKEN` is configured, saved account labels are synced back to GitHub so redeploys or repository refreshes do not wipe them.

### 14. Todo List

- **Use case**: tracking daily tasks, due dates, completion status, and archived records.
- **What it does**: recognizes common Chinese date/time phrases, supports search and soft archive, stores local SQLite data, and maintains a Markdown recovery backup.

### 15. Email Notice Editor

- **Use case**: turning a pasted notice into a structured, previewable, exportable email page.
- **What it does**: recognizes subject, notice number, body, signature, and date, with browser preview and HTML export.

### 16. Legacy Report Grading and Grade Linkage (Replaced)

- **Status**: replaced by M17, kept only for historical reference, marked with a red cross, and pinned to homepage page two.
- **Rule**: do not create new official grading tasks in M16.

### 17. Teaching Grade Workbench

- **Use case**: managing rosters, roadshows, level-three project reports, personal contribution coefficients, and final-score adjustments.
- **Rule**: group source scores, personal converted scores, and global/group/personal adjustments are stored separately. Adjustments never rewrite roadshow or report source scores.
- **Data status**: tasks currently live under local `data/grade_workbench/`; cross-computer grading-data sync is not enabled yet.

### 18. Grade Workbench Guide

- **Use case**: quickly confirming what M18, M17, and M16 mean after a long gap between grading sessions.
- **What it does**: documents the six-step workflow, score definitions, file locations, cross-computer cautions, and common questions.

### 19. Concept Fable Gallery

- **Use case**: turning hard-to-remember abstract concepts into searchable, rereadable Chinese fables.
- **What it does**: stores the domain definition, fable, and mapping from each concept to story elements.

### 20. Ding2026 File Transfer and Distribution

- **Use case**: showing how college administrative materials are identified, manually distributed, reviewed in transfer, and archived across distinct time scopes.
- **Boundary**: the page reads only a desensitized aggregate snapshot bundled with the repository. It never accesses real files, databases, Google Drive, or the independent Ding2026 runtime and exposes no operational controls.

### 21. Awesome Design MD

- **Use case**: finding brand design-system references for page design and AI-generated interfaces.
- **What it does**: filters and renders 74 bundled `DESIGN.md` files in read-only mode, using the same pinned assets locally and in deployment.

### 22. GPT Planner · Luna Executor

- **Use case**: explaining how complex local work is divided among Sol, Luna, and ChatGPT Web within explicit boundaries.
- **Boundary**: the page only presents roles, packets, and review stages. It does not create agents, call models, control a browser, or modify projects.

### 23. docker-monitor

- **Use case**: one Personal-category page that lays out four Docker tasks in a 2×2 square: TrendRadar, GLM promo radar, AIHOT increments, and Amazon.de GPU quotes (EUR list price plus CNY estimate).
- **Boundary**: the page does not access the network, start containers, read local state, or send DingTalk. Real monitoring is pulled from the private [yaoy2/docker-monitor](https://github.com/yaoy2/docker-monitor) repo and run in local Docker; TrendRadar stays a separate container. No extra sidebar entry is added.

---

## Quick Start

### Online Use

Open the [Streamlit Cloud app](https://yao-1.streamlit.app/) to use most tools without local installation.

### Local Deployment

Local deployment is recommended for WeChat archiving and large batches of private files.

1. Clone the repository.

   ```bash
   git clone https://github.com/yaoy2/yao_1.git
   cd yao_1
   ```

2. Run the first-time installer.

   Double-click `首次安装.bat`. It creates the project-local `.venv` and installs both runtime and test dependencies.

3. Start the toolbox.

   Double-click `启动YaoYao工具箱.bat`.

4. Verify the project.

   Double-click `运行测试.bat`. If it reports a failure, keep the error text and pass it to Codex for diagnosis.

### Recorder Notes Local Setup

`Recorder Notes` is the 11th panel and is best used on a fixed local computer.

The online Streamlit app cannot read local PowerShell environment variables. For online use, configure `DEEPSEEK_API_KEY` in Streamlit Cloud Secrets.

1. Confirm the project path.

   ```text
   E:\github\yao_1
   ```

2. Install dependencies.

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Configure local environment variables.

   - `DEEPSEEK_API_KEY`: used by DeepSeek for transcript cleanup. Do not write it into code, config files, logs, or GitHub.
   - `BUDGET_PASSWORD`: only needed when running locally without Streamlit secrets. It should match the Budget Tracker password.

   Example:

   ```powershell
   [Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", "your-real-key", "User")
   # Only for local runs without Streamlit secrets:
   [Environment]::SetEnvironmentVariable("BUDGET_PASSWORD", "your-budget-password", "User")
   ```

   Reopen PowerShell or restart the computer after setting environment variables.

   Streamlit Cloud Secrets example:

   ```toml
   DEEPSEEK_API_KEY = "your-real-key"
   ```

4. Confirm the scan path.

   The scan path is configured in `config/ding_minutes.ini`. The default example is:

   ```ini
   watch_dir = C:\Users\Yao\Downloads
   daily_run_time = 19:00
   model = deepseek-v4-pro
   ```

   If DingTalk exports Word files elsewhere, only change `watch_dir`. Do not place API keys in the `.ini` file.

5. Run one manual scan.

   ```powershell
   python scripts\scan_ding_minutes.py
   ```

   If the folder does not exist, check `watch_dir`. If `DEEPSEEK_API_KEY` is missing, reopen PowerShell and try again.

6. Schedule the daily 19:00 scan.

   In Windows Task Scheduler, create a basic task:

   - Name: `Ding Minutes Scan`
   - Trigger: daily at 19:00
   - Action: start a program
   - Program/script: `python`
   - Arguments:

     ```text
     scripts\scan_ding_minutes.py
     ```

   - Start in:

     ```text
     E:\github\yao_1
     ```

For L-laptop migration and detailed Task Scheduler setup, see [docs/ding_minutes_L_setup.md](docs/ding_minutes_L_setup.md).

---

## Security and Privacy

- **Privacy first**: file-processing tools prefer in-memory work; Budget Tracker and Web Memo write local data and backup files when the feature requires it.
- **Local first**: sensitive tools, such as WeChat Archiver, are designed for local use.
- **No secrets in Git**: DeepSeek API keys, DingTalk webhooks, GitHub backup tokens, and passwords must stay in environment variables, Streamlit secrets, or GitHub Secrets.
- **Locked panels**: Budget Tracker and Recorder Notes share the same access password.
- **Backup policy**: Budget Tracker and Web Memo maintain local backup files and may write GitHub backup ledgers through `GITHUB_BACKUP_TOKEN`. Web Memo merges remote backup content before writing so an empty environment cannot overwrite existing remote memos. Important data should still be exported periodically as a manual fallback.

## License

The repository does not currently include a standalone `LICENSE` file. Choose and add a license before formally redistributing the project or granting reuse rights.

## Change Log

See [CHANGELOG_EN.md](CHANGELOG_EN.md). The Chinese version is [CHANGELOG_ZH-CN.md](CHANGELOG_ZH-CN.md).

---

Built by [Yao Yao]. Issues and suggestions are welcome.
