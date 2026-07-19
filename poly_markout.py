#!/usr/bin/env python3
"""
poly_markout.py — Trägt Making überhaupt? Adverse-Selection-Test (19.07.2026, Lucas).

## Warum

Lucas hat parallel im Krypto-Projekt (CryptoEdge) sechs Poly-Strategien auf Papier gemessen.
Befund zum Maker-Modus: **Markout −4.18pp roh, −3.75pp sogar delta-gehedged → „echt-toxisch".**
Heißt: wer als Maker an seiner Fair quotet, wird GENAU DANN gefüllt, wenn die Fair falsch ist —
der Spread, den man spart, kommt über Adverse Selection doppelt zurück.

Wir haben Maker für Fußball gebaut (`poly_entry`, Lebenszyklus), aber bewusst auf `maker_enabled=
false` gelassen. Bevor das je angefasst wird, misst DIESES Skript dasselbe für unsere Märkte —
aus echten Daten, ohne einen Cent zu riskieren.

## Was „Markout" ist

Der Wert eines Fills NACH dem Move. Eine ruhende Kauf-Order (Bid) liegt unter dem Mid. Sie füllt,
wenn jemand zu ihr runter verkauft — also bei ABWÄRTSDRUCK. Die ehrliche Frage: läuft der Preis
danach WEITER runter (wir wurden adverse selektiert, Making verliert) oder erholt er sich
(Making trägt)? Markout = Preis(t+Δ) − Fill-Preis, in unsere Long-Richtung. Negativ = Adverse
Selection.

## Wie ohne echte Fills gemessen wird

Wir haben (noch) keine Maker-Fills — aber die Poly-Preishistorie. Simulation, bewusst konservativ:
  · Ein **Abwärts-Tick** (Preis fällt von einem Snapshot zum nächsten um ≥ MIN_TICK) ist der
    Moment, in dem eine ruhende Bid gefüllt worden wäre. Wir buchen einen simulierten Kauf zum
    (niedrigeren) neuen Preis.
  · **Markout** = wie sich der Preis über die nächsten Δ bewegt. Über viele Fills gemittelt.
  · Das fängt die SELEKTION ein — wir „füllen" nur bei Abwärtsbewegung, genau wie eine echte Bid.

Netto-Maker-Wert ≈ Markout + eingesparter halber Spread. Ist der Netto-Wert negativ, verliert
Making — dann bleibt `maker_enabled` aus, egal wie verlockend die Spread-Ersparnis klingt.

⚠️ Der Snapshot-Preis ist ein Mid; eine echte Bid füllt etwas darunter (leicht besserer Entry) →
unsere Markout-Schätzung ist eher PESSIMISTISCH. Für ein „trägt es überhaupt"-Tor ist das die
richtige Richtung: lieber konservativ als zu optimistisch scharfschalten.

Kein Ausführungs-Skript. Liest `{ds}-poly-history` → schreibt `{ds}_poly_markout.json`.
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).resolve().parent

OUTCOMES   = ["poly_hw", "poly_dr", "poly_aw", "poly_o25", "poly_u25"]
MIN_TICK   = 0.01     # kleinere „Bewegungen" sind Rundung, kein Fill
HORIZONS_H = [0.5, 2.0, 6.0]     # Markout-Fenster in Stunden
HEADLINE_H = 2.0      # das Fenster, an dem das Urteil hängt (typische Rest-Liegezeit vor Anpfiff)
SPREAD_SAVED_PP = 1.5  # konservativ: halber Spread bei unserer 3pp-Mindest-Maker-Schwelle
MIN_FILLS  = 30       # darunter ist die Aussage statistisch wertlos


def _ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _plausible(p) -> bool:
    """Poly-Preis muss echte Wahrscheinlichkeit sein. 0.0/1.0 sind Platzhalter (kein Markt)."""
    try:
        v = float(p)
    except (TypeError, ValueError):
        return False
    return 0.01 < v < 0.99


def _series(snaps, field):
    out = []
    for s in snaps:
        ts, p = _ts(s.get("ts")), s.get(field)
        if ts is not None and _plausible(p):
            out.append((ts, float(p)))
    out.sort()
    return out


def _fwd_price(series, i, horizon_h):
    """Preis beim ersten Snapshot ≥ t_i + horizon. None, wenn die Reihe nicht so weit reicht."""
    from datetime import timedelta
    target = series[i][0] + timedelta(hours=horizon_h)
    for j in range(i + 1, len(series)):
        if series[j][0] >= target:
            return series[j][1]
    return None


def compute_markout(history: dict) -> dict:
    """Simulierte Maker-Fills auf Abwärts-Ticks → Markout je Horizont. Rein, testbar."""
    per_h = {h: [] for h in HORIZONS_H}
    fills = 0

    for _key, snaps in (history or {}).items():
        if not isinstance(snaps, list):
            continue
        for field in OUTCOMES:
            s = _series(snaps, field)
            for i in range(1, len(s)):
                prev, cur = s[i - 1][1], s[i][1]
                if cur > prev - MIN_TICK:
                    continue                     # kein Abwärts-Tick → keine Bid-Füllung
                fills += 1
                for h in HORIZONS_H:
                    fwd = _fwd_price(s, i, h)
                    if fwd is not None:
                        per_h[h].append((fwd - cur) * 100)   # Long-Markout in pp

    def _agg(vals):
        if not vals:
            return {"n": 0, "meanPP": None, "medianPP": None}
        return {"n": len(vals), "meanPP": round(statistics.mean(vals), 3),
                "medianPP": round(statistics.median(vals), 3)}

    horizons = {f"{h}h": _agg(per_h[h]) for h in HORIZONS_H}
    head = horizons.get(f"{HEADLINE_H}h", {})
    mean_head = head.get("meanPP")
    n_head = head.get("n", 0)

    if mean_head is None or n_head < MIN_FILLS:
        verdict, net = "zu wenig Daten", None
    else:
        net = round(mean_head + SPREAD_SAVED_PP, 3)   # Markout (Adverse Selection) + Spread-Ersparnis
        if net > 0.3:
            verdict = "traegt"          # Netto positiv → Making lohnt
        elif net < -0.3:
            verdict = "traegt_nicht"    # Adverse Selection frisst die Spread-Ersparnis
        else:
            verdict = "grenzwertig"

    return {
        "dataset": D.active_dataset(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "fills": fills,
        "spreadSavedPP": SPREAD_SAVED_PP,
        "headlineHorizon": f"{HEADLINE_H}h",
        "netMakerPP": net,
        "verdict": verdict,
        "horizons": horizons,
    }


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    hist = _load(D.file("wm2026-poly-history.json", "liga-poly-history.json").name)
    if not hist:
        print("ℹ️  Keine Poly-Historie — nichts zu messen")
        return 0
    rep = compute_markout(hist)
    out = D.file("wm_poly_markout.json", "liga_poly_markout.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    label = {"traegt": "🟢 trägt", "traegt_nicht": "🔴 trägt NICHT (Adverse Selection)",
             "grenzwertig": "⚪ grenzwertig", "zu wenig Daten": "⏳ zu wenig Daten"}.get(rep["verdict"], rep["verdict"])
    print(f"=== Maker-Markout ({rep['dataset'].upper()}) — kann Making funktionieren? ===")
    print(f"{rep['fills']} simulierte Fills (Abwärts-Ticks)\n")
    print(f"{'Horizont':>9}  {'n':>6}  {'Ø Markout':>11}")
    for h, a in rep["horizons"].items():
        m = "—" if a["meanPP"] is None else f"{a['meanPP']:+.2f}pp"
        print(f"{h:>9}  {a['n']:>6}  {m:>11}")
    print(f"\nMarkout {rep['headlineHorizon']} + Spread-Ersparnis {rep['spreadSavedPP']}pp "
          f"= Netto {rep['netMakerPP']}pp  →  {label}")
    print(f"💾 {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
