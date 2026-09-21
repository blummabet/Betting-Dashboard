"""🔴 21.09.2026 (Lucas: „das ist wichtig und das haben wir damals schon mal gefixt").

Die Übersicht meldete: „liga_poly_balance.json: Positionswert $0.00 stammt aus einem Lauf vor
16 h — die Positions-API antwortet seither nicht."

Nachgemessen, bevor etwas geändert wurde:
  · Die 0,00 STIMMT. Alle fünf offenen Zeilen in `liga_auto_bets_placed.json` stehen auf
    `sold` oder `closed_manual` — die Wallet hält wirklich nichts.
  · Die 16 Stunden stimmen auch, aber nicht aus dem genannten Grund: die Datei wurde gar nicht
    geschrieben. `manage-liga-poly` liefert von 25 geplanten Läufen rund 5. Die API hatte damit
    nichts zu tun.

Zwei Funde, beide dieselbe Krankheit an verschiedenen Türen:

1. `fetch_positions_value` machte aus einer unerwarteten Antwort eine LEERE LISTE:
   `raw.get("positions") or raw.get("data") or []`. Ein `{"error": "rate limited"}` wurde damit
   zu 0,00 $ — mit frischem `positionsStand`, also von einer echten Messung nicht zu
   unterscheiden. Der Fix vom 18.09. hat den EINGEFRORENEN Wert sichtbar gemacht; die leere
   Antwort kam dabei nicht ins Licht.
   Fehlerklasse: fehlende Information rendert als harmloser Default.

2. Der Wächter nannte pauschal die API als Ursache, obwohl die Unterscheidung in der Datei
   steht: `positionsStand` ≈ `updatedAt` heißt „der Produzent lief nicht", `positionsStand`
   älter als `updatedAt` heißt „er lief, die API antwortete nicht".
   Fehlerklasse: ein Befund, der seine eigene Unterscheidung nicht trifft, obwohl die Zahl
   daneben steht. Zum zweiten Mal an diesem Tag — der Anker-Wächter hatte sie auch.

Warum das Geld kostet: der Positionswert geht in `total`, das Wallet-Equity im Header. Eine
Wallet, die ihre offenen Positionen mit 0 bewertet, sieht ärmer aus als sie ist — und eine, die
einen alten Wert mitschleppt, reicher.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import fetch_wm_poly_balance as B
import uebersicht_integrity as U

JETZT = datetime.now(timezone.utc)


class TestEineUndeutbareAntwortIstKeinNullbestand(unittest.TestCase):
    def test_eine_leere_liste_ist_eine_auskunft(self):
        """„Die Wallet haelt nichts" ist eine Messung — die darf 0.0 bleiben."""
        self.assertEqual(B._positions_rows([]), [])

    def test_ein_fehler_dict_ist_keine(self):
        self.assertIsNone(B._positions_rows({"error": "rate limited"}))

    def test_ein_dict_ohne_bekannten_umschlag_auch_nicht(self):
        self.assertIsNone(B._positions_rows({"irgendwas": [1, 2]}))

    def test_ein_string_bringt_den_produzenten_nicht_um(self):
        """Vorher waere `raw.get(...)` auf einem String mit AttributeError geflogen —
        und zwar ausserhalb des try, also mitten im Balance-Lauf."""
        self.assertIsNone(B._positions_rows("service unavailable"))
        self.assertIsNone(B._positions_rows(None))
        self.assertIsNone(B._positions_rows(42))

    def test_die_bekannten_umschlaege_gehen_weiter_durch(self):
        self.assertEqual(B._positions_rows({"positions": [{"currentValue": 3}]}),
                         [{"currentValue": 3}])
        self.assertEqual(B._positions_rows({"data": []}), [])


class TestEineTeilSummeIstKeineSumme(unittest.TestCase):
    def test_currentvalue_wird_genommen(self):
        self.assertEqual(B._positions_wert({"currentValue": "12.5"}), 12.5)

    def test_sonst_size_mal_preis(self):
        self.assertEqual(B._positions_wert({"size": 20, "curPrice": 0.5}), 10.0)

    def test_eine_zeile_ohne_beides_ist_nicht_null(self):
        """Vorher trug so eine Zeile 0 zur Summe bei — die Summe war dann zu klein und sah
        trotzdem aus wie gemessen."""
        self.assertIsNone(B._positions_wert({"foo": 1}))

    def test_unbrauchbare_zahlen_ebenso(self):
        self.assertIsNone(B._positions_wert({"currentValue": "viel"}))
        self.assertIsNone(B._positions_wert({"size": "x", "curPrice": 0.5}))


class TestDieSummeWirdNurGanzGeliefert(unittest.TestCase):
    def test_saubere_zeilen_ergeben_die_summe(self):
        self.assertEqual(B.positionen_summe([{"currentValue": 12.5}, {"size": 20, "curPrice": 0.5}]),
                         (22.5, 0))

    def test_eine_unklare_zeile_faellt_auf(self):
        """Der Kern: 1 + 0 waere 1,00 $ und saehe aus wie gemessen."""
        summe, unklar = B.positionen_summe([{"currentValue": 1}, {"foo": 2}])
        self.assertEqual(unklar, 1)

    def test_keine_zeilen_sind_null_und_klar(self):
        self.assertEqual(B.positionen_summe([]), (0.0, 0))

    def test_eine_zeile_die_kein_dict_ist_zaehlt_als_unklar(self):
        self.assertEqual(B.positionen_summe(["kaputt"])[1], 1)


class TestDieSummeTraegtIhrenNenner(unittest.TestCase):
    """🔴 21.09.2026 (Lucas: „meine verknuepfte wallet haelt rund um die 200 dollar … finde den
    fehler"). Ich konnte ihm nicht sagen, ob die 0,00 „null Zeilen zurueckbekommen" heisst oder
    „Zeilen bekommen, die zusammen null wert sind" — weil im Artefakt nur die SUMME stand.
    Fehlerklasse: eine Zahl ohne den Nenner, aus dem sie entsteht.
    """

    def _save(self, tmp, positions):
        from unittest import mock
        import json
        with mock.patch.object(B, "OUT_FILE", tmp / "wm_poly_balance.json"):
            return B._save(200.0, 0.0, "0xabc", positions=positions)

    def test_null_zeilen_und_null_summe_sind_unterscheidbar_von_nicht_gemessen(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        B.LETZTE_MESSUNG["zeilen"] = 0
        out = self._save(tmp, 0.0)
        self.assertEqual(out["positions"], 0.0)
        self.assertEqual(out["positionsZeilen"], 0, "0 Zeilen heisst: die Wallet haelt nichts")

    def test_zeilen_mit_wert_null_sehen_anders_aus(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        B.LETZTE_MESSUNG["zeilen"] = 3
        out = self._save(tmp, 0.0)
        self.assertEqual(out["positionsZeilen"], 3,
                         "3 Zeilen mit Summe 0 ist etwas anderes als eine leere Wallet")

    def test_ohne_messung_steht_dort_nichts(self):
        """Wird der alte Wert mitgeschleppt (positions=None), ist auch der Nenner unbekannt —
        und nicht 0."""
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        B.LETZTE_MESSUNG["zeilen"] = 7
        out = self._save(tmp, None)
        self.assertIsNone(out["positionsZeilen"])
        self.assertIsNone(out["positionsStand"])


class TestDerWaechterNenntDenGrundDerZutrifft(unittest.TestCase):
    def _ctx(self, updated_vor_h, stand_vor_h, positions=0.0):
        d = {"positions": positions,
             "updatedAt": (JETZT - timedelta(hours=updated_vor_h)).isoformat(),
             "positionsStand": (JETZT - timedelta(hours=stand_vor_h)).isoformat()}
        return {"balanceLiga": d}

    def test_der_echte_fall_der_produzent_lief_nicht(self):
        """15,5 h alte Datei, Positionsmessung genauso alt — `manage-liga-poly` lief nicht."""
        t = " ".join(U.check_positionswert_ist_frisch(self._ctx(15.5, 15.5))["failures"])
        self.assertIn("der Produzent laeuft nicht", t)
        self.assertNotIn("Positions-API antwortet nicht", t)

    def test_der_andere_fall_die_api_antwortet_nicht(self):
        """Frisch geschriebene Datei, alter Positionswert — genau der Vorfall vom 18.09."""
        t = " ".join(U.check_positionswert_ist_frisch(self._ctx(0.2, 20.0, positions=10.12))["failures"])
        self.assertIn("Positions-API antwortet nicht", t)
        self.assertIn("mitgeschleppt", t)
        self.assertNotIn("der Produzent laeuft nicht", t)

    def test_ohne_updatedat_wird_keine_ursache_erfunden(self):
        d = {"positions": 0.0, "positionsStand": (JETZT - timedelta(hours=20)).isoformat()}
        t = " ".join(U.check_positionswert_ist_frisch({"balanceLiga": d})["failures"])
        self.assertIn("Grund nicht bestimmbar", t)

    def test_frisch_ist_still(self):
        self.assertEqual(U.check_positionswert_ist_frisch(self._ctx(0.2, 0.2))["failures"], [])

    def test_ohne_positionsstand_meldet_er_weiter(self):
        """Der Fund vom 18.09. bleibt: ohne Stempel sagt die Datei nicht, wann gemessen wurde."""
        d = {"positions": 5.0, "updatedAt": JETZT.isoformat()}
        t = " ".join(U.check_positionswert_ist_frisch({"balanceLiga": d})["failures"])
        self.assertIn("kein `positionsStand`", t)


if __name__ == "__main__":
    unittest.main()
