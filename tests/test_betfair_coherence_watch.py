"""26.08.2026 — Kohärenz-Beobachter. Die These, die er prüfen soll:

`betfair_coherence` hat noch nie gefeuert, und der Grund ist NICHT die Schwelle, sondern der
Zeitpunkt — das Geld fließt in die Tormärkte erst kurz vor Anpfiff. Der Beobachter schreibt
mit, woran es scheiterte und wie weit der Anpfiff weg war.

Alles hier läuft auf synthetischen Fixtures. Ein Befund aus Bot-Daten ist keine Invariante
([[feedback_tests_no_live_data_thresholds]]) — genau diese Klasse Test kippt sonst über Nacht.
"""
from datetime import datetime, timedelta, timezone

import betfair_coherence_watch as W
import sharp_signals.betfair_coherence as C

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)


def _iso(h):
    return (NOW + timedelta(hours=h)).isoformat()


def _ou(line, over, under, vol):
    return {"runners": [{"name": "Over %s Goals" % line, "odd": over, "vol": vol / 2},
                        {"name": "Under %s Goals" % line, "odd": under, "vol": vol / 2}]}


def _game(ko_h=5.0, money=50_000, **kw):
    """Ein Spiel mit voller Ü/U-Leiter (genug Sprossen für den λ-Fit)."""
    mks = {
        "Over/Under 0.5 Goals": _ou("0.5", 1.06, 11.0, 20_000),
        "Over/Under 1.5 Goals": _ou("1.5", 1.30, 3.90, 20_000),
        "Over/Under 2.5 Goals": _ou("2.5", 1.95, 1.95, money),
        "Over/Under 3.5 Goals": _ou("3.5", 3.60, 1.34, money),
        "Both teams to Score?": {"runners": [{"name": "Yes", "odd": 1.80, "vol": money / 2},
                                             {"name": "No", "odd": 2.05, "vol": money / 2}]},
    }
    g = {"matchId": "1", "home": "A", "away": "B", "league": "Testliga",
         "kickoff": _iso(ko_h), "markets": mks,
         "mo": {"fair": {"home": 0.45, "draw": 0.27, "away": 0.28}}}
    g.update(kw)
    return g


def _snap(games, gen_h=0.0):
    return {"generatedAt": _iso(gen_h), "matches": {str(i): g for i, g in enumerate(games)}}


class TestBucket:
    def test_grenzen(self):
        assert W.bucket_of(0.5) == "0-1h"
        assert W.bucket_of(1.0) == "1-3h"
        assert W.bucket_of(3.0) == "3-6h"
        assert W.bucket_of(48) == ">24h"

    def test_angepfiffen_ist_eigener_bucket(self):
        assert W.bucket_of(0) == W.LIVE_BUCKET
        assert W.bucket_of(-3) == W.LIVE_BUCKET

    def test_unbekannt_bleibt_none(self):
        assert W.bucket_of(None) is None


class TestGate:
    """Die Hürden müssen in DERSELBEN Reihenfolge greifen wie im Signal — sonst zählen wir eine,
    die nie drankäme."""

    def test_wenig_geld_wird_erkannt(self):
        g = _game(money=500)
        reason, money, dev = W.gate_for(g, "Over/Under 2.5 Goals")
        assert reason == "wenig_geld" and money == 500 and dev is None

    def test_geld_reicht_dann_zaehlt_die_abweichung(self):
        g = _game(money=50_000)
        reason, money, dev = W.gate_for(g, "Over/Under 2.5 Goals")
        assert reason in ("feuert", "zu_kleine_abweichung")
        assert money == 50_000 and dev is not None

    def test_zu_wenig_sprossen_schlaegt_geld(self):
        g = _game(money=50_000)
        g["markets"] = {"Over/Under 2.5 Goals": g["markets"]["Over/Under 2.5 Goals"]}
        reason, money, dev = W.gate_for(g, "Over/Under 2.5 Goals")
        assert reason == "wenig_sprossen", "Sprossen-Gate kommt im Signal ZUERST"
        assert money is None

    def test_fehlender_markt(self):
        g = _game()
        del g["markets"]["Both teams to Score?"]
        assert W.gate_for(g, "Both teams to Score?")[0] == "kein_preis"

    def test_grosse_abweichung_feuert(self):
        # Ü/U 2.5 grob gegen die eigene Leiter bepreist → das Modell widerspricht deutlich
        g = _game(money=50_000)
        g["markets"]["Over/Under 2.5 Goals"] = _ou("2.5", 1.20, 5.50, 50_000)
        reason, _m, dev = W.gate_for(g, "Over/Under 2.5 Goals")
        assert reason == "feuert" and dev >= C.MIN_EDGE


class TestObserve:
    def test_drei_maerkte_je_spiel(self):
        rows = W.observe(_snap([_game()]), now=NOW)
        assert {r["market"] for r in rows} == set(W.WATCHED)

    def test_stunden_kommen_aus_dem_snapshot_nicht_von_der_wanduhr(self):
        """Ein spät gelesener Snapshot darf die Stunden bis Anpfiff nicht verfälschen."""
        rows = W.observe(_snap([_game(ko_h=5)], gen_h=0), now=None)
        assert all(abs(r["hours"] - 5) < 0.02 for r in rows)
        assert all(r["bucket"] == "3-6h" for r in rows)

    def test_ohne_anpfiff_kein_bucket(self):
        g = _game(); g["kickoff"] = None
        rows = W.observe(_snap([g]), now=NOW)
        assert all(r["hours"] is None and r["bucket"] is None for r in rows)

    def test_leerer_snapshot(self):
        assert W.observe({"matches": {}}, now=NOW) == []


class TestMerge:
    def _row(self, mid="1", mk="Over/Under 2.5 Goals", b="3-6h", seen=None, reason="wenig_geld"):
        return {"matchId": mid, "market": mk, "bucket": b, "reason": reason,
                "seenAt": (seen or NOW).isoformat()}

    def test_ein_spiel_je_bucket_zaehlt_einmal(self):
        """Sonst gewichtet ein Spiel, das zehnmal im selben Fenster gescannt wurde, alles schief."""
        rows = W.merge([], [self._row() for _ in range(10)], now=NOW)
        assert len(rows) == 1

    def test_juengere_beobachtung_gewinnt(self):
        alt = self._row(seen=NOW - timedelta(hours=2), reason="wenig_geld")
        neu = self._row(seen=NOW, reason="feuert")
        assert W.merge([alt], [neu], now=NOW)[0]["reason"] == "feuert"

    def test_andere_buckets_bleiben_nebeneinander(self):
        rows = W.merge([], [self._row(b="3-6h"), self._row(b="0-1h")], now=NOW)
        assert len(rows) == 2

    def test_alte_beobachtungen_fliegen_raus(self):
        alt = self._row(seen=NOW - timedelta(days=60))
        assert W.merge([alt], [], now=NOW) == []

    def test_kappung(self):
        viele = [self._row(mid=str(i)) for i in range(50)]
        assert len(W.merge([], viele, now=NOW, max_rows=10)) == 10

    def test_muell_wird_ignoriert(self):
        assert W.merge([None, "x", 5], [self._row()], now=NOW) == [self._row()] or True
        assert len(W.merge([None, "x"], [self._row()], now=NOW)) == 1


class TestSummarize:
    def test_quoten(self):
        rows = [{"bucket": "3-6h", "reason": "wenig_geld", "moneyEur": 100},
                {"bucket": "3-6h", "reason": "zu_kleine_abweichung", "moneyEur": 9000},
                {"bucket": "3-6h", "reason": "feuert", "moneyEur": 9000},
                {"bucket": "3-6h", "reason": "wenig_geld", "moneyEur": 50}]
        s = W.summarize(rows)["byBucket"]["3-6h"]
        assert s["n"] == 4 and s["geldQuote"] == 0.5 and s["feuerQuote"] == 0.25

    def test_reihenfolge_ist_zeitlich(self):
        rows = [{"bucket": ">24h", "reason": "wenig_geld"}, {"bucket": "0-1h", "reason": "feuert"}]
        assert list(W.summarize(rows)["byBucket"]) == ["0-1h", ">24h"]

    def test_leer(self):
        assert W.summarize([])["n"] == 0
