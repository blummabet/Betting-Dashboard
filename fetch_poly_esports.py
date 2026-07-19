#!/usr/bin/env python3
"""
fetch_poly_esports.py — E-Sport als eigener Poly-Datensatz für den Wallets-Tab (19.07.2026, Lucas).

E-Sport ist auf Polymarket breit und volumenstark (CS2/LoL/Dota/Valorant), hat aber KEINEN scharfen
Buchmacher-Anker wie Pinnacle. Deshalb kein Edge-vs-Pinnacle-Board — aber die volle „Poly-only"-
Sicht: wo liegt das Geld (Split), wie konzentriert (Whale-Anteil), welche Wale, und wo widerspricht
sich Poly selbst (Kohärenz-Arb).

Schreibt im GLEICHEN Format wie die Fußball-Datensätze, damit der Wallets-Tab E-Sport wie eine Liga
rendert (Menüpunkt neben MLS/Liga):
  · esports_poly_smartmoney.json  → Smart-Money-Konzentration
  · esports_poly_prices.json      → Volumen/Namen/slug + Kohärenz-Quelle
  · esports_poly_wallets.json     → Whale-Leaderboard / Flow
  · esports_poly_coherence.json   → Poly-interne Fehlbepreisung (via poly_coherence.analyze)

Reuse: Gamma-Events + Holders-Geld-Split aus poly_money_broad / fetch_wm_poly_smartmoney.
Läuft scharf nur am Mac-Runner (Poly EU-geoblockt). Reiner `build()` ohne Netz getestet.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import poly_coherence
import poly_money_broad as BR

BASE = Path(__file__).resolve().parent
ESPORT_TAGS = ["esports", "cs2", "lol", "dota", "valorant"]
MIN_VOL_USD = 5_000
_SIDES = ("home", "away")   # E-Sport-Moneyline ist 2-Wege (kein Remis)


def _now():
    return datetime.now(timezone.utc).isoformat()


def build(events, sm_fn) -> dict:
    """Gamma-Events → {prices, smartmoney, wallets}. REIN (sm_fn injiziert = Holders-Geld-Split).

    sm_fn(cond, token, price) → {usd, topHolderShare, holders, _wallets:[{wallet,usd,shares}]} | None"""
    prices, sm_matches, top_pos = {}, {}, []

    for ev in events or []:
        try:
            oc = BR._outcomes(ev)
            if len(oc) != 2:
                continue                     # nur klare 2-Wege-Moneyline
            vol = float(ev.get("volume") or 0)
            if vol < MIN_VOL_USD:
                continue
            key = ev.get("slug") or ev.get("id")
            home, away = oc[0]["label"], oc[1]["label"]
            hp, ap = oc[0].get("price"), oc[1].get("price")

            outs, wallets_here, total = {}, [], 0.0
            for side, o in zip(_SIDES, oc):
                sm = sm_fn(o.get("cond"), o.get("token"), o.get("price"))
                if not sm:
                    continue
                usd = float(sm.get("usd") or 0)
                total += usd
                outs[side] = {"usd": round(usd), "topHolderShare": sm.get("topHolderShare"),
                              "holders": sm.get("holders")}
                for w in (sm.get("_wallets") or []):
                    wallets_here.append({"wallet": w.get("wallet"), "usd": w.get("usd"),
                                         "shares": w.get("shares"), "side": side,
                                         "pick": (home if side == "home" else away),
                                         "match": home + " – " + away, "key": key})
            if total <= 0:
                continue
            for side in outs:                # share erst mit Gesamtsumme
                outs[side]["share"] = round(outs[side]["usd"] / total, 3)

            prices[key] = {"homeName": home, "awayName": away, "hw": hp, "aw": ap,
                           "poly_hw": hp, "poly_aw": ap, "vol": round(vol),
                           "slug": key, "kickoff": ev.get("startTime") or ev.get("gameStartTime")}
            sm_matches[key] = {"home": home, "away": away, "totalUsd": round(total),
                               "hoursToKickoff": BR._hours_to_ko(ev, BR._now()), "outcomes": outs}
            top_pos.extend(wallets_here)
        except Exception:
            continue

    top_pos.sort(key=lambda p: -(p.get("usd") or 0))
    return {
        "prices":     {"prices": prices, "generatedAt": _now()},
        "smartmoney": {"matches": sm_matches, "updatedAt": _now()},
        "wallets":    {"topPositionsAll": top_pos[:60], "bigTradesAll": [], "clustersAll": [],
                       "emptyReason": None, "updatedAt": _now()},
    }


def _fetch_events():
    """E-Sport-Events über alle Tags (dedupliziert). Runner-only (Gamma)."""
    seen, out = set(), []
    for tag in ESPORT_TAGS:
        for ev in BR._gamma_events(tag, closed=False):
            k = ev.get("slug") or ev.get("id")
            if k and k not in seen:
                seen.add(k); out.append(ev)
    return out


def main() -> int:
    events = _fetch_events()
    if not events:
        print("ℹ️  Keine E-Sport-Events (Runner-only) — Dateien unangetastet")
        return 0
    try:
        from fetch_wm_poly_smartmoney import _outcome_smartmoney as sm_fn
    except Exception as e:
        print(f"❌ smartmoney-Helper nicht ladbar: {e}")
        return 1

    out = build(events, sm_fn)
    (BASE / "esports_poly_prices.json").write_text(json.dumps(out["prices"], ensure_ascii=False, indent=1), encoding="utf-8")
    (BASE / "esports_poly_smartmoney.json").write_text(json.dumps(out["smartmoney"], ensure_ascii=False, indent=1), encoding="utf-8")
    (BASE / "esports_poly_wallets.json").write_text(json.dumps(out["wallets"], ensure_ascii=False, indent=1), encoding="utf-8")
    # Kohärenz-Arb auf denselben Preisen (geteilte, getestete Mathematik).
    coh = poly_coherence.analyze(out["prices"])
    (BASE / "esports_poly_coherence.json").write_text(json.dumps(coh, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"🎮 E-Sport: {len(out['prices']['prices'])} Märkte · {len(out['wallets']['topPositionsAll'])} Whale-Positionen · "
          f"{coh.get('arbCount',0)} Arb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
