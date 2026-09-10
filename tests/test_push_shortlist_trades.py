#!/usr/bin/env python3
"""test_push_shortlist_trades.py — 05.08.2026 (Lucas): „Heute spielenswert"-Plays in den Trades-
Channel. Reine Funktionen (Auswahl/Dedup/Format), kein Netz/kein node."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import push_shortlist_trades as P


def _play(key, side, conv, verdict="BET", price=0.6, league="UCL", htk=1.0, reasons=None,
          match=None, public=True):
    # 07.09.2026: `public` kam dazu und ist hier per Default True. Seit dem 07.09. haengt die
    # Auswahl am Public-Tor statt allein an der Conviction (gemessen: conv>=7 brachte +2,6 %
    # ROI ueber 165 Plays, das Tor +6,4 % ueber 167 — bei praktisch gleichem Volumen). Die Tests
    # in dieser Datei pruefen Preis-Deckel, Sperrliste, Sortierung und Deckel — nicht das Tor.
    # Damit sie weiter genau das pruefen, kommen ihre Plays durchs Tor. Das Tor selbst hat eine
    # eigene Datei: tests/test_push_shortlist_tor.py.
    return {"key": key, "side": side, "conv": conv, "verdict": verdict, "price": price,
            "league": league, "htk": htk, "reasons": reasons or ["Steam läuft rein (+3pp)"],
            "match": match or (key + " match"), "public": public}


class TestSelect(unittest.TestCase):
    def test_conv_gate_and_sort_and_cap(self):
        # 29.08.2026: relativ zu MIN_CONV formuliert. Vorher standen hier die festen 7/8/9/10 —
        # beim Nachziehen der Skala (Wallet-Neugewichtung) waere der Test gekippt, obwohl an der
        # Auswahl-Logik nichts falsch war. Geprueft gehoert: knapp drunter fliegt raus, der Rest
        # kommt absteigend.
        raus = P.MIN_CONV - 1
        plays = [_play("a", "H", raus), _play("b", "H", P.MIN_CONV + 3),
                 _play("c", "H", P.MIN_CONV + 1), _play("d", "H", P.MIN_CONV + 2)]
        sel = P.select(plays)
        self.assertEqual([p["conv"] for p in sel],
                         [P.MIN_CONV + 3, P.MIN_CONV + 2, P.MIN_CONV + 1])
        self.assertTrue(all(p["conv"] >= P.MIN_CONV for p in sel))

    def test_only_bet_and_fade(self):
        plays = [_play("a", "H", 10, verdict="NOBET"), _play("b", "H", 10, verdict="FADE")]
        sel = P.select(plays)
        self.assertEqual([p["key"] for p in sel], ["b"])

    def test_price_ceiling_skips_quasi_lock(self):
        plays = [_play("lock", "No", 10, price=0.97), _play("ok", "H", 10, price=0.80)]
        sel = P.select(plays)
        self.assertEqual([p["key"] for p in sel], ["ok"])   # 97¢ = Quasi-Lock raus

    def test_cap_max_plays(self):
        plays = [_play(str(i), "H", 10) for i in range(20)]
        self.assertEqual(len(P.select(plays)), P.MAX_PLAYS)


class TestFresh(unittest.TestCase):
    def test_new_is_fresh(self):
        sel = [_play("a", "H", 9)]
        self.assertEqual(P.fresh_plays(sel, {}), sel)

    def test_seen_same_conv_not_fresh(self):
        sel = [_play("a", "H", 9)]
        seen = {"a|H": {"conv": 9, "ts": "2026-08-05T10:00:00+00:00"}}
        self.assertEqual(P.fresh_plays(sel, seen), [])

    def test_conv_increase_repushes_same_or_lower_does_not(self):
        # 05.08.2026 (Lucas: „wenn 7->8 steigt, trotzdem schicken"): Re-Push nur bei neuem Hoechststand.
        seen = {"a|H": {"conv": 8, "ts": "2026-08-05T10:00:00+00:00"}}
        self.assertEqual(len(P.fresh_plays([_play("a", "H", 9)], seen)), 1)   # 8 -> 9: erneut schicken
        self.assertEqual(P.fresh_plays([_play("a", "H", 8)], seen), [])       # gleich: nicht
        self.assertEqual(P.fresh_plays([_play("a", "H", 8)], {"a|H": {"conv": 9}}), [])  # niedriger: nicht


class TestFormat(unittest.TestCase):
    def test_line_core_fields(self):
        ln = P._line(_play("mlb-a-b", "Yankees", 9, price=0.66, league="MLB", htk=2.0,
                           reasons=["großes Geld auf Yankees (70%)"], match="Yankees vs Red Sox"))
        self.assertIn("9/10 · BET", ln)
        self.assertIn("⚾", ln)                    # Sport-Icon
        self.assertIn("Yankees vs Red Sox", ln)
        self.assertIn("→ <b>Yankees</b> @66¢", ln)
        self.assertNotIn("LIVE", ln)              # htk>0 = nicht live

    def test_line_live_badge(self):
        ln = P._line(_play("ucl-x", "Yes", 10, htk=-1.5, match="ucl fen stu1"))
        self.assertIn("🔴 <b>LIVE</b>", ln)
        self.assertIn("ucl fen stu1", ln)         # Yes/No-Label aus dem Key (kein „Yes")

    def test_build_message_header_and_footer(self):
        msg = P.build_message([_play("a", "H", 10, match="A vs B")])
        self.assertIn("🔥 <b>Heute spielenswert</b>", msg)
        self.assertIn("Kein Auto-Bet", msg)
        self.assertIn("A vs B", msg)


if __name__ == "__main__":
    unittest.main()


class TestSperrliste(unittest.TestCase):
    """29.08.2026 (Lucas-Audit: „welche Wallets kommen in den Push"). Der Trades-Push nahm
    `_pwTopPlays(0,false,false)` roh entgegen und filterte auf Conviction, Verdict und Preis —
    aber NICHT auf die Sperrliste. US-Sport und Kampfsport sind seit dem 24.08. vom Setzen und aus
    dem oeffentlichen Schaufenster raus (78 Plays, -29,6% ROI im Papier-Depot); im Trades-Channel
    liefen sie weiter. `cat` steht seit dem 24.08. an jedem Play, `blockedCats` im selben Emit —
    verglichen wurde es nur nie."""

    def test_gesperrte_kategorie_faellt_raus(self):
        plays = [_play("mlb", "H", P.MIN_CONV + 2), _play("epl", "H", P.MIN_CONV)]
        plays[0]["cat"] = "US-Sport"
        plays[1]["cat"] = "Fussball"
        sel = P.select(plays, ["US-Sport", "Kampfsport"])
        self.assertEqual([p["key"] for p in sel], ["epl"])

    def test_ohne_sperrliste_unveraendert(self):
        plays = [_play("mlb", "H", P.MIN_CONV)]
        plays[0]["cat"] = "US-Sport"
        self.assertEqual(len(P.select(plays)), 1)          # kein Argument -> altes Verhalten
        self.assertEqual(len(P.select(plays, [])), 1)      # leere Liste -> nichts gesperrt

    def test_play_ohne_kategorie_bleibt(self):
        # Nicht wissen ist kein Verbot: aeltere Emits ohne `cat` sollen nicht stumm verschwinden.
        plays = [_play("alt", "H", P.MIN_CONV)]
        self.assertEqual(len(P.select(plays, ["US-Sport"])), 1)


# ── Die Minute gehört in die Zeile ───────────────────────────────────────────
# 03.09.2026 (Lucas): „nur da war das Spiel schon 3:0 und in der 92. Minute oder so … eher
# wertlos oder?" — das eigentliche Loch sitzt in poly-wallets.js (ein LIVE-Play wurde mit den
# Zahlen VOR Anpfiff bewertet, s. tests/frontend/live-play-basis.test.mjs). Hier geht es nur
# darum, dass die Nachricht selbst nicht mehr verschweigt, wie weit das Spiel ist.

def test_spielminute_aus_htk():
    assert P._spielminute(-1.55) == 93
    assert P._spielminute(-0.5) == 30
    assert P._spielminute(-1.0) == 60


def test_spielminute_vor_anpfiff_ist_none():
    assert P._spielminute(0.5) is None
    assert P._spielminute(0) is None
    assert P._spielminute(None) is None
    assert P._spielminute("gleich") is None


def test_zeile_nennt_die_spielminute():
    z = P._line({"conv": 8, "verdict": "BET", "match": "A vs B", "side": "A",
                 "price": 0.48, "htk": -1.55, "league": "SOCCER", "preisQuelle": "live"})
    assert "93. Min" in z, z
    assert "LIVE" in z


def test_zeile_warnt_wenn_der_preis_aus_dem_vorspiel_stammt():
    z = P._line({"conv": 8, "verdict": "BET", "match": "A vs B", "side": "A",
                 "price": 0.48, "htk": -1.55, "league": "SOCCER", "preisQuelle": "close"})
    assert "Vorspiel" in z, ("ein Live-Play mit Vorspiel-Preis muss das sagen — genau diese "
                             "Kombination war der Hapoel-Push")


def test_zeile_vor_anpfiff_bleibt_ohne_live_marker():
    z = P._line({"conv": 8, "verdict": "BET", "match": "A vs B", "side": "A",
                 "price": 0.48, "htk": 3.0, "league": "SOCCER"})
    assert "LIVE" not in z
    assert "Min" not in z


class TestPushBuch(unittest.TestCase):
    """10.09.2026 (Lucas: „Heute spielenswert Trades — wird das erst seit kurzem getrackt?").

    Nein — es vergass. Die Stats-Seite las `shortlist_push_seen.json`, ein Dedup-Buch mit drei
    Tagen TTL, das sich bei jedem Lauf selbst aufraeumt. „Heute spielenswert" war damit als
    einziger der fuenf Push-Kanaele ohne eigenes Buch.
    """

    def test_das_buch_haelt_zeitpunkt_und_push_preis(self):
        z = P.buch_zeilen([_play("k1", "Over", 7, price=0.62)], "2026-09-10T12:00:00+00:00")
        self.assertEqual(len(z), 1)
        self.assertEqual(z[0]["k"], "k1|Over")
        self.assertEqual(z[0]["sentAt"], "2026-09-10T12:00:00+00:00")
        self.assertEqual(z[0]["pushPreis"], 0.62)
        self.assertEqual(z[0]["conv"], 7)

    def test_ein_nicht_gesendeter_push_wird_NICHT_gebucht(self):
        """Vorschau-Lauf ohne Token, oder Telegram hat abgelehnt. „Wir haetten gesendet" ist
        keine Handlung — eine Bilanz darauf waere erfunden."""
        self.assertEqual(P.buch_zeilen([_play("k1", "Over", 7)], "2026-09-10T12:00:00+00:00",
                                       gesendet=False), [])

    def test_ein_unbrauchbarer_preis_wird_nicht_gerundet_sondern_weggelassen(self):
        """Fehlende Information rendert als nichts. Ein Preis von 0 oder 1 ist kein Einstieg,
        und eine erfundene Zahl waere schlimmer als keine — die Stats-Seite zeigt dann eine
        Zeile ohne Rendite statt einer falschen."""
        for schlecht in (None, 0.0, 1.0, 1.5, -0.2, "teuer"):
            z = P.buch_zeilen([_play("k1", "Over", 7, price=schlecht)],
                              "2026-09-10T12:00:00+00:00")
            self.assertIsNone(z[0]["pushPreis"], repr(schlecht))

    def test_zeilen_ohne_key_oder_seite_kommen_nicht_ins_buch(self):
        z = P.buch_zeilen([{"key": "k", "conv": 7}, {"side": "Over", "conv": 7}, "kaputt"],
                          "2026-09-10T12:00:00+00:00")
        self.assertEqual(z, [])

    def test_das_buch_rechnet_nicht_selbst_ab(self):
        """Der Ausgang steht in poly_shortlist_track.json — das seit dem 10.09. weiss, wann ein
        Buendel-Markt ueberhaupt entscheiden darf. Zwei Abrechnungen mit zwei Regeln waren in
        diesem Repo schon einmal der Fehler (s. poly_slug_urteil.py)."""
        z = P.buch_zeilen([_play("k1", "Over", 7)], "2026-09-10T12:00:00+00:00")
        for feld in ("result", "win", "pnl", "settledAt", "winner"):
            self.assertNotIn(feld, z[0], feld)
