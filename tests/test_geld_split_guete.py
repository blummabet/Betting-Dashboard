#!/usr/bin/env python3
"""02.09.2026 — Lucas: „kannst du mal die inhalte hier checken bei 'Großes Geld' und 'Bewegung'
ob das vernünftig implementiert oder man da mehr rausholen kann".

Der Audit ergab, dass der Geld-Split zwei verschiedene Dinge war, und keines davon das, was
oben drueber stand. Gemessen ueber 1.912 Maerkte aus poly_money_broad_close.json:

  · ZWEI Ausgaenge (n=1.262): |Geld% − Preis| Median 0,0pp, 1262 von 1262 unter 1pp. Struktur:
    komplementaere Tokens -> Wert-Anteil = p/(1−p). Der Split IST der Preis.
  · DREI Ausgaenge (n=650): Splits, die kein Preis hergibt — Osasuna 44,5¢ mit $745.597 gegen
    Getafe 22,5¢ mit $13.006. /holders lieferte genau EINE Seite je Ausgang, und niemand schrieb
    mit, ob das alle waren.

⚠️ Der erste Anlauf mass die Guete als sum(shares)/totalUsd und nannte das Abdeckung. `totalUsd`
ist aber das gehandelte VOLUMEN (kumulierter Umsatz), nicht die offene Position — die Zahl haette
plausibel ausgesehen und nichts gemessen. Geprueft wird jetzt, was der Abruf wirklich weiss: ob
seine Halter-Liste zu Ende war.

Diese Tests nageln fest, dass die Anzeige das sagt, statt eine Seite zu behaupten. Sie sind
bewusst hart bei der einen Frage, um die es hier geht: darf aus fehlender Information eine
Aussage werden? Nein.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poly_money_accuracy as PMA
import poly_money_broad as PMB


class SplitGueteTest(unittest.TestCase):
    def test_zwei_ausgaenge_sind_preis_echo(self):
        g = PMA.split_guete({"A": 60.0, "B": 40.0}, 100)
        self.assertEqual(g["art"], "preis_echo")

    def test_zwei_ausgaenge_bleiben_preis_echo_egal_wie_gut_erfasst(self):
        """Auch bei 100% Abdeckung sagt ein Zwei-Wege-Split nichts Eigenes — er ist der Preis."""
        self.assertEqual(PMA.split_guete({"A": 60.0, "B": 40.0}, 100)["art"], "preis_echo")

    def test_drei_ausgaenge_mit_vollstaendiger_halterliste_sind_belastbar(self):
        g = PMA.split_guete({"A": 60.0, "B": 20.0, "C": 5.0}, 100, False)
        self.assertEqual(g["art"], "belastbar")

    def test_abgeschnittene_halterliste_ist_nicht_belastbar(self):
        """Der Osasuna-Fall: 96,6% angeblich auf einer Seite bei 44,5¢, Liste nicht zu Ende."""
        g = PMA.split_guete({"Osasuna": 745597.0, "Draw": 13100.0, "Getafe": 13006.0},
                            1796655, True)
        self.assertEqual(g["art"], "abgeschnitten")

    def test_ohne_trunc_angabe_bleibt_es_unbekannt_nicht_belastbar(self):
        """Alt-Bestand: erfasst, bevor der Abruf die Vollstaendigkeit mitschrieb."""
        g = PMA.split_guete({"A": 60.0, "B": 20.0, "C": 5.0}, 100, None)
        self.assertEqual(g["art"], "unbekannt")

    def test_das_volumen_entscheidet_NICHT_mehr_ueber_die_guete(self):
        """Die Kernkorrektur: derselbe Split mit voellig anderem Umsatz ist dieselbe Guete.
        Frueher haette ein umsatzstarker Markt allein deswegen als „duenn" gegolten."""
        sh = {"A": 60.0, "B": 20.0, "C": 5.0}
        for tot in (100, 1_000_000, 0, None):
            self.assertEqual(PMA.split_guete(sh, tot, False)["art"], "belastbar", f"tot={tot}")
            self.assertEqual(PMA.split_guete(sh, tot, True)["art"], "abgeschnitten", f"tot={tot}")

    def test_normalisierte_anteile_bleiben_belastbar(self):
        """capture() friert fertige Anteile ein (Summe 1) — die sind per Konstruktion vollstaendig."""
        g = PMA.split_guete({"home": 0.6, "draw": 0.2, "away": 0.2}, 40000)
        self.assertEqual(g["art"], "belastbar")

    def test_leerer_oder_einseitiger_split(self):
        self.assertEqual(PMA.split_guete({}, 100)["art"], "leer")
        self.assertEqual(PMA.split_guete({"A": 5.0}, 100)["art"], "leer")
        self.assertEqual(PMA.split_guete({"A": 0.0, "B": 0.0}, 100)["art"], "leer")

    def test_nicht_numerische_werte_fliegen_raus(self):
        self.assertEqual(PMA.split_guete({"A": "viel", "B": 5.0}, 100)["art"], "leer")


class HolderBlaetternTest(unittest.TestCase):
    """02.09.2026: /holders liefert seitenweise. Der Abruf holte genau EINE Seite und wusste nicht,
    ob das alle waren. Hier ist festgenagelt, wann das Blaettern „fertig" sagen darf — und wann
    es zugeben muss, dass es abgeschnitten hat."""

    @staticmethod
    def _parse(d, _t):
        return d

    def _seiten(self, seitenfolge):
        """Gibt eine http_get-Attrappe zurueck, die die vorgegebenen Seiten liefert."""
        def get(url):
            off = int(url.split("offset=")[1])
            idx = off // PMB.HOLDERS_LIMIT
            return seitenfolge[idx] if idx < len(seitenfolge) else []
        return get

    def test_kurze_seite_heisst_vollstaendig(self):
        rows, trunc = PMB._alle_holder("c", "t", self._seiten([[("w%d" % i, 1.0) for i in range(50)]]),
                                       self._parse)
        self.assertEqual(len(rows), 50)
        self.assertFalse(trunc)

    def test_es_wird_geblaettert_bis_die_seite_kurz_ist(self):
        L = PMB.HOLDERS_LIMIT
        seiten = [[("p%d" % (s * L + i), 1.0) for i in range(L)] for s in range(2)]
        seiten.append([("rest%d" % i, 1.0) for i in range(10)])
        rows, trunc = PMB._alle_holder("c", "t", self._seiten(seiten), self._parse)
        self.assertEqual(len(rows), 2 * L + 10)
        self.assertFalse(trunc)

    def test_ignoriertes_offset_wird_erkannt_und_gemeldet(self):
        """Liefert die API immer dieselbe Seite, ist mehr ueber diesen Weg nicht zu holen —
        aber dann ist der Split abgeschnitten und darf nicht als vollstaendig gelten."""
        L = PMB.HOLDERS_LIMIT
        gleiche = [("same%d" % i, 1.0) for i in range(L)]
        rows, trunc = PMB._alle_holder("c", "t", lambda u: gleiche, self._parse)
        self.assertEqual(len(rows), L)
        self.assertTrue(trunc)

    def test_leerer_abruf_ist_nicht_null_halter_sondern_unbekannt(self):
        rows, trunc = PMB._alle_holder("c", "t", lambda u: None, self._parse)
        self.assertEqual(rows, [])
        self.assertTrue(trunc)

    def test_am_seiten_deckel_wird_abgeschnitten_gemeldet(self):
        L = PMB.HOLDERS_LIMIT
        def get(url):
            off = int(url.split("offset=")[1])
            return [("q%d" % (off + i), 1.0) for i in range(L)]
        rows, trunc = PMB._alle_holder("c", "t", get, self._parse)
        self.assertEqual(len(rows), PMB.HOLDERS_MAX_SEITEN * L)
        self.assertTrue(trunc)

    def test_die_url_traegt_ein_offset(self):
        self.assertIn("offset=", PMB.HOLDERS)
        self.assertIn("limit=%d" % PMB.HOLDERS_LIMIT, PMB.HOLDERS)


class SplitQuelleTest(unittest.TestCase):
    def test_broad_reicht_dieselbe_funktion_durch(self):
        """Eine Quelle für die Güte — sonst driften Producer und Auswertung auseinander."""
        self.assertIs(PMB.split_guete, PMA.split_guete)


class EvaluateGattertTest(unittest.TestCase):
    """Der Rückblick darf nur über Märkte urteilen, deren Split etwas anderes sagen KANN
    als der Preis. Vorher stand ein „🔴 faden" über 848 Spielen, von denen fast keines
    auswertbar war."""

    def _frozen(self, n_belastbar=0, n_echo=0, n_duenn=0):
        f, res = {}, {}
        for i in range(n_belastbar):
            k = "bel%d" % i
            f[k] = {"shares": {"H": 80.0, "D": 10.0, "A": 5.0}, "totalUsd": 100,
                    "prices": {"H": 0.5, "D": 0.3, "A": 0.2}, "league": "TESTLIGA",
                    "splitGuete": {"art": "belastbar", "trunc": False}}
            res[k] = "H"
        for i in range(n_echo):
            k = "echo%d" % i
            f[k] = {"shares": {"H": 60.0, "A": 40.0}, "totalUsd": 100,
                    "prices": {"H": 0.6, "A": 0.4}, "league": "TESTLIGA"}
            res[k] = "H"
        for i in range(n_duenn):
            k = "dnn%d" % i
            f[k] = {"shares": {"H": 20.0, "D": 1.0, "A": 1.0}, "totalUsd": 100,
                    "prices": {"H": 0.5, "D": 0.3, "A": 0.2}, "league": "TESTLIGA",
                    "splitGuete": {"art": "abgeschnitten", "trunc": True}}
            res[k] = "H"
        return f, res

    def test_preis_echo_und_duenne_zaehlen_nicht_mit(self):
        f, res = self._frozen(n_belastbar=2, n_echo=5, n_duenn=7)
        rep = PMA.evaluate(f, res, min_odds=1.35)
        self.assertEqual(rep["n"], 2)
        self.assertEqual(rep["guete"]["preis_echo"], 5)
        self.assertEqual(rep["guete"]["abgeschnitten"], 7)
        self.assertEqual(rep["guete"]["belastbar"], 2)

    def test_unter_der_mindeststichprobe_gibt_es_kein_urteil(self):
        f, res = self._frozen(n_belastbar=PMA.URTEIL_MIN_N - 1)
        rep = PMA.evaluate(f, res, min_odds=1.35)
        self.assertEqual(rep["verdict"], "zu wenig Daten")

    def test_ab_der_mindeststichprobe_gibt_es_eines(self):
        f, res = self._frozen(n_belastbar=PMA.URTEIL_MIN_N)
        rep = PMA.evaluate(f, res, min_odds=1.35)
        self.assertNotEqual(rep["verdict"], "zu wenig Daten")

    def test_liga_urteil_erst_ab_eigener_mindeststichprobe(self):
        f, res = self._frozen(n_belastbar=PMA.URTEIL_MIN_N_LIGA - 1)
        rep = PMA.evaluate(f, res, min_odds=1.35)
        self.assertEqual(rep["byLeague"], [])

    def test_guete_steht_auch_bei_null_gewerteten_maerkten_da(self):
        f, res = self._frozen(n_echo=4)
        rep = PMA.evaluate(f, res, min_odds=1.35)
        self.assertEqual(rep["n"], 0)
        self.assertEqual(rep["guete"]["preis_echo"], 4)


class LigaAusSlugTest(unittest.TestCase):
    """`SOCCER` war mit 39% der groesste Eimer der Liga-Tabelle und trug keinen Liganamen.
    Die Zuordnung wird aus den eigenen Daten gelernt, nicht geraten."""

    def test_spezifisches_label_bleibt_unangetastet(self):
        self.assertEqual(PMA.liga_label("lal-a-b-2026-01-01", "EPL", {"lal": "LA-LIGA"}), "EPL")

    def test_generisches_label_wird_ueber_den_praefix_aufgeloest(self):
        self.assertEqual(PMA.liga_label("lal-osa-get-2026-08-31", "SOCCER", {"lal": "LA-LIGA"}), "LA-LIGA")

    def test_unbekannter_praefix_bleibt_getrennt_aber_unbenannt(self):
        self.assertEqual(PMA.liga_label("mex-a-b-2026-01-01", "SOCCER", {}), "SOCCER:MEX")

    def test_gelernt_wird_erst_ab_genug_belegen(self):
        self.assertEqual(PMA.liga_lernen([("col-a", "UECL")] * (PMA.LIGA_MIN_BELEGE - 1)), {})
        self.assertEqual(PMA.liga_lernen([("col-a", "UECL")] * PMA.LIGA_MIN_BELEGE), {"col": "UECL"})

    def test_uneindeutiger_praefix_wird_nicht_gelernt(self):
        eintraege = [("col-a", "UECL")] * 3 + [("col-b", "COLOMBIA")] * 3
        self.assertEqual(PMA.liga_lernen(eintraege), {})

    def test_generische_labels_lehren_nichts(self):
        self.assertEqual(PMA.liga_lernen([("lal-a", "SOCCER")] * 9), {})

    def test_evaluate_loest_soccer_auf(self):
        f = {"lal-x-2026-01-01": {"shares": {"H": 80.0, "D": 10.0, "A": 5.0}, "totalUsd": 100,
                                  "prices": {"H": 0.5, "D": 0.3, "A": 0.2}, "league": "SOCCER",
                                  "splitGuete": {"art": "belastbar", "trunc": False}}}
        for i in range(PMA.LIGA_MIN_BELEGE):
            f["lal-lehr%d-2026-01-01" % i] = {"shares": {"H": 1.0, "A": 1.0}, "totalUsd": 100,
                                              "prices": {"H": 0.5, "A": 0.5}, "league": "LA-LIGA"}
        res = {k: "H" for k in f}
        rep = PMA.evaluate(f, res, min_odds=1.35)
        self.assertEqual([r["league"] for r in rep["rows"]], ["LA-LIGA"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
