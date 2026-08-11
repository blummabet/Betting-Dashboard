"""test_poly_live_watch.py — Live-Einstiegs-Alerts (11.08.2026, Lucas Stufe 2.1). Reine Auswahl-Logik,
kein Netz: scharf ODER gross, vor Anpfiff nicht drin, dedup + TTL. Sharp-Def wie im Frontend."""
import poly_live_watch as W
from datetime import datetime, timezone, timedelta

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
SCORES = {
    "0xsharp": {"n": 20, "clvSumPP": 40, "wins": 13, "pnl": 5000},   # avgClv 2.0 / 65% / pnl+ -> scharf
    "0xweak":  {"n": 15, "clvSumPP": -10, "wins": 6, "pnl": -2000},  # negativ -> nicht scharf
    "0xthin":  {"n": 2, "clvSumPP": 10, "wins": 2, "pnl": 100},      # zu wenig Historie -> nicht scharf
}


def _live():
    return {"lol-a-b": {"league": "esports", "prices": {"A": 0.6, "B": 0.4}, "whales": [
        {"wallet": "0xsharp", "side": "A", "usd": 800},     # scharf, klein -> Alarm
        {"wallet": "0xweak", "side": "B", "usd": 3000},     # schwach, klein -> kein Alarm
        {"wallet": "0xbig", "side": "A", "usd": 15000},     # kein Score, gross -> Alarm
        {"wallet": "0xpre", "side": "B", "usd": 20000},     # pre-game drin -> kein Alarm
    ]}}


CLOSE = {"lol-a-b": {"whales": [{"wallet": "0xpre", "side": "B", "usd": 18000}]}}


class TestIsSharp:
    def test_scharf(self):
        assert W.is_sharp(W._score(SCORES, "0xsharp")) is True

    def test_nicht_scharf_negativ(self):
        assert W.is_sharp(W._score(SCORES, "0xweak")) is False

    def test_zu_wenig_historie(self):
        assert W.is_sharp(W._score(SCORES, "0xthin")) is False

    def test_kein_score(self):
        assert W.is_sharp(None) is False


class TestFindAlerts:
    def test_scharf_und_gross_alarmieren(self):
        al = W.find_alerts(_live(), CLOSE, SCORES, set(), NOW)
        w = {a["wallet"] for a in al}
        assert "0xsharp" in w and "0xbig" in w

    def test_schwach_klein_nicht(self):
        al = W.find_alerts(_live(), CLOSE, SCORES, set(), NOW)
        assert "0xweak" not in {a["wallet"] for a in al}

    def test_pregame_nicht(self):
        al = W.find_alerts(_live(), CLOSE, SCORES, set(), NOW)
        assert "0xpre" not in {a["wallet"] for a in al}   # war vor Anpfiff im Top-4 -> kein Live-Einstieg

    def test_nach_usd_sortiert(self):
        al = W.find_alerts(_live(), CLOSE, SCORES, set(), NOW)
        assert al[0]["wallet"] == "0xbig"

    def test_sharp_flag(self):
        al = W.find_alerts(_live(), CLOSE, SCORES, set(), NOW)
        by = {a["wallet"]: a for a in al}
        assert by["0xsharp"]["sharp"] is True and by["0xbig"]["sharp"] is False

    def test_dedup(self):
        al = W.find_alerts(_live(), CLOSE, SCORES, {"lol-a-b|0xsharp"}, NOW)
        assert "0xsharp" not in {a["wallet"] for a in al}


class TestSeenPrune:
    def test_ttl(self):
        old = (NOW - timedelta(hours=W.SEEN_TTL_H + 1)).isoformat()
        fresh = (NOW - timedelta(hours=1)).isoformat()
        pr = W._prune_seen({"a|1": old, "b|2": fresh}, NOW)
        assert "a|1" not in pr and "b|2" in pr


class TestFormat:
    def test_message_hat_kernfelder(self):
        a = {"key": "lol-a-b-2026-08-11", "wallet": "0x1234567890abcdef", "side": "A", "usd": 5000,
             "league": "esports", "sharp": True, "score": {"n": 20, "avgClv": 2.0, "hit": 0.65, "pnl": 5000},
             "prices": {"A": 0.66, "B": 0.34}}
        msg = W.format_alert(a)
        assert "LIVE-Einstieg" in msg and "scharf" in msg and "polymarket.com/event/lol-a-b" in msg and "@66" in msg
