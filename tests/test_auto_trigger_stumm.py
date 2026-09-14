"""🔴 14.09.2026 (Lucas: „dieses Auto Trading, wo wir die Differenz zwischen Pinnacle-Quoten und
Polymarket spielen, das funktioniert ja nicht mal ansatzweise. Da passiert ja gar nix … man muss
definitiv was falsch sein und das nervt.")

## Was gemessen war

Der Trigger fand an diesem Tag in EINEM Lauf **vier** handelbare Edges (4,7–7,7 pp), platzierte
null — und sagte kein Wort. Er läuft alle 30 Minuten zwischen 10 und 21 Uhr UTC, seit dem 30.08.
also rund 350 Mal ins Leere.

## Warum die vorhandene Warnung nicht kam

Sie kam nicht, weil sie NICHT ERREICHBAR war. Die Reihenfolge in der Schleife war:

    1. Match-Dedup
    2. Tages-Bet-Cap
    3. adaptiver Tages-Deckel   → `continue`, keine Meldung
    4. Exposure-Cap             → `continue`, keine Meldung
    5. Bankroll-Schutz          → Telegram „bitte nachladen"

Der adaptive Deckel ist `0,4 × Balance`. Bei einer Balance von $0,0343 sind das **$0,0137** —
jeder Einsatz reisst ihn, jeder Kandidat faellt bei (3) heraus, und (5) wird nie erreicht.
Die Warnung existierte und war trotzdem tot.

## Die Regel

**Wer nicht handeln kann, muss es sagen.** Ein Lauf, der Kandidaten findet und keinen platzieren
kann, ist etwas anderes als ein Lauf, der nichts gefunden hat — und beide sahen gleich aus.
Dieselbe Fehlerklasse wie „fehlende Information rendert als harmloser Default", nur dass hier
das Nichthandeln der Default war.
"""
import json
import os
import unittest

# ⚠️ KEINE Umgebungsvariablen beim Import setzen. Die erste Fassung dieser Datei tat genau das
# (`COCOBET_DATASET=liga`) — und weil pytest alle Module in EINEM Prozess laedt, lief danach
# `test_poly_handicap` und der Integritaets-Waechter auf dem Liga-Datensatz statt auf WM. Zwei
# Tests fielen um, die mit dieser Aenderung nichts zu tun haben, und der Grund stand nirgends.
#
# Die geprueften Funktionen brauchen die Umgebung ohnehin nicht: sie sind rein und bekommen
# alles als Argument. Nur der Pfad des Melde-Stands haengt am Datensatz, und den setzt der
# Test selbst (s. setUp).
import auto_wm_poly_trigger as T


def _k(stake=5.5, edge=5.0, n=1):
    return [{"stake": stake, "edgePP": edge} for _ in range(n)]


class TestBlockadeWirdBenannt(unittest.TestCase):
    def test_leerer_wallet_wird_gemeldet(self):
        b = T.handels_blockade(0.0343, 0.0137, _k(n=4))
        self.assertIsNotNone(b)
        self.assertEqual(b["grund"], "balance")
        self.assertIn("4 handelbare", b["text"])
        self.assertIn("nachladen", b["text"])

    def test_die_meldung_nennt_die_beste_edge(self):
        """Ohne sie steht da „es gibt Trades" — mit ihr steht da, was einem entgeht."""
        b = T.handels_blockade(0.5, 0.2, [{"stake": 5.5, "edgePP": 4.7},
                                          {"stake": 5.5, "edgePP": 7.7}])
        self.assertIn("7.7", b["text"])

    def test_genug_geld_ist_keine_blockade(self):
        self.assertIsNone(T.handels_blockade(200.0, 50.0, _k(n=4)))

    def test_keine_kandidaten_ist_KEINE_blockade(self):
        """Der wichtigste Unterschied: „nichts gefunden" ist ein normaler Lauf und darf keine
        Alarmmeldung ausloesen — sonst ist die Meldung nach einer Woche Rauschen."""
        self.assertIsNone(T.handels_blockade(0.0, 0.0, []))

    def test_deckel_unter_einsatz_wird_eigens_gemeldet(self):
        """Der Fall, der Lucas' Lauf wirklich getroffen hat: Geld waere theoretisch da, aber
        der adaptive Deckel liegt darunter. Ein eigener Grund, weil die Abhilfe eine andere ist."""
        b = T.handels_blockade(20.0, 2.0, _k(stake=5.5))
        self.assertEqual(b["grund"], "deckel")
        self.assertIn("Deckel", b["text"])

    def test_der_guenstigste_kandidat_entscheidet(self):
        """Sonst meldet der Trigger Blockade, obwohl der kleinste Einsatz noch durchpasst."""
        self.assertIsNone(T.handels_blockade(20.0, 10.0,
                                             [{"stake": 5.0, "edgePP": 4}, {"stake": 50.0, "edgePP": 9}]))


class TestDieMeldungKommtHoechstensEinmalAmTag(unittest.TestCase):
    def setUp(self):
        self._orig = T.MELDE_FILE
        import tempfile
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp.close()
        os.unlink(self._tmp.name)
        T.MELDE_FILE = self._tmp.name

    def tearDown(self):
        T.MELDE_FILE = self._orig
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_erste_meldung_ja_zweite_nein(self):
        """Der Lauf geht alle 30 Minuten. Ohne Deckel waeren das zwei Dutzend gleiche
        Nachrichten am Tag — und die naechste echte ginge darin unter."""
        self.assertTrue(T.melden_faellig("balance", "2026-09-14"))
        T.melden_vermerken("balance", "2026-09-14")
        self.assertFalse(T.melden_faellig("balance", "2026-09-14"))

    def test_am_naechsten_tag_wieder(self):
        T.melden_vermerken("balance", "2026-09-14")
        self.assertTrue(T.melden_faellig("balance", "2026-09-15"))

    def test_ein_anderer_grund_ist_eine_andere_meldung(self):
        T.melden_vermerken("balance", "2026-09-14")
        self.assertTrue(T.melden_faellig("deckel", "2026-09-14"))

    def test_kaputter_stand_blockiert_die_meldung_nicht(self):
        with open(T.MELDE_FILE, "w") as f:
            f.write("kein json")
        self.assertTrue(T.melden_faellig("balance", "2026-09-14"))


class TestDieBlockadePruefungStehtVORDerSchleife(unittest.TestCase):
    def test_quelltext_prueft_vor_dem_durchlauf(self):
        """Genau das war der Fehler: die Pruefung stand in der Schleife HINTER dem Deckel."""
        from pathlib import Path
        q = (Path(__file__).resolve().parent.parent / "auto_wm_poly_trigger.py").read_text(encoding="utf-8")
        ohne = "\n".join(z for z in q.splitlines() if not z.lstrip().startswith("#"))
        i_block = ohne.index("_blockade = handels_blockade(")
        i_loop = ohne.index("for order in candidates:", ohne.index("def main("))
        self.assertLess(i_block, i_loop,
                        "die Blockade-Pruefung steht wieder hinter der Schleife")


if __name__ == "__main__":
    unittest.main()


class TestDieseTestsVergiftenDieUmgebungNicht(unittest.TestCase):
    """🔴 Beim Bauen passiert: dieses Modul setzte `COCOBET_DATASET` beim Import. pytest laedt
    alle Module in EINEM Prozess — danach liefen `test_poly_handicap` und der Integritaets-
    Waechter auf dem falschen Datensatz und fielen um. Zwei Fehlschlaege ohne Bezug zur
    Aenderung, und der Grund stand nirgends.

    Dieselbe Fehlerklasse wie ueberall hier, nur im Testlauf: ein globaler Zustand, den einer
    setzt und alle anderen erben."""

    def test_kein_environ_schreiben_auf_modulebene(self):
        from pathlib import Path
        q = Path(__file__).read_text(encoding="utf-8")
        kopf = q[:q.index("class ")]
        zeilen = [z for z in kopf.splitlines()
                  if "os.environ[" in z and not z.lstrip().startswith("#")]
        self.assertEqual(zeilen, [], "dieses Modul setzt wieder Umgebung beim Import")
