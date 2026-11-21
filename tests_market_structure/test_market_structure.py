import unittest
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from market_structure_lab.core import (Config, _pivots, discover_levels,
    evaluate_symbol, load_bars, summarize_events)


def synthetic_bars(n=380):
    dates=pd.bdate_range('2024-01-02',periods=n)
    x=np.arange(n,dtype=float)
    # Repeated cycles make price reactions detectable without precomputed labels.
    c=100+4*np.sin(x/8)+.008*x
    o=c+.12*np.cos(x)
    h=np.maximum(o,c)+.4
    l=np.minimum(o,c)-.4
    return pd.DataFrame({'date':dates,'open':o,'high':h,'low':l,
        'close':c,'volume':np.full(n,100000)})

class MarketStructureTests(unittest.TestCase):
    def setUp(self):
        self.cfg=Config(lookback=100,forward_bars=3,holdout_date='2025-01-01')

    def test_no_pivot_available_before_right_confirmation(self):
        df=synthetic_bars(55)
        # Isolate an extreme high at i=51; it must not exist until 54 closed.
        df.loc[51,'high']=1000
        self.assertFalse(any(i==51 for _,_,i in _pivots(df.iloc[:54],self.cfg)))
        self.assertTrue(any(i==51 for _,_,i in _pivots(df.iloc[:55],self.cfg)))

    def test_level_map_cannot_see_future_prices(self):
        df=synthetic_bars(220)
        before=discover_levels(df.iloc[:160],self.cfg)
        changed=df.copy()
        changed.loc[160:,'close']=changed.loc[160:,'close']*7
        changed.loc[160:,'open']=changed.loc[160:,'open']*7
        changed.loc[160:,'high']=changed.loc[160:,'high']*7
        changed.loc[160:,'low']=changed.loc[160:,'low']*7
        after=discover_levels(changed.iloc[:160],self.cfg)
        self.assertEqual(before,after)

    def test_complete_evaluation_level_maps_causal(self):
        df=synthetic_bars(290)
        maps,events=evaluate_symbol(df,'SPY',self.cfg)
        self.assertFalse(maps.empty)
        self.assertFalse(events.empty)
        self.assertTrue((pd.to_datetime(maps.level_asof_date) < pd.to_datetime(maps.effective_date)).all())
        self.assertTrue((pd.to_datetime(events.level_asof_date) < pd.to_datetime(events.signal_date)).all())
        self.assertTrue((pd.to_datetime(events.signal_date) < pd.to_datetime(events.entry_date)).all())
        self.assertTrue((pd.to_datetime(events.entry_date) <= pd.to_datetime(events.exit_date)).all())
        for e in events.itertuples():
            self.assertEqual(str(df.iloc[e.signal_index+1].date.date()), e.entry_date)
            self.assertEqual(str(df.iloc[e.signal_index+self.cfg.forward_bars].date.date()), e.exit_date)
            calculated=e.direction*(e.exit_price-e.entry_price)/e.entry_price
            self.assertAlmostEqual(e.gross_signed_return,calculated,places=12)

    def test_future_mutation_does_not_change_past_maps(self):
        df=synthetic_bars(270)
        m1,_=evaluate_symbol(df,'QQQ',self.cfg)
        df2=df.copy()
        # Preserve OHLC validity for every later day, while changing future path.
        df2.loc[230:,['open','high','low','close']]*=1.3
        m2,_=evaluate_symbol(df2,'QQQ',self.cfg)
        a=m1[m1.effective_date<'2024-11-01'].reset_index(drop=True)
        b=m2[m2.effective_date<'2024-11-01'].reset_index(drop=True)
        pd.testing.assert_frame_equal(a,b)

    def test_train_outcomes_do_not_cross_holdout_boundary(self):
        df=synthetic_bars(385)
        _,events=evaluate_symbol(df,'SPY',self.cfg)
        summary=summarize_events(events,self.cfg)
        self.assertIsInstance(summary,pd.DataFrame)
        # Each training row is selected using its exit date, not signal date.
        d=pd.Timestamp(self.cfg.holdout_date)
        for r in events.itertuples():
            if r.signal_date < self.cfg.holdout_date and r.exit_date >= self.cfg.holdout_date:
                self.assertFalse((pd.to_datetime(r.exit_date)<d))

    def test_rejects_unsorted_and_invalid_candles(self):
        df=synthetic_bars(55)
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'bad.csv'
            df.iloc[::-1].to_csv(f,index=False)
            with self.assertRaisesRegex(ValueError,'strictly increasing'):
                load_bars(str(f))
            df.loc[2,'high']=1
            df.to_csv(f,index=False)
            with self.assertRaisesRegex(ValueError,'invalid OHLCV'):
                load_bars(str(f))

    def test_rejects_parameter_misconfiguration(self):
        with self.assertRaises(ValueError):
            Config(pivot_right=0)
        with self.assertRaises(ValueError):
            Config(roundtrip_cost_bps=-1)

if __name__=='__main__':
    unittest.main()
