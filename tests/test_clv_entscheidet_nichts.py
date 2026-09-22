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


# ── 22.09.2026 abends: derselbe Fehler eine Stufe hoeher ─────────────────────
# 🔴 Lucas: „Und sind die Whale-Pushes für Public richtig? Funktioniert da alles? Oder wo ein
# Problem?"
#
# Das Problem stand über dem CLV-Tor und ist dieselbe Klasse: **ein Kriterium, das etwas
# anderes misst als das, wonach entschieden wird.** `_is_confirmed_loser` im Public-Trichter
# fragte `pnl` — Polymarkets Lebensbilanz über Wahlen, Krypto UND Sport in einer Zahl.
#
# Gemessen am Track vom 22.09.2026, 1.562 offene Positionen:
#     als „bestätigter Verlierer" abgelehnt      527   (ein Drittel)
#     davon mit gemessenem 30-Tage-Sportprofit   504
#     davon im PLUS                              225
# Die größte: +$863.781 Sport in 30 Tagen (n=92), abgelehnt wegen −$2.420.880 Lebensbilanz.
# Dieselbe Wallet steht auf Rang 2 der Profit-Rangliste des Dashboards.
def test_der_sport_profit_schlaegt_die_plattform_bilanz():
    import sharp_gate as SG
    wallet = {"n": 60, "wins": 40, "clvSumPP": -30.0, "pnl": -2420880,
              "fenster30": {"gewinn": 863781, "einsatz": 3260000, "n": 92, "nGeld": 92}}
    assert SG.is_confirmed_loser(wallet) is False
    assert SG.is_sharp(wallet) is True
    assert SG.sharp_grade(wallet) == 1.0


def test_und_zwar_in_beide_richtungen():
    """Kein Aufweichen, ein Tausch. Am Track steigt die Zahl der abgelehnten Positionen von
    527 auf 639 — Wallets mit gemessenem Sport-VERLUST, die vorher durchkamen, weil ihre
    Lebensbilanz unbekannt war."""
    import sharp_gate as SG
    reich_im_falschen_markt = {"n": 60, "wins": 40, "clvSumPP": 120.0, "pnl": 3700000,
                               "fenster30": {"gewinn": -5000}}
    assert SG.is_confirmed_loser(reich_im_falschen_markt) is True
    assert SG.is_sharp(reich_im_falschen_markt) is False


def test_ohne_messung_bleibt_die_plattform_bilanz_der_notbehelf():
    """Die Abdeckung liegt bei 386 von 4.394 Wallets (9 %). Für die übrigen ändert sich
    nichts — „nicht gemessen" darf nicht zu „unbedenklich" werden."""
    import sharp_gate as SG
    assert SG.is_confirmed_loser({"n": 60, "wins": 40, "pnl": -1}) is True
    assert SG.is_confirmed_loser({"n": 60, "wins": 40}) is False
    assert SG.is_confirmed_loser({"n": 60, "wins": 40, "fenster30": {}}) is False
    assert SG.is_confirmed_loser({"n": 60, "wins": 40, "pnl": -1, "fenster30": {"gewinn": 0}}) is False, \
        "exakt 0 ist kein Verlust — und die Messung liegt vor, also gilt sie"


def test_es_gibt_nur_noch_EINE_verlierer_frage():
    """Vorher standen in `is_sharp` zwei Bedingungen nebeneinander, und die erste (`pnl`)
    konnte die zweite (Sport) überstimmen. Genau so entsteht die Klasse „eine Regel an zwei
    Stellen": wer den Vorrang ändert, ändert ihn an einer."""
    import inspect
    import sharp_gate as SG
    for fn in (SG.is_sharp, SG.sharp_grade):
        q = inspect.getsource(fn)
        assert "is_confirmed_loser(score)" in q, fn.__name__
        assert "pnl < 0" not in q, (
            "%s fragt die Lebensbilanz wieder selbst ab, statt die eine Definition zu "
            "benutzen" % fn.__name__)


def test_der_public_trichter_benutzt_dieselbe_definition():
    """poly_whale_watch._is_confirmed_loser delegiert — sonst hinge am oeffentlichen Kanal
    eine zweite Wahrheit."""
    import inspect
    import poly_whale_watch as P
    assert "SG.is_confirmed_loser" in inspect.getsource(P._is_confirmed_loser)
    assert "SG.is_sharp" in inspect.getsource(P._is_smart)


def test_am_echten_track_gibt_der_tausch_wallets_frei_und_sperrt_andere():
    import json
    import sharp_gate as SG
    p = ROOT / "poly_wallet_track.json"
    if not p.exists():
        pytest.skip("kein Track im Arbeitsverzeichnis")
    sc = (json.loads(p.read_text(encoding="utf-8")) or {}).get("scores") or {}
    nur_pnl = lambda v: isinstance(v.get("pnl"), (int, float)) and v["pnl"] < 0
    frei = [w for w, v in sc.items()
            if isinstance(v, dict) and nur_pnl(v) and not SG.is_confirmed_loser(v)]
    neu_gesperrt = [w for w, v in sc.items()
                    if isinstance(v, dict) and not nur_pnl(v) and SG.is_confirmed_loser(v)]
    assert frei, "der Tausch gibt niemanden frei — dann misst er nichts"
    assert neu_gesperrt, ("der Tausch sperrt niemanden zusaetzlich — dann ist es doch eine "
                          "reine Lockerung und nicht der Wechsel des Massstabs")


# ── 22.09.2026 abends, dritter Fund: der letzte CLV-Riegel im Haus ───────────
# 🔴 Lucas: „Kannst du den ganzen Betfair-Radar auch checken, ob wir da CLV so implementiert
# haben, dass es irgendwas blockt? Auch das Betfair-Terminal."
#
# Radar und Terminal: sauber — der CLV wird dort gemessen und angezeigt, jede Auswahl läuft auf
# der Rendite (das Terminal-Mute seit 04.09. auf `roiUg`).
#
# Das Freigabe-Register aber hatte im BETFAIR-Zweig noch den alten Riegel. Am 08.09.2026 wurde
# `bewerte()` auf die Rendite umgestellt (`CLV_BLOCKT` aus) — `betfair_schubladen()` nicht.
# Gemessen kostete das 12 Schubladen mit belegter Rendite-Untergrenze, darunter
# „Peruvian Primera Division · Half Time" mit +12,9 % Untergrenze über 32 Plays.
#
# Dieselbe Fehlerklasse wie überall heute: eine Entscheidung, die an einer Stelle umgesetzt
# wird und an den anderen stehen bleibt.
def test_der_betfair_zweig_blockt_nicht_mehr_auf_clv():
    quelle = (ROOT / "freigabe.py").read_text(encoding="utf-8")
    code = "\n".join(z for z in quelle.splitlines() if not z.lstrip().startswith("#"))
    for satz in ("ohne Untergrenze keine Freigabe",
                 "ohne den keine Freigabe",
                 "ohne CLV keine Freigabe"):
        assert satz not in code, "der CLV-Riegel steht wieder im Betfair-Zweig: %r" % satz


def test_eine_betfair_schublade_mit_belegter_rendite_wird_kandidat():
    """Und zwar Kandidat, nicht Freigabe. Der Riegel war falsch begründet, aber er hat zufällig
    etwas Richtiges verhindert: das Register prüft 407 Schubladen gleichzeitig, und der Zufall
    legt bei einseitigem 5-%-Band allein 20,4 davon über die Hürde — tatsächlich liegen 15
    drüber. Auf Einzel-Ebene überlebt keine eine Mehrfachtest-Korrektur (Bonferroni 0,
    Benjamini-Hochberg bei FDR 20 % ebenfalls 0)."""
    import freigabe as F
    eimer = {"n": 32, "roi": 0.763, "roiUg": 0.129, "hitRate": 0.56, "avgClvBf": 0.53,
             "nClvBf": 32}
    zeilen = F.betfair_schubladen({"byLeagueMarket": {"Peruvian Primera Division|Half Time": eimer}}) \
        if hasattr(F, "betfair_schubladen") else None
    if zeilen is None:
        pytest.skip("betfair_schubladen heisst anders")
    treffer = [z for z in zeilen if (z.get("n") or 0) == 32]
    assert treffer, "die Zeile wurde gar nicht gebaut"
    z = treffer[0]
    assert z["status"] == "kandidat", "belegte Rendite muss mindestens Kandidat sein"
    assert "CLV" not in (z.get("grund") or ""), \
        "der CLV darf die Begruendung nicht mehr tragen: %r" % z.get("grund")
    assert z.get("clv") == 0.53, "der CLV-Wert selbst muss auf der Zeile bleiben"


def test_der_mehrfachtest_befund_wird_gezogen_nicht_nur_gerechnet():
    """🔴 `ausbeute_ueber_huerde` gab es seit dem 20.09. und wurde von KEINER Stelle aufgerufen.
    Fehlerklasse: ein Befund, der gemeldet, aber nicht gezogen wird."""
    import inspect
    import freigabe as F
    q = inspect.getsource(F.baue)
    assert "ausbeute_ueber_huerde(" in q, "die Ausbeute wird nicht gerechnet"
    assert "mehrfachtest_nachziehen(" in q, "der Befund landet auf keiner Zeile"
    assert '"ausbeute"' in q, "die Zahl steht in keinem Artefakt"


def test_der_nachtrag_trifft_nur_die_belegten_kandidaten():
    """Ein Kandidat, dem schlicht Plays fehlen, hat mit Mehrfachtesten nichts zu tun — bekäme
    er den Satz, stünde auf 300 Zeilen eine Statistik, die sie nicht betrifft."""
    import freigabe as F
    zeilen = [{"schublade": "belegt", "status": "kandidat", "roiLb": 0.12, "n": 32},
              {"schublade": "zu duenn", "status": "kandidat", "roiLb": None, "n": 12,
               "grund": "12 von 30 Plays"},
              {"schublade": "negativ", "status": "kandidat", "roiLb": -0.04, "n": 40,
               "grund": "ROI nicht belegt"},
              {"schublade": "frei", "status": "freigegeben", "roiLb": 0.03, "n": 134,
               "grund": "ROI belegt"}]
    F.mehrfachtest_nachziehen(zeilen, {"nTests": 407, "erwartet": 20.4, "nUeber": 15,
                                       "ueberschuss": False})
    assert "gleichzeitig geprüften" in zeilen[0]["grund"]
    assert zeilen[0]["mehrfachtest"]["nTests"] == 407
    assert zeilen[1]["grund"] == "12 von 30 Plays"
    assert zeilen[2]["grund"] == "ROI nicht belegt"
    assert zeilen[3]["grund"] == "ROI belegt"
    assert "mehrfachtest" not in zeilen[3]


def test_ohne_ausbeute_zahl_wird_nichts_behauptet():
    import freigabe as F
    z = [{"schublade": "x", "status": "kandidat", "roiLb": 0.12, "n": 32, "grund": "vorher"}]
    F.mehrfachtest_nachziehen(z, {})
    assert z[0]["grund"] == "vorher", "ohne Zahl lieber gar kein Satz"
    F.mehrfachtest_nachziehen(z, None)
    assert z[0]["grund"] == "vorher"
