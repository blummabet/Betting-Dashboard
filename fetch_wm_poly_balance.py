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
          positions: float | None = None, positions_stand: str | None = None):
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
        # 🔴 18.09.2026. `positions` faellt bei einem API-Fehler auf den alten Wert zurueck — und
        # sah damit aus wie eine frische Zahl. In `liga_poly_balance.json` stand $10,12 ueber
        # fuenf Laeufe und zwei Tage unveraendert, danach $9,28 ueber vier weitere, waehrend die
        # Kurse liefen. Ich selbst habe am 16.09. aus diesem eingefrorenen Wert geschlossen, die
        # Wallet halte Brentford–Chelsea noch — er stammte aus einem Lauf davor.
        #
        # `updatedAt` sagt, wann die DATEI geschrieben wurde. Wann der Positionswert zuletzt
        # wirklich gemessen wurde, sagt erst dieses Feld. Ohne es rendert eine fehlende Messung
        # als harmloser Default.
        "positionsStand": positions_stand or (now if positions is not None else None),
    }
    if error:
        out["error"] = error
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2)
    _verlauf_fortschreiben(out)
    return out


# 🔴 21.09.2026 (Lucas: „Das kam. Aber auf poly wurde nicht gesetzt"). Die Order um 01:04 hat
# das Wallet nie beruehrt — usdc stand von 21:53 bis 04:39 unveraendert bei 178,2312 — und das
# Buch hat sie trotzdem als Verlust abgerechnet.
#
# Die Gegenprobe dafuer lag die ganze Zeit im Repo: dieser Schnappschuss wird alle ~15 Minuten
# geschrieben und committet. Man musste nur die Git-Historie durchsuchen, um sie zu lesen —
# also las sie niemand.
#
# Fehlerklasse: eine zweite, unabhaengige Quelle, die es gibt, aber nicht als Reihe vorliegt.
VERLAUF_KEEP = 3000          # ~1 Monat bei 15-Minuten-Takt


def verlauf_datei() -> Path:
    """Der Verlauf liegt neben seinem Stand — abgeleitet, nicht ein zweites Mal verdrahtet.

    🔴 21.09.2026. Der Verlauf hing zuerst an einer eigenen Konstanten. `_save` schreibt
    seither zwei Dateien; `tests/test_poly_balance_positions.py` biegt fuer seine Faelle aber nur
    `OUT_FILE` auf `tmp_path` um. Der zweite Schreibvorgang lief an dieser Umleitung vorbei und
    legte `wm_poly_verlauf.json` mit den Testwerten (usdc 99.9265, danach 50.0) im echten Baum an
    — ein Pipeline-Artefakt, erzeugt von der Testsuite.
    Fehlerklasse: ein zweiter Schreibvorgang, den die Umleitung des ersten nicht mit erfasst.
    Deshalb wird der Pfad aus `OUT_FILE` abgeleitet: wer den Stand umbiegt, biegt den Verlauf mit.
    """
    p = Path(OUT_FILE)
    name = p.name.replace("balance", "verlauf")
    if name == p.name:            # kein "balance" im Namen -> nie auf den Stand selbst schreiben
        name = p.name + ".verlauf"
    return p.with_name(name)


def verlauf_anhaengen(verlauf, stand, keep: int = VERLAUF_KEEP) -> list:
    """Haengt einen Wallet-Stand an die Reihe. REIN.

    Unveraenderte Staende werden NICHT gespeichert: der Abgleich sucht Bewegungen, und eine
    Reihe aus tausend identischen Zeilen macht die Suche nur langsam. Der letzte Stand bleibt
    aber immer stehen, damit das Ende der Reihe sagt, bis wann geschaut wurde.
    """
    r = list(verlauf or [])
    neu = {"ts": stand.get("updatedAt"), "usdc": stand.get("usdc"),
           "positions": stand.get("positions"), "total": stand.get("total")}
    if r and isinstance(r[-1], dict) and r[-1].get("usdc") == neu["usdc"]:
        r[-1] = neu                      # gleicher Stand -> nur den Zeitstempel nachziehen
    else:
        r.append(neu)
    return r[-keep:] if keep else r


def _verlauf_fortschreiben(stand):
    """Best effort — ein Protokoll darf den Balance-Abruf nie kippen."""
    try:
        ziel = verlauf_datei()
        alt = []
        if ziel.exists():
            alt = json.loads(ziel.read_text(encoding="utf-8")) or []
        if not isinstance(alt, list):
            alt = []
        ziel.write_text(
            json.dumps(verlauf_anhaengen(alt, stand), ensure_ascii=False), encoding="utf-8")
    except Exception as e:                # noqa: BLE001
        print(f"  ⚠️  Wallet-Verlauf nicht fortgeschrieben: {e}")


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
    rows = _positions_rows(raw)
    if rows is None:
        # 🔴 21.09.2026 (Lucas: „das ist wichtig und das haben wir damals schon mal gefixt").
        # Hier stand `raw.get("positions") or raw.get("data") or []`. Eine Antwort, die WEDER
        # eine Liste noch einer dieser beiden Umschlaege ist — `{"error": "rate limited"}`
        # etwa — wurde damit zur leeren Liste und die Summe zu 0,00 $. Das sieht im Artefakt
        # genauso aus wie „die Wallet haelt nichts", traegt einen frischen `positionsStand`
        # und ist damit von einer echten Messung nicht zu unterscheiden.
        # Der Fix vom 18.09. hat den EINGEFRORENEN Wert sichtbar gemacht; die leere Antwort
        # kam damit nicht ins Licht. Fehlerklasse (dieselbe wie damals, andere Tuer):
        # fehlende Information rendert als harmloser Default.
        # Ein nicht deutbares Format ist kein Nullbestand. None heisst „unbekannt", und der
        # Aufrufer behaelt dann die alte Zahl samt altem `positionsStand`.
        print("  ⚠️  Positions-Antwort nicht deutbar — Positionswert bleibt UNBEKANNT (nicht 0)")
        return None
    summe, unklar = positionen_summe(rows)
    if unklar:
        print(f"  ⚠️  {unklar} von {len(rows)} Positionszeilen nicht deutbar — "
              f"Positionswert bleibt UNBEKANNT statt zu klein")
        return None
    print(f"  📊 Offene Positionen: ${summe:.2f} (in {len(rows)} Positionen)")
    return summe


def positionen_summe(rows) -> tuple:
    """(Summe, Zahl der nicht deutbaren Zeilen). REIN.

    Der Aufrufer liefert die Summe NUR aus, wenn keine Zeile unklar blieb: eine Summe aus einem
    Teil der Zeilen ist keine Summe. Sie waere systematisch zu klein — und zu klein heisst hier,
    die Wallet sieht aermer aus, als sie ist, waehrend die Zahl aussieht wie gemessen.
    """
    total, unklar = 0.0, 0
    for row in (rows or []):
        wert = _positions_wert(row) if isinstance(row, dict) else None
        if wert is None:
            unklar += 1
            continue
        total += wert
    return round(total, 4), unklar


def _positions_rows(raw):
    """Die Positionszeilen aus einer API-Antwort — oder None, wenn das Format nichts hergibt. REIN.

    Eine leere LISTE ist eine Auskunft („keine Positionen"). Ein Dict ohne bekannten Umschlag,
    ein String, eine Zahl: das ist keine Auskunft, das ist ein anderes Format.
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for k in ("positions", "data"):
            if isinstance(raw.get(k), list):
                return raw[k]
    return None


def _positions_wert(row: dict):
    """Marktwert EINER Position — `currentValue`, sonst size x curPrice. None = nicht deutbar. REIN."""
    cv = row.get("currentValue")
    if cv is not None:
        try:
            return float(cv)
        except (TypeError, ValueError):
            return None
    sz, px = row.get("size", row.get("shares")), row.get("curPrice", row.get("current_price"))
    if sz is None or px is None:
        return None
    try:
        return float(sz) * float(px)
    except (TypeError, ValueError):
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
              error=f"Missing env: {', '.join(missing)}",
              positions=existing.get("positions"),
              positions_stand=existing.get("positionsStand"))
        return

    # 25.07.2026 (Lucas: „falsche balance"): der Fetch warf auf dem Runner eine Exception (statt None)
    # → main() brach VOR dem Schreiben ab → mls_poly_balance.json existierte NIE (stiller Ausfall,
    # continue-on-error verdeckte es). Jetzt gekapselt: der Balance-Stand wird IMMER geschrieben.
    try:
        balance_raw = fetch_balance_via_clob_client(
            private_key, funder_addr, api_key, api_secret, api_passphrase
        )
    except Exception as exc:
        print(f"\n⚠️   Balance-Fetch warf eine Exception: {exc}")
        balance_raw = None

    if balance_raw is None:
        print(f"\n⚠️   Balance-Fetch fehlgeschlagen — bestehende Balance wird behalten, Datei trotzdem geschrieben")
        existing = _load_existing()
        _save(existing.get("usdc", 0.0), existing.get("usdc_e", 0.0),
              funder_addr, error="fetch_failed",
              positions=existing.get("positions"),
              positions_stand=existing.get("positionsStand"))
        return

    # USDC hat 6 Dezimalstellen — API gibt Rohwert in kleinster Einheit zurück
    # z.B. 501624 → $0.501624 USDC
    USDC_DECIMALS = 1_000_000
    balance = balance_raw / USDC_DECIMALS

    # Wert der offenen Positionen dazu — echtes Wallet-Guthaben = frei + Positionen.
    try:
        positions = fetch_positions_value(funder_addr)
    except Exception as exc:
        print(f"  ⚠️  Positions-Fetch warf eine Exception: {exc}")
        positions = None
    positions_stand = None
    if positions is None:   # API-Fehler → alten Positions-Wert behalten, nicht auf 0 fallen
        _alt = _load_existing()
        positions = _alt.get("positions")
        positions_stand = _alt.get("positionsStand")   # der Wert ist alt — das steht jetzt dran

    out = _save(balance, 0.0, funder_addr, positions=positions,
                positions_stand=positions_stand)
    print(f"\n✅  {OUT_FILE.name} geschrieben")
    print(f"    Frei (setzbar): ${out['usdc']:.2f}  +  Positionen: ${out['positions']:.2f}  "
          f"=  Wallet-Equity: ${out['total']:.2f} USDC")


if __name__ == "__main__":
    main()
