"""Tennis-Bursts live werden nicht mehr gesendet, aber weiter gebucht (01.10.2026).

Lucas: „diese ganzen Stake-Bursts zu ATP und WTA — die können ja nie positiv sein, oder?"
Nachgerechnet (95 abgerechnete Tennis-Bursts): live −9,3 % (Spiel, n=72) und +0,5 % (Auswahl,
n=17); die Turnierstufe trennt nicht (ATP/WTA −7,6 %, Challenger −12,4 %). Der Grund ist der
Mechanismus: live folgt das Geld dem Spielstand. Vor Anpfiff bleibt alles laut.
"""
import inspect

import stake_burst_push as S


def burst(kat, *phasen):
    return {"wetten": [{"kat": kat, "phase": p} for p in phasen]}


def test_tennis_live_und_gemischt_sind_stumm():
    assert S.stumm_grund(burst("Tennis", "live", "live"))
    assert S.stumm_grund(burst("Tennis", "vor", "live")), "beginnt vor Anpfiff, läuft live weiter"


def test_tennis_vor_anpfiff_bleibt_laut():
    assert S.stumm_grund(burst("Tennis", "vor", "vor")) is None


def test_andere_sportarten_live_bleiben_laut():
    assert S.stumm_grund(burst("Fußball", "live")) is None
    assert S.stumm_grund(burst("E-Sport", "live")) is None


def test_leerer_burst_kein_absturz():
    assert S.stumm_grund({}) is None


def test_main_filtert_vor_dem_deckel_und_bucht_trotzdem():
    # Gegentest zum alten Code: dort ging `neu` ungefiltert in zu_senden, und der stumme Burst
    # haette einem lauten den Platz unter dem Deckel weggenommen.
    src = inspect.getsource(S.main)
    assert "zu_senden(neu_laut)" in src
    assert "sp_laut[:SPIEL_MAX_PUSH]" in src
    assert src.count("stumm_grund(b) or (") == 2, "der Grund steht im Buch (push=false, pushGrund)"
