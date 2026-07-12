#!/usr/bin/env python3
"""
fetch_wm_poly_smartmoney.py — Polymarket Geld-/Wallet-Verteilung pro Spiel (19.06.2026, Lucas)

Für jedes WM-Fixture den 1X2-Geld-Split + Big-Wallet-Konzentration aus der Polymarket data-api.
data-api `/holders?market=<conditionId>` (conditionId, NICHT Token-ID!) liefert je Outcome-Binär
die Holder gruppiert nach Token: [{token, holders:[{proxyWallet, amount, outcomeIndex}]}]. Wir
nehmen je Outcome (home/draw/away) die Holder-Gruppe des YES-Tokens (=hwTokens[0]/drTokens[0]/
awTokens[0]) und aggregieren:
  outcomes[home|draw|away] = {usd, share, topHolderShare, holders}
  + totalUsd, topTraders (# Wallets ≥ big_trader_usd)
→ wm_poly_smartmoney.json {matches:{HOME-AWAY:{...}}, updatedAt}.

Braucht hwCondition/drCondition/awCondition + hwTokens/.. + poly_hw/dr/aw aus wm_poly_prices.json
(alle von fetch_wm_poly_prices.py geschrieben). Speist das (NIEDRIG gewichtete) smart_money-Signal
+ die violette Card-Box. Schreibt IMMER (auch partiell/leer) → Signal liefert robust None.

WICHTIG: Polymarket ist geoblockt — läuft NUR auf dem Mac-Runner (wie clob/gamma). Vom Sandbox
nicht testbar. Endpoint-Form: shaunlebron gist (Polymarket Data API Docs), /holders.

Run (Runner):  python3 fetch_wm_poly_smartmoney.py
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _kickoff_passed(fx):
    """True wenn der Anpfiff vorbei ist → Spiel gelaufen/in-play. Dann sind die offenen
    Positionen Phantom (gewonnene Wetten vor Redeem) → nicht als Smart-Money zählen.
    Fehlender/unparsebarer kickoff → False (nicht versehentlich alles überspringen)."""
    ko = fx.get("kickoff")
    if not ko:
        return False
    try:
        kt = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        return datetime.now(timezone.utc) >= kt
    except Exception:
        return False

BASE = Path(__file__).parent
PRICES_FILE  = BASE / "wm_poly_prices.json"
OUT_FILE     = BASE / "wm_poly_smartmoney.json"
WALLETS_FILE = BASE / "wm_poly_wallets.json"     # 21.06.2026: Wallet-Dashboard
HOLDERS_URL  = "https://data-api.polymarket.com/holders?market={cond}&limit=200"
TRADES_URL   = "https://data-api.polymarket.com/trades?market={cond}&limit=100"

TOP_N           = 10        # für topHolderShare
BIG_TRADER_USD  = 1000      # Wallet ab $ = „Top-Trader"
HOLDERS_TIMEOUT = 15
MIN_WRITE_USD   = 5000      # darunter ($0.00M-Platzhalter/gelaufene Spiele) NICHT schreiben

# Wallet-Dashboard (21.06.2026, Lucas): einzelne fette Einsätze sichtbar machen
TOP_WALLETS_PER_OUTCOME = 8      # wie viele Einzel-Wallets je Outcome behalten
BIG_TRADE_USD           = 2000   # Trade ab $ kommt in den „große Trades"-Feed
LEADERBOARD_MAX         = 60     # globale Bestenliste begrenzen


def _cfg_cluster_window_h() -> float:
    """Cluster-Fenster (Stunden) aus dem aktiven Profil — single source mit dem Signal.
    Der Fetcher MUSS das Fenster zur Fetch-Zeit kennen (distinkte Wallets pro Zeitraum lassen
    sich aus den Aggregaten nicht rückrechnen). Fallback 12h."""
    try:
        import json as _j
        raw = _j.loads((BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        return float(raw["profiles"][active].get("smart_money", {}).get("cluster_window_h", 12))
    except Exception:
        return 12.0


def _parse_ts(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")) if ts else None
    except Exception:
        return None


def _hours_to_kickoff(fx):
    """Stunden bis Anpfiff (positiv = liegt vorne). None wenn kein/kaputter kickoff.
    Für die Exit-Erkennung: SELLs werden erst nah am KO als Conviction-Aufgabe gewertet."""
    kt = _parse_ts(fx.get("kickoff"))
    if not kt:
        return None
    return round((kt - datetime.now(timezone.utc)).total_seconds() / 3600.0, 1)


def _cluster_metrics(trades, window_h):
    """Konsens-Cluster + Net-Flow je Outcome-Seite aus den großen Trades (PolymarketScan-Idee:
    ≥N unabhängige Wallets kaufen dieselbe Seite in kurzem Fenster → repreist meist).
      cluster    = # DISTINKTE BUY-Wallets im Fenster (echter Konsens, nicht eine Wallet ×N)
      buyUsd/sellUsd, netFlowUsd = BUY − SELL  (negativ = Verkäufer dominieren → Conviction kippt)
    Fenster ab dem JÜNGSTEN Trade (robust gegen alte Snaps ohne frische Trades)."""
    times = [t for t in (_parse_ts(x.get("ts")) for x in trades) if t]
    ref = max(times) if times else None
    agg = {}
    for t in trades:
        side = t.get("side")
        if side not in ("home", "draw", "away"):
            continue
        tt = _parse_ts(t.get("ts"))
        if ref and tt and (ref - tt).total_seconds() > window_h * 3600:
            continue
        d = agg.setdefault(side, {"_buyW": set(), "buyUsd": 0.0, "sellUsd": 0.0})
        usd = t.get("usd") or 0
        if t.get("action") == "BUY":
            d["buyUsd"] += usd
            if t.get("wallet"):
                d["_buyW"].add(t["wallet"])
        elif t.get("action") == "SELL":
            d["sellUsd"] += usd
    out = {}
    for side, d in agg.items():
        out[side] = {"cluster": len(d["_buyW"]),
                     "buyUsd": round(d["buyUsd"], 0), "sellUsd": round(d["sellUsd"], 0),
                     "netFlowUsd": round(d["buyUsd"] - d["sellUsd"], 0)}
    return out


def _http_get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "BetEdge/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HOLDERS_TIMEOUT) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  HTTP error {url[:70]}…: {e}")
        return None


def _holders_for_token(data, yes_token):
    """Aus der /holders-Antwort (Liste von {token, holders}) die Holder-Liste des YES-Tokens
    ziehen. → [(wallet, amount)]. Fallback: flache Liste, falls Format abweicht."""
    groups = data if isinstance(data, list) else (data.get("holders") if isinstance(data, dict) else None)
    rows = None
    yt = str(yes_token)
    for g in (groups or []):
        if isinstance(g, dict) and "holders" in g:          # gruppiert {token, holders:[...]}
            if str(g.get("token")) == yt:
                rows = g.get("holders"); break
        else:                                                # bereits flache Holder-Liste
            rows = groups; break
    out = []
    for h in (rows or []):
        if not isinstance(h, dict):
            continue
        w = h.get("proxyWallet") or h.get("proxy_wallet") or h.get("wallet")
        a = h.get("amount") or h.get("size") or h.get("balance")
        try:
            a = float(a)
        except (TypeError, ValueError):
            continue
        if w and a > 0:
            out.append((w, a))
    return out


def _outcome_smartmoney(condition: str, yes_token: str, price):
    """{usd, topHolderShare, holders, _big} oder None. condition=conditionId (0x…), yes_token=clobTokenId."""
    if not condition or not yes_token or not isinstance(price, (int, float)) or price <= 0:
        return None
    data = _http_get(HOLDERS_URL.format(cond=condition))
    holders = _holders_for_token(data, yes_token)
    if not holders:
        return None
    amounts = sorted((a for _, a in holders), reverse=True)
    tot_amt = sum(amounts)
    usd = tot_amt * float(price)             # Shares × $/Share = $-Wert der Positionen
    top = sum(amounts[:TOP_N]) / tot_amt if tot_amt > 0 else 0.0
    big = sum(1 for _, a in holders if a * float(price) >= BIG_TRADER_USD)
    # Einzel-Wallets (Top-N nach Größe) fürs Wallet-Dashboard behalten
    top_wallets = [{"wallet": w, "usd": round(a * float(price), 0), "shares": round(a, 0)}
                   for w, a in sorted(holders, key=lambda x: x[1], reverse=True)[:TOP_WALLETS_PER_OUTCOME]]
    return {"usd": round(usd, 0), "topHolderShare": round(top, 3),
            "holders": len(holders), "_big": big, "_wallets": top_wallets}


def _big_trades(condition, pick_label, side, price):
    """Große jüngste Trades (≥ BIG_TRADE_USD) auf einen Outcome-Markt → Liste.
    /trades liefert je Trade {proxyWallet, side BUY/SELL, size, price, timestamp}.
    Defensiv geparst (blind gebaut — Polymarket geoblockt). Leere Liste bei Fehlern."""
    if not condition:
        return []
    data = _http_get(TRADES_URL.format(cond=condition))
    rows = data if isinstance(data, list) else (data.get("trades") if isinstance(data, dict) else None)
    out = []
    for t in (rows or []):
        if not isinstance(t, dict):
            continue
        w = t.get("proxyWallet") or t.get("proxy_wallet") or t.get("wallet")
        sz = t.get("size") or t.get("amount") or t.get("shares")
        pr = t.get("price")
        action = (t.get("side") or t.get("type") or "").upper()
        ts = t.get("timestamp") or t.get("time") or t.get("matchTime")
        try:
            sz = float(sz); pr = float(pr) if pr is not None else float(price)
        except (TypeError, ValueError):
            continue
        usd = sz * pr
        if not w or usd < BIG_TRADE_USD:
            continue
        # Unix-Sekunden → ISO falls nötig
        ts_iso = ts
        try:
            if ts and (isinstance(ts, (int, float)) or str(ts).isdigit()):
                ts_iso = datetime.fromtimestamp(int(ts), timezone.utc).isoformat()
        except Exception:
            ts_iso = None
        out.append({"wallet": w, "side": side, "pick": pick_label,
                    "usd": round(usd, 0), "price": round(pr, 3),
                    "action": "BUY" if action.startswith("B") else ("SELL" if action.startswith("S") else action),
                    "ts": ts_iso})
    return out


def main():
    if not PRICES_FILE.exists():
        print("⚠️  wm_poly_prices.json fehlt — nichts zu tun."); return
    fixtures = json.loads(PRICES_FILE.read_text(encoding="utf-8")).get("allFixtures", [])
    if fixtures and not any(fx.get("hwCondition") for fx in fixtures):
        print("⚠️  Keine conditionId in wm_poly_prices.json — fetch_wm_poly_prices.py muss "
              "ZUERST laufen (schreibt hwCondition/drCondition/awCondition). Manuell testen: "
              "erst Preise, dann Smart-Money.")
    matches = {}
    wallet_matches = {}          # 21.06.2026: Wallet-Dashboard pro Spiel
    all_positions, all_trades, all_clusters = [], [], []   # 22.06.: Konsens-Cluster-Feed
    n_ok = 0
    n_skip_ko = 0
    for fx in fixtures:
        key = fx.get("key")
        if not key:
            continue
        if _kickoff_passed(fx):
            n_skip_ko += 1
            continue   # gelaufen/in-play → offenes Interesse ist Phantom
        home_nm = fx.get("home") or fx.get("homeName") or fx.get("homeId") or key.split("-")[0]
        away_nm = fx.get("away") or fx.get("awayName") or fx.get("awayId") or key.split("-")[-1]
        # side → was wird gewettet (Pick-Label)
        pick_label = {"home": f"{home_nm} Sieg", "draw": "Unentschieden", "away": f"{away_nm} Sieg"}
        legs = {
            "home": (fx.get("hwCondition"), (fx.get("hwTokens") or [None])[0], fx.get("poly_hw")),
            "draw": (fx.get("drCondition"), (fx.get("drTokens") or [None])[0], fx.get("poly_dr")),
            "away": (fx.get("awCondition"), (fx.get("awTokens") or [None])[0], fx.get("poly_aw")),
        }
        outcomes, total, top_traders = {}, 0.0, 0
        positions, trades = [], []
        for side, (cond, tok, price) in legs.items():
            sm = _outcome_smartmoney(cond, tok, price)
            if not sm:
                continue
            wallets = sm.pop("_wallets", [])
            outcomes[side] = sm
            total += sm["usd"]
            top_traders += sm.pop("_big")
            for w in wallets:
                positions.append({"wallet": w["wallet"], "usd": w["usd"], "shares": w["shares"],
                                  "side": side, "pick": pick_label[side]})
            trades.extend(_big_trades(cond, pick_label[side], side, price))
        if not outcomes or total < MIN_WRITE_USD:
            continue   # $0.00M-Platzhalter → nicht schreiben
        # Konsens-Cluster + Net-Flow je Seite aus den großen Trades (21.06.→22.06., PolymarketScan)
        cluster = _cluster_metrics(trades, _cfg_cluster_window_h())
        hk = _hours_to_kickoff(fx)
        for side, o in outcomes.items():
            o["share"] = round(o["usd"] / total, 3)
            cm = cluster.get(side)
            if cm:
                o.update(cm)
        matches[key] = {"totalUsd": round(total, 0), "topTraders": top_traders,
                        "hoursToKickoff": hk, "outcomes": outcomes}
        # Wallet-Dashboard-Daten
        positions.sort(key=lambda p: p["usd"], reverse=True)
        trades.sort(key=lambda t: (t.get("ts") or ""), reverse=True)
        wallet_matches[key] = {"home": home_nm, "away": away_nm,
                               "topPositions": positions[:12], "bigTrades": trades[:20]}
        for p in positions:
            all_positions.append({**p, "match": f"{home_nm} – {away_nm}", "key": key})
        for t in trades:
            all_trades.append({**t, "match": f"{home_nm} – {away_nm}", "key": key})
        # Konsens-Cluster-Feed: je Seite mit erkanntem Cluster/Net-Flow eine Zeile fürs Dashboard.
        # Fakten only — der Tab entscheidet Filter/Labels (Cluster-Stärke, Exit-Warnung nah am KO).
        for side, cm in cluster.items():
            if cm.get("cluster", 0) <= 0 and cm.get("netFlowUsd", 0) == 0:
                continue
            all_clusters.append({
                "key": key, "match": f"{home_nm} – {away_nm}", "side": side,
                "pick": pick_label[side], "cluster": cm.get("cluster", 0),
                "netFlowUsd": cm.get("netFlowUsd", 0), "buyUsd": cm.get("buyUsd", 0),
                "sellUsd": cm.get("sellUsd", 0), "hoursToKickoff": hk,
            })
        n_ok += 1
        print(f"  ✅ {key}: ${total/1e6:.2f}M · "
              + " · ".join(f"{s} {o['share']*100:.0f}%" for s, o in outcomes.items())
              + f" · {len(positions)} Wallets, {len(trades)} große Trades")

    # WIPE-SCHUTZ (12.07.2026, Wipe-Audit): Fällt die Polymarket-Holders/Trades-API für ALLE Legs
    # aus (Geoblock, Rate-Limit) — oder ist wm_poly_prices.json leer — bleiben matches/wallet_matches
    # leer und hätten die befüllten Dateien überschrieben → smart_money-Signal tot + 🐋-Wallets-Tab
    # leer. Bei 0 verarbeiteten Spielen NICHT schreiben (alter Stand bleibt).
    if not matches and OUT_FILE.exists():
        print(f"\n❌ 0 Spiele mit Smart-Money-Daten (Poly-API/Geoblock?) — {OUT_FILE.name} + "
              f"{WALLETS_FILE.name} NICHT überschrieben, alter Stand bleibt erhalten.")
        return

    OUT_FILE.write_text(json.dumps(
        {"matches": matches, "updatedAt": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False, indent=2), encoding="utf-8")

    # Globale Bestenliste + Trade-Feed (für das Wallet-Dashboard)
    all_positions.sort(key=lambda p: p["usd"], reverse=True)
    all_trades.sort(key=lambda t: (t.get("ts") or ""), reverse=True)
    # Konsens-Cluster: stärkster Konsens zuerst, bei Gleichstand größter Abfluss (Exit) oben
    all_clusters.sort(key=lambda c: (c.get("cluster", 0), -c.get("netFlowUsd", 0)), reverse=True)
    WALLETS_FILE.write_text(json.dumps({
        "matches":          wallet_matches,
        "topPositionsAll":  all_positions[:LEADERBOARD_MAX],
        "bigTradesAll":     all_trades[:LEADERBOARD_MAX],
        "clustersAll":      all_clusters[:LEADERBOARD_MAX],
        "updatedAt":        datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n💾 {n_ok}/{len(fixtures)} Spiele mit Smart-Money "
          f"({n_skip_ko} gelaufen übersprungen) → {OUT_FILE.name}")
    print(f"🐋 Wallet-Dashboard: {len(all_positions)} Positionen, {len(all_trades)} große Trades, "
          f"{len(all_clusters)} Cluster → {WALLETS_FILE.name}")


if __name__ == "__main__":
    main()
