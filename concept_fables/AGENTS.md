# concept_fables — 子项目规则

## 目的

概念寓言目录：用结构化条目存储「概念 → 寓言故事 → 映射 → 迁移问题」，供检索、筛选与只读展示；写入由仓库内 Codex Skill 驱动。

本文件是本子项目的工作规则，不是软件 agent 清单。

## 拥有路径

- 核心库：`concept_fables/catalog.py`
- UI 模块：`concept_fables/page.py`（只读画廊）
- 薄入口页：`pages/18_19_concept_fables.py`
- 首页注册：`hello.py` 中的 M19 卡片
- 数据：`data/concept_fables.json`
- 仓库 Skill：`.codex/skills/concept-fable-gallery/`（`SKILL.md`、`agents/openai.yaml`、`scripts/upsert_concept.py`）
- 测试：`tests/test_concept_fables.py`

## 读写边界

- Streamlit 页只读：只调用 `load_catalog` / `filter_items` / `select_item`，不提供表单，不调用 `upsert_concept` / `save_catalog`。
- 唯一支持的自动写入路径：Skill 编排 + `scripts/upsert_concept.py`。
- 生产 catalog 不含测试/样例数据；测试必须使用临时文件。
- 验证不启动 Streamlit 服务，不用浏览器截图。

## Schema 权威

- 当前唯一权威为 **schema-v1**。
- 顶层：`schema_version` 必须为整数 `1`；`items` 必须为数组。
- 条目必填字段：`id`, `concept`, `field`, `school`, `definition`, `story`, `mappings`, `questions`, `tags`, `created_at`, `updated_at`。
- 读写、校验、upsert 均以 schema-v1 为准；不静默接受其他版本。

## 编码与密钥

- 全部文本读写使用 **UTF-8**。
- 禁止把密钥、token、密码写入本子项目代码、Skill payload 或 `data/concept_fables.json`。

## 重复判定

- 概念去重键：对 `concept` 做 **Unicode NFKC → casefold → 去首尾空白 → 折叠连续空白** 后的归一化字符串。
- 同一归一化概念只允许一条；upsert 时更新已有条目，不新增重复行。

## Upsert 约定

- 仅支持确定性 upsert：规范化字符串与标签后写入。
- 新建：生成稳定 slug 作为 `id`，`created_at` / `updated_at` 同为当日。
- 更新（归一化概念已存在）：保留原 `id` 与 `created_at`，刷新 `updated_at` 与其余字段；就地替换，不追加重复项。
- 不原地修改调用方传入的 catalog / payload；返回新对象。
- CLI：`python .codex/skills/concept-fable-gallery/scripts/upsert_concept.py <payload.json> [--catalog PATH] [--today YYYY-MM-DD]`，标准输出一行含 `action` / `id` / `catalog` 的紧凑 JSON。

## 变更边界

- 只改本子项目拥有的代码、数据与 Skill 路径。
- 保留工作区内与本任务无关的既有改动，不回滚、不覆盖。
- 涉及 `data/concept_fables.json` 的提交前，先按仓库同步规则拉取远端；只暂存该数据文件。

## 验证命令

```text
python -m py_compile concept_fables/catalog.py
python -m py_compile .codex/skills/concept-fable-gallery/scripts/upsert_concept.py
python -m pytest tests/test_concept_fables.py -q
python -X utf8 E:/codex/.codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/concept-fable-gallery
```
