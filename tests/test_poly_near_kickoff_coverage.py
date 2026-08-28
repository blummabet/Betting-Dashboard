"""28.08.2026 — Lucas: „Polymarket Betting / wieso ist das von heute Bayern - Stuttgart nicht
aufgelistet? da muss ja auch was falsch sein."

Beweis aus der Git-Historie von liga_poly_prices.json:
    23.08. 21:49 UTC → 75 Fixtures, Spanne 24.08.–05.09.  (bun-bay-stu-2026-08-28, Vol 6.501 $)
    24.08. 07:58 UTC → 73 Fixtures, Spanne 29.08.–06.09.
In EINEM Lauf fielen 14 Spiele raus — alle sechs vom 28.08. und vier Serie A vom 29.08. — und 12
Events vom 06.09. kamen dazu, 11 davon mit Volumen 0. Rausgeflogen ist immer das anpfiff-nächste
Ende. Das ist die Signatur „harte Obergrenze + ascending=false".

Folge weit über ein fehlendes Spiel hinaus: Steam-Lag-Signale betrafen nur Spiele 6–13 Tage vor
Anpfiff, und es gab nie eine ≥4pp-Divergenz Poly↔Pinnacle innerhalb von 2 Tagen vor Kickoff —
nicht weil es keine Edge gab, sondern weil die spielnahen Märkte nie in den Daten waren.

Diese Tests halten die drei Gegenmaßnahmen fest:
  1. je Serie ein eigener paginierter Lauf (keine Liga hungert eine andere aus)
  2. ascending=true — eine Kappung schneidet am FERNEN Ende ab, plus Nachhol-Lauf fürs ferne Ende
  3. Slug-Gedächtnis + Rescue + Abdeckungs-Alarm für Anpfiff < 48h
"""
import os
import re
import sys
import json
import pytest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_wm_poly_prices as F


def _off(url):
    return int(re.search(r"offset=(\d+)", url).group(1))


def _flt(url):
    m = re.search(r"[?&](series_id=\d+|series_slug=[^&]+|tag_slug=[^&]+)", url)
    return m.group(1) if m else None


class TestSortierung:
    def test_naechster_anpfiff_zuerst(self):
        """ascending=true ist der ganze Punkt: kappt es, dann am fernen Ende."""
        assert "ascending=true" in F.gamma_url()
        assert "ascending=false" not in F.gamma_url()

    def test_ferne_richtung_bleibt_moeglich(self):
        """Der 01.07.-Fall (KO-Events fielen ab) war spiegelverkehrt — die Richtung muss
        weiterhin umschaltbar sein, sonst ist der Nachhol-Lauf nicht baubar."""
        assert "ascending=false" in F.gamma_url(ascending=False)

    def test_gamma_url_tmpl_bleibt_formatierbar(self):
        """Alt-Tests/Logging formatieren GAMMA_URL_TMPL nur mit limit+offset."""
        assert "offset=" in F.GAMMA_URL_TMPL
        assert "{flt}" not in F.GAMMA_URL_TMPL and "{asc}" not in F.GAMMA_URL_TMPL
        F.GAMMA_URL_TMPL.format(limit=100, offset=0)


class TestSerienGetrennt:
    def _fake(self, pro_serie):
        rufe = []

        def fake(url):
            rufe.append(url)
            return list(pro_serie.get(_flt(url), []))

        return fake, rufe

    def test_jede_serie_bekommt_eigenen_lauf(self, monkeypatch):
        monkeypatch.setattr(F, "GAMMA_SERIES_FILTERS",
                            ["series_id=1", "series_id=2", "series_id=3"])
        fake, rufe = self._fake({"series_id=1": [{"id": "a"}],
                                 "series_id=2": [{"id": "b"}],
                                 "series_id=3": [{"id": "c"}]})
        events = F.fetch_gamma_events(fetch=fake)
        assert {e["id"] for e in events} == {"a", "b", "c"}
        assert {_flt(u) for u in rufe} == {"series_id=1", "series_id=2", "series_id=3"}

    def test_volle_serie_hungert_die_anderen_nicht_aus(self, monkeypatch):
        """Der eigentliche Bug: EIN gemergter Request, eine Liga füllt den Deckel.

        Serie 1 liefert 100 Events (Deckel), Serie 2 nur eins — das eine MUSS ankommen.
        """
        monkeypatch.setattr(F, "GAMMA_SERIES_FILTERS", ["series_id=1", "series_id=2"])
        gross = [{"id": f"g{i}"} for i in range(F.GAMMA_PAGE_LIMIT)]

        def fake(url):
            if _flt(url) == "series_id=1":
                return gross if _off(url) == 0 else []
            return [{"id": "klein", "slug": "bun-bay-stu-2026-08-28"}] if _off(url) == 0 else []

        events = F.fetch_gamma_events(fetch=fake)
        assert "klein" in {e["id"] for e in events}, "kleine Liga wurde ausgehungert"

    def test_duplikate_ueber_serien_hinweg_einmal(self, monkeypatch):
        monkeypatch.setattr(F, "GAMMA_SERIES_FILTERS", ["series_id=1", "series_id=2"])
        events = F.fetch_gamma_events(fetch=lambda u: [{"id": "doppelt"}])
        assert len(events) == 1

    def test_bei_deckel_wird_das_ferne_ende_nachgeholt(self, monkeypatch):
        """Wenn eine Serie das Seitenbudget ausschöpft, dürfen die fernen Spieltage nicht
        verschwinden (Regression zum 01.07.-Befund)."""
        monkeypatch.setattr(F, "GAMMA_SERIES_FILTERS", ["series_id=1"])
        monkeypatch.setattr(F, "GAMMA_MAX_PAGES", 1)
        voll = [{"id": f"nah{i}"} for i in range(F.GAMMA_PAGE_LIMIT)]

        def fake(url):
            if "ascending=false" in url:
                return [{"id": "fern"}]
            return voll

        events = F.fetch_gamma_events(fetch=fake)
        ids = {e["id"] for e in events}
        assert "fern" in ids, "ferne Spieltage fielen weg"
        assert "nah0" in ids, "nahe Spieltage fielen weg"

    def test_kein_nachhol_lauf_ohne_deckel(self, monkeypatch):
        """Der Nachhol-Lauf kostet einen Request — er darf nur bei echter Kappung laufen."""
        monkeypatch.setattr(F, "GAMMA_SERIES_FILTERS", ["series_id=1"])
        rufe = []

        def fake(url):
            rufe.append(url)
            return [{"id": "a"}]

        F.fetch_gamma_events(fetch=fake)
        assert not any("ascending=false" in u for u in rufe)


class TestSlugDatum:
    def test_basis_slug(self):
        assert F.slug_datum("bun-bay-stu-2026-08-28") == "2026-08-28"

    def test_kindmarkt_liefert_nichts(self):
        """…-more-markets darf NIE als eigenes Spiel ins Gedächtnis."""
        assert F.slug_datum("bun-bay-stu-2026-08-28-more-markets") is None
        assert F.slug_datum("bun-bay-stu-2026-08-28-exact-score") is None

    def test_muell_ist_kein_datum(self):
        for s in (None, "", "kein-datum", "bun-bay-stu-2026-8-28"):
            assert F.slug_datum(s) is None


class TestSlugGedaechtnis:
    def test_neue_slugs_kommen_dazu(self):
        memo = F.merke_slugs({}, {"157-172": {"slug": "bun-bay-stu-2026-08-28"}},
                             heute="2026-08-28")
        assert memo["157-172"] == {"slug": "bun-bay-stu-2026-08-28", "date": "2026-08-28"}

    def test_ein_lauf_ohne_das_spiel_loescht_es_nicht(self):
        """KERN: genau der kaputte Lauf, den wir heilen wollen, liefert das Spiel nicht.
        Würde „nicht gesehen → raus" gelten, löschte er die einzige Rettungsleine."""
        memo = {"157-172": {"slug": "bun-bay-stu-2026-08-28", "date": "2026-08-28"}}
        assert "157-172" in F.merke_slugs(memo, {}, heute="2026-08-28")

    def test_abgelaufene_verfallen(self):
        memo = {"alt": {"slug": "epl-a-b-2026-08-01", "date": "2026-08-01"}}
        assert F.merke_slugs(memo, {}, heute="2026-08-28") == {}

    def test_kindmarkt_wandert_nicht_ins_memo(self):
        memo = F.merke_slugs({}, {"1-2": {"slug": "bun-a-b-2026-08-28-more-markets"}},
                             heute="2026-08-28")
        assert memo == {}

    def test_kaputtes_memo_ist_kein_absturz(self):
        assert F.merke_slugs({"x": "kein dict"}, {}, heute="2026-08-28") == {}
        assert F.merke_slugs(None, None, heute="2026-08-28") == {}

    def test_laden_ohne_datei(self, tmp_path):
        assert F.lade_slug_memo(str(tmp_path / "gibtsnicht.json")) == {}

    def test_laden_bei_muell(self, tmp_path):
        p = tmp_path / "kaputt.json"
        p.write_text("{nicht json", encoding="utf-8")
        assert F.lade_slug_memo(str(p)) == {}

    def test_laden_bei_liste(self, tmp_path):
        p = tmp_path / "liste.json"
        p.write_text("[1,2,3]", encoding="utf-8")
        assert F.lade_slug_memo(str(p)) == {}


class TestRescue:
    MEMO = {
        "157-172": {"slug": "bun-bay-stu-2026-08-28", "date": "2026-08-28"},   # heute
        "79-114":  {"slug": "fl1-lil-psg-2026-08-30", "date": "2026-08-30"},   # in 2 Tagen
        "1-2":     {"slug": "epl-a-b-2026-09-20",     "date": "2026-09-20"},   # weit weg
        "3-4":     {"slug": "sea-c-d-2026-08-20",     "date": "2026-08-20"},   # vorbei
    }

    def test_heutiges_spiel_wird_gerettet(self):
        """Bayern–Stuttgart fehlte AM SPIELTAG — „heute" muss im Fenster liegen."""
        assert "bun-bay-stu-2026-08-28" in F.rescue_kandidaten(self.MEMO, set(), heute="2026-08-28")

    def test_was_im_batch_ist_wird_nicht_geholt(self):
        raus = F.rescue_kandidaten(self.MEMO, {"bun-bay-stu-2026-08-28"}, heute="2026-08-28")
        assert "bun-bay-stu-2026-08-28" not in raus

    def test_fernes_und_vergangenes_bleiben_draussen(self):
        raus = F.rescue_kandidaten(self.MEMO, set(), heute="2026-08-28")
        assert "epl-a-b-2026-09-20" not in raus
        assert "sea-c-d-2026-08-20" not in raus

    def test_nach_datum_sortiert(self):
        raus = F.rescue_kandidaten(self.MEMO, set(), heute="2026-08-28")
        assert raus == ["bun-bay-stu-2026-08-28", "fl1-lil-psg-2026-08-30"]

    def test_horizont_ist_einstellbar(self):
        assert F.rescue_kandidaten(self.MEMO, set(), heute="2026-08-28", tage=0) == \
            ["bun-bay-stu-2026-08-28"]

    def test_leeres_memo(self):
        assert F.rescue_kandidaten({}, set(), heute="2026-08-28") == []
        assert F.rescue_kandidaten(None, None, heute="2026-08-28") == []

    def test_geschlossenes_event_wird_verworfen(self):
        """Die Slug-Abfrage kennt kein closed=false — das müssen wir selbst filtern."""
        assert F.hole_event_per_slug("x", fetch=lambda u: [{"id": 1, "closed": True}]) is None
        assert F.hole_event_per_slug("x", fetch=lambda u: [{"id": 1, "active": False}]) is None

    def test_offenes_event_kommt_durch(self):
        ev = F.hole_event_per_slug("x", fetch=lambda u: [{"id": 1, "closed": False}])
        assert ev == {"id": 1, "closed": False}

    def test_fehler_im_rescue_bricht_den_lauf_nicht_ab(self):
        def kaputt(url):
            raise RuntimeError("Gamma down")
        assert F.hole_event_per_slug("x", fetch=kaputt) is None


class TestAbdeckungsAlarm:
    def _wm(self, kickoff):
        return {"groups": {"BUN": {"fixtures": [
            {"home": "157", "away": "172", "homeName": "Bayern", "awayName": "Stuttgart",
             "kickoff": kickoff},
        ]}}}

    def test_fehlendes_nahes_spiel_wird_gemeldet(self):
        jetzt = datetime(2026, 8, 28, 6, 0, tzinfo=timezone.utc)
        wm = self._wm("2026-08-28T18:30:00+00:00")
        luecken = F.fehlende_nah_fixtures(wm, {}, jetzt=jetzt)
        assert [l["key"] for l in luecken] == ["157-172"]

    def test_vorhandenes_spiel_meldet_nichts(self):
        jetzt = datetime(2026, 8, 28, 6, 0, tzinfo=timezone.utc)
        wm = self._wm("2026-08-28T18:30:00+00:00")
        assert F.fehlende_nah_fixtures(wm, {"157-172": {}}, jetzt=jetzt) == []

    def test_poly_spiegel_zaehlt_als_vorhanden(self):
        """Polymarket dreht Paarungen — 172-157 ist dasselbe Spiel, kein Loch."""
        jetzt = datetime(2026, 8, 28, 6, 0, tzinfo=timezone.utc)
        wm = self._wm("2026-08-28T18:30:00+00:00")
        assert F.fehlende_nah_fixtures(wm, {"172-157": {}}, jetzt=jetzt) == []

    def test_fernes_spiel_ist_kein_alarm(self):
        jetzt = datetime(2026, 8, 28, 6, 0, tzinfo=timezone.utc)
        assert F.fehlende_nah_fixtures(self._wm("2026-09-20T18:30:00+00:00"), {}, jetzt=jetzt) == []

    def test_vergangenes_spiel_ist_kein_alarm(self):
        jetzt = datetime(2026, 8, 28, 6, 0, tzinfo=timezone.utc)
        assert F.fehlende_nah_fixtures(self._wm("2026-08-27T18:30:00+00:00"), {}, jetzt=jetzt) == []

    def test_kaputte_daten_sind_kein_absturz(self):
        jetzt = datetime(2026, 8, 28, 6, 0, tzinfo=timezone.utc)
        assert F.fehlende_nah_fixtures(None, {}, jetzt=jetzt) == []
        assert F.fehlende_nah_fixtures({"groups": {"X": {"fixtures": [
            {"home": "1", "away": "2"},                       # kein kickoff
            {"home": "3", "away": "4", "kickoff": "kaputt"},   # unparsebar
        ]}}}, {}, jetzt=jetzt) == []

    def test_ko_fixtures_werden_mitgeprueft(self):
        jetzt = datetime(2026, 8, 28, 6, 0, tzinfo=timezone.utc)
        wm = {"groups": {}, "koFixtures": [
            {"home": "9", "away": "8", "kickoff": "2026-08-28T20:00:00+00:00"}]}
        assert [l["key"] for l in F.fehlende_nah_fixtures(wm, {}, jetzt=jetzt)] == ["9-8"]


class TestWorkflowCommittetDasGedaechtnis:
    """Ein Gedächtnis, das den Runner nie verlässt, ist keins (Audit-Befund 07, 25.08.)."""

    def _yml(self, name):
        pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            ".github", "workflows", name)
        with open(pfad, encoding="utf-8") as f:
            return f.read()

    def test_update_liga_committet(self):
        assert "git add liga_poly_slugs.json" in self._yml("update-liga.yml")

    def test_manage_liga_poly_committet(self):
        assert "liga_poly_slugs.json" in self._yml("manage-liga-poly.yml")

    def test_wm_registry_kennt_die_datei(self):
        pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "state_files_registry.json")
        with open(pfad, encoding="utf-8") as f:
            assert "wm_poly_slugs.json" in f.read()
