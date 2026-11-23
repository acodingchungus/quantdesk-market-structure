# QuantDesk v0.7.3 — Exact-Math Replay Performance

**Research-only, localhost-only. No broker order endpoints or changes to historical signal formulas.**

This drop-in patch is for **v0.7.2 after the Empty Session + Dashboard Startup hotfixes**. It does not include or change private market data, the Windows credential vault, or SQLite journals.

## What changed

| Layer | Old | v0.7.3 |
|---|---|---|
| Intraday reaction markers | Scan every bar from the session start for every seek | Evaluate each imported session/timeframe once, index the marker positions, and slice only markers observed by the selected bar |
| Historical candles | Rebuild row dictionaries every request | Keep a **12-session LRU** of serialized historical candle rows |
| Trade volume profile | Re-apply Decimal price-to-bin conversion to all eligible prints on every request | Per-session **exact Decimal floor bin index** computed once per selected price bin, then reuse the same POC, VWAP, VAH, VAL, HVN/LVN and value-area mathematics |
| Profile responses | Re-evaluate previously visited cutoffs | Keep **16 most-recent exact responses** (keyed to date, symbol, source hash, cutoff and bin size) |
| Server responsiveness | Expensive tick processing holds the main store lock | A separate profile lock prevents long-running trade archive requests from blocking chart frames |
| Browser requests | Old frame/profile fetches can remain active; every playback bar requests a profile | Abort superseded frame fetches, debounce expensive profiles until **240 ms of settled navigation**, and skip profiles during playback |
| Canvas | Reallocate backing bitmap on every mouse hover | Reallocate only when dimensions change; use `requestAnimationFrame` for hover redraw |

**Critical:** Nothing is interpolated or forecast. KDE level construction, original `build_profile` arithmetic, all price-bin sizes, marker rules, as-of cutoffs, and transaction-cost study math are unchanged. The price-bin index is a cached *exact representation* of the original formula, not an approximation. A prior-day KDE map cannot see same-day or later prices. All cached frame markers are filtered through the selected bar before leaving the server.

## Validation

- 120/120 automated tests passed in the development environment.
- 192 before/after frame JSON objects were compared **for exact equality** (SPY and QQQ; daily/1m/5m/15m/1h; multiple sessions, windows, bar indices).
- Unit tests compare indexed profiles with the original `build_profile` across multiple price-bin sizes and historical cutoff times, including duplicate timestamps and mutated future prints.
- Browser UI smoke: 35 timeframe switches and interleaved seeking/tab switches with no JavaScript errors in a simulated local API bridge.
- Verified `node --check` on the inline JavaScript.

### Local synthetic microbenchmark — not a speed guarantee

An 80,000-trade, 8-seek synthetic test measured ~267 ms using repeated original calculations and ~75 ms using the new indexed version **including index initialization** (~3.5× total speedup). A 390-bar, 60-seek marker test measured 93.9 ms repeatedly vs 1.9 ms once. Real-world performance depends on disk speed, symbol, volume of SIP prints, rendering resolution, number of levels, and background load. The first archived trade-profile request must still decompress and validate its input.

Reproduce locally without credentials:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_replay_v073 --trades 80000 --seeks 8
```

Run regression tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
```

## Known limitations

- v0.7.3 improves **replay responsiveness and repeated queries**, not the initial KPI/KDE preprocessing cost at server startup; large CSV parsing still takes time.
- At 10× speed the effective rate remains constrained by request/paint time. Profiles intentionally update **after** playback stops; they are never inferred from candles or displayed as an earlier timestamp's future ticks.
- Cache bounds are intentionally modest; a cold request can still take longer than a repeat request.
- Headless browser smoke used a simulated local API bridge because this sandbox cannot navigate its loopback server. Verify with real data and your Windows browser before merging.
- There is no live price-data entitlement upgrade and no proof of profitability.
