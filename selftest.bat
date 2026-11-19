@echo off
cd /d "%~dp0"
echo DANTE self-test... (about 1 minute)
python -m dante selftest > selftest.txt 2>&1
type selftest.txt | findstr /C:"OK " /C:"FAIL" /C:"RESULT" /C:"Ran " /C:"busy" /C:"python processes"
echo.
echo Full report: selftest.txt. This window closes in 30 s.
timeout /t 30 >nul
