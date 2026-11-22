"""Regression protection for the v0.6.1 Graphite Terminal cosmetic patch."""
import re
import unittest
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1]/'market_structure_lab/assets/workstation.html')

class GraphiteTerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page=HTML.read_text(encoding='utf-8')

    def test_palette_contract(self):
        for token in ('--surface-app: #08090B','--surface-shell: #101317','--surface-panel: #15191E',
                      '--ink-primary: #F5F7F8','--positive: #2ED47A','--negative: #FF5A5F',
                      '--caution: #F5C451','--chart-neutral-zone: #ADB6BE','--chart-value-area: #78838E'):
            self.assertIn(token,self.page)
        for old in ('#5BA8F5','#0E1827','#060A11','#477D8B'):
            self.assertNotIn(old,self.page)

    def test_chart_uses_graphite_palette(self):
        for marker in ("plot:cssColor('--plot')","grid:cssColor('--chart-grid')",'c.fillStyle=palette.plot',
                       'palette.neutralZone','palette.belowZone','palette.valueArea','palette.warn'):
            self.assertIn(marker,self.page)
        self.assertIn('SYNTHETIC',self.page)

    def test_tabs_replay_research_live_and_journal_preserved(self):
        for marker in ('id="tabLive"','id="tabReplay"','id="tabResearch"','id="replayWorkspace"',
                       'id="researchWorkspace"','id="liveWorkspace"','id="chart"','id="sessionSlider"',
                       'id="barSlider"','id="priceBin"','id="noteInput"','id="saveNote"',
                       "'/api/live'", "'/api/notes'", 'aria-pressed', ':focus-visible', 'prefers-reduced-motion'):
            self.assertIn(marker,self.page)

    def test_semantic_status_and_research_safety(self):
        for marker in ('state-positive','state-caution','state-negative','state-neutral',
                       'STALE / NO RECENT EVENTS','UNAVAILABLE','IEX','SIP',
                       'NO BROKER / NO ORDERS','RESEARCH ONLY','do not establish profitability'):
            self.assertIn(marker,self.page)
        for bad in ('<script src=', '<link rel="stylesheet"','https://'):
            self.assertNotIn(bad,self.page)

    def test_no_blue_palette_in_active_style(self):
        css=self.page.split('<style>',1)[1].split('</style>',1)[0]
        for old in ('#0B1220','#203C5C','#315982','#A7D8FF','#1D3550','#46698C'):
            self.assertNotIn(old,css)
        self.assertIn('class="researchDateInput"',self.page)

if __name__=='__main__': unittest.main()
