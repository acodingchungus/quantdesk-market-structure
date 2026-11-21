"""CLI for reproducible, read-only SPY/QQQ market-structure research."""
from __future__ import annotations
import argparse
import json
import hashlib
from pathlib import Path
import pandas as pd
from .core import Config, load_bars, evaluate_symbol, discover_levels, summarize_events


def plot_latest(df, levels, symbol: str, destination: Path, config: Config):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    x = df.tail(config.lookback)
    fig, ax = plt.subplots(figsize=(12,5.4))
    ax.plot(x['date'],x['close'],lw=1.4,label=f'{symbol} daily close')
    for l in levels:
        ax.axhline(l.price,linestyle='--',lw=0.9,alpha=.85)
        ax.axhspan(l.price-l.radius,l.price+l.radius,alpha=.1)
        ax.text(x['date'].iloc[-1],l.price, f'  {l.price:.2f} ({l.pivot_count} pivots)', fontsize=8, va='center')
    ax.set_title(f'{symbol}: candidate reaction zones known at {x.date.iloc[-1].date()} | RESEARCH ONLY')
    ax.set_xlabel('Completed trading sessions')
    ax.set_ylabel('Adjusted or unadjusted price, per supplied dataset')
    ax.grid(alpha=.2)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(destination,dpi=150)
    plt.close(fig)


def main():
    p=argparse.ArgumentParser(description='Point-in-time price-level research — NO broker orders')
    p.add_argument('--data-dir',default='data',help='Must contain SPY.csv and QQQ.csv')
    p.add_argument('--out',default='outputs/market_structure_v01')
    p.add_argument('--symbols',nargs='+',default=['SPY','QQQ'])
    p.add_argument('--lookback',type=int,default=180)
    p.add_argument('--forward-bars',type=int,default=3)
    p.add_argument('--holdout',default='2025-12-04')
    p.add_argument('--roundtrip-cost-bps',type=float,default=5.0)
    args=p.parse_args()
    cfg=Config(lookback=args.lookback,forward_bars=args.forward_bars,
               holdout_date=args.holdout,roundtrip_cost_bps=args.roundtrip_cost_bps)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    allmaps=[];allevents=[];latest=[];data_hashes={}
    for sym in args.symbols:
        input_file=Path(args.data_dir)/f'{sym.upper()}.csv'
        data_hashes[sym.upper()]=hashlib.sha256(input_file.read_bytes()).hexdigest()
        bars=load_bars(str(input_file))
        maps,events=evaluate_symbol(bars,sym.upper(),cfg)
        allmaps.append(maps);allevents.append(events)
        level_set=discover_levels(bars,cfg)
        for lev in level_set:
            latest.append(dict(symbol=sym.upper(),**vars(lev)))
        plot_latest(bars,level_set,sym.upper(),out/f'{sym.upper()}_latest.png',cfg)
        print(f'{sym}: {len(bars)} bars; {len(maps)} historical level-map rows; {len(events)} observed events')
    maps=pd.concat(allmaps,ignore_index=True)
    events=pd.concat(allevents,ignore_index=True)
    summary=summarize_events(events,cfg)
    maps.to_csv(out/'point_in_time_levels.csv',index=False)
    events.to_csv(out/'events.csv',index=False)
    summary.to_csv(out/'summary.csv',index=False)
    pd.DataFrame(latest).to_csv(out/'latest_levels.csv',index=False)
    (out/'experiment_config.json').write_text(json.dumps({'settings':vars(cfg),'symbols':args.symbols,
      'data_csv_sha256':data_hashes,
      'interpretation':'OHLCV-only level reaction study; no options/market impact/OPRA; not trade-ready'},indent=2))
    if summary.empty:
        print('No eligible events; inspect input data and parameters. This is not a failure to be tuned away.')
    else:
        print(summary.to_string(index=False,float_format=lambda x:f'{x:.3f}'))
    print(f'READ-ONLY RESEARCH OUTPUT: {out.resolve()}')


if __name__=='__main__':
    main()
