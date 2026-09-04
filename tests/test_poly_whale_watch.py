#!/usr/bin/env python3
"""test_poly_whale_watch.py — Polymarket Whale-Watch (26.07.2026).
Sichert Sport-Mapping, Track-Record-Schwelle, Auswahl (Größe/Frische/Dedup/Aufstocken)
und den Telegram-sicheren Nachrichtenbau. Kein Modul-Level-Env (Audit-konform).

03.08.2026 (Lucas: „50% ist Münzwurf, kein Beweis"): „bewiesen"/smart heißt jetzt STATISTISCH
signifikant über 50% (Wilson-Untergrenze > 0.5), nicht bloß rohe Quote ≥50%. Die „smart"-Fixtures
tragen deshalb klar signifikante Bilanzen (z.B. 8/9, 15/20)."""
import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import poly_whale_watch as P

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
def _ts(dt): return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

def _pos(usd, league="TENNIS", side="Blockx", price=0.60, ageDays=0, wallet="0xabc123def456"):
    return {"wallet": wallet, "key": f"k-{side}", "side": side, "league": league,
            "firstPrice": price, "firstTs": _ts(NOW - timedelta(days=ageDays)), "usd": usd}


class TestSport(unittest.TestCase):
    def test_map(self):
        self.assertEqual(P._sport("ESPORTS")[0], "🎮")
        self.assertEqual(P._sport("TENNIS")[0], "🎾")
        self.assertEqual(P._sport("MLB")[0], "⚾")
        self.assertEqual(P._sport("soccer_mls")[0], "⚽")
        self.assertEqual(P._sport("SOMETHINGELSE"), ("🎯", "Somethingelse"))


class TestTrackRecord(unittest.TestCase):
    def test_too_thin_returns_none(self):
        self.assertIsNone(P.track_record({"0xa": {"n": 2, "wins": 2}}, "0xa"))

    def test_shows_hitrate(self):
        # track_record ist die NEUTRALE Faktenzeile (nicht das „bewiesen"-Label) → zeigt jede n≥MIN_TR-Bilanz
        tr = P.track_record({"0xa": {"n": 9, "wins": 6}}, "0xa")
        self.assertIn("6/9", tr); self.assertIn("67%", tr)

    def test_unknown_wallet(self):
        self.assertIsNone(P.track_record({}, "0xzz"))


class TestWilsonGate(unittest.TestCase):
    """03.08.2026 (Lucas: „24/47=51% ist kein Beweis"): „bewiesen" = signifikant über Münzwurf."""
    def test_coinflip_records_not_smart(self):
        self.assertFalse(P._is_smart({"n": 47, "wins": 24}))   # 51% — die reale Moutet-Wallet
        self.assertFalse(P._is_smart({"n": 11, "wins": 6}))    # 55% — Zhang-Wallet
        self.assertFalse(P._is_smart({"n": 16, "wins": 8}))    # 50% — Norrie-Wallet

    def test_clearly_above_coinflip_is_smart(self):
        self.assertTrue(P._is_smart({"n": 20, "wins": 15}))    # 75% bei n=20 → signifikant
        self.assertTrue(P._is_smart({"n": 9, "wins": 8}))      # 89% bei n=9 → signifikant

    def test_wilson_lb_monotone(self):
        # gleiche Quote, mehr Spiele → höhere Untergrenze (mehr Sicherheit)
        self.assertLess(P._wilson_lb(6, 8), P._wilson_lb(60, 80))


class TestSelect(unittest.TestCase):
    # Gestaffelt: ohne Record Schwelle $50k, mit Record (n≥8 & signifikant) $5k.
    def _tracked(self, wallet="0xREC"):
        return {"scores": {wallet: {"n": 9, "wins": 8}}}     # 89% → signifikant smart

    def test_untracked_below_25k_skipped(self):
        track = {"open": {"a": _pos(20000)}}          # groß, aber ohne Record < $25k
        self.assertEqual(P.select(track, {}, NOW), [])

    def test_untracked_big_included(self):
        track = {"open": {"a": _pos(60000)}}
        got = P.select(track, {}, NOW)
        self.assertEqual(len(got), 1); self.assertFalse(got[0][2])

    def test_tracked_wallet_lower_threshold(self):
        # dieselbe $6k-Position: mit signifikantem Record gemeldet, ohne Record verworfen
        pos = _pos(6000, wallet="0xREC")
        tracked = {"open": {"a": pos}}; tracked.update(self._tracked())
        self.assertEqual(len(P.select(tracked, {}, NOW)), 1)
        self.assertEqual(P.select({"open": {"a": _pos(6000, wallet="0xNOREC")}}, {}, NOW), [])

    def test_coinflip_wallet_no_low_threshold(self):
        # 03.08.2026: 24/47 (51%) ist NICHT smart → $6k verworfen (früher fälschlich gepusht)
        track = {"open": {"a": _pos(6000, wallet="0xCOIN")},
                 "scores": {"0xCOIN": {"n": 47, "wins": 24}}}
        self.assertEqual(P.select(track, {}, NOW), [])

    def test_bad_record_no_free_pass(self):
        # 0/4 (schlechter Record) bekommt NICHT die niedrige Schwelle → $6k verworfen
        track = {"open": {"a": _pos(6000, wallet="0xBAD")},
                 "scores": {"0xBAD": {"n": 4, "wins": 0}}}
        self.assertEqual(P.select(track, {}, NOW), [])
        # aber groß genug (≥$25k) kommt es trotzdem durch (reines Größen-Signal)
        big = {"open": {"a": _pos(60000, wallet="0xBAD")},
               "scores": {"0xBAD": {"n": 4, "wins": 0}}}
        self.assertEqual(len(P.select(big, {}, NOW)), 1)

    def test_stale_unseen_skipped(self):
        track = {"open": {"a": _pos(30000, ageDays=5)}}   # groß genug, aber 5 Tage alt
        self.assertEqual(P.select(track, {}, NOW), [])

    def test_already_seen_skipped(self):
        track = {"open": {"a": _pos(30000)}}
        seen = {"a": {"usd": 30000}}
        self.assertEqual(P.select(track, seen, NOW), [])

    def test_restock_realerts(self):
        track = {"open": {"a": _pos(65000)}}           # von 40000 → 65000 (≥ +50%, ≥ $50k)
        seen = {"a": {"usd": 40000}}
        got = P.select(track, seen, NOW)
        self.assertEqual(len(got), 1); self.assertTrue(got[0][2])

    def test_small_topup_not_realerted(self):
        track = {"open": {"a": _pos(30000)}}           # von 27000 → 30000 (< +50%)
        seen = {"a": {"usd": 27000}}
        self.assertEqual(P.select(track, seen, NOW), [])

    def test_sorted_by_size(self):
        track = {"open": {"a": _pos(30000, side="A"), "b": _pos(50000, side="B")}}
        got = P.select(track, {}, NOW)
        self.assertEqual(got[0][1]["side"], "B")   # größte zuerst


class TestBuildCard(unittest.TestCase):
    def test_core_fields_and_safe_tags(self):
        import re
        card = P.build_card(_pos(24000, league="MLB", side="Cleveland Guardians", price=0.46),
                            {}, restock=False)
        self.assertIn("Cleveland Guardians", card)
        self.assertIn("46¢", card)
        self.assertIn("⚾", card)
        self.assertIn("im Aufbau", card)          # neutral statt abschreckend
        bad = set(re.findall(r"</?([a-zA-Z0-9-]+)", card)) - {"b", "i", "a"}
        self.assertFalse(bad, f"verbotene Tags: {bad}")

    def test_wallet_is_clickable_profile_link(self):
        card = P.build_card(_pos(9000, wallet="0xabcdef1234567890abcd"), {}, False)
        self.assertIn('href="https://polymarket.com/profile/0xabcdef1234567890abcd"', card)
        self.assertIn("0xabcd…abcd", card)   # Kurz-ID bleibt als Linktext

    def test_coinflip_record_shown_as_neutral_bilanz(self):
        # 06.08.2026 (Lucas: „frueher stand der Track-Record oefter"): 24/47 (51%) ist kein Beweis,
        # wird aber ab n>=MIN_TR als NEUTRALE Bilanz gezeigt (nicht „bewiesen", nicht mehr versteckt).
        card = P.build_card(_pos(9000, wallet="0xc"), {"0xc": {"n": 47, "wins": 24}}, False)
        self.assertIn("Bilanz", card); self.assertIn("24/47", card); self.assertIn("51%", card)
        self.assertNotIn("bewiesene Wallet", card)
        self.assertNotIn("im Aufbau", card)

    def test_weak_record_shown_neutral(self):
        # schwache 1/3-Bilanz NICHT als abschreckende Zahl — neutral „im Aufbau"
        card = P.build_card(_pos(30000, wallet="0xw"), {"0xw": {"n": 3, "wins": 1}}, False)
        self.assertIn("im Aufbau", card)
        self.assertNotIn("33%", card)
        self.assertNotIn("1/3", card)

    def test_good_record_highlighted(self):
        # signifikanter Record (8/9 = 89%) → „bewiesene Wallet"
        card = P.build_card(_pos(9000, wallet="0xg"), {"0xg": {"n": 9, "wins": 8}}, False)
        self.assertIn("bewiesene Wallet", card); self.assertIn("8/9 richtig", card)

    def test_contrarian_hint_under_45c(self):
        self.assertIn("Außenseiter", P.build_card(_pos(9000, price=0.40), {}, False))
        self.assertNotIn("Außenseiter", P.build_card(_pos(9000, price=0.60), {}, False))

    def test_restock_header(self):
        self.assertIn("stockt auf", P.build_card(_pos(9000), {}, restock=True))


class TestPublicWhale(unittest.TestCase):
    """31.07.2026 (Lucas) — öffentlicher Whale-Watch: kuratiert (riesig ab $100K / bewährt ab $25K),
    nur Sport + sinnvoller Preis, Wallet-Qualität annotiert."""

    def test_pub_quality_filter(self):
        self.assertTrue(P._pub_ok(_pos(50000, league="TENNIS", price=0.60)))
        self.assertFalse(P._pub_ok(_pos(50000, league="Greater Manchester", price=0.60)))  # Politik → 🎯
        self.assertFalse(P._pub_ok(_pos(50000, league="TENNIS", price=1.00)))              # quasi-settled
        self.assertFalse(P._pub_ok(_pos(50000, league="TENNIS", price=0.01)))              # Dust

    def test_public_bands(self):
        track = {
            "open": {
                "k1": _pos(30000, side="A", wallet="0xSHARP"),   # bewährt+signifikant, $30K ≥ 25K → PASS
                "k2": _pos(30000, side="B", wallet="0xUNK"),     # unbekannt, $30K < 100K → SKIP
                "k3": _pos(120000, side="C", wallet="0xUNK2"),   # riesig, $120K ≥ 100K → PASS
            },
            "scores": {"0xSHARP": {"n": 20, "wins": 15, "clvSumPP": 40}},   # 75% → signifikant
        }
        cand = P.select(track, {}, NOW, P.PUB_MIN_USD_UNTRACKED, P.PUB_MIN_USD_TRACKED,
                        P.PUB_MIN_TR, P.PUB_MIN_HITRATE)
        keys = {c[0] for c in cand}
        self.assertIn("k1", keys)
        self.assertNotIn("k2", keys)
        self.assertIn("k3", keys)

    def test_public_card_proven(self):
        broad = {"k-Flamengo": {"shares": {"Flamengo": 100, "Palmeiras": 50}}}
        pos = _pos(150000, league="soccer_brasileirao", side="Flamengo", price=0.62, wallet="0xS")
        scores = {"0xS": {"n": 20, "wins": 15, "clvSumPP": 64}}   # 75%, signifikant, Ø CLV +3.2pp
        msg = P.build_public_card(pos, scores, False, broad)
        self.assertIn("Polymarket Whale", msg)
        self.assertIn("Flamengo v Palmeiras", msg)      # Paarung aus broad
        self.assertIn("$150K", msg)
        self.assertIn("62¢", msg)
        self.assertIn("bewiesen scharf", msg)
        self.assertIn("15/20 richtig (75%, +3.2pp CLV)", msg)

    def test_public_card_pnl_when_present(self):
        pos = _pos(150000, league="TENNIS", side="Sinner", price=0.55, wallet="0xP")
        scores = {"0xP": {"n": 12, "wins": 10, "clvSumPP": 24, "pnl": 120000}}   # 83% → signifikant
        msg = P.build_public_card(pos, scores, False, {})
        self.assertIn("+$120", msg)   # Lifetime-P&L, sobald der Runner sie zieht
        self.assertIn("lifetime", msg)

    def test_public_card_unproven_neutral(self):
        pos = _pos(120000, league="NBA", side="Celtics", price=0.58, wallet="0xNEW")
        msg = P.build_public_card(pos, {}, False, {})
        self.assertIn("Track-Record noch im Aufbau", msg)
        self.assertNotIn("bewiesen scharf", msg)


class TestConfirmedLoserGate(unittest.TestCase):
    """02.08.2026 (Lucas): eine hohe Trefferquote bei bestätigtem Lifetime-Verlust ist kein Schärfe-
    Beweis (real: 88% Treffer, −$7 Mio). 03.08.2026: obendrein muss die Quote SIGNIFIKANT über 50%
    liegen (Wilson), nicht bloß roh ≥50%."""

    def test_is_smart_predicate(self):
        self.assertTrue(P._is_smart({"n": 9, "wins": 8}))                      # 89%, signifikant → smart
        self.assertTrue(P._is_smart({"n": 9, "wins": 8, "pnl": 1200}))         # profitabel → smart
        self.assertFalse(P._is_smart({"n": 9, "wins": 8, "pnl": -25576}))      # bestätigter Verlierer → NICHT
        self.assertFalse(P._is_smart({"n": 5, "wins": 5}))                     # zu dünn (n<8) trotz 100%
        self.assertFalse(P._is_smart({"n": 47, "wins": 24}))                   # 51% = Münzwurf → NICHT
        self.assertFalse(P._is_smart({"n": 9, "wins": 3}))                     # 33% → NICHT

    def test_confirmed_loser_filtered_entirely(self):
        # 02.08.2026 (Lucas: „ganz rausfiltern"): −$25.576 lifetime → weder als $6k noch als $60k-Whale.
        sc = {"0xLOSS": {"n": 31, "wins": 24, "pnl": -25576}}   # 77% (signifikant) ABER Verlierer
        self.assertEqual(P.select({"open": {"a": _pos(6000, wallet="0xLOSS")}, "scores": sc}, {}, NOW), [])
        self.assertEqual(P.select({"open": {"a": _pos(60000, wallet="0xLOSS")}, "scores": sc}, {}, NOW), [])

    def test_profitable_and_unknown_still_smart(self):
        prof = {"open": {"a": _pos(6000, wallet="0xWIN")},
                "scores": {"0xWIN": {"n": 8, "wins": 7, "pnl": 4200}}}          # 87.5% + profitabel
        self.assertEqual(len(P.select(prof, {}, NOW)), 1)                       # → niedrige Schwelle
        unk = {"open": {"a": _pos(6000, wallet="0xUNK")},
               "scores": {"0xUNK": {"n": 8, "wins": 7}}}                        # signifikant, pnl unbekannt → smart
        self.assertEqual(len(P.select(unk, {}, NOW)), 1)

    def test_label_not_bewiesen_for_loser(self):
        sc = {"0xLOSS": {"n": 31, "wins": 24, "pnl": -25576}}
        self.assertNotIn("bewiesene", P._wallet_line(sc, "0xLOSS"))            # Trades-Label ehrlich
        self.assertNotIn("bewiesen scharf", P._pub_wallet_line(sc, "0xLOSS"))  # Public-Label ehrlich


class TestSharpMerge(unittest.TestCase):
    """05.08.2026 (Lucas: die alte 'Sharp im Markt'-Liste war wertlos - 56%-Tennis 6x gespammt).
    Der bewiesen-scharfe FRISCHE Einstieg wird jetzt hier mitgezogen: Klein-aber-scharf-Band unter
    dem Smart-Boden (nur mit sharp_floor), aber nur solange handelbar; strenges _is_smart-Gate
    (56%-Wallet fliegt); je Wallet nur eine Karte; Badge sagt warum die Karte kommt."""
    SMART = {"0xREC": {"n": 9, "wins": 8}}          # 89% -> signifikant smart
    NOTSMART = {"0xTN": {"n": 18, "wins": 10}}      # 56% -> NICHT smart (Wilson)

    def test_klein_aber_scharf_nur_mit_sharp_floor(self):
        t = {"open": {"a": _pos(2500, wallet="0xREC")}, "scores": self.SMART}
        self.assertEqual(P.select(t, {}, NOW), [])                                  # $2.5K < Smart-Boden $5K
        self.assertEqual(len(P.select(t, {}, NOW, sharp_floor=P.MIN_USD_SHARP)), 1) # Band greift

    def test_56prozent_wallet_ist_nicht_scharf(self):
        t = {"open": {"a": _pos(2500, wallet="0xTN")}, "scores": self.NOTSMART}
        self.assertEqual(P.select(t, {}, NOW, sharp_floor=P.MIN_USD_SHARP), [])     # genau der alte Muell

    def test_handelbarkeits_gate(self):
        run = _pos(2500, wallet="0xREC"); run["lastPrice"] = 0.74                   # 60c -> 74c gelaufen
        self.assertEqual(P.select({"open": {"a": run}, "scores": self.SMART}, {}, NOW,
                                   sharp_floor=P.MIN_USD_SHARP), [])                 # Zug weg -> raus
        chp = _pos(2500, wallet="0xREC"); chp["lastPrice"] = 0.57                   # guenstiger
        self.assertEqual(len(P.select({"open": {"a": chp}, "scores": self.SMART}, {}, NOW,
                                      sharp_floor=P.MIN_USD_SHARP)), 1)

    def test_dedup_je_wallet(self):
        cand = [("k1", _pos(9000, side="A"), False), ("k2", _pos(8000, side="B"), False),
                ("k3", _pos(7000, side="C"), False)]
        kept, extras = P._dedup_by_wallet(cand, 1)
        self.assertEqual(len(kept), 1); self.assertEqual(extras.get("k1"), 2)

    def test_badges(self):
        self.assertIn("bewiesen scharf", P.build_card(_pos(60000, wallet="0xREC"), self.SMART, False))   # Wal+Feuer
        self.assertIn("Scharfe Wallet frisch drin", P.build_card(_pos(2500, wallet="0xREC"), self.SMART, False))
        self.assertIn("weitere Position", P.build_card(_pos(60000, wallet="0xREC"), self.SMART, False, extra=3))


class TestPublicRecordAndTighten(unittest.TestCase):
    """06.08.2026 (Lucas: „frueher stand der Track-Record oefter" + „Feed straffen"): Wallets mit
    belastbarem Record (n>=8) zeigen die rohe Bilanz als neutrale Zeile (nicht nur die bewiesenen);
    grosse Wallets OHNE Record kommen nur ab PUB_MIN_USD_NOREC in den Public-Feed."""

    def test_bilanz_zeile_fuer_record_nicht_nur_bewiesen(self):
        # bewiesen (8/9, signifikant) -> die scharf-Zeile
        self.assertIn("bewiesen scharf", P._pub_wallet_line({"w": {"n": 9, "wins": 8, "clvSumPP": 18}}, "w"))
        # Record n>=8 aber NICHT signifikant (52%) -> neutrale Bilanz statt „im Aufbau"
        line = P._pub_wallet_line({"w": {"n": 83, "wins": 43, "clvSumPP": 25}}, "w")
        self.assertIn("Bilanz", line); self.assertIn("43/83", line); self.assertIn("52%", line)
        self.assertNotIn("bewiesen scharf", line)
        self.assertNotIn("im Aufbau", line)

    def test_duenner_record_bleibt_im_aufbau(self):
        self.assertIn("im Aufbau", P._pub_wallet_line({"w": {"n": 4, "wins": 3}}, "w"))

    def test_bestaetigter_verlierer_keine_schmeichel_bilanz(self):
        # 24/31 = 77% aber Netto-Verlierer -> KEINE flotte Bilanz-Zeile (Guard)
        line = P._pub_wallet_line({"0xLOSS": {"n": 31, "wins": 24, "pnl": -25576}}, "0xLOSS")
        self.assertNotIn("77%", line); self.assertIn("im Aufbau", line)

    def test_pub_keep_nur_bewiesen_scharf(self):
        # 13.08.2026 (Lucas): Public NUR bewiesen scharf — Record allein reicht NICHT mehr, Groesse
        # ohne Beweis auch nicht. Grosse-aber-unbewiesene Wallets bleiben im Trades-Channel.
        sc = {"sharp": {"n": 20, "wins": 15, "clvSumPP": 40},   # 75% + pos CLV -> bewiesen scharf
              "flat":  {"n": 30, "wins": 16},                    # 53% n=30 -> nicht signifikant
              "new":   {"n": 3, "wins": 2}}                      # zu duenn
        self.assertTrue(P._pub_keep({"wallet": "sharp", "usd": 26000}, sc))   # bewiesen -> rein
        self.assertFalse(P._pub_keep({"wallet": "flat", "usd": 60000}, sc))   # Record aber nicht scharf -> raus
        self.assertFalse(P._pub_keep({"wallet": "new", "usd": P.PUB_MIN_USD_NOREC}, sc))  # unbewiesen egal wie gross -> raus


class TestClvGate(unittest.TestCase):
    """12.08.2026 (Lucas): hohe Trefferquote OHNE positiven CLV = Glueck, kein Edge. Die reale
    Tennis-Wallet (7/9 = 78% aber Ø CLV negativ, lebenslang -70K) darf NICHT 'bewiesen' sein."""

    def test_negative_clv_not_smart(self):
        self.assertFalse(P._is_smart({"n": 9, "wins": 7, "clvSumPP": -0.59}))   # reale Tennis-Wallet
        self.assertFalse(P._is_smart({"n": 20, "wins": 15, "clvSumPP": -5}))    # gute Quote, neg CLV

    def test_nonneg_clv_bleibt_smart(self):
        self.assertTrue(P._is_smart({"n": 20, "wins": 15, "clvSumPP": 40}))     # 75% + pos CLV
        self.assertTrue(P._is_smart({"n": 9, "wins": 8}))                        # CLV fehlt -> 0 -> bleibt smart

    def test_negative_clv_label_nicht_bewiesen(self):
        line = P._wallet_line({"0xT": {"n": 9, "wins": 7, "clvSumPP": -0.59}}, "0xT")
        self.assertNotIn("bewiesene Wallet", line)   # kein Schmeichel-Label
        self.assertIn("Bilanz", line)                # faellt auf neutrale Bilanz

    def test_bewiesen_label_zeigt_clv(self):
        line = P._wallet_line({"0xA": {"n": 20, "wins": 15, "clvSumPP": 40}}, "0xA")
        self.assertIn("bewiesene Wallet", line)
        self.assertIn("pp CLV", line)                # Skill-Metrik sichtbar im Trades-Badge


class TestContestedMarket(unittest.TestCase):
    """12.08.2026 (Lucas): umkaempfte Spiele (Gross-Geld auf beiden Seiten) fliegen aus dem Public."""

    BROAD = {
        "cs2-fal2-k271": {"whales": [
            {"side": "Team Falcons", "usd": 415853}, {"side": "K27", "usd": 203675},
            {"side": "Team Falcons", "usd": 42911}]},
        "einseitig": {"whales": [
            {"side": "A", "usd": 300000}, {"side": "B", "usd": 8000}]},
        "leer": {"whales": []},
    }

    def test_beide_seiten_gross_ist_umkaempft(self):
        self.assertTrue(P._contested_market("cs2-fal2-k271", self.BROAD))

    def test_einseitig_nicht_umkaempft(self):
        self.assertFalse(P._contested_market("einseitig", self.BROAD))   # nur eine Seite >= 100K

    def test_leer_oder_unbekannt_nicht_umkaempft(self):
        self.assertFalse(P._contested_market("leer", self.BROAD))
        self.assertFalse(P._contested_market("gibtsnicht", self.BROAD))
        self.assertFalse(P._contested_market("x", None))


if __name__ == "__main__":
    unittest.main()


class TestSelectSubBreakeven(unittest.TestCase):
    """13.08.2026 (Lucas): grosse Wallet mit belastbarem, aber unterdurchschnittlichem Record (<50% Treffer)
    loest keine reine Groessen-Karte mehr aus - auch nicht Trades. Unbekannte + bewiesen scharfe bleiben."""

    def test_belegte_sub50_raus_unbekannt_und_scharf_bleiben(self):
        from datetime import datetime, timezone
        now = datetime(2026, 8, 13, tzinfo=timezone.utc)
        track = {"open": {
            "loser|k1|home":   {"wallet": "loser",   "key": "k1", "side": "home", "usd": 90000, "firstTs": now.isoformat()},
            "unknown|k2|home": {"wallet": "unknown", "key": "k2", "side": "home", "usd": 90000, "firstTs": now.isoformat()},
            "sharp|k3|home":   {"wallet": "sharp",   "key": "k3", "side": "home", "usd": 6000,  "firstTs": now.isoformat()}},
            "scores": {"loser": {"n": 34, "wins": 16}, "unknown": {"n": 2, "wins": 1},
                       "sharp": {"n": 61, "wins": 40, "clvSumPP": 85}}}
        picks = {p[0] for p in P.select(track, {}, now, sharp_floor=P.MIN_USD_SHARP)}
        self.assertNotIn("loser|k1|home", picks)
        self.assertIn("unknown|k2|home", picks)
        self.assertIn("sharp|k3|home", picks)


class TestPubMinOdds(unittest.TestCase):
    # 22.08.2026 (Lucas): Public-Whale nur bei Mindest-Quote >=1.30 (Einstieg/Jetzt <= ~0.769).
    def test_short_favourite_rejected(self):
        self.assertFalse(P._pub_min_odds_ok(_pos(50000, price=0.86)))   # Odds ~1.16 -> raus
        self.assertFalse(P._pub_min_odds_ok(_pos(50000, price=0.80)))   # Odds 1.25 -> raus

    def test_ok_at_or_above_min_odds(self):
        self.assertTrue(P._pub_min_odds_ok(_pos(50000, price=0.769)))   # ~1.30 Grenze
        self.assertTrue(P._pub_min_odds_ok(_pos(50000, price=0.60)))    # 1.67
        self.assertTrue(P._pub_min_odds_ok(_pos(50000, price=0.30)))    # Aussenseiter 3.33 -> bleibt

    def test_current_price_drifted_short_rejected(self):
        pos = _pos(50000, price=0.70)   # Einstieg 1.43 ok
        pos["lastPrice"] = 0.90         # aber jetzt 1.11 -> zu kurz
        self.assertFalse(P._pub_min_odds_ok(pos))

    def test_bad_price_rejected(self):
        self.assertFalse(P._pub_min_odds_ok({"firstPrice": None}))


class TestPubSeiteBenennbar(unittest.TestCase):
    """04.09.2026 — Lucas' Zwei-Wochen-Bilanz war 12:2, unser Buch sagte 13:1.

    Die eine Abweichung ist Leeds–Brentford am 30.08. Der Push lautete „💰 $41K auf Over" und das
    Spiel endete 1:1. Over WAS? Der Markt war `epl-lee-bre-2026-08-30-more-markets`, ein
    Totals-Markt ohne erfasste Linie: bei 1:1 gewinnt Over 1,5 und verliert Over 2,5. Lucas hat
    ihn als Verlust gebucht, unsere Aufloesung als Treffer — und keiner von beiden konnte es
    wissen, weil in poly_money_broad_close.json bei allen 2000 Maerkten `title`/`question` fehlt.

    Ein Tipp, dem der Leser nicht folgen und den er nicht nachpruefen kann, gehoert nicht in den
    oeffentlichen Kanal.
    """

    def test_der_reale_fall_geht_nicht_mehr_raus(self):
        self.assertFalse(P._pub_seite_benennbar(
            {"key": "epl-lee-bre-2026-08-30-more-markets", "side": "Over"}))

    def test_alle_generischen_ausgaenge_fallen_raus(self):
        for seite in ("Over", "under", "Yes", "NO", "Ja", "Nein", "Draw", "Unentschieden", "Tie", "Über"):
            self.assertFalse(P._pub_seite_benennbar({"side": seite}), seite)

    def test_ein_team_oder_spielername_bleibt(self):
        for seite in ("Leeds United FC", "MIBR", "Alexandra Eala", "Brighton & Hove Albion FC"):
            self.assertTrue(P._pub_seite_benennbar({"side": seite}), seite)

    def test_fehlende_seite_ist_keine_erlaubnis(self):
        self.assertFalse(P._pub_seite_benennbar({}))
        self.assertFalse(P._pub_seite_benennbar({"side": None}))
        self.assertFalse(P._pub_seite_benennbar({"side": "  "}))

    def test_die_sperre_haengt_an_der_seite_nicht_am_slug(self):
        """Ein „-more-markets"-Markt mit einem echten Ausgang (z. B. Torschuetze) bleibt drin —
        gesperrt wird, was unlesbar ist, nicht was einen bestimmten Slug hat."""
        self.assertTrue(P._pub_seite_benennbar(
            {"key": "epl-lee-bre-2026-08-30-more-markets", "side": "Kevin Schade"}))


class TestTop20RankBadge(unittest.TestCase):
    # 23.08.2026 (Lucas): Top-20-Wallets im Trades-Push extra markieren (Rang der Sharp-Rangliste).
    def _scores(self):
        # 3 Wallets ueber $1000 Ø-Einsatz, alle mit P&L (Modus A) + 1 Klein-Wallet (Ø $200 -> raus)
        return {
            "0xAAA": {"n": 20, "wins": 12, "clvSumPP": 20, "usd": 40000, "pnl": 500000},  # #1
            "0xBBB": {"n": 20, "wins": 12, "clvSumPP": 20, "usd": 40000, "pnl": 200000},  # #2
            "0xCCC": {"n": 20, "wins": 12, "clvSumPP": 20, "usd": 40000, "pnl":  90000},  # #3
            "0xTINY": {"n": 20, "wins": 12, "clvSumPP": 20, "usd": 4000, "pnl": 999999},  # Ø $200 -> NICHT gelistet
        }

    def test_rank_map_matches_pnl_order_and_size_filter(self):
        rmap = P._sharp_rank_map(self._scores())
        self.assertEqual(rmap.get("0xaaa"), 1)
        self.assertEqual(rmap.get("0xbbb"), 2)
        self.assertEqual(rmap.get("0xccc"), 3)
        self.assertIsNone(rmap.get("0xtiny"))   # Klein-Einsatz raus trotz Top-P&L

    def test_badge_present_for_top_wallet(self):
        b = P._rank_badge(self._scores(), "0xAAA")
        self.assertIsNotNone(b)
        self.assertIn("Rang #1", b)
        self.assertIn("Top-20", b)

    def test_no_badge_for_untracked_wallet(self):
        self.assertIsNone(P._rank_badge(self._scores(), "0xDEAD"))
        self.assertIsNone(P._rank_badge(self._scores(), "0xTINY"))

    def test_card_carries_badge(self):
        pos = {"wallet": "0xAAA", "league": "ESPORTS", "side": "X", "key": "k", "usd": 25000, "firstPrice": 0.6}
        card = P.build_card(pos, self._scores(), restock=False, broad={})
        self.assertIn("Rang #1", card)


class TestPublicTopN(unittest.TestCase):
    # 23.08.2026 (Lucas): Public postet NUR die Top-N (Default 10) der Sharp-Rangliste, mit Rang-Badge.
    def _scores(self):
        s = {}
        # 12 qualifizierende Wallets ($2K Ø, P&L absteigend) -> Rang 1..12
        for i in range(12):
            s["0x%02d" % i] = {"n": 20, "wins": 13, "clvSumPP": 20, "usd": 40000, "pnl": 1_000_000 - i * 10_000}
        return s

    def test_top10_in_gate_11th_out(self):
        sc = self._scores()
        self.assertTrue(P._pub_in_top_n(sc, "0x00"))    # Rang 1
        self.assertTrue(P._pub_in_top_n(sc, "0x09"))    # Rang 10
        self.assertFalse(P._pub_in_top_n(sc, "0x10"))   # Rang 11 -> raus
        self.assertFalse(P._pub_in_top_n(sc, "0xDEAD"))

    def test_public_card_shows_top10_badge(self):
        sc = self._scores()
        pos = {"wallet": "0x00", "league": "ESPORTS", "side": "X", "key": "k", "usd": 41000, "firstPrice": 0.62}
        card = P.build_public_card(pos, sc, restock=False, broad={})
        self.assertIn("Top-10-Wallet", card)
        self.assertIn("Rang #1", card)

    def test_public_card_no_badge_for_outside_topn(self):
        sc = self._scores()
        pos = {"wallet": "0x10", "league": "ESPORTS", "side": "X", "key": "k", "usd": 41000, "firstPrice": 0.62}
        card = P.build_public_card(pos, sc, restock=False, broad={})
        self.assertNotIn("Top-10-Wallet", card)


# ── Konflikt zwischen Top-Wallets im Push (24.08.2026, Lucas' INOX-Fall) ─────
# Zwei bewiesene Wallets auf Gegenseiten desselben Markts gingen als ZWEI sich widersprechende
# Push raus (#7 auf INOX, #9 auf Butterfly), ohne sich zu erwaehnen. `_contested_market` fing das
# nicht: das misst DOLLAR (>=$100K je Seite) und laeuft nur im Public-Kanal — $8,5K gegen $7K
# segelt durch. Hier zaehlt der RANG, damit auch kleine Gegeneinstiege bewiesener Wallets auffallen.
class TestConflictingTopWallet(unittest.TestCase):
    def _scores(self):
        return {
            "0xAAA": {"n": 20, "wins": 12, "clvSumPP": 20, "usd": 40000, "pnl": 500000},  # #1
            "0xBBB": {"n": 20, "wins": 12, "clvSumPP": 20, "usd": 40000, "pnl": 200000},  # #2
            "0xCCC": {"n": 20, "wins": 12, "clvSumPP": 20, "usd": 40000, "pnl":  90000},  # #3
            "0xTINY": {"n": 20, "wins": 12, "clvSumPP": 20, "usd": 4000, "pnl": 999999},  # ungerankt
        }

    def _broad(self, whales):
        return {"k1": {"whales": whales}}

    def _pos(self, wallet="0xAAA", side="INOX", key="k1"):
        return {"wallet": wallet, "key": key, "side": side, "league": "ESPORTS",
                "usd": 8500, "firstPrice": 0.55}

    def test_findet_gegenseite(self):
        b = self._broad([{"wallet": "0xccc", "side": "Butterfly", "usd": 7000}])
        cf = P._conflicting_top_wallet(self._pos(), b, self._scores())
        self.assertEqual(cf["rank"], 3)
        self.assertEqual(cf["side"], "Butterfly")
        self.assertEqual(cf["usd"], 7000.0)

    def test_bestplatzierte_gegenseite_gewinnt(self):
        # Mehrere Gegner -> der BESTE Rang zaehlt, nicht der groesste Einsatz.
        b = self._broad([{"wallet": "0xccc", "side": "Butterfly", "usd": 90000},
                         {"wallet": "0xbbb", "side": "Butterfly", "usd": 300}])
        cf = P._conflicting_top_wallet(self._pos(), b, self._scores())
        self.assertEqual(cf["rank"], 2)

    def test_gleiche_seite_ist_kein_konflikt(self):
        b = self._broad([{"wallet": "0xccc", "side": "INOX", "usd": 7000}])
        self.assertIsNone(P._conflicting_top_wallet(self._pos(), b, self._scores()))

    def test_eigene_wallet_zaehlt_nicht(self):
        # Dieselbe Wallet auf mehreren Ausgaengen (z.B. Exact-Score-Maerkte) ist kein Widerspruch.
        b = self._broad([{"wallet": "0xaaa", "side": "Butterfly", "usd": 7000}])
        self.assertIsNone(P._conflicting_top_wallet(self._pos(), b, self._scores()))

    def test_ungerankte_wallet_zaehlt_nicht(self):
        b = self._broad([{"wallet": "0xtiny", "side": "Butterfly", "usd": 7000},
                         {"wallet": "0xdead", "side": "Butterfly", "usd": 90000}])
        self.assertIsNone(P._conflicting_top_wallet(self._pos(), b, self._scores()))

    def test_rang_ausserhalb_top_n_zaehlt_nicht(self):
        b = self._broad([{"wallet": "0xccc", "side": "Butterfly", "usd": 7000}])
        self.assertIsNone(P._conflicting_top_wallet(self._pos(), b, self._scores(), top=2))
        self.assertIsNotNone(P._conflicting_top_wallet(self._pos(), b, self._scores(), top=3))

    def test_kleiner_einsatz_greift_trotzdem(self):
        # Genau Lucas' Fall: $7K haette `_contested_market` (>=$100K) nie ausgeloest.
        b = self._broad([{"wallet": "0xccc", "side": "Butterfly", "usd": 7000}])
        self.assertFalse(P._contested_market("k1", b))
        self.assertIsNotNone(P._conflicting_top_wallet(self._pos(), b, self._scores()))

    def test_kaputte_daten_werfen_nicht(self):
        sc = self._scores()
        self.assertIsNone(P._conflicting_top_wallet({}, self._broad([]), sc))
        self.assertIsNone(P._conflicting_top_wallet(self._pos(), None, sc))
        self.assertIsNone(P._conflicting_top_wallet(self._pos(), {"k1": "kaputt"}, sc))
        self.assertIsNone(P._conflicting_top_wallet(self._pos(key="andere"), self._broad(
            [{"wallet": "0xccc", "side": "Butterfly", "usd": 7000}]), sc))
        self.assertIsNone(P._conflicting_top_wallet(self._pos(), self._broad(
            ["kaputt", {"side": "Butterfly"}, {"wallet": "0xccc"}]), sc))

    def test_trades_card_zeigt_warnzeile(self):
        b = self._broad([{"wallet": "0xccc", "side": "Butterfly", "usd": 7000}])
        card = P.build_card(self._pos(), self._scores(), restock=False, broad=b)
        self.assertIn("Rang #3", card)
        self.assertIn("Gegenseite", card)
        self.assertIn("Butterfly", card)

    def test_trades_card_ohne_konflikt_ohne_zeile(self):
        card = P.build_card(self._pos(), self._scores(), restock=False, broad=self._broad([]))
        self.assertNotIn("Gegenseite", card)
        # und ohne broad ueberhaupt (Default None) faellt die Card nicht um
        self.assertNotIn("Gegenseite", P.build_card(self._pos(), self._scores(), restock=False))


# ── Gesperrte Sportarten im Push (25.08.2026, Lucas) ─────────────────────────
# „Haben wir MLB nicht gestern entfernt? Kriegs weiter im Trades-Channel." Gesperrt waren nur drei
# Stellen, alle im Frontend. poly_whale_watch kannte die Liste gar nicht — der zweite oeffentliche
# Pfad blieb offen. Lucas' Wahl: Public sperren, Trades mit Hinweis.
class TestSportCategory(unittest.TestCase):
    def test_us_sport_und_kampfsport(self):
        for lg in ("MLB", "NBA", "WNBA", "NFL", "NHL", "NCAAF"):
            self.assertEqual(P.sport_category(lg), "US-Sport", lg)
        for lg in ("UFC", "MMA", "Boxing"):
            self.assertEqual(P.sport_category(lg), "Kampfsport", lg)

    def test_spezifische_vor_fussball(self):
        # „Championship" ist ein Fussball-Begriff — er darf E-Sport/Tennis nicht wegschnappen.
        self.assertEqual(P.sport_category("ESPORTS"), "E-Sport")
        self.assertEqual(P.sport_category("LoL Championship"), "E-Sport")
        self.assertEqual(P.sport_category("ATP"), "Tennis")
        self.assertEqual(P.sport_category("EFL Championship"), "Fußball")

    def test_fussball_breit(self):
        for lg in ("SOCCER", "EPL", "DENMARK-SUPERLIGA", "LA-LIGA-2", "Bundesliga", "MLS"):
            self.assertEqual(P.sport_category(lg), "Fußball", lg)

    def test_gestempelter_sport_hat_vorrang(self):
        # Wie im Dashboard: das Capture kennt abgekuerzte Bewerbe, die kein Regex erraet.
        self.assertEqual(P.sport_category("AZE1", sport="Fußball"), "Fußball")

    def test_unbekannt_ist_sonstige(self):
        self.assertEqual(P.sport_category("Quidditch"), "Sonstige")
        self.assertEqual(P.sport_category(None), "Sonstige")

    def test_vokabular_deckt_sich_mit_dem_dashboard(self):
        """Der eigentliche Drift-Schutz: beide Mapper muessen DIESELBEN Kategorienamen liefern.

        Die Sperrliste kommt aus poly-wallets.js. Haette Python hier „Fussball" (ohne ß) geschrieben,
        waere die Sperre fuer Fussball stumm nie gegriffen — kein Fehler, kein Log, nur ein Loch.
        """
        import re
        js = open(Path(__file__).parent.parent / "poly-wallets.js",
                  encoding="utf-8").read()
        block = re.search(r"const _PW_CAT_ICON=\{(.*?)\};", js, re.S).group(1)
        js_cats = set(re.findall(r"'([^']+)':", block))
        py_cats = {c for c, _ in P._CAT_RULES} | {"Fußball", "Sonstige"}
        self.assertEqual(py_cats, js_cats)


class TestBlockedCats(unittest.TestCase):
    def test_liste_kommt_aus_dem_papier_depot(self):
        self.assertEqual(P.blocked_cats({"blockedCats": ["US-Sport", "Golf"]}), ["US-Sport", "Golf"])

    def test_fallback_wenn_datei_fehlt_oder_leer(self):
        for bad in ({}, None, {"blockedCats": []}, {"blockedCats": "kaputt"}, "kaputt"):
            self.assertEqual(P.blocked_cats(bad), list(P.BLOCKED_FALLBACK))

    def test_bet_blocked(self):
        cats = ["US-Sport", "Kampfsport"]
        self.assertTrue(P.bet_blocked({"league": "MLB"}, cats))
        self.assertTrue(P.bet_blocked({"league": "UFC"}, cats))
        self.assertFalse(P.bet_blocked({"league": "ESPORTS"}, cats))
        self.assertFalse(P.bet_blocked({"league": "EPL"}, cats))
        self.assertFalse(P.bet_blocked(None, cats))
        self.assertFalse(P.bet_blocked("kaputt", cats))

    def test_umgelegte_sperre_zieht_durch(self):
        # Legt Lucas die Sperre im Dashboard um, muss der Push mitziehen — ohne Code-Aenderung.
        self.assertTrue(P.bet_blocked({"league": "ATP"}, P.blocked_cats({"blockedCats": ["Tennis"]})))
        self.assertFalse(P.bet_blocked({"league": "MLB"}, P.blocked_cats({"blockedCats": ["Tennis"]})))


class TestBlockedCard(unittest.TestCase):
    def _sc(self):
        return {"0xA": {"n": 27, "wins": 18, "clvSumPP": 2.7, "usd": 60000, "pnl": 500000}}

    def _pos(self, league="MLB"):
        return {"wallet": "0xA", "key": "k1", "side": "Cleveland Guardians", "league": league,
                "usd": 4000, "firstPrice": 0.61}

    def test_gesperrte_sportart_traegt_den_hinweis(self):
        card = P.build_card(self._pos(), self._sc(), restock=False, broad={},
                            blocked=["US-Sport", "Kampfsport"])
        self.assertIn("nicht bespielbar", card)
        self.assertIn("Beobachtung", card)
        # Der Hinweis gehoert nach OBEN, nicht ans Ende — sonst liest man erst die Empfehlung.
        self.assertLess(card.index("nicht bespielbar"), card.index("💰"))

    def test_freie_sportart_ohne_hinweis(self):
        card = P.build_card(self._pos("ESPORTS"), self._sc(), restock=False, broad={},
                            blocked=["US-Sport", "Kampfsport"])
        self.assertNotIn("nicht bespielbar", card)

    def test_ohne_blocked_parameter_greift_der_fallback(self):
        # build_card wird auch aus Tests/Skripten ohne Liste gerufen — die Sperre darf nicht ausfallen.
        self.assertIn("nicht bespielbar", P.build_card(self._pos(), self._sc(), False, {}))

