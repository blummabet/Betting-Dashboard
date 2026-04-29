#!/usr/bin/env python3
"""
setup_poly.py — Einmalige Polymarket-Einrichtung
=================================================
Dieses Script NUR EINMAL lokal ausführen, NICHT in GitHub Actions.

Was es tut:
  1. Verbindet sich mit deinem Polymarket Wallet
  2. Zeigt Wallet-Adresse und USDC-Balance
  3. Setzt USDC- und CTF-Allowances (2 On-Chain-Transaktionen, kostet ~$0.01 MATIC)
  4. Generiert und zeigt deine API-Credentials

Voraussetzung:
  export POLY_PRIVATE_KEY=0x...
  pip install py-clob-client requests

Danach: API-Credentials in GitHub Secrets hinterlegen (optional, für L2-Auth).
Der Private Key allein reicht aber für alle Orders.
"""

import os
import sys

def main():
    private_key = os.environ.get("POLY_PRIVATE_KEY", "").strip()
    if not private_key:
        print("❌ POLY_PRIVATE_KEY nicht gesetzt.")
        print("   Führe zuerst aus: export POLY_PRIVATE_KEY=0x...")
        sys.exit(1)

    try:
        from py_clob_client.client import ClobClient
    except ImportError:
        print("❌ py-clob-client nicht installiert.")
        print("   Führe aus: pip install py-clob-client")
        sys.exit(1)

    print("\n🟣 Polymarket Setup\n" + "─" * 40)

    # Verbinden
    client = ClobClient(
        host="https://clob.polymarket.com",
        key=private_key,
        chain_id=137,         # Polygon Mainnet
        signature_type=0,     # EOA (normales Wallet, kein Safe/Multisig)
    )

    # Wallet-Adresse anzeigen
    try:
        address = client.get_address()
        print(f"✅ Wallet verbunden: {address}")
    except Exception as e:
        print(f"⚠️  Konnte Adresse nicht abrufen: {e}")

    # API Credentials generieren (idempotent — kann mehrfach aufgerufen werden)
    print("\n📋 API-Credentials generieren...")
    try:
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds)
        print(f"   API Key:        {creds.api_key}")
        print(f"   API Secret:     {creds.api_secret}")
        print(f"   API Passphrase: {creds.api_passphrase}")
        print("\n   ℹ️  Diese Werte brauchst du nur wenn du L2-Auth verwendest.")
        print("   Für dieses Dashboard reicht POLY_PRIVATE_KEY allein.\n")
    except Exception as e:
        print(f"⚠️  Credentials-Generierung fehlgeschlagen: {e}")

    # USDC + CTF Allowances setzen
    print("🔓 Allowances setzen (2 On-Chain-Transaktionen)...")
    print("   Das kostet ~$0.01 MATIC Gas und muss nur EINMAL gemacht werden.\n")

    confirm = input("   Fortfahren? [j/N]: ").strip().lower()
    if confirm not in ("j", "ja", "y", "yes"):
        print("   Abgebrochen. Führe das Script erneut aus wenn du bereit bist.")
        sys.exit(0)

    try:
        client.set_allowances()
        print("\n✅ Allowances erfolgreich gesetzt!")
        print("   Dein Wallet kann jetzt programmatisch auf Polymarket wetten.")
    except Exception as e:
        print(f"\n❌ Allowances fehlgeschlagen: {e}")
        print("   Mögliche Ursache: nicht genug MATIC für Gas (mindestens $0.05 MATIC nötig)")
        sys.exit(1)

    print("\n" + "─" * 40)
    print("✅ Setup abgeschlossen! Du kannst jetzt polymarket_bet.py verwenden.\n")


if __name__ == "__main__":
    main()
