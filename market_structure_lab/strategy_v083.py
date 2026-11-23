"""v0.8.3: deterministic completed-session decision and hypothetical portfolio engine.

Research-only. No sockets, credentials, order APIs, or live broker connections.
Uses v0.1 KDE/ATR/level algorithms unchanged. No future outcome informs decisions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from typing import Mapping

import pandas as pd

from .core import Config, _choose_event, discover_levels, true_range_and_atr
from .cross_signals_v082 import CrossSignalResearch
from .data_quality_v083 import _xnys, _days


@dataclass(frozen=True)
class StrategyPolicy:
    """Fixed before examining outcomes; not selected by maximizing hindsight P&L."""
    version: str = 'v083-research-v1'
    permitted_symbols: tuple[str, ...] = ('SPY', 'QQQ')
    side: str = 'long_only'
    allocation_fraction: float = 0.10
    max_positions: int = 2
    forward_bars: int = 3
    entry_rule: str = 'next_session_open'
    exit_rule: str = 'signal_plus_3_close'
    
    def __post_init__(self):
        if self.version != 'v083-research-v1' or self.permitted_symbols != ('SPY','QQQ'):
            raise ValueError('Unknown research strategy schema or symbol universe')
        if self.side != 'long_only' or not 0 < self.allocation_fraction <= 0.5:
            raise ValueError('Only fixed long-only cash allocation supported')
        if self.max_positions not in (1,2) or self.forward_bars != 3:
            raise ValueError('Unsupported portfolio controls/horizon')
        if self.entry_rule != 'next_session_open' or self.exit_rule != 'signal_plus_3_close':
            raise ValueError('Unsupported entry/exit convention')


@dataclass(frozen=True)
class CostAssumptions:
    """Explicit cost sensitivity, not observed bid/ask or a fill guarantee."""
    full_spread_bps: float = 2.0
    slippage_per_side_bps: float = 2.0
    commission_bps_per_side: float = 0.0
    min_order_notional: float = 1.0
    allow_fractional_shares: bool = True

    def __post_init__(self):
        for v in (self.full_spread_bps,self.slippage_per_side_bps,self.commission_bps_per_side):
            if not math.isfinite(v) or not 0 <= v <= 100:
                raise ValueError('Costs must be finite, in [0,100] basis points')
        if not math.isfinite(self.min_order_notional) or self.min_order_notional < 0:
            raise ValueError('Invalid minimum order notional')
        if not isinstance(self.allow_fractional_shares,bool):
            raise ValueError('Invalid fractional-share flag')


def _hash(value: dict) -> str:
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _next_session(day: str) -> str:
    cal=_xnys()
    return cal.next_session(pd.Timestamp(day)).strftime('%Y-%m-%d')


def kde_candidates(bars: pd.DataFrame, symbol: str, config: Config = Config()) -> dict[str,dict]:
    """End-of-session event scanner, including the final completed day.

    Reuses KDE primitives and source cooldown. It does not read t+1/t+3 bars.
    """
    if symbol not in ('SPY','QQQ'):
        raise ValueError('Unsupported KDE target')
    dates=_days(bars)
    if len(bars) <= config.lookback:
        raise ValueError('Not enough history for KDE')
    result={}; last=-10**9
    for t in range(config.lookback,len(bars)):
        history=bars.iloc[:t]
        atr=true_range_and_atr(history.iloc[-config.lookback:],config.atr_period)
        if atr <= 0 or t-last <= config.cooldown_bars:
            continue
        zones=discover_levels(history,config)
        if not zones:continue
        chosen=_choose_event(zones,float(history.iloc[-1]['close']),bars.iloc[t],atr,symbol,'clustered',t)
        if chosen:
            key=dates[t].strftime('%Y-%m-%d')
            result[key]={k:chosen[k] for k in ('symbol','source','signal_index','signal_date','level_asof_date',
                        'level_price','zone_radius','level_pivots','level_strength','setup','direction','atr')}
            last=t
    return result


def decisions_for_target(bars: pd.DataFrame, symbol: str,
                         context: CrossSignalResearch, policy: StrategyPolicy,
                         kde_config: Config = Config()) -> dict[str,list[dict]]:
    """One immutable end-of-close decision per target/session per strategy variant."""
    events=kde_candidates(bars,symbol,kde_config)
    dates=_days(bars)
    all_decisions={'kde_long_only':[],'kde_cross_confirmed':[]}
    policy_id=_hash({'policy':asdict(policy),'kde':asdict(kde_config)})
    for i in range(kde_config.lookback,len(bars)):
        day=dates[i].strftime('%Y-%m-%d')
        e=events.get(day)
        factor=context.snapshot(asof=day,target=symbol,direction=e['direction']) if e else None
        for mode in all_decisions:
            if e is None:
                reason='no_kde_event'
            elif e['direction'] != 1:
                reason='short_side_not_supported'
            elif mode=='kde_cross_confirmed' and factor['state']!='confirmed':
                reason='cross_asset_'+factor['state']
            else:
                reason='eligible_long_candidate'
            action='BUY_CANDIDATE' if reason=='eligible_long_candidate' else 'NO_TRADE'
            evidence={'kde':e,'cross_asset':factor if mode=='kde_cross_confirmed' else None}
            data={'schema':'quantdesk.decision.v1','policy_id':policy_id,'variant':mode,
                  'symbol':symbol,'asof_completed_session':day,
                  'earliest_eligible_session':_next_session(day),
                  'action':action,'reason':reason,'direction':e['direction'] if e else None,
                  'evidence_sha256':_hash(evidence),'research_only':True,'no_orders':True}
            data['decision_id']=_hash(data)
            all_decisions[mode].append(data)
    return all_decisions


def simulate_portfolio(daily: Mapping[str,pd.DataFrame], decisions: list[dict], *,
                       policy: StrategyPolicy=StrategyPolicy(),
                       costs: CostAssumptions=CostAssumptions(),
                       initial_cash:float=100.0) -> dict:
    """Cash-backed, long-only end-of-day mark-to-market; no broker simulation claims.

    Buy at *next* session's open and sell at t+3 close, with an adverse assumed
    spread/market-impact/commission. No intraday stops and no missing-bar fills.
    """
    if not math.isfinite(initial_cash) or initial_cash < 1:
        raise ValueError('Initial cash must be finite and >=1')
    frames={sym:frame.reset_index(drop=True) for sym,frame in daily.items() if sym in policy.permitted_symbols}
    if set(frames)!=set(policy.permitted_symbols):
        raise ValueError('Need both SPY and QQQ raw daily series')
    dates_by_sym={sym:[d.strftime('%Y-%m-%d') for d in _days(df)] for sym,df in frames.items()}
    index={sym:{d:i for i,d in enumerate(dates)} for sym,dates in dates_by_sym.items()}
    if dates_by_sym['SPY']!=dates_by_sym['QQQ']:
        raise ValueError('Targets must have identical complete session dates; no fill-forward')
    unique_ids=set(); by_entry={}; skipped=[]
    expected_policy_id=_hash({'policy':asdict(policy),'kde':asdict(Config())})
    for d in decisions:
        if d['decision_id'] in unique_ids:
            raise ValueError('Duplicate decision ID')
        unique_ids.add(d['decision_id'])
        if d.get('schema')!='quantdesk.decision.v1' or d.get('action') not in ('BUY_CANDIDATE','NO_TRADE') or not d.get('no_orders'):
            raise ValueError('Unrecognized or nonresearch decision')
        signed={k:v for k,v in d.items() if k!='decision_id'}
        if d.get('policy_id') != expected_policy_id or d['decision_id'] != _hash(signed):
            raise ValueError('Decision does not match the frozen policy or digest')
        if d['action']=='BUY_CANDIDATE' and (d.get('direction')!=1 or d.get('reason')!='eligible_long_candidate'):
            raise ValueError('Trade candidate lacks a valid long-only rationale')
        sym=d['symbol'];day=d['asof_completed_session']
        if sym not in frames or day not in index[sym] or d['earliest_eligible_session']!=_next_session(day):
            raise ValueError('Signal chronology or symbol invalid')
        if d['action']!='BUY_CANDIDATE':continue
        j=index[sym][day]; k=j+policy.forward_bars
        if k>=len(dates_by_sym[sym]):
            skipped.append({'decision_id':d['decision_id'],'reason':'outcome_not_yet_completed'})
            continue
        next_day=dates_by_sym[sym][j+1]
        if next_day!=d['earliest_eligible_session']:
            raise ValueError('Missing exchange session between signal and entry')
        by_entry.setdefault(next_day,[]).append((sym,d,k))
    impact=(costs.full_spread_bps/2+costs.slippage_per_side_bps)/10000
    fee=costs.commission_bps_per_side/10000
    cash=float(initial_cash); positions={}; trades=[]; equity=[]
    for today in dates_by_sym['SPY']:
        # Real cash from yesterday; open purchases in stable symbol and ID order.
        for sym,d,k in sorted(by_entry.get(today,[]),key=lambda x:(x[0],x[1]['decision_id'])):
            if sym in positions or len(positions)>=policy.max_positions:
                skipped.append({'decision_id':d['decision_id'],'reason':'position_limit_or_overlap'})
                continue
            open_px=float(frames[sym].iloc[index[sym][today]]['open'])
            execution=open_px*(1+impact)
            budget=min(cash,initial_cash*policy.allocation_fraction)
            qty=math.floor((budget/(execution*(1+fee)))*1e6)/1e6 if costs.allow_fractional_shares else math.floor(budget/(execution*(1+fee)))
            cost=qty*execution*(1+fee)
            if qty<=0 or cost<costs.min_order_notional or cost>cash+1e-9:
                skipped.append({'decision_id':d['decision_id'],'reason':'insufficient_cash_or_min_notional'})
                continue
            cash-=cost
            positions[sym]={'qty':qty,'entry_date':today,'entry_price':execution,
                            'entry_total':cost,'decision_id':d['decision_id'],
                            'due':dates_by_sym[sym][k]}
        # Exit at the known close; same-day proceeds are unavailable for morning buys.
        for sym,position in list(sorted(positions.items())):
            if position['due']!=today:continue
            close_px=float(frames[sym].iloc[index[sym][today]]['close'])
            execution=close_px*(1-impact)
            proceeds=position['qty']*execution*(1-fee)
            cash+=proceeds
            trades.append({'decision_id':position['decision_id'],'symbol':sym,
                           'entry_date':position['entry_date'],'exit_date':today,
                           'quantity':position['qty'],'entry_fill':position['entry_price'],
                           'exit_fill':execution,'cost_total':round(position['entry_total'],8),
                           'proceeds_total':round(proceeds,8),
                           'net_pnl':round(proceeds-position['entry_total'],8)})
            del positions[sym]
        nav=cash+sum(p['qty']*float(frames[sym].iloc[index[sym][today]]['close']) for sym,p in positions.items())
        equity.append({'session':today,'equity':round(nav,8),'cash':round(cash,8),'open_positions':len(positions)})
        if cash < -1e-8 or not math.isfinite(nav):
            raise AssertionError('Cash/NAV invariant violated')
    values=[x['equity'] for x in equity]
    peak=float(initial_cash); drawdown=0.0
    for x in values:
        peak=max(peak,x);drawdown=min(drawdown,x/peak-1)
    final=values[-1]
    return {'schema':'quantdesk.portfolio_research.v1','starting_cash':initial_cash,
            'ending_equity':final,'net_return_pct':round(100*(final/initial_cash-1),8),
            'max_drawdown_pct':round(100*drawdown,8),'completed_trades':len(trades),
            'unclosed_positions':len(positions),'skipped':skipped,
            'trades':trades,'equity':equity,'costs':asdict(costs),'policy':asdict(policy),
            'research_only':True,'paper_or_live_orders':False,
            'warnings':['Hypothetical daily OHLC fills and assumed costs, not observed spread/impact.',
                        'Fractional fills may not be executable in all instruments/sessions.',
                        'Historical sample previously inspected: no untouched holdout or validated alpha.',
                        'No shorting, borrow, taxes, broker-specific rejections, or corporate action cashflows modeled.']}
