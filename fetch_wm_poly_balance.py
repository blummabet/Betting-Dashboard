#!/usr/bin/env python3
"""
fetch_wm_poly_balance.py — Polymarket USDC Balance via py-clob-client-v2
=========================================================================
Verwendet dieselbe ClobClient-Initialisierung wie polymarket_bet.py —
die einzige Version die wir wissen dass sie mit dem Self-hosted Runner funktioniert.

Env-Variablen (alle als GitHub Secret hinterlegt):
    POLY_PRIVATE_KEY      — EOA Private Key
    POLY_FUNDER_ADDRESS   — Proxy-Wallet-Adresse
    POLY_API_KEY          — CLOB API Key
    POLY_API_SECRET       — CLOB API Secret
    POLY_API_PASSPHRASE   — CLOB API Passphrase

Schreibt wm_poly_balance.json:
  {
    "usdc":       123.45,
    "usdc_e":     0.00,
    "total":      123.45,
    "address":    "0x...",
    "updatedAt":  "2026-06-12T08:00:00+00:00"
  }
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE      = Path(__file__).parent
# DATASET-AWARE (12.07.2026, Lucas: „MLS auf Polymarket"). auto_wm_poly_trigger + polymarket_bet
# lesen BALANCE_FILE bereits per D.file → mls_poly_balance.json. Ohne diese Umstellung hätte der
# MLS-Trader die Balance-Datei nie gefunden (Guthaben-Check → Trade-Blockade).
import cocobet_dataset as D  # noqa: E402
OUT_FILE  = Path(str(D.file("wm_poly_balance.json", "liga_poly_balance.json")))
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID  = 137  # Polygon


def _save(usdc: float, usdc_e: float, address: str, error: str | None = None,
          positions: float | None = None):
    now = datetime.now(timezone.utc).isoformat()
    # 22.07.2026 (Lucas: „Balance passt nicht — sind 122,96, nicht 99,93"): `usdc` ist NUR das freie
    # CLOB-Collateral (was man setzen kann). Das echte Wallet-Guthaben = frei + Wert der OFFENEN
    # Positionen. `total` bildet jetzt das Wallet-Equity ab (= was Polymarket anzeigt); `usdc` bleibt
    # unverändert die Sizing-Grundlage (gesperrtes Positionsgeld ist nicht setzbar).
    pos = round(positions, 4) if positions is not None else 0.0
    out = {
        "usdc":      round(usdc,   4),   # freies Collateral → Bet-Sizing
        "usdc_e":    round(usdc_e, 4),
        "positions": pos,                # Marktwert der offenen Positionen
        "total":     round(usdc + usdc_e + pos, 4),   # Wallet-Equity (Header)
        "address":   address,
        "updatedAt": now,
    }
    if error:
        out["error"] = error
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2)
    return out


def _load_existing() -> dict:
    if OUT_FILE.exists():
        try:
            return json.loads(OUT_FILE.read_text())
        except Exception:
            pass
    return {"usdc": 0.0, "usdc_e": 0.0, "total": 0.0}


def _build_client(private_key: str, funder_addr: str,
                   api_key: str, api_secret: str, api_passphrase: str):
    """Baut ClobClient genau wie polymarket_bet.py."""
    from py_clob_client_v2.client import ClobClient
    from py_clob_client_v2.clob_types import ApiCreds
    from py_clob_client_v2 import SignatureTypeV2

    client_kwargs = dict(
        host=CLOB_HOST,
        key=private_key,
        chain_id=CHAIN_ID,
        signature_type=SignatureTypeV2.POLY_PROXY,
    )
    if funder_addr:
        client_kwargs["funder"] = funder_addr

    client = ClobClient(**client_kwargs)
    creds  = ApiCreds(api_key=api_key, api_secret=api_secret,
                      api_passphrase=api_passphrase)
    print(f"  🔑 API Creds: Key={api_key[:8]}… Addr={funder_addr[:16]}…")
    try:
        client.set_api_creds(creds)
    except AttributeError:
        client_kwargs["creds"] = creds
        client = ClobClient(**client_kwargs)

    return client


def _extract_balance(resp) -> float | None:
    """Extrahiert float-Balance aus verschiedenen Response-Formaten."""
    if resp is None:
        return None
    if isinstance(resp, (int, float)):
        return float(resp)
    if isinstance(resp, dict):
        for key in ("balance", "available", "allowance", "amount"):
            if key in resp and resp[key] is not None:
                return float(resp[key])
        # Falls Response ein Array ist: summieren
        for key in ("balances", "items"):
            if key in resp and isinstance(resp[key], list):
                total = sum(float(x.get("balance", 0)) for x in resp[key])
                return total
    if isinstance(resp, list):
        return sum(float(x.get("balance", 0)) for x in resp if isinstance(x, dict))
    return None


def _l2_headers(api_key: str, api_secret: str, api_passphrase: str,
                address: str, method: str, path: str, body: str = "") -> dict:
    """
    Baut Polymarket CLOB L2 Auth Headers.
    api_secret ist base64-encoded (Standard oder URL-safe).
    """
    import base64, hashlib, hmac as _hmac, time

    ts  = str(int(time.time()))
    msg = (ts + method.upper() + path + body).encode("utf-8")

    # api_secret: URL-safe base64 → standard base64 → decode
    secret_str = api_secret.replace("-", "+").replace("_", "/")
    pad = 4 - len(secret_str) % 4
    if pad != 4:
        secret_str += "=" * pad
    try:
        secret_bytes = base64.b64decode(secret_str)
    except Exception:
        secret_bytes = api_secret.encode("utf-8")  # raw fallback

    sig = base64.b64encode(
        _hmac.new(secret_bytes, msg, hashlib.sha256).digest()
    ).decode("utf-8")

    return {
        "POLY-API-KEY":    api_key,
        "POLY-TIMESTAMP":  ts,
        "POLY-NONCE":      "0",
        "POLY-SIGNATURE":  sig,
        "POLY-PASSPHRASE": api_passphrase,
        "POLY_ADDRESS":    address,
        "Content-Type":    "application/json",
        "Accept":          "application/json",
        "User-Agent":      "CocoBet/1.0",
    }


def fetch_balance_via_clob_client(private_key: str, funder_addr: str,
                                   api_key: str, api_secret: str,
                                   api_passphrase: str) -> float | None:
    """
    Verwendet py-clob-client-v2 ClobClient — genau wie polymarket_bet.py.
    """
    try:
        from py_clob_client_v2.client import ClobClient
        from py_clob_client_v2.clob_types import ApiCreds
        from py_clob_client_v2 import SignatureTypeV2
    except ImportError as e:
        print(f"  ❌ py-clob-client-v2 nicht verfügbar: {e}")
        return None

    client = _build_client(private_key, funder_addr, api_key, api_secret, api_passphrase)

    import types

    # ── Versuch 1: BalanceAllowanceParams aus der Library (falls vorhanden) ───
    try:
        from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        print(f"  📡 Versuche get_balance_allowance(BalanceAllowanceParams(COLLATERAL))…")
        resp = client.get_balance_allowance(params=params)
        print(f"  📦 Response: {str(resp)[:300]}")
        bal = _extract_balance(resp)
        if bal is not None:
            # M1 Fix 05.06.2026: bal ist Roh-Wert (6 Dezimalstellen USDC) — als
            # decimal anzeigen damit Log-Ausgabe nicht "$307261984" sondern "$307.26" zeigt
            print(f"  ✅ Balance via BalanceAllowanceParams: ${bal/1_000_000:.2f} USDC  (raw: {int(bal)})")
            return bal
    except ImportError:
        pass  # BalanceAllowanceParams existiert nicht → weiter mit SimpleNamespace
    except Exception as e:
        print(f"  ⚠️  BalanceAllowanceParams fehlgeschlagen: {e}")

    # ── Versuch 2: SimpleNamespace mit asset_type Attribut ────────────────────
    # get_balance_allowance macht intern params.asset_type → wir simulieren das
    from py_clob_client_v2.clob_types import AssetType

    for asset_val in [AssetType.COLLATERAL, AssetType.CONDITIONAL,
                      "COLLATERAL", "CONDITIONAL", "USDC"]:
        try:
            params = types.SimpleNamespace(asset_type=asset_val)
            print(f"  📡 Versuche SimpleNamespace(asset_type={asset_val!r})…")
            resp = client.get_balance_allowance(params=params)
            print(f"  📦 Response: {str(resp)[:300]}")
            bal = _extract_balance(resp)
            if bal is not None:
                # M1 Fix: decimal-USDC anzeigen statt Roh-Mikrowert
                print(f"  ✅ Balance via SimpleNamespace({asset_val!r}): ${bal/1_000_000:.2f} USDC  (raw: {int(bal)})")
                return bal
        except Exception as e:
            print(f"  ⚠️  SimpleNamespace({asset_val!r}) fehlgeschlagen: {e}")

    return None


POSITIONS_URL = "https://data-api.polymarket.com/positions?user={user}&sizeThreshold=0.01"


def fetch_positions_value(address: str) -> float | None:
    """Marktwert aller offenen Wallet-Positionen (data-api /positions). Bevorzugt `currentValue`,
    fällt auf size×curPrice zurück. None = API-Fehler (Aufrufer behält alte Zahl), 0.0 = keine
    Positionen. Read-only — kein Handel."""
    import urllib.request
    if not address:
        return None
    url = POSITIONS_URL.format(user=address)
    req = urllib.request.Request(url, headers={"User-Agent": "BetEdge/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = json.loads(r.read())
    except Exception as e:
        print(f"  ⚠️  Positions-Fetch fehlgeschlagen: {e}")
        return None
    rows = raw if isinstance(raw, list) else (raw.get("positions") or raw.get("data") or [])
    total = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        cv = row.get("currentValue")
        try:
            if cv is not None:
                total += float(cv)
                continue
        except (TypeError, ValueError):
            pass
        # Fallback: size × curPrice
        try:
            sz = float(row.get("size") or row.get("shares") or 0)
            px = float(row.get("curPrice") or row.get("current_price") or 0)
            total += sz * px
        except (TypeError, ValueError):
            continue
    print(f"  📊 Offene Positionen: ${total:.2f} (in {len(rows)} Positionen)")
    return round(total, 4)


def main():
    now_utc = datetime.now(timezone.utc)
    print(f"💰  fetch_wm_poly_balance.py — py-clob-client-v2")
    print(f"    Zeit: {now_utc.isoformat()[:19]} UTC\n")

    private_key    = os.environ.get("POLY_PRIVATE_KEY",    "").strip()
    funder_addr    = os.environ.get("POLY_FUNDER_ADDRESS", "").strip()
    api_key        = os.environ.get("POLY_API_KEY",        "").strip()
    api_secret     = os.environ.get("POLY_API_SECRET",     "").strip()
    api_passphrase = os.environ.get("POLY_API_PASSPHRASE", "").strip()

    missing = [k for k, v in {
        "POLY_PRIVATE_KEY": private_key,
        "POLY_FUNDER_ADDRESS": funder_addr,
        "POLY_API_KEY": api_key,
    }.items() if not v]

    if missing:
        print(f"  ❌ Fehlende Env-Variablen: {', '.join(missing)}")
        existing = _load_existing()
        _save(existing.get("usdc", 0.0), existing.get("usdc_e", 0.0),
              funder_addr or existing.get("address", ""),
              error=f"Missing env: {', '.join(missing)}",
              positions=existing.get("positions"))
        return

    balance_raw = fetch_balance_via_clob_client(
        private_key, funder_addr, api_key, api_secret, api_passphrase
    )

    if balance_raw is None:
        print(f"\n⚠️   Balance-Fetch fehlgeschlagen — bestehende Balance wird behalten")
        existing = _load_existing()
        _save(existing.get("usdc", 0.0), existing.get("usdc_e", 0.0),
              funder_addr, error="fetch_failed",
              positions=existing.get("positions"))
        return

    # USDC hat 6 Dezimalstellen — API gibt Rohwert in kleinster Einheit zurück
    # z.B. 501624 → $0.501624 USDC
    USDC_DECIMALS = 1_000_000
    balance = balance_raw / USDC_DECIMALS

    # Wert der offenen Positionen dazu — echtes Wallet-Guthaben = frei + Positionen.
    positions = fetch_positions_value(funder_addr)
    if positions is None:   # API-Fehler → alten Positions-Wert behalten, nicht auf 0 fallen
        positions = _load_existing().get("positions")

    out = _save(balance, 0.0, funder_addr, positions=positions)
    print(f"\n✅  {OUT_FILE.name} geschrieben")
    print(f"    Frei (setzbar): ${out['usdc']:.2f}  +  Positionen: ${out['positions']:.2f}  "
          f"=  Wallet-Equity: ${out['total']:.2f} USDC")


if __name__ == "__main__":
    main()
