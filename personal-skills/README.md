# Personal Skills Collection

**Language**: English | [简体中文](README_ZH-CN.md)

**Change logs**: [English](CHANGELOG_EN.md) | [中文](CHANGELOG_ZH-CN.md)

Source copies of personal Codex skills for installation across machines. This collection is not another independently running project: the toolbox still has five independent subprojects, and cloning the repository does not execute these skills.

| Skill | Purpose and trigger | Repetition reduced in this update | Boundaries retained |
| --- | --- | --- | --- |
| [create-premium-ppt](create-premium-ppt/SKILL.md) | Create or revise editable presentations from materials, templates, or targeted instructions. | Reuse the established structure for local revisions; check affected slides and relevant global constraints incrementally. | Still check missing content, cropping, overlap, corrupted text, pagination, and readability; retain requested slide count, template, and acceptance requirements. |
| [save-xhs-comment-human-images](save-xhs-comment-human-images/SKILL.md) | Save Xiaohongshu comment photos whose main subject is a real person, using a supplied note URL. | Prefer an authenticated, controllable browser to avoid repeated browser setup and login checks. | Enlarge and classify before downloading; exclude avatars, note-body images, pure text, and illustrations. The user handles login and verification. |
| [storage-analyzer](storage-analyzer/SKILL.md) | Analyze disk use and produce classified recommendations and an interactive report. | Reuse directory reads within one scan rather than reading the same directory for multiple statistics. | Analysis remains read-only; cleanup follows explicit authorization, without independently deleting data or expanding scope. |

Two orchestration skills remain at the repository root: [GPT Planner · Luna Executor](../gpt-planner-luna-executor/README_EN.md) and [Codex → Grok Builder](../codex-grok-builder/README_EN.md).

## Installation and Updates

Choose a complete skill directory and copy or install it into this machine's effective `CODEX_HOME/skills/<skill-name>/`. If `CODEX_HOME` is unset, this is typically `.codex/skills/` under the user profile. Do not install the whole `personal-skills/` collection as a single skill.

On each machine, check the effective path, existing installation, local modifications, and dependencies before synchronizing repository versions. Do not assume an E-drive directory or Junction exists. Pulling the repository updates source copies only; it does not overwrite installed skills or migrate logins, keys, or private source material.

## Validation Scope

Storage-cache verification on 2026-09-05 passed five behavior checks and preserved eight output groups. Directory reads in a synthetic fixture fell from 24 to 14. This measures directory access only, not model tokens, whole-disk elapsed time, or fees. No real full-disk scan, PPT assignment, or Xiaohongshu collection was run in this update.

The PPT and Xiaohongshu changes refine workflow instructions; real assignments still require deliverable-specific, proportionate acceptance. See the [public validation record](../docs/history/2026-09-05-skill-cost-optimization.md).
