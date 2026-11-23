"""Exact-time, point-in-time multi-asset historical observations.

No forward-filling, no hindsight prices, no signals or trades. Daily inputs are
COMPLETED sessions only; intraday requests use verified local SIP/IEX minute
archives with completed end timestamps, never the read-only live cache.
"""
from __future__ import annotations
from collections import OrderedDict
from datetime import date
from pathlib import Path
from threading import RLock
import gzip
import math
import pandas as pd
import numpy as np
from .universe import ALL_SYMBOLS
from .sip_archive import dest_path, read_meta_verified

ET = 'America/New_York'


def _time(value, intraday=False):
    t = pd.Timestamp(value)
    if intraday:
        if t.tzinfo is None:
            raise ValueError('Intraday asof requires an explicit timezone offset')
        local=t.tz_convert(ET)
        # Reject a forged/wrong UTC offset that silently shifts the requested ET bar.
        if local.strftime('%Y-%m-%dT%H:%M') != str(value)[:16]:
            raise ValueError('Timestamp offset does not match the requested Eastern Time wall clock')
        return local
    if t.tzinfo is not None or t.strftime('%Y-%m-%d') != str(value):
        raise ValueError('Daily asof must be YYYY-MM-DD, a completed research session')
    return t


def _series(frame, *, date_col, cutoff, tzaware):
    if frame is None or frame.empty:
        return pd.Series(dtype='float64')
    idx = pd.to_datetime(frame[date_col], utc=True) if tzaware else pd.to_datetime(frame[date_col])
    if tzaware:
        cutoff = cutoff.tz_convert('UTC')
    data = pd.Series(pd.to_numeric(frame['close'], errors='coerce').to_numpy(),index=idx)
    if data.index.has_duplicates or not data.index.is_monotonic_increasing:
        raise ValueError('Duplicate or unordered market timestamp')
    if (not np.isfinite(data.to_numpy(dtype=float)).all()) or (data.to_numpy(dtype=float)<=0).any():
        raise ValueError('Invalid historical close')
    return data.loc[data.index <= cutoff]


class CrossAssetEngine:
    """Bounded, auditable as-of comparison against local daily or 1m archives."""
    def __init__(self, data_dir, daily, *, cache_size=12):
        self.data_dir=Path(data_dir)
        self.daily=dict(daily)
        self.lock=RLock()
        self.cache=OrderedDict()
        self.cache_size=cache_size

    def _minutes(self, symbol, day, feed):
        from .sip_archive import BAR_FIELDS
        path=dest_path(self.data_dir,feed,'bars',symbol,day)
        if not path.exists():return None
        meta=read_meta_verified(path)
        if (meta['symbol'],meta['session'],meta['feed'],meta['kind']) != (symbol,str(day),feed,'bars'):
            raise ValueError('Archive provenance mismatch')
        key=(str(path),meta['sha256'])
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key);return self.cache[key]
        with gzip.open(path,'rt',encoding='utf-8') as fh:
            df=pd.read_csv(fh)
        if not set(BAR_FIELDS).issubset(df.columns) or len(df)!=meta['rows']:
            raise ValueError('Invalid minute archive columns or length')
        ts=pd.to_datetime(df['timestamp'],utc=True)
        if ts.isna().any() or ts.duplicated().any() or not ts.is_monotonic_increasing:
            raise ValueError('Minute timestamps are not unique and sorted')
        if any(t.tz_convert(ET).date()!=day for t in ts):
            raise ValueError('Cross-session archive bars')
        with self.lock:
            self.cache[key]=df
            while len(self.cache)>self.cache_size:self.cache.popitem(last=False)
        return df

    def snapshot(self, *, asof, target='QQQ', symbols=('SPY','QQQ','NVDA','SMH'),
                 timeframe='1d', feed='sip', window=20):
        if target not in ALL_SYMBOLS or any(s not in ALL_SYMBOLS for s in symbols):
            raise ValueError('Unknown historical research ticker')
        if feed not in ('sip','iex') or timeframe not in ('1d','1m'):
            raise ValueError('Only daily and archived 1-minute research supported')
        if not isinstance(window,int) or not 5<=window<=120:
            raise ValueError('window must be 5–120 returns')
        selected=tuple(dict.fromkeys((target,)+tuple(symbols)))
        intraday=timeframe=='1m'
        cutoff=_time(asof,intraday)
        if intraday and not pd.Timestamp('09:30:00').time() < cutoff.time() <= pd.Timestamp('16:00:00').time():
            raise ValueError('Intraday asof must be after 09:30 and no later than 16:00 ET')
        if intraday and cutoff.date()>=pd.Timestamp.now(tz=ET).date():
            raise ValueError('Only completed historical days for intraday research')
        series={}
        for sym in selected:
            if not intraday:
                df=self.daily.get(sym)
                series[sym]=_series(df,date_col='date',cutoff=cutoff,tzaware=False)
            else:
                df=self._minutes(sym,cutoff.date(),feed)
                series[sym]=_series(df,date_col='timestamp',cutoff=cutoff,tzaware=True)
        # Target last completed observation is the actual comparison reference,
        # not a supposed candle at the request cutoff that might not exist.
        base=series[target]
        base_last=base.index[-1] if len(base) else None
        if intraday and (base_last is None or base_last != cutoff.tz_convert('UTC')):
            raise ValueError('Target has no completed 1-minute bar at this exact timestamp; cannot forward-fill')
        rows=[]
        for sym in selected:
            s=series[sym]
            last=s.index[-1] if len(s) else None
            aligned=bool(base_last is not None and last==base_last)
            joint=pd.concat((base.rename('base'),s.rename('asset')),axis=1,join='inner').dropna()
            # Guard against gaps, and derive returns only from actual paired
            # timestamps (not from carry-forward or comparing mismatched bars).
            if intraday and not joint.empty:
                # Only the window used for correlation must be fully contiguous.
                recent=joint.iloc[-(window+1):]
                diff=recent.index.to_series().diff().dt.total_seconds().dropna()
                contiguous=bool(diff.eq(60).all())
            else:contiguous=True
            returns=np.log(joint).diff().dropna() if len(joint)>=2 else pd.DataFrame()
            usable=bool(aligned and len(returns)>=window and contiguous and
                        returns['base'].std()>1e-12 and returns['asset'].std()>1e-12)
            corr=float(returns['base'].iloc[-window:].corr(returns['asset'].iloc[-window:])) if usable else None
            if corr is not None and not math.isfinite(corr):corr=None
            if aligned and len(joint)>=2:
                last_ret=float((joint['asset'].iloc[-1]/joint['asset'].iloc[-2]-1)*100)
                base_ret=float((joint['base'].iloc[-1]/joint['base'].iloc[-2]-1)*100)
                relative=last_ret-base_ret
            else:last_ret=relative=None
            rows.append({'symbol':sym,'available':bool(len(s)),'aligned_to_target':aligned,
                'last_completed_at':last.isoformat() if last is not None else None,
                'last_close':float(s.iloc[-1]) if len(s) else None,
                'joint_observations':int(len(joint)),
                'one_bar_return_pct':round(last_ret,8) if last_ret is not None else None,
                'relative_to_target_pp':round(relative,8) if relative is not None else None,
                'correlation':round(corr,8) if corr is not None else None,
                'correlation_window':window if usable else None,
                'missing_or_stale':not aligned,'gap_free':contiguous})
        return {'version':'0.8.0','target':target,'requested_asof':str(asof),
            'timeframe':timeframe,'feed':feed if intraday else 'local_daily_csv',
            'target_last_completed_at':base_last.isoformat() if base_last is not None else None,
            'future_data_used':False,'rows':rows,
            'research_only':True,'no_orders':True,
            'warning':('Descriptive alignment, not a predictive signal. Missing/stale assets are not forward-filled. '
                '1m stats require contiguous paired minute timestamps in the SAME archived session. '
                'Adjusted daily versus raw minute price bases must be audited separately. '
                'Live market observations never enter this calculation.')}
