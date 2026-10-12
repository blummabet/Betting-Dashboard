"""12.10.2026 (Lucas): „aus dem Burst nimm bitte Draw wetten raus" zur Karte
„🎯 1x2 — Draw · Coventry - Newcastle · $17.8K · alle @3.90". Reine Remis-Bursts gehen nicht mehr
raus, werden aber weiter gebucht. Auf dem alten Code liefert stumm_grund hier None."""
import stake_burst_push as S


def burst(auswahl, n=5, kat="Fußball", markt="1x2"):
    return {"wetten": [{"kat": kat, "phase": "vor", "liga": "Premier League", "markt": markt,
                        "auswahl": auswahl} for _ in range(n)]}


def test_remis_burst_ist_stumm():
    assert S.stumm_grund(burst("Draw")) == "Remis stumm (Lucas 12.10.)"
    assert S.stumm_grund(burst("X"))
    assert S.stumm_grund(burst(" draw "))


def test_team_und_verwandte_maerkte_bleiben_laut():
    assert S.stumm_grund(burst("Newcastle United FC")) is None
    assert S.stumm_grund(burst("Newcastle United FC", markt="Draw No Bet")) is None
    assert S.stumm_grund(burst("Wydad AC or Draw", markt="Double Chance")) is None


def test_spiel_burst_mit_remis_und_team_bleibt_laut():
    b = burst("Draw", n=3)
    b["wetten"] += burst("Coventry City", n=3)["wetten"]
    assert S.stumm_grund(b) is None


def test_kleine_liga_nutzt_denselben_filter():
    src = open(S.__file__, encoding="utf-8").read()
    assert "kl_senden = [b for b in kl_neu if not stumm_grund(b)]" in src
