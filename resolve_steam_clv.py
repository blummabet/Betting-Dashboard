#!/usr/bin/env python3
"""
resolve_steam_clv.py — CLV-Tracking für Steam-Card-Picks (Lucas' Modell, 14.06.2026).

Closing Line Value ist der ehrliche Nordstern für Steam-Following: hat der scharfe
Schluss-Kurs unseren Einstieg bestätigt? Pro gespieltem Steam-Pick:
    clvPP = (Pinnacle-Closing-Wahrscheinlichkeit der Pick-Seite − 1/Einstiegsquote) · 100
  • positiv = Linie ist NACH unserem Einstieg weiter in Pick-Richtung gelaufen → wir haben
    den Closing-Kurs geschlagen (gut, unabhängig vom Spielausgang).
  • Über viele Picks misst der Durchschnitt, ob die Steam-These echten Vorsprung hat —
    verlässlicher als Win/Loss (rechnet die Varianz raus).

ISOLIERT: liest/schreibt nur wm2026-data.json (clvPP auf Steam-Picks). Rührt den
komplexen Bets-/Trade-Resolver NICHT an. Wiederverwendet dessen geprüfte Helfer
(build_result_lookup, get_pinn_close_for_market) als single source of truth.

Lauf nach den Ergebnissen (z.B. in fetch-results-Workflow nach resolve_wm_results).
"""
from __future__ import annotations
import json
import os
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).parent
# Dataset-Modus (Single Source: cocobet_dataset): Liga → CLV auf liga-data.json.
WM = D.data_file()

try:
    from resolve_wm_results import build_result_lookup, get_pinn_close_for_market
except Exception as e:  # pragma: no cover
    build_result_lookup = None
    get_pinn_close_for_market = None
    _IMPORT_ERR = e


def steam_clv_pp(pinn_close_prob, entry_odd):
    """CLV in pp: Pinnacle-Closing-Prob der Pick-Seite vs implizite Einstiegsquote."""
    if not pinn_close_prob or not entry_odd or entry_odd <= 1.0:
        return None
    return round((pinn_close_prob - 1.0 / entry_odd) * 100, 2)


def resolve(wm: dict) -> int:
    """Setzt clvPP auf jedem aufgelösten Steam-Pick. Gibt die Anzahl gesetzter CLVs zurück."""
    if build_result_lookup is None:
        return 0
    lookup = build_result_lookup(wm)
    picks = wm.get("picks") or {}
    n = 0
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        parts = key.split("-")
        res = lookup.get(f"{parts[2]}-{parts[3]}", {}) if len(parts) >= 4 else {}
        if not res:
            continue   # Spiel noch nicht aufgelöst
        for p in plist:
            if p.get("source") != "steam":
                continue
            entry = p.get("entryOdd") or p.get("odds")
            pinn_close = get_pinn_close_for_market(res, p.get("market", ""))
            clv = steam_clv_pp(pinn_close, entry)
            if clv is not None:
                p["clvPP"] = clv
                p["clvResolved"] = True
                n += 1
    return n


def main() -> None:
    if build_result_lookup is None:
        print(f"❌ Import aus resolve_wm_results fehlgeschlagen: {_IMPORT_ERR}")
        return
    wm = json.loads(WM.read_text(encoding="utf-8"))
    n = resolve(wm)
    if n:
        WM.write_text(json.dumps(wm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Steam-CLV gesetzt für {n} aufgelöste Pick(s)")


if __name__ == "__main__":
    main()
