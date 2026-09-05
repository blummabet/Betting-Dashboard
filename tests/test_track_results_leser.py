#!/usr/bin/env python3
"""
05.09.2026 — die Betfair-Action starb mit `'str' object has no attribute 'get'`.

    killer_push.py:231  for r in (results or []) if r.get("matchId") ...

`betfair_track_results.json` liegt seit dem 01.09. im Spaltenformat
(`{fmt, basis, woerter, zeilen}`). Ueber ein Dict zu iterieren liefert seine SCHLUESSEL —
also Strings. Alle anderen Leser wurden damals umgestellt und tragen den Kommentar
„load() nimmt beide Formate"; `killer_push.py` als einziger nicht.

Kosten: abgerechnet wird VOR dem Senden, der Absturz nahm also den kompletten
Killer-Push mit — kein Signal, keine Abrechnung, kein seen-Update.

Die Klasse: **ein Formatwechsel ist erst fertig, wenn JEDER Leser ihn kennt.** Dieser Test
haelt fest, dass niemand die Datei mehr am Store vorbei liest.
"""
import re
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATEI = "betfair_track_results.json"


def _module_die_die_datei_lesen():
    out = []
    for p in sorted(BASE.glob("*.py")):
        if p.name.startswith("test_"):
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except OSError:
            continue
        # Nur echte Code-Zeilen, keine Kommentare/Docstring-Erwaehnungen.
        zeilen = [z for z in t.splitlines()
                  if DATEI in z and not z.lstrip().startswith("#")]
        if zeilen:
            out.append((p.name, t, zeilen))
    return out


class TestLeser(unittest.TestCase):
    def test_es_gibt_ueberhaupt_leser(self):
        self.assertTrue(_module_die_die_datei_lesen(), "kein Leser gefunden — Test wertlos")

    def test_niemand_liest_am_Store_vorbei(self):
        """Wer die Datei anfasst, muss den Store importieren. Der generische JSON-Leser
        liefert im neuen Format ein Dict, und darueber zu iterieren gibt Strings."""
        fehler = []
        for name, text, zeilen in _module_die_die_datei_lesen():
            liest = [z for z in zeilen if re.search(r"_load\s*\(|json\.load", z)]
            if not liest:
                continue
            if "betfair_track_store" not in text:
                fehler.append(f"{name}: liest {DATEI} ohne betfair_track_store")
        self.assertEqual(fehler, [], "; ".join(fehler))

    def test_killer_push_benutzt_den_store(self):
        """Der konkrete Vorfall."""
        t = (BASE / "killer_push.py").read_text(encoding="utf-8")
        self.assertIn("betfair_track_store", t)
        self.assertIn("_store.load", t)
        self.assertNotIn('_load(BASE / "betfair_track_results.json"', t)


class TestAbrechnungRobust(unittest.TestCase):
    def test_unerwartete_Form_stuerzt_nicht_ab(self):
        """Ein Absturz kostet den ganzen Push, weil VOR dem Senden abgerechnet wird.
        Offen lassen ist harmlos — der naechste Lauf holt es nach."""
        import killer_push as K
        led = [{"k": "1|Match Odds", "status": "offen", "win": None}]
        for kaputt in ({"fmt": 1, "zeilen": []}, "text", 42, None):
            out = K.ledger_abrechnen([dict(r) for r in led], results=kaputt)
            self.assertEqual(out[0]["status"], "offen", f"bei {kaputt!r}")

    def test_gepacktes_Format_wird_abgerechnet(self):
        import betfair_track_store as S
        import killer_push as K
        zeilen = [{"matchId": "1", "market": "Match Odds", "win": True,
                   "settledAt": "2026-09-05T17:00:00+00:00"}]
        gepackt = S.entpacken(S.packen(zeilen))
        led = [{"k": "1|Match Odds", "status": "offen", "win": None}]
        out = K.ledger_abrechnen(led, results=gepackt)
        self.assertEqual(out[0]["status"], "abgerechnet")
        self.assertIs(out[0]["win"], True)

    def test_Altformat_bleibt_lesbar(self):
        import killer_push as K
        led = [{"k": "1|Match Odds", "status": "offen", "win": None}]
        out = K.ledger_abrechnen(led, results=[{"matchId": "1", "market": "Match Odds", "win": False}])
        self.assertEqual(out[0]["status"], "abgerechnet")
        self.assertIs(out[0]["win"], False)


if __name__ == "__main__":
    unittest.main()
