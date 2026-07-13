"""13.07.2026 — MLS-Audit (Lucas: „ich glaube wir haben noch Fehler, wo wir was nur für WM haben").

BUG-KLASSE: Ein Skript ist nicht dataset-aware und arbeitet unter COCOBET_DATASET=mls trotzdem auf
den WM- oder LIGA-Dateien. Heute an EINEM Tag viermal real aufgetreten (resolve_wm_results,
signal_check, wm_data_integrity, und der ganze Schwung unten). Die Fehler sind alle STILL: kein
Crash, keine Warnung — nur falsche Zahlen.

Diese Tests halten die Reparaturen fest. Sie prüfen das ERGEBNIS (welche Datei wird aufgelöst),
nicht den Wortlaut des Codes.
"""
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _unter_mls(code: str) -> str:
    """Modul-Konstanten in einem SUBPROZESS mit COCOBET_DATASET=mls auswerten.

    Bewusst isoliert: cocobet_dataset wird beim Import ausgewertet. Würden wir os.environ hier
    setzen, verseuchten wir alle anderen Tests im selben Prozess (genau das ist mir bei
    test_poly_mls_name_resolution schon passiert — 6 Liga-Tests gingen kaputt).
    """
    env = {**os.environ, "COCOBET_DATASET": "mls", "COCOBET_PROFILE": "mls_default"}
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, f"Subprozess-Fehler: {r.stderr[-400:]}"
    return r.stdout.strip()


class TestGeldKritisch:
    def test_guards_pruefen_die_MLS_wetten_nicht_die_WM_wetten(self):
        """🔴 Fünf Geld-Guards hingen an wm_auto_bets_placed.json — darunter
        check_autobet_kickoff_present, gebaut nach dem In-Play-Verlust QAT–SUI (−€5,50).
        Sobald der MLS-Auto-Trader scharf ist, schreibt er nach mls_auto_bets_placed.json —
        und KEIN Guard hätte je hingesehen. Der Schutz wäre blind, sobald Geld fließt."""
        out = _unter_mls(
            "import json, wm_data_integrity as W;"
            "wm=json.load(open('mls-data.json'));"
            "ctx=W.IntegrityCtx(wm=wm,poly={},schedule={},venues={});"
            "print(W.D.file('wm_auto_bets_placed.json','liga_auto_bets_placed.json').name)"
        )
        assert out == "mls_auto_bets_placed.json"

    def test_pick_engine_liest_die_MLS_spielerform(self):
        """generate_wm_picks nutzte `liga_player_form.json if IS_LIGA` — und IS_LIGA ist für MLS
        ebenfalls True. Damit war die player_form-Skalierung des lineup_signal für MLS tot; sobald
        die Liga-Datei existiert, hätte die MLS-Engine mit Top-5-Spielerform gerechnet."""
        out = _unter_mls("import cocobet_dataset as D;"
                         "print(D.file('player_form.json','liga_player_form.json').name)")
        assert out == "mls_player_form.json"


class TestMessSchicht:
    @pytest.mark.parametrize("modul,konstante,erwartet", [
        ("resolve_wm_results",   "POLY_HIST_FILE", "mls-poly-history.json"),
        ("detect_wm_sharp_moves", "POLY_FILE",     "mls_poly_prices.json"),
        ("fetch_liga_match_stats", "CACHE_FILE",   "mls_match_stats_cache.json"),
    ])
    def test_konstanten_zeigen_auf_den_MLS_datensatz(self, modul, konstante, erwartet):
        out = _unter_mls(f"import {modul} as M;"
                         f"import pathlib;print(pathlib.Path(str(M.{konstante})).name)")
        assert out == erwartet, f"{modul}.{konstante} → {out} statt {erwartet}"

    def test_match_pages_finden_die_MLS_aufstellungen(self):
        out = _unter_mls("import generate_wm_match_pages as M;"
                         "import pathlib;print(pathlib.Path(str(M.LINEUPS_FILE)).name)")
        assert out == "mls_lineups.json"

    def test_telegram_dedup_ist_datensatz_eigen(self):
        """STILLER UNTERDRÜCKER: Der Dedup-Key ist `type:datum` OHNE Datensatz. Mit gemeinsamer
        Datei unterdrückte eine gesendete WM-Morning-Card den MLS-Digest desselben Tages —
        ohne Fehler, ohne Log, einfach keine Nachricht."""
        out = _unter_mls("import telegram_wm as T, os;print(os.path.basename(T.SENT_STATE))")
        assert out == "mls_telegram_sent.json"


class TestKeineTestVerschmutzung:
    def test_kein_testmodul_setzt_den_datensatz_beim_import(self):
        """13.07.2026: test_liga_data_wipe_guard setzte COCOBET_DATASET=liga auf MODUL-Ebene.
        Das wirkt schon beim EINSAMMELN — die halbe Suite lief danach im Liga-Datensatz. Solange
        die Guards ihre Dateien hart als wm_*.json verdrahtet hatten, blieb das unsichtbar. Als sie
        dataset-aware wurden, kippten schlagartig 13 unbeteiligte Tests, die isoliert grün waren.

        Env-Setzung gehört in den Test (conftest.py stellt danach wieder her) oder in einen
        Subprozess — niemals auf Modul-Ebene.
        """
        import ast
        treffer = []
        for f in sorted((REPO / "tests").glob("test_*.py")):
            tree = ast.parse(f.read_text("utf-8"))
            for node in tree.body:                      # NUR Top-Level …
                # … und NICHT in Funktionen/Klassen hinein: dort ist Env-Setzung erlaubt,
                # conftest.py stellt nach jedem Test wieder her. Gefährlich ist ausschließlich
                # Code, der beim IMPORT läuft (also während pytest die Module einsammelt).
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                for sub in ast.walk(node):
                    ok = (isinstance(sub, ast.Subscript)
                          and isinstance(sub.value, ast.Attribute)
                          and sub.value.attr == "environ")
                    setdefault = (isinstance(sub, ast.Call)
                                  and isinstance(sub.func, ast.Attribute)
                                  and sub.func.attr == "setdefault"
                                  and isinstance(sub.func.value, ast.Attribute)
                                  and sub.func.value.attr == "environ")
                    if not (ok or setdefault):
                        continue
                    quelle = ast.unparse(sub)
                    if "COCOBET" in quelle or "LIGA_SEASON" in quelle:
                        treffer.append(f"{f.name}:{node.lineno} → {quelle}")
        assert not treffer, ("Datensatz-Env auf Modul-Ebene gesetzt (vergiftet die ganze Suite):\n  "
                             + "\n  ".join(treffer))


class TestConfigMergeVerliertNichts:
    """13.07.2026 — Der Merge lief nur über DEFAULT_FALLBACK.keys(): jede Sektion, die im Profil
    stand, aber nicht im Fallback, wurde KOMMENTARLOS VERWORFEN.

    Folge: `conviction_score.steam_bet_threshold` ist für Liga/MLS auf 8 gesetzt („Liga strenger"),
    der Code-Default ist 6 → Liga und MLS haben mit der lockeren WM-Schwelle gewettet und mehr
    Picks veröffentlicht als eingestellt. Dieselbe Falle hatte heute schon `tag_slug` und
    `smartmoney_min_usd` verschluckt.
    """

    def test_keine_profil_sektion_geht_verloren(self):
        import json
        from cocobet_config import _resolve_active_profile
        raw = json.loads((REPO / "cocobet_config.json").read_text("utf-8"))
        for prof in ("wm2026", "liga_default", "mls_default"):
            os.environ["COCOBET_PROFILE"] = prof
            try:
                merged = _resolve_active_profile(raw)
            finally:
                os.environ.pop("COCOBET_PROFILE", None)
            fehlend = set(raw["profiles"][prof]) - set(merged)
            assert not fehlend, f"{prof}: Sektionen verworfen → {sorted(fehlend)}"

    def test_steam_schwelle_je_profil(self):
        """Der konkrete Geld-Effekt: WM lockerer (6), Liga/MLS strenger (8)."""
        for prof, erwartet in (("wm2026", 6), ("liga_default", 8), ("mls_default", 8)):
            r = subprocess.run(
                [sys.executable, "-c",
                 "import generate_wm_picks as G;print(G.STEAM_BET_THRESHOLD)"],
                cwd=REPO, capture_output=True, text=True, timeout=90,
                env={**os.environ, "COCOBET_PROFILE": prof,
                     "COCOBET_DATASET": {"wm2026": "wm", "liga_default": "liga",
                                         "mls_default": "mls"}[prof]})
            assert r.returncode == 0, r.stderr[-300:]
            assert int(r.stdout.strip()) == erwartet, f"{prof}: {r.stdout.strip()} statt {erwartet}"

    def test_defaults_greifen_weiterhin_wenn_profil_die_sektion_nicht_hat(self):
        """Das Sicherheitsnetz darf durch den Union-Merge nicht verloren gehen."""
        from cocobet_config import _resolve_active_profile, DEFAULT_FALLBACK
        raw = {"profiles": {"active": "leer", "leer": {}}}
        os.environ["COCOBET_PROFILE"] = "leer"
        try:
            merged = _resolve_active_profile(raw)
        finally:
            os.environ.pop("COCOBET_PROFILE", None)
        for sec in DEFAULT_FALLBACK:
            assert merged[sec] == DEFAULT_FALLBACK[sec]
