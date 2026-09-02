"""`git add` in den Workflows — eine fehlende Datei darf nie den ganzen Lauf kosten.

🔴 02.09.2026, ZWEITES Mal dieselbe Falle. `git add a b c` staged **nichts**, sobald EIN Pfad nicht
existiert (`fatal: pathspec ... did not match any files`). Mit `2>/dev/null || true` bleibt der
Fehler unsichtbar; danach ist der Index leer, `git diff --cached --quiet` meldet „keine Änderung"
und der Lauf endet **grün**.

Am 01.09. um 22:30 UTC kamen drei neue Dateinamen in die Sammelzeile von `betfair.yml`, die es auf
dem Runner noch gar nicht gab (`punkte_state.json`, `punkte_ledger.json`, `vorregistrierung.json`,
`odds_sports.json`). Ergebnis: **sechs Stunden lang keine einzige aktualisierte Betfair-Datei**, bei
grünem Workflow und grüner Gesundheitsdatei. Erkennbar war es nur daran, dass ausgerechnet die drei
Dateien mit EIGENER `git add`-Zeile weiterliefen.

Dieser Test macht die Lehre mechanisch: **eine Datei pro `git add`.** Dann kostet eine fehlende
Datei genau sich selbst.
"""
import re
import unittest
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"
# `git add -A`, `git add .` und Glob-Muster sind bewusst erlaubt: die staged nicht selektiv und
# koennen an einem fehlenden Pfad nicht scheitern.
SAMMEL = re.compile(r"^\s*git add\s+(?P<args>[^\n]+)")


# `${{ matrix.ds }}` enthaelt Leerzeichen und ist trotzdem EIN Pfad — sonst meldet der Test
# Zeilen als Sammel-Adds, die gar keine sind (am 02.09. zweimal passiert).
AUSDRUCK = re.compile(r"\$\{\{[^}]*\}\}")


def _pfade(zeile):
    args = SAMMEL.match(zeile).group("args")
    args = args.split("2>")[0].split("|| true")[0].split("#")[0]
    args = AUSDRUCK.sub("§", args)
    return [a for a in args.split() if not a.startswith("-")]


class TestGitAddEinzeln(unittest.TestCase):
    def test_jede_git_add_zeile_nennt_hoechstens_eine_datei(self):
        fehler = []
        for wf in sorted(WF.glob("*.yml")):
            for nr, zeile in enumerate(wf.read_text(encoding="utf-8").split("\n"), 1):
                if not SAMMEL.match(zeile):
                    continue
                pfade = _pfade(zeile)
                if len(pfade) <= 1 or any(p in (".", "-A", "--all") for p in pfade):
                    continue
                fehler.append(f"{wf.name}:{nr} staged {len(pfade)} Pfade in EINER Zeile "
                              f"({pfade[0]} … {pfade[-1]}) — fehlt einer davon, staged git NICHTS "
                              f"und der Lauf endet gruen ohne Commit.")
        self.assertEqual(fehler, [], "\n" + "\n".join(fehler))

    def test_die_betfair_datei_addiert_ueberhaupt_etwas(self):
        """Gegenprobe: der Test oben waere auch dann gruen, wenn jemand alle git-add-Zeilen loescht."""
        txt = (WF / "betfair.yml").read_text(encoding="utf-8")
        self.assertGreaterEqual(txt.count("git add "), 20)
        for pflicht in ("betfair_prices.json", "betfair_consensus.json", "killer.json",
                        "freigabe.json", "betfair_track_results.json"):
            self.assertIn("git add %s" % pflicht, txt, f"{pflicht} wird nicht mehr committet")


class TestLedgerNieRohGelesen(unittest.TestCase):
    """Der zweite Fehler desselben Abends: `betfair_track_results.json` liegt seit dem 01.09. im
    kompakten Spaltenformat. Wer sie mit einem generischen `_load()` liest, bekommt ein DICT und
    iteriert beim naechsten `for x in results` dessen SCHLUESSEL — `'str' object has no attribute
    'get'`. Der Ledger wird ausschliesslich ueber `betfair_track_store.load()` gelesen."""

    ROH = re.compile(r"_load\(\s*[\"']betfair_track_results\.json[\"']")

    def test_kein_modul_liest_den_ledger_roh(self):
        wurzel = Path(__file__).resolve().parent.parent
        treffer = []
        for py in wurzel.glob("*.py"):
            for nr, z in enumerate(py.read_text(encoding="utf-8").split("\n"), 1):
                if self.ROH.search(z):
                    treffer.append(f"{py.name}:{nr}: {z.strip()}")
        self.assertEqual(treffer, [], "\nRoh gelesen statt ueber betfair_track_store.load():\n"
                         + "\n".join(treffer))


if __name__ == "__main__":
    unittest.main()


class TestGruenAberTot(unittest.TestCase):
    """Der Wächter für den Zustand, den `git add` erzeugt hat: Job läuft, Daten kommen nicht.

    Blosse Frische reicht dafür nicht — ein sechs Stunden alter Job mit sechs Stunden alten Daten
    ist ein Ausfall des Jobs (das meldet ein anderer Wächter). Der stille Commit-Fehler sieht
    anders aus: FRISCHER Job, ALTE Daten."""

    def _lauf(self, lauf_h, daten_h):
        from datetime import datetime, timedelta, timezone
        import wm_data_integrity as WDI
        now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
        def stempel(h):
            return (now - timedelta(hours=h)).isoformat()
        dateien = {"health/betfair.json": {"updatedAt": stempel(lauf_h)}}
        for f in ("betfair_prices.json", "betfair_consensus.json",
                  "betfair_track_record.json", "killer.json"):
            dateien[f] = {"generatedAt": stempel(daten_h)}
        echt, failed = WDI._lazy, set(WDI._LAZY_FAILED)
        WDI._lazy = lambda name: dateien.get(name, echt(name))
        WDI._LAZY_FAILED.discard("health/betfair.json")
        try:
            return next(c for c in WDI.run_checks({"groups": {}}, {}, {}, {}, now=now)
                        if c["id"] == "betfair_liefert")
        finally:
            WDI._lazy = echt
            WDI._LAZY_FAILED.clear(); WDI._LAZY_FAILED.update(failed)

    def test_der_waechter_deckt_beide_jobs_ab(self):
        """02.09.2026 zweimal in zwoelf Stunden: morgens Betfair (git add), abends Poly (andere
        Ursache, gleiche Signatur). Ein Fehlerbild, das sich wiederholt, verdient keine zweite
        Sonderloesung — deshalb eine Tabelle statt zwei kopierter Checks."""
        import wm_data_integrity as WDI
        ids = {c["id"] for c in WDI.run_checks({"groups": {}}, {}, {}, {})}
        self.assertIn("betfair_liefert", ids)
        self.assertIn("poly_global_liefert", ids)

    def test_frischer_job_mit_alten_daten_schlaegt_an(self):
        c = self._lauf(lauf_h=0.2, daten_h=6.0)
        self.assertFalse(c["ok"])
        self.assertIn("liefert NICHTS", c["failures"][0])

    def test_alles_frisch_ist_gruen(self):
        self.assertTrue(self._lauf(lauf_h=0.2, daten_h=0.3)["ok"])

    def test_alter_job_mit_alten_daten_ist_NICHT_dieser_fehler(self):
        """Das ist ein Job-Ausfall und gehört dem Lauf-Wächter — hier wäre es ein Fehlalarm."""
        self.assertTrue(self._lauf(lauf_h=9.0, daten_h=9.0)["ok"])
