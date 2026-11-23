"""v0.8.3 offline reproducible decision/study runner. No network or orders.

Commands:
  init-manifest (provenance placeholders, NEVER labels unknown feeds as verified)
  audit (exchange sessions / historical source provenance)
  study (requires a passing audit, produces immutable deterministic reports)
  demo (SYNTHETIC ONLY; builds a standalone ready-to-run sample)
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import math

import numpy as np
import pandas as pd

from .core import Config
from .cross_signals_v082 import CrossSignalResearch
from .data_quality_v083 import audit_universe,load_manifest,_xnys
from .strategy_v083 import StrategyPolicy,CostAssumptions,decisions_for_target,simulate_portfolio

REQUIRED=('SPY','QQQ','NVDA','SMH','XLK','IWM')


def _dump(obj):
    return json.dumps(obj,indent=2,ensure_ascii=True,sort_keys=True,allow_nan=False)+'\n'


def _write(path:Path,data:str):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(data,encoding='utf-8')


def _ci(trades,seed=2026):
    """Exploratory exit-month-block bootstrap, not independent sample significance."""
    if len(trades)<8:return None
    frame=pd.DataFrame(trades)
    frame['trade_pct']=100*frame['net_pnl']/frame['cost_total']
    frame['month']=frame['exit_date'].str[:7]
    groups=[frame[frame.month==month].trade_pct.to_numpy(dtype=float) for month in sorted(frame.month.unique())]
    if len(groups)<4:return None
    rng=np.random.default_rng(seed)
    draws=[]
    for _ in range(600):
        x=np.concatenate([groups[j] for j in rng.integers(0,len(groups),size=len(groups))])
        draws.append(float(x.mean()))
    return [round(float(v),8) for v in np.quantile(draws,[.025,.975])]


def _overview(sim):
    trades=sim['trades'];ci=_ci(trades)
    return {'net_return_pct':sim['net_return_pct'], 'max_drawdown_pct':sim['max_drawdown_pct'],
            'completed_trades':len(trades),'unclosed_positions':sim['unclosed_positions'],
            'win_rate_pct':round(100*sum(t['net_pnl']>0 for t in trades)/len(trades),8) if trades else None,
            'mean_trade_net_return_pct':round(100*sum(t['net_pnl']/t['cost_total'] for t in trades)/len(trades),8) if trades else None,
            'trade_return_ci95_pct':ci,'skipped':len(sim['skipped'])}


def _folds(decisions, daily, policy, costs, cash):
    sessions=[x.strftime('%Y-%m-%d') for x in pd.DatetimeIndex(daily['SPY']['date'])]
    usable=sessions[180:]
    left=int(len(usable)*.6);mid=int(len(usable)*.8)
    edges=[('development',usable[:left]),('validation_previously_examined',usable[left:mid]),('retrospective_previously_examined',usable[mid:])]
    output={}
    for name,dates in edges:
        if len(dates)<4:continue
        begin,end=dates[0],dates[-1]
        # Use full target history to map decision chronology, but only execute
        # entries/exits within the chosen fold; never move a trade across it.
        included=[d for d in decisions if begin<=d['asof_completed_session']<=end and
                  d['action'] in ('BUY_CANDIDATE','NO_TRADE')]
        period={s:df[(df.date>=pd.Timestamp(begin))&(df.date<=pd.Timestamp(end))].copy()
                for s,df in daily.items() if s in policy.permitted_symbols}
        retained=[]
        # A first-fold signal may have been generated before the fold starts;
        # it is explicitly excluded from fold execution, even if entry occurs in fold.
        for d in included:
            if d['asof_completed_session']<begin:continue
            retained.append(d)
        sim=simulate_portfolio(period,retained,policy=policy,costs=costs,initial_cash=cash)
        output[name]={'start':begin,'end':end,'sessions':len(dates),**_overview(sim),
                      'no_claim_of_untouched_holdout':True}
    return output


def create_study(records,daily,*,initial_cash=100.0,costs=CostAssumptions(),
                 policy=StrategyPolicy(),min_sessions=250) -> dict:
    audit=audit_universe(records,daily,min_sessions=min_sessions)
    if not audit['ready']:
        raise ValueError('Data audit failed; examine audit.json before running study: '+','.join(audit['failed_symbols']))
    # Strict synchronization: all six research symbols must have each of the
    # same completed session dates across the analysis span; no imputation.
    dates=[pd.DatetimeIndex(daily[s]['date']) for s in REQUIRED]
    if any(not dates[0].equals(x) for x in dates[1:]):
        raise ValueError('All six research series must have identical calendars in the study range')
    factor=CrossSignalResearch(daily)
    all_decisions={'kde_long_only':[],'kde_cross_confirmed':[]}
    for symbol in policy.permitted_symbols:
        by_mode=decisions_for_target(daily[symbol],symbol,factor,policy)
        for mode in all_decisions:all_decisions[mode]+=by_mode[mode]
    for mode in all_decisions:
        all_decisions[mode].sort(key=lambda d:(d['asof_completed_session'],d['symbol']))
    results={mode:simulate_portfolio(daily,decisions,policy=policy,costs=costs,initial_cash=initial_cash)
             for mode,decisions in all_decisions.items()}
    analysis={mode:{'overall':_overview(res),
                    'retrospective_splits':_folds(all_decisions[mode],daily,policy,costs,initial_cash),
                    'trade_count':len(res['trades'])}
              for mode,res in results.items()}
    source_dir=Path(__file__).parent
    source_hashes={name:sha256((source_dir/name).read_bytes()).hexdigest()
                   for name in ('core.py','cross_signals_v082.py','data_quality_v083.py',
                                'strategy_v083.py','research_pipeline_v083.py')}
    manifest={'schema':'quantdesk.research_run.v1','release':'0.8.3','policy':asdict(policy),
              'source_code_sha256':source_hashes,
              'kde_config':asdict(Config()),'cost_assumptions':asdict(costs),
              'initial_cash':initial_cash,
              'dataset_sha256':{k:v['sha256'] for k,v in sorted(records.items())},
              'data_audit':audit,'evaluation':analysis,
              'evaluation_label':'RETROSPECTIVE_PREVIOUSLY_EXAMINED_NOT_UNTOUCHED',
              'research_only':True,'orders_enabled':False,
              'warnings':['No prospective validation or proven alpha; every historical split was previously inspected.',
                          'Synthetic spread/slippage assumptions are not observed fills, NBBO, or market impact.',
                          'No shorting, tax model, adjusted-price fills, corporate-action cashflows or options modeling.',
                          'Cross-asset confirmation may overfit correlated peers; no claim of independent evidence.',
                          'The next major stage (v0.9) must add broker-specific risk, order idempotency and crash recovery.']}
    manifest['run_id']=sha256(_dump(manifest).encode()).hexdigest()
    return {'manifest':manifest,'decisions':all_decisions,'results':results}


def export_study(study:dict,out:Path):
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Refusing to overwrite an existing research run; choose a new output directory')
    out.mkdir(parents=True,exist_ok=True)
    _write(out/'report.json',_dump(study['manifest']))
    _write(out/'decisions.json',_dump(study['decisions']))
    for mode,res in study['results'].items():
        _write(out/f'{mode}_summary.json',_dump({k:v for k,v in res.items() if k not in ('equity','trades')}))
        pd.DataFrame(res['equity']).to_csv(out/f'{mode}_equity.csv',index=False)
        pd.DataFrame(res['trades'],columns=['decision_id','symbol','entry_date','exit_date','quantity','entry_fill','exit_fill','cost_total','proceeds_total','net_pnl']).to_csv(out/f'{mode}_trades.csv',index=False)
    _write(out/'report.html',html_report(study['manifest']))
    return out


def html_report(manifest:dict):
    """Self-contained printable baseline report; no JS/network/external assets."""
    rows=[]
    for mode,rep in manifest['evaluation'].items():
        z=rep['overall']
        rows.append(f'<tr><td>{escape(mode)}</td><td>{z["completed_trades"]}</td><td>{z["net_return_pct"]:+.3f}%</td><td>{z["max_drawdown_pct"]:.3f}%</td><td>{"Not available" if z["trade_return_ci95_pct"] is None else escape(str(z["trade_return_ci95_pct"]))}</td></tr>')
    n=manifest['data_audit']['shared_completed_sessions']
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>QuantDesk v0.8.3 Research</title>'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><style>'
        'body{background:#050706;color:#e5eae6;font:15px system-ui;margin:0;padding:3vw;max-width:1100px}'
        'h1{color:#30df70}small,p{color:#a9b3ad}section{border:1px solid #3b453e;background:#111713;padding:1.4rem;margin:1rem 0;border-radius:8px}'
        'table{width:100%;border-collapse:collapse}td,th{padding:.7rem;border-bottom:1px solid #3b453e;text-align:left}th{color:#b5dbb9}'
        '.warn{border-left:4px solid #eac14b;padding:.8rem;background:#292417}code{overflow-wrap:anywhere}</style></head><body>'
        '<h1>QuantDesk v0.8.3 — Strategy Research</h1>'
        '<p class="warn">RETROSPECTIVE, previously examined history. Hypothetical daily bars and estimated costs. NOT validated alpha; no orders.</p>'
        f'<section><h2>Run ID</h2><code>{escape(manifest["run_id"])}</code><p>Common verified sessions: {n} · No live data used</p></section>'
        '<section><h2>Cash-backed strategy comparison</h2><table><thead><tr><th>Strategy</th><th>Trades</th><th>Net return</th><th>Max drawdown</th><th>Trade CI (95%)</th></tr></thead><tbody>'+
        ''.join(rows)+'</tbody></table><small>Results reflect allocation limits. CI is exploratory month-block resampling, unavailable for insufficient events.</small></section>'
        '<section><h2>Next decision</h2><p>Freeze the rules; collect future market sessions prospectively. Build v0.9 paper execution separately and keep broker credentials out of this report.</p></section></body></html>')


def synthetic_demo(out: Path, sessions: int=320):
    if out.exists() and any(out.iterdir()):raise FileExistsError('Demo target is not empty')
    out.mkdir(parents=True,exist_ok=True)
    days=_xnys().sessions_in_range('2025-01-02','2026-10-01')[:sessions].tz_localize(None)
    r=np.random.default_rng(1717)
    market=np.cumsum(r.normal(0,.007,len(days)))
    specs={s:(1+i*.08,140+15*i) for i,s in enumerate(REQUIRED)}
    for i,(sym,(beta,price)) in enumerate(specs.items()):
        residual=np.cumsum(r.normal(0,.003,len(days)))
        close=price*np.exp(beta*market+residual)
        opens=close*np.exp(r.normal(0,.003,len(days)))
        hi=np.maximum(opens,close)*(1+r.uniform(.002,.015,len(days)))
        lo=np.minimum(opens,close)*(1-r.uniform(.002,.015,len(days)))
        dest=out/'data'/(sym+'.csv');dest.parent.mkdir(parents=True,exist_ok=True)
        pd.DataFrame({'date':days.strftime('%Y-%m-%d'),'open':opens,'high':hi,'low':lo,'close':close,
                      'volume':r.integers(1000,100000,len(days))}).to_csv(dest,index=False)
    manifest={'schema':1,'symbols':{s:{'path':'data/'+s+'.csv','source':'SYNTHETIC_DEMO_NOT_REAL_MARKET_DATA',
                                     'price_basis':'raw'} for s in REQUIRED}}
    _write(out/'manifest.json',_dump(manifest))
    return out/'manifest.json'


def initial_manifest(data_dir:Path,out:Path):
    """Create a local-only review template; NEVER claim data is raw without evidence."""
    if out.exists():raise FileExistsError(f'Will not overwrite {out}')
    base=out.resolve().parent
    files={}
    for sym in REQUIRED:
        candidates=[data_dir/(sym+'.csv'),data_dir/'context'/(sym+'.csv')]
        found=next((p.resolve() for p in candidates if p.is_file()),None)
        if not found:raise FileNotFoundError(f'Missing required daily CSV for {sym}')
        files[sym]={'path':str(found.relative_to(base)) if found.is_relative_to(base) else str(found),
                    'source':'UNVERIFIED_REVIEW_ME','price_basis':'unknown'}
    _write(out,_dump({'schema':1,'symbols':files}))
    return out


def main(argv=None):
    p=argparse.ArgumentParser(description='QuantDesk 0.8.3 offline audit/reproducible strategy research. NO TRADING.')
    sub=p.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init-manifest');init.add_argument('--data-dir',default='data');init.add_argument('--out',default='research_manifest_v083.local.json')
    demo=sub.add_parser('demo');demo.add_argument('--out',default='outputs/v083_synthetic_demo')
    for name in ('audit','study'):
        q=sub.add_parser(name);q.add_argument('--manifest',required=True);q.add_argument('--out',required=True)
        q.add_argument('--min-sessions',type=int,default=250)
        if name=='study':q.add_argument('--cash',type=float,default=100.)
    a=p.parse_args(argv)
    if a.command=='init-manifest':print(initial_manifest(Path(a.data_dir),Path(a.out)));return
    if a.command=='demo':print('SYNTHETIC ONLY',synthetic_demo(Path(a.out)));return
    records,daily=load_manifest(Path(a.manifest))
    audit=audit_universe(records,daily,min_sessions=a.min_sessions)
    path=Path(a.out)
    if a.command=='audit':
        if path.exists() and path.is_file():raise ValueError('Audit output must be a directory')
        _write(path/'audit.json',_dump(audit))
        print('PASS' if audit['ready'] else 'FAIL (review audit.json)',path/'audit.json')
        if not audit['ready']:raise SystemExit(2)
        return
    # Fail closed; save audit for diagnosis, never produce a "winning" report
    # from unreviewed data.
    if not audit['ready']:
        _write(path/'audit.json',_dump(audit))
        raise SystemExit('Data audit FAILED; inspect '+str(path/'audit.json'))
    study=create_study(records,daily,initial_cash=a.cash,min_sessions=a.min_sessions)
    export_study(study,path)
    print('Research report:',path/'report.html','\nRun ID:',study['manifest']['run_id'])
    print('RETROSPECTIVE ONLY. No orders. No proven alpha.')


if __name__=='__main__':main()
