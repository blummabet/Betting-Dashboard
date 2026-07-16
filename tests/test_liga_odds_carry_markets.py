"""15.07.2026 — O/U-/AH-Quoten dürfen nicht gelöscht werden, wenn die API sie mal nicht liefert.

BEFUND (Lucas: „quotentechnisch was von MLS? in 2 Tagen geht's los"): Der erste MLS-Spieltag stand
komplett OHNE O/U da, obwohl die Spiele vorher O/U hatten. Ursache: TheOddsAPI liefert `totals`
für die MLS nur sporadisch. build_odds_entry baut den Eintrag bei JEDEM Lauf komplett neu und
übernahm O/U nur `if prices.get(k)` — jeder Fetch ohne totals löschte also die letzte Quote. Die
Spiele nahe am Anpfiff werden am häufigsten gerefresht → traf genau sie am härtesten.

Fix wie bei odds_open: fehlt die frische Quote, die letzte bekannte behalten. Gilt Liga + MLS.
"""
import os

import pytest


@pytest.fixture
def F():
    os.environ["COCOBET_DATASET"] = "mls"
    import importlib
    import cocobet_dataset
    importlib.reload(cocobet_dataset)
    import fetch_liga_odds as _F
    importlib.reload(_F)
    return _F


def _mit_ou(**extra):
    return {"hw": 1.90, "dr": 3.40, "aw": 4.00, "o25": 1.85, "u25": 1.95,
            "bookmaker": "pinnacle", **extra}


def _ohne_ou(**extra):
    return {"hw": 1.92, "dr": 3.40, "aw": 3.90, "bookmaker": "pinnacle", **extra}


class TestOuCarry:
    def test_ou_bleibt_wenn_neuer_fetch_keine_hat(self, F):
        e1 = F.build_odds_entry(_mit_ou(), {}, "2026-07-15T10:00:00Z")
        e2 = F.build_odds_entry(_ohne_ou(), e1, "2026-07-15T12:00:00Z")
        assert e2.get("o25") == 1.85, "O/U wurde gelöscht statt behalten"
        assert e2.get("u25") == 1.95

    def test_frische_quote_ueberschreibt_die_getragene(self, F):
        e1 = F.build_odds_entry(_mit_ou(), {}, "2026-07-15T10:00:00Z")
        e2 = F.build_odds_entry(_ohne_ou(), e1, "2026-07-15T12:00:00Z")
        e3 = F.build_odds_entry(_mit_ou(o25=1.70, u25=2.10), e2, "2026-07-15T14:00:00Z")
        assert e3.get("o25") == 1.70, "frische API-Quote muss die getragene ersetzen"

    def test_stale_marker_zeigt_den_letzten_echten_stand(self, F):
        e1 = F.build_odds_entry(_mit_ou(), {}, "2026-07-15T10:00:00Z")
        e2 = F.build_odds_entry(_ohne_ou(), e1, "2026-07-15T12:00:00Z")
        assert e2.get("marketsCarriedAt") == "2026-07-15T12:00:00Z"
        assert e2.get("marketsFreshAt") == "2026-07-15T10:00:00Z", "freshAt muss der letzte echte Stand sein"
        # Nach frischem Fetch ist der Carried-Marker weg und freshAt aktuell.
        e3 = F.build_odds_entry(_mit_ou(), e2, "2026-07-15T14:00:00Z")
        assert "marketsCarriedAt" not in e3
        assert e3.get("marketsFreshAt") == "2026-07-15T14:00:00Z"

    def test_nie_dagewesene_ou_wird_nicht_erfunden(self, F):
        # St. Louis–Sporting hatte NIE O/U → es darf auch keins auftauchen.
        e1 = F.build_odds_entry(_ohne_ou(), {}, "2026-07-15T10:00:00Z")
        e2 = F.build_odds_entry(_ohne_ou(), e1, "2026-07-15T12:00:00Z")
        assert e2.get("o25") is None

    def test_ah_ladder_wird_ebenso_getragen(self, F):
        e1 = F.build_odds_entry(_mit_ou(ahLadder={"-0.5": [1.9, 2.0]}, ahH_n050=1.9),
                                {}, "2026-07-15T10:00:00Z")
        e2 = F.build_odds_entry(_ohne_ou(), e1, "2026-07-15T12:00:00Z")
        assert e2.get("ahLadder") == {"-0.5": [1.9, 2.0]}, "AH-Leiter muss ebenfalls überleben"
        assert e2.get("ahH_n050") == 1.9

    def test_poly_patches_ueberleben_den_odds_lauf(self, F):
        """15.07.2026: fetch_wm_poly_prices patcht poly_* NACH dem Odds-Lauf. Ohne Durchreichen
        löschte der nächste 2h-Odds-Lauf sie → anstehende Spiele standen ständig ohne Poly da
        (Steam-Lag, Poly-Edge, Whale-Tab tot). Poly kommt aus einem anderen Prozess → aus existing."""
        existing = {"hw": 1.9, "dr": 3.4, "aw": 4.0,
                    "poly_hw": 0.55, "poly_dr": 0.25, "poly_aw": 0.20,
                    "poly_vol": 1200, "poly_slug": "mls-mtl-tor"}
        e = F.build_odds_entry(_ohne_ou(), existing, "2026-07-15T12:00:00Z")
        assert e.get("poly_hw") == 0.55, "Poly-Patch wurde vom Odds-Lauf gelöscht"
        assert e.get("poly_vol") == 1200
        assert e.get("poly_slug") == "mls-mtl-tor"

    def test_1x2_wird_immer_frisch_gesetzt(self, F):
        """1X2 (der Sharp-Anker) kommt zuverlässig und soll NICHT getragen werden — sonst
        würde eine tote Linie als aktuell verkauft. Nur die lückenhaften Märkte werden getragen."""
        e1 = F.build_odds_entry(_mit_ou(), {}, "2026-07-15T10:00:00Z")
        e2 = F.build_odds_entry(_ohne_ou(hw=2.50), e1, "2026-07-15T12:00:00Z")
        assert e2.get("hw") == 2.50, "1X2 muss der frische Wert sein, nicht der alte"
