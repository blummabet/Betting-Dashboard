"""Tests fuer signal_verlauf.py — 06.09.2026.

Die Regel: **ein Urteil wirkt erst, wenn es ueber mehrere Messungen an verschiedenen Tagen und
ueber mindestens zwei Wochen gehalten hat.** Ein einziger abweichender Eintrag setzt die
Zaehlung zurueck.

Der Grund steht im Modulkopf: die Bilanz prueft ~30 Signale gleichzeitig, 1-2 falsche Urteile
pro Lauf sind zu erwarten. Ein Loop, der sofort abwertet, laeuft dem Rauschen hinterher.
"""
import unittest

import signal_verlauf as V


def _bil(**urteile):
    return {n: {"clvUrteil": u, "ausgangUrteil": "kein Urteil"} for n, u in urteile.items()}


def _reihe(tage_und_urteile):
    return [{"tag": t, "clv": u, "ausgang": "kein Urteil"} for t, u in tage_und_urteile]


class TestFortschreiben(unittest.TestCase):
    def test_haengt_an(self):
        v = V.fortschreiben({}, _bil(a="schadet"), "2026-09-06T11:00:00Z")
        self.assertEqual(len(v["a"]), 1)
        self.assertEqual(v["a"][0]["tag"], "2026-09-06")

    def test_pro_tag_nur_ein_eintrag(self):
        """Die Pipeline laeuft mehrmals taeglich — sonst waeren drei Laeufe eines Nachmittags
        schon 'drei Messungen'."""
        v = V.fortschreiben({}, _bil(a="schadet"), "2026-09-06T06:00:00Z")
        v = V.fortschreiben(v, _bil(a="kein Urteil"), "2026-09-06T18:00:00Z")
        self.assertEqual(len(v["a"]), 1)
        self.assertEqual(v["a"][0]["clv"], "kein Urteil", "der letzte Stand des Tages zaehlt")

    def test_verlauf_wird_gedeckelt(self):
        v = {}
        for i in range(1, V.MAX_VERLAUF + 12):
            v = V.fortschreiben(v, _bil(a="schadet"), f"2026-01-{i:02d}T10:00:00Z"
                                if i <= 31 else f"2026-02-{i-31:02d}T10:00:00Z")
        self.assertLessEqual(len(v["a"]), V.MAX_VERLAUF)

    def test_kaputte_eingaben(self):
        self.assertEqual(V.fortschreiben(None, None, "2026-09-06T10:00:00Z"), {})
        self.assertEqual(V.fortschreiben({}, _bil(a="schadet"), "kaputt"), {})
        self.assertEqual(V.fortschreiben({}, {"a": "kein dict"}, "2026-09-06T10:00:00Z"), {})


class TestStabil(unittest.TestCase):
    def test_zu_wenige_messungen(self):
        r = _reihe([("2026-08-01", "schadet"), ("2026-09-01", "schadet")])
        self.assertFalse(V.stabil(r, "schadet"))

    def test_zu_kurze_spanne(self):
        """Drei Messungen an drei aufeinanderfolgenden Tagen sind keine zwei Wochen."""
        r = _reihe([("2026-09-01", "schadet"), ("2026-09-02", "schadet"),
                    ("2026-09-03", "schadet")])
        self.assertFalse(V.stabil(r, "schadet"))

    def test_haelt_lange_genug(self):
        r = _reihe([("2026-08-15", "schadet"), ("2026-08-25", "schadet"),
                    ("2026-09-01", "schadet")])
        self.assertTrue(V.stabil(r, "schadet"))

    def test_ein_ausreisser_setzt_zurueck(self):
        """Der Kern der Bremse: wir wollen ein Urteil, das HAELT, nicht eines, das ueberwiegt."""
        r = _reihe([("2026-08-01", "schadet"), ("2026-08-10", "schadet"),
                    ("2026-08-20", "kein Urteil"), ("2026-09-01", "schadet")])
        self.assertFalse(V.stabil(r, "schadet"))

    def test_serie_zaehlt_vom_juengsten_rueckwaerts(self):
        r = _reihe([("2026-07-01", "kein Urteil"), ("2026-08-01", "schadet"),
                    ("2026-08-15", "schadet"), ("2026-09-01", "schadet")])
        self.assertTrue(V.stabil(r, "schadet"))

    def test_falsches_urteil_zaehlt_nicht(self):
        r = _reihe([("2026-08-01", "schadet"), ("2026-08-15", "schadet"),
                    ("2026-09-01", "schadet")])
        self.assertFalse(V.stabil(r, "traegt bei"))

    def test_kaputte_eingaben(self):
        self.assertFalse(V.stabil(None, "schadet"))
        self.assertFalse(V.stabil([], "schadet"))
        self.assertFalse(V.stabil([{"clv": "schadet"}] * 5, "schadet"))


class TestStabileUrteile(unittest.TestCase):
    def test_trennt_die_beiden_richtungen(self):
        v = {"boese": _reihe([("2026-08-01", "schadet"), ("2026-08-15", "schadet"),
                              ("2026-09-01", "schadet")]),
             "gut": _reihe([("2026-08-01", "traegt bei"), ("2026-08-15", "traegt bei"),
                            ("2026-09-01", "traegt bei")]),
             "wackelig": _reihe([("2026-08-01", "schadet"), ("2026-08-15", "kein Urteil"),
                                 ("2026-09-01", "schadet")])}
        u = V.stabile_urteile(v)
        self.assertEqual(u["schadet"], ["boese"])
        self.assertEqual(u["traegt bei"], ["gut"])

    def test_widerspruch_hebt_sich_auf(self):
        """CLV sagt gut, Ausgang sagt schlecht, beides stabil — dann gilt keines."""
        reihe = [{"tag": t, "clv": "traegt bei", "ausgang": "schadet"}
                 for t in ("2026-08-01", "2026-08-15", "2026-09-01")]
        u = V.stabile_urteile({"zwiespaeltig": reihe})
        self.assertEqual(u["schadet"], [])
        self.assertEqual(u["traegt bei"], [])
        self.assertEqual(u.get("widersprüchlich"), ["zwiespaeltig"])

    def test_leerer_verlauf(self):
        u = V.stabile_urteile({})
        self.assertEqual(u["schadet"], [])
        self.assertEqual(u["traegt bei"], [])


if __name__ == "__main__":
    unittest.main()
