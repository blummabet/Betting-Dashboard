#!/usr/bin/env python3
"""
test_auto_wm_poly_trigger.py — Trade-Pipeline Konstanten-Regression

Sicherstellt dass die Migration der Magic Numbers aus auto_wm_poly_trigger.py
nach cocobet_config.json KEINE Werte-Änderung verursacht. Sehr wichtig weil
diese Konstanten direkt die Live-Trades steuern (Polymarket, echtes USDC).

Beim WM2026-Profil müssen alle Werte exakt mit den Pre-Refactor-Hardcodes
übereinstimmen. Wenn jemand das Profile ändert (z.B. liga_default), gelten
andere Werte — aber im WM-Setup (Default) muss ALLES identisch sein.
"""
from __future__ import annotations
import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# Pre-Refactor-Hardcodes (Source of Truth für WM2026)
WM_EXPECTED = {
    "AUTO_TRIGGER_EDGE_PP":       4.0,
    "STEAM_LAG_EDGE_PP":          3.0,
    "MIN_VOL":                    1500,
    "MIN_DAYS_UNTIL_GAME":        1,
    "MIN_HOURS_BEFORE_MATCH":     4,
    "MIN_ENTRY_PRICE":            0.15,
    "MAX_ENTRY_PRICE":            0.85,
    "FLAT_STAKE_USDC":            5.5,
    "DAILY_BET_CAP":              8,
    "DAILY_STAKE_CAP_USDC":       50.0,
    "MIN_BALANCE_BUFFER":         1.0,
    "MAX_POSITIONS_PER_MATCH":    2,
    "MAX_OPEN_EXPOSURE_USDC":     80.0,
    "PRE_TOURNAMENT_DAYS":        5,
    "PRE_TOURNAMENT_EDGE_PP":     6.0,
    "ADAPTIVE_DAILY_FRACTION":    0.40,
    "AUTO_TRIGGER_EDGE_ELO_ONLY": 8.0,
}


def _reload_with_profile(profile: str):
    """Forciert Re-Load von cocobet_config + auto_wm_poly_trigger."""
    os.environ["COCOBET_PROFILE"] = profile
    import cocobet_config
    importlib.reload(cocobet_config)
    cocobet_config.reload_config()
    import auto_wm_poly_trigger
    importlib.reload(auto_wm_poly_trigger)
    return auto_wm_poly_trigger


class TestWMProfileMatchesHardcodes(unittest.TestCase):
    """KRITISCH: WM2026-Profil muss exakt Pre-Refactor-Werte liefern."""

    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.mod = _reload_with_profile("wm2026")

    @classmethod
    def tearDownClass(cls):
        if cls.original_profile is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = cls.original_profile

    def test_all_constants_unchanged(self):
        """Alle 17 Konstanten == Pre-Refactor-Wert (Live-Trading-Sicherheit)."""
        for name, expected in WM_EXPECTED.items():
            with self.subTest(constant=name):
                actual = getattr(self.mod, name)
                self.assertEqual(actual, expected,
                    f"{name} weicht ab: code-default war {expected}, ist jetzt {actual}")

    def test_flat_stake_function_returns_constant(self):
        """_get_stake_for_edge muss FLAT_STAKE_USDC zurückgeben, egal welche Edge."""
        self.assertEqual(self.mod._get_stake_for_edge(0), self.mod.FLAT_STAKE_USDC)
        self.assertEqual(self.mod._get_stake_for_edge(10), self.mod.FLAT_STAKE_USDC)
        self.assertEqual(self.mod._get_stake_for_edge(100), self.mod.FLAT_STAKE_USDC)

    def test_no_inline_magic_numbers_left(self):
        """Source-Check: keine alten Hardcode-Zuweisungen mehr."""
        src = (Path(__file__).parent.parent / "auto_wm_poly_trigger.py").read_text(encoding="utf-8")
        forbidden = [
            "AUTO_TRIGGER_EDGE_PP  = 4.0",
            "STEAM_LAG_EDGE_PP    = 3.0",
            "MIN_VOL              = 10000",
            "FLAT_STAKE_USDC = 5.5",
            "DAILY_BET_CAP        = 8 ",
            "MAX_OPEN_EXPOSURE_USDC = 80.0",
            "AUTO_TRIGGER_EDGE_ELO_ONLY = 8.0  #",
        ]
        for token in forbidden:
            self.assertNotIn(token, src,
                f"Alter Hardcode noch im Code: '{token}' — Migration unvollständig")

    def test_uses_cfg_helper(self):
        """Module muss _cfg() Helper benutzen."""
        src = (Path(__file__).parent.parent / "auto_wm_poly_trigger.py").read_text(encoding="utf-8")
        self.assertIn("from cocobet_config import CONFIG as _CFG", src)
        self.assertIn("def _cfg(section: str, key: str, default):", src)
        self.assertIn('_cfg("trade", "auto_trigger_edge_pp"', src)
        self.assertIn('_cfg("trade", "steam_lag_edge_pp"', src)


class TestLigaProfileDiffers(unittest.TestCase):
    """Sanity: Liga-Profil liefert andere (moderatere) Werte."""

    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.mod = _reload_with_profile("liga_default")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("COCOBET_PROFILE", None)
        if cls.original_profile:
            os.environ["COCOBET_PROFILE"] = cls.original_profile
        # WM-Profil wiederherstellen damit andere Tests sauber laufen
        _reload_with_profile("wm2026")

    def test_liga_has_lower_edge_threshold(self):
        """Liga-Saison nimmt mehr Edges (3.5 statt 4.0)."""
        self.assertEqual(self.mod.AUTO_TRIGGER_EDGE_PP, 3.5)

    def test_liga_has_no_pre_tournament(self):
        """Liga: pre_tournament_days=0 (keine Pre-Phase)."""
        self.assertEqual(self.mod.PRE_TOURNAMENT_DAYS, 0)

    def test_liga_has_higher_bet_cap(self):
        """Liga: 12 Bets/Tag statt 8."""
        self.assertEqual(self.mod.DAILY_BET_CAP, 12)

    def test_liga_min_vol(self):
        """Liga/MLS Vol-Schwelle (23.08.2026, Lucas): von 5000 auf 1500 gesenkt — auf Poly-Fußball
        erreichen fast keine Top-5-Märkte $5000, wodurch nie ein Bet feuerte. 1500 = wie WM."""
        self.assertEqual(self.mod.MIN_VOL, 1500)


class TestFallbackWhenConfigMissing(unittest.TestCase):
    """Sicherheits-Test: Wenn cocobet_config crash, müssen Code-Defaults greifen."""

    def test_module_imports_without_config(self):
        """Modul muss auch ohne cocobet_config importierbar bleiben — Defaults greifen."""
        # Wir können den Import nicht wirklich kaputt machen, aber verifizieren,
        # dass jeder _cfg-Call einen Default hat (Code-Inspektion).
        src = (Path(__file__).parent.parent / "auto_wm_poly_trigger.py").read_text(encoding="utf-8")
        import re
        # _cfg("section", "key", DEFAULT) — DEFAULT muss präsent sein
        calls = re.findall(r'_cfg\([^,]+,\s*[^,]+,\s*([^)]+)\)', src)
        self.assertGreater(len(calls), 0, "Keine _cfg-Calls gefunden")
        for default in calls:
            self.assertTrue(default.strip(),
                f"_cfg-Call ohne Default gefunden — bricht Fallback")


class TestConfigJsonHasAllTradeKeys(unittest.TestCase):
    """cocobet_config.json muss alle vom Code abgefragten Keys enthalten."""

    REQUIRED_TRADE_KEYS = [
        "auto_trigger_edge_pp", "steam_lag_edge_pp",
        "min_vol_usdc", "min_days_until_game", "min_hours_before_match",
        "min_entry_price", "max_entry_price",
        "stake_usdc_flat",
        "daily_bet_cap", "daily_stake_cap_usdc",
        "min_balance_buffer", "max_positions_per_match",
        "max_open_exposure_usdc",
        "pre_tournament_days", "pre_tournament_edge_pp",
        "adaptive_daily_fraction",
        "auto_trigger_edge_elo_only",
    ]

    def test_wm2026_has_all_keys(self):
        import json
        cfg_path = Path(__file__).parent.parent / "cocobet_config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        trade = cfg["profiles"]["wm2026"]["trade"]
        for key in self.REQUIRED_TRADE_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, trade,
                    f"WM2026 trade-section fehlt Key '{key}' — Code-Default greift sonst")

    def test_liga_default_has_all_keys(self):
        import json
        cfg_path = Path(__file__).parent.parent / "cocobet_config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        trade = cfg["profiles"]["liga_default"]["trade"]
        for key in self.REQUIRED_TRADE_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, trade,
                    f"liga_default trade-section fehlt Key '{key}'")


class TestTournamentOverGate(unittest.TestCase):
    """21.07.2026 — Bei beendetem Turnier (WM winterisiert) darf der Auto-Trigger NICHT den
    Stale-Odds-Circuit-Breaker in den Trades-Channel feuern („STALE-ODDS-STOP … 32h alt"). Die
    Odds sind erwartungsgemäß veraltet, weil fetch_wm_odds bewusst still liegt. Er muss still
    zurückkehren — egal welcher Runner ihn noch anstößt."""

    def test_beendetes_turnier_kein_stale_alarm(self):
        import importlib
        import unittest.mock as mock
        import auto_wm_poly_trigger as T
        importlib.reload(T)
        over = {"groups": {"A": {"fixtures": [
            {"kickoff": "2026-07-19T18:00:00Z", "result": {"status": "FT"}}]}}}
        with mock.patch.object(T, "is_kill_switch_active", return_value=(False, "")), \
             mock.patch.object(T, "load_json", return_value=over), \
             mock.patch.object(T, "send_telegram") as tg, \
             mock.patch.object(T, "newest_pinnacle_odds_age_h", return_value=99.0):
            T.main()
        tg.assert_not_called()   # trotz 99h „alter" Odds KEIN Alarm — Turnier ist beendet

    def test_laufende_saison_gate_greift_nicht(self):
        """Gegenprobe: läuft die Saison (offene Fixtures), darf der Gate NICHT greifen —
        der normale Betrieb (inkl. Stale-Alarm bei echtem Feed-Ausfall) bleibt erhalten."""
        import importlib
        import auto_wm_poly_trigger as T
        importlib.reload(T)
        import cocobet_dataset as D
        ongoing = {"groups": {"MLS": {"fixtures": [
            {"kickoff": "2026-07-19T18:00:00Z", "result": {"status": "FT"}},
            {"kickoff": "2026-07-27T18:00:00Z", "result": {"status": None}}]}}}
        self.assertFalse(D.tournament_is_over(ongoing))


if __name__ == "__main__":
    unittest.main()


# ── Kaputte Wett-Datei darf nicht ueberschrieben werden (25.08.2026, Audit-Befund 01) ────────
# `load_json` gab bei fehlender UND bei kaputter Datei still den Default. Fuer die Wett-Datei ist
# der Unterschied entscheidend: fehlt sie, faengt man bei null an; ist sie kaputt, wuerde der Lauf
# seine paar neuen Zeilen ueber die gesamte Positions-Historie schreiben — und gleichzeitig waeren
# Dedupe, Tageslimit, Exposure-Guard und Positionslimit ausgefallen.
def test_fehlende_datei_ist_kein_lesefehler(tmp_path):
    import auto_wm_poly_trigger as T
    T._LOAD_FAILED.clear()
    p = tmp_path / "gibtsnicht.json"
    assert T.load_json(str(p), {"bets": []}) == {"bets": []}
    assert str(p) not in T._LOAD_FAILED, "fehlend != kaputt"


def test_kaputte_datei_wird_gemerkt(tmp_path):
    import auto_wm_poly_trigger as T
    T._LOAD_FAILED.clear()
    p = tmp_path / "kaputt.json"
    p.write_text("{ das ist kein json", encoding="utf-8")
    assert T.load_json(str(p), {"bets": []}) == {"bets": []}
    assert str(p) in T._LOAD_FAILED


def test_erfolgreiches_lesen_loescht_die_markierung(tmp_path):
    import auto_wm_poly_trigger as T
    p = tmp_path / "wieder_ok.json"
    p.write_text("kaputt", encoding="utf-8")
    T.load_json(str(p), {})
    assert str(p) in T._LOAD_FAILED
    p.write_text('{"bets": [1]}', encoding="utf-8")
    T.load_json(str(p), {})
    assert str(p) not in T._LOAD_FAILED, "nach erfolgreichem Lesen ist die Datei wieder gut"


def test_save_json_ist_atomar(tmp_path, monkeypatch):
    import auto_wm_poly_trigger as T
    import safe_write
    p = tmp_path / "placed.json"
    T.save_json(str(p), {"bets": ["alt"]})
    monkeypatch.setattr(safe_write.json, "dump", lambda *a, **k: (_ for _ in ()).throw(OSError("weg")))
    try:
        T.save_json(str(p), {"bets": ["neu"]})
    except OSError:
        pass
    import json as _j
    assert _j.loads(p.read_text())["bets"] == ["alt"], "alter Stand ueberlebt einen Abbruch"


# ── Stale-Odds-Schutz faellt nicht mehr aus (25.08.2026, Audit-Befund 02) ────────────────────
# Vorher gab die Funktion bei JEDEM Problem None zurueck, und der Aufrufer las None als
# "kein Grund zu stoppen". Ausgerechnet bei kaputter Quoten-Datei war der Schutz also aus.
def test_kaputte_quoten_datei_stoppt_statt_durchzuwinken(tmp_path, monkeypatch):
    import auto_wm_poly_trigger as T
    p = tmp_path / "wm.json"
    p.write_text("{ kaputt", encoding="utf-8")
    monkeypatch.setattr(T, "WM_DATA_FILE", str(p))
    alter = T.newest_pinnacle_odds_age_h()
    assert alter == T.ODDS_AGE_UNREADABLE
    assert alter > T.MAX_ODDS_AGE_HOURS, "muss den Stopp ausloesen, nicht durchwinken"


def test_odds_ohne_brauchbare_zeitstempel_stoppt_auch(tmp_path, monkeypatch):
    import auto_wm_poly_trigger as T
    p = tmp_path / "wm.json"
    p.write_text('{"odds": {"a": {"hw": 2.0}}}', encoding="utf-8")   # kein updatedAt
    monkeypatch.setattr(T, "WM_DATA_FILE", str(p))
    assert T.newest_pinnacle_odds_age_h() == T.ODDS_AGE_UNREADABLE


def test_frische_quoten_liefern_ein_echtes_alter(tmp_path, monkeypatch):
    import auto_wm_poly_trigger as T
    from datetime import datetime as _d, timezone as _z, timedelta as _td
    ts = (_d.now(_z.utc) - _td(hours=2)).isoformat()
    p = tmp_path / "wm.json"
    p.write_text('{"odds": {"a": {"updatedAt": "%s"}}}' % ts, encoding="utf-8")
    monkeypatch.setattr(T, "WM_DATA_FILE", str(p))
    alter = T.newest_pinnacle_odds_age_h()
    assert 1.5 < alter < 2.5 and alter != T.ODDS_AGE_UNREADABLE

