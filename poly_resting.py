#!/usr/bin/env python3
"""
poly_resting.py — Register der ruhenden Maker-Orders (19.07.2026, Maker-Lebenszyklus).

Eine ruhende Maker-Limit-Order ist KEINE Position — sie liegt im Buch und wartet auf einen Fill.
Genau deshalb braucht sie ein eigenes Register: der normale Bet-Verlauf (`picks_history` /
`{ds}_auto_bets_placed`) behandelt „placed" als erledigt, aber ein Maker-Order kann noch
unerfüllt sein. Ohne dieses Register wüsste niemand, welche Orders noch offen im Buch liegen und
kurz vor Anpfiff eskaliert (storniert + als Taker nachgelegt) werden müssen.

Datei: `{ds}_poly_resting_orders.json` — Liste von Einträgen:
  orderId, tokenId, price, size, stakeUsdc, market, matchKey, kickoff, placedAt, status

status ∈ resting | filled | escalated | expired | cancelled  (Endzustände außer resting).

Rein I/O + Datenpflege, keine CLOB-Aufrufe → voll testbar ohne Client/Creds.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).resolve().parent


def path() -> Path:
    return D.file("wm_poly_resting_orders.json", "liga_poly_resting_orders.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(p: Path | None = None) -> list:
    p = p or path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("orders", []) if isinstance(data, dict) else (data or [])
    except Exception:
        return []


def save(orders: list, p: Path | None = None) -> None:
    p = p or path()
    p.write_text(json.dumps({"orders": orders, "updatedAt": _now()},
                            ensure_ascii=False, indent=1), encoding="utf-8")


def record(orders: list, entry: dict) -> list:
    """Neue ruhende Order aufnehmen (idempotent über orderId). Rein — gibt die neue Liste zurück."""
    oid = entry.get("orderId")
    out = [o for o in orders if o.get("orderId") != oid]
    out.append({
        "orderId":   oid,
        "tokenId":   entry.get("tokenId"),
        "price":     entry.get("price"),
        "size":      entry.get("size"),
        "stakeUsdc": entry.get("stakeUsdc"),
        "market":    entry.get("market"),
        "matchKey":  entry.get("matchKey"),
        "kickoff":   entry.get("kickoff"),
        "status":    "resting",
        "placedAt":  entry.get("placedAt") or _now(),
        "updatedAt": _now(),
    })
    return out


def set_status(orders: list, order_id: str, status: str, **extra) -> list:
    """Status eines Eintrags fortschreiben (z.B. filled/escalated/expired). Rein."""
    for o in orders:
        if o.get("orderId") == order_id:
            o["status"] = status
            o["updatedAt"] = _now()
            o.update(extra)
    return orders


def active(orders: list) -> list:
    """Nur die noch offenen (ruhenden) Orders — die, die der Monitor prüfen muss."""
    return [o for o in orders if o.get("status") == "resting"]
