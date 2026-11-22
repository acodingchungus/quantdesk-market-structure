# QuantDesk v0.4 — Intraday Research Foundation

**Research-only · 127.0.0.1 loopback · no broker or orders · no claim of trading alpha**

This release adds **strict timezone-aware minute OHLCV import**, selectable **1m / 5m / 15m / 1H / 1D** chart timeframes, intraday bar-by-bar replay, and a descriptive first-touch research export. It builds on the v0.3.1 Midnight Navy workstation. The original daily KDE algorithm, daily replay API and SQLite note journal are preserved.

## Install in your existing GitHub repo (recommended)

1. Stop the running v0.3.1 server (`Ctrl+C`). In PowerShell, go to your repository folder.
2. Check `git status` and save or commit any uncommitted work first. Optionally create a feature branch: `git switch -c feature/v0.4-intraday`.
3. Extract the **v0.4 Upgrade Patch ZIP** into that repository's root. Merge folders; **the patch does not include or replace your `README.md`, `LICENSE`, `.git`, daily CSVs or SQLite notes.**
4. Update the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
```

### Try the completely synthetic intraday demo first

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.demo --output-dir data_demo
.\.venv\Scripts\python.exe -m market_structure_lab.intraday_demo --data-dir data_demo --days 10
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data_demo
```

Or double-click `start_demo.bat` after installing dependencies. Open **http://127.0.0.1:8765/**.

**Everything in `data_demo` is generated synthetic OHLCV. It is only for testing UI/software, not validating market strategies.** The chart labels this mode SYNTHETIC DEMO.

### Use existing real daily data

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data
```

This remains **1D-only** until real minute files are provided. The app **does not invent intraday candles** from daily bars.

## Import real 1-minute bars

Put the files below in your already-ignored, local-only data folder:

```text
data/
  SPY.csv                 # existing daily OHLCV, from v0.3.1
  QQQ.csv
  intraday/
    SPY_1m.csv            # optional; never commit vendor data without rights
    QQQ_1m.csv
```

Schema (in this exact column order or any order with the same headings):

```csv
timestamp,open,high,low,close,volume
2026-09-30T09:31:00-04:00,668.1,668.4,668.0,668.2,45000
2026-09-30T09:32:00-04:00,668.2,668.5,668.1,668.3,32000
```

These two rows are **format examples, not verified historical quotes**. Do not add them to real datasets.

**Timestamp convention**: Each timestamp represents the **end** of the 1-minute candle, not its start. RTH 9:30–16:00 ET means the first minute ends **09:31** and the last ends **16:00**. Every timestamp **must contain a timezone offset** (`-04:00`, `-05:00`) or `Z`. The importer converts to America/New_York to validate regular-session boundaries, including DST. Input must be chronologically increasing, with unique timestamps, valid OHLC and nonnegative volume. No extra-hours or weekend rows. It rejects bad inputs rather than silently repairing them.

One-minute data must cover session dates that are also present in the corresponding daily file **and eligible for its historical replay**. Update daily data first if you supply newer minute sessions. Before importing real vendor data, confirm its timestamp convention, adjustment scheme, data license and whether your daily CSV uses adjusted prices (price adjustments MUST be consistent across the two datasets).

A missing minute is **not** filled. A less-than-390-bar day (including a legitimate early close) is marked `partial_session` because v0.4 does not implement an exchange holiday/early-close calendar. Aggregated buckets that have missing minutes show `complete: false`. There is a **1,000,000 minute-row maximum per file**, and the server caches the imported data in memory; start with a few days/weeks, not a multi-year tick archive.

Restart the server after changing CSVs. There is no background refresh or live streaming.

## How to replay intraday

1. Choose **SPY** or **QQQ**.
2. Use the **Timeframe** selector; only timeframes with imported minute data are enabled.
3. Pick a trading date on the main session slider. Intraday sessions start replay at their **first completed bar**.
4. Step bars with **◀ / ▶** or the separate green bar slider. **Play** advances through completed bars. **Last bar** jumps to the final available bar of that session.
5. Daily zones are frozen from the **prior completed daily session**; price reactions are labeled only after the relevant intraday bar closes.
6. Save hypotheses in the **existing local SQLite journal** (notes remain scoped to symbol + session date).

The server returns only the selected bar and the prior visible bars (up to 40/80/160); **later candles and markers are omitted from the response**, not merely hidden by CSS. Daily mode continues to work as before.

## Descriptive first-touch research export

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.intraday_study --data-dir data --out outputs/v04_intraday_study
```

Outputs (if 1-minute data exists):

- `intraday_touch_events.csv`: first zone approach per session/zone, as-of daily level, 5/15/30/60-minute subsequent directional underlying moves, maximum favorable/adverse **price excursions**. Missing full future horizons are blank, not backfilled.
- `descriptive_summary.csv`: event counts and averages/medians by ticker and horizon.
- `manifest.json`: limitations.

**This uses FUTURE data solely to measure realized outcomes in a research export—not to create contemporaneous trade signals or level maps.** There is no transaction-cost model, entry fill, options chain, predictive holdout, statistical significance test, or matched control in this first descriptive intraday study. Events and horizons overlap; do not interpret the CSV as realized strategy P&L or profitability.

## Files added/changed

- `market_structure_lab/intraday.py` — strict loader, session-anchored aggregation, causal markers, event-study functions
- `market_structure_lab/intraday_demo.py` — self-labeled synthetic 1-minute generator
- `market_structure_lab/intraday_study.py` — offline descriptive CSV export
- `market_structure_lab/workstation.py` — optional intraday datasets and per-bar API; legacy daily API unchanged
- `market_structure_lab/assets/workstation.html` — timeframe selector + intraday bar slider in original dark theme
- `tests_market_structure/test_v04_intraday.py` — importer, DST, gaps, API, and causality tests
- `requirements.txt`, `start_demo.bat` — timezone data and demo launch

## What v0.4 does NOT do

No volume profile or true volume-at-price, depth-of-market, order-flow imbalance, 0DTE options pricing, live feeds, broker access, automatic orders, statistically established alpha or realized/options P&L. Those require suitable new datasets and much stricter validation. The previous historical holdout has already been examined, so this release **does not** call it a new untouched holdout.

## Safe commit workflow

```powershell
git status
# After you have inspected the files and tests pass:
git add market_structure_lab tests_market_structure requirements.txt start_demo.bat README_V04.md docs/releases/v0.4.md docs/preview-v04-intraday.png
git commit -m "feat: add causal intraday replay and minute-bar research (v0.4)"
git push -u origin feature/v0.4-intraday
```

If you stayed on `main`, replace the last command with `git push origin main`. On a feature branch, open a pull request into `main` on GitHub after tests succeed. `.gitignore` already excludes `.env`, `data`, `data_demo`, `outputs`, and SQLite notes. Never commit licensed market-data files or API credentials.
