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
RAUSCHEN = {"the", "of", "league", "liga", "division", "cup", "copa", "coupe", "pokal",
            "championship", "premier", "professional", "football", "soccer"}

# Stufenzeichen. Sie sind das Gegenteil von Rauschen: „Serie A" und „Serie C" unterscheiden
# sich in NICHTS ausser diesem einen Zeichen. Standen sie in RAUSCHEN, galt „Italian Serie C"
# → `soccer_italy_serie_a` als sicher, weil beide „serie" teilen — der teuerste denkbare
# Fehler dieses Skripts: ein Anker auf die falsche Liga desselben Landes.
STUFE = {"1", "2", "3", "4", "a", "b", "c", "d", "i", "ii", "iii",
         "one", "two", "three", "primera", "segunda", "tercera"}


def _stufe(tokens) -> set:
    return {t for t in tokens if t in STUFE}


def _tokens(s: str) -> list:
    return [t for t in re.split(r"[^a-z0-9]+", str(s).lower()) if t]


def land_aus_liga(liga: str):
    """('ukraine', ['premier','league']) — oder (None, tokens), wenn das Land nicht erkannt ist. REIN."""
    t = _tokens(liga)
    if len(t) >= 2 and (t[0], t[1]) in LAND_PAARE:
        return LAND_PAARE[(t[0], t[1])], t[2:]
    if t and t[0] in LAND and LAND[t[0]]:
        return LAND[t[0]], t[1:]
    return None, t


def _kern(tokens) -> set:
    return {t for t in tokens if t not in RAUSCHEN}


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
    unser = _kern(rest)
    # Stufen zuerst: tragen BEIDE Seiten eine und sind sie verschieden, ist es eine andere
    # Liga — egal wie aehnlich der Rest klingt.
    su, si = _stufe(rest), _stufe(ktoks) | _stufe(titel)
    if su and si and not (su & si):
        return "vorschlag", ("Land %s, aber andere Spielklasse (%s gegen %s) — ansehen"
                             % (land, "/".join(sorted(su)), "/".join(sorted(si))))
    gemeinsam = unser & (set(ktoks) | set(titel))
    if gemeinsam:
        return "sicher", "Land %s + Kennwort %s" % (land, "/".join(sorted(gemeinsam)))
    if not unser:
        # „Ukrainian Premier League" besteht nur aus Allerweltswoertern — da KANN es kein
        # gemeinsames Kennwort geben. Dann traegt das Land allein, und ob das reicht,
        # entscheidet die Eindeutigkeit: `vorschlagen` stuft zurueck, sobald es zwei
        # Kandidaten im selben Land gibt.
        return "sicher", "Land %s, Name ohne eigenes Kennwort" % land
    # Unsere Seite hat Kennwoerter, und keines kommt vor: genau hier entstehen falsche Anker.
    return "vorschlag", "Land %s stimmt, aber kein gemeinsames Kennwort — ansehen" % land


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
    # Gegenrichtung: Einträge, die auf keinen Ligastring des Ledgers passen (MLS-Fall 01.09.).
    tot = sorted(k for k in (zuordnung or {}) if k not in namen)
    return {
        "sportsGefragt": gefragt,
        "ligenGesamt": len(namen),
        "mitAnker": sum(1 for k in (zuordnung or {}) if k in namen),
        "ohneAnkerMitKandidat": ohne,
        "ohneAnkerOhneKandidat": unbekannt,
        "eintraegeOhneLiga": tot,
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
        for x in vorschlag[:25]:
            z.append("    %-42s -> %-38s %s" % (x["liga"][:42], x["key"], x["warum"]))
    if d["eintraegeOhneLiga"]:
        z.append("")
        z.append("  ── Einträge, die auf keinen Ligastring passen (feuern nie) ──")
        for k in d["eintraegeOhneLiga"][:25]:
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
