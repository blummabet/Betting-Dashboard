"""Der CLV muss fair gegen fair rechnen — 12.09.2026 (Lucas, nach dem Plattform-Audit).

Lucas: „wir koennen keine guten CLV haben wenn wir die picks erst am selben tag posten — wie
soll das gehen?"

Der Einwand stimmte im Ergebnis, aber nicht in der Ursache, und ich hatte ihm vorher das
Gegenteil gesagt („der CLV ist belegt, nur in die falsche Richtung"). Das war falsch. Ein spaeter
Einstieg macht den CLV KLEINER in beide Richtungen, nicht systematisch negativ. Die Systematik
kam aus der Formel:

    clvPP = Pinnacle-Closing-FAIR-Wahrscheinlichkeit − 1/Einstiegsquote
                               ^^^^                    ^^^^^^^^^^^^^^^^
                         power-entvigt               ROH, mit voller Marge

Wir ziehen uns die Marge unseres eigenen Buchs vom CLV ab. Der Fingerabdruck am echten Bestand:

    Einstieg bei soft     (Overround 6,6 %)   n=90   Ø CLV −1,56 pp   Median −1,15
    Einstieg bei Pinnacle (Overround 4,4 %)   n=12   Ø CLV −0,41 pp   Median  ±0,00

Kaeme es vom Postzeitpunkt, traefe es beide Buecher gleich. Es skaliert mit der Marge.

An 29 Liga-1X2-Picks mit eindeutig zuordenbarem Einstiegs-Snapshot, beide Seiten power-entvigt:
aus Ø −1,60 pp wird **+0,32 pp** (Band −0,77 … +1,41), Close geschlagen in 62 % statt 31 %.
Also: nicht negativ — aber auch nicht belegt positiv.
"""
import unittest
from pathlib import Path

import resolve_steam_clv as R
from resolve_wm_results import power_devig

WURZEL = Path(__file__).resolve().parent.parent


class TestFaireEinstiegsWahrscheinlichkeit(unittest.TestCase):
    def test_die_marge_verschwindet(self):
        markt = {"hw": 2.0, "dr": 3.6, "aw": 3.9}
        roh = 1 / 2.0
        fair = R.fair_entry_prob(markt, "Heimsieg")
        self.assertIsNotNone(fair)
        self.assertLess(fair, roh, "die faire Wahrscheinlichkeit liegt unter der rohen")
        summe = sum(R.fair_entry_prob(markt, m) for m in ("Heimsieg", "Unentschieden", "Auswärtssieg"))
        self.assertAlmostEqual(summe, 1.0, places=3, msg="entvigt summiert sich der Markt auf 1")

    def test_ein_margenfreier_markt_aendert_fast_nichts(self):
        """Gegenprobe: ohne Marge darf die Korrektur nicht aus dem Nichts etwas erzeugen."""
        markt = {"hw": 3.0, "dr": 3.0, "aw": 3.0}     # Summe der Kehrwerte = 1,0
        self.assertAlmostEqual(R.fair_entry_prob(markt, "Heimsieg"), 1 / 3.0, places=4)

    def test_unvollstaendiger_markt_gibt_None(self):
        for markt in ({"hw": 2.0, "dr": 3.6}, {"hw": 2.0, "dr": 3.6, "aw": None},
                      {"hw": 1.0, "dr": 3.6, "aw": 3.9}, None):
            self.assertIsNone(R.fair_entry_prob(markt, "Heimsieg"),
                              "lieber keine Zahl als eine geratene")

    def test_muell_im_markt_gibt_None_statt_zu_krachen(self):
        """Ohne die Typpruefung faellt `power_devig` hier mit einem TypeError um — und ein
        Resolver, der an einer kaputten Zeile stirbt, laesst alle folgenden Picks ohne CLV
        (dieselbe Lehre wie beim Validator-Absturz heute frueh)."""
        for markt in ({"hw": 2.0, "dr": 3.6, "aw": "3.9"}, {"hw": "x", "dr": 3.6, "aw": 3.9},
                      {"hw": 2.0, "dr": [], "aw": 3.9}):
            self.assertIsNone(R.fair_entry_prob(markt, "Heimsieg"))

    def test_ueber_unter_wird_zweiweg_entvigt(self):
        """12.09.2026 nachgezogen: anfangs deckte der Fix nur 1X2 ab — 29 von 87 Zeilen. Die
        restlichen waren Ueber/Unter (34) und Doppelte Chance (21). Der Quotenverlauf traegt
        o15/u15, o25/u25, o35/u35 und BTTS seit dem 06.09. mit; sie fehlten hier, nicht in den
        Daten. Mit ihnen sind es 63 von 87."""
        markt = {"o25": 1.85, "u25": 1.95}
        fair_o = R.fair_entry_prob(markt, "Über 2.5 Tore")
        fair_u = R.fair_entry_prob(markt, "Unter 2.5 Tore")
        self.assertIsNotNone(fair_o)
        self.assertLess(fair_o, 1 / 1.85, "die Marge muss raus")
        self.assertAlmostEqual(fair_o + fair_u, 1.0, places=3)

    def test_doppelte_chance_ist_die_summe_zweier_entvigter_seiten(self):
        """Exakt, nicht geschaetzt: DC teilt sich die Quoten mit 1X2."""
        markt = {"hw": 2.0, "dr": 3.6, "aw": 3.9}
        h = R.fair_entry_prob(markt, "Heimsieg")
        d = R.fair_entry_prob(markt, "Unentschieden")
        self.assertAlmostEqual(R.fair_entry_prob(markt, "Doppelte Chance — 1X"), h + d, places=6)

    def test_asian_handicap_bleibt_draussen(self):
        """Fuer AH gibt es keine Gegenseite im Verlauf. Eine geschaetzte waere genau die
        erfundene Zahl, die dieser Fix beseitigt."""
        self.assertIsNone(R.fair_entry_prob({"hw": 2.0, "dr": 3.6, "aw": 3.9}, "AH Heim −1.5"))

    def test_doppelte_chance_findet_keinen_einstiegs_snapshot(self):
        """Die DC hat im Verlauf keinen eigenen Preis — also laesst sich der Einstieg nicht
        ueber ihn wiederfinden. Lieber keine Zeile als eine an einem beliebigen Snapshot."""
        verlauf = [{"bk": "public", "hw": 2.0, "dr": 3.6, "aw": 3.9}]
        self.assertIsNone(R.einstiegs_markt(verlauf, 1.35, "Doppelte Chance — 1X", "public"))


class TestFairClv(unittest.TestCase):
    def test_fair_liegt_ueber_roh(self):
        markt = {"hw": 2.0, "dr": 3.6, "aw": 3.9}
        roh = R.steam_clv_pp(0.48, 2.0)
        fair = R.fair_clv_pp(0.48, R.fair_entry_prob(markt, "Heimsieg"))
        self.assertGreater(fair, roh, "die eigene Marge darf nicht mehr als CLV-Verlust zaehlen")
        self.assertAlmostEqual(fair - roh, 1.13, places=1)

    def test_ohne_faire_einstiegswahrscheinlichkeit_gibt_es_keine_zahl(self):
        self.assertIsNone(R.fair_clv_pp(0.48, None))
        self.assertIsNone(R.fair_clv_pp(None, 0.48))

    def test_die_alte_zahl_bleibt_unveraendert(self):
        """`clvPP` wird NICHT umdefiniert — sonst haetten alte und neue Zeilen dieselbe
        Bezeichnung fuer zwei verschiedene Dinge."""
        self.assertEqual(R.steam_clv_pp(0.48, 2.0), -2.0)


class TestEinstiegsMarktSuche(unittest.TestCase):
    VERLAUF = [
        {"bk": "public", "hw": 2.50, "dr": 3.4, "aw": 2.8},
        {"bk": "public", "hw": 2.02, "dr": 3.5, "aw": 3.6},
        {"bk": "pinnacle", "hw": 2.00, "dr": 3.6, "aw": 3.9},
    ]

    def test_nimmt_den_snapshot_mit_dem_passenden_preis(self):
        m = R.einstiegs_markt(self.VERLAUF, 2.0, "Heimsieg", "public")
        self.assertEqual(m["hw"], 2.02)

    def test_trennt_die_buecher(self):
        m = R.einstiegs_markt(self.VERLAUF, 2.0, "Heimsieg", "pinnacle")
        self.assertEqual(m["hw"], 2.00)

    def test_ohne_treffer_in_der_toleranz_lieber_nichts(self):
        """Ein „ungefaehr passender" Markt wuerde die Korrektur erfinden statt sie zu messen."""
        self.assertIsNone(R.einstiegs_markt(self.VERLAUF, 5.0, "Heimsieg", "public"))


class TestAmEchtenBestand(unittest.TestCase):
    """Der Test, der den Fund gemacht hat. An ausgedachten Zeilen waere jede Korrektur plausibel."""

    def setUp(self):
        import json
        self.hist = json.loads((WURZEL / "liga-odds-history.json").read_text(encoding="utf-8"))

    def test_der_overround_der_buecher_ist_wirklich_verschieden(self):
        ov = {}
        for _, snaps in self.hist.items():
            if not isinstance(snaps, list):
                continue
            for s in snaps:
                if not isinstance(s, dict):
                    continue
                q = [s.get("hw"), s.get("dr"), s.get("aw")]
                if not all(isinstance(x, (int, float)) and x > 1 for x in q):
                    continue
                ov.setdefault(str(s.get("bk")), []).append(1/q[0] + 1/q[1] + 1/q[2] - 1)
        self.assertIn("public", ov)
        self.assertIn("pinnacle", ov)
        m_soft = sum(ov["public"]) / len(ov["public"])
        m_pinn = sum(ov["pinnacle"]) / len(ov["pinnacle"])
        self.assertGreater(m_soft, m_pinn,
                           "wenn das kippt, ist die Begruendung dieses Fixes hinfaellig")
        self.assertGreater(m_soft - m_pinn, 0.01,
                           "der Margen-Unterschied ist der ganze Grund fuer den Bias")

    def test_die_korrektur_hebt_den_clv_an_und_zwar_spuerbar(self):
        import json
        rows = [r for r in json.loads((WURZEL / "liga_signal_ledger.json").read_text(encoding="utf-8"))["records"]
                if isinstance(r, dict)]
        paare = []
        for r in rows:
            if not isinstance(r.get("clvPP"), (int, float)):
                continue
            o = r.get("entryOdd")
            if not isinstance(o, (int, float)) or o <= 1:
                continue
            spiel = "-".join(str(r.get("matchKey") or "").split("-")[-2:])
            buch = "pinnacle" if str(r.get("entryBook")) == "pini" else "public"
            markt = R.einstiegs_markt(self.hist.get(spiel), o, r.get("market"), buch)
            fair = R.fair_entry_prob(markt, r.get("market"))
            if fair is None:
                continue
            pinn = r["clvPP"] / 100.0 + 1.0 / o
            paare.append((r["clvPP"], R.fair_clv_pp(pinn, fair)))
        self.assertGreaterEqual(len(paare), 50,
                                "die Abdeckung ist eingebrochen — mit 1X2 + Ueber/Unter + BTTS "
                                "waren es 63 von 87 Zeilen mit gemessenem CLV")
        d = sum(b - a for a, b in paare) / len(paare)
        self.assertGreater(d, 0.5, "die Korrektur hebt den CLV — sonst stimmt die Diagnose nicht")
        self.assertLess(d, 5.0, "eine Korrektur von mehr als 5 pp waere kein Vig mehr")


if __name__ == "__main__":
    unittest.main()


class TestDerLernstromLiestDieFaireZahl(unittest.TestCase):
    """Der Bayesian-Loop rechnet den CLV in eine „Markt-Zustimmung" ∈ [0,1] um; 0,500 ist der
    Nullpunkt. Mit der schiefen Zahl lag der Schnitt bei **0,358** — der Loop hat die
    `sharp_money`-Familie also gedrueckt. Entvigt sind es **0,596**.

    Der zweite Effekt ist der schlimmere: die Deadband (±0,5 pp). Bei einer Verschiebung um
    ~2 pp faellt ein Pick mit echtem CLV +2 auf null und fliegt als „Rauschen" raus, waehrend
    einer mit echtem CLV 0 bei −2 landet und als Beleg DAGEGEN zaehlt. Der Bias sortiert die
    guten Beobachtungen aus und behaelt die schlechten — gemessen 8 statt 3 Ausfaelle.
    """

    def setUp(self):
        import update_signal_weights as U
        self.U = U

    def test_ohne_faire_basis_gibt_es_keine_beobachtung(self):
        """Auf den rohen Wert zurueckzufallen waere die erfundene Beobachtung, vor der die
        Funktion in ihrer eigenen Docstring warnt."""
        self.assertIsNone(self.U._clv_outcome_score({"clvPP": -3.0}))
        self.assertIsNone(self.U._clv_outcome_score({"clvPP": -3.0, "clvBasis": "roh",
                                                    "clvFairPP": -1.0}))

    def test_mit_fairer_basis_wird_gelernt(self):
        s = self.U._clv_outcome_score({"clvBasis": "fair", "clvFairPP": 2.5, "clvPP": -1.0})
        self.assertIsNotNone(s)
        self.assertGreater(s, 0.5, "+2,5 pp ist Zustimmung, nicht Widerspruch")

    def test_die_deadband_gilt_auf_der_fairen_zahl(self):
        self.assertIsNone(self.U._clv_outcome_score({"clvBasis": "fair", "clvFairPP": 0.2}))

    def test_der_loop_liest_nicht_mehr_clvPP(self):
        quelle = (WURZEL / "update_signal_weights.py").read_text(encoding="utf-8")
        block = quelle[quelle.index("def _clv_outcome_score"):]
        block = block[:block.index("\ndef ")]
        block = "\n".join(z for z in block.split("\n") if not z.strip().startswith("#"))
        self.assertNotIn('pick.get("clvPP")', block,
                         "der Loop liest wieder die Zahl mit der eigenen Marge drin")
        self.assertIn('pick.get("clvFairPP")', block)


class TestNachtragLaeuftInDerPipeline(unittest.TestCase):
    """Bewusst keine einmalige Migration: der Nachtrag laeuft bei jedem `build_signal_ledger`,
    ist idempotent und holt Zeilen nach, deren Quotenverlauf erst spaeter ankommt. An einer
    Pipeline-Datei von Hand herumzuschreiben waere die schlechtere Loesung."""

    def test_der_nachtrag_ist_idempotent(self):
        import build_signal_ledger as B
        verlauf = {"65-63": [{"bk": "public", "hw": 2.00, "dr": 3.6, "aw": 3.9}]}
        rec = [{"matchKey": "ENG-1-65-63", "market": "Heimsieg", "entryOdd": 2.0,
                "entryBook": "soft", "clvPP": -2.0, "clvResolved": True}]
        self.assertEqual(B.fair_clv_nachtragen(rec, verlauf), 1)
        self.assertEqual(rec[0]["clvBasis"], "fair")
        self.assertEqual(B.fair_clv_nachtragen(rec, verlauf), 0, "zweiter Lauf darf nichts tun")

    def test_platzhalter_nullen_werden_nicht_nachgetragen(self):
        """`clvPP` wird mit 0.0 angelegt und erst gefuellt, wenn ein Closing da ist. Ohne
        `clvResolved` ist die 0.0 keine gemessene Null — dieselbe Unterscheidung, die der
        Ledger seit dem 03.09. trifft."""
        import build_signal_ledger as B
        verlauf = {"65-63": [{"bk": "public", "hw": 2.00, "dr": 3.6, "aw": 3.9}]}
        rec = [{"matchKey": "ENG-1-65-63", "market": "Heimsieg", "entryOdd": 2.0,
                "entryBook": "soft", "clvPP": 0.0, "clvResolved": False}]
        self.assertEqual(B.fair_clv_nachtragen(rec, verlauf), 0)
        self.assertNotIn("clvFairPP", rec[0])

    def test_ohne_zuordenbaren_markt_bleibt_es_roh(self):
        import build_signal_ledger as B
        rec = [{"matchKey": "ENG-1-99-98", "market": "Heimsieg", "entryOdd": 2.0,
                "entryBook": "soft", "clvPP": -2.0, "clvResolved": True}]
        self.assertEqual(B.fair_clv_nachtragen(rec, {}), 0)
        self.assertEqual(rec[0]["clvBasis"], "roh")
        self.assertNotIn("clvFairPP", rec[0])
