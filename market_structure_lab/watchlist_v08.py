"""TradingView screenshot watchlists. Display identity != provider entitlement.

These are the tickers visibly present in the supplied screenshots (2026-11),
not a live TradingView sync and not an assertion that every security is active.
No provider symbol substitutions are made without explicit mapping.
"""
from __future__ import annotations
from collections import OrderedDict

WATCHLISTS = OrderedDict({
    'stocks': ('TLT','SPY','DXY','XRPUSD','SOLUSD','SPX','AAPL','QQQ','IWM','VIX',
               'ES1!','IEI','TSLA','CL1!','NVDA','SMCI','XOM','V','GOOG','NFLX',
               'AMZN','DIS','META','AMD','BA','SMH','MSFT','LLY','WMT','COST'),
    'sectors': ('XLK','XLF','XLE','XLY','XLU','XLP','TQQQ','USOIL','XLV','XLI',
                'XLB','XLRE','XLC','SISE'),
    'energy_stocks': ('CVX','OXY','COP','DVN','MPC','LRCX','ASML','UUUU','ET','TPL',
                      'PDCE','TSM','SHEL'),
    'misc': ('SQQQ','BTCUSD'),
    'macro': ('FEDFUNDS','USINTR','USIRYY','UNRATE','T10Y2Y','WALCL','USM2'),
})
CRYPTO = {'BTCUSD':'BTC/USD','XRPUSD':'XRP/USD','SOLUSD':'SOL/USD'}
INDEX = {'SPX','VIX','DXY','SISE'}
FUTURES = {'ES1!','CL1!'}
CFD = {'USOIL'}
MACRO = set(WATCHLISTS['macro'])
# PDCE was acquired/delisted; retain watchlist name, not a live equity promise.
RETIRED = {'PDCE'}

SYMBOLS = tuple(dict.fromkeys(s for items in WATCHLISTS.values() for s in items))
EQUITIES = tuple(s for s in SYMBOLS if s not in (set(CRYPTO)|INDEX|FUTURES|CFD|MACRO|RETIRED))


def record(symbol: str) -> dict:
    if symbol not in SYMBOLS:
        raise ValueError('Unknown screenshot watchlist symbol')
    groups = [name for name, tickers in WATCHLISTS.items() if symbol in tickers]
    if symbol in EQUITIES:
        kind, provider, state, mapping = 'us_equity_or_etf','alpaca_stock','supported',symbol
    elif symbol in CRYPTO:
        kind, provider, state, mapping = 'crypto','alpaca_crypto','adapter_not_enabled',CRYPTO[symbol]
    elif symbol in FUTURES:
        kind, provider, state, mapping = 'future','separate_futures_provider','not_configured',None
    elif symbol in INDEX:
        kind, provider, state, mapping = 'index','separate_index_provider','not_configured',None
    elif symbol in CFD:
        kind, provider, state, mapping = 'cfd','original_cfd_provider','not_configured',None
    elif symbol in MACRO:
        kind, provider, state, mapping = 'macroeconomic_series','separate_macro_provider','not_configured',None
    else:
        kind, provider, state, mapping = 'historical_security','none','retired_review_required',None
    return {'symbol':symbol,'groups':groups,'kind':kind,'provider':provider,
            'provider_symbol':mapping,'availability':state}


def catalog() -> dict:
    return {'source':'user_supplied_tradingview_screenshots','groups':{
        name:list(tickers) for name,tickers in WATCHLISTS.items()},
        'symbols':[record(s) for s in SYMBOLS],
        'stock_snapshots_supported':list(EQUITIES),
        'disclaimer':'Watchlist identity does not establish live availability. No data for indices, futures, CFDs, macro or crypto is fabricated or substituted. US equities require a supported listing and appropriate Alpaca feed.'}
