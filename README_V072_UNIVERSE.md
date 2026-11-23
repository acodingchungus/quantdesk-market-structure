# QuantDesk v0.7.2 — Historical multi-asset backfill and coverage

This upgrade extends **historical, read-only data tooling** on top of v0.7.1. It does **not** turn a sector ETF into a new automated strategy, introduce broker order APIs, or activate live SIP streaming. It reuses v0.7.1's Windows Credential Manager resolver: **your saved paper API key is retrieved locally when you explicitly execute a download**, and is never inserted into project files, ZIPs, console logs, or Git.

## What changes

- One **curated, allowlisted universe**, with groups `core`, `benchmarks`, `sectors`, `mag7`, `semis`, and `energy`. Groups can overlap; requested symbols are de-duplicated.
- The v0.6.3 read-only SIP/IEX **archive accepts those additional symbols** for historical minute bars and (when requested separately) historical prints. It still writes provider/price-basis metadata and hashes under Git-ignored `data/archive`.
- `universe_backfill` provides **plan → download-minutes → coverage → publish-core** and optional `download-context` for daily market-intelligence inputs.
- Verified, previously archived session-symbol pairs are **skipped** on repeat runs. Interrupted downloads can resume at the next missing day. Corrupt archives fail closed; they are never silently overwritten.
- The data coverage report marks verified archives, absent weekdays, suspicious row counts, corrupt files, and whether daily context is available. The report is a **local inventory, not a complete-market-data certification**.
- Daily context for the new symbols is visible in existing **Research Lab → Assets and relative strength**. Those values are based on completed historical daily data and are not fed into the v0.7 strategy engine.
- **SPY and QQQ remain the ONLY replay and strategy-experiment symbols.** All others are archives/context only until later versions implement independent point-in-time replay, calibrated features, and realistic cross-asset studies.

## First: verify without making API requests

From your QuantDesk repository, with v0.7.2 installed:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill plan --groups core --start 2026-09-01 --end 2026-09-30 --feed sip
```

You can add groups: `--groups core benchmarks semis`, or use `--symbols NVDA AMD`. Only approved symbols are accepted; use `--groups mag7` to limit the group rather than automatically including `core`.

## Backfill multiple SPY/QQQ intraday sessions (free historical SIP path)

**Do this before extending the universe.** For the September 2026 example:

```powershell
# Explicit read-only network request; fails if no saved credentials
.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill download-minutes --groups core --start 2026-09-01 --end 2026-09-30 --feed sip --execute

# Local checksum inventory, no network
.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill coverage --groups core --start 2026-09-01 --end 2026-09-30 --feed sip

# Publish archived minute data to EXISTING SPY/QQQ replay (not other symbols)
.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill publish-core --groups core --start 2026-09-01 --end 2026-09-30 --feed sip --min-sessions 15 --replace-active
```

`--replace-active` **backs up** any existing `data/intraday/SPY_1m.csv` and `QQQ_1m.csv` before writing. If a `.backup` already exists, publication refuses instead of overwriting it. Safely move that backup to an archival location you control before a second replacement; never delete data blindly. After publication, **restart QuantDesk** to display the newly imported sessions in 1m/5m/15m/1h replay. This uses local 1-minute bars, not fabricated candles.

On Basic Alpaca accounts, historical SIP data older than the last ~15 minutes can generally be requested without the real-time SIP subscription; availability remains subject to plan and entitlement changes. No request is made for the current day; explicit `--execute` is required. Historical minute-bar archives are typically much lighter than tick-by-tick trade archives.

## Add the rest of the watchlist to Research Lab (daily history)

Start with a **separate** 92-day range, e.g. July 1–September 30, 2026:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill download-context --groups benchmarks sectors mag7 semis energy --start 2026-07-01 --end 2026-09-30 --feed sip --execute
```

This writes new files like `data/context/NVDA.csv` and `data/context/SMH.csv`, which are picked up by the existing market-intelligence dashboard the **next time you restart the server**. If a context file already exists, **it is preserved**, not silently truncated or replaced. To extend it, prepare and validate a replacement separately using the earlier one-symbol importer, preserving backups and maintaining consistent raw/adjusted price bases.

Optional intraday archives for additional symbols:

```powershell
.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill plan --groups mag7 semis --start 2026-09-01 --end 2026-09-30
.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill download-minutes --groups mag7 semis --start 2026-09-01 --end 2026-09-30 --feed sip --execute
```

These **do not appear as selectable Replay tickers yet**. They're stored for future cross-asset tests. Adding daily context and raw intraday samples does not prove price-level confluence.

## Coverage meanings and limitations

- `verified_days`: archived, checksum-verified minute-bar days, **not** complete certified consolidated sessions.
- `absent_weekdays`: no archived bars; might include US stock-market holidays/closures or incomplete downloads. The tool does **not** silently mark all weekdays as expected market-open days.
- `non_390_days`: deviation from a **regular** 390-minute RTH session. Could reflect early closes, incomplete vendor coverage, or data gaps. Requires separate exchange-calendar checks.
- Trade prints (if acquired later) need sale-condition, corrections, out-of-sequence, and auction review before being treated as an audited executable-volume profile.
- Historical SIP bars may be *raw* whereas existing daily CSVs may be adjusted. Resolve split/price-basis and close-convention mismatches before comparing levels across sources.
- Context symbols are **descriptive**: no same-day lookahead, no forward filling, no tested multi-ticker execution signals.
- No records are downloaded automatically on application startup. To maintain a rolling archive later, schedule and audit it explicitly.

## Tests / safety

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
.\.venv\Scripts\python.exe scripts/check_git_sources.py
```

At development packaging: **108 tests passed**, including offline multi-asset archive and context, repeat/resume, checksums, point-in-time context, strict allowlists, no-network plan, and publish restrictions. No real Alpaca download was made in this environment. The GitHub workflow includes source-manifest validation; source files are tested on Python 3.11 and 3.12 after you push.
