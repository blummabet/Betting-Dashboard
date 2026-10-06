"""04.10.2026 (Lucas, FUT Esports v T1: zweite Public-Karte 30 Min spaeter „stockt auf · $254.7K ·
68 % des Marktvolumens · Anpfiff in 57 Min" — „heisst der Typ hat dick nachgelegt?").

Er hatte nachgelegt (Close-Feed-Trades: Kaeufe ueber $9K–37K). Falsch waren zwei Zahlen daneben:
Nenner und Anpfiff kamen aus dem Close-Feed, der ~1 h vor Anpfiff einfriert. Fehlerklasse:
Zaehler und Nenner aus verschiedenen Zeitpunkten."""
from datetime import datetime, timezone

import poly_money_broad as B
import poly_whale_watch as W

NOW = datetime(2026, 10, 4, 11, 32, tzinfo=timezone.utc)
BROAD = {"val-fut1-t1-2026-10-04": {"totalUsd": 374515, "hoursToKickoff": 0.95,
                                    "koTs": "2026-10-04T12:00:00+00:00"}}


def test_anpfiff_aus_fester_uhrzeit_nicht_aus_eingefrorenen_stunden():
    assert W._kickoff_txt("val-fut1-t1-2026-10-04", BROAD, now=NOW) == "Anpfiff in 28 Min"
    alt = {"k": {"hoursToKickoff": 2.0}}
    assert W._kickoff_txt("k", alt, now=NOW) == "Anpfiff in 2h", "ohne koTs wie bisher"


def test_anteil_mit_frischem_nenner():
    pos = {"key": "val-fut1-t1-2026-10-04", "usd": 254679, "marktUsd": 620000}
    assert round(W.markt_anteil(pos, BROAD), 2) == 0.41
    assert round(W.markt_anteil({"key": "val-fut1-t1-2026-10-04", "usd": 126536}, BROAD), 2) == 0.34


def test_wallet_track_schreibt_frisches_volumen_und_anpfiff_an_die_position():
    m = {"key": "k", "prices": {"T1": 0.515}, "totalUsd": 620000, "koTs": "2026-10-04T12:00:00+00:00",
         "whales": [{"wallet": "0xw", "side": "T1", "usd": 254679}]}
    t = B.update_wallet_track({"open": {"0xw|k|T1": {"wallet": "0xw", "key": "k", "side": "T1", "usd": 126536,
                                                     "firstPrice": 0.525, "lastPrice": 0.535}}}, [m], now=NOW)
    e = t["open"]["0xw|k|T1"]
    assert e["usd"] == 254679 and e["marktUsd"] == 620000 and e["koTs"] == "2026-10-04T12:00:00+00:00"


def test_aufstocken_zeigt_auch_die_quote_von_jetzt():
    pos = {"key": "val-fut1-t1-2026-10-04", "side": "T1", "usd": 254679, "league": "ESPORTS",
           "firstPrice": 0.525, "entryPrice": 0.524, "lastPrice": 0.515, "wallet": "0xw"}
    card = W.build_public_card(pos, {}, True, BROAD)
    assert "Einstieg @1.91 · jetzt @1.94" in card
    assert "jetzt" not in W.build_public_card(pos, {}, False, BROAD)


# ── 04.10.2026: welches E-Sport-Spiel ───────────────────────────────────────────────────────
def test_esport_spiel_aus_dem_slug():
    assert W.esport_spiel("cs2-spirit-faze-2026-10-04") == "CS2"
    assert W.esport_spiel("lol-t1-geng-2026-10-04") == "LoL"
    assert W.esport_spiel("val-fut1-t1-2026-10-04") == "Valorant"
    assert W.esport_spiel("dota2-a-b-2026-10-04") == "Dota 2"
    assert W.esport_spiel("epl-ars-lee-2026-10-10") is None


def test_karten_nennen_das_spiel():
    pos = {"key": "cs2-spirit-faze-2026-10-04", "side": "Spirit", "usd": 30000, "league": "ESPORTS",
           "firstPrice": 0.55, "wallet": "0xw"}
    assert "E-Sport · CS2" in W.build_card(pos, {}, False, {})
    assert "E-Sport · CS2" in W.build_public_card(pos, {}, False, {})
    tennis = dict(pos, key="atp-a-b-2026-10-04", league="TENNIS")
    assert "·" not in W.build_card(tennis, {}, False, {}).split("\n")[0]


def test_live_einstieg_nennt_das_spiel():
    import poly_live_watch as P
    t = P.format_alert({"key": "lol-t1-geng-2026-10-04", "league": "esports", "wallet": "0xw", "side": "T1",
                        "usd": 20000, "prices": {"T1": 0.6, "GenG": 0.4}, "sharp": False, "score": None})
    assert "LoL ·" in t.split("\n")[0]


# ── 06.10.2026: der Einbau oben legte poly_money_broad 37 h lahm ───────────────────────────
def test_neue_position_mit_anpfiff_stuerzt_nicht_ab():
    """Alter Fehler: der marktUsd/koTs-Block stand mitten im else-Zweig, `e["league"]` lief fuer
    jede NEUE Position mit koTs auf e=None → TypeError, der ganze Scan schrieb nichts mehr."""
    m = {"key": "k", "league": "ESPORTS", "sport": "E-Sport", "prices": {"T1": 0.5}, "totalUsd": 9000,
         "koTs": "2026-10-04T12:00:00+00:00", "whales": [{"wallet": "0xneu", "side": "T1", "usd": 5000}]}
    t = B.update_wallet_track({}, [m], now=NOW)
    e = t["open"]["0xneu|k|T1"]
    assert e["marktUsd"] == 9000 and e["koTs"] == "2026-10-04T12:00:00+00:00" and e["league"] == "ESPORTS"


def test_bestehende_position_ohne_anpfiff_bekommt_liga_und_einstieg_weiter():
    """Zweite Folge desselben Fehlers: league/sport/entryPrice wurden nur noch MIT koTs aufgefrischt."""
    m = {"key": "k", "league": "NEU-LIGA", "sport": "E-Sport", "prices": {"T1": 0.5},
         "whales": [{"wallet": "0xw", "side": "T1", "usd": 5000, "avgPrice": 0.47}]}
    t = B.update_wallet_track({"open": {"0xw|k|T1": {"wallet": "0xw", "key": "k", "side": "T1", "usd": 1,
                                                     "firstPrice": 0.5, "lastPrice": 0.5, "league": "ALT"}}},
                              [m], now=NOW)
    e = t["open"]["0xw|k|T1"]
    assert e["league"] == "NEU-LIGA" and e["entryPrice"] == 0.47 and e["sport"] == "E-Sport"
