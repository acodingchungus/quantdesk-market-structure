"""v0.4 causality, imported-minute safety, aggregation, API and notebook regression."""
from pathlib import Path
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
import pandas as pd

from market_structure_lab.core import Config
from market_structure_lab.intraday import (load_minutes, aggregate_minutes,
                                          marks_through_bars, descriptive_event_study)
from market_structure_lab.workstation import ResearchStore, make_handler


def daily(n=230):
    date = pd.bdate_range('2024-01-02', periods=n)
    x=np.arange(n,dtype=float)
    close=110+3*np.sin(x/7)+x*.03
    op=close+.1
    return pd.DataFrame({'date': date.strftime('%Y-%m-%d'), 'open':op,
                         'high':np.maximum(op,close)+.5,
                         'low':np.minimum(op,close)-.5, 'close':close,
                         'volume':10000+100*x})


def minutes(day: str, count=390):
    stamps=pd.date_range(f'{day} 09:31',periods=count,freq='min',tz='America/New_York')
    close=np.arange(count)*.01+118
    return pd.DataFrame({'timestamp':[t.isoformat() for t in stamps],
                         'open':close-.04,'high':close+.1,
                         'low':close-.1,'close':close,'volume':100})


class IntradayDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'minutes.csv'
        self.day='2024-11-18'
        minutes(self.day).to_csv(self.path,index=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_strict_timestamp_and_sanitization(self):
        good=load_minutes(self.path)
        self.assertEqual(len(good),390)
        bads=[('timestamp','2024-11-18 09:31:00'),
              ('timestamp','2024-11-18T08:31:00-05:00'),
              ('high',-1),('close',float('nan'))]
        for field,value in bads:
            bad=minutes(self.day)
            bad.loc[0,field]=value
            bad.to_csv(self.path,index=False)
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                load_minutes(self.path)
        bad=minutes(self.day)
        bad.loc[1,'timestamp']=bad.loc[0,'timestamp']
        bad.to_csv(self.path,index=False)
        with self.assertRaises(ValueError): load_minutes(self.path)

    def test_interval_boundaries_and_volumes(self):
        src=load_minutes(self.path)
        for tf,n in [('1m',390),('5m',78),('15m',26),('1h',7)]:
            r=aggregate_minutes(src,tf)
            self.assertEqual(len(r),n)
            self.assertTrue(r['complete'].all())
            self.assertEqual(float(r.volume.sum()),float(src.volume.sum()))
            self.assertEqual(float(r.iloc[0]['open']),float(src.iloc[0].open))
            self.assertEqual(float(r.iloc[-1]['close']),float(src.iloc[-1].close))
        self.assertEqual(int(aggregate_minutes(src,'1h').iloc[-1]['count']),30)

    def test_gap_not_interpolated_and_bucket_flagged(self):
        bad=minutes(self.day).drop(index=2).reset_index(drop=True)
        bad.to_csv(self.path,index=False)
        src=load_minutes(self.path)
        r=aggregate_minutes(src,'5m')
        self.assertEqual(len(r),78)
        self.assertEqual(int(r.iloc[0]['count']),4)
        self.assertFalse(bool(r.iloc[0]['complete']))

    def test_causal_markers_and_future_analysis_separated(self):
        src=load_minutes(self.path)
        z=[{'id':'TEST-Z001','price':118.7,'radius':.03,'asof_date':'2024-11-15'}]
        past=aggregate_minutes(src.iloc[:40],'1m')
        first=marks_through_bars(past,z,'SPY')
        modified=src.copy()
        modified.loc[50:,'high']=modified.loc[50:,'high']+50
        modified.loc[50:,'close']=modified.loc[50:,'close']+10
        # Earlier markers depend exclusively on earlier completed minute candles.
        second=marks_through_bars(aggregate_minutes(modified.iloc[:40],'1m'),z,'SPY')
        self.assertEqual(first,second)
        study=descriptive_event_study(src, {self.day:z}, 'SPY')
        if not study.empty:
            self.assertTrue(set(study.zone_asof)=={'2024-11-15'})
            self.assertIn('return_60m_pct',study.columns)


class WorkstationIntradayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        root=Path(cls.temp.name)
        root.joinpath('data/intraday').mkdir(parents=True)
        for symbol in ('SPY','QQQ'):
            df=daily()
            df.to_csv(root/'data'/f'{symbol}.csv',index=False)
            for day in df.tail(2)['date']:
                minute_df=minutes(day)
                if day==df.iloc[-1]['date']:
                    minute_df=minute_df.iloc[:25]
                # include both sessions, one partial
                if day==df.iloc[-2]['date']:
                    all_df=minute_df
                else:
                    all_df=pd.concat([all_df,minute_df],ignore_index=True)
            all_df.to_csv(root/'data/intraday'/f'{symbol}_1m.csv',index=False)
        cls.store=ResearchStore(root/'data',root/'notes.sqlite',config=Config(lookback=75))
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(cls.store,0))
        cls.server.RequestHandlerClass=make_handler(cls.store,cls.server.server_port)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.host=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def get(self,path):
        with urlopen(self.host+path,timeout=30) as r:
            return json.load(r)

    def test_status_advertises_only_loaded_intervals(self):
        status=self.get('/api/status')
        self.assertEqual(status['version'],'0.7')
        self.assertFalse(status['orders_enabled'])
        self.assertFalse(status['broker_connected'])
        self.assertIn('5m',status['data'][0]['timeframes'])
        self.assertEqual(status['data'][0]['intraday']['partial_sessions'],1)

    def test_intraday_replay_hides_all_future_bars(self):
        dates=self.get('/api/dates?symbol=SPY&timeframe=1m')['dates']
        f=self.get('/api/frame?symbol=SPY&timeframe=1m&date='+dates[0]+'&bar=0&window=40')
        self.assertEqual(f['session_bar_count'],390)
        self.assertEqual(f['current_bar_index'],0)
        self.assertEqual(len(f['candles']),1)
        self.assertTrue(all(z['asof_date']<dates[0] for z in f['levels']))
        self.assertTrue(all(m['date']<=f['current_bar_time'] for m in f['markers']))
        mid=self.get('/api/frame?symbol=SPY&timeframe=1m&date='+dates[0]+'&bar=38&window=40')
        self.assertEqual(len(mid['candles']),39)
        self.assertTrue(all(x['date']<=mid['current_bar_time'] for x in mid['candles']))
        self.assertEqual(mid['levels'],f['levels'])
        # Daily untouched, backwards compatible.
        daily_fr=self.get('/api/frame?symbol=SPY&date='+dates[0]+'&window=40')
        self.assertEqual(daily_fr['timeframe'],'1d')
        self.assertEqual(daily_fr['map_asof_date'],f['map_asof_date'])

    def test_partial_sessions_reported_without_fake_candles(self):
        dates=self.get('/api/dates?symbol=SPY&timeframe=5m')['dates']
        f=self.get('/api/frame?symbol=SPY&timeframe=5m&date='+dates[-1]+'&bar=4')
        self.assertEqual(f['session_minutes'],25)
        self.assertTrue(f['partial_session'])
        self.assertEqual(f['session_bar_count'],5)

    def test_bad_timeframe_and_bar_rejected(self):
        for url in ['/api/frame?timeframe=4m','/api/frame?timeframe=1m&bar=999',
                    '/api/frame?timeframe=1m&bar=-1','/api/frame?timeframe=1m&bar=garbage',
                    '/api/dates?timeframe=99m']:
            with self.subTest(url=url),self.assertRaises(HTTPError) as ctx:
                self.get(url)
            self.assertEqual(ctx.exception.code,400)


if __name__=='__main__':
    unittest.main()
