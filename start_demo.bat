@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Install Python dependencies from README.md first.
  pause
  exit /b 1
)
if not exist "data_demo\SPY.csv" (
  ".venv\Scripts\python.exe" -m market_structure_lab.demo --output-dir data_demo
  if errorlevel 1 exit /b 1
)
if not exist "data_demo\intraday\SPY_1m.csv" (
  ".venv\Scripts\python.exe" -m market_structure_lab.intraday_demo --data-dir data_demo
  if errorlevel 1 exit /b 1
)
if not exist "data_demo\trades\SPY_trades.csv" (
  ".venv\Scripts\python.exe" -m market_structure_lab.volume_profile_demo --data-dir data_demo
  if errorlevel 1 exit /b 1
)
if not exist "data_demo\context\XLK.csv" (
  ".venv\Scripts\python.exe" -m market_structure_lab.market_context_demo --data-dir data_demo
  if errorlevel 1 exit /b 1
)
echo SYNTHETIC OFFLINE DEMO. NOT REAL MARKET DATA.
".venv\Scripts\python.exe" -m market_structure_lab.workstation --data-dir data_demo
pause
