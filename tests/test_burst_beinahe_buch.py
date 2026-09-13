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


# ─────────────────────────────────────────────────────────────────────────────
# 🔴 13.09.2026 (Lucas: „aber jetzt rennen die Bursts normal als Push weiter und ich krieg die
# weiter rein")
#
# Beim Nachsehen fiel auf, dass Messen und Senden DASSELBE waren: `led.append(buch_zeile(...))`
# stand INNERHALB der Sende-Schleife und lief nur nach einem erfolgreichen `tg_send`. Folgen:
#   · Jeder Burst ueber dem Deckel von 4 wurde gezaehlt, aber nie gemessen.
#   · Den Kanal stillzulegen haette auch die Messung stillgelegt — die zwei Wochen Beobachtung,
#     auf die wir uns gerade geeinigt hatten, waeren mit dem ersten stummen Lauf weg gewesen.
#
# Dieselbe Trennung wie im Pick-Schattenbuch. Das Buch schreibt jeden erkannten Burst mit, der
# Push ist eine unabhaengige Entscheidung — und die Kanal-Bilanz zaehlt weiterhin nur, was den
# Kanal verlassen hat (die Regel, an der am 10.09. die Liga-Picks-Kachel gescheitert ist).
# ─────────────────────────────────────────────────────────────────────────────
class TestMessenUndSendenSindGetrennt(unittest.TestCase):
    def test_der_schalter_existiert_und_schaltet(self):
        import importlib, os
        alt = os.environ.get("STAKE_BURST_PUSH")
        try:
            os.environ["STAKE_BURST_PUSH"] = "false"
            self.assertFalse(importlib.reload(B).PUSH_AN)
            os.environ["STAKE_BURST_PUSH"] = "true"
            self.assertTrue(importlib.reload(B).PUSH_AN)
        finally:
            if alt is None:
                os.environ.pop("STAKE_BURST_PUSH", None)
            else:
                os.environ["STAKE_BURST_PUSH"] = alt
            importlib.reload(B)

    def test_push_aus_heisst_wirklich_nichts_senden(self):
        """Nicht nur die Variable, die WIRKUNG. Eine Mutation, die `PUSH_AN` im Ausdruck
        weglaesst, ist sonst gruen — sie war es beim ersten Versuch."""
        drei = [{"auswahlId": f"a{i}"} for i in range(3)]
        self.assertEqual(B.zu_senden(drei, push_an=False, max_push=4), [])
        self.assertEqual(len(B.zu_senden(drei, push_an=True, max_push=4)), 3)

    def test_der_deckel_gilt_weiter(self):
        zehn = [{"auswahlId": f"a{i}"} for i in range(10)]
        self.assertEqual(len(B.zu_senden(zehn, push_an=True, max_push=4)), 4)

    def test_das_buch_haengt_nicht_mehr_am_send(self):
        """Der Kern: die Buchzeile darf nicht in der Sende-Schleife entstehen."""
        quelle = __import__("pathlib").Path("stake_burst_push.py").read_text(encoding="utf-8")
        ohne = "\n".join(z for z in quelle.splitlines() if not z.lstrip().startswith("#"))
        i_send = ohne.index("for i, b in enumerate(senden):")
        i_buch = ohne.index("for b in neu:")
        self.assertLess(i_send, i_buch, "das Buch wird vor der Sende-Schleife gefuellt?")
        block = ohne[i_send:i_buch]
        self.assertNotIn("led.append", block,
                         "die Buchzeile entsteht wieder nur bei erfolgreichem Send")

    def test_jede_zeile_sagt_ob_sie_rausging(self):
        quelle = __import__("pathlib").Path("stake_burst_push.py").read_text(encoding="utf-8")
        self.assertIn('z["push"] = k in seen', quelle)
        self.assertIn('z["pushGrund"]', quelle)


class TestDieKanalBilanzZaehltNurWasRausging(unittest.TestCase):
    import stats_perioden as S

    ROWS = [
        {"sentAt": "2026-09-12T10:00:00Z", "status": "abgerechnet", "win": True,
         "rendite": 0.5, "phase": "live", "push": True},
        {"sentAt": "2026-09-12T11:00:00Z", "status": "abgerechnet", "win": False,
         "rendite": -1.0, "phase": "live", "push": False},
        {"sentAt": "2026-09-12T11:00:00Z", "status": "abgerechnet", "win": False,
         "rendite": -1.0, "phase": "live", "push": False},     # absichtlich identisch
        {"sentAt": "2026-09-12T12:00:00Z", "status": "abgerechnet", "win": True,
         "rendite": 0.2, "phase": "vor"},                      # Altzeile ohne Feld
    ]

    def _mit_rows(self, fn):
        orig = self.S._load
        self.S._load = lambda n, d=None: self.ROWS if "burst_ledger" in n else orig(n, d)
        try:
            return fn()
        finally:
            self.S._load = orig

    def test_die_drei_mengen_sind_sauber_getrennt(self):
        g = self._mit_rows(lambda: len(self.S.burst_plays()))
        n = self._mit_rows(lambda: len(self.S.burst_plays(gesendet=False)))
        a = self._mit_rows(lambda: len(self.S.burst_plays(gesendet=None)))
        self.assertEqual((g, n, a), (2, 2, 4))

    def test_zwei_identische_zeilen_kuerzen_sich_nicht_weg(self):
        """Die erste Fassung hat die zurueckgehaltenen ueber eine Listen-Differenz gebildet.
        Plays sind Dicts ohne Identitaet — zwei gleiche Zeilen haetten sich gegenseitig
        aufgehoben, und die Menge waere still um eine zu klein gewesen."""
        self.assertEqual(self._mit_rows(lambda: len(self.S.burst_plays(gesendet=False))), 2)

    def test_alte_zeilen_ohne_feld_gelten_als_gesendet(self):
        plays = self._mit_rows(lambda: self.S.burst_plays(phase="vor"))
        self.assertEqual(len(plays), 1, "die Altzeile ohne `push` muss in der Kanal-Bilanz sein")


# ─────────────────────────────────────────────────────────────────────────────
# 🔴 13.09.2026 — der Groessen-Waechter des Pages-Deploys schlug an (141 von 140 MB), ausgeloest
# von den zwei schlanken Artefakten, die ich am selben Tag DAZU gelegt hatte. Beim Nachsehen,
# wo die Masse liegt, kam der eigentliche Fund: `byTeamMarket` im Betfair-Track-Record hat
# 21.015 Eintraege und 10,6 MB — und **kein einziger** traegt ein Urteil. Das groesste n der
# ganzen Tabelle ist 6, die Schwelle fuer eine Untergrenze steht bei 30.
# ─────────────────────────────────────────────────────────────────────────────
class TestTeamMarktTabelleTraegtNurWasZaehlenKann(unittest.TestCase):
    import betfair_track_record as BT

    def test_eine_handvoll_wetten_ist_keine_verlaesslichkeit(self):
        """Die Grenze steht bei 3 und nicht bei 1: in einer Tabelle, deren Urteilsschwelle bei
        30 liegt, ist der Unterschied zwischen n=1 und n=2 keiner."""
        roh = {"A|1X2": {"n": 1}, "B|1X2": {"n": 2}, "C|1X2": {"n": 3}, "D|1X2": {"n": 6}}
        keep = {k: v for k, v in roh.items() if v["n"] >= self.BT.TEAM_MIN_N}
        self.assertEqual(sorted(keep), ["C|1X2", "D|1X2"])
        self.assertGreaterEqual(self.BT.TEAM_MIN_N, 2)

    def test_der_producer_filtert_wirklich(self):
        quelle = __import__("pathlib").Path("betfair_track_record.py").read_text(encoding="utf-8")
        ohne = "\n".join(z for z in quelle.splitlines() if not z.lstrip().startswith("#"))
        self.assertIn(">= team_min_n", ohne)
        self.assertIn('"byTeamMarket"', ohne)
        # und der Default des Parameters ist die Konstante — sonst filtert der echte Lauf nicht
        self.assertIn("team_min_n = TEAM_MIN_N if team_min_n is None else team_min_n", ohne)

    def test_die_kompakte_fassung_traegt_die_tabelle_weiterhin_gar_nicht(self):
        """Die Uebersicht liest von hier nur `byLeagueMarket` — das bleibt so, unabhaengig
        davon, wie stark die Team-Tabelle gefiltert ist."""
        self.assertIn("byTeamMarket", self.BT.NUR_IM_VOLLEN)
        self.assertNotIn("byTeamMarket", self.BT.kompakt({"a": 1, "byTeamMarket": {"x": 1}}))

    def test_gegen_das_echte_artefakt(self):
        """Gegenprobe am Bestand: keine Zeile der Tabelle kann heute ein Urteil tragen."""
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "betfair_track_record.json"
        if not p.exists():
            self.skipTest("kein Track-Record")
        tm = (json.loads(p.read_text(encoding="utf-8")) or {}).get("byTeamMarket") or {}
        if not tm:
            self.skipTest("keine Team-Tabelle")
        mit_urteil = [k for k, v in tm.items() if (v or {}).get("urteil")]
        groesstes_n = max((v or {}).get("n", 0) for v in tm.values())
        schwelle = max((v or {}).get("ugAb", 0) for v in tm.values())
        if mit_urteil:
            return          # ab dann traegt die Tabelle etwas — dieser Test hat seinen Zweck erfuellt
        self.assertLess(groesstes_n, schwelle,
                        "kein Urteil, obwohl n die Schwelle erreicht — dann stimmt etwas anderes nicht")
