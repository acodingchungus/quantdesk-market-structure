"""Opt-in, read-only Alpaca stock + crypto snapshot polling for screenshot watchlists.

A bounded in-memory cache, separated from historical replay and event studies.
No broker/order endpoints, no persistence, no automatic requests on startup.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from threading import Event, RLock, Thread
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import math

from .watchlist_v08 import EQUITIES, CRYPTO, SYMBOLS, record

STOCK_URL='https://data.alpaca.markets/v2/stocks/snapshots'
CRYPTO_URL='https://data.alpaca.markets/v1beta3/crypto/us/snapshots'


def _ts(value):
    if value is None:return None
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError,TypeError,OverflowError):return None


def _number(value, *, zero=False):
    try:
        f=float(value)
        return f if math.isfinite(f) and (f>=0 if zero else f>0) else None
    except (ValueError,TypeError,OverflowError):return None


def normalize_snapshot(payload, now=None):
    """Never fall back from missing ticks to fabricated prices."""
    if not isinstance(payload,dict):return None
    now=now or datetime.now(timezone.utc)
    candidates=[]
    for kind,field in [('trade','latestTrade'),('quote','latestQuote'),('minute_bar','minuteBar'),('daily_bar','dailyBar')]:
        data=payload.get(field)
        if not isinstance(data,dict):continue
        stamp=_ts(data.get('t'))
        if stamp is None or stamp > now+timedelta(minutes=5):continue
        if kind=='quote':
            bid=_number(data.get('bp'));ask=_number(data.get('ap'))
            if bid is None or ask is None or bid>ask:continue
            entry={'kind':kind,'event_time_utc':stamp.isoformat(),'bid':bid,'ask':ask,
                   'bid_size':_number(data.get('bs'),zero=True),
                   'ask_size':_number(data.get('as'),zero=True)}
        else:
            price=_number(data.get('p' if kind=='trade' else 'c'))
            if price is None:continue
            entry={'kind':kind,'event_time_utc':stamp.isoformat(),'price':price}
            if kind=='trade':entry['size']=_number(data.get('s'),zero=True)
            else:entry['volume']=_number(data.get('v'),zero=True)
        candidates.append(entry)
    if not candidates:return None
    # Prefer the most recent timestamp; tie-break trade before quote before bar.
    candidates.sort(key=lambda e:(_ts(e['event_time_utc']),
        {'trade':3,'quote':2,'minute_bar':1,'daily_bar':0}[e['kind']]),reverse=True)
    item=candidates[0]
    item['event_age_seconds']=round(max(0.,(now-_ts(item['event_time_utc'])).total_seconds()),1)
    item['stale']=item['event_age_seconds']>120
    return item


class WatchlistMonitor:
    def __init__(self, *, feed='iex', interval=30, chunk_size=25, opener=urlopen):
        if feed not in ('iex','sip'):raise ValueError('Invalid equity feed')
        if not 15<=interval<=600 or not 1<=chunk_size<=50:
            raise ValueError('Polling interval or batch size out of bounds')
        self.feed=feed
        self.interval=interval
        self.chunk_size=chunk_size
        self.opener=opener
        self.lock=RLock();self.stop_event=Event();self.thread=None
        self.state='disabled';self.last_poll_utc=None;self.last_error=None
        self.observations={};self.polls=0

    def _get(self, url, key, secret):
        # GET only, headers carry secrets; no URLs/query params contain credentials.
        request=Request(url,headers={
            'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret,
            'Accept':'application/json'},method='GET')
        with self.opener(request,timeout=20) as response:
            parsed=json.load(response)
        if not isinstance(parsed,dict):raise ValueError('Provider returned unexpected JSON schema')
        if 'snapshots' in parsed:
            parsed=parsed['snapshots']
        if not isinstance(parsed,dict):raise ValueError('Provider snapshots object invalid')
        return parsed

    def poll_once(self, key, secret):
        """Manual/injected polling suitable for offline tests. Atomic cache update.

        Missing symbols stay missing; HTTP errors mark the batch unavailable.
        No previous observation is relabeled fresh when a later poll lacks data.
        """
        now=datetime.now(timezone.utc)
        results={}
        failures=[]
        equities=list(EQUITIES)
        for ix in range(0,len(equities),self.chunk_size):
            names=equities[ix:ix+self.chunk_size]
            params=urlencode({'symbols':','.join(names),'feed':self.feed})
            try:
                raw=self._get(STOCK_URL+'?'+params,key,secret)
                for symbol in names:
                    item=normalize_snapshot(raw.get(symbol),now)
                    if item is not None:results[symbol]=dict(item,provider='alpaca_stock',feed=self.feed.upper())
            except HTTPError as e:
                failures.append(f'stock snapshot HTTP {e.code}')
            except (URLError,TimeoutError,OSError,ValueError,TypeError,json.JSONDecodeError):
                failures.append('stock snapshot unavailable or invalid')
        # Crypto snapshots are a different provider endpoint, not stock SIP/IEX.
        requested=list(CRYPTO.values())
        try:
            raw=self._get(CRYPTO_URL+'?'+urlencode({'symbols':','.join(requested)}),key,secret)
            for user_symbol,provider_symbol in CRYPTO.items():
                item=normalize_snapshot(raw.get(provider_symbol),now)
                if item is not None:results[user_symbol]=dict(item,provider='alpaca_crypto',feed='CRYPTO_US',provider_symbol=provider_symbol)
        except HTTPError as e:
            failures.append(f'crypto snapshot HTTP {e.code}')
        except (URLError,TimeoutError,OSError,ValueError,TypeError,json.JSONDecodeError):
            failures.append('crypto snapshot unavailable or invalid')
        with self.lock:
            self.observations=results  # Never hold stale values from earlier polls as fresh.
            self.last_poll_utc=now.isoformat()
            self.last_error='; '.join(failures) if failures else None
            self.polls+=1
            self.state='partial' if failures else 'polling'
        return self.snapshot()

    def start(self):
        if self.thread is not None:return
        from .credentials import get_alpaca_credentials
        key,secret=get_alpaca_credentials()
        self.stop_event.clear()
        with self.lock:self.state='connecting'
        self.thread=Thread(target=self._run,args=(key,secret),daemon=True,name='quantdesk-watchlist-readonly')
        self.thread.start()

    def _run(self,key,secret):
        while not self.stop_event.is_set():
            self.poll_once(key,secret)
            if self.stop_event.wait(self.interval):break
        with self.lock:self.state='stopped'

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:self.thread.join(timeout=5)

    def snapshot(self):
        now=datetime.now(timezone.utc)
        with self.lock:
            observations={}
            for symbol in SYMBOLS:
                entry=record(symbol)
                obs=self.observations.get(symbol)
                if obs is not None:
                    obs=dict(obs)
                    d=_ts(obs['event_time_utc'])
                    obs['event_age_seconds']=round(max(0.,(now-d).total_seconds()),1)
                    obs['stale']=obs['event_age_seconds']>120
                entry['observation']=obs
                entry['status']=(
                    'unsupported_source' if entry['provider_symbol'] is None else
                    'disabled' if self.state=='disabled' else
                    'stale' if obs is not None and obs['stale'] else
                    'observed' if obs is not None else 'unavailable')
                observations[symbol]=entry
            return {'version':'0.8.0','state':self.state,'stock_feed':self.feed.upper(),
                    'stock_feed_scope':'IEX_SINGLE_VENUE_ONLY' if self.feed=='iex' else 'SIP_ENTITLEMENT_REQUIRED',
                    'last_poll_utc':self.last_poll_utc,'polls':self.polls,'error':self.last_error,
                    'polling_interval_seconds':self.interval,
                    'instruments':observations,
                    'orders_enabled':False,'historical_persistence':False,
                    'warning':'Read-only last observed provider snapshots; NEVER historical replay input. Missing, stale, delisted and unsupported instruments are not synthesized. IEX is not consolidated SIP.'}
