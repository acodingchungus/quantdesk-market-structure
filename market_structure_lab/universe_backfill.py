"""v0.7.2: controlled, resumable, read-only multi-symbol historical research backfill.

Alpaca data requests are explicit; no broker/order endpoints and no implied live feed.
The archives are private, source-labeled and distinct from SPY/QQQ strategy signals.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from .universe import CORE, CONTEXT_SYMBOLS, GROUPS, select_symbols
from .sip_archive import (AlpacaArchiveClient, dest_path, download_day,
                          publish_minute_view, read_meta_verified, session_days)


def coverage_snapshot(root: Path, feed: str, symbols: tuple[str, ...],
                      start: date, end: date) -> dict:
    """Inventory verified archive minute shards without loading any raw trade data.

    Weekdays are NOT equivalent to exchange sessions. Do not infer holidays,
    completeness, liquidity, current-day or research alpha from this inventory.
    """
    if feed not in ('sip','iex'):raise ValueError('Unsupported feed')
    days=list(session_days(start,end))
    result=[]
    for sym in symbols:
        item={'symbol':sym,'feed':feed,'weekday_candidates':len(days),
              'verified_days':0,'verified_bars':0,'non_390_days':0,
              'absent_weekdays':0,'corrupt_days':0,'first':None,'last':None,
              'daily_context_file':(root/'context'/f'{sym}.csv').exists() if sym not in CORE else (root/f'{sym}.csv').exists(),
              'replay_enabled':sym in CORE}
        for day in days:
            file=dest_path(root,feed,'bars',sym,day)
            if not file.exists():
                item['absent_weekdays']+=1
                continue
            try:
                meta=read_meta_verified(file)
                if (meta['feed'],meta['kind'],meta['symbol'],meta['session']) != (
                    feed,'bars',sym,day.isoformat()):
                    raise ValueError('Metadata key mismatch')
                item['verified_days']+=1;item['verified_bars']+=meta['rows']
                item['non_390_days']+=int(meta['rows']!=390)
                item['first']=item['first'] or day.isoformat()
                item['last']=day.isoformat()
            except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
                item['corrupt_days']+=1
        result.append(item)
    return {'feed':feed,'start':start.isoformat(),'end':end.isoformat(),
            'sessions_are_weekday_candidates_only':True,
            'notes':('Absent weekdays can be weekends-excluded holidays, market closures, missing provider data, or download gaps. '
                     'Non-390 days may be early closes, partial feeds, or incomplete downloads. '
                     'Checksums verify local bytes, not trade condition eligibility or completeness. '
                     'Context-only symbols are not enabled for KDE replay or v0.7 experiments.'),
            'symbols':result}


def download_minutes(root: Path, feed: str, symbols: tuple[str,...],
                     start: date, end: date, *, client, log=print,
                     max_pages=300) -> list[dict]:
    """Fail closed at first error. Re-running skips already checksum-verified shards."""
    outcomes=[]
    for day in session_days(start,end):
        for sym in symbols:
            result=download_day(client,root,feed,'bars',sym,day,max_pages=max_pages)
            outcomes.append(result)
            log(f'{sym} {day} minute bars: {result["action"]} ({result.get("rows",0)} rows)')
    return outcomes


def download_daily_context(root: Path, feed: str, symbols: tuple[str,...],
                           start: date, end: date, *, key: str, secret: str,
                           fetcher=None, saver=None, log=print):
    """Only creates previously absent context CSVs. Never overwrites research evidence."""
    from .fetch_alpaca_context import fetch, save
    fetcher=fetcher or fetch;saver=saver or save
    rows=[]
    for sym in symbols:
        if sym in CORE:
            log(f'{sym}: core daily candles are user-supplied; leave untouched')
            continue
        if sym not in CONTEXT_SYMBOLS:
            raise ValueError(f'Unrecognized context symbol: {sym}')
        target=root/'context'/f'{sym}.csv'
        if target.exists():
            log(f'{sym}: existing context file preserved; manage/extend its date range separately')
            continue
        data=fetcher(sym,start.isoformat(),end.isoformat(),feed,key,secret)
        saver(data,target,{'provider':'Alpaca','feed':feed,'symbol':sym,
                         'adjustment':'raw','start':start.isoformat(),
                         'end':end.isoformat(),'research_only':True})
        log(f'{sym}: wrote {len(data)} historical daily candles to local context')
        rows.append(sym)
    return rows


def main(argv=None):
    p=argparse.ArgumentParser(description='QuantDesk multi-ticker historical backfill; read-only Alpaca data / NO ORDERS')
    sub=p.add_subparsers(dest='command',required=True)
    for action in ('plan','download-minutes','coverage','download-context','publish-core'):
        q=sub.add_parser(action)
        q.add_argument('--groups', nargs='+', choices=tuple(GROUPS), default=None)
        q.add_argument('--symbols', nargs='*', default=[])
        q.add_argument('--start',required=True,help='First past ET date (YYYY-MM-DD)')
        q.add_argument('--end',required=True,help='Last past ET date, <=93 calendar days')
        q.add_argument('--feed',choices=['sip','iex'],default='sip')
        q.add_argument('--data-dir',default='data')
        if action=='download-minutes':
            q.add_argument('--execute',action='store_true',help='Explicit authorization to contact Alpaca')
            q.add_argument('--max-pages-per-day',type=int,default=300)
        if action=='download-context':
            q.add_argument('--execute',action='store_true',help='Explicit authorization to contact Alpaca')
        if action=='publish-core':
            q.add_argument('--replace-active',action='store_true',help='Back up existing active SPY/QQQ minute CSVs')
            q.add_argument('--min-sessions',type=int,default=1)
    a=p.parse_args(argv)
    try:
        start=date.fromisoformat(a.start);end=date.fromisoformat(a.end)
        dates=tuple(session_days(start,end))
        if not dates:raise ValueError('Selected range has no weekdays')
        symbols=select_symbols(a.groups if a.groups is not None else ([] if a.symbols else ['core']),a.symbols)
        root=Path(a.data_dir)
        if a.command in ('plan','coverage'):
            inv=coverage_snapshot(root,a.feed,symbols,start,end)
            print(f'{len(dates)} weekday candidates × {len(symbols)} symbols = {len(dates)*len(symbols)} potential historical bar requests')
            for item in inv['symbols']:
                print(f'{item["symbol"]:6s} verified={item["verified_days"]:3d} bars={item["verified_bars"]:7d} '
                      f'absent-weekdays={item["absent_weekdays"]:3d} corrupt={item["corrupt_days"]:2d} '
                      f'context={"yes" if item["daily_context_file"] else "no"}')
            if a.command=='coverage':
                dest=root/'reports'/f'universe_coverage_{a.feed}_{start}_{end}.json'
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_text(json.dumps(inv,indent=2)+'\n',encoding='utf-8')
                print(f'Local inventory: {dest}')
            print('Weekdays are NOT verified exchange sessions; this is an archive inventory, not a complete-data certification.')
        elif a.command in ('download-minutes','download-context'):
            if not a.execute:
                raise ValueError('No download performed. Review plan and add --execute to authorize read-only data requests')
            from .credentials import get_alpaca_credentials
            key,secret=get_alpaca_credentials()
            if a.command=='download-minutes':
                if a.max_pages_per_day<1 or a.max_pages_per_day>300:
                    raise ValueError('--max-pages-per-day must be 1..300')
                client=AlpacaArchiveClient(key,secret)
                outcomes=download_minutes(root,a.feed,symbols,start,end,client=client,max_pages=a.max_pages_per_day)
                print(f'Finished {len(outcomes)} session-symbol attempts; audit before using data for research.')
            else:
                download_daily_context(root,a.feed,symbols,start,end,key=key,secret=secret)
                print('Context data are descriptive and as-of bounded. Existing local files were not overwritten.')
        else:
            if a.min_sessions<1:raise ValueError('--min-sessions must be >=1')
            if any(sym not in CORE for sym in symbols):
                raise ValueError('Only SPY/QQQ can be published into existing replay; other symbols remain context/archive only')
            inv=coverage_snapshot(root,a.feed,symbols,start,end)
            short=[x['symbol'] for x in inv['symbols'] if x['verified_days']<a.min_sessions]
            if short:raise ValueError(f'Fewer than {a.min_sessions} verified days: {short}')
            for sym in symbols:
                summary=publish_minute_view(root,a.feed,sym,start,end,replace_active=a.replace_active)
                print(f'{sym}: activated {summary["bars"]} minute bars / {summary["sessions"]} historical dates')
            print('Restart the workstation to load the active 1-minute view. Other symbols remain context-only.')
    except (ValueError,RuntimeError,OSError,FileExistsError) as e:
        p.error(str(e))
    return 0

if __name__=='__main__':raise SystemExit(main())
