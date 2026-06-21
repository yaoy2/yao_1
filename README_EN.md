# yao_1 | Academic Administration Command Center

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_svg.svg)](https://yao-1.streamlit.app/)

**Language**: English | [Simplified Chinese](README_ZH-CN.md)
**Change Log**: [English](CHANGELOG_EN.md) | [中文](CHANGELOG_ZH-CN.md)

> **"There is no victory ahead; holding the line is everything."**

`yao_1` is a Streamlit toolkit for the day-to-day work of a college-level academic office. It covers document processing, roster checks, schedule lookup, budget tracking, WeChat article archiving, color-palette reference, web memos, DingTalk recorder note cleanup, and Codex reset-window monitoring.

The project is built around real administrative, teaching-support, competition-guidance, and knowledge-management workflows. The default design preference is local-first, simple, maintainable, and practical enough to become a stable button instead of a one-off script.

---

## Current Entry Points

- **Online app**: [yao-1.streamlit.app](https://yao-1.streamlit.app/)
- **Repository**: [github.com/yaoy2/yao_1](https://github.com/yaoy2/yao_1)
- **Zhongshengshi MVP**: `zhongshengshi/`, a local Next.js subproject for validating the multi-model roundtable flow. The current version can run opening statements plus one debate round.
- **Codex Radar**: the 12th tool panel, reading `data/codex_radar_current.json` to display Codex reset-window status.
- **Home style**: a dark Command Center cover; tools are listed in reverse launch order, with a fixed 3 x 3 grid per page.
- **Sidebar navigation**: all tools are ordered from newest to oldest, so recently added modules appear first.

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
- Added `/api/roundtable/run`, which runs the minimum roundtable flow: opening statements for every selected seat, then one debate round.
- Added a prompt builder using seat name, type, core concern, typical questions, must-do / must-not-do rules, likely opponents, blind spots, speaking style, example preference, and seat-specific prompts.
- Added a mock provider for local verification and tests without spending real API calls. Real providers still run through server-side environment variables and OpenAI-compatible Chat Completions calls.
- The frontend now displays run status, provider status, error logs, and the full transcript. A failed provider or seat call does not stop the rest of the roundtable.
- The page now includes a "Project Manual / User Guide" section covering the fastest local workflow, real-provider setup, seat-pool format, result interpretation, and current limits.
- Added compact seat-pool support: the runtime only needs a `seats` array, with each seat containing `seat_name`, `type`, `core_concern`, `typical_questions`, `must_do`, `must_not_do`, and `speaking_style`.
- Added a "Load sample seat pool" button backed by the `low_relevance_competition` preset. It fills the topic and six compact seats, then hides the long JSON after parsing so the user works from seat cards.
- Added browser-local draft recovery for the topic, seat pool, parsed seats, selected seats, seat assignments, mock mode, and JSON editor state, so a page reload or development-server Fast Refresh does not force the user to rebuild the setup from scratch.

Local run:

```powershell
cd zhongshengshi
npm install
Copy-Item .env.local.example .env.local
npm run dev
```

The page enables "mock provider" by default for local verification. To call real models, turn it off and configure at least two providers in `.env.local`.

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

- The flow currently runs opening plus one debate round only; there is no complex multi-round orchestration yet.
- Speech-value evaluation, missing-view detection, final summary, and persistence are still pending.
- Real providers use OpenAI-compatible Chat Completions by default. Any incompatible provider will need its own adapter extension.

Next steps:

- Add speech-value evaluation so not every seat has to speak in every debate round.
- Add missing-view detection and final summary.
- Add SQLite / Prisma persistence for rooms, seats, messages, and summaries.
- After the core flow works, decide whether to adapt it into Streamlit or keep it as an independent local Web tool.

---

## Twelve Core Modules

The module numbers match the Streamlit sidebar. Newer tools have larger numbers and appear higher in the sidebar.

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

### 12. Codex Radar Lite

- **Use case**: monitoring Codex quota reset windows so likely reset or recovery periods are not missed.
- **What it does**:
  - **Hourly monitor**: runs through GitHub Actions every hour, without Docker or a long-running server.
  - **Rule-based judgment**: reads public sources and classifies status using signals such as Codex, limit, reset, and recovered.
  - **Toolbox display**: appears as the 12th panel with current status, evidence, historical windows, and push-notification notes.
  - **DingTalk alerts**: sends alerts when a high-probability window appears, opens, or closes.
  - **Secret protection**: DingTalk webhook and signing secret live only in GitHub Secrets.

---

## Codex Radar Lite

Codex Radar Lite is the monitoring module behind the 12th toolbox panel.

- **Workflow**: `.github/workflows/codex-radar.yml` runs hourly.
- **Judgment**: a rule engine reads public sources first; it does not call a large model by default.
- **Data files**: `data/codex_radar_current.json`, `data/codex_radar_history.json`, and `data/codex_radar_signals.json`.
- **Streamlit page**: `pages/00_12、📡_Codex雷达.py`.
- **Static fallback**: `codex_radar_lite/site/index.html`.
- **DingTalk push**: alerts only for high-probability, open, or closed reset windows.

Required GitHub repository secrets:

- `DINGTALK_WEBHOOK`: DingTalk robot webhook.
- `DINGTALK_SECRET`: optional signing secret if DingTalk signature verification is enabled.

Local checks:

```bash
python -m unittest tests.test_codex_radar_lite
python -m py_compile codex_radar_lite/*.py
python -m codex_radar_lite.cli --dry-run
```

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

2. Create a virtual environment and install dependencies.

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Start the toolbox.

   ```bash
   streamlit run hello.py
   ```

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

This project is documented as using the [MIT License](LICENSE).

## Change Log

See [CHANGELOG_EN.md](CHANGELOG_EN.md). The Chinese version is [CHANGELOG_ZH-CN.md](CHANGELOG_ZH-CN.md).

---

Built by [Yao Yao]. Issues and suggestions are welcome.
