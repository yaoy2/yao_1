@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 正在启动微信公众号文章归档窗口...
echo 固定地址：http://localhost:8502
echo 如果浏览器没有自动打开，请复制上面的地址到浏览器。
echo.

".venv\Scripts\python.exe" -m streamlit run wechat_app.py --server.port 8502 --server.address localhost

pause
