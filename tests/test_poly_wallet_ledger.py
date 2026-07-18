"""18.07.2026 — Wallet-Ledger: Längsschnitt-Gedächtnis für Polymarket-Wallets.

Kontext: `smart_money` misst „smart" bisher als GRÖSSE (topHolderShare). Der Ledger ist die
Vorstufe zu „bewiesene Wallets statt große Wallets" — er sammelt Einstiegspreise, damit später
CLV und ROI je Wallet rechenbar sind.

Was hier scharf gestellt wird, sind die zwei Fehlerarten, die den späteren Track-Record
STILL verfälschen würden — beide fallen nicht auf, weil die Datei ja wächst:

  1. **Doppelzählung.** Der Fetcher liefert dieselben jüngsten Trades in JEDEM Lauf erneut
     (alle 2h). Ohne Dedup wäre eine Wallet nach einer Woche mit 84 identischen Trades im
     Ledger — ihr Track-Record wäre reine Fiktion.
  2. **Rückwirkende Schönfärbung.** Kauft eine Wallet nach, sinkt ihr Durchschnittspreis.
     Würden wir `avgPrice` als CLV-Referenz nehmen, sähe jede nachkaufende Wallet besser aus
     als sie war. Deshalb friert `firstAvgPrice` den ERSTEN gesehenen Einstieg ein.
"""
import json

import pytest

import build_poly_wallet_ledger as L


def _trade(**over):
    t = {"wallet": "0xaaa", "key": "FRA-ENG", "match": "Frankreich – England",
         "side": "home", "pick": "Frankreich Sieg", "usd": 27601.0, "price": 0.76,
         "action": "BUY", "ts": "2026-07-18T13:07:12+00:00"}
    t.update(over)
    return t


def _position(**over):
    p = {"wallet": "0xbbb", "key": "FRA-ENG", "match": "Frankreich – England",
         "side": "home", "pick": "Frankreich Sieg", "usd": 257500.0, "shares": 500000.0}
    p.update(over)
    return p


def _snap(trades=None, positions=None):
    return {"bigTradesAll": trades or [], "topPositionsAll": positions or []}


class TestDedupTrades:
    def test_derselbe_trade_wird_nicht_doppelt_gezaehlt(self):
        snap = _snap(trades=[_trade()])
        led, s1 = L.collect(snap, {})
        assert s1["tradesNew"] == 1
        led, s2 = L.collect(snap, led)          # Fetcher liefert ihn erneut
        assert s2["tradesNew"] == 0 and s2["tradesDup"] == 1
        assert len(led["trades"]) == 1, "Trade dupliziert → Wallet-Statistik wäre Fiktion"

    def test_zwoelf_laeufe_lassen_den_bestand_stabil(self):
        """Der reale Takt: alle 2h derselbe Snapshot, bis das Spiel läuft."""
        snap = _snap(trades=[_trade(), _trade(ts="2026-07-18T14:00:00+00:00")])
        led = {}
        for _ in range(12):
            led, _s = L.collect(snap, led)
        assert len(led["trades"]) == 2

    def test_gleiche_wallet_anderer_zeitpunkt_ist_ein_neuer_trade(self):
        led, _ = L.collect(_snap(trades=[_trade()]), {})
        led, s = L.collect(_snap(trades=[_trade(ts="2026-07-18T15:00:00+00:00")]), led)
        assert s["tradesNew"] == 1 and len(led["trades"]) == 2


class TestEinstiegspreisWirdNichtGeschoent:
    def test_first_avg_price_bleibt_beim_ersten_einstieg(self):
        # Erst 500k Shares für 257.5k → 0.515. Dann Nachkauf, Schnitt fällt auf 0.40.
        led, _ = L.collect(_snap(positions=[_position()]), {})
        led, _ = L.collect(_snap(positions=[_position(usd=400000.0, shares=1000000.0)]), led)
        pos = led["positions"]["0xbbb|FRA-ENG|home"]
        assert pos["firstAvgPrice"] == pytest.approx(0.515), \
            "erster Einstieg überschrieben → Nachkäufer sähen künstlich gut aus"
        assert pos["avgPrice"] == pytest.approx(0.40), "aktueller Schnitt wird nicht fortgeschrieben"

    def test_position_wird_fortgeschrieben_nicht_dupliziert(self):
        led, _ = L.collect(_snap(positions=[_position()]), {})
        led, s = L.collect(_snap(positions=[_position(usd=300000.0)]), led)
        assert len(led["positions"]) == 1 and s["positionsUpdated"] == 1
        assert led["positions"]["0xbbb|FRA-ENG|home"]["usd"] == pytest.approx(300000.0)

    def test_first_seen_bleibt_stehen(self):
        led, _ = L.collect(_snap(positions=[_position()]), {}, now="2026-07-18T10:00:00+00:00")
        led, _ = L.collect(_snap(positions=[_position()]), led, now="2026-07-19T10:00:00+00:00")
        pos = led["positions"]["0xbbb|FRA-ENG|home"]
        assert pos["firstSeen"].startswith("2026-07-18")
        assert pos["lastSeen"].startswith("2026-07-19")


class TestMuellFliegtRaus:
    """Ein Trade ohne belastbaren Preis ist als CLV-Beobachtung wertlos — er darf nicht rein,
    sonst verwässert er still den Track-Record aller Wallets."""

    @pytest.mark.parametrize("bad", [
        {"price": None}, {"price": 0}, {"price": 1.0}, {"price": 1.4},
        {"ts": None}, {"wallet": None}, {"key": None}, {"usd": 10.0},
    ])
    def test_unbrauchbarer_trade_wird_verworfen(self, bad):
        led, s = L.collect(_snap(trades=[_trade(**bad)]), {})
        assert s["tradesNew"] == 0 and s["tradesBad"] == 1
        assert led["trades"] == []

    def test_position_ohne_shares_hat_keinen_einstiegspreis(self):
        """usd/shares IST der Einstiegspreis. Ohne shares raten wir nicht."""
        led, s = L.collect(_snap(positions=[_position(shares=0)]), {})
        assert s["positionsBad"] == 1 and led["positions"] == {}

    def test_kleinvieh_bleibt_draussen(self):
        led, s = L.collect(_snap(positions=[_position(usd=100.0, shares=200.0)]), {})
        assert s["positionsBad"] == 1, "Rauschen bläht den Ledger und verzerrt die Konzentration"


class TestDatensatzTrennung:
    def test_jeder_datensatz_hat_seinen_eigenen_ledger(self, monkeypatch):
        monkeypatch.setenv("COCOBET_DATASET", "wm")
        import importlib
        import cocobet_dataset
        importlib.reload(cocobet_dataset)
        importlib.reload(L)
        assert L.ledger_path().name == "wm_poly_wallet_ledger.json"

        monkeypatch.setenv("COCOBET_DATASET", "mls")
        importlib.reload(cocobet_dataset)
        importlib.reload(L)
        assert L.ledger_path().name == "mls_poly_wallet_ledger.json", \
            "MLS schriebe in die WM-Datei — is_liga() ist auch für MLS True"
        assert L.wallets_path().name == "mls_poly_wallets.json"


class TestSammlungLaeuftUeberall:
    """Der Ledger nützt nur, wenn er direkt nach JEDEM Smartmoney-Fetch läuft — der Snapshot
    ist flüchtig. Ein vergessener Workflow ist eine stille Datenlücke."""

    def _wf(self, name):
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / ".github" / "workflows" / name).read_text("utf-8")

    @pytest.mark.parametrize("wf", ["update-mls.yml", "fetch-wm-data.yml", "fetch-mls-odds-dense.yml"])
    def test_ledger_step_vorhanden(self, wf):
        src = self._wf(wf)
        assert "fetch_wm_poly_smartmoney.py" in src, "Testannahme veraltet: kein Smartmoney-Fetch mehr"
        assert "build_poly_wallet_ledger.py" in src, \
            f"{wf} holt Wallet-Daten, schreibt sie aber nicht weg → Beobachtungen gehen verloren"

    @pytest.mark.parametrize("wf,datei", [
        ("update-mls.yml", "mls_poly_wallet_ledger.json"),
        ("fetch-mls-odds-dense.yml", "mls_poly_wallet_ledger.json"),
    ])
    def test_ledger_wird_committet(self, wf, datei):
        assert datei in self._wf(wf), f"{wf} committet den Ledger nicht → Lauf war umsonst"

    def test_wm_ledger_in_der_registry(self):
        from pathlib import Path
        reg = json.loads((Path(__file__).resolve().parent.parent / "state_files_registry.json")
                         .read_text("utf-8"))
        files = reg["categories"]["fetch_wm_data"]["files"]
        assert "wm_poly_wallet_ledger.json" in files, \
            "fetch-wm-data holt seine git-add-Liste aus der Registry — fehlt hier, wird nie committet"
