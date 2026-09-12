#!/usr/bin/env python3
"""test_streak_watch.py — Serien-Watch (pre-match) + Serie gehalten/gerissen (post-match)
(04.07.2026, Lucas). Reine Selektoren/Auflöser, kein Send.

02.08.2026 (Lucas: „Spiele waren heute Nacht"): der Watch gated jetzt auf den ECHTEN Anpfiff
(WATCH_LEAD_MIN..WATCH_HORIZON_H) statt auf `date == today`. Tests bekommen ein `kickoff` +
ein festes `now` gespritzt."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import telegram_streak_watch as W

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)   # fixer Prüfzeitpunkt


def _ko(hours):
    return (NOW + timedelta(hours=hours)).isoformat()


def _streak(team="Frankreich", tid="FRA", stype="over25", length=12, state="intakt",
            venue="all", date="2026-07-04", opp="Paraguay", pk="KO-R16-FRA-PRY", xg=None,
            ko_h=6):
    """ko_h = Stunden bis Anpfiff (relativ zu NOW); None → gar kein kickoff-Feld."""
    s = {"team": team, "teamId": tid, "type": stype, "market": f"{stype}", "length": length,
         "venue": venue, "continuation": {"state": state}, "flag": "🇫🇷", "xgBacked": xg}
    if date:
        nx = {"oppName": opp, "date": date, "pickKey": pk, "oppRatePct": 60}
        if ko_h is not None:
            nx["kickoff"] = _ko(ko_h)
        s["next"] = nx
    return s


class TestWatch(unittest.TestCase):
    def _watch(self, streaks, watched=None):
        return W.build_watch(streaks, {}, watched or {}, "2026-07-04", now=NOW)

    def test_anpfiff_bevorstehend_bewacht(self):
        out = self._watch([_streak(ko_h=6)])
        self.assertEqual(len(out), 1)
        key, entry, msg = out[0]
        self.assertIn("Serien-Watch", msg)
        self.assertIn("Frankreich", msg)
        self.assertEqual(entry["pickKey"], "KO-R16-FRA-PRY")
        self.assertIn("kickoff", entry)   # Anpfiff wird mitgeschrieben

    def test_anpfiff_vorbei_nicht_bewacht(self):
        # DER „heute Nacht"-Bug: Spiel lief schon (Anpfiff -3 h), Datum aber == heute → früher gefeuert.
        self.assertEqual(self._watch([_streak(ko_h=-3)]), [])

    def test_anpfiff_zu_knapp_nicht_bewacht(self):
        # < WATCH_LEAD_MIN (30 min) → nicht mehr spielbar
        self.assertEqual(self._watch([_streak(ko_h=0.25)]), [])   # +15 min

    def test_anpfiff_zu_weit_weg_nicht_bewacht(self):
        # > WATCH_HORIZON_H (18 h) → erst näher am Spiel
        self.assertEqual(self._watch([_streak(ko_h=30)]), [])

    def test_ohne_kickoff_nicht_bewacht(self):
        # kein Zeitstempel → lieber still als falsch
        self.assertEqual(self._watch([_streak(ko_h=None)]), [])

    def test_spaetes_us_spiel_naechster_utc_tag_trotzdem_bewacht(self):
        # Anpfiff in 8 h, aber UTC-Datum bereits MORGEN → der alte date==today-Filter hätte es
        # verschluckt; jetzt zählt der Zeitpunkt → wird bewacht.
        out = self._watch([_streak(date="2026-07-05", ko_h=8, pk="KO-R16-FRA-XXX")])
        self.assertEqual(len(out), 1)

    def test_zu_kurz_uebersprungen(self):
        self.assertEqual(self._watch([_streak(length=9)]), [])   # 9 < 10 → raus

    def test_nicht_intakt_uebersprungen(self):
        self.assertEqual(self._watch([_streak(state="wackelt")]), [])

    def test_venue_variante_uebersprungen(self):
        self.assertEqual(self._watch([_streak(venue="H")]), [])

    def test_bereits_bewacht_uebersprungen(self):
        watched = {"FRA:over25:2026-07-04": {}}
        self.assertEqual(self._watch([_streak()], watched), [])

    def test_ecken_typ_nicht_bewacht(self):
        self.assertEqual(self._watch([_streak(stype="cornersOver")]), [])

    def test_xg_siegel_in_nachricht(self):
        self.assertIn("xG gedeckt", self._watch([_streak(xg=True)])[0][2])
        self.assertIn("Glück", self._watch([_streak(xg=False)])[0][2])


class TestParseKo(unittest.TestCase):
    def test_iso_offset(self):
        self.assertEqual(W._parse_ko("2026-08-02T00:30:00+00:00").hour, 0)

    def test_zulu(self):
        self.assertEqual(W._parse_ko("2026-08-02T00:30:00Z").minute, 30)

    def test_naiv_als_utc(self):
        self.assertEqual(W._parse_ko("2026-08-02T00:30:00").tzinfo, timezone.utc)

    def test_leer_und_muell(self):
        self.assertIsNone(W._parse_ko(""))
        self.assertIsNone(W._parse_ko(None))
        self.assertIsNone(W._parse_ko("morgen"))


class TestStreakHeld(unittest.TestCase):
    def _fx(self, hs, as_, home="FRA", away="PRY"):
        return {"home": home, "away": away,
                "result": {"status": "FT", "home_score": hs, "away_score": as_}}

    def test_over25(self):
        self.assertTrue(W.streak_held("over25", "FRA", self._fx(3, 1)))
        self.assertFalse(W.streak_held("over25", "FRA", self._fx(1, 0)))

    def test_btts(self):
        self.assertTrue(W.streak_held("bttsYes", "FRA", self._fx(2, 1)))
        self.assertFalse(W.streak_held("bttsYes", "FRA", self._fx(2, 0)))

    def test_scored_cleansheet_seitenabhaengig(self):
        self.assertTrue(W.streak_held("scored", "FRA", self._fx(1, 0)))
        self.assertFalse(W.streak_held("scored", "PRY", self._fx(1, 0)))
        self.assertTrue(W.streak_held("cleanSheet", "FRA", self._fx(1, 0)))
        self.assertFalse(W.streak_held("cleanSheet", "PRY", self._fx(1, 0)))

    def test_unfertig_none(self):
        self.assertIsNone(W.streak_held("over25", "FRA", {"home": "FRA", "away": "PRY", "result": {}}))


class TestRecap(unittest.TestCase):
    def _wm(self, hs, as_):
        return {"groups": {}, "koFixtures": [
            {"home": "FRA", "away": "PRY", "round": "R16",
             "result": {"status": "FT", "home_score": hs, "away_score": as_}}]}

    def _watched(self):
        return {"FRA:over25:2026-07-04": {"teamId": "FRA", "team": "Frankreich", "type": "over25",
                "length": 15, "market": "over25", "pickKey": "KO-R16-FRA-PRY",
                "oppName": "Paraguay", "date": "2026-07-04"}}

    # Seit 12.09.2026 haengt der PUSH an der Frische der Abrechnung — diese Klasse prueft den
    # Text, also wird hier ein „gerade gelaufen"-Jetzt gesetzt. Die Frische selbst hat unten
    # ihre eigene Klasse.
    _JETZT = datetime(2026, 7, 5, 6, 0, tzinfo=timezone.utc)

    def test_haelt(self):
        msgs, done, _b = W.build_recap(self._wm(3, 1), self._watched(), "2026-07-05",
                                       now=self._JETZT)
        self.assertEqual(len(msgs), 1)
        self.assertIn("hält", msgs[0])
        self.assertIn("16×", msgs[0])
        self.assertEqual(len(done), 1)

    def test_gerissen(self):
        msgs, done, _b = W.build_recap(self._wm(1, 0), self._watched(), "2026-07-05",
                                       now=self._JETZT)
        self.assertIn("gerissen", msgs[0])
        self.assertIn("15 Spielen", msgs[0])

    def test_spiel_noch_nicht_vorbei(self):
        msgs, done, _b = W.build_recap(self._wm(3, 1), self._watched(), "2026-07-04",
                                       now=self._JETZT)
        self.assertEqual(msgs, [])
        self.assertEqual(done, [])

    def test_kein_endstand_wartet(self):
        wm = {"groups": {}, "koFixtures": [{"home": "FRA", "away": "PRY", "result": {}}]}
        msgs, done, _b = W.build_recap(wm, self._watched(), "2026-07-05", now=self._JETZT)
        self.assertEqual(msgs, [])


class TestSendGuard(unittest.TestCase):
    """06.07.2026 (Lucas): tg_send lieferte `not (TOKEN and CHAT_ID)` → True bei FEHLENDEM
    Token → main() setzte den Dedup-Marker ohne echten Send → Serie still verschluckt, nie
    nachgesendet. Fehlender Token in einem echten Lauf muss False sein; nur SKIP_TELEGRAM True."""

    def setUp(self):
        self._orig = (W.SKIP_TELEGRAM, W.TOKEN, W.CHAT_ID)

    def tearDown(self):
        W.SKIP_TELEGRAM, W.TOKEN, W.CHAT_ID = self._orig

    def test_fehlender_token_liefert_false(self):
        W.SKIP_TELEGRAM, W.TOKEN, W.CHAT_ID = False, "", "123"
        self.assertFalse(W.tg_send("x"))

    def test_fehlende_chat_id_liefert_false(self):
        W.SKIP_TELEGRAM, W.TOKEN, W.CHAT_ID = False, "tok", ""
        self.assertFalse(W.tg_send("x"))

    def test_skip_telegram_liefert_true(self):
        W.SKIP_TELEGRAM, W.TOKEN, W.CHAT_ID = True, "", ""
        self.assertTrue(W.tg_send("x"))


class TestWatchDigest(unittest.TestCase):
    """22.08.2026 (Lucas: „reicht 1 Nachricht am Tag"): der Watch-Zweig bündelt jetzt ALLE
    anstehenden Serien in EINEN Push. Hier: Aufbau/Format/Sortierung des Digests."""

    def _entries(self):
        return [
            {"team": "Tottenham", "type": "scored", "length": 12, "market": "Team trifft",
             "oppName": "Brentford", "flag": "🏴", "oppRatePct": 60, "xgBacked": None},
            {"team": "Inter", "type": "scored", "length": 15, "market": "Team trifft",
             "oppName": "Monza", "flag": "🇮🇹", "oppRatePct": 60, "xgBacked": True},
            {"team": "Celta Vigo", "type": "scored", "length": 11, "market": "Team trifft",
             "oppName": "Valencia", "flag": "🇪🇸", "oppRatePct": 87, "xgBacked": False},
        ]

    def test_ein_string_mit_allen_teams(self):
        msg = W.build_watch_digest(self._entries())
        self.assertIsInstance(msg, str)
        for t in ("Inter", "Tottenham", "Celta Vigo", "Monza", "Brentford", "Valencia"):
            self.assertIn(t, msg)
        self.assertIn("Serien-Watch", msg)
        self.assertIn("3 Teams", msg)               # Zähler im Header
        self.assertEqual(msg.count("Serien-Watch"), 1)   # nur EIN Header, keine Wiederholung

    def test_heisseste_zuerst(self):
        msg = W.build_watch_digest(self._entries())
        self.assertLess(msg.index("Inter"), msg.index("Tottenham"))   # 15× vor 12×
        self.assertLess(msg.index("Tottenham"), msg.index("Celta Vigo"))  # 12× vor 11×

    def test_xg_siegel_und_grundrate(self):
        msg = W.build_watch_digest(self._entries())
        self.assertIn("Grundrate 87%", msg)
        self.assertIn("✓ xG", msg)      # Inter (xgBacked True)
        self.assertIn("⚠️", msg)        # Celta (xgBacked False)

    def test_singular_ein_team(self):
        msg = W.build_watch_digest(self._entries()[:1])
        self.assertIn("1 Team ", msg)   # Singular, nicht „1 Teams"

    def test_leer_kein_crash(self):
        msg = W.build_watch_digest([])
        self.assertIn("0 Teams", msg)


if __name__ == "__main__":
    unittest.main()


# ── 09.09.2026: das Buch ────────────────────────────────────────────────────────────────
# Lucas: „der Preis ist da egal um ehrlich zu sein — die Frage ist einfach: wurde Serie erfuellt
# ja oder nein."
#
# 🔴 Der Fund davor: genau das rechnete `build_recap` seit August jeden Tag aus, postete es und
# WARF ES WEG. Am 08.09. standen 50 bewachte Serien und 0 Ergebnisse im Zustand.
class TestBuchung(unittest.TestCase):
    def _wm(self, hs, as_):
        return {"groups": {}, "koFixtures": [
            {"home": "FRA", "away": "PRY", "round": "R16",
             "result": {"status": "FT", "home_score": hs, "away_score": as_}}]}

    def _watched(self, **over):
        w = {"teamId": "FRA", "team": "Frankreich", "type": "over25", "length": 15,
             "market": "over25", "pickKey": "KO-R16-FRA-PRY", "oppName": "Paraguay",
             "date": "2026-07-04", "erwartetPct": 61, "erwartetBasis": "eigen",
             "erwartetPreN": 8}
        w.update(over)
        return {"FRA:over25:2026-07-04": w}

    def test_jede_aufgeloeste_serie_wird_gebucht(self):
        _m, _d, buch = W.build_recap(self._wm(3, 1), self._watched(), "2026-07-05")
        self.assertEqual(len(buch), 1)
        self.assertIs(buch[0]["erfuellt"], True)
        self.assertEqual(buch[0]["team"], "Frankreich")

    def test_die_erwartung_reist_mit_ins_buch(self):
        """Ohne sie ist die Trefferquote hinterher nur eine Zahl: „62 % erfuellt" heisst nichts,
        solange nicht danebensteht, was ohne jede Serie zu erwarten gewesen waere."""
        _m, _d, buch = W.build_recap(self._wm(3, 1), self._watched(), "2026-07-05")
        self.assertEqual(buch[0]["erwartetPct"], 61)
        self.assertEqual(buch[0]["erwartetBasis"], "eigen")

    def test_nicht_abrechenbares_wird_gebucht_statt_verschwiegen(self):
        """Ecken und Karten stehen nicht im Endstand. Sie fielen bisher still aus dem Watch —
        ein Markt, den wir nicht abrechnen koennen, muss im Nenner sichtbar bleiben."""
        _m, done, buch = W.build_recap(self._wm(3, 1), self._watched(type="cards"), "2026-07-05")
        self.assertEqual(len(buch), 1)
        self.assertIsNone(buch[0]["erfuellt"])
        self.assertEqual(len(done), 1, "aus dem Watch faellt sie trotzdem")

    def test_ein_unfertiges_spiel_wird_nicht_gebucht(self):
        wm = {"groups": {}, "koFixtures": [{"home": "FRA", "away": "PRY", "result": {}}]}
        _m, _d, buch = W.build_recap(wm, self._watched(), "2026-07-05")
        self.assertEqual(buch, [])

    def test_sieg_und_ungeschlagen_sind_abrechenbar(self):
        """Sie stehen im Endstand genauso drin wie die Tor-Maerkte und fehlten hier nur."""
        self.assertIs(W.streak_held("win", "FRA", self._wm(2, 1)["koFixtures"][0]), True)
        self.assertIs(W.streak_held("win", "PRY", self._wm(2, 1)["koFixtures"][0]), False)
        self.assertIs(W.streak_held("unbeaten", "PRY", self._wm(1, 1)["koFixtures"][0]), True)


class TestBilanz(unittest.TestCase):
    def _z(self, n, treffer, erwartet=60):
        return ([{"erfuellt": True, "erwartetPct": erwartet} for _ in range(treffer)]
                + [{"erfuellt": False, "erwartetPct": erwartet} for _ in range(n - treffer)])

    def test_unter_der_mindestzahl_wird_nicht_geurteilt(self):
        b = W.bilanz(self._z(10, 8))
        self.assertEqual(b["urteil"], "sammelt")
        self.assertNotIn("ugPct", b)

    def test_ein_punktschaetzer_entscheidet_nichts(self):
        """⭐ 25 von 35 sind 71 % gegen 60 % Erwartung — nach dem Punkt „traegt sich selbst".
        Die Untergrenze liegt bei 58 % und damit UNTER der Erwartung: mit „die Serie sagt gar
        nichts" ist das voll vereinbar."""
        b = W.bilanz(self._z(35, 25, erwartet=60))
        self.assertGreater(b["quotePct"], 60)
        self.assertLess(b["ugPct"], 60)
        self.assertEqual(b["urteil"], "kein Unterschied")

    def test_traegt_sich_selbst_verlangt_die_untergrenze_ueber_der_erwartung(self):
        b = W.bilanz(self._z(200, 160, erwartet=60))
        self.assertGreater(b["ugPct"], 60)
        self.assertEqual(b["urteil"], "traegt sich selbst")

    def test_regression_wird_genauso_benannt(self):
        """Die Gegenrichtung ist die nuetzlichere Auskunft: lange Serien, die ueberdurchschnittlich
        oft REISSEN, waeren ein Fade-Signal."""
        b = W.bilanz(self._z(200, 80, erwartet=60))
        self.assertLess(b["ogPct"], 60)
        self.assertEqual(b["urteil"], "kehrt um")

    def test_ohne_erwartung_gibt_es_keinen_vergleich(self):
        """Eine Trefferquote ohne die Erwartung ist keine Zahl — dieselbe Regel wie
        „Trefferquote ohne die Quoten"."""
        b = W.bilanz([{"erfuellt": True} for _ in range(40)])
        self.assertEqual(b["urteil"], "kein Vergleich")

    def test_unaufloesbare_zeilen_senken_den_nenner_sichtbar(self):
        z = self._z(40, 30) + [{"erfuellt": None, "erwartetPct": 60} for _ in range(5)]
        b = W.bilanz(z)
        self.assertEqual(b["n"], 40)
        self.assertEqual(b["unaufloesbar"], 5)


# ─────────────────────────────────────────────────────────────────────────────
# 🔴 12.09.2026 (Lucas, Plattform-Audit) — das Serien-Buch war seit jeher leer.
# ─────────────────────────────────────────────────────────────────────────────
class TestAbrechnungHaengtNichtAmSchluessel(unittest.TestCase):
    """`build_recap` suchte das Spiel ueber `pickKey`: String zerlegen, die letzten zwei Teile als
    Heim/Auswaerts lesen. In **allen 132** bewachten Serien stand `pickKey: null` —
    `compute_streaks.py` baut den Schluessel intern (Z. 378), kopierte ihn aber nie nach
    `s["next"]`, und von dort holt ihn der Watch. Jede Zeile fiel in `continue`.

    Folge: `streak_record.json` existierte nicht, `streak-log.json` war 0 Bytes. Das Buch, das die
    Frage „machen die Serien Sinn" beantworten soll, hatte nach Wochen **null** Zeilen.

    Die Abrechnung geht jetzt ueber Team + Datum — das steht immer im Eintrag. Ein zusammengesetzter
    String ist nur eine Abkuerzung dorthin, und eine Abkuerzung, die durch zwei Module reisen muss,
    geht irgendwo verloren.
    """

    def _welt(self):
        return {"groups": {"ENG": {"fixtures": [
            {"home": "65", "away": "63", "date": "2026-09-10", "matchday": 5,
             "result": {"status": "FT", "home_score": 2, "away_score": 1}},
            {"home": "42", "away": "99", "date": "2026-09-10", "matchday": 5,
             "result": {"status": "NS"}},
        ]}}, "koFixtures": []}

    def _eintrag(self, **over):
        e = {"teamId": "65", "team": "Arsenal", "type": "scored", "market": "Team trifft",
             "length": 7, "date": "2026-09-10", "kickoff": "2026-09-10T18:00:00Z",
             "pickKey": None, "oppName": "Chelsea"}
        e.update(over)
        return e

    def test_ohne_pickKey_wird_trotzdem_abgerechnet(self):
        msgs, done, buch = W.build_recap(self._welt(), {"k": self._eintrag()}, "2026-09-12")
        self.assertEqual(len(buch), 1, "genau der Fall, der bisher still durchfiel")
        self.assertTrue(buch[0]["erfuellt"], "Arsenal hat 2 Tore geschossen")
        self.assertEqual(done, ["k"])

    def test_auswaertsteam_wird_genauso_gefunden(self):
        msgs, done, buch = W.build_recap(
            self._welt(), {"k": self._eintrag(teamId="63", team="Chelsea")}, "2026-09-12")
        self.assertEqual(len(buch), 1)

    def test_ein_nicht_gespieltes_spiel_bleibt_offen(self):
        msgs, done, buch = W.build_recap(
            self._welt(), {"k": self._eintrag(teamId="42", team="X")}, "2026-09-12")
        self.assertEqual(buch, [], "ohne Endstand darf nichts gebucht werden")
        self.assertEqual(done, [], "und der Eintrag muss im Watch bleiben")

    def test_falsches_datum_faellt_nicht_auf_ein_anderes_spiel(self):
        """Gegenprobe: die Suche darf nicht einfach irgendein Spiel des Teams nehmen."""
        msgs, done, buch = W.build_recap(
            self._welt(), {"k": self._eintrag(date="2026-09-03")}, "2026-09-12")
        self.assertEqual(buch, [])

    def test_pickKey_bleibt_als_zweiter_weg(self):
        """Wird ein Spiel verlegt, ist das Datum im Watch veraltet — dann traegt der Schluessel."""
        welt = self._welt()
        welt["groups"]["ENG"]["fixtures"][0]["date"] = "2026-09-11"   # verlegt
        msgs, done, buch = W.build_recap(
            welt, {"k": self._eintrag(pickKey="ENG-5-65-63")}, "2026-09-12")
        self.assertEqual(len(buch), 1, "der Schluessel muss den verlegten Fall noch fangen")

    def test_compute_streaks_stempelt_den_schluessel_mit(self):
        quelle = (Path(__file__).resolve().parent.parent / "compute_streaks.py").read_text(
            encoding="utf-8")
        self.assertIn('"pickKey": nf.get("pickKey")', quelle,
                      "ein Feld, das ein anderes Modul liest, gehoert gefuellt")


class TestErwartungTraegtDasUrteil(unittest.TestCase):
    """Als das Buch zum ersten Mal Zeilen bekam, standen sofort 52 Liga-Zeilen drin — aber nur
    **2** trugen eine Erwartung (das Feld gibt es erst seit dem 09.09.). Das Urteil lautete
    trotzdem „die Erwartung von 71,0 % liegt im Band", als waere sie aus denselben 52 gerechnet.
    Ein Mittel aus 2 Zeilen, angelegt an 52, ist kein Vergleich."""

    def _zeilen(self, n, treffer, mit_erwartung, erwartet=70.0):
        raus = []
        for i in range(n):
            z = {"key": str(i), "erfuellt": i < treffer}
            if i < mit_erwartung:
                z["erwartetPct"] = erwartet
            raus.append(z)
        return raus

    def test_zu_wenige_erwartungen_ergeben_kein_urteil(self):
        b = W.bilanz(self._zeilen(52, 37, 2))
        self.assertEqual(b["urteil"], "Erwartung zu duenn")
        self.assertIn("2 von 52", b["grund"])

    def test_auch_genug_zeilen_aber_unter_der_haelfte_reicht_nicht(self):
        b = W.bilanz(self._zeilen(60, 45, 25))
        self.assertEqual(b["urteil"], "Erwartung zu duenn",
                         "25 von 60 ist unter der Haelfte — das Mittel gilt fuer die Minderheit")

    def test_mit_breiter_erwartung_urteilt_es_wieder(self):
        b = W.bilanz(self._zeilen(60, 45, 60, erwartet=50.0))
        self.assertEqual(b["urteil"], "traegt sich selbst")

    def test_die_quote_selbst_steht_trotzdem_da(self):
        """Kein Urteil heisst nicht keine Zahl — die Trefferquote und ihr Band bleiben sichtbar."""
        b = W.bilanz(self._zeilen(52, 37, 2))
        self.assertEqual(b["quotePct"], 71.2)
        self.assertIsNotNone(b["ugPct"])


# ─────────────────────────────────────────────────────────────────────────────
# 🔴 12.09.2026 (Lucas: „Ich hab grad knapp 20 pushes in public bekommen — irgendwelche
# einzelner zu Serien. Sowas gabs in der Form noch nie. Was ist das für Mist")
#
# Verursacht vom Fix direkt darueber. Bis dahin rechnete das Buch NIE etwas ab (alle `pickKey`
# null); der Fix machte die Abrechnung ueber Team+Datum moeglich und raeumte in EINEM Lauf den
# Rueckstau aus sechs Wochen ab — 52 Zeilen, 52 Pushes. Der Lauf davor hatte 0 Nachrichten
# gesendet, der danach haette weitere ~59 aus dem MLS-Datensatz geschickt.
#
# Zwei unabhaengige Riegel, beide gegen die Klasse:
#   1. Frische  — alte Abrechnungen werden gebucht, nicht gepostet.
#   2. Form     — ein Lauf erzeugt hoechstens EINE Nachricht, egal wie viele frisch sind.
# Ein Riegel allein reicht nicht: die Frische haette den 12.09. gefangen, aber nicht einen Tag
# mit 30 gleichzeitig endenden Spielen; die Form haette beides gefangen, aber ein sechs Wochen
# altes Ergebnis trotzdem gepostet.
# ─────────────────────────────────────────────────────────────────────────────
class TestRueckstauSendetNicht(unittest.TestCase):
    JETZT = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)

    def _welt(self, tag="2026-09-10"):
        return {"groups": {"ENG": {"fixtures": [
            {"home": "65", "away": "63", "date": tag, "matchday": 5,
             "result": {"status": "FT", "home_score": 2, "away_score": 1}}]}}, "koFixtures": []}

    def _eintrag(self, **over):
        e = {"teamId": "65", "team": "Arsenal", "type": "scored", "market": "Team trifft",
             "length": 7, "date": "2026-09-10", "kickoff": "2026-09-10T18:00:00Z",
             "oppName": "Chelsea"}
        e.update(over)
        return e

    # ── Riegel 1: Frische ────────────────────────────────────────────────────
    def test_frische_abrechnung_wird_gepostet(self):
        msgs, done, buch = W.build_recap(
            self._welt(), {"k": self._eintrag()}, "2026-09-12",
            now=datetime(2026, 9, 10, 21, 0, tzinfo=timezone.utc))
        self.assertEqual(len(msgs), 1)
        self.assertEqual(len(buch), 1)

    def test_alte_abrechnung_wird_gebucht_aber_nicht_gepostet(self):
        """Der Kern des Vorfalls: die Zeile darf nicht verlorengehen, nur die Nachricht."""
        msgs, done, buch = W.build_recap(
            self._welt("2026-07-28"),
            {"k": self._eintrag(date="2026-07-28", kickoff="2026-07-28T18:00:00Z")},
            "2026-09-12", now=self.JETZT)
        self.assertEqual(msgs, [], "sechs Wochen alt — keine Nachricht")
        self.assertEqual(len(buch), 1, "aber die Zeile MUSS ins Buch")
        self.assertTrue(buch[0]["erfuellt"])
        self.assertEqual(done, ["k"], "und der Eintrag faellt aus dem Watch")

    def test_genau_an_der_grenze(self):
        """Gegenprobe zur Grenze selbst: knapp drunter sendet, knapp drueber nicht."""
        ko = datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc) + timedelta(hours=2)
        knapp_drunter = ko + timedelta(hours=W.RECAP_MAX_ALTER_H - 1)
        knapp_drueber = ko + timedelta(hours=W.RECAP_MAX_ALTER_H + 1)
        a, _d, _b = W.build_recap(self._welt(), {"k": self._eintrag()}, "2026-09-12",
                                  now=knapp_drunter)
        b, _d, _b2 = W.build_recap(self._welt(), {"k": self._eintrag()}, "2026-09-12",
                                   now=knapp_drueber)
        self.assertEqual(len(a), 1)
        self.assertEqual(b, [])

    def test_ohne_zeitangabe_wird_nicht_gepostet(self):
        """Fehlende Information rendert als harmloser Default — harmlos heisst hier: still.

        Andersherum waere genau der 12.09.: ein Eintrag ohne verwertbares Datum haette
        gesendet, weil „unbekannt" als „frisch" durchgeht.
        """
        e = self._eintrag(kickoff=None, date="")
        welt = self._welt()
        # ohne `date` findet die Datumssuche nichts → ueber pickKey abrechnen
        msgs, done, buch = W.build_recap(
            welt, {"k": dict(e, pickKey="ENG-5-65-63")}, "2026-09-12", now=self.JETZT)
        self.assertEqual(len(buch), 1, "abgerechnet wird trotzdem")
        self.assertEqual(msgs, [], "aber ohne bestimmbaren Zeitpunkt wird nicht gesendet")

    def test_datum_ohne_kickoff_zaehlt_ab_spieltag(self):
        msgs, _d, _b = W.build_recap(
            self._welt(), {"k": self._eintrag(kickoff=None)}, "2026-09-12",
            now=datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(len(msgs), 1, "Spieltag + 24 h ist am Folgetag frueh noch frisch")

    # ── Riegel 2: Form ───────────────────────────────────────────────────────
    def test_ein_lauf_sendet_hoechstens_eine_nachricht(self):
        """Nicht „selten viele", sondern nie mehr als eine — fuer JEDE Menge."""
        for n in (0, 1, 2, 5, 20, 52, 200):
            with self.subTest(n=n):
                self.assertLessEqual(len(W.recap_nachrichten([f"Zeile {i}" for i in range(n)])),
                                     1, f"{n} Abrechnungen duerfen nie {n} Pushes werden")

    def test_einzelne_abrechnung_bleibt_die_originalnachricht(self):
        self.assertEqual(W.recap_nachrichten(["✅ <b>X hält</b>"]), ["✅ <b>X hält</b>"])

    def test_sammelnachricht_traegt_alle_zeilen_oder_sagt_wie_viele_fehlen(self):
        raus = W.recap_nachrichten([f"Zeile {i}" for i in range(52)])[0]
        self.assertIn("52", raus, "die volle Zahl muss drinstehen, nicht nur die gezeigten")
        self.assertIn("Zeile 0", raus)
        fehlend = 52 - W.RECAP_DIGEST_MAX_ZEILEN
        self.assertIn(f"{fehlend} weitere", raus)

    def test_nichts_abgerechnet_ist_kein_push(self):
        self.assertEqual(W.recap_nachrichten([]), [])
        self.assertEqual(W.recap_nachrichten(None), [])

    # ── Der Weg durch main: der Zaehler, auf den ich geschaut habe ───────────
    def test_main_sendet_ueber_den_deckel_nicht_je_zeile(self):
        """Gegenprobe gegen die alte Zeile `for m in msgs: tg_send(m)`."""
        quelle = (Path(__file__).resolve().parent.parent /
                  "telegram_streak_watch.py").read_text(encoding="utf-8")
        ohne_kommentar = "\n".join(z for z in quelle.splitlines()
                                   if not z.lstrip().startswith("#"))
        self.assertIn("pushes = recap_nachrichten(msgs)", ohne_kommentar)
        self.assertNotIn("for m in msgs:", ohne_kommentar,
                         "je abgerechneter Zeile senden ist genau der Vorfall vom 12.09.")
