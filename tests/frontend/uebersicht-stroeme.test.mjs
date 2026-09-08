// tests/frontend/uebersicht-stroeme.test.mjs — Ebene 1 als Leistungstafel (08.09.2026)
//
// Lucas: „ich kapier es einfach nicht — was wird da besonders freigegeben? … mein Ansatz wäre:
// ich seh dort die Schubladen die Sinn machen, mit etwas Stats — ROI, P/L, CLV. Und dann weiß
// ich für mich auch was ich besser folgen kann: eher Poly, eher Betfair, eher Cards."
//
// Die alte Frage („darf ich blind spielen?") wurde seit Wochen jeden Tag mit „nein" beantwortet.
// Sie bleibt — als Satz weiter unten. Zuerst steht jetzt seine Frage.
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);

function load() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  return w;
}

function schublade(over) {
  return Object.assign({ schublade: 'Liga · ABWÄGEN', strom: 'cards', art: 'verdict',
    n: 91, status: 'geprueft', roi: 0.152, roiLb: 0.008, pl: 13.8, clv: -1.52, clvLb: -2.0,
    fehltN: 0 }, over || {});
}

const FG = (over) => Object.assign({
  regeln: { minN: 30 },
  zusammenfassung: { schubladen: 3, freigegeben: 0, kandidaten: 0, ruhend: 0 },
  freigegeben: [], kandidaten: [],
  stroeme: [
    { strom: 'cards', zerlegung: 'nach Verdikt', gruppen: 4, n: 156, pl: 14.9, roi: 0.0954, clv: -2.01, belegte: 1 },
    { strom: 'betfair', zerlegung: 'nach Markt', gruppen: 7, n: 16656, pl: -26.1, roi: -0.0016, clv: null, belegte: 0 },
    { strom: 'poly', zerlegung: 'nach Conviction', gruppen: 5, n: 234, pl: -17.0, roi: -0.0726, clv: -1.28, belegte: 1 },
  ],
  alle: [schublade()],
}, over || {});

function ebene1(w, f) {
  w._mdState.data = { freigabe: f };
  w._renderMainDash();
  return w.document.querySelectorAll('section.md-sp .md-eb')[0].innerHTML;
}

test('die drei Ströme stehen mit ROI, P/L, Plays und CLV nebeneinander', () => {
  const html = ebene1(load(), FG());
  ['Cards', 'Betfair', 'Polymarket'].forEach((s) => assert.match(html, new RegExp(s), s + ' fehlt'));
  assert.match(html, /\+9\.5%/, 'Cards-ROI fehlt');
  assert.match(html, /\+14\.9/, 'Cards-P\/L fehlt');
  assert.match(html, /-2\.0pp/, 'Cards-CLV fehlt');
  assert.match(html, /16\.656/, 'die Betfair-Stichprobe fehlt');
});

test('jede Strom-Kachel nennt ihre Zerlegung — sonst liest man sie als „alles von Poly"', () => {
  // Die Schubladen eines Stroms überlappen sich; summiert wird über EINE disjunkte Zerlegung.
  const html = ebene1(load(), FG());
  assert.match(html, /nach Verdikt/);
  assert.match(html, /nach Conviction/);
  assert.match(html, /nach Markt/);
  assert.match(html, /überschneidungsfreie Zerlegung/);
});

test('der Badge sagt, wer vorn liegt — nicht „nichts freigegeben"', () => {
  const html = ebene1(load(), FG());
  assert.match(html, /Cards vorn/);
  assert.doesNotMatch(html.split('md-eb-s')[0], /nichts freigegeben/);
});

test('ist etwas freigegeben, sagt der Badge das — die strenge Aussage schlägt die Rangliste', () => {
  const f = FG({ freigegeben: [schublade({ status: 'freigegeben' })] });
  const html = ebene1(load(), f);
  assert.match(html, /1 freigegeben/);
});

test('die stärksten Schubladen stehen nach Untergrenze, nicht nach Punktschätzer', () => {
  const f = FG({ alle: [
    schublade({ schublade: 'Wenig belegt', roi: 0.36, roiLb: -0.001, pl: 11.9, n: 33 }),
    schublade({ schublade: 'Gut belegt', roi: 0.152, roiLb: 0.008, pl: 13.8, n: 91 }),
  ] });
  const html = ebene1(load(), f);
  // Nur die Bestenliste betrachten: die Namen tauchen auch im Begründungssatz darüber auf,
  // und ein indexOf über das ganze Markup würde dort hängenbleiben statt die Reihenfolge zu prüfen.
  const liste = html.split('stärksten Schubladen')[1].split('md-kl-det')[0];
  assert.ok(liste.indexOf('Gut belegt') < liste.indexOf('Wenig belegt'),
    'die höhere Untergrenze gehört nach oben, auch wenn der rohe ROI kleiner ist');
  assert.match(html, /Rendite-<b>Untergrenze<\/b>/);
});

test('jede Schubladen-Zeile trägt ROI mit UG, P/L und CLV', () => {
  const html = ebene1(load(), FG());
  assert.match(html, /ROI \+15\.2%/);
  assert.match(html, /UG \+0\.8%/);
  assert.match(html, /P\/L \+13\.8/);
  assert.match(html, /CLV -1\.5pp/);
});

test('ruhende Schubladen stehen nicht in der Bestenliste', () => {
  const f = FG({ alle: [schublade({ schublade: 'WM · ABWÄGEN', status: 'ruht', roiLb: 0.5 })] });
  const html = ebene1(load(), f);
  // Das Register unten zeigt weiterhin ALLE Schubladen — nur die Bestenliste nicht.
  const oben = html.split('md-kl-det')[0];
  assert.doesNotMatch(oben.split('stärksten Schubladen')[1] || '', /WM · ABWÄGEN/,
    'eine Schublade, die nichts mehr liefert, gehört nicht in „die stärksten"');
});

test('ohne Ströme im Artefakt wird keine Tafel erfunden', () => {
  const html = ebene1(load(), FG({ stroeme: [] }));
  assert.doesNotMatch(html, /überschneidungsfreie Zerlegung/);
  assert.match(html, /nichts freigegeben/, 'dann fällt der Badge auf die alte Aussage zurück');
});

test('die Frage der Ebene ist Lucas’ Frage, die strenge steht darunter', () => {
  const html = ebene1(load(), FG());
  assert.match(html, /Wem kann ich am ehesten folgen\?/);
  assert.match(html, /blind<\/b> folgen/);
});

// ── 08.09.2026, zweite Runde ────────────────────────────────────────────────────────────
// Lucas, drei Fragen in einer Nachricht:
//   „kann man bei Betfair anzeigen z.B. die Public-Push? die sind relativ solide"
//   „geht aus dem Tracking eventuell auch anzeigen welche Ligen gut performen?"
//   „bei Poly wäre gut wenn wir den Public-Kandidaten auch anzeigen … nicht über alle Poly"
//   „bzw. wäre es eventuell auch gut wenn man anzeigt z.B. top 10 Poly Wallets"

test('die Strom-Kachel nennt ihre stärkste BELEGTE Schublade — nicht nur den Strom-Schnitt', () => {
  // Der Kern von Lucas' Einwand: „Polymarket −7,3 %" ist wahr und nutzlos, solange darin eine
  // Schublade mit +20,8 % und einer Untergrenze über null steckt.
  const f = FG({
    alle: [
      schublade({ schublade: 'Public-Kandidaten', strom: 'poly', art: 'gate',
        n: 35, roi: 0.2079, roiLb: 0.023, pl: 7.3 }),
      schublade({ schublade: 'Conviction 5', strom: 'poly', art: 'conviction',
        n: 125, roi: -0.121, roiLb: -0.31, pl: -15.1 }),
    ],
  });
  const html = ebene1(load(), f);
  const kachel = html.split('Polymarket')[1].split('</div></div>')[0];
  assert.match(kachel, /Public-Kandidaten/,
    'die stärkste belegte Schublade des Stroms muss auf seiner Kachel stehen');
  assert.doesNotMatch(kachel, /Conviction 5/,
    'die schwächere Schublade gehört nicht auf die Kachel');
});

test('ohne belegte Schublade sagt die Kachel das — statt die beste UNbelegte zu zeigen', () => {
  // Gegenbeweis gegen die naheliegende Abkürzung „nimm einfach die mit dem höchsten ROI".
  const f = FG({
    alle: [schublade({ schublade: 'Conviction 8', strom: 'poly', art: 'conviction',
      n: 45, roi: 0.77, roiLb: -0.12, pl: 34.6 })],
  });
  const kachel = ebene1(load(), f).split('Polymarket')[1].split('</div></div>')[0];
  assert.match(kachel, /keine belegte Schublade/);
  assert.doesNotMatch(kachel, /Conviction 8/,
    'ein ROI von +77 % ohne Untergrenze über null ist kein Beleg und darf nicht als einer stehen');
});

test('unter der Mindestzahl zählt eine Schublade nicht als Beleg für ihren Strom', () => {
  const f = FG({
    alle: [schublade({ schublade: 'Winzling', strom: 'poly', art: 'conviction',
      n: 4, roi: 0.77, roiLb: 0.4, pl: 3.1 })],
  });
  const kachel = ebene1(load(), f).split('Polymarket')[1].split('</div></div>')[0];
  assert.match(kachel, /keine belegte Schublade/,
    'n=4 mit „Untergrenze +40 %" ist ein Artefakt, kein Beleg');
});

const LIGEN = [
  { liga: 'Ukrainian Premier League', n: 80, wins: 40, hit: 0.5, hitLb: 0.4,
    roi: 0.379, roiLb: 0.135, pl: 30.4, clv: 0.0, belegt: true },
  { liga: 'Bolivian Cup', n: 53, wins: 26, hit: 0.49, hitLb: 0.38,
    roi: 0.375, roiLb: 0.113, pl: 19.9, clv: 0.27, belegt: true },
  { liga: 'Slovakian Cup', n: 35, wins: 9, hit: 0.257, hitLb: 0.16,
    roi: -0.499, roiLb: -0.702, pl: -17.4, clv: null, belegt: false },
];

test('die Liga-Tafel zeigt beide Enden und sagt, dass sie eine ANDERE Zerlegung ist', () => {
  const html = ebene1(load(), FG({ ligen: LIGEN }));
  assert.match(html, /Ukrainian Premier League/);
  assert.match(html, /Slovakian Cup/, 'das teure Ende gehört dazu — sonst liest sich die Tafel wie eine Empfehlungsliste');
  assert.match(html, /2 belegt/);
  assert.match(html, /andere<\/b> Zerlegung|<b>andere<\/b>/,
    'ohne diesen Satz addiert man Liga- und Markt-Tafel und erfindet 16.657 Plays doppelt');
});

test('„belegt" heißt Untergrenze über null — nicht „ROI positiv"', () => {
  const html = ebene1(load(), FG({
    ligen: [{ liga: 'Schön aussehend', n: 40, wins: 20, hit: 0.5, hitLb: 0.36,
      roi: 0.42, roiLb: -0.02, pl: 16.8, clv: null, belegt: false }],
  }));
  assert.match(html, /0 belegt/,
    '+42 % ROI mit einer Untergrenze von −2 % ist kein Beleg');
});

test('ohne Liga-Daten erscheint die Tafel gar nicht — kein leerer Rahmen', () => {
  const html = ebene1(load(), FG());
  assert.doesNotMatch(html, /Welche Ligen tragen/);
});

const WALLETS = [
  { wallet: '0xb8e32d5711223344556677889900aabbccddeeff', kurz: '0xb8e3…eeff',
    n: 50, wins: 40, hit: 0.8, hitLb: 0.693, clv: 0.62, usd: 598066, pnl: 121799.45,
    grad: 1, sportarten: ['Tennis'] },
  { wallet: '0x04641b57f332c15ecaa497799c55026d521967da', kurz: '0x0464…67da',
    n: 8, wins: 8, hit: 1.0, hitLb: 0.747, clv: 6.3, usd: 15044, pnl: 1386.3,
    grad: 1, sportarten: ['Tennis'] },
];

test('die Wallet-Tafel steht mit n, Treffer-Untergrenze und CLV da', () => {
  const html = ebene1(load(), FG({ wallets: WALLETS }));
  assert.match(html, /0xb8e3…eeff/);
  assert.match(html, /n=50/);
  assert.match(html, /UG 69%/, 'die Untergrenze der Trefferquote fehlt');
  assert.match(html, /Tennis/);
});

test('die Lebensbilanz einer Wallet steht ausdrücklich NICHT als Rang', () => {
  // $121.799 gegen $1.386 — wer danach sortiert, sortiert nach Wahlen und Krypto.
  const html = ebene1(load(), FG({ wallets: WALLETS }));
  assert.match(html, /Wahlen und Krypto/);
  assert.doesNotMatch(html, /121\.799|121799/,
    'die Lebensbilanz gehört nicht als Zahl in die Zeile — sie misst etwas anderes');
});
