"""Der Validator darf keine eigenen Kopien der Engine-Schwellen haben.

🔴 12.09.2026 (Lucas, Plattform-Audit). `check_picks_logic.py` trug sieben Konstanten und darueber
den Satz „SYNC:GATE — These values MUST match the GATE object in pick-engine.js". Sie haben nicht
gematcht: GOALS_REAL 0,12 statt 0,05 · RESULT_REAL 0,15 statt 0,05 · TEAM_REAL 0,12 statt 0,07 ·
CORN_REAL 0,10 statt 0,06 · CORN_EST 0,15 statt 0,10 · TEAM_EST 0,15 statt 0,12; BTTS_REAL und
CARD_EST fehlten ganz. Sechs von sieben zu weit.

Zwei Dinge dazu, weil die Schwere sonst groesser erzaehlt wird als sie war:

  1. Die Konstanten waren in KEINER Pruefung verdrahtet — sie standen nur in Kommentaren und
     Meldungstexten. Der Validator hat also keine Picks durchgelassen, er hat falsche Zahlen
     behauptet. Die davon ABGELEITETEN Flag-Schwellen (Karten 3.5/4.5) waren allerdings auf das
     alte, weite Gate gerechnet und haben deshalb eine Zone verschwiegen, in der die Engine
     laengst blockt: bei Quote 1,80 flaggte der Validator erst unter FV 40 %, richtig waeren
     50,6 % gewesen.
  2. Ein Sync-Vertrag, den nur ein Kommentar bewacht, ist kein Vertrag. Die Werte kommen jetzt zur
     Laufzeit aus pick-engine.js. Dieser Test haelt fest, dass das so bleibt — und dass ein nicht
     lesbarer GATE-Block LAUT abbricht statt still auf alte Zahlen zurueckzufallen.
"""
import re
import unittest
from pathlib import Path

import check_picks_logic as CPL

WURZEL = Path(__file__).resolve().parent.parent
ENGINE = WURZEL / "pick-engine.js"
VALIDATOR = WURZEL / "check_picks_logic.py"


def _gate_aus_js():
    quelle = ENGINE.read_text(encoding="utf-8")
    block = re.search(r"const GATE\s*=\s*\{(.*?)\n\};", quelle, re.S)
    assert block, "pick-engine.js: GATE-Block nicht gefunden"
    return {k: float(v) for k, v in
            re.findall(r"^\s*([A-Z_]+)\s*:\s*([0-9.]+)\s*,", block.group(1), re.M)}


class TestGateSync(unittest.TestCase):
    def test_der_validator_kennt_genau_die_gates_der_engine(self):
        js = _gate_aus_js()
        self.assertTrue(js, "keine Schwellen aus der Engine gelesen")
        self.assertEqual(CPL.GATES, js,
                         "Der Validator rechnet mit anderen Schwellen als die Engine. Genau das "
                         "war der Zustand vom 12.09.2026 — und der Kommentar daneben behauptete "
                         "das Gegenteil.")

    def test_alle_acht_gates_sind_da(self):
        """Vollstaendigkeit, nicht nur Gleichheit: BTTS_REAL und CARD_EST fehlten im Validator
        ueberhaupt, standen also in keiner der beiden Listen — ein Vergleich zweier Kopien haette
        das nie gefunden."""
        for pflicht in ("GOALS_REAL", "BTTS_REAL", "RESULT_REAL", "TEAM_REAL", "TEAM_EST",
                        "AH_REAL", "CORN_REAL", "CORN_EST", "CARD_EST"):
            self.assertIn(pflicht, CPL.GATES, f"{pflicht} fehlt")

    def test_keine_kopierte_schwelle_mehr_im_validator(self):
        """Die Fehlerklasse: eine zweite Zahl derselben Sache. Sobald wieder ein
        `GATE_IRGENDWAS = 0.12` im Validator steht, driftet es erneut."""
        quelle = VALIDATOR.read_text(encoding="utf-8")
        kopien = re.findall(r"^\s*GATE_[A-Z_]+\s*=\s*[0-9.]+", quelle, re.M)
        self.assertEqual(kopien, [], "\nKopierte Schwellen im Validator:\n" + "\n".join(kopien))

    def test_ein_unlesbarer_gate_block_bricht_laut_ab(self):
        """Gegenprobe, und die wichtigere: still auf alte Werte zurueckfallen waere derselbe
        Zustand wie vorher, nur schwerer zu finden."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write("// kein GATE-Block weit und breit\nconst ANDERES = { A: 1 };\n")
            pfad = fh.name
        with self.assertRaises(RuntimeError):
            CPL._gates_aus_engine(pfad)

    def test_die_karten_schwelle_wird_aus_dem_gate_gerechnet(self):
        """Der Teil mit echter Wirkung: die Flag-Schwelle haengt am Gate, nicht an einer Zahl im
        Code. Bei Gate 0,05 und typischer Quote 1,80 (impl. 55,6 %) flaggt der Validator unter
        50,6 % — vorher standen dort feste 40 %, gerechnet auf das alte Gate von 0,12."""
        quelle = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('_schwelle_c35 = _IMPL_C35 - GATES["GOALS_REAL"]', quelle)
        self.assertNotIn("if _fv_c35 < 0.40:", quelle, "wieder eine feste Zahl statt des Gates")
        erwartet = round(0.556 - CPL.GATES["GOALS_REAL"], 4)
        self.assertAlmostEqual(erwartet, 0.506, places=3,
                               msg="Die Engine hat ihr Gate geaendert — die Zahl im Kommentar "
                                   "dieses Tests gehoert mitgezogen.")


class TestValidatorUeberlebtEinKaputtesSpiel(unittest.TestCase):
    """🔴 Der schwerere Fund desselben Durchlaufs.

    Eine Partie ohne H2H-Schnitt hat den GANZEN Validator mit einem TypeError beendet — mitten in
    der Liste, also wurde alles danach nie geprueft. Die committete `validator_summary.json` ist
    deshalb vom **26.04.2026**: seit viereinhalb Monaten hat der Lauf nichts mehr geschrieben.
    Der echte Stand sind 107 Spiele mit 26 Fehlern, nicht 46 mit 3.

    Fehlerklasse: **ein Waechter, der stirbt, darf nicht aussehen wie einer, der nichts findet.**
    """

    def test_eine_partie_ohne_h2h_schnitt_beendet_den_lauf_nicht(self):
        quelle = (WURZEL / "check_picks_logic.py").read_text(encoding="utf-8")
        self.assertNotIn('f"Ø gpg={exp_goals_proxy:.2f}, H2H Ø={h2h_avg_g:.1f} Tore — "', quelle,
                         "h2h_avg_g darf None sein — jede andere Stelle in dieser Datei prueft das")

    def test_ein_absturz_wird_zum_befund_statt_zum_ende(self):
        quelle = (WURZEL / "check_picks_logic.py").read_text(encoding="utf-8")
        self.assertIn("VALIDATOR_ABSTURZ", quelle,
                      "Ohne Auffangen beendet eine einzige kaputte Partie den ganzen Lauf, und "
                      "nach aussen sieht das aus wie ein Validator, der nichts gefunden hat.")
        self.assertIn("issues = check_fixture(fx, key, lname, rl)", quelle)
        stelle = quelle.index("issues = check_fixture(fx, key, lname, rl)")
        self.assertIn("try:", quelle[max(0, stelle - 400):stelle],
                      "der Aufruf steht nicht in einem try-Block")


if __name__ == "__main__":
    unittest.main()
