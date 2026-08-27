"""27.08.2026 — „Die alten Ligen will ich auf keinen Fall in der Statistik haben" (Lucas)

`picks_history.json` sammelt seit dem alten breiten Card-System **20 Ligen** ein — Ungarn,
Polen, Kroatien, Schottland, Österreich, Schweiz, Türkei … — plus die komplette alte Saison
bis Mai 2026. Gezählt werden soll nur, was wir heute bespielen: Top-5 ab dem Start der neuen
Saison, plus MLS.

EINE Definition (`stats_scope.json`) für Guard und Anzeige. Zwei getippte Listen driften
auseinander, sobald eine angefasst wird.
"""
import json

import stats_scope as S

SCOPE = {"ENG": {"seasonStart": "2026-08-14"},
         "ESP": {"seasonStart": "2026-08-14"},
         "MLS": {"seasonStart": "2026-02-01"}}


class TestRegel:
    def test_top5_neue_saison_zaehlt(self):
        assert S.counts("ESP", "2026-08-15", SCOPE)

    def test_top5_alte_saison_zaehlt_nicht(self):
        """Der eigentliche Punkt: dieselbe Liga, aber vor dem Saisonstart."""
        assert not S.counts("ESP", "2026-05-17", SCOPE)

    def test_genau_am_saisonstart_zaehlt(self):
        assert S.counts("ENG", "2026-08-14", SCOPE)

    def test_kleine_liga_zaehlt_nie(self):
        for lg in ("HUN", "POL", "CRO", "SCO", "AUT", "SUI", "TUR", "NED", "BEL", "POR"):
            assert not S.counts(lg, "2026-08-22", SCOPE), lg

    def test_mls_hat_eigenen_saisonstart(self):
        """MLS läuft Februar–Oktober — ein gemeinsamer August-Schnitt wäre dort falsch."""
        assert S.counts("MLS", "2026-04-01", SCOPE)
        assert not S.counts("MLS", "2026-01-15", SCOPE)

    def test_unbekannte_liga_faellt_raus(self):
        """Fail-closed: eine neu dazukommende Liga verschmutzt die Bilanz nicht,
        bis jemand sie bewusst einträgt."""
        assert not S.counts("NEUELIGA", "2026-08-22", SCOPE)

    def test_muell_wirft_nicht(self):
        for lg, d in ((None, "2026-08-22"), ("ESP", None), ("ESP", "kaputt"), ("", ""), (5, 7)):
            assert not S.counts(lg, d, SCOPE)

    def test_leerer_umfang_zaehlt_nichts(self):
        """Kein Umfang heißt „nichts zählt" — lieber sichtbar leer als stillschweigend falsch."""
        assert not S.counts("ESP", "2026-08-22", {})


class TestSplit:
    def test_trennt_sauber(self):
        eintraege = [
            {"league": "ESP", "dateIso": "2026-08-22"},
            {"league": "ESP", "dateIso": "2026-05-17"},
            {"league": "HUN", "dateIso": "2026-08-22"},
            None, "kaputt",
        ]
        drin, raus = S.split(eintraege, scope=SCOPE)
        assert len(drin) == 1 and len(raus) == 4
        assert drin[0]["dateIso"] == "2026-08-22"


class TestDatei:
    def test_ausgelieferte_datei_deckt_die_top5_plus_mls(self):
        s = S.load()
        assert set(s) == {"ENG", "ESP", "GER", "ITA", "FRA", "MLS"}

    def test_top5_starten_alle_zum_selben_termin(self):
        s = S.load()
        starts = {k: v["seasonStart"] for k, v in s.items() if k != "MLS"}
        assert len(set(starts.values())) == 1, starts

    def test_fehlende_datei_gibt_leer_statt_absturz(self, tmp_path):
        S._CACHE.clear()
        assert S.load(tmp_path / "gibtsnicht.json") == {}

    def test_kaputte_datei_gibt_leer_statt_absturz(self, tmp_path):
        S._CACHE.clear()
        f = tmp_path / "kaputt.json"
        f.write_text("{nicht json", encoding="utf-8")
        assert S.load(f) == {}


class TestGuardNutztDenUmfang:
    def test_guard_meckert_nicht_ueber_kleine_ligen(self):
        """Ein Guard, der über Ungarn und Schottland meckert, wird nach drei Tagen ignoriert —
        und dann übersieht man den Tag, an dem er recht hat."""
        import datetime
        import wm_data_integrity as W
        hist = ([{"league": "HUN", "dateIso": "2026-08-01", "resolved": False} for _ in range(80)]
                + [{"league": "ESP", "dateIso": "2026-08-16", "resolved": False}])
        offen, _aelt = W._picks_history_open(hist, datetime.date(2026, 8, 27))
        assert offen == 1
