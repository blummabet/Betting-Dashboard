"""🔴 09.10.2026 (Lucas: „irgendwie failen auch oft die Tests in den Actions beim Merge").

tests.yml fuhr die ganze Suite (`unittest discover`) unter `timeout-minutes: 5` — gemessen
4.591 Tests in 6:53 Min, also bei jedem Push abgebrochen und rot. ci-tests.yml faehrt dieselbe
Suite mit pytest. Die Suite laeuft jetzt einmal, und zwar dort, wo kein zu enger Deckel sitzt.
"""
import re
from pathlib import Path

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def test_tests_yml_faehrt_die_suite_nicht_noch_einmal():
    src = (WF / "tests.yml").read_text(encoding="utf-8")
    code = "\n".join(z for z in src.splitlines() if not z.lstrip().startswith("#"))
    assert "unittest discover" not in code and "-m pytest" not in code


def test_ci_tests_faehrt_die_suite_ohne_engen_deckel():
    src = (WF / "ci-tests.yml").read_text(encoding="utf-8")
    assert "python -m pytest tests/" in src
    m = re.search(r"backend:.*?(?=\n  \w)", src, re.S)
    deckel = re.search(r"timeout-minutes:\s*(\d+)", m.group(0)) if m else None
    assert deckel is None or int(deckel.group(1)) >= 20, "Deckel kleiner als die Suite"


def _paths(name):
    import yaml
    d = yaml.safe_load((WF / name).read_text(encoding="utf-8"))
    on = d.get("on") or d.get(True)
    return (on.get("push") or {}).get("paths")


def test_daten_commits_starten_keine_test_suite():
    """09.10.2026: ohne Pfad-Filter startete jeder Daten-Commit der Pipeline die volle Suite —
    und machte Commits ohne eine Zeile Code rot, sobald die Daten sich bewegten."""
    import fnmatch
    for name in ("ci-tests.yml", "tests.yml"):
        pfade = _paths(name)
        assert pfade, f"{name}: kein Pfad-Filter"
        def trifft(f):
            return any(fnmatch.fnmatch(f, p.replace("**", "*")) for p in pfade)
        for daten in ("poly_money_broad_close.json", "betfair_public_ledger.json",
                      "health/betfair.json", "stake_burst_ledger.json"):
            assert not trifft(daten), f"{name} startet bei {daten}"
        for code in ("poly_whale_watch.py", "money-map.js", "tests/test_x.py",
                     ".github/workflows/betfair.yml"):
            assert trifft(code), f"{name} startet NICHT bei {code}"
