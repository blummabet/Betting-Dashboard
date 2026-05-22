#!/usr/bin/env python3
"""
fetch_wm_poly_balance.py — Polymarket USDC Balance auf Polygon

Liest POLY_FUNDER_ADDRESS und fragt BEIDE USDC-Verträge auf Polygon ab:
  · Native USDC:   0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359  (Polymarket seit 2024)
  · Bridged USDC.e: 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174  (ältere Einlagen)

Schreibt wm_poly_balance.json:
  {
    "usdc":       123.45,   ← native USDC
    "usdc_e":     0.00,     ← bridged USDC.e
    "total":      123.45,   ← Summe (was Dashboard zeigt)
    "address":    "0x...",
    "updatedAt":  "2026-06-12T08:00:00+00:00"
  }

Wird aufgerufen von: manage-wm-poly.yml (5x täglich)
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

# ── USDC Verträge auf Polygon (Mainnet, Chain-ID 137) ──────────────────────
USDC_NATIVE  = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # native USDC
USDC_BRIDGED = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e
USDC_DECIMALS = 6  # beide Verträge haben 6 Dezimalstellen

# ERC-20 balanceOf(address) selector
BALANCE_OF_SELECTOR = "0x70a08231"

# ── Zuverlässige öffentliche Polygon JSON-RPC Endpunkte ────────────────────
# Format: (host, path)
RPC_ENDPOINTS = [
    ("rpc.ankr.com",           "/polygon"),       # Ankr Public — sehr zuverlässig
    ("polygon-rpc.com",        "/"),               # Polygon Official
    ("polygon.llamarpc.com",   "/"),               # LlamaRPC
    ("rpc-mainnet.matic.network", "/"),            # Matic Network
]


def _pad_address(address: str) -> str:
    """Ethereum-Adresse auf 32 Bytes (ABI-Encoding) auffüllen."""
    addr = address.lower().replace("0x", "")
    return "0" * (64 - len(addr)) + addr


def _eth_call(host: str, path: str, contract: str, data: str) -> str | None:
    """
    Einzelner eth_call JSON-RPC Request.
    Gibt den hex-encodierten Rückgabewert zurück oder None bei Fehler.
    """
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method":  "eth_call",
        "params":  [{"to": contract, "data": data}, "latest"],
        "id":      1,
    }).encode()

    try:
        ctx  = ssl.create_default_context()
        conn = http.client.HTTPSConnection(host, timeout=12, context=ctx)
        conn.request(
            "POST", path,
            body=payload,
            headers={
                "Content-Type":   "application/json",
                "Content-Length": str(len(payload)),
                "User-Agent":     "CocoBet/1.0",
                "Accept":         "application/json",
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
        result = data_resp.get("result", "")
        return result if result and result != "0x" else None

    except Exception as e:
        print(f"    RPC {host}{path}: {e}")
        return None


def _hex_to_usdc(hex_result: str) -> float:
    """Hex uint256 → USDC float (6 Dezimalstellen)."""
    try:
        raw = hex_result.replace("0x", "").lstrip("0") or "0"
        return int(raw, 16) / (10 ** USDC_DECIMALS)
    except Exception:
        return 0.0


def fetch_balance(wallet: str, contract: str, label: str) -> float | None:
    """Holt USDC-Balance für wallet_address via Polygon RPC. Versucht alle Endpunkte."""
    call_data = BALANCE_OF_SELECTOR + _pad_address(wallet)

    for host, path in RPC_ENDPOINTS:
        result = _eth_call(host, path, contract, call_data)
        if result:
            usdc = _hex_to_usdc(result)
            print(f"  ✅  {label}: ${usdc:.4f} USDC  [{host}]")
            return usdc

    print(f"  ⚠️   {label}: Alle RPC-Endpunkte fehlgeschlagen")
    return None


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    print(f"💰  fetch_wm_poly_balance.py")
    print(f"    Zeit: {now_iso[:19]} UTC\n")

    wallet = os.environ.get("POLY_FUNDER_ADDRESS", "").strip()
    if not wallet:
        # Bestehende Datei behalten wenn frisch genug (< 3h)
        if OUT_FILE.exists():
            try:
                with open(OUT_FILE) as f:
                    existing = json.load(f)
                updated = existing.get("updatedAt")
                if updated:
                    age_s = (datetime.now(timezone.utc) - datetime.fromisoformat(updated)).total_seconds()
                    if age_s < 10800:
                        print("  ⚠️   POLY_FUNDER_ADDRESS nicht gesetzt — behalte gecachte Balance")
                        return
            except Exception:
                pass
        print("  ❌  POLY_FUNDER_ADDRESS nicht gesetzt — Balance übersprungen")
        sys.exit(0)

    if not wallet.startswith("0x") or len(wallet) < 40:
        print(f"  ❌  Ungültige Wallet-Adresse: {wallet!r}")
        sys.exit(0)

    print(f"  Wallet: {wallet}")
    print(f"  Prüfe beide USDC-Verträge auf Polygon...\n")

    usdc_native  = fetch_balance(wallet, USDC_NATIVE,  "Native USDC")
    usdc_bridged = fetch_balance(wallet, USDC_BRIDGED, "USDC.e (bridged)")

    # Falls ein Contract nicht geantwortet hat, 0 annehmen (nicht None)
    usdc_n = usdc_native  if usdc_native  is not None else 0.0
    usdc_e = usdc_bridged if usdc_bridged is not None else 0.0
    total  = round(usdc_n + usdc_e, 4)

    out = {
        "usdc":      round(usdc_n, 4),
        "usdc_e":    round(usdc_e, 4),
        "total":     total,
        "address":   wallet,
        "updatedAt": now_iso,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\n✅  wm_poly_balance.json geschrieben")
    print(f"    Native USDC:    ${usdc_n:.2f}")
    print(f"    Bridged USDC.e: ${usdc_e:.2f}")
    print(f"    Total:          ${total:.2f}")


if __name__ == "__main__":
    main()
