"""tests/test_freigabe_push.py — 01.09.2026

Der seltenste und wichtigste Push des Systems: eine Schublade wird freigegeben — oder verliert
ihre Freigabe wieder. Geprüft werden die vier Arten, wie so ein Zustands-Melder schiefgeht:
  · er flutet beim Erstlauf den Channel mit allem, was schon lange so ist,
  · er meldet Zwischenstufen, die sich ohnehin dauernd ändern,
  · er meldet die gute Nachricht und verschweigt die schlechte,
  · er verliert eine Meldung, weil er den Zustand fortschreibt, bevor gesendet wurde.
"""
import json

import freigabe_push as FP


def schub(name, status, **extra):
    d = {"schublade": name, "strom": "poly", "n": 34, "status": status,
         "roi": 0.21, "roiLb": 0.04, "clv": 0.9}
    d.update(extra)
    return d


def reg(*schubladen, **extra):
    d = {"alle": list(schubladen), "regeln": {"minN": 30, "text": "n>=30 UND ROI-UG>0"},
         "engine": "2026-09-01", "engineGefiltert": True}
    d.update(extra)
    return d


class TestWechsel:
    def test_erstlauf_meldet_nichts_lernt_aber_alles(self):
        # Sonst gingen beim ersten Start 38 Schubladen raus und die erste ECHTE Freigabe
        # ginge in dieser Flut unter.
        rauf, runter, neu = FP.wechsel(reg(schub("A", "freigegeben"), schub("B", "kandidat")), None)
        assert rauf == [] and runter == []
        assert neu == {"A": True, "B": False}

    def test_freigabe_wird_gemeldet(self):
        rauf, runter, _ = FP.wechsel(reg(schub("A", "freigegeben")), {"A": False})
        assert [r["schublade"] for r in rauf] == ["A"] and runter == []

    def test_ruecknahme_wird_GENAUSO_gemeldet(self):
        # Wer nur die gute Nachricht schickt, baut die Asymmetrie ein, die Geld kostet.
        rauf, runter, _ = FP.wechsel(reg(schub("A", "geprueft")), {"A": True})
        assert rauf == [] and [r["schublade"] for r in runter] == ["A"]

    def test_zwischenstufen_sind_keine_nachricht(self):
        for vorher, nachher in (("sammelt", "kandidat"), ("kandidat", "geprueft"),
                                ("geprueft", "ruht")):
            rauf, runter, _ = FP.wechsel(reg(schub("A", nachher)), {"A": False})
            assert not rauf and not runter, f"{vorher}→{nachher} darf nicht pushen"

    def test_neue_schublade_wird_erst_kennengelernt(self):
        rauf, runter, neu = FP.wechsel(reg(schub("A", "freigegeben"), schub("NEU", "freigegeben")),
                                       {"A": True})
        assert rauf == [] and runter == [] and neu["NEU"] is True

    def test_unveraenderte_freigabe_pusht_nicht_nochmal(self):
        rauf, runter, _ = FP.wechsel(reg(schub("A", "freigegeben")), {"A": True})
        assert not rauf and not runter


class TestNachricht:
    def test_freigabe_nennt_untergrenze_und_regel(self):
        txt = FP.nachricht([schub("Mix bf+money", "freigegeben")], [], reg())
        assert "FREIGEGEBEN" in txt
        # 08.09.2026: eine Nachkommastelle — s. TestLockereFreigabeWarntTrotzdem unten.
        assert "Untergrenze +4.0%" in txt, "ohne UG ist die Freigabe eine Behauptung"
        assert "n=34" in txt and "n&gt;=30" in txt

    def test_ruecknahme_sagt_klar_nicht_mehr_spielen(self):
        txt = FP.nachricht([], [schub("Mix bf+money", "geprueft", roiLb=-0.03)], reg())
        assert "ZURÜCKGENOMMEN" in txt and "NICHT mehr blind spielbar" in txt

    def test_engine_steht_dabei(self):
        assert "2026-09-01" in FP.nachricht([schub("A", "freigegeben")], [], reg())


class TestMain:
    def test_unlesbare_datei_taastet_den_zustand_nicht_an(self, tmp_path, monkeypatch):
        # Fehlende Information ist keine Erlaubnis — und darf sich nicht wie „alles verloren"
        # verhalten, sonst kommen beim naechsten Lauf ⛔-Meldungen fuer alles.
        st = tmp_path / "state.json"
        st.write_text(json.dumps({"A": True}), encoding="utf-8")
        monkeypatch.setattr(FP, "STATE_FILE", st)
        monkeypatch.setattr(FP, "FREIGABE_FILE", tmp_path / "fehlt.json")
        gesendet = []
        monkeypatch.setattr(FP.TG, "send_trades_message", lambda t: gesendet.append(t) or True)
        FP.main()
        assert gesendet == []
        assert json.loads(st.read_text()) == {"A": True}, "Zustand muss unveraendert bleiben"

    def test_sende_fehler_haelt_den_zustand_zurueck(self, tmp_path, monkeypatch):
        # Sonst gilt der Wechsel als gemeldet und die Nachricht ist fuer immer verloren.
        st = tmp_path / "state.json"
        st.write_text(json.dumps({"A": False}), encoding="utf-8")
        fg = tmp_path / "freigabe.json"
        fg.write_text(json.dumps(reg(schub("A", "freigegeben"))), encoding="utf-8")
        monkeypatch.setattr(FP, "STATE_FILE", st)
        monkeypatch.setattr(FP, "FREIGABE_FILE", fg)
        monkeypatch.setattr(FP.TG, "send_trades_message", lambda t: False)
        monkeypatch.delenv("DRY_RUN", raising=False)
        FP.main()
        assert json.loads(st.read_text()) == {"A": False}, "unversandter Wechsel bleibt offen"

    def test_erfolgreicher_send_schreibt_den_zustand_fort(self, tmp_path, monkeypatch):
        st = tmp_path / "state.json"
        st.write_text(json.dumps({"A": False}), encoding="utf-8")
        fg = tmp_path / "freigabe.json"
        fg.write_text(json.dumps(reg(schub("A", "freigegeben"))), encoding="utf-8")
        monkeypatch.setattr(FP, "STATE_FILE", st)
        monkeypatch.setattr(FP, "FREIGABE_FILE", fg)
        gesendet = []
        monkeypatch.setattr(FP.TG, "send_trades_message", lambda t: gesendet.append(t) or True)
        monkeypatch.delenv("DRY_RUN", raising=False)
        FP.main()
        assert len(gesendet) == 1 and "FREIGEGEBEN" in gesendet[0]
        # 08.09.2026: der Zustand traegt seit dem Spiele-Push zwei Ebenen — die Schubladen und
        # die je Schublade gemeldeten Plays. Beides in EINER Datei, damit ein Sendefehler nicht
        # die eine Haelfte fortschreibt und die andere nicht.
        assert json.loads(st.read_text())["schubladen"] == {"A": True}

    def test_alte_flache_zustandsdatei_wird_weiter_gelesen(self, tmp_path, monkeypatch):
        """Die Datei im Repo ist die flache Form von vor dem 08.09. Wuerde sie nicht mehr
        gelesen, gaelte der naechste Lauf als Erstlauf — und der meldet NICHTS. Genau die
        Freigabe, auf die seit Wochen gewartet wird, ginge still verloren."""
        st = tmp_path / "state.json"
        st.write_text(json.dumps({"A": False}), encoding="utf-8")
        fg = tmp_path / "freigabe.json"
        fg.write_text(json.dumps(reg(schub("A", "freigegeben"))), encoding="utf-8")
        monkeypatch.setattr(FP, "STATE_FILE", st)
        monkeypatch.setattr(FP, "FREIGABE_FILE", fg)
        gesendet = []
        monkeypatch.setattr(FP.TG, "send_trades_message", lambda t: gesendet.append(t) or True)
        monkeypatch.delenv("DRY_RUN", raising=False)
        FP.main()
        assert len(gesendet) == 1 and "FREIGEGEBEN" in gesendet[0], (
            "eine alte Zustandsdatei darf nicht wie ein Erstlauf wirken")


# ── 08.09.2026: „Freigabe locker" — der Push muss die Lockerung mittragen ────────────────
# Lucas: „ja zum Testen mal in Trades-Channel." Der Push geht damit an Schubladen raus, deren
# CLV nichts beweist oder sogar dagegen spricht — bis heute waeren die gar nicht freigegeben
# worden. Wer den Push liest, spielt danach; er darf die einzige Warnung, die es zu dieser
# Freigabe noch gibt, nicht nur im Frontend finden.
def _frei(**over):
    r = {"schublade": "Liga · ABWÄGEN", "strom": "cards", "n": 91, "status": "freigegeben",
         "roi": 0.1518, "roiLb": 0.0076, "clv": -1.524, "clvLb": -2.011, "clvOg": -1.038,
         "clvUrteil": "negativ belegt", "grund": "ROI belegt …"}
    r.update(over)
    return r


class TestLockereFreigabeWarntTrotzdem:
    def test_negativ_belegter_clv_steht_als_warnung_im_push(self):
        t = FP.nachricht([_frei()], [], {})
        assert "⚠️" in t and "CLV spricht dagegen" in t
        assert "−6,8" in t, "ohne die Zahl ist die Warnung eine Meinung"

    def test_nicht_erhobener_clv_ist_keine_warnung_sondern_eine_luecke(self):
        """Der Unterschied, den die Umstellung ueberhaupt erst noetig gemacht hat: gegen eine
        Schublade ohne CLV-Erhebung ist nichts gemessen. Ein ⚠️ dort waere eine Behauptung."""
        t = FP.nachricht([_frei(clv=None, clvLb=None, clvOg=None,
                                clvUrteil="nicht erhoben")], [], {})
        assert "kein CLV erhoben" in t or "gar kein CLV" in t
        assert "CLV spricht dagegen" not in t

    def test_gemessen_aber_unbelegt_ist_ein_dritter_zustand(self):
        t = FP.nachricht([_frei(clv=-0.8, clvLb=-2.528, clvOg=0.928,
                                clvUrteil="gemessen, nicht belegt")], [], {})
        assert "weder" in t and "CLV spricht dagegen" not in t

    def test_belegter_clv_bekommt_keine_zusatzzeile(self):
        t = FP.nachricht([_frei(clv=2.1, clvLb=1.2, clvOg=3.0, clvUrteil="belegt")], [], {})
        assert "CLV spricht dagegen" not in t and "weder" not in t

    def test_kopfzeile_sagt_WELCHE_untergrenze(self):
        """Frueher mussten beide stimmen, „die Untergrenze" war eindeutig. Jetzt nicht mehr —
        und eine Kopfzeile, die das verschweigt, liest sich wie eine Zusicherung, die sie
        nicht mehr ist."""
        t = FP.nachricht([_frei()], [], {})
        assert "Rendite</b>-Untergrenze" in t or "Rendite-Untergrenze" in t

    def test_untergrenze_mit_nachkommastelle(self):
        """+0,76 % als „+1%" gerundet ist genau in diesem Bereich keine Zahl mehr — dieselbe
        Korrektur wie auf dem Board."""
        t = FP.nachricht([_frei(roiLb=0.0076)], [], {})
        assert "+0.8%" in t and "+1%" not in t

    def test_bei_der_freigabe_steht_die_warnung_nur_einmal(self):
        """Zweimal dieselbe Warnung liest sich beim dritten Push wie Formelsprache."""
        t = FP.nachricht([_frei(grund="⚠️ der CLV ist dagegen negativ belegt (Obergrenze …)")],
                         [], {})
        assert t.count("⚠️") == 1, ("die Warnung steht einmal — der `grund` sagt bei einer "
                                    "Freigabe dasselbe noch einmal und gehoert deshalb nur "
                                    "an die Ruecknahme")

    def test_bei_der_ruecknahme_bleibt_der_grund_stehen(self):
        """Dort ist er die einzige Auskunft darueber, WELCHE Bedingung gekippt ist."""
        t = FP.nachricht([], [_frei(status="geprueft",
                                    grund="ROI nicht belegt über null")], {})
        assert "ROI nicht belegt über null" in t


# ── 08.09.2026: der Spiele-Push ─────────────────────────────────────────────────────────
def _fg_spiele(plays, schublade="Liga · ABWÄGEN", aufloesbar=True, **over):
    b = {"schublade": schublade, "strom": "cards", "roiLb": 0.0076,
         "clvUrteil": "negativ belegt", "aufloesbar": aufloesbar, "laufend": 0,
         "n": len(plays), "plays": plays}
    b.update(over)
    return {"spiele": [b]}


def _p(i, spiel="Venezia v Fiorentina", auswahl="Über 2.5 Tore", quote=1.78):
    return {"id": "id%d" % i, "spiel": spiel, "auswahl": auswahl, "quote": quote,
            "anpfiff": "2026-09-11T18:45:00+00:00"}


class TestSpielePush:
    def test_erstlauf_meldet_nichts(self):
        """31 Picks beim ersten Lauf waeren Tapete, und der erste echte Neuzugang ginge darin
        unter — dieselbe Regel wie beim Schublade-Zustand."""
        meldung, state = FP.play_wechsel(_fg_spiele([_p(1), _p(2)]), {})
        assert meldung == {}
        assert state["Liga · ABWÄGEN"] == ["id1", "id2"], "gelernt wird trotzdem"

    def test_nur_NEUE_plays_werden_gemeldet(self):
        alt = {"plays": {"Liga · ABWÄGEN": ["id1"]}}
        meldung, state = FP.play_wechsel(_fg_spiele([_p(1), _p(2)]), alt)
        assert [x["id"] for x in meldung["Liga · ABWÄGEN"]] == ["id2"]
        assert state["Liga · ABWÄGEN"] == ["id1", "id2"]

    def test_verschwundene_plays_erzeugen_keine_nachricht(self):
        """Ein angepfiffenes Spiel faellt still aus dem Zustand — ein „zu spaet"-Push waere
        Rauschen ueber etwas, das man ohnehin nicht mehr tun kann."""
        alt = {"plays": {"Liga · ABWÄGEN": ["id1", "id2"]}}
        meldung, state = FP.play_wechsel(_fg_spiele([_p(1)]), alt)
        assert meldung == {} and state["Liga · ABWÄGEN"] == ["id1"]

    def test_nicht_aufloesbare_schublade_erzeugt_weder_meldung_noch_zustand(self):
        """Sonst stuende beim naechsten Lauf „0 Spiele" fuer eine Schublade, ueber deren Spiele
        wir gar nichts wissen — genau die Verwechslung, gegen die `aufloesbar` gebaut ist."""
        fg = _fg_spiele([], schublade="Half Time", aufloesbar=False)
        meldung, state = FP.play_wechsel(fg, {"plays": {}})
        assert meldung == {} and "Half Time" not in state

    def test_die_nachricht_traegt_die_untergrenze_der_schublade(self):
        """Ohne sie liest sich die Liste wie eine Tipp-Empfehlung statt wie „aus diesem
        belegten Schnitt"."""
        fg = _fg_spiele([_p(1)])
        t = FP.play_nachricht({"Liga · ABWÄGEN": [_p(1)]}, fg)
        assert "Rendite-Untergrenze" in t and "+0.8%" in t
        assert "Venezia v Fiorentina" in t and "@1.78" in t

    def test_die_clv_warnung_reist_mit_zu_den_spielen(self):
        """Die Warnung gehoert an JEDE Nachricht, die auf dieser Schublade beruht — nicht nur
        an die eine, in der sie freigegeben wurde."""
        fg = _fg_spiele([_p(1)])
        t = FP.play_nachricht({"Liga · ABWÄGEN": [_p(1)]}, fg)
        assert "⚠️" in t and "CLV" in t

    def test_lange_listen_werden_gedeckelt_und_gezaehlt(self):
        plays = [_p(i) for i in range(20)]
        t = FP.play_nachricht({"Liga · ABWÄGEN": plays}, _fg_spiele(plays))
        assert t.count("▸") == FP.PLAY_MAX
        assert "und %d weitere" % (20 - FP.PLAY_MAX) in t

    def test_wochentag_steht_deutsch_da(self):
        """`%a` liefert unter der C-Locale des Runners „Fri" — in einer deutschen Nachricht ein
        Fremdkoerper, und eine Locale zu setzen waere eine Abhaengigkeit vom Runner-Image."""
        t = FP.play_nachricht({"Liga · ABWÄGEN": [_p(1)]}, _fg_spiele([_p(1)]))
        assert "Fr 11.09." in t and "Fri" not in t
