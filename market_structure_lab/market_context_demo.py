"""Toy context-asset data ONLY for v0.6 synthetic dashboard demos."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from .market_intelligence import CONTEXT_SYMBOLS


def generate(data_dir):
    base=Path(data_dir)
    spy=base/'SPY.csv'
    if not spy.exists():raise FileNotFoundError('Generate synthetic SPY/QQQ daily demo first')
    df=pd.read_csv(spy)
    if len(df)<100:raise ValueError('Daily synthetic demo needs at least 100 sessions')
    out=base/'context';out.mkdir(exist_ok=True,parents=True)
    data=df['close'].to_numpy(float)
    for idx,sym in enumerate(CONTEXT_SYMBOLS):
        rng=np.random.default_rng(800+idx)
        # Intentionally fabricated sector drift, oscillation and random noise.
        ratio=(.38+idx*.08)*np.exp(.0002*np.arange(len(data))+0.015*np.sin(np.arange(len(data))/(12+idx)))
        close=data*ratio*np.exp(np.cumsum(rng.normal(0,.002,len(data))))
        opn=close*(1+rng.normal(0,.001,len(data)))
        frame=pd.DataFrame({'date':df['date'],'open':opn,'high':np.maximum(opn,close)*1.009,
                            'low':np.minimum(opn,close)*.991,'close':close,
                            'volume':rng.integers(100000,2000000,len(data))})
        frame.to_csv(out/f'{sym}.csv',index=False)
        print(f'SYNTHETIC CONTEXT DEMO ONLY: {out/f"{sym}.csv"}')


def main():
    p=argparse.ArgumentParser(description='Generate explicitly synthetic context assets; never real market data')
    p.add_argument('--data-dir',default='data_demo')
    args=p.parse_args();generate(args.data_dir)

if __name__=='__main__':main()
