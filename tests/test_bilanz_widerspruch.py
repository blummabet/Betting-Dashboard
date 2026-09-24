"""🔴 24.09.2026 — zwei Zahlen nebeneinander, von denen eine geprueft ist.

`erzeugungs_bilanz` wurde am 22.09. gebaut, um zu entscheiden, ob GitHub die Laeufe eines
Workflows ueberhaupt erzeugt. Am 24.09. gegen die gemessene Kadenz gehalten:

    betfair         erzeugtProTag  6,6   ·  gemessene Kadenz 95,9/Tag   (Cron: 96)
    poly-global     erzeugtProTag  6,5   ·  gemessene Kadenz 47,9/Tag   (Cron: 48)
    poly-live-scan  erzeugtProTag  6,5   ·  gemessene Kadenz  5,1/Tag   (Cron: 96)

Die gemessene Kadenz trifft bei den beiden gesunden Workflows den Cron auf ein Prozent — sie
ist damit gegen zwei bekannte Wahrheiten geprueft. Die Bilanz liegt bei betfair um den Faktor
14 daneben und sitzt bei jedem schnellen Workflow auf ~6,6: sie ist gedeckelt. Warum, ist ohne
die Actions-API nicht zu klaeren — dass sie nicht stimmen kann, schon.

Fehlerklasse: eine Zahl, die einer besseren Messung daneben widerspricht und trotzdem als
Tatsache dasteht. Ausgerechnet die, die entscheiden sollte, ob ein Zeitplan feuert.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import run_health as R  # noqa: E402

BASE = pathlib.Path(__file__).resolve().parent.parent


def test_der_echte_betfair_fall_wird_markiert():
    b = R.bilanz_pruefen({"erzeugtProTag": 6.6}, 95.9)
    assert "widerspruch" in b
    assert "6.6" in b["widerspruch"] and "95.9" in b["widerspruch"]
    assert "NICHT als Beleg" in b["widerspruch"]


def test_wo_beide_zahlen_zusammenpassen_bleibt_sie_unmarkiert():
    assert "widerspruch" not in R.bilanz_pruefen({"erzeugtProTag": 5.0}, 4.2)
    assert "widerspruch" not in R.bilanz_pruefen({"erzeugtProTag": 2.6}, 2.8)


def test_die_zahl_wird_markiert_und_nicht_geloescht():
    """Geloescht waere sie nie zu reparieren — und der Deckel nie zu finden."""
    b = R.bilanz_pruefen({"erzeugtProTag": 6.5, "erzeugt": 100}, 47.9)
    assert b["erzeugtProTag"] == 6.5 and b["erzeugt"] == 100


def test_eine_alte_markierung_verschwindet_wenn_es_wieder_passt():
    b = R.bilanz_pruefen({"erzeugtProTag": 5.0, "widerspruch": "alt"}, 4.5)
    assert "widerspruch" not in b


def test_ohne_zahl_wird_nicht_geurteilt():
    """Fehlende Information ist kein Vorwurf — und kein Freispruch."""
    assert R.bilanz_pruefen(None, 10) is None
    assert "widerspruch" not in R.bilanz_pruefen({"erzeugtProTag": None}, 10)
    assert "widerspruch" not in R.bilanz_pruefen({"erzeugtProTag": 5.0}, None)
    assert "widerspruch" not in R.bilanz_pruefen({"erzeugtProTag": 0}, 10)


def test_die_gemessene_kadenz_trifft_ihren_cron_bei_den_gesunden():
    """Die Gegenprobe, die diese ganze Unterscheidung traegt: ist die Kadenz selbst geprueft?

    Ohne sie waere „die Bilanz widerspricht der Kadenz" nur der Streit zweier Zahlen, von
    denen keine belegt ist.
    """
    import datetime as dt
    erwartet = {"betfair": 96.0, "poly-global": 48.0}
    geprueft = 0
    for slug, soll in erwartet.items():
        f = BASE / "health" / f"{slug}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        ts = sorted((dt.datetime.fromisoformat(str(r["createdAt"]).replace("Z", "+00:00"))
                     for r in (d.get("runs") or []) if r.get("createdAt")), reverse=True)
        if len(ts) < 5:
            continue
        g = sorted((ts[i] - ts[i + 1]).total_seconds() / 60 for i in range(len(ts) - 1))
        ist = 1440.0 / g[len(g) // 2]
        assert abs(ist - soll) / soll < 0.10, (slug, ist, soll)
        geprueft += 1
    assert geprueft >= 1, "keine gesunde Referenz im Protokoll — die Kadenz ist ungeprueft"


def test_die_pruefung_wird_beim_schreiben_auch_angewandt():
    """Der Mutationstest hat den Aufruf ersatzlos entfernen lassen, ohne dass etwas rot wurde.

    Genau die Klasse, die in dieser Woche schon zweimal zugeschlagen hat: ein Befund, der
    gerechnet, aber nicht gezogen wird. Eine reine Funktion, die niemand aufruft, ist Deko.
    """
    src = (BASE / "run_health.py").read_text(encoding="utf-8")
    schreibteil = src.split("def bilanz_pruefen", 1)[1].split("\n\n\n", 1)[1]
    assert "bilanz_pruefen(" in schreibteil, "die Pruefung wird nirgends angewandt"
    assert 'bilanz = bilanz_pruefen(' in schreibteil, "ihr Ergebnis wird nicht uebernommen"
