#!/usr/bin/env python3
"""
build_poly_wallet_ledger.py — Längsschnitt-Gedächtnis für Polymarket-Wallets (18.07.2026, Lucas).

## Warum

`smart_money` definiert „smart" bisher als **groß + konzentriert** (`topHolderShare`). Das ist ein
Proxy, den jeder benutzt, und er ist schwach: ein Whale kann ein reicher Idiot sein. Größe sagt
nichts über Treffsicherheit.

Polymarket ist ein öffentliches Ledger — jede Wallet hat eine nachprüfbare Historie. Wir holen
Holders und Trades bereits (`fetch_wm_poly_smartmoney.py` → `{ds}_poly_wallets.json`), werfen sie
aber nach der Anzeige weg. Dieses Skript persistiert sie, damit später gilt: **bewiesene Wallets
statt großer Wallets.**

## Warum JETZT und nicht wenn das Signal gebaut wird

Das ist der einzige Baustein, der Zeit verliert. Ein Trade, den wir heute nicht wegschreiben, ist
morgen weg — die Polymarket-API liefert nur das aktuelle Fenster (Top-Holder + jüngste große
Trades), keine vollständige Rückschau. Jeder Tag ohne Sammlung ist ein Tag, den der spätere
Track-Record nicht hat. Deshalb läuft die Sammlung, bevor irgendein Signal sie liest.

## Was gesammelt wird

Zwei Beobachtungstypen, beide mit **Einstiegspreis** — ohne den ist kein CLV rechenbar:

  · **trades**    — aus `bigTradesAll`: wallet, side, price, usd, action(BUY/SELL), ts.
                    Der Goldstandard: exakter Preis zu exaktem Zeitpunkt.
  · **positions** — aus `topPositionsAll`: wallet, side, usd, shares.
                    `avgPrice = usd / shares` ist der **durchschnittliche Einstieg** der Wallet in
                    dieses Outcome. Gröber als ein Trade (mischt mehrere Käufe), aber es deckt die
                    stillen Halter ab, die nie in `bigTrades` auftauchen.

## Auslegung

**Append-only, idempotent.** Das Skript läuft in denselben Takten wie der Smartmoney-Fetch und
darf beliebig oft laufen. Trades sind über (wallet, key, side, ts, usd) eindeutig. Positionen sind
Snapshots einer sich ändernden Größe → pro (wallet, key, side) EIN Eintrag, der `lastSeen`/`usd`/
`shares` fortschreibt und `firstSeen` + `firstAvgPrice` **nie** überschreibt (der erste gesehene
Einstieg ist die ehrlichste CLV-Referenz; spätere Nachkäufe zu schlechteren Preisen sollen den
Track-Record nicht schönen).

Gepruned wird NICHT nach Alter — der historische Bestand ist genau der Wert. Gepruned wird nur,
was nachweislich Müll ist (siehe `_plausible_trade`).

Verwandt: [[project_poly_wallets_tab]], [[project_smart_money_signal]].
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).resolve().parent

# Ein Poly-Preis ist eine Wahrscheinlichkeit. Alles außerhalb ist kaputte Quelle, kein Signal.
MIN_PRICE = 0.01
MAX_PRICE = 0.99
# Darunter ist es kein „Whale", sondern Rauschen — und es bläht den Ledger auf.
MIN_TRADE_USD    = 250.0
MIN_POSITION_USD = 250.0


def ledger_path() -> Path:
    return D.file("wm_poly_wallet_ledger.json", "liga_poly_wallet_ledger.json")


def wallets_path() -> Path:
    return D.file("wm_poly_wallets.json", "liga_poly_wallets.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _plausible_price(p) -> bool:
    try:
        v = float(p)
    except (TypeError, ValueError):
        return False
    return MIN_PRICE <= v <= MAX_PRICE


def _plausible_trade(t: dict) -> bool:
    """Ein Trade ist nur brauchbar, wenn Preis UND Zeitpunkt UND Wallet stehen — sonst ist er
    als CLV-Beobachtung wertlos und würde den Track-Record nur verwässern."""
    if not t.get("wallet") or not t.get("ts") or not t.get("key"):
        return False
    if not _plausible_price(t.get("price")):
        return False
    try:
        return float(t.get("usd") or 0) >= MIN_TRADE_USD
    except (TypeError, ValueError):
        return False


def _trade_id(t: dict) -> str:
    """Eindeutig über Wallet+Markt+Seite+Zeitpunkt+Größe. Der Fetcher liefert dieselben jüngsten
    Trades in jedem Lauf erneut — ohne diesen Schlüssel würde der Ledger sie vervielfachen und
    jede spätere Statistik überzählen."""
    return "|".join(str(t.get(k) or "") for k in ("wallet", "key", "side", "ts", "usd"))


def _position_id(p: dict) -> str:
    return "|".join(str(p.get(k) or "") for k in ("wallet", "key", "side"))


def _avg_price(usd, shares):
    """Durchschnittlicher Einstieg der Wallet. Ohne shares nicht ableitbar → None statt raten."""
    try:
        u, s = float(usd), float(shares)
    except (TypeError, ValueError):
        return None
    if s <= 0:
        return None
    v = round(u / s, 4)
    return v if _plausible_price(v) else None


def collect(snapshot: dict, ledger: dict, now: str | None = None) -> tuple[dict, dict]:
    """Snapshot in den Ledger einarbeiten. Rein — kein I/O, damit testbar.

    Rückgabe: (ledger, stats)."""
    now = now or _now()
    trades    = list(ledger.get("trades") or [])
    positions = dict(ledger.get("positions") or {})

    seen_trades = {_trade_id(t) for t in trades}
    stats = {"tradesNew": 0, "tradesDup": 0, "tradesBad": 0,
             "positionsNew": 0, "positionsUpdated": 0, "positionsBad": 0}

    for t in (snapshot.get("bigTradesAll") or []):
        if not _plausible_trade(t):
            stats["tradesBad"] += 1
            continue
        tid = _trade_id(t)
        if tid in seen_trades:
            stats["tradesDup"] += 1
            continue
        seen_trades.add(tid)
        trades.append({
            "wallet": t.get("wallet"), "key": t.get("key"), "match": t.get("match"),
            "side": t.get("side"), "pick": t.get("pick"),
            "usd": float(t.get("usd")), "price": float(t.get("price")),
            "action": (t.get("action") or "BUY").upper(),
            "ts": t.get("ts"), "seenAt": now,
        })
        stats["tradesNew"] += 1

    for p in (snapshot.get("topPositionsAll") or []):
        avg = _avg_price(p.get("usd"), p.get("shares"))
        try:
            usd = float(p.get("usd") or 0)
        except (TypeError, ValueError):
            usd = 0.0
        if not p.get("wallet") or not p.get("key") or avg is None or usd < MIN_POSITION_USD:
            stats["positionsBad"] += 1
            continue
        pid = _position_id(p)
        prev = positions.get(pid)
        if prev is None:
            positions[pid] = {
                "wallet": p.get("wallet"), "key": p.get("key"), "match": p.get("match"),
                "side": p.get("side"), "pick": p.get("pick"),
                "usd": usd, "shares": float(p.get("shares")), "avgPrice": avg,
                # firstAvgPrice friert den ERSTEN gesehenen Einstieg ein — spätere Nachkäufe zu
                # besseren Preisen dürfen den Track-Record nicht rückwirkend schönen.
                "firstAvgPrice": avg, "firstSeen": now, "lastSeen": now,
            }
            stats["positionsNew"] += 1
        else:
            prev["usd"] = usd
            prev["shares"] = float(p.get("shares"))
            prev["avgPrice"] = avg
            prev["lastSeen"] = now
            prev.setdefault("firstAvgPrice", avg)
            prev.setdefault("firstSeen", now)
            stats["positionsUpdated"] += 1

    ledger["trades"] = trades
    ledger["positions"] = positions
    ledger["updatedAt"] = now
    ledger["dataset"] = D.active_dataset()
    return ledger, stats


def main() -> int:
    snap = _load(wallets_path())
    if not snap:
        # Kein Alarm: Liga hat bewusst kein Poly, und der Mac-Runner läuft nicht durchgehend.
        print(f"ℹ️  {wallets_path().name} fehlt/leer — nichts zu sammeln")
        return 0

    path = ledger_path()
    ledger, stats = collect(snap, _load(path))

    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"📒 {path.name}: +{stats['tradesNew']} Trades "
          f"(dup {stats['tradesDup']}, verworfen {stats['tradesBad']}) · "
          f"+{stats['positionsNew']} Positionen neu, {stats['positionsUpdated']} fortgeschrieben")
    print(f"   Bestand: {len(ledger['trades'])} Trades · {len(ledger['positions'])} Positionen · "
          f"{len({t['wallet'] for t in ledger['trades']} | {p['wallet'] for p in ledger['positions'].values()})} Wallets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
