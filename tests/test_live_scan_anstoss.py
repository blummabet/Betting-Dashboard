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


# ── 30.09.2026: Mengenbremse (Lucas: „irgendwas wurde da verschlimmbessert") ────────────────
# Live-Scan-Commits: 6-10/Tag vorher, 51 am 29.09., 103 am 30.09. — jeder Betfair-Lauf stiess an.
import importlib.util as _ilu
from datetime import datetime as _dt, timedelta as _td, timezone as _tz

_spec = _ilu.spec_from_file_location("live_scan_faellig", "scripts/live_scan_faellig.py")
LF = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(LF)
_JETZT = _dt(2026, 9, 30, 12, 0, tzinfo=_tz.utc)


def _h(min_her):
    return {"runs": [{"ts": (_JETZT - _td(minutes=min_her)).isoformat()}]}


def test_kurz_nach_einem_lauf_kein_anstoss():
    assert LF.faellig(_h(15), _JETZT) is False, "Gegentest: vorher stiess JEDER Lauf an"


def test_nach_40_minuten_wieder():
    assert LF.faellig(_h(41), _JETZT) is True


def test_unbekannt_heisst_anstossen():
    """Ein fehlender Stempel darf den Scan nicht stilllegen — sonst waere der alte Ausfall zurueck."""
    for h in (None, {}, {"runs": []}, {"runs": [{"ts": "kaputt"}]}):
        assert LF.faellig(h, _JETZT) is True, h


def test_luecke_bleibt_unter_dem_alarm():
    import wm_data_integrity as W
    assert LF.ABSTAND_MIN + 15 + 12 < W.LIVE_SCAN_STALE_MIN, \
        "Abstand + Betfair-Takt + Laufzeit muss unter der Alarmschwelle bleiben"


def test_workflow_fragt_vor_dem_anstoss():
    src = open(".github/workflows/betfair.yml", encoding="utf-8").read()
    schritt = src.split("Live-Scan anstossen")[-1]
    assert schritt.index("live_scan_faellig.py") < schritt.index("dispatches")


def test_reihenfolge_der_liste_egal():
    """30.09.2026: health/poly-live-scan.json steht NEUESTE ZUERST — gelesen wurde runs[-1], der
    aelteste Lauf, und die Drossel griff nie. Gegentest mit echter Reihenfolge."""
    neu_zuerst = {"runs": [{"ts": (_JETZT - _td(minutes=m)).isoformat()} for m in (10, 25, 40, 55, 70)]}
    alt_zuerst = {"runs": list(reversed(neu_zuerst["runs"]))}
    assert LF.faellig(neu_zuerst, _JETZT) is False
    assert LF.faellig(alt_zuerst, _JETZT) is False
    assert round(LF.alter_min(neu_zuerst, _JETZT)) == 10


def test_echtes_health_artefakt_hat_diese_reihenfolge():
    """Haelt die Annahme fest, an der der Fehler hing: die neueste Zeile steht oben."""
    import json, os
    p = "health/poly-live-scan.json"
    if not os.path.exists(p):
        return
    runs = json.load(open(p, encoding="utf-8")).get("runs") or []
    if len(runs) >= 2:
        assert str(runs[0].get("startedAt")) >= str(runs[-1].get("startedAt"))
