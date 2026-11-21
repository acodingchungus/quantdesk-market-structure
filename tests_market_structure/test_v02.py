import json
import tempfile
import unittest
from pathlib import Path
import pandas as pd
import numpy as np
from market_structure_lab.core import Config, evaluate_symbol
from market_structure_lab.replay_model import make_replay
from market_structure_lab.replay_view import write_replay_html
from market_structure_lab.validation import matched_controls, summarize_matched, _eligible_sample, _bh_fdr


def bars(n=280):
    dates=pd.bdate_range('2024-01-02',periods=n)
    x=np.arange(n,dtype=float)
    c=100+4*np.sin(x/7)+.03*x
    o=c+.15*np.cos(x/2)
    h=np.maximum(c,o)+.5
    l=np.minimum(c,o)-.5
    return pd.DataFrame({'date':dates,'open':o,'high':h,'low':l,'close':c,'volume':np.full(n,100000.)})


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.cfg=Config(lookback=75,forward_bars=3,holdout_date='2024-11-01')

    def test_maps_from_previous_completed_session(self):
        d=bars()
        maps,_=evaluate_symbol(d,'QQQ',self.cfg)
        frames,_=make_replay(d,'QQQ',self.cfg,maps)
        self.assertEqual(frames[0]['index'],75)
        self.assertEqual(frames[-1]['index'],len(d)-1)
        for f in frames:
            self.assertLess(f['map_asof_date'],f['date'])
            for z in f['levels']:
                self.assertLess(z['asof_date'],f['date'])
                self.assertLessEqual(z['first_seen'],f['date'])

    def test_future_mutation_does_not_change_old_replay(self):
        d=bars(255)
        f1,_=make_replay(d,'SPY',self.cfg)
        altered=d.copy()
        altered.loc[225:,['open','high','low','close']]*=3
        f2,_=make_replay(altered,'SPY',self.cfg)
        self.assertEqual(f1[:100],f2[:100])

    def test_cached_maps_match_fresh_discovery(self):
        d=bars(210)
        maps,_=evaluate_symbol(d,'SPY',self.cfg)
        a,_=make_replay(d,'SPY',self.cfg,maps)
        b,_=make_replay(d,'SPY',self.cfg)
        for va,vb in zip(a,b):
            self.assertEqual([round(x['price'],9) for x in va['levels']],
                             [round(x['price'],9) for x in vb['levels']])

    def test_labels_bounce_breakout_and_failure_not_early(self):
        from unittest.mock import patch
        from market_structure_lab.core import Level
        d=bars(90)
        # Fixed pivot levels reported ONLY as known on t-1.
        # t=75 support bounce, t=76 breakdown, t=78 recovers beyond frozen top.
        d.loc[74,['open','close','high','low']]=[105,105,106,104]
        d.loc[75,['open','close','high','low']]=[105,105,106,99.5]
        d.loc[76,['open','close','high','low']]=[104,98,105,97]
        d.loc[77,['open','close','high','low']]=[98,98,100,97]
        d.loc[78,['open','close','high','low']]=[98,105,106,97]
        known=pd.DataFrame([{'symbol':'SPY','effective_date':str(d.iloc[t].date.date()),
                             'price':100.,'radius':1.,'pivot_count':3,'strength':2.,
                             'level_asof_date':str(d.iloc[t-1].date.date())} for t in range(75,90)])
        _,r=make_replay(d,'SPY',self.cfg,known)
        q=r[['index','type']].values.tolist()
        self.assertIn([75,'rejection_up'],q)
        self.assertIn([76,'breakout_down'],q)
        self.assertIn([78,'failed_breakout_confirmed'],q)
        self.assertFalse(((r['index']==76)&(r.type=='failed_breakout_confirmed')).any())

    def test_self_contained_html_and_no_external_urls(self):
        d=bars(110)
        frames,r=make_replay(d,'QQQ',self.cfg)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'Q.html'
            write_replay_html(d,frames,r,'QQQ',p)
            html=p.read_text('utf8')
            self.assertIn('type="application/json"',html)
            self.assertNotIn('<script src=',html)
            self.assertNotIn('https://',html)
            self.assertIn('Known zones',html)
            self.assertIn('frames[current]',html)


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.cfg=Config(lookback=75,forward_bars=3,holdout_date='2024-10-01')

    def test_matches_are_earlier_and_same_sample(self):
        d=bars(310)
        _,e=evaluate_symbol(d,'SPY',self.cfg)
        matches=matched_controls(d,e,'SPY',self.cfg)
        self.assertFalse(matches.empty)
        for row in matches.itertuples(index=False):
            self.assertGreaterEqual(row.control_count,1)
            self.assertLessEqual(row.control_count,5)
            self.assertTrue(all(p<row.signal_date for p in row.control_dates.split(';')))
            self.assertIn(row.sample,('training','holdout'))

    def test_rejects_cross_boundary_outcomes(self):
        self.assertIsNone(_eligible_sample('2024-09-30','2024-10-03','2024-10-01'))
        self.assertEqual(_eligible_sample('2024-10-01','2024-10-04','2024-10-01'),'holdout')
        self.assertEqual(_eligible_sample('2024-09-20','2024-09-27','2024-10-01'),'training')

    def test_multiple_testing_correction_monotonic(self):
        q=_bh_fdr([.02,.005,None,.5])
        self.assertIsNone(q[2]);self.assertGreaterEqual(q[0],.02)
        self.assertGreaterEqual(q[1],.005)
        self.assertGreaterEqual(q[3],.5)

    def test_summary_is_exploratory(self):
        d=bars(310);_,e=evaluate_symbol(d,'QQQ',self.cfg)
        m=matched_controls(d,e,'QQQ',self.cfg)
        s=summarize_matched(m,self.cfg)
        self.assertIn('bh_fdr_q',s.columns)
        self.assertIn('matched_events',s.columns)


if __name__=='__main__':unittest.main()
