"""Opt-in read-only Alpaca stock stream. NOT an order interface.

A single daemon thread streams an authorized IEX or SIP stock feed. Messages are
held in memory, segregated from historical research, and never turned into
historical backtest data. No network connection occurs until start() is called.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import math
import os
import threading
from typing import Any

ALLOWED = frozenset({'SPY','QQQ','IWM','SMH','XLK','XLF','XLE','XLU','XLP','NVDA','AMD','MSFT','AAPL','META','XOM','CVX'})


def _utc(text):
    dt = datetime.fromisoformat(str(text).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Unzoned market timestamp')
    return dt.astimezone(timezone.utc)


def _positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError('Invalid market price / size')
    return number


class LiveTape:
    def __init__(self, symbols=('SPY','QQQ'), feed='iex'):
        self.symbols = tuple(dict.fromkeys(symbols))
        if not self.symbols or len(self.symbols) > 16 or any(s not in ALLOWED for s in self.symbols):
            raise ValueError('Unrecognized or excessive live symbols')
        if feed not in {'iex','sip'}:
            raise ValueError('Live feed must be iex or sip')
        self.feed = feed
        self.lock = threading.RLock()
        self.stopped = threading.Event()
        self.thread = None
        self.connection = 'disabled'
        self.error = None
        self.events_received = 0
        self.last_received_utc = None
        self.messages = {s: {} for s in self.symbols}

    def ingest(self, messages: Any):
        """Validate individual market messages from the authorized stream."""
        if not isinstance(messages, list):
            return
        for item in messages:
            if not isinstance(item, dict) or item.get('S') not in self.messages:
                continue
            sym, kind = item['S'], item.get('T')
            if kind not in ('t','q','b','u'):
                continue
            try:
                when = _utc(item['t'])
                now = datetime.now(timezone.utc)
                if when > now.replace(microsecond=0) + timedelta(minutes=5):
                    continue
                if kind == 't':
                    payload = {'price': _positive(item['p']), 'size': _positive(item['s'])}
                elif kind == 'q':
                    payload = {'bid': _positive(item['bp']), 'ask': _positive(item['ap']),
                               'bid_size': float(item.get('bs',0)), 'ask_size': float(item.get('as',0))}
                    if payload['bid'] > payload['ask'] or min(payload['bid_size'],payload['ask_size']) < 0:
                        continue
                else:
                    op,hi,lo,cl=(_positive(item[x]) for x in ('o','h','l','c'))
                    if hi < max(op,cl,lo) or lo > min(op,cl,hi):
                        continue
                    payload = {'open':op,'high':hi,'low':lo,'close':cl,'volume':float(item.get('v',0))}
                    if not math.isfinite(payload['volume']) or payload['volume'] < 0:
                        continue
            except (KeyError, ValueError, TypeError, OverflowError):
                continue
            payload['event_time_utc'] = when.isoformat()
            payload['received_utc'] = now.isoformat()
            with self.lock:
                channel = {'t':'last_trade','q':'last_quote','b':'last_bar','u':'updated_bar'}[kind]
                prev = self.messages[sym].get(channel)
                if prev and _utc(prev['event_time_utc']) > when:
                    continue  # late/out-of-order prints must not replace newer observations
                self.messages[sym][channel] = payload
                self.events_received += 1
                self.last_received_utc = now.isoformat()

    def snapshot(self):
        with self.lock:
            last = self.last_received_utc
            now = datetime.now(timezone.utc)
            age = max(0.0,(now-_utc(last)).total_seconds()) if last else None
            event_times = [obs['event_time_utc'] for records in self.messages.values() for obs in records.values()]
            newest_event = max((_utc(t) for t in event_times),default=None)
            event_age = max(0.0,(now-newest_event).total_seconds()) if newest_event else None
            return {
                'enabled': self.connection != 'disabled',
                'connection': self.connection, 'feed': self.feed.upper(),
                'scope': 'CONSOLIDATED_US_EQUITIES' if self.feed=='sip' else 'IEX_SINGLE_VENUE_ONLY',
                'stale': age is None or age > 60 or event_age is None or event_age > 90,
                'event_age_seconds': round(event_age,1) if event_age is not None else None,
                'last_received_age_seconds': round(age,1) if age is not None else None,
                'last_received_utc': last,
                'events_received': self.events_received,
                'symbols': {s: dict(v) for s,v in self.messages.items()},
                'error': self.error,
                'orders_enabled': False,
                'warning': 'Live observations are read-only and NOT persisted to historical research. IEX volume is not consolidated. Late/corrected prints are not reconciled. Check exchange event timestamps, not only receipt time.',
            }

    def start(self):
        key, secret = os.getenv('APCA_API_KEY_ID'), os.getenv('APCA_API_SECRET_KEY')
        if not key or not secret:
            raise ValueError('Live stream requested but APCA_API_KEY_ID / APCA_API_SECRET_KEY not set')
        if self.thread is not None:
            return
        self.connection = 'connecting'
        self.thread = threading.Thread(target=self._run, args=(key,secret), daemon=True, name='quantdesk-readonly-data')
        self.thread.start()

    def _run(self, key, secret):
        try:
            import websocket  # dependency installed from requirements.txt
        except ImportError:
            with self.lock:
                self.connection='dependency_missing'; self.error='pip install websocket-client'
            return
        backoff=2
        while not self.stopped.is_set():
            sock=None
            try:
                with self.lock:
                    self.connection='connecting'; self.error=None
                sock=websocket.create_connection('wss://stream.data.alpaca.markets/v2/'+self.feed, timeout=15)
                sock.send(json.dumps({'action':'auth','key':key,'secret':secret}))
                authenticated=False
                for _ in range(6):
                    payload=json.loads(sock.recv())
                    if any(x.get('T')=='error' for x in payload):
                        raise RuntimeError('Alpaca stream authentication / entitlement rejected')
                    if any(x.get('T')=='success' and x.get('msg')=='authenticated' for x in payload):
                        authenticated=True;break
                if not authenticated:
                    raise RuntimeError('No authentication confirmation from Alpaca stream')
                sock.send(json.dumps({'action':'subscribe','trades':self.symbols,'quotes':self.symbols,'bars':self.symbols}))
                with self.lock:self.connection='connected'
                backoff=2
                sock.settimeout(3)
                while not self.stopped.is_set():
                    try:
                        payload=json.loads(sock.recv())
                    except websocket.WebSocketTimeoutException:
                        continue
                    if isinstance(payload,list) and any(x.get('T')=='error' for x in payload if isinstance(x,dict)):
                        raise RuntimeError('Alpaca stream returned an error (check feed entitlement or symbol limit)')
                    self.ingest(payload)
            except Exception as exc:
                with self.lock:
                    self.connection='reconnecting'
                    self.error=str(exc)[:180]  # never log URLs or credentials
                if self.stopped.wait(backoff):break
                backoff=min(backoff*2,60)
            finally:
                if sock is not None:
                    try:sock.close()
                    except Exception:pass
        with self.lock:self.connection='stopped'

    def stop(self):
        self.stopped.set()
        if self.thread is not None:
            self.thread.join(timeout=4)
