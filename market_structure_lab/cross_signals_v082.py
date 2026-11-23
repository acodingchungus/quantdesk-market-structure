"""v0.8.2: predetermined, causal cross-asset research factors; NO orders.

Only completed daily CSV observations feed the factor. Market close t is known
when the factor for session t is computed; the associated v0.7 KDE event enters
no earlier than session t+1. A regression for t is fitted through t-1 only.
This is an exploratory historical comparison, not a trained predictive model.
"""
from __future__ import annotations

from collections import OrderedDict
import math
from typing import Mapping

import numpy as np
import pandas as pd

PEERS = ('NVDA', 'SMH', 'XLK', 'IWM')
WINDOW = 20
MIN_PEERS = 2
RESIDUAL_THRESHOLD_PP = 0.10  # fixed before evaluating outcomes, no calibration
PARTITIONS = ('development', 'validation', 'retrospective_test')
STATES = ('confirmed', 'contradicted', 'mixed', 'unavailable')


def _daily_closes(frame: pd.DataFrame | None) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype='float64')
    if 'date' not in frame or 'close' not in frame:
        raise ValueError('Daily inputs require date and close')
    dates = pd.DatetimeIndex(pd.to_datetime(frame['date']))
    values = pd.to_numeric(frame['close'], errors='raise').to_numpy(dtype=float)
    if dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing:
        raise ValueError('Daily observations must be ordered and unique')
    if dates.tz is not None or any(d != d.normalize() for d in dates):
        raise ValueError('Daily dates must be timezone-naive completed session dates')
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('Invalid daily close')
    return pd.Series(values, index=dates, dtype='float64')


def _corr(a: np.ndarray, b: np.ndarray):
    if len(a) < 4 or np.std(a) <= 1e-12 or np.std(b) <= 1e-12:
        return None
    value = float(np.corrcoef(a, b)[0, 1])
    return round(value, 8) if math.isfinite(value) else None


class CrossSignalResearch:
    """Read-only, deterministic factor observations and retrospective KDE study."""

    def __init__(self, daily: Mapping[str, pd.DataFrame], *, window=WINDOW, peers=PEERS):
        if not isinstance(window, int) or not 10 <= window <= 120:
            raise ValueError('window must be an integer 10–120')
        if len(peers) < MIN_PEERS or len(peers) > 12 or len(set(peers)) != len(peers):
            raise ValueError('Require 2–12 distinct research peers')
        self.window = window
        self.peers = tuple(peers)
        self.closes = {sym: _daily_closes(df) for sym, df in daily.items()}
        self._cache = OrderedDict()

    def snapshot(self, *, asof: str, target='QQQ', direction=1):
        """End-of-session t feature available before next open. No outcomes."""
        if target not in ('SPY', 'QQQ'):
            raise ValueError('Target must be SPY or QQQ')
        if direction not in (-1, 1):
            raise ValueError('direction must be -1 or +1')
        date = pd.Timestamp(asof)
        if (not isinstance(asof, str) or date.tzinfo is not None or
                date.strftime('%Y-%m-%d') != asof):
            raise ValueError('asof must be a completed YYYY-MM-DD date')
        key = (target, asof, direction)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        base = self.closes.get(target, pd.Series(dtype='float64'))
        candidates = []
        if date not in base.index:
            reason = 'target_session_unavailable'
        else:
            j = base.index.get_loc(date)
            if j < self.window + 1:
                reason = 'insufficient_prior_sessions'
            else:
                reason = None
                # Fit only on returns t-window-1 ... t-1. The target t return
                # is used only after fitted coefficients are frozen.
                needed = base.index[j-self.window-1:j+1]
                hist = np.diff(np.log(base.loc[needed[:-1]].to_numpy(dtype=float)))
                now_target = math.log(float(base.loc[needed[-1]])/float(base.loc[needed[-2]]))
                for sym in self.peers:
                    if sym == target:
                        continue
                    other = self.closes.get(sym)
                    if other is None or not needed.isin(other.index).all():
                        candidates.append({'symbol': sym, 'available': False,
                                           'reason': 'missing_or_unaligned_session'})
                        continue
                    values = other.loc[needed].to_numpy(dtype=float)
                    peer_hist = np.diff(np.log(values[:-1]))
                    v = float(np.var(hist))
                    if v <= 1e-20 or np.std(peer_hist) <= 1e-12:
                        candidates.append({'symbol': sym, 'available': False,
                                           'reason': 'insufficient_return_variation'})
                        continue
                    beta = float(np.mean((hist-hist.mean())*(peer_hist-peer_hist.mean()))/v)
                    alpha = float(peer_hist.mean() - beta*hist.mean())
                    peer_now = float(math.log(values[-1]/values[-2]))
                    residual_pp = 100*(peer_now-alpha-beta*now_target)
                    candidates.append({
                        'symbol': sym, 'available': True, 'last_completed_at': asof,
                        'beta_prior': round(beta, 8),
                        'historical_corr_prior': _corr(hist, peer_hist),
                        # Historical directional diagnostic: peer yesterday vs
                        # target today, only through t-1 (no current/future label).
                        'lead_lag_corr_prior': _corr(peer_hist[:-1], hist[1:]),
                        'residual_pp': round(residual_pp, 8),
                        'supports_direction': bool(direction*residual_pp > 0),
                    })
        available = [x for x in candidates if x.get('available')]
        state = 'unavailable'
        mean_signed = None
        breadth = None
        if reason is None and len(available) >= MIN_PEERS:
            signed = [direction*float(x['residual_pp']) for x in available]
            mean_signed = round(float(np.mean(signed)), 8)
            breadth = round(sum(x > 0 for x in signed)/len(signed), 8)
            if mean_signed >= RESIDUAL_THRESHOLD_PP and breadth >= 0.6:
                state = 'confirmed'
            elif mean_signed <= -RESIDUAL_THRESHOLD_PP and breadth <= 0.4:
                state = 'contradicted'
            else:
                state = 'mixed'
        result = {
            'version': '0.8.2', 'asof_completed_session': asof, 'target': target,
            'direction': direction, 'signal_available_at': 'end_of_session_close',
            'earliest_hypothetical_entry': 'next_session_open',
            'window_prior_returns': self.window, 'required_peers': MIN_PEERS,
            'residual_threshold_pp': RESIDUAL_THRESHOLD_PP,
            'state': state, 'coverage': len(available),
            'mean_directional_residual_pp': mean_signed,
            'confirming_peer_fraction': breadth, 'peers': candidates,
            'reason': reason if reason else ('insufficient_aligned_peers' if state == 'unavailable' else None),
            'future_data_used': False, 'research_only': True, 'no_orders': True,
            'warning': ('Prior-session beta/alpha fit; current-day residual uses only completed t close. '
                        'Historical lead/lag correlation is descriptive, not causal or a forecast. '
                        'Absence of synchronized peer sessions is never forward-filled.'),
        }
        self._cache[key] = result
        if len(self._cache) > 512:
            self._cache.popitem(last=False)
        return result

    def evaluate(self, *, target: str, study: dict):
        """Group validated v0.7 KDE outcomes by predeclared as-of factor state.

        Accept ONLY the existing study_events output: it validates entry/exit
        prices, chronology, partition boundaries, and cost assumptions.
        Results are retrospective, previously examined, and NOT holdout alpha.
        """
        if target not in ('SPY', 'QQQ') or study.get('symbol') != target:
            raise ValueError('Target/study mismatch')
        if not study.get('research_only') or not isinstance(study.get('events'), list):
            raise ValueError('Requires validated retrospective study events')
        rows = []
        for e in study['events']:
            if e['source'] != 'clustered':
                continue  # Keep exactly the existing KDE event sample.
            if e['symbol'] != target or e['partition'] not in (*PARTITIONS, 'PURGED_BOUNDARY'):
                raise ValueError('Unexpected event provenance/partition')
            if not str(e['signal_date']) < str(e['entry_date']) <= str(e['exit_date']):
                raise ValueError('Outcome used before causal signal')
            if e['partition'] == 'PURGED_BOUNDARY':
                continue
            factor = self.snapshot(asof=str(e['signal_date']), target=target,
                                   direction=int(e['direction']))
            rows.append({
                'signal_date': e['signal_date'], 'entry_date': e['entry_date'],
                'exit_date': e['exit_date'], 'partition': e['partition'],
                'direction': int(e['direction']), 'state': factor['state'],
                'peers_available': factor['coverage'],
                'mean_directional_residual_pp': factor['mean_directional_residual_pp'],
                'net_proxy_return': float(e['net_proxy_return']),
            })
        summaries = []
        for partition in PARTITIONS:
            all_rows = [x for x in rows if x['partition'] == partition]
            baseline = self._stats(all_rows)
            groups = {status: self._stats([x for x in all_rows if x['state'] == status])
                      for status in STATES}
            confirmed = groups['confirmed']
            delta = (round(confirmed['mean_net_pct']-baseline['mean_net_pct'], 8)
                     if confirmed['mean_net_pct'] is not None and baseline['mean_net_pct'] is not None
                     else None)
            summaries.append({
                'partition': partition, 'baseline': baseline, 'groups': groups,
                'confirmed_minus_baseline_pp': delta,
                'coverage_events': len(all_rows)-groups['unavailable']['events'],
            })
        return {
            'version':'0.8.2', 'target':target, 'research_only':True, 'no_orders':True,
            'signal_source':'clustered', 'studied_events':len(rows),
            'purged_boundary_events': study.get('purged_boundary_events'),
            'settings':study.get('settings'), 'split_sessions':study.get('split_sessions'),
            'prior_window':self.window, 'peers':list(self.peers),
            'method':'Fixed-sign directional peer residual against prior-20-return market beta; no tuning; next-session-open KDE event outcome from v0.7',
            'comparison':summaries, 'events':rows,
            'future_data_used_for_factors':False,
            'warnings':[
                'ALL historical periods are previously examined. The final partition is retrospective, NOT an untouched holdout.',
                'Subgroup differences can be noise, selection bias or market regime confounding; no significance or alpha claim.',
                'Underlying ETF daily OHLCV only; fixed roundtrip bps proxy is not executable options pricing or fills.',
                'Peer residuals are computed from previous-window fits and signal-day completed closes; missing tickers are never filled.',
                'Prior-day extremes baseline remains available separately in the original v0.7 study.',
            ],
        }

    @staticmethod
    def _stats(rows):
        if not rows:
            return {'events':0,'mean_net_pct':None,'win_rate_pct':None}
        returns = np.array([r['net_proxy_return'] for r in rows], dtype=float)
        if not np.isfinite(returns).all():
            raise ValueError('Invalid study return')
        return {'events':len(rows),
                'mean_net_pct':round(float(returns.mean()*100),8),
                'win_rate_pct':round(float(np.mean(returns>0)*100),8)}
