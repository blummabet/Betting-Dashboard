#!/usr/bin/env python3
# poly_direct_bets.py — 24.08.2026 (Lucas: „kriegen wir hin, dass ich von 'Heute' gleich die Wette
# auslöse?"). Abrechnung der DIREKT aus dem „Heute"-Tab gesetzten Wetten.
#
# Warum eine eigene Abrechnung: diese Bets haben kein Fixture. Ein Tennis- oder E-Sport-Play steht
# in keiner *-data.json, also findet `resolve_wm_results.py` sie nie — sie blieben ewig ohne
# Ergebnis, und damit ohne P&L und ohne CLV (= gegen den Nordstern). Sie tragen aber seit heute
# `polyKey` (= Poly-Event-Slug) + `side`, und `poly_resolutions.json` kennt den Sieger je Slug.
# Das reicht für eine vollständige Abrechnung, ganz ohne Fixture.
#
# Der Rechenweg ist ABSICHTLICH identisch zum Papier-Depot (poly_shortlist_track.py):
# Aktien = stake/entry, Gewinner zahlt 1.00/Aktie, CLV = (Schluss − Einstieg) × 100.
# Nur so ist „Papier vs. echt" eine ehrliche Gegenüberstellung derselben Engine.
#
# Datenfluss (read-only bis auf die eigene Ausgabedatei):
#   picks_history.json            → platzierte Bets mit polyKey (schreibt polymarket_bet.py)
#   poly_money_broad_close.json   → Schluss-Referenz je Slug/Seite (für CLV)
#   poly_resolutions.json         → {key:{winner,ts}}
#   poly_direct_bets.json         → open/settled/agg  (diese Datei)
#
# Setzt und sendet NICHTS. Offene Bets verfallen NIE automatisch — anders als im Papier-Depot
# steht hier echtes Geld; ein unauflösbarer Bet muss sichtbar bleiben (Guard direct_bets_settling).
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from safe_write import write_json_atomic   # 25.08.2026: temp+replace statt halber Datei
from poly_slug_urteil import aufloesbar   # 04.09.2026: Buendel-Slugs nicht raten

BASE = Path(__file__).resolve().parent

HISTORY_FILE = "picks_history.json"
CLOSE_FILE = "poly_money_broad_close.json"
RES_FILE = "poly_resolutions.json"
OUT_FILE = "poly_direct_bets.json"

SETTLED_KEEP = int(os.environ.get("DIRECT_BETS_KEEP") or 500)


def _now():
    return datetime.now(timezone.utc)


def _load(name, default=None):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def _ok_price(p):
    return isinstance(p, (int, float)) and 0 < p < 1


def _age_days(ts, now):
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (now - t).total_seconds() / 86400.0
    except (ValueError, TypeError):
        return None


def collect_bets(history) -> list[dict]:
    """Alle direkt gesetzten Poly-Bets aus picks_history. REIN.

    Kriterium: der Bet trägt `polyKey` + `side` (setzt polymarket_bet.py nur bei Direkt-Orders
    aus dem „Heute"-Tab) und wurde tatsächlich platziert. Ein Bet ohne sauberen Einstiegspreis
    ist nicht abrechenbar und fliegt raus — lieber gar nicht zählen als falsch zählen.
    """
    out = []
    for fx in (history or []):
        if not isinstance(fx, dict):
            continue
        for b in (fx.get("polyBets") or []):
            if not isinstance(b, dict):
                continue
            key, side = b.get("polyKey"), b.get("side")
            if not key or not side:
                continue
            if str(b.get("status") or "") != "placed":
                continue
            if not _ok_price(b.get("polyPrice")):
                continue
            out.append({
                "betId": b.get("orderId") or f"{key}|{side}|{b.get('placedAt')}",
                "key": key, "side": side,
                "entryPrice": round(float(b["polyPrice"]), 4),
                "stake": float(b.get("stake") or 0),
                "placedAt": b.get("placedAt"),
                "league": fx.get("league") or "",
                "sport": b.get("sport") or "",
                "conv": b.get("conviction"),
                "match": f"{fx.get('home', '')} vs {fx.get('away', '')}".strip(" vs "),
            })
    return out


def settle(bets, close, resolutions, now=None, prev=None) -> dict:
    """Bets gegen die Slug-Auflösung abrechnen. REIN/testbar.

    close liefert die Schluss-Referenz für den CLV (eingefrorener Preis der gesetzten Seite);
    fehlt sie, ist der CLV 0 statt erfunden — genau wie im Papier-Depot.
    """
    now = now or _now()
    prev_settled = {s.get("betId"): s for s in ((prev or {}).get("settled") or []) if isinstance(s, dict)}
    open_, settled = [], []

    for b in bets:
        if b["betId"] in prev_settled:
            settled.append(prev_settled[b["betId"]])        # einmal abgerechnet bleibt abgerechnet
            continue
        cp = ((close.get(b["key"]) or {}).get("prices") or {}).get(b["side"]) if isinstance(close, dict) else None
        close_ref = float(cp) if _ok_price(cp) else None
        r = resolutions.get(b["key"]) if isinstance(resolutions, dict) else None
        winner = (r or {}).get("winner")
        # 04.09.2026: ein Buendel-Slug ("-more-markets") kann Over 1,5 und Over 2,5 nicht
        # auseinanderhalten. Wo der Sieger-Name die Linie nicht traegt, wird NICHT
        # abgerechnet — der Eintrag bleibt offen statt einen Ausgang zu erfinden.
        if winner and not aufloesbar(b["key"], b.get("side"), winner):
            winner = None
        if not winner:
            row = dict(b)
            row["closePrice"] = round(close_ref, 4) if close_ref else None
            row["ageDays"] = round(_age_days(b.get("placedAt"), now) or 0, 2)
            open_.append(row)
            continue
        entry, st = float(b["entryPrice"]), float(b["stake"])
        win = (b["side"] == winner)
        pnl = (st / entry - st) if win else -st              # Aktien = stake/entry, Gewinner zahlt 1.00
        clv = round(((close_ref if close_ref else entry) - entry) * 100, 2)
        row = dict(b)
        row.update({"result": "win" if win else "loss", "winner": winner,
                    "closePrice": round(close_ref, 4) if close_ref else None,
                    "clvPP": clv, "pnl": round(pnl, 2),
                    "settledTs": now.isoformat(), "resolvedTs": (r or {}).get("ts")})
        settled.append(row)

    settled = settled[-SETTLED_KEEP:]
    return {"updatedAt": now.isoformat(), "open": open_, "settled": settled,
            "agg": aggregate(settled), "bySport": aggregate_by(settled, "sport"),
            "byConv": aggregate_by(settled, "conv")}


def aggregate(rows) -> dict:
    rows = [r for r in (rows or []) if isinstance(r, dict) and r.get("result")]
    n = len(rows)
    if not n:
        return {"n": 0, "wins": 0, "hit": None, "pnl": 0.0, "stake": 0.0, "roi": None, "clvAvg": None}
    wins = sum(1 for r in rows if r["result"] == "win")
    pnl = sum(float(r.get("pnl") or 0) for r in rows)
    stake = sum(float(r.get("stake") or 0) for r in rows)
    clvs = [float(r["clvPP"]) for r in rows if isinstance(r.get("clvPP"), (int, float))]
    return {"n": n, "wins": wins, "hit": round(wins / n, 4), "pnl": round(pnl, 2),
            "stake": round(stake, 2), "roi": (round(pnl / stake, 4) if stake else None),
            "clvAvg": (round(sum(clvs) / len(clvs), 2) if clvs else None)}


def aggregate_by(rows, field) -> dict:
    buckets = {}
    for r in (rows or []):
        if not isinstance(r, dict) or not r.get("result"):
            continue
        buckets.setdefault(str(r.get(field) if r.get(field) not in (None, "") else "?"), []).append(r)
    return {k: aggregate(v) for k, v in buckets.items()}


def main() -> int:
    bets = collect_bets(_load(HISTORY_FILE, []))
    out = settle(bets, _load(CLOSE_FILE), _load(RES_FILE), prev=_load(OUT_FILE))
    write_json_atomic((BASE / OUT_FILE), out, indent=1)
    a = out["agg"]
    print(f"🎯 Direkt-Bets: {len(bets)} platziert · {len(out['open'])} offen · {a['n']} abgerechnet"
          + (f" · Treffer {a['hit']*100:.0f}% · P&L ${a['pnl']:.2f}"
             f" · ROI {a['roi']*100:.1f}%" if a["n"] else ""))
    for row in out["open"]:
        if (row.get("ageDays") or 0) > 3:
            print(f"   ⏳ offen seit {row['ageDays']:.1f} Tagen: {row['key']} → {row['side']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
