# One-shot installation: v0.6.3 Historical SIP Archive

1. Stop the QuantDesk server (`Ctrl+C`). **Keep `data/`, API keys, and SQLite journals private.**
2. From your existing repo, make sure v0.6.2 is committed and your working tree is clean. Then:

   ```powershell
   git status
   git switch main
   git pull --ff-only origin main
   git switch -c feature/v0.6.3-sip-archive
   ```
3. Copy the files from the **patch ZIP** into the repo root; merge folders and replace `market_structure_lab/workstation.py` and `market_structure_lab/assets/workstation.html` (a tiny data-availability label update; theme/shortcuts unchanged). No personal README, UI stylesheet, notes, or market-data files are included in the patch.
4. Test:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
   ```

   Expected: **80 tests, OK** (71 baseline + 9 new archive tests). This is an offline test; we cannot verify your Alpaca subscription without your local credentials.
5. Read `README_V063_SIP_ARCHIVE.md`. Do the **one-day** SIP download, then audit it, before asking the downloader to retrieve an entire month.
6. Only after confirming the patch works and reviewing your staged files:

   ```powershell
   git add market_structure_lab/sip_archive.py market_structure_lab/workstation.py market_structure_lab/assets/workstation.html tests_market_structure/test_v063_sip_archive.py README_V063_SIP_ARCHIVE.md docs/releases/v0.6.3.md INSTALL_ONE_COMMIT_V063.md
   git diff --cached --stat
   git commit -m "feat: archive historical SIP data and audit coverage v0.6.3"
   git push -u origin feature/v0.6.3-sip-archive
   ```

Then open one pull request and merge it when checks pass. **Never** stage files inside `data/` or environment secret files.

### Unchanged and intentional

- No `README.md` replacement; your personally edited homepage is preserved.
- No v0.6.2 theme/keyboard modifications.
- No edits to original KDE / ATR / reaction formulas.
- No live trading, order routes, or broker execution.
