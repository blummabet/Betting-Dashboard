#!/usr/bin/env python3
"""
fetch_wm_poly_smartmoney.py — Polymarket Geld-/Wallet-Verteilung pro Spiel (19.06.2026, Lucas)

Für jedes WM-Fixture den 1X2-Geld-Split + Big-Wallet-Konzentration aus der Polymarket data-api
(/holders je Outcome-Token). Liest die Tokens + Preise aus wm_poly_prices.json (hwTokens/drTokens/
awTokens + poly_hw/dr/aw), holt je Token die Holder, aggregiert:
  outcomes[home|draw|away] = {usd, share, topHolderShare, holders}
  + totalUsd, topTraders (# Wallets ≥ big_trader_usd)
→ wm_poly_smartmoney.json {matches:{HOME-AWAY:{...}}, updatedAt}.

Speist das (NIEDRIG gewichtete) smart_money-Signal + die violette Card-Box. Schreibt IMMER
(auch partiell/leer), damit das Signal robust None liefert wenn nichts da ist.

WICHTIG: Polymarket ist geoblockt — läuft NUR auf dem Mac-Runner (wie clob/gamma). Vom Sandbox
nicht testbar. Holders-Endpoint-Param ggf. am ersten Live-Lauf justieren (Log zeigt rohe Antwort).

Run (Runner):  python3 fetch_wm_poly_smartmoney.py
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
PRICES_FILE = BASE / "wm_poly_prices.json"
OUT_FILE    = BASE / "wm_poly_smartmoney.json"
HOLDERS_URL = "https://data-api.polymarket.com/holders?market={token}&limit=200"

TOP_N           = 10        # für topHolderShare
BIG_TRADER_USD  = 1000      # Wallet ab $ = „Top-Trader"
HOLDERS_TIMEOUT = 15


def _http_get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "BetEdge/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HOLDERS_TIMEOUT) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  HTTP error {url[:70]}…: {e}")
        return None


def _parse_holders(data):
    """Robust: akzeptiert [..] oder {holders:[..]} mit {proxyWallet, amount}. → [(wallet, amount)]."""
    rows = data.get("holders") if isinstance(data, dict) else data
    out = []
    for h in (rows or []):
        if not isinstance(h, dict):
            continue
        w = h.get("proxyWallet") or h.get("proxy_wallet") or h.get("wallet")
        a = h.get("amount") or h.get("size") or h.get("balance")
        try:
            a = float(a)
        except (TypeError, ValueError):
            continue
        if w and a > 0:
            out.append((w, a))
    return out


def _outcome_smartmoney(token: str, price):
    """{usd, topHolderShare, holders, _big, _wallets} oder None (kein Token/Buch)."""
    if not token or not isinstance(price, (int, float)) or price <= 0:
        return None
    data = _http_get(HOLDERS_URL.format(token=token))
    holders = _parse_holders(data)
    if not holders:
        return None
    amounts = sorted((a for _, a in holders), reverse=True)
    tot_amt = sum(amounts)
    usd = tot_amt * float(price)             # Shares × $/Share = $-Wert der Positionen
    top = sum(amounts[:TOP_N]) / tot_amt if tot_amt > 0 else 0.0
    big = sum(1 for _, a in holders if a * float(price) >= BIG_TRADER_USD)
    return {"usd": round(usd, 0), "topHolderShare": round(top, 3),
            "holders": len(holders), "_big": big}


def main():
    if not PRICES_FILE.exists():
        print("⚠️  wm_poly_prices.json fehlt — nichts zu tun."); return
    fixtures = json.loads(PRICES_FILE.read_text(encoding="utf-8")).get("allFixtures", [])
    matches = {}
    n_ok = 0
    for fx in fixtures:
        key = fx.get("key")
        if not key:
            continue
        legs = {
            "home": ((fx.get("hwTokens") or [None])[0], fx.get("poly_hw")),
            "draw": ((fx.get("drTokens") or [None])[0], fx.get("poly_dr")),
            "away": ((fx.get("awTokens") or [None])[0], fx.get("poly_aw")),
        }
        outcomes, total, top_traders = {}, 0.0, 0
        for side, (tok, price) in legs.items():
            sm = _outcome_smartmoney(tok, price)
            if sm:
                outcomes[side] = sm
                total += sm["usd"]
                top_traders += sm.pop("_big")
        if not outcomes or total <= 0:
            continue
        for side, o in outcomes.items():
            o["share"] = round(o["usd"] / total, 3)
        matches[key] = {"totalUsd": round(total, 0), "topTraders": top_traders,
                        "outcomes": outcomes}
        n_ok += 1
        print(f"  ✅ {key}: ${total/1e6:.2f}M · "
              + " · ".join(f"{s} {o['share']*100:.0f}%" for s, o in outcomes.items()))

    OUT_FILE.write_text(json.dumps(
        {"matches": matches, "updatedAt": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 {n_ok}/{len(fixtures)} Spiele mit Smart-Money → {OUT_FILE.name}")


if __name__ == "__main__":
    main()
