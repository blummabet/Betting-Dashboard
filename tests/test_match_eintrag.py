"""Ein Signal muss sein Spiel finden, auch wenn die Datei anders schluesselt — 06.09.2026.

Zweiter Fund derselben Art wie `poly_volumen` am selben Tag: die Daten lagen da, gefragt wurde
mit dem falschen Schluessel.

`smart_money` las `smartmoney[context["matchKey"]]`. Der Liga-matchKey ist `ENG-1-45-33`
(Gruppe-Spieltag-Heim-Gast), `liga_poly_smartmoney.json` schluesselt nach `45-33`
(Heim-ID-Gast-ID). Kein einziger Treffer — und damit **$3,04 Mio. Polymarket-Holder-Geld ueber
39 Liga-Spiele, das nie in einen Pick eingeflossen ist**, davon 2,16 Mio. allein auf
Everton–Manchester United.

In der WM stimmten die Formate zufaellig ueberein, dort feuerte das Signal 35-mal. Ein Signal,
das in EINEM Datensatz laeuft, gilt schnell als „funktioniert" — deshalb prueft dieser Test
gegen die echte Liga-Datei und nicht gegen ein selbstgebautes Fixture.
"""
import json
import unittest
from pathlib import Path

from sharp_signals.base import match_eintrag

BASE = Path(__file__).resolve().parents[1]


class TestMatchEintrag(unittest.TestCase):
    def test_exakter_matchkey_gewinnt(self):
        c = {"ENG-1-45-33": "genau", "45-33": "fallback"}
        self.assertEqual(match_eintrag(c, {"matchKey": "ENG-1-45-33", "home_id": 45, "away_id": 33}),
                         "genau")

    def test_faellt_auf_heim_gast_zurueck(self):
        """Der eigentliche Fehler: matchKey trifft nicht, die IDs schon."""
        c = {"45-33": "gefunden"}
        self.assertEqual(match_eintrag(c, {"matchKey": "ENG-1-45-33", "home_id": 45, "away_id": 33}),
                         "gefunden")

    def test_auch_umgekehrte_ansetzung(self):
        c = {"33-45": "gefunden"}
        self.assertEqual(match_eintrag(c, {"matchKey": "ENG-1-45-33", "home_id": 45, "away_id": 33}),
                         "gefunden")

    def test_heim_gast_schlaegt_gast_heim(self):
        c = {"33-45": "verkehrt", "45-33": "richtig"}
        self.assertEqual(match_eintrag(c, {"home_id": 45, "away_id": 33}), "richtig")

    def test_nichts_gefunden_ist_none(self):
        self.assertIsNone(match_eintrag({"99-98": "x"}, {"home_id": 45, "away_id": 33}))

    def test_kaputte_eingaben(self):
        self.assertIsNone(match_eintrag(None, {"home_id": 1, "away_id": 2}))
        self.assertIsNone(match_eintrag({}, {"home_id": 1, "away_id": 2}))
        self.assertIsNone(match_eintrag({"1-2": "x"}, None))
        self.assertIsNone(match_eintrag("keine map", {"home_id": 1, "away_id": 2}))

    def test_ohne_ids_nur_der_matchkey(self):
        self.assertIsNone(match_eintrag({"45-33": "x"}, {"matchKey": "ENG-1-45-33"}))


class TestGegenDieEchteLigaDatei(unittest.TestCase):
    def _laden(self):
        sm = BASE / "liga_poly_smartmoney.json"
        dat = BASE / "liga-data.json"
        if not (sm.exists() and dat.exists()):
            self.skipTest("Liga-Artefakte nicht vorhanden")
        return (json.loads(sm.read_text(encoding="utf-8")).get("matches") or {},
                json.loads(dat.read_text(encoding="utf-8")))

    def test_smart_money_findet_seine_spiele(self):
        sm, dat = self._laden()
        if not sm:
            self.skipTest("keine Smart-Money-Eintraege")
        treffer = 0
        for gk, g in (dat.get("groups") or {}).items():
            for fx in g.get("fixtures") or []:
                h, a = fx.get("home"), fx.get("away")
                if h is None or a is None:
                    continue
                ctx = {"matchKey": f"{gk}-{fx.get('matchday')}-{h}-{a}",
                       "home_id": h, "away_id": a}
                if match_eintrag(sm, ctx) is not None:
                    treffer += 1
        self.assertGreater(
            treffer, 0,
            "Kein einziges Liga-Spiel findet seinen Smart-Money-Eintrag — genau der Zustand, "
            "in dem 3,04 Mio. USD Poly-Geld monatelang an den Picks vorbeiliefen.")

    def test_der_nackte_matchkey_allein_traefe_nichts(self):
        """Haelt fest, WARUM es vorher nie funktionierte. Sollte die Pipeline eines Tages nach
        matchKey schluesseln, ist das keine Regression — dann darf dieser Test weg."""
        sm, dat = self._laden()
        if not sm:
            self.skipTest("keine Smart-Money-Eintraege")
        direkt = 0
        for gk, g in (dat.get("groups") or {}).items():
            for fx in g.get("fixtures") or []:
                h, a = fx.get("home"), fx.get("away")
                if h is None or a is None:
                    continue
                if f"{gk}-{fx.get('matchday')}-{h}-{a}" in sm:
                    direkt += 1
        self.assertEqual(direkt, 0,
                         "Die Datei schluesselt jetzt nach matchKey — Befund neu pruefen.")


if __name__ == "__main__":
    unittest.main()
