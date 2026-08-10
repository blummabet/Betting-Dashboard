// pinnacle-poly.js — „Pinnacle × Poly" Lag-Sheet (Phase 2, 04.08.2026 Lucas)
// Liest pinnacle_poly_scan.json (Zeit-Snapshots je Spiel, gepaart Pinnacle-fair vs Poly-Preis)
// und rechnet zwei Dinge:
//   A) Aktuelle Edge je Spiel/Liga — wo ist Poly GERADE ggü. Pinnacle fehlbepreist (ab 1 Snapshot).
//   B) Round-Trip-Backtest — Einstieg auf Polys nachhinkendem Preis bei einem Pinnacle-Move,
//      Ausstieg wenn Poly konvergiert. Realisiert = wie viel der Vorsprung eingebracht hätte.
// Liga-Zeilen aufklappbar zu den Einzelspielen. Reines Messen — keine Order, kein Trade.
(function () {
  'use strict';

  // Tunbare Schwellen (später ggf. als UI-Regler) ---------------------------------------------
  var ENTRY_EDGE = 3.0;   // pp: ab so viel Edge (Pinnacle-fair − Poly) gilt ein Einstieg
  var EXIT_EDGE  = 1.0;   // pp: darunter gilt Poly als konvergiert → Ausstieg
  var MOVE_MIN   = 1.5;   // pp: Pinnacle-Bewegung (Wkt steigt = Quote fällt), die den Einstieg triggert
  var MIN_SNAPS_BT = 4;   // ab so vielen Snapshots/Spiel ist der Backtest überhaupt aussagekräftig
  var VOL_MIN = 50;       // Poly-Buch unter so viel Volumen = kein echter Preis (Hygiene-Gate 10.08.2026)

  // 10.08.2026 (Lucas): Hygiene-Gate gegen Backtest-Datenmüll — spiegelt _snap_valid in
  // poly_pinnacle_scan.py. Reinigt SOFORT auch die bereits gesammelten Snapshots: nur zählen,
  // wenn (1) echtes Poly-Volumen, (2) sauberer Pinnacle-Fair (Summe ~1), (3) Poly & Pinnacle
  // einig, wer Favorit ist. 96% der alten „Edges" waren leere Bücher oder Fehlmatches.
  function _argmax3(a) { return a[0] >= a[1] ? (a[0] >= a[2] ? 0 : 2) : (a[1] >= a[2] ? 1 : 2); }
  function _validSnap(s) {
    if (!s || !s.pinn || !s.poly || s.pinn.length !== 3 || s.poly.length !== 3) return false;
    if ((s.vol || 0) <= VOL_MIN) return false;
    for (var i = 0; i < 3; i++) { if (s.pinn[i] == null || s.poly[i] == null) return false; }
    var sum = s.pinn[0] + s.pinn[1] + s.pinn[2];
    if (sum < 0.95 || sum > 1.05) return false;
    return _argmax3(s.pinn) === _argmax3(s.poly);
  }

  var C = {
    card: '#161b22', bd: '#21262d', ink: '#e6edf3', mut: '#9aa5b1', dim: '#6b7684',
    good: '#3fb950', red: '#f85149', gold: '#ffb80c', teal: '#5eead4', blue: '#4cc2ff'
  };
  var OUT = ['Heim', 'Remis', 'Auswärts'];

  var _pp = { data: null, open: null, sort: 'edge', loading: false };

  function _esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function _pct(x) { return (x == null ? '–' : (x * 100).toFixed(0) + '%'); }
  function _pp1(x) { return (x >= 0 ? '+' : '') + x.toFixed(1); }
  function _edgeCol(pp) {
    if (pp >= ENTRY_EDGE) return C.good;
    if (pp >= 1) return '#7ee0a0';
    if (pp <= -ENTRY_EDGE) return C.red;
    if (pp <= -1) return '#f0a6a1';
    return C.dim;
  }
  function _minAgo(a, b) {
    var t0 = Date.parse(a), t1 = Date.parse(b);
    if (isNaN(t0) || isNaN(t1)) return null;
    return Math.round((t1 - t0) / 60000);
  }

  // ── B) Round-Trip-Backtest über die Snapshots eines Spiels ─────────────────────────────────
  // Für jeden Ausgang (0/1/2) chronologisch: Einstieg wenn Pinnacle hochzieht (Move≥MOVE_MIN) und
  // Poly noch ≥ENTRY_EDGE darunter liegt; Ausstieg wenn Edge auf ≤EXIT_EDGE konvergiert.
  function _backtest(snaps) {
    var trips = [];
    if (!snaps || snaps.length < 2) return trips;
    for (var o = 0; o < 3; o++) {
      var pos = null;
      for (var i = 1; i < snaps.length; i++) {
        var s = snaps[i], sp = snaps[i - 1];
        if (!s.pinn || !s.poly || !sp.pinn) continue;
        var pinnNow = s.pinn[o], polyNow = s.poly[o], pinnPrev = sp.pinn[o];
        if (pinnNow == null || polyNow == null || pinnPrev == null) continue;
        var edge = (pinnNow - polyNow) * 100;
        var move = (pinnNow - pinnPrev) * 100;
        if (!pos) {
          if (move >= MOVE_MIN && edge >= ENTRY_EDGE) {
            pos = { o: o, tsIn: s.ts, polyIn: polyNow, edgeIn: edge, pinnIn: pinnNow };
          }
        } else {
          if (edge <= EXIT_EDGE) {
            trips.push({ o: o, tsIn: pos.tsIn, tsOut: s.ts, edgeIn: pos.edgeIn,
              realized: (polyNow - pos.polyIn) * 100, converged: true,
              mins: _minAgo(pos.tsIn, s.ts) });
            pos = null;
          }
        }
      }
      if (pos) {  // bis zum letzten Snapshot nicht konvergiert → offen
        var last = snaps[snaps.length - 1];
        trips.push({ o: o, tsIn: pos.tsIn, tsOut: last.ts, edgeIn: pos.edgeIn,
          realized: (last.poly[o] - pos.polyIn) * 100, converged: false,
          mins: _minAgo(pos.tsIn, last.ts) });
      }
    }
    return trips;
  }

  // Aktuelle Edge (letzter Snapshot): beste Fehlbepreisung + Seite
  function _curEdge(snaps) {
    if (!snaps || !snaps.length) return null;
    var s = snaps[snaps.length - 1];
    if (!s.pinn || !s.poly) return null;
    var best = { pp: -99, o: 0 };
    for (var o = 0; o < 3; o++) {
      if (s.pinn[o] == null || s.poly[o] == null) continue;
      var pp = (s.pinn[o] - s.poly[o]) * 100;
      if (pp > best.pp) best = { pp: pp, o: o };
    }
    return { pp: best.pp, o: best.o, pinn: s.pinn, poly: s.poly, vol: s.vol, book: s.book, ts: s.ts };
  }

  // Aggregation je Liga ------------------------------------------------------------------------
  function _leagues() {
    var games = (_pp.data && _pp.data.games) || {};
    var by = {};
    var totalSnaps = 0;
    Object.keys(games).forEach(function (k) {
      var g = games[k];
      var snaps = (g.snaps || []).filter(_validSnap);   // 10.08.2026 (Lucas): nur saubere Snapshots in Edge/Backtest
      totalSnaps += snaps.length;
      var cur = _curEdge(snaps);
      var trips = _backtest(snaps);
      var L = by[g.league] || (by[g.league] = { league: g.league, games: [], trips: [], maxEdge: -99, sumEdge: 0, nEdge: 0, snaps: 0 });
      L.games.push({ key: k, home: g.home, away: g.away, kickoff: g.kickoff, snaps: snaps, cur: cur, trips: trips });
      L.trips = L.trips.concat(trips);
      L.snaps += snaps.length;
      if (cur) { L.maxEdge = Math.max(L.maxEdge, cur.pp); L.sumEdge += cur.pp; L.nEdge++; }
    });
    var arr = Object.keys(by).map(function (n) {
      var L = by[n];
      var conv = L.trips.filter(function (t) { return t.converged; });
      var wins = L.trips.filter(function (t) { return t.realized > 0; });
      L.avgEdge = L.nEdge ? L.sumEdge / L.nEdge : null;
      L.nTrips = L.trips.length;
      L.hit = L.nTrips ? Math.round(wins.length / L.nTrips * 100) : null;
      L.avgReal = L.nTrips ? L.trips.reduce(function (a, t) { return a + t.realized; }, 0) / L.nTrips : null;
      L.nConv = conv.length;
      return L;
    });
    arr.sort(function (a, b) {
      if (_pp.sort === 'trips') return b.nTrips - a.nTrips || b.maxEdge - a.maxEdge;
      return b.maxEdge - a.maxEdge;
    });
    return { arr: arr, totalSnaps: totalSnaps };
  }

  function _statTile(label, val, col) {
    return '<div style="flex:1;min-width:96px;background:' + C.card + ';border:1px solid ' + C.bd +
      ';border-radius:10px;padding:9px 11px"><div style="font-size:18px;font-weight:800;color:' + (col || C.ink) + '">' +
      val + '</div><div style="font-size:10px;color:' + C.dim + '">' + label + '</div></div>';
  }

  function _gameRow(g) {
    var c = g.cur;
    var edgeChip = c ? '<span style="color:' + _edgeCol(c.pp) + ';font-weight:800">' + _pp1(c.pp) + 'pp</span>' +
      ' <span style="color:' + C.dim + ';font-size:11px">' + OUT[c.o] + '</span>' : '<span style="color:' + C.dim + '">–</span>';
    var pinnPoly = c ? '<div style="font-size:11px;color:' + C.mut + ';margin-top:3px">' +
      OUT.map(function (o, i) { return o[0] + ' <b style="color:' + C.teal + '">' + _pct(c.poly[i]) + '</b>/' +
        '<span style="color:' + C.gold + '">' + _pct(c.pinn[i]) + '</span>'; }).join(' · ') +
      ' <span style="color:' + C.dim + '">(Poly/Pinn' + (c.book && c.book !== 'pinnacle' ? '·' + _esc(c.book) : '') + ')</span></div>' : '';
    var bt = '';
    if (g.trips.length) {
      bt = '<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:5px">' + g.trips.map(function (t) {
        var col = t.realized > 0 ? C.good : (t.realized < 0 ? C.red : C.dim);
        return '<span style="font-size:10.5px;border:1px solid ' + col + '55;border-radius:6px;padding:1px 6px;color:' + col + '">' +
          OUT[t.o] + ' ' + _pp1(t.realized) + 'pp' + (t.converged ? '' : ' ⧖') +
          (t.mins != null ? ' <span style="color:' + C.dim + '">' + t.mins + 'm</span>' : '') + '</span>';
      }).join('') + '</div>';
    }
    var ko = g.kickoff ? new Date(g.kickoff) : null;
    var koStr = ko && !isNaN(ko) ? ko.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
    return '<div style="padding:9px 4px;border-top:1px solid ' + C.bd + '">' +
      '<div style="display:flex;justify-content:space-between;gap:10px;align-items:baseline">' +
      '<div style="font-weight:700;color:' + C.ink + ';font-size:13px">' + _esc(g.home) + ' <span style="color:' + C.dim + '">v</span> ' + _esc(g.away) +
      ' <span style="color:' + C.dim + ';font-weight:400;font-size:11px">' + koStr + ' · ' + g.snaps.length + ' Snaps</span></div>' +
      '<div style="text-align:right;white-space:nowrap">' + edgeChip + '</div></div>' +
      pinnPoly + bt + '</div>';
  }

  function _leagueRow(L) {
    var open = _pp.open === L.league;
    var btSummary = L.nTrips
      ? '<span style="color:' + C.ink + '">' + L.nTrips + ' Trips</span> · <span style="color:' + (L.hit >= 50 ? C.good : C.mut) + '">' + L.hit + '% Treffer</span> · <span style="color:' + _edgeCol(L.avgReal) + '">' + _pp1(L.avgReal) + 'pp Ø</span>'
      : '<span style="color:' + C.dim + '">— sammelt</span>';
    var head = '<div onclick="_ppToggle(\'' + _esc(L.league).replace(/'/g, "\\'") + '\')" style="cursor:pointer;display:flex;align-items:center;gap:12px;padding:11px 13px">' +
      '<span style="color:' + C.dim + ';width:10px">' + (open ? '▾' : '▸') + '</span>' +
      '<div style="flex:1;min-width:150px"><div style="font-weight:800;color:' + C.ink + ';font-size:14px">' + _esc(L.league) + '</div>' +
      '<div style="font-size:11px;color:' + C.dim + '">' + L.games.length + ' Spiele · ' + L.snaps + ' Snaps</div></div>' +
      '<div style="text-align:right;min-width:150px"><div style="font-size:12px">' + btSummary + '</div>' +
      '<div style="font-size:11px;color:' + C.dim + ';margin-top:2px">akt. Edge max <b style="color:' + _edgeCol(L.maxEdge) + '">' + (L.maxEdge > -99 ? _pp1(L.maxEdge) + 'pp' : '–') + '</b></div></div></div>';
    var body = open ? '<div style="padding:0 13px 10px">' + L.games
      .sort(function (a, b) { return (b.cur ? b.cur.pp : -99) - (a.cur ? a.cur.pp : -99); })
      .map(_gameRow).join('') + '</div>' : '';
    return '<div style="background:' + C.card + ';border:1px solid ' + (open ? C.teal + '55' : C.bd) + ';border-radius:12px;margin-bottom:9px">' + head + body + '</div>';
  }

  function _ppRender() {
    var p = document.getElementById('pinnPolyPanel');
    if (!p) return;
    if (!_pp.data || !_pp.data.games || !Object.keys(_pp.data.games).length) {
      p.innerHTML = '<div style="text-align:center;color:' + C.dim + ';padding:60px 20px">Noch keine Scan-Daten.<br>' +
        'Der Scanner (alle 30 Min) sammelt gerade — schau in ein paar Läufen wieder rein.</div>';
      return;
    }
    var res = _leagues();
    var meta = _pp.data._meta || {};
    var avgSnaps = res.arr.length ? (res.totalSnaps / Object.keys(_pp.data.games).length) : 0;
    var collecting = avgSnaps < MIN_SNAPS_BT;
    var gen = meta.generatedAt ? new Date(meta.generatedAt) : null;
    var genStr = gen && !isNaN(gen) ? gen.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '?';

    var totTrips = res.arr.reduce(function (a, L) { return a + L.nTrips; }, 0);
    var totWins = res.arr.reduce(function (a, L) { return a + L.trips.filter(function (t) { return t.realized > 0; }).length; }, 0);
    var hit = totTrips ? Math.round(totWins / totTrips * 100) : null;

    var head = '<div style="margin-bottom:14px">' +
      '<div style="font-size:22px;font-weight:900;color:' + C.ink + '">📊 Pinnacle × Poly <span style="color:' + C.teal + '">Lag-Messung</span></div>' +
      '<div style="font-size:12px;color:' + C.mut + ';margin-top:2px">Wo läuft Pinnacle vor und Poly zieht nach. Einstieg bei Pinnacle-Move (≥' + MOVE_MIN + 'pp) auf Polys nachhinkendem Preis (Edge ≥' + ENTRY_EDGE + 'pp), Ausstieg bei Konvergenz (≤' + EXIT_EDGE + 'pp). Reines Messen.</div>' +
      '<div style="font-size:11px;color:' + C.dim + ';margin-top:2px">Stand ' + genStr + ' · ' + (meta.leaguesActive || res.arr.length) + ' aktive Ligen · ' + Object.keys(_pp.data.games).length + ' Spiele · ' + res.totalSnaps + ' Snapshots</div></div>';

    var tiles = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">' +
      _statTile('Round-Trips (Backtest)', totTrips, C.ink) +
      _statTile('Treffer gesamt', hit == null ? '–' : hit + '%', hit >= 50 ? C.good : C.mut) +
      _statTile('Ligen aktiv', meta.leaguesActive || res.arr.length, C.teal) +
      _statTile('Snapshots', res.totalSnaps, C.gold) + '</div>';

    var banner = collecting
      ? '<div style="background:rgba(255,184,12,.08);border:1px solid ' + C.gold + '44;border-radius:10px;padding:10px 13px;margin-bottom:14px;font-size:12px;color:' + C.mut + '">' +
        '⏳ <b style="color:' + C.gold + '">Backtest sammelt noch</b> — Ø ' + avgSnaps.toFixed(1) + ' Snapshots/Spiel (aussagekräftig ab ~' + MIN_SNAPS_BT + '). Die <b>aktuellen Edges</b> unten stimmen schon; die Round-Trip-Trefferquote wird mit jedem Lauf belastbarer.</div>'
      : '';

    var sortBar = '<div style="display:flex;gap:6px;margin-bottom:10px;font-size:12px">' +
      '<span style="color:' + C.dim + '">Sortieren:</span>' +
      '<button onclick="_ppSort(\'edge\')" style="background:none;border:none;cursor:pointer;color:' + (_pp.sort === 'edge' ? C.teal : C.dim) + ';font-weight:' + (_pp.sort === 'edge' ? 800 : 400) + '">akt. Edge</button>' +
      '<button onclick="_ppSort(\'trips\')" style="background:none;border:none;cursor:pointer;color:' + (_pp.sort === 'trips' ? C.teal : C.dim) + ';font-weight:' + (_pp.sort === 'trips' ? 800 : 400) + '">Round-Trips</button></div>';

    p.innerHTML = head + tiles + banner + sortBar + res.arr.map(_leagueRow).join('');
  }

  function initPinnPoly() {
    var p = document.getElementById('pinnPolyPanel');
    if (!p) return;
    if (_pp.loading) return;
    _pp.loading = true;
    p.innerHTML = '<div style="text-align:center;color:' + C.dim + ';padding:60px">Lade Scan-Daten …</div>';
    fetch('pinnacle_poly_scan.json?t=' + Date.now())
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { _pp.data = d; _pp.loading = false; _ppRender(); })
      .catch(function () { _pp.loading = false; _pp.data = null; _ppRender(); });
  }

  function _ppToggle(lg) { _pp.open = (_pp.open === lg) ? null : lg; _ppRender(); }
  function _ppSort(s) { _pp.sort = s; _ppRender(); }

  window.initPinnPoly = initPinnPoly;
  window._ppToggle = _ppToggle;
  window._ppSort = _ppSort;
  window._ppBacktest = _backtest;
})();
