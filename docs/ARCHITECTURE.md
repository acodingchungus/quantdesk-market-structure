# Architecture

```text
Browser interface (HTML, CSS, JavaScript)
               | localhost HTTP / JSON
               v
Python workstation server (`market_structure_lab.workstation`)
          /                       \
         v                         v
OHLCV CSV files             SQLite research notes
         |
         v
Core KDE / ATR price-level engine
         |
         v
Point-in-time replay / events / exploratory tests
```

| File | Purpose |
|---|---|
| `market_structure_lab/core.py` | Level discovery and underlying-data validation |
| `market_structure_lab/replay_model.py` | Completed-session replay frames and reaction labels |
| `market_structure_lab/validation.py` | Exploratory matched-event comparison |
| `market_structure_lab/workstation.py` | Local API and SQLite research notes |
| `market_structure_lab/assets/workstation.html` | Offline-friendly browser UI |
| `market_structure_lab/demo.py` | Deterministic synthetic market-shaped data |

The existing server binds to loopback and does not expose any order-entry endpoint. The public repo excludes all data, personal notes and generated research outputs.
