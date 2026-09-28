"""Nations League: Pinnacle darf nicht am Abgleich verloren gehen — 27.09.2026.

Lucas: „Nations League muss prinzipiell funktionieren, egal an welcher Stelle — da gibt es zu
100 % Quoten." Gemessen: fuenf Spiele (Austria v Kosovo, Gibraltar v Andorra, Israel v Republic
of Ireland, Northern Ireland v Hungary, Scotland v Switzerland) in 24 von 24 Laeufen ohne
Pinnacle, Norway und Denmark aus DEMSELBEN Wettbewerb in 24 von 24 mit. Zwei Stellen, an denen
Pinnacle still verloren ging, werden hier festgehalten.
"""
import betfair_consensus as BC

KO = "2026-09-27T18:45:00Z"


def _bk(key, h_name, h, d, a_name, a):
    return {"key": key, "markets": [{"key": "h2h", "outcomes": [
        {"name": h_name, "price": h}, {"name": "Draw", "price": d}, {"name": a_name, "price": a}]}]}


def _ev(home, away, books, ko=KO):
    return {"home_team": home, "away_team": away, "commence_time": ko, "bookmakers": books}


M = {"home": "Israel", "away": "Republic of Ireland", "kickoff": KO}


# ── Fall 1: Pinnacle steht im Event, schreibt ein Team aber anders ─────────────────────
def test_pinnacle_mit_anderer_schreibweise_wird_zugeordnet():
    e = BC.parse_event(_ev("Israel", "Republic of Ireland", [
        _bk("bet365", "Israel", 2.6, 3.2, "Republic of Ireland", 2.8),
        _bk("pinnacle", "Israel", 2.65, 3.3, "Ireland", 2.9)]))
    assert e["pinn"] is not None, 'Pinnacle fiel an Ireland statt Republic of Ireland heraus'
    assert e["pinnOdds"] == [2.65, 3.3, 2.9]
    assert "pinnacle" in e["buecher"]


def test_gegenbeweis_ein_name_der_zum_anderen_team_passt_wird_nicht_geraten():
    """Israel fehlt, aber der fremde Name passt auf den Gegner — dann keine Zuordnung."""
    e = BC.parse_event(_ev("Israel", "Republic of Ireland", [
        _bk("pinnacle", "Ireland U21", 2.65, 3.3, "Republic of Ireland", 2.9)]))
    assert e["pinn"] is None
    assert e.get("pinnRoh") == ["Ireland U21"], "der Beweis steht im Artefakt"


# ── Fall 2: die API fuehrt das Spiel zweimal, Pinnacle steht im zweiten ─────────────────
def test_pinnacle_aus_dem_zweiten_event_desselben_spiels():
    ohne = BC.parse_event(_ev("Israel", "Republic of Ireland", [
        _bk("bet365", "Israel", 2.6, 3.2, "Republic of Ireland", 2.8)]))
    mit = BC.parse_event(_ev("Israel", "Ireland", [
        _bk("pinnacle", "Israel", 2.65, 3.3, "Ireland", 2.9)]))
    ev = BC.match_event(M, [ohne, mit])
    assert ev is not None and not ev.get("pinn"), "Ausgangslage: das erste Event gewinnt, ohne Pinnacle"
    ev2 = BC.pinn_nachtragen(M, ev, [ohne, mit])
    assert ev2["pinn"] is not None
    assert ev2["softOdds"] == ev["softOdds"], "die Soft-Seite bleibt vom ersten Event"
    assert ev2.get("pinnQuelle")


def test_gegenbeweis_anderes_spiel_oder_andere_zeit_liefert_kein_pinnacle():
    ohne = BC.parse_event(_ev("Israel", "Republic of Ireland", [
        _bk("bet365", "Israel", 2.6, 3.2, "Republic of Ireland", 2.8)]))
    fremd = BC.parse_event(_ev("Moldova", "Faroe Islands", [
        _bk("pinnacle", "Moldova", 2.0, 3.2, "Faroe Islands", 4.0)]))
    spaeter = BC.parse_event(_ev("Israel", "Ireland", [
        _bk("pinnacle", "Israel", 2.65, 3.3, "Ireland", 2.9)], ko="2027-03-20T18:45:00Z"))
    ev = BC.match_event(M, [ohne])
    assert not BC.pinn_nachtragen(M, ev, [ohne, fremd]).get("pinn")
    assert not BC.pinn_nachtragen(M, ev, [ohne, spaeter]).get("pinn"), "Rueckspiel im Maerz ist ein anderes Spiel"


def test_anker_grund_sagt_ob_pinnacle_im_event_war():
    ohne = BC.parse_event(_ev("Israel", "Republic of Ireland", [
        _bk("bet365", "Israel", 2.6, 3.2, "Republic of Ireland", 2.8)]))
    g = BC.anker_grund(M, BC.match_event(M, [ohne]), [ohne])
    assert g["grund"] == "kein_pinnacle"
    assert g["pinnacleImEvent"] is False and g["nBuecher"] == 1


def test_beide_stellen_im_lauf_benutzen_den_nachtrag():
    import inspect
    src = inspect.getsource(BC.main)
    assert src.count("pinn_nachtragen(") == 2, "Anker-Liste UND Konsens-Spiele"


# ── Waechter ────────────────────────────────────────────────────────────────────────
class _Ctx:
    def __init__(self, games):
        self.consensus = {"games": games}


def test_waechter_rot_wenn_pinnacle_im_event_stand():
    import betfair_data_integrity as I
    c = I.check_pinnacle_nicht_verworfen(_Ctx([{"league": "UEFA Nations League", "ankerGrund": {
        "spiel": "Israel v Republic of Ireland", "grund": "kein_pinnacle", "pinnacleImEvent": True,
        "nBuecher": 20, "pinnRoh": ["Ireland U21"]}}]))
    assert c["nFail"] == 1 and "Ireland U21" in c["failures"][0]


def test_waechter_still_wenn_die_quelle_kein_pinnacle_hat():
    import betfair_data_integrity as I
    c = I.check_pinnacle_nicht_verworfen(_Ctx([{"league": "UEFA Nations League", "ankerGrund": {
        "spiel": "Austria v Kosovo", "grund": "kein_pinnacle", "pinnacleImEvent": False, "nBuecher": 17}}]))
    assert c["nFail"] == 0
    assert "Austria v Kosovo" in c.get("note", "") or "Austria v Kosovo" in str(c)
