/* stats.js — die Stats-Seite (09.09.2026, Lucas: „schaffen wir eine eigene Stats-Seite? … alles
 * rein was geht — Cards, Betfair, Poly, Push-Channels. Alles auf Monatsbasis und Wochenbasis
 * auch. Schön modern dargestellt, weil brauch das um es zu posten.")
 *
 * Diese Datei ZEICHNET nur. Gerechnet wird in `stats_perioden.py` — inklusive der Urteile
 * (`vollstaendig`, `hitUg`, `roiUg`). Ein Frontend, das seine eigenen Schwellen mitbringt, hat
 * sie zweimal; in diesem Repo ist das die häufigste Fehlerklasse.
 *
 * ── Gestaltung, und warum ──────────────────────────────────────────────────────────────
 * · EINE Serie je Sparkline. Damit braucht es keine kategoriale Palette und keine Legende —
 *   die Überschrift benennt die Serie. (Der Palette-Validator scheitert an genau der Stelle,
 *   an der man fünf gleich helle Marken-Farben nebeneinanderlegt; die Frage stellt sich hier
 *   gar nicht erst.)
 * · Farbe trägt nur STATUS (Rendite über/unter null), und Status-Farbe steht in diesem Repo
 *   nie allein: jede Zahl trägt ihr Vorzeichen, jedes Urteil sein Wort. Grün↔Rot hat für
 *   Rot-Grün-Blinde ΔE 2,2 — ohne Vorzeichen wäre die Tafel für sie unlesbar.
 * · Unvollständige Perioden sind schraffiert und beschriftet. Ein halber August neben einem
 *   ganzen September sieht sonst aus wie ein schwacher Monat.
 * · Post-Modus blendet Beträge und Quoten aus (Lucas postet Screenshots). Er ändert NUR die
 *   Anzeige — die Zahlen bleiben dieselben, sonst gäbe es zwei Wahrheiten.
 */
var _stData = null, _stLoading = false;
var _stMode = 'woche';       // woche | monat
var _stPost = false;         // Post-Modus: Beträge/Quoten aus

var ST = {
  good: '#3fb950', bad: '#f85149', warn: '#e3b341',
  ink: '#e6edf3', ink2: '#8b949e', ink3: '#6e7681',
  line: 'rgba(255,255,255,.08)', flat: '#484f58',
};

function _stEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
  });
}
function _stPct(v, stellen) {
  if (v == null) return '—';
  var d = stellen == null ? 1 : stellen;
  return (v >= 0 ? '+' : '') + (+v).toFixed(d) + '%';
}
function _stNum(v) { return v == null ? '—' : (+v).toLocaleString('de-DE'); }
function _stCol(v) { return v == null ? ST.ink3 : (v > 0 ? ST.good : v < 0 ? ST.bad : ST.flat); }

// Kalenderwoche lesbar: „KW 37" statt „2026-W37"; Monate deutsch.
var _ST_MON = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
function _stPeriode(r) {
  if (r.art === 'gesamt') return 'Gesamt';
  if (r.art === 'woche') return 'KW ' + String(r.periode).slice(6);
  var m = +String(r.periode).slice(5, 7);
  return (_ST_MON[m - 1] || r.periode) + ' ' + String(r.periode).slice(0, 4);
}

/* ── Sparkline: eine Serie, Nulllinie, unvollständige Perioden schraffiert ───────────────
 * Balken statt Linie: die Perioden sind diskret und teils unvollständig — eine Linie würde
 * zwischen ihnen interpolieren und damit Werte behaupten, die nie gemessen wurden. */
function _stSpark(reihen, feld) {
  var rs = reihen.filter(function (r) { return r.art === _stMode && r[feld] != null; });
  if (rs.length < 2) return '';
  var w = 100 / rs.length, max = Math.max.apply(null, rs.map(function (r) { return Math.abs(r[feld]); }));
  if (!max) return '';
  var mid = 26;   // Nulllinie in einer 52px hohen Fläche
  var balken = rs.map(function (r, i) {
    var h = Math.max(1.5, Math.abs(r[feld]) / max * 22);
    var y = r[feld] >= 0 ? (mid - h) : mid;
    var col = _stCol(r[feld]);
    var x = i * w + w * 0.18, bw = w * 0.64;
    // Unvollständig = schraffiert. Die Zahl stimmt, die Periode ist nur kürzer.
    var fill = r.vollstaendig ? col : 'url(#stHatch)';
    var stroke = r.vollstaendig ? '' : ' stroke="' + col + '" stroke-width="0.6"';
    return '<rect x="' + x.toFixed(2) + '" y="' + y.toFixed(2) + '" width="' + bw.toFixed(2)
      + '" height="' + h.toFixed(2) + '" rx="1" fill="' + fill + '"' + stroke
      + '><title>' + _stEsc(_stPeriode(r)) + ': ' + _stPct(r[feld])
      + (r.vollstaendig ? '' : ' · ' + _stEsc(r.grund || 'unvollständig')) + '</title></rect>';
  }).join('');
  return '<svg class="st-spark" viewBox="0 0 100 52" preserveAspectRatio="none" aria-hidden="true">'
    + '<defs><pattern id="stHatch" width="3" height="3" patternTransform="rotate(45)" '
    + 'patternUnits="userSpaceOnUse"><rect width="1.2" height="3" fill="' + ST.ink3 + '"/></pattern></defs>'
    + '<line x1="0" y1="' + mid + '" x2="100" y2="' + mid + '" stroke="' + ST.line + '" stroke-width="0.7"/>'
    + balken + '</svg>';
}

function _stKachel(lbl, wert, col, sub) {
  return '<div class="st-k"><div class="st-k-l">' + lbl + '</div>'
    + '<div class="st-k-v" style="color:' + (col || ST.ink) + '">' + wert + '</div>'
    + (sub ? '<div class="st-k-s">' + sub + '</div>' : '') + '</div>';
}

function _stZeile(r) {
  // ⚠️ „—" heißt NICHT ERHOBEN. Ein Kanal ohne Ergebnis (Dedup-Buch statt Ledger) zeigt keine
  // 0 %, sondern nichts — und die Fußzeile sagt warum.
  var unv = r.vollstaendig ? ''
    : ' <span class="st-unv" title="' + _stEsc(r.grund || '') + '">unvollständig</span>';
  return '<tr' + (r.art === 'gesamt' ? ' class="st-ges"' : '') + '>'
    + '<td class="st-p">' + _stEsc(_stPeriode(r)) + unv + '</td>'
    + '<td class="st-n">' + _stNum(r.n) + '</td>'
    + '<td class="st-n">' + (r.hitPct == null ? '—' : r.hitPct.toFixed(1) + '%')
    + (r.hitUg != null ? '<i>UG ' + r.hitUg.toFixed(0) + '%</i>' : '') + '</td>'
    + '<td class="st-n" style="color:' + _stCol(r.roi) + ';font-weight:800">' + _stPct(r.roi)
    + (r.roiUg != null ? '<i>UG ' + _stPct(r.roiUg) + '</i>' : '') + '</td>'
    + (_stPost ? '' : '<td class="st-n" style="color:' + _stCol(r.pl) + '">'
        + (r.pl == null ? '—' : (r.pl > 0 ? '+' : '') + (+r.pl).toFixed(1)) + '</td>')
    + '<td class="st-n">' + (r.clv == null ? '—' : (r.clv > 0 ? '+' : '') + r.clv.toFixed(2) + 'pp') + '</td>'
    + '</tr>';
}

/* ── Der Gegensignal-Filter: das Urteil ueber BEIDE Arme ───────────────────────────────
 * 13.09.2026 (Lucas: „ich will im Public Auswertungen schicken — als eigener Block").
 *
 * Diese Karte steht ueber den zwei Arm-Bloecken und zeigt den UNTERSCHIED, nicht zwei Zahlen
 * nebeneinander. Der Grund ist derselbe wie ueberall hier: zwei sich ueberlappende Baender
 * heissen nicht „kein Unterschied", und zwei getrennte sind kein Test. Gefragt ist die
 * Verteilung der Differenz — und die steht als Band da, mit dem Anteil der Ziehungen, in
 * denen der Filter schlechter waere.
 *
 * Das Urteil kommt aus dem Artefakt, nicht von hier. Das Frontend zeichnet. */
function _stFilterKarte(v) {
  if (!v) return '';
  var F = { 'der Filter trägt': ST.good, 'noch nicht belegt': ST.warn, 'sammelt': ST.ink3 };
  var farbe = F[v.urteil] || ST.ink3;
  var arm = function (t, k, ton) {
    return '<div class="st-fv-arm"><div class="st-fv-l" style="color:' + ton + '">' + _stEsc(t) + '</div>'
      + '<div class="st-fv-n">' + _stNum(k.n) + ' <i>abgerechnet</i></div>'
      + '<div class="st-fv-z">' + (k.hitPct == null ? '—' : k.hitPct.toFixed(1) + '%') + ' <i>Treffer'
      + (k.hitUg != null ? ' · UG ' + k.hitUg.toFixed(1) + '%' : '') + '</i></div>'
      + '<div class="st-fv-z" style="color:' + _stCol(k.roi) + '">' + _stPct(k.roi) + ' <i>Rendite'
      + (k.roiUg != null ? ' · UG ' + _stPct(k.roiUg) : '') + '</i></div></div>';
  };
  var d = v.roiDiff || {}, h = v.hitDiff || {};
  return '<section class="st-block">'
    + '<div class="st-b-h"><span class="st-b-e">⚖️</span>'
    + '<span class="st-b-t">Trägt der Filter?</span>'
    + '<span class="st-b-a">' + _stEsc(String((v.abdeckung || {}).von || '').split('-').reverse().join('.'))
    + ' – ' + _stEsc(String((v.abdeckung || {}).bis || '').split('-').reverse().join('.')) + '</span></div>'
    + '<div class="st-b-n">' + _stEsc(v.quelle || '') + '. Der Filter entscheidet vor dem Anpfiff — '
    + 'gemessen wird deshalb der Stand von vorher, nicht der bei Abrechnung.</div>'
    + '<div class="st-fv">' + arm('gesendet', v.gesendet || {}, ST.good)
    + arm('aussortiert', v.aussortiert || {}, ST.ink2) + '</div>'
    + '<div class="st-fv-d">'
    + '<div><b>' + (d.punkt == null ? '—' : (d.punkt > 0 ? '+' : '') + d.punkt.toFixed(1) + ' pp')
    + '</b> Rendite <i>(' + (d.lo == null ? '—' : (d.lo > 0 ? '+' : '') + d.lo.toFixed(1)) + ' … '
    + (d.hi == null ? '—' : (d.hi > 0 ? '+' : '') + d.hi.toFixed(1)) + ')</i></div>'
    + '<div><b>' + (h.punkt == null ? '—' : (h.punkt > 0 ? '+' : '') + h.punkt.toFixed(1) + ' pp')
    + '</b> Trefferquote <i>(' + (h.lo == null ? '—' : (h.lo > 0 ? '+' : '') + h.lo.toFixed(1)) + ' … '
    + (h.hi == null ? '—' : (h.hi > 0 ? '+' : '') + h.hi.toFixed(1)) + ')</i></div>'
    + '</div>'
    + '<div class="st-fv-u" style="border-color:' + farbe + ';color:' + farbe + '">'
    + '<b>' + _stEsc(v.urteil || '—') + '</b> — ' + _stEsc(v.grund || '') + '</div>'
    + '</section>';
}

function _stBlock(b) {
  var ges = b.reihen.filter(function (r) { return r.art === 'gesamt'; })[0] || {};
  var rs = b.reihen.filter(function (r) { return r.art === _stMode; });
  var ohneQuote = ges.mitQuote === 0;
  var kacheln = _stKachel('Plays', _stNum(ges.n), ST.ink)
    + _stKachel('Trefferquote', ges.hitPct == null ? '—' : ges.hitPct.toFixed(1) + '%', ST.ink,
                ges.hitUg != null ? 'Untergrenze ' + ges.hitUg.toFixed(1) + '%' : 'zu wenige für eine Untergrenze')
    + _stKachel('Rendite', _stPct(ges.roi), _stCol(ges.roi),
                ohneQuote ? 'keine Quoten in dieser Quelle'
                  : (ges.roiUg != null ? 'Untergrenze ' + _stPct(ges.roiUg) : 'zu wenige für eine Untergrenze'))
    + (_stPost ? '' : _stKachel('P/L', ges.pl == null ? '—' : (ges.pl > 0 ? '+' : '') + ges.pl.toFixed(1),
                // 10.09.2026 (Lucas: „im Stats-File stehen +11 P/L, im Track-Record $105 —
                // ist das gleich?"). Ja: `kennzahlen()` summiert pnl/stake, also EINHEITEN.
                // „Einheiten Einsatz" war zu leise, um neben einer Dollar-Zahl zu bestehen —
                // die Umrechnung gehoert dazu, sonst liest man zwei Zahlen als zwei Sachen.
                _stCol(ges.pl), 'in Einheiten · bei $10 fixem Einsatz ×10 = $'
                  + (ges.pl == null ? '—' : ((ges.pl > 0 ? '+' : '') + (ges.pl * 10).toFixed(0)))));
  var kopfzeile = '<th>Periode</th><th>Plays</th><th>Treffer</th><th>Rendite</th>'
    + (_stPost ? '' : '<th>P/L <i>Einh.</i></th>') + '<th>CLV</th>';
  return '<section class="st-block">'
    + '<div class="st-b-h"><span class="st-b-e">' + _stEsc(b.emoji || '') + '</span>'
    + '<span class="st-b-t">' + _stEsc(b.label) + '</span>'
    + '<span class="st-b-a">' + _stEsc(String(b.abdeckung.von || '').split('-').reverse().join('.'))
    + ' – ' + _stEsc(String(b.abdeckung.bis || '').split('-').reverse().join('.')) + '</span></div>'
    + (b.hinweis ? '<div class="st-b-n">' + _stEsc(b.hinweis) + '</div>' : '')
    + '<div class="st-ks">' + kacheln + '</div>'
    + _stSpark(b.reihen, 'roi')
    + (rs.length
      ? '<div class="st-tw"><table class="st-tbl"><thead><tr>' + kopfzeile + '</tr></thead><tbody>'
        + rs.map(_stZeile).join('') + _stZeile(ges) + '</tbody></table></div>'
      : '<div class="st-leer">Für diese Auflösung gibt es noch keine abgeschlossene Periode.</div>')
    + (ohneQuote ? '<div class="st-b-n">Dieser Kanal führt kein Ergebnis-Ledger mit Quoten — '
        + 'die Zahl der Pushes stimmt, eine Rendite gibt es hier nicht. „—" heißt nicht erhoben, '
        + 'nicht null.</div>' : '')
    + '</section>';
}

/* ── Die Kopfzeile: drei Zahlen, die mit dem Umschalter mitgehen ────────────────────────
 * 10.09.2026 (Lucas: „kannst du mir ganz oben ne Zusammenfassung von Cards / Betfair aus dem
 * Public-Push / Poly aus den Public-Kandidaten — und das wechselt mit, wenn ich Monat/Woche
 * umstell").
 *
 * Form: eine KPI-Zeile aus drei Stat-Kacheln, kein Diagramm. Drei Kennzahlen nebeneinander sind
 * genau der Fall, für den es Kacheln gibt — ein gruppiertes Balkendiagramm mit drei Balken wäre
 * mehr Tinte für weniger Auskunft.
 *
 * ⚠️ Gezeigt wird die letzte VOLLSTÄNDIGE Periode, nicht die laufende. Die laufende Woche ist am
 * Montag ein Spiel groß; als Schlagzeile gelesen wäre sie eine Behauptung über nichts. Die
 * Blöcke darunter zeigen sie weiterhin, dort steht sie in ihrer Reihe und ist als unvollständig
 * markiert.
 *
 * ⚠️ Und die Zahl bleibt ein Punktschätzer. Eine Wochen-Rendite steht auf n=10..30 — die Kachel
 * nennt deshalb IMMER die Stichprobe daneben und sagt es ausdrücklich, wenn n unter der Schwelle
 * liegt, ab der diese Seite überhaupt Untergrenzen rechnet. Ohne das wäre die Kopfzeile genau
 * die Klasse „ein Punktschätzer entscheidet", gegen die der Rest der Seite gebaut ist. */
var _ST_KOPF = [
  { id: 'cards',          label: 'Cards',   sub: 'Liga + MLS' },
  { id: 'push-bf-public', label: 'Betfair', sub: 'Public-Channel' },
  { id: 'poly-public',    label: 'Poly',    sub: 'Public-Kandidaten' },
];

// Die letzten beiden ABGESCHLOSSENEN Perioden der aktuellen Auflösung, neueste zuerst.
function _stLetzteVoll(b) {
  var rs = (b && b.reihen ? b.reihen : []).filter(function (r) {
    return r.art === _stMode && r.vollstaendig !== false;
  });
  return [rs[rs.length - 1] || null, rs[rs.length - 2] || null];
}

function _stKopfKachel(cfg, blockById, ugMinN) {
  var b = blockById[cfg.id];
  var kopf = '<div class="st-kk-l">' + _stEsc(cfg.label)
    + ' <span class="st-kk-sub">' + _stEsc(cfg.sub) + '</span></div>';
  if (!b) {
    return '<div class="st-kk">' + kopf
      + '<div class="st-kk-v" style="color:' + ST.ink3 + '">—</div>'
      + '<div class="st-kk-s">noch keine Daten für diesen Bereich</div></div>';
  }
  var paar = _stLetzteVoll(b), jetzt = paar[0], vorher = paar[1];
  if (!jetzt) {
    return '<div class="st-kk">' + kopf
      + '<div class="st-kk-v" style="color:' + ST.ink3 + '">—</div>'
      + '<div class="st-kk-s">noch keine abgeschlossene '
      + (_stMode === 'woche' ? 'Woche' : 'Monat') + '</div></div>';
  }
  // Der Delta-Wert ist eine Differenz zweier Prozentzahlen — also Prozentpunkte, nicht Prozent.
  var d = (jetzt.roi != null && vorher && vorher.roi != null) ? (jetzt.roi - vorher.roi) : null;
  var duenn = (jetzt.n || 0) < (ugMinN || 30);
  return '<div class="st-kk">' + kopf
    + '<div class="st-kk-p">' + _stEsc(_stPeriode(jetzt)) + '</div>'
    + '<div class="st-kk-v" style="color:' + _stCol(jetzt.roi) + '">' + _stPct(jetzt.roi) + '</div>'
    + '<div class="st-kk-s">' + _stNum(jetzt.n) + ' Plays'
    + (jetzt.hitPct != null ? ' · ' + jetzt.hitPct.toFixed(0) + '% Treffer' : '')
    + '</div>'
    + (d != null
        ? '<div class="st-kk-d" style="color:' + _stCol(d) + '">'
          + (d >= 0 ? '▲' : '▼') + ' ' + (d >= 0 ? '+' : '') + d.toFixed(1) + ' pp'
          + '<span class="st-kk-vgl"> ggü. ' + _stEsc(_stPeriode(vorher)) + '</span></div>'
        : '<div class="st-kk-d" style="color:' + ST.ink3 + '">keine Vorperiode zum Vergleich</div>')
    + (duenn
        ? '<div class="st-kk-w">⚠️ n &lt; ' + (ugMinN || 30) + ' — Punktschätzer, keine Untergrenze</div>'
        : '');
}

function _stKopfzahlen(d) {
  var byId = {};
  (d.bloecke || []).forEach(function (b) { byId[b.id] = b; });
  return '<div class="st-kks">'
    + _ST_KOPF.map(function (c) { return _stKopfKachel(c, byId, d.ugMinN); }).join('')
    + '</div>'
    + '<div class="st-kk-f">Letzte abgeschlossene '
    + (_stMode === 'woche' ? 'Kalenderwoche' : 'abgeschlossener Monat')
    + ' — die laufende Periode steht in den Tabellen darunter, dort als unvollständig markiert.</div>';
}

function _stRender() {
  var el = document.getElementById('statsPanel');
  if (!el) return;
  if (!_stData) {
    el.innerHTML = '<div class="st-wrap"><div class="st-leer">stats_perioden.json fehlt oder ist '
      + 'nicht lesbar — dann steht hier nichts, statt einer Null.</div></div>';
    return;
  }
  var gruppen = [];
  _stData.bloecke.forEach(function (b) {
    var g = gruppen.filter(function (x) { return x.name === b.gruppe; })[0];
    if (!g) { g = { name: b.gruppe, bloecke: [] }; gruppen.push(g); }
    g.bloecke.push(b);
  });
  var stand = String(_stData.generatedAt || '').slice(0, 16).replace('T', ' ');
  el.innerHTML = '<div class="st-wrap">'
    + '<div class="st-head"><div><h2 class="st-h1">📊 Stats</h2>'
    + '<div class="st-h2">Jede Fläche auf Wochen-, Monats- und Gesamtbasis. Stand ' + _stEsc(stand)
    + ' UTC · Untergrenzen sind einseitige 95-%-Schranken ab n=' + (_stData.ugMinN || 30) + '.</div></div>'
    + '<div class="st-ctrl">'
    + '<div class="st-seg">'
    + '<button class="st-sb' + (_stMode === 'woche' ? ' on' : '') + '" onclick="_stSetMode(\'woche\')">Wochen</button>'
    + '<button class="st-sb' + (_stMode === 'monat' ? ' on' : '') + '" onclick="_stSetMode(\'monat\')">Monate</button>'
    + '</div>'
    + '<button class="st-post' + (_stPost ? ' on' : '') + '" onclick="_stTogglePost()" '
    + 'title="Blendet P/L und Beträge aus — Trefferquote, Rendite in Prozent, Stichprobe und '
    + 'Untergrenzen bleiben. Nur die Anzeige ändert sich, nicht die Zahlen.">'
    + (_stPost ? '🔒 Post-Modus an' : '🔓 Post-Modus aus') + '</button>'
    + '</div></div>'
    + _stKopfzahlen(_stData)
    + gruppen.map(function (g) {
        return '<div class="st-g"><div class="st-g-t">' + _stEsc(g.name) + '</div>'
          + (g.name === 'Push-Filter' ? _stFilterKarte(_stData.filterVergleich) : '')
          + g.bloecke.map(_stBlock).join('') + '</div>';
      }).join('')
    + '<div class="st-foot">Schraffierte Balken und der Vermerk „unvollständig" markieren '
    + 'Perioden, die die Datenquelle nicht ganz abdeckt — der Betfair-Ledger etwa hält nur ein '
    + 'rollierendes Fenster. Eine kürzere Periode ist keine schwächere.</div>'
    + '</div>';
}

function _stSetMode(m) { _stMode = m; _stRender(); }
function _stTogglePost() { _stPost = !_stPost; _stRender(); }

function _stLoad(force) {
  if (_stLoading || (_stData && !force)) { _stRender(); return; }
  _stLoading = true;
  var t = Date.now();
  var base = 'https://raw.githubusercontent.com/blummabet/Betting-Dashboard/main';
  fetch(base + '/stats_perioden.json?t=' + t, { cache: 'no-store' })
    .then(function (r) { if (r.ok) return r.json(); throw 0; })
    .catch(function () {
      return fetch('stats_perioden.json?t=' + t, { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    })
    .then(function (d) { _stData = d; _stLoading = false; _stRender(); });
}

if (typeof window !== 'undefined') {
  window._stLoad = _stLoad;
  window._stSetMode = _stSetMode;
  window._stTogglePost = _stTogglePost;
  window._stRenderTest = _stRender;
  window._stSetDataTest = function (d) { _stData = d; };
  window._stBlockTest = _stBlock;
  window._stSparkTest = _stSpark;
}
