#!/usr/bin/env python3
"""killer.py — das Konjunktions-Element: nur wo mehrere Ströme GLEICHZEITIG zustimmen.

29.08.2026 (Lucas): „Also dort kommst halt nur rein wenn / Pini move da / Betfair geld oben
und quoten mitziehen / Poly geld oben / ggf noch so sachen wie / Streak muss auch passen."

Was die Messung zu dieser Idee gesagt hat, bevor eine Zeile Code entstand:

1) Die Konjunktion 1:1 auf die 40 Spiele des Tages angewendet ergab DREI Spiele — alle live,
   alle auf haushohe Favoriten (Galatasaray @1.15). Wo sich alle einig sind, ist der Preis
   fertig. Eine reine Konjunktion ist eine Maschine zum Kauf entschiedener Favoriten.

2) Poly deckt ~10 von 40 Spielen ab. Als Pflichtbedingung schrumpft die Sektion auf unter ein
   Spiel pro Tag und wird nie messbar.

3) Drei von Lucas' Bedingungen liegen aber seit dem 23.08. abgerechnet vor — in
   betfair_track_results.json, 8.000 Zeilen, nur vor Anpfiff erfasst:
       conc   = Geld-Favorit hält >= 65% des Marktgeldes   („Betfair Geld oben")
       inflow = >= 2.000 EUR frisch in den Markt geflossen  („frisches Geld")
       dir    = 'in', die Quote kürzt sich                  („Quoten ziehen mit")
   ROI zur Closing-Quote (Signal und Preis im selben Moment, also ohne Look-ahead):
       alles                     -1,58%   n=8000
       nur dir=in                -0,13%   n=1974
       + conc                    +1,44%   n=1351
       + inflow (Konjunktion)    +8,60%   n=115
           davon nur Match Odds +12,93%   n=81   CLV +3,5pp
   Jede zusätzliche Bedingung hebt es. Das ist das Tor.

4) Eine Preis-Bedingung (pinnFair × Quote >= 1) hatte ich vorgeschlagen und wieder verworfen:
   in den Daten steht sie ANDERSHERUM (Wert>=0: -29,4% bei n=30 · Wert<0: +16,1% bei n=83).
   Die Stichprobe ist klein und die Bänder sind weit — aber es gibt keinen Beleg dafür, so zu
   filtern, und einen schwachen dagegen. Also wird der Wert nur MITGESCHRIEBEN, nicht gefiltert.

Daraus die zwei Stufen (Lucas' Entscheidung: „Zwei Stufen sichtbar"):

   Stufe 1  „Voll gedeckt"  = Kern + Poly-Geld auf derselben Seite + Pinnacle-Favorit stimmt zu
   Stufe 2  „Betfair-Kern"  = das gemessene Tor allein

Die Verstärker (Pinnacle-Bewegung, Serie/Form, Liga-Track) heben den Rang und stehen als Chip
an der Zeile — sie sind KEINE Bedingung, weil sie nur für die Top-5-Ligen überhaupt vorliegen.

Alle Schwellen sind aus betfair_track_record.py gespiegelt, nicht nachgebaut: die Sektion muss
per Konstruktion dieselbe Menge treffen, die dort später abgerechnet wird. Läuft sie auseinander,
misst das Tracking etwas anderes als die Empfehlung — genau der Fehler, den sharp_gate.py für
die Wallets beseitigt hat.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_FILE = "killer.json"

# ── Schwellen: gespiegelt, nicht nachgebaut ─────────────────────────────────────────────
try:
    from betfair_track_record import CONC_THRESHOLD, INFLOW_MIN_EUR
except Exception:                       # pragma: no cover — nur falls das Modul fehlt
    CONC_THRESHOLD, INFLOW_MIN_EUR = 0.65, 2000

MARKT = "Match Odds"        # die gemessene Fläche (+12,9% n=81); andere Märkte sind dünner belegt
MIN_QUOTE = 1.30            # darunter zahlt keine Kante die Varianz
MAX_QUOTE = 15.0            # darüber ist es eine Lotterie, kein Geld-Signal
POLY_MIN_ANTEIL = 60        # „Poly Geld oben" — Anteil in Prozent
PINN_MIN_MOVE_PP = 1.0      # Verstärker: ab so viel pp gilt die Pinnacle-Bewegung als Bewegung

SEITE = {"H": "home", "D": "draw", "A": "away"}


def _load(name, default=None):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def _now():
    return datetime.now(timezone.utc)


def _ts(x):
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None


# ── Das Tor ─────────────────────────────────────────────────────────────────────────────
def kern_ok(sig) -> bool:
    """Die drei gemessenen Bedingungen. Fehlt eine Angabe, ist das kein Ja."""
    if not isinstance(sig, dict):
        return False
    odd = sig.get("odd")
    if not isinstance(odd, (int, float)) or not (MIN_QUOTE <= odd <= MAX_QUOTE):
        return False
    return bool(sig.get("conc")) and bool(sig.get("inflow")) and sig.get("dir") == "in"


def _track_urteil(track, league, market):
    """Liga × Markt aus dem Track — dieselben Schwellen wie im Radar und auf der Übersicht."""
    d = ((track or {}).get("byLeagueMarket") or {}).get("%s|%s" % (league, market))
    if not isinstance(d, dict) or (d.get("n") or 0) < 15 or d.get("roi") is None:
        return None
    roi = d["roi"]
    return {"n": d["n"], "roi": round(roi, 4),
            "traegt": roi >= 0.05, "verliert": roi <= -0.10}


def _streak(streaks, team):
    """Serie/Form — liegt nur für die Top-5 + MLS vor. Fehlt sie, ist das kein Minus."""
    for s in ((streaks or {}).get("streaks") or []):
        if str(s.get("team") or "").lower() != str(team or "").lower():
            continue
        fort = s.get("continuation") or {}
        if fort.get("state") != "intakt":
            continue
        return {"art": s.get("market"), "laenge": s.get("length"),
                "quote": fort.get("ratePct"), "liga": s.get("leagueName")}
    return None


def zeile(mid, eintrag, sig, cons_game, track, streaks):
    """Eine Kandidaten-Zeile bauen. Reines Zusammensetzen, keine Entscheidung."""
    fav = sig.get("fav")
    seite = SEITE.get(fav)
    home, away = eintrag.get("home"), eintrag.get("away")
    name = {"home": home, "draw": "Remis", "away": away}.get(seite)
    liga = eintrag.get("league")
    g = cons_game or {}
    poly = g.get("poly") or {}
    pinn = g.get("pinn") or {}
    pm = g.get("pinnMove") or {}

    # Poly zählt nur, wenn es DIESELBE Seite meint. Die Konsens-Zeile hat das schon geprüft
    # (verdict konsens/teil = Anker und Geld sehen dieselbe Seite vorn); zusätzlich muss die
    # Betfair-Geld-Seite dieselbe sein wie die, auf der unser Signal steht.
    poly_gleich = bool(poly) and g.get("moneySide") == seite and (poly.get("sharePct") or 0) >= POLY_MIN_ANTEIL
    pinn_gleich = bool(pinn) and pinn.get("fav") == seite

    verst = []
    if poly_gleich:
        verst.append({"art": "poly", "text": "Poly %d%%" % round(poly.get("sharePct") or 0),
                      "gewicht": 12})
    if pinn_gleich:
        verst.append({"art": "pinn", "text": "Pinnacle stimmt zu", "gewicht": 10})
    if pm.get("move") and (pm.get("movePP") or 0) >= PINN_MIN_MOVE_PP:
        verst.append({"art": "pinnMove",
                      "text": "Pinnacle zieht mit +%.1fpp" % pm["movePP"],
                      "gewicht": 14 if pm.get("laeuft") else 8})
    tr = _track_urteil(track, liga, MARKT)
    if tr and tr["traegt"]:
        verst.append({"art": "track", "text": "Liga trägt (%+d%% · n%d)" % (round(tr["roi"] * 100), tr["n"]),
                      "gewicht": 10})
    st = _streak(streaks, name) if seite in ("home", "away") else None
    if st:
        verst.append({"art": "streak",
                      "text": "%s ×%s" % (st.get("art") or "Serie", st.get("laenge")),
                      "gewicht": 8})

    # Rang: das Tor ist bestanden (Grundwert), darüber zählen die Verstärker. Der Geldanteil
    # geht bewusst nur schwach ein — 90% Anteil ist meist ein Favorit, kein Vorteil.
    rang = 50 + sum(v["gewicht"] for v in verst) + min(10, (sig.get("share") or 0) * 10)

    return {
        "matchId": str(mid), "home": home, "away": away, "league": liga,
        "kickoff": eintrag.get("kickoff"), "markt": MARKT,
        "seite": seite, "name": name, "odd": sig.get("odd"), "entryOdd": sig.get("entryOdd"),
        "anteilPct": round((sig.get("share") or 0) * 100),
        "stufe": 1 if (poly_gleich and pinn_gleich) else 2,
        "verstaerker": verst, "rang": round(rang, 1),
        "track": tr, "streak": st,
        "poly": ({"anteilPct": round(poly.get("sharePct") or 0), "usd": poly.get("vol"),
                  "odd": poly.get("odd")} if poly_gleich else None),
        "pinnMovePP": pm.get("movePP"),
        # nur mitschreiben, nicht filtern — s. Kopf, Punkt 4
        "wertVsPinn": (round(sig["pinnFair"] * sig["odd"] - 1, 4)
                       if isinstance(sig.get("pinnFair"), (int, float)) and sig.get("odd") else None),
    }


def baue(state=None, consensus=None, track=None, streaks=None, now=None) -> dict:
    now = now or _now()
    state = state if state is not None else _load("betfair_track_state.json")
    cons = consensus if consensus is not None else _load("betfair_consensus.json")
    track = track if track is not None else _load("betfair_track_record.json")
    if streaks is None:
        streaks = {"streaks": (_load("liga_streaks.json").get("streaks") or [])
                   + (_load("mls_streaks.json").get("streaks") or [])}

    spiele = {str(g.get("matchId")): g for g in ((cons or {}).get("games") or [])}
    zeilen = []
    for mid, e in ((state or {}).get("pending") or {}).items():
        sig = (e.get("signals") or {}).get(MARKT)
        if not kern_ok(sig):
            continue
        ko = _ts(e.get("kickoff"))
        if ko and ko <= now:
            continue                       # angepfiffen: der Track erfasst nur vor Anpfiff
        z = zeile(mid, e, sig, spiele.get(str(mid)), track, streaks)
        tr = z.get("track")
        if tr and tr["verliert"]:
            continue                       # belegt verlierender Eimer gehört nicht in eine Empfehlung
        zeilen.append(z)

    zeilen.sort(key=lambda r: (r["stufe"], -r["rang"]))
    return {
        "generatedAt": now.isoformat(),
        "stufe1": [z for z in zeilen if z["stufe"] == 1],
        "stufe2": [z for z in zeilen if z["stufe"] == 2],
        "regeln": {
            "markt": MARKT, "minAnteil": CONC_THRESHOLD, "minZuflussEur": INFLOW_MIN_EUR,
            "quote": [MIN_QUOTE, MAX_QUOTE], "polyMinAnteilPct": POLY_MIN_ANTEIL,
            "text": "Stufe 2 = Geldanteil ≥%d%% UND frischer Zufluss ≥€%d UND Quote zieht mit. "
                    "Stufe 1 = zusätzlich Poly-Geld ≥%d%% und Pinnacle-Favorit auf derselben Seite."
                    % (round(CONC_THRESHOLD * 100), INFLOW_MIN_EUR, POLY_MIN_ANTEIL),
        },
    }


# ── Freigabe-Schublade: rechnet sich aus DEMSELBEN Ledger, das die Zeilen abrechnet ──────
def schublade(results=None):
    """ROI und CLV je Zeile für die Konjunktion — Rohwerte, damit freigabe.bewerte urteilen kann.

    Der grosse Unterschied zu den bisherigen Betfair-Schubladen: die rechnen auf Aggregaten
    (byLeagueMarket) und kommen deshalb nie über „geprueft" hinaus, weil dort kein CLV je
    Signal steht. Hier liegen die Rohzeilen vor — inklusive clvBf. Damit kann diese Schublade
    tatsächlich freigegeben werden, statt es nur zu behaupten."""
    rows = results if results is not None else _load("betfair_track_results.json", [])
    renditen, clvs, letzter = [], [], None
    for r in (rows or []):
        if r.get("market") != MARKT:
            continue
        if not (r.get("conc") and r.get("inflow") and r.get("dir") == "in"):
            continue
        odd = r.get("odd")               # Closing-Quote: Signal und Preis im selben Moment
        if not isinstance(odd, (int, float)) or odd <= 1:
            continue
        if not (MIN_QUOTE <= odd <= MAX_QUOTE):
            continue
        renditen.append((odd - 1.0) if r.get("win") else -1.0)
        if isinstance(r.get("clvBf"), (int, float)):
            clvs.append(r["clvBf"])
        s = r.get("settledAt")
        if s and (letzter is None or s > letzter):
            letzter = s
    return {"renditen": renditen, "clvs": clvs, "letzter": letzter}


def main():
    out = baue()
    (BASE / OUT_FILE).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("killer: Stufe1=%d Stufe2=%d" % (len(out["stufe1"]), len(out["stufe2"])))


if __name__ == "__main__":
    main()
