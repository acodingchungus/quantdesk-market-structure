# QuantDesk v0.6.1 — Graphite Terminal (replace files, ONE commit)

This ZIP is a **ready-to-overlay patch** for **QuantDesk v0.6** (including your v0.5.1 importer). It does **not** contain a new repo, API keys, research database, Python backend changes or main README. No need to follow seven mini-commits from the earlier design plan.

1. Stop the running workstation (Ctrl+C). Open PowerShell in your **existing** QuantDesk Git repository. Confirm `git status` is clean. If v0.6 is not merged into `main` yet, merge it first.
2. Run:

   ```powershell
   git switch main
   git pull --ff-only origin main
   git switch -c feature/v0.6.1-graphite-terminal
   ```

3. Extract this ZIP into your EXISTING repository root. **Merge folders, replace matching files.** Copy `market_structure_lab/`, `tests_market_structure/`, `docs/`, and `INSTALL_ONE_COMMIT.md` if desired. Keep `README.md`, `.env`, `data/`, `outputs/`, and `LICENSE` unchanged.
4. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
   .\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data
   ```

5. Open `http://127.0.0.1:8765/` and check **Replay / Live / Research**. If using demo data, replace `--data-dir data` with `--data-dir data_demo` and launch as normal. Hard-refresh browser with Ctrl+Shift+R if it shows old colors.
6. After reviewing changes and checking no ignored data or credentials are staged, use **one commit**:

   ```powershell
   git add market_structure_lab/assets/workstation.html tests_market_structure/test_v031_ui.py tests_market_structure/test_v061_graphite.py docs/ROADMAP.md docs/releases/v0.6.1.md docs/design/GRAPHITE_TERMINAL_SPEC.md docs/preview-v061-graphite-desktop.png docs/preview-v061-graphite-mobile.png
   git diff --cached --stat
   git commit -m "style: ship Graphite Terminal UI v0.6.1"
   git push -u origin feature/v0.6.1-graphite-terminal
   ```

Then create a PR into main, review checks, merge, switch to main, pull and tag `v0.6.1` if you want a release. The patch does not overwrite your personal GitHub README or research notes.

If your checkout already contains uncommitted v0.6.1 changes, don't blindly overwrite them; back them up or inspect `git diff` first.
