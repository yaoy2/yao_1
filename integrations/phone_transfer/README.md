# M25 随手传

Streamlit 自定义组件，iPhone 发送，办公电脑 L 的 Edge/Chrome 接收。
两端用工具箱的 HTTPS 连接转送加密分块，无需同一局域网、额外账号或桌面接收程序。

## 使用

在 L 打开 M25，选择“设为办公电脑 L”及保存文件夹。手机扫描绑定二维码。
二维码指向本工具箱 M25 页面，文件夹权限和绑定保存在同源 IndexedDB。
接收页面须保持打开；“独立接收窗口”可在切换其他模块时继续接收。
同源 Web Lock 只允许一个接收标签页工作；独立窗口会接管当前接收，意外重复打开时提示关闭旧页。
浏览器仍可暂停后台标签页；需要时让接收页保持活动，并在 Edge 中将工具箱加入休眠例外。

仅从“文件”选择相册导出的未修改原片，才能绕开 iOS 相册选择器可能发生的格式转换。
工具本身不转换图片。实况照片原件需同时选择导出的图片及视频。

## 保存和身份

- 每批保存到 `所选目录/YYYY-MM-DD/HHMMSS_随机批次ID/序号_原文件名`；同名冲突另取新名字。
- 最多 500 个文件，每个最多 200 MiB。以 512 KiB 分块、每约 2 MiB 等待写入确认，限制内存积压。
- 传输时计算 SHA-256，关闭文件后重新读取校验，最后才回执；不完整文件不列入成功清单。
- 中断可能留下新建的空占位文件；不会删除或覆盖用户已有文件。重发另建批次。
- 接收端生成不可导出的 ECDSA 私钥。手机保存对应公钥与授权密钥；复制手机链接不能冒充 L。
- 双方用新随机挑战、角色独立 HMAC、接收端签名及本次连接 ID 验证身份。
- 分块采用 HKDF 派生的方向独立 AES-GCM 密钥；密文绑定房间、收发方、序号，拒绝篡改与重放。
- Python 仅取得独立派生的路由授权摘要及密文；密文暂存进程内有界队列，单收件箱 4 MiB、全局 32 MiB，上限包含信封。
- 队列有确认、重传去重和过期清理，不写磁盘或 GitHub。Streamlit 重启、断网或接收页休眠会中断当前传输，重发即可。
- 绑定链接放在 URL fragment，不传给 HTTP 服务；读取后清除。勿把真实链接、私钥或授权密钥提交到仓库。
- 浏览器不能读取 Windows 主机名。这里固定的是 L 上首次设置的浏览器身份，不是主机名硬件校验。

## 开发验证

在本目录运行 `npm ci`、`npm test`、`npm run build`。
提交 `frontend/app.js` 构建产物，线上无需 Node，也不增加 Python 依赖。
在仓库根目录运行 `python -m pytest tests/test_phone_transfer_relay.py tests/test_phone_transfer_page.py`。

`tests/browser.mjs` 使用两个隔离的真实浏览器会话、双层同源 iframe 和 OPFS 测试目录，
通过测试用 JSON 适配器调用实际 Python 中转队列，不启动 Streamlit。
`TRANSFER_PLAYWRIGHT` 指定已安装的 Playwright ES 模块入口，`TRANSFER_BROWSER` 指定 Chrome/Edge，
`TRANSFER_TEST_MIB` 默认 200；`TRANSFER_LATENCY_MS` 默认 100，模拟每次请求额外耗时。
测试验证密文收发与保存字节、同名文件、绑定保留、返回页面重连、单接收锁；
不等同于 iPhone 蜂窝实测、真实文件夹授权或线上吞吐量验收。
临时输出在忽略的 `test-output-可删/`。

第三方代码：前端使用 MIT 许可的 `@noble/hashes` 和 `qrcode`，版本锁定在 package-lock.json。
