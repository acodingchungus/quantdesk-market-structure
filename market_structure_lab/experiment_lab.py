"""v0.7 exploratory, point-in-time ETF event study (not options trading).

Uses v0.1's already-confirmed end-of-session signals; permits an entry only
at the next completed session's OPEN. Does not claim any untouched holdout:
this project has repeatedly inspected earlier historical periods.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .core import Config, evaluate_symbol, load_bars

SOURCES = ('clustered', 'prior_day_extremes')
SPLITS = ('development', 'validation', 'retrospective_test')


@dataclass(frozen=True)
class StudySettings:
    roundtrip_cost_bps: float = 5.0
    train_fraction: float = .60
    validation_fraction: float = .20
    bootstrap_draws: int = 600
    null_draws: int = 1000
    seed: int = 2026

    def __post_init__(self):
        if (not math.isfinite(self.roundtrip_cost_bps) or
                not 0 <= self.roundtrip_cost_bps <= 100):
            raise ValueError('roundtrip_cost_bps must be finite and in [0,100]')
        if not (.5 <= self.train_fraction <= .75 and
                .1 <= self.validation_fraction <= .3 and
                self.train_fraction + self.validation_fraction <= .9):
            raise ValueError('Invalid chronological split fractions')
        if not (1 <= self.bootstrap_draws <= 5000 and 1 <= self.null_draws <= 5000):
            raise ValueError('Invalid resampling counts')


def _finite_percent(v):
    return float(v * 100) if v is not None and math.isfinite(float(v)) else None


def study_events(bars: pd.DataFrame, events: pd.DataFrame, symbol: str,
                 settings: StudySettings = StudySettings(),
                 source_sha256: str | None = None, lookback: int = 180) -> dict:
    """Score causal daily signals, with strictly disjoint outcome windows.

    Split by eligible daily trading sessions (not by rows of selected trades).
    A trade belongs to a split only when both its ENTRY and EXIT lie inside.
    Event generation and choices were previously investigated; the last split
    is a RETROSPECTIVE test and must not be described as an untouched holdout.
    """
    if symbol not in ('SPY', 'QQQ'):
        raise ValueError('Only SPY/QQQ daily research is supported in this release')
    if len(bars) < lookback + 50:
        raise ValueError('Too few daily observations for chronological research splits')
    dts = pd.to_datetime(bars['date'])
    if dts.isna().any() or dts.duplicated().any() or not dts.is_monotonic_increasing:
        raise ValueError('Daily dates must be complete, unique and chronological')
    dates = dts.dt.strftime('%Y-%m-%d').tolist()
    by_date = {day: i for i, day in enumerate(dates)}
    eligible = dates[lookback:]
    train_cut = int(len(eligible) * settings.train_fraction)
    valid_cut = int(len(eligible) * (settings.train_fraction + settings.validation_fraction))
    if not 0 < train_cut < valid_cut < len(eligible):
        raise ValueError('Insufficient sessions for three chronological samples')
    ranges = {
        'development': (lookback, lookback + train_cut - 1),
        'validation': (lookback + train_cut, lookback + valid_cut - 1),
        'retrospective_test': (lookback + valid_cut, len(dates) - 1),
    }
    rows = []
    for e in events.to_dict('records'):
        if e.get('symbol') != symbol or e.get('source') not in SOURCES:
            continue
        signal, entry, exit_ = (str(e[x]) for x in ('signal_date', 'entry_date', 'exit_date'))
        if any(x not in by_date for x in (signal, entry, exit_)):
            raise ValueError('Signal contains dates outside daily source')
        a, b, c = (by_date[x] for x in (signal, entry, exit_))
        if not (a < b <= c and int(e['signal_index']) == a and
                str(e['level_asof_date']) < signal):
            raise ValueError('Event violates point-in-time entry or level availability')
        entry_px = float(bars.iloc[b]['open'])
        exit_px = float(bars.iloc[c]['close'])
        if (not math.isclose(entry_px, float(e['entry_price']), rel_tol=1e-8) or
                not math.isclose(exit_px, float(e['exit_price']), rel_tol=1e-8)):
            raise ValueError('Event prices disagree with source OHLCV')
        direction = int(e['direction'])
        if direction not in (-1, 1):
            raise ValueError('Event direction must be +1 or -1')
        span = bars.iloc[b:c+1]
        # These extremal paths are descriptive, NOT simultaneous fills/stops.
        max_hi = float(span['high'].max())
        min_lo = float(span['low'].min())
        mfe = ((max_hi-entry_px) if direction == 1 else (entry_px-min_lo)) / entry_px
        mae = ((min_lo-entry_px) if direction == 1 else (entry_px-max_hi)) / entry_px
        gross = direction * (exit_px-entry_px) / entry_px
        split = next((name for name,(lo,hi) in ranges.items() if lo <= b <= c <= hi), None)
        rows.append({
            'symbol': symbol, 'source': e['source'], 'signal_date': signal,
            'entry_date': entry, 'exit_date': exit_, 'direction': direction,
            'level_asof_date': str(e['level_asof_date']),
            'entry_price': entry_px, 'exit_price': exit_px,
            'underlying_return': (exit_px-entry_px)/entry_px,
            'gross_signed_return': gross,
            'net_proxy_return': gross - settings.roundtrip_cost_bps / 10000.0,
            'mfe': max(0., mfe), 'mae': min(0., mae),
            'partition': split or 'PURGED_BOUNDARY',
        })
    table = pd.DataFrame(rows)
    results = []
    for source in SOURCES:
        for part in SPLITS:
            selected = table[(table.source == source) & (table.partition == part)] if len(table) else pd.DataFrame()
            n = len(selected)
            row = {'source': source, 'sample': part, 'trades': n,
                   'mean_net_pct': None, 'win_rate_pct': None,
                   'mean_mfe_pct': None, 'mean_mae_pct': None,
                   'ci95_low_pct': None, 'ci95_high_pct': None,
                   'random_direction_null_p': None,
                   'months': 0}
            if n:
                row.update(mean_net_pct=_finite_percent(selected.net_proxy_return.mean()),
                           win_rate_pct=float((selected.net_proxy_return > 0).mean()*100),
                           mean_mfe_pct=_finite_percent(selected.mfe.mean()),
                           mean_mae_pct=_finite_percent(selected.mae.mean()))
                months = selected.exit_date.str[:7]
                groups = [selected.loc[months==month, 'net_proxy_return'].to_numpy(dtype=float)
                          for month in sorted(months.unique())]
                row['months'] = len(groups)
                # Correlated observations remain together within exit-month blocks.
                if n >= 8 and len(groups) >= 4:
                    seed = settings.seed + SOURCES.index(source)*31 + SPLITS.index(part)*113
                    rng = np.random.default_rng(seed)
                    means = [np.concatenate([groups[j] for j in rng.integers(0, len(groups), size=len(groups))]).mean()
                             for _ in range(settings.bootstrap_draws)]
                    row['ci95_low_pct'] = _finite_percent(np.quantile(means, .025))
                    row['ci95_high_pct'] = _finite_percent(np.quantile(means, .975))
                # Random-direction diagnostic is paired on identical entry/exit windows.
                # It measures directional alignment ONLY. Not a significance claim about
                # level detection, nor robust to researcher selection/multiple trials.
                if n >= 5:
                    rng = np.random.default_rng(settings.seed + 901 + SOURCES.index(source)*37 + SPLITS.index(part)*97)
                    unsigned = selected.underlying_return.to_numpy(dtype=float)
                    observed = float(selected.net_proxy_return.mean())
                    simulations = np.mean(rng.choice([-1.,1.],size=(settings.null_draws,n))*unsigned[None,:],axis=1)
                    simulations -= settings.roundtrip_cost_bps / 10000.
                    row['random_direction_null_p'] = float((1+np.count_nonzero(simulations >= observed))/(settings.null_draws+1))
            results.append(row)
    hidden = int((table.partition == 'PURGED_BOUNDARY').sum()) if len(table) else 0
    return {
        'version':'0.7.0', 'research_only':True, 'symbol':symbol,
        'data_start':dates[0], 'data_end':dates[-1],
        'source_sha256': source_sha256,
        'settings':asdict(settings), 'signal_method':'confirmed daily t close; entry next daily open; exit t + fixed horizon close',
        'split_sessions':{name:{'first':dates[a], 'last':dates[b], 'sessions':b-a+1}
                          for name,(a,b) in ranges.items()},
        'purged_boundary_events':hidden, 'candidate_events':len(table),
        'results':results,
        'events': [dict(r, **{'gross_signed_return': float(r['gross_signed_return'])}) for r in rows],
        'warnings':[
            'All periods are retrospectively examined; the final partition is NOT an untouched holdout.',
            'Only daily ETF underlying returns; hypothetical flat round-trip bps, not options P&L or executable fills.',
            'MFE and MAE are path extrema known after exit; not available at entry and not proof of attainable stops/targets.',
            'Random-direction diagnostic holds event dates fixed; it does not establish level quality or correct for research selection.',
            'No tick-volume-profile confluence or raw/adjusted price matching is assumed. These require a separate audit.',
            'No walk-forward model tuning is performed; splits support chronological evaluation of pre-existing fixed parameters.',
        ],
    }


def main():
    p=argparse.ArgumentParser(description='v0.7 read-only exploratory daily ETF event study; NO ORDERS')
    p.add_argument('--data-dir',default='data')
    p.add_argument('--out',default='outputs/v07_research')
    p.add_argument('--cost-bps',type=float,default=5.)
    args=p.parse_args()
    settings=StudySettings(roundtrip_cost_bps=args.cost_bps)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    for symbol in ('SPY','QQQ'):
        filename=Path(args.data_dir)/(symbol+'.csv')
        bars=load_bars(str(filename))
        cfg=Config()
        _, events=evaluate_symbol(bars,symbol,cfg)
        data=study_events(bars,events,symbol,settings,hashlib.sha256(filename.read_bytes()).hexdigest(),cfg.lookback)
        (out/f'{symbol}_study.json').write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')
        pd.DataFrame(data['events']).to_csv(out/f'{symbol}_events.csv',index=False)
        print(symbol,'events',data['candidate_events'],'purged',data['purged_boundary_events'],'->',out)
    print('RESEARCH ONLY. Historical partitions previously examined. No options P&L or validated alpha.')


if __name__=='__main__':
    main()
