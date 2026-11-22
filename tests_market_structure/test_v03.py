"""Workstation invariants: causal data, local-only interface, notes, no orders."""
import json
from contextlib import closing
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from market_structure_lab.core import Config
from market_structure_lab.workstation import ResearchStore, make_handler
from http.server import ThreadingHTTPServer


def synthetic(n=230):
    d = pd.bdate_range('2024-01-02', periods=n)
    x = np.arange(n, dtype=float)
    c = 100 + 3 * np.sin(x / 7) + .025 * x
    o = c + .15 * np.cos(x / 2)
    return pd.DataFrame({'date': d.strftime('%Y-%m-%d'), 'open': o,
                         'high': np.maximum(c, o) + .65,
                         'low': np.minimum(c, o) - .65,
                         'close': c, 'volume': 100000 + 1000 * x})


class WorkstationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        folder = Path(cls.dir.name)
        datadir = folder / 'data'
        datadir.mkdir()
        for sym in ('SPY', 'QQQ'):
            synthetic().to_csv(datadir / (sym + '.csv'), index=False)
        cls.db = folder / 'notes.sqlite'
        cls.store = ResearchStore(datadir, cls.db, config=Config(lookback=75, holdout_date='2024-10-01'))
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(cls.store, 0))
        # Test with the actual ephemeral port (host-header validation).
        cls.httpd.RequestHandlerClass = make_handler(cls.store, cls.httpd.server_port)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.httpd.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        cls.dir.cleanup()

    def get(self, path):
        with urlopen(self.url + path, timeout=10) as r:
            return r.status, json.load(r)

    def test_status_safety_and_dates(self):
        status, payload = self.get('/api/status')
        self.assertEqual(status, 200)
        self.assertFalse(payload['broker_connected'])
        self.assertFalse(payload['orders_enabled'])
        self.assertEqual([a['symbol'] for a in payload['data']], ['SPY','QQQ'])
        _, dates = self.get('/api/dates?symbol=SPY')
        self.assertEqual(len(dates['dates']), 155)
        self.assertLess(dates['dates'][0], dates['dates'][-1])

    def test_past_frame_cannot_see_future_candles_or_levels(self):
        _, all_dates = self.get('/api/dates?symbol=QQQ')
        past = all_dates['dates'][17]
        _, frame = self.get('/api/frame?symbol=QQQ&date='+past+'&window=40')
        self.assertEqual(frame['date'], past)
        self.assertEqual(frame['candles'][-1]['date'], past)
        self.assertEqual(frame['map_asof_date'], all_dates['dates'][16])
        self.assertTrue(all(b['date'] <= past for b in frame['candles']))
        self.assertTrue(all(z['asof_date'] < past for z in frame['levels']))
        self.assertTrue(all(m['date'] <= past for m in frame['markers']))
        self.assertLessEqual(len(frame['candles']), 40)

    def test_validation_rejects_invalid_date_and_unknown_symbol(self):
        for path in ('/api/frame?symbol=XYZ', '/api/frame?symbol=SPY&date=2029-01-01',
                     '/api/frame?symbol=SPY&window=999'):
            with self.assertRaises(HTTPError) as ctx:
                self.get(path)
            self.assertEqual(ctx.exception.code, 400)
            ctx.exception.close()

    def test_notes_persist_and_are_date_scoped(self):
        _, dates = self.get('/api/dates?symbol=SPY')
        day = dates['dates'][5]
        note = self.store.note_add('SPY', day, 'Expected resistance rejection; define rule before replay.')
        self.assertGreater(note['note']['id'], 0)
        self.assertEqual(len(self.store.note_list('SPY', day)['notes']), 1)
        self.assertEqual(len(self.store.note_list('QQQ', day)['notes']), 0)
        # Reopen the actual DB without reconstructing research, to validate persistence.
        import sqlite3
        with closing(sqlite3.connect(self.db)) as db:
            self.assertGreaterEqual(db.execute('select count(*) from research_notes').fetchone()[0], 1)
        self.assertTrue(self.store.note_delete(note['note']['id'])['deleted'])
        self.assertEqual(self.store.note_list('SPY', day)['notes'], [])

    def test_local_journal_write_header_required_and_order_routes_absent(self):
        def req(path, body, headers):
            with urlopen(Request(self.url + path, data=json.dumps(body).encode(),
                                 headers=headers, method='POST'), timeout=10) as response:
                return response.status
        _, dates = self.get('/api/dates?symbol=SPY')
        payload = {'symbol': 'SPY', 'date': dates['dates'][0], 'content': 'A dated hypothesis'}
        with self.assertRaises(HTTPError) as forbidden:
            req('/api/notes', payload, {'Content-Type':'application/json'})
        self.assertEqual(forbidden.exception.code, 403)
        forbidden.exception.close()
        self.assertEqual(req('/api/notes', payload,
                             {'Content-Type':'application/json', 'X-QuantDesk-Local':'1'}), 201)
        with self.assertRaises(HTTPError) as missing:
            req('/api/orders', payload, {'Content-Type':'application/json','X-QuantDesk-Local':'1'})
        self.assertEqual(missing.exception.code, 404)
        missing.exception.close()

    def test_csp_and_self_contained_interface(self):
        with urlopen(self.url + '/',timeout=10) as r:
            html = r.read().decode()
            self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])
        self.assertIn('Research journal',html)
        self.assertIn('sessionSlider',html)
        self.assertIn('127.0.0.1',html)
        self.assertNotIn('<script src=',html)
        self.assertNotIn('https://',html)


if __name__ == '__main__':
    unittest.main()
