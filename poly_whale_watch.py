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
import json, os, re as _re, urllib.request, urllib.error, html   # 25.08.2026: _re fuer sport_category (Spiegel von _pwSportCategory)
# 29.08.2026: `math` ist raus — die Wilson-Rechnung wohnt jetzt in sharp_gate.py.
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
import sharp_gate as SG   # 29.08.2026: DIE Sharp-Definition, geteilt mit Live-Watch + Frontend

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
CONTEST_MIN_USD       = float(os.environ.get("WHALE_CONTEST_MIN_USD")     or 100000)   # 12.08.2026 (Lucas): Public — Gross-Einstiege ab so viel auf ZWEI Seiten = umkaempft -> gar nicht posten
CONFLICT_TOP_N        = int(os.environ.get("WHALE_CONFLICT_TOP_N")        or 20)       # 24.08.2026 (Lucas, INOX-Fall): haelt eine andere Wallet aus den Top-N die Gegenseite, ist das Signal mehrdeutig — RANG statt Dollar, deshalb greift es auch bei $7K.
PUB_MIN_ODDS          = float(os.environ.get("WHALE_PUB_MIN_ODDS")       or 1.30)     # 22.08.2026 (Lucas): Public — Whale-Bet braucht Mindest-Quote (86c/1.16 = zu wenig Value). Einstieg/Jetzt <= 1/odds.
PUB_TOP_N             = int(os.environ.get("WHALE_PUB_TOP_N")            or 10)   # 23.08.2026 (Lucas): Public postet NUR die Top-N der Sharp-Rangliste (kuratiert), optisch mit Rang-Badge wie im Trades-Channel.


# 03.08.2026 (Lucas: „50% ist Münzwurf, kein Beweis"): „bewiesen" heißt jetzt STATISTISCH über
# Münzwurf — die Wilson-Untergrenze der Trefferquote muss > 50% liegen, nicht bloß die rohe Quote
# ≥ 50%. Passt sich an die Stichprobe an: 24/47 (51%) reicht nicht, 6/11 (55%) erst recht nicht.
# 29.08.2026: die Mathematik wohnt jetzt in sharp_gate.py — hier nur noch durchgereicht, damit
# es EINE Implementierung gibt statt einer pro Datei. WHALE_SIG_Z bleibt als Ueberschreibung.
SIG_Z = float(os.environ.get("WHALE_SIG_Z") or SG.SHARP_Z)  # 1.645 = 95% EINSEITIG; 1.2816 = 90% (mehr Alerts), 1.96 = strenger


def _wilson_lb(wins, n, z=SIG_Z):
    """Untere Wilson-Grenze der Trefferquote (robuster als roh bei kleinem n)."""
    return SG.wilson_lb(wins, n, z)


def _beats_coinflip(wins, n, z=SIG_Z):
    """Ist die Trefferquote SIGNIFIKANT über 50% (kein Münzwurf)? Wilson-Untergrenze > 0.5."""
    return SG.beats_coinflip(wins, n, z)


def _is_smart(s, min_tr=MIN_TR, min_hitrate=MIN_HITRATE):
    """„Bewiesen ordentliche" Wallet fürs niedrige Schwellen-Band UND das „bewiesen"-Label.
    29.08.2026: delegiert an sharp_gate.is_sharp — dieselbe Definition, die jetzt auch Dashboard,
    Shortlist, Push und Live-Watch benutzen. Inhaltlich unveraendert (n>=min_tr, Wilson >50%,
    Ø CLV >= 0, kein bestaetigter Verlierer); `min_hitrate` ist seit dem Wilson-Gate vom 03.08.
    ohne Wirkung und bleibt nur fuer Aufrufer in der Signatur stehen."""
    return SG.is_sharp(s, min_n=min_tr, z=SIG_Z)


def _is_confirmed_loser(s) -> bool:
    """02.08.2026 (Lucas: „ganz rausfiltern"): eine Wallet mit BEKANNTEM Lifetime-P&L < 0 ist ein
    nachgewiesener Verlierer und wird gar nicht mehr gepusht — auch nicht als großer Whale. Unbekannter
    P&L bleibt drin (nur nachweisliche Verlierer fliegen)."""
    return SG.is_confirmed_loser(s)
PUB_CHAT   = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
PUB_SEEN_FILE = BASE / "poly_whale_public_seen.json"
PUB_LEDGER_FILE = BASE / "poly_whale_public_ledger.json"   # 02.09.2026 (Lucas): jeder Public-Push wird abgerechnet
BROAD_FILE    = BASE / "poly_money_broad_close.json"
SHORTLIST_FILE = BASE / "poly_shortlist_track.json"   # 25.08.2026: traegt blockedCats — die EINE Sperrliste

# league-Key → (Emoji, Klartext)
_SPORT = {
    "ESPORTS": ("🎮", "E-Sport"), "TENNIS": ("🎾", "Tennis"),
    "MLB": ("⚾", "MLB Baseball"), "NBA": ("🏀", "NBA"), "WNBA": ("🏀", "WNBA"),
    "NFL": ("🏈", "NFL"), "NHL": ("🏒", "NHL"), "MMA": ("🥊", "MMA"), "UFC": ("🥊", "UFC"),
    "GOLF": ("⛳", "Golf"), "F1": ("🏎️", "Formel 1"), "CRICKET": ("🏏", "Cricket"),
}
BLOCKED_FALLBACK = ("US-Sport", "Kampfsport")   # nur wenn poly_shortlist_track.json fehlt

# Spiegel von _pwSportCategory (poly-wallets.js). Bewusst dieselbe Reihenfolge: spezifische
# Sportarten zuerst, sonst klauen breite Fussball-Begriffe wie "championship" sie weg.
_CAT_RULES = (
    ("E-Sport",    r"esport|cs2|csgo|\blol\b|dota|valorant"),
    ("US-Sport",   r"basketball|nba|nfl|americanfootball|baseball|mlb|icehockey|hockey|nhl|wnba|ncaa"),
    ("Tennis",     r"tennis|wta|atp"),
    ("Kampfsport", r"mma|ufc|boxing|box|kampf"),
    ("Golf",       r"golf"),
    ("Motorsport", r"f1|formula|motor|nascar"),
    ("Cricket",    r"cricket"),
)


def sport_category(league, sport=None):
    """Liga-String → Kategorie ("US-Sport", "Fussball", …). REIN/testbar.

    Der gestempelte Sport aus dem Capture hat Vorrang, genau wie im Dashboard — er faengt
    abgekuerzte Bewerbe, die der String-Rateversuch nie erkennt.
    """
    if sport:
        return str(sport)
    x = str(league or "").lower()
    for cat, rx in _CAT_RULES:
        if _re.search(rx, x):
            return cat
    # Exakt dieselbe Schreibweise wie _PW_CAT_ICON im Dashboard ("Fußball" mit ß) — die Sperrliste
    # kommt von dort, ein "Fussball" hier wuerde stumm nie matchen.
    return "Fußball" if _re.search(
        r"soccer|football|fussball|\bepl\b|premier|\bucl\b|\buel\b|uecl|uefa|champions|conmebol|"
        r"concacaf|copa|coupe|\bdfb\b|\befl\b|conference|europa|libertad|sudameri|\bmls\b|liga|ligue|"
        r"serie|bundesliga|eredivisie|allsven|superett|elitese|ekstrakla|veikkau|primeira|championship|"
        r"super-?lig|pro-?league|\blal\b", x) else "Sonstige"


def blocked_cats(shortlist=None):
    """Die gesperrten Kategorien — aus poly_shortlist_track.json, nicht hier hartkodiert. REIN.

    Sie entstehen in poly-wallets.js (PW_BLOCKED_BET_CATS) und wandern ueber emit_shortlist.mjs
    ins Papier-Depot. Legt Lucas die Sperre dort um, zieht der Push automatisch mit — zwei
    getrennte Listen waeren genau die Art Drift, die diesen Fix noetig gemacht hat.
    """
    got = (shortlist or {}).get("blockedCats") if isinstance(shortlist, dict) else None
    cats = [str(c) for c in got if c] if isinstance(got, list) else []
    return cats or list(BLOCKED_FALLBACK)


def bet_blocked(pos, cats=None):
    """Faellt diese Position in eine gesperrte Sportart? REIN."""
    if not isinstance(pos, dict):
        return False
    return sport_category(pos.get("league"), pos.get("sport")) in (cats or BLOCKED_FALLBACK)


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


# ── Top-20 Sharp-Rangliste im Push (23.08.2026, Lucas: „Top-20-Wallets extra highlighten, damit ich
# seh: ist eine Top-Wallet") ──────────────────────────────────────────────────────────────────────
# Spiegelt EXAKT die Dashboard-Rangliste (poly-wallets.js _pwSharpRanking). Modus A (echte Poly-P&L),
# sobald irgendein Wallet pnl hat, sonst Interim CLV-Kombi. Gates identisch: n-Floor, im P&L-Modus
# Ø CLV ≥ 0 & Treffer ≥ 45 %, plus 4-stellig-Filter (Ø-Einsatz ≥ $1.000). → {wallet_lower: Rang 1..20}.
_RANK_MIN_N_PNL   = 8
_RANK_MIN_N_CLV   = 12
_RANK_FLOOR_HIT   = 0.45
_RANK_MIN_AVG_USD = 1000.0
_RANK_HITW = 6.0
_RANK_K    = 6.0
_RANK_TOP  = 20


def _sharp_rank_map(scores):
    if not isinstance(scores, dict) or not scores:
        return {}
    has_pnl = any(isinstance(v, dict) and isinstance(v.get("pnl"), (int, float)) for v in scores.values())
    rows = []
    for w, v in scores.items():
        if not isinstance(v, dict):
            continue
        n = v.get("n") or 0
        usd = v.get("usd") or 0
        if not (n > 0 and usd / n >= _RANK_MIN_AVG_USD):        # 4-stellig-Filter (wie Dashboard)
            continue
        avg_clv = (v.get("clvSumPP") or 0) / n
        hit = (v.get("wins") or 0) / n
        if has_pnl:
            if not isinstance(v.get("pnl"), (int, float)) or n < _RANK_MIN_N_PNL:
                continue
            if not (avg_clv >= 0 and hit >= _RANK_FLOOR_HIT):   # Schärfe-Floor (P&L-Modus)
                continue
            rows.append((w, v["pnl"]))
        else:
            if n < _RANK_MIN_N_CLV:
                continue
            raw = avg_clv + (hit - 0.5) * _RANK_HITW
            rows.append((w, raw * (n / (n + _RANK_K))))
    rows.sort(key=lambda x: -x[1])
    return {str(w).lower(): i + 1 for i, (w, _) in enumerate(rows)}   # volle Rangliste; Anzeige/Gate cappen selbst


def _rank_badge(scores, wallet, top=_RANK_TOP):
    """Push-Zeile, wenn die Wallet in der Top-`top` der Sharp-Rangliste steht — sonst None."""
    if not wallet:
        return None
    r = _sharp_rank_map(scores).get(str(wallet).lower())
    if not r or r > top:
        return None
    medal = "🥇" if r == 1 else "🥈" if r == 2 else "🥉" if r == 3 else "🏅"
    return "%s <b>Top-%d-Wallet</b> · Rang #%d der Sharp-Rangliste" % (medal, top, r)


def _pub_in_top_n(scores, wallet, n=PUB_TOP_N):
    """Public-Gate (23.08.2026, Lucas): nur die Top-N der Sharp-Rangliste ins öffentliche Feed."""
    r = _sharp_rank_map(scores).get(str(wallet).lower()) if wallet else None
    return bool(r and r <= n)


def build_card(pos: dict, scores: dict, restock: bool, broad: dict = None, extra: int = 0,
               blocked=None) -> str:
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
    _tw = _rank_badge(scores, pos.get("wallet"))
    if _tw:
        lines.append(_tw)
    # 25.08.2026 (Lucas: „haben wir MLB nicht entfernt?"): weit nach oben, direkt unter den
    # Rang. Ohne diese Zeile liest sich der Push als Empfehlung fuer etwas, wofuer im Dashboard
    # bewusst kein Setzen-Button existiert.
    if bet_blocked(pos, blocked):
        lines.append("🚫 <b>Sportart aktuell nicht bespielbar</b> — im Papier-Depot klar negativ. "
                     "Kein Setzen-Button, kein Public-Post. Steht nur zur Beobachtung hier.")
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
    # 24.08.2026 (Lucas): steht eine andere Top-Wallet dagegen, gehoert das IN die Nachricht —
    # sonst liest sich der Push als Empfehlung, obwohl die Gegenseite genauso gut belegt ist.
    _cf = _conflicting_top_wallet(pos, broad, scores)
    if _cf:
        lines.append("⚔️ <b>Rang #%d haelt die Gegenseite</b> — %s (%s)"
                     % (_cf["rank"], _esc(_cf["side"]), _usd(_cf["usd"])))
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
        # 13.08.2026 (Lucas): belegt unterdurchschnittliche Wallet (belastbarer Record n>=min_tr, aber
        # < 50% Treffer) NICHT als reine Groessen-Karte pushen - Groesse ohne Koennen ist kein Signal
        # (eher Anti-Edge). "bewiesen scharf" (>=50%) und echte Unbekannte (n<min_tr) bleiben unberuehrt.
        _hit = ((_s.get("wins") or 0) / _n) if (_n and isinstance(_s, dict)) else None
        if _n >= min_tr and _hit is not None and _hit < 0.50:
            continue
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
    """Paarung „TeamA v TeamB" aus poly_money_broad_close.json (shares-Keys = Ausgänge). None sonst.
    16.08.2026 (Lucas): Prop-Märkte (Über/Unter, Ja/Nein) haben generische Outcomes statt Teams — sonst
    entsteht „Over v Under". Solche Outcomes rausfiltern (wie den Draw); echte Paarung aus dem BASIS-Event
    (Key ohne „-more-markets") ziehen. Kein erfasstes Basis-Event -> None (Post zeigt dann die Seite)."""
    def _gen(n):
        s = str(n).strip().lower()
        return (s.startswith("draw") or s.startswith("the draw") or s.startswith("unentschieden")
                or s in ("over", "under", "über", "unter", "yes", "no", "ja", "nein", "tie"))

    def _teams_of(kk):
        m = (broad or {}).get(kk) if isinstance(broad, dict) else None
        sh = (m or {}).get("shares") if isinstance(m, dict) else None
        names = list(sh.keys()) if isinstance(sh, dict) else []
        return [n for n in names if not _gen(n)]

    teams = _teams_of(key)
    if len(teams) < 2 and "-more-markets" in str(key):
        base = _teams_of(str(key).replace("-more-markets", ""))   # echte Teams aus dem Hauptmarkt
        if len(base) >= 2:
            teams = base
    return " v ".join(teams[:2]) if len(teams) >= 2 else None


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
    lines = [header, "", top, "<i>%s</i>" % _esc(sport)]
    _tw = _rank_badge(scores, pos.get("wallet"), top=PUB_TOP_N)
    if _tw:
        lines.append(_tw)
    # 04.09.2026: bei einem generischen Ausgang die LINIE nennen, nicht nur „Over".
    _label = side
    if str(side).strip().lower() in _PUB_GENERISCH:
        _lin = _linie_kurz(_markt_frage(key, broad))
        if _lin:
            _label = _lin
    lines += ["", "💰 <b>%s</b> auf <b>%s</b>" % (_usd(pos.get("usd") or 0), _esc(_label))]
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



# ── Public-Ledger ──────────────────────────────────────────────────────────────
# 02.09.2026 (Lucas: „Schaffst du irgendwie die Polymarket pushes auch auszuwerten die in diesen
# Channel kommen?"). Bis heute hielt poly_whale_public_seen.json nur einen Dedup-Stempel
# ({usd, ts}) — ohne Preis, ohne Seite als Feld, ohne Abrechnung. Rueckwirkend war deshalb bloss
# eine Trefferquote rekonstruierbar, kein ROI. Ab jetzt gilt hier dieselbe Regel wie bei Betfair:
# wer pusht, misst den Push. Der Ledger haelt den Preis FEST, zu dem ein Leser im Moment des
# Pushs haette einsteigen koennen (lastPrice; sonst firstPrice) — nicht den guenstigeren
# Whale-Einstieg, der oft Stunden aelter ist. poly_public_eval.py rechnet gegen den Slug-Sieger ab.
PUB_LEDGER_KEEP = 800


def _push_price(pos) -> float | None:
    """Der fuer einen LESER im Moment des Pushs erreichbare Preis. lastPrice ist der aktuelle Stand
    des Marktes, firstPrice der (aeltere, meist bessere) Einstieg der Wallet. Wir schreiben den
    teureren, ehrlichen der beiden — sonst misst der Ledger einen Preis, den niemand bekam."""
    for f in ("lastPrice", "firstPrice"):
        try:
            v = float(pos.get(f))
        except (TypeError, ValueError):
            continue
        if 0.0 < v < 1.0:
            return round(v, 4)
    return None


def _log_public_push(pkey, pos, scores, restock, ts) -> None:
    """Einen gesendeten Public-Push festhalten. Ein Eintrag je posKey (wallet|key|side) — derselbe
    Dedup-Schluessel wie poly_whale_public_seen.json, also kein Doppelzaehlen bei Aufstockung."""
    led = _load(PUB_LEDGER_FILE, [])
    if not isinstance(led, list):
        led = []
    if any(isinstance(e, dict) and e.get("k") == pkey for e in led):
        return
    rank = None
    try:
        rank = _sharp_rank_map(scores).get(pos.get("wallet"))
    except Exception:
        pass
    led.append({
        "k": pkey, "key": pos.get("key"), "side": pos.get("side"),
        "wallet": pos.get("wallet"), "league": pos.get("league"),
        "cat": sport_category(pos.get("league")),
        "usd": round(float(pos.get("usd") or 0), 2),
        "pushPrice": _push_price(pos),
        "whaleEntry": (round(float(pos["firstPrice"]), 4)
                       if isinstance(pos.get("firstPrice"), (int, float)) else None),
        "walletRank": rank, "restock": bool(restock),
        "sentAt": ts, "status": "pending",
    })
    try:
        _save(PUB_LEDGER_FILE, led[-PUB_LEDGER_KEEP:])
    except Exception as e:
        print("Public-Ledger-Schreibfehler:", e)


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


def _pub_min_odds_ok(pos) -> bool:
    """22.08.2026 (Lucas): Public-Whale nur bei sinnvoller Mindest-Quote. Ein Whale, der bei ~86c
    (Odds ~1.16) einsteigt, ist fuer den oeffentlichen Feed „recht wenig" Value. Gate auf den
    Einstieg (firstPrice) UND — falls vorhanden — den Jetzt-Preis (lastPrice): beide muessen Odds
    >= PUB_MIN_ODDS ergeben (Preis <= 1/odds). Aussenseiter (niedriger Preis, hohe Odds) bleiben drin."""
    max_price = (1.0 / PUB_MIN_ODDS) if PUB_MIN_ODDS > 0 else 1.0
    try:
        fp = float(pos.get("firstPrice"))
    except (TypeError, ValueError):
        return False
    if fp > max_price:
        return False
    lp = pos.get("lastPrice")
    if isinstance(lp, (int, float)) and lp > max_price:
        return False
    return True


# 04.09.2026 (Lucas' Zwei-Wochen-Bilanz: „12 Win, 2 lost — 2 Premier League lost").
# Unser Buch zaehlte 13:1, Lucas 12:2. Die eine Abweichung ist Leeds–Brentford am 30.08., und
# der Unterschied ist kein Zaehlfehler, sondern ein Fehler im PUSH:
#
#     💰 $41K auf Over        →  Leeds United FC v Brentford FC, Endstand 1:1
#
# „Over" WAS? Der Markt war `epl-lee-bre-2026-08-30-more-markets` — ein Totals-Markt, dessen Linie
# nirgends steht. Bei 1:1 gewinnt Over 1,5 und verliert Over 2,5. Lucas hat den Push als Verlust
# gebucht, unsere Aufloesung als Treffer, und BEIDE konnten es nicht wissen: in
# poly_money_broad_close.json haben alle 2000 Maerkte weder `title` noch `question` — die
# Marktfrage wird gar nicht erst mitgeschrieben. Von 230 „-more-markets" tragen 213 Over/Under.
#
# Ein Push, den der Leser nicht nachvollziehen kann, ist im oeffentlichen Kanal wertlos: er kann
# ihm nicht folgen und er kann ihn nicht nachpruefen. Und ein Ergebnis, das wir selbst nicht
# eindeutig zuordnen koennen, verschmutzt das Buch — es zaehlt als Treffer oder Fehlschlag, ohne
# dass jemand sagen kann, worauf.
#
# Deshalb: generische Ausgaenge (Over/Under/Yes/No) gehen nicht mehr in den Public-Kanal, solange
# die Linie nicht mitgeliefert wird. Im Trades-Kanal bleiben sie — dort entscheidet Lucas selbst
# und sieht den Markt-Link. Das ist bewusst die Sperre und nicht ein Warnhinweis: „$41K auf Over"
# mit Sternchen ist immer noch nicht spielbar.
_PUB_GENERISCH = {"over", "under", "über", "unter", "yes", "no", "ja", "nein", "tie",
                  "draw", "the draw", "unentschieden"}


def _markt_frage(key, broad):
    """Die Frage des Markts („Will there be over 2.5 goals…") aus poly_money_broad_close.json.
    04.09.2026: wird seit heute mitgeschrieben; fuer alles Aeltere fehlt sie. REIN/testbar."""
    m = (broad or {}).get(key) if isinstance(broad, dict) else None
    f = (m or {}).get("frage") if isinstance(m, dict) else None
    return str(f).strip() if isinstance(f, str) and f.strip() else None


def _linie_kurz(frage):
    """Aus der Marktfrage die knappe Linie fuers Push-Label: „Over 2.5 goals". REIN/testbar.

    Bewusst konservativ: nur wenn eine Zahl DIREKT an Over/Under haengt, wird gekuerzt. Sonst
    steht die ganze Frage da — lieber laenger als ungefaehr, weil genau die Ungefaehrheit den
    Leeds-Brentford-Fall verursacht hat."""
    if not frage:
        return None
    m = _re.search(r"\b(over|under|ueber|über)\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Zäöü]+)?", frage, _re.I)
    if not m:
        return frage
    wort = (m.group(3) or "").strip()
    return ("%s %s%s" % (m.group(1).title(), m.group(2).replace(",", "."),
                         (" " + wort) if wort else "")).strip()


def _pub_seite_benennbar(pos, broad=None) -> bool:
    """Kann der Leser diesem Push folgen? REIN/testbar.

    Ein generischer Ausgang („Over") ist erlaubt, SOBALD die Marktfrage die Linie nennt — dann
    steht im Push „Over 2.5 goals" und der Tipp ist nachvollziehbar und nachpruefbar. Ohne
    Frage bleibt er draussen: „$41K auf Over" ist kein Tipp, sondern ein Raetsel."""
    seite = str(pos.get("side") or "").strip().lower()
    if not seite:
        return False
    if seite in _PUB_GENERISCH:
        return bool(_markt_frage(pos.get("key"), broad))
    return True


def _pub_keep(pos, scores):
    """13.08.2026 (Lucas): Public NUR bewiesen scharfe Wallets — Record n>=PUB_MIN_TR, >=PUB_MIN_HITRATE
    Treffer, kein bestaetigter Verlierer (_is_smart). Grosse-aber-unbewiesene Wallets (frueher ab
    PUB_MIN_USD_NOREC ohne Record) bleiben jetzt im Trades-Channel — empirisch zeigen unvalidierte
    Grosswallets keine Edge (sharp-CLV -1.1pp ueber 1094 Signale). REIN/testbar."""
    s = scores.get(pos.get("wallet")) if isinstance(scores, dict) else None
    return _is_smart(s, PUB_MIN_TR, PUB_MIN_HITRATE)


def _conflicting_top_wallet(pos, broad, scores, top=None):
    """Sitzt eine ANDERE Top-N-Wallet auf einer anderen Seite desselben Markts? REIN/testbar.

    24.08.2026 (Lucas' INOX-Fall): zwei bewiesene Wallets auf Gegenseiten heben sich als Signal
    weitgehend auf — dem einen zu folgen ist dort ein Muenzwurf. `_contested_market` fing das
    nicht: es misst DOLLAR (>=$100K je Seite) und laeuft nur im Public-Kanal. Hier zaehlt der
    RANG, damit auch ein $7K-Gegeneinstieg einer Top-Wallet auffaellt.

    Gibt die bestplatzierte Gegen-Wallet zurueck: {"rank", "side", "usd", "wallet"} oder None.
    """
    top = top or CONFLICT_TOP_N
    key, side, me = pos.get("key"), pos.get("side"), str(pos.get("wallet") or "").lower()
    if not (key and side):
        return None
    m = (broad or {}).get(key) if isinstance(broad, dict) else None
    if not isinstance(m, dict):
        return None
    ranks = _sharp_rank_map(scores)
    best = None
    for w in (m.get("whales") or []):
        if not isinstance(w, dict):
            continue
        w_side, w_wallet = w.get("side"), str(w.get("wallet") or "").lower()
        if not w_side or w_side == side or not w_wallet or w_wallet == me:
            continue
        r = ranks.get(w_wallet)
        if not r or r > top:
            continue
        if best is None or r < best["rank"]:
            best = {"rank": r, "side": w_side, "usd": float(w.get("usd") or 0), "wallet": w_wallet}
    return best


def _contested_market(key, broad, min_usd=CONTEST_MIN_USD):
    """12.08.2026 (Lucas): „Gegenseiten-Krieg" — hat EIN Markt Gross-Einstiege (>= min_usd) auf MEHR
    ALS EINER Seite, ist er umkaempft und taugt NICHT als Public-Whale-Signal (zwei widerspruechliche
    Posts zum selben Spiel). Prueft die echte Markt-Geldverteilung (broad = poly_money_broad_close),
    faengt so auch die Gegenseite, die erst in einem spaeteren Scan gross wurde. REIN/testbar."""
    m = (broad or {}).get(key) if isinstance(broad, dict) else None
    if not isinstance(m, dict):
        return False
    big_sides = set()
    for w in (m.get("whales") or []):
        if isinstance(w, dict) and float(w.get("usd") or 0) >= min_usd and w.get("side"):
            big_sides.add(w.get("side"))
    return len(big_sides) >= 2


def main():
    print("=== poly_whale_watch.py ===")
    track = _load(TRACK_FILE, {})
    if not track:
        print("  ℹ️  Keine poly_wallet_track.json — nichts zu tun."); return
    scores = track.get("scores") or {}
    seen   = _load(SEEN_FILE, {})
    now    = datetime.now(timezone.utc)

    broad = _load(BROAD_FILE, {})   # Matchup/Anpfiff/Preis-Kontext für die Trades-Cards
    _blocked = blocked_cats(_load(SHORTLIST_FILE, {}))
    # (01.08.2026, Lucas: 1a) Trades-Channel bekommt denselben Sanity-Filter wie Public:
    # nur Sport + Preis 3–97¢ → kein @100¢-schon-entschieden, kein Politik/Krypto-Müll.
    cand = [c for c in select(track, seen, now, sharp_floor=MIN_USD_SHARP) if _pub_ok(c[1])]
    cand, _extra = _dedup_by_wallet(cand, MAX_PER_WALLET)   # je Wallet max MAX_PER_WALLET Karten/Lauf
    print(f"  {len(cand)} alertwürdige Position(en) (Sport + 3–97¢, ≥ {_usd(MIN_USD_TRACKED)} mit / {_usd(MIN_USD_UNTRACKED)} ohne Record, frisch)")

    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sent = 0
    for pkey, pos, restock in cand[:MAX_ALERTS]:
        card = build_card(pos, scores, restock, broad, extra=_extra.get(pkey, 0), blocked=_blocked)
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
    pub_cand = [c for c in pub_cand if _pub_in_top_n(scores, c[1].get("wallet"))]   # 23.08.2026 (Lucas): Public = NUR Top-N der Sharp-Rangliste
    # 25.08.2026 (Lucas): der oeffentliche Kanal ist das Produkt — was wir selbst nicht setzen
    # wuerden, vertreten wir dort auch nicht. Im Trades-Kanal steht stattdessen die Hinweiszeile.
    _pre_blk = len(pub_cand)
    pub_cand = [c for c in pub_cand if not bet_blocked(c[1], _blocked)]
    if _pre_blk != len(pub_cand):
        print(f"  \U0001f6ab {_pre_blk - len(pub_cand)} Post(s) unterdrueckt — gesperrte(r) Sportart ({', '.join(_blocked)})")
    pub_cand = [c for c in pub_cand if _pub_min_odds_ok(c[1])]   # 22.08.2026 (Lucas): Public-Mindest-Quote (>=1.30) — kurze Favoriten raus
    _pre_gen = len(pub_cand)
    pub_cand = [c for c in pub_cand if _pub_seite_benennbar(c[1], broad)]   # 04.09.2026: „auf Over" ohne Linie ist kein Tipp
    if _pre_gen != len(pub_cand):
        print(f"  \U0001f4ad {_pre_gen - len(pub_cand)} Post(s) unterdrueckt — generischer Ausgang (Over/Under/Yes/No) ohne Marktfrage")
    _pre_contest = len(pub_cand)
    pub_cand = [c for c in pub_cand if not _contested_market(c[1].get("key"), broad)]   # 12.08.2026 (Lucas): Gegenseiten-Krieg raus — umkaempfte Spiele gar nicht posten
    if _pre_contest != len(pub_cand):
        print(f"  \U0001f91d {_pre_contest - len(pub_cand)} umkaempfte(s) Spiel(e) unterdrueckt (Gross-Geld auf beiden Seiten)")
    # 24.08.2026 (Lucas, INOX-Fall): dasselbe nach RANG statt Dollar. Zwei sich widersprechende
    # Empfehlungen kurz nacheinander sind im oeffentlichen Kanal das Schlechteste — im Trades-
    # Kanal steht stattdessen die Warnzeile, dort entscheidet Lucas selbst.
    _pre_conf = len(pub_cand)
    pub_cand = [c for c in pub_cand if not _conflicting_top_wallet(c[1], broad, scores)]
    if _pre_conf != len(pub_cand):
        print(f"  \u2694\ufe0f  {_pre_conf - len(pub_cand)} Post(s) unterdrueckt — eine andere Top-Wallet haelt die Gegenseite")
    pub_sent = 0
    for pkey, pos, restock in pub_cand[:MAX_ALERTS]:
        if _tg_public(build_public_card(pos, scores, restock, broad)):
            pub_sent += 1
            pub_seen[pkey] = {"usd": float(pos.get("usd") or 0), "ts": now_iso}
            _log_public_push(pkey, pos, scores, restock, now_iso)
    _save(PUB_SEEN_FILE, pub_seen)
    print(f"  🐋 Public-Whale: {len(pub_cand)} Kandidat(en), {pub_sent} gesendet.")


if __name__ == "__main__":
    main()
