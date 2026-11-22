"""Strict, offline, causal RTH minute-bar ingestion and deterministic aggregation.

Timestamps are **bar END** times with explicit UTC offsets, including the
first 09:31 ET and last 16:00 ET regular-session bar. No gap interpolation.
Daily research zones are supplied separately from the PRIOR completed session.
OHLCV is not true volume-at-price, order flow, or a tradable quote.
"""
from __future__ import annotations

from datetime import time
from pathlib import Path
import re

import numpy as np
import pandas as pd

INTERVALS = {'1m': 1, '5m': 5, '15m': 15, '1h': 60}
TIMESTAMP_RE = re.compile(r'(?:Z|[+-]\d{2}:\d{2})$', re.I)
REQUIRED = ('timestamp', 'open', 'high', 'low', 'close', 'volume')
MARKET_ZONE = 'America/New_York'


def load_minutes(path: str | Path) -> pd.DataFrame:
    """Reject ambiguous timestamps, bad OHLCV, out-of-session and unordered rows.

    Missing minutes and early-close days remain *visible as incomplete* rather
    than silently inserting fabricated candles. Full-day expectation is 390.
    """
    path = Path(path)
    raw = pd.read_csv(path, dtype={'timestamp': 'string'})
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    if not set(REQUIRED).issubset(raw.columns):
        raise ValueError(f'{path}: expected timestamp,open,high,low,close,volume')
    df = raw[list(REQUIRED)].copy()
    if df.empty or len(df) > 1_000_000:
        raise ValueError(f'{path}: dataset must contain 1 to 1,000,000 minute bars')
    ts = df['timestamp'].str.strip()
    if ts.isna().any() or not ts.map(lambda x: bool(TIMESTAMP_RE.search(x))).all():
        raise ValueError(f'{path}: all timestamps must include Z or an explicit UTC offset')
    try:
        utc = pd.to_datetime(ts, utc=True, errors='raise', format='ISO8601')
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{path}: invalid timestamp') from exc
    if utc.isna().any() or utc.duplicated().any() or not utc.is_monotonic_increasing:
        raise ValueError(f'{path}: timestamps must be strictly increasing and unique')
    local = utc.dt.tz_convert(MARKET_ZONE)
    if ((local.dt.second != 0) | (local.dt.microsecond != 0)).any():
        raise ValueError(f'{path}: timestamps must end on whole minutes')
    minutes = local.dt.hour * 60 + local.dt.minute
    start = 9 * 60 + 30
    if (minutes.le(start) | minutes.gt(16 * 60) | local.dt.dayofweek.gt(4)).any():
        raise ValueError(f'{path}: only weekday 09:31–16:00 America/New_York RTH bar ends allowed')
    for key in REQUIRED[1:]:
        df[key] = pd.to_numeric(df[key], errors='raise')
    if df[list(REQUIRED[1:])].isna().any().any():
        raise ValueError(f'{path}: missing numeric OHLCV')
    vals = df[list(REQUIRED[1:])].to_numpy(dtype=float)
    if not np.isfinite(vals).all():
        raise ValueError(f'{path}: infinite or NaN market data')
    if ((df[['open', 'high', 'low', 'close']] <= 0).any().any() or
        (df['volume'] < 0).any() or
        (df['high'] < df[['open', 'low', 'close']].max(axis=1)).any() or
        (df['low'] > df[['open', 'high', 'close']].min(axis=1)).any()):
        raise ValueError(f'{path}: invalid prices or volume')
    df['timestamp'] = utc.reset_index(drop=True)
    df['session'] = local.dt.strftime('%Y-%m-%d').to_numpy()
    df['minute_offset'] = (minutes - start).to_numpy()  # 1..390
    df = df.reset_index(drop=True)
    if df.groupby('session')['minute_offset'].nunique().max() > 390:
        raise ValueError(f'{path}: too many minutes in a session')
    return df


def aggregate_minutes(minutes: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Aggregate by session / ET 09:30 anchor; never cross a session boundary.

    An incomplete bucket is retained, marked complete=False, and timestamped
    with the final OBSERVED bar end; never with a future scheduled close.
    """
    if timeframe not in INTERVALS:
        raise ValueError(f'Unsupported intraday timeframe: {timeframe}')
    width = INTERVALS[timeframe]
    df = minutes.copy()
    df['bucket'] = (df['minute_offset'] - 1) // width
    grouped = df.groupby(['session', 'bucket'], sort=True, observed=True)
    result = grouped.agg(
        timestamp=('timestamp', 'last'),
        open=('open', 'first'), high=('high', 'max'), low=('low', 'min'),
        close=('close', 'last'), volume=('volume', 'sum'), count=('close', 'size'),
        first_minute=('minute_offset', 'first'), last_minute=('minute_offset', 'last'),
    ).reset_index()
    expected = np.minimum(width, 390 - result['bucket'].to_numpy() * width)
    expected_start = result['bucket'].to_numpy() * width + 1
    expected_end = result['bucket'].to_numpy() * width + expected
    result['complete'] = ((result['count'].to_numpy() == expected) &
                          (result['first_minute'].to_numpy() == expected_start) &
                          (result['last_minute'].to_numpy() == expected_end))
    return result.drop(columns=['first_minute', 'last_minute'])


def coverage(minutes: pd.DataFrame) -> dict:
    per_day = minutes.groupby('session', sort=True).size()
    return {
        'minute_bars': int(len(minutes)),
        'sessions': int(len(per_day)),
        'partial_sessions': int((per_day < 390).sum()),
        'session_counts': {str(d): int(n) for d, n in per_day.items()},
        'source': 'user-supplied 1-minute OHLCV (not trades/Level II)',
    }


def marks_through_bars(candles: pd.DataFrame, levels: list[dict], symbol: str) -> list[dict]:
    """Causal, close-confirmed interactions. No retrospective failure tags.

    Marker is emitted on a bar only when the previous completed bar closed
    OUTSIDE the zone and current OHLC overlaps it. Consecutive touches do not
    get counted as separate events unless price has moved away again.
    """
    if candles.empty:
        return []
    marks = []
    previous_close: float | None = None
    for row in candles.itertuples(index=False):
        end = row.timestamp.isoformat()
        if previous_close is not None:
            for level in levels:
                lo = float(level['price'] - level['radius'])
                hi = float(level['price'] + level['radius'])
                if row.low > hi or row.high < lo:
                    continue
                if previous_close > hi:
                    side = 'above'
                    kind = 'rejection_up' if row.close > hi else ('breakout_down' if row.close < lo else 'close_inside_zone')
                elif previous_close < lo:
                    side = 'below'
                    kind = 'rejection_down' if row.close < lo else ('breakout_up' if row.close > hi else 'close_inside_zone')
                else:
                    continue
                marks.append({'symbol': symbol, 'date': end, 'type': kind, 'side': side,
                              'zone_id': level['id'], 'level_price': float(level['price']),
                              'asof_date': level['asof_date']})
        previous_close = float(row.close)
    return marks


def descriptive_event_study(bars_1m: pd.DataFrame, session_levels: dict[str, list[dict]],
                            symbol: str, horizons=(5, 15, 30, 60)) -> pd.DataFrame:
    """Forward *observations*, not trade fills, on first touches from outside.

    A touch at 10:01 is considered after that minute CLOSE. Outcomes measure
    future minute closes/highs/lows. Events lacking full forward horizon are NaN.
    One event per zone per session avoids inflated repeated-touch counts.
    """
    records = []
    for day, chunk in bars_1m.groupby('session', sort=True):
        levels = session_levels.get(str(day), [])
        if not levels:
            continue
        chunk = chunk.reset_index(drop=True)
        seen: set[str] = set()
        for i in range(1, len(chunk)):
            r = chunk.iloc[i]
            prev = chunk.iloc[i-1]
            for z in levels:
                zid = z['id']
                if zid in seen:
                    continue
                low = z['price'] - z['radius']; high = z['price'] + z['radius']
                if r.low > high or r.high < low:
                    continue
                if prev.close > high:
                    direction = 'from_above'
                    sign = 1  # support bounce descriptive direction
                elif prev.close < low:
                    direction = 'from_below'
                    sign = -1 # resistance bounce descriptive direction
                else:
                    continue
                seen.add(zid)
                entry = float(r.close)
                event = {'symbol': symbol, 'session': str(day), 'timestamp': r.timestamp.isoformat(),
                         'zone_id': zid, 'zone_price': z['price'], 'zone_radius': z['radius'],
                         'zone_asof': z['asof_date'], 'approach': direction,
                         'observed_close': entry}
                for horizon in horizons:
                    # Require uninterrupted forward one-minute observations.
                    target_idx = i + horizon
                    future = chunk.iloc[i+1:target_idx+1]
                    future_offset = r.minute_offset + horizon
                    ok = (target_idx < len(chunk) and len(future) == horizon and
                          int(chunk.iloc[target_idx].minute_offset) == future_offset)
                    event[f'return_{horizon}m_pct'] = (sign * (float(future.iloc[-1].close) / entry - 1)*100) if ok else np.nan
                    if ok:
                        high_price = float(future.high.max())
                        low_price = float(future.low.min())
                        mfe = (high_price-entry)/entry*100 if sign == 1 else (entry-low_price)/entry*100
                        mae = (entry-low_price)/entry*100 if sign == 1 else (high_price-entry)/entry*100
                        event[f'mfe_{horizon}m_pct'] = max(0.0, mfe)
                        event[f'mae_{horizon}m_pct'] = max(0.0, mae)
                    else:
                        event[f'mfe_{horizon}m_pct'] = np.nan
                        event[f'mae_{horizon}m_pct'] = np.nan
                records.append(event)
    return pd.DataFrame.from_records(records)
