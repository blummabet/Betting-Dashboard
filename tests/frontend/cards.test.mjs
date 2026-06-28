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

test('Bepicktes KO-Spiel läuft 1:1 durch _buildCard (Runden-Header, kein „ST", kein Crash)', () => {
  const w = loadCards();
  const t = w.__wmCardTest;
  t.setWmData({ form: { CIV: { last5: ['W','W','D','W','L'], avgScored: 1.8 }, NOR: { last5: ['L','W','W','D','W'], avgScored: 1.5 } } });
  const fx = {
    home: 'CIV', away: 'NOR', date: '2026-06-30', time: '17:00', kickoff: '2026-06-30T15:00:00Z',
    matchday: 'R32', groupKey: 'KO', isKO: true, result: null,
    koData: { round: 'R32', roundLabel: 'Sechzehntelfinale', matchNo: 78, bothResolved: true, home: 'CIV', away: 'NOR' },
    groupData: { name: 'K.O.-Runde', teams: [{ id:'CIV', name:'Elfenbeinküste', flag:'🇨🇮', elo:1700 }, { id:'NOR', name:'Norwegen', flag:'🇳🇴', elo:1720 }] },
  };
  const gData = fx.groupData;
  const home = gData.teams[0], away = gData.teams[1];
  const odds = { hw: 2.40, dr: 3.20, aw: 3.00 };
  const picks = [{ market: 'Doppelte Chance — 1X', verdict: 'BET', odds: 1.45, convictionScore: 7,
                   signalAdjustmentPP: 1.0, signals: [{ name: 'form_trend', score: 0.6, evidence: 'Heimform' }] }];
  // standing = null (KO hat keine Tabelle) → darf NICHT crashen
  const html = t.buildCard(fx, gData, home, away, odds, picks, null, null, null, null,
    gData.teams[0] && { last5:['W'] }, null, null, '2026-06-27');
  assert.match(html, /Sechzehntelfinale/, 'KO-Runden-Label im Header');
  assert.ok(!/· ST R32/.test(html), 'Kein „ST R32" mehr (KO hat keinen Spieltag)');
  assert.match(html, /Doppelte Chance/, 'Pick-Markt sichtbar (volle Card)');
  assert.match(html, /Elfenbeinküste/);
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
