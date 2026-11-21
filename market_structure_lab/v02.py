"""v0.2 runnable experiment; v0.1 core/run remain untouched.

Example:
python -m market_structure_lab.v02 --data-dir data --out outputs/v02_research
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .core import Config, load_bars, evaluate_symbol, discover_levels, summarize_events
from .replay_model import make_replay
from .replay_view import write_replay_html
from .validation import matched_controls, summarize_matched, summarize_reactions


def snapshot(bars: pd.DataFrame, frame: dict, path: Path, symbol: str, window: int = 85) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    idx=frame['index']; start=max(0,idx-window+1)
    visible=bars.iloc[start:idx+1].reset_index(drop=True)
    fig,ax=plt.subplots(figsize=(14.8,6.4),facecolor='#0e1726')
    ax.set_facecolor('#132035')
    price_hi=max([float(visible.high.max())]+[l['price']+l['radius'] for l in frame['levels']])
    price_lo=min([float(visible.low.min())]+[l['price']-l['radius'] for l in frame['levels']])
    for l in frame['levels']:
        y=l['price']; r=l['radius']
        col='#55c8ab' if y<float(visible.iloc[-1].close) else '#77b4ff'
        ax.axhspan(y-r,y+r,color=col,alpha=.10)
        ax.hlines(y,-.5,len(visible)-.5,color=col,alpha=.8,ls='--',linewidth=.9)
        ax.text(len(visible)-.1,y, f"  {y:.2f} · {l['pivot_count']} pivots", color=col,fontsize=8,va='center',clip_on=False)
    for j,b in enumerate(visible.itertuples(index=False)):
        color='#36c1a3' if b.close>=b.open else '#f27579'
        ax.vlines(j,b.low,b.high,color=color,linewidth=1)
        bottom=min(b.open,b.close); height=max(abs(b.close-b.open),.02)
        ax.add_patch(Rectangle((j-.28,bottom),.56,height,facecolor=color,edgecolor=color,linewidth=.35))
    ticks=list(range(0,len(visible),max(1,len(visible)//9)))
    ax.set_xticks(ticks,[str(pd.Timestamp(visible.iloc[i].date).date()) for i in ticks],rotation=30,ha='right',color='#c1d1e4',fontsize=9)
    ax.tick_params(axis='y',colors='#c1d1e4')
    for sp in ax.spines.values():sp.set_color('#50637c')
    ax.grid(alpha=.13,color='white')
    ax.set_ylim(price_lo-(price_hi-price_lo)*.08,price_hi+(price_hi-price_lo)*.08)
    ax.set_xlim(-.5,len(visible)+12)
    ax.set_title(f"{symbol} · completed candles through {frame['date']} | zones known at OPEN (as of {frame['map_asof_date']})",
                 color='#e5edf7',fontsize=13,pad=14)
    ax.set_ylabel('Price from supplied adjusted/unadjusted CSV',color='#c1d1e4')
    fig.text(.01,.013,'RESEARCH ONLY · v0.2 historical replay · not live, options, volume profile or order book',color='#b9c5d3',fontsize=9)
    fig.tight_layout(rect=[0,.025,1,1]);fig.savefig(path,dpi=150,facecolor=fig.get_facecolor());plt.close(fig)


def main():
    p=argparse.ArgumentParser(description='QuantDesk v0.2 causal replay & exploratory matched event study (READ ONLY)')
    p.add_argument('--data-dir', default='data')
    p.add_argument('--out', default='outputs/v02_real_sip')
    p.add_argument('--symbols',nargs='+',default=['SPY','QQQ'])
    p.add_argument('--lookback',type=int,default=180)
    p.add_argument('--forward-bars',type=int,default=3)
    p.add_argument('--holdout',default='2025-12-04')
    p.add_argument('--roundtrip-cost-bps',type=float,default=5.0)
    p.add_argument('--snapshot-date',default=None,help='YYYY-MM-DD; exact session required (default last date)')
    a=p.parse_args()
    cfg=Config(lookback=a.lookback,forward_bars=a.forward_bars,holdout_date=a.holdout,
               roundtrip_cost_bps=a.roundtrip_cost_bps)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    hashes={}; original=[]; allmaps=[]; allmatched=[]; allreactions=[]; allevents=[]
    for sym in [s.upper() for s in a.symbols]:
        pth=Path(a.data_dir)/(sym+'.csv')
        hashes[sym]=hashlib.sha256(pth.read_bytes()).hexdigest()
        bars=load_bars(str(pth))
        maps,events=evaluate_symbol(bars,sym,cfg) # Exactly the same v0.1 procedure
        frames,reactions=make_replay(bars,sym,cfg,maps)
        matches=matched_controls(bars,events,sym,cfg)
        write_replay_html(bars,frames,reactions,sym,out/(sym+'_replay.html'))
        target=frames[-1]
        if a.snapshot_date:
            found=[f for f in frames if f['date']==a.snapshot_date]
            if not found:
                raise ValueError(f'{sym}: {a.snapshot_date} is not an available replay session')
            target=found[0]
        snapshot(bars,target,out/(sym+'_snapshot.png'),sym)
        original.append({'symbol':sym,'data_start':str(bars.iloc[0].date.date()),
                         'data_end':str(bars.iloc[-1].date.date()),'bars':len(bars),
                         'replay_frames':len(frames),'reactions':len(reactions),
                         'v01_events':len(events),'matched_events':len(matches)})
        if not maps.empty:allmaps.append(maps)
        if not events.empty:allevents.append(events)
        if not matches.empty:allmatched.append(matches)
        if not reactions.empty:allreactions.append(reactions)
        print(f'{sym}: {len(bars)} real/synthetic supplied bars · {len(frames)} replay days · '
              f'{len(reactions)} zone contacts · {len(matches)} matched observations')
    events=pd.concat(allevents,ignore_index=True) if allevents else pd.DataFrame()
    maps=pd.concat(allmaps,ignore_index=True) if allmaps else pd.DataFrame()
    reactions=pd.concat(allreactions,ignore_index=True) if allreactions else pd.DataFrame()
    matches=pd.concat(allmatched,ignore_index=True) if allmatched else pd.DataFrame()
    v01=summarize_events(events,cfg)
    v02=summarize_matched(matches,cfg)
    v02_react=summarize_reactions(reactions)
    for name,frame in [('v01_unchanged_summary.csv',v01),('v01_unchanged_events.csv',events),
                       ('point_in_time_levels.csv',maps),('reactions.csv',reactions),
                       ('reaction_counts.csv',v02_react),('matched_events.csv',matches),
                       ('matched_summary.csv',v02)]:
        frame.to_csv(out/name,index=False)
    (out/'run_manifest.json').write_text(json.dumps({
        'version':'0.2','data_csv_sha256':hashes,'config':vars(cfg),
        'datasets':original,'source':'user-supplied historical OHLCV, no network calls',
        'holdout_status':'ALREADY EXAMINED IN v0.1; exploratory only, NOT fresh validation',
        'interpretation':'Not options P&L, not live price levels, not volume profile or resting liquidity. '
                         'Matched controls are earlier non-event days with similar prior ATR and 10-bar returns, '
                         'not randomized causal controls. 5 bps is hypothetical ETF proxy cost, not actual options trading costs.',
    },indent=2),encoding='utf8')
    print('\nORIGINAL v0.1 RESULTS (preserved):')
    print(v01.to_string(index=False,float_format=lambda n:f'{n:.3f}') if not v01.empty else 'No qualifying observations')
    print('\nv0.2 EXPLORATORY MATCHING:')
    print(v02.to_string(index=False,float_format=lambda n:f'{n:.3f}') if not v02.empty else 'No eligible matched observations')
    print(f'\nREAD-ONLY v0.2 OUTPUT: {out.resolve()}')
    print('Open SPY_replay.html or QQQ_replay.html in a browser. Past holdout is NOT untouched.')


if __name__=='__main__':
    main()
