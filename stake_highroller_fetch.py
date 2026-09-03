#!/usr/bin/env python3
"""
stake_highroller_fetch.py — Stake Highroller-Sammler
================================================================================
03.09.2026 (Lucas: „ich würde gerne nur im Dashboard einen Bereich mit den Spielen sehen,
mit Schwellen die wir definieren, dann rein und wir sammeln das").

## Was das hier ist — und was es NICHT ist
Stake zeigt große Wetten öffentlich an (stake.com/sports/highrollers: Event, User, Zeit,
Quote, Einsatz). Das ist die einzige Quelle im Projekt, die EINZELNE Einsätze mit Betrag
nennt. Betfair gibt Matched-Volumen, Polymarket gibt Preis-als-Geldanteil, Pinnacle gibt
den Anker — keine davon nennt eine einzelne Wette.

Dieser Sammler holt diese Liste und legt sie ab. Mehr nicht. Er bewertet nichts, er pusht
nichts, er erzeugt kein Signal. Es gibt für Stake-Einsatzfluss im Projekt KEINE gemessene
Trefferquote und KEINEN gemessenen CLV — solange das so ist, ist jede Bewertung („starkes
Signal bei 4-5 Wetten in 1 Minute") eine Behauptung ohne Beleg, und die kommt hier nicht
rein. Erst sammeln, dann gegen den Pinnacle-Schlusskurs messen, dann urteilen.

## Bekannte Schwäche der Quelle (steht mit im Ausgabe-JSON, damit sie sichtbar bleibt)
Stake hat eine „Wetten verbergen"-Einstellung. Wer sie nutzt, taucht hier nicht auf. Die
Liste ist also nicht „die großen Einsätze", sondern „die großen Einsätze der Konten, die
sich zeigen". Das ist eine Auswahl, keine Grundgesamtheit.

## Schema-Findung — geraten wird nicht
Stakes GraphQL-Schema ist nicht dokumentiert, ändert sich, und Introspection ist zu
(gemessen am 03.09.2026: HTTP 400 „introspection is not allowed by Apollo Server").
Ein geratener Feldname, der zufällig existiert und das Falsche liefert, wäre genau die
Sorte stiller Fehler, die uns hier schon zweimal Geld gekostet hat.

Deshalb wird trotzdem gefragt, nur anders: graphql-js validiert das ganze Dokument, bevor
es etwas ausführt, und schreibt in die Fehler, was es stattdessen kennt („Did you mean
\"amount\"?", „of type \"[SportBet!]!\" must have a selection of subfields"). Der Server ist
damit sein eigenes Verzeichnis, und weil alle Verstöße gemeinsam zurückkommen, kostet eine
ganze Ebene genau eine Anfrage. Gelernt wird einmal, das Ergebnis liegt in stake_query.json.

Findet es nichts, schreibt es status="schema_unbekannt" — und NICHT eine leere Liste, die
wie „heute keine großen Wetten" aussähe.

## Ausgabe
  stake_highroller.json  — aktuelle Sicht fürs Dashboard (Wetten im Fenster, roh)
  stake_bet_ledger.json  — die Sammlung (dedupliziert über Wett-ID, gedeckelt)
  stake_schema_probe.json— was die Sonde über das Schema gelernt hat (nur --sonde)
  stake_query.json       — die gelernte Abfrage, damit nicht jeder Lauf neu lernt

## Env
  STAKE_MIN_USD        Mindesteinsatz in USD (Default 1000)
  STAKE_FENSTER_H      Wie weit die Dashboard-Sicht zurückreicht (Default 48)
  STAKE_LEDGER_KEEP    Max Wetten im Ledger (Default 20000)
  STAKE_LIMIT          Wie viele Einträge je Abruf (Default 50)
  STAKE_ENDPUNKT       Endpunkt überschreiben

## Aufruf
  python3 stake_highroller_fetch.py --sonde     → nur prüfen, nichts schreiben ausser Probe
  python3 stake_highroller_fetch.py             → holen, normalisieren, ablegen
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent

VIEW_FILE   = BASE / "stake_highroller.json"
LEDGER_FILE = BASE / "stake_bet_ledger.json"
PROBE_FILE  = BASE / "stake_schema_probe.json"
QUERY_FILE  = BASE / "stake_query.json"

ENDPUNKTE = [
    "https://stake.com/_api/graphql",
    "https://api.stake.com/graphql",
    "https://stake.bet/_api/graphql",
]

MIN_USD      = float(os.environ.get("STAKE_MIN_USD")     or 1000)
FENSTER_H    = int(os.environ.get("STAKE_FENSTER_H")     or 48)
LEDGER_KEEP  = int(os.environ.get("STAKE_LEDGER_KEEP")   or 20000)
ABRUF_LIMIT  = int(os.environ.get("STAKE_LIMIT")         or 50)
VIEW_KEEP    = 1500          # so viele rohe Wetten reicht die Sicht ans Frontend

KOPF = {
    "content-type": "application/json",
    "accept": "*/*",
    "user-agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "origin": "https://stake.com",
    "referer": "https://stake.com/sports/highrollers",
}

# Stablecoins rechnen 1:1. Alles andere ohne mitgelieferten USD-Wert bleibt None —
# eine unbekannte Größe darf NICHT als 0 durchgehen, sonst sieht „weiß ich nicht"
# aus wie „war klein".
STABLE = {"usdt", "usdc", "busd", "dai", "usd", "tusd", "usdp"}


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _post(url: str, body: dict, timeout: int = 25):
    """-> (status:int|None, daten:dict|None, fehler:str|None)"""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=KOPF, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            roh = r.read()
            try:
                return r.status, json.loads(roh.decode("utf-8", "replace")), None
            except Exception:
                return r.status, None, "kein JSON: " + roh[:200].decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # 03.09.2026 — mein Fehler, und er hat den ganzen Lernweg lahmgelegt: GraphQL-Server
        # antworten auf VALIDIERUNGSFEHLER mit HTTP 400 und trotzdem mit einem gueltigen
        # JSON-Body voller "errors". Genau dieser Body IST die Auskunft, aus der wir lernen.
        # Hier wurde er weggeworfen und durch "HTTP 400 <Textschnipsel>" ersetzt — die Sonde
        # meldete daraufhin "Endpunkt antwortet nicht", obwohl der Server praezise geantwortet
        # hatte ("Cannot query field \"highroller\" on type \"Query\"."). Ein Statuscode ist
        # kein Grund, den Inhalt nicht zu lesen.
        try:
            roh = e.read()
        except Exception:
            roh = b""
        txt = roh[:300].decode("utf-8", "replace")
        try:
            d = json.loads(roh.decode("utf-8", "replace"))
            if isinstance(d, dict) and ("errors" in d or "data" in d):
                return e.code, d, None
        except Exception:
            pass
        return e.code, None, "HTTP %s %s" % (e.code, txt)
    except Exception as e:
        return None, None, str(e)


# ── Schema-Findung ───────────────────────────────────────────────────────────
INTRO_QUERY = """
{ __schema { queryType { name fields { name
  args { name type { kind name ofType { kind name } } }
  type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } } } } }
"""

INTRO_TYP = """
query T($n: String!) { __type(name: $n) { name kind
  fields { name
    args { name }
    type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } }
  possibleTypes { name } } }
"""


def _typ_name(t: dict) -> str:
    """Wickelt NON_NULL/LIST ab und gibt den nackten Typnamen."""
    # 03.09.2026: `t = t.get("ofType") or {}` allein dreht sich bei {} ewig im Kreis —
    # der Test test_typ_name_bei_muell_leer_statt_absturz hat genau das aufgedeckt.
    # Abbruch gehoert an das FEHLEN von ofType, nicht an den Typ von t.
    while isinstance(t, dict):
        if t.get("name"):
            return t["name"]
        naechst = t.get("ofType")
        if not isinstance(naechst, dict):
            return ""
        t = naechst
    return ""


def _query_felder(url: str):
    st, d, err = _post(url, {"query": INTRO_QUERY})
    if not d or d.get("errors") or not d.get("data"):
        grund = err
        if not grund and d and d.get("errors"):
            grund = str((d["errors"][0] or {}).get("message") or "")[:160]
        return None, grund or "keine Antwort"
    qt = ((d.get("data") or {}).get("__schema") or {}).get("queryType") or {}
    return qt.get("fields") or [], None


def _waehle_feld(felder: list):
    """Das Query-Feld, das die Highroller-Liste liefert."""
    kand = []
    for f in felder:
        n = (f.get("name") or "").lower()
        if "highroller" in n or "highrollers" in n:
            kand.append(f)
    if not kand:
        return None
    # Sport schlägt Casino, sonst der kürzeste Name.
    sport = [f for f in kand if "sport" in (f.get("name") or "").lower()]
    return (sport or sorted(kand, key=lambda f: len(f["name"])))[0]


SKALAR = {"SCALAR", "ENUM"}

# Was die Sonde bei der Feldsuche gehoert hat — landet in stake_schema_probe.json.
_PROTOKOLL: list = []


def _selektion(url: str, typname: str, tiefe: int, cache: dict, pfad: tuple = ()):
    """Baut rekursiv eine Selektion: alle argumentlosen Skalare, plus Objektfelder
    bis `tiefe`. Kein Raten von Feldnamen — nur was das Schema wirklich hat."""
    if tiefe <= 0 or not typname or typname in pfad:
        return ""
    if typname not in cache:
        st, d, err = _post(url, {"query": INTRO_TYP, "variables": {"n": typname}})
        cache[typname] = ((d or {}).get("data") or {}).get("__type") or {}
    typ = cache[typname]
    felder = typ.get("fields") or []
    if not felder:
        # Union/Interface ohne Felder: über possibleTypes inline-fragmentieren
        moegl = [p.get("name") for p in (typ.get("possibleTypes") or []) if p.get("name")]
        teile = []
        for pt in moegl[:6]:
            inner = _selektion(url, pt, tiefe - 1, cache, pfad + (typname,))
            if inner:
                teile.append("... on %s %s" % (pt, inner))
        return "{ __typename " + " ".join(teile) + " }" if teile else ""
    teile = ["__typename"]
    for f in felder:
        if f.get("args"):
            continue                        # Felder mit Argumenten überspringen
        t = f.get("type") or {}
        tn = _typ_name(t)
        kind = t.get("kind")
        while kind in ("NON_NULL", "LIST") and t.get("ofType"):
            t = t["ofType"]
            kind = t.get("kind")
        if kind in SKALAR:
            teile.append(f["name"])
        elif kind in ("OBJECT", "UNION", "INTERFACE"):
            inner = _selektion(url, tn, tiefe - 1, cache, pfad + (typname,))
            if inner:
                teile.append("%s %s" % (f["name"], inner))
    return "{ " + " ".join(teile) + " }"



# ── Schema lernen, wenn Introspection aus ist ────────────────────────────────
# 03.09.2026 — die Sonde auf dem Mac-Runner hat geliefert:
#
#   stake.com/_api/graphql   HTTP 400  "GraphQL introspection is not allowed by Apollo Server"
#   api.stake.com/graphql    HTTP 404  Cannot POST /graphql
#   stake.bet/_api/graphql   HTTP 403  Cloudflare-Challenge
#
# Der erste Treffer ist die gute Nachricht: der Endpunkt lebt, ist vom Mac aus erreichbar und
# antwortet als Apollo-Server mit sauberem JSON. Nur nachschlagen dürfen wir nicht.
#
# Raten wäre jetzt die naheliegende und die falsche Antwort — ein geratener Feldname, der zufällig
# existiert, aber das Falsche liefert, wäre genau die Sorte stiller Fehler, die uns hier schon
# zweimal Geld gekostet hat. Stattdessen wird gefragt, nur anders: graphql-js VALIDIERT das ganze
# Dokument, bevor es irgendetwas ausführt, und schreibt in die Fehler, was es stattdessen kennt.
#
#   Cannot query field "amont" on type "SportBet". Did you mean "amount"?
#   Field "highrollerSportBets" of type "[SportBet!]!" must have a selection of subfields.
#   Field "user" argument "id" of type "String!" is required, but it was not provided.
#
# Damit ist der Server sein eigenes Schema-Verzeichnis. Und weil die Validierung ALLE Fehler eines
# Dokuments auf einmal zurückgibt, kostet eine ganze Ebene genau EINE Anfrage: ein Kandidaten-
# Vokabular hinschicken, aus den Fehlern streichen, was es nicht gibt, aufklappen, was Unterfelder
# braucht, weitermachen. Nach drei bis vier Runden steht die Abfrage.
#
# Gelernt wird einmal; das Ergebnis liegt in stake_query.json und wird wiederverwendet, bis es
# bricht. Erst dann wird neu gelernt — nicht bei jedem Lauf.

RX_UNBEKANNT = re.compile(r'Cannot query field "([^"]+)" on type "([^"]+)"')
RX_BRAUCHT_SUB = re.compile(r'Field "([^"]+)" of type "([^"]+)" must have a selection of subfields')
RX_KEIN_SUB = re.compile(r'Field "([^"]+)" must not have a selection')
RX_MEINTEN = re.compile(r'Did you mean ([^?]+)\?')
RX_ARG_PFLICHT = re.compile(r'Field "([^"]+)" argument "([^"]+)"')

# Saatwörter für das Query-Feld. Sie müssen nicht stimmen — sie müssen nur NAH genug sein,
# damit graphql-js seinen „Did you mean"-Vorschlag mitschickt.
# 03.09.2026: „highroller" allein brachte nichts — graphql-js schlaegt nur vor, was LEXIKALISCH
# nah dran ist, und von „highroller" zu „highrollerSportBets" ist es zu weit. Deshalb mehrere
# Schreibweisen dicht am erwarteten Namen. Das ist kein Raten auf gut Glueck: ein Treffer wird
# daran erkannt, dass der Server „must have a selection of subfields" sagt — also bestaetigt,
# dass es das Feld gibt und dass es eine Liste von Objekten liefert. Was es dann wirklich
# liefert, steht vor dem ersten Sammeln in stake_schema_probe.json und wird angeschaut.
QUERY_SAAT = [
    "highrollerSportBets", "highrollerBets", "highRollerSportBets", "highRollerBets",
    "highrollerSports", "highrollers", "highRollers", "highroller",
    "sportBets", "sportsBets", "bets", "latestBets", "recentBets", "bigBets",
]

# Kandidaten je Ebene. Ein Name, den es nicht gibt, kostet nichts außer einer Zeile Fehlertext.
FELD_SAAT = [
    "id", "iid", "amount", "amountUsd", "currency", "value", "payout", "payoutMultiplier",
    "potentialMultiplier", "odds", "createdAt", "updatedAt", "placedAt", "status", "active",
    "user", "bet", "game", "outcomes", "outcome", "market", "fixture", "tournament",
    "category", "sport", "name", "slug", "startingAt", "type", "count",
]

LERN_RUNDEN = 8
LERN_TIEFE = 4

# Bekannte Grenze: Union- und Interface-Typen (etwa ein `bet`, das SportBet ODER CasinoBet sein
# kann) brauchen Inline-Fragmente, die dieser Lernweg nicht baut — solche Zweige fallen weg
# statt halb zu entstehen. Was oben liegt (Betrag, Waehrung, Quote, Zeit, Nutzer) reicht fuer
# die Sammlung; was fehlt, steht in stake_schema_probe.json und ist damit sichtbar, nicht still.


def _fehlertexte(url: str, query: str):
    st, d, err = _post(url, {"query": query})
    if d and d.get("errors"):
        return [str(e.get("message") or "") for e in d["errors"]], d, None
    return [], d, err


def _meinten(msg: str):
    """Die Namen aus 'Did you mean "a", "b", or "c"?'."""
    m = RX_MEINTEN.search(msg or "")
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


def _nackt(typ: str) -> str:
    """[SportBet!]! -> SportBet"""
    return (typ or "").strip("[]!")


def _feld_raten(url: str, protokoll: list = None):
    """-> (feldName, typName, notiz). Findet das Query-Feld über die Auskunft des Servers.

    Zwei Wege, beide aus derselben Quelle: „must have a selection of subfields" beweist, dass
    es das Feld GIBT und dass es Objekte liefert; „Did you mean ..." nennt Namen, auf die wir
    von allein nicht kommen. Apollo blendet die Vorschläge in Produktion oft aus — dann trägt
    der erste Weg allein, und deshalb steht dort eine Liste von Schreibweisen statt einer.
    """
    vorschlaege: dict = {}
    tot = 0
    for saat in QUERY_SAAT:
        msgs, _d, err = _fehlertexte(url, "{ %s }" % saat)
        if protokoll is not None:
            protokoll.append({"saat": saat, "fehler": msgs[:3] or None,
                              "transport": err[:160] if err else None})
        if err and not msgs:
            # Transportfehler (403, 404, Timeout) — nicht die Antwort des Schemas.
            tot += 1
            if tot >= 3:
                return None, None, "Endpunkt antwortet nicht: %s" % err
            continue
        for m in msgs:
            t = RX_BRAUCHT_SUB.search(m)
            if t and t.group(1) == saat:
                return saat, t.group(2), "direkt getroffen"
            for v in _meinten(m):
                vorschlaege[v] = vorschlaege.get(v, 0) + 1
    if not vorschlaege:
        return None, None, ("keine der %d Schreibweisen existiert, und der Server schlaegt "
                            "nichts vor (Apollo blendet 'Did you mean' in Produktion aus)"
                            % len(QUERY_SAAT))
    # Highroller schlägt alles, Sport schlägt Casino, danach der häufigste Vorschlag.
    def rang(n):
        k = n.lower()
        return (0 if "highroller" in k else 1, 0 if "sport" in k else 1, -vorschlaege[n], len(n))
    for name in sorted(vorschlaege, key=rang):
        msgs, _d, _e = _fehlertexte(url, "{ %s }" % name)
        for m in msgs:
            t = RX_BRAUCHT_SUB.search(m)
            if t and t.group(1) == name:
                return name, t.group(2), "ueber Vorschlag gefunden"
    return None, None, "Vorschlaege %s, keiner liefert eine Liste" % sorted(vorschlaege)


def _knoten(typ: str) -> dict:
    """Ein Kandidaten-Knoten: welcher Typ, und welche Feldnamen wir dort probieren."""
    return {"typ": typ, "felder": {x: None for x in FELD_SAAT}}


def _baue(feld: str, knoten: dict, arg: str = "") -> str:
    def sel(k):
        teile = []
        for n in sorted(k["felder"]):
            kind = k["felder"][n]
            teile.append(n + (" " + sel(kind) if kind else ""))
        return "{ " + " ".join(teile) + " }"
    return "query HR($limit: Int) { %s%s %s }" % (
        feld, "(%s: $limit)" % arg if arg else "", sel(knoten))


def _anwenden(knoten: dict, weg: dict, auf: dict, zu_flach: set, tiefe: int, ahnen: tuple = ()):
    """Eine Runde Erkenntnis in den Kandidatenbaum einarbeiten.

    03.09.2026 — hier steckte ein Denkfehler, den der nachgebaute Apollo-Server aufgedeckt hat:
    zuerst wurden die Fehler GLOBAL nach Feldnamen angewandt. `amount` ist auf SportBet gültig
    und auf User nicht, also strich „Cannot query field amount on type User" auch das gültige
    amount am Wurzelknoten — Runde für Runde, bis der Baum leer war und die Abfrage gar keine
    Selektion mehr hatte. Die Fehlermeldung nennt den TYP; also wird nach Typ gestrichen, und
    jeder Knoten weiß, welcher er ist.

    weg:       {typ: {feldname}}      nicht vorhanden auf diesem Typ
    auf:       {feldname: typname}    braucht Unterfelder, und zwar von diesem Typ
    zu_flach:  {feldname}             hat gar keine Unterfelder — Block wieder einklappen
    """
    t = knoten["typ"]
    for n in list(knoten["felder"]):
        if n in weg.get(t, ()):
            del knoten["felder"][n]
            continue
        kind = knoten["felder"][n]
        if kind is None:
            if n in auf:
                zt = _nackt(auf[n])
                # Zyklen (User -> bet -> user -> ...) und zu tiefe Zweige werden weggelassen,
                # nicht halb gebaut: eine ungültige Abfrage lernt nichts mehr dazu.
                if len(ahnen) + 1 < tiefe and zt not in ahnen and zt != t:
                    knoten["felder"][n] = _knoten(zt)
                else:
                    del knoten["felder"][n]
        else:
            if n in zu_flach:
                knoten["felder"][n] = None
                continue
            _anwenden(kind, weg, auf, zu_flach, tiefe, ahnen + (t,))
            if not kind["felder"]:
                del knoten["felder"][n]


def _zaehle(knoten: dict) -> int:
    return sum(1 + (_zaehle(v) if v else 0) for v in knoten["felder"].values())


def schema_lernen(url: str, feld: str, typ: str, arg: str = ""):
    """Baut die Selektion über die Validierungsfehler des Servers auf.

    Rückgabe: (queryText, notiz). Eine Ebene kostet EINE Anfrage, egal wie breit sie ist —
    graphql-js meldet alle Verstöße eines Dokuments gemeinsam.
    """
    wurzel = _knoten(_nackt(typ))
    fremd = []
    for runde in range(LERN_RUNDEN):
        if not wurzel["felder"]:
            return None, "Kandidatenbaum leer nach %d Runden — Saatliste passt nicht zum Schema" % runde
        q = _baue(feld, wurzel, arg)
        msgs, d, err = _fehlertexte(url, q)
        if not msgs:
            if err:
                return None, "Endpunkt bricht ab: %s" % err
            return q, "gelernt in %d Runde(n), %d Felder" % (runde + 1, _zaehle(wurzel))
        weg: dict = {}
        auf: dict = {}
        flach: set = set()
        for m in msgs:
            u = RX_UNBEKANNT.search(m)
            if u:
                weg.setdefault(u.group(2), set()).add(u.group(1))
                continue
            s = RX_BRAUCHT_SUB.search(m)
            if s and s.group(1) != feld:
                auf[s.group(1)] = s.group(2)
                continue
            f = RX_KEIN_SUB.search(m)
            if f:
                flach.add(f.group(1))
                continue
            a = RX_ARG_PFLICHT.search(m)
            if a:
                weg.setdefault(wurzel["typ"], set()).add(a.group(1))
                continue
            fremd.append(m[:140])
        if not (weg or auf or flach):
            # Fehler, die nichts mit der Struktur zu tun haben (Auth, Rate-Limit): abbrechen,
            # statt weiterzuprobieren und die Ursache zu verschleiern.
            return None, "unklarer Fehler: " + " | ".join(fremd[:3])
        _anwenden(wurzel, weg, auf, flach, LERN_TIEFE)
    return None, "nach %d Runden nicht konvergiert: %s" % (LERN_RUNDEN, " | ".join(fremd[:3]))


def _limit_arg(url: str, feld: str) -> str:
    """Nimmt der Server ein limit/first? Ohne Argument holt er sonst seinen Default."""
    for arg in ("limit", "first"):
        msgs, _d, _e = _fehlertexte(url, "query HR($limit: Int) { %s(%s: $limit) { __typename } }"
                                    % (feld, arg))
        if not any('Unknown argument "%s"' % arg in m for m in msgs):
            return arg
    return ""

def schema_finden(url: str, tiefe: int = 4):
    """-> (feldName, queryText, notiz) oder (None, None, grund)

    Zwei Wege, in dieser Reihenfolge:
      1. Introspection — der saubere. Stake hat sie zu (Apollo, 03.09.2026); ein anderer
         Endpunkt oder ein spaeteres Stake koennen sie wieder offen haben.
      2. Ueber die Validierungsfehler des Servers lernen (s. Block darueber).
    Geraten wird auf keinem der beiden Wege.
    """
    felder, err = _query_felder(url)
    if felder is not None:
        f = _waehle_feld(felder)
        if not f:
            return None, None, "kein Highroller-Feld unter %d Query-Feldern" % len(felder)
        tn = _typ_name(f.get("type") or {})
        sel = _selektion(url, tn, tiefe, {})
        if not sel:
            return None, None, "Rueckgabetyp %s ohne lesbare Felder" % tn
        args = f.get("args") or []
        argname = next((a["name"] for a in args
                        if (a.get("name") or "").lower() in ("limit", "first")), None)
        kopf = "query HR($limit: Int) { %s%s %s }" % (
            f["name"], "(%s: $limit)" % argname if argname else "", sel)
        return f["name"], kopf, "Introspection, Typ %s" % tn

    feld, typ, notiz = _feld_raten(url, _PROTOKOLL)
    if not feld:
        return None, None, "Introspection aus (%s); %s" % ((err or "?")[:120], notiz)
    arg = _limit_arg(url, feld)
    query, notiz2 = schema_lernen(url, feld, typ, arg)
    if not query:
        return None, None, "Feld %s vom Typ %s gefunden, Selektion nicht: %s" % (feld, typ, notiz2)
    return feld, query, "aus Fehlermeldungen gelernt (%s -> %s), %s" % (feld, typ, notiz2)

# ── Normalisierung ───────────────────────────────────────────────────────────
def _sammle(obj, schluessel: set, tiefe: int = 8):
    """Sucht rekursiv nach Schlüsseln (klein geschrieben) und gibt alle Treffer."""
    fund = []
    if tiefe <= 0:
        return fund
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in schluessel and not isinstance(v, (dict, list)):
                fund.append((k, v))
            fund.extend(_sammle(v, schluessel, tiefe - 1))
    elif isinstance(obj, list):
        for v in obj[:30]:
            fund.extend(_sammle(v, schluessel, tiefe - 1))
    return fund


def _erst(obj, schluessel: set, typ=None):
    for _k, v in _sammle(obj, schluessel):
        if v is None:
            continue
        if typ is float:
            try:
                return float(v)
            except Exception:
                continue
        if typ is str and not isinstance(v, str):
            continue
        return v
    return None


def _usd(betrag, waehrung, roh) -> tuple:
    """-> (usd:float|None, grund:str). None heißt unbekannt, NICHT null."""
    direkt = _erst(roh, {"amountusd", "usdamount", "amountindollars", "usdvalue"}, float)
    if direkt is not None:
        return float(direkt), "feld"
    if betrag is None:
        return None, "kein_betrag"
    w = (waehrung or "").lower()
    if w in STABLE:
        return float(betrag), "stablecoin"
    return None, "kurs_fehlt:" + (w or "?")


def normalisiere(rec: dict) -> dict:
    """Aus einem rohen Highroller-Eintrag die Felder ziehen, die wir brauchen.
    Über Feldnamen, nicht über Positionen — das überlebt Schema-Umbauten."""
    wid = _erst(rec, {"id", "iid", "betid"}, str)
    ts = _erst(rec, {"createdat", "placedat", "timestamp", "updatedat"}, str)
    betrag = _erst(rec, {"amount", "wager", "stake", "betamount"}, float)
    waehrung = _erst(rec, {"currency", "currencyname"}, str)
    quote = _erst(rec, {"odds", "totalodds", "payoutmultiplier", "potentialmultiplier"}, float)
    user = _erst(rec, {"name", "username"}, str)
    event = _erst(rec, {"fixturename", "eventname", "matchname", "name"}, str)
    liga = _erst(rec, {"tournamentname", "leaguename", "competition", "tournament"}, str)
    sport = _erst(rec, {"sportname", "sport", "category"}, str)
    markt = _erst(rec, {"marketname", "market", "bettype"}, str)
    auswahl = _erst(rec, {"outcomename", "outcome", "selection", "pick"}, str)
    anpfiff = _erst(rec, {"startingat", "starttime", "kickoff", "scheduledat"}, str)
    usd, usd_grund = _usd(betrag, waehrung, rec)
    return {
        "id": str(wid) if wid is not None else None,
        "ts": ts,
        "user": user,
        "betrag": betrag,
        "waehrung": (waehrung or "").lower() or None,
        "einsatzUsd": usd,
        "usdGrund": usd_grund,
        "quote": quote,
        "sport": sport,
        "liga": liga,
        "event": event,
        "markt": markt,
        "auswahl": auswahl,
        "anpfiff": anpfiff,
    }


# ── Ledger ───────────────────────────────────────────────────────────────────
def _lade(pfad: Path, standard):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return standard


def _schreibe(pfad: Path, daten):
    tmp = pfad.with_suffix(pfad.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(pfad)


def ledger_mischen(alt: dict, neu: list, jetzt: str) -> dict:
    """Dedupliziert über die Wett-ID. Einträge ohne ID werden verworfen —
    ohne ID kann man nicht deduplizieren, und doppelt gezähltes Geld ist
    schlimmer als eine fehlende Wette."""
    wetten = list(alt.get("wetten") or [])
    bekannt = {w.get("id") for w in wetten if w.get("id")}
    zugang = 0
    ohne_id = 0
    for w in neu:
        if not w.get("id"):
            ohne_id += 1
            continue
        if w["id"] in bekannt:
            continue
        bekannt.add(w["id"])
        wetten.append(w)
        zugang += 1
    wetten.sort(key=lambda w: (w.get("ts") or ""), reverse=True)
    if len(wetten) > LEDGER_KEEP:
        wetten = wetten[:LEDGER_KEEP]
    return {
        "seit": alt.get("seit") or jetzt,
        "aktualisiert": jetzt,
        "n": len(wetten),
        "zugangLetzterLauf": zugang,
        "ohneIdVerworfen": ohne_id,
        "wetten": wetten,
    }


def _im_fenster(w: dict, ab: datetime) -> bool:
    ts = w.get("ts")
    if not ts:
        return False
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return False
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d >= ab


def sicht_bauen(ledger: dict, jetzt: datetime, status: str, endpunkt: str,
                feld: str, notiz: str) -> dict:
    ab = jetzt - timedelta(hours=FENSTER_H)
    im_fenster = [w for w in (ledger.get("wetten") or []) if _im_fenster(w, ab)]
    ueber = [w for w in im_fenster
             if w.get("einsatzUsd") is not None and w["einsatzUsd"] >= MIN_USD]
    unklar = [w for w in im_fenster if w.get("einsatzUsd") is None]
    return {
        "asof": jetzt.isoformat().replace("+00:00", "Z"),
        "status": status,
        "endpunkt": endpunkt,
        "feld": feld,
        "notiz": notiz,
        "schwelleUsd": MIN_USD,
        "fensterH": FENSTER_H,
        "sammlungSeit": ledger.get("seit"),
        "nLedger": ledger.get("n") or 0,
        "nFenster": len(im_fenster),
        "nUeberSchwelle": len(ueber),
        "nEinsatzUnbekannt": len(unklar),
        # Die Sicht trägt die ROHEN Wetten im Fenster — gruppiert und gefiltert wird
        # im Frontend, damit Lucas die Schwellen live drehen kann.
        "wetten": im_fenster[:VIEW_KEEP],
        "belegt": False,
        "hinweis": ("Reine Sammlung. Für Stake-Einsatzfluss gibt es im Projekt noch keine "
                    "gemessene Trefferquote und keinen gemessenen CLV. Die Liste zeigt nur "
                    "Konten, die ihre Wetten sichtbar lassen — das ist eine Auswahl, keine "
                    "Grundgesamtheit."),
    }


# ── Hauptlauf ────────────────────────────────────────────────────────────────
def holen(sonde: bool = False):
    jetzt = datetime.now(timezone.utc)
    jetzt_s = jetzt.isoformat().replace("+00:00", "Z")
    urls = [os.environ["STAKE_ENDPUNKT"]] if os.environ.get("STAKE_ENDPUNKT") else ENDPUNKTE

    versuche = []
    feld = query = None
    url_ok = ""

    # Gelernt wird EINMAL, nicht alle 15 Minuten: Lernen kostet ein gutes Dutzend Anfragen,
    # das Ergebnis haelt, bis Stake das Schema umbaut. Der Cache wird deshalb zuerst probiert
    # und erst verworfen, wenn er wirklich nicht mehr traegt.
    cache = _lade(QUERY_FILE, {})
    if not sonde and cache.get("query") and cache.get("url") in urls:
        st, d, err = _post(cache["url"], {"query": cache["query"],
                                          "variables": {"limit": ABRUF_LIMIT}})
        if d and not d.get("errors") and (d.get("data") or {}).get(cache.get("feld")) is not None:
            feld, query, url_ok = cache["feld"], cache["query"], cache["url"]
            versuche.append({"url": url_ok, "feld": feld, "notiz": "aus stake_query.json"})

    if not feld:
        for url in urls:
            f, q, notiz = schema_finden(url)
            versuche.append({"url": url, "feld": f, "notiz": notiz})
            if f:
                feld, query, url_ok = f, q, url
                _schreibe(QUERY_FILE, {"url": url, "feld": f, "query": q,
                                       "gelernt": jetzt_s, "notiz": notiz})
                break

    if not feld:
        sicht = sicht_bauen(_lade(LEDGER_FILE, {}), jetzt, "schema_unbekannt", "", "",
                            "; ".join("%s: %s" % (v["url"], v["notiz"]) for v in versuche))
        if sonde:
            _schreibe(PROBE_FILE, {"asof": jetzt_s, "status": "schema_unbekannt",
                                   "versuche": versuche, "feldsuche": _PROTOKOLL[:40]})
            print("\n──── was der Server auf jede Schreibweise sagt ────")
            for e in _PROTOKOLL[:40]:
                print(" %-22s %s" % (e["saat"], (e["fehler"] or [e["transport"] or "—"])[0][:150]))
            print(json.dumps(versuche, ensure_ascii=False, indent=2))
            return 1
        _schreibe(VIEW_FILE, sicht)
        print("kein Schema gefunden:", json.dumps(versuche, ensure_ascii=False))
        return 1

    st, d, err = _post(url_ok, {"query": query, "variables": {"limit": ABRUF_LIMIT}})
    roh = ((d or {}).get("data") or {}).get(feld)
    if isinstance(roh, dict):
        for k in ("data", "results", "items", "edges", "nodes"):
            if isinstance(roh.get(k), list):
                roh = roh[k]
                break
    if not isinstance(roh, list):
        roh = []

    if sonde:
        _schreibe(PROBE_FILE, {
            "asof": jetzt_s, "status": "ok" if roh else "leer", "endpunkt": url_ok,
            "feld": feld, "query": query, "httpStatus": st, "fehler": err,
            "nRoh": len(roh), "beispielRoh": roh[:2],
            "beispielNormalisiert": [normalisiere(r) for r in roh[:5]],
            "graphqlFehler": (d or {}).get("errors"),
            "feldsuche": _PROTOKOLL[:40],
        })
        print("Endpunkt : %s\nFeld     : %s\nHTTP     : %s\nEinträge : %d"
              % (url_ok, feld, st, len(roh)))
        if roh:
            print("\nErster Eintrag normalisiert:")
            print(json.dumps(normalisiere(roh[0]), ensure_ascii=False, indent=2))
        else:
            print("Fehler:", err, (d or {}).get("errors"))
        return 0 if roh else 1

    neu = [normalisiere(r) for r in roh]
    ledger = ledger_mischen(_lade(LEDGER_FILE, {}), neu, jetzt_s)
    _schreibe(LEDGER_FILE, ledger)
    status = "ok" if roh else ("leer" if not err else "fehler")
    _schreibe(VIEW_FILE, sicht_bauen(ledger, jetzt, status, url_ok, feld, err or ""))
    print("Stake: %d geholt, %d neu, Ledger %d, Fenster %dh, Schwelle $%.0f"
          % (len(roh), ledger["zugangLetzterLauf"], ledger["n"], FENSTER_H, MIN_USD))
    return 0 if roh else 1


if __name__ == "__main__":
    sys.exit(holen(sonde="--sonde" in sys.argv))
