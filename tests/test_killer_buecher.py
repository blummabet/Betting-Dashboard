# -*- coding: utf-8 -*-
"""tests/test_killer_buecher.py — 17.09.2026

Lucas, zur Konjunktions-Karte („Betfair 74 % · Poly 86 % · Pinnacle stimmt zu", in der
Uebersicht zusaetzlich Stake): „Werten wir das irgendwo aus bzw. tracken wir diese Dinge? …
Wenn dann quasi alle 4 einig sind, was da die Trefferquote waere, wuerde mich interessieren."

Die Antwort war: nein — obwohl die Zahl zum Eintrittszeitpunkt dasteht. `buecher_punkte`
bewertet alle vier Buecher je Zeile mit ja/nein/unbekannt, die Karte zeigt es, und ins Buch
wanderte davon nichts ausser `stufe`. Die Frage liess sich nur als Einmal-Rechnung ueber das
Stake-Ledger beantworten, und das reicht fuenf Tage weit (n=30, 60 % Treffer, ROI −2,7 %,
UG −27,1 % — also nichts).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import killer as K  # noqa: E402


def _z(bf="ja", poly="ja", pin="ja", stake="ja", **kw):
    z = {"matchId": "1", "markt": "Match Odds", "league": "L", "seite": "home", "name": "A",
         "haltePreis": 2.0, "odd": 2.0, "stufe": 1, "kickoff": "2026-09-17T18:00:00Z",
         "punkte": {"punkte": 9, "teile": [{"buch": "BF", "status": bf},
                                           {"buch": "POLY", "status": poly},
                                           {"buch": "PIN", "status": pin},
                                           {"buch": "STAKE", "status": stake},
                                           {"buch": "ZEIT", "status": "ja"}]}}
    z.update(kw)
    return z


class TestBuecherStand:
    def test_alle_vier_werden_mitgeschrieben(self):
        st = K._buecher_stand(_z())
        assert st == {"BF": "ja", "POLY": "ja", "PIN": "ja", "STAKE": "ja"}

    def test_zeit_ist_kein_geldbuch(self):
        """ZEIT misst, wie lange die Lage haelt — nicht, wer zustimmt."""
        assert "ZEIT" not in K._buecher_stand(_z())

    def test_ein_fehlendes_buch_ist_unbekannt_nicht_nein(self):
        z = _z()
        z["punkte"]["teile"] = [t for t in z["punkte"]["teile"] if t["buch"] != "STAKE"]
        assert K._buecher_stand(z)["STAKE"] == "unbekannt"

    def test_ein_unsinniger_status_wird_nicht_uebernommen(self):
        assert K._buecher_stand(_z(stake="vielleicht"))["STAKE"] == "unbekannt"

    def test_ohne_punkte_dict_steht_ueberall_unbekannt(self):
        assert set(K._buecher_stand({"punkte": 9}).values()) == {"unbekannt"}


class TestEinig:
    def test_gezaehlt_wird_nur_ja(self):
        assert K.einig({"buecher": {"BF": "ja", "POLY": "ja", "PIN": "nein", "STAKE": "unbekannt"}}) == 2

    def test_altbestand_ist_none_nicht_null(self):
        """Eine Zeile von vor dem 17.09. hat keinen Stand — „nicht gemessen" ist nicht „null
        Buecher einig". Sonst waere der Altbestand die schlechteste Gruppe der Tabelle."""
        assert K.einig({"stufe": 1}) is None
        assert K.einig({"buecher": {}}) is None


class TestNachBuechern:
    def _led(self, n, einig_ja, win_quote=0.5, odd=2.0):
        b = {k: ("ja" if i < einig_ja else "nein") for i, k in enumerate(K.BUECHER)}
        return [{"k": "x%d" % i, "haltePreis": odd, "win": i < int(n * win_quote),
                 "status": "abgerechnet", "buecher": dict(b)} for i in range(n)]

    def test_eine_zeile_je_zustimmungsgrad(self):
        led = self._led(20, 4) + self._led(20, 2)
        aus = K.nach_buechern(led)
        assert [r["einig"] for r in aus] == [2, 4]
        assert all(r["n"] == 20 for r in aus)

    def test_die_untergrenze_kommt_erst_ab_genug_zeilen(self):
        aus = K.nach_buechern(self._led(4, 4), min_n=10)
        assert aus[0]["roiLb"] is None and aus[0]["belegt"] is False

    def test_altbestand_laeuft_als_eigene_gruppe_mit(self):
        """Damit die Summe aufgeht und niemand ihn fuer „0 von 4" haelt."""
        led = self._led(10, 4) + [{"k": "alt", "haltePreis": 2.0, "win": True}]
        aus = K.nach_buechern(led)
        assert aus[0]["einig"] is None and aus[0]["n"] == 1

    def test_offene_zeilen_zaehlen_nicht(self):
        led = self._led(10, 4) + [{"k": "o", "haltePreis": 2.0, "win": None, "buecher": {"BF": "ja"}}]
        assert sum(r["n"] for r in K.nach_buechern(led)) == 10

    def test_quoten_ausserhalb_des_bands_zaehlen_nicht(self):
        """Dieselbe Schranke wie in `bilanz` — sonst misst diese Tabelle eine andere Menge."""
        led = self._led(10, 4) + [{"k": "x", "haltePreis": 99.0, "win": True,
                                   "buecher": {b: "ja" for b in K.BUECHER}}]
        assert sum(r["n"] for r in K.nach_buechern(led)) == 10
