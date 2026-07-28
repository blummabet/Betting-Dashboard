/* betfair-radar.js — CocoBet „Betfair Radar" (28.07.2026, Lucas).
 * Schaltzentrale für Betfair-Exchange-Geld über ALLE Fußball-Ligen (via Betwatch).
 * Alles nach Volumen sichtbar, nach Markt + Liga filterbar. Richtung (Back/Lay) aus der
 * Preisbewegung über die Zeit (Betwatch liefert kein Back/Lay getrennt → Netto-Richtung des
 * gematchten Geldes rekonstruiert: Quote verkürzt = gebackt ▼, Quote driftet = gelayt ▲).
 * Liest betfair_prices.json (Snapshot) + betfair_history.json (Zeitreihe). Rein Frontend.
 */
(function () {
  'use strict';

  // ── Märkte, die Lucas will (Voll- + Halbzeit) ──────────────────────────────
  var BF_MARKETS = [
    { id: 'Match Odds',              label: '1X2',      kind: '1x2', grp: 'FT' },
    { id: 'Over/Under 2.5 Goals',    label: 'Ü/U 2.5',  kind: 'ou',  grp: 'FT' },
    { id: 'Over/Under 3.5 Goals',    label: 'Ü/U 3.5',  kind: 'ou',  grp: 'FT' },
    { id: 'Both teams to Score?',    label: 'BTTS',     kind: 'yn',  grp: 'FT' },
    { id: 'Half Time',               label: 'HT 1X2',   kind: '1x2', grp: 'HT' },
    { id: 'First Half Goals 0.5',    label: 'HT Ü0.5',  kind: 'ou',  grp: 'HT' },
    { id: 'First Half Goals 1.5',    label: 'HT Ü1.5',  kind: 'ou',  grp: 'HT' },
  ];
  var MK_BY_ID = {}; BF_MARKETS.forEach(function (m) { MK_BY_ID[m.id] = m; });

  var C = {
    bg: '#0d1117', card: '#161b22', raised: '#1c2330', bd: '#30363d',
    ink: '#e6edf3', mut: '#8b949e', dim: '#6e7681',
    gold: '#ffb80c', vol: '#2dd4bf', back: '#3fb950', lay: '#f85149',
    amber: '#e3b341', live: '#f85149', blue: '#4cc2ff',
  };

  var _bf = { data: null, hist: null, loading: false, market: 'all', league: 'all', sort: 'vol' };
  window._bfState = _bf;

  // ── Laden ──────────────────────────────────────────────────────────────────
  function _bfLoad() {
    if (_bf.data || _bf.loading) return;
    _bf.loading = true;
    Promise.all([
      fetch('betfair_prices.json?t=' + Date.now()).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }),
      fetch('betfair_history.json?t=' + Date.now()).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }),
    ]).then(function (a) {
      _bf.data = a[0] || { matches: [] };
      _bf.hist = a[1] || {};
      _bf.loading = false;
      var p = document.getElementById('betfairRadarPanel');
      if (p && p.style.display !== 'none') p.innerHTML = renderBetfairRadar();
    });
  }
  window._bfLoad = _bfLoad;

  // ── Helpers ─────────────────────────────────────────────────────────────────
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); }
  function usd(n) { n = +n || 0; if (n >= 1e6) return '£' + (n / 1e6).toFixed(2) + 'M'; if (n >= 1e3) return '£' + (n / 1e3).toFixed(0) + 'K'; return '£' + Math.round(n); }
  function mvol(m, key) { var mk = (m.markets || {})[key]; return mk && typeof mk.vol === 'number' ? mk.vol : 0; }
  function odds(m, key) { var mk = (m.markets || {})[key]; return (mk && mk.runners) || {}; }

  // Richtung des Geldes: Preisbewegung der 1X2-Favoritenseite aus der History.
  // Quote runter (verkürzt) = gebackt ▼ ; Quote rauf (driftet) = gelayt ▲.
  function moveOf(m) {
    var h = (_bf.hist || {})[String(m.matchId)];
    if (!Array.isArray(h) || h.length < 2) return null;
    var first = h[0].mo || {}, last = h[h.length - 1].mo || {};
    var best = null;
    ['hw', 'dr', 'aw'].forEach(function (k) {
      var a = first[k], b = last[k];
      if (typeof a === 'number' && typeof b === 'number' && a > 1 && b > 1) {
        var pp = (a - b) / a * 100;               // >0 = verkürzt (gebackt)
        if (!best || Math.abs(pp) > Math.abs(best.pp)) best = { side: k, pp: pp };
      }
    });
    return best;
  }
  function dirBadge(m) {
    var mv = moveOf(m);
    if (!mv || Math.abs(mv.pp) < 1.5) return '<span style="color:' + C.dim + '">—</span>';
    var backed = mv.pp > 0;
    var col = backed ? C.back : C.lay, ar = backed ? '▼' : '▲';
    var lbl = backed ? 'gebackt' : 'gelayt';
    var side = mv.side === 'hw' ? m.home : mv.side === 'aw' ? m.away : 'X';
    return '<span title="' + esc(side) + ' ' + (backed ? 'verkürzt' : 'driftet') + ' ' + Math.abs(mv.pp).toFixed(1) + 'pp → Geld ' + lbl + '" style="color:' + col + ';font-weight:700;white-space:nowrap">' + ar + ' ' + esc(String(side).slice(0, 12)) + '</span>';
  }

  function koStr(m) {
    if (m.liveInfo && (m.liveInfo.time != null) && !m.liveInfo.finished) {
      var t = m.liveInfo.time, ht = m.liveInfo.is_ht ? ' HT' : '';
      var sc = (m.liveInfo.goal_v1 != null) ? (' ' + m.liveInfo.goal_v1 + ':' + m.liveInfo.goal_v2) : '';
      return '<span style="color:' + C.live + ';font-weight:800">● LIVE ' + t + "'" + ht + '</span><span style="color:' + C.mut + '">' + sc + '</span>';
    }
    if (!m.kickoff) return '<span style="color:' + C.dim + '">—</span>';
    var d = new Date(m.kickoff), now = Date.now();
    var h = (d.getTime() - now) / 3.6e6;
    var lbl = h < 0 ? 'gestartet' : h < 1 ? '<1h' : h < 24 ? Math.round(h) + 'h' : d.toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit' });
    var near = h >= 0 && h < 3;
    return '<span style="color:' + (near ? C.amber : C.mut) + '">' + lbl + '</span>';
  }

  // Preis-Zelle je Markt-Typ (kompakt, mit Volumen-Kontext im title)
  function priceCell(m, mkId) {
    var mk = (m.markets || {})[mkId]; if (!mk) return '<td style="text-align:center;color:' + C.dim + '">·</td>';
    var r = mk.runners || {}, def = MK_BY_ID[mkId], v = mvol(m, mkId);
    var inner;
    if (def.kind === '1x2') {
      var hw = r[m.home], dr = r['The Draw'], aw = r[m.away];
      inner = seg(hw) + '<span style="color:' + C.dim + '">/</span>' + seg(dr) + '<span style="color:' + C.dim + '">/</span>' + seg(aw);
    } else if (def.kind === 'ou') {
      var o = pickOU(r, 'Over'), u = pickOU(r, 'Under');
      inner = '<span style="color:' + C.blue + '">O ' + fmtO(o) + '</span> <span style="color:' + C.mut + '">U ' + fmtO(u) + '</span>';
    } else {
      inner = '<span style="color:' + C.back + '">J ' + fmtO(r['Yes']) + '</span> <span style="color:' + C.mut + '">N ' + fmtO(r['No']) + '</span>';
    }
    return '<td title="' + def.label + ' · Volumen ' + usd(v) + '" style="text-align:center;white-space:nowrap;font-size:12px">' + inner + '<div style="margin-top:2px">' + volBar(v, _bf._maxMarketVol || 1) + '</div></td>';
  }
  function seg(o) { return '<b style="color:' + C.ink + '">' + fmtO(o) + '</b>'; }
  function fmtO(o) { return (typeof o === 'number' && o > 1) ? o.toFixed(2) : '–'; }
  function pickOU(r, side) { for (var k in r) { if (k.indexOf(side) === 0) return r[k]; } return null; }
  function volBar(v, max) {
    var w = Math.max(2, Math.round(v / (max || 1) * 100));
    return '<div style="height:4px;border-radius:3px;background:#0b0f14;overflow:hidden"><i style="display:block;height:100%;width:' + w + '%;background:' + C.vol + '"></i></div>';
  }

  // ── KPI-Band ────────────────────────────────────────────────────────────────
  function kpiBand(matches) {
    var totalVol = 0, byLeague = {}, biggest = null;
    matches.forEach(function (m) {
      totalVol += (m.totalVol || 0);
      byLeague[m.league] = (byLeague[m.league] || 0) + (m.totalVol || 0);
      BF_MARKETS.forEach(function (mm) { var v = mvol(m, mm.id); if (!biggest || v > biggest.v) biggest = { v: v, m: m, mk: mm.label }; });
    });
    var topLg = Object.keys(byLeague).sort(function (a, b) { return byLeague[b] - byLeague[a]; })[0];
    var live = matches.filter(function (m) { return m.liveInfo && m.liveInfo.time != null && !m.liveInfo.finished; }).length;
    function card(ic, val, lbl, sub, col) {
      return '<div style="flex:1;min-width:150px;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:12px;padding:13px 15px">' +
        '<div style="font-size:18px">' + ic + '</div>' +
        '<div style="font-size:22px;font-weight:800;color:' + (col || C.ink) + ';line-height:1.15;margin-top:2px">' + val + '</div>' +
        '<div style="font-size:11px;color:' + C.mut + ';margin-top:2px">' + lbl + '</div>' +
        (sub ? '<div style="font-size:10px;color:' + C.dim + ';margin-top:1px">' + sub + '</div>' : '') + '</div>';
    }
    return '<div style="display:flex;gap:10px;flex-wrap:wrap;margin:14px 0">' +
      card('💰', usd(totalVol), 'Betfair-Geld gematcht', matches.length + ' Spiele', C.vol) +
      card('🔴', String(live), 'live', live ? 'gerade am Laufen' : '—', live ? C.live : C.mut) +
      card('🏆', esc(topLg ? String(topLg).slice(0, 22) : '—'), 'Top-Liga nach Geld', topLg ? usd(byLeague[topLg]) : '', C.gold) +
      card('🎯', biggest ? usd(biggest.v) : '—', 'größter Einzelmarkt', biggest ? (biggest.mk + ' · ' + esc(String(biggest.m.home).slice(0, 10))) : '', C.blue) +
      '</div>';
  }

  // ── Filterleiste ────────────────────────────────────────────────────────────
  function filterBar(matches) {
    var chip = function (id, label, active) {
      return '<button onclick="_bfSetMarket(\'' + id + '\')" style="padding:5px 11px;border-radius:9px;border:1px solid ' + (active ? C.gold : C.bd) + ';background:' + (active ? 'rgba(255,184,12,.12)' : 'transparent') + ';color:' + (active ? C.gold : C.mut) + ';font-size:12px;font-weight:700;cursor:pointer">' + label + '</button>';
    };
    var mchips = chip('all', 'Alle Märkte', _bf.market === 'all');
    mchips += '<span style="color:' + C.dim + ';font-size:11px;margin:0 2px">FT</span>';
    BF_MARKETS.filter(function (m) { return m.grp === 'FT'; }).forEach(function (m) { mchips += chip(m.id, m.label, _bf.market === m.id); });
    mchips += '<span style="color:' + C.dim + ';font-size:11px;margin:0 2px">HT</span>';
    BF_MARKETS.filter(function (m) { return m.grp === 'HT'; }).forEach(function (m) { mchips += chip(m.id, m.label, _bf.market === m.id); });
    // Ligen-Dropdown (nach Volumen sortiert)
    var byLg = {}; matches.forEach(function (m) { byLg[m.league] = (byLg[m.league] || 0) + (m.totalVol || 0); });
    var lgs = Object.keys(byLg).sort(function (a, b) { return byLg[b] - byLg[a]; });
    var opts = '<option value="all">Alle Ligen (' + matches.length + ')</option>' + lgs.map(function (l) {
      return '<option value="' + esc(l) + '"' + (_bf.league === l ? ' selected' : '') + '>' + esc(l) + ' · ' + usd(byLg[l]) + '</option>';
    }).join('');
    var lgSel = '<select onchange="_bfSetLeague(this.value)" style="padding:6px 10px;border-radius:9px;border:1px solid ' + C.bd + ';background:' + C.card + ';color:' + C.ink + ';font-size:12px;max-width:260px">' + opts + '</select>';
    return '<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:12px">' + mchips +
      '<span style="flex:1"></span>' + lgSel + '</div>';
  }

  // ── Tabelle ─────────────────────────────────────────────────────────────────
  function table(matches) {
    var single = _bf.market !== 'all';
    var maxTot = matches.reduce(function (a, m) { return Math.max(a, m.totalVol || 0); }, 1);
    _bf._maxMarketVol = matches.reduce(function (a, m) {
      return BF_MARKETS.reduce(function (b, mm) { return Math.max(b, mvol(m, mm.id)); }, a);
    }, 1);
    var cols = single ? [MK_BY_ID[_bf.market]] : BF_MARKETS;
    var head = '<tr style="text-align:left;color:' + C.mut + ';font-size:11px;text-transform:uppercase;letter-spacing:.4px">' +
      '<th style="padding:7px 10px">Liga · Spiel</th><th style="padding:7px 8px">Anpfiff</th>' +
      '<th style="padding:7px 8px;text-align:right">Volumen</th><th style="padding:7px 8px">Geld-Richtung</th>' +
      cols.map(function (c) { return '<th style="padding:7px 8px;text-align:center">' + c.label + '</th>'; }).join('') + '</tr>';
    var rows = matches.map(function (m) {
      var barW = Math.max(3, Math.round((m.totalVol || 0) / maxTot * 100));
      var flag = m.country && m.country !== 'International' ? '' : '';
      var name = '<div style="font-weight:700;color:' + C.ink + '">' + esc(m.home) + ' <span style="color:' + C.dim + '">v</span> ' + esc(m.away) + '</div>' +
        '<div style="font-size:11px;color:' + C.mut + '">' + esc(String(m.league).slice(0, 34)) + '</div>';
      var volCell = '<div style="font-weight:800;color:' + C.vol + ';text-align:right">' + usd(m.totalVol) + '</div>' +
        '<div style="height:5px;border-radius:3px;background:#0b0f14;overflow:hidden;margin-top:3px"><i style="display:block;height:100%;width:' + barW + '%;background:linear-gradient(90deg,' + C.vol + ',#14b8a6)"></i></div>';
      return '<tr style="border-top:1px solid ' + C.bd + '">' +
        '<td style="padding:9px 10px;max-width:280px">' + name + '</td>' +
        '<td style="padding:9px 8px;font-size:12px">' + koStr(m) + '</td>' +
        '<td style="padding:9px 8px;min-width:96px">' + volCell + '</td>' +
        '<td style="padding:9px 8px">' + dirBadge(m) + '</td>' +
        cols.map(function (c) { return priceCell(m, c.id); }).join('') + '</tr>';
    }).join('');
    return '<div style="overflow-x:auto;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px"><table style="width:100%;border-collapse:collapse;font-size:13px"><thead>' + head + '</thead><tbody>' + rows + '</tbody></table></div>';
  }

  // ── Haupt-Render ────────────────────────────────────────────────────────────
  function renderBetfairRadar() {
    var head = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">' +
      '<h1 style="margin:0;font-size:24px;color:' + C.ink + '">🟡 Betfair <span style="color:' + C.gold + '">Radar</span></h1>' +
      '<span style="font-size:11px;color:' + C.mut + '">echtes Exchange-Geld · alle Fußball-Ligen · via Betwatch</span></div>';

    if (_bf.loading && !_bf.data) { _bfLoad(); return head + '<div style="padding:50px;text-align:center;color:' + C.mut + '">⏳ Betfair-Daten werden geladen …</div>'; }
    if (!_bf.data) { _bfLoad(); return head + '<div style="padding:50px;text-align:center;color:' + C.mut + '">⏳ …</div>'; }

    var all = (_bf.data.matches || []).filter(function (m) { return (m.totalVol || 0) > 0 || (m.liveInfo && m.liveInfo.time != null); });
    if (!all.length) {
      return head + '<div style="margin-top:16px;padding:40px 24px;text-align:center;color:' + C.mut + ';font-size:13px;line-height:1.6;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px">Noch keine Betfair-Daten. Sobald der Fetcher (<code>fetch_betfair_betwatch.py</code>) in GitHub Actions läuft, erscheinen hier alle Spiele nach Geld — live &amp; kommend.</div>';
    }
    // Filter: Liga
    var matches = all.slice();
    if (_bf.league !== 'all') matches = matches.filter(function (m) { return m.league === _bf.league; });
    // Filter: Markt (nur Spiele mit Volumen in dem Markt)
    if (_bf.market !== 'all') matches = matches.filter(function (m) { return mvol(m, _bf.market) > 0; });
    // Sortierung: nach relevantem Volumen
    matches.sort(function (a, b) {
      var va = _bf.market === 'all' ? (a.totalVol || 0) : mvol(a, _bf.market);
      var vb = _bf.market === 'all' ? (b.totalVol || 0) : mvol(b, _bf.market);
      return vb - va;
    });
    matches = matches.slice(0, 120);

    var note = '<div style="font-size:11px;color:' + C.dim + ';margin-bottom:10px;line-height:1.5">' +
      '💡 <b style="color:' + C.mut + '">Volumen</b> = £ gematcht auf Betfair (der Money-Indikator). <b style="color:' + C.mut + '">Richtung</b> aus der Preisbewegung: Quote verkürzt = Geld <span style="color:' + C.back + '">gebackt ▼</span>, driftet = <span style="color:' + C.lay + '">gelayt ▲</span> (füllt sich, sobald der Fetcher ein paar Läufe hat).</div>';

    return head + kpiBand(all) + filterBar(all) + note + table(matches) +
      '<div style="text-align:center;color:' + C.dim + ';font-size:11px;margin-top:12px">Stand ' + (_bf.data._meta && _bf.data._meta.generatedAt ? new Date(_bf.data._meta.generatedAt).toLocaleString('de-AT') : '—') + ' · zeigt Top 120 nach Volumen</div>';
  }
  window._renderBetfairRadar = renderBetfairRadar;

  // ── Filter-Handler ──────────────────────────────────────────────────────────
  function rerender() { var p = document.getElementById('betfairRadarPanel'); if (p) p.innerHTML = renderBetfairRadar(); }
  window._bfSetMarket = function (id) { _bf.market = id; rerender(); };
  window._bfSetLeague = function (v) { _bf.league = v; rerender(); };
})();
