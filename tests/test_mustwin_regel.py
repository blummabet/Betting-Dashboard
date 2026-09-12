"""Die mustWin-Regel steht an EINER Stelle — und der Validator kennt sie.

🔴 12.09.2026 (Lucas, Plattform-Audit). `calc_pressure()` setzt `mustWin = pressureRatio > 0.65`.
`update_dashboard.py` schraenkt das beim Bauen des Stakes noch einmal ein:

    "mustWin": h_pressure.get("mustWin", False) and h_motiv == 'full'

— weil bestaetigte ('none') und praktisch erledigte ('low') Teams nicht mit Must-Win-Intensitaet
spielen. Sinnvoll, dokumentiert, absichtlich.

Nur: `check_picks_logic.py` kannte die Einschraenkung nicht und meldete jeden solchen Fall als
**Fehler in calc_pressure**. Gemessen am echten Datenstand: **53 Faelle, ALLE mit
motivationLevel='low'** — 53 Fehlalarme, kein einziger echter Fund.

Warum das nicht harmlos ist: es waere der erste Befund gewesen, den die frisch angeschlossene
Validator-Karte in der Status-Uebersicht gezeigt haette. 26 rote Fehler, die keine sind. Genau so
wird ein Waechter abgeschaltet — und dann findet er auch die echten nicht mehr.

Fehlerklasse: **eine Regel, die zwei Module unabhaengig kennen muessen, driftet.** Sie steht
deshalb in `mustwin_regel.py`, und beide Seiten fragen dort nach.
"""
import re
import unittest
from pathlib import Path

import check_picks_logic as CPL
import mustwin_regel as MWR

WURZEL = Path(__file__).resolve().parent.parent


class TestRegel(unittest.TestCase):
    def test_mustwin_nur_bei_voller_motivation(self):
        self.assertTrue(MWR.mustwin_setzen(True, "full"))
        for lage in ("low", "none"):
            self.assertFalse(MWR.mustwin_setzen(True, lage),
                             f"motivationLevel='{lage}' darf kein Must-Win ergeben")

    def test_fehlende_motivation_gilt_als_voll(self):
        """Konservativ in die sichtbare Richtung: lieber ein Befund zu viel als eine stumme
        Unterdrueckung, nur weil ein Feld fehlt."""
        self.assertTrue(MWR.mustwin_setzen(True, None))

    def test_widerspruch_nur_wenn_mustwin_ueberhaupt_erlaubt_waere(self):
        self.assertTrue(MWR.widerspruch(0.83, False, "full"),
                        "bei voller Motivation ist hoher Druck ohne mustWin ein echter Fehler")
        for lage in ("low", "none"):
            self.assertFalse(MWR.widerspruch(0.83, False, lage),
                             f"bei '{lage}' ist genau das der gewollte Zustand")

    def test_kein_widerspruch_unterhalb_der_schwelle_oder_mit_flag(self):
        self.assertFalse(MWR.widerspruch(0.60, False, "full"))
        self.assertFalse(MWR.widerspruch(0.83, True, "full"))
        self.assertFalse(MWR.widerspruch(None, False, "full"), "fehlende Daten sind kein Befund")


class TestBeideSeitenBenutzenDieRegel(unittest.TestCase):
    def test_das_dashboard_baut_den_stake_ueber_die_regel(self):
        quelle = (WURZEL / "update_dashboard.py").read_text(encoding="utf-8")
        self.assertEqual(quelle.count("mustwin_regel.mustwin_setzen("), 2,
                         "Heim- UND Auswaerts-Stake muessen ueber die Regel gehen")
        self.assertNotIn("get(\"mustWin\", False) and h_motiv == 'full'", quelle,
                         "die Bedingung steht wieder ausgeschrieben im Dashboard")

    def test_der_validator_fragt_die_regel_statt_sie_zu_wiederholen(self):
        quelle = (WURZEL / "check_picks_logic.py").read_text(encoding="utf-8")
        self.assertIn("MWR.widerspruch(pr, mw, mot)", quelle)
        self.assertNotIn("if pr is not None and pr > 0.65 and not mw:", quelle,
                         "die Bedingung steht wieder ausgeschrieben im Validator")


class TestAmEchtenDatenstand(unittest.TestCase):
    """Der Test, der den Fund ueberhaupt erst gemacht hat. Ohne echte Daten haette jede
    ausgedachte Zeile hier gepasst."""

    @classmethod
    def setUpClass(cls):
        cls.ligen = CPL.parse_leagues_from_html(str(WURZEL / "season-finish.html")) or {}

    def _stakes(self):
        for key, lg in self.ligen.items():
            for fx in (lg.get("fixtures") or []):
                for seite in ("homeStake", "awayStake"):
                    st = fx.get(seite)
                    if isinstance(st, dict):
                        yield key, fx, seite, st

    def test_es_gibt_die_faelle_wirklich(self):
        """Gegenprobe: gaebe es keine Zeile mit hohem Druck ohne mustWin, waere der Test unten
        gruen, weil nichts zu pruefen ist — und nicht, weil etwas stimmt."""
        hoch = [1 for _, _, _, st in self._stakes()
                if (st.get("pressureRatio") or 0) > 0.65 and not st.get("mustWin")]
        self.assertGreater(len(hoch), 10,
                           "Keine Faelle im Datenstand — dieser Test prueft gerade nichts.")

    def test_kein_einziger_dieser_faelle_ist_ein_echter_widerspruch(self):
        echte = [f"{key} {fx.get('home')} vs {fx.get('away')} ({seite}): "
                 f"pr={st.get('pressureRatio')} motiv={st.get('motivationLevel')}"
                 for key, fx, seite, st in self._stakes()
                 if MWR.widerspruch(st.get("pressureRatio"), st.get("mustWin"),
                                    st.get("motivationLevel"))]
        self.assertEqual(echte, [], "\nEchte Widersprueche (mustWin fehlt bei voller Motivation) — "
                         "die gehoeren in calc_pressure gefixt, nicht in der Regel:\n"
                         + "\n".join(echte))

    def test_der_alte_check_haette_hier_falsch_alarm_geschlagen(self):
        """Haelt die Groesse des Fehlers fest. Verschwindet der Effekt, ist entweder der
        Datenstand ausgetauscht oder die Unterdrueckung in update_dashboard weg — beides gehoert
        angeschaut, nicht stillschweigend hingenommen."""
        alt = [1 for _, _, _, st in self._stakes()
               if (st.get("pressureRatio") or 0) > 0.65 and not st.get("mustWin")]
        self.assertGreater(len(alt), 10,
                           "Der alte Check haette hier nichts mehr gemeldet — dann ist die "
                           "Begruendung dieses Tests nicht mehr die Lage im Repo.")


if __name__ == "__main__":
    unittest.main()
