"""tests/test_killer_push.py — 01.09.2026

Lucas: „macht es Sinn, das als Telegram-Push in den Trades-Channel zu schicken … und tracken wir
da alles, damit wir wissen ob's funktioniert?"

Geprüft werden die Stellen, an denen ein Push-Kanal typischerweise lügt:
  · er schickt dasselbe zweimal,
  · er verspricht mehr, als das Buch hergibt,
  · er trägt eine Zeile ins Buch ein, die gar nicht rausging (oder umgekehrt),
  · er misst den Erfolg am Preis der FLÄCHE statt am Preis, der in der Nachricht stand.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

import killer_push as KP


def _now():
    return datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def zeile(mid="1", vor_min=90, stufe=1, odd=1.8, **extra):
    ko = _now() + timedelta(minutes=vor_min)
    z = {"matchId": mid, "markt": "Match Odds", "home": "Arsenal", "away": "Chelsea",
         "league": "English Premier League", "seite": "home", "name": "Arsenal",
         "odd": odd, "haltePreis": 1.75, "stufe": stufe, "anteilPct": 74,
         "kickoff": ko.isoformat().replace("+00:00", "Z"), "verstaerker": [], "poly": None}
    z.update(extra)
    return z


def kd(*zeilen):
    s1 = [z for z in zeilen if z["stufe"] == 1]
    s2 = [z for z in zeilen if z["stufe"] != 1]
    return {"stufe1": s1, "stufe2": s2}


class TestAuswahl:
    def test_nur_stufe_1_wird_gepusht(self):
        # 20-58 Zeilen/Tag insgesamt, davon ~5 Stufe 1. Stufe 2 traegt im eigenen Buch +0,2%.
        gewaehlt = KP.auswahl(kd(zeile("a", stufe=1), zeile("b", stufe=2)), {}, _now())
        assert [z["matchId"] for z in gewaehlt] == ["a"]

    def test_gleiche_zeile_geht_nur_einmal_raus(self):
        z = zeile("a")
        seen = {KP.schluessel(z): _now().isoformat()}
        assert KP.auswahl(kd(z), seen, _now()) == []

    def test_zu_knapp_vor_anpfiff_ist_laerm_kein_signal(self):
        # Der Median-Abstand Latch→Anpfiff liegt bei 48 Minuten; unter 10 ist die Nachricht
        # gelesen, wenn das Spiel laeuft.
        assert KP.auswahl(kd(zeile("a", vor_min=4)), {}, _now()) == []
        assert len(KP.auswahl(kd(zeile("a", vor_min=11)), {}, _now())) == 1

    def test_zu_weit_weg_wird_nicht_gepusht(self):
        assert KP.auswahl(kd(zeile("a", vor_min=13 * 60)), {}, _now()) == []

    def test_ohne_anpfiff_wird_nicht_geraten(self):
        assert KP.auswahl(kd(zeile("a", kickoff=None)), {}, _now()) == []

    def test_reihenfolge_frueheste_zuerst(self):
        g = KP.auswahl(kd(zeile("spaet", vor_min=300), zeile("frueh", vor_min=30)), {}, _now())
        assert [z["matchId"] for z in g] == ["frueh", "spaet"]


class TestNachricht:
    def test_nachricht_verspricht_nie_eine_freigabe(self):
        bil = {"gesamt": {"n": 77, "gewonnen": 46, "verloren": 31, "roi": 0.037, "roiLb": -0.130}}
        txt = KP.nachricht([zeile("a")], bil, _now())
        assert "Beobachtung, keine Freigabe" in txt
        assert "NICHT belegt" in txt
        assert "Untergrenze -13%" in txt, "der Punktschaetzer allein darf nicht dastehen"

    def test_belegte_bilanz_wird_auch_so_benannt(self):
        bil = {"gesamt": {"n": 60, "gewonnen": 40, "verloren": 20, "roi": 0.22, "roiLb": 0.05}}
        assert "✅ Belegt" in KP.nachricht([zeile("a")], bil, _now())

    def test_leeres_buch_behauptet_nichts(self):
        txt = KP.nachricht([zeile("a")], {"gesamt": {"n": 0}}, _now())
        assert "noch nichts abgerechnet" in txt

    def test_vereinsnamen_werden_html_escaped(self):
        # parse_mode=HTML: ein & im Namen zerlegt sonst die ganze Nachricht.
        txt = KP.nachricht([zeile("a", home="Brighton & Hove", name="Brighton & Hove")],
                           {"gesamt": {"n": 0}}, _now())
        assert "&amp;" in txt and "Brighton &amp; Hove</b>" in txt

    def test_die_drei_stroeme_stehen_in_der_nachricht(self):
        z = zeile("a", poly={"anteilPct": 71}, verstaerker=[{"art": "pinn", "text": "x"}])
        txt = KP.nachricht([z], {"gesamt": {"n": 0}}, _now())
        assert "Betfair 74%" in txt and "Poly 71%" in txt and "Pinnacle" in txt
        # feste Plaetze: ein fehlender Strom bleibt als „—" sichtbar, statt lautlos zu verschwinden
        leer = KP.nachricht([zeile("b")], {"gesamt": {"n": 0}}, _now())
        assert "Poly —" in leer and "Pinnacle —" in leer


class TestEigenesBuch:
    def test_gepushte_zeile_friert_den_PUSH_preis_ein(self):
        # Der Kern: haltePreis (Flaeche) und pushPreis (Nachricht) sind verschieden, und
        # gemessen wird der, zu dem man nach der Nachricht setzen konnte.
        led = KP.ledger_eintragen([], [zeile("a", odd=2.10)], _now())
        assert led[0]["pushPreis"] == 2.10
        assert led[0]["haltePreis"] == 1.75
        assert led[0]["status"] == "offen"

    def test_zweimal_eintragen_gibt_keine_doppelte_zeile(self):
        led = KP.ledger_eintragen([], [zeile("a")], _now())
        assert len(KP.ledger_eintragen(led, [zeile("a")], _now())) == 1

    def test_abrechnung_zum_pushpreis_nicht_zum_haltepreis(self):
        led = KP.ledger_eintragen([], [zeile("a", odd=3.00)], _now())
        res = [{"matchId": "a", "market": "Match Odds", "win": True, "odd": 1.5}]
        led = KP.ledger_abrechnen(led, res, _now())
        b = KP.bilanz_push(led)
        assert b["gesamt"]["n"] == 1
        assert abs(b["gesamt"]["einheiten"] - 2.00) < 1e-6, "3.00 gewonnen = +2 Einheiten"

    def test_bilanz_liefert_die_untergrenze_mit(self):
        led = []
        for i, win in enumerate([True, True, False, True, False, True]):
            led = KP.ledger_eintragen(led, [zeile(str(i), odd=2.0)], _now())
        res = [{"matchId": str(i), "market": "Match Odds", "win": w}
               for i, w in enumerate([True, True, False, True, False, True])]
        b = KP.bilanz_push(KP.ledger_abrechnen(led, res, _now()))
        assert b["gesamt"]["roi"] is not None
        assert b["gesamt"]["roiLb"] is not None
        assert b["gesamt"]["roiLb"] < b["gesamt"]["roi"], "die UG liegt immer unter dem Schaetzer"

    def test_ohne_abgerechnete_zeilen_wird_keine_bilanz_erfunden(self):
        b = KP.bilanz_push(KP.ledger_eintragen([], [zeile("a")], _now()))
        assert b["gesamt"]["n"] == 0 and b["gesamt"]["roi"] is None and b["offen"] == 1


class TestSendeFehler:
    """Ein fehlgeschlagener Send darf weder als gesendet gelten noch im Buch stehen —
    sonst misst der Channel Zeilen, die nie jemand gesehen hat."""

    def test_fehlgeschlagener_send_vermerkt_nichts(self, tmp_path, monkeypatch):
        monkeypatch.setattr(KP, "SEEN_FILE", tmp_path / "seen.json")
        monkeypatch.setattr(KP, "LEDGER_FILE", tmp_path / "led.json")
        monkeypatch.setattr(KP, "BASE", tmp_path)
        (tmp_path / "killer.json").write_text(json.dumps(kd(zeile("a"))), encoding="utf-8")
        monkeypatch.setattr(KP.TG, "send_trades_message", lambda *a, **k: False)
        monkeypatch.setattr(KP.killer, "bilanz", lambda *a, **k: {"gesamt": {"n": 0}})
        monkeypatch.delenv("DRY_RUN", raising=False)
        KP.main()
        assert json.loads((tmp_path / "seen.json").read_text()) == {}
        assert json.loads((tmp_path / "led.json").read_text()) == []

    def test_erfolgreicher_send_vermerkt_beides(self, tmp_path, monkeypatch):
        monkeypatch.setattr(KP, "SEEN_FILE", tmp_path / "seen.json")
        monkeypatch.setattr(KP, "LEDGER_FILE", tmp_path / "led.json")
        monkeypatch.setattr(KP, "BASE", tmp_path)
        (tmp_path / "killer.json").write_text(json.dumps(kd(zeile("a"))), encoding="utf-8")
        monkeypatch.setattr(KP.TG, "send_trades_message", lambda *a, **k: True)
        monkeypatch.setattr(KP.killer, "bilanz", lambda *a, **k: {"gesamt": {"n": 0}})
        monkeypatch.delenv("DRY_RUN", raising=False)
        KP.main()
        assert len(json.loads((tmp_path / "seen.json").read_text())) == 1
        assert len(json.loads((tmp_path / "led.json").read_text())) == 1


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Der Guard: ein stiller Push-Kanal tarnt sich als „gerade nichts los".
# Die Datei wird ueber _lazy untergeschoben, damit der Test nicht von der echten Datei im Repo
# abhaengt ([[feedback_tests_no_live_data_thresholds]]).
class TestGuard:
    FNAME = "killer_push_ledger.json"

    def _lauf(self, datei, jetzt=None, unlesbar=False):
        from datetime import datetime as _dt, timezone as _tz
        import wm_data_integrity as WDI
        echt_lazy, echt_failed = WDI._lazy, set(WDI._LAZY_FAILED)
        WDI._lazy = lambda name: (datei if name == self.FNAME else echt_lazy(name))
        if unlesbar:
            WDI._LAZY_FAILED.add(self.FNAME)
        else:
            WDI._LAZY_FAILED.discard(self.FNAME)
        try:
            checks = WDI.run_checks({"groups": {}}, {}, {}, {},
                                    now=jetzt or _dt(2026, 9, 5, 12, 0, tzinfo=_tz.utc))
        finally:
            WDI._lazy = echt_lazy
            WDI._LAZY_FAILED.clear()
            WDI._LAZY_FAILED.update(echt_failed)
        return next(c for c in checks if c["id"] == "killer_push_buch")

    def test_fehlende_datei_ist_unbekannt_nicht_gruen(self):
        c = self._lauf(None)
        assert c["severity"] == "warn" and not c["ok"]
        assert "❔" in " ".join(c["failures"])

    def test_unlesbare_datei_ist_ebenfalls_unbekannt(self):
        c = self._lauf(None, unlesbar=True)
        assert c["severity"] == "warn" and not c["ok"]

    def test_sauberes_buch_ist_gruen(self):
        c = self._lauf([{"k": "a|Match Odds", "pushPreis": 1.9, "status": "abgerechnet",
                         "win": True, "kickoff": "2026-09-01T12:00:00Z"}])
        assert c["ok"]

    def test_ewig_offene_zeile_schlaegt_an(self):
        # Die Abrechnung findet den Treffer nicht — das Buch waechst und misst nie.
        c = self._lauf([{"k": "a|Match Odds", "pushPreis": 1.9, "status": "offen",
                         "kickoff": "2026-09-01T12:00:00Z"}])
        assert not c["ok"] and c["severity"] == "error"

    def test_frisch_angepfiffene_zeile_ist_kein_fehler(self):
        from datetime import datetime as _dt, timezone as _tz
        c = self._lauf([{"k": "a|Match Odds", "pushPreis": 1.9, "status": "offen",
                         "kickoff": "2026-09-05T10:00:00Z"}],
                       jetzt=_dt(2026, 9, 5, 12, 0, tzinfo=_tz.utc))
        assert c["ok"]

    def test_zeile_ohne_pushpreis_schlaegt_an(self):
        c = self._lauf([{"k": "a|Match Odds", "pushPreis": None, "status": "abgerechnet",
                         "win": True, "kickoff": "2026-09-01T12:00:00Z"}])
        assert not c["ok"] and c["severity"] == "error"

    def test_leeres_buch_ist_gruen(self):
        assert self._lauf([])["ok"]
