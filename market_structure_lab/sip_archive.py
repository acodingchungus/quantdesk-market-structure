"""QuantDesk v0.6.3: explicit, read-only historical Alpaca equity archive.

No broker/trading endpoints, no automatic downloads, no credentials on disk.
Per-session immutable (unless --overwrite) gzip CSV + verified provenance metadata.
Data are LOCAL / NOT licensed for redistribution. No order-book data here.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time as dt_time, timedelta
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .intraday import load_minutes

ET = ZoneInfo('America/New_York')
UTC = ZoneInfo('UTC')
SYMBOLS = ('SPY', 'QQQ')
BAR_FIELDS = ('timestamp', 'open', 'high', 'low', 'close', 'volume')
TRADE_FIELDS = ('timestamp', 'price', 'size', 'venue', 'conditions', 'trade_id', 'source_label')
URLS = {
    'bars': 'https://data.alpaca.markets/v2/stocks/{symbol}/bars',
    'trades': 'https://data.alpaca.markets/v2/stocks/{symbol}/trades',
}


def session_days(start: date, end: date):
    if end < start or (end-start).days > 92:
        raise ValueError('Range must contain at most 93 calendar days; download one quarter at a time')
    if end >= datetime.now(ET).date():
        raise ValueError('Use only completed past dates (ET); no current-day fetches')
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def dest_path(root: Path, feed: str, kind: str, symbol: str, day: date) -> Path:
    if feed not in ('sip','iex') or kind not in ('bars','trades') or symbol not in SYMBOLS:
        raise ValueError('Invalid archive key')
    return root / 'archive' / feed / kind / symbol / (day.isoformat() + '.csv.gz')


def meta_path(path: Path) -> Path:
    return path.with_name(path.name + '.meta.json')


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_meta_verified(path: Path) -> dict:
    meta = json.loads(meta_path(path).read_text(encoding='utf-8'))
    if not isinstance(meta, dict) or meta.get('sha256') != file_sha256(path):
        raise ValueError(f'Archive checksum mismatch: {path}')
    for field in ('symbol', 'session', 'feed', 'kind', 'rows'):
        if field not in meta:
            raise ValueError(f'Missing provenance {field}: {path}')
    if (not isinstance(meta['rows'], int) or meta['rows'] < 1 or
        path.stem.replace('.csv','') != meta['session']):
        raise ValueError(f'Archive metadata inconsistent: {path}')
    return meta


class AlpacaArchiveClient:
    """Bounded paging with per-page validation and retry of transient failures.

    Injection hooks permit offline tests. A request is never made to a trading URL.
    """
    def __init__(self, key: str, secret: str, *, opener=urlopen,
                 sleeper=time.sleep, min_interval=.40, retries=4):
        if not key or not secret:
            raise ValueError('Missing local Alpaca keys')
        self.key, self.secret = key, secret
        self.opener, self.sleeper = opener, sleeper
        self.interval = min_interval
        self.retries = retries
        self.last_request = None

    def page(self, kind: str, symbol: str, day: date, feed: str, token: str | None):
        if kind not in URLS or symbol not in SYMBOLS or feed not in ('sip','iex'):
            raise ValueError('Unsupported request')
        lo = datetime.combine(day, dt_time(9,30), ET).astimezone(UTC)
        hi = datetime.combine(day, dt_time(16,1), ET).astimezone(UTC)
        params = {'start':lo.isoformat(), 'end':hi.isoformat(),
                  'feed':feed, 'sort':'asc', 'limit':10000}
        if kind == 'bars':
            params.update({'timeframe':'1Min', 'adjustment':'raw'})
        if token:
            params['page_token'] = token
        url = URLS[kind].format(symbol=symbol) + '?' + urlencode(params)
        req = Request(url, headers={'APCA-API-KEY-ID':self.key,
            'APCA-API-SECRET-KEY':self.secret, 'Accept':'application/json'}, method='GET')
        for attempt in range(self.retries + 1):
            if self.last_request is not None:
                self.sleeper(max(0., self.interval-(time.monotonic()-self.last_request)))
            self.last_request = time.monotonic()
            try:
                with self.opener(req, timeout=45) as response:
                    payload = json.load(response)
                if not isinstance(payload,dict) or not isinstance(payload.get(kind),list):
                    raise ValueError('Invalid Alpaca JSON schema')
                return payload
            except HTTPError as e:
                status = e.code
                if status not in (429,500,502,503,504) or attempt == self.retries:
                    raise RuntimeError(f'Alpaca historical {kind} HTTP {status}; check feed entitlement or try later') from None
                try:
                    retry_after = float(e.headers.get('Retry-After','0') or 0)
                except (ValueError,TypeError):
                    retry_after = 0
                self.sleeper(min(65., max(retry_after, 2**attempt)))
            except (URLError,TimeoutError) as e:
                if attempt == self.retries:
                    raise RuntimeError(f'Alpaca historical {kind} network error (request not completed)') from None
                self.sleeper(min(20., 2**attempt))
        raise RuntimeError('Unreachable retry state')


def normalize(kind: str, row: dict, day: date, feed: str):
    try:
        stamp = str(row['t'])
        t = datetime.fromisoformat(stamp.replace('Z','+00:00'))
        if t.tzinfo is None:
            raise ValueError('Missing timezone')
        local = t.astimezone(ET)
        if local.date() != day:
            return None
        if kind == 'bars':
            if not (dt_time(9,30) <= local.time() < dt_time(16,0)):
                return None
            if local.second or local.microsecond:
                raise ValueError('Non-minute-aligned Alpaca bar')
            values = [float(row[k]) for k in ('o','h','l','c','v')]
            o,h,l,c,v = values
            if not (all(math.isfinite(x) for x in values) and
                    min(o,h,l,c)>0 and v>=0 and h>=max(o,l,c) and l<=min(o,h,c)):
                raise ValueError('Invalid OHLCV')
            return {'timestamp':(t+timedelta(minutes=1)).astimezone(ET).isoformat(timespec='seconds'),
                    'open':row['o'],'high':row['h'],'low':row['l'],
                    'close':row['c'],'volume':row['v']}
        if kind == 'trades':
            if not (dt_time(9,30) <= local.time() <= dt_time(16,0)):
                return None
            price = float(row['p']); size = float(row['s'])
            if (not math.isfinite(price) or not math.isfinite(size) or
                price <= 0 or price > 1e6 or size <= 0 or
                size > 1e7 or size != int(size)):
                raise ValueError('Invalid trade price/size')
            return {'timestamp':stamp, 'price':row['p'],'size':int(size),
                    'venue':row.get('x',''), 'conditions':','.join(row.get('c') or []),
                    'trade_id':row.get('i',''), 'source_label':'ALPACA_'+feed.upper()}
        raise ValueError('Invalid kind')
    except (KeyError,TypeError,OverflowError,ValueError) as e:
        raise ValueError(f'Invalid Alpaca {kind} record for {day}: {e}') from e


def download_day(client: AlpacaArchiveClient, root: Path, feed: str, kind: str,
                 symbol: str, day: date, *, overwrite=False, max_pages=300) -> dict:
    path = dest_path(root,feed,kind,symbol,day)
    metadata_file = meta_path(path)
    if path.exists() and metadata_file.exists() and not overwrite:
        meta = read_meta_verified(path)
        if (meta['feed'],meta['kind'],meta['symbol'],meta['session']) != (feed,kind,symbol,day.isoformat()):
            raise ValueError(f'Existing archive metadata disagree: {path}')
        return {'action':'SKIPPED_VERIFIED', **meta}
    if (path.exists() or metadata_file.exists()) and not overwrite:
        raise FileExistsError(f'Partial/unverified archive exists: {path}; inspect before --overwrite')
    path.parent.mkdir(parents=True,exist_ok=True)
    partial = path.with_name(path.name + '.partial')
    seen_tokens=set(); next_token=None; pages=0; total=0; filtered=0
    first=None; last=None; prev=None; total_shares=0; bar_offsets=set()
    fields = BAR_FIELDS if kind=='bars' else TRADE_FIELDS
    try:
        with gzip.open(partial,'wt',encoding='utf-8',newline='',compresslevel=5) as fh:
            writer=csv.DictWriter(fh,fieldnames=list(fields))
            writer.writeheader()
            while True:
                if pages >= max_pages:
                    raise ValueError(f'{symbol} {day}: exceeded {max_pages} pages; narrow scope/check feed')
                payload=client.page(kind,symbol,day,feed,next_token)
                pages+=1
                for raw in payload[kind]:
                    normalized=normalize(kind,raw,day,feed)
                    if normalized is None:
                        filtered+=1
                        continue
                    # Source requests sort asc; equal trade timestamps are valid.
                    dt=datetime.fromisoformat(normalized['timestamp'].replace('Z','+00:00')).astimezone(UTC)
                    if prev is not None and dt < prev:
                        raise ValueError(f'{symbol} {day}: trade/bar timestamps decreased')
                    prev=dt
                    if kind=='bars':
                        if normalized['timestamp'] in bar_offsets:
                            raise ValueError(f'{symbol} {day}: duplicate minute bar')
                        bar_offsets.add(normalized['timestamp'])
                    else:
                        total_shares += normalized['size']
                    writer.writerow(normalized);total+=1
                    first=first or normalized['timestamp'];last=normalized['timestamp']
                token=payload.get('next_page_token')
                if not token:
                    break
                if not isinstance(token,str) or token in seen_tokens:
                    raise ValueError(f'{symbol} {day}: invalid/repeated Alpaca page token')
                seen_tokens.add(token);next_token=token
        if total==0:
            partial.unlink(missing_ok=True)
            return {'action':'NO_RTH_DATA', 'feed':feed,'kind':kind,'symbol':symbol,
                    'session':day.isoformat(),'pages':pages}
        # One-day output is validated before publication; >2m trades are allowed
        # in archive (only live profile loader has a separate memory limit).
        if kind=='bars':
            with gzip.open(partial,'rt',encoding='utf-8') as fh:
                # use temp uncompressed for the existing strict validator
                check=path.with_name(path.name + '.validate.csv')
                try:
                    with check.open('w',encoding='utf-8',newline='') as out:
                        shutil.copyfileobj(fh,out)
                    load_minutes(check)
                finally:
                    check.unlink(missing_ok=True)
        metadata={'archive_version':1,'provider':'Alpaca', 'endpoint':'historical_stocks_v2',
                  'feed':feed,'kind':kind,'symbol':symbol,'session':day.isoformat(),
                  'rows':total,'pages':pages,'filtered_out_of_RTH':filtered,
                  'first_timestamp':first,'last_timestamp':last,
                  'source_bar_timestamp':'START' if kind=='bars' else 'TRADE_EVENT',
                  'stored_bar_timestamp':'END_PLUS_1_MIN' if kind=='bars' else 'ORIGINAL',
                  'price_adjustment':'RAW', 'trade_conditions_filtered':False,
                  'corrections_and_late_reporting_audited':False,
                  'executed_shares_unfiltered':total_shares if kind=='trades' else None,
                  'downloaded_utc':datetime.now(UTC).isoformat(),
                  'sha256':file_sha256(partial)}
        # We only promote successfully completed and validated archive data.
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and overwrite:
            # No irreversible overwrite: keep a dated local backup.
            backup=path.with_name(path.name+'.backup')
            if backup.exists():
                raise FileExistsError(f'Backup already exists: {backup}')
            path.replace(backup)
            if metadata_file.exists():
                metadata_file.replace(meta_path(backup))
        partial.replace(path)
        tempmeta=metadata_file.with_suffix('.json.partial')
        tempmeta.write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
        tempmeta.replace(metadata_file)
        return {'action':'DOWNLOADED', **metadata}
    finally:
        partial.unlink(missing_ok=True)


def scan_archive(root: Path, feed: str, symbols: tuple[str,...],
                 start: date, end: date) -> list[dict]:
    """Verify byte integrity and summarize each stored session without future reads."""
    results=[]
    daily_close={}
    for sym in symbols:
        daily_file=root/f'{sym}.csv'
        if daily_file.exists():
            with daily_file.open('r',newline='',encoding='utf-8-sig') as fh:
                for row in csv.DictReader(fh):
                    try:
                        daily_close[(sym,row['date'].strip())]=float(row['close'])
                    except (KeyError,ValueError,TypeError):
                        pass
    for day in session_days(start,end):
        for sym in symbols:
            record={'session':day.isoformat(),'symbol':sym,'feed':feed}
            for kind in ('bars','trades'):
                path=dest_path(root,feed,kind,sym,day)
                if not path.exists():
                    record[kind+'_state']='MISSING';continue
                try:
                    meta=read_meta_verified(path)
                    if (meta['feed'],meta['kind'],meta['symbol'],meta['session']) != (feed,kind,sym,day.isoformat()):
                        raise ValueError('Mismatched source metadata')
                    with gzip.open(path,'rt',encoding='utf-8',newline='') as fh:
                        rdr=csv.DictReader(fh)
                        fields=BAR_FIELDS if kind=='bars' else TRADE_FIELDS
                        if not set(fields).issubset(rdr.fieldnames or []):
                            raise ValueError('Required columns missing')
                        num=0;shares=0;prev=None;seen=set();bar_shares=0;bar_close=None
                        for r in rdr:
                            num+=1
                            if kind=='bars':
                                stamp=r['timestamp']
                                if stamp in seen:raise ValueError('Duplicate bar timestamp')
                                seen.add(stamp)
                                if not all(math.isfinite(float(r[k])) for k in BAR_FIELDS[1:]):
                                    raise ValueError('Bad bar value')
                                bar_close=float(r['close'])
                                bar_shares+=float(r['volume'])
                            else:
                                shares+=int(r['size']);stamp=r['timestamp']
                                if r['source_label'] != 'ALPACA_'+feed.upper():
                                    raise ValueError('Mismatched trade source label')
                            parsed=datetime.fromisoformat(stamp.replace('Z','+00:00'))
                            if parsed.tzinfo is None or (prev is not None and parsed < prev):
                                raise ValueError('Unsorted/naive timestamp')
                            prev=parsed
                        if num != meta['rows'] or num==0:
                            raise ValueError('Metadata row count mismatch')
                    record[kind+'_state']='PRESENT'
                    record[kind+'_rows']=num
                    if kind=='bars':
                        record['bar_missing_vs_390_reference']=390-num
                        record['reported_ohlcv_shares']=bar_shares
                        record['bar_coverage_note']='390 is a FULL session reference; holiday/early close need calendar verification'
                        compare=daily_close.get((sym,day.isoformat()))
                        if compare is not None and compare>0 and bar_close is not None:
                            dev_pct=100*(bar_close/compare-1)
                            record['raw_intraday_vs_daily_close_pct']=round(dev_pct,6)
                            if abs(dev_pct) > 0.30:
                                record['daily_price_basis_warning']='REVIEW: daily CSV may be adjusted or another close convention'
                        if num != 390:
                            record['warning']='INCOMPLETE_OR_EARLY_CLOSE_UNVERIFIED'
                    else:
                        record['trade_shares_unfiltered']=shares
                        record['trade_conditions_audited']=False
                except (OSError,EOFError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
                    record[kind+'_state']='CORRUPT_OR_INCONSISTENT'
                    record[kind+'_error']=str(exc)[:180]
            if 'reported_ohlcv_shares' in record and 'trade_shares_unfiltered' in record:
                bar_vol=record['reported_ohlcv_shares']
                if bar_vol>0:
                    record['raw_trade_shares_to_bar_volume_ratio']=round(record['trade_shares_unfiltered']/bar_vol,5)
                    record['volume_comparison_warning']='NOT an equality test: conditions, late prints, auctions and corrections differ'
            results.append(record)
    return results


def publish_minute_view(root: Path, feed: str, symbol: str,
                        start: date, end: date, *, replace_active=False) -> dict:
    """Opt-in: combine verified bar shards for existing v0.6 replay API.

    Never modifies daily CSV or trade archives. Existing intraday CSV backed up.
    """
    target=root/'intraday'/f'{symbol}_1m.csv'
    if target.exists() and not replace_active:
        raise FileExistsError(f'{target} exists: pass --replace-active to back it up and rebuild')
    paths=[]
    for day in session_days(start,end):
        p=dest_path(root,feed,'bars',symbol,day)
        if p.exists():
            meta=read_meta_verified(p)
            if (meta['feed'],meta['kind'],meta['symbol'],meta['session'])!=(feed,'bars',symbol,day.isoformat()):
                raise ValueError(f'Invalid metadata for {p}')
            paths.append(p)
    if not paths:
        raise ValueError('No verified archived minute bars in the selected range')
    # Ensure daily level maps include imported sessions, otherwise workstation rejects them.
    daily=root/f'{symbol}.csv'
    if not daily.exists():
        raise ValueError(f'Missing daily research CSV: {daily}; do NOT fabricate daily level maps')
    from .core import load_bars
    known={str(x.date.date()) for x in load_bars(str(daily)).itertuples(index=False)}
    unavailable=[p.name[:10] for p in paths if p.name[:10] not in known]
    if unavailable:
        raise ValueError(f'Daily CSV does not contain {len(unavailable)} archived sessions; e.g. {unavailable[:3]}')
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix('.csv.partial')
    count=0
    try:
        with temp.open('w',newline='',encoding='utf-8') as dst:
            writer=csv.DictWriter(dst,fieldnames=list(BAR_FIELDS))
            writer.writeheader()
            for p in paths:
                with gzip.open(p,'rt',newline='',encoding='utf-8') as src:
                    for row in csv.DictReader(src):
                        writer.writerow({k:row[k] for k in BAR_FIELDS})
                        count+=1
        validated=load_minutes(temp)
        if len(validated)!=count:
            raise ValueError('Minute-view row count mismatch')
        if target.exists():
            backup=target.with_name(target.name+'.backup')
            if backup.exists():
                raise FileExistsError(f'Existing backup {backup}; move it aside before replacing again')
            target.replace(backup)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return {'target':str(target),'bars':count,'sessions':len(paths),'feed':feed}


def write_report(report: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'generated_utc':datetime.now(UTC).isoformat(),
                               'sessions':report,'note':'Coverage alone is NOT a validated consolidated volume profile.'},
                              indent=2)+'\n',encoding='utf-8')


def main(argv=None):
    parser=argparse.ArgumentParser(description='QuantDesk historical market-data archive; READ-ONLY provider API / NO ORDERS')
    subs=parser.add_subparsers(dest='command',required=True)
    for cmd in ('download','audit','publish-minutes'):
        p=subs.add_parser(cmd)
        p.add_argument('--symbols',nargs='+',choices=SYMBOLS,default=['SPY','QQQ'])
        p.add_argument('--start',required=True,help='Completed ET session YYYY-MM-DD')
        p.add_argument('--end',required=True,help='Completed ET session YYYY-MM-DD, <=93-day range')
        p.add_argument('--feed',choices=['sip','iex'],default='sip')
        p.add_argument('--data-dir',default='data')
        if cmd=='download':
            p.add_argument('--kind',choices=['both','bars','trades'],default='both')
            p.add_argument('--max-pages-per-day',type=int,default=300)
            p.add_argument('--min-request-interval',type=float,default=.4)
            p.add_argument('--overwrite',action='store_true',help='Back up current verified archive before replacing')
            p.add_argument('--dry-run',action='store_true',help='List planned sessions; no credentials or network')
        if cmd=='publish-minutes':
            p.add_argument('--replace-active',action='store_true',help='Back up existing flat minute CSV')
    args=parser.parse_args(argv)
    try:
        first=date.fromisoformat(args.start);last=date.fromisoformat(args.end)
        days=list(session_days(first,last))
        if not days:raise ValueError('No weekdays in selected range')
        if args.command=='download' and (args.max_pages_per_day<1 or args.min_request_interval<0.30):
            raise ValueError('max-pages >=1 and min-request-interval >=0.30 s required')
        root=Path(args.data_dir)
        if args.command=='download':
            if args.dry_run:
                print(f'DRY RUN: {len(days)} weekdays x {len(args.symbols)} symbol(s) x {2 if args.kind=="both" else 1} dataset(s). No API calls. Holidays require independent calendar check.')
                return 0
            from .credentials import get_alpaca_credentials
            key, secret = get_alpaca_credentials()
            client=AlpacaArchiveClient(key,secret,min_interval=args.min_request_interval)
            kinds=('bars','trades') if args.kind=='both' else (args.kind,)
            for day in days:
                for sym in args.symbols:
                    for kind in kinds:
                        result=download_day(client,root,args.feed,kind,sym,day,
                            overwrite=args.overwrite,max_pages=args.max_pages_per_day)
                        print(f'{sym} {day} {kind}: {result["action"]} ({result.get("rows",0):,} rows, {result.get("pages",0)} pages)')
            print('Historical archives remain LOCAL. Verify with audit before using as research.')
        elif args.command=='audit':
            report=scan_archive(root,args.feed,tuple(args.symbols),first,last)
            output=root/'reports'/f'sip_archive_audit_{first}_{last}.json'
            write_report(report,output)
            for r in report:
                print(f'{r["symbol"]} {r["session"]}: bars={r.get("bars_state")}, trades={r.get("trades_state")}, trades_rows={r.get("trades_rows",0):,}')
            print(f'Audit report (local): {output}')
        elif args.command=='publish-minutes':
            for sym in args.symbols:
                result=publish_minute_view(root,args.feed,sym,first,last,
                                           replace_active=args.replace_active)
                print(f'{sym}: {result["bars"]:,} bars in {result["sessions"]} dates -> {result["target"]}')
            print('Only the flat 1-minute view was rebuilt. Trade profiles load from on-demand SIP archives.')
    except (ValueError,RuntimeError,FileExistsError,OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
