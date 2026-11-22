"""Cosmetic-release invariants: keep local workstation safe and self-contained."""
from pathlib import Path
import unittest

UI = Path(__file__).resolve().parents[1] / 'market_structure_lab' / 'assets' / 'workstation.html'

class WorkstationThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = UI.read_text(encoding='utf-8')

    def test_midnight_palette_and_canvas_reuse(self):
        for token in ('--surface-app: #030504', '--surface-panel: #101310', '--surface-inset: #090B09',
                      '--positive: #22DB58', '--negative: #FF5A5F', '--caution: #F5C451'):
            self.assertIn(token, self.page)
        self.assertIn("plot:cssColor('--plot')", self.page)
        self.assertIn('c.fillStyle=palette.plot', self.page)

    def test_legacy_controls_and_research_journal_preserved(self):
        for marker in ('id="chart"', 'id="symSPY"', 'id="symQQQ"', 'id="window"',
                       'id="prev"', 'id="play"', 'id="next"', 'id="sessionSlider"',
                       'id="latest"', 'id="noteInput"', 'id="saveNote"',
                       '/api/frame?', '/api/notes?', 'aria-pressed', 'prefers-reduced-motion'):
            self.assertIn(marker, self.page)

    def test_research_disclosures_and_no_remote_assets(self):
        for disclosure in ('RESEARCH ONLY', 'NO BROKER / NO ORDERS',
                           'do not establish profitability', 'Daily bars do not contain executable intraday options fills'):
            self.assertIn(disclosure, self.page)
        self.assertNotIn('<script src=', self.page)
        self.assertNotIn('<link rel="stylesheet"', self.page)
        self.assertNotIn('https://', self.page)

if __name__ == '__main__':
    unittest.main()
