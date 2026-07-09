/*
 * _pick_helpers.js — JavaScript-Pendant zu pick_helpers.py
 * ─────────────────────────────────────────────────────────
 * Single Source of Truth für die JS-Seite:
 *   · DIRECTION_MAP   (29 Märkte → Richtung)
 *   · INCOMPATIBLE    (8 Konflikt-Paare)
 *   · isLegitimatePick(p)        — Tracker-Filter
 *   · arePicksConflicting(p1,p2) — Cross-Market-Check
 *   · findConflictingPicks(hero, others) — UI-Filter
 *   · heroSortKey(p)             — saferAlt > BET > Edge desc
 *
 * Werte spiegeln pick_constants.json (Python = Master).
 * Drift wird per Test (tests/test_js_pick_helpers.py) verboten.
 *
 * Lade-Pattern:
 *   Browser:  <script src="_pick_helpers.js"></script>  → window.CocoBetPicks
 *   Node:     const H = require('./_pick_helpers.js');
 */
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.CocoBetPicks = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ── DIRECTION_MAP ─────────────────────────────────────────────────────────
  // Mirror von pick_constants.json DIRECTION_MAP — IDENTISCH halten.
  // Schema: Market-Label → Richtungs-Bucket
  const DIRECTION_MAP = Object.freeze({
    'Heimsieg':                'homeStrong',
    'Auswärtssieg':            'awayStrong',
    'Unentschieden':           'drawOnly',
    'Doppelte Chance — 1X':    'homeBias',
    'Doppelte Chance — X2':    'awayBias',
    'Doppelte Chance — 12':    'decisive',
    'AH Heim −0.25':           'homeStrong',
    'AH Heim −0.5':            'homeStrong',
    'AH Heim −0.75':           'homeStrong',
    'AH Heim −1.0':            'homeStrong',
    'AH Heim −1.25':           'homeStrong',
    'AH Heim −1.5':            'homeStrong',
    'AH Heim −1.75':           'homeStrong',
    'AH Heim −2.0':            'homeStrong',
    'AH Heim −2.25':           'homeStrong',
    'AH Auswärts +0.25':       'awayStrong',
    'AH Auswärts +0.5':        'awayStrong',
    'AH Auswärts +0.75':       'awayStrong',
    'AH Auswärts +1.0':        'awayStrong',
    'AH Auswärts +1.25':       'awayStrong',
    'AH Auswärts +1.5':        'awayStrong',
    'AH Auswärts +1.75':       'awayStrong',
    'AH Auswärts +2.0':        'awayStrong',
    'AH Auswärts +2.25':       'awayStrong',
    'DNB: Heimteam':           'homeStrong',
    'DNB: Auswärtsteam':       'awayStrong',
    'Über 0.5 Tore':           'over',
    'Über 1.5 Tore':           'over',
    'Über 2.5 Tore':           'over',
    'Über 3.5 Tore':           'over',
    'Über 4.5 Tore':           'over',
    'Unter 0.5 Tore':          'under',
    'Unter 1.5 Tore':          'under',
    'Unter 2.5 Tore':          'under',
    'Unter 3.5 Tore':          'under',
    'Unter 4.5 Tore':          'under',
    'Beide Teams treffen':     'over',
    'Beide Teams treffen — Ja': 'over',
    'Beide Teams treffen — Nein': 'under'
  });

  // ── INCOMPATIBLE pairs ────────────────────────────────────────────────────
  // Set von "dir1|dir2" Strings — symmetrisch (beide Richtungen drin)
  const INCOMPATIBLE = Object.freeze(new Set([
    'homeStrong|awayStrong', 'awayStrong|homeStrong',
    'homeStrong|awayBias',   'awayBias|homeStrong',
    'homeStrong|drawOnly',   'drawOnly|homeStrong',
    'homeBias|awayStrong',   'awayStrong|homeBias',
    'awayStrong|drawOnly',   'drawOnly|awayStrong',
    'decisive|drawOnly',     'drawOnly|decisive',
    'over|under',            'under|over'
  ]));

  // ── Public API ────────────────────────────────────────────────────────────

  /** Direction-Bucket für ein Market-Label. null wenn unbekannt. */
  function getPickDirection(market) {
    if (typeof market !== 'string') return null;
    return DIRECTION_MAP[market] || null;
  }

  /** True wenn zwei Direction-Buckets nicht koexistieren können. */
  function areDirectionsIncompatible(d1, d2) {
    if (!d1 || !d2) return false;
    return INCOMPATIBLE.has(d1 + '|' + d2);
  }

  /**
   * True wenn ein Pick *legitim* für UI/Tracker/Stats ist.
   * Filtert trackingExcluded raus — sonst tauchen Konflikt-Picks
   * (z.B. AH Heim −0.5 wenn Hero X2 ist) wieder in der Card auf.
   * Spiegelt pick_helpers.is_legitimate_pick.
   */
  function isLegitimatePick(p) {
    if (p == null) return false;
    if (typeof p !== 'object') return true;
    return !p.trackingExcluded;
  }

  /** True wenn zwei Picks (per Market-Direction) miteinander kollidieren. */
  function arePicksConflicting(p1, p2) {
    if (!p1 || !p2) return false;
    const d1 = getPickDirection(p1.market);
    const d2 = getPickDirection(p2.market);
    return areDirectionsIncompatible(d1, d2);
  }

  /**
   * Filter-Helper: gibt aus `others` nur die Picks zurück,
   * die mit Hero-Pick KOLLIDIEREN. Nützlich um UI-Konflikte zu erkennen.
   */
  function findConflictingPicks(hero, others) {
    if (!hero || !Array.isArray(others)) return [];
    return others.filter(p => arePicksConflicting(hero, p));
  }

  /**
   * Hero-Sort-Key: Picks für Card-Auswahl sortieren.
   * Spiegelt pick_helpers.hero_sort_key (Python).
   *
   * Reihenfolge:
   *   1. saferAlt-Picks gewinnen (sicherere Quote schlägt riskante BET)
   *   2. dann BET vor ABWÄGEN vor SKIP
   *   3. dann höchste Edge zuerst
   *
   * Verwendung:  picks.sort((a, b) => heroSortKey(a) - heroSortKey(b))  ?
   * → Liefert STATTDESSEN ein Tuple-Array zurück, damit man stable sort hat.
   *   Nutzung: picks.sort((a, b) => {
   *     const ka = heroSortKey(a), kb = heroSortKey(b);
   *     for (let i = 0; i < ka.length; i++) {
   *       if (ka[i] < kb[i]) return -1;
   *       if (ka[i] > kb[i]) return 1;
   *     }
   *     return 0;
   *   });
   *
   * Komfort: heroSortCompare(a, b) direkt nutzen.
   */
  function heroSortKey(p) {
    if (!p) return [9, 9, 0];
    const saferRank  = p.saferAltFor ? 0 : 1;  // saferAlt zuerst
    const verdictRank = (p.verdict === 'BET') ? 0
                     : (p.verdict === 'ABWÄGEN') ? 1
                     : 2;
    const edgeNeg = -(Number(p.edgePP) || 0);  // höhere Edge zuerst
    return [saferRank, verdictRank, edgeNeg];
  }

  /** Komfort-Wrapper: direkt nutzbar in Array.sort(). */
  function heroSortCompare(a, b) {
    const ka = heroSortKey(a);
    const kb = heroSortKey(b);
    for (let i = 0; i < ka.length; i++) {
      if (ka[i] < kb[i]) return -1;
      if (ka[i] > kb[i]) return  1;
    }
    return 0;
  }

  /**
   * Wählt den Hero-Pick aus einer Liste.
   * Nur legitime Picks werden berücksichtigt.
   * Gibt null zurück wenn keine vorhanden.
   */
  function selectHero(picks) {
    if (!Array.isArray(picks)) return null;
    const legitimate = picks.filter(isLegitimatePick);
    if (legitimate.length === 0) return null;
    return legitimate.slice().sort(heroSortCompare)[0];
  }

  return Object.freeze({
    DIRECTION_MAP,
    INCOMPATIBLE,
    getPickDirection,
    areDirectionsIncompatible,
    isLegitimatePick,
    arePicksConflicting,
    findConflictingPicks,
    heroSortKey,
    heroSortCompare,
    selectHero,
    _version: '1.0.0'
  });
});
