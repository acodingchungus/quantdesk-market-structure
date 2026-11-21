# QuantDesk Market Structure Workstation v0.3.1

**The navy/black UI release is ready. Start with [README_V031.md](README_V031.md) for installation or upgrading v0.3 without losing your SQLite notes.**

# QuantDesk Market Structure Lab v0.3

**A local research workstation for historical SPY/QQQ price reaction zones. No live data. No orders.**

Start with **[README_V03.md](README_V03.md)** for the Windows setup and architecture.

## Quick start on Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data
```

Browse **http://127.0.0.1:8765/** while the Python terminal remains open, or double-click **`start_workstation.bat`** after dependencies are installed.

Historical data through **2026-10-01**. The original standalone `SPY_replay.html` and `QQQ_replay.html` remain in `outputs/v02_real_sip/`, with instructions in [README_V02.md](README_V02.md). The original detector and research methodology are unchanged. No proven edge or options P&L.
