"""29.09.2026 (Lucas' Übersicht-Check): „263 Ligen mit mindestens 30 Plays · 8 belegt" stand
gruen da — bei 263 gleichzeitig geprueften Ligen legt der Zufall allein 13,2 ueber die Huerde."""
import freigabe as F


def _liga(i, lb):
    return {"liga": "Liga %d" % i, "n": 40, "roiLb": lb, "belegt": lb > 0}


def test_ligen_bekommen_ihren_nenner():
    rows = [_liga(i, 0.01 if i < 8 else -0.05) for i in range(263)]
    a = F.ausbeute_ueber_huerde(rows)
    assert (a["nTests"], a["nUeber"], a["erwartet"], a["ueberschuss"]) == (263, 8, 13.2, False)
    assert a["namen"][0].startswith("Liga ")          # Ligen haben keine `schublade`


def test_baue_schreibt_ligen_ausbeute():
    src = open(F.__file__, encoding="utf-8").read()
    assert '"ligenAusbeute": ausbeute_ueber_huerde(_ligen)' in src
