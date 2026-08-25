// tests/frontend/poly-heute-bet.test.mjs
// 21.08.2026 (Lucas): „Heute"-Bet direkt auslösen wo möglich. Kernrisiko = die Seite↔Pick-Markt-
// Zuordnung (_heuteSideMatches) — falsches Mapping = falsche Geld-Wette. Diese Tests pinnen sie fest.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const VERDICT = new URL('../../pick-verdict.js', import.meta.url);
const POLY    = new URL('../../polymarket-tab.js', import.meta.url);

function loadPoly() {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.localStorage.clear();
  window.eval(readFileSync(VERDICT, 'utf8'));
  window.eval(readFileSync(POLY, 'utf8'));
  return window;
}

test('_heuteSideMatches: Heimsieg <-> Heim-Team', () => {
  const w = loadPoly();
  const p = { market:'Heimsieg', home:'Real Betis', away:'Real Sociedad' };
  assert.equal(w._heuteSideMatches('real betis', p), true);
  assert.equal(w._heuteSideMatches('betis', p), true);
  assert.equal(w._heuteSideMatches('real sociedad', p), false);
});

test('_heuteSideMatches: Auswaertssieg / Unentschieden', () => {
  const w = loadPoly();
  const p = { market:'Auswärtssieg', home:'Arsenal', away:'Coventry City' };
  assert.equal(w._heuteSideMatches('coventry city', p), true);
  assert.equal(w._heuteSideMatches('coventry', p), true);
  const d = { market:'Unentschieden', home:'A', away:'B' };
  assert.equal(w._heuteSideMatches('draw', d), true);
  assert.equal(w._heuteSideMatches('the draw', d), true);
  assert.equal(w._heuteSideMatches('arsenal', d), false);
});

test('_heuteSideMatches: Over/Under/BTTS', () => {
  const w = loadPoly();
  assert.equal(w._heuteSideMatches('over 2.5', { market:'Over 2.5 Tore', home:'A', away:'B' }), true);
  assert.equal(w._heuteSideMatches('under 2.5', { market:'Over 2.5 Tore', home:'A', away:'B' }), false);
  assert.equal(w._heuteSideMatches('under 2.5', { market:'Under 2.5 Tore', home:'A', away:'B' }), true);
  assert.equal(w._heuteSideMatches('yes', { market:'Beide Teams treffen', home:'A', away:'B' }), true);
});

test('_polyHeuteBetOrder: ohne Preis-Cache faellt es auf die Token-Order zurueck', () => {
  // 24.08.2026: Frueher gab es hier null (= Link). Der Card-Pick-Weg braucht den Preis-Cache, der
  // Direktweg nicht — polyKey+side reichen, den Rest loest der Runner ueber den Slug auf.
  const w = loadPoly();
  const r = { key:'some-slug', side:'Real Betis', price:0.6, conv:8 };
  const o = w._polyHeuteBetOrder(r, [{ home:'Real Betis', away:'Real Sociedad', market:'Heimsieg', odds:2.0 }]);
  assert.ok(o && o.polyKey === 'some-slug' && o.side === 'Real Betis');
});

test('_polyHeuteBetOrder: null nur ohne Key/Seite — sonst immer eine Order', () => {
  const w = loadPoly();
  assert.ok(w._polyHeuteBetOrder({ key:'x', side:'y' }, []), 'Key+Seite reichen');
  assert.equal(w._polyHeuteBetOrder({ key:'x' }, []), null, 'ohne Seite keine Order');
  assert.equal(w._polyHeuteBetOrder({ side:'y' }, []), null, 'ohne Key keine Order');
  assert.equal(w._polyHeuteBetOrder(null, []), null);
});

// ── 24.08.2026 (Lucas: „kriegen wir hin, dass ich von dort gleich die Wette auslöse?") ──────────
// Der Card-Pick-Umweg deckte real ~7% der Plays ab. Jetzt trägt der Play die CLOB-Token-ID selbst,
// damit ist JEDE Sportart direkt setzbar — ausser den im Papier-Track negativen (US-Sport/Kampf).

function loadPolyWithSport(cat) {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.localStorage.clear();
  // poly-wallets.js wird hier nicht geladen -> Sport-Kategorie stubben (so wie sie real liefert).
  window._pwSportCategory = () => cat;
  window.eval(readFileSync(VERDICT, 'utf8'));
  window.eval(readFileSync(POLY, 'utf8'));
  return window;
}

const PLAY = {
  key: 'atp-alcaraz-sinner-2026-08-24', side: 'Carlos Alcaraz', price: 0.58, conv: 8,
  match: 'Carlos Alcaraz vs Jannik Sinner', league: 'TENNIS', sport: 'Tennis',
  token: '71321045679252212594626385532706912750332728571942532289631379312455583992563',
};

test('_polyHeuteTokenOrder: baut eine vollstaendige Direkt-Order aus dem Play', () => {
  const w = loadPolyWithSport('Tennis');
  const o = w._polyHeuteTokenOrder(PLAY);
  assert.ok(o, 'Order erwartet');
  assert.equal(o.tokenId, PLAY.token);
  assert.equal(o.polyKey, PLAY.key);
  assert.equal(o.side, 'Carlos Alcaraz');
  assert.equal(o.market, 'Carlos Alcaraz');       // der Ausgang IST der Markt
  assert.equal(o.home, 'Carlos Alcaraz');
  assert.equal(o.away, 'Jannik Sinner');
  assert.equal(o.polyPrice, 0.58);
  assert.equal(o.conviction, 8);
  assert.equal(o.edge, null);                     // kein Pinnacle-Anker -> kein erfundener Edge
});

test('_polyHeuteTokenOrder: ohne Token trotzdem eine Order (Placer löst über den Slug auf)', () => {
  // 24.08.2026 (Lucas: „haben nur einen Öffnen-Link"): der Button hing am Token, den poly_money_broad
  // erst ab dem ersten Scan mit dem neuen Code schreibt — dazwischen war JEDER Play tokenlos. Der
  // Token ist jetzt ein Beschleuniger: fehlt er, trägt die Order polyKey+side und der Runner löst auf.
  const w = loadPolyWithSport('Tennis');
  const { token, ...ohne } = PLAY;
  const o = w._polyHeuteTokenOrder(ohne);
  assert.ok(o, 'Order auch ohne Token');
  assert.equal(o.tokenId, null, 'tokenId explizit null, nicht erfunden');
  assert.equal(o.polyKey, PLAY.key);
  assert.equal(o.side, PLAY.side);
});

test('_polyHeuteTokenOrder: US-Sport und Kampfsport bleiben Link', () => {
  // Papier-Track ueber 500 Plays: MLB -28%, NFL -49%, UFC -31% ROI -> kein Direkt-Button.
  assert.equal(loadPolyWithSport('US-Sport')._polyHeuteTokenOrder(PLAY), null);
  assert.equal(loadPolyWithSport('Kampfsport')._polyHeuteTokenOrder(PLAY), null);
  assert.ok(loadPolyWithSport('E-Sport')._polyHeuteTokenOrder(PLAY), 'E-Sport ist bewusst erlaubt');
  assert.ok(loadPolyWithSport('Fußball')._polyHeuteTokenOrder(PLAY), 'Fussball erlaubt');
});

test('_polyHeuteBetOrder: faellt ohne Card-Pick auf die Token-Order zurueck', () => {
  const w = loadPolyWithSport('Tennis');
  const o = w._polyHeuteBetOrder(PLAY, []);       // keine Picks geladen
  assert.ok(o && o.tokenId === PLAY.token, 'Token-Order statt null');
});

test('_polyHeuteTokenOrder: Label ohne "vs" -> home traegt das Label, away leer', () => {
  const w = loadPolyWithSport('E-Sport');
  const o = w._polyHeuteTokenOrder({ ...PLAY, match: 'Winner of Group A' });
  assert.equal(o.home, 'Winner of Group A');
  assert.equal(o.away, '');
});


// ── Versand: was tatsaechlich bei GitHub landet (25.08.2026, Lucas' Heute-Test) ───────────────
// Lucas loeste einen Heute-Play aus, bekam „PAT pruefen" und nichts passierte. Der Token fehlte —
// aber selbst MIT Token waere nichts angekommen: `_wmBetDispatch` baute die Order aus einer festen
// Feldliste und liess polyKey/side/tokenId liegen, stempelte alles als WM2026 und baute eine
// fifa-world-cup-URL fuer einen LoL-Markt. Der Placer findet den Markt genau ueber diese Felder.

function bootDispatch(order, respond) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyModal"><div id="polyModalBody"></div></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const sent = [];
  w.fetch = (url, opt) => {
    if (String(url).includes('/dispatches')) {
      sent.push({ url: String(url), body: JSON.parse(opt.body), auth: opt.headers.Authorization });
      return Promise.resolve(respond || { ok: true, status: 204, json: () => Promise.resolve({}) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  };
  w.localStorage.clear();
  w.eval(readFileSync(VERDICT, 'utf8'));
  w.eval(readFileSync(POLY, 'utf8'));
  w.localStorage.setItem('betedge_github_pat', 'ghp_testtoken');
  w.document.getElementById('polyModal').dataset.pendingOrder = JSON.stringify(order);
  return { w, sent };
}

const HEUTE_ORDER = {
  home: 'GSMC', away: 'Spar', market: 'Under', polyPrice: 0.78,
  slug: 'lol-gsmc-spar-2026-08-25', tokenId: 'TOK-UNDER',
  polyKey: 'lol-gsmc-spar-2026-08-25', side: 'Under',
  league: 'ESPORTS', sport: 'E-Sport', edge: null, conviction: 8,
};

test('Versand: Poly-Play traegt polyKey, side und Token bis zu GitHub', async () => {
  const { w, sent } = bootDispatch(HEUTE_ORDER);
  await w._wmBetDispatch();
  assert.strictEqual(sent.length, 1, 'genau ein Dispatch');
  const o = sent[0].body.client_payload.orders[0];
  assert.strictEqual(o.polyKey, 'lol-gsmc-spar-2026-08-25');
  assert.strictEqual(o.side, 'Under');
  assert.strictEqual(o.tokenId, 'TOK-UNDER');
  assert.strictEqual(o.sport, 'E-Sport');
  assert.strictEqual(o.conviction, 8);
  assert.notStrictEqual(o.league, 'WM2026', 'kein WM-Stempel auf einem LoL-Markt');
  assert.match(o.eventUrl, /polymarket\.com\/event\/lol-gsmc-spar/, 'kein fifa-world-cup-Pfad');
  assert.strictEqual(sent[0].body.event_type, 'place-poly-bets');
});

test('Versand: ohne Token bleibt tokenId null — der Placer loest ueber den Slug auf', async () => {
  const { tokenId, ...ohne } = HEUTE_ORDER;
  const { w, sent } = bootDispatch(ohne);
  await w._wmBetDispatch();
  const o = sent[0].body.client_payload.orders[0];
  assert.strictEqual(o.tokenId, null, 'null, nicht erfunden');
  assert.strictEqual(o.polyKey, 'lol-gsmc-spar-2026-08-25', 'der Slug traegt den Fallback');
});

test('Versand: eine WM-Order bleibt unveraendert', async () => {
  const wm = { home: 'Deutschland', away: 'Brasilien', market: 'Heimsieg', polyPrice: 0.55,
               slug: 'wm-ger-bra', edge: 4.2, pinnFair: 0.52 };
  const { w, sent } = bootDispatch(wm);
  await w._wmBetDispatch();
  const o = sent[0].body.client_payload.orders[0];
  assert.strictEqual(o.league, 'WM2026');
  assert.match(o.eventUrl, /fifa-world-cup/);
  assert.strictEqual(o.polyKey, undefined, 'keine Poly-Felder auf einer WM-Order');
  assert.strictEqual(o.edgePP, 4.2);
});

test('Fehlschlag: Status und GitHub-Meldung stehen im Dialog, nicht nur „PAT pruefen"', async () => {
  const { w } = bootDispatch(HEUTE_ORDER,
    { ok: false, status: 404, json: () => Promise.resolve({ message: 'Not Found' }) });
  await w._wmBetDispatch();
  const html = w.document.getElementById('polyModalBody').innerHTML;
  assert.match(html, /HTTP 404/);
  assert.match(html, /Not Found/);
  assert.match(html, /repo/, 'nennt den fehlenden Scope als wahrscheinlichste Ursache');
  assert.match(html, /Token ändern/, 'Weg zur Korrektur steht daneben');
});

test('Fehlschlag 401: anderer Hinweis als bei 404', async () => {
  const { w } = bootDispatch(HEUTE_ORDER,
    { ok: false, status: 401, json: () => Promise.resolve({ message: 'Bad credentials' }) });
  await w._wmBetDispatch();
  const html = w.document.getElementById('polyModalBody').innerHTML;
  assert.match(html, /HTTP 401/);
  assert.match(html, /abgelaufen/);
  assert.doesNotMatch(html, /Scope/, '401 ist kein Scope-Problem');
});

test('Netzfehler meldet UNKLAR statt falschem Erfolg', async () => {
  // Vorher stand hier `ok = true` („koennte trotzdem gelaufen sein"). Bei echtem Geld fuehrt ein
  // falsches ✅ dazu, dass man ein zweites Mal setzt — der teuerste denkbare Anzeigefehler.
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyModal"><div id="polyModalBody"></div></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url) => String(url).includes('/dispatches')
    ? Promise.reject(new Error('network down'))
    : Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  w.localStorage.clear();
  w.eval(readFileSync(VERDICT, 'utf8'));
  w.eval(readFileSync(POLY, 'utf8'));
  w.localStorage.setItem('betedge_github_pat', 'ghp_testtoken');
  w.document.getElementById('polyModal').dataset.pendingOrder = JSON.stringify(HEUTE_ORDER);
  await w._wmBetDispatch();
  const html = w.document.getElementById('polyModalBody').innerHTML;
  assert.match(html, /Unklar/);
  assert.match(html, /Place Polymarket Bets/, 'sagt WO man nachsieht');
  assert.doesNotMatch(html, /Action ausgelöst/, 'kein falsches Erfolgs-Signal');
});


// ── Token-Setup: die Schleife (25.08.2026, Lucas) ────────────────────────────────────────────
// „Ruft immer die Maske auf, ich speichere, nichts passiert, Fenster kommt wieder."
// Zwei Ursachen: Speichern war eine Sackgasse (Fenster zu, schwebende Order vergessen), und der
// Erfolg wurde gemeldet, ohne zurueckzulesen — blockt der Browser localStorage, log die Oberflaeche.

function bootPat({ storageBroken = false } = {}) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyModal"><div id="polyModalBody"></div></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const sent = [];
  w.fetch = (url, opt) => {
    if (String(url).includes('/dispatches')) { sent.push(JSON.parse(opt.body)); return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) }); }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  };
  w.localStorage.clear();
  if (storageBroken) {
    Object.defineProperty(w, 'localStorage', {
      configurable: true,
      get() { return { getItem: () => null, setItem() { throw new Error('blocked'); }, removeItem() {}, clear() {} }; },
    });
  }
  w.eval(readFileSync(VERDICT, 'utf8'));
  w.eval(readFileSync(POLY, 'utf8'));
  return { w, sent };
}

test('Kein Token: Einstellungen oeffnen, aber KEINE Fehlerbox', async () => {
  // Ein fehlender Token ist kein fehlgeschlagener Dispatch — die rote Box waere hier irrefuehrend.
  const { w, sent } = bootPat();
  w.document.getElementById('polyModal').dataset.pendingOrder = JSON.stringify(HEUTE_ORDER);
  await w._wmBetDispatch();
  assert.strictEqual(sent.length, 0, 'ohne Token wird nichts verschickt');
  const html = w.document.getElementById('polyModalBody').innerHTML;
  assert.match(html, /Personal Access Token/, 'die Maske steht da');
  assert.doesNotMatch(html, /Dispatch fehlgeschlagen/);
});

test('Nach dem Speichern geht es zur Bestaetigung zurueck — nicht ins Leere', async () => {
  const { w } = bootPat();
  const modal = w.document.getElementById('polyModal');
  modal.dataset.pendingOrder = JSON.stringify(HEUTE_ORDER);
  await w._wmBetDispatch();                       // oeffnet die Maske
  w.document.getElementById('polyPatInput').value = 'ghp_abc123';
  w.polySavePAT();
  await new Promise(r => setTimeout(r, 20));   // Speichern prueft den Token erst gegen GitHub
  const html = w.document.getElementById('polyModalBody').innerHTML;
  assert.match(html, /Poly-Play bestätigen/, 'die Bestaetigung ist zurueck');
  assert.match(html, /Bet via GitHub auslösen/, 'ein Klick fehlt noch — bewusst kein Auto-Versand');
  assert.notStrictEqual(modal.style.display, 'none', 'Fenster bleibt offen');
});

test('Danach loest derselbe Play wirklich aus', async () => {
  const { w, sent } = bootPat();
  w.document.getElementById('polyModal').dataset.pendingOrder = JSON.stringify(HEUTE_ORDER);
  await w._wmBetDispatch();
  w.document.getElementById('polyPatInput').value = 'ghp_abc123';
  w.polySavePAT();
  await w._wmBetDispatch();
  assert.strictEqual(sent.length, 1);
  assert.strictEqual(sent[0].client_payload.orders[0].polyKey, HEUTE_ORDER.polyKey);
});

test('Blockierter Browser-Speicher meldet den Fehler, statt Erfolg zu behaupten', async () => {
  const { w } = bootPat({ storageBroken: true });
  w.polyOpenSettings();
  assert.match(w.document.getElementById('polyModalBody').innerHTML, /Browser-Speicher blockiert/,
    'der Zustand steht schon beim Oeffnen da');
  w.document.getElementById('polyPatInput').value = 'ghp_abc123';
  w.polySavePAT();
  const html = w.document.getElementById('polyModalBody').innerHTML;
  assert.match(html, /Dein Browser speichert nichts/);
  assert.doesNotMatch(html, /Poly-Play bestätigen/, 'kein Weiterlaufen auf einer Luege');
});


// ── „Platziert" muss wahr sein (25.08.2026, Lucas) ───────────────────────────────────────────
// „Die Wetten werden als platziert angezeigt — aber sie sind nicht platziert." Der Code stempelte
// die Karte VOR dem Versand („Save bets to localStorage BEFORE dispatch") und glich nie ab. Eine
// Position, die es nicht gibt, ist der teuerste Anzeigefehler, den dieses Projekt haben kann.

function bootBets({ dispatchOk = true, throwOnDispatch = false } = {}) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyModal"><div id="polyModalBody"></div></div><div id="polyPickGrid"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url) => {
    if (String(url).includes('/dispatches')) {
      if (throwOnDispatch) return Promise.reject(new Error('offline'));
      return Promise.resolve(dispatchOk ? { ok: true, status: 204, json: () => Promise.resolve({}) }
                                        : { ok: false, status: 404, json: () => Promise.resolve({ message: 'Not Found' }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  };
  w.localStorage.clear();
  w.eval(readFileSync(VERDICT, 'utf8'));
  w.eval(readFileSync(POLY, 'utf8'));
  w.localStorage.setItem('betedge_github_pat', 'ghp_x');
  const pick = { id: 'p1', home: 'GSMC', away: 'Spar', market: 'Under', league: 'ESPORTS', date: '25.08.2026' };
  w._polyOrdersObj = [{ home: 'GSMC', away: 'Spar', market: 'Under', league: 'ESPORTS' }];
  w._polyOrdersSel = [pick];
  w._polyState = { prices: { p1: { found: true, price: 0.78 } }, dateStr: '25.08.2026', selected: new Set() };
  return { w, bets: () => JSON.parse(w.localStorage.getItem('betedge_poly_bets') || '[]') };
}

test('Nach dem Versand steht ANGEFRAGT, nicht platziert', async () => {
  const { w, bets } = bootBets({ dispatchOk: true });
  await w.polyDispatch();
  const b = bets();
  assert.strictEqual(b.length, 1);
  assert.strictEqual(b[0].state, 'dispatched', 'bestaetigt wird erst, was der Runner zurueckmeldet');
});

test('Fehlgeschlagener Versand nimmt den Eintrag zurueck', async () => {
  const { w, bets } = bootBets({ dispatchOk: false });
  await w.polyDispatch();
  assert.deepStrictEqual([...bets()], [], 'keine Karteileiche, die „Platziert" behauptet');
  assert.ok(!w._polyPlacedThisSession || !w._polyPlacedThisSession.p1, 'auch nicht im Sitzungsspeicher');
});

test('Netzfehler heisst UNKLAR — der Eintrag bleibt, aber markiert', async () => {
  const { w, bets } = bootBets({ throwOnDispatch: true });
  await w.polyDispatch();
  const b = bets();
  assert.strictEqual(b.length, 1, 'nicht zuruecknehmen — es koennte gelaufen sein');
  assert.strictEqual(b[0].state, 'unknown');
});

test('Badge auf der Karte folgt dem echten Zustand', () => {
  const { w } = bootBets();
  const pick = { id: 'p1', home: 'GSMC', away: 'Spar', market: 'Under', league: 'ESPORTS',
                 leagueName: 'LoL', leagueFlag: '🎮', date: '25.08.2026' };
  const setzen = (state) => w.localStorage.setItem('betedge_poly_bets',
    JSON.stringify([{ id: 'p1', home: 'GSMC', away: 'Spar', market: 'Under', state, result: null, polyPrice: 0.78 }]));

  setzen('confirmed');  assert.match(w._renderPickCard(pick), /🟣 Platziert/);
  setzen('dispatched'); assert.match(w._renderPickCard(pick), /⏳ Angefragt/);
  setzen('unknown');    assert.match(w._renderPickCard(pick), /⚠️ Unklar/);
  setzen('failed');     assert.match(w._renderPickCard(pick), /Nicht gesetzt/);

  // Alt-Eintrag ohne `state` (genau die, die Lucas jetzt faelschlich als platziert sieht):
  w.localStorage.setItem('betedge_poly_bets',
    JSON.stringify([{ id: 'p1', home: 'GSMC', away: 'Spar', market: 'Under', result: null, polyPrice: 0.78 }]));
  const html = w._renderPickCard(pick);
  assert.match(html, /⏳ Angefragt/, 'ohne Nachweis gilt NICHT als platziert');
  assert.doesNotMatch(html, /🟣 Platziert/);
});

test('Sammel-Versand zeigt den HTTP-Grund, nicht nur einen Toast', async () => {
  // 25.08.2026: Im Sammel-Weg stand nur „Versand fehlgeschlagen" plus ein Kommentar im Code, die
  // Details stuenden im Dialog — sie standen dort nie. Lucas hatte keinen Anhaltspunkt.
  const { w } = bootBets({ dispatchOk: false });
  await w.polyDispatch();
  const html = w.document.getElementById('polyModalBody').innerHTML;
  assert.match(html, /HTTP 404/);
  assert.match(html, /repo/, 'nennt den fehlenden Scope');
  assert.match(html, /Nichts gesetzt/, 'sagt, dass keine Wette steht');
  assert.strictEqual(w._polyDispatchError.status, 404, 'auch in der Konsole abfragbar');
});


// ── Token wird beim Speichern geprueft (25.08.2026, Lucas' HTTP 401) ─────────────────────────
// Der Token war ungueltig — auffallen tat das aber erst beim Klick, der echtes Geld setzt.
// Eine LESENDE Probe (GET /repos/{repo}) beantwortet Gueltigkeit und Sichtbarkeit ohne
// Nebenwirkung, und zwar im Setup, wo ein Fehlschlag nichts kostet.

function bootPatCheck(repoResp) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyModal"><div id="polyModalBody"></div></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const calls = [];
  w.fetch = (url, opt) => {
    calls.push({ url: String(url), method: (opt && opt.method) || 'GET' });
    if (String(url).includes('/repos/')) return Promise.resolve(repoResp);
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  };
  w.localStorage.clear();
  w.eval(readFileSync(VERDICT, 'utf8'));
  w.eval(readFileSync(POLY, 'utf8'));
  return { w, calls };
}
const OK200   = { ok: true,  status: 200, json: () => Promise.resolve({ full_name: 'blummabet/Betting-Dashboard' }) };
const BAD401  = { ok: false, status: 401, json: () => Promise.resolve({ message: 'Bad credentials' }) };
const NOTF404 = { ok: false, status: 404, json: () => Promise.resolve({ message: 'Not Found' }) };

test('Token-Probe ist LESEND — kein Dispatch, keine Wette', async () => {
  const { w, calls } = bootPatCheck(OK200);
  const res = await w.polyCheckPAT('ghp_gut');
  assert.strictEqual(res.ok, true);
  assert.ok(calls.every(c => c.method === 'GET'), 'nur GET');
  assert.ok(!calls.some(c => c.url.includes('/dispatches')), 'niemals ein Dispatch beim Pruefen');
});

test('401 wird als kaputter Token benannt, 404 als fehlender Scope', async () => {
  const a = await bootPatCheck(BAD401).w.polyCheckPAT('ghp_alt');
  assert.strictEqual(a.ok, false);
  assert.match(a.text, /abgelaufen|unvollständig|widerrufen/);
  const b = await bootPatCheck(NOTF404).w.polyCheckPAT('ghp_eng');
  assert.match(b.text, /Scope `repo`/);
});

test('Speichern zeigt das Ergebnis und laesst einen kaputten Token nicht durchgehen', async () => {
  const { w } = bootPatCheck(BAD401);
  w.polyOpenSettings();
  w.document.getElementById('polyPatInput').value = 'ghp_kaputt';
  w.polySavePAT();
  await new Promise(r => setTimeout(r, 20));
  const html = w.document.getElementById('polyModalBody').innerHTML;
  assert.match(html, /Token abgelehnt/);
  assert.match(html, /HTTP 401/);
  assert.doesNotMatch(html, /Poly-Play bestätigen/, 'es geht NICHT zur Wette weiter');
});

test('Gueltiger Token fuehrt zur Bestaetigung zurueck', async () => {
  const { w } = bootPatCheck(OK200);
  w.document.getElementById('polyModal').dataset.pendingOrder = JSON.stringify(HEUTE_ORDER);
  w.polyOpenSettings();
  w.document.getElementById('polyPatInput').value = 'ghp_gut';
  w.polySavePAT();
  await new Promise(r => setTimeout(r, 20));
  assert.match(w.document.getElementById('polyModalBody').innerHTML, /Poly-Play bestätigen/);
});


// ── Aufraeumen der Fehlversuche (25.08.2026, Lucas) ──────────────────────────────────────────
// „Die Bets von vorhin, die nicht geklappt haben — koennen die wieder geloest werden?" Ja, aber
// konservativ: bestaetigte Wetten und alles mit Ergebnis bleiben unangetastet.

test('Aufraeumen entfernt nur Unbestaetigtes', () => {
  const { w } = bootBets();
  w.localStorage.setItem('betedge_poly_bets', JSON.stringify([
    { id: 'a', home: 'A', away: 'B', market: 'X', state: 'dispatched', result: null },
    { id: 'b', home: 'C', away: 'D', market: 'X', state: 'confirmed',  result: null },
    { id: 'c', home: 'E', away: 'F', market: 'X', result: null },                 // Altbestand ohne state
    { id: 'd', home: 'G', away: 'H', market: 'X', state: 'unknown',    result: null },
    { id: 'e', home: 'I', away: 'J', market: 'X', state: 'dispatched', result: 'won' },  // hat Ergebnis
  ]));
  const n = w.polyCleanupUnconfirmed();
  assert.strictEqual(n, 3, 'dispatched + ohne-state + unknown');
  const rest = JSON.parse(w.localStorage.getItem('betedge_poly_bets')).map(b => b.id).sort();
  assert.deepStrictEqual(rest, ['b', 'e'], 'bestaetigt und abgerechnet bleiben');
});

test('Aufraeumen ohne Altlast sagt das und aendert nichts', () => {
  const { w } = bootBets();
  w.localStorage.setItem('betedge_poly_bets', JSON.stringify([
    { id: 'b', home: 'C', away: 'D', market: 'X', state: 'confirmed', result: null },
  ]));
  assert.strictEqual(w.polyCleanupUnconfirmed(), 0);
  assert.strictEqual(JSON.parse(w.localStorage.getItem('betedge_poly_bets')).length, 1);
});


// ── „Meine ausgelösten Wetten" (25.08.2026, Lucas dreimal: „wo seh ich die?") ────────────────
// Antwort war: nirgends. Die bestehende Liste liest *_results.json, und dort kommen manuell
// ausgeloeste Wetten nie an — kein Aufloeser liest `polyBets`. Diese Flaeche liest den lokalen
// Bestand, den _syncBetsFromHistory aus picks_history.json fuellt.

test('Wett-Liste zeigt jede ausgeloeste Wette mit ihrem Zustand', () => {
  const { w } = bootBets();
  w.localStorage.setItem('betedge_poly_bets', JSON.stringify([
    { id: '1', home: 'Real Madrid', away: 'Real Sociedad', market: 'Over 2.5 Tore',
      stake: 5, polyPrice: 0.665, placed: '2026-08-25T13:49:17Z', state: 'confirmed', result: null },
    { id: '2', home: 'Henrique Rocha', away: 'Michael Mmoh', market: 'Henrique Rocha',
      stake: 5, polyPrice: 0.575, placed: '2026-08-25T13:49:53Z', state: 'dispatched', result: null },
  ]));
  const html = w._polyMyBetsHtml();
  assert.match(html, /Real Madrid/);
  assert.match(html, /Henrique Rocha/);
  assert.match(html, /🟣 Platziert/);
  assert.match(html, /⏳ Angefragt/);
  assert.match(html, /67¢/, 'Preis und Quote stehen dran');
  assert.match(html, /· 2</, 'Anzahl im Kopf');
});

test('Wett-Liste sortiert die neueste nach oben', () => {
  const { w } = bootBets();
  w.localStorage.setItem('betedge_poly_bets', JSON.stringify([
    { id: 'alt', home: 'Alt', away: 'X', market: 'M', placed: '2026-05-01T10:00:00Z', state: 'confirmed' },
    { id: 'neu', home: 'Neu', away: 'Y', market: 'M', placed: '2026-08-25T13:49:00Z', state: 'confirmed' },
  ]));
  const html = w._polyMyBetsHtml();
  assert.ok(html.indexOf('Neu') < html.indexOf('Alt'), 'neueste zuerst');
});

test('Leere Liste erklaert, was passieren muss', () => {
  const { w } = bootBets();
  w.localStorage.setItem('betedge_poly_bets', '[]');
  const html = w._polyMyBetsHtml();
  assert.match(html, /Noch keine/);
  assert.match(html, /picks_history\.json/, 'sagt, woher die Bestaetigung kommt');
});

test('Liste erscheint auch, solange die Server-Daten noch laden', () => {
  const { w } = bootBets();
  w.localStorage.setItem('betedge_poly_bets', JSON.stringify([
    { id: '1', home: 'Real Madrid', away: 'Real Sociedad', market: 'Over 2.5 Tore', placed: '2026-08-25T13:49:17Z', state: 'confirmed' },
  ]));
  const html = w.renderPolyStats();
  assert.match(html, /Real Madrid/, 'haengt nicht an *_results.json');
  assert.match(html, /Performance lädt/);
});

