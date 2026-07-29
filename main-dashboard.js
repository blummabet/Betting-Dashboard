/* main-dashboard.js — MAIN-Dashboard „Übersicht" (29.07.2026, Lucas) ─────────────────────
 * Kuratiertes Cockpit als Einstieg: die stärksten Signale je Engine kompakt auf einen Blick.
 * Kacheln: Beste Cards · Beste Streaks · Betfair-Kohle · Poly-Whales · Sharp-Radar.
 * Triple/Konsens-Hero als Platzhalter (kommt als eigene Kachel, sobald die Konsens-Logik steht).
 * Lädt die Datendateien selbst (cache-gebustet). Jede Kachel führt per Klick in den vollen Bereich.
 * ────────────────────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  var _md = { data: null, loading: false };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]; }); }
  function eur(v) { v = +v || 0; if (v >= 1e6) return '€' + (v / 1e6).toFixed(2) + 'M'; if (v >= 1e3) return '€' + (v / 1e3).toFixed(v >= 1e5 ? 0 : 1).replace('.0', '') + 'K'; return '€' + Math.round(v); }
  function usd(v) { v = +v || 0; if (v >= 1e6) return '$' + (v / 1e6).toFixed(2) + 'M'; if (v >= 1e3) return '$' + (v / 1e3).toFixed(v >= 1e5 ? 0 : 1).replace('.0', '') + 'K'; return '$' + Math.round(v); }
  function team(x) { if (!x) return '?'; if (typeof x === 'string') return x; return x.name || x.team || x.id || '?'; }
  function short(k) {
    return String(k || '').replace('Over/Under', 'Ü/U').replace(' Goals', '').replace('Both teams to Score?', 'BTTS')
      .replace('Match Odds', '1X2').replace('First Half', 'HZ1').replace('Half Time/Full Time', 'HZ/EZ')
      .replace('Half Time', 'HZ1').replace('Correct Score', 'Exakt').replace('Draw no Bet', 'DNB');
  }

  function _mdFetch() {
    var b = '?t=' + Date.now();
    var jf = function (u) { return fetch(u + b, { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); };
    return Promise.all([jf('liga-data.json'), jf('mls-data.json'), jf('liga_streaks.json'),
      jf('mls_streaks.json'), jf('betfair_prices.json'), jf('poly_money_broad_close.json')]);
  }
  function _mdLoad(force) {
    if (_md.loading) return;
    if (_md.data && !force) { _mdRender(); return; }
    _md.loading = true;
    var p = document.getElementById('mainDashPanel');
    if (p && !_md.data) p.innerHTML = _head() + '<div style="padding:48px 0;text-align:center;color:var(--muted);font-size:13px;">⏳ Übersicht wird geladen …</div>';
    _mdFetch().then(function (a) {
      _md.data = { liga: a[0], mls: a[1], ligaStreaks: a[2], mlsStreaks: a[3], betfair: a[4], whales: a[5] };
      _md.loading = false; _mdRender();
    });
  }
  window._mdLoad = _mdLoad;

  // ── Daten-Extraktion ──────────────────────────────────────────────────────
  function fixtures(data) {
    var out = [];
    (function walk(o) {
      if (!o || typeof o !== 'object') return;
      if (Array.isArray(o)) { o.forEach(walk); return; }
      if (Array.isArray(o.picks) && (o.home || o.homeTeam)) out.push(o);
      for (var k in o) walk(o[k]);
    })(data);
    return out;
  }
  function allFixtures() { return fixtures(_md.data.liga).concat(fixtures(_md.data.mls)); }
  function fxLeague(f) { return f.leagueName || f.league || (f.group || ''); }

  function bestCards() {
    var rows = [];
    allFixtures().forEach(function (f) {
      (f.picks || []).forEach(function (p) {
        if (p.verdict === 'BET') rows.push({ f: f, p: p, conv: +p.convictionScore || 0 });
      });
    });
    rows.sort(function (a, b) { return (b.conv - a.conv) || ((+b.p.edgePP || 0) - (+a.p.edgePP || 0)); });
    return rows.slice(0, 4);
  }
  function bestStreaks() {
    var s = [];
    [_md.data.ligaStreaks, _md.data.mlsStreaks].forEach(function (d) { if (d && Array.isArray(d.streaks)) s = s.concat(d.streaks); });
    s = s.filter(function (x) { return (+x.length || 0) >= 4; });
    s.sort(function (a, b) { var ra = (a.continuation && a.continuation.ratePct) || 0, rb = (b.continuation && b.continuation.ratePct) || 0; return ((+b.length || 0) - (+a.length || 0)) || (rb - ra); });
    return s.slice(0, 4);
  }
  function bestBetfair() {
    var ms = (_md.data.betfair && _md.data.betfair.matches) || [], rows = [];
    ms.forEach(function (m) {
      var best = null, mk = m.markets || {};
      for (var name in mk) {
        var rs = mk[name].runners || [];
        var tot = rs.reduce(function (a, r) { return a + (+r.vol || 0); }, 0);
        if (tot <= 0) continue;
        var lead = rs.reduce(function (a, r) { return (!a || (+r.vol || 0) > (+a.vol || 0)) ? r : a; }, null);
        if (!lead) continue;
        var share = (+lead.vol || 0) / tot, sc = (+lead.vol || 0) * share;
        if (!best || sc > best.sc) best = { name: name, lead: lead, share: share, vol: +lead.vol || 0, sc: sc };
      }
      if (best && best.vol >= 3000) rows.push({ m: m, b: best });
    });
    rows.sort(function (a, b) { return b.b.sc - a.b.sc; });
    return rows.slice(0, 4);
  }
  function bestWhales() {
    var w = _md.data.whales || {}, all = [];
    for (var k in w) {
      var mk = w[k];
      if (mk && Array.isArray(mk.whales)) mk.whales.forEach(function (wh) {
        all.push({ usd: +wh.usd || 0, side: wh.side, league: mk.league, hrs: mk.hoursToKickoff });
      });
    }
    all.sort(function (a, b) { return b.usd - a.usd; });
    return all.slice(0, 4);
  }
  function bestSharp() {
    var rows = [];
    allFixtures().forEach(function (f) {
      (f.picks || []).forEach(function (p) {
        if (p.source === 'steam' && p.steamMovePP != null) rows.push({ f: f, p: p, mv: Math.abs(+p.steamMovePP || 0) });
      });
    });
    rows.sort(function (a, b) { return b.mv - a.mv; });
    return rows.slice(0, 4);
  }

  // ── Render-Bausteine ──────────────────────────────────────────────────────
  function _head() {
    return '<div style="max-width:1180px;margin:0 auto 4px;padding:4px 2px;">' +
      '<div style="font-family:\'Anton\',sans-serif,system-ui;font-size:26px;letter-spacing:.02em;text-transform:uppercase;color:var(--text);">Übersicht</div>' +
      '<div style="font-size:12.5px;color:var(--muted);margin-top:2px;">Die stärksten Signale aller Engines — kompakt, für den schnellen Überblick.</div></div>';
  }
  function tile(icon, title, accent, moreView, moreLbl, bodyHtml) {
    var more = moreView ? '<button onclick="showView(\'' + moreView + '\')" style="margin-left:auto;background:none;border:0;color:' + accent + ';font-size:11.5px;font-weight:700;cursor:pointer;">' + (moreLbl || 'alle') + ' →</button>' : '';
    return '<section style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:13px 15px;display:flex;flex-direction:column;min-width:0;">' +
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">' +
        '<span style="font-size:16px;">' + icon + '</span>' +
        '<span style="font-weight:800;font-size:13.5px;color:var(--text);letter-spacing:.01em;">' + title + '</span>' + more +
      '</div>' + bodyHtml + '</section>';
  }
  function empty(txt) { return '<div style="color:var(--muted);font-size:12px;padding:8px 2px;">' + (txt || 'Aktuell nichts.') + '</div>'; }
  function row(main, right, sub, accent) {
    return '<div style="display:flex;align-items:baseline;gap:8px;padding:7px 0;border-top:1px solid var(--border);">' +
      '<div style="min-width:0;flex:1;">' +
        '<div style="font-size:13px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + main + '</div>' +
        (sub ? '<div style="font-size:11px;color:var(--muted);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + sub + '</div>' : '') +
      '</div>' +
      (right ? '<div style="font-family:ui-monospace,monospace;font-size:12.5px;font-weight:800;color:' + (accent || 'var(--text)') + ';white-space:nowrap;">' + right + '</div>' : '') +
    '</div>';
  }

  function _mdRender() {
    var p = document.getElementById('mainDashPanel');
    if (!p) return;
    if (!_md.data) { _mdLoad(); return; }
    var A = { gold: '#ffb80c', teal: '#2dd4bf', purp: '#a78bfa', blue: '#4cc2ff', green: '#3fb950', red: '#f85149' };

    // Triple-Hero (Platzhalter, kommt als eigene Kachel)
    var hero = '<section style="grid-column:1/-1;background:linear-gradient(135deg,rgba(76,194,255,.08),rgba(167,139,250,.06));border:1px solid rgba(76,194,255,.28);border-radius:14px;padding:15px 17px;">' +
      '<div style="display:flex;align-items:center;gap:9px;flex-wrap:wrap;">' +
        '<span style="font-size:19px;">⚖️</span>' +
        '<span style="font-weight:800;font-size:15px;color:var(--text);">Triple-Konsens</span>' +
        '<span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px;background:rgba(255,184,12,.14);color:' + A.gold + ';">in Arbeit</span>' +
      '</div>' +
      '<div style="font-size:12.5px;color:var(--muted);margin-top:6px;line-height:1.55;max-width:760px;">Wo <b style="color:' + A.teal + '">Pinnacle</b>, <b style="color:#a7c7ff">Betfair</b>, <b style="color:' + A.purp + '">Polymarket</b> und die <b>Softbooks</b> einer Meinung sind (hohe Konfidenz) — und wo einer ausschert (Value-Kandidat). Kommt als nächste Kachel hier oben.</div></section>';

    // Cards
    var c = bestCards();
    var cardsBody = c.length ? c.map(function (x) {
      var f = x.f, p = x.p;
      var conv = x.conv ? '<span title="Conviction">' + x.conv + '/10</span>' : (p.odds != null ? '@' + (+p.odds).toFixed(2) : '');
      return row(esc(team(f.home)) + ' <span style="color:var(--muted);font-weight:400">v</span> ' + esc(team(f.away)),
        conv, esc(short(p.market)) + (fxLeague(f) ? ' · ' + esc(String(fxLeague(f)).slice(0, 22)) : '') + (p.edgePP != null ? ' · +' + Math.round(+p.edgePP) + 'pp' : ''), A.green);
    }).join('') : empty('Keine BET-Cards gerade.');

    // Streaks
    var st = bestStreaks();
    var streaksBody = st.length ? st.map(function (s) {
      var rate = s.continuation && s.continuation.ratePct != null ? s.continuation.ratePct + '%' : '';
      return row(esc(team(s.team)) + ' <span style="color:var(--muted);font-weight:400">·</span> ' + esc(s.market || s.type || ''),
        (s.length || 0) + '×', esc(String(s.leagueName || '')) + (s.continuation && s.continuation.state ? ' · ' + esc(s.continuation.state) : ''), A.gold) +
        '';
    }).join('') : empty('Keine langen Serien.');

    // Betfair
    var bf = bestBetfair();
    var bfBody = bf.length ? bf.map(function (x) {
      var m = x.m, b = x.b;
      return row(esc(team(m.home)) + ' <span style="color:var(--muted);font-weight:400">v</span> ' + esc(team(m.away)),
        eur(b.vol), esc(short(b.name)) + ' → ' + esc(b.lead.name) + ' · ' + Math.round(b.share * 100) + '%', '#a7c7ff');
    }).join('') : empty('Kein großes Betfair-Geld.');

    // Whales
    var wh = bestWhales();
    var whBody = wh.length ? wh.map(function (w) {
      var hrs = (w.hrs != null && w.hrs >= 0) ? (w.hrs < 1 ? '<1h' : Math.round(w.hrs) + 'h') : '';
      return row(esc(w.side || '?'), usd(w.usd), esc(String(w.league || '')) + (hrs ? ' · in ' + hrs : ''), A.purp);
    }).join('') : empty('Keine Whale-Bets.');

    // Sharp
    var sh = bestSharp();
    var shBody = sh.length ? sh.map(function (x) {
      var f = x.f, p = x.p, mv = +p.steamMovePP || 0;
      return row(esc(team(f.home)) + ' <span style="color:var(--muted);font-weight:400">v</span> ' + esc(team(f.away)),
        (mv > 0 ? '+' : '') + mv.toFixed(1) + 'pp', esc(short(p.market)) + (p.odds != null ? ' · @' + (+p.odds).toFixed(2) : ''), mv > 0 ? A.green : A.red);
    }).join('') : empty('Keine Steam-Moves.');

    var grid = '<div style="max-width:1180px;margin:10px auto 0;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;">' +
      hero +
      tile('🎯', 'Beste Cards', A.green, 'national-cards', 'alle Cards', cardsBody) +
      tile('🔥', 'Beste Streaks', A.gold, 'national-streaks', 'alle Serien', streaksBody) +
      tile('💷', 'Betfair-Kohle', '#a7c7ff', 'betfair', 'Radar', bfBody) +
      tile('🐋', 'Poly Whale-Bets', A.purp, 'polywallets', 'Wallets', whBody) +
      tile('📡', 'Sharp-Radar', A.blue, 'sharp', 'Radar', shBody) +
      '</div>';

    p.innerHTML = _head() + grid +
      '<div style="max-width:1180px;margin:14px auto 0;text-align:center;color:var(--muted);font-size:11px;">Kuratierter Überblick · tippe eine Kachel-Überschrift für den vollen Bereich</div>';
  }
  window._renderMainDash = _mdRender;
  window._mdState = _md;   // Test-Hook
})();
