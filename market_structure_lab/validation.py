"""Exploratory matching, uncertainty and descriptive feature reports.

All baseline outcomes are underlying ETF next-open -> third-close directional
proxies. No historical options pricing, and no claim of causal identification.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .core import Config, true_range_and_atr


def _eligible_sample(signal_date: str, exit_date: str, holdout_date: str) -> str | None:
    if exit_date < holdout_date:
        return 'training'
    if signal_date >= holdout_date:
        return 'holdout'
    return None


def _daily_features(bars: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    rows = []
    for t in range(cfg.lookback, len(bars)-cfg.forward_bars):
        history = bars.iloc[:t]
        atr = true_range_and_atr(history, cfg.atr_period)
        prev_close = float(history.iloc[-1].close)
        trailing = float(prev_close/history.iloc[-11].close-1) if len(history)>11 else 0.0
        enter = float(bars.iloc[t+1].open)
        leave = float(bars.iloc[t+cfg.forward_bars].close)
        rows.append({'index': t, 'date': str(pd.Timestamp(bars.iloc[t].date).date()),
                     'exit_date': str(pd.Timestamp(bars.iloc[t+cfg.forward_bars].date).date()),
                     'atr_pct': atr/prev_close, 'trailing_10_return': trailing,
                     'long_proxy': (leave-enter)/enter})
    return pd.DataFrame(rows)


def matched_controls(bars: pd.DataFrame, events: pd.DataFrame, symbol: str, cfg: Config,
                     max_lookback_days: int = 126, k: int = 5) -> pd.DataFrame:
    """Each event uses at most k *earlier*, same-sample, non-event control days.

    Matching uses only pre-signal ATR/price and preceding 10-bar return;
    outcome fields are accessed only AFTER candidate selection. This is a
    retrospective non-event baseline, not a randomized/causal counterfactual.
    """
    if k < 1 or max_lookback_days < 1:
        raise ValueError('k and lookback must be positive')
    if events.empty:
        return pd.DataFrame()
    features = _daily_features(bars, cfg)
    feature_by_idx = features.set_index('index')
    output = []
    for source in ('clustered', 'prior_day_extremes'):
        model_events = events[(events.symbol == symbol) & (events.source == source)]
        excluded = set(model_events.signal_index.astype(int))
        for event in model_events.itertuples(index=False):
            idx = int(event.signal_index)
            date = str(event.signal_date)
            exit_date = str(event.exit_date)
            sample = _eligible_sample(date, exit_date, cfg.holdout_date)
            if sample is None or idx not in feature_by_idx.index:
                continue
            row = feature_by_idx.loc[idx]
            possible = features[(features['index'] < idx-cfg.forward_bars) &
                                (features['index'] >= idx-max_lookback_days)].copy()
            possible = possible[~possible['index'].isin(excluded)]
            possible = possible[[
                _eligible_sample(str(r.date), str(r.exit_date), cfg.holdout_date)==sample
                for r in possible.itertuples(index=False)]]
            if possible.empty:
                continue
            # Fixed, explicit normalization—not fitted to either evaluation sample.
            possible['distance'] = ((possible.atr_pct-row.atr_pct)/.012)**2 + \
                ((possible.trailing_10_return-row.trailing_10_return)/.04)**2 + \
                .05*((idx-possible['index'])/max_lookback_days)**2
            choices = possible.nsmallest(k, 'distance')
            baseline = float((int(event.direction)*choices.long_proxy - cfg.roundtrip_cost_bps/10000).mean())
            actual = float(event.proxy_net_signed_return)
            output.append({
                'symbol': symbol, 'source': source, 'sample': sample,
                'signal_date': date, 'signal_index': idx, 'direction': int(event.direction),
                'level_price': float(event.level_price), 'level_pivots': int(event.level_pivots),
                'event_net_return': actual, 'control_mean_net_return': baseline,
                'difference': actual-baseline, 'control_count': int(len(choices)),
                'control_dates': ';'.join(choices.date.tolist()),
                'mean_matching_distance': float(choices.distance.mean()),
            })
    return pd.DataFrame(output, columns=[
        'symbol','source','sample','signal_date','signal_index','direction','level_price',
        'level_pivots','event_net_return','control_mean_net_return','difference',
        'control_count','control_dates','mean_matching_distance'])


def _block_stats(frame: pd.DataFrame, cfg: Config, reps: int = 1500):
    """Whole signal-month bootstrap + symmetric block sign-flip null test.

    Note: intervals are descriptive and not an independent validation of edge.
    """
    months = pd.to_datetime(frame.signal_date).dt.to_period('M').astype(str)
    blocks = [frame.loc[months==m,'difference'].to_numpy(float) for m in sorted(months.unique())]
    if len(blocks) < 4 or len(frame) < 8:
        return None, None, None, len(blocks)
    rng = np.random.default_rng(cfg.seed + len(frame))
    samples = np.empty(reps)
    nulls = np.empty(reps)
    for i in range(reps):
        picked = [blocks[j] for j in rng.integers(0,len(blocks),len(blocks))]
        samples[i] = float(np.concatenate(picked).mean())
        signs = rng.choice([-1,1],size=len(blocks))
        nulls[i] = float(np.concatenate([b*s for b,s in zip(blocks,signs)]).mean())
    observed = abs(float(frame.difference.mean()))
    pval = float((1+np.sum(np.abs(nulls)>=observed))/(reps+1))
    return float(np.quantile(samples,.025)),float(np.quantile(samples,.975)),pval,len(blocks)


def _bh_fdr(pvalues: list[float | None]) -> list[float | None]:
    """Benjamini-Hochberg q-values for all reported non-null tests."""
    ids = [i for i,p in enumerate(pvalues) if p is not None and np.isfinite(p)]
    if not ids:
        return [None]*len(pvalues)
    order = sorted(ids,key=lambda i:pvalues[i])
    q = [None]*len(pvalues)
    best = 1.0
    m = len(order)
    for rank in range(m-1,-1,-1):
        i = order[rank]
        best = min(best,float(pvalues[i])*m/(rank+1))
        q[i] = best
    return q


def summarize_matched(matches: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    cols = ['symbol','source','sample','matched_events','mean_event_net_pct',
            'mean_control_net_pct','mean_difference_pct','ci95_low_pct',
            'ci95_high_pct','block_signflip_p','bh_fdr_q','independent_month_blocks']
    if matches.empty:
        return pd.DataFrame(columns=cols)
    results = []
    for (sym,src,sample), z in matches.groupby(['symbol','source','sample'],sort=True):
        lo,hi,p,nb = _block_stats(z,cfg)
        results.append({'symbol': sym, 'source':src, 'sample':sample,
                        'matched_events':int(len(z)),
                        'mean_event_net_pct':100*float(z.event_net_return.mean()),
                        'mean_control_net_pct':100*float(z.control_mean_net_return.mean()),
                        'mean_difference_pct':100*float(z.difference.mean()),
                        'ci95_low_pct':None if lo is None else 100*lo,
                        'ci95_high_pct':None if hi is None else 100*hi,
                        'block_signflip_p':p,'independent_month_blocks':nb})
    qs=_bh_fdr([r['block_signflip_p'] for r in results])
    for r,q in zip(results,qs):
        r['bh_fdr_q']=q
    return pd.DataFrame(results)[cols]


def summarize_reactions(reactions: pd.DataFrame) -> pd.DataFrame:
    cols=['symbol','type','pivot_bucket','count']
    if reactions.empty:
        return pd.DataFrame(columns=cols)
    out=reactions.copy()
    out['pivot_bucket']=np.where(out['pivot_count']>=4,'4+ pivots','2–3 pivots')
    return out.groupby(['symbol','type','pivot_bucket'],as_index=False).size().rename(columns={'size':'count'})[cols]
