#!/usr/bin/env python3
"""test_wallet_clv_avgprice.py — CLV-Fix (28.07.2026, Lucas: „CLV misst 0").
Der Whale-Ø-EINSTIEG (avgPrice aus Poly /positions) wird als Einstiegsanker genutzt →
CLV = Close − echter Einstieg statt strukturell ~0 (firstPrice ≈ Close near-KO)."""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import poly_money_broad as B

T0 = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


# ── _avg_from_positions ───────────────────────────────────────────────────────
def test_avg_from_positions_findet_token():
    data = [{"asset": "TOK_A", "avgPrice": 0.31}, {"asset": "TOK_B", "avgPrice": 0.72}]
    assert B._avg_from_positions(data, "TOK_A") == 0.31
    assert B._avg_from_positions(data, "TOK_B") == 0.72


def test_avg_from_positions_ignoriert_unbekannt_und_range():
    assert B._avg_from_positions([{"asset": "X", "avgPrice": 0.5}], "TOK_A") is None
    assert B._avg_from_positions([{"asset": "TOK_A", "avgPrice": 1.4}], "TOK_A") is None   # >1 raus
    assert B._avg_from_positions([{"asset": "TOK_A", "avgPrice": "n/a"}], "TOK_A") is None
    assert B._avg_from_positions(None, "TOK_A") is None


# ── _enrich_whales_avg ────────────────────────────────────────────────────────
def test_enrich_haengt_avgprice_an_und_cached_je_wallet():
    calls = []
    positions = {"0xW1": [{"asset": "TOK_A", "avgPrice": 0.30}],
                 "0xW2": [{"asset": "TOK_B", "avgPrice": 0.66}]}

    def get(url):
        u = url.split("user=")[1].split("&")[0]
        calls.append(u)
        return positions.get(u, [])

    whales = [{"wallet": "0xW1", "side": "A", "usd": 9000},
              {"wallet": "0xW1", "side": "A", "usd": 8000},   # gleiche Wallet → cache-Hit
              {"wallet": "0xW2", "side": "B", "usd": 7000}]
    cache, budget = {}, [10]
    B._enrich_whales_avg(whales, {"A": "TOK_A", "B": "TOK_B"}, cache, get, budget)
    assert whales[0]["avgPrice"] == 0.30
    assert whales[1]["avgPrice"] == 0.30
    assert whales[2]["avgPrice"] == 0.66
    assert calls == ["0xW1", "0xW2"], calls   # je Wallet genau EIN Call
    assert budget == [8]                       # 2 Calls verbraucht


def test_enrich_respektiert_budget():
    def get(url):
        return [{"asset": "TOK_A", "avgPrice": 0.4}]

    whales = [{"wallet": "0xW1", "side": "A"}, {"wallet": "0xW2", "side": "A"}]
    cache, budget = {}, [1]
    B._enrich_whales_avg(whales, {"A": "TOK_A"}, cache, get, budget)
    assert "avgPrice" in whales[0]       # erster geht durch
    assert "avgPrice" not in whales[1]   # Budget leer → kein Call
    assert budget == [0]


# ── update_wallet_track nutzt avgPrice als Einstiegsanker ─────────────────────
def _up_avg(price_now, avg, key="mlb-a-b", side="A", wallet="0xW", usd=8000):
    return {"key": key, "league": "MLB", "resolved": False, "hoursToKickoff": 2.0,
            "prices": {side: price_now, "B": round(1 - price_now, 4)},
            "whales": [{"wallet": wallet, "side": side, "usd": usd, "avgPrice": avg}]}


def _resolved(winner="A", key="mlb-a-b"):
    return {"key": key, "resolved": True,
            "resolvedPrices": {winner: 1.0, ("B" if winner == "A" else "A"): 0.0}}


def test_clv_gegen_echten_avg_einstieg():
    # Wal erst near-KO gesehen (price_now == close 0.55) → firstPrice gäbe CLV 0.
    # Echter Ø-Einstieg 0.30 (avgPrice) → CLV = (0.55 − 0.30)*100 = 25.
    t = B.update_wallet_track({}, [_up_avg(0.55, 0.30)], now=T0)
    assert t["open"]["0xW|mlb-a-b|A"]["entryPrice"] == 0.30
    assert t["open"]["0xW|mlb-a-b|A"]["firstPrice"] == 0.55   # firstPrice bleibt der Sicht-Preis
    frozen = {"mlb-a-b": {"prices": {"A": 0.55, "B": 0.45}}}
    t = B.update_wallet_track(t, [_resolved("A")], now=T0 + timedelta(hours=3), frozen=frozen)
    s = t["scores"]["0xW"]
    assert s["n"] == 1 and abs(s["clvSumPP"] - 25.0) < 0.01 and s["wins"] == 1, s


def test_ohne_avgprice_altverhalten():
    up = {"key": "mlb-a-b", "league": "MLB", "resolved": False, "hoursToKickoff": 2.0,
          "prices": {"A": 0.40, "B": 0.60}, "whales": [{"wallet": "0xW", "side": "A", "usd": 8000}]}
    t = B.update_wallet_track({}, [up], now=T0)
    assert "entryPrice" not in t["open"]["0xW|mlb-a-b|A"]
    frozen = {"mlb-a-b": {"prices": {"A": 0.62, "B": 0.38}}}
    t = B.update_wallet_track(t, [_resolved("A")], now=T0 + timedelta(hours=3), frozen=frozen)
    s = t["scores"]["0xW"]
    assert abs(s["clvSumPP"] - 22.0) < 0.01, s   # (0.62 − 0.40)*100 = 22


if __name__ == "__main__":
    import types
    fns = [v for k, v in dict(globals()).items()
           if k.startswith("test_") and isinstance(v, types.FunctionType)]
    for f in fns:
        f()
        print("ok", f.__name__)
    print(f"\n{len(fns)} tests passed")
