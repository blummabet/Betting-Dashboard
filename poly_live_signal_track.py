#!/usr/bin/env python3
"""poly_live_signal_track.py — Stufe 1 (12.08.2026, Lucas): MISST Live-Whale-Signale, GATET NICHT.

Loggt jeden neuen Live-Whale-Einstieg mit Einstiegspreis + Kriterien-Flags und zieht die VORWAERTS-
Preisbewegung (Forward-CLV) ueber die Live-Preis-History nach. Nach ein paar Tagen zeigt der Track-
Record je Kriterien-Bucket, was traegt (positives Ø Forward-CLV) — DANN erst gaten wir. Laeuft im
Live-Scan mit (poly-live-scan), kostet nichts (Preis-Zeitreihe liegt schon vor). Reiner Kern testbar
(now injizierbar). Schreibt poly_live_signal_track.json = {record, ledger}."""
from __future__ import annotations
import json, os
import datetime as dt
from pathlib import Path

# Sharpness-Definition konsistent aus dem Alert-Modul (gleiche Wallet-Schaerfe wie die Live-Alerts).
try:
    from poly_live_watch import is_sharp as _is_sharp, _score as _wscore
except Exception:
    _is_sharp = None
    _wscore = None

BASE = Path(__file__).resolve().parent
LIVE_FILE   = BASE / "poly_money_broad_live.json"
HIST_FILE   = BASE / "poly_money_broad_live_history.json"
WTRACK_FILE = BASE / "poly_wallet_track.json"
TRACK_FILE  = BASE / "poly_live_signal_track.json"

# ── Kriterien-Schwellen (STARTWERTE — wir validieren sie gegen Forward-CLV, dann festklopfen) ──
MIN_LOG_USD   = float(os.environ.get("POLY_LSIG_MIN_LOG_USD") or 2000)   # ab so viel ueberhaupt loggen (breit, fuer Daten ueber alle Groessenbaender)
VALUE_LO, VALUE_HI = 0.25, 0.75      # Value-Zone: informativer Preisbereich (umkaempfte Mitte)
MATURE_USD    = 50000                # Markt-Reife: effizienter Preis
CHASE_PP      = 8.0                  # Preis der Seite ueber CHASE_BACK-Fenster so viel gestiegen -> Chasing
CHASE_BACK    = 2                    # ueber so viele History-Punkte zurueck messen (~30 Min)
DECIDED_HI, DECIDED_LO = 0.97, 0.03  # Markt entschieden -> settlen
SETTLE_TAIL_H = 3.0                  # so viele h nach (eingefrorenem) Anpfiff -> settlen
CLV_HORIZON_MIN = 30                 # Kopf-Kennzahl: Forward-CLV nach ~30 Min
KEEP = 3000


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _iso(t):
    return t.isoformat()


def _parse(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _price(m, side):
    p = (m.get("prices") or {}).get(side) if isinstance(m, dict) else None
    return float(p) if isinstance(p, (int, float)) else None


def _sharp(scores, wallet):
    if not (_is_sharp and _wscore):
        return False
    try:
        return bool(_is_sharp(_wscore(scores, wallet)))
    except Exception:
        return False


def _price_move_pp(histlist, side, back=CHASE_BACK):
    """Preis-Move der Seite ueber die letzten `back` History-Punkte, in pp. None wenn zu wenig Punkte."""
    if not isinstance(histlist, list) or len(histlist) < 2:
        return None
    cur = (histlist[-1].get("p") or {}).get(side)
    j = max(0, len(histlist) - 1 - back)
    prev = (histlist[j].get("p") or {}).get(side)
    if not (isinstance(cur, (int, float)) and isinstance(prev, (int, float))):
        return None
    return (cur - prev) * 100.0


def flags(entry_price, usd, sharp, total_usd, move_pp):
    """Kriterien-Flags eines Einstiegs (Boolean je Achse) — die Basis fuers spaetere Bucket-CLV."""
    vz = (entry_price is not None and VALUE_LO <= entry_price <= VALUE_HI)
    mature = (float(total_usd or 0) >= MATURE_USD)
    chasing = (move_pp is not None and move_pp >= CHASE_PP)   # Seite gerade stark hoch -> Geld laeuft nach
    size_band = "25k+" if usd >= 25000 else "10-25k" if usd >= 10000 else "5-10k" if usd >= 5000 else "2-5k"
    return {"valueZone": bool(vz), "mature": bool(mature), "notChasing": (not chasing),
            "sharp": bool(sharp), "sizeBand": size_band}


def find_events(live, hist, scores, now=None):
    """Neue Live-Whale-Einstiege als Signal-Kandidaten (MISST, gatet nicht). REIN/testbar."""
    now = now or _now()
    out = []
    for key, m in (live or {}).items():
        if not isinstance(m, dict) or not m.get("prices"):
            continue
        total = float(m.get("totalUsd") or 0)
        histlist = (hist or {}).get(key)
        for w in (m.get("whales") or []):
            wal, side = w.get("wallet"), w.get("side")
            usd = float(w.get("usd") or 0)
            if not wal or not side or usd < MIN_LOG_USD:
                continue
            ep = _price(m, side)
            if ep is None:
                continue
            sharp = _sharp(scores, wal)
            mv = _price_move_pp(histlist, side)
            out.append({"sig": "%s|%s" % (key, str(wal).lower()),
                        "key": key, "side": side, "wallet": wal, "usd": round(usd),
                        "league": m.get("league"), "entryPrice": round(ep, 4),
                        "totalUsd": round(total), "movePP": (round(mv, 1) if mv is not None else None),
                        "flags": flags(ep, usd, sharp, total, mv), "firstTs": _iso(now)})
    return out


def update_track(prev, live, hist, scores, now=None):
    """Offene Signale forttracken (Forward-CLV), neue aufnehmen, fertige settlen. REIN/testbar."""
    now = now or _now()
    led = {}
    for e in (prev or []):
        if isinstance(e, dict) and e.get("sig"):
            led[e["sig"]] = e

    # 1) neue Signale aufnehmen (nur wenn noch nicht bekannt -> Einstiegspreis einmalig fixieren)
    for ev in find_events(live, hist, scores, now):
        if ev["sig"] not in led:
            ev.update({"status": "open", "latestPrice": ev["entryPrice"], "clvPP": 0.0,
                       "clv30": None, "updatedAt": _iso(now)})
            led[ev["sig"]] = ev

    # 2) offene forttracken / settlen
    for e in led.values():
        if e.get("status") != "open":
            continue
        m = (live or {}).get(e.get("key"))
        cur = _price(m, e.get("side"))
        ft = _parse(e.get("firstTs"))
        elapsed = ((now - ft).total_seconds() / 60.0) if ft else None
        if cur is not None:
            e["latestPrice"] = round(cur, 4)
            e["clvPP"] = round((cur - float(e["entryPrice"])) * 100.0, 1)
            e["updatedAt"] = _iso(now)
            if e.get("clv30") is None and elapsed is not None and elapsed >= CLV_HORIZON_MIN:
                e["clv30"] = e["clvPP"]
        gone = not isinstance(m, dict)
        decided = (cur is not None and (cur >= DECIDED_HI or cur <= DECIDED_LO))
        htk = (m.get("hoursToKickoff") if isinstance(m, dict) else None)
        past_tail = (isinstance(htk, (int, float)) and htk < -SETTLE_TAIL_H)
        if gone or decided or past_tail:
            e["status"] = "settled"
            e["finalClvPP"] = e.get("clvPP", 0.0)
            if e.get("clv30") is None:
                e["clv30"] = e["finalClvPP"]
            e["settledAt"] = _iso(now)

    out = list(led.values())
    out.sort(key=lambda e: str(e.get("settledAt") or e.get("updatedAt") or ""))
    return out[-KEEP:]


def summarize(track, now=None):
    """Trefferquote (Forward-CLV>0) + Ø Forward-CLV je Kriterien-Bucket ueber die SETTLED Signale."""
    settled = [e for e in (track or []) if isinstance(e, dict) and e.get("status") == "settled"
               and isinstance(e.get("finalClvPP"), (int, float))]

    def agg(rows):
        n = len(rows)
        if not n:
            return {"n": 0, "posRate": None, "avgClv": None, "avgClv30": None}
        pos = sum(1 for e in rows if e["finalClvPP"] > 0)
        avg = sum(e["finalClvPP"] for e in rows) / n
        c30 = [e["clv30"] for e in rows if isinstance(e.get("clv30"), (int, float))]
        return {"n": n, "posRate": round(pos / n, 3), "avgClv": round(avg, 2),
                "avgClv30": (round(sum(c30) / len(c30), 2) if c30 else None)}

    buckets = {"alle": agg(settled)}
    for name, pred in [("sharp", lambda e: e["flags"].get("sharp")),
                       ("valueZone", lambda e: e["flags"].get("valueZone")),
                       ("mature", lambda e: e["flags"].get("mature")),
                       ("notChasing", lambda e: e["flags"].get("notChasing")),
                       ("chasing", lambda e: not e["flags"].get("notChasing"))]:
        buckets[name] = agg([e for e in settled if pred(e)])
    by_size = {}
    for e in settled:
        by_size.setdefault(e["flags"].get("sizeBand", "?"), []).append(e)
    buckets["bySize"] = {k: agg(v) for k, v in by_size.items()}
    return {"updatedAt": _iso(now or _now()), "settled": len(settled),
            "open": sum(1 for e in (track or []) if isinstance(e, dict) and e.get("status") == "open"),
            "buckets": buckets}


def main() -> int:
    now = _now()
    live = _load(LIVE_FILE, {})
    hist = _load(HIST_FILE, {})
    wt = _load(WTRACK_FILE, {})
    scores = (wt.get("scores") if isinstance(wt, dict) else {}) or {}
    prev = _load(TRACK_FILE, {})
    prev = prev.get("ledger") if isinstance(prev, dict) else prev
    track = update_track(prev if isinstance(prev, list) else [],
                         live if isinstance(live, dict) else {},
                         hist if isinstance(hist, dict) else {}, scores, now)
    rec = summarize(track, now)
    TRACK_FILE.write_text(json.dumps({"updatedAt": _iso(now), "record": rec, "ledger": track},
                                     ensure_ascii=False, indent=0), encoding="utf-8")
    print("[LIVE-SIG] %d offen, %d abgerechnet · alle: %s" % (rec["open"], rec["settled"], rec["buckets"]["alle"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
