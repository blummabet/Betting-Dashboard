"""26.08.2026 — „Wir traden mit 5 $, bei 489 $ im Markt sollte das doch reingehen?" (Lucas)

Der Auto-Trader lehnt Steam-Lag-Signale am Volumen ab und kommt deshalb nie bis zum Orderbuch.
`vol` ist aber Gammas `event.volume` — kumulierter Umsatz über die Lebensdauer, NICHT die Tiefe,
die gerade im Buch liegt. Ob 5 $ füllen, weiß bisher niemand.

Die Sonde misst genau das. Sie darf dabei NIE etwas kaufen.
"""
import poly_book_probe as P


def _fx(key="497-499", vol=489.0, steam=True, edge_hw=6.3, edge_aw=-4.7, **kw):
    f = {"key": key, "slug": "sea-rom-ata-2026-09-05", "steamLag": steam, "vol": vol,
         "homeName": "AS Roma", "awayName": "Atalanta BC", "date": "2026-09-05",
         "edge_hw": edge_hw, "edge_dr": -1.6, "edge_aw": edge_aw,
         "fair_hw": 0.4981, "poly_hw": 0.435}
    f.update(kw)
    return f


class TestOffeneSignale:
    """Auslöser ist das LOG, nicht das flüchtige Flag im Preis-File."""

    LOG = {"signals": [
        {"matchKey": "497-499", "status": "OPEN"},
        {"matchKey": "111-222", "status": "CONVERGED"},
        {"matchKey": "333-444", "status": "RESOLVED"},
        {"matchKey": "", "status": "OPEN"},
        None, "kaputt",
    ]}

    def test_nur_offene_signale(self):
        assert P.open_steam_keys(self.LOG) == {"497-499"}

    def test_leeres_log(self):
        for bad in (None, {}, {"signals": None}, {"signals": []}):
            assert P.open_steam_keys(bad) == set()

    def test_log_ist_der_ausloeser_wenn_das_flag_schon_weg_ist(self):
        """Gemessen am Bau-Tag: steamLag stand auf 0 von 62 Spielen, im Log lagen 18 offene
        Signale. Ohne diesen Pfad haette die Sonde nie etwas gemessen."""
        c = P.candidates([_fx(steam=False)], min_vol=1500, stake=5.5, steam_keys={"497-499"})
        assert len(c) == 1

    def test_fremder_key_loest_nicht_aus(self):
        assert P.candidates([_fx(steam=False)], min_vol=1500, stake=5.5, steam_keys={"999-888"}) == []


class TestKandidaten:
    def test_genau_die_luecke_wird_gemessen(self):
        """Steam-Lag liegt an, Volumen unter der Trader-Hürde → der Trader schaut nie hin."""
        c = P.candidates([_fx()], min_vol=1500, stake=5.5)
        assert len(c) == 1 and c[0]["market"] == "hw" and c[0]["edgePp"] == 6.3

    def test_handelbare_spiele_braucht_die_sonde_nicht(self):
        """Über der Hürde prüft der Trader das Buch ohnehin selbst."""
        assert P.candidates([_fx(vol=25_861.0)], min_vol=1500, stake=5.5) == []

    def test_ohne_steam_lag_kein_kandidat(self):
        assert P.candidates([_fx(steam=False)], min_vol=1500, stake=5.5) == []

    def test_zu_duenn_fuer_eine_frage(self):
        """Bei 8 $ im Markt braucht niemand ein Orderbuch, um 5 $ auszuschließen."""
        assert P.candidates([_fx(vol=8.0)], min_vol=1500, stake=5.5) == []
        assert P.candidates([_fx(vol=5.5)], min_vol=1500, stake=5.5) == []

    def test_nur_positive_edges(self):
        assert P.candidates([_fx(edge_hw=-1.0, edge_aw=-2.0)], min_vol=1500, stake=5.5) == []

    def test_staerkste_edge_zuerst_und_gedeckelt(self):
        fx = [_fx(key=str(i), edge_hw=float(i)) for i in range(1, 10)]
        c = P.candidates(fx, min_vol=1500, stake=5.5, max_n=3)
        assert [r["edgePp"] for r in c] == [9.0, 8.0, 7.0]

    def test_muell_wirft_nicht(self):
        assert P.candidates([None, "x", {}, _fx(vol="kaputt")], min_vol=1500, stake=5.5) == []
        assert P.candidates(None, min_vol=1500, stake=5.5) == []


class TestToken:
    EV = {"markets": [
        {"groupItemThreshold": "0", "clobTokenIds": '["tok-home","tok-home-no"]'},
        {"groupItemThreshold": "1", "clobTokenIds": '["tok-draw","x"]'},
        {"groupItemThreshold": "2", "clobTokenIds": ["tok-away", "y"]},
    ]}

    def test_ueber_threshold_nicht_ueber_teamnamen(self):
        assert P.token_from_event(self.EV, "hw") == "tok-home"
        assert P.token_from_event(self.EV, "dr") == "tok-draw"

    def test_liste_statt_json_string(self):
        assert P.token_from_event(self.EV, "aw") == "tok-away"

    def test_unbekannter_markt(self):
        assert P.token_from_event(self.EV, "over25") is None

    def test_kaputtes_event_gibt_none(self):
        for bad in (None, {}, "x", {"markets": [{"groupItemThreshold": "0", "clobTokenIds": "{kaputt"}]}):
            assert P.token_from_event(bad, "hw") is None


class TestBewertung:
    BOOK = {"bid": 0.42, "ask": 0.445, "mid": 0.4325, "spreadPP": 2.5, "liqUSD": 120.0}

    def test_passt_ins_top_of_book(self):
        a = P.assess(self.BOOK, 5.5, 0.4981)
        assert a["book"] is True and a["fitsTopOfBook"] is True
        assert a["askEdgePp"] == 5.31

    def test_zu_duennes_buch(self):
        a = P.assess({**self.BOOK, "liqUSD": 3.0}, 5.5, 0.4981)
        assert a["fitsTopOfBook"] is False

    def test_kein_buch_ist_keine_aussage_nicht_passt_schon(self):
        """None heißt „wir wissen es nicht" — False hieße „passt nicht"."""
        a = P.assess(None, 5.5, 0.4981)
        assert a["book"] is False and a["fitsTopOfBook"] is None

    def test_ohne_fair_keine_ask_edge(self):
        assert P.assess(self.BOOK, 5.5, None)["askEdgePp"] is None

    def test_ask_edge_ist_kleiner_als_mid_edge(self):
        """Genau der Punkt: gekauft wird über den Ask, nicht zum Mittelpreis."""
        a = P.assess(self.BOOK, 5.5, 0.4981)
        mid_edge = (0.4981 - self.BOOK["mid"]) * 100
        assert a["askEdgePp"] < mid_edge


class TestMergeUndBilanz:
    def _row(self, ts="2026-08-26T19:00:00+00:00", key="497-499", book=True, fits=True):
        return {"ts": ts, "key": key, "market": "hw", "book": book,
                "fitsTopOfBook": fits, "spreadPP": 2.5, "liqUSD": 120.0}

    def test_zeitreihe_bleibt_erhalten(self):
        """Anders als beim Kohärenz-Beobachter ist hier der VERLAUF das Ergebnis."""
        rows = P.merge([], [self._row(ts="2026-08-26T19:00:00+00:00"),
                            self._row(ts="2026-08-26T19:30:00+00:00")])
        assert len(rows) == 2

    def test_exakte_dublette_faellt_raus(self):
        assert len(P.merge([self._row()], [self._row()])) == 1

    def test_alte_messungen_fliegen_raus(self):
        from datetime import datetime, timezone
        alt = self._row(ts="2026-01-01T00:00:00+00:00")
        assert P.merge([alt], [], now=datetime(2026, 8, 26, tzinfo=timezone.utc)) == []

    def test_bilanz_zaehlt_nur_messungen_mit_buch(self):
        rows = [self._row(key="a"), self._row(key="b", fits=False),
                self._row(key="c", book=False, fits=None)]
        s = P.summarize(rows)
        assert s["n"] == 3 and s["mitBuch"] == 2 and s["passt"] == 1

    def test_leer(self):
        assert P.summarize([])["n"] == 0


def test_keine_order_funktion_importiert():
    """Leitplanke: die Sonde misst, sie handelt nicht. Kein Order-Pfad, kein Private Key."""
    src = open(P.__file__, encoding="utf-8").read()
    for verboten in ("place_order", "post_order", "create_order", "POLY_PRIVATE_KEY", "private_key"):
        assert verboten not in src, verboten
