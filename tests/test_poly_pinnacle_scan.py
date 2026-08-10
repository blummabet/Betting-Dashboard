# tests/test_poly_pinnacle_scan.py — 07.08.2026 (Lucas): das Fundament fuer Wallet-vs-Pinnacle-CLV
# UND den Lag-Backtest. Der Scanner MUSS (a) den Poly-Slug je Spiel speichern (exakter Join-Key zum
# Wallet-Ledger) und (b) den Pinnacle/Poly-Closing (letzter Snap vor Anpfiff) je Slug dauerhaft
# einfrieren, BEVOR das Spiel gepruned wird — sonst geht die Sharp-Schlusslinie nach 6h verloren.
import importlib
from datetime import datetime, timezone, timedelta

ps = importlib.import_module("poly_pinnacle_scan")
NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat()


def _row(slug, ko, ts, pinn, poly=None):
    return {"league": "MLS", "home": "A", "away": "B", "kickoff": iso(ko), "slug": slug,
            "snap": {"ts": iso(ts), "pinn": pinn, "poly": poly or [0.5, 0.3, 0.2],
                     "vol": 100, "book": "pinnacle"}}


def test_merge_store_speichert_slug():
    rows = {"MLS|A|B|x": _row("mls-a-b", NOW + timedelta(hours=2), NOW, [0.5, 0.3, 0.2])}
    store = ps.merge_store({}, rows, NOW)
    assert store["games"]["MLS|A|B|x"]["slug"] == "mls-a-b"
    assert not store.get("closings")   # noch nicht angepfiffen -> kein Closing


def test_closing_snap_nimmt_letzten_vor_anpfiff():
    ko = NOW
    g = {"kickoff": iso(ko), "snaps": [
        {"ts": iso(ko - timedelta(hours=2)), "pinn": [0.4, 0.3, 0.3]},
        {"ts": iso(ko - timedelta(minutes=10)), "pinn": [0.55, 0.28, 0.17]},  # closing
        {"ts": iso(ko + timedelta(minutes=30)), "pinn": [0.9, 0.05, 0.05]},   # in-play -> ignorieren
    ]}
    assert ps._closing_snap(g)["pinn"] == [0.55, 0.28, 0.17]


def test_freeze_idempotent_und_ueberlebt_prune():
    slug = "mls-a-b"
    ko = NOW - timedelta(hours=1)   # schon angepfiffen
    store = ps.merge_store({}, {"MLS|A|B|x": _row(slug, ko, ko - timedelta(minutes=15),
                                                  [0.6, 0.25, 0.15])}, NOW)
    assert store["closings"][slug]["pinn"] == [0.6, 0.25, 0.15]
    assert store["closings"][slug]["league"] == "MLS"
    # idempotent: spaeterer (In-Play-)Snap darf das Closing NICHT ueberschreiben
    store = ps.merge_store(store, {"MLS|A|B|x": _row(slug, ko, NOW, [0.99, 0.005, 0.005])},
                           NOW + timedelta(minutes=30))
    assert store["closings"][slug]["pinn"] == [0.6, 0.25, 0.15]
    # Spiel wird nach PRUNE_AFTER_H entfernt, Closing bleibt bestehen
    store = ps.merge_store(store, {}, NOW + timedelta(hours=ps.PRUNE_AFTER_H + 2))
    assert "MLS|A|B|x" not in store["games"]
    assert slug in store["closings"]


def test_retention_entfernt_uralte_closings():
    slug = "old-x"
    store = {"games": {}, "closings": {slug: {
        "slug": slug, "kickoff": iso(NOW - timedelta(days=ps.CLOSINGS_KEEP_DAYS + 10)),
        "pinn": [0.5, 0.3, 0.2]}}}
    store = ps.merge_store(store, {}, NOW)
    assert slug not in store["closings"]


# ── Hygiene-Gate _snap_valid (10.08.2026, Lucas): killt Backtest-Datenmuell ───────────────────
def test_snap_valid_akzeptiert_sauberen_snapshot():
    # Poly & Pinnacle einig (Heim Favorit), Volumen da, Pinnacle-Summe ~1
    assert ps._snap_valid([0.55, 0.27, 0.18], [0.50, 0.28, 0.22], 300) is True


def test_snap_valid_verwirft_leeres_buch():
    # vol=0 → Seed-Preis, kein Markt (95% der alten Falsch-Edges)
    assert ps._snap_valid([0.55, 0.27, 0.18], [0.50, 0.28, 0.22], 0) is False
    assert ps._snap_valid([0.55, 0.27, 0.18], [0.50, 0.28, 0.22], ps.VOL_MIN) is False


def test_snap_valid_verwirft_favoriten_uneinigkeit_elche_barca():
    # Pinnacle sieht Remis/Heim vorn, Poly klar Auswaerts (Barca 76%) → Fehlmatch
    assert ps._snap_valid([0.354, 0.36, 0.286], [0.13, 0.195, 0.76], 254) is False


def test_snap_valid_verwirft_kaputtes_devig_betis():
    # Pinnacle-Favorit Auswaerts (0.431), Poly-Favorit Heim (0.47) → uneinig
    assert ps._snap_valid([0.427, 0.141, 0.431], [0.47, 0.275, 0.28], 392) is False


def test_snap_valid_verwirft_kaputte_summe():
    assert ps._snap_valid([0.6, 0.6, 0.6], [0.5, 0.3, 0.2], 300) is False


def test_snap_valid_verwirft_none_und_falsche_laenge():
    assert ps._snap_valid([0.5, None, 0.2], [0.5, 0.3, 0.2], 300) is False
    assert ps._snap_valid([0.5, 0.3], [0.5, 0.3, 0.2], 300) is False
    assert ps._snap_valid(None, [0.5, 0.3, 0.2], 300) is False


def test_scan_ueberspringt_ungueltige_paare():
    # injizierte Fetcher: ein leeres Buch (vol=0) darf KEINE Zeile erzeugen
    poly_games = [{"home": "A", "away": "B", "kickoff": iso(NOW + timedelta(hours=3)),
                   "slug": "a-b", "poly": [0.5, 0.3, 0.2], "vol": 0}]
    pinn_games = [{"home": "A", "away": "B", "commence": iso(NOW + timedelta(hours=3)),
                   "pinn": [0.55, 0.27, 0.18], "book": "pinnacle", "dec": [1.8, 3.7, 5.5]}]
    lg = {"name": "MLS", "poly": "x", "odds": "y"}
    rows, *_ = ps.scan(leagues=[lg], poly_fetch=lambda s: poly_games,
                       pinn_fetch=lambda s: pinn_games, now=NOW)
    assert rows == {}, "leeres Buch (vol=0) haette keine Zeile schreiben duerfen"
    # mit echtem Volumen entsteht eine Zeile
    poly_games[0]["vol"] = 300
    rows2, *_ = ps.scan(leagues=[lg], poly_fetch=lambda s: poly_games,
                        pinn_fetch=lambda s: pinn_games, now=NOW)
    assert len(rows2) == 1
