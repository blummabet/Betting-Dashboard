"""Aufgeloest ohne Sieger (0,5/0,5) — 29.09.2026, Stoerungsmeldung „Kostet Geld".

cs2-bmb-gbc2-2026-09-24 und cs2-bbl1-brute-2026-09-25: zwei echte $5-Wetten, 5 und 4 Tage offen.
Polymarket hatte beide per UMA aufgeloest — auf 0,5/0,5 (abgesagt/annulliert). Die Kette kannte nur
„wer settlet auf 1,00", also blieb alles fuer immer „placed".
"""
from datetime import datetime, timezone

import poly_money_broad as PMB
import poly_shortlist_track as ST
import shortlist_auto_bet as SAB

KEY = "cs2-bbl1-brute-2026-09-25"
NOW = datetime(2026, 9, 29, 6, 0, tzinfo=timezone.utc)


# ── Erkennen ───────────────────────────────────────────────────────────────────────
def test_teilung_erkannt_und_nur_exakt():
    assert PMB.teilung_from_prices({"BBL": 0.5, "Brute": 0.5}) == {"BBL": 0.5, "Brute": 0.5}
    assert PMB.teilung_from_prices({"BBL": 0.54, "Brute": 0.46}) is None, "Handelspreise sind keine Teilung"
    assert PMB.teilung_from_prices({"BBL": 1.0, "Brute": 0.0}) is None, "das ist ein Sieger"
    assert PMB.teilung_from_prices({"A": 1 / 3, "X": 1 / 3, "B": 1 / 3}) is not None


def _ev(uma, p=("0.5", "0.5")):
    return {"slug": KEY, "closed": True, "markets": [{
        "question": "Counter-Strike: BBL vs Brute (BO3)", "conditionId": "0xc", "umaResolutionStatus": uma,
        "outcomes": '["BBL", "Brute"]', "outcomePrices": '["%s", "%s"]' % p, "clobTokenIds": '["1","2"]',
        "volume": "1000"}]}


def test_uma_muss_ausdruecklich_aufgeloest_sein():
    assert PMB.uma_aufgeloest(_ev("resolved"))
    assert not PMB.uma_aufgeloest(_ev("proposed"))
    assert not PMB.uma_aufgeloest({"markets": []})


def test_nachschlag_liefert_die_teilung():
    close = {KEY: {"capturedAt": "2026-09-25T15:00:00+00:00", "prices": {"BBL": 0.55, "Brute": 0.45}}}
    out = PMB.backfill_resolutions_by_slug(close, set(), get=lambda u: [_ev("resolved")])
    assert out and out[0]["key"] == KEY and out[0]["resolvedPrices"] == {"BBL": 0.5, "Brute": 0.5}
    res = PMB.update_resolutions({}, out, now=NOW)
    assert res[KEY]["winner"] is None and res[KEY]["teilung"] == {"BBL": 0.5, "Brute": 0.5}


def test_gegenbeweis_ohne_uma_aufloesung_keine_teilung():
    close = {KEY: {"capturedAt": "2026-09-25T15:00:00+00:00", "prices": {"BBL": 0.55, "Brute": 0.45}}}
    assert PMB.backfill_resolutions_by_slug(close, set(), get=lambda u: [_ev("proposed")]) == []


def test_ein_echter_sieger_ersetzt_eine_fruehere_teilung():
    alt = {KEY: {"winner": None, "teilung": {"BBL": 0.5, "Brute": 0.5}, "ts": "2026-09-26T00:00:00+00:00"}}
    neu = PMB.update_resolutions(alt, [{"key": KEY, "resolved": True, "resolvedPrices": {"BBL": 1.0, "Brute": 0.0}}], now=NOW)
    assert neu[KEY]["winner"] == "BBL" and "teilung" not in neu[KEY]


# ── Abrechnen: Papier und echtes Geld ──────────────────────────────────────────────
def _prev():
    return {"open": {KEY + "|BBL": {"key": KEY, "side": "BBL", "entryPrice": 0.55, "stake": 10.0,
                                    "firstTs": "2026-09-25T15:16:00+00:00", "league": "ESPORTS", "cat": "E-Sport"}},
            "settled": [], "blockedCats": []}


def test_papier_rechnet_die_teilung_ab():
    res = {KEY: {"winner": None, "teilung": {"BBL": 0.5, "Brute": 0.5}}}
    t = ST.update_track(_prev(), {"plays": []}, {}, res, now=NOW, blocked=[])
    z = [s for s in t["settled"] if s["key"] == KEY]
    assert z, "blieb offen"
    z = z[0]
    assert z["result"] == "void" and z["auszahlung"] == 0.5
    assert abs(z["pnl"] - (10 / 0.55 * 0.5 - 10)) < 0.01      # −0,91 $, kein Totalverlust
    assert not any(k.startswith(KEY) for k in t["open"])


def test_gegenbeweis_ohne_aufloesung_wird_nichts_abgerechnet():
    close = {KEY: {"prices": {"BBL": 0.55, "Brute": 0.45}}}
    t = ST.update_track(_prev(), {"plays": []}, close, {}, now=NOW, blocked=[])
    assert not [s for s in t["settled"] if s["key"] == KEY]
    # und eine Teilung, die die Seite nicht nennt, rechnet auch nichts ab
    t2 = ST.update_track(_prev(), {"plays": []}, close, {KEY: {"winner": None, "teilung": {"X": 0.5, "Y": 0.5}}},
                         now=NOW, blocked=[])
    assert not [s for s in t2["settled"] if s["key"] == KEY]


def test_echte_wette_auf_den_echten_fuellpreis():
    bets = [{"betKey": KEY + "|BBL", "key": KEY, "side": "BBL", "status": "placed", "stake": 5.0,
             "polyPrice": 0.54, "orderId": "0xa"}]
    track = {"settled": [{"key": KEY, "side": "BBL", "result": "void", "auszahlung": 0.5, "closePrice": 0.55}]}
    assert SAB.abgleichen(bets, track) == 1
    b = bets[0]
    assert b["status"] == "void" and b["result"] == "VOID"
    assert abs(b["pnl"] - (5 / 0.54 * 0.5 - 5)) < 0.001       # −0,37 $
