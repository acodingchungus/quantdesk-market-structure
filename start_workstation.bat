@echo off
setlocal
cd /d "%~dp0"
echo QuantDesk Market Structure Workstation v0.3.1 - Midnight Navy, Local Research Only
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m market_structure_lab.workstation --data-dir data
) else (
  py -3 -m market_structure_lab.workstation --data-dir data
)
echo.
echo QuantDesk workstation is stopped. Press any key to close.
pause >nul
