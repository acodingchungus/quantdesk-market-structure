# QuantDesk v0.7.2 — Frontend startup hotfix

## Symptoms

Python prints that SPY and QQQ historical minute data loaded, but the browser remains on Loading. All workspace tabs are unresponsive, with no data in the chart.

## Root cause (confirmed from released v0.7.1 ZIP)

The `loadDates` function contains an inline `//` JavaScript comment which accidentally comments out the remaining executable code and closing braces on that line. This causes `SyntaxError: Unexpected end of input` when the HTML script is parsed, preventing all event handlers and dashboard initialization.

## Fix

The comment is moved to its own line, preserving existing time-frame switching behavior and the `sessionSlider` update. This patch contains the corrected `market_structure_lab/assets/workstation.html` **plus** a regression test (`tests_market_structure/test_v072_dashboard_startup.py`). It does NOT alter data files, keys, journals, backend research code, or your existing `.backup` files.

## Install

1. Stop the running workstation with Ctrl+C. Stay on `feature/v0.7.2-universe-backfill`.
2. Extract this ZIP into your QuantDesk project **root**, merging folders and replacing the HTML file. You can keep the regression test next to the existing tests.
3. Run ` .\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v `.
4. Restart: ` .\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data `.
5. In the browser, reload at `http://127.0.0.1:8765/` using Ctrl+Shift+R. The workspace tabs and charts should become interactive.

If it still fails, open browser Developer Tools (F12) > Console and send the **first red error** (without secrets).

## Existing backup error

`Existing backup data\intraday\SPY_1m.csv.backup; move it aside before replacing again` is independent of this bug. Your console already reported 8,190 minute bars loaded for each ticker, so DO NOT rerun publish-core just to fix the UI. Preserve the existing `.backup` file; only rename it if you later need to publish an updated CSV.

## Git

Include the two files in the same v0.7.2 branch and its PR (no separate release version required). If a PR exists, pushing updates refreshes it; squash merging can keep one commit in main.
