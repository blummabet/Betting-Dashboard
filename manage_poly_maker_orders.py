#!/usr/bin/env python3
"""
manage_poly_maker_orders.py — Lebenszyklus der ruhenden Maker-Orders (19.07.2026, Lucas).

## Wozu

`poly_entry` legt bei viel Zeit + breitem Spread eine RUHENDE Limit-Order oben aufs Gebot, statt
den Spread zu crossen. Das spart Spread — kostet aber Fill-Sicherheit: liegt die Order bis kurz
vor Anpfiff unerfüllt im Buch, hätten wir den Steam-Move verpasst. GENAU dieses Loch schließt
dieser Monitor. Er ist der Grund, warum `maker_enabled` jetzt überhaupt aktivierbar ist.

## Was er tut (alle 30min am Mac-Runner, wie manage_wm_poly_positions)

Für jede ruhende Order aus `{ds}_poly_resting_orders.json`:
  1. Fill-Status abfragen. Gefüllt → als `filled` markieren (ist jetzt eine Position, fertig).
  2. Sonst Rest-Zeit bis Anpfiff berechnen und `poly_entry.decide_maker_action` fragen:
     · `escalate_taker` → Order **stornieren** und sofort als **Taker** neu platzieren (crossen,
       garantierter Fill). Das ist der Kern: der Move darf uns nicht durchrutschen.
     · `cancel_expired` → Anpfiff vorbei → **stornieren**, kein Nachlegen (nicht ins laufende Spiel).
     · `wait` → offen lassen, der Spread ist die Wartezeit wert.

## Sicherheit / Rollen

Ich (der Agent) platziere/storniere NICHTS selbst — dieser Code läuft auf Lucas' Mac-Runner unter
`maker_enabled`. Die Entscheidung (`decide_maker_action`) ist rein und getestet; die CLOB-Aufrufe
(`_get_fill_status`, `_cancel_order`) sind dünne, defensiv gewrappte Adapter. Die Kernschleife
`reconcile()` bekommt Client + place-Funktion INJIZIERT → voll testbar ohne Creds/Netz.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import cocobet_dataset as D
import poly_entry
import poly_resting


def _hours_to_ko(kickoff_iso, now):
    if not kickoff_iso:
        return None
    try:
        ko = datetime.fromisoformat(str(kickoff_iso).replace("Z", "+00:00"))
        return (ko - now).total_seconds() / 3600
    except Exception:
        return None


def _get_fill_status(client, order_id) -> str:
    """CLOB-Order-Status → 'filled' | 'open' | 'gone'. Defensiv: unterschiedliche Client-Versionen
    benennen die Methode/Felder anders. Im Zweifel 'open' (lieber weiter beobachten als blind
    stornieren)."""
    getter = getattr(client, "get_order", None) or getattr(client, "get_order_by_id", None)
    if not getter:
        return "open"
    try:
        o = getter(order_id) or {}
    except Exception:
        return "open"
    if isinstance(o, dict):
        st = str(o.get("status") or o.get("state") or "").lower()
        if st in ("matched", "filled", "complete", "completed"):
            return "filled"
        if st in ("canceled", "cancelled", "expired"):
            return "gone"
        try:
            size = float(o.get("original_size") or o.get("size") or 0)
            matched = float(o.get("size_matched") or o.get("matched") or 0)
            if size > 0 and matched >= size - 1e-9:
                return "filled"
        except (TypeError, ValueError):
            pass
    return "open"


def _cancel_order(client, order_id) -> bool:
    for name in ("cancel", "cancel_order"):
        fn = getattr(client, name, None)
        if fn:
            try:
                fn(order_id)
                return True
            except Exception as e:
                print(f"  ⚠️  Stornieren fehlgeschlagen ({name}: {e})")
                return False
    print("  ⚠️  Client kennt keine cancel-Methode")
    return False


def reconcile(orders: list, client, place_fn, now=None, cfg=None) -> tuple[list, dict]:
    """Kernschleife. REIN bis auf die injizierten client/place_fn → testbar mit Fakes.

    place_fn(order_record) platziert die Order neu als Taker und gibt {status, orderId, ...} zurück.
    Rückgabe: (aktualisierte Order-Liste, stats)."""
    now = now or datetime.now(timezone.utc)
    cfg = cfg or poly_entry.EntryConfig()
    stats = {"filled": 0, "escalated": 0, "expired": 0, "wait": 0, "gone": 0}

    for o in poly_resting.active(orders):
        oid = o.get("orderId")
        st = _get_fill_status(client, oid)
        if st == "filled":
            poly_resting.set_status(orders, oid, "filled")
            stats["filled"] += 1
            continue
        if st == "gone":
            # Von der Börse schon weg (extern storniert/abgelaufen) — nicht doppelt anfassen.
            poly_resting.set_status(orders, oid, "cancelled")
            stats["gone"] += 1
            continue

        act = poly_entry.decide_maker_action(False, _hours_to_ko(o.get("kickoff"), now), cfg)["action"]
        if act == "wait":
            stats["wait"] += 1
            continue
        if act == "cancel_expired":
            _cancel_order(client, oid)
            poly_resting.set_status(orders, oid, "expired")
            stats["expired"] += 1
            continue
        if act == "escalate_taker":
            # ERST stornieren, DANN als Taker neu — nie beide Orders gleichzeitig offen
            # (sonst doppelte Position bei gleichzeitigem Fill).
            if not _cancel_order(client, oid):
                stats["wait"] += 1        # Storno gescheitert → nächster Lauf erneut, nicht doppelt platzieren
                continue
            res = place_fn(o) or {}
            poly_resting.set_status(orders, oid, "escalated",
                                    escalatedTo=res.get("orderId"), escalateStatus=res.get("status"))
            stats["escalated"] += 1
    return orders, stats


# ── CLOB-Glue (nur am Runner) ────────────────────────────────────────────────

def _build_client(private_key: str):
    from py_clob_client_v2.client import ClobClient
    from py_clob_client_v2 import SignatureTypeV2
    kwargs = dict(host="https://clob.polymarket.com", key=private_key, chain_id=137,
                  signature_type=SignatureTypeV2.POLY_PROXY)
    funder = os.environ.get("POLY_FUNDER_ADDRESS", "").strip()
    if funder:
        kwargs["funder"] = funder
    return ClobClient(**kwargs)


def _taker_replace_fn(private_key: str):
    """Gibt eine place_fn zurück, die eine Order als Taker (force_taker) neu platziert."""
    import polymarket_bet as PB

    def _place(o):
        return PB.place_market_order(o.get("tokenId"), float(o.get("stakeUsdc") or 0),
                                     private_key, price_hint=o.get("price"), force_taker=True)
    return _place


def main() -> int:
    if str(_cfg_maker_enabled()).lower() not in ("1", "true", "yes"):
        print("ℹ️  maker_enabled=false — Lebenszyklus-Monitor macht nichts.")
        return 0
    orders = poly_resting.load()
    if not poly_resting.active(orders):
        print("ℹ️  Keine ruhenden Maker-Orders.")
        return 0
    private_key = os.environ.get("POLY_PRIVATE_KEY", "").strip()
    if not private_key:
        print("❌ POLY_PRIVATE_KEY nicht gesetzt")
        return 1

    client = _build_client(private_key)
    orders, stats = reconcile(orders, client, _taker_replace_fn(private_key))
    poly_resting.save(orders)
    print(f"🅼 Maker-Lebenszyklus: {stats['filled']} gefüllt · {stats['escalated']} → Taker · "
          f"{stats['expired']} abgelaufen · {stats['wait']} warten · {stats['gone']} extern weg")
    return 0


def _cfg_maker_enabled():
    try:
        raw = json.loads((poly_resting.BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        return raw.get("trade", {}).get("maker_enabled", False)
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(main())
