"""v0.7.3 correctness contracts: optimization must NOT alter research math."""
from __future__ import annotations
from datetime import timedelta
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

from market_structure_lab.core import Config
from market_structure_lab.intraday import marks_through_bars
from market_structure_lab.volume_profile import ProfileIndex, build_profile
from market_structure_lab.workstation import ResearchStore


def trades_fixture(n=275):
    rng=np.random.default_rng(20261122)
    t0=pd.Timestamp('2024-11-18 14:30:00',tz='UTC')
    # Multiple executions at identical timestamps are valid and must be preserved.
    stamps=[t0+timedelta(seconds=i//2) for i in range(n)]
    cents=rng.integers(10000,10019,size=n)
    prices=[f'{v/100:.2f}' for v in cents]
    sizes=rng.integers(1,110,size=n,dtype=np.int64)
    return pd.DataFrame({'timestamp':stamps,'price':list(map(float,prices)),
                         'price_text':prices,'size':sizes,'session':['2024-11-18']*n})


class ExactProfilePerformanceTests(unittest.TestCase):
    def test_indexed_matches_original_across_cutoffs_and_bins(self):
        ticks=trades_fixture()
        index=ProfileIndex(ticks)
        for step in ('0.01','0.05','0.10','0.25','1.00'):
            for at in (ticks.timestamp.iloc[0]-pd.Timedelta(seconds=1),
                       ticks.timestamp.iloc[0],ticks.timestamp.iloc[48],
                       ticks.timestamp.iloc[129],ticks.timestamp.iloc[-1]):
                with self.subTest(bin=step,at=at):
                    self.assertEqual(build_profile(ticks,asof=at,price_bin=step),
                                     index.evaluate(asof=at,price_bin=step))

    def test_index_does_not_admit_future_prints(self):
        ticks=trades_fixture()
        at=ticks.timestamp.iloc[90]
        old=ProfileIndex(ticks).evaluate(asof=at,price_bin='0.05')
        corrupted=ticks.copy()
        corrupted.loc[corrupted.timestamp>at,'price_text']='777.77'
        corrupted.loc[corrupted.timestamp>at,'price']=777.77
        corrupted.loc[corrupted.timestamp>at,'size']=99999
        new=ProfileIndex(corrupted).evaluate(asof=at,price_bin='0.05')
        self.assertEqual(old,new)
        self.assertEqual(old['trade_prints'],92)  # both prints at second 45

    def test_invalid_bins_rejected_before_using_cached_response(self):
        index=ProfileIndex(trades_fixture())
        with self.assertRaises(ValueError): index.evaluate(price_bin='0.07')


class ReplaySessionPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        root=Path(cls.tmp.name)
        (root/'data/intraday').mkdir(parents=True)
        days=pd.bdate_range('2024-01-02',periods=230)
        v=110+np.sin(np.arange(230)/7)*2+np.arange(230)*.04
        for sym in ('SPY','QQQ'):
            df=pd.DataFrame({'date':days.strftime('%Y-%m-%d'),'open':v+.03,
                             'high':v+.5,'low':v-.5,'close':v,'volume':10000})
            df.to_csv(root/'data'/f'{sym}.csv',index=False)
            all_days=[]
            for day in days[-2:]:
                times=pd.date_range(f'{day.date()} 09:31',periods=390,freq='min',tz='America/New_York')
                x=117+np.sin(np.arange(390)/15)*.6
                all_days.append(pd.DataFrame({'timestamp':[d.isoformat() for d in times],
                    'open':x,'high':x+.2,'low':x-.3,'close':x+.04,'volume':100}))
            pd.concat(all_days,ignore_index=True).to_csv(root/'data/intraday'/f'{sym}_1m.csv',index=False)
        cls.store=ResearchStore(root/'data',root/'notes.sqlite',config=Config(lookback=75))
        cls.day=str(days[-1].date())

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_all_replay_outputs_equal_to_naive_causal_evaluation(self):
        ds=self.store.datasets['SPY']
        for tf in ('1m','5m','15m','1h'):
            chunk=ds['intraday'][tf][self.day]
            levels=ds['frames'][ds['index'][self.day]]['levels']
            for i in (0,1,min(7,len(chunk)-1),len(chunk)//2,len(chunk)-1):
                with self.subTest(tf=tf,index=i):
                    w=40
                    frame=self.store.frame('SPY',self.day,w,tf,i)
                    base=marks_through_bars(chunk.iloc[:i+1],levels,'SPY')
                    start=chunk.iloc[max(0,i-w+1)].timestamp
                    self.assertEqual(frame['markers'],[m for m in base if pd.Timestamp(m['date'])>=start])
                    self.assertEqual(frame['today_reactions'],[m for m in base if m['date']==chunk.iloc[i].timestamp.isoformat()])
                    self.assertEqual(frame['current_bar_index'],i)
                    self.assertEqual(len(frame['candles']),min(w,i+1))
                    self.assertEqual(frame['levels'],levels)

    def test_fast_seeks_reuse_causal_marker_work(self):
        # All the expensive detection is done once per session/timeframe.
        self.store._session_cache.clear()
        original=marks_through_bars
        with patch('market_structure_lab.workstation.marks_through_bars',wraps=original) as mocked:
            for i in (50,51,52,100,250,375):
                self.store.frame('SPY',self.day,80,'1m',i)
            self.assertEqual(mocked.call_count,1)
        self.assertLessEqual(len(self.store._session_cache),12)

    def test_daily_level_map_unchanged(self):
        ds=self.store.datasets['SPY']
        x=self.store.frame('SPY',self.day,80,'1d')
        self.assertEqual(x['levels'],ds['frames'][ds['index'][self.day]]['levels'])
        idx=ds['index'][self.day]
        expected=[m for earlier in ds['frames']
                  if max(0,idx-79)<=earlier['index']<=idx
                  for m in earlier['markers']]
        self.assertEqual(x['markers'],expected)

    def test_trade_profile_work_never_holds_frame_lock(self):
        # Avoid a slow archival profile blocking all chart frame requests.
        self.store._profile_lock.acquire()
        event=threading.Event()
        done=threading.Event()
        def wait_for_profile_lock():
            event.set()
            try:self.store.volume_profile('SPY',self.day,'1m',4)
            finally:done.set()
        thread=threading.Thread(target=wait_for_profile_lock,daemon=True)
        try:
            thread.start();self.assertTrue(event.wait(2))
            # Frame API is independent of profile archive lock.
            frame=self.store.frame('SPY',self.day,40,'1m',10)
            self.assertEqual(frame['current_bar_index'],10)
        finally:
            self.store._profile_lock.release();thread.join(3)
        self.assertTrue(done.is_set())


class FrontendPerformanceTests(unittest.TestCase):
    def test_browser_coalesces_expensive_work(self):
        html=(Path(__file__).resolve().parents[1]/'market_structure_lab/assets/workstation.html').read_text(encoding='utf-8')
        for marker in ('AbortController','cancelFrameWork()','cancelProfileWork()',
                       'profileTimer=setTimeout(async()=>{','},240)',
                       'if(!app.playing)refreshProfile(token)',
                       'if(cvs.width!==pixelW)cvs.width=pixelW',
                       'scheduleHoverDraw()'):
            self.assertIn(marker,html)

if __name__=='__main__':unittest.main()
