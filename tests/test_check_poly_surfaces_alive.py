"""20.07.2026 — Guard gegen tote Poly-Flächen. Der Kern unterscheidet frisch-aber-leer (gesund)
von gestanden/nie-erzeugt (krank). Genau diese Unterscheidung fehlte, als Cross-Sport + E-Sport
seit Bau tot dalagen, ohne dass jemand hinsah."""
from datetime import datetime, timedelta, timezone

import check_poly_surfaces_alive as PSA


NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


def _iso(h_ago):
    return (NOW - timedelta(hours=h_ago)).isoformat()


class TestEvaluate:
    def test_alle_frisch_ist_gesund(self):
        surf = [{"name": "Cross-Sport", "ts": _iso(2)},
                {"name": "E-Sport", "ts": _iso(1)},
                {"name": "Geld breit", "ts": _iso(5)}]
        assert PSA.evaluate(surf, now=NOW) == []

    def test_frisch_aber_leer_ist_trotzdem_gesund(self):
        # Der Zeitstempel ist frisch — dass die Fläche INHALTLICH leer ist (Poly geoblockt), ist ok.
        # Der Guard prüft „hat der Produzent geschrieben", nicht „hat Inhalt".
        assert PSA.evaluate([{"name": "E-Sport", "ts": _iso(3)}], now=NOW) == []

    def test_nie_erzeugt_ist_krank(self):
        probs = PSA.evaluate([{"name": "Cross-Sport", "ts": None}], now=NOW)
        assert len(probs) == 1 and "nie erzeugt" in probs[0]

    def test_gestanden_ist_krank(self):
        probs = PSA.evaluate([{"name": "Cross-Sport", "ts": _iso(48)}], now=NOW, stale_hours=30)
        assert len(probs) == 1 and "steht" in probs[0]

    def test_genau_an_der_schwelle_noch_ok(self):
        assert PSA.evaluate([{"name": "x", "ts": _iso(29)}], now=NOW, stale_hours=30) == []

    def test_unparsebarer_zeitstempel_meldet(self):
        probs = PSA.evaluate([{"name": "x", "ts": "gestern"}], now=NOW)
        assert probs and "nicht parsebar" in probs[0]

    def test_mischung_meldet_nur_die_kranken(self):
        surf = [{"name": "frisch", "ts": _iso(1)},
                {"name": "tot", "ts": None},
                {"name": "alt", "ts": _iso(40)}]
        probs = PSA.evaluate(surf, now=NOW, stale_hours=30)
        assert len(probs) == 2
        assert not any("frisch" in p for p in probs)


class TestSurfacesKonfig:
    def test_drei_flaechen_registriert(self):
        namen = [s[0] for s in PSA.SURFACES]
        assert "Cross-Sport-Radar" in namen and "E-Sport" in namen and "Poly-Geld breit" in namen

    def test_collect_gibt_name_ts_paare(self):
        rows = PSA.collect()
        assert all("name" in r and "ts" in r for r in rows)
        assert len(rows) == len(PSA.SURFACES)
