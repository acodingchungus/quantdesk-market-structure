"""Alpaca optional historical trade adapter: mocked transport, no network or creds."""
import io
import json
from datetime import date
from urllib.parse import urlsplit,parse_qs
import unittest

from market_structure_lab.fetch_alpaca_trades import fetch

class MockReply:
    def __init__(self,payload):self.buf=io.BytesIO(json.dumps(payload).encode())
    def __enter__(self):return self.buf
    def __exit__(self,*args):self.buf.close()

class FetchTests(unittest.TestCase):
    def test_reads_historical_pages_filters_offhours_and_avoids_order_api(self):
        seen=[]
        def opener(req,timeout):
            url=req.full_url;seen.append(url)
            self.assertIn('/v2/stocks/SPY/trades',url)
            self.assertNotIn('/v2/orders',url)
            self.assertEqual(req.get_header('Apca-api-key-id'),'fakekey')
            token=parse_qs(urlsplit(url).query).get('page_token',[None])[0]
            if token is None:
                return MockReply({'trades':[
                    {'t':'2024-11-18T14:29:59Z','p':100,'s':10,'x':'Q','c':[]},
                    {'t':'2024-11-18T14:30:00Z','p':100.01,'s':20,'x':'Q','c':['@']}
                ],'next_page_token':'next'})
            return MockReply({'trades':[
                {'t':'2024-11-18T21:00:00Z','p':100.05,'s':30,'x':'P','c':[]},
                {'t':'2024-11-18T21:00:02Z','p':100.07,'s':40,'x':'P','c':[]}
            ],'next_page_token':None})
        rows,pages=fetch('SPY',date(2024,11,18),date(2024,11,18),'sip','fakekey','fakesecret',opener=opener)
        self.assertEqual(pages,2)
        self.assertEqual(len(rows),2)
        self.assertEqual([r['size'] for r in rows],[20,30])
        self.assertEqual(rows[0]['source_label'],'ALPACA_SIP')
        self.assertEqual(len(seen),2)

    def test_rejects_bad_bounds_feed_symbol(self):
        for params in [dict(symbol='SPY;BAD',feed='sip'),dict(symbol='SPY',feed='private')]:
            with self.assertRaises(ValueError):
                fetch(params['symbol'],date(2024,11,18),date(2024,11,18),params['feed'],'k','s')
        with self.assertRaises(ValueError):
            fetch('SPY',date(2024,11,18),date(2024,12,1),'sip','k','s')
        with self.assertRaises(ValueError):
            fetch('SPY',date(2029,1,1),date(2029,1,1),'sip','k','s')

if __name__=='__main__': unittest.main()
