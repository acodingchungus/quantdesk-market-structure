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
