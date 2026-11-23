"""Offline multi-ticker backfill regression tests; never contact market APIs."""
import contextlib
from datetime import date
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit

import numpy as np
import pandas as pd

from market_structure_lab.universe import ALL_SYMBOLS, CONTEXT_SYMBOLS, select_symbols
from market_structure_lab.sip_archive import (AlpacaArchiveClient, dest_path,
    download_day, publish_minute_view, read_meta_verified)
from market_structure_lab.universe_backfill import (
    coverage_snapshot, download_minutes, download_daily_context, main)
from market_structure_lab.market_intelligence import MarketIntelligence

DAY=date(2026,9,30)


class Response(io.BytesIO):
    def __init__(self, obj):super().__init__(json.dumps(obj).encode())
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class StubData:
    def __init__(self):self.urls=[]
    def __call__(self,req,timeout=45):
        self.urls.append(req.full_url)
        sym=urlsplit(req.full_url).path.split('/')[-2]
        assert sym in ('NVDA','SPY','QQQ')
        assert '/orders' not in req.full_url
        return Response({'bars':[{'t':'2026-09-30T13:30:00Z','o':100,'h':101,'l':99,
                                  'c':100,'v':10}],'next_page_token':None})


class UniverseTests(unittest.TestCase):
    def test_universe_is_deduplicated_and_explicit(self):
        self.assertEqual(len(ALL_SYMBOLS),len(set(ALL_SYMBOLS)))
        symbols=select_symbols(('core','mag7','semis'),('QQQ','CVX'))
        self.assertEqual(symbols.count('QQQ'),1)
        self.assertIn('NVDA',symbols)
        self.assertIn('CVX',symbols)
        self.assertIn('GOOGL',CONTEXT_SYMBOLS)
        for danger in ('..','SPY/../ZZZ','FAKE','spy'):
            with self.assertRaises(ValueError):select_symbols(('core',),(danger,))
        with self.assertRaises(ValueError):select_symbols(('anything',))

    def test_multi_asset_archives_are_read_only_and_resumable(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);mock=StubData()
            client=AlpacaArchiveClient('dummy-key','dummy-secret',opener=mock,
                  sleeper=lambda _:None,min_interval=0)
            results=download_minutes(root,'sip',('NVDA','SPY'),DAY,DAY,
                                     client=client,log=lambda _:None)
            self.assertEqual([r['action'] for r in results],['DOWNLOADED','DOWNLOADED'])
            self.assertEqual(len(mock.urls),2)
            results=download_minutes(root,'sip',('NVDA','SPY'),DAY,DAY,
                                     client=client,log=lambda _:None)
            self.assertEqual([r['action'] for r in results],['SKIPPED_VERIFIED']*2)
            self.assertEqual(len(mock.urls),2)
            path=dest_path(root,'sip','bars','NVDA',DAY)
            self.assertEqual(read_meta_verified(path)['symbol'],'NVDA')
            self.assertTrue(all(u.startswith('https://data.alpaca.markets/v2/stocks/')
                                for u in mock.urls))

    def test_null_bars_on_closed_session_does_not_break_batch_or_create_archive(self):
        """Alpaca may use null for no bars; record no RTH data without a fake file."""
        closed = date(2026, 9, 7)  # NYSE Labor Day holiday
        open_day = date(2026, 9, 8)

        class HolidayFeed:
            def __init__(self): self.requests=[]
            def __call__(self, req, timeout=45):
                self.requests.append(req.full_url)
                if '2026-09-07' in req.full_url or '2026-09-07' in str(req.full_url):
                    return Response({'bars':None,'next_page_token':None})
                return Response({'bars':[{
                    't':'2026-09-08T13:30:00Z', 'o':100,'h':101,
                    'l':99,'c':100,'v':20}], 'next_page_token':None})

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); feeder=HolidayFeed()
            client=AlpacaArchiveClient('dummy','dummy',opener=feeder,
                                       sleeper=lambda _:None,min_interval=0)
            result=download_minutes(root,'sip',('SPY',),closed,open_day,
                                    client=client,log=lambda _:None)
            self.assertEqual([x['action'] for x in result],
                             ['NO_RTH_DATA','DOWNLOADED'])
            self.assertFalse(dest_path(root,'sip','bars','SPY',closed).exists())
            self.assertEqual(read_meta_verified(dest_path(root,'sip','bars','SPY',open_day))['rows'],1)

    def test_null_is_not_accepted_when_pagination_is_present(self):
        class InvalidFeed:
            def __init__(self,payload):self.payload=payload
            def __call__(self,req,timeout=45):return Response(self.payload)

        with tempfile.TemporaryDirectory() as tmp:
            for invalid in ({'bars':None,'next_page_token':'continuation'},
                            {'error':'upstream failed'}, {'bars':{'bad':'type'}}):
                client=AlpacaArchiveClient('dummy','dummy',opener=InvalidFeed(invalid),
                                            sleeper=lambda _:None,min_interval=0)
                with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError,'Invalid Alpaca JSON schema'):
                    download_day(client,Path(tmp),'sip','bars','SPY',DAY)
            self.assertFalse(dest_path(Path(tmp),'sip','bars','SPY',DAY).exists())

    def test_inventory_checksums_and_weekday_caveat(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);mock=StubData()
            client=AlpacaArchiveClient('dummy','dummy',opener=mock,sleeper=lambda _:None,min_interval=0)
            download_day(client,root,'sip','bars','NVDA',DAY)
            inv=coverage_snapshot(root,'sip',('NVDA','QQQ'),date(2026,9,29),DAY)
            nvda,qqq=inv['symbols']
            self.assertEqual(nvda['verified_days'],1)
            self.assertEqual(nvda['absent_weekdays'],1)
            self.assertEqual(nvda['non_390_days'],1)
            self.assertEqual(qqq['verified_days'],0)
            self.assertTrue(inv['sessions_are_weekday_candidates_only'])
            with dest_path(root,'sip','bars','NVDA',DAY).open('ab') as f:f.write(b'BROKEN')
            nvda=coverage_snapshot(root,'sip',('NVDA',),DAY,DAY)['symbols'][0]
            self.assertEqual(nvda['corrupt_days'],1)
            self.assertEqual(nvda['verified_days'],0)

    def test_context_daily_existing_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);directory=root/'context';directory.mkdir()
            old=directory/'NVDA.csv';old.write_text('immutable baseline',encoding='utf-8')
            calls=[]
            def fake_fetch(sym,start,end,feed,key,secret):
                calls.append(sym)
                return [{'date':'2026-09-30','open':1,'high':2,'low':1,'close':2,'volume':9}]
            def fake_save(rows,path,metadata):path.write_text('new',encoding='utf-8')
            done=download_daily_context(root,'sip',('SPY','NVDA','GOOGL'),DAY,DAY,
                key='unused',secret='unused',fetcher=fake_fetch,saver=fake_save,log=lambda _:None)
            self.assertEqual(done,['GOOGL'])
            self.assertEqual(calls,['GOOGL'])
            self.assertEqual(old.read_text(),'immutable baseline')
            self.assertEqual((directory/'GOOGL.csv').read_text(),'new')

    def test_non_core_publish_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'SPY/QQQ only'):
                publish_minute_view(Path(t),'sip','NVDA',DAY,DAY)

    def test_context_universe_visible_at_prior_completed_cutoff(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ctx=root/'context';ctx.mkdir()
            dates=pd.bdate_range('2026-01-02',periods=110)
            vals=np.linspace(100,140,len(dates))
            df=pd.DataFrame({'date':dates,'open':vals,'high':vals+1,
                             'low':vals-1,'close':vals,'volume':1234})
            df.to_csv(ctx/'GOOGL.csv',index=False)
            daily={'SPY':df.assign(date=dates), 'QQQ':df.assign(date=dates)}
            target=dates[-3].strftime('%Y-%m-%d')
            a=MarketIntelligence(root,daily).snapshot(target)
            self.assertTrue(a['assets']['GOOGL']['available'])
            df.loc[df['date']>pd.Timestamp(target),['open','high','low','close']] *= 10
            df.to_csv(ctx/'GOOGL.csv',index=False)
            b=MarketIntelligence(root,daily).snapshot(target)
            self.assertEqual(a['assets']['GOOGL'],b['assets']['GOOGL'])

    def test_cli_plan_needs_no_credentials_and_download_requires_execute(self):
        out=io.StringIO()
        with tempfile.TemporaryDirectory() as t,contextlib.redirect_stdout(out):
            self.assertEqual(main(['plan','--groups','core','--start','2026-09-30',
                                   '--end','2026-09-30','--data-dir',t]),0)
        self.assertIn('potential historical bar requests',out.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as err:
                main(['download-minutes','--start','2026-09-30','--end','2026-09-30'])
        self.assertEqual(err.exception.code,2)

if __name__=='__main__':unittest.main()
