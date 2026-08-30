"""tests/test_moneymap_quellen.py — 30.08.2026

Aus Lucas' Checkup der Uebersicht: Chelsea–Brighton stand als „✅ knapp einig · 3 / 3" da.
Die dritte Quelle waren $1.410 Poly-Volumen neben €328.000 Betfair-Geld. Napoli–Como genauso
mit $1.787.

Der Grund war eine halb durchgezogene Entscheidung: _mm_money_ok schliesst src=="scan" seit dem
23.08. als Geldquelle aus (ein Scan-Poly liefert nur den fairen Preis) und das Frontend
beschriftet ihn als „Poly · Preis (duenn)" — nSources, mmStrong und der no_anchor-Rueckfall
haben davon nie erfahren.
"""
import unittest

import betfair_consensus as BC


def game(**kw):
    g = {"matchId": "1", "home": "Chelsea", "away": "Brighton", "league": "EPL",
         "live": False, "kickoff": None, "verdict": "konsens",
         "moneySide": "home", "moneyName": "Chelsea", "moneySharePct": 77, "totVol": 328000,
         "pinn": {"fav": "home", "home": 0.51, "draw": 0.25, "away": 0.24}}
    g.update(kw)
    return g


def poly(usd, src="upcoming", side="home", share=70):
    return {"side": side, "name": "Chelsea", "sharePct": share, "usd": usd, "src": src}


class Quellen(unittest.TestCase):
    def test_scan_preis_zaehlt_nicht_als_quelle(self):
        r = BC.money_map_row(game(), poly(1410, "scan"))
        self.assertEqual(r["nSources"], 2, "Betfair + Pinnacle — der duenne Preis ist keine Quelle")
        self.assertFalse(r["polyGeld"])

    def test_die_poly_seite_bleibt_trotzdem_sichtbar(self):
        # Der Preis ist Information, nur eben keine Bestaetigung. Er darf nicht verschwinden.
        r = BC.money_map_row(game(), poly(1410, "scan"))
        self.assertIsNotNone(r["poly"])
        self.assertEqual(r["poly"]["usd"], 1410)
        self.assertEqual(r["poly"]["src"], "scan")

    def test_echtes_poly_geld_zaehlt_weiter(self):
        r = BC.money_map_row(game(), poly(116000, "upcoming"))
        self.assertEqual(r["nSources"], 3)
        self.assertTrue(r["polyGeld"])

    def test_scan_kann_kein_verdikt_ohne_anker_tragen(self):
        # Ohne Pinnacle-Anker wurde Konsens/Divergenz aus Betfair vs Poly abgeleitet. Mit einem
        # $1.4K-Preis waere das ein Urteil aus dem Nichts.
        r = BC.money_map_row(game(verdict="no_anchor", pinn=None), poly(1410, "scan"))
        self.assertEqual(r["verdict"], "no_anchor")
        r2 = BC.money_map_row(game(verdict="no_anchor", pinn=None), poly(116000, "upcoming"))
        self.assertEqual(r2["verdict"], "konsens")

    def test_mmStrong_braucht_echtes_geld_auf_beiden_seiten(self):
        r = BC.money_map_row(game(), poly(1410, "scan", share=90))
        self.assertFalse(r["mmStrong"], "90% von $1.410 sind keine starke zweite Meinung")
        self.assertTrue(BC.money_map_row(game(), poly(116000, share=90))["mmStrong"])

    def test_eine_definition_fuer_beide_stellen(self):
        # _mm_money_ok und nSources muessen dasselbe „ist das Geld?" benutzen — sonst faellt eine
        # Zeile durchs Geld-Gate und zaehlt trotzdem drei Quellen (oder umgekehrt).
        for usd, src in ((1410, "scan"), (116000, "upcoming"), (0, "upcoming"), (500, "close")):
            pl = poly(usd, src)
            r = BC.money_map_row(game(), pl)
            self.assertEqual(r["polyGeld"], BC._poly_ist_geld(pl), (usd, src))

    def test_ohne_poly_unveraendert(self):
        r = BC.money_map_row(game(), None)
        self.assertEqual(r["nSources"], 2)
        self.assertFalse(r["polyGeld"])
        self.assertIsNone(r["poly"])


class SteamDeckel(unittest.TestCase):
    """Drei Picks im Bestand trugen einen Pinnacle-Move ueber 25pp — 5.64→1.50 (48,9pp),
    4.38→1.49 (44,3pp) und 1.56→1.11 (28,0pp, ein BET). Ein Vor-Anpfiff-Move dieser Groesse
    existiert praktisch nicht; das ist ein stehengebliebener Opener."""

    def test_deckel_stimmt_mit_der_uebersicht_ueberein(self):
        import re
        from pathlib import Path
        import generate_wm_picks as G
        md = (Path(__file__).parent.parent / "main-dashboard.js").read_text(encoding="utf-8")
        js = float(re.search(r"var SHARP_MAX_PP = (\d+)", md).group(1))
        self.assertEqual(G.STEAM_MAX_MOVE_PP, js,
                         "Engine und Uebersicht muessen dieselbe Grenze ziehen")

    def test_unglaubwuerdiger_move_faellt_raus(self):
        import generate_wm_picks as G
        self.assertTrue(G._steam_move_plausibel(24.9))
        self.assertTrue(G._steam_move_plausibel(-25.0))
        self.assertFalse(G._steam_move_plausibel(48.9))
        self.assertFalse(G._steam_move_plausibel(28.0))

    def test_fehlender_move_ist_kein_ja(self):
        import generate_wm_picks as G
        self.assertFalse(G._steam_move_plausibel(None))
        self.assertFalse(G._steam_move_plausibel("12"))


if __name__ == "__main__":
    unittest.main()
