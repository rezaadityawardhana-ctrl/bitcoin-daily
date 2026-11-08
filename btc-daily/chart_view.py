"""Full-screen candle chart (opened by tapping the BTC price) with technical-analysis read.

Uses TradingView Lightweight Charts 4.2.3 (Apache-2.0), inlined from vendor/ so it also works offline in the iPhone app.
Indicators are computed in the browser from the embedded candles so the timeframe/currency toggles are instant:
candles, volume, SMA 50/200, Bollinger Bands, bull-market support band (20W SMA + 21W EMA), VPVR (volume profile of the
visible range, with POC and value area), support/resistance and Fibonacci lines, RSI(14) and MACD(12,26,9).
"""
import html
import json
from pathlib import Path

VENDOR = Path(__file__).resolve().parent / "vendor" / "lightweight-charts-4.2.3.standalone.js"


def e(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


CSS = r'''
.price-btn{cursor:pointer;border-radius:12px;transition:background .15s}.price-btn:hover{background:rgba(255,255,255,.04)}
.chart-hint{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;color:var(--btc);border:1px solid rgba(247,147,26,.35);
 border-radius:999px;padding:2px 9px;margin-left:8px;vertical-align:middle;letter-spacing:0;white-space:nowrap}
.cm{position:fixed;inset:0;z-index:50;background:var(--page);display:flex;flex-direction:column;overscroll-behavior:contain}
.cm[hidden]{display:none}
.cm-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:12px 16px;border-bottom:1px solid var(--ring);background:var(--surface)}
.cm-title{font-weight:700;font-size:17px;margin-right:6px;white-space:nowrap}
.seg{display:flex;gap:2px;background:var(--wash);border-radius:9px;padding:3px}
.seg button{font:inherit;font-size:13px;font-weight:600;border:0;background:transparent;color:var(--ink2);border-radius:7px;padding:4px 11px;cursor:pointer}
.seg button.on{background:var(--surface);color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.15)}
.chips{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;flex:1;min-width:0}.chips::-webkit-scrollbar{display:none}
.chips button{font:inherit;font-size:12px;font-weight:600;border:1px solid var(--ring);background:transparent;color:var(--muted);border-radius:999px;
 padding:3px 10px;cursor:pointer;white-space:nowrap}
.chips button.on{color:var(--ink);border-color:color-mix(in srgb,var(--btc) 55%,transparent);background:color-mix(in srgb,var(--btc) 10%,transparent)}
.chips button i{display:inline-block;width:10px;height:3px;border-radius:2px;margin-right:5px;vertical-align:3px}
.cm-close{margin-left:auto;font:inherit;font-size:22px;line-height:1;border:0;background:var(--wash);color:var(--ink);width:36px;height:36px;border-radius:50%;cursor:pointer}
.cm-body{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch}
.cm-charts{padding:8px 12px 0;max-width:1400px;margin:0 auto}
.pane{position:relative}.pane-main{height:min(56vh,560px)}.pane-sub{height:120px;border-top:1px solid var(--grid)}
.pane-label{position:absolute;left:8px;top:6px;z-index:3;font-size:11px;font-weight:600;color:var(--muted);pointer-events:none}
.cm-legend{position:absolute;left:8px;top:6px;z-index:3;font-size:12px;color:var(--ink2);pointer-events:none;font-variant-numeric:tabular-nums;
 display:flex;flex-wrap:wrap;gap:4px 12px;max-width:calc(100% - 90px)}
.cm-legend b{color:var(--ink);font-weight:600}.cm-legend .up{color:#1baf7a}.cm-legend .dn{color:#e34948}
.vpvr{position:absolute;left:0;top:0;width:100%;height:100%;z-index:2;pointer-events:none}
.cm-note{font-size:11.5px;color:var(--muted);padding:6px 4px 0}
.ta{max-width:1400px;margin:0 auto;padding:14px 12px 40px;display:grid;grid-template-columns:1.2fr 1fr;gap:16px}
.ta-card{background:var(--surface);border:1px solid var(--ring);border-radius:16px;padding:18px 20px}
.ta-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.bias{font-size:13px;font-weight:700;border-radius:8px;padding:4px 10px}
.bias.bull{color:#1baf7a;background:rgba(27,175,122,.12)}.bias.bear{color:#e34948;background:rgba(227,73,72,.12)}.bias.neu{color:var(--ink2);background:var(--wash)}
.ta-sum{font-size:15.5px;line-height:1.55;margin:8px 0 4px}
.ta h4{margin:14px 0 4px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.ta ul{margin:0;padding-left:18px}.ta li{margin:4px 0;font-size:14px;color:var(--ink2)}
.lvl{width:100%;border-collapse:collapse;font-size:13.5px}.lvl td{padding:7px 4px;border-bottom:1px solid var(--grid);vertical-align:top}
.lvl .t{font-size:11px;font-weight:700;border-radius:5px;padding:1px 6px}.lvl .t.s{color:#1baf7a;background:rgba(27,175,122,.12)}.lvl .t.r{color:#e34948;background:rgba(227,73,72,.12)}
.lvl tr.now td{color:var(--ink);font-weight:700;border-bottom:2px solid var(--btc)}
.conf{font-size:10.5px;font-weight:700;color:var(--btc);margin-left:4px}
.scen{display:grid;gap:8px;margin-top:6px}.scen div{border:1px solid var(--ring);border-radius:10px;padding:9px 12px;font-size:13.5px;background:var(--surface2)}
.scen b{display:block;font-size:12px;letter-spacing:.04em;text-transform:uppercase;margin-bottom:2px}
.ta-lt{margin-top:12px;padding:10px 12px;border-radius:10px;border-left:3px solid var(--btc);background:var(--surface2);font-size:14px}
@media (max-width:860px){.ta{grid-template-columns:1fr}.pane-main{height:52vh}.pane-sub{height:100px}}
@media (max-width:600px){.cm-legend{font-size:10.5px;gap:1px 8px;max-width:calc(100% - 100px)}.cm-legend .lx{display:none}
 .cm-bar{gap:8px;padding:10px 12px}.cm-title{font-size:15px}.chips{order:5;flex-basis:100%}.cm-close{width:32px;height:32px;font-size:20px}}
'''

HTML = r'''
<div class="cm" id="chart-modal" hidden role="dialog" aria-modal="true" aria-label="Bitcoin chart">
  <div class="cm-bar">
    <span class="cm-title" id="cm-title">BTC / USD</span>
    <div class="seg" id="cm-cur"><button data-v="usd">USD</button><button data-v="chf">CHF</button></div>
    <div class="seg" id="cm-tf"><button data-v="d">1D</button><button data-v="w">1W</button></div>
    <div class="chips" id="cm-ind">
      <button data-k="ma50"><i style="background:#eda100"></i>MA 50</button>
      <button data-k="ma200"><i style="background:#eb6834"></i>MA 200</button>
      <button data-k="band"><i style="background:#a77bf3"></i>Bull band 20W/21W</button>
      <button data-k="bb"><i style="background:#8b8982"></i>Bollinger</button>
      <button data-k="vpvr"><i style="background:#3987e5"></i>VPVR</button>
      <button data-k="sr"><i style="background:#1baf7a"></i>Support/Resistance</button>
      <button data-k="fib"><i style="background:#f7931a"></i>Fibonacci</button>
    </div>
    <button class="cm-close" id="cm-close" aria-label="Close chart">×</button>
  </div>
  <div class="cm-body">
    <div class="cm-charts">
      <div class="pane pane-main" id="cm-main"><div class="cm-legend" id="cm-legend"></div><canvas class="vpvr" id="cm-vpvr"></canvas></div>
      <div class="pane pane-sub" id="cm-rsi"><span class="pane-label">RSI 14</span></div>
      <div class="pane pane-sub" id="cm-macd"><span class="pane-label">MACD 12 · 26 · 9</span></div>
      <div class="cm-note">Drag to pan, pinch or scroll to zoom. VPVR = volume at each price for the bars on screen (blue = up-day volume,
        red = down-day volume; brighter = 70% value area; line = point of control). Candles: Kraken. CHF volume uses the BTC volume
        traded on Kraken's USD market.</div>
    </div>
    <div class="ta" id="cm-ta"></div>
  </div>
</div>
'''

JS = r'''
(function(){
const LC = window.LightweightCharts; if(!LC||typeof TA==='undefined') return;
const modal=document.getElementById('chart-modal');
const st={cur:'usd',tf:'d',show:{ma50:1,ma200:1,band:1,bb:0,vpvr:1,sr:1,fib:0},charts:[]};
const col=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const UP='#1baf7a',DN='#e34948';
const fmtP=v=>v==null?'–':(st.cur==='usd'?'$':'CHF ')+Math.round(v).toLocaleString('en-US');
const fmtK=v=>(st.cur==='usd'?'$':'')+(v>=1000?(v/1000).toFixed(1)+'k':Math.round(v));

// ---------- indicator maths
const sma=(a,n)=>{const o=[];let s=0;for(let i=0;i<a.length;i++){s+=a[i];if(i>=n)s-=a[i-n];o.push(i>=n-1?s/n:null)}return o};
const ema=(a,n)=>{const o=[],k=2/(n+1);let p=null;for(let i=0;i<a.length;i++){if(a[i]==null){o.push(null);continue}
  if(p==null){const st0=o.length;let cnt=0,s=0;for(let j=i;j>=0&&cnt<n&&a[j]!=null;j--){s+=a[j];cnt++}if(cnt<n){o.push(null);continue}p=s/n}else p=a[i]*k+p*(1-k);o.push(p)}return o};
const rsi=(a,n=14)=>{const o=Array(a.length).fill(null);let g=0,l=0;for(let i=1;i<a.length;i++){const d=a[i]-a[i-1];const G=Math.max(d,0),L=Math.max(-d,0);
  if(i<=n){g+=G;l+=L;if(i===n){g/=n;l/=n;o[i]=l===0?100:100-100/(1+g/l)}}else{g=(g*(n-1)+G)/n;l=(l*(n-1)+L)/n;o[i]=l===0?100:100-100/(1+g/l)}}return o};
function macd(a){const f=ema(a,12),s=ema(a,26);const m=f.map((v,i)=>v!=null&&s[i]!=null?v-s[i]:null);const sg=ema(m,9);return{m,sg,h:m.map((v,i)=>v!=null&&sg[i]!=null?v-sg[i]:null)}}
function bb(a,n=20,k=2){const mid=sma(a,n);const up=[],lo=[];for(let i=0;i<a.length;i++){if(mid[i]==null){up.push(null);lo.push(null);continue}
  let s=0;for(let j=i-n+1;j<=i;j++)s+=(a[j]-mid[i])**2;const sd=Math.sqrt(s/n);up.push(mid[i]+k*sd);lo.push(mid[i]-k*sd)}return{up,mid,lo}}

// ---------- build
function destroy(){st.charts.forEach(c=>c.remove());st.charts=[]}
function line(chart,data,times,color,width=2,style=0,title='',precision=0){const s=chart.addLineSeries({priceFormat:{type:'price',precision,minMove:precision?0.1:1},color,lineWidth:width,lineStyle:style,priceLineVisible:false,
  lastValueVisible:!!title,title,crosshairMarkerVisible:false});s.setData(data.map((v,i)=>v==null?{time:times[i]}:{time:times[i],value:v}));return s}

function build(keepRange){
  const prev=keepRange&&st.main?st.main.timeScale().getVisibleLogicalRange():null;
  destroy();
  const raw=TA.candles[st.cur+'_'+st.tf];
  const t=raw.map(c=>c[0]),o=raw.map(c=>c[1]),h=raw.map(c=>c[2]),l=raw.map(c=>c[3]),c=raw.map(c=>c[4]),v=raw.map(c=>c[5]);
  st.raw=raw;
  const base={autoSize:true,layout:{background:{type:'solid',color:'transparent'},textColor:col('--muted'),fontFamily:'Inter,system-ui,sans-serif',fontSize:11},
    grid:{vertLines:{color:col('--grid')},horzLines:{color:col('--grid')}},rightPriceScale:{borderColor:col('--axis'),minimumWidth:92},
    timeScale:{borderColor:col('--axis'),rightOffset:6,timeVisible:false},crosshair:{mode:0},handleScroll:true,handleScale:true};
  const main=LC.createChart(document.getElementById('cm-main'),base);
  const PF={type:'price',precision:0,minMove:1};
  const cs=main.addCandlestickSeries({priceFormat:PF,upColor:UP,downColor:DN,borderUpColor:UP,borderDownColor:DN,wickUpColor:UP,wickDownColor:DN,priceLineColor:col('--ink2')});
  cs.setData(raw.map(r=>({time:r[0],open:r[1],high:r[2],low:r[3],close:r[4]})));
  const vs=main.addHistogramSeries({priceScaleId:'vol',priceFormat:{type:'volume'},lastValueVisible:false,priceLineVisible:false});
  main.priceScale('vol').applyOptions({scaleMargins:{top:.84,bottom:0}});
  vs.setData(raw.map(r=>({time:r[0],value:r[5],color:(r[4]>=r[1]?UP:DN)+'66'})));
  const S={},wk=st.tf==='w';
  const ma50=sma(c,50),ma200=sma(c,200);
  if(st.show.ma50)S.ma50=line(main,ma50,t,'#eda100',2,0,'MA50');
  if(st.show.ma200)S.ma200=line(main,ma200,t,'#eb6834',2,0,'MA200');
  if(st.show.band){const a=sma(c,wk?20:140),b=ema(c,wk?21:147);S.bandA=line(main,a,t,'#a77bf3',1.5,0);S.bandB=line(main,b,t,'#a77bf3',1.5,2)}
  if(st.show.bb){const B=bb(c);line(main,B.up,t,'#8b8982',1,2);line(main,B.mid,t,'#8b8982',1,1);line(main,B.lo,t,'#8b8982',1,2)}
  const L=TA.levels[st.cur];
  if(st.show.sr&&L){(L.supports||[]).forEach(x=>cs.createPriceLine({price:x.price,color:UP,lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'S ×'+x.touches}));
    (L.resistances||[]).forEach(x=>cs.createPriceLine({price:x.price,color:DN,lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'R ×'+x.touches}))}
  if(st.show.fib&&L&&L.fib){Object.entries(L.fib.levels).forEach(([r,p])=>cs.createPriceLine({price:p,color:'#f7931a',lineWidth:1,lineStyle:1,axisLabelVisible:true,title:'Fib '+r}))}

  const sub=Object.assign({},base,{timeScale:Object.assign({},base.timeScale,{visible:false}),rightPriceScale:{borderColor:col('--axis'),minimumWidth:92}});
  const rc=LC.createChart(document.getElementById('cm-rsi'),sub);const R=rsi(c);
  const rs=line(rc,R,t,'#a77bf3',1.5,0,'RSI',1);[70,30].forEach(x=>rs.createPriceLine({price:x,color:col('--muted'),lineWidth:1,lineStyle:2,axisLabelVisible:false}));
  rs.createPriceLine({price:50,color:col('--grid'),lineWidth:1,lineStyle:1,axisLabelVisible:false});
  const mc=LC.createChart(document.getElementById('cm-macd'),sub);const M=macd(c);
  const mh=mc.addHistogramSeries({priceLineVisible:false,lastValueVisible:false});
  mh.setData(M.h.map((x,i)=>x==null?{time:t[i]}:{time:t[i],value:x,color:x>=0?(i>0&&M.h[i-1]!=null&&x<M.h[i-1]?UP+'88':UP):(i>0&&M.h[i-1]!=null&&x>M.h[i-1]?DN+'88':DN)}));
  const ml=line(mc,M.m,t,'#3987e5',1.5,0,'MACD');const sl=line(mc,M.sg,t,'#eb6834',1.5,0,'Signal');
  st.charts=[main,rc,mc];st.main=main;st.cs=cs;
  // sync time scales
  let syncing=false;
  st.charts.forEach(ch=>ch.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(syncing||!r)return;syncing=true;
    st.charts.forEach(o2=>{if(o2!==ch)o2.timeScale().setVisibleLogicalRange(r)});syncing=false;drawVP()}));
  // crosshair sync + legend
  const byTime=new Map(t.map((x,i)=>[x,i]));
  const legend=i=>{if(i==null||i<0)i=raw.length-1;const r=raw[i],prev=i>0?raw[i-1][4]:r[1],ch=r[4]/prev-1;
    const d=new Date(r[0]*1000).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
    document.getElementById('cm-legend').innerHTML=`<span><b>${d}</b></span><span>O <b>${fmtP(r[1])}</b></span><span>H <b>${fmtP(r[2])}</b></span>`+
      `<span>L <b>${fmtP(r[3])}</b></span><span>C <b>${fmtP(r[4])}</b> <span class="${ch>=0?'up':'dn'}">${ch>=0?'+':''}${(ch*100).toFixed(2)}%</span></span>`+
      (st.show.ma50&&ma50[i]?`<span class="lx" style="color:#eda100">MA50 ${fmtP(ma50[i])}</span>`:'')+(st.show.ma200&&ma200[i]?`<span class="lx" style="color:#eb6834">MA200 ${fmtP(ma200[i])}</span>`:'')+
      (R[i]!=null?`<span class="lx" style="color:#a77bf3">RSI ${R[i].toFixed(1)}</span>`:'')+(M.h[i]!=null?`<span class="lx">MACD hist <b class="${M.h[i]>=0?'up':'dn'}">${Math.round(M.h[i])}</b></span>`:'')};
  legend();
  const pairs=[[main,cs,c],[rc,rs,R],[mc,ml,M.m]];
  pairs.forEach(([ch])=>ch.subscribeCrosshairMove(p=>{const i=p&&p.time!=null?byTime.get(p.time):null;legend(i);
    pairs.forEach(([o2,s2,vals])=>{if(o2===ch)return;if(i==null||vals[i]==null)o2.clearCrosshairPosition();else o2.setCrosshairPosition(vals[i],p.time,s2)})}));
  const n=raw.length,span=wk?160:180;
  main.timeScale().setVisibleLogicalRange(prev||{from:Math.max(0,n-span),to:n+4});
  requestAnimationFrame(drawVP);
}

// ---------- VPVR overlay
function drawVP(){
  const cv=document.getElementById('cm-vpvr');if(!cv||!st.main)return;
  const box=document.getElementById('cm-main');const dpr=window.devicePixelRatio||1;
  cv.width=box.clientWidth*dpr;cv.height=box.clientHeight*dpr;const g=cv.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,cv.width,cv.height);
  if(!st.show.vpvr)return;
  const r=st.main.timeScale().getVisibleLogicalRange();if(!r)return;
  const a=Math.max(0,Math.floor(r.from)),b=Math.min(st.raw.length-1,Math.ceil(r.to));const bars=st.raw.slice(a,b+1);if(bars.length<3)return;
  let lo=Infinity,hi=-Infinity;bars.forEach(x=>{lo=Math.min(lo,x[3]);hi=Math.max(hi,x[2])});
  const N=36,step=(hi-lo)/N||1,up=Array(N).fill(0),dn=Array(N).fill(0);
  bars.forEach(x=>{const i0=Math.floor((x[3]-lo)/step),i1=Math.min(N-1,Math.floor((x[2]-lo)/step));const share=x[5]/(i1-i0+1);
    for(let j=i0;j<=i1;j++)(x[4]>=x[1]?up:dn)[j]+=share});
  const tot=up.map((u,j)=>u+dn[j]),max=Math.max(...tot);const poc=tot.indexOf(max);
  let area=tot[poc],L=poc,H=poc;const all=tot.reduce((s,x)=>s+x,0);
  while(area<.7*all&&(L>0||H<N-1)){const d=L>0?tot[L-1]:-1,u=H<N-1?tot[H+1]:-1;if(u>=d){H++;area+=u}else{L--;area+=d}}
  const plotW=st.main.timeScale().width(),maxW=plotW*.26;
  for(let j=0;j<N;j++){const y1=st.cs.priceToCoordinate(lo+(j+1)*step),y0=st.cs.priceToCoordinate(lo+j*step);if(y1==null||y0==null)continue;
    const hgt=Math.max(1,Math.abs(y0-y1)-1),y=Math.min(y0,y1)+.5,inVA=j>=L&&j<=H;const wu=up[j]/max*maxW,wd=dn[j]/max*maxW;
    g.globalAlpha=inVA?.42:.18;g.fillStyle='#3987e5';g.fillRect(plotW-wu-wd,y,wu,hgt);g.fillStyle='#e34948';g.fillRect(plotW-wd,y,wd,hgt)}
  g.globalAlpha=.9;const py=st.cs.priceToCoordinate(lo+(poc+.5)*step);
  if(py!=null){g.strokeStyle='#f7931a';g.setLineDash([5,4]);g.lineWidth=1.3;g.beginPath();g.moveTo(0,py);g.lineTo(plotW,py);g.stroke();g.setLineDash([]);
    g.fillStyle='#f7931a';g.font='600 11px Inter,system-ui,sans-serif';g.fillText('POC '+fmtK(lo+(poc+.5)*step),6,py-4)}
  g.globalAlpha=1;
}

// ---------- analysis panel
function renderTA(){
  const A=TA.analysis[st.cur];const box=document.getElementById('cm-ta');if(!A){box.innerHTML='';return}
  const r=A.read,s=A.snapshot,esc=x=>String(x).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
  const cls=r.bias==='Bullish'?'bull':r.bias==='Bearish'?'bear':'neu';
  const li=a=>(a||[]).map(x=>`<li>${esc(x)}</li>`).join('');
  const levels=(r.levels||[]).slice().sort((a,b)=>b.price-a.price);let rows='',placed=false;
  levels.forEach(x=>{if(!placed&&x.price<s.price){rows+=`<tr class="now"><td>${fmtP(s.price)}</td><td>Now</td><td></td></tr>`;placed=true}
    rows+=`<tr><td>${fmtP(x.price)}</td><td><span class="t ${x.type==='support'?'s':'r'}">${x.type==='support'?'Support':'Resistance'}</span></td><td>${esc(x.why)}${x.confluence?'<span class="conf">CONFLUENCE</span>':''}</td></tr>`});
  if(!placed)rows+=`<tr class="now"><td>${fmtP(s.price)}</td><td>Now</td><td></td></tr>`;
  const src=r.source==='rules'?'Rule-based analysis · add an Anthropic key for an AI analyst read':'AI analyst read ('+esc(r.source)+')';
  box.innerHTML=`<div class="ta-card"><div class="ta-head"><h2 style="margin:0">Technical analysis</h2><span class="bias ${cls}">${esc(r.bias)}</span>
     <span class="ai-tag">${esc(r.confidence)} confidence</span><span class="ai-tag">${src}</span></div>
     <p class="ta-sum">${esc(r.summary)}</p>
     <h4>Trend</h4><ul>${li(r.trend)}</ul><h4>Momentum</h4><ul>${li(r.momentum)}</ul><h4>Volume</h4><ul>${li(r.volume)}</ul>
     <div class="ta-lt"><b>For a long-term holder:</b> ${esc(r.long_term)}</div></div>
   <div class="ta-card"><h4 style="margin-top:0">Key levels (daily)</h4><table class="lvl">${rows}</table>
     <h4>Scenarios</h4><div class="scen">${(r.scenarios||[]).map(x=>`<div><b>${esc(x.name)}</b>${esc(x.trigger)} → ${esc(x.target)}</div>`).join('')}</div>
     <h4>What changes the view</h4><p style="margin:4px 0;font-size:14px">${esc(r.invalidation)}</p>
     <p class="small muted" style="margin-top:12px">Technical analysis describes probabilities from past price behaviour. It is not financial advice.</p></div>`;
}

// ---------- controls
function sync(){
  document.getElementById('cm-title').textContent='BTC / '+st.cur.toUpperCase();
  document.querySelectorAll('#cm-cur button').forEach(b=>b.classList.toggle('on',b.dataset.v===st.cur));
  document.querySelectorAll('#cm-tf button').forEach(b=>b.classList.toggle('on',b.dataset.v===st.tf));
  document.querySelectorAll('#cm-ind button').forEach(b=>b.classList.toggle('on',!!st.show[b.dataset.k]));
}
window.openChart=function(cur){st.cur=cur||st.cur;modal.hidden=false;document.body.style.overflow='hidden';sync();build(false);renderTA();
  if(location.hash!=='#chart')history.replaceState(null,'','#chart')};
function close(){modal.hidden=true;document.body.style.overflow='';destroy();st.main=null;if(location.hash==='#chart')history.replaceState(null,'',location.pathname+location.search)}
document.getElementById('cm-close').onclick=close;
document.addEventListener('keydown',ev=>{if(ev.key==='Escape'&&!modal.hidden)close()});
document.querySelectorAll('#cm-cur button').forEach(b=>b.onclick=()=>{st.cur=b.dataset.v;sync();build(false);renderTA()});
document.querySelectorAll('#cm-tf button').forEach(b=>b.onclick=()=>{st.tf=b.dataset.v;sync();build(false)});
document.querySelectorAll('#cm-ind button').forEach(b=>b.onclick=()=>{st.show[b.dataset.k]=st.show[b.dataset.k]?0:1;sync();
  if(b.dataset.k==='vpvr')drawVP();else build(true)});
let rz;addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(drawVP,80)});
document.querySelectorAll('[data-open-chart]').forEach(el=>{el.addEventListener('click',()=>openChart(el.dataset.openChart));
  el.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();openChart(el.dataset.openChart)}})});
if(location.hash==='#chart')openChart('usd');
})();
'''


def assets(ta_data: dict | None) -> tuple[str, str, str]:
    """(css, html, script) to splice into the dashboard page; empty strings if there is no chart data."""
    if not ta_data:
        return "", "", ""
    lib = VENDOR.read_text() if VENDOR.exists() else ""
    data = json.dumps(ta_data, separators=(",", ":"), default=str).replace("</", "<\\/")
    script = f"<script>{lib}</script>\n<script>const TA={data};\n{JS}</script>"
    return CSS, HTML, script
