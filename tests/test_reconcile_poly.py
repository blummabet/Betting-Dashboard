#!/usr/bin/env python3
"""
test_reconcile_poly.py — manuelle Polymarket-Eingriffe erkennen (23.06.2026, Lucas).
Polymarket ist geoblockt → getter wird gemockt.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import reconcile_poly_positions as R   # noqa: E402


def _getter(positions, trades):
    def g(url):
        return positions if "/positions" in url else trades
    return g


class TestReconcile(unittest.TestCase):
    def _bet(self, **kw):
        b = {"betKey": "D-2-ENG-GHA|Auswärtssieg", "matchKey": "ENG-GHA", "home": "England",
             "away": "Ghana", "market": "Auswärtssieg", "status": "placed", "tokenId": "TOK1",
             "polyPrice": 0.40, "sharesEstimate": 25.0, "placedAt": "2026-06-23T08:00:00Z"}
        b.update(kw)
        return b

    def test_token_gone_prematch_closed_with_real_pnl(self):
        bet = self._bet()
        positions = []  # Wallet hält TOK1 nicht mehr
        trades = [{"asset": "TOK1", "side": "SELL", "price": 0.52, "size": 25.0,
                   "timestamp": "2026-06-23T12:00:00Z"}]
        # Seit dem 16.09. braucht eine Schliessung ZWEI Laeufe: der erste setzt nur den Marker
        # (ein Lauf ist eine Momentaufnahme, kein Befund — Vorfall Brentford–Chelsea).
        R.reconcile([bet], proxy="0xabc", finished_keys=set(),
                    now_iso="2026-06-23T16:00:00Z", getter=_getter(positions, trades))
        self.assertEqual(bet["status"], "placed", "der erste Lauf schliesst nichts")
        changed = R.reconcile([bet], proxy="0xabc", finished_keys=set(),
                              now_iso="2026-06-23T18:00:00Z", getter=_getter(positions, trades))
        self.assertEqual(len(changed), 1)
        self.assertEqual(bet["status"], "closed_manual")
        self.assertEqual(bet["sellPrice"], 0.52)
        self.assertEqual(bet["pnl"], round(25.0 * (0.52 - 0.40), 2))   # echter Sell-P&L

    def test_token_still_held_untouched(self):
        bet = self._bet()
        positions = [{"asset": "TOK1", "size": 25.0}]   # noch gehalten
        changed = R.reconcile([bet], proxy="0xabc", getter=_getter(positions, []))
        self.assertEqual(changed, [])
        self.assertEqual(bet["status"], "placed")

    def test_finished_match_not_treated_as_manual(self):
        bet = self._bet()
        positions = []  # Token weg — aber Spiel fertig → Settlement, NICHT manuell
        changed = R.reconcile([bet], proxy="0xabc", finished_keys={"ENG-GHA"},
                              getter=_getter(positions, []))
        self.assertEqual(changed, [])
        self.assertEqual(bet["status"], "placed")

    def test_api_error_does_nothing(self):
        bet = self._bet()
        # Positions-API FEHLER (None, nicht leere Liste) → konservativ NICHT schließen
        changed = R.reconcile([bet], proxy="0xabc", getter=lambda url: None)
        self.assertEqual(changed, [])
        self.assertEqual(bet["status"], "placed")

    def test_no_sell_trade_marks_without_pnl(self):
        bet = self._bet()
        positions = []
        R.reconcile([bet], proxy="0xabc", now_iso="2026-06-23T16:00:00Z",
                    getter=_getter(positions, []))
        changed = R.reconcile([bet], proxy="0xabc", now_iso="2026-06-23T18:00:00Z",
                              getter=_getter(positions, []))
        self.assertEqual(len(changed), 1)
        self.assertEqual(bet["status"], "closed_manual")
        self.assertIsNone(bet["pnl"])
        self.assertEqual(bet["pnlSource"], "manual_unknown")


if __name__ == "__main__":
    unittest.main()


class TestFrischeWetteWirdNichtGeschlossen(unittest.TestCase):
    """🔴 14.09.2026 (Lucas: „die letzten 2 mmn haben nicht von allein geclosed").

    Sie waren im Buch nie offen. Alle drei Liga-Auto-Bets wurden binnen EINER SEKUNDE nach dem
    Kauf als „manuell auf Polymarket geschlossen" gebucht — von diesem Abgleich, der direkt nach
    dem Trade laeuft und die Positions-API fragt, bevor sie den Fill indexiert hat.

        Ipswich–Liverpool   +0,5 s      Betis–Real +1,1 s      Brentford–Chelsea +0,8 s

    Danach ist die Position im Cockpit unsichtbar (`soldAt` gesetzt), der Auto-Sell fasst sie nie
    wieder an (`status != "placed"`) und ein Ergebnis entsteht nie — waehrend das Geld auf
    Polymarket liegt.
    """

    def _frisch(self, **kw):
        b = {"betKey": "55-49-Under 2.5 Tore", "home": "Brentford", "away": "Chelsea",
             "market": "Under 2.5 Tore", "status": "placed", "tokenId": "TOK1",
             "polyPrice": 0.36, "stake": 5.5, "placedAt": "2026-09-14T14:54:29Z"}
        b.update(kw)
        return b

    def test_eine_sekunde_nach_dem_kauf_wird_nicht_geschlossen(self):
        bet = self._frisch()
        changed = R.reconcile([bet], proxy="0xabc", finished_keys=set(),
                              now_iso="2026-09-14T14:54:30Z",   # +1 Sekunde
                              getter=_getter([], []))           # API kennt den Fill noch nicht
        self.assertEqual(changed, [], "eine Sekunde alt ist kein Verkauf")
        self.assertEqual(bet["status"], "placed")
        self.assertIsNone(bet.get("soldAt"))

    def test_nach_der_schonfrist_wird_wieder_geschlossen(self):
        """Die Gegenprobe: die Schranken duerfen den Zweck des Abgleichs nicht abschaffen."""
        bet = self._frisch()
        R.reconcile([bet], proxy="0xabc", finished_keys=set(),
                    now_iso="2026-09-14T16:00:00Z", getter=_getter([], []))   # Marker
        changed = R.reconcile([bet], proxy="0xabc", finished_keys=set(),
                              now_iso="2026-09-14T17:30:00Z",   # Marker + 90 Min
                              getter=_getter([], []))
        self.assertEqual(len(changed), 1)
        self.assertEqual(bet["status"], "closed_manual")

    def test_ohne_zeitstempel_bleibt_das_alte_verhalten(self):
        bet = self._frisch(placedAt=None)
        R.reconcile([bet], proxy="0xabc", finished_keys=set(),
                    now_iso="2026-09-14T14:54:30Z", getter=_getter([], []))
        changed = R.reconcile([bet], proxy="0xabc", finished_keys=set(),
                              now_iso="2026-09-14T16:30:00Z", getter=_getter([], []))
        self.assertEqual(len(changed), 1, "ohne Alter wird nichts behauptet — wie bisher")


class TestFalschGeschlosseneWerdenZurueckgeholt(unittest.TestCase):
    """Die zweite Haelfte: der Schaden liegt schon im Buch, und `reconcile` sieht nur
    `status == "placed"` — ohne Rueckholung kaeme es an die Zeilen nie wieder heran."""

    def _kaputt(self, **kw):
        b = {"betKey": "55-49-Under 2.5 Tore", "home": "Brentford", "away": "Chelsea",
             "market": "Under 2.5 Tore", "status": "closed_manual", "tokenId": "TOK1",
             "polyPrice": 0.36, "stake": 5.5,
             "placedAt": "2026-09-14T14:54:29.403881+00:00",
             "soldAt": "2026-09-14T14:54:30.207053+00:00",
             "sellReason": "manuell auf Polymarket geschlossen",
             "sellPrice": None, "pnl": None, "pnlSource": "manual_unknown"}
        b.update(kw)
        return b

    def test_handschrift_des_rennens_wird_erkannt(self):
        self.assertTrue(R.falsch_geschlossen(self._kaputt()))

    def test_echter_verkauf_wird_nicht_angetastet(self):
        # Mit Fill-Beleg war es ein echter Verkauf — auch wenn er schnell kam.
        self.assertFalse(R.falsch_geschlossen(self._kaputt(sellPrice=0.52, pnl=3.0)))

    def test_auch_eine_spaete_schliessung_ohne_beleg_ist_unbelegt(self):
        """🔴 16.09.2026 (Lucas: „im Cockpit stand, Chelsea gegen Brentford wurde manuell
        geschlossen. Das stimmt nicht, das ist immer noch offen.").

        Hier stand bis heute das Gegenteil: eine Schliessung mit Abstand zum Kauf galt als echt.
        Das beschrieb den Tathergang vom 14.09. (Indexierungs-Rennen direkt nach dem Fill), nicht
        die Fehlerklasse. Brentford–Chelsea wurde 24 STUNDEN nach dem Kauf falsch geschlossen —
        die Positions-API lieferte den Token in einem einzelnen Lauf nicht, sieben Stunden
        spaeter wieder ($10,12 Positionswert = beide offenen Tickets). Die Wette fiel durch die
        Zwei-Minuten-Regel und blieb unsichtbar im Buch liegen.

        Entscheidend ist der BELEG, nicht die Uhr: keine Verkaufsspur, aber Token in der Wallet
        (das prueft `zurueckholen`) — dann war die Buchung falsch, egal wie alt sie ist.
        """
        self.assertTrue(R.falsch_geschlossen(
            self._kaputt(soldAt="2026-09-15T14:45:18+00:00")))

    def test_die_wallet_entscheidet_nicht_die_uhr(self):
        """Die Gegenrichtung derselben Regel: ohne Token in der Wallet wird auch eine sehr
        spaete Schliessung NICHT angefasst."""
        bet = self._kaputt(soldAt="2026-09-15T14:45:18+00:00")
        self.assertEqual(R.zurueckholen([bet], {}, now_iso="2026-09-16T08:00:00Z"), [])
        self.assertEqual(bet["status"], "closed_manual")
        zurueck = R.zurueckholen([bet], {"TOK1": 15.28}, now_iso="2026-09-16T08:00:00Z")
        self.assertEqual(len(zurueck), 1)
        self.assertEqual(bet["status"], "placed")

    def test_wallet_haelt_den_token_also_lief_die_wette(self):
        bet = self._kaputt()
        zurueck = R.zurueckholen([bet], {"TOK1": 15.0}, now_iso="2026-09-14T16:00:00Z")
        self.assertEqual(len(zurueck), 1)
        self.assertEqual(bet["status"], "placed")
        self.assertIsNone(bet["soldAt"])
        self.assertIn("Wallet", bet["reopenGrund"])

    def test_ohne_token_in_der_wallet_wird_nichts_zurueckgeholt(self):
        """⭐ Kein Raten in die Gegenrichtung: haelt die Wallet nichts, war die Position
        vielleicht wirklich weg. Zurueckgeholt wird nur gegen einen Beleg."""
        bet = self._kaputt()
        self.assertEqual(R.zurueckholen([bet], {}, now_iso="2026-09-14T16:00:00Z"), [])
        self.assertEqual(bet["status"], "closed_manual")

    def test_staub_zaehlt_nicht_als_position(self):
        bet = self._kaputt()
        self.assertEqual(R.zurueckholen([bet], {"TOK1": 0.4}, now_iso="2026-09-14T16:00:00Z"), [])

    def test_reconcile_holt_im_selben_lauf_zurueck(self):
        bet = self._kaputt()
        changed = R.reconcile([bet], proxy="0xabc", finished_keys=set(),
                              now_iso="2026-09-14T16:00:00Z",
                              getter=_getter([{"asset": "TOK1", "size": 15.0}], []))
        self.assertEqual(len(changed), 1)
        self.assertEqual(bet["status"], "placed")


class TestEineAbwesenheitIstKeinBeleg(unittest.TestCase):
    """🔴 16.09.2026 — der Vorfall Brentford–Chelsea, als Regel.

    Gekauft 14.09. 14:54, „verkauft" 15.09. 14:45 (+24 h). Kein Indexierungs-Rennen: die
    Positions-API lieferte den Token in EINEM Lauf nicht. Sieben Stunden spaeter stand er
    wieder drin — `liga_poly_balance.json` meldete um 22:00 Positionen im Wert von $10,12,
    und das sind genau die beiden offenen Tickets.

    Was das kostet, ist gemessen: Seattle Sounders–Austin wurde am 18.08. so fehlgebucht, war
    fuer den Verkaufs-Manager unsichtbar (der sieht nur `status == "placed"`), lief am 20.08.
    ins Spiel und verlor den vollen Einsatz. Von vier Positionen, die je in ein Spiel gelaufen
    sind, geht diese eine allein auf diese Fehlbuchung.
    """

    def _bet(self, **kw):
        b = {"betKey": "55-49-Under 2.5 Tore", "home": "Brentford", "away": "Chelsea",
             "market": "Under 2.5 Tore", "status": "placed", "tokenId": "TOK1",
             "polyPrice": 0.36, "stake": 5.5,
             "placedAt": "2026-09-14T14:54:29+00:00"}
        b.update(kw)
        return b

    def test_ein_einzelner_fehlender_lauf_schliesst_nichts(self):
        bet = self._bet()
        changed = R.reconcile([bet], proxy="0xabc", finished_keys=set(),
                              now_iso="2026-09-15T14:45:18Z", getter=_getter([], []))
        self.assertEqual(changed, [], "ein Lauf ist eine Momentaufnahme, kein Befund")
        self.assertEqual(bet["status"], "placed")
        self.assertEqual(bet["nichtGehaltenSeit"], "2026-09-15T14:45:18Z")

    def test_taucht_die_position_wieder_auf_beginnt_die_zaehlung_von_vorn(self):
        """Genau der echte Verlauf: fehlt um 14:45, ist um 22:00 wieder da. Ohne dieses
        Zuruecksetzen summierte sich eine alte Fehlanzeige ueber Tage zu einem „Befund"."""
        bet = self._bet()
        R.reconcile([bet], proxy="0xabc", now_iso="2026-09-15T14:45:18Z", getter=_getter([], []))
        R.reconcile([bet], proxy="0xabc", now_iso="2026-09-15T22:00:00Z",
                    getter=_getter([{"asset": "TOK1", "size": 15.28}], []))
        self.assertNotIn("nichtGehaltenSeit", bet)
        changed = R.reconcile([bet], proxy="0xabc", now_iso="2026-09-15T22:20:00Z",
                              getter=_getter([], []))
        self.assertEqual(changed, [], "die Luecke faengt bei null an, nicht bei sieben Stunden")
        self.assertEqual(bet["status"], "placed")

    def test_eine_dauerhafte_luecke_wird_sehr_wohl_gebucht(self):
        """Die Schranke darf den Zweck nicht abschaffen: wer wirklich verkauft hat, soll nicht
        ewig Alarme bekommen."""
        bet = self._bet()
        R.reconcile([bet], proxy="0xabc", now_iso="2026-09-15T14:45:00Z", getter=_getter([], []))
        changed = R.reconcile([bet], proxy="0xabc", now_iso="2026-09-15T16:00:00Z",
                              getter=_getter([], []))
        self.assertEqual(len(changed), 1)
        self.assertEqual(bet["status"], "closed_manual")

    def test_die_fehlbuchung_wird_im_naechsten_lauf_repariert(self):
        """Der Weg zurueck fuer das, was schon im Buch steht — ohne Handarbeit an der Datei."""
        bet = self._bet(status="closed_manual", soldAt="2026-09-15T14:45:18+00:00",
                        sellReason="manuell auf Polymarket geschlossen",
                        sellPrice=None, pnl=None, pnlSource="manual_unknown")
        changed = R.reconcile([bet], proxy="0xabc", finished_keys=set(),
                              now_iso="2026-09-16T08:00:00Z",
                              getter=_getter([{"asset": "TOK1", "size": 15.28}], []))
        self.assertEqual(len(changed), 1)
        self.assertEqual(bet["status"], "placed")
        self.assertIsNone(bet["soldAt"])
        self.assertIn("Verkaufs-Beleg", bet["reopenGrund"])

    def test_ein_echter_verkauf_bleibt_ein_verkauf(self):
        """Mit Fill-Beleg wird nichts zurueckgeholt — auch dann nicht, wenn die Wallet wieder
        etwas haelt (nachgekauft ist nicht nie-verkauft)."""
        bet = self._bet(status="closed_manual", soldAt="2026-09-15T14:45:18+00:00",
                        sellPrice=0.34, pnl=-0.31, pnlSource="manual_sell_trade")
        self.assertEqual(R.zurueckholen([bet], {"TOK1": 15.28}, now_iso="2026-09-16T08:00:00Z"), [])
        self.assertEqual(bet["status"], "closed_manual")
