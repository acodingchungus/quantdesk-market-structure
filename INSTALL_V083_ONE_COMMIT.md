# QuantDesk v0.8.3 — install and verify

**Review the diff and merge PR yourself.** This ZIP is supplied only as a backup: the exact source changes are in the feature branch, not yet in `main`.

After GitHub checks pass and you merge the PR:

```powershell
# Stop the workstation with Ctrl+C
 git switch main
 git pull --ff-only origin main
 .\.venv\Scripts\python.exe -m pip install -r requirements.txt
 .\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
```

Expected: **162 tests**. No API keys or broker SDK are used by the new research modules.

Try the self-contained synthetic test (no market provider needed):

```powershell
 .\.venv\Scripts\python.exe -m market_structure_lab.research_pipeline_v083 demo --out outputs/v083_synthetic_demo
 .\.venv\Scripts\python.exe -m market_structure_lab.research_pipeline_v083 study --manifest outputs/v083_synthetic_demo/manifest.json --out outputs/v083_synthetic_study --cash 100
```

Open `outputs/v083_synthetic_study/report.html` in a browser.

**Real-data audit** is the next practical gate: follow `README_V083_RESEARCH_FOUNDATION.md`. All research CSV prices are UNKNOWN until explicitly verified; do not bypass by guessing. Never upload credentials, private archives or local SQLite data.
