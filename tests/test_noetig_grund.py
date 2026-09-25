"""🔴 25.09.2026 (Lucas-Übersicht-Check).

Auf dem Board stand an 25 der 444 Schubladen „Schnitt nicht positiv". Nachgezählt, auf wie
viele der Satz zutraf: null.

    Betfair-Aggregat, gar keine Einzelrenditen   12   (11 davon mit BELEGTER Untergrenze)
    unter 10 Werten, Hochrechnung unmöglich      12
    ruhende Zeile, Feld fehlt ganz                1
    Schnitt wirklich <= 0                         0

Schlimmster Fall: „Kazakhstan Premier League · Match Odds", ROI +43,8 %, UG +12,6 % — im
Register daneben mit Stern als bestes Betfair-Fach.

Ursache: `bewerte(name, "betfair", [], [])`. Dieselbe Zeile, die am 15.09. `clvUrteil` gekostet
hat — damals reparaturt, ohne zu fragen, welche anderen Felder dieselbe Herkunft haben.
Fehlerklasse: *fehlende Information rendert als Behauptung.*
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import freigabe as F  # noqa: E402
import uebersicht_integrity as UI  # noqa: E402

JS = (pathlib.Path(__file__).resolve().parent.parent / "main-dashboard.js").read_text(
    encoding="utf-8")


# ── Der Grund selbst ────────────────────────────────────────────────────────────────
def test_vier_zustaende_und_keiner_heisst_wie_der_andere():
    assert F.noetig_grund([], 30) == "keine_einzelwerte"   # Aggregat: Plays ja, Werte nein
    assert F.noetig_grund([], 0) == "zu_wenige"            # gar nichts da
    assert F.noetig_grund([0.2] * 5, 5) == "zu_wenige"     # unter NOETIG_MIN_N
    assert F.noetig_grund([-0.1] * 20, 20) == "nicht_positiv"
    assert F.noetig_grund([0.1] * 20, 20) is None          # es GIBT eine Hochrechnung


def test_ein_positiver_schnitt_heisst_niemals_nicht_positiv():
    """Die eine Aussage, die nie falsch sein darf."""
    for n in (10, 12, 30, 200):
        assert F.noetig_grund([0.01] * n, n) != "nicht_positiv"
    assert F.noetig_grund([0.0] * 30, 30) == "nicht_positiv"   # genau null ist nicht positiv


def test_jeder_grund_hat_einen_text():
    for k in ("keine_einzelwerte", "zu_wenige", "nicht_positiv"):
        assert F.NOETIG_GRUND_TEXT.get(k), k


# ── Die Quelle des Fundes: das Betfair-Aggregat ─────────────────────────────────────
def test_betfair_aggregat_nennt_seine_herkunft_nicht_sein_vorzeichen():
    """Der Kazakhstan-Fall, nachgebaut: n=30, ROI +43,8 %, eigene Untergrenze +12,6 %."""
    rec = {"byLeagueMarket": {"Kazakhstan Premier League|Match Odds": {
        "n": 30, "hitRate": 0.6, "roi": 0.4377, "roiUg": 0.1263, "ugAb": 30}}}
    z = [x for x in F.betfair_schubladen(rec) if "Kazakhstan" in x["schublade"]]
    assert len(z) == 1, z
    z = z[0]
    assert z["roiLb"] == 0.1263
    assert z["noetigGrund"] == "keine_einzelwerte", z.get("noetigGrund")
    assert z["noetigGrund"] != "nicht_positiv"


def test_jede_betfair_schublade_traegt_den_grund():
    rec = {"byMarket": {"Match Odds": {"n": 900, "hitRate": 0.52, "roi": 0.004},
                        "Half Time": {"n": 40, "hitRate": 0.6, "roi": -0.09}},
           "byLeagueMarket": {"X|Match Odds": {"n": 31, "hitRate": 0.6, "roi": 0.3}}}
    zs = F.betfair_schubladen(rec)
    assert zs
    for z in zs:
        assert z.get("noetigGrund") == "keine_einzelwerte", z["schublade"]


# ── Das Frontend darf nicht mehr raten ──────────────────────────────────────────────
def test_das_board_liest_den_grund_und_erfindet_ihn_nicht():
    """Vor dem Fund stand hier `if (r.noetigNRoi == null) -> 'Schnitt nicht positiv'`."""
    assert "FG_NOETIG_TEXT" in JS
    for k in ("keine_einzelwerte", "zu_wenige", "nicht_positiv"):
        assert k in JS, k
    # Der Satz darf nur noch aus der Tabelle kommen, nicht aus einem Zweig daneben.
    treffer = re.findall(r"noetigNRoi == null\)\s*\{\s*\n([^\n]*)", JS)
    assert treffer, JS[:200]
    for t in treffer:
        assert "Schnitt nicht positiv" not in t, t
        assert "FG_NOETIG_TEXT" in t or "_ngT" in t, t


def test_unbekannter_grund_rendert_als_schweigen():
    """Nichts zu wissen ist keine Aussage über den Schnitt — der wichtigste Teil der Reparatur."""
    i = JS.index("FG_NOETIG_TEXT[_ng]")
    aus = JS[i:i + 400]
    assert "_ngT ?" in aus, aus[:200]
    assert "''" in aus.split("_ngT ?")[1][:220], aus[:300]


# ── Der Guard faengt seinen eigenen Fall ────────────────────────────────────────────
def _ctx(zeilen):
    return {"freigabe": {"alle": zeilen}}


def test_guard_faengt_den_widerspruch():
    c = UI.check_kein_grund_widerspricht_seiner_zahl(_ctx([
        {"schublade": "Kazakhstan Premier League · Match Odds", "n": 30, "roi": 0.4377,
         "roiLb": 0.1263, "noetigGrund": "nicht_positiv"}]))
    assert c["failures"], c
    assert "Kazakhstan" in c["failures"][0]


def test_guard_faengt_positiven_roi_ohne_belegte_untergrenze():
    """Auch ohne Untergrenze: ein positiver Schnitt ist nicht „nicht positiv“."""
    c = UI.check_kein_grund_widerspricht_seiner_zahl(_ctx([
        {"schublade": "X", "n": 12, "roi": 0.35, "roiLb": None,
         "noetigGrund": "nicht_positiv"}]))
    assert c["failures"], c
    assert "ohne Untergrenze" in c["failures"][0], c["failures"][0]


def test_guard_nennt_die_untergrenze_wenn_es_eine_gibt():
    """Die Mutationsprobe hat den Untergrenzen-Zweig ersatzlos entfernen lassen, ohne dass
    etwas rot wurde — der zweite Zweig fing denselben Fall. Jetzt pruefen die Tests, WAS die
    Meldung sagt, nicht nur DASS sie kommt."""
    c = UI.check_kein_grund_widerspricht_seiner_zahl(_ctx([
        {"schublade": "Kazakhstan Premier League \u00b7 Match Odds", "n": 30, "roi": 0.4377,
         "roiLb": 0.1263, "noetigGrund": "nicht_positiv"}]))
    assert c["failures"], c
    assert "UG +12.6 %" in c["failures"][0], c["failures"][0]


def test_guard_schweigt_bei_richtigem_grund():
    c = UI.check_kein_grund_widerspricht_seiner_zahl(_ctx([
        {"schublade": "A", "n": 30, "roi": 0.44, "roiLb": 0.13,
         "noetigGrund": "keine_einzelwerte"},
        {"schublade": "B", "n": 30, "roi": -0.10, "roiLb": -0.30,
         "noetigGrund": "nicht_positiv"}]))
    assert c["failures"] == [], c


def test_guard_faengt_den_halben_rollout():
    """Halb ausgerollt ist schlimmer als gar nicht — dann raet die Oberflaeche bei der Haelfte."""
    c = UI.check_kein_grund_widerspricht_seiner_zahl(_ctx([
        {"schublade": "A", "n": 30, "roi": 0.44, "roiLb": 0.13,
         "noetigGrund": "keine_einzelwerte"},
        {"schublade": "B", "n": 30, "roi": 0.20, "roiLb": 0.01, "noetigNRoi": None}]))
    assert c["failures"], c
    assert "ohne `noetigGrund`" in c["failures"][0]


def test_guard_meldet_die_rollout_luecke_als_hinweis_nicht_als_fund():
    """Solange kein Lauf das Feld geschrieben hat, ist das kein Fehler."""
    c = UI.check_kein_grund_widerspricht_seiner_zahl(_ctx([
        {"schublade": "A", "n": 30, "roi": 0.44, "roiLb": 0.13, "noetigNRoi": None}]))
    assert c["failures"] == [], c
    assert "Rollout" in (c.get("hinweis") or ""), c
