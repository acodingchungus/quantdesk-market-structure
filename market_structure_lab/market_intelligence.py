"""Point-in-time historical cross-asset market intelligence for QuantDesk v0.6.

This is descriptive research, NOT a forecast. Every number uses completed
sessions at or before the prior-session cutoff requested by the replay engine.
No fill-forward of missing sector data or inference of unavailable VIX values.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import math
import numpy as np
import pandas as pd
from .core import load_bars

CONTEXT_SYMBOLS = ('IWM', 'SMH', 'XLK', 'XLF', 'XLE', 'XLU', 'XLP',
                   'NVDA', 'AMD', 'MSFT', 'AAPL', 'META', 'XOM', 'CVX')


def _date(s):
    if not isinstance(s, str) or len(s) != 10:
        raise ValueError('Expected YYYY-MM-DD session date')
    dt = pd.Timestamp(s)
    if dt.strftime('%Y-%m-%d') != s:
        raise ValueError('Invalid session date')
    return dt


def _finite(v):
    return round(float(v), 8) if v is not None and math.isfinite(float(v)) else None


class MarketIntelligence:
    def __init__(self, data_dir: Path | str, daily: dict[str, pd.DataFrame]):
        self.data_dir = Path(data_dir)
        self.data = dict(daily)
        self.hashes = {}
        for symbol in CONTEXT_SYMBOLS:
            file = self.data_dir / 'context' / f'{symbol}.csv'
            if file.exists():
                self.data[symbol] = load_bars(str(file))
                self.hashes[symbol] = hashlib.sha256(file.read_bytes()).hexdigest()

    def _asset(self, symbol: str, cutoff: pd.Timestamp):
        if symbol not in self.data:
            return {'symbol': symbol, 'available': False, 'reason': 'No licensed local daily CSV'}
        df = self.data[symbol]
        # A historical cutoff must be applied BEFORE calculating statistics.
        past = df.loc[df['date'] <= cutoff, ['date', 'close']].copy()
        if past.empty:
            return {'symbol': symbol, 'available': False, 'reason': 'No completed observation by cutoff'}
        last_date = past.iloc[-1]['date']
        close = past['close'].astype(float).to_numpy()
        returns = np.diff(np.log(close))
        return {
            'symbol': symbol, 'available': True,
            'asof_date': last_date.strftime('%Y-%m-%d'),
            'stale': bool(last_date != cutoff),
            'close': _finite(close[-1]),
            'return_5d_pct': _finite(100 * (close[-1] / close[-6] - 1)) if len(close) >= 6 else None,
            'return_20d_pct': _finite(100 * (close[-1] / close[-21] - 1)) if len(close) >= 21 else None,
            'realized_vol_20d_pct': _finite(100 * float(np.std(returns[-20:], ddof=1)) * math.sqrt(252)) if len(returns) >= 20 else None,
            'daily_observations': len(close),
            'source': 'local_daily_csv',
        }

    def _correlation(self, first: str, second: str, cutoff: pd.Timestamp, days=20):
        if first not in self.data or second not in self.data:
            return None
        a, b = (self.data[x].loc[self.data[x]['date'] <= cutoff, ['date', 'close']]
                .set_index('date')['close'].astype(float) for x in (first, second))
        joined = pd.concat((a.rename('a'), b.rename('b')), axis=1, join='inner').dropna()
        # Require the joint last session to equal the cutoff: do not silently
        # compute a correlation on old observations and label it current.
        if len(joined) < days+1 or joined.index[-1] != cutoff:
            return None
        r = np.log(joined.iloc[-(days+1):]).diff().dropna()
        if len(r) != days or min(r['a'].std(), r['b'].std()) <= 1e-12:
            return None
        return _finite(r['a'].corr(r['b']))

    def _volatility_regime(self, cutoff: pd.Timestamp):
        if 'SPY' not in self.data:
            return 'unavailable'
        df = self.data['SPY'].loc[self.data['SPY']['date'] <= cutoff]
        close = df['close'].to_numpy(dtype=float)
        if len(close) < 82 or df.iloc[-1]['date'] != cutoff:
            return 'insufficient_history'
        r = np.diff(np.log(close))
        # Baseline of up to 60 rolling 20-return vol estimates KNOWN by cutoff.
        rolling = np.array([np.std(r[i-20:i], ddof=1) for i in range(len(r)-59, len(r)+1)])
        v = rolling[-1]
        lo, hi = np.quantile(rolling, [.25, .75])
        return 'elevated' if v > hi else 'muted' if v < lo else 'typical'

    def snapshot(self, cutoff_date: str, requested_session: str | None = None):
        cutoff = _date(cutoff_date)
        assets = {s: self._asset(s, cutoff) for s in ('SPY', 'QQQ')+CONTEXT_SYMBOLS}
        sp = assets['SPY']
        mom = sp.get('return_20d_pct') if sp.get('available') and not sp['stale'] else None
        momentum = ('insufficient_history' if mom is None else
                    'positive' if mom > 2 else 'negative' if mom < -2 else 'mixed')
        def relative(symbol: str):
            a = assets[symbol]
            if not a['available'] or a['stale'] or not sp.get('available') or sp['stale']:
                return None
            x, y = a.get('return_20d_pct'), sp.get('return_20d_pct')
            return _finite(x-y) if x is not None and y is not None else None
        strength = {s: relative(s) for s in ('QQQ', 'IWM','SMH','XLK','XLF','XLE','XLU','XLP')}
        out = {
            'requested_session': requested_session,
            'asof_completed_session': cutoff_date,
            'future_data_used': False,
            'methodology': '20 session log-return correlation, annualized sample volatility, arithmetic relative return; completed daily observations only',
            'assets': assets,
            'indicators': {'spy_qqq_corr_20d': self._correlation('SPY','QQQ',cutoff),
                           'relative_strength_20d_pp': strength},
            'regime': {'spy_20d_momentum': momentum,
                       'spy_volatility_vs_trailing_60': self._volatility_regime(cutoff)},
            'data_source_hashes': self.hashes,
            'warning': 'Descriptive, not predictive. Adjusted vs raw close bases may differ. Stale assets are not filled forward. No intraday VIX assumed.',
        }
        return out
