"""tests/test_stake_workflow_rollout.py — 07.09.2026

Lucas: „im Spielklasse Tab steht nur das [der Block fehlt] ... hab Stake sogar die action
laufen lassen nach dem push."

Und genau so war es. Der Code war gepusht, die Tests grün, das Artefakt trotzdem alt: der
Workflow, der **🎰 Stake Radar** heisst, hat nur GESAMMELT. `stake_auswertung.json` — die
Datei, aus der jede Stake-Ansicht im Dashboard liest — entstand ausschliesslich in
`betfair.yml`. Wer nach einem Push von Hand nachladen will, greift zum Job mit dem passenden
Namen, und der tat nichts Sichtbares.

Das ist keine neue Fehlerklasse, sondern die bekannte **Rollout-Luecke**: ein Code-Fix wirkt
erst, wenn der Produzent neu gelaufen ist (04.09., Auffaelligkeits-Mass; 06.09.,
`polyKey`). Neu ist nur, wo sie sass — nicht im Code, sondern im Zuschnitt der Workflows.

Der Test macht die Lehre mechanisch: wer eine Datei anzeigt, muss sie auch erzeugen koennen.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"

# Artefakt -> (Produzent, Workflows die es erzeugen KOENNEN muessen)
# Bewusst kurz gehalten: nur die Dateien, bei denen ein Mensch nach einem Push von Hand
# nachladen wuerde, und nur die Workflows, deren NAME ihn dorthin fuehrt.
ERWARTET = {
    "stake_auswertung.json": ("stake_analyse.py", ["stake-radar.yml", "betfair.yml"]),
}


def _text(name):
    p = WF / name
    assert p.exists(), "Workflow fehlt: %s" % name
    return p.read_text(encoding="utf-8")


class StakeRollout(unittest.TestCase):
    def test_wer_das_artefakt_zeigt_muss_es_auch_erzeugen(self):
        fehler = []
        for artefakt, (produzent, workflows) in ERWARTET.items():
            for wf in workflows:
                t = _text(wf)
                if produzent not in t:
                    fehler.append("%s laeuft nicht in %s — ein Lauf von Hand aktualisiert "
                                  "%s dort also nicht" % (produzent, wf, artefakt))
                elif not re.search(r"\b%s\b" % re.escape(artefakt), t):
                    fehler.append("%s laeuft in %s, aber %s wird nie committet — das "
                                  "Ergebnis bleibt auf dem Runner liegen"
                                  % (produzent, wf, artefakt))
        self.assertEqual(fehler, [], "\n".join(fehler))

    def test_der_produzent_kennt_die_spielklassen_tabelle(self):
        """Die Ansicht lebt vom Block `randliga`; der entsteht nur, wenn stake_analyse.py
        stake_liga_stufe.py auch wirklich einbindet. Ohne diese Zeile laeuft alles gruen
        durch und die Flaeche bleibt leer — was Lucas am 07.09. gesehen hat."""
        t = (ROOT / "stake_analyse.py").read_text(encoding="utf-8")
        self.assertIn("import stake_liga_stufe", t)
        self.assertIn('"randliga"', t)

    def test_ein_fehlschlag_der_auswertung_kippt_das_sammeln_nicht(self):
        """Das Sammeln ist die knappe Ressource (Cloudflare, self-hosted Mac, 15-Minuten-
        Takt). Eine kaputte Auswertung darf den Lauf nicht abbrechen, bevor das Ledger
        committet ist — sonst kostet ein Anzeigefehler echte Datenpunkte."""
        t = _text("stake-radar.yml")
        zeile = [z for z in t.split("\n") if "stake_analyse.py" in z and "#" not in z.split("stake_analyse.py")[0]]
        self.assertTrue(zeile, "stake_analyse.py wird in stake-radar.yml nicht aufgerufen")
        self.assertTrue(any("||" in z for z in zeile),
                        "der Aufruf hat keinen Rueckfall — ein Fehler dort kostet die Sammlung")


if __name__ == "__main__":
    unittest.main()
