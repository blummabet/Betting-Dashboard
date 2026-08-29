"""29.08.2026 — Lucas: „die heute spielenswert liefern mmn nichts mehr seit gestern".

Gemessen: Kandidaten pro Tag in den NICHT gesperrten Kategorien (Fussball, E-Sport, Tennis):

    18.08. 16 · 19.08. 30 · 20.08. 21 · 21.08. 23 · 22.08. 43
    23.08. 30 · 24.08. 35 · 25.08. 22 · 26.08. 29 · 27.08. 3 · danach nichts

Der Zufluss brach am 27.08. ab, weil poly-global-scan von 30 Laeufen pro Tag auf 2 fiel.
Drei Tage lang hat das niemand gemerkt — und zwar, weil der bestehende Guard die falsche Frage
stellte: `check_shortlist_tracker_writes` prueft, ob die Datei GESCHRIEBEN wird. Das tat sie
durchgehend, stuendlich, mit korrektem Zeitstempel. Sie enthielt nur nichts Neues mehr.

Dieser Guard misst den ZUFLUSS. Und er nimmt die absichtlich gesperrten Kategorien aus —
US-Sport und Kampfsport wurden vom Lern-Gate wegen -37 % ROI stillgelegt, deren Stille ist
gewollt und darf den Alarm nicht dauerhaft rot faerben.
"""
import os
import sys
import pytest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poly_data_integrity as P

JETZT = datetime(2026, 8, 29, 6, 0, tzinfo=timezone.utc)


def eintrag(kat, alter_h, **extra):
    e = {"cat": kat, "firstTs": (JETZT - timedelta(hours=alter_h)).isoformat()}
    e.update(extra)
    return e


def ctx(shortlist, feed_alter_h=0.5):
    """PolyCtx mit frischem Scan-Feed — sonst urteilt der Guard bewusst nicht."""
    close = {"x": {"capturedAt": (JETZT - timedelta(hours=feed_alter_h)).isoformat()}}
    return P.PolyCtx(now=JETZT, close=close, shortlist=shortlist)


class TestZuflussWirdGemessen:
    def test_frischer_kandidat_ist_gruen(self):
        sl = {"open": [eintrag("Fußball", 2)], "settled": [], "blockedCats": []}
        assert P.check_shortlist_nachschub(ctx(sl))["ok"] is True

    def test_kein_nachschub_seit_einem_tag_faellt_auf(self):
        sl = {"open": [], "settled": [eintrag("Fußball", 39)], "blockedCats": []}
        c = P.check_shortlist_nachschub(ctx(sl))
        assert c["ok"] is False
        assert "39 h" in c["failures"][0]

    def test_genau_der_fall_vom_27_08(self):
        """Datei wird stuendlich geschrieben, enthaelt aber nur alte Eintraege."""
        sl = {"open": [eintrag("E-Sport", 190), eintrag("Tennis", 50)],
              "settled": [eintrag("Fußball", 39)],
              "blockedCats": ["US-Sport", "Kampfsport"],
              "updatedAt": JETZT.isoformat()}
        assert P.check_shortlist_nachschub(ctx(sl))["ok"] is False

    def test_offene_und_abgerechnete_zaehlen_beide(self):
        """Ein frischer Kandidat unter den settled genuegt — er kam ja auch herein."""
        sl = {"open": [eintrag("Tennis", 100)], "settled": [eintrag("Fußball", 3)],
              "blockedCats": []}
        assert P.check_shortlist_nachschub(ctx(sl))["ok"] is True

    def test_open_als_dict_wird_auch_gelesen(self):
        sl = {"open": {"k1": eintrag("Fußball", 2)}, "settled": [], "blockedCats": []}
        assert P.check_shortlist_nachschub(ctx(sl))["ok"] is True


class TestGesperrteKategorienZaehlenNicht:
    def test_nur_gesperrte_frisch_ist_trotzdem_rot(self):
        """Sonst haelt ein einzelner MLB-Kandidat den Alarm still, waehrend Fussball tot ist."""
        sl = {"open": [eintrag("US-Sport", 1)], "settled": [eintrag("Fußball", 40)],
              "blockedCats": ["US-Sport", "Kampfsport"]}
        c = P.check_shortlist_nachschub(ctx(sl))
        assert c["ok"] is False

    def test_gesperrte_tauchen_nicht_in_der_meldung_auf(self):
        sl = {"open": [], "settled": [eintrag("Fußball", 40), eintrag("US-Sport", 40)],
              "blockedCats": ["US-Sport"]}
        c = P.check_shortlist_nachschub(ctx(sl))
        assert "US-Sport" not in c["failures"][0]

    def test_ohne_sperren_zaehlt_alles(self):
        sl = {"open": [eintrag("US-Sport", 1)], "settled": [], "blockedCats": []}
        assert P.check_shortlist_nachschub(ctx(sl))["ok"] is True


class TestKeineFehlalarme:
    def test_ohne_frischen_feed_kein_urteil(self):
        """Haengt schon der Scan-Feed, ist die leere Shortlist nur die Folge — nicht die Ursache."""
        sl = {"open": [], "settled": [], "blockedCats": []}
        c = P.check_shortlist_nachschub(ctx(sl, feed_alter_h=99))
        assert c["ok"] is True

    def test_eintraege_ohne_zeitstempel_kippen_nicht_um(self):
        sl = {"open": [{"cat": "Fußball"}, "kaputt", None], "settled": [], "blockedCats": []}
        c = P.check_shortlist_nachschub(ctx(sl))
        assert c["nFail"] <= 1

    def test_leere_datei_bei_frischem_feed_meldet(self):
        c = P.check_shortlist_nachschub(ctx({"open": [], "settled": [], "blockedCats": []}))
        assert c["ok"] is False
        assert "Kein einziger" in c["failures"][0]

    def test_severity_ist_error(self):
        sl = {"open": [], "settled": [eintrag("Fußball", 40)], "blockedCats": []}
        assert P.check_shortlist_nachschub(ctx(sl))["severity"] == "error"


class TestGuardLaeuftMit:
    def test_ist_registriert(self):
        assert any(f.__name__ == "check_shortlist_nachschub" for f in P.POLY_CHECKS), \
            "Guard laeuft nicht mit — dann steht er nie in poly_status.json"

    def test_grenze_ist_plausibel(self):
        """20-40 Kandidaten/Tag waren normal; ein ganzer Tag ohne einen ist kein ruhiger Tag."""
        assert 12 <= P.SHORTLIST_SUPPLY_STALE_H <= 36
