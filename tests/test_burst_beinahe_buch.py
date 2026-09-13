"""🔴 13.09.2026 (Lucas: „wir müssen wirklich aufpassen, es muss auch solche Bursts auf
generelle Ligen geben — ich seh da immer Screens aus dieser einen Gruppe, irgendwelche
Panama-Ligen … und da gibt's genauso vier, fünf, sechs, sieben schnelle Geldeinsätze").

## Warum es das Beinahe-Buch gibt

Die Frage war nicht zu beantworten. Der Kanal wusste nur, was er GESENDET hat — was er verworfen
hat und warum, stand nirgends. Ich habe es an diesem Tag von Hand aus dem Ledger rekonstruiert;
das Ergebnis war, dass es NICHT an unseren Schwellen liegt (mit Betragsgrenze 0 $ und
Quotengrenze 1,01 findet die Erkennung 43 statt 39 Bursts, und keinen einzigen zusätzlichen in
einer kleinen Liga), sondern daran, dass Stakes Highroller-Feed erst ab ~1.000 $ je Wette
überhaupt etwas zeigt. Eine Stunde Handarbeit für eine Frage, die ein Zähler beantwortet.

Dieselbe Regel wie überall hier: **was wir wegfiltern, muss messbar bleiben.** Ein Filter, dessen
Preis niemand kennt, lässt sich weder rechtfertigen noch widerlegen — er hat Bestandsschutz aus
Unwissenheit.

## Die zwei Stellen, an denen so ein Buch still falsch wird

1. **Nur der erste Grund.** Wer beim ersten fehlgeschlagenen Kriterium aussteigt, kann später
   nicht mehr sagen, welche Regel man lockern müsste — „scheitert an GENAU EINER Regel" ist die
   Frage, und die braucht alle Gründe.
2. **Mehrfachzählung.** Ein Cluster bleibt mehrere Läufe lang im Fenster. Ohne Dedup steht nach
   einer Stunde „sechsmal an der Quote gescheitert", wo es einmal war — eine Statistik, die
   kaputt ist, ohne kaputt auszusehen.
"""
import unittest
from datetime import datetime, timedelta, timezone

import stake_burst_push as B

JETZT = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _w(i, quote=1.8, usd=4000.0, minute=0, sekunde=0, kat="Fußball", liga="Liga Panameña",
       auswahl="ausw-1"):
    return {"id": f"sport:{i}", "auswahlId": auswahl, "eventId": "ev-1",
            "ts": (JETZT - timedelta(minutes=minute, seconds=-sekunde)).isoformat(),
            "einsatzUsd": usd, "quote": quote, "kat": kat, "liga": liga, "ligaSlug": "pan",
            "sport": "soccer", "event": "Tauro FC - CD Universitario", "markt": "1x2",
            "auswahl": "Tauro FC", "kombi": False}


def _cluster(n=4, **over):
    return [_w(i, sekunde=i * 10, **over) for i in range(n)]


class TestJederVerworfeneGrundWirdFestgehalten(unittest.TestCase):
    def _lauf(self, wetten):
        vw = []
        B.bursts(wetten, now=JETZT, verworfen=vw)
        return vw

    def test_zu_kleine_summe_landet_im_buch(self):
        vw = self._lauf(_cluster(usd=500.0))
        self.assertEqual(len(vw), 1)
        self.assertEqual(vw[0]["gruende"], ["summe_zu_klein"])
        self.assertEqual(vw[0]["liga"], "Liga Panameña")

    def test_zu_tiefe_quote_landet_im_buch(self):
        vw = self._lauf(_cluster(quote=1.20, usd=4000.0))
        self.assertEqual(vw[0]["gruende"], ["quote_zu_tief"])

    def test_gesperrte_sportart_landet_im_buch(self):
        """Eine Sperre, deren Preis niemand kennt, ist eine Vermutung mit Bestandsschutz."""
        vw = self._lauf(_cluster(kat="Cricket", usd=4000.0))
        self.assertEqual(len(vw), 1)
        self.assertEqual(vw[0]["gruende"], ["sportart_gesperrt"])

    def test_ALLE_gruende_stehen_da_nicht_nur_der_erste(self):
        """Der Kern: mit nur einem Grund je Zeile ist „welche Regel kostet uns was" nicht
        beantwortbar."""
        w = _cluster(quote=1.10, usd=500.0)
        w[0]["quote"] = 1.12                      # zusätzlich uneinheitlich
        vw = self._lauf(w)
        self.assertEqual(vw[0]["gruende"],
                         ["quote_zu_tief", "quoten_uneinheitlich", "summe_zu_klein"])

    def test_ein_echter_burst_landet_NICHT_im_buch(self):
        vw = []
        b = B.bursts(_cluster(usd=4000.0), now=JETZT, verworfen=vw)
        self.assertEqual(len(b), 1)
        self.assertEqual(vw, [])

    def test_zu_wenige_wetten_sind_kein_beinahe_treffer(self):
        """Zwei Wetten sind kein Burst — gemessen (n=339) liegt min_n=2 bei −4,7 % ROI. Das als
        „beinahe" zu führen würde das Buch mit Rauschen fluten."""
        self.assertEqual(self._lauf(_cluster(n=2, usd=9000.0)), [])

    def test_zu_alt_ist_kein_grund_fuers_buch(self):
        """Das Cluster war fachlich in Ordnung, wir haben es nur zu spät gesehen. Im Buch wäre
        es Laufzeit-Rauschen in einer Statistik über Regeln."""
        alt = [_w(i, sekunde=i * 10, minute=600, usd=500.0) for i in range(4)]
        self.assertEqual(self._lauf(alt), [])

    def test_ohne_liste_bleibt_alles_wie_vorher(self):
        """Der Aufrufer muss nichts wissen: `verworfen` ist optional."""
        self.assertEqual(B.bursts(_cluster(usd=500.0), now=JETZT), [])


class TestDasBuchZaehltJedesClusterEinmal(unittest.TestCase):
    def _zeile(self, a="ausw-1", grund="quote_zu_tief", liga="Liga Panameña", tag="2026-09-13"):
        return {"auswahlId": a, "gruende": [grund], "liga": liga,
                "gesehenAm": tag + "T10:00:00+00:00"}

    def test_dasselbe_cluster_zaehlt_nur_einmal(self):
        """Ein Cluster bleibt mehrere Läufe im Fenster. Ohne Dedup stünde nach einer Stunde
        „sechsmal gescheitert", wo es einmal war."""
        buch = {}
        for _ in range(6):
            buch = B.verworfen_mischen(buch, [self._zeile()], JETZT)
        self.assertEqual(buch["n"], 1)
        self.assertEqual(buch["zaehler"]["quote_zu_tief"], 1)

    def test_verschiedene_cluster_zaehlen_getrennt(self):
        buch = B.verworfen_mischen({}, [self._zeile("a"), self._zeile("b")], JETZT)
        self.assertEqual(buch["n"], 2)

    def test_nur_dieser_grund_zaehlt_eindeutige_faelle(self):
        """Die eigentliche Auswertung: an welcher EINEN Regel scheitert ein sonst gültiges
        Cluster? Eine Zeile mit drei Gründen darf da nicht mitzählen."""
        mehrfach = {"auswahlId": "c", "gruende": ["quote_zu_tief", "summe_zu_klein"],
                    "liga": "X", "gesehenAm": "2026-09-13T10:00:00+00:00"}
        buch = B.verworfen_mischen({}, [self._zeile("a"), mehrfach], JETZT)
        self.assertEqual(buch["nurDieserGrund"], {"quote_zu_tief": 1})
        self.assertEqual(buch["zaehler"], {"quote_zu_tief": 2, "summe_zu_klein": 1})

    def test_das_buch_waechst_nicht_unbegrenzt(self):
        viele = [self._zeile(f"a{i}") for i in range(B.VERWORFEN_KEEP + 300)]
        buch = B.verworfen_mischen({}, viele, JETZT)
        self.assertEqual(buch["n"], B.VERWORFEN_KEEP)

    def test_die_ligen_stehen_daneben(self):
        """Ohne die Liga beantwortet das Buch Lucas' Frage nicht — die lautete ja gerade,
        ob uns KLEINE Ligen durchrutschen."""
        buch = B.verworfen_mischen({}, [self._zeile("a", liga="Liga Panameña"),
                                        self._zeile("b", liga="Liga Panameña"),
                                        self._zeile("c", liga="Premier League")], JETZT)
        self.assertEqual(buch["jeLiga"]["Liga Panameña"], 2)

    def test_main_schreibt_das_buch(self):
        quelle = __import__("pathlib").Path("stake_burst_push.py").read_text(encoding="utf-8")
        ohne = "\n".join(z for z in quelle.splitlines() if not z.lstrip().startswith("#"))
        self.assertIn("_verworfen_buchen(beinahe, now)", ohne)
        self.assertIn("verworfen=beinahe", ohne)


class TestLueckenBilanz(unittest.TestCase):
    """Die Antwort auf „hat ein schnellerer Takt negative Auswirkungen?" — erst messen.

    Die repo-weite Schedule-Last liegt bei 534/Tag, der Deckel bei 540 (test_cron_schedule_hygiene),
    und GitHub verzögert ab ~585. `betfair.yml` von 10 auf 5 Minuten wären +144/Tag. Der Takt ist
    also teuer; ob er sich lohnt, sagt nur diese Bilanz.
    """

    import stake_highroller_fetch as F

    def test_zaehlt_laeufe_und_luecken(self):
        a = {}
        for l in ({"luecke": False, "abdeckungMin": 12.0},
                  {"luecke": True, "lueckeMin": 3.0, "abdeckungMin": 12.0},
                  {"luecke": True, "lueckeMin": 5.0, "abdeckungMin": 10.0}):
            a = self.F.luecken_bilanz(a, l, "2026-09-13T09:00:00Z")
        self.assertEqual(a["laeufe"], 3)
        self.assertEqual(a["mitLuecke"], 2)
        self.assertEqual(a["minutenBlind"], 8.0)
        self.assertEqual(a["laengsteMin"], 5.0)
        self.assertAlmostEqual(a["anteilMitLueckePct"], 66.7, places=1)

    def test_erster_lauf_ohne_vergleich_zaehlt_keine_luecke(self):
        a = self.F.luecken_bilanz({}, {"luecke": None, "grund": "erster Lauf"}, "t")
        self.assertEqual(a["laeufe"], 1)
        self.assertNotIn("mitLuecke", a)

    def test_die_bilanz_ueberlebt_den_lauf(self):
        """Der ganze Punkt: `luecke_messen` rechnete das seit dem 03.09. je Lauf aus und warf
        es weg. Ein Wert, der nur den letzten Lauf kennt, beantwortet „wie oft" nie."""
        a = self.F.luecken_bilanz({"laeufe": 400, "mitLuecke": 7, "minutenBlind": 22.0,
                                   "seit": "2026-09-03T00:00:00Z"},
                                  {"luecke": True, "lueckeMin": 2.0}, "jetzt")
        self.assertEqual(a["laeufe"], 401)
        self.assertEqual(a["mitLuecke"], 8)
        self.assertEqual(a["minutenBlind"], 24.0)
        self.assertEqual(a["seit"], "2026-09-03T00:00:00Z")

    def test_der_fetcher_schreibt_die_bilanz_wirklich(self):
        quelle = __import__("pathlib").Path("stake_highroller_fetch.py").read_text(encoding="utf-8")
        ohne = "\n".join(z for z in quelle.splitlines() if not z.lstrip().startswith("#"))
        self.assertIn('ledger["luecken"] = luecken_bilanz(', ohne)


if __name__ == "__main__":
    unittest.main()
