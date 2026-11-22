"""Optional, explicit, READ-ONLY Alpaca HISTORICAL equity trade downloader.

Alpaca stock trades REST v2: https://data.alpaca.markets/v2/stocks/{symbol}/trades
This CLI never imports a trading client or writes orders. It does not claim
that trade condition eligibility, corrections, feed quality or venue coverage
has been independently validated. Do not publish the downloaded data.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .volume_profile import MAX_ROWS, load_trades

UTC_ZONE=ZoneInfo('UTC')
ET_ZONE=ZoneInfo('America/New_York')
ENDPOINT='https://data.alpaca.markets/v2/stocks/{symbol}/trades'
SYM_RE=re.compile(r'^[A-Z]{1,10}$')


def _iso_range(start: date, end: date):
    a=datetime(start.year,start.month,start.day,9,30,tzinfo=ET_ZONE)
    # Request through a minute after 16:00 to include closing auction prints;
    # filtering below clips to the RTH cutoff.
    b=datetime(end.year,end.month,end.day,16,1,tzinfo=ET_ZONE)
    return a.astimezone(UTC_ZONE).isoformat(),b.astimezone(UTC_ZONE).isoformat()


def fetch(symbol: str, start: date, end: date, feed: str,
          key: str, secret: str, opener=urlopen, max_pages: int = 250):
    """Return normalized CSV-ready executed prints; no data written on failure."""
    symbol=symbol.upper()
    if not SYM_RE.fullmatch(symbol) or feed not in ('iex','sip'):
        raise ValueError('Invalid stock symbol or feed')
    if end < start or (end-start).days > 6:
        raise ValueError('Choose a range of at most seven calendar days')
    if end >= datetime.now(ET_ZONE).date():
        raise ValueError('Current/future ET sessions are excluded; use completed historical days')
    a,b=_iso_range(start,end)
    rows=[];page_token=None;pages=0
    while True:
        if pages >= max_pages:
            raise ValueError(f'More than {max_pages} API pages; narrow your date range')
        params={'start':a,'end':b,'feed':feed,'sort':'asc','limit':10000}
        if page_token: params['page_token']=page_token
        req=Request(ENDPOINT.format(symbol=symbol)+'?'+urlencode(params),
                    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret,
                             'Accept':'application/json'},method='GET')
        try:
            with opener(req,timeout=30) as resp:
                payload=json.load(resp)
        except (HTTPError,URLError) as exc:
            code=getattr(exc,'code',None)
            raise RuntimeError(f'Alpaca historical trades request failed (HTTP {code or "network"}); verify data subscription, feed, and requested dates') from None
        if not isinstance(payload,dict) or not isinstance(payload.get('trades'),list):
            raise ValueError('Unexpected Alpaca response schema')
        for trade in payload['trades']:
            if not all(k in trade for k in ('t','p','s')):
                raise ValueError('Alpaca returned a trade missing t/p/s')
            ts=datetime.fromisoformat(trade['t'].replace('Z','+00:00')).astimezone(ET_ZONE)
            if ts.date()<start or ts.date()>end or ts.weekday()>=5:
                continue
            if not (ts.replace(hour=9,minute=30,second=0,microsecond=0)<=ts<=ts.replace(hour=16,minute=0,second=0,microsecond=0)):
                continue
            rows.append({'timestamp':trade['t'], 'price':trade['p'], 'size':trade['s'],
                         'venue':trade.get('x',''), 'conditions':','.join(trade.get('c') or []),
                         'trade_id':trade.get('i',''), 'source_label':'ALPACA_'+feed.upper()})
            if len(rows)>MAX_ROWS:
                raise ValueError(f'More than {MAX_ROWS:,} trade prints; narrow the date range')
        pages+=1
        token=payload.get('next_page_token')
        if not token:break
        if token==page_token:raise ValueError('Repeated Alpaca pagination token')
        page_token=token
    return rows,pages


def main():
    p=argparse.ArgumentParser(description='READ-ONLY Alpaca historical equity trades -> local private CSV; no orders')
    p.add_argument('--symbol',choices=['SPY','QQQ'],required=True)
    p.add_argument('--start',required=True,help='First ET session YYYY-MM-DD')
    p.add_argument('--end',required=True,help='Last completed ET session YYYY-MM-DD, max 7 calendar days')
    p.add_argument('--feed',choices=['sip','iex'],default='sip')
    p.add_argument('--data-dir',default='data')
    p.add_argument('--overwrite',action='store_true')
    args=p.parse_args()
    from .credentials import get_alpaca_credentials, CredentialError
    try:
        key, secret = get_alpaca_credentials()
    except CredentialError as exc:
        p.error(str(exc))
    try:
        start=date.fromisoformat(args.start);end=date.fromisoformat(args.end)
    except ValueError:
        p.error('Use exact YYYY-MM-DD dates')
    target=Path(args.data_dir)/'trades'/f'{args.symbol}_trades.csv'
    if target.exists() and not args.overwrite:
        p.error(f'{target} already exists. To replace it, explicitly pass --overwrite. Back it up first.')
    rows,pages=fetch(args.symbol,start,end,args.feed,key,secret)
    if not rows:raise SystemExit('No regular-session trade prints returned. No file written.')
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix('.csv.partial')
    try:
        with temp.open('w',newline='',encoding='utf-8') as f:
            wr=csv.DictWriter(f,fieldnames=['timestamp','price','size','venue','conditions','trade_id','source_label'])
            wr.writeheader();wr.writerows(rows)
        # Confirm our strict importer will accept the data before replacing any file.
        load_trades(temp)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    print(f'READ-ONLY historical trade retrieval: {len(rows):,} prints across {pages} page(s), {args.feed.upper()} feed -> {target}')
    print('Not verified: trade conditions, cancellations, adjusted prices, or feed licensing. Do not commit this CSV.')


if __name__=='__main__':main()
