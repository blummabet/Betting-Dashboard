"""Der Live-Scan wird vom Betfair-Lauf angestossen — 29.09.2026.

Der 15-Min-Cron des Live-Scans lieferte seit Wochen ~5 Laeufe am Tag (Luecken 2,5-8 h), waehrend
der Betfair-Job auf demselben Mac 98,6/Tag schafft. Ein workflow_dispatch vom Betfair-Lauf aus
umgeht den gedrosselten Zeitplan.
"""
import pathlib
import yaml

WF = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _bf():
    return yaml.safe_load((WF / "betfair.yml").read_text(encoding="utf-8"))


def test_betfair_stoesst_den_live_scan_an():
    d = _bf()
    steps = list(d["jobs"].values())[0]["steps"]
    s = [x for x in steps if "Live-Scan anstossen" in (x.get("name") or "")]
    assert s, "Anstoss-Schritt fehlt"
    s = s[0]
    assert "poly-live-scan.yml/dispatches" in s["run"]
    assert s.get("if") == "always()", "auch nach einem fehlgeschlagenen Betfair-Schritt anstossen"
    assert s.get("continue-on-error") is True, "ein gescheiterter Anstoss darf den Betfair-Lauf nicht rot machen"
    assert steps[-1] is s, "zuletzt — der Live-Scan soll den frisch committeten Stand sehen"


def test_betfair_darf_workflows_anstossen():
    assert _bf()["permissions"].get("actions") == "write"


def test_live_scan_ist_anstossbar_und_behaelt_seinen_rueckfall():
    d = yaml.safe_load((WF / "poly-live-scan.yml").read_text(encoding="utf-8"))
    on = d.get(True) or d.get("on")
    assert "workflow_dispatch" in on, "ohne workflow_dispatch laeuft der Anstoss ins Leere"
    assert on.get("schedule"), "der Cron bleibt als Rueckfall"
    assert d["concurrency"]["group"] == "poly-live-scan", "doppelte Ticks faengt die Gruppe ab"
