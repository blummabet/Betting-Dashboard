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
  WHALE_SIG_Z           — Signifikanz-Schärfe fürs smarte Band: Wilson-Untergrenze der Quote muss
                          > 50% (kein Münzwurf). 1.645 = 95% einseitig (Default), 1.2816 = 90% (mehr Alerts)
  WHALE_FRESH_DAYS     — nur Positionen, die zuletzt in N Tagen eröffnet/aufgestockt (Default 2)
  WHALE_MIN_TR         — ab wie vielen Auflösungen ein Track-Record gezeigt wird (Default 3)
  WHALE_MAX_ALERTS     — max Alerts je Lauf (Default 8)

## Dedup
poly_whale_seen.json {posKey → {usd, ts}}: je Position EINMAL alerten; erneut nur, wenn die
Wallet signifikant aufstockt (≥ +50% USD) — dann als „aufgestockt".
"""
import json, math, os, urllib.request, urllib.error, html
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
MIN_USD_UNTRACKED = float(os.environ.get("WHALE_MIN_USD")         or 50000)   # 01.08.2026 (Lucas): rauf von 25K — ohne Record ist Kleinvieh nur Rauschen
MIN_USD_TRACKED   = float(os.environ.get("WHALE_MIN_USD_TRACKED") or 5000)
MIN_HITRATE       = float(os.environ.get("WHALE_MIN_HITRATE")     or 0.5)   # „smart" = Record UND ≥50% Treffer
FRESH_DAYS  = int(os.environ.get("WHALE_FRESH_DAYS")  or 2)
MIN_TR      = int(os.environ.get("WHALE_MIN_TR")      or 8)   # 02.08.2026 (Lucas): rauf von 3 — 2/3 ist kein Beweis
MAX_ALERTS  = int(os.environ.get("WHALE_MAX_ALERTS")  or 8)
RESTOCK_MULT = 1.5   # erneuter Alert erst bei ≥ +50% Größe

# 05.08.2026 (Lucas): die alte Sharp-Textliste (poly_money_broad) nutzte ein SCHWAECHERES scharf-Gate
# (roh >=50% Treffer, n>=4) und spammte 56%-Tennis-Wallets 6x. Sie wird abgeschaltet; der bewiesen-
# scharfe FRISCHE Einstieg wird jetzt HIER als volle Karte mitgezogen, mit dem strengen _is_smart-Gate
# (n>=8, Wilson>50%, kein Verlierer). Klein-aber-scharf darf unter die Whale-Geldschwelle, ABER nur
# solange der Preis noch nahe am Einstieg (handelbar) steht.
MIN_USD_SHARP       = float(os.environ.get("WHALE_MIN_USD_SHARP") or 2000)          # Klein-aber-scharf-Boden (nur Trades)
TRADEABLE_MAX_CENTS = float(os.environ.get("WHALE_TRADEABLE_MAX_CENTS") or 0.06)    # Einstieg->jetzt max +6c teurer, sonst Zug weg
MAX_PER_WALLET      = int(os.environ.get("WHALE_MAX_PER_WALLET") or 1)              # je Wallet max Karten/Lauf (6x-Spam killen)

# 31.07.2026 (Lucas) — ÖFFENTLICHER Whale-Watch (CocoBet-Community): kuratiert, zwei Bänder —
# „riesig" ab $100K (jedes Wallet) ODER „bewährt" ab $25K (Record n≥5 & ≥50% Treffer). Eigener
# Dedup-State + Poly-Matchup aus poly_money_broad_close.json, damit der Post die Paarung zeigt.
PUB_MIN_USD_UNTRACKED = float(os.environ.get("WHALE_PUB_MIN_USD")         or 100000)
PUB_MIN_USD_TRACKED   = float(os.environ.get("WHALE_PUB_MIN_USD_TRACKED") or 25000)
PUB_MIN_TR            = int(os.environ.get("WHALE_PUB_MIN_TR")            or 8)   # 02.08.2026 (Lucas): "bewiesen" konsistent ab n>=8
PUB_MIN_HITRATE       = float(os.environ.get("WHALE_PUB_MIN_HITRATE")     or 0.5)
PUB_MIN_USD_NOREC     = float(os.environ.get("WHALE_PUB_MIN_USD_NOREC")   or 150000)   # 06.08.2026 (Lucas: Feed straffen): Wallet OHNE belastbaren Record (n<PUB_MIN_TR) nur ab so viel $


# 03.08.2026 (Lucas: „50% ist Münzwurf, kein Beweis"): „bewiesen" heißt jetzt STATISTISCH über
# Münzwurf — die Wilson-Untergrenze der Trefferquote muss > 50% liegen, nicht bloß die rohe Quote
# ≥ 50%. Passt sich an die Stichprobe an: 24/47 (51%) reicht nicht, 6/11 (55%) erst recht nicht.
SIG_Z = float(os.environ.get("WHALE_SIG_Z") or 1.645)  # 1.645 = 95% EINSEITIG („signifikant über 50%“); 1.2816 = 90% (mehr Alerts), 1.96 = strenger

def _wilson_lb(wins, n, z=SIG_Z):
    """Untere Wilson-Grenze der Trefferquote (robuster als roh bei kleinem n)."""
    if not n:
        return 0.0
    p = (wins or 0) / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - margin

def _beats_coinflip(wins, n, z=SIG_Z):
    """Ist die Trefferquote SIGNIFIKANT über 50% (kein Münzwurf)? Wilson-Untergrenze > 0.5."""
    return bool(n) and _wilson_lb(wins, n, z) > 0.5


def _is_smart(s, min_tr=MIN_TR, min_hitrate=MIN_HITRATE):
    """„Bewiesen ordentliche" Wallet fürs niedrige Schwellen-Band UND das „bewiesen"-Label.
    Record (n≥min_tr) UND ≥min_hitrate Treffer — plus (02.08.2026, Lucas, konservativ): ein
    BESTÄTIGTER Verlierer (Lifetime-P&L bekannt UND < 0) zählt NICHT als smart. Eine hohe Trefferquote
    bei Millionen-Verlust (gibt es real: 88% Treffer, −$7 Mio) ist kein Schärfe-Beweis. Unbekannter
    P&L bleibt drin → Verhalten wie bisher, nur nachweisliche Verlierer fliegen raus."""
    if not isinstance(s, dict):
        return False
    n = s.get("n") or 0
    if n < min_tr:
        return False
    if not _beats_coinflip(s.get("wins") or 0, n):   # signifikant >50%, nicht bloß roh ≥50%
        return False
    # 12.08.2026 (Lucas): CLV-Gate. Eine hohe Trefferquote OHNE positiven CLV ist Glueck, kein Edge —
    # reale Tennis-Wallet 7/9 (78%) aber Ø CLV negativ, lebenslang -70K. „Bewiesen" heisst: schlaegt
    # AUCH die Linie (Ø CLV >= 0), nicht nur die Quote. clvSumPP fehlt -> 0 (neutral, bleibt drin).
    if ((s.get("clvSumPP") or 0) / n) < 0:
        return False
    pnl = s.get("pnl")
    if isinstance(pnl, (int, float)) and pnl < 0:
        return False
    return True


def _is_confirmed_loser(s) -> bool:
    """02.08.2026 (Lucas: „ganz rausfiltern"): eine Wallet mit BEKANNTEM Lifetime-P&L < 0 ist ein
    nachgewiesener Verlierer und wird gar nicht mehr gepusht — auch nicht als großer Whale. Unbekannter
    P&L bleibt drin (nur nachweisliche Verlierer fliegen)."""
    if not isinstance(s, dict):
        return False
    pnl = s.get("pnl")
    return isinstance(pnl, (int, float)) and pnl < 0
PUB_CHAT   = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
PUB_SEEN_FILE = BASE / "poly_whale_public_seen.json"
BROAD_FILE    = BASE / "poly_money_broad_close.json"

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
    if _is_smart(s):
        wins = s.get("wins") or 0
        _clv = (s.get("clvSumPP") or 0) / n
        return f"Wallet {link} · ✅ <b>bewiesene Wallet</b> ({wins}/{n} richtig, {round(wins/n*100)}% · {_clv:+.1f}pp CLV)"
    # 06.08.2026 (Lucas: gleiche Loesung wie Public): rohe Bilanz ab n>=MIN_TR neutral zeigen, statt sie
    # hinter „im Aufbau" zu verstecken. Nur wirklich duenn (n<MIN_TR) oder Verlierer bleibt „im Aufbau".
    if isinstance(s, dict) and n >= MIN_TR and not _is_confirmed_loser(s):
        wins = s.get("wins") or 0
        return f"Wallet {link} · 📊 <b>Bilanz</b> {wins}/{n} ({round(wins/n*100)}%)"
    return f"Wallet {link} · <i>Track-Record noch im Aufbau</i>"


def _esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def build_card(pos: dict, scores: dict, restock: bool, broad: dict = None, extra: int = 0) -> str:
    """Trades-Push (01.08.2026, Lucas: „entscheidungsreif") — Matchup, Anpfiff, Einstieg→Jetzt-Preis,
    Wallet-Qualität, Markt-Link. Ein Push = eine fertige Wett-Entscheidung."""
    emoji, sport = _sport(pos.get("league"))
    side  = pos.get("side") or "?"
    key   = pos.get("key")
    usd   = pos.get("usd") or 0
    matchup = _matchup(key, broad)
    ko      = _kickoff_txt(key, broad)
    # 05.08.2026 (Lucas): Badge sagt WARUM die Karte kommt - Wal=grosses Geld, Feuer=bewiesen scharf,
    # beides=staerkstes Signal. Ein kleiner scharfer Einstieg ist kein 'Grosser' Einstieg.
    _sm  = _is_smart(scores.get(pos.get("wallet")) if isinstance(scores, dict) else None)
    _big = (pos.get("usd") or 0) >= MIN_USD_UNTRACKED
    if restock:
        header = "🐋🔥 <b>Whale stockt auf · scharf</b>" if _sm else "🐋 <b>Whale stockt auf</b>"
    elif _big and _sm:
        header = "🐋🔥 <b>Großer Einstieg · bewiesen scharf</b>"
    elif _big:
        header = "🐋 <b>Großer Whale-Einstieg</b>"
    elif _sm:
        header = "🔥 <b>Scharfe Wallet frisch drin</b>"
    else:
        header = "🐋 <b>Großer Whale-Einstieg</b>"
    lines = ["%s · %s %s" % (header, emoji, _esc(sport))]
    l2 = _esc(matchup) if matchup else "<b>%s</b>" % _esc(side)
    if ko:
        l2 += " · %s" % ko
    lines.append(l2)
    lines.append("💰 <b>%s</b> auf <b>%s</b>" % (_usd(usd), _esc(side)))
    pm = _price_move(pos)
    if pm:
        lines.append(pm)
    try:
        if float(pos.get("firstPrice")) < 0.45:
            lines.append("💡 Außenseiter-Seite — die Wallet hält gegen den Markt")
    except Exception:
        pass
    lines.append(_wallet_line(scores, pos.get("wallet")))
    if key:
        lines.append('<a href="https://polymarket.com/event/%s">→ Markt öffnen ↗</a>' % _esc(key))
    if extra and extra > 0:
        lines.append("➕ <i>+%d weitere Position(en) dieser Wallet</i>" % extra)
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
def _still_tradeable(pos, max_up=None):
    """Kann man dem Einstieg noch folgen? Nur wenn der Preis seither nicht deutlich TEURER wurde.
    firstPrice->lastPrice: gestiegen = du zahlst mehr = weniger Edge. > max_up teurer = Zug weg.
    Fehlender lastPrice -> als handelbar behandeln."""
    if max_up is None:
        max_up = TRADEABLE_MAX_CENTS
    try:
        fp = float(pos.get("firstPrice"))
    except Exception:
        return True
    lp = pos.get("lastPrice")
    if not isinstance(lp, (int, float)):
        return True
    return (lp - fp) <= max_up

def _dedup_by_wallet(cand, max_per=1):
    """6x-Spam killen: je Wallet hoechstens max_per Karten/Lauf (die groessten, da vor-sortiert).
    Rueckgabe: (gekuerzte Liste, {behaltener posKey -> Anzahl unterdrueckter weiterer Positionen})."""
    kept, counts, first_key, extras = [], {}, {}, {}
    for pkey, pos, restock in cand:
        w = pos.get("wallet")
        c = counts.get(w, 0)
        if c < max_per:
            kept.append((pkey, pos, restock)); counts[w] = c + 1; first_key[w] = pkey
        else:
            fk = first_key.get(w)
            if fk is not None:
                extras[fk] = extras.get(fk, 0) + 1
    return kept, extras


def select(track: dict, seen: dict, now: datetime,
           min_untracked=MIN_USD_UNTRACKED, min_tracked=MIN_USD_TRACKED,
           min_tr=MIN_TR, min_hitrate=MIN_HITRATE, sharp_floor=None):
    """Liefert Liste alertwürdiger Positionen. Schwellen/Record-Gate parametrisierbar (Public nutzt
    höhere Werte). REIN/testbar."""
    openpos = (track or {}).get("open") or {}
    scores  = (track or {}).get("scores") or {}
    items = openpos.items() if isinstance(openpos, dict) else []
    out = []
    for pkey, pos in items:
        if not isinstance(pos, dict):
            continue
        usd = float(pos.get("usd") or 0)
        # Gestaffelte Schwelle: niedrig NUR für bewiesen ordentliche Wallets (Record UND ≥Treffer =
        # smart); ein schlechter Record (z.B. 0/4) ist KEIN Freifahrtschein → hohe Schwelle.
        _s = scores.get(pos.get("wallet"))
        _n = (_s.get("n") or 0) if isinstance(_s, dict) else 0
        if _is_confirmed_loser(_s):
            continue          # 02.08.2026 (Lucas): bekannter Netto-Verlierer → gar nicht pushen, auch nicht als großer Whale
        _smart = _is_smart(_s, min_tr, min_hitrate)   # inkl. „kein bestätigter Verlierer"
        _floor = min_tracked if _smart else min_untracked
        # 05.08.2026 (Lucas): Klein-aber-scharf-Band (nur Trades, sharp_floor gesetzt) - bewiesen
        # scharfe Wallet darf UNTER den Smart-Boden, aber nur wenn der Einstieg noch handelbar ist.
        if usd < _floor:
            if not (sharp_floor is not None and _smart and usd >= sharp_floor):
                continue
        if sharp_floor is not None and _smart and not _still_tradeable(pos):
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


def _matchup(key, broad):
    """Paarung „TeamA v TeamB" aus poly_money_broad_close.json (shares-Keys = Ausgänge). None sonst."""
    m = (broad or {}).get(key) if isinstance(broad, dict) else None
    sh = (m or {}).get("shares") if isinstance(m, dict) else None
    names = list(sh.keys()) if isinstance(sh, dict) else []
    return " v ".join(names[:2]) if len(names) >= 2 else None


def _kickoff_txt(key, broad):
    """„Anpfiff in Xh/Min/d" aus poly_money_broad_close (hoursToKickoff). None wenn unbekannt/vorbei."""
    m = (broad or {}).get(key) if isinstance(broad, dict) else None
    h = (m or {}).get("hoursToKickoff") if isinstance(m, dict) else None
    if not isinstance(h, (int, float)) or h < 0:
        return None
    if h < 1:
        return "Anpfiff in %d Min" % round(h * 60)
    if h < 48:
        return ("Anpfiff in %.1fh" % h).replace(".0h", "h")
    return "Anpfiff in %dd" % round(h / 24)


def _price_move(pos):
    """Einstieg → jetzt (entryPrice/firstPrice → lastPrice). Zeigt, ob der Preis noch handelbar ist."""
    entry = pos.get("entryPrice")
    if not isinstance(entry, (int, float)):
        entry = pos.get("firstPrice")
    now = pos.get("lastPrice")
    if not isinstance(entry, (int, float)):
        return None
    if not isinstance(now, (int, float)) or abs(now - entry) < 0.005:
        return "Einstieg %s" % _cents(entry)   # nur Einstieg, wenn kein/gleicher Jetzt-Preis
    arrow = "↗" if now > entry else "↘"
    return "Einstieg %s → jetzt %s %s" % (_cents(entry), _cents(now), arrow)


def _pub_wallet_line(scores: dict, wallet) -> str:
    """Public: nur ein BEWÄHRTES Wallet kriegt die „🔥 scharf"-Zeile (Record n≥PUB_MIN_TR & ≥Treffer),
    inkl. Ø CLV und — sobald der Runner die echte P&L zieht — der Lifetime-Bilanz. Sonst neutral."""
    s = scores.get(wallet) if isinstance(scores, dict) else None
    n = (s.get("n") or 0) if isinstance(s, dict) else 0
    if _is_smart(s, PUB_MIN_TR, PUB_MIN_HITRATE):
        wins = s.get("wins") or 0
        clv = (s.get("clvSumPP") or 0) / n
        clvtxt = ", %s%.1fpp CLV" % ("+" if clv >= 0 else "", clv)
        extra = ""
        pnl = s.get("pnl")
        if isinstance(pnl, (int, float)):
            extra = " · %s%s lifetime" % ("+" if pnl >= 0 else "−", _usd(abs(pnl)))
        return "🔥 <b>bewiesen scharf</b> — %d/%d richtig (%d%%%s)%s" % (wins, n, round(wins / n * 100), clvtxt, extra)
    # 06.08.2026 (Lucas: „frueher stand der Track-Record oefter"): die strenge „bewiesen"-Huerde
    # (Wilson>50% + kein Verlierer) versteckte bei 81 von 89 Wallets mit echtem Record die Bilanz.
    # Ab n>=PUB_MIN_TR jetzt die rohe Bilanz als NEUTRALE Zeile zeigen (kein „scharf"-Versprechen),
    # damit man selbst urteilen kann. „im Aufbau" nur noch bei wirklich duennem Record (n<PUB_MIN_TR).
    if isinstance(s, dict) and n >= PUB_MIN_TR and not _is_confirmed_loser(s):
        wins = s.get("wins") or 0
        clv = (s.get("clvSumPP") or 0) / n
        clvtxt = " · %s%.1fpp CLV" % ("+" if clv >= 0 else "", clv)
        return "📊 <b>Bilanz</b>: %d/%d · %d%%%s" % (wins, n, round(wins / n * 100), clvtxt)
    return "👀 <i>großes Wallet · Track-Record noch im Aufbau</i>"


def _pub_ok(pos: dict) -> bool:
    """Public-Qualität: nur SPORT (kein Politik/Sonstiges → _sport-Default 🎯) und ein sinnvoller
    Einstiegspreis (nicht quasi-settled @~100¢/0¢). Hält Wahl-/Krypto-Märkte aus dem Sport-Channel."""
    if _sport(pos.get("league"))[0] == "🎯":
        return False
    try:
        p = float(pos.get("firstPrice"))
    except (TypeError, ValueError):
        return False
    return 0.03 <= p <= 0.97


def build_public_card(pos: dict, scores: dict, restock: bool, broad: dict) -> str:
    """Öffentliches Format (31.07.2026, Lucas), im Betfair-Moneyflow-Stil: Header, Paarung, Liga,
    die Wette, die Wallet-Qualität. Fett wo's zählt, Markt-Link zum Nachschauen."""
    emoji, sport = _sport(pos.get("league"))
    side = pos.get("side") or "?"
    key = pos.get("key")
    matchup = _matchup(key, broad)
    ko = _kickoff_txt(key, broad)   # 01.08.2026 (Lucas): Anpfiff + Preis-Bewegung auch im Public
    header = "🐋 <b>Polymarket Whale — stockt auf</b>" if restock else "🐋 <b>Polymarket Whale</b>"
    top = "%s <b>%s</b>" % (emoji, _esc(matchup)) if matchup else "%s <b>%s</b>" % (emoji, _esc(side))
    if ko:
        top += " · %s" % ko
    lines = [header, "", top, "<i>%s</i>" % _esc(sport), "",
             "💰 <b>%s</b> auf <b>%s</b>" % (_usd(pos.get("usd") or 0), _esc(side))]
    pm = _price_move(pos)
    if pm:
        lines.append(pm)
    try:
        if float(pos.get("firstPrice")) < 0.45:
            lines.append("💡 Außenseiter-Seite — die Wallet hält gegen den Markt")
    except Exception:
        pass
    lines.append(_pub_wallet_line(scores, pos.get("wallet")))
    if key:
        lines.append('\n<a href="https://polymarket.com/event/%s">Markt ansehen ↗</a>' % _esc(key))
    return "\n".join(lines)


def _tg_public(text: str) -> bool:
    """An den ÖFFENTLICHEN CocoBet-Channel (TELEGRAM_CHAT_ID). Ohne Token/Chat → Vorschau."""
    if not TELEGRAM_TOKEN or not PUB_CHAT:
        print("PUBLIC-Vorschau (kein TOKEN/CHAT_ID):")
        print(text); print()
        return False
    body = json.dumps({"chat_id": PUB_CHAT, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_TOKEN,
                                 data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print("Public-Send-Fehler:", e)
        return False


def _pub_keep(pos, scores):
    """Feed straffen (06.08.2026, Lucas): ein grosses Wallet OHNE belastbaren Record (n<PUB_MIN_TR)
    kommt nur bei sehr grossem Einsatz (>= PUB_MIN_USD_NOREC) in den Public-Feed. Wallets MIT Record
    (n>=PUB_MIN_TR, inkl. der bewiesenen) bleiben bei ihren normalen Schwellen. REIN/testbar."""
    s = scores.get(pos.get("wallet")) if isinstance(scores, dict) else None
    n = (s.get("n") or 0) if isinstance(s, dict) else 0
    if n >= PUB_MIN_TR:
        return True
    return (float(pos.get("usd") or 0) >= PUB_MIN_USD_NOREC)


def main():
    print("=== poly_whale_watch.py ===")
    track = _load(TRACK_FILE, {})
    if not track:
        print("  ℹ️  Keine poly_wallet_track.json — nichts zu tun."); return
    scores = track.get("scores") or {}
    seen   = _load(SEEN_FILE, {})
    now    = datetime.now(timezone.utc)

    broad = _load(BROAD_FILE, {})   # Matchup/Anpfiff/Preis-Kontext für die Trades-Cards
    # (01.08.2026, Lucas: 1a) Trades-Channel bekommt denselben Sanity-Filter wie Public:
    # nur Sport + Preis 3–97¢ → kein @100¢-schon-entschieden, kein Politik/Krypto-Müll.
    cand = [c for c in select(track, seen, now, sharp_floor=MIN_USD_SHARP) if _pub_ok(c[1])]
    cand, _extra = _dedup_by_wallet(cand, MAX_PER_WALLET)   # je Wallet max MAX_PER_WALLET Karten/Lauf
    print(f"  {len(cand)} alertwürdige Position(en) (Sport + 3–97¢, ≥ {_usd(MIN_USD_TRACKED)} mit / {_usd(MIN_USD_UNTRACKED)} ohne Record, frisch)")

    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sent = 0
    for pkey, pos, restock in cand[:MAX_ALERTS]:
        card = build_card(pos, scores, restock, broad, extra=_extra.get(pkey, 0))
        if tg_send(card):
            sent += 1
            seen[pkey] = {"usd": float(pos.get("usd") or 0), "ts": now_iso}
            _log_send(card.split("\n")[1] if "\n" in card else card,
                      {"posKey": pkey, "usd": pos.get("usd"), "league": pos.get("league")})
    _save(SEEN_FILE, seen)
    print(f"  ✅  {sent} Whale-Alert(s) (Trades) gesendet.")

    # 🐋 Öffentlicher Whale-Watch: kuratiert (riesig ab $100K ODER bewährt ab $25K), eigener Dedup.
    pub_seen = _load(PUB_SEEN_FILE, {})
    pub_cand = select(track, pub_seen, now, PUB_MIN_USD_UNTRACKED, PUB_MIN_USD_TRACKED,
                      PUB_MIN_TR, PUB_MIN_HITRATE)
    pub_cand = [c for c in pub_cand if _pub_ok(c[1])]   # nur Sport + sinnvoller Preis (Public)
    pub_cand = [c for c in pub_cand if _pub_keep(c[1], scores)]   # 06.08.2026 (Lucas): Feed straffen — grosse Wallets ohne Record nur ab PUB_MIN_USD_NOREC
    pub_sent = 0
    for pkey, pos, restock in pub_cand[:MAX_ALERTS]:
        if _tg_public(build_public_card(pos, scores, restock, broad)):
            pub_sent += 1
            pub_seen[pkey] = {"usd": float(pos.get("usd") or 0), "ts": now_iso}
    _save(PUB_SEEN_FILE, pub_seen)
    print(f"  🐋 Public-Whale: {len(pub_cand)} Kandidat(en), {pub_sent} gesendet.")


if __name__ == "__main__":
    main()
