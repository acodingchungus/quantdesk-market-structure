# QuantDesk Market Structure Lab v0.2 — Causal Historical Replay

**Research-only. No trading orders, broker integration, order-book levels, options pricing, or proven edge.** This is the v0.1 project plus new modules; the original v0.1 engine, results, and tests are preserved.

## Windows PowerShell setup

From the extracted `QuantDesk_Market_Structure_v0_2` directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
.\.venv\Scripts\python.exe -m market_structure_lab.v02 --data-dir data --out outputs/v02_real_sip
```

Then open each replay by double-clicking or entering:

```powershell
ii .\outputs\v02_real_sip\QQQ_replay.html
ii .\outputs\v02_real_sip\SPY_replay.html
```

The package includes the 690-row SPY/QQQ CSV copies you previously supplied (2024-01-02 through 2026-10-01). Their SHA-256 checksums are logged in the output manifest. It does not connect to Alpaca or your existing QuantDesk v0.6.1 repository. For an alternative dataset, replace `data/SYMBOL.csv` with properly ordered historical daily `date,open,high,low,close,volume`, then rerun.

## What is new in v0.2

1. **Offline interactive candle replay** (`SPY_replay.html`, `QQQ_replay.html`): play/pause, session-by-session date scrub, 40/80/160-day windows, volume bars, known zones, and zone interaction markers. No external JS libraries or web connection. On replay day *t*, zones are from **completed days before t**, while the candle for t appears only because the session is considered complete.
2. **Historical snapshot** (`SYMBOL_snapshot.png`): OHLC candlesticks with level radii and prices for a chosen historical date. Run `--snapshot-date 2026-08-03` (if a market session) to request a different date.
3. **Reaction classification** (`reactions.csv`, `reaction_counts.csv`): a test/rejection, breakout or close inside a zone is labeled after that day's close. A failed breakout is only marked after a later closing reversal across the **frozen original zone** within 3 trading sessions, never retroactively on the breakout day. The same event can touch several neighboring zones; these counts are not independent bets.
4. **Chronological zone tracking:** the first-seen label tracks the earliest frame of a continuously matchable zone since the 180-session warmup. IDs are assigned without future observations. These IDs are heuristic—price-level identity can jump or split.
5. **Exploratory event-matching** (`matched_events.csv`, `matched_summary.csv`): for each eligible v0.1 signal, compare its ETF directional next-open-to-third-close return proxy with a mean across up to five **earlier non-event days** with similar pre-signal ATR/close and prior 10-session return. Only controls within 126 prior sessions and the same training/holdout segment qualify. Both target direction and costs are held fixed. Calendar-month-block bootstrap intervals, block sign-flip p-values and Benjamini–Hochberg FDR are included as **descriptive sensitivity analyses**; there is no randomized control or causal identification.
6. **Original v0.1 summary preserved** (`v01_unchanged_summary.csv`, `v01_unchanged_events.csv`). No optimization/tuning based on v0.1 holdout performed here.

## Output files

- `SYMBOL_replay.html` — offline replay with future prices visually hidden at earlier dates
- `SYMBOL_snapshot.png` — candle snapshot for selected date
- `reactions.csv` / `reaction_counts.csv` — daily interaction labels and counts
- `matched_events.csv` / `matched_summary.csv` — matched descriptive comparison and uncertainty
- `point_in_time_levels.csv` — copied v0.1 chronological maps
- `v01_unchanged_events.csv` / `v01_unchanged_summary.csv` — v0.1 baseline replay
- `run_manifest.json` — parameters, input hashes, dataset coverage and caveats

## Scientific limitations / safety

- **The holdout since 2025-12-04 has ALREADY BEEN EXAMINED in v0.1.** Do not claim these v0.2 results are a new untouched test. Use a new prospective period or nested chronological validation for new tuned models.
- Matched controls are based on observed non-event earlier dates, not a randomized experiment. They may differ in market regimes, have overlapping return horizons, be reused across events, and remain correlated. Small samples and block sign-flip assumptions make p-values fragile. A low p-value here would *not* prove profitable alpha.
- A day's OHLCV contains no intraday event sequence. Daily zone contacts and future daily closes cannot establish 0DTE trade entries/fills. No actual volume-at-price profile or current limit orders are reconstructed.
- Historical **adjusted** ETF price series may change when vendors recompute historical adjustments. A historically accurate as-traded level would require archived point-in-time raw prices and adjustment histories.
- A fixed 5 bps round-trip cost is a hypothetical ETF sensitivity, **not** options bid/ask, commissions, slippage or exercise risk.
- `first_seen` refers to tracked levels since replay warmup, not necessarily their true historical discovery date; level continuity is approximate.
- The v0.1 level detector still uses a 70/30 body/wick mixture and KDE parameters as hypotheses, not optimized evidence. Avoid tuning them to these exposed data.
- Remains read-only. No strategy is enabled to trade money.

## Suggested v0.3

Record intraday observations with timestamps and **licensed** trade/quote data, then construct separate volume-at-price distributions. Test whether those features add out-of-time value to the same level rules. If researching 0–3 DTE, obtain genuine historical options chains with quotes, IV and corporate-action handling before claiming any option execution edge.
