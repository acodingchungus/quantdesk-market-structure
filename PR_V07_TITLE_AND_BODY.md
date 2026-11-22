# PR title
feat: implement v0.7 quantitative event-study research engine

# PR description
## QuantDesk v0.7 — Quantitative Research Engine

Adds an offline-first, read-only daily ETF experiment engine to the existing Midnight Graphite Research Lab.

### Delivered
- Reuses causal KDE and prior-day-extreme daily signals; next-session-open entry and fixed daily close exit
- Development/validation/retrospective chronological samples, purging trades spanning sample boundaries
- Hypothetical cost sensitivity (0/5/10/20 bps), MFE/MAE descriptions, monthly-block bootstrap CIs, randomized-direction diagnostic
- Research table and local read-only `/api/experiments` endpoint
- Reproducible JSON/CSV output with SHA256 provenance
- Fresh-clone Git source-file preflight and automated regression checks

### Validation
- 90+ automated tests locally (confirm exact count on Windows)
- GitHub Actions must pass on Python 3.11 and 3.12 before merging
- No order placement, broker writes, or real-time execution

### Honest research limitations
All historical partitions have been examined before; the retrospective test is **not untouched**. No verified alpha or options P&L. Profiles derived from raw SIP prints are not yet used as level-confluence inputs due to unverified trade conditions and corporate-action price bases. No walk-forward parameter tuning yet.
