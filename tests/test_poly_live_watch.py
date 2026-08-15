"""test_poly_live_watch.py — Live-Einstiegs-Alerts (11.08.2026, Lucas Stufe 2.1). Reine Auswahl-Logik,
kein Netz: scharf ODER gross, vor Anpfiff nicht drin, dedup + TTL. Sharp-Def wie im Frontend."""
import poly_live_watch as W
from datetime import datetime, timezone, timedelta

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
SCORES = {
    "0xsharp": {"n": 20, "clvSumPP": 40, "wins": 13, "pnl": 5000},   # avgClv 2.0 / 65% / pnl+ -> scharf
    "0xweak":  {"n": 15, "clvSumPP": -10, "wins": 6, "pnl": -2000},  # negativ -> nicht scharf
    "0xthin":  {"n": 2, "clvSumPP": 10, "wins": 2, "pnl": 100},      # zu wenig Historie -> nicht scharf
    "0xsharpdec": {"n": 30, "clvSumPP": 60, "wins": 20, "pnl": 8000},  # scharf, aber Ausgang @100
}


def _live():
    return {"lol-a-b": {"league": "esports", "prices": {"A": 0.6, "B": 0.4, "DEC": 1.0}, "whales": [
        {"wallet": "0xsharp", "side": "A", "usd": 8000},    # scharf + ueber SHARP_MIN_USD (5000) -> Alarm
        {"wallet": "0xweak", "side": "B", "usd": 3000},     # schwach, klein -> kein Alarm
        {"wallet": "0xbig", "side": "A", "usd": 30000},     # kein Score, gross (>25K), kompetitiv -> Alarm
        {"wallet": "0xpre", "side": "B", "usd": 20000},     # pre-game drin -> kein Alarm
        {"wallet": "0xdec", "side": "DEC", "usd": 40000},   # gross ABER @100 (entschieden) -> kein Alarm
        {"wallet": "0xsharpdec", "side": "DEC", "usd": 5000},  # scharf ABER @100 -> auch kein Alarm
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

    def test_entschiedener_ausgang_raus(self):
        # @100 = Spiel praktisch durch -> Settlement, KEIN Signal (auch fuer scharfe Wallets)
        al = W.find_alerts(_live(), CLOSE, SCORES, set(), NOW)
        w = {a["wallet"] for a in al}
        assert "0xdec" not in w and "0xsharpdec" not in w

    def test_big_schwelle_25k(self):
        # 15K wuerde bei alter 10K-Schwelle feuern, bei 25K nicht mehr; 30K feuert
        al = W.find_alerts({"m": {"league": "tennis", "prices": {"X": 0.5, "Y": 0.5},
            "whales": [{"wallet": "0xw15", "side": "X", "usd": 15000},
                       {"wallet": "0xw30", "side": "Y", "usd": 30000}]}}, {}, {}, set(), NOW)
        w = {a["wallet"] for a in al}
        assert "0xw15" not in w and "0xw30" in w

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


class TestContestedLive:
    """12.08.2026 (Lucas): umkaempfte Spiele (Gross-Geld auf beiden offenen Seiten) -> gar kein Live-Signal."""

    def _m(self, faze_usd, bb_usd):
        return {"league": "esports", "prices": {"FaZe": 0.70, "BetBoom": 0.30},   # 14.08.2026: unter 77¢-Deckel
                "whales": [{"wallet": "0xa", "side": "FaZe", "usd": faze_usd},
                           {"wallet": "0xb", "side": "BetBoom", "usd": bb_usd}]}

    def test_beide_seiten_gross_umkaempft(self):
        m = self._m(170000, 32000)
        assert W._contested(m) is True
        assert W.find_alerts({"cs2-bb-faze": m}, {}, {}, set(), NOW) == []   # gar nichts gesendet

    def test_einseitig_nicht_umkaempft(self):
        m = self._m(170000, 8000)   # Gegenseite < 25K
        assert W._contested(m) is False
        al = W.find_alerts({"cs2-bb-faze": m}, {}, {}, set(), NOW)
        assert "0xa" in {a["wallet"] for a in al}   # die grosse einseitige kommt durch

    def test_entschiedene_seite_zaehlt_nicht(self):
        m = {"league": "esports", "prices": {"A": 0.6, "DEC": 1.0},
             "whales": [{"wallet": "0xa", "side": "A", "usd": 30000},
                        {"wallet": "0xd", "side": "DEC", "usd": 40000}]}
        assert W._contested(m) is False   # DEC @100 ist Abwicklung, keine Contest-Seite

    def test_normale_fixture_nicht_umkaempft(self):
        assert W._contested(_live()["lol-a-b"]) is False   # nur A hat >=25K bei gueltigem Preis


class TestPriceCeiling77:
    """14.08.2026 (Lucas): Live-Einstiege ueber 77¢ (Quote < 1.30) = eingepreiste Fuehrung/kurzer
    Favorit -> reaktiv, raus. Gilt auch fuer eSport (Al-Ettifaq @84¢-Fall)."""
    def _m(self, price):
        return {"league": "esports", "prices": {"A": price, "B": round(1 - price, 2)},
                "whales": [{"wallet": "0xbig", "side": "A", "usd": 60000}]}

    def test_ueber_77_gefiltert(self):
        assert W.find_alerts({"k": self._m(0.84)}, {}, {}, set(), NOW) == []   # Quote ~1.19

    def test_unter_77_kommt_durch(self):
        al = W.find_alerts({"k": self._m(0.70)}, {}, {}, set(), NOW)           # Quote ~1.43
        assert "0xbig" in {a["wallet"] for a in al}



class TestMarketCapGuard:
    """15.08.2026 (Lucas): Position > gesamtes Markt-Volumen (totalUsd) = Daten-Artefakt -> raus."""
    def _m(self, usd, total):
        return {"league": "esports", "prices": {"A": 0.67, "B": 0.33}, "totalUsd": total,
                "whales": [{"wallet": "0xbig", "side": "A", "usd": usd}]}

    def test_position_groesser_als_markt_raus(self):
        # $99K-Position in $35.8K-Markt (Team-Vision-Fall) -> Artefakt, kein Push
        assert W.find_alerts({"k": self._m(99000, 35800)}, {}, {}, set(), NOW) == []

    def test_plausible_position_kommt_durch(self):
        al = W.find_alerts({"k": self._m(30000, 80000)}, {}, {}, set(), NOW)
        assert "0xbig" in {a["wallet"] for a in al}

    def test_ohne_totalusd_kein_guard(self):
        # kein totalUsd -> Guard greift nicht (kein Vergleich moeglich), normale Gates entscheiden
        m = {"league": "esports", "prices": {"A": 0.67}, "whales": [{"wallet": "0xbig", "side": "A", "usd": 30000}]}
        al = W.find_alerts({"k": m}, {}, {}, set(), NOW)
        assert "0xbig" in {a["wallet"] for a in al}
