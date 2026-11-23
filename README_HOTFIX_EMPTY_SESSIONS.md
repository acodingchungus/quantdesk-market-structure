# QuantDesk v0.7.2 hotfix — empty historical bar responses

## Why this exists

The v0.7.2 `AlpacaArchiveClient.page` requires `bars` to be a list. Some no-data
responses may carry an explicit `"bars": null`, such as a request made for an
exchange holiday. In the September 2026 backfill, the batch got through Friday,
September 4, then encountered the next weekday, Monday, September 7, which was
NYSE Labor Day (closed). The response contents were not captured, so that
holiday connection is a strong hypothesis, not confirmed provider telemetry.

## Behavior of this patch

- Explicit `bars: null` (or `trades: null`) with no next-page token is normalized
  to an empty list and yields the existing `NO_RTH_DATA` result.
- Nothing is archived for an empty date; there is no synthetic bar or trade.
- Absent keys, unexpected types, and null collections carrying a pagination
  token still fail closed as malformed JSON.
- Completed archived days remain checksum verified and are skipped when the
  download command is rerun. No existing archives are replaced.
- This does not add an official exchange calendar. The coverage command still
  counts weekdays as *candidates*, not certified open sessions.

## Install

Stop QuantDesk and make sure your repo is on `feature/v0.7.2-universe-backfill`
(or whatever v0.7.2 branch you are preparing), not `main`. Extract the two
replacement source files into the repository root with folder merge enabled:

```
market_structure_lab/sip_archive.py
tests_market_structure/test_v072_universe.py
```

Then run in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v

.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill download-minutes --groups core --start 2026-09-01 --end 2026-09-30 --feed sip --execute

.\.venv\Scripts\python.exe -m market_structure_lab.universe_backfill coverage --groups core --start 2026-09-01 --end 2026-09-30 --feed sip
```

Expected test count with original v0.7.2 tests and the two new tests: **110**.
A September 7 holiday may report `NO_RTH_DATA`; you should then see later
sessions downloaded. The same command should show `SKIPPED_VERIFIED` for the
successful earlier days. If another error appears, record its first error line
and preceding symbol/date; don't print your key or secret.

## Git integration

If v0.7.2 is not committed yet, stage these two files along with the full
v0.7.2 release files; keep this as one release commit. If already committed,
make one focused corrective commit on the existing v0.7.2 PR branch, then merge
only when CI is green. Avoid staging `data/`, `.env` files, or credentials.
