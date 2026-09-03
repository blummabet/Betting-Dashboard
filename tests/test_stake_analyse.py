"""tests/test_stake_analyse.py — 03.09.2026

Lucas: „anhand der Daten dort kriegen wir genug kleine Ligen, wo Leute mit guten Infos setzen."

Genau das ist der Teil, der leicht schiefgeht. Eine absolute Schwelle findet keine kleinen
Ligen, sie findet nur grosse Zahlen — und die stehen fast immer bei La Liga und im US Open.
Deshalb wird 'auffällig' hier RELATIV zur Norm der Liga bestimmt, und die Norm kommt aus den
eigenen Daten statt aus einer ausgedachten Zahl.

Die Tests sichern vor allem die Fälle, in denen es keine Norm gibt. Eine Liga mit drei Wetten
ist nicht 'unauffällig' — über sie ist nichts bekannt, und das muss anders aussehen als ein
gemessenes Nein.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("stake_analyse_t", ROOT / "stake_analyse.py")
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


def w(liga="La Liga", usd=2000, ts="2026-09-03T18:00:00Z", ko="2026-09-03T19:00:00Z",
      beine=None, kombi=False, markt="Winner", auswahl="A", wid=None):
    d = {"id": wid or ("%s-%s" % (liga, usd)), "liga": liga, "einsatzUsd": usd, "ts": ts,
         "anpfiff": ko, "kombi": kombi, "markt": markt, "auswahl": auswahl,
         "event": "A - B", "quote": 2.0}
    if beine is not None:
        d["abrechnung"] = {"endstand": True, "beine": beine, "pnlUsd": None}
    return d


# ── Phase: aus dem Feld, sonst nachgerechnet ─────────────────────────────────
def test_phase_kommt_aus_dem_feld_wenn_da():
    assert A._phase({"phase": "live"}) == "live"


def test_phase_wird_fuer_alte_zeilen_nachgerechnet():
    """Zeilen von vor dem 03.09. haben das Feld nicht. Sie duerfen deshalb nicht aus jeder
    Auswertung fallen — ts und anpfiff stehen im Ledger, es ist dieselbe Rechnung."""
    assert A._phase({"ts": "2026-09-03T20:00:00Z", "anpfiff": "2026-09-03T19:00:00Z"}) == "live"
    assert A._phase({"ts": "2026-09-03T18:00:00Z", "anpfiff": "2026-09-03T19:00:00Z"}) == "vor"


def test_phase_ohne_anpfiff_bleibt_unbekannt():
    assert A._phase({"ts": "2026-09-03T18:00:00Z"}) == "unbekannt"
    assert A._phase({}) == "unbekannt"


def test_minute_nur_fuer_live():
    assert A._minute({"ts": "2026-09-03T20:05:00Z", "anpfiff": "2026-09-03T19:00:00Z"}) == 65
    assert A._minute({"ts": "2026-09-03T18:00:00Z", "anpfiff": "2026-09-03T19:00:00Z"}) is None


# ── Liga-Norm ────────────────────────────────────────────────────────────────
def test_norm_wird_erst_ab_genug_wetten_gelernt():
    wenige = [w(liga="Klein", usd=1000 + i) for i in range(5)]
    n = A.liga_norm(wenige)
    assert n["Klein"]["basis"] == "zu duenn"
    assert n["Klein"]["median"] is None, "keine erfundene Zahl, wo nichts gemessen ist"


def test_norm_median_und_p90():
    viele = [w(liga="Gross", usd=1000 * (i + 1), wid="g%d" % i) for i in range(20)]
    n = A.liga_norm(viele)["Gross"]
    assert n["basis"] == "gelernt"
    assert n["n"] == 20
    assert n["median"] == 10500.0
    assert n["max"] == 20000.0


def test_norm_ignoriert_wetten_ohne_usd_wert():
    ws = [w(liga="X", usd=1000, wid="a%d" % i) for i in range(20)]
    ws.append(w(liga="X", usd=None, wid="ohne"))
    assert A.liga_norm(ws)["X"]["n"] == 20


# ── Auffällig ist relativ ────────────────────────────────────────────────────
def test_auffaellig_misst_gegen_den_median_der_liga():
    viele = [w(liga="L", usd=2000, wid="v%d" % i) for i in range(20)]
    norm = A.liga_norm(viele)
    assert A.auffaellig(w(liga="L", usd=20000), norm)["faktor"] == 10.0


def test_ohne_norm_gibt_es_KEINEN_faktor():
    """Nicht 1.0, nicht 0. Ueber eine Liga mit drei Wetten ist nichts bekannt, und
    'unauffaellig' waere eine Behauptung."""
    norm = A.liga_norm([w(liga="Winzig", usd=1000, wid="w%d" % i) for i in range(3)])
    a = A.auffaellig(w(liga="Winzig", usd=50000), norm)
    assert a["faktor"] is None
    assert a["basis"] == "keine Norm"


def test_dieselbe_summe_ist_in_zwei_ligen_verschieden_auffaellig():
    """Der ganze Punkt: $9.000 auf La Liga ist Dienstag, $9.000 anderswo ein Ereignis."""
    ws = ([w(liga="Gross", usd=9000, wid="G%d" % i) for i in range(20)]
          + [w(liga="Ruhig", usd=300, wid="R%d" % i) for i in range(20)])
    norm = A.liga_norm(ws)
    assert A.auffaellig(w(liga="Gross", usd=9000), norm)["faktor"] == 1.0
    assert A.auffaellig(w(liga="Ruhig", usd=9000), norm)["faktor"] == 30.0


# ── Kleine Liga, grosses Geld ────────────────────────────────────────────────
def test_ueber_der_norm_wird_gefunden():
    ws = [w(liga="L", usd=2000, wid="n%d" % i) for i in range(20)]
    ws.append(w(liga="L", usd=30000, wid="knall"))
    norm = A.liga_norm(ws)
    tr = A.kleine_liga_gross(ws, norm)
    assert any(x["id"] == "knall" for x in tr)
    assert "Median" in [x for x in tr if x["id"] == "knall"][0]["grund"]


def test_kleine_liga_ohne_norm_wird_ueber_den_globalen_punkt_gefunden():
    ws = [w(liga="Gross", usd=1000, wid="g%d" % i) for i in range(40)]
    ws.append(w(liga="Exotisch", usd=40000, wid="exot"))
    tr = A.kleine_liga_gross(ws, A.liga_norm(ws))
    treffer = [x for x in tr if x["id"] == "exot"]
    assert treffer, "genau dieser Fall ist der interessante"
    assert "kleine Liga" in treffer[0]["grund"]
    assert treffer[0]["faktor"] is None, "ohne Norm gibt es keinen Faktor — und keinen erfundenen"


def test_die_beiden_gruende_werden_nicht_vermischt():
    """Der zweite Weg ist schwaecher als der erste. Beide zu markieren ist richtig, beide
    gleich zu nennen waere falsch."""
    ws = ([w(liga="L", usd=2000, wid="n%d" % i) for i in range(20)]
          + [w(liga="L", usd=30000, wid="ueberNorm"),
             w(liga="Exotisch", usd=30000, wid="kleineLiga")])
    tr = {x["id"]: x["grund"] for x in A.kleine_liga_gross(ws, A.liga_norm(ws))}
    assert "Median" in tr["ueberNorm"]
    assert "kleine Liga" in tr["kleineLiga"]
    assert tr["ueberNorm"] != tr["kleineLiga"]


def test_kombis_zaehlen_nicht_als_auffaelliger_einsatz():
    ws = [w(liga="L", usd=2000, wid="n%d" % i) for i in range(20)]
    ws.append(w(liga="L", usd=30000, wid="k", kombi=True))
    assert not [x for x in A.kleine_liga_gross(ws, A.liga_norm(ws)) if x["id"] == "k"]


# ── Quoten: nie ohne Untergrenze ─────────────────────────────────────────────
def test_kleine_stichprobe_bekommt_keine_untergrenze():
    q = A._quote(4, 5)
    assert q["quote"] == 0.8
    assert q["ug"] is None, "unter n=%d gibt es kein Urteil" % A.MIN_N
    assert q["belegt"] is False


def test_grosse_stichprobe_bekommt_eine_untergrenze():
    q = A._quote(70, 100)
    assert q["ug"] is not None
    assert q["ug"] < q["quote"], "die Untergrenze liegt unter dem Punktschaetzer"
    assert q["belegt"] is True


def test_belegt_verlangt_mehr_als_muenzwurf():
    q = A._quote(51, 100)
    assert q["quote"] == 0.51
    assert q["belegt"] is False, "51% auf n=100 ist kein Beleg"


def test_ohne_daten_keine_quote():
    q = A._quote(0, 0)
    assert q["quote"] is None and q["ug"] is None and q["belegt"] is False


# ── Schubladen ───────────────────────────────────────────────────────────────
def test_schublade_zaehlt_beine_nicht_wetten():
    ws = [w(beine=[{"treffer": True}, {"treffer": False}], kombi=True),
          w(beine=[{"treffer": True}], wid="einzel")]
    s = A._schublade(ws)
    assert s["wetten"] == 2
    assert s["n"] == 3, "zwei Kombi-Beine plus ein Einzel-Bein"
    assert s["treffer"] == 2


def test_schublade_ignoriert_offene_wetten():
    ws = [w(beine=[{"treffer": True}]), w(wid="offen")]
    assert A._schublade(ws)["n"] == 1


def test_annullierte_beine_zaehlen_nicht_mit():
    ws = [w(beine=[{"treffer": True}, {"treffer": None, "neutral": True}])]
    assert A._schublade(ws)["n"] == 1


# ── Vorregistrierung ─────────────────────────────────────────────────────────
def test_vorregistrierung_schreibt_einmal_und_ueberschreibt_nie(tmp_path, monkeypatch):
    """Nachtraeglich die beste Variante auszusuchen ist der Fehler, den wir ueberall sonst
    rausgeraeumt haben. Ein spaeter angemeldeter Trigger startet bei n=0."""
    datei = tmp_path / "reg.json"
    monkeypatch.setattr(A, "REG_FILE", datei)
    erst = A.vorregistrieren("2026-09-03T20:00:00Z")
    assert "vor_anpfiff_alle" in erst and "kleine_liga" in erst
    assert erst["vor_anpfiff_alle"]["angemeldet"] == "2026-09-03T20:00:00Z"

    zweit = A.vorregistrieren("2026-10-01T00:00:00Z")
    assert zweit["vor_anpfiff_alle"]["angemeldet"] == "2026-09-03T20:00:00Z", (
        "ein Anmeldedatum darf nicht wandern")


def test_jeder_registrierte_trigger_nennt_signatur_und_zielN(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "REG_FILE", tmp_path / "reg.json")
    for name, k in A.vorregistrieren("2026-09-03T20:00:00Z").items():
        assert k.get("signatur"), name
        assert k.get("zielN"), name
        assert k.get("warum"), name


# ── Gesamtlauf ───────────────────────────────────────────────────────────────
def test_auswerten_bleibt_unreif_solange_zu_wenig_abgerechnet_ist():
    ws = [w(beine=[{"treffer": True}], wid="a%d" % i) for i in range(5)]
    a = A.auswerten({"wetten": ws, "bilanz": {"gewertet": 5}}, "jetzt")
    assert a["reif"] is False
    assert a["urteilAb"] == A.MIN_N


def test_auswerten_ueberlebt_ein_leeres_ledger():
    a = A.auswerten({"wetten": []}, "jetzt")
    assert a["nWetten"] == 0
    assert a["schubladen"]["gesamt"]["n"] == 0
    assert a["auffaellige"] == []


def test_auswertung_nennt_die_anonymitaet_der_quelle():
    a = A.auswerten({"wetten": []}, "jetzt")
    assert "anonym" in a["hinweis"], "kein Track-Record je Konto — das muss im Artefakt stehen"
