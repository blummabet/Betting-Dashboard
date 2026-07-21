"""21.07.2026 (Lucas, MLS Inter Miami: „S. Reguilon (?), S. Reguilon (?)"): derselbe Spieler stand
doppelt in den Injury-Daten → doppelt gezählt (Impact aufgebläht) UND doppelt gelistet. Dedup nach
Spieler-Identität muss beides verhindern."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sharp_signals.injury_signal import _team_injury_impact_pp, _team_injury_offense_defense, _unique_players

THR = {"impact_BACKUP": 1.0, "impact_GK": 3.0, "impact_DEF": 2.0, "impact_MID": 2.0,
       "impact_FWD": 3.0, "max_per_team_pp": 20.0}


def _dup(name="S. Reguilon", pos="Defender"):
    p = {"name": name, "position": pos, "importance": "starter"}
    return {"players": [dict(p), dict(p)]}   # zweimal derselbe Spieler


def test_dedup_zaehlt_nicht_doppelt():
    imp, notes = _team_injury_impact_pp(_dup(), THR)
    assert notes.count("S. Reguilon (DEF)") == 1, "Name darf nur einmal erscheinen"
    assert imp == THR["impact_DEF"], "Impact darf NICHT doppelt gezählt werden"


def test_dedup_offense_defense_split():
    inj = {"players": [{"name": "X", "position": "Attacker", "importance": "starter"},
                       {"name": "X", "position": "Attacker", "importance": "starter"}]}
    off, dfn, notes = _team_injury_offense_defense(inj, THR)
    assert notes.count("X (FWD)") == 1
    assert off == THR["impact_FWD"], "Offense-Impact nicht doppelt"


def test_unique_players_nach_id_bevorzugt():
    # Gleiche id, anderer Name-Schreibweise → trotzdem ein Spieler.
    players = [{"id": 42, "name": "Reguilón"}, {"id": 42, "name": "S. Reguilon"}]
    assert len(_unique_players(players)) == 1


def test_verschiedene_spieler_bleiben():
    players = [{"name": "A"}, {"name": "B"}]
    assert len(_unique_players(players)) == 2


def test_leer_und_kaputt_robust():
    assert _unique_players(None) == []
    assert _unique_players([{"name": "A"}, "kaputt", 123]) == [{"name": "A"}]
