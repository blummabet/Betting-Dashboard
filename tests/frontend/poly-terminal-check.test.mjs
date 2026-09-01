// tests/frontend/poly-terminal-check.test.mjs — 01.09.2026
//
// Lucas: „kannst mal im Poly Terminal checken, ob da alles passt". Vier Befunde, alle hier
// festgehalten, damit sie nicht zurückkommen:
//   1. Die Spalte hieß „CLV-Bucket" und zeigte den ROI. Bei Konv 7 (n=175) stehen ROI +1,3% und
//      CLV −0,2pp — sie widersprechen sich im VORZEICHEN, die Überschrift log also genau dort,
//      wo es zählt. `clvAvg` lag in agg.byConv vor und wurde nie gelesen.
//   2. „1 handelbare Plays jetzt".
//   3. Der Public-ROI stand als nackter Punktschätzer da — die letzte Stelle ohne Untergrenze.
//   4. „🔎 vielversprechende Wallet (noch nicht belegt)" im Singular bei Beleggrad 99,8% und
//      ZWEI verrechneten Wallets, von denen eine bewiesen war.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const SRC = readFileSync(new URL('../../poly-wallets.js', import.meta.url), 'utf8');
function laden(track) {
  const dom = new JSDOM('<!DOCTYPE html><body></body>', { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(SRC);
  if (track) w._pwCache = { shortlistTrack: track };
  return w;
}
const play = (pnl, stake = 10, pub = false) => ({ stake, pnl, public: pub, result: pnl > 0 ? 'win' : 'lose' });

test('die Spalte behauptet nicht mehr CLV zu sein, wenn sie ROI zeigt', () => {
  assert.doesNotMatch(SRC, /th\('CLV-Bucket'\)/, 'die Überschrift log über ihren Inhalt');
  assert.match(SRC, /th\('Stufen-Bilanz'\)/);
});

test('die Stufen-Zelle zeigt ROI UND CLV, beide benannt', () => {
  // clvAvg lag die ganze Zeit vor — jetzt steht es daneben, statt vom ROI verdeckt zu werden.
  const von = SRC.indexOf("? '<span style=\"font-family:ui-monospace,monospace;font-size:10.5px");
  assert.ok(von > 0, 'Stufen-Zelle nicht gefunden');
  const zelle = SRC.slice(von, von + 900);
  assert.match(zelle, /' ROI '/, 'der ROI wird als ROI benannt');
  assert.match(zelle, /b\.clvAvg/, 'und der CLV steht daneben');
});

test('Untergrenze: grün erst über null, gold bei positivem ROI ohne Beleg', () => {
  const w = laden({ settled: [] });
  assert.equal(w._pwSegUg(false), null, 'ohne Plays keine Untergrenze');
  assert.equal(w._pwUgTxt(null), '—');
  assert.equal(w._pwUgFarbe(null, 0.3), '#8b949e', 'unbekannt bleibt grau, nie grün');
  assert.equal(w._pwUgFarbe(0.04, 0.2), '#3fb950', 'UG über null → grün');
  assert.equal(w._pwUgFarbe(-0.07, 0.023), '#e3b341', 'ROI positiv, UG negativ → gold, nicht grün');
  assert.equal(w._pwUgFarbe(-0.09, -0.021), '#f85149');
});

test('die Untergrenze rechnet nur auf dem gewählten Segment', () => {
  const settled = [];
  for (let i = 0; i < 30; i++) settled.push(play(i % 2 ? 9 : -10, 10, true));   // public
  for (let i = 0; i < 30; i++) settled.push(play(-10, 10, false));              // nur Shortlist
  const w = laden({ settled });
  const pub = w._pwSegUg(true), alle = w._pwSegUg(false);
  assert.ok(pub > alle, 'das Public-Segment muss besser dastehen als die ganze Liste');
  assert.ok(alle < 0);
});

test('Einzahl bei einem Play', () => {
  assert.match(SRC, /handelbarer Play jetzt/);
  assert.match(SRC, /'handelbare Plays jetzt'/);
});

test('mehrere Wallets werden auch als mehrere benannt', () => {
  // _pwSharpInfoForKey summiert die Wallets EINER Seite (b.n += raw.n). Der Satz sagt das jetzt.
  assert.match(SRC, /_mehr=\(sh\.count\|\|1\)>1/);
  assert.match(SRC, /'🔥 scharfe Wallets'/, 'Plural existiert');
  assert.match(SRC, /Wallets, zusammen /, 'und die Summe wird als Summe ausgewiesen');
});

test('ein Beleggrad von 99% heißt nicht mehr „noch nicht belegt"', () => {
  // Im geprüften Fall war eine Wallet bewiesen (Wilson-UG 0,532), die zweite verfehlte die
  // Schwelle um 0,0005 — das Etikett „nicht belegt" war formal richtig und praktisch Unsinn.
  assert.match(SRC, /_gr>=0\.95 \?/, 'ab 95% gilt es als faktisch belegt');
  assert.match(SRC, /faktisch belegt/);
});
