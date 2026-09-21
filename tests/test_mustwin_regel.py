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


class TestDieRegelAmEingefrorenenVorfall(unittest.TestCase):
    """🔴 21.09.2026 — die beiden Tests, die hier standen, waren seit Tagen rot in der Action.

    Sie verlangten mehr als zehn Zeilen mit hohem Druck ohne `mustWin` im ECHTEN Datenstand.
    Gemessen: am 20.09. abends fuenf, am 21.09. frueh null — die Zahl schwankt mit jedem Neubau
    von `season-finish.html`, und im September (Spieltag 3-5) gibt es kaum Tabellendruck. Der
    Test prueft damit das Wetter und nicht den Code.

    Fehlerklasse: ein Regressionstest, der an der Tageslage haengt. Er wird rot, ohne dass etwas
    kaputt ist — und dann wird Rot ueberlesen, auch dort, wo es zaehlt.

    Deshalb steht der Vorfall hier als FIXTURE: dieselbe Form wie die 53 Faelle vom 12.09.
    (hoher Druck, kein mustWin, motivationLevel 'low') plus der eine Fall, der ein echter
    Widerspruch WAERE. Damit haelt der Test die Regel fest, unabhaengig vom Spieltag.
    """

    # Die Form des Vorfalls vom 12.09.2026: 53 Zeilen, ALLE mit motivationLevel 'low'.
    FALSCHALARME = [{"pressureRatio": 0.83, "mustWin": False, "motivationLevel": "low"},
                    {"pressureRatio": 0.71, "mustWin": False, "motivationLevel": "low"},
                    {"pressureRatio": 0.95, "mustWin": False, "motivationLevel": "none"}]
    # Und der Fall, der wirklich einer waere: volle Motivation, Druck ueber der Schwelle,
    # trotzdem kein mustWin. Den soll die Regel fangen.
    ECHTER = {"pressureRatio": 0.83, "mustWin": False, "motivationLevel": "full"}

    def test_die_53_falschalarme_sind_keine_widersprueche(self):
        for st in self.FALSCHALARME:
            self.assertFalse(
                MWR.widerspruch(st["pressureRatio"], st["mustWin"], st["motivationLevel"]),
                f"motivationLevel={st['motivationLevel']!r} unterdrueckt mustWin absichtlich — "
                "das ist kein Fehler in calc_pressure")

    def test_der_echte_widerspruch_wird_gefangen(self):
        """Gegenprobe — ohne sie waere der Test oben auch gruen, wenn `widerspruch` immer
        False zurueckgaebe."""
        self.assertTrue(MWR.widerspruch(self.ECHTER["pressureRatio"], self.ECHTER["mustWin"],
                                        self.ECHTER["motivationLevel"]))

    def test_unter_der_schwelle_ist_nie_ein_widerspruch(self):
        self.assertFalse(MWR.widerspruch(0.40, False, "full"))


class TestAmEchtenDatenstand(unittest.TestCase):
    """Die Live-Probe. Sie darf NICHT rot werden, wenn der Datenstand gerade duenn ist — sie
    ueberspringt dann und sagt es. Ein Rot, das „heute ist September" bedeutet, macht Rot
    wertlos.

    Die Regel selbst haelt die Klasse darueber fest, an einer eingefrorenen Fixture.
    """

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

    def _kandidaten(self):
        return [x for x in self._stakes()
                if (x[3].get("pressureRatio") or 0) > 0.65 and not x[3].get("mustWin")]

    def test_kein_einziger_dieser_faelle_ist_ein_echter_widerspruch(self):
        kand = self._kandidaten()
        if not kand:
            self.skipTest("kein Fall mit hohem Druck ohne mustWin im aktuellen Datenstand "
                          "(%d Stake-Zeilen) — die Regel prueft die Fixture-Klasse oben"
                          % sum(1 for _ in self._stakes()))
        echte = [f"{key} {fx.get('home')} vs {fx.get('away')} ({seite}): "
                 f"pr={st.get('pressureRatio')} motiv={st.get('motivationLevel')}"
                 for key, fx, seite, st in kand
                 if MWR.widerspruch(st.get("pressureRatio"), st.get("mustWin"),
                                    st.get("motivationLevel"))]
        self.assertEqual(echte, [], "\nEchte Widersprueche (mustWin fehlt bei voller Motivation) — "
                         "die gehoeren in calc_pressure gefixt, nicht in der Regel:\n"
                         + "\n".join(echte))


if __name__ == "__main__":
    unittest.main()
