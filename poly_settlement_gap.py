#!/usr/bin/env python3
"""
poly_settlement_gap.py — die Auflösungs-Lücke ausnutzen (19.07.2026, Lucas: „Poly maximal ausnutzen").

## Die Idee

Polymarket löst nicht sofort auf. Zwischen Abpfiff und der Oracle-Bestätigung (UMA) vergehen oft
Stunden. In diesem Fenster STEHT das Ergebnis fest — der Gewinner-Ausgang müsste 1.00 kosten,
handelt aber noch bei 0.95-0.98, weil die letzten Halter aussteigen und keiner mehr aktiv
nachpreist. Wer den Gewinner-Ausgang jetzt kauft, bekommt bei Auflösung garantiert 1.00. Das sind
planbare 2-5 Prozentpunkte, risikolos bis auf das Auflösungsrisiko selbst (Oracle-Streit — selten).

## Wie erkannt wird

Für jeden Poly-Markt zu einem BEENDETEN Spiel: welcher Ausgang hat gewonnen, und was kostet er
noch? Liegt er unter der Schwelle → Lücke = 1.00 − Preis.

Deckt alle Märkte ab, die wir bepreisen: 1X2, O/U 1.5/2.5/3.5, BTTS.

## Die eine Falle, an der das kippt: STALE PREISE

Ein Poly-Preis von 0.55 auf „Heimsieg" ist nur dann eine Auflösungs-Lücke, wenn er NACH dem
Abpfiff erfasst wurde. Ist es ein alter Vorspiel-Snapshot, ist 0.55 einfach die damalige
Wahrscheinlichkeit — kein Gewinn, sondern eine Wette auf ein längst gelaufenes Spiel. Deshalb:
nur werten, wenn der Preis-Snapshot NACH Anpfiff + Spieldauer liegt. Ohne diesen Filter würde das
Skript jede vergangene Wette als „garantierten Gewinn" ausweisen — der teuerste denkbare Irrtum.

Kein Ausführungs-Skript: liest Ergebnisse + `{ds}_poly_prices.json`, schreibt gerankte Lücken nach
`{ds}_poly_settlement.json`, macht sie im Wallets-Tab sichtbar. Handeln entscheidet der Mensch.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).resolve().parent

SETTLE_THRESHOLD = 0.97     # Gewinner unter diesem Preis = Lücke (nach Kosten lohnend ab ~2pp)
MIN_GAP_PP       = 1.5      # kleinere Lücken frisst die Gebühr
MATCH_DURATION_H = 2.25     # Anpfiff + so viele Stunden = sicher vorbei (inkl. Nachspielzeit)
MIN_VOL_USD      = 3_000    # dünner Markt: kein handelbarer Ausstieg


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if 0.0 <= x <= 1.0 else None


def _winning_outcomes(hs: int, aw_s: int) -> dict:
    """Welcher Preis-Feldname hat bei diesem Endstand GEWONNEN (müsste 1.0 sein)?
    Nur Märkte, die wir auch bepreisen."""
    total = hs + aw_s
    win = {}
    win["hw" if hs > aw_s else "aw" if aw_s > hs else "dr"] = "1X2"
    win["poly_o15" if total >= 2 else "poly_u15"] = "Ü/U 1.5"
    win["poly_o25" if total >= 3 else "poly_u25"] = "Ü/U 2.5"
    win["poly_o35" if total >= 4 else "poly_u35"] = "Ü/U 3.5"
    win["poly_btts" if (hs >= 1 and aw_s >= 1) else "poly_btts_no"] = "BTTS"
    return win


def _ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _result_lookup(data: dict) -> dict:
    """(homeId-awayId) → (home_score, away_score). Deckt groups UND koFixtures ab."""
    out = {}
    fixtures = []
    for g in (data.get("groups") or {}).values():
        fixtures += g.get("fixtures") or []
    fixtures += data.get("koFixtures") or []
    for fx in fixtures:
        r = fx.get("result") or {}
        if r.get("status") not in ("FT", "AET", "PEN"):
            continue
        hs, as_ = r.get("home_score"), r.get("away_score")
        if hs is None or as_ is None:
            continue
        out[f"{fx.get('home')}-{fx.get('away')}"] = (int(hs), int(as_))
    return out


def analyze(prices: dict, data: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    snap_ts = _ts(prices.get("generatedAt"))
    results = _result_lookup(data)
    gaps, skipped_stale = [], 0

    for key, e in (prices.get("prices") or {}).items():
        res = results.get(key) or results.get(f"{e.get('homeId')}-{e.get('awayId')}")
        if not res:
            continue

        # STALE-Schutz: Preis muss NACH Spielende erfasst sein, sonst ist es keine Lücke.
        ko = _ts(e.get("kickoff"))
        price_time = snap_ts
        if ko is None or price_time is None or price_time < ko + timedelta(hours=MATCH_DURATION_H):
            skipped_stale += 1
            continue

        try:
            vol = float(e.get("vol") or 0)
        except (TypeError, ValueError):
            vol = 0.0
        if vol < MIN_VOL_USD:
            continue

        hs, as_ = res
        for field, markt in _winning_outcomes(hs, as_).items():
            price = _f(e.get(field))
            if price is None or price >= SETTLE_THRESHOLD:
                continue
            gap = round((1.0 - price) * 100, 2)
            if gap < MIN_GAP_PP:
                continue
            gaps.append({
                "key": key, "match": e.get("title") or key, "markt": markt,
                "endstand": f"{hs}:{as_}", "gewinnerPreis": round(price, 4),
                "gapPP": gap, "vol": round(vol),
                "hinweis": f"{markt} steht fest ({hs}:{as_}), handelt noch {price:.2f} → +{gap:.1f}pp bis Auflösung",
            })

    gaps.sort(key=lambda g: -g["gapPP"])
    return {
        "dataset": D.active_dataset(),
        "generatedAt": now.isoformat(),
        "gapCount": len(gaps),
        "skippedStale": skipped_stale,
        "gaps": gaps,
    }


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    prices = _load(D.file("wm_poly_prices.json", "liga_poly_prices.json").name)
    data   = _load(D.data_file().name)
    if not prices or not data:
        print("ℹ️  Poly-Preise oder Datensatz fehlen — nichts zu prüfen")
        return 0
    rep = analyze(prices, data)
    out = D.file("wm_poly_settlement.json", "liga_poly_settlement.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"=== Poly Auflösungs-Lücken ({rep['dataset'].upper()}) ===")
    print(f"{rep['gapCount']} Lücken · {rep['skippedStale']} übersprungen (Vorspiel-Preis, kein Settlement)\n")
    for g in rep["gaps"][:15]:
        print(f"💰 {g['match'][:34]:34} {g['markt']:9} {g['endstand']:>5}  "
              f"{g['gewinnerPreis']:.2f} → +{g['gapPP']:.1f}pp")
    print(f"\n💾 {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
