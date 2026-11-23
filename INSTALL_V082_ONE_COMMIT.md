# QuantDesk v0.8.2 — Install and publish in one PR (Windows PowerShell)

This patch is based on **v0.8.1 merged into `main`**. Nothing here requires local secrets or historical data to be shared. **Don't apply this patch to an older branch.** Stop the server using Ctrl+C.

```powershell
git switch main
git pull --ff-only origin main
git status --short
git switch -c feature/v0.8.2-confluence
```

Before proceeding, `git status --short` should be empty and the new feature branch should exist. Extract the ZIP at your project root, replacing the matching files. If the remote PR branch already exists, instead switch to it using `git fetch origin` and `git switch --track origin/feature/v0.8.2-confluence`; do **not** attempt to recreate it.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
```

Expected: **147 tests, OK**. The tests are offline. Then:

```powershell
git add market_structure_lab/cross_signals_v082.py market_structure_lab/workstation.py market_structure_lab/assets/workstation.html
git add tests_market_structure/test_v082_cross_signals.py .github/workflows/tests.yml scripts/check_git_sources.py
git add README_V082_CROSS_SIGNALS.md INSTALL_V082_ONE_COMMIT.md PR_V082.md docs/releases/v0.8.2.md
.\.venv\Scripts\python.exe scripts/check_git_sources.py
git diff --cached --check
git diff --cached --stat
```

Check the staged manifest; NEVER stage `data`, `outputs`, secrets, `.env`, Windows Credential Manager files or `.sqlite`. If this branch was already pushed by the connected GitHub integration and matches your patch, no new commit is needed. Otherwise:

```powershell
git commit -m "feat: add causal cross-asset confluence research v0.8.2"
git push -u origin HEAD
```

Open the PR **against `main`** using `PR_V082.md`. Wait for Python 3.11/3.12 CI and review, then **you** choose whether to merge. Start the app with your usual command:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data
```

Open Cross-Market → expand **Cross-asset KDE confluence research** → choose `Inspect selected close` or `Compare KDE events`. Missing peer data is *expected* until sufficient synchronized daily context is loaded. Optional read-only Alpaca polling remains a separate opt-in.
