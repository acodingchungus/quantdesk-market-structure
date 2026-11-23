# v0.7.2 — ONE patch, ONE commit

**Prerequisite:** v0.7.1 must already be merged into `main`, and your working tree must be clean. Do **not** apply a mixed-version stash. The files in this patch are based on v0.7.1, including the secure credential resolver and replay QoL fixes.

```powershell
git switch main
git pull --ff-only origin main
git status --short
git switch -c feature/v0.7.2-universe-backfill
```

Stop QuantDesk; extract the patch ZIP into your **repository root**, replacing matching files. Do not move `data/`, private archives, or SQLite journals.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
# Expected: Ran 108 tests ... OK

# List planned data requests without credentials/network
.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill plan --groups core --start 2026-09-01 --end 2026-09-30 --feed sip
```

**Stage exactly these files** — NO `git add .`:

```powershell
git add market_structure_lab/universe.py market_structure_lab/universe_backfill.py market_structure_lab/sip_archive.py market_structure_lab/market_intelligence.py
git add tests_market_structure/test_v072_universe.py scripts/check_git_sources.py .github/workflows/tests.yml
git add README_V072_UNIVERSE.md INSTALL_V072_ONE_COMMIT.md PR_V072.md docs/releases/v0.7.2.md

git diff --cached --stat
git diff --cached --check
.\.venv\Scripts\python.exe scripts/check_git_sources.py
```

The status and diff must NOT include `data/`, `.env`, private symbols/trades, credentials, `.sqlite`, `outputs/`, or temporary backups. The extension intentionally does **not** modify the stable frontend or trading-strategy code.

```powershell
git commit -m "feat: expand historical universe and backfill tools v0.7.2"
git push -u origin feature/v0.7.2-universe-backfill
```

Open one PR, use `PR_V072.md`, wait for Python 3.11 and 3.12 checks to pass, and merge. Read `README_V072_UNIVERSE.md` for detailed historical backfill commands. The first backfill runs *after* you've verified the code, and will use your locally stored Alpaca paper key.
