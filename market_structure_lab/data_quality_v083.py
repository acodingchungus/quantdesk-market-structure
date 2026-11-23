"""v0.8.3: offline exchange-calendar and price-source audit. NO network/orders.

A clean audit certifies date/format/declared-provenance consistency, not that a
vendor's prints are economically accurate or licensed for redistribution.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from .core import REQUIRED


@lru_cache(maxsize=1)
def _xnys():
    try:
        import exchange_calendars
    except ImportError as exc:
        raise RuntimeError('v0.8.3 requires exchange-calendars: pip install -r requirements.txt') from exc
    return exchange_calendars.get_calendar('XNYS')


def _days(frame: pd.DataFrame) -> pd.DatetimeIndex:
    if 'date' not in frame:
        raise ValueError('Missing date')
    days = pd.DatetimeIndex(pd.to_datetime(frame['date'], errors='raise'))
    if days.tz is not None or days.hasnans or days.has_duplicates or not days.is_monotonic_increasing:
        raise ValueError('Dates must be unique, sorted, timezone-naive completed session dates')
    if (days != days.normalize()).any():
        raise ValueError('Session date includes intraday timestamps')
    return days


def audit_symbol(symbol: str, frame: pd.DataFrame, *, source: str,
                 price_basis: str, sha256: str, min_sessions: int = 250) -> dict:
    """Reject unknown price bases; do not repair missing data with forward fills."""
    if not symbol.isascii() or not symbol.isupper() or not symbol.replace('.', '').isalnum():
        raise ValueError('Invalid symbol')
    if not source or not isinstance(source, str):
        raise ValueError('Source must be declared')
    if not isinstance(sha256, str) or len(sha256) != 64 or any(c not in '0123456789abcdef' for c in sha256):
        raise ValueError('Expected source SHA256')
    if not isinstance(min_sessions, int) or min_sessions < 1:
        raise ValueError('Invalid minimum session requirement')
    if not set(REQUIRED).issubset(frame.columns):
        raise ValueError(f'{symbol}: daily OHLCV fields absent')
    if frame.empty:
        raise ValueError(f'{symbol}: no bars')
    days = _days(frame)
    numeric = frame[list(REQUIRED[1:])].apply(pd.to_numeric, errors='raise')
    x = numeric.to_numpy(dtype=float)
    if not np.isfinite(x).all() or np.any(x[:, :4] <= 0) or np.any(x[:, 4] < 0):
        raise ValueError(f'{symbol}: bad daily OHLCV values')
    if (numeric['high'] < numeric[['open','low','close']].max(axis=1)).any() or (numeric['low'] > numeric[['open','high','close']].min(axis=1)).any():
        raise ValueError(f'{symbol}: inconsistent OHLC ranges')
    cal = _xnys()
    expected = cal.sessions_in_range(days[0], days[-1]).tz_localize(None)
    extras = days.difference(expected)
    missing = expected.difference(days)
    close_dates = [d.strftime('%Y-%m-%d') for d in days]
    errors = []
    if len(extras): errors.append('non_exchange_session_dates')
    if len(missing): errors.append('missing_exchange_sessions')
    if len(days) < min_sessions: errors.append('insufficient_history')
    if 'UNVERIFIED' in source.upper() or 'UNKNOWN' in source.upper():
        errors.append('source_provenance_not_reviewed')
    if price_basis not in ('raw', 'adjusted'):
        errors.append('unknown_or_inconsistent_price_basis')
    elif price_basis != 'raw':
        # Approximate paper fills must correspond to actually quoted/raw prices.
        errors.append('non_raw_prices_not_fill_eligible')
    return {
        'symbol':symbol,'source':source,'sha256':sha256,'price_basis':price_basis,
        'start':close_dates[0],'end':close_dates[-1],
        'rows':len(days),'expected_exchange_sessions':len(expected),
        'missing_sessions':[d.strftime('%Y-%m-%d') for d in missing],
        'off_calendar_sessions':[d.strftime('%Y-%m-%d') for d in extras],
        'calendar':'XNYS', 'calendar_library':'exchange-calendars',
        'ready_for_fill_simulation':not errors,'errors':errors,
        'note':'Calendar coverage and declared price basis are checked; trade-print corrections and actual fills are not certified.',
    }


def load_manifest(path: Path) -> tuple[dict, dict[str, pd.DataFrame]]:
    """Require explicit, non-ambiguous provenance, and confine paths to manifest dir."""
    import json
    path=Path(path).resolve()
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or not isinstance(manifest.get('symbols'), dict):
        raise ValueError('Expected v0.8.3 provenance manifest schema=1')
    symbols = manifest['symbols']
    if not set(('SPY','QQQ','NVDA','SMH','XLK','IWM')).issubset(symbols):
        raise ValueError('Missing one of six core research symbols')
    daily={}; records={}
    base=path.parent
    for sym, meta in symbols.items():
        if not isinstance(meta,dict) or not all(k in meta for k in ('path','source','price_basis')):
            raise ValueError(f'{sym}: missing provenance')
        local=(base/meta['path']).resolve()
        if not local.is_relative_to(base) or not local.is_file():
            raise ValueError(f'{sym}: unsafe or missing local CSV path')
        sha=hashlib.sha256(local.read_bytes()).hexdigest()
        from .core import load_bars
        daily[sym]=load_bars(str(local))
        records[sym]={'source':meta['source'],'price_basis':meta['price_basis'],'sha256':sha,'path':meta['path']}
    return records,daily


def audit_universe(records: Mapping[str,dict], daily: Mapping[str,pd.DataFrame], *, min_sessions=250) -> dict:
    symbols={sym:audit_symbol(sym,daily[sym],source=meta['source'],price_basis=meta['price_basis'],
                              sha256=meta['sha256'],min_sessions=min_sessions)
             for sym,meta in sorted(records.items())}
    shared=set.intersection(*(set(_days(daily[sym])) for sym in ('SPY','QQQ','NVDA','SMH','XLK','IWM')))
    bad=[sym for sym,audit in symbols.items() if not audit['ready_for_fill_simulation']]
    return {'schema':'quantdesk.data_audit.v1','ready':not bad and len(shared)>=min_sessions,
            'failed_symbols':bad,'shared_completed_sessions':len(shared),
            'minimum_required_sessions':min_sessions,'symbols':symbols,
            'note':'A passing result does not validate an economic edge or completeness of a vendor feed.'}
