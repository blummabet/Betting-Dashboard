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


if __name__ == "__main__":
    unittest.main()
