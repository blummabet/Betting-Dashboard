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
    """„Italian Serie" passt auf A und B — dann wird nicht gewuerfelt.

    24.09.2026: der Grund hat sich verschoben, das Urteil nicht. Seit die Stufe zaehlt, faellt
    der Fall schon vorher: unsere Seite nennt keine Klasse, ihre nennt eine. Geprueft wird
    deshalb das Urteil und dass ueberhaupt ein Grund dafuer genannt wird — nicht die
    Formulierung. Ein Test, der Buchstaben prueft, meldet Umbauten statt Fehler."""
    v = A.vorschlagen("Italian Serie", SPORTS)
    assert v is not None
    assert v["urteil"] == "vorschlag", v
    assert v["warum"].strip()


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
    und zwei Kandidaten im selben Land heissen: nicht eintragen.

    24.09.2026: als zweiter Kandidat stand hier ein POKAL. Den sortiert die Art-Sperre jetzt
    schon aus, bevor es um Eindeutigkeit geht — besser, aber der Fall prueft dann nicht mehr,
    was er pruefen soll. Deshalb jetzt zwei echte Ligen desselben Landes."""
    zwei = SPORTS + [sp("soccer_ukraine_league", "Premier League - Ukraine")]
    v = A.vorschlagen("Ukrainian Premier League", zwei)
    assert v["urteil"] == "vorschlag", v
    assert "denselben" in v["warum"] or "eindeutig" in v["warum"], v["warum"]
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


# ── 🔴 24.09.2026, erster echter Lauf: 19 von 28 „sicheren" waren falsch ────────────────
# Die Tests oben waren gruen, weil ich nur die Faelle geprueft hatte, die mir eingefallen
# sind. Der Lauf gegen die echten 179 Wettbewerbe lieferte unter anderem:
#
#   "Polish Cup"                   -> soccer_poland_ekstraklasa       ein Pokal ist keine Liga
#   "Scottish Championship"        -> soccer_spl                      zweite gegen erste Klasse
#   "Argentinian Primera Nacional" -> soccer_argentina_primera_division   „primera" beweist nichts
#   "Japanese J League 2/3/Cup"    -> soccer_japan_j_league           fuenf Ligen, ein Schluessel
#   "Polish I Liga"                -> soccer_poland_ekstraklasa       I Liga ist Polens ZWEITE
#   "Scottish League One"          -> soccer_spl                      League One ist die DRITTE
#
# Haette Lucas die Liste eingetragen, haetten 19 Ligen still einen Anker auf die falsche Liga
# bekommen. Fehlerklasse: *eine Aehnlichkeit, die als Beweis zaehlt, obwohl sie das
# Unterscheidende gerade weglaesst.* Jeder dieser Faelle steht hier jetzt namentlich.

ECHT = [sp("soccer_poland_ekstraklasa", "Ekstraklasa - Poland"),
        sp("soccer_spl", "Premiership - Scotland"),
        sp("soccer_argentina_primera_division", "Primera División - Argentina"),
        sp("soccer_japan_j_league", "J League"),
        sp("soccer_italy_serie_a", "Serie A - Italy"),
        sp("soccer_italy_serie_b", "Serie B - Italy"),
        sp("soccer_greece_super_league", "Super League - Greece"),
        sp("soccer_spain_segunda_division", "La Liga 2 - Spain"),
        sp("soccer_france_ligue_two", "Ligue 2 - France"),
        sp("soccer_england_league1", "League 1"),
        sp("soccer_chile_campeonato", "Primera División - Chile"),
        sp("soccer_league_of_ireland", "League of Ireland")]


def _u(liga):
    v = A.vorschlagen(liga, ECHT)
    return (v or {}).get("urteil"), (v or {}).get("key"), (v or {}).get("warum", "")


def test_ein_pokal_ist_keine_liga():
    u, k, w = _u("Polish Cup")
    assert u == "vorschlag", (u, k, w)
    assert "andere Art" in w


def test_eine_stufe_im_namen_beweist_nichts():
    """„Primera Nacional" und „Primera División" teilen genau das Wort, das nichts sagt."""
    u, k, w = _u("Argentinian Primera Nacional")
    assert u == "vorschlag", (u, k, w)
    assert "nacional" in w.lower()


def test_eine_ordnungszahl_gegen_ein_schweigen_ist_eine_annahme():
    """Polens „I Liga" ist die zweite, Schottlands „League One" die dritte Klasse.
    Beide standen als sicher auf der jeweils ERSTEN."""
    for liga in ("Polish I Liga", "Scottish League One", "Irish Division 1"):
        u, k, w = _u(liga)
        assert u == "vorschlag", (liga, u, k, w)


def test_ihr_eigener_name_darf_unserem_nicht_widersprechen():
    u, k, w = _u("Polish I Liga")
    assert "ekstraklasa" in w.lower() or "Annahme" in w, w


def test_zweite_klasse_landet_nicht_auf_der_ersten():
    assert _u("Scottish Championship")[0] == "vorschlag"
    assert _u("Greek Super League 2")[0] == "vorschlag"
    assert _u("Chilean Primera B")[0] == "vorschlag"


def test_mehrdeutige_stufe_im_eigenen_namen_blockiert():
    """„Primera B" nennt zwei Klassen auf einmal — dann wird nicht geraten."""
    u, _, w = _u("Chilean Primera B")
    assert u == "vorschlag" and ("mehrdeutig" in w or "Spielklasse" in w or "Annahme" in w), w


def test_fuenf_ligen_ein_schluessel_ist_kein_sicherer_treffer():
    ligen = [{"liga": "Japanese J League", "n": 350},
             {"liga": "Japanese J League 2", "n": 270},
             {"liga": "Japanese Football League", "n": 111}]
    d = A.abgleich(ligen, {}, ECHT)
    sicher = [x for x in d["ohneAnkerMitKandidat"] if x["urteil"] == "sicher"]
    # 24.09.2026 stand hier `sicher == []`: alle drei sahen gleich gut aus, also durfte keine
    # gelten. 25.09.2026 unterscheidet Regel (3) sie — „J League 2" an der Stufe, „Japanese
    # Football League" daran, dass ihr Name das `j` der Gegenseite nicht nennt. Damit
    # beansprucht nur noch EINE den Schluessel, und die ist die richtige. Die alte Erwartung
    # war nicht falsch, sie war das Beste, was ohne diese Unterscheidung moeglich war.
    assert [x["liga"] for x in sicher] == ["Japanese J League"], \
        [(x["liga"], x["key"], x["warum"]) for x in sicher]
    assert all(x["key"] == "soccer_japan_j_league" for x in sicher)


def test_die_richtigen_ueberleben_den_umbau():
    """Schaerfer werden heisst nicht, alles wegzuwerfen — diese sieben sind echt."""
    for liga, key in (("Spanish Segunda Division", "soccer_spain_segunda_division"),
                      ("Italian Serie B", "soccer_italy_serie_b"),
                      ("French Ligue 2", "soccer_france_ligue_two"),
                      ("Greek Super League", "soccer_greece_super_league")):
        u, k, w = _u(liga)
        assert u == "sicher" and k == key, (liga, u, k, w)


def test_ziffern_werden_vom_namen_getrennt():
    """Ohne das steckt die Stufe in `league1` im selben Token wie der Name."""
    assert A._tokens("soccer_england_league1")[-2:] == ["league", "1"]
    assert A._stufe(["two"]) == A._stufe(["2"]) == {"t2"}


def test_ihr_name_allein_kann_widerlegen():
    """Der Fall, den erst die Mutationsprobe sichtbar gemacht hat.

    Wenn UNSER Name generisch ist, Art und Stufe passen und trotzdem nichts stimmt, bleibt
    nur ihr eigener Name als Einwand. „Ekstraklasa" heisst nun einmal Ekstraklasa — wer
    „Polish Premier League" darauf legt, hat es angenommen, nicht geprueft."""
    u, k, w = _u("Polish Premier League")
    assert u == "vorschlag", (u, k, w)
    assert "ekstraklasa" in w.lower(), w


def test_ein_schluessel_ohne_stufe_ist_die_oberste_klasse():
    """Ohne diese Annahme faellt „Greek Super League 2" gegen „Super League" nicht auf."""
    assert A._stufe(["super", "league"]) == {"t1"}
    assert A._stufe(["super", "league", "2"]) == {"t2"}


# ════════════════════════════════════════════════════════════════════════════════════
# 🔴 25.09.2026, ZWEITER echter Lauf. Von 7 „sicheren" war eine falsch und vier richtige
# fehlten. Beide Ursachen sassen in Regel (3) bzw. in der Zusammenschreibung.
# ════════════════════════════════════════════════════════════════════════════════════

def _s(key, titel, aktiv=True):
    return {"key": key, "title": titel, "active": aktiv}


JLEAGUE = _s("soccer_japan_j_league", "J League")


def test_kurzer_name_der_gegenseite_widerlegt_wieder():
    """„Japanese Football League" ist Japans VIERTE Liga und nennt keine Ordnungszahl. Weil
    der Kern von „J League" nur `j` ist und `len(t) > 2` das wegfilterte, fiel Regel (3)
    ganz aus — und die JFL stand als sichere Zuordnung auf der ersten Liga Japans."""
    urteil, warum = A.passt("Japanese Football League", JLEAGUE)
    assert urteil == "vorschlag", warum
    assert "nennt j" in warum


def test_kurzer_eigener_name_belegt_wieder():
    """Dieselbe Filterzeile schnitt in die andere Richtung: `k` und `mx` trafen unseren Namen
    exakt, wurden weggefiltert, und uebrig blieb nur die Klebeform, die nicht traf."""
    assert A.passt("South Korean K1 League",
                   _s("soccer_korea_kleague1", "K League 1"))[0] == "sicher"
    assert A.passt("Mexican Liga MX", _s("soccer_mexico_ligamx", "Liga MX"))[0] == "sicher"
    assert A.passt("Japanese J League", JLEAGUE)[0] == "sicher"


def test_zusammengeschrieben_ist_dasselbe_wort():
    """die-odds-api schreibt `superleague`, unser Feed „Super League"."""
    urteil, warum = A.passt("Swiss Super League",
                            _s("soccer_switzerland_superleague", "Swiss Superleague"))
    assert urteil == "sicher", warum
    assert "superleague" in warum


def test_klebeform_aus_lauter_allerweltswoertern_belegt_nichts():
    """Sonst waere „premierleague" gegen „premierleague" ein Kennwort — zweimal dasselbe
    Schweigen — und die Pruefung fuer namenlose Namen waere umgangen."""
    assert "premierleague" not in A._klebeformen(["premier", "league"])
    assert "superleague" in A._klebeformen(["super", "league"])
    assert "serieb" in A._klebeformen(["serie", "b"])


def test_klebeform_erfindet_keine_uebereinstimmung():
    """Nur BENACHBARTE Tokens werden verklebt, und nur zu 2er/3er-Gruppen."""
    k = A._klebeformen(["eerste", "divisie"])
    assert "eerstedivisie" in k and "eredivisie" not in k
    assert A.passt("Dutch Eerste Divisie",
                   _s("soccer_netherlands_eredivisie", "Dutch Eredivisie"))[0] == "vorschlag"


def test_namenloser_name_wird_von_regel_drei_gefangen_nicht_von_einer_extrasperre():
    """25.09.2026: ich hatte hier eine zweite Sperre eingebaut („ohne Kennwort UND ohne
    genannte Stufe"). Sie war ueberfluessig — Regel (3) fing „Japanese Football League"
    schon — und nahm dafuer richtige Zuordnungen weg. Der Test haelt beides fest: der
    namenlose Name faellt, der generische Treffer bleibt."""
    assert A.passt("Japanese Football League", JLEAGUE)[0] == "vorschlag"
    assert A.passt("Ukrainian Premier League",
                   _s("soccer_ukraine_premier_league", "Premier League - Ukraine"))[0] == "sicher"
    assert A.passt("Spanish Segunda Division",
                   _s("soccer_spain_segunda_division", "La Liga 2 - Spain"))[0] == "sicher"


def test_artikel_widerlegen_nicht():
    """Der Titel „La Liga 2 - Spain" brachte mit dem gefallenen Kurzwort-Filter ein `la` in
    ihren Kern — und haette die richtige Zuordnung der Segunda widerlegt."""
    assert "la" in A.RAUSCHEN and "de" in A.RAUSCHEN and "of" in A.RAUSCHEN
    assert A._kern(["la", "liga"]) == set()


def test_die_elf_zuordnungen_aus_dem_echten_lauf():
    """Die Liste, die Lucas eintragen soll — als Test, damit sie nicht still kippt.
    Jede Zeile ist von Hand gegen die Spielklasse des Landes geprueft."""
    fest = [
        ("Spanish Segunda Division", _s("soccer_spain_segunda_division", "La Liga 2 - Spain")),
        ("Swedish Superettan",       _s("soccer_sweden_superettan", "Superettan - Sweden")),
        ("Italian Serie B",          _s("soccer_italy_serie_b", "Serie B - Italy")),
        ("French Ligue 2",           _s("soccer_france_ligue_two", "Ligue 2 - France")),
        ("Greek Super League",       _s("soccer_greece_super_league", "Super League - Greece")),
        ("Chinese Super League",     _s("soccer_china_superleague", "Super League - China")),
        ("German Frauen-Bundesliga", _s("soccer_germany_bundesliga_women", "Frauen-Bundesliga")),
        ("Japanese J League",        JLEAGUE),
        ("Mexican Liga MX",          _s("soccer_mexico_ligamx", "Liga MX")),
        ("South Korean K1 League",   _s("soccer_korea_kleague1", "K League 1")),
        ("Swiss Super League",       _s("soccer_switzerland_superleague", "Swiss Superleague")),
    ]
    for liga, sport in fest:
        urteil, warum = A.passt(liga, sport)
        assert urteil == "sicher", "%s -> %s: %s" % (liga, sport["key"], warum)


def test_die_fallen_bleiben_gesperrt():
    """Alle Zeilen, die im ersten oder zweiten Lauf als „sicher" dastanden und falsch waren.
    Keine darf durch die Lockerung der Klebeformen zurueckkommen."""
    fallen = [
        ("Polish Cup",                   _s("soccer_poland_ekstraklasa", "Ekstraklasa - Poland")),
        ("Polish I Liga",                _s("soccer_poland_ekstraklasa", "Ekstraklasa - Poland")),
        ("Polish 2 Liga",                _s("soccer_poland_ekstraklasa", "Ekstraklasa - Poland")),
        ("Scottish Championship",        _s("soccer_spl", "Premiership - Scotland")),
        ("Scottish League One",          _s("soccer_spl", "Premiership - Scotland")),
        ("Scottish Challenge Cup",       _s("soccer_spl", "Premiership - Scotland")),
        ("Argentinian Primera Nacional", _s("soccer_argentina_primera_division",
                                            "Primera División - Argentina")),
        ("Japanese J League 2",          JLEAGUE),
        ("Japanese J League 3",          JLEAGUE),
        ("Japanese J League Cup",        JLEAGUE),
        ("Japanese Football League",     JLEAGUE),
        ("Turkish 1 Lig",                _s("soccer_turkey_super_league", "Turkey Super League")),
        ("Swedish Division 1",           _s("soccer_sweden_allsvenskan", "Allsvenskan - Sweden")),
        ("Norwegian 1st Division",       _s("soccer_norway_eliteserien", "Eliteserien - Norway")),
        ("Danish 1st Division",          _s("soccer_denmark_superliga", "Denmark Superliga")),
        ("Dutch Eerste Divisie",         _s("soccer_netherlands_eredivisie", "Dutch Eredivisie")),
        ("Chinese League 1",             _s("soccer_china_superleague", "Super League - China")),
        ("Chinese League 2",             _s("soccer_china_superleague", "Super League - China")),
        ("South Korean K2 League",       _s("soccer_korea_kleague1", "K League 1")),
        ("South Korean K3 League",       _s("soccer_korea_kleague1", "K League 1")),
        ("Italian Serie C",              _s("soccer_italy_serie_a", "Serie A - Italy")),
        ("Italian Serie C Cup",          _s("soccer_italy_serie_a", "Serie A - Italy")),
        ("Greek Super League 2",         _s("soccer_greece_super_league", "Super League - Greece")),
        ("Portuguese U23",               _s("soccer_portugal_primeira_liga",
                                            "Primeira Liga - Portugal")),
        ("Finnish Ykkosliiga",           _s("soccer_finland_veikkausliiga",
                                            "Veikkausliiga - Finland")),
        ("Saudi 1st Division",           _s("soccer_saudi_arabia_pro_league", "Saudi Pro League")),
        ("English National League",      _s("soccer_england_efl_cup", "EFL Cup")),
        ("English Sky Bet League 1",     _s("soccer_england_efl_cup", "EFL Cup")),
        ("English WSL",                  _s("soccer_england_efl_cup", "EFL Cup")),
    ]
    for liga, sport in fallen:
        urteil, warum = A.passt(liga, sport)
        assert urteil != "sicher", "%s -> %s kam als SICHER zurueck: %s" % (
            liga, sport["key"], warum)


def test_ersatzschreibweise_ist_kein_fund():
    """„Major League Soccer" feuert nie, aber `"US MLS"` daneben erreicht dasselbe Ziel. Am
    01.09. bewusst so entschieden — die Meldung machte daraus jeden Lauf einen Fund."""
    ligen = [{"liga": "US MLS", "n": 518}]
    zuo = {"US MLS": "soccer_usa_mls", "Major League Soccer": "soccer_usa_mls",
           "Ruritanian Liga": "soccer_ruritania_liga"}
    d = A.abgleich(ligen, zuo, [])
    assert d["eintraegeErsatzschreibweise"] == ["Major League Soccer"]
    assert d["eintraegeOhneLiga"] == ["Ruritanian Liga"], d["eintraegeOhneLiga"]
