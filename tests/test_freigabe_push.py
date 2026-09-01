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
        assert "Untergrenze +4%" in txt, "ohne UG ist die Freigabe eine Behauptung"
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
        assert json.loads(st.read_text()) == {"A": True}
