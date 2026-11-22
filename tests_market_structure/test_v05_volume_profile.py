"""v0.5 trade-derived profiles, exact price binning, causality and local API."""
from contextlib import closing
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
from market_structure_lab.volume_profile import load_trades, build_profile
from market_structure_lab.workstation import ResearchStore, make_handler


def prints(date='2024-11-18'):
    return pd.DataFrame([
        {'timestamp':f'{date}T09:30:20-05:00','price':'100.01','size':10},
        {'timestamp':f'{date}T09:30:50-05:00','price':'100.02','size':20},
        {'timestamp':f'{date}T09:31:15-05:00','price':'100.06','size':5},
        {'timestamp':f'{date}T09:31:35-05:00','price':'100.11','size':5},
    ])


class ProfileMathTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.file=Path(self.tmp.name)/'trades.csv'
        prints().to_csv(self.file,index=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_poc_value_area_vwap_exact_bins(self):
        t=load_trades(self.file)
        p=build_profile(t,price_bin='0.05')
        self.assertEqual(p['trade_prints'],4)
        self.assertEqual(p['volume_shares'],40)
        self.assertEqual(p['poc_low'],100.0)
        self.assertEqual(p['poc_high'],100.05)
        self.assertEqual(p['val'],100.0)
        self.assertEqual(p['vah'],100.05)
        self.assertAlmostEqual(p['value_area_achieved'],.75)
        self.assertAlmostEqual(p['vwap'],(100.01*10+100.02*20+100.06*5+100.11*5)/40)
        self.assertEqual(sum(b['volume'] for b in p['bins']),40)

    def test_point_in_time_cannot_see_later_prints(self):
        t=load_trades(self.file)
        cutoff='2024-11-18T09:31:00-05:00'
        original=build_profile(t,asof=cutoff)
        self.assertEqual(original['volume_shares'],30)
        future=prints()
        future.loc[3,'price']='100.99'
        future.loc[3,'size']=2000
        future.to_csv(self.file,index=False)
        altered=build_profile(load_trades(self.file),asof=cutoff)
        self.assertEqual(original,altered)
        self.assertEqual(original['trade_prints'],2)

    def test_rejects_bad_trade_data_and_unverified_timestamps(self):
        for column,bad in [('timestamp','2024-11-18 09:30:20'),('timestamp','2024-11-18T09:29:59-05:00'),
                           ('price',-3),('size',0),('size',1.5),('size',float('nan'))]:
            df=prints();df[column]=df[column].astype(object);df.loc[0,column]=bad;df.to_csv(self.file,index=False)
            with self.subTest(column=column,bad=bad),self.assertRaises(ValueError):
                load_trades(self.file)
        df=prints();df.loc[2,'timestamp']='2024-11-18T09:30:02-05:00';df.to_csv(self.file,index=False)
        with self.assertRaises(ValueError): load_trades(self.file)

    def test_invalid_steps_and_contiguous_va(self):
        t=load_trades(self.file)
        with self.assertRaises(ValueError):build_profile(t,price_bin='0.07')
        with self.assertRaises(ValueError):build_profile(t,value_area=.95)
        p=build_profile(t,price_bin='0.01')
        va=[i for i,b in enumerate(p['bins']) if b['in_value_area']]
        self.assertEqual(va,list(range(min(va),max(va)+1)))
        self.assertGreaterEqual(p['value_area_achieved'],.70)

    def test_identical_timestamps_are_valid_distinct_prints(self):
        df=prints();df.loc[1,'timestamp']=df.loc[0,'timestamp'];df.to_csv(self.file,index=False)
        p=build_profile(load_trades(self.file))
        self.assertEqual(p['trade_prints'],4)


class ProfileApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        root=Path(cls.tmp.name); datadir=root/'data';(datadir/'intraday').mkdir(parents=True)
        (datadir/'trades').mkdir()
        days=pd.bdate_range('2024-01-02',periods=220)
        x=np.arange(len(days),dtype=float)
        close=102+np.sin(x/10)*2+x*.03
        df=pd.DataFrame({'date':days.strftime('%Y-%m-%d'),'open':close+.05,
                         'high':close+.65,'low':close-.65,'close':close,
                         'volume':10000+50*x})
        for symbol in ('SPY','QQQ'):
            df.to_csv(datadir/f'{symbol}.csv',index=False)
        cls.day=df['date'].iloc[-1]
        ts=pd.date_range(f'{cls.day} 09:31',periods=2,freq='min',tz='America/New_York')
        pd.DataFrame({'timestamp':[d.isoformat() for d in ts],
                      'open':[100,100.1],'high':[100.2,100.4],
                      'low':[99.8,99.9],'close':[100.1,100.3],
                      'volume':[30,10]}).to_csv(datadir/'intraday/SPY_1m.csv',index=False)
        # No trades for QQQ; no minute bars either.
        ticktimes=[(ts[0]-pd.Timedelta(seconds=40)), ts[0],
                   ts[1]-pd.Timedelta(seconds=40),ts[1]]
        pd.DataFrame({'timestamp':[t.isoformat() for t in ticktimes],
                      'price':[100.01,100.02,100.06,100.11],
                      'size':[10,20,5,5]}).to_csv(datadir/'trades/SPY_trades.csv',index=False)
        cls.store=ResearchStore(datadir,root/'journal.sqlite',config=Config(lookback=75))
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(cls.store,0))
        cls.server.RequestHandlerClass=make_handler(cls.store,cls.server.server_port)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start();cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=5)
        cls.tmp.cleanup()

    def get(self, path):
        with closing(urlopen(self.url+path,timeout=15)) as resp:
            return json.load(resp)

    def test_status_and_missing_source_do_not_invent_a_profile(self):
        status=self.get('/api/status')
        self.assertEqual(status['version'],'0.5')
        self.assertFalse(status['broker_connected'])
        self.assertEqual(status['data'][0]['volume_profile']['trade_prints'],4)
        self.assertIsNone(status['data'][1]['volume_profile'])
        absent=self.get(f'/api/profile?symbol=QQQ&date={self.day}')
        self.assertFalse(absent['available'])
        self.assertIn('OHLCV is not volume-at-price',absent['reason'])

    def test_replay_profile_excludes_future_ticks(self):
        base=f'/api/profile?symbol=SPY&date={self.day}&timeframe=1m'
        first=self.get(base+'&bar=0')
        later=self.get(base+'&bar=1')
        self.assertEqual(first['trade_prints'],2)
        self.assertEqual(first['volume_shares'],30)
        self.assertEqual(later['trade_prints'],4)
        self.assertEqual(later['volume_shares'],40)
        self.assertLess(first['asof_cutoff'],later['asof_cutoff'])
        self.assertTrue(first['observed_through']<=first['asof_cutoff'])
        day=self.get(f'/api/profile?symbol=SPY&date={self.day}')
        self.assertEqual(day['volume_shares'],40)

    def test_invalid_request_returns_400_and_no_write_order_routes(self):
        for q in [f'/api/profile?symbol=SPY&date={self.day}&price_bin=0.07',
                  f'/api/profile?symbol=SPY&date={self.day}&timeframe=1m&bar=999',
                  '/api/profile?symbol=SPY&date=2027-01-01',
                  '/api/profile?symbol=SPY&bar=1']:
            with self.subTest(q=q),self.assertRaises(HTTPError) as err:
                self.get(q)
            self.assertEqual(err.exception.code,400)
            err.exception.close()
        with self.assertRaises(HTTPError) as err:
            self.get('/api/orders')
        self.assertEqual(err.exception.code,404)
        err.exception.close()

if __name__=='__main__':unittest.main()
