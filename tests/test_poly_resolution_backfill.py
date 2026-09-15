# tests/test_poly_resolution_backfill.py — 02.08.2026 (Lucas): der Settlement-Key-Fix an der Wurzel.
# Getrackte, verschwundene Märkte werden per EIGENEM Slug aufgelöst → Auflösung unter DEMSELBEN Key.
import json, unittest
import poly_money_broad as P


def _ev(outcomes, prices):
    """Gamma-Event mit einem Moneyline-Markt (outcomes/outcomePrices als JSON-Strings, wie die echte API)."""
    return {"markets": [{
        "outcomes": json.dumps(outcomes),
        "outcomePrices": json.dumps([str(p) for p in prices]),
        "clobTokenIds": json.dumps([f"t{i}" for i in range(len(outcomes))]),
        "conditionId": "cond1",
    }]}


class TestBackfill(unittest.TestCase):
    def _get_factory(self, resolved_slugs):
        # resolved_slugs: {slug: (outcomes, prices)}
        def _get(url):
            slug = url.split("slug=")[1].split("&")[0]
            if slug in resolved_slugs:
                return [_ev(*resolved_slugs[slug])]
            return []
        return _get

    def test_vanished_resolved_market_backfilled_under_same_key(self):
        prev = {"lol-kt-hle1-2026-08-02": {"prices": {"Hanwha Life Esports": 0.7}}}  # war offen
        seen = set()                                                                  # taucht NICHT mehr auf
        get = self._get_factory({"lol-kt-hle1-2026-08-02": (["Hanwha Life Esports", "KT Rolster"], [1.0, 0.0])})
        out = P.backfill_resolutions_by_slug(prev, seen, get=get)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["key"], "lol-kt-hle1-2026-08-02")   # SELBER Key wie die offene Position
        self.assertTrue(out[0]["resolved"])
        self.assertEqual(P.winner_from_prices(out[0]["resolvedPrices"]), "Hanwha Life Esports")

    def test_still_open_market_not_looked_up(self):
        prev = {"lol-x-y-2026-08-02": {"prices": {}}}
        seen = {"lol-x-y-2026-08-02"}                     # noch offen im aktuellen Lauf
        get = self._get_factory({"lol-x-y-2026-08-02": (["X", "Y"], [1.0, 0.0])})
        self.assertEqual(P.backfill_resolutions_by_slug(prev, seen, get=get), [])

    def test_already_resolved_in_prev_skipped(self):
        prev = {"k": {"resolved": True}}
        self.assertEqual(P.backfill_resolutions_by_slug(prev, set(), get=lambda u: []), [])

    def test_not_yet_resolved_not_included(self):
        prev = {"k-2026-08-02": {"prices": {}}}
        get = self._get_factory({"k-2026-08-02": (["A", "B"], [0.55, 0.45])})   # kein ~1.0 → nicht aufgelöst
        self.assertEqual(P.backfill_resolutions_by_slug(prev, set(), get=get), [])

    def test_cap_respected(self):
        prev = {f"k{i}-2026-08-02": {"prices": {}} for i in range(10)}
        get = self._get_factory({f"k{i}-2026-08-02": (["A", "B"], [1.0, 0.0]) for i in range(10)})
        out = P.backfill_resolutions_by_slug(prev, set(), get=get, cap=3)
        self.assertEqual(len(out), 3)

    def test_defensive_on_get_error(self):
        def boom(url): raise RuntimeError("net down")
        self.assertEqual(P.backfill_resolutions_by_slug({"k-1": {"prices": {}}}, set(), get=boom), [])



class TestNachzuegler(unittest.TestCase):
    """🔴 15.09.2026 (Lucas: „wieso steht BIG noch nicht als beendet"). Der Backfill iterierte nur
    ueber prev_close. Der Broad-Scan friert aber nur Maerkte ueber MIN_VOL_USD ein — ein Play, den
    nur der Shortlist-Emitter kennt, stand dort nie und wurde deshalb NIE nachgeschlagen."""

    def _get_factory(self, resolved_slugs):
        def _get(url):
            slug = url.split("slug=")[1].split("&")[0]
            if slug in resolved_slugs:
                return [_ev(*resolved_slugs[slug])]
            return []
        return _get

    def test_key_ausserhalb_des_close_files_wird_nachgeschlagen(self):
        # PROVOKATION: genau dieser Aufruf lieferte vorher [] — lol-gx-navi-2026-09-11 verfiel am
        # 13.09. als „nicht getrackt", waehrend Gamma ihn voll aufgeloest auslieferte.
        get = self._get_factory({"lol-gx-navi-2026-09-11": (["Natus Vincere", "GIANTX"], [1.0, 0.0])})
        out = P.backfill_resolutions_by_slug({}, set(), get=get,
                                             extra=[{"key": "lol-gx-navi-2026-09-11", "cond": None}])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["key"], "lol-gx-navi-2026-09-11")
        self.assertEqual(P.winner_from_prices(out[0]["resolvedPrices"]), "Natus Vincere")

    def test_nachzuegler_ohne_extra_bleibt_unsichtbar(self):
        # Der Gegenbeweis zum Test darueber: ohne `extra` passiert genau nichts.
        get = self._get_factory({"lol-gx-navi-2026-09-11": (["Natus Vincere", "GIANTX"], [1.0, 0.0])})
        self.assertEqual(P.backfill_resolutions_by_slug({}, set(), get=get), [])

    def test_nachzuegler_wird_nicht_doppelt_abgefragt(self):
        log = []
        def get(url):
            log.append(url)
            return []
        P.backfill_resolutions_by_slug({"k-2026-09-01": {"prices": {}}}, set(), get=get,
                                       extra=[{"key": "k-2026-09-01"}, {"key": "k-2026-09-01"}])
        self.assertEqual(len(log), 1)

    def test_im_aktuellen_lauf_offener_nachzuegler_wird_uebersprungen(self):
        log = []
        def get(url):
            log.append(url)
            return []
        P.backfill_resolutions_by_slug({}, {"laeuft-noch"}, get=get, extra=[{"key": "laeuft-noch"}])
        self.assertEqual(log, [])

    def test_nachzuegler_bekommen_eigenes_budget(self):
        # PROVOKATION: haengte man `extra` nur hinten an und schnitte bei cap ab, frisst ein
        # volles Close-File das Budget auf — und ausgerechnet die Position mit echtem Geld
        # (die nie im Close-File steht) kaeme nie dran.
        prev = {f"k{i}-2026-09-01": {"prices": {}, "capturedAt": f"2026-09-0{i%9+1}"} for i in range(50)}
        log = []
        def get(url):
            log.append(url.split("slug=")[1].split("&")[0])
            return []
        P.backfill_resolutions_by_slug(prev, set(), get=get, cap=10,
                                       extra=[{"key": "echtes-geld-2026-09-14"}])
        self.assertIn("echtes-geld-2026-09-14", log)
        self.assertEqual(len(log), 10)

    def test_kaputtes_close_file_killt_die_nachzuegler_nicht(self):
        # PROVOKATION: der frueher Return bei `not isinstance(prev_close, dict)` haette die
        # Nachzuegler mit weggeworfen.
        get = self._get_factory({"k-2026-09-01": (["A", "B"], [1.0, 0.0])})
        out = P.backfill_resolutions_by_slug("kaputt", set(), get=get, extra=[{"key": "k-2026-09-01"}])
        self.assertEqual(len(out), 1)

    def test_cond_des_nachzueglers_wird_benutzt(self):
        # Ohne die cond waehlt _outcomes den Markt mit dem meisten Volumen — bei einem Buendel
        # also womoeglich eine andere Linie als beim Erfassen.
        ev = {"markets": [
            {"outcomes": json.dumps(["Over", "Under"]), "outcomePrices": json.dumps(["0.0", "1.0"]),
             "clobTokenIds": json.dumps(["t0", "t1"]), "conditionId": "falsch"},
            {"outcomes": json.dumps(["Over", "Under"]), "outcomePrices": json.dumps(["1.0", "0.0"]),
             "clobTokenIds": json.dumps(["t2", "t3"]), "conditionId": "richtig"}]}
        out = P.backfill_resolutions_by_slug({}, set(), get=lambda u: [ev],
                                             extra=[{"key": "x-2026-09-01", "cond": "richtig"}])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["cond"], "richtig")
        self.assertEqual(P.winner_from_prices(out[0]["resolvedPrices"]), "Over")


class TestVerdrahtung(unittest.TestCase):
    """⭐ Die Gegenprobe an der NAHTSTELLE, nicht am Baustein. Ohne sie ueberlebt die Mutation
    „der Aufruf reicht `extra` nicht durch": alle Bausteine gruen, und der Nachschlag fragt
    trotzdem wieder nur das Close-File ab — also genau der Zustand vom 14.09."""

    def test_backfill_lauf_holt_sich_die_nachzuegler(self):
        import unittest.mock as _m
        gesehen = {}
        def _bf(prev_close, seen, get=None, cap=None, extra=None):
            gesehen["extra"] = extra
            return []
        with _m.patch.object(P, "nachschlag_kandidaten",
                             lambda base_dir=None: [{"key": "offen-2026-09-14", "cond": "0x1"}]), \
             _m.patch.object(P, "backfill_resolutions_by_slug", _bf):
            P.backfill_lauf(set(), close={})
        self.assertEqual([e["key"] for e in gesehen["extra"]], ["offen-2026-09-14"])

    def test_backfill_lauf_nutzt_die_gepatchte_http_schicht(self):
        # `get=_get` als Default-Argument waere zur Definitionszeit gebunden — dann liefe der
        # Lauf im Test (und nur dort unbemerkt) gegen das echte Netz.
        import unittest.mock as _m
        gerufen = []
        with _m.patch.object(P, "_get", lambda url: gerufen.append(url) or []):
            P.backfill_lauf(set(), close={"k-2026-09-01": {"prices": {}}}, extra=[])
        self.assertTrue(gerufen)

    def test_kandidaten_sammler_wirft_nie(self):
        import unittest.mock as _m
        with _m.patch.dict("sys.modules", {"poly_clob_aufloesung": None}):
            self.assertEqual(P.nachschlag_kandidaten("/gibt/es/nicht"), [])


if __name__ == "__main__":
    unittest.main()
