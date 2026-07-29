#!/usr/bin/env python3
"""
betfair_track_record.py — Track-Record / Backtest für das Betfair-Geld-Signal (29.07.2026, Lucas).

## Frage
Welche LIGA × MARKT (× Team) trifft wirklich, wenn man dem Betfair-Geld folgt? Beispiel: „In Ecuador
kommt viel auf HT-Sieg rein" — geht das dort historisch oft auf? Zwei Signale werden GETRENNT bewertet:
  · Konzentration  — der Geld-Favorit je Markt hat ≥ CONC_THRESHOLD des Marktgeldes
  · Zufluss        — in den Markt kam seit dem letzten Snapshot frisches Geld (mkv-Delta ≥ INFLOW_MIN)
Kennzahlen je Bucket: Trefferquote UND ROI (Gewinn zu den Quoten, wenn man den Geld-Favorit „backt").

## Ablauf (läuft nach fetch_betfair_betwatch.py auf dem Mac-Runner)
  1. capture(): für jedes VOR-Anpfiff-Spiel je Markt den Geld-Favorit + Flags festhalten (jeder Lauf
     überschreibt → am Ende steht das CLOSING-Signal). Live nahe Halbzeit den HT-Stand einfangen.
  2. settle(): sobald ein Spiel „finished" ist, jeden gemerkten Markt gegen End-/HT-Stand abrechnen.
  3. aggregate(): über alle abgerechneten Signale nach Liga×Markt und Team×Markt bündeln.
Reiner Kern (fav_token, winning_token, grade, capture, settle, aggregate) ist netz-frei/testbar.

## Dateien
  liest  betfair_prices.json (+ betfair_history.json für den Zufluss)
  führt  betfair_track_state.json    — pending Signale + eingefangener HT-Stand
         betfair_track_results.json  — abgerechnete Einzel-Signale (Ledger, gekappt)
  schreibt betfair_track_record.json — Aggregat fürs Dashboard
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRICES_FILE = BASE / "betfair_prices.json"
HISTORY_FILE = BASE / "betfair_history.json"
STATE_FILE = BASE / "betfair_track_state.json"
RESULTS_FILE = BASE / "betfair_track_results.json"
RECORD_FILE = BASE / "betfair_track_record.json"

CONC_THRESHOLD = 0.65     # Geld-Favorit gilt als „konzentriert" ab so viel Marktanteil
INFLOW_MIN_EUR = 2000     # Markt gilt als „frischer Zufluss" ab so viel € Delta (prices sind €)
RESULTS_KEEP = 8000       # Ledger-Kappung
PENDING_TTL_H = 60        # pending ohne Settlement nach so vielen h nach Anpfiff verwerfen

# marketId → Typ. Genau die 7 Dashboard-Märkte.
MARKETS = {
    "Match Odds": "1x2",
    "Half Time": "ht1x2",
    "Over/Under 2.5 Goals": "ou25",
    "Over/Under 3.5 Goals": "ou35",
    "Both teams to Score?": "btts",
    "First Half Goals 0.5": "fho05",
    "First Half Goals 1.5": "fho15",
}


def _now():
    return datetime.now(timezone.utc)


# ── reine Grading-Logik ───────────────────────────────────────────────────────
def fav_token(market_id, runner_name, home, away):
    """Runner-Name → kanonisches Token (H/D/A · OVER/UNDER · YES/NO) je Markttyp. None wenn unklar."""
    t = MARKETS.get(market_id)
    if t in ("1x2", "ht1x2"):
        if runner_name == home:
            return "H"
        if runner_name == away:
            return "A"
        if runner_name == "The Draw":
            return "D"
        return None
    if t in ("ou25", "ou35", "fho05", "fho15"):
        n = str(runner_name or "").lower()
        if n.startswith("over"):
            return "OVER"
        if n.startswith("under"):
            return "UNDER"
        return None
    if t == "btts":
        n = str(runner_name or "").strip().lower()
        if n == "yes":
            return "YES"
        if n == "no":
            return "NO"
        return None
    return None


def winning_token(market_id, ft, ht):
    """Gewinner-Token aus End-(ft) bzw. Halbzeit-(ht) Stand [heim, ausw]. None wenn nicht abrechenbar."""
    t = MARKETS.get(market_id)
    if t == "1x2":
        if not ft:
            return None
        h, a = ft
        return "H" if h > a else "A" if a > h else "D"
    if t == "ht1x2":
        if not ht:
            return None
        h, a = ht
        return "H" if h > a else "A" if a > h else "D"
    if t == "ou25":
        return None if not ft else ("OVER" if (ft[0] + ft[1]) > 2.5 else "UNDER")
    if t == "ou35":
        return None if not ft else ("OVER" if (ft[0] + ft[1]) > 3.5 else "UNDER")
    if t == "btts":
        return None if not ft else ("YES" if (ft[0] > 0 and ft[1] > 0) else "NO")
    if t == "fho05":
        return None if not ht else ("OVER" if (ht[0] + ht[1]) > 0.5 else "UNDER")
    if t == "fho15":
        return None if not ht else ("OVER" if (ht[0] + ht[1]) > 1.5 else "UNDER")
    return None


def grade(fav, market_id, ft, ht):
    """→ (win, ok). ok=False, wenn nicht abrechenbar (z.B. HT-Markt ohne eingefangenen HT-Stand)."""
    wt = winning_token(market_id, ft, ht)
    if wt is None or fav is None:
        return (False, False)
    return (fav == wt, True)


# ── Snapshot-Helfer ───────────────────────────────────────────────────────────
def _lead(market):
    best = None
    for r in (market.get("runners") or []):
        v = r.get("vol") or 0
        if best is None or v > (best.get("vol") or 0):
            best = r
    return best


def _mkt_total(market):
    return sum((r.get("vol") or 0) for r in (market.get("runners") or []))


def _inflow_eur(history, mid, market_id):
    h = (history or {}).get(str(mid))
    if not isinstance(h, list) or len(h) < 2:
        return 0
    a, b = h[-2], h[-1]
    if not (isinstance(a, dict) and isinstance(b, dict) and a.get("mkv") and b.get("mkv")):
        return 0
    return (b["mkv"].get(market_id, 0) or 0) - (a["mkv"].get(market_id, 0) or 0)


def _is_prematch(m, now):
    li = m.get("liveInfo") or {}
    if li.get("time") is not None or li.get("finished"):
        return False
    try:
        kt = datetime.fromisoformat(str(m.get("kickoff")).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    return kt > now


# ── capture / settle / aggregate ──────────────────────────────────────────────
def capture(prices, history, state, now=None):
    """Vor-Anpfiff-Signale je Markt festhalten (Closing = letzter Lauf) + HT-Stand live einfangen. REIN."""
    now = now or _now()
    state = dict(state or {})
    pending = dict(state.get("pending") or {})
    for m in (prices.get("matches") or []):
        mid = str(m.get("matchId"))
        if mid in ("None", ""):
            continue
        li = m.get("liveInfo") or {}
        tt = li.get("time")
        # HT-Stand einfangen (nur solange live, nahe Halbzeit) — für die HT-Märkte
        if mid in pending and tt is not None and not li.get("finished"):
            if (li.get("is_ht") or (isinstance(tt, (int, float)) and 43 <= tt <= 60)) \
                    and pending[mid].get("htScore") is None and li.get("goal_v1") is not None:
                pending[mid]["htScore"] = [li.get("goal_v1"), li.get("goal_v2")]
        # Signale nur VOR Anpfiff aktualisieren
        if _is_prematch(m, now):
            home, away = m.get("home"), m.get("away")
            sigs = {}
            for mkid in MARKETS:
                mk = (m.get("markets") or {}).get(mkid)
                if not mk:
                    continue
                lead = _lead(mk)
                tot = _mkt_total(mk)
                if not lead or tot <= 0:
                    continue
                fav = fav_token(mkid, lead.get("name"), home, away)
                if fav is None:
                    continue
                share = (lead.get("vol") or 0) / tot
                sigs[mkid] = {"fav": fav, "share": round(share, 3), "odd": lead.get("odd"),
                              "conc": share >= CONC_THRESHOLD,
                              "inflow": _inflow_eur(history, mid, mkid) >= INFLOW_MIN_EUR}
            if sigs:
                pending[mid] = {"league": m.get("league"), "home": home, "away": away,
                                "country": m.get("country"), "kickoff": m.get("kickoff"),
                                "signals": sigs, "htScore": (pending.get(mid) or {}).get("htScore")}
    state["pending"] = pending
    return state


def settle(prices, state, results, now=None):
    """Fertige Spiele abrechnen → results-Ledger. Entfernt settled + zu alte pending. REIN."""
    now = now or _now()
    state = dict(state or {})
    pending = dict(state.get("pending") or {})
    results = list(results or [])
    for m in (prices.get("matches") or []):
        li = m.get("liveInfo") or {}
        if not li.get("finished"):
            continue
        mid = str(m.get("matchId"))
        pend = pending.get(mid)
        if not pend:
            continue
        ft = [li.get("goal_v1"), li.get("goal_v2")] if li.get("goal_v1") is not None else None
        ht = pend.get("htScore")
        for mkid, sig in (pend.get("signals") or {}).items():
            win, ok = grade(sig["fav"], mkid, ft, ht)
            if not ok:
                continue
            results.append({"league": pend.get("league"), "market": mkid,
                            "home": pend.get("home"), "away": pend.get("away"), "country": pend.get("country"),
                            "fav": sig["fav"], "odd": sig["odd"],
                            "conc": bool(sig.get("conc")), "inflow": bool(sig.get("inflow")),
                            "win": bool(win), "settledAt": now.isoformat()})
        pending.pop(mid, None)
    # zu alte pending (nie „finished" gesehen) verwerfen
    cutoff = now - timedelta(hours=PENDING_TTL_H)
    for mid in list(pending.keys()):
        try:
            kt = datetime.fromisoformat(str(pending[mid].get("kickoff")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            kt = None
        if kt is not None and kt < cutoff:
            pending.pop(mid, None)
    state["pending"] = pending
    return state, results[-RESULTS_KEEP:]


def _bucket():
    return {"n": 0, "wins": 0, "roiSum": 0.0,
            "nConc": 0, "winsConc": 0, "roiConc": 0.0,
            "nInflow": 0, "winsInflow": 0, "roiInflow": 0.0}


def _add(b, r):
    try:
        odd = float(r.get("odd"))
    except (TypeError, ValueError):
        odd = None
    profit = ((odd - 1.0) if r.get("win") else -1.0) if odd and odd > 1 else 0.0
    b["n"] += 1
    b["wins"] += 1 if r.get("win") else 0
    b["roiSum"] += profit
    if r.get("conc"):
        b["nConc"] += 1; b["winsConc"] += 1 if r.get("win") else 0; b["roiConc"] += profit
    if r.get("inflow"):
        b["nInflow"] += 1; b["winsInflow"] += 1 if r.get("win") else 0; b["roiInflow"] += profit


def _fin(b):
    def rate(w, n):
        return round(w / n, 4) if n else None
    return {"n": b["n"], "wins": b["wins"], "hitRate": rate(b["wins"], b["n"]),
            "roi": round(b["roiSum"] / b["n"], 4) if b["n"] else None,
            "nConc": b["nConc"], "hitRateConc": rate(b["winsConc"], b["nConc"]),
            "roiConc": round(b["roiConc"] / b["nConc"], 4) if b["nConc"] else None,
            "nInflow": b["nInflow"], "hitRateInflow": rate(b["winsInflow"], b["nInflow"]),
            "roiInflow": round(b["roiInflow"] / b["nInflow"], 4) if b["nInflow"] else None}


def aggregate(results, now=None):
    """Ledger → {byLeagueMarket, byTeamMarket} mit Trefferquote + ROI, je gesamt/konz/zufluss. REIN."""
    now = now or _now()
    lm, tm = {}, {}
    for r in (results or []):
        lk = "%s|%s" % (r.get("league"), r.get("market"))
        lm.setdefault(lk, _bucket()); _add(lm[lk], r)
        for team in (r.get("home"), r.get("away")):
            if not team:
                continue
            tk = "%s|%s" % (team, r.get("market"))
            tm.setdefault(tk, _bucket()); _add(tm[tk], r)
    return {"generatedAt": now.isoformat(), "n": len(results or []),
            "concThreshold": CONC_THRESHOLD, "inflowMinEur": INFLOW_MIN_EUR,
            "byLeagueMarket": {k: _fin(v) for k, v in lm.items()},
            "byTeamMarket": {k: _fin(v) for k, v in tm.items()}}


# ── I/O (main) ────────────────────────────────────────────────────────────────
def _load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    print("=== betfair_track_record.py ===")
    prices = _load(PRICES_FILE, {})
    if not prices.get("matches"):
        print("  ℹ️  keine betfair_prices.json — übersprungen (kein Wipe).")
        return 0
    history = _load(HISTORY_FILE, {})
    state = _load(STATE_FILE, {})
    results = _load(RESULTS_FILE, [])
    if not isinstance(results, list):
        results = []
    now = _now()
    state = capture(prices, history, state, now=now)
    state, results = settle(prices, state, results, now=now)
    record = aggregate(results, now=now)
    _write(STATE_FILE, state)
    _write(RESULTS_FILE, results)
    _write(RECORD_FILE, record)
    print("  ✅  %d pending · %d abgerechnet · %d Liga×Markt · %d Team×Markt"
          % (len(state.get("pending", {})), len(results),
             len(record["byLeagueMarket"]), len(record["byTeamMarket"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
