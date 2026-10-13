"""12.10.2026 (Lucas: „Serien Watch – heute nehmen wir raus") und 13.10.2026 (zur
„📒 Serien-Abrechnung … Auxerre 16× in Folge": „Das auch bitte aus public Push entfernen"):
Watch UND Recap der Serien laufen nur mit SERIEN_WATCH_PUBLIC=true. Der Liga-Pick-Recap
(„Liga Recap → Public") ist etwas anderes und bleibt."""
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _if_zeile(t, schritt):
    i = t.index(schritt)
    return next(z for z in t[i:i + 800].split("\n") if z.strip().startswith("if:"))


def test_watch_und_recap_sind_hinter_der_variable():
    for name in ("update-liga.yml", "update-mls.yml"):
        t = (WF / name).read_text(encoding="utf-8")
        for schritt in ("Serien-Watch (PRE-Match)", "Serien-Recap (POST-Match)"):
            assert "vars.SERIEN_WATCH_PUBLIC == 'true' &&" in _if_zeile(t, schritt), (name, schritt)


def test_pick_recap_bleibt():
    t = (WF / "update-liga.yml").read_text(encoding="utf-8")
    assert "SERIEN_WATCH_PUBLIC" not in _if_zeile(t, "Liga Recap → Public (POST-Match)")
