// tests/frontend/poly-terminal-betfair-cross.test.mjs
// 21.08.2026 (Lucas: „checken wir ob auf betfair kohle liegt?"): Betfair-Geld-Gegencheck im
// Kanten/Heute-Scorer (_pwShortlistScore) aus money_map.json — symmetrisch zum Betfair-Terminal.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

function load() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url:'https://x.com/', runScripts:'outside-only' });
  const { window } = dom;
  window.eval(readFileSync(new URL('../../poly-wallets.js', import.meta.url), 'utf8'));
  return window;
}
const market = () => ({
  league:'UEFA Europa League Qualifiers', sport:'soccer',
  shares:{ 'FC Twente':54000, 'Qarabag FK':6000 },
  prices:{ 'FC Twente':0.68, 'Qarabag FK':0.32 },
  totalUsd:60000,
  kickoff:new Date(Date.now()+6*3600e3).toISOString(),
  capturedAt:new Date().toISOString(),
});

test('_pwBfFav matcht das Spiel und liefert den Betfair-Favoriten', () => {
  const w = load();
  w._pwCache = { moneyMap:{ rows:[
    { home:'FC Twente', away:'Qarabag FK', betfair:{ side:'home', name:'FC Twente', sharePct:90, eur:514416 }, pinn:null },
  ]}};
  const oc = Object.entries(market().shares).map(([s,u])=>({s,u}));
  const bf = w._pwBfFav(oc);
  assert.ok(bf, 'kein Betfair-Match');
  assert.equal(bf.polySide, 'FC Twente');
  assert.equal(bf.pct, 90);
});

test('Kanten-Scorer haengt Betfair-Bestaetigung an (bf.agree) + 💷-Reason', () => {
  const w = load();
  w._pwCache = { moneyMap:{ rows:[
    { home:'FC Twente', away:'Qarabag FK', betfair:{ side:'home', name:'FC Twente', sharePct:90, eur:514416 }, pinn:null },
  ]}};
  const r = w._pwShortlistScore('twente-qarabag', market());
  assert.notEqual(r.verdict, 'SKIP', 'Play sollte durchkommen');
  assert.equal(r.side, 'FC Twente');
  assert.ok(r.bf, 'bf-Info fehlt am Return');
  assert.equal(r.bf.agree, true);
  assert.equal(r.bf.pct, 90);
  assert.ok((r.reasons||[]).some(x=>/Betfair-Geld bestätigt/.test(x)), '💷-Reason fehlt');
});

test('_pwBfFav: kein Row-Match → null', () => {
  const w = load();
  w._pwCache = { moneyMap:{ rows:[
    { home:'Some Team', away:'Other Team', betfair:{ side:'home', name:'Some Team', sharePct:80, eur:100000 } },
  ]}};
  const oc = Object.entries(market().shares).map(([s,u])=>({s,u}));
  assert.equal(w._pwBfFav(oc), null, 'ohne Team-Match darf kein Betfair-Favorit kommen');
});

test('_pwBfFav: Betfair auf Away → polySide = Auswaerts-Team', () => {
  const w = load();
  w._pwCache = { moneyMap:{ rows:[
    { home:'FC Twente', away:'Qarabag FK', betfair:{ side:'away', name:'Qarabag FK', sharePct:75, eur:300000 } },
  ]}};
  const oc = Object.entries(market().shares).map(([s,u])=>({s,u}));
  const bf = w._pwBfFav(oc);
  assert.ok(bf, 'kein Match');
  assert.equal(bf.polySide, 'Qarabag FK');
  assert.equal(bf.pct, 75);
});

test('Betfair-Bestaetigung hebt einen sonst duennen Play ueber die Schwelle', () => {
  const w = load();
  // Ohne Betfair: nur Geld-Signal (1.5) < 3 → SKIP. Mit Betfair-Bestaetigung (+1.5) → 3.0 → Play.
  const noBf = load();
  noBf._pwCache = { moneyMap:{ rows:[] } };
  assert.equal(noBf._pwShortlistScore('t', market()).verdict, 'SKIP', 'duenner Play ohne Betfair sollte SKIP sein');
  w._pwCache = { moneyMap:{ rows:[
    { home:'FC Twente', away:'Qarabag FK', betfair:{ side:'home', name:'FC Twente', sharePct:90, eur:514416 } },
  ]}};
  const r = w._pwShortlistScore('t', market());
  assert.notEqual(r.verdict, 'SKIP', 'mit Betfair-Bestaetigung sollte es ein Play sein');
  assert.equal(r.bf.agree, true);
});
