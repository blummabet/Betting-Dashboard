#!/usr/bin/env python3
"""
stats_scope.py — Was zählt in die Card-Statistik? (27.08.2026, Lucas)

## Warum

`picks_history.json` sammelt seit dem alten, breiten Card-System **20 Ligen** ein — Ungarn,
Polen, Kroatien, Schottland, Österreich, Schweiz, Türkei und so weiter. Dazu die komplette
alte Saison bis Mai 2026. Lucas: *„die will ich auf keinen Fall drauf haben, das haut uns
komplett die Statistik zusammen"* — gezählt werden soll nur, was wir heute wirklich bespielen:
die Top-5 ab dem Start der neuen Saison, plus MLS.

## Die Regel

Ein Eintrag zählt, wenn **seine Liga in `stats_scope.json` steht** UND **sein Datum ≥ dem
Saisonstart dieser Liga** ist. Eine unbekannte Liga zählt NICHT — kommt morgen eine neue dazu,
verschmutzt sie die Bilanz nicht, bis jemand sie bewusst einträgt.

Die Zahlen stehen in `stats_scope.json`, nicht hier: `results-v2.js` liest dieselbe Datei.
Zwei getippte Listen driften auseinander, sobald eine angefasst wird.
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCOPE_FILE = BASE / "stats_scope.json"

_CACHE: dict = {}


def load(path=None) -> dict:
    """{ligaCode: {name, seasonStart}}. Leer, wenn die Datei fehlt oder kaputt ist.

    Ein leerer Umfang heißt „nichts zählt" — und das ist Absicht: lieber eine sichtbar leere
    Bilanz als eine, die stillschweigend zwanzig Ligen mitrechnet.
    """
    p = Path(path) if path else SCOPE_FILE
    key = str(p)
    if key in _CACHE:
        return _CACHE[key]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        out = data.get("leagues") or {}
        if not isinstance(out, dict):
            out = {}
    except Exception:
        out = {}
    _CACHE[key] = out
    return out


def counts(league, date_iso, scope=None) -> bool:
    """Zählt dieser Eintrag in die Bilanz? REIN, wirft nie."""
    scope = scope if scope is not None else load()
    entry = scope.get(str(league or "").strip())
    if not isinstance(entry, dict):
        return False
    start = str(entry.get("seasonStart") or "")
    d = str(date_iso or "")[:10]
    if len(d) != 10 or len(start) != 10:
        return False
    return d >= start


def split(entries, league_of=lambda e: e.get("league"),
          date_of=lambda e: e.get("dateIso"), scope=None):
    """(zaehlt, zaehlt_nicht). REIN — praktisch für Guards und Auswertungen."""
    scope = scope if scope is not None else load()
    drin, raus = [], []
    for e in (entries or []):
        if isinstance(e, dict) and counts(league_of(e), date_of(e), scope):
            drin.append(e)
        else:
            raus.append(e)
    return drin, raus


if __name__ == "__main__":
    s = load()
    print("Statistik-Umfang:", ", ".join(f"{k} ab {v.get('seasonStart')}" for k, v in sorted(s.items())))
