#!/usr/bin/env python3
"""test_compute_streaks.py — Serien-Erkennung + Continuation (28.06.2026)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import compute_streaks as S  # noqa: E402


def _wm(form):
    return {"groups": {"ENG": {"name": "Premier League",
                               "teams": [{"id": "42", "name": "Arsenal"}, {"id": "50", "name": "City"}]}},
            "form": form}


class TestStreaks(unittest.TestCase):
    def test_lead_run(self):
        self.assertEqual(S._lead_run([True, True, True, False, True], True), 3)
        self.assertEqual(S._lead_run([False, True, True], True), 0)   # jüngstes passt nicht
        self.assertEqual(S._lead_run([False, False, False], False), 3)

    def test_over_streak_detected_with_continuation(self):
        wm = _wm({"42": {"o25Seq": [True, True, True, True], "bttsSeq": [False, True, False],
                         "over25Rate": 0.75, "bttsRate": 0.4}})
        out = S.build_streaks(wm)
        over = [s for s in out["streaks"] if s["type"] == "over25"]
        self.assertEqual(len(over), 1)
        self.assertEqual(over[0]["length"], 4)
        self.assertEqual(over[0]["team"], "Arsenal")
        self.assertEqual(over[0]["league"], "ENG")
        self.assertEqual(over[0]["continuation"]["state"], "intakt")   # 75% stützt
        # under25 darf NICHT erscheinen (jüngstes Spiel war Über)
        self.assertEqual([s for s in out["streaks"] if s["type"] == "under25"], [])

    def test_short_streak_filtered(self):
        wm = _wm({"42": {"o25Seq": [True, True, False], "over25Rate": 0.6, "bttsRate": 0.5}})
        self.assertEqual(S.build_streaks(wm)["streaks"], [])   # nur 2 < MIN_LEN

    def test_btts_no_streak_wobbles_against_baseline(self):
        # 3× kein BTTS in Folge, aber Grundrate BTTS 70% → Serie läuft gegen die Rate → wackelt
        wm = _wm({"50": {"o25Seq": [True, False], "bttsSeq": [False, False, False],
                         "over25Rate": 0.5, "bttsRate": 0.7}})
        out = S.build_streaks(wm)
        bn = [s for s in out["streaks"] if s["type"] == "bttsNo"]
        self.assertEqual(len(bn), 1)
        self.assertEqual(bn[0]["continuation"]["state"], "wackelt")

    def test_corner_streak_from_cornersform(self):
        wm = _wm({})
        wm["cornersForm"] = {"42": {"cornerLine": 9.5, "overLineRate": 0.7,
                                    "cornerOverSeq": [True, True, True, True, False]}}
        out = S.build_streaks(wm)
        co = [s for s in out["streaks"] if s["type"] == "cornersOver"]
        self.assertEqual(len(co), 1)
        self.assertEqual(co[0]["length"], 4)
        self.assertEqual(co[0]["team"], "Arsenal")
        self.assertIn("9,5 Ecken", co[0]["market"])
        self.assertEqual(co[0]["continuation"]["state"], "intakt")   # 70% stützt
        self.assertEqual([s for s in out["streaks"] if s["type"] == "cornersUnder"], [])

    def test_venue_split_home_streak(self):
        wm = _wm({"42": {"o25Seq": [True, True, True, True], "venueSeq": ["H", "A", "H", "H"],
                         "over25Rate": 0.7, "bttsRate": 0.4}})
        out = S.build_streaks(wm)
        over = {s["venue"]: s["length"] for s in out["streaks"] if s["type"] == "over25"}
        self.assertEqual(over.get("all"), 4)
        self.assertEqual(over.get("H"), 3)        # Heimspiele (Index 0,2,3) alle Über
        self.assertNotIn("A", over)               # nur 1 Auswärts → < MIN_LEN

    def test_scored_and_cleansheet_markets(self):
        wm = _wm({"42": {"scoredSeq": [True, True, True], "scoredRate": 0.9,
                         "csSeq": [True, True, True], "cleanSheetRate": 0.5}})
        out = S.build_streaks(wm)
        self.assertTrue(any(s["type"] == "scored" and s["market"] == "Team trifft" for s in out["streaks"]))
        self.assertTrue(any(s["type"] == "cleanSheet" for s in out["streaks"]))

    def test_prior_from_pre_streak_games(self):
        # 08.08.2026 (Lucas): 4er-Over-Serie, davor 8× Unter → Grundrate OHNE Serie = 0% → wackelt (statt
        # tautologische Roh-Rate). basis = "prior", weil genug Vorlauf da ist.
        wm = _wm({"42": {"o25Seq": [True, True, True, True] + [False] * 8, "over25Rate": 0.7, "bttsRate": 0.4}})
        out = S.build_streaks(wm)
        over = next(s for s in out["streaks"] if s["type"] == "over25" and s["venue"] == "all")
        self.assertEqual(over["length"], 4)
        self.assertEqual(over["basis"], "prior")
        self.assertEqual(over["preN"], 8)
        self.assertEqual(over["continuation"]["ratePct"], 0)          # Vorlauf 0/8 Über
        self.assertEqual(over["continuation"]["state"], "wackelt")

    def test_ohne_vorlauf_urteilt_die_liga_nicht_die_serie(self):
        """🔴 04.09.2026 (Lucas-Serien-Check) — dieser Test stand vorher andersherum.

        Er nagelte den Fallback auf die ROH-Rate fest (basis „pure"). Fuellt die Serie aber das
        15-Spiele-Fenster, IST die Roh-Rate die Serie — also 100 %. Der Kommentar ueber
        `_pre_streak_rate` warnt sogar davor („tautologische 100 %"), und der Fallback tat es
        trotzdem. Gemessen: 457 von 733 Serien ohne unabhaengige Basis, 345 davon als „intakt"
        ausgewiesen, und ALLE 25 der Top-25 nach Laenge urteilten ueber sich selbst.

        Es gibt aber eine unabhaengige Zahl: die Grundrate des MARKTES ueber alle Teams.
        """
        wm = _wm({"42": {"o25Seq": [True] * 15, "over25Rate": 1.0, "bttsRate": 0.4},
                  "50": {"over25Rate": 0.4, "bttsRate": 0.4}})
        out = S.build_streaks(wm)
        over = next(s for s in out["streaks"] if s["type"] == "over25" and s["venue"] == "all")
        self.assertEqual(over["length"], 15)
        self.assertEqual(over["basis"], "liga", "keine eigene Vorgeschichte → Liga-Massstab")
        self.assertEqual(over["preN"], 0)
        self.assertEqual(over["continuation"]["ratePct"], 70, "Mittel aus 100% und 40%")
        self.assertNotEqual(over["continuation"]["ratePct"], 100, "die Serie darf sich nicht selbst belegen")
        self.assertIn("Liga-Grundrate", over["continuation"]["label"])

    def test_die_seltenheit_haengt_am_markt_nicht_nur_an_der_laenge(self):
        """Der Kern: 15x „Team trifft" ist harmloser als eine kurze Zu-null-Serie."""
        wm = _wm({"42": {"o25Seq": [True] * 15, "scoredSeq": [True] * 15, "csSeq": [True] * 4,
                         "over25Rate": 0.9, "scoredRate": 0.9, "cleanSheetRate": 0.2,
                         "bttsRate": 0.4}})
        out = S.build_streaks(wm)
        trifft = next(s for s in out["streaks"] if s["type"] == "scored" and s["venue"] == "all")
        zunull = next(s for s in out["streaks"] if s["type"] == "cleanSheet" and s["venue"] == "all")
        self.assertGreater(trifft["length"], zunull["length"], "die Trifft-Serie ist laenger")
        self.assertLess(zunull["zufallPct"], trifft["zufallPct"], "aber die Zu-null-Serie ist seltener")
        self.assertLess(out["streaks"].index(zunull), out["streaks"].index(trifft),
                        "und steht deshalb weiter oben")

    def test_card_streak_from_cornersform(self):
        wm = _wm({})
        wm["cornersForm"] = {"42": {"cardLine": 3.5, "cardOverRate": 0.6,
                                    "cardOverSeq": [True, True, True]}}
        out = S.build_streaks(wm)
        cards = [s for s in out["streaks"] if s["type"] == "cards"]
        self.assertEqual(len(cards), 1)
        self.assertIn("3,5 Karten", cards[0]["market"])

    def test_next_fixture_with_opponent_rate(self):
        from datetime import date, timedelta
        fut = (date.today() + timedelta(days=3)).isoformat()
        wm = _wm({"42": {"o25Seq": [True, True, True], "over25Rate": 0.7, "bttsRate": 0.4},
                  "50": {"over25Rate": 0.66}})
        wm["groups"]["ENG"]["fixtures"] = [{"home": "42", "away": "50", "date": fut,
                                            "kickoff": fut + "T15:00:00Z"}]
        out = S.build_streaks(wm)
        over = next(s for s in out["streaks"] if s["type"] == "over25" and s["venue"] == "all")
        self.assertEqual(over["next"]["oppName"], "City")
        self.assertEqual(over["next"]["atHome"], True)
        self.assertEqual(over["next"]["oppRatePct"], 66)

    def test_matchup_downgrades_status_when_opponent_hurts(self):
        # Eigentendenz stark (80% → allein „intakt"), aber nächster Gegner geht kaum über (20%)
        # → kombiniert 0.6*0.8 + 0.4*0.2 = 0.56 → „neutral" (lebendiger Status, 29.06.2026).
        from datetime import date, timedelta
        fut = (date.today() + timedelta(days=2)).isoformat()
        # 04.09.2026: Der Vorlauf muss lang genug sein (>=5 Spiele), sonst kommt die
        # Eigentendenz gar nicht mehr vom Team, sondern aus der Liga-Grundrate — und der Test
        # hier prueft die Gegner-Gewichtung, nicht die Basis-Wahl.
        wm = _wm({"42": {"o25Seq": [True] * 4 + [False] + [True] * 4,
                         "over25Rate": 0.8, "bttsRate": 0.4},
                  "50": {"over25Rate": 0.20}})
        wm["groups"]["ENG"]["fixtures"] = [{"home": "42", "away": "50", "date": fut,
                                            "kickoff": fut + "T15:00:00Z"}]
        out = S.build_streaks(wm)
        over = next(s for s in out["streaks"] if s["type"] == "over25" and s["venue"] == "all")
        self.assertEqual(over["basis"], "prior")
        self.assertEqual(over["ratePct"], 80)                 # Eigentendenz aus dem Vorlauf (4/5)
        self.assertEqual(over["oppSupportPct"], 20)           # Gegner stützt nur 20%
        self.assertEqual(over["matchupPct"], 56)              # kombiniert
        self.assertEqual(over["continuation"]["state"], "neutral")   # von intakt → offen gedämpft

    def test_matchup_only_own_when_no_opponent(self):
        # Ohne nächstes Spiel bleibt der Status reine Eigentendenz (Fallback).
        wm = _wm({"42": {"o25Seq": [True, True, True, True], "over25Rate": 0.8, "bttsRate": 0.4}})
        out = S.build_streaks(wm)
        over = next(s for s in out["streaks"] if s["type"] == "over25")
        self.assertEqual(over["continuation"]["state"], "intakt")
        self.assertNotIn("oppSupportPct", over)

    def test_signal_overlay_confirms_status(self):
        # Stufe 2: Pick des nächsten Spiels in Serien-Richtung mit ≥2 Signalen → Status auf „intakt".
        from datetime import date, timedelta
        fut = (date.today() + timedelta(days=2)).isoformat()
        wm = _wm({"42": {"o25Seq": [True, True, True], "over25Rate": 0.5, "bttsRate": 0.4},
                  "50": {"over25Rate": 0.5}})
        wm["groups"]["ENG"]["fixtures"] = [{"home": "42", "away": "50", "matchday": 7,
                                            "date": fut, "kickoff": fut + "T15:00:00Z"}]
        wm["picks"] = {"ENG-7-42-50": [{"market": "Über 2.5 Tore", "verdict": "BET",
                                        "signalCountPos": 3, "convictionScore": 7,
                                        "signals": [{"name": "form_trend", "weighted_score": -2.0},
                                                    {"name": "h2h_goals", "weighted_score": 1.0}]}]}
        out = S.build_streaks(wm)
        over = next(s for s in out["streaks"] if s["type"] == "over25" and s["venue"] == "all")
        self.assertEqual(over["signalInfo"]["state"], "confirm")
        self.assertEqual(over["signalInfo"]["count"], 3)
        self.assertIn("form_trend", over["signalInfo"]["names"])
        self.assertEqual(over["continuation"]["state"], "intakt")   # Signale heben den Status

    def test_signal_overlay_contradicts_status(self):
        # Engine pickt die GEGENrichtung (Unter) → Über-Serie wird trotz starker Tendenz „wackelt".
        from datetime import date, timedelta
        fut = (date.today() + timedelta(days=2)).isoformat()
        wm = _wm({"42": {"o25Seq": [True, True, True, True], "over25Rate": 0.8, "bttsRate": 0.4},
                  "50": {"over25Rate": 0.7}})
        wm["groups"]["ENG"]["fixtures"] = [{"home": "42", "away": "50", "matchday": 7,
                                            "date": fut, "kickoff": fut + "T15:00:00Z"}]
        wm["picks"] = {"ENG-7-42-50": [{"market": "Unter 2.5 Tore", "verdict": "BET",
                                        "signalCountPos": 3, "convictionScore": 6, "signals": []}]}
        out = S.build_streaks(wm)
        over = next(s for s in out["streaks"] if s["type"] == "over25" and s["venue"] == "all")
        self.assertEqual(over["signalInfo"]["state"], "contradict")
        self.assertEqual(over["continuation"]["state"], "wackelt")

    def test_sorted_by_length_desc(self):
        wm = _wm({"42": {"o25Seq": [True, True, True], "over25Rate": 0.6, "bttsRate": 0.5},
                  "50": {"o25Seq": [True] * 6, "over25Rate": 0.8, "bttsRate": 0.5}})
        out = S.build_streaks(wm)
        self.assertEqual(out["streaks"][0]["length"], 6)
        self.assertTrue(out["streaks"][0]["strong"])


if __name__ == "__main__":
    unittest.main()


# ── 08.09.2026: die Seltenheit rechnete mit dem falschen Nenner ─────────────────────────
# Externes Feedback zur Serien-Seite, nachgerechnet an den echten Artefakten und in jedem Punkt
# bestaetigt:
#     Parma · Unter 2,5, 10er:  angezeigt „1 von 11.990 (Liga-Basis 39 %)",
#                               daneben   „Eigenrate vor der Serie 80 %"  →  0,8^10 = 1 von 9.
# Faktor 1.290. Betroffen: 207 von 556 Serien allein in der Liga-Datei.
class TestSeltenheit:
    def test_die_eigene_rate_ist_der_nenner_wenn_es_sie_gibt(self):
        e = S.seltenheit(0.8, 5, 0.39, 10, 4125)
        assert e["basis"] == "eigen"
        assert e["einsZu"] == 9, "0,8^10 = 1 von 9 — nicht 1 von 11.990"

    def test_ohne_eigene_vorgeschichte_ist_die_seltenheit_NICHT_BELEGBAR(self):
        """⚠️ Der Unterschied, der vorher still verschwand: „unauffaellig" und „nicht gemessen"
        sind nicht dasselbe. Zwei der fuenf Serien auf Lucas' Board hatten gar keine Eigenrate,
        und die Liga-Basis rutschte als Default durch."""
        e = S.seltenheit(None, 0, 0.39, 10, 4125)
        assert e["basis"] == "liga"
        assert e["urteil"] == "nicht belegbar"
        assert "Durchschnittsteam" in e["grund"]

    def test_der_punktschaetzer_bekommt_sein_band(self):
        """Parmas 80 % sind 4 von 5 Spielen. Das Band macht daraus 1 von 2 bis 1 von 4.097 —
        eine Zahl, die ueber drei Groessenordnungen schwankt, ist keine Auskunft."""
        e = S.seltenheit(0.8, 5, 0.39, 10, 4125)
        lo, hi = e["einsZuBand"]
        assert lo < e["einsZu"] < hi
        assert hi / max(lo, 1) > 100, "bei n=5 muss das Band die Unsicherheit auch zeigen"

    def test_ein_grosses_suchfeld_macht_seltenes_erwartbar(self):
        """Ueber 125 Teams x 11 Maerkte x 3 Ansichten ist ein „1 von 90" 46-mal zu erwarten."""
        e = S.seltenheit(0.57, 7, 0.35, 8, 4125)
        assert e["urteil"] == "erwartbar"
        assert e["erwartet"] > 1

    def test_auffaellig_verlangt_die_guenstigste_eigene_rate(self):
        """⭐ Die Beweislast liegt beim Befund. Der Fall, der die Regel traegt: 3 von 10 Spielen
        (30 %) bei einer 7er-Serie ergibt als PUNKTSCHAETZER 0,9 erwartete Laeufe im Feld — nach
        dem Punkt also „auffaellig". Das 95-%-Band reicht aber bis 61 %, und damit sind 70 solche
        Laeufe zu erwarten. Wer nach dem Punkt urteilt, meldet einen Fund, den die Suche selbst
        erzeugt hat."""
        F = 4125
        e = S.seltenheit(0.3, 10, 0.5, 7, F)
        assert F * (0.3 ** 7) < 1.0, "Vorbedingung: der Punktschaetzer wuerde 'auffaellig' sagen"
        assert e["erwartetBand"][1] > 1.0, "Vorbedingung: die Bandobergrenze sagt das Gegenteil"
        assert e["urteil"] == "erwartbar"

    def test_auffaellig_gibt_es_wirklich_wenn_die_daten_es_hergeben(self):
        """Kein Kriterium, das nie feuert: mit genug Vorgeschichte und niedriger eigener Rate
        bleibt auch die Bandobergrenze unter einem erwarteten Lauf."""
        e = S.seltenheit(0.1, 40, 0.2, 12, 4125)
        assert e["urteil"] == "auffaellig"
        assert e["erwartetBand"][1] < 1

    def test_ohne_jede_basis_gibt_es_keine_zahl(self):
        assert S.seltenheit(None, 0, None, 8, 4125) is None

    def test_das_urteil_entsteht_im_produzenten(self):
        """Kein Frontend vergleicht selbst gegen eine Schwelle — das Urteil gehoert dorthin, wo
        die Zahl entsteht."""
        e = S.seltenheit(0.57, 7, 0.35, 8, 4125)
        assert set(("urteil", "grund", "erwartet", "familie")) <= set(e)
