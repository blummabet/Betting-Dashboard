"""28.08.2026 — aus Lucas' Runner-Log von „Liga aktualisieren".

Fünf Polymarket-Namen liefen bei JEDEM Lauf ins Leere:

    ⚠️  Poly-Name 'FC Barcelona' passt auf MEHRERE Teams ['529', '540']
    ⚠️  Poly-Name 'FC Internazionale Milano' passt auf MEHRERE Teams ['489', '505']
    SKIP fl1-ang-ren: 'Stade Rennais FC 1901' → None
    SKIP fl1-tro-str: 'ES Troyes AC' → None
    SKIP lal-dep-val: 'RC Deportivo A Coruña' → None

Die beiden mehrdeutigen sind eine Nebenwirkung der Espanyol-Zeile in _POLY_NAME_ALIASES:
steht „RCD Espanyol de Barcelona" in der Map, matcht „FC Barcelona" per Token-Überlapp auf
529 UND 540 → der Resolver gibt korrekt None zurück („lieber kein Trade als der falsche") →
das Spiel fliegt raus. Barcelona und Inter waren damit seit Saisonstart nie handelbar; in
einem einzigen Lauf gingen 9 Fixtures verloren.

Diese Tests halten fest, dass die exakten Aliase greifen UND dass sie die Teams, gegen die
sie kollidierten, nicht ihrerseits kaputtmachen.
"""
import os
import sys
import json
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


_DATASET_MODULE = ("fetch_wm_poly_prices", "cocobet_dataset", "cocobet_config")


def _purge():
    for m in list(sys.modules):
        if m.startswith(_DATASET_MODULE):
            del sys.modules[m]


@pytest.fixture(scope="module")
def F():
    """Modul unter COCOBET_PROFILE=liga_default laden — und die Umgebung sauber zuruecksetzen.

    Ohne das Teardown leckt die gesetzte Umgebung in alle nachfolgenden Testdateien: die
    importieren dann versehentlich den Liga-Datensatz und schlagen fehl (erlebt mit
    tests/test_smart_money.py, das je nach Dateireihenfolge rot wurde).
    """
    vorher = {k: os.environ.get(k) for k in ("COCOBET_PROFILE", "COCOBET_DATASET")}
    os.environ["COCOBET_PROFILE"] = "liga_default"
    os.environ["COCOBET_DATASET"] = "liga"
    _purge()
    import fetch_wm_poly_prices as mod
    yield mod
    for k, v in vorher.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _purge()


@pytest.fixture(scope="module")
def dataset_namen():
    with open(os.path.join(REPO, "liga-data.json"), encoding="utf-8") as f:
        d = json.load(f)
    namen = {}
    for g in (d.get("groups") or {}).values():
        for t in (g.get("teams") or []):
            namen[str(t.get("id"))] = t.get("name")
    return namen


# Genau die Namen aus dem Log, mit der ID, die sie hätten treffen müssen.
AUS_DEM_LOG = [
    ("FC Barcelona",             "529"),
    ("FC Internazionale Milano", "505"),
    ("Stade Rennais FC 1901",     "94"),
    ("ES Troyes AC",             "110"),
    ("RC Deportivo A Coruña",    "544"),
]

# Die Teams, gegen die die zwei mehrdeutigen Namen kollidiert sind — dürfen nicht kippen.
KOLLISIONSPARTNER = [
    ("RCD Espanyol de Barcelona", "540"),
    ("AC Milan",                  "489"),
]


class TestNamenAusDemLog:
    @pytest.mark.parametrize("name,erwartet", AUS_DEM_LOG)
    def test_wird_aufgeloest(self, F, name, erwartet):
        assert F.resolve_team_id(name) == erwartet

    @pytest.mark.parametrize("name,erwartet", KOLLISIONSPARTNER)
    def test_kollisionspartner_bleibt_richtig(self, F, name, erwartet):
        assert F.resolve_team_id(name) == erwartet

    def test_barcelona_und_espanyol_sind_verschieden(self, F):
        """Der eigentliche Fehler in einer Zeile: zwei Klubs, ein Wort im Namen."""
        assert F.resolve_team_id("FC Barcelona") != F.resolve_team_id("RCD Espanyol de Barcelona")

    def test_inter_und_milan_sind_verschieden(self, F):
        assert F.resolve_team_id("FC Internazionale Milano") != F.resolve_team_id("AC Milan")


class TestAliasTabelleBleibtGesund:
    def test_jeder_alias_zeigt_auf_ein_existierendes_team(self, F, dataset_namen):
        """Ein Alias auf eine ID, die es im Datensatz nicht gibt, wäre ein stiller Fehltrade."""
        for name, tid in F._POLY_NAME_ALIASES.items():
            assert tid in dataset_namen, f"Alias '{name}' zeigt auf unbekannte ID {tid}"

    def test_keine_zwei_aliase_auf_dasselbe_team(self, F):
        ids = list(F._POLY_NAME_ALIASES.values())
        assert len(ids) == len(set(ids)), f"doppelt vergebene IDs: {ids}"

    def test_alias_schlaegt_fuzzy(self, F):
        """Exakter Treffer muss VOR dem Token-Match greifen — sonst nützt die Tabelle nichts."""
        for name, tid in F._POLY_NAME_ALIASES.items():
            assert F.resolve_team_id(name) == tid, f"'{name}' fällt trotz Alias in den Fuzzy-Pfad"

    def test_alle_dataset_namen_bleiben_eindeutig(self, F, dataset_namen):
        """Regression: ein neuer Alias darf keinen bestehenden Klubnamen mehrdeutig machen."""
        kaputt = [(tid, nm) for tid, nm in dataset_namen.items()
                  if nm and F.resolve_team_id(nm) != tid]
        assert not kaputt, f"Klubnamen lösen nicht mehr auf sich selbst auf: {kaputt[:5]}"


class TestUnbekanntesBleibtUnbekannt:
    def test_phantasiename_gibt_none(self, F):
        assert F.resolve_team_id("Sportverein Nirgendwo 1899") is None

    def test_leer_gibt_none(self, F):
        assert F.resolve_team_id("") is None
        assert F.resolve_team_id(None) is None
