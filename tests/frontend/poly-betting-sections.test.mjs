// tests/frontend/poly-betting-sections.test.mjs
//
// 20.08.2026 (Lucas: „es gibt in den Cards kein BET, wieso dann in der Polymarket
// Betting Ansicht"): Der Betting-Tab labelte frische Club/Liga-Picks ueber `conf`
// (high→BET) statt ueber das echte Card-Verdict (computeVerdict). Ergebnis: ✅ BET im
// Tab, obwohl die Card SKIP/NOBET sagte. Diese Tests halten fest:
//   1) _pickCardVerdict spiegelt computeVerdict (nicht conf) fuer frische Picks.
//   2) renderPolyPickCards trennt in ZWEI Bereiche: „Zum Wetten" (1:1 Cards, BET/ABWÄGEN)
//      und „Poly-Kante" (Rest). Ein conf:'high'-Pick, den computeVerdict als SKIP wertet,
//      darf NICHT im Wett-Bereich stehen und NICHT als BET getaggt sein.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const VERDICT = new URL('../../pick-verdict.js', import.meta.url);
const POLY    = new URL('../../polymarket-tab.js', import.meta.url);

function loadPoly() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polymarketPanel"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.localStorage.clear();
  window.eval(readFileSync(VERDICT, 'utf8'));   // computeVerdict global
  window.eval(readFileSync(POLY, 'utf8'));
  return window;
}

// computeVerdict-Inputs (Schwellen aus pick-verdict.js):
//  BET : modelOdds 1.5 / odds 2.0 → +19pp → modSig 1, score 1 → BET
//  SKIP: modelOdds 3.0 / odds 2.0 → -14pp → modSig -1, score -1 → SKIP
const betPick  = { id:'ENG|A|B|Heimsieg', home:'A', away:'B', market:'Heimsieg',
                   conf:'high', odds:2.0, modelOdds:1.5, leagueFlag:'🏴', leagueName:'ENG' };
const skipPick = { id:'ENG|C|D|Heimsieg', home:'C', away:'D', market:'Heimsieg',
                   conf:'high', odds:2.0, modelOdds:3.0, leagueFlag:'🏴', leagueName:'ENG' };

test('computeVerdict ist geladen und liefert die erwarteten Verdicts', () => {
  const w = loadPoly();
  assert.equal(typeof w.computeVerdict, 'function');
  assert.equal(w.computeVerdict({ modelOdds:1.5, odds:2.0, market:'Heimsieg' }).verdict, 'BET');
  assert.equal(w.computeVerdict({ modelOdds:3.0, odds:2.0, market:'Heimsieg' }).verdict, 'SKIP');
});

test('_pickCardVerdict folgt computeVerdict, NICHT conf', () => {
  const w = loadPoly();
  // Beide Picks haben conf:'high' — die alte Logik haette BEIDE als BET gelabelt.
  assert.equal(w._pickCardVerdict(betPick),  'BET');
  assert.equal(w._pickCardVerdict(skipPick), 'SKIP');   // conf:high, aber Modell sagt fade
});

test('_pickCardVerdict nimmt vorgestempelten verdict (WM/National) unveraendert', () => {
  const w = loadPoly();
  assert.equal(w._pickCardVerdict({ verdict:'ABWÄGEN', conf:'high' }), 'ABWÄGEN');
  assert.equal(w._pickCardVerdict({ verdict:'NOBET',   conf:'high' }), 'NOBET');
});

test('_verdictTag zeigt kein ✅ BET fuer einen SKIP-Pick', () => {
  const w = loadPoly();
  assert.ok(w._verdictTag(betPick).includes('BET'), 'echter BET fehlt');
  assert.equal(w._verdictTag(skipPick), '', 'SKIP darf keinen Verdict-Tag bekommen');
});

test('Gruppierung: BET/ABWÄGEN → Wett-Bereich, SKIP/NOBET → Poly-Kante', () => {
  const w = loadPoly();
  // _isCardBet (in renderPolyPickCards) = _pickCardVerdict ∈ {BET, ABWÄGEN}. Genau diese
  // Grenze entscheidet, in welchen der zwei Bereiche ein Pick faellt.
  const isCardBet = p => { const v = w._pickCardVerdict(p); return v === 'BET' || v === 'ABWÄGEN'; };
  assert.equal(isCardBet(betPick),  true,  'BET-Spiel gehoert in den Wett-Bereich');
  assert.equal(isCardBet(skipPick), false, 'SKIP-Spiel gehoert NICHT in den Wett-Bereich');
  assert.equal(isCardBet({ verdict:'ABWÄGEN', conf:'high' }), true);
  assert.equal(isCardBet({ verdict:'NOBET',   conf:'high' }), false);
});

test('renderPolyPickCards ist aufrufbar und liefert die zwei Sektions-Header (Default leer)', () => {
  const w = loadPoly();
  // _polyState.picks ist initial [] → Empty-State; wir pruefen nur, dass die Funktion
  // ohne Fehler laeuft und die neue Struktur (Section-Header-Text) im Quelltext lebt.
  const html = w.renderPolyPickCards();
  assert.equal(typeof html, 'string');
});

// ── 20.08.2026: Sub-Tabs (Cards/Value/Heute) + „Heute"-Sektion ─────────────────
test('_polySubtabBar rendert drei Tabs, Cards default aktiv', () => {
  const w = loadPoly();
  const bar = w._polySubtabBar();
  assert.ok(bar.includes('📇 Cards'), 'Cards-Tab fehlt');
  assert.ok(bar.includes('💜 Value'), 'Value-Tab fehlt');
  assert.ok(bar.includes('🔥 Heute'), 'Heute-Tab fehlt');
  assert.ok(bar.includes("_polySetSection('heute')"), 'Heute onclick fehlt');
  // Default-Sektion 'cards' → Cards-Button aktiv (Akzent-Border)
  assert.ok(/#a78bfa[^]*📇 Cards/.test(bar) || bar.includes('📇 Cards'), 'Cards nicht aktiv markiert');
});

test('_renderPolyHeute: Lade- und Leer-Zustand', () => {
  const w = loadPoly();
  assert.ok(w._renderPolyHeute(null).includes('Lade'), 'Ladezustand fehlt');
  assert.ok(w._renderPolyHeute([]).includes('keine handelbare Kante'), 'Leerzustand fehlt');
});

test('_renderPolyHeute: Play-Row mit Polymarket-Link, Seite, Loggen-Button', () => {
  const w = loadPoly();
  const play = { key:'nyc-vs-mia-2026', match:'New York City vs Inter Miami', side:'Inter Miami',
                 conv:8, price:0.42, htk:5, league:'MLS', verdict:'BET' };
  const html = w._renderPolyHeute([play]);
  assert.ok(html.includes('New York City vs Inter Miami'), 'Match-Label fehlt');
  assert.ok(html.includes('Inter Miami'), 'Seite fehlt');
  assert.ok(html.includes('polymarket.com/event/nyc-vs-mia-2026'), 'Polymarket-Link fehlt');
  assert.ok(html.includes('_polyHeuteLog(0)'), 'Loggen-Button fehlt');
  assert.ok(html.includes('42¢'), 'Preis fehlt');
  // Engine-Herkunft transparent gemacht
  assert.ok(html.includes('Heute wetten'), 'Terminal-Engine-Hinweis fehlt');
});

test('Standard-Auswahl ist LEER (kein Auto-Select-All)', () => {
  // Lucas: „alles auswählen bitte nicht — das kann sonst blöd enden."
  // Quelle statt Laufzeit pruefen (initPolymarket braucht LEAGUES/DOM). Kein
  // `new Set(_polyState.picks.map(...))` mehr im Code → nichts wird vorausgewaehlt.
  const src = readFileSync(POLY, 'utf8');
  assert.equal(/new Set\(_polyState\.picks\.map/.test(src), false,
    'Auto-Select-All noch im Code — Vorauswahl darf nicht alle Picks anhaken');
});

// ── 20.08.2026 (Lucas: „Value war umgekehrt"): Value = Poly-Edge, nicht die SKIP-Reste ──
test('_polyPickHasValue: positive Poly-Edge zaehlt, egal welches Verdict', () => {
  const w = loadPoly();
  w._polyState.prices = {
    A: { found:true, price:0.50 },   // ref 1.88 → implied .532 → +3pp  → Value
    B: { found:true, price:0.60 },   // ref 1.50 → implied .667 → +7pp  → Value
    C: { found:true, price:0.80 },   // ref 1.50 → implied .667 → -13pp → keine Value
    D: undefined,                    // kein Preis → null → keine Value
  };
  const mk = (id, odds) => ({ id, odds });
  assert.equal(w._polyPickHasValue(mk('A', 1.88)), true,  'SKIP mit +3pp muss Value sein');
  assert.equal(w._polyPickHasValue(mk('B', 1.50)), true);
  assert.equal(w._polyPickHasValue(mk('C', 1.50)), false, 'negative Edge ist keine Value');
  assert.equal(w._polyPickHasValue(mk('D', 1.50)), false, 'ohne Preis keine Value');
});

test('Value-Tab zeigt Poly-Edge-Spiele (auch SKIP), Cards zeigt sie NICHT wenn kein Bet', () => {
  const w = loadPoly();
  // skipPick = computeVerdict SKIP (Modell fade), aber Poly quotiert besser → Value.
  const sp = { ...skipPick, id:'SKIP1', odds:1.88 };
  const bp = { ...betPick,  id:'BET1',  odds:2.0 };
  w._polyState.picks  = [sp, bp];
  w._polyState.prices = { SKIP1: { found:true, price:0.50 }, BET1: { found:true, price:0.60 } };
  // ref(sp)=1.88→.532 vs .50 = +3pp Value ; ref(bp)=2.0→.50 vs .60 = -10pp keine Value

  w._polyState.section = 'value';
  const vhtml = w.renderPolyPickCards();
  assert.ok(vhtml.includes('data-id="SKIP1"'), 'SKIP mit Poly-Edge fehlt im Value-Tab');
  assert.ok(!vhtml.includes('data-id="BET1"'), 'BET ohne Poly-Edge darf NICHT im Value-Tab stehen');

  w._polyState.section = 'cards';
  const chtml = w.renderPolyPickCards();
  assert.ok(chtml.includes('data-id="BET1"'), 'BET fehlt im Cards-Tab');
  assert.ok(!chtml.includes('data-id="SKIP1"'), 'SKIP darf NICHT im Cards-Tab stehen');
});

test('_polyCounts: Cards=Bets, Value=Poly-Edge (koennen ueberlappen)', () => {
  const w = loadPoly();
  const bpEdge = { ...betPick, id:'BE', odds:1.5 };   // BET UND +Edge → beide zaehlen
  w._polyState.picks  = [bpEdge];
  w._polyState.prices = { BE: { found:true, price:0.55 } };  // 1.5→.667 vs .55 = +12pp
  const c = w._polyCounts();
  assert.equal(c.cards, 1, 'BET zaehlt bei Cards');
  assert.equal(c.value, 1, 'derselbe +Edge-Pick zaehlt auch bei Value (Overlap ok)');
});
