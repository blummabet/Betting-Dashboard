"""28.08.2026 — „Der Ober-Pick war weg, jetzt steht er wieder da" (Lucas, Barcelona–Athletic)

Der Über-2.5-Pick stand morgens auf NOBET — deshalb weder auf der Karte noch im Public-Post,
der manuell angestoßene Digest enthielt nur den AH-Pick. **14 Minuten vor Anpfiff** hob die neu
gerechnete Conviction ihn zurück auf ABWÄGEN, und er tauchte wieder auf.

Fachlich gewollt (die Aufstellung kommt T-1h und darf noch wirken). Lucas' Entscheidung:
Logik so lassen, aber sichtbar machen. Diese Tests halten fest, dass der Wechsel MITGESCHRIEBEN
wird — und dass die Logik dabei unangetastet bleibt.
"""
import generate_wm_picks as G


def _p(market, verdict, **kw):
    d = {"market": market, "verdict": verdict}
    d.update(kw)
    return d


NOW = "2026-08-27T18:46:00+00:00"


class TestMitschreiben:
    def test_der_echte_fall(self):
        alt = [_p("Über 2.5 Tore", "NOBET"), _p("AH Heim −1.25", "ABWÄGEN")]
        neu = [_p("Über 2.5 Tore", "ABWÄGEN"), _p("AH Heim −1.25", "ABWÄGEN")]
        r = G._log_verdict_flips(alt, neu, NOW)
        assert r[0]["verdictFlips"] == [{"ts": NOW, "von": "NOBET", "auf": "ABWÄGEN"}]
        assert "verdictFlips" not in r[1], "unveränderte Picks bekommen keinen Eintrag"

    def test_auch_abstufungen_werden_notiert(self):
        r = G._log_verdict_flips([_p("X", "BET")], [_p("X", "NOBET")], NOW)
        assert r[0]["verdictFlips"][0]["auf"] == "NOBET"

    def test_verlauf_waechst_und_ist_gedeckelt(self):
        picks = [_p("X", "BET")]
        for i in range(20):
            neu = [_p("X", "NOBET" if i % 2 == 0 else "BET")]
            picks = G._log_verdict_flips(picks, neu, "2026-08-27T%02d:00:00+00:00" % (i % 24))
        assert len(picks[0]["verdictFlips"]) == G.MAX_VERDICT_FLIPS

    def test_bestehender_verlauf_bleibt_erhalten(self):
        alt = [_p("X", "NOBET", verdictFlips=[{"ts": "alt", "von": "BET", "auf": "NOBET"}])]
        r = G._log_verdict_flips(alt, [_p("X", "ABWÄGEN")], NOW)
        assert len(r[0]["verdictFlips"]) == 2

    def test_neuer_pick_ohne_vorgaenger_bekommt_nichts(self):
        r = G._log_verdict_flips([_p("A", "BET")], [_p("B", "BET")], NOW)
        assert "verdictFlips" not in r[0]

    def test_zuordnung_ueber_den_markt_nicht_ueber_die_position(self):
        """Die Reihenfolge der Picks ändert sich (Sortierung nach Verdict/Safer-Alt)."""
        alt = [_p("AH Heim −1.25", "ABWÄGEN"), _p("Über 2.5 Tore", "NOBET")]
        neu = [_p("Über 2.5 Tore", "ABWÄGEN"), _p("AH Heim −1.25", "ABWÄGEN")]
        r = G._log_verdict_flips(alt, neu, NOW)
        ueber = next(p for p in r if p["market"] == "Über 2.5 Tore")
        assert ueber["verdictFlips"][0]["von"] == "NOBET"


class TestNichtsKaputtMachen:
    def test_die_logik_bleibt_unangetastet(self):
        """Lucas: „so lassen, aber sichtbar machen" — die Verdicts selbst dürfen sich durch das
        Mitschreiben nicht ändern."""
        neu = [_p("X", "ABWÄGEN"), _p("Y", "NOBET")]
        r = G._log_verdict_flips([_p("X", "NOBET"), _p("Y", "NOBET")], neu, NOW)
        assert [p["verdict"] for p in r] == ["ABWÄGEN", "NOBET"]

    def test_muell_wirft_nicht(self):
        assert G._log_verdict_flips(None, None, NOW) is None
        assert G._log_verdict_flips([], [_p("X", "BET")], NOW) == [_p("X", "BET")]
        r = G._log_verdict_flips([None, "x", {}], [_p("X", "BET"), None, "y"], NOW)
        assert r[0]["verdict"] == "BET"

    def test_picks_ohne_markt_werden_uebersprungen(self):
        r = G._log_verdict_flips([{"verdict": "BET"}], [{"verdict": "NOBET"}], NOW)
        assert "verdictFlips" not in r[0]
