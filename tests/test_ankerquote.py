"""🔴 20.09.2026 — „0 von 25 Konsens-Spielen mit Odds-Anker — the-odds-api-Key tot?"

Die Störungsmeldung brachte diesen Befund als Erstes hoch. Nachgemessen sind es zwei Fehler,
die zusammen wie ein dritter aussahen:

1. **Der Nenner war falsch.** Von 113 offenen Spielen liegen 101 in Ligen, die in
   `LEAGUE_ODDS_KEY` gar nicht gemappt sind — Salvadoran Primera, Jamaican Premier, Serbian
   First League, Italian Serie C. Die können nie einen Anker bekommen. Die `ankerQuote` stand
   damit dauerhaft bei 0,0 % und sagte nichts. Der richtige Nenner sind die 12 ankerbaren.
   Am 02.09. wurde dieser Nenner schon einmal repariert — von `games` (auf 15.000 EUR
   gefiltert) auf ALLE offenen Spiele. Er wurde dabei zu weit aufgemacht.
   Fehlerklasse: ein Prozentsatz ohne seinen Nenner — an diesem Tag zum zweiten Mal.

2. **Der Wächter nannte zwei Verdächtige und schloss keinen aus.** „Key tot ODER Namens-Match
   gebrochen" — während `oddsKeysFetched: 40` im selben Artefakt steht und den ersten
   widerlegt. Fehlerklasse: ein Befund, der seine eigene Unterscheidung nicht trifft, obwohl
   die Zahl daneben steht.

Was bleibt: 0 von 12 ankerbaren Spielen hatten einen Anker. Klein, aber echt.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import betfair_data_integrity as BI


class _Ctx:
    def __init__(self, consensus):
        self.consensus = consensus


def _spiel(league, pinn=None):
    return {"league": league, "pinn": pinn, "verdict": "no_anchor" if pinn is None else "ok"}


class TestDerWaechterSchliesstEinenVerdaechtigenAus(unittest.TestCase):
    GEMAPPT = "Argentinian Primera Division"

    def _ctx(self, geholt, n=12, spiele=6):
        return _Ctx({"games": [_spiel(self.GEMAPPT) for _ in range(spiele)],
                     "covered": 0, "oddsKeysFetched": geholt, "ankerN": n})

    def test_geholte_keys_entlasten_den_key(self):
        c = BI.check_consensus_anchor_coverage(self._ctx(40))
        t = " ".join(c["failures"])
        self.assertIn("der Key lebt", t)
        self.assertIn("40", t)
        self.assertIn("Namens-Matching", t)

    def test_null_geholte_keys_belasten_ihn(self):
        t = " ".join(BI.check_consensus_anchor_coverage(self._ctx(0))["failures"])
        self.assertIn("Kontingent", t)
        self.assertNotIn("der Key lebt", t)

    def test_ohne_die_zahl_behauptet_er_keine_ursache(self):
        """„Fehlende Information rendert als harmloser Default" — hier waere der harmlose
        Default eine Schuldzuweisung."""
        t = " ".join(BI.check_consensus_anchor_coverage(self._ctx(None))["failures"])
        self.assertIn("laesst sich hier nicht sagen", t)
        self.assertNotIn("der Key lebt", t)

    def test_er_nennt_den_ankerbaren_nenner_nicht_alle_spiele(self):
        t = " ".join(BI.check_consensus_anchor_coverage(self._ctx(40, n=12))["failures"])
        self.assertIn("0 von 12", t)
        self.assertIn("ankerbaren", t)

    def test_mit_anker_schweigt_er(self):
        c = BI.check_consensus_anchor_coverage(
            _Ctx({"games": [_spiel(self.GEMAPPT, pinn=1.9) for _ in range(6)],
                  "covered": 3, "oddsKeysFetched": 40, "ankerN": 6}))
        self.assertEqual(c["nFail"], 0)

    def test_zu_wenige_ankerbare_spiele_geben_kein_urteil(self):
        """Ein Punktschaetzer entscheidet nichts: unter COVER_MIN_N wird nicht gemeldet."""
        c = BI.check_consensus_anchor_coverage(
            _Ctx({"games": [_spiel(self.GEMAPPT)], "covered": 0,
                  "oddsKeysFetched": 40, "ankerN": 1}))
        self.assertEqual(c["nFail"], 0)

    def test_nicht_gemappte_ligen_loesen_nichts_aus(self):
        """Salvadoran Primera kann nie einen Anker haben — sechs davon sind kein Befund."""
        c = BI.check_consensus_anchor_coverage(
            _Ctx({"games": [_spiel("Salvadoran Primera Division") for _ in range(6)],
                  "covered": 0, "oddsKeysFetched": 40, "ankerN": 0}))
        self.assertEqual(c["nFail"], 0)


class TestDieQuoteRechnetUeberAnkerbareSpiele(unittest.TestCase):
    def test_der_produzent_filtert_auf_gemappte_ligen(self):
        """Quelltext-Pruefung, weil hier die VERDRAHTUNG das Thema ist: die Quote muss ueber
        `LEAGUE_ODDS_KEY` gefiltert werden, nicht ueber alle offenen Spiele."""
        q = (Path(__file__).resolve().parents[1] / "betfair_consensus.py").read_text(
            encoding="utf-8")
        i = q.index('out["ankerQuote"]')
        block = q[i - 1500:i + 300]
        self.assertIn("_n_ankerbar", block)
        self.assertIn("LEAGUE_ODDS_KEY.get(", block)
        self.assertNotIn('out["ankerQuote"] = round(_mit_pinn / _n_ges', block)

    def test_die_grosse_zahl_bleibt_daneben_stehen(self):
        """Der ankerbare Ausschnitt ist klein (12 von 113). Wer nur die Quote sieht, haelt sie
        fuer eine Aussage ueber den ganzen Feed."""
        q = (Path(__file__).resolve().parents[1] / "betfair_consensus.py").read_text(
            encoding="utf-8")
        self.assertIn('out["ankerNOffen"]', q)

    def test_am_echten_bestand_stimmt_der_nenner(self):
        import json
        p = Path(__file__).resolve().parents[1] / "betfair_consensus.json"
        if not p.exists():
            self.skipTest("kein Konsens-Artefakt")
        d = json.loads(p.read_text(encoding="utf-8"))
        n, offen = d.get("ankerN"), d.get("ankerNOffen")
        if offen is None:
            self.skipTest("Artefakt stammt noch aus einem Lauf vor dem Umbau")
        self.assertLessEqual(n, offen, "ankerbar kann nie mehr sein als offen")


if __name__ == "__main__":
    unittest.main()
