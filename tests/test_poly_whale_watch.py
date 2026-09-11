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

# Eine Wallet, die `sharp_gate.is_sharp` besteht: n=60, 40 Treffer (Wilson-UG ~57 %), CLV positiv,
# kein bestaetigter Verlierer. Steht hier einmal, damit nicht jede Fixture ihre eigene erfindet.
SHARP = {"n": 60, "wins": 40, "clvSumPP": 30.0, "pnl": 12000}
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
        # 10.09.2026 (Lucas: „Trades-Channel lassen wir alles wie es ist"): die Wallet-Bilanz
        # und der Cent-Preis leben ab jetzt in der TRADES-Karte. Der Public-Kanal zeigt Spiel,
        # Rang, Betrag und die Quote — mehr nicht. Beide Zusicherungen bleiben, nur an der
        # richtigen Karte.
        msg = P.build_public_card(pos, scores, False, broad)
        self.assertIn("Polymarket Whale", msg)
        self.assertIn("Flamengo v Palmeiras", msg)      # Paarung aus broad
        self.assertIn("$150K", msg)
        self.assertIn("Einstieg @1.61", msg)            # Quote statt 62¢
        trades = P.build_card(pos, scores, False, broad)
        self.assertIn("bewiesen scharf", trades)
        self.assertIn("15/20 richtig, 75%", trades)
        self.assertIn("+3.2pp CLV", trades)

    def test_public_card_pnl_when_present(self):
        pos = _pos(150000, league="TENNIS", side="Sinner", price=0.55, wallet="0xP")
        scores = {"0xP": {"n": 12, "wins": 10, "clvSumPP": 24, "pnl": 120000}}   # 83% → signifikant
        msg = P.build_public_card(pos, scores, False, {})
        # 10.09.2026 (Lucas): die Lebensbilanz gehoert in den Trades-Kanal. Im Public steht sie
        # nicht mehr — halb gezeigt waere sie schlechter als gar nicht.
        self.assertIn("+$120", P.build_card(pos, scores, False, {}))
        self.assertNotIn("lifetime", msg)

    def test_die_public_karte_traegt_den_markt_link(self):
        """10.09.2026 (Lucas: „bitte wieder den Markt rein … ist userfreundlicher").

        Beim Kuerzen der Karte heute frueh ist der Link mit rausgeflogen. Er gehoert zurueck,
        und zwar aus einem Grund, der die Kuerzung ueberlebt: alles andere auf der Karte ist
        eine Behauptung von uns — Rang, Marktanteil, Quote. Der Link ist das Einzige, womit ein
        fremder Leser sie nachpruefen kann.
        """
        pos = _pos(150000, league="TENNIS", side="Sinner", price=0.55, wallet="0xP")
        msg = P.build_public_card(pos, {}, False, {})
        self.assertIn('href="https://polymarket.com/event/', msg)
        self.assertIn("Markt ansehen", msg)
        # Er steht am ENDE — die Karte fuehrt mit dem Spiel, nicht mit einem Link.
        self.assertTrue(msg.rstrip().endswith("</a>"), msg[-80:])

    def test_ohne_key_steht_kein_kaputter_link_da(self):
        """Fehlende Information rendert als nichts. Ein Link auf
        `polymarket.com/event/None` waere schlimmer als kein Link."""
        msg = P.build_public_card({"usd": 90000, "league": "TENNIS", "side": "Sinner",
                                   "wallet": "0xX"}, {}, False, {})
        self.assertNotIn("polymarket.com/event/", msg)
        self.assertNotIn("Markt ansehen", msg)
        self.assertNotIn("None", msg)

    def test_lifetime_fehlt_rendert_als_nichts(self):
        """Gegenbeweis zu `_lifetime`: fehlende Information darf keine Zahl erfinden.

        Dieselbe Wallet, einmal mit und einmal ohne `pnl`. Ohne pnl darf in der Trades-Karte
        weder „lifetime" noch ein „$0" stehen — sonst laese man eine ausgeglichene Bilanz, wo
        gar keine gemessen wurde.
        """
        pos = _pos(150000, league="TENNIS", side="Sinner", price=0.55, wallet="0xP")
        ohne = P.build_card(pos, {"0xP": {"n": 12, "wins": 10, "clvSumPP": 24}}, False, {})
        self.assertIn("bewiesene Wallet", ohne)
        self.assertNotIn("lifetime", ohne)
        self.assertNotIn("$0", ohne)
        mit = P.build_card(pos, {"0xP": {"n": 12, "wins": 10, "clvSumPP": 24, "pnl": 120000}},
                           False, {})
        self.assertIn("+$120K lifetime", mit)
        # Und in der duennen „Bilanz"-Zeile (n>=MIN_TR, aber nicht bewiesen) genauso:
        bil = P.build_card(pos, {"0xP": {"n": 30, "wins": 16, "pnl": 5000}}, False, {})
        self.assertIn("Bilanz", bil)
        self.assertIn("+$5K lifetime", bil)

    def test_negativer_lifetime_zeigt_ueberhaupt_keine_zahl(self):
        """Ein NEGATIVER Lifetime-P&L erreicht `_lifetime` nie — und das ist Absicht.

        `_is_confirmed_loser` (P&L bekannt und < 0) schliesst BEIDE Zweige von `_wallet_line`
        aus. Eine Verlierer-Wallet kriegt deshalb weder „bewiesene Wallet" noch eine Bilanz,
        sondern „Track-Record noch im Aufbau" — auch bei 10/12 Treffern. Die Minus-Formatierung
        in `_lifetime` ist damit reine Absicherung fuer kuenftige Aufrufer, kein gelebter Fall;
        wer sie streicht, macht aus einem Verlust irgendwann ein Plus.
        """
        pos = _pos(150000, league="TENNIS", side="Sinner", price=0.55, wallet="0xP")
        karte = P.build_card(pos, {"0xP": {"n": 12, "wins": 10, "clvSumPP": 24, "pnl": -8400}},
                             False, {})
        self.assertIn("Track-Record noch im Aufbau", karte)
        self.assertNotIn("lifetime", karte)
        self.assertNotIn("8", karte.split("Wallet")[-1])      # keine Verlustzahl in der Zeile
        # Die Absicherung selbst: direkt aufgerufen rendert sie ein echtes Minus, kein „+".
        self.assertIn("\u2212", P._lifetime({"pnl": -8400}))
        self.assertNotIn("+", P._lifetime({"pnl": -8400}))

    def test_public_card_unproven_neutral(self):
        pos = _pos(120000, league="NBA", side="Celtics", price=0.58, wallet="0xNEW")
        msg = P.build_public_card(pos, {}, False, {})
        # Die Wallet-Einordnung steht jetzt in der Trades-Karte; der Public-Kanal sagt zu
        # einer unbewiesenen Wallet GAR NICHTS, statt eine halbe Bilanz zu zeigen.
        self.assertNotIn("bewiesen scharf", msg)
        self.assertIn("Track-Record noch im Aufbau", P.build_card(pos, {}, False, {}))
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

    LEE = "epl-lee-bre-2026-08-30-more-markets"
    # 05.09.2026 — diese Fixture war erfunden. Polymarket schreibt die Frage als
    # „Leeds United FC vs. Brentford FC: O/U 2.5", NIE als „over 2.5 goals". Gemessen ueber den
    # Bestand: von 42 postbaren generischen Maerkten trug KEIN einziger die hier getestete
    # Schreibweise. Der Test war gruen, waehrend die Produktion zu 100 % durchfiel — deshalb
    # laeuft er jetzt gegen die echte Form.
    MIT_LINIE = {LEE: {"frage": "Leeds United FC vs. Brentford FC: O/U 2.5"}}
    MIT_LINIE_PROSA = {LEE: {"frage": "Will there be over 2.5 goals in Leeds vs Brentford?"}}

    def test_der_reale_fall_geht_nicht_mehr_raus(self):
        self.assertFalse(P._pub_seite_benennbar({"key": self.LEE, "side": "Over"}))

    def test_alle_generischen_ausgaenge_fallen_raus(self):
        for seite in ("Over", "under", "Yes", "NO", "Ja", "Nein", "Draw", "Unentschieden", "Tie", "Über"):
            self.assertFalse(P._pub_seite_benennbar({"side": seite}), seite)

    # ── Und der Weg zurueck: mit der Linie ist der Tipp wieder ein Tipp ──────
    def test_mit_bekannter_linie_darf_over_wieder_raus(self):
        """04.09.2026 (Lucas: „aber kriegt man jetzt over maerkte richtig?"). Die Sperre war nie
        das Ziel — sie war die ehrliche Notloesung, solange die Linie fehlte. Seit sie erfasst
        wird, ist „$41K auf Over 2.5 goals" ein nachvollziehbarer und nachpruefbarer Tipp."""
        self.assertTrue(P._pub_seite_benennbar({"key": self.LEE, "side": "Over"}, self.MIT_LINIE))

    def test_ohne_erfasste_frage_bleibt_es_gesperrt(self):
        self.assertFalse(P._pub_seite_benennbar({"key": self.LEE, "side": "Over"}, {}))
        self.assertFalse(P._pub_seite_benennbar({"key": self.LEE, "side": "Over"},
                                                {self.LEE: {"frage": "   "}}))

    def test_die_karte_nennt_SEITE_und_Linie(self):
        """05.09.2026 (Lucas): „nun sieht man zwar line aber nicht welche Seite — Over oder
        Under". Die Karte ersetzte die Seite durch die Marktfrage. Beides muss dastehen."""
        pos = {"key": self.LEE, "side": "Over", "usd": 40686.0, "league": "EPL",
               "firstPrice": 0.515, "wallet": "0xw"}
        for broad in (self.MIT_LINIE, self.MIT_LINIE_PROSA):
            karte = P.build_public_card(pos, {}, False, broad)
            self.assertIn("Over 2.5", karte)
            self.assertNotIn("auf <b>Over</b>", karte, 'das nackte Over darf nicht mehr dastehen')
            self.assertNotIn("Leeds United FC vs. Brentford FC: O/U", karte,
                             'die ganze Marktfrage ist kein Ausgangs-Label')
        unter = dict(pos, side="Under")
        self.assertIn("Under 2.5", P.build_public_card(unter, {}, False, self.MIT_LINIE))

    def test_ohne_frage_bleibt_die_karte_beim_rohen_ausgang(self):
        """Sie wird ohnehin nicht gesendet — aber sie darf keine Linie erfinden."""
        pos = {"key": self.LEE, "side": "Over", "usd": 40686.0, "league": "EPL",
               "firstPrice": 0.515, "wallet": "0xw"}
        self.assertIn("auf <b>Over</b>", P.build_public_card(pos, {}, False, {}))

    def test_linie_kurz_kuerzt_nur_was_eindeutig_ist(self):
        self.assertEqual(P._linie_kurz("Will there be over 2.5 goals in X vs Y?"), "Over 2.5 goals")
        self.assertEqual(P._linie_kurz("Total corners Under 9.5"), "Under 9.5")
        # Keine Zahl an Over/Under -> lieber die ganze Frage als eine ungefaehre Kurzform.
        self.assertEqual(P._linie_kurz("Will both teams score?"), "Will both teams score?")
        self.assertIsNone(P._linie_kurz(None))

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
        # 10.09.2026: kuerzere Formulierung im Public — „Rang #1 Sharp Bettor hat gewettet".
        self.assertIn("Sharp Bettor", card)
        self.assertIn("Rang #1", card)
        # Die lange Form bleibt in der Trades-Karte.
        self.assertIn("Rang #1 der Sharp-Rangliste", P.build_card(pos, sc, restock=False, broad={}))

    def test_public_card_no_badge_for_outside_topn(self):
        sc = self._scores()
        pos = {"wallet": "0x10", "league": "ESPORTS", "side": "X", "key": "k", "usd": 41000, "firstPrice": 0.62}
        card = P.build_public_card(pos, sc, restock=False, broad={})
        self.assertNotIn("Sharp Bettor", card)


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



class TestSportZuordnungIstEine(unittest.TestCase):
    """🔴 08.09.2026 (Lucas: „ob das alles sauber umgesetzt ist"). In DERSELBEN Datei standen zwei
    Liga→Sport-Zuordnungen: `sport_category()` mit voller Regex und `_sport()` mit
    „SOCCER…/LIGA/MLS/EPL/UCL". Gegatet hat die arme — `_pub_ok()` wirft alles raus, was bei ihr
    auf dem 🎯-Default landet, und `_pub_ok` filtert **beide** Kanäle.

    Gemessen an den 617 offenen Positionen des Tages: 75 auf 🎯, davon 55 echter Fußball
    (Ligue 1, EFL Championship, Eliteserien, Ligue 2, Brazil Serie A, Allsvenskan, Scottish
    Premiership). Der Fingerabdruck: `epl` 54 Pushes, `fl1` 2, `bra`/`sco`/`all` je 0. Und weil
    dieser Filter als einziger keine Unterdrückungszeile druckt, war der Verlust unsichtbar.
    """

    LIGEN = ["LIGUE-1", "LIGUE-2", "EFL-CHAMPIONSHIP", "NORWAY-ELITESERIEN",
             "BRAZIL-SERIE-A", "SWEDEN-ALLSVENSKAN", "SCOTTISH-PREMIERSHIP",
             "SAUDI-PROFESSIONAL-LEAGUE", "PRIMEIRA-LIGA", "EREDIVISIE"]

    def test_echte_fussballligen_landen_nicht_auf_dem_default(self):
        for lg in self.LIGEN:
            emoji, name = P._sport(lg)
            self.assertNotEqual(emoji, "🎯", "%s faellt auf den 🎯-Default" % lg)
            self.assertEqual(name, "Fußball", lg)

    def test_pub_ok_laesst_diese_ligen_durch(self):
        for lg in self.LIGEN:
            self.assertTrue(P._pub_ok({"league": lg, "firstPrice": 0.55}),
                            "%s wird aus BEIDEN Kanaelen gefiltert" % lg)

    def test_gestempelter_sport_hat_vorrang(self):
        # 601 der 617 offenen Positionen tragen `sport` bereits als saubere Kategorie.
        self.assertEqual(P._sport("SACHSEN", "Fußball"), ("⚽", "Fußball"))
        self.assertTrue(P._pub_ok({"league": "SACHSEN", "sport": "Fußball", "firstPrice": 0.5}))

    def test_kein_sport_bleibt_draussen(self):
        # Das 🎯 ist der Zweck des Tors: Wahl-/Krypto-Maerkte gehoeren nicht in den Sport-Kanal.
        for lg in ["US-ELECTION-2028", "BITCOIN-PRICE", "OSCARS"]:
            self.assertEqual(P._sport(lg)[0], "🎯", lg)
            self.assertFalse(P._pub_ok({"league": lg, "firstPrice": 0.5}), lg)

    def test_sport_und_sport_category_widersprechen_sich_nicht_mehr(self):
        # Der eigentliche Fehler war der WIDERSPRUCH, nicht das Etikett: `_SPORT` darf ruhig
        # feiner beschriften („MLB Baseball" statt „US-Sport"), aber wo `sport_category` eine
        # Sportart benennt, darf `_sport` nicht „keine Sportart" sagen — das ist das Tor.
        for lg in self.LIGEN + ["TENNIS", "ESPORTS", "MLB", "CFB", "UFC", "NBA", "NHL", "GOLF"]:
            if P.sport_category(lg) == "Sonstige":
                continue
            self.assertNotEqual(P._sport(lg)[0], "🎯",
                                "_sport sagt 'keine Sportart', sport_category sagt %s (%s)"
                                % (P.sport_category(lg), lg))

    def test_jede_bekannte_abkuerzung_ist_auch_eine_kategorie(self):
        # Die andere Richtung: was `_SPORT` als Sport fuehrt, darf `sport_category` nicht
        # „Sonstige" nennen — sonst greift die Sperrliste bei genau diesen Kuerzeln nie.
        for kuerzel in P._SPORT:
            self.assertNotEqual(P.sport_category(kuerzel), "Sonstige",
                                "%s ist in _SPORT, aber fuer sport_category 'Sonstige'" % kuerzel)


# ── 10.09.2026: der Public-Kanal bekommt ein eigenes, kuerzeres Format ───────────────────
# Lucas: „die Poly Push schreiben wir bitte um … können wir bitte beim Einstieg Quoten statt %?
# und bitte den Geldbetrag fett formatieren. Trades-Channel lassen wir alles wie es ist, da will
# ich die ganze Info haben."
class TestPublicKarteNeu(unittest.TestCase):
    BROAD = {"ucl-fen-rom-2026-09-10": {
        "shares": {"Fenerbahçe SK": 0.71, "AS Roma": 0.29},
        "totalUsd": 336180, "league": "UCL", "sport": "Fußball",
        "hoursToKickoff": 4.1}}

    def _pos(self, **over):
        p = {"key": "ucl-fen-rom-2026-09-10", "side": "Fenerbahçe SK", "wallet": "0xabc",
             "usd": 26894, "league": "UCL", "sport": "Fußball",
             "entryPrice": 0.71, "firstPrice": 0.71}
        p.update(over)
        return p

    def test_einstieg_steht_als_QUOTE_nicht_in_cent(self):
        """71¢ ist eine Wahrscheinlichkeit, @1.41 die Sprache, in der der Rest des Kanals
        spricht (Betfair, Cards, alles @x.xx). Zwei Einheiten fuer dieselbe Sache kosten bei
        jedem Blick eine Umrechnung."""
        t = P.build_public_card(self._pos(), {}, False, self.BROAD)
        self.assertIn("Einstieg @1.41", t)
        self.assertNotIn("71¢", t)

    def test_der_geldbetrag_ist_fett(self):
        t = P.build_public_card(self._pos(), {}, False, self.BROAD)
        self.assertIn("<b>$26.9K</b>", t)

    def test_die_reihenfolge_ist_sportart_dann_spiel(self):
        """Die Sportart ist der Filter, mit dem ein Leser entscheidet, ob ihn die Zeile
        ueberhaupt angeht — sie steht deshalb vor der Paarung."""
        t = P.build_public_card(self._pos(), {}, False, self.BROAD)
        self.assertLess(t.index("Fußball"), t.index("Fenerbahçe SK v AS Roma"))

    def test_die_trades_sicht_bleibt_draussen(self):
        """⭐ Der Kern der Umstellung: Ticket-Median, Preisbewegung, Aussenseiter-Hinweis und die
        volle Wallet-Bilanz sind TRADES-Information. Halb gezeigt waeren sie schlechter als gar
        nicht — also gar nicht."""
        scores = {"0xabc": {"n": 264, "wins": 147, "clvSumPP": 211.2, "pnl": 1000000.0,
                            "usd": 500000}}
        t = P.build_public_card(self._pos(), scores, False, self.BROAD)
        for weg in ("übliche Ticket", "Median", "→ jetzt", "lifetime", "Außenseiter"):
            self.assertNotIn(weg, t, "%s gehoert in den Trades-Kanal, nicht in den Public" % weg)

    def test_ohne_preis_steht_keine_quote_da(self):
        """Eine fehlende Zahl rendert nicht als @1.00 und nicht als 0."""
        t = P.build_public_card(self._pos(entryPrice=None, firstPrice=None), {}, False, self.BROAD)
        self.assertNotIn("Einstieg", t)
        self.assertNotIn("@", t)

    def test_quote_bei_sicherem_preis_gibt_es_nicht(self):
        """Preis 1,00 hiesse Quote 1,00 — das waere eine erfundene Wette ohne Gewinn."""
        self.assertIsNone(P._quote(1.0))
        self.assertIsNone(P._quote(0.0))
        self.assertEqual(P._quote(0.5), "@2.00")

    def test_der_rang_steht_kurz_da(self):
        scores = {"0xabc": {"n": 50, "wins": 40, "clvSumPP": 30.0}}
        import poly_whale_watch as _W
        rang = _W._pub_rang_zeile({"0xabc": scores["0xabc"]}, "0xabc")
        if rang:
            self.assertIn("Sharp Bettor", rang)
            self.assertIn("hat gewettet", rang)

    def test_ohne_marktvolumen_keine_prozentzeile(self):
        t = P.build_public_card(self._pos(), {}, False, {})
        self.assertNotIn("Marktvolumen", t)


# ── 11.09.2026: das Beobachtungsband „Markt-Dominanz" ────────────────────────────────────
class TestMarktDominanz(unittest.TestCase):
    """Lucas: „Wallets, die nur $5.000 spielen, aber das sind 80 % vom ganzen Turnier-Markt — ob
    da die Trefferquote hoch ist."

    Gemessen an den Whale-Pushs zeigte der Anteil eine Richtung (15-30 %: 81,8 % Treffer bei n=11
    gegen 57,1 % unter 15 %), aber Lucas' eigentlicher Fall kam dort 0 von 36 Mal vor: die
    $25.000-Schwelle und ein hoher Anteil schliessen sich fast aus. Deshalb ein eigenes Band.
    """

    def _tr(self, **over):
        # firstPrice 0.55 -> Quote 1,82, also ueber DOM_MIN_QUOTE (1,35).
        pos = {"wallet": "0xw", "key": "k", "side": "A", "usd": 6000, "league": "ESPORTS",
               "firstPrice": 0.55, "lastPrice": 0.55, "firstTs": NOW.isoformat()}
        pos.update(over)
        # Seit 12.09.2026 braucht das Band eine BELEGTE Wallet (sharp_gate). Die Fixture traegt
        # deshalb einen Track-Record, der das Gate besteht — sonst pruefte jeder Test hier
        # unbemerkt nur noch das Wallet-Gate.
        return {"open": {"0xw|k|A": pos}, "scores": {"0xw": SHARP}}

    @staticmethod
    def _broad(total, htk=0.4, seite=None):
        """Ein reifer Markt, dessen Anpfiff noch bevorsteht.

        `htk` muss drinstehen (ohne Messzeitpunkt gilt der Markt als unreif), und `capturedAt`
        ebenso: daraus errechnet sich der Anpfiff, und eine Position, deren Spiel schon laeuft,
        wird seit 11.09.2026 nicht mehr gepusht. Gemessen am Stand NOW, damit der Anpfiff in der
        Zukunft liegt — sonst pruefte jeder Test unbemerkt nur noch die Anpfiff-Sperre.

        `shares` ist seit 11.09.2026 der NENNER des Bands (`seiten_anteil`): das Geld auf der
        eigenen Seite, nicht das des ganzen Markts. Default: die Haelfte liegt auf „A" — damit
        misst `total` weiter die Marktgroesse (fuer den Boden) und `seite` den Anteil.
        """
        seite = total / 2.0 if seite is None else seite
        return {"k": {"totalUsd": total, "hoursToKickoff": htk,
                      "capturedAt": NOW.isoformat(),
                      "shares": {"A": seite, "B": max(total - seite, 1.0)}}}

    def test_kleiner_markt_grosser_anteil_kommt_durch(self):
        # $6.000 von $10.000 auf der eigenen Seite = 60 %. Der Gesamtmarkt ist doppelt so gross —
        # nach dem ALTEN Mass waeren es 30 % gewesen und die Position waere durchgefallen.
        r = P.dominanz_kandidaten(self._tr(), self._broad(20000, seite=10000), now=NOW)
        self.assertEqual(len(r), 1)
        self.assertAlmostEqual(r[0][2], 0.6, places=3)

    def test_zu_wenig_geld_faellt_raus(self):
        """Lucas: „ab dreitausend Dollar klingt okay." Darunter ist es kein Band, sondern Rauschen.

        Der Markt liegt bewusst knapp UEBER dem Boden, damit nicht der Boden die Ablehnung
        uebernimmt und die Einsatzschwelle ungeprueft mitlaeuft. Genau das war vorher der Fall:
        mit entfernter `min_usd`-Zeile lief die Suite gruen durch.
        """
        br = self._broad(20000, seite=5000)      # Seite $5.000, Markt weit ueber dem Boden
        self.assertEqual(P.dominanz_kandidaten(self._tr(usd=2400), br, now=NOW), [],
                         "$2.400 sind unter der Schwelle, auch bei 48 % Anteil")
        self.assertEqual(P.dominanz_kandidaten(self._tr(usd=2900), br, now=NOW), [],
                         "auch knapp darunter bleibt draussen")
        # Gegenprobe: dieselbe Seite, nur ueber der Schwelle — kommt durch.
        self.assertEqual(len(P.dominanz_kandidaten(self._tr(usd=3100), br, now=NOW)), 1)

    def test_zu_kleiner_anteil_faellt_raus(self):
        r = P.dominanz_kandidaten(self._tr(usd=6000), self._broad(100000, seite=50000), now=NOW)
        self.assertEqual(r, [], "12 % der eigenen Seite sind keine Dominanz")

    def test_der_favoriten_drall_ist_weg(self):
        """🔴 11.09.2026 — der Grund fuer die Umstellung. Bei Polymarket ist `usd = Anteile ×
        Preis`. Dieselbe Stueckzahl auf einem Favoriten @0,87 zaehlte als 6,7× so viel
        „Dominanz" wie auf einem Aussenseiter @0,13. Das Band fand fast nur Favoriten, und der
        Quotenboden warf sie wieder raus — zwei Regeln, die gegeneinander arbeiteten.

        Hier: dieselbe Stueckzahl, nur der Preis unterscheidet. Beim Anteil an der EIGENEN Seite
        kuerzt sich der Preis heraus, also muss dasselbe herauskommen."""
        for preis, gegen in ((0.87, 0.13), (0.13, 0.87)):
            tr = self._tr(usd=round(600 * preis), firstPrice=preis, lastPrice=preis)
            br = {"k": {"totalUsd": 50000, "hoursToKickoff": 0.4, "capturedAt": NOW.isoformat(),
                        "shares": {"A": 1000 * preis, "B": 1000 * gegen}}}
            a = P.seiten_anteil(tr["open"]["0xw|k|A"], br)
            self.assertAlmostEqual(a, 0.6, places=2, msg="Preis %s" % preis)

    def test_die_toleranz_kann_keinen_anteil_ueber_100_prozent_erzeugen(self):
        """Zaehler und Nenner koennen aus zwei Abrufen stammen, deshalb 2 % Toleranz. Die darf
        aber nie zu „103 % der Seite" fuehren — eine Zahl, die es nicht geben kann, faellt auf
        der Karte nicht auf, weil sie wie eine besonders gute aussieht."""
        br = {"k": {"totalUsd": 50000, "hoursToKickoff": 0.4, "capturedAt": NOW.isoformat(),
                    "shares": {"A": 10000.0, "B": 10000.0}}}
        pos = self._tr(usd=10150)["open"]["0xw|k|A"]        # 1,5 % ueber der Seite
        a = P.seiten_anteil(pos, br)
        self.assertIsNotNone(a, "innerhalb der Toleranz zaehlt es noch")
        self.assertLessEqual(a, 1.0, "aber nie ueber 100 %")

    def test_die_karte_zeigt_den_seiten_anteil(self):
        """Die Karte sagt „X % des Marktes". Wuerde sie den alten Wert zeigen und die Auswahl den
        neuen, stuende auf dem Push eine andere Zahl als die, nach der entschieden wurde."""
        pos = self._tr(usd=6000)["open"]["0xw|k|A"]
        br = self._broad(20000, seite=10000)
        k = P.build_dominanz_card(pos, {}, br, now=NOW)
        self.assertIn("60 %", k)
        self.assertNotIn("30 %", k, "das waere der Anteil am Gesamtmarkt — nicht das Mass des Bands")

    def test_beide_masse_stehen_im_buch(self):
        """`anteil` (Gesamtmarkt) und `seitenAnteil` (eigene Seite) werden BEIDE gebucht, plus
        der Nenner. Sonst liesse sich spaeter nicht nachrechnen, ob die Umstellung getragen hat —
        und genau diese Frage wird in ein paar Wochen gestellt."""
        st = P.markt_stempel(self._tr(usd=6000)["open"]["0xw|k|A"], self._broad(20000, seite=10000))
        self.assertAlmostEqual(st.get("seitenAnteil"), 0.6, places=3)
        self.assertAlmostEqual(st.get("anteil"), 0.3, places=3)
        self.assertAlmostEqual(st.get("seiteUsd"), 10000.0, places=1)

    def test_winziger_markt_ist_keine_dominanz(self):
        """Lucas ausdruecklich: „natuerlich jetzt nicht auf der Spielwohnung 300 Euro und ich hab
        100 %, das will ich nicht finden." Der Boden steht deshalb am MARKT, nicht nur am Einsatz."""
        r = P.dominanz_kandidaten(self._tr(usd=3500), self._broad(4000, seite=3500), now=NOW)
        self.assertEqual(r, [], "100 % einer Seite in einem $4.000-Markt ist kein Befund")

    def test_ohne_marktvolumen_gibt_es_keinen_anteil(self):
        """Fehlende Information rendert als nichts. Ein Anteil ohne Nenner waere schlimmer als
        kein Anteil — und 100 % anzunehmen waere die teuerste Variante davon."""
        self.assertEqual(P.dominanz_kandidaten(self._tr(), {}, now=NOW), [])
        self.assertEqual(P.dominanz_kandidaten(self._tr(), {"k": {}}, now=NOW), [])

    def test_einsatz_groesser_als_markt_gilt_nicht_als_100_prozent(self):
        """`markt_anteil` gibt None, wo der Einsatz das Marktvolumen uebersteigt — der Nenner
        widerspricht dann dem Zaehler. Das darf hier nicht als Dominanz durchgehen."""
        r = P.dominanz_kandidaten(self._tr(usd=50000), self._broad(80000, seite=20000), now=NOW)
        self.assertEqual(r, [])

    def test_sperre_nimmt_beide_whale_staende_mit(self):
        """Die Doppelung waere Lucas\' Problem, nicht das der Datei: er liest Trades UND Public.
        Eine Position, die dort schon als Whale stand, darf hier nicht noch einmal kommen."""
        sp = P.dom_sperre({"a|k|A": {"ts": "x"}},
                          {"b|k|A": {"ts": "x"}}, {"c|k|A": {"ts": "x"}})
        self.assertEqual(set(sp), {"a|k|A", "b|k|A", "c|k|A"})
        tr = self._tr()
        self.assertEqual(
            P.dominanz_kandidaten(tr, self._broad(10000),
                                  seen=P.dom_sperre({}, {"0xw|k|A": {"ts": "x"}}, {}), now=NOW),
            [], "als Trades-Whale gemeldet — kein zweiter Push")
        self.assertEqual(
            P.dominanz_kandidaten(tr, self._broad(10000),
                                  seen=P.dom_sperre({}, {}, {"0xw|k|A": {"ts": "x"}}), now=NOW),
            [], "als Public-Whale gemeldet — kein zweiter Push")

    def test_sperre_vertraegt_kaputte_staende(self):
        """Ein fehlendes oder kaputtes Buch darf die Sperre nicht sprengen — sonst faellt das
        Band beim ersten Lauf ohne Datei aus."""
        self.assertEqual(P.dom_sperre(None, None, None), {})
        self.assertEqual(P.dom_sperre("kaputt", [], 7), {})

    def test_schon_gemeldete_position_kommt_nicht_doppelt(self):
        tr = self._tr()
        r = P.dominanz_kandidaten(tr, self._broad(10000),
                                  seen={"0xw|k|A": {"ts": NOW.isoformat()}}, now=NOW)
        self.assertEqual(r, [])

    def test_bestaetigter_verlierer_bleibt_draussen(self):
        tr = self._tr()
        tr["scores"]["0xw"] = {"n": 20, "wins": 16, "pnl": -25000}
        self.assertEqual(P.dominanz_kandidaten(tr, self._broad(10000), now=NOW), [])

    def test_alte_position_ist_kein_ereignis(self):
        alt = (NOW - timedelta(days=5)).isoformat()
        r = P.dominanz_kandidaten(self._tr(firstTs=alt), self._broad(10000), now=NOW)
        self.assertEqual(r, [])

    def test_kein_sport_bleibt_draussen(self):
        """Politik und Krypto haben in diesem Band nichts zu suchen — `_pub_ok` prueft das."""
        r = P.dominanz_kandidaten(self._tr(league="US-ELECTION"), self._broad(10000), now=NOW)
        self.assertEqual(r, [])

    def test_gesperrte_sportarten_bleiben_draussen(self):
        """🔴 KORREKTUR 12.09.2026 (Lucas: „aja und bitte us Sport gleich weg").

        Hier stand das Gegenteil — mit der Begruendung, das Band sei eine Beobachtung und kein
        Kanal, dem jemand folgt. Das Argument war in sich schluessig und trotzdem falsch: Lucas
        LIEST den Trades-Kanal, und eine Karte, die er nicht gebrauchen kann, kostet ihn
        Aufmerksamkeit — ob sie „Beobachtung" heisst oder „Empfehlung", macht beim Lesen keinen
        Unterschied. Ausloeser war ein MLB-Push mit einer 314/742-Wallet (42 %) ohne Paarung.
        """
        for liga in ("NBA", "MLB", "NFL", "NHL", "UFC"):
            self.assertEqual(
                P.dominanz_kandidaten(self._tr(league=liga), self._broad(20000, seite=10000),
                                      now=NOW, blocked=["US-Sport", "Kampfsport"]),
                [], liga)

    def test_die_sperrliste_kommt_aus_derselben_quelle_wie_ueberall(self):
        """Eine eigene Liste hier waere genau die Drift, gegen die `blocked_cats` gebaut wurde:
        legt Lucas die Sperre in poly-wallets.js um, muss dieses Band mitziehen."""
        tr = self._tr(league="NBA")
        br = self._broad(20000, seite=10000)
        self.assertEqual(P.dominanz_kandidaten(tr, br, now=NOW, blocked=["US-Sport"]), [])
        self.assertEqual(len(P.dominanz_kandidaten(tr, br, now=NOW, blocked=["Kampfsport"])), 1,
                         "steht US-Sport nicht auf der Liste, laeuft es mit — die LISTE regiert")

    def test_main_reicht_DIESELBE_liste_durch_wie_an_den_public_kanal(self):
        """🔴 Beim Provozieren aufgefallen: die Weitergabe aus `main()` zu entfernen lief GRUEN
        durch — weil der Rueckfall zufaellig dieselbe Liste ist wie die aus der Datei.

        Heute unsichtbar, morgen nicht: legt Lucas die Sperre in poly-wallets.js um, liefe dieses
        Band weiter auf dem alten Rueckfall, waehrend alle anderen Kanaele umziehen. Das ist
        exakt die Drift, gegen die `blocked_cats` ueberhaupt gebaut wurde — und sie waere
        unsichtbar, weil beide Listen heute gleich aussehen.
        """
        import inspect
        q = inspect.getsource(P.main)
        i = q.index("dom_cand = dominanz_kandidaten(")
        aufruf = q[i:i + 320]
        self.assertIn("blocked=_blocked", aufruf,
                      "die Dominanz-Auswahl muss dieselbe Liste bekommen wie der Public-Kanal")
        self.assertLess(q.index("_blocked = blocked_cats("), i,
                        "die Liste muss VOR dem Aufruf aus der Datei gelesen werden")

    def test_ohne_uebergebene_liste_gilt_der_sichere_rueckfall(self):
        """Faellt poly_shortlist_track.json aus, darf NICHT alles durchrutschen. `bet_blocked`
        greift dann auf BLOCKED_FALLBACK zurueck — dieselbe Regel wie in den anderen Kanaelen."""
        self.assertEqual(P.dominanz_kandidaten(self._tr(league="NBA"),
                                               self._broad(20000, seite=10000), now=NOW), [])
        self.assertIn("US-Sport", P.BLOCKED_FALLBACK)

    def test_fussball_und_esport_laufen_weiter(self):
        """Die Gegenprobe. Ohne sie koennte die Sperre alles fangen und der Test waere gruen."""
        for liga in ("ESPORTS", "SOCCER", "TENNIS"):
            self.assertEqual(
                len(P.dominanz_kandidaten(self._tr(league=liga), self._broad(20000, seite=10000),
                                          now=NOW, blocked=["US-Sport", "Kampfsport"])), 1, liga)

    def test_der_groesste_anteil_steht_oben(self):
        tr = {"open": {
            "0xa|k1|A": {"wallet": "0xa", "key": "k1", "side": "A", "usd": 6000, "lastPrice": 0.55,
                         "league": "ESPORTS", "firstPrice": 0.55, "firstTs": NOW.isoformat()},
            "0xb|k2|B": {"wallet": "0xb", "key": "k2", "side": "B", "usd": 9000, "lastPrice": 0.55,
                         "league": "ESPORTS", "firstPrice": 0.55, "firstTs": NOW.isoformat()}},
            "scores": {"0xa": SHARP, "0xb": SHARP}}
        _ca = NOW.isoformat()
        r = P.dominanz_kandidaten(tr, {"k1": {"totalUsd": 20000, "hoursToKickoff": 0.4,
                                              "capturedAt": _ca,
                                              "shares": {"A": 10000, "B": 10000}},
                                       "k2": {"totalUsd": 40000, "hoursToKickoff": 0.4,
                                              "capturedAt": _ca,
                                              "shares": {"B": 20000, "A": 20000}}}, now=NOW)
        self.assertEqual([x[0] for x in r], ["0xa|k1|A", "0xb|k2|B"],
                         "sortiert wird nach ANTEIL, nicht nach Dollar")


class TestMarktReife(unittest.TestCase):
    """Lucas: „ein Markt in 2 Wochen wo jetzt 5K gespielt werden die 60 % sind, interessiert mich
    ja 0. Wir muessens quasi zeitlich wie die Whale-Alerts eingrenzen."

    Gemessen an 424 Maerkten mit Verlauf bis zum Anpfiff, Volumen gegen den Endstand:
    2,5-3 h vorher Median 54 % (unteres Viertel 28 %), 0,5-1 h Median 92 %, 0-0,5 h 100 %.
    Ein Anteil, der zu frueh gemessen wird, hat einen halb leeren Nenner und ist systematisch
    zu hoch. Deshalb wird der Anteil erst gelesen, wenn der Markt steht.
    """

    def _pos(self, **over):
        p = {"wallet": "0xw", "key": "k", "side": "A", "usd": 6000, "league": "ESPORTS",
             "firstPrice": 0.55, "lastPrice": 0.55, "firstTs": NOW.isoformat(), "htkFirst": 2.8}
        p.update(over)
        return p

    @staticmethod
    def _b(total, htk, key="k", capturedAt=None):
        """`capturedAt` + `hoursToKickoff` ergeben den Anpfiff. NOW als Aufnahmezeit heisst:
        der Anpfiff liegt `htk` Stunden in der Zukunft — das Spiel steht also noch bevor."""
        m = {"totalUsd": total, "hoursToKickoff": htk,
             "capturedAt": (capturedAt or NOW).isoformat(),
             "shares": {"A": total / 2.0, "B": total / 2.0}}
        return {key: m}

    def test_reifer_markt_gibt_die_stunde_zurueck(self):
        self.assertAlmostEqual(
            P.markt_reif(self._pos(), {"k": {"totalUsd": 20000, "hoursToKickoff": 0.8}}), 0.8)

    def test_zu_frueh_gemessen_ist_nicht_reif(self):
        """Der Kern der Sache: 2,8 h vor Anpfiff steht im Median erst gut die Haelfte des
        Endvolumens im Markt. Der Anteil waere dann etwa doppelt so hoch wie die Wahrheit."""
        self.assertIsNone(
            P.markt_reif(self._pos(), {"k": {"totalUsd": 20000, "hoursToKickoff": 2.8}}))

    def test_nach_anpfiff_ist_reif_nicht_unreif(self):
        """htk <= 0 heisst: der Vorspiel-Markt ist fertig. Ein Vorzeichenfehler hier wuerde
        ausgerechnet die vollsten Maerkte aussperren."""
        self.assertEqual(
            P.markt_reif(self._pos(), {"k": {"totalUsd": 20000, "hoursToKickoff": 0}}), 0.0)
        self.assertEqual(
            P.markt_reif(self._pos(), {"k": {"totalUsd": 20000, "hoursToKickoff": -0.5}}), -0.5)

    def test_ohne_messzeitpunkt_ist_der_markt_nicht_reif(self):
        """Fehlende Information rendert als harmloser Default — und „harmlos" heisst hier NICHT
        durchlassen. Ein unbekannter Messzeitpunkt als „passt schon" zu lesen waere dieselbe
        Fehlerklasse wie ein fehlendes Volumen als 100 % zu lesen."""
        for b in ({}, {"k": {}}, {"k": {"totalUsd": 20000}},
                  {"k": {"totalUsd": 20000, "hoursToKickoff": None}},
                  {"k": {"totalUsd": 20000, "hoursToKickoff": "0.5"}}):
            self.assertIsNone(P.markt_reif(self._pos(), b), repr(b))

    def test_bool_ist_keine_stunde(self):
        self.assertIsNone(
            P.markt_reif(self._pos(), {"k": {"totalUsd": 20000, "hoursToKickoff": True}}))

    def test_die_auswahl_haelt_unreife_maerkte_zurueck(self):
        """Nicht verworfen — zurueckgehalten. Derselbe Markt kommt einen Lauf spaeter durch,
        wenn seine Close-Zeile naeher am Anpfiff steht. Das ist der Tausch: spaeter, dafuer
        gegen einen Nenner, der steht."""
        # 50 % Anteil bei 2,5 h: konservativ gerechnet (× 0,69 Fuellgrad) sind das 34,5 % —
        # unter der Schwelle, also warten. Bei 0,5 h steht der Nenner und dieselbe Position kommt.
        tr = {"open": {"0xw|k|A": self._pos()}, "scores": {"0xw": SHARP}}
        self.assertEqual(
            P.dominanz_kandidaten(tr, self._b(24000, 2.5), now=NOW),
            [], "2,5 h vorher ist der Nenner im Median erst gut zwei Drittel voll")
        spaeter = P.dominanz_kandidaten(tr, self._b(24000, 0.5), now=NOW)
        self.assertEqual(len(spaeter), 1, "naeher am Anpfiff kommt dieselbe Position durch")

    def test_der_messzeitpunkt_steht_auf_der_karte(self):
        """Ein Anteil ohne Zeitstempel laedt dazu ein, 2,8-h- und 0,3-h-Anteile fuer dasselbe
        Mass zu halten. Deshalb steht die Stunde auf der Karte, nicht nur im Buch."""
        k = P.build_dominanz_card(self._pos(key="cs2-a-b-2026-09-12"), {},
                                  self._b(12000, 0.5, key="cs2-a-b-2026-09-12"), now=NOW)
        self.assertIn("30 Min", k)
        self.assertIn("vor Anpfiff", k)

    def test_stundenangabe_liest_sich_wie_ein_mensch_sie_schreibt(self):
        self.assertEqual(P._htk_text(0.5), "30 Min")
        self.assertEqual(P._htk_text(0.25), "15 Min")
        self.assertEqual(P._htk_text(1.5), "1,5 h")
        self.assertEqual(P._htk_text(0), "Anpfiff")
        self.assertEqual(P._htk_text(-0.3), "Anpfiff")
        self.assertEqual(P._htk_text(0.001), "1 Min", "nie 0 Min — das laese sich als Anpfiff")
        self.assertEqual(P._htk_text(None), "")

    def test_der_stempel_haelt_beide_zeiten_getrennt(self):
        """`htkMess` ist die Reife des MARKTS, `htkFirst` der Vorlauf der WALLET. Zwei Fragen,
        zwei Felder — zusammengelegt waere spaeter keine von beiden zu beantworten."""
        st = P.markt_stempel(self._pos(htkFirst=2.8),
                             {"k": {"totalUsd": 12000, "hoursToKickoff": 0.5}})
        self.assertEqual(st.get("htkMess"), 0.5)
        self.assertEqual(st.get("htkFirst"), 2.8)
        self.assertEqual(st.get("league"), "ESPORTS")

    def test_der_marktboden_steht_auf_dem_wert_der_wirklich_gilt(self):
        """🔴 Der Boden stand auf 6000 und konnte nie greifen: `poly_money_broad.MIN_VOL_USD`
        laesst keinen kleineren Markt in die Close-Datei (gemessen: 0 von 2.928 Zeilen unter
        $6.000, kleinster Markt $7.504). Er ist jetzt eine Stolperschwelle — senkt jemand oben
        den Boden, faellt es hier auf, statt still $2.000-Maerkte zu melden."""
        import poly_money_broad as PMB
        self.assertLessEqual(PMB.MIN_VOL_USD, P.DOM_MIN_MARKET,
                             "der Band-Boden darf nicht unter dem liegen, der oben ohnehin gilt")


class TestDominanzQuote(unittest.TestCase):
    """Lucas 11.09.2026, nach der ersten echten Karte („Einstieg @1,21"):
    „bitte mindest odd auch einbauen, ab 1,35 erst wieder."

    Der Befund ist groesser als die eine Karte: von fuenf Positionen, die das Band an dem Tag
    gefunden haette, lagen VIER unter 1,35 (@1,14 · @1,18 · @1,21 · @1,25). Bauart, nicht Zufall
    — die niedrige Einsatzschwelle dieses Bands landet in kleinen Favoritenmaerkten, wo ein
    einzelner Einsatz ueberhaupt erst 40 % erreichen kann. Im Public-Whale-Buch steht ueber 27
    abgerechnete Pushs KEINE EINZIGE Zeile unter 1,35.
    """

    def _pos(self, last=0.55, **over):
        p = {"wallet": "0xw", "key": "k", "side": "A", "usd": 6000, "league": "ESPORTS",
             "firstPrice": last, "lastPrice": last, "firstTs": NOW.isoformat()}
        p.update(over)
        return p

    def test_quote_ueber_dem_boden_kommt_durch(self):
        self.assertAlmostEqual(P._dom_quote(self._pos(0.55)), 1 / 0.55, places=6)

    def test_favoritenpreis_faellt_raus(self):
        """@1,21 war der Anlass. Bei 1,14 braucht man 88 % Trefferquote zum Nullpunkt —
        da ist keine Beobachtung mehr drin, nur noch Marge."""
        for preis in (0.88, 0.85, 0.826, 0.75):      # 1,14 · 1,18 · 1,21 · 1,33
            self.assertIsNone(P._dom_quote(self._pos(preis)), "Preis %s" % preis)

    def test_genau_auf_der_schwelle_zaehlt_als_drin(self):
        self.assertIsNotNone(P._dom_quote(self._pos(1 / 1.35)))

    def test_ohne_preis_gibt_es_keine_quote_und_keinen_push(self):
        """Eine Trefferquote ohne die Quoten ist keine Zahl — eine Beobachtung ohne
        abrechenbaren Preis waere genau das."""
        # "0.5" fehlt hier bewusst: `_push_price` wandelt eine Zahl als Text um, und das ist
        # gewollt — der Feed hat schon Preise als String geliefert. Geprueft wird, was KEIN
        # brauchbarer Preis ist: fehlend, ausserhalb (0,1), oder ein bool getarnt als Zahl.
        for bad in (None, 0, 1, 1.4, -0.2, True):
            self.assertIsNone(P._dom_quote(self._pos(last=bad)), repr(bad))

    def test_gerechnet_wird_auf_dem_push_preis_nicht_auf_dem_einstieg(self):
        """Sonst koennte eine Zeile mit @1,50 ins Buch gehen und mit @1,15 abgerechnet werden:
        dieselbe Zahl an zwei Stellen mit zwei Bedeutungen. `_log_dominanz_push` bucht den
        Push-Preis, also entscheidet der auch."""
        # Wal stieg guenstig ein (@2,00), der Markt ist inzwischen teuer (@1,15).
        self.assertIsNone(P._dom_quote(self._pos(firstPrice=0.50, lastPrice=0.87)))
        # Umgekehrt: Wal teuer rein, Markt inzwischen guenstig — das zaehlt.
        self.assertIsNotNone(P._dom_quote(self._pos(firstPrice=0.87, lastPrice=0.50)))

    def test_die_auswahl_haelt_den_boden_ein(self):
        tr = {"open": {"0xw|k|A": self._pos(0.826)}, "scores": {"0xw": SHARP}}
        br = {"k": {"totalUsd": 12000, "hoursToKickoff": 0.5, "capturedAt": NOW.isoformat(),
                    "shares": {"A": 8000.0, "B": 4000.0}}}
        self.assertEqual(P.dominanz_kandidaten(tr, br, now=NOW), [], "@1,21 bleibt draussen")
        tr["open"]["0xw|k|A"]["lastPrice"] = 0.55
        self.assertEqual(len(P.dominanz_kandidaten(tr, br, now=NOW)), 1)

    def test_die_karte_zeigt_beide_preise(self):
        """Der Einstieg des Wals ist Geschichte, die aktuelle Quote ist das, was ein Leser
        bekaeme. Bei einer Karte, die auf den reifen Markt wartet, ist der Einstieg allein
        die falsche Zahl."""
        k = P.build_dominanz_card(self._pos(firstPrice=0.50, lastPrice=0.55), {},
                                  {"k": {"totalUsd": 12000, "hoursToKickoff": 0.5,
                                         "capturedAt": NOW.isoformat(),
                                         "shares": {"A": 8000.0, "B": 4000.0}}}, now=NOW)
        self.assertIn("Einstieg", k)
        self.assertIn("jetzt", k)
        self.assertIn("@2.00", k, "der Einstieg des Wals")
        self.assertIn("@1.82", k, "und der Preis, den ein Leser jetzt bekaeme")

    def test_bei_gleichem_preis_steht_die_zahl_nur_einmal(self):
        """Zweimal dieselbe Zahl nebeneinander liest sich wie ein Fehler. Steht der Markt noch
        da, wo der Wal eingestiegen ist, ist das EINE Aussage."""
        k = P.build_dominanz_card(self._pos(0.55), {},
                                  {"k": {"totalUsd": 12000, "hoursToKickoff": 0.5,
                                         "capturedAt": NOW.isoformat(),
                                         "shares": {"A": 8000.0, "B": 4000.0}}}, now=NOW)
        self.assertEqual(k.count("1.82"), 1)
        self.assertNotIn("jetzt", k)


class TestAnpfiffAufDerKarte(unittest.TestCase):
    """Lucas 11.09.2026: „bzw sollt ich sehen wann das Spiel ist / seh ich ned."

    Und der Fund dabei: die erste echte Karte ging 26 Minuten NACH Anpfiff raus. Der Markt
    speichert keinen Anpfiff, sondern `capturedAt` + `hoursToKickoff` — `htk` ist der
    MESSzeitpunkt, nicht die Gegenwart. Zwischen Messung und Versand liegt der Runner.
    """

    def _pos(self, **over):
        p = {"wallet": "0xw", "key": "k", "side": "A", "usd": 6000, "league": "ESPORTS",
             "firstPrice": 0.55, "lastPrice": 0.55, "firstTs": NOW.isoformat()}
        p.update(over)
        return p

    def _b(self, htk, aufgenommen=None, total=12000):
        return {"k": {"totalUsd": total, "hoursToKickoff": htk,
                      "capturedAt": (aufgenommen or NOW).isoformat(),
                      "shares": {"A": total / 2.0, "B": total / 2.0}}}

    def test_anpfiff_ist_aufnahmezeit_plus_stunden_bis_anpfiff(self):
        ko = P.anpfiff_zeit(self._pos(), self._b(1.5))
        self.assertEqual(ko, NOW + timedelta(hours=1.5))

    def test_ohne_aufnahmezeit_kein_anpfiff(self):
        self.assertIsNone(P.anpfiff_zeit(self._pos(), {"k": {"hoursToKickoff": 1.5}}))
        self.assertIsNone(P.anpfiff_zeit(self._pos(), {"k": {"capturedAt": NOW.isoformat()}}))
        self.assertIsNone(P.anpfiff_zeit(self._pos(), {}))

    def test_die_uhrzeit_steht_auf_der_karte(self):
        k = P.build_dominanz_card(self._pos(), {}, self._b(0.5), now=NOW)
        self.assertIn("Anpfiff", k)
        self.assertRegex(k, r"Anpfiff <b>\d{2}:\d{2}</b>")

    def test_ein_laufendes_spiel_wird_nicht_mehr_gepusht(self):
        """Der eigentliche Fehler: die Messung lag 20 Min vor Anpfiff, der Push kam 26 Min
        danach. Fuer die MESSUNG ist ein Markt nach Anpfiff maximal reif — fuer den PUSH ist er
        wertlos, weil die genannte Quote nicht mehr zu bekommen ist."""
        tr = {"open": {"0xw|k|A": self._pos()}, "scores": {"0xw": SHARP}}
        # Aufgenommen 20 Min vor Anpfiff, gesendet wird eine halbe Stunde spaeter.
        br = self._b(0.33, aufgenommen=NOW - timedelta(hours=0.33))
        self.assertEqual(P.dominanz_kandidaten(tr, br, now=NOW + timedelta(minutes=26)), [],
                         "nach Anpfiff ist es keine Beobachtung mehr, nur Nachschau")
        self.assertEqual(len(P.dominanz_kandidaten(tr, br, now=NOW - timedelta(minutes=10))), 1,
                         "davor sehr wohl")

    def test_ohne_bestimmbaren_anpfiff_wird_nicht_gepusht(self):
        """Dieselbe Regel wie ueberall in diesem Band: fehlende Information laesst nicht durch.
        Wann das Spiel ist, ist hier keine Zusatzinfo, sondern die Voraussetzung — Lucas will es
        VORHER mitverfolgen."""
        tr = {"open": {"0xw|k|A": self._pos()}, "scores": {}}
        self.assertEqual(
            P.dominanz_kandidaten(tr, {"k": {"totalUsd": 12000, "hoursToKickoff": 0.5}}, now=NOW),
            [], "ohne capturedAt ist der Anpfiff unbekannt")


class TestFrueheFreigabe(unittest.TestCase):
    """Lucas 11.09.2026: „hast du Idee wie wir das Zeitproblem loesen?"

    Das Reifefenster loeste das MESSproblem und schuf ein ANZEIGEproblem: eine Position von
    2,8 h vor Anpfiff steht erst 1,8 h spaeter im Kanal. Beides zugleich geht, wenn man die
    Schaetzung gegen sich selbst laufen laesst: `anteil · fuellgrad(htk)` ist der Anteil, der
    uebrig bliebe, wenn sich der Markt noch wie ueblich auffuellt.
    """

    def _pos(self, usd=6000, **over):
        p = {"wallet": "0xw", "key": "k", "side": "A", "usd": usd, "league": "ESPORTS",
             "firstPrice": 0.55, "lastPrice": 0.55, "firstTs": NOW.isoformat()}
        p.update(over)
        return p

    def _b(self, total, htk, seite=None):
        seite = total / 2.0 if seite is None else seite
        return {"k": {"totalUsd": total, "hoursToKickoff": htk,
                      "capturedAt": NOW.isoformat(),
                      "shares": {"A": seite, "B": max(total - seite, 1.0)}}}

    def test_der_fuellgrad_kommt_aus_der_messung(self):
        self.assertEqual(P.fuellgrad(0.3), 1.00)
        self.assertEqual(P.fuellgrad(0.8), 0.92)
        self.assertEqual(P.fuellgrad(1.4), 0.82)
        self.assertEqual(P.fuellgrad(2.8), 0.54)
        self.assertEqual(P.fuellgrad(0), 1.0, "ab Anpfiff ist der Markt fertig")
        self.assertEqual(P.fuellgrad(-1), 1.0)

    def test_frueher_als_gemessen_bleibt_beim_leersten_band(self):
        """Ueber 3 h gibt es keine Messung. Zu extrapolieren waere eine Behauptung — das
        leerste gemessene Band ist die konservative Wahl."""
        self.assertEqual(P.fuellgrad(50), 0.54)

    def test_kein_fuellgrad_ohne_stunde(self):
        for bad in (None, "1.5", True):
            self.assertIsNone(P.fuellgrad(bad), repr(bad))

    def test_deutliche_dominanz_kommt_frueh_raus(self):
        """80 % bei 2,8 h: auch wenn sich der Markt auf seinen Median-Endstand auffuellt
        (× 0,54), blieben 43 % — ueber der Schwelle. Also sofort, nicht in zwei Stunden."""
        tr = {"open": {"0xw|k|A": self._pos(usd=9600)}, "scores": {"0xw": SHARP}}
        br = self._b(24000, 2.8, seite=12000)          # 9.600 von 12.000 der Seite = 80 %
        r = P.dominanz_kandidaten(tr, br, now=NOW)
        self.assertEqual(len(r), 1)
        _h, frueh = P.dom_freigabe(r[0][1], br, now=NOW)
        self.assertTrue(frueh, "als fruehe Freigabe gekennzeichnet")

    def test_knappe_dominanz_wartet(self):
        """45 % bei 2,8 h werden konservativ zu 24 % — das traegt nicht. Sie ist NICHT
        verworfen: sobald der Markt steht, kommt sie auf dem normalen Weg."""
        tr = {"open": {"0xw|k|A": self._pos(usd=5400)},
              "scores": {"0xw": SHARP}}                                  # 45 % der Seite
        self.assertEqual(P.dominanz_kandidaten(tr, self._b(24000, 2.8, seite=12000), now=NOW), [])
        self.assertEqual(len(P.dominanz_kandidaten(tr, self._b(24000, 0.5, seite=12000),
                                                   now=NOW)), 1)

    def test_die_karte_sagt_dass_der_markt_noch_waechst(self):
        """Bei einer fruehen Freigabe MUSS auf der Karte stehen, dass der Nenner noch waechst —
        sonst liest Lucas 80 % als Endstand, und der Fuellgrad ist ein Median, kein Versprechen."""
        k = P.build_dominanz_card(self._pos(usd=9600), {},
                                  self._b(24000, 2.8, seite=12000), now=NOW)
        self.assertIn("füllt sich noch", k)
        self.assertIn("kann noch fallen", k)

    def test_beim_reifen_markt_steht_das_gegenteil(self):
        k = P.build_dominanz_card(self._pos(), {}, self._b(24000, 0.5, seite=12000), now=NOW)
        self.assertIn("Markt steht", k)
        self.assertNotIn("füllt sich noch", k)

    def test_die_fruehe_freigabe_haengt_am_fuellgrad_nicht_an_der_stunde(self):
        """Gegenprobe: dieselbe Position, dieselbe Stunde — nur der Anteil entscheidet."""
        br = self._b(24000, 2.8, seite=12000)
        self.assertIsNotNone(P.dom_freigabe(self._pos(usd=9600), br, now=NOW))   # 80 % × 0,54
        self.assertIsNone(P.dom_freigabe(self._pos(usd=6000), br, now=NOW))      # 50 % × 0,54


class TestKleinmarktSpur(unittest.TestCase):
    """Lucas 11.09.2026: „wir muessen da an Logik Fehler haben, weil ich will ja herausfinden,
    Spiele bei Poly, die kleine Maerkte sind und wo ein eventuelles Sharp Wallet hoeher sitzt …
    wenn der auf ein Tennis-Match viertausend setzt und es sind maximal fuenftausend drin."

    🔴 Er hatte recht, und der Fehler lag NICHT bei den Schwellen dieses Bands. Der Wallet-Track
    wird aus `pre` gespeist, und `pre` hat den $7.500-Boden aus `poly_money_broad.MIN_VOL_USD` —
    unter dem wird gar kein Holder-Call gemacht, also erfahren wir nie, wer dort wie viel haelt.
    Gemessen: kleinster Markt mit Wal-Daten $7.504, in 2.928 Close-Zeilen keine einzige darunter.
    Das Band suchte kleine Maerkte in einem Bestand, aus dem kleine Maerkte entfernt waren.
    """

    def _klein(self, usd=4000, tot=5000, htk=0.66, league="TENNIS"):
        return {"atp-a-b-2026-09-12": {
            "league": league, "sport": "Tennis", "totalUsd": tot, "hoursToKickoff": htk,
            "capturedAt": NOW.isoformat(),
            "prices": {"Spieler A": 0.62, "Spieler B": 0.38},
            # Das Geld auf der eigenen Seite ist der Nenner (seiten_anteil). $4.000 von $5.000
            # dort sind die 80 %, die Lucas beschrieben hat.
            "shares": {"Spieler A": 5000.0, "Spieler B": 3000.0},
            "whales": [{"wallet": "0xabc", "side": "Spieler A", "usd": usd}]}}

    def _scores(self):
        return {"0xabc": {"n": 63, "wins": 53, "clvSumPP": 44.0, "pnl": 5200}}   # besteht sharp_gate

    def test_lucas_fall_woertlich(self):
        """$4.000 auf ein Tennis-Match, maximal $5.000 drin. Genau der Fall, den er beschrieben
        hat — und der vorher in KEINER Datei stand, die dieses Band lesen konnte."""
        tr = {"open": {}, "scores": self._scores()}
        r = P.dominanz_kandidaten(tr, {}, klein=self._klein(), now=NOW)
        self.assertEqual(len(r), 1)
        self.assertAlmostEqual(r[0][2], 0.8, places=3)

    def test_positionen_werden_aus_den_marktzeilen_abgeleitet(self):
        pos = P.klein_positionen(self._klein())
        self.assertEqual(len(pos), 1)
        p = pos["0xabc|atp-a-b-2026-09-12|Spieler A"]
        self.assertEqual(p["usd"], 4000)
        self.assertEqual(p["side"], "Spieler A")
        self.assertEqual(p["firstPrice"], 0.62)
        self.assertEqual(p["quelle"], "klein", "die Spur muss am Datensatz stehen")

    def test_der_einstieg_des_wals_wird_nicht_erfunden(self):
        """Wir wissen nur, dass die Wallet JETZT da ist — nicht, zu welchem Preis sie rein ist.
        Ein „Einstieg @1,61", der in Wahrheit der Jetzt-Preis ist, waere eine erfundene Zahl an
        genau der Stelle, an der Lucas die Bewegung ablesen wuerde."""
        pos = P.klein_positionen(self._klein())["0xabc|atp-a-b-2026-09-12|Spieler A"]
        self.assertIsNone(pos["htkFirst"], "der Vorlauf der Wallet ist hier unbekannt")
        k = P.build_dominanz_card(pos, self._scores(), self._klein(), 0.8, NOW)
        self.assertNotIn("Einstieg", k)
        self.assertIn("📈", k, "der aktuelle Preis steht sehr wohl da")

    def test_der_marktboden_gilt_hier_nicht(self):
        """Er waere ein Widerspruch in sich: die Spur existiert, WEIL diese Maerkte darunter
        liegen. Ihr Boden steht dort, wo entschieden wird, welcher Markt abgefragt wird."""
        tr = {"open": {}, "scores": self._scores()}
        self.assertEqual(len(P.dominanz_kandidaten(tr, {}, klein=self._klein(tot=5000),
                                                   now=NOW)), 1,
                         "$5.000 liegen unter DOM_MIN_MARKET und muessen trotzdem durch")

    def test_die_haupt_spur_behaelt_ihren_boden(self):
        """Gegenprobe: derselbe Markt ueber den Wallet-Track gelesen faellt am Boden — sonst
        haette die neue Spur still den alten Boden mit aufgehoben."""
        pos = P.klein_positionen(self._klein())["0xabc|atp-a-b-2026-09-12|Spieler A"]
        pos = dict(pos); pos.pop("quelle")
        tr = {"open": {"0xabc|atp-a-b-2026-09-12|Spieler A": pos}, "scores": self._scores()}
        br = {"atp-a-b-2026-09-12": dict(self._klein()["atp-a-b-2026-09-12"])}
        self.assertEqual(P.dominanz_kandidaten(tr, br, now=NOW), [])

    def test_bei_kollision_gewinnt_die_close_zeile(self):
        """Ein Markt, der ueber den Boden gewachsen ist, steht in beiden Dateien. Die
        eingefrorene Close-Zeile ist die belastbarere — sie muss den Nenner stellen."""
        kl = self._klein(tot=5000)
        br = {"atp-a-b-2026-09-12": dict(kl["atp-a-b-2026-09-12"], totalUsd=40000,
                                         shares={"Spieler A": 20000.0, "Spieler B": 20000.0})}
        tr = {"open": {}, "scores": self._scores()}
        r = P.dominanz_kandidaten(tr, br, klein=kl, now=NOW)
        self.assertEqual(r, [], "$4.000 von $20.000 auf der Seite sind 20 % — unter der Schwelle")

    def test_beide_spuren_laufen_nebeneinander(self):
        tr = {"open": {"0xw|k|A": {"wallet": "0xw", "key": "k", "side": "A", "usd": 6000,
                                   "league": "ESPORTS", "firstPrice": 0.55, "lastPrice": 0.55,
                                   "firstTs": NOW.isoformat()}},
              "scores": dict(self._scores(), **{"0xw": SHARP})}
        br = {"k": {"totalUsd": 12000, "hoursToKickoff": 0.5, "capturedAt": NOW.isoformat(),
                    "shares": {"A": 8000.0, "B": 4000.0}}}
        r = P.dominanz_kandidaten(tr, br, klein=self._klein(), now=NOW)
        self.assertEqual(len(r), 2)
        self.assertEqual({p.get("quelle") or "track" for _, p, _ in r}, {"track", "klein"})

    def test_die_spur_steht_im_buch(self):
        """Zusammengerechnet waeren es zwei Dinge unter einer Trefferquote: die Kleinmarkt-Spur
        kennt den Einstieg nicht und misst in einem anderen Groessenbereich."""
        pos = P.klein_positionen(self._klein())["0xabc|atp-a-b-2026-09-12|Spieler A"]
        self.assertEqual(pos.get("quelle"), "klein")

    def test_kaputte_zeilen_reissen_die_spur_nicht_mit(self):
        for kaputt in ({}, {"k": None}, {"k": {}}, {"k": {"whales": "x"}},
                       {"k": {"whales": [{"wallet": None, "side": "A", "usd": 1}]}},
                       {"k": {"whales": [{"wallet": "0x", "side": "A"}], "prices": {"A": 0.5}}},
                       {"k": {"whales": [{"wallet": "0x", "side": "A", "usd": 0}],
                              "prices": {"A": 0.5}}},
                       {"k": {"whales": [{"wallet": "0x", "side": "Z", "usd": 99}],
                              "prices": {"A": 0.5}}}):
            self.assertEqual(P.klein_positionen(kaputt), {}, repr(kaputt))

    def test_ohne_spur_laeuft_alles_wie_vorher(self):
        """Die Spur ist additiv. Faellt die Datei aus, muss das Band weiterlaufen wie bisher —
        nicht leer werden."""
        tr = {"open": {"0xw|k|A": {"wallet": "0xw", "key": "k", "side": "A", "usd": 6000,
                                   "league": "ESPORTS", "firstPrice": 0.55, "lastPrice": 0.55,
                                   "firstTs": NOW.isoformat()}},
              "scores": {"0xw": SHARP}}
        br = {"k": {"totalUsd": 12000, "hoursToKickoff": 0.5, "capturedAt": NOW.isoformat(),
                    "shares": {"A": 8000.0, "B": 4000.0}}}
        for leer in (None, {}, "kaputt"):
            self.assertEqual(len(P.dominanz_kandidaten(tr, br, klein=leer, now=NOW)), 1, repr(leer))


class TestWalletGate(unittest.TestCase):
    """🔴 12.09.2026 (Lucas: „jetzt kommen halt viele solcher pushs").

    Er schickte vier Karten hintereinander. Gemeinsam hatten sie nicht den Markt und nicht den
    Anteil, sondern die WALLETS: 7/15 (47 %), 15/34 (44 %), 266/582 (46 %), 13/24 (54 %) — reine
    Muenzwuerfe. Die grossen Lebensbilanzen daneben ($501K, $295K, $2,53M) stammen aus Wahl- und
    Kryptomaerkten und sagen ueber Sport nichts.

    Das Band hatte nie ein Wallet-Gate, obwohl Lucas' allererster Satz lautete: „Spiele bei Poly,
    die kleine Maerkte sind und wo ein eventuelles SHARP WALLET hoeher sitzt." Ich habe die
    Marktseite dreimal nachgebessert und die Wallet-Seite nie gebaut.

    Gemessen: 32 Kandidaten ohne Gate, 5 mit.
    """

    def _tr(self, score):
        pos = {"wallet": "0xw", "key": "k", "side": "A", "usd": 6000, "league": "ESPORTS",
               "firstPrice": 0.55, "lastPrice": 0.55, "firstTs": NOW.isoformat()}
        return {"open": {"0xw|k|A": pos}, "scores": ({"0xw": score} if score else {})}

    def _br(self):
        return {"k": {"totalUsd": 20000, "hoursToKickoff": 0.4, "capturedAt": NOW.isoformat(),
                      "shares": {"A": 10000.0, "B": 10000.0}}}

    def test_belegte_wallet_kommt_durch(self):
        self.assertEqual(len(P.dominanz_kandidaten(self._tr(SHARP), self._br(), now=NOW)), 1)

    def test_muenzwurf_wallet_bleibt_draussen(self):
        """Die vier gemeldeten Karten, wortwoertlich: 47 %, 44 %, 46 %, 54 % — mit grosser
        Lebensbilanz daneben, die genau nichts beweist."""
        for n, w, pnl in ((15, 7, 501200), (34, 15, 295500), (582, 266, 2530000), (24, 13, 364200)):
            r = P.dominanz_kandidaten(
                self._tr({"n": n, "wins": w, "clvSumPP": 5.0, "pnl": pnl}), self._br(), now=NOW)
            self.assertEqual(r, [], "%d/%d haette nicht rausgehen duerfen" % (w, n))

    def test_grosse_lebensbilanz_ersetzt_keinen_track_record(self):
        """P&L misst ALLE Polymarket-Maerkte (Wahlen, Krypto). Wer +$2,53 Mio hat, kann im Sport
        trotzdem nichts koennen — genau die Vermischung, die sharp_gate.py aufgeloest hat."""
        self.assertEqual(
            P.dominanz_kandidaten(self._tr({"n": 582, "wins": 266, "clvSumPP": 9.0,
                                            "pnl": 2530000}), self._br(), now=NOW), [])

    def test_unbekannte_wallet_bleibt_draussen(self):
        """Fehlende Information laesst nicht durch — dieselbe Regel wie beim Volumen, beim
        Messzeitpunkt und beim Anpfiff."""
        for score in (None, {}, {"n": 2, "wins": 2, "clvSumPP": 4.0}):
            self.assertEqual(P.dominanz_kandidaten(self._tr(score), self._br(), now=NOW), [],
                             repr(score))

    def test_negativer_clv_faellt_raus(self):
        """Eine hohe Trefferquote ohne CLV ist Glueck — steht so in sharp_gate.py."""
        self.assertEqual(
            P.dominanz_kandidaten(self._tr({"n": 60, "wins": 40, "clvSumPP": -30.0}),
                                  self._br(), now=NOW), [])

    def test_es_gilt_die_projektweite_definition(self):
        """Kein eigenes Gate. sharp_gate.py existiert, WEIL es vier verschiedene gab — eine
        fuenfte hier waere genau der Fehler, den diese Datei behoben hat."""
        import sharp_gate as SG
        import inspect
        self.assertIn("SG.is_sharp", inspect.getsource(P.dominanz_kandidaten))

    def test_das_gate_steht_auf_der_karte(self):
        """Wer die Karte liest, soll sehen, dass die Wallet belegt ist — sonst ist die Zeile mit
        dem Track-Record nur Dekoration neben einer Zahl, die ohne sie zustande kam."""
        k = P.build_dominanz_card(self._tr(SHARP)["open"]["0xw|k|A"], {"0xw": SHARP},
                                  self._br(), now=NOW)
        self.assertIn("bewiesene Wallet", k)
        self.assertIn("belegte Wallet", k, "die Fusszeile muss die Regel nennen")

    def test_abschaltbar_ohne_code_eingriff(self):
        """Falls das Band damit zu duenn wird, muss es sich ohne Aenderung drehen lassen."""
        self.assertTrue(hasattr(P, "DOM_NUR_SHARP"))
        self.assertEqual(len(P.dominanz_kandidaten(
            self._tr({"n": 15, "wins": 7, "clvSumPP": 5.0}), self._br(), now=NOW,
        )), 0)


class TestSubMarktAufDerKarte(unittest.TestCase):
    """🔴 11.09.2026 (Lucas: „denke hier sind corner gemeint, bitte anpassen").

    Er konnte einer Dominanz-Karte nicht ansehen, auf WAS gesetzt wurde. Bei der konkreten Karte
    war es der Matchsieger — aber die Fehlerklasse dahinter ist echt: bei einem Ecken-Markt stand
    als Ueberschrift fett „Over" und sonst nichts. Weder die Paarung noch der Markttyp.

    Zwei Ursachen, beide behoben:
      1. `_matchup` fiel nur bei „-more-markets" auf den Hauptmarkt zurueck. Gemessen gibt es
         ACHT Suffixe (more-markets 354, exact-score 288, halftime-result 32, total-corners 30,
         first-to-score 11, player-props 6, …) und bei 612 von 726 Sub-Maerkten ist der
         Hauptmarkt erfasst — nachgeschlagen wurde fuer sieben davon nie.
      2. Die Marktfrage lag vor und wurde nicht gezeigt.
    """

    def _b(self, key, shares, frage=None, basis=None):
        m = {key: {"totalUsd": 40000, "hoursToKickoff": 0.4, "capturedAt": NOW.isoformat(),
                   "shares": shares, "prices": {k: 0.5 for k in shares}}}
        if frage:
            m[key]["frage"] = frage
        if basis:
            m[basis] = {"totalUsd": 90000, "shares": {"Real Betis": 45000.0,
                                                      "Real Madrid": 45000.0},
                        "prices": {"Real Betis": 0.5, "Real Madrid": 0.5}}
        return m

    def _pos(self, key, side, usd=20000):
        return {"wallet": "0xw", "key": key, "side": side, "usd": usd, "league": "LA-LIGA",
                "firstPrice": 0.53, "lastPrice": 0.53, "firstTs": NOW.isoformat()}

    def test_der_basis_markt_wird_am_datum_geschnitten_nicht_an_einer_liste(self):
        """Eine Suffix-Liste liegt beim naechsten neuen Markttyp still daneben — genau die
        Fehlerklasse, die diesen Eintrag ausgeloest hat. Deshalb schneidet die Regel am DATUM."""
        self.assertEqual(P._basis_key("lal-bet-rea-2026-09-04-total-corners"),
                         "lal-bet-rea-2026-09-04")
        self.assertEqual(P._basis_key("x-y-2026-09-04-irgendein-neuer-typ"), "x-y-2026-09-04")
        self.assertIsNone(P._basis_key("atp-munar-brancac-2026-09-11"), "Hauptmarkt hat keinen")
        self.assertIsNone(P._basis_key(None))
        self.assertIsNone(P._basis_key(""))

    def test_die_paarung_kommt_aus_dem_hauptmarkt(self):
        br = self._b("lal-bet-rea-2026-09-04-total-corners", {"Over": 30000.0, "Under": 10000.0},
                     basis="lal-bet-rea-2026-09-04")
        self.assertEqual(P._matchup("lal-bet-rea-2026-09-04-total-corners", br),
                         "Real Betis v Real Madrid")

    def test_eckenmarkt_sagt_dass_es_ecken_sind(self):
        br = self._b("lal-bet-rea-2026-09-04-total-corners", {"Over": 30000.0, "Under": 10000.0},
                     frage="Real Betis vs. Real Madrid: O/U 10.5 Total Corners",
                     basis="lal-bet-rea-2026-09-04")
        k = P.build_dominanz_card(self._pos("lal-bet-rea-2026-09-04-total-corners", "Over"),
                                  {}, br, now=NOW)
        self.assertIn("Real Betis v Real Madrid", k, "die Paarung fehlte ganz")
        self.assertIn("Total Corners", k, "dass es Ecken sind, stand nirgends")

    def test_ohne_erfasste_frage_steht_wenigstens_der_markttyp(self):
        br = self._b("lal-bet-rea-2026-09-04-total-corners", {"Over": 30000.0, "Under": 10000.0},
                     basis="lal-bet-rea-2026-09-04")
        k = P.build_dominanz_card(self._pos("lal-bet-rea-2026-09-04-total-corners", "Over"),
                                  {}, br, now=NOW)
        self.assertIn("Ecken", k)

    def test_die_seite_wird_nie_als_paarung_ausgegeben(self):
        """Der Kern der Meldung: fett „Over" liest sich wie ein Mannschaftsname. Ist die Paarung
        nicht erfasst (114 von 726 Sub-Maerkten), bleibt die Zeile leer — die Seite steht ohnehin
        in der Geldzeile, und eine Ueberschrift, die etwas anderes behauptet als sie ist, ist
        schlechter als keine."""
        br = self._b("kor-jej-any-2026-08-15-more-markets", {"Over": 30000.0, "Under": 10000.0})
        k = P.build_dominanz_card(self._pos("kor-jej-any-2026-08-15-more-markets", "Over"),
                                  {}, br, now=NOW)
        # Geprueft wird die ZEILE, nicht das Vorkommen: „auf <b>Over</b>" in der Geldzeile ist
        # richtig, eine Zeile die NUR „<b>Over</b>" ist, waere die Ueberschrift.
        self.assertNotIn("<b>Over</b>", k.splitlines(),
                         "die Seite darf nicht als Ueberschrift dastehen")
        self.assertIn("📋 <b>Nebenmarkt</b>", k, "dann traegt der Markttyp die Karte")
        self.assertIn("auf <b>Over</b>", k, "die Seite steht weiterhin in der Geldzeile")

    def test_beim_hauptmarkt_wiederholt_sich_nichts(self):
        """Die Frage des Hauptmarkts lautet „Seville: Munar vs Brancaccio" — also genau das, was
        schon in der Ueberschrift steht. Eine Zeile, die sich selbst wiederholt, macht die eine
        Zeile unglaubwuerdig, auf die es ankommt."""
        br = self._b("atp-munar-brancac-2026-09-11",
                     {"Jaume Munar": 30000.0, "Raul Brancaccio": 10000.0},
                     frage="Seville: Jaume Munar vs Raul Brancaccio")
        k = P.build_dominanz_card(self._pos("atp-munar-brancac-2026-09-11", "Jaume Munar"),
                                  {}, br, now=NOW)
        self.assertIn("Jaume Munar v Raul Brancaccio", k)
        self.assertNotIn("📋", k, "beim Hauptmarkt ist die Markt-Zeile Fuelltext")

    def test_markttyp_klartext(self):
        f = P.sub_markt_art
        self.assertEqual(f("x-2026-09-04-total-corners"), "Ecken")
        self.assertEqual(f("x-2026-09-04-halftime-result"), "Halbzeit")
        self.assertEqual(f("x-2026-09-04-exact-score"), "Exaktes Ergebnis")
        self.assertEqual(f("x-2026-09-04-player-props"), "Spieler-Wette")
        self.assertIsNone(f("atp-a-b-2026-09-11"), "Hauptmarkt hat keinen Typ")

    def test_unbekannter_markttyp_faellt_nicht_weg(self):
        """Ein Typ, den die Liste nicht kennt, wird lesbar gemacht statt verschwiegen — sonst
        entsteht wieder eine Karte ohne Auskunft, und das war der Ausloeser."""
        self.assertEqual(P.sub_markt_art("x-2026-09-04-first-set-tiebreak"), "first set tiebreak")


class TestDominanzKarte(unittest.TestCase):
    def _karte(self, usd=6800, tot=9900):
        pos = {"usd": usd, "league": "ESPORTS", "side": "Falcons", "firstPrice": 0.58,
               "entryPrice": 0.58, "wallet": "0xW", "key": "cs2-fal-vit-2026-09-12"}
        return P.build_dominanz_card(
            pos, {}, {"cs2-fal-vit-2026-09-12": {"totalUsd": tot, "hoursToKickoff": 0.75,
                                                 "capturedAt": NOW.isoformat(),
                                                 "shares": {"Falcons": usd / 0.69,
                                                            "X": tot}}})

    def test_die_karte_ist_auf_den_ersten_blick_eine_andere(self):
        """Lucas: „mach's bitte vom Template her so, dass ich's wirklich gleich seh, weil das geht
        sonst unter in den Nachrichten." Rahmen, Balken und Kopfzeile trennen sie von der
        Whale-Karte — die fuehrt mit dem BETRAG, diese mit dem ANTEIL."""
        k = self._karte()
        self.assertIn("MARKT-DOMINANZ", k)
        self.assertIn("━━━", k)
        self.assertTrue(any(c in k for c in "█░"), "der Balken fehlt")
        self.assertIn("69 %", k)
        self.assertNotIn("Polymarket Whale", k)

    def test_die_karte_sagt_dass_sie_nichts_belegt(self):
        """Der Zweck des Bandes steht drauf. Eine Karte, die aussieht wie eine Empfehlung, wird
        als eine gelesen — und die ersten Wochen sind hier reines Rauschen."""
        k = self._karte()
        self.assertIn("Beobachtungsband", k)
        self.assertIn("kein Beleg", k)

    def test_das_marktvolumen_steht_neben_dem_einsatz(self):
        k = self._karte(usd=6800, tot=9900)
        self.assertIn("$6.8K", k)
        self.assertIn("Markt gesamt", k)
        self.assertIn("$9.9K", k)


class TestMarktStempel(unittest.TestCase):
    """11.09.2026 — von 64 Public-Pushs liess sich das Marktvolumen nachtraeglich nur bei 40
    rekonstruieren. Eine Momentaufnahme laesst sich nicht rueckwirkend herstellen."""

    def test_volumen_und_anteil_werden_gebucht(self):
        st = P.markt_stempel({"key": "k", "usd": 20000}, {"k": {"totalUsd": 50000}})
        self.assertEqual(st, {"totalUsd": 50000.0, "anteil": 0.4})

    def test_ohne_volumen_wird_nichts_erfunden(self):
        self.assertEqual(P.markt_stempel({"key": "x", "usd": 20000}, {"k": {"totalUsd": 5}}), {})
        self.assertEqual(P.markt_stempel({"key": "k", "usd": 20000}, None), {})

    def test_widerspruechlicher_nenner_gibt_keinen_anteil(self):
        """Einsatz groesser als der Markt: das Volumen wird gebucht, der Anteil NICHT — sonst
        stuende dort 100 % oder mehr, und beides waere erfunden."""
        st = P.markt_stempel({"key": "k", "usd": 90000}, {"k": {"totalUsd": 50000}})
        self.assertIn("totalUsd", st)
        self.assertNotIn("anteil", st)
