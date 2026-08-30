"""tests/test_push_gegensignal.py — 30.08.2026

Lucas wollte die ABWÄGEN im Public-Push reduzieren und vermutete den MARKT als Ursache
(„1X2 ist schwächer, den nicht schicken"). Gemessen an 220 abgerechneten ABWÄGEN trennt der
Markt nicht — pro Markt liegen 17–46 Zeilen vor, die Fehlerspanne ist ±25–35pp ROI, und 1X2
kippt je nach Ausschnitt von +8,8% auf −1,5%. Was trennt, ist das GEGENSIGNAL:

    ohne Gegensignal   n=47   78,7%   ROI +40,0%   Untergrenze +19,3%
    mit Gegensignal    n=143  49,7%   ROI −11,7%   Untergrenze −24,9%

Diese Tests halten drei Dinge fest, an denen so ein Filter typischerweise scheitert:
  1. Er darf BET nicht anfassen.
  2. Er muss fail-closed sein — keine Signal-Angabe ist keine Erlaubnis.
  3. Es darf nur EINE Definition geben. Vorher waren es zwei (ANNOUNCE_VERDICTS hier,
     _is_posted in telegram_wm), und sie waren bereits auseinandergelaufen.
"""
import importlib
import os
import unittest
from datetime import datetime, timedelta, timezone


def _pick(**kw):
    d = {"verdict": "ABWÄGEN", "market": "Heimsieg", "signalCountPos": 3, "signalCountNeg": 0}
    d.update(kw)
    return d


class Gate(unittest.TestCase):
    def setUp(self):
        os.environ["COCOBET_DATASET"] = "wm"
        import cocobet_dataset
        importlib.reload(cocobet_dataset)
        import pick_announce_state as S
        importlib.reload(S)
        self.S = S

    def test_abwaegen_ohne_gegensignal_geht_raus(self):
        self.assertTrue(self.S.push_ok(_pick(signalCountPos=3, signalCountNeg=0)))

    def test_ein_einziges_gegensignal_genuegt(self):
        self.assertFalse(self.S.push_ok(_pick(signalCountPos=9, signalCountNeg=1)),
                         "neun Für-Signale heilen kein Wider-Signal — genau das war der Befund")

    def test_bet_bleibt_unangetastet(self):
        # Beim BET hat das Verdikt-Gate schon entschieden; der Filter darf da nicht nachtreten.
        self.assertTrue(self.S.push_ok(_pick(verdict="BET", signalCountPos=2, signalCountNeg=3)))
        self.assertTrue(self.S.push_ok(_pick(verdict="BET", signalCountPos=0, signalCountNeg=0)))

    def test_ohne_signale_fail_closed(self):
        self.assertFalse(self.S.push_ok(_pick(signalCountPos=0, signalCountNeg=0)))
        self.assertFalse(self.S.push_ok({"verdict": "ABWÄGEN", "market": "X"}),
                         "gar keine Angabe ist keine Erlaubnis")

    def test_zaehler_fehlen_signalliste_zaehlt(self):
        p = {"verdict": "ABWÄGEN", "market": "X",
             "signals": [{"name": "a", "score": 2}, {"name": "b", "score": 1}]}
        self.assertTrue(self.S.push_ok(p))
        p["signals"].append({"name": "c", "score": -3})
        self.assertFalse(self.S.push_ok(p))

    def test_nobet_und_excluded_bleiben_draussen(self):
        self.assertFalse(self.S.push_ok(_pick(verdict="NOBET")))
        self.assertFalse(self.S.push_ok(_pick(trackingExcluded=True)))
        self.assertFalse(self.S.push_ok(_pick(boldAlt=True)))
        self.assertFalse(self.S.push_ok(None))

    def test_der_markt_ist_egal(self):
        # Ausgerechnet 1X2 hatte die BESTE saubere Teilmenge (85,7% / +85,6%). Lucas' ursprüng-
        # licher Filter haette sie weggeworfen. Der Markt darf hier nirgends vorkommen.
        for markt in ("Heimsieg", "Auswärtssieg", "Über 2.5 Tore", "Beide Teams treffen — Ja",
                      "Doppelte Chance — X2", "AH Heim −1.5"):
            self.assertTrue(self.S.push_ok(_pick(market=markt, signalCountNeg=0)), markt)
            self.assertFalse(self.S.push_ok(_pick(market=markt, signalCountNeg=1)), markt)

    def test_telegram_nutzt_dieselbe_definition(self):
        import telegram_wm
        importlib.reload(telegram_wm)
        for p in (_pick(signalCountNeg=0), _pick(signalCountNeg=2), _pick(verdict="BET"),
                  _pick(verdict="NOBET"), _pick(boldAlt=True)):
            self.assertEqual(telegram_wm._is_posted(p), self.S.push_ok(p), p)

    def test_oeffentliche_bilanz_bleibt_unberuehrt(self):
        # Die Bilanz wertet nur verdict == "BET" (31.07.2026, Lucas) — und BET geht unveraendert
        # durch. Der Filter kann die gezeigte Bilanz also nicht rueckwirkend umschreiben.
        import telegram_wm
        importlib.reload(telegram_wm)
        n = telegram_wm.RECORD_MIN_N          # unter der Schwelle zeigt die Bilanz gar nichts
        bets = [{"verdict": "BET", "market": "Heimsieg", "odds": 2.0, "result": "WIN",
                 "signalCountPos": 1, "signalCountNeg": 4} for _ in range(n)]
        abw = [{"verdict": "ABWÄGEN", "market": "Über 2.5 Tore", "odds": 2.0, "result": "LOSS",
                "signalCountPos": 3, "signalCountNeg": 0}]
        txt = telegram_wm.bilanz_footer({"picks": {"A": bets + abw}})
        self.assertIn(str(n), txt, "die BETs mit vier Gegensignalen zaehlen weiter")
        # Und die ABWÄGEN-Niederlage taucht nicht auf — sie tat es auch vorher nicht.
        self.assertNotIn("1 ", txt.split(str(n))[-1][:4])


class Einheiten(unittest.TestCase):
    """iter_pick_units: gefiltert fuer den Push, vollstaendig fuers Schattenbuch."""

    def setUp(self):
        os.environ["COCOBET_DATASET"] = "wm"
        import cocobet_dataset
        importlib.reload(cocobet_dataset)
        import pick_announce_state as S
        importlib.reload(S)
        self.S = S
        ko = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        self.wm = {
            "groups": {"A": {"teams": [{"id": "MEX", "name": "Mexiko", "flag": "🇲🇽"},
                                       {"id": "ZAF", "name": "Südafrika", "flag": "🇿🇦"}],
                             "fixtures": [{"home": "MEX", "away": "ZAF", "matchday": 1, "kickoff": ko}]}},
            "koFixtures": [],
            "picks": {"A-1-MEX-ZAF": [
                _pick(market="Über 2.5 Tore", signalCountNeg=0),
                _pick(market="Auswärtssieg", signalCountNeg=2),
                {"verdict": "NOBET", "market": "Unter 2.5 Tore"},
            ]},
        }

    def test_push_bekommt_nur_die_sauberen(self):
        m = {u["market"] for u in self.S.iter_pick_units(self.wm)}
        self.assertEqual(m, {"Über 2.5 Tore"})

    def test_schattenbuch_bekommt_beide(self):
        u = {x["market"]: x for x in self.S.iter_pick_units(self.wm, alle=True)}
        self.assertEqual(set(u), {"Über 2.5 Tore", "Auswärtssieg"}, "NOBET bleibt auch hier draußen")
        self.assertTrue(u["Über 2.5 Tore"]["push"])
        self.assertFalse(u["Auswärtssieg"]["push"])
        self.assertEqual((u["Auswärtssieg"]["sigPos"], u["Auswärtssieg"]["sigNeg"]), (3, 2))

    def test_current_pick_ids_folgt_dem_filter(self):
        self.assertEqual(self.S.current_pick_ids(self.wm), {"A-1-MEX-ZAF|Über 2.5 Tore"},
                         "sonst markiert der Digest Picks als angekündigt, die er nie gesendet hat")


if __name__ == "__main__":
    unittest.main()
