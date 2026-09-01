"""tests/test_moneymap_rendite.py — 01.09.2026

Lucas: „was macht das [der Killer] jetzt besser als die Money Map? Da sind ja auch nur die drei
selben Signale."

Beim Nachrechnen fiel der eigentliche Unterschied auf: die Money Map schrieb `moneyWin` mit, aber
NIE eine Quote. Ihre 81,3% Trefferquote bei „stark" sagen deshalb nichts über Geld — das Geld liegt
auf Favoriten, eine hohe Trefferquote ist dort der Normalfall. Ohne Preis ist die Fläche nicht
widerlegbar, und was nicht widerlegbar ist, belegt auch nichts.

Ab jetzt hält der Ledger ZWEI Preise fest: die Quote beim ersten Auftauchen (nur die war nehmbar →
ROI) und die zuletzt gesehene (→ CLV). Diese Tests halten die drei Eigenschaften fest, an denen so
eine Bilanz sonst schönfärbt.
"""
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

import betfair_consensus as BC  # noqa: E402


def zeile(mid="1", side="home", odd=2.0, **extra):
    r = {"matchId": mid, "home": "A", "away": "B", "league": "L", "kickoff": "2026-09-02T18:00:00Z",
         "verdict": "konsens", "nSources": 3, "mmStrong": True,
         "betfair": {"side": side, "name": "A", "sharePct": 80, "eur": 40000, "odd": odd},
         "poly": {"side": side, "name": "A", "sharePct": 70, "usd": 20000, "src": "upcoming"},
         "pinn": {"fav": side, "home": 0.5, "draw": 0.27, "away": 0.23}}
    r.update(extra)
    return r


def gebucht(mid="1", first=2.0, last=None, win=True, strong=True, verdict="konsens"):
    return {"matchId": mid, "verdict": verdict, "mmStrong": strong, "status": "won" if win else "lost",
            "moneySide": "home", "winner": "home" if win else "away", "moneyWin": win,
            "moneyOddFirst": first, "moneyOddLast": last, "league": "L"}


class TestZeileTraegtDieQuote:
    def test_die_geld_seite_bringt_ihren_preis_mit(self):
        g = {"matchId": "1", "home": "A", "away": "B", "league": "L", "verdict": "konsens",
             "moneySide": "home", "moneyName": "A", "moneySharePct": 80, "totVol": 40000,
             "moneyOdd": 1.85, "pinn": {"fav": "home", "home": .5, "draw": .27, "away": .23}}
        row = BC.money_map_row(g, {"side": "home", "name": "A", "sharePct": 70, "usd": 9000})
        assert row["betfair"]["odd"] == 1.85, "ohne Preis ist die Zeile nicht abrechenbar"

    def test_fehlende_quote_wird_nicht_erfunden(self):
        g = {"matchId": "1", "home": "A", "away": "B", "league": "L", "verdict": "konsens",
             "moneySide": "home", "moneyName": "A", "moneySharePct": 80, "totVol": 40000}
        row = BC.money_map_row(g, None)
        assert row["betfair"]["odd"] is None


class TestLedgerHaeltZweiPreise:
    def test_erster_preis_wird_nie_ueberschrieben(self):
        # Der Kern: nur der Preis beim ERSTEN Auftauchen war nehmbar. Schriebe man ihn fort,
        # rechnete die Bilanz spaeter mit einer Quote, die es beim Signal nie gab.
        led = BC.update_mm_ledger([], [zeile(odd=2.50)], now="2026-09-01T10:00:00Z")
        led = BC.update_mm_ledger(led, [zeile(odd=1.90)], now="2026-09-01T14:00:00Z")
        assert len(led) == 1
        assert led[0]["moneyOddFirst"] == 2.50, "Einstieg bleibt stehen"
        assert led[0]["moneyOddLast"] == 1.90, "die letzte Quote zieht mit — sie ergibt den CLV"

    def test_abgerechnete_zeile_wird_nicht_mehr_angefasst(self):
        led = [dict(gebucht(), status="won", moneyOddFirst=2.5, moneyOddLast=1.9)]
        neu = BC.update_mm_ledger(led, [zeile(odd=1.10)], now="2026-09-02T10:00:00Z")
        assert neu[0]["moneyOddFirst"] == 2.5 and neu[0]["moneyOddLast"] == 1.9

    def test_seitenwechsel_verwirft_den_alten_einstieg(self):
        # Kippt das Geld auf die andere Seite, ist der alte Einstiegspreis eine andere Wette.
        led = BC.update_mm_ledger([], [zeile(side="home", odd=2.50)], now="2026-09-01T10:00:00Z")
        led = BC.update_mm_ledger(led, [zeile(side="away", odd=3.20)], now="2026-09-01T12:00:00Z")
        assert led[0]["moneySide"] == "away"
        assert led[0]["moneyOddFirst"] == 3.20, "neuer Einstieg, nicht der alte der Gegenseite"


class TestBilanzRechnetEhrlich:
    def test_roi_zum_einstiegspreis(self):
        rec = BC.mm_summary([gebucht("1", first=2.0, win=True), gebucht("2", first=2.0, win=False)])
        g = rec["global"]
        assert g["nRoi"] == 2
        assert abs(g["roi"] - 0.0) < 1e-9, "1.0 gewonnen, 1.0 verloren = 0"

    def test_trefferquote_und_rendite_werden_GETRENNT_gezaehlt(self):
        # Der wichtigste Test: Alt-Zeilen ohne Quote zaehlen in die Trefferquote, aber NICHT in
        # den ROI. Sonst saehe eine Rendite aus 2 Zeilen aus wie eine aus 900.
        alt = [dict(gebucht(str(i), win=True), moneyOddFirst=None, moneyOddLast=None) for i in range(8)]
        neu = [gebucht("n1", first=2.0, win=True), gebucht("n2", first=2.0, win=False)]
        rec = BC.mm_summary(alt + neu)
        g = rec["global"]
        assert g["n"] == 10, "alle zehn zaehlen in die Trefferquote"
        assert g["nRoi"] == 2, "aber nur zwei haben eine Quote"
        assert g["hitRate"] == 0.9

    def test_untergrenze_liegt_unter_dem_schaetzer(self):
        rows = [gebucht(str(i), first=2.0, win=(i % 2 == 0)) for i in range(10)]
        g = BC.mm_summary(rows)["global"]
        assert g["roiLb"] is not None and g["roiLb"] < g["roi"]

    def test_ohne_quoten_wird_keine_rendite_erfunden(self):
        rows = [dict(gebucht(str(i)), moneyOddFirst=None, moneyOddLast=None) for i in range(5)]
        g = BC.mm_summary(rows)["global"]
        assert g["nRoi"] == 0 and g["roi"] is None and g["roiLb"] is None
        assert g["hitRate"] is not None, "die Trefferquote bleibt — sie war nie das Problem"

    def test_clv_braucht_beide_preise(self):
        rec = BC.mm_summary([gebucht("1", first=2.50, last=2.00, win=True),
                            gebucht("2", first=2.00, last=None, win=True)])
        g = rec["global"]
        assert g["nRoi"] == 2, "beide haben einen Einstieg"
        assert g["nClv"] == 1, "aber nur eine hat auch eine Schlussquote"
        assert abs(g["clv"] - 10.0) < 0.01, "2.50→2.00 = +10pp auf unserer Seite"

    def test_verdikt_und_staerke_tragen_die_rendite_mit(self):
        rows = [gebucht("1", first=3.0, win=True, strong=True),
                gebucht("2", first=3.0, win=False, strong=True),
                gebucht("3", first=1.5, win=True, strong=False, verdict="uneinig")]
        rec = BC.mm_summary(rows)
        assert rec["byVerdict"]["konsens"]["nRoi"] == 2
        assert rec["byStrength"]["strong"]["nRoi"] == 2
        assert rec["byStrength"]["weak"]["nRoi"] == 1
