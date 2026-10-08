@echo off
REM Copies plans\ (every plan, every version, and plans\_archive\) to a dated folder in
REM Documents\trade-plans-backup\. Nothing in plans\ is changed.

cd /d "%~dp0"
if not exist "plans" (
    echo No plans\ folder yet -- nothing saved to back up.
    pause
    exit /b 0
)
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set STAMP=%%d
set DEST=%USERPROFILE%\Documents\trade-plans-backup\%STAMP%
robocopy "plans" "%DEST%" /E /NFL /NDL /NJH /NJS >nul
if %ERRORLEVEL% GEQ 8 (
    echo Backup FAILED.
) else (
    echo Plans backed up to %DEST%
)
pause
