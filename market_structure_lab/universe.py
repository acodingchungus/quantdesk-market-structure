"""Curated, explicit QuantDesk research universe, not a trade recommendation.

The archive may store minute bars/trades for these symbols. Only CORE symbols
are currently enabled for KDE replay and v0.7 strategy research. Daily context
CSV imports are descriptive, point-in-time features (not trading signals).
"""
from __future__ import annotations
from .watchlist_v08 import EQUITIES as TRADINGVIEW_EQUITIES

CORE = ('SPY', 'QQQ')
BENCHMARKS = ('IWM', 'SMH')
SECTORS = ('XLK', 'XLF', 'XLE', 'XLU', 'XLP', 'XLY', 'XLV', 'XLI', 'XLB', 'XLC', 'XLRE')
MEGACAPS = ('NVDA', 'MSFT', 'AAPL', 'AMZN', 'META', 'GOOGL', 'TSLA')
SEMIS = ('NVDA', 'AMD', 'AVGO', 'TSM', 'SMH')
ENERGY = ('XOM', 'CVX', 'COP', 'OXY', 'XLE')

GROUPS = {
    'core': CORE,
    'benchmarks': BENCHMARKS,
    'sectors': SECTORS,
    'mag7': MEGACAPS,
    'semis': SEMIS,
    'energy': ENERGY,
    'watchlist': TRADINGVIEW_EQUITIES,
}

# Preserves existing context symbols then extends rather than removing them.
CONTEXT_SYMBOLS = tuple(dict.fromkeys(
    s for s in BENCHMARKS + SECTORS + MEGACAPS + SEMIS + ENERGY + TRADINGVIEW_EQUITIES if s not in CORE
))
ALL_SYMBOLS = CORE + tuple(s for s in CONTEXT_SYMBOLS if s not in CORE)


def select_symbols(groups=('core',), symbols=()):
    """Stable de-duplicated order; fail closed on unapproved symbols/groups."""
    requested=[]
    for group in groups:
        if group not in GROUPS:
            raise ValueError(f'Unknown universe group: {group}')
        requested.extend(GROUPS[group])
    requested.extend(symbols)
    bad=[s for s in requested if s not in ALL_SYMBOLS]
    if bad:raise ValueError('Unsupported symbols: '+', '.join(bad))
    result=tuple(dict.fromkeys(requested))
    if not result:raise ValueError('No symbols selected')
    return result
