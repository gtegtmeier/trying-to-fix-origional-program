@echo off
setlocal
cd /d "%~dp0"

set LOGFILE=run_log.txt
echo.>>"%LOGFILE%"
echo =============================================================================>>"%LOGFILE%"
echo Time: %date% %time%>>"%LOGFILE%"

if exist "LaborForceScheduler.exe" (
  echo Launching: LaborForceScheduler.exe>>"%LOGFILE%"
  start "" "LaborForceScheduler.exe" >>"%LOGFILE%" 2>>&1
  exit /b
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
  echo Launching: pythonw scheduler_app_v3_final.py>>"%LOGFILE%"
  start "" pythonw "scheduler_app_v3_final.py" >>"%LOGFILE%" 2>>&1
  exit /b
)

where pyw >nul 2>nul
if %errorlevel%==0 (
  echo Launching: pyw scheduler_app_v3_final.py>>"%LOGFILE%"
  start "" pyw "scheduler_app_v3_final.py" >>"%LOGFILE%" 2>>&1
  exit /b
)

echo Launching: py scheduler_app_v3_final.py>>"%LOGFILE%"
start "" py "scheduler_app_v3_final.py" >>"%LOGFILE%" 2>>&1
