#!/usr/bin/env python3
"""03.09.2026 — Lucas: „ein poly scan von vorhin ging schief".

Der Lauf um 05:09 UTC committete lokal und kam dann fuenfmal nicht durch:

    error: The following untracked working tree files would be overwritten by merge:
            wm_poly_slugs.json
    Aborting → Merge with strategy ort failed → push rejected (non-fast-forward)

`--autostash` legt nur GETRACKTE Aenderungen weg. Eine untrackte Datei, die der eingehende
Commit NEU mitbringt, blockiert den Merge. Und der Grund, warum ausgerechnet jetzt eine solche
Datei auftauchte, ist unser eigener Fix vom 02.09.: `wm_poly_slugs.json` schreibt
fetch_wm_poly_prices.py seit jeher, committet wurde sie nie — die Registry-Staging-Zeile war die
zerschredderte Kommando-Substitution. Seit deren Reparatur landet die Datei erstmals auf origin,
und auf jedem Runner, der sie schon einmal erzeugt hatte, liegt sie untracked im Weg.

Ein Fix hat einen zweiten Fehler freigelegt, der die ganze Zeit da war. Diese Tests halten die
Loesung fest — und vor allem, dass sie nichts wegraeumt, was ihr nicht gehoert.
"""
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKRIPT = os.path.join(REPO, "scripts", "ci_pull.sh")


def _sh(befehl, cwd):
    return subprocess.run(befehl, shell=True, cwd=cwd, capture_output=True, text=True)


class _Welt(unittest.TestCase):
    """Zwei Klone eines Bare-Repos: A ist „unser Runner", B spielt die anderen Jobs."""

    def setUp(self):
        if sys.platform.startswith("win"):
            self.skipTest("Shell-Skript")
        self.tmp = tempfile.mkdtemp()
        r = os.path.join(self.tmp, "remote.git")
        _sh(f"git init -q --bare {r} && git -C {r} symbolic-ref HEAD refs/heads/main", self.tmp)
        self.A = os.path.join(self.tmp, "A")
        _sh(f"git init -q A", self.tmp)
        _sh("git config user.email t@t && git config user.name T && "
            "git symbolic-ref HEAD refs/heads/main && echo a > a.txt && git add a.txt && "
            f"git commit -qm init && git remote add origin {r} && git push -q origin main", self.A)
        self.B = os.path.join(self.tmp, "B")
        _sh(f"git clone -q {r} B", self.tmp)
        _sh("git config user.email t@t && git config user.name T", self.B)

    def _origin_bringt(self, name, inhalt):
        _sh(f"echo {inhalt} > {name} && git add {name} && "
            f"git commit -qm 'bringt {name}' && git push -q origin main", self.B)

    def _pull(self):
        # Anfuehrungszeichen sind Pflicht: der Repo-Pfad enthaelt ein Leerzeichen
        # („Betting Dashboard") — ohne sie startet bash /…/Betting und findet nichts.
        return _sh(f'bash "{SKRIPT}" main', self.A)

    def _inhalt(self, pfad):
        with open(os.path.join(self.A, pfad)) as f:
            return f.read().strip()


class UntrackteKollisionTest(_Welt):
    def test_der_alte_pull_scheitert_an_der_untrackten_datei(self):
        """Vorbedingung — ohne den Beweis, dass es kaputt WAR, sagt der Test unten nichts."""
        self._origin_bringt("kollision.json", "von-origin")
        _sh("echo lokal-untracked > kollision.json", self.A)
        r = _sh("git pull origin main --no-rebase -X ours --autostash 2>&1", self.A)
        self.assertIn("untracked working tree files would be overwritten", r.stdout + r.stderr)

    def test_das_skript_bringt_den_merge_durch(self):
        self._origin_bringt("kollision.json", "von-origin")
        _sh("echo lokal-untracked > kollision.json", self.A)
        r = self._pull()
        self.assertNotIn("Aborting", r.stdout + r.stderr)
        self.assertEqual(self._inhalt("kollision.json"), "von-origin")

    def test_die_lokale_fassung_wird_aufgehoben_nicht_geloescht(self):
        """Beiseite legen, nicht wegwerfen: der Runner-Stand bleibt nachvollziehbar."""
        self._origin_bringt("kollision.json", "von-origin")
        _sh("echo lokal-untracked > kollision.json", self.A)
        self._pull()
        self.assertEqual(self._inhalt(".ci_kollisionen/kollision.json"), "lokal-untracked")

    def test_auch_in_unterordnern(self):
        _sh("mkdir -p matches/data", self.B)
        self._origin_bringt("matches/data/x.json", "von-origin")
        _sh("mkdir -p matches/data && echo lokal > matches/data/x.json", self.A)
        r = self._pull()
        self.assertNotIn("Aborting", r.stdout + r.stderr)
        self.assertEqual(self._inhalt("matches/data/x.json"), "von-origin")


class NichtsAnfassenTest(_Welt):
    """Die andere Haelfte: das Skript darf nur Kollisionen anfassen, sonst nichts."""

    def test_ohne_kollision_bleibt_alles_liegen(self):
        _sh("echo behalte-mich > eigene_notiz.json", self.A)   # untracked, aber origin kennt sie nicht
        self._origin_bringt("anderes.json", "egal")
        self._pull()
        self.assertEqual(self._inhalt("eigene_notiz.json"), "behalte-mich")
        self.assertFalse(os.path.exists(os.path.join(self.A, ".ci_kollisionen")),
                         "es wurde etwas weggeraeumt, obwohl es keine Kollision gab")

    def test_getrackte_lokale_aenderung_gewinnt_wie_bisher(self):
        """`-X ours` bleibt `-X ours` — das Skript aendert die Merge-Strategie nicht."""
        self._origin_bringt("zweite.json", "von-origin")
        _sh("echo meine-fassung > zweite.json && git add zweite.json && "
            "git commit -qm lokal", self.A)
        self._pull()
        self.assertEqual(self._inhalt("zweite.json"), "meine-fassung")
        self.assertFalse(os.path.exists(os.path.join(self.A, ".ci_kollisionen")))

    def test_normaler_pull_ohne_irgendetwas_laeuft_durch(self):
        self._origin_bringt("neu.json", "inhalt")
        r = self._pull()
        self.assertNotIn("Aborting", r.stdout + r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.A, "neu.json")))


class WorkflowsNutzenDasSkriptTest(unittest.TestCase):
    """Damit der naechste Workflow nicht wieder am rohen `git pull` haengt."""

    def _workflows(self):
        import glob
        return sorted(glob.glob(os.path.join(REPO, ".github", "workflows", "*.yml")))

    def test_kein_workflow_ruft_git_pull_direkt(self):
        fehler = []
        for wf in self._workflows():
            for nr, z in enumerate(open(wf, encoding="utf-8").read().split("\n"), 1):
                s = z.strip()
                if s.startswith("#") or "git pull" not in s:
                    continue
                if "ci_pull.sh" in s:
                    continue
                fehler.append(f"{os.path.basename(wf)}:{nr}: {s}")
        self.assertEqual(fehler, [], "\nDiese Zeilen scheitern wieder an untrackten Dateien:\n"
                         + "\n".join(fehler))

    def test_das_skript_wird_ueberhaupt_benutzt(self):
        """Gegenprobe: der Test oben waere auch gruen, wenn niemand mehr pullt."""
        treffer = sum(open(wf, encoding="utf-8").read().count("ci_pull.sh") for wf in self._workflows())
        self.assertGreaterEqual(treffer, 30, "die Pull-Zeilen sind verschwunden statt umgestellt")

    def test_die_ablage_ist_ignoriert(self):
        with open(os.path.join(REPO, ".gitignore"), encoding="utf-8") as f:
            self.assertIn(".ci_kollisionen", f.read(),
                          "sonst committet der naechste Lauf die beiseite gelegten Dateien mit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
