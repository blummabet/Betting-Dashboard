"""29.09.2026 (Lucas: „⚡ Live-Scan (ein Durchlauf) (cancelled) — in letzter Zeit paar mal
abgebrochen"). Lauf 36627837915: 789 s gegen einen Deckel von 12 Min, Median sonst 251 s.
Der Live-Lauf schlug bei jedem Durchlauf bis zu 60 Maerkte einzeln nach (je bis 12 s x 2),
deren Ergebnis `main_live` wegwirft — Aufloesungen schreibt nur `main()`."""
import poly_money_broad as P


def _still(monkeypatch):
    aufrufe = []
    monkeypatch.setattr(P, "_get", lambda url: [])
    monkeypatch.setattr(P, "_tags", lambda: [])
    monkeypatch.setattr(P, "_load_league_registry", lambda: [])
    monkeypatch.setattr(P, "_save_league_registry", lambda *a, **k: None)
    monkeypatch.setattr(P, "backfill_lauf", lambda seen, *a, **k: aufrufe.append(seen) or [])
    return aufrufe


def test_live_lauf_schlaegt_nicht_nach(monkeypatch):
    aufrufe = _still(monkeypatch)
    P.fetch_markets(live_only=True)
    assert aufrufe == [], "Gegentest: der alte Code rief den Nachschlag auch im Live-Lauf"


def test_voller_lauf_schlaegt_weiter_nach(monkeypatch):
    aufrufe = _still(monkeypatch)
    P.fetch_markets(live_only=False)
    assert len(aufrufe) == 1, "der Nachschlag ist fuers Settlement noetig — nur nicht im Live-Lauf"
