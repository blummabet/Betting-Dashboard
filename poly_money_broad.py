#!/usr/bin/env python3
"""
poly_money_broad.py — Liegt das Geld richtig? BREIT über ALLE Poly-Ligen (19.07.2026, Lucas).

## Idee

`poly_money_accuracy.py` misst das für unsere Datensätze (WM/MLS) gegen unsere Ergebnisdaten.
Lucas will es breiter: **alles, was Polymarket anbietet** (min. Volumen), um zu sehen, wo die Masse
mehr recht hat — je Liga aufgeschlüsselt, und ohne triviale Favoriten (Quote < 1.35).

Der Clou: für fremde Ligen brauchen wir GAR KEINE eigenen Ergebnisse — **Polymarket löst seine
Märkte selbst auf** (die Gewinner-Seite settlet auf 1.00). Also: Geld-Verteilung + Preis nah am
Anpfiff einfrieren, später Polys eigene Auflösung lesen. Kein externer Anker nötig.

## Filter (Lucas)

  · Volumen ≥ Schwelle (5–10k) — darunter ist die Geld-Verteilung nicht aussagekräftig.
  · Favorit-Quote ≥ 1.35 — „dass ein 1.1-Favorit öfter recht hat, ist logo"; nur kompetitive
    Märkte sagen etwas über die Klugheit der Masse.

Teilt sich `evaluate` (min_odds + byLeague) mit poly_money_accuracy — dieselbe, getestete Mathematik.

⚠️ Die Fetch-/Auflösungs-Schicht (Gamma über alle Sport-Tags + Poly-Resolution + Holders je Markt)
läuft scharf NUR am Mac-Runner (Poly EU-geoblockt) und muss dort validiert werden. Die reinen
Helfer (`winner_from_prices`, Aggregation via `evaluate`) sind ohne Netz getestet. Read-only.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import poly_money_accuracy as PMA

BASE = Path(__file__).resolve().parent

MIN_VOL_USD = 7_500     # „5-10k oben liegen" — Mitte
MIN_ODDS    = 1.35      # Lucas: triviale Favoriten (≤1.35) raus
CLOSE_FILE  = "poly_money_broad_close.json"
OUT_FILE    = "poly_money_broad.json"


def _now():
    return datetime.now(timezone.utc)


def _cfg():
    try:
        raw = json.loads((BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        p = raw.get("poly", {})
        return float(p.get("money_broad_min_vol", MIN_VOL_USD)), float(p.get("money_broad_min_odds", MIN_ODDS))
    except Exception:
        return MIN_VOL_USD, MIN_ODDS


def winner_from_prices(price_by_outcome: dict, tol: float = 0.02):
    """Aus Polys AUFGELÖSTEN Outcome-Preisen die Gewinner-Seite ableiten: die, die ~1.00 settlet.
    None, wenn (noch) nicht eindeutig aufgelöst (kein Preis nahe 1.0)."""
    best, best_p = None, 0.0
    for k, v in (price_by_outcome or {}).items():
        try:
            p = float(v)
        except (TypeError, ValueError):
            continue
        if p > best_p:
            best, best_p = k, p
    return best if best_p >= 1.0 - tol else None


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Fetch-/Capture-Schicht (Mac-Runner) ──────────────────────────────────────

def fetch_markets():
    """Alle Poly-Sportmärkte mit Volumen ≥ Schwelle. Placeholder: Poly EU-geoblockt → am Runner
    implementieren (Gamma über die Sport-Tags: nba, nfl, mlb, nhl, epl, soccer-*, tennis, …).
    Erwartetes Rückgabeformat je Markt:
        {key, league, hoursToKickoff, totalUsd,
         shares:{home,draw,away}, prices:{home,draw,away},
         resolved:bool, resolvedPrices:{home,draw,away}}"""
    return []   # no-op außerhalb des Runners → Skript lässt bestehende Dateien in Ruhe


def capture(markets, frozen, now=None, min_vol=MIN_VOL_USD):
    """Nah am Anpfiff einfrieren (Geld-Verteilung + Preis + Liga). REIN, testbar."""
    now = now or _now()
    out = dict(frozen or {})
    for m in markets or []:
        htk = m.get("hoursToKickoff")
        try:
            htk = float(htk)
        except (TypeError, ValueError):
            continue
        if not (0 < htk <= PMA.CAPTURE_WINDOW_H) or float(m.get("totalUsd") or 0) < min_vol:
            continue
        key = m.get("key")
        prev = out.get(key)
        if prev is not None and prev.get("hoursToKickoff", 99) <= htk:
            continue
        out[key] = {"shares": m.get("shares") or {}, "prices": m.get("prices") or {},
                    "league": m.get("league"), "totalUsd": round(float(m.get("totalUsd") or 0)),
                    "hoursToKickoff": round(htk, 2), "capturedAt": now.isoformat()}
    return out


def resolutions(markets) -> dict:
    """{key: winner} aus den aufgelösten Poly-Märkten (settlet auf 1.00)."""
    out = {}
    for m in markets or []:
        if not m.get("resolved"):
            continue
        w = winner_from_prices(m.get("resolvedPrices") or {})
        if w:
            out[m.get("key")] = w
    return out


def main() -> int:
    min_vol, min_odds = _cfg()
    markets = fetch_markets()
    if not markets:
        print("ℹ️  Keine Poly-Märkte (läuft scharf nur am Mac-Runner) — Dateien unangetastet")
        return 0
    frozen = capture(markets, _load(CLOSE_FILE), min_vol=min_vol)
    (BASE / CLOSE_FILE).write_text(json.dumps(frozen, ensure_ascii=False, indent=1), encoding="utf-8")

    rep = PMA.evaluate(frozen, resolutions(markets), min_odds=min_odds)
    rep["generatedAt"] = _now().isoformat()
    rep["minVolUsd"] = min_vol
    rep["scope"] = "broad_all_leagues"
    (BASE / OUT_FILE).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"=== Liegt das Geld richtig? BREIT · min Vol ${min_vol:.0f} · min Quote {min_odds} ===")
    print(f"Eingefroren {len(frozen)} · aufgelöst {rep['n']}")
    for lg in rep.get("byLeague", [])[:20]:
        print(f"  {lg['league']:18} n={lg['n']:3}  Geld {lg['moneyHitRate']*100:.0f}%  "
              f"Brier G {lg['brierMoney']} vs P {lg['brierPrice']}  → {lg['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
