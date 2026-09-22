#!/usr/bin/env python3
"""
tests/test_erzeugungs_bilanz.py — 22.09.2026: ein Protokoll, das nur die Überlebenden kennt.

🔴 Lucas' Störungsmeldung, 06:02 UTC: „Letzter Live-Scan vor 1.6h (Takt: 15 Min)". Gemessen am
Protokoll selbst: 6,1 statt 96 Läufe am Tag, `manage-liga-poly` 4,7 statt 25.

Der Kommentar bei `hole_lauf` (20.09.) nennt die beiden Erklärungen und die Zahl, die sie
trennt: lange Wartezeit = „die Macs sind dicht", kurze Wartezeit = „der Zeitplan feuert nicht".
Die Zahl ist inzwischen da und eindeutig — **alle 20 protokollierten Läufe hatten 0,0 s
Wartezeit.** Wer lief, fand sofort einen Runner.

Nur: „bleibt übrig" ist kein Beweis. Es gibt eine dritte Möglichkeit, die genauso aussieht —
GitHub hält je Concurrency-Gruppe höchstens EINEN wartenden Lauf, und ein neuer verdrängt den
alten. Verdrängte Läufe starten nie und schreiben nichts; dieses Protokoll kann sie per Bauart
nicht sehen.

Fehlerklasse: **ein Protokoll, das nur die Überlebenden kennt.**

Ich habe in dieser Sache schon zweimal die falsche Ursache genannt (Runner-Auslastung,
Schedule-Last) — deshalb hier keine dritte Behauptung, sondern die Messung, die sie entscheidet.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import run_health as R


def _lauf(created, started=None, status="completed", conclusion="success"):
    return {"created": created, "started": started, "status": status, "conclusion": conclusion}


T = "2026-09-%02dT%02d:00:00Z"


class TestDieBeidenErklaerungenSindUnterscheidbar(unittest.TestCase):
    def test_der_zeitplan_feuert_nicht(self):
        """Wenige erzeugt, alle gelaufen → GitHub legt die Läufe gar nicht erst an."""
        rows = [_lauf(T % (21, h), started=T % (21, h)) for h in range(0, 24, 4)]
        b = R.erzeugungs_bilanz(rows)
        self.assertEqual(b["erzeugt"], 6)
        self.assertEqual(b["gelaufen"], 6)
        self.assertEqual(b["verdraengt"], 0)

    def test_sie_werden_verdraengt(self):
        """⭐ Viele erzeugt, wenige gelaufen → die Läufe sterben in der Warteschlange."""
        rows = ([_lauf(T % (21, h), started=T % (21, h)) for h in (0, 12)]
                + [_lauf(T % (21, h)) for h in range(1, 12)])
        b = R.erzeugungs_bilanz(rows)
        self.assertEqual(b["erzeugt"], 13)
        self.assertEqual(b["gelaufen"], 2)
        self.assertEqual(b["verdraengt"], 11)


class TestWasNichtAlsVerdraengt_zaehlt(unittest.TestCase):
    def test_ein_lauf_der_gerade_wartet_ist_nicht_verdraengt(self):
        """`queued` heisst „steht noch an", nicht „ist gestorben". Ihn mitzuzählen würde die
        Zahl bei jedem Lauf um eins zu hoch machen — genau die Sorte stiller Drift, gegen die
        diese Messung gebaut ist."""
        rows = [_lauf(T % (21, 0), started=T % (21, 0)),
                _lauf(T % (21, 1), status="queued", conclusion=None)]
        self.assertEqual(R.erzeugungs_bilanz(rows)["verdraengt"], 0)

    def test_ein_fehlgeschlagener_lauf_ist_gelaufen(self):
        rows = [_lauf(T % (21, h), started=T % (21, h), conclusion="failure") for h in (0, 6)]
        b = R.erzeugungs_bilanz(rows)
        self.assertEqual(b["gelaufen"], 2)
        self.assertEqual(b["verdraengt"], 0)


class TestDieRate(unittest.TestCase):
    def test_erzeugt_pro_tag(self):
        rows = [_lauf(T % (21, h), started=T % (21, h)) for h in range(0, 24, 2)]  # 12 in 22h
        b = R.erzeugungs_bilanz(rows)
        self.assertEqual(b["spanneH"], 22.0)
        self.assertEqual(b["erzeugtProTag"], 13.1)


class TestNichtsIstNichtNull(unittest.TestCase):
    """None heisst „nicht abgefragt", nie „null Laeufe" — der Unterschied ist der ganze Zweck."""

    def test_leer(self):
        for x in (None, [], [{}], [{"created": None}]):
            self.assertIsNone(R.erzeugungs_bilanz(x))

    def test_ein_einziger_lauf_gibt_keine_spanne(self):
        self.assertIsNone(R.erzeugungs_bilanz([_lauf(T % (21, 0), started=T % (21, 0))]))

    def test_unlesbare_zeitstempel_kippen_es_nicht(self):
        self.assertIsNone(R.erzeugungs_bilanz([_lauf("kein Datum"), _lauf("auch nicht")]))


class TestDerAbruf(unittest.TestCase):
    def test_er_liest_die_felder_die_zaehlen(self):
        antwort = {"workflow_runs": [
            {"created_at": T % (21, 0), "run_started_at": T % (21, 0),
             "status": "completed", "conclusion": "success"},
            {"created_at": T % (21, 1), "run_started_at": None,
             "status": "completed", "conclusion": "cancelled"}]}
        rows = R.hole_erzeugte("a/b", 42, "t", fetch=lambda u: antwort)
        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[1]["started"])
        self.assertEqual(R.erzeugungs_bilanz(rows)["verdraengt"], 1)

    def test_er_fragt_nur_nach_schedule_laeufen(self):
        """Ein `workflow_dispatch` von Hand darf die Taktung nicht schoenrechnen."""
        gesehen = []

        def _fetch(u):
            gesehen.append(u)
            return {"workflow_runs": []}

        R.hole_erzeugte("a/b", 42, "t", fetch=_fetch)
        self.assertIn("event=schedule", gesehen[0])
        self.assertIn("/actions/workflows/42/runs", gesehen[0])


if __name__ == "__main__":
    unittest.main()
