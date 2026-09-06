// tests/frontend/cards.test.mjs — Render-Tests für die Cards (wm2026-renderer.js, IIFE).
// Nutzt den Test-Hook window.__wmCardTest. Prüft: gemeinsames Signal-Grid (inkl. neuer Liga-Signale)
// + dass die KO-Card genauso reich rendert wie eine normale Card (Pick + Signale + Form).
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const WM_RENDERER = new URL('../../wm2026-renderer.js', import.meta.url);

function loadCards() {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="intlCardsPanel"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const { window } = dom;
  window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  window.eval(readFileSync(WM_RENDERER, 'utf8'));
  return window;
}

// Lädt den Renderer mit #mainContent + gemocktem liga-data.json-Fetch → erlaubt den
// vollen initNationalCards-Durchlauf (kuratierte Liga-Ansicht testen).
function loadNational(ligaData) {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainContent"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const { window } = dom;
  window.fetch = (url) => Promise.resolve({
    ok: true,
    json: () => Promise.resolve(String(url).includes('liga-data.json') ? ligaData : {}),
  });
  window.eval(readFileSync(WM_RENDERER, 'utf8'));
  return window;
}

function _ligaFixture(home, away, md, daysAhead) {
  const d = new Date(Date.now() + daysAhead * 86400000).toISOString().slice(0, 10);
  return { home, away, matchday: md, date: d, time: '17:00', kickoff: d + 'T17:00:00Z', result: null };
}

test('Card-Test-Hook ist exportiert', () => {
  const w = loadCards();
  assert.ok(w.__wmCardTest, '__wmCardTest fehlt');
  assert.equal(typeof w.__wmCardTest.engineSignalGridHtml, 'function');
  assert.equal(typeof w.__wmCardTest.buildKoCard, 'function');
});

test('Signal-Grid rendert neue Liga-Signale mit Label + Begründung', () => {
  const t = loadCards().__wmCardTest;
  const html = t.engineSignalGridHtml({
    signalAdjustmentPP: 1.5,
    signals: [
      { name: 'league_pressure', score: 1.2, evidence: 'Titelrennen — beide brauchen Punkte' },
      { name: 'fixture_congestion', score: -0.8, evidence: 'Heim müde (3 Tage Pause)' },
      { name: 'topscorer_momentum', score: 0.6, evidence: 'Top-Torjäger in Form' },
    ],
  });
  assert.match(html, /Liga-Druck/);
  assert.match(html, /Erschöpfung/);
  assert.match(html, /Top-Torjäger/);
  assert.match(html, /Titelrennen/);          // Begründung sichtbar
  assert.match(html, /Engine-Signale/);
});

test('_streakRowHtml: Team + Markt + Länge + Continuation', () => {
  const t = loadCards().__wmCardTest;
  const h = t.streakRowHtml({ teamId: '50', team: 'City', leagueName: 'PL', type: 'bttsNo',
    market: 'Beide treffen — Nein', length: 4, continuation: { state: 'wackelt', label: 'x' } });
  assert.match(h, /City/);
  assert.match(h, /Beide treffen/);
  assert.match(h, /4 in Folge/);
  assert.match(h, /wackelt/);
});

test('Serien-Tab: initStreaks rendert + filtert nach Liga und Streak-Art', async () => {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="streaksPanel"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const streaks = { streaks: [
    { teamId: '42', team: 'Arsenal', league: 'ENG', leagueName: 'Premier League', type: 'over25',
      market: 'Über 2,5 Tore', length: 6, strong: true, continuation: { state: 'intakt', label: 'x' } },
    { teamId: '50', team: 'Real', league: 'ESP', leagueName: 'La Liga', type: 'cornersOver',
      market: 'Über 9,5 Ecken', length: 4, strong: false, continuation: { state: 'wackelt', label: 'y' } },
  ] };
  w.fetch = (url) => Promise.resolve({ ok: true, json: () => Promise.resolve(String(url).includes('liga_streaks') ? streaks : {}) });
  w.eval(readFileSync(WM_RENDERER, 'utf8'));
  await w.initStreaks('national');
  const panel = () => w.document.getElementById('streaksPanel').innerHTML;
  assert.match(panel(), /Arsenal/);
  assert.match(panel(), /Real/);
  assert.match(panel(), /Alle Ligen/);   // Liga-Filterleiste (2 Ligen)
  // Filter: nur Ecken → Real bleibt, Arsenal weg
  w.wmSetStreakType('ecken');
  assert.ok(/Real/.test(panel()) && !/Arsenal/.test(panel()), 'Typ-Filter Ecken');
  // Filter: nur ENG → Arsenal bleibt (Typ zurücksetzen)
  w.wmSetStreakType('all');
  w.wmSetStreakLeague('ENG');
  assert.ok(/Arsenal/.test(panel()) && !/Real/.test(panel()), 'Liga-Filter ENG');
});

test('_matchStreaksHtml: Serien der beiden Match-Teams in der Card', () => {
  const t = loadCards().__wmCardTest;
  t.setStreaksCache('wm', { streaks: [
    { teamId: 'ZAF', team: 'Südafrika', league: 'A', type: 'over25', market: 'Über 2,5 Tore', length: 5, continuation: { state: 'intakt', label: 'x' } },
    { teamId: 'XXX', team: 'Andere', league: 'A', type: 'bttsYes', market: 'BTTS', length: 4, continuation: { state: 'neutral' } },
  ] });
  const h = t.matchStreaksHtml('ZAF', 'CAN');
  assert.match(h, /Serien in diesem Spiel/);
  assert.match(h, /Südafrika/);
  assert.ok(!/Andere/.test(h), 'fremdes Team darf nicht erscheinen');
});

test('_streakRowHtml: Grundrate + nächstes Spiel + Gegner-Rate', () => {
  const t = loadCards().__wmCardTest;
  const h = t.streakRowHtml({ teamId: '42', team: 'Arsenal', leagueName: 'PL', type: 'over25',
    market: 'Über 2,5 Tore', length: 5, venue: 'H', ratePct: 72, continuation: { state: 'intakt', label: 'x' },
    next: { oppName: 'City', date: '2026-08-24', atHome: true, oppRatePct: 66 } });
  assert.match(h, /Heim/);                 // Venue-Label
  assert.match(h, /72%/);                  // Rate als %-Balken (ersetzt Flammen)
  assert.match(h, /Nächstes/);
  assert.match(h, /City/);
  assert.match(h, /66% Über/);             // komplementäre Gegner-Rate
  assert.match(h, /24\.08\./);
});

test('_streakRowHtml: Sequenz-Punkte (seqViz) werden gerendert', () => {
  const t = loadCards().__wmCardTest;
  const h = t.streakRowHtml({ teamId: '42', team: 'Arsenal', leagueName: 'PL', type: 'over25',
    market: 'Über 2,5 Tore', length: 4, ratePct: 70, continuation: { state: 'intakt' },
    seq: [true, true, true, true, false] });
  assert.equal((h.match(/●/g) || []).length, 5, '5 Punkte für 5 Sequenz-Einträge');
});

test('_streakRowHtml: Signal-Indikator (Stufe 2) bestätigt/widerspricht', () => {
  const t = loadCards().__wmCardTest;
  const confirm = t.streakRowHtml({ teamId: '42', team: 'Arsenal', leagueName: 'PL', type: 'over25',
    market: 'Über 2,5 Tore', length: 5, ratePct: 70, continuation: { state: 'intakt' },
    signalInfo: { state: 'confirm', count: 3, names: ['form_trend', 'h2h_pattern'] } });
  assert.match(confirm, /3 Signale bestätigen/);
  assert.match(confirm, /Form-Trend/);          // _SIG_META-Label
  const against = t.streakRowHtml({ teamId: '42', team: 'Arsenal', leagueName: 'PL', type: 'over25',
    market: 'Über 2,5 Tore', length: 5, ratePct: 70, continuation: { state: 'wackelt' },
    signalInfo: { state: 'contradict', count: 2, names: [] } });
  assert.match(against, /2 Signale dagegen/);
});

test('Serien-Tab: Heiß-Hero + „Nur heiße"-Filter', async () => {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="streaksPanel"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const streaks = { streaks: [
    { teamId: '42', team: 'HeissTeam', league: 'ENG', leagueName: 'PL', type: 'over25', venue: 'all',
      market: 'Über 2,5 Tore', length: 7, ratePct: 78, continuation: { state: 'intakt', label: 'x' },
      signalInfo: { state: 'confirm', count: 3, names: ['form_trend'] } },
    { teamId: '99', team: 'KaltTeam', league: 'ENG', leagueName: 'PL', type: 'under25', venue: 'all',
      market: 'Unter 2,5 Tore', length: 3, ratePct: 40, continuation: { state: 'wackelt', label: 'y' } },
  ] };
  w.fetch = (url) => Promise.resolve({ ok: true, json: () => Promise.resolve(String(url).includes('liga_streaks') ? streaks : {}) });
  w.eval(readFileSync(WM_RENDERER, 'utf8'));
  await w.initStreaks('national');
  const panel = () => w.document.getElementById('streaksPanel').innerHTML;
  assert.match(panel(), /Heißeste Serien/, 'Hero-Spotlight da');
  assert.match(panel(), /HeissTeam/);
  assert.match(panel(), /Nur heiße/, 'Heiß-Toggle da');
  // „Nur heiße" → KaltTeam (wackelt) verschwindet, HeissTeam bleibt (im Hero)
  w.wmSetStreakHot();
  assert.match(panel(), /HeissTeam/);
  assert.ok(!/KaltTeam/.test(panel()), 'wackelnde Serie im Heiß-Filter raus');
});

test('Serien-Tab: Venue-Filter zeigt Gesamt vs Heim/Auswärts', async () => {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="streaksPanel"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const streaks = { streaks: [
    { teamId: '42', team: 'Arsenal', league: 'ENG', leagueName: 'PL', type: 'over25', venue: 'all',
      market: 'Über 2,5 Tore', length: 6, strong: true, continuation: { state: 'intakt', label: 'x' } },
    { teamId: '42', team: 'Arsenal', league: 'ENG', leagueName: 'PL', type: 'over25', venue: 'H',
      market: 'Über 2,5 Tore', length: 4, strong: false, continuation: { state: 'intakt', label: 'x' } },
    { teamId: '99', team: 'Spurs', league: 'ENG', leagueName: 'PL', type: 'cards', venue: 'A',
      market: 'Über 3,5 Karten', length: 5, strong: false, continuation: { state: 'neutral' } },
  ] };
  w.fetch = (url) => Promise.resolve({ ok: true, json: () => Promise.resolve(String(url).includes('liga_streaks') ? streaks : {}) });
  w.eval(readFileSync(WM_RENDERER, 'utf8'));
  await w.initStreaks('national');
  const panel = () => w.document.getElementById('streaksPanel').innerHTML;
  // Default Gesamt: die venue='all'-Serie (Arsenal, Länge 6) erscheint (im Hero-Spotlight als „6"),
  // nicht die Heim-Variante (Länge 4, durch Venue-Filter raus).
  assert.match(panel(), /Arsenal/);
  assert.ok(!/4 in Folge/.test(panel()), 'Heim-Duplikat nicht im Gesamt-View');
  assert.match(panel(), /Heim/);          // Venue-Filterleiste vorhanden
  // Auswärts: Karten-Serie von Spurs
  w.wmSetStreakVenue('A');
  assert.ok(/Spurs/.test(panel()) && /Karten/.test(panel()), 'Auswärts-View zeigt A-Serien');
});

test('_matchStreaksHtml: Heim-Team zeigt Heim-Serie (Venue-Dedup, keine Duplikate)', () => {
  const t = loadCards().__wmCardTest;
  t.setStreaksCache('wm', { streaks: [
    { teamId: 'ZAF', team: 'Südafrika', type: 'over25', market: 'Über 2,5 Tore', venue: 'all', length: 5, continuation: { state: 'intakt', label: 'x' } },
    { teamId: 'ZAF', team: 'Südafrika', type: 'over25', market: 'Über 2,5 Tore', venue: 'H', length: 6, continuation: { state: 'intakt', label: 'x' } },
  ] });
  const h = t.matchStreaksHtml('ZAF', 'CAN');
  assert.match(h, /Heim/);                       // venue-passende Variante gewählt
  assert.equal((h.match(/Über 2,5 Tore/g) || []).length, 1, 'nur EINE Serie pro Markt (kein all+H-Duplikat)');
  assert.match(h, /6×/);                          // die Heim-Serie (Länge 6), nicht die Gesamt (5)
});

test('Sharp-Konsens: Pinnacle vs Betfair (einig / uneinig / weicht ab / fehlt)', () => {
  const t = loadCards().__wmCardTest;
  // einig: gleicher Favorit (Heim), kleine Differenz
  let c = t.sharpConsensus({ hw: 1.5, dr: 4.2, aw: 6.5, bf_hw: 1.55, bf_dr: 4.3, bf_aw: 6.2 });
  assert.ok(c && /Konsens/.test(c.label), 'sollte Konsens melden');
  // unterschiedliche Favoriten → uneinig
  c = t.sharpConsensus({ hw: 1.5, dr: 4.2, aw: 6.5, bf_hw: 6.0, bf_dr: 4.0, bf_aw: 1.5 });
  assert.ok(c && /uneinig/.test(c.label), 'sollte uneinig melden');
  // gleicher Favorit, aber Betfair weicht spürbar ab
  c = t.sharpConsensus({ hw: 1.5, dr: 4.2, aw: 6.5, bf_hw: 1.9, bf_dr: 4.3, bf_aw: 6.2 });
  assert.ok(c && /weicht/.test(c.label), 'sollte Abweichung melden');
  // kein Betfair → null
  assert.equal(t.sharpConsensus({ hw: 1.5, dr: 4.2, aw: 6.5 }), null);
});

test('_fxIsPast: kickoff entscheidet, nicht das Spieltag-Datum (Nach-Mitternacht-Fix)', () => {
  const t = loadCards().__wmCardTest;
  const today = new Date().toISOString().slice(0, 10);
  const future = new Date(Date.now() + 86400000).toISOString().replace(/\.\d+Z$/, 'Z');
  const past = new Date(Date.now() - 86400000).toISOString().replace(/\.\d+Z$/, 'Z');
  // Spät-Anpfiff: Spieltag-Datum gestern, aber Anpfiff erst in der Zukunft → NICHT gespielt
  assert.equal(t.fxIsPast({ date: '2000-01-01', kickoff: future, result: null }, today), false,
    'Spiel mit zukünftigem Anpfiff darf nicht „gespielt" sein, auch wenn date < heute');
  // Anpfiff vorbei → gespielt
  assert.equal(t.fxIsPast({ date: '2000-01-01', kickoff: past, result: null }, today), true);
  // Endstatus zählt immer als gespielt
  assert.equal(t.fxIsPast({ date: '2999-01-01', kickoff: future, result: { status: 'FT' } }, today), true);
});

test('Liga-Cards kuratiert: Alle→Pro-Liga-Top-3, Liga-Klick→beste, Spieltag→Vollansicht', async () => {
  const liga = {
    _meta: { profile: 'liga_default' },
    groups: {
      ENG: { name: 'Premier League', flag: '🏴',
        teams: [{ id: 'che', name: 'Chelsea' }, { id: 'ars', name: 'Arsenal' },
                { id: 'liv', name: 'Liverpool' }, { id: 'mci', name: 'Man City' }],
        fixtures: [_ligaFixture('che', 'ars', 1, 2), _ligaFixture('liv', 'mci', 1, 3),
                   _ligaFixture('ars', 'liv', 2, 9), _ligaFixture('che', 'mci', 2, 10)] },
      ESP: { name: 'La Liga', flag: '🇪🇸',
        teams: [{ id: 'rma', name: 'Real' }, { id: 'fcb', name: 'Barca' }],
        fixtures: [_ligaFixture('rma', 'fcb', 1, 2)] },
    },
    picks: { 'ENG-1-che-ars': [{ market: 'Heimsieg', verdict: 'BET', convictionScore: 8, odds: 1.8, signals: [] }] },
    odds: {}, standings: {}, squads: {}, form: {}, playerPicks: {},
  };
  const w = loadNational(liga);
  await w.initNationalCards();
  const mc = () => w.document.getElementById('mainContent').innerHTML;

  // (A) Default Alle Ligen + Alle Spieltage → pro Liga Top 3, beide Ligen sichtbar, ENG zuerst (BET 8)
  let html = mc();
  assert.match(html, /Beste Picks pro Liga/, 'Kuratierte Überschrift fehlt');
  assert.match(html, /Premier League/);
  assert.match(html, /La Liga/);
  assert.match(html, /alle 4 Spiele →/, 'ENG-Liga-Header mit Gesamtzahl');
  assert.ok(html.indexOf('Premier League') < html.indexOf('La Liga'), 'Liga mit bestem Pick (ENG) zuerst');
  assert.ok(!/Sortierung:/.test(html), 'Sort-Bar im kuratierten Modus ausgeblendet');

  // (B) Liga-Klick → beste dieser Liga, kein Auto-Spieltag
  w.wmSetGroup('ENG');
  html = mc();
  assert.match(html, /Beste zuerst/, 'Beste-der-Liga-Ansicht fehlt');

  // (C) Konkreter Spieltag → Vollansicht mit Datums-Trenner, keine kuratierte Überschrift
  w.wmSetMd(1);
  html = mc();
  assert.ok(!/Beste zuerst/.test(html) && !/Beste Picks pro Liga/.test(html), 'Vollansicht ohne Kuratier-Überschrift');
  assert.match(html, /wm-date-divider/, 'Vollansicht zeigt Datums-Trenner');
});

// 29.06.2026 (Lucas): MLS „wie die anderen Ligen" — National merged liga-data.json + mls-data.json,
// MLS erscheint als weitere Liga in der kuratierten Ansicht.
test('National-Cards: MLS-Datensatz wird mitgemerged (erscheint als weitere Liga)', async () => {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="mainContent"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const liga = { _meta: { profile: 'liga_default' },
    groups: { ENG: { name: 'Premier League', flag: '🏴',
      teams: [{ id: 'che', name: 'Chelsea' }, { id: 'ars', name: 'Arsenal' }],
      fixtures: [_ligaFixture('che', 'ars', 1, 2)] } },
    picks: {}, odds: {} };
  const mls = { _meta: { profile: 'mls_default' },
    groups: { MLS: { name: 'Major League Soccer', flag: '🇺🇸',
      teams: [{ id: 'mia', name: 'Inter Miami' }, { id: 'lag', name: 'LA Galaxy' }],
      fixtures: [_ligaFixture('mia', 'lag', 25, 3)] } },
    picks: { 'MLS-25-mia-lag': [{ market: 'Heimsieg', verdict: 'BET', convictionScore: 7, odds: 1.9, signals: [] }] },
    odds: {} };
  w.fetch = (url) => {
    const u = String(url);
    const body = u.includes('mls-data.json') ? mls : u.includes('liga-data.json') ? liga : {};
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  };
  w.eval(readFileSync(WM_RENDERER, 'utf8'));
  await w.initNationalCards();
  const html = w.document.getElementById('mainContent').innerHTML;
  assert.match(html, /Premier League/, 'Top-5-Liga sichtbar');
  assert.match(html, /Major League Soccer/, 'MLS als weitere Liga gemerged');
  assert.match(html, /Inter Miami/, 'MLS-Team gerendert');
});

test('National-Serien: MLS-Streaks werden mitgemerged', async () => {
  const dom = new JSDOM('<!DOCTYPE html><body><div id="streaksPanel"></div></body>', {
    url: 'https://example.com/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const ligaS = { streaks: [{ teamId: '42', team: 'Arsenal', league: 'ENG', leagueName: 'PL',
    type: 'over25', venue: 'all', market: 'Über 2,5 Tore', length: 5, strong: true, continuation: { state: 'intakt' } }] };
  const mlsS  = { streaks: [{ teamId: 'mia', team: 'Inter Miami', league: 'MLS', leagueName: 'Major League Soccer',
    type: 'cornersOver', venue: 'all', market: 'Über 9,5 Ecken', length: 4, strong: false, continuation: { state: 'neutral' } }] };
  w.fetch = (url) => {
    const u = String(url);
    const body = u.includes('mls_streaks') ? mlsS : u.includes('liga_streaks') ? ligaS : {};
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  };
  w.eval(readFileSync(WM_RENDERER, 'utf8'));
  await w.initStreaks('national');
  const html = w.document.getElementById('streaksPanel').innerHTML;
  assert.match(html, /Arsenal/, 'Liga-Serie sichtbar');
  assert.match(html, /Inter Miami/, 'MLS-Serie mitgemerged');
});

test('Bepicktes KO-Spiel läuft 1:1 durch _buildCard (Runden-Header, kein „ST", kein Crash)', () => {
  const w = loadCards();
  const t = w.__wmCardTest;
  t.setWmData({ form: { CIV: { last5: ['W','W','D','W','L'], avgScored: 1.8 }, NOR: { last5: ['L','W','W','D','W'], avgScored: 1.5 } } });
  // Anpfiff dynamisch 7 Tage in der Zukunft → _fxIsPast (Date.now-basiert) liefert nie „gespielt",
  // Test bleibt deterministisch unabhängig vom echten Datum (30.06.2026: vorher kippte er, sobald die
  // reale Zeit den fixen 2026-06-30-Anpfiff überholte → Card wurde cc-played statt Pick-Card).
  const _futureKo = new Date(Date.now() + 7 * 86400000).toISOString();
  const fx = {
    home: 'CIV', away: 'NOR', date: _futureKo.slice(0, 10), time: '17:00', kickoff: _futureKo,
    matchday: 'R32', groupKey: 'KO', isKO: true, result: null,
    koData: { round: 'R32', roundLabel: 'Sechzehntelfinale', matchNo: 78, bothResolved: true, home: 'CIV', away: 'NOR' },
    groupData: { name: 'K.O.-Runde', teams: [{ id:'CIV', name:'Elfenbeinküste', flag:'🇨🇮', elo:1700 }, { id:'NOR', name:'Norwegen', flag:'🇳🇴', elo:1720 }] },
  };
  const gData = fx.groupData;
  const home = gData.teams[0], away = gData.teams[1];
  const odds = { hw: 2.40, dr: 3.20, aw: 3.00 };
  const picks = [
    { market: 'Doppelte Chance — 1X', verdict: 'BET', odds: 1.45, convictionScore: 7, stake: 6,
      signalAdjustmentPP: 1.0, signals: [{ name: 'form_trend', score: 0.6, evidence: 'Heimform' }] },
    { market: 'Über 2.5 Tore', verdict: 'ABWÄGEN', odds: 1.90, convictionScore: 4, stake: 2.5, edgePP: 1 },
  ];
  // standing = null (KO hat keine Tabelle) → darf NICHT crashen
  const html = t.buildCard(fx, gData, home, away, odds, picks, null, null, null, null,
    gData.teams[0] && { last5:['W'] }, null, null, '2026-06-27');
  assert.match(html, /Sechzehntelfinale/, 'KO-Runden-Label im Header');
  assert.ok(!/· ST R32/.test(html), 'Kein „ST R32" mehr (KO hat keinen Spieltag)');
  assert.match(html, /Doppelte Chance/, 'Pick-Markt sichtbar (volle Card)');
  assert.match(html, /Einsatz €6/, 'Stake am Hero-Pick sichtbar');
  assert.match(html, /€2\.5/, 'Stake auch am weiteren (ABWÄGEN) Pick sichtbar');
  assert.match(html, /Elfenbeinküste/);
});

test('KO-Vorschau ohne Pick zeigt Serien + Analyse-Link (30.06.2026, Lucas)', () => {
  const w = loadCards();
  const t = w.__wmCardTest;
  t.setWmData({ form: { CIV: { last5: ['W','W','D'], avgGoals: 2.4 }, NOR: { last5: ['L','W','W'], avgGoals: 2.1 } } });
  t.setStreaksCache('wm', { streaks: [
    { teamId: 'CIV', team: 'Elfenbeinküste', league: 'KO', type: 'over25', market: 'Über 2,5 Tore', length: 5, continuation: { state: 'intakt', label: 'intakt' } },
  ] });
  const _futureKo = new Date(Date.now() + 7 * 86400000).toISOString();
  const fx = {
    home: 'CIV', away: 'NOR', date: _futureKo.slice(0, 10), time: '17:00', kickoff: _futureKo, result: null,
    koData: { round: 'R32', roundLabel: 'Sechzehntelfinale', matchNo: 78, bothResolved: true, home: 'CIV', away: 'NOR' },
  };
  const home = { id: 'CIV', name: 'Elfenbeinküste', flag: '🇨🇮', elo: 1700 };
  const away = { id: 'NOR', name: 'Norwegen', flag: '🇳🇴', elo: 1720 };
  // KEINE Picks → Zustand 2 (Vorschau)
  const html = t.buildKoCard(fx, home, away, {}, [], null, '2026-06-27');
  assert.match(html, /Quoten folgen/, 'ist die Vorschau (kein Pick)');
  assert.match(html, /Serien in diesem Spiel/, 'Serien werden gezeigt');
  assert.match(html, /wm-civ-vs-nor-/, 'Analyse-Link auf die Event-Page');
  assert.match(html, /↗ Analyse/);
});

test('KO-Vorschau bei TBD (Teams offen) bleibt schlank — kein Analyse-Link', () => {
  const w = loadCards();
  const t = w.__wmCardTest;
  t.setWmData({ form: {} });
  const fx = { home: null, away: null, date: '2026-07-10', kickoff: '2026-07-10T19:00:00Z', result: null,
    koData: { round: 'R16', roundLabel: 'Achtelfinale', matchNo: 89, bothResolved: false,
      homeRef: 'Sieger Spiel 73', awayRef: 'Sieger Spiel 74' } };
  const html = t.buildKoCard(fx, {}, {}, {}, [], null, '2026-06-27');
  assert.match(html, /Teams stehen noch nicht fest/);
  assert.ok(!/↗ Analyse/.test(html), 'kein Analyse-Link für offene Paarung');
});

test('KO-Card ist reich: Pick + Conviction + Signal-Grid + Form', () => {
  const w = loadCards();
  const t = w.__wmCardTest;
  t.setWmData({ form: {
    CIV: { last5: ['W', 'W', 'D', 'W', 'L'], avgScored: 1.8 },
    NOR: { last5: ['L', 'W', 'W', 'D', 'W'], avgScored: 1.5 },
  } });
  const fx = {
    home: 'CIV', away: 'NOR', date: '2026-06-30', kickoff: '2026-06-30T17:00:00Z',
    isKO: true, result: null,
    koData: { round: 'R32', roundLabel: 'Sechzehntelfinale', matchNo: 78,
              bothResolved: true, home: 'CIV', away: 'NOR' },
  };
  const home = { name: 'Elfenbeinküste', flag: '🇨🇮', elo: 1700 };
  const away = { name: 'Norwegen', flag: '🇳🇴', elo: 1720 };
  const picks = [{
    market: 'Doppelte Chance — 1X', verdict: 'ABWÄGEN', odds: 1.41, convictionScore: 5,
    signalAdjustmentPP: 1.0,
    signals: [{ name: 'league_pressure', score: 1.0, evidence: 'Druck' },
              { name: 'form_trend', score: 0.5, evidence: 'Heimform' }],
  }];
  const html = t.buildKoCard(fx, home, away, {}, picks, null, '2026-06-27');
  assert.match(html, /Doppelte Chance/, 'Pick-Markt muss erscheinen');
  assert.match(html, /Vorsichtiger Pick/, 'ABWÄGEN-Label');
  assert.match(html, /Warum\?/, 'Warum-Button muss da sein');
  assert.match(html, /Engine-Signale/, 'Signal-Grid muss da sein');
  assert.match(html, /Form letzten 5/, 'Form-Block muss da sein');
  assert.match(html, /Elfenbeinküste/);
});

// ── 06.09.2026 (Cards-Check) — die Ueberschrift behauptete Edge, den der Erzeuger verneint ──
// „🎯 Sieg-Pick mit Edge" stand ueber einem Pick, den `matches/data/*.json` als
// `verdict: "ABWÄGEN"` mit `edgePP: -2` fuehrte. Die Ueberschrift kam ausschliesslich aus
// Markt-String und Elo — `verdict` und `edgePP` kamen darin nicht vor.
//
// Gemessen ueber 731 Match-Dateien: von den Picks mit Edge-Wert haben **430 einen Edge <= 0
// und nur 41 einen ueber null**; Verdicts 289 ABWÄGEN / 153 NOBET / 27 BET. „mit Edge" stand
// also auf fast jeder Karte, und in neun von zehn Faellen widersprach die Zahl darunter.
const CODE = readFileSync(WM_RENDERER, 'utf8');

test('die Edge-Behauptung haengt am Urteil des Erzeugers, nicht am Markt-String', () => {
  const nurCode = CODE.split('\n').filter((z) => !/^\s*(\/\/|\*|\/\*)/.test(z)).join('\n');
  assert.ok(!/label: 'Sieg-Pick mit Edge'/.test(nurCode),
    'die feste Behauptung „Sieg-Pick mit Edge" darf nicht mehr im Code stehen');
  assert.ok(!/label: 'Pick mit Edge'/.test(nurCode),
    'die feste Behauptung „Pick mit Edge" darf nicht mehr im Code stehen');
  assert.match(nurCode, /_hatEdge\s*=\s*\(_v === 'BET'\)/,
    'Edge nur, wenn der Erzeuger BET sagt');
  assert.match(nurCode, /typeof _e === 'number' && _e > 0/,
    'und nur bei positivem edgePP');
});

test('ohne edgePP wird weder Edge behauptet noch eine Zahl erfunden', () => {
  // Kein Urteil ist etwas anderes als ein gemessenes Nein: 674 der 731 Dateien tragen gar
  // keinen edgePP — dort darf schlicht nichts dranstehen.
  const nurCode = CODE.split('\n').filter((z) => !/^\s*(\/\/|\*|\/\*)/.test(z)).join('\n');
  assert.match(nurCode, /_edgeTxt = _hatEdge \? ' mit Edge'/);
  assert.match(nurCode, /: \(typeof _e === 'number' \? ' · Edge '/,
    'ein vorhandener negativer Edge wird BENANNT, nicht verschwiegen');
  assert.match(nurCode, /: ''\)/, 'ohne edgePP bleibt das Label ohne Zusatz');
});

test('Kategorie-Labels bleiben unberuehrt — sie beschreiben den Markt, nicht den Edge', () => {
  assert.match(CODE, /label: 'Tor-Fest erwartet'/);
  assert.match(CODE, /label: 'Defensiv-Schlacht'/);
});
