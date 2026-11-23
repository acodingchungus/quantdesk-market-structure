"""Offline, reproducible microbenchmarks for QuantDesk v0.7.3. NO network/data keys.

This measures the optimized exact-trade-index versus the original build_profile,
and a cached replay marker path versus repeated prefix scans. It is NOT a
production UX latency guarantee; disk/CPU/browser may be different on Windows.
"""
import argparse
import statistics
import time

import numpy as np
import pandas as pd

from market_structure_lab.volume_profile import ProfileIndex, build_profile
from market_structure_lab.intraday import marks_through_bars


def clock(fn):
    t0=time.perf_counter();result=fn();return (time.perf_counter()-t0)*1000,result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--trades',type=int,default=80000)
    p.add_argument('--seeks',type=int,default=8)
    args=p.parse_args()
    if args.trades<100 or args.trades>500000 or args.seeks<1 or args.seeks>30:
        p.error('trades 100..500000, seeks 1..30')
    rng=np.random.default_rng(20261122)
    prices=rng.integers(10000,10150,size=args.trades)
    sizes=rng.integers(1,1000,size=args.trades,dtype=np.int64)
    stamps=pd.date_range('2024-11-18 14:30',periods=args.trades,freq='ms',tz='UTC')
    values=[f'{c/100:.2f}' for c in prices]
    trades=pd.DataFrame({'timestamp':stamps,'session':['2024-11-18']*args.trades,
                         'price':prices.astype(float)/100,'price_text':values,'size':sizes})
    seq=[int(v) for v in np.linspace(20,args.trades-1,args.seeks)]
    asofs=[trades.timestamp.iloc[k] for k in seq]
    old_times=[];old=[]
    for asof in asofs:
        dur,result=clock(lambda:build_profile(trades,asof=asof,price_bin='0.05'))
        old_times.append(dur);old.append(result)
    init_ms,index=clock(lambda:ProfileIndex(trades))
    new_times=[]
    for asof,expected in zip(asofs,old):
        dur,result=clock(lambda:index.evaluate(asof=asof,price_bin='0.05'))
        assert result==expected,'Fatal: optimized profile diverged from original numerical accounting'
        new_times.append(dur)
    print(f'EXACT EQUALITY: {len(old)} profiles, {args.trades:,} synthetic ticks, $0.05 bin')
    print(f'OLD full scans total: {sum(old_times):.1f} ms, median {statistics.median(old_times):.1f} ms')
    print(f'NEW indexed total:    {sum(new_times)+init_ms:.1f} ms including {init_ms:.1f} ms initialization')
    print(f'NEW repeated median:  {statistics.median(new_times[1:] or new_times):.1f} ms')
    print(f'MEASURED total speedup for these seeks: {sum(old_times)/(sum(new_times)+init_ms):.2f}x')
    # Causal marker benchmark, 390 RTH bars and 8 candidate KDE-like levels.
    n=390
    times=pd.date_range('2024-11-18 14:31',periods=n,freq='min',tz='UTC')
    midpoint=100+np.sin(np.arange(n)/22)*1.5
    candles=pd.DataFrame({'timestamp':times,'open':midpoint-.02,'high':midpoint+.08,
                          'low':midpoint-.1,'close':midpoint,'volume':100,'session':['2024-11-18']*n})
    levels=[{'id':f'Z{k}','price':float(p),'radius':0.08,'asof_date':'2024-11-15'} for k,p in enumerate(np.linspace(98,102,8))]
    bar_indices=[int(i) for i in np.linspace(10,389,60)]
    old_ms,ref=clock(lambda:[marks_through_bars(candles.iloc[:i+1],levels,'SPY') for i in bar_indices])
    new_ms,all_marks=clock(lambda:marks_through_bars(candles,levels,'SPY'))
    for i,r in zip(bar_indices,ref):
        eligible=[m for m in all_marks if m['date']<=times[i].isoformat()]
        assert eligible==r,'Fatal: marker indexing violated prior-bar causality'
    print(f'MARKERS: 60 prefix scans: {old_ms:.1f} ms vs one pass: {new_ms:.1f} ms')

if __name__=='__main__':main()
