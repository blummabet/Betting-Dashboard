# tests/test_team_match.py — toleranter Betfair-Namensabgleich (15.08.2026, Lucas).
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import team_match as T


class TestTeamsMatch(unittest.TestCase):
    def test_suffix_fc_sc_cf(self):
        self.assertTrue(T.teams_match("Charlotte", "Charlotte FC"))
        self.assertTrue(T.teams_match("Orlando City", "Orlando City SC"))
        self.assertTrue(T.teams_match("Inter Miami", "Inter Miami CF"))

    def test_utd_united(self):
        self.assertTrue(T.teams_match("Atlanta Utd", "Atlanta United FC"))
        self.assertTrue(T.teams_match("DC United", "DC Utd"))
        self.assertTrue(T.teams_match("Minnesota United FC", "Minnesota Utd"))

    def test_city_suffix_wegfall(self):
        self.assertTrue(T.teams_match("Deportivo La Coruna", "Deportivo"))
        self.assertTrue(T.teams_match("Columbus Crew", "Columbus"))
        self.assertTrue(T.teams_match("San Diego", "San Diego FC"))

    def test_keine_fehltreffer(self):
        # verschiedene Teams duerfen NICHT matchen
        self.assertFalse(T.teams_match("Manchester United", "Manchester City"))
        self.assertFalse(T.teams_match("Real Madrid", "Atletico Madrid"))
        self.assertFalse(T.teams_match("AC Milan", "Inter Milan"))   # Derby: 'milan' geteilt, aber ac/inter unterscheiden
        self.assertFalse(T.teams_match("Sevilla", "Real Betis"))

    def test_leer(self):
        self.assertFalse(T.teams_match("", "Getafe"))
        self.assertFalse(T.teams_match("FC", "SC"))   # nur Suffixe -> leer -> nie


class TestFindMatch(unittest.TestCase):
    def _idx(self):
        return [
            ("Deportivo", "Elche", {"vol": 15499}),
            ("Atlanta Utd", "New York Red Bulls", {"vol": 9273}),
            ("Alaves", "Getafe", {"vol": 41931}),
            ("Inter Milan", "Napoli", {"vol": 5000}),
            ("AC Milan", "Roma", {"vol": 6000}),
        ]

    def test_exakt(self):
        self.assertEqual(T.find_match(self._idx(), "Alaves", "Getafe")["vol"], 41931)

    def test_teilmenge_deportivo(self):
        self.assertEqual(T.find_match(self._idx(), "Deportivo La Coruna", "Elche")["vol"], 15499)

    def test_utd_und_reihenfolge_egal(self):
        # gedrehte Heim/Auswaerts + Utd->United
        self.assertEqual(T.find_match(self._idx(), "New York Red Bulls", "Atlanta United FC")["vol"], 9273)

    def test_derby_kein_falschtreffer(self):
        # "AC Milan v Napoli" darf NICHT das "Inter Milan v Napoli"-Spiel ziehen
        m = T.find_match(self._idx(), "AC Milan", "Napoli")
        self.assertIsNone(m)   # kein exaktes AC-Milan-v-Napoli im Index -> lieber None als Inter-Spiel

    def test_kein_match(self):
        self.assertIsNone(T.find_match(self._idx(), "Barcelona", "Villarreal"))
        self.assertIsNone(T.find_match([], "A", "B"))


if __name__ == "__main__":
    unittest.main()
