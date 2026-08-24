# Change Log

**Language**: English | [中文](CHANGELOG_ZH-CN.md)
**README**: [English](README_EN.md) | [中文](README_ZH-CN.md)

This English change log is the default GitHub changelog for Grok Builder. Keep `CHANGELOG.md` identical to this file.

## 2026-08-24

- **Initial controlled Codex-to-Grok workflow**: added a Windows-first personal Codex skill that runs `Codex plans → user approves → Grok Build implements → Codex verifies → Grok repairs if needed`.
- **Skill contract**: `SKILL.md` defines trigger phrases, the approved-task packet shape, the permission model, and acceptance rules. Codex remains the planner and verifier; Grok Build is the implementation worker.
- **Deterministic wrapper**: `scripts/invoke-grok.ps1` starts Grok Build headlessly with a named session, default `dontAsk` permissions, explicit allow rules for approved commands, and deny rules for push, hard reset, repository cleaning, and common recursive deletes.
- **Codex metadata**: `agents/openai.yaml` sets the display name, short description, default prompt, and implicit invocation.
- **No secrets in the project**: the wrapper uses the existing local `grok login` session or environment-based authentication resolved by Grok Build.
