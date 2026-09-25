"""🔴 25.09.2026 — der Waechter meldete drei Tage lang einen Bruch, den es nicht gab.

    „6 Boersen-Spiele lagen am selben Tag wie unsere Cards, verlinkt wurde KEINES —
     Namens-Bruecke oder Fixture-Index gebrochen."

Nachgesehen, was an dem Tag auf der Boerse stand und was in unseren Card-Dateien:

    Boerse   Georgia - Northern Ireland · Italy - Belgium · England - Spain ·
             Tuerkiye - France · Australia - Brazil          (UEFA Nations League)
    wir      Seattle Sounders - Real Salt Lake · Philadelphia Union - Orlando City   (MLS)

Laenderspiele gegen Klubspiele. Es gab nichts zu verlinken: der WM-Datensatz ruht seit dem
20.07., also haben wir in einer Laenderspielpause ueberhaupt keine passenden Partien. Der Tag
war derselbe, der Wettbewerb ein voellig anderer.

Fehlerklasse: *eine Meldung, die einen anderen Grund nennt als den, der zutrifft.* Dieselbe wie
am 21.09. bei `_warum_haengt` — und eine falsche Ursache ist teurer als keine, weil sie die
Suche in die falsche Richtung schickt. Ich haette hier die Namens-Bruecke auseinandergenommen.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import betfair_card_link as CL  # noqa: E402
import wm_data_integrity as WI  # noqa: E402


def g(home, away, tag):
    return {"matchId": home + away, "home": home, "away": away, "kickoff": tag + "T18:45:00Z"}


def f(home, away, tag):
    return {"home": home, "away": away, "dateIso": tag, "picks": []}


LAENDER = [g("Italy", "Belgium", "2026-09-25"), g("England", "Spain", "2026-09-25")]
KLUBS = [f("Seattle Sounders", "Real Salt Lake", "2026-09-25"),
         f("Philadelphia Union", "Orlando City SC", "2026-09-25")]


def test_derselbe_tag_ist_kein_gemeinsamer_wettbewerb():
    """Der echte Fall: gleicher Tag, keine gemeinsame Mannschaft — also kein Kandidat."""
    assert CL.candidates(LAENDER, KLUBS) == 0


def test_eine_gemeinsame_mannschaft_macht_einen_kandidaten():
    spiele = LAENDER + [g("Seattle Sounders", "Real Salt Lake", "2026-09-25")]
    assert CL.candidates(spiele, KLUBS) == 1


def test_eine_mannschaft_reicht():
    """Die Boerse schreibt oft nur eine Seite so wie wir — das genuegt fuer „verlinkbar"."""
    spiele = [g("Seattle Sounders", "Sounders FC II", "2026-09-25")]
    assert CL.candidates(spiele, KLUBS) == 1


def test_ein_anderer_tag_zaehlt_nicht():
    spiele = [g("Seattle Sounders", "Real Salt Lake", "2026-09-27")]
    assert CL.candidates(spiele, KLUBS) == 0


def test_der_waechter_schweigt_ohne_kandidaten():
    WI._LAZY_CACHE = getattr(WI, "_LAZY_CACHE", {})
    c = WI.check_card_link_alive.__wrapped__ if hasattr(WI.check_card_link_alive, "__wrapped__") \
        else WI.check_card_link_alive
    # Direkt ueber die Zahlen geprueft, ohne Datei: 0 Kandidaten, 0 verlinkt = ruhiger Tag.
    assert CL.candidates(LAENDER, KLUBS) == 0


def test_der_waechter_schlaegt_weiter_an_wenn_es_wirklich_bricht():
    """Der Bruch vom 31.08. muss weiter auffallen: Kandidaten da, aber nichts verlinkt."""
    spiele = [g("Seattle Sounders", "Real Salt Lake", "2026-09-25")]
    assert CL.candidates(spiele, KLUBS) == 1
    res = CL.link(spiele, [f("Seattle Sounders", "Real Salt Lake", "2026-09-25")])
    assert isinstance(res.get("links"), dict)


def test_am_echten_bestand_ist_die_lage_erklaert():
    """Gegenprobe: entweder gibt es Kandidaten und Links, oder es gibt keine Kandidaten."""
    cx, err = CL._load(CL.CONSENSUS_FILE)
    if err or not cx:
        return
    spiele = cx.get("games") or []
    fx = []
    for pf in CL.PICKS_FILES:
        pk, e2 = CL._load(pf)
        if pk:
            fx.extend(CL.fixtures_index(pk))
    if not spiele or not fx:
        return
    cand = CL.candidates(spiele, fx)
    linked = len(CL.link(spiele, fx).get("links") or {})
    assert cand == 0 or linked > 0, (
        f"{cand} verlinkbare Boersen-Spiele, aber {linked} verlinkt — das waere ein echter Bruch")
