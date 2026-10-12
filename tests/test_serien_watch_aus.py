"""12.10.2026 (Lucas: „Serien Watch – heute nehmen wir raus"): der Public-Watch laeuft nur mit
SERIEN_WATCH_PUBLIC=true. Der Recap bleibt."""
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def test_watch_ist_hinter_der_variable():
    for name in ("update-liga.yml", "update-mls.yml"):
        t = (WF / name).read_text(encoding="utf-8")
        i = t.index("Serien-Watch (PRE-Match)")
        zeile = t[i:i + 400].split("\n")[1]
        assert "vars.SERIEN_WATCH_PUBLIC == 'true' &&" in zeile, name
        assert "TG_STREAK_MODE:   recap" in t, "Recap bleibt"
