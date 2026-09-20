#!/usr/bin/env python3
"""paper_settle.py — das Papierbuch abrechnen.

## Warum es das gibt

20.09.2026 (Lucas: „ich bin dafuer wir stellen das Auto trading mal ab und schreiben es
nur im Cockpit mit ala paper trading. Dann kann ich da immer mitschauen").

Der Anlass ist nicht Vorsicht, sondern ein Messproblem. Der Fussball-Trader
(Pinnacle-fair gegen Polymarket) hat nach Monaten **sechs abgerechnete Zeilen**. 28 der
34 WM-Wetten endeten durch Verkauf, und deren P/L wurde bis heute gar nicht gebucht. Das
95-%-Band der 27 verkauften Trades reicht von -4,2 % bis +9,6 %: man kann weder sagen,
dass die Kante da ist, noch dass sie fehlt. Mit 5,50 $ je Wette dauert es Jahre, bis sich
das mit echtem Geld entscheidet.

Ein Papierbuch entscheidet es schneller und gratis — aber nur, wenn es abgerechnet wird.
Ein Buch ohne Ausgang beantwortet keine Schwellenfrage.

## Was hier absichtlich NICHT simuliert wird

Kein Verkauf, kein Pre-Match-Close, kein Stop-Loss. Die Papier-Wette wird **bis zum
Spielende gehalten** und am Ergebnis abgerechnet.

Das ist die ehrlichere Messung, und zwar aus einem bestimmten Grund: die Exit-Maschinerie
hat ihre eigenen Zahlen (verkaufte WM-Trades: Ziel erreicht +8,17 $, Age-Loss -5,27 $),
und wer sie in dieselbe Zahl mischt, kann hinterher nicht sagen, ob die Auswahl gut war
oder das Timing. Die Frage, die offen ist, lautet: **liegt Polymarket bei Vereinsfussball-
Torlinien systematisch neben Pinnacle?** Die beantwortet nur der Ausgang.

Der Einstieg ist trotzdem ehrlich: das Papierbuch laeuft durch dasselbe Spread-Gate wie
der Live-Pfad und bucht den **Ask**, nicht den Mid. Genau daran haengt die Frage — die
gemeldete Edge wird gegen den Mid gerechnet, gekauft wird zum Ask, und bei Toulouse–Le
Havre waren von „+3,6 pp" real +3,1 pp uebrig.

## Fehlerklasse, gegen die hier gebaut wird

    Eine Auswahl nach Ausgang: wenn nur die Zeilen in der Bilanz landen, die zufaellig
    einen Ausgang bekommen haben, misst man nicht die Strategie, sondern den Filter.

Deshalb wird JEDE Papier-Zeile abgerechnet, sobald ihr Ergebnis da ist, und keine
nachtraeglich ausgesucht. Zeilen ohne Ergebnis bleiben `PENDING` und werden gezaehlt.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import cocobet_dataset as D
from safe_write import write_json_atomic

PAPIER_FILE = str(D.file("wm_paper_bets.json", "liga_paper_bets.json"))
BERICHT = str(D.file("wm_paper_bilanz.json", "liga_paper_bilanz.json"))


def _now():
    return datetime.now(timezone.utc).isoformat()


def abrechnen(bets: list, result_lookup: dict, determine, pnl_fn) -> tuple:
    """REIN: rechnet offene Papier-Zeilen ab. (n_neu, n_pending).

    Idempotent: eine Zeile mit `result` ausser PENDING wird nicht angefasst. `determine`
    und `pnl_fn` kommen von aussen (resolve_wm_results), damit Papier und Echtgeld
    GARANTIERT dieselbe Abrechnungsregel benutzen — eine zweite Kopie der Regel waere
    genau die Bauart, die zwei Bilanzen auseinanderlaufen laesst.
    """
    neu = pending = 0
    for b in bets:
        if not isinstance(b, dict):
            continue
        if b.get("result") and b.get("result") != "PENDING":
            continue
        key = "%s-%s" % (b.get("homeId") or b.get("home", ""),
                         b.get("awayId") or b.get("away", ""))
        res = result_lookup.get(key)
        if not res:
            pending += 1
            continue
        r = determine(b, res)
        if r == "PENDING":
            pending += 1
            continue
        b["result"] = r
        b["pnl"] = pnl_fn(b, r)
        b["resolvedAt"] = _now()
        neu += 1
    return neu, pending


def bilanz(bets: list) -> dict:
    """REIN: die Zahlen des Papierbuchs. Getrennt nach Markt, weil die eine offene Frage
    genau die ist (7 von 7 Liga-Wetten waren `Under 2.5 Tore`)."""
    fertig = [b for b in bets if b.get("result") in ("WIN", "LOSS", "VOID")]
    einsatz = sum(float(b.get("stake") or 0) for b in fertig)
    pl = sum(float(b.get("pnl") or 0) for b in fertig)
    je_markt = {}
    for b in fertig:
        m = b.get("market") or "?"
        z = je_markt.setdefault(m, {"n": 0, "einsatz": 0.0, "pl": 0.0, "gewonnen": 0})
        z["n"] += 1
        z["einsatz"] += float(b.get("stake") or 0)
        z["pl"] += float(b.get("pnl") or 0)
        if b.get("result") == "WIN":
            z["gewonnen"] += 1
    for z in je_markt.values():
        z["einsatz"] = round(z["einsatz"], 2)
        z["pl"] = round(z["pl"], 2)
        z["roiPct"] = round(100 * z["pl"] / z["einsatz"], 1) if z["einsatz"] else None
    return {
        "generatedAt": _now(),
        "datei": PAPIER_FILE.rsplit("/", 1)[-1],
        "n": len(bets),
        "abgerechnet": len(fertig),
        "offen": len(bets) - len(fertig),
        "gewonnen": sum(1 for b in fertig if b.get("result") == "WIN"),
        "einsatz": round(einsatz, 2),
        "pl": round(pl, 2),
        "roiPct": round(100 * pl / einsatz, 1) if einsatz else None,
        "jeMarkt": je_markt,
        # Kein Urteil hier: bei n unter 100 ist jede Renditezahl Rauschen, und eine
        # Zahl ohne Untergrenze entscheidet nichts. Die Untergrenze rechnet die
        # Freigabe-Registrierung, sobald `zielN` erreicht ist.
        "urteil": "nicht belegt" if len(fertig) < 100 else "messbar",
    }


def main() -> int:
    print("=== paper_settle.py — %s ===" % PAPIER_FILE.rsplit("/", 1)[-1])
    if not os.path.exists(PAPIER_FILE):
        print("  ℹ️  kein Papierbuch — nichts zu tun.")
        return 0
    try:
        with open(PAPIER_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("  ❌  Papierbuch unlesbar: %s — nichts geaendert." % e)
        return 0
    bets = data.get("bets") or []
    if not bets:
        print("  ℹ️  Papierbuch leer.")
        write_json_atomic(BERICHT, bilanz([]))
        return 0

    try:
        from resolve_wm_results import build_result_lookup, determine_result, compute_pnl
        wm = json.loads(open(str(D.data_file()), encoding="utf-8").read())
        lookup = build_result_lookup(wm)
    except Exception as e:
        print("  ⚠️  Abrechnungsregel/Spielplan nicht ladbar (%s) — nur Bilanz, keine "
              "Abrechnung." % e)
        write_json_atomic(BERICHT, bilanz(bets))
        return 0

    neu, pending = abrechnen(bets, lookup, determine_result, compute_pnl)
    if neu:
        data["updatedAt"] = _now()
        write_json_atomic(PAPIER_FILE, data)
        print("  💾 %d Papier-Wette(n) abgerechnet" % neu)
    b = bilanz(bets)
    write_json_atomic(BERICHT, b)
    print("  📊 %d Zeilen · %d abgerechnet · %d offen · Einsatz %.2f · P/L %+.2f · ROI %s · %s"
          % (b["n"], b["abgerechnet"], b["offen"], b["einsatz"], b["pl"],
             ("%+.1f%%" % b["roiPct"]) if b["roiPct"] is not None else "—", b["urteil"]))
    for m, z in sorted(b["jeMarkt"].items(), key=lambda kv: -kv[1]["n"]):
        print("     %-24s n=%-3d Treffer %d · P/L %+.2f · ROI %s"
              % (m, z["n"], z["gewonnen"], z["pl"],
                 ("%+.1f%%" % z["roiPct"]) if z["roiPct"] is not None else "—"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
