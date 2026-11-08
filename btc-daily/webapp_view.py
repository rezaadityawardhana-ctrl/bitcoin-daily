"""Makes the dashboard behave like the iPhone app when opened in a phone browser.

- Installable: "Add to Home Screen" gives the ₿ icon and a full-screen app with no Safari bars (manifest + Apple meta tags).
- When opened from the home screen ("app mode"), it uses the app's dark theme, animated bitcoin background
  (gradient, glows, two drifting block chains, floating ₿ symbols) and branded splash.
- Live price: BTC/USD and BTC/CHF refresh from Coinbase every time the page is opened or brought back to the front.
- Offline: a service worker keeps the last copy (only on https, e.g. GitHub Pages).
- Status pill: when the report was built, whether the price is live, and a refresh button.
Add ?app=1 to the address to preview app mode in a normal browser.
"""

HEAD = r'''<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<script>(function(){var s=(window.navigator.standalone===true)||matchMedia('(display-mode: standalone)').matches||/[?&]app=1/.test(location.search);
if(s){document.documentElement.classList.add('app');document.documentElement.setAttribute('data-theme','dark')}})();</script>'''

CSS = r'''
#btc-bg{position:fixed;inset:0;width:100vw;height:100vh;z-index:0;pointer-events:none;display:none}
html.app #btc-bg{display:block}
html.app body{background:transparent!important;background-image:none!important}
html.app main{position:relative;z-index:1}
html.app body{padding-top:max(20px,env(safe-area-inset-top));padding-bottom:max(56px,env(safe-area-inset-bottom))}
#splash{position:fixed;inset:0;z-index:100;display:none;align-items:center;justify-content:center;flex-direction:column;gap:18px;
 background:#0e0f11;transition:opacity .45s ease}
html.app #splash{display:flex}
#splash.hide{opacity:0;pointer-events:none}
#splash .logo{width:112px;height:112px;border-radius:30px;display:grid;place-items:center;font-size:62px;font-weight:800;color:#1a1206;
 background:linear-gradient(145deg,#ffb54a,#f7931a 60%,#d97706);box-shadow:0 0 40px rgba(247,147,26,.45);animation:pop .6s cubic-bezier(.2,1.4,.4,1)}
#splash .t1{font-size:30px;font-weight:700;color:#f3f2ee}#splash .t2{font-size:14px;color:rgba(255,255,255,.6);margin-top:-12px}
@keyframes pop{from{transform:scale(.8);opacity:.4}to{transform:scale(1);opacity:1}}
#app-pill{position:fixed;right:16px;bottom:max(16px,env(safe-area-inset-bottom));z-index:40;display:none;align-items:center;gap:10px;
 padding:8px 14px;border-radius:999px;color:#fff;font-size:13px;font-weight:500;cursor:pointer;
 background:rgba(30,30,34,.72);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);border:1px solid rgba(247,147,26,.45);
 box-shadow:0 8px 24px rgba(0,0,0,.35)}
html.app #app-pill{display:flex}
#app-pill .dot{width:8px;height:8px;border-radius:50%;background:#30d158}#app-pill .dot.off{background:#ff9f0a}
#app-pill .b{display:none;color:#f7931a;font-weight:800;font-size:18px;line-height:1}
#app-pill.min{padding:0;width:44px;height:44px;justify-content:center}#app-pill.min .txt,#app-pill.min .rf{display:none}
#app-pill.min .b{display:block}#app-pill.min .dot{position:absolute;top:8px;right:8px;width:9px;height:9px}
#app-pill .txt{white-space:nowrap}
#app-pill .rf{border:0;background:rgba(255,255,255,.12);color:#fff;border-radius:999px;font:inherit;font-size:12px;padding:3px 10px}
.live-flash{animation:lf 1.2s ease}@keyframes lf{0%{color:#f7931a}100%{color:inherit}}
@media (prefers-reduced-motion:reduce){#splash .logo{animation:none}}
'''

HTML = r'''
<canvas id="btc-bg" aria-hidden="true"></canvas>
<div id="splash" aria-hidden="true"><div class="logo">₿</div><div class="t1">Bitcoin Daily</div><div class="t2">Cycle · Flows · Mood</div></div>
<div id="app-pill" role="button" tabindex="0" aria-label="Status and refresh"><span class="dot"></span><span class="b">₿</span>
  <span class="txt">Loading…</span><button class="rf" type="button">Refresh</button></div>
'''

JS = r'''
(function(){
const app=document.documentElement.classList.contains('app');
// ---------- live price (USD + CHF) from Coinbase
const fmt=(v,cur)=>cur==='usd'?'$'+Math.round(v).toLocaleString('en-US'):Math.round(v).toLocaleString('en-US');
let liveAt=null;
async function livePrices(){
  try{
    const get=async p=>parseFloat((await (await fetch('https://api.coinbase.com/v2/prices/'+p+'/spot',{cache:'no-store'})).json()).data.amount);
    const [u,c]=await Promise.all([get('BTC-USD'),get('BTC-CHF')]);
    [['usd',u],['chf',c]].forEach(([k,v])=>document.querySelectorAll('[data-live="'+k+'"]').forEach(el=>{
      const t=fmt(v,k);if(el.textContent!==t){el.textContent=t;el.classList.remove('live-flash');void el.offsetWidth;el.classList.add('live-flash')}}));
    liveAt=new Date();
  }catch(e){liveAt=null}
  pill();
}
// ---------- status pill
const P=document.getElementById('app-pill');let timer;
function pill(expand){
  if(!P)return;const rep=new Date(window.REPORT_TIME||Date.now());
  const t=d=>d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
  const day=rep.toDateString()===new Date().toDateString()?'':rep.toLocaleDateString('en-GB',{day:'numeric',month:'short'})+' ';
  P.querySelector('.txt').textContent=(liveAt?'Live '+t(liveAt):'Offline copy')+' · report '+day+t(rep);
  P.querySelector('.dot').classList.toggle('off',!liveAt||!navigator.onLine);
  if(expand){P.classList.remove('min');clearTimeout(timer);timer=setTimeout(()=>P.classList.add('min'),3500)}
}
if(P){P.addEventListener('click',e=>{if(e.target.classList.contains('rf')){location.reload();return}pill(true)});}
// ---------- splash
const S=document.getElementById('splash');
if(app&&S){const t0=performance.now();window.addEventListener('load',()=>{setTimeout(()=>{S.classList.add('hide');setTimeout(()=>S.remove(),500)},Math.max(0,1100-(performance.now()-t0)))});
  setTimeout(()=>S&&S.classList.add('hide'),5000)}
// ---------- animated bitcoin background (same design as the iPhone app)
const cv=document.getElementById('btc-bg');
if(app&&cv){
  const g=cv.getContext('2d');const O='247,147,26',B='57,135,229';let W=0,H=0,dpr=1;
  const fract=v=>v-Math.floor(v);
  function size(){dpr=Math.min(2,window.devicePixelRatio||1);W=innerWidth;H=innerHeight;cv.width=W*dpr;cv.height=H*dpr;g.setTransform(dpr,0,0,dpr,0,0)}
  function glow(x,y,r,rgb,a){const gr=g.createRadialGradient(x,y,0,x,y,r);gr.addColorStop(0,'rgba('+rgb+','+a+')');gr.addColorStop(1,'rgba('+rgb+',0)');g.fillStyle=gr;g.fillRect(x-r,y-r,2*r,2*r)}
  function chain(y,t,speed,dir){const w=46,h=32,gap=30,step=w+gap;const shift=((t*speed)%step)*dir;g.strokeStyle='rgba('+O+',.16)';g.lineWidth=1.4;
    for(let x=-2*step+shift;x<W+step;x+=step){g.beginPath();g.roundRect(x,y-h/2,w,h,7);g.stroke();
      g.save();g.globalAlpha=.6;for(let r=0;r<3;r++){const ly=y-h/2+9+r*7;g.beginPath();g.moveTo(x+9,ly);g.lineTo(x+w-9-r*6,ly);g.lineWidth=1;g.stroke()}g.restore();
      g.setLineDash([4,3]);g.beginPath();g.moveTo(x+w,y);g.lineTo(x+step,y);g.stroke();g.setLineDash([])}}
  function frame(ms){const t=ms/1000;
    const lg=g.createLinearGradient(0,0,0,H);lg.addColorStop(0,'#121214');lg.addColorStop(1,'#08080a');g.fillStyle=lg;g.fillRect(0,0,W,H);
    const R=Math.max(W,320);glow(W*.85+Math.cos(t*.13)*40,H*.1+Math.sin(t*.17)*30,R*.85,O,.30);glow(W*.05+Math.sin(t*.11)*30,H*.92+Math.cos(t*.09)*30,R*.75,B,.18);
    chain(H*.24,t,14,-1);chain(H*.78,t,10,1);
    for(let i=0;i<16;i++){const s=i+1,rx=fract(Math.sin(s*12.9898)*43758.5453),ry=fract(Math.sin(s*78.233)*12345.678),sp=6+10*fract(Math.sin(s*3.7)*999.1),
      fs=14+26*fract(Math.sin(s*5.3)*777.7),tr=H+80,y=H+40-((ry*tr+t*sp)%tr),x=rx*W+Math.sin(t*.3+s)*12,a=.05+.08*fract(Math.sin(s*9.1)*555.5);
      g.save();g.translate(x,y);g.rotate(Math.sin(t*.2+s)*.21);g.fillStyle='rgba('+O+','+a+')';g.font='800 '+fs+'px system-ui,-apple-system,sans-serif';
      g.textAlign='center';g.textBaseline='middle';g.fillText('₿',0,0);g.restore()}
  }
  size();addEventListener('resize',size);
  const still=matchMedia('(prefers-reduced-motion: reduce)').matches;
  let last=0;function loop(ms){if(ms-last>33){frame(ms);last=ms}if(!still)requestAnimationFrame(loop)}requestAnimationFrame(loop);
}
// ---------- offline copy (https only, e.g. GitHub Pages)
if('serviceWorker' in navigator&&location.protocol==='https:'){navigator.serviceWorker.register('sw.js').catch(()=>{})}
livePrices();pill(true);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')livePrices()});
addEventListener('online',livePrices);addEventListener('offline',()=>pill(true));
})();
'''


def assets(report_time_iso: str) -> tuple[str, str, str, str]:
    """(head, css, html, script) to splice into the dashboard page."""
    script = f"<script>window.REPORT_TIME={report_time_iso!r};\n{JS}</script>"
    return HEAD, CSS, HTML, script
