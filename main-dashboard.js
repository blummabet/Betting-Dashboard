/* main-dashboard.js — MAIN-Dashboard „Übersicht" · Command-Center (29.07.2026, Lucas) ─────
 * „Großer Design-Sprung": kuratiertes Cockpit als Einstieg. Eigenes, in sich geschlossenes
 * Design-System (md-*), injiziert per <style>. Farben CVD-validiert (dataviz-Skill):
 *   Pinnacle #3987e5 · Betfair #d95926 · Poly #199e70 · Soft #c98500.
 * Bausteine: KPI-Leiste · Triple-Konsens-Hero mit 4-Quellen-Zustimmungsbalken · Signal-Kacheln
 * mit Mini-Visualisierungen (Conviction-Meter, Anteilsbalken, Steam-Divergenzbalken).
 * Lädt die Datendateien selbst (cache-gebustet). Jede Kachel führt per Klick in den vollen Bereich.
 * ────────────────────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  var _md = { data: null, loading: false };

  // ── validierte Palette (dataviz-Skill, --mode dark, ALL CHECKS PASS) ──────────
  var A = {
    pinn: '#3987e5', bf: '#d95926', poly: '#199e70', soft: '#c98500',
    good: '#2ea043', gold: '#c98500', blue: '#3987e5', aqua: '#199e70',
    red: '#e5534b', ink: '#f0f4f8', ink2: '#9aa4b1', ink3: '#6b7480'
  };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]; }); }
  function eur(v) { v = +v || 0; if (v >= 1e6) return '€' + (v / 1e6).toFixed(2) + 'M'; if (v >= 1e3) return '€' + (v / 1e3).toFixed(v >= 1e5 ? 0 : 1).replace('.0', '') + 'K'; return '€' + Math.round(v); }
  function usd(v) { v = +v || 0; if (v >= 1e6) return '$' + (v / 1e6).toFixed(2) + 'M'; if (v >= 1e3) return '$' + (v / 1e3).toFixed(v >= 1e5 ? 0 : 1).replace('.0', '') + 'K'; return '$' + Math.round(v); }
  function team(x) { if (!x) return '?'; if (typeof x === 'string') return x; return x.name || x.team || x.id || '?'; }
  function short(k) {
    return String(k || '').replace('Over/Under', 'Ü/U').replace(' Goals', '').replace('Both teams to Score?', 'BTTS')
      .replace('Match Odds', '1X2').replace('First Half', 'HZ1').replace('Half Time/Full Time', 'HZ/EZ')
      .replace('Half Time', 'HZ1').replace('Correct Score', 'Exakt').replace('Draw no Bet', 'DNB');
  }
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }

  // ── Länderflaggen ─────────────────────────────────────────────────────────────
  // Quellen liefern Land unterschiedlich: Betfair `country` = ISO-2 ("EC","GB"),
  // Streaks/Fixtures `league` = ISO-3 ("ENG","GER"), Whales `league` = Sport-Kürzel ("MLB").
  function _iso2(cc) {
    cc = String(cc || '').toUpperCase();
    if (cc.length !== 2 || /[^A-Z]/.test(cc)) return '';
    try { return String.fromCodePoint(0x1F1E6 + cc.charCodeAt(0) - 65, 0x1F1E6 + cc.charCodeAt(1) - 65); } catch (e) { return ''; }
  }
  var _ISO3 = {
    GER: '🇩🇪', ENG: '🏴󠁧󠁢󠁥󠁮󠁧󠁿', ESP: '🇪🇸', ITA: '🇮🇹', FRA: '🇫🇷', NED: '🇳🇱', POR: '🇵🇹',
    USA: '🇺🇸', MEX: '🇲🇽', CAN: '🇨🇦', BRA: '🇧🇷', ARG: '🇦🇷', BEL: '🇧🇪', SCO: '🏴󠁧󠁢󠁳󠁣󠁴󠁿', SCT: '🏴󠁧󠁢󠁳󠁣󠁴󠁿',
    WAL: '🏴󠁧󠁢󠁷󠁬󠁳󠁿', NIR: '🇬🇧', IRL: '🇮🇪', TUR: '🇹🇷', GRE: '🇬🇷', SUI: '🇨🇭', AUT: '🇦🇹', DEN: '🇩🇰',
    SWE: '🇸🇪', NOR: '🇳🇴', ISL: '🇮🇸', POL: '🇵🇱', UKR: '🇺🇦', RUS: '🇷🇺', CRO: '🇭🇷', SRB: '🇷🇸',
    CZE: '🇨🇿', ROU: '🇷🇴', HUN: '🇭🇺', JPN: '🇯🇵', KOR: '🇰🇷', AUS: '🇦🇺', ECU: '🇪🇨', PAR: '🇵🇾',
    URU: '🇺🇾', CHI: '🇨🇱', COL: '🇨🇴', PER: '🇵🇪', VEN: '🇻🇪'
  };
  var _ABBR = { MLB: '🇺🇸', NBA: '🇺🇸', NFL: '🇺🇸', NHL: '🇺🇸', MLS: '🇺🇸', WNBA: '🇺🇸', CFL: '🇨🇦', EPL: '🏴󠁧󠁢󠁥󠁮󠁧󠁿', WM: '🌍', 'WORLD CUP': '🌍' };
  var _NAME = [
    [/champions league|europa league|europa conference|conference league|uefa/i, '🇪🇺'],
    [/bundesliga|german/i, '🇩🇪'], [/premier league|championship|england|english/i, '🏴󠁧󠁢󠁥󠁮󠁧󠁿'],
    [/la ?liga|spanish|españa/i, '🇪🇸'], [/serie [ab]|italian|italy/i, '🇮🇹'], [/ligue ?[12]|french|france/i, '🇫🇷'],
    [/eredivisie|dutch|netherlands/i, '🇳🇱'], [/primeira|portug/i, '🇵🇹'], [/\bmls\b|major league soccer|united states/i, '🇺🇸'],
    [/liga mx|mexic/i, '🇲🇽'], [/brasil|brazil/i, '🇧🇷'], [/argentin/i, '🇦🇷'], [/scottish|scotland/i, '🏴󠁧󠁢󠁳󠁣󠁴󠁿'],
    [/turkish|süper|super lig/i, '🇹🇷'], [/belgian|belgium/i, '🇧🇪'], [/swiss|switzerland/i, '🇨🇭'],
    [/austrian|austria/i, '🇦🇹'], [/danish|denmark|superliga/i, '🇩🇰'], [/swedish|allsvenskan|sweden/i, '🇸🇪'],
    [/norwegian|eliteserien|norway/i, '🇳🇴'], [/icelandic|iceland/i, '🇮🇸'], [/ecuador/i, '🇪🇨'], [/paraguay/i, '🇵🇾'],
    [/venezuel/i, '🇻🇪'], [/colombia/i, '🇨🇴'], [/uruguay/i, '🇺🇾'], [/chile/i, '🇨🇱'], [/peru/i, '🇵🇪'],
    [/japanese|j.?league|japan/i, '🇯🇵'], [/korea/i, '🇰🇷'], [/australian|a.?league|australia/i, '🇦🇺'],
    [/concacaf|copa|conmebol/i, '🌎'], [/africa|\bcaf\b/i, '🌍'], [/international|friendl|women/i, '🌍']
  ];
  function _flagFrom(cc, code, name) {
    if (/champions league|europa league|europa conference|conference league|uefa/i.test(String(name || code || ''))) return '🇪🇺';
    var g = _iso2(cc); if (g) return g;
    var c = String(code || '').toUpperCase().trim();
    if (_ISO3[c]) return _ISO3[c];
    if (_ABBR[c]) return _ABBR[c];
    var n = String(name || '');
    for (var i = 0; i < _NAME.length; i++) if (_NAME[i][0].test(n)) return _NAME[i][1];
    return '🌍';
  }
  function fl(emoji) { return emoji ? '<span class="md-fl">' + emoji + '</span>' : ''; }
  function fxFlag(f) { return _flagFrom(f.country, f.league, f.leagueName || f.league || f.group); }

  // ── Design-System (einmalig injiziert) ────────────────────────────────────────
  function _mdStyle() {
    if (typeof document === 'undefined' || document.getElementById('mdash-css')) return;
    var css = [
      '.mdash{--mi:#f0f4f8;--mi2:#9aa4b1;--mi3:#6b7480;--m1:#151b24;--m2:#1b2430;--mln:#242c38;--mln2:#313b49;',
      '--pinn:#3987e5;--bf:#d95926;--poly:#199e70;--soft:#c98500;--good:#2ea043;--gold:#c98500;--sharp:#3987e5;--red:#e5534b;',
      'max-width:1200px;margin:0 auto;color:var(--mi);}',
      '.mdash *{box-sizing:border-box;}',
      '@keyframes mdUp{from{opacity:0;transform:translateY(9px);}to{opacity:1;transform:none;}}',
      '.mdash .md-rise{animation:mdUp .42s cubic-bezier(.22,.61,.36,1) both;}',
      '@media(prefers-reduced-motion:reduce){.mdash .md-rise{animation:none;}}',
      /* header */
      '.md-top{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;padding:2px 2px 0;flex-wrap:wrap;}',
      '.md-h1{font-family:"Anton",-apple-system,system-ui,sans-serif;font-weight:400;font-size:30px;line-height:1;letter-spacing:.01em;text-transform:uppercase;color:var(--mi);margin:0;}',
      '.md-sub{font-size:12.5px;color:var(--mi2);margin:6px 0 0;line-height:1.4;}',
      '.md-asof{font-size:11px;color:var(--mi3);white-space:nowrap;display:flex;align-items:center;gap:6px;}',
      '.md-asof b{font-family:"JetBrains Mono","SF Mono",Menlo,monospace;color:var(--mi2);font-weight:600;}',
      '.md-dot{width:6px;height:6px;border-radius:50%;background:var(--good);box-shadow:0 0 0 3px rgba(46,160,67,.16);}',
      /* KPI strip */
      '.md-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:16px;}',
      '@media(max-width:640px){.md-kpis{grid-template-columns:repeat(2,1fr);}}',
      '.md-kpi{background:var(--m1);border:1px solid var(--mln);border-radius:13px;padding:12px 13px 11px;position:relative;overflow:hidden;}',
      '.md-kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--kc,var(--mi3));}',
      '.md-kpi-v{font-family:"JetBrains Mono","SF Mono",Menlo,monospace;font-size:23px;font-weight:800;line-height:1;letter-spacing:-.02em;color:var(--mi);}',
      '.md-kpi-l{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--mi3);margin-top:7px;}',
      '.md-kpi-h{font-size:10.5px;color:var(--mi2);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      /* hero */
      '.md-hero{background:radial-gradient(120% 140% at 0% 0%,rgba(57,135,229,.10),transparent 55%),var(--m1);border:1px solid var(--mln2);border-radius:16px;padding:16px 18px;margin-top:14px;}',
      '.md-hero-top{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}',
      '.md-hero-ic{width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:16px;background:rgba(57,135,229,.14);border:1px solid rgba(57,135,229,.3);}',
      '.md-hero-t{font-weight:800;font-size:16px;letter-spacing:-.01em;color:var(--mi);}',
      '.md-hero-s{font-size:11.5px;color:var(--mi2);}',
      '.md-legend{display:flex;gap:13px;flex-wrap:wrap;margin-left:auto;}',
      '.md-lg{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--mi2);font-weight:600;}',
      '.md-lg i{width:9px;height:9px;border-radius:50%;display:inline-block;}',
      '.md-cols{display:flex;gap:20px;flex-wrap:wrap;margin-top:12px;}',
      '.md-col{flex:1;min-width:250px;}',
      '.md-col-h{font-size:10.5px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;margin:0 0 4px;display:flex;align-items:center;gap:6px;}',
      '.md-arow{padding:10px 0;border-top:1px solid var(--mln);}',
      '.md-arow:first-of-type{border-top:0;}',
      '.md-arow-t{font-size:12.5px;color:var(--mi);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      '.md-arow-m{font-size:11px;color:var(--mi2);margin-top:2px;}',
      /* agreement bar */
      '.md-agree{position:relative;height:22px;margin:8px 0 2px;}',
      '.md-agree-track{position:absolute;left:0;right:0;top:10px;height:2px;border-radius:2px;background:var(--mln2);}',
      '.md-agree-band{position:absolute;top:8px;height:6px;border-radius:3px;background:rgba(46,160,67,.22);border:1px solid rgba(46,160,67,.4);}',
      '.md-agree-band.div{background:rgba(201,133,0,.18);border-color:rgba(201,133,0,.4);}',
      '.md-agree-dot{position:absolute;top:4px;width:9px;height:9px;border-radius:50%;transform:translateX(-50%);box-shadow:0 0 0 2px var(--m1);}',
      '.md-agree-dot.out{top:2px;width:13px;height:13px;box-shadow:0 0 0 2px var(--m1),0 0 0 4px rgba(201,133,0,.35);}',
      '.md-agree-sc{position:absolute;top:0;font-family:"JetBrains Mono",monospace;font-size:9px;color:var(--mi3);transform:translateX(-50%);}',
      /* tiles */
      '.md-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(304px,1fr));gap:12px;margin-top:14px;}',
      '.md-tile{background:var(--m1);border:1px solid var(--mln);border-radius:14px;padding:13px 15px 6px;display:flex;flex-direction:column;min-width:0;transition:border-color .16s,transform .16s;}',
      '.md-tile:hover{border-color:var(--mln2);transform:translateY(-2px);}',
      '.md-tile-h{display:flex;align-items:center;gap:9px;margin-bottom:4px;}',
      '.md-tile-ic{width:26px;height:26px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px;background:var(--tb);border:1px solid var(--tbr);}',
      '.md-tile-t{font-weight:800;font-size:13.5px;letter-spacing:-.01em;color:var(--mi);}',
      '.md-more{margin-left:auto;background:none;border:0;color:var(--ta,var(--mi2));font-size:11px;font-weight:700;cursor:pointer;padding:3px 4px;border-radius:6px;font-family:inherit;transition:opacity .15s;}',
      '.md-more:hover{opacity:.7;}',
      '.md-r{display:flex;align-items:center;gap:10px;padding:9px 0;border-top:1px solid var(--mln);}',
      '.md-r-main{min-width:0;flex:1;}',
      '.md-r-t{font-size:13px;font-weight:600;color:var(--mi);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      '.md-r-s{font-size:11px;color:var(--mi2);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      '.md-r-v{font-family:"JetBrains Mono","SF Mono",Menlo,monospace;font-size:12.5px;font-weight:800;white-space:nowrap;text-align:right;}',
      /* mini bars */
      '.md-meter{position:relative;height:5px;border-radius:3px;background:var(--mln);margin-top:6px;overflow:hidden;}',
      '.md-meter i{position:absolute;left:0;top:0;bottom:0;border-radius:3px;}',
      '.md-div{position:relative;height:6px;margin-top:6px;}',
      '.md-div-mid{position:absolute;left:50%;top:-1px;bottom:-1px;width:1px;background:var(--mln2);}',
      '.md-div i{position:absolute;top:0;bottom:0;border-radius:3px;}',
      '.md-pips{display:inline-flex;gap:2px;margin-top:6px;}',
      '.md-pip{width:5px;height:5px;border-radius:1.5px;background:var(--gold);}',
      '.md-pip.off{background:var(--mln2);}',
      '.md-fl{display:inline-block;margin-right:5px;font-size:13px;line-height:1;vertical-align:-1px;}',
      '.md-empty{color:var(--mi3);font-size:12px;padding:12px 2px 10px;line-height:1.5;}',
      '.md-foot{text-align:center;color:var(--mi3);font-size:11px;margin-top:16px;padding-bottom:2px;}'
    ].join('');
    var st = document.createElement('style');
    st.id = 'mdash-css'; st.textContent = css;
    (document.head || document.documentElement).appendChild(st);
  }

  function _mdFetch() {
    var b = '?t=' + Date.now();
    var jf = function (u) { return fetch(u + b, { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); };
    return Promise.all([jf('liga-data.json'), jf('mls-data.json'), jf('liga_streaks.json'),
      jf('mls_streaks.json'), jf('betfair_prices.json'), jf('poly_money_broad_close.json')]);
  }
  function _mdLoad(force) {
    if (_md.loading) return;
    _mdStyle();
    if (_md.data && !force) { _mdRender(); return; }
    _md.loading = true;
    var p = document.getElementById('mainDashPanel');
    if (p && !_md.data) { p.classList.add('mdash'); p.innerHTML = _head() + '<div class="md-empty" style="text-align:center;padding:52px 0;">⏳ Übersicht wird geladen …</div>'; }
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

  function betPicks() {
    var rows = [];
    allFixtures().forEach(function (f) {
      (f.picks || []).forEach(function (p) {
        if (p.verdict === 'BET') rows.push({ f: f, p: p, conv: +p.convictionScore || 0 });
      });
    });
    rows.sort(function (a, b) { return (b.conv - a.conv) || ((+b.p.edgePP || 0) - (+a.p.edgePP || 0)); });
    return rows;
  }
  function bestCards() { return betPicks().slice(0, 5); }
  function allStreaks() {
    var s = [];
    [_md.data.ligaStreaks, _md.data.mlsStreaks].forEach(function (d) { if (d && Array.isArray(d.streaks)) s = s.concat(d.streaks); });
    s = s.filter(function (x) { return (+x.length || 0) >= 4; });
    s.sort(function (a, b) { var ra = (a.continuation && a.continuation.ratePct) || 0, rb = (b.continuation && b.continuation.ratePct) || 0; return ((+b.length || 0) - (+a.length || 0)) || (rb - ra); });
    return s;
  }
  function bestStreaks() { return allStreaks().slice(0, 5); }
  function allBetfair() {
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
        if (!best || sc > best.sc) best = { name: name, lead: lead, share: share, vol: +lead.vol || 0, tot: tot, sc: sc };
      }
      if (best && best.vol >= 3000) rows.push({ m: m, b: best });
    });
    rows.sort(function (a, b) { return b.b.sc - a.b.sc; });
    return rows;
  }
  function bestBetfair() { return allBetfair().slice(0, 5); }
  function allWhales() {
    var w = _md.data.whales || {}, all = [];
    for (var k in w) {
      var mk = w[k];
      if (mk && Array.isArray(mk.whales)) mk.whales.forEach(function (wh) {
        all.push({ usd: +wh.usd || 0, side: wh.side, league: mk.league, hrs: mk.hoursToKickoff });
      });
    }
    all.sort(function (a, b) { return b.usd - a.usd; });
    return all;
  }
  function bestWhales() { return allWhales().slice(0, 5); }
  function allSharp() {
    var rows = [];
    allFixtures().forEach(function (f) {
      (f.picks || []).forEach(function (p) {
        if (p.source === 'steam' && p.steamMovePP != null) rows.push({ f: f, p: p, mv: Math.abs(+p.steamMovePP || 0) });
      });
    });
    rows.sort(function (a, b) { return b.mv - a.mv; });
    return rows;
  }
  function bestSharp() { return allSharp().slice(0, 5); }

  // ── Render-Bausteine ──────────────────────────────────────────────────────
  function _clock() {
    try { var d = new Date(); return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2); } catch (e) { return '—'; }
  }
  function _head() {
    return '<div class="md-top md-rise">' +
      '<div><h1 class="md-h1">Übersicht</h1>' +
      '<p class="md-sub">Die stärksten Signale aller Engines — kuratiert, auf einen Blick.</p></div>' +
      '<div class="md-asof"><span class="md-dot"></span>Stand <b>' + _clock() + '</b></div></div>';
  }

  function kpi(val, label, hint, color) {
    return '<div class="md-kpi" style="--kc:' + color + ';">' +
      '<div class="md-kpi-v">' + val + '</div>' +
      '<div class="md-kpi-l">' + label + '</div>' +
      (hint ? '<div class="md-kpi-h">' + hint + '</div>' : '') + '</div>';
  }
  function _kpis() {
    var bets = betPicks(), streaks = allStreaks(), bf = allBetfair(), wh = allWhales();
    var bfSum = bf.reduce(function (a, x) { return a + x.b.vol; }, 0);
    var topConv = bets.length ? (bets[0].conv || 0) : 0;
    var topStreak = streaks.length ? (streaks[0].length || 0) : 0;
    var topWhale = wh.length ? wh[0].usd : 0;
    return '<div class="md-kpis md-rise">' +
      kpi(bets.length, 'BET-Cards', bets.length ? 'Top ' + topConv + '/10 Conviction' : 'keine offen', A.good) +
      kpi(streaks.length, 'Aktive Serien', streaks.length ? 'längste ' + topStreak + '×' : 'keine ≥4', A.gold) +
      kpi(bf.length ? eur(bfSum) : '—', 'Betfair heiß', bf.length ? bf.length + ' Märkte mit Zug' : 'ruhig', A.bf) +
      kpi(wh.length, 'Whale-Bets', wh.length ? 'größte ' + usd(topWhale) : 'keine', A.poly) +
      '</div>';
  }

  var _SIDE = { home: 'Heim', away: 'Ausw.' };
  var _SRC = { pinnacle: 'Pinnacle', betfair: 'Betfair', poly: 'Poly', soft: 'Soft' };
  var _SRC_ORDER = ['pinnacle', 'betfair', 'poly', 'soft'];
  var _SRC_COL = { pinnacle: A.pinn, betfair: A.bf, poly: A.poly, soft: A.soft };

  function consensusRows() {
    var out = [];
    allFixtures().forEach(function (f) {
      (f.picks || []).forEach(function (p) { if (p.consensus && p.consensus.kind) out.push({ f: f, p: p, c: p.consensus }); });
    });
    return out;
  }
  // 4-Quellen-Zustimmungsbalken: Punkt je Quelle an ihrer Wahrscheinlichkeit, Konsens-Band, Ausreißer hervorgehoben
  function agreeBar(c) {
    var src = c.sources || {}, vals = [];
    _SRC_ORDER.forEach(function (k) { var v = src[k]; if (typeof v === 'number') vals.push(v); });
    if (!vals.length) return '';
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    // Skala: um das Cluster herum, mind. 24pp Fenster, damit enge Konsense nicht auf 0 kollabieren
    var mid = (lo + hi) / 2, half = Math.max(0.12, (hi - lo) / 2 + 0.06);
    var min = clamp(mid - half, 0, 1), max = clamp(mid + half, 0, 1), span = (max - min) || 1;
    var pos = function (v) { return clamp((v - min) / span, 0, 1) * 100; };
    var band = '<div class="md-agree-band' + (c.kind === 'divergenz' ? ' div' : '') + '" style="left:' + pos(lo) + '%;width:' + (pos(hi) - pos(lo)) + '%;"></div>';
    var dots = '';
    _SRC_ORDER.forEach(function (k) {
      var v = src[k]; if (typeof v !== 'number') return;
      var out = (c.kind === 'divergenz' && c.outlier === k);
      dots += '<div class="md-agree-dot' + (out ? ' out' : '') + '" style="left:' + pos(v) + '%;background:' + _SRC_COL[k] + ';" title="' + _SRC[k] + ' ' + Math.round(v * 100) + '%"></div>';
    });
    return '<div class="md-agree"><div class="md-agree-track"></div>' + band + dots + '</div>';
  }
  function _legend() {
    return '<div class="md-legend">' + _SRC_ORDER.map(function (k) {
      return '<span class="md-lg"><i style="background:' + _SRC_COL[k] + ';"></i>' + _SRC[k] + '</span>';
    }).join('') + '</div>';
  }
  function _mdHero() {
    var teams = function (f) { return fl(fxFlag(f)) + esc(team(f.home)) + ' <span style="color:var(--mi3);font-weight:400">v</span> ' + esc(team(f.away)); };
    var top = '<div class="md-hero-top"><span class="md-hero-ic">⚖️</span>' +
      '<div><div class="md-hero-t">Triple-Konsens</div>' +
      '<div class="md-hero-s">wo Pinnacle · Betfair · Poly · Soft einig sind — und wo einer ausschert</div></div>' +
      _legend() + '</div>';
    var rows = consensusRows();
    if (!rows.length) {
      return '<section class="md-hero md-rise">' + top +
        '<div class="md-empty" style="max-width:780px;margin-top:12px;">Füllt sich beim nächsten Pick-Lauf: dann stehen hier die Spiele, wo sich die Quellen einig sind (hohe Konfidenz, größer setzen) und wo eine ausschert (Value-Kandidat). Poly deckt aktuell MLS/WM ab — bei Top-5 zeigt der Balken „3/4".</div></section>';
    }
    var kon = rows.filter(function (x) { return x.c.kind === 'konsens'; }).sort(function (a, b) { return a.c.spreadPP - b.c.spreadPP; }).slice(0, 5);
    var div = rows.filter(function (x) { return x.c.kind === 'divergenz'; }).sort(function (a, b) { return b.c.outlierGapPP - a.c.outlierGapPP; }).slice(0, 5);
    var konRow = function (x) {
      var c = x.c;
      return '<div class="md-arow"><div class="md-arow-t">' + teams(x.f) + ' · <b>' + _SIDE[c.side] + '</b></div>' +
        agreeBar(c) +
        '<div class="md-arow-m"><b style="color:' + A.good + '">' + c.n + '/4 einig</b> · Ø ' + c.medianPP + '% · Spanne ' + c.spreadPP + 'pp</div></div>';
    };
    var divRow = function (x) {
      var c = x.c, o = c.outlier, ov = (c.sources && c.sources[o] != null ? Math.round(c.sources[o] * 100) : '?');
      return '<div class="md-arow"><div class="md-arow-t">' + teams(x.f) + ' · <b>' + _SIDE[c.side] + '</b></div>' +
        agreeBar(c) +
        '<div class="md-arow-m"><b style="color:' + A.gold + '">' + (_SRC[o] || o) + ' schert aus</b>: ' + ov + '% vs Ø ' + c.medianPP + '% (' + c.outlierGapPP + 'pp)</div></div>';
    };
    var col = function (title, tint, list, rowFn, emptyTxt) {
      return '<div class="md-col"><div class="md-col-h" style="color:' + tint + ';">' + title + '</div>' +
        (list.length ? list.map(rowFn).join('') : '<div class="md-empty">' + emptyTxt + '</div>') + '</div>';
    };
    return '<section class="md-hero md-rise">' + top +
      '<div class="md-cols">' +
        col('✅ Einig — hohe Konfidenz', A.good, kon, konRow, 'gerade keine enge Übereinstimmung') +
        col('⚡ Ausreißer — Value-Kandidat', A.gold, div, divRow, 'gerade kein klarer Ausreißer') +
      '</div></section>';
  }

  function tile(icon, title, accent, tintBg, tintBr, moreView, moreLbl, bodyHtml, delay) {
    var more = moreView ? '<button class="md-more" style="--ta:' + accent + ';" onclick="showView(\'' + moreView + '\')">' + (moreLbl || 'alle') + ' →</button>' : '';
    return '<section class="md-tile md-rise" style="animation-delay:' + (delay || 0) + 'ms;">' +
      '<div class="md-tile-h"><span class="md-tile-ic" style="--tb:' + tintBg + ';--tbr:' + tintBr + ';">' + icon + '</span>' +
        '<span class="md-tile-t">' + title + '</span>' + more + '</div>' + bodyHtml + '</section>';
  }
  function empty(txt) { return '<div class="md-empty">' + (txt || 'Aktuell nichts.') + '</div>'; }
  function rowEl(main, val, valColor, sub, extra) {
    return '<div class="md-r"><div class="md-r-main">' +
      '<div class="md-r-t">' + main + '</div>' +
      (sub ? '<div class="md-r-s">' + sub + '</div>' : '') +
      (extra || '') +
      '</div>' +
      (val ? '<div class="md-r-v" style="color:' + (valColor || 'var(--mi)') + ';">' + val + '</div>' : '') +
    '</div>';
  }
  function meter(pct, color) {
    return '<div class="md-meter"><i style="width:' + clamp(pct, 0, 100) + '%;background:' + color + ';"></i></div>';
  }
  function pips(n, max) {
    max = max || 10; var out = '<div class="md-pips">';
    for (var i = 0; i < max; i++) out += '<span class="md-pip' + (i < n ? '' : ' off') + '"></span>';
    return out + '</div>';
  }

  function _mdRender() {
    var p = document.getElementById('mainDashPanel');
    if (!p) return;
    _mdStyle();
    p.classList.add('mdash');
    if (!_md.data) { _mdLoad(); return; }
    var teamsOf = function (f) { return fl(fxFlag(f)) + esc(team(f.home)) + ' <span style="color:var(--mi3);font-weight:400">v</span> ' + esc(team(f.away)); };

    // Cards — Conviction-Meter
    var c = bestCards();
    var cardsBody = c.length ? c.map(function (x) {
      var f = x.f, p2 = x.p;
      var val = x.conv ? x.conv + '/10' : (p2.odds != null ? '@' + (+p2.odds).toFixed(2) : '');
      var sub = esc(short(p2.market)) + (fxLeague(f) ? ' · ' + esc(String(fxLeague(f)).slice(0, 20)) : '') + (p2.edgePP != null ? ' · +' + Math.round(+p2.edgePP) + 'pp' : '');
      return rowEl(teamsOf(f), val, A.good, sub, x.conv ? meter(x.conv * 10, A.good) : '');
    }).join('') : empty('Keine BET-Cards gerade.');

    // Streaks — Pips (Länge)
    var st = bestStreaks();
    var streaksBody = st.length ? st.map(function (s) {
      var sub = esc(String(s.leagueName || '')) + (s.continuation && s.continuation.state ? ' · ' + esc(s.continuation.state) : '') + (s.continuation && s.continuation.ratePct != null ? ' · ' + s.continuation.ratePct + '%' : '');
      var len = +s.length || 0;
      return rowEl(fl(_flagFrom(s.country, s.league, s.leagueName)) + esc(team(s.team)) + ' <span style="color:var(--mi3);font-weight:400">·</span> ' + esc(s.market || s.type || ''),
        len + '×', A.gold, sub, pips(Math.min(len, 10), 10));
    }).join('') : empty('Keine langen Serien.');

    // Betfair — Anteilsbalken
    var bf = bestBetfair();
    var bfBody = bf.length ? bf.map(function (x) {
      var m = x.m, b = x.b, pct = Math.round(b.share * 100);
      return rowEl(teamsOf(m), eur(b.vol), A.bf,
        esc(short(b.name)) + ' → ' + esc(b.lead.name) + ' · ' + pct + '%', meter(pct, A.bf));
    }).join('') : empty('Kein großes Betfair-Geld.');

    // Whales — USD-Balken (relativ zum größten)
    var wh = bestWhales();
    var whMax = wh.length ? wh[0].usd : 1;
    var whBody = wh.length ? wh.map(function (w) {
      var hrs = (w.hrs != null && w.hrs >= 0) ? (w.hrs < 1 ? '<1h' : Math.round(w.hrs) + 'h') : '';
      return rowEl(fl(_flagFrom(w.country, w.league, w.league)) + esc(w.side || '?'), usd(w.usd), A.poly,
        esc(String(w.league || '')) + (hrs ? ' · in ' + hrs : ''), meter(whMax ? (w.usd / whMax) * 100 : 0, A.poly));
    }).join('') : empty('Keine Whale-Bets.');

    // Sharp — Divergenzbalken (Steam-Richtung)
    var sh = bestSharp();
    var shMax = sh.length ? Math.max.apply(null, sh.map(function (x) { return Math.abs(+x.p.steamMovePP || 0); })) : 1;
    var shBody = sh.length ? sh.map(function (x) {
      var f = x.f, p2 = x.p, mv = +p2.steamMovePP || 0;
      var col = mv > 0 ? A.good : A.red;
      var w = shMax ? (Math.abs(mv) / shMax) * 50 : 0;
      var divb = '<div class="md-div"><div class="md-div-mid"></div><i style="' + (mv >= 0 ? 'left:50%;' : 'right:50%;') + 'width:' + w + '%;background:' + col + ';"></i></div>';
      return rowEl(teamsOf(f), (mv > 0 ? '+' : '') + mv.toFixed(1) + 'pp', col,
        esc(short(p2.market)) + (p2.odds != null ? ' · @' + (+p2.odds).toFixed(2) : ''), divb);
    }).join('') : empty('Keine Steam-Moves.');

    var grid = '<div class="md-grid">' +
      tile('🎯', 'Beste Cards', A.good, 'rgba(46,160,67,.14)', 'rgba(46,160,67,.32)', 'national-cards', 'alle Cards', cardsBody, 40) +
      tile('🔥', 'Beste Streaks', A.gold, 'rgba(201,133,0,.14)', 'rgba(201,133,0,.32)', 'national-streaks', 'alle Serien', streaksBody, 80) +
      tile('💷', 'Betfair-Kohle', A.bf, 'rgba(217,89,38,.14)', 'rgba(217,89,38,.32)', 'betfair', 'Radar', bfBody, 120) +
      tile('🐋', 'Poly Whale-Bets', A.poly, 'rgba(25,158,112,.14)', 'rgba(25,158,112,.32)', 'polywallets', 'Wallets', whBody, 160) +
      tile('📡', 'Sharp-Radar', A.blue, 'rgba(57,135,229,.14)', 'rgba(57,135,229,.32)', 'sharp', 'Radar', shBody, 200) +
      '</div>';

    p.innerHTML = _head() + _kpis() + _mdHero() + grid +
      '<div class="md-foot">Kuratierter Überblick · tippe „alle →" für den vollen Bereich</div>';
  }
  window._renderMainDash = _mdRender;
  window._mdState = _md;   // Test-Hook
})();
