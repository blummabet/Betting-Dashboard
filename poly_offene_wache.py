#!/usr/bin/env python3
"""poly_offene_wache.py — offene Auto-Bets, die zu nah am Anpfiff stehen.

## Der Vorfall

19.09.2026 (Lucas: „gestern gabs scheinbar bei poly probleme waehrend dieses spiels …
es wurde vorm spielstart nicht geschlossen und ist nun lost"). Toulouse–Le Havre,
`Under 2.5 Tore`, Einsatz 5,50 $. Anpfiff 18:45 UTC. Der Positions-Manager lief um
17:06 UTC — mitten im 2-Stunden-Fenster, `time_based_exit` haette feuern muessen. Die
Wette steht bis heute als `placed` im Buch, mit `valuedAt` von 19:31 UTC, also 46 Minuten
NACH Anpfiff, Kurs 0,74. Sie lief ins Spiel und ist verloren.

## Die Fehlerklasse

    Eine Wirkung, die ausbleibt, hinterlaesst keine Spur — danach ist „nie versucht"
    von „versucht und gescheitert" nicht mehr zu unterscheiden.

`manage_wm_poly_positions.py` schrieb `update_auto_bet_status` NUR im Erfolgsfall ins
Buch. Scheiterte der Verkauf, blieb im Buch exakt das, was auch dort stuende, wenn der
Manager nie gelaufen waere. Deshalb ist der Vorfall im Nachhinein nicht aufzuklaeren,
und deshalb faellt er auch nicht auf: ein `placed` sieht aus wie jedes andere.

Zwei Dinge folgen daraus. Der Manager haelt jetzt jeden Versuch fest (dort, wo er
handelt — „wer handelt, schreibt sofort"). Und diese Wache sieht nach, weil ein Buch,
das sich selbst nicht meldet, auf den naechsten Blick von aussen wartet.

## Warum eine eigene Wache und nicht ein Schritt mehr im Manager

Der Takt. `manage-liga-poly.yml` behauptet im Cron 25 Laeufe am Tag
(`0,30 10-21 * * *` plus `0 8 * * *`); gezaehlt aus `health/liga-poly.json` kamen am
16.09. vier, am 17.09. vier, am 18.09. fuenf, am 19.09. fuenf. GitHubs Scheduler liefert
auf diesem Repo rund ein Fuenftel des Nominalen, und daran ist von hier aus nichts zu
reparieren. Ein Waechter, der im selben Workflow haengt, hat dieselbe Luecke wie das,
was er bewachen soll.

`betfair.yml` laeuft auf demselben Mac alle 15 Minuten und tut es nachweislich (20 Laeufe
allein am Vormittag des 20.09.). Diese Wache haengt deshalb dort. Sie liest nur Dateien
und schickt hoechstens eine Nachricht — sie handelt nicht, sie kann nichts verkaufen.

## Die zwei Stufen

    spaet — Anpfiff in <= VORLAUF_H Stunden, die Wette steht noch offen. Der Hard-Close
            des Managers (PRE_MATCH_CLOSE_HOURS = 2 h) haette greifen muessen. Hier ist
            noch Zeit, von Hand zu schliessen.
    drin  — Anpfiff vorbei, die Wette steht immer noch offen. Der Schaden laeuft bereits.

Beide nennen, was das Buch ueber den Verkaufsversuch weiss. Steht dort nichts, heisst
das seit diesem Commit wirklich „nie versucht" und nicht mehr „vielleicht gescheitert".

## Blinder Fleck, benannt statt versteckt

`shortlist_auto_bets_placed.json` traegt keinen Anpfiff (andere Auswahl, andere
Exit-Regel). Ueber diese Zeilen urteilt die Wache nicht — sie zaehlt sie im Artefakt
unter `ohneAnpfiff`. Fehlende Information darf nicht als harmloser Default rendern.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).parent

# Die drei Buecher mit Anpfiff-gesteuertem Exit. Jede Zeile eigenes Label, damit die
# Nachricht sagt, welcher Datensatz betroffen ist.
BUECHER = [
    ("liga_auto_bets_placed.json", "Liga"),
    ("mls_auto_bets_placed.json", "MLS"),
    ("wm_auto_bets_placed.json", "WM"),
]
# Buecher ohne Anpfiff — werden gezaehlt, nicht beurteilt (s. Docstring).
BUECHER_OHNE_ANPFIFF = ["shortlist_auto_bets_placed.json"]

ARTEFAKT = "poly_offene_wache.json"
SEEN_FILE = "poly_offene_wache_seen.json"

# Etwas mehr als der Hard-Close des Managers (2 h): die Wache soll anschlagen, bevor
# das Fenster zu ist, nicht wenn es schon zu spaet ist.
VORLAUF_H = float(os.environ.get("WACHE_VORLAUF_H") or 2.5)
# Solange der Zustand bleibt, wiederholt sich die Nachricht hoechstens alle N Stunden.
WIEDERHOLUNG_H = float(os.environ.get("WACHE_WIEDERHOLUNG_H") or 6.0)
# Eine erledigte Zeile darf nicht ewig im Dedup-Stand liegen.
SEEN_TTL_H = float(os.environ.get("WACHE_SEEN_TTL_H") or 72.0)
MAX_PUSH = int(os.environ.get("WACHE_MAX_PUSH") or 6)

TELEGRAM_TOKEN = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
TRADES_CHAT_ID = (os.environ.get("TELEGRAM_TRADES_CHAT_ID") or "").strip()
SKIP_SEND = (os.environ.get("WACHE_SKIP_SEND") or "").strip().lower() in ("1", "true", "yes")


# ── reine Logik ──────────────────────────────────────────────────────────────
def _zeit(wert):
    """ISO-String -> aware datetime, sonst None. Ein unlesbarer Wert ist kein 'jetzt'."""
    if not wert:
        return None
    try:
        t = datetime.fromisoformat(str(wert).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def anpfiff(bet: dict):
    """Echter Anpfiff der Wette. `matchDate` ist oft nur ein Datum (00:00 UTC) — das
    taugt fuer ein Zeitfenster von zwei Stunden nicht und wird deshalb NICHT als
    Anpfiff akzeptiert. Genau daran starb der Hard-Close am 13.06. (QAT-SUI)."""
    t = _zeit(bet.get("kickoff"))
    if t is not None:
        return t
    md = str(bet.get("matchDate") or "")
    # nur wenn eine Uhrzeit dransteht
    return _zeit(md) if ("T" in md and len(md) > 10) else None


def stunden_bis(bet: dict, jetzt: datetime):
    k = anpfiff(bet)
    if k is None:
        return None
    return (k - jetzt).total_seconds() / 3600.0


def stufe(bet: dict, jetzt: datetime, vorlauf_h: float = VORLAUF_H) -> str:
    """'' | 'spaet' | 'drin'. Nur offene Wetten; alles andere ist nicht Sache der Wache."""
    if not isinstance(bet, dict) or bet.get("status") != "placed":
        return ""
    h = stunden_bis(bet, jetzt)
    if h is None:
        return ""
    if h <= 0:
        return "drin"
    if h <= vorlauf_h:
        return "spaet"
    return ""


def _versuchstext(bet: dict) -> str:
    """Was das Buch ueber den Verkaufsversuch weiss — die halbe Nachricht."""
    n = bet.get("sellVersuche")
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    if not n:
        return "kein Verkaufsversuch im Buch"
    grund = str(bet.get("sellVersuchGrund") or bet.get("sellFehler") or "ohne Grund im Buch")
    am = str(bet.get("sellVersuchAm") or "")[:16].replace("T", " ")
    return "%d Versuch%s, zuletzt %s — %s" % (n, "e" if n != 1 else "", am or "?", grund)


def paarung(bet: dict) -> str:
    h, a = bet.get("home"), bet.get("away")
    if h and a:
        return "%s v %s" % (h, a)
    return str(bet.get("match") or bet.get("betKey") or "?")


def zeilen_aus_buch(buch: dict, label: str, datei: str, jetzt: datetime,
                    vorlauf_h: float = VORLAUF_H) -> list:
    out = []
    for bet in ((buch or {}).get("bets") or []):
        st = stufe(bet, jetzt, vorlauf_h)
        if not st:
            continue
        h = stunden_bis(bet, jetzt)
        out.append({
            "betKey": bet.get("betKey") or "",
            "datei": datei,
            "label": label,
            "stufe": st,
            "paarung": paarung(bet),
            "markt": bet.get("market") or bet.get("side") or "?",
            "einsatz": bet.get("stake"),
            "einstieg": bet.get("entryAsk") if bet.get("entryAsk") is not None else bet.get("polyPrice"),
            "kurs": bet.get("currentPrice"),
            "pnlPct": bet.get("pnlPct"),
            "anpfiff": (anpfiff(bet) or jetzt).isoformat(),
            "stundenBis": round(h, 2) if h is not None else None,
            "versuch": _versuchstext(bet),
            "sellVersuche": bet.get("sellVersuche") or 0,
        })
    return out


def ohne_anpfiff(buch: dict) -> int:
    """Offene Zeilen, ueber die die Wache NICHT urteilen kann (kein Anpfiff im Buch)."""
    return sum(1 for b in ((buch or {}).get("bets") or [])
               if isinstance(b, dict) and b.get("status") == "placed" and anpfiff(b) is None)


def neue_zeilen(zeilen: list, seen: dict, jetzt: datetime,
                wiederholung_h: float = WIEDERHOLUNG_H,
                ttl_h: float = SEEN_TTL_H) -> tuple:
    """Dedup je (betKey, Stufe): dieselbe Lage wiederholt sich hoechstens alle
    `wiederholung_h` Stunden. Der Stufenwechsel spaet -> drin ist eine NEUE Lage und
    kommt sofort — das ist der Moment, in dem aus einer Warnung ein Schaden wird.
    Gibt (neu, seen_neu)."""
    seen = dict(seen or {})
    # abgelaufene Eintraege raeumen, sonst waechst der Stand endlos
    for k in [k for k, v in seen.items()
              if (_zeit(v) is None) or (jetzt - _zeit(v) > timedelta(hours=ttl_h))]:
        seen.pop(k, None)
    neu = []
    for z in zeilen:
        k = "%s|%s" % (z.get("betKey"), z.get("stufe"))
        vor = _zeit(seen.get(k))
        if vor is not None and (jetzt - vor) < timedelta(hours=wiederholung_h):
            continue
        neu.append(z)
        seen[k] = jetzt.isoformat()
    return neu, seen


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _preis(p) -> str:
    try:
        return "%.0f¢" % (float(p) * 100)
    except (TypeError, ValueError):
        return "—"


def karte(z: dict) -> str:
    """Optisch eindeutig: der Schaden oben, die Zahlen darunter, die Diagnose zuletzt."""
    drin = z.get("stufe") == "drin"
    kopf = "🚨🚨 <b>POSITION LIEF INS SPIEL</b>" if drin else "⚠️ <b>POSITION NOCH OFFEN</b>"
    h = z.get("stundenBis")
    if drin:
        zeit = ("seit %.1f h im Spiel" % abs(h)) if isinstance(h, (int, float)) else "Anpfiff vorbei"
    else:
        zeit = ("Anpfiff in %.1f h" % h) if isinstance(h, (int, float)) else "Anpfiff steht an"

    lines = [kopf, ""]
    lines.append("<b>%s</b>" % _esc(z.get("paarung")))
    lines.append("")
    lines.append("<b>%s</b> @ %s" % (_esc(z.get("markt")), _preis(z.get("einstieg"))))
    geld = []
    if z.get("einsatz") is not None:
        try:
            geld.append("$%.2f" % float(z["einsatz"]))
        except (TypeError, ValueError):
            pass
    if z.get("kurs") is not None:
        geld.append("jetzt %s" % _preis(z.get("kurs")))
    if isinstance(z.get("pnlPct"), (int, float)):
        geld.append("%+.1f%%" % z["pnlPct"])
    if geld:
        lines.append(" · ".join(geld))
    lines += ["", "🕐 %s · %s" % (zeit, _esc(z.get("label")))]
    lines += ["", "🔎 %s" % _esc(z.get("versuch"))]
    return "\n".join(lines)


# ── IO ───────────────────────────────────────────────────────────────────────
def _lade(name: str, default):
    p = BASE / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print("  ⚠️  %s unlesbar: %s" % (name, e))
        return default


def tg_send(text: str) -> bool:
    if SKIP_SEND or not TELEGRAM_TOKEN or not TRADES_CHAT_ID:
        print("ℹ️  Telegram-Send geskippt")
        return False
    url = "https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_TOKEN
    data = urllib.parse.urlencode({
        "chat_id": TRADES_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, data=data, method="POST"), timeout=15) as r:
            return json.loads(r.read().decode()).get("ok", False)
    except Exception as e:
        print("❌ TG-Send failed: %s" % e)
        return False


def main(probe: bool = False) -> int:
    """`probe=True` rechnet und druckt, schreibt aber NICHTS — weder Artefakt noch
    Dedup-Stand. Ein Blick von Hand darf keinen echten Alarm verschlucken (und keine
    Pipeline-Ausgabe erzeugen: die gehoert der Pipeline)."""
    jetzt = datetime.now(timezone.utc)
    zeilen, blind = [], 0
    for datei, label in BUECHER:
        buch = _lade(datei, {})
        zeilen += zeilen_aus_buch(buch, label, datei, jetzt)
        blind += ohne_anpfiff(buch)
    for datei in BUECHER_OHNE_ANPFIFF:
        blind += ohne_anpfiff(_lade(datei, {}))

    # 'drin' zuerst — der Deckel schneidet hinten ab, und hinten gehoert das Harmlosere hin.
    zeilen.sort(key=lambda z: (z.get("stufe") != "drin", z.get("stundenBis") or 0))

    neu, seen = neue_zeilen(zeilen, _lade(SEEN_FILE, {}), jetzt)
    gesendet = 0
    for z in neu[:MAX_PUSH]:
        if probe:
            print("--- Probe, nicht gesendet ---\n%s" % karte(z))
        elif tg_send(karte(z)):
            gesendet += 1
    gedeckelt = max(0, len(neu) - MAX_PUSH)

    if probe:
        print("=== Probe: %d offen (%d im Spiel, %d spaet) · %d waeren neu · %d ohne Anpfiff ==="
              % (len(zeilen), sum(1 for z in zeilen if z["stufe"] == "drin"),
                 sum(1 for z in zeilen if z["stufe"] == "spaet"), len(neu), blind))
        return 0

    (BASE / SEEN_FILE).write_text(json.dumps(seen, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    (BASE / ARTEFAKT).write_text(json.dumps({
        "generatedAt": jetzt.isoformat(),
        "vorlaufH": VORLAUF_H,
        "offen": zeilen,
        "nDrin": sum(1 for z in zeilen if z["stufe"] == "drin"),
        "nSpaet": sum(1 for z in zeilen if z["stufe"] == "spaet"),
        "neu": len(neu),
        "gesendet": gesendet,
        "gedeckelt": gedeckelt,
        "ohneAnpfiff": blind,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== poly_offene_wache: %d offen (%d im Spiel, %d spaet) · %d neu · %d gesendet "
          "· %d ohne Anpfiff ===" % (len(zeilen),
                                     sum(1 for z in zeilen if z["stufe"] == "drin"),
                                     sum(1 for z in zeilen if z["stufe"] == "spaet"),
                                     len(neu), gesendet, blind))
    for z in zeilen:
        print("  %s %s · %s · %s" % ("🚨" if z["stufe"] == "drin" else "⚠️",
                                     z["paarung"], z["markt"], z["versuch"]))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(probe="--probe" in sys.argv[1:]))
