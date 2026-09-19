#!/usr/bin/env python3
"""tests/test_ci_keine_marker.py — 19.09.2026

Lucas: „Heut kein einziger polymarket Push in public (kann nicht sein)."

Konnte sehr wohl sein. Der Lauf „🐋 Poly Global-Scan 18:05 UTC" hatte 15 Poly-Artefakte MIT
Git-Konfliktmarkern committet — `<<<<<<< Updated upstream`, die Sprache von `git stash pop`,
also vom `--autostash` im Push-Retry. Die Dateien waren danach kein JSON mehr, jeder Leser bekam
still ein leeres Dict, und die Poly-Seite schwieg drei Stunden ohne einen roten Lauf. Zwei
Stunden spaeter war derselbe Schaden wieder da — die Schleife laeuft von allein.

scripts/ci_keine_marker.sh ist der Griff dagegen. Er muss GENAU den Fall koennen, an dem der
erste Entwurf gescheitert ist: der Schaden steckt nicht nur in der Arbeitskopie, sondern schon
im COMMIT. Dann reicht `git checkout HEAD -- f` nicht, dann muss die Historie zurueckgelaufen
werden.
"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

SKRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ci_keine_marker.sh"

# Der Marker steht GANZ OBEN und danach folgen ~300 kB Fuellung. Das ist Absicht und der Kern
# des Tests: `grep -q` steigt beim ersten Treffer aus, und erst wenn danach noch genug Daten in
# der Pipe stecken (> Puffer, 64 kB), stirbt `git show` wirklich an SIGPIPE. Mit einer kleinen
# Datei laeuft der fehlerhafte Entwurf zufaellig richtig — genau deshalb hat der Fehler am
# 19.09. zwoelf echte Artefakte erwischt und waere an einem Mini-Fixture nie aufgefallen.
_FUELLUNG = ",\n".join('  "f%05d": %d' % (i, i) for i in range(12000))
KAPUTT = '''{
<<<<<<< Updated upstream
  "a": 1,
=======
  "a": 2,
>>>>>>> Stashed changes
%s
}
''' % _FUELLUNG


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


class TestDerGriffGegenKonfliktmarker(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        _git("init", "-q", "-b", "main", cwd=self.repo)
        _git("config", "user.email", "t@t", cwd=self.repo)
        _git("config", "user.name", "T", cwd=self.repo)
        os.makedirs(self.repo / "scripts", exist_ok=True)
        (self.repo / "scripts" / "ci_keine_marker.sh").write_text(
            SKRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        self.gut = {"a": 1, "b": 2, "c": [3, 4]}
        (self.repo / "artefakt.json").write_text(json.dumps(self.gut), encoding="utf-8")
        _git("add", "-A", cwd=self.repo)
        _git("commit", "-q", "-m", "gute Fassung", cwd=self.repo)

    def _lauf(self):
        return subprocess.run(["bash", "scripts/ci_keine_marker.sh"], cwd=self.repo,
                              capture_output=True, text=True)

    def test_ohne_marker_sagt_er_nichts_und_faellt_nicht(self):
        r = self._lauf()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_marker_nur_in_der_arbeitskopie_werden_geheilt(self):
        (self.repo / "artefakt.json").write_text(KAPUTT, encoding="utf-8")
        r = self._lauf()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads((self.repo / "artefakt.json").read_text()), self.gut)

    def test_marker_die_schon_im_COMMIT_stecken_werden_auch_geheilt(self):
        """🔴 Genau der Fall vom 19.09. — und genau der, den der erste Entwurf verfehlt hat.

        `grep -q` in einer Pipe steigt beim ersten Treffer aus, `git show` stirbt an SIGPIPE, und
        mit `set -o pipefail` wird der Pipe-Status 141 statt 0. Die Pruefung drehte sich damit
        um: sie meldete „sauber" GENAU dann, wenn Marker da waren, und schrieb fuer zwoelf
        Dateien „geheilt aus HEAD", waehrend sich nichts geaendert hatte."""
        (self.repo / "artefakt.json").write_text(KAPUTT, encoding="utf-8")
        _git("add", "-A", cwd=self.repo)
        _git("commit", "-q", "-m", "Schaden committet", cwd=self.repo)
        r = self._lauf()
        self.assertEqual(r.returncode, 0)
        inhalt = (self.repo / "artefakt.json").read_text()
        self.assertNotIn("<<<<<<< ", inhalt)
        self.assertEqual(json.loads(inhalt), self.gut)
        self.assertIn("geheilt aus", r.stdout)

    def test_ohne_jede_saubere_fassung_sagt_er_das_statt_still_zu_behaupten(self):
        neu = self.repo / "nie_gut.json"
        neu.write_text(KAPUTT, encoding="utf-8")
        _git("add", "-A", cwd=self.repo)
        _git("commit", "-q", "-m", "von Anfang an kaputt", cwd=self.repo)
        r = self._lauf()
        self.assertEqual(r.returncode, 0)
        self.assertIn("KEINE saubere Fassung", r.stdout)
        self.assertIn("von Hand ansehen", r.stdout)

    def test_er_kippt_den_lauf_nie(self):
        """Ein Waechter darf den Lauf nicht kippen, den er schuetzt."""
        (self.repo / "artefakt.json").write_text(KAPUTT, encoding="utf-8")
        self.assertEqual(self._lauf().returncode, 0)
        self.assertEqual(self._lauf().returncode, 0)   # auch beim zweiten Mal


if __name__ == "__main__":
    unittest.main()
