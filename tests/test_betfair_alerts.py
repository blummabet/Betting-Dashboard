# tests/test_betfair_alerts.py — Betfair-Telegram-Alerts (29.07.2026)
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_alerts as BA


def mk(name, runners):
    return {name: {"runners": runners}}


def match(mid=1, home="Alpha", away="Beta", league="Test", country="DE", markets=None):
    # Default: Rest-Tier (league „Test", Land DE) → HZ-Schwelle 5000, frisches Geld 20000.
    return {"matchId": mid, "home": home, "away": away, "league": league,
            "country": country, "markets": markets or {}}


class TestTier(unittest.TestCase):
    def test_top5_and_mls_are_top(self):
        self.assertEqual(BA.tier_of({"league": "German Bundesliga"}), "top")
        self.assertEqual(BA.tier_of({"league": "Major League Soccer"}), "top")

    def test_international_is_top(self):
        # Lucas 30.07.2026: internationale Bewerbe (UEFA / Länderspiele) verhalten sich wie Top.
        self.assertEqual(BA.tier_of({"league": "UEFA Champions League Qualifiers"}), "top")
        self.assertEqual(BA.tier_of({"league": "Friendly", "country": "International"}), "top")

    def test_others_are_rest(self):
        self.assertEqual(BA.tier_of({"league": "Chinese League 2", "country": "CN"}), "rest")

    def test_summer_series_not_top(self):
        self.assertEqual(BA.tier_of({"league": "English Premier League Summer Series"}), "rest")


class TestHtAlert(unittest.TestCase):
    def _ht_market(self, hv, dv, av, name="Half Time"):
        return mk(name, [
            {"name": "Alpha", "odd": 2.1, "vol": hv},
            {"name": "The Draw", "odd": 2.2, "vol": dv},
            {"name": "Beta", "odd": 3.4, "vol": av}])

    def test_fires_when_onesided(self):
        # Rest-Tier: 6000 ≥ 5000 UND ~83–100% auf Alpha (≥85% mit 5500/6000)
        m = match(markets=self._ht_market(5500, 250, 250))
        a = BA.ht_alert(m)
        self.assertIsNotNone(a)
        self.assertEqual(a["scenario"], "ht")
        self.assertAlmostEqual(a["total"], 6000)
        self.assertEqual(a["leadName"], "Alpha")
        self.assertGreaterEqual(a["leadShare"], 0.85)

    def test_balanced_market_none(self):
        # 6000 ≥ 5000, aber breit verteilt (max 50%) → kein Signal
        self.assertIsNone(BA.ht_alert(match(markets=self._ht_market(3000, 1500, 1500))))

    def test_below_threshold_none(self):
        # einseitig (100%), aber nur 4000 < 5000 (Rest)
        self.assertIsNone(BA.ht_alert(match(markets=self._ht_market(4000, 0, 0))))

    def test_top_tier_needs_10k(self):
        # Top-Liga: 8000 < 10000 → nichts; 11000 ≥ 10000 → feuert
        self.assertIsNone(BA.ht_alert(match(league="German Bundesliga", markets=self._ht_market(8000, 0, 0))))
        self.assertIsNotNone(BA.ht_alert(match(league="German Bundesliga", markets=self._ht_market(11000, 0, 0))))

    def test_over15_first_half_counts(self):
        # „egal ob over 1,5 oder 12x HT": Über/Unter 1,5 erste HZ zählt genauso.
        m = match(markets=mk("First Half Goals 1.5", [
            {"name": "Over 1.5 Goals", "odd": 1.9, "vol": 5500},
            {"name": "Under 1.5 Goals", "odd": 2.0, "vol": 300}]))
        a = BA.ht_alert(m)
        self.assertIsNotNone(a)
        self.assertEqual(a["market"], "First Half Goals 1.5")
        self.assertFalse(a["isX2"])
        self.assertEqual(a["mktLabel"], "HZ Over/Under 1.5")

    def test_no_ht_market_none(self):
        self.assertIsNone(BA.ht_alert(match(markets=mk("Match Odds", [{"name": "Alpha", "odd": 2, "vol": 9000}]))))


class TestFreshAlert(unittest.TestCase):
    def test_top_needs_30k_per_market(self):
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 2, "vol": 40000}, {"name": "Beta", "odd": 2, "vol": 12000}]))
        hist = {"7": [{"mkv": {"Match Odds": 20000}}, {"mkv": {"Match Odds": 52000}}]}   # +32k auf 1X2 (≥30k)
        a = BA.fresh_alert(m, hist)
        self.assertIsNotNone(a)
        self.assertEqual(a["tier"], "top")
        self.assertEqual(a["market"], "Match Odds")
        self.assertAlmostEqual(a["inflow"], 32000)
        self.assertAlmostEqual(a["total"], 52000)     # Markt-Volumen, NICHT Spiel-Gesamt
        self.assertEqual(a["leadName"], "Alpha")

    def test_top_below_30k_none(self):
        m = match(mid=7, league="German Bundesliga", markets={})
        self.assertIsNone(BA.fresh_alert(m, {"7": [{"mkv": {"Match Odds": 20000}}, {"mkv": {"Match Odds": 45000}}]}))  # +25k < 30k

    def test_biggest_inflow_market_wins(self):
        # 1X2 +7k, aber Ü/U 2.5 +25k → der groessere Zufluss-Markt gewinnt (Rest-Liga, Schwelle 20k)
        m = match(mid=8, league="Chinese League 2", country="CN",
                  markets=mk("Over/Under 2.5 Goals", [{"name": "Over 2.5 Goals", "odd": 2, "vol": 32000}, {"name": "Under 2.5 Goals", "odd": 2, "vol": 3000}]))
        hist = {"8": [{"mkv": {"Match Odds": 40000, "Over/Under 2.5 Goals": 10000}},
                      {"mkv": {"Match Odds": 47000, "Over/Under 2.5 Goals": 35000}}]}
        a = BA.fresh_alert(m, hist)
        self.assertIsNotNone(a)
        self.assertEqual(a["market"], "Over/Under 2.5 Goals")
        self.assertAlmostEqual(a["inflow"], 25000)

    def test_rest_below_20k_none(self):
        m = match(mid=8, league="Chinese League 2", country="CN", markets={})
        self.assertIsNone(BA.fresh_alert(m, {"8": [{"mkv": {"Match Odds": 5000}}, {"mkv": {"Match Odds": 20000}}]}))  # +15k < 20k

    def test_no_mkv_none(self):
        # ohne per-Markt-History (nur totalVol) kein Signal — irrefuehrende Gesamt-Zahl vermeiden
        self.assertIsNone(BA.fresh_alert(match(mid=9, league="Chinese League 2"),
                                         {"9": [{"totalVol": 5000}, {"totalVol": 30000}]}))

    def test_needs_two_points(self):
        self.assertIsNone(BA.fresh_alert(match(mid=8, league="Chinese League 2"), {"8": [{"mkv": {"Match Odds": 5000}}]}))


class TestDedup(unittest.TestCase):
    def test_first_time_sends(self):
        self.assertTrue(BA.should_send({}, "ht:1", 8000))

    def test_small_increase_suppressed(self):
        self.assertFalse(BA.should_send({"ht:1": 8000}, "ht:1", 10000))   # +25% < +50%

    def test_big_increase_resends(self):
        self.assertTrue(BA.should_send({"ht:1": 8000}, "ht:1", 12500))    # +56% ≥ +50%


class TestMessage(unittest.TestCase):
    def test_ht_message(self):
        m = match(markets=mk("Half Time", [{"name": "Alpha", "odd": 2, "vol": 8000},
                                           {"name": "The Draw", "odd": 3, "vol": 500},
                                           {"name": "Beta", "odd": 4, "vol": 500}]))
        msg = BA.build_message(BA.ht_alert(m))
        self.assertIn("Halbzeit-Geld", msg)
        self.assertIn("HZ 1X2", msg)
        self.assertIn("auf Alpha", msg)   # dominanter Ausgang genannt
        self.assertIn("%", msg)

    def test_fresh_message(self):
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 2, "vol": 45000}]))
        a = BA.fresh_alert(m, {"7": [{"mkv": {"Match Odds": 10000}}, {"mkv": {"Match Odds": 45000}}]})
        msg = BA.build_message(a)
        self.assertIn("Frisches Geld", msg)
        self.assertIn("Top-Liga", msg)
        self.assertIn("1X2", msg)          # Markt genannt
        self.assertIn("frisch", msg)
        self.assertIn("Alpha", msg)        # fuehrender Ausgang


class TestCollect(unittest.TestCase):
    def test_collects_both(self):
        m = match(mid=9, league="Chinese League 2", country="CN", markets=mk("Half Time",
                  [{"name": "Alpha", "odd": 2, "vol": 8000}]))
        alerts = BA.collect_alerts({"matches": [m]}, {"9": [{"mkv": {"Half Time": 1000}}, {"mkv": {"Half Time": 22000}}]})
        kinds = sorted(a["scenario"] for a in alerts)
        self.assertEqual(kinds, ["fresh", "ht"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestFavoriteFilter(unittest.TestCase):
    def test_ht_skips_near_lock_favorite(self):
        # 100% auf einem Ausgang, aber Quote 1.05 (fuehrt schon) -> sinnlos, kein Push
        m = match(markets=mk("Half Time", [
            {"name": "Alpha", "odd": 1.05, "vol": 9000},
            {"name": "The Draw", "odd": 15, "vol": 0}, {"name": "Beta", "odd": 30, "vol": 0}]))
        self.assertIsNone(BA.ht_alert(m))

    def test_ht_fires_when_lead_odd_ok(self):
        m = match(markets=mk("Half Time", [
            {"name": "Alpha", "odd": 1.8, "vol": 9000},
            {"name": "The Draw", "odd": 3, "vol": 500}, {"name": "Beta", "odd": 6, "vol": 500}]))
        self.assertIsNotNone(BA.ht_alert(m))

    def test_fresh_skips_near_lock_favorite(self):
        # Zufluss auf 1X2, aber Fuehrender @1.03 -> sinnlos
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 1.03, "vol": 90000}, {"name": "Beta", "odd": 40, "vol": 2000}]))
        hist = {"7": [{"mkv": {"Match Odds": 20000}}, {"mkv": {"Match Odds": 92000}}]}   # +72k
        self.assertIsNone(BA.fresh_alert(m, hist))

    def test_fresh_fires_when_lead_odd_ok(self):
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 1.6, "vol": 60000}, {"name": "Beta", "odd": 3.2, "vol": 30000}]))
        a = BA.fresh_alert(m, {"7": [{"mkv": {"Match Odds": 60000}}, {"mkv": {"Match Odds": 90000}}]})
        self.assertIsNotNone(a)
        self.assertAlmostEqual(a["leadOdd"], 1.6)


class TestBoldMoney(unittest.TestCase):
    def test_fresh_money_is_bold(self):
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 1.8, "vol": 45000}]))
        a = BA.fresh_alert(m, {"7": [{"mkv": {"Match Odds": 10000}}, {"mkv": {"Match Odds": 45000}}]})
        msg = BA.build_message(a)
        self.assertIn("+<b>", msg)          # Zufluss fett
        self.assertIn("jetzt <b>", msg)     # Markt-Volumen fett
        self.assertIn("@1.80", msg)         # Quote sichtbar

    def test_ht_money_is_bold(self):
        m = match(markets=mk("Half Time", [{"name": "Alpha", "odd": 1.9, "vol": 8000},
                                           {"name": "The Draw", "odd": 3, "vol": 500},
                                           {"name": "Beta", "odd": 5, "vol": 500}]))
        msg = BA.build_message(BA.ht_alert(m))
        self.assertRegex(msg, r"HZ 1X2: <b>€")   # gematchtes Geld fett


class TestPublicMoneyflow(unittest.TestCase):
    """31.07.2026 (Lucas) — öffentlicher Channel: kuratierte höhere Schwellen (Fresh Top100K/Rest30K,
    HZ Top50K/Rest15K), Format „Betfair Moneyflow"/„Halftime Flow", Over/Under ausgeschrieben, „Check:"."""

    def test_public_fresh_thresholds(self):
        # Rest-Liga: +€25K < 30K Public-Schwelle → kein Public-Alert (privat wäre es einer)
        hist = {"7": [{"mkv": {"Match Odds": 10000}}, {"mkv": {"Match Odds": 35000}}]}  # +25K
        m = match(mid=7, markets=mk("Match Odds", [{"name": "Alpha", "odd": 2.0, "vol": 35000}]))
        self.assertIsNone(BA.fresh_alert(m, hist, BA.PUB_FRESH_TOP, BA.PUB_FRESH_REST))
        # +€32K ≥ 30K → Public-Alert
        hist2 = {"7": [{"mkv": {"Match Odds": 10000}}, {"mkv": {"Match Odds": 42000}}]}  # +32K
        self.assertIsNotNone(BA.fresh_alert(m, hist2, BA.PUB_FRESH_TOP, BA.PUB_FRESH_REST))

    def test_public_ht_thresholds(self):
        # Rest-Liga HZ: €12K < 15K Public-Schwelle → kein Alert; €16K ≥ 15K → Alert (einseitig)
        m_lo = match(markets=mk("Half Time", [{"name": "Alpha", "odd": 1.5, "vol": 12000}, {"name": "The Draw", "odd": 6, "vol": 500}, {"name": "Beta", "odd": 8, "vol": 500}]))
        self.assertIsNone(BA.ht_alert(m_lo, BA.PUB_HT_TOP, BA.PUB_HT_REST))
        m_hi = match(markets=mk("Half Time", [{"name": "Alpha", "odd": 1.5, "vol": 16000}, {"name": "The Draw", "odd": 6, "vol": 500}, {"name": "Beta", "odd": 8, "vol": 500}]))
        self.assertIsNotNone(BA.ht_alert(m_hi, BA.PUB_HT_TOP, BA.PUB_HT_REST))

    def test_public_fresh_format(self):
        a = {"scenario": "fresh", "matchId": "1", "flag": "🇵🇾", "home": "San Lorenzo",
             "away": "Guarani", "league": "Paraguayan Reserves", "market": "Over/Under 3.5 Goals",
             "inflow": 27900, "total": 28600, "tier": "rest", "leadName": "Over 3.5 Goals",
             "leadShare": 0.74, "leadOdd": 2.0}
        msg = BA.build_public_message(a)
        self.assertIn("🟡 <b>Betfair Moneyflow</b>", msg)
        self.assertIn("Over/Under 3.5", msg)          # ausgeschrieben, nicht „Ü/U"
        self.assertNotIn("Ü/U", msg)
        # 05.08.2026 (Lucas): neues Format — Zufluss-Anteil am Markt + Geld-Leiste + Quote
        self.assertIn("+<b>€27.9K</b> → Markt <b>€28.6K</b>", msg)
        self.assertIn("(98% frisch)", msg)            # 27.9/28.6
        self.assertIn("📊 <b>Over 3.5 Goals</b>", msg)
        self.assertIn("74% @2.00", msg)
        self.assertRegex(msg, r"[▓]+[░]*")            # visuelle Geld-Leiste
        self.assertNotIn("Check:", msg)
        self.assertNotIn("führt", msg)

    def test_public_ht_format(self):
        a = {"scenario": "ht", "matchId": "2", "flag": "🌍", "home": "Gremio", "away": "Bolivar",
             "league": "CONMEBOL Copa Sudamericana", "market": "First Half Goals 1.5", "total": 89400,
             "leadLabel": "Under 1.5 Goals", "leadShare": 0.86, "leadOdd": 1.53}
        msg = BA.build_public_message(a)
        self.assertIn("🔵 <b>Betfair Halftime Flow</b>", msg)
        self.assertIn("HZ Over/Under 1.5", msg)
        self.assertIn("<b>€89.4K</b> gematcht", msg)
        self.assertIn("📊 <b>Under 1.5 Goals</b>", msg)
        self.assertIn("86% @1.53", msg)
        self.assertNotIn("Check:", msg)

    def test_public_live_badge_kein_score_keine_minute(self):
        # 05.08.2026 (Lucas: Spielstand zu riskant bei 15-Min-Scan): Status nur Zustand, KEIN
        # Score/keine Minute; laufende Spiele bekommen die 🔴-LIVE-Kopfzeile.
        base = {"scenario": "fresh", "matchId": "9", "flag": "🇮🇹", "home": "Napoli", "away": "Osasuna",
                "league": "Serie A", "market": "Match Odds", "inflow": 40000, "total": 100000,
                "tier": "top", "leadName": "Osasuna", "leadShare": 0.62, "leadOdd": 2.4}
        live = dict(base); live["live"] = {"time": 34, "is_ht": False, "finished": False, "goal_v1": 1, "goal_v2": 0}
        m = BA.build_public_message(live)
        self.assertIn("🔴 <b>LIVE</b>", m)      # LIVE-Badge in der Kopfzeile
        self.assertIn("⚽ läuft", m)
        self.assertNotIn("34", m)               # keine Minute
        self.assertNotIn("1:0", m)              # kein Spielstand
        # Halbzeit: Badge + „Halbzeit", aber kein Score
        ht = dict(base); ht["live"] = {"is_ht": True, "finished": False, "goal_v1": 0, "goal_v2": 3}
        h = BA.build_public_message(ht)
        self.assertIn("🔴 <b>LIVE</b>", h)
        self.assertIn("⏸ Halbzeit", h)
        self.assertNotIn("0:3", h)
        # Vor Anpfiff: kein LIVE-Badge, Countdown bleibt
        from datetime import datetime, timezone, timedelta
        pre = dict(base); pre["kickoff"] = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        pre["live"] = {"time": 0, "is_ht": False, "finished": False}
        pm = BA.build_public_message(pre)
        self.assertNotIn("LIVE", pm)
        self.assertIn("Anpfiff in", pm)

    def test_money_on_leader_flagged_not_suppressed(self):
        # 08.08.2026 (Lucas): Geld auf den Fuehrenden wird NICHT mehr hart unterdrueckt, sondern als
        # onLeader markiert. Das Back-Gate (_leader_gate) entscheidet danach anhand der Quote.
        from datetime import datetime, timezone, timedelta
        ko = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
        def mk(vol_home, vol_away):
            return {"matchId": "1", "home": "Napoli", "away": "Osasuna", "league": "Serie A", "country": "IT",
                    "kickoff": ko, "liveInfo": {"time": 34, "goal_v1": 1, "goal_v2": 0, "finished": False, "is_ht": False},
                    "markets": {"Match Odds": {"runners": [
                        {"name": "Napoli", "odd": 1.5, "vol": vol_home},
                        {"name": "Osasuna", "odd": 6.0, "vol": vol_away},
                        {"name": "The Draw", "odd": 4.0, "vol": 10000}]}}}
        hist = {"1": [{"mkv": {"Match Odds": 10000}}, {"mkv": {"Match Odds": 120000}}]}
        a = BA.fresh_alert(mk(90000, 10000), hist)     # Geld auf Napoli (fuehrt 1:0) -> markiert, nicht raus
        self.assertIsNotNone(a); self.assertTrue(a["onLeader"])
        a2 = BA.fresh_alert(mk(10000, 90000), hist)    # Geld auf Osasuna (Rueckstand)
        self.assertIsNotNone(a2); self.assertEqual(a2["leadName"], "Osasuna"); self.assertFalse(a2["onLeader"])
        m_lvl = mk(90000, 10000); m_lvl["liveInfo"]["goal_v2"] = 1   # Gleichstand -> kein Fuehrer
        self.assertFalse(BA.fresh_alert(m_lvl, hist)["onLeader"])

    def test_leader_gate_needs_back(self):
        # Fuehrungs-Geld nur durch, wenn die Quote bestaetigt (leadDir 'in'/Back). Sonst raus.
        big = {"scenario": "fresh", "tier": "rest", "inflow": 99000}   # weit ueber Extra-Schwelle
        self.assertEqual(BA._leader_gate([dict(big, onLeader=True, leadDir="out")]), [])  # driftet -> raus
        self.assertEqual(len(BA._leader_gate([dict(big, onLeader=True, leadDir="in")])), 1)  # Back+gross -> bleibt
        self.assertEqual(len(BA._leader_gate([dict(big, onLeader=True)])), 0)             # keine Richtung -> raus
        self.assertEqual(len(BA._leader_gate([{"onLeader": False, "leadDir": "out"}])), 1)  # Nicht-Fuehrer unberuehrt

    def test_leader_gate_extra_threshold(self):
        # 08.08.2026 (Lucas): Fuehrungs-Geld braucht EXTRA-Schwelle (LEAD_PUSH_FACTOR x tier-Schwelle),
        # sonst flutet Mitlauf-Geld an starken Spieltagen den Push. Nicht-Fuehrer bleibt bei Normal-Schwelle.
        base = BA.FRESH_REST_EUR                       # 20K Trades-Rest
        lo = {"scenario": "fresh", "tier": "rest", "onLeader": True, "leadDir": "in",
              "inflow": base * 1.2}                    # Back, aber nur knapp ueber Normal -> Fuehrung raus
        hi = dict(lo, inflow=base * BA.LEAD_PUSH_FACTOR + 1)   # ueber Extra-Schwelle -> bleibt
        self.assertEqual(BA._leader_gate([lo]), [])
        self.assertEqual(len(BA._leader_gate([hi])), 1)
        # Public: eigene (hoehere) Schwellen fliessen in den Gate ein
        self.assertEqual(BA._leader_gate([dict(lo, tier="top", inflow=BA.PUB_FRESH_TOP * 1.2)],
                                         BA.PUB_HT_TOP, BA.PUB_HT_REST, BA.PUB_FRESH_TOP, BA.PUB_FRESH_REST), [])
        self.assertEqual(len(BA._leader_gate([dict(lo, tier="top", inflow=BA.PUB_FRESH_TOP * BA.LEAD_PUSH_FACTOR + 1)],
                                             BA.PUB_HT_TOP, BA.PUB_HT_REST, BA.PUB_FRESH_TOP, BA.PUB_FRESH_REST)), 1)
        # HZ misst am gematchten Gesamt (total), nicht am Zufluss
        htlo = {"scenario": "ht", "tier": "rest", "onLeader": True, "leadDir": "in", "total": BA.HT_REST_EUR * 1.2}
        hthi = dict(htlo, total=BA.HT_REST_EUR * BA.LEAD_PUSH_FACTOR + 1)
        self.assertEqual(BA._leader_gate([htlo]), [])
        self.assertEqual(len(BA._leader_gate([hthi])), 1)

    def test_leader_gate_ignores_event_jump_back(self):
        # 08.08.2026 (Lucas): Fuehrungs-Geld mit 'in', aber die Quote sprang durch ein Tor -> Back-Lesart
        # kontaminiert -> raus (auch wenn Einsatz die Extra-Schwelle klar reisst).
        a = {"scenario": "fresh", "tier": "rest", "onLeader": True, "leadDir": "in",
             "inflow": BA.FRESH_REST_EUR * 5, "leadPrev": 2.0, "leadOdd": 1.2}
        self.assertEqual(BA._leader_gate([a]), [])
        a2 = dict(a, leadPrev=1.24, leadOdd=1.20)   # kleiner, echter Move -> dasselbe Geld geht durch
        self.assertEqual(len(BA._leader_gate([a2])), 1)

    def test_fuehrt_line(self):
        self.assertIn("führt", BA._fuehrt_line({"onLeader": True}))
        self.assertEqual(BA._fuehrt_line({}), "")


class TestDirection(unittest.TestCase):
    # 08.08.2026 (Lucas: „Back oder Lay?"): Quotenbewegung des Favoriten in den Push.
    def test_dir_line_back(self):
        line = BA._dir_line({"leadDir": "in", "leadPrev": 2.10, "leadOdd": 2.00})
        self.assertIn("Back", line); self.assertIn("2.10", line); self.assertIn("2.00", line)

    def test_dir_line_drift(self):
        self.assertIn("driftet", BA._dir_line({"leadDir": "out", "leadPrev": 2.00, "leadOdd": 2.20}))

    def test_dir_line_flat_or_missing_empty(self):
        self.assertEqual(BA._dir_line({"leadDir": "flat"}), "")
        self.assertEqual(BA._dir_line({}), "")

    def test_dir_line_event_jump_suppresses_verdict(self):
        # 08.08.2026 (Lucas, Viking 1.23->3.60 nach 1:1): grosser Sprung = Spielereignis, kein Flow.
        drift = BA._dir_line({"leadDir": "out", "leadPrev": 1.23, "leadOdd": 3.60})   # Gegentor -> Quote raus
        self.assertIn("neu gepreist", drift); self.assertNotIn("kein Back-Rückhalt", drift)
        shorten = BA._dir_line({"leadDir": "in", "leadPrev": 2.00, "leadOdd": 1.20})  # eigenes Tor -> Quote crasht
        self.assertIn("neu gepreist", shorten); self.assertNotIn("Back", shorten)     # kein falsches „Back"
        # kleiner, echter Move bleibt eindeutig lesbar
        self.assertIn("Back", BA._dir_line({"leadDir": "in", "leadPrev": 2.10, "leadOdd": 2.00}))
        self.assertIn("driftet", BA._dir_line({"leadDir": "out", "leadPrev": 2.00, "leadOdd": 2.20}))

    def test_attach_direction_joins(self):
        alerts = [{"matchId": "1", "market": "Match Odds", "leadName": "Napoli"}]
        direction = {"1": {"Match Odds": {"Napoli": {"dir": "in", "prev": 1.9, "odd": 1.8}}}}
        BA.attach_direction(alerts, direction)
        self.assertEqual(alerts[0]["leadDir"], "in")
        self.assertEqual(alerts[0]["leadPrev"], 1.9)

    def test_message_appends_back_line(self):
        a = {"scenario": "fresh", "matchId": "9", "flag": "🇮🇹", "home": "Napoli", "away": "Osasuna",
             "league": "Serie A", "market": "Match Odds", "inflow": 40000, "total": 100000,
             "tier": "top", "leadName": "Osasuna", "leadShare": 0.62, "leadOdd": 2.4,
             "leadDir": "in", "leadPrev": 2.55}
        self.assertIn("Back", BA.build_message(a))
        self.assertIn("Back", BA.build_public_message(a))


if __name__ == "__main__":
    unittest.main()
