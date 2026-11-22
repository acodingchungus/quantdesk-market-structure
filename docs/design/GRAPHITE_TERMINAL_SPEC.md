# QuantDesk v0.6.1 — Graphite Terminal
## A. UI design specification · v1.0 · 2026-11-22

**Status:** implemented in the v0.6.1 theme-only patch; see tests and release notes.  
**Source baseline:** QuantDesk v0.6 `market_structure_lab/assets/workstation.html` (523 lines), as contained in `QuantDesk_Market_Structure_v0_6_COMPLETE.zip`.  
**Scope:** visual hierarchy, styles, chart inks, interaction states, and responsive presentation. **No change** to KDE, replay causality, volume-profile mathematics, market intelligence, API endpoints, credentials, order safety, or datasets.

---

## 1. Creative brief

**Feel:** high-contrast black/graphite market-research workstation. Mechanical, fast, disciplined; not glossy, neon, blue-fintech, or soft-card aesthetics. **Black, cool grays and white are the foundation. Green is the main accent; red and yellow are roughly equal *secondary semantic accents*.**

**Core principles**

1. **Neutral-first:** 85–90% of visible surface area is grayscale. Avoid colored panels or gradient floods.
2. **Depth through tone and edge, not blur:** three distinguishable surface elevations and crisp 1px borders. Small, optional shadows only where depth helps.
3. **Color means something:** green for selection/positive/healthy, red for negative/error, yellow for caution/POC/attention. Never use color alone to encode a state.
4. **Data dominates decoration:** chart, time context, data provenance and price/volume readouts are the heroes.
5. **Truthful research status:** source (`IEX`, `SIP`, `SYNTHETIC`, `HISTORICAL`), freshness, incomplete and unavailable are always readable; no false green “live” badge for stale/no events.
6. **Readable at normal zoom:** end the 9–10px-label habit wherever reasonably possible. Aim for at least 12px ancillary text; use 13–14px normal content, 15–18px section headings and 22–28px high-priority numbers.

### Non-goals

- No redesign of trading logic, backend APIs, data storage, third-party dependencies, or a migration to a UI framework.
- No TradingView-like chart overhaul in this patch; no hover/zoom/pan rewrites unless necessary to keep contrast or accessibility.
- No new paid data feeds, trading signals, automated orders or live-to-replay data blending.
- No green gradients on every card, no red-vs-green implication for a zone whose only property is above/below current price.

---

## 2. Semantic color tokens — locked palette

Use the canonical tokens and *aliases* below. The original v0.6 CSS variables should still exist for compatibility with current selectors and canvas code; their values can point to the new tokens.

| Canonical token | Hex / value | Job |
|---|---|---|
| `--surface-app` | `#08090B` | App canvas / outer background |
| `--surface-shell` | `#101317` | Header and toolbar |
| `--surface-panel` | `#15191E` | Primary cards / sections |
| `--surface-raised` | `#1B2026` | Hovered or nested raised cards |
| `--surface-inset` | `#0C0F12` | Chart plotting area, inputs, inset wells |
| `--surface-hover` | `#23292F` | Hover feedback, no colorful bloom |
| `--stroke-subtle` | `#262C33` | Dividers and quiet structure |
| `--stroke-base` | `#343C45` | Distinct panel/field border |
| `--stroke-strong` | `#4A5561` | Hovered border or strong separation |
| `--ink-primary` | `#F5F7F8` | Main white text and critical numbers |
| `--ink-secondary` | `#D4D9DD` | Ordinary copy and secondary values |
| `--ink-muted` | `#9EA8B1` | Supporting labels / provenance |
| `--positive` | `#2ED47A` | Active selection, bullish candle, connected data |
| `--positive-hover` | `#43E08A` | Hover, bright green selected emphasis |
| `--positive-surface` | `#153524` | Subtle tinted selected surface |
| `--negative` | `#FF5A5F` | Bearish candle, decline, failure, dangerous action |
| `--negative-surface` | `#341C20` | Quiet red error surface |
| `--caution` | `#F5C451` | Stale/partial data, POC, attention marker |
| `--caution-surface` | `#332B19` | Yellow advisory surface |
| `--focus-ring` | `#43E08A` | 2px keyboard focus outline |
| `--chart-grid` | `#293039` | Subtle grid against black plotting area |
| `--chart-neutral-zone` | `#ADB6BE` | Above-price KDE zone (neutral positional distinction) |
| `--chart-supported-zone` | `#2ED47A` | Below-price KDE zone (relative position only) |
| `--chart-value-area` | `#78838E` | VAH/VAL reference strokes, not blue |
| `--chart-crosshair` | `#AAB3BA` | Hover/inspection guide |

**Color proportions:** neutrals ≥ 85% of overall UI. Green should be the most frequent *accent*, but should not turn every state or surface green. Red and yellow should have **comparable prominence among non-green alerts and markers**; not every red needs a yellow counterpart.

### Replacement mapping for existing v0.6 variables

| Existing variable | v0.6.1 value |
|---|---|
| `--bg` | `var(--surface-app)` |
| `--shell` | `var(--surface-shell)` |
| `--panel` | `var(--surface-panel)` |
| `--panel-raised` | `var(--surface-raised)` |
| `--plot` | `var(--surface-inset)` |
| `--line` | `var(--stroke-base)` |
| `--line-soft` | `var(--stroke-subtle)` |
| `--text` | `var(--ink-primary)` |
| `--text-secondary` | `var(--ink-secondary)` |
| `--text-muted` | `var(--ink-muted)` |
| `--accent` | `var(--positive)` |
| `--accent-soft` | `rgba(46,212,122,.12)` |
| `--bull` | `var(--positive)` |
| `--bear` | `var(--negative)` |
| `--warn` | `var(--caution)` |

**Contrast spot-check (WCAG relative luminance, calculated against `#15191E` panels):** primary text ≈ 16.4:1; muted text **7.3:1**; green 9.1:1; red 5.8:1; yellow 10.8:1. These are token-level checks, **not** a claim that all rendered states already meet WCAG. Actual component combinations must be audited after implementation. Border contrast is intentionally lower; don't rely on a subtle line alone to communicate a control state.

---

## 3. Shape, typography, density

| Element | Target |
|---|---|
| Base font | System stack: `Inter`, `Segoe UI`, Arial, sans-serif; no network font |
| Body / chart-support labels | 13–14px / 12px |
| Section headings | 16px, 650–700 weight |
| Page/product heading | 19–21px |
| Major numeric metrics | 24–28px, tabular numerals |
| Numerical table values | tabular figures / right aligned |
| Panel corner radius | 6px (current 14px feels soft) |
| Buttons/inputs radius | 5px |
| Chart inner frame | 4px |
| Status tags | 4px corners (small rectangles, not pills) |
| Main desktop gutter | 16px; 12px within groups; 8px micro-spacing |
| Main input height | minimum 38px desktop; 44px touch targets on compact screens |
| Border | 1px `--stroke-base`, stronger on hover/focus |
| Shadows | none by default; if needed, minimal black shadow, no glow |

**Avoid:** extra-wide letter spacing on normal labels, micro-text inside 330px side panels, rounded bubbles for every status, blue highlights, colorful hover bloom, 10px-only captions for important information.

---

## 4. Detailed component specifications

### A. Header and identity

- Header surface `--surface-shell`, 1px bottom divider.
- Product mark: near-square graphite tile, 1px border; bright green `Q` or a subtle green left edge. **No navy gradient**.
- Title primary white; `/ Market Structure Workstation` medium gray.
- Status cards small, squared, neutral. `LOCAL` may have a green *dot* when server is healthy; it is not a statement that market feed is connected.
- Feed state must be explicit. `IEX LIVE`, `SIP LIVE`, `STALE`, `STREAM DISABLED`, `HISTORICAL`, `SYNTHETIC` are different concepts.

### B. Three workspace tabs

- Arrange `Live Market`, `Historical Replay`, `Research Lab` as a flat, compact top navigation row.
- Default inactive: graphite background, gray border, white-gray text.
- Active: dark green surface + green 1px keyline/2px bottom rule + white label; do not use bright solid-green fill under the entire label.
- Hover: lighter graphite, stronger neutral border.
- Keyboard focus: 2px green outline **outside** the border.
- Active state must be conveyed with `aria-pressed` and structural indication, not only color.

### C. Metric cards and row lists

- Primary metric values white, with green/red only for actual signed performance or health state.
- Preserve all data and labels, but increase internal contrast (neutral panel vs inset rows).
- `UNAVAILABLE`: muted-neutral plus explicit text, not red (absence is not an error).
- Negative 20-day returns red; positive returns green; near-zero neutral unless semantics explicitly demand a sign.
- Research assets: compact, readable row/table with `SYMBOL / relative strength / last observation / data status`, not a tall wall of vague repeated cards. Group by indices, sectors, mega-cap tech, energy when available; do not invent data.

### D. Live Market

- Distinct freshness treatment: green `RECEIVING`, yellow `STALE` or `DELAYED`, red `DISCONNECTED`/`AUTH ERROR`, neutral `DISABLED`.
- Never display `LIVE` as green purely because Live tab is selected.
- Use separate text labels for event timestamp age and local arrival age. Preserve single-venue IEX vs consolidated SIP warnings.
- A disabled feed should have a useful empty state with its launch flag, not a fabricated last price.

### E. Replay chart

- Chart background `--surface-inset`, grid `--chart-grid`, axis labels `--ink-muted`.
- Bull candles green `#2ED47A`; bear candles red `#FF5A5F`. Candles remain distinguishable by body placement and not color alone.
- Above-price zone: gray dashed line and low-opacity gray band. Below-price zone: muted green dashed line and low-opacity green band. **Legend says “above/below selected price,” not guaranteed resistance/support or buy/sell.**
- POC: yellow short-dash line with `TICK POC` label; VAH/VAL: medium gray dash lines, not teal or blue.
- Failed breakout marker: small yellow dot with contrasting border. Reject/bounce marker retains direction as shape/position as well as color.
- Crosshair neutral gray, not neon green; hover tooltip dark raised graphite with crisp border and larger than 10px text.
- Price and time axes use tabular figures. Chart remains point-in-time: styling must never expose future bars or hidden prints.

### F. Volume profile

- Ordinary bins: neutral gray (`#555E68`); value-area bins: medium gray (`#89939D`); **POC bin is green or yellow?** Choose **yellow** to match the explicit `TICK POC` chart line and reserve green for active UI / positive market data. This supersedes the v0.6 blue-POC mapping.
- POC price annotation bright yellow with accessible label; value-area boundary labels light gray.
- Keep volume bars sharply squared, visually quieter than the POC indicator.
- No synthetic fallback profile when trade prints are unavailable. Preserve `SYNTHETIC TICKS` / `TRADE TICKS` provenance.

### G. Alerts, notebook, forms

- Inline research disclaimers: neutral dark surface; yellow left border or concise caution heading. Avoid a giant full-width yellow box.
- Dangerous errors: red border + red text + meaningful copy. Do not make every warning red.
- Notebook: off-black textarea, strong white text, visible neutral border, green focus outline, green compact Save button.
- Delete note: red text with clear confirmation; preserve existing delete behavior and API safety.
- Disabled state: neutral dark + readable `disabled` treatment, not transparent almost-invisible controls.

---

## 5. Layout across viewports

**Wide desktop (≥1200px):** 4 metric cards across, main chart + 330–370px side research rail; Research Lab should aim for a more compact two-column density; avoid vast blank space to the left of the asset list. Chart is dominant.

**Tablet (700–1199px):** 2 metric cards per row; chart full width; sidebar panels in two columns when sufficient room. Research Lab stacks if its values become cramped.

**Mobile (320–699px):** one column; metric cards may be a 2×2 grid if text doesn't collide; tabs wrap; chart height around 360–400px; all controls remain operable; no horizontal overflow. Prefer 12px minimum helper text and 44px mobile targets. Do not hide safety source labels to save space.

**Responsive acceptance:** exercise 320, 375, 390, 768, 1024, 1440, 1920px, 100% and 125% zoom.

---

## 6. Chart semantics legend

| Visual | Meaning | Warning |
|---|---|---|
| Bright green candle | Close ≥ open | Not an entry signal |
| Bright red candle | Close < open | Not an exit signal |
| Gray dashed zone | Known KDE level above selected price | Positional only |
| Green dashed zone | Known KDE level at/below selected price | Positional only |
| Yellow dotted price | Tick-derived POC | Executed-trade volume, not resting depth |
| Gray dash price | VAH/VAL from executed trades | Not an orderbook quote |
| Yellow marker | Failed-breakout event | Completed observation only |
| Green status dot | Connection/receipt healthy *for its defined source* | IEX still ≠ SIP |

---

## 7. Accessibility and interaction rules

- Minimum **4.5:1** normal-text contrast and **3:1** large text/control non-text indicators where applicable; ensure semantic badges are tested on their tinted backgrounds.
- 2px focus visible ring, at least 2px outline offset, reliable `:focus-visible`; keyboard nav preserved.
- Buttons and tabs keep `aria-pressed` and names. If adding icons, supply accompanying text or accessible name.
- Labels do not depend on red/green alone. Use explicit `+/-`, `STALE`, `CONNECTED`, etc.
- Preserve `prefers-reduced-motion` behavior. No animated gradients, excessive glows or background network calls.
- Keep chart canvas self-contained and accessible via surrounding text/legend; canvas does not become a stand-alone accessible data table in this cosmetic pass.

---

## 8. Release acceptance criteria

- [ ] No navy/blue token or hard-coded navy paint remains in active UI component styles, tooltip, chart canvas or profile histogram.
- [ ] Surface contrast visibly distinguishes shell, panel, inset, and selected states at normal zoom.
- [ ] Green dominates accents; red/yellow used semantically and at comparable levels, without artificial color clutter.
- [ ] Tab switches, replay sliders, hover, ticker switch, timeframe selection, notes, live status, regime research still work.
- [ ] Existing backend endpoints and response shapes unchanged; no order integration.
- [ ] Data provenance/source/freshness labels still correct and clear.
- [ ] Desktop + mobile screenshots reviewed and usable at 320px width.
- [ ] Legacy tests updated intentionally for new palette; tests on data causality and APIs unchanged and passing.

**Decision:** Ship this as a **v0.6.1 visual release** (UI identifier), based on the existing v0.6 research engine. Implement with the adjacent plan (`02_IMPLEMENTATION_PLAN.md`).
