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

    def test_public_bleibt_die_konjunktion_seiner_teile(self):
        """Das echte Public-Gate darf sich durch die Zerlegung NICHT geändert haben."""
        js = self._quelle("poly-wallets.js")
        self.assertIn("return _pwTermPublicRest(r) && _pwTermWalletOk(r);", js)

    def test_der_emitter_reicht_die_gruppe_durch(self):
        mjs = self._quelle("scripts/emit_shortlist.mjs")
        self.assertIn("_pwPublicOhneWalletPlays", mjs)
        self.assertIn("ohneWallet", mjs)
        self.assertIn("publicOhneWallet", mjs)


if __name__ == "__main__":
    unittest.main()
