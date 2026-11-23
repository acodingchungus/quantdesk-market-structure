# QuantDesk v0.8.0 — one feature branch, one commit

This is a **replacement-file patch**, not a new repository. Your local market data, vault credentials, SQLite notes and `.backup` archives are preserved.

## 1. Start from verified v0.7.3 main

Stop the running server (`Ctrl+C`). From your existing QuantDesk repository:

```powershell
git switch main
git pull --ff-only origin main
git status --short
```

`git status --short` **must be empty** before proceeding. If it's not, do not blindly discard files or run `git add .`; investigate first. After it is clean:

```powershell
git switch -c feature/v0.8-cross-market
```

## 2. Extract once

Extract the contents of `QuantDesk_v0_8_0_Cross_Market_ONE_SHOT_PATCH.zip` to the **repository root**, allowing Windows to replace matching files. Do not extract into `market_structure_lab` alone or create an extra nested version folder.

The patch replaces seven existing source/UI/CI files and adds three Python source modules, one test module and four release documents plus a screenshot-derived CSV catalog. It does **not** include `README.md` because your existing portfolio introduction should not be overwritten.

## 3. Test before Git

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
```

Expected development baseline: **135 tests, OK**. Test offline UI first:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data
```

Check **Cross-Market → Historical / TradingView Watchlists** and verify that Live Market and Historical Replay remain responsive. No new Alpaca connection is started by default. Restart with `--enable-watchlist-poll --live-feed iex` only after confirming stored paper credentials.

## 4. Stage exactly this release (not local market data)

```powershell
git add market_structure_lab/watchlist_v08.py market_structure_lab/cross_asset_v08.py market_structure_lab/live_watchlist_v08.py
git add market_structure_lab/universe.py market_structure_lab/universe_backfill.py market_structure_lab/live_tape.py market_structure_lab/workstation.py market_structure_lab/assets/workstation.html
git add tests_market_structure/test_v08_crossasset_watchlists.py
git add scripts/check_git_sources.py .github/workflows/tests.yml
git add README_V080_CROSS_ASSET.md INSTALL_V080_ONE_COMMIT.md PR_V080.md docs/releases/v0.8.0.md docs/watchlist_screenshot_catalog.csv

.\.venv\Scripts\python.exe scripts/check_git_sources.py
git diff --cached --check
git diff --cached --stat
git status --short
```

Check that you **did not stage** `data/`, `data_demo/`, `outputs/`, `.env`, vault content, ZIP backups, `.sqlite`, or your own notes. Inspect staged code for accidentally pasted credentials.

```powershell
git commit -m "feat: add causal cross-asset research and read-only live watchlists v0.8"
git push -u origin HEAD
```

## 5. GitHub PR

PR base **main**, compare **feature/v0.8-cross-market**. The prepared PR text is in `PR_V080.md`. Wait for green GitHub Actions Python 3.11 and 3.12 checks and test in Opera GX before merging.

After merging, synchronize your `main`:

```powershell
git switch main
git pull --ff-only origin main
```

**No account keys are contained in this ZIP. No broker order endpoints are created.**
