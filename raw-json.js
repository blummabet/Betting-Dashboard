/**
 * raw-json.js — 07.09.2026
 *
 * Eine Stelle, an der steht, WOHER das Dashboard seine JSONs holt.
 *
 * Vorgeschichte (29.08. und 07.09.): dieselbe Bug-Klasse dreimal. Eine Datei holt ihre JSONs
 * relativ, also aus dem Pages-Snapshot, der stuendlich neu gebaut wird — die Tabs daneben holen
 * raw-zuerst und sind commit-frisch. Ergebnis war einmal „vor 8,6 Std" neben live, einmal zwei
 * Staende desselben Datensatzes je nach Tab, einmal ein neuer Reiter, der leer stand, weil sein
 * NEUES Feld im Snapshot noch nicht existierte.
 *
 * Der Guard dagegen war eine handgepflegte Dateiliste — und die vergisst genau die Datei, die
 * neu ist. Deshalb gibt es die Reihenfolge jetzt als Funktion statt als Konvention:
 * `rawJson('x.json')` holt raw-zuerst und faellt auf den Snapshot zurueck. Wer sie benutzt, kann
 * die Reihenfolge nicht mehr falsch abschreiben; wer sie nicht benutzt, faellt im Test auf.
 *
 * Rueckfall ist Absicht: ohne ihn waere eine raw-Stoerung ein Totalausfall statt einer Verzoegerung.
 */
(function () {
  'use strict';

  var RAW_BASE = 'https://raw.githubusercontent.com/blummabet/Betting-Dashboard/main';
  var PAGES_HOST = 'blummabet.github.io';

  function _bust(u) {
    return u + (u.indexOf('?') >= 0 ? '&' : '?') + 't=' + Date.now();
  }

  // Relativer Pfad, wie ihn der Aufrufer schreibt ('./x.json' und 'x.json' sind dasselbe).
  function _rel(u) {
    return String(u).replace(/^\.?\//, '');
  }

  /**
   * rawJson(pfad) -> Promise<JSON|null>
   * raw.githubusercontent ZUERST (commit-frisch), dann der relative Pfad (Pages-Snapshot /
   * Offline-Cache). Nie ein Throw: unerreichbar = null, damit der Aufrufer „keine Daten" von
   * „kaputt" unterscheiden kann, ohne jeden Aufruf einzeln abzufangen.
   */
  function rawJson(u) {
    var rel = _rel(u);
    return fetch(_bust(RAW_BASE + '/' + rel), { cache: 'no-store' })
      .then(function (r) { if (r.ok) return r.json(); throw 0; })
      .catch(function () {
        return fetch(_bust(rel), { cache: 'no-store' })
          .then(function (r) { return r.ok ? r.json() : null; })
          .catch(function () { return null; });
      });
  }

  /**
   * rawFirstUrls(liste) -> Liste mit der raw-URL vor jedem Snapshot-Eintrag.
   * Fuer die Stellen, die bewusst mehrere Quellen der Reihe nach probieren (results-v2.js mit
   * seinem lokalen Dev-Server): localhost bleibt vorn, raw kommt vor den relativen und vor den
   * Pages-URLs — beides ist derselbe stuendliche Snapshot.
   */
  function rawFirstUrls(liste) {
    var out = [];
    for (var i = 0; i < liste.length; i++) {
      var u = liste[i];
      var extern = /^https?:\/\//.test(u);
      var snapshot = !extern || u.indexOf(PAGES_HOST) >= 0;
      if (snapshot) {
        var name = extern ? u.slice(u.lastIndexOf('/') + 1) : _rel(u);
        var raw = RAW_BASE + '/' + name;
        if (out.indexOf(raw) < 0) out.push(raw);
      }
      out.push(u);
    }
    return out;
  }

  // Im Browser global, unter node (Tests) via module.exports — beides ohne den jeweils
  // anderen vorauszusetzen.
  if (typeof window !== 'undefined') {
    window.rawJson = rawJson;
    window.rawFirstUrls = rawFirstUrls;
    window.RAW_BASE = RAW_BASE;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { rawJson: rawJson, rawFirstUrls: rawFirstUrls, RAW_BASE: RAW_BASE };
  }
})();
