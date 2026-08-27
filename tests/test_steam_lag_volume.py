"""26.08.2026 — „Wieso wird da nicht getradet?" (Lucas)

Drei HIGH-CONFIDENCE-Pushes für Serie-A-Spiele, kein einziger Trade. Der Grund war nicht der
Trader, sondern das Volumen: 489 $ / 749 $ / 8 $ gegen die erste Hürde `trade.min_vol_usdc`
(1.500 $). Nur SEHEN konnte man das nicht — `compute_edges` reichte `vol` nicht durch, also
stand in allen 50 geloggten Signalen `entryVol: 0` und in jedem Push „Vol: ?".

Ausgerechnet die Zahl, an der der Trader das Signal als erstes abweist, fiel auf dem Weg zum
Push runter. Fehlende Information sah aus wie keine Einschränkung.
"""
import steam_lag_monitor as M


def _poly(vol=489.0, key="497-499", hw=0.435):
    return {key: {"hw": hw, "dr": 0.285, "aw": 0.28, "slug": "sea-rom-ata-2026-09-05",
                  "date": "2026-09-05", "vol": vol, "homeName": "AS Roma",
                  "awayName": "Atalanta BC", "homeId": "497", "awayId": "499"}}


def _pinn(key="497-499", fair_hw=0.4981):
    return {key: {"fair_hw": fair_hw, "fair_dr": 0.2687, "fair_aw": 0.2332,
                  "steamLag": True, "pinnSteamMove": 4.0, "edgeTrend": "new"}}


class TestVolumeDurchgereicht:
    def test_vol_landet_im_signal(self):
        """Der eigentliche Bug: das Feld fehlte im Signal-Dict komplett."""
        sig = M.compute_edges(_poly(), _pinn())[0]
        assert sig["vol"] == 489.0

    def test_fehlendes_vol_wird_zu_null_nicht_zum_absturz(self):
        p = _poly(); p["497-499"].pop("vol")
        assert M.compute_edges(p, _pinn())[0]["vol"] == 0

    def test_edge_bleibt_unveraendert(self):
        """Die Reparatur darf die Signal-Mathematik nicht anfassen."""
        sig = M.compute_edges(_poly(), _pinn())[0]
        assert round(sig["edge_hw"], 1) == 6.3
        assert sig["steamLag"] is True and sig["pinnSteamMove"] == 4.0


class TestHandelbarkeit:
    def test_schwelle_kommt_aus_derselben_config_wie_der_trader(self):
        """Zwei getippte Zahlen driften auseinander, sobald eine angefasst wird."""
        import auto_wm_poly_trigger as T
        assert M.TRADE_MIN_VOL_USDC == T.MIN_VOL

    def test_die_drei_echten_faelle_sind_nicht_handelbar(self):
        for vol in (489.0, 749.0, 8.0):
            assert not M.tradable(vol), vol

    def test_dicker_markt_ist_handelbar(self):
        assert M.tradable(185_940.0) and M.tradable(1500)

    def test_unbekanntes_volumen_gilt_als_nicht_handelbar(self):
        """Fehlende Information ist keine Erlaubnis — 0/None/Müll darf nie durchrutschen."""
        for v in (0, None, "", "kaputt", [], {}):
            assert not M.tradable(v), repr(v)

    def test_genau_auf_der_schwelle_zaehlt_als_handelbar(self):
        assert M.tradable(M.TRADE_MIN_VOL_USDC)


class TestPushNotiz:
    def test_handelbar_erzeugt_keine_notiz(self):
        assert M.tradable_note(25_861.0) == ""

    def test_notiz_nennt_beide_zahlen(self):
        n = M.tradable_note(489.0)
        assert "489" in n and "1,500" in n and "Nicht handelbar" in n

    def test_unbekannt_sagt_unbekannt_statt_null(self):
        """„nur $0 im Markt" wäre eine Behauptung, die wir nicht belegen können."""
        n = M.tradable_note(0)
        assert "$0" not in n, "„nur $0 im Markt\" behauptet eine Messung, die es nicht gab"
        assert "bekannt" in n, "der Push soll sagen, dass das Volumen unbekannt ist"

    def test_muell_wirft_nicht(self):
        for v in ("kaputt", None, [], {}):
            assert "Nicht handelbar" in M.tradable_note(v)
