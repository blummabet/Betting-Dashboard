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


# Kleine Zusicherungs-Helfer — die Datei nutzt plain asserts, kein unittest.
def _lt(a, b, m=""):   assert a < b, m
def _in(a, b, m=""):   assert a in b, m
def _nin(a, b, m=""):  assert a not in b, m
def _t(a, m=""):       assert a, m
def _none(a, m=""):    assert a is None, m
def _near(a, b, places=6, m=""): assert round(a - b, places) == 0, m
def _skip(m=""):
    import pytest
    pytest.skip(m)


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

    def test_die_wm_ist_von_der_seite_verschwunden_aber_nicht_aus_dem_system(self):
        """10.09.2026 (Lucas: „WM kann raus, wertlos in Wahrheit").

        Am 09.09. stand hier das Gegenteil — der Test verlangte einen eigenen WM-Block. Das war
        richtig, solange die Frage lautete „wie halte ich das beendete Turnier aus der laufenden
        Zahl raus". Lucas' Antwort ist eine Ebene darueber: die Frage stellt niemand mehr.

        Geprueft wird deshalb beides. Der Block ist weg — UND die Daten sind es nicht: wer
        `cards_plays("WM")` fragt, bekommt die Picks weiterhin. Ein Block zu entfernen darf
        keine Auskunft aus dem System nehmen.
        """
        d = S.baue()
        ids = {b["id"] for b in d["bloecke"]}
        assert "cards-wm" not in ids
        assert not any("WM 2026" in b["label"] for b in d["bloecke"])
        assert S.cards_plays("WM"), "die WM-Picks muessen abfragbar bleiben"

    def test_der_laufende_betrieb_ist_genau_liga_plus_mls(self):
        """Und die WM darf nicht durch die Hintertuer in die Gesamtzahl zurueckkommen."""
        d = S.baue()
        def _n(bid):
            b = [x for x in d["bloecke"] if x["id"] == bid]
            return [r for r in b[0]["reihen"] if r["art"] == "gesamt"][0]["n"] if b else 0
        assert _n("cards") == _n("cards-liga") + _n("cards-mls")
        assert _n("cards") < len(S.cards_plays()), "cards_plays() ohne Filter haelt auch die WM"

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


# ── 10.09.2026: die Push-Kanal-Blöcke zählen, was den Kanal verlassen hat ─────────────────
class TestPushKanaeleZaehlenNurPushes:

    def test_der_picks_block_zaehlt_nur_wirklich_gepushtes(self):
        """`pick_push_ledger.json` ist ein SCHATTENBUCH: es haelt jeden announce-faehigen Pick,
        den gesendeten UND den vom Gegensignal-Filter aussortierten, damit sich der Filter nicht
        selbst bestaetigen kann. Als Quelle fuer einen Push-Kanal ist es damit untauglich —
        gemessen am 10.09. standen 127 nie gepushte Picks in der Gruppe „Push-Kanäle"."""
        import json
        bloecke = {b[0]: b for b in S.push_bloecke()}
        for bid, datei in (("liga-picks", "liga_pick_push_ledger.json"),
                           ("mls-picks", "mls_pick_push_ledger.json")):
            if bid not in bloecke:
                continue
            roh = json.loads((S.BASE / datei).read_text(encoding="utf-8"))
            gepusht = [r for r in roh if isinstance(r, dict) and r.get("push")]
            mit_tag = [r for r in gepusht if S._tag(r.get("gesehenAm"))]
            assert len(bloecke[bid][3]) == len(mit_tag), bid
            _lt(len(bloecke[bid][3]), len(roh),
                            "%s: das Schattenbuch ist groesser als der Kanal" % bid)

    def test_die_aussortierten_verschwinden_nicht_stillschweigend(self):
        """Sie werden nicht mitgezaehlt — aber der Block sagt, wie viele es sind. Eine Zahl, die
        kleiner wird, ohne dass jemand erfaehrt warum, ist die schlechtere Haelfte des Tauschs."""
        bloecke = {b[0]: b for b in S.push_bloecke()}
        if "liga-picks" not in bloecke:
            _skip("kein Liga-Ledger im Arbeitsverzeichnis")
        hinweis = bloecke["liga-picks"][4]
        _t(hinweis, "der Block muss die Aussortierten benennen")
        _in("aussortiert", hinweis)


class TestShortlistPushBuch:
    """10.09.2026 (Lucas: „wird das erst seit kurzem getrackt? weil nur 23 in KW 37 und sonst
    nichts"). Nein — die alte Quelle war ein Dedup-Buch mit 3 Tagen TTL und VERGASS."""

    def test_ergebnis_kommt_aus_dem_track_buch_und_preis_aus_dem_push(self):
        led = [{"k": "a|Over", "key": "a", "side": "Over", "sentAt": "2026-09-10T10:00:00+00:00",
                "pushPreis": 0.5, "conv": 7},
               {"k": "b|Under", "key": "b", "side": "Under", "sentAt": "2026-09-10T11:00:00+00:00",
                "pushPreis": 0.8, "conv": 6}]
        tr = {"settled": [{"key": "a", "side": "Over", "result": "win"},
                          {"key": "b", "side": "Under", "result": "loss"}]}
        pl = S.shortlist_push_plays(led, tr)
        assert [p["gewonnen"] for p in pl] == [True, False]
        # Aktien = 1/0.5 → Gewinner zahlt 1.00 je Aktie → Rendite +1.0 je Einheit Einsatz.
        _near(pl[0]["rendite"], 1.0)
        _near(pl[1]["rendite"], -1.0)

    def test_der_push_preis_entscheidet_nicht_der_scan_preis(self):
        """Wer dem Push folgt, steigt zu dem Preis ein, der in der Nachricht stand."""
        tr = {"settled": [{"key": "a", "side": "Over", "result": "win"}]}
        teuer = S.shortlist_push_plays([{"k": "a|Over", "key": "a", "side": "Over",
                                         "sentAt": "2026-09-10T10:00:00+00:00", "pushPreis": 0.9}], tr)
        billig = S.shortlist_push_plays([{"k": "a|Over", "key": "a", "side": "Over",
                                          "sentAt": "2026-09-10T10:00:00+00:00", "pushPreis": 0.5}], tr)
        _lt(teuer[0]["rendite"], billig[0]["rendite"])

    def test_ein_push_ohne_ausgang_zaehlt_als_zeile_ohne_treffer(self):
        """Er ist gesendet worden — das ist die eine Zahl, die immer stimmt. Eine Rendite hat er
        nicht, und die darf nicht als 0 erscheinen."""
        pl = S.shortlist_push_plays([{"k": "x|Over", "key": "x", "side": "Over",
                                      "sentAt": "2026-09-10T10:00:00+00:00", "pushPreis": 0.6}],
                                    {"settled": []})
        assert len(pl) == 1
        _none(pl[0]["gewonnen"])
        _none(pl[0]["rendite"])

    def test_ohne_preis_gibt_es_keine_rendite(self):
        pl = S.shortlist_push_plays([{"k": "a|Over", "key": "a", "side": "Over",
                                      "sentAt": "2026-09-10T10:00:00+00:00"}],
                                    {"settled": [{"key": "a", "side": "Over", "result": "win"}]})
        _t(pl[0]["gewonnen"])
        _none(pl[0]["rendite"], "ohne Preis keine Zahl — auch keine Null")

    def test_das_dedup_buch_ist_keine_quelle_mehr(self):
        """Der eigentliche Fund: `shortlist_push_seen.json` raeumt sich nach 3 Tagen selbst auf.
        Wer daraus eine Historie baut, zeigt leere Wochen, in denen sehr wohl gepusht wurde."""
        import inspect
        quelle = inspect.getsource(S.push_bloecke)
        _nin('_load("shortlist_push_seen.json"', quelle)
