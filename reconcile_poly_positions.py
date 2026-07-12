#!/usr/bin/env python3
"""
reconcile_poly_positions.py — manuelle Polymarket-Eingriffe erkennen (23.06.2026, Lucas).

Problem: Lucas verkauft eine Position direkt auf Polymarket. Unser System weiß nichts davon →
der Bet bleibt in wm_auto_bets_placed.json auf status='placed' → der 15-Min-Manage-Check alarmiert
weiter „verkaufen!", die Position hängt in Health/Offene-Positionen/Pending.

Lösung: die ECHTEN Wallet-Positionen (data-api /positions?user=<proxy>) gegen unsere Aufzeichnung
abgleichen. Hält die Wallet einen Token NICHT mehr UND das Spiel ist noch nicht fertig
(= kein Settlement, sondern echter Eingriff) → Bet als 'closed_manual' markieren, Alerts stoppen.
Echter realisierter P&L kommt aus dem Verkaufs-Trade (/trades?user=).

Reusable: nutzt der Auto-Abgleich (manage_wm_poly_positions) UND der Dashboard-„Geschlossen"-Button
(close-poly-position-Workflow). Polymarket ist geoblockt → läuft nur am Mac-Runner.
"""
from __future__ import annotations
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
# DATASET-AWARE (12.07.2026, Lucas: „MLS auf Polymarket") — MLS-Bets liegen in
# mls_auto_bets_placed.json; ein MLS-Reconcile darf nicht die WM-Bets anfassen.
import cocobet_dataset as D  # noqa: E402
AUTO_BETS_FILE = Path(str(D.file("wm_auto_bets_placed.json", "liga_auto_bets_placed.json")))

POSITIONS_URL = "https://data-api.polymarket.com/positions?user={user}&sizeThreshold=0.01"
TRADES_URL    = "https://data-api.polymarket.com/trades?user={user}&limit=200"
HTTP_TIMEOUT  = 15
HELD_EPS      = 1.0   # Shares ≤ EPS = praktisch nicht mehr gehalten (Staub ignorieren)


def _http_get(url: str):
    req = urllib.request.Request(
        url, headers={"User-Agent": "BetEdge/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  ⚠️  reconcile HTTP {url[:70]}…: {e}")
        return None


def _proxy_address() -> str | None:
    return (os.environ.get("POLY_FUNDER_ADDRESS")
            or os.environ.get("POLY_PROXY_ADDRESS") or "").strip() or None


def _rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("positions", "data", "trades", "results"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def _tok(d: dict):
    return d.get("asset") or d.get("tokenId") or d.get("token_id") or d.get("token")


def _num(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        try:
            if v is not None:
                return float(v)
        except (TypeError, ValueError):
            continue
    return None


def fetch_wallet_positions(proxy: str, getter=_http_get):
    """{tokenId: size} der aktuell gehaltenen Positionen, oder None bei API-Fehler.
    WICHTIG: None (Fehler) ≠ {} (gültig leer = Wallet hält nichts mehr). Der Aufrufer schließt
    nur bei einem ZUVERLÄSSIGEN Positions-Stand (None → nichts tun, sonst falsch-positiv)."""
    raw = getter(POSITIONS_URL.format(user=proxy))
    if raw is None:
        return None
    out = {}
    for row in _rows(raw):
        if not isinstance(row, dict):
            continue
        t = _tok(row)
        sz = _num(row, "size", "amount", "shares", "balance")
        if t and sz is not None:
            out[str(t)] = out.get(str(t), 0.0) + sz
    return out


def find_sell_trade(proxy: str, token_id: str, after_iso: str | None = None,
                    getter=_http_get) -> dict | None:
    """Jüngster SELL-Trade der Wallet auf token_id (nach after_iso) → {price, size, ts} oder None."""
    after_dt = None
    if after_iso:
        try:
            after_dt = datetime.fromisoformat(str(after_iso).replace("Z", "+00:00"))
        except Exception:
            after_dt = None
    best = None
    for tr in _rows(getter(TRADES_URL.format(user=proxy))):
        if not isinstance(tr, dict) or str(_tok(tr)) != str(token_id):
            continue
        side = str(tr.get("side") or tr.get("type") or "").upper()
        if not side.startswith("S"):   # nur SELL
            continue
        price = _num(tr, "price")
        size  = _num(tr, "size", "amount", "shares")
        ts = tr.get("timestamp") or tr.get("time") or tr.get("matchTime")
        ts_dt = None
        try:
            if ts is not None and (isinstance(ts, (int, float)) or str(ts).isdigit()):
                ts_dt = datetime.fromtimestamp(int(ts), timezone.utc)
            elif ts:
                ts_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            ts_dt = None
        if after_dt and ts_dt and ts_dt < after_dt:
            continue
        if price is None:
            continue
        cand = {"price": price, "size": size,
                "ts": ts_dt.isoformat() if ts_dt else None, "_dt": ts_dt}
        if best is None or (cand["_dt"] and best["_dt"] and cand["_dt"] > best["_dt"]):
            best = cand
    if best:
        best.pop("_dt", None)
    return best


def close_bet_manual(bet: dict, sell: dict | None, now_iso: str) -> dict:
    """Bet als manuell geschlossen markieren. P&L aus echtem Sell-Fill (shares×(sell−entry)),
    sonst None. Mutiert + gibt bet zurück."""
    bet["status"]     = "closed_manual"
    bet["soldAt"]     = now_iso
    bet["sellReason"] = "manuell auf Polymarket geschlossen"
    if sell and isinstance(sell.get("price"), (int, float)):
        sp = float(sell["price"])
        bet["sellPrice"] = round(sp, 4)
        entry  = bet.get("polyPrice")
        shares = bet.get("sharesEstimate") or sell.get("size")
        if isinstance(entry, (int, float)) and isinstance(shares, (int, float)):
            bet["pnl"] = round(shares * (sp - float(entry)), 2)
        bet["pnlSource"] = "manual_sell_trade"
    else:
        bet["sellPrice"] = None
        bet["pnl"] = None
        bet["pnlSource"] = "manual_unknown"
    return bet


def reconcile(bets: list, *, proxy: str, finished_keys: set | None = None,
              now_iso: str | None = None, getter=_http_get) -> list:
    """Gleicht 'placed'-Bets gegen die echten Wallet-Positionen ab. Token nicht mehr gehalten UND
    Spiel NICHT fertig (kein Settlement) → closed_manual + echter Sell-P&L. Gibt die Liste der
    geänderten Bets zurück. Wallet-Fetch leer/Fehler → nichts ändern (konservativ)."""
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    finished_keys = finished_keys or set()
    held = fetch_wallet_positions(proxy, getter=getter)
    if held is None:
        # API-Fehler (None ≠ leere Liste) → kein zuverlässiger Stand → NICHT schließen.
        print("  ⚠️  reconcile: Positions-API nicht erreichbar → übersprungen")
        return []
    changed = []
    for bet in bets:
        if bet.get("status") != "placed":
            continue
        tok = str(bet.get("tokenId") or "")
        if not tok:
            continue
        if held.get(tok, 0.0) > HELD_EPS:
            continue   # noch gehalten → nichts tun
        if bet.get("betKey") in finished_keys or bet.get("matchKey") in finished_keys:
            continue   # Spiel fertig → Settlement, NICHT als manueller Eingriff werten
        sell = find_sell_trade(proxy, tok, bet.get("placedAt"), getter=getter)
        close_bet_manual(bet, sell, now_iso)
        changed.append(bet)
        _pnl = bet.get("pnl")
        print(f"  🔁 manuell geschlossen erkannt: {bet.get('home')}–{bet.get('away')} "
              f"{bet.get('market')} · P&L "
              + (f"{_pnl:+.2f}€" if isinstance(_pnl, (int, float)) else "unbekannt"))
    return changed


def _load_finished_keys() -> set:
    """Match-Keys fertiger Spiele aus wm2026-data.json (Settlement ≠ manueller Eingriff)."""
    keys = set()
    try:
        wm = json.loads(Path(str(D.data_file())).read_text(encoding="utf-8"))
    except Exception:
        return keys
    for _g, gd in (wm.get("groups") or {}).items():
        for fx in (gd.get("fixtures") or []):
            st = str((fx.get("result") or {}).get("status") or "").upper()
            if st in ("FT", "AET", "PEN") and fx.get("home") and fx.get("away"):
                keys.add(f"{fx['home']}-{fx['away']}")
    return keys


def run(close_bet_key: str | None = None) -> int:
    """Auto-Abgleich (close_bet_key=None) ODER gezieltes Schließen EINES Bets (Button-Workflow)."""
    proxy = _proxy_address()
    if not proxy:
        print("❌ POLY_FUNDER_ADDRESS fehlt — reconcile übersprungen")
        return 1
    if not AUTO_BETS_FILE.exists():
        print("ℹ️  keine wm_auto_bets_placed.json — nichts zu tun")
        return 0
    data = json.loads(AUTO_BETS_FILE.read_text(encoding="utf-8"))
    bets = data.get("bets", [])
    now_iso = datetime.now(timezone.utc).isoformat()
    if close_bet_key:
        target = [b for b in bets if b.get("betKey") == close_bet_key and b.get("status") == "placed"]
        if not target:
            print(f"ℹ️  betKey {close_bet_key} nicht offen — nichts zu tun")
            return 0
        for b in target:
            sell = find_sell_trade(proxy, str(b.get("tokenId") or ""), b.get("placedAt"))
            close_bet_manual(b, sell, now_iso)
            print(f"  ✅ Button-Schließung: {b.get('home')}–{b.get('away')} {b.get('market')}")
        changed = target
    else:
        changed = reconcile(bets, proxy=proxy, finished_keys=_load_finished_keys(), now_iso=now_iso)
    if changed:
        data["updatedAt"] = now_iso
        AUTO_BETS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 {len(changed)} Bet(s) als manuell geschlossen markiert → {AUTO_BETS_FILE.name}")
    else:
        print("✅ reconcile: keine manuellen Eingriffe gefunden")
    return 0


if __name__ == "__main__":
    import sys
    _bk = None
    for a in sys.argv[1:]:
        if a.startswith("--close="):
            _bk = a.split("=", 1)[1]
    raise SystemExit(run(close_bet_key=_bk))
