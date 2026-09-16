#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
poly_konvergenz.py — Zieht Polymarket nach, wenn Pinnacle sich bewegt hat? (16.09.2026, Lucas)

## Die Frage

Lucas: „Ich seh die offenen 3 Trades auf Poly, die getriggert wurden, weil Pinnacle bewegt und
Poly scheinbar nicht. Alle 3 Positionen ca 5 % im Minus. Koennen wir rueckwirkend auslesen, ob
Poly ueberhaupt zu unseren Gunsten anpasst, wenn sowas passiert? Weil eventuell machen die das
nie und ist nur unsere Theorie."

Genau die richtige Frage, und sie war bis heute unbeantwortet. Der Auto-Trader setzt darauf,
dass Poly der Pinnacle-Fair hinterherlaeuft — gemessen hatte das niemand. `poly_markout.py`
misst etwas anderes (Adverse Selection beim Making), `analyze_poly_pinnacle_lag.py` misst die
Kreuzkorrelation der Bewegungen und laeuft in keinem Workflow. Die BEDINGTE Frage — nachdem
sich eine Kante geoeffnet hat, schliesst sie sich, und WER schliesst sie — stand nirgends.

## Wie gemessen wird

`{ds}-poly-history.json` fuehrt je Spiel eine Reihe von Snapshots mit `poly_<ausgang>` und
`edge_<ausgang>` (= (fair − poly) * 100, fair aus den de-viggten Pinnacle-Quoten). Damit laesst
sich beides rekonstruieren: unser Preis und die scharfe Referenz zum selben Zeitpunkt.

Einheit ist der ERSTE Trigger je Spiel und Ausgang, gemessen bis zum LETZTEN Kurs vor Anpfiff —
also genau das, was ein Trade tut: einmal einsteigen, halten. Mehrere Snapshots desselben Spiels
sind nicht unabhaengig; die Untergrenze kommt deshalb aus einem Cluster-Bootstrap ueber SPIELE,
nicht ueber Beobachtungen. Ueber Beobachtungen gerechnet waere sie rund doppelt so eng und
damit gelogen.

## Drei Arme, und der dritte ist der wichtigste

  · `dafuer`  — Kante >= Schwelle: bewegt sich Poly nach OBEN (zu uns)?
  · `dagegen` — Kante <= −Schwelle: bewegt sich Poly nach UNTEN? Der Spiegel. Ein einseitiges
    Ergebnis waere auch mit einem simplen Aufwaertsdrift der Preise vereinbar.
  · `neutral` — |Kante| < 1pp: hier MUSS null herauskommen. Tut es das nicht, misst die Rechnung
    einen Drift der Reihe selbst und nicht die Konvergenz. Der Arm ist die Kontrollgruppe,
    ohne die der Befund eine Behauptung waere (dieselbe Rolle wie die Kontrollmaerkte in
    `fade_unter.py`).

Zusaetzlich wird getrennt, WER die Luecke schliesst: `polyAnteil` ist der Teil der Schliessung,
der auf Polys Bewegung entfaellt — der Rest ist Pinnacle, das zurueckkommt. Eine Luecke, die
sich nur schliesst, weil die scharfe Seite ihren Irrtum einraeumt, ist fuer uns wertlos.

⚠️ Der Snapshot-Preis ist ein Mid. Wir kaufen den Ask, also rund einen halben Spread darueber
(in den echten Fills 1–2pp). Die gemessene Bewegung ist BRUTTO — was uebrig bleibt, steht im
Feld `nettoPP` und ist die einzige Zahl, die etwas ueber Geld sagt.

Kein Ausfuehrungs-Skript. Liest `{ds}-poly-history.json` + `{ds}-data.json`,
schreibt `{ds}_poly_konvergenz.json`. Setzt und sendet nichts.
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).resolve().parent

# Die Schwelle kommt aus derselben Config wie der Trigger — eine zweite Zahl hier waere die
# Drift, die dieses Repo sonst ueberall bekaempft.
try:
    from cocobet_config import CONFIG as _CFG
except Exception:                                            # pragma: no cover
    _CFG = {}


def _cfg(section: str, key: str, default):
    if isinstance(_CFG, dict):
        return _CFG.get(section, {}).get(key, default)
    return default


SCHWELLE_PP   = float(_cfg("trade", "auto_trigger_edge_pp", 4.0))
NEUTRAL_PP    = 1.0      # |Kante| darunter = Kontrollgruppe
MIN_H_VOR_ANPFIFF = float(_cfg("trade", "min_hours_before_match", 4))
SPREAD_PP     = 1.5      # halber Spread, konservativ — s. Kopf
MIN_SPIELE    = 20       # darunter gibt es keine Untergrenze, nur einen Schnitt
AUSGAENGE     = ("hw", "dr", "aw", "o25", "u25")
BOOT          = 1500
SAAT          = 7


def _ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def anpfiffe(daten: dict) -> dict:
    """Spiel-Schluessel -> Anpfiff. Der Schnitt am Anpfiff ist Pflicht: danach bewegen sich
    beide Reihen wegen der Tore, nicht wegen Information."""
    out = {}
    for _gk, g in ((daten or {}).get("groups") or {}).items():
        for fx in (g.get("fixtures") or []):
            k = "%s-%s" % (fx.get("home"), fx.get("away"))
            t = _ts(fx.get("kickoff"))
            if t is not None:
                out[k] = t
    return out


def _punkt(snap: dict, ausgang: str):
    """(poly, fair, kante) oder None. 0/1-Preise sind Platzhalter, kein Markt."""
    p = snap.get("poly_" + ausgang)
    e = snap.get("edge_" + ausgang)
    if not isinstance(p, (int, float)) or not isinstance(e, (int, float)):
        return None
    if isinstance(p, bool) or p <= 0.02 or p >= 0.98:
        return None
    return float(p), float(p) + float(e) / 100.0, float(e)


def beobachtungen(hist: dict, anpf: dict, schwelle=None, neutral=None,
                  min_h=None) -> list:
    """Eine Zeile je Spiel+Ausgang und Arm: der ERSTE Trigger, gemessen bis zum letzten Kurs
    vor Anpfiff. REIN.

    Kein Spiel darf mehrfach in denselben Arm fallen — sonst zaehlt ein Spiel mit vielen
    Snapshots so viel wie zwanzig Spiele.
    """
    schwelle = SCHWELLE_PP if schwelle is None else schwelle
    neutral = NEUTRAL_PP if neutral is None else neutral
    min_h = MIN_H_VOR_ANPFIFF if min_h is None else min_h
    aus = []
    for key, snaps in (hist or {}).items():
        ko = anpf.get(key)
        rows = []
        for s in (snaps or []):
            t = _ts(s.get("ts"))
            if t is None or (ko is not None and t >= ko):
                continue
            rows.append((t, s))
        rows.sort(key=lambda z: z[0])
        if len(rows) < 3:
            continue
        for o in AUSGAENGE:
            serie = [(t, _punkt(s, o)) for t, s in rows]
            serie = [(t, v) for t, v in serie if v is not None]
            if len(serie) < 3:
                continue
            letzter_p, letzter_f = serie[-1][1][0], serie[-1][1][1]
            gesehen = set()
            for t, (p, f, e) in serie:
                if ko is not None and (ko - t).total_seconds() / 3600.0 < min_h:
                    continue
                arm = ("dafuer" if e >= schwelle else
                       "dagegen" if e <= -schwelle else
                       "neutral" if abs(e) < neutral else None)
                if arm is None or arm in gesehen:
                    continue
                gesehen.add(arm)
                aus.append({"spiel": key, "ausgang": o, "arm": arm,
                            "kantePP": round(e, 2),
                            "polyPP": round(100.0 * (letzter_p - p), 2),
                            "fairPP": round(100.0 * (letzter_f - f), 2)})
    return aus


def _ug(paare, saat=SAAT, p=5):
    """Einseitige Untergrenze per Cluster-Bootstrap ueber SPIELE. `paare` = [(spiel, wert)].

    Ueber die Beobachtungen gezogen waere die Untergrenze rund doppelt so eng — Snapshots
    desselben Spiels tragen dieselbe Information, und ein Bootstrap, der das ignoriert,
    verwechselt Wiederholung mit Beleg.
    """
    je = defaultdict(list)
    for k, v in paare:
        je[k].append(v)
    keys = list(je)
    if len(keys) < MIN_SPIELE:
        return None
    r = random.Random(saat)
    zieh = []
    for _ in range(BOOT):
        pick = r.choices(keys, k=len(keys))
        werte = [x for k in pick for x in je[k]]
        zieh.append(statistics.fmean(werte))
    zieh.sort()
    return zieh[int(p / 100.0 * len(zieh))]


def _arm(zeilen: list, richtung: float) -> dict:
    """Ein Arm zusammengefasst. `richtung` dreht das Vorzeichen, damit „zu uns" in beiden
    Armen positiv heisst und die zwei Zahlen vergleichbar sind."""
    if not zeilen:
        return {"n": 0, "spiele": 0, "polyPP": None, "polyUgPP": None, "fairPP": None,
                "medianPP": None, "gegenUnsPct": None, "kantePP": None, "polyAnteil": None}
    poly = [richtung * z["polyPP"] for z in zeilen]
    fair = [richtung * z["fairPP"] for z in zeilen]
    kante = [abs(z["kantePP"]) for z in zeilen]
    # Wie viel der Luecke hat sich geschlossen, und welcher Teil davon ging auf Polys Konto?
    # Die Luecke schliesst sich um (Poly rauf) + (Fair runter) = poly − fair in unserer Richtung.
    schliessung = statistics.fmean(poly) - statistics.fmean(fair)
    anteil = (statistics.fmean(poly) / schliessung) if abs(schliessung) > 1e-9 else None
    return {"n": len(zeilen), "spiele": len({z["spiel"] for z in zeilen}),
            "polyPP": round(statistics.fmean(poly), 2),
            "polyUgPP": (lambda u: None if u is None else round(u, 2))(
                _ug([(z["spiel"], richtung * z["polyPP"]) for z in zeilen])),
            "medianPP": round(statistics.median(poly), 2),
            "fairPP": round(statistics.fmean(fair), 2),
            "kantePP": round(statistics.fmean(kante), 2),
            "gegenUnsPct": round(100.0 * sum(1 for x in poly if x < 0) / len(poly), 1),
            "polyAnteil": None if anteil is None else round(max(0.0, min(1.0, anteil)), 2)}


def urteil(arme: dict, neutral_grenze=0.5) -> tuple:
    """Das Urteil faellt HIER, nicht in der Oberflaeche.

    Drei Bedingungen, und die dritte ist die, an der ein Scheinbefund scheitert:
      1. der Trigger-Arm hat eine Untergrenze ueber null,
      2. der Spiegel-Arm zeigt in dieselbe Richtung (Poly faellt, wenn die Kante negativ ist),
      3. die Kontrollgruppe liegt flach — sonst misst die Rechnung einen Drift der Reihe.
    """
    d, g, n = arme.get("dafuer") or {}, arme.get("dagegen") or {}, arme.get("neutral") or {}
    if not d.get("n") or d.get("polyUgPP") is None:
        return "zu wenig Daten", ("weniger als %d Spiele mit einer Kante ab %.1f pp — darueber "
                                  "laesst sich nichts sagen" % (MIN_SPIELE, SCHWELLE_PP))
    if n.get("polyPP") is not None and abs(n["polyPP"]) > neutral_grenze:
        return "Kontrolle unsauber", ("die Kontrollgruppe (|Kante| < %.1f pp) bewegt sich um "
                                      "%+.2f pp — gemessen wird dann ein Drift der Reihe, nicht "
                                      "die Konvergenz" % (NEUTRAL_PP, n["polyPP"]))
    if d["polyUgPP"] <= 0:
        return "kein Beleg", ("Poly laeuft im Schnitt %+.2f pp mit, aber die Untergrenze liegt "
                              "bei %+.2f pp — das schliesst die Null nicht aus"
                              % (d["polyPP"], d["polyUgPP"]))
    if g.get("n") and g.get("polyPP") is not None and g["polyPP"] <= 0:
        return "nur einseitig", ("Poly zieht nach, wenn die Kante FUER uns steht (%+.2f pp), "
                                 "nicht aber im Spiegelfall (%+.2f pp) — ein einseitiges "
                                 "Ergebnis ist auch mit einem blossen Aufwaertsdrift vereinbar"
                                 % (d["polyPP"], g["polyPP"]))
    return "zieht nach", ("Poly laeuft bis zum Anpfiff %+.2f pp mit (Untergrenze %+.2f pp, "
                          "%d Spiele), im Spiegelfall %+.2f pp, Kontrollgruppe %+.2f pp"
                          % (d["polyPP"], d["polyUgPP"], d["spiele"], (g or {}).get("polyPP") or 0.0,
                             (n or {}).get("polyPP") or 0.0))


def bericht(hist: dict, daten: dict, now=None) -> dict:
    zeilen = beobachtungen(hist, anpfiffe(daten))
    arme = {"dafuer": _arm([z for z in zeilen if z["arm"] == "dafuer"], 1.0),
            "dagegen": _arm([z for z in zeilen if z["arm"] == "dagegen"], -1.0),
            "neutral": _arm([z for z in zeilen if z["arm"] == "neutral"], 1.0)}
    u, grund = urteil(arme)
    d = arme["dafuer"]
    netto = None if d.get("polyPP") is None else round(d["polyPP"] - SPREAD_PP, 2)
    return {
        "dataset": D.active_dataset(),
        "generatedAt": (now or datetime.now(tz=None).astimezone()).isoformat(),
        "schwellePP": SCHWELLE_PP,
        "neutralPP": NEUTRAL_PP,
        "spreadPP": SPREAD_PP,
        "minSpiele": MIN_SPIELE,
        "arme": arme,
        # Brutto ist die Bewegung des Mids, netto zieht den halben Spread ab, den wir beim
        # Einstieg zahlen. Nur die zweite Zahl sagt etwas ueber Geld.
        "nettoPP": netto,
        "belegt": u == "zieht nach",
        "urteil": u,
        "grund": grund,
    }


def main() -> int:
    hist = _load(D.file("wm2026-poly-history.json", "liga-poly-history.json").name)
    daten = _load(D.data_file().name)
    if not hist:
        print("ℹ️  Keine Poly-Historie — nichts zu messen")
        return 0
    rep = bericht(hist, daten)
    out = D.file("wm_poly_konvergenz.json", "liga_poly_konvergenz.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("=== Zieht Poly nach? (%s) — Kante ab %.1f pp, bis Anpfiff ===" % (
        rep["dataset"].upper(), rep["schwellePP"]))
    print("%-10s %6s %7s %11s %11s %11s %11s" % (
        "Arm", "n", "Spiele", "Δ Poly", "Untergrenze", "Δ Fair", "gegen uns"))
    for name in ("dafuer", "dagegen", "neutral"):
        a = rep["arme"][name]
        if not a["n"]:
            continue
        print("%-10s %6d %7d %+10.2f %+11s %+10.2f %10s" % (
            name, a["n"], a["spiele"], a["polyPP"],
            ("%.2f" % a["polyUgPP"]) if a["polyUgPP"] is not None else "—",
            a["fairPP"], ("%.0f %%" % a["gegenUnsPct"])))
    d = rep["arme"]["dafuer"]
    if d["polyAnteil"] is not None:
        print("\nVon der geschlossenen Luecke gehen %.0f %% auf Polys Bewegung, der Rest auf "
              "zurueckkommende Pinnacle-Quoten." % (100 * d["polyAnteil"]))
    print("Netto nach halbem Spread (%.1f pp): %s pp  →  %s" % (
        rep["spreadPP"], rep["nettoPP"], rep["urteil"]))
    print("   %s" % rep["grund"])
    print("💾 %s" % out.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
