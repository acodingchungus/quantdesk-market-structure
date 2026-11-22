# QuantDesk v0.6.3 — Historical SIP Archive (local, read-only)

**Purpose:** build a durable, session-sharded stock-market research dataset before claiming any statistical edge. This update extends v0.6.2; it does **not** replace its graphite UI, replay shortcuts, KDE mathematics, or journal.

## What was implemented

- `market_structure_lab.sip_archive`: explicit, read-only historical Alpaca REST importer for **SPY and QQQ**.
- Two independent datasets: **1-minute consolidated SIP bars (raw, bar-start timestamps)** and **executed SIP trade prints**; no order-book depth.
- Each session is saved separately to compressed `*.csv.gz` files, plus a checksum-verified `.meta.json` describing provider, session, feed, adjustment, original vs stored timestamps, page count and row count.
- Multi-page trade downloads; repeated pagination tokens, malformed prices, duplicate minute bars and non-chronological records cause hard failures. Temporary files are never treated as complete archives.
- **Completed-session resume**: rerun the same download range to skip existing *verified* days. An interrupted day restarts from its first page rather than continuing an incomplete data stream.
- API throttling (0.40-second minimum spacing by default, ~150 requests/min maximum under ideal conditions) and retry/backoff for 429 and transient 5xx errors. Alpaca's free-plan limit is normally 200 historical requests/min; review your actual plan.
- Local `audit` command for archived checksums, session counts, missing records, raw minute-vs-daily close differences, and *descriptive* trade-volume-vs-OHLCV comparisons.
- Optional `publish-minutes` step creates the flat CSV expected by the existing Replay UI; existing flat files are never silently overwritten.
- Existing v0.5 volume profile now loads archived SIP trades for the **selected session only**, rather than requiring one enormous all-history `SPY_trades.csv`. The in-memory cache is limited to one archived day. Raw trade conditions and corrections remain **unaudited**.

## Before starting

1. Stop QuantDesk (`Ctrl+C`). Run commands in the **existing** repository root.
2. Your `data/SPY.csv` and `data/QQQ.csv` must contain the completed daily dates you plan to replay. Daily KDE price levels use these CSVs; downloading more minute bars does not create missing daily zones.
3. Have your **paper trading Alpaca API key and secret** in this PowerShell session:

   ```powershell
   [bool]$env:APCA_API_KEY_ID
   [bool]$env:APCA_API_SECRET_KEY
   ```

   Both should say `True`. Do **not** print, paste, commit, or screenshot actual keys. `True` alone does not prove the credentials are valid.
4. Check disk capacity: historical SIP trade ticks can be large. Start with **one full session**, then a week, then a month. The API downloader never sends orders.

## 1. Test your proposed range without downloading

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.sip_archive download --symbols SPY QQQ --start 2026-09-01 --end 2026-09-30 --feed sip --dry-run
```

The calendar is **weekday-based**, not an exchange holiday calendar. A zero-data weekday is reported separately and is **not automatically labeled a holiday**. The CLI allows at most 93 calendar days per run. Run multiple quarters separately if needed.

## 2. Download one session first

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.sip_archive download --symbols SPY QQQ --start 2026-09-30 --end 2026-09-30 --feed sip --kind both
```

The historical endpoint is `https://data.alpaca.markets/v2/stocks/{symbol}/bars` or `/trades`; both requests are HTTP GET. `--feed sip` is consolidated equity data **not** consolidated Level II depth. Free historical SIP access may be subject to the recent-data restriction and your plan's permissions. On errors, the command stops instead of using fabricated samples.

Output structure (all ignored by Git):

```
data/
  archive/
    sip/
      bars/SPY/2026-09-30.csv.gz
      bars/SPY/2026-09-30.csv.gz.meta.json
      trades/SPY/2026-09-30.csv.gz
      trades/SPY/2026-09-30.csv.gz.meta.json
      bars/QQQ/...  trades/QQQ/...
```

IEX and SIP archives, if both used, go to **separate folders**. QuantDesk auto-loads only SIP trade archives; it will not quietly substitute partial-market IEX data.

## 3. Expand the verified history

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.sip_archive download --symbols SPY QQQ --start 2026-09-01 --end 2026-09-30 --feed sip --kind both
```

It will skip previously completed, checksum-verified archives. Repeated running is safe. Individual high-volume days can take many paginated requests; you may need to narrow ranges, retry after API limits, or check the `--max-pages-per-day` cap (300 by default). Neither network access nor account entitlements were tested from the developer environment.

## 4. Audit **before** interpreting profiles

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.sip_archive audit --symbols SPY QQQ --start 2026-09-01 --end 2026-09-30 --feed sip
```

The JSON report goes under `data/reports/`. Inspect fields like:

- `bars_state`, `trades_state`: present/missing/corrupt.
- `bar_missing_vs_390_reference`: against a **full** regular session; early closes still require a verified exchange calendar.
- `raw_intraday_vs_daily_close_pct`: a material difference can indicate **adjusted daily vs raw minute** mismatch or a close-convention difference.
- `raw_trade_shares_to_bar_volume_ratio`: **not** an exactness or quality score! Raw printed trade conditions, corrections, late reports, auction conventions, and OHLCV eligibility may differ.
- `trade_conditions_audited`: **false**. Do not confuse this experimental volume profile with exchange-certified or Level II liquidity.

The audit can identify *some* problems; it is not proof of complete, accurate SIP trade conditions or quote execution quality. Keep downloaded files private; data redistribution may violate vendor/exchange terms.

## 5. Publish minute bars for the existing Replay UI

The existing Replay frontend reads `data/intraday/SPY_1m.csv` and `data/intraday/QQQ_1m.csv`. To rebuild that view from your verified archived bars:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.sip_archive publish-minutes --symbols SPY QQQ --start 2026-09-01 --end 2026-09-30 --feed sip --replace-active
```

- `--replace-active` is explicit because earlier real imported minute files may exist.
- Before replacement, the previous flat CSV is kept at `SPY_1m.csv.backup` (or `QQQ_1m.csv.backup`) inside ignored `data/`.
- If a backup already exists, the command refuses replacement until you manually rename or move that backup. **It does not delete backups.**
- It refuses to publish sessions absent from `data/SPY.csv` or `data/QQQ.csv`; otherwise daily KDE zone maps would be unavailable.
- It does not modify historical daily CSVs, journals, downloaded archives, or your market-analysis calculations.

Restart QuantDesk:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data
```

Select **Historical Replay → 5m → date**. Price/volume bars come from verified archived 1-minute data, while the volume profile is read **on demand** from the matching SIP trade shard. A session with no verified trades correctly shows `NOT AVAILABLE`, not an invented profile. The profile remains experimental until proper trade eligibility/correction rules are applied.

## Limits and next work

- Per-day trade archive is compressed CSV, intentionally *not yet* Parquet/DuckDB. This format is inspectable, streaming-friendly and requires no new dependencies; columnar storage becomes useful once we know the verified dataset and memory profile.
- `load_trades()` still caps a single on-screen session at 2,000,000 prints. Very large archived days remain on disk but are **not** currently profile-renderable; this is a memory safety limit, not a request-truncation policy.
- The downloader stores raw trade-condition codes and exchange IDs, without applying an official SIP volume-eligibility/correction policy. `POC`, `VAH`, and `VAL` are **experimental observed volume** statistics.
- Provider trades may include corrected, canceled or late-reported observations and may not match minute-bar volume exactly.
- Session calendars, daylight saving time, corporate actions, total-return adjustments, tape filters and missing data still need a separately validated audit before research conclusions.
- **No live execution, no option backtest, no promised alpha.** Point-in-time research and reliable historical collection come first.

Official reference: [Alpaca historical stock trades](https://docs.alpaca.markets/us/reference/stocktradesingle-1) · [Alpaca historical stock bars](https://docs.alpaca.markets/us/reference/stockbarsingle-1) · [Alpaca market data documentation](https://docs.alpaca.markets/us/docs/about-market-data-api).
