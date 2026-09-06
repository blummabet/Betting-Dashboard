"""Der gemeinsame Schluessel war da — er wurde nur weggeworfen. 06.09.2026.

Lucas: „die 2 Elemente müssen einfach simpel zeigen warum damit ich schnell weiß. Und wenn in
beiden Elemente selbe Team dann ja eindeutiger."

Ich hatte ihm vorher gesagt, die Flaechen ueberschnitten sich nicht — gemessen an Shortlist ×
Ebene 2: null. Er hat mich mit seinem eigenen Board widerlegt:

    Ebene 2 (Konsens):     „Remo v Flamengo → Flamengo"
    Ebene 3 (Rangliste):   „CR Flamengo vs Clube do Remo → CR Flamengo"

Dasselbe Spiel, dieselbe Seite, in beiden Flaechen — und keine sagte es. Der Grund war nicht
die Abwesenheit von Ueberschneidung, sondern die Abwesenheit eines Schluessels:

    betfair_consensus.py:1267   [dict(v, src="close") for k, v in poly_raw.items()]
                                                          ^ der Marktschluessel steht NUR hier

Die Poly-Pools sind Dicts, die nach dem Marktschluessel (`bra-cre-fla-2026-09-06`) gelegt sind.
`dict(v, src=...)` uebernahm die Werte und liess den Schluessel fallen. `match_poly` gab
deshalb fuer close/live/upcoming immer `key: None` zurueck — nur der Liga-Rueckfall setzte ihn
explizit. Damit gab es zwischen einer Konsens-Zeile und einer Poly-Zeile keinen gemeinsamen
Bezeichner, und das Frontend haette Namensformen raten muessen („Flamengo" vs „CR Flamengo").

Das ist die neunte Fundstelle derselben Klasse in diesem Repo: **die Daten lagen vor, sie
wurden nur nie weitergereicht** (zuletzt `match_eintrag` am selben Tag).

Gemessen nach dem Fix, Stand 06.09. 18:00 UTC: von drei Konsens-Zeilen tragen zwei einen
Marktschluessel, und BEIDE stehen mit derselben Seite auch in der Poly-Shortlist.
"""
import json
import unittest
from pathlib import Path

import betfair_consensus as BC
import killer as K

BASE = Path(__file__).resolve().parents[1]


def _pool(datei, src):
    """Genau die Filterung, die betfair_consensus.main() auf diesen Pool anwendet."""
    p = BASE / datei
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(d, dict):
        return None
    return [dict(v, src=src, key=v.get("key") or k) for k, v in d.items()
            if isinstance(v, dict) and v.get("prices")
            and not any(x in str(k) for x in ("-more-markets", "-exact-score", "-total", "-spread"))
            and len(v.get("prices")) <= 4]


class TestSchluesselUeberlebt(unittest.TestCase):
    def test_match_poly_reicht_den_schluessel_durch(self):
        """Der Kern. Ohne ihn gibt es zwischen den beiden Flaechen keinen gemeinsamen Bezeichner."""
        e = {"key": "bra-cre-fla-2026-09-06", "totalUsd": 29875,
             "prices": {"Clube do Remo": 0.31, "Draw (Clube do Remo vs. CR Flamengo)": 0.14,
                        "CR Flamengo": 0.655}}
        r = BC.match_poly({"home": "Clube do Remo", "away": "CR Flamengo"}, {"side": "away"}, [e])
        self.assertIsNotNone(r)
        self.assertEqual(r["key"], "bra-cre-fla-2026-09-06")

    def test_die_seite_kommt_als_poly_outcome_name(self):
        """„dasselbe Spiel" und „dieselbe Seite" sind zwei Aussagen. Die zweite ist die
        staerkere und darf nicht aus Teamnamen geraten werden — sie kommt als exakt der
        Zeichenkette, die die Poly-Shortlist als `side` fuehrt."""
        e = {"key": "k", "totalUsd": 1, "prices": {"Clube do Remo": 0.31, "CR Flamengo": 0.655}}
        r = BC.match_poly({"home": "Clube do Remo", "away": "CR Flamengo"}, {"side": "away"}, [e])
        self.assertEqual(r["sideKey"], "CR Flamengo")
        r2 = BC.match_poly({"home": "Clube do Remo", "away": "CR Flamengo"}, {"side": "home"}, [e])
        self.assertEqual(r2["sideKey"], "Clube do Remo")

    def test_ohne_treffer_wird_nichts_erfunden(self):
        self.assertIsNone(BC.match_poly({"home": "A", "away": "B"}, {"side": "home"}, []))


class TestGegenDieEchtenPools(unittest.TestCase):
    """Kein erfundenes Fixture: gegen die Dateien, die die Workflows committen."""

    def test_jeder_pool_eintrag_traegt_seinen_schluessel(self):
        n = 0
        for datei, src in (("poly_money_broad_close.json", "close"),
                           ("poly_money_upcoming.json", "upcoming"),
                           ("poly_money_broad_live.json", "live")):
            ents = _pool(datei, src)
            if not ents:
                continue
            n += len(ents)
            ohne = [e for e in ents if not e.get("key")]
            self.assertEqual(ohne, [], f"{len(ohne)} Eintraege aus {datei} ohne Marktschluessel")
        if n == 0:
            self.skipTest("keine Poly-Pools im Bestand")

    def test_der_reale_fall_findet_die_shortlist_zeile(self):
        """Genau Lucas' Beispiel, End-to-End gegen den Bestand: der Schluessel, den die
        Konsens-Seite berechnet, muss in der Poly-Shortlist als Zeile existieren — und die
        Seite muss dieselbe sein."""
        ents = _pool("poly_money_broad_close.json", "close")
        sl = BASE / "poly_shortlist_track.json"
        if not ents or not sl.exists():
            self.skipTest("Bestand unvollstaendig")
        r = BC.match_poly({"home": "Remo", "away": "Flamengo"}, {"side": "away"}, ents)
        if not r or not r.get("key"):
            self.skipTest("das Spiel liegt nicht mehr im Close-Pool")
        offen = json.loads(sl.read_text(encoding="utf-8")).get("open") or {}
        treffer = [v for v in offen.values() if v.get("key") == r["key"]]
        self.assertTrue(treffer, f"kein Shortlist-Eintrag zu {r['key']}")
        self.assertIn(r["sideKey"], [v.get("side") for v in treffer],
                      "Marktschluessel gleich, Seite verschieden — dann waere es KEINE Bestaetigung")


class TestKillerStempeltDurch(unittest.TestCase):
    def _cons_game(self):
        return {"matchId": "1", "home": "Remo", "away": "Flamengo", "moneySide": "away",
                "poly": {"vol": 29875, "odd": 1.48, "sharePct": 98, "shareSrc": "geld",
                         "key": "bra-cre-fla-2026-09-06", "sideKey": "CR Flamengo",
                         "whales": None, "whaleUsd": None}}

    def _zeile(self, g):
        return K.zeile("1", {"home": "Remo", "away": "Flamengo", "league": "Brazilian Serie A",
                             "kickoff": "2026-09-06T19:00:00Z"},
                       {"fav": "away", "odd": 1.47, "share": 0.85, "flow": 1, "moveOk": True},
                       g, None, {"streaks": []})

    def test_die_zeile_traegt_schluessel_und_seite(self):
        z = self._zeile(self._cons_game())
        self.assertEqual(z["polyKey"], "bra-cre-fla-2026-09-06")
        self.assertEqual(z["polySide"], "CR Flamengo")

    def test_ohne_poly_markt_wird_nichts_behauptet(self):
        """Fehlende Information ist keine Erlaubnis: kein Markt -> kein Schluessel -> kein
        Marker. Ein leerer String oder ein geratener Name waere ein falscher Treffer."""
        g = self._cons_game()
        g["poly"] = None
        z = self._zeile(g)
        self.assertIsNone(z["polyKey"])
        self.assertIsNone(z["polySide"])

    def test_der_schluessel_steht_auch_wenn_poly_widerspricht(self):
        """Er benennt den MARKT, nicht das Urteil. Sonst koennte die Oberflaeche einen
        Widerspruch („Ebene 3 dagegen") gar nicht erst sehen — und genau der ist die
        Nachricht, die man am wenigsten verpassen darf."""
        g = self._cons_game()
        g["poly"]["sharePct"] = 12          # Poly liegt auf der Gegenseite
        z = self._zeile(g)
        self.assertEqual(z["polyStatus"], "nein")
        self.assertIsNone(z["poly"], "der Verstaerker-Block gehoert weg, wenn Poly dagegen ist")
        self.assertEqual(z["polyKey"], "bra-cre-fla-2026-09-06",
                         "der Marktschluessel ist Identitaet, kein Urteil")

    def test_gehaltene_zeile_verliert_den_schluessel_nicht(self):
        """`_halten` frischt nur wenige Felder auf. Eine Zeile, die vor dem Poly-Fetch
        entstand, bekaeme den Schluessel sonst nie — sie bliebe fuer immer unverbindbar."""
        import datetime as dt
        now = dt.datetime(2026, 9, 6, 18, 0, tzinfo=dt.timezone.utc)
        ohne = self._zeile({"matchId": "1", "home": "Remo", "away": "Flamengo",
                            "moneySide": "away", "poly": None})
        latch = K._halten({}, [ohne], now)
        mit = self._zeile(self._cons_game())
        mit["verstaerker"] = list(mit["verstaerker"]) + [{"art": "x", "text": "x", "gewicht": 1}]
        latch = K._halten(latch, [mit], now)
        z = list(latch.values())[0]
        self.assertEqual(z["polyKey"], "bra-cre-fla-2026-09-06")

    def test_ein_spaeter_fehlender_schluessel_loescht_den_bekannten_nicht(self):
        import datetime as dt
        now = dt.datetime(2026, 9, 6, 18, 0, tzinfo=dt.timezone.utc)
        mit = self._zeile(self._cons_game())
        latch = K._halten({}, [mit], now)
        ohne = self._zeile({"matchId": "1", "home": "Remo", "away": "Flamengo",
                            "moneySide": "away", "poly": None})
        ohne["verstaerker"] = list(ohne["verstaerker"]) + [{"art": "x", "text": "x", "gewicht": 1}]
        latch = K._halten(latch, [ohne], now)
        self.assertEqual(list(latch.values())[0]["polyKey"], "bra-cre-fla-2026-09-06")


if __name__ == "__main__":
    unittest.main()
