# 115 网盘 AI 文件整理系统（完整版）

这是一个“先只读盘点、再人工审核、最后按确认码执行”的 115 文件整理系统。

完整流程包括：

1. 使用 OpenList 中已有的 115 Open 授权，只读扫描指定子文件夹。
2. 保存名称、路径、大小、SHA1 和 115 原生文件 ID。
3. 自动识别电影、电视剧、动漫、纪录片、综艺、字幕等类型并建议名称和目录。
4. 识别同 SHA1、同大小的重复风险，重复文件永不自动删除。
5. 导出 HTML、Excel、JSON 三种报告，在网页中筛选和批准。
6. 把已批准项目生成带防篡改确认码的操作清单，确认后自动建目录、改名和移动。

12TB 视频**不会**下载到电脑里。

## 最简单的使用方式

按顺序双击：

1. `scripts\full_scan_and_report.bat`：粘贴文件夹链接中 `cid=` 后的数字，完整扫描并生成报告。此步骤不修改 115。
2. `scripts\start_web.bat`：在网页中查看建议；也可以点击“批准安全候选”，它会排除重复、低置信度和待识别项目。
3. `scripts\prepare_organize.bat`：生成操作清单和一次性 `APPLY-` 确认码，仍不修改 115。
4. 核对操作清单后双击 `scripts\execute_reviewed_manifest.bat`，粘贴清单路径和确认码，才会执行建目录、改名和移动。

生成的报告位于 `reports`：

- HTML：直接浏览，适合快速审核。
- Excel：适合筛选、标注和留档。
- JSON：供程序复查和后续自动化使用。

### 写入安全边界

- 项目中没有任何删除接口。
- 默认扫描、分类、报告、批准都只改本地索引。
- 没有“已批准 + 未被修改的操作清单 + 完全匹配的确认码”，不会调用 115 写接口。
- 操作清单被手工修改后，确认码立即失效。
- 目标存在同名文件时停止，不覆盖。
- 字幕、图片、压缩包和“其他”默认不自动移动，避免把海报、字幕等附件与主视频拆散。
- 来源文件名或 ID 与扫描结果不一致时停止，要求重新扫描。
- 115 列表重复返回同一原生 ID 时只保留一次，并在扫描统计中单独报告。
- 默认遇到第一个错误立即停止，并把每一步结果写入本地日志。

## 当前状态（2026-09-01）

详细过程、当前断点和换电脑恢复步骤，见 [2026-09-02 交接文档](docs/HANDOFF_2026-09-02.md)。第一阶段排障原始记录保留在 [进度.md](进度.md)。

删减后扫描：Sir 删减文件后，对原测试 CID 重新扫描得到 253 个目录、1342 个唯一文件，约 3.18GB；识别出 98 组、389 个重复风险文件。该轮批准数为 0，真实 115 写操作数为 0。

首次实盘验收：2026-09-02 在“星标视频”中选择 1 个 8.46MB 推广样本，成功新建 `已整理/首次实测`、改名为 `推广样本_01.mp4` 并移动；按同一原生 ID 复核目标存在、来源消失、大小不变。三个主视频未改动，随后已恢复“云下载”挂载。详情见交接文档。

已经完成：

- OpenList v4.2.5 已安装，只监听 `http://127.0.0.1:5244`
- 115 Open 授权成功，只挂载「云下载」，状态 Working
- 只读账号 `organizer-readonly` 已创建
- 整理程序源码、测试、只读扫描逻辑已就绪

已经解决的关键问题：

- 115 网页里「云下载」有约 3616 个文件夹、117 个文件
- OpenList 点进去是空的，所以还没有扫描 50 个文件
- 2026-09-01 实机诊断确认：115 Open 列表接口返回成功但 `data=[]`
- 同一 Token 的官方搜索接口能找到目录；抽样 50 个文件夹，50 个都是 `is_private=1`
- 隐藏属性是首个已确认原因；但取消一个直属子文件夹的隐藏后，根目录仍返回0，说明根级列表还存在另一项115侧限制
- 对一个已取消隐藏的小文件夹实测：OpenList 能看到 111 项，但公开列表不透出原生 `file_id`。
- 新增官方只读扫描通道后，已成功扫描并取得原生 ID。
- 已实现完整报告、重复风险、审核批准、防篡改操作清单，以及官方 Open API 建目录、改名、移动执行器。

不要直接扫全部，也不要批量修改 12TB。先对一个小文件夹实际取消隐藏属性，再做 50 条验证。

### 为什么在 115 里“取消隐藏”后仍然空

本机实测时，115 官方接口仍返回 `is_private=1`。这说明先前的操作没有覆盖这些条目的后端隐藏属性，可能只是退出隐藏浏览模式，也可能没有递归影响子文件夹。这里以接口实际状态为准。

官方文件列表接口没有“包含隐藏条目”的公开参数；OpenList v4.2.5 的 115 Open 驱动调用的正是这个列表接口，所以无法靠 OpenList 的刷新、分页或改 cid 绕过。

可运行脱敏诊断：

```powershell
python -m app diagnose-listing
```

该命令只读 `E:\OpenList\data\data.db` 中当前挂载信息，只向 115 官方接口发出串行只读请求；结果不显示 Token、文件名或个人内容。出现 `hidden_items_excluded_from_listing` 就表示“普通列表为空，但隐藏目录样本存在”。

### 为什么索引阶段改用115官方 Open API

OpenList 的公开 `/api/fs/list` 适合查看目录，但实测只返回名称、大小、时间和哈希，不透出115原生 `file_id`。整理系统不能用文件名伪造 ID，否则重名、改名或移动后会认错文件。

因此现在采用混合方式：OpenList 继续负责本机授权、挂载和状态检查；索引阶段通过同一 Token 调115官方 Open API，只读取得原生 ID。程序会确认指定 CID 位于当前“云下载”挂载范围内，接口请求保持串行，单层目录超过10000项会主动停止。

小文件夹首次扫描命令：

```powershell
python -m app scan-open115 `
  --root-folder-id "小文件夹CID" `
  --dir "/云下载" `
  --depth 8 `
  --max-files 50
```

先验证50个；未确认前不要扩大到500、5000或全量。

## OpenList 是什么

OpenList 是一个网盘挂载工具。它能用官方 115 开放平台方式登录你的 115，然后让本整理程序只读取文件列表。

本项目不使用来路不明的 Cookie 破解方案。

## 115 是怎么接入的

当前使用 OpenList 的 **115 开放平台** 驱动：

- 勾选「使用 OpenList 提供的参数」
- Client ID 留空
- App Secret 留空
- 通过 OpenList 官方 Token 页面授权你的 115

不需要等你自己的 115 开发者申请通过。

## 安装位置

| 项目 | 位置 |
| --- | --- |
| OpenList 程序 | `E:\OpenList\openlist.exe` |
| OpenList 配置 | `E:\OpenList\data\config.json` |
| OpenList 数据库 | `E:\OpenList\data\data.db` |
| OpenList 日志 | `E:\OpenList\data\log\log.log` |
| OpenList 管理员密码 | `E:\OpenList\ADMIN_PASSWORD.txt` |
| 本整理程序 | `E:\github\yao_1\115-ai-organizer` |
| 文件索引数据库 | `E:\github\yao_1\115-ai-organizer\data\115_index.sqlite` |
| 本程序日志 | `E:\github\yao_1\115-ai-organizer\logs\organizer.log` |
| 账号配置 | `E:\github\yao_1\115-ai-organizer\.env` |

OpenList 只监听本机：`http://127.0.0.1:5244`

## 已实现的操作

- 启动 / 停止 OpenList
- 登录 115 授权
- 读取「云下载」目录
- 扫描最多 50 / 500 / 5000 个文件
- 保存本地索引
- 生成整理建议
- 在网页里筛选、搜索、批准或取消批准
- 导出 HTML、Excel、JSON 报告
- 生成防篡改操作清单
- 经人工确认后自动建目录、改名和移动

## 始终禁止或默认拦截的操作

- 删除 115 文件
- 未经批准和确认码的批量重命名、移动
- 覆盖文件
- 修改「云下载」以外的目录
- 下载 12TB 视频
- 把密码、Cookie、Token 写进代码或 Git

`WRITE_MODE` 继续保持 `false`。通用写入入口始终被拦截；远程整理只允许通过带确认码的专用执行器完成。

---

## 第一次使用

请按顺序做。遇到需要你扫码或登录 115 的步骤，按页面提示完成后告诉我。

### 1. 启动 OpenList

双击：

```text
E:\github\yao_1\115-ai-organizer\scripts\start_openlist.bat
```

或在 PowerShell 中执行：

```powershell
cd E:\OpenList
.\openlist.exe start
```

### 2. 打开 OpenList 网页

用浏览器打开：

```text
http://127.0.0.1:5244
```

点右下角 **管理**。

- 用户名：`admin`
- 密码：打开 `E:\OpenList\ADMIN_PASSWORD.txt` 复制

如果忘记密码，在 PowerShell 中执行：

```powershell
cd E:\OpenList
.\openlist.exe admin random
```

新密码会出现在窗口里，请同时写回 `ADMIN_PASSWORD.txt`。

### 3. 给 115 授权（需要你亲自操作）

1. 用浏览器打开：<https://api.oplist.org/>
2. 网盘类型选择 **115**。
3. **勾选**「使用 OpenList 提供的参数」。
4. **客户端 ID** 留空。
5. **应用秘钥** 留空。
6. 点击 **获取 Token**。
7. 按 115 页面提示登录、扫码或点确认。
8. 授权成功后，页面会显示：
   - Access Token
   - Refresh Token
9. 把这两个值复制下来，先放在记事本。不要发给别人，也不要发给 Git。

### 4. 在 OpenList 里只挂载「云下载」

1. 回到 `http://127.0.0.1:5244` 的管理页。
2. 左侧点 **存储** → **添加**。
3. 驱动选择：**115 开放平台**。
4. 挂载路径填写：

```text
/云下载
```

5. 把刚才复制的 Refresh Token、Access Token 填进去。
6. 勾选 **Use online api**。
7. API 地址填写：

```text
https://api.oplist.org/115cloud/renewapi
```

8. 打开 115 网页版：<https://115.com>
9. 点进 **云下载** 文件夹。
10. 看浏览器地址栏，找到 `cid=` 后面的数字。  
    例如：`https://115.com/?cid=123456789&offset=0`  
    这里的根文件夹 ID 就是 `123456789`。
11. 把这个数字填到 OpenList 的 **根文件夹 ID**。
12. 保存。

Client ID 和 App Secret 继续留空。

### 5. 创建一个只读账号

不要让整理程序使用 admin。

1. OpenList 管理页左侧点 **用户** → **添加**。
2. 用户名填写：`organizer-readonly`
3. 密码自己设一个，请记下来。
4. 基本路径填写：

```text
/云下载
```

5. 下面这些权限**全部不要勾选**：
   - 新建目录或上传
   - 重命名
   - 移动
   - 复制
   - 删除
   - WebDAV 管理
6. 保存。

### 6. 填写本程序配置

1. 复制：

```text
E:\github\yao_1\115-ai-organizer\.env.example
```

另存为：

```text
E:\github\yao_1\115-ai-organizer\.env
```

2. 把 `OPENLIST_PASSWORD` 改成刚才那个只读账号的密码。
3. 不要把 `.env` 提交到 Git。

### 7. 检查连接

双击：

```text
E:\github\yao_1\115-ai-organizer\scripts\check_status.bat
```

或执行：

```powershell
cd E:\github\yao_1\115-ai-organizer
python -m app status
```

看到 `logged_in: true` 就说明连接成功。

---

## 怎么扫描

### 先扫 50 个文件

双击：

```text
E:\github\yao_1\115-ai-organizer\scripts\scan_50.bat
```

或：

```powershell
cd E:\github\yao_1\115-ai-organizer
python -m app scan --dir "/云下载" --depth 8 --max-files 50
```

### 再扫 500 个文件

确认 50 个没问题后：

```text
E:\github\yao_1\115-ai-organizer\scripts\scan_500.bat
```

```powershell
python -m app scan --dir "/云下载" --depth 12 --max-files 500
```

### 再扫 5000 个文件

```text
E:\github\yao_1\115-ai-organizer\scripts\scan_5000.bat
```

```powershell
python -m app scan --dir "/云下载" --depth 20 --max-files 5000
```

### 完整扫描并生成报告

```powershell
python -m app full-workflow --root-folder-id "小文件夹CID" --dir "/云下载" --depth 8 --max-files 0
```

`--max-files 0` 表示本次不限制文件数，仍然只读。大目录应从较小子文件夹开始，避免一次任务时间过长。

如果程序提示 **没有原生 file_id**，请停在 50 条，不要继续扩大扫描。

---

## 怎么看整理结果

双击：

```text
E:\github\yao_1\115-ai-organizer\scripts\start_web.bat
```

或：

```powershell
cd E:\github\yao_1\115-ai-organizer
python -m streamlit run app/web.py --server.port 8502
```

浏览器打开后可以看到：

- OpenList / 115 是否连接成功
- 当前扫描目录
- 文件数量和总容量
- 分类统计
- 待识别数量
- 最近一次扫描时间
- 整理计划列表

网页支持：

- 按分类筛选
- 按置信度筛选
- 搜索文件名
- 查看原路径和建议路径
- 批准 / 取消批准
- 一键批准安全候选
- 生成完整报告

「批准」只是本地审核标记，**不会立即移动文件**。只有之后生成操作清单、核对并输入匹配的确认码，专用执行器才会修改 115。

---

## 怎么停止

停止整理网页：在运行窗口按 `Ctrl+C`，或直接关掉那个黑窗口。

停止 OpenList：

双击：

```text
E:\github\yao_1\115-ai-organizer\scripts\stop_openlist.bat
```

或：

```powershell
cd E:\OpenList
.\openlist.exe stop
```

---

## 怎么重新授权

如果 115 登录过期：

1. 再打开 <https://api.oplist.org/>
2. 仍然勾选「使用 OpenList 提供的参数」
3. Client ID、App Secret 留空
4. 重新获取 Token
5. 打开 OpenList 管理页 → 存储 → 编辑「云下载」
6. 只更新 Access Token 和 Refresh Token
7. 保存后再运行 `python -m app status`

---

## 常用命令

在 `E:\github\yao_1\115-ai-organizer` 目录下：

```powershell
python -m app status
python -m app probe --dir "/云下载"
python -m app diagnose-listing
python -m app scan-open115 --root-folder-id "小文件夹CID" --dir "/云下载" --depth 8 --max-files 50
python -m app full-workflow --root-folder-id "小文件夹CID" --dir "/云下载" --depth 8 --max-files 0
python -m app scan --dir "/云下载" --depth 8 --max-files 50
python -m app stats
python -m app rebuild-plans
python -m app report
python -m app approve-safe
python -m app prepare-execution --scan-root-id "小文件夹CID" --scan-root-path "/云下载"
python -m app execute-open115 --manifest "操作清单.json" --confirm "APPLY-确认码"
python -m unittest discover -s tests -v
```

`probe` 遇到空目录会返回失败，不再把“0 条”当作探测成功。只读账号没有强制刷新权限时，结果会标记为 `empty_listing_refresh_denied`。

## 数据库和日志

- 数据库：`data/115_index.sqlite`
- 日志：`logs/organizer.log`
- 这些文件都不会提交到 Git

重复扫描时，同一个 115 原生 ID 会更新路径和名称，不会因改名或移动生成重复索引。

## 自动整理执行顺序

执行器只处理已批准且通过安全检查的项目：

1. 再次核验来源 ID、父目录 ID 和原文件名。
2. 逐级确认目标目录，不存在时创建。
3. 检查目标是否已有同名文件；有则停止，不覆盖。
4. 按原生 ID 重命名和移动。
5. 再次读取目标目录，核验最终名称和位置。
6. 写入本地操作日志；失败默认立即停止。

项目不实现删除，也不对疑似重复文件做自动处置。
