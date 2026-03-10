@echo off
setlocal
cd /d "%~dp0"
REM Launch LaborForceScheduler (portable)
REM Uses pythonw if available, falls back to python.
if exist "%~dp0\scheduler_app_v3_final.py" (
    where pythonw >nul 2>nul
    if %errorlevel%==0 (
        start "" pythonw "%~dp0\scheduler_app_v3_final.py"
    ) else (
        start "" python "%~dp0\scheduler_app_v3_final.py"
    )
) else (
    echo ERROR: scheduler_app_v3_final.py not found.
    pause
)
endlocal
