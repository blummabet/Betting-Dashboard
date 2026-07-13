"""13.07.2026 — Platzhalter-Quoten dürfen NIE einen Move/Steam/Alert auslösen.

Vorgeschichte (Lucas: „schau dir den Sharp Radar nochmal an"): Die MLS-History eröffnete mit
hw=1.04 / dr=1.01 / aw=1.04 → Overround 291 %. Das ist kein Markt, das ist ein API-Platzhalter.
Daraus wurden im Radar Geister-Mover („PSG 1.02 → 1.40") und in detect_wm_sharp_moves 80,8pp
„🔥 STEAM" — inklusive bereits versendeter Telegram-Alerts.

Der bestehende Guard check_opening_plausible meldete GRÜN, weil er `odds_open` prüfte (das war
korrekt geheilt) — die Verbraucher lesen aber die HISTORY. Ein Guard, der die falsche Datei
prüft, beruhigt nur.
"""
import odds_plausibility as OP


class TestPlausible1x2:
    def test_echter_markt_wird_akzeptiert(self):
        # typischer Pinnacle-Markt, Overround ~1.03
        assert OP.plausible_1x2(1.83, 3.60, 3.75) is True
        assert OP.plausible_1x2(2.10, 3.40, 3.50) is True
        # krasser, aber ECHTER Favoritenmarkt (Bayern gegen Aufsteiger)
        assert OP.plausible_1x2(1.14, 7.78, 15.36) is True

    def test_der_echte_mls_platzhalter_fliegt_raus(self):
        # exakt die Werte aus mls-odds-history.json (Overround 2.91)
        assert OP.plausible_1x2(1.04, 1.01, 1.04) is False
        # Chicago–Vancouver, 09.07.
        assert OP.plausible_1x2(1.17, 1.01, 1.17) is False

    def test_unmoegliches_remis(self):
        assert OP.plausible_1x2(2.00, 1.20, 3.00) is False   # Remis 1.20 gibt es nicht

    def test_arbitrage_geschenk_ist_ein_fehler(self):
        # Overround < 1.0 wäre geschenktes Geld → in Wahrheit ein Datenfehler
        assert OP.plausible_1x2(4.0, 4.0, 4.0) is False

    def test_unvollstaendig_ist_nicht_plausibel(self):
        assert OP.plausible_1x2(1.90, None, 3.0) is False
        assert OP.plausible_1x2(None, None, None) is False


class TestSnapFilter:
    def test_teilsnapshot_bleibt_erhalten(self):
        # Nur hw gesetzt → Marge nicht prüfbar → NICHT verwerfen (Fehlurteil wäre schlimmer)
        assert OP.snap_ok({"hw": 1.90}) is True
        assert OP.snap_ok({"o25": 1.95, "u25": 1.90}) is True

    def test_voller_platzhalter_snap_fliegt(self):
        assert OP.snap_ok({"hw": 1.04, "dr": 1.01, "aw": 1.04}) is False

    def test_clean_snaps_behaelt_reihenfolge(self):
        snaps = [
            {"hw": 1.04, "dr": 1.01, "aw": 1.04, "ts": "T0"},   # Platzhalter
            {"hw": 1.80, "dr": 3.60, "aw": 4.20, "ts": "T1"},   # echt
            {"hw": 1.70, "dr": 3.70, "aw": 4.60, "ts": "T2"},   # echt
        ]
        out = OP.clean_snaps(snaps)
        assert [s["ts"] for s in out] == ["T1", "T2"]
        # snaps[0] heißt danach immer noch „Opening" — nur eben das erste ECHTE
        assert out[0]["hw"] == 1.80

    def test_first_plausible(self):
        snaps = [{"hw": 1.04, "dr": 1.01, "aw": 1.04}, {"hw": 1.80, "dr": 3.6, "aw": 4.2}]
        assert OP.first_plausible(snaps)["hw"] == 1.80
        assert OP.first_plausible([{"hw": 1.04, "dr": 1.01, "aw": 1.04}]) is None
        assert OP.first_plausible([]) is None


class TestGeisterMoveVerschwindet:
    def test_80pp_steam_entsteht_nicht_mehr(self):
        """Der konkrete Fall aus Lucas' Log: 9569-1608 snap=80.8pp „🔥 STEAM"."""
        def pp(old, new):
            return round(100 / new - 100 / old, 1) if old and new else 0.0

        platzhalter = {"hw": 1.04, "dr": 1.01, "aw": 1.04, "ts": "T0"}
        echt_1      = {"hw": 1.45, "dr": 4.72, "aw": 6.50, "ts": "T1"}
        echt_2      = {"hw": 1.45, "dr": 4.70, "aw": 6.60, "ts": "T2"}

        # VORHER: Platzhalter als Vergleichsbasis → absurder Move
        geist = abs(pp(platzhalter["hw"], echt_1["hw"]))
        assert geist > 25, "Beweis: der Platzhalter erzeugt einen zweistelligen Geister-Move"

        # NACHHER: gefiltert → nur echte Snaps vergleichen → ruhiger Markt
        clean = OP.clean_snaps([platzhalter, echt_1, echt_2])
        assert len(clean) == 2
        echter_move = abs(pp(clean[0]["hw"], clean[-1]["hw"]))
        assert echter_move < 5.0, "nach dem Filter bleibt nur die echte (winzige) Bewegung"


class TestSchwellenSindEineQuelle:
    def test_steam_engine_und_fetch_liga_teilen_die_regel(self):
        """Vorher lag die Regel dreifach im Repo — mit UNTERSCHIEDLICHEN Grenzen
        (Overround 1.25 in fetch_liga_odds vs 1.30 in steam_engine). So laufen Schwellen
        still auseinander. Jetzt: identische Funktion."""
        import steam_engine
        import fetch_liga_odds
        assert steam_engine._plausible_1x2 is OP.plausible_1x2
        assert fetch_liga_odds._plausible_1x2 is OP.plausible_1x2
