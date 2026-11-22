"""v0.7 research contract: causality, outcomes, splits, honest interpretation."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
import pandas as pd

from market_structure_lab.core import Config, evaluate_symbol
from market_structure_lab.experiment_lab import StudySettings, study_events
from market_structure_lab.workstation import ResearchStore, make_handler
from http.server import ThreadingHTTPServer
from threading import Thread


def sample_bars():
    days = pd.bdate_range('2024-01-02', periods=330)
    x = np.arange(len(days),dtype=float)
    center = 100. + .045*x + 3.0*np.sin(x/4.8) + 1.1*np.sin(x/10.3)
    return pd.DataFrame({'date':days,'open':center-.22,'high':center+1.5,
                         'low':center-1.5,'close':center+.18,'volume':10000+x*2})

class StudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bars = sample_bars()
        cls.config = Config(lookback=80,forward_bars=3)
        _, cls.events = evaluate_symbol(cls.bars,'SPY',cls.config)
        if cls.events.empty:
            raise AssertionError('Study fixture must produce events')

    def study(self, settings=StudySettings()):
        return study_events(self.bars,self.events,'SPY',settings,'test-sha',self.config.lookback)

    def test_reproducible_result_and_source_provenance(self):
        first=self.study();again=self.study()
        self.assertEqual(first,again)
        self.assertEqual(first['source_sha256'],'test-sha')
        self.assertIn('NOT an untouched holdout',first['warnings'][0])
        self.assertEqual(len(first['results']),6)

    def test_cost_sensitivity_exact(self):
        a=self.study(StudySettings(roundtrip_cost_bps=0))
        b=self.study(StudySettings(roundtrip_cost_bps=20))
        for x,y in zip(a['results'],b['results']):
            self.assertEqual(x['trades'],y['trades'])
            if x['trades']:
                self.assertAlmostEqual(x['mean_net_pct']-y['mean_net_pct'],.2,places=7)

    def test_events_never_enter_before_signal_close(self):
        x=self.study()
        for event in x['events']:
            self.assertLess(event['level_asof_date'],event['signal_date'])
            self.assertLess(event['signal_date'],event['entry_date'])
            self.assertLessEqual(event['entry_date'],event['exit_date'])
            self.assertLessEqual(event['mae'],0)
            self.assertGreaterEqual(event['mfe'],0)

    def test_no_holding_period_crosses_partition_boundary(self):
        x=self.study()
        for event in x['events']:
            part=event['partition']
            if part=='PURGED_BOUNDARY':continue
            start=x['split_sessions'][part]['first']
            stop=x['split_sessions'][part]['last']
            self.assertLessEqual(start,event['entry_date'])
            self.assertLessEqual(event['exit_date'],stop)
        self.assertEqual(sum(z['trades'] for z in x['results'])+x['purged_boundary_events'],x['candidate_events'])

    def test_reject_future_asof_and_invalid_source_price(self):
        x=self.events.copy(deep=True)
        x.loc[x.index[0],'level_asof_date']=x.loc[x.index[0],'signal_date']
        with self.assertRaises(ValueError):study_events(self.bars,x,'SPY',lookback=80)
        x=self.events.copy(deep=True)
        x.loc[x.index[0],'entry_price']=999.
        with self.assertRaises(ValueError):study_events(self.bars,x,'SPY',lookback=80)

    def test_data_mutation_after_an_outcome_cannot_change_earlier_pnl(self):
        # Precomputed causal events cannot depend on future bars beyond their exit.
        first=self.study()
        changed=self.bars.copy(deep=True)
        changed.loc[changed.index[-1],['open','high','low','close']]*=1.01
        # A changed late price should not affect earlier event outcomes.
        result=study_events(changed,self.events,'SPY',lookback=80)
        lhs={(e['source'],e['signal_date']):e['net_proxy_return'] for e in first['events']
             if e['exit_date']<str(changed.iloc[-1].date.date())}
        rhs={(e['source'],e['signal_date']):e['net_proxy_return'] for e in result['events']
             if e['exit_date']<str(changed.iloc[-1].date.date())}
        self.assertEqual(lhs,rhs)

    def test_wrong_symbol_or_cost_rejected(self):
        with self.assertRaises(ValueError):self.study(StudySettings(roundtrip_cost_bps=float('nan')))
        with self.assertRaises(ValueError):StudySettings(roundtrip_cost_bps=-1)
        with self.assertRaises(ValueError):study_events(self.bars,self.events,'FAKE',lookback=80)

    def test_mfe_mae_exact_path_extremes(self):
        bars=self.bars.copy(deep=True)
        ev=self.events.head(1).copy()
        row=ev.iloc[0]
        b=bars.index[bars.date==pd.Timestamp(row.entry_date)][0]
        c=bars.index[bars.date==pd.Timestamp(row.exit_date)][0]
        direction=int(row.direction)
        results=study_events(bars,ev,'SPY',lookback=80)['events'][0]
        high=float(bars.iloc[b:c+1].high.max())
        low=float(bars.iloc[b:c+1].low.min())
        entry=float(row.entry_price)
        favorable=(high-entry)/entry if direction==1 else (entry-low)/entry
        adverse=(low-entry)/entry if direction==1 else (entry-high)/entry
        self.assertAlmostEqual(results['mfe'],max(0,favorable))
        self.assertAlmostEqual(results['mae'],min(0,adverse))

class StudyApiTests(unittest.TestCase):
    def test_read_only_route_and_bad_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            bars=sample_bars().copy()
            bars['date']=bars.date.dt.strftime('%Y-%m-%d')
            for symbol in ('SPY','QQQ'):
                bars.to_csv(folder/f'{symbol}.csv',index=False)
            store=ResearchStore(folder,folder/'notes.sqlite',config=Config(lookback=80))
            server=ThreadingHTTPServer(('127.0.0.1',0),lambda *args:make_handler(store,0)(*args))
            # The route expects an explicit trusted Host port. Build server on a
            # free port with matching handler and address.
            server.server_close()
            import socket
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            server=ThreadingHTTPServer(('127.0.0.1',port),make_handler(store,port))
            thread=Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with urlopen(f'http://127.0.0.1:{port}/api/experiments?symbol=SPY&cost_bps=5',timeout=20) as response:
                    data=json.load(response)
                self.assertEqual(data['version'],'0.7.0')
                self.assertEqual(data['symbol'],'SPY')
                self.assertTrue(data['research_only'])
                self.assertIn('source_sha256',data)
                for path in ('/api/experiments?symbol=SPY&cost_bps=-1', '/api/experiments?symbol=ABC'):
                    with self.assertRaises(HTTPError) as err:
                        urlopen(f'http://127.0.0.1:{port}'+path,timeout=20)
                    self.assertEqual(err.exception.code,400)
                    err.exception.close()
                with self.assertRaises(HTTPError) as err:
                    urlopen(f'http://127.0.0.1:{port}/api/orders',timeout=20)
                self.assertEqual(err.exception.code,404)
                err.exception.close()
            finally:
                server.shutdown();server.server_close();thread.join(timeout=4)

    def test_research_ui_is_local_and_text_only(self):
        ui=(Path(__file__).resolve().parents[1]/'market_structure_lab/assets/workstation.html').read_text(encoding='utf8')
        self.assertIn('id="experimentPanel"',ui)
        self.assertIn('/api/experiments?',ui)
        self.assertIn('r.sample.replaceAll',ui)
        self.assertNotIn('innerHTML=',ui)

if __name__=='__main__':unittest.main()
