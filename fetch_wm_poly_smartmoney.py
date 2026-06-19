#!/usr/bin/env python3
"""
fetch_wm_poly_smartmoney.py — Polymarket Geld-/Wallet-Verteilung pro Spiel (19.06.2026, Lucas)

Für jedes WM-Fixture den 1X2-Geld-Split + Big-Wallet-Konzentration aus der Polymarket data-api.
data-api `/holders?market=<conditionId>` (conditionId, NICHT Token-ID!) liefert je Outcome-Binär
die Holder gruppiert nach Token: [{token, holders:[{proxyWallet, amount, outcomeIndex}]}]. Wir
nehmen je Outcome (home/draw/away) die Holder-Gruppe des YES-Tokens (=hwTokens[0]/drTokens[0]/
awTokens[0]) und aggregieren:
  outcomes[home|draw|away] = {usd, share, topHolderShare, holders}
  + totalUsd, topTraders (# Wallets ≥ big_trader_usd)
→ wm_poly_smartmoney.json {matches:{HOME-AWAY:{...}}, updatedAt}.

Braucht hwCondition/drCondition/awCondition + hwTokens/.. + poly_hw/dr/aw aus wm_poly_prices.json
(alle von fetch_wm_poly_prices.py geschrieben). Speist das (NIEDRIG gewichtete) smart_money-Signal
+ die violette Card-Box. Schreibt IMMER (auch partiell/leer) → Signal liefert robust None.

WICHTIG: Polymarket ist geoblockt — läuft NUR auf dem Mac-Runner (wie clob/gamma). Vom Sandbox
nicht testbar. Endpoint-Form: shaunlebron gist (Polymarket Data API Docs), /holders.

Run (Runner):  python3 fetch_wm_poly_smartmoney.py
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _kickoff_passed(fx):
    """True wenn der Anpfiff vorbei ist → Spiel gelaufen/in-play. Dann sind die offenen
    Positionen Phantom (gewonnene Wetten vor Redeem) → nicht als Smart-Money zählen.
    Fehlender/unparsebarer kickoff → False (nicht versehentlich alles überspringen)."""
    ko = fx.get("kickoff")
    if not ko:
        return False
    try:
        kt = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        return datetime.now(timezone.utc) >= kt
    except Exception:
        return False

BASE = Path(__file__).parent
PRICES_FILE = BASE / "wm_poly_prices.json"
OUT_FILE    = BASE / "wm_poly_smartmoney.json"
HOLDERS_URL = "https://data-api.polymarket.com/holders?market={cond}&limit=200"

TOP_N           = 10        # für topHolderShare
BIG_TRADER_USD  = 1000      # Wallet ab $ = „Top-Trader"
HOLDERS_TIMEOUT = 15
MIN_WRITE_USD   = 5000      # darunter ($0.00M-Platzhalter/gelaufene Spiele) NICHT schreiben


def _http_get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "BetEdge/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HOLDERS_TIMEOUT) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  HTTP error {url[:70]}…: {e}")
        return None


def _holders_for_token(data, yes_token):
    """Aus der /holders-Antwort (Liste von {token, holders}) die Holder-Liste des YES-Tokens
    ziehen. → [(wallet, amount)]. Fallback: flache Liste, falls Format abweicht."""
    groups = data if isinstance(data, list) else (data.get("holders") if isinstance(data, dict) else None)
    rows = None
    yt = str(yes_token)
    for g in (groups or []):
        if isinstance(g, dict) and "holders" in g:          # gruppiert {token, holders:[...]}
            if str(g.get("token")) == yt:
                rows = g.get("holders"); break
        else:                                                # bereits flache Holder-Liste
            rows = groups; break
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


def _outcome_smartmoney(condition: str, yes_token: str, price):
    """{usd, topHolderShare, holders, _big} oder None. condition=conditionId (0x…), yes_token=clobTokenId."""
    if not condition or not yes_token or not isinstance(price, (int, float)) or price <= 0:
        return None
    data = _http_get(HOLDERS_URL.format(cond=condition))
    holders = _holders_for_token(data, yes_token)
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
    if fixtures and not any(fx.get("hwCondition") for fx in fixtures):
        print("⚠️  Keine conditionId in wm_poly_prices.json — fetch_wm_poly_prices.py muss "
              "ZUERST laufen (schreibt hwCondition/drCondition/awCondition). Manuell testen: "
              "erst Preise, dann Smart-Money.")
    matches = {}
    n_ok = 0
    n_skip_ko = 0
    for fx in fixtures:
        key = fx.get("key")
        if not key:
            continue
        if _kickoff_passed(fx):
            n_skip_ko += 1
            continue   # gelaufen/in-play → offenes Interesse ist Phantom
        legs = {
            "home": (fx.get("hwCondition"), (fx.get("hwTokens") or [None])[0], fx.get("poly_hw")),
            "draw": (fx.get("drCondition"), (fx.get("drTokens") or [None])[0], fx.get("poly_dr")),
            "away": (fx.get("awCondition"), (fx.get("awTokens") or [None])[0], fx.get("poly_aw")),
        }
        outcomes, total, top_traders = {}, 0.0, 0
        for side, (cond, tok, price) in legs.items():
            sm = _outcome_smartmoney(cond, tok, price)
            if sm:
                outcomes[side] = sm
                total += sm["usd"]
                top_traders += sm.pop("_big")
        if not outcomes or total < MIN_WRITE_USD:
            continue   # $0.00M-Platzhalter → nicht schreiben
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
    print(f"\n💾 {n_ok}/{len(fixtures)} Spiele mit Smart-Money "
          f"({n_skip_ko} gelaufen übersprungen) → {OUT_FILE.name}")


if __name__ == "__main__":
    main()
