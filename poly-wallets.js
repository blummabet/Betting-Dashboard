// ═══════════════════════════════════════════════════════════════════════════
//  poly-wallets.js — „Polymarket Edge & Smart-Money"-Tab  (Redesign 09.07.2026)
//
//  Philosophie (mit Experten-Konsultation abgestimmt): Die EDGE ist das Signal,
//  die Whales sind Bestätigung/Veto — NIE umgekehrt. Pinnacle (de-viggt) ist der
//  scharfe Anker; Polymarket ist die Trade-Gegenseite. Der Tab zeigt zuerst, WO
//  Polymarket vs. Pinnacle fehlbepreist ist (Edge-Board), und legt das Smart-
//  Money nur als Konfirmation/Veto darunter.
//
//  Sektionen:
//    1. EDGE-BOARD (Hero) — pro Outcome Poly-implied vs Pinnacle-Fair, Netto-Edge
//       (Spread-Haircut), Liquiditäts-Tier, Verdict, Whale-Chip, „Poly hinkt nach".
//    2. MATCH-DRILLDOWN — alle Outcomes + Whale-Verteilung + Conviction + Net-Flow.
//    3. EXIT-WATCH — stark negativer Net-Flow nah am Anpfiff (Veto).
//    4. FLOW-TAPE — jüngste große Trades.
//    5. WHALE-LEADERBOARD — größte Einzelpositionen (zuletzt, browse-y).
//
//  Datenquellen (dataset-aware; Liga-ready sobald liga_poly_*.json existiert):
//    {ds}_poly_prices.json  (Poly-Preise + Volumen)  · {ds}_poly_wallets.json (Whales)
//    {ds}-data.json / window.WM2026_DATA (Teams-Flaggen/Logos + Pinnacle-Odds)
// ═══════════════════════════════════════════════════════════════════════════

let _polyWalletsLoaded = false;
let _pwState = { open: null };   // aufgeklapptes Match im Edge-Board
let _pwCache = null;             // {wm, prices, wallets} — Toggle rendert aus Cache (kein Refetch)

// ── Schwellen (Experten-Brief) ──────────────────────────────────────────────
const PW_SPREAD_HAIRCUT = 1.5;   // pp Abschlag für Poly-Spread/Fee (konservativ)
const PW_NOISE = 2.0;            // < 2pp netto = Rauschen
const PW_TRADE = 4.0;            // ≥ 4pp netto = handelbar auf Edge allein
const PW_MOVE_FRESH = 2.0;       // Pinnacle-Move seit Opening (pp) → „frischer" Zug

function _pwDataset() {
  // Liga-ready: aktiver Datensatz bestimmt die Dateipräfixe. Poly ist derzeit WM-only;
  // sobald liga_poly_*.json existiert, liefert window._pwDataset='liga' die Liga-Sicht.
  return (typeof window !== 'undefined' && window._pwDataset) ? window._pwDataset : 'wm';
}
function _pwFiles() {
  const ds = _pwDataset();
  if (ds === 'liga') return { prices: 'liga_poly_prices.json', wallets: 'liga_poly_wallets.json', data: 'liga-data.json' };
  return { prices: 'wm_poly_prices.json', wallets: 'wm_poly_wallets.json', data: 'wm2026-data.json' };
}

function initPolyWallets() {
  const panel = document.getElementById('polyWalletsPanel');
  if (!panel) return;
  if (_polyWalletsLoaded) return;
  _polyWalletsLoaded = true;
  _pwInjectStyle();
  panel.innerHTML = '<div class="pw-loading">🐋 Lade Polymarket-Edge & Smart-Money…</div>';

  const f = _pwFiles();
  const bust = '?t=' + Date.now();
  const wmPromise = (typeof window !== 'undefined' && window.WM2026_DATA && _pwDataset() === 'wm')
    ? Promise.resolve(window.WM2026_DATA)
    : fetch(f.data + bust, { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null);

  Promise.all([
    wmPromise,
    fetch(f.prices + bust, { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
    fetch(f.wallets + bust, { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
  ]).then(([wm, prices, wallets]) => {
    _pwCache = { wm, prices, wallets };
    try { renderPolyDashboard(panel, wm, prices, wallets); }
    catch (e) { panel.innerHTML = '<div class="pw-loading">⚠️ Render-Fehler: ' + (e && e.message) + '</div>'; }
  });
}

// ── Formatierung ────────────────────────────────────────────────────────────
function _pwUsd(v) {
  const n = Number(v) || 0;
  if (n >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
  if (n >= 1e3) return '$' + (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + 'K';
  return '$' + Math.round(n);
}
function _pwPct(p) { return (p * 100).toFixed(0) + '%'; }
function _pwPP(v) { return (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(1) + 'pp'; }
function _pwWallet(w) { if (!w) return '—'; const s = String(w); return s.length > 12 ? s.slice(0, 6) + '…' + s.slice(-4) : s; }
function _pwLink(w) { return 'https://polymarket.com/profile/' + encodeURIComponent(w); }
function _pwAgo(ts) { return (ts && typeof _timeAgo === 'function') ? _timeAgo(ts) : ''; }

// Flagge/Logo generisch: Emoji (WM) ODER img-URL/tag (Liga-Logos).
function _pwFlag(flag) {
  if (!flag) return '<span class="pw-flag">🏳️</span>';
  const s = String(flag);
  if (s.indexOf('<img') === 0) return s.replace('<img', '<img class="pw-logo"');
  if (/^https?:\/\//.test(s)) return '<img class="pw-logo" src="' + s + '" alt="" loading="lazy">';
  return '<span class="pw-flag">' + s + '</span>';
}

// ── Team-Map aus {ds}-data.json (id → {name, flag}) ─────────────────────────
function _pwTeamsMap(wm) {
  const map = {};
  const groups = (wm && wm.groups) || {};
  Object.values(groups).forEach(g => (g.teams || []).forEach(t => {
    if (t && t.id) map[t.id] = { name: t.name || t.id, flag: t.flag };
  }));
  return map;
}
// Pinnacle-Odds-Map (key → entry)
function _pwOddsMap(wm) { return (wm && wm.odds) || {}; }

// ── Devig ───────────────────────────────────────────────────────────────────
function _pwDevig1x2(hw, dr, aw) {
  if (!(hw > 1 && dr > 1 && aw > 1)) return null;
  const a = 1 / hw, b = 1 / dr, c = 1 / aw, s = a + b + c;
  return { home: a / s, draw: b / s, away: c / s };
}
function _pwDevig2(o, u) {
  if (!(o > 1 && u > 1)) return null;
  const a = 1 / o, b = 1 / u, s = a + b;
  return { over: a / s, under: b / s };
}

// ── Liquiditäts-Tier aus Volumen ────────────────────────────────────────────
function _pwLiq(vol) {
  const v = Number(vol) || 0;
  if (v >= 100000) return { tier: 'deep', icon: '🌊', label: 'tiefer Markt', ok: true };
  if (v >= 15000)  return { tier: 'mid',  icon: '💧', label: 'mittel', ok: true };
  return { tier: 'low', icon: '·', label: 'dünn', ok: false };
}

// ── Ein Edge-Kandidat bewerten ──────────────────────────────────────────────
function _pwVerdict(net, liq) {
  if (!liq.ok && net < PW_TRADE + 1) return { v: 'THIN', cls: 'thin' };
  if (net >= PW_TRADE) return { v: 'TRADE', cls: 'trade' };
  if (net >= PW_NOISE) return { v: 'THIN', cls: 'thin' };
  return { v: 'NOISE', cls: 'noise' };
}

// Baut alle Edge-Zeilen: pro Match die 1X2 + O/U2.5 + BTTS Outcomes.
function _pwBuildEdges(prices, oddsMap) {
  const rows = [];
  const P = (prices && prices.prices) || {};
  Object.entries(P).forEach(([key, m]) => {
    const o = oddsMap[key] || {};
    const koH = _pwHoursToKO(m.kickoff);
    // 1X2
    const pf = _pwDevig1x2(o.hw, o.dr, o.aw);
    const openf = _pwDevig1x2((o.odds_open || {}).hw, (o.odds_open || {}).dr, (o.odds_open || {}).aw);
    const legs1 = [
      { side: 'home', poly: m.hw, fair: pf && pf.home, open: openf && openf.home, label: (m.homeName || key.split('-')[0]) + ' Sieg' },
      { side: 'draw', poly: m.dr, fair: pf && pf.draw, open: openf && openf.draw, label: 'Unentschieden' },
      { side: 'away', poly: m.aw, fair: pf && pf.away, open: openf && openf.away, label: (m.awayName || key.split('-')[1]) + ' Sieg' },
    ];
    // O/U 2.5
    const pou = _pwDevig2(o.o25, o.u25);
    const legsOU = [
      { side: 'over', mkt: 'ou', poly: m.poly_o25, fair: pou && pou.over, label: 'Über 2.5 Tore' },
      { side: 'under', mkt: 'ou', poly: m.poly_u25, fair: pou && pou.under, label: 'Unter 2.5 Tore' },
    ];
    // BTTS
    const pbt = _pwDevig2(o.bttsY, o.bttsN);
    const legsBT = [
      { side: 'bttsY', mkt: 'btts', poly: m.poly_btts, fair: pbt && pbt.over, label: 'Beide treffen — Ja' },
      { side: 'bttsN', mkt: 'btts', poly: m.poly_btts_no, fair: pbt && pbt.under, label: 'Beide treffen — Nein' },
    ];
    [...legs1, ...legsOU, ...legsBT].forEach(l => {
      if (!(l.poly > 0 && l.poly < 1) || !(l.fair > 0)) return;
      const gross = (l.fair - l.poly) * 100;
      const net = gross - PW_SPREAD_HAIRCUT;
      if (net <= 0) return;                       // nur echte Value-Seiten
      const liq = _pwLiq(m.vol);
      const fresh = (l.open != null && (l.fair - l.open) * 100 >= PW_MOVE_FRESH);  // Pinnacle zog zu dieser Seite
      rows.push({
        key, match: (m.homeName || key.split('-')[0]) + ' – ' + (m.awayName || key.split('-')[1]),
        homeId: m.homeId, awayId: m.awayId, kickoff: m.kickoff, koH, vol: m.vol,
        mkt: l.mkt || '1x2', side: l.side, ticket: l.label,
        poly: l.poly, fair: l.fair, gross, net, liq, fresh,
        verdict: _pwVerdict(net, liq),
      });
    });
  });
  rows.sort((a, b) => b.net - a.net);
  return rows;
}

function _pwHoursToKO(iso) {
  if (!iso) return null;
  const t = Date.parse(String(iso).replace(' ', 'T'));
  if (isNaN(t)) return null;
  return (t - Date.now()) / 3.6e6;
}

// ── Whale-Konsens je Match/Seite (aus clustersAll) ──────────────────────────
function _pwClusterFor(wallets, key, side) {
  const cl = (wallets && wallets.clustersAll) || [];
  return cl.find(c => c.key === key && c.side === side) || null;
}

// ── Conviction-Score 0–10 je Seite (Cluster-gewichtet, Konzentration-Discount) ─
function _pwConviction(wallets, key, side) {
  const match = (wallets && wallets.matches && wallets.matches[key]) || null;
  const cl = _pwClusterFor(wallets, key, side);
  if (!match && !cl) return null;
  const pos = ((match && match.topPositions) || []).filter(p => p.side === side);
  const sideUsd = pos.reduce((s, p) => s + (p.usd || 0), 0);
  const nWallets = pos.length;
  const topShare = sideUsd > 0 ? (pos[0] ? pos[0].usd / sideUsd : 0) : 0;
  const cluster = cl ? (cl.cluster || 0) : nWallets;
  const net = cl ? (cl.netFlowUsd || 0) : 0;
  // Cluster (Unabhängigkeit) = Hauptinput; Konzentration senkt Vertrauen; Net-Flow-Richtung.
  let score = Math.min(6, cluster * 1.6);           // bis 6 aus Unabhängigkeit
  score += Math.max(0, 2 - topShare * 2.5);          // verteilt → bis +2, 1-Wallet-dominiert → 0
  if (net > 0) score += 1.2; else if (net < 0) score -= 1.5;
  score = Math.max(0, Math.min(10, score));
  return { score: Math.round(score * 10) / 10, sideUsd, nWallets, topShare, cluster, net };
}

// ═══════════════════════════════════ RENDER ════════════════════════════════
function renderPolyDashboard(panel, wm, prices, wallets) {
  const teams = _pwTeamsMap(wm);
  const oddsMap = _pwOddsMap(wm);
  const edges = _pwBuildEdges(prices, oddsMap);
  const hasWm = wm && Object.keys(oddsMap).length;
  const hasPoly = wallets && ((wallets.topPositionsAll || []).length || (wallets.matches && Object.keys(wallets.matches).length));

  const upd = wallets && wallets.updatedAt ? _pwAgo(wallets.updatedAt) : '—';

  if (!hasPoly && !edges.length) {
    panel.innerHTML =
      '<div class="pw-empty"><div class="pw-empty-ico">🐋</div>'
      + '<h2>Polymarket Edge & Smart-Money</h2>'
      + '<p>Noch keine Daten. Der Mac-Runner befüllt <code>' + _pwFiles().wallets + '</code> + '
      + '<code>' + _pwFiles().prices + '</code> stündlich (Polymarket ist geoblockt → nur dort). '
      + 'Sobald Preise + Wallets da sind, erscheint hier das Edge-Board.</p></div>';
    return;
  }

  let html = ''
    + '<div class="pw-head">'
    +   '<div><h1>🐋 Polymarket <span class="pw-accent">Edge</span> & Smart-Money</h1>'
    +   '<p class="pw-sub">Wo Polymarket vs. dem scharfen Pinnacle-Anker fehlbepreist ist — bestätigt oder gevetot vom großen Geld. '
    +   '<b>Die Edge ist das Signal, die Whales sind das Veto.</b></p></div>'
    +   '<div class="pw-stamp">Stand ' + upd + '<br><span>Beträge = Anteile × Preis (geschätzt)</span></div>'
    + '</div>';

  html += _pwRenderEdgeBoard(edges, teams, wallets);
  html += _pwRenderExitWatch(wallets, teams);
  html += _pwRenderFlowTape(wallets, teams);
  html += _pwRenderLeaderboard(wallets, teams);

  panel.innerHTML = html;
}

// ── 1. EDGE-BOARD (Hero) ─────────────────────────────────────────────────────
function _pwRenderEdgeBoard(edges, teams, wallets) {
  const shown = edges.filter(e => e.net >= PW_NOISE);   // Rauschen nicht über der Falz
  let h = '<section class="pw-sec">'
    + '<div class="pw-sec-head"><span class="pw-kicker">⚡ Edge-Board</span>'
    + '<span class="pw-sec-note">Poly-Preis vs. de-viggte Pinnacle-Fairwahrscheinlichkeit · Netto nach Spread-Haircut (' + PW_SPREAD_HAIRCUT + 'pp)</span></div>';

  if (!shown.length) {
    h += '<div class="pw-none">Aktuell keine handelbare Fehlbepreisung ≥ ' + PW_NOISE + 'pp — Polymarket und Pinnacle liegen eng beieinander.</div>';
    // Beobachtungsliste: die größten Sub-Schwellen-Gaps (gedimmt), damit der Hero nie leer ist.
    const watch = edges.slice(0, 5);
    if (watch.length) {
      h += '<div class="pw-sec-note" style="margin:14px 0 8px">Nächste Beobachtungen (unter Schwelle):</div><div class="pw-board pw-watch">';
      watch.forEach(e => { h += _pwEdgeRow(e, teams, wallets); });
      h += '</div>';
    }
    return h + '</section>';
  }

  h += '<div class="pw-board">';
  shown.slice(0, 40).forEach(e => { h += _pwEdgeRow(e, teams, wallets); });
  h += '</div></section>';
  return h;
}

// Eine Edge-Zeile (wiederverwendet für Board + Watchlist)
function _pwEdgeRow(e, teams, wallets) {
  let h = '';
  {
    const wc = (e.mkt === '1x2') ? _pwWhaleChip(wallets, e.key, e.side) : null;
    const sideCol = _pwSideCol(e.side);
    const koLbl = e.koH == null ? '' : (e.koH < 0 ? 'läuft' : (e.koH < 1 ? '<1h' : Math.round(e.koH) + 'h'));
    const open = _pwState.open === e.key + '|' + e.side;
    h += '<div class="pw-row ' + (open ? 'pw-row-open' : '') + '" onclick="_pwToggle(\'' + e.key + '|' + e.side + '\')">'
      +   '<div class="pw-row-main">'
      +     '<div class="pw-teams">'
      +       _pwFlag(teams[e.homeId] && teams[e.homeId].flag) + _pwFlag(teams[e.awayId] && teams[e.awayId].flag)
      +       '<div class="pw-tk"><div class="pw-ticket" style="color:' + sideCol + '">' + e.ticket + '</div>'
      +       '<div class="pw-match">' + e.match + (koLbl ? ' · <span class="pw-ko">' + koLbl + '</span>' : '') + '</div></div>'
      +     '</div>'
      +     '<div class="pw-probs">'
      +       '<div class="pw-prob"><span>Poly</span><b>' + _pwPct(e.poly) + '</b></div>'
      +       '<div class="pw-arrow">→</div>'
      +       '<div class="pw-prob"><span>Pinnacle</span><b class="pw-fair">' + _pwPct(e.fair) + '</b></div>'
      +     '</div>'
      +     '<div class="pw-edge">'
      +       '<div class="pw-edge-n pw-' + e.verdict.cls + '">' + _pwPP(e.net) + '</div>'
      +       '<div class="pw-chips">'
      +         '<span class="pw-vd pw-' + e.verdict.cls + '">' + e.verdict.v + '</span>'
      +         '<span class="pw-liq" title="' + e.liq.label + ' · Vol ' + _pwUsd(e.vol) + '">' + e.liq.icon + '</span>'
      +         (e.fresh ? '<span class="pw-fresh" title="Pinnacle zog seit Opening zu dieser Seite — Poly hinkt nach">🔥 STEAM</span>' : '')
      +         (wc ? wc.chip : '')
      +       '</div>'
      +     '</div>'
      +   '</div>'
      +   (open ? _pwRenderDrill(e, teams, wallets) : '')
      + '</div>';
  }
  return h;
}

function _pwWhaleChip(wallets, key, side) {
  const cv = _pwConviction(wallets, key, side);
  if (!cv || (cv.cluster < 1 && cv.sideUsd < 3000)) return null;
  // Konfirmation wenn Konsens + nicht netto-negativ; Fade/Exit wenn Net-Flow raus.
  if (cv.net < 0) return { chip: '<span class="pw-wh pw-wh-fade" title="Smart Money läuft auf dieser Seite netto RAUS (Exit)">🐋 EXIT</span>', cv };
  if (cv.cluster >= 3) return { chip: '<span class="pw-wh pw-wh-conf" title="' + cv.cluster + ' unabhängige Wallets · Conviction ' + cv.score + '/10">🐋 KONSENS ' + cv.cluster + '</span>', cv };
  if (cv.sideUsd >= 5000) return { chip: '<span class="pw-wh pw-wh-soft" title="Großgeld auf dieser Seite · Conviction ' + cv.score + '/10">🐋 ' + _pwUsd(cv.sideUsd) + '</span>', cv };
  return { chip: '', cv };
}

// ── 2. DRILLDOWN (im aufgeklappten Edge-Row) ─────────────────────────────────
function _pwRenderDrill(e, teams, wallets) {
  const match = (wallets && wallets.matches && wallets.matches[e.key]) || null;
  const sides = [
    { s: 'home', label: (match && match.home) || e.homeId, col: _pwSideCol('home') },
    { s: 'draw', label: 'Remis', col: _pwSideCol('draw') },
    { s: 'away', label: (match && match.away) || e.awayId, col: _pwSideCol('away') },
  ];
  // Whale-$ je Seite
  const pos = (match && match.topPositions) || [];
  const usdBy = { home: 0, draw: 0, away: 0 };
  pos.forEach(p => { if (usdBy[p.side] != null) usdBy[p.side] += (p.usd || 0); });
  const totUsd = usdBy.home + usdBy.draw + usdBy.away;

  let h = '<div class="pw-drill" onclick="event.stopPropagation()">';
  // Geldverteilung-Balken
  h += '<div class="pw-drill-t">Smart-Money-Verteilung (1X2)</div>';
  if (totUsd > 0) {
    h += '<div class="pw-splitbar">';
    sides.forEach(sd => {
      const pct = totUsd ? (usdBy[sd.s] / totUsd * 100) : 0;
      if (pct > 0) h += '<div class="pw-split" style="width:' + pct.toFixed(1) + '%;background:' + sd.col + '" title="' + sd.label + ' ' + _pwUsd(usdBy[sd.s]) + '"></div>';
    });
    h += '</div><div class="pw-split-legend">';
    sides.forEach(sd => { h += '<span><i style="background:' + sd.col + '"></i>' + sd.label + ' ' + _pwUsd(usdBy[sd.s]) + '</span>'; });
    h += '</div>';
  } else {
    h += '<div class="pw-none-sm">Keine erfassten Whale-Positionen für dieses Match.</div>';
  }
  // Conviction je Seite
  h += '<div class="pw-conv-grid">';
  sides.forEach(sd => {
    const cv = _pwConviction(wallets, e.key, sd.s);
    const sc = cv ? cv.score : 0;
    h += '<div class="pw-conv"><div class="pw-conv-lbl" style="color:' + sd.col + '">' + sd.label + '</div>'
      + '<div class="pw-conv-bar"><i style="width:' + (sc * 10) + '%;background:' + sd.col + '"></i></div>'
      + '<div class="pw-conv-meta">' + (cv ? ('Conv ' + sc + '/10 · ' + (cv.cluster || 0) + ' Wallets · Flow ' + (cv.net >= 0 ? '+' : '−') + _pwUsd(Math.abs(cv.net)).slice(1)) : '—') + '</div></div>';
  });
  h += '</div>';
  // Top-Whales dieses Matches
  const top = pos.slice().sort((a, b) => b.usd - a.usd).slice(0, 6);
  if (top.length) {
    h += '<div class="pw-drill-t">Größte Wallets hier</div><div class="pw-whales">';
    top.forEach(p => {
      h += '<div class="pw-whale"><a href="' + _pwLink(p.wallet) + '" target="_blank" rel="noopener">' + _pwWallet(p.wallet) + '</a>'
        + '<span style="color:' + _pwSideCol(p.side) + '">' + (p.pick || p.side) + '</span>'
        + '<b>' + _pwUsd(p.usd) + '</b></div>';
    });
    h += '</div>';
  }
  h += '</div>';
  return h;
}

// ── 3. EXIT-WATCH (Net-Flow-Veto) ────────────────────────────────────────────
function _pwRenderExitWatch(wallets, teams) {
  const cl = (wallets && wallets.clustersAll) || [];
  const exits = cl.filter(c => (c.netFlowUsd || 0) <= -2000 && typeof c.hoursToKickoff === 'number' && c.hoursToKickoff >= 0 && c.hoursToKickoff <= 24)
    .sort((a, b) => (a.netFlowUsd || 0) - (b.netFlowUsd || 0));
  if (!exits.length) return '';
  let h = '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker pw-red">⚠️ Exit-Liquidität</span>'
    + '<span class="pw-sec-note">Whales laufen nah am Anpfiff netto RAUS — Veto für Trades in diese Seite</span></div><div class="pw-board">';
  exits.forEach(c => {
    const koLbl = c.hoursToKickoff < 1 ? '<1h' : Math.round(c.hoursToKickoff) + 'h';
    h += '<div class="pw-row pw-row-veto"><div class="pw-row-main">'
      + '<div class="pw-teams"><span class="pw-flag">⚠️</span><div class="pw-tk">'
      + '<div class="pw-ticket" style="color:' + _pwSideCol(c.side) + '">' + (c.pick || c.side) + '</div>'
      + '<div class="pw-match">' + (c.match || c.key) + ' · <span class="pw-ko">Anpfiff in ' + koLbl + '</span></div></div></div>'
      + '<div class="pw-edge"><div class="pw-edge-n pw-noise">' + _pwPP((c.netFlowUsd || 0) / 1000) + 'K</div>'
      + '<div class="pw-chips"><span class="pw-wh pw-wh-fade">🐋 EXIT</span></div></div>'
      + '</div></div>';
  });
  h += '</div></section>';
  return h;
}

// ── 4. FLOW-TAPE ─────────────────────────────────────────────────────────────
function _pwRenderFlowTape(wallets, teams) {
  const tr = (wallets && wallets.bigTradesAll) || [];
  if (!tr.length) return '';
  let h = '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">📟 Flow-Tape</span>'
    + '<span class="pw-sec-note">Jüngste große Trades — sagt dir, ob die Edge frisch ist oder schon gegessen</span></div><div class="pw-tape">';
  tr.slice(0, 25).forEach(t => {
    const buy = (t.action || '').toUpperCase() === 'BUY';
    h += '<div class="pw-tp-row"><span class="pw-tp-act ' + (buy ? 'pw-buy' : 'pw-sell') + '">' + (buy ? 'KAUF' : 'VERK') + '</span>'
      + '<div class="pw-tp-mid"><a href="' + _pwLink(t.wallet) + '" target="_blank" rel="noopener">' + _pwWallet(t.wallet) + '</a>'
      + '<span style="color:' + _pwSideCol(t.side) + '">' + (t.pick || t.side) + '</span> · ' + (t.match || t.key)
      + (t.price ? ' @' + Math.round(t.price * 100) + '¢' : '') + (_pwAgo(t.ts) ? ' · ' + _pwAgo(t.ts) : '') + '</div>'
      + '<b>' + _pwUsd(t.usd) + '</b></div>';
  });
  h += '</div></section>';
  return h;
}

// ── 5. WHALE-LEADERBOARD (zuletzt) ───────────────────────────────────────────
function _pwRenderLeaderboard(wallets, teams) {
  const pos = (wallets && wallets.topPositionsAll) || [];
  if (!pos.length) return '';
  let h = '<section class="pw-sec"><div class="pw-sec-head"><span class="pw-kicker">🏦 Whale-Leaderboard</span>'
    + '<span class="pw-sec-note">Größte Einzelpositionen (Discovery — nicht handeln, nur beobachten)</span></div><div class="pw-lb">';
  pos.slice(0, 20).forEach((p, i) => {
    h += '<div class="pw-lb-row"><span class="pw-rank ' + (i < 3 ? 'pw-rank-top' : '') + '">' + (i + 1) + '</span>'
      + '<div class="pw-lb-mid"><a href="' + _pwLink(p.wallet) + '" target="_blank" rel="noopener">' + _pwWallet(p.wallet) + '</a>'
      + '<div class="pw-lb-sub"><span style="color:' + _pwSideCol(p.side) + '">' + (p.pick || p.side) + '</span> · ' + (p.match || p.key) + '</div></div>'
      + '<b>' + _pwUsd(p.usd) + '</b></div>';
  });
  h += '</div></section>';
  return h;
}

function _pwSideCol(side) {
  return side === 'home' ? '#4cc2ff'
    : side === 'away' ? '#ff5d5d'
    : side === 'draw' ? '#f5c518'
    : (side === 'over' || side === 'bttsY') ? '#2dd47e'
    : (side === 'under' || side === 'bttsN') ? '#a78bfa'
    : '#e6ebf5';
}

// Toggle Drilldown (global, weil innerHTML neu gebaut wird) — rendert aus dem Cache, KEIN Refetch.
function _pwToggle(id) {
  _pwState.open = (_pwState.open === id) ? null : id;
  const panel = document.getElementById('polyWalletsPanel');
  if (!panel || !_pwCache) return;
  try { renderPolyDashboard(panel, _pwCache.wm, _pwCache.prices, _pwCache.wallets); }
  catch (e) { /* ignore */ }
}

// ── Styles (einmalig, scoped auf #polyWalletsPanel) ─────────────────────────
function _pwInjectStyle() {
  if (document.getElementById('pw-style')) return;
  const css = `
  #polyWalletsPanel{color:#e6ebf5;font-family:inherit}
  #polyWalletsPanel .pw-loading,#polyWalletsPanel .pw-empty{text-align:center;color:#76819c;padding:48px 16px;line-height:1.7}
  #polyWalletsPanel .pw-empty-ico{font-size:44px;margin-bottom:10px}
  #polyWalletsPanel .pw-empty h2{color:#e6ebf5;margin:0 0 8px}
  #polyWalletsPanel code{background:#0f1626;padding:2px 6px;border-radius:5px;font-size:12px;color:#9db2d6}
  #polyWalletsPanel .pw-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;margin-bottom:26px}
  #polyWalletsPanel .pw-head h1{font-size:24px;font-weight:800;margin:0 0 6px}
  #polyWalletsPanel .pw-accent{color:#5eead4}
  #polyWalletsPanel .pw-sub{color:#8a95ad;font-size:13px;line-height:1.6;margin:0;max-width:640px}
  #polyWalletsPanel .pw-sub b{color:#cdd6ea}
  #polyWalletsPanel .pw-stamp{color:#76819c;font-size:12px;text-align:right;white-space:nowrap}
  #polyWalletsPanel .pw-stamp span{color:#4b566e;font-size:11px}
  #polyWalletsPanel .pw-sec{margin-bottom:32px}
  #polyWalletsPanel .pw-sec-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:12px}
  #polyWalletsPanel .pw-kicker{font-size:12px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:#5eead4;background:rgba(94,234,212,.1);padding:4px 10px;border-radius:7px}
  #polyWalletsPanel .pw-kicker.pw-red{color:#ff8a6d;background:rgba(255,123,93,.12)}
  #polyWalletsPanel .pw-sec-note{color:#76819c;font-size:12px}
  #polyWalletsPanel .pw-board{display:flex;flex-direction:column;gap:9px}
  #polyWalletsPanel .pw-row{background:linear-gradient(180deg,#111a2b,#0e1524);border:1px solid rgba(255,255,255,.06);border-radius:14px;overflow:hidden;cursor:pointer;transition:border-color .15s,transform .05s}
  #polyWalletsPanel .pw-row:hover{border-color:rgba(94,234,212,.35)}
  #polyWalletsPanel .pw-row-open{border-color:rgba(94,234,212,.5)}
  #polyWalletsPanel .pw-row-veto{border-color:rgba(255,123,93,.3)}
  #polyWalletsPanel .pw-row-main{display:grid;grid-template-columns:1.5fr 1.1fr auto;gap:14px;align-items:center;padding:13px 16px}
  #polyWalletsPanel .pw-teams{display:flex;align-items:center;gap:8px;min-width:0}
  #polyWalletsPanel .pw-flag{font-size:20px;line-height:1}
  #polyWalletsPanel .pw-logo{width:22px;height:22px;border-radius:50%;object-fit:cover;background:#0f1626;vertical-align:middle}
  #polyWalletsPanel .pw-tk{min-width:0}
  #polyWalletsPanel .pw-ticket{font-weight:700;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #polyWalletsPanel .pw-match{font-size:11.5px;color:#76819c;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}
  #polyWalletsPanel .pw-ko{color:#9db2d6}
  #polyWalletsPanel .pw-probs{display:flex;align-items:center;gap:9px;justify-content:center}
  #polyWalletsPanel .pw-prob{text-align:center}
  #polyWalletsPanel .pw-prob span{display:block;font-size:9.5px;text-transform:uppercase;letter-spacing:.5px;color:#5b667e}
  #polyWalletsPanel .pw-prob b{font-family:ui-monospace,monospace;font-size:16px;color:#c6d0e4}
  #polyWalletsPanel .pw-prob b.pw-fair{color:#5eead4}
  #polyWalletsPanel .pw-arrow{color:#414c66;font-size:14px}
  #polyWalletsPanel .pw-edge{display:flex;flex-direction:column;align-items:flex-end;gap:5px;min-width:96px}
  #polyWalletsPanel .pw-edge-n{font-family:ui-monospace,monospace;font-weight:800;font-size:19px}
  #polyWalletsPanel .pw-trade{color:#2dd47e}
  #polyWalletsPanel .pw-thin{color:#f5c518}
  #polyWalletsPanel .pw-noise{color:#76819c}
  #polyWalletsPanel .pw-chips{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}
  #polyWalletsPanel .pw-vd{font-size:9.5px;font-weight:800;padding:2px 7px;border-radius:5px;letter-spacing:.5px}
  #polyWalletsPanel .pw-vd.pw-trade{background:rgba(45,212,126,.16);color:#2dd47e}
  #polyWalletsPanel .pw-vd.pw-thin{background:rgba(245,197,24,.14);color:#f5c518}
  #polyWalletsPanel .pw-vd.pw-noise{background:rgba(118,129,156,.14);color:#8a95ad}
  #polyWalletsPanel .pw-liq{font-size:12px}
  #polyWalletsPanel .pw-fresh{font-size:9.5px;font-weight:800;padding:2px 7px;border-radius:5px;background:rgba(255,138,109,.16);color:#ff8a6d}
  #polyWalletsPanel .pw-wh{font-size:9.5px;font-weight:800;padding:2px 7px;border-radius:5px;white-space:nowrap}
  #polyWalletsPanel .pw-wh-conf{background:rgba(94,234,212,.16);color:#5eead4}
  #polyWalletsPanel .pw-wh-soft{background:rgba(167,139,250,.16);color:#a78bfa}
  #polyWalletsPanel .pw-wh-fade{background:rgba(255,93,93,.16);color:#ff7b7b}
  #polyWalletsPanel .pw-drill{border-top:1px solid rgba(255,255,255,.06);padding:14px 16px;background:#0c121f;cursor:default}
  #polyWalletsPanel .pw-drill-t{font-size:10.5px;font-weight:800;text-transform:uppercase;letter-spacing:.6px;color:#5eead4;margin:2px 0 8px}
  #polyWalletsPanel .pw-splitbar{display:flex;height:12px;border-radius:6px;overflow:hidden;background:#0f1626}
  #polyWalletsPanel .pw-split{height:100%}
  #polyWalletsPanel .pw-split-legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:7px;font-size:11.5px;color:#9db2d6}
  #polyWalletsPanel .pw-split-legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:middle}
  #polyWalletsPanel .pw-conv-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0}
  #polyWalletsPanel .pw-conv-lbl{font-size:12px;font-weight:700;margin-bottom:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #polyWalletsPanel .pw-conv-bar{height:6px;border-radius:3px;background:#0f1626;overflow:hidden}
  #polyWalletsPanel .pw-conv-bar i{display:block;height:100%}
  #polyWalletsPanel .pw-conv-meta{font-size:10.5px;color:#76819c;margin-top:4px}
  #polyWalletsPanel .pw-whales{display:flex;flex-direction:column;gap:5px}
  #polyWalletsPanel .pw-whale{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;font-size:12.5px}
  #polyWalletsPanel .pw-whale a{font-family:ui-monospace,monospace;color:#c6d0e4;text-decoration:none;border-bottom:1px dashed #414c66}
  #polyWalletsPanel .pw-whale b{font-family:ui-monospace,monospace}
  #polyWalletsPanel .pw-tape,#polyWalletsPanel .pw-lb{display:flex;flex-direction:column;gap:6px}
  #polyWalletsPanel .pw-tp-row,#polyWalletsPanel .pw-lb-row{display:grid;grid-template-columns:auto 1fr auto;gap:11px;align-items:center;background:#0f1626;border:1px solid rgba(255,255,255,.05);border-radius:11px;padding:10px 13px}
  #polyWalletsPanel .pw-tp-act{font-size:10px;font-weight:800;padding:3px 8px;border-radius:6px}
  #polyWalletsPanel .pw-buy{background:rgba(45,212,126,.14);color:#2dd47e}
  #polyWalletsPanel .pw-sell{background:rgba(255,93,93,.14);color:#ff5d5d}
  #polyWalletsPanel .pw-tp-mid,#polyWalletsPanel .pw-lb-mid{min-width:0;font-size:12px;color:#9db2d6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  #polyWalletsPanel .pw-tp-mid a,#polyWalletsPanel .pw-lb-mid a{font-family:ui-monospace,monospace;color:#e6ebf5;text-decoration:none;border-bottom:1px dashed #414c66;margin-right:6px}
  #polyWalletsPanel .pw-tp-row b,#polyWalletsPanel .pw-lb-row b{font-family:ui-monospace,monospace;font-weight:800;white-space:nowrap}
  #polyWalletsPanel .pw-lb-sub{font-size:11px;color:#76819c;margin-top:1px}
  #polyWalletsPanel .pw-rank{font-family:ui-monospace,monospace;font-weight:800;color:#414c66;font-size:13px;min-width:20px}
  #polyWalletsPanel .pw-rank-top{color:#5eead4}
  #polyWalletsPanel .pw-none,#polyWalletsPanel .pw-none-sm{color:#76819c;font-size:13px;background:#0f1626;border:1px dashed rgba(255,255,255,.08);border-radius:12px;padding:16px}
  #polyWalletsPanel .pw-none-sm{padding:10px;font-size:12px}
  @media(max-width:620px){
    #polyWalletsPanel .pw-row-main{grid-template-columns:1fr auto;gap:10px}
    #polyWalletsPanel .pw-probs{display:none}
    #polyWalletsPanel .pw-conv-grid{grid-template-columns:1fr}
  }`;
  const st = document.createElement('style');
  st.id = 'pw-style';
  st.textContent = css;
  document.head.appendChild(st);
}
