# Change Log

**Language**: English | [中文](CHANGELOG_ZH-CN.md)
**README**: [English](README_EN.md) | [中文](README_ZH-CN.md)

This English change log mirrors the project history maintained in `CHANGELOG_ZH-CN.md`. It keeps the same dated structure and preserves the operational notes that matter for later troubleshooting: what changed, why it changed, what failed or detoured, and how the work was verified.

## 2026-06-21

- **WeChat-like chat surface refined**: the roundtable chat area now uses a flatter desktop-chat shell, lighter header, larger gray conversation canvas, softer rounded bubbles, subtler avatars, and a compact provider status strip so the chat remains the primary visual focus.
- **Freechat speech pattern de-AI-ed**: removed the prompt and mock examples that encouraged repetitive starts such as "I add one point" / "I jump in". Freechat now asks for more natural openings based on the previous message and the speaker planner prevents the same seat from speaking twice in a row.
- **Chat bubbles rounded**: changed the chat message bubbles to softer four-corner rounded rectangles instead of pointed speech bubbles, matching a more familiar social-chat visual style.
- **Kimi timeout handling improved**: later freechat turns include longer transcript context and Kimi K2.x responses can take longer than the original 45-second default. The roundtable engine now gives Kimi K2.7 / K2.6 / K2.5 calls a 90-second timeout while keeping the shorter default for other providers.
- **Chat room styling moved closer to desktop social apps**: reduced the web-card feel with a lighter group header, larger gray chat canvas, narrower message bubbles, square avatars, subtle bubble tails, and softer time dividers.
- **Chat room visual style tightened**: adjusted the roundtable transcript from a web-card layout into a more familiar social-chat surface, with a white group header, light gray conversation area, square avatars, subtle time dividers, and plain gray-white message bubbles.
- **Kimi HTTP 400 fixed for K2.x models**: Kimi K2.7 Code rejects non-default sampling parameters, while the generic OpenAI-compatible adapter was sending `temperature: 0.7` to every provider. The adapter now omits temperature for Kimi K2.7 / K2.6 / K2.5 model names and keeps the DeepSeek / MiMo request shape unchanged.
- **Transcript redesigned as a chat room**: replaced the engineering-style transcript cards with a roundtable chat view. Messages now appear in chronological bubble form, with speakers labeled as `seat name - model name`, so the page reads more like a multi-person discussion and less like a run log.
- **Freechat provider coverage fixed**: after switching to short freechat turns, the first lightweight speaker planner could accidentally choose only seats assigned to DeepSeek and Kimi, leaving MiMo at `idle` with 0 calls even when it had assigned seats. The planner now selects at least one active seat per assigned provider before applying the irregular speaking pattern.
- **Zhongshengshi default flow changed to `freechat`**: user feedback showed that the previous opening/debate structure still felt like one LLM answer split across seats. The page now calls `/api/roundtable/run` with `mode: "freechat"` and a short message budget, so the transcript appears as a conversational stream rather than a fixed queue of essays.
- **Freechat prompt and mock behavior added**: added `buildFreechatPrompt`, a freechat engine path, and mock freechat samples. Each turn now receives the nearby transcript and is asked to respond, interrupt, distinguish, question, or add a concrete angle without repeating the topic.
- **Known limitation recorded**: the new speaker order is still a lightweight rule, not a real model-driven moderator. This improves the default feel, but true autonomous turn-taking and speech-value evaluation remain future work.
- **Verification**: added `tests/freechat.test.ts` and expanded the API and guide tests to cover freechat mode, short message output, non-linear speaker order, and the updated guide copy.
- **Fixed misleading low-quality Zhongshengshi mock output**: user feedback showed that clicking "Start roundtable" produced transcript items filled with topic repetition, generic statements, and plumbing-test text. The root cause was that mock provider mode was still enabled and the mock output was hard-coded as a connectivity probe. Reworked `src/lib/mock-provider.ts` so mock mode now emits phase-specific seat samples and the page clearly warns that mock mode is only for workflow testing.
- **Strengthened real-model prompt quality rules**: `src/lib/prompt-builder.ts` now requires opening speeches to start with a judgment, forbids topic repetition and generic "balanced view" filler, and requires debate speeches to respond to a concrete prior seat view. Added `tests/prompt-quality.test.ts` and mock quality assertions to prevent regression to low-value templates.
- **Separated Next.js dev and build cache directories**: investigation showed that running `next build` while `next dev` was active wrote into the same `.next` directory and left the dev server unable to find temporary chunks, causing homepage 500s. Added `next.config.mjs` so dev keeps `.next` while production builds use `.next-build`, and ignored the new build directory. Verification confirmed the 3000 dev page still returns 200 after a build.
- **Zhongshengshi browser-local draft recovery added**: while investigating the page returning to an empty setup after starting the roundtable, confirmed that Next.js development Fast Refresh / full page reloads can drop temporary React state. Added `src/lib/draft-state.ts` to persist and restore the topic, seat pool, parsed seats, selected seats, assignments, mock mode, and JSON editor state; page buttons now explicitly use `type="button"` to reduce accidental submit behavior in future layout changes.
- **Draft recovery verification**: added `tests/draft-state.test.ts` for draft serialization, parsing, and invalid persisted data handling. Browser verification confirmed that a test topic survives reload. `npm run lint`, `npm test`, `npm run typecheck`, and `npm run build` all passed.
- **Third Zhongshengshi provider corrected to Kimi**: the provider previously labeled MiniMax was corrected to Kimi. The page, types, mock provider, assignment preferences, README, and tests now consistently use `kimi` / `Kimi` / `KIMI_*`.
- **Legacy environment variable fallback kept**: to avoid breaking existing `.env.local` files immediately, the Kimi provider reads `KIMI_*` first and falls back to `MINIMAX_*` if needed. New configuration should use `KIMI_API_KEY`, `KIMI_BASE_URL`, and `KIMI_MODEL`.
- **Zhongshengshi seat pools moved to a compact workflow**: the parser now supports a short `seats` array where each seat only needs `seat_name`, `type`, `core_concern`, `typical_questions`, `must_do`, `must_not_do`, and `speaking_style`; other fields may be omitted.
- **Low-relevance competition preset added**: added `src/presets/low_relevance_competition.json` with the topic about whether low-alignment competitions benefit or harm students and six compact seats. The page now has a "Load sample seat pool" button that fills the topic and compact JSON.
- **Seat-card display tightened**: after parsing, the JSON editor is hidden by default and the page shows seat cards instead. Each card face shows only name, type, core concern, and speaking style; expanding the card shows typical questions, must-do, and must-not-do.
- **Prompt defaults for missing fields**: `prompt-builder` now adds generic constraints when `opening_prompt`, `debate_prompt`, `blind_spots`, `likely_opponents`, or `example_preference` are missing, so compact seats do not fail at runtime.
- **Zhongshengshi page guide added**: added a compact "Project Manual / User Guide" section at the top of the `zhongshengshi/` page, covering the fastest local workflow, real-provider setup, seat-pool format, result interpretation, and current limits.
- **Guide content modularized**: added `src/lib/guide.ts` for the guide content and a test confirming that the guide covers mock provider usage, starting the roundtable, API-key server boundaries, current phase scope, and no Streamlit adaptation for now.
- **Zhongshengshi minimum roundtable flow added**: `zhongshengshi/` now includes `/api/roundtable/run`, implementing opening statements plus one debate round. After entering a topic, parsing a seat pool, and selecting 4 to 6 seats, the user can start the roundtable and see each seat's opening and debate messages.
- **Prompt builder and model orchestration**: added `prompt-builder`, using seat name, type, core concern, typical questions, must-do / must-not-do rules, likely opponents, blind spots, style, example preference, and custom seat prompts for opening / debate prompts. Added a roundtable engine that calls the assigned provider for each seat.
- **Mock provider and non-blocking failures**: added a mock provider for local verification and tests without real API cost. A failed seat or provider call is recorded in the transcript and error log while the remaining seats continue.
- **API-key boundary tightened**: real provider calls read API keys only from `.env.local` / server environment variables. `/api/providers` and `/api/roundtable/run` do not return secrets.
- **Frontend transcript display**: the former control placeholder is now a run log showing pending / running / success / failed status, provider call counts, failure details, and the full transcript.
- **Current limits**: this phase only implements opening plus one debate round. Speech-value evaluation, missing-view detection, summary generation, multi-round orchestration, and SQLite / Prisma persistence remain future work.
- **Verification**: prompt, mock provider, roundtable engine, API route, and failure-path tests were added first and confirmed failing before implementation. After implementation, `npm test` passed 12 tests and `npm run typecheck` passed.
- **Added the Zhongshengshi local MVP subproject**: created an isolated Next.js + TypeScript + Tailwind CSS project under `zhongshengshi/` to validate the multi-model roundtable setup flow before adapting it into the existing Streamlit toolbox.
- **Completed steps 1-4**: the MVP now has the base page, topic input, seat-pool JSON paste and parsing, candidate-seat display, 4-to-6 seat selection, DeepSeek / MiMo / Kimi provider status, an OpenAI-compatible adapter foundation, and automatic seat assignment with at most two seats per model.
- **Protected API-key boundaries**: API keys are read only from `.env.local` / server environment variables. The browser receives only provider status, Base URL, and Model Name metadata.
- **Route decision recorded**: the Streamlit adaptation question was discussed. The current decision is to validate the MVP first, because the main risk is the roundtable and model-collaboration logic; after that works, the project can either be adapted into Streamlit, kept as a standalone Next.js tool, or have its core logic reused.
- **README updated**: documented how to run `zhongshengshi/`, how to fill environment variables, what is complete, and what comes next.
- **Verification**: parsing, provider, and assignment tests were written first and confirmed failing before implementation. After implementation, `npm test` passed 7 tests. Streamlit was not started according to project rules.

## 2026-06-09

- **Excluded glare palettes from Web Memo cards**: `data/color_palettes.md` was left unchanged, so "樱桃苏打" and "橘子派对" remain available as palette references. Web Memo cards no longer draw from those two palettes, preventing existing saved memos from rendering with large high-saturation blue, orange, or cherry-red surfaces.
- **Verification**: added a regression test confirming the palette library still contains the palettes while `build_memo_card_html` skips them and uses the next memo-display palette. Streamlit was not started according to project rules.

## 2026-06-08

- **Removed four palettes**: deleted "午夜歌剧" (Midnight Opera), "泡泡糖" (Bubblegum), "冬日庄园" (Winter Estate), and "西瓜夏天" (Watermelon Summer) from `data/color_palettes.md`.
- **Memo card color logic refactored**: card backgrounds now always use the least-saturated color from the palette, preventing high-saturation colors (e.g. electric blue, vivid orange, cherry red) from filling the entire card surface. Title and accent colors use the remaining two palette colors.
- **Adaptive body text color**: body text automatically switches between dark gray `#2D3436` on light backgrounds and light `#F0EDE8` on dark backgrounds, ensuring readability.
- **Clear color-role separation**: palette colors now serve as atmosphere (background), decoration (title), and accent (tags/date), while body text is independent from the palette. This resolves the issue where palette reference images looked good but memo cards did not — the three palette colors were never designed as "background + text + text."
- **Verification**: Playwright browser preview confirmed that high-saturation palettes like 橘子派对 and 樱桃苏打 no longer produce刺眼 backgrounds. Streamlit was not started per project rules.

## 2026-06-07

- **Fixed Codex Radar Actions push conflict**: GitHub Actions run #29 was investigated. `python -m codex_radar_lite.cli` had already succeeded; the failure was in `Commit radar data`. The job log showed `main -> main (fetch first)`, meaning another remote `main` commit landed before the workflow pushed its radar-data commit.
- **Radar workflow sync protection**: `.github/workflows/codex-radar.yml` now checks out full history, runs `git pull --ff-only origin main` before generating radar data, rebases with `git pull --rebase origin main` before pushing, and retries the push. If radar data did not change, the workflow exits without pushing an old HEAD.
- **Regression check added**: `tests/test_codex_radar_workflow.py` now checks that the workflow keeps the three protections: sync main before running, skip empty pushes, and rebase before push.
- **Verification**: the new workflow test was first run against the old workflow and failed as expected. After the fix, `tests.test_codex_radar_workflow` and `tests.test_codex_radar_lite` passed, and the `codex_radar_lite` package passed syntax checks. The first syntax-check command failed because PowerShell did not expand `*.py`; rerunning with an explicit file list passed. Streamlit was not started according to project rules.
- **Bilingual README and Change Log naming added**: the former Chinese `README.md` and `CHANGELOG.md` content is now preserved as `README_ZH-CN.md` and `CHANGELOG_ZH-CN.md`. New English documents were added as `README_EN.md` and `CHANGELOG_EN.md`. `README.md` and `CHANGELOG.md` remain GitHub-default entry files that mirror the English versions and link back to the Chinese versions.
- **Project rules updated**: `AGENTS.md` now records that future README or Change Log updates must maintain both Chinese and English versions by default.
- **Verification**: this was a documentation-only change. Streamlit was not started. Markdown patch formatting and whitespace were checked with `git diff --check`.
- **Web Memo card face tightened again**: after the poster-card direction was accepted, the remaining action buttons still hurt the card face. Move up, move down, edit, and hide were moved into the full-text expander so the collapsed card shows only the poster face.
- **Fixed poster title size**: poster-card title text no longer uses oversized responsive sizing. It now uses a fixed `1.62rem` size, with full reading handled by the expander when needed.
- **Verification**: `tests.test_web_memo_db` passed 32 tests. The Web Memo page and `utils/web_memo_db.py` passed `py_compile`. Streamlit was not started according to project rules.
- **Web Memo changed to poster-style cards**: the memo list moved from long note cards with color changes to `memo-card-poster`, using centered large text, strong color blocks, inner outline, heavier shadow, and compact tags.
- **Full content moved off the card face**: each card face now shows only the first sentence or first line excerpt. The complete memo remains available in the per-card full-text expander.
- **Dark text rule corrected**: the previous rule blocked neutral black but still allowed dark brown such as `#592E2E`, which visually read like black. Tests were added for near-black dark browns, and the text-color replacement now chooses a brighter same-palette color.
- **Removed the Business Blue palette**: the user explicitly disliked the current card appearance and requested removal of `商务蓝`. The palette was removed from `data/color_palettes.md`; existing memos now remap against the current palette pool.
- **Blocked neutral black card text**: card date, tags, and body text no longer choose near-black or gray-black neutral colors. If such a color is selected, the code prefers another non-black color from the same palette.
- **Verification**: tests confirmed that `商务蓝` is no longer in the palette pool and that neutral black such as `#1F1B1D` is not used as card text. `tests.test_web_memo_db` passed 30 tests; the Web Memo page and `utils/web_memo_db.py` passed `py_compile`.
- **Web Memo action area minimized**: move, edit, and hide actions were converted to compact symbolic buttons with hover help text, reducing interference with content and color presentation.
- **Existing memos confirmed against new color rules**: HTML generated from the two records in `data/web_memos_backup.md` now outputs `--card-text` and paired background/text styles instead of the old black-on-light design.
- **Cards now use palette-paired background and text colors**: memo cards no longer use "one background color plus fixed black text." Each card now pairs main, secondary, and light colors from the same palette.
- **Added two-color reversal modes**: card positions rotate through main background plus secondary text, secondary background plus main text, and light background plus main text. Date, palette name, tags, and body all use the same text-color variable.
- **Removed fixed black text and gradient decoration**: fixed dark values such as `#182230` and `#344054` were removed from card text. The side stripe now uses the current text color, and leftover linear-gradient decoration was removed from the page CSS.
- **Regression tests added**: tests confirm that `那不勒黄曙绿` can generate yellow-background/green-text and green-background/yellow-text modes, and that the CSS uses `--card-text` instead of fixed black.
- **Fixed duplicate cards after editing a memo**: editing a memo used to keep the old card and create a new card with the edited content. The cause was remote backup merge logic that identified memos by date plus content; once the content changed, the old remote memo was imported as a new record.
- **Stable memo IDs added to backups**: `data/web_memos_backup.md` now includes an `ID` system field. Imports prefer the stable ID to identify the same memo; old backups without IDs still fall back to normalized date plus content.
- **Cleaned duplicate remote memos**: after syncing the remote backup, four records were found, three of them duplicated versions of the same memo. The backup was reduced to two unique records and given ID, order, and status fields.
- **Automatic duplicate hiding**: during database startup, visible memos are checked for duplicates. Whitespace-only differences are treated as the same memo; one visible copy is kept and the rest are hidden.
- **Card actions moved into the card container**: move, edit, hide, and edit forms now live inside the same card container instead of appearing as external buttons below each card.
- **Reduced consecutive color collisions**: memo cards now rotate through the live palette pool by visible list position rather than depending on content hashes that can make adjacent similar memos use the same colors.
- **Removed the Blue Club palette**: the disliked `蓝调俱乐部` palette was removed from `data/color_palettes.md`.
- **Detour recorded**: while cleaning the backup file, the first PowerShell here-string attempt passed Chinese text to Python in a way that turned titles and field names into question marks. The file was then rewritten using Unicode escapes and read back to confirm the Chinese text was restored.
- **Added palettes 32-40**: nine two-color integrated palettes were extracted from the WeChat article `国际流行色彩搭配` and appended to `data/color_palettes.md`.
- **Palette preview verified**: after appending the palettes, the parser detected 40 palettes and the new range was 32-40. `tests.test_color_palette_preview` and the palette page syntax check passed. Streamlit was not started.
- **Web Memo GitHub backup hardened**: `utils/github_backup_sync.py` gained read-only remote backup reading. `utils/web_memo_db.py` gained memo import, merge, and deduplication logic. The Web Memo page now merges from remote backup at startup, checks remote content before save, and blocks empty-backup overwrite.
- **Data-loss prevention rule**: before Web Memo writes to GitHub, it reads remote `data/web_memos_backup.md`. If remote has memos and the current environment is empty, the write is blocked. If both sides have content, they are merged and deduplicated before writing.
- **Current data state confirmed**: both local and remote `data/web_memos_backup.md` were empty at that time, so previously lost online memos had no recoverable source. The fix prevents future empty-environment overwrites but does not claim to restore already lost data.
- **Memo card colors now follow the current palette library**: cards no longer use palette snapshots saved at creation time. They remap from the current `data/color_palettes.md`, so palette additions, removals, and adjustments affect existing cards consistently.
- **Removed template-made gradients from memo cards**: the unwanted gradient effect came from the card template rather than the palette data. Card backgrounds now use the current palette's third color directly, the side stripe uses the main color directly, and decorative translucent circles were removed.
- **Remote memo backup confirmed before push**: a remote `data: sync web memo backup` commit had added one memo record. The code push first incorporated that remote data to avoid overwriting it.
- **Remote data synced again before later push**: during edit/hide/move work, another remote `data: sync web memo backup` commit increased the backup to two records. Local code changes were rebased after the remote data commit.
- **Web Memo actions enhanced**: memos can now be edited, hidden, moved up, and moved down. Hidden memos remain in the backup and moving only adjusts `display_order`.
- **Backup format strengthened**: `data/web_memos_backup.md` gained order and status fields so card order and hidden state survive cross-deployment restore. Old backups remain compatible.
- **Card font chosen from preview testing**: memo card body text now uses a Kai-style font stack with Songti fallback to better fit excerpt-card reading.
- **Preview and tooling detour**: the first image-based preview attempt turned Chinese into question marks because of the Windows PowerShell encoding chain. A temporary `playwright-core` install under the system temp directory and local Chrome rendering were used to confirm the font. The temporary dependency was not added to the repository.
- **Why not fully random colors**: fully random colors would make cards visually jump on every refresh. The final approach uses stable selection while the palette library is unchanged, and remaps only when the palette library changes.
- **Documentation rule updated**: `AGENTS.md` was updated so changes that need a push also update the Change Log, and user-visible behavior changes update README when appropriate.
- **README updated**: README now documents the relation between Color Palette Preview and Web Memo, explains that `data/color_palettes.md` is the live memo-card color source, and records the `GITHUB_BACKUP_TOKEN` backup flow.
- **Design detour recorded**: the first response focused on confirming the remote memo backup was empty, which did not fully address how to avoid future data loss. The later implementation added remote merge, empty-overwrite blocking, and tests.
- **Testing and encoding detour**: some test additions initially failed because Windows console encoding and emoji path matching made patches and path assertions fragile. The tests were rewritten to locate page files by prefix and assert at the function level.
- **Verification**: `tests.test_github_backup_sync`, `tests.test_web_memo_db`, `tests.test_budget_db`, and `tests.test_color_palette_preview` passed. Web Memo page and related utility files passed `py_compile`. Empty `data/web_memos_backup.md` and local SQLite database files were not included in the commit.

## 2026-06-05

- **Added module 12: Codex Radar**: `pages/00_12、📡_Codex雷达.py` was added to connect Codex reset-window monitoring to the Streamlit toolbox.
- **Added the Codex Radar Lite core**: `codex_radar_lite/` became the lightweight monitoring module behind the 12th panel.
- **Hourly automation**: `.github/workflows/codex-radar.yml` runs hourly through GitHub Actions without Docker or a long-running server.
- **Rule-based status engine**: public sources are scanned for signals such as Codex, usage limit, rate limit, reset, and recovered, then classified as `normal`, `watch`, `high_probability`, `open`, or `closed`.
- **DingTalk notification support**: DingTalk robot push support was added. Webhook and optional signing secret are read only from GitHub Secrets.
- **Page display and fallback site**: the 12th Streamlit panel was added, and `codex_radar_lite/site/index.html` remains a static fallback status page.
- **Initial status data files**: `data/codex_radar_current.json`, `data/codex_radar_history.json`, and `data/codex_radar_signals.json` were added for first-run state.
- **Test coverage**: `tests/test_codex_radar_lite.py` covers signal extraction, rule judgment, history updates, RSS output, and safe no-webhook behavior.
- **Scope note**: the first version only supports DingTalk robot alerts. It does not add email fallback or personal WeChat alerts. Streamlit was not started; only code-level verification was used.

## 2026-05-28

- **Color Palette Preview compatibility fix**: the palette page was changed from soon-to-be-deprecated `streamlit.components.v1.html` to `st.html`.
- **Regression tests added**: `tests/test_color_palette_preview.py` now blocks reintroducing `streamlit.components.v1` and `components.html`.
- **Cache cleanup**: accidentally tracked `__pycache__/*.pyc` files were removed from Git tracking. Existing `.gitignore` rules now keep Python cache files out of commits.
- **Local dependency environment completed**: local virtual environment dependencies were brought in line with `requirements.txt`, including `python-docx` and `pypdf`, fixing full-test failures caused by missing `docx`.
- **Remote changes merged before push**: before pushing, the remote repository already had Recorder scan and data-sync commits. They were fetched, checked for overlap, and merged while preserving both remote additions and the palette-page fix.
- **Verification**: after merge, 48 unit tests passed, 39 Python files passed syntax checks, and the repository no longer contained `streamlit.components.v1` or `components.html`.

## 2026-05-25

- **Recorder cloud display sync**: added `data/ding_minutes_cloud.json` and `scripts/sync_recorder_cloud.py` so locally processed Recorder records can be displayed online.
- **Recorder reading optimized**: Recorder Notes reads the local database first, then falls back to the cloud JSON when online or when the local database is empty.
- **Recorder card experience improved**: records are shown in more compact cards, with cleaned notes, original transcript, and remarks inside expanders.
- **Recorder remarks sync**: saving remarks, generating cleaned notes, or finishing a daily scan refreshes the cloud display export.
- **Home-page navigation fixed**: home tool cards now use Streamlit-native page navigation, improving reliability across environments.
- **Back-to-home entry added**: every tool page now includes a fixed home entry.
- **Dependency added**: `requirements.txt` gained `pypdf` for Universal Merger PDF handling.
- **Recorder data synced**: Recorder records produced on the L laptop were synced for cloud viewing.

## 2026-05-24

- **Added Recorder Notes**: added the locked `Recorder_笔记` panel for registering DingTalk-exported Word transcripts, preserving original text, and generating AI-cleaned notes.
- **Recorder automatic scan**: added `scripts/scan_ding_minutes.py` and `config/ding_minutes.ini` to scan for new `export_*.docx` and `dt*.docx` files every day at 19:00.
- **DeepSeek cleanup integration**: added the DeepSeek call layer. API keys are read only from local `DEEPSEEK_API_KEY`, never from code, config, logs, or database files.
- **Recorder remarks and retry support**: the page supports remarks, status filtering, original text view, AI-cleaned note view, error prompts, and per-record retry.
- **Recorder password protection**: Recorder Notes reuses the Budget Tracker password from `budget_password`, `[budget].password`, or local `BUDGET_PASSWORD`.
- **L-laptop migration guide**: added `docs/ding_minutes_L_setup.md`.
- **Home page redesigned**: the home page became a dark Command Center cover with reverse chronological tool order and a fixed 3 x 3 grid per page.
- **Navigation order adjusted**: Streamlit sidebar page files were renamed with reverse-order prefixes so newer tools appear higher.
- **Added Web Memo**: added the `灵感便签盒` page for ideas, excerpts, TODOs, writing material, and tool concepts.
- **Web Memo tags and classification**: added existing/new tag support, auto classification, and three-column memo cards.
- **Web Memo backup**: added `data/web_memos_backup.md`; saves sync the backup, and empty databases try to restore from Markdown.
- **Budget ledger fields expanded**: quick entry gained a `spender` field, and record management, edit, export, and backup sync all support it.
- **Budget hard backups**: added `data/budget_ledger_backup.md` and `data/budget_ledger_backup.xlsx`.
- **Budget category adjusted**: added `年终奖留存`, a spending category without a fixed budget ceiling.
- **Budget restore support**: the ledger can be restored from backup Excel after explicit confirmation.
- **Page compatibility fixes**: fixed Streamlit Cloud errors in Web Memo caused by HTML rendering and tag-helper compatibility.
- **Project rules added**: added project-level `AGENTS.md`, defining that Streamlit must not be started for verification and that tests, syntax checks, and pure-function checks are preferred.
- **Tests added and updated**: budget ledger, Web Memo, home entry, and palette page tests were added or updated for backups, tags, page order, and home pagination.

## 2026-05-18

- **Budget page adjusted**: removed the annual-budget overview block so the page focuses on category dashboards, record management, and cross analysis.
- **WeChat Archiver upgraded**: the local archive window gained four routes: raw, college, research-topic, and competition.
- **Launcher organized**: kept `启动微信归档窗口.bat`, fixed the local archive port at `8502`, and removed the duplicate English launcher script.
- **Tests added**: added tests for WeChat archive route recognition, local file copy, and launcher port behavior.

## 2026-05-17

- **Color Palette Preview upgraded**: the palette page moved from vertical color strips to compact mood, color-role, and PPT-application preview cards.
- **Layout improved**: adjusted the page columns, preview-card size, color-code width, and HTML rendering to improve information density at 100% zoom.
- **Tests added**: added `tests/test_color_palette_preview.py`.
- **Added Color Palette Preview module**: added `pages/09_9、🎨_配色方案预览.py`, reading color data from `data/color_palettes.md`.
- **Palette data added**: extracted eight business-style three-color palettes from a WeChat article and added them as palette entries 7-14.
- **Helper scripts added**: `exports/` received temporary helper scripts for color-card image downloads, batch OCR, and region recognition.
- **Project cleanup**: removed the `AGENTS.md` that duplicated `CLAUDE.md`; added `.gitignore` for `__pycache__/`, `.claude/`, `.venv/`, `*.db`, and related generated files.

## 2026-05-15

- **Schedule lookup rebuilt**: schedule data no longer depends on a local Excel file after first parse; it is cached as JSON in `data/schedule_cache.json`.
- **Path fix**: Excel paths changed from absolute paths to project-relative `data/` paths so cloud deployment works.
- **Deployment fix**: fixed Streamlit Cloud failures caused by missing local Excel files.
- **Dependency added**: `requirements.txt` gained `openpyxl`.

## 2026-05-04

- **Structure improved**: `README.md` was rewritten to define the project as a college administration, teaching, and research efficiency toolbox.
- **Added WeChat Archiver module**: added the 7th page entry for the WeChat Archiver.
- **Feature description clarified**: documented that WeChat Archiver runs locally and the online page is only a feature display.
- **Architecture organized**: unified the Streamlit multi-page navigation structure and visual style.
