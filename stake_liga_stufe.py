#!/usr/bin/env python3
"""
stake_liga_stufe.py — welche Spielklasse eine Fussball-Liga ist
================================================================================
07.09.2026 (Lucas: „ne 50k Wette auf Arsenal sagt 0 / Eine 50k Wette auf ein 2-3. Liga Team /
Ist zumindest jemand der mehr dran glaubt mmn").

## Warum diese Tabelle von Hand kommt und nicht gelernt wird
Die Spielklasse steht in KEINEM Feld des Stake-Feeds. Aus den Daten laesst sie sich auch nicht
ableiten: der naheliegende Ersatz — „wie viele Wetten sieht diese Liga bei uns" — misst die
Marktgroesse, nicht die Klasse. Gemessen am 07.09. landen in der so gebildeten Gruppe „kleine
Liga" die Sueper Lig, die argentinische Primera, MLS, die Serie B Brasiliens und die englische
Championship. Das sind keine Randligen; das sind mittelgrosse Maerkte. Genau die Unterscheidung,
um die Lucas gebeten hat, faellt damit heraus.

Also: eine Tabelle Slug → Ebene. Sie ist WISSEN, keine Messung, und sagt das auch von sich
(`quelle: "Tabelle"`). Was nicht drinsteht, kommt als `None` zurueck — nicht als 1, nicht als
„sonstige". Eine unbekannte Liga darf nicht wie eine gemessene Spitzenliga aussehen; das ist
die Bug-Klasse „fehlende Information rendert als harmloser Default", die in diesem Repo schon
mehrfach zugeschlagen hat.

## Warum der Slug der Schluessel ist und nicht der Name
`ligaSlug` ist stabil, der Anzeigename nicht: derselbe Slug `superliga` erscheint im Ledger
als „Superliga" UND als „Primera LFP". Umgekehrt ist der Slug NICHT sportartenrein — unter
`bundesliga` laufen Fussball und Handball, unter `premier-league-srl` Fussball und Cricket.
Deshalb nimmt `stufe()` die Sportart entgegen und liefert ausserhalb von `soccer` nichts.

## Was gemessen wurde, bevor das hier gebaut wurde
3.512 abgerechnete Fussball-Einzelwetten aus vier Tagen, Einsatz gemessen als Vielfaches des
ueblichen Einsatzes derselben Liga (bzw. derselben Ebene, wo die Liga zu duenn ist):

    Ebene 1   <1.5x  n=2041  ROI  -2,1 %      Ebene 2+3   <1.5x  n=192  ROI  +7,5 %
              1.5-3x n= 596  ROI  -1,9 %                  1.5-3x n= 49  ROI  +5,9 %
              3-6x   n= 271  ROI  -8,0 %                  3-6x   n= 37  ROI +19,2 %
              >6x    n= 210  ROI -13,9 %                  >6x    n= 12  ROI +46,7 %

Beide Reihen sind monoton — und sie laufen in ENTGEGENGESETZTE Richtungen. In der obersten
Spielklasse wird ein grosser Einsatz mit steigender Groesse schlechter, darunter besser. Das
ist Lucas' Vermutung, und es ist zugleich die Begruendung dafuer, dass die bestehende
„Auffaellig"-Ansicht als Einheitsmass nicht funktionieren konnte: sie mischt beide Richtungen.

**Belegt ist davon nichts.** Alle Untergrenzen ausser einer liegen unter null, die
interessanten Zellen haben n=37 und n=12, die Schwellen sind NACH dem Blick auf die Zahlen
gewaehlt, und vier Tage sind vier Tage. Deshalb entstehen aus beiden Richtungen
vorregistrierte Schubladen (`randliga_hoher_einsatz`, `topliga_hoher_einsatz`), und das
Urteil faellt vorwaerts. Bis dahin ist das hier eine Anzeige, keine Empfehlung.
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict

# ── Die Tabelle ──────────────────────────────────────────────────────────────
# 1 = oberste Spielklasse des Landes, 2 = zweite, 3 = dritte und tiefer / regional / Amateur.
# Die Ebene beschreibt die KLASSE, nicht die Marktgroesse: die englische Championship ist
# Ebene 2, obwohl sie mehr Umsatz sieht als die Eliteserien (Ebene 1). Genau das ist der
# Unterschied, den die Volumen-Sicht nicht abbilden kann.
EBENE = {
    # ── oberste Spielklassen ───────────────────────────────────────────────
    "premier-league": 1, "la-liga": 1, "serie-a": 1, "bundesliga": 1, "ligue-1": 1,
    "primeira-liga": 1, "eredivisie": 1, "super-lig": 1, "brasileiro-serie-a": 1,
    "superliga": 1, "major-league-soccer": 1, "saudi-prof-league": 1, "j-league": 1,
    "primera-division": 1, "primera-division-apertura": 1, "primera-a-apertura": 1,
    "superligaen": 1, "eliteserien": 1, "allsvenskan": 1, "ekstraklasa": 1,
    "first-division-a": 1, "chinese-super-league": 1, "indonesian-super-league": 1,
    "k-league-1": 1, "ligapro-primera-a": 1, "super-league": 1, "super-league-1": 1,
    "premiership": 1, "prvaliga": 1, "nb-i": 1, "arabian-gulf-league": 1, "stars-league": 1,
    "1-liga": 1, "1st-division": 1, "liga-premier-serie-a": 1, "pfl": 1, "thai-league-1": 1,
    "i-liga": 1, "1-hnl": 1, "cymru-premier": 1, "virsliga": 1, "urvalsdeild": 1,
    "premier-soccer-league": 1, "omani-league": 1, "jordan-league": 1, "top-league": 1,
    "premier-division": 1, "prva-liga": 1, "divizia-nationala": 1, "premium-liiga": 1,
    "national-womens-soccer-league": 1, "first-professional-league": 1,
    "liga-nacional-apertura": 1, "cambodian-premier-league": 1, "pro-league": 1,
    "usl-championship": 1, "liga-i": 1, "iraqi-league": 1, "vysshaya-liga": 1,
    "division-profesional": 1, "liga-portugal": 1,
    # 13.09.2026 (CI-Wachhund): die Liga Panameña de Fútbol ist die OBERSTE Klasse Panamas;
    # „Apertura" ist die Halbsaison, kein Rang (wie bei primera-division-apertura oben).
    # Beleg aus der Paarung: Tauro FC — einer der Rekordmeister — gegen CD Universitario.
    "liga-panamena-de-futbol-apertura": 1,
    # 12.09.2026 (CI-Wachhund): „philippines-footb-league" — die Philippines Football League ist
    # die OBERSTE Klasse des Landes. Der abgeschnittene Slug („footb.") sieht nach Amateurstaffel
    # aus; das ist die Abkuerzung des Feeds, nicht der Rang.
    "philippines-footb-league": 1,
    # 08.09.2026 (CI-Wachhund): die finnische Spitze fehlte, waehrend „ykkonen" (2) und
    # „kolmonen" (3) darunter seit dem ersten Tag in der Tabelle stehen. Genau die Luecke,
    # die eine Tabelle ohne Wachhund jahrelang behaelt.
    "veikkausliiga": 1,
    # 09.09.2026 (CI-Wachhund, dritter Treffer des Tages): „mizoram-premier-league". Eine
    # indische STAATSliga — trotz „Premier" im Namen nicht die oberste Klasse des Landes
    # (das ist die ISL/I-League), sondern die Ebene darunter. Genau deshalb steht sie in der
    # TABELLE und nicht in einer Regel: „premier" im Namen sagt hier das Gegenteil dessen,
    # was ein Muster daraus lesen wuerde.
    "mizoram-premier-league": 3,
    # 10.09.2026 (CI-Wachhund, vierter und fuenfter Slug): „v-league" — die oberste Klasse
    # Vietnams (Ledger-Paarung „The Cong - Viettel FC - Cong An Ha Noi FC"). Der Slug ist
    # NICHT sportartenrein: in Korea und Japan heisst die Volleyball-Liga genauso. Dass hier
    # trotzdem eine „1" stehen darf, haelt allein `stufe()` fest, das ausserhalb von
    # `sport == "soccer"` grundsaetzlich None gibt — dieselbe Vorsichtsmassnahme, die schon
    # „bundesliga" (Fussball und Handball) braucht.
    "v-league": 1,
    # 10.09.2026 (CI-Wachhund): „erovnuli-liga" — Georgiens oberste Klasse. Reiner
    # Tabelleneintrag, der Slug traegt nichts, woraus eine Regel etwas ableiten koennte.
    "erovnuli-liga": 1,
    # ── zweite Spielklassen ────────────────────────────────────────────────
    "championship": 2, "2nd-bundesliga": 2, "la-liga-2": 2, "serie-b": 2, "ligue-2": 2,
    "j-league-2": 2, "brasileiro-serie-b": 2, "primera-b": 2, "k-league-2": 2,
    "eerste-divisie": 2, "segunda-liga": 2, "liga-de-expansion-mx-apertura": 2,
    "primera-nacional": 2, "ykkonen": 2, "challenge-league": 2, "ligapro-primera-b": 2,
    "thai-league-2": 2, "liga-2": 2, "fnl": 2, "segunda-division": 2, "pervaya-liga": 2,
    "mls-next-pro": 2, "1-lig": 2, "first-division-b": 2, "2nd-division": 2,
    # 10.09.2026 (CI-Wachhund): „superettan" — Schwedens ZWEITE Klasse, obwohl „super" im
    # Namen steht. Genau deshalb Tabelle und keine Regel: „super-lig", „super-league" und
    # „chinese-super-league" sind Ebene 1, „superettan" ist es nicht. Ein Muster auf „super"
    # wuerde vier richtige Eintraege kaputtmachen, um einen zu sparen.
    "superettan": 2,
    # 10.09.2026 (CI-Wachhund): „esiliiga" — Estlands ZWEITE Klasse. Die oberste steht seit
    # jeher als „premium-liiga" (Sponsorname der Meistriliiga) in der Tabelle; ohne diese Zeile
    # waere ausgerechnet die Liga darunter die einzige ohne Ebene.
    "esiliiga": 2,
    # 11.09.2026 (CI-Wachhund): „liga-nacional-de-ascenso" — Panamas ZWEITE Klasse (LNA, die
    # Aufstiegsliga unter der LPF). Tabelleneintrag und keine Regel: „ascenso" heisst in Mexiko
    # die zweite Liga, in anderen Verbaenden steht es im Namen der OBERSTEN. Ein Muster darauf
    # waere in der Haelfte der Faelle falsch.
    "liga-nacional-de-ascenso": 2,
    # ── dritte Klasse und tiefer, regional, Amateur ────────────────────────
    "league-one": 3, "league-two": 3, "3rd-liga": 3, "tercera-division": 3,
    # 12.09.2026: hier standen frueher `serie-c-group-a/-b/-c` und `tercera-division-group-7`
    # als eigene Zeilen. Die Gruppen kommen jetzt aus der Regel in `_ebene_aus_slug` — in der
    # Tabelle steht nur noch der RUMPF, und zwar genau einmal. Eine Staffel je Zeile war der
    # Grund, warum Gruppe 4 der Tercera (von achtzehn) wieder als Luecke auffiel.
    "serie-c": 3,
    "primera-c": 3, "primera-division-rfef": 3,
    "liga-portugal-3": 3, "tweede-divisie": 3, "national": 3, "national-league": 3,
    "liga-bet-south-a": 3, "shillong-second-divison": 3, "torneo-federal-a": 3,
    "kolmonen": 3, "primera-divisio": 3, "south-australia-state-league-1": 3,
    "nsw-premier-league-2": 3, "japan-football-league": 3, "second-division-b": 3,
    "usl-league-one": 3, "k3-league": 3,
    # 11.09.2026 (CI-Wachhund): „promotion-league" — die DRITTE Schweizer Klasse. Super League
    # (1) und Challenge League (2) stehen schon oben; ohne diese Zeile fehlte ausgerechnet die
    # Liga darunter. „promotion" im Namen meint den Aufstieg, nicht den Rang.
    "promotion-league": 3,
    "northern-territory-premier-league": 3, "npl-western-australia": 3,
    "npl-new-south-wales": 3, "npl-victoria": 3, "npl-queensland": 3,
    "npl-south-australia": 3, "npl-northern-new-south": 3, "npl-capital-football": 3,
    # 11.09.2026 (CI-Wachhund): „NPL 2, Victoria" — die Stufe UNTER `npl-victoria`, das hier
    # schon auf 3 steht. Die 3 ist in diesem Schema der Boden, tiefer geht die Skala nicht;
    # eine 4 zu erfinden waere eine Genauigkeit, die das Modell nicht traegt.
    "npl-2-victoria": 3,
    # 11.09.2026 (CI-Wachhund): „MFL, Division B". Der Name sagt nichts, die PAARUNG schon —
    # gebucht wurde darauf „Samara Kryliya Sovetov - PFK Sochi", zwei russische Erstligisten.
    # Ein Erstliga-Kader in einer „Division B" ist eine Reserve-/Nachwuchsrunde, kein
    # Erstliga-Spiel. Ebene 3, und ausdruecklich NICHT ueber die Reserve-Regel: die liest
    # Namensmuster (`-ii`, „reserve"), und „division-b" ist keines davon. Wer sie dafuer
    # aufbohrt, faengt beim naechsten Lauf jede zweite echte zweite Liga mit.
    "mfl-division-b": 3,
    # 11.09.2026 (CI-Wachhund): „Jordan 1st Division" — die ZWEITE Liga Jordaniens („1st
    # Division" steht dort unter der Premier League). Ein Ligenname mit „1" ist kein Beleg fuer
    # Ebene 1; entschieden hat die Paarung (Sama Al Sarhan - Jerash, beides Zweitligisten).
    "jordan-1st-division": 3,
    # „Division 1" ohne Land — Al-Dhaid gegen Dibba Al Fujairah, also die zweite Liga der VAE.
    # Der Slug ist so generisch, dass er in einer anderen Saison etwas anderes bezeichnen kann;
    # er steht hier trotzdem, weil der Wachhund sonst bei jedem Lauf erneut anschlaegt und die
    # Alternative (ein Rueckfall auf „unbekannt = Ebene 3") die Sperre unterlaufen wuerde.
    "division-1": 3,
    # 13.09.2026 (CI-Wachhund): „Division 2" — Wong Tai Sin gegen Sun Hei SC, also Hongkong.
    # Dort steht die Second Division unter Premier League (1) und First Division (2), ist also
    # die dritte Klasse. Wieder von Hand und nicht als Regel „division-N → Ebene N": in Jordanien
    # ist die „1st Division" die zweite Liga (steht drei Zeilen drueber), die Zahl im Namen sagt
    # ueber den Rang nichts. Entschieden hat auch hier die Paarung.
    "division-2": 3,
    # 12.09.2026 (CI-Wachhund): „Division Nationale" — die ERSTE Liga Luxemburgs (Kaerjeng gegen
    # Victoria Rosport). Oberste Spielklasse eines sehr kleinen Verbands: Ebene 2, nicht 1 — die
    # 1 ist in dieser Tabelle den europaeischen Topligen vorbehalten, nach deren Massstab hier
    # die Einsatzstufen haengen.
    "division-nationale": 2,
    # 12.09.2026 (CI-Wachhund): „First Division" ohne Land — Wexford gegen Finn Harps, also die
    # ZWEITE Liga Irlands (unter der Premier Division). „First" im Namen ist auch hier kein Beleg
    # fuer Ebene 1; entschieden hat die Paarung. Dritter Slug dieser Art nach „division-1" und
    # „jordan-1st-division" — die Quelle benennt zweite Ligen gern „First/1st Division".
    "first-division": 3,
    # 12.09.2026 (CI-Wachhund): „China League" — die ZWEITE Liga Chinas (China League One, unter
    # der Super League). Guandong GZ-Power gegen Dalian Kun City, beides Zweitligisten.
    "china-league": 3,
}

# Wettbewerbe, bei denen „Spielklasse" die falsche Frage ist. Sie bekommen eine eigene Marke
# statt einer Zahl — ein Pokalspiel gegen einen Drittligisten ist kein Drittliga-Spiel.
ART = {
    "uefa-champions-league": "kontinental", "uefa-europa-conference-league": "kontinental",
    "uefa-europa-league": "kontinental", "caf-champions-league": "kontinental",
    "caf-confederations-cup": "kontinental", "copa-libertadores": "kontinental",
    "copa-sudamericana": "kontinental", "leagues-cup": "kontinental",
    "copa-do-brasil": "pokal", "fa-cup": "pokal", "efl-cup": "pokal", "ofb-cup": "pokal",
    "coppa-italia": "pokal", "greece-cup": "pokal", "copa-uruguay": "pokal",
    "copa-paulista": "pokal", "dfb-pokal": "pokal", "copa-del-rey": "pokal",
}

# Nachwuchs, egal wie der Wettbewerb ihn schreibt: als Kuerzel irgendwo im Slug (u17..u23)
# oder ausgeschrieben. Wortgrenzen, damit „usl-championship" oder „u2" nichts ausloesen.
_JUGEND_RX = re.compile(r"\bu1[789]\b|\bu2[0-3]\b|youth|jugend|junior|academy|primavera")

# Reservemannschaften, in jeder Sprache, in der sie im Ledger auftauchen.
_RESERVE_RX = re.compile(r"reserv|riserv")

# Pokalwettbewerbe, die sich nicht „Cup" nennen. Wortgrenzen, damit „shield" in einem Vereinsnamen
# nicht die ganze Liga zum Pokal macht.
# 10.09.2026 (CI-Wachhund, „dbu-pokalen"): dieselbe Klasse wie „efl-trophy" und „reserva" —
# ein Pokal, den die Regel nicht als Pokal las. `s.endswith("-pokal")` fing die deutsche Form,
# aber im Skandinavischen haengt der bestimmte Artikel HINTEN an: „pokalen" ist „der Pokal".
# Gegenprobe an allen Fussball-Slugs des Ledgers: die breitere Regel beantwortet genau den
# einen offenen Slug und stuft keinen bereits eingestuften um.
_POKAL_RX = re.compile(
    r"(?:^|-)(?:trophy|shield|coupe|taca|kupa|kubok|beker|cupa|cupen"
    r"|pokal(?:en|et)?)(?:-|$)")

# Auszeichnungen und Langzeitwetten ohne Spielklasse. Wortgrenzen, damit „winner" in einem
# Marktnamen nicht ganze Ligen zu Auszeichnungen macht.
_AUSZEICHNUNG_RX = re.compile(
    r"(?:^|-)(?:ballon-dor|golden-boy|golden-boot|golden-ball|puskas|"
    r"player-of-the-year|team-of-the-year|top-scorer|award|awards)(?:-|$)")

# Mustererkennung fuer alles, was neu dazukommt. Sie ersetzt die Tabelle nicht, sie faengt
# nur die Faelle ab, bei denen der Slug die Antwort selbst mitbringt.
_MUSTER = (
    ("srl", lambda s: s.endswith("-srl") or "-srl-" in s),          # Simulated Reality League
    # 07.09.2026 — am Tag nach dem Bau tauchte „Primera Division Reserve, Clausura" auf und
    # stand als einzige Liga ohne Ebene da. Eine Reserveliga ist keine Spielklasse: es sind
    # zweite Mannschaften eines Vereins, die Aufstellung ist naeher an einer Jugendliga als
    # an der Liga, deren Namen sie traegt. Deshalb eine eigene Marke statt einer Zahl — und
    # als MUSTER, damit die naechste Reserveliga nicht wieder von Hand nachgetragen werden
    # muss.
    # 08.09.2026 (CI-Wachhund, „campeonato-de-reserva-de-primera-division-c"): die Regel las
    # nur die ENGLISCHE Schreibweise. Reserveligen heissen in Suedamerika „reserva", in
    # Italien „riserve" — dieselbe Sache, anderes Wort. Ein Muster, das nur eine Sprache
    # kennt, faellt bei jedem neuen Land wieder aus. Gegenprobe an den 171 Fussball-Slugs des
    # Ledgers: die breitere Regel beantwortet genau den einen offenen Slug und stuft keinen
    # bereits eingestuften um.
    ("reserve", lambda s: bool(_RESERVE_RX.search(s)) or s.endswith("-ii")),
    # 08.09.2026 (CI-Wachhund, „uefa-youth-league"): die Regel las nur die ERSTEN DREI
    # ZEICHEN, fing also „u19-…" und „u23-…", aber kein Wettbewerb, der seine Jugend im Namen
    # ausschreibt. Dieselbe Unterscheidung, die heute frueh `elf_marker` in betfair_consensus
    # bekommen hat: Nachwuchs ist eine andere Mannschaft, nicht eine Spielklasse.
    #
    # Die UEFA Youth League koennte man auch „kontinental" nennen — das waere nicht falsch,
    # aber die schwaechere Auskunft: fuer den Einsatz eines Highrollers verhaelt sich ein
    # U19-Spiel wie Nachwuchs und nicht wie ein Champions-League-Abend.
    #
    # Gegenprobe an den 170 Fussball-Slugs des Ledgers: die breitere Regel stuft KEINEN
    # bereits eingestuften Slug um; sie beantwortet genau einen, der vorher None war.
    ("jugend", lambda s: bool(_JUGEND_RX.search(s))),
    ("frauen", lambda s: ("women" in s or "femenina" in s or "feminin" in s
                          or "damallsvenskan" in s or "frauen" in s)),
    # 08.09.2026 (CI-Wachhund, „efl-trophy"): dieselbe Klasse wie „reserva" zwei Stunden vorher.
    # Die Regel kannte drei Woerter fuer „Pokal" — englisch, spanisch, deutsch. Ein Wettbewerb,
    # der sich Trophy, Shield, Coupe oder Taca nennt, ist derselbe Wettbewerbstyp und fiel durch.
    # Gegenprobe an den Fussball-Slugs des Ledgers: beantwortet genau den einen offenen Slug und
    # stuft keinen bereits eingestuften um.
    ("pokal", lambda s: (s.endswith("-cup") or s.startswith("copa-") or s.endswith("-pokal")
                         or bool(_POKAL_RX.search(s)))),
    # 09.09.2026 (CI-Wachhund, „ballon-dor"): und diesmal eine ANDERE Klasse als die drei
    # Treffer davor. „reserva", „efl-trophy" und „mizoram-premier-league" waren Wettbewerbe,
    # deren Ebene nur fehlte. Der Ballon d'Or ist gar kein Wettbewerb: „Ballon dor 2026 ·
    # Winner · Harry Kane" ist eine AUSZEICHNUNG mit einem Sieger, kein Spiel mit einer
    # Spielklasse. Eine Zahl dafuer waere erfunden — es gibt keine Liga, in der Harry Kane
    # den Ballon d'Or gewinnt.
    #
    # Deshalb eine eigene Marke und keine Ebene: die Zeile faellt damit nicht mehr aus der
    # Ansicht (das war der Grund fuer den Waechter), behauptet aber auch keine Spielklasse.
    ("auszeichnung", lambda s: bool(_AUSZEICHNUNG_RX.search(s))),
)

SPORT = "soccer"


def art(slug: str):
    """Wettbewerbsart, wo die Spielklasse nichts sagt — sonst None."""
    s = (slug or "").lower()
    if not s:
        return None
    if s in ART:
        return ART[s]
    for name, passt in _MUSTER:
        if passt(s):
            return name
    return None


# 07.09.2026 — der zweite Nachtrag in zwei Tagen („2nd-division-league", „super-league-2"),
# und beide Male stand die Antwort im Slug. Die Tabelle bleibt die Wahrheit fuer alles, was
# man WISSEN muss; diese Regeln lesen nur, was der Slug selbst sagt. Nicht geraten wird
# weiterhin alles andere: was hier nicht greift, bleibt None und faellt auf.
_ORDNUNGSZAHL = re.compile(r"^([2-9])(?:st|nd|rd|th)?-(?:division|liga|league|lig)\b")
_ANHANG = re.compile(r"^(.*)-([23])$")
# 12.09.2026 (CI-Wachhund, „tercera-division-group-4"). Zum ZWEITEN Mal eine Gruppe derselben
# Liga: `tercera-division-group-7` steht seit Tagen von Hand in der Tabelle, Gruppe 4 stand
# wieder ohne Ebene da — und die spanische Tercera hat achtzehn Gruppen. Eine Tabellenzeile je
# Gruppe ist die Instanz; die Klasse ist „eine Gruppe IST ihre Liga". Regionalstaffeln teilen
# eine Spielklasse per Definition, das muss niemand wissen, das sagt der Slug selbst.
_GRUPPE = re.compile(r"^(.*)-group-(?:\d{1,2}|[a-z])$")


def _ebene_aus_slug(s: str):
    """Ebene, wenn der Slug sie selbst nennt — sonst None.

    Zwei Faelle, beide nur mit Beleg im Namen:
      · „2nd-division-league", „3rd-liga"     → die Ordnungszahl steht vorne.
      · „super-league-2", „thai-league-2"     → der Anhang zaehlt die Klasse HOCH, und der
        Rumpf muss dafuer als oberste Klasse bekannt sein. Ohne diese Bedingung wuerde
        „serie-a-2" oder eine Gruppennummer stillschweigend zur zweiten Liga.
    """
    m = _ORDNUNGSZAHL.match(s)
    if m:
        return min(int(m.group(1)), 3)
    m = _ANHANG.match(s)
    if m and EBENE.get(m.group(1)) == 1:
        return int(m.group(2))
    # „…-group-4", „…-group-b" → die Ebene des Rumpfs, wenn der bekannt ist. Nur mit Rumpf in
    # der Tabelle: eine unbekannte Liga wird durch eine Gruppennummer nicht bekannter.
    m = _GRUPPE.match(s)
    if m and EBENE.get(m.group(1)):
        return EBENE[m.group(1)]
    return None


def stufe(slug: str, sport: str = SPORT):
    """'1' | '2' | '3' | 'kontinental' | 'pokal' | 'frauen' | 'jugend' | 'srl' — oder None.

    None heisst „nicht in der Tabelle" und muss auch so angezeigt werden. Der Slug ist NICHT
    sportartenrein (`bundesliga` = Fussball und Handball), deshalb die Sportart als Bedingung.
    """
    if (sport or "") != SPORT:
        return None
    a = art(slug)
    if a:
        return a
    s = (slug or "").lower()
    v = EBENE.get(s) or _ebene_aus_slug(s)
    return str(v) if v else None


def randliga(slug: str, sport: str = SPORT) -> bool:
    """Ebene 2 oder tiefer — das, was Lucas „2.-3. Liga" nennt."""
    return stufe(slug, sport) in ("2", "3")


# ── Referenzeinsatz ──────────────────────────────────────────────────────────
# Was ein normaler Einsatz ist, kommt aus stake_league_norm.json (wachsender Stand, keine
# Ledger-Momentaufnahme — die Begruendung steht im Kopf von stake_league_norm.py). Ligen
# unter dessen MIN_N haben dort KEINE Norm. Fuer genau die Ligen ist die Frage aber am
# interessantesten, deshalb der Rueckfall auf den Median der EBENE — nicht auf den globalen
# Median, denn der wird von Tennis und E-Sport getragen und hat mit Fussball nichts zu tun.
# Welcher der beiden Wege benutzt wurde, steht in jeder Zeile (`refBasis`).
EBENE_MIN_N = 15


def ebene_median(wetten: list) -> dict:
    """Median des Einsatzes je Ebene, aus den Fussball-Einzelwetten des Ledgers."""
    je = defaultdict(list)
    for w in wetten or []:
        if w.get("kombi") or not w.get("einsatzUsd"):
            continue
        st = stufe(w.get("ligaSlug"), w.get("sport"))
        if st:
            je[st].append(float(w["einsatzUsd"]))
    return {k: round(statistics.median(v), 2) for k, v in je.items() if len(v) >= EBENE_MIN_N}


def referenz(w: dict, norm: dict, ebmed: dict):
    """-> (referenzEinsatz, basis) oder (None, 'unbekannt').

    `norm` ist der Ligen-Block aus stake_league_norm.json, dort nach ANZEIGENAME verschluesselt.
    """
    st = stufe(w.get("ligaSlug"), w.get("sport"))
    if not st:
        return None, "unbekannt"
    n = (norm or {}).get(w.get("liga")) or {}
    if n.get("basis") == "gelernt" and n.get("median"):
        return float(n["median"]), "liga"
    m = (ebmed or {}).get(st)
    if m:
        return float(m), "ebene"
    return None, "unbekannt"


def faktor(w: dict, norm: dict, ebmed: dict):
    r, basis = referenz(w, norm, ebmed)
    e = w.get("einsatzUsd")
    if not r or not e:
        return None, basis
    return round(float(e) / r, 2), basis


# ── Was daraus fuer die Anzeige wird ─────────────────────────────────────────
# Die Schwellen stehen hier EINMAL. Wenn das Frontend sie noch einmal setzt, gibt es sie
# zweimal, und irgendwann sagt die eine Flaeche etwas anderes als die andere — die Klasse
# „ein Frontend baut Produzenten-Logik nach" hat dieses Repo schon mehrfach getroffen.
KAND_AB = 3.0          # ab diesem Vielfachen gilt ein Einsatz auf Ebene 2/3 als bemerkenswert
TOP_AB = 6.0           # das Gegenstueck auf Ebene 1 (dort ist die Reihe negativ)
STUFEN = [(1.5, "<1.5x"), (3.0, "1.5-3x"), (6.0, "3-6x"), (float("inf"), ">6x")]

# 07.09.2026 — feinere Baender fuer die Phase-Ansicht (live vs vor Anpfiff). Die grobe
# STUFEN-Liste bleibt, wie sie ist: sie traegt die Spielklasse-Tabelle, und eine Aenderung
# dort waere eine stille Aenderung an einer laufenden Messung. Der Grund fuer den Schnitt
# bei 15x: der Ausreisser-Schwanz verhaelt sich messbar anders als „3-6x", und in „>6x"
# verschwand er zwischen den ruhigen Faellen.
STUFEN_FEIN = [(1.5, "<1.5x"), (3.0, "1.5-3x"), (6.0, "3-6x"), (15.0, "6-15x"),
               (float("inf"), ">15x")]


def _bucket(f, stufen=None):
    for grenze, name in (stufen or STUFEN):
        if f < grenze:
            return name
    return (stufen or STUFEN)[-1][1]


def bucket(f, fein: bool = False):
    """Oeffentlich, damit niemand die Schwellen anderswo nachbaut."""
    return _bucket(f, STUFEN_FEIN if fein else STUFEN)


def kandidaten(wetten: list, norm: dict, ab: float = KAND_AB, max_n: int = 60) -> list:
    """Grosse Einsaetze auf Ebene 2/3 — die Zeilen, um die Lucas gebeten hat.

    Bewusst OHNE Ausgangsfilter: die Liste zeigt, was gesetzt wurde, nicht was aufging.
    Ob sie traegt, entscheidet die vorregistrierte Schublade, nicht diese Anzeige.

    07.09.2026 (Backlog: „Sortierung im Spielklasse-Reiter: aktuell nur nach Faktor. Nach
    Betrag waere die zweite sinnvolle Achse — wie ungewoehnlich vs. wie viel Geld").

    Der Deckel macht daraus mehr als eine Sortierfrage: eine Liste, die nach Faktor
    ABGESCHNITTEN ist, laesst sich nicht ehrlich nach Betrag sortieren — die groesste Summe
    des Tages kann bei Faktor 3,1 liegen und waere dann nie in der Auswahl. Deshalb ist die
    Auswahl jetzt die VEREINIGUNG der beiden Bestenlisten, und jede Zeile sagt in `warumDrin`,
    ueber welche sie hereingekommen ist. Sortiert wird danach in der Flaeche; die Auswahl
    haengt nicht mehr an der Sortierung.
    """
    ebmed = ebene_median(wetten)
    out = []
    for w in wetten or []:
        if w.get("kombi") or not w.get("einsatzUsd"):
            continue
        st = stufe(w.get("ligaSlug"), w.get("sport"))
        if st not in ("2", "3"):
            continue
        f, basis = faktor(w, norm, ebmed)
        if f is None or f < ab:
            continue
        a = w.get("abrechnung") or {}
        out.append({
            "id": w.get("id"), "ts": w.get("ts"),
            "liga": w.get("liga"), "ligaSlug": w.get("ligaSlug"), "ebene": st,
            "event": w.get("event"), "eventId": w.get("eventId"),
            "markt": w.get("markt"), "auswahl": w.get("auswahl"),
            "einsatzUsd": round(float(w["einsatzUsd"]), 2), "quote": w.get("quote"),
            "phase": w.get("phase"), "faktor": f, "refBasis": basis,
            "pnlUsd": a.get("pnlUsd"),
            "ausgang": ([b.get("status") for b in (a.get("beine") or [])] or [None])[0],
        })
    # Zwei Bestenlisten, je halber Deckel, dann vereinigt: so ist keine der beiden Achsen
    # von der anderen abhaengig. Ueberschneidung ist der Normalfall und kein Fehler — die
    # Zeile steht dann mit beiden Gruenden da.
    haelfte = max(1, max_n // 2)
    nach_faktor = sorted(out, key=lambda x: -x["faktor"])[:haelfte]
    nach_betrag = sorted(out, key=lambda x: -x["einsatzUsd"])[:haelfte]
    drin = {}
    for grund, liste in (("faktor", nach_faktor), ("betrag", nach_betrag)):
        for x in liste:
            z = drin.setdefault(id(x), x)
            z.setdefault("warumDrin", []).append(grund)
    aus = sorted(drin.values(), key=lambda x: -x["faktor"])
    return aus[:max_n]


def kreuz(wetten: list, norm: dict) -> dict:
    """Ebene × Einsatzgroesse, gemessen an den ABGERECHNETEN Einzelwetten.

    Zwei Zahlen je Zelle, und sie meinen Verschiedenes:
      · roi   — geldgewichtet: was der Fluss dort tatsaechlich verdient/verloren hat.
      · flach — jede Wette gleich schwer, dazu die einseitige 95%-Untergrenze. Nur die
                entscheidet; ein Punktschaetzer ist kein Beleg.
    """
    ebmed = ebene_median(wetten)
    zellen = defaultdict(lambda: {"n": 0, "einsatz": 0.0, "pnl": 0.0, "flach": [],
                                  "spiele": set()})
    for w in wetten or []:
        if w.get("kombi") or not w.get("einsatzUsd"):
            continue
        st = stufe(w.get("ligaSlug"), w.get("sport"))
        if not st:
            continue
        pnl = (w.get("abrechnung") or {}).get("pnlUsd")
        if pnl is None:
            continue
        f, _ = faktor(w, norm, ebmed)
        if f is None:
            continue
        z = zellen[(st, _bucket(f))]
        z["n"] += 1
        z["einsatz"] += float(w["einsatzUsd"])
        z["pnl"] += float(pnl)
        z["spiele"].add(w.get("eventId"))
        q = w.get("quote")
        if q and q > 1:
            z["flach"].append((q - 1) if pnl > 0 else -1.0)
    out = {}
    for (st, b), z in zellen.items():
        u = _untergrenze(z["flach"])
        o = _obergrenze(z["flach"])
        out.setdefault(st, {})[b] = {
            "n": z["n"], "spiele": len(z["spiele"]),
            "roi": round(z["pnl"] / z["einsatz"], 4) if z["einsatz"] else None,
            "flach": round(sum(z["flach"]) / len(z["flach"]), 4) if z["flach"] else None,
            "flachUg": round(u, 4) if u is not None else None,
            "flachOg": round(o, 4) if o is not None else None,
            "belegt": bool(u is not None and u > 0),
            # 07.09.2026 — eine Zelle kann auf zwei Arten etwas sagen, und die eine Grenze
            # taugt nur fuer eine davon. Folgen belegt die UNTERgrenze ueber null. Dagegen
            # halten belegt die OBERgrenze unter null; mit der Untergrenze allein waere die
            # Ebene-1-Reihe auf ewig „kein Urteil", obwohl sie genau die Aussage traegt,
            # um die es hier geht.
            "belegtGegen": bool(o is not None and o < 0),
        }
    return out


def _untergrenze(werte: list):
    """Einseitige 95%-Untergrenze des Mittelwerts (z=1,645). Unter n=UG_MIN_N: None.

    Der harte Boden ist derselbe wie ueberall im Projekt. Ohne ihn faellt eine Schublade mit
    n=2 und ROI +81% als „belegt" durch — das ist am 06.09. in der Freigabe passiert.
    """
    UG_MIN_N = 30
    n = len(werte or [])
    if n < UG_MIN_N:
        return None
    m = sum(werte) / n
    sd = (sum((v - m) ** 2 for v in werte) / (n - 1)) ** 0.5
    return m - 1.645 * sd / (n ** 0.5)


def _obergrenze(werte: list):
    """Das Gegenstueck: einseitige 95%-OBERgrenze. Unter demselben n-Boden: None."""
    UG_MIN_N = 30
    n = len(werte or [])
    if n < UG_MIN_N:
        return None
    m = sum(werte) / n
    sd = (sum((v - m) ** 2 for v in werte) / (n - 1)) ** 0.5
    return m + 1.645 * sd / (n ** 0.5)


def kreuz_phase(wetten: list, norm: dict, phase) -> dict:
    """Phase x Einsatzgroesse — dieselbe Rechnung wie `kreuz`, andere Zeilenachse.

    07.09.2026 (Lucas, Backlog: „Achse umstellen auf live x Einsatzgroesse statt auffaellig
    ja/nein"). Der Grund fuer die Umstellung ist gemessen: „auffaellig ja/nein" trennt
    nichts — die Trennung liegt zwischen live und vor Anpfiff und im aeussersten Band.

    `phase` wird hereingereicht (stake_analyse._phase), damit die Nachrechnung fuer alte
    Zeilen an EINER Stelle steht und nicht hier ein zweites Mal.
    """
    ebmed = ebene_median(wetten)
    zellen = defaultdict(lambda: {"n": 0, "einsatz": 0.0, "pnl": 0.0, "flach": [],
                                  "spiele": set()})
    for w in wetten or []:
        if w.get("kombi") or not w.get("einsatzUsd"):
            continue
        pnl = (w.get("abrechnung") or {}).get("pnlUsd")
        if pnl is None:
            continue
        f, _ = faktor(w, norm, ebmed)
        if f is None:
            continue
        b = _bucket(f, STUFEN_FEIN)
        ph = phase(w)
        for zeile in ({ph, "alle"} if ph in ("vor", "live") else {"alle"}):
            z = zellen[(zeile, b)]
            z["n"] += 1
            z["einsatz"] += float(w["einsatzUsd"])
            z["pnl"] += float(pnl)
            z["spiele"].add(w.get("eventId"))
            q = w.get("quote")
            if q and q > 1:
                z["flach"].append((q - 1) if pnl > 0 else -1.0)
    out = {}
    for (zeile, b), z in zellen.items():
        u = _untergrenze(z["flach"])
        o = _obergrenze(z["flach"])
        out.setdefault(zeile, {})[b] = {
            "n": z["n"], "spiele": len(z["spiele"]),
            "roi": round(z["pnl"] / z["einsatz"], 4) if z["einsatz"] else None,
            "flach": round(sum(z["flach"]) / len(z["flach"]), 4) if z["flach"] else None,
            "flachUg": round(u, 4) if u is not None else None,
            "flachOg": round(o, 4) if o is not None else None,
            "belegt": bool(u is not None and u > 0),
            "belegtGegen": bool(o is not None and o < 0),
        }
    return out


def block(wetten: list, norm: dict) -> dict:
    """Der komplette `randliga`-Block fuer stake_auswertung.json."""
    ebmed = ebene_median(wetten)
    je_ebene = defaultdict(int)
    for w in wetten or []:
        st = stufe(w.get("ligaSlug"), w.get("sport"))
        if st:
            je_ebene[st] += 1
    ohne = sorted({w.get("ligaSlug") for w in (wetten or [])
                   if (w.get("sport") == SPORT and w.get("ligaSlug")
                       and stufe(w.get("ligaSlug"), w.get("sport")) is None)})
    return {
        "abFaktor": KAND_AB,
        "topAbFaktor": TOP_AB,
        "ebeneMedian": ebmed,
        "jeEbene": dict(sorted(je_ebene.items())),
        "ohneEbene": ohne[:40],
        "nOhneEbene": len(ohne),
        "kandidaten": kandidaten(wetten, norm),
        "kandidatenAuswahl": ("Vereinigung der besten 30 nach Faktor und der besten 30 nach "
                              "Betrag — sonst haenge die Betrags-Sortierung an einer Liste, "
                              "die nach Faktor abgeschnitten wurde."),
        "kreuz": kreuz(wetten, norm),
        "warum": ("Die Spielklasse steht in keinem Feld des Feeds und laesst sich aus dem "
                  "Volumen nicht ableiten — nach Volumen gelten Sueper Lig, MLS und die "
                  "Championship als 'kleine Liga'. Sie kommt deshalb aus einer Tabelle "
                  "(stake_liga_stufe.py). Gemessen am 07.09. laufen die Reihen "
                  "gegenlaeufig: auf Ebene 1 wird der Fluss mit steigendem Einsatz "
                  "schlechter, auf Ebene 2/3 besser. Belegt ist das nicht — die "
                  "interessanten Zellen haben n=37 und n=12, und die Schwellen wurden nach "
                  "dem Blick auf die Zahlen gesetzt. Das Urteil faellt vorwaerts, in "
                  "randliga_hoher_einsatz und topliga_hoher_einsatz."),
    }
