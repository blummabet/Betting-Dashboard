#!/usr/bin/env python3
"""
poly_coherence.py — Polymarket gegen sich selbst prüfen (19.07.2026, Lucas: „Poly so gut es geht ausnutzen").

## Die Idee

Bisher prüfen wir Poly IMMER gegen Pinnacle (`auto_wm_poly_trigger` verlangt einen Pinnacle-Anker).
Aber Polymarket ist eine Börse aus vielen einzelnen Ja/Nein-Märkten, die NIEMAND intern konsistent
hält. Gerade auf dünnen MLS-Märkten laufen die Preise auseinander — und diese Widersprüche sind
Fehlbepreisung, die man OHNE jeden externen Anker sieht. Reine Poly-Struktur.

## Was gemessen wird (nach Härte des Edges sortiert)

1. **Underround (echter Arb).** Ein Ja/Nein-Paar muss zusammen ≥ 1.0 kosten (der Buchmacher-
   Aufschlag). Kostet es WENIGER als 1.0, kann man beide Seiten kaufen und bekommt garantiert 1.0
   zurück — risikoloser Gewinn. Betrifft O/U-Paare (o25+u25), BTTS (btts+btts_no) und die 1X2-Summe.
   Das ist das Härteste, was es gibt: kein Modell, keine Meinung, reine Arithmetik.

2. **Leiter-Inversion.** Mehr Tore sind unwahrscheinlicher: P(Über 1.5) > P(Über 2.5) > P(Über 3.5)
   MUSS gelten. Steht z.B. Über 3.5 höher als Über 2.5, ist mindestens eine der beiden Linien
   falsch bepreist — ein Widerspruch, den der Markt selbst nicht auflösen kann.

3. **Überround-Extrem.** Summiert ein Paar deutlich ÜBER 1.0 (z.B. 1.08), ist der Spread fett und
   beide Seiten sind teuer — kein Arb, aber ein Warnsignal: hier NICHT als Taker rein
   (siehe decide_entry_price / Maker-Modus).

## Was das NICHT ist

Kein Ausführungs-Skript. Es bewegt kein Geld, es platziert nichts. Es liest `{ds}_poly_prices.json`,
schreibt eine gerankte Befund-Liste nach `{ds}_poly_coherence.json` und macht die Lücken im
Wallets-Tab sichtbar. Ob und wie gehandelt wird, entscheidet der Mensch bzw. der gegatete Trigger.

⚠️ Ein Arb, den nur EINE dünne Quelle behauptet, ist meist ein veralteter Preis, kein Geschenk.
Deshalb: Mindest-Volumen je Markt + Mindest-Tiefe, wo verfügbar. Ein „Arb" auf einem Markt mit
$200 Volumen ist Rauschen.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).resolve().parent

# Schwellen. Bewusst konservativ — ein knapper „Arb" frisst Spread + Gebühr + Slippage auf.
MIN_UNDERROUND_EDGE = 0.02    # yes+no muss ≤ 0.98 sein, damit nach Kosten was übrig bleibt
LADDER_TOL          = 0.015   # kleine Inversionen sind Rundung/Zeitversatz, kein echter Widerspruch
OVERROUND_WARN      = 1.06    # darüber: Spread zu fett für Taker-Entry
MIN_VOL_USD         = 5_000   # dünner Markt → Preise sind Deko, kein handelbarer Arb

# Ja/Nein-Paare, die je ~1.0 summieren müssen. (label, ja-Feld, nein-Feld)
BINARY_PAIRS = [
    ("Über/Unter 1.5", "poly_o15", "poly_u15"),
    ("Über/Unter 2.5", "poly_o25", "poly_u25"),
    ("Über/Unter 3.5", "poly_o35", "poly_u35"),
    ("BTTS",           "poly_btts", "poly_btts_no"),
]

# Über-Leiter: muss monoton FALLEN (mehr Tore = unwahrscheinlicher).
OVER_LADDER  = [("Über 1.5", "poly_o15"), ("Über 2.5", "poly_o25"), ("Über 3.5", "poly_o35")]


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if 0.0 < x < 1.0 else None


def _check_match(key: str, e: dict) -> list[dict]:
    """Alle Kohärenz-Befunde eines Spiels. Rein — keine I/O."""
    out = []
    vol = e.get("vol")
    try:
        vol = float(vol or 0)
    except (TypeError, ValueError):
        vol = 0.0
    if vol < MIN_VOL_USD:
        return out   # dünner Markt: Preise nicht handelbar, jeder „Arb" ist Rauschen

    match = e.get("title") or key

    # 1X2-Summe
    hw, dr, aw = _f(e.get("hw")), _f(e.get("dr")), _f(e.get("aw"))
    if hw and dr and aw:
        s = hw + dr + aw
        if s <= 1.0 - MIN_UNDERROUND_EDGE:
            out.append({"key": key, "match": match, "typ": "underround", "markt": "1X2",
                        "summe": round(s, 4), "edgePP": round((1.0 - s) * 100, 2),
                        "hinweis": "Alle drei Ergebnisse zusammen < 1.0 → garantierter Ertrag"})
        elif s >= 1.0 + (OVERROUND_WARN - 1.0):
            out.append({"key": key, "match": match, "typ": "overround", "markt": "1X2",
                        "summe": round(s, 4), "edgePP": round((s - 1.0) * 100, 2),
                        "hinweis": "Fetter Spread — nicht als Taker rein"})

    # Binär-Paare
    for label, jf, nf in BINARY_PAIRS:
        ja, nein = _f(e.get(jf)), _f(e.get(nf))
        if ja is None or nein is None:
            continue
        s = ja + nein
        if s <= 1.0 - MIN_UNDERROUND_EDGE:
            out.append({"key": key, "match": match, "typ": "underround", "markt": label,
                        "summe": round(s, 4), "edgePP": round((1.0 - s) * 100, 2),
                        "hinweis": f"{label}: Ja+Nein = {s:.3f} < 1.0 → beide Seiten kaufen"})
        elif s >= OVERROUND_WARN:
            out.append({"key": key, "match": match, "typ": "overround", "markt": label,
                        "summe": round(s, 4), "edgePP": round((s - 1.0) * 100, 2),
                        "hinweis": f"{label}: Spread {(s-1)*100:.1f}pp — Maker statt Taker"})

    # Leiter-Monotonie (Über)
    leiter = [(lbl, _f(e.get(fld))) for lbl, fld in OVER_LADDER]
    leiter = [(lbl, v) for lbl, v in leiter if v is not None]
    for (l1, v1), (l2, v2) in zip(leiter, leiter[1:]):
        if v2 > v1 + LADDER_TOL:   # späteres (mehr Tore) teurer als früheres → Widerspruch
            out.append({"key": key, "match": match, "typ": "ladder_inversion",
                        "markt": f"{l1} vs {l2}", "summe": None,
                        "edgePP": round((v2 - v1) * 100, 2),
                        "hinweis": f"{l2} ({v2:.2f}) > {l1} ({v1:.2f}) — unmöglich, eine Linie ist falsch"})
    return out


def analyze(prices: dict) -> dict:
    befunde = []
    for key, e in (prices.get("prices") or {}).items():
        befunde.extend(_check_match(key, e))
    # Härteste zuerst: Arb vor Widerspruch vor Warnung, dann nach Edge-Größe.
    rang = {"underround": 0, "ladder_inversion": 1, "overround": 2}
    befunde.sort(key=lambda b: (rang.get(b["typ"], 9), -(b.get("edgePP") or 0)))
    return {
        "dataset": D.active_dataset(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "arbCount":   sum(1 for b in befunde if b["typ"] == "underround"),
        "inversions": sum(1 for b in befunde if b["typ"] == "ladder_inversion"),
        "warnings":   sum(1 for b in befunde if b["typ"] == "overround"),
        "findings": befunde,
    }


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    prices = _load(D.file("wm_poly_prices.json", "liga_poly_prices.json").name)
    if not prices:
        print("ℹ️  Keine Poly-Preise — nichts zu prüfen")
        return 0
    rep = analyze(prices)
    out = D.file("wm_poly_coherence.json", "liga_poly_coherence.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"=== Poly-Kohärenz ({rep['dataset'].upper()}) ===")
    print(f"🟢 {rep['arbCount']} Arbs · 🟠 {rep['inversions']} Leiter-Widersprüche · "
          f"⚪ {rep['warnings']} Spread-Warnungen\n")
    for b in rep["findings"][:15]:
        ic = {"underround": "🟢", "ladder_inversion": "🟠", "overround": "⚪"}.get(b["typ"], "·")
        print(f"{ic} {b['match'][:34]:34} {b['markt']:16} {b['edgePP']:+5.1f}pp  {b['hinweis']}")
    print(f"\n💾 {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
