#!/usr/bin/env python3
"""
poly_entry.py — Maker statt Taker: wie teuer steigen wir auf Polymarket ein? (19.07.2026, Lucas).

## Das Problem

`place_market_order` überquert IMMER den Spread: erst Market-Order (FOK), dann als Fallback eine
Limit-Order bei Midpoint + 2pp. Auf einer Börse ist das die teure Seite. Auf einem dünnen
MLS-Markt mit 4pp Spread zahlen wir jedes Mal ~2pp mehr, als wir müssten — bei Steam-Picks, deren
Preis-Edge ohnehin knapp ist, frisst das die halbe Marge.

## Maker vs Taker

- **Taker** (crossen): kaufe sofort am Ask. Garantierter Fill, aber wir zahlen den Spread.
- **Maker** (ruhen): lege eine Limit-Order oben auf das Gebot (best_bid + 1 Tick). Wird sie
  gefüllt, haben wir den Spread EINGESPART statt bezahlt. Risiko: sie füllt vielleicht nicht.

## Wann was — die eine Regel, die zählt

Ein nicht gefüllter Maker-Order heißt: KEINE Position. Bei einem Steam-Pick ist das fatal — der
ganze Sinn ist, den Move mitzunehmen; verpassen wir den Fill, verpassen wir den Trade. Deshalb:

  · Viel Zeit bis Anpfiff UND fetter Spread → **Maker**. Die Order hat Stunden zu füllen, und der
    eingesparte Spread ist es wert.
  · Nah am Anpfiff ODER enger Spread → **Taker**. Fill-Sicherheit schlägt Spread-Ersparnis; bei
    engem Spread ist ohnehin fast nichts zu holen.

`decide_entry` ist eine REINE Funktion — kein Netzwerk, kein Client, kein Geld. Sie sagt nur:
welcher Modus, welcher Preis, warum. Die Ausführung bleibt in place_market_order und läuft nur,
wenn Lucas `maker_enabled` setzt. Default AUS → bestehendes Taker-Verhalten unverändert.

⚠️ OFFEN (bewusst, siehe CAPABILITIES): Der Lebenszyklus eines RUHENDEN Maker-Orders (stornieren
und als Taker nachlegen, wenn er bis kurz vor Anpfiff nicht füllt) ist noch nicht gebaut. Solange
das fehlt, bleibt `maker_enabled` aus — sonst läge Geld still in unerfüllten Orders und ein
verpasster Move fiele niemandem auf. Das ist der Grund, warum der Default-Wert AUS ist.
"""
from __future__ import annotations

from dataclasses import dataclass

TICK = 0.01   # kleinste Poly-Preisstufe (1 Cent)


@dataclass
class EntryConfig:
    maker_enabled: bool = False    # Default AUS — Lucas aktiviert, wenn der Order-Lebenszyklus steht
    maker_min_hours: float = 3.0   # so viel Zeit muss die ruhende Order zum Füllen haben
    maker_min_spread_pp: float = 3.0   # darunter lohnt der Maker-Aufwand nicht
    taker_buffer_pp: float = 2.0   # Taker crosst um so viel über das Ask (Fill-Priorität)
    max_price: float = 0.97        # nie teurer einsteigen (darüber kaum Ertrag, hohes Downside)


def _clamp(p: float) -> float:
    return max(TICK, min(0.99, round(p, 2)))


def decide_entry(fair: float, best_bid, best_ask, hours_to_ko,
                 cfg: EntryConfig | None = None) -> dict:
    """Entscheidet Einstiegs-Modus + -Preis.

    fair:        unsere Preis-Schätzung / Poly-Midpoint (0-1)
    best_bid/ask: Orderbuch-Spitze (0-1) oder None, wenn keine Tiefe erfasst
    hours_to_ko:  Stunden bis Anpfiff (kann negativ sein = läuft schon) oder None
    Rückgabe: {mode, price, reason}
    """
    cfg = cfg or EntryConfig()

    # Ohne belastbaren fairen Preis nichts erfinden — Aufrufer fällt auf sein price_hint zurück.
    if not (fair and 0 < fair < 1):
        return {"mode": "taker", "price": None, "reason": "kein fairer Preis → Aufrufer-Fallback"}

    spread_pp = None
    if best_bid and best_ask and best_ask > best_bid:
        spread_pp = (best_ask - best_bid) * 100

    # Taker-Preis: crosse das Ask (oder fair) plus Puffer → sicherer Fill.
    taker_anchor = best_ask if (best_ask and 0 < best_ask < 1) else fair
    taker_price  = _clamp(min(cfg.max_price, taker_anchor + cfg.taker_buffer_pp / 100))

    # Maker nur wenn AKTIV, genug Zeit, Spread bekannt und breit genug.
    if not cfg.maker_enabled:
        return {"mode": "taker", "price": taker_price, "reason": "maker_enabled=false (Default)"}
    if hours_to_ko is None or hours_to_ko < cfg.maker_min_hours:
        return {"mode": "taker", "price": taker_price,
                "reason": f"zu nah am Anpfiff ({hours_to_ko}h < {cfg.maker_min_hours}h) → Fill-Sicherheit"}
    if spread_pp is None:
        return {"mode": "taker", "price": taker_price, "reason": "keine Orderbuch-Tiefe → kein Maker-Preis"}
    if spread_pp < cfg.maker_min_spread_pp:
        return {"mode": "taker", "price": taker_price,
                "reason": f"Spread {spread_pp:.1f}pp zu eng — nichts zu sparen"}

    # Maker: oben auf das Gebot, einen Tick besser → Priorität im Buch, ohne zu crossen.
    maker_price = _clamp(min(cfg.max_price, best_bid + TICK))
    # Sicherung: der Maker-Preis darf nie das Ask erreichen (sonst wären wir doch Taker).
    if best_ask and maker_price >= best_ask:
        return {"mode": "taker", "price": taker_price,
                "reason": "Maker-Preis würde crossen → gleich als Taker"}
    return {"mode": "maker", "price": maker_price,
            "reason": f"Spread {spread_pp:.1f}pp, {hours_to_ko:.1f}h Zeit → ruhen, Spread einsparen"}
