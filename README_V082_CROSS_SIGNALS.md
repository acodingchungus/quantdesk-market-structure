# QuantDesk v0.8.2 — Causal Cross-Asset Signal Research

**Research-only; local daily OHLCV; no broker orders, trade recommendations, or proven alpha.** Builds on the merged v0.8.1 portrait UI and v0.7 KDE event study. This release does not change the KDE detector, v0.7 fills/cost proxy, SIP importer, live polling adapters, or historical replay.

## What actually changed

- **New `cross_signals_v082.py`:** daily, point-in-time cross-asset factors using QQQ/SPY targets and NVDA, SMH, XLK, IWM peers. A configurable 20-return window is frozen through session **t−1** before calculating peer residuals on the completed session **t**.
- **No forward fill:** if a peer lacks a required prior session or the signal-date close, that peer is unavailable. No missing/stale peer automatically becomes neutral or bullish.
- **Fixed, exploratory classification:** `confirmed`, `contradicted`, `mixed`, or `unavailable` with predefined thresholds—not tuned to event outcomes.
- **KDE confluence study:** groups the **existing verified v0.7 clustered KDE events** by signal-date factor state. Uses v0.7 next-session-open entry, exit, partition and cost proxy. Reports KDE baseline vs peer-confirmed/contradicted/mixed/unavailable outcomes separately for development, validation and *retrospective* test.
- **New read-only endpoints:** `/api/cross-signal` and `/api/cross-study`; no orders or writable research inputs.
- **Collapsible UI:** new **Cross-asset KDE confluence research** section in Cross-Market, keeping the v0.8.1 three-column portrait watchlist intact.

## The math and timeline

At a completed **session t**, write the target and peer log returns:

`r_target,t = ln(C_target,t / C_target,t−1)`, `r_peer,t = ln(C_peer,t / C_peer,t−1)`.

For each peer, fit *only* the `W=20` return pairs ending at **t−1**:

`β = Cov(r_target, r_peer) / Var(r_target)`, `α = mean(r_peer) − β×mean(r_target)`.

At **t close**, compute the peer excess return in percentage points:

`residual_peer,t = 100 × (r_peer,t − α − β×r_target,t)`.

For a KDE event with known direction `d ∈ {−1,+1}`, define:

`signed_residual_peer,t = d × residual_peer,t`.

The model requires **at least two** independently available peers. It then calculates mean signed residual and the fraction of peers with a strictly positive signed residual. Using **predeclared** rules (not optimized):

- `confirmed`: mean signed residual ≥ **+0.10 pp** and positive peer fraction ≥ **60%**.
- `contradicted`: mean signed residual ≤ **−0.10 pp** and positive peer fraction ≤ **40%**.
- `mixed`: enough peers, neither rule holds.
- `unavailable`: insufficient synchronized history/variation/peers.

The prior-window correlation is computed across the same historical 20 paired returns. The separate, descriptive **lead/lag** measure is Corr(peer return at `k−1`, target return at `k`) for pairs within that same window ending at t−1. It does not imply causality or prove forecasting ability.

**Point-in-time guarantee:** β, α and historical correlations for t do not use t or later. The t residual only uses completed t closes. The KDE event's entry occurs at **t+1 open**, not the signal day. Underlying event outcomes are computed separately and attached only for explicitly retrospective evaluation.

## API examples (server running locally)

```powershell
Invoke-RestMethod 'http://127.0.0.1:8765/api/cross-signal?target=QQQ&asof=2026-09-30&direction=1'
Invoke-RestMethod 'http://127.0.0.1:8765/api/cross-study?target=QQQ&cost_bps=5'
```

If additional local daily context is missing for NVDA, SMH, XLK or IWM, the corresponding peers will be marked unavailable. Having data for **only** September 2026 does not turn older signals into a validated study; it produces coverage gaps and small, biased subsets. No live Alpaca snapshot or IEX feed is used by these routes.

To enable independent read-only snapshots (separate from research):

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data --enable-watchlist-poll --live-feed iex --watchlist-interval 30
```

Windows Credential Manager should retain the saved credentials; don't paste them into chat or source control. Polling depends on account entitlement, current session, and data freshness. IEX isn't consolidated SIP.

## Interpreting the results

The v0.7 study validates the event chronology and labels splits **development**, **validation** and **retrospective_test**. This project has *already examined all three*—the final sample is **not untouched**. The confluence study does **not** optimize or fit a classifier and it does **not** report p-values or assert significant performance. A `confirmed_minus_baseline_pp` difference is a descriptive *difference in mean historical underlying ETF return proxies*, not an executable trade opportunity. Groups can be tiny or contain no events. Changing cost assumptions changes net proxies only, not the observation at signal close.

For a credible edge we still need longer fully synchronized data, adjusted/raw price audits, preregistered hypotheses, genuinely new chronological samples, realistic bid/ask and execution simulation, and statistical uncertainty handling multiple comparisons.

## Test and release workflow

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
.\.venv\Scripts\python.exe scripts/check_git_sources.py
```

Expected **147 tests** on v0.8.2. CI tests Python 3.11 and 3.12. New source tests cover immutable historical factors under future mutations, prior-only coefficient fitting, exact missing-day handling, malformed dates, v0.7 event partitioning and no-order API routes.

See `INSTALL_V082_ONE_COMMIT.md` and `PR_V082.md` for the PR workflow. **Merge into `main` only after manual review.**
