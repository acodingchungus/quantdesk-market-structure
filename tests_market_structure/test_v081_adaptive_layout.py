"""v0.8.1 presentation-only layout contracts; no data source or math changes."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / 'market_structure_lab' / 'assets' / 'workstation.html'


class CrossMarketLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HTML.read_text(encoding='utf-8')
        cls.css = cls.source.split('<style>', 1)[1].split('</style>', 1)[0]

    def test_portrait_layout_has_stacking_and_unclipped_watchlist(self):
        self.assertIn('@media(orientation:portrait) and (min-height:850px)', self.css)
        self.assertIn('.crossLayout{grid-template-columns:minmax(0,1fr);align-content:start;flex:1 0 auto}', self.css)
        self.assertIn('#watchRows{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;max-height:none;overflow:visible;', self.css)
        self.assertIn('@media(orientation:portrait) and (min-height:850px) and (min-width:1000px)', self.css)
        self.assertIn('#crossRows,#watchRows{grid-template-columns:repeat(3,minmax(0,1fr))}', self.css)

    def test_small_windows_and_landscape_have_bounds(self):
        self.assertIn('@media(max-width:950px)', self.css)
        self.assertIn('@media(max-width:699px)', self.css)
        self.assertIn('max-height:clamp(520px,calc(100dvh - 390px),960px)', self.css)
        self.assertNotIn('max-height:580px', self.css)
        self.assertIn('#crossRows{max-height:none;overflow:visible;', self.css)

    def test_focus_mode_is_accessible_and_does_not_mutate_snapshot_data(self):
        self.assertIn('id="crossLayout"', self.source)
        self.assertIn('id="watchFocus"', self.source)
        self.assertIn('aria-pressed="false" aria-controls="crossLayout"', self.source)
        self.assertIn("classList.toggle('is-watchlist-focus')", self.source)
        self.assertIn("setAttribute('aria-pressed',String(focus))", self.source)
        self.assertIn("textContent=focus?'Show comparison':'Focus watchlist'", self.source)
        self.assertIn('#crossLayout.is-watchlist-focus>.crossPanel:first-child{display:none}', self.css)
        # Changing screen layout must not rewrite calculations or provider payloads.
        self.assertIn('const result=await api(\'/api/cross-asset?\'+query)', self.source)
        self.assertIn("api('/api/live/watchlist')", self.source)
        self.assertIn("if(!watchCatalog||!watchSnapshot)return", self.source)


if __name__ == '__main__':
    unittest.main()
