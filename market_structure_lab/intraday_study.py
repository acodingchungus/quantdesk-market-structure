"""Descriptive, offline minute-touch event study. No trading or claims of alpha."""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import pandas as pd
from .intraday import load_minutes, descriptive_event_study
from .workstation import ResearchStore


def main():
    parser = argparse.ArgumentParser(description='Research-only intraday first-touch event study')
    parser.add_argument('--data-dir', default='data')
    parser.add_argument('--out', default='outputs/v04_intraday_study')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    store = ResearchStore(args.data_dir, out / 'notes.sqlite')
    events = []
    summary = []
    for symbol in store.symbols:
        path = Path(args.data_dir) / 'intraday' / f'{symbol}_1m.csv'
        if not path.exists():
            print(f'{symbol}: no intraday input; skipping')
            continue
        ds = store.datasets[symbol]
        daily_maps = {frame['date']: frame['levels'] for frame in ds['frames']}
        source = load_minutes(path)
        e = descriptive_event_study(source, daily_maps, symbol)
        if not e.empty:
            events.append(e)
            for h in (5, 15, 30, 60):
                values = e[f'return_{h}m_pct'].dropna()
                summary.append({'symbol': symbol, 'horizon_minutes': h, 'events':len(values),
                                'mean_directional_move_pct':float(values.mean()) if len(values) else None,
                                'median_directional_move_pct':float(values.median()) if len(values) else None,
                                'fraction_positive':float((values>0).mean()) if len(values) else None})
        print(f'{symbol}: {len(e)} independent first-touch observations')
    if events:
        pd.concat(events, ignore_index=True).to_csv(out / 'intraday_touch_events.csv', index=False)
    pd.DataFrame(summary).to_csv(out / 'descriptive_summary.csv', index=False)
    (out / 'manifest.json').write_text(json.dumps({'mode':'RESEARCH_ONLY','generated_from':'SYNTHETIC_DEMO' if Path(args.data_dir).name == 'data_demo' else 'USER_SUPPLIED_OHLCV',
      'no_options_fills':True,'no_proven_alpha':True,
      'interpretation':'Future realized price path after identified first touch; not a fill, strategy, or predictive holdout.'},indent=2))
    print('DESCRIPTIVE RESEARCH ONLY:', out.resolve())


if __name__ == '__main__':
    main()
