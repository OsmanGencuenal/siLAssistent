@echo off
setlocal
if exist "%~dp0.build-env\Scripts\python.exe" (
    "%~dp0.build-env\Scripts\python.exe" -B "%~dp0tools\select_build_version.py"
) else (
    py -3.13 -B "%~dp0tools\select_build_version.py"
)
if errorlevel 1 goto :BuildFinished
if "%~1"=="" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build_siLAssistent.ps1" -CreateInstaller
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build_siLAssistent.ps1" %*
)
:BuildFinished
set "BuildResult=%errorlevel%"
echo.
if "%BuildResult%"=="0" (
    echo ##### BUILD ABGESCHLOSSEN #####
    echo.
    echo Build erfolgreich abgeschlossen.
) else (
    echo ##### BUILD FEHLGESCHLAGEN #####
    echo.
    echo Build wurde mit Fehlercode %BuildResult% beendet. Details stehen oben.
)
pause
exit /b %BuildResult%
