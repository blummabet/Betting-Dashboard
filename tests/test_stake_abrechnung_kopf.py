"""12.10.2026: seit 08.10. ~01:43 UTC keine Stake-Abrechnung mehr. stake_settle fragte die
aeltesten 300 reifen Wetten; 298 davon bekamen von Stake keine Antwort, blieben vorn und
fuellten jeden Lauf. 17.015 Wetten wurden nie gefragt."""
from datetime import datetime, timedelta, timezone

import stake_settle as S
import uebersicht_integrity as U

JETZT = datetime(2026, 10, 12, 14, tzinfo=timezone.utc)


def _w(i, ts, abr=None):
    return {"id": "sport:%d" % i, "ts": ts, "anpfiff": ts, **({"abrechnung": abr} if abr else {})}


def test_nie_gefragte_kommen_vor_den_schon_gefragten():
    alt_ohne_antwort = [_w(i, "2026-10-08T02:00:00Z",
                           {"geprueft": "2026-10-12T13:00:00Z", "ohneAntwort": 40}) for i in range(300)]
    neu = [_w(1000 + i, "2026-10-10T12:00:00Z") for i in range(5)]
    dran = sorted(alt_ohne_antwort + neu, key=S.reihenfolge)[:300]
    # Auf dem alten Code (Sortierung nach ts) waeren es 300 alte und keine neue.
    assert all(w["id"].startswith("sport:10") for w in dran[:5])


def test_ohne_antwort_rotiert_nach_der_letzten_frage():
    a = _w(1, "2026-10-08T02:00:00Z", {"geprueft": "2026-10-12T13:00:00Z"})
    b = _w(2, "2026-10-09T02:00:00Z", {"geprueft": "2026-10-11T13:00:00Z"})
    assert sorted([a, b], key=S.reihenfolge)[0] is b


def test_aufgegebene_werden_nicht_mehr_gefragt():
    w = _w(1, "2026-10-01T02:00:00Z", {"unaufloesbar": True, "geprueft": "x"})
    assert not S.faellig(w, JETZT)


def test_guard_faengt_den_stillstand():
    reif = [_w(i, (JETZT - timedelta(hours=30)).isoformat()) for i in range(20)]
    c = U.check_stake_abrechnung_laeuft({"stakeLedger": {"wetten": reif}}, jetzt=JETZT)
    assert c["nFail"] == 1 and c["severity"] == "error"


@__import__("pytest").mark.skip(reason="25.10.2026: Stake hier abgedreht, Wächter nicht mehr in der Batterie")
def test_guard_still_bei_normaler_abrechnung():
    reif = [_w(i, (JETZT - timedelta(hours=30)).isoformat(), {"endstand": True}) for i in range(20)]
    c = U.check_stake_abrechnung_laeuft({"stakeLedger": {"wetten": reif}}, jetzt=JETZT)
    assert c["ok"]
    assert U.check_stake_abrechnung_laeuft in U.UEBERSICHT_CHECKS
