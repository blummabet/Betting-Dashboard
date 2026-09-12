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
  // 03.09.2026 (Lucas: „@1,03 und 1,2 ist schon relativ low ... wollen wir die 1,35 wieder
  // als Minimum?"). 1,35 ist im Projekt schon der Boden (pick-engine.js, „Cheap ML filter"),
  // deshalb steht er hier als Startwert — aber als REGLER, nicht als Gesetz. Dort geht es um
  // unsere eigenen Wetten, wo bei 1,20 die Marge den Wert frisst; hier geht es um die Meinung
  // eines anderen, und ob die bei 1,20 weniger wert ist, ist noch nicht gemessen. Die
  // Auswertung führt beide Bänder als eigene Schubladen — der Regler blendet aus, er urteilt nicht.
  var SR_MIN_QUOTE = 1.35;
  var SR_QUOTEN = [1.0, 1.20, 1.35, 1.60, 2.00];
  var SR_OFFEN = {};          // welche Karten aufgeklappt sind
  // 🔴 11.09.2026 (Lucas: „die ganzen Spiele da in der Liste unter Spiele, da is vieles alt").
  // Stand auf `false`, und das war der ganze Befund: gemessen am Stand vom 11.09. lagen von 47
  // Gruppen auf dem Board **37 schon über 30 Minuten im Spiel, davon 17 über sechs Stunden** —
  // also längst vorbei. Nur 10 waren überhaupt noch nicht angepfiffen.
  //
  // Der Regler war da, er stand nur falsch herum. Ein Board, dessen Standardansicht zu 79 % aus
  // gelaufenen Spielen besteht, ist kein Radar, sondern ein Archiv — und es versteckt genau die
  // eine Schublade, die im eigenen Buch etwas taugt (`vor_anpfiff`: +2,6 % ROI, UG +1,5 % bei
  // n=11.632, als einzige neben `quote_ab_350` überhaupt belegt).
  var SR_NUR_SPIELBAR = true;   // nur was noch nicht (oder kaum) läuft — s. o.
  // 12.09.2026: haelt den Rueckfall mit stake_highroller_fetch.GESPERRT gleich („Cricket bitte
  // raus"). Greift nur, wenn die Datei die Liste nicht mitschickt — sonst regiert das Artefakt.
  var SR_GESPERRT_FALLBACK = ['US-Sport', 'Cricket'];
  function _srGesperrt() {
    var d = SR.daten || {};
    return (d.gesperrt && d.gesperrt.length) ? d.gesperrt : SR_GESPERRT_FALLBACK;
  }
  // 🔴 04.09.2026 (Lucas: „geh die verbleibenden Duplikate durch"). Hier stand — wie in der
  // Übersicht — ein Nachbau von `sport_kategorie()` aus stake_highroller_fetch.py, als Rückfall
  // für Alt-Zeilen ohne `kat`. Drei Kopien derselben Regel, von denen ein Test nur die beiden
  // JS-Fassungen aneinander band; mit dem Produzenten war keine von beiden deckungsgleich:
  // der kennt 14 Kategorien (Tischtennis, Cricket, Volleyball, Snooker, Badminton, Rugby,
  // Handball, Darts …), der Nachbau vier und warf den Rest auf „Sonstige".
  //
  // Seit heute trägt `ledger_mischen()` die Kategorie auf jeder Zeile nach. Hier wird nur noch
  // gelesen — und eine Zeile ohne Kategorie ist unbekannt, nicht „Sonstige". Bei einer SPERRE
  // ist das der Unterschied, der zählt: unbekannt darf nicht durchrutschen.
  function _srKat(w) { return w.kat || null; }

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
'.sr-nav2{margin:6px 0 8px}',
// Die gepoolte Zeile ist keine dritte Phase, sondern die Summe der beiden darueber —
// abgesetzt, damit niemand sie mitzaehlt.
'.sr-pool td{border-top:1px solid #2b3442;background:rgba(255,255,255,.02)}',
'.sr-bad{font-size:9.5px;font-weight:800;letter-spacing:.3px;padding:2px 7px;border-radius:6px;white-space:nowrap}',
'.sr-bad.sr-norm{color:#f2c14e;border:1px solid rgba(234,185,56,.45);background:rgba(234,185,56,.10)}',
'.sr-bad.sr-norm-schwach{color:#9aa4b2;border:1px dashed rgba(154,164,178,.45);background:none;font-weight:700}',
'.sr-bad.sr-konf{color:#e3b341;border:1px solid rgba(201,133,0,.42)}',
'.sr-card.sr-card-norm{border-color:rgba(234,185,56,.38)}',
'.sr-ko{color:#8fc0ff;font-weight:700}.sr-live{color:#ff7a70;font-weight:700}',
'.sr-vorbei{color:#6e7681;font-weight:700}',
'.sr-sa{min-width:38px;text-align:right;color:#8fc0ff;font-weight:800;font-variant-numeric:tabular-nums}',
'.sr-note-kern{border-left:3px solid #8fc0ff;background:rgba(143,192,255,.06)}',
'.sr-warnz{color:#e3b341;font-weight:700}',
'.sr-btn{background:none;border:0;color:#5c6577;font:inherit;font-size:10.5px;cursor:pointer;padding:4px 0 0;text-align:left}',
'.sr-btn:hover{color:#9aa4b1}',
'.sr-chart{background:#131922;border:1px solid #242c38;border-radius:12px;padding:11px 13px 9px;margin:0 0 14px}',
'.sr-chart-h{display:flex;align-items:baseline;gap:10px;margin-bottom:9px;flex-wrap:wrap}',
'.sr-chart-t{font-size:11px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:#8a95ad}',
'.sr-chart-s{font-size:10.5px;color:#5c6577;margin-left:auto}',
'.sr-meter{vertical-align:middle}',
'.sr-lbs{display:flex;flex-direction:column;gap:5px}',
'.sr-lb{display:flex;align-items:center;gap:9px;font-size:11.5px;font-variant-numeric:tabular-nums}',
'.sr-lb-n{width:190px;flex:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#c2ccd8}',
'.sr-lb-t{flex:1;min-width:60px;height:9px;position:relative;background:#1c232e;border-radius:2px;overflow:hidden}',
'.sr-lb-t i{position:absolute;left:0;top:0;height:100%;border-radius:0 4px 4px 0}',
'.sr-lb-p90{background:rgba(103,204,145,.28)}',
'.sr-lb-med{background:#67cc91}',
'.sr-lb-v{width:60px;text-align:right;flex:none;color:#67cc91;font-weight:800}',
'.sr-lb-n2{width:38px;text-align:right;flex:none;color:#5c6577}',
'.sr-tl{margin:11px 0 0;padding-top:10px;border-top:1px solid #242c38}',
'.sr-tl-l{display:flex;justify-content:space-between;gap:8px;font-size:9.5px;color:#5c6577;margin-top:3px}',
'@media(max-width:600px){.sr-lb-n{width:120px}}'
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
  // 🔴 11.09.2026: `new Date(null)` ist NICHT Invalid Date — es ist der 01.01.1970. Eine Zeile
  // ohne Anpfiff (`anpfiff: null`) lief deshalb durch die null-Pruefung durch und kam als
  // „angepfiffen vor 496.981 h" auf der Karte heraus. Vorher war derselbe Fehler nur besser
  // getarnt: er stand als „🔴 29818860. Min" da. Gefunden beim Schreiben des Tests, der genau
  // diesen Fall nicht als Platzhalter sehen wollte.
  //
  // Fehlerklasse: fehlende Information rendert als harmloser Default — und Epoch 0 ist
  // alles andere als harmlos, weil es ein GUELTIGES Datum ist und jede Pruefung besteht.
  function _srMs(ts) {
    if (ts == null || ts === '') return null;
    var d = new Date(ts);
    return isNaN(d) ? null : d.getTime();
  }

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

  /** Hat der Erzeuger auf diesem Spiel etwas Auffaelliges gemessen?

      04.09.2026 — vorher rechnete diese Funktion den Faktor SELBST: groesster Einsatz durch
      den Liga-Median. Das war zweimal falsch. Erstens ist es Erzeuger-Logik im Frontend, die
      Bug-Klasse, die uns hier schon Geld gekostet hat. Zweitens waechst `x Median` mit der
      Stichprobengroesse (r = +0,68 ueber 31 Ligen) — die Kachel haette also markiert, wo wir
      am laengsten gesammelt haben, nicht wo etwas passiert ist.

      Jetzt wird nur noch nachgeschlagen, was `stake_analyse.py` geurteilt hat. Es gibt zwei
      Staerken, und sie werden nicht vermischt:
        `ueberErwartung` gesetzt → gemessenes Urteil, n-korrigiert.
        sonst                    → nur „x Median", Liga fuer ein Urteil zu duenn (n < 40). */
  var _SR_AUFF_IDX = null;
  function _srAuffIndex() {
    if (_SR_AUFF_IDX) return _SR_AUFF_IDX;
    var m = {};
    ((SR_AUS && SR_AUS.auffaellige) || []).forEach(function (r) {
      var k = r.eventId || ((r.event || '?') + '|' + (r.liga || ''));
      var alt = m[k];
      // Gemessenes Urteil schlaegt Median-Faktor; unter gleichen Zeilen die staerkere.
      var besser = !alt
        || (r.zufallPct != null && alt.zufallPct == null)
        || (r.zufallPct != null && alt.zufallPct != null && r.zufallPct < alt.zufallPct)
        || (r.zufallPct == null && alt.zufallPct == null && (r.faktor || 0) > (alt.faktor || 0));
      if (besser) m[k] = r;
    });
    _SR_AUFF_IDX = m;
    return m;
  }
  function _srNormFaktor(g) {
    return _srAuffIndex()[g.key] || null;
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
  // 🔴 11.09.2026 (Lucas: „was heisst der rote Punkt und die min daneben? ist das vergangen?").
  // Hier stand `🔴 380. Min`. Zwei Dinge waren daran falsch:
  //
  //  1. „380. Min" liest sich als SPIELMINUTE. Gemessen ist die WANDUHR seit Anpfiff — die
  //     Halbzeit zaehlt mit, und bei Cricket oder Tennis hat „Minute" ohnehin keine Bedeutung.
  //     Dieselbe Verwechslung war am 07.09. schon bei den Auswertungs-Schubladen aufgefallen und
  //     dort in der Aufschrift korrigiert worden — hier nicht, obwohl es dieselbe Zahl ist.
  //  2. Der rote Punkt hiess „laeuft". Ein Spiel, das vor sechs Stunden angepfiffen wurde, laeuft
  //     nicht mehr — es stand trotzdem rot da. Lucas' Frage („ist das vergangen?") IST der Befund:
  //     wenn der Leser raten muss, sagt die Anzeige nichts.
  //
  // Der Feed kennt kein Spielende (`phase` kennt nur `vor` und `live`, `spielminute` laeuft bis
  // 3012 weiter). Deshalb wird hier NICHT behauptet, ein Spiel sei zu Ende — es wird nur nicht
  // mehr behauptet, es laufe. Ab SR_LIVE_MAX_MIN steht grau da, wann angepfiffen wurde.
  var SR_LIVE_MAX_MIN = 150;   // darueber ist „laeuft" eine Behauptung, die der Feed nicht deckt

  function _srDauerText(min) {
    var h = Math.floor(min / 60), m = min % 60;
    return h ? (h + ' h ' + (m < 10 ? '0' : '') + m + ' min') : (m + ' min');
  }
  function _srAnpfiffText(g) {
    var m = _srBisAnpfiff(g);
    if (m == null) return '';
    if (m > 0) return '<span class="sr-ko">⏱ in ' + _srDauerText(m) + '</span>';
    var laeuftSeit = -m;
    if (laeuftSeit <= SR_LIVE_MAX_MIN) {
      return '<span class="sr-live" title="Laeuft. Die Zahl ist die WANDUHR seit Anpfiff, nicht ' +
        'die Spielminute — die Halbzeitpause zaehlt mit.">🔴 läuft · seit ' +
        _srDauerText(laeuftSeit) + '</span>';
    }
    return '<span class="sr-vorbei" title="Vor ueber ' + (SR_LIVE_MAX_MIN / 60).toFixed(1) +
      ' h angepfiffen. Der Stake-Feed meldet kein Spielende, deshalb steht hier nicht ' +
      'beendet — aber laeuft waere eine Behauptung, die er auch nicht deckt.">⏹ angepfiffen vor ' +
      _srDauerText(laeuftSeit) + '</span>';
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
      g.gewinnUsd = bek.reduce(function (s, w) {
        var gw = w.gewinnUsd != null ? w.gewinnUsd
               : (w.quote != null && w.quote > 1 ? w.einsatzUsd * (w.quote - 1) : 0);
        return s + (gw || 0);
      }, 0);
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
      grp('ab Quote', SR_QUOTEN, SR_MIN_QUOTE, '_srSetQuote', function (v) {
        return v <= 1 ? 'alle' : v.toFixed(2).replace('.', ',');
      }) +
      grp('ab Wetten', [1, 2, 3, 5], SR_MIN_N, '_srSetN', function (v) { return v + '×'; }) +
      grp('Fenster', SR_FENSTER, SR_FENSTER_H, '_srSetFenster', function (v) { return v + 'h'; }) +
      (sports.length > 1 ? grp('Sport', sports, SR_SPORT, '_srSetSport', function (v) { return _srEsc(v); }) : '') +
      grp('sortiert', ['geld', 'gewinn', 'norm', 'dichte', 'zeit'], SR_SORT, '_srSetSort', function (v) {
        return { geld: 'Einsatz', gewinn: 'zu gewinnen', norm: '× Norm',
                 dichte: 'Dichte', zeit: 'zuletzt' }[v];
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
      var _bk = _srKat(b);
      if (b.sport && _bk && sperr.indexOf(_bk) < 0) s[b.sport] = 1;
    });
    return Object.keys(s).sort().slice(0, 8);
  }

  window._srAufklappen = function (k) { SR_OFFEN[k] = !SR_OFFEN[k]; _srRender(); };
  window._srSetSpielbar = function () { SR_NUR_SPIELBAR = !SR_NUR_SPIELBAR; _srRender(); };
  window._srSetQuote = function (v) { SR_MIN_QUOTE = v; _srRender(); };
  window._srSetMin = function (v) { SR_MIN_USD = v; _srRender(); };
  window._srSetN = function (v) { SR_MIN_N = v; _srRender(); };
  window._srSetFenster = function (v) { SR_FENSTER_H = v; _srRender(); };
  window._srSetSport = function (v) { SR_SPORT = v; _srRender(); };
  window._srSetSort = function (v) { SR_SORT = v; _srRender(); };

  // ── Karte ─────────────────────────────────────────────────────────────────
  function _srKarte(g) {
    var maxGeld = g.seiten.reduce(function (m, s) { return Math.max(m, s.geld); }, 0) || 1;
    // 11.09.2026 (Lucas: „sollten wir da ja eher auch anzeigen wieviel Geld und wieviel % das
    // sind vom Markt, damit ich das gleich seh"). Das Geld stand schon da, der Anteil nicht.
    //
    // ⚠️ Der Nenner ist NICHT der Markt. Stake liefert kein Marktvolumen — der Feed ist eine
    // Liste einzelner Highroller-Wetten, keine Orderbuch-Tiefe. Was hier steht, ist der Anteil
    // am BEOBACHTETEN Großgeld dieses Spiels, und das ist eine Stichprobe mit Auswahl: nur
    // Wetten über der Schwelle, nur öffentliche Konten. Ein Prozentzeichen, das „Marktanteil"
    // suggeriert, wäre hier schlicht falsch — deshalb heißt die Spalte, was sie misst.
    var gesamt = g.seiten.reduce(function (m, s) { return m + (s.geld || 0); }, 0);
    var seiten = g.seiten.slice(0, 4).map(function (s) {
      var q = s.qMin == null ? '' : (s.qMin === s.qMax ? s.qMin.toFixed(2)
              : s.qMin.toFixed(2) + '–' + s.qMax.toFixed(2));
      var ant = gesamt > 0
        ? '<span class="sr-sa" title="Anteil am beobachteten Großgeld dieses Spiels — NICHT am ' +
          'Marktvolumen. Das liefert der Stake-Feed nicht.">' +
          Math.round(s.geld / gesamt * 100) + ' %</span>'
        : '';
      return '<div class="sr-seite">' +
        '<span class="sr-sn">' + _srEsc(s.name) + '</span>' +
        '<span class="sr-sbar"><i style="width:' + Math.round(s.geld / maxGeld * 100) + '%"></i></span>' +
        '<span class="sr-sg">' + _srUsd(s.geld) + '</span>' + ant +
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
      (nf && nf.zufallPct != null
        ? '<span class="sr-bad sr-norm" title="' + _srEsc(nf.grund || '') + '. Gemessen gegen ' +
          'den Schwanz dieser Liga selbst, nicht gegen ihren Median — der wächst mit der ' +
          'Stichprobengröße.">' + Math.round(nf.zufallPct * 100) + '% selten</span>'
        : nf && nf.ueberErwartung == null ? '<span class="sr-bad sr-norm-schwach" title="' + _srEsc(nf.grund || '') +
          '. Schwächeres Kriterium: für ein Seltenheitsurteil hat diese Liga zu wenige Wetten ' +
          '(unter 40), deshalb steht hier nur der Median-Faktor.">×' +
          Number(nf.faktor || 0).toFixed(1) + ' Median <span class="sr-mut">(dünn)</span></span>'
        : '') +
      (_srUmkaempft(g) ? '<span class="sr-bad sr-konf" title="Mindestens 30 % des Geldes ' +
        'liegen auf einer zweiten Seite — der Markt ist sich uneinig, das ist kein ' +
        'einheitlicher Fluss">⚔️ umkämpft</span>' : '');

    return '<div class="sr-card' + (nf && nf.zufallPct != null ? ' sr-card-norm' : '') + '">' +
      '<div class="sr-ch"><span class="sr-ev">' + _srEsc(g.event || '—') + '</span>' + badges +
      '<span class="sr-lg">' + _srAnpfiffText(g) + ' · ' + _srEsc(g.liga || g.sport || '') + '</span></div>' +
      '<div class="sr-meta">' +
        '<span class="sr-geld">Geld <b>' + _srUsd(g.geldUsd) + '</b>' +
          (g.nGeldBekannt !== g.n ? ' <span style="color:#6b7480">aus ' + g.nGeldBekannt + '/' + g.n + '</span>' : '') + '</span>' +
        (g.gewinnUsd ? '<span title="Was diese Einsätze gewinnen würden. Der Einsatz allein ' +
          'bevorzugt Favoritenschieber: $264k auf 1,20 riskiert eine Viertelmillion für $53k.">' +
          'zu gewinnen <b>' + _srUsd(g.gewinnUsd) + '</b></span>' : '') +
        '<span><b>' + g.nEinzel + '</b> Einzelwetten</span>' +
        (dichte ? '<span>' + dichte + '</span>' : '') +
        '<span>zuletzt ' + _srZeit(g.letzte) + '</span>' + unbek + komb +
      '</div>' +
      '<div class="sr-seiten">' + seiten + '</div>' +
      (alleZeigen ? _srZeitachse(g) : '') +
      '<div class="sr-bets">' + bets +
        (g.n > 6 ? '<button class="sr-mehr sr-btn" onclick="_srAufklappen(\'' +
          _srEsc(g.key).replace(/'/g, '') + '\')">' +
          (alleZeigen ? '▴ weniger' : '▾ + ' + (g.n - 6) + ' weitere') + '</button>' : '') +
      '</div></div>';
  }

  // ══ GRAFIK ═════════════════════════════════════════════════════════════════
  // 03.09.2026 (Lucas: „das Terminal würd ich gern noch so pimpen, dass es grafisch
  // vielleicht mit Graphen optisch einfach cooler aussieht").
  //
  // Vier Bilder, jedes mit genau einer Aufgabe — und jedes mit EINER Serie, also einer
  // Farbe. Keine bunte Palette: wo nur eine Größe dargestellt wird, ist ein zweiter Farbton
  // kein Informationsgewinn, sondern verbrannter Kanal.
  //
  //   Tagesverlauf   Geld je Stunde          → Säulen, eine Farbe (Verlauf über Zeit)
  //   Norm-Streifen  ein Einsatz vs. Liga    → Meter mit Median-Marke (ein Wert an einer Grenze)
  //   Liga-Balken    Median je Liga          → liegende Balken, eine Farbe (Größenvergleich)
  //   Zeitachse      wann kam das Geld       → Punkte auf einer Zeitachse, Größe = Einsatz
  //
  // Maße nach denselben Regeln wie im Rest: Balken höchstens 24px dick mit 4px runder
  // Datenkante und eckigem Fuß, 2px Lücke in Flächenfarbe zwischen benachbarten Balken
  // (die Lücke trennt, nicht ein Rahmen), Gitterlinien haarfein und zurückgenommen,
  // Punkte mindestens 8px mit 2px Ring in Flächenfarbe. Beschriftet wird sparsam —
  // eine Zahl an jedem Punkt liest niemand.

  var SR_FLAECHE = '#131922';
  var SR_HUE = '#67cc91';        // die eine Farbe für Geld
  var SR_MARK = '#e3b341';       // Referenzlinie (Norm), kein Serienton
  var SR_GITTER = '#242c38';

  function _srSvgTip(t) { return '<title>' + _srEsc(t) + '</title>'; }

  /** Geld je Stunde über das gewählte Fenster. Verlauf über Zeit, eine Serie. */
  function _srVerlauf(wetten, fensterH) {
    if (!wetten.length) return '';
    var jetzt = Date.now(), stunden = Math.max(6, Math.min(48, fensterH));
    var eimer = new Array(stunden).fill(0), zahl = new Array(stunden).fill(0);
    wetten.forEach(function (w) {
      var t = _srMs(w.ts); if (t == null || w.einsatzUsd == null) return;
      var alt = Math.floor((jetzt - t) / 3600000);
      var i = stunden - 1 - alt;
      if (i >= 0 && i < stunden) { eimer[i] += w.einsatzUsd; zahl[i]++; }
    });
    var max = Math.max.apply(null, eimer) || 1;
    var B = 260, H = 54, luecke = 2;
    var breite = Math.max(3, Math.min(24, (B - (stunden - 1) * luecke) / stunden));
    var schritt = breite + luecke;
    var innenB = stunden * schritt - luecke;

    var saeulen = eimer.map(function (v, i) {
      var h = v > 0 ? Math.max(2, v / max * H) : 0;
      var x = i * schritt, y = H - h;
      var std = new Date(jetzt - (stunden - 1 - i) * 3600000).getHours();
      var tip = ('0' + std).slice(-2) + ':00 · ' + _srUsd(v) + ' aus ' + zahl[i] +
                (zahl[i] === 1 ? ' Wette' : ' Wetten');
      if (!h) return '<rect x="' + x + '" y="' + (H - 2) + '" width="' + breite + '" height="2" ' +
        'rx="1" fill="' + SR_GITTER + '">' + _srSvgTip(tip) + '</rect>';
      // 4px runde Datenkante oben, eckiger Fuß auf der Grundlinie: zwei Formen statt
      // eines rx auf dem ganzen Rechteck, sonst rundet auch der Fuß.
      var r = Math.min(4, breite / 2, h);
      return '<g>' + _srSvgTip(tip) +
        '<path d="M' + x + ' ' + H + ' L' + x + ' ' + (y + r) +
        ' Q' + x + ' ' + y + ' ' + (x + r) + ' ' + y +
        ' L' + (x + breite - r) + ' ' + y +
        ' Q' + (x + breite) + ' ' + y + ' ' + (x + breite) + ' ' + (y + r) +
        ' L' + (x + breite) + ' ' + H + ' Z" fill="' + SR_HUE + '"/></g>';
    }).join('');

    var summe = eimer.reduce(function (a, b) { return a + b; }, 0);
    return '<div class="sr-chart">' +
      '<div class="sr-chart-h"><span class="sr-chart-t">Geld je Stunde</span>' +
      '<span class="sr-chart-s">' + _srUsd(summe) + ' in ' + stunden + ' h · Spitze ' +
      _srUsd(max) + '</span></div>' +
      '<svg viewBox="0 0 ' + innenB + ' ' + (H + 1) + '" width="100%" height="' + (H + 1) + '" ' +
      'preserveAspectRatio="none" role="img" aria-label="Eingesetztes Geld je Stunde">' +
      '<line x1="0" y1="' + (H + 0.5) + '" x2="' + innenB + '" y2="' + (H + 0.5) + '" ' +
      'stroke="' + SR_GITTER + '" stroke-width="1"/>' + saeulen + '</svg></div>';
  }

  /** Ein einzelner Einsatz gegen die Verteilung seiner Liga. Ein Wert an einer Grenze
      → Meter, nicht Diagramm. Die Skala ist logarithmisch, weil Einsätze über
      Größenordnungen streuen; das steht auch dran. */
  function _srNormMeter(usd, norm) {
    if (!norm || norm.basis !== 'gelernt' || !norm.median) return '';
    var ober = Math.max(usd, norm.max || norm.p90 || norm.median * 4, norm.median * 4);
    var lg = function (v) { return Math.log10(Math.max(1, v)); };
    var pos = function (v) { return Math.max(0, Math.min(1, (lg(v) - lg(norm.median / 4)) /
                                                            (lg(ober) - lg(norm.median / 4)))); };
    var B = 100, H = 8;
    var xm = pos(norm.median) * B, xp = pos(norm.p90 || norm.median) * B, xw = pos(usd) * B;
    return '<svg class="sr-meter" viewBox="0 0 ' + B + ' ' + (H + 6) + '" width="112" height="' +
      (H + 6) + '" role="img" aria-label="Einsatz gegen die Norm dieser Liga">' +
      _srSvgTip('Median ' + _srUsd(norm.median) + ' · 90%-Punkt ' + _srUsd(norm.p90) +
                ' · diese Wette ' + _srUsd(usd) + ' (n' + norm.n + ', log-Skala)') +
      '<rect x="0" y="' + (H / 2) + '" width="' + B + '" height="3" rx="1.5" fill="' + SR_GITTER + '"/>' +
      '<rect x="0" y="' + (H / 2) + '" width="' + xw + '" height="3" rx="1.5" fill="' + SR_HUE + '"/>' +
      '<line x1="' + xm + '" y1="1" x2="' + xm + '" y2="' + (H + 2) + '" stroke="' + SR_MARK +
      '" stroke-width="1.5"/>' +
      '<line x1="' + xp + '" y1="3" x2="' + xp + '" y2="' + H + '" stroke="#6b7480" stroke-width="1"/>' +
      '<circle cx="' + xw + '" cy="' + (H / 2 + 1.5) + '" r="4" fill="' + SR_HUE +
      '" stroke="' + SR_FLAECHE + '" stroke-width="2"/></svg>';
  }

  /** Median je Liga als liegende Balken. Größenvergleich, eine Serie, eine Farbe —
      ein Farbverlauf nach Größe würde die Balkenlänge doppelt kodieren. */
  function _srLigaBalken(ligen) {
    var rows = Object.keys(ligen)
      .filter(function (k) { return ligen[k].basis === 'gelernt'; })
      .sort(function (a, b) { return ligen[b].median - ligen[a].median; })
      .slice(0, 14);
    if (!rows.length) return '';
    var max = Math.max.apply(null, rows.map(function (k) { return ligen[k].max || ligen[k].p90; })) || 1;
    var zeilen = rows.map(function (k) {
      var d = ligen[k];
      var wMed = Math.max(2, d.median / max * 100), wP90 = Math.max(wMed, (d.p90 || d.median) / max * 100);
      return '<div class="sr-lb">' +
        '<span class="sr-lb-n" title="' + _srEsc(k) + '">' + _srEsc(k) + '</span>' +
        '<span class="sr-lb-t" title="Median ' + _srUsd(d.median) + ' · 90%-Punkt ' +
          _srUsd(d.p90) + ' · größter ' + _srUsd(d.max) + ' (n' + d.n + ')">' +
          '<i class="sr-lb-p90" style="width:' + wP90 + '%"></i>' +
          '<i class="sr-lb-med" style="width:' + wMed + '%"></i></span>' +
        '<span class="sr-lb-v">' + _srUsd(d.median) + '</span>' +
        '<span class="sr-lb-n2">n' + d.n + '</span></div>';
    }).join('');
    return '<div class="sr-chart"><div class="sr-chart-h">' +
      '<span class="sr-chart-t">Median-Einsatz je Liga</span>' +
      '<span class="sr-chart-s">heller Balken = 90 %-Punkt</span></div>' +
      '<div class="sr-lbs">' + zeilen + '</div></div>';
  }

  /** Wann kam das Geld — Punkte auf einer Zeitachse, Fläche ~ Einsatz.
      Ein Schwall zehn Minuten vor Anpfiff sieht anders aus als ein Rinnsal. */
  function _srZeitachse(g) {
    var mit = g.wetten.filter(function (w) { return _srMs(w.ts) != null; });
    if (mit.length < 2) return '';
    var ts = mit.map(function (w) { return _srMs(w.ts); });
    var von = Math.min.apply(null, ts), bis = Math.max.apply(null, ts);
    if (bis - von < 60000) return '';
    var ko = _srMs(g.anpfiff);
    var B = 100, H = 26;
    var x = function (t) { return (t - von) / (bis - von) * B; };
    var maxE = Math.max.apply(null, mit.map(function (w) { return w.einsatzUsd || 0; })) || 1;
    var punkte = mit.map(function (w) {
      var e = w.einsatzUsd || 0;
      // Fläche proportional zum Einsatz, Radius also über die Wurzel — sonst wächst die
      // wahrgenommene Größe quadratisch und ein doppelter Einsatz sieht vierfach aus.
      var r = 2.5 + 3.5 * Math.sqrt(e / maxE);
      return '<circle cx="' + x(_srMs(w.ts)).toFixed(2) + '" cy="' + (H / 2) + '" r="' + r.toFixed(2) +
        '" fill="' + (w.kombi ? '#6b7480' : SR_HUE) + '" fill-opacity="' + (w.kombi ? .5 : .85) +
        '" stroke="' + SR_FLAECHE + '" stroke-width="1.5">' +
        _srSvgTip(_srZeit(w.ts) + ' · ' + (w.einsatzUsd == null ? '? ' + (w.waehrung || '') : _srUsd(e)) +
                  ' · ' + (w.auswahl || w.markt || '')) + '</circle>';
    }).join('');
    var kolinie = (ko != null && ko >= von && ko <= bis)
      ? '<line x1="' + x(ko).toFixed(2) + '" y1="2" x2="' + x(ko).toFixed(2) + '" y2="' + (H - 2) +
        '" stroke="' + SR_MARK + '" stroke-width="1" stroke-opacity=".8">' +
        _srSvgTip('Anpfiff') + '</line>' : '';
    return '<div class="sr-tl"><svg viewBox="0 0 ' + B + ' ' + H + '" width="100%" height="' + H +
      '" preserveAspectRatio="none" role="img" aria-label="Zeitpunkte der Wetten">' +
      '<line x1="0" y1="' + (H / 2) + '" x2="' + B + '" y2="' + (H / 2) + '" stroke="' + SR_GITTER +
      '" stroke-width="1"/>' + kolinie + punkte + '</svg>' +
      '<div class="sr-tl-l"><span>' + _srZeit(new Date(von).toISOString()) + '</span>' +
      '<span>' + (ko != null && ko >= von && ko <= bis ? 'Anpfiff markiert · ' : '') +
      'Punktfläche = Einsatz</span>' +
      '<span>' + _srZeit(new Date(bis).toISOString()) + '</span></div></div>';
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
    // 07.09.2026: hiess „🚩 Auffällig". Der Name allein war schon die Behauptung — er sagt
    // „hier passiert etwas Beachtenswertes", und gemessen ist das Gegenteil belegt. Der
    // Schlüssel bleibt 'auffaellig' (Artefakt, Tests, Verlinkungen), nur die Aufschrift sagt
    // jetzt, was die Ansicht wirklich zeigt: Einsätze über der Norm ihrer Liga.
    var tabs = [['spiele', '⚽ Spiele'], ['auffaellig', '📏 Über der Norm'],
                ['klasse', '🏟️ Spielklasse'], ['bilanz', '🧾 Bilanz'], ['norm', '📐 Norm']];
    return '<div class="sr-nav">' + tabs.map(function (t) {
      return '<button class="sr-nb' + (SR_TAB === t[0] ? ' on' : '') +
        '" onclick="_srTab(\'' + t[0] + '\')">' + t[1] + '</button>';
    }).join('') + '</div>';
  }
  window._srTab = function (t) { SR_TAB = t; _srRender(); };

  /** Trefferquote — als Beschreibung. Sie entscheidet NICHTS mehr.
      04.09.2026: `belegt` hing hier an „Trefferquote über 50 %". Bei Wetten mit
      unterschiedlichen Quoten sagt das nichts: 63,9 % Treffer bei Ø-Quote 1,72 ergaben in
      den ersten 950 Beinen einen ROI von −6,8 %. Wer bei 1,20 setzt, braucht 83 %. */
  function _srBasis(s) {
    if (!s || !s.n) return '<span class="sr-mut">keine Basis</span>';
    return '<b>' + _srPct(s.quote) + '</b> <span class="sr-mut">· n' + s.n +
      (s.oQuote ? ' · Ø ' + Number(s.oQuote).toFixed(2) : '') + '</span>';
  }

  /** Das eigentliche Urteil: Rendite je Bein mit einseitiger 95 %-Untergrenze.
      Nur wenn die über null liegt, trägt die Schublade. */
  function _srRendite(s) {
    if (!s || !s.beinN) return '<span class="sr-mut">keine Basis</span>';
    var roi = s.beinRoi == null ? '—' : (s.beinRoi > 0 ? '+' : '') + _srPct(s.beinRoi);
    if (s.beinRoiUg == null) {
      return '<b>' + roi + '</b> <span class="sr-mut" title="Unter n=' +
        (SR_AUS ? SR_AUS.urteilAb : 30) + ' geben wir keine Untergrenze aus — ein ' +
        'Punktschätzer ist kein Beleg">· kein Urteil</span>';
    }
    var ug = (s.beinRoiUg > 0 ? '+' : '') + _srPct(s.beinRoiUg);
    return '<b class="' + (s.belegt ? 'sr-w' : '') + '">' + roi + '</b> ' +
      '<span class="sr-ug' + (s.belegt ? ' sr-ok' : '') + '" title="Einseitige 95 %-Untergrenze ' +
      'der Rendite bei flachem Einsatz je Bein. Nur über null trägt die Schublade.">UG ' + ug +
      '</span>' + (s.belegt ? ' <span class="sr-w">trägt</span>' : '');
  }

  function _srUnreif(was) {
    var b = (SR_AUS && SR_AUS.bilanz) || {};
    return '<div class="sr-empty"><b>' + was + ' braucht abgerechnete Wetten.</b><br>' +
      'Bisher: ' + (b.gewertet || 0) + ' gewertete Beine, ' + (b.offen || 0) + ' noch offen.<br>' +
      '<span class="sr-mut">Stake rechnet selbst ab — jede Wette wird ein paar Stunden nach ' +
      'Anpfiff nachgefragt. Ein Urteil gibt es ab n=' + (SR_AUS ? SR_AUS.urteilAb : 30) + '.</span></div>';
  }

  // ── Über der Norm ───────────────────────────────────────────────────────────
  // 07.09.2026 (Lucas, Backlog: „Die 'Auffällig'-Ansicht ehrlich beschriften" + „Achse
  // umstellen auf live × Einsatzgröße statt auffällig ja/nein").
  //
  // Die Ansicht hiess „Auffällig" und behauptete damit etwas, das gemessen nicht stimmt.
  // Zwei Änderungen, und nur die zweite ist Kosmetik:
  //   1. Das Urteil über die eigene Prämisse steht OBEN und kommt aus dem Artefakt
  //      (stake_analyse.norm_phase). Es wird nicht hier getippt — ein getippter Satz
  //      veraltet mit den nächsten hundert Abrechnungen, und niemand merkt es.
  //   2. Die Achse ist jetzt live × Einsatzgröße. „Auffällig ja/nein" trennt gemessen
  //      nichts; die Trennung liegt zwischen den Phasen und im äussersten Band.
  var _SR_NP_ZEILEN = {
    'vor': ['vor Anpfiff', 'Nur hier wäre ein Schlusskurs-Vergleich überhaupt möglich.'],
    'live': ['live', 'Der grösste Teil des Feeds.'],
    'alle': ['beide zusammen', 'Gepoolt — nur hier wird das äusserste Band gross genug für eine Grenze.']
  };

  function _srNpBand(x) {
    return (_SR_NP_ZEILEN[x.phase] ? _SR_NP_ZEILEN[x.phase][0] : x.phase) + ' · ' + x.band;
  }

  /** Der Urteilssatz — aus den Zahlen gebaut, nicht getippt. */
  function _srNpUrteil(np) {
    var u = (np && np.urteil) || {};
    var gegen = (u.gegen || []).filter(function (x) {
      return (np.auffBaender || []).indexOf(x.band) >= 0;
    });
    var folgen = (u.folgen || []).filter(function (x) {
      return (np.auffBaender || []).indexOf(x.band) >= 0;
    });
    if (u.praemisse === 'gestuetzt' && folgen.length) {
      return '<div class="sr-note"><b>Gemessen trägt das hier — vorerst.</b> Über der Norm ' +
        'liegt die Rendite-<b>Unter</b>grenze über null bei: ' +
        folgen.map(function (x) {
          return _srEsc(_srNpBand(x)) + ' (' + _srPct(x.flachUg, 0) + ', n' + x.n + ')';
        }).join(', ') + '. Die Schwellen wurden im Rückblick gesetzt — das Urteil fällt ' +
        'vorwärts, in den vorregistrierten Schubladen.</div>';
    }
    if (u.praemisse === 'widerlegt' && gegen.length) {
      return '<div class="sr-note"><b>Diese Ansicht ist keine Empfehlung — gemessen zeigt sie ' +
        'ins Gegenteil.</b> Wo die Einsätze am weitesten über der Norm liegen, liegt die ' +
        'Rendite-<b>Ober</b>grenze unter null: ' +
        gegen.map(function (x) {
          return _srEsc(_srNpBand(x)) + ' (' + _srPct(x.flach, 1) + ', Obergrenze ' +
            _srPct(x.flachOg, 1) + ', n' + x.n + ')';
        }).join('; ') + '. Ein grosser Einsatz ist danach eher ein Grund, <b>nicht</b> ' +
        'mitzugehen. Die Liste unten bleibt trotzdem stehen: sie zeigt, was gesetzt wurde.</div>';
    }
    return '<div class="sr-note"><b>Über der Norm ist bisher weder belegt noch widerlegt.</b> ' +
      'In keiner Zelle über 3× Norm kreuzt eine 95 %-Grenze die Null — die Ansicht ist damit ' +
      'Anzeige, keine Empfehlung. Was sie <i>nicht</i> mehr behauptet: dass ein grosser Einsatz ' +
      'für sich genommen etwas wert wäre.</div>';
  }

  function _srNpTabelle(np) {
    var k = np.kreuz || {};
    var spalten = np.spalten || [];
    var zeilen = (np.zeilen || Object.keys(k)).filter(function (z) { return k[z]; }).map(function (z) {
      var m = _SR_NP_ZEILEN[z] || [z, ''];
      var n = spalten.reduce(function (a, c) { return a + ((k[z][c] && k[z][c].n) || 0); }, 0);
      return '<tr' + (z === 'alle' ? ' class="sr-pool"' : '') + '><td><b>' + _srEsc(m[0]) + '</b>' +
        (m[1] ? '<div class="sr-mut sr-sm">' + _srEsc(m[1]) + '</div>' : '') +
        '<div class="sr-mut sr-sm">' + n + ' abgerechnete Wetten</div></td>' +
        spalten.map(function (c) { return _srKlZelle(k[z][c]); }).join('') + '</tr>';
    }).join('');
    return '<div class="sr-tw"><table class="sr-t"><thead><tr><th>Phase</th>' +
      spalten.map(function (c) { return '<th class="sr-r">' + _srEsc(c) + '</th>'; }).join('') +
      '</tr></thead><tbody>' + zeilen + '</tbody></table></div>';
  }

  function _srAuffaellig() {
    var np = SR_AUS && SR_AUS.normPhase;
    // Ein fehlender Block heisst „der Erzeuger war noch nicht dran", nicht „nichts gefunden".
    // Der Unterschied ist der ganze Punkt (drei Wege, auf denen ein fertiges Feature leer
    // aussieht — 07.09.2026).
    var kopf = np
      ? _srNpUrteil(np) +
        '<h3 class="sr-h3">Rendite nach Phase und Einsatzgrösse</h3>' +
        '<div class="sr-mut sr-sm">Einsatz als Vielfaches des üblichen Einsatzes derselben ' +
          'Liga (ohne eigene Norm: derselben Spielklasse). Nur abgerechnete Einzelwetten. ' +
          'Die fette Zahl ist geldgewichtet, die Spanne sind die einseitigen 95 %-Grenzen ' +
          'bei flachem Einsatz — <b>nur die entscheiden</b>.</div>' +
        _srNpTabelle(np) +
        '<div class="sr-mut sr-sm">' + _srEsc(np.warum || '') + '</div>'
      : '<div class="sr-empty"><b>Der Block „normPhase" fehlt in stake_auswertung.json.</b>' +
        '<br><span class="sr-mut">Er entsteht auf dem Runner (stake_analyse.py). Bis dahin ' +
        'steht hier kein Urteil — statt eines, das niemand nachgerechnet hat.</span></div>';

    var rows = (SR_AUS && SR_AUS.auffaellige) || [];
    var liste = rows.length
      ? '<div class="sr-tw"><table class="sr-t"><thead><tr>' +
        '<th>Zeit</th><th>Liga</th><th>Spiel</th><th>Auswahl</th>' +
        '<th class="sr-r">Einsatz</th><th>gegen die Liga</th><th class="sr-r">Quote</th>' +
        '<th>Warum hier gelistet</th><th>Ausgang</th>' +
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
            '<td>' + _srNormMeter(r.einsatzUsd,
              (SR_AUS && SR_AUS.ligaNorm && SR_AUS.ligaNorm[r.liga]) || null) + '</td>' +
            '<td class="sr-r">' + (r.quote != null ? Number(r.quote).toFixed(2) : '—') + '</td>' +
            '<td class="sr-mut">' + _srEsc(r.grund) + '</td>' +
            '<td>' + aus + '</td></tr>';
        }).join('') + '</tbody></table></div>'
      : '<div class="sr-empty">Noch nichts über der Norm.<br><span class="sr-mut">' +
        'Eine Liga-Norm entsteht ab 15 Wetten in derselben Liga; ein <b>Urteil</b> darüber, ' +
        'ob ein Einsatz wirklich überraschend ist, erst ab 40 — darunter lässt sich der ' +
        'Schwanz der Verteilung nicht schätzen, und geraten wird hier nicht.</span></div>';

    return kopf +
      '<h3 class="sr-h3">Die einzelnen Einsätze über der Norm</h3>' +
      '<div class="sr-mut sr-sm">Anzeige, keine Empfehlung — welche Zeile etwas wert ist, ' +
        'entscheidet die Tabelle darüber, nicht die Grösse des Einsatzes.</div>' +
      liste +
      '<div class="sr-note"><b>Drei verschiedene Gründe, absichtlich nicht vermischt</b> — ' +
      'sie stehen in dieser Reihenfolge, stärkstes Urteil zuerst:<br>' +
      '<b>% selten</b> ist das einzige echte Urteil <i>über die Seltenheit</i>: wie oft eine ' +
      'völlig unauffällige Liga dieser Größe so etwas überhaupt hervorbringt — gegen eine ' +
      'simulierte Nullverteilung, nicht gegen ein Vielfaches. Ein festes Vielfaches ginge ' +
      'nicht: schon in einer Liga, in der nichts passiert, liegt das Maximum in rund einem ' +
      'Viertel der Fälle bei „2× über Erwartung". Gerechnet über mehrere ' +
      'Schwanz&shy;ausschnitte, gewertet wird der konservativste. Selten heisst <b>nicht</b> ' +
      'spielenswert — das steht oben.<br>' +
      '<b>× Median (dünn)</b> ist schwächer: die Liga hat eine Norm, aber unter 40 Wetten und ' +
      'damit keinen schätzbaren Schwanz. Dieser Faktor wächst mit der Sammeldauer — er ' +
      'beschreibt, er urteilt nicht.<br>' +
      '<b>kleine Liga</b> ist am schwächsten: keine Norm, nur wenige Wetten und ein Einsatz ' +
      'über dem globalen 90 %-Punkt.</div>';
  }

  // ── Bilanz ──────────────────────────────────────────────────────────────────
  var _SR_SCHUBLADEN = [
    ['vor_anpfiff', 'vor Anpfiff', 'Nur hier ist CLV gegen den Schlusskurs überhaupt möglich.'],
    ['live', 'live', '83 % des Feeds — aber ohne Schlusskurs, also nur über die Abrechnung messbar.'],
    // 07.09.2026 (Übersicht-Check): „Min" hiess hier Spielminute, gemessen ist die WANDUHR
    // seit Anpfiff — die Halbzeitpause zählt mit. Die Schwellen bleiben, wie sie
    // vorregistriert wurden; nur die Aufschrift sagt jetzt, was gemessen wird.
    ['live_frueh', 'live, ≤ 30 min nach Anpfiff', 'Wenn Live etwas taugt, dann früh.'],
    ['live_spaet', 'live, > 60 min nach Anpfiff', 'Späte Einsätze auf den Führenden sind kein Signal — Gegenprobe.'],
    ['einsatz_ab_10k', 'ab $10k', 'Trägt Größe allein etwas? Die Vorlage behauptet ja, ohne Beleg.'],
    ['einsatz_1k_10k', '$1k – $10k', 'Die Vergleichsgruppe dazu.'],
    ['ueber_liga_norm', 'über Liga-Norm', 'Die eigentliche These: auffällig ist relativ.'],
    ['randliga_hoher_einsatz', 'Ebene 2/3, ab 3× Norm',
     'Lucas 07.09.: „ne 50k Wette auf Arsenal sagt 0". Vorwärts gemessen.'],
    ['topliga_hoher_einsatz', 'oberste Liga, ab 6× Norm',
     'Die Gegenprobe — im Rückblick läuft diese Reihe nach unten.'],
  ];

  // ── Spielklasse ───────────────────────────────────────────────────────────
  // 07.09.2026 (Lucas: „ne 50k Wette auf Arsenal sagt 0 / Eine 50k Wette auf ein 2-3. Liga
  // Team / Ist zumindest jemand der mehr dran glaubt mmn").
  //
  // Diese Ansicht rechnet NICHTS. Die Spielklasse, die Referenzeinsätze, die Schwellen und
  // die Kreuztabelle kommen fertig aus stake_analyse.py (`randliga`), das sie wiederum aus
  // stake_liga_stufe.py holt. Würde das Frontend die Schwelle noch einmal setzen, gäbe es
  // sie zweimal — dieselbe Klasse, die in diesem Repo schon zweimal auseinandergelaufen ist.
  var _SR_KL_EBENE = {
    '1': ['oberste Spielklasse', 'Premier League, La Liga, Serie A …'],
    '2': ['zweite Spielklasse', 'Championship, 2. Bundesliga, Serie B …'],
    '3': ['dritte Klasse und tiefer', 'League One, Serie C, NPL, Amateur …'],
    'kontinental': ['kontinental', 'Champions League, Libertadores, Leagues Cup'],
    'pokal': ['Pokal', 'ein Pokalspiel ist kein Ligaspiel'],
    'frauen': ['Frauen', ''],
    'jugend': ['Jugend', ''],
    'srl': ['Simulated Reality', 'simulierte Spiele — keine echte Partie'],
    'reserve': ['Reserve', 'zweite Mannschaften — keine Spielklasse']
  };
  var _SR_KL_SPALTEN = ['<1.5x', '1.5-3x', '3-6x', '>6x'];

  // 07.09.2026 (Backlog): zweite Achse für die Kandidatenliste. „Wie ungewöhnlich" und „wie
  // viel Geld" sind zwei Fragen; die Liste beantwortete nur die erste. Die AUSWAHL macht der
  // Erzeuger (Vereinigung beider Bestenlisten) — hier wird nur umsortiert. Sonst zeigte die
  // Betrags-Sortierung die grössten Beträge einer nach Faktor abgeschnittenen Liste.
  var SR_KL_SORT = 'faktor';
  window._srKlSort = function (v) { SR_KL_SORT = v; _srRender(); };

  function _srKlZelle(z) {
    if (!z || !z.n) return '<td class="sr-r sr-mut">—</td>';
    var roi = z.roi == null ? '—' : (z.roi > 0 ? '+' : '') + _srPct(z.roi);
    // Zwei Grenzen, zwei Aussagen — und je nach Richtung entscheidet die andere.
    // Folgen belegt die UNTERgrenze über null. Dagegenhalten belegt die OBERgrenze unter
    // null. Stünde hier nur die Untergrenze, bliebe die Ebene-1-Reihe auf ewig „kein
    // Urteil", obwohl sie genau die Aussage trägt, um die es in dieser Ansicht geht.
    var spanne = (z.flachUg == null || z.flachOg == null)
      ? '<span class="sr-mut" title="Unter n=30 geben wir keine Grenze aus — ein ' +
        'Punktschätzer ist kein Beleg.">kein Urteil</span>'
      : '<span class="sr-ug' + (z.belegt || z.belegtGegen ? ' sr-ok' : '') + '" ' +
        'title="Einseitige 95 %-Grenzen der Rendite bei flachem Einsatz. Über null: dem ' +
        'Fluss folgen trägt. Unter null: dagegenhalten trägt.">' +
        (z.flachUg > 0 ? '+' : '') + _srPct(z.flachUg, 0) + ' … ' +
        (z.flachOg > 0 ? '+' : '') + _srPct(z.flachOg, 0) + '</span>';
    var marke = z.belegt ? ' <span class="sr-w">folgen</span>'
              : z.belegtGegen ? ' <span class="sr-w">dagegen</span>' : '';
    return '<td class="sr-r"><b class="' + (z.belegt || z.belegtGegen ? 'sr-w' : '') + '">' + roi + '</b>' +
      '<div class="sr-mut sr-sm">n' + z.n + ' · ' + z.spiele + ' Spiele</div>' +
      '<div class="sr-sm">' + spanne + marke + '</div></td>';
  }

  function _srKlasse() {
    var r = SR_AUS && SR_AUS.randliga;
    if (!r) {
      return '<div class="sr-empty"><b>Der Block „randliga" fehlt in stake_auswertung.json.</b>' +
        '<br><span class="sr-mut">Er entsteht auf dem Runner (stake_analyse.py → ' +
        'stake_liga_stufe.py). Bis dahin steht hier nichts, statt einer leeren Tabelle.</span></div>';
    }

    // Kreuztabelle: Ebene × Einsatzgröße. Der Punkt der Ansicht ist, dass die Zeilen
    // GEGENLÄUFIG sind — deshalb stehen sie untereinander und nicht in getrennten Kacheln.
    // Die Zeilen kommen aus dem ARTEFAKT, nicht aus der Beschriftungsliste unten. Andersherum
    // wäre eine Ebene, die der Produzent kennt und der Renderer noch nicht, still aus der
    // Tabelle gefallen — dieselbe Klasse wie „fehlende Information rendert als harmloser
    // Default", nur ist der harmlose Default hier die Leerstelle. Die Liste liefert nur den
    // Klartext; fehlt er, steht der rohe Schlüssel da und fällt auf.
    var k = r.kreuz || {};
    var reihenfolge = Object.keys(_SR_KL_EBENE);
    var zeilen = Object.keys(k).sort(function (a, b) {
      var ia = reihenfolge.indexOf(a), ib = reihenfolge.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    }).map(function (e) {
      var m = _SR_KL_EBENE[e] || [e, 'noch ohne Beschriftung im Radar'];
      return '<tr><td><b>' + _srEsc(m[0]) + '</b>' +
        (m[1] ? '<div class="sr-mut sr-sm">' + _srEsc(m[1]) + '</div>' : '') +
        '<div class="sr-mut sr-sm">' + (r.jeEbene[e] || 0) + ' Wetten gesammelt</div></td>' +
        _SR_KL_SPALTEN.map(function (c) { return _srKlZelle(k[e][c]); }).join('') + '</tr>';
    }).join('');

    var tabelle = '<div class="sr-tw"><table class="sr-t"><thead><tr><th>Spielklasse</th>' +
      _SR_KL_SPALTEN.map(function (c) { return '<th class="sr-r">' + c + '</th>'; }).join('') +
      '</tr></thead><tbody>' + zeilen + '</tbody></table></div>';

    // Die Liste, um die Lucas gebeten hat: große Einsätze dort, wo groß selten ist.
    var kand = (r.kandidaten || []).slice().sort(function (a, b) {
      return SR_KL_SORT === 'betrag'
        ? (b.einsatzUsd || 0) - (a.einsatzUsd || 0)
        : (b.faktor || 0) - (a.faktor || 0);
    });
    var umschalter = '<div class="sr-nav sr-nav2">' +
      [['faktor', 'nach Faktor'], ['betrag', 'nach Betrag']].map(function (t) {
        return '<button class="sr-nb' + (SR_KL_SORT === t[0] ? ' on' : '') +
          '" onclick="_srKlSort(\'' + t[0] + '\')">' + t[1] + '</button>';
      }).join('') + '</div>';
    var liste = kand.length
      ? '<div class="sr-tw"><table class="sr-t"><thead><tr><th>Faktor</th><th class="sr-r">Einsatz</th>' +
        '<th>Liga</th><th>Spiel</th><th>Wette</th><th class="sr-r">Quote</th>' +
        '<th>drin über</th><th>Ausgang</th></tr></thead><tbody>' +
        kand.map(function (x) {
          var aus = x.ausgang === 'won' ? '<span class="sr-w">Treffer</span>'
                  : x.ausgang === 'lost' ? '<span class="sr-mut">daneben</span>'
                  : '<span class="sr-mut">offen</span>';
          return '<tr><td><b>' + Number(x.faktor).toFixed(1).replace('.', ',') + '×</b>' +
            '<div class="sr-mut sr-sm" title="' +
              (x.refBasis === 'liga'
                ? 'gegen den gelernten Median DIESER Liga'
                : 'diese Liga hat noch keine eigene Norm — gemessen gegen den Median ihrer Spielklasse') +
              '">' + (x.refBasis === 'liga' ? 'Liga-Norm' : 'Ebene-Norm') + '</div></td>' +
            '<td class="sr-r sr-geldz">' + _srUsd(x.einsatzUsd) + '</td>' +
            '<td>' + _srEsc(x.liga || '') +
              '<div class="sr-mut sr-sm">Ebene ' + _srEsc(x.ebene) + '</div></td>' +
            '<td>' + _srEsc(x.event || '') + '</td>' +
            '<td>' + _srEsc(x.markt || '') +
              '<div class="sr-mut sr-sm">' + _srEsc(x.auswahl || '') + '</div></td>' +
            '<td class="sr-r">' + (x.quote == null ? '—' : Number(x.quote).toFixed(2).replace('.', ',')) + '</td>' +
            // Warum diese Zeile überhaupt in der Auswahl ist. Eine Zeile, die nur über den
            // Betrag hereinkam, ist beim Faktor-Blick sonst ein Rätsel — und umgekehrt.
            '<td class="sr-mut sr-sm">' + _srEsc((x.warumDrin || ['faktor']).join(' + ')) + '</td>' +
            '<td>' + aus + '</td></tr>';
        }).join('') + '</tbody></table></div>'
      : '<div class="sr-empty">Gerade kein Einsatz ab ' + r.abFaktor +
        '× der Norm auf Ebene 2 oder tiefer.</div>';

    var ohne = r.nOhneEbene
      ? '<div class="sr-basis"><span class="sr-mut" title="' + _srEsc((r.ohneEbene || []).join(', ')) +
        '">' + r.nOhneEbene + ' Fußball-Ligen stehen nicht in der Tabelle — sie tauchen ' +
        'in keiner Zeile oben auf, statt still als Ebene 1 zu zählen.</span></div>'
      : '';

    return '<div class="sr-basis"><span>Die Spielklasse steht in <b>keinem Feld</b> des Feeds ' +
        'und lässt sich aus dem Volumen nicht ableiten — danach gelten Süper Lig, MLS und die ' +
        'Championship als „kleine Liga". Sie kommt aus einer <b>Tabelle</b> ' +
        '(stake_liga_stufe.py), nicht aus einer Messung.</span></div>' +
      ohne +
      '<h3 class="sr-h3">Rendite nach Spielklasse und Einsatzgröße</h3>' +
      '<div class="sr-mut sr-sm">Einsatz als Vielfaches des üblichen Einsatzes derselben Liga ' +
        '(hat die Liga noch keine eigene Norm: derselben Spielklasse). Nur abgerechnete ' +
        'Einzelwetten. Die fette Zahl ist geldgewichtet, die UG ist die einseitige ' +
        '95 %-Untergrenze bei flachem Einsatz — <b>nur die entscheidet</b>.</div>' +
      tabelle +
      '<div class="sr-mut sr-sm">' + _srEsc(r.warum || '') + '</div>' +
      '<h3 class="sr-h3">Große Einsätze auf Ebene 2 und tiefer</h3>' +
      '<div class="sr-mut sr-sm">Ab ' + r.abFaktor + '× der Norm. Ohne Ausgangsfilter: die ' +
        'Liste zeigt, was gesetzt wurde, nicht was aufging.' +
        (r.kandidatenAuswahl ? ' ' + _srEsc(r.kandidatenAuswahl) : '') + '</div>' +
      umschalter +
      liste;
  }

  /** Wie viele Schubladen tragen überhaupt ein Urteil — gezählt aus dem ARTEFAKT.
   *
   * 11.09.2026 (Lucas: „sagen uns die anderen Auswertungen in den anderen Tabs etwas aus?").
   * Die Tabelle stand da und war ehrlich, aber sie beantwortete die Frage nicht: man musste 18
   * Zeilen einzeln lesen, um zu sehen, dass zwei davon etwas belegen. Das ist genau die Sorte
   * Ansicht, die viel zeigt und nichts sagt.
   *
   * Gezählt statt geschrieben: eine feste Zahl im Text wäre in einer Woche falsch, und die
   * Zeile, die das Urteil zusammenfasst, darf nicht als erste veralten.
   */
  function _srBelegLage() {
    var s = (SR_AUS && SR_AUS.schubladen) || {};
    var namen = {}, i;
    for (i = 0; i < _SR_SCHUBLADEN.length; i++) namen[_SR_SCHUBLADEN[i][0]] = _SR_SCHUBLADEN[i][1];
    var alle = Object.keys(s).filter(function (k) {
      return s[k] && typeof s[k] === 'object' && k !== 'gesamt';
    });
    var traegt = alle.filter(function (k) { return s[k].belegt; });
    var gegen = alle.filter(function (k) { return s[k].belegtGegen; });
    var nenn = function (k) { return _srEsc(namen[k] || k); };
    if (!alle.length) return '';
    var kern = traegt.length
      ? '<b>' + traegt.length + ' von ' + alle.length + '</b> Schubladen ' +
        (traegt.length === 1 ? 'trägt' : 'tragen') + ' ein Urteil: ' +
        traegt.map(function (k) {
          return '<b>' + nenn(k) + '</b> (' + (s[k].beinRoi > 0 ? '+' : '') +
            _srPct(s[k].beinRoi) + ', Untergrenze ' + (s[k].beinRoiUg > 0 ? '+' : '') +
            _srPct(s[k].beinRoiUg) + ' bei n=' + s[k].beinN + ')';
        }).join(' · ')
      : '<b>Keine</b> der ' + alle.length + ' Schubladen trägt bisher ein Urteil.';
    var rest = gegen.length
      ? ' Dagegenhalten belegt: ' + gegen.map(nenn).join(', ') + '.'
      : '';
    return '<div class="sr-note sr-note-kern">' + kern + '.' + rest +
      ' Alle übrigen liegen mit ihrer Untergrenze unter null — sie sind <b>nicht widerlegt, ' +
      'sondern unbelegt</b>, und ein Punktschätzer daraus ist keine Aussage.</div>';
  }

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
        '<td>' + _srRendite(d) + '</td>' +
        '<td class="sr-r sr-geldz">' + (d.einsatzUsd ? _srUsd(d.einsatzUsd) : '—') +
          (d.gewinnUsd ? '<div class="sr-mut sr-sm">zu gewinnen ' + _srUsd(d.gewinnUsd) + '</div>' : '') +
        '</td>' +
        // Die Rendite rechnet NUR auf abgerechneten Einzelwetten — deshalb steht deren Zahl
        // daneben und nicht die aller Einzelwetten. Zwei Grundgesamtheiten, zwei Namen.
        '<td class="sr-r">' + (d.roi == null ? '—' : _srPct(d.roi)) +
          '<div class="sr-mut sr-sm">' + (d.abgerechnetN || 0) + ' abgerechnet</div>' +
        '</td></tr>';
    }).join('');

    var ligen = Object.keys(SR_AUS.jeLiga || {}).map(function (k) {
      var d = SR_AUS.jeLiga[k];
      return '<tr><td>' + _srEsc(k) + '</td><td class="sr-r">' + d.n + '</td><td>' + _srBasis(d) + '</td></tr>';
    }).join('');

    return _srBelegLage() +
      '<div class="sr-kpi">' +
        _srKpi(b.gewertet, 'Beine gewertet') +
        _srKpi(b.treffer + ' / ' + b.daneben, 'Treffer / daneben') +
        _srKpi(b.quote == null ? '—' : _srPct(b.quote), 'rohe Trefferquote') +
        _srKpi((SR_AUS.schubladen && SR_AUS.schubladen.gesamt &&
                SR_AUS.schubladen.gesamt.beinRoi != null)
               ? (SR_AUS.schubladen.gesamt.beinRoi > 0 ? '+' : '') +
                 _srPct(SR_AUS.schubladen.gesamt.beinRoi) : '—', 'Rendite je Bein') +
        _srKpi(b.offen, 'noch offen') +
        _srKpi(b.unaufloesbar, 'unauflösbar') +
      '</div>' +
      '<div class="sr-tw"><table class="sr-t"><thead><tr><th>Schublade</th>' +
      '<th class="sr-r">Wetten</th><th class="sr-r">Beine</th><th>Trefferquote</th>' +
      '<th>Rendite je Bein</th><th class="sr-r">Einsatz</th>' +
      '<th class="sr-r">ROI Geld</th></tr></thead><tbody>' +
      zeilen + '</tbody></table></div>' +
      (ligen ? '<h3 class="sr-h3">Je Liga</h3><div class="sr-tw"><table class="sr-t"><thead><tr>' +
        '<th>Liga</th><th class="sr-r">Beine</th><th>Trefferquote</th></tr></thead><tbody>' +
        ligen + '</tbody></table></div>' : '') +
      _srGesperrteSchubladen() +
      '<div class="sr-note"><b>Eine Trefferquote über 50 % ist hier kein gutes Zeichen.</b> ' +
      'Gemessen an den ersten 950 abgerechneten Beinen: 63,9 % Treffer bei Ø-Quote 1,72 — und ' +
      'trotzdem <b>−6,8 % Rendite</b>. Wer bei Quote 1,20 setzt, braucht 83 % zum Nullpunkt. ' +
      'Das Urteil („trägt") hängt deshalb an der <b>Rendite-Untergrenze</b>, nicht an der ' +
      'Trefferquote — dieselbe Rechnung wie im Freigabe-Register.</div>' +
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
      _srLigaBalken(n) +
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
    var sperr = _srGesperrt(), nGesperrt = 0, nQuote = 0;
    var roh = (d.wetten || []).filter(function (w) {
      if (w.einsatzUsd == null || w.einsatzUsd < SR_MIN_USD) return false;
      var t = _srMs(w.ts); if (t == null || t < ab) return false;
      // Ein stiller Filter ist genau die Sorte Fehler, die wir hier ausräumen — deshalb
      // wird gezählt, was weggelassen wird, und die Zahl steht unten drunter.
      var _k = _srKat(w);
      if (!_k || sperr.indexOf(_k) >= 0) { nGesperrt++; return false; }   // unbekannt = keine Erlaubnis
      // Bei einer Kombi zaehlt die Gesamtquote, bei einer Einzelwette die des Beins —
      // beides steht als `quote` drin. Ohne Quote wird nicht gefiltert: unbekannt ist
      // nicht dasselbe wie niedrig.
      if (SR_MIN_QUOTE > 1 && w.quote != null && w.quote < SR_MIN_QUOTE) { nQuote++; return false; }
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
      if (SR_SORT === 'gewinn') return b.gewinnUsd - a.gewinnUsd;
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
      (nQuote ? '<span class="sr-mut" title="Gemessen an 445 Wetten: unter Quote 1,35 liegen ' +
        '32 % der Wetten und 35 % des Einsatzes — aber nur 3 % des möglichen Gewinns. Ob sie ' +
        'deshalb schlechter informiert sind, ist nicht gemessen; der Regler blendet aus, er urteilt nicht.">' +
        nQuote + ' unter Quote ' + SR_MIN_QUOTE.toFixed(2).replace('.', ',') + '</span>' : '') +
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

    var spiele = _srCtrl() + _srVerlauf(roh, SR_FENSTER_H) + treffer + koerper;
    var inhalt = SR_TAB === 'spiele' ? spiele
               : SR_TAB === 'auffaellig' ? _srAuffaellig()
               : SR_TAB === 'klasse' ? _srKlasse()
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

  // 07.09.2026 (Lucas: „na alle tabs klappen nur der nicht"). Der Spielklasse-Reiter stand
  // leer, waehrend Bilanz, Norm und Auffaellig daneben liefen — weil die drei nur Felder
  // brauchen, die es im ALTEN Artefakt schon gab. Diese Datei holte relativ, also aus dem
  // Pages-Schnappschuss, und der haengt am stuendlichen Deploy. Ein neues Feld ist dort bis
  // zu eine Stunde lang nicht da, und das sieht aus wie „der Produzent laeuft nicht".
  //
  // Dritter Fall derselben Klasse: am 29.08. traf es poly-wallets.js und status-checks.js,
  // danach die Cards. `raw-first-fetch.test.mjs` gab es da schon — aber als HANDGEPFLEGTE
  // Liste, in der diese Datei fehlte. Eine Liste, die man vergessen kann, ist kein Guard;
  // der Test prueft jetzt jede Datei, die das Dashboard laedt.
  var _SR_RAW = 'https://raw.githubusercontent.com/blummabet/Betting-Dashboard/main';

  function _srJson(u) {
    var b = '?t=' + Date.now();
    return fetch(_SR_RAW + '/' + u + b, { cache: 'no-store' })
      .then(function (r) { if (r.ok) return r.json(); throw 0; })
      .catch(function () {
        return fetch(u + b, { cache: 'no-store' })
          .then(function (r) { return r.ok ? r.json() : null; })
          .catch(function () { return null; });
      });
  }

  // ── Einstieg ──────────────────────────────────────────────────────────────
  window.initStakeRadar = function () {
    _srStyle();
    if (SR.geladen) { _srRender(); return; }
    SR.geladen = true;
    _srRender();
    _srJson('stake_highroller.json')
      .then(function (j) { SR.daten = j || { status: 'fehler', notiz: 'stake_highroller.json nicht lesbar' }; _srRender(); })
      .catch(function () { SR.daten = { status: 'fehler', notiz: 'stake_highroller.json nicht erreichbar' }; _srRender(); });
    _srJson('stake_auswertung.json')
      .then(function (j) { SR_AUS = j; SR_AUS_STATUS = j ? 'da' : 'fehlt'; _SR_AUFF_IDX = null; _srRender(); })
      .catch(function () { SR_AUS = null; SR_AUS_STATUS = 'fehlt'; _SR_AUFF_IDX = null; _srRender(); });
  };

  // Für Tests
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { _srGruppen: _srGruppen, _srDichte: _srDichte, _srUsd: _srUsd,
                   _srBasis: _srBasis, _srRendite: _srRendite, _srPct: _srPct, _srKat: _srKat,
                   _srUmkaempft: _srUmkaempft, _srBisAnpfiff: _srBisAnpfiff,
                   _srVerlauf: _srVerlauf, _srNormMeter: _srNormMeter,
                   _srNpUrteil: _srNpUrteil, _srNpTabelle: _srNpTabelle,
                   _srLigaBalken: _srLigaBalken, _srZeitachse: _srZeitachse,
                   _srAnpfiffText: _srAnpfiffText, _srDauerText: _srDauerText,
                   _srKarte: _srKarte, _srBelegLage: _srBelegLage,
                   _srAus: function (a) { SR_AUS = a; },
                   _srNurSpielbar: function () { return SR_NUR_SPIELBAR; } };
  }
})();
