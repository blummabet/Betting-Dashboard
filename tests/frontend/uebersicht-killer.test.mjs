// tests/frontend/uebersicht-killer.test.mjs — 29.08.2026
//
// Lucas: „das könnte man irgendwie noch spezielle bauen oder? Also dort kommst halt nur rein
// wenn / Pini move da / Betfair geld oben und quoten mitziehen / Poly geld oben."
//
// Entschieden hat er sich für ZWEI Stufen sichtbar. Die Auswahl trifft killer.py; hier wird
// nur geprüft, dass die Übersicht sie ehrlich zeigt — vor allem die zwei Stellen, an denen
// eine solche Sektion sonst lügt:
//   · sie darf nicht „spielbar" behaupten, solange die ROI-Untergrenze unter null liegt,
//   · Stufe 2 darf nicht aussehen wie Stufe 1 (fehlendes Poly muss sichtbar fehlen).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const MOD = new URL('../../main-dashboard.js', import.meta.url);

function render(killer, freigabe) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainDashPanel"></div></body>',
    { url: 'https://x.com/', runScripts: 'outside-only' });
  const w = dom.window;
  w.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(null) });
  w.eval(readFileSync(MOD, 'utf8'));
  w._mdState.data = {
    liga: null, mls: null, ligaStreaks: null, mlsStreaks: null, betfair: null, whales: null,
    killer, freigabe,
  };
  w._renderMainDash();
  // 01.09.2026: die drei Fragen stehen jetzt als EBENEN in EINER Sektion („Was kann ich
  // spielen?"). Zugeschnitten wird deshalb per DOM auf Ebene 2 — nicht per Offsets und nicht
  // per Ueberschrift-Text: beides ist beim naechsten Umbau wieder falsch.
  const n = w.document.querySelector('.md-eb-n.e2');
  assert.ok(n, 'Ebene 2 (Konjunktion) wird gar nicht gerendert');
  return n.closest('.md-eb').outerHTML;
}

const ko = (h = 2) => new Date(Date.now() + h * 3600e3).toISOString();
const jetzt = new Date().toISOString();
const zeile = (home, extra = {}) => ({
  matchId: 'm' + home, home, away: 'Gegner', league: 'English Premier League', kickoff: ko(),
  markt: 'Match Odds', seite: 'home', name: home, odd: 1.8, haltePreis: 1.8, anteilPct: 74,
  stufe: 2, verstaerker: [], rang: 55, track: null, streak: null, poly: null,
  pinnMovePP: null, wertVsPinn: null,
  gehaltenSeit: jetzt, zuletztAktiv: jetzt, aktiv: true, ...extra,
});

const REG = (status, extra = {}) => ({
  alle: [{ schublade: 'Konjunktion · Betfair-Kern', strom: 'betfair', n: 70, status,
           roi: 0.117, roiLb: -0.058, clv: 3.51, clvLb: 2.72, ...extra }],
});

// 01.09.2026 (Lucas: „das wirkt jetzt schon sehr oft quasi redundant, oder?"). Bis dahin sprach
// DIESE Ebene das Urteil des Freigabe-Registers mit aus — dieselbe Zahl aus derselben Datei, die
// Ebene 1 direkt darüber schon nennt. Das war die einzige echte Doppelung der Übersicht.
// Der Vertrag ist jetzt umgekehrt: Ebene 2 darf über Freigabe GAR NICHTS sagen.
test('Ebene 2 spricht kein Freigabe-Urteil aus — das gehört Ebene 1', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal')] }, REG('geprueft'));
  assert.doesNotMatch(html, /freigegeben/i, 'kein Freigabe-Wort auf dieser Ebene');
  assert.doesNotMatch(html, /Tor n70/, 'die Register-Zahl gehört nicht in diesen Badge');
  assert.match(html, /Ebene 1/, 'stattdessen wird nach oben verwiesen');
});

test('auch eine freigegebene Schublade ändert an Ebene 2 nichts', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal')] },
    REG('freigegeben', { roiLb: 0.04 }));
  assert.doesNotMatch(html, /freigegeben · n70/, 'sonst stünde dasselbe Urteil zweimal auf der Seite');
  assert.match(html, /eigenes Buch/, 'diese Ebene spricht nur über ihr eigenes Buch');
});

test('ohne Freigabe-Datei wird nichts behauptet', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal')] }, null);
  assert.match(html, /eigenes Buch 0\/20/, 'ohne Register bleibt der eigene Stand die Aussage');
});

// 30.08.2026 (Lucas: „glaub da ist noch mehr drin"): die Chip-Kette ist einem Deckungs-Profil
// mit FESTEN Plätzen je Geldstrom gewichen — man zählt leuchtende Blöcke, statt Text zu lesen.
// Diese Tests prüfen jetzt die Eigenschaft (welcher Strom trägt?), nicht mehr den Chip-Wortlaut.
test('die drei Betfair-Belege sind als volle Marken sichtbar', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal')] }, REG('geprueft'));
  const bf = html.slice(html.indexOf('md-kl-str'), html.indexOf('>BF '));
  assert.equal((bf.match(/class="md-kl-pip"/g) || []).length, 3, 'Anteil · Zufluss · Richtung');
  assert.doesNotMatch(bf, /md-kl-pip leer/, 'das Tor ist bei jeder gezeigten Zeile voll');
  assert.match(html, /Geldanteil 74% · frischer Zufluss · Quote zieht mit/, 'im Titel nachlesbar');
});

test('der Zähler sagt, wie viele Ströme tragen', () => {
  const nackt = render({ stufe1: [], stufe2: [zeile('Arsenal')] }, REG('geprueft'));
  assert.match(nackt, /class="md-kl-cnt"[^>]*>3<i>\/7<\/i>/, 'nur das Betfair-Tor');
  const voll = render({ stufe1: [], stufe2: [zeile('Arsenal', {
    poly: { anteilPct: 71 },
    verstaerker: [{ art: 'pinn', text: 'Pinnacle stimmt zu' },
                  { art: 'pinnMove', text: 'Pinnacle zieht mit +2.0pp' },
                  { art: 'streak', text: 'Ungeschlagen ×9' }] })] }, REG('geprueft'));
  assert.match(voll, /class="md-kl-cnt"[^>]*>7<i>\/7<\/i>/);
});

test('der Geldanteil steht als Zahl am Betfair-Block, nicht als Balken', () => {
  // Erst stand hier ein Meter. Über die echten Zeilen lag der Anteil bei 74–84%: vier fast
  // identische Balken, die Schwellenmarke kaum sichtbar. Ein Verhältnis, das nie nennenswert
  // schwankt, ist als Balken Rauschen — dataviz: bei genau EINEM Wert schlägt die
  // Direktbeschriftung die Marke.
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal')],
    regeln: { minAnteil: 0.65, text: 'x' } }, REG('geprueft'));
  assert.doesNotMatch(html, /md-kl-mtr/, 'kein Meter mehr');
  const bf = html.slice(html.indexOf('md-kl-deck'));
  assert.match(bf.slice(0, bf.indexOf('PIN')), /BF 74%/, 'die Zahl hängt am BF-Block');
});

test('ein fehlender Strom bleibt als LEERER Platz sichtbar', () => {
  // Der Kern der Idee: feste Plätze. Ein fehlender Poly-Markt verschwindet nicht, er bleibt
  // als unbelegte Marke stehen — sonst sähe Stufe 2 aus wie Stufe 1, nur kürzer.
  const voll = zeile('Chelsea', { stufe: 1, poly: { anteilPct: 71, usd: 40000, odd: 1.75 },
    verstaerker: [{ art: 'poly', text: 'Poly 71%' }, { art: 'pinn', text: 'Pinnacle stimmt zu' }] });
  const html = render({ stufe1: [voll], stufe2: [zeile('Arsenal')] }, REG('geprueft'));
  assert.match(html, /Voll gedeckt/);
  assert.match(html, /Betfair-Kern/);
  assert.match(html, /Poly-Geld 71% auf derselben Seite/);
  assert.match(html, /kein Poly-Markt/, 'die Lücke wird benannt, nicht weggelassen');
  assert.match(html, /md-kl-pip leer/, 'und sie bleibt als unbelegte Marke stehen');
});

test('kein Strom wird allein durch Farbe unterschieden', () => {
  // Gold↔Grün liegen unter Tritanopie bei ΔE 4,0 — jeder Block MUSS sein Kürzel tragen.
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal')] }, REG('geprueft'));
  // BF trägt zusätzlich seinen Anteil, die anderen nur das Kürzel — beide Formen sind Text.
  ['BF', 'PIN', 'POLY', 'FORM'].forEach(k => assert.match(html, new RegExp('>' + k + '[< ]')));
});

test('leer heißt leer — keine erfundene Zeile, aber die Regel bleibt lesbar', () => {
  const html = render({ stufe1: [], stufe2: [],
    regeln: { text: 'Geldanteil ≥65% UND frischer Zufluss ≥€2000 UND Quote zieht mit.' } },
    REG('geprueft'));
  assert.match(html, /Gerade deckt sich nichts/);
  assert.match(html, /≥65%/);
});

// 30.08.2026 (Lucas: „das wechselt auch ohne dass ich die Seite aktualisiere"): der Treffer
// wird bis zum Anpfiff gehalten. Damit das nicht wie ein eingefrorener Fehler aussieht, muss
// die Zeile zeigen, seit wann sie steht und ob die Bedingungen gerade noch anliegen.
test('eine laufende Zeile ist von einer gehaltenen unterscheidbar', () => {
  const alt = new Date(Date.now() - 90 * 60000).toISOString();
  const html = render({ stufe1: [], stufe2: [
    zeile('Arsenal'),
    zeile('Chelsea', { aktiv: false, zuletztAktiv: alt, gehaltenSeit: alt }),
  ] }, REG('geprueft'));
  assert.match(html, /md-kl-live/);
  assert.match(html, /md-kl-halt/);
  assert.match(html, /gehalten seit/);
  assert.match(html, /zuletzt /);
});

test('der Haltepreis bleibt stehen, die weggelaufene Quote steht daneben', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal', { haltePreis: 1.80, odd: 2.40 })] },
    REG('geprueft'));
  assert.match(html, /@1\.80/, 'gezeigt wurde der Preis beim Treffer');
  assert.match(html, /jetzt 2\.40/, 'dass die Quote weggelaufen ist, darf nicht verschwiegen werden');
});

test('steht die Quote noch, wird kein Zweitpreis danebengeklebt', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Arsenal', { haltePreis: 1.80, odd: 1.81 })] },
    REG('geprueft'));
  assert.doesNotMatch(html, /jetzt 1\.81/);
});

// 30.08.2026 (Lucas-Checkup, zweite Runde): die Sektion zeigte „FC Utrecht v PSV ⏱ 1m", während
// die Betfair-Kachel daneben schon „● LIVE" schrieb. killer.py entfernt angepfiffene Zeilen
// korrekt — aber killer.json ist bis zu 15 Minuten alt, und dazwischen pfeift ein Spiel an.
// Ein Feed-Zeitstempel ist kein Ereignis-Zeitstempel.
test('ein bereits angepfiffenes Spiel verschwindet, auch wenn der Feed es noch führt', () => {
  const html = render({ stufe1: [], stufe2: [
    zeile('Laeuft', { kickoff: ko(-0.2) }),
    zeile('Kommt', { kickoff: ko(3) }),
  ] }, REG('geprueft'));
  assert.match(html, /Kommt/);
  assert.doesNotMatch(html, /Laeuft/);
});

// „Lecce v Roma ⏱ 30h 16m" stand in einer Sektion, die beantworten soll, was JETZT spielbar ist.
// Der gehaltene Preis von heute Mittag gilt morgen Abend nicht mehr.
test('ausserhalb des 12-Stunden-Fensters wird nichts empfohlen', () => {
  const html = render({ stufe1: [], stufe2: [
    zeile('Morgen', { kickoff: ko(30) }),
    zeile('Bald', { kickoff: ko(5) }),
  ] }, REG('geprueft'));
  assert.match(html, /Bald/);
  assert.doesNotMatch(html, /Morgen/);
});

test('faellt dadurch alles weg, sagt die Sektion das ehrlich', () => {
  const html = render({ stufe1: [], stufe2: [zeile('Morgen', { kickoff: ko(30) })],
    regeln: { text: 'Geldanteil ≥65% UND frischer Zufluss ≥€2000 UND Quote zieht mit.' } },
    REG('geprueft'));
  assert.match(html, /Gerade deckt sich nichts/);
});

// 30.08.2026 (Lucas: „sollten wir das nicht mittracken, damit ich seh wie gut es performt?").
// Das Buch lief seit gestern mit, war aber nirgends sichtbar — der Badge zeigte die Zahl der
// SCHLUSS-Definition aus dem Betfair-Track (n=70), also eine verwandte, aber ANDERE Menge als
// das, was in dieser Sektion wirklich stand.
const bilanz = (o = {}) => ({
  gesamt: { n: 0, gewonnen: 0, verloren: 0, einheiten: 0, roi: null },
  jeStufe: { 1: { n: 0, gewonnen: 0, verloren: 0, einheiten: 0, roi: null },
             2: { n: 0, gewonnen: 0, verloren: 0, einheiten: 0, roi: null } },
  offen: 0, zeilen: [], ...o,
});
const KL = { stufe1: [], stufe2: [zeile('Arsenal')] };

// 01.09.2026: früher borgte sich dieser Badge bei dünnem eigenem Buch die Zahl des Registers
// („Tor n70"). Seit die Ebene darüber genau das sagt, borgt er nichts mehr — er zeigt den
// eigenen Fortschritt und sonst nichts.
test('dünnes eigenes Buch borgt keine fremde Zahl mehr', () => {
  const html = render({ ...KL, bilanz: bilanz({ offen: 4 }) }, REG('geprueft'));
  assert.match(html, /eigenes Buch 0\/20 · 4 offen/);
  assert.doesNotMatch(html, /Tor n70/, 'die fremde Zahl steht eine Ebene höher');
});

test('ab genug eigenen Zeilen zählt die eigene Bilanz', () => {
  const g = { n: 24, gewonnen: 15, verloren: 9, einheiten: 4.8, roi: 0.2, roiLb: 0.03 };
  const html = render({ ...KL, bilanz: bilanz({ gesamt: g }) }, REG('geprueft'));
  assert.match(html, /eigene Bilanz · 15–9 · ROI \+20% \(UG \+3%\)/);
  assert.doesNotMatch(html, /Tor n70/, 'die eigene Zahl ersetzt die fremde');
});

// 30.08.2026: der Badge sprang auf GRÜN, sobald der ROI-Punktschätzer über null lag — bei n=32
// und einer Untergrenze von −20%. Zwei Zeilen tiefer sagte dieselbe Sektion „keine Freigabe".
// Grün darf nur werden, was denselben Richter besteht wie die Freigabe.
test('ein positiver ROI mit negativer Untergrenze wird NICHT grün', () => {
  const g = { n: 32, gewonnen: 19, verloren: 13, einheiten: 2.31, roi: 0.072, roiLb: -0.201 };
  const html = render({ ...KL, bilanz: bilanz({ gesamt: g }) }, REG('geprueft'));
  const badge = html.slice(html.indexOf('md-eb-st'), html.indexOf('md-eb-st') + 300);
  assert.match(badge, /👀/, 'beobachten, nicht spielen');
  assert.match(badge, /UG −?-?20%/, 'die Untergrenze steht dabei');
  assert.doesNotMatch(badge, /46,160,67/, 'kein grüner Hintergrund');
});

test('ohne Untergrenze bleibt der Badge gelb — fehlende Information ist keine Erlaubnis', () => {
  const g = { n: 40, gewonnen: 25, verloren: 15, einheiten: 9, roi: 0.225 };   // altes killer.json
  const html = render({ ...KL, bilanz: bilanz({ gesamt: g }) }, REG('geprueft'));
  const badge = html.slice(html.indexOf('md-eb-st'), html.indexOf('md-eb-st') + 300);
  assert.match(badge, /UG —/);
  assert.doesNotMatch(badge, /46,160,67/);
});

test('die Bilanz ist aufklappbar und listet, was gezeigt wurde', () => {
  const html = render({ ...KL, bilanz: bilanz({
    gesamt: { n: 2, gewonnen: 1, verloren: 1, einheiten: 0.52, roi: 0.26 },
    jeStufe: { 1: { n: 1, gewonnen: 1, verloren: 0, einheiten: 1.52, roi: 1.52 },
               2: { n: 1, gewonnen: 0, verloren: 1, einheiten: -1, roi: -1 } },
    zeilen: [{ name: 'PSV', liga: 'Eredivisie', stufe: 1, haltePreis: 2.52, schlussPreis: 2.4, win: true },
             { name: 'Heracles', liga: 'Eerste Divisie', stufe: 2, haltePreis: 1.62, schlussPreis: 1.62, win: false }],
  }) }, REG('geprueft'));
  assert.match(html, /2 abgerechnet · 1 gewonnen · 1 verloren/);
  assert.match(html, /\+0\.52 Einheiten/);
  assert.match(html, /Stufe 1: 1–0/);
  assert.match(html, /Stufe 2: 0–1/);
  assert.match(html, /PSV/);
  assert.match(html, /@2\.52/);
  assert.match(html, /→2\.40/, 'die Schlussquote gehoert daneben');
});

test('ohne abgerechnete Zeilen wird keine Bilanz erfunden', () => {
  const html = render({ ...KL, bilanz: bilanz({ offen: 3 }) }, REG('geprueft'));
  assert.match(html, /Noch nichts abgerechnet — 3 Zeilen/);
  assert.doesNotMatch(html, /Einheiten/);
});

test('auch eine leere Sektion zeigt ihre Bilanz', () => {
  // Sonst verschwindet der Leistungsnachweis genau dann, wenn gerade nichts ansteht.
  const html = render({ stufe1: [], stufe2: [], regeln: { text: 'x' },
    bilanz: bilanz({ gesamt: { n: 5, gewonnen: 3, verloren: 2, einheiten: 1.1, roi: 0.22 } }) },
    REG('geprueft'));
  assert.match(html, /Gerade deckt sich nichts/);
  assert.match(html, /5 abgerechnet · 3 gewonnen · 2 verloren/);
});
