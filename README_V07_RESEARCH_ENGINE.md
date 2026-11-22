# QuantDesk v0.7 — Quantitative Research Engine

**This is a read-only, retrospective, DAILY ETF event-study module, not an options-trading strategy or proven edge.** It builds on the v0.6.3 historical SIP archive but does **not yet merge raw SIP prints into the KDE event rules**. Trade-condition eligibility, corporate actions, and raw-versus-adjusted price bases have not been certified.

## What actually ships

- `market_structure_lab/experiment_lab.py`: the strategy-study engine, a CLI, and deterministic research outputs.
- `GET /api/experiments?symbol=SPY&cost_bps=5`: read-only JSON, with dataset SHA256, partition boundaries, per-trade descriptive outcomes, and research warnings.
- Research Lab: a new Midnight Graphite **Strategy research** section. Switch SPY/QQQ and 0/5/10/20 bps hypothetical roundtrip cost. Compare KDE-detected levels against **prior-day high/low** reactions. The market-regime dashboard, the live monitor, the playback engine, and the note journal are preserved.
- A Git preflight to detect missing untracked Python files before publishing (the issue which previously broke Actions).

## Exact causal trade definition (same as v0.1)

1. On day *t*, detect price-zone **candidate levels** using daily sessions completed **before t**. Pivot confirmation requires right-side completed candles, ATR sets zone sizes, and KDE clusters independent pivots.
2. After the complete day *t* has closed, label a possible support/resistance rejection using its range and close. **There is no entry on t.** The earlier signal is not an intraday-available instruction.
3. Entry is the **OPEN of t+1**, exit is the **CLOSE of t+3** under the currently fixed `Config.forward_bars=3`. No stop, order execution, liquidity or leverage is inferred.
4. Signed underlying gross return is `direction × (exit_close − entry_open) / entry_open`, where direction is +1 for long and −1 for short. **Proxy net** subtracts a configurable flat 0/5/10/20 bps roundtrip assumption. This is NOT an options spread, commission or a realistic shorting model.
5. Intraholding **MFE** and **MAE** are computed using the full interval's observed highs/lows. These are post-event descriptive path extrema, not tradable target/stop fills or forward-known features. We do not infer the order of intraday highs and lows.

### Why do we call this a baseline comparison?

The two predefined methods are KDE clustered zones and prior-day high/low extremes. **Their event dates, directions, and counts differ**, so comparing their means does not establish that KDE is superior. The existing classifier, tuned settings, and historical periods have been studied repeatedly. The randomized-direction test keeps selected event windows fixed and flips direction; its one-sided diagnostic p-value concerns directional alignment under that particular null **only**. It does not adjust for the multiple prior research decisions or identify causal level effects.

## Chronological evaluation, without false confidence

The usable daily sessions after the detector's lookback are partitioned **60% development / 20% validation / 20% retrospective test**. All entry and exit sessions must lie entirely inside one partition. Boundary-crossing observations are dropped (reported separately). This prevents crossing-outcome contamination, not every source of leakage or bias.

The **retrospective_test is NOT an untouched test**: we have already inspected SPY/QQQ and earlier holdout slices. For real forward-looking validation we must lock the model once and collect *new* subsequent market sessions with no tuning on those outcomes.

For groups with at least 8 trades and 4 distinct exit months, monthly-block bootstrap confidence intervals approximate uncertainty of the average proxy return (600 reproducible draws). They are descriptive, can be unstable with few months, and are not coverage guarantees. For groups with at least 5 trades, 1000 date/holding-window-preserving random-direction draws provide a simple directional null diagnostic. Missing/underpowered values are shown as **unavailable**, not zero or statistical significance.

## Run it

From the existing project root with v0.7 installed:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
.\.venv\Scripts\python.exe -m market_structure_lab.experiment_lab --data-dir data --out outputs/v07_research --cost-bps 5
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data
```

Open `http://127.0.0.1:8765/` → **Research Lab** → **Strategy research · v0.7**.

The CLI creates `outputs/v07_research/SPY_study.json`, `QQQ_study.json`, and matching per-event CSVs. The `outputs/` folder is already Git-ignored. Results include a source hash, fixed settings, partition dates, and warning list so you can reproduce each run. The browser API computes the same immutable fixed study from supplied daily CSVs; its `cost_bps` sensitivity does not tune entry/exit rules.

Synthetic demo:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.demo --output-dir data_demo
.\.venv\Scripts\python.exe -m market_structure_lab.experiment_lab --data-dir data_demo --out outputs/v07_synthetic_demo
```

**Synthetic results are software tests, not evidence of trading profitability.** Daily SPY/QQQ data may contain split/dividend adjustments. Do not combine raw SIP tick price nodes with adjusted daily KDE levels without reconciliation and provenance checking.

## Not included yet

- No real volume-profile/KDE confluence experiment (requires tick condition/correction validation and price-basis alignment).
- No walk-forward **retraining or parameter selection**; this release uses fixed parameters and retrospective chronological partitions. A true nested walk-forward optimizer is future work, subject to data sufficiency.
- No options quotes, IV, Greeks, OPRA reconstruction, implied stops, actual execution cost model, or live trading.
- No broker integration or order routes.
