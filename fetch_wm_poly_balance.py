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


def fetch_balance_via_clob_client(private_key: str, funder_addr: str,
                                   api_key: str, api_secret: str,
                                   api_passphrase: str) -> float | None:
    """
    Verwendet py-clob-client-v2 ClobClient — genau wie polymarket_bet.py.
    Ruft /balance-allowance?asset_type=USDC via authentifizierte Session ab.
    """
    try:
        from py_clob_client_v2.client import ClobClient
        from py_clob_client_v2.clob_types import ApiCreds
        from py_clob_client_v2 import SignatureTypeV2
    except ImportError as e:
        print(f"  ❌ py-clob-client-v2 nicht verfügbar: {e}")
        return None

    client_kwargs = dict(
        host=CLOB_HOST,
        key=private_key,
        chain_id=CHAIN_ID,
        signature_type=SignatureTypeV2.POLY_PROXY,
    )
    if funder_addr:
        client_kwargs["funder"] = funder_addr

    client = ClobClient(**client_kwargs)

    # API Creds setzen (genau wie polymarket_bet.py)
    creds = ApiCreds(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
    )
    print(f"  🔑 API Creds: Key={api_key[:8]}… Addr={funder_addr[:16]}…")
    try:
        client.set_api_creds(creds)
    except AttributeError:
        client_kwargs["creds"] = creds
        client = ClobClient(**client_kwargs)

    # ── Versuch 1: client.get_balance_allowance() ─────────────────────────────
    for method_name in ["get_balance_allowance", "get_balance", "get_allowance"]:
        method = getattr(client, method_name, None)
        if method is None:
            continue
        try:
            print(f"  📡 Versuche client.{method_name}(asset_type='USDC')…")
            resp = method(asset_type="USDC")
            if resp is None:
                resp = method()
            print(f"  📦 Response: {str(resp)[:200]}")
            if isinstance(resp, (int, float)):
                return float(resp)
            if isinstance(resp, dict):
                for key in ("balance", "available", "allowance"):
                    if key in resp:
                        return float(resp[key])
        except TypeError:
            # Falls kein asset_type Parameter unterstützt
            try:
                resp = method()
                print(f"  📦 Response (no args): {str(resp)[:200]}")
                if isinstance(resp, (int, float)):
                    return float(resp)
                if isinstance(resp, dict):
                    for key in ("balance", "available", "allowance"):
                        if key in resp:
                            return float(resp[key])
            except Exception as e2:
                print(f"  ⚠️  {method_name}() fehlgeschlagen: {e2}")
        except Exception as e:
            print(f"  ⚠️  client.{method_name}() fehlgeschlagen: {e}")

    # ── Versuch 2: Authenticated requests Session aus dem Client ──────────────
    print("  📡 Fallback: direkte L2-Auth Session aus ClobClient…")
    try:
        # py-clob-client-v2 hat intern eine Session — wir extrahieren die Headers
        # indem wir einen minimalen Request damit bauen
        session = getattr(client, "_session", None) or getattr(client, "session", None)
        if session and hasattr(session, "get"):
            url = f"{CLOB_HOST}/balance-allowance?asset_type=USDC"
            resp = session.get(url, timeout=20)
            print(f"  📬 Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"  📦 {json.dumps(data)[:200]}")
                for key in ("balance", "available", "allowance"):
                    if key in data:
                        return float(data[key])
            else:
                print(f"  ❌ HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  ⚠️  Session-Fallback fehlgeschlagen: {e}")

    # ── Versuch 3: L2 Headers direkt aus ClobClient-Methode ──────────────────
    print("  📡 Fallback: L2 Headers via client.create_l2_headers()…")
    try:
        for header_method in ["create_l2_headers", "get_l2_headers", "_get_auth_headers"]:
            fn = getattr(client, header_method, None)
            if fn is None:
                continue
            try:
                headers = fn(method="GET", request_path="/balance-allowance")
                if not headers:
                    continue
                url = f"{CLOB_HOST}/balance-allowance?asset_type=USDC"
                r = requests.get(url, headers=headers, timeout=20)
                print(f"  📬 {header_method} → Status: {r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    print(f"  📦 {json.dumps(data)[:200]}")
                    for key in ("balance", "available", "allowance"):
                        if key in data:
                            return float(data[key])
            except Exception as e2:
                print(f"  ⚠️  {header_method} fehlgeschlagen: {e2}")
    except Exception as e:
        print(f"  ⚠️  L2 Header Fallback fehlgeschlagen: {e}")

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
