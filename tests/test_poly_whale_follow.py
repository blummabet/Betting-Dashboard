# tests/test_poly_whale_follow.py — 24.08.2026 (Lucas): Papier-Depot fürs Nachspielen der Top-20-Whales.
# Der Kern ist NICHT „was halten die Whales", sondern: bringt Nachspielen etwas zu UNSEREM Einstiegs-
# preis? Diese Tests pinnen genau das fest — Einstieg = unser Preis, Konsens eingefroren, und `lagPP`
# als ehrliches Maß dafür, wie viel vom Move schon weg war.
import importlib
from datetime import datetime, timezone, timedelta

WF = importlib.import_module("poly_whale_follow")

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
KEY = "cs2-g1-leo2-2026-08-24"


def _emit(price=0.325, n=2, entry_avg=0.30, **kw):
    # kw reicht alles durch, was der Emitter mitgibt (conflict, againstRank, …)
    w = {"key": KEY, "side": "Leo Team", "price": price, "n": n, "bestRank": 9,
         "league": "ESPORTS", "cat": "E-Sport", "usd": 2516, "entryAvg": entry_avg, "htk": 1.7}
    w.update(kw)
    return {"whales": [w]}


def _close(price=0.325):
    return {KEY: {"prices": {"Leo Team": price, "GenOne": round(1 - price, 3)}}}


# ── Öffnen ───────────────────────────────────────────────────────────────────
def test_einstieg_ist_unser_preis_nicht_ihrer():
    # Die Whales sind bei 30¢ rein, wir sehen den Markt bei 40¢ — gewertet wird UNSER Preis.
    t = WF.update_track({}, _emit(price=0.40, entry_avg=0.30), _close(0.40), {}, now=NOW)
    e = t["open"][f"{KEY}|Leo Team"]
    assert e["entryPrice"] == 0.40 and e["whaleEntryAvg"] == 0.30


def test_konsens_wird_beim_einstieg_eingefroren():
    t = WF.update_track({}, _emit(n=2), _close(), {}, now=NOW)
    # Später liegen 5 Wallets drauf — der schon offene Play behält seine 2 (sonst wäre es Rückblick).
    t2 = WF.update_track(t, _emit(n=5), _close(), {}, now=NOW + timedelta(hours=1))
    assert t2["open"][f"{KEY}|Leo Team"]["consensusAtEntry"] == 2


def test_ohne_sauberen_preis_kein_play():
    t = WF.update_track({}, _emit(price=None), {}, {}, now=NOW)
    assert not t["open"]


def test_preis_faellt_auf_den_close_feed_zurueck():
    t = WF.update_track({}, _emit(price=None), _close(0.33), {}, now=NOW)
    assert t["open"][f"{KEY}|Leo Team"]["entryPrice"] == 0.33


def test_kein_doppeltes_oeffnen_eines_abgerechneten_plays():
    t = WF.update_track({}, _emit(), _close(), {KEY: {"winner": "Leo Team"}}, now=NOW)
    assert len(t["settled"]) == 1 and not t["open"]
    t2 = WF.update_track(t, _emit(), _close(), {}, now=NOW + timedelta(hours=1))
    assert not t2["open"] and len(t2["settled"]) == 1


# ── Abrechnen ────────────────────────────────────────────────────────────────
def test_gewinn_rechnet_wie_das_shortlist_depot():
    # $10 @ 0.50 = 20 Aktien, Gewinner zahlt 1.00 → +$10.
    t = WF.update_track({}, _emit(price=0.50), _close(0.50), {}, now=NOW)
    t2 = WF.update_track(t, {"whales": []}, _close(0.50), {KEY: {"winner": "Leo Team"}}, now=NOW)
    r = t2["settled"][0]
    assert r["result"] == "win" and r["pnl"] == 10.0


def test_verlust_kostet_den_einsatz():
    t = WF.update_track({}, _emit(price=0.50), _close(0.50), {}, now=NOW)
    t2 = WF.update_track(t, {"whales": []}, _close(0.50), {KEY: {"winner": "GenOne"}}, now=NOW)
    assert t2["settled"][0]["pnl"] == -10.0


def test_lag_misst_den_verpassten_move():
    # Whales bei 30¢, wir steigen bei 42¢ ein → 12pp des Moves sind weg, bevor wir dabei sind.
    t = WF.update_track({}, _emit(price=0.42, entry_avg=0.30), _close(0.42), {}, now=NOW)
    t2 = WF.update_track(t, {"whales": []}, _close(0.42), {KEY: {"winner": "Leo Team"}}, now=NOW)
    assert t2["settled"][0]["lagPP"] == 12.0
    assert t2["agg"]["all"]["lagAvg"] == 12.0


def test_clv_kommt_aus_dem_nachgezogenen_schlusspreis():
    t = WF.update_track({}, _emit(price=0.40), _close(0.40), {}, now=NOW)
    t2 = WF.update_track(t, {"whales": []}, _close(0.52), {KEY: {"winner": "Leo Team"}}, now=NOW)
    assert t2["settled"][0]["clvPP"] == 12.0     # (0.52 − 0.40) × 100


# ── Verfall ──────────────────────────────────────────────────────────────────
def test_nicht_getrackter_play_verfaellt_schnell():
    # Markt gar nicht (mehr) im Close-Feed → bekommt nie eine Auflösung, kurze Frist. KEIN Fake-Ergebnis.
    t = WF.update_track({}, _emit(), _close(), {}, now=NOW)
    t2 = WF.update_track(t, {"whales": []}, {}, {}, now=NOW + timedelta(days=3))
    assert not t2["open"] and not t2["settled"] and t2["expired"] == 1


def test_getrackter_play_bekommt_langen_backstop():
    t = WF.update_track({}, _emit(), _close(), {}, now=NOW)
    t2 = WF.update_track(t, {"whales": []}, _close(), {}, now=NOW + timedelta(days=5))
    assert len(t2["open"]) == 1 and t2["expired"] == 0


# ── Aufschlüsselung ──────────────────────────────────────────────────────────
def test_konsens_und_solo_getrennt_ausgewiesen():
    solo = {"key": "a-b", "side": "A", "price": 0.5, "n": 1, "cat": "Tennis", "entryAvg": 0.5}
    cons = {"key": "c-d", "side": "C", "price": 0.5, "n": 3, "cat": "Fußball", "entryAvg": 0.5}
    close = {"a-b": {"prices": {"A": 0.5}}, "c-d": {"prices": {"C": 0.5}}}
    t = WF.update_track({}, {"whales": [solo, cons]}, close, {}, now=NOW)
    t2 = WF.update_track(t, {"whales": []}, close,
                         {"a-b": {"winner": "B"}, "c-d": {"winner": "C"}}, now=NOW)
    a = t2["agg"]
    assert a["solo"]["n"] == 1 and a["solo"]["pnl"] == -10.0
    assert a["consensus"]["n"] == 1 and a["consensus"]["pnl"] == 10.0
    assert a["byCat"]["Fußball"]["n"] == 1 and a["byCat"]["Tennis"]["n"] == 1


def test_leeres_depot_kippt_nicht_um():
    t = WF.update_track({}, {"whales": []}, {}, {}, now=NOW)
    assert t["agg"]["all"]["n"] == 0 and t["agg"]["consensus"] is None


# ── Konflikt-Flag (24.08.2026, Lucas' INOX-Fall) ─────────────────────────────
# Zwei bewiesene Top-Wallets auf Gegenseiten. Ob solche Plays wirklich schlechter laufen, ist eine
# EMPIRISCHE Frage — also wird der Zustand beim Einstieg eingefroren und getrennt ausgewiesen,
# statt ihn anzunehmen.
def test_konflikt_wird_beim_einstieg_eingefroren():
    t = WF.update_track({}, _emit(conflict=True, againstRank=7), _close(), {}, now=NOW)
    e = t["open"][f"{KEY}|Leo Team"]
    assert e["conflictAtEntry"] is True and e["againstRankAtEntry"] == 7
    # Loest sich der Konflikt spaeter auf, bleibt der Play trotzdem als Konflikt gewertet.
    t2 = WF.update_track(t, _emit(conflict=False), _close(), {}, now=NOW + timedelta(hours=1))
    assert t2["open"][f"{KEY}|Leo Team"]["conflictAtEntry"] is True


def test_konflikt_wandert_in_die_abrechnung():
    t = WF.update_track({}, _emit(conflict=True, againstRank=7), _close(), {}, now=NOW)
    t2 = WF.update_track(t, {"whales": []}, _close(), {KEY: {"winner": "Leo Team"}}, now=NOW)
    assert t2["settled"][0]["conflictAtEntry"] is True


def test_bilanz_trennt_konflikt_von_sauber():
    konflikt = {"key": "a-b", "side": "A", "price": 0.5, "n": 1, "cat": "E-Sport",
                "entryAvg": 0.5, "conflict": True, "againstRank": 4}
    sauber = {"key": "c-d", "side": "C", "price": 0.5, "n": 2, "cat": "E-Sport", "entryAvg": 0.5}
    close = {"a-b": {"prices": {"A": 0.5}}, "c-d": {"prices": {"C": 0.5}}}
    t = WF.update_track({}, {"whales": [konflikt, sauber]}, close, {}, now=NOW)
    t2 = WF.update_track(t, {"whales": []}, close,
                         {"a-b": {"winner": "B"}, "c-d": {"winner": "C"}}, now=NOW)
    a = t2["agg"]
    assert a["conflict"]["n"] == 1 and a["conflict"]["pnl"] == -10.0
    assert a["clean"]["n"] == 1 and a["clean"]["pnl"] == 10.0


def test_ohne_konflikt_kein_konflikt_bucket():
    t = WF.update_track({}, _emit(), _close(), {KEY: {"winner": "Leo Team"}}, now=NOW)
    assert t["agg"]["conflict"] is None and t["agg"]["clean"]["n"] == 1

