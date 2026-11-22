"""Point-in-time market intelligence, live source segregation, and API contracts."""
import json
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import numpy as np
import pandas as pd

from market_structure_lab.market_intelligence import MarketIntelligence
from market_structure_lab.live_tape import LiveTape
from market_structure_lab.workstation import ResearchStore, make_handler


def series(days=110, start='2026-01-01', drift=.003):
    dates=pd.bdate_range(start,periods=days)
    p=100*np.exp(np.arange(days)*drift + 0.012*np.sin(np.arange(days)*.7))
    return pd.DataFrame({'date':dates,'open':p,'high':p*1.005,'low':p*.995,'close':p,'volume':2000})


class ResearchMath(unittest.TestCase):
    def setUp(self):
        self.dir=TemporaryDirectory(); self.base=Path(self.dir.name)
        self.daily={'SPY':series(), 'QQQ':series(drift=.0035)}

    def tearDown(self):self.dir.cleanup()

    def test_snapshot_asof_and_regime(self):
        eng=MarketIntelligence(self.base,self.daily)
        a=eng.snapshot('2026-05-21',requested_session='2026-05-22')
        self.assertEqual(a['asof_completed_session'],'2026-05-21')
        self.assertEqual(a['requested_session'],'2026-05-22')
        self.assertFalse(a['future_data_used'])
        self.assertIn('spy_qqq_corr_20d',a['indicators'])
        self.assertIsNotNone(a['indicators']['spy_qqq_corr_20d'])
        self.assertIn(a['regime']['spy_20d_momentum'],('positive','mixed','negative','insufficient_history'))

    def test_mutating_future_never_changes_past(self):
        date='2026-04-14'
        a=MarketIntelligence(self.base,self.daily).snapshot(date)
        changed={s:d.copy(deep=True) for s,d in self.daily.items()}
        for d in changed.values():d.loc[d['date']>pd.Timestamp(date),'close']*=17
        b=MarketIntelligence(self.base,changed).snapshot(date)
        self.assertEqual(a,b)

    def test_context_data_only_through_cutoff(self):
        ctx=self.base/'context';ctx.mkdir()
        f=ctx/'XLK.csv';d=series().copy();d.to_csv(f,index=False)
        a=MarketIntelligence(self.base,self.daily).snapshot('2026-03-31')
        d.loc[d['date']>pd.Timestamp('2026-03-31'),['open','high','low','close']]*=23;d.to_csv(f,index=False)
        b=MarketIntelligence(self.base,self.daily).snapshot('2026-03-31')
        self.assertEqual(a['assets']['XLK'],b['assets']['XLK'])
        self.assertEqual(a['indicators']['relative_strength_20d_pp'],b['indicators']['relative_strength_20d_pp'])

    def test_missing_or_stale_assets_not_invented(self):
        eng=MarketIntelligence(self.base,self.daily)
        a=eng.snapshot('2026-08-03')
        self.assertFalse(a['assets']['IWM']['available'])
        self.assertTrue(a['assets']['SPY']['stale'])
        self.assertIsNone(a['indicators']['relative_strength_20d_pp']['QQQ'])
        self.assertEqual(a['regime']['spy_20d_momentum'],'insufficient_history')


class LiveTests(unittest.TestCase):
    def test_disabled_without_network_and_iex_scope(self):
        x=LiveTape(('SPY','QQQ'))
        s=x.snapshot()
        self.assertFalse(s['enabled'])
        self.assertEqual(s['scope'],'IEX_SINGLE_VENUE_ONLY')
        self.assertIsNone(s['last_received_utc'])
        self.assertFalse(s['orders_enabled'])

    def test_ingest_and_reject_bad_future_and_old(self):
        x=LiveTape(('SPY',),'sip')
        now=datetime.now(timezone.utc)
        t=now.isoformat();older=(now-timedelta(seconds=12)).isoformat()
        x.ingest([{'T':'t','S':'SPY','t':t,'p':700,'s':10},
                  {'T':'t','S':'SPY','t':older,'p':200,'s':1},
                  {'T':'t','S':'QQQ','t':t,'p':900,'s':5},
                  {'T':'t','S':'SPY','t':t,'p':-1,'s':2}])
        a=x.snapshot()
        self.assertEqual(a['events_received'],1)
        self.assertEqual(a['symbols']['SPY']['last_trade']['price'],700)
        self.assertEqual(a['scope'],'CONSOLIDATED_US_EQUITIES')

    def test_no_credentials_in_readonly_snapshot(self):
        x=LiveTape(('SPY',))
        x.ingest([{'T':'q','S':'SPY','t':datetime.now(timezone.utc).isoformat(),
                   'bp':100,'ap':100.01,'bs':50,'as':30}])
        self.assertEqual(x.snapshot()['symbols']['SPY']['last_quote']['ask'],100.01)
        self.assertNotIn('secret',json.dumps(x.snapshot()))

    def test_invalid_symbols_disallowed(self):
        for symbols in [(), ('../../evil',),tuple('S'+str(i) for i in range(17))]:
            with self.assertRaises(ValueError):LiveTape(symbols)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use synthetic demo generated using public module's CLI.
        from market_structure_lab.demo import main as demo_main
        import sys
        cls.tmp=TemporaryDirectory();cls.base=Path(cls.tmp.name)
        old=sys.argv[:]
        try:sys.argv=['demo','--output-dir',str(cls.base)];demo_main()
        finally:sys.argv=old
        cls.store=ResearchStore(cls.base,cls.base/'notes.sqlite')
        cls.live=LiveTape()
        # Bind an ephemeral port, then supply that exact port to the Host validator.
        import socket
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        cls.httpd=ThreadingHTTPServer(('127.0.0.1',port),make_handler(cls.store,port,cls.live))
        cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{port}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown();cls.httpd.server_close();cls.thread.join(timeout=5);cls.tmp.cleanup()

    def test_new_endpoints_causal(self):
        with urlopen(self.url+'/api/intelligence?date=2026-05-18',timeout=5) as f:
            a=json.load(f)
        self.assertEqual(a['requested_session'],'2026-05-18')
        self.assertLess(a['asof_completed_session'],'2026-05-18')
        with urlopen(self.url+'/api/live',timeout=5) as f:b=json.load(f)
        self.assertFalse(b['enabled']);self.assertFalse(b['orders_enabled'])
        with urlopen(self.url+'/api/status',timeout=5) as f:c=json.load(f)
        self.assertEqual(c['version'],'0.6')

    def test_future_session_rejected_and_no_order_route(self):
        for p in ['/api/intelligence?date=2040-01-01','/api/place_order']:
            with self.assertRaises(HTTPError) as cm:urlopen(self.url+p,timeout=5)
            self.assertIn(cm.exception.code,[400,404])
            cm.exception.close()

    def test_ui_tabs_do_not_include_remote_assets(self):
        with urlopen(self.url+'/',timeout=5) as f:s=f.read().decode()
        for token in ('liveWorkspace','replayWorkspace','researchWorkspace','showIntelligence','showLive'):
            self.assertIn(token,s)
        self.assertNotIn('<script src=',s)
        self.assertNotIn('<link href="https://',s)

if __name__=='__main__':unittest.main()

class ContextImporterTests(unittest.TestCase):
    def test_readonly_historical_context_download_and_save(self):
        import io
        from market_structure_lab.fetch_alpaca_context import fetch, save
        t='2026-09-30T04:00:00Z'
        class Reader(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        calls=[]
        def opener(req,timeout=30):
            calls.append((req.full_url,req.get_method()))
            return Reader(json.dumps({'bars':[{'t':t,'o':100,'h':103,'l':99,'c':101,'v':500}],
                                      'next_page_token':None}).encode())
        rows=fetch('XLK','2026-09-30','2026-09-30','sip','fakekey','fakesecret',opener)
        self.assertEqual(rows[0]['date'],'2026-09-30')
        self.assertEqual(calls[0][1],'GET')
        self.assertIn('/v2/stocks/XLK/bars',calls[0][0])
        with TemporaryDirectory() as d:
            target=Path(d)/'XLK.csv'
            save(rows,target,{'feed':'SIP'})
            self.assertTrue(target.exists())
            self.assertTrue(target.with_suffix('.meta.json').exists())
            with self.assertRaises(FileExistsError):save(rows,target,{'feed':'SIP'})

    def test_rejects_unapproved_context_symbol(self):
        from market_structure_lab.fetch_alpaca_context import fetch
        with self.assertRaises(ValueError):
            fetch('SPY','2026-01-01','2026-02-01','sip','x','y',lambda *a,**kw:None)
