@echo off
setlocal
cd /d "%~dp0"

REM Optional build step: creates LaborForceScheduler.exe in this folder.
REM NOTE: One-file EXE bundles assets internally. Data/history/exports remain next to the EXE.

py -m pip install --upgrade pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed --name LaborForceScheduler ^
  --icon "assets\scheduler.ico" ^
  --add-data "assets;assets" ^
  LaborForceScheduler.py

if exist "dist\LaborForceScheduler.exe" (
  copy /y "dist\LaborForceScheduler.exe" "%~dp0LaborForceScheduler.exe" >nul
  echo Built: LaborForceScheduler.exe
) else (
  echo Build failed. Check output above.
)
pause
