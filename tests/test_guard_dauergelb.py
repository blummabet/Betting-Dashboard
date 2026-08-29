"""29.08.2026 (Lucas, Status-Tab) — zwei Guards standen dauerhaft auf Gelb.

    🟡 Pinnacle-1X2 vollständig + plausibel   11 Fehler (Liga) · 13 (MLS)
    🟡 Public-Konsens (Soft-Books) vorhanden  14 Fehler (Liga) ·  7 (MLS)

Nachgemessen: ausnahmslos Spiele 5,5 bis 7,7 Tage in der Zukunft, zu denen Polymarket laengst
listet und Pinnacle noch nicht. Der vorhandene 7-Tage-Deckel konnte das nicht abfangen, denn die
Zonen ueberlappen — bepreiste Anpfiffe reichen bis 9,5 Tage, unbepreiste beginnen bei 5,5. Ein
reiner Tages-Schwellenwert trennt sie also gar nicht.

Das richtige Kriterium ist nicht die Entfernung, sondern ob Pinnacle ueberhaupt schon eroeffnet
hat. Und Dauer-Gelb ist nicht harmlos: es erzieht dazu, die Statusseite zu ueberblaettern —
genau das hat am 28.08. einen halben Tag gekostet, als die Feed-Frische zu Recht Alarm schlug.
"""
import os
import sys
import pytest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wm_data_integrity as W

JETZT = datetime(2026, 8, 29, 6, 0, tzinfo=timezone.utc)


def ctx(odds, tage_bis_anpfiff):
    ko = (JETZT + timedelta(days=tage_bis_anpfiff)).isoformat()
    wm = {"groups": {"X": {"teams": [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}],
                           "fixtures": [{"home": "1", "away": "2", "kickoff": ko}]}},
          "odds": {"1-2": odds}}
    return W.IntegrityCtx(wm=wm, poly={}, schedule=[], venues={}, now=JETZT)


NUR_POLY = {"poly_hw": 0.4, "poly_dr": 0.3, "poly_aw": 0.3, "poly_slug": "x"}
NUR_BETFAIR = {"bf_hw": 2.1, "bf_dr": 3.4, "bf_aw": 3.2, "ahLadder": {}}
HALB = {"aw": 2.2, "dr": 3.4, "bookmaker": "pinnacle"}          # hw fehlt
VOLL = {"hw": 2.1, "dr": 3.4, "aw": 3.2, "bookmaker": "pinnacle", "public_hw": 2.0}


class TestNieEroeffnetErkennen:
    def test_nur_poly_gilt_als_nicht_eroeffnet(self):
        assert W._pinnacle_nie_eroeffnet(NUR_POLY) is True

    def test_betfair_und_ah_zaehlen_nicht_als_pinnacle(self):
        """Betfair und die AH-Leiter listen frueher — das ist keine Pinnacle-Eroeffnung."""
        assert W._pinnacle_nie_eroeffnet(NUR_BETFAIR) is True

    def test_halber_eintrag_gilt_als_eroeffnet(self):
        """aw + dr da, hw fehlt: DAS ist ein echter Fehler und muss sichtbar bleiben."""
        assert W._pinnacle_nie_eroeffnet(HALB) is False

    def test_vollstaendig_ist_eroeffnet(self):
        assert W._pinnacle_nie_eroeffnet(VOLL) is False

    def test_muell_gilt_als_nicht_eroeffnet(self):
        assert W._pinnacle_nie_eroeffnet(None) is True
        assert W._pinnacle_nie_eroeffnet("kaputt") is True


class TestGuardsSchweigenNurWoAngebracht:
    def test_fernes_unbepreistes_spiel_ist_kein_fehler(self):
        """Der Fall aus dem Status-Tab: 7 Tage weg, nur Poly-Preise."""
        c = W.check_odds_sane(ctx(NUR_POLY, 7))
        assert c["ok"] is True

    def test_auch_der_public_guard_schweigt_dazu(self):
        assert W.check_public_consensus(ctx(NUR_POLY, 7))["ok"] is True

    def test_nahes_spiel_ohne_pinnacle_bleibt_ein_fehler(self):
        """Ein Spiel uebermorgen ohne Pinnacle-Linie ist nicht handelbar — das gehoert gemeldet."""
        assert W.check_odds_sane(ctx(NUR_POLY, 1))["ok"] is False

    def test_grenze_liegt_bei_drei_tagen(self):
        assert W.check_odds_sane(ctx(NUR_POLY, 2.9))["ok"] is False
        assert W.check_odds_sane(ctx(NUR_POLY, 3.1))["ok"] is True

    def test_halber_eintrag_wird_auch_weit_draussen_gemeldet(self):
        """Real Betis–Real Madrid hatte aw und dr, aber kein hw — kein Schweigen dafuer."""
        c = W.check_odds_sane(ctx(HALB, 7))
        assert c["ok"] is False
        assert "unvollständig" in c["failures"][0]

    def test_vollstaendige_quoten_bleiben_sauber(self):
        assert W.check_odds_sane(ctx(VOLL, 1))["ok"] is True
        assert W.check_public_consensus(ctx(VOLL, 1))["ok"] is True


class TestEchteDatenSindRuhig:
    """Gegenprobe auf dem echten Datensatz — genau daran hing die Beschwerde."""

    @pytest.mark.parametrize("profil,datensatz", [("liga_default", "liga"), ("mls_default", "mls")])
    def test_kein_dauergelb_mehr_beim_1x2_guard(self, profil, datensatz, monkeypatch):
        import json
        monkeypatch.setenv("COCOBET_PROFILE", profil)
        monkeypatch.setenv("COCOBET_DATASET", datensatz)
        for m in list(sys.modules):
            if m.startswith(("cocobet_dataset", "cocobet_config")):
                del sys.modules[m]
        import cocobet_dataset as D
        pfad = str(D.data_file())
        if not os.path.exists(pfad):
            pytest.skip(f"{pfad} fehlt")
        with open(pfad, encoding="utf-8") as f:
            wm = json.load(f)
        c = W.check_odds_sane(W.IntegrityCtx(wm=wm, poly={}, schedule=[], venues={}))
        assert c["ok"], f"{datensatz}: noch {c['nFail']} Fehler — {c['failures'][:3]}"


# 29.08.2026 (Dauergelb, Teil 2): zwischen Anpfiff und Abpfiff raeumt der Buchmacher seine
# Vor-Spiel-Quoten ab. `_finished_keys` greift da noch nicht (result.status kommt erst nach
# Abpfiff), also flaggte der 1X2-Guard jedes laufende Spiel als „unvollstaendig". Gemessen an
# Liverpool-Nottm Forest: Anpfiff 11:30, Pruefung 14:30, hw/dr/aw=None — nichts kaputt, Spiel laeuft.
class TestLaufendeSpieleSindKeinFehler:
    def _ctx(self, ko_iso, jetzt):
        wm = {"groups": {"ENG": {"fixtures": [
            {"home": "40", "away": "65", "kickoff": ko_iso, "date": ko_iso[:10], "matchday": 2}]}}}
        ctx = W.IntegrityCtx(wm=wm, poly={}, schedule=[], venues={})
        ctx.odds = {"40-65": {"poly_dr": 1.0, "poly_hw": 0.0, "poly_aw": 0.0005}}
        ctx.now = jetzt
        return ctx

    def test_angepfiffenes_spiel_ohne_1x2_ist_kein_fehler(self):
        from datetime import datetime, timezone
        jetzt = datetime(2026, 8, 29, 14, 30, tzinfo=timezone.utc)
        c = W.check_odds_sane(self._ctx("2026-08-29T11:30:00Z", jetzt))
        assert c["ok"], c.get("failures")

    def test_kommendes_spiel_ohne_1x2_wird_weiter_geflaggt(self):
        # Der Guard soll nicht stumm werden — ein Spiel VOR Anpfiff ohne Quoten ist echt kaputt.
        from datetime import datetime, timezone
        jetzt = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
        c = W.check_odds_sane(self._ctx("2026-08-29T11:30:00Z", jetzt))
        assert not c["ok"] and "1X2" in c["failures"][0]
