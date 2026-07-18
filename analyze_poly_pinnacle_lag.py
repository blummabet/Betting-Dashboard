#!/usr/bin/env python3
"""
analyze_poly_pinnacle_lag.py — Wer bewegt sich zuerst: Polymarket oder Pinnacle? (18.07.2026, Lucas)

## Die Frage

Wir haben zwei unabhängige, dicht getaktete Preisreihen auf dasselbe Ereignis: Pinnacle (scharf,
de-viggt) und Polymarket (Crowd, echtes Geld). `lead_lag_bias` misst bereits Pinnacle gegen
Softbooks — Poly kam darin nie vor. Dabei ist genau das die interessante Reihe, weil Poly kein
Buchmacher ist, sondern eine Börse.

Beide möglichen Ergebnisse sind verwertbar:

  · **Poly führt** → wir hätten eine Frühwarnung, BEVOR unser Steam-Trigger auf Pinnacle feuert.
    Für MLS besonders plausibel: dort sitzt die US-Crowd näher an lokaler Information
    (Aufstellungs-Gerüchte, Beat-Reporter) als ein asiatischer Sharp-Book.
  · **Pinnacle führt** → bestätigt die bestehende These und sagt uns, WIE LANG das Lag-Fenster
    ist. Das setzt direkt unser Entry-Timing: aktuell steigen wir bei Trigger ein und aus 20min
    vor Anpfiff. Wenn das Fenster typisch 6h ist, ist „sofort" richtig; wenn 30min, verbrennen
    wir Zeit.

Das Skript entscheidet NICHT, ob daraus ein Signal wird — es misst nur. Ein Signal folgt erst,
wenn die Antwort stabil und stark genug ist.

## Methode

Für jedes Match und jedes 1X2-Outcome:
 1. Pinnacle-Quoten → de-viggte Wahrscheinlichkeit (sonst vergleichen wir Overround mit Preis).
 2. Beide Reihen auf ein gemeinsames Zeitraster (`GRID_MIN`) mit Forward-Fill.
 3. Differenzen je Rasterschritt — verglichen werden BEWEGUNGEN, nicht Niveaus. (Niveaus sind
    ohnehin hoch korreliert; das sagt nichts über Führung.)
 4. Kreuzkorrelation über Lags: `corr(Δpinn[t], Δpoly[t−k])`.
    k > 0 ⇒ Poly bewegte sich FRÜHER (Poly führt). k < 0 ⇒ Pinnacle führt.

## Zwei Fallen, die hier eingebaut abgefangen werden

  · **Platzhalter-Quoten.** Eröffnungen wie 1.04/1.01/1.04 (291 % Overround) haben schon einmal
    80pp-Fake-Steam erzeugt. Ungefiltert würden sie hier eine gewaltige Scheinkorrelation
    produzieren. → `odds_plausibility.plausible_1x2` auf JEDEN Snapshot.
  · **In-Play.** Nach Anpfiff bewegen sich beide Reihen wegen der Tore, nicht wegen Information.
    Das ist trivial korreliert und hätte mit unserer Frage nichts zu tun. → harter Schnitt am
    Anpfiff.

Lauf:  python3 analyze_poly_pinnacle_lag.py            (aktiver Datensatz)
       COCOBET_DATASET=mls python3 analyze_poly_pinnacle_lag.py
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cocobet_dataset as D
from odds_plausibility import plausible_1x2

BASE = Path(__file__).resolve().parent

GRID_MIN     = 60      # Rasterweite in Minuten
MAX_LAG      = 6       # ±6 Schritte = ±6h bei 60min-Raster
MIN_STEPS    = 6       # kürzere Reihen sind statistisch wertlos
MIN_MOVE     = 0.002   # Bewegungen < 0.2pp sind Rundung/Rauschen, keine Information
MIN_PAIRS    = 30      # unter so wenigen Paaren wird kein Lag ausgewiesen

OUTCOMES = (("hw", "poly_hw"), ("dr", "poly_dr"), ("aw", "poly_aw"))


def _ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _devig(hw, dr, aw):
    """Quoten → faire Wahrscheinlichkeiten. Ohne De-Vig vergleichen wir Buchmacher-Marge
    mit einem Börsenpreis — der Vergleich wäre systematisch verschoben."""
    try:
        a, b, c = 1.0 / float(hw), 1.0 / float(dr), 1.0 / float(aw)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    s = a + b + c
    if s <= 0:
        return None
    return {"hw": a / s, "dr": b / s, "aw": c / s}


def _grid(series, kickoff, key):
    """Reihe [(ts, wert)] → {rasterindex: wert} per Forward-Fill.

    Index 0 = Anpfiff, negative Indizes = davor. Nach Anpfiff wird hart abgeschnitten:
    In-Play-Bewegungen folgen Toren, nicht Information, und wären trivial korreliert."""
    out = {}
    for ts, val in sorted(series):
        if val is None or ts >= kickoff:
            continue
        idx = int((ts - kickoff).total_seconds() // (GRID_MIN * 60))
        out[idx] = val          # letzter Wert im Rasterfenster gewinnt
    if not out:
        return {}
    gefuellt, letzter = {}, None
    for i in range(min(out), max(out) + 1):
        if i in out:
            letzter = out[i]
        if letzter is not None:
            gefuellt[i] = letzter
    return gefuellt


def _deltas(grid):
    return {i: grid[i] - grid[i - 1] for i in sorted(grid) if (i - 1) in grid}


def _corr(paare):
    if len(paare) < MIN_PAIRS:
        return None
    xs = [p[0] for p in paare]
    ys = [p[1] for p in paare]
    try:
        return statistics.correlation(xs, ys)
    except statistics.StatisticsError:
        return None       # konstante Reihe → keine Korrelation definierbar


def collect_pairs(odds_hist: dict, poly_hist: dict, fixtures: dict) -> dict:
    """Sammelt je Lag die Delta-Paare über alle Matches/Outcomes. Rein, damit testbar."""
    pro_lag: dict[int, list] = {k: [] for k in range(-MAX_LAG, MAX_LAG + 1)}
    stats = {"matches": 0, "verworfenKeinKickoff": 0, "verworfenPlatzhalter": 0,
             "verworfenZuKurz": 0}

    for key, snaps in (odds_hist or {}).items():
        ko = _ts((fixtures or {}).get(key, {}).get("kickoff"))
        if ko is None:
            stats["verworfenKeinKickoff"] += 1
            continue
        psnaps = (poly_hist or {}).get(key) or []
        if not snaps or not psnaps:
            continue

        pinn_series = {o: [] for o, _ in OUTCOMES}
        for s in snaps:
            ts = _ts(s.get("ts"))
            if ts is None:
                continue
            hw, dr, aw = s.get("hw"), s.get("dr"), s.get("aw")
            if not (hw and dr and aw):
                continue
            if not plausible_1x2(hw, dr, aw):
                stats["verworfenPlatzhalter"] += 1
                continue          # 291%-Overround-Eröffnungen → sonst Scheinkorrelation
            fair = _devig(hw, dr, aw)
            if not fair:
                continue
            for o, _pk in OUTCOMES:
                pinn_series[o].append((ts, fair[o]))

        poly_series = {o: [] for o, _ in OUTCOMES}
        for s in psnaps:
            ts = _ts(s.get("ts"))
            if ts is None:
                continue
            for o, pk in OUTCOMES:
                v = s.get(pk)
                if v is not None:
                    poly_series[o].append((ts, float(v)))

        genutzt = False
        for o, _pk in OUTCOMES:
            gp = _grid(pinn_series[o], ko, o)
            gq = _grid(poly_series[o], ko, o)
            if len(gp) < MIN_STEPS or len(gq) < MIN_STEPS:
                stats["verworfenZuKurz"] += 1
                continue
            dp, dq = _deltas(gp), _deltas(gq)
            for lag in pro_lag:
                for i, v in dp.items():
                    w = dq.get(i - lag)
                    if w is None:
                        continue
                    # Beide Seiten müssen sich bewegt haben — zwei Nullen korrelieren perfekt
                    # und würden das Ergebnis Richtung "kein Lag" ziehen.
                    if abs(v) < MIN_MOVE and abs(w) < MIN_MOVE:
                        continue
                    pro_lag[lag].append((v, w))
                    genutzt = True
        if genutzt:
            stats["matches"] += 1

    return {"perLag": pro_lag, "stats": stats}


def analyze(odds_hist, poly_hist, fixtures) -> dict:
    roh = collect_pairs(odds_hist, poly_hist, fixtures)
    lags = []
    for lag, paare in sorted(roh["perLag"].items()):
        c = _corr(paare)
        lags.append({"lagStunden": lag * GRID_MIN / 60, "n": len(paare),
                     "korrelation": None if c is None else round(c, 4)})

    gueltig = [l for l in lags if l["korrelation"] is not None]
    best = max(gueltig, key=lambda l: l["korrelation"]) if gueltig else None
    null = next((l for l in lags if l["lagStunden"] == 0), None)

    befund = "zu wenig Daten"
    if best and null and null["korrelation"] is not None:
        # Ein Peak abseits 0 zählt nur, wenn er MERKLICH über dem Gleichstand liegt —
        # sonst ist es Rauschen und wir würden eine Führung hineinlesen, die es nicht gibt.
        vorsprung = best["korrelation"] - null["korrelation"]
        if best["lagStunden"] == 0 or vorsprung < 0.02:
            befund = "kein messbarer Vorlauf — beide Reihen bewegen sich gleichzeitig"
        elif best["lagStunden"] > 0:
            befund = (f"Polymarket führt um ~{best['lagStunden']:.0f}h "
                      f"(r={best['korrelation']:.3f} vs {null['korrelation']:.3f} bei Gleichstand)")
        else:
            befund = (f"Pinnacle führt um ~{abs(best['lagStunden']):.0f}h "
                      f"(r={best['korrelation']:.3f} vs {null['korrelation']:.3f} bei Gleichstand)")

    return {"dataset": D.active_dataset(), "gridMinuten": GRID_MIN,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "befund": befund, "lags": lags, "stats": roh["stats"]}


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fixtures_map(data: dict) -> dict:
    """matchKey → fixture. Deckt Gruppen UND koFixtures ab — KO-Spiele liegen NICHT in groups."""
    out = {}
    for g in (data.get("groups") or {}).values():
        for fx in (g.get("fixtures") or []):
            for k in (fx.get("key"), f"{fx.get('home')}-{fx.get('away')}"):
                if k:
                    out[k] = fx
    for fx in (data.get("koFixtures") or []):
        for k in (fx.get("key"), f"{fx.get('home')}-{fx.get('away')}"):
            if k:
                out[k] = fx
    return out


def main() -> int:
    odds = _load(D.file("wm2026-odds-history.json", "liga-odds-history.json").name)
    poly = _load(D.file("wm2026-poly-history.json", "liga-poly-history.json").name)
    data = _load(D.data_file().name)
    if not odds or not poly:
        print("ℹ️  Keine zwei Preisreihen vorhanden — nichts zu messen "
              f"(odds {len(odds)}, poly {len(poly)})")
        return 0

    rep = analyze(odds, poly, _fixtures_map(data))
    out = D.file("wm_poly_lag_report.json", "liga_poly_lag_report.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"=== Poly ↔ Pinnacle Lead-Lag ({rep['dataset'].upper()}) ===")
    print(f"Matches genutzt: {rep['stats']['matches']} · "
          f"Platzhalter-Snaps verworfen: {rep['stats']['verworfenPlatzhalter']}\n")
    print(f"{'Lag':>7}  {'n':>7}  Korrelation")
    for l in rep["lags"]:
        mark = ""
        if l["korrelation"] is not None:
            gueltig = [x["korrelation"] for x in rep["lags"] if x["korrelation"] is not None]
            mark = "  ←" if gueltig and l["korrelation"] == max(gueltig) else ""
        k = "—" if l["korrelation"] is None else f"{l['korrelation']:+.4f}"
        print(f"{l['lagStunden']:>+6.0f}h  {l['n']:>7}  {k}{mark}")
    print(f"\n📌 {rep['befund']}")
    print("   (Lag > 0 = Poly bewegte sich früher · Lag < 0 = Pinnacle führte)")
    print(f"💾 {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
