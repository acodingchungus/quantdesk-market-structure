# QuantDesk v0.6.2 — Midnight Graphite + Smooth Replay

A **drop-in UI-only** patch for an existing QuantDesk **v0.6.1** working tree. One replacement step, one commit. No modifications to Python research formulas, read-only Alpaca adapters, data providers, or SQLite databases.

## What's different

- True near-black backgrounds (`#030504`) and neutral graphite panels (`#101310`), not navy.
- A greener active accent (`#22DB58`); red continues to denote negative/error, yellow the POC and caution.
- A redesigned Historical Replay transport with session and intraday timelines, tooltips, filled progress tracks, current-position labels, and larger mobile controls.
- Responsive drag scrubbing: the selected index/label updates immediately; API requests are coalesced to roughly one request per 85 ms while dragging and the final position is requested on release.
- A bounded **22-frame revisit cache** to speed travel to previously viewed frames. It never preloads a future session or bar; the server still returns point-in-time frames.
- Playback speed: **0.5×, 1×, 2×, 4×**, plus first/last buttons and ±5-bar jumps.
- Arrow-key / keyboard shortcuts while on Historical Replay (details below).
- Read-only Live Market, Research Lab, volume profile and the SQLite journal are preserved.

## Installation

**Stop the workstation** (`Ctrl+C` in the PowerShell window running the server).

1. Check Git status. Make sure the current tree is clean and v0.6.1 is present.
2. If v0.6.1 is already merged into `main`, create a new feature branch:

   ```powershell
   git switch main
   git pull --ff-only origin main
   git switch -c feature/v0.6.2-midnight-replay
   ```

3. Open this ZIP and copy the **contents** directly into your existing QuantDesk project root (the folder that contains `market_structure_lab`, `tests_market_structure`, and `requirements.txt`). Windows: **Merge folders** and **Replace matching files**.
4. Do **not** copy the ZIP folder itself as a nested directory. Do **not** replace `README.md`, `data/`, `.env`, `.venv/`, `outputs/`, or your personal SQLite journal. None of those are included in this ZIP.
5. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests_market_structure -v
   .\.venv\Scripts\python.exe -m market_structure_lab.workstation --data-dir data
   ```

   If `data` isn't populated, run with your existing `data_demo` directory instead. Open **http://127.0.0.1:8765/**. Use **Ctrl+Shift+R** in your browser if an old stylesheet remains cached.

Expected: **71 tests, OK** if you have the v0.6.1 codebase plus the patch. If you have extra tests, your count can be higher.

## Keyboard shortcuts — Historical Replay only

| Keys | Behavior |
| --- | --- |
| **Left / Right** | Previous / next **intraday bar**, or session on 1D. If the session slider itself is focused, step sessions. |
| **Shift + Left / Right** | Jump **5 bars** (or 5 sessions when the session slider is focused / in 1D). |
| **Up / Down** | Previous / next available session. |
| **Home / End** | First / last intraday bar, or first / last session in 1D. |
| **Shift + Home / End** | First / last available session. |
| **Space** | Play / pause; playback speed selected from the Speed dropdown. |

Shortcuts do not fire while typing into the research journal, editing text, using date/time selectors or in another workspace. Arrow presses on a focused range slider follow the corresponding timeline.

## Commit once

After verifying the UI and tests, in the project root:

```powershell
git add market_structure_lab/assets/workstation.html tests_market_structure/test_v031_ui.py tests_market_structure/test_v061_graphite.py tests_market_structure/test_v062_replay_ux.py docs/preview-v062-midnight-desktop.png docs/preview-v062-midnight-mobile.png docs/releases/v0.6.2.md INSTALL_ONE_COMMIT.md
git diff --cached --stat
git commit -m "style: darken graphite theme and polish replay controls v0.6.2"
git push -u origin feature/v0.6.2-midnight-replay
```

Create a pull request to `main` and merge once checks pass. Tag `v0.6.2` after the merge if desired. **No need for separate styling, keyboard or playback commits.**

## Scope, fidelity and limitations

- This is **still historical replay**, not a continuously streamed TradingView-like feed. Replay frames and profiles come from your local read-only APIs; the existing time-aware backend prevents future-bar leakage.
- On first visits to a new bar, network/server response time can still limit how quickly its candle chart appears. Only position labels and scrub preview update instantly; previously visited frames use the short cache.
- Replay cache is in-memory and cleared on page refresh. It only caches **previously requested** frames; it does not use future prices to compute levels.
- The backend still reports its v0.6 research API version; the interface is labeled **v0.6.2**.
- No additional dependencies or API entitlements. No trading endpoints or orders.
