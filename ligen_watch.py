#!/usr/bin/env python3
"""
ligen_watch.py — eingefrorene Ligen-Listen, vorwaerts gemessen. 03.10.2026.

Lucas: „welche Liga am besten abschneidet … in einem Monat naechster Check" und „das selbe gilt
aber fuer Poly auch".

🔴 Warum eine EINGEFRORENE Liste. Am 03.10. standen in freigabe.json 12 Betfair-Ligen ueber der
Huerde — gegen 13,7, die man bei so vielen Ligen ohne jede Kante per Zufall erwartet. Und die
Liga-Rendite der ersten Haelfte sagte die der zweiten nicht voraus (−6,6 %). Eine Rangliste, die
sich jeden Tag neu sortiert, findet immer „die besten Ligen" — sie findet nur jeden Tag andere.
Das ist dieselbe Fehlerklasse wie jede nachtraegliche Auswahl: *wer die Gewinner im Nachhinein
waehlt, misst seine Auswahl, nicht die Ligen.*

Deshalb: Liste HEUTE festschreiben, ab morgen nur noch zaehlen. Was ab FREEZE abgerechnet wird,
war beim Aufstellen der Liste unbekannt — das ist die einzige Messung, die die Frage beantwortet.
Neben jede Liste gehoert eine Kontrolle (Top-Ligen), damit „die Liste verliert weniger als der
Rest" von „die Liste gewinnt" unterscheidbar bleibt.

Die Zeilen werden in ligen_watch.json GESAMMELT, nicht jedes Mal aus den Quellen gelesen: das
Betfair-Ledger ist auf 40.000 Zeilen gedeckelt (~34 Tage) — am 01.11. waeren die ersten
Oktobertage sonst schon herausgerollt.

Urteil am Erzeuger: je Liste „sammelt" / „traegt" (UG > 0) / „traegt nicht" (OG < 0) / „offen".
Rendite Betfair zur Signalquote minus 2 % Kommission, Poly aus pnl/stake des Shortlist-Tracks.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
AUSGABE_FILE = "ligen_watch.json"
FREEZE = "2026-10-04T00:00:00+00:00"   # Liste am 03.10. aufgestellt; gezaehlt ab dem Folgetag
EINGEFROREN_AM = "2026-10-03"
KOMMISSION = 0.02
Z = 1.645
UG_MIN_N = 30
MINDEST_N = {"betfair": 300, "poly": 150}

# NICHT ANFASSEN bis zur Auswertung. Exakte Namen — „German Bundesliga 2" ist NICHT Bundesliga.
LISTEN = {
    "betfair_liste": {"quelle": "betfair", "titel": "Betfair: 12 Ligen ueber der Huerde (freigabe 03.10.)",
                      "ligen": ["CONCACAF Nations League C", "Ukrainian Premier League",
                                "Uzbekistan 1st Division", "Venezuelan Segunda Division",
                                "UAE Division 1", "Czech 2 Liga", "Czech Cup",
                                "Guatemalan Primera Division de Ascenso",
                                "Belgian Challenger Pro League", "Armenian Premier League",
                                "Georgian Liga 3", "Friendlies International U20"]},
    "betfair_kontrolle": {"quelle": "betfair", "titel": "Betfair-Kontrolle: Top-5-Ligen",
                          "ligen": ["English Premier League", "Spanish La Liga",
                                    "German Bundesliga", "Italian Serie A", "French Ligue 1"]},
    "poly_esport": {"quelle": "poly", "titel": "Poly: E-Sport", "kat": "E-Sport"},
    "poly_itf": {"quelle": "poly", "titel": "Poly: ITF-Tennis", "keyPraefix": "itf-"},
    "poly_kontrolle": {"quelle": "poly", "titel": "Poly-Kontrolle: EPL/LaLiga/Bundesliga/Ligue 1",
                       "ligen": ["EPL", "LA-LIGA", "BUNDESLIGA", "LIGUE-1"]},
}
VERGLEICHE = (("betfair_liste", "betfair_kontrolle"),
              ("poly_esport", "poly_kontrolle"), ("poly_itf", "poly_kontrolle"))


def _laden(pfad, leer=None):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return leer


# ── Zuordnung ───────────────────────────────────────────────────────────────────────────────
def liste_von(quelle, zeile) -> list:
    """Alle Listen, in die eine Zeile faellt. REIN."""
    aus = []
    for name, l in LISTEN.items():
        if l["quelle"] != quelle:
            continue
        if "ligen" in l and zeile.get("league") in l["ligen"]:
            aus.append(name)
        elif "kat" in l and zeile.get("cat") == l["kat"]:
            aus.append(name)
        elif "keyPraefix" in l and str(zeile.get("key") or "").startswith(l["keyPraefix"]):
            aus.append(name)
    return aus


def betfair_rendite(z) -> float | None:
    odd = z.get("odd")
    if not isinstance(odd, (int, float)) or odd <= 1 or not isinstance(z.get("win"), bool):
        return None
    return round((odd - 1) * (1 - KOMMISSION), 4) if z["win"] else -1.0


def poly_rendite(s) -> float | None:
    if s.get("result") not in ("win", "loss"):
        return None
    st, pnl = s.get("stake"), s.get("pnl")
    if not isinstance(st, (int, float)) or st <= 0 or not isinstance(pnl, (int, float)):
        return None
    return round(pnl / st, 4)


# ── Sammeln ─────────────────────────────────────────────────────────────────────────────────
def sammeln(stand, bf_zeilen, poly_settled) -> dict:
    """Neue Vorwaerts-Zeilen in stand['zeilen'] uebernehmen (Schluessel -> Eintrag). REIN.

    Nur was NACH dem Einfrieren abgerechnet (Betfair) bzw. erstmals gesehen (Poly) wurde.
    Ein Schluessel, der schon drin ist, wird nicht ueberschrieben: das Buch ist ein Buch."""
    zeilen = dict(stand.get("zeilen") or {})
    for z in bf_zeilen or []:
        if not isinstance(z, dict) or str(z.get("settledAt") or "") < FREEZE:
            continue
        listen = liste_von("betfair", z)
        r = betfair_rendite(z)
        if not listen or r is None:
            continue
        k = f"bf|{z.get('matchId')}|{z.get('market')}"
        zeilen.setdefault(k, {"listen": listen, "r": r, "liga": z.get("league"),
                              "markt": z.get("market"), "ts": z.get("settledAt")})
    for s in poly_settled or []:
        if not isinstance(s, dict) or str(s.get("firstTs") or "") < FREEZE:
            continue
        listen = liste_von("poly", s)
        r = poly_rendite(s)
        if not listen or r is None:
            continue
        k = f"poly|{s.get('key')}|{s.get('side')}"
        zeilen.setdefault(k, {"listen": listen, "r": r, "liga": s.get("league"),
                              "ts": s.get("firstTs")})
    return zeilen


# ── Werten ──────────────────────────────────────────────────────────────────────────────────
def kennzahlen(werte) -> dict:
    n = len(werte)
    if not n:
        return {"n": 0, "roi": None, "ug": None, "og": None}
    m = sum(werte) / n
    if n < UG_MIN_N:
        return {"n": n, "roi": round(m * 100, 1), "ug": None, "og": None}
    var = sum((w - m) ** 2 for w in werte) / (n - 1)
    se = math.sqrt(var / n)
    return {"n": n, "roi": round(m * 100, 1), "ug": round((m - Z * se) * 100, 1),
            "og": round((m + Z * se) * 100, 1)}


def urteil(k, mindest) -> str:
    if k["n"] < mindest or k["ug"] is None:
        return "sammelt"
    if k["ug"] > 0:
        return "traegt"
    if k["og"] < 0:
        return "traegt nicht"
    return "offen"


def bericht(zeilen, jetzt=None) -> dict:
    jetzt = jetzt or datetime.now(timezone.utc)
    listen = {}
    for name, l in LISTEN.items():
        werte = [e["r"] for e in zeilen.values() if name in e.get("listen", ())]
        k = kennzahlen(werte)
        je_liga = {}
        for e in zeilen.values():
            if name in e.get("listen", ()):
                je_liga.setdefault(e.get("liga") or "?", []).append(e["r"])
        listen[name] = {"titel": l["titel"], **k,
                        "urteil": urteil(k, MINDEST_N[l["quelle"]]),
                        "mindestN": MINDEST_N[l["quelle"]],
                        "jeLiga": {lg: kennzahlen(w) | {"ug": None, "og": None}
                                   for lg, w in sorted(je_liga.items())}}
    vergleiche = []
    for a, b in VERGLEICHE:
        ra, rb = listen[a]["roi"], listen[b]["roi"]
        vergleiche.append({"liste": a, "kontrolle": b,
                           "abstandPP": round(ra - rb, 1) if ra is not None and rb is not None else None})
    return {"updatedAt": jetzt.isoformat(), "eingefrorenAm": EINGEFROREN_AM, "freeze": FREEZE,
            "listen": listen, "vergleiche": vergleiche,
            "hinweis": "Je-Liga-Zahlen ohne Grenzen: Einzelligen sind zu klein, das Urteil gilt nur fuer die Liste."}


def main(base_dir=BASE, jetzt=None) -> int:
    import betfair_track_store
    stand = _laden(os.path.join(base_dir, AUSGABE_FILE), {}) or {}
    bf = betfair_track_store.load(os.path.join(base_dir, "betfair_track_results.json"))
    poly = (_laden(os.path.join(base_dir, "poly_shortlist_track.json"), {}) or {}).get("settled") or []
    zeilen = sammeln(stand, bf, poly)
    aus = bericht(zeilen, jetzt)
    aus["zeilen"] = zeilen
    from safe_write import write_json_atomic
    from pathlib import Path
    write_json_atomic(Path(base_dir) / AUSGABE_FILE, aus, indent=None)
    for name, l in aus["listen"].items():
        print(f"[ligen_watch] {name}: n={l['n']} roi={l['roi']} ug={l['ug']} -> {l['urteil']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
