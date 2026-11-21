"""Convert existing QuantDesk Alpaca SIP daily CSVs to Market Structure Lab format.

No network access. No brokerage keys. Raw data preserved; outputs only new files.
"""
from __future__ import annotations
import argparse
import csv
from datetime import date
from pathlib import Path

OHLCV = ('open', 'high', 'low', 'close', 'volume')


def convert(src: Path, dest: Path, start: str) -> int:
    if not src.is_file():
        raise FileNotFoundError(f"Missing source: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with src.open('r', newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        missing = set(('timestamp',) + OHLCV) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{src} is missing {sorted(missing)}")
        previous = ''
        for item in reader:
            stamp = item['timestamp']
            day = stamp[:10]
            date.fromisoformat(day)
            if day <= previous:
                raise ValueError(f"Source dates are out of order or duplicated: {day}")
            previous = day
            if day < start:
                continue
            values = {key: item[key] for key in OHLCV}
            for key in OHLCV:
                float(values[key])
            rows.append({'date': day, **values})
    if not rows:
        raise ValueError(f"No rows on or after {start} in {src}")
    with dest.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=('date',) + OHLCV)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{src.name} -> {dest} ({len(rows)} completed daily bars: {rows[0]['date']} to {rows[-1]['date']})")
    return len(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir', type=Path, required=True, help='Directory containing spy_daily_sip.csv and qqq_daily_sip.csv')
    p.add_argument('--out', type=Path, default=Path('data'), help='Output directory for SPY.csv and QQQ.csv')
    p.add_argument('--start', default='2024-01-01', help='First included date YYYY-MM-DD')
    args = p.parse_args()
    date.fromisoformat(args.start)
    for ticker in ('SPY', 'QQQ'):
        convert(args.source_dir / f'{ticker.lower()}_daily_sip.csv', args.out / f'{ticker}.csv', args.start)

if __name__ == '__main__':
    main()
