# Ding Minutes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build board 11 for daily DingTalk `.docx` transcript registration, DeepSeek-based cleanup, user remarks, and L-computer deployment guidance.

**Architecture:** Keep reusable logic outside Streamlit: configuration and scanning in `utils/ding_minutes.py`, persistence in SQLite, and a thin page in `pages/00_11、🎙️_钉钉纪要登记.py`. A standalone script runs one scan for Windows Task Scheduler, while the page can trigger the same scan manually.

**Tech Stack:** Python standard library, SQLite, `python-docx`, `requests`, Streamlit, `unittest`.

---

### Task 1: Configuration, Matching, and Time Window

**Files:**
- Create: `utils/ding_minutes.py`
- Create: `config/ding_minutes.ini`
- Test: `tests/test_ding_minutes.py`

- [ ] **Step 1: Write failing tests**

Cover `export_*.docx`, `dt*.docx`, non-matching names, and the 19:00 scanning window.

- [ ] **Step 2: Run the tests**

Run: `python -m unittest tests.test_ding_minutes -v`
Expected: fail because `utils.ding_minutes` does not exist yet.

- [ ] **Step 3: Implement minimal config and matching helpers**

Add `matches_ding_docx`, `build_scan_window`, and `load_config`.

- [ ] **Step 4: Run the tests**

Run: `python -m unittest tests.test_ding_minutes -v`
Expected: pass for matching and time window tests.

### Task 2: Database, Word Extraction, and Remarks

**Files:**
- Modify: `utils/ding_minutes.py`
- Test: `tests/test_ding_minutes.py`

- [ ] **Step 1: Write failing tests**

Cover database initialization, inserting a record, duplicate avoidance, listing newest first, and updating `remark`.

- [ ] **Step 2: Run the tests**

Run: `python -m unittest tests.test_ding_minutes -v`
Expected: fail because persistence functions do not exist yet.

- [ ] **Step 3: Implement SQLite persistence**

Add `init_db`, `upsert_file_record`, `get_records`, `update_remark`, `mark_done`, and `mark_failed`.

- [ ] **Step 4: Run the tests**

Run: `python -m unittest tests.test_ding_minutes -v`
Expected: pass.

### Task 3: DeepSeek Client and Scan Pipeline

**Files:**
- Modify: `utils/ding_minutes.py`
- Create: `scripts/scan_ding_minutes.py`
- Modify: `requirements.txt`
- Test: `tests/test_ding_minutes.py`

- [ ] **Step 1: Write failing tests**

Use a fake AI client and temporary `.docx` files to prove the scanner processes only files in the window, stores original text, writes AI output, and does not need a real API key in tests.

- [ ] **Step 2: Run the tests**

Run: `python -m unittest tests.test_ding_minutes -v`
Expected: fail because the scan pipeline is missing.

- [ ] **Step 3: Implement the scan pipeline**

Add `extract_docx_text`, `DeepSeekClient`, `build_ai_prompt`, `scan_once`, and the standalone script entrypoint.

- [ ] **Step 4: Run the tests**

Run: `python -m unittest tests.test_ding_minutes -v`
Expected: pass without network access.

### Task 4: Board 11 Page and Homepage Entry

**Files:**
- Create: `pages/00_11、🎙️_钉钉纪要登记.py`
- Modify: `hello.py`
- Test: `tests/test_ding_minutes.py`

- [ ] **Step 1: Write failing tests**

Add pure function tests for status labels or page-safe formatting if needed; keep Streamlit runtime out of tests.

- [ ] **Step 2: Implement the page**

Show counts, filters, manual scan button, original text, AI整理稿, editable remarks, and error messages.

- [ ] **Step 3: Add homepage entry**

Add board 11 to `TOOLS` using the existing card structure.

- [ ] **Step 4: Run syntax checks**

Run: `python -m py_compile utils/ding_minutes.py scripts/scan_ding_minutes.py "pages/00_11、🎙️_钉钉纪要登记.py" hello.py`
Expected: pass.

### Task 5: L Computer Run Guide, Verification, Commit, Push

**Files:**
- Create: `docs/ding_minutes_L_setup.md`

- [ ] **Step 1: Write setup guide**

Document Git pull, dependency installation, `DEEPSEEK_API_KEY`, config path, manual scan command, and Windows Task Scheduler setup for 19:00.

- [ ] **Step 2: Run focused tests**

Run: `python -m unittest tests.test_ding_minutes -v`
Expected: pass.

- [ ] **Step 3: Run syntax checks**

Run the same `py_compile` command from Task 4.
Expected: pass.

- [ ] **Step 4: Search for leaked keys**

Run: `rg -n "sk-[A-Za-z0-9_-]{16,}|Bearer\\s+[A-Za-z0-9._-]{16,}" -S .`
Expected: no matches.

- [ ] **Step 5: Commit and push**

Commit all related files and push the current branch.
