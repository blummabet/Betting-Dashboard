# -*- coding: utf-8 -*-
"""tests/test_freigabe.py — 29.08.2026 (Lucas: „eine Sektion, die ich blind nehmen kann").

Das Register entscheidet, was blind spielbar ist. Es darf in genau zwei Richtungen falsch liegen,
und die eine ist viel teurer als die andere: eine Schublade zu FRUEH freizugeben kostet echtes
Geld und das Vertrauen in die Sektion; eine zu spaet freizugeben kostet Wartezeit. Diese Tests
sichern deshalb vor allem die Nein-Faelle.
"""
import math

import freigabe as F


def _plays(n, r, clv, stake=10.0, ev="X", tage_alt=1):
    """Fixture-Plays. `settledTs` gehoert dazu: seit der Lebendig-Bedingung ist eine Schublade
    ohne Datum nicht freigebbar — ein Fixture ohne Zeitstempel wuerde also etwas anderes testen
    als gemeint."""
    from datetime import timedelta
    ts = (F._now() - timedelta(days=tage_alt)).isoformat()
    return [{"pnl": r * stake, "stake": stake, "clvPP": clv, "conv": 7, "signals": ["money"],
             "ev": ev, "settledTs": ts} for _ in range(n)]


class TestUntergrenze:
    def test_streuung_null_ist_der_mittelwert(self):
        assert abs(F.untergrenze([0.2] * 40) - 0.2) < 1e-9

    def test_mehr_stichprobe_hebt_die_untergrenze(self):
        klein = F.untergrenze([0.4, -0.1, 0.3, -0.2, 0.5])
        gross = F.untergrenze([0.4, -0.1, 0.3, -0.2, 0.5] * 20)
        assert klein < gross

    def test_unter_drei_werten_wird_nicht_geraten(self):
        assert F.untergrenze([0.5, 0.5]) is None


class TestBewertung:
    def test_klar_positiv_und_genug_historie_wird_freigegeben(self):
        from datetime import timedelta
        r = [0.25, 0.30, 0.20, 0.28, 0.22] * 8          # n=40, eng gestreut, klar > 0
        c = [1.2, 1.5, 0.9, 1.1, 1.3] * 8
        e = F.bewerte("test", "poly", r, c, letzter=(F._now() - timedelta(days=1)).isoformat())
        assert e["status"] == "freigegeben", e

    def test_hoher_roi_mit_negativem_clv_wird_NICHT_freigegeben(self):
        # Der Cards-Fall: +3,2% ROI sah spielbar aus, der CLV lag bei -2,01pp (UG -2,43) ueber
        # 216 Picks. Positiver ROI bei sicher negativem CLV heisst: der Gewinn kam aus der
        # Varianz, nicht aus einer Kante. Genau das darf nie durchrutschen.
        r = [0.25, 0.30, 0.20, 0.28, 0.22] * 8
        c = [-2.0, -2.2, -1.8, -2.1, -1.9] * 8
        e = F.bewerte("test", "cards", r, c)
        assert e["status"] == "geprueft"
        assert "CLV" in e["grund"]

    def test_ohne_messbaren_clv_keine_freigabe(self):
        r = [0.25, 0.30, 0.20, 0.28, 0.22] * 8
        e = F.bewerte("test", "x", r, [])
        assert e["status"] == "geprueft" and "CLV" in e["grund"]

    def test_gute_zahlen_aber_zu_wenig_plays_bleiben_kandidat(self):
        r = [0.25, 0.30, 0.20, 0.28, 0.22] * 3          # n=15 < MIN_N
        c = [1.2, 1.5, 0.9, 1.1, 1.3] * 3
        e = F.bewerte("test", "poly", r, c)
        assert e["status"] == "kandidat" and e["fehltN"] == F.MIN_N - 15

    def test_rauschen_um_null_wird_nicht_freigegeben(self):
        r = [0.9, -1.0, 0.8, -1.0, 1.1, -1.0] * 8       # n=48, Mittel knapp positiv, breit gestreut
        c = [0.1, -0.1] * 24
        assert F.bewerte("test", "poly", r, c)["status"] == "geprueft"


class TestPolyEngineFilter:
    def test_alte_engine_zaehlt_fuer_eine_freigabe_nicht(self):
        # Anders als beim Kalibrierer (halbes Gewicht) gilt hier: Halbwissen ist keine Erlaubnis.
        track = {"settled": _plays(40, 0.25, 1.2, ev="alt") + _plays(5, 0.25, 1.2, ev="neu")}
        nur_neu = F.poly_schubladen(track, engine="neu")
        assert all(e["n"] == 5 for e in nur_neu if e["art"] == "conviction")
        # ⚠️ 01.09.2026: hier stand `engine=None` als „kein Filter". Die Bedeutung hat sich
        # umgedreht — None heisst jetzt „aus den Daten bestimmen", weil der Filter sonst wieder
        # nie greift (die Env, an der er hing, hat nie jemand gesetzt). Ausdruecklich NICHT
        # filtern heisst jetzt `engine=False`.
        ohne_filter = F.poly_schubladen(track, engine=False)
        assert any(e["n"] == 45 for e in ohne_filter if e["art"] == "conviction")
        # Und die Gegenprobe: der Default filtert wirklich.
        default = F.poly_schubladen(track)
        assert all(e["n"] == 5 for e in default if e["art"] == "conviction"), \
            "Default muss die aktuelle Engine erkennen (Mehrheit der juengsten Plays)"


class TestBetfair:
    def test_betfair_wird_nie_freigegeben_solange_kein_clv_im_ledger_steht(self):
        rec = {"byMarket": {"Match Odds": {"n": 5000, "hitRate": 0.60, "roi": 0.25}}}
        e = F.betfair_schubladen(rec)[0]
        assert e["status"] != "freigegeben"
        assert "CLV" in e["grund"]
        assert e["naeherung"] is True      # die Streuung ist rekonstruiert, nicht gemessen

    def test_zu_kleine_liga_markt_eimer_fallen_raus(self):
        rec = {"byLeagueMarket": {"Irgendwo|Match Odds": {"n": 5, "hitRate": 0.8, "roi": 0.5}}}
        assert F.betfair_schubladen(rec) == []

    def test_streuung_naeherung_ist_plausibel(self):
        # 50% Treffer bei ROI 0 => mittlere Quote 2.0 => sd = 2*0.5 = 1.0 => se = 1/sqrt(n)
        se = F._betfair_streuung(100, 0.5, 0.0)
        assert abs(se - 0.1) < 1e-9


class TestBau:
    def test_leeres_register_ist_ein_gueltiges_ergebnis(self):
        d = F.baue(track={"settled": []}, cards=[], betfair={})
        assert d["freigegeben"] == [] and d["zusammenfassung"]["freigegeben"] == 0
        assert "minN" in d["regeln"]

    def test_freigegebene_stehen_oben(self):
        # Gleiche Rendite bei jedem Play -> Streuung null -> Untergrenze = Mittelwert.
        track = {"settled": _plays(40, 0.25, 1.2, ev="neu")}
        d = F.baue(engine="neu", track=track, cards=[], betfair={})
        assert d["alle"][0]["status"] == "freigegeben"
        assert d["zusammenfassung"]["freigegeben"] >= 1

    def test_naechste_freigabe_zeigt_die_kuerzeste_distanz(self):
        cards = ([{"ds": "Liga", "verdict": "BET", "r": 0.2, "clv": 1.0}] * 25
                 + [{"ds": "MLS", "verdict": "BET", "r": 0.2, "clv": 1.0}] * 12)
        d = F.baue(track={"settled": []}, cards=cards, betfair={})
        assert d["zusammenfassung"]["naechsteFreigabe"] == F.MIN_N - 25


# ── Lebendig-Bedingung (29.08.2026, Lucas: „Was heisst bis WM BET? Was WM?") ─────────────
# Die erste Fassung fuehrte „WM · BET" als Kandidat mit „noch 5 Plays". Die WM ist seit dem
# 28.06. durch — die fuenf Plays kommen nie, und selbst freigegeben waere die Schublade nicht
# spielbar. Freigegeben muss heissen „das kannst du MORGEN spielen".
class TestLebendig:
    def _rows(self, n, r, clv, tage_alt):
        from datetime import timedelta
        ts = (F._now() - timedelta(days=tage_alt)).isoformat()
        return ([r] * n, [clv] * n, ts)

    def test_alte_schublade_ruht_statt_kandidat_zu_sein(self):
        r, c, ts = self._rows(25, 0.17, -0.6, F.MAX_ALTER_TAGE + 40)
        e = F.bewerte("WM · BET", "cards", r, c, letzter=ts)
        assert e["status"] == "ruht"
        assert "liefert nichts mehr" in e["grund"]
        assert e["fehltN"] == 0, "eine tote Schublade wartet auf nichts"

    def test_alte_schublade_wird_auch_bei_top_zahlen_nicht_freigegeben(self):
        # Sonst waere „hat mal funktioniert" eine Spielerlaubnis.
        r = [0.25, 0.30, 0.20, 0.28, 0.22] * 8
        c = [1.2, 1.5, 0.9, 1.1, 1.3] * 8
        from datetime import timedelta
        alt = (F._now() - timedelta(days=F.MAX_ALTER_TAGE + 1)).isoformat()
        assert F.bewerte("alt", "poly", r, c, letzter=alt)["status"] == "ruht"

    def test_frische_schublade_wird_normal_bewertet(self):
        r = [0.25, 0.30, 0.20, 0.28, 0.22] * 8
        c = [1.2, 1.5, 0.9, 1.1, 1.3] * 8
        from datetime import timedelta
        frisch = (F._now() - timedelta(days=2)).isoformat()
        assert F.bewerte("frisch", "poly", r, c, letzter=frisch)["status"] == "freigegeben"

    def test_ohne_zeitstempel_wird_nicht_als_frisch_unterstellt(self):
        # Kein Datum heisst nicht „von heute". Die Bewertung laeuft normal weiter, aber das Alter
        # steht als unbekannt drin — sichtbar statt stillschweigend gutgeschrieben.
        r = [0.25, 0.30, 0.20, 0.28, 0.22] * 8
        e = F.bewerte("ohne", "poly", r, [1.0] * 40, letzter=None)
        assert e["alterTage"] is None

    def test_ohne_datum_gibt_es_keine_freigabe(self):
        # Fail-closed wie bei fehlendem CLV. Aufgefallen an KO-3RD-FRA-SEN: Picks, zu denen im
        # Datensatz gar kein Fixture steht -> undatierbar. Ohne diese Klausel koennte so eine
        # Schublade bei guten Zahlen freigegeben werden, obwohl niemand weiss, ob sie noch lebt.
        r = [0.25, 0.30, 0.20, 0.28, 0.22] * 8
        c = [1.2, 1.5, 0.9, 1.1, 1.3] * 8
        e = F.bewerte("undatiert", "poly", r, c, letzter=None)
        assert e["status"] == "geprueft" and "Datum" in e["grund"]

    def test_die_echte_WM_wartet_auf_nichts_mehr(self):
        # Gegen die echten Dateien: die WM ist seit dem 28.06. durch. Keine ihrer Schubladen
        # darf noch in der Warteschlange stehen oder gar freigegeben sein.
        wm = [e for e in F.card_schubladen() if e.get("datensatz") == "WM"]
        assert wm, "keine WM-Schublade gefunden"
        assert not [e for e in wm if e["status"] in ("freigegeben", "kandidat")], wm


# ── Engine-Trennung (01.09.2026) ─────────────────────────────────────────────
# Der Filter existierte seit dem 29.08., hing aber an FREIGABE_ENGINE — und die Variable wurde
# nirgends gesetzt. Das Register mischte deshalb Engine-Versionen: die staerkste Schublade
# („Conviction 9") bestand ausschliesslich aus Plays einer Engine, die es nicht mehr gab.
# Jetzt kommt die Engine aus den Daten, und Alt-Plays zaehlen nicht mehr fuer die Freigabe —
# verschwinden aber auch nicht, sonst sieht „veraltete Datenbasis" aus wie „gab es nie".

def _play(ev, conv=9, pnl=5.0, clv=1.0, ts="2026-09-01T10:00:00+00:00"):
    return {"conv": conv, "pnl": pnl, "stake": 10.0, "clvPP": clv, "ev": ev,
            "settledTs": ts, "signals": ["money"]}


def _track(rows, offen=None):
    return {"settled": rows, "open": offen or []}


class TestAktuelleEngine:
    def test_mehrheit_der_juengsten_plays_entscheidet(self):
        t = _track([_play("alt")] * 40 + [_play("neu")] * 20)
        assert F.aktuelle_engine(t) == "neu"

    def test_eine_ausreisser_zeile_kippt_das_register_nicht(self):
        # Genau der Grund fuer Mehrheit statt „letzte Zeile".
        t = _track([_play("neu")] * 24 + [_play("muell")])
        assert F.aktuelle_engine(t) == "neu"

    def test_ohne_stempel_faellt_sie_auf_die_offenen_zurueck(self):
        t = _track([{"conv": 7, "pnl": 1, "stake": 10}], offen=[{"ev": "neu"}])
        assert F.aktuelle_engine(t) == "neu"

    def test_gar_kein_stempel_heisst_nicht_filtern(self):
        # Eine alte Datei ohne Stempel darf das Register nicht leeren.
        assert F.aktuelle_engine(_track([{"conv": 7, "pnl": 1, "stake": 10}])) is None


class TestEngineTrennung:
    def test_alt_plays_zaehlen_nicht_fuer_die_freigabe(self):
        t = _track([_play("alt")] * 40 + [_play("neu")] * 25)
        z = [r for r in F.poly_schubladen(t) if r["schublade"] == "Conviction 9"][0]
        assert z["n"] == 25, "nur die aktuelle Engine zaehlt"
        assert z["nAlt"] == 40
        assert z["status"] != "freigegeben", "25 < 30 -> keine Freigabe"

    def test_reine_alt_schublade_verschwindet_nicht_sondern_erklaert_sich(self):
        t = _track([_play("alt")] * 12 + [_play("neu", conv=5)] * 30)
        z = [r for r in F.poly_schubladen(t) if r["schublade"] == "Conviction 9"]
        assert len(z) == 1, "die Schublade muss sichtbar bleiben"
        assert z[0]["n"] == 0 and z[0]["nAlt"] == 12
        assert "frueheren" in z[0]["grund"], "der Grund muss die veraltete Datenbasis benennen"

    def test_alt_kennzahlen_stehen_als_kontext_daneben(self):
        t = _track([_play("alt", pnl=8.0)] * 10 + [_play("neu")] * 5)
        z = [r for r in F.poly_schubladen(t) if r["schublade"] == "Conviction 9"][0]
        assert abs(z["roiAlt"] - 0.8) < 1e-6, "Alt-ROI wird berichtet, nur nicht gewertet"
        assert z["engineAlt"] is True

    def test_ohne_filter_zaehlt_wieder_alles(self):
        t = _track([_play("alt")] * 40 + [_play("neu")] * 25)
        z = [r for r in F.poly_schubladen(t, engine=False) if r["schublade"] == "Conviction 9"][0]
        assert z["n"] == 65 and "nAlt" not in z

    def test_default_filtert_wirklich(self):
        """Der eigentliche Bug: der Filter war da und griff nie."""
        t = _track([_play("alt")] * 40 + [_play("neu")] * 25)
        ohne = [r for r in F.poly_schubladen(t, engine=False) if r["schublade"] == "Conviction 9"][0]
        mit = [r for r in F.poly_schubladen(t) if r["schublade"] == "Conviction 9"][0]
        assert mit["n"] < ohne["n"], "ohne diesen Unterschied ist der Filter wieder tot"


def test_umschalten_direkt_nach_einem_versionssprung():
    """Der Grund fuer „juengster mit Belegen" statt „Mehrheit".

    Direkt nach einem Sprung ist die Mehrheit im Fenster noch der ALTE Stempel. Wuerde das
    Register ihm folgen, zaehlte es einen halben Tag lang genau die Plays als aktuell, die es
    gerade aussortieren soll — und eine Schublade koennte in diesem Fenster auf alter Datenbasis
    freigegeben werden.
    """
    t = _track([_play("alt")] * 22 + [_play("neu")] * 3)
    assert F.aktuelle_engine(t) == "neu", "drei frische Plays reichen zum Umschalten"
    knapp = _track([_play("alt")] * 23 + [_play("neu")] * 2)
    assert F.aktuelle_engine(knapp) == "alt", "zwei sind noch kein Beleg"


class TestDateiSagtWoraufSieGefiltertHat:
    """Eine Datei, die ueber ihre eigene Filterung schweigt, ist der Grund, warum der tote
    Filter monatelang niemandem auffiel: `freigabe.json` trug `engine: null` — und das sah aus
    wie „nicht gefiltert", war aber schlicht der durchgereichte Parameter."""

    def _t(self):
        return _track([_play("alt")] * 40 + [_play("neu")] * 25)

    def test_default_meldet_die_erkannte_engine(self):
        d = F.baue(track=self._t())
        assert d["engine"] == "neu"
        assert d["engineGefiltert"] is True

    def test_bewusst_ohne_filter_meldet_das_auch(self):
        d = F.baue(engine=False, track=self._t())
        assert d["engine"] is None
        assert d["engineGefiltert"] is False

    def test_erzwungene_engine_wird_gemeldet(self):
        d = F.baue(engine="alt", track=self._t())
        assert d["engine"] == "alt" and d["engineGefiltert"] is True
