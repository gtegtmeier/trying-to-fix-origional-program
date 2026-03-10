@echo off
setlocal
cd /d "%~dp0"

REM This updater replaces ONLY the program file and keeps your data intact.
REM 1) Put the new LaborForceScheduler.py next to this file.
REM 2) Run this .bat. Your data in .\data\scheduler_data.json is preserved.

if not exist "LaborForceScheduler.py" (
  echo ERROR: LaborForceScheduler.py not found in this folder.
  pause
  exit /b 1
)

echo Program updated in-place. Data preserved.
pause
