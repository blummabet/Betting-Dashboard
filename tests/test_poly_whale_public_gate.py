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
    def test_die_clv_untergrenze_ist_keine_huerde_mehr(self):
        """🔴 22.09.2026. Hier stand „Die EIGENSCHAFT bleibt die Huerde". Sie war es genau
        sechs Tage. Lucas: „Man kann CLV anzeigen, aber es darf kein Kriterium sein, dass
        irgendwas gekickt wird." Sie wird weiter gerechnet und steht auf der Karte."""
        sc = {"0xa": _w(n=20, wins=10, clv_sum=-40.0)}
        ug, _ = W._clv_ug(sc["0xa"])
        self.assertLessEqual(ug, 0)
        self.assertTrue(W._pub_in_top_n(sc, "0xa"))

    def test_der_gemessene_sportverlust_ist_die_huerde(self):
        """Was an ihre Stelle getreten ist — und die Regel fuer „nicht gemessen"."""
        sc = {"0xa": _w(n=20, wins=10, clv_sum=40.0)}
        self.assertTrue(W._pub_in_top_n(sc, "0xa"))
        sc["0xa"]["fenster30"] = {"gewinn": -777}
        self.assertFalse(W._pub_in_top_n(sc, "0xa"))
        sc["0xa"]["fenster30"] = {}
        self.assertTrue(W._pub_in_top_n(sc, "0xa"))

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


# ── 22.09.2026: die zweite Hürde, die in der ersten steckte ─────────────────────────────
class TestEineUntergrenzeBrauchtEineStichprobe(unittest.TestCase):
    """🔴 Beim Nachmessen des eigenen Fixes vom 21.09. gefunden.

    Ich hatte den Rang-Zwang entfernt, weil er still eine ZWEITE Mindest-Stichprobe erzwang
    (n>=12 in der Schrumpf-Rechnung), die niemand als Hürde gemeint hatte. Mit ihm ist aber
    auch die Stichprobe ganz verschwunden. Gemessen über die 4.376 Wallets des Tracks:

        altes Tor (Rang)                 50
        der Fix vom 21.09.            1.622   davon 815 mit n=1, weitere 630 mit n=2–7
        mit der Stichprobe-Zeile        177

    Der einzige Kandidat, der am 22.09. durchkam, hatte n=1 und eine „Untergrenze" von
    +0,0015 pp — Rauschen mit Vorzeichen. Das Repo sagt es selbst: ein Punktschätzer
    entscheidet nichts.

    Fehlerklasse: eine Hürde entfernt und die zweite, die in ihr steckte, gleich mit.
    """

    ADR = "0xaaaa000000000000000000000000000000000001"

    def _scores(self, n, clv_sum=10.49):
        return {self.ADR: _w(n=n, clv_sum=clv_sum)}

    def test_ein_einziger_trade_ist_keine_untergrenze(self):
        s = self._scores(n=1, clv_sum=0.002)
        ug, _ = W._clv_ug(s[self.ADR])
        self.assertGreater(ug, 0, "die Untergrenze ist rechnerisch positiv …")
        self.assertFalse(W._pub_in_top_n(s, self.ADR), "… und trotzdem kein Beleg")

    def test_auch_sieben_reichen_nicht(self):
        self.assertFalse(W._pub_in_top_n(self._scores(n=W.PUB_MIN_TR - 1), self.ADR))

    def test_ab_PUB_MIN_TR_zaehlt_sie(self):
        """Die Schwelle ist nicht neu erfunden: `PUB_MIN_TR` ist die Stichprobe, ab der dieser
        Kanal einen Record ohnehin „belastbar" nennt."""
        self.assertTrue(W._pub_in_top_n(self._scores(n=W.PUB_MIN_TR), self.ADR))

    def test_der_echte_fall_vom_21_09_bleibt_drin(self):
        """⭐ Die Gegenprobe. Eine Stichprobe-Hürde, die den Anlass des Vorfalls wieder
        aussperrt, hat nichts repariert — n=9 muss durchkommen, n=12 der Rangliste wäre
        wieder zu streng."""
        adr = "0x5e6e2c3f06686f2607b86c90e35f536e81a1be00"
        self.assertTrue(W._pub_in_top_n({adr: _w(n=9)}, adr))
        self.assertLess(W.PUB_MIN_TR, W._RANK_MIN_N_CLV)

    def test_eine_wallet_ohne_n_kommt_nicht_durch(self):
        s = {self.ADR: {"clvSumPP": 10.0, "usd": 249422}}
        self.assertFalse(W._pub_in_top_n(s, self.ADR))
