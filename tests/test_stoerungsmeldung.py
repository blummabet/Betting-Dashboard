"""🔴 20.09.2026 (Lucas: „ich weiß dann nicht, funktioniert das eigentlich, was tracken wir da").

Drei Guard-Batterien laufen 57 Prüfungen und schreiben sie in drei Artefakte — und sonst
nirgendwohin. Am Abend des 20.09. meldeten sie zusammen 14 Dinge, darunter Positionen, die seit
13 Tagen offen sind, und 39 % aufgelöste Tennis-Märkte.

Fehlerklasse: ein Messgerät, dessen Zeiger niemand ansieht.

Diese Tests halten die vier Eigenschaften fest, die eine solche Meldung von „noch einer Fläche"
unterscheiden — und die als Erstes kippen, wenn jemand sie anfasst.
"""
import sys
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stoerungsmeldung as S

JETZT = datetime(2026, 9, 21, 7, 0, tzinfo=timezone.utc)


def _batterie(checks, alter_h=1.0):
    return {"generatedAt": (JETZT - timedelta(hours=alter_h)).isoformat(), "checks": checks}


def _c(label, ok=False, sev="error", fails=("etwas",), cid=None):
    d = {"label": label, "ok": ok, "severity": sev, "nFail": 0 if ok else len(fails),
         "failures": list(fails)}
    if cid:
        d["id"] = cid
    return d


class TestStilleWennNichtsKaputtIst(unittest.TestCase):
    """Eine tägliche „alles gut"-Nachricht wird nach einer Woche weggewischt — und dann auch
    die, in der etwas steht."""

    def test_alles_gruen_ergibt_keine_nachricht(self):
        a = {"x.json": _batterie([_c("A", ok=True), _c("B", ok=True)])}
        self.assertEqual(S.baue_meldung(S.sammeln(a, JETZT), JETZT), "")

    def test_ein_einziger_befund_ergibt_eine_nachricht(self):
        a = {"x.json": _batterie([_c("A", ok=True), _c("Ergebnisse kommen an")])}
        self.assertNotEqual(S.baue_meldung(S.sammeln(a, JETZT), JETZT), "")


class TestGeldStehtOben(unittest.TestCase):
    def test_geld_vor_messung(self):
        a = {"x.json": _batterie([_c("Takt: Cron gegen gemessene Laeufe", sev="warn"),
                                  _c("Ergebnisse kommen an")])}
        t = S.baue_meldung(S.sammeln(a, JETZT), JETZT)
        self.assertLess(t.index("Ergebnisse kommen an"), t.index("Takt:"))

    def test_die_einstufung_kommt_aus_der_liste_nicht_aus_der_schwere(self):
        """Ein Geld-Check bleibt Geld, auch wenn er nur `warn` ist — und umgekehrt."""
        a = {"x.json": _batterie([_c("Jeder Push hat seinen Beleg", sev="warn"),
                                  _c("Stumme Signale: wer hat nie gefeuert?", sev="error")])}
        b = S.sammeln(a, JETZT)
        self.assertEqual([z["label"] for z in b["geld"]], ["Jeder Push hat seinen Beleg"])
        self.assertEqual([z["label"] for z in b["messung"]],
                         ["Stumme Signale: wer hat nie gefeuert?"])

    def test_innerhalb_einer_gruppe_zuerst_die_fehler(self):
        a = {"x.json": _batterie([_c("Positionswert ist frisch", sev="warn"),
                                  _c("Ergebnisse kommen an", sev="error")])}
        self.assertEqual([z["label"] for z in S.sammeln(a, JETZT)["geld"]][0],
                         "Ergebnisse kommen an")


class TestEinVeraltetesMessgeraetIstSelbstEinBefund(unittest.TestCase):
    """Die Klasse, die an diesem Tag dreimal zugeschlagen hat: fehlende Information rendert als
    harmloser Default. Eine stille Meldung über einer toten Batterie hiesse „alles gut"."""

    def test_eine_alte_batterie_meldet_sich_als_blind(self):
        a = {"x.json": _batterie([_c("A", ok=True)], alter_h=S.ALT_H + 1)}
        b = S.sammeln(a, JETZT)
        self.assertEqual(len(b["blind"]), 1)
        self.assertIn("Blind", S.baue_meldung(b, JETZT))

    def test_ihre_checks_werden_nicht_mehr_geglaubt(self):
        """Weder die grünen noch die roten — sie sagt gerade gar nichts."""
        a = {"x.json": _batterie([_c("Ergebnisse kommen an")], alter_h=S.ALT_H + 1)}
        b = S.sammeln(a, JETZT)
        self.assertEqual(b["geld"], [])
        self.assertEqual(len(b["blind"]), 1)

    def test_ohne_zeitstempel_ebenfalls_blind(self):
        b = S.sammeln({"x.json": {"checks": [_c("A", ok=True)]}}, JETZT)
        self.assertEqual(len(b["blind"]), 1)

    def test_eine_unlesbare_datei_ebenfalls(self):
        self.assertEqual(len(S.sammeln({"x.json": None}, JETZT)["blind"]), 1)

    def test_eine_frische_batterie_ist_nicht_blind(self):
        self.assertEqual(S.sammeln({"x.json": _batterie([_c("A", ok=True)], 1.0)},
                                   JETZT)["blind"], [])


class TestEinNeuerCheckVerschwindetNichtStill(unittest.TestCase):
    """Ein neuer geldnaher Check landet per Default unter „Messung". Damit das kein stiller
    Default wird, meldet er sich als „nicht eingestuft" — eine Entscheidung wird erzwungen."""

    def test_ein_unbekannter_geldnaher_check_faellt_auf(self):
        a = {"x.json": _batterie([_c("Neue Wette ohne Gegenbuchung")])}
        b = S.sammeln(a, JETZT)
        self.assertEqual(len(b["offen"]), 1)
        self.assertIn("Nicht eingestuft", S.baue_meldung(b, JETZT))

    def test_ein_check_ohne_geldwort_bleibt_still_unter_messung(self):
        b = S.sammeln({"x.json": _batterie([_c("Serien-Buch zeigt beide Buecher")])}, JETZT)
        self.assertEqual(b["offen"], [])
        self.assertEqual(len(b["messung"]), 1)

    def test_ein_geprueft_kein_geld_check_meldet_sich_nicht_mehr(self):
        b = S.sammeln({"x.json": _batterie([_c("Money Map meldet ihre Luecken")])}, JETZT)
        self.assertEqual(b["offen"], [])

    def test_auch_ein_harmlos_klingender_check_braucht_eine_entscheidung(self):
        """🔴 21.09.2026. `braucht_entscheidung` verlangte eine Einstufung nur, wenn der NAME
        geldnah klang (`GELD_WORTE`). `absagen_abgerechnet` traegt keines dieser Woerter und
        ist trotzdem Geld: ein Spiel, das nie abrechnet, faellt aus der Bilanz. Im
        Mutationstest liess sich der Eintrag ersatzlos loeschen, ohne dass etwas rot wurde.
        Der Kopf der Datei sagt selbst: „Geld ist eine Entscheidung, keine Zeichenkette."
        Fehlerklasse: ein Waechter, der nur die Faelle einfordert, die er ohnehin erkennt.
        """
        self.assertTrue(S.braucht_entscheidung({"id": "voellig_neuer_waechter_ohne_geldwort"}))
        self.assertTrue(S.braucht_entscheidung({"label": "Irgendeine neue Pruefung"}))

    def test_ein_eingestufter_check_braucht_keine_mehr(self):
        self.assertFalse(S.braucht_entscheidung({"id": "absagen_abgerechnet"}))
        self.assertFalse(S.braucht_entscheidung({"id": "clv_card_coverage"}))

    def test_am_echten_bestand_ist_nichts_uneingestuft(self):
        """Der Riegel gegen eine Liste, die niemand pflegt: stehen die echten Checks nicht alle
        in GELD oder GEPRUEFT_KEIN_GELD, schlägt das hier an."""
        import json
        offen = []
        for n, d in S.quellen().items():
            for c in ((d or {}).get("checks") or []):
                if S.braucht_entscheidung(c):
                    offen.append(S.schluessel(c))
        self.assertEqual(offen, [],
                         "diese Checks brauchen eine Einstufung in stoerungsmeldung.py: %s"
                         % ", ".join(offen))


class TestEinmalAmTagImFenster(unittest.TestCase):
    def test_im_fenster_und_noch_nicht_gesendet(self):
        self.assertTrue(S.soll_senden({}, JETZT))

    def test_heute_schon_gesendet(self):
        self.assertFalse(S.soll_senden({"zuletzt": "2026-09-21"}, JETZT))

    def test_gestern_gesendet_heute_wieder(self):
        self.assertTrue(S.soll_senden({"zuletzt": "2026-09-20"}, JETZT))

    def test_ausserhalb_des_fensters_nicht(self):
        self.assertFalse(S.soll_senden({}, JETZT.replace(hour=15)))
        self.assertFalse(S.soll_senden({}, JETZT.replace(hour=3)))


class TestDieNachrichtBleibtLesbar(unittest.TestCase):
    def test_die_messung_wird_gekappt_das_geld_nicht(self):
        # 21.09.2026: hier standen erfundene Labels („Messkram 0"…). Seit JEDER Check eine
        # Einstufung braucht, landen erfundene Namen unter „Nicht eingestuft" statt unter
        # „Messung" — und der Deckel, den dieser Test prueft, haengt an der Messung.
        # Deshalb echte, als Messung eingestufte Waechter.
        _echte_messung = ["clv_card_coverage", "trade_clv_coverage", "signal_coverage",
                          "soft_book_history", "soft_opening_captured", "ah_ladder_coverage",
                          "liga_market_coverage", "ko_apif_coverage", "finished_has_stats"]
        viele_messung = [_c(n, sev="warn") for n in _echte_messung]
        viel_geld = [_c("Ergebnisse kommen an"), _c("Positionswert ist frisch"),
                     _c("Jeder Push hat seinen Beleg"), _c("geschlossen heisst belegt"),
                     _c("offene Wette hat den Anpfiff ueberlebt")]
        t = S.baue_meldung(S.sammeln({"x.json": _batterie(viele_messung + viel_geld)}, JETZT),
                           JETZT)
        self.assertIn("und 5 weitere", t)
        for g in ("Ergebnisse kommen an", "Positionswert ist frisch",
                  "offene Wette hat den Anpfiff ueberlebt"):
            self.assertIn(g, t, "Geld wird nie gekappt")

    def test_lange_zeilen_werden_gekuerzt(self):
        lang = "x" * 500
        t = S.baue_meldung(S.sammeln({"x.json": _batterie([_c("Ergebnisse kommen an",
                                                              fails=(lang,))])}, JETZT), JETZT)
        self.assertNotIn(lang, t)
        self.assertIn("…", t)


if __name__ == "__main__":
    unittest.main()

# ── 21.09.2026: alle Batterien, und eine ruhende ist kein Fehler ─────────────────────────
class TestAlleBatterienWerdenGefundenNichtGelistet:
    """🔴 Lucas: „ich merke mir nicht, wo was ist." Die Meldung las drei Quellen. Die groesste
    Batterie im Haus — `wm_data_integrity`, rund 80 Waechter — schreibt je Datensatz nach
    `{praefix}_status.json`, und keine davon stand in der Liste. Der Satz unter der Meldung
    („kommt nichts, ist nichts kaputt") war damit schlicht nicht wahr.

    Mein erster Anlauf war, die Liste zu verlaengern. Er ging daneben: ich trug
    `wm_status.json` nach — die hat gar keine `checks` und ist seit dem 19.07. tot — und
    vergass `mls_status.json`, eine echte Batterie. Den toten Namen fing
    `tests/test_tote_quellen.py`; den fehlenden haette niemand gefangen, weil eine zu kurze
    Liste nichts wirft.

    Fehlerklasse: eine Zusammenfassung, die ihre Quellen aufzaehlt statt sie zu finden.
    """

    def test_ein_name_entscheidet_nicht_die_form_entscheidet(self):
        assert S.ist_batterie({"checks": [], "generatedAt": "x"})
        assert not S.ist_batterie({"updatedAt": "x", "built": 3})          # esports_poly_status
        assert not S.ist_batterie({"checks": {"a": 1}})
        assert not S.ist_batterie(None) and not S.ist_batterie([])

    def test_am_echten_bestand_sind_alle_sechs_batterien_dabei(self):
        """Darunter `mls_status.json`, die ich beim Verlaengern der Liste vergessen hatte."""
        gefunden = set(S.quellen())
        for n in ("uebersicht_integrity.json", "poly_status.json", "betfair_status.json",
                  "liga_status.json", "mls_status.json", "wm_status.json"):
            assert n in gefunden, "%s fehlt — %s" % (n, sorted(gefunden))

    def test_ein_feed_stand_ist_keine_batterie(self):
        """`esports_poly_status.json` heisst wie eine Batterie und traegt einen Feed-Stand —
        kein `checks`, also nichts, worueber diese Meldung etwas sagen koennte."""
        assert "esports_poly_status.json" not in S.quellen()

    def test_eine_neue_batterie_meldet_sich_selbst(self):
        """⭐ Der eigentliche Punkt: kein Mensch muss etwas nachtragen."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "voellig_neue_engine_status.json").write_text(
                json.dumps({"generatedAt": "2026-09-21T00:00:00Z", "checks": []}))
            assert "voellig_neue_engine_status.json" in S.quellen(d)

    def test_eine_kaputte_batterie_verschwindet_nicht_still(self):
        """Unlesbar heisst nicht „keine Batterie" — sonst rendert genau der Ausfall, den die
        Meldung finden soll, als harmloser Default. Sie bleibt drin und wird „blind"."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "kaputt_status.json").write_text("{ das ist kein json")
            q = S.quellen(d)
            assert q == {"kaputt_status.json": None}
            assert [x["quelle"] for x in S.sammeln(q)["blind"]] == ["kaputt_status.json"]


class TestEineRuhendeBatterieIstKeineStoerung:
    """🔴 Lucas: „Der WM Mist ist vorbei, interessiert niemand." Die WM-Batterie ist seit dem
    19. Juli eingefroren. Als „blind" gemeldet stuende sie ab jetzt jeden Tag mit derselben
    Zeile in der Nachricht — fuer immer.
    Fehlerklasse: ein abgeschlossener Zustand, der als Stoerung gemeldet wird.
    """

    def _art(self, alter_h):
        from datetime import datetime, timezone, timedelta
        jetzt = datetime.now(timezone.utc)
        return {"x.json": {"generatedAt": (jetzt - timedelta(hours=alter_h)).isoformat(),
                           "checks": []}}, jetzt

    def test_vierzehn_tage_still_heisst_ruht_nicht_blind(self):
        art, jetzt = self._art(S.RUHEND_H + 1)
        b = S.sammeln(art, jetzt)
        assert [x["quelle"] for x in b["ruht"]] == ["x.json"]
        assert b["blind"] == []

    def test_ein_echter_ausfall_bleibt_blind(self):
        """Zwischen ALT_H und RUHEND_H ist es eine Stoerung — genau dafuer ist blind da."""
        art, jetzt = self._art(S.ALT_H + 2)
        b = S.sammeln(art, jetzt)
        assert [x["quelle"] for x in b["blind"]] == ["x.json"]
        assert b["ruht"] == []

    def test_eine_frische_batterie_ist_weder_noch(self):
        art, jetzt = self._art(1)
        b = S.sammeln(art, jetzt)
        assert b["blind"] == [] and b["ruht"] == []

    def test_ruhend_allein_loest_keine_nachricht_aus(self):
        """Eine ruhende Batterie ist kein Grund, jemandem aufs Telefon zu gehen."""
        from datetime import datetime, timezone
        t = S.baue_meldung({"geld": [], "messung": [], "offen": [], "blind": [],
                            "ruht": [{"quelle": "wm_status.json", "alterH": 64 * 24}]},
                           datetime.now(timezone.utc))
        assert t == ""

    def test_gibt_es_sonst_etwas_wird_sie_genannt(self):
        """Verschwiegen darf sie trotzdem nicht werden: eine Luecke, die sich durch Zeitablauf
        selbst erledigt, hinterlaesst sonst keine Spur, und in drei Monaten weiss niemand mehr,
        dass diese Pruefung existiert."""
        from datetime import datetime, timezone
        t = S.baue_meldung({"geld": [{"quelle": "q", "label": "L", "severity": "error",
                                      "nFail": 1, "failures": ["x"]}],
                            "messung": [], "offen": [], "blind": [],
                            "ruht": [{"quelle": "wm_status.json", "alterH": 64 * 24}]},
                           datetime.now(timezone.utc))
        assert "Ruht: wm_status.json (64 Tage)" in t
        assert "ist auch kein Fehler" in t


# ── 21.09.2026: ein Vorfall, eine Zeile ──────────────────────────────────────────────────
class TestDieselbeStoerungAusZweiBatterien:
    """🔴 Direkt nach dem Umbau auf `quellen()`: mit liga UND mls in der Meldung stand
    „Stake Radar: seit 337 h kein Lauf" zweimal da und „Poly-Live-Scan taktet" auch — einmal
    mit 3,7 h, einmal mit 3,4 h. Beide Batterien pruefen denselben globalen Workflow.
    Fehlerklasse: eine Zaehlung, die die Quellen zaehlt statt die Vorfaelle.
    """

    def _z(self, quelle, label, fail, nfail=1, sev="error"):
        return {"quelle": quelle, "label": label, "severity": sev,
                "nFail": nfail, "failures": [fail]}

    def test_zwei_batterien_derselbe_check_eine_zeile(self):
        r = S.falten([self._z("liga_status.json", "Poly-Live-Scan taktet", "vor 3.7h"),
                      self._z("mls_status.json", "Poly-Live-Scan taktet", "vor 3.4h")])
        assert len(r) == 1
        assert r[0]["quellen"] == ["liga_status.json", "mls_status.json"]

    def test_verschiedene_checks_bleiben_getrennt(self):
        r = S.falten([self._z("liga_status.json", "A", "x"),
                      self._z("liga_status.json", "B", "y")])
        assert len(r) == 2

    def test_nfail_wird_gemaxt_nicht_summiert(self):
        """Derselbe Ausfall, zweimal gesehen, ist nicht doppelt so schlimm."""
        r = S.falten([self._z("liga_status.json", "A", "x", nfail=3),
                      self._z("mls_status.json", "A", "y", nfail=2)])
        assert r[0]["nFail"] == 3

    def test_die_schwerere_einstufung_gewinnt(self):
        r = S.falten([self._z("liga_status.json", "A", "x", sev="warn"),
                      self._z("mls_status.json", "A", "y", sev="error")])
        assert r[0]["severity"] == "error"

    def test_beide_beispiele_bleiben_lesbar(self):
        """Die Zahlen unterscheiden sich — man will beide sehen, nur nicht zweimal die Zeile."""
        r = S.falten([self._z("liga_status.json", "A", "vor 3.7h"),
                      self._z("mls_status.json", "A", "vor 3.4h")])
        assert r[0]["failures"] == ["vor 3.7h", "vor 3.4h"]

    def test_eine_quelle_wird_nicht_genannt(self):
        """Bei einer einzigen Quelle sagt der Name nichts und kostet nur Platz."""
        assert S._quellen_kurz({"quellen": ["liga_status.json"]}) == ""
        assert S._quellen_kurz({}) == ""

    def test_zwei_quellen_stehen_dran(self):
        assert S._quellen_kurz({"quellen": ["liga_status.json", "mls_status.json"]}) \
            == " (liga, mls)"

    def test_am_echten_bestand_steht_keine_zeile_doppelt(self):
        """⭐ Der Riegel: aus den LIVE-Artefakten darf kein Label zweimal kommen."""
        b = S.sammeln(S.quellen())
        for topf in ("geld", "messung", "offen"):
            labels = [x["label"] for x in b[topf]]
            assert len(labels) == len(set(labels)), "%s doppelt: %s" % (topf, labels)
