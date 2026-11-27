@echo off
rem 自动维护 + 推送：Windows 计划任务入口（见 DEVELOPMENT_PLAN §6.9）
cd /d "%~dp0"
if not exist logs mkdir logs
python maintain.py
if errorlevel 1 exit /b %errorlevel%
python push_data.py >> logs\push.log 2>&1
exit /b %errorlevel%
