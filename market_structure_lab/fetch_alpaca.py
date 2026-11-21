"""Optional read-only downloader for Alpaca daily SPY/QQQ bars.

No trading API is imported or used. Uses environment variables for credentials.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description='Download daily bars ONLY; never sends orders')
    ap.add_argument('--start',default='2024-01-02')
    ap.add_argument('--end',default=None,help='Inclusive completed ET session date; no partial current day')
    ap.add_argument('--symbols',nargs='+',default=['SPY','QQQ'])
    ap.add_argument('--feed',choices=['iex','sip'],default='iex')
    ap.add_argument('--output-dir',default='data')
    args=ap.parse_args()
    k=os.getenv('APCA_API_KEY_ID'); s=os.getenv('APCA_API_SECRET_KEY')
    if not k or not s:
        raise SystemExit('Set APCA_API_KEY_ID and APCA_API_SECRET_KEY locally (do not share keys).')
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        from alpaca.data.enums import DataFeed, Adjustment
    except ImportError:
        raise SystemExit('Missing alpaca-py: pip install alpaca-py')
    from zoneinfo import ZoneInfo
    now=datetime.now(ZoneInfo('America/New_York'))
    # Excludes today even after close: intentionally conservative about partial bars.
    end_day = datetime.fromisoformat(args.end).date() if args.end else now.date()-timedelta(days=1)
    if end_day >= now.date():
        raise SystemExit('Refusing to include current/future ET date; use last completed session.')
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end_exclusive = datetime.combine(end_day+timedelta(days=1),datetime.min.time(),tzinfo=timezone.utc)
    client=StockHistoricalDataClient(k,s)
    feed=DataFeed.IEX if args.feed=='iex' else DataFeed.SIP
    path=Path(args.output_dir);path.mkdir(parents=True,exist_ok=True)
    for symbol in args.symbols:
        req=StockBarsRequest(symbol_or_symbols=symbol.upper(),timeframe=TimeFrame.Day,
             start=start,end=end_exclusive,feed=feed,adjustment=Adjustment.ALL)
        df=client.get_stock_bars(req).df
        if df.empty:
            print(f'{symbol}: no rows from {args.feed}; check subscription and dates')
            continue
        df=df.reset_index()
        # UTC midnight timestamp is used for the exchange session date for 1Day bars.
        df=df.rename(columns={'timestamp':'date'})
        df['date']=df['date'].dt.strftime('%Y-%m-%d')
        output=df[['date','open','high','low','close','volume']]
        output.to_csv(path/f'{symbol.upper()}.csv',index=False)
        print(f'{symbol.upper()}: {len(output)} {args.feed} daily bars -> {path/f"{symbol.upper()}.csv"}')
    print('Source: Alpaca adjusted OHLCV; IEX is exchange-specific, not consolidated SIP.')

if __name__=='__main__':
    main()
