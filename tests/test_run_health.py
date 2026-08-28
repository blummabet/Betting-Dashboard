"""28.08.2026 — Lucas: „glaubst du nicht auch dass oft in diesen Logs Fehler stehen die wir gar
nicht mitkriegen?"

Gezaehlt: 393 Steps insgesamt, davon 135 mit `continue-on-error: true`, dazu 279 `|| true`.
Ein Job laeuft gruen durch, waehrend ein Drittel gescheitert ist. Bewiesene Faelle: resolve_picks
war drei Monate tot (315 offene Picks) und der Poly-Fetch verlor ab dem 24.08. jeden Lauf die
anpfiff-nahen Maerkte.

run_health.py fragt am Ende jedes Laufs die eigenen Steps ueber die GitHub-API ab. Diese Tests
halten die drei Eigenschaften fest, an denen ein Waechter steht und faellt:

  1. Er sieht gescheiterte Steps AUCH dann, wenn der Job gruen ist (der ganze Zweck).
  2. „Konnte nicht fragen" ist NICHT „alles gruen" — fehlende Information ist keine Erlaubnis.
  3. Er macht den ueberwachten Lauf nie rot und spamt nicht bei jedem 30-Minuten-Lauf.
"""
import io
import os
import re
import sys
import json
import yaml
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import run_health as R


def jobs(*steps):
    """GitHub-API-Antwort nachbauen: (name, conclusion) → /actions/runs/<id>/jobs."""
    return {"jobs": [{"name": "build", "steps": [
        {"name": n, "conclusion": c, "number": i + 1} for i, (n, c) in enumerate(steps)]}]}


class TestGescheiterteStepsFinden:
    def test_gruener_job_mit_kaputtem_step_wird_erkannt(self):
        """DER Fall: continue-on-error macht den Job gruen, der Step ist trotzdem tot."""
        steps = R.hole_steps("a/b", 1, "", fetch=lambda u: jobs(
            ("Repo auschecken", "success"),
            ("Picks aufloesen", "failure"),      # continue-on-error → Job bleibt gruen
            ("Committen", "success")))
        fails = R.fehlerhafte_steps(steps)
        assert [f[1] for f in fails] == ["Picks aufloesen"]

    def test_sauberer_lauf_meldet_nichts(self):
        steps = R.hole_steps("a/b", 1, "", fetch=lambda u: jobs(("A", "success"), ("B", "success")))
        assert R.fehlerhafte_steps(steps) == []

    def test_uebersprungene_steps_sind_kein_fehler(self):
        """Fast jeder Step haengt an einem `if:` — skipped ist der Normalfall, kein Schaden."""
        steps = R.hole_steps("a/b", 1, "", fetch=lambda u: jobs(
            ("PRE-Match-Digest", "skipped"), ("POST-Match-Recap", "skipped")))
        assert R.fehlerhafte_steps(steps) == []

    def test_timeout_und_abbruch_zaehlen_als_fehler(self):
        steps = R.hole_steps("a/b", 1, "", fetch=lambda u: jobs(
            ("Odds holen", "timed_out"), ("Push", "cancelled")))
        assert len(R.fehlerhafte_steps(steps)) == 2

    def test_laufender_step_zaehlt_nicht(self):
        """Der Waechter selbst laeuft noch, waehrend er fragt — conclusion ist dann null."""
        steps = R.hole_steps("a/b", 1, "", fetch=lambda u: jobs(
            ("A", "success"), ("Lauf-Gesundheit", None)))
        assert R.fehlerhafte_steps(steps) == []

    def test_erster_fehler_steht_oben(self):
        """Bei einer Kette ist der ERSTE Fehler die Ursache, der Rest oft Folge."""
        steps = R.hole_steps("a/b", 1, "", fetch=lambda u: jobs(
            ("A", "success"), ("Odds", "failure"), ("Picks", "failure")))
        assert [f[1] for f in R.fehlerhafte_steps(steps)] == ["Odds", "Picks"]

    def test_mehrere_jobs_werden_zusammengefasst(self):
        antwort = {"jobs": [
            {"name": "liga", "steps": [{"name": "A", "conclusion": "failure", "number": 1}]},
            {"name": "mls",  "steps": [{"name": "B", "conclusion": "success", "number": 1}]},
        ]}
        steps = R.hole_steps("a/b", 1, "", fetch=lambda u: antwort)
        assert [(f[0], f[1]) for f in R.fehlerhafte_steps(steps)] == [("liga", "A")]


class TestUnbekanntIstNichtGruen:
    def test_api_fehler_macht_den_eintrag_nicht_ok(self):
        e = R.baue_eintrag("Liga", 1, None, [], api_fehler="HTTP 403")
        assert e["ok"] is False
        assert e["apiError"] == "HTTP 403"

    def test_api_fehler_steht_in_der_zusammenfassung(self):
        e = R.baue_eintrag("Liga", 1, None, [], api_fehler="HTTP 403")
        assert "UNBEKANNT" in R.zusammenfassen(e)

    def test_leerer_lauf_ohne_api_fehler_ist_ok(self):
        assert R.baue_eintrag("Liga", 1, None, [])["ok"] is True


class TestAlarmVerhalten:
    def _mit(self, *namen):
        return {"ok": False, "apiError": None,
                "failures": [{"job": "build", "step": n, "conclusion": "failure"} for n in namen]}

    def test_neuer_fehler_alarmiert(self):
        assert R.alarm_noetig(self._mit("Picks"), None) is True

    def test_derselbe_fehler_alarmiert_nicht_nochmal(self):
        """Sonst pingt der 30-Minuten-Workflow 48x am Tag dieselbe Meldung."""
        letzter = self._mit("Picks")
        assert R.alarm_noetig(self._mit("Picks"), letzter) is False

    def test_zusaetzlicher_fehler_alarmiert(self):
        assert R.alarm_noetig(self._mit("Picks", "Odds"), self._mit("Picks")) is True

    def test_rueckfall_nach_erholung_alarmiert_wieder(self):
        gesund = {"ok": True, "apiError": None, "failures": []}
        assert R.alarm_noetig(self._mit("Picks"), gesund) is True

    def test_sauberer_lauf_alarmiert_nicht(self):
        assert R.alarm_noetig({"ok": True, "apiError": None, "failures": []}, None) is False

    def test_api_fehler_loest_keinen_telegram_aus(self):
        """Ein API-Ausfall ist ein Waechter-Problem, kein Pipeline-Problem — das gehoert auf die
        Status-Seite, nicht als Alarm aufs Handy."""
        assert R.alarm_noetig({"ok": False, "apiError": "HTTP 403", "failures": []}, None) is False


class TestNieDenLaufKaputtmachen:
    def test_ohne_actions_kontext_exit_0(self, monkeypatch, tmp_path):
        for k in ("GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.chdir(tmp_path)
        assert R.main(["--slug", "x"]) == 0

    def test_api_ausfall_exit_0_und_datei_entsteht(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GITHUB_REPOSITORY", "a/b")
        monkeypatch.setenv("GITHUB_RUN_ID", "42")
        monkeypatch.setenv("GITHUB_WORKFLOW", "Liga aktualisieren")
        monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
        monkeypatch.setattr(R, "hole_steps", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        monkeypatch.chdir(tmp_path)
        assert R.main(["--slug", "liga"]) == 0
        d = json.loads((tmp_path / "health" / "liga.json").read_text(encoding="utf-8"))
        assert d["runs"][0]["apiError"].startswith("boom")
        assert d["ok"] is False

    def test_slug_wird_zu_einem_sicheren_dateinamen(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GITHUB_REPOSITORY", "a/b")
        monkeypatch.setenv("GITHUB_RUN_ID", "42")
        monkeypatch.setattr(R, "hole_steps", lambda *a, **k: [])
        monkeypatch.chdir(tmp_path)
        R.main(["--slug", "../../etc/passwd"])
        assert (tmp_path / "health").is_dir()
        assert not (tmp_path / "etc").exists()

    def test_historie_wird_gedeckelt(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GITHUB_REPOSITORY", "a/b")
        monkeypatch.setenv("GITHUB_RUN_ID", "42")
        monkeypatch.setattr(R, "hole_steps", lambda *a, **k: [])
        monkeypatch.chdir(tmp_path)
        for _ in range(R.HISTORIE + 5):
            R.main(["--slug", "liga"])
        d = json.loads((tmp_path / "health" / "liga.json").read_text(encoding="utf-8"))
        assert len(d["runs"]) == R.HISTORIE

    def test_kaputte_bestehende_datei_wirft_nicht(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GITHUB_REPOSITORY", "a/b")
        monkeypatch.setenv("GITHUB_RUN_ID", "42")
        monkeypatch.setattr(R, "hole_steps", lambda *a, **k: [])
        monkeypatch.chdir(tmp_path)
        (tmp_path / "health").mkdir()
        (tmp_path / "health" / "liga.json").write_text("{kaputt", encoding="utf-8")
        assert R.main(["--slug", "liga"]) == 0

    def test_keine_order_oder_geld_funktion_im_skript(self):
        """Ein Waechter fasst nichts an. Fixiert, damit hier nie 'nur kurz' etwas dazukommt."""
        src = io.open(os.path.join(REPO, "run_health.py"), encoding="utf-8").read()
        for verboten in ("clob", "private_key", "POLY_PRIVATE_KEY", "post_order", "place_bet"):
            assert verboten.lower() not in src.lower(), f"'{verboten}' hat hier nichts verloren"


class TestVerdrahtungInDenWorkflows:
    """Ein Waechter, der in keinem Workflow steht, ueberwacht nichts (Audit-Befund 07)."""

    DATEIEN = ["update-liga.yml", "manage-liga-poly.yml", "fetch-liga-odds-dense.yml",
               "betfair.yml", "capture-closing-liga.yml"]

    def _src(self, datei):
        with open(os.path.join(REPO, ".github", "workflows", datei), encoding="utf-8") as f:
            return f.read()

    def _steps(self, datei):
        """Steps als geparstes YAML — Textsuche ueber Zeilenabstaende ist zu bruechig
        (der erste Anlauf dieses Tests fiel auf einen `run_health.py`-Treffer im
        permissions-Kommentar herein und meldete Fehlalarm)."""
        wf = yaml.safe_load(self._src(datei))
        raus = []
        for job in (wf.get("jobs") or {}).values():
            raus.extend((job or {}).get("steps") or [])
        return raus

    def _waechter(self, datei):
        treffer = [s for s in self._steps(datei) if "run_health.py" in str(s.get("run") or "")]
        assert len(treffer) == 1, f"{datei}: {len(treffer)} run_health-Steps, erwartet genau 1"
        return treffer[0]

    @pytest.mark.parametrize("datei", DATEIEN)
    def test_workflow_ruft_run_health(self, datei):
        assert "run_health.py --slug" in self._src(datei)

    @pytest.mark.parametrize("datei", DATEIEN)
    def test_waechter_laeuft_auch_nach_einem_fehler(self, datei):
        """Ohne `if: always()` liefe er genau dann NICHT, wenn er gebraucht wird."""
        assert str(self._waechter(datei).get("if", "")).strip() == "always()", \
            f"{datei}: run_health ohne `if: always()`"

    @pytest.mark.parametrize("datei", DATEIEN)
    def test_waechter_macht_den_job_nicht_rot(self, datei):
        """Ein Waechter, der den ueberwachten Lauf zum Scheitern bringt, wird abgeschaltet."""
        assert self._waechter(datei).get("continue-on-error") is True, \
            f"{datei}: run_health ohne continue-on-error"

    @pytest.mark.parametrize("datei", DATEIEN)
    def test_waechter_bekommt_den_token(self, datei):
        env = self._waechter(datei).get("env") or {}
        assert "GITHUB_TOKEN" in env, f"{datei}: run_health ohne GITHUB_TOKEN — API gibt 401"

    @pytest.mark.parametrize("datei", DATEIEN)
    def test_workflow_darf_die_eigenen_steps_lesen(self, datei):
        """Ohne `actions: read` gibt die API 403 — der Waechter meldete dann ewig UNBEKANNT."""
        assert re.search(r"^\s*actions:\s*read", self._src(datei), re.M), \
            f"{datei}: permissions.actions: read fehlt"

    @pytest.mark.parametrize("datei", DATEIEN)
    def test_health_datei_wird_committet(self, datei):
        """Bleibt sie auf der Runner-Platte, ist der Waechter nach dem Job weg."""
        assert "health/" in self._src(datei), f"{datei}: health/<slug>.json wird nicht committet"

    @pytest.mark.parametrize("datei", DATEIEN)
    def test_waechter_steht_vor_dem_commit(self, datei):
        """Laeuft er nach dem Commit, bleibt health/<slug>.json auf der Runner-Platte."""
        steps = self._steps(datei)
        i_w = next(i for i, s in enumerate(steps) if "run_health.py" in str(s.get("run") or ""))
        i_c = next(i for i, s in enumerate(steps) if "git add" in str(s.get("run") or ""))
        assert i_w < i_c, f"{datei}: Waechter laeuft nach dem Commit"
