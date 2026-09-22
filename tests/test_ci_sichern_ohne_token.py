#!/usr/bin/env python3
"""
tests/test_ci_sichern_ohne_token.py — 21.09.2026.

🔴 Lucas: „das kam als Fehler" —

    [main 696aaed199] 🔐 🧾 Wallet-Verlauf aus der Git-Historie nachgetragen
     3 files changed, 3 insertions(+), 3 deletions(-)
    scripts/ci_sichern.sh: line 42: GITHUB_TOKEN: unbound variable
    Error: Process completed with exit code 1.

Der Commit war da, der Push nie — und weil der Runner danach verschwindet, war die ganze Arbeit
weg. Schuld war `${GITHUB_TOKEN}` blank unter `set -u`. Auf dem self-hosted Mac steht die
Variable in der Runner-Umgebung, also lief es dort seit Wochen; der erste Lauf auf
`ubuntu-latest` fiel darueber. Gebraucht wird sie gar nicht: `actions/checkout` legt den Token
als `http.extraheader` in die lokale Git-Config.

Fehlerklasse: **eine Abhaengigkeit, die nirgends steht und nur dort auffaellt, wo sie fehlt.**

Der Test bildet genau diese Umgebung nach: ein Repo, eine Datei, KEIN GITHUB_TOKEN.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


_CACHE = {}


def _lauf(mit_token: bool):
    """Gecacht — der Push-Versuch des Skripts laeuft in seine eigenen Retries, das dauert."""
    if mit_token not in _CACHE:
        _CACHE[mit_token] = _lauf_wirklich(mit_token)
    return _CACHE[mit_token]


def _lauf_wirklich(mit_token: bool):
    umgebung = {k: v for k, v in os.environ.items()
                if k not in ("GITHUB_TOKEN", "GITHUB_REPOSITORY")}
    umgebung["HOME"] = umgebung.get("HOME", "/tmp")
    if mit_token:
        umgebung["GITHUB_TOKEN"] = "gh-test"
        umgebung["GITHUB_REPOSITORY"] = "a/b"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "scripts").mkdir()
        for n in ("ci_sichern.sh", "ci_pull.sh"):
            q = REPO / "scripts" / n
            if q.exists():
                shutil.copy(q, p / "scripts" / n)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=p, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=p, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=p, check=True)
        (p / "erste.txt").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=p, check=True)
        subprocess.run(["git", "commit", "-qm", "start"], cwd=p, check=True)
        (p / "beleg.json").write_text('{"a": 1}')
        r = subprocess.run(["bash", "scripts/ci_sichern.sh", "Test", "beleg.json"],
                           cwd=p, env=umgebung, capture_output=True, text=True, timeout=90)
        commits = subprocess.run(["git", "log", "--oneline"], cwd=p,
                                 capture_output=True, text=True).stdout
    return r, commits


class TestOhneTokenLaeuftEsTrotzdem(unittest.TestCase):
    def test_kein_unbound_variable(self):
        """⭐ Der eigentliche Fall. Ohne diesen Riegel faellt es erst im Betrieb auf — und dann
        ist der Commit weg."""
        r, _ = _lauf(mit_token=False)
        self.assertNotIn("unbound variable", r.stdout + r.stderr,
                         "das Skript verlangt eine Variable, die es nicht deklariert")

    def test_es_endet_nicht_hart(self):
        """Der Kopf des Skripts sagt: „Faellt NIE hart aus." Ein Exit 1 riss den ganzen Lauf mit."""
        r, _ = _lauf(mit_token=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_der_beleg_ist_committet(self):
        """Der Zweck des Skripts — ohne Remote kann es nicht pushen, committen schon."""
        _, commits = _lauf(mit_token=False)
        self.assertIn("Test", commits)

    def test_mit_token_bleibt_alles_wie_vorher(self):
        """Die Gegenprobe: der Weg ueber den Token darf nicht kaputtgegangen sein."""
        r, commits = _lauf(mit_token=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Test", commits)


class TestKeinSkriptVerlangtEineUndeklarierteVariable(unittest.TestCase):
    """Die Klasse statt der Instanz: unter `set -u` ist jede blanke `${VAR}` eine Wette darauf,
    dass der Runner sie zufaellig setzt."""

    ERLAUBT = {"GRUND", "ETWAS", "BRANCH"}

    def test_keine_blanke_umgebungsvariable_unter_set_u(self):
        import re
        fehler = []
        for sh in sorted((REPO / "scripts").glob("*.sh")):
            roh = sh.read_text(encoding="utf-8", errors="ignore")
            if not re.search(r"^set -[a-z]*u", roh, re.M):
                continue
            # Kommentare sind kein Verhalten — sonst schlaegt der Waechter an der ERKLAERUNG an,
            # warum es die Variable nicht mehr blank gibt. (Dieselbe Lehre wie `nur_code` in
            # tests/test_tote_quellen.py.)
            zeilen = [("" if z.lstrip().startswith("#") else z) for z in roh.split("\n")]
            t = "\n".join(zeilen)
            eigen = set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=", t, re.M)) | self.ERLAUBT
            # Wer irgendwo `${NAME:-…}` schreibt, hat den Fall bedacht.
            eigen |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):", t))
            for m in re.finditer(r"\$\{([A-Z][A-Z0-9_]*)\}", t):
                name = m.group(1)
                if name in eigen:
                    continue
                zeile = t[:m.start()].count("\n") + 1
                fehler.append("%s:%d: ${%s} ohne :- und ohne Zuweisung" % (sh.name, zeile, name))
        self.assertEqual(fehler, [], "\n".join(fehler))

    def test_die_regel_faengt_den_echten_fall(self):
        """⭐ Gegenprobe: hier steht der Fehler vom 21.09. als Schnipsel. Faellt dieser Test,
        ist der Waechter blind."""
        import re
        t = ('set -uo pipefail\n'
             'git remote set-url origin "https://x:${GITHUB_TOKEN}@github.com/x.git"\n')
        eigen = set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=", t, re.M))
        eigen |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):", t))
        treffer = [m.group(1) for m in re.finditer(r"\$\{([A-Z][A-Z0-9_]*)\}", t)
                   if m.group(1) not in eigen]
        self.assertEqual(treffer, ["GITHUB_TOKEN"])


if __name__ == "__main__":
    unittest.main()
