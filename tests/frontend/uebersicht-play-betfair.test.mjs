// tests/frontend/uebersicht-play-betfair.test.mjs — 30.08.2026
//
// Lucas: „heute spielenswert ist mehr polymarket getrieben richtig?" — ja: Geld · Wallet-Bilanz ·
// Zufluss lesen alle DIESELBE Quelle. Drei Blickwinkel auf Polymarket sahen in der Zeile aus wie
// drei Belege. Die einzige fremde Stimme im Scorer ist Betfair (und die einzige Untergruppe im
// Papier-Depot mit positivem ROI: n=57, +6,5%) — sie stand nirgends.
//
// Geprüft wird deshalb: die Betfair-Zelle erscheint, wenn es etwas zu vergleichen gibt; sie
// verschweigt kein Gegensignal; und sie erfindet nichts, wo es gar keinen Betfair-Markt gibt.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);

const play = (extra = {}) => ({
  key: 'nba-lal-bos-2026-07-25', match: 'Lakers vs Celtics', side: 'Lakers', verdict: 'BET',
  conv: 8, reasons: ['großes Geld'], htk: 3, league: 'NBA', moneyPct: 0.68, vol: 180000,
  sharp: { n: 40, wins: 26, hit: 0.65, count: 2 }, ...extra,
});

function render(p) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  w._pwSportIcon = () => '🏀';
  w._pwEnsurePlaysData = (cb) => cb && cb();
  w._pwTopPlays = () => [p];
  w._pwPublicTopPlays = () => [];
  w._pwOverNormTop = () => [];
  w._mdState.data = { liga: null, mls: null, ligaStreaks: null, mlsStreaks: null,
    betfair: { matches: [] }, whales: null };
  w._renderMainDash();
  const h = w.document.getElementById('mainDashPanel').innerHTML;
  const von = h.indexOf('Heute spielenswert');
  return h.slice(von, von + 3000);
}

test('ohne Betfair-Markt bleibt die Zeile bei den drei Poly-Zellen', () => {
  // Für Tennis/Esports gibt es keinen Betfair-Gegenpart. Eine leere Zelle wäre kein fehlendes
  // Signal, sondern eine fehlende Fläche — also gar keine Zelle.
  const h = render(play());
  assert.match(h, /Wallet-Bilanz/, 'die bekannten Zellen stehen');
  assert.doesNotMatch(h, />Betfair</, 'keine erfundene vierte Zelle');
});

test('liegt Betfair-Geld auf derselben Seite, steht es als eigene Stimme da', () => {
  const h = render(play({ bf: { agree: true, pct: 71, eur: 128000, name: 'Lakers' } }));
  assert.match(h, />Betfair</);
  assert.match(h, />71%</);
  assert.match(h, /bestätigt · €128K/);
});

test('liegt Betfair-Geld DAGEGEN, wird es nicht verschwiegen', () => {
  // Der Scorer rechnet r.bf.agree ohnehin — verschwiegen hat es nur die Anzeige.
  const h = render(play({ bf: { agree: false, pct: 63, eur: 90000, name: 'Celtics' } }));
  assert.match(h, />Betfair</);
  assert.match(h, /dagegen — Geld auf/);
  assert.match(h, /Celtics/);
});

test('im Gegenfall bleibt der Balken leer — Länge heißt Rückhalt', () => {
  // 64% gehören dort der ANDEREN Seite. Ein gefüllter Balken haette Rueckhalt behauptet.
  const con = render(play({ bf: { agree: false, pct: 64, eur: 96000, name: 'Celtics' } }));
  const zelle = con.slice(con.indexOf('>Betfair<'));
  assert.match(zelle.slice(0, 400), /width:0%/, 'keine Fuellung gegen uns');
  const pro = render(play({ bf: { agree: true, pct: 64, eur: 96000, name: 'Lakers' } }));
  const z2 = pro.slice(pro.indexOf('>Betfair<'));
  assert.match(z2.slice(0, 400), /width:64%/, 'mit uns: die Fuellung ist der Anteil');
});

test('die Richtung hängt nicht an der Farbe allein', () => {
  // Gold gegen Orange trennt unter Tritanopie kaum — das Wort trägt die Aussage.
  const pro = render(play({ bf: { agree: true, pct: 71, eur: 1000, name: 'Lakers' } }));
  const con = render(play({ bf: { agree: false, pct: 71, eur: 1000, name: 'Celtics' } }));
  assert.match(pro, /bestätigt/);
  assert.match(con, /dagegen/);
});

test('ohne Prozentwert wird keine Zelle gebaut — fail-closed', () => {
  const h = render(play({ bf: { agree: true, eur: 5000, name: 'Lakers' } }));
  assert.doesNotMatch(h, />Betfair</);
});
