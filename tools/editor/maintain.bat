@echo off
rem HoyoCalendar auto-maintain: extract + calibrate + apply
cd /d "%~dp0"
python maintain.py
echo.
pause
