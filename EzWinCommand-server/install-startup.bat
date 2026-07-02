@echo off
cd /d "%~dp0"
pythonw.exe app.py --install
echo EzWinCommand Agent 已注册开机自启动。
pause
