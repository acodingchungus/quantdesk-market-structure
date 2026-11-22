"""Generate visibly SYNTHETIC 1-minute bars for offline UI testing.

Never use these generated candles to claim a market prediction or a backtest.
Uses only deterministic mathematics and already-synthetic daily demo bars.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd


def generate(data_dir: str | Path, days: int = 10) -> None:
    root = Path(data_dir)
    minute_dir = root / 'intraday'
    minute_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(3104)
    for symbol in ('SPY', 'QQQ'):
        src = root / f'{symbol}.csv'
        if not src.exists():
            raise FileNotFoundError(f'Missing {src}. Run market_structure_lab.demo first.')
        daily = pd.read_csv(src)
        daily['date'] = pd.to_datetime(daily['date'])
        rows = []
        for d in daily.tail(days).itertuples(index=False):
            day = pd.Timestamp(d.date).strftime('%Y-%m-%d')
            end_times = pd.date_range(f'{day} 09:31', periods=390, freq='min', tz='America/New_York')
            # Ensure exact daily extrema are touched at two known synthetic timestamps.
            points = [0, 120, 250, 389]
            targets = [float(d.open), float(d.high), float(d.low), float(d.close)]
            close_path = np.interp(np.arange(390), points, targets)
            close_path = np.clip(close_path + (np.sin(np.arange(390)*.37)*.012), float(d.low), float(d.high))
            close_path[0] = float(d.open)
            close_path[-1] = float(d.close)
            volume_shape = rng.uniform(.4, 1.6, 390)
            vol = np.maximum(1, np.floor(volume_shape / volume_shape.sum() * float(d.volume)).astype(int))
            for k, ts in enumerate(end_times):
                op = float(d.open) if k == 0 else float(close_path[k-1])
                cl = float(close_path[k])
                hi = min(float(d.high), max(op, cl)+.01)
                lo = max(float(d.low), min(op, cl)-.01)
                if k == 120: hi = float(d.high)
                if k == 250: lo = float(d.low)
                rows.append({'timestamp':ts.isoformat(), 'open':round(op,5),
                             'high':round(hi,5), 'low':round(lo,5),
                             'close':round(cl,5), 'volume':int(vol[k])})
        dest = minute_dir / f'{symbol}_1m.csv'
        pd.DataFrame(rows).to_csv(dest, index=False)
        print(f'GENERATED SYNTHETIC INTRADAY DEMO ONLY: {dest} ({len(rows)} bars)')


def main():
    parser = argparse.ArgumentParser(description='Create SYNTHETIC minute OHLCV for UI testing, not market research')
    parser.add_argument('--data-dir', default='data_demo')
    parser.add_argument('--days', type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.days <= 100:
        parser.error('--days must be 1..100')
    generate(args.data_dir, args.days)


if __name__ == '__main__':
    main()
