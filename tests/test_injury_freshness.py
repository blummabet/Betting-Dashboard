"""13.07.2026 — Ausfall-Liste = aktueller Stand, nicht Saison-Archiv.

BEFUND (Lucas: „MLS startet Freitag — haben wir die Saisondaten am Schirm?"):
Die MLS-Verletzungsdaten listeten **116 Ausfälle für einen 30-Mann-Kader**. Ursache:
/injuries?league&season liefert einen Eintrag JE FIXTURE — über 15 gespielte Runden sammelt sich
ein Archiv aller je gefehlten Spieler an. Jüngster Eintrag: Mai. Wir schrieben Juli.

Bei der WM (Turnier über 4 Wochen) fiel das nie auf. Dass das injury-Signal trotzdem schwieg, war
Glück, kein Schutz: hätte es gefeuert, hätten wir jedem Team dauerhaft eine halbe Mannschaft
„verletzt" gerechnet und Favoriten grundlos abgewertet.

ZUSÄTZLICH gefunden: wm_data_integrity lief unter COCOBET_DATASET=mls gegen liga-data.json und
schrieb liga_status.json → der MLS-Status war nie echt, und der neue Guard meldete deshalb
fälschlich „0 Fehler". Ein Guard, der die falsche Datei prüft, beruhigt nur.
"""
from datetime import datetime, timedelta, timezone

import pytest

import wm_data_integrity as W


def _ctx(injuries, squads=None):
    wm = {"injuries": injuries, "squads": squads or {}, "_meta": {"profile": "mls_default"}}
    return W.IntegrityCtx(wm=wm, poly={}, schedule={}, venues={}, history={}, streaks={})


def _p(name, tage_alt):
    d = (datetime.now(timezone.utc) - timedelta(days=tage_alt)).date().isoformat()
    return {"name": name, "type": "Injury", "reason": "", "status": "missing",
            "fixture": f"{d}T19:00:00+00:00"}


class TestInjuryGuard:
    def test_archiv_wird_erkannt(self):
        """Der echte MLS-Fall: mehr Ausfälle als Kaderspieler."""
        inj = {"1603": {"players": [_p(f"Spieler {i}", 5) for i in range(116)]}}
        squads = {"1603": {"players": [{"name": f"S{i}"} for i in range(30)]}}
        r = W.check_injuries_plausible(_ctx(inj, squads))
        assert not r["ok"]
        assert "116" in r["failures"][0] and "30" in r["failures"][0]

    def test_ohne_kaderdaten_greift_die_absolute_grenze(self):
        inj = {"1603": {"players": [_p(f"S{i}", 3) for i in range(60)]}}
        r = W.check_injuries_plausible(_ctx(inj))
        assert not r["ok"], "60 Ausfälle sind nie ein echter Ausfallstand"

    def test_veraltete_daten_werden_erkannt(self):
        """Jüngster Eintrag Mai, heute Juli → der Fetcher liefert nichts Aktuelles mehr."""
        inj = {"1603": {"players": [_p("A. Franco", 70)]}}
        r = W.check_injuries_plausible(_ctx(inj))
        assert not r["ok"]
        assert any("Tage alt" in f for f in r["failures"])

    def test_plausibler_stand_ist_gruen(self):
        inj = {"1603": {"players": [_p("A. Franco", 2), _p("B. White", 5)]},
               "1607": {"players": [_p("C. Duran", 1)]}}
        squads = {"1603": {"players": [{"name": f"S{i}"} for i in range(28)]}}
        r = W.check_injuries_plausible(_ctx(inj, squads))
        assert r["ok"], r["failures"]

    def test_keine_daten_ist_kein_fehler(self):
        # Früh in der Saison völlig normal — daraus keinen Alarm bauen.
        r = W.check_injuries_plausible(_ctx({}))
        assert r["ok"]


class TestFetcherDedupUndFenster:
    def test_konstante_existiert_und_ist_grosszuegig(self):
        import fetch_wm_injuries as F
        assert F.INJURY_RECENT_DAYS >= 14, "zu eng → echte Langzeitverletzungen fielen raus"

    def test_juengster_eintrag_gewinnt(self):
        """Vorher gewann im Per-Team-Pfad der ERSTE (= älteste) Eintrag. Ein im Februar verletzter,
        längst genesener Spieler blieb damit dauerhaft „aktuell verletzt"."""
        import inspect
        import fetch_wm_injuries as F
        src = inspect.getsource(F.fetch_sidelined_per_team)
        assert "neueste" in src, "Per-Team-Pfad muss den jüngsten Eintrag behalten"
        assert "fenster" in src, "Per-Team-Pfad braucht das Aktualitätsfenster"

    def test_liga_modus_nutzt_liga_season(self):
        """War hart auf WM_SEASON — im Liga-Modus die falsche Saison."""
        import inspect
        import fetch_wm_injuries as F
        src = inspect.getsource(F.fetch_sidelined_per_team)
        assert "LIGA_SEASON if _IS_LIGA else WM_SEASON" in src


class TestGuardsLaufenAufDemRichtigenDatensatz:
    def test_cli_liest_nicht_mehr_hart_liga_data(self):
        """13.07.2026: unter COCOBET_DATASET=mls liefen ALLE Guards gegen liga-data.json und
        schrieben liga_status.json. Der MLS-Status war nie echt."""
        from pathlib import Path
        src = Path(W.__file__).read_text("utf-8")
        tail = src.split("def run_checks")[1]
        assert 'load("liga-data.json")' not in tail, "Datensatz-Datei muss aus cocobet_dataset kommen"
        assert '(B / "liga_status.json").write_text' not in tail, "Status muss datensatz-eigen sein"
