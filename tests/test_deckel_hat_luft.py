"""🔴 23.09.2026 (Lucas: „betfair action hat scheinbar abgebrochen").

Der Betfair-Lauf um 13:00 UTC endete mit „The operation was canceled" — im Schritt
`ci_sichern.sh`, NACH dem Commit des Belegs (9a7b361, 3 Dateien, 39 Zeilen) und VOR dessen
Push. Der Commit lag nur lokal auf dem Runner und war mit dem naechsten `actions/checkout`
weg. Die Alarme waren da laengst raus; fuer den naechsten Lauf gelten sie als nie gesendet.
Das ist der Vorfall vom 19.09. („Push kam 2x"), gegen den ci_sichern.sh geschrieben wurde.

Gemessen an zwoelf Laeufen desselben Tages (Commit-Zeiten gegen den Cron-Slot):
    bis zum Beleg   Median 6,1 Min
    ganzer Lauf     Median 6,3 Min, laengster 6,6 Min
Der Deckel stand auf 8. Anderthalb Minuten Luft — und die verbraucht der Beleg-Push selbst,
sobald er sich den Branch mit ~130 Commits/Stunde teilen muss (bis zu drei Runden pull+push).

Fehlerklasse: ein Deckel, den der Lauf regelmaessig streift, ist kein Deckel, sondern ein
Wuerfel — und er faellt dort, wo gerade die langsamste Operation laeuft.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import uebersicht_integrity as U  # noqa: E402
import run_health as R  # noqa: E402

BASE = pathlib.Path(__file__).resolve().parent.parent


def _health(*sekunden):
    return {"runs": [{"laeuftSeitS": s} for s in sekunden]}


def test_der_deckel_wird_am_laengsten_lauf_gemessen():
    """Ein Deckel muss den schlechten Tag aushalten, nicht den guten."""
    u = U.deckel_auslastung(_health(300, 310, 320, 470), 8)
    assert u is not None
    pct, med, mx = u
    assert mx == 470 and med == 320
    assert round(pct) == round(100 * 470 / 480)


def test_der_alte_betfair_deckel_waere_aufgefallen():
    """8 Minuten Deckel, 6,6 Minuten laengster Lauf — 82 %."""
    pct, _, _ = U.deckel_auslastung(_health(378, 372, 366, 396), 8)
    assert pct >= U.DECKEL_ENG_PCT, pct


def test_der_neue_deckel_hat_luft():
    pct, _, _ = U.deckel_auslastung(_health(378, 372, 366, 396), 14)
    assert pct < U.DECKEL_ENG_PCT, pct


def test_ohne_deckel_und_ohne_daten_wird_nicht_geurteilt():
    """Fehlende Information ist keine Erlaubnis — und auch kein Vorwurf."""
    assert U.deckel_auslastung(_health(300, 300, 300), None) is None
    assert U.deckel_auslastung(_health(300, 300), 8) is None, "zwei Laeufe sind keine Messung"
    assert U.deckel_auslastung({"runs": [{"laeuftSeitS": None}] * 5}, 8) is None


def test_betfair_hat_seinen_deckel_angehoben():
    t = (BASE / ".github" / "workflows" / "betfair.yml").read_text(encoding="utf-8")
    assert U._timeout_minuten(t) >= 12, "der Deckel ist wieder eng"
    # und er bleibt unter dem Takt, sonst ueberholen sich die Laeufe
    cron = re.search(r"cron:\s*'(\*/\d+)", t)
    if cron:
        takt = int(cron.group(1).split("/")[1])
        assert U._timeout_minuten(t) <= takt, "Deckel groesser als der Takt"


def test_der_lauf_misst_seine_eigene_laufzeit():
    """Ohne diese Zahl muss man die Laufzeit aus git ausgraben — so wie ich heute."""
    e = R.baue_eintrag("W", 1, "u", [], lauf={"startedAt": "2026-09-23T13:00:00Z",
                                              "createdAt": "2026-09-23T12:59:00Z"})
    assert isinstance(e.get("laeuftSeitS"), (int, float)), e
    assert e["laeuftSeitS"] > 0


def test_ohne_startzeit_steht_dort_none_und_nicht_null():
    e = R.baue_eintrag("W", 1, "u", [], lauf={})
    assert e.get("laeuftSeitS") is None


def test_der_waechter_haengt_in_der_batterie():
    assert U.check_der_deckel_hat_luft in U.UEBERSICHT_CHECKS


def test_der_waechter_schlaegt_an_wenn_es_eng_wird(tmp_path):
    c = U.check_der_deckel_hat_luft({})
    assert c["severity"] == "warn"
    # Er darf nicht still „ok" sagen, solange er gar nichts gemessen hat.
    if c["nFail"] == 0:
        assert c["ok"] is True
