"""19.07.2026 — Maker statt Taker: Einstiegs-Preis-Entscheidung auf Polymarket.

Der teuerste Fehler wäre NICHT ein schlechter Maker-Preis, sondern ein Maker-Order, der nicht
füllt und uns einen Steam-Move verpassen lässt. Deshalb prüfen diese Tests vor allem, dass in
JEDER unsicheren Lage auf Taker (Fill-Sicherheit) zurückgefallen wird — und dass der Default
(maker_enabled=false) das bestehende Live-Verhalten Bit für Bit erhält.
"""
import pytest

import poly_entry as P


def _on(**over):
    d = dict(maker_enabled=True, maker_min_hours=3.0, maker_min_spread_pp=3.0)
    d.update(over)
    return P.EntryConfig(**d)


class TestDefaultIstTaker:
    def test_maker_aus_bleibt_taker(self):
        """Solange Lucas maker_enabled nicht setzt, ändert sich NICHTS am Live-Verhalten."""
        r = P.decide_entry(0.50, 0.48, 0.54, 6.0, P.EntryConfig())
        assert r["mode"] == "taker"
        assert "Default" in r["reason"]

    def test_taker_preis_crosst_das_ask(self):
        r = P.decide_entry(0.50, 0.48, 0.54, 6.0, P.EntryConfig())
        assert r["price"] >= 0.54, "Taker muss übers Ask crossen (Fill-Priorität)"


class TestMakerNurWennEsSichLohnt:
    def test_viel_zeit_breiter_spread_ist_maker(self):
        r = P.decide_entry(0.50, 0.48, 0.54, 6.0, _on())   # 6pp Spread, 6h Zeit
        assert r["mode"] == "maker"
        assert r["price"] == 0.49, "Maker legt sich einen Tick über das Gebot"
        assert r["price"] < 0.54, "Maker darf das Ask nie erreichen (sonst crosst er)"

    def test_nah_am_anpfiff_ist_taker(self):
        """Wenig Zeit → Fill-Sicherheit schlägt Spread-Ersparnis."""
        r = P.decide_entry(0.50, 0.48, 0.54, 1.0, _on())
        assert r["mode"] == "taker" and "nah am Anpfiff" in r["reason"]

    def test_enger_spread_ist_taker(self):
        """1pp Spread → nichts zu sparen, also gleich sicher crossen."""
        r = P.decide_entry(0.50, 0.495, 0.505, 6.0, _on())
        assert r["mode"] == "taker"

    def test_ohne_orderbuch_kein_maker(self):
        """Keine Tiefe → kein belastbarer Maker-Preis → Taker."""
        assert P.decide_entry(0.50, None, None, 6.0, _on())["mode"] == "taker"

    def test_hours_none_ist_taker(self):
        assert P.decide_entry(0.50, 0.48, 0.54, None, _on())["mode"] == "taker"


class TestSicherungen:
    def test_maker_crosst_nie(self):
        """Enges Buch, aber gerade breit genug: der Maker-Preis (bid+1 Tick) darf nie ans Ask
        stoßen — sonst wären wir Taker und würden den Spread doch zahlen."""
        r = P.decide_entry(0.50, 0.50, 0.53, 6.0, _on(maker_min_spread_pp=2.0))
        if r["mode"] == "maker":
            assert r["price"] < 0.53
        # bid 0.50 + Tick 0.01 = 0.51 < 0.53 → maker ok

    def test_bid_direkt_unterm_ask_faellt_auf_taker(self):
        """bid 0.53 / ask 0.54 → bid+Tick = 0.54 = Ask → würde crossen → Taker."""
        r = P.decide_entry(0.50, 0.53, 0.54, 6.0, _on(maker_min_spread_pp=0.5))
        assert r["mode"] == "taker" and "crossen" in r["reason"]

    def test_kein_fairer_preis(self):
        r = P.decide_entry(None, 0.48, 0.54, 6.0, _on())
        assert r["mode"] == "taker" and r["price"] is None, "ohne Fair → Aufrufer-Fallback"

    def test_max_price_deckelt(self):
        """Nie teurer als max_price einsteigen, egal wie das Buch aussieht."""
        r = P.decide_entry(0.98, 0.99, 0.995, 0.5, P.EntryConfig(max_price=0.97))
        assert r["price"] <= 0.97


class TestVerdrahtung:
    def test_place_market_order_ruft_maker_intent(self):
        """Der Vorentscheid muss in place_market_order eingehängt sein, sonst ist die ganze
        Datei toter Code — und niemandem fiele es auf, weil der Default eh Taker ist."""
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent / "polymarket_bet.py").read_text("utf-8")
        assert "_maker_intent(" in src, "Maker-Vorentscheid nicht in place_market_order verdrahtet"
        assert "maker_limit" in src, "Maker-Order-Pfad fehlt"
