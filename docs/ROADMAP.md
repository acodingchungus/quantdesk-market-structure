# Research roadmap

## Completed (v0.3.1)

Daily SPY/QQQ research engine, volatility-normalized KDE levels, point-in-time historical replay, offline replay exports, local Python web server, SQLite notes, automated tests and Midnight Navy dashboard.

## Proposed v0.4

- Timestamped intraday data ingestion with timezone, session and missing-bar audits.
- Multi-timeframe replay that never reveals future data.
- First-touch, rejection and breakout analytics over realistic intraday horizons.
- Prespecified evaluation and matched comparisons with leakage tests.

## Later experiments

- Actual trade-level volume-at-price / liquidity visualization; cannot infer resting orders from volume alone.
- Market regime features (VIX, sectors, trend) with correlation controls.
- Historical options quotes, 0–3 DTE IV/Greeks, execution-cost modeling.
- Statistical ML baselines and a local AI research assistant.

No trading execution or unverified profitability claims are part of this repository.
