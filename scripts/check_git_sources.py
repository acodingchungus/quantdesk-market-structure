"""Prevent another local-success / GitHub-missing-source release.

Run AFTER 'git add' and BEFORE commit, from repository root.
Checks tracked (or staged) manifest, not merely files present on disk.
"""
import subprocess
import sys
from pathlib import Path

REQUIRED = [
    'market_structure_lab/fetch_alpaca_minutes.py',
    'market_structure_lab/fetch_alpaca_context.py',
    'market_structure_lab/live_tape.py',
    'market_structure_lab/market_context_demo.py',
    'market_structure_lab/market_intelligence.py',
    'market_structure_lab/experiment_lab.py',
    'market_structure_lab/sip_archive.py',
    'market_structure_lab/universe.py',
    'market_structure_lab/universe_backfill.py',
    'tests_market_structure/test_v072_universe.py',
    'market_structure_lab/volume_profile.py',
    'market_structure_lab/intraday.py',
    'market_structure_lab/workstation.py',
    'market_structure_lab/assets/workstation.html',
    'tests_market_structure/test_v051_alpaca_minutes.py',
    'tests_market_structure/test_v06_intelligence.py',
    'tests_market_structure/test_v063_sip_archive.py',
    'tests_market_structure/test_v07_experiments.py',
    'market_structure_lab/watchlist_v08.py',
    'market_structure_lab/cross_asset_v08.py',
    'market_structure_lab/live_watchlist_v08.py',
    'tests_market_structure/test_v08_crossasset_watchlists.py',
    'market_structure_lab/cross_signals_v082.py',
    'tests_market_structure/test_v082_cross_signals.py',
    'market_structure_lab/data_quality_v083.py',
    'market_structure_lab/strategy_v083.py',
    'market_structure_lab/research_pipeline_v083.py',
    'tests_market_structure/test_v083_research_pipeline.py',
]

def main():
    root=Path(__file__).resolve().parents[1]
    out=subprocess.run(['git','ls-files','--cached','--full-name'],cwd=root,
                       check=True,capture_output=True,text=True).stdout
    present=set(out.splitlines())
    missing=[name for name in REQUIRED if name not in present or not (root/name).is_file()]
    if missing:
        print('GIT PREFLIGHT FAILED. Stage or recover required source files:')
        for name in missing:print(' -',name)
        return 1
    print('GIT PREFLIGHT OK:',len(REQUIRED),'required source files tracked/staged')
    return 0

if __name__=='__main__':sys.exit(main())
