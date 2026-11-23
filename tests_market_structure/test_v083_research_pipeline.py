"""v0.8.3: point-in-time, calendar, provenance and cash-backed replay contracts."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import unittest

import numpy as np
import pandas as pd

from market_structure_lab.core import Config, evaluate_symbol
from market_structure_lab.cross_signals_v082 import CrossSignalResearch
from market_structure_lab.data_quality_v083 import audit_symbol, audit_universe, load_manifest, _xnys
from market_structure_lab.research_pipeline_v083 import create_study, export_study, initial_manifest, synthetic_demo
from market_structure_lab.strategy_v083 import (StrategyPolicy, CostAssumptions, _hash,
                                                kde_candidates, decisions_for_target,
                                                simulate_portfolio, _next_session)


class DataAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c=_xnys()
        cls.days=c.sessions_in_range('2026-09-01','2026-09-17').tz_localize(None)

    def frame(self, days=None):
        days=self.days if days is None else days
        n=len(days)
        return pd.DataFrame({'date':days,'open':[100.]*n,'high':[102.]*n,
                             'low':[99.]*n,'close':[101.]*n,'volume':[1000.]*n})

    def audit(self, frame, basis='raw',min_sessions=5):
        return audit_symbol('SPY',frame,source='FIXTURE',price_basis=basis,sha256='a'*64,min_sessions=min_sessions)

    def test_labor_day_is_not_fake_missing_session(self):
        a=self.audit(self.frame())
        self.assertEqual(a['errors'],[])
        self.assertNotIn('2026-09-07',a['missing_sessions'])

    def test_missing_exchange_day_rejected(self):
        df=self.frame().drop(index=3).reset_index(drop=True)
        a=self.audit(df)
        self.assertFalse(a['ready_for_fill_simulation'])
        self.assertIn('missing_exchange_sessions',a['errors'])

    def test_weekend_bar_rejected(self):
        df=self.frame();extra=df.iloc[0].copy();extra['date']=pd.Timestamp('2026-09-19')
        a=self.audit(pd.concat([df,pd.DataFrame([extra])],ignore_index=True))
        self.assertIn('non_exchange_session_dates',a['errors'])

    def test_unknown_or_adjusted_basis_is_not_fill_ready(self):
        self.assertIn('unknown_or_inconsistent_price_basis',self.audit(self.frame(),'unknown')['errors'])
        self.assertIn('non_raw_prices_not_fill_eligible',self.audit(self.frame(),'adjusted')['errors'])

    def test_invalid_ohlcv_rejected(self):
        df=self.frame();df.loc[0,'high']=10
        with self.assertRaises(ValueError):self.audit(df)

    def test_manifest_has_unsafe_paths_and_unknown_basis_blocked(self):
        with TemporaryDirectory() as root:
            base=Path(root)
            (base/'data').mkdir()
            df=self.frame()
            for symbol in ('SPY','QQQ','NVDA','SMH','XLK','IWM'):
                df.to_csv(base/'data'/f'{symbol}.csv',index=False)
            manifest=initial_manifest(base/'data',base/'manifest.json')
            records,daily=load_manifest(manifest)
            audit=audit_universe(records,daily,min_sessions=5)
            self.assertFalse(audit['ready'])
            self.assertEqual(set(audit['failed_symbols']),set(('SPY','QQQ','NVDA','SMH','XLK','IWM')))
            with self.assertRaises(FileExistsError):initial_manifest(base/'data',base/'manifest.json')
            j=json.loads(manifest.read_text());j['symbols']['SPY']['path']='../../outside.csv'
            manifest.write_text(json.dumps(j))
            with self.assertRaises(ValueError):load_manifest(manifest)


class StrategyDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=Config()
        rng=np.random.default_rng(1010)
        cls.days=_xnys().sessions_in_range('2025-01-02','2026-10-01')[:230].tz_localize(None)
        t=np.arange(len(cls.days));base=100+0.05*t+8*np.sin(t*.19)+rng.normal(0,.45,len(t))
        cls.daily={}
        for i,sym in enumerate(('SPY','QQQ','NVDA','SMH','XLK','IWM')):
            close=base*(.8+.05*i) + .5*np.sin(t*.3+i)
            op=close+rng.normal(0,.15,len(t))
            cls.daily[sym]=pd.DataFrame({'date':cls.days,'open':op,'high':np.maximum(op,close)+1.4,
                                        'low':np.minimum(op,close)-1.4,'close':close,'volume':1000})
        cls.context=CrossSignalResearch(cls.daily)

    def test_kde_candidate_scanner_agrees_with_original_math(self):
        bars=self.daily['SPY']
        _,original=evaluate_symbol(bars,'SPY',self.cfg)
        events=kde_candidates(bars,'SPY',self.cfg)
        actual=[(x['signal_date'],x['direction'],x['level_asof_date']) for x in events.values()]
        prior=[(r.signal_date,r.direction,r.level_asof_date) for r in original.itertuples() if r.source=='clustered']
        self.assertEqual(actual,prior)

    def test_future_mutation_does_not_modify_past_decisions(self):
        a=decisions_for_target(self.daily['QQQ'],'QQQ',self.context,StrategyPolicy())
        changed={k:v.copy(deep=True) for k,v in self.daily.items()}
        for k,df in changed.items():
            df.loc[df.index[-12:],'close']*=4
            df.loc[df.index[-12:],'high']*=4
            df.loc[df.index[-12:],'open']*=4
        b=decisions_for_target(changed['QQQ'],'QQQ',CrossSignalResearch(changed),StrategyPolicy())
        cutoff=self.days[-13].strftime('%Y-%m-%d')
        for mode in a:
            early=lambda decisions:[x for x in decisions if x['asof_completed_session']<=cutoff]
            self.assertEqual(early(a[mode]),early(b[mode]))

    def test_no_trade_short_and_missing_factor_are_explicit(self):
        decisions=decisions_for_target(self.daily['SPY'],'SPY',CrossSignalResearch({'SPY':self.daily['SPY']}),StrategyPolicy())
        self.assertEqual(len(decisions['kde_cross_confirmed']),len(self.days)-self.cfg.lookback)
        self.assertTrue(all(d['action']=='NO_TRADE' for d in decisions['kde_cross_confirmed']))
        self.assertTrue(all(d['no_orders'] and d['research_only'] for d in decisions['kde_cross_confirmed']))
        self.assertTrue(all(d['earliest_eligible_session']>d['asof_completed_session'] for d in decisions['kde_cross_confirmed']))


class CashBackedReplayTests(unittest.TestCase):
    def setUp(self):
        self.days=_xnys().sessions_in_range('2026-09-01','2026-09-18').tz_localize(None)
        self.daily={sym:pd.DataFrame({'date':self.days,'open':[100]*len(self.days),
              'high':[101]*len(self.days),'low':[99]*len(self.days),'close':[100]*len(self.days),
              'volume':[1000]*len(self.days)}) for sym in ('SPY','QQQ')}
        self.policy=StrategyPolicy()

    def decision(self,day,sym='SPY'):
        d={'schema':'quantdesk.decision.v1','policy_id':_hash({'policy':asdict(self.policy),'kde':asdict(Config())}),
           'variant':'kde_cross_confirmed','symbol':sym,'asof_completed_session':day,
           'earliest_eligible_session':_next_session(day),'action':'BUY_CANDIDATE',
           'reason':'eligible_long_candidate','direction':1,'evidence_sha256':'e'*64,
           'research_only':True,'no_orders':True}
        d['decision_id']=_hash(d)
        return d

    def test_cash_and_costs_are_conservative(self):
        d=[self.decision('2026-09-01')]
        no=simulate_portfolio(self.daily,d,costs=CostAssumptions(0,0,0))
        with_cost=simulate_portfolio(self.daily,d,costs=CostAssumptions(4,4,0))
        self.assertAlmostEqual(no['ending_equity'],100,places=5)
        self.assertLess(with_cost['ending_equity'],no['ending_equity'])
        self.assertEqual(no['completed_trades'],1)
        self.assertEqual(no['trades'][0]['entry_date'],'2026-09-02')
        self.assertEqual(no['trades'][0]['exit_date'],'2026-09-04')
        self.assertTrue(all(row['cash']>=-1e-8 for row in with_cost['equity']))

    def test_overlaps_rejected_and_position_limit(self):
        d=[self.decision('2026-09-01'),self.decision('2026-09-02')]
        out=simulate_portfolio(self.daily,d)
        self.assertEqual(out['completed_trades'],1)
        self.assertEqual(out['skipped'][0]['reason'],'position_limit_or_overlap')

    def test_insufficient_cash_and_no_unclosed_outcome_fills(self):
        d=[self.decision('2026-09-01')]
        no=simulate_portfolio(self.daily,d,costs=CostAssumptions(min_order_notional=50))
        self.assertEqual(no['completed_trades'],0)
        self.assertEqual(no['ending_equity'],100)
        last=self.days[-2].strftime('%Y-%m-%d')
        missing=simulate_portfolio(self.daily,[self.decision(last)])
        self.assertEqual(missing['completed_trades'],0)
        self.assertIn('outcome_not_yet_completed',missing['skipped'][0]['reason'])

    def test_rejects_duplicate_forged_or_future_order_decisions(self):
        d=self.decision('2026-09-01')
        with self.assertRaises(ValueError):simulate_portfolio(self.daily,[d,d])
        altered=dict(d,action='BUY_CANDIDATE',direction=-1)
        with self.assertRaises(ValueError):simulate_portfolio(self.daily,[altered])
        wrong=dict(d,earliest_eligible_session='2026-09-01')
        wrong['decision_id']=_hash({k:v for k,v in wrong.items() if k!='decision_id'})
        with self.assertRaises(ValueError):simulate_portfolio(self.daily,[wrong])


class ReproducibleReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory()
        cls.root=Path(cls.tmp.name)
        manifest=synthetic_demo(cls.root/'demo',sessions=260)
        cls.records,cls.daily=load_manifest(manifest)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_identical_runs_and_safe_no_overwrite(self):
        a=create_study(self.records,self.daily,min_sessions=250)
        b=create_study(self.records,self.daily,min_sessions=250)
        self.assertEqual(a['manifest'],b['manifest'])
        self.assertEqual(a['decisions'],b['decisions'])
        self.assertEqual(a['results'],b['results'])
        path=self.root/'study'
        export_study(a,path)
        with self.assertRaises(FileExistsError):export_study(a,path)
        self.assertIn('RETROSPECTIVE_PREVIOUSLY_EXAMINED',json.loads((path/'report.json').read_text())['evaluation_label'])
        self.assertNotIn('https://',(path/'report.html').read_text())
        self.assertTrue((path/'decisions.json').exists())

    def test_misaligned_peer_dates_fail_without_imputation(self):
        other={k:v.copy(deep=True) for k,v in self.daily.items()}
        other['NVDA']=other['NVDA'].drop(index=4).reset_index(drop=True)
        with self.assertRaises(ValueError):create_study(self.records,other,min_sessions=250)


if __name__=='__main__':unittest.main()
