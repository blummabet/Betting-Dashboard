"""28.08.2026 — der Guard, der health/*.json auf die Status-Seite holt.

Der Waechter allein reicht nicht: wenn seine Datei nur im Repo liegt und niemand sie liest,
ist das dieselbe Sorte Fehler wie die, die er finden soll (Audit-Befund 07, 25.08.: die
Poly-Analyseschicht lief, ihr Ergebnis verliess den Runner nie).

check_run_health in wm_data_integrity.py meldet drei Dinge:
  * ein gescheiterter Step im letzten Lauf — auch wenn der Job gruen war,
  * ein nicht abfragbarer Lauf (UNBEKANNT ist kein Gruen),
  * eine ueberfaellige Health-Datei — der Workflow meldet sich gar nicht mehr.
"""
import os
import sys
import json
import pytest
from datetime import datetime, timezone, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import wm_data_integrity as W


JETZT = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


class Ctx:
    now = JETZT


def schreibe(tmp_path, name, laeufe, ok=True):
    d = tmp_path / "health"
    d.mkdir(exist_ok=True)
    (d / (name + ".json")).write_text(json.dumps({
        "slug": name, "workflow": name, "ok": ok, "runs": laeufe}), encoding="utf-8")


def lauf(alter_h=0.5, failures=(), api_fehler=None):
    return {"ts": (JETZT - timedelta(hours=alter_h)).isoformat(),
            "workflow": "Liga", "runId": "1", "nSteps": 12,
            "apiError": api_fehler, "ok": (api_fehler is None and not failures),
            "failures": [{"job": "build", "step": s, "conclusion": "failure"} for s in failures]}


@pytest.fixture
def health(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_BASE", tmp_path)
    return tmp_path


class TestGuard:
    def test_sauberer_lauf_ist_gruen(self, health):
        schreibe(health, "liga", [lauf()])
        c = W.check_run_health(Ctx())
        assert c["ok"] is True and c["nFail"] == 0

    def test_gescheiterter_step_wird_gemeldet(self, health):
        schreibe(health, "liga", [lauf(failures=["Picks aufloesen"])])
        c = W.check_run_health(Ctx())
        assert c["ok"] is False
        assert "Picks aufloesen" in c["failures"][0]
        assert "gruen" in c["failures"][0], "der Kern der Meldung fehlt: Job war trotzdem gruen"

    def test_severity_ist_error_nicht_warn(self, health):
        """Ein toter Step ist kein Schoenheitsfehler — er muss die Status-Ampel kippen."""
        schreibe(health, "liga", [lauf(failures=["X"])])
        assert W.check_run_health(Ctx())["severity"] == "error"

    def test_api_fehler_ist_kein_gruen(self, health):
        schreibe(health, "liga", [lauf(api_fehler="HTTP 403")])
        c = W.check_run_health(Ctx())
        assert c["ok"] is False and "UNBEKANNT" in c["failures"][0]

    def test_ueberfaelliger_workflow_faellt_auf(self, health):
        """Der Fall, den kein Log zeigen kann: der Lauf hat gar nicht stattgefunden."""
        schreibe(health, "liga", [lauf(alter_h=W.RUN_HEALTH_STALE_H + 2)])
        c = W.check_run_health(Ctx())
        assert c["ok"] is False and "kein Lauf mehr" in c["failures"][0]

    def test_ein_ausfall_allein_schreit_noch_nicht(self, health):
        schreibe(health, "liga", [lauf(alter_h=W.RUN_HEALTH_STALE_H - 2)])
        assert W.check_run_health(Ctx())["ok"] is True

    def test_nur_der_letzte_lauf_zaehlt(self, health):
        """Ein behobener Fehler von gestern darf die Ampel nicht dauerhaft rot halten."""
        schreibe(health, "liga", [lauf(), lauf(alter_h=5, failures=["Alt"])])
        assert W.check_run_health(Ctx())["ok"] is True

    def test_mehrere_workflows_werden_alle_geprueft(self, health):
        schreibe(health, "liga", [lauf()])
        schreibe(health, "betfair", [lauf(failures=["Radar"])])
        c = W.check_run_health(Ctx())
        assert c["nFail"] == 1 and "Radar" in c["failures"][0]

    def test_ohne_dateien_nur_warnung(self, health):
        """Solange der Waechter nirgends laeuft, ist 'nichts gefunden' keine Aussage."""
        c = W.check_run_health(Ctx())
        assert c["severity"] == "warn" and c["ok"] is True
        assert "run_health.py" in c["note"]

    def test_kaputte_datei_wird_gemeldet_statt_verschluckt(self, health):
        d = health / "health"
        d.mkdir(exist_ok=True)
        (d / "liga.json").write_text("{kaputt", encoding="utf-8")
        c = W.check_run_health(Ctx())
        assert c["ok"] is False and "nicht lesbar" in c["failures"][0]

    def test_datei_ohne_laeufe_wird_gemeldet(self, health):
        schreibe(health, "liga", [])
        assert W.check_run_health(Ctx())["ok"] is False

    def test_unlesbarer_zeitstempel_gilt_nicht_als_ueberfaellig(self, health):
        """Unbekanntes Alter darf keinen Fehlalarm ausloesen — der Step-Status zaehlt weiter."""
        schreibe(health, "liga", [{"ts": "kaputt", "failures": [], "apiError": None, "ok": True}])
        assert W.check_run_health(Ctx())["ok"] is True

    def test_guard_ist_registriert(self):
        assert any(f.__name__ == "check_run_health" for f in W.INTEGRITY_CHECKS), \
            "Guard laeuft nicht mit — dann steht er nie in liga_status.json"


class TestAlterHilfsfunktion:
    def test_rechnet_stunden(self):
        assert W._alter_h((JETZT - timedelta(hours=3)).isoformat(), JETZT) == pytest.approx(3, abs=0.01)

    def test_z_suffix_wird_verstanden(self):
        assert W._alter_h("2026-08-28T09:00:00Z", JETZT) == pytest.approx(3, abs=0.01)

    def test_naive_zeit_gilt_als_utc(self):
        assert W._alter_h("2026-08-28T09:00:00", JETZT) == pytest.approx(3, abs=0.01)

    def test_muell_gibt_none(self):
        for x in (None, "", "gestern", 12345):
            assert W._alter_h(x, JETZT) is None
