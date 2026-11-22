"""Read-only historical Alpaca DAILY context-symbol importer for v0.6.

One symbol at a time; source and adjustment basis retained beside the CSV.
Files are stored in data/context, excluded from version control. No orders.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, date
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .core import load_bars
from .market_intelligence import CONTEXT_SYMBOLS

ET = ZoneInfo('America/New_York')
BASE = 'https://data.alpaca.markets/v2/stocks/{symbol}/bars'


def fetch(symbol, start, end, feed, key, secret, opener=urlopen):
    if symbol not in CONTEXT_SYMBOLS or feed not in {'iex','sip'}:
        raise ValueError('Invalid context symbol or feed')
    a,b = date.fromisoformat(start),date.fromisoformat(end)
    if a > b or b >= datetime.now(ET).date() or (b-a).days > 900:
        raise ValueError('Use a past date range up to 900 calendar days')
    result = []
    tokens = set()
    token = None
    for _ in range(60):
        params={'timeframe':'1Day','start':start+'T00:00:00Z',
                'end':end+'T23:59:59Z','sort':'asc','limit':10000,
                'adjustment':'raw','feed':feed}
        if token:params['page_token']=token
        req=Request(BASE.format(symbol=symbol)+'?'+urlencode(params),
                    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret,
                             'Accept':'application/json'},method='GET')
        try:
            with opener(req,timeout=30) as response:payload=json.load(response)
        except (HTTPError,URLError) as e:
            raise RuntimeError(f'Historical context-data download failed ({getattr(e,"code","network")}). Check feed entitlement.') from None
        if not isinstance(payload,dict) or not isinstance(payload.get('bars'),list):
            raise ValueError('Unexpected Alpaca response')
        for b0 in payload['bars']:
            dt=datetime.fromisoformat(str(b0['t']).replace('Z','+00:00')).astimezone(ET).date()
            if dt < a or dt > b:continue
            result.append({'date':dt.isoformat(),'open':b0['o'],'high':b0['h'],
                           'low':b0['l'],'close':b0['c'],'volume':b0['v']})
        token=payload.get('next_page_token')
        if not token:break
        if token in tokens:raise ValueError('Repeated API pagination token')
        tokens.add(token)
    else:raise ValueError('Maximum pagination exceeded')
    if not result:raise ValueError('No context bars returned')
    dates=[r['date'] for r in result]
    if len(set(dates)) != len(dates) or dates != sorted(dates):
        raise ValueError('Duplicate / out-of-order daily context bars')
    return result


def save(rows,path:Path,source,overwrite=False):
    if path.exists() and not overwrite:raise FileExistsError('Target exists; --overwrite required')
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.csv.partial')
    try:
        with tmp.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=('date','open','high','low','close','volume'))
            w.writeheader();w.writerows(rows)
        load_bars(str(tmp))
        sha=hashlib.sha256(tmp.read_bytes()).hexdigest()
        tmp.replace(path)
        path.with_suffix('.meta.json').write_text(json.dumps({**source,'sha256':sha,'bars':len(rows)},indent=2)+'\n',encoding='utf-8')
    finally:tmp.unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser(description='Download READ-ONLY daily sector/leader data for v0.6 research')
    p.add_argument('--symbol',choices=CONTEXT_SYMBOLS,required=True)
    p.add_argument('--start',required=True)
    p.add_argument('--end',required=True)
    p.add_argument('--feed',choices=['sip','iex'],default='sip')
    p.add_argument('--data-dir',default='data')
    p.add_argument('--overwrite',action='store_true')
    a=p.parse_args()
    key,secret=os.getenv('APCA_API_KEY_ID'),os.getenv('APCA_API_SECRET_KEY')
    if not key or not secret:p.error('Set APCA_API_KEY_ID and APCA_API_SECRET_KEY locally; never commit secrets')
    path=Path(a.data_dir)/'context'/f'{a.symbol}.csv'
    if path.exists() and not a.overwrite:p.error(f'{path} exists; --overwrite required')
    try:
        rows=fetch(a.symbol,a.start,a.end,a.feed,key,secret)
        save(rows,path,{'provider':'Alpaca daily bars','feed':a.feed.upper(),
                        'adjustment':'raw','start':a.start,'end':a.end},a.overwrite)
    except (ValueError,FileExistsError,RuntimeError) as e:p.error(str(e))
    print(f'READ-ONLY context data: {a.symbol} {len(rows)} daily bars -> {path}; feed={a.feed.upper()} raw (check adjustment alignment)')

if __name__=='__main__':main()
