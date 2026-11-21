"""Causal (bar-close) price-level discovery and descriptive forward evaluation.

This intentionally does NOT use an options-pricing model, order book, or true
volume-at-price. All calculations use completed OHLCV daily bars only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence
import math
import numpy as np
import pandas as pd

REQUIRED = ('date', 'open', 'high', 'low', 'close', 'volume')


@dataclass(frozen=True)
class Config:
    lookback: int = 180
    pivot_left: int = 3
    pivot_right: int = 3
    atr_period: int = 14
    bandwidth_atr: float = 0.35
    zone_atr: float = 0.20
    min_pivots: int = 2
    pivot_spacing: int = 5
    max_levels: int = 6
    forward_bars: int = 3
    cooldown_bars: int = 3
    roundtrip_cost_bps: float = 5.0  # Sensitivity only, NOT real option execution cost
    holdout_date: str = '2025-12-04'
    seed: int = 2026

    def __post_init__(self):
        if self.lookback < 30 or self.pivot_left < 1 or self.pivot_right < 1:
            raise ValueError('Invalid lookback or pivot confirmation sizes')
        if self.atr_period < 2 or self.forward_bars < 1 or self.cooldown_bars < 0:
            raise ValueError('Invalid ATR/horizon/cooldown')
        if self.bandwidth_atr <= 0 or self.zone_atr <= 0 or self.min_pivots < 1:
            raise ValueError('Invalid clustering settings')
        if self.max_levels < 1 or self.pivot_spacing < 1 or self.roundtrip_cost_bps < 0:
            raise ValueError('Invalid levels/spacing/cost settings')
        pd.Timestamp(self.holdout_date)


@dataclass(frozen=True)
class Level:
    price: float
    radius: float
    pivot_count: int
    strength: float
    asof_date: str
    latest_pivot_date: str


def load_bars(path: str) -> pd.DataFrame:
    """CSV with date,open,high,low,close,volume; dates designate COMPLETED days.

    Fail closed rather than silently sort/deduplicate or backfill bad bars.
    """
    df = pd.read_csv(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = set(REQUIRED) - set(df.columns)
    if missing:
        raise ValueError(f'{path}: missing columns: {sorted(missing)}')
    df = df[list(REQUIRED)].copy()
    df['date'] = pd.to_datetime(df['date'], errors='raise', utc=True).dt.tz_convert(None).dt.normalize()
    for key in REQUIRED[1:]:
        df[key] = pd.to_numeric(df[key], errors='raise')
    if df.empty or df.isna().any().any():
        raise ValueError(f'{path}: missing data')
    if not df['date'].is_monotonic_increasing or df['date'].duplicated().any():
        raise ValueError(f'{path}: dates must be strictly increasing and unique')
    v = df[['open','high','low','close','volume']].to_numpy(dtype=float)
    if not np.isfinite(v).all():
        raise ValueError(f'{path}: non-finite OHLCV')
    if ((df[['open','high','low','close']] <= 0).any().any() or (df['volume'] < 0).any() or
        (df['high'] < df[['open', 'close', 'low']].max(axis=1)).any() or
        (df['low'] > df[['open', 'close', 'high']].min(axis=1)).any()):
        raise ValueError(f'{path}: invalid OHLCV')
    return df.reset_index(drop=True)


def true_range_and_atr(history: pd.DataFrame, period: int) -> float:
    h = history['high'].to_numpy(dtype=float)
    l = history['low'].to_numpy(dtype=float)
    c = history['close'].to_numpy(dtype=float)
    tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    if len(tr) < period:
        raise ValueError('Not enough completed bars for ATR')
    return float(np.mean(tr[-period:]))


def _pivots(history: pd.DataFrame, config: Config) -> list[tuple[float, float, int]]:
    """Pivot exists only after `pivot_right` *completed* confirmation bars."""
    high = history['high'].to_numpy(dtype=float)
    low = history['low'].to_numpy(dtype=float)
    opn = history['open'].to_numpy(dtype=float)
    close = history['close'].to_numpy(dtype=float)
    n = len(history)
    found = []
    for i in range(config.pivot_left, n-config.pivot_right):
        a, b = i-config.pivot_left, i+config.pivot_right+1
        age = n-1-i
        weight = float(math.exp(-age / 100.0))
        # Defined in advance: 70% candle-body extreme and 30% wick extreme.
        if high[i] > max(high[a:i].max(), high[i+1:b].max()):
            p = .7 * max(opn[i], close[i]) + .3 * high[i]
            found.append((float(p), weight, i))
        if low[i] < min(low[a:i].min(), low[i+1:b].min()):
            p = .7 * min(opn[i], close[i]) + .3 * low[i]
            found.append((float(p), weight, i))
    return found


def _independent_members(members: list[tuple[float,float,int]], min_spacing: int):
    """Collapse neighboring swing dates so one choppy week is not many independent touches."""
    selected = []
    for p,w,i in sorted(members, key=lambda x:x[1], reverse=True):
        if all(abs(i-j) >= min_spacing for _,_,j in selected):
            selected.append((p,w,i))
    return selected


def discover_levels(history: pd.DataFrame, config: Config = Config()) -> list[Level]:
    """Input MUST end on the last completed bar known at analysis time.

    Does not examine any row after history.iloc[-1]. Call with bars[:t] for
    the level map permitted during session t (zero-based index).
    """
    if len(history) < max(35, config.atr_period+1):
        return []
    h = history.iloc[-config.lookback:].reset_index(drop=True)
    atr = true_range_and_atr(h, config.atr_period)
    if atr <= 0:
        return []
    pivots = _pivots(h, config)
    if len(pivots) < config.min_pivots:
        return []
    prices = np.array([x[0] for x in pivots]); weights = np.array([x[1] for x in pivots])
    bw = max(config.bandwidth_atr * atr, .0005 * float(h['close'].iloc[-1]))
    grid = np.linspace(float(prices.min()-2*bw), float(prices.max()+2*bw), 480)
    density = (np.exp(-.5*((grid[:,None]-prices[None,:])/bw)**2) * weights[None,:]).sum(axis=1)
    inds = np.where((density[1:-1] > density[:-2]) & (density[1:-1] >= density[2:]))[0]+1
    inds = sorted(inds, key=lambda k:float(density[k]), reverse=True)
    levels = []
    asof = str(pd.Timestamp(h['date'].iloc[-1]).date())
    for idx in inds:
        location = float(grid[idx])
        # Only reactions near a KDE mode count as contributors to the level.
        members = [p for p in pivots if abs(p[0]-location) <= 1.35*bw]
        members = _independent_members(members, config.pivot_spacing)
        if len(members) < config.min_pivots:
            continue
        p = np.array([x[0] for x in members]); w = np.array([x[1] for x in members])
        center = float(np.average(p, weights=w))
        radius = float(max(config.zone_atr * atr, min(.35*atr, np.sqrt(np.average((p-center)**2, weights=w)))))
        # Do not report nearly identical modes as separate price levels.
        if any(abs(center-old.price) <= (radius+old.radius) for old in levels):
            continue
        latest = max(x[2] for x in members)
        levels.append(Level(price=center, radius=radius, pivot_count=len(members),
                            strength=float(density[idx]), asof_date=asof,
                            latest_pivot_date=str(pd.Timestamp(h['date'].iloc[latest]).date())))
        if len(levels) == config.max_levels:
            break
    return sorted(levels, key=lambda x:x.price)


def _choose_event(candidates: Sequence[Level], prior_close: float, day: pd.Series,
                  atr: float, symbol: str, source: str, day_idx: int):
    valid = []
    for lev in candidates:
        if day['low'] > lev.price + lev.radius or day['high'] < lev.price - lev.radius:
            continue
        # Support approached from ABOVE; resistance approached from BELOW.
        if prior_close > lev.price + lev.radius + .10*atr and day['close'] >= lev.price:
            direction, setup = 1, 'support_rejection'
        elif prior_close < lev.price - lev.radius - .10*atr and day['close'] <= lev.price:
            direction, setup = -1, 'resistance_rejection'
        else:
            continue
        valid.append((abs(prior_close-lev.price), lev, direction, setup))
    if not valid:
        return None
    _, lev, direction, setup = min(valid, key=lambda r:r[0])
    return dict(symbol=symbol, source=source, signal_index=day_idx,
                signal_date=str(pd.Timestamp(day['date']).date()),
                level_asof_date=lev.asof_date, level_price=lev.price,
                zone_radius=lev.radius, level_pivots=lev.pivot_count,
                level_strength=lev.strength, setup=setup, direction=direction,
                atr=atr)


def evaluate_symbol(df: pd.DataFrame, symbol: str, config: Config = Config()) -> tuple[pd.DataFrame,pd.DataFrame]:
    """One confirmed signal per model per symbol per non-overlapping horizon.

    * At day t market-open the only map available is discovered from bars < t.
    * Signal uses complete OHLC bar t, hence entry is OPEN of t+1.
    * Exit is CLOSE of t+forward_bars (not the max favorable excursion).
    * No intraday stop inference and no option P&L inference.
    """
    if len(df) <= config.lookback + config.forward_bars:
        raise ValueError(f'{symbol}: need more than {config.lookback+config.forward_bars} bars')
    results = []
    maps = []
    last_signal = {'clustered':-10**10,'prior_day_extremes':-10**10}
    # Loop uses only historical data as of the PREVIOUS completed session.
    for t in range(config.lookback, len(df)-config.forward_bars):
        history = df.iloc[:t]
        atr = true_range_and_atr(history.iloc[-config.lookback:], config.atr_period)
        if atr <= 0:
            continue
        levels = discover_levels(history, config)
        for rank,lev in enumerate(levels):
            maps.append(dict(symbol=symbol, effective_date=str(pd.Timestamp(df.iloc[t]['date']).date()),
                             price=lev.price, radius=lev.radius, pivot_count=lev.pivot_count,
                             strength=lev.strength, level_asof_date=lev.asof_date,
                             latest_pivot_date=lev.latest_pivot_date, rank=rank+1))
        prev = history.iloc[-1]
        prev_baseline = [Level(float(prev['low']),config.zone_atr*atr,1,1.,
                               str(pd.Timestamp(prev['date']).date()),str(pd.Timestamp(prev['date']).date())),
                         Level(float(prev['high']),config.zone_atr*atr,1,1.,
                               str(pd.Timestamp(prev['date']).date()),str(pd.Timestamp(prev['date']).date()))]
        for source, levels_for_source in [('clustered', levels),('prior_day_extremes', prev_baseline)]:
            if t-last_signal[source] <= config.cooldown_bars or not levels_for_source:
                continue
            event = _choose_event(levels_for_source, float(prev['close']), df.iloc[t], atr, symbol, source, t)
            if event is None:
                continue
            entry = df.iloc[t+1]
            exit_ = df.iloc[t+config.forward_bars]
            entry_price = float(entry['open']); exit_price = float(exit_['close'])
            gross = event['direction']*(exit_price-entry_price)/entry_price
            # Flat roundtrip sensitivity proxy, not observed bid-ask or options costs.
            net = gross - config.roundtrip_cost_bps/10000.
            event.update(entry_date=str(pd.Timestamp(entry['date']).date()),
                         exit_date=str(pd.Timestamp(exit_['date']).date()),
                         entry_price=entry_price, exit_price=exit_price,
                         gross_signed_return=gross, proxy_net_signed_return=net,
                         positive_forward_return=int(gross>0))
            results.append(event)
            last_signal[source] = t
    return pd.DataFrame(maps), pd.DataFrame(results)


def _month_block_ci(df: pd.DataFrame, config: Config, reps: int = 2000):
    """Bootstrap whole exit-month blocks to retain within-month dependence."""
    if len(df) < 8:
        return (None,None)
    months = pd.to_datetime(df['exit_date']).dt.to_period('M').astype(str)
    blocks = [df.loc[months==m,'proxy_net_signed_return'].to_numpy(dtype=float) for m in sorted(months.unique())]
    if len(blocks) < 4:
        return (None,None)
    rng = np.random.default_rng(config.seed)
    vals = []
    for _ in range(reps):
        sampled = [blocks[j] for j in rng.integers(0,len(blocks),size=len(blocks))]
        vals.append(float(np.concatenate(sampled).mean()))
    return (float(np.quantile(vals,.025)),float(np.quantile(vals,.975)))


def summarize_events(events: pd.DataFrame, config: Config) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=['symbol','source','sample','trades','win_rate','mean_gross_pct',
                                     'mean_proxy_net_pct','median_proxy_net_pct','ci95_low_pct','ci95_high_pct'])
    rows=[]
    d = pd.Timestamp(config.holdout_date)
    for symbol in sorted(events['symbol'].unique()):
        for source in ('clustered','prior_day_extremes'):
            x=events[(events.symbol==symbol)&(events.source==source)]
            # A training outcome with exit on/after holdout is not training data.
            for sample, mask in [('training',pd.to_datetime(x.exit_date)<d),
                                 ('holdout',pd.to_datetime(x.signal_date)>=d)]:
                z=x[mask]
                if z.empty:
                    continue
                lo,hi=_month_block_ci(z,config)
                rows.append(dict(symbol=symbol,source=source,sample=sample,
                                 trades=len(z),win_rate=float(z.positive_forward_return.mean()),
                                 mean_gross_pct=100*float(z.gross_signed_return.mean()),
                                 mean_proxy_net_pct=100*float(z.proxy_net_signed_return.mean()),
                                 median_proxy_net_pct=100*float(z.proxy_net_signed_return.median()),
                                 ci95_low_pct=None if lo is None else lo*100,
                                 ci95_high_pct=None if hi is None else hi*100))
    return pd.DataFrame(rows)
