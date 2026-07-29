/* betfair-radar.js — CocoBet „Betfair Radar" v4 (29.07.2026, Lucas-Feedback #3).
 * NEU ggü. v3:
 *  · EU-Flagge 🇪🇺 für UEFA-Bewerbe (nicht die Heim-Flagge), 🌍 für sonstige internationale.
 *  · Karten standard EINGEKLAPPT: zeigen komprimiert den geldstärksten Markt; Klick klappt ALLE Märkte auf.
 *  · Hotspot-Leiste zeigt den konkreten AUSGANG (Heim/Über/…) samt € und %, größer.
 *  · Drei Ebenen: Top 5 + MLS · International/UEFA (niedrigere Schwelle) · Rest.
 *  · Beträge in € roh (Betwatch liefert €, keine £-Umrechnung mehr).
 * Liest betfair_prices.json (Runner mit Einzel-Volumen) + betfair_history.json.
 */
(function () {
  'use strict';

  var EURFX = 1.0;  // Betwatch liefert € → keine Umrechnung.

  var MK = [
    { id: 'Match Odds',           label: '1X2',     kind: '1x2', grp: 'FT' },
    { id: 'Over/Under 2.5 Goals', label: 'Ü/U 2.5', kind: 'ou',  grp: 'FT' },
    { id: 'Over/Under 3.5 Goals', label: 'Ü/U 3.5', kind: 'ou',  grp: 'FT' },
    { id: 'Both teams to Score?', label: 'BTTS',    kind: 'yn',  grp: 'FT' },
    { id: 'Half Time',            label: 'HT 1X2',  kind: '1x2', grp: 'HT' },
    { id: 'First Half Goals 0.5', label: 'HT Ü0.5', kind: 'ou',  grp: 'HT' },
    { id: 'First Half Goals 1.5', label: 'HT Ü1.5', kind: 'ou',  grp: 'HT' },
  ];
  var MK_ID = {}; MK.forEach(function (m) { MK_ID[m.id] = m; });

  // Schwellen je Ebene (€). Internationale/UEFA-Quali sind weniger liquide → niedriger.
  var THR = { top: { FT: 10000, HT: 5000 }, intl: { FT: 3000, HT: 1000 }, rest: { FT: 5000, HT: 1500 } };
  var CHIP_FLOOR = 500;

  var C = {
    bg: '#0d1117', card: '#161b22', raised: '#1c2330', bd: '#30363d',
    ink: '#e6edf3', mut: '#8b949e', dim: '#6e7681',
    gold: '#ffb80c', vol: '#2dd4bf', back: '#3fb950', lay: '#f85149',
    amber: '#e3b341', live: '#f85149', blue: '#4cc2ff', purp: '#a78bfa',
  };
  function segCols(n) { return n >= 3 ? [C.vol, C.dim, C.purp] : [C.vol, C.blue]; }

  var UEFA_RX = /(champions league|europa league|europa conference|conference league|uefa)/i;
  // Top 5 + MLS: LAND-qualifizierte Namen verlangen, sonst schnappt „premier league"/„serie a" auch
  // Bhutan/Libanon/Brasilien. Und Freundschafts-/Sommer-/Jugend-Turniere ausschließen (z.B.
  // „English Premier League Summer Series" ist ein Vorbereitungsturnier, keine Liga).
  var TOP5_RX = /(german bundesliga|english premier league|spanish la ?liga|italian serie a|french ligue 1|\bmls\b|major league soccer)/i;
  var TOP5_NEG = /(summer series|friendl|reserve|women|u1[0-9]\b|youth|amateur|\bii\b|\bb\b team)/i;
  function isTop5(league) { var l = String(league || ''); return TOP5_RX.test(l) && !TOP5_NEG.test(l); }
  function isIntlCountry(cc) { return /^(int|international|eu|europe)$/i.test(String(cc || '')); }
  function tierOf(m) {
    if (isTop5(m.league)) return 'top';
    if (UEFA_RX.test(String(m.league || '')) || isIntlCountry(m.country)) return 'intl';
    return 'rest';
  }
  window._bfTier = tierOf;

  var _bf = { data: null, hist: null, loading: false, league: 'all', tab: 'all', date: 'all', cardOpen: {} };
  window._bfState = _bf;

  function _bfLoad() {
    if (_bf.data || _bf.loading) return;
    _bf.loading = true;
    Promise.all([
      fetch('betfair_prices.json?t=' + Date.now()).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }),
      fetch('betfair_history.json?t=' + Date.now()).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }),
    ]).then(function (a) {
      _bf.data = a[0] || { matches: [] }; _bf.hist = a[1] || {}; _bf.loading = false; _bf.cardOpen = {};
      var p = document.getElementById('betfairRadarPanel');
      if (p && p.style.display !== 'none') p.innerHTML = renderBetfairRadar();
    });
  }
  window._bfLoad = _bfLoad;

  // ── Helpers ─────────────────────────────────────────────────────────────────
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]; }); }
  function eur(v) { return (+v || 0) * EURFX; }
  function fmtE(v) { var n = eur(v); if (n >= 1e6) return '€' + (n / 1e6).toFixed(2) + 'M'; if (n >= 1e3) return '€' + (n / 1e3).toFixed(n >= 1e5 ? 0 : 1).replace('.0', '') + 'K'; return '€' + Math.round(n); }
  function mkOf(m, id) { return (m.markets || {})[id] || null; }
  function mvolG(m, id) { var mk = mkOf(m, id); return mk && typeof mk.vol === 'number' ? mk.vol : 0; }
  function totalG(m) { return (m.totalVol || 0); }
  function runnersOf(mk) { var r = mk && mk.runners; return Array.isArray(r) ? r : []; }
  function distTotal(mk) { return runnersOf(mk).reduce(function (a, r) { return a + (+r.vol || 0); }, 0); }
  function leadRunner(mk) { return runnersOf(mk).reduce(function (a, r) { return (!a || (+r.vol || 0) > (+a.vol || 0)) ? r : a; }, null); }
  function fO(o) { return (typeof o === 'number' && o > 1) ? o.toFixed(2) : '–'; }
  function rLabel(name, m) {
    if (name === m.home) return String(m.home);
    if (name === m.away) return String(m.away);
    if (name === 'The Draw') return 'Remis';
    return String(name).replace('Over', 'Ü').replace('Under', 'U').replace(' Goals', '').replace('Yes', 'Ja').replace('No', 'Nein');
  }
  function flag(cc, league) {
    if (UEFA_RX.test(String(league || ''))) return '🇪🇺';       // UEFA-Bewerbe → EU
    cc = String(cc || '').toUpperCase();
    if (isIntlCountry(cc) || cc.length !== 2) return '🌍';       // sonstige internationale → Globus
    var A = 0x1F1E6;
    try { return String.fromCodePoint(A + cc.charCodeAt(0) - 65, A + cc.charCodeAt(1) - 65); } catch (e) { return '🌍'; }
  }

  function genAgeMin() {
    var g = _bf.data && _bf.data._meta && _bf.data._meta.generatedAt;
    if (!g) return 9999;
    var t = Date.parse(g); return isNaN(t) ? 9999 : (Date.now() - t) / 60000;
  }
  // GitHub-Actions-Schedule ist jittery (~8–30 Min statt exakt 15) → Schwellen locker halten,
  // sonst „veraltet"-Alarm bei ganz normalem Betrieb.
  var FRESH_LIVE_MIN = 30;   // bis hierher gilt Live-Status als vertrauenswürdig
  var STALE_WARN_MIN = 45;   // erst ab hier „Daten veraltet"-Banner (≈ 3 verpasste Läufe)
  function isLive(m) { var li = m.liveInfo || {}; if (li.time == null || li.finished) return false; return genAgeMin() <= FRESH_LIVE_MIN; }
  function isStale(m) {
    if (isLive(m)) return false;
    if (!m.kickoff) return false;
    var k = Date.parse(m.kickoff); if (isNaN(k)) return false;
    return (Date.now() - k) > 3 * 3.6e6;
  }
  function qualifies(m) {
    var thr = THR[tierOf(m)] || THR.rest, ftMax = 0, htMax = 0;
    MK.forEach(function (mm) { var v = eur(mvolG(m, mm.id)); if (mm.grp === 'FT') ftMax = Math.max(ftMax, v); else htMax = Math.max(htMax, v); });
    return ftMax >= thr.FT || htMax >= thr.HT;
  }

  // ── Datum ─────────────────────────────────────────────────────────────────
  function dOnly(d) { return d.toLocaleDateString('en-CA'); }
  function matchDateKey(m) { if (isLive(m)) return dOnly(new Date()); var k = Date.parse(m.kickoff); return isNaN(k) ? '' : dOnly(new Date(k)); }
  function dayLabel(key) {
    var today = dOnly(new Date()), tm = dOnly(new Date(Date.now() + 864e5));
    if (key === today) return 'Heute';
    if (key === tm) return 'Morgen';
    var d = new Date(key + 'T12:00:00');
    return d.toLocaleDateString('de-AT', { weekday: 'short', day: '2-digit', month: '2-digit' });
  }
  function dateBar(matches) {
    var keys = {}; matches.forEach(function (m) { var k = matchDateKey(m); if (k) keys[k] = (keys[k] || 0) + 1; });
    var ks = Object.keys(keys).sort();
    if (ks.length < 2) return '';
    var btn = function (val, lbl, n) {
      var on = _bf.date === val;
      return '<button onclick="_bfSetDate(\'' + val + '\')" style="padding:6px 12px;border:1px solid ' + (on ? C.gold : C.bd) + ';border-radius:8px;background:' + (on ? 'rgba(255,184,12,.12)' : 'transparent') + ';color:' + (on ? C.gold : C.mut) + ';font-size:12px;font-weight:700;cursor:pointer">' + lbl + (n != null ? ' <span style="color:' + C.dim + ';font-weight:600">' + n + '</span>' : '') + '</button>';
    };
    return '<div style="display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-bottom:10px">' +
      '<span style="font-size:11px;color:' + C.dim + ';margin-right:2px">📅 Datum</span>' +
      btn('all', 'Alle', matches.length) +
      ks.map(function (k) { return btn(k, dayLabel(k), keys[k]); }).join('') + '</div>';
  }

  // ── Richtung (aus 1X2-Preisbewegung) ────────────────────────────────────────
  function moveOf(m) {
    var h = (_bf.hist || {})[String(m.matchId)];
    if (!Array.isArray(h) || h.length < 2) return null;
    var f = h[0].mo || {}, l = h[h.length - 1].mo || {}, best = null;
    ['hw', 'dr', 'aw'].forEach(function (k) {
      var a = f[k], b = l[k];
      if (typeof a === 'number' && typeof b === 'number' && a > 1 && b > 1) {
        var pp = (a - b) / a * 100;
        if (!best || Math.abs(pp) > Math.abs(best.pp)) best = { side: k, pp: pp };
      }
    });
    return best && Math.abs(best.pp) >= 1.5 ? best : null;
  }
  function dirPill(m) {
    var mv = moveOf(m); if (!mv) return '';
    var backed = mv.pp > 0, col = backed ? C.back : C.lay;
    var side = mv.side === 'hw' ? m.home : mv.side === 'aw' ? m.away : 'Remis';
    var txt = backed ? ('Geld → ' + String(side).slice(0, 14)) : (String(side).slice(0, 14) + ' driftet');
    var tip = backed ? 'Quote fällt = auf diesen Ausgang wird gesetzt (Back). ' : 'Quote steigt = Ausgang wird schwächer, Geld dagegen (Lay). ';
    return '<span title="' + esc(tip) + Math.abs(mv.pp).toFixed(1) + 'pp seit erstem Snapshot" style="display:inline-flex;gap:4px;align-items:center;padding:2px 9px;border-radius:20px;background:' + (backed ? 'rgba(63,185,80,.14)' : 'rgba(248,81,73,.14)') + ';color:' + col + ';font-size:11px;font-weight:800">' + (backed ? '▼' : '▲') + ' ' + esc(txt) + ' <span style="opacity:.7">' + (backed ? 'Quote fällt' : 'Quote steigt') + '</span></span>';
  }
  function koPill(m) {
    if (isLive(m)) {
      var li = m.liveInfo, sc = (li.goal_v1 != null) ? (li.goal_v1 + ':' + li.goal_v2) : '';
      return '<span style="display:inline-flex;gap:4px;align-items:center;padding:2px 8px;border-radius:20px;background:rgba(248,81,73,.15);color:' + C.live + ';font-size:11px;font-weight:800"><span style="width:6px;height:6px;border-radius:50%;background:' + C.live + '"></span>LIVE ' + li.time + "'" + (sc ? ' · ' + sc : '') + '</span>';
    }
    if (!m.kickoff) return '';
    var d = new Date(m.kickoff), h = (d.getTime() - Date.now()) / 3.6e6;
    var lbl = h < 0 ? 'läuft' : h < 1 ? 'in <1h' : h < 12 ? 'in ' + Math.round(h) + 'h' : d.toLocaleDateString('de-AT', { weekday: 'short', day: '2-digit', month: '2-digit' }) + ' ' + d.toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit' });
    var near = h >= 0 && h < 3;
    return '<span style="color:' + (near ? C.amber : C.mut) + ';font-size:12px;font-weight:600">🕐 ' + lbl + '</span>';
  }

  // ── Verteilungs-Balken ──────────────────────────────────────────────────────
  function distBar(mk, slim) {
    var rs = runnersOf(mk), tot = distTotal(mk) || 1, cols = segCols(rs.length);
    var seg = rs.map(function (r, i) { var w = Math.max(0, (+r.vol || 0) / tot * 100); return '<div style="width:' + w + '%;background:' + cols[i % cols.length] + '"></div>'; }).join('');
    return '<div style="display:flex;height:' + (slim ? 7 : 9) + 'px;border-radius:5px;overflow:hidden;background:#0b0f14;gap:1px">' + seg + '</div>';
  }
  function distRows(mk, m) {
    var rs = runnersOf(mk), tot = distTotal(mk) || 1, cols = segCols(rs.length);
    return rs.slice().sort(function (a, b) { return (+b.vol || 0) - (+a.vol || 0); }).map(function (r) {
      var i = rs.indexOf(r), pct = (+r.vol || 0) / tot * 100;
      return '<div style="display:flex;align-items:center;gap:8px;font-size:12px;margin-top:5px">' +
        '<span style="width:9px;height:9px;border-radius:2px;background:' + cols[i % cols.length] + ';flex:none"></span>' +
        '<span style="flex:1;color:' + C.ink + '">' + esc(rLabel(r.name, m)) + '</span>' +
        '<span style="width:38px;text-align:right;font-weight:800;color:' + C.ink + '">' + pct.toFixed(0) + '%</span>' +
        '<span style="width:66px;text-align:right;font-weight:800;color:' + C.vol + '">' + fmtE(r.vol) + '</span>' +
        '<span style="width:44px;text-align:right;color:' + C.mut + '">@' + fO(r.odd) + '</span></div>';
    }).join('');
  }
  // Markt-Block (aufgeklappte Karte): Label + € + Balken + Ausgänge.
  function marketBlock(m, mm) {
    var mk = mkOf(m, mm.id); if (!mk) return '';
    var ht = mm.grp === 'HT';
    return '<div style="padding:8px 0;border-top:1px solid ' + C.bd + '">' +
      '<div style="display:flex;align-items:center;gap:9px">' +
        '<span style="min-width:62px;font-size:11px;font-weight:800;color:' + (ht ? C.purp : C.mut) + '">' + mm.label + '</span>' +
        '<span style="flex:1"></span>' +
        '<span style="font-size:13px;font-weight:800;color:' + C.vol + '">' + fmtE(mvolG(m, mm.id)) + '</span>' +
      '</div>' + distRows(mk, m) + '</div>';
  }
  // Komprimierte Zeile (eingeklappte Karte): geldstärkster Markt + konkreter Ausgang.
  function topLine(m, x) {
    var mk = mkOf(m, x.mm.id), lead = leadRunner(mk), tot = distTotal(mk) || 1;
    var pct = lead ? (+lead.vol || 0) / tot * 100 : 0, ht = x.mm.grp === 'HT';
    return '<div style="display:flex;align-items:center;gap:10px;margin-top:9px;padding-top:9px;border-top:1px solid ' + C.bd + '">' +
      '<span style="min-width:56px;font-size:11px;font-weight:800;color:' + (ht ? C.purp : C.mut) + '">' + x.mm.label + '</span>' +
      '<span style="font-size:12px;color:' + C.ink + ';font-weight:700">→ ' + esc(lead ? rLabel(lead.name, m) : '—') + '</span>' +
      '<span style="font-size:12px;font-weight:900;color:' + C.gold + '">' + pct.toFixed(0) + '%</span>' +
      '<span style="flex:1;max-width:160px">' + distBar(mk, true) + '</span>' +
      '<span style="font-size:13px;font-weight:800;color:' + C.vol + '">' + fmtE(mvolG(m, x.mm.id)) + '</span>' +
      '<span style="font-size:11px;color:' + C.dim + '">▸ alle Märkte</span>' +
    '</div>';
  }

  function presentMarkets(m) {
    return MK.map(function (mm) { return { mm: mm, v: mvolG(m, mm.id) }; })
      .filter(function (x) { return eur(x.v) >= CHIP_FLOOR && distTotal(mkOf(m, x.mm.id)) > 0; })
      .sort(function (a, b) { return b.v - a.v; });
  }

  function matchCard(m, maxTot) {
    var barW = Math.max(4, Math.round(totalG(m) / (maxTot || 1) * 100));
    var mks = presentMarkets(m), open = _bf.cardOpen[m.matchId] === true;
    var inner = mks.length
      ? (open ? mks.map(function (x) { return marketBlock(m, x.mm); }).join('') : topLine(m, mks[0]))
      : '<div style="margin-top:8px;color:' + C.dim + ';font-size:11px">— noch kein nennenswertes Geld je Markt —</div>';
    var chev = open ? '▾' : '▸';
    return '<div id="bfg-' + esc(m.matchId) + '" style="background:' + C.card + ';border:1px solid ' + (open ? C.gold + '55' : C.bd) + ';border-radius:14px;padding:13px 15px;margin-bottom:10px">' +
      '<div onclick="_bfCard(\'' + esc(m.matchId) + '\')" style="cursor:pointer;display:flex;align-items:flex-start;gap:12px;flex-wrap:wrap">' +
        '<div style="flex:1;min-width:230px">' +
          '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">' +
            '<span style="color:' + C.dim + ';font-size:12px;width:10px">' + chev + '</span>' +
            '<span style="font-size:19px;line-height:1">' + flag(m.country, m.league) + '</span>' +
            '<span style="font-weight:800;font-size:15px;color:' + C.ink + '">' + esc(m.home) + ' <span style="color:' + C.dim + ';font-weight:600">v</span> ' + esc(m.away) + '</span>' +
          '</div>' +
          '<div style="display:flex;align-items:center;gap:10px;margin-top:4px;flex-wrap:wrap;padding-left:18px">' +
            '<span style="font-size:11px;color:' + C.mut + '">' + esc(String(m.league).slice(0, 44)) + '</span>' + koPill(m) + dirPill(m) +
          '</div>' +
        '</div>' +
        '<div style="text-align:right;min-width:120px">' +
          '<div style="font-size:20px;font-weight:900;color:' + C.vol + '">' + fmtE(totalG(m)) + '</div>' +
          '<div style="font-size:10px;color:' + C.dim + '">gematchtes Geld</div>' +
          '<div style="height:5px;border-radius:3px;background:#0b0f14;overflow:hidden;margin-top:4px"><i style="display:block;height:100%;width:' + barW + '%;background:linear-gradient(90deg,' + C.vol + ',#14b8a6)"></i></div>' +
        '</div>' +
      '</div>' + inner +
    '</div>';
  }

  function section(matches, title, accent, sub) {
    if (!matches.length) return '';
    var maxTot = matches.reduce(function (a, m) { return Math.max(a, totalG(m)); }, 1);
    return '<div style="margin:6px 0 20px">' +
      '<div style="display:flex;align-items:baseline;gap:10px;margin:0 0 10px;padding-bottom:7px;border-bottom:2px solid ' + accent + '33">' +
        '<h2 style="margin:0;font-size:16px;color:' + accent + '">' + title + '</h2>' +
        '<span style="font-size:11px;color:' + C.dim + '">' + sub + '</span>' +
        '<span style="margin-left:auto;font-size:12px;color:' + C.mut + '">' + matches.length + ' Spiel' + (matches.length === 1 ? '' : 'e') + '</span>' +
      '</div>' + matches.map(function (m) { return matchCard(m, maxTot); }).join('') + '</div>';
  }

  // ── Hotspot-Leiste: konkreter Ausgang mit dem meisten Geld ──────────────────
  function hotspots(matches) {
    var hs = [];
    matches.forEach(function (m) {
      MK.forEach(function (mm) {
        var mk = mkOf(m, mm.id); if (!mk || distTotal(mk) <= 0) return;
        var lead = leadRunner(mk); if (!lead) return;
        var v = eur(lead.vol); if (v < CHIP_FLOOR) return;
        hs.push({ m: m, mm: mm, lead: lead, v: v, pct: (+lead.vol || 0) / (distTotal(mk) || 1) * 100 });
      });
    });
    hs.sort(function (a, b) { return b.v - a.v; });
    return hs.slice(0, 8);
  }
  function hotspotStrip(matches) {
    var hs = hotspots(matches); if (!hs.length) return '';
    var chips = hs.map(function (x) {
      var ht = x.mm.grp === 'HT';
      return '<button onclick="_bfJump(\'' + esc(x.m.matchId) + '\')" style="display:flex;flex-direction:column;gap:2px;padding:9px 13px;border-radius:11px;border:1px solid ' + (ht ? 'rgba(167,139,250,.4)' : C.bd) + ';background:' + C.raised + ';cursor:pointer;text-align:left;min-width:150px">' +
        '<span style="font-size:11px;color:' + C.mut + ';font-weight:700">' + flag(x.m.country, x.m.league) + ' ' + esc(String(x.m.home).slice(0, 11)) + ' – ' + esc(String(x.m.away).slice(0, 11)) + '</span>' +
        '<span style="font-size:13px;color:' + C.ink + ';font-weight:800">' + (ht ? '<span style="color:' + C.purp + '">' + x.mm.label + '</span> ' : x.mm.label + ' ') + '→ ' + esc(rLabel(x.lead.name, x.m)) + '</span>' +
        '<span style="font-size:14px;font-weight:900;color:' + C.vol + '">' + fmtE(x.v) + ' <span style="font-size:11px;color:' + C.gold + '">' + x.pct.toFixed(0) + '%</span> <span style="font-size:10px;color:' + C.dim + '">@' + fO(x.lead.odd) + '</span></span>' +
        '</button>';
    }).join('');
    return '<div style="background:linear-gradient(180deg,rgba(255,184,12,.06),transparent);border:1px solid ' + C.bd + ';border-radius:14px;padding:11px 13px;margin:12px 0 14px">' +
      '<div style="font-size:12px;color:' + C.gold + ';font-weight:800;margin-bottom:8px">🔥 Wo das Geld genau liegt — größte Einzel-Ausgänge <span style="color:' + C.dim + ';font-weight:600">(Klick springt zum Spiel)</span></div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap">' + chips + '</div></div>';
  }

  // ── Info-Band ────────────────────────────────────────────────────────────────
  function tile(ic, val, lbl, sub, col) {
    return '<div style="flex:1;min-width:135px;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:12px;padding:12px 14px">' +
      '<div style="font-size:16px">' + ic + '</div>' +
      '<div style="font-size:20px;font-weight:900;color:' + (col || C.ink) + ';line-height:1.15;margin-top:2px">' + val + '</div>' +
      '<div style="font-size:10.5px;color:' + C.mut + ';margin-top:2px">' + lbl + '</div>' +
      (sub ? '<div style="font-size:9.5px;color:' + C.dim + ';margin-top:1px">' + sub + '</div>' : '') + '</div>';
  }
  function infoBand(groups) {
    var all = groups.top.concat(groups.intl, groups.rest);
    var sumG = function (a) { return a.reduce(function (s, m) { return s + totalG(m); }, 0); };
    var live = all.filter(isLive).length;
    var steam = null;
    all.forEach(function (m) { var mv = moveOf(m); if (mv && (!steam || Math.abs(mv.pp) > Math.abs(steam.mv.pp))) steam = { m: m, mv: mv }; });
    var htBest = null;
    all.forEach(function (m) { var hv = ['Half Time', 'First Half Goals 0.5', 'First Half Goals 1.5'].reduce(function (a, id) { return Math.max(a, mvolG(m, id)); }, 0); if (!htBest || hv > htBest.v) htBest = { m: m, v: hv }; });
    return '<div style="display:flex;gap:9px;flex-wrap:wrap;margin:12px 0 6px">' +
      tile('💰', fmtE(sumG(all)), 'Geld gematcht gesamt', all.length + ' Spiele über Schwelle', C.vol) +
      tile('⭐', fmtE(sumG(groups.top)), 'Top 5 + MLS', groups.top.length + ' Spiele', C.gold) +
      tile('🇪🇺', fmtE(sumG(groups.intl)), 'International / UEFA', groups.intl.length + ' Spiele', C.blue) +
      tile('🔴', String(live), 'live', live ? 'gerade am Laufen' : '—', live ? C.live : C.mut) +
      tile('📈', steam ? (Math.abs(steam.mv.pp).toFixed(1) + 'pp') : '—', 'stärkster Steam', steam ? esc(String(steam.m.home).slice(0, 12)) : '', steam ? (steam.mv.pp > 0 ? C.back : C.lay) : C.mut) +
      tile('⏱️', htBest && htBest.v ? fmtE(htBest.v) : '—', 'meiste HT-Action', htBest && htBest.v ? esc(String(htBest.m.home).slice(0, 12)) : '', C.purp) +
      '</div>';
  }

  function controlBar(all) {
    var by = {}; all.forEach(function (m) { by[m.league] = (by[m.league] || 0) + totalG(m); });
    var lgs = Object.keys(by).sort(function (a, b) { return by[b] - by[a]; });
    var opts = '<option value="all">Alle Ligen</option>' + lgs.map(function (l) { return '<option value="' + esc(l) + '"' + (_bf.league === l ? ' selected' : '') + '>' + esc(l) + ' · ' + fmtE(by[l]) + '</option>'; }).join('');
    var seg = function (id, lbl) { var on = _bf.tab === id; return '<button onclick="_bfSetTab(\'' + id + '\')" style="padding:6px 12px;border:1px solid ' + (on ? C.gold : C.bd) + ';background:' + (on ? 'rgba(255,184,12,.12)' : 'transparent') + ';color:' + (on ? C.gold : C.mut) + ';font-size:12px;font-weight:700;cursor:pointer">' + lbl + '</button>'; };
    return '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px">' +
      '<div style="display:inline-flex;border-radius:9px;overflow:hidden;border:1px solid ' + C.bd + '">' + seg('all', 'Alle') + seg('top', '⭐ Top5+MLS') + seg('intl', '🇪🇺 Int./UEFA') + seg('rest', '🌍 Rest') + '</div>' +
      '<span style="flex:1"></span>' +
      '<button onclick="_bfCards(true)" style="padding:6px 10px;border:1px solid ' + C.bd + ';border-radius:8px;background:transparent;color:' + C.mut + ';font-size:11px;cursor:pointer">alle aufklappen</button>' +
      '<button onclick="_bfCards(false)" style="padding:6px 10px;border:1px solid ' + C.bd + ';border-radius:8px;background:transparent;color:' + C.mut + ';font-size:11px;cursor:pointer">alle zu</button>' +
      '<select onchange="_bfSetLeague(this.value)" style="padding:6px 10px;border-radius:9px;border:1px solid ' + C.bd + ';background:' + C.card + ';color:' + C.ink + ';font-size:12px;max-width:230px">' + opts + '</select>' +
      '</div>';
  }

  function legend() {
    return '<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;font-size:11px;color:' + C.mut + ';background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:10px;padding:8px 12px;margin-bottom:12px">' +
      '<span style="color:' + C.ink + ';font-weight:700">So liest du den Radar:</span>' +
      '<span>Karte klicken → alle Märkte mit Geld-<b>Verteilung</b> (€ + % je Ausgang).</span>' +
      '<span style="color:' + C.back + ';font-weight:700">▼ Quote fällt</span> = auf den Ausgang wird gesetzt (Back).' +
      '<span style="color:' + C.lay + ';font-weight:700">▲ Quote steigt</span> = Ausgang wird schwächer, Geld dagegen (Lay).' +
      '<span style="color:' + C.dim + '">HT-Märkte lila · 🇪🇺 UEFA.</span>' +
      '</div>';
  }

  // ── Haupt-Render ────────────────────────────────────────────────────────────
  function renderBetfairRadar() {
    var head = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap">' +
      '<h1 style="margin:0;font-size:24px;color:' + C.ink + '">🟡 Betfair <span style="color:' + C.gold + '">Radar</span></h1>' +
      '<span style="font-size:11px;color:' + C.mut + '">wo echtes Exchange-Geld liegt · wie es sich verteilt · via Betwatch</span></div>';

    if (!_bf.data) { _bfLoad(); return head + '<div style="padding:50px;text-align:center;color:' + C.mut + '">⏳ Betfair-Daten werden geladen …</div>'; }

    var fresh = (_bf.data.matches || []).filter(function (m) { return !isStale(m); });
    var qAll = fresh.filter(qualifies);

    var q = qAll.slice();
    if (_bf.league !== 'all') q = q.filter(function (m) { return m.league === _bf.league; });
    if (_bf.date !== 'all') q = q.filter(function (m) { return isLive(m) || matchDateKey(m) === _bf.date; });

    var sortV = function (a, b) { return totalG(b) - totalG(a); };
    var groups = {
      top: q.filter(function (m) { return tierOf(m) === 'top'; }).sort(sortV),
      intl: q.filter(function (m) { return tierOf(m) === 'intl'; }).sort(sortV),
      rest: q.filter(function (m) { return tierOf(m) === 'rest'; }).sort(sortV),
    };

    var age = genAgeMin();
    var ageTxt = age > 1440 ? Math.round(age / 1440) + ' Tage' : age >= 90 ? Math.round(age / 60) + 'h' : Math.round(age) + ' Min';
    var stale = age > STALE_WARN_MIN
      ? '<div style="margin:8px 0;padding:9px 13px;border:1px solid #7d4b16;background:#2b1d0e;color:' + C.amber + ';border-radius:10px;font-size:12px">⚠️ <b>Daten sind ' + ageTxt + ' alt</b> — der Fetcher (GitHub Actions) hat länger nicht frisch geschrieben. Live-Status ist ausgeblendet.</div>'
      : '';

    if (!qAll.length) {
      return head + stale + '<div style="margin-top:14px;padding:40px 24px;text-align:center;color:' + C.mut + ';font-size:13px;line-height:1.6;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px">Aktuell kein Spiel über der Geld-Schwelle (' +
        'Top: €10k FT/€5k HT · Int./UEFA: €3k/€1k · Rest: €5k/€1,5k). Sobald irgendwo genug Geld liegt, erscheint es hier.</div>';
    }

    var out = head + infoBand(groups) + hotspotStrip(q) + dateBar(qAll) + controlBar(qAll) + legend() + stale;
    var t = _bf.tab;
    if (t === 'all' || t === 'top') out += section(groups.top, '⭐ Top 5 + MLS', C.gold, '≥ €10k FT · €5k HT');
    if (t === 'all' || t === 'intl') out += section(groups.intl, '🇪🇺 International / UEFA', C.blue, '≥ €3k FT · €1k HT');
    if (t === 'all' || t === 'rest') out += section(groups.rest, '🌍 Rest — andere Ligen', C.purp, '≥ €5k FT · €1,5k HT');
    if (!groups.top.length && !groups.intl.length && !groups.rest.length) {
      out += '<div style="padding:34px;text-align:center;color:' + C.mut + ';font-size:13px;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px">Kein Spiel für diesen Filter. Datum/Liga/Reiter anpassen.</div>';
    }
    out += '<div style="text-align:center;color:' + C.dim + ';font-size:11px;margin-top:6px">Stand ' + (_bf.data._meta && _bf.data._meta.generatedAt ? new Date(_bf.data._meta.generatedAt).toLocaleString('de-AT') : '—') + ' · Beträge in € (Betwatch)</div>';
    return out;
  }
  window._renderBetfairRadar = renderBetfairRadar;

  function rerender() { var p = document.getElementById('betfairRadarPanel'); if (p) p.innerHTML = renderBetfairRadar(); }
  window._bfSetLeague = function (v) { _bf.league = v; rerender(); };
  window._bfSetTab = function (v) { _bf.tab = v; rerender(); };
  window._bfSetDate = function (v) { _bf.date = v; rerender(); };
  window._bfCard = function (mid) { _bf.cardOpen[mid] = !_bf.cardOpen[mid]; rerender(); };
  window._bfCards = function (open) { (_bf.data && _bf.data.matches || []).forEach(function (m) { _bf.cardOpen[m.matchId] = !!open; }); rerender(); };
  window._bfJump = function (mid) { _bf.cardOpen[mid] = true; rerender(); var el = document.getElementById('bfg-' + mid); if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'center' }); };
})();
