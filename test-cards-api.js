// ═══════════════════════════════════════════════════════════════════════════
//  TheOddsAPI — Diagnose-Script für Specialty Markets (BTTS, Corners, Cards)
//  node test-cards-api.js
// ═══════════════════════════════════════════════════════════════════════════
const https = require('https');

const ODDS_API_KEY = process.env.ODDS_API_KEY || 'e33cee8d4ce8d646476115c7d1e3f3e4';
const ODDS_API_HOST = 'api.the-odds-api.com';

const TEST_SPORT = 'soccer_spain_la_liga';  // La Liga — meistens genug Spiele

function get(path) {
  return new Promise((resolve) => {
    const options = { hostname: ODDS_API_HOST, path, method: 'GET', headers: { 'User-Agent': 'BetEdge/1.0' } };
    const req = https.request(options, res => {
      let body = '';
      res.on('data', d => body += d);
      res.on('end', () => {
        resolve({ status: res.statusCode, headers: res.headers, body });
      });
    });
    req.on('error', e => resolve({ status: 0, headers: {}, body: e.message }));
    req.setTimeout(15000, () => { req.destroy(); resolve({ status: 0, headers: {}, body: 'timeout' }); });
    req.end();
  });
}

function parseBody(body) {
  try { return JSON.parse(body); } catch(e) { return body; }
}

async function testMarket(label, path) {
  console.log(`\n── ${label} ──`);
  const { status, headers, body } = await get(path);
  const data = parseBody(body);

  console.log(`  HTTP: ${status} | Remaining: ${headers['x-requests-remaining'] || '?'} | Used: ${headers['x-requests-used'] || '?'}`);

  if (status !== 200) {
    console.log(`  ❌ FEHLER: ${typeof data === 'object' ? JSON.stringify(data) : body.slice(0, 300)}`);
    return null;
  }

  if (!Array.isArray(data)) {
    console.log(`  ⚠️  Non-array response: ${JSON.stringify(data).slice(0, 200)}`);
    return null;
  }

  if (data.length === 0) {
    console.log(`  ⚠️  0 Events — kein Spieltag gerade oder Market nicht verfügbar`);
    return data;
  }

  // Welche Market-Keys kommen zurück?
  const allKeys = new Set();
  for (const ev of data)
    for (const bkr of (ev.bookmakers || []))
      for (const mkt of (bkr.markets || []))
        allKeys.add(mkt.key);

  console.log(`  ✅ ${data.length} Events | Markets: [${[...allKeys].join(', ')}]`);

  // Sample-Quoten für jeden Market-Key
  for (const key of allKeys) {
    for (const ev of data) {
      for (const bkr of (ev.bookmakers || [])) {
        const mkt = (bkr.markets || []).find(m => m.key === key);
        if (!mkt) continue;
        const outcomes = (mkt.outcomes || []).slice(0, 4).map(o => `${o.name}${o.point != null ? ' '+o.point : ''}: ${o.price}`).join(' | ');
        console.log(`    ${key} @ ${bkr.key}: ${outcomes}`);
        break; // nur erste Bookie als Sample
      }
      break; // nur erstes Event als Sample
    }
  }

  return data;
}

(async () => {
  console.log('═══════════════════════════════════════════════════');
  console.log('  TheOddsAPI Specialty Markets Diagnose');
  console.log(`  Sport: ${TEST_SPORT}`);
  console.log('═══════════════════════════════════════════════════');

  // 1. Welche Markets sind laut API überhaupt verfügbar?
  console.log('\n[1] Verfügbare Markets für diesen Sport:');
  const { status: mSt, body: mBody } = await get(`/v4/sports/${TEST_SPORT}/markets?apiKey=${ODDS_API_KEY}`);
  if (mSt === 200) {
    const markets = parseBody(mBody);
    if (Array.isArray(markets)) {
      console.log('  ' + markets.map(m => m.key).join('\n  '));
    } else {
      console.log('  ', JSON.stringify(markets).slice(0, 500));
    }
  } else {
    console.log(`  HTTP ${mSt}: ${mBody.slice(0, 200)}`);
  }

  // 2. BTTS (UK) — sollte grundsätzlich funktionieren
  await testMarket(
    'BTTS (regions=uk, markets=btts)',
    `/v4/sports/${TEST_SPORT}/odds/?apiKey=${ODDS_API_KEY}&regions=uk&markets=btts&oddsFormat=decimal`
  );

  // 3. Corners (UK) — separate um Interference zu vermeiden
  await testMarket(
    'Corners (regions=uk, markets=alternate_totals_corners)',
    `/v4/sports/${TEST_SPORT}/odds/?apiKey=${ODDS_API_KEY}&regions=uk&markets=alternate_totals_corners&oddsFormat=decimal`
  );

  // 4. Cards (UK) — der kritische Test
  await testMarket(
    'Cards (regions=uk, markets=alternate_totals_cards)',
    `/v4/sports/${TEST_SPORT}/odds/?apiKey=${ODDS_API_KEY}&regions=uk&markets=alternate_totals_cards&oddsFormat=decimal`
  );

  // 5. Alt-Bundle wie im Server (eu+uk, alle markets zusammen)
  await testMarket(
    'Alt-Bundle wie im Server (regions=eu,uk, alle Markets)',
    `/v4/sports/${TEST_SPORT}/odds/?apiKey=${ODDS_API_KEY}&regions=eu,uk&markets=alternate_totals_corners,alternate_totals_cards,alternate_totals,alternate_spreads,double_chance&oddsFormat=decimal`
  );

  console.log('\n═══════════════════════════════════════════════════');
  console.log('  Fertig');
  console.log('═══════════════════════════════════════════════════');
})();
