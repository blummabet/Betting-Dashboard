"""29.09.2026 (Lucas: „Haben wir die wo ausgewertet?") — die Kursrutsch-Karte zitierte eine
Rueckrechnung (+18,3 % auf n=203, zur groesseren Haelfte Match Odds mit −9,1 %, die der Alarm
gar nicht mehr sendet), waehrend die gesendeten Alarme bei 4/9 und ROI −28 % standen.
Die Karte zeigt jetzt die Abrechnung aus betfair_rutsch_bericht.json."""
import betfair_alerts as BA

A = {"leadName": "Over 2.5 Goals", "entryOdd": 2.5, "leadOdd": 1.98, "fall": 0.208,
     "home": "Finland", "away": "Belarus", "league": "UEFA Nations League",
     "market": "Over/Under 2.5 Goals", "total": 5200.0, "leadShare": 0.54, "flag": ""}
BERICHT = {"n": 9, "wins": 4, "roi": -0.2844, "roiUg": None, "belegt": False,
           "generatedAt": "2026-09-29T13:07:40+00:00"}


def test_karte_zeigt_die_abgerechneten_alarme():
    k = BA.build_rutsch_message(A, bericht=BERICHT)
    assert "4/9" in k and "-28,4 %" in k and "kein Urteil" in k and "Stand 29.09." in k
    assert "nur Trades" in k


def test_gegentest_keine_rueckrechnungszahl_mehr():
    """Alter Code: fester Text „gemessen +18,3 % (UG +2,3) auf n=203"."""
    k = BA.build_rutsch_message(A, bericht=BERICHT)
    assert "18,3" not in k and "n=203" not in k


def test_ohne_bericht_keine_erfundene_zahl():
    k = BA.build_rutsch_message(A, bericht={})
    assert "noch kein Alarm abgerechnet" in k and "%" not in k.split("🔬")[1]


def test_urteil_folgt_der_untergrenze():
    z = BA.rutsch_bilanz_zeile({"n": 420, "wins": 230, "roi": 0.061, "roiUg": 0.012, "belegt": True})
    assert "UG +1,2 %, belegt" in z
    z = BA.rutsch_bilanz_zeile({"n": 60, "wins": 30, "roi": 0.02, "roiUg": -0.05, "belegt": False})
    assert "nicht belegt" in z
