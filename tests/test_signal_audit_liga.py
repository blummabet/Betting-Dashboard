"""tests/test_signal_audit_liga.py — 30.08.2026

Lucas: „Und die Signale sind alle richtig in den Ligen? Feuern und kalibrieren sich nach Spiel
und lernen?" Der Audit ergab: der Lern-Loop ist vollstaendig (31 von 31 abgerechneten Liga-Picks
im Ledger, Gewichte taeglich aktualisiert, Gewicht wirkt ueber weighted_score auf die
Conviction). Von 26 fuer die Liga aktiven Signalen feuerten aber nur 22 — und die vier stummen
hatten drei ganz verschiedene Ursachen. Genau diese Unterscheidung halten diese Tests fest,
damit „feuert nicht" nicht pauschal als kaputt oder pauschal als gewollt durchgeht.
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent


def _cfg():
    return json.loads((REPO / "cocobet_config.json").read_text(encoding="utf-8"))


def _disabled(profile: str) -> set:
    return set((_cfg()["profiles"].get(profile) or {}).get("disabled_signals") or [])


class Sperrliste(unittest.TestCase):
    def test_mls_travel_ist_in_der_liga_gesperrt(self):
        # Liest die MLS-Venue-Tabelle (Reise/Hoehe/Turf). In den Top-5 kann es per Konstruktion
        # nichts liefern, wurde aber bis 30.08.2026 je Pick ausgewertet.
        self.assertIn("mls_travel", _disabled("liga_default"))

    def test_mls_travel_bleibt_fuer_mls_aktiv(self):
        self.assertNotIn("mls_travel", _disabled("mls_default"),
                         "in der MLS ist es das ganze Signal")

    def test_stumme_aber_intakte_signale_bleiben_aktiv(self):
        # game_state_openness braucht ein Team ohne Ziel (Saisonende) — am 3. Spieltag gibt es das
        # nicht. betfair_coherence sucht Inkohaerenz in der Ue/U-Leiter; in den liquiden Top-5
        # liegt die groesste gemessene Abweichung bei 0,53pp gegen eine Schwelle von 4pp, in
        # duennen Ligen erreicht sie 11pp. Beide sind korrekt stumm, nicht kaputt — sie hier
        # wegzusperren wuerde sie genau dann kosten, wenn sie etwas taugen.
        d = _disabled("liga_default")
        self.assertNotIn("game_state_openness", d)
        self.assertNotIn("betfair_coherence", d)

    def test_kein_gesperrtes_signal_ohne_modul(self):
        # Ein Tippfehler in der Sperrliste sperrt nichts und faellt sonst nie auf.
        r = subprocess.run(
            [sys.executable, "-c",
             "from sharp_signals.registry import ACTIVE_SIGNALS;"
             "print('\\n'.join(s.name() for s in ACTIVE_SIGNALS))"],
            cwd=REPO, capture_output=True, text=True, timeout=90,
            env={**os.environ, "COCOBET_PROFILE": "wm2026"})
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        namen = set(r.stdout.split())
        for profil in ("liga_default", "mls_default", "wm2026"):
            for n in _disabled(profil):
                self.assertIn(n, namen, f"{profil}: '{n}' ist kein Signal-Name")


class Lernloop(unittest.TestCase):
    def test_gewicht_wirkt_auf_den_score(self):
        # Der geschlossene Kreis: Gewicht -> weighted_score -> combined_score_pp -> Conviction.
        # Ohne diese Zeile lernt der Loop zwar Gewichte, aber sie aendern nichts.
        src = (REPO / "sharp_signals" / "registry.py").read_text(encoding="utf-8")
        self.assertIn("result.score * w * result.confidence", src)

    def test_unbekanntes_signal_ist_neutral_nicht_stumm(self):
        from sharp_signals.registry import get_weight
        self.assertEqual(get_weight({}, "gibtsnochnicht"), 1.0)
        self.assertEqual(get_weight({"x": {"weight": None}}, "x"), 1.0)

    def test_der_lernlauf_haengt_in_den_liga_workflows(self):
        # 30.08.2026: update_signal_weights lief in update-liga/update-mls, aber NICHT in den
        # dense-Workflows, die ebenfalls Picks erzeugen. Das ist in Ordnung (die Gewichte sind
        # persistent und greifen beim naechsten Lauf) — aber irgendwo MUSS er laufen.
        wf = REPO / ".github" / "workflows"
        laeuft = [f.name for f in wf.glob("*.yml")
                  if "update_signal_weights.py" in f.read_text(encoding="utf-8")]
        self.assertTrue(any("liga" in n for n in laeuft), f"kein Liga-Workflow lernt: {laeuft}")
        self.assertTrue(any("mls" in n for n in laeuft), f"kein MLS-Workflow lernt: {laeuft}")


if __name__ == "__main__":
    unittest.main()
