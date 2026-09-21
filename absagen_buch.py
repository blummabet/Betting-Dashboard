"""Das Buch der abgesagten Spiele — rein, ohne I/O.

🔴 21.09.2026 (Lucas' Störungsmeldung): „Levante–Athletic Club seit 97 h ohne Ergebnis".
Das Spiel wurde am 16.09. eine halbe Stunde vor Anpfiff wegen Starkregen abgesagt. Fünf Tage
später meldete es niemand mehr — nicht weil es abgerechnet worden wäre, sondern weil es aus
`liga-data.json` herausgerollt ist. Der Absage-Vermerk vom 20.09. lag AM FIXTURE und ist mit
ihm verschwunden. In `picks_history.json` stehen seine drei Picks bis heute auf `result: null`,
in `money_map_ledger.json` steht es auf `pending`. Beides rechnet nie ab.

Gemessen: von den 263 Zeilen in `picks_history.json`, die in die Cards-Bilanz zählen, ist genau
diese eine unaufgelöst — die 129 übrigen offenen liegen ausserhalb des Umfangs und sollen es.
Der Schaden ist also nicht die Zahl, sondern die Bauart: eine Zeile, die nie abrechnet, und ein
Melder, der nach ein paar Tagen von selbst verstummt.

Fehlerklasse: eine Lücke, die sich durch Zeitablauf selbst erledigt, hinterlässt keine Statistik.

Deshalb dieses Buch: die Absage wird dort festgehalten, wo sie ERKANNT wird, in einer Datei mit
eigenem Lebenslauf — und nicht in einem Datensatz, der ein rollierendes Fenster ist. Wer später
fragt „warum rechnet dieses Spiel nicht ab?", bekommt eine Antwort statt Schweigen.

Der Schlüssel muss aus zwei Welten treffen: `fetch_liga_ergebnisse` kennt Fixtures aus der
API, `resolve_picks` kennt Einträge aus `picks_history`. Gemeinsam haben beide nur Datum und
die beiden Mannschaftsnamen — dieselbe Paarung, in unterschiedlicher Schreibweise
(„Athletic Club" / „Athletic Bilbao"). `schluessel()` normalisiert deshalb genauso wie
`resolve_picks._norm_name` und trägt die Namen zusätzlich im Klartext mit, damit ein Mensch
im Buch lesen kann, was dort steht.
"""
from __future__ import annotations

import re

# Dieselben Suffixe wie in `resolve_picks._norm_name` — die Schreibweisen unterscheiden sich
# zwischen den Quellen, die Paarung nicht.
_SUFFIXE = r'\b(fc|sv|sc|ac|as|us|cd|sk|rb|bv|vv|nk|fk|cf|ss|if|kf|pfc)\b'

# Wie lange bleibt eine Absage im Buch? Lang genug, dass ein Resolver sie sicher sieht, und
# nicht ewig: ein Buch, das nur waechst, wird irgendwann nicht mehr gelesen.
KEEP_TAGE = 120


def norm(s) -> str:
    """Mannschaftsname auf seine Vergleichsform. REIN."""
    s = str(s or "").lower()
    s = re.sub(_SUFFIXE, " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def schluessel(datum, heim, gast) -> str:
    """"JJJJ-MM-TT|heim|gast" — oder "" wenn eines der drei Stuecke fehlt. REIN.

    Ohne Datum oder ohne einen der Namen gibt es keinen Schluessel: ein halber Schluessel
    wuerde spaeter irgendetwas treffen. Fehlende Information rendert hier als NICHTS.
    """
    d = str(datum or "")[:10]
    h, g = norm(heim), norm(gast)
    if not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and h and g):
        return ""
    return f"{d}|{h}|{g}"


def eintragen(buch: dict, datum, heim, gast, status, gesehen_at, liga=None) -> dict:
    """Neues Buch mit dieser Absage. REIN — das uebergebene Buch bleibt unveraendert.

    Ein bereits eingetragenes Spiel behaelt seinen ERSTEN `gesehenAt`: wann die Absage zuerst
    bekannt war, ist die Auskunft; jeder spaetere Lauf wuerde sie sonst nach vorn schieben und
    „seit wann haengt das" unbeantwortbar machen.
    """
    k = schluessel(datum, heim, gast)
    if not k or not str(status or "").strip():
        return dict(buch or {})
    neu = dict(buch or {})
    if k in neu and isinstance(neu[k], dict) and neu[k].get("gesehenAt"):
        return neu
    neu[k] = {"datum": str(datum)[:10], "heim": str(heim), "gast": str(gast),
              "status": str(status), "gesehenAt": str(gesehen_at)}
    if liga:
        neu[k]["liga"] = str(liga)
    return neu


def _kopf(name: str) -> str:
    """Das erste Wort der Vergleichsform — „athletic club" und „athletic bilbao" haben es
    gemeinsam, „atletico" nicht. REIN."""
    t = norm(name).split()
    return t[0] if t else ""


def nachschlagen(buch: dict, datum, heim, gast):
    """Der Eintrag zu dieser Paarung, oder None. REIN.

    Zuerst der exakte Schluessel. Trifft er nicht, wird am selben DATUM ueber den Kopf beider
    Namen verglichen: die Quellen schreiben dieselbe Paarung verschieden — „Athletic Club" bei
    Sofascore, „Athletic Bilbao" bei API-Football, „Levante" und „Levante UD". Ohne diesen
    zweiten Weg findet das Buch den Levante-Fall nicht, fuer den es gebaut ist.

    Der zweite Weg gilt nur bei EINDEUTIGKEIT: passen an einem Datum mehrere Eintraege
    (Manchester United / Manchester City), wird None zurueckgegeben. Eine falsch gevoidete
    Wette ist teurer als eine, die offen bleibt — und „mehrdeutig" ist eine Auskunft, die
    `mehrdeutig()` getrennt liefert, damit sie nicht als „nicht abgesagt" verschwindet.

    None heisst „nicht als abgesagt bekannt" — nie „findet regulaer statt". Der Aufrufer
    wartet dann weiter, statt etwas zu erfinden.
    """
    k = schluessel(datum, heim, gast)
    if not k:
        return None
    e = (buch or {}).get(k)
    if isinstance(e, dict):
        return e
    kand = _kandidaten(buch, datum, heim, gast)
    return kand[0] if len(kand) == 1 else None


def _kandidaten(buch: dict, datum, heim, gast) -> list:
    d, kh, kg = str(datum or "")[:10], _kopf(heim), _kopf(gast)
    if not (d and kh and kg):
        return []
    return [e for e in (buch or {}).values()
            if isinstance(e, dict) and str(e.get("datum"))[:10] == d
            and _kopf(e.get("heim")) == kh and _kopf(e.get("gast")) == kg]


def mehrdeutig(buch: dict, datum, heim, gast) -> bool:
    """Passt am selben Datum mehr als ein Eintrag? REIN.

    Diese Faelle duerfen nicht als „nicht abgesagt" durchrutschen — sie brauchen einen
    Menschen, und dafuer muessen sie zaehlbar sein.
    """
    if schluessel(datum, heim, gast) in (buch or {}):
        return False
    return len(_kandidaten(buch, datum, heim, gast)) > 1


def aufraeumen(buch: dict, heute, keep_tage: int = KEEP_TAGE) -> dict:
    """Eintraege aelter als `keep_tage` fallen raus. REIN.

    `heute` ist ein `date`. Ein Eintrag ohne lesbares Datum bleibt: ihn zu entfernen waere
    eine Entscheidung auf Basis einer Information, die nicht dasteht.
    """
    import datetime as _dt
    out = {}
    for k, e in (buch or {}).items():
        if not isinstance(e, dict):
            continue
        try:
            d = _dt.date.fromisoformat(str(e.get("datum"))[:10])
        except (ValueError, TypeError):
            out[k] = e
            continue
        if (heute - d).days <= keep_tage:
            out[k] = e
    return out
