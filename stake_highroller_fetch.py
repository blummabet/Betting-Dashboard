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

## Schema-Findung
Stakes GraphQL-Schema ist nicht dokumentiert und ändert sich. Deshalb rät dieses Skript
NICHT: es fragt per Introspection, welches Query-Feld die Highroller liefert, baut daraus
die Selektion und speichert das gefundene Schema. Geht Introspection nicht, fällt es auf
eine Kandidatenliste zurück. Findet es nichts, schreibt es status="schema_unbekannt" —
und NICHT eine leere Liste, die wie „heute keine großen Wetten" aussähe.

## Ausgabe
  stake_highroller.json  — aktuelle Sicht fürs Dashboard (Wetten im Fenster, roh)
  stake_bet_ledger.json  — die Sammlung (dedupliziert über Wett-ID, gedeckelt)
  stake_schema_probe.json— was die Sonde über das Schema gelernt hat (nur --sonde)

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
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent

VIEW_FILE   = BASE / "stake_highroller.json"
LEDGER_FILE = BASE / "stake_bet_ledger.json"
PROBE_FILE  = BASE / "stake_schema_probe.json"

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
        try:
            txt = e.read()[:300].decode("utf-8", "replace")
        except Exception:
            txt = ""
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
        return None, err or (json.dumps(d)[:200] if d else "keine Antwort")
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


def schema_finden(url: str, tiefe: int = 4):
    """-> (feldName, queryText, notiz) oder (None, None, grund)"""
    felder, err = _query_felder(url)
    if felder is None:
        return None, None, "Introspection aus (%s)" % (err or "?")
    f = _waehle_feld(felder)
    if not f:
        namen = [x.get("name") for x in felder][:400]
        return None, None, "kein Highroller-Feld unter %d Query-Feldern" % len(namen)
    tn = _typ_name(f.get("type") or {})
    cache: dict = {}
    sel = _selektion(url, tn, tiefe, cache)
    if not sel:
        return None, None, "Rückgabetyp %s ohne lesbare Felder" % tn
    args = f.get("args") or []
    hat_limit = any((a.get("name") or "").lower() in ("limit", "first") for a in args)
    argname = next((a["name"] for a in args
                    if (a.get("name") or "").lower() in ("limit", "first")), None)
    kopf = "query HR($limit: Int) { %s%s %s }" % (
        f["name"],
        "(%s: $limit)" % argname if hat_limit else "",
        sel)
    return f["name"], kopf, "Typ %s, Tiefe %d" % (tn, tiefe)


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
    for url in urls:
        f, q, notiz = schema_finden(url)
        versuche.append({"url": url, "feld": f, "notiz": notiz})
        if f:
            feld, query, url_ok = f, q, url
            break

    if not feld:
        sicht = sicht_bauen(_lade(LEDGER_FILE, {}), jetzt, "schema_unbekannt", "", "",
                            "; ".join("%s: %s" % (v["url"], v["notiz"]) for v in versuche))
        if sonde:
            _schreibe(PROBE_FILE, {"asof": jetzt_s, "status": "schema_unbekannt",
                                   "versuche": versuche})
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
