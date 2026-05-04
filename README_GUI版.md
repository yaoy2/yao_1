# 微信公众号文章归档 GUI 版

## 你要的效果

双击启动一个本地窗口，然后直接输入：

```text
归档竞赛
https://mp.weixin.qq.com/s/xxxx
https://mp.weixin.qq.com/s/yyyy
```

或者：

```text
归档课题
https://mp.weixin.qq.com/s/xxxx
```

点击“开始归档”，它会自动保存 Markdown 和图片。

## 默认归档目录

课题：

```text
E:\GoogleDrive\Obsidian Vault (1)\ChatGPT\50_教学_课题
```

竞赛：

```text
E:\GoogleDrive\Obsidian Vault (1)\ChatGPT\40_学生_竞赛
```

## 文件说明

```text
wechat_core.py      核心抓取、解析、下载、保存逻辑
wechat_app.py       本地 GUI 界面
requirements.txt    依赖列表
首次安装.bat        第一次使用前双击运行一次
启动微信归档窗口.bat 每次日常使用双击这个
```

## 第一次使用

双击：

```text
首次安装.bat
```

安装完成后，日常使用只需要双击：

```text
启动微信归档窗口.bat
```

## 注意

本工具默认调用你电脑自带的 Microsoft Edge：

```python
p.chromium.launch(channel="msedge")
```

所以不要执行：

```text
playwright install chromium
```

如果遇到验证码或微信风控，可以在界面里取消勾选“后台运行浏览器”，让浏览器显示出来。
