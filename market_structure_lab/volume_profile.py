"""QuantDesk v0.5: executed TRADE-tick volume-at-price, strictly point-in-time.

This module intentionally does NOT fabricate volume profile from minute OHLCV,
classify aggressor side, infer resting liquidity, or reconstruct Level II depth.
The source is a CSV of executed trades: timestamp,price,size; timestamps must
include UTC offsets and be strictly ordered (equal timestamps are permitted).
Only US regular-hours trades are supported in the first implementation.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path
import hashlib
import math
import re

import numpy as np
import pandas as pd

MARKET_ZONE = 'America/New_York'
TIMESTAMP_RE = re.compile(r'(?:Z|[+-]\d{2}:\d{2})$', re.I)
REQUIRED = ('timestamp', 'price', 'size')
BIN_SIZES = ('0.01', '0.05', '0.10', '0.25', '0.50', '1.00')
MAX_ROWS = 2_000_000
MAX_BINS = 3_000


def load_trades(path: str | Path) -> pd.DataFrame:
    """Load user-supplied executed prints, rejecting ambiguous/invalid inputs.

    The output timestamps are UTC; session labels are in US Eastern time.
    We intentionally preserve duplicate timestamps and trade records because
    prints at the same instant can be distinct executions.
    """
    path = Path(path)
    raw = pd.read_csv(path, dtype={'timestamp': 'string', 'price': 'string', 'size': 'string'})
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    if not set(REQUIRED).issubset(raw.columns):
        raise ValueError(f'{path}: expected timestamp,price,size for executed trades')
    if raw.empty or len(raw) > MAX_ROWS:
        raise ValueError(f'{path}: expected 1..{MAX_ROWS:,} rows; split larger data into batches')
    df = raw[list(REQUIRED)].copy()
    stamps = df['timestamp'].str.strip()
    if stamps.isna().any() or not stamps.map(lambda v: bool(TIMESTAMP_RE.search(v))).all():
        raise ValueError(f'{path}: timestamp must include Z or an explicit UTC offset')
    try:
        utc = pd.to_datetime(stamps, utc=True, format='ISO8601', errors='raise')
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{path}: invalid trade timestamp') from exc
    if utc.isna().any() or not utc.is_monotonic_increasing:
        raise ValueError(f'{path}: timestamps must be chronological; equal timestamps permitted')
    local = utc.dt.tz_convert(MARKET_ZONE)
    second_of_day = local.dt.hour*3600 + local.dt.minute*60 + local.dt.second + local.dt.microsecond/1e6
    if ((second_of_day < 9*3600+30*60) | (second_of_day > 16*3600) |
            (local.dt.dayofweek > 4)).any():
        raise ValueError(f'{path}: only US weekday 09:30:00 <= trade time <= 16:00 ET supported')
    exact_price_text = df['price'].str.strip()
    prices = pd.to_numeric(df['price'], errors='coerce')
    sizes = pd.to_numeric(df['size'], errors='coerce')
    if (prices.isna().any() or sizes.isna().any() or
        not np.isfinite(prices.to_numpy(dtype=float)).all() or
        not np.isfinite(sizes.to_numpy(dtype=float)).all() or
        (prices <= 0).any() or (sizes <= 0).any() or
        (sizes > 10_000_000).any() or (sizes != np.floor(sizes)).any()):
        raise ValueError(f'{path}: prices must be finite >0 and trade sizes must be positive integer shares')
    if (prices > 1_000_000).any():
        raise ValueError(f'{path}: unrealistic price > $1,000,000')
    df['timestamp'] = utc.reset_index(drop=True)
    # Retain exact supplied price strings to avoid float errors at bin edges.
    df['price'] = prices.to_numpy(dtype=float)
    df['price_text'] = exact_price_text.to_numpy()
    df['size'] = sizes.to_numpy(dtype='int64')
    df['session'] = local.dt.strftime('%Y-%m-%d').to_numpy()
    df.attrs['is_synthetic_demo'] = 'source_label' in raw and raw['source_label'].astype(str).str.upper().eq('SYNTHETIC_DEMO').any()
    return df.reset_index(drop=True)


def _step(value: str) -> Decimal:
    if value not in BIN_SIZES:
        raise ValueError(f'price_bin must be one of: {", ".join(BIN_SIZES)}')
    return Decimal(value)


def build_profile(trades: pd.DataFrame, *, asof: pd.Timestamp | str | None = None,
                  price_bin: str = '0.05', value_area: float = .70) -> dict:
    """Aggregate executed share volume by price band, as of a historical instant.

    POC = bin of maximum volume (ties: closest to VWAP then lower bin).
    Value area expands contiguously from POC by choosing the higher-volume
    adjacent band until >= target fraction. This is *one reproducible convention*,
    not an exchange-standard calculation. HVN/LVN are local-extrema heuristics.
    """
    step = _step(price_bin)
    if not (isinstance(value_area, (float,int)) and math.isfinite(value_area) and .5 <= value_area <= .9):
        raise ValueError('value_area must be in [0.50,0.90]')
    if asof is not None:
        cutoff = pd.Timestamp(asof)
        if cutoff.tzinfo is None:
            raise ValueError('asof timestamp must have timezone offset')
        cutoff = cutoff.tz_convert('UTC')
        trades = trades.loc[trades['timestamp'] <= cutoff]
    if trades.empty:
        return {'available': False, 'reason': 'No executed trade ticks observed at/before this replay point'}
    if trades['session'].nunique() != 1:
        raise ValueError('build_profile expects trades from one trading session')
    prices = trades['price'].to_numpy(dtype=float)
    sizes = trades['size'].to_numpy(dtype=np.int64)
    # Decimal rounding based on canonical price text avoids e.g. 1.005 / 0.05 errors.
    price_texts = trades['price_text'] if 'price_text' in trades else [str(x) for x in prices]
    try:
        bin_ids = np.fromiter((int((Decimal(str(p)) / step).to_integral_value(rounding=ROUND_FLOOR))
                               for p in price_texts), dtype=np.int64, count=len(trades))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Invalid price for volume binning') from exc
    return _profile_from_exact_bins(
        prices, sizes, bin_ids, session=str(trades['session'].iloc[-1]),
        last_timestamp=trades['timestamp'].iloc[-1], price_bin=price_bin,
        step=step, value_area=value_area)


def _profile_from_exact_bins(prices: np.ndarray, sizes: np.ndarray, bin_ids: np.ndarray,
                             *, session: str, last_timestamp: pd.Timestamp,
                             price_bin: str, step: Decimal, value_area: float) -> dict:
    """Shared accounting for ordinary and indexed profiles; never approximate prices."""
    bottom, top = int(bin_ids.min()), int(bin_ids.max())
    count = top-bottom+1
    if count > MAX_BINS:
        raise ValueError(f'Price range spans {count:,} bins; choose a wider price_bin (max {MAX_BINS})')
    vol = np.bincount(bin_ids-bottom, weights=sizes.astype(float), minlength=count)
    total = int(sizes.sum())
    vwap = float(np.dot(prices, sizes.astype(float)) / total)
    center_values = (np.arange(bottom, top+1)+.5)*float(step)
    maxvol = float(vol.max())
    contenders = np.flatnonzero(vol == maxvol)
    poc = int(min(contenders, key=lambda k: (abs(center_values[k] - vwap), center_values[k])))
    left = right = int(poc)
    running = float(vol[poc]); target = total*float(value_area)
    while running + 1e-9 < target and (left > 0 or right < count-1):
        lv = float(vol[left-1]) if left > 0 else -1
        rv = float(vol[right+1]) if right < count-1 else -1
        if rv > lv: right += 1; running += float(vol[right])
        else: left -= 1; running += float(vol[left])
    # Only local extrema of observed/nonzero bins; no unearned 'liquidity' claims.
    hvn = {k for k in range(1, count-1) if vol[k] >= vol[k-1] and vol[k] > vol[k+1] and vol[k] >= .5*maxvol}
    lvn = {k for k in range(1, count-1) if vol[k] > 0 and vol[k] < vol[k-1] and vol[k] <= vol[k+1] and vol[k] <= .35*maxvol}
    asof_stamp = last_timestamp.isoformat()
    bins = [{'low': round(float(Decimal(bottom+k)*step), 6),
             'high': round(float(Decimal(bottom+k+1)*step), 6),
             'volume': int(round(v)),
             'pct': round(float(v/total*100), 4),
             'poc': k == poc, 'in_value_area': left <= k <= right,
             'node': 'HVN' if k in hvn else ('LVN' if k in lvn else '')}
            for k, v in enumerate(vol)]
    return {
        'available': True, 'kind': 'EXECUTED_TRADES_VOLUME_AT_PRICE',
        'session': str(session),
        'price_bin': price_bin, 'value_area_target': value_area,
        'volume_shares': total, 'trade_prints': len(prices),
        'observed_through': asof_stamp,
        'poc_low': bins[poc]['low'], 'poc_high': bins[poc]['high'],
        'val': bins[left]['low'], 'vah': bins[right]['high'],
        'value_area_achieved': round(running/total, 6),
        'vwap': round(vwap, 6),
        'bins': bins,
        'disclaimer': 'Executed share volume at price, NOT displayed/resting liquidity, order-book depth, trade aggressor or options fills. HVN/LVN are experimental local-extrema labels.',
    }


class ProfileIndex:
    """Immutable, session-local exact bin cache for repeated historical seeks.

    Price text -> Decimal FLOOR binning happens once per price-bin setting.
    Every requested historical prefix still uses the *same* profile arithmetic
    as build_profile. No future trades enter a prefix's aggregate.
    """

    def __init__(self, trades: pd.DataFrame):
        if trades.empty or trades['session'].nunique() != 1:
            raise ValueError('ProfileIndex expects one nonempty trading session')
        if not trades['timestamp'].is_monotonic_increasing:
            raise ValueError('ProfileIndex needs sorted trade timestamps')
        self.session = str(trades['session'].iloc[0])
        self._timestamps = trades['timestamp'].array.asi8.copy()
        self._prices = trades['price'].to_numpy(dtype=float, copy=True)
        self._sizes = trades['size'].to_numpy(dtype=np.int64, copy=True)
        if 'price_text' in trades:
            self._price_texts = trades['price_text'].astype(str).to_numpy(copy=True)
        else:
            self._price_texts = np.array([str(v) for v in self._prices])
        self._bins: dict[str, np.ndarray] = {}

    def evaluate(self, *, asof: pd.Timestamp | str | None = None,
                 price_bin: str = '0.05', value_area: float = .70) -> dict:
        step = _step(price_bin)
        if not (isinstance(value_area, (float,int)) and math.isfinite(value_area) and .5 <= value_area <= .9):
            raise ValueError('value_area must be in [0.50,0.90]')
        if asof is None:
            end = len(self._prices)
        else:
            cutoff = pd.Timestamp(asof)
            if cutoff.tzinfo is None:
                raise ValueError('asof timestamp must have timezone offset')
            end = int(np.searchsorted(self._timestamps, cutoff.tz_convert('UTC').value, side='right'))
        if end == 0:
            return {'available': False, 'reason': 'No executed trade ticks observed at/before this replay point'}
        if price_bin not in self._bins:
            try:
                self._bins[price_bin] = np.fromiter(
                    (int((Decimal(str(p)) / step).to_integral_value(rounding=ROUND_FLOOR))
                     for p in self._price_texts), dtype=np.int64, count=len(self._prices))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError('Invalid price for volume binning') from exc
        return _profile_from_exact_bins(
            self._prices[:end], self._sizes[:end], self._bins[price_bin][:end],
            session=self.session, last_timestamp=pd.Timestamp(self._timestamps[end-1], tz='UTC'),
            price_bin=price_bin, step=step, value_area=value_area)


def provenance(path: str | Path, trades: pd.DataFrame) -> dict:
    path = Path(path)
    return {
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'trade_prints': int(len(trades)),
        'sessions': int(trades['session'].nunique()),
        'first_timestamp': trades['timestamp'].iloc[0].isoformat(),
        'last_timestamp': trades['timestamp'].iloc[-1].isoformat(),
        'source': 'user-supplied executed trade prints; venue/conditions not independently verified',
        'is_synthetic_demo': bool(trades.attrs.get('is_synthetic_demo', False)),
    }
