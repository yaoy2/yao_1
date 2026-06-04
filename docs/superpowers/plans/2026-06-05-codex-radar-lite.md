# Codex Radar Lite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight Codex reset radar inside `yao_1` with hourly GitHub Actions, static JSON/Page output, and DingTalk alerts.

**Architecture:** A small Python package under `codex_radar_lite/` collects public signals, evaluates rule-based status, writes static outputs, and sends DingTalk only on important state changes. A static page reads `data/codex_radar_current.json` directly.

**Tech Stack:** Python 3.11, requests, BeautifulSoup, unittest, GitHub Actions, GitHub Pages static files, DingTalk robot webhook.

---

### Task 1: Core Data Model And Rules

**Files:**
- Create: `codex_radar_lite/models.py`
- Create: `codex_radar_lite/rules.py`
- Test: `tests/test_codex_radar_lite.py`

- [x] Define `Signal` and `RadarState` dataclasses with JSON conversion helpers.
- [x] Implement rule evaluation for `normal`, `watch`, `high_probability`, `open`, and `closed`.
- [x] Verify open and closed keywords trigger the expected status.

### Task 2: Collectors And Outputs

**Files:**
- Create: `codex_radar_lite/collectors.py`
- Create: `codex_radar_lite/storage.py`
- Create: `codex_radar_lite/feed.py`
- Create: `config/codex_radar_sources.json`
- Create: `config/codex_radar_rules.json`

- [x] Fetch HTML sources with a clear user agent.
- [x] Extract relevant lines into structured signals.
- [x] Write current state, history, signals, and RSS output.

### Task 3: DingTalk Alert Adapter

**Files:**
- Create: `codex_radar_lite/notifiers.py`

- [x] Read `DINGTALK_WEBHOOK` and optional `DINGTALK_SECRET` from environment variables.
- [x] Skip sending when no webhook is configured.
- [x] Push only when the current state is important and differs from the previous state.

### Task 4: Static Page And GitHub Actions

**Files:**
- Create: `codex_radar_lite/site/index.html`
- Create: `codex_radar_lite/site/app.js`
- Create: `codex_radar_lite/site/style.css`
- Create: `.github/workflows/codex-radar.yml`

- [x] Build a compact status page that reads static JSON.
- [x] Add an hourly scheduled workflow.
- [x] Commit generated data changes from GitHub Actions.

### Task 5: Local Verification

**Files:**
- Create: `tests/test_codex_radar_lite.py`

- [x] Run targeted unit tests.
- [x] Run Python compile checks for the new package.
- [x] Run a dry-run CLI check without sending DingTalk.

