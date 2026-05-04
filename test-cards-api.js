// ═══════════════════════════════════════════════════════════════════════════
//  TheOddsAPI — Multi-Liga Specialty Markets Test
//  node test-cards-api.js
//
//  Testet alle unsere Ligen auf BTTS / Ecken / Karten / DC Verfügbarkeit.
//  Pro Liga: 1 Event-List-Call + 1 Specialty-Call = 2 API-Credits.
//  Bei ~10 Ligen: ~20 Credits gesamt.
// ═══════════════════════════════════════════════════════════════════════════
const https = require('https');

const ODDS_API_KEY  = process.env.ODDS_API_KEY || '';
const ODDS_API_HOST = 'api.the-odds-api.com';

// Alle Ligen die wir im Dashboard tracken — sport_key muss exakt mit TheOddsAPI übereinstimmen
const LEAGUES = [
  { name: 'Premier League (ENG)',       key: 'soccer_england_premier_league' },
  { name: 'La Liga (ESP)',              key: 'soccer_spain_la_liga'           },
  { name: 'Bundesliga (GER)',           key: 'soccer_germany_bundesliga'      },
  { name: 'Serie A (ITA)',              key: 'soccer_italy_serie_a'           },
  { name: 'Ligue 1 (FRA)',             key: 'soccer_france_ligue_one'        },
  { name: 'Eredivisie (NED)',           key: 'soccer_netherlands_eredivisie'  },
  { name: 'Austrian BL (AUT)',          key: 'soccer_austria_bundesliga'      },
  { name: 'Scottish Prem (SCO)',        key: 'soccer_spl'                     },
  { name: 'Swiss Superleague (SUI)',    key: 'soccer_switzerland_superleague' },
  { name: 'Belgian Pro League (BEL)',   key: 'soccer_belgium_first_div'       },
];

const SPECIALTY_MARKETS = [
  'btts',
  'alternate_totals_corners',
  'alternate_totals_cards',
  'double_chance',
  'alternate_totals',
  'h2h_h1',
  'totals_h1',
  'btts_h1',
].join(',');

// Märkte die wir kritisch brauchen
const CRITICAL = ['btts', 'alternate_totals_corners', 'alternate_totals_cards', 'double_chance'];

function get(path) {
  return new Promise((resolve) => {
    const options = { hostname: ODDS_API_HOST, path, method: 'GET',
      headers: { 'User-Agent': 'BetEdge/1.0' } };
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

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function testLeague(league) {
  // Step 1: Erstes verfügbares Event holen
  const evRes = await get(`/v4/sports/${league.key}/events?apiKey=${ODDS_API_KEY}`);
  if (evRes.status !== 200) {
    let errMsg = evRes.body.slice(0, 120);
    try { errMsg = JSON.parse(evRes.body).message || errMsg; } catch(_) {}
    return { league, status: 'error', error: `HTTP ${evRes.status}: ${errMsg}`, remaining: null };
  }

  let events;
  try { events = JSON.parse(evRes.body); } catch(_) {
    return { league, status: 'error', error: 'JSON parse error', remaining: null };
  }

  const remaining = evRes.headers['x-requests-remaining'] || '?';

  if (!Array.isArray(events) || events.length === 0) {
    return { league, status: 'no_events', remaining };
  }

  const ev = events[0];

  // Step 2: Specialty markets für dieses Event abrufen
  const spRes = await get(
    `/v4/sports/${league.key}/events/${ev.id}/odds?apiKey=${ODDS_API_KEY}`
    + `&regions=eu,uk&markets=${SPECIALTY_MARKETS}&oddsFormat=decimal`
  );

  const remaining2 = spRes.headers['x-requests-remaining'] || remaining;

  if (spRes.status !== 200) {
    return { league, status: 'specialty_error', event: ev, error: `HTTP ${spRes.status}`, remaining: remaining2 };
  }

  let spData;
  try { spData = JSON.parse(spRes.body); } catch(_) {
    return { league, status: 'specialty_error', event: ev, error: 'JSON parse error', remaining: remaining2 };
  }

  const bookmakers = spData.bookmakers || [];
  const marketsByBkr = {};     // market_key → [bookmaker_key, ...]
  const sampleOdds   = {};     // market_key → "Bkr: outcome: price | ..."

  for (const bkr of bookmakers) {
    for (const mkt of (bkr.markets || [])) {
      if (!marketsByBkr[mkt.key]) marketsByBkr[mkt.key] = [];
      marketsByBkr[mkt.key].push(bkr.key);
      if (!sampleOdds[mkt.key]) {
        const sample = (mkt.outcomes || []).slice(0, 3)
          .map(o => `${o.name}${o.point != null ? ' '+o.point : ''}: ${o.price}`)
          .join(' | ');
        sampleOdds[mkt.key] = `${bkr.key}: ${sample}`;
      }
    }
  }

  return {
    league,
    status: 'ok',
    event: ev,
    bookmakerCount: bookmakers.length,
    marketsByBkr,
    sampleOdds,
    remaining: remaining2,
  };
}

(async () => {
  if (!ODDS_API_KEY) {
    console.error('❌ ODDS_API_KEY nicht gesetzt — export ODDS_API_KEY=... oder via GitHub Secrets');
    process.exit(1);
  }

  console.log('═══════════════════════════════════════════════════════════════');
  console.log('  TheOddsAPI — Multi-Liga Specialty Markets Test');
  console.log(`  Ligen: ${LEAGUES.length} | Märkte: btts, corners, cards, dc, ...`);
  console.log('═══════════════════════════════════════════════════════════════\n');

  const results = [];

  for (const league of LEAGUES) {
    process.stdout.write(`Teste ${league.name.padEnd(30)} ... `);
    const r = await testLeague(league);
    results.push(r);
    if (r.status === 'ok') {
      const criticalFound = CRITICAL.filter(k => r.marketsByBkr[k]);
      const criticalMissing = CRITICAL.filter(k => !r.marketsByBkr[k]);
      const icon = criticalMissing.length === 0 ? '✅' : criticalMissing.length <= 1 ? '🟡' : '🔴';
      console.log(`${icon} ${r.bookmakerCount} Bkr | Credits übrig: ${r.remaining}`);
    } else if (r.status === 'no_events') {
      console.log(`⬜ Kein aktiver Spieltag`);
    } else {
      console.log(`❌ ${r.error}`);
    }
    await sleep(500);  // Rate-limit schonen
  }

  // ── Detailreport ────────────────────────────────────────────────────────────
  console.log('\n\n══════════════════════════════════════════════════════════════════════');
  console.log('  DETAILREPORT — Welche Märkte pro Liga verfügbar');
  console.log('══════════════════════════════════════════════════════════════════════');

  for (const r of results) {
    console.log(`\n▶ ${r.league.name} (${r.league.key})`);
    if (r.status === 'no_events') { console.log('   ⬜ Kein aktiver Spieltag — kein Test möglich'); continue; }
    if (r.status !== 'ok') { console.log(`   ❌ ${r.error}`); continue; }
    console.log(`   Event: ${r.event.home_team} vs ${r.event.away_team} (${(r.event.commence_time||'').slice(0,10)})`);
    console.log(`   Bookmakers gesamt: ${r.bookmakerCount}`);

    // Kritische Märkte
    console.log('   Kritische Märkte:');
    for (const k of CRITICAL) {
      const bkrs = r.marketsByBkr[k];
      if (bkrs) {
        console.log(`     ✅ ${k.padEnd(28)} → ${bkrs.join(', ')}`);
        console.log(`        Sample: ${r.sampleOdds[k]}`);
      } else {
        console.log(`     ❌ ${k.padEnd(28)} → FEHLT`);
      }
    }

    // Sonstige Märkte
    const other = Object.keys(r.marketsByBkr).filter(k => !CRITICAL.includes(k));
    if (other.length) {
      console.log(`   Weitere Märkte: ${other.join(', ')}`);
    }
  }

  // ── Zusammenfassung ─────────────────────────────────────────────────────────
  console.log('\n\n══════════════════════════════════════════════════════════════════════');
  console.log('  ZUSAMMENFASSUNG');
  console.log('══════════════════════════════════════════════════════════════════════');

  const okResults = results.filter(r => r.status === 'ok');
  for (const k of CRITICAL) {
    const withMarket    = okResults.filter(r => r.marketsByBkr[k]).map(r => r.league.name);
    const withoutMarket = okResults.filter(r => !r.marketsByBkr[k]).map(r => r.league.name);
    const icon = withoutMarket.length === 0 ? '✅' : withoutMarket.length <= 2 ? '🟡' : '🔴';
    console.log(`\n${icon} ${k}`);
    if (withMarket.length)    console.log(`   Verfügbar:  ${withMarket.join(', ')}`);
    if (withoutMarket.length) console.log(`   ❌ Fehlt:   ${withoutMarket.join(', ')}`);
  }

  const lastRemaining = results.filter(r => r.remaining).pop()?.remaining;
  if (lastRemaining) console.log(`\n💳 TheOddsAPI Credits verbleibend: ${lastRemaining}`);

  console.log('\n══════════════════════════════════════════════════════════════════════\n');
})();
