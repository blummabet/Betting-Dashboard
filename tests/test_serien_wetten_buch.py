"""Serien-Wetten-Buch (01.10.2026, Lucas: „ja" zu Punkt 5).

Die Tafel behauptet je Serie eine Chance und eine Quote. Das Buch schreibt beides beim ersten
Erscheinen fest und rechnet nach Spielende ab: stimmt die angezeigte Chance, was bringt die
gezeigte Quote? Ohne Buch waere die Tafel eine Behauptung, die nie jemand prueft.
"""
import json
from datetime import datetime, timedelta, timezone

import messungen
import serien_wetten_buch as B

T0 = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


def row(tid="42", typ="win", h=24, pct=70.0, quote=1.5, chance="markt", **kw):
    r = {"teamId": tid, "team": "Arsenal", "type": typ, "serie": typ, "length": 5, "gegner": "X",
         "heim": True, "kickoff": (T0 + timedelta(hours=h)).isoformat(), "trefferPct": pct,
         "quote": quote, "fairQuote": 1.43, "chanceAus": chance, "markt": "Sieg"}
    r.update(kw)
    return r


def wm_mit(home, away, hs, as_, ko, status="FT", date=None):
    return {"groups": {"A": {"fixtures": [{"home": home, "away": away, "kickoff": ko.isoformat(),
                                           "date": date or ko.date().isoformat(),
                                           "result": {"status": status, "home_score": hs, "away_score": as_}}]}}}


def test_erste_quote_bleibt_letzte_laeuft_mit():
    buch = {}
    assert B.vormerken(buch, [row(quote=1.50, pct=70)], T0) == 1
    assert B.vormerken(buch, [row(quote=1.40, pct=72)], T0 + timedelta(hours=5)) == 0
    z = buch["zeilen"][0]
    assert (z["erstQuote"], z["erstPct"]) == (1.50, 70)
    assert (z["letztQuote"], z["letztPct"]) == (1.40, 72)


def test_vergangene_und_chancenlose_zeilen_werden_nicht_vorgemerkt():
    buch = {}
    B.vormerken(buch, [row(h=-1), row(typ="scored", trefferPct=None)], T0)
    assert buch["zeilen"] == []


def test_abrechnung_treffer_und_rendite_zur_ersten_quote():
    buch = {}
    B.vormerken(buch, [row(quote=1.50)], T0)
    B.vormerken(buch, [row(quote=1.30)], T0 + timedelta(hours=10))
    ko = T0 + timedelta(hours=24)
    assert B.abrechnen(buch, wm_mit("42", "7", 2, 0, ko), ko + timedelta(hours=3)) == 1
    z = buch["zeilen"][0]
    assert z["status"] == "abgerechnet" and z["erfuellt"] is True
    assert z["rendite"] == 0.5, "zur Quote beim ersten Erscheinen, nicht zur letzten"


def test_int_ids_im_datensatz_werden_trotzdem_abgerechnet():
    # streak_held vergleicht mit == — die ID muss so uebergeben werden, wie sie im Spiel steht.
    buch = {}
    B.vormerken(buch, [row(tid="42")], T0)
    ko = T0 + timedelta(hours=24)
    B.abrechnen(buch, wm_mit(42, 7, 0, 1, ko), ko + timedelta(hours=3))
    z = buch["zeilen"][0]
    assert z["erfuellt"] is False and z["rendite"] == -1.0


def test_lokaler_spieltag_im_datensatz():
    # MLS: `date` ist teils der lokale Tag (Anpfiff 02:00 UTC = Vortag in den USA).
    buch = {}
    B.vormerken(buch, [row(h=14)], T0)       # 02:00 UTC am 02.10.
    ko = T0 + timedelta(hours=14)
    B.abrechnen(buch, wm_mit("42", "7", 1, 0, ko, date="2026-10-01"), ko + timedelta(hours=3))
    assert buch["zeilen"][0]["erfuellt"] is True


def test_ecken_bleiben_im_nenner_als_unaufloesbar():
    buch = {}
    B.vormerken(buch, [row(typ="cornersOver", quote=None, chance="modell")], T0)
    ko = T0 + timedelta(hours=24)
    B.abrechnen(buch, wm_mit("42", "7", 1, 0, ko), ko + timedelta(hours=3))
    assert buch["zeilen"][0]["status"] == "unaufloesbar"
    assert B.bilanz(buch["zeilen"])["gesamt"]["unaufloesbar"] == 1


def test_ohne_ergebnis_nach_einer_woche_unaufloesbar_davor_offen():
    buch = {}
    B.vormerken(buch, [row()], T0)
    ko = T0 + timedelta(hours=24)
    B.abrechnen(buch, {"groups": {}}, ko + timedelta(days=2))
    assert buch["zeilen"][0]["status"] == "offen"
    B.abrechnen(buch, {"groups": {}}, ko + timedelta(days=8))
    assert buch["zeilen"][0]["status"] == "unaufloesbar"


def _zeilen(n, treffer, pct, quote=1.4, chance="markt"):
    out = []
    for i in range(n):
        hit = i < treffer
        out.append({"status": "abgerechnet", "erfuellt": hit, "erstPct": pct, "chanceAus": chance,
                    "rendite": (quote - 1) if (hit and quote) else (-1.0 if quote else None)})
    return out


def test_bilanz_sammelt_unter_mindest_n():
    b = B.bilanz(_zeilen(10, 8, 70))
    assert b["gesamt"]["urteil"] == "sammelt"


def test_bilanz_chance_stimmt_und_geld_verliert_wie_erwartet():
    # 70 % angezeigt, 70 % getroffen, @1.40 -> ROI -2 %: Chance stimmt, Geld nicht belegt.
    b = B.bilanz(_zeilen(400, 280, 70))["markt"]
    assert b["chance"] == "stimmt"
    assert b["roiPct"] == -2.0 and b["geld"] in ("offen", "verliert")


def test_bilanz_modell_trifft_seltener_als_angezeigt():
    b = B.bilanz(_zeilen(200, 100, 75, quote=None, chance="modell"))
    assert b["modell"]["chance"] == "trifft seltener als angezeigt"
    assert b["modell"]["geld"] == "ohne Quote"
    assert b["markt"]["n"] == 0


def test_messung_zaehlt_beide_buecher(tmp_path):
    (tmp_path / "liga_serien_wetten_buch.json").write_text(json.dumps({"zeilen": _zeilen(3, 1, 60)}))
    (tmp_path / "mls_serien_wetten_buch.json").write_text(json.dumps(
        {"zeilen": _zeilen(2, 1, 60) + [{"status": "offen"}]}))
    assert messungen.zaehler_serien_wetten(str(tmp_path)) == 5
    assert messungen.zaehler_serien_wetten(str(tmp_path / "leer")) == 0


def test_register_eintrag_hat_einen_messer():
    reg = json.load(open("messungen_register.json"))
    e = next(m for m in reg["messungen"] if m["id"] == "serien-wetten")
    assert e["messer"] in messungen.ZAEHLER and e["mindestN"] >= 100


def test_autobet_oktober_zaehlt_nur_abgerechnete_ab_stichtag(tmp_path):
    bets = [{"status": "won", "placedAt": "2026-10-02T10:00:00+00:00"},
            {"status": "lost", "placedAt": "2026-10-01T00:10:00+00:00"},
            {"status": "won", "placedAt": "2026-09-30T23:00:00+00:00"},   # vor der Festlegung
            {"status": "placed", "placedAt": "2026-10-03T10:00:00+00:00"}]
    (tmp_path / "shortlist_auto_bets_placed.json").write_text(json.dumps({"bets": bets}))
    assert messungen.zaehler_autobet_oktober(str(tmp_path)) == 2
    reg = json.load(open("messungen_register.json"))
    e = next(m for m in reg["messungen"] if m["id"] == "poly-autobet-oktober")
    assert e["messer"] in messungen.ZAEHLER and e["faellig"] == "2026-11-01"
