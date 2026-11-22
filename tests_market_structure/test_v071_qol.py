"""v0.7.1 quality-of-life contracts. No network or live credentials."""
from pathlib import Path
import unittest

HTML = (Path(__file__).resolve().parents[1]/'market_structure_lab/assets/workstation.html')


class ReplayQoLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = HTML.read_text(encoding='utf-8')

    def test_extended_playback_rates_are_distinct(self):
        for value in ('6','8','10'):
            self.assertIn(f'<option value="{value}">{value}×</option>', self.page)
        self.assertIn('Math.max(65,Math.round(820/Number(', self.page)
        self.assertEqual([round(820/x) for x in (6, 8, 10)], [137, 102, 82])

    def test_switch_and_last_date_target_latest_completed_bar(self):
        self.assertIn('app.bar=null; // On timeframe switch', self.page)
        self.assertIn("go(app.dates.length-1,{lastBar:true})", self.page)
        self.assertIn("app.bar=(lastBar||app.timeframe==='1d')?null:0", self.page)
        self.assertIn("if(k===app.idx && !lastBar)return Promise.resolve()", self.page)
        self.assertIn("app.frame=null;app.profile=null;syncReplayProgress()", self.page)
        self.assertIn("app.bar=frame.timeframe==='1d'?null:frame.current_bar_index", self.page)
        self.assertIn("if(app.timeframe!=='1d')params.set('bar',String(app.bar))", self.page)

    def test_past_safety_and_keyboard_are_preserved(self):
        self.assertIn("if(workspace!=='replay'||e.altKey||e.ctrlKey||e.metaKey)return", self.page)
        self.assertIn("e.key==='ArrowLeft'", self.page)
        self.assertIn("e.key==='ArrowRight'", self.page)
        self.assertIn('app.timeframe!==\'1d\'', self.page)
        self.assertNotIn('/api/orders', self.page)


if __name__ == '__main__':
    unittest.main()
