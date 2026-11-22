"""Static regression contracts for v0.6.2 UI-only replay improvements.

The interactive drag and keyboard behavior is also checked manually in a browser;
these unittest checks require no browser, network, or new dependencies.
"""
from pathlib import Path
import unittest

PAGE = (Path(__file__).resolve().parents[1]/'market_structure_lab/assets/workstation.html')

class MidnightReplayUXTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = PAGE.read_text(encoding='utf-8')

    def test_midnight_graphite_palette_and_semantics(self):
        for token in ('--surface-app: #030504','--surface-panel: #101310',
                      '--surface-inset: #090B09','--positive: #22DB58',
                      '--negative: #FF5A5F','--caution: #F5C451'):
            self.assertIn(token,self.page)
        self.assertIn('plot:cssColor(\'--plot\')',self.page)

    def test_replay_transport_and_seek_labels_exist(self):
        for id_ in ('firstDate','prev','next','latest','play','playSpeed',
                    'sessionSlider','sessionScrubTip','sessionProgress',
                    'barFirst','barBack5','barPrev','barNext','barForward5',
                    'barLast','barSlider','barScrubTip','barProgress'):
            self.assertIn('id="'+id_+'"',self.page)

    def test_keyboard_navigation_and_editable_exclusion(self):
        for marker in ('ArrowLeft','ArrowRight','ArrowUp','ArrowDown',
                       "e.key==='Home'","e.key==='End'","e.code==='Space'",
                       'e.shiftKey?5:1','if(workspace!==\'replay\'',
                       'textarea,select,input:not([type="range"])',
                       '[contenteditable="true"]','e.preventDefault()'):
            self.assertIn(marker,self.page)

    def test_live_scrub_is_coalesced_and_cache_is_bounded(self):
        for marker in ('addEventListener(\'input\'','addEventListener(\'change\'',
                       'setTimeout(()=>{seekTimer=null;show();},85)',
                       'replayCacheLimit=22','if(token!==app.request)return',
                       'function showScrubTip','function syncRange'):
            self.assertIn(marker,self.page)

    def test_ui_only_does_not_add_remote_assets_or_order_actions(self):
        for banned in ('<script src=', '<link rel="stylesheet"', 'https://',
                       '/api/orders', '/api/trading'):
            self.assertNotIn(banned,self.page)
        for marker in ('NO BROKER / NO ORDERS', 'RESEARCH ONLY',
                       'SYNTHETIC DEMO','Executed-trade volume profile'):
            self.assertIn(marker,self.page)

if __name__ == '__main__':
    unittest.main()
