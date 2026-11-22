# v0.7 one-commit installation (AFTER v0.6.3)

1. **Finish v0.6.2 PR first.** Confirm GitHub Actions is green on 3.11 and 3.12; merge it and `git switch main && git pull --ff-only origin main`.
2. Apply **the separately supplied v0.6.3 SIP archive patch** to your existing project, test 80/80, commit, push, open PR, merge, and update `main`. First test a one-day SIP archive download/audit from `README_V063_SIP_ARCHIVE.md` with your local API keys. No need to download a month to begin v0.7.
3. Once `main` contains v0.6.3, check `git status`. If clean:

```powershell
git switch main
git pull --ff-only origin main
git switch -c feature/v0.7-research-engine
```

4. Extract the **v0.7 patch** over the SAME repository root, merging folders and replacing matching files. It does NOT replace root `README.md`, `LICENSE`, `data/`, API credentials, or SQLite journal.
5. Test the updated checkout:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
.\.venv\Scripts\python.exe -m market_structure_lab.experiment_lab --data-dir data --out outputs/v07_research
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data
```

Expected **90+ tests OK**; open `http://127.0.0.1:8765/` → Research Lab. The newer v0.7 module outputs only daily underlying research, not options profitability.

6. **Stage ONLY these files** to avoid historical data or credentials entering Git:

```powershell
git add market_structure_lab/experiment_lab.py market_structure_lab/workstation.py market_structure_lab/assets/workstation.html
 git add tests_market_structure/test_v04_intraday.py tests_market_structure/test_v05_volume_profile.py tests_market_structure/test_v06_intelligence.py tests_market_structure/test_v07_experiments.py
 git add scripts/check_git_sources.py .github/workflows/tests.yml README_V07_RESEARCH_ENGINE.md INSTALL_V07_ONE_COMMIT.md docs/releases/v0.7.md
.\.venv\Scripts\python.exe scripts/check_git_sources.py
git diff --cached --stat
git diff --cached --check
git commit -m "feat: add v0.7 quantitative research and event-study engine"
git push -u origin feature/v0.7-research-engine
```

NOTE: If `check_git_sources.py` reports untracked required files from v0.5.1/v0.6, **do not commit yet**. Review that list, stage missing source/test modules, re-run the test suite, then commit. This specifically guards against the previous Github Actions missing-module failures.

7. Open a v0.7 pull request using `PR_V07_TITLE_AND_BODY.md`; wait for clean CI and merge. Then:

```powershell
git switch main
git pull --ff-only origin main
git tag v0.7.0
git push origin v0.7.0
```

**Never commit** `data/`, `data_demo/`, `outputs/`, `.env` or secret keys. Research results and market data remain local. Offline lab can be used without Alpaca credentials.
