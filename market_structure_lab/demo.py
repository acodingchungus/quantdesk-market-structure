"""Generate explicitly synthetic toy OHLCV data for smoke-testing (NOT market data)."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output-dir',default='data_demo')
    args=p.parse_args()
    dest=Path(args.output_dir); dest.mkdir(parents=True,exist_ok=True)
    dates=pd.bdate_range('2024-01-02',periods=620)
    for seed,sym,base in [(18,'SPY',460),(29,'QQQ',390)]:
        rng=np.random.default_rng(seed)
        prices=[base]
        for k in range(1,len(dates)+1):
            # Artificial cyclic structure, not calibrated or similar to actual market returns.
            r=0.00008+0.006*np.sin(k/19)+rng.normal(0,0.008)
            prices.append(prices[-1]*np.exp(r))
        c=np.array(prices[1:]); o=np.array(prices[:-1])*(1+rng.normal(0,.001,len(dates)))
        hi=np.maximum(o,c)*(1+rng.uniform(.002,.009,len(dates)))
        lo=np.minimum(o,c)*(1-rng.uniform(.002,.009,len(dates)))
        df=pd.DataFrame({'date':dates.strftime('%Y-%m-%d'),'open':o,'high':hi,'low':lo,
             'close':c,'volume':rng.integers(3_000_000,10_000_000,len(dates))})
        df.to_csv(dest/f'{sym}.csv',index=False)
        print(f'GENERATED SYNTHETIC DEMO ONLY: {dest/f"{sym}.csv"}')

if __name__=='__main__':
    main()
