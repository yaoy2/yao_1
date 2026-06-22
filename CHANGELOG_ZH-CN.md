# 更新日志 (CHANGELOG)

## 2026-06-21

- **修复 freechat provider 覆盖问题**：切换到短消息自由讨论后，第一版轻量说话人规划可能只选到分配给 DeepSeek 和 Kimi 的席位，导致 MiMo 即使已有分配席位也一直显示 `idle`、调用 0 次。现在规划器会先确保每个已分配 provider 至少有一个活跃席位，再套用不规则发言顺序。
- **众声室默认流程改为 `freechat`**：用户反馈原来的 opening / debate 结构仍然像“一个 LLM 回答拆给多个席位”。现在页面点击“开始圆桌”时会调用 `/api/roundtable/run` 的 `mode: "freechat"`，按短消息预算生成更接近聊天流的 transcript，而不是固定排队小作文。
- **新增自由讨论 prompt 和 mock 行为**：新增 `buildFreechatPrompt`、freechat engine 路径和 mock freechat 样例；每一轮都会读取附近 transcript，要求席位接话、打断、反驳、区分、追问或补一个具体角度，避免复述题目。
- **记录当前限制**：新说话顺序仍然是轻量规则，不是真正由模型主持人自主控场。这能改善默认体感，但真正的自主接话和发言价值评估仍待后续实现。
- **验证结果**：新增 `tests/freechat.test.ts`，并扩展 API 和指南测试，覆盖 freechat 模式、短消息输出、非线性说话顺序和新版说明文字。
- **修复众声室 mock 输出低质误导问题**：用户反馈点击“开始圆桌”后 transcript 充满复述题目、空泛表态和“链路连通”测试话术。定位原因是当前运行勾选了 mock provider，而 mock 输出硬编码为通路验证文本，容易被误认为圆桌真实质量。已重写 `src/lib/mock-provider.ts`，让 mock 生成更像席位样例的 opening / debate 内容，并在页面明确提示 mock 只用于流程测试。
- **强化真实模型 prompt 质量底线**：`src/lib/prompt-builder.ts` 新增明确约束，要求 opening 第一句直接给判断，禁止复述题目、禁止“综合看待”式糊弄；debate 必须点名回应具体席位观点，不能只说同意或复述前文。新增 `tests/prompt-quality.test.ts` 和 mock 质量测试，防止回退到低质模板。
- **隔离 Next.js dev / build 缓存目录**：排查到一边运行 `next dev` 一边执行 `next build` 会共同写入 `.next`，造成开发服务找不到临时 chunk 并让首页 500。新增 `next.config.mjs`，开发模式继续使用 `.next`，生产构建改用 `.next-build`，并加入 `.gitignore`；验证 build 后 3000 首页仍返回 200。
- **众声室增加浏览器本地草稿恢复**：排查“点击开始圆桌后页面回到空状态”时确认，Next.js 开发服务 Fast Refresh / 整页重载会导致 React 临时状态丢失。新增 `src/lib/draft-state.ts`，自动暂存并恢复话题、席位池、已解析席位、已选席位、席位分配、mock 模式和 JSON 编辑区状态；同时给页面按钮补 `type="button"`，降低误触发表单提交的风险。
- **草稿恢复验证**：新增 `tests/draft-state.test.ts` 覆盖草稿序列化、反序列化和异常数据忽略；本地浏览器验证刷新后可恢复测试话题。`npm run lint`、`npm test`、`npm run typecheck`、`npm run build` 均通过。
- **众声室第三 provider 更正为 Kimi**：将原先误写的 MiniMax provider 更正为 Kimi，页面、类型、mock provider、自动分配偏好、README 和测试统一改为 `kimi` / `Kimi` / `KIMI_*`。
- **兼容旧环境变量名**：为了不让已经写入 `.env.local` 的旧 `MINIMAX_*` 配置立刻失效，Kimi provider 会优先读取 `KIMI_*`，没有时再读取 `MINIMAX_*` 作为 fallback；文档推荐新配置统一使用 `KIMI_API_KEY`、`KIMI_BASE_URL`、`KIMI_MODEL`。
- **众声室席位池改为 compact 工作流**：支持只包含 `seats` 数组的短版席位池，每个席位只需 `seat_name`、`type`、`core_concern`、`typical_questions`、`must_do`、`must_not_do`、`speaking_style`，其他字段可缺省。
- **新增低相关竞赛示例席位池**：新增 `src/presets/low_relevance_competition.json`，内置“学院四个专业对口竞赛少且难，参加艺术设计大赛、AI微摄影大赛、知识竞赛，对学生利大还是弊大。”主题和 6 个短席位；页面新增“载入示例席位池”按钮，自动填入主题和 compact JSON。
- **席位卡片展示收敛**：解析后默认收起 JSON，只展示席位卡片；卡片正面只显示席位名称、类型、核心关切和发言风格，点击“展开”后再显示典型问题、应当做、应当避免。
- **Prompt 缺省字段兜底**：`prompt-builder` 在 `opening_prompt`、`debate_prompt`、`blind_spots`、`likely_opponents`、`example_preference` 缺失时自动加入通用约束，不让短版席位因为字段少而运行失败。
- **众声室页面新增说明书板块**：在 `zhongshengshi/` 页面顶部新增“项目说明书 / 使用指南”，用紧凑分栏说明最快跑通、真实模型配置、席位池格式、结果解读和当前边界，方便打开页面后直接按步骤使用。
- **指南内容模块化**：新增 `src/lib/guide.ts` 管理说明书内容，并新增测试确认指南覆盖 mock provider、开始圆桌、API Key 服务端边界、当前阶段和暂不做 Streamlit 适配等关键说明。
- **众声室最小圆桌链路上线**：在 `zhongshengshi/` 新增 `/api/roundtable/run`，实现 opening + 1 轮 debate。用户输入话题、解析席位池、选择 4 到 6 个席位后，可以点击开始圆桌，前端展示每个席位的开场发言和一轮交锋发言。
- **Prompt builder 与模型编排**：新增 `prompt-builder`，按席位名称、类型、核心关切、典型问题、应做/不应做、反驳对象、盲点、风格、例子偏好和自定义提示词生成 opening / debate 提示。新增 roundtable engine，按席位分配调用对应 provider。
- **Mock provider 与失败不中断**：新增 mock provider 用于本地验证和测试，不消耗真实 API。单个席位或 provider 调用失败时会写入 transcript 和错误日志，其他席位继续运行。
- **密钥安全继续收紧**：真实 provider 调用只在服务端读取 `.env.local` / 环境变量中的 API Key；`/api/providers` 和 `/api/roundtable/run` 都不返回密钥。
- **前端 transcript 展示**：控制台占位区升级为运行日志区，显示 pending / running / success / failed 状态、provider 调用次数、失败信息和完整 transcript。
- **当前限制**：本阶段只做 opening + 1 轮 debate；发言价值评估、缺席视角检测、总结、多轮编排和 SQLite / Prisma 持久化仍待后续实现。
- **验证结果**：先新增 prompt、mock provider、roundtable engine、API route 和失败路径测试，确认缺实现时失败；补实现后 `npm test` 通过 12 项测试，`npm run typecheck` 通过。
- **新增“众声室”本地 MVP 子项目**：在 `zhongshengshi/` 下创建独立 Next.js + TypeScript + Tailwind CSS 项目，用来先验证多模型圆桌群聊的核心前置流程，而不是直接改造进现有 Streamlit 工具箱。
- **完成第 1-4 步范围**：已完成基础页面、话题输入、席位池 JSON 粘贴解析、候选席位展示、4 到 6 个席位选择、DeepSeek / MiMo / Kimi provider 配置状态读取、OpenAI-compatible adapter 基础封装，以及每个模型最多 2 个席位的自动分配。
- **密钥边界处理**：API Key 只通过 `.env.local` / 服务端环境变量读取，前端页面只显示配置状态、Base URL 和 Model Name，不返回密钥。
- **路线判断记录**：本轮讨论过是否直接搬成 Streamlit。当前判断是先跑通 MVP 更稳，因为真正风险在圆桌流程和模型协作逻辑；等核心流程成功后，再决定适配 Streamlit、继续保留独立 Next.js，或抽取逻辑复用。
- **README 同步更新**：补充 `zhongshengshi/` 的运行方式、环境变量填写方式、已完成内容和下一步计划。
- **验证结果**：先写解析、provider 和席位分配测试，确认缺实现时失败；补实现后 `npm test` 通过 7 项测试。按项目规则未启动 Streamlit。

## 2026-06-09

- **便签展示池排除刺眼色卡**：不修改 `data/color_palettes.md` 中任何具体色号，保留「樱桃苏打」「橘子派对」作为配色方案参考；但灵感便签卡片不再从这两套色卡中取色，避免已保存便签继续出现高饱和蓝底、橙底或红粉大面积背景。
- **验证结果**：新增测试确认配色库仍保留这两套方案，但 `build_memo_card_html` 会跳过它们并改用便签展示池中的下一套色卡；按项目规则未启动 Streamlit。

## 2026-06-08

- **删除四个色卡方案**：从 `data/color_palettes.md` 移除「午夜歌剧」「泡泡糖」「冬日庄园」「西瓜夏天」。
- **便签卡片配色逻辑重构**：卡片底色不再轮换，改为始终取色卡中饱和度最低的颜色做背景，避免高饱和色（如电光蓝、活力橙、樱桃红）铺满整张卡片导致刺眼。标题和点缀使用其余两个颜色。
- **正文颜色自适应**：正文文字颜色根据底色明度自动切换——亮底用深灰 `#2D3436`，暗底用浅色 `#F0EDE8`，保证可读性。
- **色卡三色分工明确**：底色负责氛围（大面积），标题用色卡深色（装饰），点缀用中间色（标签、日期），正文颜色独立于色卡之外。解决了"色卡图片好看但便签不好看"的问题——色卡三色本就不是为"底色+字色+字色"设计的。
- **验证结果**：通过 Playwright 浏览器预览确认橘子派对、樱桃苏打等高饱和色卡不再出现刺眼底色。按项目规则未启动 Streamlit。

## 2026-06-07

- **修复 Codex Radar Actions 并发推送失败**：排查 GitHub Actions 第 29 次运行发现，`python -m codex_radar_lite.cli` 已成功，失败发生在 `Commit radar data` 步骤；日志显示 `main -> main (fetch first)`，原因是同一时间远端 `main` 已有其他数据提交先进入，旧工作流直接 `git push` 导致被拒。
- **Radar 工作流同步保护**：`.github/workflows/codex-radar.yml` 现在 checkout 后使用完整历史，并在生成 radar 数据前 `git pull --ff-only origin main`；提交 radar 数据后先 `git pull --rebase origin main`，再带重试执行 `git push`。如果 radar 数据没有变化，工作流会直接退出，不再无意义推送旧 HEAD。
- **回归检查补充**：新增 `tests/test_codex_radar_workflow.py`，专门检查 workflow 是否包含“运行前同步 main、无变更跳过推送、推送前 rebase”三项保护，避免以后又退回到直接 push。
- **验证结果**：先运行新增测试确认旧 workflow 会失败；修复后 `tests.test_codex_radar_workflow` 与 `tests.test_codex_radar_lite` 均通过，`codex_radar_lite` 包语法检查通过。第一次语法检查曾因 PowerShell 不展开 `*.py` 通配符而报 `[Errno 22] Invalid argument`，随后改为显式文件列表验证通过。按项目规则未启动 Streamlit。
- **README 与 Change Log 双语命名落地**：将原中文 README / CHANGELOG 保留为 `README_ZH-CN.md` 和 `CHANGELOG_ZH-CN.md`，新增英文版 `README_EN.md` 和 `CHANGELOG_EN.md`；`README.md` 与 `CHANGELOG.md` 保留为 GitHub 默认入口，指向英文主版本并链接中文版。
- **项目规则同步更新**：更新 `AGENTS.md`，明确以后凡是更新 README 或 Change Log，默认同时维护中英文版本；正式命名为 `README_ZH-CN.md` / `README_EN.md` 和 `CHANGELOG_ZH-CN.md` / `CHANGELOG_EN.md`。
- **验证结果**：本次只改文档，未启动 Streamlit；已用 `git diff --check` 检查 Markdown 补丁格式和空白问题。
- **灵感便签封面继续收敛**：用户认可“海报卡正面 + 全文展开”的正文设计，但反馈操作按钮仍破坏卡片观感。本次将上移、下移、编辑、隐藏全部移入“全文”展开区，卡片收起时只显示封面。
- **固定封面字号**：海报卡标题不再使用过大的响应式字号，改为固定 `1.62rem`，让卡片封面正常排版；排不下或需要阅读全文时，通过“全文”展开区查看。
- **验证结果**：`tests.test_web_memo_db` 32 项通过；灵感便签页面和 `utils/web_memo_db.py` 通过 `py_compile`。按项目规则未启动 Streamlit。
- **灵感便签改为海报式卡片正面**：用户明确指出想要的是截图那类鲜活的色卡海报卡，而不是旧的全文便签卡换颜色。本次将卡片正面改为 `memo-card-poster`：居中大字、强色块背景、内描边、加重阴影和紧凑标签。
- **全文从卡面移入展开区**：卡片正面只展示第一句/首行短摘录，长文本不再铺满卡面；完整内容放入每张卡片下方的“全文”折叠区，保留阅读能力，同时让正面优先服务视觉效果。
- **深色文字规则修正**：上一轮只禁止中性黑，导致暖棕复古的 `#592E2E` 仍像黑字。本次新增针对深棕等视觉近黑文字的测试，并调整文字色替换逻辑，暖棕复古会改用更亮的同色卡文字色。
- **验证结果**：`tests.test_web_memo_db` 32 项通过；灵感便签页面和 `utils/web_memo_db.py` 通过 `py_compile`。按项目规则未启动 Streamlit。
- **删除“商务蓝”配色方案**：用户反馈当前卡片仍不好看，并明确要求删除“商务蓝”。本次从 `data/color_palettes.md` 移除该方案；便签卡片展示会按当前色卡池重新映射，现有便签不需要改备份数据。
- **禁止卡片内容使用中性黑文字**：新增卡片文字色过滤逻辑，色卡中接近黑色/黑灰的中性色不会被选为正文、日期、标签文字色；如果抽到这类颜色，会优先换用同一色卡里的其他非黑色。
- **验证结果**：新增测试确认色卡池不再包含“商务蓝”，并确认 `#1F1B1D` 这类中性黑不会成为卡片文字色；`tests.test_web_memo_db` 30 项通过，灵感便签页面和 `utils/web_memo_db.py` 通过 `py_compile`。
- **灵感便签操作区最小化**：用户反馈“移动位置、编辑和隐藏”按钮太占空间。本次将上移、下移、编辑、隐藏改为卡片内紧凑符号按钮，并通过 `help` 悬停提示显示“上移 / 下移 / 编辑 / 隐藏”，减少对卡片内容和配色效果的干扰。
- **现有便签确认套用新配色规则**：用当前 `data/web_memos_backup.md` 中的 2 条记录直接生成卡片 HTML，确认都已经输出 `--card-text` 和底字互配样式，不再走旧的黑字浅底展示。
- **验证结果**：`tests.test_web_memo_db` 28 项通过；灵感便签页面和 `utils/web_memo_db.py` 通过 `py_compile`。按项目规则未启动 Streamlit。
- **灵感便签卡片改为色卡底字互配**：用户指出色卡版块的初心是提供真正可参考的配色效果，而不是“选一个底色再配黑字”。本次将便签卡片从“第三色做底、正文固定深色”改为“同一套色卡内主色/辅色互为底色和文字色”的视觉规则。
- **新增双色反转卡片模式**：每套色卡按卡片位置轮换为三种模式：主色底 + 辅色字、辅色底 + 主色字、浅色底 + 主色字。日期、色卡名、标签和正文都使用同一套文字色变量，减少黑字浅底的模板感。
- **移除卡片固定黑字和渐变装饰**：卡片正文、日期、标签不再固定使用 `#182230` / `#344054` 等深色；左侧色条改为当前文字色，页面 CSS 中移除残留的线性渐变装饰，避免展示出色卡组合之外的视觉效果。
- **防回退测试**：新增测试确认“那不勒黄曙绿”能生成黄底绿字和绿底黄字两种卡面，并确认卡片 CSS 使用 `--card-text` 变量而不是固定黑字。
- **验证结果**：`tests.test_web_memo_db` 28 项通过；`utils/web_memo_db.py` 和灵感便签页面通过 `py_compile`。按项目规则未启动 Streamlit，视觉细节仍以线上部署后的实际页面为准。
- **修复灵感便签编辑后复制卡片**：用户反馈编辑一张卡并保存后，原卡不变，同时新增一张同内容卡；再次编辑会继续复制。排查后确认原因是远端备份合并仍按“日期 + 内容”识别同一张卡，内容一改，旧远端记录就会被当成新卡导回。
- **便签备份新增稳定 ID**：`data/web_memos_backup.md` 的系统字段新增 `ID`，导入远端备份时优先按 ID 识别同一张便签；旧格式无 ID 时继续用“日期 + 规范化内容”兜底，避免旧备份立刻失效。
- **清理线上重复便签**：同步远端最新备份后，发现线上备份已有 4 条记录，其中 3 条是同一“发心”便签的重复版本。本次把备份整理为 2 条唯一记录，并补入 ID、顺序、状态字段。
- **重复便签自动隐藏**：启动数据库时会对可见便签做重复检查；内容只存在换行或空白差异时，也视为同一张卡，只保留一张可见，其余转为隐藏状态，避免线上旧 DB 已经有重复行时继续显示多张。
- **卡片操作收进卡内**：灵感便签列表中，上移、下移、编辑、隐藏和编辑表单都放入同一个卡片容器中，不再像外置按钮一样挂在卡片下方。
- **卡片配色减少连续撞色**：便签卡片展示时改为按当前列表位置从实时色卡池轮换取色，不再让多张连续卡因内容相同或哈希接近而使用同一配色。
- **删除“蓝调俱乐部”配色方案**：从 `data/color_palettes.md` 移除用户明确不喜欢的“蓝调俱乐部”方案。
- **本次绕路记录**：清理备份时第一次通过 PowerShell here-string 传中文给 Python，导致备份标题和字段名被写成问号；随后改用 Unicode 转义重写字段名，并用 Python 读取确认文件内容恢复为正常中文。
- **验证结果**：`tests.test_web_memo_db` 26 项通过；`utils/web_memo_db.py` 和灵感便签页面通过 `py_compile`。按项目规则没有启动 Streamlit 做页面预览，剩余风险是线上视觉细节需部署后实际查看。
- **新增配色方案 32-40**：从微信公众号文章 `国际流行色彩搭配` 中整理 9 组双色综合配色，追加到 `data/color_palettes.md`，包括克莱因蓝雅黄、勃艮第红果金、爱马仕橙深渊、蒂芙尼蓝淡黄、普鲁士蓝圣罗、那不勒黄曙绿、马尔斯绿哑金、凡戴克棕卡其、殷红赤金。
- **配色预览验证**：追加色卡后确认配色库可解析出 40 组方案，新方案编号为 32-40；验证 `tests.test_color_palette_preview` 和配色页面语法检查通过。没有启动 Streamlit，本次仍按项目规则只做代码级验证。
- **灵感便签 GitHub 备份加固**：在 `utils/github_backup_sync.py` 增加只读远端备份内容的 `read_file_from_github` 能力；在 `utils/web_memo_db.py` 增加便签导入合并和去重逻辑；在灵感便签页面中加入启动后远端合并、保存前远端检查和空备份覆盖保护。
- **防丢数据规则**：灵感便签保存到 GitHub 前会先读取远端 `data/web_memos_backup.md`。如果远端已有便签而当前环境为空，会阻止空账本覆盖远端；如果远端和本地都有内容，会按“日期 + 内容”合并去重后再写回。
- **现状确认**：本地和远端 `data/web_memos_backup.md` 当时都仍是 0 条记录，所以之前已经清空的线上便签没有可恢复来源。本次改动的目标是防止后续再次被空环境覆盖，不承诺恢复已经丢失的数据。
- **灵感便签卡片配色改为跟随当前色卡库**：卡片展示时不再使用新增便签时写入的旧 `palette_name` / `palette_colors` 快照，而是从当前 `data/color_palettes.md` 中按便签日期和内容稳定抽取配色。这样色卡库新增、删减或调整后，便签卡片会跟随当前方案池重新映射。
- **灵感便签卡片取消模板自造渐变**：用户反馈便签卡片出现了配色池里没有的渐变效果。排查后确认原因不是色卡池存在渐变，而是卡片模板额外把背景写成 `linear-gradient`，左侧色条也使用主色到辅助色的渐变，并有右上角半透明装饰圆。本次改为纯色表达：卡片背景直接使用当前色卡第三色，左侧色条直接使用主色，去掉额外装饰圆，避免展示出色卡池以外的视觉效果。
- **远端便签备份确认**：本次推送前发现远端新增 `data: sync web memo backup` 提交，`data/web_memos_backup.md` 已有 1 条便签记录；后续提交先同步该远端数据，再推送代码改动，避免覆盖线上刚写入的便签。
- **再次同步远端数据**：实现卡片编辑/隐藏/移动期间，推送前再次发现远端新增 `data: sync web memo backup`，远端便签备份增至 2 条；本地代码提交后继续通过 rebase 接到远端数据提交之后，保持线上便签优先。
- **灵感便签卡片操作增强**：新增便签编辑、隐藏、上移和下移能力。编辑可修改内容、分类和标签；隐藏默认不再展示，但仍写入备份，避免误删后完全丢失；移动只调整 `display_order`，三列瀑布流布局仍由当前列表顺序自动分配。
- **便签备份格式补强**：`data/web_memos_backup.md` 新增“顺序”和“状态”字段，便于跨部署恢复卡片顺序和隐藏状态；旧备份没有这些字段时仍按默认正常状态解析，保持向后兼容。
- **卡片字体采用预览中间方案**：根据预览结果采用楷体方向，正式卡片正文使用 `Kaiti SC` / `KaiTi` / `STKaiti` / 宋体兜底组合，提高摘录卡片的公众号式阅读感。
- **预览与工具绕路**：最初用图片方式生成预览时，中文因 PowerShell 编码链路显示为问号；随后临时安装 `playwright-core` 到系统临时目录并调用本机 Chrome 渲染 HTML 预览，确认字体方案。该临时依赖不写入仓库。
- **为什么不用完全随机**：如果每次刷新都纯随机，用户浏览便签时会感觉卡片视觉不停跳动；本次采用“稳定抽取”的方式，在当前色卡库不变时同一条便签颜色稳定，在色卡库变化后再重新映射。
- **文档规则更新**：更新 `AGENTS.md`，明确以后凡是完成需要 `git push` 的改动，默认同步更新 `CHANGELOG.md`；如果是功能、使用方式、数据同步规则或用户可见行为变化，再同步更新 `README.md`。小调整可以不写 README，但仍要写 changelog。
- **README 更新**：补充配色预览与灵感便签的关系，说明 `data/color_palettes.md` 是便签卡片配色的实时来源；补充灵感便签通过 `GITHUB_BACKUP_TOKEN` 写回 GitHub 备份，并在同步前合并远端、阻止空备份覆盖。
- **过程中走过的弯路**：一开始只确认了便签远端备份是 0 条，并说明当前没有可恢复来源；这没有完全回应“以后如何避免再次丢数据”的设计诉求。后续补上了远端合并、防空覆盖和测试保护。
- **测试与编码绕路**：新增测试时曾因为 Windows 控制台中文/emoji 路径显示和匹配问题导致补丁失败、路径测试报错，后来改为按页面文件前缀自动查找，并使用更稳定的函数级断言。这个问题属于测试写法绕路，不是业务功能失败。
- **验证结果**：完成后验证 `tests.test_github_backup_sync`、`tests.test_web_memo_db`、`tests.test_budget_db`、`tests.test_color_palette_preview` 通过；灵感便签页面和相关工具文件通过 `py_compile`。确认没有把空的 `data/web_memos_backup.md` 或本地 SQLite 数据库夹带进提交。

## 2026-06-05

- **新增第 12 个板块：Codex雷达**：新增 `pages/00_12、📡_Codex雷达.py`，把 Codex 重置窗口监控接入主工具箱首页和 Streamlit 多页面入口。
- **新增 Codex Radar Lite 内核**：新增 `codex_radar_lite/`，作为第 12 板块背后的轻量监控模块。
- **每小时自动运行**：新增 `.github/workflows/codex-radar.yml`，通过 GitHub Actions 每小时运行一次，不需要 Docker 或常驻服务器。
- **规则判断内核**：采集公开来源后，根据 Codex、usage limit、rate limit、reset、recovered 等关键词判断 `normal`、`watch`、`high_probability`、`open`、`closed` 状态。
- **钉钉推送适配**：新增钉钉机器人推送，只读取 GitHub Secrets 中的 `DINGTALK_WEBHOOK` 和可选 `DINGTALK_SECRET`，不把 webhook 或密钥写入仓库。
- **页面展示**：新增第 12 板块页面，同时保留 `codex_radar_lite/site/index.html` 作为备用静态状态页，读取 `data/codex_radar_current.json` 展示当前状态、概率和关键证据。
- **状态数据文件**：新增 `data/codex_radar_current.json`、`data/codex_radar_history.json`、`data/codex_radar_signals.json` 作为首次运行前的初始数据。
- **测试覆盖**：新增 `tests/test_codex_radar_lite.py`，覆盖信号提取、规则判断、历史更新、RSS 输出和无 webhook 时的安全跳过。
- **范围说明**：第一版只做钉钉机器人，不做邮件兜底，不做个人微信；按项目规则未启动 Streamlit，只做代码级验证。

## 2026-05-28
- **配色预览兼容修复**：将 `配色方案预览` 页面从即将废弃的 `streamlit.components.v1.html` 调整为 `st.html` 渲染，避免 Streamlit 后续移除旧接口后页面预览失效。
- **防回退测试补充**：更新 `tests/test_color_palette_preview.py`，明确禁止再次引入 `streamlit.components.v1` 和 `components.html`，防止兼容修复被后续改动覆盖。
- **缓存文件清理**：将已经误入版本管理的 `__pycache__/*.pyc` 文件移出 Git；`.gitignore` 已有忽略规则，后续运行测试或语法检查不再因为 Python 缓存污染提交状态。
- **本地依赖环境补齐**：按 `requirements.txt` 补齐本地虚拟环境中的 `python-docx` 和 `pypdf`，解决全量测试因缺少 `docx` 模块失败的问题。
- **远端变更合并**：推送前发现 GitHub 远端已有 Recorder 下载扫描和数据同步相关提交，先 `fetch` 检查文件重叠，再合并远端更新，保留远端新增内容和本次配色页修复。
- **验证结果**：合并后全量单元测试 48 项通过，项目内 39 个 Python 文件语法检查通过，并确认仓库内不再出现 `streamlit.components.v1` / `components.html`。

## 2026-05-25
- **Recorder 云端展示同步**：新增 `data/ding_minutes_cloud.json` 云端展示数据和 `scripts/sync_recorder_cloud.py` 同步脚本，本地电脑扫描整理后的记录可以同步到线上页面展示。
- **Recorder 记录读取优化**：`Recorder_笔记` 页面优先读取本地数据库；线上或本地数据库为空时自动读取云端同步 JSON，并显示同步时间和状态统计。
- **Recorder 卡片体验优化**：记录列表改为更紧凑的卡片样式，整理稿、原文和备注收进可展开区域，减少页面滚动压力。
- **Recorder 备注同步**：本地保存备注、生成整理稿或每日扫描完成后，会自动刷新云端展示导出，避免线上记录滞后。
- **首页入口修复**：首页工具卡片改用 Streamlit 原生页面跳转，修复部分环境下卡片链接不稳定的问题。
- **返回主页入口**：各工具页新增固定的“回到主页”入口，方便从子页面快速回到工具箱首页。
- **依赖补充**：`requirements.txt` 新增 `pypdf`，补齐万能合并机 PDF 处理依赖。
- **Recorder 数据同步**：同步更新了 L 电脑产生的 Recorder 记录，便于云端查看今天整理过的内容。

## 2026-05-24
- **新增模块：Recorder_笔记**：新增上锁板块 `🎙️ Recorder_笔记`，用于登记钉钉导出的 Word 转写文件，保留原文并生成 AI 整理稿。
- **Recorder 自动扫描**：新增 `scripts/scan_ding_minutes.py` 和 `config/ding_minutes.ini`，支持每天 19:00 扫描前一天 19:00 到当天 19:00 新建的 `export_*.docx`、`dt*.docx`。
- **DeepSeek 整理接入**：新增 DeepSeek 调用层，API key 只从本机 `DEEPSEEK_API_KEY` 环境变量读取，不写入代码、配置、日志或数据库。
- **Recorder 备注与重试**：记录页支持备注、状态筛选、原文查看、AI 整理稿查看、失败提示和单条重新整理。
- **Recorder 密码保护**：`Recorder_笔记` 复用预算速记台账同一套密码，读取 `budget_password` / `[budget].password` 或本机 `BUDGET_PASSWORD`。
- **L 电脑迁移指南**：新增 `docs/ding_minutes_L_setup.md`，说明在 `E:\github\yao_1` 下 `git pull`、配置环境变量和设置 Windows 任务计划的步骤。
- **首页改版**：首页改为 Command Center 深色封面，工具入口按时间倒序展示；首页每页固定 3 x 3，超过 9 个工具时进入下一页。
- **导航顺序调整**：Streamlit 侧边栏页面文件统一改为倒序前缀，越晚完成的工具越靠上，全部工具仍保留在导航中。
- **新增模块：灵感便签盒**：新增 `🧾 灵感便签盒` 页面，支持快速记录灵感、摘录、待办、写作素材和工具想法。
- **灵感便签盒标签能力**：支持选择已有标签、新增标签、自动分类和三列备忘卡片展示；分类规则扩展为摘录、观点、待办、写作素材、工作记录、工具想法、金句等。
- **灵感便签盒备份**：新增 `data/web_memos_backup.md` 硬备份，保存后自动同步；数据库为空时会尝试从 Markdown 备份恢复。
- **预算台账字段扩展**：快速录入新增 `支出人` 字段，记录管理、编辑、导出和备份同步支持该字段。
- **预算台账硬备份**：新增 `data/budget_ledger_backup.md` 和 `data/budget_ledger_backup.xlsx`，保存、更新和恢复台账后自动同步。
- **预算类别调整**：新增 `年终奖留存` 类别，作为不设固定预算上限的支出类别，只累计实际支出，不参与余额计算。
- **预算恢复能力**：预算台账支持从备份 Excel 覆盖恢复，恢复前需要勾选确认。
- **页面兼容修复**：修复灵感便签盒在 Streamlit Cloud 上因 HTML 渲染接口和标签函数兼容导致的报错。
- **项目规则补充**：新增项目级 `AGENTS.md`，明确本项目不要启动 Streamlit 做验证，改用单元测试、语法检查和纯函数检查。
- **测试补充**：新增/更新预算台账、灵感便签盒、首页入口和配色页相关测试，覆盖备份、标签、页面排序和首页分页逻辑。

## 2026-05-18
- **预算页调整**：移除预算速记台账中的年度预算总览区，页面聚焦分类预算看板、记录管理与交叉分析。
- **微信归档升级**：本地归档窗口升级为四路线入口，支持 raw、学院、课题、竞赛的识别与本地可执行流程。
- **启动入口整理**：统一保留 `启动微信归档窗口.bat`，固定归档窗口端口为 `8502`，删除重复的英文启动脚本。
- **测试补充**：新增微信归档路线识别、本地文件复制和启动脚本端口检查测试。

## 2026-05-17
- **配色预览升级**：将配色方案预览页从竖条色卡升级为“氛围展示 + 色彩角色 + PPT 应用预览”的紧凑型示范卡，更适合做 PPT、海报和简单视觉设计时参考。
- **页面布局优化**：调整配色页左右栏顶线、示范卡尺寸、色号区域宽度与 HTML 渲染方式，提升 100% 缩放下的信息可见度。
- **测试补充**：新增 `tests/test_color_palette_preview.py`，覆盖色彩示范卡的核心展示内容。
- **新增模块**：配色方案预览页面（`pages/09_9、🎨_配色方案预览.py`），支持从 `data/color_palettes.md` 读取配色数据，以竖条色卡形式展示。
- **配色数据**：从微信公众号文章提取 8 组商务风 3 色配色方案（夜空墨蓝、复古酒红、极简双灰、静谧青灰、复古红棕、黛青法金、醇紫柔雅、商务蓝标），写入 `color_palettes.md` 7-14 号。
- **工具脚本**：`exports/` 新增色卡图片下载、批量 OCR、分区域识别等辅助脚本。
- **项目清理**：删除与 `CLAUDE.md` 重复的 `AGENTS.md`；新增 `.gitignore`（排除 `__pycache__/`、`.claude/`、`.venv/`、`*.db` 等）。

## 2026-05-15
- **课表查询改造**：课表数据不再依赖本地 Excel 文件，首次解析后自动缓存为 JSON（`data/schedule_cache.json`），后续直接读取缓存。
- **路径修复**：Excel 路径从绝对路径改为项目相对路径 `data/` 目录，支持云端部署。
- **部署修复**：修复 Streamlit Cloud 上课表页因找不到本地 Excel 而报错的问题。
- **依赖更新**：`requirements.txt` 新增 `openpyxl` 依赖。

## 2026-05-04
- **结构优化**：全面重写 `README.md`，明确项目定位为“学院行政与教学科研效率工具箱”。
- **新增模块**：增加第 7 个页面 `📥 微信归档工具` 展示页。
- **功能说明**：明确微信归档工具的本地化运行逻辑，线上页面仅作展示。
- **架构梳理**：统一 Streamlit 多页面导航结构与视觉风格。
