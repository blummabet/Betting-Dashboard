#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
poly_price_path.py — 29.08.2026 (Lucas: „bei Poly kennt man ja die Wallets — wenn man die
mitlernt, sieht man, wie die Leute spielen").

## Warum das fehlte

Um die Frage zu beantworten, auf die es bei der Wallet-These ankommt — *bewegt sich der Preis,
NACHDEM eine Wallet eingestiegen ist?* — braucht es einen Preisverlauf. Den hatten wir nicht.
Gemessen am 29.08.:

    Betfair   835 Spiele · median 51 Punkte je Spiel · 90 % mit >= 6
    Poly      430 Maerkte · median  2 Punkte je Markt · 10 % mit >= 6
              (162 Maerkte hatten GENAU EINEN Punkt)

Mit zwei Punkten laesst sich kein Nachlauf messen. Damit ist die stroemungsstaerkste Idee des
Systems — Wallets folgen, die der Markt bestaetigt — schlicht nicht pruefbar gewesen.

## Warum es so duenn war, und warum die Behebung nichts kostet

`poly_money_broad_history.json` haengt am Close-Feed, und der nimmt einen Markt erst ~3h vor
Anpfiff auf, weil jeder Eintrag dort einen /holders-Call kostet (Deckel: 90 Maerkte je Lauf).
Bei zwei Laeufen pro Stunde sind das eine Handvoll Punkte, mehr nicht.

Der PREIS kostet dagegen gar nichts: er steckt schon in den Basis-Event-Daten des Sweeps, ohne
einen einzigen zusaetzlichen Call. `poly_money_upcoming.json` haelt ihn bereits ueber ein
120-Stunden-Fenster — aber nur als Momentaufnahme, die jeder Lauf ueberschreibt. Diese Datei hier
schreibt daraus einen Verlauf: gleiche Daten, gleiche Calls, nur nicht mehr weggeworfen.

## Was drin steht

    {key: {"league":…, "points":[{"ts":…, "htk":…, "vol":…, "p":{Ausgang: Preis}}, …]}}

Ein Punkt je Lauf und Markt. Bei zwei Laeufen pro Stunde und 120h Fenster sind das bis zu ~240
Punkte je Markt statt zwei — genug fuer die Frage, die dahinter steht.

Rein/netzfrei/testbar. Liest poly_money_upcoming.json + poly_money_broad_close.json,
schreibt poly_price_path.json. Setzt und sendet nichts.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent

UPCOMING_FILE = "poly_money_upcoming.json"
CLOSE_FILE = "poly_money_broad_close.json"
OUT_FILE = "poly_price_path.json"

# Ein Punkt je Lauf; darunter wird nicht nachgetragen (zwei Laeufe koennen sich ueberlappen).
MIN_ABSTAND_MIN = float(os.environ.get("POLY_PATH_MIN_ABSTAND_MIN") or 8)
# Deckel je Markt. 240 = 120h Fenster bei 2 Laeufen/h — mehr braucht kein Markt.
MAX_POINTS = int(os.environ.get("POLY_PATH_MAX_POINTS") or 240)
# Ein Markt faellt raus, wenn er so lange nicht mehr gesehen wurde (aufgeloest/vorbei).
KEEP_H = float(os.environ.get("POLY_PATH_KEEP_H") or 36)


def _now():
    return datetime.now(timezone.utc)


def _load(name, default=None):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def _ts(x):
    try:
        t = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _preise(m):
    """Nur echte Preise (0<p<1). Ein aufgeloester Markt (1.0/0.0) ist kein Preis mehr, sondern
    ein Ergebnis — der gehoert nicht in einen Pfad, der Bewegung messen soll."""
    p = (m or {}).get("prices") or {}
    out = {}
    for k, v in p.items():
        if isinstance(v, (int, float)) and 0 < float(v) < 1:
            out[str(k)] = round(float(v), 4)
    return out


def update(prev, quellen, now=None, min_abstand_min=MIN_ABSTAND_MIN,
           max_points=MAX_POINTS, keep_h=KEEP_H):
    """Haengt je Markt einen Punkt an. `quellen` = Liste von {key: markt}-Dicts, spaetere
    ueberschreiben frueher (Close-Feed hat den frischeren Preis als der Upcoming-Sweep).
    REIN/testbar."""
    now = now or _now()
    out = {k: {"league": v.get("league"), "sport": v.get("sport"),
               "points": list(v.get("points") or [])}
           for k, v in (prev or {}).items() if isinstance(v, dict)}

    zusammen = {}
    for q in (quellen or []):
        for key, m in (q or {}).items():
            if isinstance(m, dict):
                zusammen[key] = m

    for key, m in zusammen.items():
        if m.get("resolved"):
            continue                       # aufgeloest -> kein Preis mehr, nur noch Ergebnis
        pr = _preise(m)
        if not pr:
            continue
        e = out.setdefault(key, {"league": m.get("league"), "sport": m.get("sport"), "points": []})
        e["league"] = m.get("league") or e.get("league")
        e["sport"] = m.get("sport") or e.get("sport")
        pts = e["points"]
        # Nicht zweimal derselbe Lauf: zwei ueberlappende Laeufe wuerden den Pfad sonst
        # verdoppeln und jede Bewegungsmessung verwaessern.
        if pts:
            letzt = _ts(pts[-1].get("ts"))
            if letzt and (now - letzt).total_seconds() < min_abstand_min * 60:
                continue
        htk = m.get("hoursToKickoff")
        pts.append({"ts": now.isoformat(),
                    "htk": round(float(htk), 2) if isinstance(htk, (int, float)) else None,
                    "vol": round(float(m.get("totalUsd") or 0)),
                    "p": pr})
        if len(pts) > max_points:
            del pts[:len(pts) - max_points]

    cutoff = now - timedelta(hours=keep_h)
    for key in list(out.keys()):
        pts = out[key].get("points") or []
        letzt = _ts(pts[-1].get("ts")) if pts else None
        if not pts or (letzt and letzt < cutoff):
            del out[key]
    return out


def markout(pfad, key, side, ab_ts, minuten=30):
    """DIE Frage: bewegt sich der Preis NACH einem Einstieg — und in welche Richtung?

    Gibt die Preisaenderung in Prozentpunkten zurueck: Preis(ab_ts + minuten) − Preis(ab_ts),
    positiv = der Markt kam zu uns. None, wenn der Pfad den Zeitraum nicht abdeckt — bewusst
    None statt 0, sonst zaehlt eine Luecke als „keine Bewegung" und verwaessert jeden Schnitt.

    Genau das ist die Messung, mit der sich „diese Wallet ist kopierbar" von „diese Wallet hat
    nur gewonnen" trennen laesst. REIN/testbar."""
    e = (pfad or {}).get(key)
    pts = (e or {}).get("points") or []
    t0 = _ts(ab_ts)
    if not pts or not t0 or not side:
        return None
    ziel = t0 + timedelta(minutes=minuten)

    def _preis_bei(t, vorwaerts):
        """Naechstliegender Punkt: vor `t` der letzte davor, fuer das Ziel der erste danach.
        Kein Interpolieren — ein erfundener Zwischenwert waere eine Messung, die es nicht gab."""
        best = None
        for pt in pts:
            ts = _ts(pt.get("ts"))
            if ts is None or side not in (pt.get("p") or {}):
                continue
            if vorwaerts and ts >= t:
                return pt["p"][side]
            if not vorwaerts and ts <= t:
                best = pt["p"][side]
        return best

    a = _preis_bei(t0, False)
    b = _preis_bei(ziel, True)
    if a is None or b is None:
        return None
    return round((b - a) * 100, 3)


def main() -> int:
    from safe_write import write_json_atomic
    prev = _load(OUT_FILE)
    up = _load(UPCOMING_FILE)
    close = _load(CLOSE_FILE)
    d = update(prev, [up, close])
    write_json_atomic(BASE / OUT_FILE, d, indent=None)
    pts = [len(v.get("points") or []) for v in d.values()]
    pts.sort()
    med = pts[len(pts) // 2] if pts else 0
    print("=== poly_price_path.py ===")
    print(f"  {len(d)} Maerkte · median {med} Punkte · max {max(pts) if pts else 0} "
          f"· {sum(1 for n in pts if n >= 6)} mit >=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
