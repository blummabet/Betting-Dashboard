#!/usr/bin/env python3
"""test_hz_marktlisten.py — drei Listen von Halbzeit-Märkten, die nicht übereinstimmen.

## Der Vorfall

20.09.2026 (Lucas zu einer Karte von Cottbus–St Pauli: „Wieso ist das eigentlich nicht wie
die anderen HT Wetten mit schwarzer Kugel? Ist mir so nicht aufgefallen, war guter alert und
viel Geld scheinbar").

Die Karte kam als 🟡 Moneyflow (frischer Zufluss, +97,5 K€ in ~15 Min, 98 % einseitig auf
Over 0.5 der ersten Halbzeit) — und sie hatte recht, zwischen Minute 26 und 41 fiel das Tor.

Die ⚫ fehlte zu Recht: die schwarze Kugel verlangt HZ-Geld >= 2x FT-Geld, und der FT-Markt
(Match Odds) stand zu dem Zeitpunkt bei 75–133 K€ gegen 98,7 K€ im HZ-Markt — also 0,7 bis
1,3x statt >= 2x. Kein Missverhältnis, kein Fix-Verdacht.

Die 🔵 fehlte aber NICHT zu Recht. Sie konnte gar nicht kommen:

    HT_MARKETS      = ("Half Time", "First Half Goals 1.5")
    FIX_HT_MARKETS  = ("Half Time", "First Half Goals 0.5", "First Half Goals 1.5")
    HT_LABEL        = {..., "First Half Goals 0.5": "HZ Over/Under 0.5"}

`First Half Goals 0.5` steht in der Fix-Liste und hat sogar ein Anzeige-Label — im blauen
Halbzeit-Alarm steht er nicht. Ein Markt mit 98,7 K€ und 98 % auf einer Seite konnte deshalb
nie eine blaue Karte erzeugen; aufgefallen ist er nur, weil der allgemeine Zufluss-Scanner
ihn mitgenommen hat.

## Warum hier ein Test steht und kein Fix

Weil die naheliegende Reparatur — 0.5 einfach in HT_MARKETS nachtragen — die Sache
verschlechtern könnte. Gemessen am Buch (32.123 abgerechnete Signale):

    Half Time              n=3783  Treffer 40%  ROI +3,3%  P/L +125,1
    First Half Goals 1.5   n=4141  Treffer 53%  ROI -0,2%  P/L  -10,3
    First Half Goals 0.5   n=4567  Treffer 61%  ROI -1,6%  P/L  -72,0   ← der fehlende

Der fehlende ist der SCHWÄCHSTE der drei. Und die stark einseitige Teilmenge, also genau
Lucas' Fall, trägt bisher n=49 mit +2,2 % — bei einer Schranke von +19 % sagt das nichts.

Fehlerklasse: drei Kopien derselben Liste, von denen zwei gepflegt wurden und eine nicht.
Dieser Test hält den Unterschied fest, damit er eine ENTSCHEIDUNG ist und kein Versehen —
und damit ihn niemand (ich eingeschlossen) beim nächsten Mal blind synchronisiert.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import betfair_alerts as A  # noqa: E402

NUR_FIX = "First Half Goals 0.5"


class TestHzMarktlisten(unittest.TestCase):
    def test_der_unterschied_ist_genau_dieser_eine_markt(self):
        """Fällt der Unterschied weg oder wächst er, ist die Lage eine andere als die
        gemessene — dann gehört neu gemessen, nicht weitergeschoben."""
        nur_fix = set(A.FIX_HT_MARKETS) - set(A.HT_MARKETS)
        self.assertEqual(nur_fix, {NUR_FIX},
                         "Die Fix-Liste und die HZ-Liste unterscheiden sich anders als am "
                         "20.09. gemessen — bitte neu messen statt anpassen.")
        self.assertEqual(set(A.HT_MARKETS) - set(A.FIX_HT_MARKETS), set(),
                         "der blaue Alarm sieht einen Markt, den der Fix-Verdacht nicht kennt")

    def test_der_fehlende_markt_hat_trotzdem_ein_label(self):
        """Das Label existiert — jemand hat den Markt also schon einmal anzeigen wollen.
        Genau daran erkennt man, dass die Lücke ein Versehen war und keine Absicht."""
        self.assertIn(NUR_FIX, A.HT_LABEL)
        self.assertEqual(A.HT_LABEL[NUR_FIX], "HZ Over/Under 0.5")

    def test_jeder_markt_im_blauen_alarm_hat_sein_label(self):
        for mk in A.HT_MARKETS:
            self.assertIn(mk, A.HT_LABEL, mk)

    def test_die_schwarze_kugel_verlangt_ein_missverhaeltnis_keine_hohe_summe(self):
        """Cottbus: 98,7 K€ im HZ-Markt gegen 75–133 K€ im FT-Markt. Viel Geld, aber kein
        Missverhältnis — deshalb zu Recht keine ⚫. Wer die Schranke auf 1,0 senkt, macht aus
        „technisch unlogisch" ein „ziemlich viel"."""
        self.assertGreaterEqual(A.FIX_RATIO_MIN, 2.0)

    def test_die_schwarze_kugel_schweigt_in_der_zweiten_hallfte(self):
        """Ab Minute 30 entscheidet die Uhr, nicht das Geld."""
        self.assertLessEqual(A.FIX_INPLAY_MAX_MIN, 30.0)
        self.assertFalse(A._fix_window_ok({"liveInfo": {"time": 31.0}}))
        self.assertFalse(A._fix_window_ok({"liveInfo": {"is_ht": True}}))
        self.assertTrue(A._fix_window_ok({"liveInfo": {"time": 26.0}}))


if __name__ == "__main__":
    unittest.main()
