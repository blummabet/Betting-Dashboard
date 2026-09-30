"""30.09.2026 — „Roots FC v Sporting Club Bengaluru: name — bester Kandidat Braga v Sporting Lisbon"
war ein Fehlalarm: ein gemeinsames Wort auf einer Seite ist kein Kandidat."""
import betfair_consensus as B

M = {"home": "Roots FC", "away": "Sporting Club Bengaluru", "kickoff": "2026-09-30T10:00:00Z"}
EVS = [{"home": "Braga", "away": "Sporting Lisbon", "commence": "2026-09-30T19:00:00Z", "key": "soccer_portugal"}]


def test_ein_allerweltswort_ist_kein_namensfehler():
    g = B.anker_grund(M, None, EVS)
    assert g["grund"] == "kein_kandidat", "Gegentest: der alte Code meldete „name“"


def test_zur_selben_zeit_bleibt_es_ein_namensfehler():
    """Dasselbe Allerweltswort, aber gleicher Anpfiff: dann kann es eine echte Luecke sein."""
    ev = [dict(EVS[0], commence=M["kickoff"])]
    assert B.anker_grund(M, None, ev)["grund"] == "name"
