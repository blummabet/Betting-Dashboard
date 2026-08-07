#!/usr/bin/env python3
"""
build_dashboard_pulse.py — winziger Performance-Puls für die Übersicht (30.07.2026, Lucas).

Liest die drei Signal-Ledger (liga/mls/wm), nimmt die LETZTEN 30 abgerechneten Picks (nach
resolvedAt) und verdichtet sie zu einer ~1-KB-Datei `dashboard_pulse.json`, die die Übersicht
ohne die schweren Ledger (WM allein ~113 KB) laden kann. Metriken:
  · avgClvPP    — Ø Closing Line Value (schlagen wir die Schlussquote?)  ← der Nordstern
  · pctBeatClose— Anteil Picks mit CLV > 0
  · winPct      — WIN / (WIN+LOSS), VOID/offene raus
  · series      — die 30 Einzel-CLVs (alt→neu) für die Sparkline
ROI bewusst NICHT: die Ledger speichern keine Quote je Pick. Kommt, sobald wir Quoten mitschreiben.
"""
from __future__ import annotations
import json, datetime as dt
from pathlib import Path

BASE = Path(__file__).resolve().parent
LEDGERS = ["liga_signal_ledger.json", "mls_signal_ledger.json", "wm_signal_ledger.json"]
N = 30


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _betfair_pulse(rec=None) -> dict | None:
    """Betfair-Geld-Signal-Bilanz (betfair_track_record.py → global). Win/Loss + ROI, KEIN CLV
    (Betfair-Track speichert kein Closing je Signal). Zeigt die Gesamt-Trefferquote/ROI aller
    abgerechneten Betfair-Signale."""
    g = ((rec if rec is not None else _load("betfair_track_record.json")) or {}).get("global") or {}
    if not g.get("n"):
        return None
    return {"n": g.get("n"),
            "hitPct": round(100.0 * (g.get("hitRate") or 0), 1),
            "roiPct": round(100.0 * (g.get("roi") or 0), 1)}


def _poly_pulse(track=None) -> dict | None:
    """Poly „Heute wetten"-Paper-Trade (poly_shortlist_track.py → agg.all). n/Treffer/ROI/Ø CLV
    der ganzen Shortlist + Zahl der offenen Plays."""
    d = track if track is not None else _load("poly_shortlist_track.json")
    a = ((d or {}).get("agg") or {}).get("all") or {}
    if not a.get("n"):
        return None
    return {"n": a.get("n"),
            "hitPct": round(100.0 * (a.get("hit") or 0), 1),
            "roiPct": round(100.0 * (a.get("roi") or 0), 1),
            "clvAvg": a.get("clvAvg"),
            "openN": len((d or {}).get("open") or {})}


def build() -> dict:
    recs = []
    for lf in LEDGERS:
        d = _load(lf)
        for r in (d.get("records") or []) if isinstance(d, dict) else []:
            if isinstance(r, dict) and r.get("resolvedAt"):
                recs.append(r)
    recs.sort(key=lambda r: str(r.get("resolvedAt")), reverse=True)
    last = recs[:N]
    last_chrono = list(reversed(last))                    # alt→neu für die Sparkline
    clvs = [r.get("clvPP") for r in last_chrono if isinstance(r.get("clvPP"), (int, float))]
    wins = sum(1 for r in last if str(r.get("result")).upper() == "WIN")
    losses = sum(1 for r in last if str(r.get("result")).upper() == "LOSS")
    graded = wins + losses
    avg = round(sum(clvs) / len(clvs), 2) if clvs else None
    beat = round(100.0 * sum(1 for c in clvs if c > 0) / len(clvs), 1) if clvs else None
    win = round(100.0 * wins / graded, 1) if graded else None
    return {
        "_meta": {"description": "Übersicht-Puls: letzte %d abgerechnete Picks (CLV/Trefferquote)." % N,
                  "updated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
        "n": len(last), "nClv": len(clvs), "nGraded": graded,
        "avgClvPP": avg, "pctBeatClose": beat, "winPct": win, "wins": wins, "losses": losses,
        "series": [round(c, 2) for c in clvs],
        "oldest": (last_chrono[0].get("resolvedAt") if last_chrono else None),
        "newest": (last[0].get("resolvedAt") if last else None),
        "betfair": _betfair_pulse(),   # 07.08.2026 (Lucas): Betfair-Tracking mit in den Puls
        "poly": _poly_pulse(),         # 07.08.2026 (Lucas): Poly „Heute wetten" mit in den Puls
    }


def main():
    out = build()
    (BASE / "dashboard_pulse.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print("dashboard_pulse.json:", {k: out[k] for k in ("n", "avgClvPP", "pctBeatClose", "winPct")},
          "| betfair", out.get("betfair"), "| poly", out.get("poly"))


if __name__ == "__main__":
    main()
