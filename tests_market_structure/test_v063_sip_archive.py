"""Offline contract tests for SIP archival ingestion, integrity and activation."""
import csv
from datetime import date
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pandas as pd

from market_structure_lab.sip_archive import (
    AlpacaArchiveClient, dest_path, download_day, read_meta_verified, scan_archive,
    publish_minute_view, session_days,
)
from market_structure_lab.workstation import ResearchStore
from market_structure_lab.core import Config

DAY=date(2026,9,30)

def bar(t='2026-09-30T13:30:00Z'):
    return {'t':t,'o':100,'h':101,'l':99,'c':100,'v':40}

def trade(t='2026-09-30T13:30:05Z',price=100.02,size=12):
    return {'t':t,'p':price,'s':size,'x':'V','c':['@'],'i':'test-id'}

class FakeResponse(io.BytesIO):
    def __init__(self,payload):super().__init__(json.dumps(payload).encode('utf-8'))

class FakeFeed:
    def __init__(self,bars=None,trades=None):
        self.bars=bars if bars is not None else [bar()]
        self.trades=trades if trades is not None else [trade(),trade('2026-09-30T13:30:06Z',100.04,23)]
        self.paths=[]
    def __call__(self,req,timeout=45):
        self.paths.append(req.full_url)
        assert req.get_method()=='GET'
        assert req.full_url.startswith('https://data.alpaca.markets/v2/stocks/SPY/')
        assert '/orders' not in req.full_url
        kind='bars' if '/bars?' in req.full_url else 'trades'
        query=parse_qs(urlsplit(req.full_url).query)
        assert query['feed']==['sip']
        if kind=='bars':
            assert query['timeframe']==['1Min']
            assert query['adjustment']==['raw']
        return FakeResponse({kind:getattr(self,kind),'next_page_token':None})

class SipArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.feed=FakeFeed()
        self.client=AlpacaArchiveClient('fake-key','fake-secret',opener=self.feed,
                                        sleeper=lambda _:None,min_interval=0)
    def tearDown(self):self.tmp.cleanup()

    def test_download_validates_and_preserves_metadata(self):
        b=download_day(self.client,self.root,'sip','bars','SPY',DAY)
        t=download_day(self.client,self.root,'sip','trades','SPY',DAY)
        self.assertEqual(b['rows'],1)
        self.assertEqual(t['rows'],2)
        self.assertEqual(t['executed_shares_unfiltered'],35)
        self.assertFalse(t['trade_conditions_filtered'])
        self.assertIn('/bars?',self.feed.paths[0]);self.assertIn('/trades?',self.feed.paths[1])
        bp=dest_path(self.root,'sip','bars','SPY',DAY)
        tp=dest_path(self.root,'sip','trades','SPY',DAY)
        with __import__('gzip').open(bp,'rt',newline='') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(rows[0]['timestamp'],'2026-09-30T09:31:00-04:00')
        self.assertEqual(read_meta_verified(tp)['feed'],'sip')
        self.assertEqual(download_day(self.client,self.root,'sip','trades','SPY',DAY)['action'],'SKIPPED_VERIFIED')
        self.assertEqual(len(self.feed.paths),2)
        report=scan_archive(self.root,'sip',('SPY',),DAY,DAY)
        self.assertEqual(report[0]['bars_state'],'PRESENT')
        self.assertEqual(report[0]['trades_state'],'PRESENT')
        self.assertEqual(report[0]['trade_shares_unfiltered'],35)
        self.assertIn('raw_trade_shares_to_bar_volume_ratio',report[0])

    def test_corruption_refuses_resume_without_overwrite(self):
        download_day(self.client,self.root,'sip','trades','SPY',DAY)
        file=dest_path(self.root,'sip','trades','SPY',DAY)
        with file.open('ab') as f:f.write(b'corruption')
        with self.assertRaises(ValueError):read_meta_verified(file)
        with self.assertRaises(ValueError):download_day(self.client,self.root,'sip','trades','SPY',DAY)
        self.assertEqual(scan_archive(self.root,'sip',('SPY',),DAY,DAY)[0]['trades_state'],'CORRUPT_OR_INCONSISTENT')

    def test_reject_duplicate_timestamp_and_never_publish_partial(self):
        self.feed.bars=[bar(),bar()]
        with self.assertRaises(ValueError):download_day(self.client,self.root,'sip','bars','SPY',DAY)
        final=dest_path(self.root,'sip','bars','SPY',DAY)
        self.assertFalse(final.exists())
        self.assertFalse(final.with_name(final.name+'.partial').exists())

    def test_no_data_does_not_fabricate_holiday_sessions(self):
        self.feed.bars=[]
        info=download_day(self.client,self.root,'sip','bars','SPY',DAY)
        self.assertEqual(info['action'],'NO_RTH_DATA')
        self.assertFalse(dest_path(self.root,'sip','bars','SPY',DAY).exists())

    def test_publish_view_never_overwrites_implicitly(self):
        download_day(self.client,self.root,'sip','bars','SPY',DAY)
        days=pd.bdate_range('2025-12-01','2026-10-01')
        x=np.arange(len(days),dtype=float)
        df=pd.DataFrame({'date':days.strftime('%Y-%m-%d'), 'open':100+.01*x,
                         'high':101+.01*x,'low':99+.01*x,'close':100+.01*x,
                         'volume':1000})
        df.to_csv(self.root/'SPY.csv',index=False)
        result=publish_minute_view(self.root,'sip','SPY',DAY,DAY)
        self.assertEqual(result['bars'],1)
        with self.assertRaises(FileExistsError):publish_minute_view(self.root,'sip','SPY',DAY,DAY)
        result=publish_minute_view(self.root,'sip','SPY',DAY,DAY,replace_active=True)
        self.assertTrue((self.root/'intraday'/'SPY_1m.csv.backup').exists())
        self.assertEqual(result['sessions'],1)

    def test_workstation_lazily_reads_selected_archive_and_hides_future_trades(self):
        # Use 2024 in this test so it belongs to generated daily history.
        session=date(2024,11,18)
        self.feed.trades=[trade('2024-11-18T14:30:10Z',100.01,10),
                          trade('2024-11-18T14:31:10Z',100.05,20)]
        download_day(self.client,self.root,'sip','trades','SPY',session)
        days=pd.bdate_range('2024-01-02',periods=230)
        x=np.arange(len(days),dtype=float)
        val=100+np.sin(x/10)*2+x*.01
        daily=pd.DataFrame({'date':days.strftime('%Y-%m-%d'),
                            'open':val,'high':val+1,'low':val-1,
                            'close':val,'volume':10000})
        self.assertIn('2024-11-18',set(daily['date']))
        for sym in ('SPY','QQQ'):
            daily.to_csv(self.root/f'{sym}.csv',index=False)
        store=ResearchStore(self.root,self.root/'journal.sqlite',config=Config(lookback=75))
        p=store.volume_profile('SPY','2024-11-18','1d')
        self.assertTrue(p['available'])
        self.assertEqual(p['trade_prints'],2)
        self.assertEqual(p['volume_shares'],30)
        self.assertEqual(p['source_feed'],'sip')
        self.assertFalse(p['trade_conditions_audited'])
        self.assertEqual(store.status()['data'][0]['archive_sip_trade_dates'],1)
        self.assertEqual(store.volume_profile('QQQ','2024-11-18','1d')['available'],False)

    def test_bounds_and_future_rejected(self):
        with self.assertRaises(ValueError):list(session_days(date(2026,1,1),date(2026,6,1)))
        with self.assertRaises(ValueError):list(session_days(date(2026,11,22),date(2026,11,22)))

if __name__=='__main__':unittest.main()

class MultiPageTests(unittest.TestCase):
    def test_pagination_preserves_equal_timestamps_and_source(self):
        import tempfile
        class Pages:
            def __init__(self):self.calls=0
            def __call__(self,req,timeout):
                self.calls+=1
                page=parse_qs(urlsplit(req.full_url).query).get('page_token',[''])[0]
                if page=='':
                    return FakeResponse({'trades':[trade('2026-09-30T13:30:05Z',100.01,10)],
                                         'next_page_token':'page2'})
                if page=='page2':
                    return FakeResponse({'trades':[trade('2026-09-30T13:30:05Z',100.04,15)],
                                         'next_page_token':None})
                raise AssertionError(page)
        api=Pages()
        client=AlpacaArchiveClient('k','s',opener=api,sleeper=lambda _:None,min_interval=0)
        with tempfile.TemporaryDirectory() as tmp:
            obj=download_day(client,Path(tmp),'sip','trades','SPY',DAY)
            self.assertEqual(obj['rows'],2)
            self.assertEqual(obj['pages'],2)
            self.assertEqual(api.calls,2)
            f=dest_path(Path(tmp),'sip','trades','SPY',DAY)
            from market_structure_lab.volume_profile import load_trades
            self.assertEqual(len(load_trades(f)),2)

    def test_never_publish_when_page_token_repeats(self):
        class Pages:
            def __call__(self,req,timeout):
                return FakeResponse({'trades':[trade()], 'next_page_token':'stuck'})
        client=AlpacaArchiveClient('k','s',opener=Pages(),sleeper=lambda _:None,min_interval=0)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                download_day(client,Path(tmp),'sip','trades','SPY',DAY)
            self.assertFalse(dest_path(Path(tmp),'sip','trades','SPY',DAY).exists())
