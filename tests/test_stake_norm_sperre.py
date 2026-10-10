"""10.10.2026 (Übersicht-Check): „Buse I / Vallejo D - Andreozzi G / Guinard M · ATP Shanghai,
China Men Doubles · $70.6K … ×28.2" stand oben in „Stake · über der Norm" — zwei Tage nachdem
ATP/WTA aus der Übersicht genommen war (08.10.). Im Artefakt standen 6 von 51 `auffaellige`
aus ATP/WTA-Ligen.

Die Liga-Sperre lebte nur im Frontend-Filter `_mdStakeWetten`; die Norm-Kachel liest
`stakeAus.auffaellige` aus stake_analyse, und dessen `_erlaubt` kannte nur die Sportarten.
Fehlerklasse: eine Sperre, die je Kachel nachgebaut wird, statt beim Produzenten zu gelten.
"""
import stake_analyse as SA
import stake_highroller_fetch as SH
import uebersicht_integrity as U

ATP = {"kat": "Tennis", "liga": "ATP Shanghai, China Men Doubles",
       "event": "Buse I / Vallejo D - Andreozzi G / Guinard M", "einsatzUsd": 70610.81}
WTA = {"kat": "Tennis", "liga": "WTA 125K Suzhou, China Women Doubles", "event": "x"}
ITF = {"kat": "Tennis", "liga": "ITF W35 Wagga Wagga", "event": "Wan - Sibai"}
FUSS = {"kat": "Fußball", "liga": "Botola", "event": "Maghreb Fes - Raja"}


class TestEineSperre:
    def test_atp_und_wta_sind_im_produzenten_gesperrt(self):
        # Auf dem alten Code war _erlaubt(ATP) True — so kam die Zeile in `auffaellige`.
        assert not SA._erlaubt(ATP)
        assert not SA._erlaubt(WTA)

    def test_itf_und_fussball_bleiben(self):
        assert SA._erlaubt(ITF) and SA._erlaubt(FUSS)
        assert SH.sperr_grund(ITF) is None

    def test_kategorie_sperre_gilt_weiter(self):
        assert SH.sperr_grund({"kat": "US-Sport", "liga": "MLB"}) == "US-Sport"


class TestGuard:
    def test_faengt_den_fall_vom_board(self):
        c = U.check_stake_norm_kachel_ohne_gesperrte({"stakeAus": {"auffaellige": [ATP, FUSS, ITF]}})
        assert c["nFail"] == 1 and "ATP Shanghai" in c["failures"][0]
        assert c["severity"] == "error"

    def test_sauber_ohne_gesperrte(self):
        c = U.check_stake_norm_kachel_ohne_gesperrte({"stakeAus": {"auffaellige": [FUSS, ITF]}})
        assert c["ok"]

    def test_steht_in_der_batterie(self):
        assert U.check_stake_norm_kachel_ohne_gesperrte in U.UEBERSICHT_CHECKS
