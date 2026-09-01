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
var _pwCache = null;   // 21.08.2026: var (nicht let) -> testbar
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
// 29.08.2026 (Lucas: „weder in Uebersicht noch im Polymarket-Wallets") — die Uebersicht kam nach
// dem Deploy zurueck, die Wallets nicht. Grund: main-dashboard.js und betfair-radar.js holen ihre
// JSONs seit jeher PRIMAER von raw.githubusercontent.com/main, diese Datei holte relativ — also
// aus dem Pages-Snapshot, der am traegen Deploy haengt (real ~8 Republishes/Tag). Jetzt dieselbe
// Reihenfolge wie ueberall: raw/main zuerst (commit-frisch), Snapshot als Rueckfall.
const _PW_RAW_BASE = 'https://raw.githubusercontent.com/blummabet/Betting-Dashboard/main';

function _pwJson(u, bust){
  if(!u) return Promise.resolve(null);
  const b = bust || ('?t=' + Date.now());
  return fetch(_PW_RAW_BASE + '/' + u + b, {cache:'no-store'})
    .then(r => { if(r.ok) return r.json(); throw 0; })
    .catch(() => fetch(u + b, {cache:'no-store'})
      .then(r => r.ok ? r.json() : null)
      .catch(() => null));
}

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
// 25.07.2026 (Lucas ③): 🔥 Heute wetten ist der erste, prominente Tab (der Entscheidungs-Screen),
// aber die LANDUNG bleibt vorerst auf 💰 Großes Geld (hat heute Inhalt) — die Shortlist ist leer,
// bis ① Steam + ② Sharp-Wallets Daten gesammelt haben. Dann → 'bet' als Default.
let _pwView='money';
function _pwSetView(v){ if(v===_pwView)return; _pwView=v; _pwDestroyCharts(); _pwRender(); }
if(typeof window!=='undefined') window._pwSetView=_pwSetView;
function _pwViewTabs(){
  const b=(id,label)=>'<button class="pw-ds-btn'+(id===_pwView?' pw-ds-on':'')
    +'" onclick="_pwSetView(\''+id+'\')">'+label+'</button>';
  // 19.07.2026 (Lucas: „besser aufteilen") — 4 Unter-Reiter statt 9 gestapelter Sektionen.
  // Reihenfolge 25.07.2026: globales „Großes Geld" (immer Content+Filter) zuerst → Landing-Tab.
  return '<div class="pw-ds" style="margin-top:-6px">'
    +b('terminal','🖥️ Terminal')+b('bet','🔥 Heute wetten')+b('track','📊 Track-Record')+b('xsport','🎯 Poly-Radar')+b('money','💰 Großes Geld')+b('live','⚡ LIVE')+b('move','📈 Bewegung')+b('new','🆕 Neu')+b('edge','🎯 Chancen')+b('whales','🐋 Whales')+b('pinnpoly','📊 Pinni×Poly')
    +'</div>';
}

// 25.07.2026 (Lucas: „alle Zahlen verwirrend, keine Ahnung was ich damit mache"). Pro Unter-Reiter
// EINE Klartext-Box: was zeige ich, und — wichtiger — was tust DU damit. Kein Jargon, ein Satz je.
const _PW_VIEW_INTRO = {
  terminal: ['🖥️ Terminal — alle handelbaren Kanten auf einem Screen',
    'Dieselben Plays und Conviction wie „🔥 Heute wetten" (identische Engine) — nur dicht, nach Conviction und nach der historischen Bilanz der Stufe geordnet. CLV-Bucket zeigt je Conviction-Stufe, wie sie in deinem Paper-Track wirklich performt.',
    'Von oben abarbeiten: hohe Conviction mit grünem CLV-Bucket zuerst. Gemutete Stufen (historisch -EV, z.B. Konv5) stehen ausgegraut unten — Toggle blendet sie ganz aus. Nichts gelöscht, nichts am Algo geändert.'],
  live: ['⚡ LIVE — Geld & Wallets auf laufenden Spielen',
    'Nur In-Play-Märkte (Esport/Tennis/…). Wo fließt GERADE Geld rein, welche Whales steigen JETZT ein — markiert die, die vor Anpfiff nicht im Top-4 waren (live rein).',
    'Mitschauen, was daherkommt: großer frischer Zufluss + eine live einsteigende Wallet ist das Signal, das man vor Anpfiff nicht sieht. Noch roh (Stufe 2 v1) — kein Auto-Signal, erstmal beobachten.'],
  xsport: ['🎯 Poly-Radar — Poly vs Sharp: wo Polymarket messbar neben der scharfen Pinnacle liegt (alle Sportarten)',
    'Das einzige echte Preis-Signal hier: Poly-% gegen die faire Pinnacle-% über ALLE Sportarten. Eine Lücke ist ein Kandidat, kein Auftrag.',
    'Erst wenn sich die Lücke über die Tage zur Pinnacle SCHLIESST (Konvergenz ▼), war sie echt — kein Settlement-Artefakt. Sonst Finger weg.'],
  edge:  ['🎯 Chancen — wo Polymarket „falscher\" liegt als die scharfe Pinnacle',
    'Kandidaten zum Dagegenhalten: je größer die Abweichung, desto interessanter. Aber Poly und Pinnacle sind meist im Einklang — leere/kleine Liste ist der Normalfall, kein Fehler.',
    'Große Lücke, die die Whales BESTÄTIGEN (nicht dagegen stehen) → beobachten. Nichts blind traden — erst wenn sich die Lücke über Tage zur Pinnacle schließt, war sie echt.'],
  smart: ['💡 Smart-Money — wo das GROSSE Geld liegt und wie konzentriert',
    'Zeigt, auf welche Seite die dicken Wallets gesetzt haben und wie einig sie sich sind. Das ist KEIN eigenes Wett-Signal.',
    'Nutze es als Bestätigung oder Veto für einen bestehenden Pick: steht das große Geld dahinter → Rückenwind; steht es dagegen → vorsichtig sein.'],
  whales:['🐋 Whales — die einzelnen großen Wallets',
    'Ganz oben die 🥇 Rangliste der schärfsten Wallets nach Track-Record (Kombi-Score aus CLV + Treffer); darunter: wer ist zu welchem Preis eingestiegen, jüngste große Trades, Trefferbilanz je Wallet. „Groß\" heißt nicht automatisch „treffsicher\".',
    'Nur Wallets mit bewiesener Trefferquote als Rückenwind nehmen; die bloß-großen ohne Track-Record ignorieren.'],
  bet: ['🔥 Heute wetten — die klarsten Gelegenheiten, ein Screen',
    'Bündelt alle Signale zu einem Verdikt je Markt: BET (mit dem Geld) oder FADE (dagegen), Conviction 0–10. Zeigt nur echte Signale — bloße Favoriten ohne Edge fehlen bewusst.',
    'Von oben nach unten abarbeiten: hohe Conviction zuerst prüfen, „Warum" lesen, selbst entscheiden. Leere Liste = heute keine klare Kante → nicht wetten.'],
  track: ['📊 Track-Record — wie gut „Heute wetten" WIRKLICH performt (Paper)',
    'Jeder Global-Scan schreibt die exakten Shortlist-Empfehlungen mit (fixer Einsatz $10 zum Einstiegspreis) und rechnet bei Auflösung ab: Trefferquote, ROI, Ø CLV. Zwei Sichten: bespielbare Sportarten und die harten Public-Kandidaten (gesperrte laufen als reine Beobachtung mit). Es wird NICHTS gesetzt — reines Mitschreiben.',
    'Auf die Conviction-Tabelle schauen: erst wenn eine Stufe über genug Spiele klar im Plus ist (ROI + CLV), lohnt das echte Nachspielen (Auto-Bet) — vorher nur beobachten.'],
  new: ['🆕 Neu — was sich seit deinem letzten Blick getan hat',
    'Aktivitäts-Feed über alle Sportarten: neue große Whale-Einstiege (letzte 24h) und Märkte, in denen der Favorit gekippt ist. Der schnelle „was ist passiert"-Check.',
    'Ein frischer 🔥-Einstieg oder ein Favoriten-Flip ist ein Anstoß zum Hinschauen — kein Auto-Bet. Prüf den Markt in 🔥 Heute wetten oder 📈 Bewegung nach.'],
  move: ['📈 Bewegung — was sich GERADE auf Poly bewegt (Steam vs Reversal)',
    'Nicht wo Geld LIEGT, sondern wohin der Poly-Preis zieht: der stärkste Move je Markt über die letzten Stunden, alle Sportarten. Steam ▲ = zieht weiter, dreht ▼ = kehrt um.',
    'Einem beschleunigenden Steam auf der scharfen Seite folgen (dein Steam-Modell); bei einem Reversal vorsichtig sein — das Geld korrigiert. Füllt sich über die nächsten Runner-Läufe.'],
  money: ['💰 Das große Geld — alle Sportarten inkl. E-Sport',
    'Oben: auf welche Seite die Masse bei KOMMENDEN Spielen gesetzt hat (zum Folgen). Unten: der Rückblick — hatte die Masse bei aufgelösten Spielen recht?',
    'Kommenden Märkten mit klarer Geld-Mehrheit folgen — aber nur dort, wo der Rückblick unten 🟢 „Geld schärfer\" zeigt. Wo 🔴 „Preis besser\" steht, liegt die Masse daneben → faden.'],
};
// 25.07.2026 (Lucas: „Ligen oben weg, statt dessen ein Filter je Tab damit ich besser suchen kann").
// Globaler Sport-Filter über alle Sektionen (a/b/d). Kategorie robust aus Liga-Label ODER Sport-Key.
let _pwSportFilter='all';
function _pwSetSportFilter(cat){ _pwSportFilter=cat; _pwRender(); }
if(typeof window!=='undefined') window._pwSetSportFilter=_pwSetSportFilter;
function _pwSportCategory(s, sport){
  // 16.08.2026 (Lucas): gestempelter Sport aus dem Capture (poly_money_broad) hat Vorrang — fängt
  // abgekürzte Bewerbe (ERE/BEL1/RUS/AZE1/CLF …), die der String-Rateversuch nie erkennt.
  if(sport && _PW_CAT_ICON[sport]) return sport;
  const x=String(s||'').toLowerCase();
  // spezifische Sportarten ZUERST (sonst klauen breite Fußball-Begriffe wie „championship" sie)
  if(/esport|cs2|csgo|\blol\b|dota|valorant/.test(x)) return 'E-Sport';
  if(/basketball|nba|nfl|americanfootball|baseball|mlb|icehockey|hockey|nhl|wnba|ncaa/.test(x)) return 'US-Sport';
  if(/tennis|wta|atp/.test(x)) return 'Tennis';
  if(/mma|ufc|boxing|box|kampf/.test(x)) return 'Kampfsport';
  if(/golf/.test(x)) return 'Golf';
  if(/f1|formula|motor|nascar/.test(x)) return 'Motorsport';
  if(/cricket/.test(x)) return 'Cricket';
  // Fußball breit: Namen + Liga-Muster (16.08.2026 Lucas: Eredivisie/Allsvenskan/EFL-Championship/… gefangen)
  if(/soccer|football|fussball|fußball|\bepl\b|premier|\bucl\b|\buel\b|uecl|uefa|champions|conmebol|concacaf|copa|coupe|\bdfb\b|\befl\b|conference|europa|libertad|sudameri|\bmls\b|liga|ligue|serie|bundesliga|eredivisie|allsven|superett|elitese|ekstrakla|veikkau|primeira|championship|super-?lig|pro-?league|\blal\b/.test(x)) return 'Fußball';
  return 'Sonstige';
}
const _PW_CAT_ICON={'Fußball':'⚽','US-Sport':'🏀','E-Sport':'🎮','Tennis':'🎾','Kampfsport':'🥊','Golf':'⛳','Motorsport':'🏎️','Cricket':'🏏','Sonstige':'🎯'};
// 24.08.2026 (Lucas: „sollen wir die dann ganz rausnehmen? was wenn sie besser werden?").
// Sportarten, auf die NICHT gesetzt und die NICHT oeffentlich promotet werden. Gemessen am
// Papier-Depot ueber 500 abgerechnete Plays: MLB n=72, ROI −28%, 90%-Intervall komplett unter
// null, Ø CLV −1,62pp — das ist Signal, kein Pech. NFL (n=6) und UFC (n=7) sind statistisch
// nichts, dort ist die Sperre eine Vorsichtsentscheidung (kein Modell, duenne Maerkte).
// NBA hat null Plays. BEWUSST NICHT aus dem Scan/Papier-Depot entfernt: das Mitschreiben ist
// gratis und die EINZIGE Art, je zu merken, dass eine Sportart dreht (Wiedereintritt ueber CLV,
// siehe poly_shortlist_track.reentry_status).
const PW_BLOCKED_BET_CATS=['US-Sport','Kampfsport'];
try{ window.PW_BLOCKED_BET_CATS=PW_BLOCKED_BET_CATS; }catch(_e){}   // eine Quelle fuer Emitter + Betting-Tab
function _pwBetBlocked(r){ return PW_BLOCKED_BET_CATS.indexOf(_pwSportCategory(r&&r.league,r&&r.sport))>=0; }
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
function _pwSportPass(s, sport){ return _pwSportFilter==='all' || _pwSportCategory(s, sport)===_pwSportFilter; }
// 25.07.2026 (Lucas: „Filter nur beim letzten Tab"): Kategorien aus ALLEN globalen Quellen
// (kommendes Geld + Cross-Sport-Edge) vereinen → EINE Filterleiste oben, auf jedem Unter-Reiter.
function _pwGlobalCats(){
  const cats=new Set();
  const live=_pwCache&&_pwCache.broadLive;
  if(live) for(const m of Object.values(live)) if(m&&m.resolved==null&&m.league) cats.add(_pwSportCategory(m.league));
  const cs=_pwCache&&_pwCache.crossSport;
  if(cs&&Array.isArray(cs.discrepancies)) for(const d of cs.discrepancies) if(d&&d.sport) cats.add(_pwSportCategory(d.sport));
  return cats;
}

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
  const jf=(url)=>url?_pwJson(url,b):Promise.resolve(null);
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
    jf('poly_money_broad_history.json'),// 25.07.2026 (Lucas ① Momentum): globale Poly-Preis-Zeitreihe je Markt
    jf('poly_wallet_track.json'),       // 25.07.2026 (Lucas ② Sharp): CLV/Treffer je Wallet (Einstieg→Close)
    jf('poly_shortlist_track.json'),    // 02.08.2026 (Lucas): Paper-Track-Record der „Heute wetten"-Plays
    jf('poly_money_broad_live.json'),        // 11.08.2026 (Lucas Stufe 2): laufende Maerkte (Live-Erfassung, alle ~5 Min)
    jf('poly_money_broad_live_history.json'),
    jf('poly_live_signal_track.json'),       // 12.08.2026 (Lucas): Live-Signal Forward-CLV Track-Record
    jf('money_map.json'),                    // 21.08.2026 (Lucas): Betfair-Geld je Spiel → Gegencheck im Kanten-Scorer
  ]).then(([wm,prices,wallets,hist,coherence,settlement,ledger,moneyAcc,moneyBroad,smart,broadLive,crossSport,broadHist,walletTrack,shortlistTrack,broadLiveNow,broadLiveHist,liveSigTrack,moneyMap])=>{
    _pwCache={wm,prices,wallets,hist,coherence,settlement,ledger,moneyAcc,moneyBroad,smart,broadLive,crossSport,broadHist,walletTrack,shortlistTrack,broadLiveNow,broadLiveHist,liveSigTrack,moneyMap};
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

// 28.07.2026 (Lucas: „Boyer/Tomic steht IMMER noch da"): hoursToKickoff in der Broad-Close-Datei ist
// auf den Freeze-Zeitpunkt (capturedAt) eingefroren. Steht der Runner (Spiel gelaufen/Walkover, Markt
// nie resolved), bleibt htk für immer bei z.B. 0.97 → das Spiel zeigt ewig „<1h" und feuert weiter
// Steam-Verdikte in „Heute wetten" / „Chancen" / „Großes Geld". Echten Rest bis Anpfiff aus capturedAt
// rekonstruieren — dieselbe Idee wie der Momentum-Filter (ts+htk), nur für die Close-Märkte.
function _pwRealHtk(m){
  if(!m||m.hoursToKickoff==null) return null;
  const cap=m.capturedAt?Date.parse(m.capturedAt):NaN;
  if(isNaN(cap)) return m.hoursToKickoff;   // kein Freeze-Stempel → roher Wert (best effort)
  return m.hoursToKickoff - (Date.now()-cap)/3.6e6;
}
const PW_STALE_AFTER_KO_H = 4;   // Default (eSport/Tennis/Cricket: lange Serien laufen legitim 3-4h)
// 14.08.2026 (Lucas): Fussball ist nach ~2h durch — nicht 4h als "live" haengen lassen. Poly loest
// obskure Ligen (China/Japan Unterhaus) spaet auf, der Markt bleibt offen -> der Scan faengt das
// fertige Spiel weiter als live ein. Sportabhaengiger Cutoff loest genau das, ohne den eSport-Live-
// Tab zu beschneiden.
const PW_STALE_AFTER_KO_H_FOOTBALL = 2.5;
function _pwStaleCutoff(m){ return _pwSportCategory(m&&m.league, m&&m.sport)==='Fußball' ? PW_STALE_AFTER_KO_H_FOOTBALL : PW_STALE_AFTER_KO_H; }
function _pwKoStale(m){ const r=_pwRealHtk(m); return r!=null && r < -_pwStaleCutoff(m); }
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
  const panel=document.getElementById('polyWalletsPanel'); if(!panel)return;
  if(_pwView==='pinnpoly'){   // 04.08.2026 (Lucas): Pinnacle×Poly als Sub-Tab der Wallets
    _pwDestroyCharts();
    panel.innerHTML=_pwViewTabs()+'<div id="pinnPolyPanel" style="margin-top:12px"></div>';
    if(typeof window.initPinnPoly==='function') window.initPinnPoly();
    return;
  }
  if(!_pwCache)return;
  _pwDestroyCharts();
  const {wm,prices,wallets,hist,coherence,settlement,ledger,moneyAcc,moneyBroad,smart}=_pwCache;
  const teams=_pwTeamsMap(wm), oddsMap=_pwOddsMap(wm);
  const edges=_pwBuildEdges(prices,oddsMap);
  const hasPoly=wallets&&((wallets.topPositionsAll||[]).length||(wallets.matches&&Object.keys(wallets.matches).length));
  // 25.07.2026 (Lucas: „ich seh a und c gar nicht"): a (Edge) + c (Wale) sind GLOBAL — sie dürfen
  // NICHT vom datensatz-eigenen Poly-Bestand abhängen. Gibt es globale Daten, wird gerendert.
  const hasGlobal=((_pwCache.crossSport&&(_pwCache.crossSport.discrepancies||[]).length)
    ||(_pwCache.broadLive&&Object.keys(_pwCache.broadLive).length)
    ||(_pwCache.moneyBroad&&_pwCache.moneyBroad.n));
  const f=_pwFiles();
  // 25.07.2026 (Lucas: „die MLS-Boards sollen für das greifen, was im Filter eingestellt ist"): das
  // datensatz-eigene Detail (MLS = Fußball) erscheint NUR, wenn der Sport-Filter auf dessen Kategorie
  // steht. Default „Alle" bleibt damit REIN GLOBAL — kein Random-MLS mehr in den Tabs.
  const showDs=_pwSportFilter===(f.noAnchor?'E-Sport':'Fußball');

  // 19.07.2026 (Lucas) — eigener Sub-View „Liegt das Geld richtig?" neben dem Edge-Board.
  if(_pwView==='terminal'){
    panel.innerHTML=_pwViewTabs()+_pwSportFilterBar(_pwGlobalCats())+_pwViewIntro('terminal')+_pwTerminal();
    return;
  }
  if(_pwView==='money'){
    // (b) Wo liegt das große Geld (kommend, alle Sportarten) ZUERST, dann (d) Rückblick „liegt es richtig".
    // 25.07.2026 (Lucas: „Liga-Umschalter oben gehört weg"): der Wallets-Tab ist global über alle
    // Sportarten — kein Datensatz-Selektor mehr. (Sport-Filter je Sektion kommt als Nächstes.)
    panel.innerHTML=_pwViewTabs()+_pwSportFilterBar(_pwGlobalCats())+_pwViewIntro('money')
      +_pwOverNorm(_pwCache.broadLive,_pwCache.broadHist)
      +_pwMoneyLive(_pwCache.broadLive)+_pwMoneyBroad(moneyBroad)
      +(showDs?_pwMoneyAccuracy(moneyAcc,teams):'');   // MLS-Rückblick nur unter ⚽ Fußball
    return;
  }
  if(_pwView==='live'){
    panel.innerHTML=_pwViewTabs()+_pwSportFilterBar(_pwGlobalCats())+_pwViewIntro('live')+_pwLiveWhales();
    return;
  }
  if(_pwView==='move'){
    // ① Momentum (25.07.2026): was bewegt sich GERADE — globale Poly-Preis-Zeitreihe.
    panel.innerHTML=_pwViewTabs()+_pwSportFilterBar(_pwGlobalCats())+_pwViewIntro('move')
      +_pwMomentum(_pwCache.broadHist);
    return;
  }
  if(_pwView==='bet'){
    // ③ Heute-wetten-Shortlist (25.07.2026): alle Signale → ein Verdikt je Markt.
    panel.innerHTML=_pwViewTabs()+_pwSportFilterBar(_pwGlobalCats())+_pwViewIntro('bet')
      +_pwShortlist(_pwCache.broadLive);
    return;
  }
  if(_pwView==='track'){
    // 📊 Paper-Track-Record der Shortlist (02.08.2026, Lucas): sehen, ob „Heute wetten" performt.
    panel.innerHTML=_pwViewTabs()+_pwViewIntro('track')+_pwTrackRecord(_pwCache.shortlistTrack)+_pwLiveSignalTrack(_pwCache.liveSigTrack);
    return;
  }
  if(_pwView==='xsport'){
    // ⚖️ Poly vs Sharp (28.07.2026, Lucas: eigener Tab): die globale Cross-Sport-Edge Poly
    // vs de-viggte Pinnacle — das einzige echte Preis-Signal. Konvergenz = Echtheits-Gate.
    panel.innerHTML=_pwViewTabs()+_pwSportFilterBar(_pwGlobalCats())+_pwViewIntro('xsport')
      +_pwGlobalEdge(_pwCache.crossSport);
    return;
  }
  if(_pwView==='new'){
    // 🆕 Was-ist-neu-Feed (25.07.2026): neue Einstiege + Favoriten-Flips aus akkumulierten Daten.
    panel.innerHTML=_pwViewTabs()+_pwSportFilterBar(_pwGlobalCats())+_pwViewIntro('new')
      +_pwWhatsNew();
    return;
  }
  if(!hasPoly&&!edges.length&&!hasGlobal){
    panel.innerHTML=_pwViewTabs()
      +'<div class="pw-empty"><div class="pw-empty-ico">🐋</div><h2>Polymarket-Intelligence</h2>'
      +'<p>Noch keine Polymarket-Daten — sobald der Mac-Runner die globalen Dateien '
      +'(<code>poly_money_broad</code>, <code>poly_cross_sport</code>) befüllt, erscheinen hier Edge, Geld & Wale über alle Sportarten.</p></div>';
    return;
  }
  const upd=wallets&&wallets.updatedAt?_pwAgo(wallets.updatedAt):'—';
  const noAnchor=!!f.noAnchor;   // E-Sport: kein scharfer Pinnacle-Anker → Poly-only-Sicht

  const head='<div class="pw-head"><div><h1>'+(noAnchor?'🎮 Polymarket <span class="pw-accent">E-Sport</span> — Smart-Money'
      :'🐋 Polymarket <span class="pw-accent">Edge</span> & Smart-Money')+'</h1>'
    +'<p class="pw-sub">'+(noAnchor
      ? 'E-Sport hat keinen scharfen Buchmacher-Anker — deshalb <b>keine Edge-vs-Pinnacle-Ansicht</b>. Stattdessen die reine Poly-Sicht: <b>wo liegt das Geld, wie konzentriert, welche Wale, und wo widerspricht sich Poly selbst</b> (Arbitrage).'
      : 'Wo Polymarket vs. dem scharfen Pinnacle-Anker fehlbepreist ist — bestätigt oder gevetot vom großen Geld. <b>Die Edge ist das Signal, die Whales sind das Veto.</b>')+'</p></div>'
    +'<div class="pw-stamp">🌐 Alle Sportarten · Stand '+upd+'<br><span>Beträge geschätzt (Anteile × Preis)</span></div></div>';   // 09.08.2026 (Lucas): NICHT das Datensatz-Flag (🇺🇸 MLS) — Whale/Geld-Sicht ist global über alle Sportarten, der Datensatz betrifft nur den Pinnacle-Anker der Edge-Sektion

  // 19.07.2026 (Lucas: „besser aufteilen") — Sektionen auf Unter-Reiter verteilt, statt alle 9
  // untereinander. Jede Ansicht zeigt nur ihr Thema → kurze Scroll-Achse, klare Trennung.
  let h=_pwViewTabs()+_pwSportFilterBar(_pwGlobalCats())+_pwViewIntro(_pwView)+head+_pwKpiBand();
  let drawScatter=false;
  // 25.07.2026 (Lucas): Datensatz-Boards (MLS) NUR wenn der Filter auf ⚽ Fußball steht — sonst rein global.
  if(_pwView==='whales'){
    // 🐋 Whales: Schärfste-Rangliste (Track-Record) ZUERST, dann größte nach Einsatz, dann Einzel-Wale.
    h+=_pwSharpRanking();
    h+=_pwGlobalWhaleLeaderboard(_pwCache.broadLive);
    h+=_pwGlobalWhales(_pwCache.broadLive);
    if(showDs&&hasPoly){
      // Datensatz-Detail (MLS = ⚽ Fußball): Konzentration, Einstiegsqualität, jüngste Trades.
      // 26.07.2026 (Lucas: „aufräumen"): Kinder zuerst sammeln — Divider nur, wenn wirklich etwas
      // darunter steht (sonst verwaiste Überschrift ohne Inhalt). Respektiert „keine leeren Kästen".
      let _ds='';
      _ds+=_pwSmartConcentration(smart,prices,teams);
      _ds+=_pwWhaleEntryQuality(ledger);
      _ds+=_pwFlowTape(wallets,teams);
      _ds+=_pwExitWatch(wallets,teams);
      if(_ds) h+=_pwDsDivider(f,'Wale & Smart-Money in deinem aktiven Bewerb')+_ds;
    }
  }else{
    // 🎯 Chancen: Deep-Detail des aktiven Bewerbs (Settlement, Kohärenz, Pinnacle-Edges). Die
    // GLOBALE Cross-Sport-Edge (Poly vs Pinnacle) hat seit 28.07.2026 den eigenen Tab ⚖️ Poly vs Sharp.
    let _ds='';
    if(showDs&&hasPoly){
      _ds+=_pwSettlementBoard(settlement,teams);
      _ds+=_pwCoherenceBoard(coherence);
      if(!noAnchor){
        const _sc=_pwScatterSection(edges), _eb=_pwEdgeBoard(edges,teams,wallets,hist);
        _ds+=_sc+_eb;
        if(_sc||_eb) drawScatter=true;
      }
    }
    if(_ds) h+=_pwDsDivider(f,'Chancen in deinem aktiven Bewerb')+_ds;
    else h+='<div class="pw-none">Die globale <b>Poly-vs-Pinnacle-Edge</b> liegt jetzt im Tab <b>⚖️ Poly vs Sharp</b>. Hier erscheint das Deep-Detail deines aktiven Bewerbs (Settlement, Kohärenz, Pinnacle-Edges) — sichtbar unter dem ⚽ Fußball-Filter.</div>';
  }
  panel.innerHTML=h;
  if(drawScatter) _pwDrawScatter(edges);
  if(_pwState.open) _pwDrawDrillChart(edges,hist);
}

// ── KPI-Band ────────────────────────────────────────────────────────────────
// 25.07.2026 (Lucas: „+100% kauft netto muss falsch sein — und alles nur MLS"): der Balken war
// komplett aus dem MLS-Datensatz gerechnet und die Sentiment-Kachel degenerierte bei sell=0 zu
// +100%. Jetzt GLOBAL über alle Sportarten (broadLive + cross_sport), filter-abhängig, und ohne
// die kaputte Netto-Kachel. Wo noch keine Daten (Edge/Wale), ehrlich 0 / „—".
function _pwKpiBand(){
  const live=_pwCache&&_pwCache.broadLive;
  const up=(live?Object.values(live):[]).filter(m=>m&&m.resolved==null&&!_pwKoStale(m)&&_pwSportPass(m.league));   // 03.08.2026 (Lucas): fertige Spiele nicht ins "kommend"-KPI
  const vol=up.reduce((s,m)=>s+(m.totalUsd||0),0);
  const cats=new Set(up.map(m=>_pwSportCategory(m.league)));
  let whaleCap=0;
  for(const m of up) if(Array.isArray(m.whales)) for(const wh of m.whales) whaleCap+=Number(wh.usd)||0;
  const cs=_pwCache&&_pwCache.crossSport;
  const disc=(((cs&&cs.discrepancies)||[])).filter(d=>_pwSportPass(d.sport));
  const nGaps=disc.length;
  const big=disc.reduce((mx,d)=>Math.max(mx,Math.abs(d.gapPP||0)),0);
  const card=(ic,lbl,val,sub,col)=>'<div class="pw-kpi"><div class="pw-kpi-ic">'+ic+'</div><div class="pw-kpi-b">'
    +'<div class="pw-kpi-v" style="color:'+(col||PW_C.txt)+'">'+val+'</div><div class="pw-kpi-l">'+lbl+'</div>'
    +(sub?'<div class="pw-kpi-s">'+sub+'</div>':'')+'</div></div>';
  return '<div class="pw-kpis">'
    +card('💧','Poly-Volumen',_pwUsd(vol),'auf '+up.length+' kommenden Märkten'+(_pwSportFilter==='all'?' (alle Sportarten)':''))
    +card('🎯','Größte Lücke vs Pinnacle',big>0?_pwPP(big):'—',big>=PW_TRADE?'handelbar':big>=PW_NOISE?'dünn — nur beobachten':'aktuell keine echte Lücke',big>=PW_TRADE?PW_C.green:big>=PW_NOISE?PW_C.draw:PW_C.mut)
    +card('⚡','Auffällige Lücken',String(nGaps),'≥6pp Poly vs Pinnacle',nGaps>0?PW_C.green:PW_C.mut)
    +card('🐋','Whale-Kapital',whaleCap>0?_pwUsd(whaleCap):'—',whaleCap>0?'größte Einzel-Wallets':'füllt sich nah am Anpfiff')
    +card('🎮','Sportarten',String(cats.size),'mit Geld beobachtet')
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
function _pwCatOf(league, sport){
  if(sport && _PW_CAT_ICON[sport]) return [sport, _PW_CAT_ICON[sport]];   // 16.08.2026 (Lucas): gestempelter Sport zuerst
  const c=PW_LEAGUE_CAT[String(league||'').toLowerCase()];
  if(c) return c;
  // 03.08.2026 (Lucas: „Poly hat nun La Liga“): Regex-Fallback statt exaktem Key — laliga/bundesliga/
  // serie/ligue (und künftige Ligen) landen so korrekt in ⚽ Fußball statt „Sonstige“.
  const cat=_pwSportCategory(league);
  return cat!=='Sonstige' ? [cat, _PW_CAT_ICON[cat]||'·'] : ['Sonstige','·'];
}

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

// 25.07.2026 (Lucas: „ich seh nur MLS von vorher"): die Close-Datei (Geld+Wale) fror seit 19.07.
// nichts Neues ein. Statt der beschwichtigenden „füllt sich"-Meldung ehrlich sagen, wenn der Strom
// STEHT. _pwCloseNewestH = Stunden seit dem jüngsten eingefrorenen Markt (null = leer).
function _pwCloseNewestH(live){
  let newest=0;
  for(const m of (live?Object.values(live):[])){
    const t=(m&&m.capturedAt)?Date.parse(m.capturedAt):NaN;
    if(!isNaN(t)&&t>newest) newest=t;
  }
  if(!newest) return null;
  return (Date.now()-newest)/3.6e6;
}
function _pwStaleAge(h){ return Math.floor(h/24)>=1?Math.floor(h/24)+' Tagen':Math.round(h)+' h'; }
// Warnbanner über veralteten Daten (>36h ohne neuen Freeze). Leer, wenn frisch.
function _pwStaleBanner(live){
  const h=_pwCloseNewestH(live);
  if(h==null||h<=36) return '';
  return '<div class="pw-none" style="border:1px solid #7d4b16;background:#2b1d0e;color:#e3b341;margin:6px 0">'
    +'⚠️ <b>Datenstrom steht</b> — der zuletzt eingefrorene Markt ist <b>'+_pwStaleAge(h)+' alt</b>. '
    +'Der Mac-Runner friert gerade keine neuen Märkte ein (Anpfiff-Fenster), Geld &amp; Wale sind daher veraltet.</div>';
}

// Trenner: alles OBERHALB ist global (alle Sportarten), alles darunter ist der aktive Datensatz
// (z.B. MLS). 25.07.2026 (Lucas: „ich seh nur MLS von vorher") — macht die Herkunft eindeutig.
function _pwDsDivider(f,label){
  return '<div class="pw-dsdiv" style="margin:22px 0 6px;padding-top:14px;border-top:1px dashed #30363d;'
    +'color:#8b949e;font-size:12px;font-weight:700;letter-spacing:.3px;text-transform:uppercase">'
    +'↓ '+((f&&f.icon)?f.icon+' ':'')+_pwEsc(label)+' · '+_pwEsc((f&&f.label)||'aktiver Bewerb')+'</div>';
}

// 25.07.2026 (Lucas: „ich will sehen was einzelne Wale setzen, alle Sportarten"). Sektion (c):
// die größten EINZELNEN Wallets über alle Märkte (aus poly_money_broad_close.json → whales je Markt).
function _pwGlobalWhales(live){
  const entries=(live?Object.values(live):[]).filter(m=>m&&Array.isArray(m.whales)&&m.whales.length);
  const cats=new Set(entries.map(m=>_pwSportCategory(m.league)));
  const all=[];
  for(const [k,m] of (live?Object.entries(live):[])){
    if(!m||!Array.isArray(m.whales)||!m.whales.length||!_pwSportPass(m.league)) continue;
    if(m.resolved!=null||_pwKoStale(m)) continue;   // 03.08.2026 (Lucas): schon angepfiffene/aufgeloeste Spiele raus
    const match=(typeof _pwPlayLabel==='function')?_pwPlayLabel(k,Object.keys(m.shares||{}).map(s=>({s}))):Object.keys(m.shares||{}).join(' vs ');   // 16.08.2026 (Lucas): Spielkontext statt "Over vs Under"
    for(const wh of m.whales) if(wh&&wh.wallet) all.push({wallet:wh.wallet,side:wh.side,usd:Number(wh.usd)||0,key:k,league:m.league,match});
  }
  all.sort((a,b)=>b.usd-a.usd);
  const intro='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🐋 Was einzelne Wale setzen — alle Sportarten</span>'
    +'<span class="pw-sec-note">die größten Einzel-Wallets je Markt · auf welche Seite · wie viel · Klick → Wallet bzw. Markt auf Polymarket</span></div>';
  if(!all.length){
    if(_pwSportFilter!=='all')
      return intro+'<div class="pw-none">Keine '+_pwSportFilter+'-Wale gerade — Filter „Alle" zeigt wieder alles.</div></section>';
    const h=_pwCloseNewestH(live);
    const msg=(h!=null&&h>36)
      ? '⚠️ <b>Datenstrom steht seit '+_pwStaleAge(h)+'</b> — der Mac-Runner friert keine neuen Märkte ein, daher noch keine Wale erfasst.'
      : 'Noch keine Wale erfasst (füllt sich nah am Anpfiff über den Mac-Runner).';
    return intro+'<div class="pw-none"'+((h!=null&&h>36)?' style="border:1px solid #7d4b16;background:#2b1d0e;color:#e3b341"':'')+'>'+msg+'</div></section>';
  }
  const banner=_pwStaleBanner(live);
  const body=all.slice(0,25).map(x=>{
    const wl=_pwWalletChip(x.wallet);
    const mk='<a href="https://polymarket.com/event/'+encodeURIComponent(x.key)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681" title="Markt öffnen ↗">'+_pwEsc(x.match)+' <span style="color:#a78bfa">↗</span></a>';
    return '<tr><td style="white-space:nowrap">'+_pwSportIcon(x.league)+' <span class="pw-mut" style="font-size:11px">'+_pwEsc((x.league||'').toUpperCase())+'</span></td>'
      +'<td>'+mk+'</td><td>'+wl+'</td>'
      +'<td class="pw-cm"><b style="color:#4cc2ff">'+_pwEsc(x.side)+'</b></td>'
      +'<td class="pw-cn" style="font-weight:800">'+_pwUsd(x.usd)+'</td></tr>';
  }).join('');
  return intro+banner+'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    +'<th>Sport</th><th>Spiel</th><th>Wallet</th><th>setzt auf</th><th>Betrag</th>'
    +'</tr></thead><tbody>'+body+'</tbody></table></div></section>';
}

// ② Sharp-Wallet (25.07.2026, Lucas): CLV/Treffer je Wallet aus poly_wallet_track.json — trennt
// „scharf" (schlägt die Linie) von „bloß groß". Ab PW_SHARP_MIN_N aufgelösten Positionen bewertbar.
// 29.08.2026 (Lucas: „prinzipiell checken, welche Wallets wir tracken") — DIE Definition steht
// jetzt in sharp_gate.py; das hier ist ihr Spiegel. Der Vertrag zwischen beiden liegt in
// tests/fixtures/sharp_gate_cases.json und wird von pytest UND node geprueft.
//
// Was sich geaendert hat und warum (Zahlen vom 29.08.):
//  · n>=4 -> n>=8. Die 4 war ohnehin Dekoration: P&L wird erst ab n>=5 geholt, das Gate verlangte
//    P&L>0 — von 131 Wallets mit exakt n=4 hatte KEINE einen Wert. n>=4 und n>=8 lieferten
//    dasselbe Ergebnis. Jetzt steht die echte Schwelle da, statt dass ein Fetch-Budget sie setzt.
//  · rohe Quote >=55% -> Wilson-Untergrenze >50%. 5/9 sind 55,6% und beweisen nichts (Wilson 30%).
//    27 der 42 „scharfen" Wallets bestanden diesen Test nicht.
//  · P&L>0 zwingend -> P&L ist nur noch ein AUSSCHLUSS. Er ist bei 87% der Wallets unbekannt, und
//    er misst die gesamte Poly-Lebensbilanz (Wahlen, Krypto), waehrend die Trefferquote nur unsere
//    beobachteten Positionen misst. Zwei Welten, nicht ein Beweis.
const PW_SHARP_MIN_N=8;
const PW_SHARP_Z=1.645;        // 95% einseitig — identisch zu sharp_gate.SHARP_Z
function _pwWilsonLb(wins,n,z){
  n=n||0; if(n<=0) return 0;
  z=(z==null?PW_SHARP_Z:z);
  const p=(wins||0)/n, d=1+z*z/n;
  const centre=(p+z*z/(2*n))/d;
  const margin=z*Math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d;
  return centre-margin;
}
function _pwBeatsCoinflip(wins,n,z){ return !!n && _pwWilsonLb(wins,n,z)>0.5; }
const PW_SHARP_MIN_USD=250;    // 07.08.2026 (Lucas): $2-6-Positionen sind kein Signal — raus aus der Liste
function _pwIsSharpScore(sc){
  if(!sc) return false;
  const n=sc.n||0;
  if(n<PW_SHARP_MIN_N) return false;
  // wins bevorzugt direkt; sonst aus der Quote rekonstruieren (aeltere Aufrufer geben nur hit).
  const wins=(typeof sc.wins==='number')?sc.wins:Math.round((sc.hit||0)*n);
  if(!_pwBeatsCoinflip(wins,n)) return false;
  if((sc.avgClv||0)<0) return false;
  if(sc.pnlKnown && (sc.pnl||0)<0) return false;   // bestaetigter Verlierer raus, unbekannt bleibt
  return true;
}
// ── Der Regler (01.09.2026) — Spiegel von sharp_gate.sharp_grade ─────────────────────────────
// Gemessen (Wallets am 25.08. klassifiziert, danach ausgewertet was sie WIRKLICH taten):
//   dieses Gate (z=1.645)  16 Wallets -> n=180  54,4% (UG 48,3%)  Ø CLV +0,26pp
//   lockerer (z=1.282)     24 Wallets -> n=251  55,8% (UG 50,6%)  Ø CLV +0,55pp
//   die ausgeschlossene Bande (>=55% roh, UG<=50%, CLV>=0): n=136, Ø CLV +0,94pp — der beste Wert.
// Die strengste Einstellung lieferte die SCHLECHTESTE Vorwaerts-Leistung. Der Fehler lag nicht in
// der Schwelle, sondern in der FORM: ein Schalter gibt einer Wallet mit 60% aus 65 Plays
// (UG 49,8%) dieselbe Null wie einer mit 30% aus 8. Deshalb hier ein Regler statt eines Schalters —
// aber NUR fuer die Conviction, die abwaegt. Wo veroeffentlicht wird (Public-Push, das 🔥-Badge,
// _pwSharpSideForKey), bleibt der strenge Schalter: dort kostet ein Fehlalarm Glaubwuerdigkeit.
const PW_SHARP_GRADE_FLOOR=0.40;   // UG <=40% => 0 · UG >50% => 1 · dazwischen linear
const PW_SHARP_TAG_MIN_GRADE=0.5;  // ab hier heisst der Play auch 'sharp' (Eimer-Schutz, s. unten)
function _pwSharpGrade(sc){
  if(!sc) return 0;
  const n=sc.n||0;
  if(n<PW_SHARP_MIN_N) return 0;
  if((sc.avgClv||0)<0) return 0;
  if(sc.pnlKnown && (sc.pnl||0)<0) return 0;
  const wins=(typeof sc.wins==='number')?sc.wins:Math.round((sc.hit||0)*n);
  const lb=_pwWilsonLb(wins,n);
  if(lb>0.5) return 1;
  if(lb<=PW_SHARP_GRADE_FLOOR) return 0;
  return (lb-PW_SHARP_GRADE_FLOOR)/(0.5-PW_SHARP_GRADE_FLOOR);
}
const PW_MONEY_MAJ=0.60;   // (01.08.2026, Lucas) „großes Geld" erst ab echter Mehrheit — 50–55% ist Münzwurf, kein Signal
function _pwWalletScore(wallet){
  const s=_pwCache&&_pwCache.walletTrack&&_pwCache.walletTrack.scores;
  const e=s&&s[wallet];
  if(!e||!e.n) return null;
  // 29.08.2026: pnlKnown trennt „unbekannt" von „0". Vorher machte `Number(e.pnl)||0` aus beidem
  // dieselbe Null — und weil das Gate P&L>0 verlangte, flogen 318 Wallets raus, ueber die wir
  // schlicht nichts wussten. wins wandert mit, damit das Gate Wilson rechnen kann.
  return {n:e.n, avgClv:e.clvSumPP/e.n, hit:(e.wins||0)/e.n, wins:(e.wins||0),
          pnl:Number(e.pnl)||0, pnlKnown:(typeof e.pnl==='number' && isFinite(e.pnl))};
}
function _pwSharpCell(wallet){
  const sc=_pwWalletScore(wallet);
  if(!sc||sc.n<PW_SHARP_MIN_N)
    return {proven:false, html:'<span class="pw-mut" style="font-size:11px">· sammelt'+(sc?' (n'+sc.n+')':'')+'</span>'};
  const proven=_pwIsSharpScore(sc);   // 13.08.2026 (Lucas-Audit): strenges Gate (beide Achsen + PnL), nicht nur CLV>0
  const col=proven?'#3fb950':'#f85149';
  return {proven, html:'<span style="color:'+col+';font-weight:700">'+(sc.avgClv>=0?'+':'')+sc.avgClv.toFixed(1)+'pp</span>'
    +' <span class="pw-mut" style="font-size:11px">'+Math.round(sc.hit*100)+'% · n'+sc.n+'</span>'};
}

// 🔎 Whale-Drilldown (25.07.2026, Lucas): Klick auf eine Wallet → Karte mit Track-Record + allen
// offenen Positionen über alle Sportarten (aus walletTrack.open/scores). Overlay, schließbar.
function _pwWhaleDrillClose(){ const o=document.getElementById('pwDrillOverlay'); if(o) o.remove(); }
function _pwWhaleDrill(wallet){
  if(typeof document==='undefined'||!wallet) return;
  _pwWhaleDrillClose();
  const tr=_pwCache&&_pwCache.walletTrack, sc=_pwWalletScore(wallet);
  const open=(tr&&tr.open)?Object.values(tr.open).filter(e=>e&&e.wallet===wallet):[];
  open.sort((a,b)=>(b.usd||0)-(a.usd||0));
  const totUsd=open.reduce((s,e)=>s+(e.usd||0),0);
  const sports=[...new Set(open.map(e=>_pwSportCategory(e.league)))];
  const trHtml=sc
    ?('<span style="color:'+(sc.avgClv>0?'#3fb950':'#f85149')+';font-weight:800">'+(sc.avgClv>=0?'+':'')+sc.avgClv.toFixed(1)+'pp Ø CLV</span> · '+Math.round(sc.hit*100)+'% Treffer · n'+sc.n+(_pwIsSharpScore(sc)?' · <b style="color:#3fb950">🔥 scharf</b>':(sc.n>=PW_SHARP_MIN_N?' · <span class="pw-mut">unauffällig/schwach</span>':' · <span class="pw-mut">sammelt (n<'+PW_SHARP_MIN_N+')</span>')))
    :'<span class="pw-mut">noch kein Track-Record — sammelt über aufgelöste Positionen</span>';
  const rows=open.length?open.map(e=>'<tr>'
    +'<td style="white-space:nowrap">'+_pwSportIcon(e.league)+' <span class="pw-mut" style="font-size:11px">'+_pwEsc((e.league||'').toUpperCase())+'</span></td>'
    +'<td><a href="https://polymarket.com/event/'+encodeURIComponent(e.key)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:inherit;border-bottom:1px dotted #6e7681;text-decoration:none">'+_pwEsc(e.key)+' <span style="color:#a78bfa">↗</span></a></td>'
    +'<td class="pw-cm"><b style="color:#4cc2ff">'+_pwEsc(e.side)+'</b></td>'
    +'<td class="pw-cn pw-mut">'+(e.firstPrice!=null?Math.round(e.firstPrice*100)+'¢':'—')+'</td>'
    +'<td class="pw-cn" style="font-weight:700">'+_pwUsd(e.usd)+'</td></tr>').join('')
    :'<tr><td colspan="5" class="pw-mut" style="padding:12px">Keine offenen Positionen erfasst (getrackt werden Märkte nah am Anpfiff).</td></tr>';
  const o=document.createElement('div');
  o.id='pwDrillOverlay';
  o.style.cssText='position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;padding:20px';
  o.addEventListener('click',ev=>{ if(ev.target===o) _pwWhaleDrillClose(); });
  o.innerHTML='<div style="background:#0d1117;border:1px solid #30363d;border-radius:14px;max-width:720px;width:100%;max-height:85vh;overflow:auto;padding:18px 20px">'
    +'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><h2 style="margin:0;font-size:17px">🔎 Wallet '+_pwWallet(wallet)+'</h2>'
    +'<button onclick="_pwWhaleDrillClose()" style="background:none;border:none;color:#8b949e;font-size:22px;cursor:pointer;line-height:1">✕</button></div>'
    +'<div style="font-size:13px;margin-bottom:5px">Track-Record: '+trHtml+'</div>'
    +'<div class="pw-mut" style="font-size:12px;margin-bottom:12px">'+open.length+' offene Position(en) · '+_pwUsd(totUsd)+(sports.length?' · '+_pwEsc(sports.join(', ')):'')+' · <a href="https://polymarket.com/profile/'+encodeURIComponent(wallet)+'" target="_blank" rel="noopener" style="color:#a78bfa">Profil auf Polymarket ↗</a></div>'
    +'<div class="pw-tw"><table class="pw-tbl"><thead><tr><th>Sport</th><th>Markt</th><th>Seite</th><th>Einstieg</th><th>Einsatz</th></tr></thead><tbody>'+rows+'</tbody></table></div></div>';
  document.body.appendChild(o);
}
// Wallet mit 🔎-Drilldown (Profil-Link + In-App-Karte). Wallet ist eine Hex-Adresse (quote-sicher).
function _pwWalletChip(wallet){
  return '<a href="https://polymarket.com/profile/'+encodeURIComponent(wallet)+'" target="_blank" rel="noopener" class="pw-wl" title="Profil auf Polymarket">'+_pwWallet(wallet)+'</a>'
    +' <span onclick="_pwWhaleDrill(\''+wallet+'\')" title="Positionen & Track-Record ansehen" style="cursor:pointer;color:#a78bfa;font-size:12px">🔎</span>';
}
if(typeof window!=='undefined'){ window._pwWhaleDrill=_pwWhaleDrill; window._pwWhaleDrillClose=_pwWhaleDrillClose; }

// 25.07.2026 (Lucas: „die Whale-Auflistung für ALLE Sportarten, die größten Whales halt"):
// aggregiertes Leaderboard — je Wallet der GESAMT-Einsatz über alle kommenden Märkte (nicht pro
// Markt wie oben). ② Schärfe-Spalte (CLV/Treffer) + 🔥 für bewiesen-scharfe Wallets.
// ── 🥇 Schärfste Wallets — Rangliste nach Track-Record (31.07.2026, Lucas: „bei den Whale-Wallets
// fehlt ein Ranking — nur große, keine guten"). Rankt ALLE bewerteten Wallets (poly_wallet_track.
// scores), auch ohne aktuelle Position, nach einem Kombi-Score: Ø CLV + Trefferquote, konfidenz-
// gewichtet nach Stichprobe (mehr n → mehr Vertrauen). Beantwortet „wem folgen", nicht „wer setzt viel".
const PW_RANK_MIN_N = 12;      // CLV-Interim: hoch gaten, sonst adeln Zufalls-Stichproben (n=9) Verlierer
const PW_RANK_MIN_N_PNL = 8;   // sobald echte Poly-P&L da ist, reicht weniger getrackte Historie
// 09.08.2026 (Lucas): „Schärfste" darf nicht bloß „größter Gewinner" heißen. Wer bei genug getrackter
// Stichprobe den Close NICHT schlägt (Ø CLV<0) oder klar unter Münzwurf trifft, fliegt aus der Rangliste —
// egal wie hoch die Lifetime-P&L (die kommt oft aus Größe/Varianz/Krypto, nicht aus Sport-Schärfe).
const PW_RANK_FLOOR_N = 8;      // ab so vielen getrackten Wetten greift der Schärfe-Floor
const PW_RANK_FLOOR_CLV = 0;    // Ø CLV muss ≥ 0 sein (Einstieg schlägt Close)
const PW_RANK_FLOOR_HIT = 0.45; // und Trefferquote ≥ 45 %

// 23.08.2026 (Lucas: „das Wallet spielt auch hundert-Euro-Beträge, das interessiert mich nicht —
// ab 4-stellig aufwärts"). Rangliste standardmäßig auf Wallets mit ernsthaftem Ø-Einsatz filtern.
// Umschaltbar (Chip) falls man doch alle sehen will.
const PW_RANK_MIN_AVG_USD = 1000;
let _pwRankBigOnly = true;
function _pwSetRankBigOnly(v){ if(v===_pwRankBigOnly) return; _pwRankBigOnly=v; _pwRender(); }
if(typeof window!=='undefined') window._pwSetRankBigOnly=_pwSetRankBigOnly;
function _pwRankToggle(){
  const chip=(v,label)=>{const on=_pwRankBigOnly===v;
    return '<button onclick="_pwSetRankBigOnly('+(v?'true':'false')+')" style="padding:4px 11px;border-radius:16px;border:1px solid '
      +(on?'#5eead4':'var(--border)')+';background:'+(on?'rgba(94,234,212,.16)':'transparent')+';color:'+(on?'#5eead4':'var(--muted)')
      +';font-size:11.5px;font-weight:'+(on?700:500)+';cursor:pointer;font-family:inherit">'+label+'</button>';};
  return '<div style="max-width:1000px;margin:2px auto 12px;display:flex;gap:7px;flex-wrap:wrap;align-items:center">'
    +'<span class="pw-mut" style="font-size:11px;font-weight:700;margin-right:2px">Einsatz-Filter:</span>'
    +chip(true,'💰 nur ≥ $1.000 / Wette')+chip(false,'alle')+'</div>';
}
const PW_RANK_K = 6;           // Shrinkage: kleine Stichproben werden zur Neutralität gezogen
const PW_RANK_HITW = 6;        // Gewicht der Trefferquote (ggü. CLV) im Kombi-Score
function _pwWalletKombi(sc) {
  const raw = sc.avgClv + (sc.hit - 0.5) * PW_RANK_HITW;
  return raw * (sc.n / (sc.n + PW_RANK_K));
}
function _pwOpenByWallet() {
  const op = _pwCache && _pwCache.walletTrack && _pwCache.walletTrack.open, map = {};
  if (op && typeof op === 'object') for (const k in op) { const p = op[k]; if (!p || !p.wallet) continue; (map[p.wallet] = map[p.wallet] || []).push(p); }
  for (const w in map) map[w].sort((a, b) => (Number(b.usd) || 0) - (Number(a.usd) || 0));
  return map;
}
// $-Betrag mit Vorzeichen (P&L kann negativ sein). +$12K / −$800K
function _pwPnl(v) { const n = Number(v) || 0; return (n < 0 ? '−' : '+') + _pwUsd(Math.abs(n)); }
// „setzt gerade auf" — größte offene Position des Wallets (oder Hinweis).
function _pwNowCell(openMap, wallet) {
  const opens = openMap[wallet] || [], op = opens[0];
  if (!op) return '<span class="pw-mut" style="font-size:11px">— keine offene Position</span>';
  return _pwSportIcon(op.league) + ' <a href="https://polymarket.com/event/' + encodeURIComponent(op.key) + '" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681" title="Markt oeffnen"><b>' + _pwEsc(op.side) + '</b></a> <span class="pw-mut" style="font-size:11px">' + _pwUsd(op.usd) + (opens.length > 1 ? ' · +' + (opens.length - 1) : '') + '</span>';
}
function _pwMedal(i) { return i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : (i + 1); }

// ── 🐋 Whale-Plays (24.08.2026, Lucas: „im Betting ein Tab mit den Wetten der Top-20 Wale") ──
// Dieselbe Rangliste wie im Wallets-Menü (Modus A echte P&L, sonst CLV-Interim) → deren OFFENE
// Positionen. Gefiltert auf das, was man noch spielen KANN: Markt im Feed, nicht aufgelöst,
// Anpfiff in der Zukunft. Ohne diesen Filter wäre der Tab ein Friedhof — von 17 offenen
// Positionen der Top-20 waren am 24.08. genau 1 vor Anpfiff, 9 liefen schon, 7 waren gar nicht
// mehr im Feed (poly_wallet_track hält offen, bis eine Auflösung kommt).
const PW_WHALE_TOP_N = 20;
function _pwRankRows() {
  const scores = _pwCache && _pwCache.walletTrack && _pwCache.walletTrack.scores;
  if (!scores || !Object.keys(scores).length) return [];
  const hasPnl = Object.values(scores).some(s => s && typeof s.pnl === 'number');
  return hasPnl ? _pwRankRowsPnl(scores) : _pwRankRowsClv(scores);
}
// Markt zu einem Key: live zuerst, sonst der Vor-Spiel-Freeze. (`moneyBroad` ist NICHT die
// Markt-Landkarte, sondern der Genauigkeits-Backtest {n, byLeague} — als Fallback wertlos.)
function _pwMarketFor(key) {
  const c = _pwCache || {};
  return (c.broadLiveNow && c.broadLiveNow[key]) || (c.broadLive && c.broadLive[key]) || null;
}
function _pwWhalePlays(topN) {
  const top = _pwRankRows().slice(0, topN || PW_WHALE_TOP_N);
  if (!top.length) return [];
  const openMap = _pwOpenByWallet(), agg = {};
  top.forEach(function (r, i) {
    (openMap[r.wallet] || []).forEach(function (p) {
      if (!p || !p.key || !p.side) return;
      const m = _pwMarketFor(p.key);
      if (!m || m.resolved != null) return;            // nicht mehr im Feed / aufgelöst → nicht spielbar
      const htk = _pwRealHtk(m);
      if (htk == null || htk <= 0) return;             // angepfiffen → raus (Lucas: „nur noch spielbar")
      // 25.08.2026 (Lucas: „diese Sportarten scheinen in vielen Tabs noch auf"): der Whales-Tab ist
      // eine SETZ-Flaeche. Gesperrte Sportarten fielen hier auf einen toten „Öffnen"-Link zurueck —
      // Zeilen, die man nie spielen wird. Die Beobachtung lebt weiter im Wallets-Tab (Rangliste,
      // groesste Positionen, Trades) und im Papier-Depot, wo sie hingehoert.
      if (_pwBetBlocked({ league: m.league || p.league, sport: m.sport })) return;
      const gk = p.key + '|' + p.side;
      const e = agg[gk] || (agg[gk] = {
        key: p.key, side: p.side, league: m.league || p.league, sport: m.sport, htk: htk,
        price: (m.prices || {})[p.side], token: (m.tokens || {})[p.side] || null,
        // _pwEventLabel liefert HTML (<span>vs</span>) — hier braucht es KLARTEXT, weil der
        // Renderer escaped und der Token-Order-Bauer das Label an ' vs ' zerlegt. _pwPlayLabel
        // ist genau die Klartext-Variante, die auch der Heute-Scorer benutzt.
        match: _pwPlayLabel(p.key, Object.keys(m.shares || m.prices || {}).map(function (s) { return { s: s }; })),
        wallets: [], usd: 0, _eSum: 0, _eW: 0 });
      const u = Number(p.usd) || 0;
      const ent = Number(p.entryPrice != null ? p.entryPrice : p.firstPrice);
      e.wallets.push({ wallet: r.wallet, rank: i + 1, pnl: r.pnl, usd: u, entry: (ent > 0 ? ent : null) });
      e.usd += u;
      if (ent > 0) { e._eSum += ent * (u || 1); e._eW += (u || 1); }   // größere Position wiegt schwerer
    });
  });
  const out = Object.keys(agg).map(function (k) {
    const e = agg[k];
    e.entryAvg = e._eW ? (e._eSum / e._eW) : null;
    // „Haben wir den Move verpasst?" — ihr Einstieg vs. der Preis, den WIR jetzt zahlen.
    e.driftPP = (typeof e.price === 'number' && e.entryAvg) ? Math.round((e.price - e.entryAvg) * 1000) / 10 : null;
    e.n = e.wallets.length;
    e.bestRank = Math.min.apply(null, e.wallets.map(function (w) { return w.rank; }));
    delete e._eSum; delete e._eW;
    return e;
  });
  // Konflikt: halten Top-Wallets GEGENSEITEN desselben Markts? (24.08.2026, Lucas' INOX-Fall)
  // Zwei bewiesene Wallets auf verschiedenen Seiten heben sich als Signal weitgehend auf —
  // das MUSS dranstehen, sonst liest man eine Seite als Empfehlung, obwohl die andere genauso
  // gut belegt ist. Nicht unterdrückt, nur markiert und nach hinten sortiert (erst messen).
  // WICHTIG: erst NACH der map() oben — `n`/`bestRank` entstehen dort. Vorher gebaut,
  // trug `against` lauter undefined-Ränge (Badge zeigte „#undefined").
  const byMarket = {};
  out.forEach(function (e) { (byMarket[e.key] = byMarket[e.key] || []).push(e); });
  Object.keys(byMarket).forEach(function (mk) {
    const list = byMarket[mk];
    if (list.length < 2) return;
    list.forEach(function (e) {
      e.conflict = true;
      e.against = list.filter(function (o) { return o !== e; })
        .map(function (o) { return { side: o.side, n: o.n, bestRank: o.bestRank, usd: o.usd }; })
        .sort(function (x, y) { return x.bestRank - y.bestRank; });
    });
  });
  // Konsens zuerst, Konflikt ganz ans Ende: ein Wallet ist eine Meinung, zwei sind ein Signal —
  // zwei GEGENEINANDER sind keins.
  out.sort(function (a, b) {
    return ((a.conflict ? 1 : 0) - (b.conflict ? 1 : 0))
        || (b.n - a.n) || (a.bestRank - b.bestRank) || (b.usd - a.usd);
  });
  return out;
}
try { window._pwWhalePlays = _pwWhalePlays; window.PW_WHALE_TOP_N = PW_WHALE_TOP_N; } catch (_e) {}

// 🥇 Schärfste Wallets — Rangliste. ZWEI Modi:
//  (A) echte Poly-Bilanz (scores[w].pnl vorhanden, vom Mac-Runner aus der data-api /positions) →
//      primär nach realer P&L ranken, CLV/Treffer/n als Nebenwert. Das ist „wer verdient wirklich".
//  (B) Interim (noch keine P&L) → CLV-Kombi-Score auf getrackter Stichprobe, HART gegated + klar als
//      „kein Gewinn/Verlust" gelabelt. (31.07.2026, Lucas: ein −800K-Wallet stand mit n=9 auf #1, weil
//      CLV nur Timing auf 9 von 2000+ Wetten misst — nicht die echte Bilanz.)
function _pwSharpRanking() {
  const scores = _pwCache && _pwCache.walletTrack && _pwCache.walletTrack.scores;
  const kick = '<span class="pw-kicker">🥇 Schärfste Wallets — Rangliste nach Track-Record</span>';
  if (!scores || !Object.keys(scores).length) {
    return '<section class="pw-sec"><div class="pw-sec-head">' + kick + '<span class="pw-sec-note">wem folgen statt nur wer setzt viel</span></div>'
      + '<div class="pw-none">Noch keine bewerteten Wallets — <code>poly_wallet_track.json</code> sammelt je Wallet über die aufgelösten Spiele.</div></section>';
  }
  const openMap = _pwOpenByWallet();
  const hasPnl = Object.values(scores).some(s => s && typeof s.pnl === 'number');
  return hasPnl ? _pwRankByPnl(scores, openMap, kick) : _pwRankByClv(scores, openMap, kick);
}
// 24.08.2026 (Lucas, Whales-Tab): die AUSWAHL der Top-Wallets steckte bisher mitten im HTML-Bauen.
// Jetzt eigene Funktion, damit der Betting-Tab exakt dieselben Wallets bekommt wie das Wallets-Menü —
// ein zweites, nachgebautes Ranking wäre genau die Sorte Drift, die uns schon dreimal erwischt hat.
function _pwRankRowsPnl(scores) {
  return Object.keys(scores).map(function (w) {
    const v = scores[w]; if (!v || typeof v.pnl !== 'number' || (v.n || 0) < PW_RANK_MIN_N_PNL) return null;
    return { wallet: w, pnl: v.pnl, n: v.n || 0, avgClv: v.n ? (v.clvSumPP || 0) / v.n : 0, hit: v.n ? (v.wins || 0) / v.n : 0, usd: Number(v.usd) || 0 };
  }).filter(Boolean)
    // 09.08.2026 (Lucas): Schärfe-Floor — wer genug getrackt ist (n≥FLOOR_N) und den Close NICHT schlägt
    // (Ø CLV<0) oder klar unter Münzwurf trifft (Treffer<45 %), gehört nicht in die „Schärfste"-Liste,
    // egal wie hoch die Lifetime-P&L. Zu dünn getrackte (n<FLOOR_N) bleiben (können wir noch nicht beurteilen).
    .filter(function (r) { return r.n < PW_RANK_FLOOR_N || (r.avgClv >= PW_RANK_FLOOR_CLV && r.hit >= PW_RANK_FLOOR_HIT); })
    .filter(function (r) { return !_pwRankBigOnly || (r.n > 0 && r.usd / r.n >= PW_RANK_MIN_AVG_USD); })   // 4-stellig-Filter (Lucas)
    .sort(function (a, b) { return b.pnl - a.pnl; }).slice(0, 20);
}
function _pwRankByPnl(scores, openMap, kick) {
  const rows = _pwRankRowsPnl(scores);
  const intro = '<section class="pw-sec"><div class="pw-sec-head">' + kick
    + '<span class="pw-sec-note">Wallets, die den Close schlagen (Ø CLV ≥ 0 &amp; Treffer ≥ 45 % bei genug n), sortiert nach <b>echter Poly-Gesamt-Bilanz</b> (data-api /positions) · 🔥 = profitabel · nur Wallets ab $1.000 Ø-Einsatz</span></div>' + _pwRankToggle();
  if (!rows.length) return intro + '<div class="pw-none">Noch keine Wallet mit P&amp;L-Historie erfasst.</div></section>';
  const body = rows.map(function (r, i) {
    const pcol = r.pnl >= 0 ? '#3fb950' : '#f85149', clvCol = r.avgClv >= 0 ? '#3fb950' : '#f85149';
    return '<tr><td class="pw-cn" style="font-weight:800">' + _pwMedal(i) + '</td>'
      + '<td style="white-space:nowrap">' + (r.pnl > 0 ? '🔥 ' : '') + _pwWalletChip(r.wallet) + '</td>'
      + '<td class="pw-cn" style="font-weight:900;color:' + pcol + '">' + _pwPnl(r.pnl) + '</td>'
      + '<td class="pw-cn" style="color:' + clvCol + '">' + (r.avgClv >= 0 ? '+' : '') + r.avgClv.toFixed(1) + 'pp</td>'
      + '<td class="pw-cn">' + Math.round(r.hit * 100) + '%</td>'
      + '<td class="pw-cn pw-mut">' + r.n + '</td>'
      + '<td class="pw-cn pw-mut">' + _pwUsd(r.usd) + '</td>'
      + '<td class="pw-cn" style="font-weight:700">' + _pwUsd(r.n ? r.usd / r.n : 0) + '</td>'
      + '<td>' + _pwNowCell(openMap, r.wallet) + '</td></tr>';
  }).join('');
  return intro + '<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    + '<th>#</th><th>Wallet</th><th>Poly-P&amp;L</th><th>Ø CLV</th><th>Treffer</th><th>n</th><th>Einsatz</th><th>Ø/Wette</th><th>setzt gerade auf</th>'
    + '</tr></thead><tbody>' + body + '</tbody></table></div></section>';
}
function _pwRankRowsClv(scores) {
  return Object.keys(scores).map(function (w) {
    const v = scores[w]; if (!v || !v.n || v.n < PW_RANK_MIN_N) return null;
    const sc = { wallet: w, n: v.n, avgClv: (v.clvSumPP || 0) / v.n, hit: (v.wins || 0) / v.n, pnl: Number(v.pnl) || 0, usd: Number(v.usd) || 0 };
    sc.score = _pwWalletKombi(sc); return sc;
  }).filter(Boolean)
    .filter(function (r) { return !_pwRankBigOnly || (r.n > 0 && r.usd / r.n >= PW_RANK_MIN_AVG_USD); })   // 4-stellig-Filter (Lucas)
    .sort(function (a, b) { return b.score - a.score; }).slice(0, 20);
}
function _pwRankByClv(scores, openMap, kick) {
  const rows = _pwRankRowsClv(scores);
  const intro = '<section class="pw-sec"><div class="pw-sec-head">' + kick
    + '<span class="pw-sec-note">Interim: Kombi-Score aus Ø CLV + Treffer, ab n≥' + PW_RANK_MIN_N + ' getrackten Wetten · über alle Sportarten</span></div>'
    + '<div class="pw-sec-p" style="background:rgba(227,179,65,.08);border:1px solid rgba(227,179,65,.3);border-radius:9px;padding:9px 12px;margin:2px 0 12px"><b style="color:#e3b341">⚠️ Vorläufig — misst Timing (CLV), nicht Gewinn.</b> Diese Zahlen kommen nur aus den <i>wenigen großen Wetten, die wir mitbekommen haben</i> (nicht die Poly-Gesamt-Bilanz). Ein Wallet kann hier oben stehen und auf Polymarket trotzdem tief im Minus sein. Die Rangliste nach <b>echter P&amp;L</b> kommt, sobald der Runner sie mitzieht.</div>' + _pwRankToggle();
  if (!rows.length) return intro + '<div class="pw-none">Noch keine Wallet mit genug getrackter Historie (min. ' + PW_RANK_MIN_N + ' Wetten). Sammelt sich über die nächsten Tage.</div></section>';
  const body = rows.map(function (r, i) {
    const proven = _pwIsSharpScore(r), scol = r.score > 0 ? '#3fb950' : '#f85149', clvCol = r.avgClv >= 0 ? '#3fb950' : '#f85149';   // 13.08.2026 (Lucas-Audit): 🔥 nur bei echtem Sharp-Gate
    return '<tr><td class="pw-cn" style="font-weight:800">' + _pwMedal(i) + '</td>'
      + '<td style="white-space:nowrap">' + (proven ? '🔥 ' : '') + _pwWalletChip(r.wallet) + '</td>'
      + '<td class="pw-cn" style="font-weight:900;color:' + scol + '">' + (r.score >= 0 ? '+' : '') + r.score.toFixed(1) + '</td>'
      + '<td class="pw-cn" style="color:' + clvCol + ';font-weight:700">' + (r.avgClv >= 0 ? '+' : '') + r.avgClv.toFixed(1) + 'pp</td>'
      + '<td class="pw-cn">' + Math.round(r.hit * 100) + '%</td>'
      + '<td class="pw-cn pw-mut">' + r.n + '</td>'
      + '<td class="pw-cn pw-mut">' + _pwUsd(r.usd) + '</td>'
      + '<td class="pw-cn" style="font-weight:700">' + _pwUsd(r.n ? r.usd / r.n : 0) + '</td>'
      + '<td>' + _pwNowCell(openMap, r.wallet) + '</td></tr>';
  }).join('');
  return intro + '<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    + '<th>#</th><th>Wallet</th><th>CLV-Score</th><th>Ø CLV</th><th>Treffer</th><th>n</th><th>Einsatz</th><th>Ø/Wette</th><th>setzt gerade auf</th>'
    + '</tr></thead><tbody>' + body + '</tbody></table></div></section>';
}
if (typeof window !== 'undefined') window._pwSharpRanking = _pwSharpRanking;

function _pwGlobalWhaleLeaderboard(live){
  const agg={};
  for(const [k,m] of (live?Object.entries(live):[])){
    if(!m||m.resolved!=null||_pwKoStale(m)||!Array.isArray(m.whales)||!m.whales.length||!_pwSportPass(m.league)) continue;   // 03.08.2026 (Lucas): + Anpfiff-Gate
    const match=(typeof _pwPlayLabel==='function')?_pwPlayLabel(k,Object.keys(m.shares||{}).map(s=>({s}))):Object.keys(m.shares||{}).join(' vs ');   // 16.08.2026 (Lucas): Spielkontext statt "Over vs Under"
    for(const wh of m.whales){
      if(!wh||!wh.wallet) continue;
      const usd=Number(wh.usd)||0;
      const a=agg[wh.wallet]||(agg[wh.wallet]={usd:0,mkts:new Set(),sports:new Set(),top:null});
      a.usd+=usd; a.mkts.add(k); if(m.league) a.sports.add(m.league);
      if(!a.top||usd>a.top.usd) a.top={usd,match,side:wh.side,league:m.league,key:k};
    }
  }
  const rows=Object.entries(agg).map(([w,a])=>({wallet:w,usd:a.usd,mkts:a.mkts,sports:a.sports,top:a.top}))
    .sort((x,y)=>y.usd-x.usd).slice(0,25);
  const intro='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🏦 Größte Whales — alle Sportarten</span>'
    +'<span class="pw-sec-note">nach Gesamt-Einsatz · <b>Schärfe</b> = Ø CLV (Einstieg schlägt Close) + Trefferquote je Wallet · 🔥 = bewiesen scharf · Klick → Wallet bzw. Markt</span></div>';
  if(!rows.length) return intro+'<div class="pw-none">'+(_pwSportFilter==='all'
    ?'Noch keine Wale erfasst (füllt sich nah am Anpfiff über den Mac-Runner).'
    :'Keine '+_pwSportFilter+'-Wale gerade — Filter „Alle" zeigt wieder alles.')+'</div></section>';
  const body=rows.map((r,i)=>{
    const sh=_pwSharpCell(r.wallet);
    const wl=_pwWalletChip(r.wallet);
    const sports=[...r.sports].slice(0,4).map(s=>_pwSportIcon(s)).join('');
    const mk=r.top?('<a href="https://polymarket.com/event/'+encodeURIComponent(r.top.key)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681" title="Markt öffnen ↗">'+_pwEsc(r.top.match)+' <span style="color:#a78bfa">↗</span></a>'):'—';
    return '<tr><td class="pw-cn pw-mut">'+(i+1)+'</td>'
      +'<td style="white-space:nowrap">'+(sh.proven?'🔥 ':'')+wl+'</td>'
      +'<td class="pw-cn" style="font-weight:800">'+_pwUsd(r.usd)+'</td>'
      +'<td style="white-space:nowrap">'+sh.html+'</td>'
      +'<td class="pw-cn pw-mut">'+r.mkts.size+'</td>'
      +'<td style="white-space:nowrap">'+sports+'</td>'
      +'<td>'+mk+' <span class="pw-mut" style="font-size:11px">('+_pwEsc(r.top?r.top.side:'')+')</span></td></tr>';
  }).join('');
  return intro+'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    +'<th>#</th><th>Wallet</th><th>Gesamt-Einsatz</th><th>Schärfe (CLV/Treffer)</th><th>Märkte</th><th>Sport</th><th>größte Position</th>'
    +'</tr></thead><tbody>'+body+'</tbody></table></div></section>';
}

// 25.07.2026 (Lucas: „wo liegt Poly falsch vs Pinnacle, alle Sportarten"). Sektion (a): globale
// Edge aus poly_cross_sport.json (Poly-% vs de-viggte Pinnacle-%). Konvergenz = das Echtheits-
// Kriterium (Lücke schließt sich über Tage → echt; steht → Artefakt). Dieselbe Daten wie Poly-Radar.
const _PW_SPORT_ICON={soccer:'⚽',basketball:'🏀',americanfootball:'🏈',baseball:'⚾',icehockey:'🏒',
  mma:'🥊',boxing:'🥊',tennis:'🎾',cricket:'🏏',golf:'⛳',esports:'🎮'};
function _pwSportIcon(sport){
  // 18.08.2026 (Lucas: „für Fußball dieses komische Pfeil-Icon"): frueher grobe Eigen-Map -> Fallback 🎯
  // fuer La-Liga/Serie/Ligue etc. Jetzt ueber den robusten _pwSportCategory (kennt alle Liga-Muster).
  if(sport && _PW_CAT_ICON[sport]) return _PW_CAT_ICON[sport];   // schon eine Kategorie ('Fußball' …)
  return _PW_CAT_ICON[_pwSportCategory(sport)] || '🎯';
}
function _pwGlobalEdge(cs){
  const allDisc=(cs&&cs.discrepancies)?cs.discrepancies.slice():[];
  const cats=new Set(allDisc.map(d=>_pwSportCategory(d.sport)));
  const disc=allDisc.filter(d=>_pwSportPass(d.sport));
  const intro='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🎯 Wo Poly falscher liegt als Pinnacle — alle Sportarten</span>'
    +'<span class="pw-sec-note">Poly-% vs faire Pinnacle-% · Lücke = Kandidat · aber erst echt, wenn sie sich über Tage schließt (Konvergenz)</span></div>';
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
// 26.07.2026 (Lucas: No-vs-Yes als Spielname ist sinnlos). Team-Maerkte haben echte Namen in den
// Ausgaengen (-> A vs B). Binaere Ja/Nein-Maerkte (Props, Einzelfragen) haetten nur Yes/No -> als
// Spielname wertlos. Dann lesbaren Namen aus dem Slug ableiten: {liga}-{a}-{b}-{datum}[-{prop}].
// 16.08.2026 (Lucas): geteilter Team-Resolver fuer ALLE Label-Funktionen. Bei Prop-Maerkten
// (-more-markets/-exact-score/…) sind die Outcomes KEINE Teams (Over/Under, Score-Zeilen "0 - 0") ->
// echte Paarung aus dem BASIS-Event ziehen. Liefert {teams:[A,B]|null, base}.
const _PW_SCORE_RX=/\d\s*[-:]\s*\d/;
const _PW_GEN_RX=/^(yes|no|ja|nein|over|under|draw|remis|tie)$/i;
const _PW_DRAWP_RX=/^(draw|the draw|unentschieden|remis)\b/i;
const _PW_PROP_SUFFIX_RX=/-(more-markets|exact-score|halftime-result|1st-half|first-half|2nd-half)$/i;
// 23.08.2026 (Lucas): breitere Liste NUR fuer die Team-Namens-Aufloesung (nicht fuers Play-Dedup) —
// so wird auch bei -total-corners/-btts/-player-props der Basis-Event fuer die Teamnamen gefunden,
// ohne solche eigenstaendigen Wett-Typen faelschlich mit der Moneyline zu einem Play zu verschmelzen.
const _PW_NAME_SUFFIX_RX=/-(more-markets|exact-score|halftime-result|total-corners|total-cards|total-goals|both-teams-to-score|btts|first-to-score|player-props|1st-half|first-half|2nd-half)$/i;
function _pwRealTeams(arr){
  return (arr||[]).filter(n=>{const t=String(n).trim();return t&&!_PW_GEN_RX.test(t)&&!_PW_DRAWP_RX.test(t)&&!_PW_SCORE_RX.test(t);});
}
function _pwResolveTeams(key, names){
  const base=String(key||'').replace(_PW_NAME_SUFFIX_RX,'');
  if(base===String(key||'')){                     // kein Prop -> Outcomes SIND die Teams
    const r=_pwRealTeams(names); return {teams:r.length>=2?r.slice(0,2):null, base};
  }
  // Prop (z.B. -total-corners, -exact-score) -> Teamnamen aus dem Basis-Event ziehen. 23.08.2026 (Lucas):
  // (a) auch prices lesen (Basis-Event hat oft leere shares, die Teamnamen stehen dann nur in prices),
  // (b) alle geladenen Broad-Caches durchsuchen (Close/Live/Global), nicht nur die zwei Live-Quellen —
  // sonst bleibt "epl new liv · total corners" als roher Slug stehen statt "Newcastle vs Liverpool".
  const srcs=[_pwCache&&_pwCache.broadLiveNow,_pwCache&&_pwCache.broadLive,_pwCache&&_pwCache.moneyBroad];
  for(let i=0;i<srcs.length;i++){
    const bm=srcs[i]&&srcs[i][base]; if(!bm) continue;
    const keysS=bm.shares?Object.keys(bm.shares):[];
    const keysP=bm.prices?Object.keys(bm.prices):[];
    const r=_pwRealTeams(keysS.length?keysS:keysP);
    if(r.length>=2) return {teams:r.slice(0,2), base};
  }
  return {teams:null, base};
}
function _pwEventLabel(key, names, league){
  const {teams,base}=_pwResolveTeams(key,names);
  if(teams) return teams.map(_pwEsc).join(' <span style="color:#6e7681">vs</span> ');
  // 16.08.2026 (Lucas): keine Teams aufloesbar -> Slug MIT Suffix als Markt-Typ-Hinweis (kein blindes Strippen).
  let str=String(key||'').replace(/-\d{4}-\d{2}-\d{2}/g,'');
  let parts=str.split('-').filter(Boolean);
  const lg=String(league||'').toLowerCase();
  if(parts.length>1 && parts[0].toLowerCase()===lg) parts.shift();
  const human=parts.map(p=>p.length<=3?p.toUpperCase():p.charAt(0).toUpperCase()+p.slice(1)).join(' ');
  return _pwEsc(human||key||'—');
}

// ── ×-Norm (30.07.2026, Lucas): überverhältnismäßig viel Geld erkennen ─────────────
// Wie beim Betfair-Radar, aber Poly-gerecht: (1) Gesamt-Volumen und (2) frischer Zufluss
// werden je Spiel gegen den Median VERGLEICHBARER Spiele gemessen — gebucketet nach
// Sportart × Phase (live / ≤3h vor Anpfiff / früher). Cross-Sport-Vergleich wäre unfair
// (MLB-Markt ≫ Nischen-Esport), darum die Sportart mit im Bucket. Ab ×1.6 auffällig, ab ×2.6 stark.
var PW_NORM_AMBER = 1.6, PW_NORM_RED = 2.6, PW_NORM_MIN_PEERS = 4, PW_NORM_MIN_USD = 5000, PW_NORM_MIN_INFLOW = 1000;
// 16.08.2026 (Lucas Übersicht-Check): "welche Seite hat die Masse gesetzt"-Sektionen (Großes Geld,
// ×-Norm) nur fuer Maerkte mit echter Seiten-Aufteilung. Raus: (a) leere shares:{} (Volumen ohne Split,
// Capture-Luecke — z.B. cs2-9z-mgc "Geld auf — 0%") und (b) Exact-Score-Props, deren Favorit eine
// Score-Zeile "0 - 0" ist (keine Seite -> Rauschen; das Moneyline-Event deckt das Spiel schon ab).
function _pwSideMarket(k,m){
  if(!m||!m.shares) return false;
  var names=Object.keys(m.shares); if(!names.length) return false;
  if(/-exact-score$/i.test(String(k||''))) return false;
  var fav=names[0], best=-Infinity;
  for(var i=0;i<names.length;i++){ var u=Number(m.shares[names[i]])||0; if(u>best){best=u;fav=names[i];} }
  return !_PW_SCORE_RX.test(String(fav||''));
}
function _pwNormStage(m){ var h=_pwRealHtk(m); if(h==null) return 'pre'; if(h<0) return 'live'; if(h<=3) return 'soon'; return 'pre'; }
function _pwNormKey(m){ return _pwSportCategory(m.league, m.sport)+'|'+_pwNormStage(m); }
// Frischer Zufluss = Δ Gesamt-Volumen zwischen den letzten zwei History-Punkten (Poly-Volumen
// wächst nur, also ist Δ≥0 „neu dazugekommenes Geld"). null, wenn <2 Punkte vorliegen.
function _pwInflow(key,hist){ var a=hist&&hist[key]; if(!Array.isArray(a)||a.length<2) return null; var v2=Number(a[a.length-1].v), v1=Number(a[a.length-2].v); if(!isFinite(v2)||!isFinite(v1)) return null; var d=v2-v1; return d>0?d:0; }
function _pwMedianBy(items,keyFn,valFn){ var acc={}; items.forEach(function(it){ var k=keyFn(it); (acc[k]=acc[k]||[]).push(valFn(it)); }); var out={}; for(var k in acc){ var arr=acc[k].slice().sort(function(a,b){return a-b;}); out[k]={med:arr[Math.floor(arr.length/2)],n:arr.length}; } return out; }
function _pwNormCss(){
  if(typeof document==='undefined'||document.getElementById('pwn-css'))return;
  var css=[
   '#polyWalletsPanel .pwn-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(440px,1fr));gap:4px 20px;margin:4px 0 12px;}',
   '@media(max-width:820px){#polyWalletsPanel .pwn-grid{grid-template-columns:1fr;}}',
   '#polyWalletsPanel .pwn-sub{font-size:12px;font-weight:800;color:#e6edf3;margin:10px 0 4px;}',
   '#polyWalletsPanel .pwn-note{font-weight:600;color:#6e7681;font-size:10.5px;}',
   '#polyWalletsPanel .pwn-none{font-size:11.5px;color:#6e7681;margin:2px 0 8px;}',
   '#polyWalletsPanel .pwn-row{position:relative;padding:7px 11px;border-radius:9px;overflow:hidden;background:#0f141b;}',
   '#polyWalletsPanel .pwn-over{box-shadow:inset 0 0 0 1px rgba(245,197,24,.42);}',
   '#polyWalletsPanel .pwn-over2{box-shadow:inset 0 0 0 1px rgba(248,81,73,.58);}',
   '#polyWalletsPanel .pwn-fill{position:absolute;left:0;top:0;bottom:0;border-radius:9px;}',
   '#polyWalletsPanel .pwn-in{position:relative;display:flex;justify-content:space-between;align-items:center;gap:12px;}',
   '#polyWalletsPanel .pwn-l{min-width:0;}',
   '#polyWalletsPanel .pwn-g{font-size:12.5px;font-weight:700;color:#e6edf3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
   '#polyWalletsPanel .pwn-lg{color:#8b949e;font-size:10.5px;font-weight:700;}',
   '#polyWalletsPanel .pwn-a{color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681;}',
   '#polyWalletsPanel .pwn-side{font-size:10.5px;color:#8b949e;margin-top:1px;}',
   '#polyWalletsPanel .pwn-r{text-align:right;white-space:nowrap;flex:0 0 auto;}',
   '#polyWalletsPanel .pwn-v{display:block;font-size:12.5px;font-weight:900;color:#e6edf3;font-family:ui-monospace,"JetBrains Mono",Menlo,monospace;}',
   '#polyWalletsPanel .pwn-badge{display:inline-block;font-size:9.5px;font-weight:800;padding:0 5px;margin-top:2px;border:1px solid;border-radius:6px;line-height:15px;}'
  ].join('');
  var st=document.createElement('style'); st.id='pwn-css'; st.textContent=css; (document.head||document.documentElement).appendChild(st);
}
function _pwNormRow(it,mx,mode){
  var m=it.m;
  var oc=Object.entries(m.shares||{}).map(function(e){return {n:e[0],u:Number(e[1])||0};}).sort(function(a,b){return b.u-a.u;});
  var tot=oc.reduce(function(s,o){return s+o.u;},0)||1, fav=oc[0]||{n:'—',u:0}, favPct=Math.round(fav.u/tot*100);
  var ic=_pwCatOf(m.league, m.sport)[1], lg=(m.league||'').toUpperCase();
  var name=_pwEventLabel(it.k,oc.map(function(o){return o.n;}),m.league);
  var link=it.k?('https://polymarket.com/event/'+encodeURIComponent(it.k)):null;
  var nameHtml=link?('<a href="'+link+'" target="_blank" rel="noopener" class="pwn-a">'+name+' ↗</a>'):name;
  var red=it.ratio>=PW_NORM_RED, col=red?'#f85149':'#f5c518';
  var w=Math.max(6,it.val/mx*100);
  var val=mode==='inf'?('▲ +'+_pwUsd(it.val)):_pwUsd(it.val);
  var badge='<span class="pwn-badge" style="color:'+col+';border-color:'+col+'">×'+it.ratio.toFixed(1)+' Norm</span>';
  return '<div class="pwn-row '+(red?'pwn-over2':'pwn-over')+'"><i class="pwn-fill" style="width:'+w+'%;background:'+(red?'rgba(248,81,73,.16)':'rgba(245,197,24,.14)')+'"></i>'
    +'<div class="pwn-in"><div class="pwn-l"><div class="pwn-g">'+ic+' <span class="pwn-lg">'+lg+'</span> · '+nameHtml+'</div>'
    +'<div class="pwn-side">Geld auf <b style="color:#4cc2ff">'+_pwEsc(fav.n)+'</b> '+favPct+'%</div></div>'
    +'<div class="pwn-r"><span class="pwn-v">'+val+'</span>'+badge+'</div></div></div>';
}
function _pwNormBlock(title,note,items,mode){
  if(!items.length) return '<div class="pwn-sub">'+title+'</div><div class="pwn-none">sammelt noch — braucht ≥'+PW_NORM_MIN_PEERS+' vergleichbare Spiele je Sportart×Phase'+(mode==='inf'?' und zwei Läufe für den Zufluss':'')+'.</div>';
  var mx=Math.max.apply(null,items.map(function(it){return it.val;}))||1;
  return '<div class="pwn-sub">'+title+' <span class="pwn-note">'+note+'</span></div><div class="pwn-grid">'+items.map(function(it){return _pwNormRow(it,mx,mode);}).join('')+'</div>';
}
// Beide Blickwinkel: Gesamt-Volumen (steht auf dem Markt) und frischer Zufluss (kam gerade rein).
function _pwOverNorm(live,hist){
  if(!live||!Object.keys(live).length) return '';
  var cand=Object.entries(live).map(function(e){return {k:e[0],m:e[1]};})
    .filter(function(x){return x.m&&x.m.resolved==null&&(x.m.totalUsd||0)>=PW_NORM_MIN_USD&&!_pwKoStale(x.m)&&_pwSportPass(x.m.league, x.m.sport)&&_pwSideMarket(x.k,x.m);});
  if(!cand.length) return '';
  var over=function(items,valFn,floor){
    var base=_pwMedianBy(items,function(it){return _pwNormKey(it.m);},function(it){return it.val;});
    return items.map(function(it){var b=base[_pwNormKey(it.m)];var r=(b&&b.n>=PW_NORM_MIN_PEERS&&b.med)?it.val/b.med:null;it.ratio=r;return it;})
      .filter(function(it){return it.ratio!=null&&it.ratio>=PW_NORM_AMBER;}).sort(function(a,b){return b.ratio-a.ratio;}).slice(0,8);
  };
  var totItems=cand.map(function(x){return {k:x.k,m:x.m,val:x.m.totalUsd||0};});
  var totOver=over(totItems);
  var infItems=cand.map(function(x){var d=_pwInflow(x.k,hist);return (d!=null&&d>=PW_NORM_MIN_INFLOW)?{k:x.k,m:x.m,val:d}:null;}).filter(Boolean);
  var infOver=over(infItems);
  if(!totOver.length&&!infOver.length){
    return '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">⚖️ ×-Norm — überverhältnismäßig viel Geld</span>'
      +'<span class="pw-sec-note">Median je Sportart × Spielphase</span></div>'
      +'<div class="pw-sec-p">Gerade liegt kein Markt auffällig über seiner Norm — alles im üblichen Rahmen für Sportart &amp; Phase. Meldet sich, sobald irgendwo verhältnismäßig viel Geld draufkommt.</div></section>';
  }
  _pwNormCss();
  return '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">⚖️ ×-Norm — wo überverhältnismäßig viel Geld liegt</span>'
    +'<span class="pw-sec-note">jedes Spiel gegen den Median gleicher <b>Sportart × Phase</b> (live/≤3h/vorab) · ab ×1.6 auffällig, ab ×2.6 stark</span></div>'
    +'<div class="pw-sec-p" style="margin:2px 0 10px">Nicht wer absolut am meisten hat, sondern wer <b>mehr als üblich</b> für seine Situation zieht. Zwei Blickwinkel: das <b>Gesamt-Volumen</b> auf dem Markt und der <b>frische Zufluss</b> seit dem letzten Lauf.</div>'
    +_pwNormBlock('💰 Gesamt-Volumen über Norm','Gesamt-$ auf dem Markt ÷ Median',totOver,'tot')
    +_pwNormBlock('💸 Zufluss über Norm','frisches $ seit letztem Lauf ÷ Median',infOver,'inf')
    +'</section>';
}
if(typeof window!=='undefined'){ window._pwOverNorm=_pwOverNorm; window._pwNormStage=_pwNormStage; window._pwInflow=_pwInflow; }
// 07.08.2026 (Lucas): „Volumen ueber Norm" auch auf der Uebersicht (statt Whale-Watch). Liefert die
// Top-Zeilen als DATEN (Rendering macht main-dashboard im Uebersichts-Stil). Reine Leseschicht, gleiche
// Quelle/Logik wie der Grosses-Geld-Tab (_pwOverNorm), nur Gesamt-Volumen (kein Zufluss).
function _pwOverNormTop(limit){
  var live=_pwCache&&_pwCache.broadLive; if(!live) return [];
  var cand=Object.entries(live).map(function(e){return {k:e[0],m:e[1]};})
    .filter(function(x){return x.m&&x.m.resolved==null&&(x.m.totalUsd||0)>=PW_NORM_MIN_USD&&!_pwKoStale(x.m)&&_pwSportPass(x.m.league, x.m.sport)&&_pwSideMarket(x.k,x.m);})
    .map(function(x){return {k:x.k,m:x.m,val:x.m.totalUsd||0};});
  if(!cand.length) return [];
  var base=_pwMedianBy(cand,function(it){return _pwNormKey(it.m);},function(it){return it.val;});
  return cand.map(function(it){var b=base[_pwNormKey(it.m)];it.ratio=(b&&b.n>=PW_NORM_MIN_PEERS&&b.med)?it.val/b.med:null;return it;})
    .filter(function(it){return it.ratio!=null&&it.ratio>=PW_NORM_AMBER;})
    .sort(function(a,b){return b.ratio-a.ratio;}).slice(0,limit||5)
    .map(function(it){
      var m=it.m||{};
      var oc=Object.entries(m.shares||{}).map(function(e){return {n:e[0],u:Number(e[1])||0};}).sort(function(a,b){return b.u-a.u;});
      var tot=oc.reduce(function(su,o){return su+o.u;},0)||1, fav=oc[0]||{n:'-',u:0};
      return {key:it.k, league:m.league, sport:m.sport, name:_pwEventLabel(it.k,oc.map(function(o){return o.n;}),m.league),
              fav:fav.n, favPct:Math.round(fav.u/tot*100), usd:m.totalUsd||0, ratio:it.ratio,
              url: it.k?('https://polymarket.com/event/'+encodeURIComponent(it.k)):null};
    });
}
if(typeof window!=='undefined') window._pwOverNormTop=_pwOverNormTop;

function _pwMoneyLive(live){
  const all=(live?Object.entries(live):[]).map(([k,m])=>({k,m}))
    .filter(x=>x.m && x.m.resolved==null && x.m.shares && Object.keys(x.m.shares).length && (x.m.totalUsd||0)>=5000 && !_pwKoStale(x.m) && _pwSideMarket(x.k,x.m));   // 16.08.2026 (Lucas): leere shares:{} (Volumen ohne Split, Capture-Luecke) raus -> kein Crash im Geld-Split
  const cats=new Set(all.map(x=>_pwSportCategory(x.m.league, x.m.sport)));
  const rows=all.filter(x=>_pwSportPass(x.m.league, x.m.sport))
    .sort((a,b)=>(b.m.totalUsd||0)-(a.m.totalUsd||0)).slice(0,30);
  const intro='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">💰 Wo liegt das große Geld — alle Sportarten</span>'
    +'<span class="pw-sec-note">kommende Spiele nach Poly-Volumen · auf welche Seite hat die Masse gesetzt · zum Folgen</span></div>';
  if(!rows.length) return intro+'<div class="pw-none">'+_pwStaleMsg(_pwSportFilter==='all'
    ?'Gerade kein nennenswertes Geld auf kommenden Märkten (füllt sich nah am Anpfiff, läuft am Mac-Runner).'
    :'Keine kommenden '+_pwSportFilter+'-Märkte gerade — Filter „Alle" zeigt wieder alles.')+'</div></section>';
  const body=rows.map(({k,m})=>{
    const oc=Object.entries(m.shares||{}).map(([name,usd])=>({name,usd:Number(usd)||0}));
    const total=oc.reduce((s,o)=>s+o.usd,0)||1; oc.sort((a,b)=>b.usd-a.usd);
    const fav=oc[0]||{name:'—',usd:0}, favPct=Math.round(fav.usd/total*100);   // 16.08.2026 (Lucas): Guard wie _pwLiveCard/_pwNormRow — oc kann leer sein
    const favPrice=(m.prices&&m.prices[fav.name]!=null)?Math.round(m.prices[fav.name]*100)+'¢':'—';
    // Spiel-Spalte klickbar → direkt auf den Polymarket-Markt (Key ist der Event-Slug). 25.07.2026 (Lucas).
    const matchTxt=_pwEventLabel(k, oc.map(o=>o.name), m.league);
    const match=k?('<a href="https://polymarket.com/event/'+encodeURIComponent(k)+'" target="_blank" rel="noopener" '
      +'style="color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681" title="Auf Polymarket öffnen ↗">'+matchTxt+' <span style="color:#a78bfa">↗</span></a>'):matchTxt;
    const ic=_pwCatOf(m.league, m.sport)[1], lg=(m.league||'').toUpperCase();
    const _rh=_pwRealHtk(m); const htk=_rh!=null?(_rh<0?'live':_rh<1?'<1h':Math.round(_rh)+'h'):'—';
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
  return intro+_pwStaleBanner(live)
    +'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    +'<th>Sport</th><th>Spiel</th><th>Geld-Split</th><th>Geld liegt auf</th><th>Volumen</th><th>Anpfiff</th>'
    +'</tr></thead><tbody>'+body+'</tbody></table></div></section>';
}

// ③ Heute-wetten-Shortlist (25.07.2026, Lucas): EINE Liste, die alle Signale zu einer Entscheidung
// bündelt. Edge-fokussiert — zeigt NICHT bloße Favoriten (kein Edge), sondern Märkte mit echtem
// Signal: Steam, scharfe Wallet, oder Geld-vs-Preis-Divergenz (liga-informiert). BET = mit dem Geld,
// FADE = gegen das Geld. Wird reicher, je mehr ①/② Daten sammeln.
// ── ⚡ LIVE (11.08.2026, Lucas Stufe 2): Geld & Whales auf LAUFENDEN Spielen. Quelle: poly_money_broad_live.json
// (der leichte Live-Scan, alle ~5 Min). Zeigt frischen Zufluss + Whales, die JETZT reingehen, und markiert
// Wallets, die im Live-Top-4 auftauchen, aber vor Anpfiff NICHT drin waren (= live eingestiegen = das Signal).
// 11.08.2026 (Lucas): entschiedene Live-Maerkte raus — steht der Favorit bei >=95c, ist das Spiel
// quasi durch (der 100c-Fall). Live-Geld darauf ist nur noch Abwicklung, kein Signal. Gleiche
// „durch-das-Spiel"-Logik wie die Alert-Preisschwelle. Greift in beiden Live-Listen + im Live-Tab.
const PW_LIVE_DECIDED_PRICE=0.95;
function _pwLiveDecided(m){
  if(!m||!m.prices) return false;
  let mx=0; for(const k in m.prices){ const v=Number(m.prices[k]); if(isFinite(v)&&v>mx) mx=v; }
  return mx>=PW_LIVE_DECIDED_PRICE;
}
// ⚡ Live-Signal Track-Record (12.08.2026, Lucas Stufe 1): Forward-CLV je Kriterien-Bucket aus
// poly_live_signal_track.json. Misst, gatet noch nicht — zeigt, welche Kriterien wirklich tragen.
function _pwLiveSignalTrack(d){
  var rec = d && d.record;
  var intro='<section class="pw-sec" style="margin-top:20px"><div class="pw-sec-head">'
    +'<span class="pw-kicker">⚡ Live-Signale — Forward-CLV Track-Record</span>'
    +'<span class="pw-sec-note">Misst (gatet noch nicht): jeder Live-Whale-Einstieg wird über die Preis-Zeitreihe nachgezogen. <b>Forward-CLV = Preisbewegung NACH dem Einstieg</b> — &gt;0 heißt, das Geld hat den Preis geführt. Nach ein paar Tagen zeigt sich je Kriterium, was trägt.</span></div>';
  if(!rec || !rec.buckets || !rec.settled){
    return intro+'<div class="pw-none">Noch keine abgerechneten Live-Signale — sammelt sich, sobald der Live-Scan läuft und Spiele durch sind. (Offen gerade: '+((rec&&rec.open)||0)+')</div></section>';
  }
  var b=rec.buckets;
  var clvCol=function(v){return v==null?'var(--muted)':v>0?'#3fb950':v<0?'#f85149':'var(--muted)';};
  var pctv=function(v){return v==null?'—':Math.round(v*100)+'%';};
  var clvv=function(v){return v==null?'—':(v>0?'+':'')+(+v).toFixed(1)+'pp';};
  var row=function(label,x,hint){ if(!x||!x.n) return '';
    return '<tr><td style="padding:6px 10px;border-bottom:1px solid #21262d">'+label+(hint?' <span class="pw-mut" style="font-size:10.5px">'+hint+'</span>':'')+'</td>'
      +'<td style="padding:6px 10px;text-align:right;border-bottom:1px solid #21262d;font-variant-numeric:tabular-nums">'+x.n+'</td>'
      +'<td style="padding:6px 10px;text-align:right;border-bottom:1px solid #21262d;font-weight:800;color:'+clvCol(x.avgClv)+'">'+clvv(x.avgClv)+'</td>'
      +'<td style="padding:6px 10px;text-align:right;border-bottom:1px solid #21262d">'+pctv(x.posRate)+'</td>'
      +'<td style="padding:6px 10px;text-align:right;border-bottom:1px solid #21262d;color:var(--muted)">'+clvv(x.avgClv30)+'</td></tr>';
  };
  var head='<tr style="color:var(--muted);font-size:11px"><th style="text-align:left;padding:6px 10px">Kriterium</th><th style="text-align:right;padding:6px 10px">n</th><th style="text-align:right;padding:6px 10px">Ø Fwd-CLV</th><th style="text-align:right;padding:6px 10px">% positiv</th><th style="text-align:right;padding:6px 10px">Ø @30min</th></tr>';
  var bs=b.bySize||{};
  var body=row('<b>Alle</b>',b.alle)
    +row('🔥 scharfe Wallet',b.sharp)
    +row('🎯 Value-Zone',b.valueZone,'25–75¢')
    +row('🏦 reifer Markt',b.mature,'≥$50K')
    +row('✅ nicht-chasing',b.notChasing)
    +row('🔴 chasing',b.chasing,'Nachlauf')
    +row('$25k+',bs['25k+'])+row('$10–25k',bs['10-25k'])+row('$5–10k',bs['5-10k'])+row('$2–5k',bs['2-5k']);
  var kpi='<div style="display:flex;gap:10px;flex-wrap:wrap;margin:4px 0 12px">'
    +_pwLiveKpi(String(rec.settled),'abgerechnet','#4cc2ff')
    +_pwLiveKpi(String(rec.open||0),'offen','#a78bfa')
    +_pwLiveKpi(clvv(b.alle&&b.alle.avgClv),'Ø Forward-CLV',clvCol(b.alle&&b.alle.avgClv))+'</div>';
  return intro+kpi
    +'<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12.5px"><thead>'+head+'</thead><tbody>'+body+'</tbody></table></div>'
    +'<div style="font-size:11px;color:var(--muted);margin-top:10px">Stufe 1 — misst nur. Sobald ein Bucket klar positives Ø CLV mit genug n zeigt, wird das Kriterium zum Filter. „Ø @30min" = Preisbewegung 30 Min nach Einstieg.</div></section>';
}
function _pwLiveInflow(key){
  const a=_pwCache&&_pwCache.broadLiveHist&&_pwCache.broadLiveHist[key];
  if(!Array.isArray(a)||a.length<2) return null;
  const v2=Number(a[a.length-1].v), v1=Number(a[a.length-2].v);
  if(!isFinite(v2)||!isFinite(v1)) return null;
  const d=v2-v1; return d>0?d:0;
}
function _pwPregameWhales(key){
  const c=_pwCache&&_pwCache.broadLive&&_pwCache.broadLive[key];
  const set=new Set();
  if(c&&Array.isArray(c.whales)) c.whales.forEach(w=>{ if(w&&w.wallet) set.add(String(w.wallet).toLowerCase()); });
  return set;
}
function _pwLiveAge(m){ const c=m&&m.capturedAt?Date.parse(m.capturedAt):NaN; return isNaN(c)?null:Math.max(0,(Date.now()-c)/60000); }
function _pwLiveKpi(v,l,c){
  return '<div style="flex:1;min-width:120px;background:var(--card,#161b22);border:1px solid #21262d;border-radius:10px;padding:9px 12px">'
    +'<div style="font-size:19px;font-weight:800;color:'+c+'">'+v+'</div>'
    +'<div style="font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em">'+l+'</div></div>';
}
function _pwLiveCard(x){
  const k=x.k, m=x.m;
  const oc=Object.entries(m.shares||{}).map(([name,usd])=>({name,usd:Number(usd)||0}));
  const tot=oc.reduce((s,o)=>s+o.usd,0)||1; oc.sort((a,b)=>b.usd-a.usd);
  const fav=oc[0]||{name:'—',usd:0}, favPct=Math.round(fav.usd/tot*100);
  const favPrice=(m.prices&&m.prices[fav.name]!=null)?Math.round(m.prices[fav.name]*100)+'¢':'—';
  const cols=['#4cc2ff','#f5c518','#ff5d5d'];
  const seg=oc.slice(0,3).map((o,i)=>'<i style="display:inline-block;height:100%;width:'+Math.round(o.usd/tot*100)+'%;background:'+cols[i]+'" title="'+_pwEsc(o.name)+' '+Math.round(o.usd/tot*100)+'%"></i>').join('');
  const ic=_pwCatOf(m.league)[1];
  const label=_pwEventLabel(k, oc.map(o=>o.name), m.league);
  const match='<a href="https://polymarket.com/event/'+encodeURIComponent(k)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681">'+label+' <span style="color:#a78bfa">↗</span></a>';
  const inflow=(x.inflow!=null && x.inflow>0)?'<span style="color:#a78bfa;font-weight:700">+'+_pwUsd(x.inflow)+' seit letztem Scan</span>':'';
  const liveBadge='<span style="font-size:9px;font-weight:800;color:#f85149;border:1px solid rgba(248,81,73,.5);border-radius:5px;padding:0 5px;margin-left:6px">● LIVE</span>';
  const pre=_pwPregameWhales(k);
  const _wc=w=>{ if(!w||!w.wallet) return null; const sc=_pwWalletScore(w.wallet); return {isNew:!pre.has(String(w.wallet).toLowerCase()), sc, sharp:_pwIsSharpScore(sc)}; };
  const wh=(m.whales||[]).slice().map(w=>({w,c:_wc(w)})).filter(o=>o.c)
    .sort((a,b)=>((b.c.sharp&&b.c.isNew?1:0)-(a.c.sharp&&a.c.isNew?1:0)) || ((b.c.sharp?1:0)-(a.c.sharp?1:0)) || (Number(b.w.usd)||0)-(Number(a.w.usd)||0))
    .map(({w,c})=>{
    const sharpLive=c.sharp&&c.isNew;
    const trk=(c.sc&&c.sc.n>=4)?' <span style="color:'+(c.sc.avgClv>0?'#3fb950':'#f85149')+';font-weight:700;font-size:11px">'+(c.sc.avgClv>=0?'+':'')+c.sc.avgClv.toFixed(1)+'pp</span> <span class="pw-mut" style="font-size:10.5px">'+Math.round(c.sc.hit*100)+'% · n'+c.sc.n+'</span>':'';
    let tag='';
    if(sharpLive) tag='<span title="bewiesen scharfe Wallet, live eingestiegen (vor Anpfiff nicht im Top-4)" style="font-size:9px;font-weight:800;color:#3fb950;border:1px solid rgba(63,185,80,.55);border-radius:5px;padding:0 4px;margin-left:6px">🔥 scharf live rein</span>';
    else if(c.sharp) tag='<span title="bewiesen scharfe Wallet (Track-Record)" style="font-size:9px;font-weight:800;color:#3fb950;border:1px solid rgba(63,185,80,.45);border-radius:5px;padding:0 4px;margin-left:6px">🔥 scharf</span>';
    else if(c.isNew) tag='<span title="im Live-Top-4, vor Anpfiff NICHT drin — live eingestiegen" style="font-size:9px;font-weight:800;color:#f85149;border:1px solid rgba(248,81,73,.5);border-radius:5px;padding:0 4px;margin-left:6px">🔴 live rein</span>';
    const avg=(w.avgPrice!=null && isFinite(w.avgPrice))?' @'+Math.round(w.avgPrice*100)+'¢':'';
    return '<div style="display:flex;align-items:center;gap:8px;font-size:12px;padding:3px 0'+(sharpLive?';background:rgba(63,185,80,.07);border-radius:6px;padding-left:6px;padding-right:6px':'')+'">'
      +'<a href="'+_pwLink(w.wallet)+'" target="_blank" rel="noopener" class="pw-wl" style="color:#a78bfa">'+_pwWallet(w.wallet)+'</a>'
      +'<span style="color:var(--muted)">auf</span> <b style="color:#4cc2ff">'+_pwEsc(w.side||'—')+'</b>'+trk
      +'<span style="margin-left:auto;font-weight:800">'+_pwUsd(w.usd)+avg+'</span>'+tag+'</div>';
  }).join('');
  return '<div style="background:var(--card,#161b22);border:1px solid #21262d;border-radius:12px;padding:12px 14px;margin-bottom:10px">'
    +'<div style="font-size:13.5px;font-weight:700;margin-bottom:7px">'+ic+' '+match+liveBadge+'</div>'
    +'<div style="height:9px;border-radius:5px;overflow:hidden;background:#0d1117;display:flex;margin-bottom:6px">'+seg+'</div>'
    +'<div style="font-size:12px;color:var(--muted);margin-bottom:'+(wh?'9px':'0')+'">Geld auf <b style="color:#4cc2ff">'+_pwEsc(fav.name)+'</b> '+favPct+'% <span style="color:#6e7681">('+favPrice+')</span> · '+_pwUsd(m.totalUsd)+(inflow?' · '+inflow:'')+'</div>'
    +(wh?'<div style="border-top:1px solid #21262d;padding-top:7px">'+wh+'</div>':'')
    +'</div>';
}
function _pwLiveWhales(){
  const live=_pwCache&&_pwCache.broadLiveNow;
  const intro='<section class="pw-sec"><div class="pw-sec-head">'
    +'<span class="pw-kicker">⚡ LIVE — Geld & Wallets auf laufenden Spielen</span>'
    +'<span class="pw-sec-note">nur In-Play-Märkte · frischer Zufluss + Whales, die JETZT reingehen · alle ~5 Min</span></div>';
  let rows=(live?Object.entries(live):[]).map(e=>({k:e[0],m:e[1]}))
    .filter(x=>x.m && x.m.shares && (x.m.totalUsd||0)>=5000 && _pwSportPass(x.m.league) && !_pwLiveDecided(x.m) && !_pwKoStale(x.m) && !_pwLiveGone(x.m));
  if(!rows.length){
    const _sm=_pwLiveStaleMin(), _had=live&&Object.keys(live).length;
    const _stale=(_sm!=null&&_sm>20&&_had);
    const _msg=_stale
      ? 'Kein <b>frischer</b> Live-Stand — letzte Erfassung vor '+(_sm>=120?Math.round(_sm/60)+' h':_sm+' Min')+'. Die erfassten Spiele sind durch; der Live-Scan (Mac-Runner, alle ~5 Min) lief zuletzt nicht. Sobald er wieder läuft, stehen hier laufende Spiele.'
      : 'Gerade keine laufenden Märkte mit nennenswertem Geld. Die Live-Erfassung läuft am Mac-Runner (alle ~5 Min) — sobald Esport/Tennis/… live ist und Geld drauf liegt, steht hier was.';
    return intro+'<div class="pw-none"'+(_stale?' style="border:1px solid #7d4b16;background:#2b1d0e;color:#e3b341"':'')+'>'+_msg+'</div></section>';
  }
  rows.forEach(x=>{ x.inflow=_pwLiveInflow(x.k); x.vol=x.m.totalUsd||0;
    const pre=_pwPregameWhales(x.k); let sl=0,nw=0;
    (x.m.whales||[]).forEach(w=>{ if(!w||!w.wallet) return; const isNew=!pre.has(String(w.wallet).toLowerCase()); if(isNew){ nw++; if(_pwIsSharpScore(_pwWalletScore(w.wallet))) sl++; } });
    x.sharpLiveN=sl; x.newN=nw; });
  rows.sort((a,b)=>((b.sharpLiveN>0?1:0)-(a.sharpLiveN>0?1:0)) || (b.inflow||0)-(a.inflow||0) || b.vol-a.vol);
  const totVol=rows.reduce((s,x)=>s+x.vol,0);
  const nNew=rows.reduce((s,x)=>s+x.newN,0), nSharp=rows.reduce((s,x)=>s+x.sharpLiveN,0);
  const kpi='<div style="display:flex;gap:10px;flex-wrap:wrap;margin:4px 0 12px">'
    +_pwLiveKpi(String(rows.length),'laufende Märkte','#4cc2ff')
    +_pwLiveKpi(_pwUsd(totVol),'Volumen live','#199e70')
    +_pwLiveKpi(String(nSharp),'scharf live rein','#3fb950')
    +_pwLiveKpi(String(nNew),'Wallets live rein','#f85149')+'</div>';
  const ages=rows.map(x=>_pwLiveAge(x.m)).filter(a=>a!=null);
  const maxAge=ages.length?Math.round(Math.max.apply(null,ages)):null;
  const fresh=maxAge!=null?('<div style="font-size:11px;color:'+(maxAge>20?'#f2a6a6':'var(--muted)')+';margin:-6px 0 12px">Live-Stand vor '+(maxAge<1?'<1':maxAge)+' Min'+(maxAge>20?' — der Live-Scan lief länger nicht (GitHub-Takt)':'')+'</div>'):'';
  const body=rows.slice(0,30).map(_pwLiveCard).join('');
  return intro+kpi+fresh+body+'</section>';
}

function _pwMoveFor(key){
  const arr=_pwCache&&_pwCache.broadHist&&_pwCache.broadHist[key];
  if(!Array.isArray(arr)||arr.length<2) return null;
  const latest=arr[arr.length-1], base=arr[0], prev=arr[arr.length-2];
  let best=null;
  for(const s in (latest.p||{})){ const p1=base.p&&base.p[s], p2=latest.p[s];
    if(typeof p1!=='number'||typeof p2!=='number') continue;
    const move=(p2-p1)*100, step=(prev&&typeof prev.p[s]==='number')?(p2-prev.p[s])*100:move;
    if(!best||move>best.move) best={side:s,move,step}; }
  if(!best) return null;
  best.steam=(best.step>0)===(best.move>0)&&Math.abs(best.step)>=0.3;
  return best;
}
// 07.08.2026 (Lucas: „wenn der Poly-Preis nach dem Alert gegen uns dreht, muss der Tick raus"): Umkehr-
// Erkennung rein aus Poly-Preisen (kein neuer Anbieter noetig). Wie weit ist die EMPFOHLENE Seite von
// ihrem Hoch im Fenster zurueckgefallen? Der Markt ist das schnellste Signal — dreht er hart gegen unser
// (oft traeges) Geld-Signal, entwerten wir den Play: erst warnen, bei starker Umkehr ganz raus.
const PW_ADVERSE_WARN_PP = 6;    // ab so viel pp Rueckfall vom Hoch: Warn-Badge + Conviction runter
const PW_ADVERSE_KILL_PP = 12;   // ab so viel pp: Play raus aus Box + Uebersicht (verdict SKIP)
const PW_ADVERSE_MAX_CUR = 0.70; // nur werten, wenn die Seite nicht mehr klar fuehrt (<=70%) — ein Dip beim Favoriten ist kein Dreh
function _pwAdverseFor(key, side){
  const arr=_pwCache&&_pwCache.broadHist&&_pwCache.broadHist[key];
  if(!Array.isArray(arr)||arr.length<2||!side) return null;
  let peak=-1, cur=null;
  for(const s of arr){ const p=s&&s.p&&s.p[side];
    if(typeof p==='number'){ if(p>peak)peak=p; cur=p; } }
  if(cur==null||peak<0) return null;
  return {fromPeak:(peak-cur)*100, cur, peak};
}
function _pwSharpSideFor(m){
  const bySide={};
  for(const wh of (m.whales||[])){ const sc=_pwWalletScore(wh.wallet);
    if(_pwIsSharpScore(sc)&&(Number(wh.usd)||0)>=PW_SHARP_MIN_USD) bySide[wh.side]=(bySide[wh.side]||0)+(Number(wh.usd)||0); }
  let best=null,bmax=0; for(const s in bySide) if(bySide[s]>bmax){bmax=bySide[s];best=s;}
  return best;
}
function _pwLeagueMoneyRow(league){
  const bl=_pwCache&&_pwCache.moneyBroad&&_pwCache.moneyBroad.byLeague;
  if(!Array.isArray(bl)||!league) return null;
  const up=String(league).toUpperCase();
  return bl.find(x=>String(x.league||'').toUpperCase()===up) || null;
}
function _pwLeagueMoneyVerdict(league){ const r=_pwLeagueMoneyRow(league); return r?r.verdict:null; }
// Ab so vielen ausgewerteten Spielen gilt ein Liga-Urteil („Geld schaerfer" / „Preis besser") als
// belegt. Darunter ist es eine Behauptung — reale Eintraege haben teils n=5, und aus fuenf
// Spielen laesst sich nicht ableiten, ob in einer Liga das Geld oder der Preis naeher dran ist.
const PW_GVP_MIN_N=10;
// (01.08.2026, Lucas) Wiederverwendbare Play-Rangliste — Kern für „🔥 Heute wetten" UND die
// Übersicht-Box. limit=0 → alle. useSportPass steuert den Sport-Filter (Übersicht: aus).
var PW_LIVE_MAX_PRICE = 0.77;   // 15.08.2026 (Lucas): wie Live-Watch — live > 77¢ (Quote <1.30) = fast entschieden, kein Value
var PW_LIVE_FRESH_MAX_MIN = 45;   // 16.08.2026 (Lucas): Live-Snapshot älter als das = der Scan führt das Spiel nicht mehr -> vorbei/eingefroren -> nicht als Live-Play zeigen (fertige Esport-Spiele hingen 1h+ in den Top-Wetten)
function _pwLiveGone(m){ var a=(typeof _pwLiveAge==='function')?_pwLiveAge(m):null; return a!=null && a>PW_LIVE_FRESH_MAX_MIN; }
var PW_LIVE_FLIP_GAP = 0.20;   // 16.08.2026 (Lucas): live gekippt — Shares-Seite liegt >=20pp hinter dem Preis-Favoriten => Markt gegen die Positionsmehrheit, Play raus
function _pwTopPlays(limit, live, useSportPass){
  live = live || (_pwCache && _pwCache.broadLive) || {};
  const all=[];
  for(const [k,m] of Object.entries(live)){
    if(!m||m.resolved!=null||_pwKoStale(m)) continue;
    // 16.08.2026 (Lucas): fertiges Live-Spiel raus. Ein laut close-Freeze schon laufendes Spiel (realHtk<0)
    // gilt nur als aktuell, wenn der LIVE-Scan es noch FRISCH führt — sonst vorbei/eingefroren (blockierte Platz).
    if((_pwRealHtk(m)||0)<0){ var _lnm=_pwCache&&_pwCache.broadLiveNow&&_pwCache.broadLiveNow[k]; if(!_lnm||_pwLiveGone(_lnm)) continue; }
    if(_pwSportCategory(m.league, m.sport)==='Sonstige') continue;   // kein Politik/Krypto/Sonstiges in die Play-Liste
    if(useSportPass && !_pwSportPass(m.league, m.sport)) continue;
    const r=_pwShortlistScore(k,m);
    if(r&&r.verdict==='BET'){
      const _lv=(r.htk!=null&&r.htk<0);   // 15.08.2026 (Lucas): live fast entschieden (>77¢) = kein Value, wie Live-Watch
      if(_lv&&typeof r.price==='number'&&r.price>PW_LIVE_MAX_PRICE) continue;
      all.push(r);   // 13.08.2026 (Lucas): FADE raus aus Public-Plays — nur BET wird promotet
    }
  }
  // 14.08.2026 (Lucas): dasselbe Spiel taucht auf Polymarket manchmal unter zwei Event-Slugs auf
  // (Basis + "-more-markets") -> exakt gleicher Pick 2x in den Play-Boxen. Nach normalisiertem
  // Spiel+Seite (Key ohne "-more-markets") dedupen, staerkste Conviction gewinnt.
  const _seen={}, _dedup=[];
  for(const r of all){
    const gk=String(r.key||'').replace(_PW_PROP_SUFFIX_RX,'');   // 16.08.2026 (Lucas): Basis + -more-markets/-exact-score = EIN Spiel -> ein Pick (staerkste Conviction)
    if(_seen[gk]==null){ _seen[gk]=_dedup.length; _dedup.push(r); }
    else if((+r.conv||0)>(+_dedup[_seen[gk]].conv||0)){ _dedup[_seen[gk]]=r; }
  }
  _dedup.sort((a,b)=>b.conv-a.conv);
  return limit?_dedup.slice(0,limit):_dedup;
}

// (01.08.2026, Lucas) PUBLIC-KANDIDAT „Top-Play" — hart gegatet, NUR Vorschau (sendet nicht).
// Nur was wir öffentlich vertreten würden: Conviction≥7 (Skala neu, = altes ≥9) + bewiesene Wallet (n≥8 & ≥55% Treffer)
// + echte Geld-Mehrheit ≥60% + Sport. Sport-Filter der View wird ignoriert (public = alle Sportarten).
const PW_PUBLIC_MIN_CONV=6;   // 29.08.2026: 7 → 6, siehe unten (Wallet-Neugewichtung, „D")
// Zugriff fuer Tests/Diagnose: ein `const` im Skript-Scope ist keine window-Property, eine
// Funktionsdeklaration schon. Damit koennen Tests gegen das Gate pruefen statt gegen eine Zahl.
function _pwPublicMinConv(){ return PW_PUBLIC_MIN_CONV; }
function _pwPublicTopPlays(){
  // 24.08.2026 (Lucas): gesperrte Sportarten fliegen HIER raus, nicht erst beim Setzen — der
  // oeffentliche Track-Record ist das Produkt. Bisher gingen 13 MLB-Plays als Public-Kandidat
  // durch. Im Scan/Papier-Depot bleiben sie (Beobachtung), nur nicht mehr im Schaufenster.
  // 29.08.2026 (Lucas-Checkup, „D"): war ≥7. Die Wallet-Neugewichtung nimmt der Skala rund einen
  // Punkt — und zwar genau dort, wo die Wallet den Score getragen hat. Bliebe das Gate auf 7, waere
  // aus „Wallets zaehlen weniger" unbemerkt „das Schaufenster bleibt leer" geworden: gemessen am
  // Stand von heute fielen alle drei Public-Kandidaten weg (INOX, Kashima, MOUZ — 7 → 6). Mit 6
  // stehen exakt dieselben drei drin, nur setzt sich ihr Score jetzt anders zusammen. Die Strenge
  // bleibt, die Gewichtung aendert sich — das war der Auftrag.
  // 01.09.2026: die Bedingung stand hier ausgeschrieben UND in _pwTermIsPublic. Eine Quelle.
  return _pwTopPlays(0,false,false).filter(r=> !_pwBetBlocked(r) && _pwTermIsPublic(r));
}

// (01.08.2026, Lucas) PUBLIC-KANDIDAT „Whale-Watch" — repliziert das Public-Gate von poly_whale_watch.py
// auf walletTrack.open, NUR Vorschau. Schwelle: untracked ≥$100K / tracked ≥$25K + Sport + Preis 3–97¢.
const PW_WHALE_PUB_UNTRACKED=100000, PW_WHALE_PUB_TRACKED=25000;
function _pwWhalePublicCandidates(){
  const wt=_pwCache&&_pwCache.walletTrack; const op=wt&&wt.open, sc=(wt&&wt.scores)||{};
  if(!op) return [];
  const opens=Array.isArray(op)?op:Object.values(op);
  const out=[];
  for(const pos of opens){
    if(!pos) continue;
    if(_pwSportCategory(pos.league, pos.sport)==='Sonstige') continue;   // nur Sport
    const usd=Number(pos.usd)||0; if(usd<=0) continue;
    const price=Number(pos.lastPrice!=null?pos.lastPrice:pos.entryPrice);
    if(!(price>=0.03 && price<=0.97)) continue;               // kein fast-sicher, kein Staub
    const raw=sc[pos.wallet]; const tracked=!!(raw&&raw.n&&raw.n>=PW_SHARP_MIN_N);
    const thr=tracked?PW_WHALE_PUB_TRACKED:PW_WHALE_PUB_UNTRACKED;
    if(usd<thr) continue;
    const hit=raw&&raw.n?(raw.wins||0)/raw.n:null, clv=raw&&raw.n?raw.clvSumPP/raw.n:null;
    out.push({wallet:pos.wallet,key:pos.key,side:pos.side,league:pos.league,usd,price,
              entryPrice:Number(pos.entryPrice),tracked,n:raw?raw.n:0,hit,clv,
              match:_pwMatchLabel(pos.key)});
  }
  out.sort((a,b)=>b.usd-a.usd);
  return out;
}

// Schlanker Loader für die Übersicht-Box: lädt nur die Dateien, die der Scorer braucht, und
// füllt _pwCache NUR wo noch nichts drin ist (der volle Poly-Tab-Loader überschreibt später sauber).
let _pwPlaysLoadedTs=0;
function _pwEnsurePlaysData(cb){
  // 11.08.2026 (Lucas): Live-Dateien mitladen, damit die Uebersicht das Live-Poly-Element ohne den
  // vollen Poly-Tab-Load bekommt. Guard verlangt jetzt AUCH broadLiveNow.
  const _ready=()=> _pwCache && _pwCache.broadLive && _pwCache.broadLiveNow;
  if(_ready()){ cb&&cb(); return; }
  if(_pwPlaysLoadedTs && (Date.now()-_pwPlaysLoadedTs)<120000 && _ready()){ cb&&cb(); return; }
  const b='?t='+Date.now();
  const jf=u=>_pwJson(u,b);
  // 29.08.2026 (Lucas: „soll man das mit lernen und neu gewichten") — poly_shortlist_track.json
  // FEHLTE hier. Der schlanke Loader bedient die Uebersichts-Kachel „Heute spielenswert" UND
  // scripts/emit_shortlist.mjs (also das Papier-Depot und den Telegram-Push). Ohne den Track gab
  // _pwComboFor() null zurueck -> _pwCalibConv stieg stumm aus -> die Kalibrierung lief AUSSCHLIESSLICH
  // im Wallets-Tab, wo der grosse Loader sie mitlaedt.
  //
  // Zwei Folgen, beide unsichtbar: derselbe Play trug auf der Uebersicht eine andere Conviction als
  // im Wallets-Tab daneben. Und der Steam-Alleingang, den der Lerner mit -3 abstraft (n=19, -43% ROI),
  // ging ungebremst ins Papier-Depot und in den Push — genau dorthin, wo es zaehlt.
  //
  // Rueckkopplung ist unkritisch: die calib+/calib--Tags landen zwar in signals, aber _PW_CALIB_CORE
  // filtert sie beim Eimer-Bau raus. Der Lerner faerbt seine eigene Datenbasis also nicht ein.
  Promise.all([jf('poly_money_broad_close.json'),jf('poly_money_broad_history.json'),
               jf('poly_money_broad.json'),jf('poly_wallet_track.json'),jf('poly_cross_sport.json'),
               jf('poly_money_broad_live.json'),jf('poly_money_broad_live_history.json'),
               jf('money_map.json'),jf('poly_shortlist_track.json')])
   .then(([broadLive,broadHist,moneyBroad,walletTrack,crossSport,broadLiveNow,broadLiveHist,moneyMap,shortlistTrack])=>{
     if(!_pwCache) _pwCache={};
     if(!_pwCache.broadLive)     _pwCache.broadLive=broadLive;
     if(!_pwCache.broadHist)     _pwCache.broadHist=broadHist;
     if(!_pwCache.moneyBroad)    _pwCache.moneyBroad=moneyBroad;
     if(!_pwCache.walletTrack)   _pwCache.walletTrack=walletTrack;
     if(!_pwCache.crossSport)    _pwCache.crossSport=crossSport;
     if(!_pwCache.broadLiveNow)  _pwCache.broadLiveNow=broadLiveNow;
     if(!_pwCache.broadLiveHist) _pwCache.broadLiveHist=broadLiveHist;
     if(!_pwCache.moneyMap)      _pwCache.moneyMap=moneyMap;   // 21.08.2026 (Lucas): Betfair-Geld-Gegencheck
     if(!_pwCache.shortlistTrack)_pwCache.shortlistTrack=shortlistTrack;   // 29.08.2026: Lern-Basis der Kalibrierung
     _pwPlaysLoadedTs=Date.now();
     cb&&cb();
   }).catch(()=>{ cb&&cb(); });
}

// ── Uebersicht-Feeder (11.08.2026, Lucas): Top-N Live-Whales + Top-N Live-Zufluss fuer das
//    Vollbreiten-Element auf der Startseite. Nutzen dieselbe Sharp-Logik/Labels wie der Live-Tab.
// 12.08.2026 (Lucas): "allein die Betraege" — ein $475-Einstieg ist kein Whale. Boden wie die Pre-Game-
// Whale-Kachel ($10K), und je Markt nur EIN Eintrag (kein 4x dasselbe Spiel), sortiert nach Groesse.
const PW_LIVE_WHALE_MIN_USD = 10000;
const PW_LIVE_INFLOW_MIN_USD = 10000;   // 12.08.2026 (Lucas): +$472 Zufluss ist kein Signal -> nur nennenswerte frische Bewegung
function _pwLiveTopWhales(n){
  const live=_pwCache&&_pwCache.broadLiveNow; if(!live) return [];
  const byMarket={};   // Dedup: je Markt der groesste Whale
  Object.entries(live).forEach(([k,m])=>{
    if(!m||!m.shares||(Number(m.totalUsd)||0)<5000||!_pwSportPass(m.league)||_pwLiveDecided(m)||_pwKoStale(m)||_pwLiveGone(m)) return;
    const pre=_pwPregameWhales(k);
    const label=_pwEventLabel(k,Object.keys(m.shares||{}),m.league);
    (m.whales||[]).forEach(w=>{
      if(!w||!w.wallet) return;
      const usd=Number(w.usd)||0;
      if(usd < PW_LIVE_WHALE_MIN_USD) return;   // nur echte Betraege
      const sc=_pwWalletScore(w.wallet), sharp=_pwIsSharpScore(sc), isNew=!pre.has(String(w.wallet).toLowerCase());
      const _sp=(m.prices&&m.prices[w.side]!=null&&isFinite(Number(m.prices[w.side])))?Math.round(Number(m.prices[w.side])*100):null;
      const e={key:k,label:label,league:m.league,sport:m.sport,side:w.side||'—',usd:usd,wallet:w.wallet,
               sharp:sharp,isNew:isNew,sharpLive:sharp&&isNew,avgPrice:w.avgPrice,price:_sp,
               sc:(sc&&sc.n>=4)?{avgClv:sc.avgClv,hit:sc.hit,n:sc.n}:null};
      const cur=byMarket[k];
      if(!cur || e.usd>cur.usd) byMarket[k]=e;   // je Markt nur den groessten
    });
  });
  const out=Object.values(byMarket);
  out.sort((a,b)=>(b.usd-a.usd));   // groesstes Live-Geld zuerst
  return out.slice(0,n||5);
}
function _pwLiveTopInflow(n){
  const live=_pwCache&&_pwCache.broadLiveNow; if(!live) return [];
  const rows=Object.entries(live).map(e=>({k:e[0],m:e[1]}))
    .filter(x=>x.m&&x.m.shares&&(Number(x.m.totalUsd)||0)>=5000&&_pwSportPass(x.m.league)&&!_pwLiveDecided(x.m)&&!_pwKoStale(x.m));
  rows.forEach(x=>{ x.inflow=_pwLiveInflow(x.k)||0; });
  const out=rows.filter(x=>x.inflow>=PW_LIVE_INFLOW_MIN_USD);   // nur nennenswerter Zufluss (kein +$472-Rauschen)
  out.sort((a,b)=>(b.inflow-a.inflow)||((Number(b.m.totalUsd)||0)-(Number(a.m.totalUsd)||0)));
  return out.slice(0,n||5).map(x=>{
    const oc=Object.entries(x.m.shares||{}).map(e=>({name:e[0],usd:Number(e[1])||0})).sort((a,b)=>b.usd-a.usd);
    const tot=oc.reduce((s,o)=>s+o.usd,0)||1, fav=oc[0]||{name:'—',usd:0};
    return {key:x.k,label:_pwEventLabel(x.k,oc.map(o=>o.name),x.m.league),league:x.m.league,sport:x.m.sport,
            inflow:x.inflow,totalUsd:Number(x.m.totalUsd)||0,favName:fav.name,favPct:Math.round(fav.usd/tot*100),
            favPrice:(x.m.prices&&x.m.prices[fav.name]!=null)?Math.round(x.m.prices[fav.name]*100):null};
  });
}
function _pwLiveStaleMin(){
  const live=_pwCache&&_pwCache.broadLiveNow; if(!live) return null;
  let newest=null;
  for(const k in live){ const c=live[k]&&live[k].capturedAt?Date.parse(live[k].capturedAt):NaN;
    if(!isNaN(c)&&(newest==null||c>newest)) newest=c; }
  return newest==null?null:Math.max(0,Math.round((Date.now()-newest)/60000));
}
if(typeof window!=='undefined'){ window._pwLiveTopWhales=_pwLiveTopWhales; window._pwLiveTopInflow=_pwLiveTopInflow; window._pwLiveStaleMin=_pwLiveStaleMin; }

// Sharp-Seite eines Markts aus poly_wallet_track.open (01.08.2026, Lucas) — DIE Brücke zwischen
// „hunderte Wallet-Daten" und „was wetten": nur BEWÄHRTE Wallets (n≥Schwelle, CLV+ ODER ≥50% Treffer)
// mit AKTUELL offener Position; die Seite mit dem meisten scharfen Geld gewinnt. broadLive-Märkte
// tragen kein .whales-Feld → ohne diesen Key-Join würde das Sharp-Signal nie feuern.
function _pwSharpSideForKey(key){
  const wt=_pwCache&&_pwCache.walletTrack; const op=wt&&wt.open; if(!op||!key) return null;
  const opens=Array.isArray(op)?op:Object.values(op);
  const bySide={};
  for(const pos of opens){
    if(!pos||pos.key!==key) continue;
    const usd=Number(pos.usd)||0; if(usd<PW_SHARP_MIN_USD) continue;   // 07.08.2026 (Lucas): Mini-Einsaetze ($2-6) raus
    const sc=_pwWalletScore(pos.wallet); if(!sc||sc.n<PW_SHARP_MIN_N) continue;
    if(!_pwIsSharpScore(sc)) continue;   // 07.08.2026 (Lucas): beide Achsen streng     // bewährt: schlägt Linie ODER gewinnt
    bySide[pos.side]=(bySide[pos.side]||0)+usd;
  }
  let best=null,bmax=0; for(const sd in bySide) if(bySide[sd]>bmax){bmax=bySide[sd];best=sd;}
  return best;
}

// Wallet-QUALITÄT je Schlüssel (01.08.2026, Lucas „Trefferquote mit rein"): statt flach „scharfe Wallet drin"
// die Seite mit dem stärksten bewiesenen Geld zurückgeben PLUS deren aggregierte Bilanz (n/Treffer/CLV/P&L,
// usd-gewichtet). Erlaubt eine qualitätsskalierte Gewichtung + eine ehrliche „Warum"-Zeile mit Record.
function _pwSharpInfoForKey(key){
  const wt=_pwCache&&_pwCache.walletTrack; const op=wt&&wt.open, sc=wt&&wt.scores;
  if(!op||!sc||!key) return null;
  const opens=Array.isArray(op)?op:Object.values(op);
  const bySide={};  // side -> {usd, n, wins, pnl, clvUsd, count}
  for(const pos of opens){
    if(!pos||pos.key!==key) continue;
    const usd=Number(pos.usd)||0; if(usd<PW_SHARP_MIN_USD) continue;   // 07.08.2026 (Lucas): Mini-Einsaetze ($2-6) raus
    const raw=sc[pos.wallet]; if(!raw||!raw.n||raw.n<PW_SHARP_MIN_N) continue;
    const avgClv=raw.clvSumPP/raw.n, hit=(raw.wins||0)/raw.n;
    // 01.09.2026: hier stand `if(!_pwIsSharpScore(...)) continue;` — der Schalter. Jetzt der
    // Regler: unbelegt (0) faellt weiterhin raus, alles darueber traegt anteilig bei.
    const grade=_pwSharpGrade({n:raw.n,avgClv:avgClv,hit:hit,wins:(raw.wins||0),
                               pnl:Number(raw.pnl)||0,
                               pnlKnown:(typeof raw.pnl==='number' && isFinite(raw.pnl))});
    if(grade<=0) continue;
    const b=bySide[pos.side]||(bySide[pos.side]={usd:0,n:0,wins:0,pnl:0,clvUsd:0,count:0,gradeUsd:0});
    b.usd+=usd; b.n+=raw.n; b.wins+=(raw.wins||0); b.pnl+=(Number(raw.pnl)||0);
    b.clvUsd+=avgClv*usd; b.gradeUsd+=grade*usd; b.count++;
  }
  let side=null,smax=0; for(const sd in bySide) if(bySide[sd].usd>smax){smax=bySide[sd].usd;side=sd;}
  if(!side) return null;
  const b=bySide[side];
  return {side, usd:b.usd, n:b.n, wins:b.wins, hit:b.n?b.wins/b.n:0,
          clv:b.usd?b.clvUsd/b.usd:0, pnl:b.pnl, count:b.count,
          // usd-gewichteter Beleggrad der Seite: 1 = alle bewiesen, <1 = vielversprechend
          grade:b.usd?Math.max(0,Math.min(1,b.gradeUsd/b.usd)):0};
}

// Pinnacle-Kante für einen Markt aus poly_cross_sport.discrepancies (01.08.2026, Lucas).
// disc: {outcome, gapPP, richtung}. gap<0 = Poly zu niedrig → diese Seite backen (Value).
// gap>0 = Poly zu hoch → Gegenseite. Match über den Ausgangsnamen (normalisiert).
function _pwPinnEdgeFor(m, oc){
  const cs=_pwCache&&_pwCache.crossSport; const disc=(cs&&cs.discrepancies)||[];
  if(!disc.length||!oc||!oc.length) return null;
  const norm=x=>String(x==null?'':x).trim().toLowerCase();
  const names=oc.map(o=>o.s);
  let bestHit=null;
  for(const d of disc){
    const idx=names.findIndex(n=>norm(n)===norm(d.outcome));
    if(idx<0) continue;
    if(!bestHit||Math.abs(d.gapPP)>Math.abs(bestHit.gapPP)) bestHit={d,idx};
  }
  if(!bestHit) return null;
  const d=bestHit.d, side=names[bestHit.idx], other=names.find(n=>n!==side)||null;
  return {side, other, gapPP:d.gapPP, back:d.gapPP<0};
}

// 05.08.2026 (Lucas: bei Yes/No sieht man nicht WELCHES Spiel): bei generischen Ausgaengen
// (Yes/No, Over/Under, Draw) sagt der Ausgang nichts ueber das Match -> Spiel aus dem Key ableiten.
function _pwPrettyKey(key){
  const s=String(key||'');
  const m=s.match(/^(.*?)-(\d{4}-\d{2}-\d{2})(?:-(.+))?$/);
  if(m){
    const base=m[1].replace(/[-_]+/g,' ').trim();
    const suf=(m[3]||'').replace(/[-_]+/g,' ').trim();
    return suf ? base+' · '+suf : base;
  }
  return s.replace(/[-_]+/g,' ').trim();
}
const _PW_GENERIC_OUTCOME=/^(yes|no|over|under|the draw|draw|tie|remis|ja|nein)$/i;
// 14.08.2026 (Lucas): zentraler Draw-Filter fuer 3-Weg-Poly-Maerkte. "Draw (A vs. B)" ist ein
// Outcome, kein drittes Team. Fallback: bleiben <2 Namen uebrig, Originalliste behalten (2-Weg unberuehrt).
function _pwNoDraw(names){
  const arr=(names||[]).map(function(n){return String(n);});
  const teams=arr.filter(function(n){return !/^(draw|the draw|unentschieden|remis)\b/i.test(n.trim());});
  return teams.length>=2?teams:arr;
}
function _pwPlayLabel(key,oc){
  const names=(oc||[]).map(o=>String(o.s||'').trim()).filter(Boolean);
  const {teams,base}=_pwResolveTeams(key,names);   // 16.08.2026 (Lucas): Prop-aware, wie _pwEventLabel
  if(teams) return teams.join(' vs ');
  return _pwPrettyKey(key);                         // 16.08.2026 (Lucas): keine Teams -> Slug + Markt-Typ-Hinweis
}
// 21.08.2026 (Lucas: „checken wir ob auf betfair kohle liegt?"): Betfair-Geld-Gegencheck fuer den
// Kanten/Heute-Scorer — symmetrisch zum Betfair-Terminal, das Poly schon als Bestaetigung hat.
// Quelle: money_map.json (matcht Betfair<->Poly je Spiel, inkl. UEFA). Liefert den Betfair-Geld-
// Favoriten fuer DIESES Spiel (auf die Poly-Outcome-Namen gemappt) oder null.
// 21.08.2026 (Lucas #3): Track-kalibrierte Konviktion. Aus poly_shortlist_track.json (settled)
// die reale Performance JE SIGNAL-MIX rechnen und historisch klar -EV Mixe abwerten. Kern-Erkenntnis:
// sharp/steam ALLEIN verlieren stark (-12%/-38% ROI), nur MIT money gewinnen sie.
let _pwComboCache=null, _pwComboRef=null;
// 29.08.2026 (Lucas: „soll man das mit lernen und neu gewichten") — DER STEMPEL.
// Der Cards-Lernloop weigert sich, ueber Engine-Versionen hinweg zu lernen (update_signal_weights.py:
// „nur auf der AKTUELLEN Engine-Version lernen ... so vergiftet ein Fix den Ledger nicht"). Der
// Poly-Track hatte das nicht: die 500 abgerechneten Plays wurden alle unter den ALTEN Gewichten
// bewertet — Wallet-Basis 2,5 statt 1,8, Sharp-Gate n>=4 mit roher Quote statt n>=8 mit Wilson.
// Ohne Stempel wirft der Kalibrierer beide Welten in denselben Topf und lernt aus einer Engine,
// die es nicht mehr gibt.
//
// Diese Zeichenkette hochzaehlen, sobald sich an Gewichten, Schwellen oder dem Sharp-Gate etwas
// aendert — sie ist die Grenze zwischen „das war dieselbe Maschine" und „das war eine andere".
// 29.08.2026b: Saeulen-Neugewichtung (steam 3,0→2,5 · bf 1,5→2,0 · pinn 2,0→1,5 · gvp 2,0→1,0).
// Der Stempel wandert mit — das ist sein einziger Zweck: die 500 Plays davor wurden unter
// anderen Gewichten bewertet und zaehlen fuer den Kalibrierer ab jetzt nur noch halb.
// ⚠️ WANN DER STEMPEL SPRINGT (Regel, 01.09.2026) — er springt bei Aenderungen, die die AUSWAHL
// oder die Bewertung verschieben: Saeulen-Gewichte, Gates, Schwellen, neue Signale. Er springt
// NICHT bei Refactorings, Umbenennungen, UI- oder Textaenderungen. Grund: jeder Sprung setzt die
// Schubladen im Freigabe-Register faktisch zurueck (Alt-Plays zaehlen halb), und eine Schublade
// braucht n=30. Springt der Stempel monatlich, erreicht sie diese 30 nie — dann misst das Register
// dauerhaft nichts. Im Zweifel: NICHT springen und stattdessen messen, ob sich die Verteilung
// ueberhaupt verschoben hat.
// 01.09.2026: springt, weil der Sharp-Beitrag von einem Schalter auf einen Regler umgestellt wurde
// (s. _pwSharpGrade) — das ist eine echte Bewertungsaenderung, keine Kosmetik.
const PW_ENGINE_VERSION='2026-09-01';
// Alt-Plays fliegen NICHT raus, sie zaehlen halb. Grund: was ein Signal-MIX bringt, haengt nur
// zum Teil an unseren Gewichten — dass `steam` allein -43% ROI macht, gilt auch unter der neuen
// Engine. Was sich wirklich geaendert hat, ist die Bedeutung des `sharp`-Tags (das Gate). Halbes
// Gewicht laesst den ROI-Schaetzer stehen und senkt nur das Vertrauen (conf = n/(n+25)) — und der
// Alt-Anteil verwaessert sich von selbst, weil seine n eingefroren ist und die neue waechst.
// Harte Alternative waere n=0 fuer Wochen; das haette die Kalibrierung stillgelegt.
const PW_CALIB_LEGACY_W=0.5;
// 29.08.2026: 'bf' war NICHT im Kern — ausgerechnet das beste Signal im ganzen Track (+26,4% ROI
// ueber n=41). Folge: der Eimer „money" (n=33, +21,1% ROI) war in Wahrheit groesstenteils
// money+bf — `money` allein kommt gewichtsmaessig gar nicht ueber die Schwelle von 3. Der Lerner
// schrieb den Erfolg also dem falschen Signal zu und hat ihn nie dort gesucht, wo er herkam.
const _PW_CALIB_CORE=['money','sharp','steam','pinn','gvp','bf'];
function _pwComboStatsAll(){
  const st=_pwCache&&_pwCache.shortlistTrack&&_pwCache.shortlistTrack.settled;
  if(!st) return null;
  if(_pwComboRef===st && _pwComboCache) return _pwComboCache;
  const core=new Set(_PW_CALIB_CORE), agg={};
  for(const x of st){
    const sigs=(x.signals||[]).filter(t=>core.has(t)).slice().sort();
    const k=sigs.join('+')||'(none)';
    const a=agg[k]||(agg[k]={n:0,nRoh:0,nAlt:0,wins:0,stake:0,pnl:0});
    // Gewicht nach Engine-Version: was unter der aktuellen Maschine entstand, zaehlt voll; was
    // davor lief, halb. nRoh/nAlt bleiben roh mitgezaehlt, damit die Anzeige ehrlich sagen kann,
    // wie viele Plays wirklich dahinterstehen und wie viele davon aus der alten Welt stammen.
    const alt=(x.ev||null)!==PW_ENGINE_VERSION;
    const w=alt?PW_CALIB_LEGACY_W:1;
    a.n+=w; a.nRoh++; if(alt)a.nAlt++;
    if(x.result==='win')a.wins+=w;
    a.stake+=(Number(x.stake)||0)*w; a.pnl+=(Number(x.pnl)||0)*w;
  }
  for(const k in agg){ const a=agg[k]; a.roi=a.stake?a.pnl/a.stake:0; a.hit=a.n?a.wins/a.n:0; }
  _pwComboCache=agg; _pwComboRef=st; return agg;
}
function _pwComboFor(sigs){
  const agg=_pwComboStatsAll(); if(!agg) return null;
  const core=new Set(_PW_CALIB_CORE);
  const k=(sigs||[]).filter(t=>core.has(t)).slice().sort().join('+')||'(none)';
  return agg[k]||null;
}
// Basis-ROI der ganzen Shortlist (agg.all) — Kalibrierung ist RELATIV dazu: ein Mix ueber dem
// Schnitt wird leicht aufgewertet, drunter leicht abgewertet. So bleibt der Durchschnitt stabil,
// nur die Rangfolge schaerft sich. Kein Signal fliegt raus.
function _pwComboBaselineRoi(){
  const a=_pwCache&&_pwCache.shortlistTrack&&_pwCache.shortlistTrack.agg&&_pwCache.shortlistTrack.agg.all;
  return (a&&typeof a.roi==='number')?a.roi:0;
}
// Kontinuierliche, symmetrische Konviktions-Kalibrierung (21.08.2026, Lucas: „automatisch mitlernen
// und weiter gewichten, Signale nicht ganz raus"). Verschiebt conv sanft Richtung realer Mix-Performance,
// gewichtet nach Stichprobe (conf = n/(n+25) → kleine n zaehlen wenig, kein Overfit). Asymmetrisch
// geklammert: mehr Abwertung (-3) als Boost (+2) erlaubt (Risiko-vorsichtig). Gibt {conv,reason,tag}.
// ⚠️ 01.09.2026 — DER LERNER BEOBACHTET NUR NOCH. Lucas: „schau dir das mal an, ob der Lerneffekt
// dort eh greift." Antwort nach Messung: er greift (32% aller Plays wurden angefasst), aber er
// traegt nicht. Walk-Forward ueber `poly_shortlist_track` (jeder Play lernt nur aus seiner eigenen
// Vergangenheit), ab sechs verschiedenen Startpunkten:
//
//     ab Play  ↑ hochgestuft   ↓ abgestuft
//        100    +1,4% (n92)     +8,4% (n53)
//        150    −1,7% (n72)     +8,4% (n39)
//        200    +4,7% (n59)     +6,4% (n38)
//        250    +9,4% (n53)    +12,3% (n30)
//        300   +10,2% (n42)    +25,6% (n21)
//        350    +6,7% (n36)    +38,7% (n10)
//
// SECHS von sechs: die abgestuften Plays schlagen die hochgestuften. Der Grund ist nicht, dass die
// Eimer nichts wissen — ihre REIHENFOLGE haelt ueber die Zeit. Was nicht haelt, ist die GROESSE:
//     bf+money  +52,2% → +9,2%   ·  sharp  −12,3% → −2,5%
// `bf+money` bekam auf Basis von +52% zwei Konviktionsstufen; der wahre Vorwaertswert war +9%,
// richtig waeren ~0,2 Stufen gewesen. Die Formel bemass sich am rohen Punktschaetzer, und
// conf=n/(n+25) daempft nach STICHPROBENGROESSE, nicht danach, wie viel der beobachteten Kante
// Rauschen ist — bei n=60 daempft sie auf 0,7, also praktisch gar nicht.
//
// Die naheliegende Reparatur (Untergrenze statt Punktschaetzer) wurde mitgetestet und hilft NICHT:
// dann stuft der Lerner 318 von 328 Plays ab, weil eine Untergrenze auf verrauschtem ROI fast immer
// unter der Basis liegt. 0/5 in beiden Varianten.
//
// ⭐ Deshalb dieselbe Doktrin wie bei `wertVsPinn` in killer.py: MITSCHREIBEN, NICHT FILTERN.
// Das Lern-Board bleibt vollstaendig — es ist informativ und zeigt, welcher Mix wie laeuft. Aber
// die Conviction wird nicht mehr bewegt, solange nicht belegt ist, dass es hilft. `reason` und
// `tag` bleiben erhalten, damit die Oberflaeche weiter anzeigen KANN, was der Lerner denken wuerde.
// Wiederholbar messen: scripts/calib_walkforward.py — vor jedem Wiedereinschalten laufen lassen.
const PW_CALIB_AKTIV = false;   // auf true erst, wenn der Walk-Forward „hoch schlaegt runter" zeigt

function _pwCalibConv(sigs, conv){
  const cb=_pwComboFor(sigs);
  if(!cb || cb.n<8) return {conv, reason:null, tag:null};
  const base=_pwComboBaselineRoi();
  const conf=cb.n/(cb.n+25);
  const adj=Math.max(-3, Math.min(2, (cb.roi-base)*15*conf));
  const nc=Math.max(1, Math.min(10, Math.round(conv+adj)));
  if(nc===conv) return {conv, reason:null, tag:null};
  const up=nc>conv;
  const grund=(up?'📈':'📉')+' Signal-Mix real '+Math.round(cb.roi*100)+'% ROI (n'+(cb.nRoh||Math.round(cb.n))
          +(cb.nAlt?', '+cb.nAlt+' aus alter Engine':'')+') → '+(up?'+':'')+(nc-conv)+' Konv';
  // Beobachtet, aber nicht angewendet: conv bleibt, was die Engine gerechnet hat. Der Hinweis
  // wird als `hinweis` mitgegeben — kein `tag`, damit calib+/calib- nicht in die Signal-Eimer,
  // ins Papier-Depot oder ins Public-Gate sickert.
  if(!PW_CALIB_AKTIV) return {conv, reason:null, tag:null, hinweis:grund, wuerde:nc};
  return { conv:nc, reason:grund, tag: up?'calib+':'calib-' };
}

function _pwBfEur(v){ const n=Number(v)||0; return n>=1e6?'€'+(n/1e6).toFixed(1)+'M':n>=1e3?'€'+Math.round(n/1e3)+'K':'€'+Math.round(n); }
function _pwBfFav(oc){
  const mm=_pwCache&&_pwCache.moneyMap; const rows=mm&&mm.rows; if(!rows||!rows.length) return null;
  const norm=x=>String(x||'').toLowerCase().replace(/[^a-z0-9]/g,'');
  const like=(x,y)=>{ x=norm(x); y=norm(y); return x&&y&&(x===y||x.includes(y)||y.includes(x)); };
  const names=(oc||[]).map(o=>o.s).filter(Boolean);
  for(const r of rows){
    const bf=r.betfair; if(!bf) continue;
    if(!(names.some(n=>like(n,r.home)) && names.some(n=>like(n,r.away)))) continue;   // beide Teams muessen matchen
    const favName=bf.name || (bf.side==='home'?r.home:bf.side==='away'?r.away:null);
    if(!favName) return null;
    const polySide=names.find(n=>like(n,favName)) || null;
    return { polySide, name:favName, pct:Number(bf.sharePct)||0, eur:Number(bf.eur)||0, side:bf.side };
  }
  return null;
}

function _pwShortlistScore(key,m){
  const oc=Object.entries(m.shares||{}).map(([s,u])=>({s,u:Number(u)||0}));
  if(oc.length<2) return {verdict:'SKIP'};
  const total=oc.reduce((a,b)=>a+b.u,0)||1; oc.sort((a,b)=>b.u-a.u);
  const moneyFav=oc[0].s, moneyPct=oc[0].u/total;
  const pr=m.prices||{}; let priceFav=null,pmax=-1;
  for(const k in pr){ if(typeof pr[k]==='number'&&pr[k]>pmax){pmax=pr[k];priceFav=k;} }
  const sides={}, why={}, tags={};
  // 05.08.2026 (Lucas): jedes Signal traegt einen strukturierten Tag (nicht nur Freitext), damit der
  // Paper-Tracker spaeter je Signal Trefferquote/ROI/CLV zeigen kann (welches Signal traegt die Kante).
  const add=(side,w,reason,tag)=>{ if(!side||!w)return; sides[side]=(sides[side]||0)+w; (why[side]=why[side]||[]).push(reason); if(tag)(tags[side]=tags[side]||[]).push(tag); };
  // 10.08.2026 (Lucas): Spiel-Einsatz (Markt-Volumen) direkt an die Geld-Mehrheit hängen → man sieht sofort,
  // worauf sich die % beziehen. total = Summe der Outcome-Shares = m.totalUsd (die "Vol"-Spalte).
  if(moneyPct>=PW_MONEY_MAJ) add(moneyFav, moneyPct>=0.70?1.5:1, 'großes Geld auf '+moneyFav+' ('+Math.round(moneyPct*100)+'%) → '+_pwUsd(m.totalUsd||total), 'money');
  // Geld vs Preis uneinig → liga-informiert entscheiden (sofort verfügbar aus broadLive)
  // 29.08.2026: gvp hat in 500 abgerechneten UND 550 offenen Plays NULL mal gefeuert — und trug
  // trotzdem bis zu 2,0. Der Grund ist strukturell, kein Bug: auf einem Prognosemarkt IST der
  // Preis die Geldverteilung. Geld-Favorit und Preis-Favorit weichen nur in 15,7% der Maerkte
  // voneinander ab, und das sind fast ausschliesslich Exakt-Ergebnis-Maerkte mit vielen
  // Ausgaengen, wo „Favorit" nichts bedeutet und die ohnehin nie Play werden.
  // Der Zweig bleibt (bei Buchmacher-Maerkten waere er sinnvoll), aber ein ungetesteter Pfad
  // bekommt kein Gewicht, das schwerer waegt als die gemessenen Saeulen.
  if(priceFav&&priceFav!==moneyFav){
    // Ein BELEGTES Liga-Urteil wiegt mehr als der Rueckfall „wir wissen es nicht" — aber beides
    // weniger als frueher (2,0), weil dieser Zweig in 1.050 Plays kein einziges Mal gefeuert hat
    // und deshalb ungetestet ist.
    const _lgr=_pwLeagueMoneyRow(m.league);
    const lg=_lgr?_lgr.verdict:null;
    const _belegt=!!(_lgr && (_lgr.n||0)>=PW_GVP_MIN_N);
    const _w=_belegt?1.5:1;
    if(lg==='geld_schaerfer') add(moneyFav,_w,'Geld schlägt Preis in '+(m.league||'').toUpperCase()+(_belegt?' (n'+_lgr.n+')':''),'gvp');
    else if(lg==='preis_besser') add(priceFav,_w,'Preis schlägt Geld in '+(m.league||'').toUpperCase()+(_belegt?' (n'+_lgr.n+')':''),'gvp');
    else add(priceFav,1,'Geld & Preis uneinig','gvp');
  }
  // 29.08.2026 (Lucas: „das Heute-Spielenswert weiter optimieren") — Steam war das SCHWERSTE
  // Einzelgewicht im Scorer (3,0) bei der zweitschlechtesten Leistung im Papier-Depot:
  // n=127, ROI -7,9%, Untergrenze -19,4%. Und mit 3,0 kam es allein ueber die Play-Schwelle —
  // die 18 Steam-Alleingaenge trafen zu 31,6% bei -40% ROI, die schlechteste Gruppe des Boards.
  // Der Kalibrierer strafte sie hinterher mit -2 ab; besser ist, sie kommen gar nicht erst rein.
  // 2,5 heisst: Steam bestaetigt, Steam traegt nicht mehr allein.
  const mv=_pwMoveFor(key);
  if(mv&&mv.steam&&mv.move>=2) add(mv.side, mv.move>=4?2.5:1.5, 'Steam läuft rein (+'+mv.move.toFixed(1)+'pp)', 'steam');
  const sh=_pwSharpInfoForKey(key);
  if(sh){
    // 29.08.2026 (Lucas-Checkup, „D": Wallets sollen nicht so wichtig sein). Zwei Gruende, beide
    // gemessen statt geschaetzt:
    //  1. Basis war 2,5 — damit war die Wallet das SCHWERSTE Einzelsignal auf dem Board, schwerer
    //     als „grosses Geld >=70%" (1,5). Die Signal-Bilanz sagt das Gegenteil: sharp n=352 bringt
    //     +1,2% ROI, bf n=41 bringt +26,4%. Ein Signal mit +1,2% darf nicht das Ruder fuehren.
    //  2. Der Konfidenzfaktor hatte einen Boden von 0,7 und war ab n=12 voll. Eine Wallet-Historie
    //     aus 9 abgerechneten Plays bekam also 92,5% des Gewichts einer aus 266 — der Grund, warum
    //     ein Cricket-Spiel mit 9 Plays Historie und 54% Geld auf Platz 2 der Top-Wetten stand.
    // Jetzt: Basis 1,8 (Boni unveraendert) und ein Faktor, der wirklich beisst — 0,30 bei n=4,
    // 0,48 bei n=9, 0,94 bei n=32, voll erst ab n=35.
    // 29.08.2026 (Punkt 5): der P&L-Bonus (+0,5 bei pnl>0) ist raus. P&L ist die Poly-Gesamtbilanz
    // ueber alle Maerkte — Wahlen, Krypto, alles. Ihn als Schaerfe-BEWEIS zu verrechnen, mischt
    // zwei verschiedene Welten. Er bleibt, was er belegen kann: ein Ausschluss im Gate oben.
    let w=1.8; if(sh.hit>=0.6)w+=0.5; if(sh.hit>=0.7)w+=0.5;
    w *= Math.min(1, 0.3 + (sh.n||0)/50);
    // 01.09.2026: Beleggrad statt Schalter. Eine bewiesene Wallet (Wilson-UG >50%) traegt wie
    // bisher voll; eine vielversprechende anteilig. Vorher trug letztere GAR NICHT bei — und
    // genau diese Bande lieferte out of sample den besten CLV (+0,94pp, s. _pwSharpGrade).
    const _gr=(typeof sh.grade==='number')?sh.grade:1;
    w *= _gr;
    // 10.08.2026 (Lucas): Lebenszeit-P&L der Wallet über _pwUsd formatieren → rollt ab 1M sauber auf "M"
    // (z.B. +$3.44M statt des hässlichen "3440K"). _pwUsd trägt das '$', Vorzeichen kommt davor.
    const pnlTxt=(sh.pnl>=0?'+':'-')+_pwUsd(Math.abs(sh.pnl));
    // Der Text sagt, was die Zahl sagt: „scharf" nur bei bewiesenen Wallets, sonst ehrlich
    // „vielversprechend". Ein halber Beleg darf nicht wie ein ganzer klingen.
    const _lbl=_gr>=1?'🔥 scharfe Wallet':'🔎 vielversprechende Wallet (noch nicht belegt)';
    // ⚠️ Der TAG ist nicht dasselbe wie das GEWICHT. Das Gewicht darf beliebig fein sein — der Tag
    // bildet die Eimer, in denen `_pwCalibConv` und das Freigabe-Register rechnen. Liefe jeder
    // 0,1-Beitrag als 'sharp' mit, stuende ein Play mit 0,23 Gewicht im selben Eimer wie eines mit
    // 2,8 — und der Eimer misst dann nichts mehr. Deshalb traegt nur ein halbwegs belegter Beitrag
    // das Etikett; darunter zaehlt die Wallet mit, benennt den Play aber nicht.
    add(sh.side,w,_lbl+' ('+sh.wins+'/'+sh.n+', '+Math.round(sh.hit*100)+'% · '+pnlTxt+')'
        +(_gr>=1?'':' · zählt '+Math.round(_gr*100)+'%'),
        _gr>=PW_SHARP_TAG_MIN_GRADE?'sharp':null);
  } else {
    // 29.08.2026 (Lucas-Checkup, „D"): Dieser Zweig greift, wenn wir zwar eine scharfe Wallet
    // sehen, aber KEINE Bilanz zu ihr haben — und vergab dafuer 2,5, also exakt so viel wie eine
    // belegte Historie oben. Kein Wissen ist keine Bestaetigung: jetzt 1,0, ein Hinweis statt
    // eines Arguments.
    const sharp=_pwSharpSideForKey(key) || _pwSharpSideFor(m);
    if(sharp) add(sharp,1.0,'🔥 scharfe Wallet drin (ohne Bilanz)', 'sharp');
  }
  // (01.08.2026, Lucas) Pinnacle-Kante einweben: de-viggte Pinnacle vs Poly-Preis. Konsens hebt
  // Conviction, deutliche Fehlbewertung = eigener Value-Play. Feuert nur wenn crossSport-Daten da.
  // 29.08.2026: pinn hat acht abgerechnete Plays (ROI -41%, Untergrenze -88%). Acht Beobachtungen
  // rechtfertigen kein Gewicht von 2 — das ist keine Abwertung des Signals, sondern der Respekt
  // vor der Stichprobe. Waechst sie und traegt sie, holt der Kalibrierer es von selbst zurueck.
  const pe=_pwPinnEdgeFor(m,oc);
  if(pe){
    const w=Math.abs(pe.gapPP)>=8?1.5:1;
    if(pe.back) add(pe.side,w,'Pinnacle: Poly '+Math.abs(pe.gapPP).toFixed(0)+'pp zu billig → Value','pinn');
    else if(pe.other) add(pe.other,w,'Pinnacle: Poly '+Math.abs(pe.gapPP).toFixed(0)+'pp zu teuer auf '+pe.side,'pinn');
  }
  // 21.08.2026 (Lucas): Betfair-Geld als Gegencheck. Liegt auf Betfair Geld (>=55%) auf einer Seite,
  // zaehlt das als Bestaetigung fuer die Seite (moderate Gewichtung, kippt gut gestuetzte Picks nicht).
  // 29.08.2026: bf war Rang 1 nach Leistung und Rang 6 nach Gewicht — die einzige Saeule, deren
  // Untergrenze nicht unter null liegt (n=43, ROI +20,5%, UG 0,0%). Rauf auf 1,5/2,0. Bewusst
  // NICHT ueber die Play-Schwelle von 3: 43 Plays rechtfertigen mehr Stimme, aber keinen
  // Alleingang. Ein zweites Signal muss weiterhin dazukommen.
  const _bf=_pwBfFav(oc);
  if(_bf && _bf.polySide && _bf.pct>=55){
    add(_bf.polySide, _bf.pct>=70?2:1.5, '💷 Betfair-Geld bestätigt: '+_bf.pct+'% · '+_pwBfEur(_bf.eur), 'bf');
  }
  let best=null,bs=0; for(const s in sides) if(sides[s]>bs){bs=sides[s];best=s;}
  const vol=m.totalUsd||0;
  if(!best||bs<3||vol<15000) return {verdict:'SKIP'};
  let conv=Math.min(10,Math.round(2+bs));   // 09.08.2026 (Lucas): Basis 4→2 — ein Einzelsignal ist nicht mehr schon 7-8/10; Skala spreizt ~5-10 (Public-Gate unten von ≥9 auf ≥7 mitgezogen, gleiche effektive Stärke)
  let reasons=(why[best]||[]).slice(0,3);
  const sigs=[...new Set(tags[best]||[])];
  let turned=false;
  // 07.08.2026 Umkehr-Sperre: Preis der empfohlenen Seite hart vom Hoch zurueck → warnen bzw. raus.
  const adv=_pwAdverseFor(key,best);
  if(adv && adv.cur<=PW_ADVERSE_MAX_CUR && adv.fromPeak>=PW_ADVERSE_WARN_PP){
    if(adv.fromPeak>=PW_ADVERSE_KILL_PP) return {verdict:'SKIP',turned:true};   // Markt gedreht → raus aus Box + Uebersicht
    turned=true;
    reasons=['⚠️ Markt gedreht — Preis '+adv.fromPeak.toFixed(0)+'pp gegen uns'].concat(reasons).slice(0,3);
    sigs.push('turned');
    conv=Math.max(1,conv-3);   // stark abwerten → rutscht ans Ende der Liste
  }
  // 21.08.2026 (Lucas #3, kontinuierlich): Track-Kalibrierung — conv sanft Richtung realer Mix-
  // Performance ziehen (auf UND ab, gewichtet nach Stichprobe). Kein Signal raus; nur Rangfolge schaerfen.
  const _ca=_pwCalibConv(sigs, conv);
  conv=_ca.conv;
  if(_ca.reason){
    reasons=[_ca.reason].concat(reasons).slice(0,3);
    if(!sigs.includes(_ca.tag)) sigs.push(_ca.tag);
  }
  // 16.08.2026 (Lucas Übersicht): Live-Flip-Riegel — laufendes Spiel, Shares-Seite != Preis-Seite und
  // Preis klar (>=PW_LIVE_FLIP_GAP) dagegen => der Markt ist auf die Gegenseite gekippt, unsere Positions-
  // mehrheit ist Vor-Anpfiff-Alt. Braucht KEINE History (anders als _pwAdverseFor) -> greift trotz Scan-Lag.
  if((_pwRealHtk(m)||0) < 0 && priceFav && best !== priceFav
     && typeof pr[best]==='number' && typeof pr[priceFav]==='number'
     && (pr[priceFav]-pr[best]) >= PW_LIVE_FLIP_GAP){
    return {verdict:'SKIP', turned:true};
  }
  // Betfair-Gegencheck relativ zur empfohlenen Seite (fuer die Anzeige im Konviktions-Panel).
  let bf=null;
  if(_bf){
    const _n=x=>String(x||'').toLowerCase().replace(/[^a-z0-9]/g,'');
    const agree=_bf.polySide && (_n(_bf.polySide)===_n(best) || _n(_bf.polySide).includes(_n(best)) || _n(best).includes(_n(_bf.polySide)));
    bf={agree:!!agree, pct:_bf.pct, eur:_bf.eur, name:_bf.name};
  }
  // 24.08.2026 (Lucas): `token` = CLOB-Token-ID der empfohlenen Seite (seit heute im Broad-Feed).
  // Damit kann der Betting-Tab die Wette DIREKT ausloesen, statt den Play erst ueber Slug+Teamnamen
  // an einen gestempelten Card-Pick zu matchen (ging nur fuer Fussball MIT Pick). `sport` fuer die
  // Sportart-Sperre. Beides rein additiv — bestehende Verbraucher ignorieren die Felder.
  return {key,match:_pwPlayLabel(key,oc),verdict:(best===moneyFav?'BET':'FADE'),side:best,
    conv,reasons,signals:sigs,vol,htk:_pwRealHtk(m),league:m.league,sport:m.sport,turned,
    ev:PW_ENGINE_VERSION,   // 29.08.2026: Engine-Stempel -> Papier-Depot -> Kalibrierung

    token:((m.tokens||{})[best]||null),
    moneyPct,sharp:(sh&&sh.side===best)?sh:null,price:(typeof pr[best]==='number'?pr[best]:null),bf};
}
// 📊 Paper-Track-Record der „Heute wetten"-Shortlist (02.08.2026, Lucas). Liest poly_shortlist_track.json
// (open/settled/agg), zeigt: KPIs je Sicht (ganze Shortlist + Public), Conviction-Tabelle (die
// Entscheidungshilfe fürs spätere Auto-Bet), offene Plays, letzte abgerechnete. Setzt/sendet NICHTS.
const _PW_TRACK_MIN_N = 20;   // ab so vielen abgerechneten Plays gilt eine Sicht/Stufe als belastbar
function _pwtPct(x){ return (x==null?'—':(Math.round(x*1000)/10)+'%'); }
function _pwtSig(x){ return (x>=0?'+':'')+x; }
function _pwtUsd(x){ const v=Math.round(x); return (v>=0?'+$':'-$')+Math.abs(v); }
function _pwTrackKpis(a, label, hint){
  const thin = a.n < _PW_TRACK_MIN_N;
  const roiCol = a.n? (a.roi>0?'#3fb950':a.roi<0?'#f85149':'#8b949e') : '#8b949e';
  const clvCol = a.n? (a.clvAvg>0?'#3fb950':a.clvAvg<0?'#f85149':'#8b949e') : '#8b949e';
  const card=(lbl,val,col,sub)=>'<div style="flex:1;min-width:120px;background:#0f1626;border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:12px 14px">'
    +'<div style="font-size:10.5px;color:#8b949e;text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px">'+lbl+'</div>'
    +'<div style="font-size:21px;font-weight:900;color:'+(col||'#e6edf3')+'">'+val+'</div>'
    +(sub?'<div style="font-size:10px;color:#6e7681;margin-top:1px">'+sub+'</div>':'')+'</div>';
  const badge = thin ? '<span style="font-size:10.5px;color:#e3b341;font-weight:700;margin-left:8px">· sammelt noch (n&lt;'+_PW_TRACK_MIN_N+')</span>' : '';
  return '<div style="margin:2px 0 16px">'
    +'<div style="font-size:13px;font-weight:800;color:#e6edf3;margin-bottom:8px">'+label+badge
      +(hint?'<span style="font-size:11px;color:#6e7681;font-weight:600;margin-left:6px">'+hint+'</span>':'')+'</div>'
    +'<div style="display:flex;gap:9px;flex-wrap:wrap">'
      +card('abgerechnet', a.n, '#e6edf3', a.wins+' Treffer')
      +card('Trefferquote', a.n?_pwtPct(a.hit):'—', a.n?(a.hit>=0.5?'#3fb950':'#f85149'):'#8b949e')
      +card('ROI', a.n?_pwtSig(Math.round(a.roi*1000)/10)+'%':'—', roiCol, 'fixer Einsatz $'+ (a.stake&&a.n?Math.round(a.stake/a.n):10))
      +card('Netto P&amp;L', a.n?_pwtUsd(a.pnl):'—', roiCol, 'Einsatz $'+Math.round(a.stake||0))
      +card('Ø CLV', a.n?_pwtSig(a.clvAvg)+'pp':'—', clvCol, 'Einstieg→Schluss')
    +'</div></div>';
}
// 24.08.2026 (Lucas: „ziehen die die Statistik runter?"). Ja — deshalb steht vorne die Zahl, die
// wirklich bespielt wird, und die gesperrten Sportarten kommen als eigene BEOBACHTUNGS-Zeile.
// Nicht gelöscht, sondern beobachtet: das Mitschreiben kostet nichts und ist die einzige Art zu
// merken, dass eine Sportart dreht. Wiedereintritt wird am CLV gemessen (Frühindikator), nicht am
// ROI, und schaltet NICHTS automatisch frei — es ist ein Hinweis.
function _pwTrackBlocked(agg, reentry, blockedCats){
  const a=agg&&agg.blocked;
  const cats=(blockedCats||[]).join(' · ');
  // Kein Segment gesperrt UND nichts abgerechnet -> gar keine Zeile. (Sonst stand da
  // „Nicht bespielbar: — —" auf jedem Board, das die Sperrliste noch nicht kennt.)
  if(!cats.length && !(a&&a.n)) return '';
  if(!a||!a.n) return '<div class="pw-mut" style="font-size:11px;margin:-8px 0 14px">🚫 Nicht bespielbar: '
    +_pwEsc(cats)+' — bisher keine abgerechneten Plays. Bleiben im Depot, damit ein Umschwung sichtbar würde.</div>';
  const roiCol=a.roi>0?'#3fb950':a.roi<0?'#f85149':'#8b949e';
  const clvCol=a.clvAvg>0?'#3fb950':a.clvAvg<0?'#f85149':'#8b949e';
  let hint='';
  const rs=reentry||{};
  const ready=Object.keys(rs).filter(k=>rs[k]&&rs[k].eligible);
  if(ready.length){
    hint='<div style="font-size:11.5px;color:#3fb950;font-weight:700;margin-top:5px">↩︎ '
      +_pwEsc(ready.join(', '))+' erfüllt die Wiedereintritts-Kriterien (Ø CLV ≥ 0 über genug frische Plays)'
      +' — Sperre in poly-wallets.js <code>PW_BLOCKED_BET_CATS</code> prüfen.</div>';
  } else {
    const parts=Object.keys(rs).map(k=>{
      const r=rs[k]||{};
      const clv=(r.clvAvg==null)?'kein Schluss erfasst':(_pwtSig(r.clvAvg)+'pp');
      const need=r.needN?(' · noch '+r.needN+' Plays'):(r.needClvN?(' · noch '+r.needClvN+' mit Schluss'):'');
      return _pwEsc(k)+' '+clv+' ('+(r.n||0)+')'+need;
    });
    if(parts.length) hint='<div class="pw-mut" style="font-size:11px;margin-top:5px">Wiedereintritt (Ø CLV ≥ 0): '+parts.join(' · ')+'</div>';
  }
  return '<div style="background:#0f1626;border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:9px 12px;margin:-6px 0 16px">'
    +'<div style="font-size:11.5px;color:#8b949e">🚫 <b style="color:#c9d1d9">Nicht bespielbar</b> ('+_pwEsc(cats)+') — nur Beobachtung, kein Geld: '
      +'<b>'+a.n+'</b> Plays · Treffer '+_pwtPct(a.hit)
      +' · ROI <b style="color:'+roiCol+'">'+_pwtSig(Math.round(a.roi*1000)/10)+'%</b>'
      +' · Ø CLV <b style="color:'+clvCol+'">'+_pwtSig(a.clvAvg)+'pp</b></div>'+hint+'</div>';
}
function _pwTrackConvTable(byConv){
  const rows=Object.keys(byConv||{}).map(k=>({c:+k, a:byConv[k]})).sort((x,y)=>y.c-x.c);
  if(!rows.length) return '';
  const body=rows.map(r=>{
    const a=r.a, roiCol=a.roi>0?'#3fb950':a.roi<0?'#f85149':'#8b949e', clvCol=a.clvAvg>0?'#3fb950':a.clvAvg<0?'#f85149':'#8b949e';
    const thin=a.n<8?' style="opacity:.6"':'';
    return '<tr'+thin+'><td class="pw-cn" style="font-weight:800;color:#4cc2ff">'+r.c+'/10</td>'
      +'<td class="pw-cn">'+a.n+'</td>'
      +'<td class="pw-cn" style="color:'+(a.hit>=0.5?'#3fb950':'#f85149')+'">'+_pwtPct(a.hit)+'</td>'
      +'<td class="pw-cn" style="font-weight:800;color:'+roiCol+'">'+_pwtSig(Math.round(a.roi*1000)/10)+'%</td>'
      +'<td class="pw-cn" style="color:'+clvCol+'">'+_pwtSig(a.clvAvg)+'pp</td>'
      +'<td class="pw-cn pw-mut">'+_pwtUsd(a.pnl)+'</td></tr>';
  }).join('');
  return '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🎯 Nach Conviction — wo lohnt sich das echte Setzen?</span>'
    +'<span class="pw-sec-note">Je höher die Conviction, desto besser sollte ROI &amp; CLV sein. Erst wenn eine Stufe über genug Spiele (n≥8, klar &gt;0) im Plus ist, ist sie ein Auto-Bet-Kandidat. Blasse Zeilen = noch zu wenige.</span></div>'
    +'<div class="pw-tw"><table class="pw-tbl"><thead><tr><th>Conviction</th><th>n</th><th>Treffer</th><th>ROI</th><th>Ø CLV</th><th>P&amp;L</th></tr></thead><tbody>'+body+'</tbody></table></div></section>';
}
function _pwTrackSettled(settled){
  const rows=(settled||[]).slice(-15).reverse();
  if(!rows.length) return '';
  const body=rows.map(r=>{
    const win=r.result==='win', rc=win?'#3fb950':'#f85149';
    const vc=r.verdict==='BET'?'#3fb950':'#e3b341';
    const pnlCol=(+r.pnl||0)>=0?'#3fb950':'#f85149';
    return '<tr>'
      +'<td>'+_pwSportIcon(r.league)+' <span class="pw-cm">'+_pwEsc(String(r.key||'').slice(0,26))+'</span></td>'
      +'<td class="pw-cm"><b style="color:#4cc2ff">'+_pwEsc(r.side)+'</b></td>'
      +'<td><span style="color:'+vc+';font-weight:700;font-size:11px">'+_pwEsc(r.verdict||'')+'</span>'+(r.public?' <span title="Public-Kandidat" style="color:#a78bfa">◆</span>':'')+'</td>'
      +'<td class="pw-cn">'+(r.conv!=null?r.conv+'/10':'—')+'</td>'
      +'<td class="pw-cn pw-mut">'+(r.entryPrice!=null?Math.round(r.entryPrice*100)+'¢':'—')+'</td>'
      +'<td class="pw-cn" style="font-weight:800;color:'+rc+'">'+(win?'✓':'✗')+'</td>'
      +'<td class="pw-cn" style="color:'+pnlCol+'">'+_pwtUsd(r.pnl)+'</td>'
      +'<td class="pw-cn pw-mut">'+_pwtSig(r.clvPP)+'pp</td></tr>';
  }).join('');
  return '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🧾 Letzte abgerechnete Plays</span>'
    +'<span class="pw-sec-note">◆ = war Public-Kandidat · ✓/✗ = Markt getroffen · P&amp;L bei fixem $-Einsatz · CLV = Einstieg→Schluss</span></div>'
    +'<div class="pw-tw"><table class="pw-tbl"><thead><tr><th>Markt</th><th>Seite</th><th>Verdikt</th><th>Conv</th><th>Einstieg</th><th>Erg.</th><th>P&amp;L</th><th>CLV</th></tr></thead><tbody>'+body+'</tbody></table></div></section>';
}
// 23.08.2026 (Lucas): Live-Konviktion eines offenen Plays neu rechnen — die im Track gespeicherte Zahl
// ist beim EINSTIEG eingefroren, die Uebersicht rechnet live. Fuer den „Einstieg -> jetzt"-Pfeil in den
// offenen Plays holen wir den aktuellen Markt (live > close > global) und lassen den Scorer neu urteilen.
// null = Markt nicht mehr im Scan (abgepfiffen/aufgeloest) ODER der Play wuerde jetzt gar nicht mehr feuern.
function _pwLiveConvFor(key){
  const c=_pwCache||{};
  const m=(c.broadLiveNow&&c.broadLiveNow[key]) || (c.broadLive&&c.broadLive[key]) || (c.moneyBroad&&c.moneyBroad[key]);
  if(!m) return null;
  try{ const sc=_pwShortlistScore(key,m); return (sc&&typeof sc.conv==='number')?sc.conv:null; }catch(e){ return null; }
}
function _pwTrackOpen(open){
  const arr=Object.values(open||{}).sort((a,b)=>(b.conv||0)-(a.conv||0));
  if(!arr.length) return '';
  const head='<div style="font-size:12px;color:#8b949e;margin:14px 0 6px"><b style="color:#e6edf3">'+arr.length+' offene Plays</b> — laufen noch, werden bei Markt-Auflösung abgerechnet · <span class="pw-mut">Konviktion = Einstieg → jetzt (live)</span></div>';
  const body=arr.slice(0,12).map(e=>{
    const lc=_pwLiveConvFor(e.key);
    // Pfeil nur wenn die Live-Zahl real abweicht — sonst nur die eingefrorene Einstiegs-Konviktion.
    const trend=(lc!=null && e.conv!=null && lc!==e.conv)
      ? ' <span style="color:'+(lc>e.conv?'#3fb950':'#f0883e')+';font-weight:700"> → '+lc+' '+(lc>e.conv?'↑':'↓')+'</span>'
      : '';
    const convTxt=(e.conv!=null?e.conv+'/10':'')+trend;
    return '<span style="display:inline-block;margin:0 6px 6px 0;padding:4px 9px;border-radius:14px;background:#0f1626;border:1px solid rgba(255,255,255,.08);font-size:11.5px">'
    +_pwSportIcon(e.league)+' <b style="color:#4cc2ff">'+_pwEsc(String(e.side).slice(0,16))+'</b> '
    +'<span class="pw-mut">'+(e.verdict||'')+' · '+convTxt+' · '+(e.entryPrice!=null?Math.round(e.entryPrice*100)+'¢':'')+'</span>'
    +(e.public?' <span style="color:#a78bfa">◆</span>':'')+'</span>';
  }).join('');
  return head+'<div style="margin-bottom:6px">'+body+'</div>';
}
const _PW_SIG_LABEL={sharp:'🔥 Scharfe Wallet',steam:'📈 Steam',money:'💰 Geld-Mehrheit',gvp:'⚖️ Geld vs Preis',pinn:'🎯 Pinnacle-Value',bf:'💷 Betfair-Geld'};   // 29.08.2026: bf ergaenzt — seit heute im Kalibrier-Kern
// 05.08.2026 (Lucas): welches Signal traegt die Kante? Trefferquote/ROI/CLV je Ausloeser-Signal.
// Ein Play kann mehrere Signale haben (zaehlt dann in mehreren Zeilen) - so wird sichtbar, welches
// Signal wirklich Geld bringt und welches Ballast ist. Fuellt sich mit neu abgerechneten Plays.
function _pwTrackSignalTable(bySig){
  const rows=Object.keys(bySig||{}).map(k=>({k,a:bySig[k]})).filter(r=>r.a&&r.a.n).sort((x,y)=>y.a.n-x.a.n);
  if(!rows.length) return '';
  const body=rows.map(r=>{
    const a=r.a, roiCol=a.roi>0?'#3fb950':a.roi<0?'#f85149':'#8b949e', clvCol=a.clvAvg>0?'#3fb950':a.clvAvg<0?'#f85149':'#8b949e';
    const thin=a.n<8?' style="opacity:.6"':'';
    return '<tr'+thin+'><td class="pw-cm" style="font-weight:700">'+(_PW_SIG_LABEL[r.k]||_pwEsc(r.k))+'</td>'
      +'<td class="pw-cn">'+a.n+'</td>'
      +'<td class="pw-cn" style="color:'+(a.hit>=0.5?'#3fb950':'#f85149')+'">'+_pwtPct(a.hit)+'</td>'
      +'<td class="pw-cn" style="font-weight:800;color:'+roiCol+'">'+_pwtSig(Math.round(a.roi*1000)/10)+'%</td>'
      +'<td class="pw-cn" style="color:'+clvCol+'">'+_pwtSig(a.clvAvg)+'pp</td>'
      +'<td class="pw-cn pw-mut">'+_pwtUsd(a.pnl)+'</td></tr>';
  }).join('');
  return '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🧭 Welches Signal trägt die Kante?</span>'
    +'<span class="pw-sec-note">Trefferquote/ROI/CLV je Auslöser-Signal. Ein Play kann mehrere Signale haben (zählt dann in mehreren Zeilen). Blasse Zeilen = noch zu wenige (n&lt;8).</span></div>'
    +'<div class="pw-tw"><table class="pw-tbl"><thead><tr><th>Signal</th><th>n</th><th>Treffer</th><th>ROI</th><th>Ø CLV</th><th>P&amp;L</th></tr></thead><tbody>'+body+'</tbody></table></div></section>';
}
function _pwTrackRecord(track){
  const intro='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">📊 Track-Record — „Heute wetten" als Paper-Trade</span>'
    +'<span class="pw-sec-note">Jeder Scan schreibt die exakten Shortlist-Empfehlungen mit (fixer Einsatz, Einstieg = Snapshot-Preis) und rechnet bei Auflösung ab. <b>Es wird nichts gesetzt</b> — nur mitgeschrieben, damit wir sehen, ob sich echtes Nachspielen lohnt.</span></div>';
  if(!track || (!(track.settled||[]).length && !Object.keys(track.open||{}).length)){
    return intro+'<div class="pw-none">Noch keine Daten. Der Tracker läuft mit jedem Global-Scan (~alle 30 Min): er öffnet die aktuellen „Heute wetten"-Plays als Paper-Positionen und rechnet sie bei Markt-Auflösung ab. Nach den ersten aufgelösten Spielen steht hier Trefferquote, ROI und CLV — <b>getrennt für die ganze Shortlist und die Public-Kandidaten</b>.</div></section>';
  }
  const agg=track.agg||{all:{n:0},public:{n:0},byConv:{}};
  const upd=track.updatedAt?('<div class="pw-mut" style="font-size:11px;margin:2px 0 10px">Stand '+_pwEsc(String(track.updatedAt).slice(0,16).replace('T',' '))+' · fixer Einsatz $'+Math.round(track.stake||10)+' je Play</div>'):'';
  return intro+upd
    +_pwTrackKpis(agg.bettable||agg.all||{n:0}, '🟢 Bespielbar', '(alle Sportarten, auf die gesetzt werden darf)')
    +_pwTrackBlocked(agg, track.reentry, track.blockedCats)
    +_pwTrackKpis(agg.public||{n:0}, '◆ Public-Kandidaten', '(hart gegated: Conv≥7 + bewiesene Wallet + Mehrheit)')
    +_pwTrackConvTable(agg.byConv)
    +_pwCalibBoard()          // 29.08.2026: warum eine Stufe hoeher/tiefer — sichtbar statt Blackbox
    +_pwTrackSignalTable(agg.bySignal)
    +_pwTrackOpen(track.open)
    +_pwTrackSettled(track.settled);
}

// ═══════════════════════════════════════════════════════════════════════════════════════
//  🧭 LERN-BOARD — was die Kalibrierung aus dem Papier-Depot gelernt hat (29.08.2026, Lucas:
//  „das ist sehr wichtig, es optisch cool darzustellen").
//
//  Bis heute war _pwCalibConv eine Blackbox: sie verschob Conviction um bis zu drei Stufen und
//  die einzige Spur davon war eine Zeile im „Warum". Einem Lerner, den man nicht sehen kann,
//  sollte man nicht glauben — und bei „warum hat der Play nur 4?" gab es keine Antwort.
//
//  Form: DIVERGIERENDER BALKEN. Die Frage ist Polaritaet (liegt dieser Signal-Mix ueber oder
//  unter dem Schnitt der ganzen Shortlist), nicht Groesse — also ein Balken, der aus einer
//  Mittellinie nach links oder rechts waechst, nicht aus dem Nullpunkt.
//
//  Farbe: gruen/rot ist die Sprache des ganzen Dashboards (P&L, CLV, Trefferquote) und bleibt.
//  ABER: das Paar hat fuer Rot-Gruen-Blinde einen Abstand von ΔE 2,2 (deutan) — praktisch
//  ununterscheidbar. Deshalb traegt die Farbe hier NIE die Aussage allein: Richtung ab der
//  Mittellinie, Vorzeichen und ein ↑/↓ sagen dasselbe noch dreimal. Wer die Farben nicht
//  trennen kann, liest die Zeile trotzdem.
const _PW_CAL_BAR_W=190;   // halbe Balkenbreite je Richtung
function _pwCalMixLabel(k){
  if(k==='(none)') return '<span class="pw-mut" style="font-size:12px">ohne Kern-Signal</span>';
  return k.split('+').map(t=>'<span class="pw-cal-chip">'+(_PW_SIG_LABEL[t]||_pwEsc(t))+'</span>').join('');
}
function _pwCalibBoard(){
  const agg=_pwComboStatsAll();
  const intro='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🧭 Lern-Board — was die Kalibrierung gelernt hat</span>'
    +'<span class="pw-sec-note">Jeder Play trägt einen Signal-Mix. Der Lerner misst je Mix den <b>echten ROI</b> des Papier-Depots und verschiebt die Conviction sanft dorthin — nach oben wie nach unten, gewichtet nach Stichprobe. Kein Signal fliegt raus.</span></div>';
  if(!agg||!Object.keys(agg).length){
    return intro+'<div class="pw-none">Noch nichts gelernt — der Lerner braucht abgerechnete Plays aus dem Papier-Depot.</div></section>';
  }
  const base=_pwComboBaselineRoi();
  const rows=Object.entries(agg).map(([k,a])=>({k,...a,d:a.roi-base})).sort((x,y)=>y.nRoh-x.nRoh);
  const span=Math.max(0.05, ...rows.map(r=>Math.abs(r.d)));
  const nRoh=rows.reduce((s,r)=>s+r.nRoh,0), nAlt=rows.reduce((s,r)=>s+r.nAlt,0);
  const pc=v=>(v>=0?'+':'−')+Math.abs(v*100).toFixed(1)+'%';

  const kpi=(v,l,sub,col)=>'<div class="pw-cal-kpi"><div class="pw-cal-kpi-v" style="color:'+col+'">'+v+'</div>'
    +'<div class="pw-cal-kpi-l">'+l+'</div><div class="pw-cal-kpi-s">'+sub+'</div></div>';
  const head='<div class="pw-cal-kpis">'
    +kpi(_pwEsc(PW_ENGINE_VERSION),'Engine-Version','Stempel an jedem Play','#5eead4')
    +kpi(pc(base),'Basis-ROI der Shortlist','die Mittellinie im Balken','#e6edf3')
    +kpi(nRoh+' Plays','Lern-Basis',(nAlt===nRoh?'alle aus älterer Engine — zählen halb'
        :nAlt?nAlt+' aus älterer Engine — zählen halb':'alle aus der aktuellen Engine'),'#e6edf3')
    +'</div>';

  // Die Skala gehoert UEBER die Plot-Spalte, nicht ueber die ganze Zeile — sonst steht „Schnitt"
  // irgendwo, nur nicht ueber der Mittellinie. Gleiches Raster wie die Zeilen.
  const skala='<div class="pw-cal-row pw-cal-legend"><div></div><div class="pw-cal-plot">'
    +'<div class="pw-cal-scale"><span>schlechter</span><span class="pw-cal-scale-mid">Schnitt</span><span>besser</span></div>'
    +'</div><div></div><div></div><div></div></div>';

  const body=rows.map(r=>{
    const stark=r.n>=8;
    const conf=r.n/(r.n+25);
    const adj=stark?Math.max(-3,Math.min(2,r.d*15*conf)):0;
    const stufen=Math.round(adj);
    const pos=r.d>=0;
    const w=Math.max(3, Math.round(Math.abs(r.d)/span*_PW_CAL_BAR_W));
    const col=pos?'#3fb950':'#f85149';
    const bar='<div class="pw-cal-track"><div class="pw-cal-mid"></div>'
      +'<div class="pw-cal-bar" style="'+(pos?'left:50%;border-radius:0 4px 4px 0':'right:50%;border-radius:4px 0 0 4px')
      +';width:'+w+'px;background:'+col+(stark?'':';opacity:.42')+'"></div></div>';
    const chip=!stark
      ? '<span class="pw-cal-adj pw-cal-adj-off">sammelt · n&lt;8</span>'
      : (stufen===0
        ? '<span class="pw-cal-adj pw-cal-adj-off">keine Anpassung</span>'
        : '<span class="pw-cal-adj" style="color:'+(stufen>0?'#3fb950':'#f85149')+';border-color:'+(stufen>0?'rgba(63,185,80,.4)':'rgba(248,81,73,.4)')+'">'
          +(stufen>0?'↑ +':'↓ −')+Math.abs(stufen)+' Stufe'+(Math.abs(stufen)===1?'':'n')+'</span>');
    // ROI und Abstand sind ZWEI Zahlen. Der Pfeil gehoert zum Abstand (das zeigt der Balken),
    // nicht zum ROI — sonst stuende bei -0,5% ROI ein ↑, weil es ueber dem Schnitt von -1,5% liegt.
    const val='<div class="pw-cal-val"><b>'+pc(r.roi)+'</b><i>ROI im Depot</i></div>';
    const dist='<div class="pw-cal-dist" style="color:'+(stark?col:'#5b667e')+'">'
      +(pos?'↑ ':'↓ ')+Math.abs(r.d*100).toFixed(1)+'pp'
      +'<i>'+(pos?'über':'unter')+' Schnitt</i></div>';
    const basis=r.nRoh+' Play'+(r.nRoh===1?'':'s')
      +(r.nAlt===r.nRoh?' · alle aus älterer Engine':(r.nAlt?' · '+r.nAlt+' älter':''))
      +(r.nAlt?'<i>zählt wie '+r.n.toFixed(1).replace('.0','')+'</i>':'');
    const tip='Signal-Mix '+r.k+' — ROI '+(r.roi*100).toFixed(1)+'%, Schnitt '+(base*100).toFixed(1)
      +'%, Abstand '+(r.d*100).toFixed(1)+'pp, Vertrauen '+Math.round(conf*100)+'% (gewichtete n '+r.n.toFixed(1)+')';
    return '<div class="pw-cal-row'+(stark?'':' pw-cal-row-thin')+'" title="'+_pwEsc(tip)+'">'
      +'<div class="pw-cal-mix">'+_pwCalMixLabel(r.k)+'</div>'
      +'<div class="pw-cal-plot">'+bar+dist+'</div>'
      +val
      +'<div class="pw-cal-n">'+basis+'</div>'
      +'<div class="pw-cal-out">'+chip+'</div></div>';
  }).join('');

  const fuss='<div class="pw-sec-p" style="margin-top:12px">Die Anpassung wächst mit dem Abstand zum Schnitt <i>und</i> mit der Stichprobe (Vertrauen = n/(n+25)), '
    +'ist auf <b>−3 bis +2 Stufen</b> geklammert — mehr Abwertung als Boost — und wirkt erst ab acht gewichteten Plays. '
    +'Plays aus einer älteren Engine zählen halb: ihre ROI-Schätzung bleibt, nur das Vertrauen sinkt.</div>';
  return intro+head+skala+'<div class="pw-cal-board">'+body+'</div>'+fuss+'</section>';
}

// 18.08.2026 (Lucas): 🖥️ TERMINAL — dichtes Board als Aufsatz auf „Heute wetten" (_pwTopPlays, UNVERAENDERT).
// Gleiche Plays, gleiche Conviction. NEU: CLV-Bucket je Conviction-Stufe (aus poly_shortlist_track.agg.byConv)
// + Auto-Mute historisch -EV Stufen (z.B. Konv5). Slice 1 = Board; Edge/Kelly/Drilldown = Slice 2.
let _pwTermHideMuted=false;
function _pwTermMute(v){ _pwTermHideMuted=!!v; _pwRender(); }
if(typeof window!=='undefined') window._pwTermMute=_pwTermMute;

function _pwTermBucket(conv){
  const bc=(_pwCache&&_pwCache.shortlistTrack&&_pwCache.shortlistTrack.agg&&_pwCache.shortlistTrack.agg.byConv)||{};
  return bc[String(conv)]||null;
}
function _pwTermMuted(r){
  // 21.08.2026 (Lucas #3): Signal-Mix historisch klar -EV → muten (Grund zeigt echten ROI).
  const cb=_pwComboFor(r.signals);
  if(cb && cb.n>=15 && cb.roi<=-0.10) return {m:true,reason:'Mix '+Math.round(cb.roi*100)+'% ROI · n'+cb.n};
  const b=_pwTermBucket(r.conv);
  if(b&&b.n>=20&&typeof b.roi==='number'&&b.roi<=-0.10) return {m:true,reason:'Konv'+r.conv+' '+Math.round(b.roi*100)+'% ROI · n'+b.n};   // nur klar -EV (<=-10%); knapp negative Stufen (z.B. -5%) bleiben sichtbar mit rotem Chip
  if((+r.conv||0)<=4) return {m:true,reason:'Konv≤4 dünn'};
  return {m:false,reason:''};
}
// ⚠️ 01.09.2026 — EINE Definition. Dieselbe Bedingung stand an zwei Stellen (hier und in
// _pwPublicTopPlays); als der Sharp-Beitrag zum Regler wurde, haette man beide anfassen muessen
// und genau so entstehen zwei Wahrheiten. Jetzt ruft die andere Stelle diese Funktion auf.
//
// Der Zusatz `grade>=1` ist der eigentliche Punkt: `r.sharp` existierte frueher NUR fuer bewiesene
// Wallets — der Regler laesst jetzt auch vielversprechende durch. Fuers Abwaegen ist das gewollt,
// fuer den OEFFENTLICHEN Kanal nicht: dort kostet ein Fehlalarm Glaubwuerdigkeit. Ohne diese Zeile
// haette die Lockerung still die Public-Schwelle mitgesenkt — die Bauform „eine Aenderung sickert
// in eine Flaeche, fuer die sie nie gedacht war".
function _pwTermIsPublic(r){
  return !!(r && r.conv>=PW_PUBLIC_MIN_CONV && r.moneyPct>=0.60
            && r.sharp && r.sharp.n>=8 && r.sharp.hit>=0.55
            && (r.sharp.grade==null || r.sharp.grade>=1));   // nur BEWIESEN geht oeffentlich
}

// 18.08.2026 (Lucas) Slice 2 — Drilldown: Preis-Kurve (Variante A: Poly vs faire Pinnacle + Kante-Fläche),
// Konviktions-Aufschlüsselung, Whale-Tape, ½-Kelly. Rein lesend & additiv.
let _pwTermRow=null;
function _pwTermOpen(k){ _pwTermRow=(String(_pwTermRow)===String(k))?null:k; _pwRender(); }
if(typeof window!=='undefined') window._pwTermOpen=_pwTermOpen;

function _pwTermHist(key){ const c=_pwCache||{}; return (c.broadLiveHist&&c.broadLiveHist[key])||(c.broadHist&&c.broadHist[key])||[]; }
function _pwTermFair(r){
  const cs=_pwCache&&_pwCache.crossSport, disc=(cs&&cs.discrepancies)||[];
  const side=String(r.side||'').toLowerCase();
  for(const d of disc){ if(!d) continue; const oc=String(d.outcome||'').toLowerCase();
    if(oc&&side&&(oc.includes(side)||side.includes(oc))&&typeof d.pinnPP==='number') return d.pinnPP/100; }
  return null;
}
function _pwTermCurve(r){
  const H=_pwTermHist(r.key).filter(s=>s&&s.p&&typeof s.p[r.side]==='number');
  if(H.length<2) return '<div style="color:#484f58;font-size:11px;padding:8px 2px">Zu wenig Preis-Verlauf für eine Kurve (sammelt über die Runner-Läufe).</div>';
  const fair=_pwTermFair(r);
  const W=520,Hh=160,pl=40,pr=64,pt=14,pb=26,cw=W-pl-pr,ch=Hh-pt-pb;
  const t0=Date.parse(H[0].ts), t1=Date.parse(H[H.length-1].ts)||t0+1;
  const ps=H.map(s=>s.p[r.side]); let mn=Math.min.apply(null,ps),mx=Math.max.apply(null,ps);
  if(fair!=null){ mn=Math.min(mn,fair); mx=Math.max(mx,fair); }
  const pad=(mx-mn)*0.18||0.04; mn-=pad; mx+=pad; if(mx<=mn) mx=mn+0.04;
  const X=t=>pl+((t-t0)/((t1-t0)||1))*cw, Y=p=>pt+(mx-p)/(mx-mn)*ch;
  const line=H.map((s,i)=>(i?'L':'M')+X(Date.parse(s.ts)).toFixed(1)+' '+Y(s.p[r.side]).toFixed(1)).join(' ');
  const lp=H[H.length-1].p[r.side];
  let ticks=''; for(let i=0;i<3;i++){ const pv=mn+(mx-mn)*(i/2), yy=Y(pv);
    ticks+='<line x1="'+pl+'" y1="'+yy.toFixed(1)+'" x2="'+(pl+cw)+'" y2="'+yy.toFixed(1)+'" stroke="#21262d" stroke-width=".5"/><text x="'+(pl-6)+'" y="'+(yy+3).toFixed(1)+'" text-anchor="end" font-size="9" fill="#484f58" font-family="monospace">'+Math.round(pv*100)+'¢</text>'; }
  let wedge='',fairEl='',edgeEl='';
  if(fair!=null&&fair>lp){ const yf=Y(fair);
    wedge='<path d="'+line+' L'+X(t1).toFixed(1)+' '+yf.toFixed(1)+' L'+X(t0).toFixed(1)+' '+yf.toFixed(1)+' Z" fill="rgba(63,185,80,.15)"/>';
    fairEl='<line x1="'+pl+'" y1="'+yf.toFixed(1)+'" x2="'+(pl+cw)+'" y2="'+yf.toFixed(1)+'" stroke="#5eead4" stroke-width="1.3" stroke-dasharray="5 3"/><text x="'+(pl+cw+4)+'" y="'+(yf+3).toFixed(1)+'" font-size="9" fill="#5eead4" font-family="monospace">faire Pinnacle '+Math.round(fair*100)+'¢</text>';
    edgeEl='<text x="'+(pl+cw+4)+'" y="'+((Y(lp)+yf)/2).toFixed(1)+'" font-size="9.5" fill="#3fb950" font-family="monospace" font-weight="700">+'+Math.round((fair-lp)*100)+'¢</text>'; }
  const dot='<circle cx="'+X(t1).toFixed(1)+'" cy="'+Y(lp).toFixed(1)+'" r="4" fill="#a78bfa"/><text x="'+(X(t1)-6).toFixed(1)+'" y="'+(Y(lp)-7).toFixed(1)+'" text-anchor="end" font-size="10.5" fill="#a78bfa" font-family="monospace" font-weight="700">Poly '+Math.round(lp*100)+'¢</text>';
  return '<svg viewBox="0 0 '+W+' '+Hh+'" style="width:100%;max-width:'+W+'px;display:block">'+ticks+wedge
    +'<path d="'+line+'" fill="none" stroke="#a78bfa" stroke-width="2"/>'+fairEl+edgeEl+dot
    +'<text x="'+pl+'" y="'+(Hh-6)+'" font-size="8.5" fill="#484f58">Opening</text><text x="'+(pl+cw)+'" y="'+(Hh-6)+'" text-anchor="end" font-size="8.5" fill="#484f58">jetzt</text></svg>';
}
function _pwTermWhaleTape(r){
  const m=(_pwCache&&_pwCache.broadLive&&_pwCache.broadLive[r.key])||null;
  const wh=(m&&Array.isArray(m.whales))?m.whales.slice():[];
  if(!wh.length) return '<span style="color:#484f58;font-size:11px">keine Whale-Positionen erfasst</span>';
  const sc=(_pwCache&&_pwCache.walletTrack&&_pwCache.walletTrack.scores)||{};
  wh.sort((a,b)=>(b.usd||0)-(a.usd||0));
  return wh.slice(0,6).map((w,i)=>{
    const raw=sc[w.wallet], n=(raw&&raw.n)||0;
    const hit=n?Math.round((raw.wins||0)/n*100):null, clv=n?(raw.clvSumPP/n):null;
    const medal=i===0?'🥇':i===1?'🥈':i===2?'🥉':'&nbsp;&nbsp;';
    const onSide=(w.side===r.side);
    const trk=n>=8?(' <span style="color:#484f58">· '+hit+'% n'+n+(clv!=null?' · CLV '+(clv>=0?'+':'')+clv.toFixed(1):'')+'</span>'):' <span style="color:#484f58">· neu</span>';
    const wl=String(w.wallet||'');
    return '<div style="font-family:ui-monospace,monospace;font-size:11.5px;line-height:1.95">'+medal+' <span style="color:'+(onSide?'#a78bfa':'#6e7681')+'">'+wl.slice(0,6)+'…'+wl.slice(-3)+'</span> '+_pwUsd(w.usd)+(onSide?'':' <span style="color:#e3b341;font-size:10px">⟂ '+_pwEsc(w.side)+'</span>')+trk+'</div>';
  }).join('');
}
function _pwTermConvPanel(r){
  const col=r.conv>=8?'#3fb950':r.conv>=6?'#e3b341':'#8b949e';
  const reasons=(r.reasons||[]).map(x=>'<div style="font-size:11px;color:#8b949e;line-height:1.7">• '+_pwEsc(x)+'</div>').join('');
  // 21.08.2026 (Lucas): Betfair-Geld-Gegencheck sichtbar (bestaetigt / dagegen / kein Match).
  let bfLine='';
  if(r.bf){
    bfLine = r.bf.agree
      ? '<div style="font-size:11px;color:#3fb950;line-height:1.7;margin-top:4px">💷 Betfair bestätigt · '+r.bf.pct+'% · '+_pwBfEur(r.bf.eur)+'</div>'
      : '<div style="font-size:11px;color:#e3742f;line-height:1.7;margin-top:4px">💷 Betfair-Geld auf '+_pwEsc(r.bf.name)+' ('+r.bf.pct+'%) — Gegenseite</div>';
  }
  return '<div style="text-align:center;margin-bottom:6px"><div style="font-size:26px;font-weight:900;font-family:ui-monospace,monospace;color:'+col+'">'+r.conv+'<span style="font-size:13px;color:#484f58">/10</span></div></div>'+(reasons||'<div style="font-size:11px;color:#484f58">—</div>')+bfLine;
}
// 18.08.2026 (Lucas, Arkham-Inspiration) Slice 3 — Orderbuch/Spread/Liquidität + gelabeltes Trade-Tape.
// Frontend liest m.book (bids/asks/spread) + m.trades vom Runner; fehlt es → „sammelt".
// Plus Wettbewerbs-Badge (Sport-Emoji + kurzes Liga-Kürzel) statt nur ⚽.
const _PW_LEAGUE_ABBR = [
  [/uefa champions|champions league|\bucl\b/i,'UCL','#5b8def'],
  [/europa league|\buel\b/i,'UEL','#e3742f'],
  [/premier league|\bepl\b|english premier/i,'EPL','#3fb950'],
  [/la ?liga/i,'LaLiga','#e3b341'],
  [/serie a/i,'SerieA','#4cc2ff'],
  [/bundesliga/i,'BL','#f85149'],
  [/ligue ?1/i,'L1','#a78bfa'],
  [/eredivisie/i,'ERE','#e3742f'],
  [/\bmls\b/i,'MLS','#4cc2ff'],
  [/counter-?strike|\bcs2\b|csgo|cs:go/i,'CS2','#e3b341'],
  [/league of legends|\blol\b|\blck\b|\blpl\b|\blec\b/i,'LoL','#c9a227'],
  [/dota/i,'Dota','#f85149'],
  [/valorant|\bval\b/i,'VAL','#f85149'],
  [/\batp\b/i,'ATP','#3fb950'],
  [/\bwta\b/i,'WTA','#a78bfa'],
  [/\bmlb\b|baseball/i,'MLB','#4cc2ff'],
  [/\bnba\b|basketball/i,'NBA','#e3742f'],
  [/\bnfl\b|american football/i,'NFL','#3fb950'],
  [/\bnhl\b|ice ?hockey/i,'NHL','#4cc2ff'],
];
function _pwLeagueBadge(league, sport, hint){
  const emoji=_pwSportIcon(sport||league||hint);
  const hay=String(league||'')+' '+String(hint||'');
  let abbr='',col='#6e7681';
  for(let i=0;i<_PW_LEAGUE_ABBR.length;i++){ const e=_PW_LEAGUE_ABBR[i]; if(e[0].test(hay)){ abbr=e[1]; col=e[2]; break; } }
  if(!abbr){ const L=String(league||'').replace(/[^A-Za-z0-9 ]/g,'').trim();
    if(L && !/^espo?rts?$/i.test(L)) abbr=L.split(/\s+/).filter(Boolean).slice(0,2).map(w=>w[0]).join('').toUpperCase().slice(0,3); }
  return '<span style="display:inline-flex;align-items:center;gap:4px;white-space:nowrap">'+emoji
    +(abbr?'<span style="font-size:8px;font-weight:800;letter-spacing:.02em;color:'+col+';border:1px solid '+col+'66;background:'+col+'1f;padding:0 4px;border-radius:4px">'+_pwEsc(abbr)+'</span>':'')+'</span>';
}

function _pwTermBook(r){
  const m=(_pwCache&&_pwCache.broadLive&&_pwCache.broadLive[r.key])||null, b=m&&m.book;
  if(!b||!Array.isArray(b.asks)||!Array.isArray(b.bids)||(!b.asks.length&&!b.bids.length))
    return '<div style="color:#484f58;font-size:11px">Orderbuch: sammelt (Runner erfasst Tiefe je Play-Markt).</div>';
  const all=b.asks.concat(b.bids).map(x=>x[1]||0), maxSz=Math.max.apply(null,all)||1;
  const row=(p,sz,side)=>{ const w=Math.round((sz/maxSz)*100), col=side==='ask'?'#f85149':'#3fb950';
    return '<div style="position:relative;display:flex;justify-content:space-between;font-family:ui-monospace,monospace;font-size:11px;padding:2px 7px">'
      +'<span style="position:absolute;top:0;bottom:0;'+(side==='ask'?'right':'left')+':0;width:'+w+'%;background:'+col+'14"></span>'
      +'<span style="position:relative;color:'+col+'">'+Math.round(p*100)+'¢</span><span style="position:relative;color:#8b949e">'+_pwUsd(sz)+'</span></div>'; };
  const asks=b.asks.slice(0,4).slice().reverse().map(x=>row(x[0],x[1],'ask')).join('');
  const bids=b.bids.slice(0,4).map(x=>row(x[0],x[1],'bid')).join('');
  const spC=(b.ask!=null&&b.bid!=null)?Math.round((b.ask-b.bid)*100):null;
  const spPct=(b.spreadPct!=null)?b.spreadPct:(b.ask&&spC!=null?spC/(b.ask*100)*100:null);
  const liq=(spPct!=null&&spPct<=3)?'<span style="color:#3fb950;font-weight:700">liquide</span>'
    :(spPct!=null&&spPct<=6)?'<span style="color:#e3b341;font-weight:700">mittel</span>':'<span style="color:#f85149;font-weight:700">eng</span>';
  const mid='<div style="display:flex;justify-content:space-between;font-family:ui-monospace,monospace;font-size:10.5px;color:#8b949e;border-top:1px solid #21262d;border-bottom:1px solid #21262d;padding:3px 7px;margin:2px 0">'
    +'<span>Spread '+(spC!=null?spC+'¢':'—')+(spPct!=null?' ('+spPct.toFixed(1)+'%)':'')+'</span>'+liq+'</div>';
  return asks+mid+bids;
}

function _pwTermTape(r){
  const m=(_pwCache&&_pwCache.broadLive&&_pwCache.broadLive[r.key])||null;
  const tr=(m&&Array.isArray(m.trades))?m.trades.slice(0,7):[];
  const _ago=t=>{ if(t.tsAgo) return t.tsAgo; var ts=t.ts; if(ts==null) return ''; var ms;
    if(typeof ts==='number'||/^\d+$/.test(String(ts))){ var n=Number(ts); ms=n<1e12?n*1000:n; } else { ms=Date.parse(ts); }
    if(isNaN(ms)) return ''; var mi=Math.max(0,Math.round((Date.now()-ms)/60000)); return mi<60?mi+'m':Math.floor(mi/60)+'h'; };
  if(!tr.length) return '<div style="color:#484f58;font-size:11px">Trade-Tape: sammelt (letzte große Käufe/Verkäufe je Markt).</div>';
  const sc=(_pwCache&&_pwCache.walletTrack&&_pwCache.walletTrack.scores)||{};
  return tr.map(t=>{ const buy=(t.action?String(t.action).toUpperCase()!=='SELL':t.buy!==false);
    const onSide=(t.side===r.side); const raw=sc[t.wallet], sharp=!!(raw&&raw.n>=8);
    const wl=String(t.wallet||''), name=t.label||(wl?wl.slice(0,6)+'…'+wl.slice(-3):'?'), col=buy?'#3fb950':'#f85149';
    return '<div style="display:flex;align-items:center;gap:8px;font-family:ui-monospace,monospace;font-size:11px;line-height:1.95">'
      +'<span style="color:#484f58;min-width:52px">'+_pwEsc(_ago(t))+'</span>'
      +'<span style="flex:1;color:'+(sharp?'#a78bfa':'#8b949e')+';overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+_pwEsc(name)+(sharp?' 🔥':'')+'</span>'
      +'<span style="color:'+col+';font-weight:800;min-width:34px">'+(buy?'BUY':'SELL')+'</span>'
      +'<span style="color:'+(onSide?'#4cc2ff':'#6e7681')+';min-width:60px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+_pwEsc(t.side||'')+'</span>'
      +'<span style="color:#8b949e;min-width:30px;text-align:right">'+Math.round((t.price||0)*100)+'¢</span>'
      +'<span style="color:#e6edf3;font-weight:700;min-width:54px;text-align:right">'+_pwUsd(t.usd)+'</span></div>';
  }).join('');
}

function _pwTermDrawer(r){
  const fair=_pwTermFair(r), poly=r.price;
  const box='background:#0f1626;border:1px solid #21262d;border-radius:10px;padding:11px 13px';
  let kelly;
  if(fair!=null&&poly!=null&&fair>poly&&poly<1){ const f=(fair-poly)/(1-poly), hk=Math.max(0,f/2);
    kelly='<div style="font-size:20px;font-weight:900;color:#3fb950;font-family:ui-monospace,monospace">'+(hk*100).toFixed(1)+'%</div><div style="font-size:10.5px;color:#8b949e;margin-top:2px">½-Kelly der Bankroll · Edge +'+Math.round((fair-poly)*100)+'¢</div>';
  } else { kelly='<div style="font-size:15px;font-weight:800;color:#484f58">kein Stake</div><div style="font-size:10.5px;color:#8b949e;margin-top:2px">'+(fair==null?'kein Pinnacle-Anker':'keine positive Kante')+'</div>'; }
  return '<div style="padding:12px 4px 6px">'
    +'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">'
      +'<div style="flex:2;min-width:300px;'+box+'"><div style="font-size:11px;color:#484f58;margin-bottom:4px">Poly-Preis '+_pwEsc(r.side)+(fair!=null?' vs. faire Pinnacle · grüne Fläche = Kante':' — reine Poly-Sicht (kein Pinnacle-Anker)')+'</div>'+_pwTermCurve(r)+'</div>'
      +'<div style="flex:1;min-width:150px;'+box+'"><div style="font-size:11px;color:#484f58;margin-bottom:2px">Konviktion — warum</div>'+_pwTermConvPanel(r)+'</div>'
      +'<div style="flex:1;min-width:130px;'+box+';display:flex;flex-direction:column;justify-content:center;text-align:center">'+kelly+'</div>'
    +'</div>'
    +'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">'
      +'<div style="flex:1;min-width:230px;'+box+'"><div style="font-size:11px;color:#484f58;margin-bottom:6px">📖 Orderbuch '+_pwEsc(r.side)+' — Ausführbarkeit (Spread &amp; Tiefe)</div>'+_pwTermBook(r)+'</div>'
      +'<div style="flex:1;min-width:230px;'+box+'"><div style="font-size:11px;color:#484f58;margin-bottom:6px">🐋 Whale-Tape — wer steht drin (nach Einsatz · Track wenn n≥8 · ⟂ Gegenseite)</div>'+_pwTermWhaleTape(r)+'</div>'
    +'</div>'
    +'<div style="'+box+'"><div style="font-size:11px;color:#484f58;margin-bottom:6px">⚡ Live-Trades — frischer Fluss (BUY grün / SELL rot · 🔥 = scharfe Wallet · blau = auf unserer Seite)</div>'+_pwTermTape(r)+'</div>'
  +'</div>';
}

// 18.08.2026 (Lucas): Terminal-Linsen — nichts verlieren. Kanten=signal-gated (Heute wetten) ·
// Geld/Bewegung/Live = volles Markt-Universum (broadLive), gleiche Spalten, andere Auswahl+Sortierung.
let _pwTermLens='kanten';
function _pwTermSetLens(l){ _pwTermLens=l; _pwTermRow=null; _pwRender(); }
if(typeof window!=='undefined') window._pwTermSetLens=_pwTermSetLens;

function _pwMarketSteam(key, side){
  const c=_pwCache||{}; const H=(c.broadLiveHist&&c.broadLiveHist[key])||(c.broadHist&&c.broadHist[key])||[];
  if(H.length<2) return null; const a=H[0], b=H[H.length-1];
  const p1=a.p&&a.p[side], p2=b.p&&b.p[side];
  if(typeof p1!=='number'||typeof p2!=='number') return null; return (p2-p1)*100;
}
// Markt (broadLive) -> Play-artige Zeile. Conviction via Engine falls sie greift, sonst null („kein Signal").
function _pwMarketRow(key, m){
  if(!m) return null; const shares=m.shares||{}, prices=m.prices||{};
  let fav=null,fu=-1; for(const k in shares){ if((+shares[k]||0)>fu){fu=+shares[k]; fav=k;} }
  if(fav==null){ let pm=-1; for(const k in prices){ if((+prices[k]||0)>pm){pm=+prices[k]; fav=k;} } }
  if(fav==null) return null;
  const tot=Object.keys(shares).reduce((a,k)=>a+(+shares[k]||0),0);
  const moneyPct=tot>0?(+shares[fav]||0)/tot:null;
  let conv=null, reasons=[], sharp=null;
  try{ const sc=_pwShortlistScore(key, m); if(sc&&typeof sc.conv==='number'){ conv=sc.conv; reasons=sc.reasons||[]; sharp=sc.sharp||null; } }catch(e){}
  const match=_pwPlayLabel(key, Object.keys(prices).map(s=>({s})));
  return {key, match, side:fav, conv, reasons, moneyPct, sharp,
          price:(typeof prices[fav]==='number'?prices[fav]:null),
          vol:m.totalUsd||0, htk:_pwRealHtk(m), league:m.league, sport:m.sport};
}
// 18.08.2026 (Lucas): fuer laufende Spiele in Geld/Bewegung die FRISCHE Live-Poly bevorzugen, sonst
// zeigt das Terminal den eingefrorenen Close-Preis auf einem Live-Spiel. Preise/Shares/Volumen/Zeit aus
// live, Liga/Sport/uebriges aus close behalten (falls live sie nicht traegt). Kanten bleibt unberuehrt.
function _pwLivePreferred(m, lnm){
  if(!lnm) return m;
  return Object.assign({}, m, {
    prices:(lnm.prices||m.prices), shares:(lnm.shares||m.shares),
    totalUsd:(lnm.totalUsd!=null?lnm.totalUsd:m.totalUsd),
    whales:(lnm.whales||m.whales), capturedAt:(lnm.capturedAt||m.capturedAt), _live:true });
}
function _pwTermRows(lens){
  const useSP=(_pwSportFilter && _pwSportFilter!=='all');
  if(lens==='kanten'){
    return _pwTopPlays(0, _pwCache&&_pwCache.broadLive, useSP)
      .map(r=>({r, mute:_pwTermMuted(r), pub:_pwTermIsPublic(r)}));
  }
  // Live-Linse zieht aus dem LAUFENDEN Universum (broadLiveNow = poly_money_broad_live.json),
  // NICHT aus broadLive (=close.json, nur kommende Maerkte). Sonst waere Live immer leer, obwohl
  // der Live-Reiter Maerkte hat — genau das darf nicht verloren gehen. Gleiche Filter wie Live-Reiter.
  const uni=(lens==='live')?((_pwCache&&_pwCache.broadLiveNow)||{}):((_pwCache&&_pwCache.broadLive)||{});
  const rows=[];
  for(const k in uni){ const m=uni[k];
    if(!m||m.resolved!=null||_pwKoStale(m)) continue;
    let mrow=m;
    if(lens==='live'){
      if(!m.shares||(m.totalUsd||0)<5000||_pwLiveDecided(m)||_pwLiveGone(m)) continue;
      if(useSP && !_pwSportPass(m.league,m.sport)) continue;
    } else {
      if((_pwRealHtk(m)||0)<0){ const lnm=_pwCache&&_pwCache.broadLiveNow&&_pwCache.broadLiveNow[k];
        if(!lnm||_pwLiveGone(lnm)) continue;
        mrow=_pwLivePreferred(m,lnm); }   // laufendes Spiel -> frische Live-Poly statt Close-Freeze
      if(_pwSportCategory(m.league,m.sport)==='Sonstige') continue;
      if(useSP && !_pwSportPass(m.league,m.sport)) continue;
    }
    const r=_pwMarketRow(k,mrow); if(!r) continue;
    if(lens==='bewegung'){ r._steam=_pwMarketSteam(k,r.side); if(r._steam==null||Math.abs(r._steam)<1) continue; }
    rows.push({r, mute:{m:false,reason:''}, pub:_pwTermIsPublic(r)});
  }
  if(lens==='geld') rows.sort((a,b)=>(b.r.vol||0)-(a.r.vol||0));
  else if(lens==='bewegung') rows.sort((a,b)=>Math.abs(b.r._steam||0)-Math.abs(a.r._steam||0));
  else if(lens==='live') rows.sort((a,b)=>(b.r.vol||0)-(a.r.vol||0));
  return rows.slice(0,40);
}
function _pwTermMeter(conv){
  if(conv==null) return '<span style="display:inline-flex;align-items:center;gap:6px"><span style="width:46px;height:6px;background:#161b22;border-radius:3px;display:inline-block"></span><span style="color:#484f58;font-size:11px">—</span></span>';
  const c=conv>=8?'#3fb950':conv>=6?'#e3b341':'#8b949e';
  return '<span style="display:inline-flex;align-items:center;gap:6px"><span style="width:46px;height:6px;background:#161b22;border-radius:3px;overflow:hidden;display:inline-block"><span style="display:block;height:6px;width:'+(Math.max(0,Math.min(10,conv))*10)+'%;background:'+c+'"></span></span><span style="font-family:ui-monospace,monospace;font-weight:800;color:'+c+';font-size:11.5px">'+conv+'</span></span>';
}

function _pwTerminal(){
  const lens=_pwTermLens||'kanten';
  const _lensDef={kanten:['🎯 Kanten','handelbare Kanten — signal-gated (dieselbe „Heute wetten"-Engine), nach Conviction & CLV-Stufe.'],
                  geld:['💰 Geld','ALLE Märkte nach Zufluss — auch ohne Signal. Konviktion/Edge/CLV daneben zeigen, ob was dahintersteckt.'],
                  bewegung:['📈 Bewegung','ALLE Märkte nach Steam (Preis-Move) — wohin das Geld zieht.'],
                  live:['⚡ Live','laufende Spiele nach Zufluss.']};
  const rowsAll=_pwTermRows(lens);
  const isK=(lens==='kanten');
  let rows=rowsAll.slice();
  if(isK) rows.sort((a,b)=>{ const am=a.mute.m?1:0,bm=b.mute.m?1:0; if(am!==bm) return am-bm; return (b.r.conv||0)-(a.r.conv||0); });
  const nMuted=isK?rows.filter(x=>x.mute.m).length:0;
  const shown=(isK&&_pwTermHideMuted)?rows.filter(x=>!x.mute.m):rows;

  const lbtn=(id)=>{ const on=id===lens, d=_lensDef[id]; return '<button onclick="_pwTermSetLens(\''+id+'\')" style="padding:5px 12px;border:1px solid '+(on?'#a78bfa':'#21262d')+';background:'+(on?'rgba(167,139,250,.14)':'transparent')+';color:'+(on?'#a78bfa':'#8b949e')+';font-size:12px;font-weight:700;cursor:pointer;border-radius:0">'+d[0]+'</button>'; };
  const lensBar='<div style="display:inline-flex;border-radius:9px;overflow:hidden;border:1px solid #21262d;margin:2px 0 10px">'+['kanten','geld','bewegung','live'].map(lbtn).join('')+'</div>';

  const agg=(_pwCache&&_pwCache.shortlistTrack&&_pwCache.shortlistTrack.agg)||{};
  const pub=agg.public||{}, allA=agg.all||{};
  const kpi=(v,lbl,col,sub)=>'<div style="flex:1;min-width:128px;background:#0d1117;border:1px solid #21262d;border-left:3px solid '+col+';border-radius:10px;padding:11px 13px"><div style="font-size:20px;font-weight:900;color:'+col+';line-height:1.1">'+v+'</div><div style="font-size:10px;color:#8b949e;text-transform:uppercase;letter-spacing:.4px;margin-top:4px">'+lbl+'</div>'+(sub?'<div style="font-size:10px;color:#6e7681;margin-top:1px">'+sub+'</div>':'')+'</div>';
  const pctS=x=>x==null?'—':(x>=0?'+':'')+(Math.round(x*1000)/10)+'%';
  const kpiBand=isK?('<div style="display:flex;gap:10px;flex-wrap:wrap;margin:2px 0 14px">'
    +kpi(pctS(pub.roi),'ROI Public-Segment',(pub.roi>=0?'#3fb950':'#f85149'),'n'+(pub.n||0)+' · CLV '+((pub.clvAvg!=null)?(pub.clvAvg>=0?'+':'')+pub.clvAvg:'—'))
    +kpi(pctS(allA.roi),'ROI ganze Shortlist',(allA.roi>=0?'#3fb950':'#f85149'),'n'+(allA.n||0)+' · Rauschen inkl.')
    +kpi(String(rows.length-nMuted),'handelbare Plays jetzt','#a78bfa',nMuted?(nMuted+' gemutet'):'nichts gemutet')+'</div>'):'';

  const th=(t,a)=>'<th style="font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;color:#484f58;font-weight:700;text-align:'+(a||'right')+';padding:7px 9px;border-bottom:1px solid #21262d;white-space:nowrap">'+t+'</th>';
  let out='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🖥️ Terminal — '+_lensDef[lens][0].replace(/^\S+\s/,'')+'</span>'
    +'<span class="pw-sec-note">'+_lensDef[lens][1]+' · Zeile klicken → Drilldown · alte Reiter bleiben, nichts geht verloren</span></div>';
  out+=lensBar+kpiBand;
  if(isK&&nMuted) out+='<div style="display:flex;align-items:center;gap:8px;margin:0 0 10px;font-size:11.5px;color:#8b949e"><label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" '+(_pwTermHideMuted?'checked':'')+' onclick="_pwTermMute(this.checked)"/> '+nMuted+' gemutete (historisch -EV) ausblenden</label></div>';
  if(!shown.length) return out+'<div class="pw-none">'+(isK?'Aktuell keine klare Gelegenheit — die Shortlist lebt von Steam &amp; scharfen Wallets.':'Keine Märkte in dieser Linse gerade.')+'</div></section>';

  const flHead=lens==='bewegung'?'Steam':'Geld / Fluss';
  out+='<div class="pw-tw"><table class="pw-tbl" style="width:100%"><thead><tr>'
    +th('Anpfiff','left')+th('Spiel','left')+th('Pick','left')+th('Konviktion')+th(flHead)+th('CLV-Bucket')+th('Einstieg')+'</tr></thead><tbody>';
  let mutedStarted=false;
  shown.forEach(x=>{
    const r=x.r; const open=(String(_pwTermRow)===String(r.key));
    if(isK&&x.mute.m && !mutedStarted){ mutedStarted=true;
      out+='<tr><td colspan="7" style="padding:10px 9px 4px;font-size:10px;color:#484f58;border-top:1px dashed #21262d">🔇 Gemutet — Conviction-Stufe historisch -EV (dein Track) oder zu dünn.</td></tr>'; }
    const meter=_pwTermMeter(r.conv);
    const b=(r.conv!=null)?_pwTermBucket(r.conv):null;
    const clv=(b&&b.n>=20)
      ? '<span style="font-family:ui-monospace,monospace;font-size:10.5px;font-weight:700;padding:1px 6px;border-radius:5px;color:'+(b.roi>0?'#3fb950':b.roi<0?'#f85149':'#8b949e')+';background:'+(b.roi>0?'rgba(63,185,80,.1)':b.roi<0?'rgba(248,81,73,.1)':'transparent')+'">'+(b.roi>0?'🟢':b.roi<0?'🔴':'⚪')+' '+(b.roi>=0?'+':'')+Math.round(b.roi*100)+'% · n'+b.n+'</span>'
      : '<span style="color:#484f58;font-size:10px">'+(b?('dünn n'+b.n):'—')+'</span>';
    const htk=r.htk!=null?(r.htk<0?'<span style="color:#f85149;font-weight:700">● LIVE</span>':r.htk<1?'<1h':Math.round(r.htk)+'h'):'—';
    const price=(r.price!=null)?Math.round(r.price*100)+'¢':'—';
    const mk='<a href="https://polymarket.com/event/'+encodeURIComponent(r.key)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681" title="Markt öffnen ↗">'+_pwEsc(r.match)+' <span style="color:#a78bfa">↗</span></a>';
    let fluss;
    if(lens==='bewegung'){ const st=r._steam||0, up=st>=0; fluss='<span style="color:'+(up?'#3fb950':'#f85149')+';font-weight:700">'+(up?'▲ ':'▼ ')+(st>=0?'+':'')+st.toFixed(1)+'pp</span>'; }
    else { const moneyPct=(r.moneyPct!=null)?Math.round(r.moneyPct*100)+'%':'—'; fluss=_pwUsd(r.vol)+' <span class="pw-mut" style="font-size:10px">'+moneyPct+'</span>'; }
    out+='<tr onclick="_pwTermOpen(\''+r.key+'\')" style="cursor:pointer;opacity:'+((isK&&x.mute.m)?'0.5':'1')+';background:'+(open?'rgba(167,139,250,.06)':'transparent')+'">'
      +'<td class="pw-cn" style="text-align:left;font-family:ui-monospace,monospace;color:#8b949e"><span style="color:#484f58;margin-right:3px">'+(open?'▾':'▸')+'</span>'+htk+'</td>'
      +'<td style="white-space:nowrap">'+_pwLeagueBadge(r.league,r.sport,r.match)+' '+mk+(x.pub?' <span title="Public-Kandidat" style="color:#a78bfa">◆</span>':'')+'</td>'
      +'<td class="pw-cm" style="font-weight:700;color:#4cc2ff">'+_pwEsc(r.side)+((isK&&x.mute.m)?' <span style="font-family:system-ui;font-size:8.5px;color:#484f58;border:1px solid #21262d;padding:0 4px;border-radius:4px">🔇 '+_pwEsc(x.mute.reason)+'</span>':'')+'</td>'
      +'<td class="pw-cn">'+meter+'</td>'
      +'<td class="pw-cn" style="font-family:ui-monospace,monospace">'+fluss+'</td>'
      +'<td class="pw-cn">'+clv+'</td>'
      +'<td class="pw-cn pw-mut" style="font-family:ui-monospace,monospace">'+price+'</td></tr>';
    if(open) out+='<tr><td colspan="7" style="background:rgba(167,139,250,.03);padding:0 9px 6px">'+_pwTermDrawer(r)+'</td></tr>';
  });
  out+='</tbody></table></div>';
  out+='<div style="font-size:10px;color:#484f58;margin-top:9px;line-height:1.5">'+(isK
    ?'Gleiche Engine wie 🔥 Heute wetten (Algo unverändert). Muten = ausgrauen &amp; nach unten (nie löschen), aus deinem Paper-Track.'
    :'Linse „'+_lensDef[lens][0]+'" = volles Markt-Universum, nicht signal-gefiltert. Konviktion „—" = kein Wett-Signal (nur Geld/Bewegung). So geht nichts verloren, was in Großes-Geld/Bewegung/Live steht.')+'</div></section>';
  return out;
}

function _pwShortlist(live){
  const intro='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🔥 Heute wetten — die klarsten Gelegenheiten</span>'
    +'<span class="pw-sec-note">nur Märkte mit echtem Signal (Steam · scharfe Wallet · Geld-vs-Preis) · BET = mit dem Geld, FADE = dagegen · Conviction 0–10 · nichts blind, das ist ein Ausgangspunkt</span></div>';
  const all=_pwTopPlays(0, live, true);   // 0 = alle · sportPass-Filter an (View hat Sport-Filter)
  if(!all.length) return intro+'<div class="pw-none">Aktuell keine klare Gelegenheit. Die Shortlist lebt von <b>📈 Steam</b> und <b>🐋 scharfen Wallets</b> — die sammeln sich noch über die Runner-Läufe (auf Poly ist der Preis ≈ die Geld-Verteilung, daher braucht es die dynamischen Signale). Bis dahin: schau in <b>💰 Großes Geld</b>, <b>📈 Bewegung</b> und <b>🐋 Whales</b>. <b>Kein Signal ist auch ein Ergebnis</b> — dann nicht wetten.</div></section>';
  // 05.08.2026 (Lucas: entscheidungsreifer): Einstiegspreis + Spielraum je Zeile, staerkster Play (Index 0,
  // nach Conviction sortiert) mit ⭐ + Highlight. eng = >=85¢ kaum Raum · Auß. = <=35¢ Aussenseiter-Seite.
  const body=all.slice(0,20).map((r,ix)=>{
    const bet=r.verdict==='BET'; const vc=bet?'#3fb950':'#e3b341'; const top=ix===0;
    const badge='<span style="display:inline-block;padding:2px 9px;border-radius:12px;border:1px solid '+vc+';color:'+vc+';font-weight:800;font-size:11px">'+r.verdict+'</span>';
    const convCol=r.conv>=8?'#3fb950':r.conv>=6?'#e3b341':'#8b949e';
    const mk='<a href="https://polymarket.com/event/'+encodeURIComponent(r.key)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681" title="Markt öffnen ↗">'+_pwEsc(r.match)+' <span style="color:#a78bfa">↗</span></a>';
    const htk=r.htk!=null?(r.htk<0?'live':r.htk<1?'<1h':Math.round(r.htk)+'h'):'—';
    const price=(r.price!=null)?Math.round(r.price*100)+'¢':'—';
    const room=(r.price!=null)?(r.price>=0.85?' <span style="color:#e3b341;font-size:9.5px">eng</span>':r.price<=0.35?' <span style="color:#a78bfa;font-size:9.5px">Auß.</span>':''):'';
    return '<tr'+(top?' style="background:rgba(63,185,80,.07)"':'')+'>'
      +'<td>'+(top?'<span title="stärkster Play">⭐</span> ':'')+badge+'</td>'
      +'<td style="white-space:nowrap">'+_pwSportIcon(r.league)+' '+mk+'</td>'
      +'<td class="pw-cm"><b style="color:#4cc2ff">'+_pwEsc(r.side)+'</b></td>'
      +'<td class="pw-cn pw-mut" style="white-space:nowrap">'+price+room+'</td>'
      +'<td class="pw-cn" style="font-weight:800;color:'+convCol+'">'+r.conv+'/10</td>'
      +'<td style="font-size:12px;color:var(--muted)">'+r.reasons.map(_pwEsc).join(' · ')+'</td>'
      +'<td class="pw-cn pw-mut">'+_pwUsd(r.vol)+'</td>'
      +'<td class="pw-cn pw-mut">'+htk+'</td></tr>';
  }).join('');
  return intro+'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    +'<th>Verdikt</th><th>Spiel</th><th>Empf. Seite</th><th>Einstieg</th><th>Conviction</th><th>Warum</th><th>Vol</th><th>Anpfiff</th>'
    +'</tr></thead><tbody>'+body+'</tbody></table></div></section>';
}

// ① Momentum (25.07.2026, Lucas): was bewegt sich GERADE — aus der globalen Poly-Preis-Zeitreihe
// (poly_money_broad_history.json). Je Markt der stärkste Preis-Move einer Seite über das erfasste
// Fenster; Steam ▲ = letzter Schritt zieht weiter, dreht ▼ = letzter Schritt kehrt um.
function _pwMomentum(hist){
  const intro='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">📈 Was sich gerade bewegt — alle Sportarten</span>'
    +'<span class="pw-sec-note">stärkster Poly-Preis-Move je Markt über die letzten Stunden · ▲ Steam (zieht weiter) vs ▼ dreht (kehrt um) · Klick → Markt</span></div>';
  const rows=[];
  for(const [key,arr] of Object.entries(hist||{})){
    if(!Array.isArray(arr)||arr.length<2) continue;
    const latest=arr[arr.length-1], base=arr[0], prev=arr[arr.length-2];
    const league=latest.league||base.league;
    if(!_pwSportPass(league)) continue;
    // 27.07.2026 (Lucas: „was kommt oder live — fertige Spiele raus"): echten Anpfiff aus dem
    // letzten Snapshot rekonstruieren (ts + htk). >4h nach Anpfiff = Spiel fertig → nicht mehr
    // „was sich GERADE bewegt". History-Retention (96h Steam-Fenster) bleibt, nur die Anzeige filtert.
    if(latest.htk != null){
      const koMs = Date.parse(latest.ts) + latest.htk * 3.6e6;
      if(!isNaN(koMs) && (Date.now() - koMs) > 4 * 3.6e6) continue;
    }
    let best=null;
    for(const side of Object.keys(latest.p||{})){
      const p1=base.p&&base.p[side], p2=latest.p[side];
      if(typeof p1!=='number'||typeof p2!=='number') continue;
      const move=(p2-p1)*100;
      const step=(prev&&typeof prev.p[side]==='number')?(p2-prev.p[side])*100:move;
      // die STEIGENDE Seite zeigen (wohin das Geld strömt) — größter positiver Move gewinnt.
      if(!best||move>best.move) best={side,from:p1,to:p2,move,step};
    }
    if(!best||Math.abs(best.move)<1) continue;   // <1pp = Rauschen
    const spanH=(Date.parse(latest.ts)-Date.parse(base.ts))/3.6e6;
    rows.push({key,league,spanH,htk:latest.htk,vol:latest.v,match:_pwPlayLabel(key,Object.keys(latest.p).map(s=>({s}))),   // 16.08.2026 (Lucas): Prop-aware Label (kein Exact-Score-Zeilen-Leak, kein rohes "Over vs Under")
      side:best.side,from:best.from,to:best.to,move:best.move,step:best.step});
  }
  rows.sort((a,b)=>Math.abs(b.move)-Math.abs(a.move));
  if(!rows.length) return intro+'<div class="pw-none">'+_pwStaleMsg(_pwSportFilter==='all'
    ?'Noch keine Bewegung erfasst — die Preis-Zeitreihe füllt sich über die nächsten Runner-Läufe (min. 2 Snapshots je Markt).'
    :'Keine '+_pwSportFilter+'-Bewegung gerade — Filter „Alle" zeigt wieder alles.')+'</div></section>';
  const body=rows.slice(0,30).map(r=>{
    const up=r.move>=0;
    const mCol=Math.abs(r.move)>=5?'#f85149':Math.abs(r.move)>=3?'#e3b341':'#8b949e';
    const cont=(r.step>0)===(r.move>0)&&Math.abs(r.step)>=0.3;
    const tag=Math.abs(r.step)<0.3?'<span class="pw-mut">→ flach</span>'
      :cont?'<span style="color:#3fb950;font-weight:700">▲ Steam</span>'
      :'<span style="color:#f85149;font-weight:700">▼ dreht</span>';
    const mk='<a href="https://polymarket.com/event/'+encodeURIComponent(r.key)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681" title="Markt öffnen ↗">'+_pwEsc(r.match)+' <span style="color:#a78bfa">↗</span></a>';
    const htk=r.htk!=null?(r.htk<0?'live':r.htk<1?'<1h':Math.round(r.htk)+'h'):'—';
    return '<tr>'
      +'<td style="white-space:nowrap">'+_pwSportIcon(r.league)+' <span class="pw-mut" style="font-size:11px">'+_pwEsc((r.league||'').toUpperCase())+'</span></td>'
      +'<td>'+mk+'</td>'
      +'<td class="pw-cm"><b style="color:#4cc2ff">'+_pwEsc(r.side)+'</b></td>'
      +'<td class="pw-cn pw-mut">'+Math.round(r.from*100)+'¢→'+Math.round(r.to*100)+'¢</td>'
      +'<td class="pw-cn" style="font-weight:800;color:'+mCol+'">'+(up?'+':'')+r.move.toFixed(1)+'pp</td>'
      +'<td class="pw-cm">'+tag+'</td>'
      +'<td class="pw-cn pw-mut">'+(r.spanH>=1?Math.round(r.spanH)+'h':'<1h')+'</td>'
      +'<td class="pw-cn pw-mut">'+htk+'</td></tr>';
  }).join('');
  return intro+'<div class="pw-tw"><table class="pw-tbl"><thead><tr>'
    +'<th>Sport</th><th>Spiel</th><th>Seite</th><th>von→zu</th><th>Move</th><th>Signal</th><th>über</th><th>Anpfiff</th>'
    +'</tr></thead><tbody>'+body+'</tbody></table></div></section>';
}

// 🆕 Was-ist-neu (25.07.2026, Lucas): Aktivitäts-Feed aus den akkumulierten Daten — neue große
// Einstiege (wallet_track.open, firstTs<24h) + gekippte Favoriten (broadHist: führende Seite
// gewechselt). Geräteübergreifend, kein Browser-State. Füllt sich mit den Runner-Läufen.
// Poly-Datenalter (aus dem globalen Money-Scan). Der Scan läuft in Wellen (MLS-Zeiten + Mittag) →
// tagsüber sind die Snapshots oft Stunden alt und die erfassten Märkte schon angepfiffen. Damit die
// Money/Bewegung/Neu-Views nicht stumm leer bleiben, sagen wir ehrlich, dass die Daten alt sind.
function _pwPolyAgeH(){
  const g=_pwCache&&_pwCache.moneyBroad&&_pwCache.moneyBroad.generatedAt;
  const t=g?Date.parse(g):NaN; return isNaN(t)?null:(Date.now()-t)/3.6e6;
}
function _pwStaleMsg(base){
  const a=_pwPolyAgeH();
  if(a!=null && a>2){
    const at=a<1?Math.round(a*60)+' Min':a.toFixed(1)+' h';
    return '⏳ <b>Poly-Daten sind '+at+' alt.</b> Der globale Geld-Scan läuft in Wellen (rund um die MLS-Zeiten ~22–06 UTC + Mittag) — tagsüber sind mehrstündige Lücken normal, dann sind die erfassten Märkte schon angepfiffen. Beim nächsten Lauf erscheinen wieder frische kommende Spiele.';
  }
  return base;
}
const PW_NEW_MIN_USD = 5000;   // „Neu": Dust + Politik-Mini-Positionen raus (Lucas 31.07.2026: „$33-Einstiege wertlos")
// 03.08.2026 (Lucas: „Neu ist nicht aktuell"): der Feed zeigte GROSSE Einstiege nach firstTs (<24h),
// aber ohne Anpfiff-Gate — $300K auf ein MLB-Spiel von GESTERN stand oben als „neu", längst durch.
// Fix: schon angepfiffene/durchgelaufene Spiele raus (rekonstruierter Anpfiff via broadLive-Freeze,
// >4h danach = fertig; Fallback = Datum aus dem Key < heute UTC, falls der Markt nicht mehr im Freeze ist).
function _pwKeyDatePast(key){
  const m=/(\d{4}-\d{2}-\d{2})/.exec(String(key||''));
  return !!m && m[1] < new Date().toISOString().slice(0,10);
}
function _pwEntryOver(e, live){
  const m = live && live[e.key];
  if(m) return _pwKoStale(m);        // echter Anpfiff (capturedAt+hoursToKickoff)
  return _pwKeyDatePast(e.key);      // kein Markt mehr im Freeze → Datum aus dem Key
}
function _pwNewEntries(track, hours, live){
  live = live || (_pwCache && _pwCache.broadLive) || {};
  const open=track&&track.open; if(!open) return [];
  const cutoff=Date.now()-hours*3.6e6, rows=[];
  for(const e of Object.values(open)){
    if(!e||!_pwSportPass(e.league, e.sport)) continue;
    if(_pwSportCategory(e.league, e.sport)==='Sonstige') continue;      // Politik/Krypto (GREATER/ELON …) raus
    if((Number(e.usd)||0) < PW_NEW_MIN_USD) continue;          // Kleckerbeträge raus — „GROSSE Einstiege"
    const t=Date.parse(e.firstTs); if(isNaN(t)||t<cutoff) continue;
    if(_pwEntryOver(e, live)) continue;                        // schon angepfiffen/durch → nicht „neu"
    const sc=_pwWalletScore(e.wallet);
    rows.push({wallet:e.wallet,key:e.key,side:e.side,league:e.league,price:e.firstPrice,usd:e.usd||0,ts:t,
      sharp:_pwIsSharpScore(sc),avgClv:sc?sc.avgClv:null,n:sc?sc.n:0});   // 13.08.2026 (Lucas-Audit): strenges Gate
  }
  return rows.sort((a,b)=>b.usd-a.usd||b.ts-a.ts);            // größte zuerst
}
function _pwFlips(hist){
  const lead=o=>{let s=null,m=-1;for(const k in (o.p||{}))if(typeof o.p[k]==='number'&&o.p[k]>m){m=o.p[k];s=k;}return s;};
  const rows=[];
  for(const [key,arr] of Object.entries(hist||{})){
    if(!Array.isArray(arr)||arr.length<2) continue;
    const base=arr[0], latest=arr[arr.length-1];
    if(!_pwSportPass(latest.league||base.league)) continue;
    if(latest.htk!=null){ const koMs=Date.parse(latest.ts)+latest.htk*3.6e6;   // 03.08.2026 (Lucas): fertige Spiele raus
      if(!isNaN(koMs)&&(Date.now()-koMs)>4*3.6e6) continue; }
    const b=lead(base), l=lead(latest);
    if(!b||!l||b===l) continue;
    rows.push({key,from:b,to:l,league:latest.league||base.league,ts:Date.parse(latest.ts),match:_pwNoDraw(Object.keys(latest.p||{})).join(' vs ')});
  }
  return rows.sort((a,b)=>b.ts-a.ts);
}
function _pwWhatsNew(){
  const ago=t=>{const m=(Date.now()-t)/60000;return m<1?'gerade':m<60?Math.round(m)+'m':Math.round(m/60)+'h';};
  const entries=_pwNewEntries(_pwCache&&_pwCache.walletTrack,24,_pwCache&&_pwCache.broadLive).slice(0,20);
  const flips=_pwFlips(_pwCache&&_pwCache.broadHist).slice(0,15);
  if(!entries.length&&!flips.length)
    return '<section class="pw-sec"><div class="pw-none">'+_pwStaleMsg('Noch nichts Neues erfasst — der Feed zeigt neue große Einstiege (ab '+_pwUsd(PW_NEW_MIN_USD)+') und gekippte Favoriten, sobald die Runner-Läufe Daten liefern.')+'</div></section>';
  let h='';
  if(entries.length){
    const body=entries.map(e=>{
      const wl=_pwWalletChip(e.wallet);
      const mk='<a href="https://polymarket.com/event/'+encodeURIComponent(e.key)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681">'+_pwEsc(e.key)+' <span style="color:#a78bfa">↗</span></a>';
      return '<tr><td class="pw-cn pw-mut">'+ago(e.ts)+'</td>'
        +'<td style="white-space:nowrap">'+_pwSportIcon(e.league)+'</td>'
        +'<td>'+mk+'</td><td>'+(e.sharp?'🔥 ':'')+wl+'</td>'
        +'<td class="pw-cm"><b style="color:#4cc2ff">'+_pwEsc(e.side)+'</b></td>'
        +'<td class="pw-cn pw-mut">'+(e.price!=null?Math.round(e.price*100)+'¢':'—')+'</td>'
        +'<td class="pw-cn" style="font-weight:800">'+_pwUsd(e.usd)+'</td></tr>';
    }).join('');
    h+='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🆕 Neue große Einstiege — letzte 24h</span>'
      +'<span class="pw-sec-note">frisch aufgetauchte Whale-Positionen · 🔥 = bewiesen scharfe Wallet · Klick → Wallet/Markt</span></div>'
      +'<div class="pw-tw"><table class="pw-tbl"><thead><tr><th>vor</th><th>Sport</th><th>Markt</th><th>Wallet</th><th>Seite</th><th>Einstieg</th><th>Einsatz</th></tr></thead><tbody>'+body+'</tbody></table></div></section>';
  }
  if(flips.length){
    const body=flips.map(f=>'<tr><td class="pw-cn pw-mut">'+ago(f.ts)+'</td>'
      +'<td style="white-space:nowrap">'+_pwSportIcon(f.league)+' <span class="pw-mut" style="font-size:11px">'+_pwEsc((f.league||'').toUpperCase())+'</span></td>'
      +'<td><a href="https://polymarket.com/event/'+encodeURIComponent(f.key)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:inherit;text-decoration:none;border-bottom:1px dotted #6e7681">'+_pwEsc(f.match)+' <span style="color:#a78bfa">↗</span></a></td>'
      +'<td class="pw-cm"><span class="pw-mut">'+_pwEsc(f.from)+'</span> → <b style="color:#4cc2ff">'+_pwEsc(f.to)+'</b></td></tr>').join('');
    h+='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🔀 Favorit gekippt</span>'
      +'<span class="pw-sec-note">Märkte, in denen die führende Seite seit Beobachtungsbeginn gewechselt hat — oft ein starker Move</span></div>'
      +'<div class="pw-tw"><table class="pw-tbl"><thead><tr><th>vor</th><th>Sport</th><th>Markt</th><th>Favorit</th></tr></thead><tbody>'+body+'</tbody></table></div></section>';
  }
  return h;
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
      && (_pwRealHtk(m)==null || (_pwRealHtk(m)>=-3 && _pwRealHtk(m)<=PW_EDGE_HORIZON_H)))
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
      const _rh=_pwRealHtk(m); const htk=(_rh!=null)?(_rh<0?'live':_rh.toFixed(1)+'h'):'—';
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
  // 25.07.2026 (Lucas: „Kästen die nicht passen entfernen"): kein Leer-Kasten mehr — das Board
  // erscheint NUR, wenn es echte handelbare Fehlbepreisung gibt. Die globale Edge (a) deckt sonst ab.
  if(!shown.length) return '';
  let h='<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🎯 Wo Poly günstiger ist als die faire Quote</span>'
    +'<span class="pw-sec-note">Die pp-Zahl = wie viel Vorteil du hättest, wenn du diese Seite auf Poly nimmst statt zur fairen Pinnacle-Quote (Spread-Abzug '+PW_SPREAD_HAIRCUT+'pp schon drin). Nur Spiele der nächsten '+Math.round(PW_EDGE_HORIZON_H/24)+' Tage · Kurve = Pinnacle-Verlauf · Klick → Details</span></div><div class="pw-board">';
  shown.slice(0,40).forEach(e=>{h+=_pwEdgeRow(e,teams,wallets,hist);});
  return h+'</div></section>';
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
  const tr=(w&&w.bigTradesAll)||[]; if(!tr.length)return '';   // 13.08.2026: leer -> stumm; Sichtbarkeit via check_wallet_trades-Guard (Status-Panel)
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
  /* 🧭 Lern-Board (29.08.2026) — divergierender Balken je Signal-Mix. Marken bewusst duenn:
     10px Balken, 1px Mittellinie, gerundetes Datenende, eckig an der Linie. Die Daten sind das
     einzige, was laut sein darf. */
  #polyWalletsPanel .pw-cal-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:11px;margin:2px 0 16px}
  #polyWalletsPanel .pw-cal-kpi{background:linear-gradient(145deg,#13203a,#0d1524);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:12px 14px}
  #polyWalletsPanel .pw-cal-kpi-v{font-size:19px;font-weight:800;font-family:ui-monospace,monospace;line-height:1.15}
  #polyWalletsPanel .pw-cal-kpi-l{font-size:11px;color:#8a95ad;margin-top:4px;font-weight:600}
  #polyWalletsPanel .pw-cal-kpi-s{font-size:10px;color:#5b667e;margin-top:2px}
  #polyWalletsPanel .pw-cal-board{display:flex;flex-direction:column;gap:7px}
  #polyWalletsPanel .pw-cal-row{display:grid;grid-template-columns:minmax(160px,1.05fr) 390px 92px minmax(112px,.7fr) 134px;   /* letzte Spalte FEST: sonst sitzt die Skala-Zeile (leere Zelle) anders als die Datenzeilen und „Schnitt" steht neben statt ueber der Mittellinie */
    gap:16px;align-items:center;background:linear-gradient(180deg,#111a2b,#0e1524);
    border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:11px 16px}
  #polyWalletsPanel .pw-cal-row-thin{opacity:.6}
  #polyWalletsPanel .pw-cal-legend{background:none;border:0;padding:0 16px;margin-bottom:2px;align-items:end}
  #polyWalletsPanel .pw-cal-scale{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px;
    font-size:10px;color:#5b667e;text-transform:uppercase;letter-spacing:.6px}
  #polyWalletsPanel .pw-cal-scale span:first-child{text-align:right}
  #polyWalletsPanel .pw-cal-scale-mid{color:#8a95ad;font-weight:700}
  #polyWalletsPanel .pw-cal-mix{display:flex;flex-wrap:wrap;gap:5px}
  #polyWalletsPanel .pw-cal-chip{background:rgba(255,255,255,.05);color:#c9d2e3;font-size:11px;font-weight:600;
    padding:2px 8px;border-radius:6px;white-space:nowrap}
  #polyWalletsPanel .pw-cal-plot{min-width:0}
  #polyWalletsPanel .pw-cal-track{position:relative;height:10px}
  #polyWalletsPanel .pw-cal-mid{position:absolute;left:50%;top:-5px;bottom:-5px;width:1px;background:rgba(255,255,255,.18)}
  #polyWalletsPanel .pw-cal-bar{position:absolute;top:0;height:10px}
  #polyWalletsPanel .pw-cal-dist{margin-top:7px;text-align:center;font-size:11px;font-weight:700;
    font-variant-numeric:tabular-nums}
  #polyWalletsPanel .pw-cal-dist i{font-style:normal;font-weight:600;color:#5b667e;margin-left:5px}
  #polyWalletsPanel .pw-cal-val{text-align:right;white-space:nowrap}
  #polyWalletsPanel .pw-cal-val b{display:block;font-family:ui-monospace,monospace;font-size:15px;font-weight:800;
    color:#e6edf3;font-variant-numeric:tabular-nums}
  #polyWalletsPanel .pw-cal-val i{display:block;font-style:normal;font-size:9.5px;font-weight:600;color:#5b667e;
    letter-spacing:.4px;margin-top:2px}
  #polyWalletsPanel .pw-cal-n{font-size:11px;color:#76819c;line-height:1.45}
  #polyWalletsPanel .pw-cal-n i{display:block;font-style:normal;color:#5b667e}
  #polyWalletsPanel .pw-cal-out{text-align:right}
  #polyWalletsPanel .pw-cal-adj{display:inline-block;font-size:11px;font-weight:700;white-space:nowrap;
    padding:4px 10px;border-radius:7px;border:1px solid rgba(255,255,255,.12)}
  #polyWalletsPanel .pw-cal-adj-off{color:#5b667e}
  @media (max-width:980px){
    #polyWalletsPanel .pw-cal-kpis{grid-template-columns:1fr}
    #polyWalletsPanel .pw-cal-legend{display:none}
    #polyWalletsPanel .pw-cal-row{grid-template-columns:1fr auto;gap:10px}
    #polyWalletsPanel .pw-cal-plot{grid-column:1/-1;order:3}
    #polyWalletsPanel .pw-cal-val{text-align:left;order:2}
    #polyWalletsPanel .pw-cal-n{grid-column:1/-1;order:4}
    #polyWalletsPanel .pw-cal-out{grid-column:1/-1;order:5;text-align:left}
  }
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
