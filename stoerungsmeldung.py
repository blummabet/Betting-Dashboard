#!/usr/bin/env python3
"""
stoerungsmeldung.py — einmal am Tag: was nicht stimmt. Sonst Stille.
====================================================================
🔴 20.09.2026 (Lucas: „ich weiß dann nicht, funktioniert das eigentlich, was tracken wir da …
es ist halt sehr viel aktuell").

Die Antwort darauf gibt es längst. Drei Guard-Batterien laufen 57 Prüfungen und schreiben sie
nach `uebersicht_integrity.json`, `poly_status.json` und `betfair_status.json` — und sonst
nirgendwohin. Am Abend des 20.09. meldeten sie zusammen 14 Dinge, darunter ein Spiel, das seit
95 Stunden nicht abgerechnet werden konnte.

Fehlerklasse: ein Messgerät, dessen Zeiger niemand ansieht. Das Instrument war nicht das
Problem, die Zustellung war es.

## Was diese Meldung anders macht als eine weitere Fläche

1. **Sie kommt nur, wenn etwas kaputt ist.** Eine tägliche „alles gut"-Nachricht wird nach einer
   Woche weggewischt, und dann auch die, in der etwas steht.
2. **Sie sortiert nach Geld, nicht nach Reihenfolge der Dateien.** Ein Spiel, das nicht
   abgerechnet werden kann, steht über einer Taktung, die zu langsam ist.
3. **Ein veraltetes Messgerät ist selbst ein Befund.** Wäre eine Batterie zwölf Stunden alt und
   die Meldung bliebe still, hiesse „keine Nachricht" fälschlich „alles in Ordnung" — genau die
   Klasse, die diesen Tag über dreimal zugeschlagen hat (fehlende Information rendert als
   harmloser Default).
4. **Sie fügt keinen Workflow hinzu.** Die Runner sind gesättigt (zwei Workflows liefern über
   Soll, alle anderen 2–7 Läufe am Tag). Sie hängt an einem Lauf, der ohnehin zuverlässig
   fährt, und schickt nur im Zeitfenster und nur einmal je Tag.

REIN/testbar bis auf `main()`: Einstufung, Sortierung, Text und Sende-Entscheidung sind reine
Funktionen.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
# 🔴 21.09.2026 (Lucas: „Wie kann so eine Nachricht aber in public gehen"). Die Meldung vom
# 06:14 UTC stand im oeffentlichen Kanal — Wallet-Adressen, Markt-Keys, der Stand der Buecher.
# `tg_send` faellt ohne gesetzte `TELEGRAM_CHAT_ID` auf die feste oeffentliche Kanal-ID zurueck,
# und dieses Secret ist seit dem 04.08. bewusst leer, damit der oeffentliche Pfad laeuft.
# Fehlerklasse: ein Standard-Empfaenger, der der oeffentliche Kanal ist.
#
# Diese Marke sagt es fuer jeden spaeteren Leser und fuer den Test in
# tests/test_interne_meldungen_bleiben_intern.py: was hier entsteht, geht NUR an den internen
# Kanal. Wer dieses Modul anfasst und `tg_send` einsetzt, faellt dort durch.
NUR_INTERN = True

QUELLEN = ("uebersicht_integrity.json", "poly_status.json", "betfair_status.json")
STAND_FILE = "stoerungsmeldung_stand.json"

# Ab wann ist eine Batterie selbst ein Befund? update-liga laeuft dreimal taeglich, die
# Poly- und Betfair-Batterien oefter — 14 h laesst einen ausgefallenen Lauf durch und faengt
# einen ausgefallenen Tag.
ALT_H = 14.0
# Das Fenster, in dem gesendet wird (UTC). Frueh genug, dass der Tag noch etwas bringt.
FENSTER = (6, 10)

# ── Was ist Geld? ────────────────────────────────────────────────────────────
#
# Die Reihenfolge ist die ganze Leistung dieser Meldung. Sie steht deshalb hier als LISTE und
# nicht als Stichwortsuche: „Geld" ist eine Entscheidung, keine Zeichenkette.
#
# Ein neuer Check landet per Default unter „Messung". Damit das kein stiller Default wird,
# prueft `tests/test_stoerungsmeldung.py`, dass jeder Check mit einem geldnahen Wort im Namen
# entweder hier oder in GEPRUEFT_KEIN_GELD steht — ein neuer Check zwingt also zu einer
# Entscheidung, statt unten zu verschwinden.
GELD = {
    # offene Positionen und ihr Ausgang
    "offene wette hat den anpfiff ueberlebt",
    "geschlossen heisst belegt",
    "positionswert ist frisch",
    # was nicht abgerechnet werden kann, faellt aus jeder Bilanz
    "ergebnisse kommen an",
    "settlement_alive",
    "resolutions_match_open_keys",
    "direct_bets_settling",
    "track_record_grading_sane",
    # wer handelt, schreibt sofort — fehlt der Beleg, ist die Bilanz unvollstaendig
    "jeder push hat seinen beleg",
    "public_push_buch",
    "trades_push_buch",
    "shortlist_tracker_writes",
    # 21.09.2026: eine ruhende Order, die als Position gebucht ist, steht mit Geld im Buch,
    # das nie bewegt wurde — genau der Toluca-Fall.
    "ruhende_order_ist_keine_position",
    # blind zum Geld gesetzt
    "poly-deckung: money-scan gegen liga-fetcher",
    "money map: die poly-seite gehoert zum spiel",
    "preis-signal-deckung: entstehen picks blind zum markt?",
    # ohne frische Aufloesungen rechnet niemand etwas ab
    "resolutions_fresh",
    "close_resolution_stamped",
    "track_record_fresh",
}
GEPRUEFT_KEIN_GELD = {
    # angesehen und bewusst NICHT als Geld eingestuft — mit dem Grund daneben.
    "poly-kachel gibt sich nicht als kanal-bilanz aus",   # Anzeige, keine Wette
    "jede stake-wette traegt ihre sportart",              # Zuordnung, kein Ausgang
    "buecher-punktestand: die zahl stimmt mit ihrer begruendung ueberein",
    "stake-auffaelligkeiten tragen ihr gemessenes urteil",
    "signal-bilanz: schadet ein signal belegt?",          # Messung ueber Messungen
    "fade-unter: haelt die kontrollgruppe?",              # laeuft mit, sendet nie
    "clv-urteil passt zur clv-zahl",
    "money map meldet ihre luecken",                      # meldet selbst, kein Ausfall
    "freigabe-grund ist aus den daten ableitbar",
    "shortlist_nachschub",
    "proven_wallets_profitable",
    # 21.09.2026: eine Annahme ueber die Daten, kein Ausgang. Er sagt, ob der Markt-Stempel-
    # Nachtrag noch tragen darf — schlaegt er an, rechnet nichts falsch ab, sondern der
    # Nachtrag gehoert geprueft, bevor wieder abgerechnet wird.
    "buendel_cond_stabil",
    "grosses_geld_bleibt_im_feed",
    "direction_covers_money",
}
GELD_WORTE = ("wette", "position", "order", "push", "beleg", "ergebnis", "bilanz",
              "geld", "money", "settle", "resolution", "track_record", "deckung")


def _zeit(wert):
    if not wert:
        return None
    try:
        t = datetime.fromisoformat(str(wert).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def alter_h(wert, jetzt=None):
    t = _zeit(wert)
    if t is None:
        return None
    return round(((jetzt or datetime.now(timezone.utc)) - t).total_seconds() / 3600.0, 1)


def schluessel(check: dict) -> str:
    return str(check.get("id") or check.get("label") or "").strip().lower()


def ist_geld(check: dict) -> bool:
    return schluessel(check) in GELD


def braucht_entscheidung(check: dict) -> bool:
    """Ein Check mit geldnahem Namen, der weder als Geld noch als geprueft dasteht. REIN."""
    k = schluessel(check)
    if k in GELD or k in GEPRUEFT_KEIN_GELD:
        return False
    return any(w in k for w in GELD_WORTE)


def sammeln(artefakte: dict, jetzt=None) -> dict:
    """{quelle: inhalt} -> {"geld": [...], "messung": [...], "offen": [...], "blind": [...]}.

    REIN. `blind` sind Batterien, die zu alt sind, um etwas zu behaupten — sie sind selbst ein
    Befund und nie ein stilles Gruen.
    """
    geld, messung, offen, blind = [], [], [], []
    for quelle, inhalt in sorted((artefakte or {}).items()):
        if not isinstance(inhalt, dict):
            blind.append({"quelle": quelle, "grund": "nicht lesbar"})
            continue
        a = alter_h(inhalt.get("generatedAt"), jetzt)
        if a is None:
            blind.append({"quelle": quelle, "grund": "ohne Zeitstempel"})
            continue
        if a > ALT_H:
            blind.append({"quelle": quelle, "grund": "%.0f h alt" % a, "alterH": a})
            continue
        for c in (inhalt.get("checks") or []):
            if not isinstance(c, dict) or c.get("ok"):
                continue
            zeile = {"quelle": quelle, "label": c.get("label") or c.get("id"),
                     "severity": c.get("severity"), "nFail": c.get("nFail") or 0,
                     "failures": [str(f) for f in (c.get("failures") or [])][:2]}
            if braucht_entscheidung(c):
                offen.append(zeile)
            elif ist_geld(c):
                geld.append(zeile)
            else:
                messung.append(zeile)
    schwer = lambda z: (0 if z.get("severity") == "error" else 1, -(z.get("nFail") or 0))
    return {"geld": sorted(geld, key=schwer), "messung": sorted(messung, key=schwer),
            "offen": offen, "blind": blind}


def _kurz(text: str, n: int = 150) -> str:
    t = " ".join(str(text).split())
    return t if len(t) <= n else t[:n - 1] + "…"


def baue_meldung(befund: dict, jetzt=None) -> str:
    """Der Text. REIN. Leer = nichts zu melden, dann wird nicht gesendet."""
    b = befund or {}
    if not (b.get("geld") or b.get("messung") or b.get("blind") or b.get("offen")):
        return ""
    jetzt = jetzt or datetime.now(timezone.utc)
    z = ["🩺 <b>Störungsmeldung</b> · %s" % jetzt.strftime("%d.%m. %H:%M UTC")]
    if b.get("blind"):
        z.append("")
        z.append("⚫️ <b>Blind</b> — diese Prüfung sagt gerade gar nichts:")
        for x in b["blind"]:
            z.append("   · %s (%s)" % (x["quelle"], x["grund"]))
    # Geld steht vollstaendig da — das ist der Zweck. Die Messung wird gekappt: eine Nachricht,
    # die man scrollen muss, wird wie eine Fläche behandelt, also weggewischt.
    for name, titel, zeichen, deckel in (("geld", "Kostet Geld", "🔴", None),
                                         ("offen", "Nicht eingestuft", "🟠", None),
                                         ("messung", "Messung", "🟡", 4)):
        rows = b.get(name) or []
        if not rows:
            continue
        z.append("")
        z.append("%s <b>%s</b>" % (zeichen, titel))
        zeigen = rows if deckel is None else rows[:deckel]
        for x in zeigen:
            z.append("   · <b>%s</b>" % _kurz(x["label"], 70))
            for f in (x.get("failures") or [])[:1 if name == "messung" else 2]:
                z.append("       %s" % _kurz(f))
        if deckel is not None and len(rows) > deckel:
            z.append("   · <i>und %d weitere</i>" % (len(rows) - deckel))
    z.append("")
    z.append("<i>Nur Störungen. Kommt nichts, ist nichts kaputt — außer die Prüfung selbst "
             "steht oben unter „Blind\".</i>")
    return "\n".join(z)


def soll_senden(stand: dict, jetzt=None, fenster=FENSTER) -> bool:
    """Einmal am Tag, im Fenster. REIN.

    Kein eigener Workflow: die Runner sind gesaettigt. Diese Meldung haengt an einem Lauf, der
    ohnehin oft faehrt, und entscheidet selbst, ob sie dran ist.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    if not (fenster[0] <= jetzt.hour < fenster[1]):
        return False
    return str((stand or {}).get("zuletzt") or "") != jetzt.date().isoformat()


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    probe = "--probe" in argv
    jetzt = datetime.now(timezone.utc)

    artefakte = {}
    for n in QUELLEN:
        p = BASE / n
        try:
            artefakte[n] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        except Exception:
            artefakte[n] = None

    befund = sammeln(artefakte, jetzt)
    text = baue_meldung(befund, jetzt)

    stand_p = BASE / STAND_FILE
    try:
        stand = json.loads(stand_p.read_text(encoding="utf-8"))
    except Exception:
        stand = {}

    print("=== stoerungsmeldung ===")
    print("  Geld %d · Messung %d · nicht eingestuft %d · blind %d"
          % (len(befund["geld"]), len(befund["messung"]),
             len(befund["offen"]), len(befund["blind"])))
    if probe:
        print(text or "  (nichts zu melden)")
        return 0
    if not text:
        print("  nichts zu melden — keine Nachricht.")
        return 0
    if not soll_senden(stand, jetzt):
        print("  ausserhalb des Fensters oder heute schon gesendet.")
        return 0
    try:
        from telegram_bot import tg_send_ops
    except Exception as e:                       # noqa: BLE001
        print("  Telegram nicht verfuegbar: %s" % e)
        return 0
    if tg_send_ops(text):
        stand["zuletzt"] = jetzt.date().isoformat()
        stand["geld"] = len(befund["geld"])
        stand_p.write_text(json.dumps(stand, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  gesendet.")
    else:
        print("  Versand fehlgeschlagen — Stand NICHT gesetzt, naechster Lauf versucht es erneut.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
