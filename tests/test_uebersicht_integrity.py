"""tests/test_uebersicht_integrity.py — 04.09.2026

Lucas: „mir waere es wichtig fehlerfrei zu sein, weil sonst ist die ganze Arbeit in Wahrheit
umsonst."

Die Betfair-, Poly- und WM-Pipelines haben je eine Guard-Batterie auf ihre eigenen Daten. Die
UEBERSICHT hatte keine — dabei ist sie die einzige Flaeche, die elf Engines zu SAETZEN verdichtet,
und genau dort entstehen die Fehler. Die drei Funde vom 04.09. waren kein Absturz, keine
Fehlrechnung, kein Datenfehler: es waren Behauptungen, die zum Schreibzeitpunkt stimmten und
danach still veralteten.

Diese Tests pruefen die Guards selbst — jeder muss den Vorfall fangen, aus dem er entstanden ist.
Ein Guard, der seinen eigenen Fall nicht faengt, ist Dekoration.
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
spec = importlib.util.spec_from_file_location("ui_t", os.path.join(ROOT, "uebersicht_integrity.py"))
UI = importlib.util.module_from_spec(spec)
spec.loader.exec_module(UI)


def _ok(res, label):
    return [c for c in res if c["label"] == label][0]["ok"]


class SerienRangfolge(unittest.TestCase):
    """Der Fund: „Beste Streaks" zeigte fuenfmal „Team trifft 15x · Grundrate 82 %"."""

    def _st(self, **kw):
        s = {"length": 15, "zufallPct": 3.87}
        s.update(kw)
        # eigene dicts, sonst aendert pop() alle vier auf einmal
        return {"_meta": {"sortiert": "zufallPct"}, "streaks": [dict(s) for _ in range(4)]}

    def test_gesunder_stand_faellt_nicht_auf(self):
        self.assertTrue(UI.check_serien_rangfolge({"ligaStreaks": self._st()})["ok"])

    def test_fehlendes_seltenheitsmass_wird_gemeldet(self):
        d = self._st()
        for s in d["streaks"]:
            s.pop("zufallPct")
        c = UI.check_serien_rangfolge({"ligaStreaks": d})
        self.assertFalse(c["ok"])
        self.assertIn("Laengen-Sortierung", c["failures"][0])

    def test_abweichendes_sortierkriterium_wird_gemeldet(self):
        d = self._st()
        d["_meta"]["sortiert"] = "length"
        self.assertFalse(UI.check_serien_rangfolge({"ligaStreaks": d})["ok"])

    def test_leerer_datensatz_ist_kein_fehler(self):
        self.assertTrue(UI.check_serien_rangfolge({"ligaStreaks": {"streaks": []}})["ok"])


class FreigabeGrund(unittest.TestCase):
    """Der Fund: „keine Schublade hat ihre Untergrenze ueber null" — Liga·ABWAEGEN stand
    bei ROI-UG +3,7 % und scheiterte an CLV."""

    def test_ohne_roiLb_kann_der_grund_nur_geraten_werden(self):
        f = {"regeln": {"minN": 30}, "alle": [{"schublade": "X", "n": 46, "clvLb": -2.1}]}
        c = UI.check_freigabe_grund({"freigabe": f})
        self.assertFalse(c["ok"])
        self.assertIn("roiLb", c["failures"][0])

    def test_der_reale_fall_wird_als_hinweis_benannt(self):
        f = {"regeln": {"minN": 30},
             "alle": [{"schublade": "Liga · ABWÄGEN", "n": 46, "roiLb": 0.037, "clvLb": -2.16}]}
        c = UI.check_freigabe_grund({"freigabe": f})
        self.assertTrue(c["ok"], "das ist kein Datenfehler, sondern ein Zustand")
        self.assertIn("Liga · ABWÄGEN", c["hinweis"])
        self.assertIn("CLV", c["hinweis"])

    def test_unreife_schubladen_zaehlen_nicht(self):
        f = {"regeln": {"minN": 30}, "alle": [{"schublade": "X", "n": 5}]}
        self.assertTrue(UI.check_freigabe_grund({"freigabe": f})["ok"])


class PolyKachel(unittest.TestCase):
    """Der Fund: „🎮 Poly Public n155 · 70 % · +5,0 %" — die Vorschau, die nichts sendet."""

    def test_ohne_sendet_flag_schlaegt_es_an(self):
        c = UI.check_poly_kachel_ist_keine_kanalbilanz({"pulse": {"poly": {"n": 155}}})
        self.assertFalse(c["ok"])
        self.assertTrue(any("sendet" in f for f in c["failures"]))

    def test_sendet_true_waere_der_rueckfall(self):
        c = UI.check_poly_kachel_ist_keine_kanalbilanz(
            {"pulse": {"poly": {"n": 155, "sendet": True, "gesendetN": 3}}})
        self.assertFalse(c["ok"])

    def test_richtig_gekennzeichnet_ist_ok(self):
        c = UI.check_poly_kachel_ist_keine_kanalbilanz(
            {"pulse": {"poly": {"n": 155, "sendet": False, "gesendetN": 3}}})
        self.assertTrue(c["ok"])

    def test_gesendetN_none_ist_erlaubt(self):
        """Kein Buch heisst unbekannt — das Feld muss da sein, der Wert darf None sein."""
        c = UI.check_poly_kachel_ist_keine_kanalbilanz(
            {"pulse": {"poly": {"n": 5, "sendet": False, "gesendetN": None}}})
        self.assertTrue(c["ok"])


class StakeKategorien(unittest.TestCase):
    """Der Fund: „Chicago Cubs – Milwaukee Brewers" trotz US-Sport-Sperre in einer Kachel."""

    def test_zeile_ohne_kategorie_wird_gemeldet(self):
        c = UI.check_stake_kategorien({"stake": {"wetten": [{"kat": "Fußball"}, {}]}})
        self.assertFalse(c["ok"])

    def test_vollstaendig_gestempelt_ist_ok(self):
        self.assertTrue(UI.check_stake_kategorien(
            {"stake": {"wetten": [{"kat": "Fußball"}, {"kat": "US-Sport"}]}})["ok"])


class StakeSpielklasse(unittest.TestCase):
    """07.09.2026 — die Spielklasse kommt aus einer Tabelle, und eine Tabelle veraltet still.

    Stake nimmt laufend neue Ligen auf. Eine Liga ohne Eintrag verschwindet aus jeder Zeile
    der Ansicht, statt aufzufallen — der harmlose Default ist hier die LEERE.
    """

    def _ok_ctx(self, **ueber):
        c = {"stakeAus": {
            "randliga": {"nOhneEbene": 0, "ohneEbene": []},
            "schubladen": {"randliga_hoher_einsatz": {"belegt": False, "beinRoiUg": None},
                           "topliga_hoher_einsatz": {"belegt": False, "beinRoiUg": -0.14}}}}
        c["stakeAus"].update(ueber)
        return c

    def test_vollstaendige_tabelle_ist_ok(self):
        self.assertTrue(UI.check_stake_spielklasse(self._ok_ctx())["ok"])

    def test_neue_liga_ohne_ebene_schlaegt_an(self):
        c = self._ok_ctx(randliga={"nOhneEbene": 2, "ohneEbene": ["neue-liga", "noch-eine"]})
        r = UI.check_stake_spielklasse(c)
        self.assertFalse(r["ok"])
        self.assertIn("neue-liga", r["failures"][0])

    def test_zusammengelegte_richtungen_schlagen_an(self):
        c = self._ok_ctx()
        del c["stakeAus"]["schubladen"]["randliga_hoher_einsatz"]
        self.assertFalse(UI.check_stake_spielklasse(c)["ok"])

    def test_belegt_ohne_untergrenze_schlaegt_an(self):
        c = self._ok_ctx()
        c["stakeAus"]["schubladen"]["randliga_hoher_einsatz"] = {"belegt": True, "beinRoiUg": None}
        self.assertFalse(UI.check_stake_spielklasse(c)["ok"])

    def test_ohne_block_ist_es_eine_warnung_kein_fehler(self):
        r = UI.check_stake_spielklasse({"stakeAus": {}})
        self.assertTrue(r["ok"])
        self.assertIn("nichts gesagt", r.get("hinweis", ""))


class BetfairUrteil(unittest.TestCase):
    """Der Fund: die Fade-Schwelle stand an vier Stellen, die vierte bei -0,05 statt -0,10."""

    def test_fehlendes_urteil_im_artefakt_schlaegt_an(self):
        c = UI.check_betfair_urteil({"bfTrack": {"global": {"n": 100, "roiUg": -0.02}}})
        self.assertFalse(c["ok"])

    def test_bucket_mit_untergrenze_aber_ohne_urteil_faellt_auf(self):
        c = UI.check_betfair_urteil({"bfTrack": {
            "global": {"urteil": "neutral"},
            "byLeagueMarket": {"A|Match Odds": {"roiUg": -0.4}}}})
        self.assertFalse(c["ok"])

    def test_vollstaendig_ist_ok(self):
        c = UI.check_betfair_urteil({"bfTrack": {
            "global": {"urteil": "neutral"},
            "byLeagueMarket": {"A|Match Odds": {"roiUg": -0.4, "urteil": "verliert"}}}})
        self.assertTrue(c["ok"])


class Robustheit(unittest.TestCase):
    def test_die_batterie_laeuft_auf_leerem_kontext_durch(self):
        res = UI.run_checks({})
        self.assertEqual(len(res), len(UI.UEBERSICHT_CHECKS))
        self.assertTrue(all("ok" in c for c in res))

    def test_ein_abstuerzender_guard_kippt_die_batterie_nicht(self):
        def kaputt(ctx):
            raise ValueError("absichtlich")
        alt = list(UI.UEBERSICHT_CHECKS)
        try:
            UI.UEBERSICHT_CHECKS.append(kaputt)
            res = UI.run_checks({})
            letzter = res[-1]
            self.assertFalse(letzter["ok"])
            self.assertIn("gecrasht", letzter["failures"][0])
        finally:
            UI.UEBERSICHT_CHECKS[:] = alt

    def test_jeder_guard_traegt_seinen_vorfall_im_docstring(self):
        """Ein Guard ohne Vorfall ist eine Meinung — im Rest des Repos steht ueberall, WARUM."""
        for fn in UI.UEBERSICHT_CHECKS:
            self.assertTrue((fn.__doc__ or "").strip(), fn.__name__)
            self.assertIn("2026", fn.__doc__, fn.__name__ + ": kein Datum/Vorfall genannt")


class MoneyMapPolyGehoertZumSpiel(unittest.TestCase):
    """07.09.2026 (Uebersicht-Check): die Money Map zeigte fuer Al-Ahed v Al Ahli Akhaa Aley
    (Lebanese FA Cup) „Poly $267.964 · Konsens einig auf Al-Ahed · 2/3". Das Geld gehoerte zu
    Al Hilal v Al Ahli (Saudi Pro League) — einem Markt, der sechs Tage vorher abgerechnet war
    und im selben Board zwei Kacheln weiter mit $257K stand.

    Ein Konsens aus fremdem Geld ist schlimmer als kein Konsens: er sieht nach Bestaetigung aus.
    """

    def _ctx(self, poly_name):
        return {"moneyMap": {"rows": [{"home": "Al-Ahed", "away": "Al Ahli Akhaa Aley",
                                       "league": "Lebanese FA Cup",
                                       "betfair": {"side": "home", "eur": 8868},
                                       "poly": {"side": "home", "name": poly_name,
                                                "usd": 267964, "sharePct": 97}}]}}

    def test_fremder_poly_name_wird_gemeldet(self):
        r = UI.check_money_map_poly_gehoert_zum_spiel(self._ctx("Al Hilal Saudi Club"))
        self.assertEqual(len(r["failures"]), 1)
        self.assertIn("267964", r["failures"][0])

    def test_der_eigene_name_faellt_nicht_auf(self):
        r = UI.check_money_map_poly_gehoert_zum_spiel(self._ctx("Al-Ahed"))
        self.assertEqual(r["failures"], [])

    def test_abkuerzung_gilt_als_derselbe_name(self):
        # „Al Ahli Akhaa Aley" vs „Akhaa Ahli Aley" — ein Kern-Token genuegt, sonst waere der
        # Guard ein Namens-Matcher und wuerde bei jeder Schreibweise Fehlalarm schlagen.
        r = UI.check_money_map_poly_gehoert_zum_spiel(self._ctx("Akhaa Ahli Aley"))
        self.assertEqual(r["failures"], [])

    def test_zeile_ohne_poly_ist_kein_fall(self):
        ctx = {"moneyMap": {"rows": [{"home": "A", "away": "B", "poly": None}]}}
        self.assertEqual(UI.check_money_map_poly_gehoert_zum_spiel(ctx)["failures"], [])


class BetfairUrteilBrauchtDieRichtigeGrenze(unittest.TestCase):
    """07.09.2026 (Uebersicht-Check): 40 Buckets trugen „verliert", 37 davon mit einer
    Obergrenze ueber null und 18 mit positivem Punktschaetzer — bis +32,6 %."""

    def _ctx(self, **bucket):
        d = {"n": 36, "roi": 0.111, "roiUg": -0.208, "roiOg": 0.43, "urteil": "verliert"}
        d.update(bucket)
        return {"bfTrack": {"global": {"urteil": None},
                            "byLeagueMarket": {"Argentinian Primera Nacional|Match Odds": d}}}

    def test_verliert_ueber_null_wird_gemeldet(self):
        r = UI.check_betfair_urteil(self._ctx())
        self.assertTrue(any("Verlustbeleg" in f for f in r["failures"]), r["failures"])

    def test_belegter_verlust_faellt_nicht_auf(self):
        r = UI.check_betfair_urteil(self._ctx(roi=-0.30, roiUg=-0.50, roiOg=-0.10))
        self.assertEqual([f for f in r["failures"] if "Verlustbeleg" in f], [])

    def test_traegt_faellt_nicht_auf(self):
        r = UI.check_betfair_urteil(self._ctx(roi=0.3, roiUg=0.05, roiOg=0.55, urteil="traegt"))
        self.assertEqual([f for f in r["failures"] if "Verlustbeleg" in f], [])

    def test_altes_artefakt_ohne_obergrenze_wird_benannt(self):
        # Rollout-Luecke: der Code ist gefixt, der Produzent noch nicht gelaufen. Das ist ein
        # eigener Zustand und darf nicht wie „alles in Ordnung" aussehen.
        r = UI.check_betfair_urteil(self._ctx(roiOg=None))
        self.assertTrue(any("Obergrenze" in f for f in r["failures"]), r["failures"])


class TestPolyMarktSelbeMannschaft(unittest.TestCase):
    """08.09.2026: der Senioren-Markt hing am Nachwuchsspiel (Real Madrid U19 → $294.571 aus
    `ucl-rma-int-2026-09-08`), und derselbe Markt gleichzeitig an zwei Betfair-Spielen."""

    def _ctx(self, anker):
        return {"bfAnker": {"anker": anker}}

    def test_faengt_die_ebenen_vermischung(self):
        r = UI.check_poly_markt_gehoert_zur_selben_mannschaft(self._ctx({
            "1": {"league": "UEFA Youth League", "moneyName": "Real Madrid U19",
                  "poly": {"key": "ucl-rma-int-2026-09-08", "sideKey": "Real Madrid CF", "vol": 294571}},
        }))
        self.assertEqual(r["nFail"], 1)
        self.assertIn("Mannschaftsebene", r["failures"][0])

    def test_faengt_denselben_markt_an_zwei_spielen(self):
        r = UI.check_poly_markt_gehoert_zur_selben_mannschaft(self._ctx({
            "1": {"league": "UEFA Champions League", "moneyName": "Man City",
                  "poly": {"key": "ucl-por-mnc-2026-09-08", "sideKey": "Manchester City", "vol": 47300}},
            "2": {"league": "UEFA Youth League", "moneyName": "Man City U19",
                  "poly": {"key": "ucl-por-mnc-2026-09-08", "sideKey": "Manchester City", "vol": 47300}},
        }))
        # zweimal auffaellig: die Ebene UND der doppelt belegte Markt
        self.assertTrue(any("haengt an 2" in f for f in r["failures"]))

    def test_sauberer_join_bleibt_still(self):
        r = UI.check_poly_markt_gehoert_zur_selben_mannschaft(self._ctx({
            "1": {"league": "UEFA Champions League", "moneyName": "Real Madrid",
                  "poly": {"key": "ucl-rma-int-2026-09-08", "sideKey": "Real Madrid CF", "vol": 294571}},
            "2": {"league": "Serie A", "moneyName": "Inter", "poly": None},
        }))
        self.assertEqual(r["failures"], [])


class TestBuecherPunktestand(unittest.TestCase):
    """08.09.2026 - die Tafel von Ebene 2 zeigt Punkte UND ihre Aufschluesselung. Vier Wege,
    die Zahl ohne sichtbaren Unterschied zu entwerten. (Loest den Guard der Spielzentrale ab,
    die am selben Tag wieder ausgebaut wurde - 24 von 25 ihrer Zeilen standen ohnehin hier.)"""

    def _t(self, buch, punkte, moeglich, grund_ok, tiefe_ok=False, status=None):
        return {"buch": buch, "status": status or ("ja" if grund_ok else "nein"),
                "punkte": punkte, "moeglich": moeglich,
                "grund": {"ok": grund_ok, "text": "x"},
                "tiefe": {"ok": tiefe_ok, "text": "y"} if moeglich else None}

    def _ctx(self, teile, punkte=None, moeglich=None):
        p = sum(t["punkte"] for t in teile) if punkte is None else punkte
        m = sum(t["moeglich"] for t in teile) if moeglich is None else moeglich
        return {"killer": {"alleBewertet": [
            {"name": "Real Madrid", "liga": "UCL", "punkte": p, "moeglich": m, "teile": teile}]}}

    def test_saubere_zeile_bleibt_still(self):
        t = [self._t("BF", 3, 3, True, True), self._t("POLY", 0, 0, False, status="unbekannt")]
        self.assertEqual(UI.check_buecher_punktestand(self._ctx(t))["failures"], [])

    def test_punkte_muessen_die_summe_der_teile_sein(self):
        t = [self._t("BF", 2, 3, True)]
        r = UI.check_buecher_punktestand(self._ctx(t, punkte=9))
        self.assertTrue(any("Summe der Teile" in f for f in r["failures"]))

    def test_nicht_erhobenes_buch_darf_nicht_im_nenner_stehen(self):
        t = [self._t("BF", 3, 3, True), self._t("STAKE", 0, 3, False, status="unbekannt")]
        r = UI.check_buecher_punktestand(self._ctx(t))
        self.assertTrue(any("im Nenner" in f for f in r["failures"]))

    def test_tiefe_ohne_zustimmung_faellt_auf(self):
        # Sonst waere „viel Geld auf der GEGENSEITE, das schnell fliesst" ein Pluspunkt.
        t = [self._t("BF", 1, 3, False, tiefe_ok=True)]
        r = UI.check_buecher_punktestand(self._ctx(t))
        self.assertTrue(any("Tiefe" in f for f in r["failures"]))

    def test_zeile_ohne_aufschluesselung_faellt_auf(self):
        ctx = {"killer": {"alleBewertet": [{"name": "X", "liga": "L", "punkte": 7, "moeglich": 13}]}}
        r = UI.check_buecher_punktestand(ctx)
        self.assertTrue(any("Begruendung" in f for f in r["failures"]))


# ── 08.09.2026: der Nenner der Serien-Seltenheit ────────────────────────────────────────
# Externes Feedback, an den Artefakten bestaetigt: „Parma · Unter 2,5, 10er: 1 von 11.990
# (Liga-Basis 39 %)" stand neben „Eigenrate vor der Serie 80 %" — 0,8^10 sind 1 von 9.
#
# ⭐ Der aeltere Guard war dabei GRUEN: er prueft, dass `zufallPct` sauber aus der Liga-Basis
# folgt, und das tat sie. Ein Guard, der die Arithmetik einer Zahl bewacht, die die falsche
# Frage beantwortet, meldet nichts.
def _serie(**over):
    s = {"team": "Parma", "type": "under25", "length": 10, "basis": "prior", "preN": 5,
         "seltenheit": {"basis": "eigen", "ratePct": 80, "preN": 5, "einsZu": 9,
                        "erwartet": 340.16, "familie": 3168, "bandPct": [44, 95],
                        "einsZuBand": [2, 4097], "erwartetBand": [0.77, 1979.08],
                        "urteil": "erwartbar", "grund": "…"}}
    s.update(over)
    return s


def _ctx(*serien):
    return {"ligaStreaks": {"streaks": list(serien)}, "mlsStreaks": {"streaks": []}}


class TestSeltenheitsNenner(unittest.TestCase):
    def _n(self, ctx):
        return UI.check_serie_seltenheit_rechnet_mit_der_eigenen_rate(ctx)["nFail"]

    def test_gesunder_stand_faellt_nicht_auf(self):
        self.assertEqual(self._n(_ctx(_serie())), 0)

    def test_liga_nenner_trotz_eigener_rate_wird_gemeldet(self):
        """Der Fund selbst: eigene Vorgeschichte da, gerechnet wurde gegen den Liga-Schnitt."""
        s = _serie()
        s["seltenheit"] = dict(s["seltenheit"], basis="liga", urteil="nicht belegbar")
        self.assertGreaterEqual(self._n(_ctx(s)), 1)

    def test_liga_basis_darf_kein_urteil_tragen(self):
        """Ohne eigene Vorgeschichte gilt der Liga-Schnitt fuer ein Durchschnittsteam — ob
        dieses Team eines ist, wissen wir gerade nicht. Das ist „nicht gemessen", nicht
        „unauffaellig"."""
        s = _serie(basis="liga", preN=0)
        s["seltenheit"] = dict(s["seltenheit"], basis="liga", urteil="erwartbar")
        self.assertGreaterEqual(self._n(_ctx(s)), 1)

    def test_auffaellig_ohne_feldgroesse_wird_gemeldet(self):
        """Ohne die Zahl der geprueften Kombinationen ist jede Seltenheit ein Fund, den die
        Suche selbst erzeugt hat."""
        s = _serie()
        s["seltenheit"] = dict(s["seltenheit"], urteil="auffaellig", familie=None,
                               erwartetBand=[0.1, 0.5])
        self.assertGreaterEqual(self._n(_ctx(s)), 1)

    def test_auffaellig_trotz_erwartbarer_bandobergrenze_wird_gemeldet(self):
        s = _serie()
        s["seltenheit"] = dict(s["seltenheit"], urteil="auffaellig")
        self.assertGreaterEqual(self._n(_ctx(s)), 1)

    def test_zahl_die_nicht_aus_der_rate_folgt_wird_gemeldet(self):
        s = _serie()
        s["seltenheit"] = dict(s["seltenheit"], einsZu=99999)
        self.assertGreaterEqual(self._n(_ctx(s)), 1)

    def test_fehlende_seltenheit_ist_die_rollout_luecke(self):
        """Ein Code-Fix wirkt erst, wenn der Produzent neu gelaufen ist — das muss auffallen,
        statt als „alles gruen" durchzugehen."""
        s = _serie()
        s.pop("seltenheit")
        self.assertGreaterEqual(self._n(_ctx(s)), 1)

    def test_kleine_zahlen_loesen_keinen_fehlalarm_aus(self):
        """Arsenal „Sieg-Serie 3x": 0,67^3 = 1 von 3,3 -> gerundet 3. Der erste Entwurf dieses
        Guards meldete prompt 8 gesunde Serien, weil Rate UND Ergebnis gerundet sind."""
        s = _serie(length=3, preN=9)
        s["seltenheit"] = {"basis": "eigen", "ratePct": 67, "preN": 9, "einsZu": 3,
                           "erwartet": 1000.0, "familie": 3168, "bandPct": [40, 86],
                           "einsZuBand": [2, 16], "erwartetBand": [12.0, 1500.0],
                           "urteil": "erwartbar", "grund": "…"}
        self.assertEqual(self._n(_ctx(s)), 0)
