@echo off
rem "Send to -> DANTE": copy the chosen files to C:\DANTE\drop and ask the pult to read them.
rem «Надіслати -> Данте»: копіює вибрані файли в C:\DANTE\drop і дає пульту завдання їх прочитати.
if not exist C:\DANTE\drop mkdir C:\DANTE\drop
:next
if "%~1"=="" goto job
copy /y "%~1" C:\DANTE\drop\ >nul
shift
goto next
:job
set T=%date:~-4%%date:~3,2%%date:~0,2%-%time:~0,2%%time:~3,2%%time:~6,2%
set T=%T: =0%
> "C:\DANTE\inbox\zz-drop-%T%.json" echo {"kind":"cmd","lane":"drop","owner":"author-sendto","command":"cd /d C:\\DANTE\\dante ^& python C:\\DANTE\\proby\\intake\\drop_run.py","timeout":3600}
echo DANTE: files are in the queue, reports in C:\DANTE\drop\out / файли в черзі, звіти в C:\DANTE\drop\out
timeout /t 3 >nul
