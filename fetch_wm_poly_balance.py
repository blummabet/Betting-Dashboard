#!/usr/bin/env python3
"""
fetch_wm_poly_balance.py — Fetch Polymarket USDC balance from Polygon.

Reads the POLY_FUNDER_ADDRESS env var and queries the USDC contract on
Polygon via a public JSON-RPC endpoint (no API key required).

Writes wm_poly_balance.json:
  {
    "usdc":       123.45,
    "address":    "0x...",
    "updatedAt":  "2026-05-22T08:00:00+00:00"
  }

Run: python fetch_wm_poly_balance.py
Triggered by: manage-wm-poly.yml (5x daily)
"""

import json
import os
import sys
import http.client
import ssl
from datetime import datetime, timezone
from pathlib import Path

BASE     = Path(__file__).parent
OUT_FILE = BASE / "wm_poly_balance.json"

# USDC contract on Polygon (bridged USDC used by Polymarket)
USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# Polygon JSON-RPC endpoints (tried in order until one works)
RPC_ENDPOINTS = [
    "polygon-rpc.com",
    "rpc-mainnet.matic.network",
    "polygon-mainnet.g.alchemy.com",  # may require key — skip silently on 401
]

# ERC-20 balanceOf(address) selector = first 4 bytes of keccak256("balanceOf(address)")
BALANCE_OF_SELECTOR = "0x70a08231"

# USDC on Polygon has 6 decimals
USDC_DECIMALS = 6


def _eth_call(rpc_host: str, contract: str, data: str) -> str | None:
    """Make a single eth_call JSON-RPC request. Returns hex result string or None."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method":  "eth_call",
        "params":  [{"to": contract, "data": data}, "latest"],
        "id":      1,
    }).encode()

    try:
        ctx  = ssl.create_default_context()
        conn = http.client.HTTPSConnection(rpc_host, timeout=10, context=ctx)
        conn.request(
            "POST", "/",
            body=payload,
            headers={
                "Content-Type":   "application/json",
                "Content-Length": str(len(payload)),
                "User-Agent":     "CocoBet/1.0",
            },
        )
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()

        if resp.status not in (200, 201):
            return None

        data_resp = json.loads(raw)
        if "error" in data_resp:
            return None
        return data_resp.get("result")

    except Exception as e:
        print(f"  RPC {rpc_host}: {e}")
        return None


def _pad_address(address: str) -> str:
    """Pad an Ethereum address to 32 bytes for ABI encoding."""
    addr = address.lower().replace("0x", "")
    return "0" * (64 - len(addr)) + addr


def fetch_usdc_balance(wallet_address: str) -> float | None:
    """
    Fetch USDC balance for wallet_address on Polygon.
    Returns balance in USDC (float) or None on failure.
    """
    if not wallet_address or not wallet_address.startswith("0x"):
        print(f"  ❌  Invalid wallet address: {wallet_address!r}")
        return None

    # ABI-encode: balanceOf(address) call
    call_data = BALANCE_OF_SELECTOR + _pad_address(wallet_address)

    for rpc_host in RPC_ENDPOINTS:
        print(f"  → Trying RPC: {rpc_host}")
        result = _eth_call(rpc_host, USDC_CONTRACT, call_data)
        if result and result != "0x":
            # Result is a hex-encoded uint256 (32 bytes)
            hex_val = result.replace("0x", "").lstrip("0") or "0"
            raw_balance = int(hex_val, 16)
            usdc = raw_balance / (10 ** USDC_DECIMALS)
            print(f"  ✅  USDC balance: ${usdc:.2f} USDC")
            return usdc

    print("  ⚠️  All RPC endpoints failed or returned empty")
    return None


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    print(f"💰  fetch_wm_poly_balance.py")
    print(f"    Time: {now_iso[:19]} UTC\n")

    wallet = os.environ.get("POLY_FUNDER_ADDRESS", "").strip()
    if not wallet:
        # Check if there's an existing balance file — keep it if fresh (< 2h)
        if OUT_FILE.exists():
            try:
                with open(OUT_FILE) as f:
                    existing = json.load(f)
                age_s = (datetime.now(timezone.utc) - datetime.fromisoformat(existing["updatedAt"])).total_seconds()
                if age_s < 7200:
                    print("  ⚠️  POLY_FUNDER_ADDRESS not set — keeping cached balance")
                    return
            except Exception:
                pass
        print("  ❌  POLY_FUNDER_ADDRESS not set — skipping")
        sys.exit(0)   # Non-fatal: balance display is optional

    usdc = fetch_usdc_balance(wallet)

    out = {
        "usdc":      usdc,
        "address":   wallet,
        "updatedAt": now_iso,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2)

    status = f"${usdc:.2f} USDC" if usdc is not None else "fetch failed"
    print(f"\n✅  wm_poly_balance.json written — {status}")


if __name__ == "__main__":
    main()
