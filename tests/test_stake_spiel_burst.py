"""tests/test_stake_spiel_burst.py — 22.09.2026

🔴 Lucas schickt einen Fremd-Radar-Post:

    ⚽️ #Uzbekistan #Pro_League · PFC Terdu – FK Gazalkent · Volume $15.734,34
    WhiteList #PFC_Terdu · Total 5 bets / 5 bets in 7 min
    last bet: Handicap – FK Gazalkent (-1.5) $2000 x 1.75 @ 17:16

„Genau sowas ist halt das Geile, wenn man sowas findet — und wir HÄTTEN es gefunden.
 Also macht das bitte so, dass man es findet."

Wir hatten die Wetten: sechs Fußballwetten auf genau dieses Spiel standen im Ledger, darunter
die aus dem fremden Post. Gefunden hat sie niemand, weil `bursts()` je AUSWAHL gruppiert und
dieselbe Quote verlangt — der fremde Radar gruppiert je SPIEL. Die größte gleichgerichtete
Gruppe war n=3 / $7.262 auf zwei Quoten. Kein Fehler in der alten Regel: eine andere Frage.

Diese Tests halten fest, was die neue Gruppierung leisten muss und wo sie bewusst schweigt.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

import stake_burst_push as M  # noqa: E402

NOW = datetime(2026, 9, 22, 14, 40, tzinfo=timezone.utc)
NORM = {"Pro League": 1800.0, "Premier League": 2000.0}


def w(ts_off_s, usd, quote=1.75, auswahl="FK Gazalkent", markt="1x2",
      event="PFC Terdu - FK Gazalkent", ev="fx1", liga="Pro League", kat="Fußball", **extra):
    d = {"id": "b%d-%s" % (ts_off_s, auswahl), "eventId": ev, "event": event,
         "liga": liga, "kat": kat, "markt": markt, "auswahl": auswahl,
         "quote": quote, "einsatzUsd": float(usd), "kombi": False, "phase": "live",
         "ts": (NOW - timedelta(seconds=1200 - ts_off_s)).isoformat().replace("+00:00", "Z")}
    d.update(extra)
    return d


# Der echte Fall, Zeile für Zeile aus dem Ledger (ohne die @1,03 zwanzig Minuten später).
LUCAS = [
    w(0,   1524.19, 1.80, "Over 1.5", "1st Half - Asian Total"),
    w(173, 1434.54, 1.85, "Over 1.5", "1st Half - Asian Total"),
    w(228, 4303.61, 1.85, "Over 1.5", "1st Half - Asian Total"),
    w(255, 6472.00, 1.65, "FK Gazalkent", "1st Half - 1x2"),
    w(396, 2000.00, 1.75, "FK Gazalkent (-1.5)", "Asian Handicap"),
]


def test_der_fall_den_lucas_geschickt_hat_wird_gefunden():
    """Der Test, um den es geht. Summe und Ticketzahl müssen dem fremden Post entsprechen:
    $15.734 über 5 Wetten."""
    b = M.spiel_bursts(LUCAS, norm=NORM, now=NOW)
    assert len(b) == 1
    assert b[0]["seite"] == "FK Gazalkent"
    assert round(b[0]["summe"]) == 15734
    assert len(b[0]["wetten"]) == 5


def test_die_alte_gruppierung_findet_ihn_nicht():
    """Nicht als Vorwurf, sondern als Beleg, dass die neue Regel eine andere Frage stellt und
    keine Dublette ist. Ohne diesen Test wäre „wir haben das doch schon" ein Rückbaugrund."""
    assert M.bursts(LUCAS, now=NOW) == []


def test_eine_gegenseite_macht_daraus_einen_markt_kein_signal():
    """Die tragende Regel. Viel Geld auf BEIDE Mannschaften sind zwei Parteien, die sich uneinig
    sind — das ist ein Markt. Viel Geld auf EINE über mehrere Märkte ist die Beobachtung."""
    b = M.spiel_bursts(LUCAS + [w(300, 9000, 1.9, "PFC Terdu", "1x2")], norm=NORM, now=NOW)
    assert b == []


def test_neutrale_wetten_sind_keine_gegenseite():
    """Over/Under zeigt auf keine Mannschaft. Sie zählen zur Summe — sonst wäre Lucas' Fall
    drei Tickets und $8.472 statt fünf und $15.734 — aber sie sperren nicht."""
    b = M.spiel_bursts(LUCAS, norm=NORM, now=NOW)
    assert b[0]["nGerichtet"] == 2, "zwei Tickets nennen FK Gazalkent, drei sind neutral"
    assert len(b[0]["wetten"]) == 5


def test_ein_reiner_torlinien_schwall_meldet_nicht():
    """Ohne `SPIEL_MIN_GERICHTET` wäre jeder Über/Unter-Schwall eine Meldung — und das ist ein
    Torlinien-Handel, keine Richtungswette."""
    nur_neutral = [w(i * 60, 5000, 1.85, "Over 2.5", "Total") for i in range(6)]
    assert M.spiel_bursts(nur_neutral, norm=NORM, now=NOW) == []
    # eine einzige gerichtete reicht auch nicht
    assert M.spiel_bursts(nur_neutral + [w(400, 5000, 1.8, "FK Gazalkent")],
                          norm=NORM, now=NOW) == []
    # zwei schon
    assert len(M.spiel_bursts(nur_neutral + [w(400, 5000, 1.8, "FK Gazalkent"),
                                             w(420, 5000, 1.8, "FK Gazalkent (-0.5)", "AH")],
                              norm=NORM, now=NOW)) == 1


def test_eine_abstauber_quote_entwertet_die_uebrigen_nicht():
    """🔴 Beim Bau zuerst falsch gemacht: der Quotenboden verwarf das ganze Cluster, sobald EINE
    Wette darunter lag — und damit fiel Lucas' eigener Fall durch (die @1,03 zwanzig Minuten
    später). Er wirkt je ZEILE: die 1,03 zählt weder zur Anzahl noch zur Summe."""
    b = M.spiel_bursts(LUCAS + [w(600, 3897, 1.03, "FK Gazalkent", "1x2")], norm=NORM, now=NOW)
    assert len(b) == 1
    assert round(b[0]["summe"]) == 15734, "die Abstauber-Wette darf die Summe nicht aufblähen"
    assert len(b[0]["wetten"]) == 5


def test_ohne_liga_norm_kein_urteil():
    """Fehlende Information ist hier bewusst eine Sperre und kein harmloser Default: „wir kennen
    die Liga nicht" heißt nicht „der Einsatz ist normal". Das ist die Bug-Klasse, die in diesem
    Repo schon mehrfach zugeschlagen hat — hier in die sichere Richtung aufgelöst."""
    assert M.spiel_bursts(LUCAS, norm={}, now=NOW) == []
    assert M.spiel_bursts(LUCAS, norm={"Pro League": 0}, now=NOW) == []


def test_der_faktor_misst_gegen_die_liga_nicht_gegen_dollar():
    """„Ne 50k Wette auf Arsenal sagt 0" (Lucas, 07.09.). Dieselben Beträge in einer Liga mit
    zehnfacher Norm sind kein Ausreißer."""
    b = M.spiel_bursts(LUCAS, norm={"Pro League": 18000.0}, now=NOW)
    assert b == [], "1.800 → 18.000 Norm: derselbe Schwall ist dort Alltag"


def test_gesperrte_sportarten_bleiben_draussen():
    kampf = [dict(x, kat="Kampfsport") for x in LUCAS]
    assert M.spiel_bursts(kampf, norm=NORM, now=NOW, gesperrt=["Kampfsport"]) == []


def test_kombiwetten_zaehlen_nicht():
    """Dieselbe Regel wie beim Auswahl-Burst: der Einsatz hängt an mehreren Spielen und ist
    keinem davon zurechenbar."""
    kombi = [dict(x, kombi=True) for x in LUCAS]
    assert M.spiel_bursts(kombi, norm=NORM, now=NOW) == []


def test_zu_alt_wird_nicht_gemeldet():
    """Dieselbe Grenze wie oben — die Regel prüft den Zustand UND wann er galt (12.09.,
    Venezia-Fiorentina)."""
    spaet = NOW + timedelta(minutes=M.MAX_ALTER_MIN + 5)
    assert M.spiel_bursts(LUCAS, norm=NORM, now=spaet) == []


def test_je_spiel_hoechstens_eine_meldung():
    lang = LUCAS + [w(500 + i * 30, 4000, 1.8, "FK Gazalkent", "1x2") for i in range(4)]
    b = M.spiel_bursts(lang, norm=NORM, now=NOW)
    assert len(b) == 1, "sonst sieht der Kanal ein Ereignis als fünf"


def test_zwei_spiele_sind_zwei_meldungen():
    zweites = [dict(x, eventId="fx2", event="A Team - B Team", id="z" + x["id"],
                    auswahl=x["auswahl"].replace("FK Gazalkent", "A Team"))
               for x in LUCAS]
    b = M.spiel_bursts(LUCAS + zweites, norm=NORM, now=NOW)
    assert len(b) == 2


def test_eine_mehrdeutige_mannschaft_wird_nicht_geraten():
    """„Deportivo La Coruna - Deportivo Alaves": „Deportivo" passt auf beide. Eine geratene
    Seite wäre schlimmer als keine — die Auswahl gilt dann als neutral."""
    assert M.seite({"event": "Deportivo La Coruna - Deportivo Alaves",
                    "auswahl": "Deportivo"}) is None
    assert M.seite({"event": "Deportivo La Coruna - Deportivo Alaves",
                    "auswahl": "Deportivo Alaves"}) == "Deportivo Alaves"
    assert M.seite({"event": "PFC Terdu - FK Gazalkent", "auswahl": "Over 1.5"}) is None
    assert M.seite({"event": "kein Trennzeichen", "auswahl": "irgendwas"}) is None


def test_die_karte_nennt_seite_maerkte_und_faktor():
    b = M.spiel_bursts(LUCAS, norm=NORM, now=NOW)[0]
    k = M.build_spiel_card(b)
    assert "FK Gazalkent" in k
    assert "PFC Terdu - FK Gazalkent" in k
    assert "3 Märkte" in k
    assert "1.7x" in k


def test_die_karte_sagt_dass_die_andere_rendite_hier_nicht_gilt():
    """Die Fehlerklasse, die das verhindert: eine Rendite, die für eine andere Einheit gemessen
    wurde, auf einer neuen Karte mitlesen. Der Auswahl-Burst hat +45,9 % (UG +34,3 %, n=212);
    dieser Zuschnitt hat noch gar nichts."""
    k = M.build_spiel_card(M.spiel_bursts(LUCAS, norm=NORM, now=NOW)[0])
    assert "NICHT" in k and "45,9" in k
    assert "noch nicht belegt" in k


def test_die_karte_zeigt_die_spielklasse_ohne_sie_zu_filtern():
    """Lucas' eigene Liga steht seit heute als „mehrdeutig" in stake_liga_stufe (der Slug
    `pro-league` trägt zwei Klassen). Als Filter wäre sie deshalb genau der Fehler, den wir
    heute an vier anderen Stellen entfernt haben."""
    mit_slug = [dict(x, ligaSlug="pro-league", sport="soccer") for x in LUCAS]
    b = M.spiel_bursts(mit_slug, norm=NORM, now=NOW)
    assert len(b) == 1, "eine unklare Spielklasse darf nichts sperren"
    assert "nicht eindeutig" in M.build_spiel_card(b[0])


def test_das_buch_trennt_die_beiden_arten():
    """Sie messen verschiedene Einheiten und dürfen nie in einer Zahl zusammenfallen."""
    z = M.spiel_buch_zeile(M.spiel_bursts(LUCAS, norm=NORM, now=NOW)[0], "2026-09-22T14:40:00Z")
    assert z["art"] == "spiel"
    assert z["k"].startswith("spiel:")
    assert z["seite"] == "FK Gazalkent" and z["nGerichtet"] == 2
    assert z["status"] == "pending"
    # und der Auswahl-Burst trägt diesen Schlüssel nicht
    auswahl = [w(i * 30, 5000, 1.8, "FK Gazalkent", "1x2", auswahlId="a1") for i in range(4)]
    ab = M.bursts(auswahl, now=NOW)
    assert ab and not M.burst_key(ab[0]).startswith("spiel:")


def test_gegen_das_echte_ledger_bleibt_die_lautstaerke_im_rahmen():
    """Ein Zuschnitt, der 50 Meldungen am Tag erzeugt, wird abgeschaltet statt gelesen —
    Lucas am 11.09.: „hab Angst, dass da zu viel kommt"."""
    p = BASE / "stake_bet_ledger.json"
    if not p.exists():
        import pytest
        pytest.skip("kein Ledger im Arbeitsverzeichnis")
    d = json.loads(p.read_text(encoding="utf-8")) or {}
    rows = d.get("wetten") or []
    if len(rows) < 1000:
        import pytest
        pytest.skip("Ledger zu dünn")
    ts = sorted(r["ts"] for r in rows if r.get("ts"))
    tage = max((datetime.fromisoformat(ts[-1].replace("Z", "+00:00"))
                - datetime.fromisoformat(ts[0].replace("Z", "+00:00"))).total_seconds() / 86400, 0.5)
    b = M.spiel_bursts(rows, max_alter_min=1e9, now=datetime.now(timezone.utc))
    pro_tag = len(b) / tage
    assert pro_tag <= 30, "zu laut: %.1f Meldungen pro Tag" % pro_tag
