"""tests/test_stake_settle.py — 03.09.2026

Lucas: 'bitte alles umsetzen'. Die Abrechnung ist der Schritt, nach dem wir zum ersten Mal
eine gemessene Zahl haben statt einer Vermutung — und deshalb der Ort, an dem ein leiser
Fehler am teuersten wäre: eine Quote, die zu gut aussieht, weil etwas fehlt.

Die Antworten in diesen Tests sind echt. Am 03.09. gegen stake.com/_api/graphql geprüft:

  sport:648199979  status "settled"   payout 0      Beine ["won", "lost"]   (2er-Kombi)
  sport:648200455  status "confirmed" payout 0      Beine ["pending"]       ← laeuft noch
  sport:648200459  status "settled"   payout 2373.5 Beine ["won"]

Der mittlere Fall ist der Grund für die halbe Datei: 'confirmed' heisst NICHT abgerechnet.
Wer nur auf 'settled' prüft, zählt so eine Wette nie; wer alles ausser 'settled' als fertig
nimmt, zählt sie als Nulltreffer. Beides verschiebt die Quote.
"""
import importlib.util
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _modul(**env):
    import os
    alt = {k: os.environ.get(k) for k in env}
    os.environ.update({k: str(v) for k, v in env.items()})
    try:
        spec = importlib.util.spec_from_file_location("stake_settle_t", ROOT / "stake_settle.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        for k, v in alt.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


S = _modul()

KURSE = {"usd": {"cad": 0.7252447}, "geholt": None}

ABGERECHNET_EINZEL = {"id": "x", "iid": "sport:648200459", "bet": {
    "__typename": "SportBet", "amount": 2350, "currency": "usdc", "status": "settled",
    "active": False, "payout": 2373.5, "payoutMultiplier": 1.01, "potentialMultiplier": 1.01,
    "outcomes": [{"status": "won", "odds": 1.01, "outcome": {"name": "Taylor Fritz"},
                  "fixtureName": "Taylor Fritz - Bellucci, Mattia"}]}}

ABGERECHNET_KOMBI = {"id": "y", "iid": "sport:648199979", "bet": {
    "__typename": "SportBet", "amount": 2000, "currency": "cad", "status": "settled",
    "active": False, "payout": 0, "payoutMultiplier": 0, "potentialMultiplier": 3.976,
    "outcomes": [{"status": "won", "odds": 1.12, "outcome": {"name": "Alexandra Eala"},
                  "fixtureName": "Oliynykova - Eala"},
                 {"status": "lost", "odds": 3.55, "outcome": {"name": "Tristan Schoolkate"},
                  "fixtureName": "Schoolkate - Cobolli"}]}}

NOCH_OFFEN = {"id": "z", "iid": "sport:648200455", "bet": {
    "__typename": "SportBet", "amount": 77000, "currency": "usdt", "status": "confirmed",
    "active": True, "payout": 0, "payoutMultiplier": None, "potentialMultiplier": 1.6,
    "outcomes": [{"status": "pending", "odds": 1.6, "outcome": {"name": "Cleveland Guardians"},
                  "fixtureName": "Cleveland Guardians - Toronto Blue Jays"}]}}


# ── „confirmed" ist nicht fertig ─────────────────────────────────────────────
def test_confirmed_gilt_als_offen():
    a = S.lies_abrechnung(NOCH_OFFEN, KURSE)
    assert a["endstand"] is False, "confirmed heisst angenommen, nicht abgerechnet"
    assert a["beine"][0]["treffer"] is None


def test_unbekannter_zustand_gilt_als_offen_nicht_als_fertig():
    """Taucht morgen ein neuer Zwischenzustand auf, soll er weiter nachgefragt werden —
    nicht stillschweigend als abgerechnet durchgehen."""
    k = {"bet": {"status": "irgendwas_neues", "outcomes": [{"status": "pending"}]}}
    assert S.lies_abrechnung(k)["endstand"] is False


def test_settled_mit_gewinn():
    a = S.lies_abrechnung(ABGERECHNET_EINZEL, KURSE)
    assert a["endstand"] is True
    assert a["status"] == "settled"
    assert a["beine"][0]["treffer"] is True
    assert a["auszahlungUsd"] == 2373.5
    assert a["pnlUsd"] == 23.5, "2373,50 zurueck auf 2350 Einsatz"


def test_settled_mit_verlust_wird_negativ():
    k = dict(ABGERECHNET_EINZEL)
    k["bet"] = dict(ABGERECHNET_EINZEL["bet"], payout=0,
                    outcomes=[dict(ABGERECHNET_EINZEL["bet"]["outcomes"][0], status="lost")])
    a = S.lies_abrechnung(k, KURSE)
    assert a["beine"][0]["treffer"] is False
    assert a["pnlUsd"] == -2350.0


# ── Kombis: Trefferquote ja, Geld nein ───────────────────────────────────────
def test_kombi_liefert_zwei_beine_mit_eigenem_ausgang():
    a = S.lies_abrechnung(ABGERECHNET_KOMBI, KURSE)
    assert [b["treffer"] for b in a["beine"]] == [True, False]


def test_kombi_bekommt_KEINEN_pnl():
    """Der Einsatz einer Kombi haengt an mehreren Spielen und ist keinem davon zurechenbar.
    Ihn einem Bein zuzuschlagen waere doppelt gezaehltes Geld."""
    a = S.lies_abrechnung(ABGERECHNET_KOMBI, KURSE)
    assert a["pnlUsd"] is None


def test_kombi_einsatz_wird_trotzdem_umgerechnet():
    a = S.lies_abrechnung(ABGERECHNET_KOMBI, KURSE)
    assert round(a["einsatzUsdGeprueft"]) == 1450, "2000 CAD"


# ── Annulliert ist kein Treffer und kein Fehlschlag ──────────────────────────
@pytest.mark.parametrize("status", ["void", "cancelled", "refunded", "push"])
def test_annulliert_faellt_aus_der_quote(status):
    k = {"bet": {"status": "settled", "amount": 100, "currency": "usdt", "payout": 100,
                 "outcomes": [{"status": status, "odds": 2.0}]}}
    a = S.lies_abrechnung(k)
    assert a["endstand"] is True
    assert a["beine"][0]["neutral"] is True
    assert a["beine"][0]["treffer"] is None, "annulliert ist weder Treffer noch Fehlschlag"


def test_bilanz_zaehlt_annulliert_getrennt():
    w = [{"einsatzUsd": 100, "abrechnung": {"endstand": True, "pnlUsd": 0, "beine": [
        {"treffer": True, "neutral": False}, {"treffer": False, "neutral": False},
        {"treffer": None, "neutral": True}]}}]
    b = S.bilanz(w)
    assert b["beine"] == 3
    assert b["gewertet"] == 2, "das annullierte Bein zaehlt nicht in die Quote"
    assert b["treffer"] == 1 and b["daneben"] == 1 and b["neutral"] == 1
    assert b["quote"] == 0.5


# ── Faelligkeit ──────────────────────────────────────────────────────────────
def _w(anpfiff_vor_h=None, ts_vor_h=None, abger=None):
    j = datetime.now(timezone.utc)
    d = {"id": "i"}
    if anpfiff_vor_h is not None:
        d["anpfiff"] = (j - timedelta(hours=anpfiff_vor_h)).isoformat().replace("+00:00", "Z")
    if ts_vor_h is not None:
        d["ts"] = (j - timedelta(hours=ts_vor_h)).isoformat().replace("+00:00", "Z")
    if abger:
        d["abrechnung"] = abger
    return d


def test_frisches_spiel_ist_noch_nicht_faellig():
    assert S.faellig(_w(anpfiff_vor_h=1), datetime.now(timezone.utc)) is False


def test_nach_der_frist_ist_es_faellig():
    assert S.faellig(_w(anpfiff_vor_h=5), datetime.now(timezone.utc)) is True


def test_ohne_anpfiff_zaehlt_der_zeitpunkt_der_wette():
    """Lieber einmal zu frueh gefragt (kostet eine Anfrage) als nie abgerechnet
    (kostet die Messung)."""
    assert S.faellig(_w(ts_vor_h=5), datetime.now(timezone.utc)) is True


def test_abgerechnete_wetten_werden_nicht_nochmal_gefragt():
    assert S.faellig(_w(anpfiff_vor_h=99, abger={"endstand": True}),
                     datetime.now(timezone.utc)) is False


def test_ohne_jede_zeitangabe_wird_nicht_gefragt():
    assert S.faellig({"id": "i"}, datetime.now(timezone.utc)) is False


def test_aufgegeben_erst_nach_tagen():
    j = datetime.now(timezone.utc)
    assert S.aufgegeben(_w(anpfiff_vor_h=10), j) is False
    assert S.aufgegeben(_w(anpfiff_vor_h=24 * 6), j) is True


# ── Der gebuendelte Abruf ────────────────────────────────────────────────────
def test_batch_baut_eine_anfrage_mit_aliasen(monkeypatch):
    """300 Wetten einzeln waeren 300 Anfragen. Mit Aliasen sind es zwoelf."""
    gesehen = {}

    def fake(url, body, timeout=25):
        gesehen.update(body)
        return 200, {"data": {"b0": {"iid": "a", "bet": {"status": "settled",
                                                         "outcomes": [{"status": "won"}]}},
                              "b1": {"iid": "b", "bet": {"status": "confirmed",
                                                         "outcomes": [{"status": "pending"}]}}}}, None

    monkeypatch.setattr(S.SH, "_post", fake)
    out, err = S.frage_batch("http://test", ["a", "b"])
    assert err is None
    assert set(out) == {"a", "b"}
    assert gesehen["variables"] == {"i0": "a", "i1": "b"}
    assert gesehen["query"].count("bet(iid:") == 2, "eine Anfrage, zwei Wetten"


def test_batch_ohne_iids_fragt_gar_nicht(monkeypatch):
    monkeypatch.setattr(S.SH, "_post",
                        lambda *a, **k: pytest.fail("es gab nichts zu fragen"))
    out, err = S.frage_batch("http://test", [])
    assert out == {} and err is None


def test_batch_reicht_einen_fehler_durch(monkeypatch):
    monkeypatch.setattr(S.SH, "_post", lambda u, b, timeout=25: (403, None, "HTTP 403"))
    out, err = S.frage_batch("http://test", ["a"])
    assert out == {}
    assert "403" in err


def test_fehlende_antwort_laesst_die_wette_offen(monkeypatch):
    """Fragt man nach drei und bekommt zwei, bleibt die dritte offen — sie wird nicht
    als 'nichts gefunden, also nichts passiert' abgehakt."""
    monkeypatch.setattr(S.SH, "_post", lambda u, b, timeout=25:
                        (200, {"data": {"b0": {"iid": "a", "bet": {"status": "settled",
                                                                   "outcomes": []}},
                                        "b1": None}}, None))
    out, err = S.frage_batch("http://test", ["a", "b"])
    assert set(out) == {"a"}


# ── Bilanz ───────────────────────────────────────────────────────────────────
def test_bilanz_trennt_offen_und_unaufloesbar():
    w = [{"abrechnung": {"endstand": False}},
         {"abrechnung": {"endstand": False, "unaufloesbar": True}},
         {}]
    b = S.bilanz(w)
    assert b["offen"] == 2 and b["unaufloesbar"] == 1


def test_bilanz_ohne_daten_gibt_keine_quote():
    b = S.bilanz([])
    assert b["quote"] is None and b["einzelRoi"] is None, "kein n, kein Urteil"


def test_roi_nur_aus_einzelwetten():
    w = [
        {"einsatzUsd": 1000, "abrechnung": {"endstand": True, "pnlUsd": 500,
                                            "beine": [{"treffer": True}]}},
        {"einsatzUsd": 1000, "abrechnung": {"endstand": True, "pnlUsd": None,   # Kombi
                                            "beine": [{"treffer": True}, {"treffer": False}]}},
    ]
    b = S.bilanz(w)
    assert b["einzelN"] == 1
    assert b["einzelEinsatzUsd"] == 1000.0
    assert b["einzelRoi"] == 0.5
    assert b["gewertet"] == 3, "die Trefferquote nimmt die Kombi-Beine trotzdem mit"
