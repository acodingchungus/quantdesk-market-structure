"""Isolated, offline contract tests for the v0.5.1 minute-bar importer."""
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_structure_lab.fetch_alpaca_minutes import (fetch_one_day,
    normalize_one_day, save_one_day)


class FakeResponse(io.BytesIO):
    def __init__(self, body):
        super().__init__(json.dumps(body).encode())


class ImportTests(unittest.TestCase):
    def test_shift_alpaca_start_to_replay_bar_end(self):
        raw = [
            {'t':'2026-09-30T13:30:00Z','o':100,'h':101,'l':99,'c':100.5,'v':100},
            {'t':'2026-09-30T19:59:00Z','o':101,'h':102,'l':101,'c':102,'v':50},
            {'t':'2026-09-30T20:00:00Z','o':104,'h':104,'l':104,'c':104,'v':1},
        ]
        rows = normalize_one_day(raw,date(2026,9,30))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['timestamp'],'2026-09-30T09:31:00-04:00')
        self.assertEqual(rows[1]['timestamp'],'2026-09-30T16:00:00-04:00')
        self.assertEqual(rows[0]['volume'],100)

    def test_api_request_uses_raw_sip_and_read_only(self):
        def opener(req, timeout):
            self.assertEqual(req.get_method(), 'GET')
            url = req.full_url
            self.assertTrue(url.startswith('https://data.alpaca.markets/v2/stocks/SPY/bars?'))
            self.assertIn('timeframe=1Min',url)
            self.assertIn('adjustment=raw',url)
            self.assertIn('feed=sip',url)
            self.assertNotIn('/orders',url)
            return FakeResponse({'bars':[{'t':'2026-09-30T13:30:00Z','o':10,'h':11,'l':9,'c':10,'v':25}], 'next_page_token':None})
        data,pages = fetch_one_day('SPY',date(2026,9,30),'sip','k','s',opener=opener)
        self.assertEqual((len(data),pages),(1,1))

    def test_write_validates_and_refuses_overwrite(self):
        rows = normalize_one_day([{'t':'2026-09-30T13:30:00Z','o':100,'h':101,'l':99,'c':100,'v':3}],date(2026,9,30))
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'SPY_1m.csv'
            status=save_one_day(rows,f,overwrite=False,metadata={'feed':'SIP'})
            self.assertEqual(status['minute_bars'],1)
            self.assertTrue(f.with_suffix('.meta.json').exists())
            with self.assertRaises(FileExistsError):
                save_one_day(rows,f,overwrite=False,metadata={})

    def test_rejects_duplicate_minute_and_bad_schema(self):
        bars=[{'t':'2026-09-30T13:30:00Z','o':100,'h':101,'l':99,'c':100,'v':1}]
        with self.assertRaises(ValueError):
            normalize_one_day(bars+bars,date(2026,9,30))
        with self.assertRaises(ValueError):
            normalize_one_day([{'t':'2026-09-30T13:30:00Z'}],date(2026,9,30))

    def test_rejects_future_and_bad_symbol(self):
        with self.assertRaises(ValueError):
            fetch_one_day('NVDA',date(2026,9,30),'sip','a','b')
        with self.assertRaises(ValueError):
            fetch_one_day('SPY',date(9999,1,1),'sip','a','b')


if __name__=='__main__':
    unittest.main()
