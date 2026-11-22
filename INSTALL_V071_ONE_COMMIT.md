# v0.7.1 one-commit install (Windows PowerShell)

**Precondition: v0.7 already merged to `main` and your tree clean.** Do NOT apply to the still-unmerged v0.6.3 branch.

```powershell
git switch main
git pull --ff-only origin main
git status
git switch -c feature/v0.7.1-replay-credentials
```

Stop the workstation. Extract this patch to the existing project ROOT and replace matching files. Do not place it inside `market_structure_lab/` as an extra nested directory.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
```

Expected on the assembled v0.7 base: **101 tests**, `OK`.

Once per Windows user, save paper keys using the **local hidden terminal prompts**:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.credentials save
.\.venv\Scripts\python.exe -m market_structure_lab.credentials status
```

Restart your terminal; then test a read-only data command without exporting environment variables. Check both daily/intraday replay and `Last date` after switching to 5m. Check speeds 6×, 8×, 10×.

**Stage only these paths** (no `git add .`):

```powershell
git add market_structure_lab/credentials.py market_structure_lab/fetch_alpaca.py market_structure_lab/fetch_alpaca_trades.py market_structure_lab/fetch_alpaca_minutes.py market_structure_lab/fetch_alpaca_context.py market_structure_lab/live_tape.py market_structure_lab/sip_archive.py market_structure_lab/assets/workstation.html requirements.txt tests_market_structure/test_credentials.py tests_market_structure/test_v071_qol.py README_V071_SECURE_KEYS_AND_REPLAY.md INSTALL_V071_ONE_COMMIT.md PR_V071.md

git diff --cached --stat
git diff --cached --check
git status --short
```

Review staged files; ensure no credentials, `data/`, `.env`, `.sqlite`, or market-data downloads are staged. Then:

```powershell
git commit -m "feat: persist Alpaca paper keys securely and polish replay v0.7.1"
git push -u origin feature/v0.7.1-replay-credentials
```

Open one PR, paste title/body from `PR_V071.md`, wait for green Python 3.11/3.12 CI, then merge. This patch does not require manually editing Python files.
