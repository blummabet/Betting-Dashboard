// ═══════════════════════════════════════════════════════════════════════════
//  TheOddsAPI — Test-Script für Specialty Markets via /events/{eventId}/odds
//  node test-cards-api.js
//
//  Hintergrund: "Additional markets" (btts, corners, cards, double_chance etc.)
//  sind NICHT über den Batch-Endpoint /sports/{sport}/odds/ verfügbar.
//  TheOddsAPI Doku: "additional markets need to be accessed one event at a time
//  using the new /events/{eventId}/odds endpoint."
// ═══════════════════════════════════════════════════════════════════════════
const https = require('https');

const ODDS_API_KEY = process.env.ODDS_API_KEY || 'e33cee8d4ce8d646476115c7d1e3f3e4';
const ODDS_API_HOST = 'api.the-odds-api.com';
const TEST_SPORT = 'soccer_spain_la_liga';

function get(path) {
  return new Promise((resolve) => {
    const options = { hostname: ODDS_API_HOST, path, method: 'GET', headers: { 'User-Agent': 'BetEdge/1.0' } };
    const req = https.request(options, res => {
      let body = '';
      res.on('data', d => body += d);
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body }));
    });
    req.on('error', e => resolve({ status: 0, headers: {}, body: e.message }));
    req.setTimeout(15000, () => { req.destroy(); resolve({ status: 0, headers: {}, body: 'timeout' }); });
    req.end();
  });
}

function parseBody(body) {
  try { return JSON.parse(body); } catch(e) { return body; }
}

(async () => {
  console.log('═══════════════════════════════════════════════════════');
  console.log('  TheOddsAPI Specialty Markets Test (Events Endpoint)');
  console.log(`  Sport: ${TEST_SPORT}`);
  console.log('═══════════════════════════════════════════════════════');

  // ── Step 1: Get event list ────────────────────────────────────────────────
  console.log('\n[1] Events abrufen...');
  const evRes = await get(`/v4/sports/${TEST_SPORT}/events?apiKey=${ODDS_API_KEY}`);
  const events = parseBody(evRes.body);
  console.log(`  HTTP: ${evRes.status} | Remaining: ${evRes.headers['x-requests-remaining'] || '?'}`);

  if (evRes.status !== 200 || !Array.isArray(events) || events.length === 0) {
    console.log('  ❌ Keine Events — kein Spieltag oder Fehler');
    console.log('  ', typeof events === 'string' ? events.slice(0, 300) : JSON.stringify(events).slice(0, 300));
    process.exit(0);
  }

  const firstEvent = events[0];
  console.log(`  ✅ ${events.length} Events | Erstes: ${firstEvent.home_team} vs ${firstEvent.away_team}`);
  console.log(`  Event ID: ${firstEvent.id} | Anpfiff: ${firstEvent.commence_time}`);

  // ── Step 2: Test /events/{eventId}/odds mit allen specialty markets ───────
  console.log('\n[2] /events/{eventId}/odds — alle Specialty Markets auf einmal...');
  const markets = [
    'btts',
    'alternate_totals_corners',
    'alternate_totals_cards',
    'double_chance',
    'alternate_totals',
    'alternate_spreads',
    'h2h_h1',
    'totals_h1',
    'btts_h1',
  ].join(',');

  const evOddsRes = await get(
    `/v4/sports/${TEST_SPORT}/events/${firstEvent.id}/odds?apiKey=${ODDS_API_KEY}`
    + `&regions=eu,uk&markets=${markets}&oddsFormat=decimal`
  );
  const evOdds = parseBody(evOddsRes.body);
  console.log(`  HTTP: ${evOddsRes.status} | Remaining: ${evOddsRes.headers['x-requests-remaining'] || '?'} | Used: ${evOddsRes.headers['x-requests-used'] || '?'}`);

  if (evOddsRes.status !== 200) {
    console.log(`  ❌ FEHLER: ${typeof evOdds === 'object' ? JSON.stringify(evOdds) : String(evOdds).slice(0, 400)}`);
    process.exit(1);
  }

  const bookmakers = evOdds.bookmakers || [];
  if (!bookmakers.length) {
    console.log('  ⚠️  200 OK aber keine Bookmaker-Daten zurück');
    process.exit(0);
  }

  // Sammle alle Market-Keys aus der Antwort
  const allKeys = new Set();
  for (const bkr of bookmakers)
    for (const mkt of (bkr.markets || []))
      allKeys.add(mkt.key);

  console.log(`  ✅ ${bookmakers.length} Bookmakers | Markets: [${[...allKeys].join(', ')}]`);

  // Sample-Quoten pro Market-Key
  console.log('\n[3] Sample-Quoten pro Market:');
  for (const key of allKeys) {
    for (const bkr of bookmakers) {
      const mkt = (bkr.markets || []).find(m => m.key === key);
      if (!mkt) continue;
      const outcomes = (mkt.outcomes || []).slice(0, 5)
        .map(o => `${o.name}${o.point != null ? ' '+o.point : ''}: ${o.price}`)
        .join(' | ');
      console.log(`  ${key} @ ${bkr.key}: ${outcomes}`);
      break;
    }
  }

  // Prüfe gezielt ob die wichtigsten Märkte da sind
  console.log('\n[4] Kritische Märkte — Check:');
  const critical = ['btts', 'alternate_totals_corners', 'alternate_totals_cards', 'double_chance'];
  for (const k of critical) {
    const found = [...allKeys].includes(k);
    console.log(`  ${found ? '✅' : '❌'} ${k}: ${found ? 'VORHANDEN' : 'FEHLT'}`);
  }

  console.log('\n═══════════════════════════════════════════════════════');
  console.log('  Fertig');
  console.log('═══════════════════════════════════════════════════════');
})();
