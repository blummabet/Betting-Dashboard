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

// Struktur-Check auf ECHTEN Daten. BEWUSST ohne feste ROI-Schwelle: die Datei wächst mit jedem
// Scan, jede absolute Zahl wäre wieder eine Zeitbombe. Geprüft wird die AUSSAGE der Kalibrierung
// — money+sharp schlägt sharp-allein — und dass die Stichprobe überhaupt trägt.
test('_pwComboFor auf echten Daten: money+sharp schlaegt sharp-allein', () => {
  const w = load(REAL);
  const sharp = w._pwComboFor(['sharp']);
  const ms    = w._pwComboFor(['money','sharp']);
  assert.ok(sharp && sharp.n >= 50, 'sharp-Combo zu duenn');
  assert.ok(ms && ms.n >= 50, 'money+sharp-Combo zu duenn');
  assert.ok(typeof sharp.roi === 'number' && typeof ms.roi === 'number', 'ROIs sind Zahlen');
  assert.ok(ms.roi > sharp.roi,
    `money+sharp muss besser als sharp-allein sein (sharp ${(sharp.roi*100).toFixed(1)}%, ms ${(ms.roi*100).toFixed(1)}%)`);
  // Verdrahtung gegen echte Daten: darf nicht werfen, egal wo die Zahlen gerade stehen.
  assert.ok(typeof w._pwTermMuted({ conv:6, signals:['sharp'] }).m === 'boolean');
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
