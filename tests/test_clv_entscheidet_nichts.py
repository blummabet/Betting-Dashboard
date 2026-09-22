"""tests/test_clv_entscheidet_nichts.py — 22.09.2026

🔴 Lucas, ausdrücklich und nach eigener Angabe seit Wochen:

    „Ich habe es ja bei Polymarket gesagt, dieses CLV, das kickt Sachen raus. Den CLV von mir
     aus messe ihn, aber ich will, dass der nicht irgendwo irgendwie limitiert. Wir haben das
     Thema gehabt auch bei den Cards. Nur CLV ist leider nicht das Wichtige, und das sage ich
     jetzt schon seit Wochen. Wichtiger ist der Profit. Und siehst du, dann fliegen gute
     Wallets raus. Und ich bin mir sicher, dass wir das CLV-Problem woanders auch noch immer
     haben. Man kann es anzeigen, aber es darf kein Kriterium sein, dass irgendwas gekickt
     wird."

Er hatte an vier Stellen recht, und er hatte recht damit, dass es mehr als eine war. Die
Entscheidung war am 08.09. für das Freigabe-Register schon getroffen (`freigabe.py`: „Der CLV
blockiert nicht mehr, er BESCHREIBT") — auf der Polymarket-Seite wurde sie nie nachgezogen.
Das ist die Fehlerklasse hinter dem Ärger: **eine Entscheidung, die an einer Stelle umgesetzt
wird und an den anderen stehen bleibt.** Ein Test, der eine einzelne Stelle prüft, hätte das
nicht gefunden; dieser hier prüft die EIGENSCHAFT über alle Stellen.

Was die Zeilen gekostet haben, gemessen am Track vom 22.09.2026 (4.394 Wallets):
    sharp_gate.is_sharp besteht                     27
    ohne die eine CLV-Zeile                         48
    also NUR an CLV gescheitert                     21   davon 11 mit gemessenem 30-Tage-Profit,
                                                         zusammen +$176.456
Vorwärtsprobe (Auswahl an den Auflösungen 17.–19.09., gemessen an denen vom 20.–21.09.,
einsatzgewichtet):
    alle Wallets (Basisrate)      n=913   Folge-ROI  −3,8 %
    Ø CLV >= 0  (das alte Gate)   n=108   Folge-ROI −13,6 %
    Ø CLV <  0  (was es kickte)   n=119   Folge-ROI  −5,3 %
    Profit > 0 in der Auswahl     n=205   Folge-ROI  +4,4 %
Das Gate wählte die schlechtere Hälfte.

WAS DIESER TEST NICHT SAGT: dass CLV nichts misst. Er wird weiter gerechnet, gespeichert und
in jeder Spalte angezeigt — und `test_der_clv_wird_weiterhin_gemessen` hält genau das fest.
Ein „Kriterium entfernt" durch „Zahl gelöscht" zu ersetzen wäre der nächste Fehler.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Die Stellen, an denen CLV bis zum 22.09.2026 AUSGESCHLOSSEN hat. Jede Zeile nennt Datei,
# Suchmuster und den Vorfall — ein Guard ohne Vorfall ist eine Meinung.
VERBOTEN = [
    ("sharp_gate.py", r"if\s+avg_clv\s*<\s*0",
     "die eine Sharp-Definition; sie speist Dashboard, Push, Live-Watch und killer.py"),
    ("poly_whale_watch.py", r"avg_clv\s*>=\s*0\s*and",
     "der Schaerfe-Floor der Push-Rangliste"),
    ("poly_whale_watch.py", r"if\s+not\s*\(\s*ug\s+is\s+not\s+None\s+and\s+ug\s*>\s*0\s*\)",
     "das Tor des oeffentlichen Kanals (16.-22.09.)"),
    ("poly-wallets.js", r"\(sc\.avgClv\s*\|\|\s*0\s*\)\s*<\s*0",
     "der JS-Spiegel des Sharp-Gates"),
    ("poly-wallets.js", r"r\.avgClv\s*>=\s*PW_RANK_FLOOR_CLV",
     "der Schaerfe-Floor der Wallet-Rangliste"),
    ("poly_shortlist_track.py", r"avg\s+is\s+not\s+None\s+and\s+avg\s*>=\s*0",
     "der Wiedereintritt gesperrter Sportarten"),
]


@pytest.mark.parametrize("datei,muster,vorfall", VERBOTEN,
                         ids=[f"{d}:{v[:40]}" for d, _m, v in VERBOTEN])
def test_die_entfernten_clv_tore_bleiben_entfernt(datei, muster, vorfall):
    text = (ROOT / datei).read_text(encoding="utf-8")
    # Kommentare zaehlen nicht: sie BESCHREIBEN den Fehler, sie sind er nicht.
    code = "\n".join(z for z in text.splitlines()
                     if not z.lstrip().startswith(("#", "//")))
    treffer = re.search(muster, code)
    assert not treffer, (
        "CLV entscheidet wieder in %s (%s).\n"
        "Lucas, 22.09.2026: „Man kann es anzeigen, aber es darf kein Kriterium sein, dass "
        "irgendwas gekickt wird.\"\nGefunden: %r" % (datei, vorfall, treffer.group(0)))


def test_das_gate_laesst_negativen_clv_durch():
    """Die Eigenschaft, nicht die Schreibweise. Ein Muster-Test allein waere die Fehlerklasse
    „ein Waechter, der eine Schreibweise kennt statt einer Wirkung" — der hat uns hier schon
    einmal erwischt (test_public_ledger_fuehrung, 21.09.)."""
    import sharp_gate as SG
    belegt_mit_schlechtem_clv = {"n": 60, "wins": 40, "clvSumPP": -600.0, "pnl": 5000}
    assert SG.is_sharp(belegt_mit_schlechtem_clv) is True
    assert SG.sharp_grade(belegt_mit_schlechtem_clv) == 1.0
    # und der CLV veraendert das Ergebnis ueberhaupt nicht mehr
    for clv in (-600.0, -1.0, 0.0, 1.0, 600.0):
        s = {**belegt_mit_schlechtem_clv, "clvSumPP": clv}
        assert SG.is_sharp(s) is True, clv
        assert SG.sharp_grade(s) == 1.0, clv


def test_der_clv_wird_weiterhin_gemessen():
    """Die andere Haelfte der Anweisung: „von mir aus messe ihn". Ein Kriterium zu entfernen,
    indem man die Zahl loescht, waere der naechste Fehler — dann stuende nirgends mehr, was
    der Markt nach dem Einstieg getan hat."""
    import sharp_gate as SG
    n, wins, avg_clv, pnl = SG._felder({"n": 10, "wins": 6, "clvSumPP": -12.5, "pnl": 1})
    assert avg_clv == -1.25, "der Wert muss weiter herausfallen, auch wenn ihn niemand fragt"
    track = ROOT / "poly_wallet_track.json"
    if track.exists():
        sc = (json.loads(track.read_text(encoding="utf-8")) or {}).get("scores") or {}
        mit = sum(1 for v in sc.values() if isinstance(v, dict) and v.get("clvSumPP") is not None)
        assert mit > 0, "der Track schreibt keinen CLV mehr mit"


def test_der_clv_steht_weiterhin_auf_der_flaeche():
    js = (ROOT / "poly-wallets.js").read_text(encoding="utf-8")
    assert "CLV-UG" in js, "die Spalte muss bleiben — angezeigt, nicht entscheidend"
    assert "Ø CLV" in js


def test_was_an_die_stelle_getreten_ist_wirkt_auch():
    """Sonst waere das Tor nicht umgestellt, sondern abgeschafft."""
    import sharp_gate as SG
    gut = {"n": 60, "wins": 40, "clvSumPP": 60.0, "pnl": 5000}
    assert SG.is_sharp(gut) is True
    assert SG.is_sharp({**gut, "fenster30": {"gewinn": -1}}) is False
    assert SG.is_sharp({**gut, "fenster30": {"gewinn": 1}}) is True
    assert SG.is_sharp({**gut, "fenster30": {}}) is True, "nicht gemessen ist kein Verlust"


def test_die_freigabe_hat_es_seit_dem_08_09_richtig():
    """Der Praezedenzfall, auf den sich alles andere haette beziehen muessen. Bleibt er
    stehen, faellt beim naechsten Mal auf, dass die Regel eine Regel ist und keine
    Einzelentscheidung."""
    import freigabe
    quelle = (ROOT / "freigabe.py").read_text(encoding="utf-8")
    assert "Der CLV blockiert nicht mehr" in quelle
    assert hasattr(freigabe, "clv_urteil"), "das BESCHREIBENDE Feld muss es weiter geben"
