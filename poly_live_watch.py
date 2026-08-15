#!/usr/bin/env python3
"""poly_live_watch.py — Live-Einstiegs-Alerts (11.08.2026, Lucas Stufe 2.1).

Meldet in den TRADES-Channel (Test — schauen, was durchkommt), wenn eine Wallet WAEHREND eines laufenden
Spiels frisch einsteigt: im Live-Top-4 (poly_money_broad_live.json), vor Anpfiff NICHT drin
(poly_money_broad_close.json), und entweder BEWIESEN scharf (poly_wallet_track.json, gleiche Definition wie
im Frontend _pwIsSharpScore) ODER gross (>= LIVE_BIG_USD). Dedup ueber poly_live_watch_seen.json. Read-only
bis auf den Seen-Dedup; Netz nur fuer Telegram (Silent-Guard: kein Token -> nichts). Laeuft am Mac-Runner
nach dem Live-Scan. Reine Auswahl-Logik (find_alerts) ohne Netz getestet."""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE = Path(__file__).resolve().parent
LIVE_FILE   = BASE / "poly_money_broad_live.json"
CLOSE_FILE  = BASE / "poly_money_broad_close.json"
WTRACK_FILE = BASE / "poly_wallet_track.json"
SEEN_FILE   = BASE / "poly_live_watch_seen.json"

LIVE_BIG_USD  = float(os.environ.get("POLY_LIVE_BIG_USD") or 25000)    # gross genug fuer Alarm auch OHNE Track-Record
SHARP_MIN_USD = float(os.environ.get("POLY_LIVE_SHARP_MIN_USD") or 5000)  # 12.08.2026 (Lucas): auch scharfe Wallets brauchen eine Mindest-Summe -- ein $370-Einstieg ist kein Signal
LIVE_MAX_PRICE = float(os.environ.get("POLY_LIVE_MAX_PRICE") or 0.77)   # 14.08.2026 (Lucas): 0.90->0.77 = Quote 1.30. Ueber 77¢ (Quote <1.30) live = eingepreiste Fuehrung/kurzer Favorit, reaktiv, kein Value (Al-Ettifaq @84¢ 1:0). Sportuebergreifend (auch eSport).
LIVE_MIN_PRICE = float(os.environ.get("POLY_LIVE_MIN_PRICE") or 0.10)   # <= toter Ausgang -> Lay/Rausch
LIVE_MAX_POS_FRAC = float(os.environ.get("POLY_LIVE_MAX_POS_FRAC") or 0.5)   # 15.08.2026 (Lucas): eine EINZELNE Position > 50% des ganzen Spiel-Volumens ist kein frischer Einstieg, sondern Positionswert/Artefakt -> raus ($136K in $150K-Spiel = 91%)
LIVE_CONTEST_MIN_USD = float(os.environ.get("POLY_LIVE_CONTEST_MIN_USD") or 25000)  # 12.08.2026 (Lucas): ab so viel je Seite = umkaempft -> gar kein Live-Signal (Gegenseiten-Krieg)
SEEN_TTL_H   = float(os.environ.get("POLY_LIVE_SEEN_TTL_H") or 12)   # gemeldete Wallet+Markt so lange nicht erneut
# Sharp-Definition — identisch zum Frontend: genug Historie UND profitabel UND schlaegt die Linie UND
# (klar ueber Muenzwurf ODER deutliche Kante).
SHARP_MIN_N, SHARP_MIN_HIT, SHARP_CLEAR_HIT, SHARP_STRONG_CLV = 4, 0.5, 0.55, 1.0

_ICON = {"esports": "\U0001f3ae", "tennis": "\U0001f3be", "cricket": "\U0001f3cf", "soccer": "⚽",
         "mls": "⚽", "ucl": "⚽", "epl": "⚽", "laliga": "⚽", "bundesliga": "⚽",
         "nba": "\U0001f3c0", "wnba": "\U0001f3c0", "nfl": "\U0001f3c8", "nhl": "\U0001f3d2",
         "mlb": "⚾", "ufc": "\U0001f94a", "mma": "\U0001f94a", "boxing": "\U0001f94a",
         "golf": "⛳", "f1": "\U0001f3c1", "lol": "\U0001f3ae", "cs2": "\U0001f3ae", "dota": "\U0001f3ae"}


def _load(p, d):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d


def _now():
    return datetime.now(timezone.utc)


def _score(scores, wallet):
    e = (scores or {}).get(wallet)
    if not isinstance(e, dict) or not e.get("n"):
        return None
    n = e["n"]
    return {"n": n, "avgClv": (e.get("clvSumPP") or 0) / n,
            "hit": (e.get("wins") or 0) / n, "pnl": float(e.get("pnl") or 0)}


def is_sharp(sc) -> bool:
    if not sc:
        return False
    if not (sc["n"] >= SHARP_MIN_N and sc["hit"] >= SHARP_MIN_HIT and sc["avgClv"] >= 0 and sc["pnl"] > 0):
        return False
    return sc["hit"] >= SHARP_CLEAR_HIT or sc["avgClv"] >= SHARP_STRONG_CLV


def _pregame_wallets(close, key):
    c = (close or {}).get(key) or {}
    return {str(w.get("wallet")).lower() for w in (c.get("whales") or [])
            if isinstance(w, dict) and w.get("wallet")}


def _contested(m, min_usd=LIVE_CONTEST_MIN_USD):
    """12.08.2026 (Lucas): „Gegenseiten-Krieg" live — hat der Markt Einstiege (>= min_usd) auf MEHR
    ALS EINER (noch offenen) Seite, ist er umkaempft und taugt NICHT als Live-Signal (zwei
    widerspruechliche Alerts zum selben Spiel). Dann wird fuer das Spiel gar nichts gesendet; nur klar
    einseitige Live-Einstiege kommen durch. Entschiedene/tote Seiten (@100/@0) zaehlen NICHT als
    Contest-Seite (das ist Abwicklung, kein Gegengeld). REIN/testbar."""
    if not isinstance(m, dict):
        return False
    prices = m.get("prices") or {}
    big_sides = set()
    for w in (m.get("whales") or []):
        if not isinstance(w, dict):
            continue
        side = w.get("side")
        pr = prices.get(side)
        if not isinstance(pr, (int, float)) or pr < LIVE_MIN_PRICE or pr > LIVE_MAX_PRICE:
            continue                              # entschiedene/tote Seite -> kein echtes Gegengeld
        if side and float(w.get("usd") or 0) >= min_usd:
            big_sides.add(side)
    return len(big_sides) >= 2


def find_alerts(live, close, scores, seen, now=None):
    """REIN/testbar. Neue Live-Einstiege (scharf ODER >= LIVE_BIG_USD), die vor Anpfiff nicht im Top-4
    waren und noch nicht in `seen` (Menge von sig). -> Liste alert-dicts, nach $ absteigend."""
    out = []
    for key, m in (live or {}).items():
        if not isinstance(m, dict):
            continue
        if _contested(m):
            continue                              # umkaempft: Gross-Geld auf beiden Seiten -> gar kein Live-Signal (Lucas 12.08.2026)
        pre = _pregame_wallets(close, key)
        for w in (m.get("whales") or []):
            if not isinstance(w, dict) or not w.get("wallet"):
                continue
            wal = str(w["wallet"])
            if wal.lower() in pre:
                continue                              # schon vor Anpfiff drin -> kein Live-Einstieg
            price = (m.get("prices") or {}).get(w.get("side"))
            if not isinstance(price, (int, float)) or price < LIVE_MIN_PRICE or price > LIVE_MAX_PRICE:
                continue                              # entschieden/tot (z.B. @100) -> Settlement, kein Signal (gilt auch fuer scharfe)
            usd = float(w.get("usd") or 0)
            # 15.08.2026 (Lucas): eine EINZELNE Position, die > POLY_LIVE_MAX_POS_FRAC (Default 50%) des
            # GANZEN Spiel-Volumens ausmacht, ist kein frischer Einstieg, sondern Positionswert
            # (Shares × Preis) einer laenger aufgebauten Position bzw. ein Daten-Artefakt. TEAM VISION:
            # $136K-„Einstieg" bei ~$150K Spiel-Volumen (91%) -> raus. (Frueher nur usd > totalUsd = 100%.)
            _mtot = float(m.get("totalUsd") or 0)
            if _mtot > 0 and usd > LIVE_MAX_POS_FRAC * _mtot:
                continue
            sc = _score(scores, wal)
            sharp = is_sharp(sc)
            if not ((sharp and usd >= SHARP_MIN_USD) or usd >= LIVE_BIG_USD):
                continue
            sig = "%s|%s" % (key, wal.lower())
            if sig in seen:
                continue
            out.append({"key": key, "wallet": wal, "side": w.get("side"), "usd": usd,
                        "league": m.get("league"), "sharp": sharp, "score": sc,
                        "prices": m.get("prices") or {}, "sig": sig})
    out.sort(key=lambda a: -a["usd"])
    return out


def _esc(s):
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _usd(v):
    v = float(v or 0)
    if v >= 1e6:
        return "$%.2fM" % (v / 1e6)
    if v >= 1e3:
        return ("$%.0fK" % (v / 1e3)) if v >= 1e4 else ("$%.1fK" % (v / 1e3))
    return "$%d" % round(v)


def _short(w):
    s = str(w or "")
    return (s[:6] + "…" + s[-4:]) if len(s) > 12 else s


def _label(key, prices):
    gen = {"yes", "no", "over", "under", "draw", "ja", "nein"}
    def _is_generic(n):
        s = str(n).strip().lower()
        # 15.08.2026 (Lucas): Poly-Draw = "Draw (X vs. Y)" -> nicht als Team zaehlen (sonst "X vs Draw (…)")
        return s in gen or s.startswith("draw") or s.startswith("the draw")
    names = [n for n in (prices or {}) if not _is_generic(n)]
    if len(names) >= 2:
        return "%s vs %s" % (names[0], names[1])
    s = re.sub(r"-\d{4}-\d{2}-\d{2}.*", "", str(key))
    return s.replace("-", " ").strip().title() or str(key)


def format_alert(a) -> str:
    ic = _ICON.get(str(a.get("league") or "").lower(), "•")
    sc = a.get("score")
    if a.get("sharp") and sc:
        tag = "\n\U0001f525 <b>scharf</b> · %+.1fpp Ø CLV · %d%% Treffer · n%d" % (
            sc["avgClv"], round(sc["hit"] * 100), sc["n"])
    else:
        tag = "\n\U0001f4b0 grosser Einstieg (ohne Track-Record)"
    price = a["prices"].get(a["side"]) if isinstance(a.get("prices"), dict) else None
    ptxt = " @%d¢" % round(price * 100) if isinstance(price, (int, float)) else ""
    url = "https://polymarket.com/event/" + str(a["key"])
    return ("⚡ <b>LIVE-Einstieg</b> · %s %s\n"
            "\U0001f534 <code>%s</code> → <b>%s</b> · %s%s%s\n%s"
            % (ic, _esc(_label(a["key"], a["prices"])), _short(a["wallet"]),
               _esc(a.get("side") or "?"), _usd(a["usd"]), ptxt, tag, url))


def _prune_seen(seen_raw, now):
    out, cutoff = {}, now - timedelta(hours=SEEN_TTL_H)
    for sig, ts in (seen_raw or {}).items():
        try:
            t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            t = None
        if t and t >= cutoff:
            out[sig] = ts
    return out


def main() -> int:
    now = _now()
    live = _load(LIVE_FILE, {})
    close = _load(CLOSE_FILE, {})
    wt = _load(WTRACK_FILE, {})
    scores = (wt.get("scores") if isinstance(wt, dict) else {}) or {}
    seen = _prune_seen(_load(SEEN_FILE, {}), now)
    alerts = find_alerts(live if isinstance(live, dict) else {},
                         close if isinstance(close, dict) else {},
                         scores, set(seen.keys()), now)
    sent = 0
    if alerts:
        try:
            import telegram_trades
            for a in alerts:
                if telegram_trades.send_trades_message(format_alert(a)):
                    seen[a["sig"]] = now.isoformat()   # nur bei echtem Versand als gesehen -> ohne Token kein stiller Verlust
                    sent += 1
        except Exception as exc:
            print("Live-Alert uebersprungen (nicht fatal):", exc)
    try:
        SEEN_FILE.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as exc:
        print("Seen-Schreibfehler:", exc)
    print("[LIVE-WATCH] %d Kandidat(en), %d in Trades-Channel gepusht" % (len(alerts), sent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
