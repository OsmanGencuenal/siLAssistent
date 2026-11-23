@echo off
setlocal
for /f %%T in ('powershell -NoProfile -Command "[DateTime]::UtcNow.Ticks"') do set "BuildStartTicks=%%T"
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
    echo ### BUILD ERFOLGREICH ABGESCHLOSSEN ###
) else (
    echo ### BUILD FEHLGESCHLAGEN ###
    echo.
    echo Build wurde mit Fehlercode %BuildResult% beendet. Details stehen oben.
)
powershell -NoProfile -Command "$elapsed=[TimeSpan]::FromTicks([DateTime]::UtcNow.Ticks - [long]$env:BuildStartTicks); Write-Host ('Gesamte Build-Zeit: {0:00}:{1:00}:{2:00}' -f [math]::Floor($elapsed.TotalHours),$elapsed.Minutes,$elapsed.Seconds)"
echo.
pause
exit /b %BuildResult%
