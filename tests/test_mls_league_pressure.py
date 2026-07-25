"""13.07.2026 — Playoff-Druck für die MLS (Lucas: „MLS startet Freitag").

Vorher kannte league_pressure nur ENG/ESP/ITA/GER/FRA → für MLS gab LEAGUE_META.get("MLS") None
zurück und das Signal schwieg, obwohl die Tabelle längst vorlag (15 Runden gespielt).

MLS ist strukturell anders, deshalb reicht keine sechste Zeile mit europäischen Annahmen:
  · KEIN Abstieg → der „Abstiegskampf"-Zweig darf nie greifen (sonst erfinden wir Druck)
  · Das Rennen läuft JE CONFERENCE — Gesamtrang ≠ Conference-Rang
  · Playoff-Schnitt: Top 9 je Conference; darunter jagt JEDES Team weiter
"""
import json
from pathlib import Path

import pytest

from sharp_signals.league_pressure import (
    LEAGUE_META, DEFAULT_CHASE_WINDOW, team_pressure, _conference_view, _conference_of,
)

REPO = Path(__file__).resolve().parent.parent


def _row(team, pos, pts, gd=0):
    return {"team": team, "pos": pos, "points": pts, "gd": gd}


class TestConferenceDaten:
    def test_datei_hat_30_teams_15_15(self):
        raw = json.loads((REPO / "mls_conferences.json").read_text("utf-8"))
        teams = raw["teams"]
        assert len(teams) == 30
        east = [t for t in teams.values() if t["conference"] == "East"]
        west = [t for t in teams.values() if t["conference"] == "West"]
        assert len(east) == 15 and len(west) == 15

    def test_die_beiden_LA_klubs_sind_beide_west(self):
        # LA Galaxy (1605) und LAFC (1616) — die Verwechslungsgefahr, die uns schon beim
        # Poly-Namensmatching fast einen Trade auf das falsche Team gekostet hätte.
        assert _conference_of("1605") == "West"
        assert _conference_of("1616") == "West"

    def test_geografische_gegenprobe(self):
        """Unabhängige Kontrolle: Conference muss zur Geografie passen (Längengrad-Schnitt −88°).
        Beide Methoden wurden beim Anlegen gekreuzt — dieser Test hält das fest."""
        venues = json.loads((REPO / "mls_venues.json").read_text("utf-8"))
        raw = json.loads((REPO / "mls_conferences.json").read_text("utf-8"))["teams"]
        for tid, meta in raw.items():
            lon = (venues.get(tid) or {}).get("lon")
            if lon is None:
                continue
            erwartet = "East" if lon > -88 else "West"
            assert meta["conference"] == erwartet, f"{meta['name']}: lon {lon} → {erwartet}"


class TestMlsMeta:
    def test_mls_ist_bekannt(self):
        assert "MLS" in LEAGUE_META

    def test_kein_abstieg(self):
        assert LEAGUE_META["MLS"]["rel"] == 0

    def test_playoff_schnitt_top9(self):
        assert LEAGUE_META["MLS"]["europe_cut"] == 9

    def test_conference_flag(self):
        assert LEAGUE_META["MLS"].get("conference") is True

    def test_europaeische_ligen_unveraendert(self):
        # Anti-Drift: die MLS-Erweiterung darf die 5 Ligen NICHT anfassen.
        assert LEAGUE_META["ENG"] == {"total": 20, "rounds": 38, "europe_cut": 7, "rel": 3}
        assert LEAGUE_META["GER"]["rel"] == 3
        assert DEFAULT_CHASE_WINDOW == 3


class TestConferenceView:
    def test_schneidet_auf_conference_zu_und_nummeriert_neu(self):
        rows = [
            _row("9569", 1, 33),    # Nashville  — East
            _row("1603", 2, 32),    # Vancouver  — West
            _row("9568", 3, 31),    # Miami      — East
            _row("1596", 4, 32),    # San Jose   — West
        ]
        sub, me = _conference_view(rows, "9568")     # Miami → East
        assert [r["team"] for r in sub] == ["9569", "9568"]
        assert me["pos"] == 2, "Miami ist Gesamtrang 3, aber Conference-Rang 2"

    def test_ohne_zuordnung_kein_raten(self):
        sub, me = _conference_view([_row("99999", 1, 10)], "99999")
        assert sub == [] and me is None


class TestPlayoffDruck:
    def _east(self, pts_by_pos):
        """Ost-Tabelle aus echten Team-IDs bauen (Punkte absteigend)."""
        east_ids = [t for t in json.loads((REPO / "mls_conferences.json").read_text("utf-8"))["teams"]
                    if _conference_of(t) == "East"]
        return [_row(tid, i + 1, pts_by_pos[i]) for i, tid in enumerate(east_ids)]

    def test_kein_druck_in_der_ersten_saisonhaelfte(self):
        rows = self._east([40 - 2 * i for i in range(15)])
        p, _, _ = team_pressure(rows[8], rows, LEAGUE_META["MLS"], rounds_left=19)   # Runde 15/34
        assert p == 0.0, "Runde 15 von 34 → Zeitfaktor 0, kein Endspurt-Druck"

    def test_team_auf_der_playoff_kippe_hat_druck(self):
        rows = self._east([40 - 2 * i for i in range(15)])
        p9, m9, b9 = team_pressure(rows[8], rows, LEAGUE_META["MLS"], rounds_left=6)   # Platz 9 = Schnitt
        assert p9 > 0 and m9 == "win"
        assert b9 == "hold", "Platz 9 = am Schnitt → hold-Zweig (starke Seite, darf Sieg boosten)"

    def test_schlusslicht_jagt_weiter_statt_abstiegskampf(self):
        """In Europa wäre der Letzte im Abstiegskampf. In der MLS gibt es keinen Abstieg —
        er jagt die Playoffs. Der Abstiegs-Zweig darf NICHT greifen."""
        rows = self._east([40 - 2 * i for i in range(15)])
        p, motive, branch = team_pressure(rows[14], rows, LEAGUE_META["MLS"], rounds_left=8)
        assert motive in ("win", "dead")
        assert branch in ("chase", "dead"), "Schlusslicht jagt (chase) oder ist raus (dead) — nie releg"
        # Und die Begründung darf nie „Abstiegskampf" heißen:
        from sharp_signals import league_pressure as LP
        src = (REPO / "sharp_signals" / "league_pressure.py").read_text("utf-8")
        assert "has_rel" in src, "Abstiegs-Zweig muss an rel>0 gebunden sein"

    def test_rechnerisch_raus_ist_dead(self):
        # Letzter mit 5 Punkten, Schnitt bei 40 → mit 2 Runden (6 Punkte) nicht erreichbar.
        pts = [40] * 9 + [20, 18, 16, 12, 8, 5]
        rows = self._east(pts)
        p, motive, branch = team_pressure(rows[14], rows, LEAGUE_META["MLS"], rounds_left=2)
        assert p == 0.0 and motive == "dead"


class TestRichtungsFix:
    """25.07.2026 (Backtest): der Jagd-Zweig (unter dem Schnitt) darf keinen Sieg-Boost mehr geben —
    das schwächere Team auf Sieg zu heben war anti-prädiktiv. Halten (am Schnitt) darf weiter."""

    def _east(self, pts_by_pos):
        east_ids = [t for t in json.loads((REPO / "mls_conferences.json").read_text("utf-8"))["teams"]
                    if _conference_of(t) == "East"]
        return [_row(tid, i + 1, pts_by_pos[i]) for i, tid in enumerate(east_ids)]

    def _ctx(self, home_id, away_id, rows, md=28):
        return {"group_id": "MLS", "standings": {"MLS": rows}, "matchday": md,
                "home_id": home_id, "away_id": away_id}

    def test_jagd_gibt_keinen_sieg_boost(self):
        from sharp_signals.league_pressure import LeaguePressureSignal
        # Enges Ost-Rennen; Heim ist Platz 11 (chase, unter Schnitt 9), Gegner Platz 14 (chase/dead).
        rows = self._east([40, 38, 36, 34, 32, 30, 28, 26, 24, 23, 22, 20, 18, 16, 14])
        r = LeaguePressureSignal().evaluate({"market": "Heimsieg"}, self._ctx(rows[10]["team"], rows[13]["team"], rows))
        # chase-Heim ohne starken Gegner-Druck → kein Boost → unter der 0.3-Schwelle → None.
        assert r is None or r.score <= 0

    def test_halten_gibt_sieg_boost(self):
        from sharp_signals.league_pressure import LeaguePressureSignal
        # Heim Platz 8 (hold, über Schnitt), enger Vorsprung auf ersten Verfolger → hold-Boost;
        # Gegner Platz 15 rechnerisch raus (dead).
        rows = self._east([50, 48, 46, 44, 42, 40, 38, 30, 29, 28, 27, 26, 25, 24, 7])
        r = LeaguePressureSignal().evaluate({"market": "Heimsieg"}, self._ctx(rows[7]["team"], rows[14]["team"], rows))
        assert r is not None and r.score > 0
        assert r.metadata.get("homeBranch") == "hold"
