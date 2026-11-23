# QuantDesk v0.8.0 — Cross-Market Intelligence & Read-Only Watchlists

**Local-first, research-only. No trading endpoints, no execution, no proof of predictive alpha.**

This patch extends the **already-merged v0.7.3** workstation without rewriting its KDE detector, trading study, exact volume-profile calculations, SQLite notes, or replay behavior. The UI adds a **Cross-Market** workspace.

## What works in v0.8.0

1. **TradingView screenshot registry:** all **66 distinct symbols visibly present** across the saved Stocks, Sectors, Energy Stocks, Miscellaneous, and Macro screenshots. Not a live TradingView synchronization. Screenshots of different lists or parts of lists that weren't visible cannot be inferred. See `docs/watchlist_screenshot_catalog.csv` for the auditable, editable transcription (do not confuse watchlist entries with live market entitlements).
2. **Market-data provider classification:** 48 stock/ETF symbols eligible for Alpaca stock snapshot *requests* (subject to listing, entitlement, timing and provider response); three crypto pairs mapped explicitly to Alpaca's `BTC/USD`, `XRP/USD`, `SOL/USD` source, whose venue prices might differ from TradingView. Fifteen others (indices, futures, CFDs, economic symbols, and PDCE) are visible but **unavailable until separately licensed/provider-integrated**, not substituted with unrelated symbols.
3. **Historical cross-asset snapshots:** point-in-time daily comparisons from `data/SPY.csv`, `data/QQQ.csv`, and `data/context/*.csv`, including correlations and relative return. Missing or stale assets do not receive invented prices.
4. **Archived one-minute comparisons:** for symbols with locally verified per-day SIP/IEX minute shards under `data/archive/<feed>/bars/<ticker>/YYYY-MM-DD.csv.gz`, the backend uses **completed minute-END timestamps** and exact pairwise matching, with no fill-forward. It rejects a missing target minute rather than extrapolating it.
5. **Opt-in live snapshot poller:** requests batches of U.S. stock/ETF snapshots from the Alpaca IEX data API and separately requests Alpaca U.S. crypto snapshots. It caches only the latest observations in memory, flags missing/stale data, and never stores snapshots in the historical data/journal. It makes **zero external requests** by default.
6. **Existing WebSocket priority feed** still supports `--enable-live --live-symbols SPY,QQQ,...` with a maximum of 30 approved equity tickers. The wider stock watchlist uses REST snapshot polling instead of attempting to subscribe to more symbols than the basic streaming limit.
7. **New local read-only GET APIs:** `/api/watchlist`, `/api/live/watchlist`, `/api/cross-asset`. Same-origin host restrictions and no `POST /api/orders` remain.

## Installation

See [`INSTALL_V080_ONE_COMMIT.md`](INSTALL_V080_ONE_COMMIT.md). Install on top of **v0.7.3 merged into `main`**, not an earlier release or old feature branch. The patch does not contain your Alpaca keys, any local `.env`, CSVs, `.sqlite`, or generated reports. Keep all these files private.

### Historical mode (no live network)

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data
```

Open `http://127.0.0.1:8765` → **Cross-Market**. The historical panel works without live keys and uses only your local completed data. In **Cross-Market**, select a target and historical date. Daily comparisons use 20 jointly observed log-return pairs when enough valid history exists. Intraday requires exact verified archives and a correct ET UTC offset chosen on the screen; daily and minute sources are not mixed.

Example direct API requests:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8765/api/watchlist'
Invoke-RestMethod 'http://127.0.0.1:8765/api/cross-asset?target=QQQ&asof=2026-09-30&symbols=SPY,QQQ,NVDA,SMH'
Invoke-RestMethod 'http://127.0.0.1:8765/api/cross-asset?target=QQQ&asof=2026-09-30T10:05:00-04:00&timeframe=1m&feed=sip&symbols=SPY,QQQ,NVDA,SMH'
```

`asof` for daily is explicitly a **completed** session date, not what was known at that morning's open. To reconstruct a morning-only decision, use the prior completed daily date or historical minute bars with timestamps at or before the actual decision. Intraday feature availability never uses a later candle.

### Enable read-only live snapshots for the screenshot universe

First confirm the vault without displaying secrets:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.credentials status
```

Then start the stock + crypto **snapshot poller** explicitly:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data --enable-watchlist-poll --live-feed iex --watchlist-interval 30
```

Alternatively, combine it with the existing WebSocket for *priority* stocks:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data --enable-watchlist-poll --enable-live --live-symbols SPY,QQQ,NVDA,SMH --live-feed iex
```

While running, the browser's **Cross-Market → TradingView watchlists** shows every screenshot symbol and its status. The WebSocket is still shown in **Live Market**. Do not run two QuantDesk servers on the same port. Stop with `Ctrl+C` before restarting with different flags. Never paste actual keys into code, scripts, screenshots, Git, or chat.

**Feed interpretation:** Basic IEX data represents one U.S. exchange, not consolidated SIP. A quote may be missing, older than 120 seconds, or absent outside market hours. The API records **exchange timestamp**, freshness and feed, not just receipt time. `--live-feed sip` will only work with the applicable entitlement and fails closed rather than silently falling back. Crypto prices use the Alpaca U.S. crypto endpoint and can differ from TradingView's exchange. Provider capability/availability and plan limits can change.

### Backfill daily and intraday history for expanded equities

First plan the watchlist universe, then request a **small pilot** only after inspecting its size:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill plan --groups watchlist --start 2026-09-01 --end 2026-09-30 --feed sip
.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill download-context --groups watchlist --start 2026-07-01 --end 2026-09-30 --feed sip --execute
.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill download-minutes --symbols NVDA SMH --start 2026-09-28 --end 2026-09-30 --feed sip --execute
.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill coverage --symbols NVDA SMH --start 2026-09-28 --end 2026-09-30 --feed sip
```

The downloader is intentionally **resumable and never overwrites existing context by default**. It doesn't magically provide a long, continuous backtest dataset. Indices/futures/macro are excluded from the Alpaca stock downloader: do not conflate ticker strings across providers. SPY/QQQ remain the only KDE replay and v0.7 strategy-study symbols; broader watchlist archives are available for cross-asset research.

### Known limitations and future v0.8.x

- This is an **as-of historical comparison engine**, not a trained confluence model, validated signal, or an integrated multi-ticker execution system.
- **15 non-stock/non-crypto items** need appropriate adapters/providers or delisting review. GOOG from your screenshots and previously included GOOGL are different share classes; they are NOT silently aliased. An index such as VIX is **not** a stock; ES1! / CL1! continuous futures need contract-roll rules and a licensed futures source; `USOIL` is a vendor-specific CFD; economic indicators have publication/revision lags. The watchlist correctly marks them unavailable instead of fabricating feeds.
- No automated TradingView import, no on-disk real-time archive, no options quotes, no trading integration, no true cross-asset order routing.
- Daily CSVs may be adjusted, while historical minute archives are raw. Resolve adjustment/timezone/vendor discrepancies before treating price-level comparisons as comparable.
- No future data may affect an earlier result. No intraday filling of missing bars. The first archive access may cost more CPU due to checksum verification and decompressing.
- v0.8.1+: add verified futures/indices/macro adapters and historical revision calendars; then walk-forward **incremental predictive value** experiments for KDE vs cross-asset features, accounting for overlapping constituent exposure and realistic costs.

### Tests and CI

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
```

Development: **135/135 passed**, including 15 new tests for timestamp alignment, archival provenance, future mutation invariance, every screenshot symbol, safe snapshot parsing, opt-in defaults, local read-only API routes, and no broker order endpoint. Test locally on Windows and watch GitHub Actions on Python 3.11/3.12 before merging.
