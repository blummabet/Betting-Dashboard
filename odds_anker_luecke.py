"""Wie viele unserer Ligen könnten einen Pinnacle-Anker haben — und haben keinen.

🔴 24.09.2026 (Lucas, nach dem ScoutingStats-Check: „ich dachte, die Seite bietet mehr Daten,
die uns nützlich sein könnten"). Beim Nachrechnen kam heraus, dass die Daten, die uns fehlen,
längst bezahlt sind:

    verbraucht    419.770 Credits / 30 Tage   (gemessen, 287 Punkte über 70 h)
    Tarif         5.000.000                   →  Auslastung 8,4 %
    ungenutzt     4.580.000 Credits pro Monat, die jeden Monat verfallen

Der Anker deckt 31 Ligen ab. Unsere Ligen-Tafel führt 251 mit mindestens 30 Plays. Der Grund
für die 31 steht im Kopf von `betfair_consensus.py`: „Aus dem 09.08.2026-Abgleich". Die Tabelle
wurde einmal gebaut und nie wieder angefasst — die Grenze ist also keine Kosten-, sondern eine
Pflegegrenze. Eine zusätzliche Liga kostet 3 Regionen × 96 Läufe × 30 Tage = 8.640 Credits im
Monat; bei 4,58 Mio ungenutzten passen rund 530 davon hinein.

Fehlerklasse, die dieses Skript sichtbar macht: *eine Abdeckung, die einmal erhoben und nie
nachgezogen wurde.*

── Warum hier NICHTS automatisch eingetragen wird ──────────────────────────────────────
Eine falsche Zuordnung ist schlimmer als eine fehlende: der Anker zeigt dann auf die falsche
Liga, und der Konsens urteilt still über Spiele, die er nie gesehen hat. Deshalb schreibt
dieses Skript einen VORSCHLAG und niemals `LEAGUE_ODDS_KEY`. Ein Vorschlag ist keine Zuordnung.

── Die zweite Hälfte: Einträge, die nie feuern ─────────────────────────────────────────
Am 01.09.2026 (Lucas: „Pinnacle haben wir zu tausend Prozent der Spiele") stellte sich heraus:
`"Major League Soccer": "soccer_usa_mls"` stand seit jeher da — der Betfair-Feed schreibt aber
„US MLS". 105 MLS-Zeilen im Ledger, davon 0 mit Anker. Eingebaut, feuert aber nie, und auf dem
Papier sah es nach Abdeckung aus. Deshalb meldet dieses Skript auch die Gegenrichtung: welche
Einträge der Tabelle auf keinen einzigen Ligastring unseres Ledgers passen.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_FILE = BASE / "odds_anker_luecke.json"
API = "https://api.the-odds-api.com/v4"

# Credits, die eine zusätzliche Liga im Konsens-Takt kostet: Regionen × Läufe/Tag × 30.
REGIONEN = 3
LAEUFE_PRO_TAG = 96
CREDITS_JE_LIGA_MONAT = REGIONEN * LAEUFE_PRO_TAG * 30

# Betfair schreibt das Land als Eigenschaftswort, die-odds-api als Land im Schlüssel.
# Was hier fehlt, wird NICHT geraten, sondern als „Land nicht erkannt" gemeldet — genau daran
# ist der MLS-Eintrag jahrelang vorbeigelaufen.
LAND = {
    "english": "england", "scottish": "scotland", "welsh": "wales", "irish": "ireland",
    "spanish": "spain", "italian": "italy", "german": "germany", "french": "france",
    "portuguese": "portugal", "dutch": "netherlands", "belgian": "belgium",
    "austrian": "austria", "swiss": "switzerland", "danish": "denmark",
    "norwegian": "norway", "swedish": "sweden", "finnish": "finland",
    "polish": "poland", "czech": "czechia", "slovakian": "slovakia", "slovak": "slovakia",
    "hungarian": "hungary", "romanian": "romania", "bulgarian": "bulgaria",
    "greek": "greece", "turkish": "turkey", "russian": "russia", "ukrainian": "ukraine",
    "croatian": "croatia", "serbian": "serbia", "slovenian": "slovenia",
    "bosnian": "bosnia", "albanian": "albania", "israeli": "israel",
    "brazilian": "brazil", "argentinian": "argentina", "argentine": "argentina",
    "chilean": "chile", "colombian": "colombia", "peruvian": "peru",
    "uruguayan": "uruguay", "paraguayan": "paraguay", "bolivian": "bolivia",
    "ecuadorian": "ecuador", "venezuelan": "venezuela", "mexican": "mexico",
    "japanese": "japan", "chinese": "china", "korean": "korea", "australian": "australia",
    "indian": "india", "thai": "thailand", "vietnamese": "vietnam",
    "saudi": "saudi", "egyptian": "egypt", "moroccan": "morocco", "tunisian": "tunisia",
    "algerian": "algeria", "nigerian": "nigeria", "georgian": "georgia",
    "kazakh": "kazakhstan", "kazakhstan": "kazakhstan", "estonian": "estonia",
    "latvian": "latvia", "lithuanian": "lithuania", "icelandic": "iceland",
    "cypriot": "cyprus", "maltese": "malta", "armenian": "armenia",
    "azerbaijani": "azerbaijan", "belarusian": "belarus", "moldovan": "moldova",
    "us": "usa", "american": "usa", "canadian": "canada", "costa": "costa_rica",
    "south": None, "north": None,      # „South African" / „North …" braucht das zweite Wort
}
# Zusammengesetzte Eigenschaftswörter, die aus zwei Tokens bestehen.
LAND_PAARE = {
    ("south", "african"): "south_africa", ("south", "korean"): "korea",
    ("north", "american"): "usa", ("costa", "rican"): "costa_rica",
    ("new", "zealand"): "new_zealand", ("hong", "kong"): "hong_kong",
    ("united", "arab"): "uae",
}
# Wörter, die nichts über die Liga aussagen.
RAUSCHEN = {"the", "of", "league", "liga", "division", "divisie", "divisao", "premier",
            "professional", "football", "soccer", "campeonato",
            # 25.09.2026: Artikel und Praepositionen. Sie stehen in Titeln wie „La Liga 2 -
            # Spain" und „League of Ireland" und sagen ueber die Liga nichts. Sobald der
            # Kurzwort-Filter in Regel (3) faellt (s. unten), wuerde sonst ein „la" als
            # eigener Name gelten und eine richtige Zuordnung widerlegen.
            "la", "le", "el", "los", "las", "de", "del", "da", "do", "dos", "di", "du",
            "des", "and", "und", "en", "al"}

# 🔴 24.09.2026, erster echter Lauf: von 28 „sicheren" Zuordnungen waren rund zwei Drittel
# FALSCH — „Polish Cup" → Ekstraklasa, „Scottish Championship" → SPL, „Argentinian Primera
# Nacional" → Primera División, „Japanese J League 2/3/Cup" alle → J League. Haette Lucas die
# Liste eingetragen, haetten 19 Ligen still einen Anker auf die falsche Liga bekommen: genau
# der Fehler, den dieses Skript verhindern soll. Meine Tests waren gruen, weil ich nur die
# Faelle geprueft hatte, die mir eingefallen sind.
# Fehlerklasse: *eine Aehnlichkeit, die als Beweis zaehlt, obwohl sie das Unterscheidende
# gerade weglaesst.*
#
# Drei Unterscheidungen tragen jetzt, und alle drei koennen nur WIDERLEGEN:
#
# 1) Die Stufe. „Serie A" und „Serie C" unterscheiden sich in nichts ausser diesem Zeichen.
#    Geschrieben wird sie in vielen Formen (2 / two / II / B / Segunda) — deshalb auf eine
#    Normalform gebracht. Fehlt sie ganz, ist die oberste Klasse gemeint: ein Schluessel ohne
#    Stufe ist die erste Liga des Landes. Nur so faellt „Greek Super League 2" gegen
#    `soccer_greece_super_league` auf.
STUFE = {
    "1": "t1", "one": "t1", "i": "t1", "a": "t1", "primera": "t1", "primeira": "t1",
    "2": "t2", "two": "t2", "ii": "t2", "b": "t2", "segunda": "t2", "championship": "t2",
    "3": "t3", "three": "t3", "iii": "t3", "c": "t3", "tercera": "t3",
    "4": "t4", "d": "t4",
}
# 2) Die Art des Wettbewerbs. Ein Pokal ist keine Liga, eine Reserve-Mannschaft kein Verein.
#    „cup" stand in RAUSCHEN und verschwand damit spurlos — so wurde aus „Polish Cup" ein
#    Anker auf die Ekstraklasa.
ART = {
    "cup": "pokal", "cups": "pokal", "pokal": "pokal", "copa": "pokal", "coppa": "pokal",
    "coupe": "pokal", "beker": "pokal", "taca": "pokal", "trophy": "pokal",
    "kupa": "pokal", "kubok": "pokal", "shield": "pokal", "supercup": "pokal",
    "reserves": "reserve", "reserve": "reserve", "b2": "reserve",
    "u19": "nachwuchs", "u20": "nachwuchs", "u21": "nachwuchs", "u23": "nachwuchs",
    "youth": "nachwuchs", "junior": "nachwuchs", "juniors": "nachwuchs",
    "primavera": "nachwuchs", "development": "nachwuchs",
    "women": "frauen", "womens": "frauen", "ladies": "frauen", "femenina": "frauen",
    "feminine": "frauen", "frauen": "frauen",
    "friendly": "freundschaft", "friendlies": "freundschaft",
}


def _stufe(tokens) -> set:
    """Die Spielklassen in Normalform. Leer heisst: oberste Klasse."""
    return {STUFE[t] for t in tokens if t in STUFE} or {"t1"}


def _stufe_genannt(tokens) -> bool:
    """Steht die Stufe im Namen, oder ist sie nur angenommen?

    Der Unterschied entscheidet: ein Schluessel OHNE Stufe ist die oberste Klasse des Landes,
    ein Name MIT Ordnungszahl ist eine benannte Spielklasse — und die ist oft nicht die
    oberste. „Polish I Liga" ist Polens ZWEITE Liga, „Irish Division 1" Irlands zweite,
    „Scottish League One" Schottlands dritte. Alle drei standen im ersten Lauf als sicher auf
    der jeweiligen ERSTEN Liga. Eine Ordnungszahl gegen ein Schweigen ist keine
    Uebereinstimmung, sondern eine Annahme."""
    return any(t in STUFE for t in tokens)


def _art(tokens) -> set:
    return {ART[t] for t in tokens if t in ART}


def _tokens(s: str) -> list:
    """Zerlegt auch an der Grenze Buchstabe/Ziffer: `league1` -> ['league','1'].

    Ohne das steht die Stufe in `soccer_england_league1` in demselben Token wie der Name und
    ist nicht vergleichbar — und `ligue_two` gegen unser „Ligue 2" waere ein Widerspruch,
    obwohl es dieselbe Liga ist."""
    # Akzente zuerst wegnehmen: „Primera División" zerfiel sonst an dem ó zu „divisi"+„n",
    # und aus einem passenden Namen wurde ein Widerspruch.
    flach = unicodedata.normalize("NFKD", str(s).lower())
    flach = "".join(c for c in flach if not unicodedata.combining(c))
    roh = [t for t in re.split(r"[^a-z0-9]+", flach) if t]
    raus = []
    for t in roh:
        raus.extend(x for x in re.findall(r"[a-z]+|[0-9]+", t) if x)
    return raus


def _klebeformen(tokens) -> set:
    """Die Tokens plus die Zusammenschreibungen benachbarter Tokens.

    🔴 25.09.2026: die-odds-api schreibt zusammen, was unser Feed trennt —
    `superleague` gegen „Super League", `ligamx` gegen „Liga MX", `kleague1` gegen
    „K1 League". Ohne diese Formen widerlegt Regel (3) drei RICHTIGE Zuordnungen mit dem
    Satz „ihr Name nennt superleague, unserer nicht" — obwohl unserer genau das nennt, nur
    mit einem Leerzeichen darin.

    Nur BENACHBARTE Tokens werden verklebt, und die Einzelformen bleiben erhalten. Damit
    entsteht keine Uebereinstimmung, die nicht im Namen steht: „Eerste Divisie" wird
    `eerstedivisie` und trifft `eredivisie` weiterhin nicht.
    """
    t = [x for x in tokens]
    raus = set(t)
    for i in range(len(t) - 1):
        for j in (2, 3):
            if i + j > len(t):
                continue
            teile = t[i:i + j]
            # Eine Klebeform aus NUR Allerweltswoertern belegt nichts: „premierleague" gegen
            # „premierleague" ist zweimal dasselbe Schweigen. Mindestens ein Teil muss ein
            # eigenes Wort sein, sonst umgeht die Klebeform genau die Pruefung, die fuer
            # namenlose Namen gebaut ist (s. `_stufe_genannt` im Beweis-Schritt).
            if all(x in RAUSCHEN or x in STUFE or x in ART for x in teile):
                continue
            raus.add("".join(teile))
    return raus


def land_aus_liga(liga: str):
    """('ukraine', ['premier','league']) — oder (None, tokens), wenn das Land nicht erkannt ist. REIN."""
    t = _tokens(liga)
    if len(t) >= 2 and (t[0], t[1]) in LAND_PAARE:
        return LAND_PAARE[(t[0], t[1])], t[2:]
    if t and t[0] in LAND and LAND[t[0]]:
        return LAND[t[0]], t[1:]
    return None, t


def _kern(tokens) -> set:
    """Die Woerter, die eine Zuordnung BELEGEN koennen.

    Stufen- und Art-Woerter gehoeren nicht dazu: sie koennen widerlegen, nie beweisen. „Primera
    Nacional" und „Primera División" teilen „primera" — und sind zwei verschiedene Ligen."""
    return {t for t in tokens if t not in RAUSCHEN and t not in STUFE and t not in ART}


def passt(liga: str, sport: dict):
    """Wie gut passt ein /sports-Eintrag auf einen Betfair-Ligastring. REIN.

    -> (urteil, warum). urteil ∈ {"sicher", "vorschlag", None}.

    „sicher" verlangt BEIDES: dasselbe Land im Schlüssel UND mindestens ein gemeinsames
    Kennwort, das nicht Rauschen ist. Alles andere ist höchstens ein Vorschlag — und ein
    Vorschlag wird nie eingetragen, sondern angesehen.
    """
    key = str(sport.get("key") or "")
    if not key.startswith("soccer_"):
        return None, "kein Fußball"
    land, rest = land_aus_liga(liga)
    ktoks = _tokens(key[len("soccer_"):])
    titel = _tokens(sport.get("title") or "")
    if land is None:
        return None, "Land nicht erkannt — Eigenschaftswort fehlt in LAND"
    if land not in ktoks and land not in titel:
        return None, "anderes Land"
    ihre = set(ktoks) | set(titel)
    unser = _kern(rest)
    # ── Erst widerlegen, dann belegen ───────────────────────────────────────────────────
    # (1) Die Art: ein Pokal ist keine Liga.
    au, ai = _art(rest), _art(ktoks) | _art(titel)
    if au != ai:
        nur_wir, nur_sie = au - ai, ai - au
        return "vorschlag", ("Land %s, aber andere Art (%s) — ansehen"
                             % (land, " / ".join(filter(None, [
                                 "wir: " + "+".join(sorted(nur_wir)) if nur_wir else "",
                                 "sie: " + "+".join(sorted(nur_sie)) if nur_sie else ""]))))
    # (2) Die Stufe. Fehlt sie, ist die oberste gemeint — nur so faellt „Super League 2"
    #     gegen „Super League" auf.
    su, si = _stufe(rest), _stufe(ktoks) | _stufe(titel)
    if len(su) > 1:
        return "vorschlag", ("Land %s, aber mehrdeutige Spielklasse (%s) — ansehen"
                             % (land, "/".join(sorted(su))))
    if not (su & si):
        return "vorschlag", ("Land %s, aber andere Spielklasse (%s gegen %s) — ansehen"
                             % (land, "/".join(sorted(su)), "/".join(sorted(si))))
    if _stufe_genannt(rest) != _stufe_genannt(ktoks + titel):
        return "vorschlag", ("Land %s, aber eine Seite NENNT ihre Spielklasse und die andere "
                             "nicht — eine Ordnungszahl gegen ein Schweigen ist eine Annahme, "
                             "keine Uebereinstimmung. Ansehen." % land)
    # (3) Ihr eigener Name darf unserem nicht widersprechen: heisst ihre Liga „Ekstraklasa"
    #     und unsere „I Liga", ist das kein Schweigen, sondern ein anderer Name.
    # 🔴 25.09.2026, zweiter echter Lauf: hier stand `len(t) > 2`. Dieselbe Fehlerklasse
    # wie einen Tag vorher in `stake_burst_push` — *ein Filter, der das Unterscheidende
    # wegwirft, weil es kurz ist* — und hier schnitt er in BEIDE Richtungen:
    #   • „J League" hat als Kern nur `j`. Weggefiltert war ihr_kern leer, die Regel fiel
    #     ganz aus, und „Japanese Football League" (Japans VIERTE Liga, im Namen keine
    #     Ordnungszahl) stand als sichere Zuordnung auf `soccer_japan_j_league`.
    #   • „K League 1" -> `k`, „Liga MX" -> `mx`: beide trafen unseren Namen exakt, wurden
    #     aber weggefiltert, sodass nur die Klebeform (`kleague`, `ligamx`) uebrigblieb —
    #     und die traf nicht. Zwei richtige Zuordnungen fielen an ihrem eigenen Beweis.
    # Kurze Woerter sind in Liganamen genau die unterscheidenden: j, k, mx, us. Was hier
    # wirklich nicht traegt, sind Artikel und Ordnungszahlen — und die stehen in RAUSCHEN
    # bzw. STUFE.
    ihr_kern = {t for t in _kern(ktoks) | _kern(titel) if t != land}
    unser_vgl = _klebeformen(rest)
    if ihr_kern and not (_klebeformen(ihr_kern) & unser_vgl):
        return "vorschlag", ("Land %s, aber ihr Name nennt %s, unserer nicht — ansehen"
                             % (land, "/".join(sorted(ihr_kern))))
    # ── Jetzt erst belegen ──────────────────────────────────────────────────────────────
    # Verglichen wird auf den GEORDNETEN Tokens, nicht auf dem Kern: die Klebeform entsteht
    # aus der Nachbarschaft, und ein Kern ist eine Menge ohne Reihenfolge. („Swiss Super
    # League" -> `superleague` gibt es nur, solange `super` und `league` benachbart sind.)
    beiden = unser_vgl & _klebeformen(list(ktoks) + list(titel))
    gemeinsam = {t for t in beiden
                 if t not in RAUSCHEN and t not in STUFE and t not in ART and t != land}
    if gemeinsam:
        return "sicher", "Land %s + Kennwort %s" % (land, "/".join(sorted(gemeinsam)))
    if not unser:
        # „Ukrainian Premier League" besteht nur aus Allerweltswoertern — da KANN es kein
        # gemeinsames Kennwort geben. Dann tragen Land, Art und Stufe allein, und ob das
        # reicht, entscheidet die Eindeutigkeit: `vorschlagen` stuft zurueck, sobald ein
        # zweiter Kandidat im selben Land steht.
        # 25.09.2026, VERWORFEN: hier stand kurz eine Sperre „Name ohne Kennwort UND ohne
        # genannte Stufe ist kein Beweis". Sie sollte „Japanese Football League" fangen — den
        # fing aber schon Regel (3), sobald deren Kurzwort-Filter weg war. Was sie zusaetzlich
        # traf, waren RICHTIGE Zuordnungen: „Ukrainian Premier League" gegen
        # `soccer_ukraine_premier_league` wurde zum Vorschlag. Drei bestehende Tests wurden
        # davon rot, und sie hatten recht. Eine Sperre, die nichts Neues widerlegt und dafuer
        # Richtiges wegnimmt, gehoert nicht ins Haus — die Eindeutigkeitspruefung in
        # `vorschlagen`/`abgleich` deckt den Rest dieses Zweigs ab.
        return "sicher", "Land %s, Stufe %s, Name ohne eigenes Kennwort" % (land, "/".join(su))
    # Unsere Seite hat ein eigenes Kennwort, und es kommt drueben nicht vor — „Primera
    # NACIONAL" gegen „Primera División". Genau hier entstehen falsche Anker.
    return "vorschlag", ("Land %s, Stufe passt, aber unser Kennwort %s kommt drueben nicht vor "
                         "— ansehen" % (land, "/".join(sorted(unser))))


def vorschlagen(liga: str, sports: list):
    """Bester Kandidat für eine Liga. REIN. -> {key, titel, urteil, warum} oder None."""
    treffer = []
    for s in sports or []:
        u, w = passt(liga, s)
        if u:
            treffer.append({"key": s.get("key"), "titel": s.get("title"),
                            "aktiv": bool(s.get("active")), "urteil": u, "warum": w})
    if not treffer:
        return None
    treffer.sort(key=lambda t: (t["urteil"] != "sicher", not t["aktiv"], t["key"] or ""))
    bester = treffer[0]
    if len(treffer) > 1:
        bester = dict(bester)
        bester["weitere"] = [t["key"] for t in treffer[1:4]]
        if bester["urteil"] == "sicher" and treffer[1]["urteil"] == "sicher":
            # Zwei sichere Treffer sind kein sicherer Treffer.
            bester["urteil"] = "vorschlag"
            bester["warum"] += " — ABER mehrere Kandidaten, nicht eindeutig"
    return bester


def abgleich(ligen: list, zuordnung: dict, sports: list) -> dict:
    """Die ganze Lücke. REIN.

    `ligen`: [{"liga","n",...}] aus freigabe.json. `zuordnung`: LEAGUE_ODDS_KEY.

    Ohne abgerufene `sports` wird NICHT behauptet, die-odds-api kenne nichts dazu — dann
    wurde sie schlicht nicht gefragt. Eine Meldung, die einen anderen Grund nennt als den,
    der zutrifft, hat hier schon einmal in die falsche Richtung suchen lassen
    (s. `_warum_haengt` in poly_data_integrity, 21.09.2026).
    """
    gefragt = bool(sports)
    namen = {str(r.get("liga")) for r in (ligen or []) if isinstance(r, dict) and r.get("liga")}
    ohne, unbekannt = [], []
    for r in sorted((x for x in (ligen or []) if isinstance(x, dict)),
                    key=lambda x: -(x.get("n") or 0)):
        liga = str(r.get("liga") or "")
        if not liga or liga in zuordnung:
            continue
        v = vorschlagen(liga, sports)
        eintrag = {"liga": liga, "n": r.get("n"), "roi": r.get("roi"), "roiLb": r.get("roiLb")}
        if v:
            eintrag.update(v)
            ohne.append(eintrag)
        else:
            land, _ = land_aus_liga(liga)
            if not gefragt:
                eintrag["warum"] = "nicht abgefragt — ohne API-Schluessel keine Kandidaten"
            elif land is None:
                eintrag["warum"] = "Land nicht erkannt"
            else:
                eintrag["warum"] = "die-odds-api kennt keine Liga in %s dazu" % land
            unbekannt.append(eintrag)
    # (4) Beanspruchen MEHRERE unserer Ligen denselben Schlüssel, kann höchstens eine recht
    #     haben — welche, entscheidet hier niemand. Im ersten echten Lauf zeigten „Japanese
    #     J League", „J League 2", „J League 3", „J League Cup" und „Japanese Football League"
    #     alle auf `soccer_japan_j_league`, und alle fünf standen als „sicher" da.
    from collections import Counter
    beansprucht = Counter(x["key"] for x in ohne if x.get("urteil") == "sicher")
    for x in ohne:
        if x.get("urteil") == "sicher" and beansprucht[x["key"]] > 1:
            x["urteil"] = "vorschlag"
            x["warum"] += (" — ABER %d unserer Ligen beanspruchen denselben Schlüssel"
                           % beansprucht[x["key"]])

    # Gegenrichtung: Einträge, die auf keinen Ligastring des Ledgers passen (MLS-Fall 01.09.).
    #
    # 🔴 25.09.2026: hier stand nur EINE Liste, und „Major League Soccer" stand darin — obwohl
    # `"US MLS": "soccer_usa_mls"` zwei Zeilen darueber steht und feuert. Am 01.09. wurde
    # ausdruecklich entschieden, BEIDE Schreibweisen stehen zu lassen („ein Key, der nie
    # trifft, schadet nicht, ein fehlender schon"). Die Meldung machte aus dieser Entscheidung
    # jeden Lauf erneut einen Fund — und wer ihr nachgeht, sucht eine Abdeckungsluecke, die es
    # nicht gibt. Eine zweite Schreibweise neben einer feuernden ist ein ERSATZSCHLUESSEL,
    # keine Luecke.
    # Fehlerklasse: *eine Meldung, die eine bewusste Entscheidung jedes Mal als Fund meldet,
    # verbraucht dieselbe Aufmerksamkeit wie ein echter Fund.*
    lebende_ziele = {v for k, v in (zuordnung or {}).items() if k in namen}
    stumm = [k for k in (zuordnung or {}) if k not in namen]
    tot = sorted(k for k in stumm if zuordnung[k] not in lebende_ziele)
    ersatz = sorted(k for k in stumm if zuordnung[k] in lebende_ziele)
    return {
        "sportsGefragt": gefragt,
        "ligenGesamt": len(namen),
        "mitAnker": sum(1 for k in (zuordnung or {}) if k in namen),
        "ohneAnkerMitKandidat": ohne,
        "ohneAnkerOhneKandidat": unbekannt,
        "eintraegeOhneLiga": tot,
        "eintraegeErsatzschreibweise": ersatz,
        "creditsJeLigaMonat": CREDITS_JE_LIGA_MONAT,
        "creditsFuerAlleVorschlaege": CREDITS_JE_LIGA_MONAT * len(ohne),
    }


def hole_sports(api_key, fetch=None):
    """Die Liste der Wettbewerbe. Der einzige Schritt, der ins Netz geht."""
    if not api_key:
        return None
    url = "%s/sports/?apiKey=%s&all=true" % (API, api_key)
    if fetch:
        return fetch(url)
    req = urllib.request.Request(url, headers={"User-Agent": "cocobet-anker-abgleich"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def bericht(d: dict) -> str:
    z = []
    z.append("=== Odds-Anker: was fehlt ===")
    z.append("  %d Ligen im Ledger · %d mit Anker · %d ohne"
             % (d["ligenGesamt"], d["mitAnker"], d["ligenGesamt"] - d["mitAnker"]))
    sicher = [x for x in d["ohneAnkerMitKandidat"] if x.get("urteil") == "sicher"]
    vorschlag = [x for x in d["ohneAnkerMitKandidat"] if x.get("urteil") != "sicher"]
    if not d.get("sportsGefragt"):
        z.append("  ⚠️  /sports NICHT abgefragt — die Lücke steht, die Kandidaten fehlen.")
    z.append("  %d sichere Zuordnungen möglich, %d zum Ansehen, %d ohne Kandidat"
             % (len(sicher), len(vorschlag), len(d["ohneAnkerOhneKandidat"])))
    z.append("  Kosten: %d Credits/Monat je Liga · alle Vorschläge zusammen %d"
             % (d["creditsJeLigaMonat"], d["creditsFuerAlleVorschlaege"]))
    if sicher:
        z.append("")
        z.append("  ── sicher (Land + Kennwort) ──")
        for x in sicher[:40]:
            z.append('    "%s": "%s",   # n=%s · %s%s'
                     % (x["liga"], x["key"], x["n"], x["warum"],
                        "" if x.get("aktiv") else " · AKTUELL INAKTIV"))
    if vorschlag:
        z.append("")
        z.append("  ── ansehen, nicht eintragen ──")
        # 🔴 25.09.2026: hier stand nur `x["key"]`. Der ist bei einem ABGELEHNTEN Kandidaten
        # fast beliebig gewaehlt: alle Kandidaten haben dasselbe Urteil, also entscheidet die
        # alphabetische Reihenfolge. Fuer „English Sky Bet League 1" stand damit `efl_cup` da
        # (ein Pokal), obwohl `soccer_england_league1` in derselben Liste lag und die richtige
        # Antwort ist. Wer die Zeile liest, sieht den Pokal und blaettert weiter.
        # Fehlerklasse: *eine Zeile, die von mehreren gleich guten Moeglichkeiten eine zeigt
        # und die Auswahl nicht nennt, sieht wie ein Befund aus und ist eine Wuerfelzahl.*
        for x in vorschlag[:25]:
            z.append("    %-42s -> %-38s %s" % (x["liga"][:42], x["key"], x["warum"]))
            weitere = [k for k in (x.get("weitere") or []) if k != x["key"]]
            if weitere:
                z.append("    %-42s    auch moeglich: %s" % ("", ", ".join(weitere)))
    if d["eintraegeOhneLiga"]:
        z.append("")
        z.append("  ── Einträge ohne Anker-Wirkung: kein Ligastring, kein Ersatz ──")
        for k in d["eintraegeOhneLiga"][:25]:
            z.append("    %s -> %s" % (k, "(die Liga heisst im Feed anders oder kommt nicht vor)"))
    if d.get("eintraegeErsatzschreibweise"):
        z.append("")
        z.append("  ── Ersatzschreibweisen (harmlos, KEIN Fund) ──")
        z.append("    Diese Einträge feuern nie, aber ihr Ziel wird von einer anderen,")
        z.append("    feuernden Schreibweise erreicht. Am 01.09. so entschieden.")
        for k in d["eintraegeErsatzschreibweise"][:25]:
            z.append("    %s" % k)
    ohne = d["ohneAnkerOhneKandidat"]
    if ohne:
        z.append("")
        z.append("  ── ohne Kandidat, größte zuerst ──")
        for x in ohne[:15]:
            z.append("    %-42s n=%-5s %s" % (x["liga"][:42], x["n"], x["warum"]))
    return "\n".join(z)


def main() -> int:
    import betfair_consensus as BC
    frei = json.loads((BASE / "freigabe.json").read_text(encoding="utf-8"))
    ligen = [r for r in (frei.get("ligen") or []) if isinstance(r, dict)]
    key = os.environ.get("ODDS_API_KEY") or os.environ.get("THE_ODDS_API_KEY")
    sports = hole_sports(key)
    if sports is None:
        print("  ⚠️  Kein API-Schlüssel in der Umgebung — ohne /sports kann nichts zugeordnet "
              "werden. Die Lücke wird trotzdem gezählt, aber ohne Kandidaten.")
        sports = []
    d = abgleich(ligen, BC.LEAGUE_ODDS_KEY, sports)
    d["sportsAbgerufen"] = len(sports)
    OUT_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(bericht(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
