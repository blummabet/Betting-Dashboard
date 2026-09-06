"""Das Poly-Track-Board muss seine eigene Regel einhalten — 06.09.2026.

Lucas: „kannst du da auch mal schauen ob alles in Ordnung ist, das ist ein sehr wichtiges
Element für mich."

Auf dem Board steht wörtlich: *„Die Spalte UG entscheidet, nicht ROI — ein ROI ohne
Untergrenze ist ein Punktschätzer"* — und bei den Whale-Pushes meldet es korrekt „kein Urteil:
n=6". Direkt darüber standen die Zahlen, an denen wirklich etwas hängt, OHNE jede Schranke:

    bespielbar        n=555  ROI  +0,1 %      →  UG  −6,1 %   nicht belegt
    Public-Kandidaten n=172  ROI  +6,0 %      →  UG  −3,2 %   nicht belegt
    Conviction 9/10   n= 11  ROI  +9,9 %      →  kein Urteil
    Signal calib+     n= 19  ROI +26,9 %      →  kein Urteil

Und der Anleitungstext knüpfte die Auto-Bet-Empfehlung an „klar im Plus". Mit Schranke
qualifiziert sich **keine** Stufe und **kein** Signal. Klasse: *ein Punktschätzer entscheidet.*

Zweiter Fund: `calib+`, `calib-`, `turned` standen in „Welches Signal trägt die Kante?"
zwischen money/sharp/steam/bf — mit calib+ bei +26,9 % ganz oben. Das sind keine Auslöser,
sondern die Marken, die der LERNER an einen Play hängt, nachdem er ihn gestuft hat. Die
Kalibrierung benotete ihre eigene Hausaufgabe. Klasse: *eine Kennzahl urteilt über sich selbst.*
"""
import unittest

import poly_shortlist_track as T


def _play(pnl, stake=10.0, clv=0.0, signals=(), conv=6, cat="Fussball", result="win"):
    return {"pnl": pnl, "stake": stake, "clvPP": clv, "signals": list(signals),
            "conv": conv, "cat": cat, "result": result}


class TestUntergrenze(unittest.TestCase):
    def test_jede_menge_traegt_ihre_schranke(self):
        rows = [_play(1.0 if i % 2 else -1.0) for i in range(60)]
        a = T._agg_one(rows)
        for feld in ("roi", "roiUg", "belegt", "clvAvg", "clvUg"):
            self.assertIn(feld, a, f"{feld} fehlt — dann steht auf dem Board wieder ein "
                                   "nackter Punktschätzer")

    def test_unter_der_mindestzahl_gibt_es_kein_urteil(self):
        """Kein Urteil ist etwas anderes als ein gemessenes Nein. Ohne diese Sperre fiel die
        Schranke am 03.09. schon einmal auf den Punktschätzer zusammen („UG +74 %" aus drei
        Plays)."""
        a = T._agg_one([_play(5.0) for _ in range(5)])
        self.assertIsNone(a["roiUg"])
        self.assertFalse(a["belegt"])

    def test_belegt_nur_wenn_die_schranke_ueber_null_liegt(self):
        gut = T._agg_one([_play(4.0 + (i % 3) * 0.2) for i in range(60)])
        self.assertTrue(gut["belegt"])
        self.assertGreater(gut["roiUg"], 0)

        wackelig = T._agg_one([_play(12.0 if i % 2 else -10.0) for i in range(60)])
        self.assertFalse(wackelig["belegt"],
                         "stark gestreut um einen positiven Schnitt ist kein Beleg")

    def test_die_schranke_liegt_unter_dem_punktschaetzer(self):
        a = T._agg_one([_play(2.0 + (i % 4) * 0.5) for i in range(60)])
        self.assertLess(a["roiUg"], a["roi"])

    def test_plays_ohne_einsatz_verfaelschen_die_streuung_nicht(self):
        rows = [_play(1.0, stake=10.0) for _ in range(40)] + [_play(0.0, stake=0.0)]
        a = T._agg_one(rows)
        self.assertEqual(a["n"], 41)
        self.assertIsNotNone(a["roiUg"])


class TestKalibrierMarkenGetrennt(unittest.TestCase):
    def test_calib_marken_sind_keine_signale(self):
        rows = ([_play(1.0, signals=["money"]) for _ in range(40)]
                + [_play(5.0, signals=["calib+"]) for _ in range(20)]
                + [_play(-1.0, signals=["turned"]) for _ in range(5)])
        a = T.aggregate(rows)
        self.assertIn("money", a["bySignal"])
        for marke in ("calib+", "turned"):
            self.assertNotIn(marke, a["bySignal"],
                             f"{marke} steht wieder zwischen den Auslöser-Signalen — "
                             "die Kalibrierung benotet dann ihre eigene Hausaufgabe")
            self.assertIn(marke, a["byKalibrierung"])

    def test_die_markenliste_ist_vollstaendig(self):
        self.assertEqual(T.KALIB_MARKEN, frozenset({"calib+", "calib-", "turned"}))

    def test_getrennt_heisst_nicht_geloescht(self):
        """Die Zahl bleibt interessant — als Selbstkontrolle, nicht als Beleg für eine Kante."""
        rows = [_play(2.0, signals=["calib+"]) for _ in range(40)]
        a = T.aggregate(rows)
        self.assertEqual(a["byKalibrierung"]["calib+"]["n"], 40)


class TestGegenDenEchtenBestand(unittest.TestCase):
    def test_keine_menge_ist_heute_belegt(self):
        """Hält den Stand vom 06.09. fest. Wird eine Menge eines Tages belegt, schlägt dieser
        Test an — und DAS ist die Nachricht, nicht sein Grünsein."""
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "poly_shortlist_track.json"
        if not p.exists():
            self.skipTest("kein Track vorhanden")
        d = json.loads(p.read_text(encoding="utf-8"))
        a = T.aggregate(d.get("settled") or [], d.get("blockedCats") or ())
        belegt = [k for k in ("all", "bettable", "public") if a[k]["belegt"]]
        self.assertEqual(belegt, [],
                         f"Neu belegt: {belegt} — bitte ansehen, das wäre der erste Fall.")


if __name__ == "__main__":
    unittest.main()
