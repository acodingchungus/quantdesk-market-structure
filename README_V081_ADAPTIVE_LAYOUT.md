# QuantDesk v0.8.1 — Adaptive Cross-Market Workspace

A presentation-only improvement to the v0.8 Cross-Market workspace. **No changes to the KDE engine, historical synchronization, strategy-study math, read-only Alpaca integrations, or saved data.**

## Why

In v0.8.0 the Cross-Market view used two side-by-side panels unless the browser was narrower than 950 CSS pixels. Both research rows and watchlist rows were capped at 580px, causing a very short island of content near the top of a tall portrait monitor and requiring scrolling inside a small nested ticker pane.

## What changed

- **Orientation-aware layout:** on tall portrait viewports (portrait orientation, at least 850px high), historical comparison sits above the watchlist, regardless of its desktop-sized width. Horizontal landscape layouts retain the side-by-side presentation.
- **Use available height:** in portrait mode, the Cross-Market card fills the available viewport where content is short. The watchlist uses *page* scrolling instead of a hard 580px internal list cap.
- **Adaptive density:** portrait widths >=1000px get three columns of ticker rows; 700–999px get two; narrow windows get one. The historical comparison also forms a compact grid, reducing wasted height.
- **Landscape balance:** the watchlist uses a viewport-responsive bounded height rather than an unchanging 580px, retaining localized scrolling for landscape workstations.
- **Focus watchlist:** a user-controlled `Focus watchlist` / `Show comparison` button hides and restores the descriptive comparison panel without changing the watchlist data, provider polling, or historical computation.
- **Overflow/accessibility:** rows can wrap lengthy status text without widening the entire page. Focus mode exposes `aria-pressed` and remains available across layout changes.

The interface remains fully local with no remote assets. All 66 screenshot watchlist symbols keep their existing provider eligibility and unavailable/stale handling; this release does **not** add streaming entitlements or transform these data into trading signals.

## Verify locally

1. Start the existing workstation as usual and open `http://127.0.0.1:8765/` in Opera GX.
2. Open **Cross-Market** and choose **All visible symbols**. Confirm the same 66 instruments, including unsupported-source labels where appropriate.
3. On portrait monitor (e.g. 1080×1920 / 1440×2560), ensure **Aligned cross-asset comparison** appears above **TradingView watchlists**, and that the watchlist uses 3 columns and normal page scrolling.
4. On landscape (e.g. 1920×1080), confirm the comparison and watchlist are side by side and the watchlist has a viewport-aware scroll area.
5. Try **Focus watchlist** then **Show comparison**, switch to other workspaces and back, change screenshot groups, and refresh snapshots. No layout action should request broker orders or alter historical results.
6. Run `python -m unittest discover -s tests_market_structure -v`. Expected regression count: **138**.

### Development verification

- All 138 Python unit tests passed in the development environment (135 existing + 3 new layout contracts).
- JavaScript parsed successfully.
- Chromium rendered offline fixture views at 690×1200, 1080×1920, 1150×2048, 1440×2560, and 1920×1080. In the 66-row test: no horizontal overflow, intended orientation-specific grid/scroll behavior, focus mode toggles, and no JavaScript page errors.
- Browser testing used local HTML plus **synthetic display fixture data**, not production Alpaca requests. Confirm the Opera GX appearance locally before merging. Existing API tests cover backend behavior separately.

**Research-only. No automated order execution or established trading profitability.**
