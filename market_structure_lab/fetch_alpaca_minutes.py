"""Read-only one-session Alpaca SIP/IEX 1-minute OHLCV importer for QuantDesk v0.5.

Alpaca's minute timestamps denote BAR START, while QuantDesk's denote BAR END.
This module explicitly shifts all accepted timestamps +1 minute, never fills gaps,
never accesses trading/order endpoints, and never overwrites without --overwrite.
Historical equity bars endpoint: https://data.alpaca.markets/v2/stocks/{symbol}/bars
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time, timedelta
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .intraday import coverage, load_minutes

ET = ZoneInfo('America/New_York')
UTC = ZoneInfo('UTC')
ENDPOINT = 'https://data.alpaca.markets/v2/stocks/{symbol}/bars'
FIELDS = ['timestamp', 'open', 'high', 'low', 'close', 'volume']


def normalize_one_day(bars: list[dict], session: date) -> list[dict]:
    """Convert API 1m START timestamps to validated QuantDesk END timestamps."""
    normalized = []
    for bar in bars:
        try:
            start = datetime.fromisoformat(str(bar['t']).replace('Z', '+00:00'))
            if start.tzinfo is None:
                raise ValueError('Missing UTC offset')
            start_et = start.astimezone(ET)
            if start_et.date() != session or not (time(9, 30) <= start_et.time() < time(16, 0)):
                continue  # Out-of-session trade aggregates are not RTH minute bars.
            if start_et.second or start_et.microsecond:
                raise ValueError('Non-minute-aligned bar start')
            end = start + timedelta(minutes=1)
            normalized.append({
                'timestamp': end.astimezone(ET).isoformat(timespec='seconds'),
                'open': bar['o'], 'high': bar['h'], 'low': bar['l'],
                'close': bar['c'], 'volume': bar['v'],
            })
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('Unexpected or invalid Alpaca minute bar') from exc
    normalized.sort(key=lambda r: r['timestamp'])
    times = [r['timestamp'] for r in normalized]
    if len(times) != len(set(times)):
        raise ValueError('Repeated minute timestamps across API pages')
    if len(normalized) > 390:
        raise ValueError('More than 390 regular-session minute bars')
    return normalized


def fetch_one_day(symbol: str, session: date, feed: str, key: str, secret: str,
                  opener=urlopen, max_pages: int = 10) -> tuple[list[dict], int]:
    if symbol not in ('SPY', 'QQQ') or feed not in ('sip', 'iex'):
        raise ValueError('Unsupported symbol/feed')
    if session >= datetime.now(ET).date() or session.weekday() >= 5:
        raise ValueError('Select a past weekday session')
    start_et = datetime.combine(session, time(9, 30), ET)
    end_et = datetime.combine(session, time(16, 0), ET)
    seen_tokens: set[str] = set()
    token = None
    raw_bars = []
    pages = 0
    while True:
        if pages >= max_pages:
            raise ValueError('Too many API pages; check historical data provider response')
        params = {
            'start': start_et.astimezone(UTC).isoformat(),
            'end': end_et.astimezone(UTC).isoformat(),
            'timeframe': '1Min', 'adjustment': 'raw',
            'feed': feed, 'sort': 'asc', 'limit': 10000,
        }
        if token:
            params['page_token'] = token
        url = ENDPOINT.format(symbol=symbol) + '?' + urlencode(params)
        request = Request(url, headers={
            'APCA-API-KEY-ID': key,
            'APCA-API-SECRET-KEY': secret,
            'Accept': 'application/json',
        }, method='GET')
        try:
            with opener(request, timeout=30) as response:
                payload = json.load(response)
        except (HTTPError, URLError) as exc:
            status = getattr(exc, 'code', 'network')
            raise RuntimeError(f'Alpaca historical bars request failed: {status}. Verify feed access and keys.') from None
        if not isinstance(payload, dict) or not isinstance(payload.get('bars'), list):
            raise ValueError('Alpaca returned an unexpected historical bars response')
        raw_bars.extend(payload['bars'])
        pages += 1
        nxt = payload.get('next_page_token')
        if not nxt:
            break
        if nxt in seen_tokens:
            raise ValueError('Alpaca repeated a pagination token')
        seen_tokens.add(nxt)
        token = nxt
    return normalize_one_day(raw_bars, session), pages


def save_one_day(rows: list[dict], destination: Path, *, overwrite: bool, metadata: dict) -> dict:
    if destination.exists() and not overwrite:
        raise FileExistsError(f'{destination} exists. Back it up before using --overwrite.')
    if not rows:
        raise ValueError('No regular-session minute bars were returned; refusing to create an empty CSV')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix('.csv.partial')
    meta_path = destination.with_suffix('.meta.json')
    try:
        with temp.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        validated = load_minutes(temp)
        status = coverage(validated)
        metadata = dict(metadata)
        metadata.update({'sha256': hashlib.sha256(temp.read_bytes()).hexdigest(),
                         'bar_count': len(rows), 'partial_sessions': status['partial_sessions']})
        # Both the CSV and metadata remain local (the repository's data/ is gitignored).
        temp.replace(destination)
        meta_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        return status
    finally:
        temp.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description='Read-only Alpaca minute bars to QuantDesk; never sends orders')
    ap.add_argument('--symbol', required=True, choices=['SPY', 'QQQ'])
    ap.add_argument('--date', required=True, help='Completed market session YYYY-MM-DD')
    ap.add_argument('--feed', choices=['sip', 'iex'], default='sip')
    ap.add_argument('--data-dir', default='data')
    ap.add_argument('--overwrite', action='store_true')
    args = ap.parse_args()
    key = os.getenv('APCA_API_KEY_ID')
    secret = os.getenv('APCA_API_SECRET_KEY')
    if not key or not secret:
        ap.error('Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY environment variables')
    try:
        session = date.fromisoformat(args.date)
    except ValueError:
        ap.error('--date must be YYYY-MM-DD')
    target = Path(args.data_dir) / 'intraday' / f'{args.symbol}_1m.csv'
    if target.exists() and not args.overwrite:
        ap.error(f'{target} exists; will not overwrite without --overwrite')
    try:
        rows, pages = fetch_one_day(args.symbol, session, args.feed, key, secret)
        info = save_one_day(rows, target, overwrite=args.overwrite, metadata={
            'source': 'Alpaca US equity historical bars v2', 'symbol': args.symbol,
            'feed': args.feed.upper(), 'date': str(session),
            'adjustment': 'raw', 'provider_timestamp': 'BAR_START',
            'quantdesk_timestamp': 'BAR_END_PLUS_ONE_MINUTE',
            'downloaded_utc': datetime.now(UTC).isoformat(),
            'note': 'Historical, research-only; coverage, trade eligibility and corrections not independently audited',
        })
    except (ValueError, FileExistsError, RuntimeError) as exc:
        ap.error(str(exc))
    print(f'READ-ONLY {args.feed.upper()} minute bars: {len(rows)} rows, {pages} API page(s) -> {target}')
    print(f'Session completeness: {390-len(rows)} missing RTH minute(s); 0 invented. Data remain private/local.')
    print('Converted Alpaca bar-start -> QuantDesk bar-end timestamps (+1 minute).')
    print('WARNING: compare RAW minute/trade prices with daily OHLCV adjustment basis before interpreting zones.')


if __name__ == '__main__':
    main()
