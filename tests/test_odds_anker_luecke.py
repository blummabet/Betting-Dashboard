"""🔴 24.09.2026 (Lucas, nach dem ScoutingStats-Check).

Gemessen, bevor irgendetwas gekauft wurde:

    verbraucht    419.770 Credits / 30 Tage (287 Messpunkte über 70 h)
    Tarif         5.000.000  →  8,4 % Auslastung, 4,58 Mio verfallen monatlich
    Anker         31 Einträge für 251 Ligen mit ≥30 Plays

Die Grenze ist keine Kosten-, sondern eine Pflegegrenze: die Tabelle stammt aus EINEM Abgleich
am 09.08.2026. Fehlerklasse: eine Abdeckung, die einmal erhoben und nie nachgezogen wurde.

Dieses Skript zählt die Lücke und schlägt Zuordnungen vor — und trägt bewusst nichts ein.
Eine falsche Zuordnung ist schlimmer als eine fehlende: der Anker zeigt dann auf die falsche
Liga, und der Konsens urteilt still über Spiele, die er nie gesehen hat.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import odds_anker_luecke as A  # noqa: E402


def sp(key, title, aktiv=True):
    return {"key": key, "title": title, "active": aktiv}


SPORTS = [
    sp("soccer_italy_serie_a", "Serie A - Italy"),
    sp("soccer_italy_serie_b", "Serie B - Italy"),
    sp("soccer_ukraine_premier_league", "Premier League - Ukraine"),
    sp("soccer_argentina_primera_division", "Primera División - Argentina"),
    sp("soccer_usa_mls", "MLS - USA"),
    sp("soccer_spain_segunda_division", "La Liga 2 - Spain"),
    sp("basketball_nba", "NBA"),
]


# ── Das Land ist die halbe Zuordnung ────────────────────────────────────────────────────

def test_eigenschaftswort_wird_zum_land():
    assert A.land_aus_liga("Ukrainian Premier League") == ("ukraine", ["premier", "league"])
    assert A.land_aus_liga("US MLS") == ("usa", ["mls"])
    assert A.land_aus_liga("South African Premier Division")[0] == "south_africa"


def test_ein_unbekanntes_eigenschaftswort_wird_gemeldet_nicht_geraten():
    """Genau daran ist der MLS-Eintrag jahrelang vorbeigelaufen — still."""
    land, _ = A.land_aus_liga("Other Competitions Soccer")
    assert land is None


# ── Wann ist eine Zuordnung sicher ──────────────────────────────────────────────────────

def test_land_und_kennwort_ist_sicher():
    u, w = A.passt("Italian Serie B", sp("soccer_italy_serie_b", "Serie B - Italy"))
    assert u == "sicher" and "italy" in w


def test_falsches_land_ist_gar_nichts():
    assert A.passt("Italian Serie B", sp("soccer_spain_segunda_division", "La Liga 2 - Spain"))[0] is None


def test_kein_fussball_ist_gar_nichts():
    assert A.passt("Italian Serie A", sp("basketball_nba", "NBA"))[0] is None


def test_land_allein_reicht_nur_fuer_einen_vorschlag():
    """Hier entstehen falsche Anker: das Land stimmt, der Wettbewerb ist ein anderer."""
    u, w = A.passt("Italian Coppa Cup", sp("soccer_italy_serie_a", "Serie A - Italy"))
    assert u == "vorschlag", (u, w)
    assert "ansehen" in w


def test_zwei_sichere_treffer_sind_kein_sicherer_treffer():
    """„Italian Serie" passt auf A und B — dann wird nicht gewuerfelt."""
    v = A.vorschlagen("Italian Serie", SPORTS)
    assert v is not None
    assert v["urteil"] == "vorschlag", v
    assert "nicht eindeutig" in v["warum"]


def test_ein_eindeutiger_treffer_bleibt_sicher():
    v = A.vorschlagen("Ukrainian Premier League", SPORTS)
    assert v["urteil"] == "sicher" and v["key"] == "soccer_ukraine_premier_league"


# ── Die Lücke selbst ────────────────────────────────────────────────────────────────────

LIGEN = [{"liga": "Ukrainian Premier League", "n": 162},
         {"liga": "Italian Serie B", "n": 90},
         {"liga": "Argentinian Primera Division", "n": 413},
         {"liga": "Other Competitions Soccer", "n": 362}]
ZUORDNUNG = {"Argentinian Primera Division": "soccer_argentina_primera_division",
             "Major League Soccer": "soccer_usa_mls"}


def test_die_luecke_wird_nach_groesse_sortiert():
    d = A.abgleich(LIGEN, ZUORDNUNG, SPORTS)
    assert [x["liga"] for x in d["ohneAnkerMitKandidat"]] == \
        ["Ukrainian Premier League", "Italian Serie B"]


def test_ein_eintrag_der_auf_keine_liga_passt_wird_gemeldet():
    """Der MLS-Fall vom 01.09.: eingebaut, feuert nie, sieht nach Abdeckung aus."""
    d = A.abgleich(LIGEN, ZUORDNUNG, SPORTS)
    assert d["eintraegeOhneLiga"] == ["Major League Soccer"]


def test_ohne_abfrage_wird_nicht_behauptet_es_gaebe_nichts():
    """Eine Meldung, die einen anderen Grund nennt als den, der zutrifft."""
    d = A.abgleich(LIGEN, ZUORDNUNG, [])
    assert d["sportsGefragt"] is False
    for x in d["ohneAnkerOhneKandidat"]:
        assert "nicht abgefragt" in x["warum"], x
        assert "kennt keine" not in x["warum"], x


def test_die_kosten_stehen_dabei():
    d = A.abgleich(LIGEN, ZUORDNUNG, SPORTS)
    assert d["creditsJeLigaMonat"] == 3 * 96 * 30
    assert d["creditsFuerAlleVorschlaege"] == d["creditsJeLigaMonat"] * len(d["ohneAnkerMitKandidat"])


def test_das_skript_traegt_nichts_ein():
    """Ein Vorschlag ist keine Zuordnung — das Skript darf betfair_consensus.py nicht anfassen."""
    src = (pathlib.Path(__file__).resolve().parent.parent / "odds_anker_luecke.py").read_text(encoding="utf-8")
    assert "LEAGUE_ODDS_KEY[" not in src
    assert "betfair_consensus.py" not in src.split('"""', 2)[-1] or "write_text" not in src.split("def main")[1].split("betfair_consensus")[0]
    for verboten in ("open(BASE / \"betfair_consensus.py\", \"w\")", "betfair_consensus.py\").write_text"):
        assert verboten not in src


def test_der_echte_bestand_hat_eine_luecke():
    """Gegenprobe am Artefakt — die Zahl, um die es geht."""
    import json
    f = pathlib.Path(__file__).resolve().parent.parent / "freigabe.json"
    if not f.exists():
        return
    import betfair_consensus as BC
    ligen = [r for r in (json.loads(f.read_text(encoding="utf-8")).get("ligen") or [])
             if isinstance(r, dict)]
    d = A.abgleich(ligen, BC.LEAGUE_ODDS_KEY, [])
    assert d["ligenGesamt"] > 200
    assert d["ligenGesamt"] - d["mitAnker"] > 100, "die Luecke waere zu — dann ist dieser Test fertig"


def test_ein_generischer_name_traegt_nur_wenn_er_eindeutig_ist():
    """„Premier League" besteht nur aus Allerweltswoertern. Dann entscheidet das Land —
    und zwei Kandidaten im selben Land heissen: nicht eintragen."""
    zwei = SPORTS + [sp("soccer_ukraine_cup", "Cup - Ukraine")]
    v = A.vorschlagen("Ukrainian Premier League", zwei)
    assert v["urteil"] == "vorschlag", v
    v2 = A.vorschlagen("Ukrainian Premier League", SPORTS)
    assert v2["urteil"] == "sicher"


def test_ein_abweichendes_kennwort_wird_nie_sicher():
    """Der teuerste Fehler waere ein Anker auf die falsche Liga desselben Landes."""
    u, _ = A.passt("Italian Serie C", sp("soccer_italy_serie_a", "Serie A - Italy"))
    assert u == "vorschlag"


def test_die_spielklasse_entscheidet_vor_der_aehnlichkeit():
    """Serie A und Serie C teilen alles ausser dem einen Zeichen, auf das es ankommt."""
    u, w = A.passt("Italian Serie C", sp("soccer_italy_serie_a", "Serie A - Italy"))
    assert u == "vorschlag" and "Spielklasse" in w
    u2, _ = A.passt("Italian Serie A", sp("soccer_italy_serie_a", "Serie A - Italy"))
    assert u2 == "sicher"


def test_spanische_zweite_liga_landet_nicht_auf_der_ersten():
    assert A.passt("Spanish Segunda Division",
                   sp("soccer_spain_la_liga", "La Liga - Spain"))[0] == "vorschlag"
    assert A.passt("Spanish Segunda Division",
                   sp("soccer_spain_segunda_division", "La Liga 2 - Spain"))[0] == "sicher"


def test_eine_stufe_nur_auf_einer_seite_blockiert_nicht():
    """„Ukrainian Premier League" gegen „Premier League - Ukraine": keine Stufe, kein Problem."""
    assert A.passt("Ukrainian Premier League",
                   sp("soccer_ukraine_premier_league", "Premier League - Ukraine"))[0] == "sicher"
