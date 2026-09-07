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
    # ── zweite Spielklassen ────────────────────────────────────────────────
    "championship": 2, "2nd-bundesliga": 2, "la-liga-2": 2, "serie-b": 2, "ligue-2": 2,
    "j-league-2": 2, "brasileiro-serie-b": 2, "primera-b": 2, "k-league-2": 2,
    "eerste-divisie": 2, "segunda-liga": 2, "liga-de-expansion-mx-apertura": 2,
    "primera-nacional": 2, "ykkonen": 2, "challenge-league": 2, "ligapro-primera-b": 2,
    "thai-league-2": 2, "liga-2": 2, "fnl": 2, "segunda-division": 2, "pervaya-liga": 2,
    "mls-next-pro": 2, "1-lig": 2, "first-division-b": 2, "2nd-division": 2,
    # ── dritte Klasse und tiefer, regional, Amateur ────────────────────────
    "league-one": 3, "league-two": 3, "3rd-liga": 3, "serie-c-group-a": 3,
    "serie-c-group-b": 3, "serie-c-group-c": 3, "tercera-division": 3,
    "tercera-division-group-7": 3, "primera-c": 3, "primera-division-rfef": 3,
    "liga-portugal-3": 3, "tweede-divisie": 3, "national": 3, "national-league": 3,
    "liga-bet-south-a": 3, "shillong-second-divison": 3, "torneo-federal-a": 3,
    "kolmonen": 3, "primera-divisio": 3, "south-australia-state-league-1": 3,
    "nsw-premier-league-2": 3, "japan-football-league": 3, "second-division-b": 3,
    "usl-league-one": 3, "k3-league": 3,
    "northern-territory-premier-league": 3, "npl-western-australia": 3,
    "npl-new-south-wales": 3, "npl-victoria": 3, "npl-queensland": 3,
    "npl-south-australia": 3, "npl-northern-new-south": 3, "npl-capital-football": 3,
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

# Mustererkennung fuer alles, was neu dazukommt. Sie ersetzt die Tabelle nicht, sie faengt
# nur die Faelle ab, bei denen der Slug die Antwort selbst mitbringt.
_MUSTER = (
    ("srl", lambda s: s.endswith("-srl") or "-srl-" in s),          # Simulated Reality League
    ("jugend", lambda s: s[:3] in ("u17", "u19", "u20", "u21", "u23")),
    ("frauen", lambda s: ("women" in s or "femenina" in s or "feminin" in s
                          or "damallsvenskan" in s or "frauen" in s)),
    ("pokal", lambda s: s.endswith("-cup") or s.startswith("copa-") or s.endswith("-pokal")),
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
    v = EBENE.get((slug or "").lower())
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


def _bucket(f):
    for grenze, name in STUFEN:
        if f < grenze:
            return name
    return STUFEN[-1][1]


def kandidaten(wetten: list, norm: dict, ab: float = KAND_AB, max_n: int = 60) -> list:
    """Grosse Einsaetze auf Ebene 2/3 — die Zeilen, um die Lucas gebeten hat.

    Bewusst OHNE Ausgangsfilter: die Liste zeigt, was gesetzt wurde, nicht was aufging.
    Ob sie traegt, entscheidet die vorregistrierte Schublade, nicht diese Anzeige.
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
    out.sort(key=lambda x: -x["faktor"])
    return out[:max_n]


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
