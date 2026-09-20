#!/usr/bin/env python3
"""fetch_liga_ergebnisse.py — die Ergebnisse nachholen, die der Tagesbau verpasst hat.

## Der Vorfall

19.09.2026, Toulouse–Le Havre, Anpfiff 18:45 UTC, `Under 2.5 Tore`, 5,50 $. Das Spiel
endete mit fuenf Toren, die Wette ist verloren. Im Buch stand sie am naechsten Mittag
immer noch als `placed` — ohne `result`, ohne `pnl`, ohne `resolvedAt`.

`resolve_wm_results.py` ist nicht schuld. Es kann nichts abrechnen, wozu in
`liga-data.json` kein Ergebnis steht, und dort stand `"result": null`.

## Warum das Ergebnis fehlte

`build_liga_data.py` ist der einzige Produzent, der Ergebnisse schreibt, und er haengt in
`update-liga.yml` — drei Crons am Tag (06:07, 07:37, 18:07 UTC). Der letzte erfolgreiche
Lauf war am 19.09. um 20:34 UTC; das Spiel war zu dem Zeitpunkt noch nicht abgepfiffen
(Schlusspfiff gegen 20:40). Die beiden Crons am 20.09. sind beide ausgefallen — in
`health/liga.json` steht fuer den 20.09. kein einziger Lauf. Also hat seit sechs Minuten
vor dem Schlusspfiff niemand mehr nachgesehen.

Gemessen am Bestand vom 20.09. 08:00 UTC: von 23 abgepfiffenen Spielen des 19.09. trugen
sechs kein Ergebnis, und Levante–Athletic vom 16.09. fehlte seit vier Tagen.

## Die Fehlerklasse

    Ein Ergebnis kommt nur dann an, wenn zufaellig ein Tagesbau nach dem Schlusspfiff
    laeuft — und eine Zeile, die nicht abgerechnet werden kann, faellt aus der Rechnung
    und nicht negativ auf.

Der zweite Halbsatz ist der teurere. Das liga-Buch zeigte einen Verlust, tatsaechlich
waren es zwei. Ein Buch, das nur die Spiele bucht, deren Ergebnis rechtzeitig ankommt,
wird systematisch zu gut — und ein geschoenter Track Record ist schlimmer als ein
schlechter.

## Was dieses Skript tut — und was ausdruecklich nicht

Es sieht nach, welche Fixtures laenger als `NACHLAUF_H` her sind und noch kein Ergebnis
tragen, und holt genau fuer deren Ligen die Fixture-Liste nach. Ist nichts offen, macht es
KEINEN einzigen API-Aufruf — es darf also oft laufen.

Es schreibt ausschliesslich das Feld `result` der betroffenen Fixtures. Es baut keine
Gruppen, legt keine Fixtures an, ruehrt Teams, Quoten und Picks nicht an. Das ist Absicht:
ein zweiter Vollschreiber auf `liga-data.json` waere genau die Bauart, die am 19.09. um
20:44 siebzehn frisch gebaute Ergebnisse wieder aus der Datei geworfen hat (der
Odds-Refresh committete seinen 10 Minuten alten Stand mit `-X ours` darueber).

Vorhandene `stats` (xG) bleiben erhalten — die schreibt ein anderer Produzent, und wer
sie hier ueberschreibt, verliert sie.

Es benutzt denselben Endpunkt wie `build_liga_data.py`
(`/fixtures?league={id}&season={jahr}`), der sich in diesem Repo bewaehrt hat. Kein neuer,
ungetesteter Abfrageweg fuer einen Pfad, der Geld bucht.
"""
from __future__ import annotations

import http.client
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import cocobet_dataset as D
from safe_write import write_json_atomic

APIF_HOST = "v3.football.api-sports.io"
APIF_KEY = os.environ.get("APISPORTS_KEY", "")
OUT_FILE = str(D.data_file())
BERICHT = str(D.file("wm_ergebnis_nachlauf.json", "liga_ergebnis_nachlauf.json"))

# Wie lange nach Anpfiff ein Spiel als „muesste durch sein" gilt. 2,5 h deckt
# Nachspielzeit und Halbzeit; Verlaengerung gibt es in den Top-5-Ligen nicht.
NACHLAUF_H = float(os.environ.get("ERGEBNIS_NACHLAUF_H") or 2.5)
# Aelter als das holt dieses Skript nicht mehr nach: die Saison-Abfrage liefert zwar alles,
# aber ein Spiel, das seit Wochen ohne Ergebnis dasteht, ist ein anderer Befund als ein
# verpasster Tagesbau — dafuer ist der Guard da, nicht ein stiller Nachtrag.
MAX_ALTER_TAGE = float(os.environ.get("ERGEBNIS_MAX_ALTER_TAGE") or 21)

FERTIG = {"FT", "AET", "PEN"}


def _api_get(path: str) -> dict | None:
    if not APIF_KEY:
        return None
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", "replace")
        conn.close()
        if resp.status != 200:
            print("  ⚠️  API-Football %s: %s" % (resp.status, raw[:160]))
            return None
        return json.loads(raw)
    except Exception as e:
        print("  ❌  API-Football Fehler: %s" % e)
        return None


# ── reine Logik ──────────────────────────────────────────────────────────────
def _zeit(wert):
    if not wert:
        return None
    try:
        t = datetime.fromisoformat(str(wert).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def hat_ergebnis(fx: dict) -> bool:
    return bool((fx.get("result") or {}).get("status"))


def offene_fixtures(groups: dict, jetzt: datetime, nachlauf_h: float = NACHLAUF_H,
                    max_alter_tage: float = MAX_ALTER_TAGE) -> dict:
    """REIN: {ligaKey: [fixture, ...]} — abgepfiffen, aber ohne Ergebnis.

    Ein Fixture ohne lesbaren Anpfiff wird NICHT mitgenommen: ohne Zeit laesst sich
    „muesste durch sein" nicht behaupten, und fehlende Information darf nicht als
    harmloser Default rendern (der Guard zaehlt diese Zeilen getrennt).
    """
    grenze = jetzt - timedelta(hours=nachlauf_h)
    zu_alt = jetzt - timedelta(days=max_alter_tage)
    offen: dict = {}
    for lk, g in (groups or {}).items():
        for fx in ((g or {}).get("fixtures") or []):
            if not isinstance(fx, dict) or hat_ergebnis(fx):
                continue
            k = _zeit(fx.get("kickoff"))
            if k is None or k > grenze or k < zu_alt:
                continue
            offen.setdefault(lk, []).append(fx)
    return offen


def ohne_anpfiff(groups: dict) -> int:
    """Fixtures ohne lesbaren Anpfiff — ueber die urteilt hier niemand, also werden sie
    gezaehlt statt verschwiegen."""
    return sum(1 for g in (groups or {}).values()
               for fx in ((g or {}).get("fixtures") or [])
               if isinstance(fx, dict) and not hat_ergebnis(fx) and _zeit(fx.get("kickoff")) is None)


def ergebnis_aus_api(item: dict) -> dict | None:
    """REIN: API-Antwort -> unser `result`-Block, oder None wenn nicht fertig."""
    fxo = (item.get("fixture") or {})
    kurz = str(((fxo.get("status") or {}).get("short")) or "").upper()
    if kurz not in FERTIG:
        return None
    gl = (item.get("goals") or {})
    h, a = gl.get("home"), gl.get("away")
    if h is None or a is None:
        return None
    return {"status": kurz, "home_score": h, "away_score": a}


def eintragen(fx: dict, ergebnis: dict) -> bool:
    """REIN: traegt `result` ein und BEHAELT vorhandene `stats` (xG kommt von einem
    anderen Produzenten — wer sie hier ueberschreibt, loescht sie). True, wenn sich
    etwas geaendert hat."""
    if not ergebnis or hat_ergebnis(fx):
        return False
    alt_stats = (fx.get("result") or {}).get("stats")
    neu = dict(ergebnis)
    if alt_stats:
        neu["stats"] = alt_stats
    fx["result"] = neu
    return True


def _liga_defs():
    import build_liga_data as B
    return B._active_league_defs()


def _saison() -> int:
    import build_liga_data as B
    return int(os.environ.get("LIGA_SEASON") or B.current_season())


def main() -> int:
    jetzt = datetime.now(timezone.utc)
    print("=== fetch_liga_ergebnisse.py — %s ===" % OUT_FILE)
    try:
        with open(OUT_FILE, encoding="utf-8") as f:
            wm = json.load(f)
    except Exception as e:
        print("  ❌  %s unlesbar: %s — nichts getan." % (OUT_FILE, e))
        return 0

    groups = wm.get("groups") or {}
    offen = offene_fixtures(groups, jetzt)
    # Der Bericht traegt die Zahlen, ueber die der Guard urteilt — das Urteil gehoert
    # dorthin, wo die Zahl entsteht, und die Guard-Batterie muss dafuer nicht die 4,7 MB
    # von liga-data.json durchsuchen. `datenbauAt` verraet zusaetzlich, wann der Tagesbau
    # zuletzt geschrieben hat: am 20.09. stand dort 19.09. 12:02, also 20 Stunden alt.
    bericht = {
        "generatedAt": jetzt.isoformat(),
        "datei": OUT_FILE.rsplit("/", 1)[-1],
        "nachlaufH": NACHLAUF_H,
        "datenbauAt": (wm.get("_meta") or {}).get("dataUpdatedAt"),
        "offenVorher": {lk: len(v) for lk, v in offen.items()},
        "offen": [{"liga": lk,
                   "paarung": "%s–%s" % (f.get("homeName"), f.get("awayName")),
                   "kickoff": f.get("kickoff"),
                   "stundenHer": round((jetzt - (_zeit(f.get("kickoff")) or jetzt))
                                       .total_seconds() / 3600.0, 1)}
                  for lk, v in sorted(offen.items()) for f in v],
        "ohneAnpfiff": ohne_anpfiff(groups),
        "nachgetragen": 0,
        "ligenAbgefragt": [],
        "apiLeer": [],
    }

    if not offen:
        print("  ✅ kein abgepfiffenes Spiel ohne Ergebnis — kein API-Aufruf noetig.")
        write_json_atomic(BERICHT, bericht)
        return 0

    for lk, fxs in sorted(offen.items()):
        print("  %s: %d ohne Ergebnis — %s" % (
            lk, len(fxs), ", ".join("%s–%s (%s)" % (f.get("homeName"), f.get("awayName"),
                                                    str(f.get("kickoff"))[:10])
                                    for f in fxs[:4])))

    if not APIF_KEY:
        print("  ⚠️  APISPORTS_KEY nicht gesetzt — nur gemeldet, nichts nachgetragen.")
        write_json_atomic(BERICHT, bericht)
        return 0

    defs = _liga_defs()
    saison = _saison()
    nachgetragen = 0
    for lk, fxs in sorted(offen.items()):
        lid = (defs.get(lk) or {}).get("apif_id")
        if not lid:
            print("  ⚠️  %s: keine league_id im Datensatz — uebersprungen." % lk)
            continue
        bericht["ligenAbgefragt"].append(lk)
        data = _api_get("/fixtures?league=%s&season=%s" % (lid, saison))
        antwort = (data or {}).get("response") or []
        if not antwort:
            # Leere Antwort ist KEIN „keine Ergebnisse" — sie ist ein Ausfall. Sie darf
            # nichts ueberschreiben und muss sichtbar bleiben (Quota, Key, Saison).
            print("  ⚠️  %s: API lieferte 0 Fixtures — Quota/Key/Saison %s pruefen." % (lk, saison))
            bericht["apiLeer"].append(lk)
            continue
        per_fid = {}
        for item in antwort:
            fid = ((item.get("fixture") or {}).get("id"))
            if fid is not None:
                per_fid[str(fid)] = item
        for fx in fxs:
            item = per_fid.get(str(fx.get("fid")))
            if item is None:
                print("    ↯ %s–%s: fid %s nicht in der API-Antwort"
                      % (fx.get("homeName"), fx.get("awayName"), fx.get("fid")))
                continue
            erg = ergebnis_aus_api(item)
            if erg is None:
                print("    ⏳ %s–%s: bei der API noch nicht fertig (%s)"
                      % (fx.get("homeName"), fx.get("awayName"),
                         ((item.get("fixture") or {}).get("status") or {}).get("short")))
                continue
            if eintragen(fx, erg):
                nachgetragen += 1
                print("    ✅ %s–%s %s:%s (%s)" % (fx.get("homeName"), fx.get("awayName"),
                                                   erg["home_score"], erg["away_score"],
                                                   erg["status"]))

    bericht["nachgetragen"] = nachgetragen
    uebrig = offene_fixtures(groups, jetzt)
    bericht["offenNachher"] = {lk: len(v) for lk, v in uebrig.items()}
    bericht["offen"] = [z for z in bericht["offen"]
                        if any(z["paarung"] == "%s–%s" % (f.get("homeName"), f.get("awayName"))
                               for v in uebrig.values() for f in v)]
    if nachgetragen:
        wm.setdefault("_meta", {})["ergebnisNachlaufAt"] = jetzt.isoformat()
        write_json_atomic(OUT_FILE, wm)
        print("  💾 %d Ergebnis(se) nachgetragen → %s" % (nachgetragen, OUT_FILE))
    else:
        print("  ℹ️  nichts nachzutragen (API hatte die Spiele auch noch nicht fertig).")
    write_json_atomic(BERICHT, bericht)
    return 0


if __name__ == "__main__":
    sys.exit(main())
