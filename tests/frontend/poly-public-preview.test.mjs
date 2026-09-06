// tests/frontend/poly-public-preview.test.mjs — 01.08.2026 (Lucas):
// (#69) Sharp-Signal nach Wallet-Qualität gewichten: bewiesene Wallet mit hoher Trefferquote +
//   positiver Lifetime-P&L hebt die Conviction; die „Warum"-Zeile zeigt den Record.
// (#70) Public-Kandidat „Top-Play" — hart gegatet (Conv≥9 + Wallet n≥8 & ≥55% + Geld-Mehrheit ≥60%).
// (#71) Public-Kandidat „Whale-Watch" — Public-Schwelle (untracked ≥$100K / tracked ≥$25K) auf open.
// Alle drei sind NUR Vorschau/Analyse — es wird nichts gesendet.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const PW = new URL('../../poly-wallets.js', import.meta.url);

function boot(files) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="polyWalletsPanel"></div></body>',
    { url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url) => { const u = String(url); let b = null;
    for (const [f, d] of Object.entries(files)) if (u.includes(f)) { b = d; break; }
    return Promise.resolve({ ok: b != null, json: () => Promise.resolve(b) }); };
  w.eval(readFileSync(PW, 'utf8'));
  return w;
}

// broadLive-Markt (poly_money_broad_close.json): frischer Anpfiff, keine Resolution.
function market(league, shares, prices, totalUsd) {
  return { league, resolved: null, totalUsd, shares, prices,
    hoursToKickoff: 3, capturedAt: new Date().toISOString() };
}

const BROAD = {
  // MLB: 65% Geld auf Braves, Preis auch Braves-Favorit → BET Braves. Scharfe Wallet auf Braves.
  'mlb-braves-padres': market('MLB',
    { 'Atlanta Braves': 65000, 'San Diego Padres': 35000 },
    { 'Atlanta Braves': 0.62, 'San Diego Padres': 0.38 }, 100000),
  // NBA: nur Whale-Kandidat (untracked $120K), kein Shortlist-Signal nötig
  'nba-lakers-celtics': market('NBA',
    { 'Lakers': 55000, 'Celtics': 45000 },
    { 'Lakers': 0.55, 'Celtics': 0.45 }, 100000),
};

const TRACK = {
  updatedAt: new Date().toISOString(),
  scores: {
    // 29.08.2026: n von 10 auf 60 gehoben. Nicht um einen Test gruen zu bekommen, sondern weil die
    // Fixture sonst das Falsche behauptet: seit der Wallet-Neugewichtung ist eine Historie aus 10
    // abgerechneten Plays bewusst duenn (Konfidenzfaktor 0,5) und soll KEINEN Public-Kandidaten
    // tragen. Diese Tests pruefen die Sportart-Sperre, nicht die Stichprobengroesse — also eine
    // Wallet, die wirklich belegt ist: n60, 70% Treffer, +CLV, +$150K lifetime.
    '0xSHARP': { n: 60, clvSumPP: 120, wins: 42, usd: 40000, pnl: 150000 },
    // ... und dieselbe Qualitaet auf duenner Basis, fuer den Vergleich in #69.
    '0xTHIN':  { n: 10, clvSumPP: 20,  wins: 7,  usd: 40000, pnl: 150000 },
  },
  open: [
    { wallet: '0xSHARP', key: 'mlb-braves-padres', side: 'Atlanta Braves', league: 'MLB',
      usd: 40000, entryPrice: 0.55, lastPrice: 0.62 },
    // untracked Whale auf NBA: $120K, Preis 55¢ → Public-Whale-Kandidat
    { wallet: '0xWHALE', key: 'nba-lakers-celtics', side: 'Lakers', league: 'NBA',
      usd: 120000, entryPrice: 0.50, lastPrice: 0.55 },
    // untracked, aber unter Schwelle ($40K) → NICHT
    { wallet: '0xSMALL', key: 'nba-lakers-celtics', side: 'Celtics', league: 'NBA',
      usd: 40000, entryPrice: 0.45, lastPrice: 0.45 },
  ],
};

function withData(fn) {
  const w = boot({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_money_broad_close.json': BROAD,
    'poly_money_broad_history.json': {},
    'poly_money_broad.json': { n: 100, byLeague: [{ league: 'MLB', verdict: 'neutral' }] },
    'poly_wallet_track.json': TRACK,
    'poly_cross_sport.json': { discrepancies: [] },
  });
  // Lexischen _pwCache über den schlanken Loader füllen (wie die Übersicht-Box es tut).
  return new Promise((resolve) => { w._pwEnsurePlaysData(() => resolve(fn(w))); });
}

test('#69 Sharp-Qualität: bewiesene Wallet hebt Conviction + Warum zeigt Record', async () => {
  await withData((w) => {
    const info = w._pwSharpInfoForKey('mlb-braves-padres');
    assert.ok(info, 'Sharp-Info für den Key vorhanden');
    assert.strictEqual(info.side, 'Atlanta Braves');
    assert.strictEqual(info.n, 60);
    assert.strictEqual(info.wins, 42);
    assert.ok(Math.abs(info.hit - 0.7) < 1e-9, 'Trefferquote 70%');
    assert.ok(info.pnl > 0, 'positive Lifetime-P&L');

    const r = w._pwShortlistScore('mlb-braves-padres', BROAD['mlb-braves-padres']);
    assert.strictEqual(r.verdict, 'BET');
    assert.strictEqual(r.side, 'Atlanta Braves');
    assert.ok(r.reasons.some(x => /scharfe Wallet \(42\/60, 70% · \+\$150K\)/.test(x)),
      'Warum zeigt den Wallet-Record: ' + JSON.stringify(r.reasons));
    assert.ok(r.sharp && r.sharp.n === 60, 'Sharp-Record am Play angehängt');
  });
});

// 29.08.2026 (Lucas-Checkup, „D"): Der Test darf nicht an einer festen Conviction haengen — genau
// daran waere er beim Umgewichten gekippt, ohne dass etwas kaputt war. Was wirklich gelten muss,
// ist die REIHENFOLGE: ohne Wallet-Beleg < duenne Historie < belegte Historie. Und der Abstand
// zwischen duenn und belegt muss sichtbar sein, sonst ist der Konfidenzfaktor Dekoration.
test('#69b Wallet-Gewicht skaliert mit der Historie, nicht nur mit der Trefferquote', async () => {
  const mk = (scores, open) => new Promise((resolve) => {
    const w = boot({
      'poly_money_broad_close.json': BROAD, 'poly_money_broad_history.json': {},
      'poly_money_broad.json': { n: 100, byLeague: [{ league: 'MLB', verdict: 'neutral' }] },
      'poly_wallet_track.json': { updatedAt: new Date().toISOString(), scores, open },
      'poly_cross_sport.json': { discrepancies: [] },
    });
    w._pwEnsurePlaysData(() => resolve(w._pwShortlistScore('mlb-braves-padres', BROAD['mlb-braves-padres'])));
  });
  const pos = (wallet) => [{ wallet, key: 'mlb-braves-padres', side: 'Atlanta Braves',
    league: 'MLB', usd: 40000, entryPrice: 0.55, lastPrice: 0.62 }];

  const ohne  = await mk({}, []);
  const duenn = await mk({ '0xTHIN':  TRACK.scores['0xTHIN']  }, pos('0xTHIN'));
  const dick  = await mk({ '0xSHARP': TRACK.scores['0xSHARP'] }, pos('0xSHARP'));

  const c = (r) => (r && r.verdict !== 'SKIP') ? (r.conv || 0) : 0;
  assert.ok(c(dick) > c(duenn),
    `belegte Historie (n60) muss schwerer wiegen als duenne (n10): ${c(dick)} vs ${c(duenn)}`);
  assert.ok(c(duenn) >= c(ohne),
    `eine duenne Historie darf nie WENIGER zaehlen als gar keine: ${c(duenn)} vs ${c(ohne)}`);
  // Und der Abstand muss wirken, nicht nur existieren: mit 65% Geld PLUS einer 10-Play-Historie
  // reicht es seit der Neugewichtung nicht mehr ueber die Play-Schwelle — mit 60 Plays schon.
  assert.strictEqual(dick.verdict, 'BET', 'belegte Wallet traegt den Play');
  assert.strictEqual(duenn.verdict, 'SKIP',
    'duenne Wallet + 65% Geld kommt nicht mehr ueber die Schwelle (genau das war der Cricket-Fall)');
});

test('#70 Public Top-Play: MLB fällt seit 24.08. aus dem Public-Gate (US-Sport gesperrt)', async () => {
  // Der Play erfüllt ALLE inhaltlichen Gates — er fliegt allein an der Sportart raus. Grund:
  // im Papier-Depot brachte US-Sport über 78 Plays −29,6% ROI bei Ø CLV −0,51pp, und der
  // öffentliche Track-Record ist das Produkt. Im Scan/Depot bleibt der Play (Beobachtung).
  await withData((w) => {
    const r = w._pwShortlistScore('mlb-braves-padres', BROAD['mlb-braves-padres']);
    // 29.08.2026: nicht mehr gegen eine feste Zahl, sondern gegen das Gate selbst — sonst prueft
    // der Test die Kalibrierung mit, obwohl es hier um die Sportart-Sperre geht.
    assert.ok(r.conv >= w._pwPublicMinConv() && r.moneyPct >= 0.60 && r.sharp && r.sharp.n >= 8,
      'inhaltlich weiterhin ein starker Play: ' + JSON.stringify({ conv: r.conv, money: r.moneyPct }));
    assert.strictEqual(w._pwPublicTopPlays().length, 0, 'aber kein Public-Kandidat mehr');
    assert.ok(w._pwTopPlays(0, false, false).some(p => p.key === 'mlb-braves-padres'),
      'im Scan/Papier-Depot bleibt er drin — sonst könnte man einen Umschwung nie bemerken');
  });
});

test('#70 Public Top-Play: dieselbe Konstellation in erlaubter Sportart → Kandidat', async () => {
  // Gegenprobe: nur die Liga getauscht (EPL statt MLB), sonst identisch.
  const broad2 = { 'epl-arsenal-chelsea': market('EPL',
    { 'Arsenal': 65000, 'Chelsea': 35000 }, { 'Arsenal': 0.62, 'Chelsea': 0.38 }, 100000) };
  const track2 = { updatedAt: new Date().toISOString(),
    // 29.08.2026: n10 -> n60, wie in der Haupt-Fixture. Der Test prueft die Sportart-Gegenprobe,
    // nicht die Stichprobe; mit 10 Plays waere es seit der Neugewichtung zurecht kein Kandidat.
    scores: { '0xSHARP': { n: 60, clvSumPP: 120, wins: 42, usd: 40000, pnl: 150000 } },
    open: [{ wallet: '0xSHARP', key: 'epl-arsenal-chelsea', side: 'Arsenal', league: 'EPL',
             usd: 40000, entryPrice: 0.55, lastPrice: 0.62 }] };
  const w = boot({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_money_broad_close.json': broad2, 'poly_money_broad_history.json': {},
    'poly_money_broad.json': { n: 100, byLeague: [] },
    'poly_wallet_track.json': track2, 'poly_cross_sport.json': { discrepancies: [] },
  });
  await new Promise((res) => w._pwEnsurePlaysData(res));
  const tops = w._pwPublicTopPlays();
  assert.strictEqual(tops.length, 1, 'Fußball-Play bleibt Public-Kandidat');
  assert.strictEqual(tops[0].side, 'Arsenal');
});

test('#70 Sperrliste ist EINE Quelle (window.PW_BLOCKED_BET_CATS)', async () => {
  await withData((w) => {
    // Array kommt aus dem jsdom-Realm -> ueber den Inhalt vergleichen, nicht referenzgleich.
    assert.deepStrictEqual(Array.from(w.PW_BLOCKED_BET_CATS), ['US-Sport', 'Kampfsport']);
    assert.strictEqual(w._pwBetBlocked({ league: 'MLB' }), true);
    assert.strictEqual(w._pwBetBlocked({ league: 'UFC' }), true);
    assert.strictEqual(w._pwBetBlocked({ league: 'ATP' }), false);
    assert.strictEqual(w._pwBetBlocked({ league: 'EPL' }), false);
  });
});

test('#70 Public Top-Play: schwache Wallet fällt raus', async () => {
  const track2 = JSON.parse(JSON.stringify(TRACK));
  track2.scores['0xSHARP'] = { n: 5, clvSumPP: 5, wins: 2, usd: 40000, pnl: -10000 }; // n<8, hit40%, P&L neg
  const w = boot({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_money_broad_close.json': BROAD, 'poly_money_broad_history.json': {},
    'poly_money_broad.json': { n: 100, byLeague: [] },
    'poly_wallet_track.json': track2, 'poly_cross_sport.json': { discrepancies: [] },
  });
  await new Promise((res) => w._pwEnsurePlaysData(res));
  assert.strictEqual(w._pwPublicTopPlays().length, 0, 'n<8 & schwach → kein Public-Top-Play');
});

test('#71 Whale-Public: nur Positionen über der Schwelle + Sport + Preis 3–97¢', async () => {
  await withData((w) => {
    const c = w._pwWhalePublicCandidates();
    const lakers = c.find(x => x.side === 'Lakers');
    assert.ok(lakers, 'untracked $120K Lakers-Whale ist Kandidat');
    assert.strictEqual(lakers.tracked, false);
    assert.ok(!c.some(x => x.side === 'Celtics'), 'untracked $40K unter $100K-Schwelle → raus');
  });
});

test('#71 Whale-Public: tracked-Schwelle greift bei $25K', async () => {
  const track3 = JSON.parse(JSON.stringify(TRACK));
  // 0xWHALE jetzt getrackt mit n8 → Schwelle $25K statt $100K; setze eine $30K-Position dazu
  track3.scores['0xMID'] = { n: 8, clvSumPP: 8, wins: 5, usd: 30000, pnl: 5000 };
  track3.open.push({ wallet: '0xMID', key: 'nba-lakers-celtics', side: 'Celtics', league: 'NBA',
    usd: 30000, entryPrice: 0.45, lastPrice: 0.45 });
  const w = boot({
    'mls-data.json': { groups: {} }, 'mls_poly_prices.json': { prices: {} },
    'mls_poly_wallets.json': { topPositionsAll: [], matches: {}, updatedAt: new Date().toISOString() },
    'poly_money_broad_close.json': BROAD, 'poly_money_broad_history.json': {},
    'poly_money_broad.json': { n: 100, byLeague: [] },
    'poly_wallet_track.json': track3, 'poly_cross_sport.json': { discrepancies: [] },
  });
  await new Promise((res) => w._pwEnsurePlaysData(res));
  const c = w._pwWhalePublicCandidates();
  const mid = c.find(x => x.side === 'Celtics');
  assert.ok(mid && mid.tracked, 'getrackte $30K-Position ist Kandidat (Schwelle $25K)');
});

// ── 01.09.2026: der Regler darf nicht in den öffentlichen Kanal sickern ──────────────────────
// Als der Sharp-Beitrag von einem Schalter auf einen Regler umgestellt wurde, existierte
// `r.sharp` plötzlich auch für NICHT bewiesene Wallets. Das Public-Gate prüfte aber nur
// `r.sharp && n>=8 && hit>=0.55` — die Lockerung hätte damit still die öffentliche Schwelle
// mitgesenkt. Genau die Bauform „eine Änderung sickert in eine Fläche, für die sie nie gedacht war".
function ladePublicGate() {
  const src = readFileSync(PW, 'utf8');
  const von = src.indexOf('const PW_PUBLIC_MIN_CONV=');
  const bisZeile = src.indexOf('\n', von);
  // 06.09.2026: das Gate wurde in seine Teile zerlegt (_pwTermWalletOk / _pwTermPublicRest),
  // damit die Wallet-Bedingung für die Kontrollgruppe WEGGELASSEN werden kann. Der Extraktor
  // schnitt vorher nur `_pwTermIsPublic` heraus und fand die Helfer nicht mehr. Er nimmt jetzt
  // den ganzen Block — die Prüfung selbst bleibt unverändert: das öffentliche Gate darf sich
  // durch die Zerlegung nicht gelockert haben.
  const fnVon = src.indexOf('function _pwTermWalletOk');
  const ende = src.indexOf('function _pwTermIsPublicOhneWallet');
  const fnBis = ende > fnVon ? ende : (src.indexOf('\n}', src.indexOf('function _pwTermIsPublic')) + 2);
  assert.ok(von > 0 && fnVon > 0, 'Public-Gate in poly-wallets.js nicht gefunden');
  const g = {};
  // eslint-disable-next-line no-new-func
  new Function('exp', src.slice(von, bisZeile) + '\n' + src.slice(fnVon, fnBis)
    + '\nexp.isPublic=_pwTermIsPublic; exp.minConv=PW_PUBLIC_MIN_CONV;'
    + '\nexp.walletOk=_pwTermWalletOk; exp.rest=_pwTermPublicRest;')(g);
  return g;
}
const PG = ladePublicGate();
const play = (over = {}) => ({ conv: PG.minConv, moneyPct: 0.7,
  sharp: { n: 20, hit: 0.6, grade: 1 }, ...over });

test('Public-Gate: bewiesene Wallet kommt durch', () => {
  assert.strictEqual(PG.isPublic(play()), true);
});

test('Public-Gate: NUR vielversprechende Wallet kommt NICHT durch', () => {
  // Genau der Fall, den der Regler neu erzeugt: Beleg 0,98 — fürs Abwägen fast voll,
  // für den öffentlichen Kanal trotzdem nicht bewiesen.
  assert.strictEqual(PG.isPublic(play({ sharp: { n: 65, hit: 0.6, grade: 0.98 } })), false,
    'ein Play mit unbewiesener Wallet darf nie öffentlich werden');
  assert.strictEqual(PG.isPublic(play({ sharp: { n: 65, hit: 0.6, grade: 0.5 } })), false);
});

test('Public-Gate: alte Objekte ohne grade bleiben gültig', () => {
  // Rückwärts-Kompatibilität: ein sharp-Objekt aus einer älteren Datei hat kein grade-Feld.
  assert.strictEqual(PG.isPublic(play({ sharp: { n: 20, hit: 0.6 } })), true);
});

test('Public-Gate: die harten Schwellen gelten weiter', () => {
  assert.strictEqual(PG.isPublic(play({ conv: PG.minConv - 1 })), false, 'Conviction zu niedrig');
  assert.strictEqual(PG.isPublic(play({ moneyPct: 0.5 })), false, 'Geld-Mehrheit zu dünn');
  assert.strictEqual(PG.isPublic(play({ sharp: { n: 7, hit: 0.9, grade: 1 } })), false, 'Stichprobe zu klein');
  assert.strictEqual(PG.isPublic(play({ sharp: { n: 20, hit: 0.5, grade: 1 } })), false, 'Trefferquote zu niedrig');
  assert.strictEqual(PG.isPublic(play({ sharp: null })), false, 'ohne Wallet gar nicht');
});

test('Public-Gate ist EINE Quelle — nicht zweimal ausgeschrieben', () => {
  const src = readFileSync(PW, 'utf8');
  const treffer = src.match(/r\.sharp\.n>=8 && r\.sharp\.hit>=0\.55/g) || [];
  assert.strictEqual(treffer.length, 1,
    'die Public-Bedingung steht wieder an mehreren Stellen — sie läuft dann auseinander');
});

// ── 06.09.2026: die Kontrollgruppe darf das Gate nicht verändern ─────────────────────────────
// Von 172 abgerechneten Public-Kandidaten waren 172 sharp — ohne Vergleichsgruppe ist nicht
// messbar, ob das Wallet-Tor etwas beiträgt. Die Zerlegung schafft die Gruppe; sie darf aber
// das öffentliche Gate nicht anfassen.
test('Public bleibt exakt die Konjunktion aus Rest und Wallet', () => {
  const ok = play();
  assert.equal(PG.isPublic(ok), PG.rest(ok) && PG.walletOk(ok));
  const ohneWallet = play({ sharp: { n: 20, hit: 0.6, grade: 0.6 } });
  assert.equal(PG.isPublic(ohneWallet), false, 'unbewiesene Wallet darf nicht öffentlich werden');
  assert.equal(PG.rest(ohneWallet), true, 'Conviction und Mehrheit stimmen ja');
  assert.equal(PG.walletOk(ohneWallet), false);
});

test('die Kontrollgruppe ist genau der Rest ohne Wallet-Nachweis', () => {
  const kandidat = play({ sharp: { n: 20, hit: 0.6, grade: 0.6 } });
  assert.ok(PG.rest(kandidat) && !PG.walletOk(kandidat),
    'genau diese Kombination bildet die Kontrollgruppe');
  const zuWenigConv = play({ conv: PG.minConv - 1, sharp: { n: 20, hit: 0.6, grade: 0.6 } });
  assert.equal(PG.rest(zuWenigConv), false,
    'wer schon an der Conviction scheitert, gehört nicht in die Kontrollgruppe');
});
