"""18.07.2026 — CLV als zweiter Lernstrom im Bayesian-Loop.

## Warum es das gibt

Ein aufgelöster Pick liefert genau EINE won/lost-Beobachtung je Signal. Bei ~100 Picks auf
30 Signale hungert der Loop — deshalb stehen die Gewichte praktisch still. `clvPP` ist stetig
statt binär, hat viel kleinere Varianz und steht schon beim Anpfiff fest.

## Die Grenze, die dabei NICHT verwischen darf

Lucas' Einwand gegen „CLV ist der Maßstab": das gilt für plumpes Odd-Drop-Folgen. Signale, die
bewusst GEGEN den Move schießen (Form, Ausfälle, Tabellendruck), an CLV zu messen würde exakt
das bestrafen, wofür sie da sind — sie behaupten „diese Mannschaft ist besser als der Markt
denkt", nicht „der Markt läuft weiter in diese Richtung".

Deshalb lernt NUR die sharp_money-Familie auf CLV. Diese Trennung ist der eigentliche Inhalt
dieser Datei; ginge sie verloren, wäre der Loop schneller und gleichzeitig falsch.
"""
import pytest

import update_signal_weights as U


# 🔴 11.09.2026 — der Loop las `clvPP`, und `clvPP` verglich AEPFEL MIT BIRNEN: Pinnacles
# entvigte Schlussquote gegen unsere rohe, vigbehaftete Einstiegsquote. Der Overround (gemessen:
# public 6,60 %, Pinnacle 4,43 %) steckte einseitig auf der Einstiegsseite → jeder CLV war um
# ~2-3 pp zu negativ. Der Loop lernte damit systematisch das Falsche.
#
# Seither gilt: der Lernstrom nimmt NUR `clvFairPP` mit `clvBasis == "fair"` — beide Seiten
# entvigt. Ein Pick, dessen Einstiegsmarkt sich nicht zuordnen laesst, liefert lieber gar keine
# Beobachtung als eine schiefe. Deshalb tragen die Fixtures hier beides; `_clv` baut es.
def _clv(pp, basis="fair"):
    return {"clvFairPP": pp, "clvBasis": basis}


class TestCLVScore:
    def test_stillstand_ist_keine_beobachtung(self):
        """0.5 zurückzugeben wäre bequem — und falsch: eine erfundene neutrale Beobachtung
        zieht echte Signale Richtung 1.0 und täuscht Datenmenge vor."""
        assert U._clv_outcome_score(_clv(0)) is None
        assert U._clv_outcome_score(_clv(0.3)) is None, "Rauschen innerhalb der Deadband"

    def test_fehlender_clv_ist_keine_beobachtung(self):
        """BTTS/DC/AH haben (noch) kein Closing → clvPP None. Darf nicht als neutral zählen."""
        assert U._clv_outcome_score({}) is None
        assert U._clv_outcome_score(_clv(None)) is None
        assert U._clv_outcome_score(_clv("kaputt")) is None

    def test_richtung_stimmt(self):
        assert U._clv_outcome_score(_clv(5)) == pytest.approx(1.0)
        assert U._clv_outcome_score(_clv(-5)) == pytest.approx(0.0)
        assert U._clv_outcome_score(_clv(2.5)) == pytest.approx(0.75)

    def test_ausreisser_werden_geklippt(self):
        """Ein 40pp-CLV (meist Platzhalter-Quoten) darf ein Signal nicht im Alleingang drehen."""
        assert U._clv_outcome_score(_clv(40)) == pytest.approx(1.0)
        assert U._clv_outcome_score(_clv(-40)) == pytest.approx(0.0)


class TestNurDieFaireBasisLernt:
    """Die Umstellung vom 11.09. — und der Grund, warum sie ein eigener Test sein muss.

    Ein alter Pick traegt `clvPP` (vigbehaftete Einstiegsseite) und kein `clvBasis`. Wuerde der
    Loop darauf zurueckfallen, saehe man nichts: die Zahlen sind plausibel, nur um den halben
    Overround verschoben. Genau solche Fehler wandern still durch — deshalb hier explizit.
    """

    def test_alter_vigbehafteter_clv_zaehlt_nicht(self):
        assert U._clv_outcome_score({"clvPP": 5}) is None, \
            "der alte, vigbehaftete Wert darf keine Beobachtung mehr erzeugen"

    def test_faire_zahl_ohne_ausgewiesene_basis_zaehlt_nicht(self):
        assert U._clv_outcome_score({"clvFairPP": 5}) is None, \
            "ohne clvBasis ist nicht belegt, dass beide Seiten entvigt sind"

    def test_fremde_basis_zaehlt_nicht(self):
        assert U._clv_outcome_score(_clv(5, basis="roh")) is None

    def test_basis_fair_ohne_faire_zahl_faellt_nicht_auf_die_alte_zurueck(self):
        """Der zweite, unabhaengige Riegel: nicht nur die Basis muss stimmen, es muss auch das
        FAIRE Feld gelesen werden. Ein `.get("clvFairPP", pick.get("clvPP"))` sieht harmlos aus
        und holt die vigbehaftete Zahl durch die Hintertuer wieder herein."""
        assert U._clv_outcome_score({"clvBasis": "fair", "clvPP": 5}) is None

    def test_mit_ausgewiesener_fairer_basis_zaehlt_sie(self):
        assert U._clv_outcome_score(_clv(5)) == pytest.approx(1.0)


class TestNurSharpMoneyLerntAufCLV:
    @pytest.mark.parametrize("sig", ["lead_lag_bias", "steam_lag", "polymarket_sharp",
                                     "reverse_line_move", "opener_move", "multi_book_steam"])
    def test_move_signale_ja(self, sig):
        assert U._learns_on_clv(sig), f"{sig} behauptet 'der Move läuft weiter' — CLV testet das direkt"

    @pytest.mark.parametrize("sig", ["form_trend", "xg_strength", "injury_signal", "lineup_signal",
                                     "league_pressure", "h2h_pattern", "travel_burden",
                                     "chance_creation", "fixture_congestion"])
    def test_orthogonale_signale_nein(self, sig):
        assert not U._learns_on_clv(sig), \
            f"{sig} schießt bewusst gegen den Move — an CLV gemessen würde es dafür bestraft"

    def test_unbekanntes_signal_lernt_nicht_auf_clv(self):
        """Sicherer Default: ein neues Signal ohne Gruppen-Eintrag rutscht nicht versehentlich rein."""
        assert not U._learns_on_clv("irgendein_neues_signal")


class TestLoopEndeZuEnde:
    """Gegen echte Gewichts-Berechnung, mit gemocktem Ledger."""

    def _run(self, picks, monkeypatch, tmp_path):
        monkeypatch.setattr(U, "_load_results", lambda: picks)
        monkeypatch.setattr(U, "_load_weights", lambda: {})
        monkeypatch.setattr(U, "_load_priors", lambda: {})
        gespeichert = {}
        monkeypatch.setattr(U, "_save_weights", lambda w: gespeichert.update(w))
        U.update_weights()
        return gespeichert

    def _pick(self, sig, score=1.0, result="WIN", clv=None, quote=2.00):
        # 06.09.2026: der Ergebnis-Strom misst gegen den PREIS. Ohne Quote gibt es keine
        # Ergebnis-Beobachtung mehr — die Fixture braucht eine. 2.00 haelt die Mischung
        # 6:4 sichtbar ueber dem Nullpunkt, ohne an den Deckel zu stossen.
        p = {"result": result, "odds": quote, "signals": [{"name": sig, "score": score}]}
        if clv is not None:
            p.update(_clv(clv))
        return p

    def _gemischt(self, sig, clv=None):
        """6 Treffer / 4 Fehlschläge — realistische Trefferquote. Bei 10/10 sitzt das Gewicht
        am Deckel (1.7) und jede Änderung wäre unsichtbar."""
        return ([self._pick(sig, result="WIN", clv=clv)] * 6
                + [self._pick(sig, result="LOSS", clv=clv)] * 4)

    def test_clv_erzeugt_zusaetzliche_beobachtungen(self, monkeypatch, tmp_path):
        ohne = self._run(self._gemischt("lead_lag_bias"), monkeypatch, tmp_path)
        mit  = self._run(self._gemischt("lead_lag_bias", clv=4.0), monkeypatch, tmp_path)
        assert ohne["lead_lag_bias"]["n_clv"] == 0
        assert mit["lead_lag_bias"]["n_clv"] > 0, "CLV-Strom kommt nicht an"
        assert mit["lead_lag_bias"]["weight"] > ohne["lead_lag_bias"]["weight"], \
            "zusätzliche bestätigende Evidenz muss das Vertrauen erhöhen"

    def test_orthogonales_signal_bleibt_unberuehrt(self, monkeypatch, tmp_path):
        """Der Kern der Trennung: derselbe CLV darf form_trend NICHT anfassen."""
        ohne = self._run(self._gemischt("form_trend"), monkeypatch, tmp_path)
        mit  = self._run(self._gemischt("form_trend", clv=4.0), monkeypatch, tmp_path)
        assert mit["form_trend"]["n_clv"] == 0
        assert mit["form_trend"]["weight"] == ohne["form_trend"]["weight"], \
            "form_trend wurde an CLV gemessen — genau das soll nicht passieren"

    def test_negativer_clv_daempft(self, monkeypatch, tmp_path):
        """Signal lag ergebnisseitig richtig, aber die Linie lief dagegen → weniger Vertrauen
        als bei Zustimmung des Marktes."""
        gut      = self._run(self._gemischt("steam_lag", clv=4.0), monkeypatch, tmp_path)
        schlecht = self._run(self._gemischt("steam_lag", clv=-4.0), monkeypatch, tmp_path)
        assert schlecht["steam_lag"]["weight"] < gut["steam_lag"]["weight"]

    def test_pick_ohne_ergebnis_lernt_trotzdem_aus_clv(self, monkeypatch, tmp_path):
        """Der halbe Punkt der Übung: CLV steht beim Anpfiff fest, das Ergebnis erst danach.
        Ein noch nicht aufgelöster Pick mit Closing muss schon Evidenz liefern."""
        w = self._run([{"result": "PENDING", **_clv(4.0),
                        "signals": [{"name": "opener_move", "score": 1.0}]}] * 10,
                      monkeypatch, tmp_path)
        assert "opener_move" in w, "Pick ohne Ergebnis liefert gar keine Beobachtung"
        assert w["opener_move"]["n_clv"] > 0
        assert w["opener_move"]["n_observations"] == 0, "PENDING darf nicht als Ergebnis zählen"

    def test_clv_zaehlt_weniger_als_ein_echtes_ergebnis(self, monkeypatch, tmp_path):
        """CLV ist präziser, aber indirekt — es misst Markt-Zustimmung, nicht Realität."""
        w = self._run(self._gemischt("steam_lag", clv=4.0), monkeypatch, tmp_path)
        assert w["steam_lag"]["n_clv"] < w["steam_lag"]["n_observations"], \
            "eine CLV-Beobachtung wiegt so schwer wie ein Ergebnis — CLV_OBS_WEIGHT greift nicht"

    def test_gegensignal_wird_richtig_herum_bewertet(self, monkeypatch, tmp_path):
        """score < 0 heißt 'schlechter Pick'. Läuft die Linie dann WEG, lag das Signal richtig."""
        w = self._run([self._pick("steam_lag", score=-1.0, result="LOSS", clv=-4.0)] * 10,
                      monkeypatch, tmp_path)
        assert w["steam_lag"]["weight"] > 1.0, "Warn-Signal wurde für korrekte Warnung bestraft"


def test_clv_wird_in_den_ledger_geschrieben():
    """Der Updater liest NUR den Ledger. Fehlt clvPP dort, ist der ganze Strom tot —
    und zwar still, weil alles andere weiterläuft."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "build_signal_ledger.py").read_text("utf-8")
    assert '"clvPP":' in src, "build_signal_ledger reicht clvPP nicht durch → CLV-Lernen ist tot"
