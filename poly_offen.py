#!/usr/bin/env python3
"""
poly_offen.py — 14.09.2026 (Lucas): EINE Definition von „offene Position".

🔴 Warum es das gibt. Der Open-Exposure-Deckel in auto_wm_poly_trigger.py fragte an zwei
Stellen `not bet.get("resolved") and not bet.get("soldAt")`. Ein Feld `resolved` schreibt
aber **niemand** — der Resolver setzt `status` (won/lost/void), `result` und `resolvedAt`,
der Auto-Sell setzt `soldAt`. Ergebnis am 14.09.2026 in den echten Dateien:

    wm_auto_bets_placed.json   3x status=lost, aufgeloest im Juni     $16,50
    wm_auto_bets_placed.json   1x status=sold                          $5,50
    ------------------------------------------------------------------------
    als „offen" gezaehlt, obwohl seit drei Monaten terminal:          $22,00

Das sind 27,5 % des $80-Deckels, dauerhaft blockiert von Wetten, die laengst abgerechnet
sind — und der Anteil waechst mit jeder aufgeloesten Wette. Solange die Wallet leer war,
fiel es nicht auf. Mit Geld drauf und einem ZWEITEN Verbraucher am selben Deckel (dem
Shortlist-Auto-Play) wuerde es den Handel still abwuergen: kein Fehler, keine Meldung,
nur „Cap erreicht".

Deshalb hier, an EINER Stelle: eine Position ist offen, bis ein **ausdrueckliches**
Terminal-Merkmal dransteht. Fehlt jede Information, gilt sie als offen — bei einem
Risiko-Deckel ist der harmlose Default „blockiert", nicht „frei".
"""
from __future__ import annotations

import json
import os

# Datensaetze auf DERSELBEN Polymarket-Wallet. Wer hier fehlt, wird beim Deckel nicht
# mitgezaehlt und darf faktisch doppelt setzen.
#   wm_/liga_/mls_   — Pinnacle-Edge-Trader (auto_wm_poly_trigger.py)
#   shortlist_       — „Heute spielenswert"-Auto-Play (shortlist_auto_bet.py), 14.09.2026
DATENSATZ_PRAEFIXE = ("wm_", "liga_", "mls_", "shortlist_")

# Ausdrueckliche Terminal-Zustaende. `dry-run` steht hier, weil dabei KEIN Geld floss —
# eine Simulation darf keinen echten Deckel blockieren.
# 21.09.2026: `unbelegt` aus demselben Grund. Eine Zeile, die bewiesen nie die Kasse beruehrt
# hat (`wallet_abgleich.entbuchen`), bindet kein Geld — sie darf den Deckel nicht belegen und
# schon gar nicht als „wieder offen" zurueckkommen.
TERMINAL_STATUS = {"won", "lost", "void", "sold", "closed_manual", "dry-run", "dry_run",
                   "unbelegt"}
TERMINAL_RESULT = {"WIN", "LOSS", "VOID", "UNBELEGT"}


def ist_offen(bet) -> bool:
    """Bindet diese Wette noch Geld? REIN/testbar.

    Offen = KEIN ausdrueckliches Terminal-Merkmal. Unbekanntes gilt als offen.
    """
    if not isinstance(bet, dict):
        return False
    if bet.get("resolved"):            # Altfeld, schreibt niemand — bleibt als Vorsorge
        return False
    if bet.get("soldAt") or bet.get("resolvedAt"):
        return False
    if str(bet.get("result") or "").upper() in TERMINAL_RESULT:
        return False
    if str(bet.get("status") or "").strip().lower() in TERMINAL_STATUS:
        return False
    return True


def offene_summe(bets) -> tuple[float, int]:
    """(Summe der Einsaetze, Anzahl) der noch offenen Wetten. REIN/testbar."""
    summe, n = 0.0, 0
    for b in (bets or []):
        if ist_offen(b):
            try:
                summe += float(b.get("stake") or 0)
            except (TypeError, ValueError):
                continue
            n += 1
    return round(summe, 4), n


def _laden(pfad):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        # Kaputte Datei: der Aufrufer erfaehrt es ueber `unlesbar` und entscheidet selbst.
        return False


def wallet_exposure(base_dir: str, praefixe=None) -> dict:
    """Offene Exposure ueber ALLE Datensatz-Dateien derselben Wallet.

    → {"offen": float, "n": int, "je": {datei: (offen, n)}, "unlesbar": [datei, ...]}

    `unlesbar` ist wichtig: eine kaputte Datei heisst NICHT „keine offenen Positionen".
    Wer den Deckel prueft, muss dann anhalten statt blind weiterzusetzen.
    """
    offen, n, je, unlesbar = 0.0, 0, {}, []
    for pfx in (praefixe or DATENSATZ_PRAEFIXE):
        name = f"{pfx}auto_bets_placed.json"
        d = _laden(os.path.join(base_dir, name))
        if d is None:
            continue                      # Datei gibt es nicht — kein Datensatz, kein Risiko
        if d is False:
            unlesbar.append(name)
            continue
        s, c = offene_summe((d or {}).get("bets") or [])
        if c:
            je[name] = (s, c)
        offen += s
        n += c
    return {"offen": round(offen, 4), "n": n, "je": je, "unlesbar": unlesbar}


def heute_exposure(base_dir: str, tag: str, praefixe=None) -> tuple[float, int]:
    """Summe/Anzahl der HEUTE platzierten Einsaetze ueber alle Datensaetze."""
    summe, n = 0.0, 0
    for pfx in (praefixe or DATENSATZ_PRAEFIXE):
        d = _laden(os.path.join(base_dir, f"{pfx}auto_bets_placed.json"))
        if not isinstance(d, dict):
            continue
        for b in (d.get("bets") or []):
            if not isinstance(b, dict):
                continue
            if str(b.get("placedAt") or "")[:10] == tag:
                try:
                    summe += float(b.get("stake") or 0)
                except (TypeError, ValueError):
                    continue
                n += 1
    return round(summe, 4), n
