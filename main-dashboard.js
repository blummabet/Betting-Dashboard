/* main-dashboard.js — MAIN-Dashboard „Übersicht" · Command-Center (29.07.2026, Lucas) ─────
 * „Großer Design-Sprung": kuratiertes Cockpit als Einstieg. Eigenes, in sich geschlossenes
 * Design-System (md-*), injiziert per <style>. Farben CVD-validiert (dataviz-Skill):
 *   Pinnacle #3987e5 · Betfair #d95926 · Poly #199e70 · Soft #c98500.
 * Bausteine: „Mehrfach gedeckt" (Konjunktion) · KPI-Leiste · Signal-Kacheln
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
    red: '#e5534b', money: '#e8843a', flow: '#a78bfa', ink: '#f0f4f8', ink2: '#9aa4b1', ink3: '#6b7480'
  };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]; }); }
  function eur(v) { v = +v || 0; if (v >= 1e6) return '€' + (v / 1e6).toFixed(2) + 'M'; if (v >= 1e3) return '€' + (v / 1e3).toFixed(v >= 1e5 ? 0 : 1).replace('.0', '') + 'K'; return '€' + Math.round(v); }
  function usd(v) { v = +v || 0; if (v >= 1e6) return '$' + (v / 1e6).toFixed(2) + 'M'; if (v >= 1e3) return '$' + (v / 1e3).toFixed(v >= 1e5 ? 0 : 1).replace('.0', '') + 'K'; return '$' + Math.round(v); }
  function team(x) { if (!x) return '?'; if (typeof x === 'string') return x; return x.name || x.team || x.id || '?'; }
  // 28.08.2026 (Lucas: „da passt noch was nicht mit den Team-Namen") — im Triple-Konsens stand
  // „45 v 52" statt „Everton v Crystal Palace". Ursache: in liga-data.json / mls-data.json ist
  // fx.home die TEAM-ID als String ("45"), der Klarname liegt daneben in fx.homeName. team()
  // bekommt nur die ID und gibt sie mangels Besserem unveraendert zurueck. Im WM-Datensatz gibt
  // es homeName gar nicht — dort ist fx.home ein Kuerzel ("MEX"), dessen Name in
  // groups[*].teams steht. Reihenfolge deshalb: Name-Feld → ID→Name-Map des Datensatzes → Rohwert.
  function fxTeam(f, seite) {
    if (!f) return '?';
    var nm = (seite === 'home') ? f.homeName : f.awayName;
    if (nm) return nm;
    var id = (seite === 'home') ? f.home : f.away;
    var map = _MD_TEAM_NAMES && _MD_TEAM_NAMES[String(id)];
    return map || team(id);
  }
  // ID→Name ueber ALLE geladenen Datensaetze. Bewusst global statt pro Aufruf: dieselbe Map
  // bedient Liga, MLS und WM, und die IDs kollidieren zwischen den Datensaetzen nicht.
  var _MD_TEAM_NAMES = {};
  function _mdLearnTeamNames(data) {
    if (!data || typeof data !== 'object') return;
    var groups = data.groups || {};
    for (var code in groups) {
      var ts = (groups[code] || {}).teams || [];
      for (var i = 0; i < ts.length; i++) {
        var t = ts[i];
        if (t && t.id != null && t.name) _MD_TEAM_NAMES[String(t.id)] = t.name;
      }
    }
  }
  function short(k) {
    return String(k || '').replace('Over/Under', 'Ü/U').replace(' Goals', '').replace('Both teams to Score?', 'BTTS')
      .replace('Match Odds', '1X2').replace('First Half', 'HZ1').replace('Half Time/Full Time', 'HZ/EZ')
      .replace('Half Time', 'HZ1').replace('Correct Score', 'Exakt').replace('Draw no Bet', 'DNB');
  }
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  // 30.08.2026 (Lucas-Checkup): las nur _meta.generatedAt/updated_at. Die Card-Datensätze
  // stempeln aber picksUpdatedAt/oddsUpdatedAt, und Money-Map/Konsens stempeln generatedAt auf
  // OBERSTER Ebene — für die drei kam nie ein Alter zurück, also stand nirgends „Stand vor X".
  function _ageMin(obj) {
    if (!obj) return null;
    var m = obj._meta || {};
    var g = m.picksUpdatedAt || m.generatedAt || m.updated_at || m.oddsUpdatedAt || m.dataUpdatedAt
      || obj.generatedAt || obj.updatedAt;
    if (!g) return null;
    var t = Date.parse(String(g).replace(' ', 'T')); 
    return isNaN(t) ? null : Math.max(0, (Date.now() - t) / 60000);
  }
  // Alle geladenen Quellen mit ihrem echten Alter — und die älteste davon.
  // Der Kopf zeigte bisher die BROWSER-UHR („Stand 10:56"). Die sagt nichts über die Daten:
  // am 30.08. war Betfair 12 Minuten alt, die Cards 5,9 Stunden und die Serien 12,1 Stunden —
  // die Seite behauptete für alles dieselbe Frische.
  // 03.09.2026 (Lucas-Checkup): hier standen 8 von 13 geladenen Datensaetzen. `mlsStreaks`,
  // `bfDir`, `bfTrack`, `killer` und `freigabe` fehlten — und der Polymarket-LIVE-Feed hat gar
  // kein Feld in `_md.data`, er kommt ueber `_pwCache.broadLiveNow`. Folge: oben stand
  // „aelteste Quelle Serien vor 64 Min", waehrend dieselbe Seite unten „letzte Erfassung vor
  // 2 h" meldete. Der Kommentar in _head() verspricht ausdruecklich das Gegenteil („die Seite
  // ist nur so frisch wie ihr traegster Feed") — jetzt stimmt er wieder.
  //
  // Eine Quelle OHNE lesbaren Zeitstempel taucht bewusst nicht auf: _ageMin gibt dann null
  // zurueck, und ein unbekanntes Alter darf sich nicht als frisch ausgeben (es faellt aber auch
  // nicht als „aelteste" ins Gewicht — dafuer ist der Datei-Waechter zustaendig, nicht diese Zeile).
  function _mdQuellenAlter() {
    var d = _md.data || {};
    var q = [['Cards', d.liga], ['Cards MLS', d.mls],
             ['Serien', d.ligaStreaks], ['Serien MLS', d.mlsStreaks],
             ['Betfair', d.betfair], ['Börse', d.bfOverview], ['Richtung', d.bfDir],
             ['Betfair-Track', d.bfTrack], ['Money-Map', d.moneyMap],
             ['Puls', d.pulse], ['Poly', d.whales],
             ['Konjunktion', d.killer], ['Register', d.freigabe]];
    var out = [];
    q.forEach(function (x) { var a = _ageMin(x[1]); if (a != null) out.push({ n: x[0], min: a }); });
    // Poly-LIVE fuehrt seine eigene Rechnung (dieselbe, die die Kachel unten anzeigt).
    try {
      if (typeof _pwLiveStaleMin === 'function') {
        var lm = _pwLiveStaleMin();
        if (lm != null && isFinite(lm)) out.push({ n: 'Poly LIVE', min: lm });
      }
    } catch (e) { /* Poly-Cache noch nicht geladen — dann eben ohne */ }
    out.sort(function (a, b) { return b.min - a.min; });
    return out;
  }
  function _ageTxt(m) { return m >= 90 ? (m / 60).toFixed(1).replace('.', ',') + ' h' : Math.round(m) + ' Min'; }
  function _ageStr(obj) {
    var m = _ageMin(obj); if (m == null) return '';
    var col = m > 35 ? '#f2a6a6' : m > 15 ? 'var(--gold)' : 'var(--mi3)';
    return '<div style="text-align:right;font-size:10px;color:' + col + ';padding:6px 0 2px">Stand vor ' + _ageTxt(m) + '</div>';
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
      // 30.08.2026 (Lucas: „was aber dann mit dem tripple konsens? ist das nicht teils redundant?“):
      // Der Triple-Konsens ist RAUS. Nicht wegen Redundanz zum Konjunktions-Element — die Universen
      // überschneiden sich nur zu 7% (63 von 68 Konjunktions-Zeilen liegen in Ligen, in denen es gar
      // keine Card gibt). Sondern weil das Panel für sich genommen nichts trug: die Spalte „Einig“
      // sortierte nach der KLEINSTEN Spanne zwischen den Quellen, wählte also per Konstruktion die
      // Spiele mit fertigem Preis; von 139 Zeilen waren 91 NOBET und nur 2 BET; und in der
      // Ausreißer-Spalte scherte durchgehend „Soft“ aus — dass die langsamen Buchmacher hinterher-
      // hinken, deckt steam_lag in den Cards längst ab. Die Regeln .md-hero* .md-agree* .md-arow*
      // .md-cols .md-col* .md-legend .md-lg gingen mit dem Markup; keine andere Sektion nutzte sie.
      /* tiles */
      '.md-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:14px;}',
      '.md-cell{display:contents;}',
      // Vollbreiten-Elemente (Money Map, Polymarket LIVE) — spannen alle 3 Spalten (11.08.2026, Lucas)
      '.md-wide{grid-column:1/-1;}',
      '.md-mm-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px;margin-top:2px;}',
      '@media(max-width:760px){.md-mm-grid{grid-template-columns:1fr;}}',
      '.md-lv-cols{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:2px;}',
      '@media(max-width:760px){.md-lv-cols{grid-template-columns:1fr;gap:8px;}}',
      '.md-lv-col{min-width:0;}',
      '.md-lv-sub{display:flex;align-items:center;gap:7px;font-size:11px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:var(--mi3);margin:2px 0 6px;}',
      '.md-lv-tags{display:flex;justify-content:flex-end;margin-top:2px;}',
      '.md-lv-tag{font-size:9px;font-weight:800;border:1px solid;border-radius:5px;padding:0 5px;}',
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
      '.md-r-top{align-items:flex-start;}',
      '.md-r-top .md-ring{margin-top:1px;}',
      '.md-sig{display:flex;gap:9px;margin-top:9px;}',
      '.md-sig-c{flex:1;min-width:0;}',
      '.md-sig-off{opacity:.5;}',
      '.md-sig-h{display:flex;justify-content:space-between;align-items:baseline;gap:5px;}',
      '.md-sig-l{font-size:8.5px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:var(--mi3);white-space:nowrap;}',
      '.md-sig-v{font-family:"JetBrains Mono","SF Mono",Menlo,monospace;font-size:11.5px;font-weight:800;white-space:nowrap;}',
      '.md-sig-bar{position:relative;height:4px;border-radius:3px;background:var(--mln);margin-top:4px;overflow:hidden;}',
      '.md-sig-bar i{position:absolute;left:0;top:0;bottom:0;border-radius:3px;}',
      '.md-sig-sub{font-size:9px;color:var(--mi3);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
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
      '.md-jz-row{display:flex;align-items:center;gap:10px;padding:9px 0;border-top:1px solid var(--mln);}',
      '.md-jz-row:first-of-type{border-top:0;}',
      '.md-jz-main{min-width:0;flex:1;}',
      '.md-jz-tm{font-size:13px;font-weight:600;color:var(--mi);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      '.md-jz-sub{font-size:11px;color:var(--mi2);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      '.md-jz-ko{font-family:"JetBrains Mono",monospace;font-size:12px;font-weight:800;color:var(--bf);white-space:nowrap;}',
      '.md-jz-row3{display:block;padding:11px 0;border-top:1px solid var(--mln);}',
      '.md-jz-row3:first-of-type{border-top:0;}',
      '.md-jz-l1{display:flex;align-items:center;gap:6px;}',
      '.md-jz-n{color:var(--mi3);font-weight:800;font-size:11px;}',
      '.md-jz-nm{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px;font-weight:600;color:var(--mi2);}',
      '.md-jz-pick{font-size:14.5px;font-weight:800;color:var(--mi);margin-top:5px;line-height:1.25;}',
      '.md-jz-pick b{color:#4cc2ff;}',
      '.md-jz-pick .q{color:var(--mi3);font-weight:700;font-size:12px;}',
      '.md-jz-div{font-size:12.5px;font-weight:700;line-height:1.3;}',
      '.md-jz-mv{font-family:"JetBrains Mono",monospace;font-size:12px;font-weight:800;white-space:nowrap;text-align:right;min-width:52px;}',
      '.md-badge{display:inline-block;font-size:9.5px;font-weight:800;padding:1px 6px;border-radius:5px;margin-left:6px;vertical-align:1px;}',
      // 30.08.2026 (Lucas: „wir müssen hier noch rausarbeiten was der Unterschied ist"): zwei
      // geldgetriebene Sektionen standen untereinander und sahen aus wie zweimal dasselbe.
      // Sie sind aber gegensätzlich gebaut — die eine ist ein FILTER (alle Bedingungen
      // gleichzeitig, kann leer sein), die andere eine RANGLISTE (bestes Einzelsignal, ist nie
      // leer). Das steht jetzt als erstes Wort in beiden Köpfen, in derselben Form.
      '.md-mech{font-size:9px;font-weight:800;letter-spacing:.07em;text-transform:uppercase;padding:2px 6px;border-radius:5px;border:1px solid;white-space:nowrap;}',
      // 01.09.2026 (Lucas: „das wirkt jetzt schon sehr oft quasi redundant, oder?"). Gemessen war
      // die Ueberschneidung null — die drei Sektionen zeigten NIE dasselbe Spiel. Redundant war
      // nicht der Inhalt, sondern die FORM: drei gleich gebaute Koepfe mit je eigenem Badge,
      // eigener Bauart-Pille und eigenem Erklaersatz, untereinander, die alle nach „was soll ich
      // spielen?" klingen. Drei Antworten sehen aus wie dreimal dieselbe Frage, wenn nichts sagt,
      // wie sie zusammenhaengen.
      //
      // Jetzt: EIN Rahmen, EINE Ueberschrift, drei nummerierte Ebenen von streng nach breit.
      // Die Nummer ist die Aussage — man liest eine Leiter hinab, nicht drei Konkurrenten
      // nebeneinander. Deshalb auch bewusst KEIN eigener Rahmen/Farbverlauf je Ebene mehr.
      // (Die eigenen Rahmen/Koepfe von „Mehrfach gedeckt" und „Top-Wetten jetzt" — .md-jetzt,
      //  .md-jz-h/-t/-s, .md-kl-h/-t/-s/-st — sind am 01.09. entfallen: beide sind jetzt Ebenen
      //  EINER Sektion und teilen sich deren Kopf. Zeilen-, Chip- und Bilanz-Klassen bleiben.)
      '.md-sp{background:radial-gradient(130% 150% at 0% 0%,rgba(46,160,71,.09),transparent 55%),var(--m1);border:1px solid var(--mln);border-radius:14px;padding:13px 15px 10px;margin-top:12px;}',
      '.md-sp-h{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;}',
      '.md-sp-t{font-weight:800;font-size:14.5px;color:var(--mi);letter-spacing:-.01em;}',
      '.md-sp-s{font-size:11px;color:var(--mi2);width:100%;margin-top:3px;line-height:1.5;}',
      '.md-eb{margin-top:13px;padding-top:11px;border-top:1px solid var(--mln);}',
      '.md-eb-h{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}',
      '.md-eb-n{font-family:"JetBrains Mono",monospace;font-size:10px;font-weight:800;color:var(--mi3);border:1px solid var(--mln2);border-radius:5px;padding:1px 6px;flex-shrink:0;}',
      '.md-eb-q{font-weight:800;font-size:12.5px;color:var(--mi);}',
      '.md-eb-st{margin-left:auto;font-size:10px;font-weight:700;padding:2px 7px;border-radius:6px;white-space:nowrap;}',
      '.md-eb-s{font-size:10.5px;color:var(--mi3);width:100%;line-height:1.45;margin-top:2px;}',
      // Die Ebenen-Nummer traegt die Strenge: 1 ist das engste Tor, 3 das weiteste.
      '.md-eb-n.e1{color:#2ea047;border-color:rgba(46,160,71,.45);}',
      '.md-eb-n.e2{color:#4cc2ff;border-color:rgba(76,194,255,.45);}',
      '.md-eb-n.e3{color:#d95926;border-color:rgba(217,89,38,.45);}',
      // 29.08.2026 (Lucas): das Konjunktions-Element. Bewusst anders als „Top-Wetten jetzt":
      // dunkler, ruhiger, weniger Zeilen. Die Sektion soll aussehen, als koste jede Zeile etwas.
      '.md-kl{background:radial-gradient(130% 150% at 0% 0%,rgba(76,194,255,.10),transparent 58%),var(--m1);border:1px solid rgba(76,194,255,.26);border-radius:14px;padding:13px 15px 10px;margin-top:12px;}',
      '.md-kl-grp{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.05em;color:var(--mi3);margin:12px 0 2px;display:flex;align-items:center;gap:7px;}',
      '.md-kl-grp i{height:1px;flex:1;background:var(--mln);font-style:normal;}',
      '.md-kl-row{padding:11px 0;border-top:1px solid var(--mln);}',
      // Die EBENEN bleiben untereinander (die Reihenfolge streng→breit ist die Aussage), aber die
      // SPIELE innerhalb einer Ebene sind untereinander gleichrangig — die duerfen nebeneinander.
      // Erst ab 1040px: darunter passt das Deckungs-Profil (sieben feste Bloecke) nicht in eine
      // halbe Spalte, und dann zaehlt man keine Bloecke mehr, sondern liest Text.
      '@media(min-width:1040px){',
      '  .md-kl-paar{display:grid;grid-template-columns:1fr 1fr;gap:0 26px;}',
      '  .md-kl-paar>.md-kl-row:nth-child(-n+2){border-top:0;}',
      '  .md-jz-paar{display:grid;grid-template-columns:1fr 1fr;gap:0 26px;}',
      '  .md-jz-paar>.md-jz-row3:nth-child(-n+2){border-top:0;}',
      '}',
      '.md-kl-l1{display:flex;align-items:center;gap:7px;}',
      '.md-kl-nm{flex:0 1 auto;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px;font-weight:600;color:var(--mi2);}',
      '.md-kl-l1>.md-kl-halt,.md-kl-l1>.md-kl-live{margin-left:auto;}',
      '.md-kl-pick{font-size:16px;font-weight:800;color:var(--mi);margin-top:4px;line-height:1.2;letter-spacing:-.01em;}',
      '.md-kl-pick b{color:#4cc2ff;}',
      '.md-kl-pick .q{color:var(--mi3);font-weight:700;font-size:12px;}',
      '.md-kl-ch{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px;}',
      // Deckungs-Profil (30.08.2026). Feste Plätze je Quelle → zwei Zeilen sind vergleichbar.
      // Marken bewusst dünn (dataviz: thin marks), 4px gerundetes Datenende, 2px Luft dazwischen.
      '.md-kl-deck{display:flex;align-items:center;gap:12px;margin-top:9px;flex-wrap:wrap;}',
      '.md-kl-str{display:flex;align-items:center;gap:5px;}',
      '.md-kl-str.aus{opacity:.4;}',
      '.md-kl-pips{display:flex;gap:2px;}',                       /* 2px Untergrund-Luft zwischen Fuellungen */
      '.md-kl-pip{width:10px;height:5px;border-radius:4px;display:block;}',   /* 4px gerundetes Datenende */
      '.md-kl-pip.leer{background:var(--mln2);}',
      '.md-kl-lbl{font-size:9px;font-weight:800;letter-spacing:.04em;color:var(--mi3);}',
      /* Zaehler zuerst gelesen: die Kennzahl der Zeile, nicht ein Anhaengsel am Ende. */
      '.md-kl-cnt{font-family:"JetBrains Mono",monospace;font-size:17px;font-weight:800;color:var(--mi);line-height:1;min-width:38px;}',
      // 01.09.2026 — Buecher-Punktestand. Die grosse Zahl traegt die Aussage, die Bloecke sagen
      // WOHER sie kommt. Jeder Block nennt sein Buch im Klartext (BF/POLY/PIN/ZEIT), damit die
      // Farbe nie allein entscheidet — dieselbe Regel wie beim Deckungs-Profil darunter.
      '.md-pk-b{display:inline-flex;align-items:center;gap:5px;padding:2px 7px;border:1px solid var(--mi3);border-radius:7px;font-size:10.5px;line-height:1.5;white-space:nowrap}',
      '.md-pk-b b{font-weight:800;letter-spacing:.3px}',
      '.md-pk-b i{font-style:normal;font-family:"JetBrains Mono",monospace;color:var(--mi2);font-weight:700}',
      '.md-pk-d{font-size:10.5px;color:var(--mi2);white-space:nowrap;padding:2px 0}',
      '.md-kl-cnt i{font-style:normal;font-size:11px;font-weight:700;color:var(--mi3);}',
      '.md-kl-live{display:inline-flex;align-items:center;gap:4px;font-size:10px;font-weight:700;color:var(--good);white-space:nowrap;}',
      '.md-kl-live>i{width:5px;height:5px;border-radius:50%;background:var(--good);display:block;}',
      '.md-kl-halt{font-size:10px;color:var(--mi3);white-space:nowrap;}',
      '.md-kl-row.ruht{opacity:.72;}',
      '.md-kl-c{font-size:10px;font-weight:700;padding:2px 7px;border-radius:6px;background:rgba(120,130,150,.13);color:var(--mi2);white-space:nowrap;}',
      '.md-kl-c.on{background:rgba(76,194,255,.15);color:#4cc2ff;}',
      '.md-kl-c.off{opacity:.45;}',
      '.md-kl-foot{font-size:10.5px;color:var(--mi3);margin-top:11px;line-height:1.5;border-top:1px solid var(--mln);padding-top:9px;}',
      '.md-kl-det{margin-top:9px;border-top:1px solid var(--mln);padding-top:8px;}',
      '.md-kl-sum{display:flex;align-items:center;gap:8px;flex-wrap:wrap;cursor:pointer;font-size:11px;font-weight:700;color:var(--mi2);list-style:none;}',
      '.md-kl-sum::-webkit-details-marker{display:none;}',
      '.md-kl-sum::before{content:"▸";color:var(--mi3);font-size:9px;}',
      '.md-kl-det[open] .md-kl-sum::before{content:"▾";}',
      '.md-kl-bliste{margin-top:8px;display:flex;flex-direction:column;gap:1px;}',
      '.md-kl-bz{display:flex;align-items:center;gap:8px;font-size:11px;padding:3px 0;border-top:1px solid var(--mln);}',
      '.md-kl-bz:first-child{border-top:0;}',
      '.md-kl-bn{font-weight:700;color:var(--mi);min-width:0;flex:0 1 auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      // 01.09.2026 (Lucas: braucht das am Desktop die gesamte Breite?). Nein — und schuld war
      // nicht das Layout der Ebenen, sondern dieses flex:1. Die mittlere Zelle frass allen
      // Restplatz und drueckte ROI/CLV an den aeussersten Rand: bei 1200px wanderte das Auge die
      // volle Breite, um „Mix bf+money" mit „+29%" zusammenzubringen. Jetzt waechst die Zeile nur
      // bis zu einem Maass; was uebrig bleibt, bleibt leer — Leerraum rechts ist billiger als eine
      // Zeile, die man nicht mehr in einem Blick zusammenbekommt.
      '.md-kl-bl{color:var(--mi3);flex:0 1 auto;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      '.md-kl-bz{max-width:820px;}',
      '.md-kl-bz>.md-kl-bo{margin-left:auto;}',
      '.md-kl-bo{font-family:"JetBrains Mono",monospace;color:var(--mi2);white-space:nowrap;}',
      '.md-kl-bs{font-size:9px;font-weight:800;color:var(--mi3);}',
      '.mpc-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;}',
      '@media(max-width:760px){.mpc-grid{grid-template-columns:repeat(2,1fr);}}',
      '.mpc{position:relative;overflow:hidden;text-align:left;font:inherit;color:var(--mi);cursor:pointer;background:var(--m2);border:1px solid var(--mln);border-radius:12px;padding:11px 12px 10px;display:block;transition:transform .15s,border-color .15s;}',
      '.mpc:hover{transform:translateY(-2px);border-color:var(--ac);}',
      '.mpc::before{content:\"\";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--ac,var(--mi3));}',
      '.mpc-h{display:flex;align-items:center;gap:6px;font-size:11.5px;font-weight:800;color:var(--mi);}',
      '.mpc-h b{margin-left:auto;font-family:\"JetBrains Mono\",monospace;font-size:10px;font-weight:700;color:var(--mi3);}',
      '.mpc-big{font-family:\"JetBrains Mono\",monospace;font-size:24px;font-weight:800;line-height:1;letter-spacing:-.03em;margin:10px 0 3px;color:var(--mi);}',
      '.mpc-soft{font-size:15px;color:var(--mi3);padding:5px 0 3px;}',
      '.mpc-cap{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--mi3);}',
      '.mpc-subs{display:flex;gap:12px;margin-top:9px;flex-wrap:wrap;}',
      '.mpc-sub{display:flex;flex-direction:column;gap:2px;}',
      '.mpc-sub b{font-family:\"JetBrains Mono\",monospace;font-size:12.5px;font-weight:800;line-height:1;}',
      '.mpc-sub i{font-size:9px;color:var(--mi3);font-style:normal;}',
      '.mpc-meter{position:relative;height:6px;border-radius:4px;background:var(--mln);margin-top:10px;overflow:hidden;}',
      '.mpc-meter>i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;}',
      '.mpc-meter>span{position:absolute;left:50%;top:-1px;bottom:-1px;width:1px;background:var(--mi3);opacity:.5;}',
      '.mpc-split{display:flex;gap:2px;height:8px;border-radius:4px;overflow:hidden;margin-top:10px;}',
      '.mpc-split>i{border-radius:2px;}',
      '.mpc-hint{margin-left:auto;font-size:9.5px;font-weight:600;letter-spacing:0;text-transform:none;color:var(--mi3);}',
      '.md-kpi{cursor:pointer;text-align:left;font:inherit;color:var(--mi);width:100%;display:block;transition:transform .15s,border-color .15s;}',
      '.md-kpi:hover{transform:translateY(-2px);border-color:var(--kc);}',
      '.md-kpi-top{display:flex;align-items:center;gap:5px;font-size:10.5px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;color:var(--mi2);margin-bottom:9px;}'
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
      jf('betfair_overview.json'), jf('betfair_direction.json'), jf('money_map.json'),
      // 29.08.2026 (Lucas: „das müsste man auf der Übersicht auch anpassen"): der Betfair-Track.
      // Die Poly-Zeilen tragen ihre Conviction und ziehen deshalb bei jeder Neugewichtung
      // automatisch mit — die Betfair-Zeilen hingen an festen Konstanten und bewegten sich nie.
      jf('betfair_track_record.json'),
      // 29.08.2026 (Lucas: „sowas könnte man schon als super killer Element bauen"): die
      // Konjunktions-Sektion + das Freigabe-Register, das ihr Urteil trägt. Beides muss hier
      // rein, weil die Sektion NICHT behaupten darf, sie sei spielbar — sie zeigt ihren
      // eigenen Stand aus freigabe.json.
      jf('killer.json'), jf('freigabe.json')]);
  }
  function _mdLoad(force) {
    if (_md.loading) return;
    _mdStyle();
    if (_md.data && !force) { _mdRender(); return; }
    _md.loading = true;
    var p = document.getElementById('mainDashPanel');
    if (p && !_md.data) { p.classList.add('mdash'); p.innerHTML = _head() + '<div class="md-empty" style="text-align:center;padding:52px 0;">⏳ Übersicht wird geladen …</div>'; }
    _mdFetch().then(function (a) {
      _md.data = { liga: a[0], mls: a[1], ligaStreaks: a[2], mlsStreaks: a[3], betfair: a[4], whales: a[5], pulse: a[6], bfOverview: a[7], bfDir: a[8], moneyMap: a[9], bfTrack: a[10], killer: a[11], freigabe: a[12] };
      _md.loading = false; _mdRender();
    });
  }
  window._mdLoad = _mdLoad;

  // 19.08.2026 (Lucas: „Betfair-HT-Kasten zeigt alte Spiele, Live-Badge fehlt bei laufenden"): das
  // Main-Dashboard lud die Daten NUR EINMAL beim Öffnen und aktualisierte nie. Spiele, die nach dem
  // Laden anpfiffen, hatten im eingefrorenen Snapshot kein liveInfo.time -> kein Live-Badge; alte Spiele
  // blieben liegen, „Stand vor X Min" wuchs unbegrenzt, obwohl die Betfair-Action 1-2x weitergelaufen
  // war. Fix (wie der Radar): periodischer Refresh alle 2 Min + beim Zurückkehren zum Tab, NUR wenn das
  // Dashboard sichtbar ist. _mdLoad(true) re-fetcht frisch ohne Lade-Platzhalter (Daten sind ja schon da).
  function _mdRefresh() {
    if (_md.loading) return;
    var p = document.getElementById('mainDashPanel');
    if (!p || p.style.display === 'none') return;   // nur nachladen, wenn das Dashboard sichtbar ist
    _mdLoad(true);
  }
  window._mdRefresh = _mdRefresh;
  if (typeof window !== 'undefined' && !window._mdAutoRefreshSet && !window._mdNoAutoRefresh
      && !/jsdom/i.test((window.navigator && window.navigator.userAgent) || '')) {   // in jsdom-Tests aus (Timer würde node offenhalten)
    window._mdAutoRefreshSet = true;
    var _mdTimer = setInterval(_mdRefresh, 2 * 60000);
    if (_mdTimer && typeof _mdTimer.unref === 'function') _mdTimer.unref();   // Tests: node sauber beenden
    document.addEventListener('visibilitychange', function () { if (!document.hidden) _mdRefresh(); });
  }

  // ── Daten-Extraktion ──────────────────────────────────────────────────────
  // 28.08.2026 (Lucas: „der Triple-Konsens ist immer leer"): Der Walker suchte Objekte, die
  // SELBST ein picks-Array tragen. In liga-data.json / mls-data.json haengen die Picks aber gar
  // nicht am Fixture — sie liegen in einer eigenen Map unter `picks`, verschluesselt als
  // `<LIGA>-<Spieltag>-<homeId>-<awayId>`. Ergebnis: der Walker fand NULL Fixtures, und zwar in
  // allen drei Datensaetzen. Damit lagen nicht nur der Triple-Konsens brach, sondern alles, was
  // auf allFixtures() steht: beste Cards, Sharp-Moves, „Jetzt" und die Engine-Kandidaten.
  //
  // Die Daten waren die ganze Zeit da: 92 Picks mit consensus-Feld, davon 67 „konsens" und
  // 3 „divergenz". Nur zusammengefuehrt hat sie niemand. (Verdrahtung ist nicht Ankunft.)
  function _mdJoinPicks(data) {
    if (!data || typeof data !== 'object') return [];
    _mdLearnTeamNames(data);
    var picks = data.picks || {}, out = [];
    var add = function (code, fx) {
      if (!fx || typeof fx !== 'object') return;
      var key = code + '-' + fx.matchday + '-' + fx.home + '-' + fx.away;
      var ps = picks[key];
      // Kopie statt Mutation: die Rohdaten bleiben unberuehrt, sonst haengen die Picks nach
      // einem Refresh doppelt dran.
      out.push(Object.assign({}, fx, {
        picks: Array.isArray(ps) ? ps : [],
        leagueName: fx.leagueName || code,
        group: code,
        // Namen hier schon aufloesen: alles Nachgelagerte (Hero, „Jetzt", Sharp-Moves) liest
        // dieselbe Kopie und muss die ID→Name-Frage nicht je Stelle neu beantworten.
        homeName: fxTeam(fx, 'home'),
        awayName: fxTeam(fx, 'away'),
      }));
    };
    var groups = data.groups || {};
    for (var code in groups) {
      var fxs = (groups[code] || {}).fixtures || [];
      for (var i = 0; i < fxs.length; i++) add(code, fxs[i]);
    }
    // KO-Spiele liegen in koFixtures, nicht in groups — das hat schon mehrfach Picks gekostet.
    var ko = data.koFixtures || [];
    for (var j = 0; j < ko.length; j++) add(String(ko[j] && ko[j].round || 'KO'), ko[j]);
    return out;
  }

  function fixtures(data) {
    var joined = _mdJoinPicks(data);
    // Nur uebernehmen, wenn der Join auch WIRKLICH Picks gefunden hat. `joined.length` allein
    // reichte nicht: bei einem Format, in dem die Picks am Fixture haengen, lieferte der Join
    // Fixtures mit LEEREN Pick-Arrays — und verdraengte damit den Fallback, der sie gefunden
    // haette. Fehlende Daten sahen aus wie „nichts da".
    if (joined.some(function (f) { return f.picks && f.picks.length; })) return joined;
    // Fallback fuer aeltere/andere Formate, in denen die Picks doch am Fixture haengen.
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
  // 30.08.2026 (Lucas-Checkup): „Beste Cards" zeigte FC Cincinnati — Anpfiff 179 Stunden her,
  // also seit siebeneinhalb Tagen gespielt. Die Pinnacle-Steam-Kachel zeigte drei von fünf
  // Zeilen auf bereits gespielten Partien, die oberste seit 331 Stunden (14 Tage). Von 299
  // Steam-Picks im Bestand sind 192 vorbei — zwei Drittel.
  //
  // Ursache: betPicks() und allSharp() liefen über ALLE Fixtures, ohne den Anpfiff zu prüfen.
  // Jede andere Kachel tut das (Top-Wetten hat ein Fenster, Betfair prüft live) — diese zwei
  // sind nie nachgezogen worden. Deshalb standen dort auch dieselben Zahlen wie am Vortag: die
  // Spiele waren durch, die Werte konnten sich gar nicht mehr bewegen.
  var MD_FIX_MAX_H = 72;   // weiter draußen ist es keine Empfehlung mehr, sondern ein Ausblick
  function _fxKommend(f, maxH) {
    var t = Date.parse(String(f && (f.kickoff || f.date) || '').replace('Z', '+00:00'));
    if (!isFinite(t)) return false;          // ohne Anpfiff nicht raten — fail-closed
    var h = (t - Date.now()) / 3.6e6;
    return h > -2 && h <= (maxH || MD_FIX_MAX_H);   // 2h Nachlauf: laufende Spiele bleiben sichtbar
  }
  function fxLeague(f) { return f.leagueName || f.league || (f.group || ''); }

  function betPicks() {
    var rows = [];
    allFixtures().forEach(function (f) {
      if (!_fxKommend(f)) return;   // s. _fxKommend — gespielte Karten sind keine Empfehlung
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
  // ── Betfair-Track auf der Übersicht (29.08.2026) ────────────────────────────────────────
  // Dieselben drei Schwellen wie in sharp_signals/betfair_money.py und im Radar. Sie stehen hier
  // zum dritten Mal — deshalb prüft tests/frontend/uebersicht-bftrack.test.mjs alle drei Dateien
  // gegeneinander. In den Cards dreht ein verlierender Liga×Markt das Signal um (Fade). Auf der
  // Übersicht gibt es nichts umzudrehen: eine Zeile in „Top-Wetten jetzt" ist eine Empfehlung,
  // und eine Empfehlung aus einem Eimer, in dem dem Geld zu folgen historisch verliert, gehört
  // nicht in die Liste. Also fliegt sie raus statt gedreht zu werden.
  var MD_BFTR_MIN_N = 15, MD_BFTR_FADE = -0.10, MD_BFTR_BOOST = 0.05;
  function _mdBfTrack(league, market) {
    try {
      var blm = (_md.data.bfTrack || {}).byLeagueMarket || {};
      var v = blm[String(league) + '|' + String(market)];
      if (!v || (v.n || 0) < MD_BFTR_MIN_N || typeof v.roi !== 'number') return null;
      return { roi: v.roi, n: v.n, traegt: v.roi >= MD_BFTR_BOOST, verliert: v.roi <= MD_BFTR_FADE };
    } catch (e) { return null; }
  }
  // ⚡ Sharpe Bewegungen: Vor-Anpfiff-Quotenbewegung (pp). +pp = Quote fällt = Geld drauf, −pp = driftet.
  function _mdBfSteamBody() {
    var items = (((_md.data.bfOverview || {}).steam) || []).filter(function (x) { return Math.abs(+x.pp || 0) <= 25; });   // 13.08.2026 (Lucas): >25pp = Platzhalter-/Opening-Artefakt (z.B. -73pp) raus
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
      // 30.08.2026: die Zahl rechts war eine nackte „1" — in jeder anderen Kachel steht dort
      // €/pp/%. Sie zählt harte Abweichungen, also gehört das auch dran.
      return _mdWarnRow(_bfTeams(r.m) + _mdBfLive(r.m),
        esc(String(t.k || 'Abweichung')) + (t.mkt ? ' · ' + esc(String(t.mkt).slice(0, 26)) : ''),
        r.nHard + '<span style="font-size:9px;font-weight:700;color:var(--mi3);margin-left:3px">' +
        (r.nHard === 1 ? 'Bruch' : 'Brüche') + '</span>');
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
    if (!items.length) return empty('Kein auffälliger Zufluss gerade (großes Geld ≥ €10K oder marktdominant) — sammelt (2 Snapshots nötig).');
    var mx = items.reduce(function (a, x) { return Math.max(a, +x.deltaEur || 0); }, 1);
    return items.map(function (x) {
      var _thinB = x.thin ? ' <span title="Zufluss macht ' + (x.sharePct != null ? x.sharePct + '% ' : '') + 'des gesamten Marktgeldes aus — dünner Markt, oft nicht beim Buchmacher spielbar. Anomalie/Fix-Kandidat." style="font-size:9px;font-weight:800;color:#f2c14e;border:1px solid rgba(234,185,56,.5);border-radius:4px;padding:0 4px">🔍 dünner Markt</span>' : '';
      return rowEl(_bfTeams(x) + _mdBfLiveById(x.matchId) + _thinB, '+' + eur(x.deltaEur), A.good,
        '→ ' + esc(x.sideName || '') + _bfReactiveChip(x.sideName, !!_mdBfLiveById(x.matchId)) + _mdDirBadge(x.dir) + ' · jetzt ' + eur(x.nowEur) + (x.odd != null ? ' @' + (+x.odd).toFixed(2) : ''),
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
  // 29.08.2026 (Lucas-Checkup, „B"): Betfair-Steam wirft seit 13.08. alles ueber 25pp als
  // Opening-/Platzhalter-Artefakt raus, die Pinnacle-Kachel hatte diesen Deckel nie. Deshalb
  // standen dort +48,9pp auf @6.05 und +44,3pp auf @4.55 ganz oben — bei @6.05 sind 16,5%
  // implizit, ein +48,9pp-Move kaeme also aus minus 32%. Unmoeglich. Schlimmer als die zwei
  // falschen Zeilen war die Skalierung: shMax richtet sich nach dem groessten Wert, also
  // schrumpften die echten 12-14pp-Moves darunter zu Stummeln. Median ueber alle 273 Picks: 3,9pp.
  var SHARP_MAX_PP = 25;
  function allSharp() {
    var rows = [];
    allFixtures().forEach(function (f) {
      if (!_fxKommend(f)) return;   // s. _fxKommend — ein Move auf ein gespieltes Spiel ist Historie
      (f.picks || []).forEach(function (p) {
        if (p.source !== 'steam' || p.steamMovePP == null) return;
        var mv = Math.abs(+p.steamMovePP || 0);
        if (mv > SHARP_MAX_PP) return;
        rows.push({ f: f, p: p, mv: mv });
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
    // Nicht die Uhr, sondern die ÄLTESTE Quelle: die Seite ist nur so frisch wie ihr trägster
    // Feed. Steht dort „Cards vor 5,9 h", weiß man sofort, dass die Card-Kacheln von heute Nacht
    // sind, während Betfair daneben 12 Minuten alt ist.
    var q = _mdQuellenAlter(), a = q.length ? q[0] : null;
    var col = !a ? 'var(--mi3)' : a.min > 180 ? '#f2a6a6' : a.min > 60 ? 'var(--gold)' : 'var(--mi3)';
    var titel = q.map(function (x) { return x.n + ': ' + _ageTxt(x.min); }).join(' · ');
    var stand = a
      ? '<span title="' + esc(titel) + '">älteste Quelle <b style="color:' + col + '">' +
        esc(a.n) + ' vor ' + _ageTxt(a.min) + '</b></span>'
      : 'Stand <b>' + _clock() + '</b>';
    return '<div class="md-top md-rise">' +
      '<div><h1 class="md-h1">Übersicht</h1>' +
      '<p class="md-sub">Die stärksten Signale aller Engines — kuratiert, auf einen Blick.</p></div>' +
      '<div class="md-asof" id="md-asof"><span class="md-dot" style="background:' + col + '"></span>' + stand + '</div></div>';
  }

  // Der Kopf wird EINMAL gerendert, der Poly-LIVE-Cache kommt aber erst spaeter (lazy, s.
  // _mdFillLive). Ohne dieses Nachziehen bliebe die aelteste Quelle auf dem Stand VOR dem
  // Laden stehen — also genau wieder zu optimistisch.
  function _mdRefreshAsof() {
    var el = document.getElementById('md-asof'); if (!el) return;
    var q = _mdQuellenAlter(), a = q.length ? q[0] : null; if (!a) return;
    var col = a.min > 180 ? '#f2a6a6' : a.min > 60 ? 'var(--gold)' : 'var(--mi3)';
    el.innerHTML = '<span class="md-dot" style="background:' + col + '"></span>' +
      '<span title="' + esc(q.map(function (x) { return x.n + ': ' + _ageTxt(x.min); }).join(' · ')) + '">' +
      'älteste Quelle <b style="color:' + col + '">' + esc(a.n) + ' vor ' + _ageTxt(a.min) + '</b></span>';
  }

  function kpi(val, label, hint, color) {
    return '<div class="md-kpi" style="--kc:' + color + ';">' +
      '<div class="md-kpi-v">' + val + '</div>' +
      '<div class="md-kpi-l">' + label + '</div>' +
      (hint ? '<div class="md-kpi-h">' + hint + '</div>' : '') + '</div>';
  }
  function _kpis() {
    var d = _md.data.pulse || {}, pl = d.poly || {};
    var bets = betPicks();
    var mmRows = (_md.data.moneyMap && _md.data.moneyMap.rows) || [];
    var kon = mmRows.filter(function (r) { return r.verdict === 'konsens'; }).length;
    var mmAnch = mmRows.filter(function (r) { return r.pinn; }).length;   // 13.08.2026 (Lucas): echter Pinnacle-Anker vorhanden?
    // 03.09.2026 (Lucas: „Was fehlt dann noch von Poly bei dem Betis - Real Madrid Beispiel?"):
    // die Kachel schrieb „7 Konsens · BF × Poly × Pinn" — eine Behauptung ueber DREI Buecher fuer
    // ALLE sieben Zeilen. Bei Betis–Real Madrid bestand die dritte Quelle aus $74 Umsatz und
    // einem Preis, der 21pp neben dem Anker lag; die Zeile selbst schreibt das korrekt mit
    // (`polyGeld:false`, `nSources:2`), nur die Kachel las es nie. Jetzt zaehlt sie, wie viele
    // Zeilen wirklich alle drei tragen — und benennt den Rest, statt ihn mitzuzaehlen.
    var drei = mmRows.filter(function (r) { return (r.nSources || 0) >= 3; }).length;
    var ohnePoly = mmRows.filter(function (r) { return r.polyGeld === false; }).length;
    var st = ((_md.data.bfOverview && _md.data.bfOverview.steam) || []).filter(function (x) { return Math.abs(+x.pp || 0) <= 25; });   // Artefakt-Moves raus
    var fl = (_md.data.bfOverview && _md.data.bfOverview.flow) || [];
    var bigPp = st.reduce(function (m, x) { var q = +x.pp || 0; return Math.abs(q) > Math.abs(m) ? q : m; }, 0);
    var topConv = bets.length ? (bets[0].conv || 0) : 0;
    var K = function (val, top, label, hint, color, view) {
      return '<button class="md-kpi" style="--kc:' + color + '" onclick="showView(\'' + view + '\')">' +
        '<div class="md-kpi-top">' + top + '</div><div class="md-kpi-v">' + val + '</div>' +
        '<div class="md-kpi-l">' + label + '</div>' + (hint ? '<div class="md-kpi-h">' + hint + '</div>' : '') + '</button>';
    };
    return '<div class="md-kpis md-rise">' +
      K(bets.length, '🎯 BET-Cards', bets.length ? 'Top ' + topConv + '/10' : 'keine offen', bets.length ? 'Conviction-Setz-Kandidaten' : 'Conviction ≥ Schwelle · sammelt', A.blue, 'national-cards') +
      K((pl.openN || 0), '🔥 Heiße Spiele Poly', 'Top-Plays offen', 'Heute Spielenswert ' + (pl.hitPct == null ? '—' : Math.round(pl.hitPct) + '%') + (pl.n ? ' (' + pl.n + ')' : ''), A.poly, 'polywallets') +
      K(st.length, '💷 Betfair heiß', st.length ? 'Märkte mit Zug' : 'ruhig', st.length ? 'größter ' + (bigPp > 0 ? '+' : '') + bigPp.toFixed(1) + 'pp' + (fl.length ? ' · +' + fl.length + ' Zufluss' : '') : '—', A.bf, 'betfair') +
      K(mmRows.length, '🔗 Money Map', mmRows.length ? 'Spiele im Bild' : 'ruhig',
        kon + ' Konsens · ' + drei + '× alle drei' + (ohnePoly ? ' · ' + ohnePoly + ' ohne Poly-Geld' : '')
          + (mmAnch ? '' : ' · kein Anker'), A.flow, 'moneymap') +
      '</div>';
  }
  
  // 30.08.2026: hier standen _SIDE/_SRC/consensusRows/agreeBar/_legend/_mdHero — der
  // Triple-Konsens-Hero. Entfernt, Begründung oben im CSS-Block. `pick.consensus` schreibt
  // generate_wm_picks weiter mit (additiv, try/except) und liegt damit bereit, falls die Frage
  // später doch gemessen statt eingeschätzt werden soll — gezeigt wird es nur nicht mehr.

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
  // 15.08.2026 (Lucas): live Tore-Unter = reaktiv (verkürzt sich mit der Uhr, ein Tor kippt es -> Lay-Verdacht).
  function _bfReactiveUnder(sideName, live) { if (!live) return false; var s = String(sideName || ''); return /under|unter/i.test(s) && /goal|tore/i.test(s); }
  function _bfReactiveChip(sideName, live) { return _bfReactiveUnder(sideName, live) ? ' <span class="md-badge" style="background:rgba(229,83,75,.14);color:' + A.red + '" title="Live-Unter läuft mit der Uhr runter — ein Tor kippt es. Reaktives Geld, Lay-Verdacht (Over ist die scharfe Seite).">⚠ reaktiv</span>' : ''; }
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
  function _mdPlayInflow(r) {
    try {
      if (typeof _pwInflow === 'function' && typeof _pwCache !== 'undefined' && _pwCache && _pwCache.broadHist)
        return +_pwInflow(r.key, _pwCache.broadHist) || 0;
    } catch (e) {}
    return 0;
  }
  function _mdSigCell(label, val, col, barPct, sub) {
    return '<div class="md-sig-c"><div class="md-sig-h"><span class="md-sig-l">' + label + '</span>'
      + '<span class="md-sig-v" style="color:' + col + '">' + val + '</span></div>'
      + '<div class="md-sig-bar"><i style="width:' + clamp(barPct, 0, 100) + '%;background:' + col + '"></i></div>'
      + '<div class="md-sig-sub">' + sub + '</div></div>';
  }
  function _mdSigMuted(label, sub) {
    return '<div class="md-sig-c md-sig-off"><div class="md-sig-h"><span class="md-sig-l">' + label + '</span>'
      + '<span class="md-sig-v" style="color:var(--mi3)">–</span></div>'
      + '<div class="md-sig-bar"></div><div class="md-sig-sub">' + sub + '</div></div>';
  }
  function _mdSigStrip(r, maxInf) {
    var mp = Math.round((+r.moneyPct || 0) * 100), vol = +r.vol || 0, sh = r.sharp, inf = _mdPlayInflow(r);
    var c1 = _mdSigCell('Geld', mp + '%', A.money, mp, vol ? usd(vol) + ' Vol' : '—');
    var c2 = (sh && sh.n)
      // 29.08.2026 (Lucas-Checkup): stand als „Wallets 57% · 152 von 266" da und las sich als
      // „152 von 266 Wallets stehen auf dieser Seite". Ist es nicht: sh.n/sh.wins sind die
      // LEBENSLANGE Bilanz der scharfen Wallets auf dieser Seite (Summe ihrer abgerechneten
      // Plays). Verraten hat es sich selbst — zwei voellig verschiedene Japan-Spiele zeigten
      // exakt „152 von 266", weil dieselbe Wallet-Kohorte dahinter stand. Die Zahl der Wallets
      // ist sh.count und stand nirgends. Jetzt beides, richtig benannt.
      ? _mdSigCell('Wallet-Bilanz', Math.round(sh.hit * 100) + '%', A.blue, Math.round(sh.hit * 100),
          (sh.count ? sh.count + (sh.count === 1 ? ' Wallet' : ' Wallets') + ' · ' : '') + sh.wins + '/' + sh.n + ' lifetime')
      : _mdSigMuted('Wallet-Bilanz', 'keine');
    var c3 = (inf > 0)
      ? _mdSigCell('Zufluss', '+' + usd(inf), A.flow, maxInf ? (inf / maxInf * 100) : 0, 'seit Lauf')
      : _mdSigMuted('Zufluss', '—');
    // 30.08.2026 (Lucas: „heute spielenswert ist mehr polymarket getrieben richtig?") — ja, und
    // genau das war das Problem an dieser Zeile: Geld · Wallet-Bilanz · Zufluss lesen ALLE
    // DIESELBE Quelle. Drei Blickwinkel auf Polymarket sahen aus wie drei Belege. Die einzige
    // wirklich fremde Stimme im Scorer ist Betfair — und sie ist die einzige Untergruppe im
    // Papier-Depot mit positivem ROI (n=57, +6,5%; der Mix bf+money +5,1%). Sie stand nirgends.
    //
    // Bewusst KEIN fester Platz wie in „Mehrfach gedeckt": dort sind alle Ströme grundsätzlich
    // möglich, hier gibt es für Tennis/Esports gar keinen Betfair-Markt. Ein leerer Slot auf
    // 89% der Zeilen wäre kein fehlendes Signal, sondern eine fehlende Fläche — also erscheint
    // die Zelle nur, wenn es wirklich etwas zu vergleichen gibt.
    //
    // Und sie zeigt BEIDE Richtungen. Liegt das Betfair-Geld auf der Gegenseite, ist das eine
    // Warnung, keine Leerstelle — der Scorer rechnet das ohnehin (r.bf.agree), verschwiegen hat
    // es nur die Anzeige. Farbe entscheidet nichts: „bestätigt" bzw. „dagegen" steht als Wort da.
    var b = r.bf, c4 = '';
    if (b && b.pct != null) {
      c4 = b.agree
        ? _mdSigCell('Betfair', b.pct + '%', A.bf, b.pct, 'bestätigt' + (b.eur ? ' · ' + eur(b.eur) : ''))
        // Balkenlänge = Rückhalt. Im Gegenfall gibt es keinen — die 64% gehören der ANDEREN
        // Seite. Ein gefüllter Balken hätte genau das Gegenteil erzählt, deshalb bleibt die
        // Spur leer und die Zahl trägt die Aussage.
        : _mdSigCell('Betfair', b.pct + '%', A.gold, 0,
            'dagegen — Geld auf ' + esc(short(String(b.name || 'Gegenseite'))));
    }
    return '<div class="md-sig">' + c1 + c2 + c3 + c4 + '</div>';
  }
  function _mdPlayRow(r, maxInf) {
    var vcol = r.verdict === 'BET' ? A.good : A.gold, conv = +r.conv || 0;
    var badge = '<span style="display:inline-block;padding:1px 7px;border-radius:10px;border:1px solid ' + vcol + ';color:' + vcol + ';font-weight:800;font-size:10px;margin-right:6px">' + r.verdict + '</span>';
    var icon = (typeof _pwSportIcon === 'function') ? _pwSportIcon(r.league) + ' ' : '';
    var live = (r.htk != null && r.htk < 0) ? _MD_LIVE : '';
    var htk = (r.htk == null || r.htk < 0) ? '' : (r.htk < 1 ? '<1h' : Math.round(r.htk) + 'h');
    var main = badge + icon + _mdPolyLink(r.key, esc(String(r.match).slice(0, 38)) + ' <span style="color:var(--mi3)">→</span> <b style="color:#4cc2ff">' + esc(r.side) + '</b>') + live
      + (htk ? ' <span style="font-size:10px;color:var(--mi3)">· Anpfiff ' + htk + '</span>' : '');
    return '<div class="md-r md-r-top">' + _mdRing(conv, _mdConvCol(conv))
      + '<div class="md-r-main"><div class="md-r-t">' + main + '</div>' + _mdSigStrip(r, maxInf) + '</div></div>';
  }
  function _mdPlaysHtml(plays) {
    var maxInf = (plays && plays.length) ? plays.reduce(function (a, p) { return Math.max(a, _mdPlayInflow(p)); }, 1) : 1;
    var body = (plays && plays.length)
      ? plays.map(function (p) { return _mdPlayRow(p, maxInf); }).join('')
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
  // 23.08.2026 (Lucas: „Fußball hat dieses komische andere Icon"): früher grobe Exakt-Map + Fallback 🎯
  // für Serie A/La Liga/… . Jetzt über den robusten _pwSportCategory (kennt alle Liga-Muster UND den
  // gestempelten Sport aus dem Capture). Fallbacks nur, falls poly-wallets.js (noch) nicht geladen ist.
  function _mdSportIco(lg, sp) {
    if (typeof _pwSportCategory === 'function' && typeof _PW_CAT_ICON !== 'undefined')
      return _PW_CAT_ICON[_pwSportCategory(lg, sp)] || '🎯';
    if (typeof _pwSportIcon === 'function') return _pwSportIcon(lg);
    var k = String(lg || '').toUpperCase(); return _MD_SPORT_ICO[k] || (k.indexOf('SOCCER') === 0 ? '⚽' : '🎯');
  }
  // 💰 Volumen über Norm (aus dem Großes-Geld-Tab): welche Märkte ziehen verhältnismäßig — Gesamt-$ ÷
  // Median gleicher Sportart×Phase. ×1.6 auffällig, ×2.6 stark. Ersetzt Whale-Watch (07.08.2026, Lucas).
  function _mdOverNormBody(rows) {
    if (!rows || !rows.length) return empty('Kein Markt auffällig über seiner Norm — alles im üblichen Rahmen für Sportart & Phase.');
    var mx = rows.reduce(function (a, r) { return Math.max(a, +r.ratio || 0); }, 1);
    return rows.map(function (r) {
      var col = r.ratio >= 2.6 ? A.red : A.gold;
      var label = _mdSportIco(r.league, r.sport) + ' ' + (r.url
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
        // 01.09.2026: hier stand „Conv≥7" fest getippt, die Schwelle steht aber seit dem 29.08.
        // auf 6. Ein Leertext, der eine falsche Schwelle nennt, ist eine kleine Lüge über das
        // eigene System — jetzt aus der Konstante gezogen. „Bewiesen" heißt seit dem Regler
        // ausdrücklich: volle Wilson-Untergrenze, nicht bloß vielversprechend.
        : empty('Kein Top-Play über der Schwelle — Conv≥'
                + (typeof PW_PUBLIC_MIN_CONV === 'number' ? PW_PUBLIC_MIN_CONV : 6)
                + ', bewiesene Wallet (n≥8, ≥55%, Beleg voll), Geld-Mehrheit ≥60%. Normalfall.'));
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
  // 19.08.2026 (Lucas: „wenn Halbzeit vorbei brauch ich's nicht mehr, blockiert sonst neue Spiele"):
  // die HT-Kachel zeigt NUR Erste-Halbzeit-Maerkte (HT 1X2, HT O/U 0.5/1.5). Laeuft schon die 2. HZ,
  // ist das HT-Geld entschieden = Rauschen und klaut Slots. Raus, sobald die 1. HZ vorbei ist. Die
  // Halbzeitpause selbst (is_ht) bleibt sichtbar — Peak-Interesse, HT gerade entschieden.
  function _mdHtOver(m) {
    var li = m.liveInfo || {};
    if (li.is_ht) return false;                        // Halbzeitpause -> noch zeigen
    var t = li.time;
    return (typeof t === 'number') && t >= 46;         // 2. Halbzeit -> HT-Markt durch, raus
  }
  function _mdBfHt() {
    var ms = (_md.data.betfair && _md.data.betfair.matches) || [], rows = [];
    ms.forEach(function (m) {
      if (_mdBfStale(m)) return;   // durchgelaufene Spiele nicht mehr zeigen
      if (_mdHtOver(m)) return;    // 1. HZ vorbei -> HT-Markt entschieden, Slot fuer laufende Spiele frei
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
      return _mdDonutRow(_bfTeams(m) + _mdBfLive(m), (_HT_MK[b.name] || b.name) + ' \u2192 ' + esc(b.lead.name) + _bfReactiveChip(b.lead.name, !!_mdBfLive(m)) + od + _mdDirBadge(_mdDirOf(m.matchId, b.name, b.lead.name)), eur(b.vol), A.bf, pct, A.bf);
    }).join('') + _ageStr(_md.data.betfair);
  }

  // ── ⚡ Polymarket LIVE (11.08.2026, Lucas): Vollbreiten-Element unter den Poly-Kacheln. Zwei Listen —
  //    Top-5 Live-Whales (wer JETZT groß reingeht, scharfe zuerst) + Top-5 Live-Zufluss (wo seit dem
  //    letzten Scan das meiste frische Geld reinkam). Daten via _pwLiveTopWhales/_pwLiveTopInflow.
  function _mdLiveWhaleRow(w) {
    var live = _MD_LIVE;
    var tag = w.sharpLive ? '<span class="md-lv-tag" style="color:' + A.good + ';border-color:rgba(46,160,67,.55)">🔥 scharf live</span>'
      : w.sharp ? '<span class="md-lv-tag" style="color:' + A.good + ';border-color:rgba(46,160,67,.4)">🔥 scharf</span>'
      : w.isNew ? '<span class="md-lv-tag" style="color:' + A.red + ';border-color:rgba(229,83,75,.5)">🔴 live rein</span>' : '';
    var rec = w.sc ? ' <span style="color:' + (w.sc.avgClv > 0 ? A.good : A.red) + ';font-weight:700">' + (w.sc.avgClv >= 0 ? '+' : '') + w.sc.avgClv.toFixed(1) + 'pp</span> <span style="color:var(--mi3)">' + Math.round(w.sc.hit * 100) + '%·n' + w.sc.n + '</span>' : '';
    var avg = (w.price != null) ? ' @' + w.price + '¢' : ((w.avgPrice != null && isFinite(w.avgPrice)) ? ' @' + Math.round(w.avgPrice * 100) + '¢' : '');
    var main = _mdSportIco(w.league, w.sport) + ' ' + _mdPolyLink(w.key, '<b style="color:#4cc2ff">' + esc(String(w.side).slice(0, 22)) + '</b>') + live;
    var sub = esc(String(w.label).replace(/<[^>]*>/g, '').slice(0, 40)) + rec;
    return rowEl(main, usd(w.usd) + avg, A.poly, sub, tag ? '<div class="md-lv-tags">' + tag + '</div>' : '');
  }
  function _mdLiveInflowRow(r, mx) {
    var side = (r.favPct != null && r.favPct >= 55) ? ('Geld auf ' + esc(String(r.favName).slice(0, 18)) + ' ' + r.favPct + '%' + (r.favPrice != null ? ' · ' + r.favPrice + '¢' : '')) : ('~offen · ' + (r.favPct != null ? r.favPct + '%' : ''));
    var main = _mdSportIco(r.league, r.sport) + ' ' + _mdPolyLink(r.key, esc(String(r.label).replace(/<[^>]*>/g, '').slice(0, 34))) + _MD_LIVE;
    var sub = side + ' · ' + usd(r.totalUsd) + ' gesamt';
    return rowEl(main, '+' + usd(r.inflow), A.flow, sub, meter(mx ? (r.inflow / mx * 100) : 0, A.flow));
  }
  function _mdLiveHtml(whales, inflow) {
    var head = '<div class="md-tile-h"><span class="md-tile-ic" style="--tb:rgba(248,81,73,.14);--tbr:rgba(248,81,73,.4);">⚡</span>' +
      '<span class="md-tile-t">Polymarket LIVE</span>' +
      '<span style="font-size:10px;color:var(--mi3);font-weight:600;margin-left:8px">laufende Spiele · alle ~5 Min</span>' +
      '<button class="md-more" style="--ta:' + A.poly + ';" onclick="showView(\'polywallets\')">LIVE →</button></div>';
    if ((!whales || !whales.length) && (!inflow || !inflow.length)) {
      var sm = (typeof _pwLiveStaleMin === 'function') ? _pwLiveStaleMin() : null;
      var msg = (sm != null && sm > 20)
        ? 'Kein frischer Live-Stand — letzte Erfassung vor ' + (sm >= 120 ? Math.round(sm / 60) + ' h' : sm + ' Min') + '. Die erfassten Spiele sind durch; der Live-Scan (Mac-Runner) lief zuletzt nicht.'
        : 'Gerade keine laufenden Märkte mit nennenswertem Geld — sobald live Volumen reinkommt (Esport/Tennis/…), steht hier was.';
      return '<section class="md-tile md-rise md-wide" style="animation-delay:190ms;">' + head + empty(msg) + '</section>';
    }
    var mxIn = (inflow && inflow.length) ? inflow.reduce(function (a, r) { return Math.max(a, +r.inflow || 0); }, 1) : 1;
    var colW = (whales && whales.length) ? whales.map(_mdLiveWhaleRow).join('') : empty('Keine großen Live-Whale-Einstiege gerade.');
    var colI = (inflow && inflow.length) ? inflow.map(function (r) { return _mdLiveInflowRow(r, mxIn); }).join('') : empty('Kein frischer Live-Zufluss messbar (braucht ≥2 Scans).');
    var sub = function (icon, t) { return '<div class="md-lv-sub"><span>' + icon + '</span>' + t + '</div>'; };
    var body = '<div class="md-lv-cols">' +
      '<div class="md-lv-col">' + sub('🐋', 'Top-5 Live-Whales') + colW + '</div>' +
      '<div class="md-lv-col">' + sub('💨', 'Top-5 Live-Zufluss') + colI + '</div>' +
      '</div>';
    return '<section class="md-tile md-rise md-wide" style="animation-delay:190ms;">' + head + body + '</section>';
  }
  function _mdLiveWidePlaceholder() {
    return '<section class="md-tile md-rise md-wide" style="animation-delay:190ms;">' +
      '<div class="md-tile-h"><span class="md-tile-ic" style="--tb:rgba(248,81,73,.14);--tbr:rgba(248,81,73,.4);">⚡</span>' +
      '<span class="md-tile-t">Polymarket LIVE</span></div>' + empty('lädt …') + '</section>';
  }
  function _mdFillLive() {
    var box = document.getElementById('md-cell-live'); if (!box) return;
    if (typeof _pwEnsurePlaysData !== 'function' || typeof _pwLiveTopWhales !== 'function') return;   // Skelett bleibt
    _pwEnsurePlaysData(function () {
      var b = document.getElementById('md-cell-live'); if (!b) return;
      var whales = [], inflow = [];
      try { whales = _pwLiveTopWhales(5) || []; } catch (e) { whales = []; }
      try { inflow = _pwLiveTopInflow(5) || []; } catch (e) { inflow = []; }
      b.innerHTML = _mdLiveHtml(whales, inflow);
      try { _mdRefreshAsof(); } catch (e) { /* Kopf bleibt, wie er war */ }
    });
  }

  // ── 🔗 Money Map (11.08.2026, Lucas): Vollbreiten-Streifen — Top-10-Fußballspiele mit den
  //    Betfair- + Poly-Geld-Bubbles + Pinnacle-Linie. Rendert die IDENTISCHEN Cards wie der Tab
  //    (window._mmCardHtml aus money-map.js). Reine Anzeige aus money_map.json.
  function _mdMoneyMapWide() {
    var mm = _md.data.moneyMap, rows = (mm && mm.rows) || [];
    rows = rows.filter(function (r) { return r && r.verdict && r.verdict !== 'no_anchor' && (r.betfair || r.poly); }).slice(0, 10);
    var head = '<div class="md-tile-h"><span class="md-tile-ic" style="--tb:rgba(234,185,56,.14);--tbr:rgba(234,185,56,.32);">🔗</span>' +
      '<span class="md-tile-t">Money Map</span>' +
      '<button class="md-more" style="--ta:' + A.gold + ';" onclick="showView(\'moneymap\')">Map →</button></div>';
    var body;
    if (!rows.length) {
      body = empty(mm ? 'Gerade kein Fußballspiel mit genug Geld auf Betfair oder Poly.' : 'Füllt sich beim nächsten Betfair-Lauf: Betfair- + Poly-Geld je Spiel, Pinnacle als scharfe Linie.');
    } else if (typeof window._mmCardHtml === 'function') {
      if (typeof window._mmEnsureStyle === 'function') window._mmEnsureStyle();
      body = '<div class="md-mm-grid">' + rows.map(function (r) { try { return window._mmCardHtml(r); } catch (e) { return ''; } }).join('') + '</div>';
    } else {
      body = empty('Money-Map-Ansicht lädt …');
    }
    return '<section class="md-tile md-rise md-wide" style="animation-delay:120ms;">' + head + body + '</section>';
  }

  function _mdRender() {
    var p = document.getElementById('mainDashPanel');
    if (!p) return;
    _mdStyle();
    p.classList.add('mdash');
    if (!_md.data) { _mdLoad(); return; }
    var teamsOf = function (f) { return fl(fxFlag(f)) + esc(fxTeam(f, 'home')) + ' <span style="color:var(--mi3);font-weight:400">v</span> ' + esc(fxTeam(f, 'away')); };

    // Cards — Conviction-Meter
    var c = bestCards();
    var cardsBody = c.length ? c.map(function (x) {
      var f = x.f, p2 = x.p, conv = +x.conv || 0;
      // 30.08.2026 (Lucas-Checkup): hier stand nackt „-3pp" an einer Conviction-8-BET-Card.
      // Das liest sich wie ein Widerspruch, ist aber keiner: ein Steam-Folger kauft bewusst NACH
      // der Bewegung — die Quote ist dann schlechter als die eigene Fair-Linie, der Grund ist
      // das gefolgte Geld, nicht der Preis. Also wird der Grund dazugeschrieben statt die Zahl
      // zu verstecken; ein negativer Edge OHNE Steam bleibt weiter nackt sichtbar (dort wäre er
      // wirklich ein Widerspruch).
      var _st = (p2.source === 'steam');
      var _edge = (p2.edgePP != null) ? ' · ' + (Math.round(+p2.edgePP) > 0 ? '+' : '') + Math.round(+p2.edgePP) + 'pp' : '';
      if (_st && p2.edgePP != null && +p2.edgePP < 0) {
        _edge += ' <span title="Steam-Folger: wir kaufen nach der Bewegung, deshalb liegt die Quote unter der eigenen Fair-Linie. Der Grund ist das Geld, nicht der Preis." style="color:var(--mi3)">(Steam-Folger'
          + (p2.lateEntry ? ', spät' : '') + ')</span>';
      }
      var sub = esc(short(p2.market)) + (fxLeague(f) ? ' · ' + esc(String(fxLeague(f)).slice(0, 20)) : '') + _edge;
      return conv ? _mdRingRow(teamsOf(f), sub, conv, _mdConvCol(conv))
        : rowEl(teamsOf(f), (p2.odds != null ? '@' + (+p2.odds).toFixed(2) : ''), A.good, sub, '');
    }).join('') + _ageStr(_md.data.liga) : empty('Keine BET-Cards gerade.');

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
    }).join('') + _ageStr(_md.data.ligaStreaks) : empty('Keine langen Serien.');

    // Betfair — Anteilsbalken
    var bf = bestBetfair();
    var bfBody = bf.length ? bf.map(function (x) {
      var m = x.m, b = x.b, pct = Math.round(b.share * 100);
      // 05.08.2026 (Lucas): Führungsquote dazu, dann ist die Kachel immer eindeutig (@1.74 vs @1.06).
      var od = (b.lead && b.lead.odd != null && +b.lead.odd > 1) ? ' <span style="color:var(--mi3)">@' + (+b.lead.odd).toFixed(2) + '</span>' : '';
      return _mdDonutRow(teamsOf(m) + _mdBfLive(m), esc(short(b.name)) + ' → ' + esc(b.lead.name) + _bfReactiveChip(b.lead.name, !!_mdBfLive(m)) + od + _mdDirBadge(_mdDirOf(m.matchId, b.name, b.lead.name)), eur(b.vol), A.bf, pct, A.bf);
    }).join('') : empty('Kein großes Betfair-Geld.');
    bfBody += _ageStr(_md.data.betfair);

    // Whales — USD-Balken (relativ zum größten)
    var wh = bestWhales();
    var whMax = wh.length ? wh[0].usd : 1;
    var whBody = wh.length ? wh.map(function (w) {
      var live = (w.hrs != null && w.hrs < 0) ? _MD_LIVE : '';
      var hrs = (w.hrs != null && w.hrs >= 0) ? (w.hrs < 1 ? '<1h' : Math.round(w.hrs) + 'h') : '';
      // 16.08.2026 (Lucas): Spielkontext statt nur "Over"/"Under" — Spiel aus dem Basis-Event aufloesen.
      var _gm = (typeof _pwCache !== 'undefined' && _pwCache) ? ((_pwCache.broadLiveNow && _pwCache.broadLiveNow[w.key]) || (_pwCache.broadLive && _pwCache.broadLive[w.key])) : null;
      var _gn = (_gm && typeof _pwPlayLabel === 'function') ? _pwPlayLabel(w.key, Object.keys(_gm.shares || {}).map(function (s) { return { s: s }; })) : '';
      return rowEl(fl(_flagFrom(w.country, w.league, w.league)) + _mdPolyLink(w.key, esc((_gn || w.side || '?').slice(0, 34))) + live, usd(w.usd), A.poly,
        '\u2192 ' + esc(String(w.side || '?')) + ' \u00b7 ' + esc(String(w.league || '')) + (hrs ? ' \u00b7 in ' + hrs : ''), meter(whMax ? (w.usd / whMax) * 100 : 0, A.poly));
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
    }).join('') + _ageStr(_md.data.liga) : empty('Keine Steam-Moves.');

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
      // Reihe 3.5 — Money Map (Vollbreite): Betfair + Poly + Pinnacle je Fußballspiel
      _mdMoneyMapWide() +
      // Reihe 4 — Poly
      tile('🐋', 'Poly Whale-Bets', A.poly, 'rgba(25,158,112,.14)', 'rgba(25,158,112,.32)', 'polywallets', 'Wallets', whBody, 160) +
      '<div id="md-cell-top" class="md-cell">' + tile('🎯', 'Top-Play', A.good, 'rgba(46,160,67,.14)', 'rgba(46,160,67,.32)', 'polywallets', 'Wallets', empty('lädt …'), 170) + '</div>' +
      '<div id="md-cell-whale" class="md-cell">' + tile('💰', 'Volumen über Norm', A.poly, 'rgba(25,158,112,.14)', 'rgba(25,158,112,.32)', 'polywallets', 'Wallets', empty('lädt …'), 180) + '</div>' +
      // Reihe 4.5 — Polymarket LIVE (Vollbreite): laufende Wallets + frischer Zufluss
      '<div id="md-cell-live" class="md-cell">' + _mdLiveWidePlaceholder() + '</div>' +
      '</div>';

    p.innerHTML = _head() + _mdPulse() + _mdSpielbar() + _mdSignalBoard() + _mdNobetBoard() + _kpis() + grid +
      '<div class="md-foot">Kuratierter Überblick · tippe „alle →" für den vollen Bereich</div>';
    _mdFillPlays();
    _mdFillPubPreview();
    _mdFillLive();
    _mdFillJetzt();
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
    var mmRows = (_md.data.moneyMap && _md.data.moneyMap.rows) || [];
    var bf = d.betfair, pl = d.poly, ml = d.moneymap;
    if (!d.n && !(bf && bf.n) && !(pl && pl.n) && !mmRows.length) return '<section class="md-pulse md-rise"><div class="md-pulse-h">📈 Puls</div>' +
      '<div class="md-pulse-l" style="color:var(--mi2)">Noch keine abgerechneten Picks/Plays — füllt sich, sobald die ersten resolven.</div></section>';
    var col0 = function (v) { return v == null ? 'var(--mi3)' : v > 0 ? A.good : v < 0 ? A.red : 'var(--mi2)'; };
    var sub = function (v, l, c) { return '<span class="mpc-sub"><b style="color:' + (c || 'var(--mi)') + '">' + v + '</b><i>' + l + '</i></span>'; };
    var meter = function (x, c) { x = Math.max(0, Math.min(100, +x || 0)); return '<div class="mpc-meter"><span></span><i style="width:' + x + '%;background:' + c + '"></i></div>'; };
    var cards = [];
    if (d.n) {
      var clv = d.avgClvPP, clvTxt = clv == null ? '—' : (clv > 0 ? '+' : '') + (+clv).toFixed(1) + 'pp', beat = d.pctBeatClose;
      cards.push('<button class="mpc" style="--ac:' + A.blue + '" onclick="showView(\'national-cards\')" title="→ Betting-Cards">' +
        // 03.09.2026 (Lucas-Checkup): hier stand nur `n30` — daneben aber „78% Treffer 21–6",
        // also eine Quote auf 27. `n` ist die Fenstergroesse (alle abgerechneten Picks),
        // `nGraded` = wins+losses; Picks, deren Ergebnis weder WIN noch LOSS ist, fallen aus der
        // Quote und blieben trotzdem im angezeigten n. Jetzt traegt jede Zahl ihre eigene Basis.
        '<span class="mpc-h">🎯 Cards<b>n' + d.n +
          (d.nGraded != null && d.nGraded !== d.n ? ' · ' + d.nGraded + ' gew.' : '') + '</b></span>' +
        '<div class="mpc-big" style="color:' + col0(clv) + '">' + clvTxt + '</div>' +
        '<div class="mpc-cap"' + (d.nClv != null && d.nClv !== d.n ? ' title="Ø über ' + d.nClv + ' Picks mit CLV"' : '') +
          '>Ø CLV' + (d.nClv != null && d.nClv !== d.n ? ' · n' + d.nClv : '') + '</div>' +
        _spark(d.series) +
        '<div class="mpc-subs">' + sub(beat == null ? '—' : Math.round(beat) + '%', 'schlägt Close', beat == null ? 'var(--mi3)' : beat >= 50 ? A.good : beat >= 33 ? A.gold : A.red) +
        sub(d.winPct == null ? '—' : Math.round(d.winPct) + '%', 'Treffer ' + (d.wins || 0) + '–' + (d.losses || 0), 'var(--mi)') + '</div></button>');
    }
    if (bf && bf.n) {
      cards.push('<button class="mpc" style="--ac:' + A.bf + '" onclick="showView(\'betfair\')" title="→ Betfair Radar">' +
        '<span class="mpc-h">💷 Betfair<b>n' + bf.n + '</b></span>' +
        '<div class="mpc-big">' + (bf.hitPct == null ? '—' : (+bf.hitPct).toFixed(1) + '%') + '</div><div class="mpc-cap">Treffer · Geld-Seite</div>' +
        meter(bf.hitPct, A.good) +
        '<div class="mpc-subs">' + sub(bf.roiPct == null ? '—' : (bf.roiPct > 0 ? '+' : '') + (+bf.roiPct).toFixed(1) + '%', 'ROI', col0(bf.roiPct)) + '</div></button>');
    }
    if (pl && pl.n) {
      cards.push('<button class="mpc" style="--ac:' + A.poly + '" onclick="showView(\'polywallets\')" title="→ Polymarket · Heute wetten">' +
        '<span class="mpc-h">🎮 Poly Public<b>n' + pl.n + '</b></span>' +
        '<div class="mpc-big" style="color:' + (pl.hitPct >= 50 ? A.good : 'var(--mi)') + '">' + (pl.hitPct == null ? '—' : Math.round(pl.hitPct) + '%') + '</div><div class="mpc-cap">Treffer · hart gegatet</div>' +
        meter(pl.hitPct, A.good) +
        '<div class="mpc-subs">' + sub(pl.roiPct == null ? '—' : (pl.roiPct > 0 ? '+' : '') + (+pl.roiPct).toFixed(1) + '%', 'ROI', col0(pl.roiPct)) +
        (pl.openN ? sub(pl.openN, 'offen', 'var(--mi2)') : '') + '</div></button>');
    }
    if ((ml && ml.n) || mmRows.length) {
      var kon = mmRows.filter(function (r) { return r.verdict === 'konsens'; }).length;
      var une = mmRows.filter(function (r) { return r.verdict === 'uneinig' || r.verdict === 'teil'; }).length;
      var na = mmRows.length - kon - une, inner;
      if (ml && ml.n) {
        inner = '<div class="mpc-big" style="color:' + (ml.hitPct >= 50 ? A.good : 'var(--mi)') + '">' + Math.round(ml.hitPct) + '%</div><div class="mpc-cap">Geld trifft</div>' +
          '<div class="mpc-subs">' + sub(ml.konHitPct == null ? '—' : Math.round(ml.konHitPct) + '%', 'Konsens n' + (ml.konN || 0), ml.konHitPct == null ? 'var(--mi3)' : ml.konHitPct >= 50 ? A.good : 'var(--mi)') +
          (ml.openN ? sub(ml.openN, 'offen', 'var(--mi2)') : '') + '</div>';
      } else {
        inner = '<div class="mpc-big mpc-soft">sammelt …</div><div class="mpc-cap">0 abgerechnet</div>' +
          '<div class="mpc-split"><i style="flex:' + (kon || .01) + ';background:' + A.good + '"></i><i style="flex:' + (une || .01) + ';background:' + A.gold + '"></i><i style="flex:' + (na || .01) + ';background:var(--mln2)"></i></div>' +
          '<div class="mpc-subs">' + sub(kon, 'Konsens', A.good) + sub(une, 'uneinig', A.gold) + (na ? sub(na, 'kein Anker', 'var(--mi3)') : '') + '</div>';
      }
      cards.push('<button class="mpc" style="--ac:' + A.flow + '" onclick="showView(\'moneymap\')" title="→ Money Map">' +
        '<span class="mpc-h">🔗 Money Map<b>' + mmRows.length + '</b></span>' + inner + '</button>');
    }
    return '<section class="md-pulse md-rise">' +
      '<div class="md-pulse-h">📈 Puls<span class="mpc-hint">letzte abgerechnete · Klick → Bereich</span></div>' +
      '<div class="mpc-grid">' + cards.join('') + '</div>' + _mdStrip(d) + _ageStr(d) + '</section>';
  }
  // ── 🧪 Signal-Bilanz (22.08.2026, Lucas: „checken ob die Signale funktionieren") ──────────────
  // Ausklappbares Board direkt unter dem Puls: pro Signal n + Win% dafuer/dagegen + Edge + Ampel.
  // Daten: dashboard_pulse.json .signalBoard (build_dashboard_pulse.py). Rein diagnostisch, read-only.
  var _SIG_LABELS = {
    form_trend:['📈','Form-Trend'], xg_strength:['⚡','xG-Stärke'], chance_creation:['🎨','Chancen'],
    form_rating:['📋','Form-Rating'], smart_money:['🐋','Smart Money'], betfair_money:['💷','Betfair-Geld'],
    betfair_coherence:['💷','Betfair-Kohärenz'], injury:['🩹','Verletzungen'], lead_lag_bias:['📊','Sharp-Lag'],
    freshness_leg:['🌬️','Frische'], pressure_index:['🎯','Tabellendruck'], league_pressure:['🔥','Ligadruck'],
    h2h_pattern:['⚔️','H2H'], venue_form:['🏟️','Heim/Auswärts'], topscorer_momentum:['🥅','Torjäger'],
    transfer_shift:['📦','Kader-Abgänge'], fixture_congestion:['🗓️','Termindichte'], apif_predictions:['🤖','Prognose-Modell'],
    travel_burden:['✈️','Reise'], mls_travel:['✈️','MLS-Reise'], weather_signal:['🌡️','Wetter'],
    lineup_signal:['🧩','Aufstellung'], incentive_signal:['🎲','Anreiz'], public_static_bias:['👥','Public-Bias'],
    reverse_line_move:['🔄','Reverse-Line'], multi_book_steam:['💨','Multi-Book-Steam'], opener_move:['📊','Opener'],
    move_following:['💨','Steam-Move'], streak_momentum:['🔗','Serie'], altitude_signal:['⛰️','Höhe'],
    coach_change:['🔄','Trainerwechsel'], game_state_openness:['🔓','Spieloffenheit'], polymarket_sharp:['🌊','Poly-Fluss'],
    steam_lag:['💨','Steam-Lag'], pinnacle_move:['📊','Pinnacle-Bewegung']
  };
  function _sigLabel(nm){ var m=_SIG_LABELS[nm]; return m ? {ic:m[0],lb:m[1]} : {ic:'•',lb:nm}; }
  function _sbStyles(){
    if(document.getElementById('sbStyles')) return;
    var s=document.createElement('style'); s.id='sbStyles';
    s.textContent='.sb-wrap{margin-top:10px}.sb-sum{display:flex;align-items:center;gap:10px;cursor:pointer;list-style:none}'
      +'.sb-sum::-webkit-details-marker{display:none}.sb-sum::after{content:\'▸\';color:var(--mi3);font-size:12px;margin-left:auto}'
      +'details[open] .sb-sum::after{content:\'▾\'}'
      +'.sb-legend{font-size:10.5px;color:var(--mi3);margin:9px 0 7px;line-height:1.5}'
      +'.sb-list{display:flex;flex-direction:column;gap:2px}'
      +'.sb-row{display:grid;grid-template-columns:9px 1.35fr .45fr 1fr 1fr .6fr;align-items:center;gap:8px;padding:5px 6px;border-radius:8px;font-size:11.5px}'
      +'.sb-row:nth-child(odd){background:rgba(255,255,255,.025)}'
      +'.sb-dot{width:9px;height:9px;border-radius:50%}'
      +'.sb-nm{font-weight:700;color:var(--mi);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}'
      +'.sb-fire{color:var(--mi3);font-variant-numeric:tabular-nums;text-align:right}'
      +'.sb-cell{color:var(--mi2);font-variant-numeric:tabular-nums;white-space:nowrap}'
      +'.sb-cell i{color:var(--mi3);font-style:normal;font-size:9px;margin-left:2px}'
      +'.sb-edge{font-weight:800;text-align:right;font-variant-numeric:tabular-nums}';
    document.head.appendChild(s);
  }
  function _mdSignalBoard(){
    var d=_md.data.pulse||{}, b=d.signalBoard;
    if(!b||!b.rows||!b.rows.length) return '';
    _sbStyles();
    var base=b.baseWinPct;
    // Belastbarkeit: Edge nur bei genug Faellen auf BEIDEN Seiten (supp>=8 & opp>=5); sonst
    // „dafuer vs. Baseline" wenn die Stuetz-Seite dick genug ist (supp>=10); sonst zu wenig Daten.
    var strength=function(r){
      if(r.supp>=8 && r.opp>=5 && r.edge!=null) return r.edge;
      if(r.supp>=10 && r.suppWinPct!=null) return r.suppWinPct-base;
      return null;
    };
    var tier=function(r){
      var s=strength(r);
      if(s==null) return {c:'var(--mi3)'};
      if(s>=10) return {c:A.good};
      if(s<=-12) return {c:A.red};
      return {c:A.gold};
    };
    var rows=b.rows.slice().sort(function(x,y){
      var sx=strength(x), sy=strength(y);
      if(sx==null&&sy==null) return y.fire-x.fire;
      if(sx==null) return 1;
      if(sy==null) return -1;
      return sy-sx;
    });
    var pct=function(v){return v==null?'—':Math.round(v)+'%';};
    var lines=rows.map(function(r){
      var L=_sigLabel(r.name), tg=tier(r), st=strength(r);
      var viaBase=!(r.supp>=8&&r.opp>=5&&r.edge!=null)&&r.supp>=10;
      var edgeTxt=st==null?'—':((st>0?'+':'')+Math.round(st)+'%'+(viaBase?'<i style="font-size:8px;color:var(--mi3);margin-left:1px">⌀</i>':''));
      return '<div class="sb-row">'
        +'<span class="sb-dot" style="background:'+tg.c+'"></span>'
        +'<span class="sb-nm">'+L.ic+' '+esc(L.lb)+'</span>'
        +'<span class="sb-fire">n'+r.fire+'</span>'
        +'<span class="sb-cell" title="Win% wenn das Signal den Pick STÜTZT ('+r.supp+' Fälle)">'+pct(r.suppWinPct)+' <i>dafür</i></span>'
        +'<span class="sb-cell" title="Win% wenn das Signal GEGEN den Pick steht ('+r.opp+' Fälle)">'+pct(r.oppWinPct)+' <i>gegen</i></span>'
        +'<span class="sb-edge" style="color:'+tg.c+'">'+edgeTxt+'</span>'
        +'</div>';
    }).join('');
    return '<details class="md-pulse md-rise sb-wrap">'
      +'<summary class="sb-sum"><span class="md-pulse-h" style="margin:0">🧪 Signal-Bilanz</span>'
      +'<span class="mpc-hint">funktionieren die Signale? · '+b.n+' Picks · Ø '+Math.round(base)+'% Win</span></summary>'
      +'<div class="sb-legend">🟢 trägt Richtungsinfo · 🟡 schwach · 🔴 evtl. schädlich · ⚪ zu wenig Daten. '
      +'„dafür/gegen" = Win-Quote, wenn das Signal den Pick stützt bzw. dagegen steht · Zahl rechts = Edge (dafür−gegen), ⌀ = dafür vs. Ø bei dünner Gegen-Seite.</div>'
      +'<div class="sb-list">'+lines+'</div></details>';
  }

  // ── 🚫 NOBET-Bilanz (23.08.2026, Lucas: „wenn ein NOBET stark positiv wäre — was macht man?") ──
  // Waren unsere Abstufungen richtig? Pro Kipp-Grund: Schatten-Trefferquote + Ø CLV der demoteten
  // Picks. CLV ist der Richter (negativ = Linie lief weiter gegen uns = richtig gekippt). Read-only,
  // NICHT im P&L. Daten: dashboard_pulse.json .nobetBoard (build_dashboard_pulse.py).
  function _mdNobetBoard(){
    var d=_md.data.pulse||{}, b=d.nobetBoard;
    if(!b||!b.rows||!b.rows.length) return '';
    _sbStyles();
    var band=b.clvBand||1, minF=b.minFire||6;
    var tier=function(r){
      if(r.n<minF||r.clvAvg==null) return {c:'var(--mi3)', t:'zu wenig Daten'};
      if(r.clvAvg<=-band) return {c:A.good, t:'gut gekippt'};
      if(r.clvAvg>=band)  return {c:A.red,  t:'zu früh gekippt'};
      return {c:A.gold, t:'grenzwertig'};
    };
    var clvTxt=function(v){ return v==null?'—':((v>0?'+':'')+(+v).toFixed(1)+'pp'); };
    var lines=b.rows.map(function(r){
      var tg=tier(r);
      var clvCol=(r.clvAvg!=null&&r.clvAvg<0)?A.good:(r.clvAvg>0?A.red:'var(--mi2)');
      return '<div class="sb-row">'
        +'<span class="sb-dot" style="background:'+tg.c+'"></span>'
        +'<span class="sb-nm">'+esc(r.reason)+'</span>'
        +'<span class="sb-fire">n'+r.n+'</span>'
        +'<span class="sb-cell" title="Schatten-Trefferquote — hätte gewonnen">'+(r.winPct==null?'—':r.winPct+'%')+' <i>Schatten</i></span>'
        +'<span class="sb-cell" style="color:'+clvCol+'" title="Ø Closing Line Value NACH dem Kippen — der ehrliche Richter">'+clvTxt(r.clvAvg)+' <i>CLV</i></span>'
        +'<span class="sb-edge" style="color:'+tg.c+';font-size:9.5px;font-weight:700">'+tg.t+'</span>'
        +'</div>';
    }).join('');
    var overCol=(b.clvAvg!=null&&b.clvAvg<0)?A.good:(b.clvAvg>0?A.red:'var(--mi2)');
    return '<details class="md-pulse md-rise sb-wrap">'
      +'<summary class="sb-sum"><span class="md-pulse-h" style="margin:0">🚫 NOBET-Bilanz</span>'
      +'<span class="mpc-hint">richtig abgestuft? · '+b.n+' NOBETs · Schatten '+(b.winPct==null?'—':b.winPct+'%')+' · Ø CLV <b style="color:'+overCol+'">'+clvTxt(b.clvAvg)+'</b></span></summary>'
      +'<div class="sb-legend">CLV ist der Richter: 🟢 <b>gut gekippt</b> (Linie lief weiter GEGEN uns, Ø CLV negativ) · 🔴 <b>zu früh</b> (lief weiter FÜR uns → Sieger weggeworfen) · ⚪ zu wenig Daten.<br>'
      +'„Schatten" = hätte gewonnen — <b>allein trügerisch</b>: hohe Quote bei negativem CLV heißt, der Preis war schon weg (also korrekt gekippt). Zählt NICHT in P&L/Lernen.</div>'
      +'<div class="sb-list">'+lines+'</div></details>';
  }

  // 13.08.2026 (Lucas-Audit): „Jetzt spielen"-Leiste — wo lohnt Setzen (beste Conviction-Stufe/Signal
  // nach ROI) + was gerade laeuft. Daten lagen schon in dashboard_pulse.json (strip), wurden aber nie
  // gerendert. CSS .md-pulse-strip existierte bereits.
  function _mdStrip(d) {
    var s = d && d.strip; if (!s) return '';
    var it = function (lab, val, sub) {
      return '<span style="display:inline-flex;gap:5px;align-items:baseline"><b style="color:var(--mi3);font-weight:600">' + lab + '</b>' + val + (sub ? ' <i style="color:var(--mi3);font-style:normal">' + sub + '</i>' : '') + '</span>';
    };
    var roi = function (b) { return '<b style="color:' + (b.roiPct > 0 ? A.good : b.roiPct < 0 ? A.red : 'var(--mi2)') + '">' + (b.roiPct > 0 ? '+' : '') + (+b.roiPct).toFixed(1) + '% ROI</b>'; };
    // 03.09.2026 (Lucas-Checkup): die Leiste warb mit „Beste Stufe Conv 7 · +2.5% ROI · n149" —
    // aus dem GANZEN Bestand über mehrere Engine-Versionen, während Ebene 1 direkt darunter für
    // dieselbe Stufe `4/30` zeigt und sagt, dass alte Plays nicht zählen. Jetzt rechnet der Puls
    // auf der aktuellen Engine und trägt seine Untergrenze mit. Was sie nicht hält, steht weiter
    // da — aber als „nicht belegt", nicht als Empfehlung.
    var sub = function (b) {
      var t = 'n' + b.n;
      if (b.belegt) return t + ' · UG ' + (b.roiUgPct > 0 ? '+' : '') + (+b.roiUgPct).toFixed(1) + '%';
      return t + ' · <span style="color:' + A.gold + '">nicht belegt'
        + (b.roiUgPct != null ? ' (UG ' + (b.roiUgPct > 0 ? '+' : '') + (+b.roiUgPct).toFixed(1) + '%)' : '')
        + '</span>';
    };
    var parts = [];
    if (s.bestConv) parts.push(it('Beste Stufe', 'Conv ' + esc(s.bestConv.key) + ' · ' + roi(s.bestConv), sub(s.bestConv)));
    if (s.bestSignal) parts.push(it('Bestes Signal', esc(s.bestSignal.key) + ' · ' + roi(s.bestSignal), sub(s.bestSignal)));
    var inf = s.inflight || {}, live = [];
    if (inf.poly) live.push(inf.poly + ' Poly');
    if (inf.betfair) live.push(inf.betfair + ' Betfair');
    if (inf.cards) live.push(inf.cards + ' Cards');
    if (live.length) parts.push(it('Läuft', esc(live.join(' · '))));
    if (!parts.length) return '';
    return '<div class="md-pulse-strip" title="Wo sich Setzen historisch auszahlt + was gerade offen ist">' + parts.join('') + '</div>';
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
  // 13.08.2026 (Lucas): EINE unified "Top-Wetten jetzt"-Box — das Beste ueber ALLE Flaechen
  // (Engine-Cards, Poly-Lag, Betfair-Steam, Money-Map), gerankt nach einem gemeinsamen Signal-Score
  // statt chronologisch. Exoten bleiben drin, aber markiert + heruntergestuft. Artefakt-Moves raus.
  // ── Konjunktion: nur wo mehrere Ströme GLEICHZEITIG zustimmen ────────────────
  // 29.08.2026 (Lucas): „dort kommst halt nur rein wenn Pini move da / Betfair geld oben und
  // quoten mitziehen / Poly geld oben". Die Auswahl trifft killer.py — das Frontend zeigt sie
  // nur. Wichtig dabei: die Sektion behauptet NICHT, sie sei spielbar. Sie liest ihren eigenen
  // Stand aus freigabe.json und schreibt ihn oben rechts hin. Solange die ROI-Untergrenze nicht
  // über null liegt, steht dort „beobachten", nicht „spielen".
  function _mdKillerStand() {
    var f = _md.data && _md.data.freigabe;
    var zeilen = (f && (f.alle || f.zeilen)) || [];
    // 31.08.2026: seit dem Ligen-Zuschnitt gibt es MEHRERE Konjunktions-Schubladen
    // („Top-5 + MLS", „übrige Ligen", „gehalten"). Vorher genügte die erste — jetzt wäre das
    // zufällig die kleinste. Genommen wird die mit den meisten abgerechneten Plays: der Badge
    // ist ein Ersatz, solange das eigene Buch zu dünn ist, und dafür zählt die breiteste
    // Stichprobe. Welche es war, steht im Badge, damit die Zahl nicht anonym bleibt.
    var best = null;
    for (var i = 0; i < zeilen.length; i++) {
      var z = zeilen[i];
      if (String(z.schublade || '').indexOf('Konjunktion') !== 0) continue;
      if (!best || (+z.n || 0) > (+best.n || 0)) best = z;
    }
    return best;
  }
  // 30.08.2026 (Lucas: „sollten wir das nicht mittracken, damit ich seh wie gut es performt?"):
  // Der Badge zeigte die Zahl der SCHLUSS-Definition aus dem Betfair-Track (n=70) — eine
  // verwandte, aber andere Menge als das, was in dieser Sektion wirklich stand. Sobald das
  // eigene Buch genug abgerechnete Zeilen hat, zählt das eigene; bis dahin steht dran, dass
  // die Zahl von woanders kommt und wie weit das eigene Buch ist.
  var KL_EIGEN_MIN_N = 20;
  function _mdKillerBadge(st, bil) {
    var g = (bil && bil.gesamt) || null;
    if (g && g.n >= KL_EIGEN_MIN_N) {
      // 30.08.2026: hier stand `r > 0` — der nackte Punktschätzer. Bei n=32 / ROI +7% war der
      // Badge damit GRÜN, während die Fußzeile zwei Zeilen tiefer „Beobachtungsliste, keine
      // Freigabe" sagte. Die einseitige 95%-Untergrenze lag bei −20%. Grün darf nur werden, was
      // denselben Richter besteht wie die Freigabe: die UNTERGRENZE über null. Fehlt sie (altes
      // killer.json vor diesem Lauf), bleibt es gelb — fehlende Information ist keine Erlaubnis.
      var r = g.roi == null ? null : Math.round(g.roi * 100);
      var lb = (g.roiLb == null) ? null : Math.round(g.roiLb * 100);
      var belegt = lb != null && lb > 0;
      return { txt: (belegt ? '✅ ' : '👀 ') + 'eigene Bilanz · ' + g.gewonnen + '–' + g.verloren +
                    ' · ROI ' + (r == null ? '—' : (r >= 0 ? '+' : '') + r + '%') +
                    ' (UG ' + (lb == null ? '—' : (lb >= 0 ? '+' : '') + lb + '%') + ')',
               col: belegt ? A.good : A.gold,
               bg: belegt ? 'rgba(46,160,67,.16)' : 'rgba(201,133,0,.14)' };
    }
    // 01.09.2026 (Lucas: „das wirkt schon sehr oft redundant"): hier stand frueher das URTEIL
    // aus dem Freigabe-Register — dieselbe Zahl aus derselben Datei, die die Ebene direkt
    // darueber schon ausspricht. Das war die einzige echte Doppelung der Uebersicht.
    // Jetzt sagt dieser Badge nur noch, wie weit das EIGENE Buch dieser Ebene ist; das Urteil
    // gehoert Ebene 1 und wird nicht wiederholt.
    var fort = g ? (g.n + '/' + KL_EIGEN_MIN_N + (bil.offen ? ' · ' + bil.offen + ' offen' : ''))
                 : ('0/' + KL_EIGEN_MIN_N);
    return { txt: '👀 eigenes Buch ' + fort, col: A.gold, bg: 'rgba(201,133,0,.14)' };
  }
  // Die Bilanz DER SEKTION: was sie gezeigt hat und wie es ausging — zum Haltepreis gerechnet,
  // also zu dem Preis, der dastand, als die Zeile erschien. Aufklappbar wie im Card-Tracking.
  function _mdKlBilanz(bil) {
    if (!bil || !bil.gesamt) return '';
    var g = bil.gesamt, z = bil.zeilen || [];
    if (!g.n && !bil.offen) return '';
    var stufe = function (nr) {
      var b = (bil.jeStufe || {})[String(nr)] || {};
      if (!b.n) return '';
      var r = b.roi == null ? null : Math.round(b.roi * 100);
      return '<span class="md-kl-c">Stufe ' + nr + ': ' + b.gewonnen + '–' + b.verloren +
        ' · ' + (r == null ? '—' : (r >= 0 ? '+' : '') + r + '%') + '</span>';
    };
    if (!g.n) {
      return '<div class="md-kl-foot">📁 Noch nichts abgerechnet — ' + bil.offen +
        ' Zeile' + (bil.offen === 1 ? '' : 'n') + ' warten auf ihr Ergebnis. ' +
        'Gerechnet wird zum Haltepreis, also zu dem Preis, der beim Treffer dastand.</div>';
    }
    var r = g.roi == null ? null : Math.round(g.roi * 100);
    var kopf = '📁 ' + g.n + ' abgerechnet · ' + g.gewonnen + ' gewonnen · ' + g.verloren +
      ' verloren · ' + (g.einheiten >= 0 ? '+' : '') + (+g.einheiten).toFixed(2) + ' Einheiten' +
      (r == null ? '' : ' (ROI ' + (r >= 0 ? '+' : '') + r + '%)') +
      (bil.offen ? ' · ' + bil.offen + ' offen' : '');
    var liste = z.map(function (x) {
      var col = x.win ? A.good : A.red;
      return '<div class="md-kl-bz"><span style="color:' + col + ';font-weight:800">' +
        (x.win ? '✓' : '✗') + '</span><span class="md-kl-bn">' + esc(x.name || '—') + '</span>' +
        '<span class="md-kl-bl">' + esc(String(x.liga || '').slice(0, 22)) + '</span>' +
        '<span class="md-kl-bo">@' + (+x.haltePreis).toFixed(2) +
        (x.schlussPreis != null && Math.abs(+x.schlussPreis - +x.haltePreis) >= 0.02
          ? ' <i style="color:var(--mi3);font-style:normal">→' + (+x.schlussPreis).toFixed(2) + '</i>' : '') +
        '</span><span class="md-kl-bs">S' + (x.stufe || 2) + '</span></div>';
    }).join('');
    return '<details class="md-kl-det"><summary class="md-kl-sum">' + kopf +
      '<span class="md-kl-ch" style="margin-left:auto">' + stufe(1) + stufe(2) + '</span></summary>' +
      '<div class="md-kl-bliste">' + liste + '</div>' +
      '<div class="md-kl-foot" style="border-top:0;padding-top:6px">Zum Haltepreis gerechnet — dem Preis, ' +
      'der beim Treffer dastand. Flach eine Einheit je Zeile.</div></details>';
  }
  // 30.08.2026 (Lucas-Checkup, zweite Runde): die Sektion zeigte FC Utrecht v PSV mit „⏱ 1m",
  // während die Betfair-HT-Kachel daneben schon „● LIVE" schrieb — das Spiel lief bereits.
  // killer.py entfernt angepfiffene Zeilen korrekt, aber killer.json ist bis zu 15 Minuten alt;
  // dazwischen pfeift ein Spiel an und die Zeile steht weiter da. Ein Feed-Zeitstempel ist kein
  // Ereignis-Zeitstempel — das Frontend muss selbst rechnen.
  //
  // Und ein Fenster: „Lecce v Roma ⏱ 30h 16m" stand in einer Sektion, die beantworten soll, was
  // JETZT spielbar ist. Der gehaltene Preis von heute Mittag gilt morgen Abend nicht mehr.
  // 12 Stunden, dasselbe Fenster wie nebenan in „Top-Wetten jetzt".
  var KL_FENSTER_H = 12;
  function _klSichtbar(z) {
    var t = Date.parse(String(z && z.kickoff || '').replace('Z', '+00:00'));
    if (!isFinite(t)) return false;
    var h = (t - Date.now()) / 3.6e6;
    return h > 0 && h <= KL_FENSTER_H;
  }
  // Die Brücke zwischen den beiden Sektionen. Steht ein Spiel in BEIDEN, ist das keine
  // Doppelung, sondern die stärkste Aussage, die das Portal machen kann: das stärkste
  // Einzelsignal fällt mit der vollen Konjunktion zusammen. Ohne Markierung sah es aus wie
  // zweimal dieselbe Zeile untereinander. Nur MARKIEREN, nicht ranken — der Score in den
  // Top-Wetten bleibt unverändert, weil eine Rang-Änderung eine Auswahl-Entscheidung wäre.
  function _klKeys() {
    var k = _md.data && _md.data.killer, m = {};
    [].concat((k && k.stufe1) || [], (k && k.stufe2) || []).forEach(function (z) {
      if (!_klSichtbar(z)) return;
      if (z.matchId) m['id:' + String(z.matchId)] = z.stufe || 2;
      if (z.home && z.away) m['tm:' + team(z.home) + team(z.away)] = z.stufe || 2;
    });
    return m;
  }
  // ══ FREIGABE-REGISTER (01.09.2026, Lucas: „wo bauen wir das im Frontend ein?") ══════════════
  // Ort: direkt nach dem Puls, VOR „Mehrfach gedeckt". Das Register ist die Meta-Antwort ueber
  // allen Sektionen darunter — „darf ich hiervon ueberhaupt etwas blind spielen?". Steht es
  // weiter unten, liest man erst die Empfehlungen und danach die Einschraenkung; das ist die
  // falsche Reihenfolge. Lucas' Satz („ich muss wissen, was ich blind nachspielen kann, weil das
  // System es sagt") ist die erste Frage der Seite, also gehoert die Antwort nach oben.
  //
  // Bewusst KEINE Rangliste der besten Plays: das Register urteilt ueber SCHUBLADEN, nicht ueber
  // einzelne Zeilen. Und es darf leer ausgehen — dann sagt es, wie weit die naechste noch ist.
  var FG_BAR_MAX = 30;   // nur fuer die Balkenbreite; die echte Schwelle kommt aus regeln.minN
  function _mdFgZahl(v, suffix, stellen) {
    if (v == null) return '—';
    var x = (stellen === 1) ? (+v).toFixed(1) : Math.round(v);
    return (v >= 0 ? '+' : '') + x + (suffix || '');
  }
  function _mdFgZeile(r, minN) {
    // Eine Schublade als Zeile: Name, Stichprobe, ROI und CLV IMMER mit Untergrenze daneben
    // (feedback_punktschaetzer_kein_beleg — der Punktschaetzer allein hat hier nichts verloren).
    var frei = r.status === 'freigegeben';
    var col = frei ? A.good : (r.status === 'ruht' ? A.ink3 : A.gold);
    var n = +r.n || 0, ziel = minN || FG_BAR_MAX;
    var pct = Math.max(0, Math.min(100, Math.round(n / ziel * 100)));
    var alt = (r.nAlt ? '<span class="md-kl-c" title="Plays aus einer früheren Engine-Version — sie zählen NICHT für die Freigabe, stehen hier nur als Kontext">'
      + '+' + r.nAlt + ' alt (' + _mdFgZahl(r.roiAlt == null ? null : r.roiAlt * 100, '%') + ')</span>' : '');
    return '<div class="md-kl-bz" style="align-items:center">'
      + '<span style="color:' + col + ';font-weight:800;flex-shrink:0">' + (frei ? '✓' : r.status === 'ruht' ? '·' : '◔') + '</span>'
      + '<span class="md-kl-bn">' + esc(String(r.schublade || '—')) + '</span>'
      + '<span class="md-kl-bl" style="min-width:74px">'
      +   '<span style="display:inline-block;width:52px;height:4px;border-radius:2px;background:var(--mln2);vertical-align:middle;overflow:hidden">'
      +     '<span style="display:block;height:4px;width:' + pct + '%;background:' + col + '"></span></span>'
      +   ' <span style="font-size:10px;color:var(--mi3)">' + n + '/' + ziel + '</span></span>'
      + '<span class="md-kl-bo" title="ROI mit einseitiger 95%-Untergrenze">'
      +   'ROI ' + _mdFgZahl(r.roi == null ? null : r.roi * 100, '%')
      +   ' <i style="color:var(--mi3);font-style:normal">(UG ' + _mdFgZahl(r.roiLb == null ? null : r.roiLb * 100, '%') + ')</i></span>'
      + '<span class="md-kl-bs" title="CLV mit Untergrenze — bei kleinem n belastbarer als der ROI">'
      +   'CLV ' + _mdFgZahl(r.clv, 'pp', 1) + '</span>' + alt + '</div>';
  }
  // Eine Ebene der Spielbar-Sektion. Alle drei bekommen denselben Kopf, damit man sie
  // uebereinander VERGLEICHEN kann: Nummer (Strenge) · Frage · Bauart · eigener Stand.
  // Vorher hatte jede Sektion ihren eigenen Kopfbau — deshalb sahen drei Antworten aus wie
  // dreimal dieselbe Frage.
  function _mdEbene(nr, frage, mech, mechCol, mechTitel, unter, badge, inhalt) {
    var rand = mechCol === A.good ? 'rgba(46,160,71,.45)' : mechCol === A.blue ? 'rgba(76,194,255,.45)' : 'var(--mln2)';
    if (!mechCol) mechCol = 'var(--mi2)';   // Ebene 3 traegt bewusst KEINE Signalfarbe: sie belegt nichts.
    return '<div class="md-eb">'
      + '<div class="md-eb-h"><span class="md-eb-n e' + nr + '">' + nr + '</span>'
      + '<span class="md-eb-q">' + frage + '</span>'
      + '<span class="md-mech" style="color:' + mechCol + ';border-color:' + rand + '" title="'
      + mechTitel + '">' + mech + '</span>'
      + (badge ? '<span class="md-eb-st" style="background:' + badge.bg + ';color:' + badge.col + '">' + badge.txt + '</span>' : '')
      + '<span class="md-eb-s">' + unter + '</span></div>' + inhalt + '</div>';
  }
  // ── Ebene 1: das Freigabe-Register ────────────────────────────────────────────────────
  // Beurteilt SCHUBLADEN ueber Wochen, nicht einzelne Spiele heute. Das ist der Grund, warum
  // sie ganz oben steht und warum sie kein einziges Spiel zeigt: sie sagt, wie ernst man die
  // beiden Ebenen darunter nehmen darf.
  function _mdFreigabe() {
    var f = _md.data && _md.data.freigabe;
    var frage = 'Darf ich ueberhaupt blind spielen?'.replace('ueberhaupt', 'überhaupt');
    var mechT = 'Register: beurteilt SCHUBLADEN ueber Wochen, nicht einzelne Spiele. Freigegeben wird eine Schublade erst, wenn ihre Untergrenze ueber null liegt.';
    var unter = 'nicht der einzelne Tipp wird freigegeben, sondern die Schublade, aus der er kommt';
    // ❔ statt gruen: eine fehlende oder unlesbare Datei ist keine Aussage über die Freigabe.
    if (!f || !f.zusammenfassung) {
      return _mdEbene(1, frage, 'Register', A.good, mechT, unter,
        { txt: '❔ unbekannt', col: A.gold, bg: 'rgba(201,133,0,.14)' },
        '<div class="md-kl-foot" style="border-top:0;padding-top:8px">freigabe.json fehlt oder ist nicht lesbar — '
        + 'ob etwas freigegeben ist, lässt sich gerade <b>nicht</b> sagen. Das ist ausdrücklich nicht dasselbe wie „nichts freigegeben".</div>');
    }
    var z = f.zusammenfassung || {}, minN = (f.regeln && f.regeln.minN) || FG_BAR_MAX;
    var frei = f.freigegeben || [], kand = (f.kandidaten || []).slice(0, 3);
    var bad = frei.length
      ? { txt: '✅ ' + frei.length + ' freigegeben', col: A.good, bg: 'rgba(46,160,71,.16)' }
      : { txt: '👀 nichts freigegeben' + (z.naechsteFreigabe != null ? ' · nächste in ' + z.naechsteFreigabe + ' Plays' : ''),
          col: A.gold, bg: 'rgba(201,133,0,.14)' };

    var body;
    if (frei.length) {
      body = frei.map(function (r) { return _mdFgZeile(r, minN); }).join('');
    } else {
      body = '<div class="md-kl-foot" style="border-top:0;padding-top:8px;padding-bottom:2px">'
        + '<b>Heute gibt es nichts, dem man blind folgen darf</b> — keine Schublade hat ihre Untergrenze über null. '
        + 'Das ist ein Ergebnis, kein Fehler, und es gilt für alles darunter. Am nächsten dran:</div>'
        + (kand.length ? kand.map(function (r) { return _mdFgZeile(r, minN); }).join('')
                       : '<div class="md-kl-foot" style="border-top:0">Noch nicht einmal ein Kandidat — die Bücher sammeln.</div>');
    }

    // Engine-Zeile: seit 01.09. zählt für eine Freigabe nur die aktuelle Engine-Version.
    var eng;
    if (f.engineGefiltert === true) {
      eng = 'Gerechnet auf Engine <b>' + esc(String(f.engine)) + '</b> — Plays älterer Versionen zählen nicht für eine Freigabe und stehen nur als „alt" daneben.';
    } else if (f.engineGefiltert === false) {
      eng = '⚠️ Ohne Engine-Filter gerechnet — Plays aus älteren Bewertungen zählen mit.';
    } else {
      eng = '❔ Ob auf eine Engine-Version gefiltert wurde, sagt die Datei nicht (alte Fassung).';
    }
    var regel = (f.regeln && f.regeln.text) || '';

    var alle = (f.alle || []).slice().sort(function (a, b) { return (+b.n || 0) - (+a.n || 0); });
    var det = alle.length ? '<details class="md-kl-det"><summary class="md-kl-sum">📁 Alle '
      + alle.length + ' Schubladen ansehen<span class="md-kl-ch" style="margin-left:auto">'
      + '<span class="md-kl-c">' + (z.kandidaten || 0) + ' Kandidaten</span>'
      + '<span class="md-kl-c">' + (z.ruhend || 0) + ' ruhend</span></span></summary>'
      + '<div class="md-kl-bliste">' + alle.map(function (r) { return _mdFgZeile(r, minN); }).join('') + '</div>'
      + '<div class="md-kl-foot" style="border-top:0;padding-top:6px">' + esc(regel) + '</div></details>' : '';

    return _mdEbene(1, frage, 'Register', A.good, mechT, unter, bad,
      body + '<div class="md-kl-foot">' + eng + '</div>' + det);
  }

  function _mdKiller() {
    var k = _md.data && _md.data.killer;
    var s1 = ((k && k.stufe1) || []).filter(_klSichtbar), s2 = ((k && k.stufe2) || []).filter(_klSichtbar);
    var st = _mdKillerStand(), bil = (k && k.bilanz) || null, bad = _mdKillerBadge(st, bil);
    // 01.09.2026: der Kopf heißt weiter „Mehrfach gedeckt", ist aber Ebene 2 EINER Sektion.
    // Der Badge spricht seit heute nur noch über das EIGENE Buch — das Urteil über die
    // Schublade steht eine Ebene höher und muss hier nicht ein zweites Mal stehen.
    var ebene = function (inhalt) {
      return _mdEbene(2, 'Wie viele Bücher sind sich einig?', 'Punktestand', A.blue,
        'Je zustimmendem Buch 2 Punkte, 1 für Tiefe im selben Buch, 1 wenn es schon ≥3h vor Anpfiff steht. Nicht erhobene Bücher senken den Nenner — sie kosten keine Punkte.',
        'Betfair · Polymarket · Pinnacle im Vergleich · gehalten bis zum Anpfiff · leer heißt leer',
        bad, inhalt);
    };
    if (!s1.length && !s2.length) {
      var regel = (k && k.regeln && k.regeln.text) || 'Geldanteil, frischer Zufluss und mitziehende Quote müssen zusammenfallen.';
      return ebene('<div class="md-kl-foot" style="border-top:0;padding-top:8px">Gerade deckt sich nichts. ' +
        esc(regel) + '</div>' + _mdKlBilanz(bil));
    }
    var now = Date.now();
    var uhr = function (iso) {
      var t = iso ? new Date(String(iso).replace('Z', '+00:00')) : null;
      return t && isFinite(t) ? ('0' + t.getHours()).slice(-2) + ':' + ('0' + t.getMinutes()).slice(-2) : null;
    };
    // ── Deckungs-Profil (30.08.2026, Lucas: „glaub da ist noch mehr drin") ──────────────
    // Vorher war jede Zeile eine Kette gleich aussehender Chips: die drei Pflicht-Bedingungen
    // sahen aus wie die optionalen Verstärker, und eine Zeile mit fünf Strömen war auf einen
    // Blick nicht von einer mit zweien zu unterscheiden. Das ist ausgerechnet die Frage, die
    // die Sektion beantworten soll.
    //
    // Jetzt: FESTE Plätze je Geldstrom, immer in derselben Reihenfolge, belegt oder leer. Man
    // zählt die leuchtenden Blöcke, statt Text zu lesen — und weil die Plätze fest sind, sind
    // zwei Zeilen untereinander vergleichbar. Gruppiert wird nach QUELLE, nicht nach Bedingung:
    // Betfair trägt drei Belege, Pinnacle zwei, Poly und Form je einen. Damit bleiben es vier
    // Farben statt sieben (dataviz: Farben nie über acht, und hier sind es Identitäten).
    //
    // Palette gegen den dunklen Untergrund #151b24 mit scripts/validate_palette.js geprüft:
    // alle vier bestehen Helligkeitsband, Chroma, Kontrast und CVD-Trennung (schlechtestes
    // Paar Gold↔Grün ΔE 8,4 protan). Unter Tritanopie liegt dasselbe Paar bei 4,0 — deshalb
    // trägt JEDER Block zusätzlich sein Kürzel. Farbe allein entscheidet hier nichts.
    var KL_STROEME = [
      { k: 'bf',   kurz: 'BF',   name: 'Betfair',  col: A.bf,   n: 3 },
      { k: 'pinn', kurz: 'PIN',  name: 'Pinnacle', col: A.pinn, n: 2 },
      { k: 'poly', kurz: 'POLY', name: 'Poly',     col: A.poly, n: 1 },
      { k: 'form', kurz: 'FORM', name: 'Form',     col: A.gold, n: 1 }
    ];
    function _klDeckung(x) {
      var v = {};
      (x.verstaerker || []).forEach(function (a) { v[a.art] = a; });
      // Belegt/unbelegt je Strom. Die drei Betfair-Plätze sind das Tor selbst — sie sind bei
      // jeder gezeigten Zeile voll; sichtbar bleiben sie trotzdem, weil sie der Beleg sind.
      var belegt = {
        bf: [true, true, true],
        pinn: [!!v.pinn, !!v.pinnMove],
        poly: [!!x.poly],
        form: [!!v.streak || !!v.track]
      };
      var titel = {
        bf: 'Betfair: Geldanteil ' + (x.anteilPct || 0) + '% · frischer Zufluss · Quote zieht mit',
        pinn: 'Pinnacle: ' + (v.pinn ? 'stimmt zu' : 'keine Zustimmung') + ' · ' +
              (v.pinnMove ? v.pinnMove.text : 'keine Bewegung'),
        // 01.09.2026 (Lucas: „poly taucht da mmn nie aktiv auf?"): der Titel behauptete bei jedem
        // leeren Block „kein Poly-Markt" — dabei ist der haeufigste Fall, dass es den Markt sehr
        // wohl gibt, aber die Holder-Anteile ausserhalb des ~3h-Freeze schlicht nicht erhoben sind.
        poly: x.poly ? ('Poly-Geld ' + x.poly.anteilPct + '% auf derselben Seite')
              : x.polyStatus === 'nein' ? 'Poly-Geld liegt NICHT (ausreichend) auf dieser Seite'
              : 'Poly-Anteil unbekannt — die Holder-Anteile werden erst ab ca. 3h vor Anpfiff erhoben. Das ist kein Nein.',
        form: v.streak ? v.streak.text : (v.track ? v.track.text : 'keine Form-/Liga-Stütze')
      };
      var n = 0, moeglich = 0;
      var bloecke = KL_STROEME.map(function (st) {
        var b = belegt[st.k] || [], an = b.filter(Boolean).length;
        // Ein NICHT ERHOBENER Strom zaehlt auch nicht ins Moegliche — sonst liest sich „3/7" wie
        // „vier Bedingungen fehlen", obwohl eine davon nie gepruefet wurde. Aus 3/7 wird 3/6.
        n += an;
        moeglich += (st.k === 'poly' && !((belegt.poly || [])[0]) && x.polyStatus !== 'nein') ? 0 : st.n;
        var pips = b.map(function (voll) {
          return '<i class="md-kl-pip' + (voll ? '' : ' leer') + '"' +
            (voll ? ' style="background:' + st.col + '"' : '') + '></i>';
        }).join('');
        var zahl = (st.k === 'bf' && x.anteilPct != null) ? ' ' + x.anteilPct + '%' : '';
        // ❔ statt Leere: ein unbekannter Strom darf nicht aussehen wie ein abgelehnter. Bisher
        // war der POLY-Block in beiden Faellen identisch dunkel — man las ein Nein, wo niemand
        // gefragt hatte. Gilt nur fuer Poly; Betfair ist per Konstruktion immer da, und bei
        // Pinnacle/Form heisst leer wirklich „liegt nicht vor".
        // Auch eine ALTE killer.json ohne `polyStatus` gilt als unbekannt — wir behaupten kein
        // Nein, das wir nicht belegen koennen (dieselbe Richtung wie ueberall sonst).
        var unbekannt = (st.k === 'poly' && !an && x.polyStatus !== 'nein');
        return '<span class="md-kl-str' + (an ? '' : ' aus') + '" title="' + esc(titel[st.k]) + '">' +
          '<span class="md-kl-pips">' + pips + '</span>' +
          '<span class="md-kl-lbl"' + (an ? ' style="color:' + st.col + '"' : '') + '>' + st.kurz + zahl +
          (unbekannt ? ' <i style="font-style:normal;color:var(--mi3)" title="nicht erhoben">❔</i>' : '') +
          '</span></span>';
      }).join('');
      return { html: bloecke, n: n, moeglich: moeglich };
    }
    // Ein Meter für den Geldanteil stand hier zuerst — und ist wieder rausgeflogen. Über vier
    // Zeilen lag er bei 74–84%: vier fast identische Balken, die Schwellenmarke kaum sichtbar.
    // Ein Verhältnis, das nie nennenswert schwankt, ist als Balken Rauschen. Die Zahl steht
    // jetzt direkt am Betfair-Block (dataviz: selektive Direktbeschriftung schlägt eine Marke,
    // wenn es genau EIN Wert ist).
    // ── Bücher-Punktestand (01.09.2026) ────────────────────────────────────────────────
    // Lucas: „ich will die Bücher alle im Vergleich mit den Kriterien, wie viel erfüllt wird, mit
    // einer Punkteanzeige … das Maximum ist zehn von zehn." Und: „ich sitze nicht zehn Stunden am
    // Dashboard" — die Zahl muss in einer Sekunde lesbar sein, die Details liegen in den Terminals.
    //
    // Das Deckungs-Profil darunter zählte Betfair mit DREI und Pinnacle mit ZWEI Plätzen. „6/7 voll
    // gedeckt" las sich wie sechs Zeugen und waren zweieinhalb. Der Punktestand zählt stattdessen
    // BÜCHER: zustimmendes Buch 2, Tiefe im selben Buch 1, Dauer 1 — die Gewichtung kommt aus der
    // Messung vom 01.09. (Bücher addieren +11,5%; Signale stapeln −1,1%), nicht aus dem Bauch.
    //
    // ⚠️ Ein nicht erhobenes Buch senkt den NENNER, es kostet keine Punkte: „5/7", nicht „5/10".
    var PKT_COL = function (p, m) {
      if (!m) return 'var(--mi3)';
      var q = p / m;
      return q >= 0.8 ? A.good : q >= 0.55 ? A.gold : 'var(--mi2)';
    };
    function _klPunkte(x) {
      var pk = x && x.punkte;
      if (!pk || typeof pk.punkte !== 'number' || !pk.moeglich) return null;   // altes killer.json
      var bloecke = (pk.teile || []).map(function (t) {
        var un = t.status === 'unbekannt';
        var an = t.punkte > 0;
        var col = un ? 'var(--mi3)' : an ? A.good : 'var(--mi2)';
        var tip = un ? (t.name + ' — nicht erhoben, zählt nicht in den Nenner')
                     : (t.name + ': ' + (t.grund ? t.grund.text : '') +
                        (t.tiefe && t.tiefe.ok ? ' · ' + t.tiefe.text : ''));
        return '<span class="md-pk-b" title="' + esc(tip) + '" style="border-color:' + col + '">' +
          '<b style="color:' + col + '">' + esc(t.buch) + '</b>' +
          '<i>' + (un ? '❔' : t.punkte + '/' + t.moeglich) + '</i></span>';
      }).join('');
      return { html: bloecke, punkte: pk.punkte, moeglich: pk.moeglich, dauerH: pk.dauerH };
    }

    var row = function (x) {
      var k2 = x.kickoff ? Date.parse(String(x.kickoff).replace('Z', '+00:00')) : NaN;
      var min = isFinite(k2) ? Math.max(0, Math.round((k2 - now) / 60000)) : null;
      var ko = (min == null) ? null : (min < 60 ? min + 'm' : Math.floor(min / 60) + 'h' + (min % 60 ? ' ' + (min % 60) + 'm' : ''));
      var pkt = _klPunkte(x);
      var deck = pkt ? null : _klDeckung(x);   // Rueckfall fuer ein killer.json von vor dem 01.09.
      // 30.08.2026 (Lucas: „vorhin stand da Inter und Freiburg, jetzt Man Utd, und nun wieder
      // Inter — das wechselt auch ohne dass ich die Seite aktualisiere"): der Treffer wird jetzt
      // bis zum Anpfiff gehalten. Damit das nicht wie ein eingefrorener Fehler aussieht, steht
      // dran, SEIT WANN er steht und ob die Bedingungen gerade noch anliegen.
      var seit = uhr(x.gehaltenSeit);
      var stand = x.aktiv
        ? '<span class="md-kl-live"><i></i>läuft' + (seit ? ' · seit ' + seit : '') + '</span>'
        : '<span class="md-kl-halt">gehalten' + (seit ? ' seit ' + seit : '') +
          (uhr(x.zuletztAktiv) ? ' · zuletzt ' + uhr(x.zuletztAktiv) : '') + '</span>';
      // Der Haltepreis ist der Preis, den die Sektion gezeigt hat. Läuft die Quote seither weg,
      // gehört das dazu — sonst empfiehlt sie einen Preis, den es nicht mehr gibt.
      var hp = x.haltePreis, jetzt = x.odd, oddTxt = '';
      if (hp != null) {
        oddTxt = ' <span class="q">@' + (+hp).toFixed(2) + '</span>';
        if (jetzt != null && Math.abs(+jetzt - +hp) >= 0.02) {
          oddTxt += ' <span class="q" style="color:' + ((+jetzt > +hp) ? A.good : A.gold) + '">(jetzt ' +
            (+jetzt).toFixed(2) + ')</span>';
        }
      }
      // Aufbau der Zeile: Spiel + Uhr · dann der PICK als lauteste Zeile (er ist das Produkt) ·
      // darunter das Deckungs-Profil mit dem Zähler, und rechts der Meter für den Geldanteil
      // gegen sein Tor. Der Zustand (läuft/gehalten) steht als ruhiger Text daneben, nicht mehr
      // als Chip zwischen lauter gleich aussehenden Chips.
      return '<div class="md-kl-row' + (x.aktiv ? '' : ' ruht') + '">' +
        '<div class="md-kl-l1">' +
          '<span class="md-kl-nm">' + esc(team(x.home)) + ' <span style="color:var(--mi3);font-weight:400">v</span> ' + esc(team(x.away)) + '</span>' +
          stand + (ko ? '<span class="md-jz-ko">⏱ ' + ko + '</span>' : '') + '</div>' +
        '<div class="md-kl-pick"><span style="color:var(--mi3)">→</span> <b>' + esc(x.name || '—') + '</b>' + oddTxt + '</div>' +
        '<div class="md-kl-deck">' +
          (pkt
            ? '<span class="md-kl-cnt" title="Punkte von möglichen — nicht erhobene Bücher senken den Nenner"'
              + ' style="color:' + PKT_COL(pkt.punkte, pkt.moeglich) + '">' + pkt.punkte + '<i>/' + pkt.moeglich + '</i></span>' + pkt.html
              + (pkt.dauerH != null && pkt.dauerH >= 3 ? '<span class="md-pk-d" title="so lange steht die Übereinstimmung schon vor Anpfiff">⏳ ' + pkt.dauerH.toFixed(1) + 'h</span>' : '')
            : '<span class="md-kl-cnt" title="belegte Ströme von möglichen">' + deck.n + '<i>/' + deck.moeglich + '</i></span>' + deck.html)
          + '</div></div>';
    };
    // Sortiert wird nach PUNKTEN, nicht mehr nach Stufe/Rang: die Frage der Sektion ist „wie viele
    // Bücher sind sich einig", und die Antwort gehört nach oben. Bei Gleichstand entscheidet der
    // Anteil am Möglichen (eine 5/6 ist mehr wert als eine 5/10), dann der Vorlauf.
    var _pktSort = function (arr) {
      return arr.slice().sort(function (a, b) {
        var pa = (a.punkte || {}), pb = (b.punkte || {});
        var d = (pb.punkte || 0) - (pa.punkte || 0);
        if (d) return d;
        var qa = pa.moeglich ? pa.punkte / pa.moeglich : 0, qb = pb.moeglich ? pb.punkte / pb.moeglich : 0;
        if (qb !== qa) return qb - qa;
        return (pb.dauerH || 0) - (pa.dauerH || 0);
      });
    };
    var grp = function (titel, arr) {
      if (!arr.length) return '';
      arr = _pktSort(arr);
      // .md-kl-paar wird erst ab 1040px zum Zweispalter (s. CSS); darunter aendert der Wrapper nichts.
      return '<div class="md-kl-grp">' + titel + '<i></i></div>'
        + '<div class="md-kl-paar">' + arr.map(row).join('') + '</div>';
    };
    // Die Fusszeile sagt, was DIESE Ebene beitraegt — nicht noch einmal, ob freigegeben ist.
    var fuss = 'Ein Buch, das zustimmt, zählt hier doppelt so viel wie ein weiteres Kriterium im selben Buch — '
      + 'gemessen am 01.09. an 500 Plays: Bücher addieren trug (+11,5%), Signale stapeln nicht (−1,1%). '
      + 'Ob man einer Zeile blind folgen darf, beantwortet Ebene 1 — nicht diese Liste.'
      + (st && st.clv != null ? ' Gemessenes Tor: ' + (st.n || 0) + ' abgerechnete Zeilen, CLV '
          + (st.clv >= 0 ? '+' : '') + st.clv.toFixed(1) + 'pp.' : '');
    return ebene(
      grp('🔒 Voll gedeckt — Betfair · Poly · Pinnacle', s1) +
      grp('💷 Betfair-Kern — das gemessene Tor', s2) +
      '<div class="md-kl-foot">' + esc(fuss) + '</div>' + _mdKlBilanz(bil));
  }

  function _mdJetzt(polyPlays) {
    var now = Date.now(), soon = now + 12 * 3600e3, floor = now - 30 * 60000;
    var vsp = ' <span style="color:var(--mi3);font-weight:400">v</span> ';
    var MAJOR = /premier league|la liga|laliga|bundesliga|serie a|ligue 1|eredivisie|primeira liga|championship|major league soccer|\bmls\b|liga mx|s(u|ü)per lig|champions league|europa league|conference league/i;
    var THIN = /qualif|u1[789]|u2[0-3]|reserve|friendl|primera b|segunda|women|frauen|youth|amateur/i;
    var exoticLg = function (lg, anchored) { if (anchored) return false; lg = String(lg || ''); if (THIN.test(lg)) return true; return !MAJOR.test(lg); };
    var mid = function (h, a, id) { return id || (team(h) + team(a)); };
    var _polyMaxInf = (polyPlays || []).reduce(function (a, p) { return Math.max(a, _mdPlayInflow(p)); }, 1);
    var _bfFlowMax = ((_md.data.bfOverview && _md.data.bfOverview.flow) || []).reduce(function (a, x) { return Math.max(a, +x.deltaEur || 0); }, 1);
    var _klk = _klKeys();
    var cand = {};
    var put = function (o) {
      if (isNaN(o.k) || o.k < floor || o.k > soon) return;
      if (o.exotic) o.score -= 14;                 // duenner/exotischer Markt: Signal weniger verlaesslich
      // Deckungs-Abgleich: über matchId ODER Teamnamen — die Flächen liefern nicht dieselbe ID.
      o.gedeckt = o.mk ? (_klk['id:' + o.mk] || _klk['tm:' + o.mk] || 0) : 0;
      var e = cand[o.id];
      if (!e || o.score > e.score) cand[o.id] = o;  // dedup je Spiel: staerkstes Signal gewinnt
    };
    // 1) Engine-Cards: BET-Picks + Poly-Lag — hoechste Autoritaet (durch das Verdikt-Gate gelaufen)
    allFixtures().forEach(function (f) {
      var k = f.kickoff ? Date.parse(String(f.kickoff).replace('Z', '+00:00')) : NaN;
      (f.picks || []).forEach(function (p) {
        var bet = p.verdict === 'BET';
        var lag = (p.signals || []).some(function (s) { return s && s.name === 'steam_lag' && (+s.score || 0) > 0; });
        if (!bet && !lag) return;
        var conv = +p.convictionScore || 0;
        var o = { id: 'x' + mid(f.home, f.away, f.matchId), mk: mid(f.home, f.away, f.matchId), k: k, exotic: false, src: 'card', conv: conv, odd: p.odds,
                  match: esc(fxTeam(f, 'home')) + vsp + esc(fxTeam(f, 'away')), pick: esc(short(p.market || '') || 'Pick') };
        if (bet) { o.score = 60 + conv * 3.5; o.badge = 'BET' + (conv ? ' ' + conv : ''); o.bc = A.good; }
        else { o.score = 48 + conv * 2; o.badge = '⚡ Poly-Lag'; o.bc = A.blue; }
        put(o);
      });
    });
    // 2) Poly-Public-Plays ("Heute spielenswert") — empirisch die staerkste Flaeche (74% Treffer, +ROI).
    (polyPlays || []).forEach(function (r) {
      if (r.verdict !== 'BET' && r.verdict !== 'ABWÄGEN') return;
      var htk = (r.htk == null) ? null : +r.htk, live = (htk != null && htk < 0);
      var k = (htk == null || live) ? now : now + htk * 3600e3;
      if (htk != null && !live && k > soon) return;
      var conv = +r.conv || 0;
      var ico = (typeof _pwSportIcon === 'function') ? _pwSportIcon(r.league) + ' ' : '';
      put({ id: 'p' + (r.key || (r.match || '')), k: k, live: live, exotic: false, odd: null, src: 'poly', poly: r,
        match: esc(String(r.match || '')), pick: esc(r.side || ''),
        score: (r.verdict === 'BET' ? 60 + conv * 3.5 : 48 + conv * 2), bc: A.poly, badge: ico + 'Poly ' + r.verdict });
    });
    // 3) Betfair-Steam — geld-getrieben; plausibel gefiltert, Richtung ehrlich beschriftet
    ((_md.data.bfOverview && _md.data.bfOverview.steam) || []).forEach(function (x) {
      var pp = +x.pp || 0, app = Math.abs(pp);
      if (app < 1.5 || app > 25) return;           // <1.5 kein Signal · >25pp = Platzhalter-Artefakt
      // 29.08.2026 (Lucas-Dump: „Sao Paulo @2.60 · −5,4pp · Quote driftet“ stand als Top-Wette Nr. 3):
      // pp<0 heißt, die Quote LÄUFT WEG — das Geld liegt auf der GEGENSEITE. Für den Frisches-Geld-Block
      // hat Lucas das am 16.08. entschieden (dir==='out' fliegt raus); der Steam-Block hatte dieselbe
      // Regel nie bekommen und empfahl weiter die verlassene Seite. Jetzt gleich an beiden Stellen.
      if (pp < 0) return;                          // driftet = kein Back-Rueckhalt -> keine Top-Wette
      var moneyIn = pp > 0, ex = exoticLg(x.league, false);  // pp>0 = Quote fiel = Geld rein
      // Steam wird immer aus den Match Odds gerechnet (steam_list liest `mo`) -> Eimer ist
      // Liga × Match Odds.
      var trS = _mdBfTrack(x.league, 'Match Odds');
      if (trS && trS.verliert) return;   // dem Geld hier zu folgen verliert historisch -> keine Empfehlung
      put({ id: 'b' + mid(x.home, x.away, x.matchId), mk: mid(x.home, x.away, x.matchId),
        k: x.kickoff ? Date.parse(String(x.kickoff).replace('Z', '+00:00')) : NaN,
        exotic: ex, src: 'bf', odd: x.odd, pp: pp, moneyIn: moneyIn, tr: trS,
        match: esc(team(x.home)) + vsp + esc(team(x.away)), pick: esc(short(x.sideName || '') || '—'),
        score: 42 + Math.min(app, 22) - (moneyIn ? 0 : 8) + (trS && trS.traegt ? 10 : 0), badge: '💷 Steam', bc: A.bf });
    });
    // 3b) Betfair „Frisches Geld" (€) — wo wirklich Geld reinkippt (15.08.2026 Lucas: Steam PLUS Geld).
    ((_md.data.bfOverview && _md.data.bfOverview.flow) || []).forEach(function (x) {
      var dv = +x.deltaEur || 0, od = x.odd;
      if (dv < 2000) return;                                   // Rausch-Untergrenze wie im Radar
      if (od != null && (+od < 1.30 || +od > 15)) return;      // Lock/Longshot raus (wie _mdBfFlowBody)
      if (x.dir === 'out') return;                             // 16.08.2026 (Lucas): driftet = kein Back-Rückhalt → nicht als Geld-Top-Wette (bleibt im Frisches-Geld-Radar, dort als „driftet" markiert)
      var ex = exoticLg(x.league, false);
      var trF = _mdBfTrack(x.league, x.market);
      if (trF && trF.verliert) return;   // s.o. — verlierender Eimer gehört nicht in die Empfehlung
      // 29.08.2026 (Lucas-Checkup): hier stand `k: now`, weil der Zufluss-Feed keinen Anpfiff
      // mitlieferte. Folge: JEDE Betfair-Geld-Zeile zeigte „⏱ 0m" — Liverpool–Forest stand als
      // „Anpfiff jetzt" in der Liste, waehrend der Poly-Block daneben korrekt „in 2h" sagte.
      // Der Anpfiff kommt jetzt aus dem Feed (build_betfair_overview.flow_list); fehlt er,
      // bleibt die Uhr-Chip weg statt eine Zeit zu erfinden.
      put({ id: 'bf' + mid(x.home, x.away, x.matchId), mk: mid(x.home, x.away, x.matchId),
        k: x.kickoff ? Date.parse(String(x.kickoff).replace('Z', '+00:00')) : NaN,
        live: !!_mdBfLiveById(x.matchId),
        exotic: ex, src: 'bfflow', odd: od, deltaEur: dv, nowEur: +x.nowEur || 0, sideName: x.sideName, dir: x.dir,
        match: esc(team(x.home)) + vsp + esc(team(x.away)), pick: esc(short(x.sideName || '') || '—'),
        score: 46 + Math.min(dv / 3000, 20) + (trF && trF.traegt ? 10 : 0), tr: trF, badge: '💷 Geld', bc: A.bf });
    });
    // 4) Money-Map — NUR echte Divergenz (starke Fehlbepreisung).
    ((_md.data.moneyMap && _md.data.moneyMap.rows) || []).forEach(function (r) {
      if (r.verdict !== 'uneinig') return;
      var strong = r.mmStrong;
      if (strong === undefined) { var bs0 = (r.betfair && r.betfair.sharePct) || 0, ps0 = (r.poly && r.poly.sharePct) || 0; strong = bs0 >= 55 && ps0 >= 55; }
      if (!strong) return;
      var ex = !r.pinn;
      put({ id: 'm' + mid(r.home, r.away, r.matchId), mk: mid(r.home, r.away, r.matchId),
        k: r.kickoff ? Date.parse(String(r.kickoff).replace('Z', '+00:00')) : NaN,
        exotic: ex, live: r.live, src: 'mm', odd: null, bf: r.betfair, pl: r.poly,
        match: esc(team(r.home)) + vsp + esc(team(r.away)), pick: 'Divergenz',
        score: 50, badge: '🔗 Divergenz', bc: A.flow });
    });
    // 15.08.2026 (Lucas): Quellen-Diversitaet — je EIN garantierter Platz fuer Betfair + Money-Map.
    var _all = Object.keys(cand).map(function (id) { return cand[id]; })
      .sort(function (a, b) { return b.score - a.score || a.k - b.k; });
    var items = (function () {
      var N = 6, pick = [], used = {};   // 15.08.2026 (Lucas): bis zu 6, damit Betfair (Steam + Geld) + Money-Map reinpassen
      var take = function (x) { if (x && !used[x.id]) { used[x.id] = 1; pick.push(x); } };
      var firstOf = function (s, ok) { for (var i = 0; i < _all.length; i++) { var x = _all[i]; if (x.src === s && (!ok || ok(x))) return x; } return null; };
      // 15.08.2026 (Lucas): Betfair nur reservieren, wenn's was taugt — sonst kein €9K-Draw / duenner Exoten-Steam.
      // 29.08.2026: der garantierte Platz war bedingungslos — eine Betfair-Zeile kam auch dann in
      // die Top-Wetten, wenn ihr Eimer nie etwas getragen hat. Jetzt wird er verdient: reserviert
      // nur, wenn der Liga×Markt-Track ihn stützt ODER (mangels Stichprobe) noch nichts dagegen
      // spricht. Ein Eimer mit belegtem Minus ist oben schon rausgeflogen.
      var reserve = [
        firstOf('bf', function (x) { return !x.exotic && (+x.pp || 0) >= 3; }),   // ordentlicher Steam: >=3pp REIN (Betrag hätte auch Drift reserviert)
        firstOf('bfflow', function (x) { return (+x.deltaEur || 0) >= 30000; }),           // echter Geld-Zufluss (>=EUR30K), kein Mini-Draw
        firstOf('mm')
      ].filter(Boolean);
      var strong = Math.max(0, N - reserve.length);
      for (var i = 0; i < _all.length && pick.length < strong; i++) take(_all[i]);   // staerkste zuerst
      reserve.forEach(take);                                                          // Quellen-Reserve
      for (var j = 0; j < _all.length && pick.length < N; j++) take(_all[j]);          // Rest auffuellen
      return pick.sort(function (a, b) { return b.score - a.score || a.k - b.k; });
    })();
    // Leer heisst leer — aber die Ebene verschwindet NICHT. Eine fehlende dritte Sprosse laesst
    // die Leiter unvollstaendig aussehen und man sucht nach der Sektion, statt die Aussage zu lesen.
    if (!items.length) return '<div id="mdJetztBox">' + _mdEbene(3, 'Was ist gerade das Stärkste?',
      'Rangliste', null,
      'Disjunktion: das stärkste Einzelsignal über alle Flächen. EINE Quelle genügt.',
      'bestes Einzelsignal je Fläche — eine Quelle genügt, kein UND', null,
      '<div class="md-kl-foot" style="border-top:0;padding-top:8px">Gerade kein spielbares Signal in den nächsten Stunden — meldet sich automatisch.</div>') + '</div>';
    // Signal-Balken je Quelle (gleicher Stil wie "Heute spielenswert")
    var sigOf = function (o) {
      if (o.src === 'poly' && o.poly) return _mdSigStrip(o.poly, _polyMaxInf);
      if (o.src === 'bf') {
        var ap = Math.min(Math.abs(+o.pp || 0), 25), val = ((o.pp > 0) ? '+' : '') + (+o.pp).toFixed(1) + 'pp';
        var sub = o.moneyIn ? ('Quote zieht rein' + (o.odd != null ? ' · @' + (+o.odd).toFixed(2) : '')) : 'Quote driftet → Geld auf Gegenseite';
        return '<div class="md-sig">' + _mdSigCell('Betfair-Geld', val, A.bf, ap / 25 * 100, sub) + _mdTrCell(o.tr) + '</div>';
      }
      if (o.src === 'bfflow') {
        var dv = +o.deltaEur || 0, nv = +o.nowEur || 0;
        return '<div class="md-sig">' + _mdSigCell('Betfair-Geld', '+' + eur(dv), A.bf, _bfFlowMax ? dv / _bfFlowMax * 100 : 60, 'jetzt ' + eur(nv) + (o.odd != null ? ' @' + (+o.odd).toFixed(2) : '')) + _mdTrCell(o.tr) + '</div>';
      }
      if (o.src === 'mm') {
        var bs = Math.round((o.bf && o.bf.sharePct) || 0), ps = Math.round((o.pl && o.pl.sharePct) || 0);
        return '<div class="md-sig">' + _mdSigCell('Betfair', bs + '%', A.bf, bs, esc(short((o.bf && o.bf.name) || '—')))
          + _mdSigCell('Poly', ps + '%', A.poly, ps, esc(short((o.pl && o.pl.name) || '—'))) + '</div>';
      }
      var cv = +o.conv || 0;   // card
      return '<div class="md-sig">' + _mdSigCell('Conviction', cv + '/10', A.good, cv * 10, 'Engine-Pick · Verdikt-Gate') + '</div>';
    };
    var _mdTrCell = function (tr) {
      // Was der Track ueber diesen Liga×Markt sagt — dieselbe Sprache wie im Radar.
      if (!tr) return _mdSigMuted('Liga-Track', 'noch zu wenig Historie');
      return _mdSigCell('Liga-Track', (tr.roi >= 0 ? '+' : '') + Math.round(tr.roi * 100) + '%',
        tr.traegt ? A.good : A.gold, Math.min(100, Math.abs(tr.roi) * 400),
        (tr.traegt ? '✅ trägt hier' : '➖ neutral') + ' · n' + tr.n);
    };
    var body = items.map(function (x, i) {
      // Kein Anpfiff bekannt -> gar keine Uhr. Vorher wurde aus NaN/`now` ein „0m", also eine
      // erfundene Angabe an der Stelle, an der man am ehesten hinschaut.
      var min = isFinite(x.k) ? Math.max(0, Math.round((x.k - now) / 60000)) : null;
      var ko = x.live ? 'live'
        : (min == null ? null
          : (min < 60 ? min + 'm' : Math.floor(min / 60) + 'h' + (min % 60 ? ' ' + (min % 60) + 'm' : '')));
      var live = x.live ? '<span class="md-badge" style="background:rgba(229,83,75,.16);color:' + A.red + '">● LIVE</span>' : '';
      var chip = x.exotic ? '<span class="md-badge" style="background:rgba(201,133,0,.14);color:' + A.gold + '" title="dünner/exotischer Markt — Signal weniger verlässlich">dünn</span>' : '';
      var deck = x.gedeckt ? '<span class="md-badge" style="background:rgba(76,194,255,.16);color:#4cc2ff" ' +
        'title="Steht auch oben in Mehrfach gedeckt (Stufe ' + x.gedeckt +
        ') — alle Geld-Bedingungen liegen gleichzeitig an.">🔒 gedeckt</span>' : '';
      var badge = '<span class="md-badge" style="background:rgba(120,130,150,.14);color:' + x.bc + '">' + x.badge + '</span>';
      var oddTxt = (x.odd != null) ? ' <span class="q">@' + (+x.odd).toFixed(2) + '</span>' : '';
      var pickLine = (x.src === 'mm')
        ? '<div class="md-jz-pick md-jz-div"><b style="color:' + A.bf + '">BF</b> ' + esc(short((x.bf && x.bf.name) || '—')) + ' <span style="color:var(--mi3)">vs</span> <b style="color:' + A.poly + '">Poly</b> ' + esc(short((x.pl && x.pl.name) || '—')) + '</div>'
        : '<div class="md-jz-pick"><span style="color:var(--mi3)">→</span> <b>' + (x.pick || '—') + '</b>' + oddTxt + ((x.src === 'bfflow') ? _bfReactiveChip(x.sideName, x.live) : '') + '</div>';
      return '<div class="md-jz-row md-jz-row3">' +
        '<div class="md-jz-l1"><span class="md-jz-n">' + (i + 1) + '</span>' +
        '<span class="md-jz-nm">' + x.match + '</span>' + badge + deck + live + chip +
        (ko ? '<span class="md-jz-ko">⏱ ' + ko + '</span>' : '') + '</div>' +
        pickLine + sigOf(x) + '</div>';
    }).join('');
    // 01.09.2026: Ebene 3 derselben Sektion. Der Kasten behaelt seine id, weil _mdFillJetzt ihn
    // nach dem Poly-Nachladen per outerHTML ersetzt — er muss also allein austauschbar bleiben.
    return '<div id="mdJetztBox">' + _mdEbene(3, 'Was ist gerade das Stärkste?', 'Rangliste', null,
      'Disjunktion: das stärkste Einzelsignal über alle Flächen. EINE Quelle genügt — deshalb steht hier auch an einem schwachen Tag etwas.',
      'bestes Einzelsignal je Fläche — eine Quelle genügt, kein UND · <b>nicht</b> geprüft, nur sortiert',
      null, '<div class="md-jz-paar">' + body + '</div>') + '</div>';
  }
  // ── Die Klammer: „Was kann ich spielen?" ──────────────────────────────────────────────
  // 01.09.2026, Lucas: „jetzt haben wir blindspielbar, mehrfach gedeckt darunter und top wetten
  // jetzt auch darunter … das wirkt jetzt schon sehr oft quasi redundant, oder?"
  //
  // Nachgemessen war die Ueberschneidung NULL: die drei Flaechen zeigten kein einziges gemeinsames
  // Spiel (Register 0 Spiele — es beurteilt Schubladen —, Konjunktion 1, Rangliste 3, Schnitt 0).
  // Redundant war also nicht der Inhalt, sondern der AUFBAU: drei gleich gebaute Sektionen mit je
  // eigenem Kopf, Badge, Bauart-Pille und Erklaersatz, die alle nach derselben Frage klingen.
  //
  // Die drei Antworten unterscheiden sich in DREI Achsen gleichzeitig, und genau das stand nirgends:
  //   Einheit  — Ebene 1 beurteilt Schubladen, Ebene 2+3 einzelne Spiele
  //   Zeit     — Ebene 1 blickt ueber Wochen zurueck, Ebene 2+3 auf die naechsten 12 Stunden
  //   Logik    — Ebene 1 urteilt, Ebene 2 ist ein UND, Ebene 3 ein ODER
  // Deshalb jetzt eine Leiter von streng nach breit unter EINER Ueberschrift. Die Reihenfolge ist
  // die Aussage: je weiter unten, desto mehr steht da — und desto weniger ist es belegt.
  function _mdSpielbar(polyPlays) {
    return '<section class="md-sp md-rise">'
      + '<div class="md-sp-h"><span style="font-size:16px">🎯</span>'
      + '<span class="md-sp-t">Was kann ich spielen?</span>'
      + '<span class="md-sp-s">Drei Ebenen von streng nach breit — <b>je weiter unten, desto mehr steht da '
      + 'und desto weniger ist belegt</b>. Ebene 1 sagt, wie ernst man die beiden darunter nehmen darf.</span></div>'
      + _mdFreigabe() + _mdKiller() + _mdJetzt(polyPlays)
      + '</section>';
  }
  // 13.08.2026 (Lucas): Poly-Public-Plays sind erst async da → Box nach dem Laden mit ihnen neu ranken
  // (ersetzt die synchrone Version ohne Poly). So landen Andres Andrade & Co. korrekt oben.
  function _mdFillJetzt() {
    if (typeof document === 'undefined') return;
    if (typeof _pwEnsurePlaysData !== 'function' || typeof _pwTopPlays !== 'function') return;
    _pwEnsurePlaysData(function () {
      var el = document.getElementById('mdJetztBox'); if (!el) return;
      var plays = []; try { plays = _pwTopPlays(8, null, false) || []; } catch (e) { plays = []; }
      el.outerHTML = _mdJetzt(plays);
    });
  }
  
  window._renderMainDash = _mdRender;
  window._mdState = _md;   // Test-Hook
})();
