#!/usr/bin/env python3
"""
tests/test_poly_heartbeat.py — 15.09.2026: der taegliche Auto-Trader-Heartbeat.

Anlass ist die Karte vom 15.09., die in jeder Zahl falsch war, weil sie genau EINEN Datensatz las
(den der im Juli beendeten WM). Jede Schranke hier wird provoziert: zu jeder gehoert ein Fall, in
dem die Karte sonst wieder etwas Falsches behauptet — und eine taegliche Karte, der man nicht
glauben kann, ist schlimmer als keine.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import poly_heartbeat as H
import poly_offen as PO

JETZT = datetime(2026, 9, 15, 11, 0, tzinfo=timezone.utc)


def _iso(stunden_alt):
    return (JETZT - timedelta(hours=stunden_alt)).isoformat()


def _bet(ds="liga", stunden_alt=1.0, stake=5.5, **kw):
    b = {"placedAt": _iso(stunden_alt), "stake": stake, "status": "placed",
         "home": "A", "away": "B", "_datensatz": ds}
    b.update(kw)
    return b


class AlterText(unittest.TestCase):
    def test_minuten_stunden_tage(self):
        self.assertEqual(H.alter_text(300), "vor 5 Min")
        self.assertEqual(H.alter_text(3600 * 5), "vor 5.0 h")
        self.assertEqual(H.alter_text(3600 * 24 * 65), "vor 65 Tagen")

    def test_lange_spannen_werden_nicht_mehr_in_stunden_gezeigt(self):
        # 🔴 In der Karte stand „vor 1565.4h". Niemand rechnet das im Kopf in Tage um — genau
        # deshalb ist die Stille niemandem aufgefallen.
        self.assertNotIn("h", H.alter_text(1565.4 * 3600))
        self.assertEqual(H.alter_text(1565.4 * 3600), "vor 65 Tagen")

    def test_muell_wirft_nicht(self):
        for x in (None, "viel", float("nan")):
            self.assertIsInstance(H.alter_text(x), str)


class AlleWetten(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _schreib(self, name, obj):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def test_jeder_datensatz_wird_gelesen_und_gestempelt(self):
        # PROVOKATION: genau hier stand `PLACED_FILE = wm_auto_bets_placed.json`. Alles, was
        # seit Juli auf derselben Wallet passiert, war damit unsichtbar.
        self._schreib("wm_auto_bets_placed.json", {"bets": [{"placedAt": "2026-07-12"}]})
        self._schreib("liga_auto_bets_placed.json", {"bets": [{"placedAt": "2026-09-14"}]})
        self._schreib("shortlist_auto_bets_placed.json", {"bets": [{"placedAt": "2026-09-15"}]})
        bets, unlesbar = H.alle_wetten(self.dir)
        self.assertEqual(len(bets), 3)
        self.assertEqual({b["_datensatz"] for b in bets}, {"wm", "liga", "shortlist"})
        self.assertEqual(unlesbar, [])

    def test_die_praefixliste_ist_dieselbe_wie_beim_risiko_deckel(self):
        # Eine zweite Liste waere eine zweite Wahrheit — dieselbe Fehlerklasse wie der Deckel.
        self.assertEqual(H.alle_wetten(self.dir, PO.DATENSATZ_PRAEFIXE), H.alle_wetten(self.dir))

    def test_kaputte_datei_wird_gemeldet_nicht_verschluckt(self):
        with open(os.path.join(self.dir, "liga_auto_bets_placed.json"), "w") as f:
            f.write("{kaputt")
        bets, unlesbar = H.alle_wetten(self.dir)
        self.assertEqual(bets, [])
        self.assertEqual(unlesbar, ["liga_auto_bets_placed.json"])


class LetzterTradeJeFamilie(unittest.TestCase):
    def test_der_shortlist_verdeckt_das_schweigen_des_traders_nicht(self):
        # 🔴 DIE wichtigste Schranke. Beide Systeme laufen auf einer Wallet; der Shortlist setzt
        # taeglich. Stuende nur die juengste Wette da, bliebe „Trader seit 65 Tagen still"
        # dauerhaft unsichtbar — also genau die Tatsache, wegen der die Karte auffiel.
        bets = [_bet("wm", stunden_alt=1565.4), _bet("shortlist", stunden_alt=4.7)]
        fam = H.letzte_je_familie(bets)
        self.assertEqual(fam["Trader"]["_datensatz"], "wm")
        self.assertEqual(fam["Shortlist"]["_datensatz"], "shortlist")

    def test_familie_ohne_wette_gibt_none(self):
        self.assertIsNone(H.letzte_je_familie([_bet("shortlist")])["Trader"])

    def test_wetten_ohne_zeitstempel_kippen_die_auswahl_nicht(self):
        bets = [{"_datensatz": "liga"}, _bet("liga", stunden_alt=3)]
        self.assertIsNotNone(H.letzter_trade(bets))


class Heute(unittest.TestCase):
    def test_zaehlt_ueber_alle_datensaetze(self):
        # PROVOKATION: „Heute 0 Bets", waehrend derselbe Tag eine Shortlist-Wette gesehen hatte.
        bets = [_bet("shortlist", stunden_alt=5, stake=5.0), _bet("liga", stunden_alt=30)]
        n, s = H.heute(bets, "2026-09-15")
        self.assertEqual((n, s), (1, 5.0))

    def test_kaputte_einsaetze_werfen_nicht(self):
        self.assertEqual(H.heute([_bet(stunden_alt=1, stake="viel")], "2026-09-15")[0], 1)


class Angebot(unittest.TestCase):
    def _p(self, n_fix=3, pinn=2, vol=9999, ts=None):
        fx = [{"hasPinnacle": i < pinn, "vol": vol} for i in range(n_fix)]
        return {"generatedAt": ts or _iso(2), "allFixtures": fx}

    def test_zaehlt_pinnacle_und_liquiditaet(self):
        a = H.angebot(self._p(n_fix=5, pinn=3, vol=2000), JETZT)
        self.assertEqual((a["fixtures"], a["mitPinnacle"], a["genugVolumen"]), (5, 3, 3))

    def test_zu_duenne_maerkte_zaehlen_nicht_als_handelbar(self):
        a = H.angebot(self._p(n_fix=5, pinn=5, vol=10), JETZT)
        self.assertEqual(a["genugVolumen"], 0)

    def test_das_abweichende_wm_zeitformat_wirft_nicht(self):
        # Die WM-Datei traegt "19.07.2026 20:41 UTC" statt ISO.
        a = H.angebot(self._p(ts="19.07.2026 20:41 UTC"), JETZT)
        self.assertIsNotNone(a["alterH"])
        self.assertGreater(a["alterH"], 24 * 50)

    def test_unlesbarer_zeitstempel_ist_unbekannt_nicht_null(self):
        self.assertIsNone(H.angebot(self._p(ts="irgendwann"), JETZT)["alterH"])
        self.assertIsNone(H.angebot({"allFixtures": []}, JETZT)["alterH"])

    def test_muell_wirft_nicht(self):
        for p in (None, [], "nein", {}):
            self.assertEqual(H.angebot(p, JETZT)["fixtures"], 0)


class AngebotsZeilen(unittest.TestCase):
    def test_laufende_und_ruhende_werden_getrennt(self):
        je = {"liga": {"fixtures": 57, "mitPinnacle": 57, "genugVolumen": 26, "alterH": 11.7},
              "wm": {"fixtures": 1, "mitPinnacle": 1, "genugVolumen": 1, "alterH": 24 * 57}}
        t = "\n".join(H.angebots_zeilen(je))
        self.assertIn("liga", t)
        self.assertIn("ruht: wm", t)
        # PROVOKATION: eine seit Juli tote WM-Datei jeden Tag als „Angebot" zu zeigen, macht die
        # Zeile zur Luege — und sie taeglich rot zu faerben, macht sie zum Rauschen.
        self.assertNotIn("57 Spiele · 57", t.split("ruht")[1] if "ruht" in t else "")

    def test_ein_spiel_heisst_spiel_nicht_spiele(self):
        je = {"mls": {"fixtures": 1, "mitPinnacle": 1, "genugVolumen": 0, "alterH": 3}}
        self.assertIn("1 Spiel ", "\n".join(H.angebots_zeilen(je)) + " ")

    def test_ohne_laufenden_datensatz_steht_das_da(self):
        self.assertIn("unbekannt", "\n".join(H.angebots_zeilen({})))
        self.assertIn("unbekannt", "\n".join(H.angebots_zeilen(
            {"wm": {"fixtures": 1, "mitPinnacle": 1, "genugVolumen": 1, "alterH": 9999}})))

    def test_das_angebot_haengt_an_keiner_umgebungsvariable(self):
        # 🔴 `cocobet_dataset.active_dataset()` liest COCOBET_DATASET; der Heartbeat-Workflow
        # setzte sie nie → Default „wm" → Preisdatei der beendeten WM. Eine Flaeche, die von
        # einer Variablen abhaengt, an die jemand denken muss, geht falsch, wenn niemand hinsieht.
        quelle = open(os.path.join(str(H.BASE), "poly_heartbeat.py"), encoding="utf-8").read()
        # Der Kopfkommentar DARF die Variable nennen (er erklaert den Fehler) — der Code nicht.
        code = "\n".join(l for l in quelle.splitlines()
                         if not l.lstrip().startswith("#") and "active_dataset()" not in l)
        self.assertNotIn("import cocobet_dataset", code)
        self.assertNotIn("D.file(", code)
        self.assertNotIn('os.environ.get("COCOBET_DATASET"', code)
        self.assertIn("PREIS_DATENSAETZE", code)


class StilleZeile(unittest.TestCase):
    def test_schweigen_wird_ausgesprochen(self):
        self.assertIn("65 Tagen", H.stille_zeile(_iso(24 * 65), JETZT))

    def test_frischer_trade_erzeugt_keine_zeile(self):
        self.assertEqual(H.stille_zeile(_iso(3), JETZT), "")

    def test_nie_gehandelt_ist_kein_leerer_string(self):
        self.assertIn("kein Trade", H.stille_zeile(None, JETZT))

    def test_unlesbarer_zeitstempel_behauptet_keine_stille(self):
        self.assertEqual(H.stille_zeile("irgendwann", JETZT), "")


class Bericht(unittest.TestCase):
    def _karte(self, **kw):
        arg = dict(jetzt=JETZT, schalter_an=True, kill_grund="", balance=188.06,
                   exp={"offen": 15.5, "n": 3, "je": {"liga_auto_bets_placed.json": (5.5, 1),
                                                      "shortlist_auto_bets_placed.json": (10.0, 2)},
                        "unlesbar": []},
                   bets=[_bet("liga", 20.2), _bet("shortlist", 4.7, stake=5.0)],
                   unlesbar=[],
                   a={"liga": {"fixtures": 57, "mitPinnacle": 57, "genugVolumen": 26, "alterH": 11.7}})
        arg.update(kw)
        return H.bericht(**arg)

    def test_beide_deckel_stehen_da(self):
        # Zwei echte Grenzen auf einer Wallet — sich eine auszusuchen waere eine Behauptung.
        t = self._karte()
        self.assertIn("$80 Trader", t)
        self.assertIn("$100 Wallet", t)

    def test_mehrere_datensaetze_werden_aufgeschluesselt(self):
        # PROVOKATION: „liga" und „shortlist" stehen ohnehin bei „Letzter Trade" — geprueft wird
        # deshalb die AUFSCHLUESSELUNG selbst, samt Betrag. Sonst sieht die Summe $15,50 aus wie
        # die eines Systems, und genau diese Verwechslung war der ganze Fehler.
        zeilen = [z for z in self._karte().splitlines() if z.startswith("     · ")]
        self.assertEqual(len(zeilen), 2, "keine Aufschluesselung je Datensatz")
        text = "\n".join(zeilen)
        self.assertIn("liga", text)
        self.assertIn("5.50", text)
        self.assertIn("shortlist", text)
        self.assertIn("10.00", text)

    def test_ein_einzelner_datensatz_braucht_keine_aufschluesselung(self):
        t = self._karte(exp={"offen": 5.5, "n": 1,
                             "je": {"liga_auto_bets_placed.json": (5.5, 1)}, "unlesbar": []})
        self.assertNotIn("     · liga", t)

    def test_schweigen_des_traders_steht_im_kopf(self):
        t = self._karte(bets=[_bet("wm", 24 * 65), _bet("shortlist", 2.0)])
        self.assertIn("Trader: seit 65 Tagen kein Trade", t)

    def test_unlesbare_datei_macht_die_zahlen_ausdruecklich_unvollstaendig(self):
        # Eine kaputte Datei heisst NICHT „keine offenen Positionen".
        t = self._karte(unlesbar=["liga_auto_bets_placed.json"])
        self.assertIn("unvollstaendig", t)

    def test_voller_wallet_deckel_warnt(self):
        t = self._karte(exp={"offen": 95.0, "n": 9, "je": {}, "unlesbar": []})
        self.assertIn("Wallet-Deckel fast voll", t)

    def test_pausierter_schalter_nennt_den_grund(self):
        t = self._karte(schalter_an=False, kill_grund="Balance zu niedrig")
        self.assertIn("PAUSIERT", t)
        self.assertIn("Balance zu niedrig", t)

    def test_die_schwellen_sind_nicht_abgeschrieben(self):
        # Sie standen als Kopien in dieser Datei — dieselbe Zwei-Stellen-Fehlerklasse wie bei
        # der Whale-Rangliste. Jetzt kommen sie aus derselben Config wie der Trigger.
        quelle = open(os.path.join(str(H.BASE), "poly_heartbeat.py"), encoding="utf-8").read()
        for name in ("daily_bet_cap", "daily_stake_cap_usdc", "adaptive_daily_fraction",
                     "max_open_exposure_usdc", "min_vol_usdc"):
            self.assertIn(name, quelle, "%s wird nicht aus der Config gelesen" % name)

    def test_die_offen_definition_ist_die_geteilte(self):
        quelle = open(os.path.join(str(H.BASE), "poly_heartbeat.py"), encoding="utf-8").read()
        self.assertIn("PO.wallet_exposure", quelle)
        self.assertNotIn('not b.get("resolved")', quelle)


if __name__ == "__main__":
    unittest.main()
