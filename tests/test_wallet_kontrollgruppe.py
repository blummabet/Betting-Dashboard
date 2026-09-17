"""Das Wallet-Tor braucht eine Kontrollgruppe, sonst ist es nicht messbar — 06.09.2026.

Lucas: „ich weiss nicht, ob wir da optimale Logik gebaut haben."

Gemessen: von 172 abgerechneten Public-Kandidaten sind **172 sharp**. Die Wallet-Prüfung ist
ein hartes Tor — also hat jeder Play sie bestanden, und es gibt keine Vergleichsgruppe. Wir
können nicht wissen, ob sie etwas beiträgt. Dieselbe Falle wie das abgeschaltete Signal
(polymarket_sharp) und das stumme streak_momentum: **was immer gilt, ist nicht messbar.**

Was dagegen spricht, dass sie viel trägt:
  · Wallet-Bilanz sagt nichts über die nächste Wette (r = −0,005 bei ≥8 Vorwetten, n=736 Wallets)
  · „scharfe Wallet" ist im Live-Tracker das schlechteste Kriterium (−2,6 pp Fwd-CLV)
  · Conviction 7 OHNE sharp: +17,9 % (n=21) — bester Punktschätzer der Tabelle

Was dafür spricht (Näherung aus dem Altbestand, moneyPct fehlt dort):
  · conv≥6 + money-Signal ohne sharp: n=122, ROI −10,7 %, UG −23,0 %

Beides ist zu dünn. Deshalb läuft die Kontrollgruppe ab jetzt mit — nicht gesendet, nur
mitgeschrieben.
"""
import unittest

import poly_shortlist_track as T


def _play(pnl, public=False, ohne=False, stake=10.0, clv=0.0):
    return {"pnl": pnl, "stake": stake, "clvPP": clv, "result": "win" if pnl > 0 else "loss",
            "public": public, "ohneWallet": ohne, "signals": [], "conv": 7, "cat": "Fussball"}


class TestKontrollgruppe(unittest.TestCase):
    def test_die_gruppe_existiert_im_aggregat(self):
        a = T.aggregate([_play(1.0, ohne=True) for _ in range(5)])
        self.assertIn("publicOhneWallet", a)
        self.assertEqual(a["publicOhneWallet"]["n"], 5)

    def test_public_und_kontrollgruppe_sind_disjunkt(self):
        """Ein Play kann nicht gleichzeitig durchs Wallet-Tor UND daran gescheitert sein."""
        rows = ([_play(1.0, public=True) for _ in range(10)]
                + [_play(-1.0, ohne=True) for _ in range(7)])
        a = T.aggregate(rows)
        self.assertEqual(a["public"]["n"], 10)
        self.assertEqual(a["publicOhneWallet"]["n"], 7)

    def test_die_kontrollgruppe_traegt_ihre_untergrenze(self):
        a = T.aggregate([_play(1.0 if i % 2 else -1.0, ohne=True) for i in range(60)])
        v = a["publicOhneWallet"]
        self.assertIn("roiUg", v)
        self.assertIn("belegt", v)

    def test_leere_kontrollgruppe_kippt_nichts(self):
        """Am Tag der Einführung ist sie leer — das darf keine Zahl erfinden."""
        a = T.aggregate([_play(1.0, public=True) for _ in range(20)])
        self.assertEqual(a["publicOhneWallet"]["n"], 0)
        self.assertIsNone(a["publicOhneWallet"]["roiUg"])
        self.assertFalse(a["publicOhneWallet"]["belegt"])

    def test_alte_zeilen_ohne_das_feld_zaehlen_nicht_mit(self):
        """Der Altbestand kennt `ohneWallet` nicht. Fehlt das Feld, ist der Play KEIN
        Kontrollgruppen-Mitglied — fehlende Information ist keine Zugehörigkeit."""
        alt = {"pnl": 5.0, "stake": 10.0, "result": "win", "public": False,
               "signals": [], "conv": 7, "cat": "Fussball"}
        a = T.aggregate([alt] * 30)
        self.assertEqual(a["publicOhneWallet"]["n"], 0)


class TestEmitterVertrag(unittest.TestCase):
    """Die Gruppe entsteht im Frontend-Gate und muss durch den Emitter kommen."""

    def _quelle(self, datei):
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / datei
        if not p.exists():
            self.skipTest(f"{datei} fehlt")
        return p.read_text(encoding="utf-8")

    def test_das_gate_ist_in_seine_teile_zerlegt(self):
        """Ohne die Trennung von Wallet-Bedingung und Rest lässt sich die eine nicht weglassen."""
        js = self._quelle("poly-wallets.js")
        for fn in ("_pwTermWalletOk", "_pwTermPublicRest", "_pwTermIsPublicOhneWallet"):
            self.assertIn(fn, js, f"{fn} fehlt — dann ist das Tor wieder ein Block")

    def test_public_bleibt_aus_seinen_benannten_teilen_gebaut(self):
        """Die Zerlegung selbst darf nicht verloren gehen — sonst ist das Tor wieder ein Block
        und die Kontrollgruppe misst nichts mehr.

        07.09.2026: hier stand die Konjunktion als WORTLAUT
        (`_pwTermPublicRest(r) && _pwTermWalletOk(r)`). Am 07.09. wurde die Wallet-Bedingung für
        E-Sport gelockert (gemessen: durchgelassenes E-Sport +5,1 pp gegen Break-even,
        ABGEWIESENES +5,0 pp — sie trennt dort nichts), und der Test schlug an, obwohl genau das
        beabsichtigt war. Wieder ein Test, der eine Formulierung festhielt statt einer Regel.

        Die Regel, die bleiben muss: `_pwTermPublicRest` ist Pflicht für JEDEN Play, die
        Wallet-Bedingung ist der Normalweg, und jede Ausnahme davon ist benannt und begrenzt."""
        js = self._quelle("poly-wallets.js")
        self.assertIn("if(!_pwTermPublicRest(r)) return false;", js,
                      "der Rest des Tors muss unbedingt gelten")
        self.assertIn("return _pwTermWalletOk(r) || _pwEsportOhneWalletOk(r);", js,
                      "die Wallet-Bedingung bleibt der Normalweg, die Ausnahme ist benannt")
        self.assertIn("PW_ESPORT_FREI_AB_PREIS", js,
                      "die Ausnahme braucht eine benannte Schwelle, keinen Zahlenliteral")

    def test_der_emitter_reicht_die_gruppe_durch(self):
        mjs = self._quelle("scripts/emit_shortlist.mjs")
        self.assertIn("_pwPublicOhneWalletPlays", mjs)
        self.assertIn("ohneWallet", mjs)
        self.assertIn("publicOhneWallet", mjs)


if __name__ == "__main__":
    unittest.main()


class TestDieKontrolleEnthaeltNichtDieBehandlung(unittest.TestCase):
    """🔴 17.09.2026 (Lucas: „schaut ok aus oder?", zur Kontrollgruppen-Kachel).

    Sah ok aus und war es nicht. Die Kachel sagt „laeuft nur mit, wird NIE gesendet" — von 124
    abgerechneten Kontroll-Plays waren 12 trotzdem gesendet. Die E-Sport-Ausnahme vom 07.09.
    laesst E-Sport ab einem Preis auch OHNE Wallet-Nachweis durchs Public-Tor; die
    Kontrollgruppe fragte aber nur nach der fehlenden Wallet. Derselbe Play erfuellte damit
    beide Definitionen.

    Die zwoelf waren nicht irgendwelche: 11 Gewinne, ROI +33,2 %. Sie hoben die Kontrolle von
    +4,5 % auf +7,3 % — und daraus las die Kachel „das Wallet-Tor traegt nicht: ohne Nachweis
    +1,5 pp hoeher". Bereinigt liegt die Kontrolle 1,2 pp DARUNTER. Entschieden ist beides
    nicht, aber das Vorzeichen kam aus der Verunreinigung.

    Der bestehende Test `test_public_und_kontrollgruppe_sind_disjunkt` hat das nicht gefangen:
    er fuetterte Plays, die je nur EINE Flagge tragen, und prueft damit die Fixture, nicht die
    Regel. Ein Guard, der seinen eigenen Fall nicht provoziert, ist Dekoration.
    """

    def test_ein_play_mit_beiden_flaggen_zaehlt_nur_als_behandlung(self):
        rows = ([_play(1.0, public=True) for _ in range(10)]
                + [_play(-1.0, ohne=True) for _ in range(7)]
                + [_play(9.0, public=True, ohne=True) for _ in range(3)])
        a = T.aggregate(rows)
        self.assertEqual(a["public"]["n"], 13, "gesendet ist gesendet")
        self.assertEqual(a["publicOhneWallet"]["n"], 7,
                         "die Kontrolle darf keinen gesendeten Play enthalten")

    def test_die_verunreinigung_wuerde_das_vorzeichen_drehen(self):
        """Der Vorfall in Zahlen: drei starke Gewinner in beiden Armen drehen den Vergleich."""
        rows = ([_play(0.5, public=True) for _ in range(20)]
                + [_play(-1.0, ohne=True) for _ in range(10)]
                + [_play(9.0, public=True, ohne=True) for _ in range(3)])
        a = T.aggregate(rows)
        self.assertLess(a["publicOhneWallet"]["roi"], a["public"]["roi"],
                        "mit der Verunreinigung saehe die Kontrolle besser aus als die Behandlung")

    def test_das_frontend_schliesst_die_gesendeten_aus(self):
        """Die Regel muss auch dort stehen, wo der Marker entsteht — sonst repariert die
        Python-Seite ewig nach, was das Gate falsch schreibt."""
        from pathlib import Path
        js = (Path(__file__).resolve().parents[1] / "poly-wallets.js").read_text(encoding="utf-8")
        self.assertIn("return _pwTermPublicRest(r) && !_pwTermWalletOk(r) && !_pwTermIsPublic(r);",
                      js, "die Kontrollgruppe muss die gesendeten ausschliessen")


class TestDerUnterschiedTraegtSeinBand(unittest.TestCase):
    """Die zweite Haelfte des Fundes vom 17.09.: die Kachel entschied am VORZEICHEN der Differenz
    zweier ROIs und schrieb im selben Absatz, dass ein Unterschied zwischen zwei Punktschaetzern
    selbst nur einer ist. Gemessen: bereinigt −1,2 pp mit einem Band von [−13,3, +16,2] — die
    Null steckt weit drin.
    """

    def test_ein_band_um_die_null_entscheidet_nichts(self):
        # Hohe Streuung, kleiner Unterschied — genau die Lage im echten Bestand: wenige grosse
        # Gewinner tragen den Schnitt, und zwei Treffer mehr im einen Arm sehen aus wie ein
        # Vorsprung.
        mit = [_play(9.0) for _ in range(20)] + [_play(-1.0) for _ in range(40)]
        ohne = [_play(9.0) for _ in range(19)] + [_play(-1.0) for _ in range(41)]
        v = T.wallet_tor_vergleich(mit, ohne)
        self.assertGreater(v["diffPP"], 0, "der Punktschaetzer zeigt nach oben …")
        self.assertLess(v["lo"], 0)
        self.assertGreater(v["hi"], 0)
        self.assertEqual(v["urteil"], "nicht entschieden", "… das Band tut es nicht")

    def test_ein_klarer_vorsprung_heisst_traegt(self):
        mit = [_play(3.0) for _ in range(60)]
        ohne = [_play(-3.0) for _ in range(60)]
        v = T.wallet_tor_vergleich(mit, ohne)
        self.assertEqual(v["urteil"], "traegt")
        self.assertGreater(v["lo"], 0)

    def test_ein_klarer_rueckstand_heisst_traegt_nicht(self):
        mit = [_play(-3.0) for _ in range(60)]
        ohne = [_play(3.0) for _ in range(60)]
        v = T.wallet_tor_vergleich(mit, ohne)
        self.assertEqual(v["urteil"], "traegt nicht")
        self.assertLess(v["hi"], 0)

    def test_unter_der_mindestzahl_gibt_es_kein_urteil(self):
        v = T.wallet_tor_vergleich([_play(1.0) for _ in range(5)], [_play(1.0) for _ in range(60)])
        self.assertEqual(v["urteil"], "zu duenn")
        self.assertIsNone(v["diffPP"])

    def test_das_ergebnis_haengt_im_aggregat(self):
        """Sonst rechnet es niemand und die Kachel faellt auf den Punktschaetzer zurueck."""
        a = T.aggregate([_play(1.0, public=True) for _ in range(40)]
                        + [_play(-1.0, ohne=True) for _ in range(40)])
        self.assertIn("walletTor", a)
        self.assertEqual(a["walletTor"]["nMit"], 40)
