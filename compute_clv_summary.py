#!/usr/bin/env python3
"""compute_clv_summary.py — CLV-Scoreboard für Steam-Card-Picks (28.06.2026, Lucas).

CLV (Closing Line Value) ist der ehrliche Nordstern des Steam-Followings: schlagen wir
KONSISTENT die Closing-Linie? resolve_steam_clv.py setzt `clvPP` pro aufgelöstem Steam-Pick;
DIESES Modul aggregiert sie zur Bilanz — verlässlicher als Win/Loss, weil es die Varianz
rausrechnet (man kann mit +CLV verlieren und mit −CLV gewinnen; langfristig zahlt CLV).

Ausgabe ({wm_,liga_}clv_summary.json):
  overall : n, avgClvPP, pctBeatClose (Anteil clvPP>0), coverage (Closing erfasst / aufgelöst)
  byMarket / byLeague / byTime(Spieltag) : je n, avgClvPP, pctBeatClose

Reine Auswertung — verändert die Picks NICHT. Dataset-aware (cocobet_dataset).
Lauf nach resolve_steam_clv (z.B. im fetch-results- / update-liga-Workflow).
"""
from __future__ import annotations
import json
from datetime import datetime, timezone

import cocobet_dataset as D

OUT = D.file("wm_clv_summary.json", "liga_clv_summary.json")

# pick.result-Konventionen: Python-Pipeline schreibt UPPERCASE (WIN/LOSS/VOID).
# Lowercase (won/lost/push) defensiv mit-akzeptiert (s. project_wm_tracking_results).
_RESOLVED = {"WIN", "LOSS", "VOID", "WON", "LOST", "PUSH"}


def market_category(market: str) -> str:
    """Pick-Markt → grobe Kategorie für die Bilanz."""
    m = (market or "").lower()
    if "doppelte chance" in m or "double chance" in m:
        return "Doppelte Chance"
    if any(w in m for w in ("über", "unter", "over", "under", "o2.5", "u2.5", "tore")):
        return "Über/Unter"
    if "beide teams" in m or "btts" in m or "gg" in m or "ng" in m:
        return "BTTS"
    if "handicap" in m or m.startswith("ah ") or "asian" in m:
        return "Handicap"
    if any(w in m for w in ("heimsieg", "auswärtssieg", "unentschieden", "remis", "dnb", "1x2", "doppel")):
        return "1X2/DNB"
    return "Sonstige"


def _agg(clvs: list[float]) -> dict:
    n = len(clvs)
    if not n:
        return {"n": 0, "avgClvPP": None, "pctBeatClose": None}
    beat = sum(1 for c in clvs if c > 0)
    return {"n": n, "avgClvPP": round(sum(clvs) / n, 2), "pctBeatClose": round(beat / n * 100, 1)}


def _md_sort_key(s: str):
    try:
        return (0, float(s))
    except (TypeError, ValueError):
        return (1, str(s))


def build_summary(wm: dict) -> dict:
    """Aggregiert clvPP aller aufgelösten Steam-Picks. Reine Funktion (testbar)."""
    picks_map = wm.get("picks") or {}
    n_resolved = 0          # aufgelöste Steam-Picks (haben ein Ergebnis)
    rows = []               # davon mit Closing-Linie (clvPP gesetzt)
    # BET-Quote (28.06.2026, Lucas: bei ~50 Spielen/Runde dürfen nicht zu viele BET werden) —
    # über ALLE Steam-BET/ABWÄGEN-Picks (auch ungespielte), pro Liga + gesamt.
    vcount = {}             # league → {"BET": n, "ABWÄGEN": n}
    for key, plist in picks_map.items():
        if not isinstance(plist, list):
            continue
        parts = str(key).split("-")
        league = parts[0] if parts else "?"
        matchday = parts[1] if len(parts) > 1 else "?"
        for p in plist:
            if not isinstance(p, dict):
                continue
            if p.get("source") != "steam" or p.get("trackingExcluded"):
                continue
            verdict = p.get("verdict")
            if verdict in ("BET", "ABWÄGEN"):
                vcount.setdefault(league, {"BET": 0, "ABWÄGEN": 0})[verdict] += 1
            if str(p.get("result") or "").upper() not in _RESOLVED:
                continue   # noch nicht gespielt
            n_resolved += 1
            clv = p.get("clvPP")
            if clv is None or not p.get("clvResolved"):
                continue   # kein Closing erfasst → zählt nur in die Abdeckung
            rows.append({"clvPP": float(clv), "market": market_category(p.get("market", "")),
                         "league": league, "matchday": matchday, "verdict": verdict})

    by_market, by_league, by_time, by_verdict = {}, {}, {}, {}
    for r in rows:
        by_market.setdefault(r["market"], []).append(r["clvPP"])
        by_league.setdefault(r["league"], []).append(r["clvPP"])
        by_time.setdefault(r["matchday"], []).append(r["clvPP"])
        if r["verdict"]:
            by_verdict.setdefault(r["verdict"], []).append(r["clvPP"])

    def _bet_rate(c):
        tot = (c.get("BET", 0) + c.get("ABWÄGEN", 0))
        return round(c.get("BET", 0) / tot * 100, 1) if tot else None

    overall_v = {"BET": 0, "ABWÄGEN": 0}
    for c in vcount.values():
        overall_v["BET"] += c["BET"]; overall_v["ABWÄGEN"] += c["ABWÄGEN"]

    cov = len(rows)
    overall = _agg([r["clvPP"] for r in rows])
    overall["coverage"] = {
        "withClosing": cov, "resolved": n_resolved,
        "pct": round(cov / n_resolved * 100, 1) if n_resolved else None,
    }
    return {
        "_meta": {"dataset": D.active_dataset(),
                  "generatedAt": datetime.now(timezone.utc).isoformat()},
        "overall": overall,
        "byVerdict": {k: _agg(v) for k, v in by_verdict.items()},
        "betRate": {"overall": _bet_rate(overall_v),
                    "byLeague": {k: _bet_rate(c) for k, c in sorted(vcount.items())},
                    "counts": overall_v},
        "byMarket": {k: _agg(v) for k, v in sorted(by_market.items())},
        "byLeague": {k: _agg(v) for k, v in sorted(by_league.items())},
        "byTime": [{"bucket": k, **_agg(v)} for k, v in
                   sorted(by_time.items(), key=lambda kv: _md_sort_key(kv[0]))],
    }


def main() -> None:
    wm = json.loads(D.data_file().read_text(encoding="utf-8"))
    summary = build_summary(wm)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    ov = summary["overall"]
    print(f"✅ CLV-Summary ({D.active_dataset()}): n={ov['n']} avgCLV={ov['avgClvPP']} "
          f"beat={ov['pctBeatClose']}% coverage={ov['coverage']['pct']}% → {OUT.name}")


if __name__ == "__main__":
    main()
