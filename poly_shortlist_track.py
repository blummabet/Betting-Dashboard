#!/usr/bin/env python3
# poly_shortlist_track.py — 02.08.2026 (Lucas): Paper-Track-Record für die „Heute spielenswert"-
# Shortlist. Snapshottet bei jedem Global-Scan die EXAKTEN Empfehlungen (via node-Emitter, der die
# echte Frontend-Engine lädt → kein Drift), rechnet bei Markt-Auflösung ab: fixer Einsatz $10 zum
# Einstiegspreis, Abrechnung 0/1, plus CLV (Einstieg→Schluss). Zwei Sichten aus EINEM File: die
# ganze Shortlist UND die Public-Kandidaten-Teilmenge (public-Flag je Play). Setzt/sendet NICHTS —
# reines Mitschreiben, damit Lucas sieht, ob sich das echte Nachspielen (Auto-Bet) lohnt.
#
# Datenfluss (alles read-only ggü. Poly, nur Track-File wird geschrieben):
#   node scripts/emit_shortlist.mjs  → Plays (key, side, verdict, conv, price, public, …)
#   poly_money_broad_close.json      → lastPrice-Update offener Plays (Schluss-Referenz für CLV)
#   poly_resolutions.json            → {key:{winner,ts}} (von poly_money_broad geschrieben)
#   poly_shortlist_track.json        → vorheriger Stand (open/settled/agg)
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
CLOSE_FILE = "poly_money_broad_close.json"
RES_FILE = "poly_resolutions.json"
TRACK_FILE = "poly_shortlist_track.json"
EMITTER = "scripts/emit_shortlist.mjs"

STAKE = float(os.environ.get("SHORTLIST_STAKE") or 10.0)   # fixer Einsatz je Play (USD-Notional)
SETTLED_KEEP = 500                                          # abgerechnete Plays behalten (rollierend)


def _now():
    return datetime.now(timezone.utc)


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_emit():
    """Emitter-Output holen. Test/Offline: $SHORTLIST_EMIT_JSON = Pfad zu fertigem JSON.
    Sonst: node-Emitter laufen lassen (lädt die echte poly-wallets.js-Engine). None bei Fehler."""
    override = os.environ.get("SHORTLIST_EMIT_JSON")
    if override:
        try:
            return json.loads(Path(override).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  Emit-Override nicht lesbar: {e}")
            return None
    try:
        out = subprocess.run(["node", str(BASE / EMITTER)], cwd=str(BASE),
                             capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            print(f"  Emitter-Fehler (rc={out.returncode}): {out.stderr.strip()[:400]}")
            return None
        return json.loads(out.stdout)
    except Exception as e:
        print(f"  Emitter nicht ausführbar (nicht fatal): {e}")
        return None


def _ok_price(p):
    return isinstance(p, (int, float)) and 0.0 < float(p) < 1.0


def _agg_one(rows):
    n = len(rows)
    wins = sum(1 for r in rows if r.get("result") == "win")
    stake = sum(float(r.get("stake") or 0) for r in rows)
    pnl = sum(float(r.get("pnl") or 0) for r in rows)
    clv = sum(float(r.get("clvPP") or 0) for r in rows)
    return {"n": n, "wins": wins,
            "hit": round(wins / n, 4) if n else 0.0,
            "pnl": round(pnl, 2), "stake": round(stake, 2),
            "roi": round(pnl / stake, 4) if stake else 0.0,
            "clvAvg": round(clv / n, 2) if n else 0.0}


def aggregate(settled):
    allr = settled
    pub = [r for r in settled if r.get("public")]
    by_conv = {}
    for c in range(0, 11):
        rows = [r for r in settled if int(r.get("conv") or 0) == c]
        if rows:
            by_conv[str(c)] = _agg_one(rows)
    by_verdict = {}
    for v in ("BET", "FADE"):
        rows = [r for r in settled if r.get("verdict") == v]
        if rows:
            by_verdict[v] = _agg_one(rows)
    return {"all": _agg_one(allr), "public": _agg_one(pub),
            "byConv": by_conv, "byVerdict": by_verdict}


def update_track(prev, emit, close, resolutions, now=None, stake=STAKE):
    """REIN/testbar. Öffnet neue Plays, zieht lastPrice mit, rechnet aufgelöste ab. Ein Play =
    (marketKey, side); der Einstieg (firstTs/entryPrice) ist der ERSTE Zeitpunkt, an dem der Play
    in der Shortlist auftauchte — genau das, was man live gesetzt hätte."""
    now = now or _now()
    open_ = {k: dict(v) for k, v in (prev.get("open") or {}).items() if isinstance(v, dict)}
    settled = [dict(s) for s in (prev.get("settled") or []) if isinstance(s, dict)]
    settled_keys = {(s.get("key"), s.get("side")) for s in settled}

    # 1) Neue Plays öffnen (fixer Einsatz, Entry = Snapshot-Preis der empfohlenen Seite)
    for pl in (emit.get("plays") or []):
        key, side = pl.get("key"), pl.get("side")
        if not key or not side:
            continue
        ok = f"{key}|{side}"
        if ok in open_ or (key, side) in settled_keys:
            continue
        price = pl.get("price")
        if not _ok_price(price):
            price = ((close.get(key) or {}).get("prices") or {}).get(side)
        if not _ok_price(price):
            continue                                  # kein sauberer Einstiegspreis → nicht öffnen
        open_[ok] = {
            "key": key, "side": side, "verdict": pl.get("verdict"),
            "conv": pl.get("conv"), "league": pl.get("league"),
            "entryPrice": round(float(price), 4), "firstTs": now.isoformat(),
            "lastPrice": round(float(price), 4), "lastTs": now.isoformat(),
            "htkAtEntry": pl.get("htk"), "public": bool(pl.get("public")),
            "reasons": (pl.get("reasons") or [])[:3], "stake": stake,
        }

    # 2) lastPrice aller offenen Plays aus dem Close-File nachziehen (beste Schluss-Referenz für CLV)
    for e in open_.values():
        cp = ((close.get(e["key"]) or {}).get("prices") or {}).get(e["side"])
        if _ok_price(cp):
            e["lastPrice"] = round(float(cp), 4)
            e["lastTs"] = now.isoformat()

    # 3) Aufgelöste Plays abrechnen
    for ok in list(open_.keys()):
        e = open_[ok]
        r = resolutions.get(e["key"]) if isinstance(resolutions, dict) else None
        winner = (r or {}).get("winner")
        if not winner:
            continue
        entry = float(e["entryPrice"])
        st = float(e.get("stake") or stake)
        win = (e["side"] == winner)
        pnl = (st / entry - st) if win else -st       # Aktien = st/entry, Gewinner zahlt 1.00/Aktie
        close_ref = float(e.get("lastPrice") or entry)
        clv = round((close_ref - entry) * 100, 2)
        settled.append({
            "key": e["key"], "side": e["side"], "verdict": e.get("verdict"),
            "conv": e.get("conv"), "league": e.get("league"),
            "entryPrice": round(entry, 4), "closePrice": round(close_ref, 4),
            "result": "win" if win else "loss", "winner": winner,
            "pnl": round(pnl, 2), "clvPP": clv, "stake": st,
            "public": bool(e.get("public")), "firstTs": e.get("firstTs"),
            "settledTs": now.isoformat(), "resolvedTs": (r or {}).get("ts"),
        })
        del open_[ok]

    settled = settled[-SETTLED_KEEP:]
    return {"updatedAt": now.isoformat(), "stake": stake,
            "open": open_, "settled": settled, "agg": aggregate(settled)}


def main() -> int:
    emit = load_emit()
    if emit is None:
        # Emitter ist umgebungs-flaky (node_modules/jsdom im CI weggewischt). FRÜHER hing die
        # ganze Abrechnung daran (früher return) → aufgelöste Plays blieben ewig „offen", obwohl
        # poly_resolutions.json den Sieger längst kennt. Abrechnung braucht den Emitter NICHT:
        # ohne Emit einfach keine NEUEN Plays öffnen, offene aber weiter abrechnen. (02.08.2026, Lucas)
        print("ℹ️  Kein Emitter-Output — keine neuen Plays, aber offene werden weiter abgerechnet.")
        emit = {"plays": []}
    close = _load(CLOSE_FILE)
    resolutions = _load(RES_FILE)
    prev = _load(TRACK_FILE)
    track = update_track(prev, emit, close if isinstance(close, dict) else {},
                         resolutions if isinstance(resolutions, dict) else {})
    (BASE / TRACK_FILE).write_text(json.dumps(track, ensure_ascii=False, indent=1), encoding="utf-8")
    a = track["agg"]["all"]
    print(f"📈 Shortlist-Paper-Track: {len(track['open'])} offen · {a['n']} abgerechnet · "
          f"Treffer {a['hit']*100:.0f}% · ROI {a['roi']*100:+.1f}% · Ø CLV {a['clvAvg']:+.1f}pp "
          f"(Public: {track['agg']['public']['n']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
