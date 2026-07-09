// ═══════════════════════════════════════════════════════════════════════════
//  poly-wallets.js — „Polymarket Edge & Smart-Money"-Dashboard  (v2 09.07.2026)
//
//  Visuell (Chart.js 4 ist im SPA geladen + SVG-Micro-Charts). Philosophie (mit
//  Experten-Agent abgestimmt): Die EDGE ist das Signal, die Whales sind Veto —
//  Pinnacle (de-viggt) = scharfer Anker, Polymarket = Trade-Gegenseite.
//
//  Aufbau:
//    · KPI-Band (Volumen · Live-Edges · größte Edge · Whale-Kapital · Sentiment)
//    · EDGE-SCATTER (Hero-Grafik: Pinnacle-Fair vs Poly-Preis, Bubble=Volumen)
//    · EDGE-BOARD  — Zeilen mit Steam-Sparkline (Linienbewegung) + Prob-Bar + Chips
//    · DRILLDOWN   — Steam-Kurve (Chart.js), Whale-Donut (SVG), Conviction-Gauges
//    · EXIT-WATCH · FLOW-TAPE · LEADERBOARD
//
//  Daten (dataset-aware, Liga-ready): {ds}_poly_prices.json · {ds}_poly_wallets.json
//    · {ds}-data.json (Teams+Pinnacle) · {ds}-odds-history.json (Steam-Kurven)
// ═══════════════════════════════════════════════════════════════════════════

let _polyWalletsLoaded = false;
let _pwState = { open: null };
let _pwCache = null;
let _pwCharts = [];   // Chart.js-Instanzen (vor Re-Render zerstören)

const PW_SPREAD_HAIRCUT = 1.5, PW_NOISE = 2.0, PW_TRADE = 4.0, PW_MOVE_FRESH = 2.0;
const PW_C = { home:'#4cc2ff', away:'#ff5d5d', draw:'#f5c518', over:'#2dd47e', under:'#a78bfa',
  teal:'#5eead4', txt:'#e6ebf5', mut:'#76819c', dim:'#414c66', card:'#0f1626', green:'#2dd47e', red:'#ff6b6b' };

function _pwDataset(){ return (typeof window!=='undefined' && window._pwDataset) ? window._pwDataset : 'wm'; }
function _pwFiles(){
  const ds=_pwDataset();
  return ds==='liga'
    ? { prices:'liga_poly_prices.json', wallets:'liga_poly_wallets.json', data:'liga-data.json', hist:'liga-odds-history.json' }
    : { prices:'wm_poly_prices.json', wallets:'wm_poly_wallets.json', data:'wm2026-data.json', hist:'wm2026-odds-history.json' };
}

function initPolyWallets(){
  const panel=document.getElementById('polyWalletsPanel');
  if(!panel || _polyWalletsLoaded) return;
  _polyWalletsLoaded=true;
  _pwInjectStyle();
  panel.innerHTML='<div class="pw-loading">🐋 Lade Polymarket-Edge, Smart-Money & Steam-Kurven…</div>';
  const f=_pwFiles(), b='?t='+Date.now();
  const wmP=(typeof window!=='undefined' && window.WM2026_DATA && _pwDataset()==='wm')
    ? Promise.resolve(window.WM2026_DATA)
    : fetch(f.data+b,{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null);
  Promise.all([
    wmP,
    fetch(f.prices+b,{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null),
    fetch(f.wallets+b,{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null),
    fetch(f.hist+b,{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null),
  ]).then(([wm,prices,wallets,hist])=>{
    _pwCache={wm,prices,wallets,hist};
    _pwRender();
  });
}

// ── Format ──────────────────────────────────────────────────────────────────
function _pwUsd(v){const n=Number(v)||0;if(n>=1e6)return '$'+(n/1e6).toFixed(2)+'M';if(n>=1e3)return '$'+(n/1e3).toFixed(n>=1e4?0:1)+'K';return '$'+Math.round(n);}
function _pwPct(p){return (p*100).toFixed(0)+'%';}
function _pwPP(v){return (v>=0?'+':'−')+Math.abs(v).toFixed(1)+'pp';}
function _pwWallet(w){if(!w)return '—';const s=String(w);return s.length>12?s.slice(0,6)+'…'+s.slice(-4):s;}
function _pwLink(w){return 'https://polymarket.com/profile/'+encodeURIComponent(w);}
function _pwAgo(ts){return (ts && typeof _timeAgo==='function')?_timeAgo(ts):'';}
function _pwFlag(flag){if(!flag)return '<span class="pw-flag">🏳️</span>';const s=String(flag);if(s.indexOf('<img')===0)return s.replace('<img','<img class="pw-logo"');if(/^https?:\/\//.test(s))return '<img class="pw-logo" src="'+s+'" alt="" loading="lazy">';return '<span class="pw-flag">'+s+'</span>';}
// Flagge/Logo NUR des im Pick genannten Teams (side). Remis/unbekannt → beide (kein Team einzeln gemeint).
function _pwSideFlag(teams,key,side){
  if(!key||!teams)return '';
  const parts=String(key).split('-'); if(parts.length<2)return '';
  const hf=teams[parts[0]]&&teams[parts[0]].flag, af=teams[parts[parts.length-1]]&&teams[parts[parts.length-1]].flag;
  let flags;
  if(side==='home') flags=_pwFlag(hf);
  else if(side==='away') flags=_pwFlag(af);
  else { if(!hf&&!af)return ''; flags=_pwFlag(hf)+_pwFlag(af); }
  return '<span class="pw-mflags">'+flags+'</span>';
}

function _pwTeamsMap(wm){const m={};Object.values((wm&&wm.groups)||{}).forEach(g=>(g.teams||[]).forEach(t=>{if(t&&t.id)m[t.id]={name:t.name||t.id,flag:t.flag};}));return m;}
function _pwOddsMap(wm){return (wm&&wm.odds)||{};}
function _pwDevig1x2(hw,dr,aw){if(!(hw>1&&dr>1&&aw>1))return null;const a=1/hw,b=1/dr,c=1/aw,s=a+b+c;return {home:a/s,draw:b/s,away:c/s};}
function _pwDevig2(o,u){if(!(o>1&&u>1))return null;const a=1/o,b=1/u,s=a+b;return {over:a/s,under:b/s};}
function _pwLiq(vol){const v=Number(vol)||0;if(v>=100000)return{tier:'deep',icon:'🌊',label:'tiefer Markt',ok:true};if(v>=15000)return{tier:'mid',icon:'💧',label:'mittel',ok:true};return{tier:'low',icon:'·',label:'dünn',ok:false};}
function _pwVerdict(net,liq){if(!liq.ok&&net<PW_TRADE+1)return{v:'THIN',cls:'thin'};if(net>=PW_TRADE)return{v:'TRADE',cls:'trade'};if(net>=PW_NOISE)return{v:'THIN',cls:'thin'};return{v:'NOISE',cls:'noise'};}
function _pwHoursToKO(iso){if(!iso)return null;const t=Date.parse(String(iso).replace(' ','T'));if(isNaN(t))return null;return (t-Date.now())/3.6e6;}
function _pwSideCol(s){return PW_C[s]||(s==='bttsY'?PW_C.over:s==='bttsN'?PW_C.under:PW_C.txt);}

// ── Edges bauen ─────────────────────────────────────────────────────────────
function _pwBuildEdges(prices,oddsMap){
  const rows=[]; const P=(prices&&prices.prices)||{};
  Object.entries(P).forEach(([key,m])=>{
    const o=oddsMap[key]||{};
    const pf=_pwDevig1x2(o.hw,o.dr,o.aw);
    const op=o.odds_open||{}; const openf=_pwDevig1x2(op.hw,op.dr,op.aw);
    const H=m.homeName||key.split('-')[0], A=m.awayName||key.split('-')[1];
    const legs=[
      {side:'home',poly:m.hw,fair:pf&&pf.home,open:openf&&openf.home,label:H+' Sieg'},
      {side:'draw',poly:m.dr,fair:pf&&pf.draw,open:openf&&openf.draw,label:'Unentschieden'},
      {side:'away',poly:m.aw,fair:pf&&pf.away,open:openf&&openf.away,label:A+' Sieg'},
    ];
    const pou=_pwDevig2(o.o25,o.u25);
    legs.push({side:'over',mkt:'ou',poly:m.poly_o25,fair:pou&&pou.over,label:'Über 2.5 Tore'});
    legs.push({side:'under',mkt:'ou',poly:m.poly_u25,fair:pou&&pou.under,label:'Unter 2.5 Tore'});
    const pbt=_pwDevig2(o.bttsY,o.bttsN);
    legs.push({side:'bttsY',mkt:'btts',poly:m.poly_btts,fair:pbt&&pbt.over,label:'Beide treffen — Ja'});
    legs.push({side:'bttsN',mkt:'btts',poly:m.poly_btts_no,fair:pbt&&pbt.under,label:'Beide treffen — Nein'});
    legs.forEach(l=>{
      if(!(l.poly>0&&l.poly<1)||!(l.fair>0))return;
      const gross=(l.fair-l.poly)*100, net=gross-PW_SPREAD_HAIRCUT;
      const liq=_pwLiq(m.vol);
      const fresh=(l.open!=null && (l.fair-l.open)*100>=PW_MOVE_FRESH);
      rows.push({key,match:H+' – '+A,homeId:m.homeId,awayId:m.awayId,kickoff:m.kickoff,koH:_pwHoursToKO(m.kickoff),
        vol:m.vol,mkt:l.mkt||'1x2',side:l.side,ticket:l.label,poly:l.poly,fair:l.fair,gross,net,liq,fresh,verdict:_pwVerdict(net,liq)});
    });
  });
  rows.sort((a,b)=>b.net-a.net);
  return rows;
}

// ── Pinnacle-Zeitreihe (Steam-Kurven) ───────────────────────────────────────
function _pwPinnSeries(hist,key){
  const arr=(hist&&hist[key])||[]; const out={home:[],draw:[],away:[]};
  arr.forEach(s=>{ if(!s||s.bk!=='pinnacle')return; const d=_pwDevig1x2(s.hw,s.dr,s.aw); if(!d)return;
    const t=Date.parse(String(s.ts).replace(' ','T')); if(isNaN(t))return;
    out.home.push({x:t,y:d.home*100}); out.draw.push({x:t,y:d.draw*100}); out.away.push({x:t,y:d.away*100}); });
  return out;
}
// implizite Serie einer beliebigen Seite als reine y-Werte (für Sparkline)
function _pwSideSpark(hist,key,side){
  const s=_pwPinnSeries(hist,key); const m={home:s.home,draw:s.draw,away:s.away}[side];
  if(!m)return []; return m.slice(-20).map(p=>p.y);
}

// ── Whale-Conviction ────────────────────────────────────────────────────────
function _pwClusterFor(w,key,side){const cl=(w&&w.clustersAll)||[];return cl.find(c=>c.key===key&&c.side===side)||null;}
function _pwConviction(w,key,side){
  const match=(w&&w.matches&&w.matches[key])||null; const cl=_pwClusterFor(w,key,side);
  if(!match&&!cl)return null;
  const pos=((match&&match.topPositions)||[]).filter(p=>p.side===side);
  const sideUsd=pos.reduce((s,p)=>s+(p.usd||0),0), nW=pos.length;
  const topShare=sideUsd>0?(pos[0]?pos[0].usd/sideUsd:0):0;
  const cluster=cl?(cl.cluster||0):nW, net=cl?(cl.netFlowUsd||0):0;
  let sc=Math.min(6,cluster*1.6)+Math.max(0,2-topShare*2.5); if(net>0)sc+=1.2; else if(net<0)sc-=1.5;
  sc=Math.max(0,Math.min(10,sc));
  return {score:Math.round(sc*10)/10,sideUsd,nWallets:nW,topShare,cluster,net};
}

// ═══════════════════════════ SVG-Micro-Charts ══════════════════════════════
function _pwSpark(vals,color){
  if(!vals||vals.length<2)return '<span class="pw-spark-empty">—</span>';
  const w=88,h=26,pad=2; const min=Math.min(...vals),max=Math.max(...vals),rng=(max-min)||1;
  const pts=vals.map((v,i)=>{const x=pad+i*(w-2*pad)/(vals.length-1);const y=h-pad-((v-min)/rng)*(h-2*pad);return x.toFixed(1)+','+y.toFixed(1);});
  const up=vals[vals.length-1]>=vals[0]; const col=color||(up?PW_C.green:PW_C.red);
  const area='M'+pts[0]+' L'+pts.join(' ')+' L'+(w-pad)+','+h+' L'+pad+','+h+' Z';
  return '<svg class="pw-spark" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none">'
    +'<path d="'+area+'" fill="'+col+'" opacity="0.12"/>'
    +'<polyline points="'+pts.join(' ')+'" fill="none" stroke="'+col+'" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
    +'<circle cx="'+pts[pts.length-1].split(',')[0]+'" cy="'+pts[pts.length-1].split(',')[1]+'" r="2.2" fill="'+col+'"/></svg>';
}
// Prob-Balken: Poly (Marker) vs Pinnacle-Fair (Marker) auf 0-100 Skala
function _pwProbBar(poly,fair,col){
  const p=Math.max(0,Math.min(100,poly*100)), f=Math.max(0,Math.min(100,fair*100));
  const lo=Math.min(p,f),hi=Math.max(p,f);
  return '<div class="pw-pbar"><div class="pw-pbar-gap" style="left:'+lo+'%;width:'+(hi-lo)+'%;background:'+col+'"></div>'
    +'<div class="pw-pbar-m pw-pbar-poly" style="left:'+p+'%" title="Poly '+p.toFixed(0)+'%"></div>'
    +'<div class="pw-pbar-m pw-pbar-fair" style="left:'+f+'%;background:'+PW_C.teal+'" title="Pinnacle '+f.toFixed(0)+'%"></div></div>';
}
// Donut (SVG) aus Segmenten [{v,color,label}]
function _pwDonut(segs,center){
  const tot=segs.reduce((s,x)=>s+x.v,0)||1; const R=42,C=2*Math.PI*R; let off=0;
  let rings='';
  segs.forEach(sg=>{const frac=sg.v/tot;const len=frac*C;
    rings+='<circle cx="60" cy="60" r="'+R+'" fill="none" stroke="'+sg.color+'" stroke-width="15" stroke-dasharray="'+len+' '+(C-len)+'" stroke-dashoffset="'+(-off)+'" transform="rotate(-90 60 60)"/>';
    off+=len;});
  return '<svg class="pw-donut" viewBox="0 0 120 120">'+rings
    +'<text x="60" y="56" text-anchor="middle" class="pw-donut-c1">'+(center&&center[0]||'')+'</text>'
    +'<text x="60" y="72" text-anchor="middle" class="pw-donut-c2">'+(center&&center[1]||'')+'</text></svg>';
}
// Radial-Gauge 0-10
function _pwGauge(val,color,label){
  const R=30,C=Math.PI*R; const frac=Math.max(0,Math.min(10,val))/10;
  return '<div class="pw-gauge"><svg viewBox="0 0 76 46">'
    +'<path d="M8 42 A30 30 0 0 1 68 42" fill="none" stroke="#1a2338" stroke-width="7" stroke-linecap="round"/>'
    +'<path d="M8 42 A30 30 0 0 1 68 42" fill="none" stroke="'+color+'" stroke-width="7" stroke-linecap="round" stroke-dasharray="'+(frac*C)+' '+C+'"/>'
    +'<text x="38" y="40" text-anchor="middle" class="pw-gauge-v">'+val.toFixed(1)+'</text></svg>'
    +'<div class="pw-gauge-l" style="color:'+color+'">'+label+'</div></div>';
}

// ═══════════════════════════════ RENDER ════════════════════════════════════
function _pwRender(){
  const panel=document.getElementById('polyWalletsPanel'); if(!panel||!_pwCache)return;
  _pwDestroyCharts();
  const {wm,prices,wallets,hist}=_pwCache;
  const teams=_pwTeamsMap(wm), oddsMap=_pwOddsMap(wm);
  const edges=_pwBuildEdges(prices,oddsMap);
  const hasPoly=wallets&&((wallets.topPositionsAll||[]).length||(wallets.matches&&Object.keys(wallets.matches).length));
  if(!hasPoly&&!edges.length){
    panel.innerHTML='<div class="pw-empty"><div class="pw-empty-ico">🐋</div><h2>Polymarket Edge & Smart-Money</h2>'
      +'<p>Noch keine Daten. Der Mac-Runner befüllt <code>'+_pwFiles().wallets+'</code> + <code>'+_pwFiles().prices+'</code> stündlich (Polymarket geoblockt).</p></div>';
    return;
  }
  const upd=wallets&&wallets.updatedAt?_pwAgo(wallets.updatedAt):'—';
  let h='<div class="pw-head"><div><h1>🐋 Polymarket <span class="pw-accent">Edge</span> & Smart-Money</h1>'
    +'<p class="pw-sub">Wo Polymarket vs. dem scharfen Pinnacle-Anker fehlbepreist ist — bestätigt oder gevetot vom großen Geld. <b>Die Edge ist das Signal, die Whales sind das Veto.</b></p></div>'
    +'<div class="pw-stamp">Stand '+upd+'<br><span>Beträge geschätzt (Anteile × Preis)</span></div></div>';
  h+=_pwKpiBand(edges,wallets);
  h+=_pwScatterSection(edges);
  h+=_pwEdgeBoard(edges,teams,wallets,hist);
  h+=_pwExitWatch(wallets,teams);
  h+=_pwFlowTape(wallets,teams);
  h+=_pwLeaderboard(wallets,teams);
  panel.innerHTML=h;
  // Charts nach DOM-Insert zeichnen
  _pwDrawScatter(edges);
  if(_pwState.open) _pwDrawDrillChart(edges,hist);
}

// ── KPI-Band ────────────────────────────────────────────────────────────────
function _pwKpiBand(edges,wallets){
  const vol=(_pwCache.prices&&_pwCache.prices.prices)?Object.values(_pwCache.prices.prices).reduce((s,m)=>s+(m.vol||0),0):0;
  const live=edges.filter(e=>e.net>=PW_NOISE).length;
  const big=edges.length?edges[0].net:0;
  const whaleCap=((wallets&&wallets.topPositionsAll)||[]).reduce((s,p)=>s+(p.usd||0),0);
  const cl=(wallets&&wallets.clustersAll)||[]; const buy=cl.reduce((s,c)=>s+(c.buyUsd||0),0),sell=cl.reduce((s,c)=>s+(c.sellUsd||0),0);
  const senti=(buy+sell)>0?(buy-sell)/(buy+sell):0;
  const card=(ic,lbl,val,sub,col)=>'<div class="pw-kpi"><div class="pw-kpi-ic">'+ic+'</div><div class="pw-kpi-b">'
    +'<div class="pw-kpi-v" style="color:'+(col||PW_C.txt)+'">'+val+'</div><div class="pw-kpi-l">'+lbl+'</div>'
    +(sub?'<div class="pw-kpi-s">'+sub+'</div>':'')+'</div></div>';
  return '<div class="pw-kpis">'
    +card('💧','Getracktes Volumen',_pwUsd(vol),'über '+((_pwCache.prices&&_pwCache.prices.prices)?Object.keys(_pwCache.prices.prices).length:0)+' Märkte')
    +card('⚡','Live-Edges',String(live),'≥'+PW_NOISE+'pp handelbar',live>0?PW_C.green:PW_C.mut)
    +card('🎯','Größte Edge',_pwPP(big),big>=PW_TRADE?'TRADE':big>=PW_NOISE?'THIN':'unter Schwelle',big>=PW_TRADE?PW_C.green:big>=PW_NOISE?PW_C.draw:PW_C.mut)
    +card('🐋','Whale-Kapital',_pwUsd(whaleCap),'Top-Positionen')
    +card(senti>=0?'📈':'📉','Sentiment',(senti>=0?'+':'−')+Math.abs(senti*100).toFixed(0)+'%',senti>=0?'Netto-Kauf':'Netto-Verkauf',senti>=0?PW_C.green:PW_C.red)
    +'</div>';
}

// ── Edge-Scatter (Hero-Grafik, Chart.js) ────────────────────────────────────
function _pwScatterSection(edges){
  const pts=edges.filter(e=>e.fair>0&&e.poly>0);
  if(!pts.length)return '';
  return '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">📊 Edge-Landkarte</span>'
    +'<span class="pw-sec-note">Jede Blase = ein Markt-Outcome · X Pinnacle-Fair, Y Poly-Preis · unter der Diagonale = Poly zu billig (Value) · Größe = Volumen</span></div>'
    +'<div class="pw-chartwrap"><canvas id="pwScatter"></canvas></div></section>';
}
function _pwDrawScatter(edges){
  const el=document.getElementById('pwScatter'); if(!el||typeof Chart==='undefined')return;
  const mk=(cls)=>edges.filter(e=>e.verdict.cls===cls&&e.fair>0&&e.poly>0).map(e=>({x:e.fair*100,y:e.poly*100,e}));
  const rad=(ctx)=>{const v=ctx.raw&&ctx.raw.e?ctx.raw.e.vol:0;return Math.max(4,Math.min(20,4+Math.sqrt((v||0)/1000)));};
  const ds=(cls,color)=>({data:mk(cls),backgroundColor:color+'cc',borderColor:color,borderWidth:1,pointRadius:rad,pointHoverRadius:rad});
  try{
  const c=new Chart(el,{type:'scatter',
    data:{datasets:[
      Object.assign(ds('trade',PW_C.green),{label:'TRADE'}),
      Object.assign(ds('thin',PW_C.draw),{label:'THIN'}),
      Object.assign(ds('noise',PW_C.mut),{label:'NOISE'}),
      {label:'fair',type:'line',data:[{x:0,y:0},{x:100,y:100}],borderColor:PW_C.dim,borderDash:[5,5],borderWidth:1,pointRadius:0,fill:false},
    ]},
    options:{responsive:true,maintainAspectRatio:false,
      scales:{x:{min:0,max:100,title:{display:true,text:'Pinnacle-Fair %',color:PW_C.mut},ticks:{color:PW_C.mut},grid:{color:'#1a2338'}},
              y:{min:0,max:100,title:{display:true,text:'Poly-Preis %',color:PW_C.mut},ticks:{color:PW_C.mut},grid:{color:'#1a2338'}}},
      plugins:{legend:{labels:{color:PW_C.mut,usePointStyle:true,filter:i=>i.text!=='fair'}},
        tooltip:{callbacks:{label:(ctx)=>{const e=ctx.raw&&ctx.raw.e;if(!e)return '';return [e.ticket+' — '+e.match,'Poly '+(e.poly*100).toFixed(0)+'% · Pinnacle '+(e.fair*100).toFixed(0)+'% · Edge '+_pwPP(e.net),'Vol '+_pwUsd(e.vol)];}}}}}
  });
  _pwCharts.push(c);
  }catch(err){}
}

// ── Edge-Board ──────────────────────────────────────────────────────────────
function _pwEdgeBoard(edges,teams,wallets,hist){
  const shown=edges.filter(e=>e.net>=PW_NOISE);
  let h='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">⚡ Edge-Board</span>'
    +'<span class="pw-sec-note">Netto nach Spread-Haircut ('+PW_SPREAD_HAIRCUT+'pp) · Kurve = Pinnacle-Linienbewegung · Klick → Steam-Chart</span></div>';
  const list=shown.length?shown.slice(0,40):edges.slice(0,6);
  if(!shown.length) h+='<div class="pw-none">Keine handelbare Fehlbepreisung ≥'+PW_NOISE+'pp — Poly & Pinnacle liegen eng. Unten die größten Sub-Schwellen-Gaps:</div>';
  h+='<div class="pw-board">';
  list.forEach(e=>{h+=_pwEdgeRow(e,teams,wallets,hist);});
  h+='</div></section>';
  return h;
}
function _pwEdgeRow(e,teams,wallets,hist){
  const wc=(e.mkt==='1x2')?_pwWhaleChip(wallets,e.key,e.side):null;
  const col=_pwSideCol(e.side);
  const koLbl=e.koH==null?'':(e.koH<0?'läuft':(e.koH<1?'<1h':Math.round(e.koH)+'h'));
  const id=e.key+'|'+e.side, open=_pwState.open===id;
  const spark=(e.mkt==='1x2')?_pwSpark(_pwSideSpark(hist,e.key,e.side)):'';
  return '<div class="pw-row '+(open?'pw-row-open':'')+'" onclick="_pwToggle(\''+id+'\')">'
    +'<div class="pw-row-main">'
    +'<div class="pw-teams">'+_pwFlag(teams[e.homeId]&&teams[e.homeId].flag)+_pwFlag(teams[e.awayId]&&teams[e.awayId].flag)
    +'<div class="pw-tk"><div class="pw-ticket" style="color:'+col+'">'+e.ticket+'</div>'
    +'<div class="pw-match">'+e.match+(koLbl?' · <span class="pw-ko">'+koLbl+'</span>':'')+'</div></div></div>'
    +'<div class="pw-mid">'+(spark?'<div class="pw-spark-wrap">'+spark+'</div>':'')+_pwProbBar(e.poly,e.fair,col)+'</div>'
    +'<div class="pw-edge"><div class="pw-edge-n pw-'+e.verdict.cls+'">'+_pwPP(e.net)+'</div>'
    +'<div class="pw-chips"><span class="pw-vd pw-'+e.verdict.cls+'">'+e.verdict.v+'</span>'
    +'<span class="pw-liq" title="'+e.liq.label+' · Vol '+_pwUsd(e.vol)+'">'+e.liq.icon+'</span>'
    +(e.fresh?'<span class="pw-fresh" title="Pinnacle zog seit Opening zu dieser Seite — Poly hinkt nach">🔥 STEAM</span>':'')
    +(wc?wc.chip:'')+'</div></div></div>'
    +(open?_pwDrill(e,teams,wallets):'')+'</div>';
}
function _pwWhaleChip(w,key,side){
  const cv=_pwConviction(w,key,side); if(!cv||(cv.cluster<1&&cv.sideUsd<3000))return null;
  if(cv.net<0)return{chip:'<span class="pw-wh pw-wh-fade" title="Smart Money läuft netto RAUS">🐋 EXIT</span>',cv};
  if(cv.cluster>=3)return{chip:'<span class="pw-wh pw-wh-conf" title="'+cv.cluster+' unabhängige Wallets · Conv '+cv.score+'/10">🐋 KONSENS '+cv.cluster+'</span>',cv};
  if(cv.sideUsd>=5000)return{chip:'<span class="pw-wh pw-wh-soft" title="Conv '+cv.score+'/10">🐋 '+_pwUsd(cv.sideUsd)+'</span>',cv};
  return{chip:'',cv};
}

// ── Drilldown ───────────────────────────────────────────────────────────────
function _pwDrill(e,teams,wallets){
  const match=(wallets&&wallets.matches&&wallets.matches[e.key])||null;
  const sides=[{s:'home',label:(match&&match.home)||e.homeId},{s:'draw',label:'Remis'},{s:'away',label:(match&&match.away)||e.awayId}];
  const pos=(match&&match.topPositions)||[]; const usd={home:0,draw:0,away:0}; pos.forEach(p=>{if(usd[p.side]!=null)usd[p.side]+=(p.usd||0);});
  const tot=usd.home+usd.draw+usd.away;
  let h='<div class="pw-drill" onclick="event.stopPropagation()"><div class="pw-drill-grid">';
  // Links: Steam-Kurve (Chart.js)
  h+='<div class="pw-drill-card"><div class="pw-drill-t">Pinnacle-Steam (Fair-% über Zeit)</div>'
    +'<div class="pw-chartwrap pw-chartwrap-sm"><canvas id="pwDrill"></canvas></div>'
    +'<div class="pw-drill-legend"><span><i style="background:'+PW_C.home+'"></i>'+sides[0].label+'</span>'
    +'<span><i style="background:'+PW_C.draw+'"></i>Remis</span><span><i style="background:'+PW_C.away+'"></i>'+sides[2].label+'</span></div></div>';
  // Rechts: Whale-Donut
  h+='<div class="pw-drill-card"><div class="pw-drill-t">Smart-Money-Verteilung</div>';
  if(tot>0){
    h+='<div class="pw-donut-wrap">'+_pwDonut([{v:usd.home,color:PW_C.home},{v:usd.draw,color:PW_C.draw},{v:usd.away,color:PW_C.away}],[_pwUsd(tot),'Whale-$'])
      +'<div class="pw-donut-leg">'
      +'<span><i style="background:'+PW_C.home+'"></i>'+sides[0].label+' '+_pwUsd(usd.home)+'</span>'
      +'<span><i style="background:'+PW_C.draw+'"></i>Remis '+_pwUsd(usd.draw)+'</span>'
      +'<span><i style="background:'+PW_C.away+'"></i>'+sides[2].label+' '+_pwUsd(usd.away)+'</span></div></div>';
  } else h+='<div class="pw-none-sm">Keine erfassten Whale-Positionen.</div>';
  h+='</div></div>';
  // Conviction-Gauges
  h+='<div class="pw-gauges">';
  sides.forEach(sd=>{const cv=_pwConviction(wallets,e.key,sd.s);h+=_pwGauge(cv?cv.score:0,_pwSideCol(sd.s),sd.label+(cv?(' · '+(cv.cluster||0)+'W'):''));});
  h+='</div>';
  // Top-Whales
  const top=pos.slice().sort((a,b)=>b.usd-a.usd).slice(0,6);
  if(top.length){h+='<div class="pw-drill-t" style="margin-top:6px">Größte Wallets hier</div><div class="pw-whales">';
    top.forEach(p=>{h+='<div class="pw-whale"><a href="'+_pwLink(p.wallet)+'" target="_blank" rel="noopener">'+_pwWallet(p.wallet)+'</a>'
      +'<span style="color:'+_pwSideCol(p.side)+'">'+(p.pick||p.side)+'</span><b>'+_pwUsd(p.usd)+'</b></div>';});
    h+='</div>';}
  h+='</div>';
  return h;
}
function _pwDrawDrillChart(edges,hist){
  const el=document.getElementById('pwDrill'); if(!el||typeof Chart==='undefined')return;
  const id=_pwState.open; if(!id)return; const key=id.split('|')[0];
  const s=_pwPinnSeries(hist,key); if(!s.home.length)return;
  try{
  const c=new Chart(el,{type:'line',
    data:{datasets:[
      {label:'Heim',data:s.home,borderColor:PW_C.home,backgroundColor:'transparent',borderWidth:2,pointRadius:0,tension:.25},
      {label:'Remis',data:s.draw,borderColor:PW_C.draw,backgroundColor:'transparent',borderWidth:1.5,pointRadius:0,tension:.25},
      {label:'Auswärts',data:s.away,borderColor:PW_C.away,backgroundColor:'transparent',borderWidth:2,pointRadius:0,tension:.25},
    ]},
    options:{responsive:true,maintainAspectRatio:false,parsing:false,
      scales:{x:{type:'linear',display:false},y:{ticks:{color:PW_C.mut,callback:v=>v+'%'},grid:{color:'#1a2338'}}},
      plugins:{legend:{display:false},tooltip:{enabled:false}}}
  });
  _pwCharts.push(c);
  }catch(err){}
}

// ── Exit-Watch / Flow-Tape / Leaderboard ────────────────────────────────────
function _pwExitWatch(w){
  const cl=(w&&w.clustersAll)||[];
  const ex=cl.filter(c=>(c.netFlowUsd||0)<=-2000&&typeof c.hoursToKickoff==='number'&&c.hoursToKickoff>=0&&c.hoursToKickoff<=24).sort((a,b)=>(a.netFlowUsd||0)-(b.netFlowUsd||0));
  if(!ex.length)return '';
  let h='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker pw-red">⚠️ Exit-Liquidität</span>'
    +'<span class="pw-sec-note">Whales laufen nah am Anpfiff netto RAUS — Veto</span></div><div class="pw-board">';
  ex.forEach(c=>{const ko=c.hoursToKickoff<1?'<1h':Math.round(c.hoursToKickoff)+'h';
    h+='<div class="pw-row pw-row-veto"><div class="pw-row-main"><div class="pw-teams"><span class="pw-flag">⚠️</span>'
      +'<div class="pw-tk"><div class="pw-ticket" style="color:'+_pwSideCol(c.side)+'">'+(c.pick||c.side)+'</div>'
      +'<div class="pw-match">'+(c.match||c.key)+' · <span class="pw-ko">Anpfiff in '+ko+'</span></div></div></div>'
      +'<div class="pw-edge"><div class="pw-edge-n pw-noise">'+_pwUsd(c.netFlowUsd)+'</div><div class="pw-chips"><span class="pw-wh pw-wh-fade">🐋 EXIT</span></div></div></div></div>';});
  h+='</div></section>'; return h;
}
function _pwFlowTape(w,teams){
  const tr=(w&&w.bigTradesAll)||[]; if(!tr.length)return '';
  let h='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">📟 Flow-Tape</span>'
    +'<span class="pw-sec-note">Jüngste große Trades — frische Edge oder schon gegessen?</span></div><div class="pw-tape">';
  tr.slice(0,25).forEach(t=>{const buy=(t.action||'').toUpperCase()==='BUY';
    h+='<div class="pw-tp-row"><span class="pw-tp-act '+(buy?'pw-buy':'pw-sell')+'">'+(buy?'KAUF':'VERK')+'</span>'
      +_pwSideFlag(teams,t.key,t.side)
      +'<div class="pw-tp-mid"><a href="'+_pwLink(t.wallet)+'" target="_blank" rel="noopener">'+_pwWallet(t.wallet)+'</a>'
      +'<span style="color:'+_pwSideCol(t.side)+'">'+(t.pick||t.side)+'</span> · '+(t.match||t.key)
      +(t.price?' @'+Math.round(t.price*100)+'¢':'')+(_pwAgo(t.ts)?' · '+_pwAgo(t.ts):'')+'</div><b>'+_pwUsd(t.usd)+'</b></div>';});
  h+='</div></section>'; return h;
}
function _pwLeaderboard(w,teams){
  const pos=(w&&w.topPositionsAll)||[]; if(!pos.length)return '';
  const max=pos[0]?pos[0].usd:1;
  let h='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🏦 Whale-Leaderboard</span>'
    +'<span class="pw-sec-note">Größte Einzelpositionen (Discovery)</span></div><div class="pw-lb">';
  pos.slice(0,20).forEach((p,i)=>{const wpc=Math.max(6,(p.usd/max)*100);
    h+='<div class="pw-lb-row"><span class="pw-rank '+(i<3?'pw-rank-top':'')+'">'+(i+1)+'</span>'
      +_pwSideFlag(teams,p.key,p.side)
      +'<div class="pw-lb-mid"><a href="'+_pwLink(p.wallet)+'" target="_blank" rel="noopener">'+_pwWallet(p.wallet)+'</a>'
      +'<div class="pw-lb-bar"><i style="width:'+wpc+'%;background:'+_pwSideCol(p.side)+'"></i></div>'
      +'<div class="pw-lb-sub"><span style="color:'+_pwSideCol(p.side)+'">'+(p.pick||p.side)+'</span> · '+(p.match||p.key)+'</div></div>'
      +'<b>'+_pwUsd(p.usd)+'</b></div>';});
  h+='</div></section>'; return h;
}

// ── Toggle / Charts-Lifecycle ───────────────────────────────────────────────
function _pwToggle(id){ _pwState.open=(_pwState.open===id)?null:id; _pwRender(); }
function _pwDestroyCharts(){ _pwCharts.forEach(c=>{try{c.destroy();}catch(e){}}); _pwCharts=[]; }

// ── Styles ──────────────────────────────────────────────────────────────────
function _pwInjectStyle(){
  if(document.getElementById('pw-style'))return;
  const css=`
  #polyWalletsPanel{color:#e6ebf5}
  #polyWalletsPanel .pw-loading,#polyWalletsPanel .pw-empty{text-align:center;color:#76819c;padding:48px 16px;line-height:1.7}
  #polyWalletsPanel .pw-empty-ico{font-size:44px;margin-bottom:10px}#polyWalletsPanel .pw-empty h2{color:#e6ebf5;margin:0 0 8px}
  #polyWalletsPanel code{background:#0f1626;padding:2px 6px;border-radius:5px;font-size:12px;color:#9db2d6}
  #polyWalletsPanel .pw-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;margin-bottom:20px}
  #polyWalletsPanel .pw-head h1{font-size:24px;font-weight:800;margin:0 0 6px}#polyWalletsPanel .pw-accent{color:#5eead4}
  #polyWalletsPanel .pw-sub{color:#8a95ad;font-size:13px;line-height:1.6;margin:0;max-width:640px}#polyWalletsPanel .pw-sub b{color:#cdd6ea}
  #polyWalletsPanel .pw-stamp{color:#76819c;font-size:12px;text-align:right;white-space:nowrap}#polyWalletsPanel .pw-stamp span{color:#4b566e;font-size:11px}
  #polyWalletsPanel .pw-kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:11px;margin-bottom:26px}
  #polyWalletsPanel .pw-kpi{display:flex;gap:11px;align-items:center;background:linear-gradient(145deg,#13203a,#0d1524);border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:14px 15px}
  #polyWalletsPanel .pw-kpi-ic{font-size:22px;opacity:.9}
  #polyWalletsPanel .pw-kpi-v{font-size:21px;font-weight:800;font-family:ui-monospace,monospace;line-height:1.1}
  #polyWalletsPanel .pw-kpi-l{font-size:11px;color:#8a95ad;margin-top:3px;font-weight:600}
  #polyWalletsPanel .pw-kpi-s{font-size:10px;color:#5b667e;margin-top:1px}
  #polyWalletsPanel .pw-sec{margin-bottom:30px}
  #polyWalletsPanel .pw-sec-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:12px}
  #polyWalletsPanel .pw-kicker{font-size:12px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:#5eead4;background:rgba(94,234,212,.1);padding:4px 10px;border-radius:7px}
  #polyWalletsPanel .pw-kicker.pw-red{color:#ff8a6d;background:rgba(255,123,93,.12)}
  #polyWalletsPanel .pw-sec-note{color:#76819c;font-size:12px}
  #polyWalletsPanel .pw-chartwrap{background:linear-gradient(145deg,#111a2b,#0d1420);border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:14px;height:340px}
  #polyWalletsPanel .pw-chartwrap-sm{height:180px;padding:8px}
  #polyWalletsPanel .pw-board{display:flex;flex-direction:column;gap:9px}
  #polyWalletsPanel .pw-row{background:linear-gradient(180deg,#111a2b,#0e1524);border:1px solid rgba(255,255,255,.06);border-radius:14px;overflow:hidden;cursor:pointer;transition:border-color .15s}
  #polyWalletsPanel .pw-row:hover{border-color:rgba(94,234,212,.35)}#polyWalletsPanel .pw-row-open{border-color:rgba(94,234,212,.5)}#polyWalletsPanel .pw-row-veto{border-color:rgba(255,123,93,.3)}
  #polyWalletsPanel .pw-row-main{display:grid;grid-template-columns:1.4fr 1.2fr auto;gap:14px;align-items:center;padding:12px 15px}
  #polyWalletsPanel .pw-teams{display:flex;align-items:center;gap:8px;min-width:0}
  #polyWalletsPanel .pw-flag{font-size:20px;line-height:1}#polyWalletsPanel .pw-logo{width:22px;height:22px;border-radius:50%;object-fit:cover;background:#0f1626;vertical-align:middle}
  #polyWalletsPanel .pw-tk{min-width:0}#polyWalletsPanel .pw-ticket{font-weight:700;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #polyWalletsPanel .pw-match{font-size:11.5px;color:#76819c;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}#polyWalletsPanel .pw-ko{color:#9db2d6}
  #polyWalletsPanel .pw-mid{display:flex;align-items:center;gap:10px}
  #polyWalletsPanel .pw-spark-wrap{width:88px;height:26px;flex-shrink:0}#polyWalletsPanel .pw-spark{width:88px;height:26px;display:block}#polyWalletsPanel .pw-spark-empty{color:#414c66;font-size:11px;width:88px;display:inline-block;text-align:center}
  #polyWalletsPanel .pw-pbar{position:relative;flex:1;height:8px;background:#0f1626;border-radius:5px;min-width:70px}
  #polyWalletsPanel .pw-pbar-gap{position:absolute;top:0;height:100%;opacity:.28;border-radius:5px}
  #polyWalletsPanel .pw-pbar-m{position:absolute;top:-2px;width:3px;height:12px;border-radius:2px;transform:translateX(-1.5px)}
  #polyWalletsPanel .pw-pbar-poly{background:#c6d0e4}
  #polyWalletsPanel .pw-edge{display:flex;flex-direction:column;align-items:flex-end;gap:5px;min-width:92px}
  #polyWalletsPanel .pw-edge-n{font-family:ui-monospace,monospace;font-weight:800;font-size:19px}
  #polyWalletsPanel .pw-trade{color:#2dd47e}#polyWalletsPanel .pw-thin{color:#f5c518}#polyWalletsPanel .pw-noise{color:#76819c}
  #polyWalletsPanel .pw-chips{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}
  #polyWalletsPanel .pw-vd{font-size:9.5px;font-weight:800;padding:2px 7px;border-radius:5px;letter-spacing:.5px}
  #polyWalletsPanel .pw-vd.pw-trade{background:rgba(45,212,126,.16);color:#2dd47e}#polyWalletsPanel .pw-vd.pw-thin{background:rgba(245,197,24,.14);color:#f5c518}#polyWalletsPanel .pw-vd.pw-noise{background:rgba(118,129,156,.14);color:#8a95ad}
  #polyWalletsPanel .pw-liq{font-size:12px}
  #polyWalletsPanel .pw-fresh{font-size:9.5px;font-weight:800;padding:2px 7px;border-radius:5px;background:rgba(255,138,109,.16);color:#ff8a6d}
  #polyWalletsPanel .pw-wh{font-size:9.5px;font-weight:800;padding:2px 7px;border-radius:5px;white-space:nowrap}
  #polyWalletsPanel .pw-wh-conf{background:rgba(94,234,212,.16);color:#5eead4}#polyWalletsPanel .pw-wh-soft{background:rgba(167,139,250,.16);color:#a78bfa}#polyWalletsPanel .pw-wh-fade{background:rgba(255,93,93,.16);color:#ff7b7b}
  #polyWalletsPanel .pw-drill{border-top:1px solid rgba(255,255,255,.06);padding:14px 15px;background:#0c121f;cursor:default}
  #polyWalletsPanel .pw-drill-grid{display:grid;grid-template-columns:1.3fr 1fr;gap:12px}
  #polyWalletsPanel .pw-drill-card{background:#0f1626;border:1px solid rgba(255,255,255,.05);border-radius:12px;padding:11px}
  #polyWalletsPanel .pw-drill-t{font-size:10.5px;font-weight:800;text-transform:uppercase;letter-spacing:.6px;color:#5eead4;margin:0 0 8px}
  #polyWalletsPanel .pw-drill-legend,#polyWalletsPanel .pw-donut-leg{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:#9db2d6;margin-top:7px}
  #polyWalletsPanel .pw-drill-legend i,#polyWalletsPanel .pw-donut-leg i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;vertical-align:middle}
  #polyWalletsPanel .pw-donut-wrap{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  #polyWalletsPanel .pw-donut{width:110px;height:110px;flex-shrink:0}
  #polyWalletsPanel .pw-donut-c1{fill:#e6ebf5;font-size:15px;font-weight:800;font-family:ui-monospace,monospace}#polyWalletsPanel .pw-donut-c2{fill:#76819c;font-size:9px;text-transform:uppercase;letter-spacing:1px}
  #polyWalletsPanel .pw-donut-leg{flex-direction:column;gap:5px}
  #polyWalletsPanel .pw-gauges{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:12px}
  #polyWalletsPanel .pw-gauge{background:#0f1626;border:1px solid rgba(255,255,255,.05);border-radius:12px;padding:8px;text-align:center}
  #polyWalletsPanel .pw-gauge svg{width:76px;height:46px}#polyWalletsPanel .pw-gauge-v{fill:#e6ebf5;font-size:15px;font-weight:800;font-family:ui-monospace,monospace}
  #polyWalletsPanel .pw-gauge-l{font-size:10.5px;font-weight:700;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #polyWalletsPanel .pw-whales{display:flex;flex-direction:column;gap:5px}
  #polyWalletsPanel .pw-whale{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;font-size:12.5px}
  #polyWalletsPanel .pw-whale a{font-family:ui-monospace,monospace;color:#c6d0e4;text-decoration:none;border-bottom:1px dashed #414c66}#polyWalletsPanel .pw-whale b{font-family:ui-monospace,monospace}
  #polyWalletsPanel .pw-tape,#polyWalletsPanel .pw-lb{display:flex;flex-direction:column;gap:6px}
  #polyWalletsPanel .pw-tp-row,#polyWalletsPanel .pw-lb-row{display:grid;grid-template-columns:auto auto 1fr auto;gap:11px;align-items:center;background:#0f1626;border:1px solid rgba(255,255,255,.05);border-radius:11px;padding:10px 13px}
  #polyWalletsPanel .pw-mflags{display:inline-flex;align-items:center;gap:2px;white-space:nowrap}
  #polyWalletsPanel .pw-mflags .pw-flag{font-size:17px}
  #polyWalletsPanel .pw-mflags .pw-logo{width:19px;height:19px}
  #polyWalletsPanel .pw-tp-act{font-size:10px;font-weight:800;padding:3px 8px;border-radius:6px}#polyWalletsPanel .pw-buy{background:rgba(45,212,126,.14);color:#2dd47e}#polyWalletsPanel .pw-sell{background:rgba(255,93,93,.14);color:#ff5d5d}
  #polyWalletsPanel .pw-tp-mid,#polyWalletsPanel .pw-lb-mid{min-width:0;font-size:12px;color:#9db2d6;overflow:hidden}
  #polyWalletsPanel .pw-tp-mid{white-space:nowrap;text-overflow:ellipsis}
  #polyWalletsPanel .pw-tp-mid a,#polyWalletsPanel .pw-lb-mid a{font-family:ui-monospace,monospace;color:#e6ebf5;text-decoration:none;border-bottom:1px dashed #414c66;margin-right:6px}
  #polyWalletsPanel .pw-tp-row b,#polyWalletsPanel .pw-lb-row b{font-family:ui-monospace,monospace;font-weight:800;white-space:nowrap}
  #polyWalletsPanel .pw-lb-bar{height:5px;background:#0b1220;border-radius:3px;margin:4px 0;overflow:hidden}#polyWalletsPanel .pw-lb-bar i{display:block;height:100%;border-radius:3px}
  #polyWalletsPanel .pw-lb-sub{font-size:11px;color:#76819c;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #polyWalletsPanel .pw-rank{font-family:ui-monospace,monospace;font-weight:800;color:#414c66;font-size:13px;min-width:20px}#polyWalletsPanel .pw-rank-top{color:#5eead4}
  #polyWalletsPanel .pw-none,#polyWalletsPanel .pw-none-sm{color:#76819c;font-size:13px;background:#0f1626;border:1px dashed rgba(255,255,255,.08);border-radius:12px;padding:14px;margin-bottom:10px}#polyWalletsPanel .pw-none-sm{padding:20px;text-align:center}
  @media(max-width:820px){#polyWalletsPanel .pw-kpis{grid-template-columns:repeat(2,1fr)}#polyWalletsPanel .pw-drill-grid{grid-template-columns:1fr}}
  @media(max-width:620px){#polyWalletsPanel .pw-row-main{grid-template-columns:1fr auto}#polyWalletsPanel .pw-mid{display:none}#polyWalletsPanel .pw-gauges{grid-template-columns:1fr}}
  `;
  const st=document.createElement('style'); st.id='pw-style'; st.textContent=css; document.head.appendChild(st);
}
