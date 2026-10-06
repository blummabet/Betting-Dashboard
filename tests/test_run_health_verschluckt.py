"""06.10.2026: run_health sah 37 h lang keinen Absturz — continue-on-error-Steps stehen in der
REST-API auf conclusion „success". Erst die Check-Run-Annotation sagt „exit code 1"."""
import run_health as R

JOBS = {"jobs": [{"id": 112108794046, "name": "scan", "steps": [
    {"name": "🌐 Poly-Geld breit", "conclusion": "success", "number": 7}]}]}
ANN = [{"annotation_level": "warning", "message": "Node.js 20 is deprecated"},
       {"annotation_level": "failure", "message": "Process completed with exit code 1."}]


def fetch(url):
    return ANN if "/annotations" in url else JOBS


def test_verschluckter_abbruch_wird_sichtbar():
    steps = [("scan", "🌐 Poly-Geld breit", "success", 7)]
    extra = R.verschluckte_abbrueche("o/r", "1", "", steps, fetch=fetch)
    assert len(extra) == 1 and extra[0][2] == "failure (exit code)"
    e = R.baue_eintrag("wf", "1", None, steps + extra)
    assert e["ok"] is False and e["failures"][0]["conclusion"] == "failure (exit code)"


def test_schon_gezaehlte_fehler_nicht_doppelt():
    steps = [("scan", "x", "failure", 3)]
    assert R.verschluckte_abbrueche("o/r", "1", "", steps, fetch=fetch) == []


def test_ohne_failure_annotation_nichts():
    leer = lambda u: [] if "/annotations" in u else JOBS
    assert R.verschluckte_abbrueche("o/r", "1", "", [], fetch=leer) == []
