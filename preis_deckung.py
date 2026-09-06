#!/usr/bin/env python3
"""
preis_deckung.py — wie viele Picks entstehen blind zum Markt?
=============================================================
06.09.2026.

Die Preis/Geld-Signale sind die einzige Signalfamilie mit belegtem CLV-Zusammenhang
(r = +0,353, p = 0,0001, n = 156; Bootstrap-KI [+0,21; +0,48]). Die Staerke-Signale liegen bei
r = +0,003. Ein Pick ohne ein einziges Preis-Signal ist damit nicht „etwas schwaecher belegt" —
er ist von der einzigen Haelfte abgeschnitten, die etwas kann.

Gemessen am 06.09.2026 ueber die drei Signal-Ledger: **162 von 318 Picks (51 %) trugen kein
einziges Preis-Signal.** Aufgeschluesselt war das keine Streuung, sondern eine Struktur:

    Marktfamilie      blind
    1X2 / DC / AH      klein
    Ueber/Unter        gross
    BTTS               vollstaendig

Die Ursachen lagen in `fetch_liga_odds.append_snapshot` (beide am 06.09. behoben):
BTTS wurde nie in die Zeitreihe geschrieben, und das Schreib-Gate fragte nur nach 1X2 — eine
reine Tor-Bewegung bei stehendem 1X2 erzeugte keinen Snapshot.

Dieses Modul misst, ob der Fix wirkt. Es ist die zweite, unabhaengige Messung neben dem Test:
der Test sagt „die Funktion schreibt jetzt BTTS", dieses Modul sagt „und es kommt auch bei den
Picks an". Beides braucht es — ein gruener Test an einer Funktion, die niemand mehr aufruft,
ist kein Beleg.

WICHTIG: die Zeitreihe laesst sich nicht rueckwirkend fuellen. Alles vor dem 06.09. bleibt
blind. Deshalb misst `deckung()` nur ein Fenster der ZULETZT abgerechneten Picks — sonst
verduennt der Altbestand den Befund auf Monate hinaus.

REIN/testbar, kein I/O.
"""
from __future__ import annotations

from datetime import datetime, timezone

# Signale, die aus Preis, Geld oder Bewegung kommen. Eine Quelle: preis_signal.
from preis_signal import PREIS_SIGNALE

# Unter so vielen abgerechneten Picks im Fenster gibt es kein Urteil, nur eine Beschreibung.
MIN_N = 25
# Fenster in Tagen. Kurz genug, dass der Altbestand den Fix nicht ueberdeckt.
FENSTER_TAGE = 21
# Ab hier ist die Deckung ein Befund und keine Schwankung.
BLIND_MAX = 0.35


def _zeit(wert):
    if not wert:
        return None
    try:
        t = datetime.fromisoformat(str(wert).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def familie(markt) -> str:
    """Marktfamilie eines Picks — das ist die Ebene, auf der die Luecke lag."""
    m = (markt or "").lower()
    if "btts" in m or "bts" in m or "beide teams" in m:
        return "BTTS"
    # Ecken VOR Ü/U: „Unter 6.5 Ecken" traegt beide Woerter. Der eigene Test hat das
    # gefunden — die Reihenfolge ist hier die ganze Regel.
    if any(w in m for w in ("ecke", "corner")):
        return "Ecken"
    if any(w in m for w in ("über", "ueber", "over", "unter", "under")):
        return "Ü/U"
    return "1X2/DC/AH"


def hat_preis_signal(rec) -> bool:
    """Traegt dieser Ledger-Eintrag mindestens ein Preis/Geld-Signal mit echter Zahl?"""
    if not isinstance(rec, dict):
        return False
    for s in (rec.get("signals") or []):
        if not isinstance(s, dict) or s.get("name") not in PREIS_SIGNALE:
            continue
        w = s.get("score")
        if isinstance(w, bool) or not isinstance(w, (int, float)):
            continue
        return True
    return False


def deckung(records, now=None, fenster_tage: float = FENSTER_TAGE) -> dict | None:
    """Blind-Quote der zuletzt abgerechneten Picks.

    -> {"n", "blind", "blindPct", "proFamilie": {fam: {"n","blind","blindPct"}}, "fensterTage"}
    -> None, wenn im Fenster weniger als MIN_N Picks liegen. Kein Urteil ist etwas anderes als
       ein gemessenes „alles gut".
    """
    now = now or datetime.now(timezone.utc)
    grenze = now.timestamp() - float(fenster_tage) * 86400.0
    im_fenster = []
    for r in (records or []):
        if not isinstance(r, dict):
            continue
        t = _zeit(r.get("resolvedAt"))
        if t is None or t.timestamp() < grenze:
            continue
        im_fenster.append(r)
    if len(im_fenster) < MIN_N:
        return None

    pro = {}
    blind = 0
    for r in im_fenster:
        fam = familie(r.get("market"))
        d = pro.setdefault(fam, {"n": 0, "blind": 0})
        d["n"] += 1
        if not hat_preis_signal(r):
            d["blind"] += 1
            blind += 1
    for d in pro.values():
        d["blindPct"] = round(d["blind"] / d["n"] * 100, 1)
    n = len(im_fenster)
    return {"n": n, "blind": blind, "blindPct": round(blind / n * 100, 1),
            "proFamilie": pro, "fensterTage": float(fenster_tage)}


def befunde(d, blind_max: float = BLIND_MAX) -> list:
    """Lesbare Befunde aus einer Deckungsmessung. Leere Liste = nichts zu melden."""
    if not d:
        return []
    out = []
    if d["blindPct"] > blind_max * 100:
        out.append("%.0f %% der letzten %d abgerechneten Picks (%d) trugen kein Preis-Signal — "
                   "sie entstanden blind zu der einzigen Signalfamilie mit belegtem CLV"
                   % (d["blindPct"], d["n"], d["blind"]))
    for fam, v in sorted(d["proFamilie"].items(), key=lambda kv: -kv[1]["blindPct"]):
        if v["n"] >= 8 and v["blindPct"] >= 99.0:
            out.append("%s: %d von %d ohne jedes Preis-Signal — vollstaendig blind, das ist "
                       "eine fehlende Zuleitung, keine Streuung" % (fam, v["blind"], v["n"]))
    return out
