# QuantDesk Market Structure Workstation — v0.3.1 UI Design Specification

**Status:** Approved design direction to implement; not yet a code release  
**Target:** Existing Python-served dashboard at `market_structure_lab/assets/workstation.html`  
**Theme name:** Midnight Navy / Graphite  
**Scope:** Frontend redesign only. Preserve v0.3 research behavior, endpoint contracts, local-only server, historical/casual replay rules, saved SQLite notes, and disabled broker/orders behavior.

## 1. Visual North Star

Build an elegant, high-density *quant research terminal* — more understated than a gaming interface, more readable than an unstyled chart app. The chart is the primary focus. Surrounding modules should look polished and intentional but never compete with candlestick readability.

**Keywords:** midnight navy, near-black canvas, slate typography, restrained cyan, quiet borders, precision, legibility, information density.

**Avoid:** bright gradient fills across every card, oversized rounded boxes, noisy drop shadows/glow, redundant badges, gratuitous animation, green/red as the only meaning cue, third-party fonts/CDNs, pretending historical prices are live.

## 2. Theme Tokens (CSS Custom Properties)

| Token | Value | Intended use |
|---|---|---|
| `--bg` | `#060A11` | App background (near-black with navy cast) |
| `--shell` | `#0B1220` | Header/top bar |
| `--panel` | `#0E1827` | Main panels |
| `--panel-raised` | `#121F31` | Hover/selected surfaces, inputs |
| `--plot` | `#080F1B` | Chart plotting region |
| `--line` | `#203047` | Panel edges and dividers |
| `--line-soft` | `#172439` | Chart grids and internal separators |
| `--text` | `#E8EEF8` | Primary text |
| `--text-secondary` | `#A3B3C9` | Secondary text |
| `--text-muted` | `#7F93AC` | Muted labels, metadata |
| `--accent` | `#5BA8F5` | Focus, current selection, resistance zones |
| `--accent-soft` | `rgba(91,168,245,.12)` | Selected background |
| `--bull` | `#32CBB1` | Bullish candle / support zone |
| `--bear` | `#F07686` | Bearish candle |
| `--warn` | `#E9B96F` | Warning/failed breakout |
| `--radius-lg` | `14px` | Main panels |
| `--radius-md` | `10px` | Controls and nested cards |
| `--shadow-panel` | `0 10px 28px rgba(0,0,0,.18)` | Restrained panel depth |

Colors should remain readable under common color-vision differences. Include text labels or iconography for reaction classifications.

## 3. Typography and Density

- Use **system-font stack only**: `Inter, system-ui, Segoe UI, Arial, sans-serif`; do not download Inter. Preserve graceful fallback.
- App title: 18–20px, weight 700. Module titles: 14–16px, weight 650. Metric values: 24–27px, weight 700, `font-variant-numeric: tabular-nums`.
- Label text: 11–12px. Body text: 12.5–14px. Secondary metadata at least 11px, with sufficient contrast.
- Prefer tighter structure and spacing to tiny text. For narrow widths, stack modules before dropping important details.

## 4. Desktop Layout (~1440px and wider)

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  [Q] QuantDesk   / Market Structure            ● LOCAL  HISTORICAL  NO ORDERS │
├──────────────────────────────────────────────────────────────────────────────┤
│  Close [$763.99]   Known zones [6]   Reactions [1]   Dataset [Oct 2026]    │
├───────────────────────────────────────────────┬──────────────────────────────┤
│ Price-reaction replay     [SPY|QQQ] [40/80/160]│ Known zones                 │
│                                               │ price / radius / pivots     │
│     LARGE CANDLESTICK + VOLUME CANVAS         │ first observed / as-of     │
│     restrained grid and zone bands            ├──────────────────────────────┤
│                                               │ Session's reactions         │
│                                               ├──────────────────────────────┤
│ [◀] [▶ Play] [▶] ─────slider──── [DATE]       │ Research journal            │
│                                               │ textarea  [Save]  past notes│
│ Point-in-time disclosure / explanation        │                              │
└───────────────────────────────────────────────┴──────────────────────────────┘
```

- Overall max-width: 1640px; 20–24px outer gutters above 1100px.
- Content: `minmax(0, 1fr) 320–340px` two-column grid, 16px gap. The chart should own ~72–78% of horizontal room.
- Header: visually quiet with subtle bottom border; minimize height. Compact status chips on the right.
- KPI cards: four balanced columns, each separated with subtle borders; no neon gradients. Labels above metrics, context below.
- Side panels: align as they do in v0.3; avoid excessive whitespace and nested boxes. Maintain independent scroll regions for long zone lists and note history.
- Chart area: 510–550px desktop height, 10px radius, no oversized shadow inside the plot.

## 5. Component-Specific Styling

### 5.1 Header and status
- Small monogram mark, midnight background, restrained blue-cyan accent edge.
- Title `QuantDesk` prominent; `/ Market Structure` secondary. Subtitle should not compete with title.
- Status tags: LOCAL (muted cyan dot), HISTORICAL DATA (neutral), NO BROKER / NO ORDERS (neutral outline). Never use a green 'live' treatment for historical prices.

### 5.2 Metrics
- `$763.99` or current displayed result in tabular figures, primary white.
- The `Known zones`, `Reactions`, and `Dataset` figures must retain their factual meanings and date context.
- Reactions **must not** be described as executed trades.
- Hover state subtle; metrics are not clickable and should not look like buttons.

### 5.3 Main chart
- Plot background `--plot`; grid lines `--line-soft` with low contrast.
- Bullish candle `--bull`; bearish candle `--bear`; relatively thin, precise wicks.
- Above-current-price zones: muted blue. Below-current-price zones: muted teal. Do not imply guaranteed resistance/support; existing current-price-relative interpretation stays.
- Zone band fill opacity approx. 0.08–0.14. Dashed midpoint ~0.75 opacity. Small price labels at right edge.
- Event markers: slightly smaller circles, optionally subtle outline. Keep yellow for failed breakouts; use accessible legends/tooltip words.
- Volume: low-opacity bars in candle direction; do not mistake this daily aggregate for volume-at-price.
- Chart tooltip: floating dark panel, crisp border, OHLCV tabular numbers, never obstructs pointer excessively.
- Optional thin current-price reference line only if correctly derived from the selected historical session; avoid fabricated live-price effects.

### 5.4 Controls
- Ticker selector as compact segmented control. Selected symbol receives restrained blue background.
- Previous/play/next with consistent 36–40px hit areas; play/pause text and icons remain clear.
- Slider track dark, filled portion blue. Keyboard operation must continue to work.
- Date displayed in tabular numerals, visually separated from window selector.
- Window selector 40/80/160 bars should retain current values and behavior.

### 5.5 Known zones
- Price emphasized; radius and pivot count visually subordinate.
- One thin separator per zone. Two lines max of metadata before any overflow handling.
- Keep `first tracked`, zone ID, and map `as of` information; never imply first tracked = original discovery date beyond the warm-up tracking rules.
- Add `above / below` label in text or tooltips if colors alone could be ambiguous.

### 5.6 Research journal
- Dark editable textarea with calm focus ring, generous padding, rounded corners.
- Save button: restrained teal emphasis; disabled while request pending.
- Saved notes remain date-and-symbol scoped. Preserve delete functionality, warning confirmation, errors, and data persistence.
- Distinguish saved notes clearly from editable draft. Prevent text clipping.

### 5.7 Footer and research caveats
- Deemphasize visually but keep legible. Explicitly retain **local**, **historical**, **no orders**, **no proof of profitability**, and **daily bars lack intraday option fill data** disclaimers.

## 6. Responsive Behavior

- **≥1100px:** 4 metric columns; chart + right sidebar.
- **700–1099px:** 2 metric columns; chart full width; side panels may appear in two columns below.
- **<700px:** single column; compact header, metrics 2 columns (or 1 when too narrow), chart 340–390px high, controls wrap without cutting labels, side panels stacked.
- Preserve usable button sizes (minimum ~36px target; ideally 40–44px), readable prices, and no horizontal page scroll.

## 7. Motion and States

- Transitions ≤150ms for hover/focus/active changes, no chart animation that changes historical meaning.
- Respect `prefers-reduced-motion: reduce`.
- Loading: muted status 'Loading historical session…' and disabled conflicting inputs only where necessary. Errors shown accessibly via existing alert region.
- Empty zones and empty journal show clear neutral explanations, not broken/blank cards.
- Selected ticker and date must be unambiguous. Browser refresh should retain existing supported behavior; persistent session selection would be a separate feature.

## 8. Exact Implementation Boundary

**Primary UI file to edit:** `market_structure_lab/assets/workstation.html`.

Existing styles are in the file's `<style>` section; JavaScript canvas colors currently occur directly in `draw()` (`#0c1726`, `#f07883`, `#39c7a8`, `#75b6ff`, etc.). A complete theme pass must update **both** CSS custom properties **and** canvas drawing constants. Otherwise the shell and chart will appear mismatched.

**Keep unchanged in v0.3.1:** `market_structure_lab/core.py`, `replay_model.py`, `validation.py`, `workstation.py` API, SQLite database schema, event detection algorithm, same historical datasets, no broker integrations, causal date rules, point-in-time data requests. Optionally document minor cosmetic version label. Do not invent new data endpoints or analytics just to make the mockup look populated.

**Implementation order:**
1. Consolidate CSS tokens and ensure all panels/controls reference the palette.
2. Update chart canvas colors and tooltip presentation to match the palette.
3. Refine spacing, metric cards, sidebar, and control hierarchy.
4. Verify narrow-width layout and reduced-motion/focus states.
5. Run the existing `unittest` suite and manual browser checks on SPY/QQQ, replay dates, window selections, and SQLite journal writes.

## 9. Acceptance Criteria (Definition of Done)

- No external fonts, CDN imports, tracking, or network dependencies introduced.
- Local loopback-only backend and **no order routes** remain intact.
- Both symbols load, switch, and render correctly; 40/80/160-bar view still works.
- Prev, Next, Play/Pause, slider, and hover OHLCV still work.
- Causal maps never expose future candles/levels to earlier session views.
- Zone metadata and completed-session reaction labels remain accurate and readable.
- Journal add/list/delete remains functional and persistent after server restart.
- At common widths (1440px, 1024px, 768px, 390px) no clipping or horizontal page scrollbar; focus outlines visible.
- Candlestick colors, zones, sidebar swatches, and badges use one cohesive palette.
- All existing tests still pass; add UI smoke/structure checks only where they genuinely test behavior.
- A before/after screenshot shows the stronger black/navy contrast, quieter card edges, chart prominence, and cleaner typography without suppressing critical research caveats.

## 10. Explicitly Out of Scope for v0.3.1

New indicators, intraday bars, options-chain feeds, account integration, trading decisions, AI inference, draggable chart tools, volume profile, new backend endpoints, real-time price streaming, and profitability claims. Those belong to later versions; v0.3.1 should remain a **safe, visual-only refinement**.
