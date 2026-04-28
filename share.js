// ═══════════════════════════════════════════════════════
//  share.js — CocoBet Share / Copy / Infographic Engine
//  Extracted from season-finish.html (Apr 2026)
//
//  Contains:
//    · igRoundRect(), igTrunc(), igWrapText()   — Canvas helpers
//    · igDrawPills(), _drawFormSparklineCanvas() — Canvas drawing
//    · _pillColor(), _igT()                     — Infographic helpers
//    · generateInfographic()                    — 1080×1080 Canvas generator
//    · closeIgModal(), shareInfographic()       — Modal + Web Share API
//    · _captureCard(), copyCardImage()          — Card → PNG
//    · copyInfographic()                        — Infographic to clipboard
//    · shareTelegram()                          — Telegram share text
//    · _translateEN()                           — DE→EN translation map
//    · copyCard()                               — Card text to clipboard
//    · showToast()                              — Toast notification
//
//  Runtime dependencies (provided by the page):
//    · LEAGUES                  — injected by update_dashboard.py
//    · window._teamStats        — injected by refresh_stats.py
//    · window._preMatchData     — loaded by prematch-server.js
//    · getBettingPicks()        — from pick-engine.js
//    · computeMatchScore()      — from season-finish.html (main script)
//    · getBettingAngle()        — from season-finish.html (main script)
//    · html2canvas              — from CDN (html2canvas.min.js)
//    · DOM: document, navigator.clipboard, navigator.share
// ═══════════════════════════════════════════════════════


// ═══════════════════════════════════════════════════════
//  INFOGRAPHIC GENERATOR  (Canvas 1080×1080)
// ═══════════════════════════════════════════════════════

// ── Canvas helpers ─────────────────────────────────────
function igRoundRect(ctx, x, y, w, h, r, fill, stroke) {
  const rr = typeof r === 'number' ? [r,r,r,r] : r;
  ctx.beginPath();
  ctx.moveTo(x + rr[0], y);
  ctx.lineTo(x + w - rr[1], y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + rr[1]);
  ctx.lineTo(x + w, y + h - rr[2]);
  ctx.quadraticCurveTo(x + w, y + h, x + w - rr[2], y + h);
  ctx.lineTo(x + rr[3], y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - rr[3]);
  ctx.lineTo(x, y + rr[0]);
  ctx.quadraticCurveTo(x, y, x + rr[0], y);
  ctx.closePath();
  if (fill) ctx.fill();
  if (stroke) ctx.stroke();
}

function igTrunc(ctx, text, maxW) {
  if (ctx.measureText(text).width <= maxW) return text;
  let t = text;
  while (ctx.measureText(t + '…').width > maxW && t.length > 0) t = t.slice(0, -1);
  return t + '…';
}

function igWrapText(ctx, text, x, y, maxW, lh, maxLines) {
  const words = text.split(' ');
  let line = '', count = 0;
  for (const w of words) {
    const test = line + w + ' ';
    if (ctx.measureText(test).width > maxW && line) {
      ctx.fillText(line.trim(), x, y + count * lh);
      line = w + ' '; count++;
      if (count >= maxLines) { ctx.fillText(line.trim() + '…', x, y + count * lh); count++; break; }
    } else { line = test; }
  }
  if (line.trim() && count < maxLines) { ctx.fillText(line.trim(), x, y + count * lh); count++; }
  return count;
}

function igDrawPills(ctx, labels, pillColors, cx, y) {
  if (!labels || !labels.length) return 40;
  ctx.font = 'bold 20px system-ui,sans-serif';
  const pH = 36, pPad = 18, gap = 8;
  const pills = labels.map(l => ({ ...l, w: ctx.measureText(l.l).width + pPad * 2 }));
  const totalW = pills.reduce((s,p) => s + p.w, 0) + gap * (pills.length - 1);
  let sx = cx - totalW / 2;
  for (const p of pills) {
    const pc = pillColors[p.c] || { bg:'#161b22', text:'#8b949e', border:'#30363d' };
    ctx.fillStyle = pc.bg;
    igRoundRect(ctx, sx, y, p.w, pH, pH/2, true, false);
    ctx.strokeStyle = pc.border; ctx.lineWidth = 1.5;
    igRoundRect(ctx, sx, y, p.w, pH, pH/2, false, true);
    ctx.fillStyle = pc.text; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(p.l, sx + p.w/2, y + pH/2);
    sx += p.w + gap;
  }
  ctx.textBaseline = 'alphabetic';
  return pH + 6;
}

// ── Player silhouette helper ────────────────────────────

// ── Form sparkline on canvas ────────────────────────────
function _drawFormSparklineCanvas(ctx, formStr, x, y, w, h, teamColor) {
  const results = (formStr||'').split('').filter(c=>'WDL'.includes(c)).slice(-6);
  const n = results.length;
  // Background track
  ctx.fillStyle = 'rgba(255,255,255,0.05)';
  igRoundRect(ctx, x, y, w, h, 6, true, false);
  if (n < 2) {
    ctx.font = '11px system-ui,sans-serif'; ctx.fillStyle = '#8b949e88';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('Keine Daten', x+w/2, y+h/2);
    ctx.textBaseline = 'alphabetic'; return;
  }
  const pts = results.map(r => r==='W'?1.0:r==='D'?0.5:0.0);
  const padX=10, padY=8;
  const xStep = (w - padX*2) / Math.max(n-1, 1);
  const coords = pts.map((pt,i) => ({
    px: x + padX + i*xStep,
    py: y + padY + (1-pt)*(h - padY*2)
  }));
  // Area fill
  ctx.beginPath();
  coords.forEach((c,i) => i===0 ? ctx.moveTo(c.px,c.py) : ctx.lineTo(c.px,c.py));
  ctx.lineTo(coords[n-1].px, y+h-padY);
  ctx.lineTo(coords[0].px,   y+h-padY);
  ctx.closePath();
  ctx.fillStyle = teamColor + '1a';
  ctx.fill();
  // Line
  ctx.beginPath();
  coords.forEach((c,i) => i===0 ? ctx.moveTo(c.px,c.py) : ctx.lineTo(c.px,c.py));
  ctx.strokeStyle = teamColor + 'cc'; ctx.lineWidth=2; ctx.lineJoin='round'; ctx.stroke();
  // Dots + letters
  const dotC = {W:'#3fb950',D:'#e3b341',L:'#f85149'};
  coords.forEach((c,i) => {
    const r=results[i];
    ctx.beginPath(); ctx.arc(c.px,c.py,4.5,0,Math.PI*2);
    ctx.fillStyle=dotC[r]||'#8b949e'; ctx.fill();
    ctx.font='bold 10px system-ui,sans-serif';
    ctx.fillStyle=(dotC[r]||'#8b949e')+'dd';
    ctx.textAlign='center'; ctx.textBaseline='top';
    ctx.fillText(r, c.px, c.py+7);
  });
  ctx.textBaseline='alphabetic';
}

// ── Pill color config (canvas) ─────────────────────────
function _pillColor(c) {
  return ({
    red:    {bg:'rgba(58,12,12,0.92)',   text:'#f85149', border:'rgba(100,22,22,0.85)'},
    gold:   {bg:'rgba(58,44,0,0.92)',    text:'#f0c040', border:'rgba(100,88,0,0.85)'},
    blue:   {bg:'rgba(10,24,46,0.92)',   text:'#58a6ff', border:'rgba(16,60,150,0.85)'},
    orange: {bg:'rgba(46,20,0,0.92)',    text:'#fb923c', border:'rgba(90,46,0,0.85)'},
    purple: {bg:'rgba(26,10,48,0.92)',   text:'#a78bfa', border:'rgba(76,28,146,0.85)'},
    green:  {bg:'rgba(10,30,16,0.92)',   text:'#3fb950', border:'rgba(16,76,48,0.85)'},
    yellow: {bg:'rgba(44,36,0,0.92)',    text:'#e3b341', border:'rgba(88,72,0,0.85)'},
  })[c] || {bg:'rgba(28,33,40,0.92)', text:'#8b949e', border:'rgba(48,54,61,0.85)'};
}

// ── Infographic text translation DE→EN ──────────────────────
// Applied to pick markets and reason strings drawn on the canvas.
function _igT(s) {
  if (!s) return s;
  return s
    // ── Full sentence patterns (longest/most specific first) ──────────────
    // DNB reason
    .replace(/(.+?) ist Favorit, aber ein Remis ist zu (\d+)% möglich\. DNB \(Draw No Bet\) ist eine Absicherung: bei einem Unentschieden bekommst du den Einsatz zurück — nur bei einer Niederlage verlierst du\./g,
      '$1 are favourites, but a draw occurs $2% of the time. Draw No Bet (DNB) is your safety net: if it draws you get your stake back — only a loss costs you.')
    .replace(/(.+?) ist klarer Favorit, aber ein Remis ist zu (\d+)% möglich\. DNB \(Draw No Bet\) ist eine Absicherung: bei einem Unentschieden bekommst du den Einsatz zurück — nur bei einer Niederlage verlierst du\./g,
      '$1 are clear favourites, but a draw occurs $2% of the time. Draw No Bet (DNB) is your safety net: if it draws you get your stake back — only a loss costs you.')
    // Over 3.5 reason
    .replace(/(.+?) erzielt Ø ([\d.]+) Tore\/Spiel, (.+?) Ø ([\d.]+) — beide Defensiven sind anfällig und lassen viele Gegentore zu\. Das Modell erwartet ([\d.]+) Tore insgesamt: ein Torfestival mit 4\+ Treffern ist klar möglich\./g,
      '$1 avg $2 G/g, $3 avg $4 — both defenses are leaky. Model expects $5 goals total: a 4+ goal festival is very likely.')
    // Over 2.5 reason
    .replace(/(.+?) erzielt Ø ([\d.]+) Tore\/Spiel, (.+?) Ø ([\d.]+) — beide Defensiven lassen regelmäßig Gegentore zu\. Das Modell erwartet ([\d.]+) Tore: mindestens 3 Treffer sind gut möglich\./g,
      '$1 avg $2 G/g, $3 avg $4 — both defenses concede regularly. Model expects $5 goals: 3+ goals are well within reach.')
    // Under 2.5 — dominant team variant
    .replace(/(.+?) dominiert dieses Spiel — der schwächere Angriff \(Ø ([\d.]+) Tore\/Spiel\) kommt kaum zu Chancen\. Weniger als 3 Tore sind zu erwarten\./g,
      '$1 expected to dominate — the weaker attack (avg $2 G/g) will struggle to create chances. Under 3 goals anticipated.')
    // Under 2.5 — both weak variant
    .replace(/Das Modell erwartet nur ([\d.]+) Tore insgesamt — (.+?) \(Ø ([\d.]+) Tore\/Spiel\) und (.+?) \(Ø ([\d.]+)\) sind beide offensiv zu schwach für viele Treffer\./g,
      'Model expects just $1 goals total — $2 (avg $3 G/g) and $4 (avg $5) are both too weak in attack for a high-scoring game.')
    // Under 2.5 — extreme variant
    .replace(/Das Modell erwartet nur ([\d.]+) Tore — beide Teams sind offensiv extrem schwach\. Ein einziger Treffer in diesem Spiel wäre schon viel\./g,
      'Model expects just $1 goals — both teams are extremely weak in attack. Even one goal would be a lot to ask.')
    // BTTS Yes reason
    .replace(/(.+?) \(Ø ([\d.]+) Tore\/Spiel\) und (.+?) \(Ø ([\d.]+)\) treffen beide regelmäßig — beide Defensiven sind anfällig und lassen Gegentore zu\. Beide Teams werden voraussichtlich treffen\./g,
      '$1 (avg $2 G/g) and $3 (avg $4) both score regularly — both defenses are leaky. Both teams are expected to find the net.')
    // BTTS No reason
    .replace(/(.+?) ist offensiv sehr schwach \(Ø ([\d.]+) Tore\/Spiel\) — ein Treffer ist für dieses Team schon eine Herausforderung\. Wahrscheinlich bleibt eines der beiden Teams ohne Tor\./g,
      '$1 are very weak in attack (avg $2 G/g) — even scoring once is a challenge for them. One team likely to keep a clean sheet.')
    // Team over goals — home
    .replace(/(.+?) trifft im Schnitt ([\d.]+) Mal pro Spiel — der Gegner lässt ([\d.]+) Tore zu\. Das Modell erwartet ([\d.]+) Heimtore: mindestens 2 Treffer für (.+?) sind gut möglich\./g,
      '$1 avg $2 goals/game — opponents concede $3. Model expects $4 home goals: 2+ for $5 is very plausible.')
    // Team over goals — away
    .replace(/(.+?) trifft im Schnitt ([\d.]+) Mal pro Spiel — der Gegner lässt ([\d.]+) Tore zu\. Das Modell erwartet ([\d.]+) Auswärtstore: mindestens 2 Treffer für (.+?) sind gut möglich\./g,
      '$1 avg $2 goals/game — opponents concede $3. Model expects $4 away goals: 2+ for $5 is very plausible.')
    // 1st Half under 0.5
    .replace(/Taktisch vorsichtiger Spielbeginn erwartet — beide Teams tasten sich ab\. Das Modell erwartet insgesamt nur ([\d.]+) Tore: ein torloser Start in die erste Halbzeit ist gut möglich\./g,
      'A cautious tactical start expected — both teams feeling each other out. Model expects only $1 total goals: a scoreless first half is plausible.')
    // Corners
    .replace(/Beide Teams spielen offensiv — ca\. (\d+) Ecken werden in diesem Spiel erwartet\. Beide Defensiven sind anfällig, was viele Angriffe und damit viele Ecken begünstigt\./g,
      'Both teams play offensively — est. $1 corners expected. Leaky defenses mean lots of attacks and more set pieces.')
    .replace(/Beide Teams spielen offensiv — ca\. (\d+) Ecken werden in diesem Spiel erwartet\./g,
      'Both teams play offensively — est. $1 corners expected.')
    // Handicap home
    .replace(/(.+?) gewinnt (\d+)% seiner Heimspiele und erzielt dabei im Schnitt ([\d.]+) Tore — ein klarer Heimsieg \(Handicap -0\.5\) ist gut möglich\./g,
      '$1 win $2% of home games, averaging $3 goals — a convincing home win (Handicap -0.5) is very plausible.')
    // Handicap away
    .replace(/(.+?) gewinnt (\d+)% seiner Auswärtsspiele und trifft dabei im Schnitt ([\d.]+) Mal — ein klarer Auswärtssieg \(Handicap -0\.5\) ist gut möglich\./g,
      '$1 win $2% of away games, averaging $3 goals — a convincing away win (Handicap -0.5) is very plausible.')
    // 1st Half BTTS Yes
    .replace(/(.+?) \(Ø ([\d.]+) Tore\/Spiel\) und (.+?) \(Ø ([\d.]+)\) spielen beide offensiv — ein Treffer schon in der ersten Halbzeit ist sehr wahrscheinlich\./g,
      '$1 (avg $2 G/g) and $3 (avg $4) both attack from the off — at least 1 goal in the first half is very likely.')
    .replace(/(.+?) \(Ø ([\d.]+) Tore\/Spiel\) und (.+?) \(Ø ([\d.]+)\) starten offensiv — beide Teams könnten schon in der ersten Halbzeit getroffen haben\./g,
      '$1 (avg $2 G/g) and $3 (avg $4) come out attacking — both teams could score before half time.')
    // 1st Half under
    .replace(/Vorsichtiger Spielbeginn erwartet — beide Teams tasten sich erst ab\. Das Modell erwartet ([\d.]+) Tore insgesamt: in der ersten Halbzeit ist maximal 1 Treffer wahrscheinlich\./g,
      'A cautious start expected — both teams will feel each other out. Model expects $1 goals total: max 1 goal before half time is likely.')
    // Cards — relegation battle
    .replace(/6-Punkte-Kellerduell(.*?) — Verzweiflung, taktische Fouls, emotionale Zweikämpfe\. Historisch >4\.5 Karten\./g,
      'Six-pointer relegation clash$1 — desperation, cynical fouls, heated duels. Historically >4.5 cards.')
    // Pressure amplifier note
    .replace(/Druckspiel(.*?)verstärkt\./g, 'Pressure game$1amplifies this pick.')
    .replace(/Druckspiel(.*?)verstärkt/g, 'Pressure game$1amplifies this pick')
    // ── H2H appendix notes ────────────────────────────────
    .replace(/Historisch Ø ([\d.]+) Tore\/Duell\./g, 'Historically avg $1 goals/meeting.')
    .replace(/Historisch ([\d]+)\/([\d]+) Spielen über 2\.5 Tore\./g, 'Historically $1/$2 meetings over 2.5 goals.')
    .replace(/Historisch ([\d]+)\/([\d]+) Spielen über 3\.5 Tore\./g, 'Historically $1/$2 meetings over 3.5 goals.')
    .replace(/Historisch beide Teams in ([\d]+)\/([\d]+) Duellen getroffen\./g, 'BTTS in $1/$2 previous meetings.')
    .replace(/Historisch nur ([\d]+)\/([\d]+) BTTS-Duelle\./g, 'Only $1/$2 BTTS meetings historically.')
    .replace(/H2H: häufig unter 2\.5 Tore \(([\d]+)\/([\d]+) Spielen\)\./g, 'H2H: frequently under 2.5 goals ($1/$2 games).')
    // ── Markets ───────────────────────────────────────────
    .replace(/\bHeimsiege?\b/g, 'Home Win')
    .replace(/\bAuswärtssieg\b/g, 'Away Win')
    .replace(/\bUnentschieden\b/g, 'Draw')
    .replace(/[Üü]ber ([\d,.]+) Tore/g, 'Over $1 Goals')
    .replace(/[Uu]nter ([\d,.]+) Tore/g, 'Under $1 Goals')
    .replace(/Beide Teams treffen: Nein/g, 'Both Teams Score: No')
    .replace(/Beide Teams treffen: Ja/g, 'Both Teams Score: Yes')
    .replace(/Beide Teams treffen\b/g, 'Both Teams Score')
    .replace(/\b1\. HZ:/g, '1st Half:')
    .replace(/\b([A-Za-zÄÖÜäöüß ]+) über ([\d,.]+) Tore/g, '$1 Over $2 Goals')
    // ── Word-level fallbacks ──────────────────────────────
    .replace(/Torfestival erwartet/g, 'Goal fest expected')
    .replace(/Wenig Tore erwartet/g, 'Low-scoring game expected')
    .replace(/Extrem torarm/g, 'Extremely low-scoring')
    .replace(/Angriff trifft auf offene Abwehren\./g, 'Attack meets open defense.')
    .replace(/Beide Angriffe stark/g, 'Both attacks strong')
    .replace(/Beide Abwehren permissiv/g, 'Both defenses leaky')
    .replace(/kaum torgefährlich/g, 'barely dangerous in front of goal')
    .replace(/siegt defensiv/g, 'wins defensively')
    .replace(/schwächerer Angriff/g, 'weaker attack')
    .replace(/lässt wenig Tore zu/g, 'concedes few goals')
    .replace(/greift voll an/g, 'attacks fully')
    .replace(/geht volles Risiko/g, 'goes all-in')
    .replace(/Heimteam greift voll an/g, 'Home team attacks fully')
    .replace(/Auswärtsteam geht volles Risiko/g, 'Away team goes all-in')
    .replace(/unter Druck/g, 'under pressure')
    .replace(/Beide Teams\b/g, 'Both teams')
    .replace(/\bHeimteam\b/g, 'Home team')
    .replace(/\bAuswärtsteam\b/g, 'Away team')
    .replace(/muss gewinnen/g, 'must win')
    .replace(/Historisch /g, 'Historically ')
    .replace(/ Duelle\b/g, ' meetings')
    .replace(/presst von Minute 1/g, 'pressing from minute 1')
    .replace(/erhöht früh-Tor-Wahrscheinlichkeit/g, 'increases early goal probability')
    .replace(/erhöht frühe BTTS-Wahrscheinlichkeit/g, 'increases early BTTS probability')
    .replace(/Pressingspiel von Beginn/g, 'High-press game from the start')
    .replace(/intensives Pressing treibt Eckenzahl/g, 'pressing drives corner count')
    .replace(/ca\. (\d+) Ecken erwartet/g, 'est. $1 corners')
    .replace(/ca\.? ?(\d+) Karten erwartet/g, 'est. $1 cards expected')
    .replace(/kassieren ([\d.]+) \/ ([\d.]+)/g, 'concede $1 / $2')
    .replace(/kassieren/g, 'concede')
    // Stats suffixes
    .replace(/xG\/Sp\b/g, 'xG/g')
    .replace(/T\/Sp\b/g, 'G/g')
    .replace(/Tore\/Spiel\b/g, 'G/g')
    .replace(/Tore\/Sp\b/g, 'G/g')
    .replace(/\bTore\b/g, 'Goals')
    .replace(/Ø ([\d.]+) EG\b/g, 'Avg $1 EG')
    .replace(/Ø ([\d.]+)/g, 'avg $1')
    // H2H snippets (fallback)
    .replace(/H2H: (\d+)H\/(\d+)U\/(\d+)A/g, 'H2H: $1W/$2D/$3A')
    .replace(/avg ([\d.]+) goals\/match/g, 'avg $1 goals/match')
    .replace(/avg ([\d.]+) G\/g/g, 'avg $1 G/g')
    .replace(/der ([\d]+) Duelle/g, 'of $1 meetings')
    .replace(/unter 2\.5 Tore/g, 'under 2.5 Goals')
    ;
}

// ── Infographic generator — 1080×1920px Social Media (9:16) ──
function generateInfographic(matchJson, leagueName, leagueFlag, leagueKey) {
  const match  = JSON.parse(decodeURIComponent(matchJson));
  const score  = computeMatchScore(match, leagueKey);
  const angle  = getBettingAngle(match);
  const odds   = leagueKey ? findOdds(leagueKey, match.home, match.away) : null;
  const oddsD  = deriveOdds(odds || {});
  // Context: rest days + injuries (mirrors card logic)
  const _igFix   = leagueKey ? (LEAGUES[leagueKey]?.fixtures || []) : [];
  const _igHRest = getRestDays(match.home, match.date, _igFix);
  const _igARest = getRestDays(match.away, match.date, _igFix);
  const _igHInj  = _missToInjDisplay(match.homeSquad?.missingStarters ?? match.homeStake?.missingStarters)
                   || match.homeForm?.injuries || null;
  const _igAInj  = _missToInjDisplay(match.awaySquad?.missingStarters ?? match.awayStake?.missingStarters)
                   || match.awayForm?.injuries || null;
  // ── Context badges (mirrors card logic) ─────────────────
  const _igCtxBadges = [];
  // Fatigue — English text for infographic
  if (_igHRest != null && _igHRest <= 5) _igCtxBadges.push({text:`😴 Short rest: ${match.home} (${_igHRest}d)`, col:_igHRest<=3?'#f85149':'#e3b341'});
  if (_igARest != null && _igARest <= 5) _igCtxBadges.push({text:`😴 Short rest: ${match.away} (${_igARest}d)`, col:_igARest<=3?'#f85149':'#e3b341'});
  // Injuries — player names like card (English labels)
  const _igBuildInj = (inj, teamName) => {
    if (!inj || (inj.total||0) === 0) return null;
    const imp = inj.impactScore || 0;
    if (imp < 0.3 && (inj.confirmed||0) === 0) return null;
    const col = imp >= 3.5 ? '#f85149' : imp >= 2.0 ? '#e3b341' : '#a78bfa';
    const confirmed = (inj._raw || []).filter(p => p.type === 'Missing Fixture');
    const names = confirmed.slice(0, 2).map(p => p.player.split(' ').slice(-1)[0]);
    const nameStr = names.length ? names.join(', ') + (confirmed.length > 2 ? ` +${confirmed.length - 2}` : '') : '';
    const areaMap = [];
    if ((inj.goalkeeper||0) > 0) areaMap.push('GK');
    if ((inj.attack||0)     > 0) areaMap.push(`${inj.attack} att`);
    if ((inj.defense||0)    > 0) areaMap.push(`${inj.defense} def`);
    if ((inj.midfield||0)   > 0) areaMap.push(`${inj.midfield} mid`);
    const areaStr = areaMap.length ? ` · ${areaMap.slice(0,3).join('/')}` : '';
    const label = nameStr ? `${nameStr} out${areaStr}` : `${inj.total} missing${areaStr}`;
    return {text:`🏥 ${teamName}: ${label}`, col};
  };
  const _igHInjB = _igBuildInj(_igHInj, match.home);
  const _igAInjB = _igBuildInj(_igAInj, match.away);
  if (_igHInjB) _igCtxBadges.push(_igHInjB);
  if (_igAInjB) _igCtxBadges.push(_igAInjB);
  // Referee
  const _igRef = match.refereeStats || null;
  if (_igRef?.name) {
    const avg = _igRef.avgCards;
    const refCol = avg == null ? '#8b949e' : avg >= 4.5 ? '#f85149' : avg >= 3.5 ? '#e3b341' : '#3fb950';
    const avgNote = avg != null ? ` · Ø ${avg} cards/g` : '';
    _igCtxBadges.push({text:`👨‍⚖️ Referee: ${_igRef.name}${avgNote}`, col:refCol});
  }
  const _igHasCtx = _igCtxBadges.length > 0;
  // Only show high/medium confidence picks in the infographic — low conf = not worth sharing
  const picks  = getBettingPicks(match, oddsD, leagueKey)
    .filter(p => p.conf === 'high' || p.conf === 'medium')
    .slice(0, 3);
  const hLabels = match.homeStake?.labels || [];
  const aLabels = match.awayStake?.labels || [];

  const teamColor = (labels) => {
    const cs = labels.map(l=>l.c);
    if (cs.includes('red'))    return {main:'#f85149', soft:'rgba(248,81,73,'};
    if (cs.includes('gold'))   return {main:'#f0c040', soft:'rgba(240,192,64,'};
    if (cs.includes('blue'))   return {main:'#58a6ff', soft:'rgba(88,166,255,'};
    if (cs.includes('orange')) return {main:'#fb923c', soft:'rgba(251,146,60,'};
    if (cs.includes('purple')) return {main:'#a78bfa', soft:'rgba(167,139,250,'};
    return {main:'#00d4a1', soft:'rgba(0,212,161,'};
  };
  const hC = teamColor(hLabels), aC = teamColor(aLabels);
  const scoreColor = score>=9?'#f85149':score>=7?'#3fb950':'#e3b341';

  // ── Height calculation (new layout) ─────────────────────────────────────────
  const _rl_ig  = match.roundsLeft ?? 99;
  const _hasH2H = match.h2h && match.h2h.games >= 3;
  const _anyNW  = (_rl_ig<=6) && (hLabels.length>0 || aLabels.length>0);
  let _estH = 80    // header bar
            + 180   // teams + pills
            + (odds?.hw ? 74 : 0)  // odds strip (now above stats)
            + 200   // stats grid
            + (_hasH2H ? 170 : 0)
            + (_anyNW  ? 90 : 0)   // compact stakes
            + (_igCtxBadges.length ? 60 : 0)
            + 60    // picks section header
            + (picks.length > 0 ? 200 : 0)  // 3-across pick cards (single row)
            + 100;  // footer
  _estH = Math.max(1080, _estH);

  const W=1080, H=_estH;
  const canvas=document.createElement('canvas');
  canvas.width=W; canvas.height=H;
  const ctx=canvas.getContext('2d');

  // ═══════════════════════════════════════════════════════════════════
  // NEW INFOGRAPHIC DESIGN — inspired by professional football graphics
  // ═══════════════════════════════════════════════════════════════════

  // ── Drawing helpers ────────────────────────────────────────────────
  const sec = (title, y, accentCol) => {
    ctx.save();
    // Section accent line left
    ctx.fillStyle = accentCol || '#00d4a1';
    ctx.fillRect(48, y+4, 4, 22);
    ctx.font = 'bold 18px system-ui,sans-serif';
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillStyle = '#e6edf3';
    ctx.fillText(title.toUpperCase(), 60, y+15);
    // Full-width thin rule under header
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(48,y+32); ctx.lineTo(W-48,y+32); ctx.stroke();
    ctx.restore();
    return y+44;
  };

  const statRing = (cx, cy, r, pct, ringCol, valText, labelText, valSize) => {
    const start = -Math.PI/2, end = start + Math.PI*2*Math.min(1,Math.max(0,pct));
    // BG ring
    ctx.save();
    ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2);
    ctx.strokeStyle='rgba(255,255,255,0.10)'; ctx.lineWidth=r*0.22; ctx.stroke();
    // Fill ring
    if (pct > 0) {
      ctx.beginPath(); ctx.arc(cx,cy,r,start,end);
      ctx.strokeStyle=ringCol; ctx.lineWidth=r*0.22;
      ctx.lineCap='round'; ctx.stroke();
      // Glow
      ctx.shadowColor=ringCol; ctx.shadowBlur=12;
      ctx.beginPath(); ctx.arc(cx,cy,r,start,end);
      ctx.stroke(); ctx.shadowBlur=0;
    }
    // Value text
    ctx.font = `bold ${valSize||28}px system-ui,sans-serif`;
    ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillStyle='#ffffff'; ctx.fillText(valText, cx, cy-8);
    // Label below
    ctx.font = '13px system-ui,sans-serif';
    ctx.fillStyle = 'rgba(255,255,255,0.55)';
    ctx.fillText(labelText, cx, cy+14);
    ctx.restore();
  };

  const pill2 = (lb, cx, y) => {
    const pc = _pillColor(lb.c);
    ctx.font = 'bold 15px system-ui,sans-serif';
    const tw = ctx.measureText(lb.l).width, pw=tw+20, ph=28;
    igRoundRect(ctx,cx-pw/2,y,pw,ph,14,true,false);
    ctx.fillStyle=pc.bg; igRoundRect(ctx,cx-pw/2,y,pw,ph,14,true,false);
    ctx.strokeStyle=pc.border; ctx.lineWidth=1; igRoundRect(ctx,cx-pw/2,y,pw,ph,14,false,true);
    ctx.fillStyle=pc.text; ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillText(lb.l,cx,y+ph/2); ctx.textBaseline='alphabetic';
    return ph+6;
  };

  // ── BACKGROUND ──────────────────────────────────────────────────────
  // Deep dark gradient
  const bg = ctx.createLinearGradient(0,0,W,H);
  bg.addColorStop(0,'#060a0f'); bg.addColorStop(0.5,'#0b1018'); bg.addColorStop(1,'#060a10');
  ctx.fillStyle=bg; ctx.fillRect(0,0,W,H);

  // Team color atmosphere glows
  const glowH = ctx.createRadialGradient(0,H*0.35,0,0,H*0.35,W*0.65);
  glowH.addColorStop(0,hC.soft+'0.22)'); glowH.addColorStop(1,'transparent');
  ctx.fillStyle=glowH; ctx.fillRect(0,0,W,H);
  const glowA = ctx.createRadialGradient(W,H*0.35,0,W,H*0.35,W*0.65);
  glowA.addColorStop(0,aC.soft+'0.22)'); glowA.addColorStop(1,'transparent');
  ctx.fillStyle=glowA; ctx.fillRect(0,0,W,H);

  // Dot grid
  ctx.fillStyle='rgba(255,255,255,0.016)';
  for(let gx=54;gx<W;gx+=54) for(let gy=54;gy<H;gy+=54){
    ctx.beginPath();ctx.arc(gx,gy,1.3,0,Math.PI*2);ctx.fill();
  }

  // Outer rounded border (gradient: home color → away color)
  ctx.save();
  const brdG=ctx.createLinearGradient(0,0,W,0);
  brdG.addColorStop(0,hC.main+'90'); brdG.addColorStop(0.5,'rgba(48,54,61,0.6)'); brdG.addColorStop(1,aC.main+'90');
  ctx.strokeStyle=brdG; ctx.lineWidth=2.5;
  igRoundRect(ctx,10,10,W-20,H-20,22,false,true);
  ctx.restore();

  // ── HEADER BAR (y 10 → 80) ──────────────────────────────────────────
  const hdrG = ctx.createLinearGradient(10,10,W-10,10);
  hdrG.addColorStop(0,hC.main+'28'); hdrG.addColorStop(0.5,'rgba(22,27,34,0.92)'); hdrG.addColorStop(1,aC.main+'28');
  igRoundRect(ctx,10,10,W-20,66,[22,22,0,0],true,false);
  ctx.fillStyle=hdrG; igRoundRect(ctx,10,10,W-20,66,[22,22,0,0],true,false);
  // Accent bars under header
  const ab1=ctx.createLinearGradient(10,0,W/2,0);
  ab1.addColorStop(0,hC.main); ab1.addColorStop(1,'transparent');
  ctx.fillStyle=ab1; ctx.fillRect(10,74,W/2-10,3);
  const ab2=ctx.createLinearGradient(W,0,W/2,0);
  ab2.addColorStop(0,aC.main); ab2.addColorStop(1,'transparent');
  ctx.fillStyle=ab2; ctx.fillRect(W/2,74,W/2-10,3);
  // League + date text (adaptive: shrink font if league name is long)
  ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillStyle='#e6edf3';
  const _lgText = `${leagueFlag}  ${leagueName}`;
  let _lgFz = 20; ctx.font=`bold ${_lgFz}px system-ui,sans-serif`;
  while (_lgFz > 13 && ctx.measureText(_lgText).width > W-200) { _lgFz--; ctx.font=`bold ${_lgFz}px system-ui,sans-serif`; }
  ctx.fillText(_lgText, W/2, 38);
  ctx.font='13px system-ui,sans-serif'; ctx.fillStyle='rgba(200,210,220,0.55)';
  ctx.fillText(`${match.date}  ·  Matchday Analysis`, W/2, 60);

  // ── TEAMS SECTION ────────────────────────────────────────────────────
  let curY = 90;
  // Adaptive font: start at 46px, scale down until name fits in 420px column
  const _tnFit = (text, maxW) => {
    let sz = 46; ctx.font=`bold ${sz}px system-ui,sans-serif`;
    while (sz > 22 && ctx.measureText(text).width > maxW) { sz -= 2; ctx.font=`bold ${sz}px system-ui,sans-serif`; }
    return sz;
  };
  const _tnSz = Math.min(_tnFit(match.home, 420), _tnFit(match.away, 420));
  // Home team name
  ctx.save();
  const hTG = ctx.createLinearGradient(40,0,500,0);
  hTG.addColorStop(0,'#ffffff'); hTG.addColorStop(1,hC.main+'bb');
  ctx.fillStyle=hTG; ctx.font=`bold ${_tnSz}px system-ui,sans-serif`;
  ctx.textAlign='center'; ctx.textBaseline='alphabetic';
  ctx.fillText(igTrunc(ctx,match.home,420), W*0.25, curY+58);
  ctx.restore();
  // Away team name
  ctx.save();
  const aTG = ctx.createLinearGradient(W-40,0,W-500,0);
  aTG.addColorStop(0,'#ffffff'); aTG.addColorStop(1,aC.main+'bb');
  ctx.fillStyle=aTG; ctx.font=`bold ${_tnSz}px system-ui,sans-serif`;
  ctx.textAlign='center'; ctx.textBaseline='alphabetic';
  ctx.fillText(igTrunc(ctx,match.away,420), W*0.75, curY+58);
  ctx.restore();
  // VS center circle (smaller, proportional)
  const vsR=34;
  ctx.save();
  const vsG=ctx.createRadialGradient(W/2,curY+32,0,W/2,curY+32,vsR*2.5);
  vsG.addColorStop(0,'rgba(0,212,161,0.14)'); vsG.addColorStop(1,'transparent');
  ctx.fillStyle=vsG; ctx.fillRect(0,0,W,H);
  igRoundRect(ctx,W/2-vsR,curY+32-vsR,vsR*2,vsR*2,vsR,false,true);
  ctx.strokeStyle='rgba(255,255,255,0.18)'; ctx.lineWidth=1.5;
  igRoundRect(ctx,W/2-vsR,curY+32-vsR,vsR*2,vsR*2,vsR,false,true);
  ctx.font='bold 20px system-ui,sans-serif'; ctx.fillStyle='rgba(255,255,255,0.85)';
  ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText('VS', W/2, curY+32);
  ctx.restore();
  curY += 72;
  // Pressure pills
  let hPY = curY, aPY = curY;
  for(const lb of hLabels.slice(0,2)) hPY+=pill2(lb,W*0.25,hPY);
  for(const lb of aLabels.slice(0,2)) aPY+=pill2(lb,W*0.75,aPY);
  curY = Math.max(hPY,aPY)+20;

  // ── ODDS STRIP (Home / Draw / Away — moved above stats) ─────────────
  if (odds?.hw) {
    curY += 8;
    const _cw3 = (W-96)/3;
    const _o3 = [
      {lbl:'Home Win', val:odds.hw?.toFixed(2)||'–', col:hC.main},
      {lbl:'Draw',     val:odds.dr?.toFixed(2)||'–', col:'#8b949e'},
      {lbl:'Away Win', val:odds.aw?.toFixed(2)||'–', col:aC.main},
    ];
    _o3.forEach((o,i)=>{
      const ox=48+i*_cw3+_cw3/2, bx=48+i*_cw3+4;
      igRoundRect(ctx,bx,curY,_cw3-8,56,10,true,false);
      ctx.fillStyle='rgba(18,22,30,0.80)'; igRoundRect(ctx,bx,curY,_cw3-8,56,10,true,false);
      ctx.strokeStyle=o.col+'35'; ctx.lineWidth=1; igRoundRect(ctx,bx,curY,_cw3-8,56,10,false,true);
      ctx.font='bold 26px system-ui,sans-serif'; ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillStyle=o.col; ctx.fillText(o.val, ox, curY+24);
      ctx.font='12px system-ui,sans-serif'; ctx.fillStyle='rgba(139,148,158,0.70)'; ctx.textBaseline='middle';
      ctx.fillText(o.lbl, ox, curY+44);
    });
    curY += 68;
  }

  // ── THIN DIVIDER ────────────────────────────────────────────────────
  ctx.strokeStyle='rgba(255,255,255,0.07)'; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(48,curY); ctx.lineTo(W-48,curY); ctx.stroke();
  curY += 20;

  // ── TEAM STATS GRID (3 rings per side, inspired by example 1) ───────
  curY = sec('TEAM STATS', curY, '#00d4a1');
  curY += 10;
  const hForm = match.homeForm || {}, aForm = match.awayForm || {};
  const hGPG  = hForm.goalsPerGame ?? 1.3, aGPG = aForm.goalsPerGame ?? 1.0;
  const hWR   = hForm.homeWinRate  ?? 0.5, aWR  = aForm.awayWinRate  ?? 0.35;
  const hFS   = hForm.formScore    ?? 0.5, aFS  = aForm.formScore    ?? 0.5;
  const rRad  = 52;
  const statsY = curY + rRad + 10;
  // Col positions: 3 columns each side
  const hCols = [148, 268, 388], aCols = [W-148, W-268, W-388];
  // Home side rings
  statRing(hCols[0],statsY,rRad, hFS,        hC.main, `${Math.round(hFS*100)}%`,  'Form',    22);
  statRing(hCols[1],statsY,rRad, hGPG/4,     '#3fb950', hGPG.toFixed(1),          'Goals/G', 22);
  statRing(hCols[2],statsY,rRad, hWR,        '#58a6ff', `${Math.round(hWR*100)}%`,'Home W%', 22);
  // Away side rings
  statRing(aCols[0],statsY,rRad, aFS,        aC.main, `${Math.round(aFS*100)}%`,  'Form',    22);
  statRing(aCols[1],statsY,rRad, aGPG/4,     '#3fb950', aGPG.toFixed(1),          'Goals/G', 22);
  statRing(aCols[2],statsY,rRad, aWR,        '#58a6ff', `${Math.round(aWR*100)}%`,'Away W%', 22);
  // Center label: match score
  const scoreRad = 40;
  ctx.save();
  ctx.beginPath(); ctx.arc(W/2,statsY,scoreRad,0,Math.PI*2);
  ctx.fillStyle='rgba(22,27,34,0.92)'; ctx.fill();
  ctx.strokeStyle=scoreColor+'80'; ctx.lineWidth=2; ctx.stroke();
  ctx.font='bold 13px system-ui,sans-serif'; ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillStyle='rgba(200,210,220,0.6)'; ctx.fillText('SCORE', W/2, statsY-13);
  ctx.font='bold 28px system-ui,sans-serif'; ctx.fillStyle=scoreColor;
  ctx.fillText(score.toFixed(1), W/2, statsY+6);
  ctx.restore();
  curY = statsY + rRad + 24;

  // ── H2H SECTION ─────────────────────────────────────────────────────
  if (_hasH2H) {
    curY += 8;
    ctx.strokeStyle='rgba(255,255,255,0.07)'; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(48,curY); ctx.lineTo(W-48,curY); ctx.stroke();
    curY += 16;
    curY = sec('HEAD TO HEAD', curY, hC.main);
    curY += 12;
    const h2h = match.h2h;
    const n = h2h.games, hw = h2h.homeWins||0, dr = h2h.draws||0, aw = h2h.awayWins||0;
    const barW = W-160, barH = 36, barX = 80, barY = curY;
    const pH = n>0?hw/n:0, pD = n>0?dr/n:0, pA = n>0?aw/n:0;
    // Background track
    igRoundRect(ctx,barX,barY,barW,barH,barH/2,true,false);
    ctx.fillStyle='rgba(255,255,255,0.07)'; igRoundRect(ctx,barX,barY,barW,barH,barH/2,true,false);
    // Home wins
    if(pH>0){igRoundRect(ctx,barX,barY,barW*pH,barH,[barH/2,0,0,barH/2],true,false);
      const hBG=ctx.createLinearGradient(barX,0,barX+barW*pH,0);
      hBG.addColorStop(0,hC.main); hBG.addColorStop(1,hC.main+'99');
      ctx.fillStyle=hBG; igRoundRect(ctx,barX,barY,barW*pH,barH,[barH/2,0,0,barH/2],true,false);}
    // Draws (center)
    if(pD>0){const dX=barX+barW*pH;
      ctx.fillStyle='rgba(139,148,158,0.70)'; ctx.fillRect(dX,barY,barW*pD,barH);}
    // Away wins
    if(pA>0){const aX=barX+barW*(pH+pD);const aW=barW*pA;
      igRoundRect(ctx,aX,barY,aW,barH,[0,barH/2,barH/2,0],true,false);
      const aBG=ctx.createLinearGradient(aX,0,aX+aW,0);
      aBG.addColorStop(0,aC.main+'99'); aBG.addColorStop(1,aC.main);
      ctx.fillStyle=aBG; igRoundRect(ctx,aX,barY,aW,barH,[0,barH/2,barH/2,0],true,false);}
    // Labels inside/below bar
    ctx.font='bold 20px system-ui,sans-serif'; ctx.textBaseline='middle';
    if(pH>0.12){ctx.fillStyle='rgba(0,0,0,0.7)';ctx.textAlign='left';
      ctx.fillText(`${hw}W`,barX+14,barY+barH/2);}
    if(pD>0.08){ctx.fillStyle='rgba(0,0,0,0.7)';ctx.textAlign='center';
      ctx.fillText(`${dr}D`,barX+barW*(pH+pD/2),barY+barH/2);}
    if(pA>0.12){ctx.fillStyle='rgba(0,0,0,0.7)';ctx.textAlign='right';
      ctx.fillText(`${aw}W`,barX+barW-14,barY+barH/2);}
    // Team labels + avg goals below
    curY = barY+barH+12;
    ctx.font='13px system-ui,sans-serif'; ctx.textBaseline='alphabetic';
    ctx.fillStyle=hC.main; ctx.textAlign='left'; ctx.fillText(igTrunc(ctx,match.home,280),barX,curY+14);
    ctx.fillStyle='rgba(139,148,158,0.8)'; ctx.textAlign='center';
    const avgG = (h2h.avgGoals||0).toFixed(1);
    ctx.fillText(`${n} Spiele · Ø ${avgG} Goals`,W/2,curY+14);
    ctx.fillStyle=aC.main; ctx.textAlign='right'; ctx.fillText(igTrunc(ctx,match.away,280),barX+barW,curY+14);
    curY += 34;
  }

  // ── SEASON STAKES (2-column compact badges) ─────────────────────────
  if (_anyNW) {
    curY += 10;
    ctx.strokeStyle='rgba(255,255,255,0.07)'; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(48,curY); ctx.lineTo(W-48,curY); ctx.stroke();
    curY += 16;
    curY = sec('SEASON STAKES', curY, '#f0c040');
    curY += 10;

    const _colHalfW = (W-96)/2 - 8;
    const _stakeColY0 = curY;

    const _drawStakeCol = (stake, teamName, tColor, isLeft) => {
      if (!stake || !stake.labels?.length) return 0;
      const bx0 = isLeft ? 48 : 48 + (W-96)/2 + 8;
      let sy = _stakeColY0;
      // Team name header
      ctx.font='bold 13px system-ui,sans-serif'; ctx.textAlign='left'; ctx.textBaseline='alphabetic';
      ctx.fillStyle=tColor;
      ctx.fillText(igTrunc(ctx,teamName,_colHalfW-4), bx0, sy+13);
      sy += 20;
      // Must-win badge (if applicable)
      let bx = bx0;
      if (stake.mustWin) {
        const mwT='🔥 MUST WIN';
        ctx.font='bold 11px system-ui,sans-serif';
        const mwW=ctx.measureText(mwT).width+14, mwH=22;
        igRoundRect(ctx,bx,sy,mwW,mwH,5,true,false);
        ctx.fillStyle='rgba(248,81,73,0.22)'; igRoundRect(ctx,bx,sy,mwW,mwH,5,true,false);
        ctx.strokeStyle='#f8514980'; ctx.lineWidth=1; igRoundRect(ctx,bx,sy,mwW,mwH,5,false,true);
        ctx.fillStyle='#f85149'; ctx.textAlign='center'; ctx.textBaseline='middle';
        ctx.fillText(mwT,bx+mwW/2,sy+mwH/2);
        bx += mwW+6;
      }
      // Label badges (inline, wrap to next row if needed)
      for (const lb of (stake.labels||[]).slice(0,4)) {
        const pc=_pillColor(lb.c);
        ctx.font='bold 11px system-ui,sans-serif';
        const pw=ctx.measureText(lb.l).width+14, ph=22;
        if (bx+pw > bx0+_colHalfW) { bx=bx0; sy+=28; } // wrap
        igRoundRect(ctx,bx,sy,pw,ph,5,true,false); ctx.fillStyle=pc.bg;
        igRoundRect(ctx,bx,sy,pw,ph,5,true,false); ctx.strokeStyle=pc.border; ctx.lineWidth=1;
        igRoundRect(ctx,bx,sy,pw,ph,5,false,true); ctx.fillStyle=pc.text;
        ctx.textAlign='center'; ctx.textBaseline='middle';
        ctx.fillText(lb.l,bx+pw/2,sy+ph/2); ctx.textBaseline='alphabetic';
        bx+=pw+5;
      }
      return (sy+28) - _stakeColY0;
    };

    const _hSH = _drawStakeCol(match.homeStake, match.home, hC.main, true);
    const _aSH = _drawStakeCol(match.awayStake, match.away, aC.main, false);
    const _stakeH = Math.max(_hSH, _aSH, 0);

    // Rounds remaining — subtle center note
    if (_stakeH > 0 && _rl_ig <= 99) {
      ctx.font='11px system-ui,sans-serif'; ctx.textAlign='center'; ctx.textBaseline='alphabetic';
      ctx.fillStyle='rgba(139,148,158,0.55)';
      ctx.fillText(`${_rl_ig} matchdays remaining`, W/2, _stakeColY0+_stakeH+14);
    }
    curY = _stakeColY0 + _stakeH + (_stakeH>0 ? 26 : 0);
  }

  // ── CONTEXT STRIP (injuries/fatigue/referee) ─────────────────────────
  if (_igCtxBadges.length) {
    curY += 8;
    ctx.strokeStyle='rgba(255,255,255,0.07)'; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(48,curY); ctx.lineTo(W-48,curY); ctx.stroke();
    curY += 16;
    ctx.font = '14px system-ui,sans-serif'; ctx.textAlign='left'; ctx.textBaseline='alphabetic';
    for (const b of _igCtxBadges) {
      ctx.fillStyle = b.col || '#8b949e';
      ctx.fillText(igTrunc(ctx,b.text,W-100), 60, curY+14);
      curY += 24;
    }
    curY += 6;
  }

  // ── PICKS SECTION (3-across cards) ──────────────────────────────────
  curY += 10;
  ctx.strokeStyle='rgba(255,255,255,0.07)'; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(48,curY); ctx.lineTo(W-48,curY); ctx.stroke();
  curY += 16;
  curY = sec('TOP BETS', curY, scoreColor);
  curY += 16;

  const _pickConfCol = {high:'#3fb950',medium:'#e3b341',low:'#8b949e'};

  if (picks.length > 0) {
    const _nP = picks.length; // 1–3
    const _pcGap = 12;
    const _pcW = Math.floor((W - 96 - _pcGap*(_nP-1)) / _nP);
    const _pcH = 185;
    const _pcRowY = curY;

    // Abbreviate market name for compact card
    const _abbrMkt = (market) => {
      let t = _igT(market);
      const subs = [
        ['Beide treffen','BTTS'],['Keine beider','No BTTS'],
        ['Auswärtssieg','Auswärts'],['Unentschieden','Unentsch.'],
        ['Torschüsse','Schüsse'],['Strafecke','Ecke'],
      ];
      for (const [f,r] of subs) t=t.replace(f,r);
      return t.length>15 ? t.slice(0,13)+'…' : t;
    };

    picks.forEach((p, pi) => {
      const _px = 48 + pi*(_pcW+_pcGap);
      const _confCol = _pickConfCol[p.conf]||'#e3b341';
      // POTD = first pick; hot value picks get red accent
      const _isTopPick = pi===0;
      const _accent = p.value==='hot' ? '#f85149' : p.value==='value' ? '#3fb950' : _confCol;
      const _borderAlpha = _isTopPick ? 'aa' : '55';

      // Card bg
      igRoundRect(ctx,_px,_pcRowY,_pcW,_pcH,14,true,false);
      ctx.fillStyle='rgba(15,19,26,0.97)'; igRoundRect(ctx,_px,_pcRowY,_pcW,_pcH,14,true,false);
      // Colored border (green for high conf, yellow for medium)
      ctx.strokeStyle=_confCol+_borderAlpha; ctx.lineWidth=_isTopPick?2:1.5;
      igRoundRect(ctx,_px,_pcRowY,_pcW,_pcH,14,false,true);
      // Top accent bar (full width, 4px)
      igRoundRect(ctx,_px,_pcRowY,_pcW,4,[14,14,0,0],true,false);
      ctx.fillStyle=_accent; igRoundRect(ctx,_px,_pcRowY,_pcW,4,[14,14,0,0],true,false);

      // "TOP PICK" floating tab above first card
      if (_isTopPick) {
        const _tpLbl='★ TOP PICK';
        ctx.font='bold 11px system-ui,sans-serif';
        const _tpW=ctx.measureText(_tpLbl).width+16, _tpH=20;
        igRoundRect(ctx,_px+12,_pcRowY-_tpH+2,_tpW,_tpH,[4,4,0,0],true,false);
        ctx.fillStyle=_confCol; igRoundRect(ctx,_px+12,_pcRowY-_tpH+2,_tpW,_tpH,[4,4,0,0],true,false);
        ctx.fillStyle='#000'; ctx.textAlign='center'; ctx.textBaseline='middle';
        ctx.fillText(_tpLbl,_px+12+_tpW/2,_pcRowY-_tpH/2+2);
      }

      // Confidence ring (top-right corner)
      const _cRX=_px+_pcW-36, _cRY=_pcRowY+42;
      const _confPct=p.conf==='high'?1:p.conf==='medium'?0.67:0.33;
      const _confLbl=p.conf==='high'?'HIGH':p.conf==='medium'?'MED':'LOW';
      statRing(_cRX,_cRY,26,_confPct,_confCol,_confLbl,'CONF',9);

      // Icon + market name
      ctx.font='24px system-ui,sans-serif'; ctx.textAlign='left'; ctx.textBaseline='middle';
      ctx.fillText(p.icon||'🎲',_px+14,_pcRowY+36);
      ctx.font=`bold ${_pcW<280?14:16}px system-ui,sans-serif`; ctx.fillStyle='#e6edf3';
      ctx.textAlign='left'; ctx.textBaseline='alphabetic';
      ctx.fillText(igTrunc(ctx,_abbrMkt(p.market),_pcW-80),_px+46,_pcRowY+44);

      // Odds badge
      if (p.odds) {
        const _oStr=`@ ${p.odds.toFixed(2)}`;
        ctx.font='bold 22px system-ui,sans-serif';
        const _oW=ctx.measureText(_oStr).width+16;
        igRoundRect(ctx,_px+12,_pcRowY+56,_oW,36,8,true,false);
        ctx.fillStyle=_accent+'28'; igRoundRect(ctx,_px+12,_pcRowY+56,_oW,36,8,true,false);
        ctx.strokeStyle=_accent+'60'; ctx.lineWidth=1; igRoundRect(ctx,_px+12,_pcRowY+56,_oW,36,8,false,true);
        ctx.fillStyle=_accent; ctx.textAlign='center'; ctx.textBaseline='middle';
        ctx.fillText(_oStr,_px+12+_oW/2,_pcRowY+74);
      }

      // FV chip (small, below odds)
      if (p.modelOdds) {
        ctx.font='11px system-ui,sans-serif'; ctx.fillStyle='rgba(139,148,158,0.60)';
        ctx.textAlign='left'; ctx.textBaseline='alphabetic';
        ctx.fillText(`FV ${p.modelOdds}`,_px+14,_pcRowY+105);
      }

      // Value badge (hot/value) — bottom-right
      if (p.value==='hot'||p.value==='value') {
        const _vLbl=p.value==='hot'?'🔥 HOT':'💰 VALUE';
        ctx.font='bold 10px system-ui,sans-serif';
        const _vW=ctx.measureText(_vLbl).width+12, _vH=18;
        igRoundRect(ctx,_px+_pcW-_vW-10,_pcRowY+_pcH-_vH-10,_vW,_vH,4,true,false);
        ctx.fillStyle=p.value==='hot'?'rgba(248,81,73,0.22)':'rgba(63,185,80,0.18)';
        igRoundRect(ctx,_px+_pcW-_vW-10,_pcRowY+_pcH-_vH-10,_vW,_vH,4,true,false);
        ctx.fillStyle=p.value==='hot'?'#f85149':'#3fb950';
        ctx.textAlign='center'; ctx.textBaseline='middle';
        ctx.fillText(_vLbl,_px+_pcW-_vW/2-10,_pcRowY+_pcH-_vH/2-10);
      }

      // Bottom confidence label strip
      ctx.font='11px system-ui,sans-serif';
      ctx.fillStyle='rgba(139,148,158,0.45)'; ctx.textAlign='left'; ctx.textBaseline='alphabetic';
      const _cLbl=p.conf==='high'?'Hohe Konfidenz':p.conf==='medium'?'Mittlere Konfidenz':'Niedrig';
      ctx.fillText(_cLbl,_px+14,_pcRowY+_pcH-12);
    });
    curY = _pcRowY + _pcH + 20;
  }

  // ── FOOTER ────────────────────────────────────────────────────────────
  curY = H-90;
  ctx.strokeStyle='rgba(255,255,255,0.07)'; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(48,curY); ctx.lineTo(W-48,curY); ctx.stroke();
  curY += 18;
  // Logo / Brand
  ctx.font='bold 22px system-ui,sans-serif'; ctx.textAlign='left'; ctx.textBaseline='middle';
  ctx.fillStyle='#00d4a1'; ctx.fillText('CocoBet', 56, curY+18);
  ctx.font='13px system-ui,sans-serif'; ctx.fillStyle='rgba(139,148,158,0.65)';
  ctx.fillText('AI-powered betting analysis', 56, curY+38);
  // Match score badge (right)
  igRoundRect(ctx,W-180,curY+4,130,38,10,true,false);
  ctx.fillStyle='rgba(22,27,34,0.8)'; igRoundRect(ctx,W-180,curY+4,130,38,10,true,false);
  ctx.strokeStyle=scoreColor+'60'; ctx.lineWidth=1; igRoundRect(ctx,W-180,curY+4,130,38,10,false,true);
  ctx.font='bold 13px system-ui,sans-serif'; ctx.fillStyle='rgba(200,210,220,0.55)'; ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText('MATCH SCORE', W-115, curY+14);
  ctx.font='bold 20px system-ui,sans-serif'; ctx.fillStyle=scoreColor;
  ctx.fillText(`${score.toFixed(1)} / 12`, W-115, curY+30);
  // Disclaimer right
  ctx.font='11px system-ui,sans-serif'; ctx.fillStyle='rgba(139,148,158,0.40)';
  ctx.textAlign='right'; ctx.textBaseline='middle';
  ctx.fillText('18+ · No winnings guaranteed · Gamble responsibly', W-48, curY+48);
  ctx.textBaseline='alphabetic';

  // ── Show modal ───────────────────────────────────────────
  const dataUrl=canvas.toDataURL('image/png');
  const slug=`${match.home}-vs-${match.away}`.replace(/\s+/g,'-').replace(/[^a-zA-Z0-9\-]/g,'');
  const fname=`betedge-${slug}.png`;
  const modal=document.getElementById('ig-modal');
  const img=document.getElementById('ig-preview-img');
  const dlBtn=document.getElementById('ig-download-btn');
  img.src=dataUrl; dlBtn.href=dataUrl; dlBtn.download=fname;
  window._igDataUrl=dataUrl; window._igFileName=fname;
  const shareBtn=document.getElementById('ig-share-btn');
  shareBtn.style.display=navigator.canShare&&navigator.canShare({files:[new File([],'t.png',{type:'image/png'})]})?'flex':'none';
  modal.classList.add('ig-open');
}

function closeIgModal() {
  document.getElementById('ig-modal').classList.remove('ig-open');
}

async function shareInfographic() {
  if (!navigator.share || !window._igDataUrl) return;
  try {
    const res=await fetch(window._igDataUrl);
    const blob=await res.blob();
    const file=new File([blob], window._igFileName, {type:'image/png'});
    await navigator.share({files:[file], title:'CocoBet Infografik'});
  } catch(e) {}
}

// ── Shared card-to-PNG helper ────────────────────────────
async function _captureCard(card, btn, lang = 'de') {
  const orig = btn.innerHTML;
  btn.innerHTML = '⏳';
  btn.disabled = true;

  // For EN: translate all text nodes in the card, revert after screenshot
  const _snapshots = [];
  if (lang === 'en') {
    const walk = node => {
      if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
        const translated = _translateEN(node.textContent);
        if (translated !== node.textContent) {
          _snapshots.push({ node, orig: node.textContent });
          node.textContent = translated;
        }
      } else {
        node.childNodes.forEach(walk);
      }
    };
    walk(card);
  }

  try {
    const canvas = await html2canvas(card, {
      scale: 2,
      backgroundColor: null,
      useCORS: true,
      logging: false,
      scrollX: 0,
      scrollY: -window.scrollY,
    });

    // Revert DOM immediately after capture
    _snapshots.forEach(({ node, orig }) => { node.textContent = orig; });

    const blob = await new Promise(r => canvas.toBlob(r, 'image/png'));
    if (navigator.clipboard?.write) {
      await navigator.clipboard.write([new ClipboardItem({'image/png': blob})]);
      btn.innerHTML = lang === 'en' ? '🇬🇧✅' : '✅';
      setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 2000);
    } else {
      const home = card.querySelector('.card-home')?.textContent?.trim().replace(/\s+/g,'-') || 'home';
      const away = card.querySelector('.card-away')?.textContent?.trim().replace(/\s+/g,'-') || 'away';
      const a = document.createElement('a');
      a.href = canvas.toDataURL('image/png');
      a.download = `cocobet-card-${home}-vs-${away}${lang==='en'?'-en':''}.png`;
      a.click();
      btn.innerHTML = orig; btn.disabled = false;
    }
  } catch(e) {
    _snapshots.forEach(({ node, orig }) => { node.textContent = orig; }); // always revert
    console.error('[copyCardImage]', e);
    btn.innerHTML = '❌';
    setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 2000);
  }
}

// ── Copy the rendered HTML card as a PNG image ───────────
async function copyCardImage(btn, lang = 'de') {
  const card = btn.closest('.stake-card');
  if (!card) return;
  await _captureCard(card, btn, lang);
}

async function copyInfographic(btn) {
  if (!window._igDataUrl) return;
  try {
    const res=await fetch(window._igDataUrl);
    const blob=await res.blob();
    await navigator.clipboard.write([new ClipboardItem({'image/png': blob})]);
    const orig=btn.textContent;
    btn.textContent='✅ Kopiert! Jetzt in Telegram einfügen (⌘V)';
    btn.style.color='#3fb950';
    setTimeout(()=>{ btn.textContent=orig; btn.style.color=''; },3000);
  } catch(e) {
    // Fallback: click download
    document.getElementById('ig-download-btn').click();
  }
}


// ═══════════════════════════════════════════════════════
//  TELEGRAM SHARE ENGINE
// ═══════════════════════════════════════════════════════
function shareTelegram(matchJson, leagueName, leagueFlag, leagueKey) {
  const match = JSON.parse(decodeURIComponent(matchJson));
  const score = computeMatchScore(match, leagueKey);
  const angle = getBettingAngle(match);
  const angleTxt = angle.text.replace(/<[^>]+>/g,'').replace(/&amp;/g,'&').replace(/&lt;/g,'<');
  const odds  = leagueKey ? findOdds(leagueKey, match.home, match.away) : null;
  const oddsD = deriveOdds(odds || {});
  const picks = getBettingPicks(match, oddsD, leagueKey);
  const _ok   = p => p.odds == null ? true : p.odds >= 1.30;
  const visiblePicks = picks.filter(p => (p.conf==='high'||p.conf==='medium') && _ok(p));

  // Context: rest days + injuries + referee (mirrors card logic)
  const _tgFix   = leagueKey ? (LEAGUES[leagueKey]?.fixtures||[]) : [];
  const _tgHRest = getRestDays(match.home, match.date, _tgFix);
  const _tgARest = getRestDays(match.away, match.date, _tgFix);
  const _tgHInj  = _missToInjDisplay(match.homeSquad?.missingStarters ?? match.homeStake?.missingStarters)
                   || match.homeForm?.injuries || null;
  const _tgAInj  = _missToInjDisplay(match.awaySquad?.missingStarters ?? match.awayStake?.missingStarters)
                   || match.awayForm?.injuries || null;
  const _tgRef   = match.refereeStats || null;
  const _tgBuildInj = (inj, teamName) => {
    if (!inj || (inj.total||0) === 0) return '';
    const imp = inj.impactScore || 0;
    if (imp < 0.3 && (inj.confirmed||0) === 0) return '';
    const icon = imp >= 3.5 ? '🔴' : imp >= 2.0 ? '🟠' : '🟡';
    const confirmed = (inj._raw || []).filter(p => p.type === 'Missing Fixture');
    const names = confirmed.slice(0, 2).map(p => p.player.split(' ').slice(-1)[0]);
    const nameStr = names.length ? names.join(', ') + (confirmed.length > 2 ? ` +${confirmed.length - 2}` : '') : '';
    const areaMap = [];
    if ((inj.goalkeeper||0) > 0) areaMap.push('TW');
    if ((inj.attack||0)     > 0) areaMap.push(`${inj.attack} Ang`);
    if ((inj.defense||0)    > 0) areaMap.push(`${inj.defense} Abw`);
    if ((inj.midfield||0)   > 0) areaMap.push(`${inj.midfield} MF`);
    const areaStr = areaMap.length ? ` · ${areaMap.slice(0,3).join('/')}` : '';
    const label = nameStr ? `${nameStr} fehlt${confirmed.length > 1 ? 'en' : ''}${areaStr}` : `${inj.total} Ausfälle${areaStr}`;
    return `${icon} 🏥 ${teamName}: ${label}`;
  };
  const ctxLines = [];
  if (_tgHRest != null && _tgHRest <= 5) ctxLines.push(`😴 Kurze Pause: ${match.home} (${_tgHRest} Tage)`);
  if (_tgARest != null && _tgARest <= 5) ctxLines.push(`😴 Kurze Pause: ${match.away} (${_tgARest} Tage)`);
  const _tgHInjLine = _tgBuildInj(_tgHInj, match.home);
  const _tgAInjLine = _tgBuildInj(_tgAInj, match.away);
  if (_tgHInjLine) ctxLines.push(_tgHInjLine);
  if (_tgAInjLine) ctxLines.push(_tgAInjLine);
  if (_tgRef?.name) {
    const avg = _tgRef.avgCards;
    const avgNote = avg != null ? ` · Ø ${avg} Karten/Sp` : '';
    ctxLines.push(`👨‍⚖️ Schiri: ${_tgRef.name}${avgNote}`);
  }

  const hLabels = (match.homeStake?.labels||[]).map(l=>l.l).join(' · ') || '—';
  const aLabels = (match.awayStake?.labels||[]).map(l=>l.l).join(' · ') || '—';

  let msg = `🏁 Season Finish · ${leagueFlag} ${leagueName}\n`;
  msg += `📅 ${match.date}${match.time ? ' · ' + match.time : ''}  ·  ⭐ Score ${score}/12\n`;
  msg += `${'─'.repeat(32)}\n`;
  msg += `⚽ ${match.home} vs ${match.away}\n\n`;
  msg += `🏠 ${match.home}: ${hLabels}\n`;
  msg += `✈️ ${match.away}: ${aLabels}\n\n`;
  msg += `${angle.badge}\n${angleTxt}\n\n`;

  if (ctxLines.length) {
    msg += `⚠️ Kontext\n${ctxLines.join('\n')}\n\n`;
  }

  if (oddsD && oddsD.hw) {
    msg += `📊 Pinnacle Quoten\n`;
    msg += `H ${oddsD.hw.toFixed(2)}  ·  X ${(oddsD.dr||0).toFixed(2)}  ·  A ${oddsD.aw.toFixed(2)}\n`;
    if (oddsD.o25) msg += `O2.5 ${oddsD.o25.toFixed(2)}  ·  U2.5 ${(oddsD.u25||0).toFixed(2)}\n`;
    const derived=[];
    if (oddsD.dnbH) derived.push(`DNB H ${oddsD.dnbH.toFixed(2)}`);
    if (oddsD.dnbA) derived.push(`DNB A ${oddsD.dnbA.toFixed(2)}`);
    if (oddsD.dc1X) derived.push(`1X ${oddsD.dc1X.toFixed(2)}`);
    if (oddsD.dcX2) derived.push(`X2 ${oddsD.dcX2.toFixed(2)}`);
    if (oddsD.bttsY) derived.push(`BTTS Ja ${oddsD.bttsY.toFixed(2)}`);
    if (oddsD.bttsN) derived.push(`BTTS Nein ${oddsD.bttsN.toFixed(2)}`);
    if (derived.length) msg += derived.join('  ·  ') + '\n';
    msg += `\n`;
  }

  msg += `🎲 Top Wetten (★★☆+)\n`;
  for (const p of visiblePicks) {
    const oddsStr = p.odds ? ` @ ${p.odds.toFixed(2)}` : '';
    const confStr = {high:'★★★',medium:'★★☆',low:'★☆☆'}[p.conf]||'★★☆';
    msg += `${p.icon} ${p.market}${oddsStr}  ${confStr}\n`;
  }
  if (!visiblePicks.length) msg += `(Kein Pick mit ausreichender Konfidenz)\n`;

  msg += `${'─'.repeat(32)}\n`;
  msg += `via CocoBet · Nur ab 18 Jahren`;

  // Try native desktop app first (tg:// scheme)
  // Falls back to web after 800ms if app didn't open
  const tgApp = `tg://msg?text=${encodeURIComponent(msg)}`;
  const tgWeb = `https://t.me/share/url?text=${encodeURIComponent(msg)}`;

  // Show toast
  showToast('📤 Telegram wird geöffnet…', 'Klick auf <a href="' + tgWeb + '" target="_blank" style="color:#0088cc">Web-Version</a> wenn App nicht startet');

  window.location.href = tgApp;

  // If page is still visible after 900ms → app not installed, open web fallback
  setTimeout(() => {
    if (!document.hidden) {
      window.open(tgWeb, '_blank');
    }
  }, 900);
}

// ── EN Translation map for copyCard ────────────────────
function _translateEN(text) {
  const map = [
    // Section headers
    [/🏁 Season Finish/g,           '🏁 Season Finish'],
    [/⚠️ Kontext/g,                  '⚠️ Context'],
    [/📊 Pinnacle Quoten/g,          '📊 Pinnacle Odds'],
    [/🎲 Top Wetten \(★★☆\+\)/g,    '🎲 Top Bets (★★☆+)'],
    [/Kein Pick mit ausreichender Konfidenz/g, 'No pick with sufficient confidence'],
    [/via CocoBet · Nur ab 18 Jahren/g, 'via CocoBet · 18+ only'],

    // Markets — specific first, then general
    [/Beide Teams treffen: Nein/g,   'BTTS: No'],
    [/Beide Teams treffen/g,         'BTTS: Yes'],
    [/Heimsieg/g,                    'Home Win'],
    [/Auswärtssieg/g,                'Away Win'],
    [/Unentschieden/g,               'Draw'],
    [/DNB: Heimteam/g,               'DNB: Home'],
    [/DNB: Auswärtsteam/g,           'DNB: Away'],
    [/AH -0\.25 Heim/g,              'AH -0.25 Home'],
    [/AH -0\.25 Auswärts/g,          'AH -0.25 Away'],
    [/Doppelte Chance 1X/g,          'Double Chance 1X'],
    [/Doppelte Chance X2/g,          'Double Chance X2'],
    [/Handicap -0\.5 Heim/g,         'Handicap -0.5 Home'],
    [/Handicap -0\.5 Auswärts/g,     'Handicap -0.5 Away'],
    [/(Over|Under) ([\d.]+) Tore/g,  (_, ou, n) => `${ou} ${n} Goals`],
    [/Über ([\d.]+) Ecken/g,         (_, n) => `Over ${n} Corners`],
    [/Über ([\d.]+) Karten/g,        (_, n) => `Over ${n} Cards`],
    [/1\. HZ: Under ([\d.]+) Tore/g, (_, n) => `1st Half: Under ${n} Goals`],
    [/1\. HZ: Over ([\d.]+) Tore/g,  (_, n) => `1st Half: Over ${n} Goals`],
    [/1\. HZ: BTTS/g,                '1st Half: BTTS'],
    [/ über ([\d.]+) Tore/g,         (_, n) => ` Over ${n} Goals`],

    // Context labels
    [/Kurze Pause/g,                 'Short Rest'],
    [/ Tage\b/g,                     ' days'],
    [/Schiri:/g,                     'Referee:'],
    [/Karten\/Sp/g,                  'cards\/game'],
    [/ Ausfälle/g,                   ' missing'],
    [/ fehlen\b/g,                   ' out'],
    [/ fehlt\b/g,                    ' out'],
    [/Angriff/g,                     'Attack'],
    [/Abwehr/g,                      'Defense'],
    [/Torwart/g,                     'Goalkeeper'],

    // Stake labels — specific before general
    [/Titelchance/g,                 'Title Chance'],
    [/Titelkampf/g,                  'Title Race'],
    [/Abstiegsgefahr/g,              'Relegation Risk'],
    [/Abstiegskampf/g,               'Relegation Battle'],
    [/\bAbstieg\b/g,                 'Relegated'],
    [/UCL Jagd/g,                    'UCL Hunt'],
    [/UCL sichern/g,                 'UCL Secure'],
    [/EL Jagd/g,                     'EL Hunt'],
    [/EL sichern/g,                  'EL Secure'],
    [/Rel\.-Playoff/g,               'Rel. Playoff'],
    [/Champions League/g,            'Champions League'],
    [/Europa League/g,               'Europa League'],
    [/Conference League/g,           'Conference League'],
    [/kein direkter Stake/g,         'no direct stake'],
    [/Keine Daten/g,                 'No data'],

    // Card UI — also match without leading emoji (DOM splits text nodes)
    [/Hauptempfehlung:/g,            'Main Pick:'],
    [/Hauptempfehlung\b/g,           'Main Pick'],

    // Odds display (text copy)
    [/BTTS Ja\b/g,                   'BTTS Yes'],
    [/BTTS Nein\b/g,                 'BTTS No'],

    // Card UI labels (image copy)
    [/🎲 Top Wetten für diese Partie/g, '🎲 Top Bets for this Match'],
    [/Wett-Winkel/g,                 'Betting Angle'],
    [/🛡️ Hauptempfehlung:/g,         '🛡️ Main Pick:'],
    [/📈 Mehr Value:/g,              '📈 More Value:'],
    [/Modell-Näherung/g,             'Model estimate'],
    [/Hohe Konfidenz/g,              'High Confidence'],
    [/Mittlere Konfidenz/g,          'Medium Confidence'],
    [/Niedrige Konfidenz/g,          'Low Confidence'],

    // Reason text — fixed patterns
    [/📊 Heimstatistik \(Saison\):/g,     '📊 Home stats (season):'],
    [/📊 Auswärtsstatistik \(Saison\):/g, '📊 Away stats (season):'],
    [/🔥 Aktueller Lauf:/g,          '🔥 Current streak:'],
    [/📡 API-Signale bestätigen[^:]*:/g,  '📡 API signals confirm:'],
    [/📡 API-Signale:/g,             '📡 API signals:'],
    [/🤖 Statistisches Modell sieht ([^m]+) mit (\d+)% als Favorit — bestätigt die Analyse\./g,
      (_, team, pct) => `🤖 Statistical model: ${team} at ${pct}% — confirms the analysis.`],
    [/🤖 Statistisches Modell sieht ([^m]+) mit (\d+)% als Favorit\./g,
      (_, team, pct) => `🤖 Statistical model: ${team} at ${pct}% — slightly favoured.`],
    [/⚠️ Statistisches Modell: ([^ ]+) nur bei (\d+)% Siegchance — Modell ist skeptischer\./g,
      (_, team, pct) => `⚠️ Statistical model: ${team} only at ${pct}% — model is more cautious.`],
    [/🤖 API-Modell erwartet ([\d.]+) Tore — bestätigt die Over-Prognose\./g,
      (_, n) => `🤖 Model expects ${n} goals — confirms the Over.`],
    [/🤖 API-Modell erwartet nur ([\d.]+) Tore — geht von weniger Toren aus\./g,
      (_, n) => `🤖 Model expects only ${n} goals — projects fewer goals.`],
    [/📊 Elo bestätigt:/g,           '📊 Elo confirms:'],
    [/⚠️ Elo-Warnung:/g,             '⚠️ Elo warning:'],
    [/% Siege/g,                     '% wins'],
    [/% Siege · /g,                  '% wins · '],
    [/% Clean Sheets/g,              '% clean sheets'],
    [/(\d+)× ungeschlagen/g,         (_, n) => `${n}× unbeaten`],
    [/(\d+)× ohne Sieg/g,            (_, n) => `${n}× without a win`],
    [/ zeigt aktuell klar die bessere Form\./g, ' is showing clearly better current form.'],
    [/ hat aktuell die bessere Formkurve — Vorsicht\./g, ' has the better current form — caution.'],
    [/ liegt in der aktuellen Form vorn — Vorsicht\./g, ' leads in current form — caution.'],

    // Reason prose — most common sentences
    [/ist in Topform \(zuletzt (\d+) Siege\)/g,  (_, n) => `is in top form (last ${n} wins)`],
    [/kämpft um den Titel/g,         'fighting for the title'],
    [/kämpft gegen den Abstieg/g,    'fighting relegation'],
    [/kämpft im Abstiegskampf/g,     'in the relegation battle'],
    [/braucht jeden Punkt/g,         'needs every point'],
    [/ist Favorit/g,                 'is the favourite'],
    [/erzielt Ø ([\d.]+) Tore\/Spiel/g,  (_, n) => `avg ${n} goals/game`],
    [/kassiert Ø ([\d.]+) Tore\/Spiel/g, (_, n) => `concedes avg ${n} goals/game`],
    [/lassen regelmäßig Gegentore zu/g,  'concede regularly'],
    [/ist anfällig/g,                'is vulnerable'],
    [/Das Modell erwartet ([\d.]+) Tore/g, (_, n) => `Model expects ${n} goals`],
    [/Tore erwartet/g,               'goals expected'],
    [/mindestens (\d+) Treffer sind gut möglich/g, (_, n) => `at least ${n} goals are likely`],
    [/Historisch (\d+)% der (\d+) Duelle über 2\.5 Tore/g,
      (_, pct, n) => `Historically ${pct}% of ${n} H2H matches over 2.5 goals`],
    [/Ø ([\d.]+) Tore\/Spiel/g,      (_, n) => `avg ${n} goals/game`],
    [/gewinnt (\d+)% seiner Heimspiele/g,  (_, n) => `wins ${n}% of home games`],
    [/gewinnt (\d+)% seiner Auswärtsspiele/g, (_, n) => `wins ${n}% of away games`],
    [/· H2H: (\d+)H\/(\d+)U\/(\d+)A \((\d+) Duelle\)/g,
      (_, h, d, a, n) => `· H2H: ${h}W/${d}D/${a}L (${n} games)`],
    [/ Duelle\b/g,                   ' games'],
    [/ Duellen\b/g,                  ' games'],
    [/\bTore\b/g,                    'goals'],
    [/\bTreffer\b/g,                 'goals'],
    [/Remis/g,                       'draw'],
    [/ ist Pflicht/g,                ' is a must'],
    [/Titeldruck/g,                  'title pressure'],
    [/mathematisch bestätigt/g,      'mathematically confirmed'],
    [/ ist abgestiegen/g,            ' has been relegated'],
    [/ abgestiegen\b/g,              ' relegated'],
    [/ gesichert\b/g,                ' secured'],
    [/\bgesichert\b/g,               'secured'],
    [/nahezu bestätigt/g,            'near-confirmed'],
    [/Heimvorteil in Existenzkämpfen/g, 'home advantage in must-win games'],
    [/Druckspiel — /g,               'Pressure game — '],
    [/Extreme Motivation/g,          'Extreme motivation'],
    [/hohes Risiko/g,                'high risk'],
    [/karten-intensive Partie/g,     'card-intensive match'],

    // Pressure angle snippets
    [/Muss-Spiel/g,                  'Must-Win'],
    [/Muss gewinnen/g,               'Must Win'],
    [/Druckspiel/g,                  'Pressure Game'],
    [/Titelfavorit/g,                'Title Contender'],
    [/Abstiegszone/g,                'Relegation Zone'],
    [/Tabellenführer/g,              'League Leader'],
    [/Runden verbleibend/g,          'rounds remaining'],
    [/Spieltage? verbleibend/g,      'matchdays remaining'],
    [/NOCH (\d+) RUNDEN/g,           (_, n) => `${n} ROUNDS LEFT`],
  ];
  let out = text;
  for (const [from, to] of map) {
    out = out.replace(from, to);
  }
  return out;
}

// ── Copy card text to clipboard ────────────────────────
function copyCard(matchJson, leagueName, leagueFlag, leagueKey, btn, lang = 'de') {
  const match = JSON.parse(decodeURIComponent(matchJson));
  const score = computeMatchScore(match, leagueKey);
  const angle = getBettingAngle(match);
  const angleTxt = angle.text.replace(/<[^>]+>/g,'').replace(/&amp;/g,'&');
  const odds  = leagueKey ? findOdds(leagueKey, match.home, match.away) : null;
  const oddsD = deriveOdds(odds || {});
  const picks = getBettingPicks(match, oddsD, leagueKey);
  const _ok   = p => p.odds == null ? true : p.odds >= 1.30;
  const visiblePicks = picks.filter(p => (p.conf==='high'||p.conf==='medium') && _ok(p));

  // Context: rest days + injuries + referee (mirrors card logic)
  const _cpFix   = leagueKey ? (LEAGUES[leagueKey]?.fixtures||[]) : [];
  const _cpHRest = getRestDays(match.home, match.date, _cpFix);
  const _cpARest = getRestDays(match.away, match.date, _cpFix);
  const _cpHInj  = _missToInjDisplay(match.homeSquad?.missingStarters ?? match.homeStake?.missingStarters)
                   || match.homeForm?.injuries || null;
  const _cpAInj  = _missToInjDisplay(match.awaySquad?.missingStarters ?? match.awayStake?.missingStarters)
                   || match.awayForm?.injuries || null;
  const _cpRef   = match.refereeStats || null;
  const _cpBuildInj = (inj, teamName) => {
    if (!inj || (inj.total||0) === 0) return '';
    const imp = inj.impactScore || 0;
    if (imp < 0.3 && (inj.confirmed||0) === 0) return '';
    const icon = imp >= 3.5 ? '🔴' : imp >= 2.0 ? '🟠' : '🟡';
    const confirmed = (inj._raw || []).filter(p => p.type === 'Missing Fixture');
    const names = confirmed.slice(0, 2).map(p => p.player.split(' ').slice(-1)[0]);
    const nameStr = names.length ? names.join(', ') + (confirmed.length > 2 ? ` +${confirmed.length - 2}` : '') : '';
    const areaMap = [];
    if ((inj.goalkeeper||0) > 0) areaMap.push('TW');
    if ((inj.attack||0)     > 0) areaMap.push(`${inj.attack} Ang`);
    if ((inj.defense||0)    > 0) areaMap.push(`${inj.defense} Abw`);
    if ((inj.midfield||0)   > 0) areaMap.push(`${inj.midfield} MF`);
    const areaStr = areaMap.length ? ` · ${areaMap.slice(0,3).join('/')}` : '';
    const label = nameStr ? `${nameStr} fehlt${confirmed.length > 1 ? 'en' : ''}${areaStr}` : `${inj.total} Ausfälle${areaStr}`;
    return `${icon} 🏥 ${teamName}: ${label}`;
  };
  const ctxLines = [];
  if (_cpHRest != null && _cpHRest <= 5) ctxLines.push(`😴 Kurze Pause: ${match.home} (${_cpHRest} Tage)`);
  if (_cpARest != null && _cpARest <= 5) ctxLines.push(`😴 Kurze Pause: ${match.away} (${_cpARest} Tage)`);
  const _cpHInjLine = _cpBuildInj(_cpHInj, match.home);
  const _cpAInjLine = _cpBuildInj(_cpAInj, match.away);
  if (_cpHInjLine) ctxLines.push(_cpHInjLine);
  if (_cpAInjLine) ctxLines.push(_cpAInjLine);
  if (_cpRef?.name) {
    const avg = _cpRef.avgCards;
    const avgNote = avg != null ? ` · Ø ${avg} Karten/Sp` : '';
    ctxLines.push(`👨‍⚖️ Schiri: ${_cpRef.name}${avgNote}`);
  }

  const hLabels = (match.homeStake?.labels||[]).map(l=>l.l).join(' · ') || '—';
  const aLabels = (match.awayStake?.labels||[]).map(l=>l.l).join(' · ') || '—';

  let msg = `🏁 Season Finish · ${leagueFlag} ${leagueName}\n`;
  msg += `📅 ${match.date}${match.time ? ' · ' + match.time : ''}  ·  ⭐ Score ${score}/12\n`;
  msg += `${'─'.repeat(32)}\n`;
  msg += `⚽ ${match.home} vs ${match.away}\n\n`;
  msg += `🏠 ${match.home}: ${hLabels}\n`;
  msg += `✈️ ${match.away}: ${aLabels}\n\n`;
  msg += `${angle.badge}\n${angleTxt}\n\n`;

  if (ctxLines.length) {
    msg += `⚠️ Kontext\n${ctxLines.join('\n')}\n\n`;
  }

  if (oddsD && oddsD.hw) {
    msg += `📊 Pinnacle Quoten\n`;
    msg += `H ${oddsD.hw.toFixed(2)}  ·  X ${(oddsD.dr||0).toFixed(2)}  ·  A ${oddsD.aw.toFixed(2)}\n`;
    if (oddsD.o25) msg += `O2.5 ${oddsD.o25.toFixed(2)}  ·  U2.5 ${(oddsD.u25||0).toFixed(2)}\n`;
    const derived=[];
    if (oddsD.dnbH) derived.push(`DNB H ${oddsD.dnbH.toFixed(2)}`);
    if (oddsD.dnbA) derived.push(`DNB A ${oddsD.dnbA.toFixed(2)}`);
    if (oddsD.dc1X) derived.push(`1X ${oddsD.dc1X.toFixed(2)}`);
    if (oddsD.dcX2) derived.push(`X2 ${oddsD.dcX2.toFixed(2)}`);
    if (oddsD.bttsY) derived.push(`BTTS Ja ${oddsD.bttsY.toFixed(2)}`);
    if (oddsD.bttsN) derived.push(`BTTS Nein ${oddsD.bttsN.toFixed(2)}`);
    if (derived.length) msg += derived.join('  ·  ') + '\n';
    msg += '\n';
  }

  msg += `🎲 Top Wetten (★★☆+)\n`;
  for (const p of visiblePicks) {
    const oddsStr = p.odds ? ` @ ${p.odds.toFixed(2)}` : '';
    const confStr = {high:'★★★',medium:'★★☆',low:'★☆☆'}[p.conf]||'★★☆';
    msg += `${p.icon} ${p.market}${oddsStr}  ${confStr}\n`;
  }
  if (!visiblePicks.length) msg += `(Kein Pick mit ausreichender Konfidenz)\n`;
  msg += `${'─'.repeat(32)}\nvia CocoBet · Nur ab 18 Jahren`;

  if (lang === 'en') msg = _translateEN(msg);

  navigator.clipboard.writeText(msg).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = '✓';
    btn.style.color = 'var(--green)';
    btn.style.borderColor = 'var(--green)';
    setTimeout(() => { btn.innerHTML = orig; btn.style.color = ''; btn.style.borderColor = ''; }, 2000);
    const label = lang === 'en' ? '🇬🇧 Copied!' : '📋 Kopiert!';
    showToast(label, 'Text in Zwischenablage — einfach in Telegram einfügen');
  });
}

// ── Toast notification ──────────────────────────────────
function showToast(title, sub) {
  const existing = document.getElementById('tg-toast');
  if (existing) existing.remove();

  const t = document.createElement('div');
  t.id = 'tg-toast';
  t.innerHTML = `<div style="font-weight:700;font-size:13px;margin-bottom:3px">${title}</div><div style="font-size:11px;color:#8b949e">${sub}</div>`;
  Object.assign(t.style, {
    position:'fixed', bottom:'24px', right:'24px', zIndex:'9999',
    background:'#1c2128', border:'1px solid #30363d', borderRadius:'10px',
    padding:'12px 16px', maxWidth:'280px', boxShadow:'0 8px 24px rgba(0,0,0,.5)',
    color:'#e6edf3', fontFamily:'-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
    transition:'opacity .3s', opacity:'0'
  });
  document.body.appendChild(t);
  requestAnimationFrame(() => t.style.opacity = '1');
  setTimeout(() => { t.style.opacity = '0'; setTimeout(()=>t.remove(), 300); }, 4000);
}
