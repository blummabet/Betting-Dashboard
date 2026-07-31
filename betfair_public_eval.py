#!/usr/bin/env python3
"""
betfair_public_eval.py — Tracking & Auswertung der ÖFFENTLICHEN Betfair-Moneyflow/Halftime-Pushs
(31.07.2026, Lucas: „schaffst du die public Pushs zu tracken und auszuwerten?").

betfair_alerts.py loggt jeden gesendeten Public-Push nach betfair_public_ledger.json (pending).
Hier: den HT-Stand einfangen, fertige Spiele gegen End-/Halbzeitstand abrechnen (dieselben Grading-
Funktionen wie der Liga-Track-Record) und zu einer Bilanz zusammenfassen (Trefferquote + ROI, je
Szenario/Markt) → betfair_public_record.json. Bewertet: „lag das Geld, dem der Push folgte, richtig?"

Läuft im betfair.yml direkt NACH betfair_alerts.py (Mac-Runner, alle 15 Min). REIN/testbar.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Grading aus dem bestehenden Track-Record wiederverwenden (kein Duplikat).
from betfair_track_record import fav_token, winning_token, grade, MARKETS

BASE = Path(__file__).resolve().parent
LEDGER_FILE = BASE / "betfair_public_ledger.json"
RECORD_FILE = BASE / "betfair_public_record.json"
PENDING_TTL_H = 72          # nie „finished" gesehen nach 3 Tagen → als nicht abrechenbar verwerfen
LEDGER_KEEP = 800


def _now():
    return datetime.now(timezone.utc)


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _by_id(prices):
    return {str(m.get("matchId")): m for m in (prices.get("matches") or [])}


def capture_ht(ledger, prices, now=None):
    """Halbzeit-Stand für noch offene Pushs einfangen (für HT-Märkte nötig; für FT harmlos)."""
    idx = _by_id(prices)
    for e in ledger:
        if e.get("status") != "pending" or e.get("htScore") is not None:
            continue
        m = idx.get(str(e.get("matchId")))
        if not m:
            continue
        li = m.get("liveInfo") or {}
        tt = li.get("time")
        at_ht = li.get("is_ht") or (isinstance(tt, (int, float)) and 43 <= tt <= 60)
        if at_ht and li.get("goal_v1") is not None and not li.get("finished"):
            e["htScore"] = [li.get("goal_v1"), li.get("goal_v2")]
    return ledger


def settle(ledger, prices, now=None):
    """Fertige Spiele abrechnen. Setzt status won/lost/void + profit (1 Einheit Einsatz). REIN."""
    now = now or _now()
    idx = _by_id(prices)
    for e in ledger:
        if e.get("status") != "pending":
            continue
        m = idx.get(str(e.get("matchId")))
        if m:
            li = m.get("liveInfo") or {}
            if li.get("finished"):
                ft = [li.get("goal_v1"), li.get("goal_v2")] if li.get("goal_v1") is not None else None
                ht = e.get("htScore")
                if ht is None and li.get("goal_v1") is not None and (li.get("is_ht")):
                    ht = [li.get("goal_v1"), li.get("goal_v2")]
                fav = fav_token(e.get("market"), e.get("leadName"), e.get("home"), e.get("away"))
                win, ok = grade(fav, e.get("market"), ft, ht)
                e["settledAt"] = now.isoformat()
                e["ftScore"] = ft
                if not ok:
                    e["status"] = "void"          # nicht abrechenbar (z.B. HT-Markt ohne HT-Stand)
                    continue
                odd = e.get("leadOdd")
                e["status"] = "won" if win else "lost"
                e["profit"] = (float(odd) - 1.0) if (win and isinstance(odd, (int, float))) else (-1.0 if not win else 0.0)
                continue
        # nie „finished" gesehen & zu alt → verwerfen (Spiel aus dem Feed gefallen)
        try:
            st = datetime.fromisoformat(str(e.get("sentAt")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            st = None
        if st is not None and st < now - timedelta(hours=PENDING_TTL_H):
            e["status"] = "expired"
    return ledger


def summarize(ledger, now=None):
    now = now or _now()
    res = [e for e in ledger if e.get("status") in ("won", "lost")]
    pend = sum(1 for e in ledger if e.get("status") == "pending")

    def agg(rows):
        n = len(rows)
        wins = sum(1 for e in rows if e.get("status") == "won")
        profit = sum(float(e.get("profit") or 0) for e in rows)
        odds = [float(e["leadOdd"]) for e in rows if isinstance(e.get("leadOdd"), (int, float))]
        return {"n": n, "wins": wins,
                "hitRate": round(wins / n, 4) if n else None,
                "roi": round(profit / n, 4) if n else None,
                "avgOdd": round(sum(odds) / len(odds), 2) if odds else None}

    by_scn, by_mkt = {}, {}
    for scn in ("fresh", "ht"):
        rows = [e for e in res if e.get("scenario") == scn]
        if rows:
            by_scn[scn] = agg(rows)
    for mk in sorted({e.get("market") for e in res if e.get("market")}):
        by_mkt[mk] = agg([e for e in res if e.get("market") == mk])

    recent = [{"home": e.get("home"), "away": e.get("away"), "league": e.get("league"),
               "market": e.get("market"), "leadName": e.get("leadName"), "leadOdd": e.get("leadOdd"),
               "won": e.get("status") == "won", "settledAt": e.get("settledAt")}
              for e in sorted(res, key=lambda x: str(x.get("settledAt") or ""), reverse=True)[:15]]

    out = agg(res)
    out.update({"generatedAt": now.isoformat(), "pending": pend,
                "byScenario": by_scn, "byMarket": by_mkt, "recent": recent})
    return out


def main():
    ledger = _load(LEDGER_FILE, [])
    if not isinstance(ledger, list):
        ledger = []
    prices = _load(BASE / "betfair_prices.json", {})
    ledger = capture_ht(ledger, prices)
    ledger = settle(ledger, prices)
    # abgeschlossene/verworfene lange behalten fürs Ledger, aber deckeln
    ledger = ledger[-LEDGER_KEEP:]
    record = summarize(ledger)
    try:
        json.dump(ledger, open(LEDGER_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        json.dump(record, open(RECORD_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as e:
        print("Schreibfehler:", e)
    print("Public-Eval: %d abgerechnet (%s%% Treffer, ROI %s) · %d offen"
          % (record["n"], round((record["hitRate"] or 0) * 100), record["roi"], record["pending"]))


if __name__ == "__main__":
    main()
