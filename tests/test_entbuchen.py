#!/usr/bin/env python3
"""
tests/test_entbuchen.py — 21.09.2026: eine Zeile, die nie Geld bewegt hat, darf nicht als
Verlust in der Bilanz stehen.

🔴 Lucas, 21.09. 01:04 UTC: „Das kam. Aber auf poly wurde nicht gesetzt."

Deportivo Toluca vs Santos Laguna, 5 $, Order-ID, Zeile im Buch, `result: LOSS, pnl: -5.00`.
Das Wallet stand von 21:53 bis 04:39 unveraendert bei 178,2312. Zwei solche Zeilen im Buch,
zusammen 10 $ — die Bilanz war um diesen Betrag schlechter als die Wirklichkeit.

`check_wette_hat_die_kasse_beruehrt` hat das seit heute frueh GEMELDET. Gezogen hat die Meldung
nichts. Fehlerklasse: **ein Befund, der gemeldet, aber nicht gezogen wird.**

Die zweite Haelfte des Tests ist die wichtigere: `entbuchen` darf NUR ziehen, was bewiesen ist.
„Nicht pruefbar" bleibt gebucht — eine Zeile aus der Zeit vor dem Verlauf ist unbeobachtet,
nicht widerlegt. Sie stillschweigend herauszunehmen waere derselbe Fehler noch einmal, nur in
die andere Richtung.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poly_offen as PO
import wallet_abgleich as WA

T0 = datetime(2026, 9, 20, 21, 0, tzinfo=timezone.utc)


def _iso(m):
    return (T0 + timedelta(minutes=m)).isoformat()


def _verlauf(*paare):
    """[(Minute, usdc)] -> Verlauf."""
    return [{"ts": _iso(m), "usdc": u, "positions": 0.0} for m, u in paare]


def _bet(minute, stake=5.0, result="LOSS", pnl=-5.0, key="k"):
    return {"betKey": key, "stake": stake, "placedAt": _iso(minute),
            "status": "lost" if result == "LOSS" else "won", "result": result,
            "pnl": pnl, "resolvedAt": _iso(minute + 600)}


# Ein Verlauf, der den ganzen Zeitraum abdeckt: ein echter Kauf um Minute 10, danach Stillstand.
VERLAUF = _verlauf((0, 180.0), (15, 174.93), (30, 174.93), (60, 174.93), (120, 174.93))


class TestDerToluca_Fall(unittest.TestCase):
    def test_eine_zeile_ohne_wallet_bewegung_faellt_aus_der_bilanz(self):
        bets = [_bet(50, key="toluca")]
        g = WA.entbuchen(bets, VERLAUF)
        self.assertEqual(len(g), 1)
        self.assertEqual(bets[0]["pnl"], 0.0)
        self.assertIs(bets[0]["bilanz"], False)
        self.assertEqual(bets[0]["result"], "UNBELEGT")
        self.assertEqual(bets[0]["status"], "unbelegt")

    def test_der_alte_wert_bleibt_lesbar(self):
        """Nichts wird vernichtet — sonst laesst sich der Vorfall spaeter nicht mehr nachrechnen."""
        bets = [_bet(50)]
        WA.entbuchen(bets, VERLAUF)
        self.assertEqual(bets[0]["pnlGebucht"], -5.0)
        self.assertEqual(bets[0]["resultGebucht"], "LOSS")
        self.assertEqual(bets[0]["statusGebucht"], "lost")
        self.assertIn("kein freier Abgang", bets[0]["kasseGrund"])

    def test_eine_belegte_zeile_bleibt_unangetastet(self):
        """⭐ Die Gegenprobe. Ohne sie wuerde ein `entbuchen`, das ALLES zieht, gruen sein."""
        bets = [_bet(10, key="echt")]          # Kauf um Minute 10, Abgang im Schnappschuss 15
        g = WA.entbuchen(bets, VERLAUF)
        self.assertEqual(g, [])
        self.assertEqual(bets[0]["pnl"], -5.0)
        self.assertEqual(bets[0]["result"], "LOSS")
        self.assertNotIn("bilanz", bets[0])


class TestNurWasBewiesenIst(unittest.TestCase):
    """Lucas' Bedingung: nur `ohne`, nie `unpruefbar`."""

    def test_ohne_verlauf_wird_nichts_gezogen(self):
        bets = [_bet(50)]
        self.assertEqual(WA.entbuchen(bets, []), [])
        self.assertEqual(bets[0]["pnl"], -5.0)

    def test_eine_zeile_vor_dem_verlauf_bleibt_gebucht(self):
        """Der haeufigste Fall: der Verlauf laeuft erst seit heute, die Zeile ist von letzter
        Woche. Unbeobachtet ist nicht widerlegt."""
        bets = [_bet(-5000)]
        self.assertEqual(WA.entbuchen(bets, VERLAUF), [])
        self.assertEqual(bets[0]["pnl"], -5.0)
        self.assertNotIn("bilanz", bets[0])

    def test_eine_zeile_ohne_zeitstempel_bleibt_gebucht(self):
        bets = [_bet(50)]
        bets[0]["placedAt"] = None
        self.assertEqual(WA.entbuchen(bets, VERLAUF), [])
        self.assertEqual(bets[0]["pnl"], -5.0)


class TestWasNichtAngefasstWird(unittest.TestCase):
    def test_eine_offene_zeile_wird_nicht_entbucht(self):
        """Eine Wette ohne Ausgang hat noch gar keine Bilanz-Zeile. Ihr fehlender Kauf ist
        Sache von `check_ruhende_order_ist_keine_position`, nicht dieser Stelle."""
        bets = [{"betKey": "x", "stake": 5.0, "placedAt": _iso(50), "status": "placed"}]
        self.assertEqual(WA.entbuchen(bets, VERLAUF), [])
        self.assertNotIn("bilanz", bets[0])

    def test_zweimal_laufen_aendert_nichts_mehr(self):
        """Der Lauf faehrt alle paar Minuten — ohne Idempotenz wuerde `pnlGebucht` beim zweiten
        Mal auf 0.0 ueberschrieben und der echte Wert waere weg."""
        bets = [_bet(50)]
        self.assertEqual(len(WA.entbuchen(bets, VERLAUF)), 1)
        self.assertEqual(WA.entbuchen(bets, VERLAUF), [])
        self.assertEqual(bets[0]["pnlGebucht"], -5.0)

    def test_ein_gewinn_ohne_kasse_wird_genauso_gezogen(self):
        """Es geht nicht darum, Verluste wegzurechnen — eine erfundene Zeile ist in beide
        Richtungen falsch."""
        bets = [_bet(50, result="WIN", pnl=+3.9)]
        self.assertEqual(len(WA.entbuchen(bets, VERLAUF)), 1)
        self.assertEqual(bets[0]["pnl"], 0.0)


class TestEineEntbuchteZeileBindetKeinGeld(unittest.TestCase):
    """🔴 Die Falle beim Bauen: ein neuer Status, den die Terminal-Liste nicht kennt, macht die
    Zeile WIEDER OFFEN — und sie belegt den Exposure-Deckel, obwohl nie Geld floss."""

    def test_unbelegt_ist_terminal(self):
        bets = [_bet(50)]
        WA.entbuchen(bets, VERLAUF)
        self.assertFalse(PO.ist_offen(bets[0]))

    def test_auch_ohne_resolvedAt(self):
        bets = [_bet(50)]
        bets[0].pop("resolvedAt")
        WA.entbuchen(bets, VERLAUF)
        self.assertFalse(PO.ist_offen(bets[0]),
                         "der Status allein muss reichen, nicht ein Nebenfeld")

    def test_beide_listen_tragen_es_einzeln(self):
        """🔴 Beim Mutationstest aufgefallen: `unbelegt` aus TERMINAL_STATUS zu entfernen blieb
        gruen, weil TERMINAL_RESULT es noch trug — und umgekehrt. Ein Test, der nur die
        Kombination prueft, deckt eine halb zurueckgebaute Regel nicht auf."""
        self.assertIn("unbelegt", PO.TERMINAL_STATUS)
        self.assertIn("UNBELEGT", PO.TERMINAL_RESULT)
        self.assertFalse(PO.ist_offen({"status": "unbelegt", "stake": 5}))
        self.assertFalse(PO.ist_offen({"result": "UNBELEGT", "stake": 5}))

    def test_sie_belegt_den_deckel_nicht(self):
        bets = [_bet(50)]
        WA.entbuchen(bets, VERLAUF)
        self.assertEqual(PO.offene_summe(bets), (0.0, 0))


class TestDerText(unittest.TestCase):
    def test_leer_heisst_still(self):
        self.assertEqual(WA.entbucht_text([]), "")

    def test_er_nennt_die_summe(self):
        bets = [_bet(50, key="a"), _bet(55, key="b")]
        t = WA.entbucht_text(WA.entbuchen(bets, VERLAUF))
        self.assertIn("2 Zeile(n)", t)
        self.assertIn("-10.00", t)


class TestDerWaechterMeldetDenErledigtenFallNichtWeiter(unittest.TestCase):
    """🔴 Ein abgeschlossener Zustand, der als Stoerung gerendert wird — dieselbe Fehlerklasse
    wie die ruhende WM-Batterie in der Stoerungsmeldung. Ohne diesen Riegel stuende der Befund
    ab jetzt jeden Tag in der Meldung, mit 0,00 $ dahinter."""

    def test_pruefe_buch_sieht_eine_entbuchte_zeile_weiter(self):
        """`pruefe_buch` selbst filtert NICHT — es ist die Messung, nicht das Urteil."""
        bets = [_bet(50)]
        WA.entbuchen(bets, VERLAUF)
        self.assertEqual(len(WA.pruefe_buch(bets, VERLAUF)["ohne"]), 1)

    def test_der_check_filtert_sie_heraus(self):
        import json
        import tempfile
        from pathlib import Path
        import poly_data_integrity as PI
        bets = [_bet(50)]
        WA.entbuchen(bets, VERLAUF)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "liga_poly_verlauf.json").write_text(json.dumps(VERLAUF))
            (Path(d) / "shortlist_auto_bets_placed.json").write_text(
                json.dumps({"bets": bets}))
            alt = PI.__file__
            try:
                PI.__file__ = str(Path(d) / "poly_data_integrity.py")
                c = PI.check_wette_hat_die_kasse_beruehrt(None)
            finally:
                PI.__file__ = alt
        self.assertTrue(c["ok"], c.get("failures"))


class TestDerGanzeLaufZiehtSie(unittest.TestCase):
    """⭐ Gegenprobe am ganzen Lauf. Beim Bauen rutschte der Aufruf versehentlich IN den
    `if entbucht:`-Zweig darueber und verschluckte die Haengend-Meldung — ein Test an der
    Funktion allein haette das nie gesehen."""

    def test_main_entbucht_und_schreibt_es_weg(self):
        import json
        import tempfile
        from pathlib import Path
        import shortlist_auto_bet as SAB

        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "liga_poly_verlauf.json").write_text(json.dumps(VERLAUF))
            placed = p / "placed.json"
            placed.write_text(json.dumps({"bets": [_bet(50, key="toluca")]}))
            leer = p / "leer.json"
            leer.write_text("{}")
            alt = {k: getattr(SAB, k) for k in
                   ("BASE", "PLACED_FILE", "TRACK_FILE", "OFFEN_FILE", "CLOSE_FILE",
                    "LEDGER_FILE", "_balance")}
            try:
                SAB.BASE = p
                SAB.PLACED_FILE = placed
                SAB.TRACK_FILE = leer
                SAB.OFFEN_FILE = leer
                SAB.CLOSE_FILE = leer
                SAB.LEDGER_FILE = p / "ledger.json"
                SAB.LEDGER_FILE.write_text("[]")
                SAB._balance = lambda base_dir=None: (250.0, "TEST")
                SAB.main()
            finally:
                for k, v in alt.items():
                    setattr(SAB, k, v)
            raus = json.loads(placed.read_text())["bets"][0]
        self.assertIs(raus["bilanz"], False)
        self.assertEqual(raus["pnl"], 0.0)
        self.assertEqual(raus["pnlGebucht"], -5.0)


if __name__ == "__main__":
    unittest.main()
