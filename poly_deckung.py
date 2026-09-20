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


# ── Das Buch: eine Luecke, die anpfeift, verschwindet aus der Messung ────────
#
# 🔴 20.09.2026. Die Batterie meldete „sea-mil-lec-2026-09-20 (AC Milan v US Lecce, Anpfiff in
# 0.1h) — der Liga-Fetcher hat den Markt, der Money-Scan nie". Zwanzig Minuten spaeter war die
# Messung leer: `luecken()` nimmt nur Maerkte mit `0 < htk <= fenster_h`, und mit dem Anpfiff
# faellt die Luecke aus dem Fenster. Der Fund war weg, bevor jemand ihn ansehen konnte.
#
# Fehlerklasse: eine Luecke, die sich durch Zeitablauf selbst erledigt, hinterlaesst keine
# Statistik. Auf die Frage „passiert das oft?" gab es deshalb nie eine Zahl — nur „gerade
# keine". Das ist dieselbe Klasse wie beim ausgebliebenen Verkaufsversuch: eine Wirkung, die
# ausbleibt, hinterlaesst keine Spur.
#
# Das Buch haelt beides fest: jeden Lauf mit seinem Nenner (wie viele Maerkte kannte die
# zweite Quelle?) und jede Luecke mit ihrer engsten Annaeherung an den Anpfiff. Erst damit
# laesst sich sagen, ob die Deckung besser wird.
LEDGER_KEEP_LAEUFE = 500
LEDGER_KEEP_SLUGS = 400


def buchen(ledger: dict, luecken_liste, n_liga_maerkte: int, bekannte_keys,
           now: datetime = None, keep_laeufe: int = LEDGER_KEEP_LAEUFE,
           keep_slugs: int = LEDGER_KEEP_SLUGS) -> dict:
    """Schreibt einen Lauf und seine Luecken fort. REIN (nimmt und gibt ein dict).

    `n_liga_maerkte` ist der NENNER: ohne ihn ist „3 Luecken" keine Auskunft. Ein Slug, der
    spaeter in `bekannte_keys` auftaucht, wird als `nachgeholt` markiert statt geloescht —
    „spaet gesehen" und „nie gesehen" sind zwei verschiedene Befunde.
    """
    now = now or datetime.now(timezone.utc)
    ts = now.isoformat()
    led = dict(ledger or {})
    slugs = dict(led.get("slugs") or {})
    bekannt = set(bekannte_keys or ())

    for r in (luecken_liste or []):
        z = dict(slugs.get(r["slug"]) or {})
        if not z:
            z = {"slug": r["slug"], "home": r.get("home"), "away": r.get("away"),
                 "erstGesehen": ts, "minHtk": r["htk"], "vol": r.get("vol"),
                 "nLaeufe": 0, "nachgeholt": False}
        z["zuletztGesehen"] = ts
        z["nLaeufe"] = int(z.get("nLaeufe") or 0) + 1
        # Die ENGSTE Annaeherung an den Anpfiff ist die teure Zahl: eine Luecke bei 100h ist
        # ein Fetch-Rueckstand, eine bei 0,1h ist ein Spiel, das blind zum Geld gesetzt wurde.
        if r["htk"] < (z.get("minHtk") if z.get("minHtk") is not None else 1e9):
            z["minHtk"] = r["htk"]
        if r.get("vol"):
            z["vol"] = r["vol"]
        slugs[r["slug"]] = z

    for slug, z in slugs.items():
        if not z.get("nachgeholt") and slug in bekannt:
            z["nachgeholt"] = True
            z["nachgeholtAt"] = ts

    if keep_slugs and len(slugs) > keep_slugs:
        geordnet = sorted(slugs.values(), key=lambda z: str(z.get("zuletztGesehen") or ""))
        for z in geordnet[:len(slugs) - keep_slugs]:
            slugs.pop(z["slug"], None)

    laeufe = list(led.get("laeufe") or [])
    laeufe.append({"ts": ts, "nLigaMaerkte": int(n_liga_maerkte or 0),
                   "nLuecken": len(luecken_liste or []),
                   "nNah": len(nah(luecken_liste))})
    led["laeufe"] = laeufe[-keep_laeufe:] if keep_laeufe else laeufe
    led["slugs"] = slugs
    led["updatedAt"] = ts
    return led


def bilanz(ledger: dict) -> dict:
    """Was das Buch sagt — mit Nenner. REIN.

    `quotePct` ist der Anteil der Laeufe, in denen ueberhaupt eine Luecke offen war; ohne
    einen einzigen Lauf gibt es kein Urteil und keine 0 %.
    """
    led = ledger or {}
    laeufe = [l for l in (led.get("laeufe") or []) if isinstance(l, dict)]
    slugs = [z for z in (led.get("slugs") or {}).values() if isinstance(z, dict)]
    mit = [l for l in laeufe if (l.get("nLuecken") or 0) > 0]
    offen = [z for z in slugs if not z.get("nachgeholt")]
    nie_erfasst = [z for z in offen if (z.get("minHtk") is not None and z["minHtk"] <= NAH_H)]
    return {
        "nLaeufe": len(laeufe),
        "nLaeufeMitLuecke": len(mit),
        "quotePct": round(len(mit) / len(laeufe) * 100) if laeufe else None,
        "nSlugs": len(slugs),
        "nOffen": len(offen),
        "nBisAnpfiff": len(nie_erfasst),
        "urteil": ("nicht belegt" if len(laeufe) < 20
                   else ("Deckung dicht" if not mit else "Deckung hat Loecher")),
    }
