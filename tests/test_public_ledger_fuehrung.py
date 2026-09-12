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

🔴 NACHTRAG 12.09.2026 (Lucas: „Team in Führung und dann kommt das trotzdem — meinst du, das ist
stark positiv? ich hab das gestern und heute mitgekriegt und beide Male minus").

Die exakte Antwort gibt es immer noch nicht, und das muss hier stehen. Seit dem Stempel sind
**2** Pushs auf einen Führenden gegangen, davon **1** abgerechnet. Die +27,8 % von oben waren
die Rekonstruktion, nicht die Messung — und sie als Widerlegung zu präsentieren war zu stark.

Dazu ein Fehler in diesem Test selbst: er schrieb fest, `onLeader` müsse ein `bool` sein, mit
der Begründung „beim Senden ist die Lage immer bekannt". Falsch — bei 7 von 25 gestempelten
Pushs gab es keinen Live-Stand, und alle sieben landeten als `False` in der Vergleichsgruppe.
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

    def test_unbekannter_stand_wird_NICHT_zu_false(self):
        """🔴 12.09.2026 — hier stand das Gegenteil, und es war falsch.

        Der Test hiess `test_onleader_ist_ein_bool_kein_none` und begruendete das mit „beim
        Senden ist die Lage aber immer bekannt". Die Daten sagen etwas anderes: von 25
        gestempelten Pushs hatten **7** keinen Live-Stand zum Sendezeitpunkt. Alle sieben standen
        als `onLeader: False` im Buch — also in der Vergleichsgruppe „nicht auf den Fuehrenden",
        mit der die Frage beantwortet werden soll, ob Fuehrungs-Pushes taugen.

        Damit hat mein eigener Test die Fehlerklasse festgeschrieben, die dieses Projekt sonst
        ueberall jagt: fehlende Information als harmloser Default. Jetzt drei Zustaende.
        """
        self.assertNotIn('bool(a.get("onLeader"))', LOG,
                         "bool() macht aus 'unbekannt' ein 'nein'")
        self.assertIn('"onLeader": a.get("onLeader")', LOG)

    def test_die_funktion_selbst_kennt_drei_zustaende(self):
        quelle = _funktion("_money_on_leader")
        self.assertIn("return None", quelle,
                      "ohne den dritten Zustand ist 'Stand unbekannt' nicht von "
                      "'fuehrt nicht' zu unterscheiden")
        self.assertIn("_stand_bekannt(m)", quelle)


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
                self.assertIn(r["onLeader"], (True, False, None),
                              "drei Zustaende, nichts anderes")

    def test_unbekannte_zeilen_stehen_nicht_als_nein_im_buch(self):
        """Die Gegenprobe am echten Bestand: eine Zeile ohne Live-Stand darf kuenftig nicht mehr
        als `False` gebucht sein. Altzeilen (vor 12.09.) duerfen es noch — sie sind der Grund,
        warum die Frage bis heute nicht exakt beantwortbar war."""
        p = BASE / "betfair_public_ledger.json"
        if not p.exists():
            self.skipTest("kein Public-Ledger vorhanden")
        rows = json.loads(p.read_text(encoding="utf-8"))
        falsch = []
        for r in rows:
            if not isinstance(r, dict) or "onLeader" not in r:
                continue
            if str(r.get("sentAt") or "")[:10] < "2026-09-13":
                continue                       # Altbestand, bewusst ausgenommen
            s = (r.get("live") or {}).get("score")
            unbekannt = not (isinstance(s, list) and len(s) == 2
                             and s[0] is not None and s[1] is not None)
            if unbekannt and r["onLeader"] is False:
                falsch.append(str(r.get("k")))
        self.assertEqual(falsch, [], "\nStand unbekannt, trotzdem als 'nicht auf den "
                         "Fuehrenden' gebucht:\n" + "\n".join(falsch))


if __name__ == "__main__":
    unittest.main()
