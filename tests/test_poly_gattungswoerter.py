"""Ein Poly-Treffer darf nicht nur auf Gattungswoertern stehen — 29.09.2026.

„FC Halifax Town v Boston Utd" und „Slough Town v Ebbsfleet Utd" bekamen den Markt von
Hartlepool v Harrogate Town: je Seite genau ein geteiltes Wort („town", „united"), 0,5 + 0,5 = 1,0.
"""
import betfair_consensus as BC

POOL = [{"key": "enl-har-ht-2026-09-29", "prices": {"Hartlepool United FC": 0.34, "Draw": 0.28,
                                                      "Harrogate Town AFC": 0.38}}]
KO = "2026-09-29T18:45:00Z"


def _m(h, a):
    return {"home": h, "away": a, "kickoff": KO}


def test_das_richtige_spiel_behaelt_seinen_markt():
    b = BC._best_poly_entry(_m("Hartlepool", "Harrogate Town"), POOL)
    assert b and b[0]["key"] == "enl-har-ht-2026-09-29"


def test_die_zwei_falschen_vom_29_09_bekommen_nichts():
    assert BC._best_poly_entry(_m("FC Halifax Town", "Boston Utd"), POOL) is None
    assert BC._best_poly_entry(_m("Slough Town", "Ebbsfleet Utd"), POOL) is None


def test_gattungswort_allein_unterscheidet_nicht():
    assert not BC._unterscheidet("Real Madrid", "Real Sociedad", set())
    assert not BC._unterscheidet("Bristol City", "Manchester City", set())
    assert BC._unterscheidet("Leeds", "Leeds United FC", set())
    assert BC._unterscheidet("Man Utd", "Manchester United", set())


def test_gegenbeweis_der_alte_score_haette_getroffen():
    s = BC._name_score("FC Halifax Town", "Harrogate Town AFC") + BC._name_score("Boston Utd", "Hartlepool United FC")
    assert s > 0.99, "ohne die neue Regel laege der Fehlgriff ueber der Schwelle"


def test_vereinsnamen_die_wie_gattung_aussehen_bleiben_verbindbar():
    """Gegenprobe zur Liste: diese Paare teilen oft NUR dieses eine Wort und muessen halten."""
    for a, b in (("Inter", "Inter Milan"), ("Sporting Lisbon", "Sporting CP"),
                 ("Athletic Bilbao", "Athletic Club"), ("Racing Club", "Racing Club de Avellaneda")):
        assert BC._unterscheidet(a, b, set()), (a, b)
