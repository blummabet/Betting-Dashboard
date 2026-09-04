#!/usr/bin/env python3
"""
push_serie.py — welche Serie hatte der gepushte Ausgang IM MOMENT des Pushs?

04.09.2026 (Lucas): „wenn wir einen Favoriten haben und der hat eine lange Serie zu Hause
ungeschlagen, dann ist es ja okay, den zu pushen. Wenn wir auf den gar keine Serie haben,
eher nicht. Aber das müssten wir alles haben, die Infos."

Genau die haben wir NICHT — und konnten sie auch nicht nachtraeglich beschaffen. `liga_streaks.json`
ist eine Momentaufnahme: welche Serie ein Team an einem Push-Tag vor drei Wochen hatte, steht
nirgends. Der Push-Ledger schrieb davon nichts mit. Die Frage „tragen Pushs mit Serie besser als
ohne?" war damit unbeantwortbar, egal wie lange man wartet.

Dieses Modul stempelt die Serie beim SENDEN in den Ledger. Ab dann waechst die Antwort mit.

## Zwei Regeln, die hier hart verdrahtet sind

**Kein Treffer ist kein Ergebnis.** Findet die Namensbruecke das Team nicht, steht `None` da —
nicht „keine Serie". Ein Team, das wir nicht zuordnen konnten, ist etwas anderes als ein Team ohne
Serie, und beim spaeteren Auswerten entscheidet genau dieser Unterschied. Die Bruecke
(`betfair_name_bridge.compatible`) ist absichtlich eng: *„ein falscher Treffer ist schlimmer als
kein Treffer."*

**Die Serie muss zum Markt passen.** Bei „Match Odds → Real Madrid" zaehlen Sieg-/Ungeschlagen-
Serien von Real, nicht die Ueber-2,5-Serie des Gegners. Und sie muss zur SEITE passen: eine
Heim-Serie sagt ueber ein Auswaertsspiel nichts (derselbe Fehler stand am 04.09. in der
Card-Serien-Box).

## Was NICHT drinsteht
Ein Urteil. Das Modul sammelt nur — ob eine Serie den Push besser macht, ist offen und wird
gemessen, nicht angenommen. Der Kopf von `compute_streaks.py` gilt unveraendert: eine Serie
allein ist kein Edge.

REIN/testbar, kein I/O.
"""
from __future__ import annotations

from betfair_name_bridge import compatible

# Markt → welche Serien-Typen sind ueberhaupt einschlaegig, und fuer WEN.
#   ("seite", [typen])  ·  seite: "gewaehlt" = das gepushte Team, "beide" = beide Mannschaften
_MARKT_SERIEN = {
    "match odds":            ("gewaehlt", ["win", "unbeaten", "scored"]),
    "over/under 2.5 goals":  ("beide",    None),        # Richtung kommt aus leadName
    "over/under 3.5 goals":  ("beide",    None),
    "both teams to score?":  ("beide",    None),
}
_RICHTUNG = {
    "over 2.5 goals": ["over25"], "under 2.5 goals": ["under25"],
    "over 3.5 goals": ["over25"], "under 3.5 goals": ["under25"],
    "yes": ["bttsYes"], "no": ["bttsNo"],
}


def _typen(market, lead_name):
    m = str(market or "").strip().lower()
    eintrag = _MARKT_SERIEN.get(m)
    if not eintrag:
        return None, None
    seite, typen = eintrag
    if typen is None:
        typen = _RICHTUNG.get(str(lead_name or "").strip().lower())
    return (seite, typen) if typen else (None, None)


def _team_serien(streaks, team, venue, typen):
    """Serien EINES Teams, passend zu Typ und Spielhaelfte. Gesamt-Serien zaehlen mit,
    Serien der anderen Haelfte nie — die sagen ueber dieses Spiel nichts."""
    out = []
    for s in streaks or []:
        if s.get("type") not in typen:
            continue
        v = s.get("venue")
        if v not in (venue, "all", None):
            continue
        if not compatible(s.get("team"), team):
            continue
        out.append(s)
    return out


def _beste(kandidaten):
    """Die aussagekraeftigste: seltenste zuerst (zufallPct), sonst laengste."""
    mit = [s for s in kandidaten if isinstance(s.get("zufallPct"), (int, float))]
    if mit:
        return min(mit, key=lambda s: s["zufallPct"])
    return max(kandidaten, key=lambda s: s.get("length") or 0) if kandidaten else None


def _abdruck(s, team, venue):
    return {
        "team": team, "venue": venue,
        "typ": s.get("type"), "markt": s.get("market"),
        "laenge": s.get("length"),
        "zufallPct": s.get("zufallPct"),
        "basis": s.get("basis"),
        "state": (s.get("continuation") or {}).get("state"),
        "ligaBasisPct": s.get("ligaBasisPct"),
    }


def serie_fuer_push(alert: dict, streaks: list) -> dict | None:
    """Serien-Abdruck fuer einen Public-Push. None = nicht bestimmbar (kein Markt-Mapping,
    kein Team-Treffer). REIN.

    Rueckgabe:
      {"gefunden": True,  "serie": {...}}                      eine passende Serie
      {"gefunden": False, "grund": "keine Serie"}              Team erkannt, aber ohne Serie
      {"gefunden": False, "grund": "kein Team-Treffer"}        Namensbruecke greift nicht
      None                                                     Markt nicht abgebildet
    """
    seite, typen = _typen(alert.get("market"), alert.get("leadName"))
    if not typen:
        return None

    home, away = alert.get("home"), alert.get("away")
    lead = alert.get("leadName")

    if seite == "gewaehlt":
        if compatible(lead, home):
            paare = [(home, "H")]
        elif compatible(lead, away):
            paare = [(away, "A")]
        else:
            return {"gefunden": False, "grund": "kein Team-Treffer"}
    else:
        paare = [(home, "H"), (away, "A")]

    kandidaten, erkannt = [], False
    for team, venue in paare:
        treffer = _team_serien(streaks, team, venue, typen)
        # „erkannt" heisst: das Team kommt in den Serien-Daten ueberhaupt vor.
        if any(compatible(s.get("team"), team) for s in (streaks or [])):
            erkannt = True
        kandidaten += [(s, team, venue) for s in treffer]

    if not erkannt:
        return {"gefunden": False, "grund": "kein Team-Treffer"}
    if not kandidaten:
        return {"gefunden": False, "grund": "keine Serie"}

    beste = _beste([k[0] for k in kandidaten])
    team, venue = next((t, v) for s, t, v in kandidaten if s is beste)
    return {"gefunden": True, "serie": _abdruck(beste, team, venue)}
