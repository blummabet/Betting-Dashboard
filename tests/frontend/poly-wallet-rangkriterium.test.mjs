// tests/frontend/poly-wallet-rangkriterium.test.mjs — 22.09.2026
//
// 🔴 Lucas: „na klar Trefferquote ist nur ne Zusatzinfo / interessant ist einfach Profit der
// Wallet in Wahrheit / auf Poly treiben sich gute Leute rum und die gilt es zu erfassen /
// können Leute sein die 5K pro Wette setzen oder auch 50K oder mehr."
//
// Die Rangliste kannte genau EIN Kriterium (CLV-UG). Der gemessene Sport-Profit stand daneben
// und konnte nichts ordnen. Jetzt ordnet er — und genau daraus entstehen drei neue Fehlerklassen,
// die dieser Test abdeckt:
//
//  (1) „fehlende Information rendert als harmloser Default": eine Wallet ohne Auflösung im
//      Fenster hat keinen Profit von 0, sie hat keinen. Als 0 sortiert stünde sie vor jeder
//      Wallet, die im Fenster Geld verloren hat.
//  (2) „eine Anzeige-Einstellung, die still eine Auswahl verschiebt": `_pwRankRows()` speist den
//      Betting-Tab. Ein Sortier-Chip im Wallets-Menü darf dort nichts bewegen.
//  (3) „ein Satz behauptet, was die Zahl daneben widerlegt": der Kopftext sagte fest „sortiert
//      nach der CLV-Untergrenze" — auf zwei von drei Sortierungen wäre das schlicht falsch.
//
// Dazu der Schärfe-Floor. Gemessen am 22.09.2026 über poly_wallet_track.json: von 683 Wallets ab
// $1.000 Ø-Einsatz wirft er 339 raus, darunter 90 von 142 mit positivem 30-Tage-Profit — die
// zweitbeste Wallet überhaupt (+$864K/30T, ROI +26,5 %, n=92) wegen Ø CLV −0,1pp. Auf einer
// Profit-Sortierung ist das kein Detail, also ist er schaltbar und seine Wirkung steht als Zahl
// auf der Fläche.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const ROOT = new URL('../../', import.meta.url);
const JS = readFileSync(new URL('poly-wallets.js', ROOT), 'utf8');

function fenster(cache) {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
  w.eval(JS);
  w.eval('_pwRender = function(){};');          // Zustandswechsel ohne Neuzeichnen
  w._pwCache = cache || {};
  return w;
}

// n=40 ⇒ über PW_RANK_MIN_N_PNL, usd/n = $2.000 ⇒ über dem Einsatz-Filter.
// clvSq so gesetzt, dass eine echte Untergrenze entsteht.
function wallet(o) {
  const n = o.n || 40;
  return Object.assign({
    pnl: 1000, n, wins: Math.round(n * (o.hit == null ? 0.6 : o.hit)),
    clvSumPP: n * (o.clv == null ? 1.0 : o.clv),
    clvSqSum: n * 4, usd: n * 2000,
    lastTs: new Date().toISOString(),
  }, o.extra || {});
}
const scores = (obj) => obj;

// A verdient viel im Fenster, hat aber den schlechteren CLV. B ist umgekehrt.
// C hat im Fenster VERLOREN. D hat im Fenster gar nichts aufgelöst.
const BESTAND = scores({
  '0xa': wallet({ clv: 0.2, hit: 0.55, extra: { fenster7: { gewinn: 9000, roi: 0.3, n: 10, nGeld: 10 },
                                                fenster30: { gewinn: 50000, roi: 0.25, n: 30, nGeld: 30 } } }),
  '0xb': wallet({ clv: 3.0, hit: 0.65, extra: { fenster7: { gewinn: 100, roi: 0.01, n: 10, nGeld: 10 },
                                                fenster30: { gewinn: 900, roi: 0.02, n: 30, nGeld: 30 } } }),
  '0xc': wallet({ clv: 1.5, hit: 0.60, extra: { fenster7: { gewinn: -4000, roi: -0.4, n: 10, nGeld: 10 },
                                                fenster30: { gewinn: -7000, roi: -0.3, n: 30, nGeld: 30 } } }),
  '0xd': wallet({ clv: 2.0, hit: 0.62, extra: {} }),
});
const rang = (rows) => rows.map(r => r.wallet);

test('⭐ ohne Argument sortiert die Rangliste nach dem gemessenen Profit', () => {
  // 🔴 22.09.2026, wenige Stunden nach dem Bau der Chips. Hier stand „unverändert nach der
  // CLV-Untergrenze" — Lucas: „Man kann CLV anzeigen, aber es darf kein Kriterium sein, dass
  // irgendwas gekickt wird." Eine Sortierung, die bei 20 Zeilen abschneidet, IST ein Kriterium.
  const w = fenster();
  const r = rang(w._pwRankRowsPnl(BESTAND));
  assert.strictEqual(r[0], '0xa', 'der höchste 30-Tage-Profit gehört nach oben');
  // und die Vorgabe steht auch so im Code, nicht nur im Ergebnis dieser Fixture
  assert.match(readFileSync(new URL('poly-wallets.js', ROOT), 'utf8'),
    /const PW_RANK_KRIT_STD = 'profit30';/);
});

test('⭐ nach Profit 30T sortiert steht die Geld-Wallet oben', () => {
  const w = fenster();
  // Floor aus, sonst wirft der gemessene 30-Tage-Verlust 0xc heraus, bevor sortiert wird.
  const r = rang(w._pwRankRowsPnl(BESTAND, 'profit30', false));
  assert.strictEqual(r[0], '0xa', '+$50.000 über 30 Tage gehört auf #1');
  assert.ok(r.indexOf('0xb') < r.indexOf('0xc'), '+$900 gehört vor −$7.000');
});

test('⭐ CLV bleibt als Sortier-Option erhalten — er wird gemessen, er entscheidet nur nichts', () => {
  const w = fenster();
  const r = rang(w._pwRankRowsPnl(BESTAND, 'clvUg', false));
  assert.strictEqual(r[0], '0xb', 'wer den Chip auf CLV stellt, bekommt CLV');
});

test('Profit 7T und Profit 30T sind zwei verschiedene Fenster', () => {
  const w = fenster();
  // Eine Wallet, die über 7 Tage vorne liegt und über 30 hinten — sonst wäre „liest f7" grün,
  // auch wenn die Funktion f30 läse.
  const b = Object.assign({}, BESTAND, {
    '0xe': wallet({ clv: 0.1, hit: 0.5, extra: { fenster7: { gewinn: 99000, roi: 0.9, n: 9, nGeld: 9 },
                                                 fenster30: { gewinn: 10, roi: 0.001, n: 30, nGeld: 30 } } }),
  });
  assert.strictEqual(rang(w._pwRankRowsPnl(b, 'profit7'))[0], '0xe');
  assert.strictEqual(rang(w._pwRankRowsPnl(b, 'profit30'))[0], '0xa');
});

test('⭐ eine Wallet ohne Auflösung im Fenster steht UNTEN, nicht bei null', () => {
  const w = fenster();
  // BEIDE Eingabe-Reihenfolgen. Steht die ungemessene ohnehin schon hinten, ist „gib 0 zurück"
  // eine gruene Mutation: 0 heisst gleichwertig, und eine stabile Sortierung laesst sie dann
  // einfach stehen. Erst die umgekehrte Reihenfolge zeigt, ob wirklich verschoben wird.
  const messbar = { '0xc': BESTAND['0xc'], '0xa': BESTAND['0xa'] };
  for (const [name, b] of [['ungemessen zuerst', { '0xd': BESTAND['0xd'], ...messbar }],
                           ['ungemessen zuletzt', { ...messbar, '0xd': BESTAND['0xd'] }]]) {
    const r = rang(w._pwRankRowsPnl(b, 'profit30', false));
    assert.ok(r.indexOf('0xd') > r.indexOf('0xc'),
      name + ': ungemessen als 0 sortiert stünde 0xd vor der Wallet, die −$7.000 gemacht hat — '
      + 'die Rangliste behauptete damit eine Auskunft, die sie nicht hat');
    assert.strictEqual(r[r.length - 1], '0xd', name);
  }
});

test('⭐ der Vergleich selbst stellt ungemessen hinter gemessen — in beide Richtungen', () => {
  // Der Fall, den die fertige Liste nicht zeigt: eine stabile Sortierung liefert bei
  // `return 0` („gleichwertig") in mancher Eingabe-Reihenfolge dasselbe Ergebnis wie ein
  // korrektes Verschieben. Die Mutation `if (wa == null) return 0` ueberlebte genau daran.
  const w = fenster();
  const cmp = w._pwRangVergleich('profit30');
  const A = w._pwRankRowsPnl({ '0xa': BESTAND['0xa'] }, 'profit30', false)[0];   // +$50.000
  const C = w._pwRankRowsPnl({ '0xc': BESTAND['0xc'] }, 'profit30', false)[0];   // −$7.000
  const D = w._pwRankRowsPnl({ '0xd': BESTAND['0xd'] }, 'profit30', false)[0];   // ungemessen
  assert.ok(cmp(D, C) > 0, 'ungemessen gehört HINTER eine Wallet, die Geld verloren hat');
  assert.ok(cmp(C, D) < 0, 'und zwar auch, wenn die Argumente andersherum kommen');
  assert.ok(cmp(A, C) < 0);
  assert.ok(cmp(C, A) > 0);
  // Antisymmetrie als Eigenschaft, nicht als Einzelfall: sonst haengt das Ergebnis vom
  // Sortier-Algorithmus ab statt von der Regel.
  for (const x of [A, C, D]) for (const y of [A, C, D]) {
    assert.strictEqual(Math.sign(cmp(x, y)) + Math.sign(cmp(y, x)), 0);   // -0 === 0 waere hier falsch-negativ
  }
});

test('zwei ungemessene untereinander ordnet weiterhin die CLV-Untergrenze', () => {
  const w = fenster();
  // Die schwaechere Wallet steht in der EINGABE vorn — sonst waere \`return 0\` gruen, weil eine
  // stabile Sortierung die schon richtige Reihenfolge einfach stehen laesst.
  const b = { '0xf': wallet({ clv: 0.1, hit: 0.5 }), '0xd': BESTAND['0xd'] };
  assert.strictEqual(rang(w._pwRankRowsPnl(b, 'profit30')).join(','), '0xd,0xf');
});

test('⭐ der Sortier-Chip verschiebt NICHT, was der Betting-Tab bekommt', () => {
  // `_pwRankRows()` speist die Whale-Plays im Betting-Tab. Eine Anzeige-Einstellung im
  // Wallets-Menü, die dort still eine andere Auswahl einspielt, wäre genau die Kopplung,
  // die in diesem Repo schon dreimal zugeschlagen hat.
  const w = fenster({ walletTrack: { scores: BESTAND } });
  const vorher = rang(w._pwRankRows()).join(',');
  w.eval('_pwSetRankKrit("clvUg"); _pwSetRankFloor(false);');
  assert.strictEqual(rang(w._pwRankRows()).join(','), vorher);
  assert.ok(vorher.startsWith('0xa'), 'und zwar auf der Vorgabe (gemessener 30-Tage-Profit)');
});

test('der gerenderte Abschnitt folgt dem Chip', () => {
  const w = fenster({ walletTrack: { scores: BESTAND } });
  const html = () => w.eval('_pwSharpRanking()');
  const vorZuerst = (h, a, b) => h.indexOf(a) < h.indexOf(b);
  assert.ok(vorZuerst(html(), '0xa', '0xb'), 'Vorgabe ist der Profit');
  w.eval('_pwSetRankKrit("clvUg");');
  assert.ok(vorZuerst(html(), '0xb', '0xa'), 'die Tabelle ignoriert das gewählte Kriterium');
});

test('⭐ der Kopftext behauptet nicht das Kriterium, nach dem gerade NICHT sortiert wird', () => {
  const w = fenster({ walletTrack: { scores: BESTAND } });
  w.eval('_pwSetRankKrit("profit30");');
  const h = w.eval('_pwSharpRanking()');
  assert.doesNotMatch(h, /sortiert nach der <b>CLV-Untergrenze<\/b>/);
  assert.match(h, /gemessenen Sport-Profit<\/b> der letzten 30 Tage/);
});

test('die aktive Spalte ist als die aktive markiert — und nur sie', () => {
  const w = fenster({ walletTrack: { scores: BESTAND } });
  w.eval('_pwSetRankKrit("profit7");');
  const h = w.eval('_pwSharpRanking()');
  // Nicht `/▼ /` — die Spalte „zuletzt" trägt „▲/▼" in ihrem Tooltip. Ein Test, der das
  // mitzählt, misst etwas anderes als die Frage, die er stellt. (Genau hineingelaufen.)
  const treffer = (h.match(/>▼ /g) || []).length;
  assert.strictEqual(treffer, 1, 'genau eine Spalte darf die Reihenfolge für sich reklamieren');
  assert.match(h, />▼ Profit 7T/);
});

test('der Schärfe-Floor ist an, solange niemand ihn abschaltet', () => {
  const w = fenster();
  // clv −1pp und Treffer 40 % bei n=40: fällt durch beide Hälften des Floors.
  const b = { '0xg': wallet({ clv: -1, hit: 0.4, extra: { fenster30: { gewinn: 800000, roi: 0.3, n: 30, nGeld: 30 } } }) };
  assert.strictEqual(w._pwRankRowsPnl(b, 'profit30').length, 0);
  assert.strictEqual(w._pwRankRowsPnl(b, 'profit30', false).length, 1,
    'ausgeschaltet muss die Wallet durchkommen, sonst schaltet der Chip nichts');
});

test('⭐ der Floor filtert nicht mehr nach CLV', () => {
  // 🔴 22.09.2026. Hier stand, dass ein negativer Ø CLV allein zum Rauswurf reicht.
  // Genau das war Lucas' Beschwerde: „siehst du, dann fliegen gute Wallets raus."
  const w = fenster();
  const nurClvSchlecht = { '0xh': wallet({ clv: -5, hit: 0.8 }) };
  assert.strictEqual(w._pwRankRowsPnl(nurClvSchlecht).length, 1,
    'ein negativer CLV darf niemanden mehr aus der Liste werfen');
});

test('⭐ die beiden Hälften, die geblieben sind, wirken einzeln', () => {
  // Ohne diese Fälle bliebe „&&" statt „||" eine grüne Mutation.
  const w = fenster();
  const trefferSchlecht = { '0xi': wallet({ clv: 3, hit: 0.3 }) };
  const geldVerlust = { '0xj': wallet({ clv: 3, hit: 0.8,
    extra: { fenster30: { gewinn: -4000, roi: -0.2, n: 30, nGeld: 30 } } }) };
  const geldUngemessen = { '0xk': wallet({ clv: -3, hit: 0.8 }) };
  assert.strictEqual(w._pwRankRowsPnl(trefferSchlecht).length, 0, 'Treffer unter 45 % muss reichen');
  assert.strictEqual(w._pwRankRowsPnl(geldVerlust).length, 0, 'gemessener 30T-Verlust muss reichen');
  assert.strictEqual(w._pwRankRowsPnl(geldUngemessen).length, 1,
    '„nicht gemessen" ist kein Verlust — sonst hinge das Tor an der Mess-Abdeckung (9 %)');
});

test('⭐ die Floor-Bilanz zählt die Zurückgehaltenen — und die davon im Plus', () => {
  const w = fenster();
  const b = {
    '0xg': wallet({ clv: -1, hit: 0.4, extra: { fenster30: { gewinn: 800000, roi: 0.3, n: 30, nGeld: 30 } } }),  // raus, im Plus
    '0xj': wallet({ clv: -1, hit: 0.4, extra: { fenster30: { gewinn: -500, roi: -0.1, n: 30, nGeld: 30 } } }),   // raus, im Minus
    '0xk': wallet({ clv: 2, hit: 0.6, extra: { fenster30: { gewinn: 300, roi: 0.05, n: 30, nGeld: 30 } } }),     // bleibt, im Plus
  };
  const bil = w._pwFloorBilanz(b);
  assert.strictEqual(bil.kandidaten, 3);
  assert.strictEqual(bil.raus, 2);
  assert.strictEqual(bil.rausImPlus, 1, 'nur die zurückgehaltene mit Gewinn > 0 zählt');
  assert.strictEqual(bil.imPlus, 2);
});

test('die Bilanz steht auf der Fläche, nicht nur im Test', () => {
  const w = fenster({ walletTrack: { scores: BESTAND } });
  const h = w.eval('_pwSharpRanking()');
  assert.match(h, /Floor haelt gerade/);
  assert.match(h, /_pwSetRankFloor\(false\)/, 'ohne Schalter ist die Zahl eine Sackgasse');
});

test('bei abgeschaltetem Floor sagt der Kopftext das auch', () => {
  const w = fenster({ walletTrack: { scores: BESTAND } });
  w.eval('_pwSetRankFloor(false);');
  const h = w.eval('_pwSharpRanking()');
  assert.match(h, /Schärfe-Floor ist <b>aus<\/b>/);
  assert.doesNotMatch(h, /Wallets, die den Close schlagen/,
    'sonst behauptet die Überschrift eine Filterung, die gerade nicht stattfindet');
});

test('am echten Bestand: die Profit-Sortierung liefert eine ANDERE Reihenfolge', () => {
  // Wäre sie identisch, hätte der Chip keinen Zweck — und wir hätten es nicht gemerkt.
  const track = JSON.parse(readFileSync(new URL('poly_wallet_track.json', ROOT), 'utf8'));
  const w = fenster({ walletTrack: track });
  const a = rang(w._pwRankRowsPnl(track.scores, 'clvUg')).join(',');
  const b = rang(w._pwRankRowsPnl(track.scores, 'profit30')).join(',');
  if (!a || !b) return;
  assert.notStrictEqual(a, b);
});
