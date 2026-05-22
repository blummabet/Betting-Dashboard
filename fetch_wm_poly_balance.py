#!/usr/bin/env python3
"""
fetch_wm_poly_balance.py — Polymarket USDC Balance via CLOB API

Polymarket hält Gelder im CLOB-Exchange-Vertrag (nicht direkt im Proxy-Wallet
on-chain). Deshalb liefert ein direkter Blockchain-Query immer 0 — wir fragen
stattdessen die offizielle Polymarket CLOB API via py_clob_client_v2 ab.

Env-Variablen:
    POLY_PRIVATE_KEY      — Polygon EOA private key (aus GitHub Secret)
    POLY_FUNDER_ADDRESS   — Proxy-Wallet-Adresse (optional, verbessert Auth)
    POLY_API_KEY          — Optional: gespeicherte API Creds (sonst auto-deriviert)
    POLY_API_SECRET
    POLY_API_PASSPHRASE

Schreibt wm_poly_balance.json:
  {
    "usdc":       123.45,
    "usdc_e":     0.00,
    "total":      123.45,
    "address":    "0x...",
    "updatedAt":  "2026-06-12T08:00:00+00:00"
  }

Wird aufgerufen von: manage-wm-poly.yml (5x täglich)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE      = Path(__file__).parent
OUT_FILE  = BASE / "wm_poly_balance.json"
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID  = 137  # Polygon


# ── Cache helper ────────────────────────────────────────────────────────────

def _load_existing() -> dict | None:
    """Bestehende Balance-Datei laden falls vorhanden und frisch genug (< 2h)."""
    if not OUT_FILE.exists():
        return None
    try:
        with open(OUT_FILE) as f:
            existing = json.load(f)
        updated = existing.get("updatedAt")
        if updated:
            age_s = (datetime.now(timezone.utc) - datetime.fromisoformat(updated)).total_seconds()
            if age_s < 7200:  # 2h Cache
                return existing
    except Exception:
        pass
    return None


# ── CLOB API Balance ────────────────────────────────────────────────────────

def fetch_clob_balance(private_key: str, funder_addr: str) -> dict | None:
    """
    Holt die handelbare USDC-Balance aus der Polymarket CLOB API.
    Identisches Auth-Pattern wie polymarket_bet.py.
    Gibt {"usdc": float, "usdc_e": 0.0, "total": float} zurück oder None bei Fehler.
    """
    try:
        from py_clob_client_v2.client import ClobClient
        from py_clob_client_v2.clob_types import ApiCreds
        from py_clob_client_v2 import SignatureTypeV2
    except ImportError as e:
        print(f"  ❌ py-clob-client-v2 Import-Fehler: {e}")
        print(f"     Bitte: pip install py-clob-client-v2")
        return None

    # ── Client initialisieren (gleiche Logik wie polymarket_bet.py) ───────────
    client_kwargs: dict = dict(
        host=CLOB_HOST,
        key=private_key,
        chain_id=CHAIN_ID,
        signature_type=SignatureTypeV2.POLY_PROXY,
    )
    if funder_addr:
        client_kwargs["funder"] = funder_addr

    client = ClobClient(**client_kwargs)

    # ── API Creds derivieren oder aus Env lesen ───────────────────────────────
    api_key = os.environ.get("POLY_API_KEY", "").strip()
    creds   = None

    if api_key:
        api_secret     = os.environ.get("POLY_API_SECRET", "").strip()
        api_passphrase = os.environ.get("POLY_API_PASSPHRASE", "").strip()
        creds = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase)
        print(f"  🔑 Verwende gespeicherte API Creds (Key: {api_key[:8]}…)")
    else:
        print(f"  🔑 Deriviere API Creds aus Private Key…")
        try:
            creds_raw = client.derive_api_key()
            if isinstance(creds_raw, ApiCreds):
                creds = creds_raw
            elif isinstance(creds_raw, dict):
                creds = ApiCreds(
                    api_key=creds_raw.get("key", creds_raw.get("apiKey", "")),
                    api_secret=creds_raw.get("secret", ""),
                    api_passphrase=creds_raw.get("passphrase", ""),
                )
            if creds:
                key_preview = getattr(creds, "api_key", "?")[:8]
                print(f"  ✅ API Creds deriviert (Key: {key_preview}…)")
        except Exception as e:
            print(f"  ⚠️  derive_api_key fehlgeschlagen: {e}")

    if creds:
        try:
            client.set_api_creds(creds)
        except AttributeError:
            client_kwargs["creds"] = creds
            client = ClobClient(**client_kwargs)

    # ── Balance abrufen ───────────────────────────────────────────────────────
    # Versuche mehrere Methoden der py_clob_client_v2 API
    balance_usdc = None

    # Methode 1: get_balance_allowance mit asset_type Parameter
    try:
        result = client.get_balance_allowance(params={"asset_type": "USDC"})
        if isinstance(result, dict):
            raw = result.get("balance", result.get("available", None))
            if raw is not None:
                balance_usdc = float(raw)
                print(f"  ✅ CLOB Balance (Methode 1): ${balance_usdc:.4f} USDC")
    except Exception as e:
        print(f"  ⚠️  get_balance_allowance fehlgeschlagen: {e}")

    # Methode 2: get_balance_allowance ohne Parameter
    if balance_usdc is None:
        try:
            result = client.get_balance_allowance()
            if isinstance(result, dict):
                raw = result.get("balance", result.get("available", None))
                if raw is not None:
                    balance_usdc = float(raw)
                    print(f"  ✅ CLOB Balance (Methode 2): ${balance_usdc:.4f} USDC")
        except Exception as e:
            print(f"  ⚠️  get_balance_allowance() fehlgeschlagen: {e}")

    # Methode 3: Direkter HTTP Request an /balance-allowance mit L1-Auth
    if balance_usdc is None:
        balance_usdc = _http_balance_direct(funder_addr)

    if balance_usdc is None:
        return None

    total = round(balance_usdc, 4)
    return {"usdc": total, "usdc_e": 0.0, "total": total}


def _http_balance_direct(funder_addr: str) -> float | None:
    """
    Direkter HTTP GET an /balance-allowance?asset_type=USDC — public endpoint
    der die Balance für die gegebene Proxy-Wallet-Adresse zurückgibt.
    """
    import http.client
    import ssl
    import urllib.parse

    if not funder_addr:
        return None

    print(f"  🔄 Versuche direkten HTTP Balance-Request für {funder_addr[:16]}…")
    params = urllib.parse.urlencode({
        "asset_type": "USDC",
        "signature_type": "2",  # POLY_PROXY
    })
    path = f"/balance-allowance?{params}"

    try:
        ctx  = ssl.create_default_context()
        conn = http.client.HTTPSConnection("clob.polymarket.com", timeout=15, context=ctx)
        conn.request("GET", path, headers={
            "User-Agent": "CocoBet/1.0",
            "Accept":     "application/json",
            "POLY_ADDRESS": funder_addr,
        })
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()

        if resp.status in (200, 201):
            data = json.loads(raw)
            raw_bal = data.get("balance", data.get("available"))
            if raw_bal is not None:
                bal = float(raw_bal)
                print(f"  ✅ HTTP Balance: ${bal:.4f} USDC")
                return bal
        print(f"  ⚠️  HTTP Balance: Status {resp.status}")
    except Exception as e:
        print(f"  ⚠️  HTTP Balance Fehler: {e}")

    return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    now_iso     = datetime.now(timezone.utc).isoformat()
    print(f"💰  fetch_wm_poly_balance.py — CLOB API")
    print(f"    Zeit: {now_iso[:19]} UTC\n")

    private_key = os.environ.get("POLY_PRIVATE_KEY", "").strip()
    funder_addr = os.environ.get("POLY_FUNDER_ADDRESS", "").strip()

    if not private_key:
        # Kein Private Key → Cache behalten falls frisch genug
        cached = _load_existing()
        if cached:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached["updatedAt"])).total_seconds()
            print(f"  ⚠️   POLY_PRIVATE_KEY nicht gesetzt — behalte Cache ({age/3600:.1f}h alt)")
            print(f"      Balance: ${cached.get('total', 0):.2f} USDC")
            return
        print("  ❌  POLY_PRIVATE_KEY nicht gesetzt — Balance übersprungen")
        sys.exit(0)

    if funder_addr:
        print(f"  Funder: {funder_addr}")
    else:
        print(f"  Funder: (auto-deriviert aus Private Key)")
    print(f"  Frage Polymarket CLOB API ab...\n")

    result = fetch_clob_balance(private_key, funder_addr)

    if result is None:
        # CLOB fehlgeschlagen — bestehende Datei wenn vorhanden behalten
        if OUT_FILE.exists():
            try:
                with open(OUT_FILE) as f:
                    existing = json.load(f)
                print(f"\n⚠️   CLOB-Abfrage fehlgeschlagen — behalte gespeicherte Balance")
                print(f"    Letzte bekannte Balance: ${existing.get('total', 0):.2f} USDC")
                return
            except Exception:
                pass
        # Keine bestehende Datei — leer schreiben
        result = {"usdc": 0.0, "usdc_e": 0.0, "total": 0.0}
        print(f"\n⚠️   CLOB-Abfrage fehlgeschlagen — schreibe 0.00 USDC")

    out = {
        "usdc":      result.get("usdc",   0.0),
        "usdc_e":    result.get("usdc_e", 0.0),
        "total":     result.get("total",  0.0),
        "address":   funder_addr or "",
        "updatedAt": now_iso,
    }

    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\n✅  wm_poly_balance.json geschrieben")
    print(f"    Handelbare CLOB Balance: ${out['total']:.2f} USDC")
    if out.get("usdc_e", 0) > 0.01:
        print(f"    (USDC: ${out['usdc']:.2f} + USDC.e: ${out['usdc_e']:.2f})")


if __name__ == "__main__":
    main()
