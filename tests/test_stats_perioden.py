# -*- coding: utf-8 -*-
"""tests/test_stats_perioden.py — 09.09.2026

Lucas: „schaffen wir eine eigene Stats-Seite? … alles auf Monatsbasis und Wochenbasis auch."

Die zwei Saetze, an denen so eine Seite sonst scheitert, stehen hier als Tests:
  1. Eine Periode, die die QUELLE nicht ganz abdeckt, ist keine Periode. Der Betfair-Ledger
     reicht am 09.09. nur bis zum 26.08. zurueck — ein Balken „August" waere seine letzte Woche
     und saehe neben dem September aus wie ein schwacher Monat statt wie ein halber.
  2. Eine fehlende Kennzahl ist keine Null. Ein Kanal ohne Quoten hat keinen ROI, kein „0 %".
"""
from datetime import date, timedelta

import stats_perioden as S


def _p(tag, rendite=None, gewonnen=None, clv=None):
    return {"tag": tag, "rendite": rendite, "gewonnen": gewonnen, "clv": clv}


class TestPeriodenSchluessel:
    def test_woche_und_monat(self):
        assert S.woche_von("2026-09-09") == "2026-W37"
        assert S.monat_von("2026-09-09") == "2026-09"

    def test_spannen_sind_montag_bis_sonntag(self):
        von, bis = S.wochen_spanne("2026-W37")
        assert date.fromisoformat(von).isoweekday() == 1
        assert date.fromisoformat(bis).isoweekday() == 7
        assert (date.fromisoformat(bis) - date.fromisoformat(von)).days == 6

    def test_monatsspanne_endet_am_letzten_tag(self):
        assert S.monats_spanne("2026-02") == ("2026-02-01", "2026-02-28")
        assert S.monats_spanne("2026-12") == ("2026-12-01", "2026-12-31")

    def test_unlesbarer_tag_ist_none_nicht_heute(self):
        assert S._tag("quatsch") is None and S._tag(None) is None
        assert S._tag("2026-09-09T12:00:00Z") == "2026-09-09"


class TestKennzahlen:
    def test_treffer_und_rendite(self):
        k = S.kennzahlen([_p("2026-09-01", 1.5, True), _p("2026-09-02", -1.0, False)])
        assert k["n"] == 2 and k["treffer"] == 1 and k["hitPct"] == 50.0
        assert k["roi"] == 25.0 and k["pl"] == 0.5

    def test_ohne_quoten_gibt_es_KEINEN_roi(self):
        """⚠️ Der teure Fall: ein Kanal ohne Ergebnis-Ledger (Dedup-Buch) haette sonst „0 %"
        Rendite dastehen — eine Zahl, die niemand gemessen hat."""
        k = S.kennzahlen([_p("2026-09-01", None, True), _p("2026-09-02", None, False)])
        assert k["roi"] is None and k["pl"] is None
        assert k["mitQuote"] == 0, "und die Zeile sagt, dass keine Quote da war"
        assert k["hitPct"] == 50.0, "die Trefferquote gibt es trotzdem"

    def test_ohne_ergebnis_gibt_es_keine_trefferquote(self):
        k = S.kennzahlen([_p("2026-09-01"), _p("2026-09-02")])
        assert k["hitPct"] is None and k["treffer"] is None
        assert k["n"] == 2, "gesendet wurde trotzdem — das ist die Zahl, die immer stimmt"

    def test_untergrenzen_erst_ab_der_mindestzahl(self):
        """Ein Punktschaetzer aus 5 Plays mit „UG" davor ist schlimmer als einer ohne."""
        klein = S.kennzahlen([_p("2026-09-01", 1.0, True) for _ in range(5)])
        assert klein["roiUg"] is None
        gross = S.kennzahlen([_p("2026-09-01", (1.0 if i % 2 else -1.0), i % 2 == 1)
                              for i in range(60)])
        assert gross["roiUg"] is not None and gross["hitUg"] is not None


class TestVollstaendigkeit:
    HEUTE = "2026-09-09"

    def test_periode_vor_der_abdeckung_ist_unvollstaendig(self):
        """⭐ Der reale Fall: der Betfair-Ledger beginnt am 26.08. Der August-Balken waere
        seine letzte Woche."""
        plays = [_p("2026-08-26", 1.0, True), _p("2026-09-05", -1.0, False)]
        r = {x["periode"]: x for x in S.perioden_reihen(plays, self.HEUTE)}
        assert r["2026-08"]["vollstaendig"] is False
        assert "26" in r["2026-08"]["grund"] and "zurück" in r["2026-08"]["grund"]

    def test_laufende_periode_ist_unvollstaendig(self):
        plays = [_p("2026-08-01", 1.0, True), _p("2026-09-05", -1.0, False)]
        r = {x["periode"]: x for x in S.perioden_reihen(plays, self.HEUTE)}
        assert r["2026-09"]["vollstaendig"] is False
        assert r["2026-09"]["grund"] == "läuft noch"

    def test_eine_abgeschlossene_periode_innerhalb_der_abdeckung_ist_vollstaendig(self):
        plays = [_p("2026-08-01", 1.0, True), _p("2026-08-20", -1.0, False),
                 _p("2026-09-05", 1.0, True)]
        r = {x["periode"]: x for x in S.perioden_reihen(plays, self.HEUTE)}
        assert r["2026-08"]["vollstaendig"] is True

    def test_perioden_ganz_vor_der_abdeckung_erzeugen_keine_null_zeile(self):
        """Eine Woche ohne jede Chance auf Daten als „0 Plays" zu zeigen, waere eine Aussage
        ueber einen Zeitraum, ueber den die Quelle nichts weiss."""
        plays = [_p("2026-09-08", 1.0, True)]
        wochen = [x for x in S.perioden_reihen(plays, self.HEUTE) if x["art"] == "woche"]
        assert len(wochen) == 1, "nur die Woche, in der die Quelle ueberhaupt beginnt"

    def test_gesamt_ist_immer_vollstaendig(self):
        plays = [_p("2026-08-26", 1.0, True), _p("2026-09-05", -1.0, False)]
        g = [x for x in S.perioden_reihen(plays, self.HEUTE) if x["art"] == "gesamt"][0]
        assert g["vollstaendig"] is True and g["n"] == 2

    def test_ohne_plays_gibt_es_gar_keine_zeilen(self):
        assert S.perioden_reihen([], self.HEUTE) == []


class TestBau:
    def test_bloecke_tragen_gruppe_abdeckung_und_reihen(self):
        d = S.baue()
        assert d["bloecke"], "gegen die echten Artefakte muss etwas herauskommen"
        for b in d["bloecke"]:
            assert b["gruppe"] and b["label"] and b["reihen"]
            assert b["abdeckung"]["von"] and b["abdeckung"]["bis"]
            assert any(r["art"] == "gesamt" for r in b["reihen"])

    def test_die_wm_steht_getrennt_vom_laufenden_betrieb(self):
        """Die WM traegt 160 der 314 abgerechneten Card-Picks und ist seit 19.07. vorbei. Eine
        Gesamtzahl, die zur Haelfte aus einem beendeten Turnier besteht, beantwortet „wie laeuft
        es gerade" mit dem letzten Sommer."""
        d = S.baue()
        ids = {b["id"] for b in d["bloecke"]}
        assert "cards-wm" in ids
        laufend = [b for b in d["bloecke"] if b["id"] == "cards"][0]
        wm = [b for b in d["bloecke"] if b["id"] == "cards-wm"][0]
        n_l = [r for r in laufend["reihen"] if r["art"] == "gesamt"][0]["n"]
        n_w = [r for r in wm["reihen"] if r["art"] == "gesamt"][0]["n"]
        liga = [b for b in d["bloecke"] if b["id"] == "cards-liga"][0]
        mls = [b for b in d["bloecke"] if b["id"] == "cards-mls"][0]
        n_lm = ([r for r in liga["reihen"] if r["art"] == "gesamt"][0]["n"]
                + [r for r in mls["reihen"] if r["art"] == "gesamt"][0]["n"])
        assert n_l == n_lm, "der laufende Betrieb ist genau Liga + MLS"
        assert n_w > 0 and n_l != n_l + n_w

    def test_gesperrte_sportarten_sind_nicht_in_der_poly_bilanz(self):
        """Sie laufen als reine Beobachtung — eine Bilanz dessen, was gespielt werden darf,
        enthaelt sie nicht. Dieselbe Trennung wie im Track-Record."""
        import json
        tr = json.loads((S.BASE / "poly_shortlist_track.json").read_text(encoding="utf-8"))
        gesperrt = set(tr.get("blockedCats") or [])
        if not gesperrt:
            return
        st = tr.get("settled") or []
        st = list(st.values()) if isinstance(st, dict) else st
        n_gesperrt = len([r for r in st if r.get("cat") in gesperrt])
        assert n_gesperrt > 0, "Vorbedingung: es gibt ueberhaupt gesperrte Zeilen"
        n_block = len(S.poly_plays(tr))
        assert n_block == len([r for r in st if r.get("cat") not in gesperrt
                               and S._tag(r.get("settledTs"))])
