#!/usr/bin/env python3
"""test_whale_trades_buch.py — der Trades-Kanal bekommt sein Buch (20.09.2026).

Lucas: „tracken wir eigentlich die trades Channel pushes … echt mühsam dass wir irgendwie nie
stringent das durchgezogen haben mit dem tracken."

Gemessen: 1705 Trades-Karten seit dem 27.07. gegen 77 Public-Pushs. Der Public-Kanal ist seit
dem 02.09. vollständig verbucht — und `check_public_push_buch` beschreibt dort wortgleich
denselben Mangel, den die Trades-Karte bis heute hatte. Derselbe Mangel, dieselbe Datei, zwei
Sender, einer repariert: eine Reparatur an der Instanz statt an der Klasse.
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


class TestSchreibpfad(unittest.TestCase):
    def test_die_trades_schleife_schreibt_ins_buch(self):
        q = (REPO / "poly_whale_watch.py").read_text(encoding="utf-8")
        # zwischen dem Trades-Send und dem Public-Block muss der Ledger-Aufruf stehen
        i = q.index('print(f"  ✅  {sent} Whale-Alert(s) (Trades) gesendet.")')
        j = q.rindex("_log_trades_push(", 0, i)
        self.assertGreater(j, q.index("for pkey, pos, restock in cand[:MAX_ALERTS]:"),
                           "der Ledger-Aufruf steht nicht in der Trades-Schleife")

    def test_nur_bei_tatsaechlich_gesendeter_karte(self):
        """Ein Buch, das auch die nicht gesendeten Karten enthaelt, ist kein Push-Buch."""
        q = (REPO / "poly_whale_watch.py").read_text(encoding="utf-8")
        block = q[q.index("for pkey, pos, restock in cand[:MAX_ALERTS]:"):
                  q.index('print(f"  ✅  {sent} Whale-Alert(s) (Trades) gesendet.")')]
        self.assertIn("if tg_send(card):", block)
        self.assertLess(block.index("if tg_send(card):"), block.index("_log_trades_push("))

    def test_der_pushpreis_wird_beim_senden_geschrieben(self):
        """Nach dem Lauf ist er nicht mehr rekonstruierbar. Genau daran krankt das
        Public-Buch: in 11 von 23 frueheren Zeilen fehlt er, und die zaehlen nie in eine
        Rendite. Eine Trefferquote ohne die Preise ist keine Zahl."""
        q = (REPO / "poly_whale_watch.py").read_text(encoding="utf-8")
        block = q[q.index("def _log_trades_push("):q.index("def _markiere_public(")]
        self.assertIn('"pushPrice": _push_price(pos)', block)
        self.assertIn('"sentAt": ts', block)

    def test_public_startet_als_unbekannt_nicht_als_nein(self):
        """Die Public-Schleife laeuft spaeter im selben Lauf. Ein Default False waere eine
        Behauptung ueber etwas, das noch nicht feststeht."""
        q = (REPO / "poly_whale_watch.py").read_text(encoding="utf-8")
        block = q[q.index("def _log_trades_push("):q.index("def _markiere_public(")]
        self.assertIn('"public": None', block)
        self.assertNotIn('"public": False', block)

    def test_der_public_marker_wird_nachgetragen(self):
        q = (REPO / "poly_whale_watch.py").read_text(encoding="utf-8")
        self.assertIn("_markiere_public([pkey for pkey, _pos, _r in pub_cand[:MAX_ALERTS]])", q)

    def test_kein_doppeleintrag_je_position(self):
        """Derselbe Dedup-Schluessel wie poly_whale_seen.json — sonst zaehlt jede Aufstockung
        als neue Karte."""
        q = (REPO / "poly_whale_watch.py").read_text(encoding="utf-8")
        block = q[q.index("def _log_trades_push("):q.index("def _markiere_public(")]
        self.assertIn('if any(isinstance(e, dict) and e.get("k") == pkey for e in led):', block)
        self.assertIn("return", block)


class TestAbrechnung(unittest.TestCase):
    def test_dieselbe_abrechnungsregel_wie_der_public_kanal(self):
        """Eine zweite Kopie der Regel waere die Bauart, die zwei Bilanzen auseinanderlaufen
        laesst — `settle()` ist die eine Wahrheit darueber, was ein Treffer ist."""
        q = (REPO / "poly_public_eval.py").read_text(encoding="utf-8")
        block = q[q.index("_tr = _load(TRADES_LEDGER_FILE"):q.index("rep = report(led)")]
        self.assertIn("settle(_tr, _res, _close, korrekturen=_korr)", block)
        self.assertIn("report(_tr)", block)

    def test_die_public_teilmenge_wird_abgezogen(self):
        """Die Public-Pushs sind eine TEILMENGE der Trades-Karten. Wer sie mitrechnet,
        vergleicht eine Gruppe mit sich selbst."""
        q = (REPO / "poly_public_eval.py").read_text(encoding="utf-8")
        self.assertIn('r.get("public") is not True', q)
        self.assertIn('_trep["nurTrades"]', q)

    def test_die_stats_zaehlen_die_teilmenge_nicht_doppelt(self):
        q = (REPO / "stats_perioden.py").read_text(encoding="utf-8")
        block = q[q.index('poly_whale_trades_ledger.json'):q.index('("whale-trades"')]
        self.assertIn('if r.get("public") is True:', block)
        self.assertIn("continue", block)

    def test_die_flaeche_zeigt_es(self):
        js = (REPO / "poly-wallets.js").read_text(encoding="utf-8")
        self.assertIn("poly_whale_trades_record.json", js)
        self.assertIn("function _pwTradesPush(rec)", js)
        self.assertIn("_pwTradesPush(_pwCache && _pwCache.tradesRec)", js)
        # und die Fläche darf nicht die Gesamtzahl statt der bereinigten zeigen
        block = js[js.index("function _pwTradesPush(rec)"):js.index("function _pwPublicPush(rec)")]
        self.assertIn("rec.nurTrades||rec.agg", block)


class TestGuard(unittest.TestCase):
    def test_der_guard_haengt_in_der_batterie(self):
        import poly_data_integrity as P
        namen = [getattr(f, "__name__", "") for f in getattr(P, "POLY_CHECKS", [])]
        self.assertIn("check_trades_push_buch", namen,
                      "ein Guard, den die Batterie nie aufruft, ist Dekoration")

    def test_der_guard_meldet_das_fehlende_buch_bei_laufendem_dedup(self):
        """Genau der heutige Zustand: 1709 Karten im Dedup-Stempel, kein Buch."""
        import poly_data_integrity as P
        alt = P._load
        try:
            P._load = lambda f: ({} if f == P.TRADES_LEDGER_FILE
                                 else ({"a": 1, "b": 2} if f == P.TRADES_SEEN_FILE else alt(f)))
            r = P.check_trades_push_buch(None)
        finally:
            P._load = alt
        self.assertFalse(r["ok"])
        self.assertIn("Dedup-Stempel", r["fails"][0] if r.get("fails") else str(r))


if __name__ == "__main__":
    unittest.main()
