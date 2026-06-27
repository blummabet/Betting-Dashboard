#!/usr/bin/env python3
"""
poly_debug.py — Diagnose welche Wallet-Adresse py-clob-client-v2 verwendet
Ausführen: POLY_PRIVATE_KEY=0x... python3 poly_debug.py
"""

import os, sys, json, requests

private_key = os.environ.get("POLY_PRIVATE_KEY", "").strip()
if not private_key:
    print("❌ POLY_PRIVATE_KEY nicht gesetzt")
    sys.exit(1)

CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID  = 137

print("─" * 60)
print("1. py-clob-client-v2 Version + verfügbare Methoden")
print("─" * 60)

try:
    import py_clob_client_v2
    print(f"   Version: {getattr(py_clob_client_v2, '__version__', 'unbekannt')}")
    print(f"   Pfad:    {py_clob_client_v2.__file__}")
except ImportError as e:
    print(f"   ❌ Import fehlgeschlagen: {e}")
    sys.exit(1)

from py_clob_client_v2.client import ClobClient
from py_clob_client_v2 import SignatureTypeV2

import inspect
init_params = list(inspect.signature(ClobClient.__init__).parameters.keys())
print(f"   ClobClient.__init__ Parameter: {init_params}")
print()

print("─" * 60)
print("2. ClobClient mit POLY_PROXY initialisieren (keine API Creds)")
print("─" * 60)

client_no_creds = ClobClient(
    host=CLOB_HOST,
    key=private_key,
    chain_id=CHAIN_ID,
    signature_type=SignatureTypeV2.POLY_PROXY,
)

# Alle Methoden/Attribute anzeigen
methods = [m for m in dir(client_no_creds) if not m.startswith('_')]
print(f"   Verfügbare Methoden: {methods}")
print()

# Adressen prüfen
print("─" * 60)
print("3. Wallet-Adressen")
print("─" * 60)

for attr in ['address', 'signer', 'funder', 'maker', 'proxy_wallet', 'get_address']:
    if hasattr(client_no_creds, attr):
        val = getattr(client_no_creds, attr)
        if callable(val):
            try:
                val = val()
            except Exception as e:
                val = f"Error: {e}"
        print(f"   client.{attr} = {val}")

print()

# EOA-Adresse aus Private Key berechnen
try:
    from eth_account import Account
    eoa = Account.from_key(private_key)
    print(f"   EOA Adresse (aus Private Key): {eoa.address}")
except ImportError:
    print("   eth_account nicht installiert — EOA Adresse nicht berechenbar")

print()

# API Key derivieren (ohne Netzwerk falls möglich)
print("─" * 60)
print("4. API Credentials derivieren")
print("─" * 60)

for method_name in ['derive_api_key', 'create_api_key', 'get_api_keys']:
    if hasattr(client_no_creds, method_name):
        print(f"   ✅ Methode '{method_name}' existiert")
        try:
            result = getattr(client_no_creds, method_name)()
            print(f"      Ergebnis: {result}")
        except Exception as e:
            print(f"      Fehler beim Aufruf: {e}")
    else:
        print(f"   ❌ Methode '{method_name}' nicht vorhanden")

print()

# Polymarket Gamma API: Proxy Wallet über EOA finden
print("─" * 60)
print("5. Polymarket CLOB: welche Adresse wird erwartet?")
print("─" * 60)

try:
    from eth_account import Account
    eoa_addr = Account.from_key(private_key).address

    # GET /auth/info oder /profile
    for endpoint in ["/auth/info", f"/users/{eoa_addr}", f"/balance/{eoa_addr}"]:
        try:
            r = requests.get(f"{CLOB_HOST}{endpoint}", timeout=5)
            if r.status_code == 200:
                print(f"   GET {endpoint} → {r.json()}")
        except Exception:
            pass
except Exception as e:
    print(f"   Fehler: {e}")

print()
print("─" * 60)
print("6. create_and_post_market_order Signatur prüfen")
print("─" * 60)

if hasattr(client_no_creds, 'create_and_post_market_order'):
    sig = inspect.signature(client_no_creds.create_and_post_market_order)
    print(f"   Parameter: {list(sig.parameters.keys())}")
else:
    print("   ❌ Methode nicht gefunden")

# MarketOrderArgs prüfen
try:
    from py_clob_client_v2.clob_types import MarketOrderArgs
    sig2 = inspect.signature(MarketOrderArgs.__init__)
    print(f"   MarketOrderArgs Parameter: {list(sig2.parameters.keys())}")
except Exception as e:
    print(f"   MarketOrderArgs Fehler: {e}")
