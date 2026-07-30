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

  // Schwellen je Ebene (€) — Lucas 30.07.2026. FT = größter „Full-Time"-Markt, HT = größter Halbzeit-
  // Markt (HT-1X2 ODER Über 1,5/0,5 erste HZ). Spiel erscheint, sobald FT- ODER HT-Schwelle erreicht.
  // International (UEFA/Länder) verhält sich wie Top (Lucas: „internationale Bewerbe bleiben, wie Top").
  var THR = { top: { FT: 20000, HT: 10000 }, intl: { FT: 20000, HT: 10000 }, rest: { FT: 15000, HT: 5000 } };
  window._bfTHR = THR;   // Test-Hook: Rendering-Tests pinnen eigene Schwellen (produktiv unverändert)
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

  var _bf = { data: null, hist: null, track: null, loading: false, view: 'live', league: 'all', tab: 'all', date: 'all', onlyLive: false, market: 'all', cardOpen: {} };
  var MIN_CONF_N = 20;   // ab so vielen abgerechneten Spielen gilt eine Liga×Markt-Quote als „belastbar"
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
    return Promise.all([jf('betfair_prices.json'), jf('betfair_history.json'), jf('betfair_track_record.json')]);
  }
  function _bfLoad() {
    if (_bf.data || _bf.loading) return;
    _bf.loading = true;
    _bfFetch3().then(function (a) {
      _bf.data = a[0] || { matches: [] }; _bf.hist = a[1] || {}; _bf.track = a[2] || null;
      _bf._cohCache = {}; _bf._mixBase = null;
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
      _bf._cohCache = {}; _bf._mixBase = null;
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
  var STALE_WARN_MIN = 75;   // GitHub-Schedule ist stark jittery (~15–100min) → erst ab ~5 verpassten Läufen warnen
  var LIVE_MAX_H = 2.5;   // ein Fußballspiel dauert ~2h (inkl. Nachspielzeit); danach ist es vorbei
  function _kickMs(m) { var k = m.kickoff ? Date.parse(m.kickoff) : NaN; return isNaN(k) ? null : k; }
  // Live-Status (29.07.2026, Fix „längst beendete Spiele wurden live gezeigt"): HARTER Cut — beendet
  // ODER mehr als LIVE_MAX_H nach Anpfiff → vorbei, egal ob der Feed noch eine Uhr sendet (stale). Sonst
  // ist die Betwatch-Live-Uhr das verlässlichste Live-Signal; ohne Uhr zählt das Anpfiff-Fenster
  // (Anpfiff .. +2,5h). Keine Hysterese mehr (die hielt beendete Spiele fälschlich live). EINE Quelle.
  function isLive(m) {
    var li = m.liveInfo || {};
    if (li.finished) return false;
    if (genAgeMin() > STALE_WARN_MIN) return false;
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
      if (dd > 0.4) checks.push({ k: 'Leiter-Monotonie', mkt: 'Ü' + ks[i + 1] + ' > Ü' + ks[i],
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
        if (Math.abs(d3) >= 2.5) checks.push({ k: 'Tor-Kurve', mkt: 'Ü' + n, market: rungs[n], model: model, dev: d3,
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
        why: 'Aus Torerwartung und Supremacy folgt eine BTTS-Quote. Große Lücken heißen: der Markt erwartet eine schiefere Torverteilung als 1X2 + Ü/U zulassen.' });
    }
    // 5 — Halbzeit-Märkte vs. FT-Torerwartung (weich)
    var hr = htRungs(m);
    if (fit) { var hk = Object.keys(hr).map(Number);
      for (var b = 0; b < hk.length; b++) {
        var hn = hk[b], hm = poisOver(hn, fit.l * HT_SHARE), d5 = (hr[hn] - hm) * 100;
        if (Math.abs(d5) >= 3) checks.push({ k: 'Halbzeit', mkt: 'HZ1 Ü' + hn, market: hr[hn], model: hm, dev: d5,
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
      if (a > 1 && b > 1) { var d = (a - b) / a * 100; if (Math.abs(d) > Math.abs(move)) { move = d; side = k; } }
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
    var mv = moveOf(m); if (!mv) return '';
    var backed = mv.pp > 0, col = backed ? C.back : C.lay;
    var side = mv.side === 'hw' ? m.home : mv.side === 'aw' ? m.away : 'Remis';
    var txt = backed ? ('Geld → ' + String(side).slice(0, 14)) : (String(side).slice(0, 14) + ' driftet');
    var tip = backed ? 'Quote fällt = auf diesen Ausgang wird gesetzt (Back). ' : 'Quote steigt = Ausgang wird schwächer, Geld dagegen (Lay). ';
    return '<span title="' + esc(tip) + Math.abs(mv.pp).toFixed(1) + 'pp seit erstem Snapshot" style="display:inline-flex;gap:4px;align-items:center;padding:2px 9px;border-radius:20px;background:' + (backed ? 'rgba(63,185,80,.14)' : 'rgba(248,81,73,.14)') + ';color:' + col + ';font-size:11px;font-weight:800">' + (backed ? '▼' : '▲') + ' ' + esc(txt) + ' <span style="opacity:.7">' + (backed ? 'Quote fällt' : 'Quote steigt') + '</span></span>';
  }
  function koPill(m) {
    if (isLive(m)) {
      var li = m.liveInfo || {}, sc = (li.goal_v1 != null && li.goal_v2 != null) ? (li.goal_v1 + ':' + li.goal_v2) : '';
      return '<span style="display:inline-flex;gap:4px;align-items:center;padding:2px 8px;border-radius:20px;background:rgba(248,81,73,.15);color:' + C.live + ';font-size:11px;font-weight:800"><span style="width:6px;height:6px;border-radius:50%;background:' + C.live + '"></span>LIVE' + (sc ? ' · ' + sc : '') + '</span>';
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
        confBadge(m.league, mm.id) +
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
    return String(k).replace('Over/Under', 'Ü/U').replace(' Goals', '').replace('Both teams to Score?', 'BTTS')
      .replace('Match Odds', '1X2').replace('First Half', 'HZ1').replace('Half Time/Full Time', 'HZ/EZ')
      .replace('Half Time', 'HZ1 1X2').replace('Correct Score', 'Exakt').replace('Draw no Bet', 'DNB');
  }
  function cohPill(txt, color, bg) {
    return '<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:20px;font-size:10.5px;font-weight:700;background:' + bg + ';color:' + color + '">' + txt + '</span>';
  }
  function cohPillsRow(m) {
    var r = cohOf(m), p = [];
    if (isLive(m)) { p.push(cohPill('● LIVE', C.live, 'rgba(248,81,73,.15)')); }
    if (r.hard.length) p.push(cohPill('⚠ ' + r.hard.length + ' harte Abweichung' + (r.hard.length > 1 ? 'en' : ''), C.lay, 'rgba(248,81,73,.14)'));
    if (r.soft.length) p.push(cohPill(r.soft.length + ' Modell-Lücke' + (r.soft.length > 1 ? 'n' : ''), C.gold, 'rgba(255,184,12,.13)'));
    if (r.fl && r.fl.kind === 'steam') p.push(cohPill('↯ Steam ' + _cpp(r.fl.move) + 'pp' + (r.fl.sideName ? ' · ' + esc(String(r.fl.sideName).slice(0, 14)) : ''), C.vol, 'rgba(45,212,191,.13)'));
    if (r.fl && r.fl.kind === 'absorb') p.push(cohPill('▤ Absorption · ' + fmtE(r.fl.dv) + ' ohne Preis', C.purp, 'rgba(167,139,250,.14)'));
    if (r.fl && r.fl.kind === 'air') p.push(cohPill('◌ Preis ohne Geld', C.mut, 'rgba(139,148,158,.14)'));
    if (r.mx) p.push(cohPill(esc(shortMk(r.mx.market)) + ' ' + r.mx.ratio.toFixed(1) + '× über Norm', C.blue, 'rgba(76,194,255,.13)'));
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

  function section(matches, title, accent, sub) {
    if (!matches.length) return '';
    var maxTot = matches.reduce(function (a, m) { return Math.max(a, cardMoney(m)); }, 1);
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

  // ── Frisches Geld: Zufluss seit dem letzten Update (aus der History-Delta je Markt) ──────────
  var FLOW_MIN_EUR = 2000;     // €-Zufluss erst ab so viel zeigen
  var SURGE_MIN_BASE = 1000;   // % Surge nur wenn Basis ≥ so viel € (sonst Rauschen)
  var SURGE_MIN_DELTA = 500;   // und Zuwachs ≥ so viel €
  var SURGE_MIN_PCT = 25;      // und ≥ so viel % Sprung
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
  function flowChip(x, mode) {
    var lbl = x.mm ? x.mm.label : 'gesamt', ht = x.mm && x.mm.grp === 'HT';
    var right = mode === 'eur' ? ('+' + fmtE(x.delta)) : ('+' + Math.round(x.pct) + '%' + (x.pct >= 200 ? ' 🚨' : ''));
    var sub = mode === 'eur' ? ('jetzt ' + fmtE(x.curr)) : (fmtE(x.prev) + '→' + fmtE(x.curr));
    return '<button onclick="_bfJump(\'' + esc(x.m.matchId) + '\')" style="display:flex;flex-direction:column;gap:1px;padding:7px 11px;border-radius:10px;border:1px solid rgba(63,185,80,.35);background:rgba(63,185,80,.06);cursor:pointer;text-align:left;min-width:150px">' +
      '<span style="font-size:11px;color:' + C.mut + ';font-weight:700">' + flag(x.m.country, x.m.league) + ' ' + esc(String(x.m.home).slice(0, 11)) + '–' + esc(String(x.m.away).slice(0, 11)) + '</span>' +
      '<span style="font-size:12px;color:' + C.ink + ';font-weight:800">' + (ht ? '<span style="color:' + C.purp + '">' + lbl + '</span>' : lbl) + ' <span style="color:' + C.back + '">▲ ' + right + '</span></span>' +
      '<span style="font-size:10px;color:' + C.dim + '">' + sub + '</span></button>';
  }
  function flowRow(label, items, mode) {
    if (!items.length) return '';
    return '<div style="margin-bottom:8px"><div style="font-size:11px;color:' + C.back + ';font-weight:700;margin-bottom:6px">' + label + '</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap">' + items.map(function (x) { return flowChip(x, mode); }).join('') + '</div></div>';
  }
  function flowStrip(base) {
    var items = flowItems(base);
    var eurItems = items.filter(function (x) { return eur(x.delta) >= FLOW_MIN_EUR; })
      .sort(function (a, b) { return b.delta - a.delta; }).slice(0, 6);
    var surge = items.filter(function (x) { return eur(x.prev) >= SURGE_MIN_BASE && eur(x.delta) >= SURGE_MIN_DELTA && x.pct >= SURGE_MIN_PCT && x.pct < 900; })
      .sort(function (a, b) { return b.pct - a.pct; }).slice(0, 6);
    var head = '<div style="font-size:12px;color:' + C.back + ';font-weight:800;margin-bottom:8px">💸 Frisches Geld — wo seit dem letzten Update Kohle reinkam <span style="color:' + C.dim + ';font-weight:600">(kann woanders liegen als oben · Klick springt zum Spiel)</span></div>';
    var body = (!eurItems.length && !surge.length)
      ? '<div style="font-size:11px;color:' + C.dim + '">sammelt Daten — der Zufluss braucht zwei Fetches (~15–30 Min), dann siehst du hier, auf welchen Markt gerade Geld fließt.</div>'
      : flowRow('📈 Größter €-Zufluss', eurItems, 'eur') + flowRow('⚡ Stärkster Sprung (%)', surge, 'pct');
    return '<div style="background:linear-gradient(180deg,rgba(63,185,80,.07),transparent);border:1px solid rgba(63,185,80,.25);border-radius:14px;padding:11px 13px;margin:0 0 14px">' + head + body + '</div>';
  }

  // ── Track-Record (Trefferquoten) ─────────────────────────────────────────────
  function trackFor(league, marketId) {
    var t = _bf.track; if (!t || !t.byLeagueMarket) return null;
    return t.byLeagueMarket[String(league) + '|' + String(marketId)] || null;
  }
  function _pctTxt(x) { return x == null ? '—' : Math.round(x * 100) + '%'; }
  function _roiTxt(x) { return x == null ? '—' : (x >= 0 ? '+' : '') + Math.round(x * 100) + '%'; }
  function _roiCol(x) { return x == null ? C.dim : x > 0.05 ? C.back : x < -0.08 ? C.lay : C.mut; }
  // Kleine Confidence-Chip an einem Markt in der Spielliste (nur wenn belastbare Stichprobe da).
  function confBadge(league, marketId) {
    var v = trackFor(league, marketId);
    if (!v || !v.n || v.n < 6) return '';
    var solid = v.n >= MIN_CONF_N, col = _roiCol(v.roi);
    var tip = 'Track-Record ' + league + ' · ' + (MK_ID[marketId] ? MK_ID[marketId].label : marketId) +
      ': ' + _pctTxt(v.hitRate) + ' Trefferquote · ROI ' + _roiTxt(v.roi) + ' · n=' + v.n +
      (solid ? '' : ' (noch dünn)');
    return '<span title="' + esc(tip) + '" style="display:inline-flex;gap:4px;align-items:center;padding:1px 7px;border-radius:20px;background:' + (solid ? 'rgba(63,185,80,.10)' : 'transparent') + ';border:1px solid ' + (solid ? 'rgba(63,185,80,.3)' : C.bd) + ';font-size:10px;font-weight:700;color:' + col + ';opacity:' + (solid ? 1 : 0.6) + '">🎯 ' + _pctTxt(v.hitRate) + ' · ' + _roiTxt(v.roi) + ' <span style="color:' + C.dim + ';font-weight:600">n' + v.n + '</span></span>';
  }

  function viewToggle() {
    var b = function (id, lbl) { var on = _bf.view === id; return '<button onclick="_bfSetView(\'' + id + '\')" style="padding:6px 13px;border:1px solid ' + (on ? C.gold : C.bd) + ';background:' + (on ? 'rgba(255,184,12,.12)' : 'transparent') + ';color:' + (on ? C.gold : C.mut) + ';font-size:12px;font-weight:700;cursor:pointer">' + lbl + '</button>'; };
    return '<div style="display:inline-flex;border-radius:9px;overflow:hidden;border:1px solid ' + C.bd + ';margin:6px 0 12px">' + b('live', '🔴 Live-Radar') + b('record', '📊 Trefferquoten') + '</div>';
  }

  function renderTrackBoard() {
    var t = _bf.track, head = viewToggle() +
      '<div style="font-size:11px;color:' + C.mut + ';margin-bottom:12px;line-height:1.5">Verlässlichkeit je <b style="color:' + C.ink + '">Liga × Markt</b>: wie oft der Geld-Favorit eintrifft (Trefferquote) und ob es zu den Quoten Gewinn gebracht hätte (ROI). Getrennt nach <b>Konzentration</b> (Geld-Favorit ≥65%) und <b>Zufluss</b> (frisches Geld). n = abgerechnete Spiele — erst ab n≈' + MIN_CONF_N + ' belastbar.</div>';
    if (!t || !t.byLeagueMarket || !t.n) {
      return head + '<div style="padding:34px 22px;text-align:center;color:' + C.mut + ';font-size:13px;line-height:1.7;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px">📊 <b>Sammelt Daten.</b><br>Der Track-Record füllt sich, sobald Spiele abgeschlossen sind und abgerechnet werden (der Fetcher merkt sich je Spiel den Geld-Favorit und rechnet nach Abpfiff ab). Nach ein paar Tagen stehen hier die Ligen × Märkte mit hoher Trefferquote — z.B. „Ecuador × HT-Sieg 68% · +14% ROI".</div>';
    }
    var rows = Object.keys(t.byLeagueMarket).map(function (k) {
      var i = k.lastIndexOf('|'), lg = k.slice(0, i), mid = k.slice(i + 1), v = t.byLeagueMarket[k];
      return { lg: lg, mid: mid, label: MK_ID[mid] ? MK_ID[mid].label : mid, v: v };
    }).filter(function (r) { return r.v.n >= 1; }).sort(function (a, b) {
      // belastbare (n≥MIN) zuerst, dann nach ROI, dann n
      var as = a.v.n >= MIN_CONF_N ? 1 : 0, bs = b.v.n >= MIN_CONF_N ? 1 : 0;
      if (as !== bs) return bs - as;
      return (b.v.roi || -9) - (a.v.roi || -9);
    });
    var th = function (s, w) { return '<th style="text-align:' + (w ? 'right' : 'left') + ';padding:6px 8px;font-size:10.5px;color:' + C.dim + ';font-weight:700;white-space:nowrap">' + s + '</th>'; };
    var head2 = '<tr>' + th('Liga') + th('Markt') + th('Spiele', 1) + th('Trefferquote', 1) + th('ROI', 1) + th('Konz. (n)', 1) + th('Zufluss (n)', 1) + '</tr>';
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
    return head + '<div style="font-size:11px;color:' + C.dim + ';margin-bottom:8px">' + t.n + ' abgerechnete Signale · ' + rows.length + ' Liga×Markt-Kombinationen · Stand ' + (t.generatedAt ? new Date(t.generatedAt).toLocaleString('de-AT') : '—') + '</div>' +
      '<div style="overflow-x:auto;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px"><table style="width:100%;border-collapse:collapse;min-width:560px"><thead>' + head2 + '</thead><tbody>' + body + '</tbody></table></div>' +
      '<div style="font-size:10.5px;color:' + C.dim + ';margin-top:8px">Blasse Zeilen: Stichprobe noch zu klein (n&lt;' + MIN_CONF_N + '). Team-Ebene folgt.</div>';
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
  function renderBetfairRadar() {
    var head = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap">' +
      '<h1 style="margin:0;font-size:24px;color:' + C.ink + '">🟡 Betfair <span style="color:' + C.gold + '">Radar</span></h1>' +
      '<span style="font-size:11px;color:' + C.mut + '">wo echtes Exchange-Geld liegt · wie es sich verteilt · via Betwatch</span></div>';

    if (!_bf.data) { _bfLoad(); return head + '<div style="padding:50px;text-align:center;color:' + C.mut + '">⏳ Betfair-Daten werden geladen …</div>'; }

    if (_bf.view === 'record') return head + renderTrackBoard();

    var fresh = (_bf.data.matches || []).filter(function (m) { return !isStale(m); });
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
      return head + stale + '<div style="margin-top:14px;padding:40px 24px;text-align:center;color:' + C.mut + ';font-size:13px;line-height:1.6;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px">Aktuell kein Spiel über der Geld-Schwelle (' +
        'Top: €20k FT/€10k HT · Int./UEFA: €20k/€10k · Rest: €15k/€5k). Sobald irgendwo genug Geld liegt, erscheint es hier.</div>';
    }

    // „Frisches Geld" scannt ALLE frischen Spiele (auch unter der Geld-Schwelle) im aktuellen
    // Liga/Datum-Filter — der Zufluss kann auf einem Spiel liegen, das oben (noch) nicht auftaucht.
    var flowBase = fresh.slice();
    if (_bf.league !== 'all') flowBase = flowBase.filter(function (m) { return m.league === _bf.league; });
    if (_bf.date !== 'all') flowBase = flowBase.filter(function (m) { return isLive(m) || matchDateKey(m) === _bf.date; });
    if (_bf.onlyLive) flowBase = flowBase.filter(function (m) { return isLive(m); });
    if (_bf.market !== 'all') flowBase = flowBase.filter(function (m) { return mvolG(m, _bf.market) > 0; });

    var out = head + viewToggle() + infoBand(groups) + hotspotStrip(q) + flowStrip(flowBase) + dateBar(qAll) + controlBar(qAll) + legend() + stale;
    var t = _bf.tab;
    if (t === 'all' || t === 'top') out += section(groups.top, '⭐ Top 5 + MLS', C.gold, '≥ €20k FT · €10k HT');
    if (t === 'all' || t === 'intl') out += section(groups.intl, '🇪🇺 International / UEFA', C.blue, '≥ €20k FT · €10k HT');
    if (t === 'all' || t === 'rest') out += section(groups.rest, '🌍 Rest — andere Ligen', C.purp, '≥ €15k FT · €5k HT');
    if (!groups.top.length && !groups.intl.length && !groups.rest.length) {
      out += '<div style="padding:34px;text-align:center;color:' + C.mut + ';font-size:13px;background:' + C.card + ';border:1px solid ' + C.bd + ';border-radius:14px">Kein Spiel für diesen Filter. Datum/Liga/Markt/Live/Reiter anpassen.</div>';
    }
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
  function drawerHTML(m) {
    var r = cohOf(m), co = r.co, fit = co.fit, sup = co.sup, i;
    var kick = isLive(m) ? 'live' : (m.kickoff ? new Date(m.kickoff).toLocaleString('de-AT') : '—');
    var h = '<div class="bfd-hd"><button class="bfd-close" onclick="_bfCloseDrawer()" aria-label="Schließen">✕</button>' +
      '<div style="font-size:11px;color:' + C.mut + '">' + flag(m.country, m.league) + ' ' + esc(String(m.league).slice(0, 48)) + ' · ' + esc(kick) + '</div>' +
      '<div style="font-size:22px;font-weight:800;letter-spacing:-.01em;color:' + C.ink + ';margin-top:3px">' + esc(m.home) + ' <span style="color:' + C.dim + '">v</span> ' + esc(m.away) + '</div>' +
      (cohPillsRow(m) || '') + '</div><div class="bfd-body">';

    // Kennzahlen
    h += '<div class="bfd-kv">' +
      _kvi(fmtE(totalG(m)), 'gematcht', C.vol) +
      _kvi(String(r.s), 'Auffälligkeit', r.s >= 45 ? C.gold : C.ink) +
      (fit ? _kvi(fit.l.toFixed(2), 'λ Tore', C.blue) : '') +
      (sup ? _kvi((sup.s > 0 ? '+' : '') + sup.s.toFixed(2), 'Supremacy', C.purp) : '') +
      (sup ? _kvi(sup.lh.toFixed(2) + ' / ' + sup.la.toFixed(2), 'λ Heim / Gast', C.ink) : '') +
      '</div>';

    // Konsens-Kurve
    if (fit && Object.keys(co.rungs).length >= 3) {
      var dist = []; for (var k = 0; k <= 6; k++) { var mkt = marketExact(co.rungs, k), model = pois(k, fit.l); dist.push({ k: k, model: model, market: mkt != null ? mkt : model, filled: mkt == null }); }
      var mx = 0; dist.forEach(function (d) { mx = Math.max(mx, d.model, d.market || 0); }); if (mx <= 0) mx = 1;
      var gaps = dist.filter(function (d) { return d.filled; }).length;
      h += '<div class="bfd-card"><h3>Konsens-Kurve</h3>' +
        '<p class="sub">Was die Ü/U-Leiter über die Tor-Verteilung sagt (Balken) gegen die am besten passende Poisson-Kurve (Linie). RMSE ' + (fit.rmse * 100).toFixed(2) + ' pp über ' + Object.keys(co.rungs).length + ' Sprossen.</p>' +
        '<div class="bfd-curve">' + dist.map(function (d) {
          var mh = (d.market != null ? d.market / mx * 100 : 0), dh = d.model / mx * 100;
          return '<div class="bfd-cb"><div class="bfd-mk" style="height:' + mh.toFixed(1) + '%' + (d.filled ? ';opacity:.28;background:repeating-linear-gradient(45deg,#4cc2ff,#4cc2ff 3px,transparent 3px,transparent 6px)' : '') + '"></div>' +
            '<div class="bfd-md" style="bottom:' + dh.toFixed(1) + '%"></div><div class="bfd-lb">' + (d.k === 6 ? '6+' : d.k) + '</div></div>';
        }).join('') + '</div>' +
        '<div class="bfd-legend"><span><i class="bfd-sw" style="background:#4cc2ff"></i>Markt (aus Ü/U-Differenzen)</span>' +
        '<span><i class="bfd-sw" style="background:#ffb80c"></i>Poisson-Fit λ=' + fit.l.toFixed(2) + '</span>' +
        (gaps ? '<span style="color:' + C.dim + '">schraffiert = Sprosse nicht bepreist, aus dem Modell ergänzt (' + gaps + ')</span>' : '') + '</div></div>';
    } else {
      h += '<div class="bfd-gap"><b style="color:' + C.ink + '">Kurve nicht rekonstruierbar.</b> Weniger als drei bepreiste Ü/U-Sprossen für dieses Spiel.</div>';
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

    return h + '</div>';
  }
  window._bfDrawerHTML = drawerHTML;   // Test-Hook

  function rerender() { var p = document.getElementById('betfairRadarPanel'); if (p) p.innerHTML = renderBetfairRadar(); }
  window._bfSetView = function (v) { _bf.view = v; rerender(); };
  window._bfSetLeague = function (v) { _bf.league = v; rerender(); };
  window._bfSetTab = function (v) { _bf.tab = v; rerender(); };
  window._bfSetDate = function (v) { _bf.date = v; rerender(); };
  window._bfSetMarket = function (v) { _bf.market = v; rerender(); };
  window._bfToggleLive = function () { _bf.onlyLive = !_bf.onlyLive; rerender(); };
  window._bfCard = function (mid) { _bf.cardOpen[mid] = !_bf.cardOpen[mid]; rerender(); };
  window._bfCards = function (open) { (_bf.data && _bf.data.matches || []).forEach(function (m) { _bf.cardOpen[m.matchId] = !!open; }); rerender(); };
  window._bfJump = function (mid) { _bf.cardOpen[mid] = true; rerender(); var el = document.getElementById('bfg-' + mid); if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'center' }); };
})();
