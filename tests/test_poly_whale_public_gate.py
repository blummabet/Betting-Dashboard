"""🔴 21.09.2026 (Lucas: „schon wieder was falsch beim public, es kommen seit gestern 11 uhr
keine whale pushes mehr").

Letzter Public-Whale-Push: 20.09. 09:31 UTC — genau sein „gestern 11 Uhr" (lokal). Der
Trades-Pfad lief die ganze Zeit weiter; nur der öffentliche stand.

Trichter gemessen, gegen die Live-Artefakte:

    select() — Größe/Record                     1
    _pub_ok — Sportart + Preisfenster           1
    _pub_in_top_n — Sharp-Rangliste             0   ← hier
    … alle weiteren Tore                        0

Der eine Kandidat: Wallet 0x5e6e2c3f…, $103.500 Position, n=9, Treffer 56 %,
CLV-Untergrenze +0,31 pp. Also genau das, was der Kanal zeigen soll.

Der Grund: `if not rang` hat „gar nicht gerangt" wie „schlecht gerangt" behandelt. Die
Sharp-Rangliste verlangt in der Schrumpf-Rechnung n≥12 (und eine vorhandene `pnl`), das
öffentliche Tor laut `PUB_MIN_TR` nur n≥8. Eine zweite, strengere Hürde, die niemand als
Hürde gemeint hat — und die im Docstring des Tores selbst seit dem 16.09. ausgeschlossen
wird: „Der Gate fragt ab jetzt nach der EIGENSCHAFT statt nach einem Listenplatz."

Zwei Fehlerklassen in einem Tor:
  · ein Satz, der behauptet, was der Code daneben widerlegt
  · ein fehlender Wert, der wie ein schlechter behandelt wird

Derselbe Wächter trägt bereits den Vorfall vom 16.09. („gestern und heute kam kein einziger
Public-Push") — dieselbe Stelle, dieselbe Wirkung, fünf Tage später.
"""
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import poly_whale_watch as W


def _w(n=9, wins=5, clv_sum=10.49, usd=249422, pnl=600282.4):
    return {"n": n, "wins": wins, "clvSumPP": clv_sum, "usd": usd, "pnl": pnl,
            "clvSqSum": 5.79, "clvFenN": 4, "clvFenSum": 3.57}


class TestDerEchteFall(unittest.TestCase):
    """Die Wallet, die am 21.09. als einzige durchkam und rausflog."""

    def setUp(self):
        self.adr = "0x5e6e2c3f06686f2607b86c90e35f536e81a1be00"
        self.scores = {self.adr: _w()}

    def test_sie_hat_eine_positive_clv_untergrenze(self):
        ug, art = W._clv_ug(self.scores[self.adr])
        self.assertIsNotNone(ug)
        self.assertGreater(ug, 0)

    def test_sie_steht_nicht_in_der_rangliste(self):
        """n=9 < 12 in der Schrumpf-Rechnung — die Rangliste kennt sie gar nicht."""
        self.assertIsNone(W._sharp_rank_map(self.scores).get(self.adr))

    def test_und_darf_trotzdem_public(self):
        self.assertTrue(W._pub_in_top_n(self.scores, self.adr),
                        "kein Rang ist keine Auskunft, kein Durchfallen")


class TestDieNotbremseBremstWasSieBeurteilenKann(unittest.TestCase):
    def test_ohne_clv_untergrenze_kein_public(self):
        """Die EIGENSCHAFT bleibt die Huerde — daran aendert sich nichts."""
        sc = {"0xa": _w(n=20, wins=10, clv_sum=-40.0)}
        ug, _ = W._clv_ug(sc["0xa"])
        self.assertLessEqual(ug, 0)
        self.assertFalse(W._pub_in_top_n(sc, "0xa"))

    def test_ein_schlechter_rang_sperrt_weiterhin(self):
        """Wer IN der Liste steht und dort hinten liegt, bleibt draussen."""
        sc = {}
        for i in range(80):
            sc["0x%040d" % i] = _w(n=20, wins=14, clv_sum=40.0 - i * 0.4, usd=400000)
        rang = W._sharp_rank_map(sc)
        letzte = [w for w, r in rang.items() if r > W.PUB_RANG_NOTBREMSE]
        self.assertTrue(letzte, "die Testdaten muessen Raenge jenseits der Notbremse erzeugen")
        schlecht = letzte[0]
        if W._clv_ug(sc[schlecht])[0] and W._clv_ug(sc[schlecht])[0] > 0:
            self.assertFalse(W._pub_in_top_n(sc, schlecht),
                             "schlechter Rang muss weiter sperren")

    def test_ein_guter_rang_kommt_durch(self):
        sc = {}
        for i in range(80):
            sc["0x%040d" % i] = _w(n=20, wins=14, clv_sum=40.0 - i * 0.4, usd=400000)
        rang = W._sharp_rank_map(sc)
        bester = min(rang, key=lambda w: rang[w])
        self.assertTrue(W._pub_in_top_n(sc, bester))

    def test_ohne_wallet_kein_public(self):
        self.assertFalse(W._pub_in_top_n({"0xa": _w()}, ""))
        self.assertFalse(W._pub_in_top_n({"0xa": _w()}, None))


class TestZweiSchwellenFuerDieselbeFrage(unittest.TestCase):
    """Der Kern: das Public-Tor verlangte faktisch n>=12, obwohl PUB_MIN_TR n>=8 sagt."""

    def test_die_beiden_schwellen_stehen_auseinander(self):
        self.assertLess(W.PUB_MIN_TR, W._RANK_MIN_N_CLV,
                        "genau diese Luecke war die unsichtbare Huerde")

    def test_eine_wallet_dazwischen_kommt_jetzt_durch(self):
        for n in range(W.PUB_MIN_TR, W._RANK_MIN_N_CLV):
            sc = {"0xb": _w(n=n, wins=max(1, int(n * 0.6)), clv_sum=1.2 * n)}
            ug, _ = W._clv_ug(sc["0xb"])
            if ug is not None and ug > 0:
                self.assertTrue(W._pub_in_top_n(sc, "0xb"),
                                f"n={n} liegt ueber PUB_MIN_TR und muss durchkommen")


if __name__ == "__main__":
    unittest.main()
