@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run the installation steps in README.md.
  pause
  exit /b 1
)
if not exist "data_demo\SPY.csv" (
  echo Creating SYNTHETIC demo data - NOT real market prices.
  ".venv\Scripts\python.exe" -m market_structure_lab.demo --output-dir data_demo
  if errorlevel 1 exit /b 1
)
echo Local research dashboard: http://127.0.0.1:8765/
".venv\Scripts\python.exe" -m market_structure_lab.workstation --data-dir data_demo
pause
