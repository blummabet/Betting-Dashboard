#!/usr/bin/env python3
# build_betfair_overview.py — 02.08.2026 (Lucas): kompakter Sidecar für die ÜBERSICHT (erster
# Menüpunkt). Der Übersicht-Blick soll knackig & schnell sein — er darf NICHT die 6,8 MB History
# laden. Darum rechnet dieser Runner-Schritt (in betfair.yml, direkt nach dem Fetch) die zwei
# history-abhängigen Signale vor und schreibt sie als winzige betfair_overview.json:
#
#   • steam  — Vor-Anpfiff-Spiele mit der stärksten 1X2-Quotenbewegung (Implied-Prob-pp, erster→
#              letzter Snapshot). Spiegelt exakt die moveOf-Definition des Radars (bounded ±100,
#              Schwelle ≥1,5pp, live/gestartet ausgeschlossen). „Wohin wandert das schlaue Geld,
#              bevor der Ball rollt."
#   • flow   — größter frischer Zufluss (€) je Spiel seit dem letzten Snapshot. „Was kippt gerade rein."
#
# Die dritte Kachel (Fehlbepreisung/Kohärenz) rechnet die Übersicht CLIENT-SEITIG über die schon
# geladene betfair_prices.json (window._bfCoherence) — kein Poisson-Nachbau in Python, kein Drift.
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRICES = "betfair_prices.json"
HIST = "betfair_history.json"
OUT = "betfair_overview.json"

MOVE_MIN_PP = 1.5      # = Radar moveOf: schwächere Bewegungen ignorieren
FLOW_MIN_EUR = 2000    # = Radar FLOW_MIN_EUR: Zufluss erst ab so viel zeigen
TOP_STEAM = 5
TOP_FLOW = 5
KICKOFF_GRACE_S = 60   # winzige Toleranz, damit ein Spiel exakt bei Anpfiff nicht flackert


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_ts(t):
    if not isinstance(t, str) or not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except Exception:
        return None


def _num(x):
    return x if isinstance(x, (int, float)) else None


def implied_move(first_mo, last_mo):
    """Spiegelt Radar moveOf: stärkste Implied-Prob-Differenz (pp) auf hw/dr/aw, erster→letzter
    Snapshot. pp>0 = Quote fällt = auf diesen Ausgang wird gesetzt. Bounded, weil 1/odd∈(0,1)."""
    if not isinstance(first_mo, dict) or not isinstance(last_mo, dict):
        return None
    best = None
    for k in ("hw", "dr", "aw"):
        a, b = _num(first_mo.get(k)), _num(last_mo.get(k))
        if a is not None and b is not None and a > 1 and b > 1:
            pp = (1 / b - 1 / a) * 100
            if best is None or abs(pp) > abs(best[1]):
                best = (k, pp)
    if best and abs(best[1]) >= MOVE_MIN_PP:
        return {"side": best[0], "pp": round(best[1], 1)}
    return None


def _side_name(side, m):
    return m.get("home") if side == "hw" else m.get("away") if side == "aw" else "Remis"


def _lead(mk):
    runners = (mk or {}).get("runners") or []
    best = None
    for r in runners:
        v = _num(r.get("vol")) or 0
        if best is None or v > (_num(best.get("vol")) or 0):
            best = r
    return best


def _biggest_market(m):
    """Markt mit dem meisten gematchten Geld + dessen Lead-Runner (für die Zufluss-Seite)."""
    best_name, best_tot, best_lead = None, -1, None
    for name, mk in (m.get("markets") or {}).items():
        runners = (mk or {}).get("runners") or []
        tot = sum((_num(r.get("vol")) or 0) for r in runners)
        if tot > best_tot:
            best_name, best_tot, best_lead = name, tot, _lead(mk)
    return best_name, best_lead


def _base(m):
    return {"matchId": m.get("matchId"), "home": m.get("home"), "away": m.get("away"),
            "country": m.get("country"), "league": m.get("league")}


def _is_upcoming(m, now):
    """Vor Anpfiff = Kickoff in der Zukunft und (noch) keine Live-Uhr. Genau der Zustand, in dem
    Geld↔Quote gültig ist — live wäre die Bewegung spiel-getrieben, nicht geld-getrieben."""
    li = m.get("liveInfo") or {}
    if li.get("time") is not None and not li.get("finished"):
        return False
    ko = _parse_ts(m.get("kickoff"))
    if ko is None:
        return False
    return (ko - now).total_seconds() > -KICKOFF_GRACE_S


def steam_list(prices, hist, now, top=TOP_STEAM):
    out = []
    for m in (prices.get("matches") or []):
        if not _is_upcoming(m, now):
            continue
        arr = hist.get(str(m.get("matchId")))
        if not isinstance(arr, list) or len(arr) < 2:
            continue
        mv = implied_move((arr[0] or {}).get("mo"), (arr[-1] or {}).get("mo"))
        if not mv:
            continue
        _, lead = _biggest_market(m)
        row = _base(m)
        row.update({"side": mv["side"], "sideName": _side_name(mv["side"], m), "pp": mv["pp"],
                    "odd": _num((m.get("mo") or {}).get(mv["side"])),
                    "kickoff": m.get("kickoff")})
        out.append(row)
    out.sort(key=lambda r: abs(r["pp"]), reverse=True)
    return out[:top]


def flow_list(prices, hist, top=TOP_FLOW):
    out = []
    by_id = {str(m.get("matchId")): m for m in (prices.get("matches") or [])}
    for mid, m in by_id.items():
        arr = hist.get(mid)
        if not isinstance(arr, list) or len(arr) < 2:
            continue
        a, b = arr[-2], arr[-1]
        d = (_num(b.get("totalVol")) or 0) - (_num(a.get("totalVol")) or 0)
        if d < FLOW_MIN_EUR:
            continue
        mkt, lead = _biggest_market(m)
        row = _base(m)
        row.update({"deltaEur": round(d), "nowEur": round(_num(b.get("totalVol")) or 0),
                    "market": mkt, "sideName": (lead or {}).get("name"),
                    "odd": _num((lead or {}).get("odd"))})
        out.append(row)
    out.sort(key=lambda r: r["deltaEur"], reverse=True)
    return out[:top]


def build(prices, hist, now):
    return {
        "_meta": {"description": "Übersicht-Sidecar: Vor-Anpfiff-Steam + frischer Zufluss (leicht, "
                                 "damit der erste Menüpunkt schnell bleibt). Fehlbepreisung rechnet "
                                 "die Übersicht client-seitig über _bfCoherence."},
        "generatedAt": now.isoformat(),
        "steam": steam_list(prices, hist, now),
        "flow": flow_list(prices, hist),
    }


def main() -> int:
    prices, hist = _load(PRICES), _load(HIST)
    if not isinstance(prices, dict) or not isinstance(hist, dict):
        print("ℹ️  betfair_prices/history fehlen — Übersicht-Sidecar übersprungen.")
        return 0
    data = build(prices, hist, datetime.now(timezone.utc))
    (BASE / OUT).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"📊 {OUT}: {len(data['steam'])} Steam · {len(data['flow'])} Zuflüsse geschrieben.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
