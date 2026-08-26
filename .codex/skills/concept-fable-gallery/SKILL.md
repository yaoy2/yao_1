---
name: concept-fable-gallery
description: "当用户给出一个抽象概念，并要求用寓言、寓言法、故事化讲解，或把结果写入/收录到「概念寓言馆 / M19」时使用。把概念改写成可记忆的中文寓言，给出领域定义与故事映射，并自动写入更新仓库内 M19 概念寓言目录。不适用于普通散文、新闻稿、通知或与寓言馆无关的泛写作。"
---

# 概念寓言馆（M19）

把抽象概念改写成可记忆的中文寓言，结构化收录到本仓库 `data/concept_fables.json`，供只读 Streamlit 页 M19 展示。

普通用户只需给出概念，或调用 `$concept-fable-gallery <概念>`。Streamlit 页只读，不提供写入表单。

## 寓言写作契约（必须完整遵守）

默认中文。先给出写完的寓言正文，再给概念分析与问题。

1. **篇幅**：故事正文最多 1000 个汉字/字符（与 schema 校验一致）。
2. **概念不泄露**：故事正文不得出现目标概念名、所属学科/领域名、学派名，也不得使用该概念的专业术语。这些信息只出现在故事之后的分析区。
3. **场景约束**：一个具体场景；剧情转折仅 1–2 次；角色最多 3 个。优先现代职业、非人视角，或日常小事。
4. **禁止套路开场与结构**：
   - 旅人请教智者
   - 村庄顿悟
   - 孩子纠正大人
   - 师徒训诫
   - 临终告白
5. **禁止这些套路角色**：钟表匠、图书管理员、隐士、说书人、老船夫、酿酒师、铁匠、抄经人。
6. **禁止这些滥俗中心意象**：钟、河流、镜子、迷宫、织布机、地图、灯塔、棋盘、回声、影子、沙漏、风、蜡烛、种子、桥、星辰、蝴蝶、蛛网。同时避免华丽幻想地名。
7. **故事之后**给出简洁概念分析，必须包含：
   - 领域 `field`
   - 学派/理论家族 `school`（可空字符串）
   - 一句话定义 `definition`
   - 明确的「故事元素 → 概念元素」映射列表
8. **结尾恰好两个问题**：一个核心问题、一个迁移问题。不得再加第三问。
9. **动笔前静默自检**：黑名单角色/意象、字数上限、概念泄露、映射是否齐全、是否恰好两问。任一失败先改写，再继续后续步骤。

## 结构化 payload（schema-v1）

面向用户写完解释后，在内存中构造 deterministic CLI 所需 JSON 对象（不要在本任务里发明生产样例数据）：

```json
{
  "concept": "目标概念",
  "field": "简洁领域",
  "school": "学派或空字符串",
  "definition": "一句话定义",
  "story": "展示给用户的寓言正文（一字不差）",
  "mappings": [
    {"story_element": "故事元素", "concept_element": "概念元素"}
  ],
  "questions": {
    "core": "核心问题",
    "transfer": "迁移问题"
  },
  "tags": ["标签1", "标签2"]
}
```

约束：

- `mappings` 非空
- `questions` 恰好 `{core, transfer}`
- `tags` 2–5 个可检索短标签，无重复

## 确定性写入脚本

唯一支持的自动写入路径：

```text
python .codex/skills/concept-fable-gallery/scripts/upsert_concept.py <payload.json> [--catalog PATH] [--today YYYY-MM-DD]
```

- 位置参数：UTF-8 JSON payload 文件路径
- `--catalog` 默认仓库 `data/concept_fables.json`
- `--today YYYY-MM-DD` 供测试固定日期
- 标准输出一行紧凑 UTF-8 JSON，至少含 `action`、`id`、`catalog`
- 脚本不跑 git、不 commit/push、不删文件、不访问网络

payload 文件尽量写在仓库外的临时路径，内容不含密钥。

## 自动收录 + Git 执行顺序

未来每次被调用时，严格按下列顺序执行；任一步被脏工作区或其他层阻塞时，停在该层并原样说明，不得 stash / reset / force / discard。

1. 阅读仓库根 `AGENTS.md`、schema-v1 约定，并按归一化概念查找是否已有条目。保留工作区中与本任务无关的既有改动。
2. 在内存中完成寓言、分析与 payload；此时不要改生产目录文件。
3. 数据变更前运行：`git status --short`、`git fetch origin`，并比较 `HEAD...origin/main`。
4. 若 `origin/main` 领先且工作区干净：执行 `git pull --rebase origin main`。若远端领先但无关脏文件使安全 pull 不可行：停止并告知用户。绝不 stash、reset、force、丢弃改动。
5. 调用确定性 CLI，payload 文件尽量放在仓库外。不写入密钥。
6. 运行 `python -m pytest tests/test_concept_fables.py -q`，再重新加载 catalog，确认该归一化概念恰好一条，且可见 `story` 与展示稿一致。
7. 只暂存 `data/concept_fables.json`；检查 staged diff / 文件名列表。不暂存无关文件。
8. 若无数据 diff：报告 no-op。否则用简洁 data-only 信息 commit，并 `git push origin main`（依赖本仓库既有授权）。绝不 force-push。
9. 若 push 因远端前进被拒：再次 fetch；不要覆盖远端。若安全 rebase 被脏改动挡住则停止。
10. 汇报：概念名、created/updated、catalog 路径、测试结果、commit hash、push 结果。任一步未完成时，明确写出卡在哪一层。

## 边界

- 生产 `data/concept_fables.json` 不得写入测试/样例数据；测试只用临时文件。
- 页面只读；Skill + `upsert_concept.py` 是唯一支持的自动写入路径。
- 不启动 Streamlit，不用浏览器做验证。
