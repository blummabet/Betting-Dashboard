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
  function _ageMin(obj) {
    var g = obj && obj._meta && obj._meta.generatedAt;
    if (!g) return null;
    var t = Date.parse(g); return isNaN(t) ? null : Math.max(0, (Date.now() - t) / 60000);
  }
  function _ageStr(obj) {
    var m = _ageMin(obj); if (m == null) return '';
    var col = m > 35 ? '#f2a6a6' : m > 15 ? 'var(--gold)' : 'var(--mi3)';
    var txt = m >= 90 ? Math.round(m / 60) + 'h' : Math.round(m) + ' Min';
    return '<div style="text-align:right;font-size:10px;color:' + col + ';padding:6px 0 2px">Stand vor ' + txt + '</div>';
  }

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
      '.md-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:14px;}',
      '.md-cell{display:contents;}',
      '@media(max-width:760px){.md-grid{grid-template-columns:1fr;}}',
      '.md-ring{position:relative;flex:0 0 auto;width:44px;height:44px;}',
      '.md-ring .n{position:absolute;inset:0;display:grid;place-items:center;font-weight:900;font-size:18px;}',
      '.md-donut{position:relative;flex:0 0 auto;width:42px;height:42px;}',
      '.md-donut .n{position:absolute;inset:0;display:grid;place-items:center;font-weight:800;font-size:13px;}',
      '.md-live{display:inline-block;font-size:8.5px;font-weight:800;color:var(--red);border:1px solid rgba(229,83,75,.55);border-radius:6px;padding:0 5px;margin-left:6px;vertical-align:middle;letter-spacing:.3px;line-height:14px;}',
      '.md-polylink{color:inherit;text-decoration:none;border-bottom:1px dotted var(--mln2);transition:border-color .15s;}',
      '.md-polylink:hover{border-bottom-color:var(--poly);}',
      '.md-ext{color:#a78bfa;font-size:.82em;}',
      '.md-wdot{flex:0 0 auto;width:22px;height:22px;border-radius:7px;display:grid;place-items:center;font-size:12px;background:rgba(229,83,75,.13);color:var(--red);}',
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
      '.md-foot{text-align:center;color:var(--mi3);font-size:11px;margin-top:16px;padding-bottom:2px;}',
      '.md-preview-h{margin:22px 0 2px;font-weight:800;font-size:13px;color:var(--mi);border-top:1px dashed var(--mln2);padding-top:16px;}',
      '.md-pulse{display:flex;flex-direction:column;align-items:stretch;gap:9px;background:var(--m1);border:1px solid var(--mln);border-radius:14px;padding:12px 15px;margin-top:14px;}',
      '.md-pulse-row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;}',
      '.md-pulse-tag{display:flex;align-items:center;gap:6px;font-size:11px;font-weight:800;color:var(--mi2);min-width:120px;}',
      '.md-pulse-strip{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;border-top:1px solid var(--mln);padding-top:8px;margin-top:1px;font-size:11px;color:var(--mi2);}',
      '.md-pulse-live{color:var(--mi3);font-weight:700;white-space:nowrap;}',
      '.md-pulse-h{display:flex;align-items:center;gap:7px;font-size:10.5px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--mi3);}',
      '.md-pulse-ms{display:flex;align-items:center;gap:18px;flex-wrap:wrap;flex:1;min-width:0;}',
      '.md-pulse-m{display:flex;flex-direction:column;gap:2px;}',
      '.md-pulse-v{font-family:"JetBrains Mono","SF Mono",Menlo,monospace;font-size:19px;font-weight:800;line-height:1;letter-spacing:-.02em;}',
      '.md-pulse-l{font-size:10px;color:var(--mi3);font-weight:600;white-space:nowrap;}',
      '.md-spk{position:relative;display:flex;align-items:stretch;gap:1px;height:34px;margin-left:auto;}',
      '.md-spk-mid{position:absolute;left:0;right:0;top:50%;height:1px;background:var(--mln2);}',
      '.md-spk-col{position:relative;width:3px;}',
      '.md-spk-b{position:absolute;left:0;width:100%;border-radius:1.5px;min-height:1px;}',
      '.md-jetzt{background:radial-gradient(120% 140% at 100% 0%,rgba(217,89,38,.10),transparent 55%),var(--m1);border:1px solid rgba(217,89,38,.3);border-radius:14px;padding:13px 15px 8px;margin-top:12px;}',
      '.md-jz-h{display:flex;align-items:center;gap:8px;margin-bottom:2px;}',
      '.md-jz-t{font-weight:800;font-size:13.5px;color:var(--mi);}',
      '.md-jz-s{font-size:11px;color:var(--mi2);}',
      '.md-jz-row{display:flex;align-items:center;gap:10px;padding:9px 0;border-top:1px solid var(--mln);}',
      '.md-jz-row:first-of-type{border-top:0;}',
      '.md-jz-main{min-width:0;flex:1;}',
      '.md-jz-tm{font-size:13px;font-weight:600;color:var(--mi);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      '.md-jz-sub{font-size:11px;color:var(--mi2);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      '.md-jz-ko{font-family:"JetBrains Mono",monospace;font-size:12px;font-weight:800;color:var(--bf);white-space:nowrap;}',
      '.md-jz-mv{font-family:"JetBrains Mono",monospace;font-size:12px;font-weight:800;white-space:nowrap;text-align:right;min-width:52px;}',
      '.md-badge{display:inline-block;font-size:9.5px;font-weight:800;padding:1px 6px;border-radius:5px;margin-left:6px;vertical-align:1px;}'
    ].join('');
    var st = document.createElement('style');
    st.id = 'mdash-css'; st.textContent = css;
    (document.head || document.documentElement).appendChild(st);
  }

  function _mdFetch() {
    var t = Date.now();
    var base = 'https://raw.githubusercontent.com/blummabet/Betting-Dashboard/main';
    // raw.github ZUERST → commit-frisch (spiegelt den Fetcher-Commit sofort, ohne auf den trägen
    // Pages-Deploy zu warten), sonst lokal (Pages/Offline-Cache). Gleiche Logik wie im Betfair-Radar.
    var jf = function (u) {
      return fetch(base + '/' + u + '?t=' + t, { cache: 'no-store' })
        .then(function (r) { if (r.ok) return r.json(); throw 0; })
        .catch(function () { return fetch(u + '?t=' + t, { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); });
    };
    return Promise.all([jf('liga-data.json'), jf('mls-data.json'), jf('liga_streaks.json'),
      jf('mls_streaks.json'), jf('betfair_prices.json'), jf('poly_money_broad_close.json'), jf('dashboard_pulse.json'),
      jf('betfair_overview.json'), jf('betfair_direction.json')]);
  }
  function _mdLoad(force) {
    if (_md.loading) return;
    _mdStyle();
    if (_md.data && !force) { _mdRender(); return; }
    _md.loading = true;
    var p = document.getElementById('mainDashPanel');
    if (p && !_md.data) { p.classList.add('mdash'); p.innerHTML = _head() + '<div class="md-empty" style="text-align:center;padding:52px 0;">⏳ Übersicht wird geladen …</div>'; }
    _mdFetch().then(function (a) {
      _md.data = { liga: a[0], mls: a[1], ligaStreaks: a[2], mlsStreaks: a[3], betfair: a[4], whales: a[5], pulse: a[6], bfOverview: a[7], bfDir: a[8] };
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
    var BF_LEAD_MAX_ODD = 15;   // 09.08.2026 (Lucas): Longshot-Deckel — @>15 = live abgestuerzter Aussenseiter (Hannover @100, St Pauli @80), Geld darauf ist Lay/reaktiv, kein Kohle-Signal. Gegenstueck zum <1.30-Filter, wie der HT-Deckel.
    var ms = (_md.data.betfair && _md.data.betfair.matches) || [], rows = [];
    ms.forEach(function (m) {
      if (_mdBfStale(m)) return;   // 07.08.2026: fertige/vorbei Spiele raus (hoechstes Volumen -> klebten oben in der Kohle-Kachel)
      var best = null, mk = m.markets || {};
      for (var name in mk) {
        var rs = mk[name].runners || [];
        var tot = rs.reduce(function (a, r) { return a + (+r.vol || 0); }, 0);
        if (tot <= 0) continue;
        var lead = rs.reduce(function (a, r) { return (!a || (+r.vol || 0) > (+a.vol || 0)) ? r : a; }, null);
        if (!lead) continue;
        if (typeof lead.odd === 'number' && (lead.odd < 1.30 || lead.odd > BF_LEAD_MAX_ODD)) continue;   // 08.08.2026 (Lucas): Quasi-Lock (@<1.30) ODER Longshot (@>15, live abgestuerzt = Lay/reaktiv) = kein Signal — wie HT/Frisches Geld/Alerts
        var share = (+lead.vol || 0) / tot, sc = (+lead.vol || 0) * share;
        if (!best || sc > best.sc) best = { name: name, lead: lead, share: share, vol: +lead.vol || 0, tot: tot, sc: sc };
      }
      if (best && best.vol >= 3000) rows.push({ m: m, b: best });
    });
    rows.sort(function (a, b) { return b.b.sc - a.b.sc; });
    return rows;
  }
  function bestBetfair() { return allBetfair().slice(0, 5); }
  // ── Übersicht-Betfair-Kacheln (02.08.2026, Lucas): Steam + Frisches Geld aus dem leichten
  // Sidecar (betfair_overview.json), Fehlbepreisung client-seitig über die echte Radar-Engine
  // (window._bfCoherence) — kein Poisson-Nachbau, kein Drift. Gemeinsamer Team-Label-Helfer:
  function _bfTeams(x) {
    return fl(_flagFrom(x.country, x.league, x.league)) + esc(String(x.home)) +
      ' <span style="color:var(--mi3);font-weight:400">v</span> ' + esc(String(x.away));
  }
  // 08.08.2026 (Lucas): Back/Lay-Richtung auch in den Übersicht-Kacheln — aus betfair_direction.json.
  function _mdDirOf(matchId, market, runner) {
    try { return ((((_md.data.bfDir || {})[String(matchId)] || {})[market] || {})[runner] || {}).dir || null; } catch (e) { return null; }
  }
  function _mdDirBadge(dir) {
    if (dir === 'in') return ' <span title="Quote kürzer → Geld kommt als Back" style="font-size:9px;font-weight:800;color:#3fb950;border:1px solid rgba(63,185,80,.45);border-radius:4px;padding:0 3px">Back ✓</span>';
    if (dir === 'out') return ' <span title="Quote driftet raus → kein echter Back-Rückhalt" style="font-size:9px;font-weight:800;color:#e3b341;border:1px solid rgba(227,179,65,.45);border-radius:4px;padding:0 3px">driftet</span>';
    return '';
  }
  // ⚡ Sharpe Bewegungen: Vor-Anpfiff-Quotenbewegung (pp). +pp = Quote fällt = Geld drauf, −pp = driftet.
  function _mdBfSteamBody() {
    var items = ((_md.data.bfOverview || {}).steam) || [];
    if (!items.length) return empty('Keine Vor-Anpfiff-Bewegung — sammelt (2 Snapshots nötig).');
    var mx = items.reduce(function (a, x) { return Math.max(a, Math.abs(+x.pp || 0)); }, 1);
    return items.map(function (x) {
      var mv = +x.pp || 0, backed = mv > 0, col = backed ? A.good : A.red, w = mx ? Math.abs(mv) / mx * 50 : 0;
      var divb = '<div class="md-div"><div class="md-div-mid"></div><i style="' + (backed ? 'left:50%;' : 'right:50%;') + 'width:' + w + '%;background:' + col + ';"></i></div>';
      return rowEl(_bfTeams(x), (mv > 0 ? '+' : '') + mv.toFixed(1) + 'pp', col,
        '→ ' + esc(x.sideName || '') + ' · ' + (backed ? 'Quote fällt' : 'Quote steigt') + (x.odd != null ? ' · @' + (+x.odd).toFixed(2) : ''), divb);
    }).join('') + _ageStr(_md.data.betfair);
  }
  // ⚖️ Größte Fehlbepreisung: harte Modell-Abweichungen je Spiel (nur vor Anpfiff), Radar-Engine.
  var _MISP_MIN_VOL = 10000;   // Kohärenz nur für liquide Spiele: spart Rechenzeit (≈6ms/Spiel) UND
                               // hebt das Signal — bei €500-Spielen ist „Fehlbepreisung" ohnehin Rauschen.
  function _bfTopVol(m) {
    var best = 0, mk = m.markets || {};
    for (var k in mk) { var rs = mk[k].runners || [], t = 0, i; for (i = 0; i < rs.length; i++) t += (+rs[i].vol || 0); if (t > best) best = t; }
    return best;
  }
  function _mdBfMispriced() {
    if (typeof window._bfCoherence !== 'function') return null;
    var ms = (_md.data.betfair && _md.data.betfair.matches) || [];
    if (_md._bfMispSrc === ms && _md._bfMisp) return _md._bfMisp;   // Memo: einmal pro Daten-Load, nicht je Render
    var out = [];
    var liveFn = (typeof window._bfIsLive === 'function') ? window._bfIsLive : function () { return false; };
    ms.forEach(function (m) {
      if (_mdBfStale(m) || liveFn(m, _mdBfGenAge()) || _bfTopVol(m) < _MISP_MIN_VOL) return;   // 08.08.2026 (Lucas): _mdBfGenAge()-Override wie beim LIVE-Badge — sonst haelt _bfIsLive auf der Uebersicht ALLES fuer nicht-live (genAgeMin liest leeren _bfState) -> Live-Spiele leakten in die Fehlbepreisung
      var co; try { co = window._bfCoherence(m); } catch (e) { return; }
      var checks = (co && co.checks) || [];
      var hard = checks.filter(function (c) { return c.hard && Math.abs(c.dev) >= 0.8 && (c.w == null || c.w >= 0.15); });
      if (!hard.length) return;
      var top = hard.reduce(function (a, c) { return (!a || Math.abs(c.dev) > Math.abs(a.dev)) ? c : a; }, null);
      var score = hard.reduce(function (sc, c) { return sc + Math.abs(c.dev) * (c.w == null ? 1 : c.w); }, 0);
      out.push({ m: m, nHard: hard.length, top: top, score: score });
    });
    out.sort(function (a, b) { return b.score - a.score; });
    _md._bfMispSrc = ms; _md._bfMisp = out.slice(0, 5);
    return _md._bfMisp;
  }
  function _mdBfMispricedBody() {
    var rows = _mdBfMispriced();
    if (rows == null) return empty('Radar-Engine lädt noch …');
    if (!rows.length) return empty('Keine harte Fehlbepreisung — Markt & Modell im Lot.');
    var mx = rows[0].score || 1;
    return rows.map(function (r) {
      var t = r.top || {};
      return _mdWarnRow(_bfTeams(r.m) + _mdBfLive(r.m),
        esc(String(t.k || 'Abweichung')) + (t.mkt ? ' · ' + esc(String(t.mkt).slice(0, 26)) : ''), r.nHard);
    }).join('') + _ageStr(_md.data.betfair);
  }
  // 💸 Frisches Geld: größter Zufluss (€) je Spiel seit dem letzten Snapshot.
  function _mdBfFlowBody() {
    // 04.08.2026 (Lucas: "@1.01 ist sinnfrei"): Geld auf Quasi-Lock-Quoten (< 1.30, meist live/
    // entschieden) ist kein Zufluss-Signal - raus, wie im Radar (MIN_ODD_SHOW). Fehlende Quote -> drin.
    var FLOW_MIN_ODD = 1.30, FLOW_MAX_ODD = 15;   // 09.08.2026 (Lucas): auch oben deckeln — Zufluss auf @>15-Longshot (live abgestuerzt) ist reaktiv/Lay, kein Signal
    var items = (((_md.data.bfOverview || {}).flow) || []).filter(function (x) {
      return !(x.odd != null && (+x.odd < FLOW_MIN_ODD || +x.odd > FLOW_MAX_ODD));
    });
    if (!items.length) return empty('Kein frischer Zufluss ≥ €2K — sammelt (2 Snapshots nötig).');
    var mx = items.reduce(function (a, x) { return Math.max(a, +x.deltaEur || 0); }, 1);
    return items.map(function (x) {
      return rowEl(_bfTeams(x) + _mdBfLiveById(x.matchId), '+' + eur(x.deltaEur), A.good,
        '→ ' + esc(x.sideName || '') + _mdDirBadge(x.dir) + ' · jetzt ' + eur(x.nowEur) + (x.odd != null ? ' @' + (+x.odd).toFixed(2) : ''),
        meter(mx ? (+x.deltaEur / mx * 100) : 0, A.good));
    }).join('') + _ageStr(_md.data.betfair);
  }
  // 03.08.2026 (Lucas: „Spiele waren in der Nacht“): echten Anpfiff aus dem Freeze rekonstruieren
  // (capturedAt + hoursToKickoff) statt des eingefrorenen htk. So zeigt die Kachel korrekt live/Zeit
  // und schon durchgelaufene Spiele (>4h nach Anpfiff) sowie aufgelöste Märkte fliegen raus — wie im
  // Wallet-Reiter (_pwKoStale). Ohne diese Gate standen $300K-MLB-Nachtspiele als „in <1h“ oben.
  function _mdRealHtk(mk) {
    if (!mk || mk.hoursToKickoff == null) return null;
    var cap = mk.capturedAt ? Date.parse(mk.capturedAt) : NaN;
    return isNaN(cap) ? mk.hoursToKickoff : (mk.hoursToKickoff - (Date.now() - cap) / 3.6e6);
  }
  // 03.08.2026 (Lucas: „Einsätze sehr low?“): der Feed nennt schon ~$1.5K eine „Whale"-Position (Median).
  // Für die Übersicht-Kachel zählt erst ab MD_WHALE_MIN_USD als Whale — sonst zeigt ein ruhiger Slate $821.
  var MD_WHALE_MIN_USD = 10000;
  function allWhales() {
    var w = _md.data.whales || {}, all = [];
    for (var k in w) {
      var mk = w[k];
      if (!mk || mk.resolved != null || !Array.isArray(mk.whales)) continue;   // aufgelöst → raus
      var rh = _mdRealHtk(mk);
      if (rh != null && rh < -4) continue;                                     // >4h nach Anpfiff = durch
      mk.whales.forEach(function (wh) {
        if ((+wh.usd || 0) < MD_WHALE_MIN_USD) return;   // kein Kleinvieh als „Whale"
        all.push({ usd: +wh.usd || 0, side: wh.side, league: mk.league, hrs: rh, key: k, wallet: wh.wallet });
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
        '<div class="md-empty" style="max-width:780px;margin-top:12px;">Füllt sich beim nächsten Pick-Lauf: dann stehen hier die Spiele, wo sich die Quellen einig sind (hohe Konfidenz, größer setzen) und wo eine ausschert (Value-Kandidat). Poly deckt jetzt alle Top-5-Ligen ab (Premier League, La Liga, Serie A, Ligue 1, Bundesliga) — Spiele ohne Poly-Markt zeigen „3/4".</div></section>';
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
  // ── Form-Sprachen für die Übersicht (02.08.2026, Lucas): Anteil→Donut, Score→Ring, Alert→Warn,
  //    Live→Badge. Donut/Ring als Inline-SVG-Bogen; Zeilen nutzen die bestehende .md-r-Flexzeile. ──
  function _mdArc(pct, color, size, sw) {
    var r = (size - sw) / 2, cx = size / 2, circ = 2 * Math.PI * r;
    var on = Math.max(0, Math.min(1, pct)) * circ;
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '" style="transform:rotate(-90deg)">'
      + '<circle cx="' + cx + '" cy="' + cx + '" r="' + r + '" fill="none" stroke="var(--mln)" stroke-width="' + sw + '"/>'
      + '<circle cx="' + cx + '" cy="' + cx + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="' + sw + '" stroke-linecap="round" stroke-dasharray="' + on + ' ' + (circ - on) + '"/></svg>';
  }
  function _mdRing(conv, color) { return '<div class="md-ring">' + _mdArc((+conv || 0) / 10, color, 44, 5) + '<div class="n" style="color:' + color + '">' + (+conv || 0) + '</div></div>'; }
  function _mdDonut(pct, color) { return '<div class="md-donut">' + _mdArc((+pct || 0) / 100, color, 42, 6) + '<div class="n">' + Math.round(+pct || 0) + '%</div></div>'; }
  function _mdConvCol(conv) { return conv >= 9 ? A.good : conv >= 8 ? '#2dd4bf' : A.gold; }
  var _MD_LIVE = '<span class="md-live">\u25cf LIVE</span>';
  // Übersicht → Polymarket-Markt verlinken (wie im Wallet-Reiter): wrappt das Match-Label,
  // öffnet die jeweilige Ereignis-Seite im neuen Tab. Ohne Slug bleibt der Text unverlinkt.
  function _mdPolyUrl(key) { return key ? 'https://polymarket.com/event/' + encodeURIComponent(key) : ''; }
  function _mdPolyLink(key, inner) {
    var u = _mdPolyUrl(key);
    return u ? '<a href="' + u + '" target="_blank" rel="noopener" class="md-polylink" title="Markt auf Polymarket \u2197">' + inner + ' <span class="md-ext">\u2197</span></a>' : inner;
  }
  // 04.08.2026 (Lucas): eigene Daten-Frische an die Radar-Live-Pruefung durchreichen. Sonst liest
  // isLive() die Frische aus _bfState (nur nach Radar-Tab gefuellt) — auf der Uebersicht leer,
  // also feuerte das Badge nie, obwohl Spiele real live waren.
  function _mdBfGenAge() {
    var g = _md.data.betfair && _md.data.betfair._meta && _md.data.betfair._meta.generatedAt;
    if (!g) return 9999;
    var t = Date.parse(g); return isNaN(t) ? 9999 : (Date.now() - t) / 60000;
  }
  function _mdBfLive(m) { return (typeof window._bfIsLive === 'function' && window._bfIsLive(m, _mdBfGenAge())) ? _MD_LIVE : ''; }  function _mdBfLiveById(id) {
    var ms = (_md.data.betfair && _md.data.betfair.matches) || [];
    for (var i = 0; i < ms.length; i++) if (String(ms[i].matchId) === String(id)) return _mdBfLive(ms[i]);
    return '';
  }
  function _mdRingRow(main, sub, conv, color) {
    return '<div class="md-r">' + _mdRing(conv, color) + '<div class="md-r-main"><div class="md-r-t">' + main + '</div>'
      + (sub ? '<div class="md-r-s">' + sub + '</div>' : '') + '</div></div>';
  }
  function _mdDonutRow(main, sub, val, valcol, pct, dcol) {
    return '<div class="md-r">' + _mdDonut(pct, dcol) + '<div class="md-r-main"><div class="md-r-t">' + main + '</div>'
      + (sub ? '<div class="md-r-s">' + sub + '</div>' : '') + '</div>'
      + (val ? '<div class="md-r-v" style="color:' + valcol + '">' + val + '</div>' : '') + '</div>';
  }
  function _mdWarnRow(main, sub, count) {
    return '<div class="md-r"><span class="md-wdot">\u26a0</span><div class="md-r-main"><div class="md-r-t">' + main + '</div>'
      + (sub ? '<div class="md-r-s">' + sub + '</div>' : '') + '</div><div class="md-r-v" style="color:var(--red)">' + (count || 1) + '</div></div>';
  }
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

  // ── 🔥 Heute spielenswert (01.08.2026, Lucas) — verdichtet die Poly-Wallet-Signale (Geld · Steam ·
  //    scharfe Wallets · Pinnacle) zu 2–3 konkreten Plays. Nutzt den Scorer aus poly-wallets.js.
  function _mdPlayRow(r) {
    var vcol = r.verdict === 'BET' ? A.good : A.gold, conv = +r.conv || 0;
    var badge = '<span style="display:inline-block;padding:1px 7px;border-radius:10px;border:1px solid ' + vcol + ';color:' + vcol + ';font-weight:800;font-size:10px;margin-right:6px">' + r.verdict + '</span>';
    var icon = (typeof _pwSportIcon === 'function') ? _pwSportIcon(r.league) + ' ' : '';
    var live = (r.htk != null && r.htk < 0) ? _MD_LIVE : '';
    var htk = (r.htk == null || r.htk < 0) ? '' : (r.htk < 1 ? '<1h' : Math.round(r.htk) + 'h');
    var main = badge + icon + _mdPolyLink(r.key, esc(String(r.match).slice(0, 38)) + ' <span style="color:var(--mi3)">→</span> <b style="color:#4cc2ff">' + esc(r.side) + '</b>') + live;
    var sub = (r.reasons || []).slice(0, 2).map(esc).join(' · ') + (htk ? ' · Anpfiff ' + htk : '');
    return _mdRingRow(main, sub, conv, _mdConvCol(conv));
  }
  function _mdPlaysHtml(plays) {
    var body = (plays && plays.length)
      ? plays.map(_mdPlayRow).join('')
      : empty('Keine klaren Plays gerade — kein Signal ist auch ein Ergebnis. Sobald Geld, Steam und scharfe Wallets sich einig sind, steht hier was.');
    return tile('🔥', 'Heute spielenswert', A.red, 'rgba(229,83,75,.14)', 'rgba(229,83,75,.32)', 'polywallets', 'alle Plays', body, 10);
  }
  function _mdFillPlays() {
    var box = document.getElementById('md-cell-play'); if (!box) return;
    if (typeof _pwEnsurePlaysData !== 'function' || typeof _pwTopPlays !== 'function') return;   // Skelett bleibt
    _pwEnsurePlaysData(function () {
      var b2 = document.getElementById('md-cell-play'); if (!b2) return;
      var plays = []; try { plays = _pwTopPlays(3, null, false) || []; } catch (e) { plays = []; }
      b2.innerHTML = _mdPlaysHtml(plays);
    });
  }

  // ── 🧪 Public-Kandidaten (Vorschau — sendet NICHT) (01.08.2026, Lucas). Zwei Logiken parallel,
  //    ein paar Tage beobachten, bevor irgendwas in den Channel geht: (A) „Top-Play" hart gegatet
  //    (Conv≥7 + bewiesene Wallet + echte Mehrheit), (B) „Whale-Watch" (Schwellen wie im Public-Push).
  function _mdPubTopRow(r) {
    var vcol = r.verdict === 'BET' ? A.good : A.gold, conv = +r.conv || 0;
    var badge = '<span style="display:inline-block;padding:1px 7px;border-radius:10px;border:1px solid ' + vcol + ';color:' + vcol + ';font-weight:800;font-size:10px;margin-right:6px">' + r.verdict + '</span>';
    var icon = (typeof _pwSportIcon === 'function') ? _pwSportIcon(r.league) + ' ' : '';
    var live = (r.htk != null && r.htk < 0) ? _MD_LIVE : '';
    var main = badge + icon + _mdPolyLink(r.key, esc(String(r.match).slice(0, 38)) + ' <span style="color:var(--mi3)">→</span> <b style="color:#4cc2ff">' + esc(r.side) + '</b>') + live;
    var sh = r.sharp || {};
    var rec = sh.n ? (sh.wins + '/' + sh.n + ' · ' + Math.round((sh.hit || 0) * 100) + '%') : '';
    var sub = 'Geld ' + Math.round((r.moneyPct || 0) * 100) + '%' + (rec ? ' · Wallet ' + rec : '');
    return _mdRingRow(main, sub, conv, _mdConvCol(conv));
  }
  function _mdWhalePubRow(w) {
    var icon = (typeof _pwSportIcon === 'function') ? _pwSportIcon(w.league) + ' ' : '';
    var tag = w.tracked
      ? '<span style="color:' + A.good + ';font-weight:800;font-size:10px">✓ tracked</span>'
      : '<span style="color:var(--mi2);font-weight:700;font-size:10px">untracked</span>';
    var live = (w.htk != null && w.htk < 0) ? _MD_LIVE : '';
    var main = icon + _mdPolyLink(w.key, esc(String(w.match).replace(/<[^>]*>/g, '').slice(0, 38)) + ' <span style="color:var(--mi3)">→</span> <b style="color:#4cc2ff">' + esc(w.side) + '</b>') + live;
    var sub = tag + ' · ' + Math.round(w.price * 100) + '¢' + ((w.tracked && w.n) ? ' · n' + w.n : '');
    var hit = (w.tracked && w.n) ? Math.round((w.hit || 0) * 100) : null;
    return hit != null
      ? _mdDonutRow(main, sub, usd(w.usd), A.poly, hit, hit >= 55 ? A.poly : '#8b949e')
      : rowEl(main, usd(w.usd), A.poly, sub, '');
  }
  var _MD_SPORT_ICO = { ESPORTS: '🎮', TENNIS: '🎾', MLB: '⚾', NBA: '🏀', WNBA: '🏀', NFL: '🏈', NHL: '🏒', MMA: '🥊', UFC: '🥊', GOLF: '⛳', SOCCER: '⚽', MLS: '⚽', CRICKET: '🏏' };
  function _mdSportIco(lg) { var k = String(lg || '').toUpperCase(); return _MD_SPORT_ICO[k] || (k.indexOf('SOCCER') === 0 ? '⚽' : '🎯'); }
  // 💰 Volumen über Norm (aus dem Großes-Geld-Tab): welche Märkte ziehen verhältnismäßig — Gesamt-$ ÷
  // Median gleicher Sportart×Phase. ×1.6 auffällig, ×2.6 stark. Ersetzt Whale-Watch (07.08.2026, Lucas).
  function _mdOverNormBody(rows) {
    if (!rows || !rows.length) return empty('Kein Markt auffällig über seiner Norm — alles im üblichen Rahmen für Sportart & Phase.');
    var mx = rows.reduce(function (a, r) { return Math.max(a, +r.ratio || 0); }, 1);
    return rows.map(function (r) {
      var col = r.ratio >= 2.6 ? A.red : A.gold;
      var label = _mdSportIco(r.league) + ' ' + (r.url
        ? '<a href="' + r.url + '" target="_blank" rel="noopener" style="color:inherit;text-decoration:none">' + r.name + ' ↗</a>'
        : r.name);
      // 08.08.2026 (Lucas): bei ~50/50 ist „Geld auf X" sinnlos (könnte genauso die Gegenseite sein) — dann neutral labeln.
      var _side = (r.favPct != null && r.favPct >= 55) ? ('Geld auf ' + esc(r.fav) + ' ' + r.favPct + '%') : ('kein klarer Favorit · ' + (r.favPct != null ? r.favPct + '%' : '~50/50'));
      var sub = _side + ' · ' + usd(r.usd);
      return rowEl(label, '×' + (+r.ratio).toFixed(1), col, sub, meter(mx ? (r.ratio / mx * 100) : 0, col));
    }).join('');
  }
  function _mdFillPubPreview() {
    var cTop = document.getElementById('md-cell-top'), cWh = document.getElementById('md-cell-whale');
    if (!cTop && !cWh) return;
    if (typeof _pwEnsurePlaysData !== 'function' || typeof _pwPublicTopPlays !== 'function' || typeof _pwOverNormTop !== 'function') return;   // Skelett bleibt
    _pwEnsurePlaysData(function () {
      var t = document.getElementById('md-cell-top'), w = document.getElementById('md-cell-whale');
      var tops = [], over = [];
      try { tops = _pwPublicTopPlays() || []; } catch (e) { tops = []; }
      try { over = _pwOverNormTop(5) || []; } catch (e) { over = []; }
      var note = '<div style="font-size:10px;color:var(--mi3);margin:-2px 0 8px">🧪 Vorschau — sendet nicht · ein paar Tage beobachten</div>';
      var topBody = note + (tops.length ? tops.slice(0, 5).map(_mdPubTopRow).join('')
        : empty('Kein Top-Play über der Schwelle — Conv≥7, bewiesene Wallet (n≥8, ≥55%), Geld-Mehrheit ≥60%. Normalfall.'));
      var overBody = _mdOverNormBody(over);
      if (t) t.innerHTML = tile('🎯', 'Top-Play', A.good, 'rgba(46,160,67,.14)', 'rgba(46,160,67,.32)', 'polywallets', 'Wallets', topBody, 0);
      if (w) w.innerHTML = tile('💰', 'Volumen über Norm', A.poly, 'rgba(25,158,112,.14)', 'rgba(25,158,112,.32)', 'polywallets', 'Wallets', overBody, 0);
    });
  }

  // ── 🕐 Betfair HT (02.08.2026, Lucas): wo das Geld auf den HALBZEIT-Märkten liegt — HT 1X2,
  // HT O/U 0.5, HT O/U 1.5. Kleinere Schwelle als Voll-Zeit (HT-Märkte tragen weniger Geld). Client-
  // seitig aus den geladenen Betfair-Preisen, gerankt nach Konzentration (€ × Anteil) wie „Kohle".
  var _HT_MK = { 'Half Time': 'HT 1X2', 'First Half Goals 0.5': 'HT O/U 0.5', 'First Half Goals 1.5': 'HT O/U 1.5' };
  var _HT_FLOOR = 1000;
  var _HT_MIN_ODD = 1.30;   // 06.08.2026 (Lucas): Geld auf HT-Quasi-Lock (@<1.30 = HT-Ergebnis entschieden) ist kein Signal — „The Draw @1.02" raus.
  var _HT_MAX_ODD = 6.0;    // 08.08.2026 (Lucas): und die andere Seite — Geld auf einen fast toten Ausgang (@>6, z.B. „Over 0.5 @11" bei 0:0 kurz vor HZ) ist Lay-/Rausch-Geld, kein Back-Signal.
  function _mdBfStale(m) {
    // 06.08.2026 (Lucas: „haengt seit Stunden"): fertige/lange-vorbei Spiele raus. finished ODER
    // Anpfiff > 3.5h her (Spiel durch, HT laengst entschieden). Ohne Kickoff/Live-Info -> nicht stale.
    var li = m.liveInfo || {};
    if (li.finished) return true;
    var ko = m.kickoff ? Date.parse(m.kickoff) : NaN;
    return !isNaN(ko) && (Date.now() - ko) > 3.5 * 3.6e6;
  }
  function _mdBfHt() {
    var ms = (_md.data.betfair && _md.data.betfair.matches) || [], rows = [];
    ms.forEach(function (m) {
      if (_mdBfStale(m)) return;   // durchgelaufene Spiele nicht mehr zeigen
      var best = null, mk = m.markets || {};
      for (var name in _HT_MK) {
        var market = mk[name]; if (!market) continue;
        var rs = market.runners || [], tot = 0, i;
        for (i = 0; i < rs.length; i++) tot += (+rs[i].vol || 0);
        if (tot <= 0) continue;
        var lead = rs.reduce(function (a, r) { return (!a || (+r.vol || 0) > (+a.vol || 0)) ? r : a; }, null);
        if (!lead) continue;
        if (typeof lead.odd === 'number' && (lead.odd < _HT_MIN_ODD || lead.odd > _HT_MAX_ODD)) continue;   // HT-Quasi-Lock ODER fast toter Ausgang -> kein Signal
        var share = (+lead.vol || 0) / tot, sc = (+lead.vol || 0) * share;
        if (!best || sc > best.sc) best = { name: name, lead: lead, share: share, vol: +lead.vol || 0, sc: sc };
      }
      if (best && best.vol >= _HT_FLOOR) rows.push({ m: m, b: best });
    });
    rows.sort(function (a, b) { return b.b.sc - a.b.sc; });
    return rows.slice(0, 5);
  }
  function _mdBfHtBody() {
    var rows = _mdBfHt();
    if (!rows.length) return empty('Kein nennenswertes HT-Geld gerade (Schwelle \u20ac1K).');
    return rows.map(function (x) {
      var m = x.m, b = x.b, pct = Math.round(b.share * 100);
      var od = (b.lead && b.lead.odd != null && +b.lead.odd > 1) ? ' <span style="color:var(--mi3)">@' + (+b.lead.odd).toFixed(2) + '</span>' : '';
      return _mdDonutRow(_bfTeams(m) + _mdBfLive(m), (_HT_MK[b.name] || b.name) + ' \u2192 ' + esc(b.lead.name) + od + _mdDirBadge(_mdDirOf(m.matchId, b.name, b.lead.name)), eur(b.vol), A.bf, pct, A.bf);
    }).join('') + _ageStr(_md.data.betfair);
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
      var f = x.f, p2 = x.p, conv = +x.conv || 0;
      var sub = esc(short(p2.market)) + (fxLeague(f) ? ' · ' + esc(String(fxLeague(f)).slice(0, 20)) : '') + (p2.edgePP != null ? ' · +' + Math.round(+p2.edgePP) + 'pp' : '');
      return conv ? _mdRingRow(teamsOf(f), sub, conv, _mdConvCol(conv))
        : rowEl(teamsOf(f), (p2.odds != null ? '@' + (+p2.odds).toFixed(2) : ''), A.good, sub, '');
    }).join('') : empty('Keine BET-Cards gerade.');

    // Streaks — Pips (Länge)
    var st = bestStreaks();
    var streaksBody = st.length ? st.map(function (s) {
      // 08.08.2026 (Lucas: „vernünftig bewerten"): „Grundrate X%" = Rate der Serien-Richtung VOR der Serie
      // (echte Basis). „reine Serie" = Serie füllt das 15-Spiele-Fenster → keine unabhängige Basis (kein Fake-100%).
      var _bq = (s.basis === 'pure') ? ' · reine Serie' : ((s.continuation && s.continuation.ratePct != null) ? ' · Grundrate ' + s.continuation.ratePct + '%' : '');
      var sub = esc(String(s.leagueName || '')) + (s.continuation && s.continuation.state ? ' · ' + esc(s.continuation.state) : '') + _bq;
      var len = +s.length || 0;
      return rowEl(fl(_flagFrom(s.country, s.league, s.leagueName)) + esc(team(s.team)) + ' <span style="color:var(--mi3);font-weight:400">·</span> ' + esc(s.market || s.type || ''),
        len + '×', A.gold, sub, pips(Math.min(len, 10), 10));
    }).join('') : empty('Keine langen Serien.');

    // Betfair — Anteilsbalken
    var bf = bestBetfair();
    var bfBody = bf.length ? bf.map(function (x) {
      var m = x.m, b = x.b, pct = Math.round(b.share * 100);
      // 05.08.2026 (Lucas): Führungsquote dazu, dann ist die Kachel immer eindeutig (@1.74 vs @1.06).
      var od = (b.lead && b.lead.odd != null && +b.lead.odd > 1) ? ' <span style="color:var(--mi3)">@' + (+b.lead.odd).toFixed(2) + '</span>' : '';
      return _mdDonutRow(teamsOf(m) + _mdBfLive(m), esc(short(b.name)) + ' → ' + esc(b.lead.name) + od + _mdDirBadge(_mdDirOf(m.matchId, b.name, b.lead.name)), eur(b.vol), A.bf, pct, A.bf);
    }).join('') : empty('Kein großes Betfair-Geld.');
    bfBody += _ageStr(_md.data.betfair);

    // Whales — USD-Balken (relativ zum größten)
    var wh = bestWhales();
    var whMax = wh.length ? wh[0].usd : 1;
    var whBody = wh.length ? wh.map(function (w) {
      var live = (w.hrs != null && w.hrs < 0) ? _MD_LIVE : '';
      var hrs = (w.hrs != null && w.hrs >= 0) ? (w.hrs < 1 ? '<1h' : Math.round(w.hrs) + 'h') : '';
      return rowEl(fl(_flagFrom(w.country, w.league, w.league)) + _mdPolyLink(w.key, esc(w.side || '?')) + live, usd(w.usd), A.poly,
        esc(String(w.league || '')) + (hrs ? ' · in ' + hrs : ''), meter(whMax ? (w.usd / whMax) * 100 : 0, A.poly));
    }).join('') : empty('Keine großen Whale-Bets gerade (ab ' + usd(MD_WHALE_MIN_USD) + ') — ruhiger Slate.');

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
      // Reihe 1 — unsere Picks
      tile('🎯', 'Beste Cards', A.good, 'rgba(46,160,67,.14)', 'rgba(46,160,67,.32)', 'national-cards', 'alle Cards', cardsBody, 40) +
      tile('🔥', 'Beste Streaks', A.gold, 'rgba(201,133,0,.14)', 'rgba(201,133,0,.32)', 'national-streaks', 'alle Serien', streaksBody, 60) +
      '<div id="md-cell-play" class="md-cell">' + tile('🔥', 'Heute spielenswert', A.red, 'rgba(229,83,75,.14)', 'rgba(229,83,75,.32)', 'polywallets', 'alle Plays', empty('lädt …'), 80) + '</div>' +
      // Reihe 2 — Betfair-Geld
      tile('💷', 'Betfair-Kohle', A.bf, 'rgba(217,89,38,.14)', 'rgba(217,89,38,.32)', 'betfair', 'Radar', bfBody, 90) +
      tile('💸', 'Frisches Geld', A.good, 'rgba(46,160,67,.14)', 'rgba(46,160,67,.32)', 'betfair', 'Radar', _mdBfFlowBody(), 100) +
      tile('🕐', 'Betfair HT', A.bf, 'rgba(217,89,38,.14)', 'rgba(217,89,38,.32)', 'betfair', 'Radar', _mdBfHtBody(), 110) +
      // Reihe 3 — Linienbewegung & Fehlbepreisung
      tile('⚡', 'Betfair-Steam', A.bf, 'rgba(217,89,38,.14)', 'rgba(217,89,38,.32)', 'betfair', 'Radar', _mdBfSteamBody(), 130) +
      tile('⚖️', 'Größte Fehlbepreisung', A.red, 'rgba(229,83,75,.14)', 'rgba(229,83,75,.32)', 'betfair', 'Radar', _mdBfMispricedBody(), 140) +
      tile('📡', 'Pinnacle-Steam', A.blue, 'rgba(57,135,229,.14)', 'rgba(57,135,229,.32)', 'sharp', 'Radar', shBody, 150) +
      // Reihe 4 — Poly
      tile('🐋', 'Poly Whale-Bets', A.poly, 'rgba(25,158,112,.14)', 'rgba(25,158,112,.32)', 'polywallets', 'Wallets', whBody, 160) +
      '<div id="md-cell-top" class="md-cell">' + tile('🎯', 'Top-Play', A.good, 'rgba(46,160,67,.14)', 'rgba(46,160,67,.32)', 'polywallets', 'Wallets', empty('lädt …'), 170) + '</div>' +
      '<div id="md-cell-whale" class="md-cell">' + tile('💰', 'Volumen über Norm', A.poly, 'rgba(25,158,112,.14)', 'rgba(25,158,112,.32)', 'polywallets', 'Wallets', empty('lädt …'), 180) + '</div>' +
      '</div>';

    p.innerHTML = _head() + _mdPulse() + _mdJetzt() + _kpis() + _mdHero() + grid +
      '<div class="md-foot">Kuratierter Überblick · tippe „alle →" für den vollen Bereich</div>';
    _mdFillPlays();
    _mdFillPubPreview();
  }
  // ── Puls: letzte 30 abgerechnete Picks (CLV / Trefferquote) ──────────────────
  function _spark(series) {
    if (!series || !series.length) return '';
    var mx = 1, i; for (i = 0; i < series.length; i++) mx = Math.max(mx, Math.abs(+series[i] || 0));
    var cols = series.map(function (v) {
      v = +v || 0; var h = Math.min(50, Math.abs(v) / mx * 50), pos = v >= 0;
      return '<div class="md-spk-col"><span class="md-spk-b" style="height:' + h + '%;' + (pos ? 'bottom:50%' : 'top:50%') + ';background:' + (pos ? A.good : A.red) + ';"></span></div>';
    }).join('');
    return '<div class="md-spk" title="CLV je Pick (alt→neu) · gruen schlaegt die Close"><div class="md-spk-mid"></div>' + cols + '</div>';
  }
  function _mdPulse() {
    var d = _md.data.pulse || {};
    var hasCards = !!d.n, bf = d.betfair, pl = d.poly;
    if (!hasCards && !(bf && bf.n) && !(pl && pl.n)) return '<section class="md-pulse md-rise"><div class="md-pulse-h">📈 Puls</div>' +
      '<div class="md-pulse-l">Noch keine abgerechneten Picks/Plays — füllt sich, sobald die ersten resolven.</div></section>';
    var metric = function (v, l, c) { return '<div class="md-pulse-m"><span class="md-pulse-v" style="color:' + (c || 'var(--mi)') + '">' + v + '</span><span class="md-pulse-l">' + l + '</span></div>'; };
    var pct = function (v) { return v == null ? '—' : Math.round(v) + '%'; };
    var roiTxt = function (v) { return v == null ? '—' : (v > 0 ? '+' : '') + (+v).toFixed(1) + '%'; };
    var col0 = function (v) { return v == null ? 'var(--mi2)' : v > 0 ? A.good : v < 0 ? A.red : 'var(--mi2)'; };
    var clvCell = function (v) { return metric(v == null ? '—' : (v > 0 ? '+' : '') + (+v).toFixed(2) + 'pp', 'Ø CLV', col0(v)); };
    var rows = '';
    if (hasCards) {
      var clv = d.avgClvPP, clvTxt = (clv == null) ? '—' : (clv > 0 ? '+' : '') + clv.toFixed(1) + 'pp';
      var beat = d.pctBeatClose, beatCol = beat == null ? 'var(--mi)' : beat >= 50 ? A.good : beat >= 33 ? A.gold : A.red;
      rows += '<div class="md-pulse-row"><span class="md-pulse-tag">🎯 Cards · ' + d.n + '</span><div class="md-pulse-ms">' +
        metric(clvTxt, 'Ø CLV', col0(clv)) +
        metric((beat == null ? '—' : Math.round(beat) + '%'), 'schlägt Close', beatCol) +
        metric((d.winPct == null ? '—' : Math.round(d.winPct) + '%'), 'Treffer · ' + (d.wins || 0) + '–' + (d.losses || 0), 'var(--mi)') +
        '</div>' + _spark(d.series) + '</div>';
    }
    if (bf && bf.n) {
      rows += '<div class="md-pulse-row"><span class="md-pulse-tag">💷 Betfair · ' + bf.n + '</span><div class="md-pulse-ms">' +
        metric(pct(bf.hitPct), 'Treffer', bf.hitPct >= 50 ? A.good : 'var(--mi)') +
        metric(roiTxt(bf.roiPct), 'ROI', col0(bf.roiPct)) +
        '</div></div>';
    }
    if (pl && pl.n) {
      rows += '<div class="md-pulse-row"><span class="md-pulse-tag">🎮 Poly (Heute) · ' + pl.n + '</span><div class="md-pulse-ms">' +
        metric(pct(pl.hitPct), 'Treffer', pl.hitPct >= 50 ? A.good : 'var(--mi)') +
        metric(roiTxt(pl.roiPct), 'ROI', col0(pl.roiPct)) +
        clvCell(pl.clvAvg) +
        (pl.openN ? metric(pl.openN, 'offen', 'var(--mi3)') : '') +
        '</div></div>';
    }
    var strip = '';
    var st = d.strip;
    if (st) {
      var SIGN = { money: 'Geld-Mehrheit', sharp: 'scharfe Wallet', steam: 'Steam', gvp: 'Geld-vs-Preis', pinn: 'Pinnacle' };
      var parts = [];
      if (st.bestConv) parts.push('⭐ Setzen: <b style="color:' + A.good + '">' + st.bestConv.key + '/10</b> +' + st.bestConv.roiPct + '% (n' + st.bestConv.n + ')');
      if (st.bestSignal) parts.push('Signal <b>' + (SIGN[st.bestSignal.key] || st.bestSignal.key) + '</b> +' + st.bestSignal.roiPct + '% (n' + st.bestSignal.n + ')');
      var live = st.inflight || {};
      var liveTxt = 'Live: 🎯 ' + (live.cards || 0) + ' · 💷 ' + (live.betfair || 0) + ' · 🎮 ' + (live.poly || 0);
      strip = '<div class="md-pulse-strip"><span>' + (parts.join(' · ') || 'Wo Setzen lohnt: sammelt noch (n<8 je Stufe)') + '</span><span class="md-pulse-live">' + liveTxt + '</span></div>';
    }
    return '<section class="md-pulse md-rise">' +
      '<div class="md-pulse-h" title="Cards nach CLV (Nordstern) · Betfair-Signale nach Treffer/ROI · Poly „Heute wetten“ Paper-Trade">📈 Puls</div>' +
      rows + strip + '</section>';
  }
  // ── „Jetzt": Spiele mit Anpfiff <= 3h und Live-Signal (BET / Poly-Lag); CLV-Cue = steamMovePP ──
  function jetztRows() {
    var now = Date.now(), horizon = now + 3 * 3600e3, out = [];
    allFixtures().forEach(function (f) {
      var ks = f.kickoff ? Date.parse(String(f.kickoff).replace('Z', '+00:00')) : NaN;
      if (isNaN(ks) || ks < now - 6 * 60000 || ks > horizon) return;
      (f.picks || []).forEach(function (p) {
        var bet = p.verdict === 'BET';
        var lag = (p.signals || []).some(function (s) { return s && s.name === 'steam_lag' && (+s.score || 0) > 0; });
        if (bet || lag) out.push({ f: f, p: p, k: ks, bet: bet, lag: lag });
      });
    });
    out.sort(function (a, b) { return a.k - b.k; });
    return out.slice(0, 6);
  }
  function _mdJetzt() {
    var rows = jetztRows();
    if (!rows.length) return '<section class="md-jetzt md-rise" style="border-color:var(--mln);background:var(--m1);padding-bottom:13px">' +
      '<div class="md-jz-h"><span style="font-size:16px;opacity:.55">⚡</span><span class="md-jz-t" style="color:var(--mi2)">Jetzt</span>' +
      '<span class="md-jz-s">kein Spiel mit Anpfiff in den nächsten 3 h & BET/Poly-Signal — meldet sich automatisch, sobald eins ansteht.</span></div></section>';
    var now = Date.now();
    var body = rows.map(function (x) {
      var f = x.f, p = x.p, min = Math.max(0, Math.round((x.k - now) / 60000));
      var ko = min < 60 ? min + 'm' : Math.floor(min / 60) + 'h' + (min % 60 ? ' ' + (min % 60) + 'm' : '');
      var mv = p.steamMovePP != null ? +p.steamMovePP : null;
      var mvHtml = mv == null ? '' : '<span class="md-jz-mv" style="color:' + (mv > 0 ? A.good : mv < 0 ? A.red : 'var(--mi2)') + '" title="Linie seit Pick — gruen: Markt zieht mit">' + (mv > 0 ? '+' : '') + mv.toFixed(1) + 'pp</span>';
      var badges = (x.bet ? '<span class="md-badge" style="background:rgba(46,160,67,.16);color:' + A.good + '">BET' + (p.convictionScore ? ' ' + p.convictionScore : '') + '</span>' : '') +
        (x.lag ? '<span class="md-badge" style="background:rgba(57,135,229,.16);color:' + A.blue + '">⚡ Poly-Lag</span>' : '');
      return '<div class="md-jz-row"><div class="md-jz-main">' +
        '<div class="md-jz-tm">' + fl(fxFlag(f)) + esc(team(f.home)) + ' <span style="color:var(--mi3);font-weight:400">v</span> ' + esc(team(f.away)) + badges + '</div>' +
        '<div class="md-jz-sub">' + esc(short(p.market)) + (p.odds != null ? ' · @' + (+p.odds).toFixed(2) : '') + (fxLeague(f) ? ' · ' + esc(String(fxLeague(f)).slice(0, 18)) : '') + '</div>' +
        '</div><span class="md-jz-ko">⏱ ' + ko + '</span>' + mvHtml + '</div>';
    }).join('');
    return '<section class="md-jetzt md-rise"><div class="md-jz-h"><span style="font-size:16px">⚡</span>' +
      '<span class="md-jz-t">Jetzt</span><span class="md-jz-s">Anpfiff in ≤ 3 h mit BET/Poly-Signal</span></div>' + body + '</section>';
  }
  window._renderMainDash = _mdRender;
  window._mdState = _md;   // Test-Hook
})();
