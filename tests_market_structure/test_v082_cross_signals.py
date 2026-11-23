"""v0.8.2: causal cross-market signal factors and retrospective KDE comparisons."""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path
import socket
import threading
import unittest
from http.server import ThreadingHTTPServer
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
import pandas as pd

from market_structure_lab.cross_signals_v082 import CrossSignalResearch, PEERS
from market_structure_lab.workstation import ResearchStore, make_handler


def fixture(n=260):
    dates = pd.bdate_range('2025-09-01', periods=n)
    x = np.linspace(0, 36, n)
    common = 140 * np.exp(.0004*np.arange(n) + .013*np.sin(x))
    def make(y):
        return pd.DataFrame({'date':dates,'open':y*.997,'high':y*1.015,
                             'low':y*.985,'close':y,'volume':1000})
    return {
        'QQQ':make(common), 'SPY':make(common*.92*(1+.004*np.cos(x*.6))),
        'NVDA':make(common*.8*(1+.011*np.sin(x*.8))),
        'SMH':make(common*.7*(1+.007*np.cos(x*1.3))),
        'XLK':make(common*.6*(1+.009*np.sin(x*1.1))),
        'IWM':make(common*.5*(1+.012*np.cos(x*.85))),
    }


class CausalFactors(unittest.TestCase):
    def setUp(self):
        self.data=fixture()
        self.date=self.data['QQQ'].iloc[130]['date'].strftime('%Y-%m-%d')

    def test_prior_fit_is_independent_of_future_data(self):
        a=CrossSignalResearch(self.data).snapshot(asof=self.date,target='QQQ',direction=1)
        newer={k:v.copy(deep=True) for k,v in self.data.items()}
        for f in newer.values():
            f.loc[f.date>pd.Timestamp(self.date),'close']*=50
        b=CrossSignalResearch(newer).snapshot(asof=self.date,target='QQQ',direction=1)
        self.assertEqual(a,b)
        self.assertFalse(a['future_data_used'])
        self.assertEqual(a['coverage'],4)
        self.assertTrue(all(x.get('last_completed_at')==self.date for x in a['peers'] if x['available']))

    def test_current_day_not_used_in_regression_coefficients(self):
        today=pd.Timestamp(self.date)
        start=self.data['QQQ']['date'].to_list().index(today)
        original=CrossSignalResearch(self.data).snapshot(asof=self.date)
        mutated={k:v.copy(deep=True) for k,v in self.data.items()}
        mutated['NVDA'].loc[start,'close']*=1.04
        new=CrossSignalResearch(mutated).snapshot(asof=self.date)
        before=next(x for x in original['peers'] if x['symbol']=='NVDA')
        after=next(x for x in new['peers'] if x['symbol']=='NVDA')
        self.assertEqual(before['beta_prior'],after['beta_prior'])
        self.assertEqual(before['historical_corr_prior'],after['historical_corr_prior'])
        self.assertEqual(before['lead_lag_corr_prior'],after['lead_lag_corr_prior'])
        self.assertNotEqual(before['residual_pp'],after['residual_pp'])

    def test_missing_peers_never_forward_filled(self):
        missing={k:v.copy(deep=True) for k,v in self.data.items()}
        for peer in PEERS:
            missing[peer]=missing[peer].loc[missing[peer]['date']!=pd.Timestamp(self.date)]
        result=CrossSignalResearch(missing).snapshot(asof=self.date)
        self.assertEqual(result['state'],'unavailable')
        self.assertEqual(result['coverage'],0)
        self.assertEqual(result['reason'],'insufficient_aligned_peers')
        self.assertTrue(all(not x['available'] for x in result['peers']))
        self.assertIsNone(result['confirming_peer_fraction'])

    def test_missing_prior_session_not_bridged(self):
        data={k:v.copy(deep=True) for k,v in self.data.items()}
        prior=self.data['QQQ'].iloc[125]['date']
        data['NVDA']=data['NVDA'].loc[data['NVDA']['date']!=prior]
        row=next(x for x in CrossSignalResearch(data).snapshot(asof=self.date)['peers'] if x['symbol']=='NVDA')
        self.assertFalse(row['available'])

    def test_input_rejections(self):
        obj=CrossSignalResearch(self.data)
        for kwargs in ({'asof':'2026-07-01','target':'VIX'},
                       {'asof':self.date,'direction':0},
                       {'asof':'2026-01-15T16:00:00-05:00'},
                       {'asof':'not-a-date'}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):obj.snapshot(**kwargs)
        bad={k:v.copy(deep=True) for k,v in self.data.items()}
        bad['SMH']=bad['SMH'].iloc[::-1].reset_index(drop=True)
        with self.assertRaises(ValueError):CrossSignalResearch(bad)
        with self.assertRaises(ValueError):CrossSignalResearch(self.data,window=5)

    def test_retro_partition_and_cost_match_baseline_population(self):
        obj=CrossSignalResearch(self.data)
        days=self.data['QQQ']['date'].dt.strftime('%Y-%m-%d').tolist()
        base_event=lambda a,p,r:dict(symbol='QQQ',source='clustered',signal_date=days[a],
             entry_date=days[a+1],exit_date=days[a+3],direction=1,
             partition=p,net_proxy_return=r)
        events=[base_event(130,'development',.01),base_event(140,'development',-.005),
                base_event(180,'validation',.002),base_event(200,'retrospective_test',-.002),
                base_event(210,'PURGED_BOUNDARY',.30)]
        events.append(dict(base_event(131,'development',.99),source='prior_day_extremes'))
        source=dict(symbol='QQQ',research_only=True,events=events,
                    purged_boundary_events=1,settings={'roundtrip_cost_bps':5},split_sessions={})
        result=obj.evaluate(target='QQQ',study=source)
        self.assertEqual(result['studied_events'],4)
        self.assertEqual(result['comparison'][0]['baseline']['events'],2)
        self.assertAlmostEqual(result['comparison'][0]['baseline']['mean_net_pct'],.25)
        self.assertNotIn('0.99',json.dumps(result))
        self.assertTrue(result['research_only'])
        self.assertTrue(result['future_data_used_for_factors'] is False)
        self.assertEqual(len(result['events']),4)

    def test_study_rejects_unverified_and_misordered_events(self):
        obj=CrossSignalResearch(self.data)
        with self.assertRaises(ValueError):obj.evaluate(target='SPY',study={'symbol':'QQQ','research_only':True,'events':[]})
        with self.assertRaises(ValueError):obj.evaluate(target='QQQ',study={'symbol':'QQQ','events':[]})
        fake=dict(symbol='QQQ',research_only=True,events=[dict(symbol='QQQ',source='clustered',
                signal_date='2025-04-10',entry_date='2025-04-09',exit_date='2025-04-11',
                partition='development',direction=1,net_proxy_return=.1)])
        with self.assertRaises(ValueError):obj.evaluate(target='QQQ',study=fake)


class ApiAndUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory();root=Path(cls.tmp.name)
        (root/'data/context').mkdir(parents=True)
        frames=fixture(320)
        for symbol,frame in frames.items():
            frame.to_csv(root/'data'/(symbol+'.csv') if symbol in ('SPY','QQQ') else root/'data/context'/(symbol+'.csv'),index=False)
        cls.store=ResearchStore(root/'data',root/'notes.sqlite')
        with socket.socket() as so:
            so.bind(('127.0.0.1',0));cls.port=so.getsockname()[1]
        cls.httpd=ThreadingHTTPServer(('127.0.0.1',cls.port),make_handler(cls.store,cls.port))
        cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown();cls.httpd.server_close();cls.thread.join(timeout=3);cls.tmp.cleanup()

    def req(self,path):
        with urlopen('http://127.0.0.1:'+str(self.port)+path,timeout=15) as response:
            return json.load(response)

    def test_readonly_routes(self):
        d=self.req('/api/cross-signal?target=QQQ&asof=2026-01-21&direction=-1')
        self.assertEqual(d['version'],'0.8.2')
        self.assertFalse(d['future_data_used'])
        self.assertTrue(d['no_orders'])
        study=self.req('/api/cross-study?target=QQQ&cost_bps=5')
        self.assertEqual(study['version'],'0.8.2')
        self.assertEqual(len(study['comparison']),3)
        self.assertEqual(study['signal_source'],'clustered')
        with self.assertRaises(HTTPError) as cm:
            self.req('/api/cross-signal?target=VIX&asof=2026-01-21')
        self.assertEqual(cm.exception.code,400);cm.exception.close()
        with self.assertRaises(HTTPError) as cm:
            self.req('/api/orders')
        self.assertEqual(cm.exception.code,404);cm.exception.close()

    def test_ui_is_local_and_optional(self):
        html=(Path(__file__).resolve().parents[1]/'market_structure_lab/assets/workstation.html').read_text(encoding='utf-8')
        for token in ('signalLab','signalInspect','signalEvaluate','showSignalClose',
                      'showSignalStudy','/api/cross-study','/api/cross-signal'):
            self.assertIn(token,html)
        self.assertIn('<details class="signalLab"',html)
        self.assertNotIn('<script src=',html)

if __name__=='__main__':unittest.main()
