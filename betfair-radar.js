/* betfair-radar.js — CocoBet „Betfair Radar" v2 (28.07.2026, Lucas-Feedback).
 * Schaltzentrale für Betfair-Exchange-Geld (via Betwatch). Zwei Sektionen: Top 5 + MLS / Rest.
 * NUR Spiele, wo Geld liegt (Schwellwerte je Sektion). NUR Märkte mit Volumen — keine leeren Quoten.
 * Flaggen vor der Paarung, Beträge in €, Karten statt Tabelle, Richtung (Back/Lay) aus Preisbewegung.
 * Robust gegen veraltete Daten (Stale-Banner, kein Fake-Live). Liest betfair_prices.json + _history.json.
 */
(function () {
  'use strict';

  // £→€ (Betfair matcht in £; Betwatch gibt roh weiter). Faktor leicht anpassbar.
  var GBP_EUR = 1.17;

  // Märkte: Voll- + Halbzeit. grp steuert den Schwellwert (FT vs HT).
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

  // Schwellwerte in € (Lucas): Top5/MLS 10k FT / 5k HT · Rest 5k FT / 1,5k HT.
  var THR = { top: { FT: 10000, HT: 5000 }, rest: { FT: 5000, HT: 1500 } };
  var CHIP_FLOOR = 800;   // Markt-Chip erst ab so viel € zeigen (kein Rauschen)

  var C = {
    bg: '#0d1117', card: '#161b22', raised: '#1c2330', bd: '#30363d',
    ink: '#e6edf3', mut: '#8b949e', dim: '#6e7681',
    gold: '#ffb80c', vol: '#2dd4bf', back: '#3fb950', lay: '#f85149',
    amber: '#e3b341', live: '#f85149', blue: '#4cc2ff', purp: '#a78bfa',
  };

  // Top 5 + MLS erkennen (nach Liga-Namen, robust gegen Schreibvarianten).
  var TOP_RX = /(bundesliga|premier league|la ?liga|serie a|ligue 1|\bmls\b|major league soccer)/i;
  function isTop(league) { return TOP_RX.test(String(league || '')); }

  var _bf = { data: null, hist: null, loading: false, league: 'all', tab: 'both' };
  window._bfState = _bf;

  function _bfLoad() {
    if (_bf.data || _bf.loading) return;
    _bf.loading = true;
    Promise.all([
      fetch('betfair_prices.json?t=' + Date.now()).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }),
      fetch('betfair_history.json?t=' + Date.now()).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }),
    ]).then(function (a) {
      _bf.data = a[0] || { matches: [] }; _bf.hist = a[1] || {}; _bf.loading = false;
      var p = document.getElementById('betfairRadarPanel');
      if (p && p.style.display !== 'none') p.innerHTML = renderBetfairRadar();
    });
  }
  window._bfLoad = _bfLoad;

  // ── Helpers ─────────────────────────────────────────────────────────────────
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); }
  function eur(gbp) { return (+gbp || 0) * GBP_EUR; }
  function fmtE(gbp) { var n = eur(gbp); if (n >= 1e6) return '€' + (n / 1e6).toFixed(2) + 'M'; if (n >= 1e3) return '€' + (n / 1e3).toFixed(n >= 1e5 ? 0 : 1).replace('.0', '') + 'K'; return '€' + Math.round(n); }
  function mvolG(m, id) { var mk = (m.markets || {})[id]; return mk && typeof mk.vol === 'number' ? mk.vol : 0; }  // roh (£)
  function totalG(m) { return (m.totalVol || 0); }
  function flag(cc) {
    cc = String(cc || '').toUpperCase();
    if (cc === 'INT' || cc === 'INTERNATIONAL' || cc === 'EU' || cc.length !== 2) return '🌍';
    var A = 0x1F1E6;
    try { return String.fromCodePoint(A + cc.charCodeAt(0) - 65, A + cc.charCodeAt(1) - 65); } catch (e) { return '🌍'; }
  }

  // Frische: ist der Datensatz aktuell? (gegen „gestern als live")
  function genAgeMin() {
    var g = _bf.data && _bf.data._meta && _bf.data._meta.generatedAt;
    if (!g) return 9999;
    var t = Date.parse(g); return isNaN(t) ? 9999 : (Date.now() - t) / 60000;
  }
  function isLive(m) {
    // nur echtes Live: Runner-Zeit gesetzt, nicht beendet, UND der Datensatz ist frisch (<25 Min).
    var li = m.liveInfo || {};
    if (li.time == null || li.finished) return false;
    if (genAgeMin() > 25) return false;
    return true;
  }
  function isStale(m) {
    // kein Live + Anpfiff deutlich in der Vergangenheit → altes Spiel, raus.
    if (isLive(m)) return false;
    if (!m.kickoff) return false;
    var k = Date.parse(m.kickoff); if (isNaN(k)) return false;
    return (Date.now() - k) > 3 * 3.6e6;   // >3h nach Anpfiff und nicht (frisch) live → vorbei
  }

  function qualifies(m) {
    var top = isTop(m.league), thr = top ? THR.top : THR.rest;
    var ftMax = 0, htMax = 0;
    MK.forEach(function (mm) { var v = eur(mvolG(m, mm.id)); if (mm.grp === 'FT') ftMax = Math.max(ftMax, v); else htMax = Math.max(htMax, v); });
    return ftMax >= thr.FT || htMax >= thr.HT;
  }

  // Richtung des Geldes (aus 1X2-Preisbewegung der History).
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
    return '<span title="' + esc(side) + ' ' + (backed ? 'verkürzt (gebackt)' : 'driftet (gelayt)') + ' ' + Math.abs(mv.pp).toFixed(1) + 'pp" style="display:inline-flex;gap:3px;align-items:center;padding:2px 8px;border-radius:20px;background:' + (backed ? 'rgba(63,185,80,.14)' : 'rgba(248,81,73,.14)') + ';color:' + col + ';font-size:11px;font-weight:800">' + (backed ? '▼' : '▲') + ' ' + esc(String(side).slice(0, 14)) + '</span>';
  }

  function koPill(m) {
    if (isLive(m)) {
      var li = m.liveInfo, sc = (li.goal_v1 != null) ? (li.goal_v1 + ':' + li.goal_v2) : '';
      return '<span style="display:inline-flex;gap:4px;align-items:center;padding:2px 8px;border-radius:20px;background:rgba(248,81,73,.15);color:' + C.live + ';font-size:11px;font-weight:800"><span style="width:6px;height:6px;border-radius:50%;background:' + C.live + '"></span>LIVE ' + li.time + "'" + (sc ? ' · ' + sc : '') + '</span>';
    }
    if (!m.kickoff) return '';
    var d = new Date(m.kickoff), h = (d.getTime() - Date.now()) / 3.6e6;
    var lbl = h < 0 ? 'läuft' : h < 1 ? 'in <1h' : h < 24 ? 'in ' + Math.round(h) + 'h' : d.toLocaleDateString('de-AT', { weekday: 'short', day: '2-digit', month: '2-digit' }) + ' ' + d.toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit' });
    var near = h >= 0 && h < 3;
    return '<span style="color:' + (near ? C.amber : C.mut) + ';font-size:12px;font-weight:600">🕐 ' + lbl + '</span>';
  }

  // Markt-Chips: nur Märkte mit Volumen ≥ CHIP_FLOOR, nach € sortiert.
  function chips(m) {
    var arr = MK.map(function (mm) { return { mm: mm, v: mvolG(m, mm.id) }; })
      .filter(function (x) { return eur(x.v) >= CHIP_FLOOR; })
      .sort(function (a, b) { return b.v - a.v; });
    if (!arr.length) return '<span style="color:' + C.dim + ';font-size:11px">— noch kein nennenswertes Geld je Markt —</span>';
    return arr.map(function (x) {
      var mk = (m.markets || {})[x.mm.id] || {}, r = mk.runners || {}, o = '';
      if (x.mm.kind === '1x2') { var hw = r[m.home], dr = r['The Draw'], aw = r[m.away]; o = fO(hw) + '·' + fO(dr) + '·' + fO(aw); }
      else if (x.mm.kind === 'ou') { o = 'O' + fO(pk(r, 'Over')) + ' U' + fO(pk(r, 'Under')); }
      else { o = 'J' + fO(r['Yes']) + ' N' + fO(r['No']); }
      var ht = x.mm.grp === 'HT';
      return '<span title="' + x.mm.label + ' · ' + o + '" style="display:inline-flex;flex-direction:column;gap:1px;padding:5px 9px;border-radius:9px;background:' + C.raised + ';border:1px solid ' + (ht ? 'rgba(167,139,250,.35)' : C.bd) + '">' +
        '<span style="font-size:10px;color:' + (ht ? C.purp : C.mut) + ';font-weight:700">' + x.mm.label + '</span>' +
        '<span style="font-size:13px;font-weight:800;color:' + C.vol + '">' + fmtE(x.v) + '</span>' +
        '<span style="font-size:10px;color:' + C.dim + '">' + o + '</span></span>';
    }).join('');
  }
  function fO(o) { return (typeof o === 'number' && o > 1) ? o.toFixed(2) : '–'; }
  function pk(r, s) { for (var k in r) if (k.indexOf(s) === 0) return r[k]; return null; }

  // Eine Match-Karte.
  function matchCard(m, maxTot) {
    var barW = Math.max(4, Math.round(totalG(m) / (maxTot || 1) * 100));
    return '<div style="background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px;padding:13px 15px;margin-bottom:10px">' +
      '<div style="display:flex;align-items:flex-start;gap:12px;flex-wrap:wrap">' +
        '<div style="flex:1;min-width:220px">' +
          '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">' +
            '<span style="font-size:19px;line-height:1">' + flag(m.country) + '</span>' +
            '<span style="font-weight:800;font-size:15px;color:' + C.ink + '">' + esc(m.home) + ' <span style="color:' + C.dim + ';font-weight:600">v</span> ' + esc(m.away) + '</span>' +
          '</div>' +
          '<div style="display:flex;align-items:center;gap:10px;margin-top:4px">' +
            '<span style="font-size:11px;color:' + C.mut + '">' + esc(String(m.league).slice(0, 40)) + '</span>' + koPill(m) + dirPill(m) +
          '</div>' +
        '</div>' +
        '<div style="text-align:right;min-width:120px">' +
          '<div style="font-size:20px;font-weight:900;color:' + C.vol + '">' + fmtE(totalG(m)) + '</div>' +
          '<div style="font-size:10px;color:' + C.dim + '">gematchtes Geld</div>' +
          '<div style="height:5px;border-radius:3px;background:#0b0f14;overflow:hidden;margin-top:4px"><i style="display:block;height:100%;width:' + barW + '%;background:linear-gradient(90deg,' + C.vol + ',#14b8a6)"></i></div>' +
        '</div>' +
      '</div>' +
      '<div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:11px">' + chips(m) + '</div>' +
    '</div>';
  }

  // Sektion (Top5+MLS oder Rest).
  function section(matches, title, accent, sub) {
    var maxTot = matches.reduce(function (a, m) { return Math.max(a, totalG(m)); }, 1);
    var body = matches.length
      ? matches.map(function (m) { return matchCard(m, maxTot); }).join('')
      : '<div style="padding:26px;text-align:center;color:' + C.dim + ';font-size:12px;background:' + C.card + ';border:1px dashed ' + C.bd + ';border-radius:14px">Kein Spiel über der Geld-Schwelle — hier taucht nur auf, wo wirklich Geld liegt.</div>';
    return '<div style="margin:6px 0 20px">' +
      '<div style="display:flex;align-items:baseline;gap:10px;margin:0 0 10px;padding-bottom:7px;border-bottom:2px solid ' + accent + '33">' +
        '<h2 style="margin:0;font-size:16px;color:' + accent + '">' + title + '</h2>' +
        '<span style="font-size:11px;color:' + C.dim + '">' + sub + '</span>' +
        '<span style="margin-left:auto;font-size:12px;color:' + C.mut + '">' + matches.length + ' Spiel' + (matches.length === 1 ? '' : 'e') + '</span>' +
      '</div>' + body + '</div>';
  }

  // ── Info-Band (ausgebaut) ─────────────────────────────────────────────────
  function tile(ic, val, lbl, sub, col) {
    return '<div style="flex:1;min-width:135px;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:12px;padding:12px 14px">' +
      '<div style="font-size:16px">' + ic + '</div>' +
      '<div style="font-size:20px;font-weight:900;color:' + (col || C.ink) + ';line-height:1.15;margin-top:2px">' + val + '</div>' +
      '<div style="font-size:10.5px;color:' + C.mut + ';margin-top:2px">' + lbl + '</div>' +
      (sub ? '<div style="font-size:9.5px;color:' + C.dim + ';margin-top:1px">' + sub + '</div>' : '') + '</div>';
  }
  function infoBand(top, rest) {
    var all = top.concat(rest);
    var sumG = function (a) { return a.reduce(function (s, m) { return s + totalG(m); }, 0); };
    var live = all.filter(isLive).length;
    // stärkster Steam (Betrag der Richtung × Volumen-Rang)
    var steam = null;
    all.forEach(function (m) { var mv = moveOf(m); if (mv && (!steam || Math.abs(mv.pp) > Math.abs(steam.mv.pp))) steam = { m: m, mv: mv }; });
    // meiste HT-Action
    var htBest = null;
    all.forEach(function (m) { var hv = ['Half Time', 'First Half Goals 0.5', 'First Half Goals 1.5'].reduce(function (a, id) { return Math.max(a, mvolG(m, id)); }, 0); if (!htBest || hv > htBest.v) htBest = { m: m, v: hv }; });
    return '<div style="display:flex;gap:9px;flex-wrap:wrap;margin:12px 0 16px">' +
      tile('💰', fmtE(sumG(all)), 'Geld gematcht gesamt', all.length + ' Spiele über Schwelle', C.vol) +
      tile('⭐', fmtE(sumG(top)), 'Top 5 + MLS', top.length + ' Spiele', C.gold) +
      tile('🌍', fmtE(sumG(rest)), 'Rest (alle Ligen)', rest.length + ' Spiele', C.blue) +
      tile('🔴', String(live), 'live', live ? 'gerade am Laufen' : '—', live ? C.live : C.mut) +
      tile('📈', steam ? (Math.abs(steam.mv.pp).toFixed(1) + 'pp') : '—', 'stärkster Steam', steam ? esc(String(steam.m.home).slice(0, 12)) : '', steam ? (steam.mv.pp > 0 ? C.back : C.lay) : C.mut) +
      tile('⏱️', htBest && htBest.v ? fmtE(htBest.v) : '—', 'meiste HT-Action', htBest && htBest.v ? esc(String(htBest.m.home).slice(0, 12)) : '', C.purp) +
      '</div>';
  }

  function leagueBar(all) {
    var by = {}; all.forEach(function (m) { by[m.league] = (by[m.league] || 0) + totalG(m); });
    var lgs = Object.keys(by).sort(function (a, b) { return by[b] - by[a]; });
    var opts = '<option value="all">Alle Ligen</option>' + lgs.map(function (l) { return '<option value="' + esc(l) + '"' + (_bf.league === l ? ' selected' : '') + '>' + esc(l) + ' · ' + fmtE(by[l]) + '</option>'; }).join('');
    var seg = function (id, lbl) { var on = _bf.tab === id; return '<button onclick="_bfSetTab(\'' + id + '\')" style="padding:6px 13px;border:1px solid ' + (on ? C.gold : C.bd) + ';background:' + (on ? 'rgba(255,184,12,.12)' : 'transparent') + ';color:' + (on ? C.gold : C.mut) + ';font-size:12px;font-weight:700;cursor:pointer">' + lbl + '</button>'; };
    return '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:14px">' +
      '<div style="display:inline-flex;border-radius:9px;overflow:hidden;border:1px solid ' + C.bd + '">' + seg('both', 'Beide') + seg('top', '⭐ Top 5 + MLS') + seg('rest', '🌍 Rest') + '</div>' +
      '<span style="flex:1"></span>' +
      '<select onchange="_bfSetLeague(this.value)" style="padding:6px 10px;border-radius:9px;border:1px solid ' + C.bd + ';background:' + C.card + ';color:' + C.ink + ';font-size:12px;max-width:250px">' + opts + '</select>' +
      '</div>';
  }

  // ── Haupt-Render ────────────────────────────────────────────────────────────
  function renderBetfairRadar() {
    var head = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap">' +
      '<h1 style="margin:0;font-size:24px;color:' + C.ink + '">🟡 Betfair <span style="color:' + C.gold + '">Radar</span></h1>' +
      '<span style="font-size:11px;color:' + C.mut + '">wo echtes Exchange-Geld liegt · alle Fußball-Ligen · via Betwatch</span></div>';

    if (!_bf.data) { _bfLoad(); return head + '<div style="padding:50px;text-align:center;color:' + C.mut + '">⏳ Betfair-Daten werden geladen …</div>'; }

    // frische, nicht-veraltete Spiele
    var live0 = (_bf.data.matches || []).filter(function (m) { return !isStale(m); });
    var q = live0.filter(qualifies);
    if (_bf.league !== 'all') q = q.filter(function (m) { return m.league === _bf.league; });

    var top = q.filter(function (m) { return isTop(m.league); }).sort(function (a, b) { return totalG(b) - totalG(a); });
    var rest = q.filter(function (m) { return !isTop(m.league); }).sort(function (a, b) { return totalG(b) - totalG(a); });

    var stale = genAgeMin() > 30
      ? '<div style="margin:8px 0;padding:9px 13px;border:1px solid #7d4b16;background:#2b1d0e;color:' + C.amber + ';border-radius:10px;font-size:12px">⚠️ <b>Daten sind ' + (genAgeMin() > 1440 ? Math.round(genAgeMin() / 1440) + ' Tage' : Math.round(genAgeMin() / 60) + 'h') + ' alt</b> — der Fetcher (GitHub Actions, alle 15 Min) hat noch nicht frisch geschrieben. Live-Status ist deshalb ausgeblendet.</div>'
      : '';

    if (!top.length && !rest.length) {
      return head + stale + '<div style="margin-top:14px;padding:40px 24px;text-align:center;color:' + C.mut + ';font-size:13px;line-height:1.6;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px">Aktuell kein Spiel über der Geld-Schwelle (' +
        'Top 5/MLS: €10k FT / €5k HT · Rest: €5k FT / €1,5k HT). Sobald irgendwo genug Geld liegt, erscheint es hier — nach Volumen, mit Flagge und den Märkten, die zählen.</div>';
    }

    var note = '<div style="font-size:11px;color:' + C.dim + ';margin:2px 0 4px;line-height:1.5">Nur Spiele <b style="color:' + C.mut + '">über der Geld-Schwelle</b>, sortiert nach € · nur Märkte mit Geld · ' +
      '<span style="color:' + C.back + '">▼ gebackt</span> / <span style="color:' + C.lay + '">▲ gelayt</span> aus der Preisbewegung · HT-Chips lila umrandet.</div>';

    var out = head + infoBand(top, rest) + leagueBar(live0.filter(qualifies)) + note + stale;
    if (_bf.tab !== 'rest') out += section(top, '⭐ Top 5 + MLS', C.gold, '≥ €10k FT · €5k HT');
    if (_bf.tab !== 'top') out += section(rest, '🌍 Rest — alle anderen Ligen', C.blue, '≥ €5k FT · €1,5k HT');
    out += '<div style="text-align:center;color:' + C.dim + ';font-size:11px;margin-top:6px">Stand ' + (_bf.data._meta && _bf.data._meta.generatedAt ? new Date(_bf.data._meta.generatedAt).toLocaleString('de-AT') : '—') + ' · Beträge ≈ € (aus £ ×' + GBP_EUR + ')</div>';
    return out;
  }
  window._renderBetfairRadar = renderBetfairRadar;

  function rerender() { var p = document.getElementById('betfairRadarPanel'); if (p) p.innerHTML = renderBetfairRadar(); }
  window._bfSetLeague = function (v) { _bf.league = v; rerender(); };
  window._bfSetTab = function (v) { _bf.tab = v; rerender(); };
})();
