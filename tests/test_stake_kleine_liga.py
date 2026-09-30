"""30.09.2026 (Lucas: „hab ja oft genug erwähnt das ich die kleinen ligen halt gerne hätte —
aber bis heute nicht ein burst dafür gekommen"). Die Burst-Regel (>=4 Wetten derselben Seite)
konnte in kleinen Ligen strukturell nie feuern: auf Ebene 3 standen in 5,7 Tagen Rohbuch nie
mehr als 2 Wetten derselben Seite in 30 Min. Eigene Einheit: die einzelne grosse Wette."""
import json
from datetime import datetime, timedelta, timezone

import stake_burst_push as B

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def w(i=1, usd=6000, slug="league-two", liga="League Two", phase="vor", quote=1.85,
      kombi=False, alter_min=5, ko_h=3, auswahl="a1", kat="Fußball"):
    return {"id": "sport:%d" % i, "ts": (NOW - timedelta(minutes=alter_min)).isoformat(),
            "einsatzUsd": usd, "quote": quote, "beinQuote": quote, "kombi": kombi, "nBeine": 1,
            "sport": "soccer", "kat": kat, "liga": liga, "ligaSlug": slug, "ligaId": None,
            "event": "Newport - Grimsby", "eventId": "e1", "markt": "Total", "auswahl": "Over 2.5",
            "auswahlId": auswahl, "phase": phase,
            "anpfiff": (NOW + timedelta(hours=ko_h)).isoformat()}


EM = {"1": 2000.0, "2": 2000.0, "3": 2000.0}


def kl(wetten, norm=None):
    return B.kleine_liga(wetten, norm=norm or {}, ebene_median=EM, now=NOW)


def test_einzelne_grosse_wette_in_kleiner_liga_meldet():
    """Gegentest: vorher gab es fuer diesen Fall keinen Weg — bursts() verlangt >=4 Wetten."""
    assert B.bursts([w()], now=NOW) == []
    r = kl([w()])
    assert len(r) == 1 and r[0]["ebene"] == "3" and r[0]["refBasis"] == "ebene"
    assert abs(r[0]["faktor"] - 3.0) < 1e-9


def test_liga_norm_schlaegt_ebenen_median():
    r = kl([w(slug="la-liga-2", liga="La Liga 2")], norm={"La Liga 2": 1000.0})
    assert r[0]["refBasis"] == "liga" and r[0]["ebene"] == "2" and r[0]["faktor"] == 6.0


def test_was_nicht_passt_bleibt_draussen():
    assert kl([w(slug="premier-league", liga="Premier League")]) == [], "Ebene 1 ist keine kleine Liga"
    assert kl([w(phase="live")]) == [], "nur vor Anpfiff"
    assert kl([w(kombi=True)]) == []
    assert kl([w(usd=3000)]) == [], "unter 2x Norm"
    assert kl([w(quote=1.30)]) == [], "Quotenboden 1,35 wie überall"
    assert kl([w(alter_min=45)]) == [], "zu alt, um den Preis noch zu bekommen"
    assert kl([w(ko_h=-0.1)]) == [], "schon angepfiffen"
    assert kl([w(kat="Tennis")]) == [], "die Spielklassen-Tabelle gilt fuer Fussball"
    assert B.kleine_liga([w()], norm={}, ebene_median={}, now=NOW) == [], \
        "ohne Bezugsgroesse kein Treffer — unbekannt ist nicht gross"


def test_mehrere_wetten_derselben_seite_werden_gebuendelt():
    r = kl([w(1, usd=2500), w(2, usd=2500)])
    assert len(r) == 1 and len(r[0]["wetten"]) == 2 and r[0]["summe"] == 5000


def test_eigene_buchart_faellt_nie_in_die_burst_bilanz():
    led = [{"art": "klein", "rendite": 1.0}, {"rendite": -0.5}]
    assert B.buch_bilanz(led)["n"] == 1 and B.buch_bilanz(led)["roi"] == -0.5
    assert B.klein_bilanz(led) == {"n": 1, "roi": 1.0, "ug": None}


def test_karte_sagt_testlauf_und_nennt_die_eigene_bilanz():
    k = B.build_klein_card(kl([w()])[0], bilanz={"n": 12, "roi": -0.05, "ug": None})
    assert "KLEINE LIGA" in k and "nur Trades" in k and "12 abgerechnet" in k and "n=100" in k
    assert "dritte Klasse" in k


def test_main_sendet_und_bucht(tmp_path, monkeypatch):
    for name in ("QUELLE_FILE", "LEDGER_FILE", "SEEN_FILE", "WETTEN_FILE", "VERWORFEN_FILE",
                 "NORM_FILE", "AUSWERTUNG_FILE"):
        monkeypatch.setattr(B, name, tmp_path / getattr(B, name).name)
    jetzt = datetime.now(timezone.utc)
    x = w()
    x["ts"] = (jetzt - timedelta(minutes=2)).isoformat()
    x["anpfiff"] = (jetzt + timedelta(hours=3)).isoformat()
    (tmp_path / "stake_highroller.json").write_text(json.dumps({"wetten": [x]}))
    (tmp_path / "stake_auswertung.json").write_text(json.dumps({"randliga": {"ebeneMedian": EM}}))
    gesendet = []
    monkeypatch.setattr(B, "send_trades_message", lambda t: gesendet.append(t) or True)
    B.main()
    led = json.loads((tmp_path / "stake_burst_ledger.json").read_text())
    assert [z["art"] for z in led if z.get("art") == "klein"] == ["klein"]
    assert led[-1]["push"] is True and any("KLEINE LIGA" in t for t in gesendet)
    B.main()                                           # zweiter Lauf: kein Doppel
    assert sum(1 for t in gesendet if "KLEINE LIGA" in t) == 1
