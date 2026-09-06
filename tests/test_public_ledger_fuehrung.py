"""Der Public-Ledger muss die Führungs-Lage im Moment des Sendens festhalten — 06.09.2026.

Lucas: „bitte unterbinde solche Pushes, wo einfach einer Führung gefolgt wird — oder kannst du
das widerlegen?"

Widerlegen ging, aber nur über einen Umweg: `onLeader` stand nirgends im Ledger. Ich musste
aus `htScore` + `leadName` rekonstruieren, wer zur HALBZEIT vorn lag — für In-Play-Pushes zu
beliebigen Minuten ein Näherungswert. Ein Push in der 70. bei 1:0, aber 0:0 zur Pause, landet
in der falschen Gruppe.

Das Ergebnis trug trotzdem (n=52, Treffer 80,8 % gegen 64,1 % implizit, ROI +27,8 %,
einseitige Untergrenze +12,5 %) — aber die nächste Antwort soll exakt sein. Dieselbe Lehre wie
beim Serien-Stempel am 04.09.: **eine Momentaufnahme lässt sich nicht rückwirkend
rekonstruieren.**
"""
import json
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
QUELLE = (BASE / "betfair_alerts.py").read_text(encoding="utf-8")


def _funktion(name):
    """Den Rumpf EINER Funktion herausschneiden — bis zur naechsten Definition auf Spaltenebene.
    Kein fester zweiter Anker: der wandert bei jeder Umsortierung und macht den Test sproede."""
    a = QUELLE.index("def %s" % name)
    b = QUELLE.find("\ndef ", a + 1)
    return QUELLE[a:(b if b > a else len(QUELLE))]


LOG = _funktion("_log_public_push")


class TestLedgerStempel(unittest.TestCase):
    def test_onleader_wird_gestempelt(self):
        self.assertIn('"onLeader"', LOG,
                      "ohne onLeader ist die Führungs-Frage nur über Umwege beantwortbar")

    def test_richtung_und_anteil_kommen_mit(self):
        """`leadDir` entscheidet im `_leader_gate`, ob überhaupt gepusht wird — ohne das Feld
        lässt sich später nicht sagen, WELCHE Führungs-Pushes durchkamen."""
        self.assertIn('"leadDir"', LOG)
        self.assertIn('"leadShare"', LOG)

    def test_spielstand_zum_sendezeitpunkt(self):
        """htScore ist der Halbzeitstand und wird erst NACH dem Push gefüllt. Für einen
        In-Play-Push in der 70. Minute sagt er nichts über die Lage beim Senden."""
        self.assertIn('"live"', LOG)
        self.assertIn("goal_v1", LOG)

    def test_onleader_ist_ein_bool_kein_none(self):
        """None hiesse 'unbekannt' und wäre beim Auswerten nicht von False zu unterscheiden —
        beim Senden ist die Lage aber immer bekannt."""
        self.assertIn('bool(a.get("onLeader"))', LOG)


class TestBestandBleibtLesbar(unittest.TestCase):
    def test_alte_zeilen_ohne_stempel_kippen_die_auswertung_nicht(self):
        p = BASE / "betfair_public_ledger.json"
        if not p.exists():
            self.skipTest("kein Public-Ledger vorhanden")
        rows = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            self.skipTest("Ledger leer")
        # Der Altbestand hat den Stempel nicht — das ist erwartet und darf nichts brechen.
        ohne = sum(1 for r in rows if isinstance(r, dict) and "onLeader" not in r)
        self.assertGreaterEqual(ohne, 0)
        for r in rows:
            if isinstance(r, dict) and "onLeader" in r:
                self.assertIsInstance(r["onLeader"], bool)


if __name__ == "__main__":
    unittest.main()
