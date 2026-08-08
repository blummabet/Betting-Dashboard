#!/usr/bin/env python3
"""
betfair_draw_tracker.py -- Draw-Geld-Tracker (07.08.2026, Lucas).

## Frage
Lucas: "es kommen bei Betfair oft Spiele rein wo das Draw gespielt wird mit hohen Einsaetzen. Meine
Meinung ist dass das Trader-Moves sind, die da raustraden je laenger es X steht. Frage ist wie oft das
kommt, wenn diese Maerkte bespielt werden -- nach X auf dem 1x2-Markt suchen wo hohe Einsaetze waren
und dann ob das Spiel (Unentschieden) kam oder nicht."

Der bestehende Track-Record haelt nur den GELD-FUEHRER je Markt fest (fav=D war nur 19x in 10 Tagen) und
nur den PRE-MATCH-Schlussstand -- er misst Lucas' In-Play-Trade-Out-Mechanismus gar nicht. Dieses Modul
schreibt daher pro Match-Odds-Spiel gezielt die Draw-Dynamik mit:
  · Pre-Match:  Draw-Anteil am 1x2-Geld, Draw-Quote, Draw-Volumen, ob Draw der Geld-Fuehrer ist, wieviel
                frisches Geld vor Anpfiff aufs X kam (Summe positiver Draw-Vol-Deltas).
  · In-Play:    wieviel Geld WAEHREND 0:0 / Gleichstand aufs X kommt (der Trade-Out-Verdacht), plus die
                Draw-Quoten-Bewegung (kuerzeste In-Play-Quote vs. letzte -> erst rein, dann raustraden).
  · Settle:     kam X am Ende (ft[0]==ft[1])? -- ueber "finished" ODER Verschwinde-Settle (wie track_record).
Aggregat vergleicht: kommt X bei "viel Draw-Geld" oefter oder SELTENER als der Markt/Basisrate impliziert?

## Dateien
  liest    betfair_prices.json (per-Runner Draw-Volumen + liveInfo je Lauf)
  fuehrt   betfair_draw_state.json    -- pending Spiele + akkumulierte Draw-Metriken + letzter Live-Stand
           betfair_draw_results.json  -- abgerechnete Einzelspiele (Ledger, gekappt)
  schreibt betfair_draw_record.json   -- Aggregat fuers Dashboard

Reiner Kern (draw_metrics/capture/settle/aggregate) ist netz-frei/testbar. Laeuft im betfair.yml nach
betfair_track_record.py (alle 15 Min, Mac-Runner).
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRICES_FILE = BASE / "betfair_prices.json"
STATE_FILE = BASE / "betfair_draw_state.json"
RESULTS_FILE = BASE / "betfair_draw_results.json"
RECORD_FILE = BASE / "betfair_draw_record.json"

DRAW_MARKET = "Match Odds"
DRAW_NAME = "The Draw"
RESULTS_KEEP = 8000
PENDING_TTL_H = 60          # pending ohne Settlement nach so vielen h nach Anpfiff verwerfen

# "hohe Einsaetze aufs X" -- ein Spiel gilt als auffaellig, wenn EINES zutrifft:
NOTABLE_SHARE = 0.33        # Draw hat >= so viel Anteil am 1x2-Geld (normal hat X am wenigsten)
NOTABLE_INFLOW_EUR = 3000   # oder: so viel frisches Geld kam vor Anpfiff aufs X
# (oder der Draw ist ueberhaupt der Geld-Fuehrer -> drawLeader)

# Verschwinde-Settle (identisch zu betfair_track_record): Feed zeigt "finished" nur fluechtig.
VANISH_MIN_MINUTE = 85
VANISH_GRACE_MIN = 25


def _now():
    return datetime.now(timezone.utc)


# -- reine Metrik-Extraktion -----------------------------------------------------
def draw_metrics(m):
    """Aus einem Match die Draw-Kennzahlen des 1x2-Markts ziehen. None, wenn nicht bestimmbar."""
    mk = (m.get("markets") or {}).get(DRAW_MARKET)
    if not mk:
        return None
    runners = mk.get("runners") or []
    total = sum((r.get("vol") or 0) for r in runners)
    if total <= 0:
        return None
    dr = next((r for r in runners if r.get("name") == DRAW_NAME), None)
    if not dr:
        return None
    dvol = dr.get("vol") or 0
    lead = max(runners, key=lambda r: (r.get("vol") or 0))
    return {"drawVol": dvol, "moTotal": total,
            "drawShare": round(dvol / total, 4),
            "drawOdd": dr.get("odd"),
            "drawLeader": lead.get("name") == DRAW_NAME}


def _blank(m):
    return {"league": m.get("league"), "home": m.get("home"), "away": m.get("away"),
            "country": m.get("country"), "kickoff": m.get("kickoff"),
            "pre": None,
            "inplay": {"drawInflowEur": 0.0, "levelDrawInflowEur": 0.0,
                       "minOdd": None, "lastOdd": None, "lastMin": None,
                       "everLevel": False, "firstLevelOdd": None},
            "htScore": None, "last": None, "prevDrawVol": None}


# -- capture ---------------------------------------------------------------------
def capture(prices, state, now=None):
    """Draw-Dynamik je Match-Odds-Spiel mitschreiben (Pre-Match-Schluss + In-Play-Zufluesse). REIN."""
    now = now or _now()
    state = dict(state or {})
    pending = dict(state.get("pending") or {})
    for m in (prices.get("matches") or []):
        mid = str(m.get("matchId"))
        if mid in ("None", ""):
            continue
        dm = draw_metrics(m)
        if not dm:
            continue
        li = m.get("liveInfo") or {}
        tt = li.get("time")
        fin = li.get("finished")
        e = pending.get(mid) or _blank(m)
        prev = e.get("prevDrawVol")
        inc = max(0.0, dm["drawVol"] - prev) if isinstance(prev, (int, float)) else 0.0

        if fin:
            pass                                   # nicht mehr updaten -- settle() rechnet ab
        elif tt is None:
            # Pre-Match: Schlussstand ueberschreiben + frischen Draw-Zufluss aufsummieren
            pre = e.get("pre") or {}
            e["pre"] = {"drawVol": dm["drawVol"], "moTotal": dm["moTotal"],
                        "drawShare": dm["drawShare"], "drawOdd": dm["drawOdd"],
                        "drawLeader": dm["drawLeader"],
                        "inflowEur": round((pre.get("inflowEur") or 0.0) + inc, 2)}
        else:
            # In-Play: Quotenbewegung + wieviel Geld waehrend Gleichstand aufs X kommt
            ip = e["inplay"]
            od = dm["drawOdd"]
            ip["lastOdd"] = od
            ip["lastMin"] = tt
            if od is not None:
                ip["minOdd"] = od if ip["minOdd"] is None else min(ip["minOdd"], od)
            ip["drawInflowEur"] = round((ip["drawInflowEur"] or 0.0) + inc, 2)
            gv1, gv2 = li.get("goal_v1"), li.get("goal_v2")
            level = gv1 is not None and gv1 == gv2
            if level:
                if not ip["everLevel"]:
                    ip["everLevel"] = True
                    ip["firstLevelOdd"] = od
                ip["levelDrawInflowEur"] = round((ip["levelDrawInflowEur"] or 0.0) + inc, 2)
            # letzten Live-Stand + HT fuer den Verschwinde-Settle
            if gv1 is not None:
                e["last"] = {"score": [gv1, gv2], "min": tt, "seenAt": now.isoformat()}
                if (li.get("is_ht") or (isinstance(tt, (int, float)) and 43 <= tt <= 60)) \
                        and e.get("htScore") is None:
                    e["htScore"] = [gv1, gv2]

        e["prevDrawVol"] = dm["drawVol"]
        pending[mid] = e
    state["pending"] = pending
    return state


# -- settle ----------------------------------------------------------------------
def _row(mid, e, ft, ht, via, now):
    pre = e.get("pre") or {}
    ip = e.get("inplay") or {}
    draw_came = bool(ft and ft[0] is not None and ft[0] == ft[1])
    return {"matchId": mid, "league": e.get("league"), "home": e.get("home"),
            "away": e.get("away"), "country": e.get("country"),
            "ft": ft, "ht": ht, "drawCame": draw_came, "via": via, "settledAt": now.isoformat(),
            # Pre-Match-Signal
            "drawShare": pre.get("drawShare"), "drawOdd": pre.get("drawOdd"),
            "drawVol": pre.get("drawVol"), "moTotal": pre.get("moTotal"),
            "drawLeader": bool(pre.get("drawLeader")), "preInflowEur": pre.get("inflowEur") or 0.0,
            # In-Play-Signal (der Trade-Out-Verdacht)
            "inplayDrawInflowEur": ip.get("drawInflowEur") or 0.0,
            "levelDrawInflowEur": ip.get("levelDrawInflowEur") or 0.0,
            "everLevel": bool(ip.get("everLevel")),
            "minDrawOddInplay": ip.get("minOdd"), "lastDrawOddInplay": ip.get("lastOdd"),
            "firstLevelOdd": ip.get("firstLevelOdd")}


def settle(prices, state, results, now=None):
    """Fertige Spiele abrechnen (finished ODER Verschwinde-Settle) -> results. Entfernt pending. REIN."""
    now = now or _now()
    state = dict(state or {})
    pending = dict(state.get("pending") or {})
    results = list(results or [])

    # 1) Feed zeigt "finished" -> exakter Endstand
    for m in (prices.get("matches") or []):
        li = m.get("liveInfo") or {}
        if not li.get("finished"):
            continue
        mid = str(m.get("matchId"))
        e = pending.get(mid)
        if not e:
            continue
        ft = [li.get("goal_v1"), li.get("goal_v2")] if li.get("goal_v1") is not None else None
        results.append(_row(mid, e, ft, e.get("htScore"), "finished", now))
        pending.pop(mid, None)

    # 2) Verschwinde-Settle: Spiel aus dem Feed, zuletzt spaet (>=85') live gesehen, seit >=25 weg
    feed_ids = {str(m.get("matchId")) for m in (prices.get("matches") or [])}
    for mid in list(pending.keys()):
        if mid in feed_ids:
            continue
        e = pending[mid]
        last = e.get("last") or {}
        score, mn = last.get("score"), last.get("min")
        if score is None or not isinstance(mn, (int, float)) or mn < VANISH_MIN_MINUTE:
            continue
        try:
            seen = datetime.fromisoformat(str(last.get("seenAt")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            seen = None
        if seen is None or seen > now - timedelta(minutes=VANISH_GRACE_MIN):
            continue
        results.append(_row(mid, e, list(score), e.get("htScore"), "vanish", now))
        pending.pop(mid, None)

    # zu alte pending (nie spaet gesehen / nie finished) verwerfen
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


# -- aggregate -------------------------------------------------------------------
def _is_notable(r):
    return bool(r.get("drawLeader")) or (r.get("drawShare") or 0) >= NOTABLE_SHARE \
        or (r.get("preInflowEur") or 0) >= NOTABLE_INFLOW_EUR


def _agg(rows):
    n = len(rows)
    came = sum(1 for r in rows if r.get("drawCame"))
    # ROI: X backen zur Pre-Match-Draw-Quote
    prof, priced = 0.0, 0
    imp = 0.0
    for r in rows:
        od = r.get("drawOdd")
        if isinstance(od, (int, float)) and od > 1:
            priced += 1
            imp += 1.0 / od
            prof += (od - 1.0) if r.get("drawCame") else -1.0
    return {"n": n, "drawCame": came,
            "drawRate": round(came / n, 4) if n else None,
            "impliedRate": round(imp / priced, 4) if priced else None,
            "backRoi": round(prof / priced, 4) if priced else None}


def aggregate(results, now=None):
    """Ledger -> Antwort auf Lucas' Frage: kommt X bei viel Draw-Geld oefter oder seltener? REIN."""
    now = now or _now()
    rows = list(results or [])
    notable = [r for r in rows if _is_notable(r)]

    # Draw-Anteil-Baender (Pre-Match)
    def band(r):
        s = r.get("drawShare") or 0
        return "share_lt_30" if s < 0.30 else "share_30_40" if s < 0.40 else "share_ge_40"
    by_share = {}
    for key in ("share_lt_30", "share_30_40", "share_ge_40"):
        by_share[key] = _agg([r for r in notable if band(r) == key])

    # In-Play-Trade-Out-Test: viel Geld WAEHREND Gleichstand aufs X -> kommt X dann SELTENER?
    level_money = [r for r in notable if (r.get("levelDrawInflowEur") or 0) > 0]
    hi_level = [r for r in level_money if (r.get("levelDrawInflowEur") or 0) >= NOTABLE_INFLOW_EUR]
    lo_level = [r for r in level_money if (r.get("levelDrawInflowEur") or 0) < NOTABLE_INFLOW_EUR]

    # Quoten-Raustraden: Draw-Quote in-play erst gefallen (rein), Signal fuer Positionsaufbau
    def shortened(r):
        fo, mo = r.get("firstLevelOdd"), r.get("minDrawOddInplay")
        return isinstance(fo, (int, float)) and isinstance(mo, (int, float)) and fo > 0 and mo < fo * 0.95
    tightened = [r for r in notable if r.get("everLevel") and shortened(r)]

    return {"generatedAt": now.isoformat(),
            "notableShare": NOTABLE_SHARE, "notableInflowEur": NOTABLE_INFLOW_EUR,
            "all": _agg(rows),                       # Basisrate ueber ALLE getrackten 1x2-Spiele
            "notable": _agg(notable),                # "hohe Einsaetze aufs X"
            "drawLeader": _agg([r for r in notable if r.get("drawLeader")]),
            "byShareBand": by_share,
            "inplayLevelMoneyHigh": _agg(hi_level),  # viel In-Play-Draw-Geld bei Gleichstand
            "inplayLevelMoneyLow": _agg(lo_level),
            "inplayOddTightened": _agg(tightened)}   # Draw-Quote in-play gefallen (Aufbau, dann raus?)


# -- I/O (main) ------------------------------------------------------------------
def _load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    print("=== betfair_draw_tracker.py ===")
    prices = _load(PRICES_FILE, {})
    if not prices.get("matches"):
        print("  keine betfair_prices.json -- uebersprungen (kein Wipe).")
        return 0
    state = _load(STATE_FILE, {})
    results = _load(RESULTS_FILE, [])
    if not isinstance(results, list):
        results = []
    now = _now()
    state = capture(prices, state, now=now)
    state, results = settle(prices, state, results, now=now)
    record = aggregate(results, now=now)
    _write(STATE_FILE, state)
    _write(RESULTS_FILE, results)
    _write(RECORD_FILE, record)
    nb = record["notable"]
    print("  %d pending - %d abgerechnet - notable=%d (X kam %s%%, ROI %s)"
          % (len(state.get("pending", {})), len(results), nb["n"],
             round((nb["drawRate"] or 0) * 100) if nb["drawRate"] is not None else "-",
             nb["backRoi"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
