#!/usr/bin/env python3
"""
poly_whale_watch.py — Polymarket Whale-Watch (Telegram Trades-Channel)
================================================================================
26.07.2026 (Lucas: „Service für die Polymarket-Wallet-Schicht, alle Sportarten, zum Testen
in den Trades-Channel"). Geschwister zum Steam-Move-Service (detect_wm_sharp_moves.py), nur
für Polymarket: alertet, wenn eine WALLET eine große NEUE Position eingeht.

## Warum Whale-Watch und nicht „Geld-Mehrheit"
Auf Polymarket IST der Preis die Geldverteilung — der Backtest (poly_money_broad.json) zeigt
moneyHitRate == priceHitRate. „Der Mehrheit folgen" bringt also keinen eigenen Vorteil. Das
Signal steckt in EINZELNEN großen Wallets: wer setzt wie viel, zu welchem Preis, und hat die
Wallet in der Vergangenheit recht gehabt (scores: wins/n).

## Quelle
poly_wallet_track.json (vom Mac-Runner, poly_money_broad.py):
  · open   : {"wallet|key|side": {wallet,key,side,league,firstPrice,firstTs,lastPrice,usd}}
  · scores : {wallet: {n, wins, clvSumPP, usd}}   ← Track-Record je Wallet

## Ausgabe
Ein HTML-Post je frischer Großposition in den Trades-Channel (TELEGRAM_TRADES_CHAT_ID).

## Env
  TELEGRAM_TOKEN / TELEGRAM_TRADES_CHAT_ID   — ohne Token = Vorschau (stdout)
  WHALE_MIN_USD         — Mindestgröße OHNE Track-Record (Default 25000)
  WHALE_MIN_USD_TRACKED — Mindestgröße für SMARTE Wallets (n≥MIN_TR & ≥MIN_HITRATE) (Default 5000)
  WHALE_MIN_HITRATE     — Mindest-Trefferquote fürs smarte Band (Default 0.5)
  WHALE_FRESH_DAYS     — nur Positionen, die zuletzt in N Tagen eröffnet/aufgestockt (Default 2)
  WHALE_MIN_TR         — ab wie vielen Auflösungen ein Track-Record gezeigt wird (Default 3)
  WHALE_MAX_ALERTS     — max Alerts je Lauf (Default 8)

## Dedup
poly_whale_seen.json {posKey → {usd, ts}}: je Position EINMAL alerten; erneut nur, wenn die
Wallet signifikant aufstockt (≥ +50% USD) — dann als „aufgestockt".
"""
import json, os, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
TRACK_FILE = BASE / "poly_wallet_track.json"
SEEN_FILE  = BASE / "poly_whale_seen.json"
LOG_FILE   = BASE / "telegram-log.json"

TELEGRAM_TOKEN = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
CHAT_ID        = (os.environ.get("TELEGRAM_TRADES_CHAT_ID") or "").strip()

# 26.07.2026 (Lucas: „$5K ohne Record ist Rauschen"): gestaffelt. Ohne Track-Record zählt NUR
# Größe → hohe Schwelle. Mit Record (n≥MIN_TR) ist es smart → niedrige Schwelle.
MIN_USD_UNTRACKED = float(os.environ.get("WHALE_MIN_USD")         or 25000)
MIN_USD_TRACKED   = float(os.environ.get("WHALE_MIN_USD_TRACKED") or 5000)
MIN_HITRATE       = float(os.environ.get("WHALE_MIN_HITRATE")     or 0.5)   # „smart" = Record UND ≥50% Treffer
FRESH_DAYS  = int(os.environ.get("WHALE_FRESH_DAYS")  or 2)
MIN_TR      = int(os.environ.get("WHALE_MIN_TR")      or 3)
MAX_ALERTS  = int(os.environ.get("WHALE_MAX_ALERTS")  or 8)
RESTOCK_MULT = 1.5   # erneuter Alert erst bei ≥ +50% Größe

# league-Key → (Emoji, Klartext)
_SPORT = {
    "ESPORTS": ("🎮", "E-Sport"), "TENNIS": ("🎾", "Tennis"),
    "MLB": ("⚾", "MLB Baseball"), "NBA": ("🏀", "NBA"), "WNBA": ("🏀", "WNBA"),
    "NFL": ("🏈", "NFL"), "NHL": ("🏒", "NHL"), "MMA": ("🥊", "MMA"), "UFC": ("🥊", "UFC"),
    "GOLF": ("⛳", "Golf"), "F1": ("🏎️", "Formel 1"), "CRICKET": ("🏏", "Cricket"),
}
def _sport(league: str):
    x = str(league or "").upper()
    if x in _SPORT:
        return _SPORT[x]
    if x.startswith("SOCCER") or "LIGA" in x or "MLS" in x or "EPL" in x or "UCL" in x:
        return ("⚽", "Fußball")
    return ("🎯", (league or "Sport").title())


# ── Helpers ────────────────────────────────────────────────────────────────────
def _load(path, default):
    try:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _iso(t):
    try:
        return datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except Exception:
        return None

def _cents(p):
    try:
        return f"{round(float(p) * 100)}¢"
    except Exception:
        return "—"

def _usd(v):
    try:
        n = float(v)
    except Exception:
        return "$0"
    if n >= 1e6: return f"${n/1e6:.2f}M"
    if n >= 1e3: return f"${n/1e3:.1f}K".replace(".0K", "K")
    return f"${round(n)}"

def _wallet(w):
    s = str(w or "")
    return (s[:6] + "…" + s[-4:]) if len(s) > 12 else s

def _wallet_link(w):
    """Kurz-ID als klickbarer Link auf das öffentliche Polymarket-Profil der Wallet.
    Als Text wäre die halbe Adresse wertlos — als Link führt sie zur ganzen Historie."""
    full = str(w or "").strip()
    short = _wallet(full)
    if full.startswith("0x"):
        return f'<a href="https://polymarket.com/profile/{full}">{short}</a>'
    return short


def track_record(scores: dict, wallet: str):
    """Track-Record-Text aus scores[wallet], oder None wenn zu dünn."""
    s = scores.get(wallet) if isinstance(scores, dict) else None
    if not isinstance(s, dict):
        return None
    n = s.get("n") or 0
    if n < MIN_TR:
        return None
    wins = s.get("wins") or 0
    pct = round(wins / n * 100) if n else 0
    return f"bisher <b>{wins}/{n} richtig</b> ({pct}%)"


def _wallet_line(scores: dict, wallet) -> str:
    """Nur eine gute Bilanz wird als Zahl gezeigt (Verkaufsargument). Schwacher/kein/zu duenner
    Record → neutral „im Aufbau", damit ein legitimer Groessen-Alert nicht durch eine 1/3-Quote
    abgewertet wird. Die volle Historie ist ueber den Wallet-Link ohnehin einen Klick entfernt."""
    link = _wallet_link(wallet)
    s = scores.get(wallet) if isinstance(scores, dict) else None
    n = (s.get("n") or 0) if isinstance(s, dict) else 0
    if n >= MIN_TR:
        wins = s.get("wins") or 0
        if (wins / n) >= MIN_HITRATE:
            return f"Wallet {link} · ✅ <b>bewiesene Wallet</b> ({wins}/{n} richtig, {round(wins/n*100)}%)"
    return f"Wallet {link} · <i>Track-Record noch im Aufbau</i>"


def build_card(pos: dict, scores: dict, restock: bool) -> str:
    emoji, sport = _sport(pos.get("league"))
    side  = pos.get("side") or "?"
    price = pos.get("firstPrice")
    usd   = pos.get("usd") or 0
    header = "🐋 <b>Whale stockt auf</b>" if restock else "🐋 <b>Großer Whale-Einstieg</b>"
    lines = [
        header,
        f"{emoji} <b>{_usd(usd)}</b> auf <b>{side}</b> @ {_cents(price)}",
        f"{sport}",
    ]
    lines.append("")
    lines.append(_wallet_line(scores, pos.get("wallet")))
    # Preiskontext: klarer Außenseiter, gegen den der Markt steht
    try:
        if float(price) < 0.45:
            lines.append("💡 Unter 50¢ = der Markt sieht die Seite als Außenseiter — die Wallet hält dagegen.")
    except Exception:
        pass
    lines.append("\n🤖 CocoBet Whale-Watch")
    return "\n".join(lines)


# ── Telegram ────────────────────────────────────────────────────────────────────
def tg_send(text: str) -> bool:
    if not TELEGRAM_TOKEN:
        print("⚠️  Kein TELEGRAM_TOKEN — Vorschau:")
        print(text); print()
        return True
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req  = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("ok", False)
    except urllib.error.HTTPError as e:
        print(f"❌ Telegram HTTP {e.code}: {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"❌ Telegram Fehler: {e}")
        return False

def _log_send(preview, meta):
    try:
        log = _load(LOG_FILE, [])
        if not isinstance(log, list): log = []
        entry = {"type": "poly_whale", "sentAt":
                 datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "preview": preview[:160], "chatId": CHAT_ID}
        entry.update(meta or {})
        log.append(entry); log = log[-200:]
        _save(LOG_FILE, log)
    except Exception:
        pass


# ── Auswahl ─────────────────────────────────────────────────────────────────────
def select(track: dict, seen: dict, now: datetime):
    """Liefert (Liste alertwürdiger Positionen, aktualisierter seen-Store)."""
    openpos = (track or {}).get("open") or {}
    scores  = (track or {}).get("scores") or {}
    items = openpos.items() if isinstance(openpos, dict) else []
    out = []
    for pkey, pos in items:
        if not isinstance(pos, dict):
            continue
        usd = float(pos.get("usd") or 0)
        # Gestaffelte Schwelle: niedrig NUR für bewiesen ordentliche Wallets (Record UND ≥50%
        # Treffer = smart); ein schlechter Record (z.B. 0/4) ist KEIN Freifahrtschein → hohe Schwelle.
        _s = scores.get(pos.get("wallet"))
        _n = (_s.get("n") or 0) if isinstance(_s, dict) else 0
        _smart = _n >= MIN_TR and ((_s.get("wins") or 0) / _n) >= MIN_HITRATE
        if usd < (MIN_USD_TRACKED if _smart else MIN_USD_UNTRACKED):
            continue
        # Frische: firstTs innerhalb FRESH_DAYS (kein Alt-Flut beim ersten Lauf)
        ft = _iso(pos.get("firstTs"))
        if ft and (now - ft).days >= FRESH_DAYS:
            # alt — aber wenn signifikant aufgestockt seit letztem Alert, trotzdem melden
            prev = seen.get(pkey)
            if not (prev and usd >= (prev.get("usd", 0) * RESTOCK_MULT)):
                continue
        prev = seen.get(pkey)
        restock = False
        if prev:
            if usd < prev.get("usd", 0) * RESTOCK_MULT:
                continue          # schon gemeldet, nicht signifikant größer → skip
            restock = True
        out.append((pkey, pos, restock))
    # größte zuerst
    out.sort(key=lambda t: -(float(t[1].get("usd") or 0)))
    return out


def main():
    print("=== poly_whale_watch.py ===")
    track = _load(TRACK_FILE, {})
    if not track:
        print("  ℹ️  Keine poly_wallet_track.json — nichts zu tun."); return
    scores = track.get("scores") or {}
    seen   = _load(SEEN_FILE, {})
    now    = datetime.now(timezone.utc)

    cand = select(track, seen, now)
    print(f"  {len(cand)} alertwürdige Position(en) (≥ {_usd(MIN_USD_TRACKED)} mit / {_usd(MIN_USD_UNTRACKED)} ohne Record, frisch)")

    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sent = 0
    for pkey, pos, restock in cand[:MAX_ALERTS]:
        card = build_card(pos, scores, restock)
        if tg_send(card):
            sent += 1
            seen[pkey] = {"usd": float(pos.get("usd") or 0), "ts": now_iso}
            _log_send(card.split("\n")[1] if "\n" in card else card,
                      {"posKey": pkey, "usd": pos.get("usd"), "league": pos.get("league")})
    _save(SEEN_FILE, seen)
    print(f"  ✅  {sent} Whale-Alert(s) gesendet.")


if __name__ == "__main__":
    main()
