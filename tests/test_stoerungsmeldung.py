"""🔴 20.09.2026 (Lucas: „ich weiß dann nicht, funktioniert das eigentlich, was tracken wir da").

Drei Guard-Batterien laufen 57 Prüfungen und schreiben sie in drei Artefakte — und sonst
nirgendwohin. Am Abend des 20.09. meldeten sie zusammen 14 Dinge, darunter Positionen, die seit
13 Tagen offen sind, und 39 % aufgelöste Tennis-Märkte.

Fehlerklasse: ein Messgerät, dessen Zeiger niemand ansieht.

Diese Tests halten die vier Eigenschaften fest, die eine solche Meldung von „noch einer Fläche"
unterscheiden — und die als Erstes kippen, wenn jemand sie anfasst.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stoerungsmeldung as S

JETZT = datetime(2026, 9, 21, 7, 0, tzinfo=timezone.utc)


def _batterie(checks, alter_h=1.0):
    return {"generatedAt": (JETZT - timedelta(hours=alter_h)).isoformat(), "checks": checks}


def _c(label, ok=False, sev="error", fails=("etwas",), cid=None):
    d = {"label": label, "ok": ok, "severity": sev, "nFail": 0 if ok else len(fails),
         "failures": list(fails)}
    if cid:
        d["id"] = cid
    return d


class TestStilleWennNichtsKaputtIst(unittest.TestCase):
    """Eine tägliche „alles gut"-Nachricht wird nach einer Woche weggewischt — und dann auch
    die, in der etwas steht."""

    def test_alles_gruen_ergibt_keine_nachricht(self):
        a = {"x.json": _batterie([_c("A", ok=True), _c("B", ok=True)])}
        self.assertEqual(S.baue_meldung(S.sammeln(a, JETZT), JETZT), "")

    def test_ein_einziger_befund_ergibt_eine_nachricht(self):
        a = {"x.json": _batterie([_c("A", ok=True), _c("Ergebnisse kommen an")])}
        self.assertNotEqual(S.baue_meldung(S.sammeln(a, JETZT), JETZT), "")


class TestGeldStehtOben(unittest.TestCase):
    def test_geld_vor_messung(self):
        a = {"x.json": _batterie([_c("Takt: Cron gegen gemessene Laeufe", sev="warn"),
                                  _c("Ergebnisse kommen an")])}
        t = S.baue_meldung(S.sammeln(a, JETZT), JETZT)
        self.assertLess(t.index("Ergebnisse kommen an"), t.index("Takt:"))

    def test_die_einstufung_kommt_aus_der_liste_nicht_aus_der_schwere(self):
        """Ein Geld-Check bleibt Geld, auch wenn er nur `warn` ist — und umgekehrt."""
        a = {"x.json": _batterie([_c("Jeder Push hat seinen Beleg", sev="warn"),
                                  _c("Stumme Signale: wer hat nie gefeuert?", sev="error")])}
        b = S.sammeln(a, JETZT)
        self.assertEqual([z["label"] for z in b["geld"]], ["Jeder Push hat seinen Beleg"])
        self.assertEqual([z["label"] for z in b["messung"]],
                         ["Stumme Signale: wer hat nie gefeuert?"])

    def test_innerhalb_einer_gruppe_zuerst_die_fehler(self):
        a = {"x.json": _batterie([_c("Positionswert ist frisch", sev="warn"),
                                  _c("Ergebnisse kommen an", sev="error")])}
        self.assertEqual([z["label"] for z in S.sammeln(a, JETZT)["geld"]][0],
                         "Ergebnisse kommen an")


class TestEinVeraltetesMessgeraetIstSelbstEinBefund(unittest.TestCase):
    """Die Klasse, die an diesem Tag dreimal zugeschlagen hat: fehlende Information rendert als
    harmloser Default. Eine stille Meldung über einer toten Batterie hiesse „alles gut"."""

    def test_eine_alte_batterie_meldet_sich_als_blind(self):
        a = {"x.json": _batterie([_c("A", ok=True)], alter_h=S.ALT_H + 1)}
        b = S.sammeln(a, JETZT)
        self.assertEqual(len(b["blind"]), 1)
        self.assertIn("Blind", S.baue_meldung(b, JETZT))

    def test_ihre_checks_werden_nicht_mehr_geglaubt(self):
        """Weder die grünen noch die roten — sie sagt gerade gar nichts."""
        a = {"x.json": _batterie([_c("Ergebnisse kommen an")], alter_h=S.ALT_H + 1)}
        b = S.sammeln(a, JETZT)
        self.assertEqual(b["geld"], [])
        self.assertEqual(len(b["blind"]), 1)

    def test_ohne_zeitstempel_ebenfalls_blind(self):
        b = S.sammeln({"x.json": {"checks": [_c("A", ok=True)]}}, JETZT)
        self.assertEqual(len(b["blind"]), 1)

    def test_eine_unlesbare_datei_ebenfalls(self):
        self.assertEqual(len(S.sammeln({"x.json": None}, JETZT)["blind"]), 1)

    def test_eine_frische_batterie_ist_nicht_blind(self):
        self.assertEqual(S.sammeln({"x.json": _batterie([_c("A", ok=True)], 1.0)},
                                   JETZT)["blind"], [])


class TestEinNeuerCheckVerschwindetNichtStill(unittest.TestCase):
    """Ein neuer geldnaher Check landet per Default unter „Messung". Damit das kein stiller
    Default wird, meldet er sich als „nicht eingestuft" — eine Entscheidung wird erzwungen."""

    def test_ein_unbekannter_geldnaher_check_faellt_auf(self):
        a = {"x.json": _batterie([_c("Neue Wette ohne Gegenbuchung")])}
        b = S.sammeln(a, JETZT)
        self.assertEqual(len(b["offen"]), 1)
        self.assertIn("Nicht eingestuft", S.baue_meldung(b, JETZT))

    def test_ein_check_ohne_geldwort_bleibt_still_unter_messung(self):
        b = S.sammeln({"x.json": _batterie([_c("Serien-Buch zeigt beide Buecher")])}, JETZT)
        self.assertEqual(b["offen"], [])
        self.assertEqual(len(b["messung"]), 1)

    def test_ein_geprueft_kein_geld_check_meldet_sich_nicht_mehr(self):
        b = S.sammeln({"x.json": _batterie([_c("Money Map meldet ihre Luecken")])}, JETZT)
        self.assertEqual(b["offen"], [])

    def test_am_echten_bestand_ist_nichts_uneingestuft(self):
        """Der Riegel gegen eine Liste, die niemand pflegt: stehen die echten Checks nicht alle
        in GELD oder GEPRUEFT_KEIN_GELD, schlägt das hier an."""
        import json
        offen = []
        for n in S.QUELLEN:
            p = Path(__file__).resolve().parents[1] / n
            if not p.exists():
                continue
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for c in (d.get("checks") or []):
                if S.braucht_entscheidung(c):
                    offen.append(S.schluessel(c))
        self.assertEqual(offen, [],
                         "diese Checks brauchen eine Einstufung in stoerungsmeldung.py: %s"
                         % ", ".join(offen))


class TestEinmalAmTagImFenster(unittest.TestCase):
    def test_im_fenster_und_noch_nicht_gesendet(self):
        self.assertTrue(S.soll_senden({}, JETZT))

    def test_heute_schon_gesendet(self):
        self.assertFalse(S.soll_senden({"zuletzt": "2026-09-21"}, JETZT))

    def test_gestern_gesendet_heute_wieder(self):
        self.assertTrue(S.soll_senden({"zuletzt": "2026-09-20"}, JETZT))

    def test_ausserhalb_des_fensters_nicht(self):
        self.assertFalse(S.soll_senden({}, JETZT.replace(hour=15)))
        self.assertFalse(S.soll_senden({}, JETZT.replace(hour=3)))


class TestDieNachrichtBleibtLesbar(unittest.TestCase):
    def test_die_messung_wird_gekappt_das_geld_nicht(self):
        viele_messung = [_c("Messkram %d" % i, sev="warn") for i in range(9)]
        viel_geld = [_c("Ergebnisse kommen an"), _c("Positionswert ist frisch"),
                     _c("Jeder Push hat seinen Beleg"), _c("geschlossen heisst belegt"),
                     _c("offene Wette hat den Anpfiff ueberlebt")]
        t = S.baue_meldung(S.sammeln({"x.json": _batterie(viele_messung + viel_geld)}, JETZT),
                           JETZT)
        self.assertIn("und 5 weitere", t)
        for g in ("Ergebnisse kommen an", "Positionswert ist frisch",
                  "offene Wette hat den Anpfiff ueberlebt"):
            self.assertIn(g, t, "Geld wird nie gekappt")

    def test_lange_zeilen_werden_gekuerzt(self):
        lang = "x" * 500
        t = S.baue_meldung(S.sammeln({"x.json": _batterie([_c("Ergebnisse kommen an",
                                                              fails=(lang,))])}, JETZT), JETZT)
        self.assertNotIn(lang, t)
        self.assertIn("…", t)


if __name__ == "__main__":
    unittest.main()
