"""Causal daily OHLCV replay frames and descriptive level-interaction labels.

At frame date t, level candidates use only completed bars through t-1.
Markers describe the fully completed t candle and only appear on/after t.
This is NOT order-book liquidity or intraday executable entry logic.
"""
from __future__ import annotations
from dataclasses import asdict
from typing import Optional
import pandas as pd
from .core import Config, discover_levels


def make_replay(df: pd.DataFrame, symbol: str, cfg: Config, historical_maps: Optional[pd.DataFrame] = None,
                failure_window: int = 3) -> tuple[list[dict], pd.DataFrame]:
    if failure_window < 1:
        raise ValueError('failure_window must be >= 1')
    if len(df) <= cfg.lookback:
        raise ValueError('Not enough bars for causal replay')
    # Use the original v0.1 historical maps, if supplied, to avoid recomputing
    # the same discoveries. Their effective_date is the date when they can be used.
    known = {}
    if historical_maps is not None and not historical_maps.empty:
        rows = historical_maps[historical_maps.symbol == symbol]
        for day, g in rows.groupby('effective_date', sort=False):
            known[day] = g.to_dict('records')
    prior_live: list[dict] = []
    next_id = 1
    frames = []
    marks: list[dict] = []
    pending: list[dict] = []
    for i in range(cfg.lookback, len(df)):
        date = str(pd.Timestamp(df.iloc[i].date).date())
        prior_date = str(pd.Timestamp(df.iloc[i-1].date).date())
        if date in known:
            candidates = [{
                'price': float(x['price']), 'radius': float(x['radius']),
                'pivot_count': int(x['pivot_count']), 'strength': float(x['strength']),
                'asof_date': str(x['level_asof_date']),
            } for x in known[date]]
        else:
            candidates = [{
                'price': float(v.price), 'radius': float(v.radius),
                'pivot_count': int(v.pivot_count), 'strength': float(v.strength),
                'asof_date': v.asof_date,
            } for v in discover_levels(df.iloc[:i], cfg)]
        if any(x['asof_date'] >= date for x in candidates):
            raise AssertionError('Future-aware level candidate detected')

        # Greedy one-to-one level tracking, using ONLY the immediately previous map.
        edges = []
        for ni, c in enumerate(candidates):
            for oi, p in enumerate(prior_live):
                gap = abs(c['price']-p['price'])
                tol = max(c['radius'] + p['radius'], .005 * c['price'])
                if gap <= tol:
                    edges.append((gap / tol, ni, oi))
        assignment = {}
        used_old = set()
        for _, ni, oi in sorted(edges):
            if ni not in assignment and oi not in used_old:
                assignment[ni] = oi
                used_old.add(oi)
        levels = []
        for ni, c in enumerate(candidates):
            if ni in assignment:
                old = prior_live[assignment[ni]]
                c['id'] = old['id']
                c['first_seen'] = old['first_seen']
            else:
                c['id'] = f'{symbol}-Z{next_id:03d}'
                next_id += 1
                c['first_seen'] = date
            levels.append(c)
        prior_live = levels
        cur = df.iloc[i]
        prev_close = float(df.iloc[i-1].close)
        low, high, close = float(cur.low), float(cur.high), float(cur.close)

        # Failed-breakout confirmations use FROZEN earlier zones, not updated zones.
        # No success/failure label is placed on the original breakout retroactively.
        survivors = []
        today_markers = []
        for p in pending:
            if i - p['break_idx'] > failure_window:
                continue
            reversed_back = close > p['upper'] if p['side'] == 'down' else close < p['lower']
            if reversed_back:
                item = {'symbol': symbol, 'date': date, 'index': i,
                        'type': 'failed_breakout_confirmed', 'zone_id': p['zone_id'],
                        'level_price': p['center'], 'pivot_count': p['pivot_count'],
                        'first_seen': p['first_seen'], 'asof_date': p['asof_date'],
                        'origin_breakout_date': p['break_date'], 'close': close,
                        'side': p['side']}
                marks.append(item)
                today_markers.append(item)
            else:
                survivors.append(p)
        pending = survivors
        for v in levels:
            lo = v['price']-v['radius']; hi = v['price']+v['radius']
            if low > hi or high < lo:
                continue
            if prev_close > hi:
                side = 'above'
                label = ('rejection_up' if close > hi else
                         'breakout_down' if close < lo else 'close_inside_zone')
            elif prev_close < lo:
                side = 'below'
                label = ('rejection_down' if close < lo else
                         'breakout_up' if close > hi else 'close_inside_zone')
            else:
                side = 'inside'
                label = 'close_inside_zone'
            item = {'symbol': symbol, 'date': date, 'index': i,
                    'type': label, 'zone_id': v['id'],
                    'level_price': v['price'], 'pivot_count': v['pivot_count'],
                    'first_seen': v['first_seen'], 'asof_date': v['asof_date'],
                    'origin_breakout_date': '', 'close': close, 'side': side}
            marks.append(item)
            today_markers.append(item)
            if label.startswith('breakout_'):
                pending.append({'break_idx': i, 'break_date': date,
                                'upper': hi, 'lower': lo, 'center': v['price'],
                                'zone_id': v['id'], 'pivot_count': v['pivot_count'],
                                'first_seen': v['first_seen'], 'asof_date': v['asof_date'],
                                'side': 'down' if label.endswith('down') else 'up'})
        frames.append({'index': i, 'date': date, 'levels': levels,
                       'markers': today_markers, 'map_asof_date': prior_date})
    return frames, pd.DataFrame(marks, columns=[
        'symbol','date','index','type','zone_id','level_price','pivot_count','first_seen',
        'asof_date','origin_breakout_date','close','side'])
