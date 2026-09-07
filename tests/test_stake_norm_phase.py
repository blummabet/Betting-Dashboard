"""
tests/test_stake_norm_phase.py — 07.09.2026

Backlog: „Die 🚩 Auffällig-Ansicht ehrlich beschriften. Ihre Prämisse ist gemessen invertiert"
+ „Achse umstellen auf live × Einsatzgröße statt auffällig ja/nein".

Der teure Teil daran ist nicht die Rechnung, sondern die Haltbarkeit: ein Satz wie „über der
Norm verliert" ist heute richtig und in zwei Wochen vielleicht nicht mehr. Deshalb rechnet
`norm_phase` das Urteil über die eigene Prämisse bei jedem Lauf neu, und die Fläche liest es
nur ab. Diese Tests halten fest, dass es dabei bleibt — vor allem, dass alle DREI Ausgänge
möglich sind. Eine Funktion, die nur „widerlegt" sagen kann, ist keine Messung.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("stake_analyse_np", ROOT / "stake_analyse.py")
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)
LS = A.LS


def w(usd, quote, gewonnen, phase="live", liga="Testliga", slug="premier-league", wid=None):
    """Eine abgerechnete Einzelwette. pnl ist das, was kreuz_phase liest.

    Der Slug muss in stake_liga_stufe stehen — eine Liga ohne Ebene faellt aus der Tabelle,
    und zwar absichtlich (sie still als Ebene 1 zu zaehlen war der Fehler davor).
    """
    pnl = round(usd * (quote - 1), 2) if gewonnen else -usd
    return {
        "id": wid or ("%s-%s-%s" % (liga, usd, quote)),
        "liga": liga, "ligaSlug": slug, "sport": "soccer",
        "einsatzUsd": usd, "quote": quote, "phase": phase,
        "eventId": wid or ("e%s" % usd), "kombi": False,
        "ts": "2026-09-07T19:30:00Z", "anpfiff": "2026-09-07T19:00:00Z",
        "abrechnung": {"pnlUsd": pnl, "beine": [{"treffer": gewonnen, "quote": quote}]},
    }


def _norm(median):
    return {"Testliga": {"median": median, "basis": "gelernt", "n": 50}}


# ── Die Achse ────────────────────────────────────────────────────────────────
def test_zeilen_sind_phasen_und_die_summe():
    wetten = ([w(1000, 2.0, True, "live", wid="l%d" % i) for i in range(5)] +
              [w(1000, 2.0, False, "vor", wid="v%d" % i) for i in range(5)])
    k = LS.kreuz_phase(wetten, _norm(1000.0), A._phase)
    assert set(k) == {"live", "vor", "alle"}
    assert k["alle"]["<1.5x"]["n"] == 10, "die Summenzeile zählt beide Phasen"
    assert k["live"]["<1.5x"]["n"] == 5


def test_eine_wette_zaehlt_in_ihrer_phase_und_in_der_summe_je_einmal():
    """Doppelt in derselben Zelle wäre eine stille Verdopplung der Basis."""
    k = LS.kreuz_phase([w(1000, 2.0, True)], _norm(1000.0), A._phase)
    assert k["live"]["<1.5x"]["n"] == 1
    assert k["alle"]["<1.5x"]["n"] == 1


def test_unbekannte_phase_faellt_nicht_raus_sondern_in_die_summe():
    """Alte Zeilen ohne Anpfiff haben keine Phase. Sie aus allem zu streichen wäre eine
    stille Auswahl; sie als 'live' zu zählen wäre eine Erfindung."""
    ohne = w(1000, 2.0, True, phase=None, wid="ohne")
    ohne["phase"] = None
    ohne.pop("anpfiff")
    k = LS.kreuz_phase([ohne], _norm(1000.0), A._phase)
    assert "alle" in k and k["alle"]["<1.5x"]["n"] == 1
    assert "unbekannt" not in k, "unbekannt ist keine Phase, die man anzeigen könnte"


def test_feine_baender_trennen_den_schwanz_ab():
    """>15x war vorher in >6x verborgen — genau das Band, das gemessen etwas sagt."""
    assert LS.bucket(20.0, fein=True) == ">15x"
    assert LS.bucket(20.0) == ">6x", "die grobe Liste der Spielklasse-Ansicht bleibt, wie sie war"
    assert LS.STUFEN == [(1.5, "<1.5x"), (3.0, "1.5-3x"), (6.0, "3-6x"), (float("inf"), ">6x")]


# ── Das Urteil über die eigene Prämisse ──────────────────────────────────────
def test_ohne_genug_basis_ist_die_praemisse_offen():
    """Unter n=30 gibt es keine Grenze — und ohne Grenze kein Urteil in beide Richtungen."""
    wetten = [w(20000, 2.0, i % 2 == 0, wid="x%d" % i) for i in range(10)]
    np = A.norm_phase(wetten, _norm(1000.0))
    assert np["urteil"]["praemisse"] == "offen"
    assert np["urteil"]["folgen"] == [] and np["urteil"]["gegen"] == []


def test_verlierender_schwanz_widerlegt_die_praemisse():
    verlierer = [w(20000, 2.0, False, wid="v%d" % i) for i in range(40)]
    np = A.norm_phase(verlierer, _norm(1000.0))
    assert np["urteil"]["praemisse"] == "widerlegt"
    assert any(x["band"] == ">15x" for x in np["urteil"]["gegen"])


def test_gewinnender_schwanz_stuetzt_sie_auch():
    """Der Gegenbeweis muss genauso möglich sein — sonst misst die Funktion nichts, sondern
    bestätigt nur, was am 07.09. zufällig in den Daten stand."""
    gewinner = [w(20000, 2.0, True, wid="g%d" % i) for i in range(40)]
    np = A.norm_phase(gewinner, _norm(1000.0))
    assert np["urteil"]["praemisse"] == "gestuetzt"
    assert any(x["band"] == ">15x" for x in np["urteil"]["folgen"])


def test_ein_beleg_unterhalb_der_auffaellig_baender_stuetzt_die_praemisse_nicht():
    """Die Prämisse ist „über der Norm sagt etwas". Ein Beleg bei <1.5x sagt darüber nichts —
    er würde sonst als Bestätigung durchgehen, obwohl er das Gegenteil des Arguments ist."""
    gewinner = [w(1000, 2.0, True, wid="g%d" % i) for i in range(40)]
    np = A.norm_phase(gewinner, _norm(1000.0))
    assert np["urteil"]["praemisse"] == "offen"
    assert any(x["band"] == "<1.5x" for x in np["urteil"]["folgen"]), \
        "der Beleg wird trotzdem ausgewiesen, nur nicht als Stütze gewertet"


def test_die_baender_stehen_im_block_damit_die_flaeche_sie_nicht_erfindet():
    np = A.norm_phase([], {})
    assert np["spalten"] == [n for _, n in LS.STUFEN_FEIN]
    assert np["auffBaender"] == ["3-6x", "6-15x", ">15x"]
    assert np["zeilen"] == ["vor", "live", "alle"]


def test_block_haengt_in_der_auswertung():
    """Sonst ist das Feature fertig und die Fläche trotzdem leer — der häufigste Weg,
    auf dem hier etwas 'kaputt' aussieht."""
    led = {"wetten": [w(20000, 2.0, False, wid="v%d" % i) for i in range(40)], "bilanz": {}}
    a = A.auswerten(led, "2026-09-07T20:00:00Z")
    assert "normPhase" in a
    assert a["normPhase"]["urteil"]["praemisse"] in ("offen", "widerlegt", "gestuetzt")
