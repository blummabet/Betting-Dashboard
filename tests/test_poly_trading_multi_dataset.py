"""18.07.2026 — Poly-Trading + manuelles Betting für MLS/Liga (Lucas: „muss funktionieren wie zur WM").

ZWEI BLOCKER, beide geldrelevant:

1. AUTO-TRADING stand für MLS auf $0. Balance wurde pro Datensatz gelesen
   (`mls_poly_balance.json`) — die Datei existierte nicht, weil der self-hosted MLS-Workflow noch
   nicht lief. Der Trigger sah $0.00, kappte seinen adaptiven Daily-Cap auf 0 und brach ab, obwohl
   die Wallet real $162.88 hatte (in `wm_poly_balance.json`). Es ist DIESELBE Wallet.

   ⚠️ Kehrseite: Wenn alle Datensätze eine Wallet teilen, darf nicht jeder sein Limit auf die volle
   Balance rechnen — sonst setzen WM+Liga+MLS zusammen ein Vielfaches ein. Exposure und Tages-Stake
   werden deshalb über ALLE Datensätze summiert.

2. MANUELLES BETTING hätte MLS-Wetten als WM-Wetten platziert. Der Frontend-Dispatch sendete nur
   `{orders}`; poly-bets.yml liest `client_payload.dataset` und fällt ohne Angabe auf 'wm' zurück
   → falsche Datei, falscher P&L, falscher Lern-Loop.
"""
import json
import os

import pytest


class TestWalletBalanceGeteilt:
    def test_balance_wird_datensatz_uebergreifend_gefunden(self, tmp_path, monkeypatch):
        """MLS ohne eigene Balance-Datei muss die Wallet-Balance trotzdem sehen."""
        import auto_wm_poly_trigger as T
        (tmp_path / "wm_poly_balance.json").write_text(json.dumps(
            {"usdc": 162.88, "updatedAt": "2026-07-18T09:17:55Z"}))
        # mls_poly_balance.json existiert bewusst NICHT
        monkeypatch.setattr(T, "BASE_DIR", str(tmp_path))
        data, quelle = T._load_wallet_balance()
        assert float(data.get("usdc")) == pytest.approx(162.88), "Wallet-Balance nicht gefunden"
        assert "wm_poly_balance" in quelle

    def test_frischeste_datei_gewinnt(self, tmp_path, monkeypatch):
        import auto_wm_poly_trigger as T
        (tmp_path / "wm_poly_balance.json").write_text(json.dumps(
            {"usdc": 100.0, "updatedAt": "2026-07-18T08:00:00Z"}))
        (tmp_path / "mls_poly_balance.json").write_text(json.dumps(
            {"usdc": 55.0, "updatedAt": "2026-07-18T09:30:00Z"}))
        monkeypatch.setattr(T, "BASE_DIR", str(tmp_path))
        data, quelle = T._load_wallet_balance()
        assert float(data["usdc"]) == pytest.approx(55.0), "ältere Balance gewann"
        assert "mls_poly_balance" in quelle

    def test_ohne_jede_datei_null_statt_absturz(self, tmp_path, monkeypatch):
        import auto_wm_poly_trigger as T
        monkeypatch.setattr(T, "BASE_DIR", str(tmp_path))
        data, _ = T._load_wallet_balance()
        assert float(data.get("usdc") or 0) == 0.0


class TestLimitsGeltenGlobal:
    """Der Schutz gegen Überwetten: eine Wallet → Limits über alle Datensätze."""

    def _setup(self, tmp_path, monkeypatch):
        import auto_wm_poly_trigger as T
        (tmp_path / "wm_auto_bets_placed.json").write_text(json.dumps({"bets": [
            {"stake": 5.0, "placedAt": "2026-07-18T08:00:00Z"},                    # offen + heute
            {"stake": 7.0, "placedAt": "2026-07-17T08:00:00Z"},                    # offen, gestern
            {"stake": 9.0, "placedAt": "2026-07-18T08:00:00Z", "resolved": True},  # zu, heute
        ]}))
        (tmp_path / "liga_auto_bets_placed.json").write_text(json.dumps({"bets": [
            {"stake": 3.0, "placedAt": "2026-07-18T08:00:00Z"},
        ]}))
        monkeypatch.setattr(T, "BASE_DIR", str(tmp_path))
        monkeypatch.setattr(T, "PLACED_FILE", str(tmp_path / "mls_auto_bets_placed.json"))
        return T

    def test_fremde_offene_positionen_zaehlen(self, tmp_path, monkeypatch):
        T = self._setup(tmp_path, monkeypatch)
        offen, heute, n = T._cross_dataset_exposure("2026-07-18")
        assert offen == pytest.approx(15.0), "offene Stakes aus WM+Liga fehlen (5+7+3)"
        assert heute == pytest.approx(17.0), "heutige Stakes fehlen (5+9+3)"
        assert n == 3

    def test_eigener_datensatz_wird_nicht_doppelt_gezaehlt(self, tmp_path, monkeypatch):
        T = self._setup(tmp_path, monkeypatch)
        (tmp_path / "mls_auto_bets_placed.json").write_text(json.dumps({"bets": [
            {"stake": 99.0, "placedAt": "2026-07-18T08:00:00Z"}]}))
        offen, _heute, _n = T._cross_dataset_exposure("2026-07-18")
        assert offen == pytest.approx(15.0), "eigener Datensatz doppelt gezählt"


class TestManuellesBettingTrifftDenRichtigenDatensatz:
    """polymarket-tab.js: der Dispatch MUSS dataset+profile mitsenden."""

    def _js(self):
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / "polymarket-tab.js").read_text("utf-8")

    def test_dispatch_sendet_dataset_und_profile(self):
        src = self._js()
        assert "client_payload: { orders: grp.orders, dataset, profile: grp.profile }" in src, \
            "Dispatch sendet den Datensatz nicht → poly-bets.yml fällt auf 'wm' zurück"

    def test_gemischter_batch_wird_gruppiert(self):
        """MLS + Liga in einem Klick dürfen nicht in EINEN Lauf — sonst falsche Datei."""
        src = self._js()
        assert "const gruppen = {}" in src and "for (const [dataset, grp] of Object.entries(gruppen))" in src

    def test_liga_codes_vollstaendig(self):
        src = self._js()
        for code in ("ENG", "ESP", "GER", "ITA", "FRA"):
            assert code in src, f"Liga-Code {code} fehlt in der Datensatz-Zuordnung"


class TestGammaPaginierung:
    """18.07.2026 — der falsche Spieltag kam an.

    `order=startDate` sortiert nach ERSTELLUNG des Marktes, nicht nach Anpfiff, und die Gamma-API
    deckelt bei 100 Events (limit=300 wird ignoriert). Wir bekamen nur die zuletzt angelegten
    Märkte (Spieltag 25./26.07.) — die Spiele am 22./23.07., die einzigen mit Pinnacle-Quoten,
    fielen hinten raus. Ergebnis: 0 Überschneidung Poly↔Pinnacle → keine Edge → nie ein Kandidat.
    """

    def test_holt_alle_seiten(self):
        import fetch_wm_poly_prices as F
        seiten = {0: [{"id": i} for i in range(100)],
                  100: [{"id": 100 + i} for i in range(35)]}

        def fake(url):
            import re
            off = int(re.search(r"offset=(\d+)", url).group(1))
            return seiten.get(off, [])

        assert len(F.fetch_gamma_all(fetch=fake)) == 135, "Folgeseiten werden nicht geholt"

    def test_stoppt_bei_kurzer_seite(self):
        import fetch_wm_poly_prices as F
        rufe = []

        def fake(url):
            rufe.append(url)
            return [{"id": 1}]          # kurze Seite → sofort Schluss

        F.fetch_gamma_all(fetch=fake)
        assert len(rufe) == 1, "läuft weiter, obwohl die Seite kurz war (Quota-Verschwendung)"

    def test_duplikate_werden_entfernt(self):
        import fetch_wm_poly_prices as F
        assert len(F.fetch_gamma_all(fetch=lambda u: [{"id": 7}, {"id": 7}])) == 1

    def test_url_enthaelt_offset(self):
        import fetch_wm_poly_prices as F
        assert "offset=" in F.GAMMA_URL_TMPL
