#!/usr/bin/env python3
"""
poly_deckung.py — was der Money-Scan NICHT gesehen hat
======================================================
06.09.2026 (Lucas mit Polymarket-Screenshot: „Serie A sind alle Spiele da. Blödsinn zu sagen
2 solche Spiele seien nicht verfuegbar."). Er hatte recht. Ich hatte aus „nicht in unseren
Artefakten" auf „gibt es nicht" geschlossen — der Fehler, vor dem die eigene Arbeitsregel warnt:
*leeres eigenes File = unser Fetcher-Bug, nicht die Quelle.*

## Das Problem hinter dem Problem
Ein Scanner kann nicht melden, was er nie gesehen hat. `health/poly-global.json` stand auf gruen,
`poly_status.json` auf gruen — beide messen, ob der Lauf DURCHLIEF, nicht ob er VOLLSTAENDIG war.
Eine Lueckenmessung braucht eine **zweite, unabhaengige Quelle**.

Die haben wir: `liga_poly_prices.json` wird vom Liga-Fetcher gefuellt und traegt Slug, Anpfiff
und Preise. Wo der Liga-Fetcher einen Poly-Markt kennt, den der Money-Scan nie hatte, ist das
eine Deckungsluecke — nachweisbar ohne einen einzigen API-Aufruf.

## Der Fund vom 06.09.
9 Maerkte, 5 davon im 8h-Fenster:

    htk   Slug                     Paarung                        vol(1X2)
    1.4   sea-par-mon-2026-09-06   Parma v Monza                     1.184
    4.4   sea-bol-sas-2026-09-06   Bologna v Sassuolo                1.033
    4.9   lal-ala-osa-2026-09-06   Alavés v Osasuna                  1.041
    7.1   fl1-olm-pfc-2026-09-06   Marseille v Paris FC              1.533
    7.1   sea-juv-mil-2026-09-06   Juventus v AC Milan               7.898

Alle unter `MIN_VOL_USD = 7500` — dem Boden, der auch fuer die PREIS-ONLY-Zweige galt, obwohl
der nur das teure Holder-Budget schuetzen soll. Daher jetzt `MIN_VOL_PREIS_USD`.

REIN/testbar, kein I/O.
"""
from __future__ import annotations

from datetime import datetime, timezone

FENSTER_H = 120.0          # so weit reicht die upcoming-Erfassung
NAH_H = 8.0                # bis hierher latcht die Konjunktion — Luecken hier tun weh


def _ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def luecken(liga_prices: dict, bekannte_keys, now: datetime = None,
            fenster_h: float = FENSTER_H) -> list:
    """Maerkte, die der Liga-Fetcher kennt und der Money-Scan nie hatte. REIN.

    -> [{"slug","home","away","htk","vol"}], nach Anpfiff-Naehe sortiert.

    `bekannte_keys` ist die Vereinigung aus close, upcoming UND history — history deshalb,
    weil ein Markt, der irgendwann einmal erfasst wurde, keine Luecke ist, auch wenn er
    gerade aus dem Fenster gefallen ist.
    """
    now = now or datetime.now(timezone.utc)
    bekannt = set(bekannte_keys or ())
    out = []
    for v in ((liga_prices or {}).get("prices") or {}).values():
        if not isinstance(v, dict):
            continue
        slug, ko = v.get("slug"), _ts(v.get("kickoff"))
        if not slug or ko is None or slug in bekannt:
            continue
        htk = (ko - now).total_seconds() / 3600.0
        if not (0 < htk <= fenster_h):
            continue
        out.append({"slug": slug, "home": v.get("homeName"), "away": v.get("awayName"),
                    "htk": round(htk, 1), "vol": round(v.get("vol") or 0)})
    out.sort(key=lambda r: r["htk"])
    return out


def nah(luecken_liste, nah_h: float = NAH_H) -> list:
    """Die Luecken, die JETZT wehtun — innerhalb des Latch-Fensters. REIN."""
    return [r for r in (luecken_liste or []) if r["htk"] <= nah_h]
