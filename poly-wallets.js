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

// ── Datensätze (Liga-Auswahl oben im Tab) ───────────────────────────────────
// 12.07.2026 (Lucas: „im Whale-Wallets-Tab brauche ich oben eine Ligen-Auswahl, da wir danach
// weitere Ligen hinzufügen"). NEUE LIGA HINZUFÜGEN = EINE ZEILE hier. Der Rest (Fetch, Flaggen/
// Logos, Edge-Board, Charts) ist komplett generisch.
// Reihenfolge = Tab-Reihenfolge. 18.07.2026: MLS zuerst (laufende Saison + Poly-Liquidität),
// WM ans Ende — nach dem Finale am 19.07. ist sie Archiv, kein Einstieg.
const PW_DATASETS = [
  { id:'mls',  icon:'🇺🇸', label:'MLS',
    prices:'mls_poly_prices.json',  wallets:'mls_poly_wallets.json',
    data:'mls-data.json',           hist:'mls-odds-history.json' },
  { id:'liga', icon:'⚽', label:'Top-5',
    prices:'liga_poly_prices.json', wallets:'liga_poly_wallets.json',
    data:'liga-data.json',          hist:'liga-odds-history.json' },
  // 19.07.2026 (Lucas) — E-Sport als eigener Menüpunkt. „Poly-only": KEIN scharfer Pinnacle-Anker
  // (noAnchor) → kein Edge-vs-Pinnacle-Board, aber volle Smart-Money/Whale/Kohärenz-Sicht aus
  // Polys eigenen Daten. Dateien schreibt der Mac-Runner (fetch_poly_esports.py).
  { id:'esports', icon:'🎮', label:'E-Sport', noAnchor:true,
    prices:'esports_poly_prices.json', wallets:'esports_poly_wallets.json',
    data:null,                          hist:null },
  { id:'wm',   icon:'🏆', label:'WM 2026',
    prices:'wm_poly_prices.json',   wallets:'wm_poly_wallets.json',
    data:'wm2026-data.json',        hist:'wm2026-odds-history.json' },
];

// ⚠️ 12.07.2026 — BUG-FIX (Lucas: „im Whale-Tab erscheint nichts, wenn ich auf MLS klicke").
// Der aktive Datensatz lag in `window._pwDataset` — GENAU der Name der Funktion `_pwDataset()`.
// Top-Level-`function`-Deklarationen hängen im Browser aber selbst an `window`. `window._pwDataset = id`
// hat die FUNKTION mit dem String überschrieben → der nächste Aufruf warf
// „TypeError: _pwDataset is not a function" → _pwRender starb → Panel blieb leer.
// (WM lief, weil dort nie umgeschaltet werden musste.) Zustand heißt jetzt `_pwDsId` — nie wieder
// gleich benennen wie eine Funktion. Guard: tests/test_poly_wallets_dataset_switch.js
// 18.07.2026 (Lucas): Einstieg ist MLS statt WM — die WM endet mit dem Finale am 19.07.
// MLS ist der Datensatz mit laufenden Spielen UND echter Poly-Liquidität; Top-5 hat bewusst
// kein Polymarket (siehe registry.py-Gates), wäre als Default also dauerhaft leer.
const PW_DEFAULT_DS = 'mls';
let _pwDsId = PW_DEFAULT_DS;
function _pwDataset(){
  return PW_DATASETS.some(d=>d.id===_pwDsId) ? _pwDsId : PW_DEFAULT_DS;
}
function _pwFiles(){
  const ds=_pwDataset();
  return PW_DATASETS.find(d=>d.id===ds) || PW_DATASETS[0];
}
// Datensatz wechseln: Cache leeren, State zurücksetzen, neu laden.
function _pwSwitchDataset(id){
  if (!PW_DATASETS.some(d=>d.id===id) || _pwDataset()===id) return;
  _pwDsId = id;
  _pwCache = null;
  _pwState.open = null;
  _polyWalletsLoaded = false;
  _pwDestroyCharts();
  initPolyWallets();
}
// Warum sind keine Whales da? Ehrlich beantworten statt „keine Daten" (12.07.2026).
// Der Fetcher legt `emptyReason` ab: no_volume = API lieferte, aber der Markt ist noch leer.
function _pwWhyNoWhales(wallets){
  const r = wallets && wallets.emptyReason;
  if (r && r.code==='no_volume')
    return 'Noch keine Whale-Positionen: die Märkte sind frisch gelistet und haben unter '
      + _pwUsd(r.minWriteUsd) + ' offenes Interesse ('+r.gamesBelow+'/'+r.gamesSeen+' Spiele). '
      + 'Die Edges oben sind trotzdem gültig — Whales erscheinen, sobald echtes Geld fließt.';
  return 'Keine erfassten Whale-Positionen.';
}
function _pwDatasetTabs(){
  const cur=_pwDataset();
  return '<div class="pw-ds">'+PW_DATASETS.map(d=>
    '<button class="pw-ds-btn'+(d.id===cur?' pw-ds-on':'')+'" onclick="_pwSwitchDataset(\''+d.id+'\')">'
    +'<span>'+d.icon+'</span>'+d.label+'</button>').join('')+'</div>';
}

// ── View-Umschalter (19.07.2026): Edge-Board vs. „Liegt das Geld richtig?" ────
let _pwView='edge';
function _pwSetView(v){ if(v===_pwView)return; _pwView=v; _pwDestroyCharts(); _pwRender(); }
if(typeof window!=='undefined') window._pwSetView=_pwSetView;
function _pwViewTabs(){
  const b=(id,label)=>'<button class="pw-ds-btn'+(id===_pwView?' pw-ds-on':'')
    +'" onclick="_pwSetView(\''+id+'\')">'+label+'</button>';
  // 19.07.2026 (Lucas: „besser aufteilen") — 4 Unter-Reiter statt 9 gestapelter Sektionen.
  return '<div class="pw-ds" style="margin-top:-6px">'
    +b('edge','🎯 Chancen')+b('smart','💡 Smart-Money')+b('whales','🐋 Whales')
    +b('money','⚖️ Liegt das Geld richtig?')+'</div>';
}

// 25.07.2026 (Lucas: „alle Zahlen verwirrend, keine Ahnung was ich damit mache"). Pro Unter-Reiter
// EINE Klartext-Box: was zeige ich, und — wichtiger — was tust DU damit. Kein Jargon, ein Satz je.
const _PW_VIEW_INTRO = {
  edge:  ['🎯 Chancen — wo Polymarket „falscher\" liegt als die scharfe Pinnacle',
    'Kandidaten zum Dagegenhalten: je größer die Abweichung, desto interessanter. Aber Poly und Pinnacle sind meist im Einklang — leere/kleine Liste ist der Normalfall, kein Fehler.',
    'Große Lücke, die die Whales BESTÄTIGEN (nicht dagegen stehen) → beobachten. Nichts blind traden — erst wenn sich die Lücke über Tage zur Pinnacle schließt, war sie echt.'],
  smart: ['💡 Smart-Money — wo das GROSSE Geld liegt und wie konzentriert',
    'Zeigt, auf welche Seite die dicken Wallets gesetzt haben und wie einig sie sich sind. Das ist KEIN eigenes Wett-Signal.',
    'Nutze es als Bestätigung oder Veto für einen bestehenden Pick: steht das große Geld dahinter → Rückenwind; steht es dagegen → vorsichtig sein.'],
  whales:['🐋 Whales — die einzelnen großen Wallets',
    'Wer ist zu welchem Preis eingestiegen, jüngste große Trades, Trefferbilanz je Wallet. „Groß\" heißt nicht automatisch „treffsicher\".',
    'Nur Wallets mit bewiesener Trefferquote als Rückenwind nehmen; die bloß-großen ohne Track-Record ignorieren.'],
  money: ['💰 Das große Geld — alle Sportarten inkl. E-Sport',
    'Oben: auf welche Seite die Masse bei KOMMENDEN Spielen gesetzt hat (zum Folgen). Unten: der Rückblick — hatte die Masse bei aufgelösten Spielen recht?',
    'Kommenden Märkten mit klarer Geld-Mehrheit folgen — aber nur dort, wo der Rückblick unten 🟢 „Geld schärfer\" zeigt. Wo 🔴 „Preis besser\" steht, liegt die Masse daneben → faden.'],
};
// 25.07.2026 (Lucas: „Ligen oben weg, statt dessen ein Filter je Tab damit ich besser suchen kann").
// Globaler Sport-Filter über alle Sektionen (a/b/d). Kategorie robust aus Liga-Label ODER Sport-Key.
let _pwSportFilter='all';
function _pwSetSportFilter(cat){ _pwSportFilter=cat; _pwRender(); }
if(typeof window!=='undefined') window._pwSetSportFilter=_pwSetSportFilter;
function _pwSportCategory(s){
  const x=String(s||'').toLowerCase();
  if(/soccer|epl|ucl|mls|laliga|la-liga|liga|bundesliga|serie|ligue|fussball|fußball/.test(x)) return 'Fußball';
  if(/basketball|nba|nfl|americanfootball|baseball|mlb|icehockey|hockey|nhl|wnba|ncaa/.test(x)) return 'US-Sport';
  if(/esport|cs2|csgo|lol|dota|valorant/.test(x)) return 'E-Sport';
  if(/tennis|wta|atp/.test(x)) return 'Tennis';
  if(/mma|ufc|boxing|box|kampf/.test(x)) return 'Kampfsport';
  if(/golf/.test(x)) return 'Golf';
  if(/f1|formula|motor|nascar/.test(x)) return 'Motorsport';
  if(/cricket/.test(x)) return 'Cricket';
  return 'Sonstige';
}
const _PW_CAT_ICON={'Fußball':'⚽','US-Sport':'🏀','E-Sport':'🎮','Tennis':'🎾','Kampfsport':'🥊','Golf':'⛳','Motorsport':'🏎️','Cricket':'🏏','Sonstige':'🎯'};
// Filter-Chip-Leiste aus den tatsächlich vorhandenen Kategorien (order fix, nur präsente zeigen).
function _pwSportFilterBar(cats){
  const order=['Fußball','US-Sport','E-Sport','Tennis','Kampfsport','Golf','Motorsport','Cricket','Sonstige'];
  const present=order.filter(c=>cats.has(c));
  if(present.length<2) return '';   // nur eine Kategorie → Filter sinnlos
  const chip=(cat,label)=>{const on=_pwSportFilter===cat;
    return '<button onclick="_pwSetSportFilter(\''+cat+'\')" style="padding:5px 12px;border-radius:16px;border:1px solid '
      +(on?'#5eead4':'var(--border)')+';background:'+(on?'rgba(94,234,212,.16)':'transparent')+';color:'+(on?'#5eead4':'var(--muted)')
      +';font-size:12px;font-weight:'+(on?700:500)+';cursor:pointer;font-family:inherit">'+label+'</button>';};
  return '<div style="max-width:1000px;margin:0 auto 12px;display:flex;gap:7px;flex-wrap:wrap;align-items:center">'
    +'<span class="pw-mut" style="font-size:11px;margin-right:2px">Filter:</span>'
    +chip('all','Alle')+present.map(c=>chip(c,_PW_CAT_ICON[c]+' '+c)).join('')+'</div>';
}
function _pwSportPass(s){ return _pwSportFilter==='all' || _pwSportCategory(s)===_pwSportFilter; }

function _pwViewIntro(view){
  const t=_PW_VIEW_INTRO[view]; if(!t) return '';
  return '<div style="max-width:1000px;margin:6px auto 14px;padding:12px 16px;'
    +'background:rgba(94,234,212,.06);border-left:3px solid #5eead4;border-radius:0 10px 10px 0;">'
    +'<div style="font-size:14px;font-weight:800;color:#5eead4;margin-bottom:5px;">'+t[0]+'</div>'
    +'<div style="font-size:12.5px;color:var(--muted);line-height:1.55;margin-bottom:7px;">'+t[1]+'</div>'
    +'<div style="font-size:12.5px;color:var(--fg);line-height:1.55;">'
    +'<b style="color:#5eead4;">→ Was du damit tust:</b> '+t[2]+'</div></div>';
}

function initPolyWallets(){
  const panel=document.getElementById('polyWalletsPanel');
  if(!panel || _polyWalletsLoaded) return;
  _polyWalletsLoaded=true;
  _pwInjectStyle();
  panel.innerHTML='<div class="pw-loading">🐋 Lade Polymarket-Edge, Smart-Money & Steam-Kurven…</div>';
  const f=_pwFiles(), b='?t='+Date.now();
  // 19.07.2026 — Poly-Edge-Dateien aus dem Preis-Dateinamen ableiten (wm_poly_prices → wm_poly_*).
  // Fehlen sie (Liga hat kein Poly, oder Detektor lief noch nicht) → null, sauber abgefangen.
  const _derive=(suffix)=>f.prices.replace('poly_prices','poly_'+suffix);
  const jf=(url)=>url?fetch(url+b,{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null):Promise.resolve(null);
  const wmP=(typeof window!=='undefined' && window.WM2026_DATA && _pwDataset()==='wm')
    ? Promise.resolve(window.WM2026_DATA)
    : jf(f.data);   // E-Sport: f.data=null → null (kein Fixture-/Odds-Datensatz)
  Promise.all([
    wmP, jf(f.prices), jf(f.wallets), jf(f.hist),
    jf(_derive('coherence')), jf(_derive('settlement')), jf(_derive('wallet_ledger')),
    jf(_derive('money_accuracy')),
    jf('poly_money_broad.json'),   // liga-übergreifend (global, nicht datensatz-spezifisch)
    jf(_derive('smartmoney')),     // 19.07.2026 — war ungenutzt: Konzentration/Split/Breite
    jf('poly_money_broad_close.json'),  // 25.07.2026 (Lucas): kommende Märkte ALLER Sportarten → Sektion „Wo liegt das große Geld"
    jf('poly_cross_sport.json'),        // 25.07.2026 (Lucas): globale Edge Poly-vs-Pinnacle über alle Sportarten
  ]).then(([wm,prices,wallets,hist,coherence,settlement,ledger,moneyAcc,moneyBroad,smart,broadLive,crossSport])=>{
    _pwCache={wm,prices,wallets,hist,coherence,settlement,ledger,moneyAcc,moneyBroad,smart,broadLive,crossSport};
    _pwRender();
  }).catch(err=>{
    // 12.07.2026: Vorher gab es KEIN catch — eine Exception im Render (z.B. der
    // _pwDataset-Namensclash) ließ das Panel einfach leer stehen, ohne jeden Hinweis.
    // Stiller Ausfall → nie wieder: Fehler sichtbar machen, Liga-Umschalter bleibt bedienbar.
    console.error('[poly-wallets] Render fehlgeschlagen:', err);
    panel.innerHTML=_pwDatasetTabs()
      +'<div class="pw-empty"><div class="pw-empty-ico">⚠️</div><h2>Anzeige fehlgeschlagen</h2>'
      +'<p>Das Edge-Board konnte für <b>'+f.label+'</b> nicht gerendert werden.<br>'
      +'<code>'+String(err && err.message || err)+'</code></p></div>';
  });
}

// ── Format ──────────────────────────────────────────────────────────────────
function _pwEsc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
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
// (20.07.2026, Lucas: „über 125h — Aktualisierung?") Das Edge-Board zeigte Spiele bis zu Wochen im
// Voraus. Polymarket listet MLS-Märkte früh, aber weit draußen liegt fast kein Geld drin (Vol ~0) →
// der Preis ist ein Platzhalter, der „Edge" gegen Pinnacle ist Rauschen. Genauso wenig gehören schon
// GESPIELTE Spiele rein. Deshalb: nur Spiele im Anpfiff-Fenster [jetzt-3h .. +HORIZON] ins Board.
const PW_EDGE_HORIZON_H = 96;   // ~4 Tage — deckt den nächsten Spieltag ab, ohne leere Fern-Märkte
function _pwBuildEdges(prices,oddsMap){
  const rows=[]; const P=(prices&&prices.prices)||{};
  Object.entries(P).forEach(([key,m])=>{
    const _koH=_pwHoursToKO(m.kickoff);
    // Fenster-Filter: kein Anpfiff → behalten (kein Datum, nicht ausschließen); sonst muss er im
    // Fenster liegen. Schon angepfiffen (< -3h) oder zu weit weg (> HORIZON) → raus.
    if(_koH!=null && (_koH < -3 || _koH > PW_EDGE_HORIZON_H)) return;
    const o=oddsMap[key]||{};
    const pf=_pwDevig1x2(o.hw,o.dr,o.aw);
    const op=o.odds_open||{}; const openf=_pwDevig1x2(op.hw,op.dr,op.aw);
    const H=m.homeName||key.split('-')[0], A=m.awayName||key.split('-')[1];
    const legs=[
      {side:'home',poly:m.hw,fair:pf&&pf.home,open:openf&&openf.home,label:H+' Sieg'},
      {side:'draw',poly:m.dr,fair:pf&&pf.draw,open:openf&&openf.draw,label:'Unentschieden'},
      {side:'away',poly:m.aw,fair:pf&&pf.away,open:openf&&openf.away,label:A+' Sieg'},
    ];
    // O/U-Leiter komplett (19.07.2026): 1.5 / 2.5 / 3.5 — die Poly-Preise poly_o15/o35 lagen
    // ungenutzt. Fair aus Pinnacle (o.o15/o25/o35). Wo kein Pinnacle-Fair da ist (z.B. MLS ohne
    // TheOddsAPI-totals), überspringt der leg-Guard sauber. Fallback auf Softbook-Konsens (public_*),
    // damit die Linie auch ohne Pinnacle wenigstens gegen das Public bewertet wird.
    const _ouLegs=(oS,uS,pO,pU,lbl,mk)=>{
      let f=_pwDevig2(o[oS],o[uS]); let src='pinn';
      if(!f){ f=_pwDevig2(o['public_'+oS],o['public_'+uS]); src='public'; }
      const tag=src==='public'?' ᴾ':'';   // ᴾ = Fair aus Softbook-Konsens, nicht Pinnacle
      legs.push({side:'over',mkt:mk,poly:m[pO],fair:f&&f.over,fairSrc:src,label:'Über '+lbl+' Tore'+tag});
      legs.push({side:'under',mkt:mk,poly:m[pU],fair:f&&f.under,fairSrc:src,label:'Unter '+lbl+' Tore'+tag});
    };
    _ouLegs('o15','u15','poly_o15','poly_u15','1.5','ou15');
    _ouLegs('o25','u25','poly_o25','poly_u25','2.5','ou');
    _ouLegs('o35','u35','poly_o35','poly_u35','3.5','ou35');
    const pbt=_pwDevig2(o.bttsY,o.bttsN);
    legs.push({side:'bttsY',mkt:'btts',poly:m.poly_btts,fair:pbt&&pbt.over,label:'Beide treffen — Ja'});
    legs.push({side:'bttsN',mkt:'btts',poly:m.poly_btts_no,fair:pbt&&pbt.under,label:'Beide treffen — Nein'});
    legs.forEach(l=>{
      if(!(l.poly>0&&l.poly<1)||!(l.fair>0))return;
      const gross=(l.fair-l.poly)*100, net=gross-PW_SPREAD_HAIRCUT;
      const liq=_pwLiq(m.vol);
      const fresh=(l.open!=null && (l.fair-l.open)*100>=PW_MOVE_FRESH);
      rows.push({key,match:H+' – '+A,homeId:m.homeId,awayId:m.awayId,kickoff:m.kickoff,koH:_pwHoursToKO(m.kickoff),
        vol:m.vol,mkt:l.mkt||'1x2',side:l.side,ticket:l.label,poly:l.poly,fair:l.fair,fairSrc:l.fairSrc,gross,net,liq,fresh,verdict:_pwVerdict(net,liq)});
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
  // 25.07.2026 (Lucas: „schnell erkennbar"): die zwei Zahlen als SICHTBARE Beschriftung, nicht
  // nur im Tooltip. Poly = was der Markt zahlt (implizit), fair = de-viggte Pinnacle-Wahrscheinlichkeit.
  return '<div class="pw-pbar"><div class="pw-pbar-gap" style="left:'+lo+'%;width:'+(hi-lo)+'%;background:'+col+'"></div>'
    +'<div class="pw-pbar-m pw-pbar-poly" style="left:'+p+'%" title="Poly '+p.toFixed(0)+'%"></div>'
    +'<div class="pw-pbar-m pw-pbar-fair" style="left:'+f+'%;background:'+PW_C.teal+'" title="Pinnacle '+f.toFixed(0)+'%"></div></div>'
    +'<div style="font-size:10.5px;color:var(--muted);margin-top:3px;white-space:nowrap;">'
    +'Poly <b style="color:#a78bfa">'+p.toFixed(0)+'%</b> · fair <b style="color:'+PW_C.teal+'">'+f.toFixed(0)+'%</b></div>';
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
  const {wm,prices,wallets,hist,coherence,settlement,ledger,moneyAcc,moneyBroad,smart}=_pwCache;
  const teams=_pwTeamsMap(wm), oddsMap=_pwOddsMap(wm);
  const edges=_pwBuildEdges(prices,oddsMap);
  const hasPoly=wallets&&((wallets.topPositionsAll||[]).length||(wallets.matches&&Object.keys(wallets.matches).length));
  const f=_pwFiles();

  // 19.07.2026 (Lucas) — eigener Sub-View „Liegt das Geld richtig?" neben dem Edge-Board.
  if(_pwView==='money'){
    // (b) Wo liegt das große Geld (kommend, alle Sportarten) ZUERST, dann (d) Rückblick „liegt es richtig".
    // 25.07.2026 (Lucas: „Liga-Umschalter oben gehört weg"): der Wallets-Tab ist global über alle
    // Sportarten — kein Datensatz-Selektor mehr. (Sport-Filter je Sektion kommt als Nächstes.)
    panel.innerHTML=_pwViewTabs()+_pwViewIntro('money')
      +_pwMoneyLive(_pwCache.broadLive)+_pwMoneyBroad(moneyBroad)+_pwMoneyAccuracy(moneyAcc,teams);
    return;
  }
  if(!hasPoly&&!edges.length){
    // Liga-Auswahl AUCH im Leer-Zustand zeigen → man kann umschalten, wenn eine Liga noch nichts hat.
    panel.innerHTML=_pwDatasetTabs()
      +'<div class="pw-empty"><div class="pw-empty-ico">🐋</div><h2>Polymarket Edge & Smart-Money</h2>'
      +'<p>Für <b>'+f.label+'</b> noch keine Polymarket-Daten. Sobald der Runner '
      +'<code>'+f.wallets+'</code> + <code>'+f.prices+'</code> befüllt, erscheint hier das Edge-Board.</p></div>';
    return;
  }
  const upd=wallets&&wallets.updatedAt?_pwAgo(wallets.updatedAt):'—';
  const noAnchor=!!f.noAnchor;   // E-Sport: kein scharfer Pinnacle-Anker → Poly-only-Sicht

  const head='<div class="pw-head"><div><h1>'+(noAnchor?'🎮 Polymarket <span class="pw-accent">E-Sport</span> — Smart-Money'
      :'🐋 Polymarket <span class="pw-accent">Edge</span> & Smart-Money')+'</h1>'
    +'<p class="pw-sub">'+(noAnchor
      ? 'E-Sport hat keinen scharfen Buchmacher-Anker — deshalb <b>keine Edge-vs-Pinnacle-Ansicht</b>. Stattdessen die reine Poly-Sicht: <b>wo liegt das Geld, wie konzentriert, welche Wale, und wo widerspricht sich Poly selbst</b> (Arbitrage).'
      : 'Wo Polymarket vs. dem scharfen Pinnacle-Anker fehlbepreist ist — bestätigt oder gevetot vom großen Geld. <b>Die Edge ist das Signal, die Whales sind das Veto.</b>')+'</p></div>'
    +'<div class="pw-stamp">'+f.icon+' '+f.label+' · Stand '+upd+'<br><span>Beträge geschätzt (Anteile × Preis)</span></div></div>';

  // 19.07.2026 (Lucas: „besser aufteilen") — Sektionen auf Unter-Reiter verteilt, statt alle 9
  // untereinander. Jede Ansicht zeigt nur ihr Thema → kurze Scroll-Achse, klare Trennung.
  let h=_pwViewTabs()+_pwViewIntro(_pwView)+head+_pwKpiBand(edges,wallets);
  let drawScatter=false;
  if(_pwView==='smart'){
    // 💡 Smart-Money: wo liegt das Geld, wie konzentriert, welcher Fluss.
    h+=_pwSmartConcentration(smart,prices,teams);
    h+=_pwExitWatch(wallets,teams);
  }else if(_pwView==='whales'){
    // 🐋 Whales: (c) GLOBALE Einzel-Wale über alle Sportarten ZUERST (Lucas 25.07.2026),
    // dann die datensatz-eigenen Panels (Einstieg, jüngste Trades, Leaderboard).
    h+=_pwGlobalWhales(_pwCache.broadLive);
    h+=_pwWhaleEntryQuality(ledger);
    h+=_pwFlowTape(wallets,teams);
    h+=_pwLeaderboard(wallets,teams);
  }else{
    // 🎯 Chancen (Default): (a) GLOBALE Edge über alle Sportarten ZUERST (Lucas 25.07.2026),
    // dann die datensatz-eigenen Auflösungs-Lücken + interne Fehlbepreisung + Edge-Board.
    h+=_pwGlobalEdge(_pwCache.crossSport);
    h+=_pwSettlementBoard(settlement,teams);
    h+=_pwCoherenceBoard(coherence);
    if(!noAnchor){
      h+=_pwScatterSection(edges);
      h+=_pwEdgeBoard(edges,teams,wallets,hist);
      drawScatter=true;
    }
  }
  panel.innerHTML=h;
  if(drawScatter) _pwDrawScatter(edges);
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
  // 25.07.2026 (Lucas: „Zahlen schnell erkennbar"): Klartext-Labels statt „Live-Edges/THIN/Sentiment".
  return '<div class="pw-kpis">'
    +card('💧','Poly-Volumen',_pwUsd(vol),'über '+((_pwCache.prices&&_pwCache.prices.prices)?Object.keys(_pwCache.prices.prices).length:0)+' Märkte beobachtet')
    +card('⚡','Handelbare Chancen',String(live),'ab '+PW_NOISE+'pp Abweichung',live>0?PW_C.green:PW_C.mut)
    +card('🎯','Größter Vorteil',_pwPP(big),big>=PW_TRADE?'handelbar':big>=PW_NOISE?'dünn — nur beobachten':'kein echter Vorteil',big>=PW_TRADE?PW_C.green:big>=PW_NOISE?PW_C.draw:PW_C.mut)
    +card('🐋','Whale-Kapital',_pwUsd(whaleCap),'in den Top-Positionen')
    +card(senti>=0?'📈':'📉','Großes Geld',(senti>=0?'+':'−')+Math.abs(senti*100).toFixed(0)+'%',senti>=0?'kauft netto':'verkauft netto',senti>=0?PW_C.green:PW_C.red)
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

// ── Auflösungs-Lücken (19.07.2026) ───────────────────────────────────────────
// Feststehende Ergebnisse, die Poly noch unter 1.00 handelt. Risikoärmster Edge überhaupt:
// das Spiel ist vorbei, nur der Oracle hinkt. Quelle: poly_settlement_gap.py.
function _pwSettlementBoard(settlement,teams){
  const gaps=(settlement&&settlement.gaps)||[];
  if(!gaps.length) return '';
  const rows=gaps.slice(0,8).map(g=>{
    const pct=(g.gewinnerPreis*100).toFixed(0);
    return '<tr>'
      +'<td class="pw-cm">'+_pwEsc(g.match)+'</td>'
      +'<td><span class="pw-chip">'+_pwEsc(g.markt)+'</span></td>'
      +'<td class="pw-cn">'+_pwEsc(g.endstand)+'</td>'
      +'<td class="pw-cn">'+pct+'¢</td>'
      +'<td class="pw-cn pw-pos"><b>+'+g.gapPP.toFixed(1)+'pp</b></td>'
      +'<td class="pw-cn pw-mut">'+_pwUsd(g.vol)+'</td></tr>';
  }).join('');
  return '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">💰 Auflösungs-Lücken</span>'
    +'<span class="pw-sec-note">feststehend, noch nicht 1.00</span></div>'
    +'<p class="pw-sec-p">Das Ergebnis steht fest — der Gewinner-Ausgang handelt aber noch unter 100¢, '
    +'weil Polymarket erst verzögert auflöst. Kaufen und bis zur Auflösung halten = planbare pp. '
    +'<b>Rest-Risiko:</b> Oracle-Streit (selten).</p>'
    +'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    +'<th>Spiel</th><th>Markt</th><th>Endstand</th><th>Preis</th><th>Lücke</th><th>Vol</th>'
    +'</tr></thead><tbody>'+rows+'</tbody></table></div></section>';
}

// ── Poly-interne Fehlbepreisung (19.07.2026) ─────────────────────────────────
// Poly gegen sich selbst: Underround-Arb, Leiter-Widersprüche, fette Spreads. Kein Pinnacle-Anker.
function _pwCoherenceBoard(coherence){
  const f=(coherence&&coherence.findings)||[];
  if(!f.length) return '';
  const ic={underround:'🟢',ladder_inversion:'🟠',overround:'⚪'};
  const lbl={underround:'Arbitrage',ladder_inversion:'Widerspruch',overround:'fetter Spread'};
  const rows=f.slice(0,10).map(b=>'<tr>'
      +'<td class="pw-cm">'+_pwEsc(b.match)+'</td>'
      +'<td><span class="pw-chip">'+_pwEsc(b.markt)+'</span></td>'
      +'<td>'+(ic[b.typ]||'·')+' '+(lbl[b.typ]||b.typ)+'</td>'
      +'<td class="pw-cn'+(b.typ==='underround'?' pw-pos':'')+'">'+(b.summe!=null?b.summe.toFixed(3):'—')+'</td>'
      +'<td class="pw-cn"><b>'+(b.edgePP>=0?'+':'')+b.edgePP.toFixed(1)+'pp</b></td>'
      +'</tr>').join('');
  const n=coherence.arbCount||0;
  return '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🎯 Poly-interne Fehlbepreisung</span>'
    +'<span class="pw-sec-note">'+n+' Arb'+(n===1?'':'s')+' · ohne Pinnacle-Anker</span></div>'
    +'<p class="pw-sec-p">Polymarket hält seine eigenen Märkte nicht konsistent. '
    +'<b>🟢 Arbitrage</b>: Ja+Nein &lt; 1.00 → beide Seiten kaufen zahlt garantiert 1.00. '
    +'<b>🟠 Widerspruch</b>: mehr Tore teurer als weniger — eine Linie ist falsch. '
    +'<b>⚪ Spread</b>: hier nicht als Taker rein. '
    +'<i>Auf dünnen Märkten oft ein veralteter Preis — vor dem Handeln Tiefe prüfen.</i></p>'
    +'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    +'<th>Spiel</th><th>Markt</th><th>Typ</th><th>Summe</th><th>Edge</th>'
    +'</tr></thead><tbody>'+rows+'</tbody></table></div></section>';
}

// ── Whale-Einstiegsqualität (19.07.2026) ─────────────────────────────────────
// Nicht „wer ist groß", sondern „wer ist zu welchem Preis eingestiegen". Aus dem Wallet-Ledger
// (firstAvgPrice). Bis der Track-Record reift (Wochen), ist das der erste harte Qualitäts-Proxy:
// ein Whale, der billig einkauft, ist interessanter als einer, der teuer nachkauft.
function _pwWhaleEntryQuality(ledger){
  const pos=ledger&&ledger.positions?Object.values(ledger.positions):[];
  if(pos.length<3) return '';
  // Nach Größe sortieren, Einstiegspreis zeigen. (Wallet-CLV kommt, sobald Closing je Position da ist.)
  const top=pos.filter(p=>p.usd>=1000&&p.firstAvgPrice)
              .sort((a,b)=>b.usd-a.usd).slice(0,8);
  if(!top.length) return '';
  const rows=top.map(p=>{
    const entry=(p.firstAvgPrice*100).toFixed(0);
    // 19.07.2026 — avgPrice war ungenutzt: aktueller Schnitt vs. erster Einstieg zeigt, ob die
    // Wallet BILLIG rein und teuer nachgekauft hat (Overconfidence) oder günstig aufgestockt.
    let nach='<span class="pw-mut">—</span>';
    if(typeof p.avgPrice==='number' && Math.abs(p.avgPrice-p.firstAvgPrice)>=0.02){
      const up=p.avgPrice>p.firstAvgPrice;
      nach='<span style="color:'+(up?'#e3b341':'#3fb950')+'" title="'+(up?'teurer nachgekauft (Overconfidence?)':'günstig aufgestockt')+'">'
        +(up?'▲':'▼')+' '+(p.avgPrice*100).toFixed(0)+'¢</span>';
    }
    return '<tr>'
      +'<td><a href="'+_pwLink(p.wallet)+'" target="_blank" rel="noopener" class="pw-wl">'+_pwWallet(p.wallet)+'</a></td>'
      +'<td class="pw-cm">'+_pwEsc(p.pick||p.match||'—')+'</td>'
      +'<td class="pw-cn">'+_pwUsd(p.usd)+'</td>'
      +'<td class="pw-cn">'+entry+'¢</td>'
      +'<td class="pw-cn">'+nach+'</td></tr>';
  }).join('');
  const seit=ledger.updatedAt?_pwAgo(ledger.updatedAt):'—';
  return '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🐋 Whale-Einstiegsqualität</span>'
    +'<span class="pw-sec-note">Einstiegspreis, nicht nur Größe</span></div>'
    +'<p class="pw-sec-p">Aus dem Wallet-Ledger: zu welchem Preis sind die großen Wallets '
    +'ursprünglich rein? Der Einstieg (nicht die Positionsgröße) trennt scharfes von dummem Geld. '
    +'<i>Track-Record (CLV/ROI je Wallet) folgt, sobald genug Auflösungen gesammelt sind · Stand '+seit+'</i></p>'
    +'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    +'<th>Wallet</th><th>Spiel/Pick</th><th>Einsatz</th>'
    +'<th title="Preis, zu dem die Wallet zuerst eingestiegen ist — niedrig = früh/scharf">Einstieg</th>'
    +'<th title="Aktueller Durchschnittspreis: ▲ teurer nachgekauft (Overconfidence?) · ▼ günstig aufgestockt">nachgekauft zu</th>'
    +'</tr></thead><tbody>'+rows+'</tbody></table></div></section>';
}

// ── Breit über ALLE Poly-Ligen (19.07.2026, Lucas) ───────────────────────────
// „Wo hat die Masse mehr recht?" — alle Poly-Ligen mit Volumen ≥ Schwelle, triviale Favoriten
// (Quote < min) raus. Aus poly_money_broad.py (Mac-Runner, Polys eigene Auflösung).
// League-Tag → Kategorie (Ordnung, 19.07.2026, Lucas). Unbekannte → „Sonstige".
const PW_LEAGUE_CAT={
  nba:['US-Sport','🇺🇸'],nfl:['US-Sport','🇺🇸'],mlb:['US-Sport','🇺🇸'],nhl:['US-Sport','🇺🇸'],
  epl:['Fußball','⚽'],soccer:['Fußball','⚽'],ucl:['Fußball','⚽'],mls:['Fußball','⚽'],
  esports:['E-Sport','🎮'],cs2:['E-Sport','🎮'],lol:['E-Sport','🎮'],dota:['E-Sport','🎮'],valorant:['E-Sport','🎮'],
  tennis:['Tennis','🎾'],
  // 21.07.2026 (Lucas: „mehr Sport?") — ganzjährige Poly-Sportarten kategorisiert (statt „Sonstige").
  ufc:['Kampfsport','🥊'],mma:['Kampfsport','🥊'],boxing:['Kampfsport','🥊'],
  golf:['Golf','⛳'],f1:['Motorsport','🏎'],cricket:['Cricket','🏏'],
};
function _pwCatOf(league){const c=PW_LEAGUE_CAT[String(league||'').toLowerCase()];return c?c:['Sonstige','·'];}

function _pwMoneyBroad(broad){
  const b=broad||{};
  const V={geld_schaerfer:['🟢','#3fb950','Geld schärfer'],preis_besser:['🔴','#f85149','Preis besser'],gleichauf:['⚪','#8b949e','gleichauf']};
  if(!b.n && !(b.byLeague&&b.byLeague.length)){
    return '<div class="pw-sec" style="margin-top:6px"><div class="pw-sec-head">'
      +'<span class="pw-kicker">🌐 Alle Poly-Ligen</span>'
      +'<span class="pw-sec-note">liga-übergreifend · sammelt am Mac-Runner</span></div>'
      +'<div class="pw-sec-p">Breiter Scan über alles, was Polymarket anbietet — inkl. <b>🎮 E-Sport</b> '
      +'(CS2/LoL/Dota/Valorant), US-Sport, Fußball, Tennis (Volumen ≥ Schwelle, triviale Favoriten raus). '
      +'Zeigt je Liga, ob das Geld schärfer ist als der Preis. Füllt sich über die kommenden Tage, sobald der Runner läuft.</div></div>';
  }

  // „Vorsprung" = wie viel treffsicherer das Geld ggü. dem Preis ist (Brier-Differenz, intern).
  // Positiv = Geld schärfer. Wir zeigen NICHT die Roh-Brier-Zahlen (Fachjargon), sondern ein
  // Klartext-Urteil + die anschauliche Trefferquote.
  // 25.07.2026: respektiert den globalen Sport-Filter (die Leiste rendert die (b)-Sektion darüber).
  const leagues=(b.byLeague||[]).map(l=>({...l,edge:(l.brierPrice-l.brierMoney)})).filter(l=>_pwSportPass(l.league));

  // Highlight-Kacheln nur, wenn es überhaupt einen NENNENSWERTEN Unterschied gibt — sonst ist
  // „am schärfsten/dümmsten" bei quasi-gleichauf-Daten irreführend (aktuell alles ~gleichauf).
  let highlight='';
  const spread=leagues.filter(l=>Math.abs(l.edge)>=0.01);
  if(spread.length>=2){
    const s=spread.slice().sort((a,b)=>b.edge-a.edge);
    const best=s[0], worst=s[s.length-1];
    const tile=(t,l,col)=>'<div style="flex:1;min-width:200px;background:'+col+'14;border:1px solid '+col+'44;border-radius:12px;padding:12px 14px">'
      +'<div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px">'+t+'</div>'
      +'<div style="font-size:17px;font-weight:800;color:'+col+';margin-top:2px">'+_pwCatOf(l.league)[1]+' '+_pwEsc(l.league)+'</div>'
      +'<div style="font-size:12px;color:#8b949e">Geld trifft '+Math.round(l.moneyHitRate*100)+'% · '+l.n+' Spiele</div></div>';
    highlight='<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">'
      +tile('🏆 Masse weiß am meisten',best,'#3fb950')+tile('🃏 Masse liegt am öftesten daneben',worst,'#f85149')+'</div>';
  }

  // Nach Kategorie gruppieren (Ordnung). Trefferquote als Balken + Klartext-Urteil statt Brier-Zahlen.
  const cats={};
  leagues.forEach(l=>{const[cat,icon]=_pwCatOf(l.league);(cats[cat]=cats[cat]||{icon,rows:[],n:0}).rows.push(l);
    cats[cat].n+=l.n;});
  const catOrder=['Fußball','US-Sport','E-Sport','Tennis','Kampfsport','Golf','Motorsport','Cricket','Sonstige'];
  const hitBar=(pct,col)=>'<span style="display:inline-flex;align-items:center;gap:7px;justify-content:flex-end">'
    +'<span style="width:52px;height:7px;background:#1c2333;border-radius:4px;overflow:hidden;display:inline-block">'
    +'<i style="display:block;height:100%;width:'+pct+'%;background:'+col+'"></i></span>'
    +'<b style="color:#e6edf3;min-width:34px;text-align:right">'+pct+'%</b></span>';
  const row=l=>{const f=V[l.verdict]||['⚪','#8b949e','gleichauf'];
    const hit=Math.round(l.moneyHitRate*100);
    const hitCol=hit>=60?'#3fb950':hit>=45?'#5eead4':'#f0883e';
    return '<tr><td class="pw-cm">'+_pwEsc(l.league)+'</td><td class="pw-cn pw-mut">'+l.n+'</td>'
      +'<td class="pw-cn">'+hitBar(hit,hitCol)+'</td>'
      +'<td><span style="display:inline-block;padding:2px 9px;border-radius:20px;font-size:11.5px;font-weight:700;'
        +'background:'+f[1]+'1a;color:'+f[1]+'">'+f[0]+' '+f[2]+'</span></td></tr>';};
  const blocks=catOrder.filter(c=>cats[c]).map(cat=>{
    const c=cats[cat];
    return '<div style="margin-top:14px"><div style="padding:2px 2px 6px">'
      +'<span style="font-size:13px;font-weight:800;color:#e6edf3">'+c.icon+' '+cat+'</span>'
      +'<span style="font-size:12px;color:#76819c;margin-left:8px">'+c.n+' Spiele</span></div>'
      +'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
      +'<th>Liga</th><th style="text-align:right">Spiele</th><th style="text-align:right">Geld-Favorit trifft</th><th>Geld vs. Preis</th>'
      +'</tr></thead><tbody>'+c.rows.sort((a,b)=>b.moneyHitRate-a.moneyHitRate).map(row).join('')+'</tbody></table></div></div>';
  }).join('');

  const legend='<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:11.5px;color:#76819c;margin:2px 2px 6px">'
    +'<span>🟢 <b style="color:#3fb950">Geld schärfer</b> — der Masse folgen</span>'
    +'<span>⚪ <b style="color:#8b949e">gleichauf</b> — steckt schon im Preis</span>'
    +'<span>🔴 <b style="color:#f85149">Preis besser</b> — Masse faden</span></div>';
  const note='nur Spiele mit Volumen ≥ '+_pwUsd(b.minVolUsd||0)+' und Quote ≥ '+(b.minOdds||'—')+' (klare Favoriten fliegen raus) · '+(b.n||0)+' aufgelöste Spiele';
  return '<div class="pw-sec" style="margin-top:6px"><div class="pw-sec-head">'
    +'<span class="pw-kicker">🌐 Alle Poly-Ligen — trifft die Seite mit dem meisten Geld?</span>'
    +'<span class="pw-sec-note">'+note+'</span></div>'
    +'<div class="pw-sec-p" style="margin:2px 0 10px">Für jede Liga: <b>gewinnt die Seite, auf der am meisten Geld liegt</b> — und liegt das Geld damit <b>öfter richtig als der reine Preis</b>? Grün = ja, dem großen Geld folgen lohnt.</div>'
    +legend+highlight
    +(blocks||'<div class="pw-sec-p">Noch keine Liga mit genug aufgelösten Spielen (min. 5). Sammelt sich über die nächsten Tage.</div>')
    +'</div>';
}

// ── „Liegt das Geld richtig?" (19.07.2026, Lucas) ────────────────────────────
// Empirischer Test: gewinnt die Seite mit dem meisten Geld — und ist das Geld SCHÄRFER als der
// Preis (Brier) oder nur Rauschen, das der Preis eh enthält? Aus poly_money_accuracy.py.
// 25.07.2026 (Lucas: „können wir das Spiel anzeigen statt der IDs?"). Der Match-Key ist
// "homeId-awayId" (z.B. 2242-1603) — der teams-Map (aus groups[].teams) kennt die Namen. Auf
// „Heim-Team vs Auswärts-Team" auflösen; Flag ist bereits sicheres HTML, Name wird escaped.
// Fallback (unbekannte ID / anderes Key-Format): roher Key.
function _pwMatchLabel(key, teams){
  const s=String(key||''); const i=s.indexOf('-');
  if(i>0 && teams){
    const hid=s.slice(0,i), aid=s.slice(i+1), h=teams[hid], a=teams[aid];
    if(h||a){
      const nm=(t,id)=>t?((t.flag?t.flag+' ':'')+_pwEsc(t.name)):_pwEsc(id);
      return nm(h,hid)+' <span style="color:#6e7681">vs</span> '+nm(a,aid);
    }
  }
  return '<span class="pw-cm">'+_pwEsc(s)+'</span>';
}

// 25.07.2026 (Lucas: „ich will sehen was einzelne Wale setzen, alle Sportarten"). Sektion (c):
// die größten EINZELNEN Wallets über alle Märkte (aus poly_money_broad_close.json → whales je Markt).
function _pwGlobalWhales(live){
  const entries=(live?Object.values(live):[]).filter(m=>m&&Array.isArray(m.whales)&&m.whales.length);
  const cats=new Set(entries.map(m=>_pwSportCategory(m.league)));
  const all=[];
  for(const [k,m] of (live?Object.entries(live):[])){
    if(!m||!Array.isArray(m.whales)||!m.whales.length||!_pwSportPass(m.league)) continue;
    const match=Object.keys(m.shares||{}).join(' vs ');
    for(const wh of m.whales) if(wh&&wh.wallet) all.push({wallet:wh.wallet,side:wh.side,usd:Number(wh.usd)||0,key:k,league:m.league,match});
  }
  all.sort((a,b)=>b.usd-a.usd);
  const intro='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🐋 Was einzelne Wale setzen — alle Sportarten</span>'
    +'<span class="pw-sec-note">die größten Einzel-Wallets je Markt · auf welche Seite · wie viel · Klick → Wallet bzw. Markt auf Polymarket</span></div>'
    +_pwSportFilterBar(cats);
  if(!all.length) return intro+'<div class="pw-none">'+(_pwSportFilter==='all'
    ?'Noch keine Wale erfasst (füllt sich nah am Anpfiff über den Mac-Runner).'
    :'Keine '+_pwSportFilter+'-Wale gerade — Filter „Alle" zeigt wieder alles.')+'</div></section>';
  const body=all.slice(0,25).map(x=>{
    const wl='<a href="https://polymarket.com/profile/'+encodeURIComponent(x.wallet)+'" target="_blank" rel="noopener" class="pw-wl" title="Wallet auf Polymarket">'+_pwWallet(x.wallet)+'</a>';
    const mk='<a href="https://polymarket.com/event/'+encodeURIComponent(x.key)+'" target="_blank" rel="noopener" style="color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681" title="Markt öffnen ↗">'+_pwEsc(x.match)+' <span style="color:#a78bfa">↗</span></a>';
    return '<tr><td style="white-space:nowrap">'+_pwSportIcon(x.league)+' <span class="pw-mut" style="font-size:11px">'+_pwEsc((x.league||'').toUpperCase())+'</span></td>'
      +'<td>'+mk+'</td><td>'+wl+'</td>'
      +'<td class="pw-cm"><b style="color:#4cc2ff">'+_pwEsc(x.side)+'</b></td>'
      +'<td class="pw-cn" style="font-weight:800">'+_pwUsd(x.usd)+'</td></tr>';
  }).join('');
  return intro+'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    +'<th>Sport</th><th>Spiel</th><th>Wallet</th><th>setzt auf</th><th>Betrag</th>'
    +'</tr></thead><tbody>'+body+'</tbody></table></div></section>';
}

// 25.07.2026 (Lucas: „wo liegt Poly falsch vs Pinnacle, alle Sportarten"). Sektion (a): globale
// Edge aus poly_cross_sport.json (Poly-% vs de-viggte Pinnacle-%). Konvergenz = das Echtheits-
// Kriterium (Lücke schließt sich über Tage → echt; steht → Artefakt). Dieselbe Daten wie Poly-Radar.
const _PW_SPORT_ICON={soccer:'⚽',basketball:'🏀',americanfootball:'🏈',baseball:'⚾',icehockey:'🏒',
  mma:'🥊',boxing:'🥊',tennis:'🎾',cricket:'🏏',golf:'⛳',esports:'🎮'};
function _pwSportIcon(sport){const s=String(sport||'').toLowerCase();
  for(const k in _PW_SPORT_ICON) if(s.indexOf(k)>=0) return _PW_SPORT_ICON[k]; return '🎯';}
function _pwGlobalEdge(cs){
  const allDisc=(cs&&cs.discrepancies)?cs.discrepancies.slice():[];
  const cats=new Set(allDisc.map(d=>_pwSportCategory(d.sport)));
  const disc=allDisc.filter(d=>_pwSportPass(d.sport));
  const intro='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🎯 Wo Poly falscher liegt als Pinnacle — alle Sportarten</span>'
    +'<span class="pw-sec-note">Poly-% vs faire Pinnacle-% · Lücke = Kandidat · aber erst echt, wenn sie sich über Tage schließt (Konvergenz)</span></div>'
    +_pwSportFilterBar(cats);
  if(!disc.length){
    const seen=(cs&&cs.matched)||0;
    return intro+'<div class="pw-none">'+(seen>0
      ?'Aktuell keine Lücke ≥6pp — Poly & Pinnacle liegen über alle Sportarten eng beieinander (Normalfall auf liquiden Märkten).'
      :'Noch keine Cross-Sport-Daten (läuft am Mac-Runner, Poly ist EU-geoblockt).')+'</div></section>';
  }
  // konvergierende zuerst (echtes Signal), dann größte Lücke
  disc.sort((a,b)=>{const ca=a.convergePP==null?-9:a.convergePP,cb=b.convergePP==null?-9:b.convergePP;
    if((cb>0.5)!==(ca>0.5))return (cb>0.5?1:0)-(ca>0.5?1:0); return Math.abs(b.gapPP)-Math.abs(a.gapPP);});
  const body=disc.slice(0,25).map(d=>{
    const gapCol=Math.abs(d.gapPP)>=10?'#f85149':Math.abs(d.gapPP)>=7?'#e3b341':'#8b949e';
    const conv=d.convergePP;
    const cv=conv==null?'<span class="pw-mut" style="font-style:italic">neu</span>'
      :conv>0.5?'<span style="color:#3fb950;font-weight:700" title="Lücke schließt sich — echt">▼ '+conv.toFixed(1)+'pp</span>'
      :conv<-0.5?'<span style="color:#f85149" title="Lücke wächst — Artefakt-Verdacht">▲ '+Math.abs(conv).toFixed(1)+'pp</span>'
      :'<span class="pw-mut" title="Lücke steht — Artefakt-Verdacht">→ 0</span>';
    return '<tr>'
      +'<td style="white-space:nowrap">'+_pwSportIcon(d.sport)+'</td>'
      +'<td>'+_pwEsc(d.event||'')+' · <span class="pw-mut">'+_pwEsc(d.outcome||'')+'</span></td>'
      +'<td class="pw-cn" style="color:#a78bfa">'+(d.polyPP)+'%</td>'
      +'<td class="pw-cn" style="color:#5eead4">'+(d.pinnPP)+'%</td>'
      +'<td class="pw-cn" style="font-weight:800;color:'+gapCol+'">'+(d.gapPP>0?'+':'')+d.gapPP+'pp</td>'
      +'<td class="pw-cm" style="font-size:11px">'+_pwEsc(d.richtung||'')+'</td>'
      +'<td class="pw-cn">'+cv+'</td></tr>';
  }).join('');
  return intro+'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    +'<th>Sport</th><th>Spiel · Seite</th><th>Poly</th><th>fair</th><th>Lücke</th><th>Richtung</th><th title="Schließt sich die Lücke über die Tage? ▼ = ja (echt) · → = steht (Artefakt)">Konvergenz</th>'
    +'</tr></thead><tbody>'+body+'</tbody></table></div></section>';
}

// 25.07.2026 (Lucas: „ich will sehen wo viel Geld liegt, welche Seite, alle Sportarten inkl E-Sport
// — zum Folgen"). Sektion (b): die eingefrorenen KOMMENDEN Märkte aus poly_money_broad_close.json
// (resolved==null), nach Volumen sortiert. Team-Namen + Geld-Seite stehen direkt in `shares`.
function _pwMoneyLive(live){
  const all=(live?Object.entries(live):[]).map(([k,m])=>({k,m}))
    .filter(x=>x.m && x.m.resolved==null && x.m.shares && (x.m.totalUsd||0)>=5000);
  const cats=new Set(all.map(x=>_pwSportCategory(x.m.league)));
  const rows=all.filter(x=>_pwSportPass(x.m.league))
    .sort((a,b)=>(b.m.totalUsd||0)-(a.m.totalUsd||0)).slice(0,30);
  const intro='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">💰 Wo liegt das große Geld — alle Sportarten</span>'
    +'<span class="pw-sec-note">kommende Spiele nach Poly-Volumen · auf welche Seite hat die Masse gesetzt · zum Folgen</span></div>'
    +_pwSportFilterBar(cats);
  if(!rows.length) return intro+'<div class="pw-none">'+(_pwSportFilter==='all'
    ?'Gerade kein nennenswertes Geld auf kommenden Märkten (füllt sich nah am Anpfiff, läuft am Mac-Runner).'
    :'Keine kommenden '+_pwSportFilter+'-Märkte gerade — Filter „Alle" zeigt wieder alles.')+'</div></section>';
  const body=rows.map(({k,m})=>{
    const oc=Object.entries(m.shares||{}).map(([name,usd])=>({name,usd:Number(usd)||0}));
    const total=oc.reduce((s,o)=>s+o.usd,0)||1; oc.sort((a,b)=>b.usd-a.usd);
    const fav=oc[0], favPct=Math.round(fav.usd/total*100);
    const favPrice=(m.prices&&m.prices[fav.name]!=null)?Math.round(m.prices[fav.name]*100)+'¢':'—';
    // Spiel-Spalte klickbar → direkt auf den Polymarket-Markt (Key ist der Event-Slug). 25.07.2026 (Lucas).
    const matchTxt=oc.map(o=>_pwEsc(o.name)).join(' <span style="color:#6e7681">vs</span> ');
    const match=k?('<a href="https://polymarket.com/event/'+encodeURIComponent(k)+'" target="_blank" rel="noopener" '
      +'style="color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681" title="Auf Polymarket öffnen ↗">'+matchTxt+' <span style="color:#a78bfa">↗</span></a>'):matchTxt;
    const ic=_pwCatOf(m.league)[1], lg=(m.league||'').toUpperCase();
    const htk=m.hoursToKickoff!=null?(m.hoursToKickoff<0?'live':m.hoursToKickoff<1?'<1h':Math.round(m.hoursToKickoff)+'h'):'—';
    // Split-Balken (bis 3 Ausgänge)
    const cols=['#4cc2ff','#f5c518','#ff5d5d'];
    const seg=oc.slice(0,3).map((o,i)=>'<i style="display:inline-block;height:100%;width:'+Math.round(o.usd/total*100)+'%;background:'+cols[i]+'" title="'+_pwEsc(o.name)+' '+Math.round(o.usd/total*100)+'%"></i>').join('');
    return '<tr>'
      +'<td style="white-space:nowrap">'+ic+' <span class="pw-mut" style="font-size:11px">'+lg+'</span></td>'
      +'<td>'+match+'</td>'
      +'<td style="min-width:110px"><div style="height:9px;border-radius:5px;overflow:hidden;background:#161b22;display:flex">'+seg+'</div></td>'
      +'<td class="pw-cm" style="white-space:nowrap"><b style="color:#4cc2ff">'+_pwEsc(fav.name)+'</b> '+favPct+'% <span class="pw-mut">('+favPrice+')</span></td>'
      +'<td class="pw-cn pw-mut">'+_pwUsd(m.totalUsd)+'</td>'
      +'<td class="pw-cn pw-mut">'+htk+'</td></tr>';
  }).join('');
  return intro
    +'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    +'<th>Sport</th><th>Spiel</th><th>Geld-Split</th><th>Geld liegt auf</th><th>Volumen</th><th>Anpfiff</th>'
    +'</tr></thead><tbody>'+body+'</tbody></table></div></section>';
}

function _pwMoneyAccuracy(acc, teams){
  const a=acc||{};
  const intro='<div class="pw-sec-p" style="max-width:820px;margin:14px 0 18px">'
    +'Wir kennen bei jedem Spiel den <b>Preis</b> und die <b>Geld-Verteilung</b>. Die Frage: '
    +'<b>gewinnt die Seite, auf der am meisten Geld liegt</b> — und liegt das Geld damit <b>öfter richtig als der reine Preis</b>? '
    +'Wenn ja, weiß das große Geld mehr, als im Preis steht, und man folgt ihm. Wenn nicht, steckt es schon im Preis oder liegt daneben. '
    +'<i>Die Geld-Verteilung wird nah am Anpfiff eingefroren und nach dem Spiel gegen den Ausgang geprüft.</i></div>';

  if(!a.n){
    return intro+'<div class="pw-empty"><div class="pw-empty-ico">🎯</div><h2>Sammelt noch</h2>'
      +'<p>Die Geld-Verteilung wird nah am Anpfiff eingefroren und erst nach dem Spiel aufgelöst. '
      +'Das Urteil braucht ein paar Dutzend aufgelöste Märkte — es füllt sich über die kommenden Spieltage.</p></div>';
  }

  const V={geld_schaerfer:['🟢','#3fb950','Das Geld ist schärfer als der Preis','Das große Geld weiß mehr, als im Preis steht — es lohnt sich, ihm zu folgen.'],
           preis_besser:['🔴','#f85149','Der Preis ist besser als das Geld','Das Geld liegt schlechter als der Preis — dummes Geld, das man faden kann.'],
           gleichauf:['⚪','#8b949e','Geld ≈ Preis','Das Geld steckt schon im Preis — kein Zusatznutzen als Signal.']}[a.verdict]
        ||['⏳','#8b949e','Zu wenig Daten',''];
  const pct=v=>Math.round((v||0)*100)+'%';
  const kpi=(lbl,val,col,sub)=>'<div class="pw-kpi"><div class="pw-kpi-b">'
    +'<div class="pw-kpi-v" style="color:'+(col||PW_C.txt)+'">'+val+'</div>'
    +'<div class="pw-kpi-l">'+lbl+'</div>'+(sub?'<div class="pw-kpi-s">'+sub+'</div>':'')+'</div></div>';

  const d=a.disagree||{n:0,moneyWon:0,priceWon:0};
  const disagreeHtml=d.n?('<div class="pw-sec" style="margin-top:4px"><div class="pw-sec-head"><span class="pw-kicker">⚔️ Wenn Geld ≠ Preis</span>'
    +'<span class="pw-sec-note">wer gewinnt, wenn sie uneinig sind? (der reinste Test)</span></div>'
    +'<div style="display:flex;gap:24px;padding:4px 2px 8px;font-size:14px">'
    +'<div><b style="color:#a78bfa;font-size:22px">'+d.moneyWon+'</b> <span style="color:#8b949e">Geld gewann</span></div>'
    +'<div><b style="color:#5eead4;font-size:22px">'+d.priceWon+'</b> <span style="color:#8b949e">Preis gewann</span></div>'
    +'<div><b style="color:#8b949e;font-size:22px">'+(d.n-d.moneyWon-d.priceWon)+'</b> <span style="color:#8b949e">keiner</span></div>'
    +'</div></div>'):'';

  // Match-Tabelle
  const rows=(a.rows||[]).slice(0,25).map(r=>{
    const seite=s=>({home:'Heim',draw:'Remis',away:'Ausw.'})[s]||s;
    const mark=ok=>ok?'<span style="color:#3fb950">✓</span>':'<span style="color:#f85149">✗</span>';
    return '<tr><td>'+_pwMatchLabel(r.key,teams)+'</td>'
      +'<td>'+seite(r.moneyFav)+' '+mark(r.moneyOK)+'</td>'
      +'<td>'+seite(r.priceFav)+' '+mark(r.priceOK)+'</td>'
      +'<td class="pw-cm">'+seite(r.winner)+'</td>'
      +'<td class="pw-cn pw-mut">'+_pwUsd(r.totalUsd)+'</td></tr>';
  }).join('');

  return intro
    +'<div style="background:linear-gradient(145deg,'+V[1]+'14,transparent);border:1px solid '+V[1]+'44;border-radius:14px;padding:18px 20px;margin-bottom:16px">'
    +'<div style="font-size:20px;font-weight:800;color:'+V[1]+'">'+V[0]+' '+V[2]+'</div>'
    +'<div style="font-size:13px;color:#8b949e;margin-top:4px">'+V[3]+'  ·  <span style="color:#6e7681">'+a.n+' aufgelöste Märkte</span></div></div>'
    +'<div class="pw-kpis" style="margin-bottom:16px">'
    +kpi('Geld liegt richtig',pct(a.moneyHitRate),'#a78bfa','Seite mit dem meisten Geld gewinnt')
    +kpi('Preis liegt richtig',pct(a.priceHitRate),'#5eead4','Vergleich: der günstigste Preis gewinnt')
    +'</div>'
    +disagreeHtml
    +(rows?('<div class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">Aufgelöste Spiele</span>'
      +'<span class="pw-sec-note">worauf lag das Geld, was sagte der Preis, wer gewann — ✓ richtig, ✗ falsch</span></div>'
      +'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
      +'<th>Spiel</th><th>Geld auf</th><th>Preis-Favorit</th><th>Gewinner</th><th style="text-align:right">Volumen</th>'
      +'</tr></thead><tbody>'+rows+'</tbody></table></div></div>'):'');
}

// ── Deep-Link auf den Polymarket-Markt (19.07.2026) ──────────────────────────
// Prices tragen `slug`/`moreMktSlug` — bisher nie verlinkt. Ein modernes Dashboard springt.
function _pwSlugMap(prices){
  const m={}; const p=(prices&&prices.prices)||{};
  for(const [k,e] of Object.entries(p)) if(e&&e.slug) m[k]=e.slug;
  return m;
}
function _pwPolyLink(slug,label){
  if(!slug) return '';
  return '<a href="https://polymarket.com/event/'+encodeURIComponent(slug)+'" target="_blank" rel="noopener" '
    +'style="color:#a78bfa;text-decoration:none;font-size:11px" title="Auf Polymarket öffnen">'+(label||'↗')+'</a>';
}

// ── Smart-Money-Konzentration (19.07.2026, war KOMPLETT ungenutzt) ───────────
// Aus {ds}_poly_smartmoney.json: WO liegt das Geld (Split), WIE breit (Halter) und WIE konzentriert
// (topHolderShare). Das trennt „echter Konsens der Masse" von „ein Wal drückt den Markt".
function _pwSmartConcentration(smart,prices,teams){
  const matches=smart&&smart.matches?Object.entries(smart.matches):[];
  if(!matches.length) return '';
  const slugs=_pwSlugMap(prices);
  const OUT=[['home','#4cc2ff'],['draw','#f5c518'],['away','#ff5d5d']];
  // Nach Geld sortiert, nur Märkte mit echtem Volumen UND im Anpfiff-Fenster (wie das Edge-Board).
  // Weit-entfernte Spiele (Wochen draußen) haben zwar teils Geld, gehören aber nicht in die
  // Nah-am-Anpfiff-Sicht; ein echtes Früh-Whale-Signal bleibt im Whales-Tab sichtbar.
  const rows=matches
    .filter(([_k,m])=>(m.totalUsd||0)>=2000 && m.outcomes
      && (m.hoursToKickoff==null || (m.hoursToKickoff>=-3 && m.hoursToKickoff<=PW_EDGE_HORIZON_H)))
    .sort((a,b)=>(b[1].totalUsd||0)-(a[1].totalUsd||0))
    .slice(0,14).map(([key,m])=>{
      const oc=m.outcomes||{};
      // Geld-Split-Balken (share je Outcome)
      const seg=OUT.filter(([k])=>oc[k]&&oc[k].share>0).map(([k,c])=>
        '<i style="display:inline-block;height:100%;width:'+Math.round((oc[k].share||0)*100)+'%;background:'+c+'" title="'+k+' '+Math.round((oc[k].share||0)*100)+'%"></i>').join('');
      // Konzentration = höchste topHolderShare über die Outcomes; Breite = Summe Halter
      const conc=Math.max(...OUT.map(([k])=>(oc[k]&&oc[k].topHolderShare)||0));
      const holders=OUT.reduce((s,[k])=>s+((oc[k]&&oc[k].holders)||0),0);
      const flow=OUT.reduce((s,[k])=>s+((oc[k]&&oc[k].netFlowUsd)||0),0);
      const concBadge= conc>=0.7
        ? '<span style="color:#f85149;font-weight:700" title="Wenige große Wallets dominieren — weiches Signal, evtl. ein Wal">⚠️ '+Math.round(conc*100)+'%</span>'
        : conc>=0.5 ? '<span style="color:#e3b341">'+Math.round(conc*100)+'%</span>'
        : '<span style="color:#3fb950" title="Breite Verteilung — echter Massen-Konsens">'+Math.round(conc*100)+'%</span>';
      // Namen bevorzugt aus smartmoney (home/away), sonst aus der Teams-Map, sonst der Key.
      let mn=(m.home&&m.away)?(m.home+' – '+m.away):key;
      if(mn===key && teams){const [a,b]=String(key).split('-');
        if(teams[a]&&teams[b]) mn=(teams[a].name||a)+' – '+(teams[b].name||b);}
      const htk=(m.hoursToKickoff!=null)?(m.hoursToKickoff<0?'live':m.hoursToKickoff.toFixed(1)+'h'):'—';
      return '<tr>'
        +'<td class="pw-cm">'+_pwEsc(mn)+' '+_pwPolyLink(slugs[key])+'</td>'
        +'<td style="min-width:120px"><div style="height:10px;border-radius:5px;overflow:hidden;background:#161b22;display:flex">'+seg+'</div></td>'
        +'<td class="pw-cn pw-mut">'+_pwUsd(m.totalUsd)+'</td>'
        +'<td class="pw-cn">'+holders+'</td>'
        +'<td class="pw-cn">'+concBadge+'</td>'
        +'<td class="pw-cn" style="color:'+(flow>=0?'#3fb950':'#f85149')+'">'+(flow>=0?'+':'−')+_pwUsd(Math.abs(flow)).slice(1)+'</td>'
        +'<td class="pw-cn pw-mut">'+htk+'</td></tr>';
    }).join('');
  if(!rows) return '';
  return '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">💡 Smart-Money-Konzentration</span>'
    +'<span class="pw-sec-note">wo liegt das Geld · wie breit (Halter) · wie konzentriert (Wale) · Fluss zum Anpfiff</span></div>'
    +'<div class="pw-sec-p" style="margin:2px 0 10px">Der <b>Split-Balken</b> zeigt, auf welche Seite das Geld setzt. '
    +'<b>Konzentration</b>: 🟢 breit = echter Massen-Konsens · 🔴 hoch = wenige Wale drücken den Markt (weiches Signal). '
    +'<b>Fluss</b>: grün = Geld läuft rein, rot = raus.</div>'
    +'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    +'<th>Spiel</th><th>Geld liegt auf</th><th>Volumen</th><th title="Anzahl Wallets — viele = breiter Konsens">Wallets</th>'
    +'<th title="Anteil der größten Wallets: 🟢 breit gestreut = Massen-Konsens · 🔴 hoch = wenige Wale drücken">Wer drückt</th>'
    +'<th title="Netto-Geldfluss zum Anpfiff: grün rein, rot raus">Fluss</th><th>Anpfiff</th>'
    +'</tr></thead><tbody>'+rows+'</tbody></table></div></section>';
}

// ── Edge-Board ──────────────────────────────────────────────────────────────
function _pwEdgeBoard(edges,teams,wallets,hist){
  const shown=edges.filter(e=>e.net>=PW_NOISE);
  let h='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🎯 Wo Poly günstiger ist als die faire Quote</span>'
    +'<span class="pw-sec-note">Die pp-Zahl = wie viel Vorteil du hättest, wenn du diese Seite auf Poly nimmst statt zur fairen Pinnacle-Quote (Spread-Abzug '+PW_SPREAD_HAIRCUT+'pp schon drin). Nur Spiele der nächsten '+Math.round(PW_EDGE_HORIZON_H/24)+' Tage · Kurve = Pinnacle-Verlauf · Klick → Details</span></div>';
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
  } else h+='<div class="pw-none-sm">'+_pwWhyNoWhales(wallets)+'</div>';
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
  let h='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">📟 Jüngste große Trades</span>'
    +'<span class="pw-sec-note">Wer hat gerade groß gekauft/verkauft — frisches Signal oder schon durchgelaufen?</span></div><div class="pw-tape">';
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
  let h='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🏦 Größte Wallets</span>'
    +'<span class="pw-sec-note">Wer hat am meisten drin — reine Größe, noch ohne Trefferbilanz (groß ≠ treffsicher)</span></div><div class="pw-lb">';
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
  #polyWalletsPanel .pw-ds{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:18px}
  #polyWalletsPanel .pw-ds-btn{display:flex;align-items:center;gap:6px;background:#0f1626;border:1px solid rgba(255,255,255,.08);color:#8a95ad;font-size:13px;font-weight:700;padding:8px 14px;border-radius:10px;cursor:pointer;transition:all .15s;font-family:inherit}
  #polyWalletsPanel .pw-ds-btn:hover{border-color:rgba(94,234,212,.4);color:#cdd6ea}
  #polyWalletsPanel .pw-ds-btn.pw-ds-on{background:linear-gradient(145deg,#164e46,#0f2f2b);border-color:#5eead4;color:#5eead4}
  #polyWalletsPanel .pw-ds-btn span{font-size:15px}
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
  /* 19.07.2026 — kompakte Tabelle für die neuen Poly-Edge-Sektionen */
  #polyWalletsPanel .pw-sec-p{color:#8b98b5;font-size:12.5px;line-height:1.6;margin:2px 0 12px}
  #polyWalletsPanel .pw-sec-p i{color:#76819c}
  #polyWalletsPanel .pw-tw{overflow-x:auto}
  #polyWalletsPanel .pw-tbl{width:100%;border-collapse:collapse;font-size:13px}
  #polyWalletsPanel .pw-tbl th{text-align:left;color:#76819c;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px;padding:6px 10px;border-bottom:1px solid rgba(255,255,255,.08)}
  #polyWalletsPanel .pw-tbl td{padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.04)}
  #polyWalletsPanel .pw-cm{color:#e6edf3;font-weight:600}
  #polyWalletsPanel .pw-cn{text-align:right;font-variant-numeric:tabular-nums}
  #polyWalletsPanel .pw-mut{color:#76819c}
  #polyWalletsPanel .pw-pos{color:#3fb950}
  #polyWalletsPanel .pw-chip{background:rgba(94,234,212,.1);color:#5eead4;font-size:11px;font-weight:700;padding:2px 8px;border-radius:6px;white-space:nowrap}
  #polyWalletsPanel .pw-wl{color:#a78bfa;text-decoration:none;font-family:ui-monospace,monospace;font-size:12px}
  #polyWalletsPanel .pw-wl:hover{text-decoration:underline}
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
