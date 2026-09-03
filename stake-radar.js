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

  // 03.09.2026 (Lucas: „Ganze US-Sport brauch ich aktuell mal nicht. Ähnlich Poly").
  // Die Sperrliste kommt aus stake_highroller.json (dort: GESPERRT in stake_highroller_fetch.py),
  // damit sie NICHT zweimal definiert ist — dieselbe Konstruktion wie PW_BLOCKED_BET_CATS im
  // Poly-Tab. Der Rückfall greift nur, wenn die Datei sie nicht mitschickt.
  var SR_OFFEN = {};          // welche Karten aufgeklappt sind
  var SR_NUR_SPIELBAR = false;  // nur was noch nicht (oder kaum) läuft
  var SR_GESPERRT_FALLBACK = ['US-Sport'];
  function _srGesperrt() {
    var d = SR.daten || {};
    return (d.gesperrt && d.gesperrt.length) ? d.gesperrt : SR_GESPERRT_FALLBACK;
  }
  // Kategorie einer Wette. Aus dem Feld, sonst grob nachgerechnet — Zeilen aus der Zeit
  // vor dem Feld sollen nicht durch den Filter rutschen, nur weil sie älter sind.
  function _srKat(w) {
    if (w.kat) return w.kat;
    var x = ' ' + String((w.sport || '') + ' ' + (w.liga || '')).toLowerCase() + ' ';
    if (/ nba | mlb | nfl | nhl | wnba | ncaa |basketball|baseball|ice-?hockey/.test(x)) return 'US-Sport';
    if (/tennis| wta | atp /.test(x)) return 'Tennis';
    if (/esport|cs2|csgo| lol |dota|valorant|counter-strike|league-of-legends|fifa/.test(x)) return 'E-Sport';
    if (/soccer|liga|ligue|serie|premier|bundesliga|eredivisie| mls | epl | ucl | uel /.test(x)) return 'Fußball';
    return 'Sonstige';
  }

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
'.sr-tag{font-size:9px;font-weight:800;letter-spacing:.4px;padding:2px 7px;border-radius:6px;text-transform:uppercase;color:#e3b341;border:1px solid rgba(201,133,0,.42)}',
'.sr-nav{display:flex;gap:6px;margin:16px 0 14px;flex-wrap:wrap}',
'.sr-nb{background:#151b24;border:1px solid #242c38;color:#9aa4b1;font:inherit;font-size:12.5px;font-weight:700;padding:7px 15px;border-radius:9px;cursor:pointer}',
'.sr-nb.on{background:rgba(103,204,145,.16);border-color:rgba(103,204,145,.42);color:#67cc91}',
'.sr-tw{overflow-x:auto;border:1px solid #242c38;border-radius:12px;background:#131922}',
'.sr-t{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}',
'.sr-t th{text-align:left;font-size:10px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;color:#6b7480;padding:9px 11px;border-bottom:1px solid #242c38;white-space:nowrap}',
'.sr-t td{padding:8px 11px;border-bottom:1px solid #1c232e;vertical-align:top}',
'.sr-t tr:last-child td{border-bottom:0}',
'.sr-t .sr-r{text-align:right}',
'.sr-t .sr-geldz{color:#67cc91;font-weight:800}',
'.sr-mut{color:#6b7480}.sr-sm{font-size:10.5px;line-height:1.45;margin-top:2px;max-width:340px}',
'.sr-ug{color:#8a95ad;font-weight:700}.sr-ug.sr-ok{color:#4ade80}',
'.sr-w{color:#4ade80;font-weight:700}.sr-l{color:#e5534b;font-weight:700}',
'.sr-kpi{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 14px}',
'.sr-k{flex:1;min-width:120px;background:#131922;border:1px solid #242c38;border-radius:11px;padding:10px 13px}',
'.sr-kv{font-size:19px;font-weight:800;color:#e6ebf5;font-variant-numeric:tabular-nums}',
'.sr-kl{font-size:10.5px;color:#6b7480;text-transform:uppercase;letter-spacing:.03em;margin-top:2px}',
'.sr-h3{font-size:13px;font-weight:800;margin:18px 0 8px;color:#c2ccd8}',
'.sr-note{margin:12px 0 0;font-size:11.5px;line-height:1.6;color:#76819c}',
'.sr-bad{font-size:9.5px;font-weight:800;letter-spacing:.3px;padding:2px 7px;border-radius:6px;white-space:nowrap}',
'.sr-bad.sr-norm{color:#f2c14e;border:1px solid rgba(234,185,56,.45);background:rgba(234,185,56,.10)}',
'.sr-bad.sr-konf{color:#e3b341;border:1px solid rgba(201,133,0,.42)}',
'.sr-card.sr-card-norm{border-color:rgba(234,185,56,.38)}',
'.sr-ko{color:#8fc0ff;font-weight:700}.sr-live{color:#ff7a70;font-weight:700}',
'.sr-warnz{color:#e3b341;font-weight:700}',
'.sr-btn{background:none;border:0;color:#5c6577;font:inherit;font-size:10.5px;cursor:pointer;padding:4px 0 0;text-align:left}',
'.sr-btn:hover{color:#9aa4b1}'
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

  /** Der groesste EINZELNE Einsatz auf dieses Spiel, gemessen an der Norm seiner Liga.
      Nicht die Summe: zehn Wetten a $2.000 sind ein normaler Abend, EINE ueber $30.000 ist
      das Ereignis. Ohne gelernte Norm gibt es keinen Faktor — nicht 1.0, nicht 0. */
  function _srNormFaktor(g) {
    var n = (SR_AUS && SR_AUS.ligaNorm && SR_AUS.ligaNorm[g.liga]) || null;
    if (!n || n.basis !== 'gelernt' || !n.median) return null;
    var groesster = 0;
    g.wetten.forEach(function (w) {
      if (!w.kombi && w.einsatzUsd != null && w.einsatzUsd > groesster) groesster = w.einsatzUsd;
    });
    if (!groesster) return null;
    return { faktor: groesster / n.median, median: n.median, n: n.n, groesster: groesster };
  }

  /** Grosses Geld auf ZWEI Seiten heisst: der Markt ist sich uneinig, nicht dass jemand
      Bescheid weiss. Der Poly-Tab markiert genau das seit dem 12.08. als „umkaempft" und
      unterdrueckt solche Faelle im oeffentlichen Kanal — hier wird es wenigstens markiert. */
  var SR_UMKAEMPFT_ANTEIL = 0.30;
  function _srUmkaempft(g) {
    if (!g.geldUsd || g.seiten.length < 2) return false;
    var zweit = g.seiten[1];
    return (zweit.geld / g.geldUsd) >= SR_UMKAEMPFT_ANTEIL;
  }

  /** Minuten bis Anpfiff (negativ = laeuft). null, wenn kein Anpfiff bekannt ist. */
  function _srBisAnpfiff(g) {
    var t = _srMs(g.anpfiff);
    return t == null ? null : Math.round((t - Date.now()) / 60000);
  }
  function _srAnpfiffText(g) {
    var m = _srBisAnpfiff(g);
    if (m == null) return '';
    if (m > 0) {
      var h = Math.floor(m / 60);
      return '<span class="sr-ko">⏱ ' + (h ? h + ' h ' + (m % 60) + ' min' : m + ' min') + '</span>';
    }
    return '<span class="sr-live">🔴 ' + (-m) + '. Min</span>';
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
      g.anpfiff = g.anpfiff || (g.wetten.find(function (w) { return w.anpfiff; }) || {}).anpfiff;
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
      grp('sortiert', ['geld', 'norm', 'dichte', 'zeit'], SR_SORT, '_srSetSort', function (v) {
        return { geld: 'Geld', norm: '× Norm', dichte: 'Dichte', zeit: 'zuletzt' }[v];
      }) +
      // Der praktische Filter: was noch nicht angepfiffen ist oder gerade erst läuft.
      // Ein Einsatz in der 85. Minute auf den Führenden ist kein Signal — dieselbe Lehre
      // wie beim Hapoel-Push, hier als Schalter statt als harte Grenze.
      '<div class="sr-cg"><span class="sr-cl">Zeitpunkt</span>' +
      '<button class="sr-fb' + (SR_NUR_SPIELBAR ? ' on' : '') + '" onclick="_srSetSpielbar()" ' +
      'title="Nur Spiele, die noch nicht angepfiffen sind oder erst seit höchstens 30 Minuten laufen">' +
      (SR_NUR_SPIELBAR ? '✓ ' : '') + 'noch spielbar</button></div>' +
      '</div>';
  }

  function _srSports() {
    var s = {}, w = (SR.daten && SR.daten.wetten) || [], sperr = _srGesperrt();
    w.forEach(function (b) {
      if (b.sport && sperr.indexOf(_srKat(b)) < 0) s[b.sport] = 1;
    });
    return Object.keys(s).sort().slice(0, 8);
  }

  window._srAufklappen = function (k) { SR_OFFEN[k] = !SR_OFFEN[k]; _srRender(); };
  window._srSetSpielbar = function () { SR_NUR_SPIELBAR = !SR_NUR_SPIELBAR; _srRender(); };
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
    var alleZeigen = SR_OFFEN[g.key];
    var bets = g.wetten.slice(0, alleZeigen ? 40 : 6).map(function (w) {
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

    var nf = _srNormFaktor(g);
    var badges =
      (nf && nf.faktor >= 3 ? '<span class="sr-bad sr-norm" title="Größter Einzeleinsatz ' +
        _srUsd(nf.groesster) + ' gegen den Median dieser Liga (' + _srUsd(nf.median) +
        ', aus n' + nf.n + ')">×' + nf.faktor.toFixed(1) + ' Norm</span>' : '') +
      (_srUmkaempft(g) ? '<span class="sr-bad sr-konf" title="Mindestens 30 % des Geldes ' +
        'liegen auf einer zweiten Seite — der Markt ist sich uneinig, das ist kein ' +
        'einheitlicher Fluss">⚔️ umkämpft</span>' : '');

    return '<div class="sr-card' + (nf && nf.faktor >= 3 ? ' sr-card-norm' : '') + '">' +
      '<div class="sr-ch"><span class="sr-ev">' + _srEsc(g.event || '—') + '</span>' + badges +
      '<span class="sr-lg">' + _srAnpfiffText(g) + ' · ' + _srEsc(g.liga || g.sport || '') + '</span></div>' +
      '<div class="sr-meta">' +
        '<span class="sr-geld">Geld <b>' + _srUsd(g.geldUsd) + '</b>' +
          (g.nGeldBekannt !== g.n ? ' <span style="color:#6b7480">aus ' + g.nGeldBekannt + '/' + g.n + '</span>' : '') + '</span>' +
        '<span><b>' + g.nEinzel + '</b> Einzelwetten</span>' +
        (dichte ? '<span>' + dichte + '</span>' : '') +
        '<span>zuletzt ' + _srZeit(g.letzte) + '</span>' + unbek + komb +
      '</div>' +
      '<div class="sr-seiten">' + seiten + '</div>' +
      '<div class="sr-bets">' + bets +
        (g.n > 6 ? '<button class="sr-mehr sr-btn" onclick="_srAufklappen(\'' +
          _srEsc(g.key).replace(/'/g, '') + '\')">' +
          (alleZeigen ? '▴ weniger' : '▾ + ' + (g.n - 6) + ' weitere') + '</button>' : '') +
      '</div></div>';
  }

  // ══ TERMINAL ═══════════════════════════════════════════════════════════════
  // 03.09.2026 (Lucas: „in Wahrheit kannst ja gleich so ein Terminal bauen oder wie bei
  // Betfair und Polymarket"). Dichtes Board statt Karten: vier Ansichten auf dieselbe
  // Sammlung, jede mit ihrer Basis in der Kopfzeile.
  //
  //   Spiele      — was gerade laeuft, gruppiert (die Kartenansicht von vorher)
  //   Auffaellig  — Einsatz gegen die NORM SEINER LIGA, nicht gegen eine erfundene Zahl
  //   Bilanz      — Trefferquote je Schublade, immer mit Wilson-Untergrenze
  //   Norm        — was in welcher Liga ueberhaupt ein grosser Einsatz ist
  //
  // Die letzten drei lesen stake_auswertung.json (vom Runner, stake_analyse.py). Fehlt die
  // Datei, steht das da — und nicht eine leere Tabelle, die wie „nichts gefunden" aussaehe.

  var SR_TAB = 'spiele';
  var SR_AUS = null;         // stake_auswertung.json
  var SR_AUS_STATUS = 'lädt';

  function _srPct(x, stellen) {
    return (x == null || !isFinite(x)) ? '—' : (x * 100).toFixed(stellen == null ? 1 : stellen) + '%';
  }

  function _srNav() {
    var tabs = [['spiele', '⚽ Spiele'], ['auffaellig', '🚩 Auffällig'],
                ['bilanz', '🧾 Bilanz'], ['norm', '📐 Norm']];
    return '<div class="sr-nav">' + tabs.map(function (t) {
      return '<button class="sr-nb' + (SR_TAB === t[0] ? ' on' : '') +
        '" onclick="_srTab(\'' + t[0] + '\')">' + t[1] + '</button>';
    }).join('') + '</div>';
  }
  window._srTab = function (t) { SR_TAB = t; _srRender(); };

  /** Eine Zahl ohne Basis ist im Rest des Boards verboten — hier auch. */
  function _srBasis(s) {
    if (!s || !s.n) return '<span class="sr-mut">keine Basis</span>';
    var q = _srPct(s.quote), ug = s.ug == null ? null : _srPct(s.ug);
    return '<b>' + q + '</b> <span class="sr-mut">· n' + s.n + '</span>' +
      (ug ? ' <span class="sr-ug' + (s.belegt ? ' sr-ok' : '') + '">UG ' + ug + '</span>'
          : ' <span class="sr-mut" title="Unter n=' + (SR_AUS ? SR_AUS.urteilAb : 30) +
            ' geben wir keine Untergrenze aus — ein Punktschätzer ist kein Beleg">kein Urteil</span>');
  }

  function _srUnreif(was) {
    var b = (SR_AUS && SR_AUS.bilanz) || {};
    return '<div class="sr-empty"><b>' + was + ' braucht abgerechnete Wetten.</b><br>' +
      'Bisher: ' + (b.gewertet || 0) + ' gewertete Beine, ' + (b.offen || 0) + ' noch offen.<br>' +
      '<span class="sr-mut">Stake rechnet selbst ab — jede Wette wird ein paar Stunden nach ' +
      'Anpfiff nachgefragt. Ein Urteil gibt es ab n=' + (SR_AUS ? SR_AUS.urteilAb : 30) + '.</span></div>';
  }

  // ── Auffällig ───────────────────────────────────────────────────────────────
  function _srAuffaellig() {
    var rows = (SR_AUS && SR_AUS.auffaellige) || [];
    if (!rows.length) {
      return '<div class="sr-empty">Noch nichts über der Norm.<br><span class="sr-mut">' +
        'Eine Liga-Norm entsteht ab 15 Wetten in derselben Liga — vorher ist „auffällig" ' +
        'nicht entscheidbar.</span></div>';
    }
    return '<div class="sr-tw"><table class="sr-t"><thead><tr>' +
      '<th>Zeit</th><th>Liga</th><th>Spiel</th><th>Auswahl</th>' +
      '<th class="sr-r">Einsatz</th><th class="sr-r">Quote</th><th>Warum auffällig</th><th>Ausgang</th>' +
      '</tr></thead><tbody>' +
      rows.map(function (r) {
        var aus = r.ausgang === 'won' ? '<span class="sr-w">Treffer</span>'
                : r.ausgang === 'lost' ? '<span class="sr-l">daneben</span>'
                : '<span class="sr-mut">offen</span>';
        return '<tr><td class="sr-mut">' + _srZeit(r.ts) + '</td>' +
          '<td>' + _srEsc(r.liga || '—') + '</td>' +
          '<td>' + _srEsc(r.event || '—') + '</td>' +
          '<td>' + _srEsc(((r.markt ? r.markt + ': ' : '') + (r.auswahl || '—'))) + '</td>' +
          '<td class="sr-r sr-geldz">' + _srUsd(r.einsatzUsd) + '</td>' +
          '<td class="sr-r">' + (r.quote != null ? Number(r.quote).toFixed(2) : '—') + '</td>' +
          '<td class="sr-mut">' + _srEsc(r.grund) + '</td>' +
          '<td>' + aus + '</td></tr>';
      }).join('') + '</tbody></table></div>' +
      '<div class="sr-note">Zwei verschiedene Gründe, absichtlich nicht vermischt: ' +
      '<b>× Median der Liga</b> ist gemessen — die Liga hat genug Wetten für eine Norm. ' +
      '<b>kleine Liga</b> ist schwächer — dort gibt es keine Norm, nur wenige Wetten und einen ' +
      'Einsatz über dem globalen 90 %-Punkt.</div>';
  }

  // ── Bilanz ──────────────────────────────────────────────────────────────────
  var _SR_SCHUBLADEN = [
    ['vor_anpfiff', 'vor Anpfiff', 'Nur hier ist CLV gegen den Schlusskurs überhaupt möglich.'],
    ['live', 'live', '83 % des Feeds — aber ohne Schlusskurs, also nur über die Abrechnung messbar.'],
    ['live_frueh', 'live, ≤ 30. Min', 'Wenn Live etwas taugt, dann früh.'],
    ['live_spaet', 'live, > 60. Min', 'Späte Einsätze auf den Führenden sind kein Signal — Gegenprobe.'],
    ['einsatz_ab_10k', 'ab $10k', 'Trägt Größe allein etwas? Die Vorlage behauptet ja, ohne Beleg.'],
    ['einsatz_1k_10k', '$1k – $10k', 'Die Vergleichsgruppe dazu.'],
    ['ueber_liga_norm', 'über Liga-Norm', 'Die eigentliche These: auffällig ist relativ.'],
  ];

  function _srBilanz() {
    if (!SR_AUS) return '<div class="sr-empty">stake_auswertung.json fehlt noch.</div>';
    var b = SR_AUS.bilanz || {};
    if (!b.gewertet) return _srUnreif('Die Bilanz');
    var s = SR_AUS.schubladen || {};
    var zeilen = _SR_SCHUBLADEN.filter(function (x) { return s[x[0]]; }).map(function (x) {
      var d = s[x[0]];
      return '<tr><td><b>' + x[1] + '</b><div class="sr-mut sr-sm">' + x[2] + '</div></td>' +
        '<td class="sr-r">' + d.wetten + '</td>' +
        '<td class="sr-r">' + d.n + '</td>' +
        '<td>' + _srBasis(d) + '</td>' +
        '<td class="sr-r">' + (d.roi == null ? '—' : _srPct(d.roi)) +
          (d.einzelN ? '<div class="sr-mut sr-sm">' + d.einzelN + ' Einzelwetten</div>' : '') +
        '</td></tr>';
    }).join('');

    var ligen = Object.keys(SR_AUS.jeLiga || {}).map(function (k) {
      var d = SR_AUS.jeLiga[k];
      return '<tr><td>' + _srEsc(k) + '</td><td class="sr-r">' + d.n + '</td><td>' + _srBasis(d) + '</td></tr>';
    }).join('');

    return '<div class="sr-kpi">' +
        _srKpi(b.gewertet, 'Beine gewertet') +
        _srKpi(b.treffer + ' / ' + b.daneben, 'Treffer / daneben') +
        _srKpi(b.quote == null ? '—' : _srPct(b.quote), 'rohe Quote') +
        _srKpi(b.offen, 'noch offen') +
        _srKpi(b.unaufloesbar, 'unauflösbar') +
      '</div>' +
      '<div class="sr-tw"><table class="sr-t"><thead><tr><th>Schublade</th>' +
      '<th class="sr-r">Wetten</th><th class="sr-r">Beine</th><th>Trefferquote</th>' +
      '<th class="sr-r">ROI</th></tr></thead><tbody>' + zeilen + '</tbody></table></div>' +
      (ligen ? '<h3 class="sr-h3">Je Liga</h3><div class="sr-tw"><table class="sr-t"><thead><tr>' +
        '<th>Liga</th><th class="sr-r">Beine</th><th>Trefferquote</th></tr></thead><tbody>' +
        ligen + '</tbody></table></div>' : '') +
      _srGesperrteSchubladen() +
      '<div class="sr-note">Die Trefferquote zählt <b>Beine</b>, nicht Wetten — ein Bein ist ' +
      'eine Meinung zu einem Spiel. Der ROI zählt nur <b>Einzelwetten</b>: bei einer Kombi ' +
      'hängt der Einsatz an mehreren Spielen und ist keinem davon zurechenbar. Annullierte ' +
      'Beine fallen aus der Quote heraus, statt als Fehlschlag zu zählen.</div>';
  }

  /** Gesperrte Sportarten stehen weiter da — nur getrennt und ohne ins Urteil zu zählen.
      Sonst könnte man nie merken, dass eine davon dreht; ein Wiedereintritt braucht Zahlen. */
  function _srGesperrteSchubladen() {
    var g = (SR_AUS && SR_AUS.gesperrteSchubladen) || {};
    var keys = Object.keys(g);
    if (!keys.length) return '';
    return '<h3 class="sr-h3">Ausgeblendet — mitgeschrieben, nicht mitgezählt</h3>' +
      '<div class="sr-tw"><table class="sr-t"><thead><tr><th>Sportart</th>' +
      '<th class="sr-r">Wetten</th><th class="sr-r">Beine</th><th>Trefferquote</th>' +
      '</tr></thead><tbody>' + keys.map(function (k) {
        var d = g[k];
        return '<tr><td>' + _srEsc(k) + '</td><td class="sr-r">' + d.wetten + '</td>' +
          '<td class="sr-r">' + d.n + '</td><td>' + _srBasis(d) + '</td></tr>';
      }).join('') + '</tbody></table></div>';
  }

  function _srKpi(v, l) {
    return '<div class="sr-k"><div class="sr-kv">' + v + '</div><div class="sr-kl">' + l + '</div></div>';
  }

  // ── Norm ────────────────────────────────────────────────────────────────────
  function _srNorm() {
    var n = (SR_AUS && SR_AUS.ligaNorm) || {};
    var keys = Object.keys(n);
    if (!keys.length) return '<div class="sr-empty">Noch keine Liga-Daten.</div>';
    var gelernt = keys.filter(function (k) { return n[k].basis === 'gelernt'; });
    var duenn = keys.filter(function (k) { return n[k].basis !== 'gelernt'; });
    return '<div class="sr-note" style="margin-top:0">Was in welcher Liga ein <b>großer</b> ' +
      'Einsatz ist, wird aus unseren eigenen Daten gelernt — nicht festgelegt. $9.000 auf ' +
      'La Liga ist Dienstag, $9.000 in einer ruhigen Liga ein Ereignis. Unter 15 Wetten gibt ' +
      'es keine Norm, und dann steht dort auch keine Zahl.</div>' +
      '<div class="sr-tw"><table class="sr-t"><thead><tr><th>Liga</th><th class="sr-r">Wetten</th>' +
      '<th class="sr-r">Median</th><th class="sr-r">90 %-Punkt</th><th class="sr-r">größter</th>' +
      '</tr></thead><tbody>' +
      gelernt.map(function (k) {
        var d = n[k];
        return '<tr><td>' + _srEsc(k) + '</td><td class="sr-r">' + d.n + '</td>' +
          '<td class="sr-r sr-geldz">' + _srUsd(d.median) + '</td>' +
          '<td class="sr-r">' + _srUsd(d.p90) + '</td>' +
          '<td class="sr-r sr-mut">' + _srUsd(d.max) + '</td></tr>';
      }).join('') + '</tbody></table></div>' +
      (duenn.length ? '<div class="sr-note"><b>' + duenn.length + ' Ligen ohne Norm</b> ' +
        '(unter 15 Wetten): ' + duenn.slice(0, 20).map(function (k) {
          return _srEsc(k) + ' <span class="sr-mut">' + n[k].n + '</span>';
        }).join(' · ') + (duenn.length > 20 ? ' …' : '') +
        '<br><span class="sr-mut">Über diese ist nichts bekannt — das ist etwas anderes als ' +
        '„unauffällig". Genau hier sitzt aber der Fall, den wir suchen, deshalb greift für sie ' +
        'das schwächere Kriterium auf dem Auffällig-Reiter.</span></div>' : '');
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
      '<span>Stand <b>' + _srZeit(d.asof) + '</b></span>' +
      // Stakes Deckel liegt bei 50 Einträgen je Abruf. Deckt ein Abruf weniger Zeit ab als
      // der Abstand zum nächsten, fehlt dazwischen alles — und zwar am ehesten dann, wenn
      // viel los ist. Das gehört auf die Fläche, nicht nur ins JSON.
      (d.luecke && d.luecke.luecke
        ? '<span class="sr-warnz" title="Zwischen zwei Abrufen lagen mehr Wetten, als der Feed ' +
          'auf einmal hergibt (50). Was dazwischen lag, haben wir nicht gesehen.">⚠ Lücke ' +
          d.luecke.lueckeMin + ' min</span>'
        : (d.luecke && d.luecke.abdeckungMin != null
            ? '<span class="sr-mut">Abruf deckt ' + d.luecke.abdeckungMin + ' min</span>' : '')) +
      '</div>';

    var warn = '<div class="sr-warn">Der Feed ist <b>anonym</b> — Stake nennt zu keiner Wette ein ' +
      'Konto. Ein Track-Record je Spieler, wie ihn die Poly-Wallets tragen, ist hier also ' +
      'unmöglich; es gibt nur aggregierten Fluss. Dazu kommt die „Wetten verbergen"-Einstellung: ' +
      'wer sie nutzt, taucht gar nicht erst auf. ' +
      'Die Liste ist damit <b>eine Auswahl, keine Grundgesamtheit</b>. ' +
      'Bevor daraus ein Signal wird, muss der Fluss gegen den ' +
      'Pinnacle-Schlusskurs gemessen werden.</div>';

    var jetzt = Date.now(), ab = jetzt - SR_FENSTER_H * 3600000;
    var sperr = _srGesperrt(), nGesperrt = 0;
    var roh = (d.wetten || []).filter(function (w) {
      if (w.einsatzUsd == null || w.einsatzUsd < SR_MIN_USD) return false;
      var t = _srMs(w.ts); if (t == null || t < ab) return false;
      // Ein stiller Filter ist genau die Sorte Fehler, die wir hier ausräumen — deshalb
      // wird gezählt, was weggelassen wird, und die Zahl steht unten drunter.
      if (sperr.indexOf(_srKat(w)) >= 0) { nGesperrt++; return false; }
      if (SR_SPORT !== 'alle' && w.sport !== SR_SPORT) return false;
      return true;
    });

    var gruppen = _srGruppen(roh).filter(function (g) { return g.n >= SR_MIN_N; });
    var vorSpielbar = gruppen.length;
    if (SR_NUR_SPIELBAR) {
      gruppen = gruppen.filter(function (g) {
        var m = _srBisAnpfiff(g);
        return m == null || m > -30;      // noch nicht angepfiffen oder max. 30 Min drin
      });
    }
    gruppen.sort(function (a, b) {
      if (SR_SORT === 'norm') {
        var fa = _srNormFaktor(a), fb = _srNormFaktor(b);
        return (fb ? fb.faktor : -1) - (fa ? fa.faktor : -1);
      }
      if (SR_SORT === 'dichte') {
        var bn = b.dichte ? b.dichte.n : 0, an = a.dichte ? a.dichte.n : 0;
        if (bn !== an) return bn - an;
        return (a.dichte ? a.dichte.min : 1e9) - (b.dichte ? b.dichte.min : 1e9);
      }
      if (SR_SORT === 'zeit') return (_srMs(b.letzte) || 0) - (_srMs(a.letzte) || 0);
      return b.geldUsd - a.geldUsd;
    });

    var treffer = '<div class="sr-basis"><span><b>' + gruppen.length + '</b> Spiele über den Reglern' +
      ' — aus <b>' + roh.length + '</b> Wetten ab ' + _srUsd(SR_MIN_USD) + ' in ' + SR_FENSTER_H + 'h</span>' +
      (SR_NUR_SPIELBAR && vorSpielbar > gruppen.length
        ? '<span class="sr-mut">' + (vorSpielbar - gruppen.length) + ' zu weit im Spiel</span>' : '') +
      (nGesperrt ? '<span class="sr-mut" title="' + _srEsc(sperr.join(', ')) + ' ist ausgeblendet. ' +
        'Gesammelt und abgerechnet wird weiter — sonst könnte man nie merken, wenn eine ' +
        'Sportart dreht.">' + nGesperrt + ' ausgeblendet (' + _srEsc(sperr.join(', ')) + ')</span>' : '') +
      '</div>';

    var koerper = gruppen.length
      ? '<div class="sr-grid">' + gruppen.slice(0, 60).map(_srKarte).join('') + '</div>'
      : '<div class="sr-empty">Kein Spiel über diesen Schwellen im Fenster.<br>' +
        'Regler runter, oder der Feed hat gerade nichts Großes.</div>';

    var spiele = _srCtrl() + treffer + koerper;
    var inhalt = SR_TAB === 'spiele' ? spiele
               : SR_TAB === 'auffaellig' ? _srAuffaellig()
               : SR_TAB === 'bilanz' ? _srBilanz()
               : _srNorm();
    if (SR_TAB !== 'spiele' && !SR_AUS) {
      inhalt = '<div class="sr-empty">' + (SR_AUS_STATUS === 'lädt' ? 'lädt …' :
        '<b>stake_auswertung.json nicht lesbar.</b><br><span class="sr-mut">Die Auswertung ' +
        'entsteht auf dem Runner (stake_analyse.py) — bis dahin steht hier nichts, statt einer ' +
        'leeren Tabelle, die wie „nichts gefunden" aussähe.</span>') + '</div>';
    }
    el.innerHTML = kopf + basis + warn + _srNav() + inhalt;
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
    fetch('stake_auswertung.json?t=' + Date.now())
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { SR_AUS = j; SR_AUS_STATUS = j ? 'da' : 'fehlt'; _srRender(); })
      .catch(function () { SR_AUS = null; SR_AUS_STATUS = 'fehlt'; _srRender(); });
  };

  // Für Tests
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { _srGruppen: _srGruppen, _srDichte: _srDichte, _srUsd: _srUsd,
                   _srBasis: _srBasis, _srPct: _srPct, _srKat: _srKat,
                   _srUmkaempft: _srUmkaempft, _srBisAnpfiff: _srBisAnpfiff };
  }
})();
