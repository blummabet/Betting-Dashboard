"""13.09.2026 (Lucas: „ich brauch es zumindest in den Stats, weil ich will im Public ja
Auswertungen schicken … und die Stake-Bursts hätte ich auch gerne als extra Block").

Zwei Blöcke, zwei sehr verschiedene Fallen.

## 1. Der Gegensignal-Filter

Der Filter entstand am 30.08. aus einer Messung, die IN-SAMPLE war und den Signalstand bei
ABRECHNUNG las. Out-of-sample, am Stand vor Anpfiff gemessen, sieht er deutlich schwächer aus.
Die Falle beim Bauen eines Stats-Blocks ist deshalb nicht Rechnen, sondern AUSWAHL: zeigt man
nur den gesendeten Arm, steht dort eine schöne Zahl, und die Gegenprobe — sind die
Aussortierten in Wahrheit gut? — ist unsichtbar. Genau dagegen wurde das Schattenbuch gebaut.

Also: beide Arme, und das Urteil über die DIFFERENZ mit ihrem Band.

## 2. Die Stake-Bursts

Beim Bauen stellte sich heraus, dass der Kanal seit dem 11.09. pusht und **nie etwas
abgerechnet** hat — alle 15 Buchzeilen standen auf `pending`, obwohl der Kopf von `buch_zeile`
die Abrechnung ankündigte. „Wer pusht, misst den Push", in der stillsten Form: nichts ist
falsch, es steht nur nichts da.

Dazu eine Frist, die man nicht sieht: `stake_bet_ledger.json` ist ein rollierendes Fenster von
20.000 Wetten — am 13.09. sind das 5,3 Tage. Was darin nicht abgerechnet wird, ist danach nicht
mehr abrechenbar.
"""
import json
import unittest
from pathlib import Path

import stake_burst_push as B
import stats_perioden as S

WURZEL = Path(__file__).resolve().parent.parent


def _zeile(k, ids, sent="2026-09-12T10:00:00+00:00", status="pending", **rest):
    d = {"k": k, "betIds": ids, "sentAt": sent, "status": status, "phase": "vor",
         "quote": 1.8, "summeUsd": 12000.0, "nWetten": len(ids)}
    d.update(rest)
    return d


def _wette(i, endstand=True, pnl=100.0, einsatz=1000.0, ts="2026-09-12T09:00:00Z"):
    return {"id": i, "ts": ts,
            "abrechnung": {"endstand": endstand, "pnlUsd": pnl, "einsatzUsdGeprueft": einsatz}}


class TestBurstAbrechnung(unittest.TestCase):
    def test_ein_burst_mit_endstand_wird_abgerechnet(self):
        z, fertig, tot = B.abrechnen([_zeile("a", ["1", "2"])],
                                     [_wette("1"), _wette("2")])
        self.assertEqual((fertig, tot), (1, 0))
        self.assertEqual(z[0]["status"], "abgerechnet")
        self.assertTrue(z[0]["win"])
        self.assertAlmostEqual(z[0]["rendite"], 0.1, places=4)

    def test_geldgewichtet_nicht_je_ticket_gemittelt(self):
        """Ein Burst ist EINE Position auf mehreren Tickets — genau das macht ihn zum Burst.
        Je Ticket zu mitteln gäbe dem 200-$-Ticket dasselbe Gewicht wie dem 20.000-$-Ticket."""
        z, _f, _t = B.abrechnen(
            [_zeile("a", ["1", "2"])],
            [_wette("1", pnl=-200.0, einsatz=200.0),        # Ticket klein, total verloren
             _wette("2", pnl=2000.0, einsatz=20000.0)])     # Ticket gross, +10 %
        # geldgewichtet: (2000-200)/20200 = +8,9 %  ·  je Ticket gemittelt waere es -45 %
        self.assertAlmostEqual(z[0]["rendite"], 1800 / 20200, places=4)

    def test_teilweise_fertig_wird_NICHT_abgerechnet(self):
        """Sonst zeigt die Zeile beim nächsten Lauf eine andere Zahl als beim letzten — die
        früh fertigen Beine sind nicht dieselbe Menge wie der ganze Burst."""
        z, fertig, _t = B.abrechnen([_zeile("a", ["1", "2"])],
                                    [_wette("1"), _wette("2", endstand=False)])
        self.assertEqual(fertig, 0)
        self.assertEqual(z[0]["status"], "pending")

    def test_verlorene_wetten_werden_aufgegeben_statt_ewig_pending(self):
        """Das rollierende Fenster ist ~5 Tage breit. Eine Zeile, deren Wetten herausgefallen
        sind, ist keine offene Frage mehr — als `pending` stehenzubleiben behauptet, da käme
        noch was."""
        z, fertig, tot = B.abrechnen(
            [_zeile("alt", ["weg1", "weg2"], sent="2026-09-01T10:00:00+00:00")],
            [_wette("andere", ts="2026-09-08T00:00:00Z")])
        self.assertEqual((fertig, tot), (0, 1))
        self.assertEqual(z[0]["status"], "nicht_abrechenbar")
        self.assertIn("gefallen", z[0]["grund"])

    def test_ein_leeres_stake_ledger_erklaert_nichts_fuer_tot(self):
        """Die Gegenprobe zur Regel darüber: ein Lauf, in dem die Quelle fehlt oder halb
        geladen ist, darf nicht reihenweise Zeilen abschreiben."""
        z, fertig, tot = B.abrechnen([_zeile("a", ["1"], sent="2026-09-01T10:00:00+00:00")], [])
        self.assertEqual((fertig, tot), (0, 0))
        self.assertEqual(z[0]["status"], "pending")

    def test_abgerechnete_zeilen_werden_nicht_nochmal_angefasst(self):
        fertig_zeile = _zeile("a", ["1"], status="abgerechnet", rendite=0.5, win=True)
        z, fertig, _t = B.abrechnen([fertig_zeile], [_wette("1", pnl=-1000.0)])
        self.assertEqual(fertig, 0)
        self.assertEqual(z[0]["rendite"], 0.5)

    def test_main_rechnet_bei_jedem_lauf_ab(self):
        """Ohne diesen Aufruf hätte der Kanal wieder ein Buch voller `pending` — und die Frist
        des rollierenden Fensters läuft trotzdem."""
        quelle = (WURZEL / "stake_burst_push.py").read_text(encoding="utf-8")
        ohne_kommentar = "\n".join(z for z in quelle.splitlines()
                                   if not z.lstrip().startswith("#"))
        self.assertIn("abrechnen(led,", ohne_kommentar)


class TestBurstBlock(unittest.TestCase):
    def test_nicht_abrechenbare_zeilen_zaehlen_nicht_mit(self):
        """Sie als „ohne Ergebnis" mitzuzählen macht die Zahl der Pushes richtig und die
        Trefferquote schleichend falsch."""
        rows = [{"sentAt": "2026-09-12T10:00:00Z", "status": "abgerechnet", "win": True,
                 "rendite": 0.5, "phase": "live"},
                {"sentAt": "2026-09-12T10:00:00Z", "status": "nicht_abrechenbar", "phase": "live"}]
        orig = S._load
        S._load = lambda name, default=None: rows if "burst" in name else orig(name, default)
        try:
            self.assertEqual(len(S.burst_plays()), 1)
            self.assertEqual(len(S.burst_plays("live")), 1)
            self.assertEqual(S.burst_plays("vor"), [])
        finally:
            S._load = orig

    def test_die_rendite_kommt_aus_der_abrechnung_nicht_aus_der_quote(self):
        rows = [{"sentAt": "2026-09-12T10:00:00Z", "status": "abgerechnet", "win": True,
                 "rendite": 0.31, "quote": 9.9, "phase": "vor"}]
        orig = S._load
        S._load = lambda name, default=None: rows if "burst" in name else orig(name, default)
        try:
            self.assertAlmostEqual(S.burst_plays()[0]["rendite"], 0.31)
        finally:
            S._load = orig


class TestFilterVergleich(unittest.TestCase):
    def _z(self, push, win, odds=2.0, n=1):
        return [{"status": "abgerechnet", "win": win, "odds": odds, "push": push,
                 "gesehenAm": "2026-09-05T10:00:00+00:00"} for _ in range(n)]

    def test_beide_arme_stehen_da(self):
        v = S.filter_vergleich(self._z(True, True, n=40) + self._z(False, False, n=40), boot=400)
        self.assertEqual(v["gesendet"]["n"], 40)
        self.assertEqual(v["aussortiert"]["n"], 40)

    def test_ein_klarer_unterschied_wird_belegt(self):
        v = S.filter_vergleich(self._z(True, True, n=60) + self._z(False, False, n=60), boot=800)
        self.assertEqual(v["urteil"], "der Filter trägt")
        self.assertGreater(v["roiDiff"]["lo"], 0)

    def test_kein_unterschied_wird_nicht_belegt(self):
        """Der wichtigste Fall: gleich gute Arme dürfen nicht als Erfolg durchgehen."""
        gleich = (self._z(True, True, n=30) + self._z(True, False, n=30)
                  + self._z(False, True, n=30) + self._z(False, False, n=30))
        v = S.filter_vergleich(gleich, boot=800)
        self.assertEqual(v["urteil"], "noch nicht belegt")
        self.assertLessEqual(v["roiDiff"]["lo"], 0)

    def test_unter_der_mindestzahl_gibt_es_kein_urteil(self):
        v = S.filter_vergleich(self._z(True, True, n=5) + self._z(False, False, n=80), boot=400)
        self.assertEqual(v["urteil"], "sammelt")

    def test_dieselbe_datenlage_ergibt_dieselbe_zahl(self):
        """Fester Seed: sonst wandert das Band bei jedem Lauf ein bisschen, und man sucht die
        Ursache in den Daten statt im Zufallsgenerator.

        ⚠️ Die Mischung ist hier der Test. Mit lauter gleichen Zeilen je Arm zieht der Bootstrap
        immer denselben Mittelwert — dann ist das Ergebnis auch ohne Seed stabil, und dieser
        Test wäre grün, während der Seed längst weg ist. (Genau so stand er zuerst da.)"""
        d = (self._z(True, True, odds=2.4, n=20) + self._z(True, False, n=12)
             + self._z(False, True, odds=1.7, n=18) + self._z(False, False, n=25))
        a, b = S.filter_vergleich(d, boot=600), S.filter_vergleich(d, boot=600)
        self.assertEqual(a["roiDiff"], b["roiDiff"])
        self.assertEqual(a["hitDiff"], b["hitDiff"])

    def test_das_artefakt_traegt_beide_arme_und_das_urteil(self):
        d = S.baue()
        ids = {b["id"] for b in d["bloecke"]}
        self.assertIn("filter-gesendet", ids)
        self.assertIn("filter-aussortiert", ids,
                      "nur den gesendeten Arm zu zeigen ist genau die Selbstbestätigung, "
                      "die das Schattenbuch verhindern soll")
        if d.get("filterVergleich"):
            self.assertIn(d["filterVergleich"]["urteil"],
                          ("der Filter trägt", "noch nicht belegt", "sammelt"))

    def test_das_frontend_zeigt_das_urteil_und_beide_arme(self):
        js = (WURZEL / "stats.js").read_text(encoding="utf-8")
        ohne_kommentar = "\n".join(z for z in js.splitlines() if not z.lstrip().startswith("*")
                                   and not z.lstrip().startswith("/*"))
        self.assertIn("_stFilterKarte", ohne_kommentar)
        self.assertIn("v.aussortiert", ohne_kommentar)
        self.assertIn("v.urteil", ohne_kommentar)


if __name__ == "__main__":
    unittest.main()


# ─────────────────────────────────────────────────────────────────────────────
# 🔴 13.09.2026 (Lucas: „ich will heute oder morgen die Stats für die letzte und vorletzte
# Kalenderwoche posten und hätte halt gern, dass das halbwegs passt")
#
# Der Abgleich Push-Buch → Stats-Block stimmte in jedem Kanal und in beiden Wochen; unabhängig
# aus den Büchern nachgerechnet kam überall dieselbe Zahl heraus. Zwei Dinge stimmten NICHT:
#
# 1. Die drei Kennzahlen einer Zeile haben drei verschiedene Nenner, genannt war nur der erste.
#    Poly-Whales: 69 Pushes · Trefferquote aus 42 · Rendite aus 31. Liga-Picks KW37: fünf
#    Pushes, davon zwei abgerechnet — angezeigt als „100 % Treffer, +55,5 % Rendite".
# 2. „Liga-Picks · Trades" und „MLS-Picks · Trades" gehen in den PUBLIC-Channel. Ein falsches
#    Etikett auf genau der Seite, von der Screenshots rausgehen.
# ─────────────────────────────────────────────────────────────────────────────
class TestJedeZahlNenntIhrenNenner(unittest.TestCase):
    def test_kennzahlen_traegt_die_zahl_der_abgerechneten(self):
        plays = [{"tag": "2026-09-10", "gewonnen": True, "rendite": 0.5},
                 {"tag": "2026-09-10", "gewonnen": False, "rendite": -1.0},
                 {"tag": "2026-09-10", "gewonnen": None, "rendite": None}]
        k = S.kennzahlen(plays)
        self.assertEqual(k["n"], 3)
        self.assertEqual(k["nAufgeloest"], 2, "die Trefferquote kommt aus zweien, nicht aus drei")
        self.assertEqual(k["mitQuote"], 2)
        self.assertEqual(k["hitPct"], 50.0)

    def test_ohne_ergebnis_ist_der_nenner_null_und_nicht_die_zeilenzahl(self):
        k = S.kennzahlen([{"tag": "2026-09-10", "gewonnen": None, "rendite": None}] * 5)
        self.assertEqual((k["n"], k["nAufgeloest"]), (5, 0))
        self.assertIsNone(k["hitPct"], "ohne ein einziges Ergebnis darf keine Quote dastehen")

    def test_jede_zeile_jedes_blocks_traegt_den_nenner(self):
        d = S.baue()
        fehlt = [f"{b['label']}/{r['periode']}" for b in d["bloecke"] for r in b["reihen"]
                 if "nAufgeloest" not in r]
        self.assertEqual(fehlt, [])


class TestJederPushBlockNenntSeinenKanal(unittest.TestCase):
    def test_die_pick_kanaele_sind_public_nicht_trades(self):
        """`notify_new_picks.py` und der Digest in `telegram_wm.py` senden an TELEGRAM_CHAT_ID."""
        self.assertEqual(S.KANAL.get("liga-picks"), "Public")
        self.assertEqual(S.KANAL.get("mls-picks"), "Public")

    def test_kein_block_heisst_noch_trades_obwohl_er_public_ist(self):
        d = S.baue()
        falsch = [b["label"] for b in d["bloecke"]
                  if b.get("kanal") == "Public" and "Trades" in b["label"]]
        self.assertEqual(falsch, [])

    def test_jeder_push_block_sagt_wohin_er_geht(self):
        d = S.baue()
        ohne = [b["id"] for b in d["bloecke"]
                if b["gruppe"] == "Push-Kanäle" and not b.get("kanal")]
        self.assertEqual(ohne, [], "ein Kanal-Block ohne Ziel ist im Telegram-Überblick blind")

    def test_der_kanal_stimmt_mit_dem_ziel_im_code_ueberein(self):
        """Gegenprobe am Quelltext statt an meiner Erinnerung: wer TELEGRAM_TRADES_CHAT_ID
        benutzt, ist Trades; wer TELEGRAM_CHAT_ID benutzt, ist Public."""
        from pathlib import Path
        wurzel = Path(__file__).resolve().parent.parent
        erwartet = {"stake_burst_push.py": "Trades", "push_shortlist_trades.py": "Trades",
                    "notify_new_picks.py": "Public"}
        for datei, ziel in erwartet.items():
            p = wurzel / datei
            if not p.exists():
                continue
            q = p.read_text(encoding="utf-8")
            trades = "TELEGRAM_TRADES_CHAT_ID" in q
            self.assertEqual("Trades" if trades else "Public", ziel, datei)
