"""QuantDesk v0.4: loopback-only, research-only local workstation.

Uses the unchanged v0.1 detector and v0.2 causal replay. The browser asks for one
historical frame at a time; candles after its requested date are NEVER returned.
The only write endpoint persists local researcher notes, never orders or trades.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import webbrowser

from .core import Config, evaluate_symbol, load_bars
from .replay_model import make_replay
from .intraday import INTERVALS, load_minutes, aggregate_minutes, coverage, marks_through_bars
import pandas as pd


def pd_timestamp(text):
    return pd.Timestamp(text)

SYMBOL_RE = re.compile(r"^[A-Z]{1,10}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UI_FILE = Path(__file__).resolve().parent / 'assets' / 'workstation.html'
_WINDOWS = {40, 80, 160}


def _iso(series_date):
    return str(series_date.date())


def _numeric(value):
    val = float(value)
    if not math.isfinite(val):
        raise ValueError('Non-finite market value')
    return val


class ResearchStore:
    """Caches price research in memory and stores analyst notes in local SQLite."""

    def __init__(self, data_dir: Path | str, db_file: Path | str,
                 symbols=('SPY', 'QQQ'), config: Config | None = None):
        self.config = config or Config()
        self.data_dir = Path(data_dir)
        self.db_file = Path(db_file)
        self.symbols = tuple(symbols)
        self.datasets = {}
        self.lock = RLock()
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_db()
        self.reload()

    def _connect(self):
        conn = sqlite3.connect(self.db_file, timeout=10)
        conn.execute('PRAGMA busy_timeout=10000')
        return conn

    def _initialize_db(self):
        with closing(self._connect()) as conn, conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS research_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                session_date TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                CHECK(length(content) <= 2000)
            )''')
            conn.execute('CREATE INDEX IF NOT EXISTS note_symbol_date ON research_notes(symbol, session_date)')

    def reload(self):
        """Recompute from validated CSVs; switch all symbols atomically after success."""
        incoming = {}
        for sym in self.symbols:
            if not SYMBOL_RE.fullmatch(sym):
                raise ValueError('Invalid configured symbol')
            file = self.data_dir / (sym + '.csv')
            raw = file.read_bytes()
            bars = load_bars(str(file))
            if len(bars) <= self.config.lookback:
                raise ValueError(f'{sym}: insufficient bars for lookback {self.config.lookback}')
            maps, events = evaluate_symbol(bars, sym, self.config)
            frames, reactions = make_replay(bars, sym, self.config, maps)
            dates = [frame['date'] for frame in frames]
            day_index = {d: i for i, d in enumerate(dates)}
            minute_file = self.data_dir / 'intraday' / f'{sym}_1m.csv'
            intraday = {}
            minute_coverage = None
            minute_sha256 = None
            if minute_file.exists():
                minute_data = load_minutes(minute_file)
                minute_days = set(minute_data['session'])
                unknown = sorted(minute_days - set(day_index))
                if unknown:
                    raise ValueError(f'{sym}: intraday sessions without eligible prior-day zone maps: {unknown[:4]} '
                                     '(extend the corresponding daily CSV first)')
                minute_coverage = coverage(minute_data)
                minute_sha256 = hashlib.sha256(minute_file.read_bytes()).hexdigest()
                for timeframe in INTERVALS:
                    aggreg = aggregate_minutes(minute_data, timeframe)
                    intraday[timeframe] = {
                        str(day): subset.reset_index(drop=True)
                        for day, subset in aggreg.groupby('session', sort=True)
                    }
            incoming[sym] = {
                'bars': bars, 'frames': frames, 'reactions': reactions, 'events': events,
                'index': day_index, 'dates': dates,
                'sha256': hashlib.sha256(raw).hexdigest(),
                'intraday': intraday, 'minute_coverage': minute_coverage,
                'minute_sha256': minute_sha256,
            }
        with self.lock:
            self.datasets = incoming

    def _symbol(self, symbol):
        sym = (symbol or '').upper()
        if sym not in self.datasets:
            raise ValueError(f'Unknown symbol: {sym}')
        return sym

    def status(self):
        with self.lock:
            return {
                'version': '0.4', 'mode': 'RESEARCH_ONLY', 'network': 'LOOPBACK_ONLY',
                'broker_connected': False, 'orders_enabled': False, 'live_prices': False,
                'replay_rule': 't-day map uses completed bars through t-1',
                'data': [{
                    'symbol': sym, 'start': ds['dates'][0], 'end': ds['dates'][-1],
                    'sessions': len(ds['dates']), 'ohlcv_bars': len(ds['bars']),
                    'source_sha256': ds['sha256'],
                    'timeframes': ['1d'] + list(ds['intraday']),
                    'intraday': ds['minute_coverage'],
                    'intraday_source_sha256': ds['minute_sha256'],
                    'is_synthetic_demo': self.data_dir.name == 'data_demo',
                } for sym, ds in self.datasets.items()],
            }

    def dates(self, symbol, timeframe='1d'):
        with self.lock:
            sym = self._symbol(symbol)
            ds = self.datasets[sym]
            if timeframe == '1d':
                dates = list(ds['dates'])
            elif timeframe in ds['intraday']:
                dates = sorted(ds['intraday'][timeframe])
            else:
                raise ValueError(f'{sym}: {timeframe} unavailable. Import data/intraday/{sym}_1m.csv first')
            return {'symbol': sym, 'timeframe': timeframe, 'dates': dates}

    def frame(self, symbol, date=None, window=80, timeframe='1d', bar=None):
        if window not in _WINDOWS:
            raise ValueError('window must be 40, 80 or 160')
        if timeframe != '1d':
            return self._intraday_frame(symbol, date, window, timeframe, bar)
        with self.lock:
            sym = self._symbol(symbol)
            ds = self.datasets[sym]
            date = date or ds['dates'][-1]
            if not DATE_RE.fullmatch(date) or date not in ds['index']:
                raise ValueError('Date is not an eligible completed replay session')
            frame = ds['frames'][ds['index'][date]]
            idx = frame['index']
            lo = max(0, idx - window + 1)
            visible = ds['bars'].iloc[lo:idx+1]
            bars = [{
                'date': _iso(row.date),
                'open': _numeric(row.open), 'high': _numeric(row.high),
                'low': _numeric(row.low), 'close': _numeric(row.close),
                'volume': _numeric(row.volume),
            } for row in visible.itertuples(index=False)]
            # Markers are only taken from completed frames at/before this replay date.
            marks = [m for earlier in ds['frames']
                     if lo <= earlier['index'] <= idx
                     for m in earlier['markers']]
            return {
                'symbol': sym, 'date': date, 'map_asof_date': frame['map_asof_date'],
                'window': window, 'current_index': ds['index'][date],
                'candles': bars, 'levels': frame['levels'], 'markers': marks,
                'today_reactions': frame['markers'],
                'data_ends': ds['dates'][-1],
                'data_is_historical': True, 'timeframe': '1d',
                'current_bar_index': 0, 'session_bar_count': 1,
                'bar_is_complete': True, 'partial_session': False,
            }

    def _intraday_frame(self, symbol, date, window, timeframe, bar):
        with self.lock:
            sym = self._symbol(symbol)
            ds = self.datasets[sym]
            if timeframe not in INTERVALS or timeframe not in ds['intraday']:
                raise ValueError(f'{sym}: no {timeframe} data. Import data/intraday/{sym}_1m.csv')
            sessions = ds['intraday'][timeframe]
            date = date or max(sessions)
            if not isinstance(date, str) or not DATE_RE.fullmatch(date) or date not in sessions:
                raise ValueError('Date is not an imported intraday session')
            day = sessions[date]
            if bar is None:
                index = len(day) - 1
            elif isinstance(bar, int) and 0 <= bar < len(day):
                index = bar
            else:
                raise ValueError('bar must be a valid completed intraday bar index')
            lo = max(0, index-window+1)
            visible = day.iloc[lo:index+1]
            # Zone map is frozen as of previous DAILY close, never refreshed intraday.
            dframe = ds['frames'][ds['index'][date]]
            if any(z['asof_date'] >= date for z in dframe['levels']):
                raise AssertionError('Intraday frame attempted to read future daily zones')
            observed = day.iloc[:index+1]
            prior_marks = marks_through_bars(observed, dframe['levels'], sym)
            visible_start = visible.iloc[0]['timestamp']
            marks = [m for m in prior_marks if pd_timestamp(m['date']) >= visible_start]
            current_time = day.iloc[index]['timestamp'].isoformat()
            today = [m for m in prior_marks if m['date'] == current_time]
            rows = [{
                'date': row.timestamp.isoformat(),
                'open': _numeric(row.open), 'high': _numeric(row.high),
                'low': _numeric(row.low), 'close': _numeric(row.close),
                'volume': _numeric(row.volume), 'complete': bool(row.complete),
                'minutes_observed': int(row['count']),
            } for _, row in visible.iterrows()]
            counts = ds['minute_coverage']['session_counts']
            return {
                'symbol': sym, 'date': date, 'map_asof_date': dframe['map_asof_date'],
                'timeframe': timeframe, 'window': window, 'current_index': ds['index'][date],
                'current_bar_index': index, 'session_bar_count': len(day),
                'current_bar_time': current_time, 'bar_is_complete': bool(day.iloc[index].complete),
                'candles': rows, 'levels': dframe['levels'], 'markers': marks,
                'today_reactions': today, 'data_ends': max(sessions),
                'data_is_historical': True, 'partial_session': counts[date] < 390,
                'session_minutes': counts[date], 'expected_session_minutes': 390,
                'source': '1-minute RTH OHLCV; derived timeframes, not tick-by-tick volume profile',
            }

    def note_list(self, symbol, date=None):
        sym = self._symbol(symbol)
        if date is not None and (not DATE_RE.fullmatch(date) or date not in self.datasets[sym]['index']):
            raise ValueError('Invalid note date')
        with closing(self._connect()) as conn, conn:
            conn.row_factory = sqlite3.Row
            if date:
                rows = conn.execute('''SELECT id,symbol,session_date,content,created_at FROM research_notes
                                       WHERE symbol=? AND session_date=? ORDER BY id DESC LIMIT 100''', (sym, date))
            else:
                rows = conn.execute('''SELECT id,symbol,session_date,content,created_at FROM research_notes
                                       WHERE symbol=? ORDER BY id DESC LIMIT 100''', (sym,))
            return {'notes': [dict(r) for r in rows]}

    def note_add(self, symbol, date, content):
        sym = self._symbol(symbol)
        if not isinstance(date, str) or not DATE_RE.fullmatch(date) or date not in self.datasets[sym]['index']:
            raise ValueError('Invalid note date')
        if not isinstance(content, str) or not (1 <= len(content.strip()) <= 2000):
            raise ValueError('Note length must be 1–2000 characters')
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute('INSERT INTO research_notes (symbol,session_date,content) VALUES (?,?,?)',
                                  (sym, date, content.strip()))
            note_id = cursor.lastrowid
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT id,symbol,session_date,content,created_at FROM research_notes WHERE id=?',
                               (note_id,)).fetchone()
            return {'note': dict(row)}

    def note_delete(self, note_id):
        if not isinstance(note_id, int) or note_id < 1:
            raise ValueError('Invalid note ID')
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute('DELETE FROM research_notes WHERE id=?', (note_id,))
            return {'deleted': bool(cursor.rowcount)}


def make_handler(store: ResearchStore, port: int):
    """Factory supplies testable, isolated handlers for the stdlib server."""
    class Handler(BaseHTTPRequestHandler):
        server_version = 'QuantDeskLocal/0.4'

        def log_message(self, fmt, *args):
            # Suppress request logs; journal text and URL query parameters stay private.
            pass

        def _trusted_host(self):
            host = self.headers.get('Host', '')
            return host in {f'127.0.0.1:{port}', f'localhost:{port}',
                            '127.0.0.1', 'localhost'}

        def _send(self, status, body: bytes, content_type='application/json; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj, separators=(',', ':'), allow_nan=False).encode('utf-8'))

        def _error(self, status, explanation):
            self._json(status, {'error': str(explanation)})

        def _request_ok(self, write=False):
            if not self._trusted_host():
                self._error(403, 'Untrusted host header')
                return False
            if write:
                origin = self.headers.get('Origin')
                if origin and origin not in {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}:
                    self._error(403, 'Untrusted origin')
                    return False
                if self.headers.get('X-QuantDesk-Local') != '1':
                    self._error(403, 'Local UI header required')
                    return False
                if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
                    self._error(415, 'JSON request required')
                    return False
            return True

        def do_GET(self):
            if not self._request_ok():
                return
            info = urlsplit(self.path)
            try:
                if info.path in {'/', '/index.html'}:
                    self._send(200, UI_FILE.read_bytes(), 'text/html; charset=utf-8')
                    return
                if info.path == '/favicon.ico':
                    self._send(204, b'', 'image/x-icon')
                    return
                query = parse_qs(info.query)
                sym = query.get('symbol', ['SPY'])[0]
                date = query.get('date', [None])[0]
                timeframe = query.get('timeframe', ['1d'])[0]
                if info.path == '/api/status':
                    self._json(200, store.status())
                elif info.path == '/api/dates':
                    self._json(200, store.dates(sym, timeframe))
                elif info.path == '/api/frame':
                    w = int(query.get('window', ['80'])[0])
                    raw_bar = query.get('bar', [None])[0]
                    bar = None if raw_bar is None else int(raw_bar)
                    self._json(200, store.frame(sym, date, w, timeframe, bar))
                elif info.path == '/api/notes':
                    self._json(200, store.note_list(sym, date))
                else:
                    self._error(404, 'Route not found')
            except (ValueError, TypeError) as exc:
                self._error(400, exc)
            except Exception:
                self._error(500, 'Internal error; check terminal')
                raise

        def do_POST(self):
            if not self._request_ok(write=True):
                return
            if self.path != '/api/notes':
                self._error(404, 'No trading/order endpoints exist')
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size < 1 or size > 8192:
                    self._error(413, 'Invalid request size')
                    return
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('Expected JSON object')
                self._json(201, store.note_add(body.get('symbol'), body.get('date'), body.get('content')))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._error(400, exc)

        def do_DELETE(self):
            if not self._request_ok(write=True):
                return
            match = re.fullmatch(r'/api/notes/(\d+)', self.path)
            if not match:
                self._error(404, 'Route not found')
                return
            self._json(200, store.note_delete(int(match.group(1))))

        def do_OPTIONS(self):
            self._error(405, 'Cross-origin access is not enabled')

    return Handler


def main():
    parser = argparse.ArgumentParser(description='QuantDesk v0.4 local-only research workstation. NO ORDERS.')
    parser.add_argument('--data-dir', default='data', help='Folder containing SPY.csv and QQQ.csv')
    parser.add_argument('--db', default='outputs/v03_workstation/research_notes.sqlite', help='Local SQLite note journal')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('--port must be between 1024 and 65535')
    print('Loading SPY and QQQ historical data and calculating causal zone maps...', flush=True)
    store = ResearchStore(args.data_dir, args.db)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(store, args.port))
    server.daemon_threads = True
    url = f'http://127.0.0.1:{args.port}/'
    print('\nQuantDesk Market Structure Workstation v0.4')
    print('URL:', url)
    print('Mode: LOCALHOST ONLY | HISTORICAL RESEARCH | NO BROKER | NO ORDERS')
    for entry in store.status()['data']:
        print(f" {entry['symbol']}: {entry['ohlcv_bars']} bars, through {entry['end']}")
    for entry in store.status()['data']:
        if entry['intraday']:
            print(f" {entry['symbol']} intraday: {entry['intraday']['minute_bars']} minute bars; "
                  f"{entry['intraday']['partial_sessions']} incomplete/early-close sessions")
        else:
            print(f" {entry['symbol']} intraday: none; 1m/5m/15m/1h disabled until imported")
    print('Research notes SQLite:', Path(args.db).resolve())
    print('Press Ctrl+C to stop the local server.\n', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print('\nShutting down QuantDesk local server.')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
