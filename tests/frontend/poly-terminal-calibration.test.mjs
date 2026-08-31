// tests/frontend/poly-terminal-calibration.test.mjs
// 21.08.2026 (Lucas #3): Track-kalibrierte Konviktion aus poly_shortlist_track.json.
// Kern-Erkenntnis der Daten: sharp/steam ALLEIN verlieren stark, nur mit money gewinnen sie.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

function load(track) {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url:'https://x.com/', runScripts:'outside-only' });
  const { window } = dom;
  window.eval(readFileSync(new URL('../../poly-wallets.js', import.meta.url), 'utf8'));
  window._pwCache = { shortlistTrack: track };
  return window;
}

const REAL = JSON.parse(readFileSync(new URL('../../poly_shortlist_track.json', import.meta.url), 'utf8'));

// 24.08.2026: Die Schwellen-Tests liefen gegen die LIVE-Datei, die der Bot alle 30 Min neu
// schreibt — sharp-allein driftete auf −9,07 % und riss damit die −10 %-Mute-Schwelle, ohne
// dass jemand Code angefasst hatte. Solche Tests sind Zeitbomben (vgl. den now()-Fall vom
// 20.07.). Schwellen prüfen wir deshalb an einem SYNTHETISCHEN Track; die inhaltliche
// Ordnung („sharp-allein schlechter als money+sharp") bleibt unten auf echten Daten.
function synth() {
  const rows = (sigs, wins, losses) => {
    const out = [];
    for (let i = 0; i < wins; i++)   out.push({ signals: sigs, result: 'win',  pnl:  10, stake: 10, clvPP: 0, conv: 6 });
    for (let i = 0; i < losses; i++) out.push({ signals: sigs, result: 'loss', pnl: -10, stake: 10, clvPP: 0, conv: 6 });
    return out;
  };
  const settled = [
    ...rows(['sharp'], 16, 24),            // n=40 → ROI −20 % (klar unter der −10 %-Mute-Schwelle)
    ...rows(['money', 'sharp'], 18, 12),   // n=30 → ROI +20 %
  ];
  return { settled, agg: { all: { n: settled.length, roi: 0 } } };
}

// 25.08.2026: Auch die AUSSAGE gehört nicht in einen Test gegen Live-Daten. Am 24.08. wurden hier
// die Schwellen auf einen synthetischen Track verlegt und die Ordnung „money+sharp schlägt
// sharp-allein" auf echten Daten stehen gelassen — genau die kippte einen Tag später von selbst
// (sharp −1,04 % vs money+sharp −1,26 % bei n=138/190; beide praktisch flach, der Abstand ist
// Rauschen). Eine Ordnung, die aus Bot-Daten kommt, ist ein BEFUND, kein Invariant: ändert er sich,
// ist das eine Nachricht an Lucas, kein roter Build. Auf echten Daten wird deshalb nur noch die
// VERDRAHTUNG geprüft; die inhaltliche Aussage steht am synthetischen Track ([[feedback_tests_no_live_data_thresholds]]).
test('_pwComboFor auf echten Daten: verdrahtet und plausibel — ohne Aussage ueber die Reihenfolge', () => {
  const w = load(REAL);
  for (const combo of [['sharp'], ['money','sharp']]) {
    const r = w._pwComboFor(combo);
    assert.ok(r, combo.join('+') + ' liefert kein Ergebnis');
    // ⚠️ 31.08.2026, DRITTE Runde desselben Fehlers in dieser Datei: hier stand `r.n >= 50`, und
    // der Build wurde rot mit „sharp-Combo zu duenn (n=47)". Niemand hatte Code angefasst.
    // `n` ist die GEWICHTETE Zahl — Plays aus einer aelteren Engine-Version zaehlen halb
    // (PW_CALIB_LEGACY_W). Beim Versionssprung auf 2026-08-29b halbierte sich der Bestand
    // schlagartig und waechst seitdem wieder. Eine Stichprobengroesse, die per Konstruktion
    // schrumpft und nachwaechst, ist niemals eine Invariante.
    // Auf echten Daten wird deshalb nur noch geprueft, dass der Eimer ueberhaupt existiert und
    // die Zahlen physikalisch moeglich sind. „Genug Daten zum Kalibrieren?" ist eine Frage an
    // die Anzeige, nicht an den Build ([[feedback_tests_no_live_data_thresholds]]).
    assert.ok(r.nRoh > 0, combo.join('+') + '-Combo kommt in den echten Daten gar nicht vor');
    assert.ok(r.n > 0, combo.join('+') + '-Combo hat kein Gewicht (n=' + r.n + ')');
    assert.ok(typeof r.roi === 'number' && Number.isFinite(r.roi), 'ROI ist eine endliche Zahl');
    assert.ok(r.roi > -1 && r.roi < 5, 'ROI in einem physikalisch moeglichen Band');
  }
  // Darf nicht werfen, egal wo die Zahlen gerade stehen.
  assert.ok(typeof w._pwTermMuted({ conv:6, signals:['sharp'] }).m === 'boolean');
});

// 31.08.2026: DAS ist der Mechanismus, an dem die Zahl oben gewandert ist — und im Gegensatz zur
// Stichprobengroesse steht er fest. Alt-Plays zaehlen im Gewicht halb, in der Roh-Zahl voll. Wer
// beides verwechselt, baut wieder einen Test, der von selbst kippt.
test('_pwComboStats: Alt-Plays zaehlen halb im Gewicht, voll in nRoh', () => {
  // Die beiden Konstanten sind `const` im Modul-Scope und landen NICHT auf window — hier also
  // aus der Quelle gelesen statt hart getippt. So wandert der Test beim naechsten
  // Versions-Sprung von selbst mit, statt still das Falsche zu pruefen.
  const SRC = readFileSync(new URL('../../poly-wallets.js', import.meta.url), 'utf8');
  const EV = /const PW_ENGINE_VERSION\s*=\s*'([^']+)'/.exec(SRC)[1];
  const LEG = Number(/const PW_CALIB_LEGACY_W\s*=\s*([0-9.]+)/.exec(SRC)[1]);
  const zeile = (ev, result) => ({ signals: ['sharp'], result, pnl: result === 'win' ? 10 : -10,
                                   stake: 10, clvPP: 0, conv: 6, ev });
  const w2 = load({ settled: [zeile(EV, 'win'), zeile(EV, 'loss'),
                              zeile('uralt', 'win'), zeile('uralt', 'loss')],
                    agg: { all: { n: 4, roi: 0 } } });
  const r = w2._pwComboFor(['sharp']);
  assert.equal(r.nRoh, 4, 'nRoh zaehlt jeden Play einmal');
  assert.equal(r.nAlt, 2, 'nAlt zaehlt die Plays aus der alten Engine');
  assert.equal(r.n, 2 + 2 * LEG, `gewichtet: 2 volle + 2 halbe = ${2 + 2 * LEG}`);
  assert.ok(r.n < r.nRoh, 'das Gewicht liegt unter der Roh-Zahl, solange Alt-Plays dabei sind');
});

test('_pwComboFor: money+sharp schlaegt sharp-allein — am synthetischen Track', () => {
  // Die Aussage, auf der die Kalibrierung ruht. Hier steht sie auf Daten, die sich nicht bewegen.
  const w = load(synth());
  const sharp = w._pwComboFor(['sharp']);
  const ms    = w._pwComboFor(['money','sharp']);
  assert.ok(ms.roi > sharp.roi,
    `money+sharp muss besser sein (sharp ${(sharp.roi*100).toFixed(1)}%, ms ${(ms.roi*100).toFixed(1)}%)`);
});

test('_pwTermMuted mutet historisch -EV Mix (sharp-allein), nicht money+sharp', () => {
  const w = load(synth());
  const mutedSharp = w._pwTermMuted({ conv:6, signals:['sharp'] });
  assert.equal(mutedSharp.m, true, 'sharp-allein muss gemutet werden');
  assert.match(mutedSharp.reason, /Mix .*ROI/);
  const okMs = w._pwTermMuted({ conv:7, signals:['money','sharp'] });
  assert.equal(okMs.m, false, 'money+sharp (real +EV) darf NICHT ueber den Combo-Mute rausfliegen');
});

test('Ohne Track-Daten kein Combo-Effekt (graceful)', () => {
  const w = load(null);
  assert.equal(w._pwComboFor(['sharp']), null);
  assert.equal(w._pwTermMuted({ conv:6, signals:['sharp'] }).m, false, 'ohne Daten kein Combo-Mute (conv6)');
});

// 21.08.2026 (Lucas): kontinuierliche/symmetrische Variante — conv sanft in BEIDE Richtungen.
test('_pwCalibConv: sharp-allein wird abgewertet, money+sharp aufgewertet', () => {
  const w = load(synth());
  const sharp = w._pwCalibConv(['sharp'], 6);
  const ms    = w._pwCalibConv(['money','sharp'], 6);
  assert.ok(sharp.conv <= 6, `sharp-allein sollte nicht hochgehen, war ${sharp.conv}`);
  assert.ok(ms.conv >= 6, `money+sharp sollte nicht runtergehen, war ${ms.conv}`);
  assert.ok(ms.conv > sharp.conv, 'money+sharp muss hoehere Konviktion bekommen als sharp-allein');
  if (sharp.conv < 6) { assert.match(sharp.reason, /📉/); assert.equal(sharp.tag, 'calib-'); }
  if (ms.conv > 6)    { assert.match(ms.reason, /📈/);    assert.equal(ms.tag, 'calib+'); }
});

test('_pwCalibConv: bleibt in [1..10] und ist bei duenner Stichprobe zahm', () => {
  const w = load(synth());
  for (const c of [1,5,10]) {
    const r = w._pwCalibConv(['sharp'], c);
    assert.ok(r.conv >= 1 && r.conv <= 10);
  }
  // unbekannter/duenner Mix → keine Aenderung
  const thin = w._pwCalibConv(['pinn'], 7);   // pinn-allein kommt im synthetischen Track nicht vor
  assert.equal(thin.conv, 7);
  assert.equal(thin.reason, null);
});

test('_pwCalibConv: ohne Track-Daten unveraendert', () => {
  const w = load(null);
  const r = w._pwCalibConv(['sharp'], 6);
  assert.equal(r.conv, 6);
  assert.equal(r.reason, null);
});
