# Data and reproducibility

This repo ships source and a **synthetic data generator**, not historical market-data CSVs. The synthetic output exists only to demonstrate the application; it cannot establish signal accuracy or trading profitability.

For real research, place ascending daily `date,open,high,low,close,volume` records in `data/SPY.csv` and `data/QQQ.csv`. Preserve dataset/source provenance, adjustment policy, timezone assumptions, and date coverage privately. Do not distribute provider-restricted exports or credentials without permission.

The earlier experimental holdout beginning 2025-12-04 has already been inspected. Do not present future tuning against that window as an untouched holdout. Use nested chronological evaluations or new prospective data. The tool's daily candles cannot recover order-book depth, intraday path, volume profile, 0DTE Greeks or options fills.
