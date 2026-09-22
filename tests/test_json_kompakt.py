"""tests/test_json_kompakt.py — 22.09.2026

🔴 Lucas: „Was ist da jetzt mit diesen 12 Megabyte, liga-data.json — was, was kann man da
machen, oder wo führt das zu Problemen? Ich brauche immer Lösungsvorschläge."

Gemessen: von den 12,7 MB, die die Übersicht vor der ersten Kachel parst, sind **3,85 MB
reiner Leerraum** (liga-data −2,10, mls-data −0,78, betfair_prices −0,51, liga_streaks −0,26).
Über die Leitung gehen ohnehin nur 1,2 MB (gzip) — die Bytes kosten also Parse-Zeit und
Speicher am Handy, und genau darüber ging die Beschwerde am 12.09.

Der Schritt sitzt vor `git add` und nicht bei den Schreibern: liga-data.json wird von 15+
Stellen geschrieben, fast alle mit `indent=2`. Eine vergessene ließe die Datei bei jedem Lauf
zwischen zwei Formaten springen — das wäre teurer als das Problem.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))

import json_kompakt as K  # noqa: E402

WORKFLOWS = {
    "fetch-liga-odds-dense.yml": ["liga-data.json"],
    "fetch-mls-odds-dense.yml": ["mls-data.json"],
    "update-liga.yml": ["liga-data.json", "liga_streaks.json"],
    "update-mls.yml": ["mls-data.json", "mls_streaks.json"],
    # 0,51 MB Leerraum, und sie wechselt alle 14 Minuten — die Uebersicht laedt sie bei jedem
    # Refresh. Vom Waechter unten beim Bau sofort gemeldet, genau dafuer gibt es ihn.
    "betfair.yml": ["betfair_prices.json"],
}


def test_die_einrueckung_faellt_weg_und_der_inhalt_bleibt(tmp_path):
    p = tmp_path / "x.json"
    daten = {"a": [1, 2, {"b": "ü"}], "c": {"d": None, "e": True}}
    p.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    vor, nach = K.kompakt(p)
    assert nach < vor
    assert json.loads(p.read_text(encoding="utf-8")) == daten
    assert "\n" not in p.read_text(encoding="utf-8")


def test_er_ist_idempotent():
    """Der zweite Lauf darf nichts mehr tun — sonst waere jeder Lauf ein Commit."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.json"
        p.write_text(json.dumps({"a": list(range(50))}, indent=2), encoding="utf-8")
        assert K.kompakt(p) is not None
        assert K.kompakt(p) is None, "beim zweiten Mal gibt es nichts zu kuerzen"


def test_umlaute_werden_nicht_escaped():
    """`ensure_ascii=True` blaeht die Datei wieder auf — genau das, was hier vermieden wird."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.json"
        p.write_text(json.dumps({"t": "Mönchengladbach"}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        K.kompakt(p)
        assert "Mönchengladbach" in p.read_text(encoding="utf-8")
        assert "\\u" not in p.read_text(encoding="utf-8")


def test_kaputte_dateien_bleiben_unangetastet():
    """Ein Normalisierer, der bei Zweifel schreibt, ist ein Datenverlust-Werkzeug."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.json"
        p.write_text('{"a": 1,,,', encoding="utf-8")
        assert K.kompakt(p) is None
        assert p.read_text(encoding="utf-8") == '{"a": 1,,,'


def test_eine_fehlende_datei_ist_kein_fehler():
    assert K.kompakt(Path("/gibt/es/nicht.json")) is None
    assert K.main(["/gibt/es/nicht.json"]) == 0
    assert K.main([]) == 0


def test_schon_kompakte_dateien_werden_nicht_angefasst():
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.json"
        p.write_text(json.dumps({"a": 1}, separators=(",", ":")), encoding="utf-8")
        mt = os.path.getmtime(p)
        assert K.kompakt(p) is None
        assert os.path.getmtime(p) == mt, "keine Schreiboperation, kein Commit"


@pytest.mark.parametrize("wf,dateien", sorted(WORKFLOWS.items()))
def test_jeder_workflow_normalisiert_vor_dem_stagen(wf, dateien):
    """⭐ Der eigentliche Wächter. Ein Schritt, der in drei von vier Workflows steht, wirkt
    nicht — der vierte schreibt die Datei beim naechsten Lauf wieder eingerueckt zurueck, und
    dann springt sie zwischen zwei Formaten. Fehlerklasse: eine Regel, die an mehreren Stellen
    steht und an einer fehlt."""
    q = (BASE / ".github" / "workflows" / wf).read_text(encoding="utf-8")
    assert "scripts/json_kompakt.py" in q, "%s normalisiert nicht" % wf
    aufruf = [z for z in q.splitlines() if "scripts/json_kompakt.py" in z][0]
    for d in dateien:
        assert d in aufruf, "%s: %s fehlt im Aufruf" % (wf, d)
    # und er muss VOR dem `git add` derselben Datei stehen
    i_kompakt = q.index("scripts/json_kompakt.py")
    i_add = q.index("git add %s" % dateien[0])
    assert i_kompakt < i_add, "%s: normalisiert erst nach dem Stagen" % wf


def test_jede_grosse_uebersichts_datei_wird_von_irgendwem_normalisiert():
    """Die Gegenrichtung: waechst eine neue schwere Datei in die Uebersicht hinein, faellt hier
    auf, dass sie niemand kompakt schreibt. Sonst holt sich die Seite die 3,85 MB langsam
    zurueck, ohne dass es jemand merkt."""
    import re
    js = (BASE / "main-dashboard.js").read_text(encoding="utf-8")
    m = re.search(r"return Promise\.all\(\[(.*?)\]\);", js, flags=re.DOTALL)
    block = "\n".join(z for z in m.group(1).splitlines() if not z.lstrip().startswith("//"))
    namen = [a or b for a, b in
             re.findall(r"jfSchlank\('([^']+)',\s*'[^']+'\)|jf\('([^']+)'\)", block)]
    alle_aufrufe = " ".join(
        z for wf in WORKFLOWS
        for z in (BASE / ".github" / "workflows" / wf).read_text(encoding="utf-8").splitlines()
        if "scripts/json_kompakt.py" in z)
    offen = []
    for n in namen:
        p = BASE / n
        if not p.exists():
            continue
        roh = p.read_bytes()
        if len(roh) < 500_000:
            continue                       # unter 0,5 MB lohnt der Schritt nicht
        try:
            kompakt = json.dumps(json.loads(roh.decode("utf-8")), ensure_ascii=False,
                                 separators=(",", ":")).encode("utf-8")
        except Exception:
            continue
        if len(roh) - len(kompakt) > 200_000 and n not in alle_aufrufe:
            offen.append("%s (%.2f MB Leerraum)" % (n, (len(roh) - len(kompakt)) / 1e6))
    assert not offen, (
        "diese Uebersichts-Dateien tragen viel Einrueckung und werden von keinem Workflow "
        "normalisiert: %s" % ", ".join(offen))


def test_am_echten_artefakt_schrumpft_es_messbar():
    p = BASE / "liga-data.json"
    if not p.exists():
        pytest.skip("kein liga-data.json im Arbeitsverzeichnis")
    roh = p.read_bytes()
    try:
        kompakt = json.dumps(json.loads(roh.decode("utf-8")), ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
    except Exception:
        pytest.skip("liga-data.json nicht lesbar")
    # Wenn der Workflow schon gelaufen ist, ist die Datei bereits kompakt — dann ist die
    # Ersparnis null, und das ist der Erfolgsfall, nicht ein Fehlschlag.
    assert len(kompakt) <= len(roh)
