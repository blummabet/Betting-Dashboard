/* messungen.js — das Buch der laufenden Messungen (15.09.2026, Lucas: „wo sehen wir den Outcome
 * dieser Messungen? Damit wir in 2 Wochen wissen, dass wir das heute gemacht haben?").
 *
 * Diese Datei ZEICHNET nur. Gerechnet und beurteilt wird in `messungen.py` — der Zustand einer
 * Messung ist eine Entscheidung, und Entscheidungen gehören nicht zweimal ins Repo.
 *
 * ── Gestaltung, und warum ──────────────────────────────────────────────────────────────
 * · Jeder Zustand trägt sein WORT, nicht nur seine Farbe. „Überfällig" in Rot ist für
 *   Rot-Grün-Blinde sonst dasselbe wie „bereit" in Grün.
 * · Der Fortschrittsbalken erscheint NUR, wenn es etwas zu zählen gibt. Eine Messung ohne
 *   eingebauten Zähler bekommt keinen leeren Balken — ein Balken behauptet Fortschritt, und
 *   „0 von 60" sähe aus wie „fängt gerade an" statt wie „zählt gar nicht".
 * · Was Handlung braucht, steht oben und ist am lautesten. Die Reihenfolge kommt aus der
 *   Python-Seite; hier wird sie nicht noch einmal erfunden.
 * · Fehlt die Datei ganz, steht das da — als Satz, nicht als leere Fläche. Ein Buch, das noch
 *   nie geschrieben wurde, ist kein Buch ohne Einträge.
 */
var _msData = null, _msLoading = false, _msGeladen = false;

var MS = {
  good: '#3fb950', bad: '#f85149', warn: '#e3b341', accent: '#00d4a1', lila: '#a78bfa',
  ink: '#e6edf3', ink2: '#8b949e', ink3: '#6e7681', flat: '#484f58',
  line: 'rgba(255,255,255,.08)',
};

// Zustand → (Farbe, Label). Die Labels sind die Wörter, die auch im Log stehen.
var _MS_ZUSTAND = {
  'ueberfaellig':      [MS.bad,    'ÜBERFÄLLIG'],
  'faellig':           [MS.warn,   'ENTSCHEIDUNG FÄLLIG'],
  'quelle unlesbar':   [MS.bad,    'QUELLE UNLESBAR'],
  'wartet auf Einbau': [MS.lila,   'ZÄHLT NOCH NICHT'],
  'bereit':            [MS.accent, 'MENGE ERREICHT'],
  'sammelt':           [MS.ink3,   'SAMMELT'],
  'entschieden':       [MS.good,   'ENTSCHIEDEN'],
};

function _msEsc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _msBadge(zustand) {
  var z = _MS_ZUSTAND[zustand] || [MS.ink3, String(zustand || 'UNBEKANNT').toUpperCase()];
  return '<span style="display:inline-block;padding:3px 9px;border-radius:999px;font-size:10px;'
       + 'font-weight:800;letter-spacing:.6px;color:' + z[0] + ';border:1px solid ' + z[0]
       + '44;background:' + z[0] + '14;">' + _msEsc(z[1]) + '</span>';
}

function _msBalken(m) {
  // Kein Balken ohne Zählbares — siehe Kopfkommentar.
  if (m.fortschritt === null || m.fortschritt === undefined) return '';
  var pct = Math.round(m.fortschritt * 100);
  var farbe = m.fortschritt >= 1 ? MS.accent : (m.zustand === 'ueberfaellig' ? MS.bad : MS.ink3);
  return '<div style="margin-top:10px;">'
       + '<div style="height:6px;border-radius:3px;background:rgba(255,255,255,.06);overflow:hidden;">'
       + '<div style="height:100%;width:' + pct + '%;background:' + farbe + ';"></div></div>'
       + '<div style="margin-top:4px;font-size:10px;color:' + MS.ink3 + ';">'
       + _msEsc(m.standN) + ' von ' + _msEsc(m.mindestN) + ' Beobachtungen (' + pct + ' %)</div>'
       + '</div>';
}

function _msTermin(m) {
  var t = m.tageBisFaellig;
  if (t === null || t === undefined) return 'kein Termin';
  if (t > 1)  return 'fällig ' + _msEsc(m.faellig) + ' · in ' + t + ' Tagen';
  if (t === 1) return 'fällig ' + _msEsc(m.faellig) + ' · morgen';
  if (t === 0) return 'fällig heute';
  return 'fällig war ' + _msEsc(m.faellig) + ' · seit ' + (-t) + ' Tagen offen';
}

function _msKarte(m) {
  var z = _MS_ZUSTAND[m.zustand] || [MS.ink3, ''];
  var laut = (m.zustand === 'ueberfaellig' || m.zustand === 'faellig');
  return '<div style="border:1px solid ' + (laut ? z[0] + '55' : MS.line) + ';border-left:3px solid '
    + z[0] + ';border-radius:10px;padding:14px 16px;margin-bottom:12px;'
    + 'background:' + (laut ? z[0] + '0d' : 'rgba(255,255,255,.02)') + ';">'
    + '<div style="display:flex;gap:10px;align-items:flex-start;flex-wrap:wrap;">'
    +   '<div style="flex:1;min-width:200px;font-size:14px;font-weight:700;color:' + MS.ink + ';">'
    +     _msEsc(m.titel || m.id) + '</div>'
    +   _msBadge(m.zustand)
    + '</div>'
    + '<div style="margin-top:6px;font-size:12px;color:' + MS.ink2 + ';line-height:1.5;">'
    +   _msEsc(m.frage) + '</div>'
    + (m.warum ? '<div style="margin-top:8px;font-size:11px;color:' + MS.ink3
        + ';line-height:1.5;border-left:2px solid ' + MS.line + ';padding-left:10px;">'
        + _msEsc(m.warum) + '</div>' : '')
    + _msBalken(m)
    + '<div style="margin-top:10px;font-size:11px;color:' + z[0] + ';font-weight:600;">'
    +   _msEsc(m.stand) + '</div>'
    + '<div style="margin-top:6px;font-size:10px;color:' + MS.ink3 + ';">'
    +   _msEsc(_msTermin(m)) + ' · gestartet ' + _msEsc(m.gestartet)
    +   (m.quelle ? ' · Quelle: ' + _msEsc(m.quelle) : '')
    +   (m.wecker ? ' · Wecker: ' + _msEsc(m.wecker) : '')
    + '</div>'
    + '</div>';
}

function _msRender() {
  var el = (typeof document !== 'undefined') && document.getElementById('messungenPanel');
  if (!el) return;
  var kopf = '<div class="section-label" style="margin-bottom:4px;">🔬 Laufende Messungen</div>'
    + '<div style="font-size:12px;color:' + MS.ink2 + ';margin-bottom:16px;line-height:1.5;">'
    + 'Offene Fragen mit Termin und Datenstand. Eine Frage, die nur im Gesprächsprotokoll steht, '
    + 'ist keine offene Frage — sie ist eine vergessene.</div>';

  if (!_msData) {
    el.innerHTML = kopf + '<div style="padding:18px;border:1px dashed ' + MS.line
      + ';border-radius:10px;font-size:12px;color:' + MS.ink3 + ';">'
      + (_msLoading ? 'Buch wird geladen …'
                    : 'Das Buch wurde noch nie geschrieben — <code>messungen.json</code> fehlt. '
                      + 'Es entsteht beim nächsten Pipeline-Lauf.')
      + '</div>';
    return;
  }
  var liste = (_msData.messungen || []);
  if (!liste.length) {
    el.innerHTML = kopf + '<div style="padding:18px;font-size:12px;color:' + MS.ink3 + ';">'
      + 'Keine Einträge im Register.</div>';
    return;
  }
  var nH = _msData.nHandlung || 0;
  var bilanz = '<div style="margin-bottom:14px;padding:10px 14px;border-radius:8px;font-size:12px;'
    + 'background:' + (nH ? MS.warn + '14' : 'rgba(0,212,161,.06)') + ';border-left:3px solid '
    + (nH ? MS.warn : MS.accent) + ';color:' + (nH ? MS.warn : MS.accent) + ';">'
    + (nH ? '⚠️ ' + nH + ' von ' + liste.length + ' brauchen Aufmerksamkeit'
          : '✓ ' + (_msData.nOffen || 0) + ' offen, alle sammeln planmäßig')
    + '</div>';
  el.innerHTML = kopf + bilanz + liste.map(_msKarte).join('');
}

function _msLoad(force) {
  if (_msLoading || (_msGeladen && !force)) { _msRender(); return; }
  _msLoading = true;
  _msRender();
  // Reihenfolge (raw zuerst, Snapshot als Rueckfall) steht EINMAL im Repo — in raw-json.js.
  // Wer sie hier abschreibt, schreibt sie irgendwann falsch ab; genau daran ist am 29.08. und
  // am 07.09. dreimal dieselbe Bug-Klasse entstanden.
  window.rawJson('messungen.json')
    .then(function (d) { _msData = d; _msLoading = false; _msGeladen = true; _msRender(); });
}

function initMessungen() { _msLoad(); }

if (typeof window !== 'undefined') {
  window.initMessungen = initMessungen;
  window._msLoad = _msLoad;
  window._msRenderTest = _msRender;
  window._msSetDataTest = function (d) { _msData = d; _msGeladen = true; _msLoading = false; };
  window._msKarteTest = _msKarte;
  window._msBalkenTest = _msBalken;
  window._msTerminTest = _msTermin;
}
