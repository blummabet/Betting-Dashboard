#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""poly_pinnacle_stats.py — DAUERHAFTES Ledger fuer den Pinnacle x Poly Lag-Backtest (07.08.2026, Lucas).

Der Round-Trip-Backtest selbst laeuft schon LIVE im Frontend (pinnacle-poly.js::_backtest). Dessen
Schwaeche: er sieht nur die Spiele, die GERADE im Scan-File liegen (nach 6h gepruned) -> der Sample
waechst nie ("Backtest sammelt noch" haengt fest). Dieses Modul rechnet DIESELBE Logik server-seitig
und schreibt abgeschlossene Round-Trips in ein append-only Ledger -> der Track-Record waechst ueber
Wochen. Schwellen sind exakt auf pinnacle-poly.js ausgerichtet, damit die Zahlen konsistent sind.

  Einstieg  — Pinnacle zieht im Schritt hoch (move >= MOVE_MIN_PP) UND Poly liegt noch >= ENTRY_EDGE_PP
              darunter (edge = pinn-fair − poly = Poly-Lag). Gekauft: der Ausgang auf Poly.
  Ausstieg  — edge konvergiert auf <= EXIT_EDGE_PP, sonst Zwangs-Close am letzten Vor-Anpfiff-Snap.

Nur abgeschlossene Spiele (Anpfiff vorbei) -> jeder Round-Trip ist fertig. Reine Messung, keine Trades.
Kern (backtest_game/run/merge_ledger) ist netz-frei/testbar; main() liest/schreibt nur.
Ausgabe: poly_pinnacle_lag_stats.json fuer die Anzeige im Pinnacle-Poly-Tab.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCAN_FILE = BASE / "pinnacle_poly_scan.json"
OUT_FILE = BASE / "poly_pinnacle_lag_stats.json"

# Schwellen EXAKT wie pinnacle-poly.js (_backtest). Env-ueberschreibbar.
MOVE_MIN_PP = float(os.environ.get("LAG_MOVE_MIN_PP") or 1.5)     # Pinnacle-Move (Schritt)
ENTRY_EDGE_PP = float(os.environ.get("LAG_ENTRY_EDGE_PP") or 3.0)  # Poly-Lag beim Einstieg
EXIT_EDGE_PP = float(os.environ.get("LAG_EXIT_EDGE_PP") or 1.0)    # konvergiert -> Ausstieg
MIN_SNAPS = int(os.environ.get("LAG_MIN_SNAPS") or 4)
MAX_TRADES_OUT = 200

SIDES = (("home", 0), ("draw", 1), ("away", 2))   # alle drei Ausgaenge, wie im Frontend


def _ts(s):
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _prob(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if 0.01 < v < 0.99 else None


def _pre_ko_snaps(game):
    """Vor-Anpfiff-Snaps in Zeitreihenfolge; jeder mit brauchbarem pinn+poly-Tripel."""
    ko = _ts(game.get("kickoff"))
    out = []
    for sn in (game.get("snaps") or []):
        t = _ts(sn.get("ts"))
        if t is None or (ko is not None and t > ko):
            continue
        pinn, poly = sn.get("pinn"), sn.get("poly")
        if not (isinstance(pinn, list) and isinstance(poly, list) and len(pinn) == 3 and len(poly) == 3):
            continue
        out.append((t, pinn, poly))
    out.sort(key=lambda x: x[0])
    return out


def _mk_trade(game, side, pos, t_exit, poly_exit, reason):
    gain_pp = (poly_exit - pos["poly"]) * 100.0
    roi = (poly_exit - pos["poly"]) / pos["poly"] * 100.0 if pos["poly"] else 0.0
    hold_h = (t_exit - pos["t"]).total_seconds() / 3600.0
    return {
        "league": game.get("league"), "home": game.get("home"), "away": game.get("away"),
        "side": side, "entryTs": pos["t"].isoformat(), "entryPoly": round(pos["poly"], 4),
        "targetPinn": round(pos["target"], 4), "exitTs": t_exit.isoformat(),
        "exitPoly": round(poly_exit, 4), "gainPP": round(gain_pp, 2), "roiPct": round(roi, 2),
        "holdH": round(hold_h, 2), "exitReason": reason,
    }


def backtest_game(game, move_min=MOVE_MIN_PP, entry_edge=ENTRY_EDGE_PP,
                  exit_edge=EXIT_EDGE_PP, min_snaps=MIN_SNAPS):
    """Ein Spiel -> Liste Round-Trip-Trades. Logik EXAKT wie pinnacle-poly.js::_backtest. REIN/testbar."""
    snaps = _pre_ko_snaps(game)
    if len(snaps) < min_snaps:
        return []
    trades = []
    for name, idx in SIDES:
        pos = None
        for i in range(1, len(snaps)):
            t, pinn, poly = snaps[i]
            pinn_prev = snaps[i - 1][1]
            pf, pp, pf_prev = _prob(pinn[idx]), _prob(poly[idx]), _prob(pinn_prev[idx])
            if pf is None or pp is None or pf_prev is None:
                continue
            edge = (pf - pp) * 100.0        # Poly-Lag: Pinnacle-fair − Poly
            move = (pf - pf_prev) * 100.0   # Pinnacle-Bewegung im Schritt
            if pos is None:
                if move >= move_min and edge >= entry_edge:
                    pos = {"t": t, "poly": pp, "target": pf}
            elif edge <= exit_edge:
                trades.append(_mk_trade(game, name, pos, t, pp, "converged"))
                pos = None
        if pos is not None:   # nicht konvergiert -> Zwangs-Close am letzten Vor-KO-Snap
            t_last, _, poly_last = snaps[-1]
            pp_last = _prob(poly_last[idx])
            if pp_last is not None and t_last > pos["t"]:
                trades.append(_mk_trade(game, name, pos, t_last, pp_last, "close"))
    return trades


def _agg(trades):
    if not trades:
        return {"n": 0, "avgGainPP": 0.0, "avgRoiPct": 0.0, "winRatePct": 0.0, "medianHoldH": 0.0}
    n = len(trades)
    holds = sorted(t["holdH"] for t in trades)
    med = holds[n // 2] if n % 2 else (holds[n // 2 - 1] + holds[n // 2]) / 2.0
    return {
        "n": n,
        "avgGainPP": round(sum(t["gainPP"] for t in trades) / n, 2),
        "avgRoiPct": round(sum(t["roiPct"] for t in trades) / n, 2),
        "winRatePct": round(100.0 * sum(1 for t in trades if t["gainPP"] > 0) / n, 1),
        "medianHoldH": round(med, 2),
    }


def _by_league(trades):
    out = {}
    for lg in sorted({t["league"] for t in trades if t.get("league")}):
        out[lg] = _agg([t for t in trades if t["league"] == lg])
    return out


def run(store, now=None, move_min=MOVE_MIN_PP, entry_edge=ENTRY_EDGE_PP,
        exit_edge=EXIT_EDGE_PP, min_snaps=MIN_SNAPS):
    """Store -> {overall, byLeague, trades}. Mit `now` NUR abgeschlossene Spiele (Anpfiff vorbei).
    Ohne `now` (Tests): alle Spiele. REIN/testbar."""
    trades = []
    for g in (store or {}).get("games", {}).values():
        if now is not None:
            ko = _ts(g.get("kickoff"))
            if ko is None or ko > now:
                continue    # noch nicht angepfiffen -> Runde offen, nicht backtestbar
        trades.extend(backtest_game(g, move_min, entry_edge, exit_edge, min_snaps))
    return {"overall": _agg(trades), "byLeague": _by_league(trades), "trades": trades}


def _trade_key(t):
    return (t.get("home"), t.get("away"), t.get("side"), t.get("entryTs"))


def merge_ledger(prev_trades, new_trades):
    """Append-only Trade-Ledger (dedup ueber home|away|side|entryTs). Damit waechst der Track-Record
    ueber Laeufe, statt bei jedem Lauf nur das aktuelle 6h-Fenster zu sehen. REIN/testbar."""
    led = list(prev_trades or [])
    seen = {_trade_key(t) for t in led}
    added = 0
    for t in new_trades:
        k = _trade_key(t)
        if k in seen:
            continue
        seen.add(k)
        led.append(t)
        added += 1
    return led, added


def main():
    print("=== poly_pinnacle_stats.py (Lag-Backtest-Ledger) ===")
    try:
        store = json.loads(SCAN_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        print(f"  ℹ️  {SCAN_FILE.name} fehlt/leer — nichts zu rechnen.")
        return 0
    now = datetime.now(timezone.utc)
    try:
        prev = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        prev = {}
    new = run(store, now=now)                       # nur abgeschlossene Spiele -> fertige Round-Trips
    ledger, added = merge_ledger(prev.get("trades"), new["trades"])
    ledger.sort(key=lambda t: t["entryTs"], reverse=True)
    presets = {}                                    # Sensitivitaet auf dem AKTUELLEN Fenster
    for mm in (1.5, 3.0, 5.0):
        presets[f"move>={mm:.1f}pp"] = run(store, now=now, move_min=mm)["overall"]
    out = {
        "_meta": {"generatedAt": now.isoformat(),
                  "params": {"moveMinPP": MOVE_MIN_PP, "entryEdgePP": ENTRY_EDGE_PP,
                             "exitEdgePP": EXIT_EDGE_PP, "minSnaps": MIN_SNAPS},
                  "gamesScanned": len(store.get("games", {})), "tradesAdded": added,
                  "ledgerSize": len(ledger)},
        "overall": _agg(ledger), "byLeague": _by_league(ledger), "presets": presets,
        "trades": ledger[:MAX_TRADES_OUT],
    }
    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    o = out["overall"]
    print(f"  → +{added} neu · Ledger {len(ledger)} Round-Trips · Ø {o['avgGainPP']:+.2f}pp · "
          f"Ø {o['avgRoiPct']:+.2f}% ROI · {o['winRatePct']:.0f}% Treffer → {OUT_FILE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
