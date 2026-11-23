# QuantDesk v0.8.3 — Reproducible Research Foundation

**Research only. No Alpaca orders, no broker connections, no validated profitability.** This adds an *offline audit → causal daily signal → cost-aware cash ledger → reproducible report* path. All older research and UI are preserved, including KDE, v0.8.2 factors, watchlists, and portrait mode.

## What is implemented

- **Actual XNYS exchange calendar** via `exchange-calendars` (including exchange holidays, not just weekdays). Audits unique ordered sessions, missing dates, invalid OHLCV, source names, file hashes and declared price basis. Unknown/adjusted price basis or unverified source blocks hypothetical raw-price fills.
- **Frozen, end-of-day signal policy.** Reuses the original KDE/ATR primitives and cooldown without requiring future exit data. For SPY/QQQ, evaluates two predeclared LONG-ONLY variants: (1) KDE candidates by themselves, (2) KDE candidates only when the v0.8.2 cross-asset factor confirms the direction. Missing/contradictory peers produce explicit `NO_TRADE`, not synthetic neutral data. Shorts aren't included (small cash accounts may be ineligible for shorting).
- **Portfolio simulation.** One cash-backed ledger for SPY/QQQ with a maximum of two positions and 10% of initial cash per new position. Next-session-open hypothetical entries, original t+3-close exits, fractional-share assumption configurable, adverse full-spread/slippage/commission assumptions per side, no leverage, and deterministic decision/skip/trade/equity records.
- **Retrospective comparisons.** Recomputes identical capital and cost assumptions for KDE-long-only and KDE-plus-confirmed. Partitions existing history by chronological sessions, purges boundary-crossing executions, and reports drawdown and exploratory month-block-bootstrap trade-return intervals only when powered. All old partitions are ALREADY EXAMINED and are NOT untouched out-of-sample validation.
- **Reproducible artifact.** Every study produces `report.json`, `decisions.json`, per-strategy ledger CSVs, summary JSON and a self-contained HTML report. Dataset SHA256 hashes, strategy policy settings and source-code hashes produce a repeatable `run_id`. Reruns refuse to overwrite earlier output folders.
- **Paper-trader handoff format.** Schema `quantdesk.decision.v1` includes stable decision ID, versioned policy ID, as-of completed session, next eligible session, BUY_CANDIDATE/NO_TRADE, reason, evidence hash and `no_orders=true`. v0.9 will build broker-specific pre-trade checks and execution around this interface, not share the research executor as a live trading engine.

## Installation

After you merge the feature PR (YOU choose when to merge):

```powershell
 git switch main
 git pull --ff-only origin main
 .\.venv\Scripts\python.exe -m pip install -r requirements.txt
 .\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
```

First run a deliberately synthetic smoke test. **Synthetic prices are not evidence of profitability**:

```powershell
 .\.venv\Scripts\python.exe -m market_structure_lab.research_pipeline_v083 demo --out outputs/v083_synthetic_demo
 .\.venv\Scripts\python.exe -m market_structure_lab.research_pipeline_v083 study --manifest outputs/v083_synthetic_demo/manifest.json --out outputs/v083_synthetic_study
```

Open `outputs/v083_synthetic_study/report.html`. No market access or credentials are needed.

## Auditing YOUR real data, without pretending it's raw

Run this command to create a **local, ignored** manifest from `data/SPY.csv`, `data/QQQ.csv`, and `data/context/{NVDA,SMH,XLK,IWM}.csv`:

```powershell
 .\.venv\Scripts\python.exe -m market_structure_lab.research_pipeline_v083 init-manifest --data-dir data --out research_manifest_v083.local.json
```

**Review the file manually.** All `source` values are initially `UNVERIFIED_REVIEW_ME` and all `price_basis` values are `unknown`. Determine the real provider, feed and price adjustment basis from ORIGINAL source records before changing either. Do **not** simply change `unknown` to `raw` to pass a test; SPY/QQQ CSVs may be adjusted and context files may come from a different feed. The manifest is local-only; it contains file paths and source declarations but should never contain API credentials. It is explicitly Git-ignored.

```powershell
 .\.venv\Scripts\python.exe -m market_structure_lab.research_pipeline_v083 audit --manifest research_manifest_v083.local.json --out outputs/v083_data_audit
```

Audit failure is **expected** until data is verified, long enough and synchronized. Check `outputs/v083_data_audit/audit.json` for missing exchange sessions, insufficient history and unknown price bases. The audit requires 250 complete sessions by default; longer samples (ideally two or more years) provide more meaningful retrospective evidence. The study requires identical dates across all six assets for the entire evaluated window, without forward fills. If a manifest is unsafe or has missing data, the study exits without producing profitability summaries.

After the audit passes on real compatible raw daily data:

```powershell
 .\.venv\Scripts\python.exe -m market_structure_lab.research_pipeline_v083 study --manifest research_manifest_v083.local.json --out outputs/v083_real_run_001 --cash 100
```

Every output path must be new; run numbers are intentionally not overwritten. This is still *retrospective*. The next prospective cohort must be locked, dated, and collected independently.

## Very important omissions

- No real consolidated spread or NBBO replay, auction/open execution model, broker rejections, latency simulation, queue position, partial fills, opening gaps beyond the next-day OHLC convention, options quotes, margin or short-sale borrowing. The modeled spread/slippage are **assumptions**, not sampled quotes.
- No corporate-action event stream or automatic raw/adjusted reconciliation. The audit checks declaration and coverage, but cannot verify that a human declaration is true. A passing audit is not proof the feed is trustworthy.
- No hyperparameter optimization or genuine forward holdout. All prior 2026 research samples have been inspected. The CI isn't a claim of statistical significance.
- No support for trading the 66-symbol screenshot watchlist; research signals remain restricted to SPY/QQQ with NVDA/SMH/XLK/IWM as context. No live-streaming path changes.
- No background service, persisted broker order state, live order routing or real-money key access in this release. That belongs to v0.9.

## v0.9 handoff and secondary PC

Before moving paper execution to a secondary Windows PC, first eliminate its spontaneous reboots. Stress-test RAM, GPU, PSU and idle transitions; inspect Windows Event Viewer and hardware logs; then verify sustained reliability under the actual data-feed/server workload. Use a dedicated non-admin account, Windows Task Scheduler/service with **restart-on-failure**, start-on-boot, system time sync, monitor alerts, and local backups. An interrupted order submission must NEVER be repeated blindly on restart: v0.9 needs a durable state machine, idempotency keys, broker reconciliation, an emergency stop and limits before trading. Do not expose localhost port 8765 publicly.

**Exit condition:** The engineering interface is ready when the audit passes on locally reviewed real data, the same frozen decisions replay exactly, and new prospective evidence can be collected independently. That is *not* the same as a demonstrated trading edge.
