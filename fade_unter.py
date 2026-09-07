"""Fade-Unter: die Gegenseite spielen, wenn das Betfair-Geld auf dem UNTER liegt.

06.09.2026, Lucas: „wenn wir sehen, dass die gespielten Sachen schlecht liefen, dann könnte man
das ja auch ins Positive umkehren und faden … könnten wir das mal durchdenken."

Durchgerechnet auf 15.945 abgerechneten Zeilen, in einer Such- und einer getrennten Prüfhälfte.
Von 16 Markt×Seite-Schnitten waren genau zwei in BEIDEN Hälften positiv, und beide sind
derselbe Typ — die Ganzspiel-Torlinien, wenn das Geld auf UNTER liegt:

    n = 2.720   (987 × Ü/U 2,5  ·  1.733 × Ü/U 3,5)
    Geldseite trifft 59,2 %, implizit erwartet 62,4 %          →  −3,2 pp
    Fade nach 5 % Kommission:  Suche +5,5 %  ·  Prüfung +5,2 %  ·  gepoolt +5,3 % (UG +0,9 %)

Warum das kein Zufallsfund ist — die Kontrolle auf Märkten, wo die Regel nicht greifen sollte:

    Match Odds H                Geldseite +1,0 pp BESSER als implizit  →  Fade  −5,6 %
    Both teams to Score? YES               +1,8 pp besser              →  Fade  −6,8 %
    First Half Goals 1.5 UNDER             +1,3 pp besser              →  Fade  −7,8 %

Wo das Geld recht hat, verliert derselbe Fade korrekt. Die Preis-Rekonstruktion erzeugt also
keine Kante aus dem Nichts.

⚠️ WAS DAGEGEN SPRICHT — steht hier, damit es niemand überliest:
  · Der Gegenpreis war im Altbestand NICHT erhoben. Für die Rückrechnung musste er aus einem
    angenommenen Overround rekonstruiert werden. Das Ergebnis hält bis ~1 % Overround und stirbt
    bei 2 %. Gemessen sind 0,3 % Median — aber gemessen am LIVE-Schnappschuss, nicht je Zeile.
    Seit heute schreibt `betfair_track_record.gegenseite()` den echten Preis mit; ab dann wird
    gemessen statt geschätzt. Beide Rechnungen stehen getrennt im Artefakt (`echt` / `rekon`).
  · Liquidität. Faden heißt per Konstruktion die unbeliebtere Seite nehmen. Im Live-Schnappschuss
    trug eine Gegenseite €5, eine andere €3.691. Deshalb wandert `gegenVol` mit und deshalb gibt
    es die Untermenge `mitGeld`.
  · 12 Tage Datenbasis (26.08.–06.09.) und ein nachträglich gepoolter Schnitt aus 16.

Deshalb ist das hier eine VORREGISTRIERTE Schublade und kein Tipp: die Regel steht fest, bevor
die Daten kommen. Was ab dem 07.09. dazukommt, ist sauber out-of-sample — und nur das zählt.
"""
from __future__ import annotations

import json
import math
import statistics as st
from datetime import datetime, timezone
from pathlib import Path

import betfair_track_store as _store

BASE = Path(__file__).resolve().parent
OUT_FILE = "fade_unter.json"

# ── Die Regel. Steht fest, seit 07.09.2026. Änderungen daran starten die Messung neu. ──────
MAERKTE = frozenset({"Over/Under 2.5 Goals", "Over/Under 3.5 Goals"})
GELD_SEITE = "UNDER"          # wir spielen die ANDERE Seite
VORREG_AB = "2026-09-07"
Z = 1.645                     # einseitige 95%-Grenze
UG_MIN_N = 30                 # darunter gibt es keine Untergrenze, nur einen Punktschätzer
KOMMISSION = 0.05             # Betfair-Standard auf Nettogewinn
OVERROUND_ANNAHME = 0.003     # nur für die Rückrechnung; gemessener Median am 06.09.
MIN_GEGEN_VOL = 200.0         # ab hier gilt eine Gegenseite als bespielbar


def gilt(zeile) -> bool:
    """Trifft die Regel auf diese Zeile zu? REIN/testbar."""
    return (isinstance(zeile, dict)
            and zeile.get("market") in MAERKTE
            and zeile.get("fav") == GELD_SEITE)


def fade_rendite(zeile, kommission: float = KOMMISSION, overround: float = OVERROUND_ANNAHME):
    """Rendite je Einsatz beim Spielen der Gegenseite → (wert, quelle) oder (None, grund).

    `quelle` ist "echt", wenn der Gegenpreis erhoben wurde, sonst "rekon". Die beiden werden
    NIE vermischt: eine rekonstruierte Zahl ist ein Modell, eine erhobene eine Messung.
    """
    if zeile.get("win") is None:
        return None, "nicht abgerechnet"
    g = zeile.get("entryGegenOdd") or zeile.get("gegenOdd")
    quelle = "echt"
    if not isinstance(g, (int, float)) or g <= 1.0:
        o = zeile.get("entryOdd") or zeile.get("odd")
        if not isinstance(o, (int, float)) or o <= 1.0:
            return None, "kein Preis"
        inv = (1.0 + overround) - 1.0 / o
        if inv <= 0.02:
            return None, "Gegenseite nicht handelbar"
        g, quelle = 1.0 / inv, "rekon"
    # Das Geld lag auf UNTER: kam UNTER (win=True), verliert unser Über.
    return (-1.0 if zeile["win"] else (g - 1.0) * (1.0 - kommission)), quelle


def untergrenze(werte):
    """Einseitige 95%-Untergrenze. None unter UG_MIN_N — ein Punktschätzer ist kein Beleg."""
    xs = [float(x) for x in (werte or []) if isinstance(x, (int, float))]
    if len(xs) < UG_MIN_N:
        return None
    m = sum(xs) / len(xs)
    return m - Z * st.stdev(xs) / math.sqrt(len(xs))


def _menge(zeilen, kommission=KOMMISSION):
    """Eine Menge Zeilen → Kennzahlen. Punktschätzer UND Schranke, nie nur einer von beiden."""
    paare = [fade_rendite(z, kommission) for z in zeilen]
    werte = [w for w, _ in paare if w is not None]
    n = len(werte)
    if n == 0:
        return {"n": 0, "roi": None, "roiUg": None, "belegt": False, "treffer": None,
                "implizit": None, "vorsprungPP": None, "echtAnteil": None}
    echt = sum(1 for w, q in paare if w is not None and q == "echt")
    # Trefferquote der GELDSEITE gegen ihre eigene implizite Wahrscheinlichkeit — das ist die
    # Größe, aus der die Kante kommt. Eine Trefferquote ohne die Quoten wäre keine Zahl.
    mit_odd = [z for z in zeilen if isinstance(z.get("entryOdd") or z.get("odd"), (int, float))]
    tref = imp = None
    if mit_odd:
        tref = 100.0 * sum(1 for z in mit_odd if z.get("win")) / len(mit_odd)
        imp = 100.0 * sum(1.0 / (z.get("entryOdd") or z["odd"]) for z in mit_odd) / len(mit_odd)
    ug = untergrenze(werte)
    return {"n": n, "roi": round(sum(werte) / n, 4),
            "roiUg": round(ug, 4) if ug is not None else None,
            "belegt": bool(ug is not None and ug > 0),
            "treffer": round(tref, 1) if tref is not None else None,
            "implizit": round(imp, 1) if imp is not None else None,
            "vorsprungPP": round(tref - imp, 1) if (tref is not None and imp is not None) else None,
            "echtAnteil": round(echt / n, 3)}


def bilanz(zeilen=None) -> dict:
    """Der Papier-Stand der Regel. `vorreg` ist der einzige Teil, der wirklich zählt."""
    if zeilen is None:
        zeilen = _store.load(str(BASE / "betfair_track_results.json"))
    treffer = [z for z in (zeilen or []) if gilt(z)]
    vor = [z for z in treffer if (z.get("settledAt") or "") < VORREG_AB]
    nach = [z for z in treffer if (z.get("settledAt") or "") >= VORREG_AB]
    mitgeld = [z for z in nach
               if isinstance(z.get("gegenVol"), (int, float)) and z["gegenVol"] >= MIN_GEGEN_VOL]
    return {
        "regel": {"maerkte": sorted(MAERKTE), "geldSeite": GELD_SEITE,
                  "wirSpielen": "OVER", "abDatum": VORREG_AB,
                  "kommissionPct": round(100 * KOMMISSION, 1),
                  "minGegenVol": MIN_GEGEN_VOL,
                  "text": ("Liegt das meiste gematchte Betfair-Geld auf dem UNTER einer "
                           "Ganzspiel-Torlinie, spielen wir stattdessen das ÜBER.")},
        "rueckblick": _menge(vor),      # Rückrechnung — Gegenpreis überwiegend rekonstruiert
        "vorreg": _menge(nach),         # ab der Vorregistrierung — das ist der Beleg
        "mitGeld": _menge(mitgeld),     # nur wo die Gegenseite auch Volumen trug
        "kontrolle": _kontrolle(zeilen),
    }


def _kontrolle(zeilen) -> list:
    """Dieselbe Rechnung auf Märkten, wo sie NICHT gelten soll. Ein Befund ohne Kontrollgruppe
    ist eine Behauptung — schlägt sie hier auch an, misst die Konstruktion sich selbst."""
    raus = []
    for markt, seite in (("Match Odds", "H"), ("Both teams to Score?", "YES"),
                         ("First Half Goals 1.5", "UNDER")):
        sel = [z for z in (zeilen or []) if z.get("market") == markt and z.get("fav") == seite]
        if len(sel) < UG_MIN_N:
            continue
        m = _menge(sel)
        raus.append({"markt": markt, "seite": seite, "n": m["n"], "roi": m["roi"],
                     "roiUg": m["roiUg"], "vorsprungPP": m["vorsprungPP"]})
    return raus


def offen(prices=None) -> list:
    """Welche Spiele erfüllen die Regel GERADE? Aus dem Live-Schnappschuss, damit Lucas
    mitschauen kann statt nur die Bilanz zu sehen."""
    if prices is None:
        p = BASE / "betfair_prices.json"
        prices = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    import betfair_track_record as B
    raus = []
    for m in (prices.get("matches") or []):
        if (m.get("liveInfo") or {}).get("finished"):
            continue
        for mkid in sorted(MAERKTE):
            mk = (m.get("markets") or {}).get(mkid)
            if not mk:
                continue
            lead = B._lead(mk)
            if not lead:
                continue
            if B.fav_token(mkid, lead.get("name"), m.get("home"), m.get("away")) != GELD_SEITE:
                continue
            g = B.gegenseite(mk, lead)
            if not g or not isinstance(g.get("odd"), (int, float)):
                continue
            tot = B._mkt_total(mk) or 0
            raus.append({
                "matchId": str(m.get("matchId")), "home": m.get("home"), "away": m.get("away"),
                "league": m.get("league"), "kickoff": m.get("kickoff"), "markt": mkid,
                "geldAuf": lead.get("name"), "geldOdd": lead.get("odd"),
                "geldAnteilPct": (round(100 * (lead.get("vol") or 0) / tot) if tot else None),
                "spielen": g.get("name"), "spielenOdd": g.get("odd"), "spielenVol": g.get("vol"),
                "bespielbar": bool(isinstance(g.get("vol"), (int, float))
                                   and g["vol"] >= MIN_GEGEN_VOL),
            })
    raus.sort(key=lambda r: (not r["bespielbar"], r.get("kickoff") or ""))
    return raus


def baue(zeilen=None, prices=None) -> dict:
    d = bilanz(zeilen)
    d["offen"] = offen(prices)
    d["generatedAt"] = datetime.now(timezone.utc).isoformat()
    return d


def main() -> int:
    from safe_write import write_json_atomic
    d = baue()
    write_json_atomic(BASE / OUT_FILE, d, indent=1)
    r, v, g = d["rueckblick"], d["vorreg"], d["mitGeld"]
    print("=== fade_unter.py ===")
    print("  Regel: %s" % d["regel"]["text"])
    for lab, m in (("Rückblick (rekonstruiert)", r), ("seit Vorregistrierung", v), ("davon mit Geld", g)):
        print("  %-26s n=%4d  ROI %s  UG %s  Vorsprung Geldseite %s pp"
              % (lab, m["n"],
                 ("%+6.1f %%" % (100 * m["roi"])) if m["roi"] is not None else "   —   ",
                 ("%+6.1f %%" % (100 * m["roiUg"])) if m["roiUg"] is not None else "  kein Urteil",
                 m["vorsprungPP"]))
    print("  Kontrollmärkte (dort soll der Fade VERLIEREN):")
    for k in d["kontrolle"]:
        print("    %-24s %-6s n=%4d  ROI %+6.1f %%  Vorsprung %+4.1f pp"
              % (k["markt"][:24], k["seite"], k["n"], 100 * k["roi"], k["vorsprungPP"]))
    print("  gerade offen: %d Spiele (%d davon mit Geld auf der Gegenseite)"
          % (len(d["offen"]), sum(1 for o in d["offen"] if o["bespielbar"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
