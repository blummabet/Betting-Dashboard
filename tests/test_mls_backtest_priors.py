"""13.07.2026 — MLS-Backtest → Signal-Priors.

Lucas: „Backtest VOR dem Lineup-Watcher, weil 1) es gibt schon Daten aus dieser Saison und
2) wir starten in Runde 16 — da können wir nicht 10 Runden lang lernen."

WARUM: Signal-Gewichte starten bei 1.0 (= jedes Signal gleich vertrauenswürdig). Der Bayesian-Loop
korrigiert das erst nach ~30 aufgelösten Picks JE SIGNAL. Bei Start in Runde 16/34 wäre die halbe
Saison verlernt, bevor die Engine weiß, was in der MLS taugt. Der Backtest liefert Start-Gewichte
aus der Historie → der Loop beginnt informiert.

Kernpunkt für MLS: football-data.co.uk führt die MLS nicht → KEINE historischen Closing-Quoten.
Das ist verkraftbar, weil `build_priors` ausschließlich Trefferquote + Anzahl der Calls liest.
ROI/CLV bleiben im Report leer — ehrlich statt erfunden.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _unter(ds: str, code: str) -> str:
    env = {**os.environ, "COCOBET_DATASET": ds,
           "COCOBET_PROFILE": {"mls": "mls_default", "liga": "liga_default"}.get(ds, "wm2026")}
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, r.stderr[-400:]
    return r.stdout.strip()


class TestMlsImBacktest:
    def test_mls_ist_eine_bekannte_liga(self):
        import liga_backtest as B
        assert "MLS" in B.LEAGUES
        lid, fd = B.LEAGUES["MLS"]
        assert lid == 253, "API-Football league_id der MLS"
        assert fd is None, "football-data.co.uk führt die MLS nicht → kein CSV-Code"

    def test_ohne_csv_quelle_kein_absturz(self):
        """Der CSV-Fetch muss übersprungen werden, wenn es keine Quelle gibt — sonst stirbt der
        MLS-Backtest an einer 404 statt Priors zu liefern."""
        import inspect
        import liga_backtest as B
        src = inspect.getsource(B.main)
        assert "if fd_code:" in src, "CSV-Fetch muss an fd_code gebunden sein"

    def test_mls_lauf_mischt_keine_europaeischen_ligen_ein(self):
        """Sonst primen wir die MLS-Gewichte mit Premier-League-Ergebnissen — exakt die
        Cross-Dataset-Kontamination, die wir überall sonst entfernt haben."""
        assert _unter("mls", "import liga_backtest as B;print(B._default_leagues())") == "['MLS']"
        liga = _unter("liga", "import liga_backtest as B;print(B._default_leagues())")
        assert "MLS" not in liga

    def test_mls_nutzt_vorsaison_UND_laufende_saison(self):
        """MLS spielt im Kalenderjahr. Die laufende Saison (218 Spiele) ist aktuell, die Vorsaison
        (~510) liefert die Masse — zusammen reicht es für MIN_CALLS=50 je Signal."""
        out = _unter("mls", "import liga_backtest as B;print(len(B._default_seasons()))")
        assert int(out) == 2
        out = _unter("liga", "import liga_backtest as B;print(len(B._default_seasons()))")
        assert int(out) == 1, "Europa: nur die abgeschlossene Vorsaison"


class TestPriorKette:
    def test_beide_enden_zeigen_auf_dieselbe_datei(self):
        """prime_liga_priors SCHREIBT und update_signal_weights LIEST — wenn die auseinanderlaufen,
        läuft der Backtest ins Leere, ohne dass es jemand merkt."""
        for ds, erwartet in (("mls", "mls_signal_priors.json"), ("liga", "liga_signal_priors.json")):
            out = _unter(ds, "import prime_liga_priors as P, update_signal_weights as U;"
                             "print(P.OUT.name, U.PRIORS_FILE.name)")
            schreibt, liest = out.split()
            assert schreibt == liest == erwartet, f"{ds}: schreibt {schreibt}, liest {liest}"

    def test_report_ist_datensatz_eigen(self):
        """Ein MLS-Backtest darf den Liga-Report nicht überschreiben."""
        assert _unter("mls", "import liga_backtest as B;import pathlib;"
                             "print(pathlib.Path(B.REPORT_FILE).name)") == "mls_backtest_report.json"
        assert _unter("liga", "import liga_backtest as B;import pathlib;"
                              "print(pathlib.Path(B.REPORT_FILE).name)") == "liga_backtest_report.json"

    def test_priors_brauchen_keine_quoten(self):
        """Der Kern, warum MLS ohne historische Quoten funktioniert: build_priors liest nur
        hitRate + calls."""
        import prime_liga_priors as P
        report = {"perSignal": {
            "xg_strength": {"hitRate": 0.663, "calls": 326},      # keine odds/roi-Felder
            "form_trend":  {"hitRate": 0.572, "calls": 502},
            "zu_wenig":    {"hitRate": 0.900, "calls": 10},       # unter MIN_CALLS → kein Prior
        }}
        p = P.build_priors(report)
        assert set(p) == {"xg_strength", "form_trend"}
        assert p["xg_strength"]["hitRate"] == 0.663
        assert p["xg_strength"]["winsPrior"] > 0
        assert "zu_wenig" not in p, "verrauschte Signale dürfen keinen Prior bekommen"


class TestReplayKontext:
    def test_spielplan_im_replay(self):
        """fixture_congestion bekam im Backtest NIE einen Call (kein team_schedule im Kontext) →
        also auch nie einen Prior, obwohl es live regelmäßig feuert (MLS spielt viel unter der
        Woche). Mit Spielplan: 88 Calls auf den 218 echten Spielen."""
        import inspect
        import liga_backtest as B
        src = inspect.getsource(B.replay)
        assert '"team_schedule"' in src
        assert '"current_match_date"' in src

    def test_replay_laeuft_auf_echten_mls_spielen(self):
        """Trockenlauf gegen die echten Saisondaten — kein Mock. Wenn der Replay für MLS crasht
        oder nichts liefert, ist der ganze Backtest wertlos."""
        code = """
import json
import liga_backtest as B, sharp_signals.registry as R
d = json.load(open("mls-data.json")); g = list(d["groups"].values())[0]
matches = []
for f in g["fixtures"]:
    r = f.get("result") or {}
    if r.get("home_score") is None:
        continue
    matches.append({"home": f["home"], "away": f["away"],
                    "hs": int(r["home_score"]), "as_": int(r["away_score"]),
                    "matchday": f.get("matchday") or 1, "date": f.get("date") or ""})
matches.sort(key=lambda m: m["date"])
led, _ = B.replay(matches, lambda p, c: R.evaluate_signals(p, c, {}), league="MLS")
sig = {e["signal"] for e in led}
print(len(matches), len(led), len(sig))
"""
        n_matches, n_calls, n_sig = map(int, _unter("mls", code).split())
        assert n_matches >= 200, "MLS-Saisondaten fehlen"
        assert n_calls > 500, "Replay liefert kaum Calls"
        assert n_sig >= 3, "zu wenige Signale kommen im Backtest überhaupt zum Zug"
