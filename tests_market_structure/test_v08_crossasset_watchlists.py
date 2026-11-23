"""v0.8: offline regression checks; no real Alpaca keys, network or broker orders."""
from __future__ import annotations
import gzip
import io
import json
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
import pandas as pd

from market_structure_lab.watchlist_v08 import (WATCHLISTS, SYMBOLS, EQUITIES,
                                                  catalog, record)
from market_structure_lab.cross_asset_v08 import CrossAssetEngine
from market_structure_lab.live_watchlist_v08 import WatchlistMonitor, normalize_snapshot
from market_structure_lab.sip_archive import dest_path,meta_path,file_sha256
from market_structure_lab.universe import select_symbols
from market_structure_lab.workstation import ResearchStore, make_handler


def daily(drift, days=95):
    t=pd.bdate_range('2026-04-01',periods=days)
    v=100*np.exp(np.arange(days)*drift+0.002*np.sin(np.arange(days)))
    return pd.DataFrame({'date':t,'open':v,'high':v*1.01,'low':v*.99,'close':v,'volume':1_000})


class WatchlistCatalogTests(unittest.TestCase):
    def test_exact_screenshot_groups_and_routing(self):
        self.assertEqual(len(SYMBOLS),66)
        self.assertEqual(len(EQUITIES),48)
        for x in ('VIX','ES1!','CL1!','DXY','SISE','FEDFUNDS','USIRYY','USM2','USOIL'):
            self.assertIn(x,SYMBOLS)
            self.assertIsNone(record(x)['provider_symbol'])
        for x,y in {'BTCUSD':'BTC/USD','XRPUSD':'XRP/USD','SOLUSD':'SOL/USD'}.items():
            self.assertEqual(record(x)['provider_symbol'],y)
        self.assertEqual(record('PDCE')['availability'],'retired_review_required')
        self.assertIn('TLT',select_symbols(['watchlist']))
        self.assertIn('QQQ',select_symbols(['watchlist']))
        self.assertEqual(catalog()['groups']['macro'],list(WATCHLISTS['macro']))

    def test_cli_explicit_symbols_are_not_augmented_with_core(self):
        import contextlib
        import io
        from market_structure_lab.universe_backfill import main
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            main(['plan','--symbols','NVDA','SMH',
                  '--start','2026-09-28','--end','2026-09-30'])
        self.assertIn('3 weekday candidates × 2 symbols',out.getvalue())
        self.assertNotIn('SPY   ',out.getvalue())
        self.assertIn('NVDA  ',out.getvalue())

    def test_unlisted_symbol_fails_closed(self):
        with self.assertRaises(ValueError):record('A_UNKNOWN')
        with self.assertRaises(ValueError):select_symbols(['watchlist'],['VIX'])


class CrossAssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name)
        self.data={'SPY':daily(.001), 'QQQ':daily(.002), 'NVDA':daily(.0028),'SMH':daily(.0025)}
        self.engine=CrossAssetEngine(self.root,self.data)

    def tearDown(self):self.tmp.cleanup()

    def test_daily_synchronized_no_lookahead(self):
        asof='2026-07-10'
        first=self.engine.snapshot(asof=asof,symbols=('SPY','NVDA','SMH'))
        self.assertFalse(first['future_data_used'])
        self.assertEqual(first['timeframe'],'1d')
        self.assertIsNotNone(first['rows'][0]['correlation'])
        later={k:v.copy(deep=True) for k,v in self.data.items()}
        for frame in later.values():
            frame.loc[frame['date']>pd.Timestamp(asof),'close']*=12
        second=CrossAssetEngine(self.root,later).snapshot(asof=asof,symbols=('SPY','NVDA','SMH'))
        self.assertEqual(first,second)

    def test_stale_and_unavailable_assets_not_filled(self):
        self.data['SMH']=self.data['SMH'].iloc[:10].copy()
        a=CrossAssetEngine(self.root,self.data).snapshot(asof='2026-07-10',symbols=('SMH','AMD'))
        smh=next(x for x in a['rows'] if x['symbol']=='SMH')
        amd=next(x for x in a['rows'] if x['symbol']=='AMD')
        self.assertTrue(smh['missing_or_stale'])
        self.assertIsNone(smh['correlation'])
        self.assertFalse(amd['available'])
        self.assertIsNone(amd['relative_to_target_pp'])

    def test_fail_closed_on_unsupported_timeframe(self):
        for kw in ({'timeframe':'5m'},{'feed':'unverified'},{'target':'VIX'}):
            with self.assertRaises(ValueError):self.engine.snapshot(asof='2026-06-01',**kw)
        with self.assertRaises(ValueError):
            self.engine.snapshot(asof='2026-06-01 10:05:00',timeframe='1m')

    def _archive(self,sym,day,shift=0):
        day=date_from(day)
        p=dest_path(self.root,'sip','bars',sym,day);p.parent.mkdir(parents=True,exist_ok=True)
        t0=pd.Timestamp(str(day)+'T09:30:00-04:00')
        data=[]
        for i in range(31):
            stamp=t0+pd.Timedelta(minutes=i+1)
            price=100+shift+i*.05
            data.append({'timestamp':stamp.isoformat(),'open':price,'high':price+.10,'low':price-.10,'close':price,'volume':1000})
        with gzip.open(p,'wt',encoding='utf-8',newline='') as fh:
            pd.DataFrame(data).to_csv(fh,index=False)
        meta={'feed':'sip','kind':'bars','symbol':sym,'session':str(day),'rows':len(data),'sha256':file_sha256(p)}
        meta_path(p).write_text(json.dumps(meta),encoding='utf-8')
        return p

    def test_minute_exact_timestamp_and_provenance(self):
        self._archive('QQQ','2026-09-30',0)
        self._archive('SPY','2026-09-30',10)
        obj=self.engine.snapshot(asof='2026-09-30T10:01:00-04:00',timeframe='1m',symbols=('SPY',),window=5)
        spy=next(x for x in obj['rows'] if x['symbol']=='SPY')
        self.assertTrue(spy['aligned_to_target']);self.assertEqual(spy['joint_observations'],31)
        self.assertEqual(spy['last_completed_at'],'2026-09-30T14:01:00+00:00')
        self.assertIsNotNone(spy['correlation'])
        prior=self.engine.snapshot(asof='2026-09-30T09:40:00-04:00',timeframe='1m',symbols=('SPY',),window=5)
        self.assertEqual(prior['rows'][0]['joint_observations'],10)

    def test_future_minute_mutation_cannot_change_earlier_snapshot(self):
        self._archive('QQQ','2026-09-30',0)
        target=self._archive('SPY','2026-09-30',10)
        original=self.engine.snapshot(asof='2026-09-30T09:40:00-04:00',
                                     timeframe='1m',symbols=('SPY',),window=5)
        with gzip.open(target,'rt',encoding='utf-8') as f:
            df=pd.read_csv(f)
        df.loc[20:,'close']*=20
        with gzip.open(target,'wt',encoding='utf-8',newline='') as f:
            df.to_csv(f,index=False)
        meta=json.loads(meta_path(target).read_text(encoding='utf-8'))
        meta['sha256']=file_sha256(target)
        meta_path(target).write_text(json.dumps(meta),encoding='utf-8')
        later=self.engine.snapshot(asof='2026-09-30T09:40:00-04:00',
                                    timeframe='1m',symbols=('SPY',),window=5)
        self.assertEqual(original,later)

    def test_wrong_eastern_offset_is_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.snapshot(asof='2026-09-30T10:00:00-05:00',timeframe='1m')

    def test_archive_corruption_rejected(self):
        self._archive('QQQ','2026-09-30')
        p=self._archive('SPY','2026-09-30')
        with p.open('ab') as f:f.write(b'changed')
        with self.assertRaises(ValueError):
            self.engine.snapshot(asof='2026-09-30T10:01:00-04:00',timeframe='1m',symbols=('SPY',))


def date_from(s):
    from datetime import date
    return date.fromisoformat(s)


class SnapshotTests(unittest.TestCase):
    def test_disabled_never_contacts_alpaca(self):
        def forbidden(*a,**kw):raise AssertionError('Unexpected network')
        obj=WatchlistMonitor(opener=forbidden)
        snap=obj.snapshot()
        self.assertEqual(snap['state'],'disabled')
        self.assertEqual(len(snap['instruments']),66)
        self.assertEqual(snap['instruments']['VIX']['status'],'unsupported_source')
        self.assertEqual(snap['instruments']['NVDA']['status'],'disabled')
        self.assertFalse(snap['orders_enabled'])

    def test_validated_mixed_stock_crypto_snapshots(self):
        now=datetime.now(timezone.utc).isoformat()
        calls=[]
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        def opener(req,timeout=20):
            calls.append(req)
            self.assertEqual(req.get_method(),'GET')
            self.assertNotIn('testsecret',req.full_url)
            if '/crypto/' in req.full_url:
                payload={'snapshots':{'BTC/USD':{'latestTrade':{'t':now,'p':101,'s':1}}}}
            else:
                payload={'snapshots':{'SPY':{'latestTrade':{'t':now,'p':550,'s':3}}}}
            return Response(json.dumps(payload).encode())
        obj=WatchlistMonitor(opener=opener,chunk_size=25)
        out=obj.poll_once('testkey','testsecret')
        self.assertEqual(len(calls),3)
        self.assertEqual(out['instruments']['SPY']['observation']['price'],550)
        self.assertEqual(out['instruments']['BTCUSD']['observation']['price'],101)
        self.assertEqual(out['instruments']['VIX']['status'],'unsupported_source')
        self.assertEqual(out['instruments']['NVDA']['status'],'unavailable')
        self.assertNotIn('testsecret',json.dumps(out))
        self.assertFalse(out['historical_persistence'])

    def test_stale_future_and_invalid_price_rejected(self):
        now=datetime.now(timezone.utc)
        self.assertIsNone(normalize_snapshot({'latestTrade':{'t':now.isoformat(),'p':-3}}))
        self.assertIsNone(normalize_snapshot({'latestTrade':{'t':(now+timedelta(hours=1)).isoformat(),'p':2}}))
        old=normalize_snapshot({'latestTrade':{'t':(now-timedelta(hours=1)).isoformat(),'p':3}})
        self.assertTrue(old['stale'])
        self.assertIsNone(normalize_snapshot({'latestQuote':{'t':now.isoformat(),'bp':5,'ap':3}}))


class ApiIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from market_structure_lab.demo import main as demo_main
        import sys
        cls.tmp=TemporaryDirectory();cls.root=Path(cls.tmp.name)
        orig=sys.argv[:]
        try:sys.argv=['demo','--output-dir',str(cls.root)];demo_main()
        finally:sys.argv=orig
        cls.store=ResearchStore(cls.root,cls.root/'notes.sqlite')
        import socket
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));cls.port=s.getsockname()[1]
        cls.monitor=WatchlistMonitor()
        cls.httpd=ThreadingHTTPServer(('127.0.0.1',cls.port),make_handler(cls.store,cls.port,watchlist=cls.monitor))
        cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown();cls.httpd.server_close();cls.thread.join(timeout=5);cls.tmp.cleanup()

    def request(self,path):
        with urlopen(f'http://127.0.0.1:{self.port}'+path,timeout=8) as f:return json.load(f)

    def test_all_readonly_endpoints_and_no_order_endpoint(self):
        w=self.request('/api/watchlist')
        self.assertEqual(len(w['symbols']),66)
        a=self.request('/api/live/watchlist')
        self.assertEqual(a['state'],'disabled')
        d=self.request('/api/cross-asset?target=QQQ&asof=2026-05-18&symbols=SPY,QQQ,SMH')
        self.assertEqual([x['symbol'] for x in d['rows']],['QQQ','SPY','SMH'])
        self.assertFalse(d['future_data_used'])
        with self.assertRaises(HTTPError) as cm:
            urlopen(f'http://127.0.0.1:{self.port}/api/orders',timeout=8)
        self.assertEqual(cm.exception.code,404);cm.exception.close()

    def test_ui_cross_market_tab(self):
        with urlopen(f'http://127.0.0.1:{self.port}/',timeout=8) as f:html=f.read().decode('utf-8')
        for token in ('tabCross','crossWorkspace','showCross','showWatchlist'):
            self.assertIn(token,html)
        self.assertNotIn('<script src=',html)

if __name__=='__main__':unittest.main()
