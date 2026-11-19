@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul && start "" pythonw -m dante gui && exit /b 0
python -m dante gui
if errorlevel 1 pause
