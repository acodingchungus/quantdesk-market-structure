# QuantDesk v0.7.3 — One-shot install, one Git commit

## IMPORTANT BEFORE INSTALLING

1. **Finish testing and merge v0.7.2 first**, with both the Empty Session and Dashboard Startup hotfixes. Do not combine this release with an uncommitted v0.7.2 patch.
2. Back up any personal research files if desired. The ZIP includes only source/tests/docs, and **must not contain** credentials, market data, `.env`, or SQLite journals.
3. In PowerShell, from your existing `QuantDesk_Market_Structure_v0_3` directory:

```powershell
git switch main
git pull --ff-only origin main
git status --short
```

If status is not empty, stop and determine what those changes are before extracting.

```powershell
git switch -c feature/v0.7.3-performance
```

## Install

Extract `QuantDesk_v0_7_3_Performance_ONE_SHOT_PATCH.zip` into the repository root, preserving folder structure and replacing matching source files. It is specifically built on the corrected v0.7.2 source.

**Replaced:**

- `market_structure_lab/workstation.py`
- `market_structure_lab/volume_profile.py`
- `market_structure_lab/assets/workstation.html`

**New:**

- `tests_market_structure/test_v073_performance.py`
- `scripts/benchmark_replay_v073.py`
- `README_V073_PERFORMANCE.md`
- `INSTALL_V073_ONE_COMMIT.md`
- `PR_V073.md`

No `pip install` is required: there are no new runtime dependencies.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
.\.venv\Scripts\python.exe -m scripts.benchmark_replay_v073 --trades 80000 --seeks 8
```

Expected: **120 tests, OK**, plus a printed *synthetic* speed comparison and equality checks. Results vary by machine.

Close the running workstation with `Ctrl+C`, then relaunch:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data
```

In your browser open `http://127.0.0.1:8765/` and hard refresh with `Ctrl+Shift+R`. Check SPY/QQQ at 1m, 5m, 15m and 1h. Rapidly scrub and switch for 1–2 minutes; check that the chart stays interactive. The profile panel will say it is waiting while moving; it fills after navigation settles or playback pauses. This is intentional to protect UI responsiveness and point-in-time correctness.

## One commit and PR

From the feature branch:

```powershell
git add market_structure_lab/workstation.py market_structure_lab/volume_profile.py market_structure_lab/assets/workstation.html
git add tests_market_structure/test_v073_performance.py scripts/benchmark_replay_v073.py
git add README_V073_PERFORMANCE.md INSTALL_V073_ONE_COMMIT.md PR_V073.md
.\.venv\Scripts\python.exe scripts/check_git_sources.py
git diff --cached --stat
git diff --cached --check
```

**Inspect** `git status --short` and the staged diff for unexpected `.env`, API keys, data, backups, or journal files. Never use `git add .` automatically in this repository.

```powershell
git commit -m "perf: optimize exact replay and volume profile queries v0.7.3"
git push -u origin HEAD
```

Open a PR from `feature/v0.7.3-performance` to `main` using `PR_V073.md`. Confirm Python 3.11 and 3.12 CI checks pass before merging. Keep earlier backup stashes intact until finished.
