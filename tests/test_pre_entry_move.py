"""Bewegung VOR dem Einstieg — mitschreiben, damit es messbar wird. 06.09.2026.

Gemessen auf den 611 abgerechneten Poly-Plays sind die CLV-Terzile in JEDER Kategorie monoton:

    ALLE (n=611)   CLV niedrig -36,2 %   mittel -12,0 %   hoch +37,1 %
    Fußball        -43,9 %  ·  -21,4 %  ·  +54,2 %
    E-Sport        -17,3 %  ·  +15,2 %  ·  +25,5 %
    Tennis         -22,2 %  ·   +2,2 %  ·  +14,4 %

(Ich hatte das vorher mit einer Korrelation gemessen — r = -0,017 — und daraus geschlossen, CLV
sage auf Poly nichts. Das war das falsche Werkzeug: bei Renditen mit sd ≈ 1,0 zeigt sich der
Effekt nur in Gruppenmitteln.)

Nutzbar ist das nur, wenn man es VOR dem Einstieg erkennt. Auf den 69 Plays, für die der Pfad
damals zurückreichte, war der Zusammenhang monoton — Preis lief vorher weg / kaum / zu uns ergab
hinterher -45,6 % / -25,6 % / +3,7 %. Bei n=23 je Eimer ist das keine Aussage, sondern ein Grund,
es endlich mitzuschreiben. Abdeckung ab jetzt: 615 von 645 Pfaden liefern ein 6h-Fenster.

Diese Datei prüft nur eines: dass gemessen wird, was draufsteht — und dass „unbekannt" nicht als
„keine Bewegung" durchgeht.
"""
import datetime as dt
import unittest

import poly_shortlist_track as T


def _pfad(key, side, punkte):
    """punkte: [(stunden_vor_jetzt, preis)]"""
    now = dt.datetime(2026, 9, 7, 12, 0, tzinfo=dt.timezone.utc)
    return now, {key: {"points": [
        {"ts": (now - dt.timedelta(hours=h)).isoformat(), "p": {side: p}} for h, p in punkte]}}


class TestPreEntryMove(unittest.TestCase):
    def test_ein_lauf_zu_uns_ist_positiv(self):
        now, pf = _pfad("k", "A", [(5, 0.50), (3, 0.54), (1, 0.58)])
        self.assertAlmostEqual(T._pre_entry_move("k", "A", now, pf), 8.0, places=3)

    def test_ein_lauf_weg_von_uns_ist_negativ(self):
        now, pf = _pfad("k", "A", [(5, 0.60), (1, 0.52)])
        self.assertAlmostEqual(T._pre_entry_move("k", "A", now, pf), -8.0, places=3)

    def test_stillstand_ist_null_und_nicht_unbekannt(self):
        """0.0 ist eine Aussage: der Preis stand. Sie darf nicht mit None verwechselt werden."""
        now, pf = _pfad("k", "A", [(5, 0.55), (1, 0.55)])
        self.assertEqual(T._pre_entry_move("k", "A", now, pf), 0.0)

    def test_kein_pfad_ist_unbekannt_und_nicht_null(self):
        """Der Kern. Ein fehlender Pfad als 0.0 zu rendern waere dieselbe Klasse wie
        `sharePct or 0` im Konsens: fehlende Information wird zum harmlosen Default und
        rutscht an jeder Schwelle vorbei."""
        now, pf = _pfad("k", "A", [(5, 0.55), (1, 0.60)])
        self.assertIsNone(T._pre_entry_move("gibtsnicht", "A", now, pf))
        self.assertIsNone(T._pre_entry_move("k", "AndereSeite", now, pf))
        self.assertIsNone(T._pre_entry_move("k", "A", now, {}))

    def test_ein_zu_alter_pfad_behauptet_nichts(self):
        """Reicht der Pfad nicht ins Fenster, gibt es keine Bewegung zu melden — auch dann
        nicht, wenn ältere Punkte existieren."""
        now, pf = _pfad("k", "A", [(30, 0.40), (25, 0.70)])
        self.assertIsNone(T._pre_entry_move("k", "A", now, pf))

    def test_punkte_nach_dem_einstieg_zaehlen_nicht_mit(self):
        """Sonst misst der Wert die Zukunft — genau die Zahl, die er vorhersagen soll."""
        now, pf = _pfad("k", "A", [(4, 0.50), (2, 0.52), (-1, 0.99)])
        self.assertAlmostEqual(T._pre_entry_move("k", "A", now, pf), 2.0, places=3)

    def test_ein_einzelner_punkt_ergibt_keine_bewegung(self):
        now, pf = _pfad("k", "A", [(2, 0.55)])
        self.assertIsNone(T._pre_entry_move("k", "A", now, pf))

    def test_unlesbare_zeitstempel_kippen_nicht_durch(self):
        now, pf = _pfad("k", "A", [(3, 0.50), (1, 0.55)])
        pf["k"]["points"].append({"ts": "morgen frueh", "p": {"A": 0.99}})
        self.assertAlmostEqual(T._pre_entry_move("k", "A", now, pf), 5.0, places=3)

    def test_das_fenster_ist_einstellbar_und_wirkt(self):
        now, pf = _pfad("k", "A", [(10, 0.40), (5, 0.50), (1, 0.55)])
        self.assertAlmostEqual(T._pre_entry_move("k", "A", now, pf, stunden=6), 5.0, places=3)
        self.assertAlmostEqual(T._pre_entry_move("k", "A", now, pf, stunden=24), 15.0, places=3)


class TestGegenDenEchtenBestand(unittest.TestCase):
    def test_die_pfade_decken_das_fenster_wirklich_ab(self):
        """Der Grund, warum die Rueckrechnung nur 69 von 611 Plays hatte: der Pfad wurde erst
        spaet angelegt. Wenn die Abdeckung heute schlecht waere, waere das Mitschreiben
        wirkungslos — dann muesste man erst den Pfad reparieren."""
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "poly_price_path.json"
        if not p.exists():
            self.skipTest("kein Preispfad")
        pf = json.loads(p.read_text(encoding="utf-8"))
        if len(pf) < 50:
            self.skipTest("zu wenige Pfade")
        ok = 0
        for k, e in pf.items():
            pts = e.get("points") or []
            if len(pts) < 2:
                continue
            seite = next(iter((pts[0].get("p") or {})), None)
            if not seite:
                continue
            bezug = T._iso(pts[-1].get("ts"))
            if bezug and T._pre_entry_move(k, seite, bezug, pf) is not None:
                ok += 1
        self.assertGreater(ok / len(pf), 0.5,
                           f"nur {ok} von {len(pf)} Pfaden liefern ein Fenster — dann bringt "
                           "das Mitschreiben nichts")


if __name__ == "__main__":
    unittest.main()
