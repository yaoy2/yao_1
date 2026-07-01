# Email Notice Streamlit Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Streamlit page that embeds the existing email notice HTML editor and provides a paste-to-prefill workflow for raw notice text.

**Architecture:** Keep the rich editor as a static HTML component under `assets/`. Put parsing logic in `utils/email_notice_parser.py` so it can be tested without Streamlit. The Streamlit page reads the HTML asset, injects parsed field values with a small script, and renders it through `st.components.v1.html()`.

**Tech Stack:** Python 3.11, Streamlit components, unittest, vanilla HTML/JavaScript.

---

### Task 1: Notice Parser

**Files:**
- Create: `utils/email_notice_parser.py`
- Create: `tests/test_email_notice_parser.py`

- [ ] **Step 1: Write failing parser tests**

Cover a typical notice with header, subject, notice number, body paragraphs, unit, and Chinese date.

- [ ] **Step 2: Run parser tests and verify RED**

Run: `python -m unittest tests.test_email_notice_parser`

Expected: fail with `ModuleNotFoundError` or missing parser function.

- [ ] **Step 3: Implement parser**

Expose `parse_notice_text(raw_text)` returning `header`, `subject`, `number`, `unit`, `date`, `body_text`, and `body_html`.

- [ ] **Step 4: Run parser tests and verify GREEN**

Run: `python -m unittest tests.test_email_notice_parser`

Expected: all tests pass.

### Task 2: Streamlit Page and HTML Asset

**Files:**
- Create: `assets/email_notice_editor.html`
- Create: `pages/15_0_email_notice.py`
- Modify: `hello.py`

- [ ] **Step 1: Copy the current HTML editor into repo assets**

Copy `E:\GoogleDrive\Ding2026\邮件通知编辑器.html` to `assets/email_notice_editor.html` without changing its content.

- [ ] **Step 2: Create Streamlit page**

Add `pages/15_0_email_notice.py` with a paste area, one-click parse button, preview of parsed fields, and embedded HTML component.

- [ ] **Step 3: Inject parsed values into HTML**

Append a script to the component HTML that assigns parsed values to `inputHeader`, `inputSubject`, `inputNumber`, `inputUnit`, `inputDate`, and `editorContent`, then calls `refreshPreview()`.

- [ ] **Step 4: Add homepage metadata**

Add the new tool to `hello.py` as `M15` so it appears in the custom Streamlit platform navigation.

### Task 3: Verification

**Files:**
- Test: `tests/test_email_notice_parser.py`
- Test: `tests/test_home_page.py`
- Verify: `pages/15_0_email_notice.py`, `utils/email_notice_parser.py`

- [ ] **Step 1: Run targeted tests**

Run: `python -m unittest tests.test_email_notice_parser tests.test_home_page`

- [ ] **Step 2: Run syntax checks**

Run: `python -m py_compile utils/email_notice_parser.py pages/15_0_email_notice.py hello.py`

- [ ] **Step 3: Do not start Streamlit**

Per project rule, skip `streamlit run`; report remaining browser-level visual risk.
