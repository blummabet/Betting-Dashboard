/* stake-radar.js — Stake Radar (03.09.2026, Lucas: „ich würde gerne nur im Dashboard einen
   Bereich mit den Spielen sehen, mit Schwellen die wir definieren, dann rein und wir sammeln das").

   Stake zeigt große Einzelwetten öffentlich (Event, User, Zeit, Quote, Einsatz). Das ist die
   einzige Quelle im Projekt, die EINZELNE Einsätze mit Betrag nennt — Betfair gibt Volumen,
   Poly gibt Preis-als-Geldanteil, Pinnacle gibt den Anker.

   Dieser Tab ist eine SAMMELANSICHT, kein Signal. Es gibt für Stake-Einsatzfluss noch keine
   gemessene Trefferquote und keinen gemessenen CLV — deshalb steht hier nirgends „stark" oder
   „schwach", sondern nur, was gezählt wurde und auf wie vielen Wetten es beruht. Die Schwellen
   sind Regler, keine Wahrheit: sie filtern die Anzeige, sie bewerten nicht.

   Liest stake_highroller.json (vom Runner, stake_highroller_fetch.py). Reine Anzeige. */
(function () {
  var SR = { daten: null, geladen: false, styled: false };
  // 03.09.2026 (Lucas, nach dem ersten echten Ledger): „müssen uns nur etwas mehr an den
  // Schwellen rumspielen, die gehören mal etwas höher". Im ersten Lauf lagen 68 von 93 Wetten
  // über $1.000 — das ist keine Auswahl mehr, das ist die Liste. $5.000 lässt die Handvoll
  // übrig, bei der die Größe selbst schon etwas heißt. Der Sammler sammelt weiter ALLES;
  // hier wird nur angezeigt, die Regler gehen jederzeit wieder runter.
  var SR_MIN_USD = 5000;      // Regler: Mindesteinsatz je Wette
  var SR_MIN_N = 2;           // Regler: ab wie vielen Wetten ein Spiel gezeigt wird
  var SR_FENSTER_H = 24;      // Regler: Zeitfenster
  var SR_SPORT = 'alle';
  var SR_SORT = 'geld';       // geld | dichte | zeit

  var SR_STAKE_LIMITS = [1000, 2500, 5000, 10000, 25000];
  var SR_FENSTER = [6, 12, 24, 48];

  function _srStyle() {
    if (SR.styled) return; SR.styled = true;
    var css = [
'#stakeRadarPanel{color:#e6ebf5}',
'#stakeRadarPanel .sr-loading,#stakeRadarPanel .sr-empty{text-align:center;color:#76819c;padding:44px 16px;line-height:1.7}',
'.sr-head{display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin-bottom:4px}',
'.sr-ic{width:32px;height:32px;border-radius:9px;display:grid;place-items:center;font-size:16px;background:rgba(103,204,145,.14);border:1px solid rgba(103,204,145,.32)}',
'.sr-head h1{font-size:19px;font-weight:800;margin:0;letter-spacing:-.01em}',
'.sr-sub{flex-basis:100%;color:#8a95ad;font-size:12.5px;line-height:1.55;margin-top:2px;max-width:860px}',
'.sr-warn{margin:12px 0 0;padding:10px 13px;border-radius:10px;background:rgba(201,133,0,.08);border:1px solid rgba(201,133,0,.28);color:#e3b341;font-size:12px;line-height:1.55}',
'.sr-basis{margin:14px 0 0;display:flex;gap:16px;flex-wrap:wrap;font-size:11.5px;color:#76819c;font-weight:600}',
'.sr-basis b{color:#c2ccd8;font-weight:800;font-variant-numeric:tabular-nums}',
'.sr-ctrl{display:flex;gap:18px;flex-wrap:wrap;align-items:center;margin:16px 0 14px;padding:12px 14px;background:#131922;border:1px solid #242c38;border-radius:12px}',
'.sr-cg{display:flex;gap:6px;align-items:center}',
'.sr-cl{font-size:10.5px;color:#6b7480;font-weight:800;letter-spacing:.03em;text-transform:uppercase;margin-right:2px}',
'.sr-fb{background:#151b24;border:1px solid #242c38;color:#9aa4b1;font:inherit;font-size:11.5px;font-weight:700;padding:5px 11px;border-radius:8px;cursor:pointer;font-variant-numeric:tabular-nums}',
'.sr-fb.on{background:rgba(103,204,145,.16);border-color:rgba(103,204,145,.42);color:#67cc91}',
'.sr-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}',
'@media(max-width:820px){.sr-grid{grid-template-columns:1fr}}',
'.sr-card{background:linear-gradient(180deg,#161d27,#131922);border:1px solid #242c38;border-radius:14px;padding:13px 15px 14px}',
'.sr-ch{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}',
'.sr-ev{font-size:14px;font-weight:800;letter-spacing:-.01em}',
'.sr-lg{margin-left:auto;font-size:10.5px;color:#6b7480;font-weight:700}',
'.sr-meta{display:flex;gap:14px;flex-wrap:wrap;margin:9px 0 0;font-size:11.5px;color:#8a95ad;font-weight:600;font-variant-numeric:tabular-nums}',
'.sr-meta b{color:#e6ebf5;font-weight:800}',
'.sr-meta .sr-geld b{color:#67cc91}',
'.sr-seiten{margin:11px 0 0;display:flex;flex-direction:column;gap:5px}',
'.sr-seite{display:flex;align-items:center;gap:8px;font-size:12px;font-variant-numeric:tabular-nums}',
'.sr-sn{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#c2ccd8;font-weight:700}',
'.sr-sbar{width:74px;height:5px;border-radius:3px;background:#1c232e;overflow:hidden;flex:none}',
'.sr-sbar i{display:block;height:100%;background:linear-gradient(90deg,#3f9d6d,#67cc91);border-radius:3px}',
'.sr-sg{color:#67cc91;font-weight:800;width:64px;text-align:right;flex:none}',
'.sr-sq{color:#6b7480;font-weight:600;width:78px;text-align:right;flex:none}',
'.sr-bets{margin:11px 0 0;padding-top:10px;border-top:1px solid #242c38;display:flex;flex-direction:column;gap:4px}',
'.sr-bet{display:flex;gap:9px;align-items:baseline;font-size:11px;color:#76819c;font-variant-numeric:tabular-nums}',
'.sr-bet .sr-bt{width:44px;flex:none;color:#5c6577}',
'.sr-bet .sr-bm{width:110px;flex:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#5c6577}',
'.sr-bet.sr-kombi{opacity:.62}',
'.sr-kb{font-size:9px;font-weight:800;color:#e3b341;border:1px solid rgba(201,133,0,.4);border-radius:5px;padding:1px 5px;margin-left:4px}',
'.sr-bet .sr-bs{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#9aa4b1}',
'.sr-bet .sr-bo{width:46px;flex:none;text-align:right}',
'.sr-bet .sr-bg{width:64px;flex:none;text-align:right;color:#c2ccd8;font-weight:700}',
'.sr-bet .sr-bg.sr-unk{color:#e3b341;font-weight:600}',
'.sr-um{color:#5c6577;font-weight:600;margin-left:2px}',
'.sr-mehr{margin-top:6px;font-size:10.5px;color:#5c6577}',
'.sr-tag{font-size:9px;font-weight:800;letter-spacing:.4px;padding:2px 7px;border-radius:6px;text-transform:uppercase;color:#e3b341;border:1px solid rgba(201,133,0,.42)}'
    ].join('\n');
    var s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
  }

  // ── Helfer ────────────────────────────────────────────────────────────────
  function _srEsc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function _srUsd(v) {
    if (v == null || !isFinite(v)) return '—';
    if (v >= 1e6) return '$' + (v / 1e6).toFixed(1) + 'M';
    if (v >= 1e3) return '$' + Math.round(v / 1e3) + 'k';
    return '$' + Math.round(v);
  }
  function _srZeit(ts) {
    if (!ts) return '—';
    var d = new Date(ts); if (isNaN(d)) return '—';
    return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
  }
  function _srMs(ts) { var d = new Date(ts); return isNaN(d) ? null : d.getTime(); }

  /** Die meisten Wetten, die innerhalb eines Fensters von SR_DICHTE_MAX_MIN lagen.
      03.09.2026: erst als Rate n/Minuten gerechnet — das kürte immer ein Zweier-Paar,
      weil zwei Wetten in einer Minute (2,0) über vier in drei Minuten (1,33) liegen.
      Zwei ist aber keine Häufung. Deshalb: MENGE entscheidet, Kürze bricht den Gleichstand.
      Und weiterhin gilt — dass Dichte irgendetwas vorhersagt, ist im Projekt NICHT gemessen.
      Diese Zahl ist eine Beobachtung, keine Note. */
  var SR_DICHTE_MAX_MIN = 10;

  function _srDichte(wetten) {
    var ts = wetten.map(function (w) { return _srMs(w.ts); })
                   .filter(function (t) { return t != null; })
                   .sort(function (a, b) { return a - b; });
    if (ts.length < 2) return null;
    var best = null, i = 0;
    for (var j = 1; j < ts.length; j++) {
      while ((ts[j] - ts[i]) / 60000 > SR_DICHTE_MAX_MIN) i++;
      if (j === i) continue;
      var n = j - i + 1, min = (ts[j] - ts[i]) / 60000;
      if (!best || n > best.n || (n === best.n && min < best.min)) best = { n: n, min: min };
    }
    return best;
  }

  function _srKey(w) {
    // Die Fixture-ID des Feeds ist eindeutig; der Anzeigename ist es nicht (dasselbe
    // Paar kann in Liga und Pokal stehen). Nur ohne ID faellt es auf Name+Liga zurueck.
    return w.eventId || ((w.event || '?') + '|' + (w.liga || ''));
  }

  function _srGruppen(wetten) {
    var m = {};
    wetten.forEach(function (w) {
      var k = _srKey(w);
      if (!m[k]) m[k] = { key: k, event: w.event, liga: w.liga, sport: w.sport, anpfiff: w.anpfiff, wetten: [] };
      m[k].wetten.push(w);
    });
    return Object.keys(m).map(function (k) {
      var g = m[k];
      g.wetten.sort(function (a, b) { return (_srMs(b.ts) || 0) - (_srMs(a.ts) || 0); });
      g.n = g.wetten.length;
      // Eine Kombi ueber vier Spiele ist keine Wette auf DIESES Spiel — ihr Einsatz haengt
      // an allen Beinen zugleich. Sie bleibt sichtbar, zaehlt aber nicht ins Spielgeld.
      g.nKombi = g.wetten.filter(function (w) { return w.kombi; }).length;
      var einzel = g.wetten.filter(function (w) { return !w.kombi; });
      // Geld nur aus Wetten mit bekanntem USD-Wert. Unbekannt wird GEZÄHLT, nicht als 0 addiert.
      var bek = einzel.filter(function (w) { return w.einsatzUsd != null; });
      g.geldUsd = bek.reduce(function (s, w) { return s + w.einsatzUsd; }, 0);
      g.nGeldBekannt = bek.length;
      g.nEinzel = einzel.length;
      g.nGeldUnbekannt = einzel.length - bek.length;
      g.letzte = g.wetten[0] && g.wetten[0].ts;
      g.dichte = _srDichte(g.wetten);
      var seiten = {};
      einzel.forEach(function (w) {
        var s = w.auswahl ? ((w.markt ? w.markt + ': ' : '') + w.auswahl) : (w.markt || '?');
        if (!seiten[s]) seiten[s] = { name: s, n: 0, geld: 0, qMin: null, qMax: null };
        var o = seiten[s]; o.n++;
        if (w.einsatzUsd != null) o.geld += w.einsatzUsd;
        if (w.quote != null) {
          o.qMin = o.qMin == null ? w.quote : Math.min(o.qMin, w.quote);
          o.qMax = o.qMax == null ? w.quote : Math.max(o.qMax, w.quote);
        }
      });
      g.seiten = Object.keys(seiten).map(function (s) { return seiten[s]; })
                        .sort(function (a, b) { return b.geld - a.geld || b.n - a.n; });
      return g;
    });
  }

  // ── Regler ────────────────────────────────────────────────────────────────
  function _srCtrl() {
    function grp(label, werte, aktiv, fn, fmt) {
      return '<div class="sr-cg"><span class="sr-cl">' + label + '</span>' +
        werte.map(function (v) {
          return '<button class="sr-fb' + (v === aktiv ? ' on' : '') + '" onclick="' + fn + '(' +
            (typeof v === 'string' ? "'" + v + "'" : v) + ')">' + fmt(v) + '</button>';
        }).join('') + '</div>';
    }
    var sports = ['alle'].concat(_srSports());
    return '<div class="sr-ctrl">' +
      grp('ab Einsatz', SR_STAKE_LIMITS, SR_MIN_USD, '_srSetMin', function (v) { return _srUsd(v); }) +
      grp('ab Wetten', [1, 2, 3, 5], SR_MIN_N, '_srSetN', function (v) { return v + '×'; }) +
      grp('Fenster', SR_FENSTER, SR_FENSTER_H, '_srSetFenster', function (v) { return v + 'h'; }) +
      (sports.length > 1 ? grp('Sport', sports, SR_SPORT, '_srSetSport', function (v) { return _srEsc(v); }) : '') +
      grp('sortiert', ['geld', 'dichte', 'zeit'], SR_SORT, '_srSetSort', function (v) {
        return { geld: 'Geld', dichte: 'Dichte', zeit: 'zuletzt' }[v];
      }) +
      '</div>';
  }

  function _srSports() {
    var s = {}, w = (SR.daten && SR.daten.wetten) || [];
    w.forEach(function (b) { if (b.sport) s[b.sport] = 1; });
    return Object.keys(s).sort().slice(0, 8);
  }

  window._srSetMin = function (v) { SR_MIN_USD = v; _srRender(); };
  window._srSetN = function (v) { SR_MIN_N = v; _srRender(); };
  window._srSetFenster = function (v) { SR_FENSTER_H = v; _srRender(); };
  window._srSetSport = function (v) { SR_SPORT = v; _srRender(); };
  window._srSetSort = function (v) { SR_SORT = v; _srRender(); };

  // ── Karte ─────────────────────────────────────────────────────────────────
  function _srKarte(g) {
    var maxGeld = g.seiten.reduce(function (m, s) { return Math.max(m, s.geld); }, 0) || 1;
    var seiten = g.seiten.slice(0, 4).map(function (s) {
      var q = s.qMin == null ? '' : (s.qMin === s.qMax ? s.qMin.toFixed(2)
              : s.qMin.toFixed(2) + '–' + s.qMax.toFixed(2));
      return '<div class="sr-seite">' +
        '<span class="sr-sn">' + _srEsc(s.name) + '</span>' +
        '<span class="sr-sbar"><i style="width:' + Math.round(s.geld / maxGeld * 100) + '%"></i></span>' +
        '<span class="sr-sg">' + _srUsd(s.geld) + '</span>' +
        '<span class="sr-sq">' + (q ? '@ ' + q : '') + ' · ' + s.n + '×</span></div>';
    }).join('');

    // Der Feed nennt keinen Nutzer — `user` ist bei Stake immer null. Statt einer Spalte
    // mit lauter Strichen steht dort das, was der Feed wirklich hergibt: Markt und Auswahl.
    var bets = g.wetten.slice(0, 6).map(function (w) {
      var umger = w.einsatzUsd != null && String(w.usdGrund || '').indexOf('kurs') === 0;
      var geld = w.einsatzUsd != null
        ? '<span class="sr-bg"' + (umger ? ' title="' + _srEsc(w.betrag) + ' ' +
            _srEsc((w.waehrung || '').toUpperCase()) + ', umgerechnet mit Stakes Kurs"' : '') + '>' +
          _srUsd(w.einsatzUsd) + (umger ? '<span class="sr-um">≈</span>' : '') + '</span>'
        : '<span class="sr-bg sr-unk" title="Einsatz in ' + _srEsc(w.waehrung || '?') +
          ' — kein USD-Kurs im Feed, deshalb nicht mitgerechnet">? ' + _srEsc(w.waehrung || '') + '</span>';
      var q = w.kombi ? (w.beinQuote != null ? w.beinQuote : w.quote) : w.quote;
      return '<div class="sr-bet' + (w.kombi ? ' sr-kombi' : '') + '">' +
        '<span class="sr-bt">' + _srZeit(w.ts) + '</span>' +
        '<span class="sr-bm">' + _srEsc(w.markt || '—') + '</span>' +
        '<span class="sr-bs">' + _srEsc(w.auswahl || '—') +
          (w.kombi ? ' <span class="sr-kb" title="Kombi ueber ' + (w.nBeine || '?') +
            ' Spiele — der Einsatz haengt an allen Beinen, deshalb zaehlt er nicht ins Spielgeld">' +
            (w.nBeine || '?') + 'er-Kombi</span>' : '') + '</span>' +
        '<span class="sr-bo">' + (q != null ? Number(q).toFixed(2) : '—') + '</span>' + geld + '</div>';
    }).join('');

    var dichte = g.dichte
      ? '<span title="Beobachtung ohne Beleg: dass dichte Einsätze etwas vorhersagen, ist im Projekt nicht gemessen">' +
        'dichteste Folge <b>' + g.dichte.n + '×</b> in ' + Math.round(g.dichte.min) + ' min</span>'
      : '';
    var unbek = g.nGeldUnbekannt
      ? '<span class="sr-tag" title="Einsatz in einer Währung ohne USD-Kurs im Feed">' +
        g.nGeldUnbekannt + ' ohne $-Wert</span>' : '';
    var komb = g.nKombi
      ? '<span class="sr-tag" title="Kombiwetten: der Einsatz haengt an mehreren Spielen und ist ' +
        'diesem hier nicht zurechenbar — sie werden gezeigt, aber nicht mitgerechnet">' +
        g.nKombi + ' Kombi</span>' : '';

    return '<div class="sr-card">' +
      '<div class="sr-ch"><span class="sr-ev">' + _srEsc(g.event || '—') + '</span>' +
      '<span class="sr-lg">' + _srEsc(g.liga || g.sport || '') + '</span></div>' +
      '<div class="sr-meta">' +
        '<span class="sr-geld">Geld <b>' + _srUsd(g.geldUsd) + '</b>' +
          (g.nGeldBekannt !== g.n ? ' <span style="color:#6b7480">aus ' + g.nGeldBekannt + '/' + g.n + '</span>' : '') + '</span>' +
        '<span><b>' + g.nEinzel + '</b> Einzelwetten</span>' +
        (dichte ? '<span>' + dichte + '</span>' : '') +
        '<span>zuletzt ' + _srZeit(g.letzte) + '</span>' + unbek + komb +
      '</div>' +
      '<div class="sr-seiten">' + seiten + '</div>' +
      '<div class="sr-bets">' + bets +
        (g.n > 6 ? '<div class="sr-mehr">+ ' + (g.n - 6) + ' weitere</div>' : '') +
      '</div></div>';
  }

  // ── Render ────────────────────────────────────────────────────────────────
  function _srRender() {
    var el = document.getElementById('stakeRadarPanel');
    if (!el) return;
    var d = SR.daten;

    var kopf = '<div class="sr-head"><span class="sr-ic">🎰</span><h1>Stake Radar</h1>' +
      '<div class="sr-sub">Große Einzelwetten, wie Stake sie öffentlich anzeigt. Die einzige ' +
      'Quelle hier, die einen <b>einzelnen Einsatz mit Betrag</b> nennt. Reine Sammlung — es gibt ' +
      'für diesen Fluss noch keine gemessene Trefferquote und keinen gemessenen CLV, deshalb ' +
      'steht auf keiner Karte „stark" oder „schwach". Die Regler filtern, sie urteilen nicht.</div></div>';

    if (!d) { el.innerHTML = kopf + '<div class="sr-loading">lädt …</div>'; return; }

    if (d.status === 'schema_unbekannt' || d.status === 'fehler') {
      el.innerHTML = kopf +
        '<div class="sr-warn"><b>Kein Feed.</b> Der Sammler kommt gerade nicht an Stakes Schnittstelle: ' +
        _srEsc(d.notiz || d.status) + '. Es werden bewusst <b>keine</b> alten Zahlen als aktuell gezeigt.</div>';
      return;
    }

    var seit = d.sammlungSeit ? new Date(d.sammlungSeit) : null;
    var tage = seit ? Math.max(0, Math.round((Date.now() - seit.getTime()) / 86400000)) : null;
    var basis = '<div class="sr-basis">' +
      '<span>Sammlung seit <b>' + (seit ? seit.toLocaleDateString('de-DE') : '—') + '</b>' +
        (tage != null ? ' (' + tage + ' T)' : '') + '</span>' +
      '<span>im Ledger <b>' + (d.nLedger || 0) + '</b> Wetten</span>' +
      '<span>im Feed-Fenster <b>' + (d.nFenster || 0) + '</b></span>' +
      (d.nEinsatzUnbekannt ? '<span style="color:#e3b341">ohne $-Wert <b>' + d.nEinsatzUnbekannt + '</b></span>' : '') +
      (d.kurse && d.kurse.quelle
        ? '<span title="Nicht-USD-Einsätze werden mit Stakes eigenen Kursen umgerechnet">Kurse <b>' +
          _srEsc(d.kurse.quelle === 'live' ? 'frisch' : d.kurse.quelle) + '</b></span>' : '') +
      '<span>Stand <b>' + _srZeit(d.asof) + '</b></span></div>';

    var warn = '<div class="sr-warn">Der Feed ist <b>anonym</b> — Stake nennt zu keiner Wette ein ' +
      'Konto. Ein Track-Record je Spieler, wie ihn die Poly-Wallets tragen, ist hier also ' +
      'unmöglich; es gibt nur aggregierten Fluss. Dazu kommt die „Wetten verbergen"-Einstellung: ' +
      'wer sie nutzt, taucht gar nicht erst auf. ' +
      'Die Liste ist damit <b>eine Auswahl, keine Grundgesamtheit</b>. ' +
      'Bevor daraus ein Signal wird, muss der Fluss gegen den ' +
      'Pinnacle-Schlusskurs gemessen werden.</div>';

    var jetzt = Date.now(), ab = jetzt - SR_FENSTER_H * 3600000;
    var roh = (d.wetten || []).filter(function (w) {
      if (w.einsatzUsd == null || w.einsatzUsd < SR_MIN_USD) return false;
      var t = _srMs(w.ts); if (t == null || t < ab) return false;
      if (SR_SPORT !== 'alle' && w.sport !== SR_SPORT) return false;
      return true;
    });

    var gruppen = _srGruppen(roh).filter(function (g) { return g.n >= SR_MIN_N; });
    gruppen.sort(function (a, b) {
      if (SR_SORT === 'dichte') {
        var bn = b.dichte ? b.dichte.n : 0, an = a.dichte ? a.dichte.n : 0;
        if (bn !== an) return bn - an;
        return (a.dichte ? a.dichte.min : 1e9) - (b.dichte ? b.dichte.min : 1e9);
      }
      if (SR_SORT === 'zeit') return (_srMs(b.letzte) || 0) - (_srMs(a.letzte) || 0);
      return b.geldUsd - a.geldUsd;
    });

    var treffer = '<div class="sr-basis"><span><b>' + gruppen.length + '</b> Spiele über den Reglern' +
      ' — aus <b>' + roh.length + '</b> Wetten ab ' + _srUsd(SR_MIN_USD) + ' in ' + SR_FENSTER_H + 'h</span></div>';

    var koerper = gruppen.length
      ? '<div class="sr-grid">' + gruppen.slice(0, 60).map(_srKarte).join('') + '</div>'
      : '<div class="sr-empty">Kein Spiel über diesen Schwellen im Fenster.<br>' +
        'Regler runter, oder der Feed hat gerade nichts Großes.</div>';

    el.innerHTML = kopf + basis + warn + _srCtrl() + treffer + koerper;
  }

  // ── Einstieg ──────────────────────────────────────────────────────────────
  window.initStakeRadar = function () {
    _srStyle();
    if (SR.geladen) { _srRender(); return; }
    SR.geladen = true;
    _srRender();
    fetch('stake_highroller.json?t=' + Date.now())
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { SR.daten = j || { status: 'fehler', notiz: 'stake_highroller.json nicht lesbar' }; _srRender(); })
      .catch(function () { SR.daten = { status: 'fehler', notiz: 'stake_highroller.json nicht erreichbar' }; _srRender(); });
  };

  // Für Tests
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { _srGruppen: _srGruppen, _srDichte: _srDichte, _srUsd: _srUsd };
  }
})();
