#!/usr/bin/env python3
"""
tests/test_messungen.py — 15.09.2026: das Buch der laufenden Messungen.

Lucas' Frage war „wo sehen wir den Outcome dieser Messungen?". Die teuerste Antwort waere ein
Buch, das Fortschritt behauptet, wo nichts zaehlt — dann sieht man in zwei Wochen einen gruenen
Balken statt der Wahrheit. Jede Schranke hier wird deshalb provoziert.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import messungen as M


def _e(**kw):
    e = {"id": "x", "titel": "T", "frage": "F", "gestartet": "2026-09-01",
         "faellig": "2026-09-29", "messer": "htk_shortlist", "mindestN": 60,
         "entscheidung": None}
    e.update(kw)
    return e


class Zustand(unittest.TestCase):
    def test_sammelt_vor_dem_termin(self):
        z, t = M.zustand(_e(), 14, "2026-09-15")
        self.assertEqual(z, "sammelt")
        self.assertIn("14 von 60", t)
        self.assertIn("14 Tag", t)

    def test_menge_erreicht_aber_termin_noch_nicht(self):
        self.assertEqual(M.zustand(_e(), 60, "2026-09-15")[0], "bereit")

    def test_termin_und_menge_da_heisst_faellig(self):
        self.assertEqual(M.zustand(_e(), 60, "2026-09-29")[0], "faellig")

    def test_termin_ohne_menge_ist_ueberfaellig_und_sagt_es(self):
        # 🔴 DIE wichtigste Schranke. Ohne sie verschwindet eine Messung, die nie genug Daten
        # bekam, genauso lautlos wie frueher ein unaufloesbarer Play — und niemand erfaehrt,
        # dass die Frage NIE beantwortet wurde.
        z, t = M.zustand(_e(), 14, "2026-10-01")
        self.assertEqual(z, "ueberfaellig")
        self.assertIn("NICHT beantwortet", t)

    def test_messung_ohne_eingebauten_zaehler_behauptet_keinen_fortschritt(self):
        # PROVOKATION: „0 von 60 · sammelt" saehe aus wie „faengt gerade an". In Wahrheit
        # zaehlt niemand — das ist eine Luege in Gruen.
        z, t = M.zustand(_e(messer="gibt_es_nicht"), None, "2026-09-15")
        self.assertEqual(z, "wartet auf Einbau")
        self.assertIn("gibt es noch nicht", t)

    def test_kaputte_quelle_ist_nicht_null_beobachtungen(self):
        z, t = M.zustand(_e(), None, "2026-09-15")
        self.assertEqual(z, "quelle unlesbar")
        self.assertNotIn("0 von", t)

    def test_entscheidung_schliesst_den_eintrag_unabhaengig_vom_zaehler(self):
        z, t = M.zustand(_e(entscheidung="conv>=7 ab 30.09."), 0, "2026-10-30")
        self.assertEqual(z, "entschieden")
        self.assertIn("conv>=7", t)

    def test_offene_entscheidung_hat_nur_einen_termin(self):
        e = _e(messer=None, mindestN=None)
        self.assertEqual(M.zustand(e, None, "2026-09-15")[0], "sammelt")
        self.assertEqual(M.zustand(e, None, "2026-09-29")[0], "faellig")
        self.assertIn("seit 2 Tagen", M.zustand(e, None, "2026-10-01")[1])

    def test_unlesbarer_termin_wirft_nicht(self):
        self.assertTrue(M.zustand(_e(faellig="irgendwann"), 10, "2026-09-15")[0])

    def test_muell_eintrag_wirft_nicht(self):
        self.assertEqual(M.zustand(None, 0, "2026-09-15")[0], "quelle unlesbar")


class Fortschritt(unittest.TestCase):
    def test_anteil_wird_gedeckelt(self):
        self.assertAlmostEqual(M.fortschritt(30, 60), 0.5)
        self.assertEqual(M.fortschritt(90, 60), 1.0)
        self.assertEqual(M.fortschritt(-5, 60), 0.0)

    def test_ohne_mindestmenge_gibt_es_keinen_balken(self):
        # PROVOKATION: ein Balken ohne Bezugsgroesse zeigt irgendetwas an — und irgendetwas
        # ist auf einer Flaeche, der man glauben soll, schlimmer als nichts.
        self.assertIsNone(M.fortschritt(10, None))
        self.assertIsNone(M.fortschritt(10, 0))
        self.assertIsNone(M.fortschritt(None, 60))


class Buch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _schreib(self, name, obj):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def test_handlungsbedarf_steht_oben(self):
        # PROVOKATION: sortierte das Buch nur nach Termin, stuende der Eintrag, bei dem gar
        # nichts zaehlt, GANZ UNTEN — weil sein Termin am weitesten weg ist. Genau der gehoert
        # aber nach oben: er sammelt nicht, er wartet auf Einbau.
        reg = {"messungen": [
            _e(id="sammelt-bald", messer=None, mindestN=None, faellig="2026-09-20"),
            _e(id="zaehlt-gar-nicht", messer="gibt_es_nicht", faellig="2026-12-01"),
        ]}
        b = M.buch(reg, self.dir, heute="2026-09-15")
        self.assertEqual([z["id"] for z in b["messungen"]],
                         ["zaehlt-gar-nicht", "sammelt-bald"])
        self.assertEqual(b["nHandlung"], 1)

    def test_bei_gleichem_rang_entscheidet_der_termin(self):
        reg = {"messungen": [
            _e(id="spaet", messer=None, mindestN=None, faellig="2026-11-01"),
            _e(id="frueh", messer=None, mindestN=None, faellig="2026-09-20"),
        ]}
        b = M.buch(reg, self.dir, heute="2026-09-15")
        self.assertEqual([z["id"] for z in b["messungen"]], ["frueh", "spaet"])

    def test_zaehler_wird_wirklich_ausgefuehrt(self):
        self._schreib("poly_shortlist_track.json",
                      {"settled": [{"htkAtEntry": 3.0}, {"htkAtEntry": 0.5}, {"x": 1}]})
        b = M.buch({"messungen": [_e()]}, self.dir, heute="2026-09-15")
        self.assertEqual(b["messungen"][0]["standN"], 2)

    def test_werfender_zaehler_kippt_das_buch_nicht(self):
        echt = M.ZAEHLER["htk_shortlist"]
        M.ZAEHLER["htk_shortlist"] = lambda d: (_ for _ in ()).throw(RuntimeError("peng"))
        try:
            b = M.buch({"messungen": [_e()]}, self.dir, heute="2026-09-15")
        finally:
            M.ZAEHLER["htk_shortlist"] = echt
        self.assertEqual(b["messungen"][0]["zustand"], "quelle unlesbar")

    def test_entschiedene_zaehlen_nicht_als_offen(self):
        b = M.buch({"messungen": [_e(entscheidung="fertig")]}, self.dir, heute="2026-09-15")
        self.assertEqual(b["nOffen"], 0)
        self.assertEqual(b["n"], 1)

    def test_muell_register_gibt_ein_leeres_buch(self):
        for r in (None, "nein", 42, {"messungen": "kaputt"}, {"messungen": [None, 7]}):
            self.assertEqual(M.buch(r, self.dir, heute="2026-09-15")["n"], 0)


class Zaehler(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _schreib(self, name, obj):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def test_fehlende_datei_ist_unbekannt_nicht_null(self):
        # PROVOKATION: gaebe die fehlende Datei 0 zurueck, zeigte das Board „0 von 25 · sammelt"
        # fuer eine Messung, deren Quelle gar nicht existiert.
        self.assertIsNone(M.zaehler_htk_shortlist(self.dir))
        self.assertIsNone(M.zaehler_echte_fills(self.dir))

    def test_kaputte_wettdatei_ist_unbekannt(self):
        with open(os.path.join(self.dir, "shortlist_auto_bets_placed.json"), "w") as f:
            f.write("{kaputt")
        self.assertIsNone(M.zaehler_echte_fills(self.dir))

    def test_eine_kaputte_datei_macht_den_ganzen_stand_unbekannt(self):
        # PROVOKATION: ueberspraenge der Zaehler die kaputte Datei einfach, meldete er die
        # Zahl der LESBAREN als Stand — ein Fortschritt, der in Wahrheit unvollstaendig ist.
        # Bei einer Messung, an der eine Entscheidung haengt, ist das die teuerste Sorte Zahl.
        self._schreib("liga_auto_bets_placed.json", {"bets": [{"htkAtEntry": 30}]})
        with open(os.path.join(self.dir, "wm_auto_bets_placed.json"), "w") as f:
            f.write("{kaputt")
        self.assertIsNone(M.zaehler_htk_trader(self.dir))

    def test_echte_fills_zaehlt_nur_gemessene(self):
        self._schreib("shortlist_auto_bets_placed.json", {"bets": [
            {"clvPP": 2.5}, {"clvPP": -1.0}, {"status": "placed"}]})
        self.assertEqual(M.zaehler_echte_fills(self.dir), 2)

    def test_trader_zaehler_ignoriert_die_shortlist(self):
        # Die beiden Fragen sind getrennt — der Shortlist-Auto-Play ist nicht der Pinnacle-Trader.
        self._schreib("shortlist_auto_bets_placed.json", {"bets": [{"htkAtEntry": 5}]})
        self._schreib("liga_auto_bets_placed.json", {"bets": [{"htkAtEntry": 30}]})
        self.assertEqual(M.zaehler_htk_trader(self.dir), 1)


class RegisterImRepo(unittest.TestCase):
    """Das echte Register muss lesbar sein und mit dem Code zusammenpassen."""

    def setUp(self):
        with open(os.path.join(str(M.BASE), M.REGISTER_FILE), encoding="utf-8") as f:
            self.reg = json.load(f)

    def test_jeder_messer_existiert(self):
        for e in self.reg["messungen"]:
            if e.get("messer"):
                self.assertIn(e["messer"], M.ZAEHLER,
                              "Register nennt einen Zaehler, den es nicht gibt: %s" % e["messer"])

    def test_jeder_eintrag_hat_frage_termin_und_grund(self):
        for e in self.reg["messungen"]:
            for feld in ("id", "titel", "frage", "warum", "gestartet", "faellig", "quelle"):
                self.assertTrue(e.get(feld), "%s fehlt %s" % (e.get("id"), feld))

    def test_ids_sind_eindeutig(self):
        ids = [e["id"] for e in self.reg["messungen"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_die_fuenf_offenen_fragen_stehen_drin(self):
        # Der ganze Zweck des Buches: sie leben nicht mehr nur im Gespraechsprotokoll.
        ids = {e["id"] for e in self.reg["messungen"]}
        for noetig in ("horizont-shortlist", "horizont-trader", "echte-fills",
                       "devig-proportional-vs-power", "serie-a-btts-schublade",
                       "sharp-radar-drift-pushes", "einigkeit-statt-geld"):
            self.assertIn(noetig, ids)


class TestDieEinigkeitsMessungWirdAuchGefuellt(unittest.TestCase):
    """18.09.2026 (Lucas: „hau das auch in den Menuepunkt Messung, damit wir das wo haben und ich
    schauen kann und wir das nicht vergessen").

    Eine eingetragene Messung, die niemand fuellt, ist schlimmer als keine: sie steht sechs
    Wochen auf „0 von 40" und sieht dabei aus, als liefe sie. Genau das waere hier passiert —
    das Schattenbuch wurde geschrieben, aber von niemandem abgerechnet.
    """

    def test_der_zaehler_zaehlt_nur_abgerechnete_zeilen(self):
        """Offene Kandidaten sind keine Beobachtungen. Wer sie mitzaehlt, meldet „40 von 40
        erreicht", ohne einen einzigen Ausgang gesehen zu haben."""
        import json, tempfile, os
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "poly_einigkeit_schatten.json"), "w") as f:
                json.dump([{"k": "a", "status": "settled"}, {"k": "b", "status": "pending"},
                           {"k": "c", "status": "settled"}, {"k": "d"}], f)
            self.assertEqual(M.zaehler_einigkeit_schatten(d), 2)

    def test_ohne_buch_ist_es_null_und_nicht_unbekannt(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(M.zaehler_einigkeit_schatten(d), 0)

    def test_das_schattenbuch_wird_wirklich_abgerechnet(self):
        """Der Test, der den stillen Ausfall verhindert: `poly_public_eval` muss das Buch
        anfassen. Ohne ihn haette die Messung bis zum Faelligkeitstag bei null gestanden, und
        erst dann waere aufgefallen, dass nie jemand gesettelt hat."""
        import os
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        quelle = open(os.path.join(wurzel, "poly_public_eval.py"), encoding="utf-8").read()
        self.assertIn("poly_einigkeit_schatten.json", quelle)
        self.assertIn("SCHATTEN_LEDGER_FILE", quelle)
        stelle = quelle.index("SCHATTEN_LEDGER_FILE, []")
        self.assertIn("settle(", quelle[stelle:stelle + 400])

    def test_die_quelle_im_register_zeigt_auf_das_buch(self):
        e = [x for x in self.reg["messungen"] if x["id"] == "einigkeit-statt-geld"][0]
        self.assertIn("poly_einigkeit_schatten.json", e["quelle"])
        self.assertEqual(e["messer"], "einigkeit_schatten")
        self.assertIn(e["messer"], M.ZAEHLER)

    def setUp(self):
        import json, os
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.reg = json.loads(open(os.path.join(wurzel, "messungen_register.json"),
                                   encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
