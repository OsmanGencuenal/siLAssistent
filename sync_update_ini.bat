@echo off
setlocal
if exist "%~dp0.build-env\Scripts\python.exe" (
    "%~dp0.build-env\Scripts\python.exe" "%~dp0tools\sync_update_ini.py"
) else (
    py -3.13 "%~dp0tools\sync_update_ini.py"
)
exit /b %errorlevel%
