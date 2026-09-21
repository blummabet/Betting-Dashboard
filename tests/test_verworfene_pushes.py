"""🔴 21.09.2026 (Lucas: „Zuerst checke wieso das Spiel schon wieder nicht gesetzt wurde").

Der Push zu Victor Ryden vs Christian Sigsgaard ging um 11:09:36 in den Kanal, mit dem Satz
„Diese Plays werden automatisch mit $5 nachgespielt — die Bestätigung kommt gleich als eigene
Meldung." Die Bestätigung kam nicht. Gesetzt wurde die Wette erst um 11:33:51, im NÄCHSTEN
Lauf, 24 Minuten später — dazwischen sagte nichts und niemand etwas.

Gemessen am ganzen Push-Buch (62 Pushes):
    Fußball   11 → 11 gesetzt (100 %)
    E-Sport   40 → 24 gesetzt ( 60 %)
    Tennis    11 →  4 gesetzt ( 36 %)
23 angekündigte Pushes wurden nie gesetzt, und für keinen einzigen stand irgendwo ein Grund.

Ablehnungen INNERHALB der Setz-Schleife melden sich seit jeher selbst (`_liegen` →
Liegengeblieben-Meldung). Was in `faellige_zeilen` DAVOR aussortiert wurde, meldete sich nie:
die Zeile fiel still heraus. Und weil ein Push, dessen 90-Minuten-Fenster zu ist, nie wieder
fällig wird, war das ein endgültiger Verlust ohne eine einzige Spur.

Fehlerklasse: wer ablehnt, schreibt nicht.

Das Repo kennt die Gegenregel längst — „wer handelt, schreibt sofort". Sie galt nur für die
Tat, nie für die Unterlassung.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import shortlist_auto_bet as S

JETZT = datetime(2026, 9, 21, 11, 40, tzinfo=timezone.utc)


def _push(minuten_her, key="itf-ryden1-sigsga1-2026-09-21", side="Christian Sigsgaard",
          preis=0.865, **kw):
    z = {"k": f"{key}|{side}", "key": key, "side": side, "side_": side,
         "match": "Victor Ryden vs Christian Sigsgaard", "cat": "Tennis", "conv": 6,
         "pushPreis": preis,
         "sentAt": (JETZT - timedelta(minutes=minuten_her)).isoformat()}
    z.update(kw)
    return z


class TestWasStillVerschwand(unittest.TestCase):
    def test_ein_frischer_push_ist_faellig_und_kein_befund(self):
        r = S.sichten([_push(1)], set(), jetzt=JETZT)
        self.assertEqual(len(r["faellig"]), 1)
        self.assertEqual(r["verworfen"], [])

    def test_ein_zu_alter_push_bekommt_einen_grund(self):
        r = S.sichten([_push(120)], set(), jetzt=JETZT)
        self.assertEqual(r["faellig"], [])
        self.assertEqual(len(r["verworfen"]), 1)
        self.assertIn("Fenster zu", r["verworfen"][0][1])
        self.assertIn("nie mehr gesetzt", r["verworfen"][0][1])

    def test_der_grund_nennt_die_gemessene_zahl(self):
        """„zu alt" ohne die Minuten ist keine Auskunft."""
        grund = S.sichten([_push(120)], set(), jetzt=JETZT)["verworfen"][0][1]
        self.assertIn("120", grund)
        self.assertIn("90", grund)

    def test_live_hat_sein_eigenes_engeres_fenster(self):
        r = S.sichten([_push(20)], set(), jetzt=JETZT, live_fn=lambda k: True)
        self.assertEqual(r["faellig"], [])
        self.assertIn("live", r["verworfen"][0][1])

    def test_ohne_push_preis_gibt_es_einen_grund(self):
        r = S.sichten([_push(1, pushPreis=None)], set(), jetzt=JETZT)
        self.assertIn("kein Push-Preis", r["verworfen"][0][1])

    def test_ohne_zeitstempel_ebenso(self):
        z = _push(1); z["sentAt"] = None
        self.assertIn("ohne Zeitstempel", S.sichten([z], set(), jetzt=JETZT)["verworfen"][0][1])

    def test_schon_gesetzt_ist_kein_verlust_und_kein_eintrag(self):
        """Sonst ertraenkt der Normalfall die Ausnahme."""
        z = _push(1)
        r = S.sichten([z], {S.bet_key(z)}, jetzt=JETZT)
        self.assertEqual(r["faellig"], [])
        self.assertEqual(r["verworfen"], [], "eine gesetzte Wette gehoert nicht ins Verworfen-Buch")

    def test_der_alte_umschlag_liefert_weiter_dasselbe(self):
        """`faellige_zeilen` ist jetzt ein Umschlag — die Entscheidung steht an einer Stelle."""
        ledger = [_push(1), _push(120, key="alt-1"), _push(2, key="neu-2")]
        self.assertEqual(S.faellige_zeilen(ledger, set(), jetzt=JETZT),
                         S.sichten(ledger, set(), jetzt=JETZT)["faellig"])


class TestDasBuchWiederholtSichNicht(unittest.TestCase):
    def test_der_erste_grund_bleibt_stehen(self):
        """Er ist der, der den Verlust erklaert."""
        z = _push(120)
        b, neu = S.verworfen_buchen({}, [(z, "Fenster zu: 120 Min")], "2026-09-21T11:40:00Z")
        b, neu2 = S.verworfen_buchen(b, [(z, "irgendein spaeterer Grund")], "2026-09-21T12:10:00Z")
        e = list(b.values())[0]
        self.assertIn("120 Min", e["grund"])
        self.assertEqual(e["gesehen"], 2)
        self.assertEqual(e["zuletzt"], "2026-09-21T12:10:00Z")

    def test_nur_beim_ersten_mal_ist_es_neu(self):
        """Ein zu alter Push wird bei JEDEM Lauf wieder aussortiert. Ohne das hier wiederholt
        sich die Meldung, bis niemand mehr hinsieht."""
        z = _push(120)
        b, neu = S.verworfen_buchen({}, [(z, "x")], "t1")
        self.assertEqual(len(neu), 1)
        b, neu = S.verworfen_buchen(b, [(z, "x")], "t2")
        self.assertEqual(neu, [], "beim zweiten Mal ist nichts neu")

    def test_das_buch_waechst_nicht_unbegrenzt(self):
        b = {}
        for i in range(S.VERWORFEN_KEEP + 25):
            b, _ = S.verworfen_buchen(b, [(_push(120, key=f"k-{i:04d}"), "x")],
                                      "2026-09-%02dT00:00:00Z" % (1 + i % 28))
        self.assertLessEqual(len(b), S.VERWORFEN_KEEP)

    def test_eine_zeile_ohne_key_landet_nicht_im_buch(self):
        b, neu = S.verworfen_buchen({}, [({}, "Zeile ohne key/side")], "t")
        self.assertEqual(b, {})
        self.assertEqual(neu, [])


class TestDerGrundUeberlebtDenChatverlauf(unittest.TestCase):
    """🔴 Die Liegengeblieben-Meldung gab es schon — aber nur als Telegram-Nachricht.

    Auf „wieso wurde das nicht gesetzt" liess sich damit nur antworten, solange man die
    Nachricht noch scrollen konnte. Beide Arten von Ablehnung — still aussortiert und in der
    Schleife abgelehnt — gehoeren in DASSELBE Buch: eine Frage, ein Ort.
    """

    def test_beide_arten_landen_im_selben_buch(self):
        still = (_push(120), "Fenster zu: 120 Min nach dem Push")
        schleife = (_push(2, key="atp-misolic-gima-2026-09-21", side="Filip Misolic"),
                    "Ask 74¢, das sind +4.5pp ueber dem Push-Preis von 69¢ (max 3.0pp)")
        b, _ = S.verworfen_buchen({}, [still], "t1")
        b, _ = S.verworfen_buchen(b, [schleife], "t1")
        self.assertEqual(len(b), 2)
        gruende = " ".join(e["grund"] for e in b.values())
        self.assertIn("Fenster zu", gruende)
        self.assertIn("ueber dem Push-Preis", gruende)

    def test_ein_spaeter_gesetzter_push_bleibt_mit_seinem_grund_stehen(self):
        """Der Sigsgaard-Fall: um 11:09 abgelehnt, um 11:33 gesetzt. Beides ist wahr, und
        die Ablehnung erklaert die 24 Minuten dazwischen."""
        z = _push(2)
        b, _ = S.verworfen_buchen({}, [(z, "zu wenig Ask-Volumen fuer $5.00")], "2026-09-21T11:09:59Z")
        # Ein spaeterer Lauf setzt sie: `sichten` liefert sie dann gar nicht mehr als verworfen.
        r = S.sichten([z], {S.bet_key(z)}, jetzt=JETZT)
        self.assertEqual(r["verworfen"], [])
        # Der alte Eintrag bleibt aber lesbar — sonst waere die Frage wieder unbeantwortbar.
        self.assertIn("Ask-Volumen", list(b.values())[0]["grund"])


class TestDasBuchLiegtNebenSeinemWettbuch(unittest.TestCase):
    """🔴 21.09.2026, zum ZWEITEN Mal an einem Tag: mein zweiter Schreibvorgang lief an der
    Umleitung des ersten vorbei und legte `shortlist_auto_verworfen.json` im echten Baum an —
    ein Pipeline-Artefakt aus einem Testlauf. Vormittags war es `wm_poly_verlauf.json`.
    Fehlerklasse: ein zweiter Schreibvorgang, den die Umleitung des ersten nicht mit erfasst.
    """

    def test_es_folgt_dem_wettbuch_wohin_man_es_auch_legt(self):
        from unittest import mock
        with mock.patch.object(S, "PLACED_FILE", Path("/tmp/x/shortlist_auto_bets_placed.json")):
            self.assertEqual(S.verworfen_datei(),
                             Path("/tmp/x/shortlist_auto_verworfen.json"))

    def test_ohne_das_muster_im_namen_wird_das_wettbuch_nicht_ueberschrieben(self):
        from unittest import mock
        with mock.patch.object(S, "PLACED_FILE", Path("/tmp/x/irgendwas.json")):
            self.assertNotEqual(S.verworfen_datei(), Path("/tmp/x/irgendwas.json"))


class TestDieMeldung(unittest.TestCase):
    def test_ohne_neue_faelle_wird_nichts_gesendet(self):
        self.assertEqual(S.verworfen_text([]), "")

    def test_sie_nennt_das_spiel_die_seite_und_den_grund(self):
        _, neu = S.verworfen_buchen({}, [(_push(120), "Fenster zu: 120 Min nach dem Push")], "t")
        t = S.verworfen_text(neu)
        self.assertIn("Victor Ryden vs Christian Sigsgaard", t)
        self.assertIn("Christian Sigsgaard", t)
        # Genau so, wie der Push ihn in den Kanal geschrieben hat („@86¢") — dieselbe
        # Rundung wie push_shortlist_trades.py:80. Zwei Meldungen ueber denselben Push
        # duerfen sich nicht um einen Cent widersprechen.
        self.assertIn("86¢", t)
        self.assertIn("Fenster zu", t)

    def test_viele_faelle_werden_gedeckelt(self):
        b, neu = {}, []
        for i in range(12):
            b, n = S.verworfen_buchen(b, [(_push(120, key=f"k{i}"), "x")], "t")
            neu += n
        t = S.verworfen_text(neu)
        self.assertIn("und 6 weitere", t)


if __name__ == "__main__":
    unittest.main()
