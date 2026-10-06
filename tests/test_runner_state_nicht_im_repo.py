"""🔴 06.10.2026 (Lucas: „wieso funktioniert der mist nicht mehr, bricht immer an dieser Stelle").

Betfair 14:46 UTC: Beleg lokal committet, `git fetch` → „curl 28 Operation too slow", Push
abgelehnt, wieder und wieder. Dieselbe Stelle am 30.09., 01.10., 03.10. — jedes Mal wurde an der
Frist gedreht, nie an der Menge. Gemessen: ein Global-Scan-Commit schrieb ~47 MB Blobs neu, davon
~17 MB reine Zwischenstaende (poly_wallet_norm_state, poly_price_path), die keine Seite fetcht.
Jeder andere Mac-Lauf musste sie vor seinem Push abholen.

Diese Tests halten fest: (1) die zwei Zwischenstaende werden nicht mehr committet und nicht mehr
ins Repo geschrieben, (2) was der Global-Scan committet, hat ein Budget — eine Liste waechst still.
"""
import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import runner_state  # noqa: E402

WF = REPO / ".github" / "workflows" / "poly-global-scan.yml"
NUR_RUNNER = ("poly_wallet_norm_state.json", "poly_price_path.json")

# Was ein Global-Scan-Commit hoechstens umschreiben darf (Summe der Dateigroessen in der
# Commit-Liste). Nach dem Fix ~30 MB; 40 laesst Wachstum zu, schlaegt aber an, bevor wieder
# ~47 MB je halbe Stunde durch jede Mac-Leitung muessen.
COMMIT_BUDGET_MB = 40


def _commit_liste():
    src = WF.read_text(encoding="utf-8")
    m = re.search(r"for f in \\\n(.*?);\s*do", src, re.S)
    assert m, "Commit-Schleife im Global-Scan nicht gefunden"
    return m.group(1).replace("\\\n", " ").split()


def test_zwischenstaende_werden_nicht_committet():
    liste = _commit_liste()
    for f in NUR_RUNNER:
        assert f not in liste, f"{f} ist reiner Runner-Zwischenstand und gehoert nicht in den Commit"


def test_commit_liste_hat_ein_budget():
    mb = sum(os.path.getsize(REPO / f) for f in _commit_liste() if (REPO / f).exists()) / 1e6
    assert mb <= COMMIT_BUDGET_MB, (
        f"Global-Scan committet {mb:.0f} MB je Lauf > {COMMIT_BUDGET_MB} MB — jeder andere "
        f"Mac-Lauf muss das vor seinem Push abholen (06.10.2026: curl 28, Push abgelehnt).")


def test_price_path_schreibt_in_den_runner_stand(tmp_path, monkeypatch):
    import poly_price_path as P
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "poly_money_upcoming.json").write_text("{}", encoding="utf-8")
    (repo / "poly_money_broad_close.json").write_text("{}", encoding="utf-8")
    (repo / "poly_price_path.json").write_text('{"alt": {"points": []}}', encoding="utf-8")
    vorher = (repo / "poly_price_path.json").read_text(encoding="utf-8")
    monkeypatch.setattr(P, "BASE", repo)
    monkeypatch.setenv("COCOBET_STATE_DIR", str(tmp_path / "state"))
    P.main()
    assert (tmp_path / "state" / "poly_price_path.json").exists()
    assert (repo / "poly_price_path.json").read_text(encoding="utf-8") == vorher, \
        "Repo-Fassung darf nicht mehr angefasst werden"


def test_wallet_norm_schreibt_state_in_den_runner_stand():
    src = (REPO / "poly_wallet_norm.py").read_text(encoding="utf-8")
    assert "_schreibe(STATE_FILE" not in src
    assert "runner_state.schreiben(STATE_FILE.name" in src


class TestLesen:
    def test_runner_stand_gewinnt(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COCOBET_STATE_DIR", str(tmp_path / "s"))
        (tmp_path / "x.json").write_text('{"q": "repo"}', encoding="utf-8")
        runner_state.schreiben("x.json", {"q": "runner"})
        assert runner_state.lesen("x.json", tmp_path) == {"q": "runner"}

    def test_repo_fassung_ist_startwert(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COCOBET_STATE_DIR", str(tmp_path / "s"))
        (tmp_path / "x.json").write_text('{"q": "repo"}', encoding="utf-8")
        assert runner_state.lesen("x.json", tmp_path) == {"q": "repo"}

    def test_nichts_da_gibt_standard(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COCOBET_STATE_DIR", str(tmp_path / "s"))
        assert runner_state.lesen("x.json", tmp_path, {"leer": 1}) == {"leer": 1}

    def test_kaputter_runner_stand_faellt_auf_repo(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COCOBET_STATE_DIR", str(tmp_path / "s"))
        runner_state.state_dir()
        (tmp_path / "s" / "x.json").write_text('{"kaputt', encoding="utf-8")
        (tmp_path / "x.json").write_text('{"q": "repo"}', encoding="utf-8")
        assert runner_state.lesen("x.json", tmp_path) == {"q": "repo"}
