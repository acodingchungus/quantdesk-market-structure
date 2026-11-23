"""Regression against a JavaScript inline comment that swallowed replay startup code."""
import re
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / 'market_structure_lab' / 'assets' / 'workstation.html'

class DashboardStartupTests(unittest.TestCase):
    def test_replay_load_dates_retains_executable_slider_update(self):
        src = HTML.read_text(encoding='utf-8')
        chunk = src.split('async function loadDates(', 1)[1].split('async function selectTimeframe(', 1)[0]
        active_lines = [line.split('//', 1)[0] for line in chunk.splitlines()]
        self.assertTrue(any("$('sessionSlider').max=" in line and 'await show()' in line for line in active_lines),
                        'The replay initialization statements must be active code, not inside a line comment')

    def test_inline_comment_cannot_swallow_replay_initializer(self):
        src = HTML.read_text(encoding='utf-8')
        chunk = src.split('async function loadDates(', 1)[1].split('async function selectTimeframe(', 1)[0]
        self.assertNotRegex(chunk, r'//[^\n]*\$\(\'sessionSlider\'\)')

if __name__ == '__main__':
    unittest.main()
