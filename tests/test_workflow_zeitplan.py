"""tests/test_workflow_zeitplan.py — 30.08.2026

Beim Verschieben der Crons weg von der vollen Stunde waere fast ein stiller Bruch entstanden:
update-mls.yml schaltet einzelne Steps ueber `github.event.schedule == '0 19 * * *'` frei
(PRE-Match: Digest + Previews, POST-Match: Recap + Reviews). Aendert man den Cron und vergisst
diese Vergleiche, laeuft der Workflow weiter gruen — nur der Digest kommt nie wieder. Genau die
Sorte Fehler, die man erst Wochen spaeter am fehlenden Push bemerkt.

Dieser Waechter prueft repo-weit, dass jeder Schedule-Vergleich auf einen Cron zeigt, den es im
selben Workflow auch gibt. Auskommentierte Crons zaehlen mit: fetch-wm-data ist seit dem
20.07. bewusst winterisiert (WM beendet), der Vergleich dort soll ins Leere laufen.
"""
import glob
import re
import unittest
from pathlib import Path

WF = sorted((Path(__file__).parent.parent / ".github" / "workflows").glob("*.yml"))


def crons(text: str) -> set:
    # aktive UND auskommentierte Crons — letztere sind absichtlich stillgelegte Zeitplaene
    return set(re.findall(r"^\s*#?\s*- cron: '([^']+)'", text, re.M))


def geprueft(text: str) -> set:
    return set(re.findall(r"github\.event\.schedule == '([^']+)'", text))


class Zeitplan(unittest.TestCase):
    def test_kein_vergleich_zeigt_ins_leere(self):
        tot = []
        for f in WF:
            t = f.read_text(encoding="utf-8")
            fehlt = geprueft(t) - crons(t)
            if fehlt:
                tot.append(f"{f.name}: prueft {sorted(fehlt)}, geplant {sorted(crons(t))}")
        self.assertEqual(tot, [], "Steps haengen an einem Cron, den es nicht gibt:\n" + "\n".join(tot))

    def test_die_dichten_laeufe_starten_nicht_auf_der_vollen_stunde(self):
        # Beleg aus health/liga-odds-dense.json: mit '0 */2' waren die tatsaechlichen Abstaende
        # 4,93h · 3,10h · 4,18h · 6,36h · 7,17h — bei durchweg ok:true und null Fehlern. Die
        # Laeufe scheiterten nicht, sie wurden gar nicht erst gestartet. :00 ist repo-weit UND
        # GitHub-global die vollste Minute.
        for name in ("fetch-liga-odds-dense.yml", "fetch-mls-odds-dense.yml",
                     "update-liga.yml", "update-mls.yml"):
            t = (WF[0].parent / name).read_text(encoding="utf-8")
            for c in re.findall(r"^\s*- cron: '([^']+)'", t, re.M):
                self.assertNotEqual(c.split()[0], "0", f"{name}: Cron '{c}' startet auf :00")

    def test_pre_und_post_bleiben_unterscheidbar(self):
        # '11 7,19 * * *' waere EIN Cron fuer beide Slots — github.event.schedule koennte PRE
        # und POST dann nicht mehr trennen, und beide Zweige liefen zweimal taeglich.
        for name in ("update-liga.yml", "update-mls.yml"):
            t = (WF[0].parent / name).read_text(encoding="utf-8")
            cs = re.findall(r"^\s*- cron: '([^']+)'", t, re.M)
            self.assertEqual(len(cs), 2, name)
            for c in cs:
                self.assertNotIn(",", c.split()[1], f"{name}: '{c}' fasst beide Slots zusammen")
            self.assertEqual(len(set(cs)), 2, name)


class Nebenlaeufigkeit(unittest.TestCase):
    def test_der_volllauf_teilt_seine_gruppe_nicht_mit_dem_dichten_lauf(self):
        # 28.08.2026 fuer die Liga erkannt und behoben, fuer die MLS nie nachgezogen: ein
        # WARTENDER Lauf wird vom naechsten Ankoemmling GECANCELT, nicht verschoben. Der
        # seltenste Teilnehmer (der Volllauf mit Digest/Recap) ist damit strukturell der Verlierer.
        def gruppe(name):
            t = (WF[0].parent / name).read_text(encoding="utf-8")
            m = re.search(r"^\s*group: (\S+)", t, re.M)
            return m.group(1) if m else None
        for voll, dicht in (("update-liga.yml", "fetch-liga-odds-dense.yml"),
                            ("update-mls.yml", "fetch-mls-odds-dense.yml")):
            self.assertNotEqual(gruppe(voll), gruppe(dicht), f"{voll} und {dicht} teilen die Gruppe")


class Waechter(unittest.TestCase):
    def test_jeder_getaktete_liga_und_mls_workflow_meldet_seine_gesundheit(self):
        # Lucas: „was soll ich mir bei MLS in den Actions anschauen?" — bis 30.08. gab es nichts
        # zu sehen: run_health.py lief in beiden LIGA-Workflows, in keinem MLS-Workflow. Deshalb
        # existierte nie eine health/mls*.json und kein Mensch konnte sagen, ob ein Lauf
        # stattfand, scheiterte oder gecancelt wurde.
        for name in ("fetch-liga-odds-dense.yml", "update-liga.yml",
                     "fetch-mls-odds-dense.yml", "update-mls.yml"):
            t = (WF[0].parent / name).read_text(encoding="utf-8")
            self.assertIn("run_health.py", t, f"{name} hat keinen Gesundheits-Waechter")
            self.assertIn("actions: read", t, f"{name}: run_health.py braucht actions:read")


if __name__ == "__main__":
    unittest.main()
