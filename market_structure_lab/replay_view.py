"""Standalone, offline price-zone replay, no CDN/network dependency."""
from __future__ import annotations
from pathlib import Path
import json
import pandas as pd
from .core import Config


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantDesk — __SYMBOL__ | Historical market replay</title>
<style>
:root{color-scheme:dark;font-family:Inter,Segoe UI,Arial,sans-serif;background:#0b1120;color:#e6eaf2}
*{box-sizing:border-box}body{margin:0;padding:0}header{display:flex;justify-content:space-between;align-items:center;gap:14px;border-bottom:1px solid #263244;padding:20px 25px;background:#111b2b;flex-wrap:wrap}
header h1{font-size:19px;margin:0 0 5px}header p{margin:0;color:#92a4bd;font-size:12px} .tag{border:1px solid #355075;border-radius:99px;font-size:11px;color:#acc6ee;padding:6px 10px}
main{max-width:1480px;margin:auto;padding:22px;display:grid;grid-template-columns:minmax(0,1fr) 290px;gap:18px}
.panel{background:#111a29;border:1px solid #263448;border-radius:14px;padding:16px;min-width:0} .chart-hd{display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.muted{color:#95a9c1;font-size:12px}.title{font-size:15px;font-weight:700}.value{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
canvas{height:560px;width:100%;display:block;background:#0c1522;border-radius:8px;cursor:crosshair}
.controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:13px}button,select{background:#1d2c41;color:#eaf1fd;border:1px solid #38516e;border-radius:7px;padding:8px 12px;cursor:pointer;font-size:13px}button:hover{background:#284362}button:focus-visible,input:focus-visible{outline:2px solid #60a5fa}input[type=range]{flex:1;min-width:190px;accent-color:#4da6ff}
.side-hd{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.zone{padding:10px 9px;border-top:1px solid #263448}.zone .top{display:flex;justify-content:space-between;gap:8px;font-weight:600;font-size:13px}.zone .sub{color:#92a4bd;font-size:11px;margin-top:5px;line-height:1.5}
.note{padding:12px;background:#19273a;border-radius:8px;color:#bfcee4;font-size:12px;line-height:1.5;margin-top:12px}.event{font-size:12px;padding:7px 0;border-bottom:1px solid #233146}small{color:#96a9be}footer{max-width:1480px;padding:0 22px 22px;margin:auto;font-size:12px;color:#94a6bc;line-height:1.6}
@media(max-width:950px){main{grid-template-columns:1fr}canvas{height:450px}}
</style></head>
<body><header><div><h1>QuantDesk · __SYMBOL__ price-reaction replay</h1><p>Real historical daily OHLCV · experimental KDE zones · standalone/offline viewer</p></div><span class="tag">RESEARCH ONLY • NO ORDERS</span></header>
<main><section class="panel"><div class="chart-hd"><div><div class="title">__SYMBOL__ · Daily candles</div><div class="muted" id="asof"></div></div><div style="text-align:right"><div id="price" class="value"></div><div class="muted" id="session"></div></div></div>
<canvas id="canvas" role="img" aria-label="Historical candlestick replay with known prior-session support and resistance zones"></canvas>
<div class="controls"><button id="prev" title="Previous session">◀</button><button id="play">▶ Play</button><button id="next" title="Next session">▶</button><input id="date" type="range" min="0" max="10" step="1" value="10" aria-label="Selected historical trading session"><span id="dateText" style="min-width:100px;font-size:12px"></span><label for="window" class="muted">Window</label><select id="window"><option value="40">40 bars</option><option value="80" selected>80 bars</option><option value="160">160 bars</option></select></div>
<div class="note">A zone shown on the selected date was calculated using <b>only completed sessions before that date</b>. Candles to the right of the selected day are hidden. Rejection and breakout labels appear only after their candle closes. A failed breakout is labeled only when the later re-entry is actually observed.</div>
</section><aside class="panel"><div class="side-hd"><span class="title">Known zones</span><span id="levelCount" class="muted"></span></div><div id="levels"></div><div class="side-hd" style="margin-top:15px"><span class="title">That day's reactions</span></div><div id="reactions" class="muted">Select a date</div><div class="note">Zones are historical reactions, <b>not actual resting orders</b>. "First seen" is the start of the currently tracked continuous zone (tracking begins after warmup). A changing zone is matched only to the previous day's zones.</div></aside></main>
<footer>Input is adjusted or unadjusted per supplied CSV. Original back-adjusted data can differ from as-traded historical quotes. No volume profile, futures depth, options P&amp;L, intraday fills, or proven alpha. The embedded dataset may contain later rows for navigation, but the viewer never plots them or uses them to calculate earlier level maps.</footer>
<script id="payload" type="application/json">__DATA__</script>
<script>
(()=>{'use strict';
const data=JSON.parse(document.getElementById('payload').textContent);
const bars=data.bars, frames=data.frames;let current=frames.length-1, playing=null, hover=null;
const el=id=>document.getElementById(id), cvs=el('canvas'), ctx=cvs.getContext('2d');
el('date').max=String(frames.length-1);el('date').value=String(current);
const money=n=>Number(n).toFixed(2);
function plot(){
 const dpr=window.devicePixelRatio||1, rect=cvs.getBoundingClientRect();
 const W=Math.max(450,Math.round(rect.width)), H=Math.max(300,Math.round(rect.height));
 cvs.width=Math.round(W*dpr);cvs.height=Math.round(H*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
 ctx.clearRect(0,0,W,H);const frame=frames[current];const end=frame.index;const windowSize=Number(el('window').value);
 const start=Math.max(0,end-windowSize+1), visible=bars.slice(start,end+1);const n=visible.length;
 const x0=55,x1=W-77,top=20,priceBottom=H-112,volumeTop=H-83,volBottom=H-39;
 const values=visible.flatMap(b=>[b.h,b.l]);for(const l of frame.levels){values.push(l.price+l.radius,l.price-l.radius);}
 const lo=Math.min(...values),hi=Math.max(...values),pad=Math.max((hi-lo)*.08,.01);
 const low=lo-pad, high=hi+pad;
 const py=p=>top+(high-p)/(high-low)*(priceBottom-top);
 const px=i=>x0+(i+.5)*(x1-x0)/n;
 ctx.font='11px Segoe UI,Arial';ctx.textBaseline='middle';
 for(let i=0;i<=5;i++){const p=low+(high-low)*i/5,y=py(p);ctx.strokeStyle='#26384b';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x0,y);ctx.lineTo(x1,y);ctx.stroke();ctx.fillStyle='#91a5bb';ctx.textAlign='left';ctx.fillText(money(p),x1+8,y);}
 for(const l of frame.levels){const y1=py(l.price+l.radius),y2=py(l.price-l.radius),cy=py(l.price);
  const isSupport=l.price<visible[n-1].c;ctx.fillStyle=isSupport?'rgba(25,178,131,.10)':'rgba(71,147,255,.13)';ctx.fillRect(x0,y1,x1-x0,Math.max(1,y2-y1));
  ctx.strokeStyle=isSupport?'#34b58f':'#6caeff';ctx.lineWidth=1;ctx.setLineDash([5,4]);ctx.beginPath();ctx.moveTo(x0,cy);ctx.lineTo(x1,cy);ctx.stroke();ctx.setLineDash([]);
  ctx.fillStyle=isSupport?'#73d7ba':'#9ac8ff';ctx.textAlign='right';ctx.font='10px Segoe UI,Arial';ctx.fillText(money(l.price),x1-4,cy-7);
 }
 const maxVol=Math.max(1,...visible.map(b=>b.v));const width=Math.max(1.4,Math.min(12,(x1-x0)/n*.6));
 visible.forEach((b,j)=>{const x=px(j),green=b.c>=b.o,color=green?'#34c3a3':'#f16f75';
 ctx.strokeStyle=color;ctx.lineWidth=1.1;ctx.beginPath();ctx.moveTo(x,py(b.h));ctx.lineTo(x,py(b.l));ctx.stroke();
 const yo=py(b.o),yc=py(b.c);ctx.fillStyle=color;ctx.fillRect(x-width/2,Math.min(yo,yc),width,Math.max(1.5,Math.abs(yc-yo)));
 ctx.fillStyle=green?'rgba(52,195,163,.4)':'rgba(241,111,117,.4)';const vh=(b.v/maxVol)*(volBottom-volumeTop);ctx.fillRect(x-width/2,volBottom-vh,width,vh);
 });
 ctx.strokeStyle='#536278';ctx.beginPath();ctx.moveTo(x0,volBottom);ctx.lineTo(x1,volBottom);ctx.stroke();
 for(let i=0;i<n;i+=Math.max(1,Math.round(n/7))){const b=visible[i];ctx.textAlign='center';ctx.fillStyle='#9badbf';ctx.font='11px Segoe UI,Arial';ctx.fillText(b.d.slice(5),px(i),H-16);}
 const events=data.markers.filter(m=>m.index>=start&&m.index<=end&&m.type!=='close_inside_zone');
 for(const m of events){const x=px(m.index-start);const yy=py(m.close);ctx.beginPath();ctx.arc(x,yy,4.1,0,Math.PI*2);ctx.fillStyle=m.type.startsWith('failed')?'#fbbf24':m.type.startsWith('rejection')?'#4ade80':'#fb7185';ctx.fill();ctx.strokeStyle='#0c1522';ctx.lineWidth=1;ctx.stroke();}
 if(hover!==null&&hover>=0&&hover<n){const b=visible[hover];const x=px(hover);ctx.strokeStyle='#8795ad';ctx.setLineDash([3,5]);ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,volBottom);ctx.stroke();ctx.setLineDash([]);ctx.font='11px Segoe UI,Arial';ctx.textAlign='left';ctx.fillStyle='#d8e6f5';ctx.fillText(b.d+' | O '+money(b.o)+' H '+money(b.h)+' L '+money(b.l)+' C '+money(b.c),x0+6,10);}
 cvs.dataset.start=String(start);cvs.dataset.count=String(n);cvs.dataset.left=String(x0);cvs.dataset.right=String(x1);
}
function render(){const f=frames[current],bar=bars[f.index];el('date').value=String(current);el('dateText').textContent=f.date;el('price').textContent='$'+money(bar.c);
 el('session').textContent='O '+money(bar.o)+'  H '+money(bar.h)+'  L '+money(bar.l);
 el('asof').textContent='Zones available at open '+f.date+' • map as of '+f.map_asof_date;
 el('levelCount').textContent=f.levels.length+' zones';
 el('levels').innerHTML=f.levels.length?f.levels.slice().sort((a,b)=>b.price-a.price).map(l=>`<div class="zone"><div class="top"><span>${l.price<bar.c?'🟢':'🔵'} $${money(l.price)} ± ${money(l.radius)}</span><span>${l.pivot_count} pivots</span></div><div class="sub">${l.id} · First seen ${l.first_seen}<br>Known as of ${l.asof_date}</div></div>`).join(''):'<div class="muted">No qualifying clusters on this date.</div>';
 el('reactions').innerHTML=f.markers.length?f.markers.map(m=>`<div class="event"><b>${m.type.replaceAll('_',' ')}</b><br><small>${m.zone_id} · $${money(m.level_price)}${m.origin_breakout_date?' · broke '+m.origin_breakout_date:''}</small></div>`).join(''):'No zone contacts on this session.';
 plot();}
function seek(i){current=Math.max(0,Math.min(frames.length-1,i));hover=null;render()}
function stop(){if(playing){clearInterval(playing);playing=null;}el('play').textContent='▶ Play'}
el('prev').onclick=()=>{stop();seek(current-1)};el('next').onclick=()=>{stop();seek(current+1)};
el('date').oninput=e=>{stop();seek(Number(e.target.value))};el('window').onchange=render;
el('play').onclick=()=>{if(playing){stop();return}el('play').textContent='❚❚ Pause';playing=setInterval(()=>{if(current>=frames.length-1){stop();return}seek(current+1)},350)};
cvs.addEventListener('mousemove',e=>{const a=cvs.getBoundingClientRect();const x=(e.clientX-a.left),left=Number(cvs.dataset.left),right=Number(cvs.dataset.right),n=Number(cvs.dataset.count);
 hover=x<left||x>right?null:Math.min(n-1,Math.max(0,Math.floor((x-left)/(right-left)*n)));plot()});
cvs.addEventListener('mouseleave',()=>{hover=null;plot()});window.addEventListener('resize',plot);render();
})();
</script></body></html>'''


def write_replay_html(bars: pd.DataFrame, frames: list[dict], reactions: pd.DataFrame,
                      symbol: str, destination: Path) -> None:
    b=[{'d':str(pd.Timestamp(r.date).date()),'o':round(float(r.open),4),
        'h':round(float(r.high),4),'l':round(float(r.low),4),
        'c':round(float(r.close),4),'v':round(float(r.volume),2)}
       for r in bars.itertuples(index=False)]
    records=reactions.to_dict('records') if not reactions.empty else []
    raw=json.dumps({'symbol':symbol, 'bars':b, 'frames':frames, 'markers':records},
                   separators=(',',':'),allow_nan=False).replace('</','<\\/')
    html=PAGE.replace('__SYMBOL__',symbol).replace('__DATA__',raw)
    destination.write_text(html,encoding='utf-8')
