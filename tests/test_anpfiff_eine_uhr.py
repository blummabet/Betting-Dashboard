"""29.09.2026 (Lucas' Übersicht-Check): Czechia v England „⏱ 14m" in Ebene 3, „⏱ 9 min"
daneben; Polymarket nennt 18:45. Die Close-Zeile hatte hoursToKickoff=0.45 (gemessen zu
Scan-Beginn ~18:18) mit capturedAt 18:23 (Schreibzeit) -> rekonstruierter Anpfiff 18:50."""
from datetime import datetime, timedelta, timezone

import poly_money_broad as P
import poly_data_integrity as PI
import stoerungsmeldung as SM

KO = datetime(2026, 9, 29, 18, 45, tzinfo=timezone.utc)
SCAN_START = datetime(2026, 9, 29, 18, 18, tzinfo=timezone.utc)
SCHREIBEN = datetime(2026, 9, 29, 18, 23, 12, tzinfo=timezone.utc)


def _markt(mit_ko=True):
    m = {"key": "unl-cze-eng-2026-09-29", "league": "UNL", "sport": "Fußball",
         "hoursToKickoff": (KO - SCAN_START).total_seconds() / 3600,      # 0.45, Scan-Beginn
         "totalUsd": 500000, "shares": {"England": 9.0, "Czechia": 1.0},
         "prices": {"England": 0.74, "Czechia": 0.1}}
    if mit_ko:
        m["koTs"] = KO.isoformat()
    return m


def _rekonstruiert(e):
    cap = datetime.fromisoformat(e["capturedAt"])
    return cap + timedelta(hours=e["hoursToKickoff"])


def test_gamma_formate_werden_gelesen():
    assert P._ko_zeit({"gameStartTime": "2026-09-29 18:45:00+00"}) == KO
    assert P._ko_zeit({"startTime": "2026-09-29T18:45:00Z"}) == KO
    assert P._ko_zeit({}) is None


def test_capture_rechnet_htk_zur_schreibzeit():
    out = P.capture([_markt()], {}, now=SCHREIBEN)
    e = out["unl-cze-eng-2026-09-29"]
    assert abs((_rekonstruiert(e) - KO).total_seconds()) <= 60
    assert e["koTs"] == KO.isoformat()


def test_gegentest_ohne_ko_liegt_es_um_die_scan_dauer_daneben():
    """Der alte Weg (kein koTs): +5 Min — genau der Board-Fund."""
    e = P.capture([_markt(mit_ko=False)], {}, now=SCHREIBEN)["unl-cze-eng-2026-09-29"]
    assert (_rekonstruiert(e) - KO).total_seconds() > 4 * 60


def test_guard_faengt_zwei_uhren_und_ist_eingestuft():
    schlecht = {"k": {"capturedAt": SCHREIBEN.isoformat(), "hoursToKickoff": 0.45, "koTs": KO.isoformat()}}
    c = PI.check_anpfiff_eine_uhr(PI.PolyCtx(close=schlecht))
    assert not c["ok"] and "+5 Min" in c["failures"][0]
    gut = P.capture([_markt()], {}, now=SCHREIBEN)
    assert PI.check_anpfiff_eine_uhr(PI.PolyCtx(close=gut))["ok"]
    assert "anpfiff_eine_uhr" in SM.GEPRUEFT_KEIN_GELD


def test_prune_upcoming_rechnet_nach():
    fresh = {"k": {"hoursToKickoff": 5.0, "koTs": KO.isoformat(), "prices": {"a": 0.5}}}
    out = P.prune_upcoming({}, fresh, now=SCHREIBEN)
    assert abs((_rekonstruiert(out["k"]) - KO).total_seconds()) <= 60
