"""Deterministic SYNTHETIC executed prints for UI tests only.

Fabricated demonstration prints are NOT exchange data, and were derived from
synthetic minute bars. Never mix these files with real market research.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def generate(data_dir: str | Path):
    root = Path(data_dir)
    dest = root / 'trades'
    dest.mkdir(parents=True, exist_ok=True)
    for sym in ('SPY', 'QQQ'):
        path = root / 'intraday' / f'{sym}_1m.csv'
        if not path.exists():
            raise FileNotFoundError(f'Missing {path}. Generate synthetic intraday_demo first.')
        minute = pd.read_csv(path)
        ticks = []
        for bar in minute.itertuples(index=False):
            end = pd.Timestamp(bar.timestamp)
            n = int(bar.volume)
            if n < 1: continue
            pieces = [n] if n < 3 else [n//3, n//3, n-2*(n//3)]
            prices = [float(bar.close)] if len(pieces)==1 else [float(bar.open), (float(bar.high)+float(bar.low))/2, float(bar.close)]
            seconds = [0] if len(pieces)==1 else [-40, -20, 0]
            for qty, price, delta in zip(pieces, prices, seconds):
                ticks.append({'timestamp': (end + pd.Timedelta(seconds=delta)).isoformat(),
                              'price': f'{price:.6f}', 'size':qty, 'source_label':'SYNTHETIC_DEMO'})
        out = dest / f'{sym}_trades.csv'
        pd.DataFrame(ticks).to_csv(out,index=False)
        print(f'SYNTHETIC DEMO PRINTS ONLY: {out} ({len(ticks):,} made-up ticks)')


def main():
    p = argparse.ArgumentParser(description='Generate synthetic prints for UI, never market research')
    p.add_argument('--data-dir',default='data_demo')
    args=p.parse_args()
    generate(args.data_dir)


if __name__=='__main__':
    main()
