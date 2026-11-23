# v0.8.1 — Single-commit installation and Git workflow

**Preferred:** Review and merge the GitHub feature PR after green Python 3.11/3.12 checks and local portrait-monitor QA. Then simply `git switch main` and `git pull --ff-only origin main` on your Windows PC. Your local data files and saved Alpaca credentials are not touched by the commit.

**Manual offline ZIP alternative** (only if you have not merged the PR):

1. Stop the QuantDesk workstation with Ctrl+C.
2. Ensure clean local `main` tracking the v0.8.0 release. Create `feature/v0.8.1-adaptive-layout` **before** extracting the ZIP.
3. Extract the patch into the repository root, replacing the HTML and adding the test/documentation files.
4. ` .\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v `
5. `git add market_structure_lab/assets/workstation.html tests_market_structure/test_v081_adaptive_layout.py README_V081_ADAPTIVE_LAYOUT.md INSTALL_V081_ONE_COMMIT.md PR_V081.md docs/releases/v0.8.1.md`
6. Run `git diff --cached --check` and inspect `git diff --cached --stat` before creating **one** commit.
7. Commit with `ui: adapt portrait Cross-Market layout v0.8.1` and push the dedicated feature branch.

**Do not create a second branch and push duplicate commits if the GitHub PR already exists.**

For testing: open Cross-Market on the portrait monitor, use All visible symbols, Focus watchlist, screen rotation/window resize, and change screenshot groups. This is a UI-only update; no API-key reset or historical data downloads are needed.
