@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m dante models > keys-check.txt 2>&1
type keys-check.txt
echo.
pause
