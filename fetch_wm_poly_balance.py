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
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE      = Path(__file__).parent
OUT_FILE  = BASE / "wm_poly_balance.json"
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID  = 137  # Polygon


def _save(usdc: float, usdc_e: float, address: str, error: str | None = None):
    now = datetime.now(timezone.utc).isoformat()
    out = {
        "usdc":      round(usdc,   4),
        "usdc_e":    round(usdc_e, 4),
        "total":     round(usdc + usdc_e, 4),
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

    # ── Versuch 1: AssetType.USDC direkt (kein list() → kein Crash) ──────────
    try:
        from py_clob_client_v2.clob_types import AssetType
        # Zeige alle class-Attribute (für Debugging)
        attrs = {k: getattr(AssetType, k) for k in dir(AssetType)
                 if not k.startswith("_")}
        print(f"  📡 AssetType Attribute: {attrs}")

        # Direkt AssetType.USDC verwenden
        usdc_val = getattr(AssetType, "USDC", None)
        if usdc_val is not None:
            print(f"  📡 Versuche get_balance_allowance(params=AssetType.USDC={usdc_val!r})…")
            resp = client.get_balance_allowance(params=usdc_val)
            print(f"  📦 Response: {str(resp)[:300]}")
            bal = _extract_balance(resp)
            if bal is not None:
                print(f"  ✅ Balance via AssetType.USDC: ${bal:.4f}")
                return bal
    except Exception as e:
        print(f"  ⚠️  AssetType.USDC fehlgeschlagen: {e}")

    # ── Versuch 2: Alle anderen AssetType-Attribute durchprobieren ────────────
    try:
        from py_clob_client_v2.clob_types import AssetType
        for attr_name in [a for a in dir(AssetType) if not a.startswith("_")]:
            val = getattr(AssetType, attr_name)
            try:
                print(f"  📡 Versuche get_balance_allowance(params=AssetType.{attr_name}={val!r})…")
                resp = client.get_balance_allowance(params=val)
                print(f"  📦 Response: {str(resp)[:200]}")
                bal = _extract_balance(resp)
                if bal is not None:
                    print(f"  ✅ Balance via AssetType.{attr_name}: ${bal:.4f}")
                    return bal
            except Exception as e2:
                print(f"  ⚠️  AssetType.{attr_name} fehlgeschlagen: {e2}")
    except Exception as e:
        print(f"  ⚠️  AssetType-Iteration fehlgeschlagen: {e}")

    # ── Versuch 3: Direkte L2-Auth Requests (eigen implementiert) ─────────────
    # Probiere alle bekannten asset_type Werte + kein Parameter
    print("  📡 Direkte L2-Auth Requests mit verschiedenen asset_type Werten…")
    h = _l2_headers(api_key, api_secret, api_passphrase, funder_addr, "GET", "/balance-allowance")
    for asset_type_val in [None, "USDC", "USDC_E", "COLLATERAL", "0", "1", "usdc", "usdc_e"]:
        params_dict = {} if asset_type_val is None else {"asset_type": asset_type_val}
        label = f"asset_type={asset_type_val!r}" if asset_type_val else "kein asset_type"
        try:
            r = requests.get(f"{CLOB_HOST}/balance-allowance",
                             params=params_dict, headers=h, timeout=20)
            print(f"  📬 {label} → {r.status_code} | {r.text[:150]}")
            if r.status_code == 200:
                data = r.json()
                bal = _extract_balance(data)
                if bal is not None:
                    print(f"  ✅ Balance via direkte L2-Auth: ${bal:.4f}")
                    return bal
        except Exception as e:
            print(f"  ⚠️  Direkte Request ({label}): {e}")

    return None


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
              error=f"Missing env: {', '.join(missing)}")
        return

    balance = fetch_balance_via_clob_client(
        private_key, funder_addr, api_key, api_secret, api_passphrase
    )

    if balance is None:
        print(f"\n⚠️   Balance-Fetch fehlgeschlagen — bestehende Balance wird behalten")
        existing = _load_existing()
        _save(existing.get("usdc", 0.0), existing.get("usdc_e", 0.0),
              funder_addr, error="fetch_failed")
        return

    out = _save(balance, 0.0, funder_addr)
    print(f"\n✅  wm_poly_balance.json geschrieben")
    print(f"    Handelbare CLOB Balance: ${out['total']:.2f} USDC")


if __name__ == "__main__":
    main()
