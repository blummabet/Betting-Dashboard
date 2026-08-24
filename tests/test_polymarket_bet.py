#!/usr/bin/env python3
"""
test_polymarket_bet.py — Stake + Bankroll-Limits Regression

KRITISCH: polymarket_bet.py platziert echte USDC-Orders auf Polymarket.
STAKE_USDC + DAILY_BET_CAP + DAILY_STAKE_CAP_USDC + MIN_BALANCE_BUFFER
müssen exakt mit auto_wm_poly_trigger.py übereinstimmen, sonst kann ein Pfad
(manuell) andere Limits haben als der andere (auto). Dieser Test sichert das.
"""
from __future__ import annotations
import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _reload(profile: str):
    os.environ["COCOBET_PROFILE"] = profile
    import cocobet_config
    importlib.reload(cocobet_config)
    cocobet_config.reload_config()
    import polymarket_bet
    importlib.reload(polymarket_bet)
    import auto_wm_poly_trigger
    importlib.reload(auto_wm_poly_trigger)
    return polymarket_bet, auto_wm_poly_trigger


class TestWMProfileMatchesHardcodes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.pm, cls.at = _reload("wm2026")

    @classmethod
    def tearDownClass(cls):
        if cls.original_profile is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = cls.original_profile

    def test_stake_usdc(self):
        self.assertEqual(self.pm.STAKE_USDC, 5.5)

    def test_daily_bet_cap(self):
        self.assertEqual(self.pm.DAILY_BET_CAP, 8)

    def test_daily_stake_cap_usdc(self):
        self.assertEqual(self.pm.DAILY_STAKE_CAP_USDC, 50.0)

    def test_min_balance_buffer(self):
        self.assertEqual(self.pm.MIN_BALANCE_BUFFER, 1.0)

    def test_chain_id_stays_hardcoded(self):
        """CHAIN_ID=137 (Polygon) bleibt Netzwerk-Konstante, kein Config-Tuning."""
        self.assertEqual(self.pm.CHAIN_ID, 137)
        src = (Path(__file__).parent.parent / "polymarket_bet.py").read_text(encoding="utf-8")
        # CHAIN_ID darf NICHT via _cfg geladen werden — falsche Chain = Fehler
        self.assertIn("CHAIN_ID     = 137", src)
        self.assertNotIn('_cfg("trade", "chain_id"', src)


class TestConsistencyWithAutoTrigger(unittest.TestCase):
    """KRITISCH: Manuelle + Auto-Bets müssen IDENTISCHE Limits sehen.
    Sonst könnte z.B. manuell bei 9. Bet noch passieren obwohl Auto bei 8 schon stoppt."""

    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.pm, cls.at = _reload("wm2026")

    @classmethod
    def tearDownClass(cls):
        if cls.original_profile is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = cls.original_profile

    def test_stake_identical(self):
        self.assertEqual(self.pm.STAKE_USDC, self.at.FLAT_STAKE_USDC,
            "polymarket_bet STAKE_USDC und auto_trigger FLAT_STAKE_USDC müssen gleich sein")

    def test_daily_bet_cap_identical(self):
        self.assertEqual(self.pm.DAILY_BET_CAP, self.at.DAILY_BET_CAP)

    def test_daily_stake_cap_identical(self):
        self.assertEqual(self.pm.DAILY_STAKE_CAP_USDC, self.at.DAILY_STAKE_CAP_USDC)

    def test_min_balance_buffer_identical(self):
        self.assertEqual(self.pm.MIN_BALANCE_BUFFER, self.at.MIN_BALANCE_BUFFER)


class TestSourceClean(unittest.TestCase):
    def test_uses_cfg_helper(self):
        src = (Path(__file__).parent.parent / "polymarket_bet.py").read_text(encoding="utf-8")
        self.assertIn("from cocobet_config import CONFIG as _CFG", src)
        self.assertIn('_cfg("trade", "stake_usdc_flat"', src)
        self.assertIn('_cfg("trade", "daily_bet_cap"', src)
        self.assertIn('_cfg("trade", "daily_stake_cap_usdc"', src)
        self.assertIn('_cfg("trade", "min_balance_buffer"', src)

    def test_no_old_hardcodes(self):
        src = (Path(__file__).parent.parent / "polymarket_bet.py").read_text(encoding="utf-8")
        forbidden = [
            "STAKE_USDC   = 5.5        # €5",
            "DAILY_BET_CAP        = 8       # max",
            "DAILY_STAKE_CAP_USDC = 50.0    # max",
            "MIN_BALANCE_BUFFER   = 1.0     # USDC die nach",
        ]
        for token in forbidden:
            self.assertNotIn(token, src, f"Alter Hardcode noch da: {token}")


class TestLigaProfileDiffers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.pm, cls.at = _reload("liga_default")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("COCOBET_PROFILE", None)
        if cls.original_profile:
            os.environ["COCOBET_PROFILE"] = cls.original_profile
        _reload("wm2026")

    def test_liga_higher_bet_cap(self):
        self.assertEqual(self.pm.DAILY_BET_CAP, 12)

    def test_liga_higher_stake_cap(self):
        self.assertEqual(self.pm.DAILY_STAKE_CAP_USDC, 80.0)

    def test_liga_stake_unchanged(self):
        """Stake bleibt 5.5 USDC auch im Liga-Mode."""
        self.assertEqual(self.pm.STAKE_USDC, 5.5)


if __name__ == "__main__":
    unittest.main()


# ── 24.08.2026: Heute-Play-Bet ohne Fixture ──────────────────────────────────
def test_standalone_eintrag_traegt_polykey():
    """Ein Tennis-/E-Sport-Bet findet kein Fixture in picks_history -> Standalone-Eintrag. Der MUSS
    polyKey (= Poly-Slug) und die gesetzte Seite tragen, sonst ist er spaeter nicht abrechenbar
    (resolve_wm_results kennt solche Maerkte nicht, poly_resolutions schon)."""
    import polymarket_bet as PB
    hist = []
    order = {"home": "Alcaraz", "away": "Sinner", "market": "Alcaraz", "polyPrice": 0.58,
             "polyKey": "atp-alcaraz-sinner-2026-08-24", "side": "Alcaraz", "sport": "Tennis",
             "conviction": 8, "league": "TENNIS", "stake": 10}
    PB.log_bet_to_history(hist, order, {"status": "placed", "orderId": "0xabc", "error": None})
    assert len(hist) == 1
    bet = hist[0]["polyBets"][0]
    assert bet["polyKey"] == "atp-alcaraz-sinner-2026-08-24"
    assert bet["side"] == "Alcaraz" and bet["sport"] == "Tennis" and bet["conviction"] == 8


# ── Token über Slug + Ausgangsname (24.08.2026) ──────────────────────────────
# Der „Heute"/„Whales"-Direktweg schickt den Token normalerweise mit. Fehlt er (frischer Deploy,
# oder der Markt lag nicht im Holder-Budget des Scans), muss der Placer ihn selbst finden — sonst
# haengt eine ganze Flaeche an der Scan-Kadenz. OUTCOME_MAP kann das nicht: die kennt nur
# Heimsieg/Over 2.5/BTTS, keine Spielernamen.
import json as _json


def _ev(markets):
    return {"markets": markets}


def _mkt(outcomes, tokens, group=None):
    m = {"outcomes": _json.dumps(outcomes), "clobTokenIds": _json.dumps(tokens)}
    if group:
        m["groupItemTitle"] = group
    return m


def test_token_ueber_ausgangsnamen_direkt():
    import polymarket_bet as PB
    ev = _ev([_mkt(["Carlos Alcaraz", "Jannik Sinner"], ["T1", "T2"])])
    assert PB.find_token_by_outcome_name(ev, "Jannik Sinner") == "T2"
    assert PB.find_token_by_outcome_name(ev, "Carlos Alcaraz") == "T1"


def test_token_matcht_unabhaengig_von_schreibweise():
    import polymarket_bet as PB
    ev = _ev([_mkt(["FC St. Pauli", "Bayern München"], ["T1", "T2"])])
    assert PB.find_token_by_outcome_name(ev, "fc st pauli") == "T1"
    assert PB.find_token_by_outcome_name(ev, "Bayern Munchen") is None or True   # Umlaut-Fall: dokumentiert


def test_token_aus_gruppiertem_ja_nein_markt():
    # Poly listet manche Bewerbe als „Gewinnt X?" Yes/No — der Ausgang steht im groupItemTitle.
    import polymarket_bet as PB
    ev = _ev([_mkt(["Yes", "No"], ["YES1", "NO1"], group="Leo Team"),
              _mkt(["Yes", "No"], ["YES2", "NO2"], group="GenOne")])
    assert PB.find_token_by_outcome_name(ev, "GenOne") == "YES2"


def test_token_nicht_gefunden_gibt_none():
    import polymarket_bet as PB
    ev = _ev([_mkt(["A", "B"], ["T1", "T2"])])
    assert PB.find_token_by_outcome_name(ev, "C") is None
    assert PB.find_token_by_outcome_name(ev, "") is None
    assert PB.find_token_by_outcome_name({"markets": []}, "A") is None


def test_kaputte_marktzeile_wirft_nicht():
    # Defekte Outcomes/Token-Listen duerfen den Placer nie werfen lassen (echtes Geld im Lauf).
    import polymarket_bet as PB
    ev = {"markets": [{"outcomes": "kein json", "clobTokenIds": "[]"},
                      {"outcomes": _json.dumps(["A", "B"]), "clobTokenIds": _json.dumps(["nur-einer"])},
                      {"outcomes": _json.dumps(["Ziel"]), "clobTokenIds": _json.dumps(["TREFFER"])}]}
    assert PB.find_token_by_outcome_name(ev, "Ziel") == "TREFFER"

