"""🔴 23.09.2026 — die Stoerungsmeldung meldete rot: „1 Public-Push SEIT der Sofort-Sicherung
ohne Ledger-Zeile (fresh:36041720, 21.09. 22:46) — der Sicherungsschritt greift nicht".

Nachgemessen: dieser Verlust hatte eine ANDERE Ursache als die vier davor — die Anreicherung
(`_consensus_for_push` / `_serie_fuer_push`) riss die ganze Ledger-Zeile mit, wenn sie warf. Das
wurde am 22.09.2026 05:14 behoben (817e5a0f). Der heutige Code kann diesen Fall nicht mehr
erzeugen, und seit dem 21.09. 20:16 ist ueberhaupt kein Public-Push mehr gesendet worden.

Die Meldung blieb trotzdem rot und haette es fuer immer getan: „datiert" hiess „nach der
Reparatur", und gemeint war die Reparatur vom 20.09. — die erste von inzwischen zwei.

Fehlerklasse: ein Alarm, der nie wieder ausgeht, ist keiner. Die Grenze muss mit jeder Reparatur
wandern, sonst lernt man, ueber ihn hinwegzulesen — und dann sieht man den echten nicht.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import betfair_public_eval as E  # noqa: E402

BASE = pathlib.Path(__file__).resolve().parent.parent


def _seen(**kv):
    return {k: ({"t": v} if v else {}) for k, v in kv.items()}


LEDGER = [{"scenario": "fresh", "matchId": "1", "k": "fresh:1:Match Odds"}]


def test_die_grenze_ist_die_juengste_reparatur():
    assert E.letzte_reparatur() == max(t for t, _ in E.REPARATUREN)
    assert E.letzte_reparatur() >= "2026-09-22T05:14"


def test_jede_reparatur_nennt_ihren_grund():
    """Ein Eintrag ohne Begruendung verschiebt die Grenze, ohne dass jemand weiss wofuer."""
    for t, grund in E.REPARATUREN:
        assert t[:4] == "2026" and len(t) >= 19, t
        assert isinstance(grund, str) and len(grund) > 40, (t, grund)


def test_verlust_vor_der_letzten_reparatur_ist_keine_frische_wunde():
    """Genau der Fall aus der Meldung: 21.09. 22:46, Reparatur 22.09. 05:14."""
    seen = _seen(**{"fresh:36041720": "2026-09-21T22:46:48+00:00"})
    frisch = E.gesendet_ohne_beleg_datiert(seen, LEDGER)
    assert frisch == [], frisch
    narbe = E.gesendet_ohne_beleg_narbe(seen, LEDGER)
    assert narbe == ["fresh:36041720"]


def test_verlust_nach_der_letzten_reparatur_ist_ein_befund():
    seen = _seen(**{"fresh:99": "2026-09-23T04:00:00+00:00"})
    frisch = E.gesendet_ohne_beleg_datiert(seen, LEDGER)
    assert [z["key"] for z in frisch] == ["fresh:99"]
    assert E.gesendet_ohne_beleg_narbe(seen, LEDGER) == []


def test_undatierter_verlust_bleibt_narbe():
    seen = {"fresh:7": {}}
    assert E.gesendet_ohne_beleg_datiert(seen, LEDGER) == []
    assert E.gesendet_ohne_beleg_narbe(seen, LEDGER) == ["fresh:7"]


def test_narbe_und_frische_wunde_ueberschneiden_sich_nie():
    """Die Meldung zaehlte vier und druckte fuenf Schluessel — weil beide Listen dieselbe war."""
    seen = _seen(**{"fresh:1001": "2026-09-19T10:00:00+00:00",
                    "fresh:1002": "2026-09-23T10:00:00+00:00"})
    seen["fresh:1003"] = {}
    frisch = {z["key"] for z in E.gesendet_ohne_beleg_datiert(seen, LEDGER)}
    narbe = set(E.gesendet_ohne_beleg_narbe(seen, LEDGER))
    assert frisch & narbe == set()
    assert frisch | narbe == set(E.gesendet_ohne_beleg(seen, LEDGER))


def test_die_meldung_druckt_die_alten_schluessel_nicht_die_frischen():
    import uebersicht_integrity as U
    r = {"gesendetOhneBeleg": 5, "gesendetOhneBelegNeu": 1,
         "gesendetOhneBelegNeuKeys": [{"key": "fresh:neu", "t": "2026-09-23T04:00"}],
         "gesendetOhneBelegKeys": ["fresh:a", "fresh:b", "fresh:c", "fresh:d", "fresh:neu"],
         "gesendetOhneBelegAltKeys": ["fresh:a", "fresh:b", "fresh:c", "fresh:d"],
         "belegReparaturAb": "2026-09-22T05:14:00+00:00"}
    c = U.check_jeder_push_hat_seinen_beleg({"bfPublicRecord": r})
    alt_zeile = [f for f in c["failures"] if "aeltere" in f]
    assert alt_zeile, c["failures"]
    assert "fresh:neu" not in alt_zeile[0], alt_zeile[0]


def test_der_alarm_ist_heute_aus():
    """Gegenprobe am echten Artefakt: nach der Reparatur vom 22.09. gibt es keinen Befund."""
    f = BASE / "betfair_public_record.json"
    if not f.exists():
        return
    r = json.loads(f.read_text(encoding="utf-8"))
    # Rollout-Luecke: bis betfair.yml einmal gelaufen ist, stammt das Artefakt noch aus dem
    # Code von gestern und kennt die verschobene Grenze nicht. Dann ist hier nichts zu pruefen.
    ab = r.get("belegReparaturAb")
    if not ab:
        return
    for z in (r.get("gesendetOhneBelegNeuKeys") or []):
        assert str(z.get("t")) >= ab, ("Verlust VOR der letzten Reparatur als Befund gemeldet", z)
