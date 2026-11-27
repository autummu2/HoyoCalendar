@echo off
rem 自动维护 + 推送：本机脚本链入口（见 DEVELOPMENT_PLAN §6.9）
cd /d "%~dp0"
rem 控制台默认 GBK，标题里的 U+2022（•）无法编码会让整轮中断（2026-11-27 实测）
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
if not exist logs mkdir logs
python maintain.py
if errorlevel 1 exit /b %errorlevel%
python push_data.py >> logs\push.log 2>&1
exit /b %errorlevel%
