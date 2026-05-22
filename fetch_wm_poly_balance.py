#!/usr/bin/env python3
"""
fetch_wm_poly_balance.py — Polymarket USDC Balance via CLOB L2 Auth (kein py-clob-client)

Polymarket hält Gelder im CLOB-Exchange-Vertrag — nicht on-chain im Wallet.
Diese Version verwendet direkte HMAC-Authentifizierung mit requests + Python-Stdlib.
Keine Abhängigkeit von py-clob-client-v2, eth_account oder web3.

Env-Variablen (alle als GitHub Secret hinterlegt):
    POLY_PRIVATE_KEY      — (nicht mehr benötigt, nur zur Rückwärtskompatibilität)
    POLY_FUNDER_ADDRESS   — Proxy-Wallet-Adresse (z.B. 0x02e0B17Da6...)
    POLY_API_KEY          — Polymarket CLOB API Key
    POLY_API_SECRET       — Polymarket CLOB API Secret
    POLY_API_PASSPHRASE   — Polymarket CLOB API Passphrase (wird für Header gesendet)

Schreibt wm_poly_balance.json:
  {
    "usdc":       123.45,
    "usdc_e":     0.00,
    "total":      123.45,
    "address":    "0x...",
    "updatedAt":  "2026-06-12T08:00:00+00:00"
  }

Wird aufgerufen von: manage-wm-poly.yml (5x täglich, self-hosted runner)
"""

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE      = Path(__file__).parent
OUT_FILE  = BASE / "wm_poly_balance.json"
CLOB_HOST = "https://clob.polymarket.com"


# ── HMAC L2 Auth ─────────────────────────────────────────────────────────────

def _build_l2_headers(api_key: str, api_secret: str, api_passphrase: str,
                      address: str, method: str, path: str, body: str = "") -> dict:
    """
    Erzeugt die HMAC-signierten Headers für Polymarket CLOB L2-Authentifizierung.
    Quelle: https://docs.polymarket.com/#authentication

    Signature message: timestamp + METHOD + path (ohne Query-String) + body
    Signature: HMAC-SHA256(api_secret, message) → Base64-encoded
    """
    ts  = str(int(time.time()))
    msg = ts + method.upper() + path + body

    sig_bytes = hmac.new(
        api_secret.encode("utf-8"),
        msg=msg.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")

    return {
        "POLY-ADDRESS":   address,
        "POLY-API-KEY":   api_key,
        "POLY-TIMESTAMP": ts,
        "POLY-NONCE":     "0",
        "POLY-SIGNATURE": sig_b64,
        "Content-Type":   "application/json",
        "Accept":         "application/json",
        "User-Agent":     "CocoBet/1.0",
    }


# ── Balance Fetch ─────────────────────────────────────────────────────────────

def fetch_balance(api_key: str, api_secret: str, api_passphrase: str,
                  funder_addr: str) -> float | None:
    """
    Fragt /balance-allowance?asset_type=USDC mit L2-Auth ab.
    Gibt die USDC-Balance als float zurück, oder None bei Fehler.
    """
    path = "/balance-allowance"
    url  = f"{CLOB_HOST}{path}?asset_type=USDC"

    headers = _build_l2_headers(api_key, api_secret, api_passphrase,
                                 funder_addr, "GET", path)

    print(f"  🔑 L2-Auth: Key={api_key[:8]}… Addr={funder_addr[:16]}…")
    print(f"  📡 GET {url}")

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        print(f"  📬 Status: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            print(f"  📦 Response: {json.dumps(data)[:200]}")
            # API returns: {"balance": "123.456789", ...}
            raw = data.get("balance", data.get("available", data.get("allowance")))
            if raw is not None:
                bal = float(raw)
                print(f"  ✅ Balance: ${bal:.4f} USDC")
                return bal
            # Falls Response direkt ein Array oder andere Struktur
            print(f"  ⚠️  Kein 'balance'-Feld in Response: {data}")
            return None

        elif resp.status_code == 401:
            print(f"  ❌ 401 Unauthorized — Auth fehlgeschlagen")
            print(f"     Body: {resp.text[:300]}")
            return None

        else:
            print(f"  ❌ HTTP {resp.status_code}: {resp.text[:300]}")
            return None

    except requests.Timeout:
        print("  ❌ Timeout nach 20s")
        return None
    except Exception as e:
        print(f"  ❌ Request-Fehler: {e}")
        return None


def fetch_balance_usdc_e(api_key: str, api_secret: str, api_passphrase: str,
                          funder_addr: str) -> float:
    """
    Fragt /balance-allowance?asset_type=USDC_E für Bridged USDC ab.
    Gibt 0.0 bei Fehler (nicht kritisch).
    """
    path = "/balance-allowance"
    url  = f"{CLOB_HOST}{path}?asset_type=USDC_E"

    headers = _build_l2_headers(api_key, api_secret, api_passphrase,
                                 funder_addr, "GET", path)
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            raw = data.get("balance", data.get("available", 0))
            return float(raw) if raw is not None else 0.0
    except Exception:
        pass
    return 0.0


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    print(f"💰  fetch_wm_poly_balance.py — CLOB L2 Auth (kein py-clob-client)")
    print(f"    Zeit: {now_iso[:19]} UTC\n")

    # ── Env-Variablen lesen ───────────────────────────────────────────────────
    api_key        = os.environ.get("POLY_API_KEY",        "").strip()
    api_secret     = os.environ.get("POLY_API_SECRET",     "").strip()
    api_passphrase = os.environ.get("POLY_API_PASSPHRASE", "").strip()
    funder_addr    = os.environ.get("POLY_FUNDER_ADDRESS", "").strip()

    # Fallback: aus Private Key ableiten (nur Adresse)
    if not funder_addr:
        funder_addr = os.environ.get("POLY_PRIVATE_KEY", "").strip()
        if funder_addr:
            print("  ⚠️  POLY_FUNDER_ADDRESS nicht gesetzt — verwende POLY_PRIVATE_KEY (nur Adresse)")

    # ── Validierung ───────────────────────────────────────────────────────────
    missing = []
    if not api_key:        missing.append("POLY_API_KEY")
    if not api_secret:     missing.append("POLY_API_SECRET")
    if not funder_addr:    missing.append("POLY_FUNDER_ADDRESS")

    if missing:
        print(f"  ❌ Fehlende Env-Variablen: {', '.join(missing)}")
        print(f"     Balance-Fetch übersprungen — bestehende Datei bleibt erhalten")
        # Timestamp aktualisieren damit wir wissen wann zuletzt versucht
        if OUT_FILE.exists():
            try:
                with open(OUT_FILE) as f:
                    existing = json.load(f)
                existing["lastAttempt"] = now_iso
                existing["error"] = f"Missing env: {', '.join(missing)}"
                with open(OUT_FILE, "w") as f:
                    json.dump(existing, f, indent=2)
            except Exception:
                pass
        return

    print(f"  Funder:  {funder_addr}")
    print(f"  API Key: {api_key[:8]}…\n")

    # ── Balance abrufen ───────────────────────────────────────────────────────
    balance_usdc = fetch_balance(api_key, api_secret, api_passphrase, funder_addr)

    if balance_usdc is None:
        print(f"\n⚠️   Balance-Fetch fehlgeschlagen")

        # Bestehende Datei behalten aber Timestamp + Error aktualisieren
        existing = {}
        if OUT_FILE.exists():
            try:
                with open(OUT_FILE) as f:
                    existing = json.load(f)
                print(f"    Letzte bekannte Balance: ${existing.get('total', 0):.2f} USDC")
            except Exception:
                pass

        # Schreibe updated file with error info so we can debug
        out = {
            "usdc":        existing.get("usdc", 0.0),
            "usdc_e":      existing.get("usdc_e", 0.0),
            "total":       existing.get("total", 0.0),
            "address":     funder_addr,
            "updatedAt":   existing.get("updatedAt", now_iso),  # behalte alten Timestamp
            "lastAttempt": now_iso,
            "error":       "fetch_failed",
        }
        with open(OUT_FILE, "w") as f:
            json.dump(out, f, indent=2)
        return

    # USDC.e (Bridged) — optional, 0 wenn nicht verfügbar
    balance_usdc_e = fetch_balance_usdc_e(api_key, api_secret, api_passphrase, funder_addr)
    total = round(balance_usdc + balance_usdc_e, 4)

    out = {
        "usdc":      round(balance_usdc,   4),
        "usdc_e":    round(balance_usdc_e, 4),
        "total":     total,
        "address":   funder_addr,
        "updatedAt": now_iso,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\n✅  wm_poly_balance.json geschrieben")
    print(f"    Handelbare CLOB Balance: ${total:.2f} USDC")
    if balance_usdc_e > 0.01:
        print(f"    (USDC: ${balance_usdc:.2f} + USDC.e: ${balance_usdc_e:.2f})")


if __name__ == "__main__":
    main()
