"""Whale-Push auf ein Buendel: die Linie aus Erfassung + Wallet belegen — 29.09.2026."""
from datetime import datetime, timezone

import poly_public_eval as PE

K = "unl-tur-fra-2026-09-25-more-markets"
W = "0x076daa87c4fe1a85402a9b6b8e0a866224388d4c"
COND = "0x6dbf"
NOW = datetime(2026, 9, 29, 6, 0, tzinfo=timezone.utc)
RES = {K: {"winner": "Under", "cond": COND, "frage": "Türkiye vs. France: O/U 3.5"}}


def _close(wallet=W, side="Under", cond=COND):
    return {K: {"cond": cond, "prices": {"Over": 0.495, "Under": 0.505},
                "whales": [{"wallet": wallet, "side": side, "usd": 40642}]}}


def _push(**kw):
    e = {"key": K, "side": "Under", "wallet": W, "pushPrice": 0.495, "status": "pending",
         "sentAt": "2026-09-25T16:14:53Z"}
    e.update(kw)
    return e


def test_der_fall_vom_29_09_rechnet_ab():
    out = PE.settle([_push()], RES, _close(), now=NOW)[0]
    assert out["status"] == "settled" and out["result"] == "win"
    assert out["cond"] == COND and out["condQuelle"] == "erfassung+wallet"
    assert "nichtAufloesbarGrund" not in out


def test_gegenbeweis_andere_wallet_bleibt_offen():
    out = PE.settle([_push()], RES, _close(wallet="0xandere"), now=NOW)[0]
    assert out["status"] == "pending" and out.get("nichtAufloesbarGrund")


def test_gegenbeweis_andere_seite_bleibt_offen():
    assert PE.settle([_push()], RES, _close(side="Over"), now=NOW)[0]["status"] == "pending"


def test_gegenbeweis_erfassung_und_aufloesung_meinen_verschiedene_maerkte():
    assert PE.settle([_push()], RES, _close(cond="0xanders"), now=NOW)[0]["status"] == "pending"


def test_gegenbeweis_ohne_wallet_im_push_wird_nicht_geraten():
    e = _push(); e.pop("wallet")
    assert PE.settle([e], RES, _close(), now=NOW)[0]["status"] == "pending"
