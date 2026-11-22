# Research roadmap

## Completed (through v0.4)

Daily SPY/QQQ research engine, volatility-normalized KDE levels, point-in-time historical replay, offline replay exports, local Python web server, SQLite notes, automated tests and Midnight Navy dashboard.

## Implemented in v0.4

- Timestamped intraday data ingestion with timezone, session and missing-bar audits.
- Multi-timeframe replay that never reveals future data.
- Close-confirmed first-touch / reaction labels and a descriptive first-touch research export at 5/15/30/60-minute horizons (not a trading backtest).
- Point-in-time replay tests that reject future intraday candles and frozen prior-day zone maps. **Matched controls and new untouched validation are not yet implemented for the intraday study.**

## Later experiments

- Actual trade-level volume-at-price / liquidity visualization; cannot infer resting orders from volume alone.
- Market regime features (VIX, sectors, trend) with correlation controls.
- Historical options quotes, 0–3 DTE IV/Greeks, execution-cost modeling.
- Statistical ML baselines and a local AI research assistant.

No trading execution or unverified profitability claims are part of this repository.

## v0.5 — Implemented locally, pending merge

- Optional executed-tick CSV importer; price-binned share volume; POC/VWAP/value area.
- Profile panel and POC/VA price overlays, updated only with historically observed prints.
- No true order book; no volume-profile inference when tick data is absent.
- Next validation objective: historical conditional reaction rates with suitable licensed market prints.

## v0.6 — Implemented Market Intelligence workspaces

- Live Market / Historical Replay / Research Lab tab separation.
- Optional read-only Alpaca IEX or entitled SIP WebSocket stock observations, always off by default.
- Daily prior-session-only SPY/QQQ momentum and volatility; optional sector-relative-strength inputs stored locally.
- No VIX or true market-depth feed, no real-time chart backfill, no live order functionality.

## Future milestones

- Historical multi-day minute/trade ingestion, feed/adjustment audits, tick corrections and condition eligibility policy.
- Validated sector/VIX data entitlements and full source provenance.
- Statistical matched-controls experiments and prospective out-of-sample validation.
- Historical options quotes/IV/Greeks, spread-aware fill models, and research-only ML.

## v0.6.1 — Graphite Terminal (visual update)

- Applied graphite / high-contrast palette and consistent green, red and yellow chart semantics.
- Sharpened panels, tabs, journal, form controls, histograms and mobile presentation.
- Updated UI theme tests while leaving market calculations and local backend unchanged.
