"""Der Trades-Push haengt am Public-Tor, nicht mehr an der Conviction — 07.09.2026.

Lucas: „das haett ich gern dann halt auch als Push in den Trades Channel."

Vorher war der Push eine VIERTE Menge, verschieden von der Uebersichts-Kachel (Top 3 nach Score)
und von den Public-Kandidaten. Gemessen an 570 abgerechneten, spielbaren Plays:

    Topf: alle spielbaren BET-Plays     n=570   63,3 %   +6,85 EUR    ROI +0,1 %
    Trades-Push bisher (conv>=7)        n=165   64,8 %   +42,86 EUR   ROI +2,6 %
    Public-Kandidaten (das Tor)         n=167   70,7 %   +107,22 EUR  ROI +6,4 %

Praktisch dasselbe Volumen (7,5 gegen 8,0 Plays je Tag), zweieinhalbfacher Gewinn. Die
Conviction-Schwelle war eine Naeherung an „stark"; das Tor misst es.
"""
import unittest

import push_shortlist_trades as P


def play(key, conv=7, public=True, cat="E-Sport", price=0.62, verdict="BET"):
    return {"key": key, "side": "X", "conv": conv, "public": public,
            "cat": cat, "price": price, "verdict": verdict}


class TestAuswahlHaengtAmTor(unittest.TestCase):
    def test_nur_was_durchs_tor_kommt(self):
        sel = P.select([play("a", conv=9, public=False), play("b", conv=6, public=True)], [])
        self.assertEqual([p["key"] for p in sel], ["b"],
                         "Conviction 9 ohne Tor ist kein Push mehr")

    def test_die_conviction_bleibt_als_zweite_schranke(self):
        """Das Tor beginnt bei 6. Faellt PW_PUBLIC_MIN_CONV, soll der Push nicht mitrutschen."""
        sel = P.select([play("tief", conv=P.MIN_CONV - 1, public=True)], [])
        self.assertEqual(sel, [])

    def test_gesperrte_kategorien_bleiben_draussen(self):
        sel = P.select([play("us", cat="US-Sport"), play("ok", cat="Fußball")],
                       ["US-Sport", "Kampfsport"])
        self.assertEqual([p["key"] for p in sel], ["ok"])

    def test_quasi_locks_bleiben_draussen(self):
        self.assertEqual(P.select([play("lock", price=0.95)], []), [])

    def test_staerkste_zuerst_und_gedeckelt(self):
        viele = [play("k%d" % i, conv=6 + (i % 4)) for i in range(20)]
        sel = P.select(viele, [])
        self.assertLessEqual(len(sel), P.MAX_PLAYS)
        self.assertEqual([p["conv"] for p in sel], sorted([p["conv"] for p in sel], reverse=True))

    def test_ein_altes_emit_ohne_das_feld_pusht_NICHTS(self):
        """Ein Rueckfall auf conv>=MIN_CONV waere die ALTE Menge unter neuem Namen — und niemand
        wuerde es bemerken, weil weiterhin Pushes kaemen. Fehlende Information ist keine
        Erlaubnis."""
        alt = [{"key": "x", "side": "Y", "conv": 9, "cat": "E-Sport",
                "price": 0.6, "verdict": "BET"}]           # kein `public`
        self.assertEqual(P.select(alt, []), [])

    def test_das_alt_emit_wird_ausdruecklich_gemeldet_statt_still_zu_schweigen(self):
        """🔴 Beim Gegenbeweis aufgefallen: die `_hat_flag`-Sperre in select() ist redundant —
        `_tor()` filtert Alt-Zeilen ohnehin weg, und der Test oben blieb gruen, als ich die
        Sperre entfernte. Ein Waechter, den man nicht zum Anschlagen bringt, ist Dekoration.

        Was wirklich zaehlt und hier geprueft wird: main() SAGT es, statt still null Plays zu
        melden. Der Unterschied ist der zwischen „heute kam nichts durch das Tor" und „das
        Feld fehlt seit drei Tagen und niemand hat es gemerkt"."""
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1] / "push_shortlist_trades.py").read_text(encoding="utf-8")
        self.assertIn("Emit ohne `public`-Feld", src,
                      "der Fall muss benannt werden, nicht als leeres Ergebnis durchgehen")
        self.assertIn("es wird NICHTS gepusht", src)

    def test_public_false_ist_etwas_anderes_als_fehlend(self):
        """Ein Emit, das `public` FUEHRT und false sagt, ist gueltig — dann gibt es eben
        gerade nichts zu pushen, und das ist eine Aussage."""
        self.assertEqual(P.select([play("a", public=False)], []), [])

    def test_fade_bleibt_erlaubt_wenn_es_durchs_tor_kommt(self):
        sel = P.select([play("f", verdict="FADE")], [])
        self.assertEqual([p["key"] for p in sel], ["f"])

    def test_die_schwelle_passt_zum_tor(self):
        """PW_PUBLIC_MIN_CONV ist 6. Stuende hier 7, waere die Conviction heimlich das
        schaerfere Kriterium und das Tor haette nur die halbe Wirkung."""
        from pathlib import Path
        js = (Path(__file__).resolve().parents[1] / "poly-wallets.js").read_text(encoding="utf-8")
        import re
        m = re.search(r"const PW_PUBLIC_MIN_CONV=(\d+)", js)
        self.assertIsNotNone(m, "PW_PUBLIC_MIN_CONV nicht gefunden")
        self.assertEqual(P.MIN_CONV, int(m.group(1)),
                         "Push-Schwelle und Tor-Schwelle sind auseinandergelaufen")


class TestEineQuelleFuerAlleDrei(unittest.TestCase):
    def test_kachel_depot_und_push_meinen_dieselbe_menge(self):
        """Sonst heisst in drei Wochen wieder dasselbe Wort drei verschiedene Dinge — genau der
        Zustand, den Lucas am 07.09. aufgedeckt hat."""
        from pathlib import Path
        base = Path(__file__).resolve().parents[1]
        emit = (base / "scripts" / "emit_shortlist.mjs").read_text(encoding="utf-8")
        dash = (base / "main-dashboard.js").read_text(encoding="utf-8")
        self.assertIn("_pwPublicTopPlays()", emit, "der Emitter fuellt `public`")
        self.assertIn("_pwPublicTopPlays()", dash, "die Uebersichts-Kachel zieht aus derselben Quelle")


if __name__ == "__main__":
    unittest.main()
