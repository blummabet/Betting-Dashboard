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
    { id: 'Over/Under 2.5 Goals', label: 'O/U 2.5', kind: 'ou',  grp: 'FT' },
    { id: 'Over/Under 3.5 Goals', label: 'O/U 3.5', kind: 'ou',  grp: 'FT' },
    { id: 'Both teams to Score?', label: 'BTTS',    kind: 'yn',  grp: 'FT' },
    { id: 'Half Time',            label: 'HT 1X2',  kind: '1x2', grp: 'HT' },
    { id: 'First Half Goals 0.5', label: 'HT O/U 0.5', kind: 'ou',  grp: 'HT' },
    { id: 'First Half Goals 1.5', label: 'HT O/U 1.5', kind: 'ou',  grp: 'HT' },
  ];
  var MK_ID = {}; MK.forEach(function (m) { MK_ID[m.id] = m; });

  // Schwellen je Ebene (€) — Lucas 30.07.2026. FT = größter „Full-Time"-Markt, HT = größter Halbzeit-
  // Markt (HT-1X2 ODER Über 1,5/0,5 erste HZ). Spiel erscheint, sobald FT- ODER HT-Schwelle erreicht.
  // International (UEFA/Länder) verhält sich wie Top (Lucas: „internationale Bewerbe bleiben, wie Top").
  var THR = { top: { FT: 20000, HT: 10000 }, intl: { FT: 20000, HT: 10000 }, rest: { FT: 15000, HT: 5000 } };
  window._bfTHR = THR;   // Test-Hook: Rendering-Tests pinnen eigene Schwellen (produktiv unverändert)
  var CHIP_FLOOR = 500;
  var MIN_ODD_SHOW = 1.30;   // Ausgänge, auf denen das Geld unter dieser Quote liegt (fast sichere Favoriten / Parken), gar nicht zeigen — Hotspot + Frisches Geld (wie Push-Floor)

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

  var _bf = { data: null, hist: null, track: null, loading: false, view: 'live', league: 'all', tab: 'all', date: 'all', onlyLive: false, market: 'all', cardOpen: {}, trackBy: 'league' };
  var MIN_CONF_N = 20;   // ab so vielen abgerechneten Spielen gilt eine Liga×Markt-Quote als „belastbar"
  // 16.08.2026 (Lucas): betfair_prices.json kann Doppel-Einträge tragen (Workflow-Merge einer sich
  // aendernden JSON verdoppelt Array-Zeilen). Radar-seitig hart deduppen: pro matchId EIN Eintrag,
  // bevorzugt der, dessen Match-Odds-Runner zu home/away passen (fixt "Debreceni → GAIS"-Korruption),
  // dann hoechstes Volumen.
  function _bfPairScore(m) {
    var mo = (m && m.markets && m.markets['Match Odds']) || {}, rs = mo.runners || [];
    var h = String((m && m.home) || '').trim().toLowerCase(), a = String((m && m.away) || '').trim().toLowerCase();
    var sc = 0;
    for (var i = 0; i < rs.length; i++) {
      var rn = String((rs[i] && rs[i].name) || '').trim().toLowerCase();
      if (!rn || /draw|unentschieden|remis/.test(rn)) continue;
      if (h && (h.indexOf(rn) >= 0 || rn.indexOf(h) >= 0)) sc++;
      else if (a && (a.indexOf(rn) >= 0 || rn.indexOf(a) >= 0)) sc++;
    }
    return sc;
  }
  function _bfDedupMatches(matches) {
    if (!Array.isArray(matches)) return matches || [];
    var by = {}, order = [], noid = [];
    for (var i = 0; i < matches.length; i++) {
      var m = matches[i], id = String((m && m.matchId) || '');
      if (!id) { noid.push(m); continue; }
      if (!(id in by)) { by[id] = m; order.push(id); continue; }
      var a = _bfPairScore(m), b = _bfPairScore(by[id]);
      if (a > b || (a === b && (+(m && m.totalVol) || 0) > (+(by[id] && by[id].totalVol) || 0))) by[id] = m;
    }
    return order.map(function (id) { return by[id]; }).concat(noid);
  }
  window._bfState = _bf;

  function _bfFetch3() {
    // raw.github ZUERST → spiegelt den Commit sofort, also so frisch wie der Telegram-Push (der Push
    // feuert beim Fetch, VOR dem Pages-Deploy). Sonst lokal (Pages/Offline-Cache). Schließt die
    // Push↔Radar-Lücke: der Radar wartet nicht mehr auf den separaten, trägen Pages-Deploy-Schedule.
    var base = 'https://raw.githubusercontent.com/blummabet/Betting-Dashboard/main';
    var t = Date.now();
    var jf = function (name) {
      return fetch(base + '/' + name + '?t=' + t, { cache: 'no-store' })
        .then(function (r) { if (r.ok) return r.json(); throw 0; })
        .catch(function () {
          return fetch(name + '?t=' + t, { cache: 'no-store' })
            .then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
        });
    };
    return Promise.all([jf('betfair_prices.json'), jf('betfair_history.json'), jf('betfair_track_record.json'), jf('betfair_public_record.json'), jf('betfair_direction.json'), jf('betfair_consensus.json'), jf('betfair_league_norm.json'), jf('betfair_card_link.json')]);
  }
  function _bfLoad() {
    if (_bf.data || _bf.loading) return;
    _bf.loading = true;
    _bfFetch3().then(function (a) {
      _bf.data = a[0] || { matches: [] }; if (_bf.data && Array.isArray(_bf.data.matches)) _bf.data.matches = _bfDedupMatches(_bf.data.matches); _bf.hist = a[1] || {}; _bf.track = a[2] || null; _bf.pubrec = a[3] || null; _bf.dir = a[4] || {}; _bf.consensus = a[5] || null; _bf.lnorm = a[6] || null; _bf.cardLink = a[7] || null;
      _bf._cohCache = {}; _bf._mixBase = null; _bf._normBase = null;
      _bf.loading = false; _bf.cardOpen = {};
      var p = document.getElementById('betfairRadarPanel');
      if (p && p.style.display !== 'none') p.innerHTML = renderBetfairRadar();
    });
  }
  window._bfLoad = _bfLoad;

  // Auto-Refresh (29.07.2026, Lucas: „Daten sind 2h alt" bei offenem Tab). Der Radar lud die
  // Daten NUR EINMAL (_bfLoad-Guard) und pollte nie nach → in einem länger offenen Tab wuchs
  // genAgeMin() unbegrenzt und der Stale-Banner feuerte, obwohl der Server frische Daten hatte.
  // Fix: alle 5 Min + beim Zurückkehren zum Tab frisch nachladen — OHNE die offene UI zu resetten
  // (View/Liga/Tab/Datum + aufgeklappte Cards bleiben; nur data/hist/track werden ersetzt).
  function _bfRefresh() {
    if (_bf.loading) return;
    var p = document.getElementById('betfairRadarPanel');
    if (!p || p.style.display === 'none') return;   // nur nachladen, wenn der Radar sichtbar ist
    _bf.loading = true;
    return _bfFetch3().then(function (a) {
      if (a[0]) _bf.data = a[0];
      if (a[1]) _bf.hist = a[1];
      if (a[2] != null) _bf.track = a[2];
      if (a[3] != null) _bf.pubrec = a[3];
      if (a[4] != null) _bf.dir = a[4];
      if (a[5] != null) _bf.consensus = a[5];
      if (a[6] != null) _bf.lnorm = a[6];
      if (a[7] != null) _bf.cardLink = a[7];
      _bf._cohCache = {}; _bf._mixBase = null; _bf._normBase = null;
      _bf.loading = false;
      var pp = document.getElementById('betfairRadarPanel');
      if (pp && pp.style.display !== 'none') pp.innerHTML = renderBetfairRadar();
    });
  }
  window._bfRefresh = _bfRefresh;
  // _bfNoAutoRefresh: Test-Flag (Timer würde sonst die jsdom-Event-Loop offenhalten). unref()
  // hält den Timer im echten Browser aktiv, lässt aber node bei Tests sauber beenden.
  if (typeof window !== 'undefined' && !window._bfAutoRefreshSet && !window._bfNoAutoRefresh) {
    window._bfAutoRefreshSet = true;
    var _bfTimer = setInterval(_bfRefresh, 5 * 60000);
    if (_bfTimer && typeof _bfTimer.unref === 'function') _bfTimer.unref();
    document.addEventListener('visibilitychange', function () { if (!document.hidden) _bfRefresh(); });
    window.addEventListener('focus', _bfRefresh);
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]; }); }
  function eur(v) { return (+v || 0) * EURFX; }
  function fmtE(v) { var n = eur(v); if (n >= 1e6) return '€' + (n / 1e6).toFixed(2) + 'M'; if (n >= 1e3) return '€' + (n / 1e3).toFixed(n >= 1e5 ? 0 : 1).replace('.0', '') + 'K'; return '€' + Math.round(n); }
  function mkOf(m, id) { return (m.markets || {})[id] || null; }
  // Geld = Summe der Runner-Volumina (das echte Matched-Geld). NICHT mk.vol/totalVol aus alten
  // Daten (die trugen average_volume — eine andere, viel größere Kennzahl). So stimmt Kopf = Summe.
  function mvolG(m, id) { var mk = mkOf(m, id); return mk ? distTotal(mk) : 0; }
  function totalG(m) { var s = 0, mm = m.markets || {}; for (var k in mm) s += distTotal(mm[k]); return s; }
  // Geld des GRÖSSTEN einzelnen (getrackten) Marktes — die aussagekräftige Zahl fürs Spiel,
  // NICHT die Summe aller Märkte (die blähte den Kopf auf: €279K statt der 137K auf 1X2).
  function topMktVol(m) { var best = 0; for (var i = 0; i < MK.length; i++) { var v = mvolG(m, MK[i].id); if (v > best) best = v; } return best; }
  // Bei aktivem Markt-Filter zeigt der Kopf den GEFILTERTEN Markt, sonst den größten (Lucas 29.07.).
  function cardMoney(m) { if (_bf.market !== 'all') { var v = mvolG(m, _bf.market); if (v > 0) return v; } return topMktVol(m); }
  function cardMoneyLbl(m) { if (_bf.market !== 'all' && mvolG(m, _bf.market) > 0) { return MK_ID[_bf.market] ? MK_ID[_bf.market].label : shortMk(_bf.market); } return 'größter Markt'; }
  function runnersOf(mk) { var r = mk && mk.runners; return Array.isArray(r) ? r : []; }
  function distTotal(mk) { return runnersOf(mk).reduce(function (a, r) { return a + (+r.vol || 0); }, 0); }
  function leadRunner(mk) { return runnersOf(mk).reduce(function (a, r) { return (!a || (+r.vol || 0) > (+a.vol || 0)) ? r : a; }, null); }
  function fO(o) { return (typeof o === 'number' && o > 1) ? (o >= 20 ? String(Math.round(o)) : o.toFixed(2)) : '–'; }   // 08.08.2026 (Lucas): hohe Quoten ohne sinnlose „.00" (@23 statt @23.00, @800 statt @800.00)
  // 08.08.2026 (Lucas: „Back oder Lay?"): Richtung aus betfair_direction.json (Quote kuerzer=Back, driftet=Lay).
  function dirOf(m, marketId, runnerName) {
    try { return (((( _bf.dir || {})[String(m.matchId)] || {})[marketId] || {})[runnerName]) || null; } catch (e) { return null; }
  }
  function dirBadge(m, marketId, runner) {
    if (!runner) return '';
    var e = dirOf(m, marketId, runner.name); if (!e) return '';
    if (e.dir === 'in') return ' <span title="Quote kürzer → Geld kommt als Back" style="font-size:9.5px;font-weight:800;color:#3fb950;border:1px solid rgba(63,185,80,.45);border-radius:4px;padding:0 4px">Back ✓</span>';
    if (e.dir === 'out') return ' <span title="Quote driftet raus → kein echter Back-Rückhalt" style="font-size:9.5px;font-weight:800;color:#e3b341;border:1px solid rgba(227,179,65,.45);border-radius:4px;padding:0 4px">driftet</span>';
    return '';
  }
  window._bfDirBadge = dirBadge;   // Test-Hook
  // 08.08.2026 (Lucas): Geld auf die aktuell FÜHRENDE Mannschaft nicht mehr rauswerfen, sondern
  // markieren — zusammen mit dem Back/driftet-Badge ist „führt + Back ✓" ein starkes Folge-Signal,
  // „führt + driftet" dagegen verdächtig. _leaderTeam ist weiter unten (function-hoisted).
  function fuehrtTag(m, runnerName) {
    var ldr = _leaderTeam(m);
    if (!ldr || runnerName == null || String(runnerName) !== String(ldr)) return '';
    return ' <span title="Geld auf die aktuell führende Mannschaft — folgt der Führung. Mit „Back ✓" bestätigt die Quote das (starkes Signal), mit „driftet" wird die Führung eher gelayt." style="font-size:9px;font-weight:800;color:#8b949e;border:1px solid rgba(139,148,150,.45);border-radius:4px;padding:0 4px">▶ führt</span>';
  }
  window._bfFuehrtTag = fuehrtTag;   // Test-Hook
  function rLabel(name, m) {
    if (name === m.home) return String(m.home);
    if (name === m.away) return String(m.away);
    if (name === 'The Draw') return 'Remis';
    return String(name).replace('Over', 'O').replace('Under', 'U').replace(' Goals', '').replace('Yes', 'Ja').replace('No', 'Nein');
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
  // GitHub-Actions-Schedule ist jittery (~8–30 Min statt exakt 10) → Schwellen locker halten,
  // sonst „veraltet"-Alarm bei ganz normalem Betrieb.
  var FRESH_LIVE_MIN = 30;   // bis hierher gilt Live-Status als vertrauenswürdig
  var STALE_WARN_MIN = 75;   // absolute Vertrauensgrenze fürs Live-Alter (cadence-unabhängig) → erst ab ~1h Funkstille warnen
  var LIVE_MAX_H = 2.5;   // ein Fußballspiel dauert ~2h (inkl. Nachspielzeit); danach ist es vorbei
  function _kickMs(m) { var k = m.kickoff ? Date.parse(m.kickoff) : NaN; return isNaN(k) ? null : k; }
  // Live-Status (29.07.2026, Fix „längst beendete Spiele wurden live gezeigt"): HARTER Cut — beendet
  // ODER mehr als LIVE_MAX_H nach Anpfiff → vorbei, egal ob der Feed noch eine Uhr sendet (stale). Sonst
  // ist die Betwatch-Live-Uhr das verlässlichste Live-Signal; ohne Uhr zählt das Anpfiff-Fenster
  // (Anpfiff .. +2,5h). Keine Hysterese mehr (die hielt beendete Spiele fälschlich live). EINE Quelle.
  function isLive(m, _ageMinOverride) {
    var li = m.liveInfo || {};
    if (li.finished) return false;
    // 04.08.2026 (Lucas: „Uebersicht zeigt kein Live-Badge“): die Stale-Sperre las die Frische aus
    // _bfState (Radar-Speicher) — auf der Uebersicht leer → genAgeMin()=9999 → ALLES „nicht live“.
    // Aufrufer aus anderem Kontext (main-dashboard) reichen ihre eigene Daten-Frische als Override rein.
    var _ageMin = (typeof _ageMinOverride === 'number') ? _ageMinOverride : genAgeMin();
    if (_ageMin > STALE_WARN_MIN) return false;
    var k = _kickMs(m), now = Date.now(), age = (k != null) ? (now - k) : null;
    if (age != null && age > LIVE_MAX_H * 3.6e6) return false;               // klar vorbei
    if (li.time != null) return true;                                       // Betwatch-Live-Uhr → live
    return age != null && age >= -60000 && age <= LIVE_MAX_H * 3.6e6;       // ohne Uhr: Anpfiff-Fenster
  }
  window._bfIsLive = isLive;   // Test-Hook
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
  // ═══ Kohärenz-Engine (portiert aus Lucas' v5-Prototyp, 29.07.2026) ═══════════════════════
  // Nicht nur WO das Geld liegt, sondern WO der Markt sich selbst widerspricht. Fittet ein
  // Poisson-λ an die Ü/U-Leiter + Supremacy an die de-viggten 1X2-Fairs, leitet BTTS/HZ ab und
  // prüft jeden gehandelten Preis gegen das, was die übrigen Märkte desselben Spiels implizieren.
  // hart = reine Arithmetik (echter Widerspruch) · weich = Modellabweichung (Poisson-Annahme).
  var OU_LADDER = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5];
  var HT_SHARE = 0.45;                                  // ~45 % der Tore fallen in HZ1 (Richtwert)
  function _cpct(p) { return (p * 100).toFixed(1) + '%'; }
  function _cpp(d) { return (d >= 0 ? '+' : '−') + Math.abs(d).toFixed(1); }
  function devig2(a, b) { if (!(a > 1) || !(b > 1)) return null; var ia = 1 / a, ib = 1 / b; return ia / (ia + ib); }
  function pois(k, l) { var p = Math.exp(-l); for (var i = 1; i <= k; i++) p *= l / i; return p; }
  function poisOver(n, l) { var cum = 0; for (var k = 0; k <= Math.floor(n); k++) cum += pois(k, l); return 1 - cum; }
  function fitLambda(rungs) {
    var ks = Object.keys(rungs).map(Number); if (ks.length < 2) return null;
    var best = null;
    for (var l = 0.20; l <= 6.60; l += 0.01) {
      var e = 0; for (var i = 0; i < ks.length; i++) { var d = poisOver(ks[i], l) - rungs[ks[i]]; e += d * d; }
      if (!best || e < best.e) best = { l: +l.toFixed(2), e: e, rmse: Math.sqrt(e / ks.length) };
    }
    return best;
  }
  function cohOutcome(lh, la, N) {
    N = N || 12; var h = 0, d = 0, a = 0, ph = [], pa = [], i, j;
    for (i = 0; i <= N; i++) { ph[i] = pois(i, lh); pa[i] = pois(i, la); }
    for (i = 0; i <= N; i++) for (j = 0; j <= N; j++) { var p = ph[i] * pa[j]; if (i > j) h += p; else if (i === j) d += p; else a += p; }
    return { h: h, d: d, a: a };
  }
  function fitSupremacy(lam, fair) {
    if (!lam || !fair) return null; var best = null;
    for (var sp = -3.2; sp <= 3.2; sp += 0.02) {
      var lh = (lam + sp) / 2, la = (lam - sp) / 2; if (lh <= 0.01 || la <= 0.01) continue;
      var o = cohOutcome(lh, la); var e = Math.pow(o.h - fair.home, 2) + Math.pow(o.a - fair.away, 2);
      if (!best || e < best.e) best = { s: +sp.toFixed(2), lh: lh, la: la, e: e, o: o };
    }
    return best;
  }
  function bttsP(lh, la) { return (1 - Math.exp(-lh)) * (1 - Math.exp(-la)); }
  function cohRunner(m, id, test) {
    var x = mkOf(m, id); if (!x) return null; var rs = runnersOf(x);
    for (var i = 0; i < rs.length; i++) { if (test(String(rs[i].name || ''))) return rs[i]; }
    return null;
  }
  function ouRungs(m) {
    var out = {};
    for (var i = 0; i < OU_LADDER.length; i++) {
      var n = OU_LADDER[i], id = 'Over/Under ' + n + ' Goals';
      var o = cohRunner(m, id, function (s) { return s.indexOf('Over') === 0; });
      var u = cohRunner(m, id, function (s) { return s.indexOf('Under') === 0; });
      var p = devig2(o && o.odd, u && u.odd); if (p != null) out[n] = p;
    }
    return out;
  }
  function htRungs(m) {
    var out = {}, lines = [0.5, 1.5, 2.5];
    for (var i = 0; i < lines.length; i++) {
      var n = lines[i], id = 'First Half Goals ' + n;
      var o = cohRunner(m, id, function (s) { return s.indexOf('Over') === 0; });
      var u = cohRunner(m, id, function (s) { return s.indexOf('Under') === 0; });
      var p = devig2(o && o.odd, u && u.odd); if (p != null) out[n] = p;
    }
    return out;
  }
  function liqW(vol) { vol = +vol || 0; if (vol < 750) return 0; return Math.min(1, Math.log10(vol / 750) / 1.6); }
  function coherence(m) {
    var checks = [];
    var fair = (m.mo || {}).fair || null;
    var rungs = ouRungs(m);
    var fit = fitLambda(rungs);
    var sup = fit ? fitSupremacy(fit.l, fair) : null;
    var ks = Object.keys(rungs).map(Number).sort(function (a, b) { return a - b; });
    // 1 — Leiter-Monotonie: P(Ü0.5) ≥ P(Ü1.5) ≥ …  (hart)
    for (var i = 0; i < ks.length - 1; i++) {
      var dd = (rungs[ks[i + 1]] - rungs[ks[i]]) * 100;
      if (dd > 0.4) checks.push({ k: 'Leiter-Monotonie', mkt: 'O' + ks[i + 1] + ' > O' + ks[i],
        market: rungs[ks[i + 1]], model: rungs[ks[i]], dev: dd, hard: true, vol: mvolG(m, 'Over/Under ' + ks[i + 1] + ' Goals'),
        why: 'Mehr Tore können nie wahrscheinlicher sein als weniger. Reiner Widerspruch.' });
    }
    // 2 — Draw no Bet vs. 1X2 (harte Identität)
    var dh = cohRunner(m, 'Draw no Bet', function (s) { return s === String(m.home); });
    var da = cohRunner(m, 'Draw no Bet', function (s) { return s === String(m.away); });
    var dnb = devig2(dh && dh.odd, da && da.odd);
    if (dnb != null && fair) {
      var impl = fair.home / (fair.home + fair.away);
      checks.push({ k: 'Draw no Bet', mkt: 'DNB ' + m.home, market: dnb, model: impl, dev: (dnb - impl) * 100,
        hard: true, vol: mvolG(m, 'Draw no Bet'),
        why: 'DNB ist reine Algebra aus 1X2: p(H)/(p(H)+p(A)). Jede Abweichung ist ein echter Preisfehler zwischen zwei Märkten.' });
    }
    // 3 — Ü/U-Sprossen vs. gefittete Poisson-Kurve (weich)
    if (fit && ks.length >= 3) {
      for (var a = 0; a < ks.length; a++) {
        var n = ks[a], model = poisOver(n, fit.l), d3 = (rungs[n] - model) * 100;
        if (Math.abs(d3) >= 2.5) checks.push({ k: 'Tor-Kurve', mkt: 'O' + n, market: rungs[n], model: model, dev: d3,
          hard: false, vol: mvolG(m, 'Over/Under ' + n + ' Goals'),
          why: 'Diese Sprosse liegt neben der Kurve, die die anderen Sprossen desselben Marktes aufspannen.' });
      }
    }
    // 4 — BTTS vs. doppelt-Poisson aus λ + Supremacy (weich)
    var by = cohRunner(m, 'Both teams to Score?', function (s) { return /^yes/i.test(s); });
    var bn = cohRunner(m, 'Both teams to Score?', function (s) { return /^no/i.test(s); });
    var btts = devig2(by && by.odd, bn && bn.odd);
    if (btts != null && sup) {
      var mb = bttsP(sup.lh, sup.la);
      checks.push({ k: 'BTTS', mkt: 'Beide treffen', market: btts, model: mb, dev: (btts - mb) * 100,
        hard: false, vol: mvolG(m, 'Both teams to Score?'),
        why: 'Aus Torerwartung und Supremacy folgt eine BTTS-Quote. Große Lücken heißen: der Markt erwartet eine schiefere Torverteilung als 1X2 + O/U zulassen.' });
    }
    // 5 — Halbzeit-Märkte vs. FT-Torerwartung (weich)
    var hr = htRungs(m);
    if (fit) { var hk = Object.keys(hr).map(Number);
      for (var b = 0; b < hk.length; b++) {
        var hn = hk[b], hm = poisOver(hn, fit.l * HT_SHARE), d5 = (hr[hn] - hm) * 100;
        if (Math.abs(d5) >= 3) checks.push({ k: 'Halbzeit', mkt: 'HZ1 O' + hn, market: hr[hn], model: hm, dev: d5,
          hard: false, vol: mvolG(m, 'First Half Goals ' + hn),
          why: 'HZ1 trägt im Schnitt ~45 % der Tore. Weicht die Halbzeit stark ab, hat jemand eine Meinung zum Spielverlauf, nicht nur zum Ergebnis.' });
      }
    }
    for (var c = 0; c < checks.length; c++) checks[c].w = liqW(checks[c].vol);
    checks.sort(function (x, y) { return (y.hard * y.w - x.hard * x.w) || (Math.abs(y.dev) * y.w - Math.abs(x.dev) * x.w); });
    return { checks: checks, fit: fit, sup: sup, rungs: rungs, fair: fair, btts: btts, dnb: dnb, ht: hr };
  }
  // Geldfluss aus der History → steam / absorb / air.
  function cohFlow(m) {
    var h = (_bf.hist || {})[String(m.matchId)];
    if (!Array.isArray(h) || h.length < 2) return null;
    var f = h[0], l = h[h.length - 1];
    var mins = (Date.parse(l.ts) - Date.parse(f.ts)) / 6e4;
    if (!(mins > 0)) return null;
    var fv = (f.totalVol != null ? f.totalVol : ((f.mo || {}).vol || 0));
    var lv = (l.totalVol != null ? l.totalVol : ((l.mo || {}).vol || 0));
    var dv = lv - fv, rate = dv / (mins / 60), move = 0, side = null;
    ['hw', 'dr', 'aw'].forEach(function (k) {
      var a = (f.mo || {})[k], b = (l.mo || {})[k];
      if (a > 1 && b > 1) { var d = (1 / b - 1 / a) * 100; if (Math.abs(d) > Math.abs(move)) { move = d; side = k; } }   // Implied-Prob-pp (bounded ±100), nicht relative Quote
    });
    var growth = fv > 0 ? dv / fv : 0, kind = 'ruhig';
    if (Math.abs(move) >= 3 && growth >= 0.35) kind = 'steam';
    else if (Math.abs(move) < 1.2 && growth >= 0.60) kind = 'absorb';
    else if (Math.abs(move) >= 3 && growth < 0.15) kind = 'air';
    return { rate: rate, dv: dv, mins: mins, move: move, side: side, growth: growth, kind: kind, snaps: h.length,
      sideName: side === 'hw' ? m.home : side === 'aw' ? m.away : side === 'dr' ? 'Remis' : null };
  }
  // Markt-Mix-Anomalie: Verteilung ggü. Median-Baseline über alle Spiele.
  function mixBaseline(matches) {
    var acc = {};
    for (var i = 0; i < matches.length; i++) {
      var mks = matches[i].markets || {}, tot = 0, k;
      for (k in mks) tot += distTotal(mks[k]);
      if (tot < 5000) continue;
      for (k in mks) { (acc[k] = acc[k] || []).push(distTotal(mks[k]) / tot); }
    }
    var med = {};
    for (var kk in acc) { var arr = acc[kk].sort(function (x, y) { return x - y; }); med[kk] = arr[Math.floor(arr.length / 2)]; }
    return med;
  }
  function mixAnomaly(m, base) {
    var mks = m.markets || {}, tot = 0, k;
    for (k in mks) tot += distTotal(mks[k]);
    if (tot < 5000) return null;
    var best = null;
    for (k in mks) {
      var vol = distTotal(mks[k]), share = vol / tot, b = base[k];
      if (!b || b < 0.004 || share < 0.08 || vol < 5000) continue;
      var ratio = share / b;
      if (!best || ratio > best.ratio) best = { market: k, share: share, base: b, ratio: ratio, vol: vol };
    }
    return (best && best.ratio >= 1.8) ? best : null;
  }
  function cohScore(m, base) {
    var co = coherence(m), fl = cohFlow(m), mx = mixAnomaly(m, base), s = 0, i;
    var hard = co.checks.filter(function (c) { return c.hard && Math.abs(c.dev) >= 0.8 && c.w >= 0.15; });
    var soft = co.checks.filter(function (c) { return !c.hard && Math.abs(c.dev) >= 2.5 && c.w >= 0.15; });
    for (i = 0; i < hard.length; i++) s += Math.min(30, 9 + Math.abs(hard[i].dev) * 3.2) * hard[i].w;
    for (i = 0; i < soft.length; i++) s += Math.min(20, Math.abs(soft[i].dev) * 2.2) * soft[i].w;
    if (fl) { if (fl.kind === 'steam') s += 17; else if (fl.kind === 'absorb') s += 13; else if (fl.kind === 'air') s += 6; }
    if (mx) s += Math.min(14, (mx.ratio - 1.8) * 9 + 5);
    if (isLive(m)) s += 5;
    var tv = totalG(m) || m.totalVol || 0;
    s *= 0.72 + 0.28 * Math.min(1, Math.log10(Math.max(1, tv)) / 6.2);
    return { s: Math.round(Math.min(99, s)), co: co, fl: fl, mx: mx, hard: hard, soft: soft };
  }
  // Memoisierung: Kohärenz hängt nur an den Preisen, nicht an Filtern → Cache bis Reload.
  function cohOf(m) {
    var id = String(m.matchId);
    if (!_bf._cohCache) _bf._cohCache = {};
    if (_bf._cohCache[id]) return _bf._cohCache[id];
    if (!_bf._mixBase) _bf._mixBase = mixBaseline((_bf.data && _bf.data.matches) || []);
    var r = cohScore(m, _bf._mixBase);
    _bf._cohCache[id] = r; return r;
  }
  window._bfCoherence = coherence;   // Test-Hook
  window._bfCohScore = cohScore;
  window._bfCohFlow = cohFlow;
  window._bfMixAnomaly = mixAnomaly;

  // ── ×-Norm: liegt auf DIESEM Spiel überverhältnismäßig viel Geld? ───────────────
  // Idee (Lucas 30.07.): nicht die absolute €-Summe zählt, sondern das VERHÄLTNIS zum
  // Üblichen für die gleiche Liga UND die gleiche Spielphase. Live zieht generell mehr Geld —
  // also vergleichen wir live-mit-live und vor-Anpfiff-mit-vor-Anpfiff, und ein EPL-Spiel nur
  // mit EPL-Spielen. Die Basis liefert betfair_league_norm.py (gelernt aus der Historie);
  // Details und der Grund dafür stehen bei _normBasis weiter unten.
  // Über ~1,6× Median = auffällig (Bernstein), über ~2,6× = stark (rot umrandet).
  var NORM_AMBER = 1.6, NORM_RED = 2.6, NORM_MIN_PEERS = 4, NORM_MIN_EUR = 3000;
  function _stageOf(m) {
    if (isLive(m)) {
      var li = m.liveInfo || {}, t = li.time;
      if (li.is_ht) return 'l2';
      if (typeof t === 'number') return t > 45 ? 'l2' : 'l1';
      var k = _kickMs(m); return (k != null && (Date.now() - k) > 45 * 60000) ? 'l2' : 'l1';
    }
    var k2 = _kickMs(m); if (k2 == null) return 'p0';
    return (k2 - Date.now()) <= 3 * 3.6e6 ? 'p1' : 'p0';   // p1 = letzte 3h vor Anpfiff, p0 = früher
  }
  // Stage → { med: Median-€ auf dem ganzen Spiel, n: Anzahl Vergleichsspiele }. Memoisiert bis Reload,
  // wird an denselben Stellen wie _mixBase geleert. Nur Spiele ab NORM_MIN_EUR zählen (Kleckerbeträge
  // würden den Median nach unten ziehen und harmlose Spiele „über Norm" aussehen lassen).
  // 22.08.2026 (Lucas: „auf Liga relativ"): Vergleich gegen die EIGENE Liga statt gegen alles —
  // „viel Geld FÜR EIN EPL-Spiel" ist die aussagekräftige Zahl. _normBase liefert dafür den
  // heutigen Schnappschuss (Liga+Phase, Liga). Der greift aber nur, wenn heute genug Spiele
  // derselben Liga laufen — die Hauptquelle ist seit 24.08. die gelernte Basis, siehe _normBasis.
  function _normLeague(m) { return String(m.league || m.leagueId || '?'); }
  function _normBase() {
    if (_bf._normBase) return _bf._normBase;
    // 24.08.2026: der globale Pool (sg) wird nicht mehr gebaut — er war die Ursache der ×80.
    var ms = (_bf.data && _bf.data.matches) || [], ls = {}, lg = {}, i;
    for (i = 0; i < ms.length; i++) {
      var tot = eur(totalG(ms[i])); if (tot < NORM_MIN_EUR) continue;
      var st = _stageOf(ms[i]), L = _normLeague(ms[i]);
      (ls[st + '|' + L] = ls[st + '|' + L] || []).push(tot);
      (lg[L] = lg[L] || []).push(tot);   // 24.08.2026: kein globaler Stage-Pool mehr — siehe _normBasis
    }
    function _med(map) {
      var out = {}; for (var k in map) { var a = map[k].sort(function (x, y) { return x - y; }); out[k] = { med: a[Math.floor(a.length / 2)], n: a.length }; } return out;
    }
    _bf._normBase = { ls: _med(ls), lg: _med(lg) };
    return _bf._normBase;
  }
  // 24.08.2026 (Lucas: „bei Premier League und Serie A steht das immer noch so extrem"): die
  // Liga-Stufe vom 22.08. war eingebaut — sie lief nur ins Leere. Jede Stufe verlangt
  // NORM_MIN_PEERS Vergleichsspiele, und die kamen aus dem AKTUELLEN Schnappschuss. Den erreichen
  // fast nie 4 Spiele derselben Liga (24.08.: 2 von 34 Ligen), also fiel praktisch alles auf den
  // GLOBALEN Pool durch — und der besteht aus Slovenian U19, Reserve- und Nachwuchsspielen
  // (Median ~€11K). Fulham–Chelsea kam so auf ×82; an echten EPL-Spielen gemessen sind es ×0.6.
  // Das Badge war nicht ungenau, es war INVERTIERT: das Spiel lag unter seiner Liga-Norm.
  //
  // Die Basis muss aus der ZEIT kommen, nicht aus dem Moment. betfair_league_norm.py lernt rollend
  // „was ist üblich für Liga X in Phase Y" (60-Tage-Fenster, Median echter Spiele) — das ist die
  // erste Stufe. Der heutige Schnappschuss bleibt als Notnagel für Ligen, die noch keine Historie
  // haben. Der globale Fallback ist RAUS: kennen wir die Liga nicht, sagen wir nichts, statt sie
  // am falschen Maßstab zu messen. Kein Badge ist besser als ein falsches.
  function _normLearned(L, st) {
    var b = _bf.lnorm && _bf.lnorm.byLeagueStage, x = b && b[L + '|' + st];
    return (x && x.n >= NORM_MIN_PEERS && x.med) ? x : null;
  }
  // { med, n, src } oder null. src: 'gelernt' = Historie, 'heute' = aktueller Schnappschuss.
  function _normBasis(m) {
    if (eur(totalG(m)) < NORM_MIN_EUR) return null;   // Kleckerspiel: „×3" waere nur Rauschen
    var st = _stageOf(m), L = _normLeague(m);
    var pick = _normLearned(L, st);                   // 1. gelernte Liga+Phase (die aussagekraeftige)
    if (pick) return { med: pick.med, n: pick.n, src: 'gelernt' };
    var b = _normBase(), ok = function (x) { return x && x.n >= NORM_MIN_PEERS && x.med; };
    pick = b.ls[st + '|' + L];                        // 2. heutige Spiele derselben Liga+Phase
    if (!ok(pick)) pick = b.lg[L];                    // 3. heutige Spiele derselben Liga
    return ok(pick) ? { med: pick.med, n: pick.n, src: 'heute' } : null;
  }
  function _normRatio(m) {
    var b = _normBasis(m);
    return b ? (eur(totalG(m)) / b.med) : null;
  }
  function _normLvl(m) { var r = _normRatio(m); return r == null ? 0 : (r >= NORM_RED ? 2 : r >= NORM_AMBER ? 1 : 0); }
  function _normCls(m) { var l = _normLvl(m); return l === 2 ? ' bfb-over2' : l === 1 ? ' bfb-over' : ''; }
  function _normBadge(m) {
    var b = _normBasis(m); if (!b) return '';
    var r = eur(totalG(m)) / b.med; if (r < NORM_AMBER) return '';
    var red = r >= NORM_RED, col = red ? '#f0883e' : C.gold;   // 02.08.2026 (Lucas): Gold->Orange zweistufig statt Rot (Rot = nur Live)
    // Der Tooltip nennt die Basis, damit die Zahl nachpruefbar ist: an WAS gemessen und aus wie
    // vielen Spielen. Genau das fehlte, als das Badge still gegen den globalen Pool mass.
    var basis = (b.src === 'gelernt' ? 'gelernter Median dieser Liga in dieser Spielphase'
                                     : 'Median der heutigen Spiele dieser Liga')
              + ': ' + fmtE(b.med) + ' aus ' + b.n + ' Spielen';
    return '<span class="bfb-norm" style="color:' + col + ';border-color:' + col + '" title="' + (red ? 'weit über' : 'über') + ' dem üblichen Geld für diese Liga — ' + basis + '. Ohne belastbare Liga-Basis zeigen wir gar kein Badge.">×' + r.toFixed(1) + ' Norm</span>';
  }
  function _normLine(m) { var b = _normBadge(m); return b ? '<br>' + b : ''; }
  // (31.07.2026, Lucas) Live-Hervorhebung in den Streifen: Rot = NUR Live (×-Norm ist amber).
  // Live hat Vorrang vor der ×-Norm-Umrandung; das ×N-Norm-Badge bleibt zusätzlich sichtbar.
  function _liveBadge(m) {
    if (!isLive(m)) return '';
    // (01.08.2026, Lucas) nur "● LIVE" — Spielstand/Minute war zeitlich unzuverlässig, daher weglassen.
    return '<span class="bfb-liveb">● LIVE</span>';
  }
  function _rowHl(m) { return _normCls(m); }   // 02.08.2026 (Lucas): keine rote Live-Umrandung mehr; Rot nur im LIVE-Badge, Ueber-Norm traegt amber.
  function _hlLine(m) {
    var parts = [];
    var lv = _liveBadge(m); if (lv) parts.push(lv);
    var nb = _normBadge(m); if (nb) parts.push(nb);
    return parts.length ? '<br>' + parts.join(' ') : '';
  }
  window._bfNormRatio = _normRatio;   // Test-Hook
  window._bfNormBasis = _normBasis;   // Test-Hook
  window._bfNormBadge = _normBadge;   // Test-Hook
  window._bfStageOf = _stageOf;

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
        var pp = (1 / b - 1 / a) * 100;   // Implied-Prob-Differenz in pp (bounded ±100) — NICHT relative
        if (!best || Math.abs(pp) > Math.abs(best.pp)) best = { side: k, pp: pp };     // Quotenänderung, die bei Live-Drift explodiert (16279pp-Bug, Lucas 29.07.)
      }
    });
    return best && Math.abs(best.pp) >= 1.5 ? best : null;
  }
  window._bfMoveOf = moveOf;   // Test-Hook
  function dirPill(m) {
    if (isLive(m)) return '';   // 03.08.2026 (Lucas): live bewegt der Spielstand die Quote, kein Wettsignal
    var mv = moveOf(m); if (!mv) return '';
    var backed = mv.pp > 0, col = backed ? C.back : C.lay;
    var side = mv.side === 'hw' ? m.home : mv.side === 'aw' ? m.away : 'Remis';
    var txt = backed ? ('Geld → ' + String(side).slice(0, 14)) : (String(side).slice(0, 14) + ' driftet');
    var tip = backed ? 'Quote fällt = auf diesen Ausgang wird gesetzt (Back). ' : 'Quote steigt = Ausgang wird schwächer, Geld dagegen (Lay). ';
    return '<span title="' + esc(tip) + Math.abs(mv.pp).toFixed(1) + 'pp seit erstem Snapshot" style="display:inline-flex;gap:4px;align-items:center;padding:2px 9px;border-radius:20px;background:' + (backed ? 'rgba(63,185,80,.14)' : 'rgba(248,81,73,.14)') + ';color:' + col + ';font-size:11px;font-weight:800">' + (backed ? '▼' : '▲') + ' ' + esc(txt) + ' <span style="opacity:.7">' + (backed ? 'Quote fällt' : 'Quote steigt') + '</span></span>';
  }
  function liveMinTxt(m) {
    // 10.08.2026 (Lucas): Live-Minute im Radar — aber EHRLICH. Der Feed ist ~alle 15 Min, die gespeicherte
    // Minute also „alt". Wir rechnen den Scan-Verzug (genAgeMin) drauf → ~Jetzt-Stand, mit „~" markiert.
    // Halbzeit separat (Verzug draufrechnen waere dann falsch). Score selbst ist exakt (echte Tor-Zahl).
    var li = m.liveInfo || {};
    if (li.is_ht) return 'HZ';
    var t = li.time;
    if (typeof t !== 'number' || t <= 0) return '';
    var lag = genAgeMin();
    return '~' + Math.min(130, t + (lag > 0 && lag < 30 ? Math.round(lag) : 0)) + "'";
  }
  function koPill(m) {
    if (isLive(m)) {
      var li = m.liveInfo || {};
      var sc = (li.goal_v1 != null && li.goal_v2 != null) ? (li.goal_v1 + ':' + li.goal_v2) : '';
      var mn = liveMinTxt(m);
      var rc = ((li.red_v1 || 0) + (li.red_v2 || 0)) > 0 ? ' 🟥' : '';
      var lag = Math.round(genAgeMin());
      var ttl = 'Live-Stand vom letzten Scan' + (lag > 0 && lag < 300 ? ' (vor ' + lag + ' Min)' : '');
      return '<span title="' + ttl + '" style="display:inline-flex;gap:4px;align-items:center;padding:2px 8px;border-radius:20px;background:rgba(248,81,73,.15);color:' + C.live + ';font-size:11px;font-weight:800"><span style="width:6px;height:6px;border-radius:50%;background:' + C.live + '"></span>LIVE' + (sc ? ' · ' + sc : '') + (mn ? ' · ' + mn : '') + rc + '</span>';
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
  // 15.08.2026 (Lucas): live Tore-Unter = reaktiv (Uhr-Zerfall, Tor kippt es -> Lay-Verdacht).
  function reactiveUnder(m, name) { return isLive(m) && /under|unter/i.test(String(name || '')) && /goal|tore/i.test(String(name || '')); }
  function reactiveTag(m, name) { return reactiveUnder(m, name) ? ' <span style="font-size:9px;font-weight:800;padding:1px 5px;border-radius:6px;background:rgba(248,81,73,.16);color:' + C.live + '" title="Live-Unter läuft mit der Uhr runter — ein Tor kippt es. Reaktives Geld (Lay-Verdacht, Over ist die scharfe Seite).">⚠ reaktiv</span>' : ''; }
  function distRows(mk, m) {
    var rs = runnersOf(mk), tot = distTotal(mk) || 1, cols = segCols(rs.length);
    return rs.slice().sort(function (a, b) { return (+b.vol || 0) - (+a.vol || 0); }).map(function (r) {
      var i = rs.indexOf(r), pct = (+r.vol || 0) / tot * 100;
      return '<div style="display:flex;align-items:center;gap:8px;font-size:12px;margin-top:5px">' +
        '<span style="width:9px;height:9px;border-radius:2px;background:' + cols[i % cols.length] + ';flex:none"></span>' +
        '<span style="flex:1;color:' + C.ink + '">' + esc(rLabel(r.name, m)) + reactiveTag(m, r.name) + '</span>' +
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
        confBadge(m.league, mm.id) +
      '</div>' + distRows(mk, m) + '</div>';
  }
  // Komprimierte Zeile (eingeklappte Karte): geldstärkster Markt + konkreter Ausgang.
  function topLine(m, x) {
    var mk = mkOf(m, x.mm.id), lead = leadRunner(mk), tot = distTotal(mk) || 1;
    var pct = lead ? (+lead.vol || 0) / tot * 100 : 0, ht = x.mm.grp === 'HT';
    return '<div style="display:flex;align-items:center;gap:10px;margin-top:9px;padding-top:9px;border-top:1px solid ' + C.bd + '">' +
      '<span style="min-width:56px;font-size:11px;font-weight:800;color:' + (ht ? C.purp : C.mut) + '">' + x.mm.label + '</span>' +
      '<span style="font-size:12px;color:' + C.ink + ';font-weight:700">→ ' + esc(lead ? rLabel(lead.name, m) : '—') + reactiveTag(m, lead && lead.name) + '</span>' +
      '<span style="font-size:12px;font-weight:900;color:' + C.gold + '">' + pct.toFixed(0) + '%</span>' +
      '<span style="flex:1;max-width:160px">' + distBar(mk, true) + '</span>' +
      '<span style="font-size:13px;font-weight:800;color:' + C.vol + '">' + fmtE(mvolG(m, x.mm.id)) + '</span>' +
      dirBadge(m, x.mm.id, lead) +
      fuehrtTag(m, lead && lead.name) +
      confBadge(m.league, x.mm.id) +
      '<span style="font-size:11px;color:' + C.dim + '">▸ alle Märkte</span>' +
    '</div>';
  }

  function presentMarkets(m) {
    return MK.map(function (mm) { return { mm: mm, v: mvolG(m, mm.id) }; })
      .filter(function (x) { return eur(x.v) >= CHIP_FLOOR && distTotal(mkOf(m, x.mm.id)) > 0; })
      .sort(function (a, b) { return b.v - a.v; });
  }

  function shortMk(k) {
    return String(k).replace('Over/Under', 'O/U').replace(' Goals', '').replace('Both teams to Score?', 'BTTS')
      .replace('Match Odds', '1X2').replace('First Half', 'HZ1').replace('Half Time/Full Time', 'HZ/EZ')
      .replace('Half Time', 'HZ1 1X2').replace('Correct Score', 'Exakt').replace('Draw no Bet', 'DNB');
  }
  function cohPill(txt, color, bg) {
    return '<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:20px;font-size:10.5px;font-weight:700;background:' + bg + ';color:' + color + '">' + txt + '</span>';
  }
  // (03.08.2026, Lucas: „zu viele Badges, live irreführend“) — die KARTE trägt nur noch das Auf-einen-
  // Blick-Signal: Steam, und NUR vor Anpfiff (live bewegt der Spielstand die Quote, kein Wettsignal).
  // LIVE steht schon oben im koPill. Der Kohärenz-Kram (harte Abweichung, Modell-Lücken, Absorption,
  // Preis-ohne-Geld, Markt×über-Norm) wandert in den Deep-Dive (full=true) — dorthin gehört Analyse.
  function cohPillsRow(m, full) {
    var r = cohOf(m), p = [], live = isLive(m);
    if (full) {
      if (live) p.push(cohPill('● LIVE', C.live, 'rgba(248,81,73,.15)'));
      if (r.hard.length) p.push(cohPill('⚠ ' + r.hard.length + ' harte Abweichung' + (r.hard.length > 1 ? 'en' : ''), C.lay, 'rgba(248,81,73,.14)'));
      if (r.soft.length) p.push(cohPill(r.soft.length + ' Modell-Lücke' + (r.soft.length > 1 ? 'n' : ''), C.gold, 'rgba(255,184,12,.13)'));
      if (r.fl && r.fl.kind === 'steam') p.push(cohPill('↯ Steam ' + _cpp(r.fl.move) + 'pp' + (r.fl.sideName ? ' · ' + esc(String(r.fl.sideName).slice(0, 14)) : ''), C.vol, 'rgba(45,212,191,.13)'));
      if (r.fl && r.fl.kind === 'absorb') p.push(cohPill('▤ Absorption · ' + fmtE(r.fl.dv) + ' ohne Preis', C.purp, 'rgba(167,139,250,.14)'));
      if (r.fl && r.fl.kind === 'air') p.push(cohPill('◌ Preis ohne Geld', C.mut, 'rgba(139,148,158,.14)'));
      if (r.mx) p.push(cohPill(esc(shortMk(r.mx.market)) + ' ' + r.mx.ratio.toFixed(1) + '× über Norm', C.blue, 'rgba(76,194,255,.13)'));
    } else if (!live && r.fl && r.fl.kind === 'steam') {
      p.push(cohPill('↯ Steam ' + _cpp(r.fl.move) + 'pp' + (r.fl.sideName ? ' · ' + esc(String(r.fl.sideName).slice(0, 14)) : ''), C.vol, 'rgba(45,212,191,.13)'));
    }
    if (!p.length) return '';
    return '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:7px;padding-left:18px">' + p.join('') + '</div>';
  }
  function matchCard(m, maxTot) {
    var barW = Math.max(4, Math.round(cardMoney(m) / (maxTot || 1) * 100));
    var mks = presentMarkets(m), open = _bf.cardOpen[m.matchId] === true;
    var comp = mks[0];
    if (_bf.market !== 'all') {                        // Markt-Filter: komprimierte Karte auf den gewählten Markt fokussieren
      var _mmF = MK_ID[_bf.market], _mkF = _mmF && mkOf(m, _mmF.id);
      if (_mkF && distTotal(_mkF) > 0) comp = { mm: _mmF, v: mvolG(m, _mmF.id) };
    }
    var _noMoney = '<div style="margin-top:8px;color:' + C.dim + ';font-size:11px">— noch kein nennenswertes Geld je Markt —</div>';
    var inner = open
      ? (mks.length ? mks.map(function (x) { return marketBlock(m, x.mm); }).join('') : _noMoney)
      : (comp ? topLine(m, comp) : _noMoney);
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
          '</div>' + cohPillsRow(m) +
        '</div>' +
        '<div style="text-align:right;min-width:120px">' +
          '<div style="font-size:20px;font-weight:900;color:' + C.vol + '">' + fmtE(cardMoney(m)) + '</div>' +
          '<div style="font-size:10px;color:' + C.dim + '">' + esc(cardMoneyLbl(m)) + '</div>' +
          '<div style="height:5px;border-radius:3px;background:#0b0f14;overflow:hidden;margin-top:4px"><i style="display:block;height:100%;width:' + barW + '%;background:linear-gradient(90deg,' + C.vol + ',#14b8a6)"></i></div>' +
        '</div>' +
      '</div>' + inner +
      '<div style="margin-top:9px;padding-top:9px;border-top:1px solid ' + C.bd + ';display:flex;justify-content:flex-end">' +
        '<button onclick="event.stopPropagation();_bfDrawer(\'' + esc(m.matchId) + '\')" style="padding:5px 11px;border:1px solid ' + C.bd + ';border-radius:8px;background:transparent;color:' + C.blue + ';font-size:11px;font-weight:700;cursor:pointer">🔬 Kohärenz-Deep-Dive</button>' +
      '</div>' +
    '</div>';
  }

  // 14.08.2026 (Lucas): Kategorie-Liste ein-/ausklappen. Zustand in window._bfrCollapsed -> ueberlebt
  // Daten-Re-Renders; Toggle schaltet DOM direkt (kein Full-Rerender, kein Scroll-Sprung).
  window._bfrCollapsed = window._bfrCollapsed || {};
  window._bfrToggleCat = function (key) {
    window._bfrCollapsed = window._bfrCollapsed || {};
    var now = !window._bfrCollapsed[key];
    window._bfrCollapsed[key] = now;
    var el = document.getElementById('bfrcat-' + key);
    var ch = document.getElementById('bfrchev-' + key);
    if (el) el.style.display = now ? 'none' : 'block';
    if (ch) ch.textContent = now ? '\u203A' : '\u2304';   // ▸ / ▾
  };

  function section(matches, title, accent, sub) {
    if (!matches.length) return '';
    var maxTot = matches.reduce(function (a, m) { return Math.max(a, cardMoney(m)); }, 1);
    var key = title.replace(/[^a-zA-Z0-9]/g, '');
    window._bfrCollapsed = window._bfrCollapsed || {};
    var collapsed = !!window._bfrCollapsed[key];
    return '<div style="margin:6px 0 20px">' +
      '<div onclick="_bfrToggleCat(\'' + key + '\')" title="Ein-/Ausklappen" style="display:flex;align-items:baseline;gap:10px;margin:0 0 10px;padding-bottom:7px;border-bottom:2px solid ' + accent + '33;cursor:pointer;user-select:none">' +
        '<span id="bfrchev-' + key + '" style="font-size:12px;color:' + accent + '">' + (collapsed ? '\u203A' : '\u2304') + '</span>' +
        '<h2 style="margin:0;font-size:16px;color:' + accent + '">' + title + '</h2>' +
        '<span style="font-size:11px;color:' + C.dim + '">' + sub + '</span>' +
        '<span style="margin-left:auto;font-size:12px;color:' + C.mut + '">' + matches.length + ' Spiel' + (matches.length === 1 ? '' : 'e') + '</span>' +
      '</div>' +
      '<div id="bfrcat-' + key + '" style="display:' + (collapsed ? 'none' : 'block') + '">' +
        matches.map(function (m) { return matchCard(m, maxTot); }).join('') +
      '</div>' +
    '</div>';
  }

  // ── Hotspot-Leiste: konkreter Ausgang mit dem meisten Geld ──────────────────
  var HOTSPOT_MIN_SHARE = 60;   // (Lucas 02.08.) oberer Block nur mit klarer Mehrheit
  var HOTSPOT_MAX_ODD = 5.0;   // 16.08.2026 (Lucas): Geld-Mehrheit auf schwerem Außenseiter (Quote >5.0 = <20% implizit) = Lay-/Churn-Volumen, kein 'wo das Geld liegt'-Signal (Ulsan @9.80 mit 64% live hinten). Preis widerspricht.
  var HOTSPOT_MIN_EUR = 2000;   // (Lucas 04.08.) 'groesste' Einzel-Ausgaenge: Kruemel (<2K) raus. Bei Lock-Spielen (FT-Fav @<1.30 ausgeblendet) tauchte sonst ein 920-EUR-Seitenmarkt neben 24K-Positionen auf = Rausch-Liquiditaet. Nur dieser Block; Kartendetail bleibt bei CHIP_FLOOR.
  // 05.08.2026 (Lucas: 1:0 fuehrt und Kohle kommt = reaktiv, wertlos): Geld auf die bereits
  // fuehrende Mannschaft ist kein handelbares Signal — im Radar (Hotspots + Frisches Geld) abfangen.
  function _leaderTeam(m) {
    var li = m.liveInfo || {}, g1 = li.goal_v1, g2 = li.goal_v2;
    if (typeof g1 !== 'number' || typeof g2 !== 'number' || g1 === g2) return null;
    return g1 > g2 ? m.home : m.away;
  }
  function _moneyOnLeaderMk(m, mm) {
    if (!mm) return false;                       // Match-Ebene: keine Seite bekannt -> nicht filtern
    var mk = mkOf(m, mm.id), lead = mk ? leadRunner(mk) : null;
    if (!lead) return false;
    var ldr = _leaderTeam(m);
    return !!(ldr && lead.name != null && String(lead.name) === String(ldr));
  }
  function hotspots(matches) {
    var hs = [];
    matches.forEach(function (m) {
      MK.forEach(function (mm) {
        var mk = mkOf(m, mm.id); if (!mk || distTotal(mk) <= 0) return;
        var lead = leadRunner(mk); if (!lead) return;
        if (typeof lead.odd === 'number' && lead.odd < MIN_ODD_SHOW) return;   // Geld auf ~Lock-Favorit = keine Info
        if (typeof lead.odd === 'number' && lead.odd > HOTSPOT_MAX_ODD) return;   // 16.08.2026 (Lucas): Geld-Mehrheit auf schwerem Außenseiter = Exchange-Churn, kein Signal (bleibt im Deep-Dive)
        // 08.08.2026 (Lucas): Geld auf den Fuehrenden NICHT mehr rauswerfen — mit „▶ fuehrt" markiert + Back/driftet-Badge ist es ein echtes Signal.
        var v = eur(lead.vol); if (v < HOTSPOT_MIN_EUR) return;
        var pct = (+lead.vol || 0) / (distTotal(mk) || 1) * 100;
        if (pct < HOTSPOT_MIN_SHARE) return;   // 02.08.2026 (Lucas): Fast-Gleichstand raus - der Block zeigt WO das Geld liegt, nicht grosse liquide Spiele. < 60% Konzentration ist kein Signal (gehoert zu Frisches Geld).
        hs.push({ m: m, mm: mm, lead: lead, v: v, pct: pct });
      });
    });
    hs.sort(function (a, b) { return b.v - a.v; });
    return hs.slice(0, 8);
  }
  function hotspotStrip(matches) {
    var hs = hotspots(matches); if (!hs.length) return '';
    var mx = Math.max.apply(null, hs.map(function (x) { return x.v; })) || 1;
    var rows = hs.map(function (x) {
      var ht = x.mm.grp === 'HT', w = Math.max(6, Math.round(Math.min(100, x.pct)));   // Fill = Anteil des Geldes auf diesen Ausgang (nicht €/max → keine Nub-Optik)
      return '<div class="bfb-row' + _rowHl(x.m) + '" onclick="_bfJump(\'' + esc(x.m.matchId) + '\')">' +
        '<div class="bfb-lbl"><div class="bfb-g">' + flag(x.m.country, x.m.league) + ' ' + esc(String(x.m.home).slice(0, 13)) + ' – ' + esc(String(x.m.away).slice(0, 13)) + '</div>' +
        '<div class="bfb-o"><span class="bfb-mk' + (ht ? ' ht' : '') + '">' + esc(x.mm.label) + ' →</span> ' + esc(rLabel(x.lead.name, x.m)) + '</div></div>' +
        '<div class="bfb-bar"><i style="width:' + w + '%;background:' + C.vol + '"></i></div>' +
        '<div class="bfb-meta"><span class="bfb-v" style="color:' + C.vol + '">' + fmtE(x.v) + '</span><br><span class="bfb-s">' + x.pct.toFixed(0) + '%</span> <span class="bfb-odd">@' + fO(x.lead.odd) + '</span>' + dirBadge(x.m, x.mm.id, x.lead) + fuehrtTag(x.m, x.lead && x.lead.name) + _hlLine(x.m) + '</div></div>';
    }).join('');
    return '<div style="background:linear-gradient(180deg,rgba(255,184,12,.06),transparent);border:1px solid ' + C.bd + ';border-radius:14px;padding:11px 13px;margin:12px 0 14px">' +
      '<div style="font-size:12px;color:' + C.gold + ';font-weight:800;margin-bottom:10px">🔥 Wo das Geld genau liegt — größte Einzel-Ausgänge <span style="color:' + C.dim + ';font-weight:600">· Balken = Anteil des Geldes auf den Ausgang · nur klare Mehrheiten (≥60%) · ab 2K € · Klick springt zum Spiel</span></div>' +
      '<div class="bfb-grid">' + rows + '</div></div>';
  }

  // ── Frisches Geld: Zufluss seit dem letzten Update (aus der History-Delta je Markt) ──────────
  var FLOW_MIN_EUR = 10000;    // €-Zufluss erst ab so viel zeigen (21.08.2026 Lucas: 2000->10000)
  // 21.08.2026 (Lucas: Fix-Erkennung): 2. Weg — ein paar Tausend €, die den GROSSTEIL eines kleinen
  // Marktes ausmachen (duenne Liga/Markt), sind das Anomalie-/Fix-Signal, auch unter FLOW_MIN_EUR.
  var THIN_MIN_EUR = 2000;     // Duenn-Markt-Zufluss ab so viel absolut
  var THIN_SHARE   = 0.40;     // ... und >= so viel Anteil am Marktgeld
  function _flowThin(x) { var e = eur(x.delta), c = eur(x.curr); return e < FLOW_MIN_EUR && e >= THIN_MIN_EUR && c > 0 && (e / c) >= THIN_SHARE; }
  var SURGE_MIN_BASE = 1000;   // % Surge nur wenn Basis ≥ so viel € (sonst Rauschen)
  var SURGE_MIN_DELTA = 500;   // und Zuwachs ≥ so viel €
  var SURGE_MIN_PCT = 25;      // und ≥ so viel % Sprung
  function _leadOddOk(m, mm) {
    if (!mm) return true;                                  // Match-Ebene-Fallback: keine Seite bekannt -> nicht filtern
    var mk = mkOf(m, mm.id), lead = mk ? leadRunner(mk) : null;
    return !(lead && typeof lead.odd === 'number' && lead.odd < MIN_ODD_SHOW);
  }
  function flowItems(base) {
    var H = _bf.hist || {}, out = [];
    base.forEach(function (m) {
      var h = H[String(m.matchId)];
      if (!Array.isArray(h) || h.length < 2) return;
      var a = h[h.length - 2], b = h[h.length - 1];
      if (a && b && a.mkv && b.mkv) {                 // pro Markt (sobald mkv-History da ist)
        MK.forEach(function (mm) {
          var cv = +b.mkv[mm.id] || 0; if (cv <= 0) return;
          var pv = +a.mkv[mm.id] || 0, d = cv - pv;
          if (d <= 0) return;
          out.push({ m: m, mm: mm, prev: pv, curr: cv, delta: d, pct: pv > 0 ? d / pv * 100 : 999 });
        });
      } else if (a && b) {                            // Fallback: Match-Ebene (alte History ohne mkv)
        var cv2 = +b.totalVol || 0, pv2 = +a.totalVol || 0, d2 = cv2 - pv2;
        if (d2 > 0) out.push({ m: m, mm: null, prev: pv2, curr: cv2, delta: d2, pct: pv2 > 0 ? d2 / pv2 * 100 : 999 });
      }
    });
    return out;
  }
  function _flowLead(x) {
    if (!x.mm) return null;
    var mk = mkOf(x.m, x.mm.id), lead = mk ? leadRunner(mk) : null;
    if (!lead) return null;
    return { name: rLabel(lead.name, x.m), share: Math.round((+lead.vol || 0) / (distTotal(mk) || 1) * 100), odd: fO(lead.odd) };
  }
  function _flowBar(x, mode, mx) {
    var ht = x.mm && x.mm.grp === 'HT', lbl = x.mm ? x.mm.label : 'gesamt', ld = _flowLead(x);
    var _fmk = mkOf(x.m, x.mm && x.mm.id), rawLead = _fmk ? leadRunner(_fmk) : null;   // roher Runner fuer Back/Lay-Join
    var side = ld ? esc(ld.name) : '';
    // 05.08.2026 (Lucas): Quote ins Flow-Label. Ohne sie war unklar, ob das Live-Geld bei @1.74
    // (echtes Signal) oder @1.06 (Quasi-Lock nach Tor) reinkam. ld.odd = fO(lead.odd) -> '2.34' oder '-'.
    var oddTxt = (ld && ld.odd && ld.odd !== '–') ? ' <span class="bfb-odd">@' + ld.odd + '</span>' : '';
    var lblLine = '<span class="bfb-mk' + (ht ? ' ht' : '') + '">' + esc(lbl) + (side ? ' →' : '') + '</span>' + (side ? ' ' + side : '') + oddTxt;
    var bar, meta;
    if (mode === 'eur') {
      var w = Math.max(6, Math.round(Math.min(100, x.delta / mx * 100)));   // Balken = Zufluss relativ zum größten Zufluss (grün, eine Farbe)
      bar = '<div class="bfb-bar"><i style="width:' + w + '%;background:' + C.back + '"></i></div>';
      var _thinBadge = _flowThin(x) ? ' <span title="Zufluss macht ' + Math.round(eur(x.delta) / eur(x.curr) * 100) + '% des gesamten Marktgeldes aus — d\u00fcnner Markt, oft eine Liga/ein Markt, den du beim Buchmacher nicht spielen kannst. Anomalie/Fix-Kandidat." style="font-size:9px;font-weight:800;color:#f2c14e;border:1px solid rgba(234,185,56,.5);border-radius:4px;padding:0 4px">\uD83D\uDD0D d\u00fcnner Markt</span>' : '';
      meta = '<span class="bfb-v" style="color:' + C.back + '">▲ +' + fmtE(x.delta) + '</span>' + _thinBadge + '<br><span class="bfb-odd">jetzt ' + fmtE(x.curr) + '</span>' + (ld ? ' <span class="bfb-s">' + ld.share + '%</span>' : '');
    } else {
      var w = Math.max(6, Math.round(Math.min(100, x.pct / 300 * 100)));
      bar = '<div class="bfb-bar"><i style="width:' + w + '%;background:' + C.back + '"></i></div>';
      meta = '<span class="bfb-v" style="color:' + C.back + '">▲ +' + Math.round(x.pct) + '%' + (x.pct >= 200 ? ' 🚨' : '') + '</span><br><span class="bfb-odd">' + fmtE(x.prev) + '→' + fmtE(x.curr) + '</span>';
    }
    return '<div class="bfb-row' + _rowHl(x.m) + '" onclick="_bfJump(\'' + esc(x.m.matchId) + '\')">' +
      '<div class="bfb-lbl"><div class="bfb-g">' + flag(x.m.country, x.m.league) + ' ' + esc(String(x.m.home).slice(0, 13)) + ' – ' + esc(String(x.m.away).slice(0, 13)) + '</div>' +
      '<div class="bfb-o">' + lblLine + '</div></div>' + bar +
      '<div class="bfb-meta">' + meta + dirBadge(x.m, x.mm && x.mm.id, rawLead) + fuehrtTag(x.m, rawLead && rawLead.name) + _hlLine(x.m) + '</div></div>';
  }
  function _flowBars(label, items, mode) {
    if (!items.length) return '';
    var mx = mode === 'eur' ? (Math.max.apply(null, items.map(function (x) { return x.delta; })) || 1) : 1;
    return '<div class="bfb-sub">' + label + '</div><div class="bfb-grid">' + items.map(function (x) { return _flowBar(x, mode, mx); }).join('') + '</div>';
  }
  // ── 🔍 Fix-Verdacht (21.08.2026, Lucas) — HZ-Geld dominiert den FT-Markt ─────────────
  // Lucas' Erfahrung ueber Jahre: liegt auf dem HALBZEIT-Markt mehr Geld als auf Full-Time, macht das
  // technisch keinen Sinn (FT ist normal viel liquider) -> starkes Fix-Indiz. Dazu die Neben-Indizien:
  // Geld rein + Quote faellt (Back ✓) und sehr einseitig (>=90% auf einer Seite) bei kleinen Betraegen.
  // SCANNT ALLE frischen Spiele (nicht nur die ueber der Radar-Schwelle) — Fix-Spiele liegen ja gerade
  // auf duennen Maerkten UNTER der normalen Geld-Schwelle.
  var FIX_HT_MIN = 2000;   // HZ-Geld-Boden fuer den Verdacht (filtert den €8/€28-Mini-Kram)
  var FIX_RATIO_MIN = 2.0; // 22.08.2026 (Lucas): HZ muss FT KLAR dominieren (>=2x). 1.1x = nahezu ident = Rauschen.
  var FIX_LEAD_SHARE = 0.65; // 22.08.2026 (Lucas): HZ-Markt muss klar EINSEITIG sein (>=65%). 50/50-O/U ist kein Signal.
  var FIX_INPLAY_MAX_MIN = 30; // 23.08.2026 (Lucas, Admira „1 min später war Halbzeit"): HZ-Markt in-play nur bis Minute 30 — danach entscheidet die Zeit, spätes Geld auf's Sichere ist kein Fix-Signal.
  var FIX_LEAD_MIN_ODD = 1.15; // 23.08.2026 (Lucas): einseitige Seite darf nicht schon quasi entschieden sein (@1.08 = 93% = Naht-Lock) — sonst Geld auf's Offensichtliche.
  // 22.08.2026 (Lucas: „es ist grad Pause 😂"): Fix nur solange der HZ-Markt NOCH offen ist —
  // vor Anpfiff oder 1. Halbzeit. Ab Halbzeit/2. HZ/Ende ist er durch, „mehr Geld auf HZ" wertlos.
  function _fixWindowOk(m) {
    var li = m.liveInfo || {};
    if (li.finished || li.is_ht) return false;
    var t = li.time;
    if (typeof t === "number" && t > FIX_INPLAY_MAX_MIN) return false;
    return true;
  }
  function _htFtVols(m) {
    var ft = 0;
    MK.forEach(function (mm) {
      if (mm.grp === 'FT') { var v = eur(mvolG(m, mm.id)); if (v > ft) ft = v; }
    });
    // 22.08.2026 (Lucas): NICHT den volumenstaerksten HZ-Markt nehmen, sondern den mit dem groessten
    // EINSEITIGEN Geld. Ein 50/50-O/U ist kein Fix-Signal; ein klar einseitig geladener HZ-Markt schon.
    var ht = 0, htMk = null, bestLead = -1;
    MK.forEach(function (mm) {
      if (mm.grp !== 'HT') return;
      var tot = eur(mvolG(m, mm.id));
      if (tot < FIX_HT_MIN) return;
      var mk = mkOf(m, mm.id), lead = mk ? leadRunner(mk) : null, dtot = mk ? distTotal(mk) : 0;
      if (!lead || !dtot) return;
      var share = (+lead.vol || 0) / dtot;
      if (share < FIX_LEAD_SHARE) return;      // ausgewogen -> raus
      var lo = +lead.odd;
      if (lo && lo < FIX_LEAD_MIN_ODD) return; // Naht-Lock (@~1.0) -> Geld auf's Sichere, kein Fix-Signal
      var leadEur = tot * share;               // einseitiges Geld in €
      if (leadEur > bestLead) { bestLead = leadEur; ht = tot; htMk = mm.id; }
    });
    return { ft: ft, ht: ht, htMk: htMk };
  }
  function _fixCandidates(matches) {
    var out = [];
    (matches || []).forEach(function (m) {
      if (isStale(m)) return;
      var v = _htFtVols(m);
      if (v.ft > 0 && v.ht >= FIX_HT_MIN && v.ht >= v.ft * FIX_RATIO_MIN && _fixWindowOk(m)) {   // HZ >=2x FT, ueber Boden, HZ-Markt noch offen
        out.push({ m: m, ht: v.ht, ft: v.ft, htMk: v.htMk, ratio: v.ft > 0 ? v.ht / v.ft : 99 });
      }
    });
    out.sort(function (a, b) { return b.ratio - a.ratio; });   // krassestes Missverhaeltnis oben
    return out;
  }
  function fixStrip(cands) {
    var head = '<div style="font-size:12px;color:' + C.lay + ';font-weight:800;margin-bottom:8px">🔍 Fix-Verdacht — mehr Geld auf dem <b>Halbzeit</b>- als dem Full-Time-Markt <span style="color:' + C.dim + ';font-weight:600">(technisch unlogisch, klassisches Anomalie-Muster · Klick springt zum Spiel)</span></div>';
    var body;
    if (!cands || !cands.length) {
      body = '<div style="font-size:11px;color:' + C.dim + '">gerade kein Spiel, wo HZ-Geld (≥ €2K) den Full-Time-Markt übersteigt.</div>';
    } else {
      body = '<div class="bfb-grid">' + cands.slice(0, 8).map(function (c) {
        var m = c.m, mk = mkOf(m, c.htMk), lead = mk ? leadRunner(mk) : null, tot = mk ? distTotal(mk) : 0;
        var share = (lead && tot) ? Math.round((+lead.vol || 0) / tot * 100) : 0;
        var side = lead ? rLabel(lead.name, m) : '';
        var oddTxt = (lead && fO(lead.odd) !== '–') ? ' <span class="bfb-odd">@' + fO(lead.odd) + '</span>' : '';
        var back = dirBadge(m, c.htMk, lead);
        var oneSided = share >= 90 ? ' <span title="Fast alles Geld auf einer Seite bei kleinem Betrag — Achtungszeichen." style="font-size:9px;font-weight:800;color:#f2c14e;border:1px solid rgba(234,185,56,.5);border-radius:4px;padding:0 4px">' + share + '% einseitig</span>' : '';
        var htLbl = MK_ID[c.htMk] ? MK_ID[c.htMk].label : 'HZ';
        return '<div class="bfb-row' + _rowHl(m) + '" onclick="_bfJump(\'' + esc(m.matchId) + '\')">' +
          '<div class="bfb-lbl"><div class="bfb-g">' + flag(m.country, m.league) + ' ' + esc(String(m.home).slice(0, 13)) + ' – ' + esc(String(m.away).slice(0, 13)) + '</div>' +
          '<div class="bfb-o"><span class="bfb-mk ht">' + esc(htLbl) + (side ? ' →' : '') + '</span>' + (side ? ' ' + side : '') + oddTxt + '</div></div>' +
          '<div class="bfb-meta"><span class="bfb-v" style="color:' + C.lay + '">HZ ' + fmtE(c.ht) + '</span><br><span class="bfb-odd">FT ' + fmtE(c.ft) + ' · ' + (c.ft > 0 ? c.ratio.toFixed(1) + '\u00d7 mehr auf HZ' : 'FT ~0') + '</span>' + back + oneSided + '</div></div>';
      }).join('') + '</div>';
    }
    return '<div style="background:linear-gradient(180deg,rgba(248,81,73,.07),transparent);border:1px solid rgba(248,81,73,.28);border-radius:14px;padding:11px 13px;margin:0 0 14px">' + head + body + '</div>';
  }

  function flowStrip(base) {
    var items = flowItems(base);
    var eurItems = items.filter(function (x) { return (eur(x.delta) >= FLOW_MIN_EUR || _flowThin(x)) && _leadOddOk(x.m, x.mm); })   // 08.08.2026: Fuehrungs-Geld nicht filtern, „▶ fuehrt". 21.08.2026 (Lucas): + Duenn-Markt-Anomalie-Weg
      .sort(function (a, b) { return ((_flowThin(b) ? 1 : 0) - (_flowThin(a) ? 1 : 0)) || (b.delta - a.delta); }).slice(0, 8);
    var surge = items.filter(function (x) { return eur(x.prev) >= SURGE_MIN_BASE && eur(x.delta) >= SURGE_MIN_DELTA && x.pct >= SURGE_MIN_PCT && x.pct < 900 && _leadOddOk(x.m, x.mm); })
      .sort(function (a, b) { return b.pct - a.pct; }).slice(0, 6);
    var head = '<div style="font-size:12px;color:' + C.back + ';font-weight:800;margin-bottom:8px">💸 Frisches Geld — was seit dem letzten Lauf reinfloss &amp; auf welche Seite <span style="color:' + C.dim + ';font-weight:600">(Klick springt zum Spiel)</span></div>';
    var body = (!eurItems.length && !surge.length)
      ? '<div style="font-size:11px;color:' + C.dim + '">sammelt Daten — der Zufluss braucht zwei Fetches (~15–30 Min), dann siehst du hier, auf welchen Markt gerade Geld fließt.</div>'
      : _flowBars('📈 Größte Zuflüsse (€) — Balken = Zufluss relativ zum größten', eurItems, 'eur') + _flowBars('⚡ Größte Sprünge (%) — Balken = Sprung-Höhe', surge, 'pct');
    return '<div style="background:linear-gradient(180deg,rgba(63,185,80,.07),transparent);border:1px solid rgba(63,185,80,.25);border-radius:14px;padding:11px 13px;margin:0 0 14px">' + head + body + '</div>';
  }

  // ── Track-Record (Trefferquoten) ─────────────────────────────────────────────
  function trackFor(league, marketId) {
    var t = _bf.track; if (!t || !t.byLeagueMarket) return null;
    return t.byLeagueMarket[String(league) + '|' + String(marketId)] || null;
  }
  function _pctTxt(x) { return x == null ? '—' : Math.round(x * 100) + '%'; }
  function _clvTxt(x) { return x == null ? '—' : (x > 0 ? '+' : '') + (+x).toFixed(1) + 'pp'; }
  function _clvCol(x) { return x == null ? C.dim : x > 0 ? C.back : x < 0 ? C.lay : C.mut; }
  function _roiTxt(x) { return x == null ? '—' : (x >= 0 ? '+' : '') + Math.round(x * 100) + '%'; }
  function _roiCol(x) { return x == null ? C.dim : x > 0.05 ? C.back : x < -0.08 ? C.lay : C.mut; }
  // ── Was der Track-Record WIRKLICH auslöst (29.08.2026, Lucas: „was trägt, was trägt nicht") ──
  // Diese drei Zahlen sind die Spiegelung von sharp_signals/betfair_money.py. Dort entscheidet der
  // Liga×Markt-Track seit dem 29.07. über die confidence des Card-Signals — und dreht es bei
  // klarem Minus sogar UM (dem Geld dort zu folgen verliert → Fade). Sichtbar war davon nichts:
  // die Konsequenz stand als Textfragment in der Evidence-Zeile eines Picks, nirgends auf einer
  // Karte. Man sah die Zahl, aber nicht, was sie anrichtet.
  // Die Werte müssen mit betfair_money.py übereinstimmen — tests/frontend/betfair-lernboard.test.mjs
  // vergleicht beide Dateien, damit sie nicht auseinanderlaufen.
  var BF_TR_MIN_N = 15;       // = MIN_TR_N
  var BF_TR_FADE  = -0.10;    // = TR_FADE_ROI  → Signal wird umgedreht
  var BF_TR_BOOST = 0.05;     // = TR_BOOST_ROI → Signal wird verstärkt
  function bfTrackWirkung(v) {
    if (!v || !v.n || typeof v.roi !== 'number') return null;
    if (v.n < BF_TR_MIN_N) return { art: 'sammelt', txt: '⏳ sammelt', sub: 'n' + v.n + '/' + BF_TR_MIN_N, col: C.dim };
    if (v.roi <= BF_TR_FADE) return { art: 'fade', txt: '⚠️ verliert hier', sub: 'Card fadet', col: C.lay };
    if (v.roi >= BF_TR_BOOST) return { art: 'boost', txt: '✅ trägt', sub: 'Card verstärkt', col: C.back };
    return { art: 'neutral', txt: '➖ neutral', sub: 'ohne Wirkung', col: C.mut };
  }

  // Kleine Confidence-Chip an einem Markt in der Spielliste.
  function confBadge(league, marketId) {
    var v = trackFor(league, marketId);
    var w = bfTrackWirkung(v);
    // 29.08.2026: unter n=12 stand hier gar nichts — man konnte „noch keine Daten" nicht von
    // „nie hingeschaut" unterscheiden. Jetzt zeigt auch der leere Zustand seinen Fortschritt.
    if (!w) return '';
    if (w.art === 'sammelt' && v.n < 6) return '';   // unter 6 Spielen ist auch der Fortschritt Rauschen
    var stark = (w.art === 'fade' || w.art === 'boost');
    var tip = 'Track-Record ' + league + ' · ' + (MK_ID[marketId] ? MK_ID[marketId].label : marketId) +
      ': ' + _pctTxt(v.hitRate) + ' Trefferquote · ROI ' + _roiTxt(v.roi) + ' · n=' + v.n + ' — ' +
      (w.art === 'fade' ? 'dem Geld hier zu folgen verliert historisch; das Card-Signal wird umgedreht'
       : w.art === 'boost' ? 'dem Geld hier zu folgen trägt; das Card-Signal wird verstärkt'
       : w.art === 'neutral' ? 'weder klar tragend noch verlierend — das Card-Signal bleibt unverändert'
       : 'erst ab n=' + BF_TR_MIN_N + ' wirkt der Track auf das Card-Signal');
    return '<span title="' + esc(tip) + '" style="display:inline-flex;gap:5px;align-items:center;padding:1px 7px;border-radius:20px;background:'
      + (stark ? (w.art === 'boost' ? 'rgba(63,185,80,.10)' : 'rgba(248,81,73,.10)') : 'transparent')
      + ';border:1px solid ' + (stark ? (w.art === 'boost' ? 'rgba(63,185,80,.3)' : 'rgba(248,81,73,.3)') : C.bd)
      + ';font-size:10px;font-weight:700;color:' + w.col + ';opacity:' + (stark ? 1 : 0.65) + '">'
      + w.txt + (typeof v.roi === 'number' && w.art !== 'sammelt' ? ' ' + _roiTxt(v.roi) : '')
      + ' <span style="color:' + C.dim + ';font-weight:600">' + (w.art === 'sammelt' ? w.sub : 'n' + v.n) + '</span></span>';
  }

  // 17.08.2026 (Lucas): 🖥️ TERMINAL — dichtes Profi-Board + Drilldown. Rein lesend & additiv.
  // Board: Konsens (faire Pinnacle-% -> Edge) + Richtung + Poly-Gegencheck + CLV-Bucket je Liga.
  // Drilldown: Preis-Kurve (Verlauf) + Volumen, gematcht-je-Quote, inferierte Back/Lay-Richtung, ½-Kelly in €.
  function _tKoTxt(iso){ if(!iso) return '—'; var t=Date.parse(String(iso)); if(isNaN(t)) return '—';
    var m=Math.round((t-Date.now())/60000); if(m<0) return 'live'; if(m<60) return 'in '+m+'′'; return 'in '+Math.floor(m/60)+':'+('0'+(m%60)).slice(-2); }
  function _tEur(v){ v=Number(v)||0; if(v>=1e6) return '€'+(v/1e6).toFixed(1)+'M'; if(v>=1e3) return '€'+Math.round(v/1e3)+'K'; return '€'+Math.round(v); }
  function _tEdge(g){ var s=g.moneySide, p=(g.pinn&&typeof g.pinn[s]==='number')?g.pinn[s]:null; return (p&&g.moneyOdd>1)?(p*g.moneyOdd-1):null; }
  function _tFair(g){ var s=g.moneySide, p=(g.pinn&&typeof g.pinn[s]==='number')?g.pinn[s]:null; return (p&&p>0)?(1/p):null; }
  function _tBucket(g){ var t=(_bf.track&&_bf.track.byLeagueMarket)||{}; return t[(g.league||'')+'|Match Odds']||null; }
  // 17.08.2026 (Lucas P1): Auto-Mute — Zeilen, die keine handelbare Kante sind, ausgrauen & nach unten:
  // (a) kein Pinnacle-Anker (edge==null -> die illiquiden @110/@230-Ligen), (b) historisch schwacher CLV-Bucket.
  function _tMute(g){ var e=_tEdge(g), b=_tBucket(g);
    if(e==null) return {m:true,r:'kein Anker'};
    if(b && b.n>=10 && typeof b.roi==='number' && b.roi<=-0.05) return {m:true,r:'Bucket '+Math.round(b.roi*100)+'% ROI'};
    return {m:false,r:''}; }
  var _TSK={home:'hw',draw:'dr',away:'aw'};
  function _tSer(g){ var h=(_bf.hist||{})[String(g.matchId)]||[]; var key=_TSK[g.moneySide]||'hw'; var pts=[];
    for(var i=0;i<h.length;i++){ var s=h[i]; if(!s||!s.mo) continue; var o=s.mo[key];
      if(typeof o==='number'&&o>1&&s.ts){ var t=Date.parse(s.ts); if(!isNaN(t)) pts.push({t:t,o:o,v:Number(s.totalVol)||0}); } }
    pts.sort(function(a,b){return a.t-b.t;}); return pts; }
  function _tBank(){ var b=(_bf.bankroll!=null)?_bf.bankroll:1000; _bf.bankroll=b; return b; }
  function _tHalfKelly(g){ var e=_tEdge(g); return (e!=null&&e>0&&g.moneyOdd>1)?(e/(g.moneyOdd-1))*0.5:0; }
  // 17.08.2026 (Lucas P4): Cross-Source-Konviktion — die 3 Quellen (Betfair-Fluss + Pinnacle-Anker/Steam
  // + Poly-Crowd) zu EINER Zahl 0–100 verdichtet. Einig + Geld rein + Sharp-Steam → hoch; Drift/Widerspruch → runter.
  function _tConv(g){
    var v=g.verdict||'no_anchor';
    var base=v==='konsens'?60:v==='teil'?42:v==='uneinig'?8:20;
    var bf=g.moneyDir==='in'?25:g.moneyDir==='out'?-20:0;
    var mv=(typeof g.pinnMovePP==='number')?g.pinnMovePP:null;
    var steam=mv==null?0:(mv>=1?15:mv>=0.2?8:mv<=-0.5?-8:0);
    var ps=(g.poly&&typeof g.poly.sharePct==='number')?g.poly.sharePct:null;
    var poly=ps==null?0:(ps>=65?10:ps>=55?5:ps<45?-8:0);
    var s=Math.max(0,Math.min(100,base+bf+steam+poly));
    if(v==='no_anchor') s=Math.min(s,55);   // ohne Pinnacle-Anker keine „starke" Konviktion behaupten
    var label=s>=80?'🔥 Stark':s>=60?'Solide':s>=40?'Mittel':(v==='uneinig'?'⚠ Widerspruch':'Schwach');
    var col=s>=80?'#2ee08a':s>=60?'#5eead4':s>=40?'#f5c518':'#ff5d5d';
    return {score:s,label:label,col:col,base:base,bf:bf,steam:steam,poly:poly,verdict:v,ps:ps,mv:mv};
  }
  function _tConvMeter(g){ var c=_tConv(g);
    return '<div style="display:inline-flex;align-items:center;gap:6px" title="Konviktion '+c.score+'/100 · '+esc(c.label)+'">'
      +'<div style="width:46px;height:6px;background:#141c2c;border-radius:3px;overflow:hidden"><div style="height:6px;width:'+c.score+'%;background:'+c.col+'"></div></div>'
      +'<span style="font-family:monospace;font-weight:800;color:'+c.col+';font-size:11.5px">'+c.score+'</span></div>'; }
  function _tConvPanel(g){ var c=_tConv(g);
    var vtxt={konsens:'Konsens — alle Quellen sehen dieselbe Seite vorn',teil:'Teil-Konsens — Anker stimmt, eine Quelle schert aus',uneinig:'Uneinig — Buchmacher sehen die andere Seite vorn',no_anchor:'Kein Pinnacle-Anker — nur Betfair/Poly'}[c.verdict]||c.verdict;
    var srow=function(dcol,on,name,txt){ return '<div style="display:flex;align-items:center;gap:7px;margin:4px 0">'
      +'<i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:'+(on?dcol:'#26324a')+';flex:none"></i>'
      +'<span style="font-size:11px;color:'+C.mut+';width:58px;flex:none">'+name+'</span>'
      +'<span style="font-size:11px;color:'+(on?C.ink:C.dim)+'">'+txt+'</span></div>'; };
    var bfTxt=g.moneyDir==='in'?'Geld REIN (Back)':g.moneyDir==='out'?'driftet (Geld raus)':'flach';
    var pinTxt=g.pinn?((g.pinn.fav===g.moneySide?'Favorit stimmt':'Favorit ANDERS')+(c.mv!=null?' · Move '+(c.mv>0?'+':'')+c.mv+'pp':'')):'kein Pinnacle';
    var _pO=(g.poly&&typeof g.poly.odd==='number')?g.poly.odd:null;
    var polTxt=(c.ps!=null)?(c.ps+'% Crowd'+(c.ps>=55?' (einig)':c.ps<45?' (dagegen)':''))
      :(_pO!=null?('Quote '+_pO+(g.poly.vol?' · '+_tEur(g.poly.vol):'')+' · Share erst ~3h vor Anpfiff'):'kein Poly-Markt');
    return '<div style="text-align:center;margin-bottom:8px"><div style="font-size:26px;font-weight:900;font-family:monospace;color:'+c.col+';line-height:1">'+c.score+'</div>'
      +'<div style="font-size:12px;font-weight:800;color:'+c.col+'">'+esc(c.label)+'</div>'
      +'<div style="font-size:10px;color:'+C.dim+';margin-top:2px">'+esc(vtxt)+'</div></div>'
      +srow('#4cc2ff',g.moneyDir==='in',' Betfair',bfTxt)
      +srow('#5eead4',!!(g.pinn&&g.pinn.fav===g.moneySide),' Pinnacle',pinTxt)
      +srow('#a78bfa',!!((c.ps!=null&&c.ps>=55)||_pO!=null),' Poly',polTxt); }

  function _tChart(g){
    var pts=_tSer(g); if(pts.length<2) return '<div style="color:'+C.dim+';font-size:11px;padding:10px 2px">Zu wenig Verlaufsdaten für eine Kurve.</div>';
    var fair=_tFair(g);
    var W=680,H=158,pl=46,pr=58,pt=12,pb=34,cw=W-pl-pr,ch=H-pt-pb;
    var t0=pts[0].t,t1=pts[pts.length-1].t; if(t1<=t0) t1=t0+1;
    var os=pts.map(function(p){return p.o;}),mn=Math.min.apply(null,os),mx=Math.max.apply(null,os);
    if(fair!=null){ mn=Math.min(mn,fair); mx=Math.max(mx,fair); }
    var pad=(mx-mn)*0.14||0.1; mn-=pad; mx+=pad; if(mx<=mn) mx=mn+0.1;
    var X=function(t){return pl+(t-t0)/(t1-t0)*cw;};
    var Y=function(o){return pt+(mx-o)/(mx-mn)*ch;};   // konventionell: hohe Quote oben, niedrige unten (Drift steigt, Steam faellt)
    var i,line=pts.map(function(p,ix){return (ix?'L':'M')+X(p.t).toFixed(1)+' '+Y(p.o).toFixed(1);}).join(' ');
    var area=line+' L'+X(pts[pts.length-1].t).toFixed(1)+' '+(pt+ch).toFixed(1)+' L'+X(pts[0].t).toFixed(1)+' '+(pt+ch).toFixed(1)+' Z';
    var maxdv=1; for(i=1;i<pts.length;i++){ var dv=pts[i].v-pts[i-1].v; if(dv>maxdv) maxdv=dv; }
    var vb='',bw=Math.max(1,cw/pts.length*0.6);
    for(i=1;i<pts.length;i++){ var dv2=pts[i].v-pts[i-1].v; if(dv2<=0) continue; var hh=dv2/maxdv*24, up=pts[i].o<pts[i-1].o;
      vb+='<rect x="'+(X(pts[i].t)-bw/2).toFixed(1)+'" y="'+(H-pb+8-hh).toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+hh.toFixed(1)+'" fill="'+(up?'#2ee08a':'#ff5d5d')+'" opacity="0.5"/>'; }
    var ticks=''; for(i=0;i<3;i++){ var ov=mn+(mx-mn)*(i/2), yy=Y(ov);
      ticks+='<line x1="'+pl+'" y1="'+yy.toFixed(1)+'" x2="'+(pl+cw)+'" y2="'+yy.toFixed(1)+'" stroke="'+C.bd+'" stroke-width="0.5" opacity="0.5"/>'
        +'<text x="'+(pl-6)+'" y="'+(yy+3).toFixed(1)+'" text-anchor="end" font-size="9" fill="'+C.dim+'" font-family="monospace">'+ov.toFixed(2)+'</text>'; }
    var fairEl=''; if(fair!=null&&fair>=mn&&fair<=mx){ var fy=Y(fair);
      fairEl='<line x1="'+pl+'" y1="'+fy.toFixed(1)+'" x2="'+(pl+cw)+'" y2="'+fy.toFixed(1)+'" stroke="#5eead4" stroke-width="1" stroke-dasharray="4 3"/>'
        +'<text x="'+(pl+cw+4)+'" y="'+(fy+3).toFixed(1)+'" font-size="9" fill="#5eead4" font-family="monospace">fair '+fair.toFixed(2)+'</text>'; }
    var koEl='',kt=Date.parse(String(g.kickoff||'')); if(!isNaN(kt)&&kt>=t0&&kt<=t1){ var kx=X(kt);
      koEl='<line x1="'+kx.toFixed(1)+'" y1="'+pt+'" x2="'+kx.toFixed(1)+'" y2="'+(pt+ch)+'" stroke="'+C.gold+'" stroke-width="1" stroke-dasharray="2 3" opacity="0.7"/>'
        +'<text x="'+(kx+3).toFixed(1)+'" y="'+(pt+9)+'" font-size="8.5" fill="'+C.gold+'">Anpfiff</text>'; }
    var last=pts[pts.length-1];
    var dotEl='<circle cx="'+X(last.t).toFixed(1)+'" cy="'+Y(last.o).toFixed(1)+'" r="3.5" fill="#4cc2ff"/>'
      +'<text x="'+(X(last.t)-6).toFixed(1)+'" y="'+(Y(last.o)-6).toFixed(1)+'" font-size="9.5" fill="#4cc2ff" font-family="monospace" text-anchor="end">'+last.o.toFixed(2)+'</text>';
    return '<svg viewBox="0 0 '+W+' '+H+'" width="100%" style="max-width:'+W+'px;display:block">'
      +ticks+vb
      +'<path d="'+area+'" fill="rgba(76,194,255,.08)"/>'
      +'<path d="'+line+'" fill="none" stroke="#4cc2ff" stroke-width="1.6"/>'
      +fairEl+koEl+dotEl
      +'<text x="'+pl+'" y="'+(H-6)+'" font-size="8.5" fill="'+C.dim+'">Opening</text>'
      +'<text x="'+(pl+cw)+'" y="'+(H-6)+'" font-size="8.5" fill="'+C.dim+'" text-anchor="end">jetzt</text>'
      +'</svg>';
  }

  function _tMBP(g){
    var pts=_tSer(g); if(pts.length<2) return '';
    var bins={},any=false,i;
    for(i=1;i<pts.length;i++){ var dv=pts[i].v-pts[i-1].v; if(dv<=0) continue; var o=pts[i].o, step=o<4?0.05:0.2, b=+(Math.round(o/step)*step).toFixed(2); bins[b]=(bins[b]||0)+dv; any=true; }
    if(!any) return '';
    var arr=Object.keys(bins).map(function(k){return {o:+k,v:bins[k]};});
    arr.sort(function(a,b){return b.v-a.v;}); arr=arr.slice(0,7); arr.sort(function(a,b){return a.o-b.o;});
    var max=Math.max.apply(null,arr.map(function(x){return x.v;}))||1;
    return arr.map(function(x){ var w=Math.round(x.v/max*100);
      return '<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'
        +'<span style="width:44px;font-family:monospace;font-size:11px;color:'+C.ink+';text-align:right">'+x.o.toFixed(2)+'</span>'
        +'<div style="flex:1;background:#141c2c;border-radius:4px;overflow:hidden;height:12px"><div style="height:12px;width:'+w+'%;background:linear-gradient(90deg,#2ee08a,#4cc2ff)"></div></div>'
        +'<span style="width:58px;font-family:monospace;font-size:10.5px;color:'+C.mut+';text-align:right">'+_tEur(x.v)+'</span></div>'; }).join('');
  }

  // 18.08.2026 (Lucas: „im Terminal ist nur 1X2 abgedeckt, kein Over/Under — im Drilldown die anderen
  // Märkte auch zeigen"): Neben Match Odds trägt Betfair pro Spiel Über/Unter, BTTS, DNB, 1.HZ … mit
  // echtem Matched-Volumen. Consensus-Game hat die nicht, betfair_prices.json (=_bf.data.matches) schon
  // → per matchId verknüpfen. Rein lesend, kein Pinnacle-Anker auf diesen Märkten → kein Edge/Stake,
  // nur „wo liegt sonst das Geld + Back/driftet-Richtung".
  function _tMkShort(k){
    return String(k)
      .replace('Over/Under ','Ü/U ').replace(' Goals','')
      .replace('Both Teams to Score?','BTTS').replace('Both teams to Score?','BTTS')
      .replace('Draw no Bet','Unentschieden-frei')
      .replace('First Half Goals ','1.HZ Tore ')
      .replace('Half Time/Full Time','HZ/EZ').replace('Half Time Score','HZ-Ergebnis').replace('Half Time','Halbzeit')
      .replace('Correct Score','Exakt-Ergebnis');
  }
  function _tOtherMarkets(g){
    var arr=(_bf.data&&_bf.data.matches)||[], m=null, i;
    for(i=0;i<arr.length;i++){ if(String(arr[i].matchId)===String(g.matchId)){ m=arr[i]; break; } }
    if(!m||!m.markets) return '';
    var PT=g.pinnTotals||null;
    function _ouEdge(x){
      if(!PT) return null;
      var lm=String(x.k).match(/^Over\/Under ([0-9.]+) Goals$/); if(!lm) return null;
      var pt=PT[lm[1]]; if(!pt||typeof pt.overFair!=='number') return null;
      var oOdd=null,uOdd=null;
      runnersOf(x.mk).forEach(function(r){ var nm=String(r&&r.name||'').toLowerCase(), od=+r.odd;
        if(!(od>1)) return;
        if(nm.indexOf('over')===0) oOdd=od; else if(nm.indexOf('under')===0) uOdd=od; });
      if(oOdd&&uOdd){ var io=1/oOdd, iu=1/uOdd, bfO=io/(io+iu);
        if(Math.abs(bfO-pt.overFair)>0.25) return null; }
      var eO=(oOdd!=null)?pt.overFair*oOdd-1:null;
      var eU=(uOdd!=null&&typeof pt.underFair==='number')?pt.underFair*uOdd-1:null;
      var e=null,side=''; if(eO!=null){e=eO;side='Über';} if(eU!=null&&(e==null||eU>e)){e=eU;side='Unter';}
      if(e==null) return null;
      if(Math.abs(e)>0.35) return null;
      return {e:e,side:side};
    }
    var list=[];
    for(var k in m.markets){ if(k==='Match Odds') continue;
      // 18.08.2026 (Lucas): Correct Score / Half Time Score raus — nie gebraucht, nur Rauschen.
      if(k.indexOf('Correct Score')>=0 || k.indexOf('Half Time Score')>=0) continue;
      var v=distTotal(m.markets[k]); if(!(v>=50)) continue;
      var it={k:k,v:v,mk:m.markets[k]}; it.edge=_ouEdge(it); list.push(it); }
    if(!list.length) return '';
    list.sort(function(a,b){
      var av=(a.edge&&a.edge.e>=0.02)?1:0, bv=(b.edge&&b.edge.e>=0.02)?1:0;
      if(av!==bv) return bv-av;
      if(av&&bv) return b.edge.e-a.edge.e;
      return b.v-a.v; });
    var top=list.slice(0,7), rest=list.length-top.length;
    var totOther=list.reduce(function(a,x){return a+x.v;},0);
    var nEdge=list.filter(function(x){return x.edge&&x.edge.e>=0.02;}).length;
    var hasPT=!!(PT&&Object.keys(PT).length);
    // eine Marktseite: Name @Quote (+ Back/driftet an DIESER Seite) · matched € · Anteil%
    function sideCell(r, x, isLead, alignRight){
      if(!r) return '<div style="min-width:128px"></div>';
      var c=isLead?'#4cc2ff':C.ink, tV=x.v||0, pct=tV>0?Math.round((+r.vol||0)/tV*100):0;
      return '<div style="min-width:128px;text-align:'+(alignRight?'right':'left')+'">'
        +'<span style="font-family:monospace;font-weight:'+(isLead?'800':'600')+';color:'+c+';font-size:11.5px">'+esc(rLabel(r.name,m))+' <span style="color:#5eead4">@'+fO(r.odd)+'</span></span>'+dirBadge(m,x.k,r)
        +'<div style="font-family:monospace;font-size:10px;color:'+C.mut+';margin-top:1px">'+_tEur(+r.vol||0)+' <span style="color:'+C.dim+'">· '+pct+'%</span></div></div>';
    }
    var body=top.map(function(x){
      var rs=runnersOf(x.mk).filter(function(r){return r&&r.name;}).slice()
              .sort(function(a,b){ return (+b.vol||0)-(+a.vol||0); });
      var lead=rs[0]||{}, other=(rs.length===2?rs[1]:null), tV=x.v||0;
      var lPct=tV>0?Math.round((+lead.vol||0)/tV*100):0, oPct=other?(100-lPct):0;
      var bar= other
        ? '<div style="display:flex;height:9px;width:84px;flex:none;border-radius:5px;overflow:hidden;background:'+C.bd+'"><div style="width:'+lPct+'%;background:#4cc2ff"></div><div style="width:'+oPct+'%;background:#2b6e93"></div></div>'
        : '<div style="width:84px;flex:none;text-align:center;color:'+C.dim+';font-size:10px">'+(rs.length>2?(rs.length+' Runner'):'')+'</div>';
      var moneyCell='<div style="display:flex;align-items:center;gap:10px">'+sideCell(lead,x,true,true)+bar+(other?sideCell(other,x,false,false):'<div style="min-width:128px"></div>')+'</div>';
      var eCell, hot=false;
      if(x.edge){ var e=x.edge.e; hot=(e>=0.02);
        var ec=e>=0.02?'#2ee08a':e>=-0.01?'#f5c518':C.dim;
        eCell='<span style="color:'+ec+';font-family:monospace;font-weight:800;font-size:12px">'+(e>=0?'+':'')+(e*100).toFixed(1)+'%</span> <span style="color:'+C.dim+';font-size:10px">'+x.edge.side+'</span>';
      } else { eCell='<span style="color:'+C.dim+';font-size:11px" title="kein Pinnacle-Total auf dieser Linie">—</span>'; }
      return '<tr style="border-top:1px solid rgba(255,255,255,.05)'+(hot?';border-left:2px solid #2ee08a':'')+'">'
        +'<td style="padding:7px 8px;color:'+C.ink+';font-size:12px;font-weight:600;white-space:nowrap;vertical-align:top">'+esc(_tMkShort(x.k))+'</td>'
        +'<td style="padding:7px 8px">'+moneyCell+'</td>'
        +'<td style="padding:7px 8px;text-align:right;white-space:nowrap;vertical-align:top">'+eCell+'</td>'
        +'<td style="padding:7px 8px;text-align:right;font-family:monospace;font-size:11.5px;color:'+C.mut+';white-space:nowrap;vertical-align:top">'+_tEur(x.v)+'</td>'
        +'</tr>';
    }).join('');
    var col2='background:'+C.card+';border:1px solid '+C.bd+';border-radius:10px;padding:10px 12px';
    var th=function(t,a){ return '<th style="font-size:9.5px;letter-spacing:.05em;text-transform:uppercase;color:'+C.dim+';text-align:'+(a||'right')+';padding:3px 8px">'+t+'</th>'; };
    return '<div style="'+col2+';margin-top:12px">'
      +'<div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:6px">'
        +'<span style="font-size:11px;color:'+C.dim+'">Andere Märkte — wo sonst das Geld liegt · Betfair matched</span>'
        +'<span style="font-size:10px;color:'+C.mut+'">'+_tEur(totOther)+' neben 1X2'+(rest>0?(' · +'+rest+' weitere'):'')
          +(hasPT?(nEdge?(' · <span style="color:#2ee08a;font-weight:700">'+nEdge+' O/U-Kante'+(nEdge>1?'n':'')+' ≥ +2%</span>'):' · keine O/U-Kante ≥ +2%'):'')+'</span></div>'
      +'<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse">'
        +'<thead><tr>'+th('Markt','left')+th('Wo das Geld liegt · <span style="color:#4cc2ff">mehr</span> ←→ Gegenseite (Quote · matched €)','left')+th('Edge vs Pinnacle')+th('Fluss ges.')+'</tr></thead><tbody>'+body+'</tbody></table></div>'
      +'<div style="font-size:10px;color:'+C.mut+';margin-top:8px;line-height:1.55">Je Markt beide Seiten mit Quote, gematchtem € und Anteil; der Balken zeigt das Verhältnis (<span style="color:#4cc2ff">blau</span> = mehr Geld). „Back ✓/driftet" steht an der Seite, für die es gilt (aus dem Quotenverlauf). '
        +'Edge vs Pinnacle = faire O/U-% (de-viggt, neuester Pinnacle-Snap) × Betfair-Quote − 1, beste Seite; grün ≥ +2%. '
        +(hasPT?'':'<b>Noch keine Pinnacle-Totals im Datensatz</b> — erscheinen nach dem nächsten Betfair-Lauf. ')
        +'Linien ohne Pinnacle-Total (BTTS, Ecken, 1.HZ …) bleiben ohne Edge.</div>'
      +'</div>';
  }
  // 26.08.2026 (Lucas): Das Terminal zeigte in der Pick-Spalte immer die GELD-Seite von Betfair,
  // nie unseren eigenen Pick — man sah also nicht, ob die Boerse mit uns oder gegen uns steht.
  // Der Link kommt fertig aus betfair_card_link.py (Namens-Bruecke lebt in Python, getestet).
  // WICHTIG: Das ist Information, KEIN zweites Urteil. Die Engine bleibt die einzige Instanz,
  // die Picks bewertet — das Terminal stuft nie etwas herab.
  function _tCardLink(g){ var m=(_bf.cardLink&&_bf.cardLink.links)||{}; return m[String(g&&g.matchId)]||null; }
  // agree: true = Geld auf unserer Seite · false = dagegen · null = andere Achse (Tore/Ecken/BTTS),
  // da gibt es nichts zu vergleichen und wir behaupten auch nichts.
  function _tCardMark(c){
    if(!c) return {t:'',col:C.dim,txt:''};
    // 28.08.2026 (Lucas: „wieso wird ein Ue/U-Pick nicht mit der Over-Seite verglichen?"):
    // Tor- und BTTS-Picks werden jetzt gegen den passenden Boersen-Markt geprueft, nicht mehr
    // achselzuckend uebergangen. Im Text steht, WORAUF sich das Urteil stuetzt — 87 % von
    // 7.039 EUR ist eine andere Aussage als 87 % von 30 EUR.
    var basis = '';
    if(c.achse==='tor' && c.torMarkt){
      basis = ' \u00b7 ' + c.torMarkt + ' ' + (c.torSeite||'') + ': ' + (c.torSharePct!=null?c.torSharePct+'% von ':'')
            + (c.torEur!=null?_tEur(c.torEur):'?');
    } else if(c.achse==='1X2'){
      basis = ' \u00b7 1X2-Geldseite';
    }
    if(c.agree===true)  return {t:'\u25cf',col:'#2ee08a',txt:'Geld auf unserer Seite'+basis};
    if(c.agree===false) return {t:'\u25cf',col:'#ff5d5d',txt:'Geld steht gegen unsere Card'+basis};
    return {t:'\u25cb',col:C.dim,txt:'kein Boersen-Markt zum Vergleichen'};
  }
  function _tCardCell(g){
    var c=_tCardLink(g);
    if(!c) return '<span style="color:'+C.dim+';font-size:10.5px">keine Card</span>';
    var mk=_tCardMark(c);
    var odd=(c.odds!=null)?(' <span style="color:#5eead4">@'+c.odds+'</span>'):'';
    // 28.08.2026: `sc` kommt aus liga-data.json und ist der convictionScore auf der 0-10-Skala,
    // KEIN Anteil. `*100` haette daraus „Konviktion 600%" gemacht.
    // Duenner Tor-Markt: „87 % des Geldes" heisst bei 40 EUR wenig. Sichtbar machen statt
    // so zu tun, als waere jede Mehrheit gleich viel wert.
    var duenn=(c.achse==='tor' && typeof c.torEur==='number' && c.torEur<500)
      ? ' <span style="color:'+C.dim+'" title="nur '+_tEur(c.torEur)+' im Tor-Markt">(d\u00fcnn)</span>' : '';
    var sc=(typeof c.sc==='number')?('<div style="font-size:9.5px;color:'+C.dim+'">Konviktion '+c.sc+'/10'+(c.verdict?(' \u00b7 '+esc(c.verdict)):'')+(c.nPicks>1?(' \u00b7 +'+(c.nPicks-1)+' weitere'):'')+duenn+'</div>'):'';
    return '<span title="'+esc(mk.txt)+'" style="color:'+mk.col+';margin-right:4px">'+mk.t+'</span>'
      +'<span style="font-family:monospace">'+esc(c.icon||'')+' '+esc(c.market||'')+odd+'</span>'+sc;
  }
  function _tDrawer(g){
    var edge=_tEdge(g),fair=_tFair(g),pts=_tSer(g),bank=_tBank(),hk=_tHalfKelly(g),stake=bank*hk;
    var dir='',dcol=C.mut; if(pts.length>=2){ var d=pts[pts.length-1].o-pts[0].o;
      if(d< -0.01){ dir='BACK — Quote von '+pts[0].o.toFixed(2)+' auf '+pts[pts.length-1].o.toFixed(2)+' gekürzt (Geld rein)'; dcol='#2ee08a'; }
      else if(d>0.01){ dir='DRIFT — Quote von '+pts[0].o.toFixed(2)+' auf '+pts[pts.length-1].o.toFixed(2)+' gestiegen (Geld raus)'; dcol='#ff5d5d'; }
      else { dir='flach — kaum Bewegung ('+pts[0].o.toFixed(2)+' → '+pts[pts.length-1].o.toFixed(2)+')'; } }
    var col2='background:'+C.card+';border:1px solid '+C.bd+';border-radius:10px;padding:10px 12px';
    var kelly= (edge!=null&&edge>0)
      ? '<div style="font-size:22px;font-weight:900;color:#2ee08a;font-family:monospace">'+_tEur(stake)+'</div><div style="font-size:10.5px;color:'+C.mut+';margin-top:2px">½-Kelly · '+(hk*100).toFixed(1)+'% der Bankroll ('+_tEur(bank)+')</div>'
      : '<div style="font-size:15px;font-weight:800;color:'+C.dim+'">kein Stake</div><div style="font-size:10.5px;color:'+C.mut+';margin-top:2px">keine positive Kante — '+(edge==null?'kein Pinnacle-Anker':'Edge '+(edge*100).toFixed(1)+'%')+'</div>';
    return '<div style="padding:12px 4px 6px">'
      +'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">'
        +'<div style="flex:2;min-width:300px;'+col2+'">'
          +'<div style="font-size:11px;color:'+C.dim+';margin-bottom:4px">Quotenverlauf '+esc(g.moneyName)+' (Money-Seite) · faire Pinnacle-Linie gestrichelt · Balken = Zufluss</div>'
          +_tChart(g)+'</div>'
        +'<div style="flex:1;min-width:180px;'+col2+'"><div style="font-size:11px;color:'+C.dim+';margin-bottom:2px">Konviktion (3 Quellen)</div>'+_tConvPanel(g)+'</div>'
        +'<div style="flex:1;min-width:150px;'+col2+';display:flex;flex-direction:column;justify-content:center;text-align:center">'+kelly+'</div>'
      +'</div>'
      +'<div style="display:flex;gap:12px;flex-wrap:wrap">'
        +'<div style="flex:1;min-width:240px;'+col2+'"><div style="font-size:11px;color:'+C.dim+';margin-bottom:6px">Gematcht je Quote — wo floss das Geld</div>'+(_tMBP(g)||'<span style="color:'+C.dim+';font-size:11px">kein Zufluss im Verlauf</span>')+'</div>'
        +'<div style="flex:1;min-width:240px;'+col2+'">'
          +'<div style="font-size:11px;color:'+C.dim+';margin-bottom:6px">Richtung (aus Quotenverlauf inferiert)</div>'
          +'<div style="font-size:12.5px;font-weight:700;color:'+dcol+';line-height:1.5">'+dir+'</div>'
          +'<div style="font-size:10.5px;color:'+C.mut+';margin-top:8px;line-height:1.5">Edge '+(edge==null?'—':(edge>=0?'+':'')+(edge*100).toFixed(1)+'%')+' · faire Quote '+(fair==null?'—':fair.toFixed(2))+' vs. angeboten '+(g.moneyOdd||'—')+'. Kein Orderbuch — Betwatch liefert nur gematchtes Volumen, Richtung ist inferiert.</div>'
        +'</div>'
      +'</div>'
      +_tOtherMarkets(g)
      +'</div>';
  }

  function renderTerminal(){
    var cx=_bf.consensus, games=((cx&&cx.games)||[]).slice();
    if(!games.length) return viewToggle()+'<div style="padding:44px;text-align:center;color:'+C.mut+'">Noch keine Konsens-Daten — das Terminal füllt sich mit dem nächsten Betfair-Lauf.</div>';
    var bank=_tBank();
    var rows=games.map(function(g){ return {g:g,edge:_tEdge(g),b:_tBucket(g),hk:_tHalfKelly(g),mute:_tMute(g)}; });
    rows.sort(function(a,b){ var am=a.mute.m?1:0,bm=b.mute.m?1:0; if(am!==bm) return am-bm; return (b.edge==null?-9:b.edge)-(a.edge==null?-9:a.edge); });
    var nMuted=rows.filter(function(r){return r.mute.m;}).length, hideMuted=!!_bf.termHideMuted;
    var shown=hideMuted?rows.filter(function(r){return !r.mute.m;}):rows;
    var eCol=function(e){ return e==null?C.mut:e>=0.02?'#2ee08a':e>=-0.01?'#f5c518':'#ff5d5d'; };
    var dot=function(on,c){ return '<i style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:3px;background:'+(on?c:'#26324a')+'"></i>'; };
    var th=function(t,a){ return '<th style="font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;color:'+C.dim+';font-weight:700;text-align:'+(a||'right')+';padding:7px 10px;border-bottom:1px solid '+C.bd+';white-space:nowrap">'+t+'</th>'; };
    var head='<div style="display:flex;align-items:baseline;gap:10px;margin:2px 0 8px;flex-wrap:wrap"><span style="font-size:13px;font-weight:800;color:'+C.ink+'">🖥️ Terminal — handelbare Kanten</span>'
      +'<span style="font-size:10.5px;color:'+C.dim+'">Edge = faire Pinnacle-% × Quote − 1 · Konviktion = Betfair-Fluss + Pinnacle-Steam + Poly (0–100) · CLV-Bucket = hist. Kante je Liga (n≥10) · Unsere Card = der gepostete Pick; ● grün/rot = Geld auf unserer Seite / dagegen · gemutet = nicht handelbar · Zeile klicken → Drilldown</span></div>';
    var bankBar='<div style="display:flex;align-items:center;gap:8px;margin:0 0 10px;font-size:11.5px;color:'+C.mut+'">Bankroll <span style="color:'+C.dim+'">€</span>'
      +'<input type="number" value="'+bank+'" min="0" step="50" onchange="_bfTermBank(this.value)" onclick="event.stopPropagation()" style="width:96px;background:'+C.card+';border:1px solid '+C.bd+';border-radius:7px;color:'+C.ink+';padding:4px 8px;font-family:monospace;font-size:12px"/>'
      +'<span style="color:'+C.dim+'">→ ½-Kelly-Stakes in € je Zeile</span>'
      +(nMuted?'<label style="margin-left:auto;display:inline-flex;align-items:center;gap:6px;cursor:pointer;color:'+C.mut+'"><input type="checkbox" '+(hideMuted?'checked':'')+' onchange="_bfTermMute(this.checked)" onclick="event.stopPropagation()" style="cursor:pointer"/> '+nMuted+' gemutet ausblenden</label>':'')
      +'</div>';
    var out=viewToggle()+head+bankBar+'<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12.5px">'
      +'<thead><tr>'+th('Anpfiff','left')+th('Spiel','left')+th('Geld-Seite','left')+th('Unsere Card','left')+th('Edge')+th('Konviktion')+th('Fluss')+th('CLV-Bucket')+th('½-Kelly €')+'</tr></thead><tbody>';
    var mutedStarted=false;
    shown.forEach(function(r){
      var g=r.g,e=r.edge,open=(String(_bf.termOpen)===String(g.matchId));
      if(r.mute.m && !mutedStarted){ mutedStarted=true; out+='<tr><td colspan="9" style="padding:10px 10px 4px;font-size:10px;color:'+C.dim+';border-top:1px dashed '+C.bd+'">🔇 Nicht handelbar (gemutet) — kein Pinnacle-Anker oder historisch schwacher Bucket. Nach unten sortiert.</td></tr>'; }
      var dirTag=g.moneyDir==='in'?'<span style="font-size:8.5px;font-weight:800;color:#2ee08a;background:rgba(46,224,138,.14);padding:1px 5px;border-radius:5px">BACK</span>'
                 :g.moneyDir==='out'?'<span style="font-size:8.5px;font-weight:800;color:#ff5d5d;background:rgba(255,93,93,.14);padding:1px 5px;border-radius:5px">DRIFT</span>':'';
      var conv=_tConvMeter(g);
      var clv=(r.b&&r.b.n>=10)?('<span style="font-family:monospace;font-size:10.5px;font-weight:700;padding:1px 6px;border-radius:5px;color:'+(r.b.roi>0?'#2ee08a':r.b.roi<0?'#ff5d5d':C.mut)+';background:'+(r.b.roi>0?'rgba(46,224,138,.1)':r.b.roi<0?'rgba(255,93,93,.1)':'transparent')+'">'+(r.b.roi>0?'🟢':r.b.roi<0?'🔴':'⚪')+' '+Math.round(r.b.hitRate*100)+'% · n'+r.b.n+'</span>'):'<span style="color:'+C.dim+';font-size:10px">dünn</span>';
      var ko=g.live?'<span style="color:#ff5d5d;font-weight:700;font-family:monospace">● LIVE</span>':'<span style="font-family:monospace;color:'+C.mut+'">'+_tKoTxt(g.kickoff)+'</span>';
      var stakeCell=r.hk>0?('<b>'+_tEur(bank*r.hk)+'</b> <span style="color:'+C.dim+';font-weight:600">'+(r.hk*100).toFixed(1)+'%</span>'):'—';
      out+='<tr onclick="_bfTermOpen(\''+g.matchId+'\')" style="border-bottom:1px solid rgba(255,255,255,.045);cursor:pointer;opacity:'+(r.mute.m?'0.5':'1')+';background:'+(open?'rgba(76,194,255,.06)':'transparent')+'">'
        +'<td style="padding:7px 10px">'+ko+'</td>'
        +'<td style="padding:7px 10px"><span style="color:'+C.dim+';margin-right:4px">'+(open?'▾':'▸')+'</span><b>'+esc(g.home)+'</b> <span style="color:'+C.dim+'">v '+esc(g.away)+'</span><div style="font-size:10px;color:'+C.dim+';padding-left:14px">'+esc(g.league||'')+'</div></td>'
        +'<td style="padding:7px 10px;font-family:monospace"><b>'+esc(g.moneyName)+'</b> <span style="color:#5eead4">@'+(g.moneyOdd||'—')+'</span>'+(r.mute.m?' <span style="font-family:system-ui;font-size:8.5px;color:'+C.dim+';border:1px solid '+C.bd+';padding:0 4px;border-radius:4px;white-space:nowrap">🔇 '+esc(r.mute.r)+'</span>':'')+'</td>'
        +'<td style="padding:7px 10px">'+_tCardCell(g)+'</td>'
        +'<td style="padding:7px 10px;text-align:right;font-family:monospace;font-weight:800;color:'+eCol(e)+'">'+(e==null?'—':(e>=0?'+':'')+(e*100).toFixed(1)+'%')+'</td>'
        +'<td style="padding:7px 10px;text-align:right;white-space:nowrap">'+conv+'</td>'
        +'<td style="padding:7px 10px;text-align:right;font-family:monospace;white-space:nowrap">'+_tEur(g.totVol)+' '+dirTag+'</td>'
        +'<td style="padding:7px 10px;text-align:right">'+clv+'</td>'
        +'<td style="padding:7px 10px;text-align:right;font-family:monospace;font-weight:700;color:'+(r.hk>0?C.ink:C.dim)+'">'+stakeCell+'</td>'
        +'</tr>';
      if(open){ out+='<tr style="background:rgba(76,194,255,.03)"><td colspan="9" style="padding:0 10px 6px">'+_tDrawer(g)+'</td></tr>'; }
    });
    out+='</tbody></table></div>';
    out+='<div style="font-size:10px;color:'+C.dim+';margin-top:9px;line-height:1.5">Fluss = gematchtes Volumen (Betwatch); Richtung aus dem Quotenverlauf inferiert (nicht Back/Lay-Orderbuch). ½-Kelly in € aus deiner Bankroll, nur bei positiver Edge. Zeile klicken für Preis-Kurve, gematcht-je-Quote & Richtung.</div>';
    return out;
  }

  function viewToggle() {
    var b = function (id, lbl) { var on = _bf.view === id; return '<button onclick="_bfSetView(\'' + id + '\')" style="padding:6px 13px;border:1px solid ' + (on ? C.gold : C.bd) + ';background:' + (on ? 'rgba(255,184,12,.12)' : 'transparent') + ';color:' + (on ? C.gold : C.mut) + ';font-size:12px;font-weight:700;cursor:pointer">' + lbl + '</button>'; };
    return '<div style="display:inline-flex;border-radius:9px;overflow:hidden;border:1px solid ' + C.bd + ';margin:6px 0 12px">' + b('live', '🔴 Live-Radar') + b('record', '📊 Trefferquoten') + b('push', '📈 Push-Bilanz') + b('consensus', '🧭 Konsens') + b('terminal', '🖥️ Terminal') + '</div>';
  }

  // 05.08.2026 (Lucas: wissen wir, ob die Kohle erfolgreich war?): DIE Gesamt-Bilanz. Bisher gab es
  // nur Liga×Markt-Buckets (je winzig → sagt einzeln nichts). Diese Kopfzeile rollt ALLE abgerechneten
  // Signale auf: hat das Geld-folgen überhaupt Gewinn gebracht — und in WELCHEM Markt steckt die Kante.
  // 01.09.2026 (Lucas: „kann es sein dass da schon ewig 8000 steht"). Konnte es: der Ledger war auf
  // 8000 Zeilen gedeckelt, das waren bei ~1.300 Abrechnungen/Tag exakt SECHS Tage — die Zahl sah nach
  // Gesamthistorie aus und war ein rollendes Fenster. Seit dem 01.09. steht neben der Zahl immer, wie
  // viele Tage sie abdeckt. Fehlt `fenster` (Aggregat noch aus der Zeit davor), steht dort nichts
  // Erfundenes, sondern gar nichts.
  function _fensterTxt(t) {
    var f = t && t.fenster; if (!f || typeof f.tage !== 'number') return '';
    var d = function (iso) { return iso ? new Date(iso).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit' }) : '?'; };
    return f.tage.toFixed(f.tage < 10 ? 1 : 0) + ' Tage · ' + d(f.von) + '–' + d(f.bis);
  }

  function trackHeadline(t) {
    var g = t && t.global; if (!g || !g.n) return '';
    var kpi = function (lbl, val, col, sub) {
      return '<div style="flex:1;min-width:118px;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:12px;padding:11px 13px">'
        + '<div style="font-size:10px;color:' + C.dim + ';text-transform:uppercase;letter-spacing:.4px">' + lbl + '</div>'
        + '<div style="font-size:21px;font-weight:900;color:' + (col || C.ink) + ';margin-top:3px">' + val + '</div>'
        + (sub ? '<div style="font-size:9.5px;color:' + C.dim + ';margin-top:1px">' + sub + '</div>' : '') + '</div>';
    };
    var kpis = '<div style="display:flex;gap:9px;flex-wrap:wrap;margin-bottom:10px">'
      + kpi('Signale', g.n, C.ink, g.wins + ' getroffen' + (_fensterTxt(t) ? ' · ' + _fensterTxt(t) : ''))
      + kpi('Trefferquote', _pctTxt(g.hitRate), g.hitRate != null && g.hitRate >= 0.5 ? C.back : C.lay)
      + kpi('ROI — Geld backen', _roiTxt(g.roi), _roiCol(g.roi), 'zu den Quoten')
      + kpi('Konzentration ≥65%', _roiTxt(g.roiConc), _roiCol(g.roiConc), _pctTxt(g.hitRateConc) + ' · n' + g.nConc)
      + kpi('Zufluss', _roiTxt(g.roiInflow), _roiCol(g.roiInflow), _pctTxt(g.hitRateInflow) + ' · n' + g.nInflow)
      + kpi('CLV vs Betfair-Close', _clvTxt(g.avgClvBf), _clvCol(g.avgClvBf), g.nClvBf ? (_pctTxt(g.pctBeatBf) + ' schlagen Close · n' + g.nClvBf) : 'sammelt …')
      + kpi('CLV vs Pinnacle', _clvTxt(g.avgClvPinn), _clvCol(g.avgClvPinn), g.nClvPinn ? (_pctTxt(g.pctBeatPinn) + ' · n' + g.nClvPinn) : 'nur abgedeckte Ligen')
      + '</div>';
    var verdict = (g.roi != null && g.roi > 0.02)
      ? '✅ Dem Geld-Favorit blind zu folgen war insgesamt profitabel (ROI ' + _roiTxt(g.roi) + ').'
      : (g.roi != null && g.roi < -0.02)
        ? '⚠️ Dem Geld-Favorit BLIND über alle Märkte zu folgen zahlt sich NICHT aus (ROI ' + _roiTxt(g.roi) + '). Die Kante steckt in einzelnen Märkten — siehe unten.'
        : '➖ Über alles etwa Nullsumme (ROI ' + _roiTxt(g.roi) + ') — die Kante steckt in einzelnen Märkten, nicht im blinden Folgen.';
    var bm = t.byMarket || {};
    var mrows = Object.keys(bm).map(function (k) { return { mk: k, v: bm[k] }; })
      .filter(function (r) { return r.v.n >= 5; })
      .sort(function (a, b) { return (b.v.roi == null ? -9 : b.v.roi) - (a.v.roi == null ? -9 : a.v.roi); });
    var mkTable = '';
    if (mrows.length) {
      var tr = mrows.map(function (r) {
        var v = r.v, lbl = (MK_ID[r.mk] ? MK_ID[r.mk].label : r.mk), solid = v.n >= MIN_CONF_N;
        return '<tr style="border-top:1px solid ' + C.bd + ';opacity:' + (solid ? 1 : 0.6) + '">'
          + '<td style="padding:5px 8px;font-size:12px;color:' + C.ink + '">' + esc(lbl) + '</td>'
          + '<td style="text-align:right;padding:5px 8px;font-size:12px;color:' + C.mut + '">' + v.n + '</td>'
          + '<td style="text-align:right;padding:5px 8px;font-size:12px;font-weight:700;color:' + C.ink + '">' + _pctTxt(v.hitRate) + '</td>'
          + '<td style="text-align:right;padding:5px 8px;font-size:12px;font-weight:800;color:' + _roiCol(v.roi) + '">' + _roiTxt(v.roi) + '</td></tr>';
      }).join('');
      mkTable = '<div style="font-size:11px;color:' + C.mut + ';margin:2px 0 6px"><b style="color:' + C.ink + '">Wo trägt das Geld? — je Markt über ALLE Ligen</b> (das ist die eigentliche Antwort)</div>'
        + '<div style="overflow-x:auto;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:12px"><table style="width:100%;border-collapse:collapse;min-width:340px"><thead><tr>'
        + '<th style="text-align:left;padding:6px 8px;font-size:10.5px;color:' + C.dim + '">Markt</th>'
        + '<th style="text-align:right;padding:6px 8px;font-size:10.5px;color:' + C.dim + '">Spiele</th>'
        + '<th style="text-align:right;padding:6px 8px;font-size:10.5px;color:' + C.dim + '">Treffer</th>'
        + '<th style="text-align:right;padding:6px 8px;font-size:10.5px;color:' + C.dim + '">ROI</th></tr></thead><tbody>' + tr + '</tbody></table></div>';
    }
    return '<div style="background:linear-gradient(180deg,rgba(255,184,12,.06),transparent);border:1px solid ' + C.bd + ';border-radius:14px;padding:12px 13px;margin:0 0 14px">'
      + '<div style="font-size:13px;font-weight:800;color:' + C.ink + ';margin-bottom:9px">🎯 War die Kohle erfolgreich? — Bilanz über alle abgerechneten Signale'
      + (_fensterTxt(t) ? '<span style="font-weight:600;color:' + C.mut + ';font-size:11px"> · rollendes Fenster, ' + _fensterTxt(t) + '</span>' : '') + '</div>'
      + kpis
      + '<div style="font-size:11.5px;color:' + C.mut + ';line-height:1.5;margin-bottom:12px">' + verdict + '</div>'
      + mkTable + '</div>';
  }

  // ═══════════════════════════════════════════════════════════════════════════════════════
  //  🧭 LERN-BOARD BETFAIR (29.08.2026, Lucas: „im Betfair-Radar sieht man alle Ligen — dort
  //  wissen wir dann auch, was trägt und was nicht. Ich will schon wissen, wo viel Geld
  //  reinfließt, aber auch: in dieser Liga ist das zwar okay, aber nicht gewinnbringend.")
  //
  //  Die Tabelle darunter zeigt seit je Trefferquote und ROI je Liga×Markt. Was sie nie zeigte:
  //  welche Zeile tatsächlich etwas AUSLÖST. Genau das ist hier die Aussage — die zwei
  //  Schwellen aus betfair_money.py sind als Linien eingezeichnet, und jede Zeile steht
  //  sichtbar links oder rechts davon.
  //
  //  Form: divergierender Balken um 0% ROI. Die Frage ist Polarität (trägt / trägt nicht),
  //  nicht Größe. Farbe trägt die Aussage nie allein — Richtung ab der Mittellinie, Vorzeichen
  //  und ein Wort ("trägt" / "verliert hier") sagen dasselbe noch dreimal; grün/rot ist für
  //  Rot-Grün-Blinde praktisch ununterscheidbar (ΔE 2,2 deutan).
  var BF_LB_HALF = 150;   // halbe Balkenbreite in px
  function renderBfLernBoard() {
    var t = _bf.track;
    var src = (t && t.byLeagueMarket) || {};
    // 01.09.2026 (Lucas: „hat das einen Grund?" — dass oben nur ein paar Ligen stehen und unten alle).
    // Ja: hier stehen nur Kombinationen, die WIRKEN (n≥15, die Schwelle aus sharp_signals/betfair_money.py).
    // Nur stand nirgends, wie viele das von wie vielen sind — gemessen am 01.09.: 60 von 1.418, und davon
    // waren 24 sichtbar. Beide Zahlen stehen jetzt da, sonst liest sich der Ausschnitt wie das Ganze.
    var alle = Object.keys(src).map(function (k) {
      var p = k.split('|'), v = src[k];
      return { lg: p[0], mid: p[1], label: MK_ID[p[1]] ? MK_ID[p[1]].label : p[1], v: v,
               w: bfTrackWirkung(v) };
    });
    var nAlle = alle.length;
    var rows = alle.filter(function (r) { return r.w && r.w.art !== 'sammelt'; });
    if (!rows.length) {
      return '<div style="background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px;padding:18px;margin:0 0 14px;color:' + C.mut + ';font-size:12.5px;line-height:1.6">'
        + '<b style="color:' + C.ink + '">🧭 Lern-Board — noch nichts aktiv.</b><br>Kein Liga×Markt hat die '
        + BF_TR_MIN_N + ' abgerechneten Spiele erreicht, ab denen der Track-Record auf das Card-Signal wirkt. '
        + 'Bis dahin zählt das Geld-Signal überall gleich stark.</div>';
    }
    var ORD = { fade: 0, boost: 1, neutral: 2 };
    rows.sort(function (a, b) { return (b.v.n - a.v.n); });
    var span = Math.max(0.15, Math.max.apply(null, rows.map(function (r) { return Math.abs(r.v.roi); })));
    var nF = rows.filter(function (r) { return r.w.art === 'fade'; }).length;
    var nB = rows.filter(function (r) { return r.w.art === 'boost'; }).length;
    var nN = rows.length - nF - nB;
    var CAP = 24;
    var px = function (roi) { return Math.max(3, Math.round(Math.abs(roi) / span * BF_LB_HALF)); };
    // Die zwei Entscheidungslinien als feine Marken im Track — die Regel wird sichtbar.
    var mark = function (roi, col) {
      var off = Math.round(roi / span * BF_LB_HALF);
      return '<div style="position:absolute;left:calc(50% + ' + off + 'px);top:-3px;bottom:-3px;width:1px;background:' + col + ';opacity:.45"></div>';
    };
    var body = rows.slice(0, CAP).map(function (r) {
      var pos = r.v.roi >= 0, col = r.w.art === 'boost' ? C.back : r.w.art === 'fade' ? C.lay : C.mut;
      var bar = '<div style="position:relative;height:10px">'
        + '<div style="position:absolute;left:50%;top:-4px;bottom:-4px;width:1px;background:rgba(255,255,255,.18)"></div>'
        + mark(BF_TR_FADE, C.lay) + mark(BF_TR_BOOST, C.back)
        + '<div style="position:absolute;top:0;height:10px;' + (pos ? 'left:50%;border-radius:0 4px 4px 0' : 'right:50%;border-radius:4px 0 0 4px')
        + ';width:' + px(r.v.roi) + 'px;background:' + col + (r.w.art === 'neutral' ? ';opacity:.45' : '') + '"></div></div>';
      return '<div style="display:grid;grid-template-columns:minmax(150px,1.2fr) 310px 74px minmax(96px,auto);gap:14px;align-items:center;'
        + 'background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:12px;padding:9px 13px">'
        + '<div style="min-width:0"><div style="font-size:12.5px;font-weight:700;color:' + C.ink + ';white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(r.lg) + '</div>'
        + '<div style="font-size:11px;color:' + C.mut + '">' + esc(r.label) + '</div></div>'
        + '<div>' + bar + '</div>'
        + '<div style="text-align:right;font-family:ui-monospace,monospace;font-size:13px;font-weight:800;color:' + C.ink + ';font-variant-numeric:tabular-nums">'
        + _roiTxt(r.v.roi) + '<div style="font-size:9.5px;font-weight:600;color:' + C.dim + ';font-family:inherit">n' + r.v.n + '</div></div>'
        + '<div style="text-align:right;font-size:11px;font-weight:700;color:' + col + ';white-space:nowrap">' + r.w.txt
        + '<div style="font-size:10px;font-weight:600;color:' + C.dim + '">' + r.w.sub + '</div></div>'
        + '</div>';
    }).join('');
    return '<div style="margin:0 0 16px">'
      + '<div style="font-size:13px;font-weight:800;color:' + C.ink + ';margin-bottom:4px">🧭 Lern-Board — was das Geld-Signal in den Cards auslöst</div>'
      + '<div style="font-size:11.5px;color:' + C.mut + ';line-height:1.55;margin-bottom:10px">Ab <b style="color:' + C.ink + '">' + BF_TR_MIN_N + '</b> abgerechneten Spielen wirkt der Track-Record je Liga×Markt auf das Card-Signal <i>Betfair-Geld</i>: '
      + '<b style="color:' + C.back + '">ab ' + Math.round(BF_TR_BOOST * 100) + '% ROI verstärkt</b> es, '
      + '<b style="color:' + C.lay + '">ab ' + Math.round(BF_TR_FADE * 100) + '% dreht es um</b> (dem Geld dort zu folgen verliert → Fade). '
      + 'Die zwei feinen Linien im Balken sind genau diese Schwellen.</div>'
      + '<div style="font-size:11px;color:' + C.dim + ';line-height:1.5;margin:-6px 0 10px">Deshalb stehen hier weniger Ligen als in der Tabelle darunter: '
      + '<b style="color:' + C.mut + '">' + rows.length + ' von ' + nAlle + '</b> Liga×Markt-Kombinationen haben die ' + BF_TR_MIN_N + ' Spiele erreicht — '
      + 'der Rest sammelt noch und zählt überall gleich. Die Tabelle unten zeigt alle, auch die sammelnden.</div>'
      + '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;font-size:11px">'
      + '<span style="padding:3px 9px;border-radius:7px;border:1px solid rgba(63,185,80,.3);color:' + C.back + ';font-weight:700">' + nB + '× verstärkt</span>'
      + '<span style="padding:3px 9px;border-radius:7px;border:1px solid rgba(248,81,73,.3);color:' + C.lay + ';font-weight:700">' + nF + '× gefadet</span>'
      + '<span style="padding:3px 9px;border-radius:7px;border:1px solid ' + C.bd + ';color:' + C.mut + ';font-weight:700">' + nN + '× ohne Wirkung</span>'
      + '</div>'
      + '<div style="display:flex;flex-direction:column;gap:6px">' + body + '</div>'
      + '<div style="font-size:10.5px;color:' + C.dim + ';margin-top:8px">'
      + (rows.length > CAP ? '⚠️ Nur die Top ' + CAP + ' nach Stichprobengröße gezeigt — ' + (rows.length - CAP) + ' weitere wirkende Kombinationen sind hier NICHT sichtbar (in der Tabelle unten schon).'
                           : 'Alle ' + rows.length + ' wirkenden Kombinationen gezeigt.')
      + '</div>'
      + '</div>';
  }

  function renderTrackBoard() {
    var t = _bf.track, isTeam = _bf.trackBy === 'team';
    var byBtn = function (id, lbl) { var on = _bf.trackBy === id; return '<button onclick="_bfSetTrackBy(\'' + id + '\')" style="padding:5px 12px;border:1px solid ' + (on ? C.gold : C.bd) + ';background:' + (on ? 'rgba(255,184,12,.12)' : 'transparent') + ';color:' + (on ? C.gold : C.mut) + ';font-size:11.5px;font-weight:700;cursor:pointer">' + lbl + '</button>'; };
    var byToggle = '<div style="display:inline-flex;border-radius:8px;overflow:hidden;border:1px solid ' + C.bd + ';margin:0 0 10px">' + byBtn('league', '🏆 nach Liga') + byBtn('team', '👥 nach Team') + '</div>';
    var head = viewToggle() + '<br>' + byToggle +
      '<div style="font-size:11px;color:' + C.mut + ';margin-bottom:12px;line-height:1.5">Verlässlichkeit je <b style="color:' + C.ink + '">' + (isTeam ? 'Team' : 'Liga') + ' × Markt</b>: wie oft der Geld-Favorit eintrifft (Trefferquote) und ob es zu den Quoten Gewinn gebracht hätte (ROI). Getrennt nach <b>Konzentration</b> (Geld-Favorit ≥65%) und <b>Zufluss</b> (frisches Geld). n = abgerechnete Spiele — erst ab n≈' + MIN_CONF_N + ' belastbar.</div>';
    if (!t || !t.byLeagueMarket || !t.n) {
      return head + '<div style="padding:34px 22px;text-align:center;color:' + C.mut + ';font-size:13px;line-height:1.7;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px">📊 <b>Sammelt Daten.</b><br>Der Track-Record füllt sich, sobald Spiele abgeschlossen sind und abgerechnet werden (der Fetcher merkt sich je Spiel den Geld-Favorit und rechnet nach Abpfiff ab). Nach ein paar Tagen stehen hier die Ligen × Märkte mit hoher Trefferquote — z.B. „Ecuador × HT-Sieg 68% · +14% ROI".</div>';
    }
    var src = (isTeam ? t.byTeamMarket : t.byLeagueMarket) || {}, CAP = isTeam ? 60 : 500;
    var all = Object.keys(src).map(function (k) {
      var i = k.lastIndexOf('|'), lg = k.slice(0, i), mid = k.slice(i + 1), v = src[k];
      return { lg: lg, mid: mid, label: MK_ID[mid] ? MK_ID[mid].label : mid, v: v };
    }).filter(function (r) { return r.v.n >= 1; }).sort(function (a, b) {
      var as = a.v.n >= MIN_CONF_N ? 1 : 0, bs = b.v.n >= MIN_CONF_N ? 1 : 0;
      if (as !== bs) return bs - as;
      return (b.v.roi || -9) - (a.v.roi || -9);
    });
    var total = all.length, rows = all.slice(0, CAP);
    var th = function (s, w) { return '<th style="text-align:' + (w ? 'right' : 'left') + ';padding:6px 8px;font-size:10.5px;color:' + C.dim + ';font-weight:700;white-space:nowrap">' + s + '</th>'; };
    var head2 = '<tr>' + th(isTeam ? 'Team' : 'Liga') + th('Markt') + th('Spiele', 1) + th('Trefferquote', 1) + th('ROI', 1) + th('Konz. (n)', 1) + th('Zufluss (n)', 1) + '</tr>';
    var body = rows.map(function (r) {
      var v = r.v, solid = v.n >= MIN_CONF_N, ht = MK_ID[r.mid] && MK_ID[r.mid].grp === 'HT';
      var td = function (s, col) { return '<td style="text-align:right;padding:6px 8px;font-size:12px;font-weight:700;color:' + (col || C.ink) + '">' + s + '</td>'; };
      return '<tr style="border-top:1px solid ' + C.bd + ';opacity:' + (solid ? 1 : 0.55) + '">' +
        '<td style="padding:6px 8px;font-size:12px;color:' + C.ink + '">' + esc(String(r.lg).slice(0, 30)) + '</td>' +
        '<td style="padding:6px 8px;font-size:12px;font-weight:700;color:' + (ht ? C.purp : C.mut) + '">' + esc(r.label) + '</td>' +
        td(v.n, solid ? C.ink : C.mut) +
        td(_pctTxt(v.hitRate)) +
        td(_roiTxt(v.roi), _roiCol(v.roi)) +
        td(v.hitRateConc != null ? _pctTxt(v.hitRateConc) + ' <span style="color:' + C.dim + ';font-weight:600">' + v.nConc + '</span>' : '—', v.hitRateConc != null ? C.ink : C.dim) +
        td(v.hitRateInflow != null ? _pctTxt(v.hitRateInflow) + ' <span style="color:' + C.dim + ';font-weight:600">' + v.nInflow + '</span>' : '—', v.hitRateInflow != null ? C.ink : C.dim) +
        '</tr>';
    }).join('');
    return head + trackHeadline(t) + (isTeam ? '' : renderBfLernBoard()) + '<div style="font-size:11px;color:' + C.dim + ';margin-bottom:8px">' + t.n + ' abgerechnete Signale · ' + total + ' ' + (isTeam ? 'Team' : 'Liga') + '×Markt-Kombinationen' + (total > CAP ? ' · Top ' + CAP + ' gezeigt' : '') + ' · Stand ' + (t.generatedAt ? new Date(t.generatedAt).toLocaleString('de-AT') : '—') + '</div>' +
      '<div style="overflow-x:auto;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px"><table style="width:100%;border-collapse:collapse;min-width:560px"><thead>' + head2 + '</thead><tbody>' + body + '</tbody></table></div>' +
      '<div style="font-size:10.5px;color:' + C.dim + ';margin-top:8px">Blasse Zeilen: Stichprobe noch zu klein (n&lt;' + MIN_CONF_N + ').' + (isTeam ? ' Team-Ebene: früh, viele Buckets mit n=1.' : '') + '</div>';
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
    all.forEach(function (m) { if (isLive(m)) return; var mv = moveOf(m); if (mv && (!steam || Math.abs(mv.pp) > Math.abs(steam.mv.pp))) steam = { m: m, mv: mv }; });
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
    var mByMkt = {}; MK.forEach(function (mm) { mByMkt[mm.id] = 0; });
    all.forEach(function (m) { MK.forEach(function (mm) { mByMkt[mm.id] += mvolG(m, mm.id); }); });
    var mopts = '<option value="all">Alle Märkte</option>' + MK.filter(function (mm) { return eur(mByMkt[mm.id]) > 0; })
      .map(function (mm) { return '<option value="' + esc(mm.id) + '"' + (_bf.market === mm.id ? ' selected' : '') + '>' + esc(mm.label) + ' · ' + fmtE(mByMkt[mm.id]) + '</option>'; }).join('');
    var liveN = all.filter(isLive).length;
    var liveBtn = '<button onclick="_bfToggleLive()" title="nur laufende Spiele" style="padding:6px 12px;border:1px solid ' + (_bf.onlyLive ? C.live : C.bd) + ';border-radius:8px;background:' + (_bf.onlyLive ? 'rgba(248,81,73,.14)' : 'transparent') + ';color:' + (_bf.onlyLive ? C.live : C.mut) + ';font-size:12px;font-weight:700;cursor:pointer">🔴 Nur Live' + (liveN ? ' <span style="color:' + C.dim + ';font-weight:600">' + liveN + '</span>' : '') + '</button>';
    return '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px">' +
      '<div style="display:inline-flex;border-radius:9px;overflow:hidden;border:1px solid ' + C.bd + '">' + seg('all', 'Alle') + seg('top', '⭐ Top5+MLS') + seg('intl', '🇪🇺 Int./UEFA') + seg('rest', '🌍 Rest') + '</div>' +
      liveBtn +
      '<span style="flex:1"></span>' +
      '<button onclick="_bfCards(true)" style="padding:6px 10px;border:1px solid ' + C.bd + ';border-radius:8px;background:transparent;color:' + C.mut + ';font-size:11px;cursor:pointer">alle aufklappen</button>' +
      '<button onclick="_bfCards(false)" style="padding:6px 10px;border:1px solid ' + C.bd + ';border-radius:8px;background:transparent;color:' + C.mut + ';font-size:11px;cursor:pointer">alle zu</button>' +
      '<select onchange="_bfSetMarket(this.value)" title="nach Markt filtern" style="padding:6px 10px;border-radius:9px;border:1px solid ' + C.bd + ';background:' + C.card + ';color:' + C.ink + ';font-size:12px;max-width:190px">' + mopts + '</select>' +
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
  function _freshChip() {
    // Oben sichtbar: wann zuletzt aktualisiert + grobe Schätzung fürs nächste (CAD_MIN-Kadenz → auch
    // wann ~der nächste Push kommt). Grün frisch, amber ab 1 verpasstem Lauf, rot ab ~2.5, dann „überfällig"/„hängt".
    var g = _bf.data && _bf.data._meta && _bf.data._meta.generatedAt;
    if (!g) return '';
    var CAD_MIN = 15;   // Anzeige-Kadenz in Minuten. Cron steht auf */10, ABER GitHubs Schedule drosselt kurze Intervalle → real ~15 Min. Statuszeile spiegelt die Realitaet (Lucas 09.08.2026: „wieder auf 15").
    var a = genAgeMin();
    var at = a >= 90 ? Math.round(a / 60) + 'h' : Math.round(a) + ' Min';
    var col = a > CAD_MIN * 2.5 ? '#f2a6a6' : a > CAD_MIN ? C.amber : C.back;
    var nx = a <= CAD_MIN ? 'nächster ~in ' + Math.max(1, Math.round(CAD_MIN - a)) + ' Min'
           : a <= CAD_MIN * 4 ? 'nächster überfällig' : 'Fetcher hängt';
    return '<span style="margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:11.5px;font-weight:700;color:' + col + ';background:rgba(255,255,255,.03);border:1px solid ' + C.bd + ';border-radius:20px;padding:3px 11px" title="Fetcher läuft ~alle ' + CAD_MIN + ' Min; der Trades-Push feuert beim Lauf">🕐 vor ' + at + ' <span style="color:' + C.dim + ';font-weight:600">· ' + nx + '</span></span>';
  }
  function _bfbCss() {
    if (typeof document === 'undefined' || document.getElementById('bfb-css')) return;
    var css = [
      '.bfb-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(470px,1fr));gap:2px 24px;}',
      '@media(max-width:860px){.bfb-grid{grid-template-columns:1fr;}}',
      '.bfb-row{display:grid;grid-template-columns:150px 1fr auto;align-items:center;gap:10px;padding:6px 0;cursor:pointer;border-radius:8px;}',
      '.bfb-row:hover{background:rgba(255,255,255,.025);}',
      '.bfb-lbl{min-width:0;}',
      '.bfb-g{font-size:11.5px;color:#9aa4b1;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      '.bfb-o{font-size:13.5px;color:#e6edf3;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px;}',
      '.bfb-mk{color:#8b949e;font-weight:600;font-size:11.5px;}',
      '.bfb-mk.ht{color:#a78bfa;}',
      '.bfb-bar{position:relative;height:13px;background:#212a36;border-radius:7px;overflow:hidden;}',
      '.bfb-bar>i{position:absolute;left:0;top:0;bottom:0;border-radius:7px;}',
      '.bfb-base{background:rgba(45,212,191,.28);}',
      '.bfb-fresh{background:#3fb950;border-radius:7px;}',
      '.bfb-meta{text-align:right;white-space:nowrap;font-family:\"JetBrains Mono\",\"SF Mono\",Menlo,monospace;}',
      '.bfb-v{font-size:14px;font-weight:900;}',
      '.bfb-s{font-size:12px;font-weight:700;color:#ffb80c;}',
      '.bfb-odd{font-size:12px;color:#9aa4b1;}',
      '.bfb-leg{display:flex;gap:14px;font-size:10.5px;color:#8b949e;margin:0 0 9px;}',
      '.bfb-leg i{display:inline-block;width:18px;height:8px;border-radius:4px;vertical-align:1px;margin-right:5px;}',
      '.bfb-sub{font-size:11px;color:#3fb950;font-weight:700;margin:9px 0 6px;}',
      '.bfb-norm{display:inline-block;font-size:9.5px;font-weight:800;padding:0 5px;margin-left:6px;border:1px solid;border-radius:6px;letter-spacing:.2px;vertical-align:middle;line-height:15px;}',
      '.bfb-over{box-shadow:inset 0 0 0 1px rgba(255,184,12,.5);background:rgba(255,184,12,.05);padding-left:8px;padding-right:8px;}',
      '.bfb-over2{box-shadow:inset 0 0 0 1px rgba(255,184,12,.5);background:rgba(255,184,12,.05);padding-left:8px;padding-right:8px;}'  /* 31.07.2026 Lucas: keine rote Umrandung fuer x-Norm (Rot = nur Live). Amber wie bfb-over; das rote xN-Norm-Badge traegt die Intensitaet. */,
      '.bfb-live{box-shadow:inset 0 0 0 1.5px rgba(248,81,73,.75);background:rgba(248,81,73,.07);padding-left:8px;padding-right:8px;}',
      '.bfb-liveb{display:inline-block;font-size:9.5px;font-weight:800;padding:0 5px;margin-left:6px;border:1px solid rgba(248,81,73,.75);color:#f85149;border-radius:6px;letter-spacing:.2px;vertical-align:middle;line-height:15px;}',
      /* 03.08.2026 (Lucas): am iPhone saß der Deep-Dive-Schließen-Button unter der Notch/Statusleiste → nicht tippbar. Safe-Area + Mindestabstand. */
      '@media(max-width:760px){',
      '.bfd-hd{padding-top:max(48px,calc(env(safe-area-inset-top,0px) + 16px)) !important;}',
      '.bfd-close{top:max(44px,calc(env(safe-area-inset-top,0px) + 13px)) !important;width:40px;height:40px;font-size:17px;}',
      '.bfd-body{padding-bottom:calc(env(safe-area-inset-bottom,0px) + 16px);}',
      '}'
    ].join('');
    var st = document.createElement('style'); st.id = 'bfb-css'; st.textContent = css;
    (document.head || document.documentElement).appendChild(st);
  }
  // 📈 Push-Bilanz: Trefferquote/ROI der ÖFFENTLICHEN Moneyflow/Halftime-Pushs (31.07.2026, Lucas:
  // „schaffst du die Public-Pushs zu tracken?"). Daten aus betfair_public_record.json (Mac-Runner
  // rechnet jeden gesendeten Push gegen den End-/Halbzeitstand ab). Bewertet: lag das Geld richtig?
  function _pct(x) { return (x == null) ? '—' : Math.round(x * 100) + '%'; }
  function _roi(x) { return (x == null) ? '—' : (x >= 0 ? '+' : '') + (x * 100).toFixed(1) + '%'; }
  function renderPushBoard() {
    var r = _bf.pubrec;
    if (!r || !r.n) {
      return viewToggle() + '<div style="background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px;padding:30px 24px;text-align:center;color:' + C.mut + ';line-height:1.7;font-size:13px">' +
        '<div style="font-size:15px;font-weight:800;color:' + C.ink + ';margin-bottom:8px">📈 Push-Bilanz sammelt noch</div>' +
        'Hier wird ausgewertet, ob das Geld, dem die öffentlichen <b>Moneyflow</b>- und <b>Halftime</b>-Pushs gefolgt sind, recht hatte — die gefolgte Seite gegen den End-/Halbzeitstand. Sobald die ersten Pushs aufgelöst sind, stehen hier Trefferquote &amp; ROI' + ((r && r.pending) ? ' (aktuell ' + r.pending + ' offen)' : '') + '.</div>';
    }
    var roiCol = (r.roi >= 0) ? C.back : C.lay;
    var kpi = function (lbl, val, col, sub) { return '<div style="flex:1;min-width:120px;background:' + C.raised + ';border:1px solid ' + C.bd + ';border-radius:12px;padding:13px 15px"><div style="font-size:11px;color:' + C.mut + ';text-transform:uppercase;letter-spacing:.4px;margin-bottom:5px">' + lbl + '</div><div style="font-size:22px;font-weight:900;color:' + (col || C.ink) + '">' + val + '</div><div style="font-size:10px;color:' + C.dim + '">' + (sub || '') + '</div></div>'; };
    var band = '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">' +
      kpi('Trefferquote', _pct(r.hitRate), C.gold, r.wins + '/' + r.n + ' Signale') +
      kpi('ROI', _roi(r.roi), roiCol, '1 Einheit/Signal') +
      kpi('Ø Quote', r.avgOdd ? ('@' + (+r.avgOdd).toFixed(2)) : '—', C.ink, 'gefolgte Seite') +
      kpi('offen', r.pending || 0, C.mut, 'noch nicht aufgelöst') +
      kpi('CLV vs Betfair-Close', _clvTxt(r.avgClvBf), _clvCol(r.avgClvBf), r.nClvBf ? (_pct(r.pctBeatBf) + ' schlagen Close · n' + r.nClvBf) : 'sammelt …') +
      kpi('CLV vs Pinnacle', _clvTxt(r.avgClvPinn), _clvCol(r.avgClvPinn), r.nClvPinn ? (_pct(r.pctBeatPinn) + ' · n' + r.nClvPinn) : 'nur abgedeckte Ligen') + '</div>';
    var scnRow = function (key, lbl) { var s = (r.byScenario || {})[key]; if (!s) return ''; return '<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid ' + C.bd + ';font-size:13px"><span style="font-weight:700">' + lbl + '</span><span style="text-align:right"><b style="color:' + C.gold + '">' + _pct(s.hitRate) + '</b> · <b style="color:' + (s.roi >= 0 ? C.back : C.lay) + '">' + _roi(s.roi) + '</b> ROI <span style="color:' + C.dim + '">' + s.wins + '/' + s.n + ' · Ø@' + (s.avgOdd || '—') + '</span></span></div>'; };
    var scn = '<div style="background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:12px;padding:12px 15px;margin-bottom:14px"><div style="font-size:12px;color:' + C.mut + ';font-weight:700;margin-bottom:2px">nach Signal-Typ</div>' + scnRow('fresh', '💶 Moneyflow (frisches Geld)') + scnRow('ht', '💷 Halftime (einseitig)') + '</div>';
    var mkKeys = Object.keys(r.byMarket || {});
    var mkRows = mkKeys.map(function (k) { var s = r.byMarket[k]; return '<tr><td style="padding:5px 8px">' + esc(shortMk(k)) + '</td><td style="text-align:right;padding:5px 8px;color:' + C.gold + '">' + _pct(s.hitRate) + '</td><td style="text-align:right;padding:5px 8px;color:' + (s.roi >= 0 ? C.back : C.lay) + '">' + _roi(s.roi) + '</td><td style="text-align:right;padding:5px 8px;color:' + C.dim + '">' + s.wins + '/' + s.n + '</td></tr>'; }).join('');
    var mkt = mkRows ? '<div style="background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:12px;padding:12px 15px;margin-bottom:14px"><div style="font-size:12px;color:' + C.mut + ';font-weight:700;margin-bottom:6px">nach Markt</div><table style="width:100%;border-collapse:collapse;font-size:12.5px"><thead><tr style="color:' + C.mut + ';font-size:11px"><th style="text-align:left;padding:4px 8px">Markt</th><th style="text-align:right;padding:4px 8px">Treffer</th><th style="text-align:right;padding:4px 8px">ROI</th><th style="text-align:right;padding:4px 8px">n</th></tr></thead><tbody>' + mkRows + '</tbody></table></div>' : '';
    var recRows = (r.recent || []).map(function (e) { return '<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid ' + C.bd + ';font-size:12.5px"><span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (e.won ? '✅' : '❌') + ' <b>' + esc(String(e.home).slice(0, 12)) + '</b> – ' + esc(String(e.away).slice(0, 12)) + ' <span style="color:' + C.dim + '">· ' + esc(shortMk(e.market)) + ' → ' + esc(e.leadName) + '</span></span><span style="color:' + C.dim + ';white-space:nowrap">@' + (e.leadOdd ? (+e.leadOdd).toFixed(2) : '—') + '</span></div>'; }).join('');
    var rec = recRows ? '<div style="background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:12px;padding:12px 15px"><div style="font-size:12px;color:' + C.mut + ';font-weight:700;margin-bottom:2px">zuletzt aufgelöst</div>' + recRows + '</div>' : '';
    var intro = '<div style="font-size:11.5px;color:' + C.mut + ';margin:6px 0 12px;line-height:1.5">Wertet aus, ob das Geld, dem die öffentlichen Pushs gefolgt sind, recht hatte — die <b style="color:' + C.ink + '">gefolgte Seite</b> (die mit dem Geld) gegen den End-/Halbzeitstand. 1 Einheit Einsatz je Signal · ROI zu den gemeldeten Quoten.</div>';
    return viewToggle() + intro + band + scn + mkt + rec;
  }

  // 04.08.2026 (Lucas): Push-Schwellen-Referenz (Trades + Public), unten auf der Radar-Seite.
  // Spiegelt betfair_alerts.py (FRESH_*/HT_*/PUB_*) — bei Aenderung der Schwellen dort HIER mitziehen.
  function _pushThr() {
    var col = function (title, accent, ft, fr, ht, hr) {
      return '<div style="flex:1;min-width:210px;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:10px;padding:11px 13px">' +
        '<div style="font-weight:800;color:' + accent + ';font-size:13px;margin-bottom:7px">' + title + '</div>' +
        '<div style="font-size:12px;color:' + C.mut + ';line-height:1.7">' +
          '\uD83D\uDCB6 <b style="color:' + C.ink + '">Frisches Geld</b> \u2014 Top/Intl <b style="color:' + accent + '">\u20AC' + ft + 'K</b> \u00B7 Rest <b style="color:' + accent + '">\u20AC' + fr + 'K</b><br>' +
          '\uD83D\uDD50 <b style="color:' + C.ink + '">Halbzeit</b> \u2014 Top/Intl <b style="color:' + accent + '">\u20AC' + ht + 'K</b> \u00B7 Rest <b style="color:' + accent + '">\u20AC' + hr + 'K</b>' +
        '</div></div>';
    };
    return '<div style="background:' + C.raised + ';border:1px solid ' + C.bd + ';border-radius:14px;padding:13px 15px;margin:16px 0 8px">' +
      '<div style="font-size:13px;font-weight:800;color:' + C.ink + '">\uD83D\uDCE3 Push-Schwellen \u2014 wann was in welchen Channel geht</div>' +
      '<div style="font-size:11px;color:' + C.dim + ';margin:2px 0 11px">gematchtes Geld je Markt \u00B7 \u201eTop/Intl\u201c = Top-5 + MLS + UEFA-Wettbewerbe \u00B7 \u201eRest\u201c = alle anderen</div>' +
      '<div style="display:flex;gap:9px;flex-wrap:wrap">' +
        col('\uD83D\uDD12 Trades (privat)', C.blue, 30, 20, 10, 5) +
        col('\uD83D\uDCE3 Public (CocoBet-Channel)', C.gold, 100, 30, 50, 15) +
      '</div>' +
      '<div style="font-size:11px;color:' + C.mut + ';margin-top:10px;line-height:1.6"><b style="color:' + C.dim + '">Gates (beide Channels):</b> Halbzeit nur einseitig (\u226585% auf einen Ausgang) \u00B7 f\u00FChrende Quote \u2265 1.30 (kein Geld auf Quasi-Locks) \u00B7 Re-Push erst bei +50% Volumen</div>' +
      '</div>';
  }
  // 🧭 Konsens-Tab (09.08.2026, Lucas): Zweitmeinung zu jedem Betfair-Geld-Signal — was sagen Pinnacle
  // + Soft-Books? Rein lesend aus betfair_consensus.json (Mac-Runner, betfair_consensus.py). KEIN Push.
  function _bfConsAge(cx) {
    var g = cx && cx.generatedAt; if (!g) return '—';
    var t = Date.parse(g); if (isNaN(t)) return '—';
    var a = Math.round((Date.now() - t) / 60000);
    return a < 1 ? 'gerade' : a < 90 ? ('vor ' + a + ' Min') : ('vor ' + Math.round(a / 60) + 'h');
  }
  function _bfConsFlag(cc) {
    cc = String(cc || '').toUpperCase();
    if (/^[A-Z]{2}$/.test(cc)) { try { return String.fromCodePoint(0x1F1E6 + cc.charCodeAt(0) - 65) + String.fromCodePoint(0x1F1E6 + cc.charCodeAt(1) - 65); } catch (e) {} }
    return '🌍';
  }
  function renderConsensusBoard() {
    var cx = _bf.consensus;
    var intro = '<div style="max-width:900px;margin:2px 0 14px;padding:12px 15px;background:rgba(94,234,212,.06);border-left:3px solid ' + C.vol + ';border-radius:0 10px 10px 0">' +
      '<div style="font-size:15px;font-weight:800;color:' + C.vol + ';margin-bottom:4px">🧭 Zweitmeinung — sagen die Buchmacher dasselbe?</div>' +
      '<div style="font-size:12.5px;color:' + C.mut + ';line-height:1.5">Zu jedem Spiel aus der Radar-Liste (dieselbe Schwelle) der Gegencheck: Wohin zeigt <b>Pinnacle</b> (schärfster Buchmacher, de-viggt), die <b>Soft-Books</b> und — wo vorhanden — <b>Poly</b>? Zieht Pinnacle die Quote auf dieselbe Seite wie das Betfair-Geld — und bewegt sie sich gerade dorthin (▲pp) — ist das Signal bestätigt. Rührt sich nichts oder zeigt der Markt die andere Seite, ist Vorsicht angesagt. Bestätigte Fälle testen wir aktuell im Trades-Push.</div></div>';
    if (!cx || !cx.games || !cx.games.length) {
      return viewToggle() + intro + '<div style="padding:40px;text-align:center;color:' + C.mut + '">⏳ Sammelt — nach dem nächsten Betfair-Lauf stehen hier die Spiele mit Zweitmeinung (läuft am Mac-Runner).</div>';
    }
    var withA = cx.games.filter(function (g) { return g.verdict !== 'no_anchor'; });
    var noA = cx.games.filter(function (g) { return g.verdict === 'no_anchor'; });
    var vbadge = function (v) {
      var map = { konsens: ['✓ Konsens', C.back, 'rgba(63,185,80,.12)'], teil: ['~ teils', C.amber, 'rgba(227,179,65,.12)'], uneinig: ['✗ uneinig', C.lay, 'rgba(248,81,73,.12)'], no_anchor: ['— kein Anker', C.dim, 'transparent'] };
      var x = map[v] || map.no_anchor;
      return '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:10.5px;font-weight:800;color:' + x[1] + ';background:' + x[2] + ';border:1px solid ' + x[1] + '55">' + x[0] + '</span>';
    };
    var pct = function (p) { return p == null ? '' : ' <span style="color:' + C.dim + ';font-size:10px">' + Math.round(p * 100) + '%</span>'; };
    var oddTxt = function (o) { return o == null ? '<span style="color:' + C.dim + '">—</span>' : '@' + (+o).toFixed(2); };
    var usd = function (v) { if (v == null) return ''; v = +v; return v >= 1000 ? '$' + (v / 1000).toFixed(v >= 10000 ? 0 : 1) + 'K' : '$' + Math.round(v); };
    var dirTag = function (d) { if (d === 'in') return ' <span style="color:' + C.back + ';font-weight:800;font-size:10px">Back ✓</span>'; if (d === 'out') return ' <span style="color:' + C.amber + ';font-weight:800;font-size:10px">driftet</span>'; return ''; };
    var moveTag = function (pp) { if (pp == null) return ''; var up = pp > 0; return ' <span style="color:' + (up ? C.back : C.lay) + ';font-size:10px;font-weight:700" title="Pinnacle-Bewegung auf die Geld-Seite seit letztem Lauf">' + (up ? '▲' : '▼') + Math.abs(pp).toFixed(1) + 'pp</span>'; };
    var polyCell = function (p) {
      if (!p) return '<span style="color:' + C.dim + '">—</span>';
      var bits = [];
      if (p.odd != null) bits.push('@' + (+p.odd).toFixed(2));
      if (p.vol) bits.push('<span style="color:' + C.dim + ';font-size:10px">' + usd(p.vol) + (p.sharePct != null ? ' · ' + p.sharePct + '%' : '') + '</span>');
      return bits.length ? bits.join(' ') : '<span style="color:' + C.dim + '">—</span>';
    };
    var row = function (g) {
      var side = g.moneySide;
      var live = g.live ? ' <span style="color:' + C.live + ';font-weight:800;font-size:10px">● LIVE</span>' : '';
      return '<tr style="border-top:1px solid ' + C.bd + '">' +
        '<td style="padding:7px 8px">' + _bfConsFlag(g.country) + ' <b style="color:' + C.ink + '">' + esc(g.home) + '</b> <span style="color:' + C.dim + '">v</span> <b style="color:' + C.ink + '">' + esc(g.away) + '</b>' + live + '<div style="font-size:10px;color:' + C.dim + '">' + esc(g.league || '') + '</div></td>' +
        '<td style="padding:7px 8px;white-space:nowrap"><b style="color:' + C.gold + '">' + esc(g.moneyName || '') + '</b> ' + (g.moneySharePct != null ? g.moneySharePct + '%' : '') + (g.moneyOdd ? ' @' + (+g.moneyOdd).toFixed(2) : '') + dirTag(g.moneyDir) + '</td>' +
        '<td style="padding:7px 8px;text-align:right;white-space:nowrap;color:' + C.ink + '">' + oddTxt(g.pinnOdd) + (g.pinn ? pct(g.pinn[side]) : '') + moveTag(g.pinnMovePP) + '</td>' +
        '<td style="padding:7px 8px;text-align:right;white-space:nowrap;color:' + C.ink + '">' + oddTxt(g.softOdd) + (g.softN ? ' <span style="color:' + C.dim + ';font-size:9.5px">×' + g.softN + '</span>' : '') + '</td>' +
        '<td style="padding:7px 8px;text-align:right;white-space:nowrap;color:' + C.ink + '">' + polyCell(g.poly) + '</td>' +
        '<td style="padding:7px 8px;text-align:center">' + vbadge(g.verdict) + '</td></tr>';
    };
    var head2 = '<thead><tr style="color:' + C.mut + ';font-size:10.5px;text-transform:uppercase;letter-spacing:.3px">' +
      '<th style="text-align:left;padding:6px 8px">Spiel</th><th style="text-align:left;padding:6px 8px">Betfair-Geld</th>' +
      '<th style="text-align:right;padding:6px 8px" title="Pinnacle-Quote für die Betfair-Geld-Seite (+ de-viggte Wahrscheinlichkeit, + Bewegung)">Pinnacle</th>' +
      '<th style="text-align:right;padding:6px 8px" title="Ø Soft-Book-Quote für die Geld-Seite (×n = Anzahl Bücher)">Soft</th>' +
      '<th style="text-align:right;padding:6px 8px" title="Polymarket-Quote + Volumen + Geld-Anteil für die Geld-Seite">Poly</th>' +
      '<th style="text-align:center;padding:6px 8px">Verdikt</th></tr></thead>';
    var stamp = '<div style="font-size:11px;color:' + C.dim + ';margin:0 0 8px">' + cx.covered + ' mit Anker · ' + (cx.count - cx.covered) + ' ohne · Stand ' + _bfConsAge(cx) + '</div>';
    var tbl = withA.length
      ? '<div style="overflow-x:auto;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:12px"><table style="width:100%;border-collapse:collapse;min-width:640px;font-size:12.5px">' + head2 + '<tbody>' + withA.map(row).join('') + '</tbody></table></div>'
      : '<div style="padding:24px;text-align:center;color:' + C.mut + '">Aktuell kein Betfair-Signal in einer gecoverten Liga — sobald z.B. Brasilien/Portugal spielt, erscheint hier die Zweitmeinung.</div>';
    var noABlock = noA.length
      ? '<div style="margin-top:14px"><div style="font-size:12px;color:' + C.mut + ';font-weight:700;margin-bottom:6px">Ohne Anker — kein scharfer Buchmarkt für die Liga (' + noA.length + ')</div><div style="overflow-x:auto;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:12px;opacity:.7"><table style="width:100%;border-collapse:collapse;min-width:640px;font-size:12.5px">' + head2 + '<tbody>' + noA.map(row).join('') + '</tbody></table></div></div>'
      : '';
    return viewToggle() + intro + stamp + tbl + noABlock;
  }

  function renderBetfairRadar() {
    _bfbCss();
    var head = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap">' +
      '<h1 style="margin:0;font-size:24px;color:' + C.ink + '">🟡 Betfair <span style="color:' + C.gold + '">Radar</span></h1>' +
      '<span style="font-size:11px;color:' + C.mut + '">wo echtes Exchange-Geld liegt · wie es sich verteilt · via Betwatch</span>' + _freshChip() + '</div>';

    if (!_bf.data) { _bfLoad(); return head + '<div style="padding:50px;text-align:center;color:' + C.mut + '">⏳ Betfair-Daten werden geladen …</div>'; }

    if (_bf.view === 'terminal') return head + renderTerminal();
    if (_bf.view === 'record') return head + renderTrackBoard();
    if (_bf.view === 'push') return head + renderPushBoard();
    if (_bf.view === 'consensus') return head + renderConsensusBoard();

    var fresh = (_bf.data.matches || []).filter(function (m) { return !isStale(m); });
    var fixCands = _fixCandidates(fresh);   // 21.08.2026 (Lucas): Fix-Verdacht scannt ALLE frischen Spiele (auch unter der Radar-Schwelle)
    var qAll = fresh.filter(qualifies);

    var q = qAll.slice();
    if (_bf.league !== 'all') q = q.filter(function (m) { return m.league === _bf.league; });
    if (_bf.date !== 'all') q = q.filter(function (m) { return isLive(m) || matchDateKey(m) === _bf.date; });
    if (_bf.onlyLive) q = q.filter(function (m) { return isLive(m); });
    if (_bf.market !== 'all') q = q.filter(function (m) { return mvolG(m, _bf.market) > 0; });

    var sortV = function (a, b) { return cardMoney(b) - cardMoney(a); };
    var groups = {
      top: q.filter(function (m) { return tierOf(m) === 'top'; }).sort(sortV),
      intl: q.filter(function (m) { return tierOf(m) === 'intl'; }).sort(sortV),
      rest: q.filter(function (m) { return tierOf(m) === 'rest'; }).sort(sortV),
    };

    var age = genAgeMin();
    var ageTxt = age > 1440 ? Math.round(age / 1440) + ' Tage' : age >= 90 ? Math.round(age / 60) + 'h' : Math.round(age) + ' Min';
    var stale = age > 35
      ? '<div style="margin:8px 0;padding:10px 13px;border:1px solid #7d2b2b;background:#2b0e0e;color:#f2a6a6;border-radius:10px;font-size:12.5px">⚠️ <b>Daten ' + ageTxt + ' alt</b> — die Geldflüsse unten sind NICHT aktuell (Fetcher hängt). Live-Zahlen erst handeln, wenn frisch.</div>'
      : age > 15
      ? '<div style="margin:8px 0;padding:8px 13px;border:1px solid #7d4b16;background:#2b1d0e;color:' + C.amber + ';border-radius:10px;font-size:12px">🕒 <b>Daten ' + ageTxt + ' alt</b> — Geldflüsse spiegeln diesen Stand, nicht jetzt.</div>'
      : '';

    if (!qAll.length) {
      return head + stale + fixStrip(fixCands) + '<div style="margin-top:14px;padding:40px 24px;text-align:center;color:' + C.mut + ';font-size:13px;line-height:1.6;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px">Aktuell kein Spiel über der Geld-Schwelle (' +
        'Top: €20k FT/€10k HT · Int./UEFA: €20k/€10k · Rest: €15k/€5k). Sobald irgendwo genug Geld liegt, erscheint es hier.</div>' + _pushThr();
    }

    // „Frisches Geld" nutzt dieselbe Tier-Schwelle wie Hotspots + Karten (31.07.2026, Lucas: „gleicher
    // Schwellwert wie unten") — sonst schwemmten Klein-Ligen (Indian Calcutta, Timor) über den reinen
    // Zufluss-Floor rein. Basis = qualifizierte Spiele (qAll), dann derselbe Liga/Datum/Live/Markt-Filter.
    var flowBase = qAll.slice();
    if (_bf.league !== 'all') flowBase = flowBase.filter(function (m) { return m.league === _bf.league; });
    if (_bf.date !== 'all') flowBase = flowBase.filter(function (m) { return isLive(m) || matchDateKey(m) === _bf.date; });
    if (_bf.onlyLive) flowBase = flowBase.filter(function (m) { return isLive(m); });
    if (_bf.market !== 'all') flowBase = flowBase.filter(function (m) { return mvolG(m, _bf.market) > 0; });

    var out = head + viewToggle() + infoBand(groups) + hotspotStrip(q) + flowStrip(flowBase) + fixStrip(fixCands) + dateBar(qAll) + controlBar(qAll) + legend() + stale;
    var t = _bf.tab;
    if (t === 'all' || t === 'top') out += section(groups.top, '⭐ Top 5 + MLS', C.gold, '≥ €20k FT · €10k HT');
    if (t === 'all' || t === 'intl') out += section(groups.intl, '🇪🇺 International / UEFA', C.blue, '≥ €20k FT · €10k HT');
    if (t === 'all' || t === 'rest') out += section(groups.rest, '🌍 Rest — andere Ligen', C.purp, '≥ €15k FT · €5k HT');
    if (!groups.top.length && !groups.intl.length && !groups.rest.length) {
      out += '<div style="padding:34px;text-align:center;color:' + C.mut + ';font-size:13px;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px">Kein Spiel für diesen Filter. Datum/Liga/Markt/Live/Reiter anpassen.</div>';
    }
    out += _pushThr();
    var _fc = age > 35 ? '#f2a6a6' : age > 15 ? C.amber : C.dim;
    out += '<div style="text-align:center;color:' + _fc + ';font-size:11px;margin-top:6px">Stand ' + (_bf.data._meta && _bf.data._meta.generatedAt ? new Date(_bf.data._meta.generatedAt).toLocaleString('de-AT') : '—') + ' · vor ' + ageTxt + ' · Beträge in € (Betwatch)</div>';
    return out;
  }
  window._renderBetfairRadar = renderBetfairRadar;

  // ═══ Kohärenz-Deep-Dive-Drawer (Singleton am body → überlebt Panel-Rerender), mobil ═══════
  function _bfEnsureDrawer() {
    if (document.getElementById('bfdDrawer')) return;
    var sc = document.createElement('div'); sc.id = 'bfdScrim'; sc.className = 'bfd-scrim'; sc.onclick = _bfCloseDrawer;
    var dr = document.createElement('aside'); dr.id = 'bfdDrawer'; dr.className = 'bfd-drawer'; dr.setAttribute('aria-hidden', 'true');
    dr.innerHTML = '<div id="bfdIn"></div>';
    document.body.appendChild(sc); document.body.appendChild(dr);
    if (!window._bfdEscBound) { window._bfdEscBound = true; document.addEventListener('keydown', function (e) { if (e.key === 'Escape') _bfCloseDrawer(); }); }
  }
  function _bfDrawer(id) {
    var ms = (_bf.data && _bf.data.matches) || [], m = null;
    for (var i = 0; i < ms.length; i++) { if (String(ms[i].matchId) === String(id)) { m = ms[i]; break; } }
    if (!m) return;
    _bfEnsureDrawer();
    document.getElementById('bfdIn').innerHTML = drawerHTML(m);
    var dr = document.getElementById('bfdDrawer'), sc = document.getElementById('bfdScrim');
    dr.classList.add('on'); dr.setAttribute('aria-hidden', 'false'); sc.classList.add('on');
    document.body.style.overflow = 'hidden'; dr.scrollTop = 0;
  }
  function _bfCloseDrawer() {
    var dr = document.getElementById('bfdDrawer'), sc = document.getElementById('bfdScrim');
    if (dr) { dr.classList.remove('on'); dr.setAttribute('aria-hidden', 'true'); }
    if (sc) sc.classList.remove('on');
    document.body.style.overflow = '';
  }
  window._bfDrawer = _bfDrawer; window._bfCloseDrawer = _bfCloseDrawer;
  function _kvi(v, l, c) {
    return '<div style="min-width:66px"><b style="display:block;font-family:\'JetBrains Mono\',monospace;font-size:19px;font-weight:800;letter-spacing:-.02em;color:' + (c || C.ink) + '">' + v + '</b>' +
      '<span style="font-size:9.5px;color:' + C.dim + ';text-transform:uppercase;letter-spacing:.1em">' + l + '</span></div>';
  }
  function marketExact(rungs, k) { var a = k === 0 ? 1 : rungs[k - 0.5], b = rungs[k + 0.5]; if (a == null || b == null) return null; return Math.max(0, a - b); }
  function cohFlowText(fl) {
    if (fl.kind === 'steam') return 'Preis bewegt sich und Umsatz beschleunigt gleichzeitig — die Bewegung ist mit Geld unterlegt.';
    if (fl.kind === 'absorb') return 'Viel Geld gematcht, Preis praktisch unverändert: jemand nimmt die Gegenseite in Größe. Die interessanteste Konstellation — eine Meinung mit Kapital, nicht bloß Nachfrage.';
    if (fl.kind === 'air') return 'Der Preis wandert, ohne dass nennenswert Geld durchläuft — dünnes Buch, keine Konviktion. Solche Bewegungen kehren häufig zurück.';
    return 'Unauffällig: weder ungewöhnlicher Zufluss noch nennenswerte Preisbewegung.';
  }
  // (03.08.2026, Lucas) Verdikt zuerst: die Deep-Dive-Seite diagnostizierte viel, entschied nichts.
  // Diese Box übersetzt die HARTEN Kohärenz-Abweichungen (reine Algebra zwischen zwei Märkten) in
  // einen Satz: welche Seite ist fehlbepreist, Richtung, Größe. Nur mit echtem Geld (w≥VERDICT_MIN_W
  // ≈ €2.7K gematcht). Live keine Value-Aussage (Teilmärkte desynchronisieren).
  var VERDICT_MIN_W = 0.35;
  function _bfHardEdge(c) {
    if (c.k === 'Leiter-Monotonie') {
      return '<b>' + esc(c.mkt) + '</b> — reiner Widerspruch (mehr Tore teurer als weniger). Einer der beiden Preise ist falsch.';
    }
    var d = c.dev, ref = ' <span style="color:' + C.dim + '">(Markt ' + _cpct(c.market) + ' vs. faire ' + _cpct(c.model) + ')</span>';
    if (d < 0) return '<b>' + esc(c.mkt) + '</b> ist ' + Math.abs(d).toFixed(1) + 'pp <b style="color:' + C.back + '">unterbewertet</b> \u2192 Back ' + esc(c.mkt) + ref;
    return '<b>' + esc(c.mkt) + '</b> ist ' + d.toFixed(1) + 'pp <b style="color:' + C.lay + '">überbewertet</b> \u2192 Lay ' + esc(c.mkt) + ' (bzw. Gegenseite backen)' + ref;
  }
  function _bfVerdict(r, m) {
    var card = function (accent, bg, title, body) {
      return '<div class="bfd-card" style="border-left:3px solid ' + accent + ';background:' + bg + '"><h3 style="margin-top:0">' + title + '</h3>' + body + '</div>';
    };
    if (isLive(m)) {
      return card(C.lay, 'rgba(248,81,73,.06)', '\u26a0 Live — mit Vorsicht',
        '<p class="sub" style="margin:0">Live desynchronisieren die Teilmärkte (1X2, O/U, BTTS aktualisieren unterschiedlich schnell) und die Quotenbewegung folgt dem Spielstand, nicht dem Geld. Die Abweichungen unten sind daher <b>kein verlässliches Value-Signal</b> — belastbar erst vor Anpfiff.</p>');
    }
    var hard = (r.hard || []).filter(function (c) { return c.w >= VERDICT_MIN_W; })
      .sort(function (a, b) { return Math.abs(b.dev) * b.w - Math.abs(a.dev) * a.w; });
    if (!hard.length) {
      var why = (r.hard && r.hard.length) ? 'die harten Abweichungen liegen auf zu dünnen Märkten (kein verlässliches Geld dahinter)' : 'die Märkte sind untereinander sauber bepreist';
      var add = (r.fl && r.fl.kind === 'steam') ? ' — der Zug kommt aus dem Geldfluss (Steam), nicht aus einer Fehlbepreisung' : '';
      return card(C.mut, 'transparent', '\u26aa Nichts klar Handelbares',
        '<p class="sub" style="margin:0">' + why + '. Auffälligkeit ' + r.s + '/99' + add + '.</p>');
    }
    var more = hard.length > 1 ? '<p style="font-size:11px;color:' + C.dim + ';margin:8px 0 0">+' + (hard.length - 1) + ' weitere harte Abweichung' + (hard.length - 1 > 1 ? 'en' : '') + ' mit Geld dahinter (siehe Tabelle).</p>' : '';
    return card(C.gold, 'rgba(255,184,12,.06)', '\ud83d\udfe2 Handelbar — härteste Fehlbepreisung',
      '<p style="font-size:13px;color:' + C.ink + ';margin:0 0 2px;line-height:1.5">' + _bfHardEdge(hard[0]) + '</p>' +
      '<p class="sub" style="margin:6px 0 0">' + fmtE(hard[0].vol) + ' auf diesem Markt gematcht. \u201eHart\u201c = reine Algebra zwischen zwei Märkten, kein Modell — der sicherste Value-Typ.</p>' + more);
  }
  function drawerHTML(m) {
    var r = cohOf(m), co = r.co, fit = co.fit, sup = co.sup, i;
    var kick = isLive(m) ? 'live' : (m.kickoff ? new Date(m.kickoff).toLocaleString('de-AT') : '—');
    var h = '<div class="bfd-hd"><button class="bfd-close" onclick="_bfCloseDrawer()" aria-label="Schließen">✕</button>' +
      '<div style="font-size:11px;color:' + C.mut + '">' + flag(m.country, m.league) + ' ' + esc(String(m.league).slice(0, 48)) + ' · ' + esc(kick) + '</div>' +
      '<div style="font-size:22px;font-weight:800;letter-spacing:-.01em;color:' + C.ink + ';margin-top:3px">' + esc(m.home) + ' <span style="color:' + C.dim + '">v</span> ' + esc(m.away) + '</div>' +
      (cohPillsRow(m, true) || '') + '</div><div class="bfd-body">';

    // Verdikt zuerst — was heißt das? (03.08.2026, Lucas)
    h += _bfVerdict(r, m);

    // Kennzahlen
    h += '<div class="bfd-kv">' +
      _kvi(fmtE(totalG(m)), 'gematcht', C.vol) +
      _kvi(String(r.s), 'Auffälligkeit', r.s >= 45 ? C.gold : C.ink) +
      (fit ? _kvi(fit.l.toFixed(2), 'λ Tore', C.blue) : '') +
      (sup ? _kvi((sup.s > 0 ? '+' : '') + sup.s.toFixed(2), 'Supremacy', C.purp) : '') +
      (sup ? _kvi(sup.lh.toFixed(2) + ' / ' + sup.la.toFixed(2), 'λ Heim / Gast', C.ink) : '') +
      '</div>';

    // Konsens-Kurve (03.08.2026, Lucas: ans Ende — Beleg, kein Handlungssignal)
    var curveHtml = '';
    if (fit && Object.keys(co.rungs).length >= 3) {
      var dist = []; for (var k = 0; k <= 6; k++) { var mkt = marketExact(co.rungs, k), model = pois(k, fit.l); dist.push({ k: k, model: model, market: mkt != null ? mkt : model, filled: mkt == null }); }
      var mx = 0; dist.forEach(function (d) { mx = Math.max(mx, d.model, d.market || 0); }); if (mx <= 0) mx = 1;
      var gaps = dist.filter(function (d) { return d.filled; }).length;
      curveHtml += '<div class="bfd-card"><h3>Konsens-Kurve</h3>' +
        '<p class="sub">Was die O/U-Leiter über die Tor-Verteilung sagt (Balken) gegen die am besten passende Poisson-Kurve (Linie). RMSE ' + (fit.rmse * 100).toFixed(2) + ' pp über ' + Object.keys(co.rungs).length + ' Sprossen.</p>' +
        '<div class="bfd-curve">' + dist.map(function (d) {
          var mh = (d.market != null ? d.market / mx * 100 : 0), dh = d.model / mx * 100;
          return '<div class="bfd-cb"><div class="bfd-mk" style="height:' + mh.toFixed(1) + '%' + (d.filled ? ';opacity:.28;background:repeating-linear-gradient(45deg,#4cc2ff,#4cc2ff 3px,transparent 3px,transparent 6px)' : '') + '"></div>' +
            '<div class="bfd-md" style="bottom:' + dh.toFixed(1) + '%"></div><div class="bfd-lb">' + (d.k === 6 ? '6+' : d.k) + '</div></div>';
        }).join('') + '</div>' +
        '<div class="bfd-legend"><span><i class="bfd-sw" style="background:#4cc2ff"></i>Markt (aus O/U-Differenzen)</span>' +
        '<span><i class="bfd-sw" style="background:#ffb80c"></i>Poisson-Fit λ=' + fit.l.toFixed(2) + '</span>' +
        (gaps ? '<span style="color:' + C.dim + '">schraffiert = Sprosse nicht bepreist, aus dem Modell ergänzt (' + gaps + ')</span>' : '') + '</div></div>';
    } else {
      curveHtml += '<div class="bfd-gap"><b style="color:' + C.ink + '">Kurve nicht rekonstruierbar.</b> Weniger als drei bepreiste O/U-Sprossen für dieses Spiel.</div>';
    }

    // Kohärenz-Tabelle
    if (co.checks.length) {
      h += '<div class="bfd-card"><h3>Kohärenz-Prüfung</h3>' +
        '<p class="sub">Jede Zeile vergleicht einen gehandelten Preis mit dem, was die übrigen Märkte desselben Spiels implizieren. <span style="color:' + C.lay + '">Hart</span> = reine Algebra, kein Modell.</p>' +
        '<table class="bfd-ck"><thead><tr><th>Prüfung</th><th>Markt</th><th>Implizit</th><th>Δ</th><th>Geld</th><th></th></tr></thead><tbody>' +
        co.checks.slice(0, 10).map(function (c) {
          return '<tr title="' + esc(c.why) + '" style="opacity:' + (0.42 + 0.58 * c.w).toFixed(2) + '">' +
            '<td>' + esc(c.mkt) + '<div style="font-size:10px;color:' + C.dim + '">' + esc(c.k) + '</div></td>' +
            '<td>' + _cpct(c.market) + '</td><td style="color:' + C.mut + '">' + _cpct(c.model) + '</td>' +
            '<td style="color:' + (c.hard ? C.lay : (Math.abs(c.dev) >= 4 ? C.gold : C.mut)) + ';font-weight:700">' + _cpp(c.dev) + '</td>' +
            '<td style="color:' + (c.w >= 0.5 ? C.vol : C.dim) + '">' + fmtE(c.vol) + '</td>' +
            '<td><span class="bfd-tag" style="background:' + (c.hard ? 'rgba(248,81,73,.16)' : 'rgba(255,184,12,.14)') + ';color:' + (c.hard ? C.lay : C.gold) + '">' + (c.hard ? 'hart' : 'modell') + '</span></td></tr>';
        }).join('') + '</tbody></table>' +
        '<p style="font-size:10.5px;color:' + C.dim + ';margin:9px 0 0">Blasse Zeilen = zu wenig gematchtes Geld, um ernst genommen zu werden — sie fließen nicht in den Score.</p></div>';
    } else {
      h += '<div class="bfd-card"><h3>Kohärenz-Prüfung</h3><p class="sub" style="margin:0">Keine prüfbare Abweichung — sauber bepreist oder Quoten fehlen.</p></div>';
    }

    // Geldfluss
    var fl = r.fl;
    h += '<div class="bfd-card"><h3>Geldfluss</h3>';
    if (fl) {
      h += '<p class="sub">' + fl.snaps + ' Snapshots über ' + (fl.mins / 60).toFixed(1) + ' h.</p><div class="bfd-kv">' +
        _kvi(fmtE(fl.rate) + '/h', 'Zuflussrate', C.vol) +
        _kvi('+' + (fl.growth * 100).toFixed(0) + '%', 'Umsatz-Wachstum', C.ink) +
        _kvi(_cpp(fl.move) + ' pp', 'stärkste 1X2-Bewegung', fl.move > 0 ? C.back : C.lay) +
        (fl.sideName ? _kvi(esc(String(fl.sideName).slice(0, 16)), 'betroffener Ausgang', C.mut) : '') +
        '</div><p style="font-size:12px;color:' + C.mut + ';margin:0">' + cohFlowText(fl) + '</p>';
    } else {
      h += '<p class="sub" style="margin:0">Weniger als zwei Snapshots in der History — keine Aussage möglich.</p>';
    }
    h += '</div>';

    // Geld je Markt (mit Median-Marker)
    var base = _bf._mixBase || {};
    var mks = Object.keys(m.markets || {}).map(function (kk) { return { k: kk, v: distTotal((m.markets || {})[kk]) }; })
      .filter(function (x) { return x.v > 0; }).sort(function (a, b) { return b.v - a.v; }).slice(0, 12);
    h += '<div class="bfd-card"><h3>Geld je Markt</h3><p class="sub">Anteil am gematchten Gesamtvolumen. Graue Linie = Median über alle Spiele; rechts davon heißt: hier wird auf etwas Bestimmtes gesetzt.</p>' +
      mks.map(function (x) {
        var share = x.v / (totalG(m) || 1) * 100, b = (base[x.k] || 0) * 100, hot = b > 0.4 && share / b >= 1.6;
        return '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;font-size:12px">' +
          '<span style="width:118px;color:' + (hot ? C.blue : C.mut) + '">' + esc(shortMk(x.k)) + '</span>' +
          '<span style="flex:1;height:7px;border-radius:4px;background:#0A0E14;overflow:hidden;position:relative">' +
            '<i style="display:block;height:100%;width:' + Math.min(100, share).toFixed(1) + '%;background:' + (hot ? C.blue : C.vol) + ';opacity:' + (hot ? 1 : .55) + '"></i>' +
            (b > 0 ? '<i style="position:absolute;top:-2px;bottom:-2px;left:' + Math.min(100, b).toFixed(1) + '%;width:1px;background:' + C.dim + '"></i>' : '') +
          '</span>' +
          '<span style="width:50px;text-align:right;font-weight:700;font-family:\'JetBrains Mono\',monospace">' + share.toFixed(1) + '%</span>' +
          '<span style="width:60px;text-align:right;color:' + C.dim + ';font-family:\'JetBrains Mono\',monospace">' + fmtE(x.v) + '</span></div>';
      }).join('') + '</div>';

    h += curveHtml;   // Konsens-Kurve zuletzt (Beleg)
    return h + '</div>';
  }
  window._bfVerdict = _bfVerdict; window._bfHardEdge = _bfHardEdge;   // Test-Hooks
  window._bfDrawerHTML = drawerHTML;   // Test-Hook

  function rerender() { var p = document.getElementById('betfairRadarPanel'); if (p) p.innerHTML = renderBetfairRadar(); }
  try{ var _cb=(typeof localStorage!=='undefined')&&localStorage.getItem('cocoBank'); if(_cb!=null&&_cb!==false&&!isNaN(+_cb)) _bf.bankroll=+_cb; }catch(e){}
  window._bfTermOpen = function (mid) { _bf.termOpen = (String(_bf.termOpen)===String(mid))?null:mid; rerender(); };
  window._bfTermBank = function (v) { var n=parseFloat(v); if(isNaN(n)||n<0) n=0; _bf.bankroll=n; try{localStorage.setItem('cocoBank',n);}catch(e){} rerender(); };
  window._bfTermMute = function (v) { _bf.termHideMuted=!!v; rerender(); };
  window._bfSetView = function (v) { _bf.view = v; rerender(); };
  window._bfSetTrackBy = function (v) { _bf.trackBy = v; rerender(); };
  window._bfSetLeague = function (v) { _bf.league = v; rerender(); };
  window._bfSetTab = function (v) { _bf.tab = v; rerender(); };
  window._bfSetDate = function (v) { _bf.date = v; rerender(); };
  window._bfSetMarket = function (v) { _bf.market = v; rerender(); };
  window._bfToggleLive = function () { _bf.onlyLive = !_bf.onlyLive; rerender(); };
  window._bfCard = function (mid) { _bf.cardOpen[mid] = !_bf.cardOpen[mid]; rerender(); };
  window._bfCards = function (open) { (_bf.data && _bf.data.matches || []).forEach(function (m) { _bf.cardOpen[m.matchId] = !!open; }); rerender(); };
  window._bfJump = function (mid) { _bf.cardOpen[mid] = true; rerender(); var el = document.getElementById('bfg-' + mid); if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'center' }); };
})();
