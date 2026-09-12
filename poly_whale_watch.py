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
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
import sharp_gate as SG   # 29.08.2026: DIE Sharp-Definition, geteilt mit Live-Watch + Frontend
import push_deckel as PD  # 12.09.2026: Nachrichten-Deckel je Lauf

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
WNORM_FILE    = BASE / "poly_wallet_norm.json"   # 05.09.2026: was ist fuer DIESES Konto normal?
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
    ("US-Sport",   r"basketball|nba|nfl|americanfootball|baseball|mlb|icehockey|hockey|nhl|wnba|ncaa|\bcfb\b"),
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
        # 08.09.2026: `pro-?league` traf „SAUDI-PROFESSIONAL-LEAGUE" nicht (nach „pro" kommt
        # „fessional"). 4 offene Whale-Positionen liefen deshalb auf „Sonstige" und fielen
        # aus beiden Kanaelen. Spiegel in poly-wallets.js mitgeaendert.
        r"super-?lig|pro(?:fessional)?-?league|\blal\b", x) else "Sonstige"


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


# 08.09.2026 (Lucas: „schau dir die ganzen Whales an, ob das alles sauber umgesetzt ist").
# Hier standen ZWEI Liga→Sport-Zuordnungen in derselben Datei: `sport_category()` (Zeile 146,
# volle Regex, kennt ligue/serie/eredivisie/elitese/championship/…) und `_sport()` (arm:
# „SOCCER…", „LIGA", „MLS", „EPL", „UCL"). Gegatet hat die ARME — `_pub_ok()` wirft alles raus,
# was bei ihr auf dem 🎯-Default landet, und `_pub_ok` filtert **beide** Kanäle, nicht nur Public.
#
# Gemessen an den 617 offenen Positionen von heute: 75 (12,2 %) landeten auf 🎯, davon **55
# echter Fußball** — Ligue 1 (13), EFL Championship (14), Eliteserien (8), Ligue 2 (7),
# Brazil Serie A (5), Allsvenskan (4), Scottish Premiership (4). Der Fingerabdruck steht in den
# Push-Zahlen: `epl` 54 Pushes, `lal` 33, `bun` 9 — aber `fl1` 2, `elc` 5, `nor` 1, `bra`/`sco`/
# `all`/`fl2` **0**. Und weil jeder ANDERE Public-Filter eine Unterdrückungszeile druckt
# (🚫 💭 🤝 ⚔️) und dieser nicht, war der Verlust im Log unsichtbar.
#
# ⭐ Zwei Zuordnungen für dieselbe Frage sind eine zu viel. `sport_category()` ist die Quelle
# (sie spiegelt `_pwSportCategory` im Dashboard und liefert dieselben Kategorien, die auch die
# Sperrliste benutzt); `_sport()` haengt nur noch das Emoji dran. Der gestempelte `sport` aus dem
# Capture hat Vorrang — 601 der 617 Positionen tragen ihn bereits.
_CAT_EMOJI = {
    "Fußball": "⚽", "E-Sport": "🎮", "Tennis": "🎾", "US-Sport": "🏀",
    "Kampfsport": "🥊", "Golf": "⛳", "Motorsport": "🏎️", "Cricket": "🏏",
}


def _sport(league: str, sport=None):
    """(Emoji, Sportname) für die Karte. 🎯 heisst „keine Sportart erkannt" und ist das
    einzige, was `_pub_ok` sperrt — deshalb darf hier nichts landen, was `sport_category`
    benennen kann. REIN."""
    x = str(league or "").upper()
    if x in _SPORT:
        return _SPORT[x]
    cat = sport_category(league, sport)
    if cat in _CAT_EMOJI:
        return (_CAT_EMOJI[cat], cat)
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


def _lifetime(s) -> str:
    """Die Lebensbilanz der Wallet auf Polymarket, als Zusatz — nie als Rang.

    10.09.2026 (Lucas: „Trades-Channel lassen wir alles wie es ist, da will ich die ganze Info
    haben die sonst noch da steht“). Die Zeile stand bis heute NUR in der Public-Karte
    (`_pub_wallet_line`). Mit deren Kürzung wäre sie ersatzlos verschwunden — obwohl der
    Trades-Channel genau der Kanal ist, in dem die volle Auskunft bleiben soll. Also wandert sie
    hierher statt weg.

    ⚠️ `pnl` ist die LEBENSBILANZ über ALLE Polymarket-Märkte (Wahlen, Krypto, Sport) und misst
    deshalb NICHT die Sport-Qualität, nach der `sharp_gate` sortiert — s. sharp_gate.py. Sie steht
    hier bewusst am Ende der Zeile und ohne eigenes Urteil, damit sie niemand als Rang liest.
    Fehlt sie (Runner hat sie noch nicht gezogen), rendert sie als nichts — kein „?“, kein „0“.
    """
    pnl = s.get("pnl") if isinstance(s, dict) else None
    if not isinstance(pnl, (int, float)):
        return ""
    return " · %s%s lifetime" % ("+" if pnl >= 0 else "−", _usd(abs(pnl)))


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
        return (f"Wallet {link} · ✅ <b>bewiesene Wallet</b> "
                f"({wins}/{n} richtig, {round(wins/n*100)}% · {_clv:+.1f}pp CLV){_lifetime(s)}")
    # 06.08.2026 (Lucas: gleiche Loesung wie Public): rohe Bilanz ab n>=MIN_TR neutral zeigen, statt sie
    # hinter „im Aufbau" zu verstecken. Nur wirklich duenn (n<MIN_TR) oder Verlierer bleibt „im Aufbau".
    if isinstance(s, dict) and n >= MIN_TR and not _is_confirmed_loser(s):
        wins = s.get("wins") or 0
        return f"Wallet {link} · 📊 <b>Bilanz</b> {wins}/{n} ({round(wins/n*100)}%){_lifetime(s)}"
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


# ── Groesse relativ statt absolut (05.09.2026) ────────────────────────────────
# Lucas: „250.000 ist fuer mich ein Vermoegen, fuer den wahrscheinlich ein normaler Bet."
# Die Schwelle war ein fester Dollar-Betrag. 9 Wallets haben ein MEDIAN-Ticket ueber
# $50.000 — bei denen loest per Konstruktion jede zweite Position aus. Zwei relative
# Masse ersetzen das Urteil; beide duerfen fehlen, und dann steht dort nichts.

# Ab wann ein Anteil am Marktvolumen gross heisst. Gemessen ueber 3.000 Positionen:
# Median 8 %, p75 16 %, p90 29 %. 25 % liegt also knapp unter dem obersten Zehntel.
MARKT_ANTEIL_GROSS = float(os.environ.get("WHALE_MARKT_ANTEIL") or 0.25)
# Ab welchem Vielfachen des eigenen Median-Tickets eine Position fuer DIESES Konto gross ist.
TICKET_FAKTOR_GROSS = float(os.environ.get("WHALE_TICKET_FAKTOR") or 2.0)

_WNORM_CACHE = None


def _wallet_norm():
    """poly_wallet_norm.json, einmal geladen. Fehlt sie, gibt es keine Vergleiche — und dann
    steht auf der Karte nichts statt einer erfundenen Normalitaet."""
    global _WNORM_CACHE
    if _WNORM_CACHE is None:
        _WNORM_CACHE = (_load(WNORM_FILE, {}) or {}).get("wallets") or {}
    return _WNORM_CACHE


def markt_anteil(pos: dict, broad: dict):
    """Anteil dieser Position am Volumen ihres Markts. None, wenn nicht bestimmbar.

    Der Nenner ist nicht immer derselbe Markt wie der Zaehler — poly_money_broad.py haelt das
    im Kopf fest („Event $1.24M, Markt ~$150K"). Gemessen betrifft das 21 von 8.509 Positionen
    (0,2 %), aber wo der Einsatz groesser ist als das gesamte Marktvolumen, widerspricht der
    Nenner dem Zaehler — dann gibt es KEINE Zahl, nicht 100 %."""
    usd = pos.get("usd")
    m = (broad or {}).get(pos.get("key")) or {}
    total = m.get("totalUsd")
    if (not isinstance(usd, (int, float)) or isinstance(usd, bool)
            or not isinstance(total, (int, float)) or isinstance(total, bool)):
        return None
    if usd <= 0 or total <= 0 or usd > total:
        return None
    return usd / total


def seiten_anteil(pos: dict, broad: dict):
    """Anteil dieser Position am Geld der EIGENEN SEITE. None, wenn nicht bestimmbar. REIN.

    🔴 11.09.2026 — der Grund, warum es diese Funktion neben `markt_anteil` gibt.

    Lucas fragte, ob bei Polymarket viel Geld auf einer Seite die Quote zwangslaeufig runterdrueckt
    (anders als beim Buchmacher, wo beides unabhaengig ist). Beim Nachrechnen kam heraus: ja, aber
    zu einem guten Teil ist es UNSERE MESSUNG.

    Bei Polymarket ist `usd = Anteile × Preis`. Wer dieselbe Stueckzahl auf einen Favoriten @0,87
    haelt statt auf einen Aussenseiter @0,13, hat rechnerisch das 6,7-FACHE an „Dominanz" — bei
    identischem Contract-Bestand. Gemessen an 159 Positionen fiel die Median-Quote monoton mit dem
    Marktanteil (1,96 unter 10 % → 1,16 ab 60 %), und 80 % der Positionen ab 40 % Anteil lagen
    unter Quote 1,35. Das Band fand also fast nur Favoriten, und der Quotenboden warf sie wieder
    raus — zwei Regeln, die gegeneinander arbeiteten, beide aus demselben Messfehler.

    Hier kuerzt sich der Preis heraus: Zaehler und Nenner sind beide „Anteile × derselbe Preis".
    Uebrig bleibt der reine Stueck-Anteil an der offenen Position dieser Seite. Gemessen
    verschwindet der Drall vollstaendig (Median-Quote 2,00 / 2,15 / 1,98 / 1,74 ueber die Baender,
    kein Trend), es gibt 43 statt 5 Kandidaten, und 77 % davon liegen ueber 1,35 statt 20 %.

    ⚠️ `markt_anteil` bleibt unveraendert und wird weiter benutzt. Es beantwortet eine ANDERE
    Frage („wie gross ist diese Position gemessen am ganzen Markt") und steht so auf den
    Whale-Karten. Beide durch denselben Namen zu ersetzen haette eine bestehende Anzeige still
    umgedeutet.
    """
    usd = pos.get("usd")
    m = (broad or {}).get(pos.get("key")) if isinstance(broad, dict) else None
    seite = ((m or {}).get("shares") or {}).get(pos.get("side")) if isinstance(m, dict) else None
    if (not isinstance(usd, (int, float)) or isinstance(usd, bool)
            or not isinstance(seite, (int, float)) or isinstance(seite, bool)):
        return None
    if usd <= 0 or seite <= 0 or usd > seite * 1.02:
        # Mehr als die eigene Seite zu halten ist rechnerisch unmoeglich. 2 % Toleranz, weil
        # Zaehler und Nenner aus zwei Abrufen stammen koennen; darueber widerspricht der Nenner
        # dem Zaehler, und dann gibt es KEINE Zahl — nicht 100 %.
        return None
    return min(usd / seite, 1.0)


def ticket_vergleich(pos: dict):
    """Wie gross ist die Position fuer DIESES Konto? None = zu wenig ueber das Konto bekannt.

    „Unbekannt" ist ausdruecklich nicht „normal": ein Konto, von dem wir die erste Position
    sehen, hat keine Normalgroesse, und die Karte darf keine behaupten."""
    from poly_wallet_norm import ticket_vergleich as _tv
    wal = str(pos.get("wallet") or "").lower()
    return _tv(pos.get("usd"), _wallet_norm().get(wal))


def _groessen_zeilen(pos: dict, broad: dict):
    """Die Zeilen, die die Groesse einordnen. Leer, wenn nichts bekannt ist."""
    out = []
    tv = ticket_vergleich(pos)
    if tv:
        if tv["faktor"] >= TICKET_FAKTOR_GROSS:
            out.append("📐 <b>%.1f×</b> das übliche Ticket dieses Kontos (Median %s aus %d Positionen)"
                       % (tv["faktor"], _usd(tv["median"]), tv["n"]))
        else:
            out.append("📐 Für dieses Konto <b>Normalgröße</b> — %.1f× sein übliches Ticket "
                       "(Median %s aus %d Positionen)" % (tv["faktor"], _usd(tv["median"]), tv["n"]))
    a = markt_anteil(pos, broad)
    if a is not None:
        out.append("📊 <b>%d %%</b> des Marktvolumens%s" % (round(a * 100),
                   " — das ist viel" if a >= MARKT_ANTEIL_GROSS else ""))
    return out


def _ist_gross(pos: dict, broad: dict) -> bool:
    """Gross heisst: gross RELATIV — zum eigenen Ticket oder zum Markt. Ist beides unbekannt,
    faellt es auf die alte absolute Schwelle zurueck, und das ist dann eine Aussage ueber den
    Dollar-Betrag, nicht ueber Auffaelligkeit."""
    tv = ticket_vergleich(pos)
    if tv:
        return tv["faktor"] >= TICKET_FAKTOR_GROSS
    a = markt_anteil(pos, broad)
    if a is not None:
        return a >= MARKT_ANTEIL_GROSS
    return (pos.get("usd") or 0) >= MIN_USD_UNTRACKED


def build_card(pos: dict, scores: dict, restock: bool, broad: dict = None, extra: int = 0,
               blocked=None) -> str:
    """Trades-Push (01.08.2026, Lucas: „entscheidungsreif") — Matchup, Anpfiff, Einstieg→Jetzt-Preis,
    Wallet-Qualität, Markt-Link. Ein Push = eine fertige Wett-Entscheidung."""
    emoji, sport = _sport(pos.get("league"), pos.get("sport"))
    side  = pos.get("side") or "?"
    key   = pos.get("key")
    usd   = pos.get("usd") or 0
    matchup = _matchup(key, broad)
    ko      = _kickoff_txt(key, broad)
    # 05.08.2026 (Lucas): Badge sagt WARUM die Karte kommt - Wal=grosses Geld, Feuer=bewiesen scharf,
    # beides=staerkstes Signal. Ein kleiner scharfer Einstieg ist kein 'Grosser' Einstieg.
    _sm  = _is_smart(scores.get(pos.get("wallet")) if isinstance(scores, dict) else None)
    _big = _ist_gross(pos, broad)
    if restock:
        header = "🐋🔥 <b>Whale stockt auf · scharf</b>" if _sm else "🐋 <b>Whale stockt auf</b>"
    elif _big and _sm:
        header = "🐋🔥 <b>Großer Einstieg · bewiesen scharf</b>"
    elif _big:
        header = "🐋 <b>Großer Whale-Einstieg</b>"
    elif _sm:
        header = "🔥 <b>Scharfe Wallet frisch drin</b>"
    else:
        # Weder relativ gross noch bewiesen scharf: dann heisst es auch nicht „Großer".
        header = "🐋 <b>Whale-Einstieg</b>"
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
    # 05.09.2026: dieselbe Beschriftung wie im Public-Kanal — hier stand vorher das nackte
    # „Over", also die Seite ohne Linie. Zwei Kanaele, ein Label.
    lines.append("💰 <b>%s</b> auf <b>%s</b>"
                 % (_usd(usd), _esc(ausgang_label(side, _markt_frage(key, broad)) or side)))
    lines += _groessen_zeilen(pos, broad)
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
    if len(teams) < 2:
        base = _basis_key(key)
        if base:
            b = _teams_of(base)          # echte Teams aus dem Hauptmarkt
            if len(b) >= 2:
                teams = b
    return " v ".join(teams[:2]) if len(teams) >= 2 else None


# 🔴 11.09.2026 (Lucas: „denke hier sind corner gemeint, bitte anpassen").
#
# Er hat eine Dominanz-Karte geschickt und nicht erkennen koennen, auf WAS gesetzt wurde. Bei der
# konkreten Karte war es zwar der Matchsieger — aber die Fehlerklasse dahinter ist echt und
# haesslich: bei einem Ecken-Markt rendert die Karte als Ueberschrift schlicht
#
#     ⚽ Fussball
#     Over                          ← das soll die Paarung sein
#     💰 $21.4K auf Over 10.5
#
# Die Paarung fehlt GANZ, und dass es Ecken sind, steht nirgends. Zwei Ursachen:
#
#  1. `_matchup` fiel nur bei „-more-markets" auf den Basis-Markt zurueck. Gemessen gibt es acht
#     Suffixe (more-markets 354, exact-score 288, halftime-result 32, total-corners 30,
#     first-to-score 11, player-props 6, …) — fuer die anderen sieben wurde nie nachgeschlagen,
#     obwohl der Basis-Markt bei 612 von 726 Sub-Maerkten erfasst ist. Eine Liste, die nur ihren
#     ersten Fall kennt.
#  2. Die Marktfrage („… O/U 10.5 Total Corners") lag vor und wurde auf der Karte nicht gezeigt.
_SUB_SUFFIXE = ("more-markets", "exact-score", "halftime-result", "total-corners",
                "first-to-score", "player-props", "first-half-exact-score",
                "first-five-winner")


def _basis_key(key):
    """Der Haupt-Markt zu einem Sub-Markt — oder None. REIN.

    Geschnitten wird am DATUM, nicht an einer Suffix-Liste: `…-2026-09-04-total-corners` →
    `…-2026-09-04`. Die Liste oben dient nur der Beschriftung; als Schnittregel waere sie eine
    Aufzaehlung, die beim naechsten neuen Markttyp still danebenliegt — genau die Fehlerklasse,
    die diesen Eintrag ausgeloest hat.
    """
    m = _re.match(r"^(.*-\d{4}-\d{2}-\d{2})-(.+)$", str(key or ""))
    return m.group(1) if m else None


def sub_markt_art(key):
    """Klartext fuer den Markttyp eines Sub-Markts — oder None beim Hauptmarkt. REIN."""
    m = _re.match(r"^.*-\d{4}-\d{2}-\d{2}-(.+)$", str(key or ""))
    if not m:
        return None
    suf = m.group(1)
    return {"total-corners": "Ecken", "exact-score": "Exaktes Ergebnis",
            "halftime-result": "Halbzeit", "first-to-score": "Erstes Tor",
            "player-props": "Spieler-Wette", "first-half-exact-score": "Exaktes Ergebnis (HZ)",
            "first-five-winner": "Erste 5 Innings",
            "more-markets": "Nebenmarkt"}.get(suf, suf.replace("-", " "))


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
    if _sport(pos.get("league"), pos.get("sport"))[0] == "🎯":
        return False
    try:
        p = float(pos.get("firstPrice"))
    except (TypeError, ValueError):
        return False
    return 0.03 <= p <= 0.97


def _quote(preis):
    """Cent-Preis -> Dezimalquote. 71¢ = 1/0,71 = @1.41. REIN.

    10.09.2026 (Lucas: „können wir bitte beim Einstieg Quoten statt % ?"). Der Preis auf
    Polymarket IST die Wahrscheinlichkeit — die Quote ist ihr Kehrwert und die Sprache, in der
    der Rest des Kanals spricht (Betfair, Cards, alles @x.xx). Zwei Einheiten fuer dieselbe Sache
    in einem Channel kosten bei jedem Blick eine Umrechnung.
    """
    try:
        p = float(preis)
    except (TypeError, ValueError):
        return None
    if not (0.0 < p < 1.0):
        return None      # 0 oder 1 hat keine Quote — und 1,00 waere gelogen
    return "@%.2f" % (1.0 / p)


def _pub_einstieg(pos: dict):
    """„Einstieg @1.41" — oder None, wenn es keinen brauchbaren Preis gibt."""
    entry = pos.get("entryPrice")
    if not isinstance(entry, (int, float)):
        entry = pos.get("firstPrice")
    q = _quote(entry)
    return ("Einstieg %s" % q) if q else None


def _pub_rang_zeile(scores, wallet, top=PUB_TOP_N):
    """„🏅 Rang #9 Sharp Bettor hat gewettet" — kurz, ohne Rangliste-Jargon."""
    if not wallet:
        return None
    r = _sharp_rank_map(scores).get(str(wallet).lower())
    if not r or r > top:
        return None
    medal = "🥇" if r == 1 else "🥈" if r == 2 else "🥉" if r == 3 else "🏅"
    return "%s <b>Rang #%d Sharp Bettor</b> hat gewettet" % (medal, r)


def build_public_card(pos: dict, scores: dict, restock: bool, broad: dict) -> str:
    """Öffentliches Format — 10.09.2026 von Lucas neu geschnitten.

    Vorher standen hier sieben Zeilen: Ticket-Median des Kontos, Preis-Bewegung mit Pfeil,
    Außenseiter-Hinweis, die volle Wallet-Bilanz (n/Treffer/CLV/Lifetime) und der Markt-Link.
    Das ist die TRADES-Sicht — dort bleibt sie auch unverändert, weil Lucas dort selbst
    entscheidet. Der öffentliche Kanal bekommt die vier Dinge, die eine fremde Person braucht:
    welches Spiel, wer hat gesetzt, wie viel, zu welchem Preis.

    ⚠️ Was hier NICHT mehr steht, steht auch nirgends verkürzt: eine Wallet-Bilanz halb zu
    zeigen wäre schlechter als sie wegzulassen. Weggelassen wird sie ganz.
    """
    emoji, sport = _sport(pos.get("league"), pos.get("sport"))
    side = pos.get("side") or "?"
    key = pos.get("key")
    matchup = _matchup(key, broad)
    ko = _kickoff_txt(key, broad)
    header = "🐋 <b>Polymarket Whale — stockt auf</b>" if restock else "🐋 <b>Polymarket Whale</b>"

    # Sportart zuerst, dann das Spiel: die Sportart ist der Filter, mit dem ein Leser entscheidet,
    # ob ihn die Zeile ueberhaupt angeht.
    zeile_spiel = "%s <b>%s</b>" % (emoji, _esc(matchup or side))
    if ko:
        zeile_spiel += " · %s" % ko
    lines = [header, "", "<i>%s</i>" % _esc(sport), zeile_spiel]
    _r = _pub_rang_zeile(scores, pos.get("wallet"))
    if _r:
        lines.append(_r)

    _label = ausgang_label(side, _markt_frage(key, broad)) or side
    lines += ["", "💰 <b>%s</b> auf <b>%s</b>" % (_usd(pos.get("usd") or 0), _esc(_label))]

    # Einordnung: Marktanteil und Einstieg. Beide duerfen fehlen — dann steht dort nichts,
    # keine Null und kein Platzhalter.
    _unten = []
    a = markt_anteil(pos, broad)
    if a is not None:
        _unten.append("📊 <b>%d %%</b> des Marktvolumens" % round(a * 100))
    _e = _pub_einstieg(pos)
    if _e:
        _unten.append(_e)
    if _unten:
        lines += [""] + _unten

    # 10.09.2026 (Lucas: „bitte wieder den Markt rein, das hab ich vergessen … ist
    # userfreundlicher"). Beim Kuerzen der Karte heute frueh ist der Markt-Link mit rausgeflogen.
    # Er gehoert zurueck, und zwar aus einem Grund, der die ganze Kuerzung ueberlebt: alles
    # andere auf der Karte ist eine BEHAUPTUNG von uns — der Rang, der Marktanteil, die Quote.
    # Der Link ist das Einzige, womit ein fremder Leser sie nachpruefen kann. Eine Karte, die
    # Zahlen nennt und den Weg zur Quelle weglaesst, verlangt Vertrauen, statt es zu verdienen.
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


# ══════════════════════════════════════════════════════════════════════════════════════════
#  MARKTDOMINANZ — das Band UNTERHALB der Whale-Schwelle (11.09.2026)
# ══════════════════════════════════════════════════════════════════════════════════════════
# Lucas: „ob wir da eine Nische finden koennten — Wallets, die nur $5.000 spielen, aber das sind
# dann 80 % vom ganzen Turnier-Markt. Weniger Geld im Nennwert, aber vom Markt deckt es 60, 70 %
# ab. Ob da die Trefferquote hoch ist."
#
# GEMESSEN, bevor gebaut wurde — und die Messung sagt zweierlei:
#
#   1. Die Richtung stimmt. Von 36 abgerechneten Public-Whale-Pushs, deren Marktvolumen sich
#      nachtraeglich rekonstruieren liess:
#          Anteil < 15 %   n=21   Treffer 57,1 %   (UG 39,6 %)   Ø Markt $500.830
#          Anteil 15-30 %  n=11   Treffer 81,8 %   (UG 57,3 %)   Ø Markt $151.446
#          Anteil > 30 %   n= 4   Treffer 75,0 %   (UG 35,6 %)   Ø Markt  $97.201
#      Kleiner Markt mit spuerbarem Anteil trifft besser als grosser Markt mit Streuung.
#
#   2. Lucas' eigentlicher Fall kommt darin GAR NICHT VOR. Die Public-Schwelle verlangt $25.000;
#      fuer 60 % Anteil braeuchte ein $25.000-Einsatz einen Markt unter $42.000. Pushs in
#      Maerkten <= $60.000: **0 von 36**. Der Dollar-Boden und ein hoher Anteil schliessen sich
#      fast aus — hoher Anteil heisst kleiner Markt, kleiner Markt heisst wenig absolutes Geld.
#      Wir finden die Nische nicht, weil wir sie herausfiltern.
#
# Deshalb ein eigenes Band mit eigener Schwelle, eigenem Buch und eigenem Kanal-Platz. Es geht in
# den TRADES-Kanal, nicht in den Public — es ist eine BEOBACHTUNG, keine Empfehlung, und das muss
# die Karte auch sagen. Ob es traegt, weiss in ein paar Wochen das Buch.
DOM_MIN_USD   = float(os.environ.get("WHALE_DOM_MIN_USD")   or 3000)    # Lucas: „ab dreitausend Dollar klingt okay"
DOM_MIN_SHARE = float(os.environ.get("WHALE_DOM_MIN_SHARE") or 0.40)    # Lucas: „mindestens Anteil groesser vierzig Prozent"
DOM_MAX_ALERTS = int(os.environ.get("WHALE_DOM_MAX") or 5)
DOM_LEDGER_FILE = BASE / "poly_dominanz_ledger.json"
DOM_SEEN_FILE   = BASE / "poly_dominanz_seen.json"
DOM_LEDGER_KEEP = 800
# ⚠️ Ein winziger Markt macht jeden Einsatz zur Dominanz. „$300 im Markt und ich habe 100 %"
# wollte Lucas ausdruecklich NICHT finden. Der Boden steht deshalb am MARKT, nicht nur am Einsatz.
#
# 🔴 KORREKTUR 11.09.2026: dieser Boden stand auf 6000 und konnte NIE greifen. `poly_money_broad.py`
# nimmt mit `MIN_VOL_USD = 7500` ohnehin keinen kleineren Markt in die Close-Datei auf — gemessen:
# 0 von 2.928 Zeilen unter $6.000, der kleinste Markt ueberhaupt $7.504. Der Boden war Deko: er
# stand im Code, im Backlog und in einem gruenen Test, und hat in der Praxis nie eine Zeile
# abgelehnt. Er steht jetzt auf dem Wert, der TATSAECHLICH gilt, und seine Aufgabe hat sich
# geaendert: er ist eine STOLPERSCHWELLE. Senkt jemand oben `MIN_VOL_USD`, faengt das Band nicht
# still an, $2.000-Maerkte als Dominanz zu melden — es faellt hier auf.
DOM_MIN_MARKET = float(os.environ.get("WHALE_DOM_MIN_MARKET") or 7500)

# ⏱️ Das Reifefenster — Lucas: „ein Markt in 2 Wochen wo jetzt 5K gespielt werden die 60 % sind,
# interessiert mich ja 0. Wir muessens quasi zeitlich wie die Whale-Alerts eingrenzen."
#
# Er hat recht, und zwar staerker als gedacht. Gemessen an 424 Maerkten mit Verlauf bis zum
# Anpfiff, Volumen im Verhaeltnis zum Endstand:
#
#     2,5-3 h vor Anpfiff   Median  54 %   (unteres Viertel  28 %)
#     1,5-2 h               Median  75 %
#     0,5-1 h               Median  92 %   (unteres Viertel  73 %)
#     0-0,5 h               Median 100 %
#
# Ein Anteil, der 3 h vor Anpfiff gemessen wird, hat einen halb leeren Nenner — er ist
# systematisch zu HOCH. Das ist genau Lucas' „jeder Markt beginnt bei 0", nur passiert es nicht
# zwei Wochen vorher, sondern INNERHALB des Fensters, das wir ohnehin schon erfassen.
#
# Der Zeitpunkt, an dem der Anteil gemessen wird, ist deshalb nicht egal. Gemessen wird erst, wenn
# der Markt weitgehend voll ist. 1,0 h, weil dort der Nenner im Median 92 % seines Endstands hat
# und 94 % aller Close-Zeilen diesen Punkt ueberhaupt erreichen (2.756 von 2.928) — enger gaebe
# kaum mehr Genauigkeit und kostet Abdeckung.
#
# ⚠️ Das ist ein TAUSCH: die Karte kommt spaeter. Eine Position, die 2,8 h vorher aufgemacht wird,
# steht erst ~1,8 h spaeter im Kanal. Fuer ein Beobachtungsband ist das richtig herum — ein zu
# frueh gemessener Anteil verdirbt die Zahl, um die es in diesem Band ueberhaupt geht.
DOM_MAX_HTK = float(os.environ.get("WHALE_DOM_MAX_HTK") or 1.0)

# 🎯 Mindestquote — Lucas 11.09.2026 nach der ersten echten Karte („Einstieg @1,21"):
# „bitte mindest odd auch einbauen, ab 1,35 erst wieder."
#
# Der Befund dahinter ist groesser als die eine Karte. Von den fuenf Positionen, die das Band an
# diesem Tag gefunden haette, lagen VIER unter 1,35: @1,14 · @1,18 · @1,21 · @1,25. Nur eine
# (@1,75) daruber. Das ist kein Zufall, sondern Bauart: die $25.000-Schwelle des Whale-Pushs
# landet in grossen, ausgeglichenen Maerkten — die $3.000-Schwelle dieses Bands landet in kleinen
# Favoritenmaerkten, wo ein einzelner Einsatz ueberhaupt erst 40 % erreichen kann.
#
# Gemessen am Public-Whale-Buch (27 abgerechnete Pushs mit Preis): dort steht KEINE EINZIGE Zeile
# unter Quote 1,35. Das Band haette also mehrheitlich in einer Ecke gemessen, in der das Projekt
# noch nie etwas gemessen hat — und in der die Marge den Wert frisst: bei 1,14 braucht man 88 %
# Trefferquote zum Nullpunkt.
#
# 1,35 ist im Projekt schon der Boden (pick-engine.js „Cheap ML filter", stake-radar.js), also
# dieselbe Zahl und nicht eine neue.
DOM_MIN_QUOTE = float(os.environ.get("WHALE_DOM_MIN_QUOTE") or 1.35)

# 🔬 Die Kleinmarkt-Spur (11.09.2026). Geschrieben von poly_money_broad.py, gelesen NUR hier.
# Lucas: „ich will ja herausfinden, Spiele bei Poly, die kleine Maerkte sind und wo ein
# eventuelles Sharp Wallet hoeher sitzt." Genau diese Maerkte standen in KEINER Datei, die dieses
# Band lesen konnte — s. die Begruendung in poly_money_broad.py bei KLEIN_MIN_VOL.
DOM_KLEIN_FILE = BASE / "poly_money_klein.json"

# ⏱️ Die gemessene Fuellkurve: wie voll ein Markt im MEDIAN ist, je Stunde vor Anpfiff (424
# Maerkte mit Verlauf bis zum Anpfiff). Sie steht hier als Tabelle und nicht als Formel, weil sie
# GEMESSEN ist — eine glatte Kurve daruberzulegen wuerde eine Genauigkeit behaupten, die die
# Streuung nicht hergibt (unteres Viertel bei 2,5-3 h: 28 %).
DOM_FUELLUNG = ((0.5, 1.00), (1.0, 0.92), (1.5, 0.82), (2.0, 0.75), (2.5, 0.69), (3.0, 0.54))

# 🔴 12.09.2026 (Lucas: „jetzt kommen halt viele solcher pushs") — das fehlende Gate.
#
# Er schickte vier Karten hintereinander. Gemeinsam hatten sie NICHT den Markt und nicht den
# Anteil, sondern die WALLETS: 7/15 (47 %), 15/34 (44 %), 266/582 (46 %), 13/24 (54 %). Das sind
# Muenzwuerfe. Die grossen Lebensbilanzen daneben ($501K, $295K, $2,53M) sagen nichts ueber
# Sport — sie stammen aus Wahl- und Kryptomaerkten, genau die Vermischung, die sharp_gate.py am
# 29.08. auseinandergenommen hat.
#
# Das Band hatte von Anfang an KEIN Wallet-Gate — nur `_is_confirmed_loser` (P&L bekannt UND
# negativ), was bei 87 % unbekanntem P&L fast nie greift. Dabei stand Lucas' Bedingung von
# Anfang an in seinem ersten Satz: „Spiele bei Poly, die kleine Maerkte sind und wo ein
# eventuelles SHARP WALLET hoeher sitzt." Ich habe die Marktseite dreimal nachgebessert und die
# Wallet-Seite nie gebaut.
#
# Gemessen am Stand vom 12.09.: 32 Kandidaten ohne Gate, 5 mit. Die fuenf tragen 213/390 (55 %,
# CLV +0,63pp), 93/157 (59 %, +0,46pp) und 175/307 (57 %, +0,80pp) — grosse Stichproben mit
# positivem CLV, nicht die Muenzwuerfe von oben.
#
# Es gilt `sharp_gate.is_sharp`: n>=8, Wilson-Untergrenze der Trefferquote ueber 50 %, CLV >= 0,
# kein bestaetigter Verlierer. DIE Definition des Projekts — eine eigene waere die fuenfte.
DOM_NUR_SHARP = (os.environ.get("WHALE_DOM_NUR_SHARP") or "1").strip() not in ("0", "false", "")


def _dom_quote(pos, min_quote=None):
    """Die Quote, mit der diese Beobachtung ins Buch geht — oder None, wenn sie zu niedrig ist.

    Gerechnet wird auf dem PUSH-Preis (`_push_price`), nicht auf dem Einstieg des Wals: das ist
    der Preis, den ein Leser in dem Moment bekaeme, und derselbe, den `_log_dominanz_push` bucht.
    Waere hier der Einstiegspreis massgeblich, koennte eine Zeile mit @1,50 ins Buch gehen und
    mit @1,15 abgerechnet werden — dieselbe Zahl an zwei Stellen mit zwei Bedeutungen.

    Fehlt der Preis, gibt es KEINE Quote und damit keinen Push. „Eine Trefferquote ohne die
    Quoten ist keine Zahl" — eine Beobachtung ohne abrechenbaren Preis waere genau das.
    """
    min_quote = DOM_MIN_QUOTE if min_quote is None else min_quote
    p = _push_price(pos)
    if not isinstance(p, (int, float)) or isinstance(p, bool) or not 0 < p < 1:
        return None
    q = 1.0 / p
    return q if q >= min_quote else None


def klein_positionen(klein, now=None):
    """Die Wal-Positionen der Kleinmarkt-Spur, in der Form von `track["open"]`. REIN.

    Der Wallet-Track kennt diese Maerkte nicht — er wird aus `pre` gespeist, und `pre` hat den
    $7.500-Boden. Statt einen zweiten Track zu fuehren, werden die Positionen hier direkt aus den
    Marktzeilen abgeleitet: alles Noetige (Wallet, Seite, Einsatz, Preis) steht dort.

    ⚠️ Was hier FEHLT und nicht erfunden wird:
      · `firstTs` — wir wissen nicht, wann die Wallet eingestiegen ist, nur dass sie jetzt da ist.
        Gesetzt wird die Aufnahmezeit des Markts, und weil die Spur nur innerhalb des
        Anpfiff-Fensters sammelt, ist die Frischepruefung damit ohnehin erfuellt.
      · `htkFirst` — derselbe Grund, bleibt None. Der Vorlauf der WALLET ist hier unbekannt; die
        Reife des MARKTS (`htkMess`) ist es nicht und entscheidet.
      · `firstPrice` ist der AKTUELLE Preis, nicht der Einstieg. Die Karte zeigt deshalb bei
        diesen Zeilen keinen „Einstieg" — eine Zahl, die wie ein Einstieg aussieht und keiner
        ist, waere schlimmer als keine.
    """
    now = now or datetime.now(timezone.utc)
    aus = {}
    if not isinstance(klein, dict):
        return aus          # eine kaputte oder fehlende Datei nimmt die Spur raus, nicht das Band
    for key, m in klein.items():
        if not isinstance(m, dict):
            continue
        preise = m.get("prices") or {}
        for w in (m.get("whales") or []):
            if not isinstance(w, dict):
                continue
            wallet, seite = w.get("wallet"), w.get("side")
            preis = preise.get(seite)
            if not wallet or seite is None or not isinstance(preis, (int, float)):
                continue
            usd = w.get("usd")
            if not isinstance(usd, (int, float)) or usd <= 0:
                continue
            aus["%s|%s|%s" % (wallet, key, seite)] = {
                "wallet": wallet, "key": key, "side": seite,
                "league": m.get("league"), "sport": m.get("sport"),
                "usd": round(float(usd)),
                "firstPrice": round(float(preis), 4),
                "lastPrice": round(float(preis), 4),
                "firstTs": (m.get("capturedAt") or now.isoformat()),
                "htkFirst": None,
                "quelle": "klein",          # stempeln, damit sich beide Spuren trennen lassen
            }
    return aus


def fuellgrad(htk):
    """Wie voll ein Markt zu dieser Stunde vor Anpfiff im Median ist. REIN.

    1.0 ab Anpfiff, sonst die naechsthoehere gemessene Stufe aus DOM_FUELLUNG. Unbekannte oder
    unsinnige Stunde -> None, nie ein Default: ein geratener Fuellgrad waere ein geratener
    Nenner, und der Nenner ist in diesem Band die ganze Frage.
    """
    if not isinstance(htk, (int, float)) or isinstance(htk, bool):
        return None
    if htk <= 0:
        return 1.0
    for grenze, anteil in DOM_FUELLUNG:
        if htk <= grenze:
            return anteil
    return DOM_FUELLUNG[-1][1]   # frueher als 3 h: so voll wie im leersten gemessenen Band


def anpfiff_zeit(pos, broad):
    """Wann das Spiel beginnt, als datetime — oder None. REIN.

    Der Markt speichert keinen Anpfiff, sondern `capturedAt` + `hoursToKickoff`. Der Anpfiff ist
    die Summe. Dieselbe Rechnung nutzt `poly_money_broad.capture()` seit 06.08.2026, um
    Geister-Maerkte zu prunen — hier wird sie nur gelesen.

    11.09.2026 (Lucas: „bzw sollt ich sehen wann das Spiel ist / seh ich ned"). Die Karte nannte
    einen Anteil, einen Betrag und eine Wallet — aber nicht, worauf sich das alles bezieht. Eine
    Beobachtung ohne Zeitpunkt kann man nicht einordnen und schon gar nicht mitverfolgen.
    """
    m = (broad or {}).get(pos.get("key")) if isinstance(broad, dict) else None
    if not isinstance(m, dict):
        return None
    htk = m.get("hoursToKickoff")
    if not isinstance(htk, (int, float)) or isinstance(htk, bool):
        return None
    ct = _iso(m.get("capturedAt"))
    if ct is None:
        return None
    return ct + timedelta(hours=float(htk))



def dom_freigabe(pos, broad, max_htk=None, min_share=None, now=None):
    """Wann diese Beobachtung raus darf — und mit welcher Begruendung. REIN.

    Gibt (htk, frueh) zurueck oder None. `frueh=True` heisst: der Markt ist noch nicht reif, die
    Dominanz ist aber so deutlich, dass sie auch dann noch ueber der Schwelle laege, wenn sich
    der Markt bis zum Anpfiff auf seinen Median-Endstand auffuellt.

    ── Warum es diesen zweiten Weg gibt ─────────────────────────────────────────────────────
    Lucas 11.09.2026: „hast du Idee wie wir das Zeitproblem loesen?" Das Reifefenster loeste das
    MESSproblem (ein Anteil bei 2,8 h hat einen halb leeren Nenner) und schuf ein ANZEIGEproblem:
    eine Position, die 2,8 h vorher aufgemacht wird, steht erst 1,8 h spaeter im Kanal.

    Beides zugleich geht, wenn man nicht den Anteil schaetzt, sondern die Schaetzung gegen sich
    selbst laufen laesst: `anteil · fuellgrad(htk)` ist der Anteil, der uebrig bliebe, WENN der
    Markt sich noch wie ueblich fuellt. Wer den so gerechnet noch besteht, ist frueh belegbar
    dominant; wer nur knapp ueber der Schwelle liegt, wartet auf den echten Nenner.

    ⚠️ Ehrlich bleiben, was das ist: der Fuellgrad ist ein MEDIAN. In der Haelfte der Faelle
    fuellt sich der Markt staerker und der Anteil faellt doch unter die Schwelle. Deshalb wird
    im Buch `fruehFreigabe` gestempelt — sonst liesse sich spaeter nicht trennen, ob eine
    Trefferquote von den frueh oder den reif gemeldeten Zeilen kommt.
    """
    max_htk = DOM_MAX_HTK if max_htk is None else max_htk
    min_share = DOM_MIN_SHARE if min_share is None else min_share
    m = (broad or {}).get(pos.get("key")) if isinstance(broad, dict) else None
    htk = (m or {}).get("hoursToKickoff")
    if not isinstance(htk, (int, float)) or isinstance(htk, bool):
        return None                       # unbekannter Messzeitpunkt ist nicht „passt schon"
    htk = float(htk)
    # 🔴 11.09.2026, an der ersten echten Karte gesehen: sie ging 26 Minuten NACH Anpfiff raus.
    # Grund ist der Versatz zwischen Messung und Versand — die Close-Zeile stammte von 20 Minuten
    # VOR Anpfiff, der Runner lief spaeter. `htk` ist der Messzeitpunkt, nicht die Gegenwart.
    #
    # Fuer die MESSUNG ist ein Markt nach Anpfiff maximal reif; fuer den PUSH ist er wertlos:
    # Lucas wollte „aktiv mitbeobachten", und die genannte Quote waere nicht mehr zu bekommen.
    # Deshalb entscheidet hier die ECHTE Uhr gegen den Anpfiff, nicht der Messzeitpunkt.
    #
    # Kein bestimmbarer Anpfiff heisst hier NICHT „dann eben durchlassen". Dieses Band lebt davon,
    # dass Lucas ein Spiel vorher mitverfolgen kann — wann es ist, ist keine Zusatzinfo, sondern
    # die Voraussetzung. Dieselbe Regel wie beim fehlenden Volumen und beim fehlenden
    # Messzeitpunkt: fehlende Information laesst nicht durch.
    ko = anpfiff_zeit(pos, broad)
    if ko is None or ko <= (now or datetime.now(timezone.utc)):
        return None                       # laeuft schon (oder unbekannt) — keine Beobachtung mehr
    if htk <= max_htk:
        return (htk, False)               # der Nenner steht — der normale Weg
    a = seiten_anteil(pos, broad)
    f = fuellgrad(htk)
    if a is None or f is None:
        return None
    return (htk, True) if a * f >= min_share else None


def markt_reif(pos, broad, max_htk=None):
    """Ist der Nenner voll genug, um einen Anteil daraus zu lesen? REIN.

    Gibt die Stunden bis Anpfiff der Close-Zeile zurueck, wenn der Markt reif ist — sonst None.
    Die Stunde kommt aus der CLOSE-Zeile (`hoursToKickoff`), nicht aus `htkFirst` der Position:
    gefragt ist, wie voll der MARKT beim Messen war, nicht wie frueh die Wallet drin war. Das
    sind zwei verschiedene Dinge, und nur das erste entscheidet ueber die Guete des Anteils.

    Fehlt die Stunde, ist der Markt NICHT reif. Ein unbekannter Messzeitpunkt als „passt schon" zu
    lesen waere dieselbe Fehlerklasse wie ein fehlendes Volumen als 100 % zu lesen.
    """
    max_htk = DOM_MAX_HTK if max_htk is None else max_htk
    m = (broad or {}).get(pos.get("key")) if isinstance(broad, dict) else None
    htk = (m or {}).get("hoursToKickoff")
    if not isinstance(htk, (int, float)) or isinstance(htk, bool):
        return None
    # Nach dem Anpfiff (htk <= 0) ist der Vorspiel-Markt fertig — das ist reif, nicht unreif.
    return float(htk) if htk <= max_htk else None


def dom_sperre(dom_seen, trades_seen=None, pub_seen=None) -> dict:
    """Was fuer das Dominanz-Band als „schon gemeldet" gilt. REIN.

    Drei Staende, eine Sperre: der eigene (`dom_seen`) und BEIDE Whale-Staende. Eine Position,
    die als Whale schon im Trades- oder Public-Kanal stand, kommt nicht Minuten spaeter ein
    zweites Mal als Dominanz — Lucas liest beide Kanaele, die Doppelung waere seine.

    Steht hier und nicht in main(), weil eine Regel, die nur im Ablauf existiert, nicht
    pruefbar ist: der Zusammenbau der Sperre IST die Regel.
    """
    aus = dict(dom_seen if isinstance(dom_seen, dict) else {})
    for stand in (trades_seen, pub_seen):
        if isinstance(stand, dict):
            aus.update({k: True for k in stand})
    return aus


def dominanz_kandidaten(track, broad, seen=None, now=None, min_usd=None, min_share=None,
                        min_market=None, max_htk=None, klein=None, blocked=None) -> list:
    """Positionen mit kleinem Markt und grossem Anteil. REIN (alles injizierbar).

    🔴 KORREKTUR 12.09.2026 (Lucas: „aja und bitte us Sport gleich weg"). Hier stand bis heute
    das Gegenteil: „ausdruecklich ALLE Sportarten … die Sperrliste gilt hier NICHT, weil dies ein
    Beobachtungsband ist und kein Kanal, dem jemand folgen soll."

    Das Argument war in sich schluessig und trotzdem falsch: Lucas LIEST den Trades-Kanal. Eine
    Karte, die er nicht gebrauchen kann, kostet ihn Aufmerksamkeit — ob sie „Beobachtung" heisst
    oder „Empfehlung", macht fuer die Zeit beim Lesen keinen Unterschied. Ausloeser war ein
    MLB-Push mit einer 314/742-Wallet (42 %) und ohne erfasste Paarung.

    Die Sperre kommt aus DERSELBEN Quelle wie fuer alle anderen Kanaele (`blocked_cats` →
    poly-wallets.js `PW_BLOCKED_BET_CATS`). Legt Lucas sie dort um, zieht dieses Band mit — eine
    eigene Liste hier waere genau die Drift, gegen die `blocked_cats` gebaut wurde.

    Was sehr wohl gilt:
      · SPORT, kein Politik/Krypto (`_pub_ok` prueft Sportart und ein sinnvolles Preisfenster).
      · KEINE gesperrte Sportart (`bet_blocked`, dieselbe Liste wie in allen anderen Kanaelen).
      · Ein Marktboden, damit „100 % von $300" nicht als Dominanz durchgeht.
      · Frische (`FRESH_DAYS`) wie ueberall — eine alte Position ist kein Ereignis.
      · REIFE des Markts (`dom_freigabe`): der Anteil wird erst gelesen, wenn der Nenner steht —
        oder wenn er so deutlich ist, dass er auch bei ueblicher Nachfuellung noch traegt.
      · QUOTE ab DOM_MIN_QUOTE. Ohne Preis kein Push: eine Beobachtung, die sich nicht
        abrechnen laesst, ist keine.
      · SHARP-Wallet (`DOM_NUR_SHARP`) — Lucas' urspruengliche Bedingung, s. dort.
      · Kein bestaetigter Verlierer.
    """
    min_usd = DOM_MIN_USD if min_usd is None else min_usd
    min_share = DOM_MIN_SHARE if min_share is None else min_share
    min_market = DOM_MIN_MARKET if min_market is None else min_market
    max_htk = DOM_MAX_HTK if max_htk is None else max_htk
    now = now or datetime.now(timezone.utc)
    seen = seen if isinstance(seen, dict) else {}
    scores = (track or {}).get("scores") or {}
    # Zwei Quellen, ein Band: der Wallet-Track (Maerkte ab $7.500) und die Kleinmarkt-Spur
    # (darunter). Die Bewertung der Wallet kommt IMMER aus `scores` des Haupt-Tracks — dort
    # stehen 3.650 Konten mit Historie; eine Kleinmarkt-Zeile bringt keine eigene Reputation mit
    # und soll auch keine vortaeuschen.
    offen = dict((track or {}).get("open") or {})
    offen.update(klein_positionen(klein, now) if klein else {})
    # EINE Marktsicht statt zwei durchgereichter Dateien: jede Hilfsfunktion (Anteil, Anpfiff,
    # Reife, Stempel) schlaegt den Markt unter seinem Key nach, und die soll nicht jede fuer sich
    # wissen muessen, aus welcher Datei die Zeile kam. Bei einer Kollision gewinnt `broad` — das
    # ist die eingefrorene Close-Zeile eines Markts, der inzwischen ueber den Boden gewachsen
    # ist, und sie ist die belastbarere von beiden.
    sicht = dict(klein if isinstance(klein, dict) else {})
    sicht.update(broad if isinstance(broad, dict) else {})
    aus = []
    for pkey, pos in offen.items():
        if not isinstance(pos, dict) or pkey in seen:
            continue
        usd = pos.get("usd")
        if not isinstance(usd, (int, float)) or usd < min_usd:
            continue
        m = sicht.get(pos.get("key"))
        tot = (m or {}).get("totalUsd")
        # Der Marktboden gilt fuer die Haupt-Spur. Fuer die Kleinmarkt-Spur waere er ein
        # Widerspruch in sich: sie existiert, WEIL diese Maerkte darunter liegen. Dort gilt ihr
        # eigener Boden, und der steht in poly_money_broad.py (KLEIN_MIN_VOL) — also dort, wo
        # entschieden wird, welcher Markt ueberhaupt abgefragt wird.
        _boden = 0 if pos.get("quelle") == "klein" else min_market
        if not isinstance(tot, (int, float)) or tot < _boden or tot <= 0:
            continue
        a = seiten_anteil(pos, sicht)         # Anteil an der EIGENEN Seite — s. dort, warum
        if a is None or a < min_share:
            continue
        if dom_freigabe(pos, sicht, max_htk, min_share, now) is None:
            continue                          # Nenner noch nicht voll und nicht deutlich genug
        if _dom_quote(pos) is None:
            continue                          # unter dem Quotenboden — oder gar kein Preis
        if DOM_NUR_SHARP and not SG.is_sharp(scores.get(pos.get("wallet"))):
            continue                          # keine belegte Wallet — s. DOM_NUR_SHARP
        if not _pub_ok(pos):
            continue
        if bet_blocked(pos, blocked):
            continue                          # gesperrte Sportart — s. DOM_SPERRE_GILT
        if _is_confirmed_loser(scores.get(pos.get("wallet"))):
            continue
        ft = _iso(pos.get("firstTs"))
        if ft and (now - ft).days >= FRESH_DAYS:
            continue
        aus.append((pkey, pos, a))
    # Der groesste Anteil zuerst — das ist die Eigenschaft, um die es in diesem Band geht.
    aus.sort(key=lambda x: -x[2])
    aus = aus[:DOM_MAX_ALERTS]
    # Die Marktsicht haengt am Ergebnis, nicht am Aufrufer: wer die Karte baut oder die Zeile
    # bucht, muss denselben Markt sehen wie die Auswahl. Sie hier zurueckzugeben ist billiger als
    # die Regel „nimm dieselbe Sicht" in jede aufrufende Stelle zu schreiben und zu hoffen.
    dominanz_kandidaten.sicht = sicht
    return aus


def _dom_balken(anteil, breite=10) -> str:
    """Der Anteil als Balken. Er ist die EINE Zahl, um die es in diesem Band geht — und ein Balken
    liest sich auf dem Handy schneller als „68 %" zwischen zwei anderen Prozentzahlen."""
    try:
        n = max(0, min(breite, int(round(float(anteil) * breite))))
    except (TypeError, ValueError):
        return ""
    return "█" * n + "░" * (breite - n)


try:
    from zoneinfo import ZoneInfo
    _TZ_WIEN = ZoneInfo("Europe/Vienna")
except Exception:
    _TZ_WIEN = None   # faellt auf UTC zurueck statt zu brechen


def _anpfiff_zeile(pos, broad, now=None):
    """„🕒 Anpfiff 21:30 Uhr — in 1 h 05" — oder nichts. Die Uhrzeit steht in Wiener Zeit, weil
    sie fuer Lucas lesbar sein muss und nicht fuer den Server."""
    ko = anpfiff_zeit(pos, broad)
    if ko is None:
        return None
    now = now or datetime.now(timezone.utc)
    lokal = ko.astimezone(_TZ_WIEN) if _TZ_WIEN else ko
    rest = (ko - now).total_seconds() / 3600.0
    if rest > 0:
        wann = "in %s" % _htk_text(rest)
    elif rest > -3:
        wann = "läuft seit %s" % _htk_text(-rest)
    else:
        wann = "angepfiffen"
    return "🕒 Anpfiff <b>%s</b> — %s" % (lokal.strftime("%H:%M"), wann)


def _htk_text(h) -> str:
    """Stunden bis Anpfiff so, wie ein Mensch sie liest. „0,3 h" liest niemand — „20 Min" schon."""
    try:
        h = float(h)
    except (TypeError, ValueError):
        return ""
    if h <= 0:
        return "Anpfiff"
    if h < 1:
        return "%d Min" % max(1, round(h * 60))
    return ("%.1f h" % h).replace(".", ",")


def build_dominanz_card(pos, scores, broad, anteil=None, now=None) -> str:
    """Das Beobachtungs-Band als Telegram-Karte — bewusst anders gebaut als jede andere.

    11.09.2026 (Lucas: „mach's bitte vom Template her so, dass ich's wirklich gleich seh, weil das
    geht sonst unter in den Nachrichten"). Drei Dinge unterscheiden sie auf einen Blick von der
    Whale-Karte: die Doppel-Linie als Rahmen, der Balken statt einer weiteren Prozentzahl, und die
    Kopfzeile, die den Anteil NENNT statt den Betrag.

    ⚠️ Die letzte Zeile ist kein Kleingedrucktes, sondern der Zweck: dieses Band ist eine
    BEOBACHTUNG. Es hat kein Buch, das etwas belegt, und niemand soll ihm folgen, bis es eines
    hat. Eine Karte, die aussieht wie eine Empfehlung, wird als eine gelesen.
    """
    a = seiten_anteil(pos, broad) if anteil is None else anteil
    emoji, sport = _sport(pos.get("league"), pos.get("sport"))
    key = pos.get("key")
    side = pos.get("side") or "?"
    matchup = _matchup(key, broad)
    _label = ausgang_label(side, _markt_frage(key, broad)) or side
    m = (broad or {}).get(key) if isinstance(broad, dict) else None
    tot = (m or {}).get("totalUsd")

    kopf = "🎯 <b>MARKT-DOMINANZ</b>"
    if a is not None:
        kopf += " · <b>%d %%</b> des Marktes" % round(a * 100)
    lines = ["━━━━━━━━━━━━━━━━━━━━", kopf, "━━━━━━━━━━━━━━━━━━━━", ""]
    lines.append("%s <i>%s</i>" % (emoji, _esc(sport)))
    # Die Ueberschrift ist die PAARUNG. Faellt sie auf die Seite zurueck, steht dort fett „Over"
    # und liest sich wie ein Mannschaftsname — genau die Verwechslung, die Lucas gemeldet hat.
    # Ist die Paarung nicht erfasst (114 von 726 Sub-Maerkten haben keinen erfassten Hauptmarkt),
    # bleibt die Zeile LEER: die Seite steht ohnehin in der Geldzeile, und eine Ueberschrift, die
    # etwas anderes behauptet als sie ist, ist schlechter als keine.
    if matchup:
        lines.append("<b>%s</b>" % _esc(matchup))
    # 🔴 11.09.2026 (Lucas: „denke hier sind corner gemeint, bitte anpassen"). Ohne diese Zeile
    # stand bei einem Ecken-Markt als Ueberschrift „Over" und sonst nichts — weder die Paarung
    # noch, worauf ueberhaupt gesetzt wurde. Die Marktfrage lag vor und wurde nicht gezeigt.
    #
    # Reihenfolge: erst die erfasste Frage (praeziseste Auskunft, enthaelt die Linie), sonst der
    # Markttyp aus dem Slug. Beim Hauptmarkt steht hier NICHTS — „Matchsieger" dazuzuschreiben
    # waere Fuelltext, und die Karte soll nur sagen, was sie weiss.
    _art = sub_markt_art(key)
    _frage = _markt_frage(key, broad)
    if _art:
        # NUR beim Sub-Markt. Beim Hauptmarkt lautet die Frage „Seville: Munar vs Brancaccio" —
        # also genau das, was schon in der Ueberschrift steht. Eine Zeile, die sich selbst
        # wiederholt, macht die eine Zeile unglaubwuerdig, auf die es ankommt.
        _txt = _frage or _art
        lines.append(("📋 <b>%s</b>" if not matchup else "📋 <i>%s</i>") % _esc(_txt))
    elif not matchup:
        lines.append("📋 <i>Paarung nicht erfasst — siehe Markt-Link</i>")
    lines.append("")
    if a is not None:
        lines.append("<code>%s</code>  <b>%d %%</b>" % (_dom_balken(a), round(a * 100)))
    _geld = "💰 <b>%s</b> auf <b>%s</b>" % (_usd(pos.get("usd") or 0), _esc(_label))
    if isinstance(tot, (int, float)) and tot > 0:
        _geld += "\n📦 Markt gesamt <b>%s</b>" % _usd(tot)
    lines.append(_geld)
    # 🕒 Wann das Spiel ist — Lucas 11.09.2026: „sollt ich sehen wann das Spiel ist, seh ich ned."
    _ap = _anpfiff_zeile(pos, broad, now)
    if _ap:
        lines.append(_ap)
    # ⏱️ Der Messzeitpunkt gehoert auf die Karte, nicht nur ins Buch. Ein Anteil ist eine Zahl mit
    # Zeitstempel — wer ihn ohne liest, haelt 2,8-h-Anteile und 0,3-h-Anteile fuer dasselbe Mass.
    # Gerechnet wird hier NUR die Beschriftung — ueber das Senden hat `dominanz_kandidaten`
    # schon entschieden. Deshalb der Messzeitpunkt direkt aus der Close-Zeile und nicht noch
    # einmal ueber die Freigabe: sonst faellt die Zeile still weg, sobald die Uhr weitergelaufen
    # ist, und die Karte verschweigt ausgerechnet ihre eigene Grundlage.
    _frueh_gesetzt = False
    _h = (m or {}).get("hoursToKickoff")
    if isinstance(_h, (int, float)) and not isinstance(_h, bool):
        _h = float(_h)
        _frueh = _frueh_gesetzt = _h > DOM_MAX_HTK
        if _frueh:
            # Frueh heraus, weil die Dominanz auch bei ueblicher Nachfuellung noch traegt. Das
            # gehoert auf die Karte, nicht nur ins Buch: der Leser soll wissen, dass der Nenner
            # hier noch waechst und der Anteil noch fallen kann.
            lines.append("⏱️ gemessen <b>%s</b> vor Anpfiff — <i>Markt füllt sich noch "
                         "(~%d %% voll), der Anteil kann noch fallen</i>"
                         % (_htk_text(_h), round((fuellgrad(_h) or 0) * 100)))
        else:
            lines.append("⏱️ gemessen <b>%s</b> vor Anpfiff — Markt steht" % _htk_text(_h))
    # Zwei Preise, zwei Bedeutungen: der Einstieg des Wals ist Geschichte, die aktuelle Quote ist
    # das, was ein Leser JETZT bekaeme — und die, mit der das Buch rechnet. Bis heute stand nur
    # der Einstieg da; bei einer Karte, die auf den reifen Markt wartet, ist das die falsche Zahl.
    # Bei einer Kleinmarkt-Zeile kennen wir den Einstieg des Wals NICHT — dort steht nur der
    # aktuelle Preis. Ein „Einstieg @x", der in Wahrheit der Jetzt-Preis ist, waere eine erfundene
    # Zahl an der Stelle, an der Lucas die Bewegung ablesen wuerde.
    _e = None if pos.get("quelle") == "klein" else _pub_einstieg(pos)
    _q = _dom_quote(pos)
    if _q is not None:
        _jz = _quote(_push_price(pos))
        # Zweimal dieselbe Zahl nebeneinander liest sich wie ein Fehler. Steht der Markt noch da,
        # wo der Wal eingestiegen ist, ist das EINE Aussage und gehoert auch als eine dazustehen.
        lines.append(_e if (_e and _e.endswith(_jz)) else
                     ((_e + " · 📈 jetzt <b>%s</b>" % _jz) if _e else "📈 <b>%s</b>" % _jz))
    elif _e:
        lines.append(_e)
    lines.append("")
    lines.append(_wallet_line(scores, pos.get("wallet")))
    if key:
        lines.append('\n<a href="https://polymarket.com/event/%s">Markt ansehen ↗</a>' % _esc(key))
    # Die Fusszeile muss zu DIESER Karte passen. Sie pauschal „nur wenn der Markt steht" sagen zu
    # lassen, waere auf einer frueh freigegebenen Karte ein Widerspruch im eigenen Text.
    _wann = ("der Anteil auch bei üblicher Nachfüllung des Marktes noch trägt" if _frueh_gesetzt
             else "der Markt steht")
    lines.append("\n<i>🔬 Beobachtungsband — läuft mit, ist noch kein Beleg. Erst ab $%d "
                 "Einsatz, %d %% des Geldes auf dieser Seite, Quote ab %s%s — und nur, "
                 "wenn %s.</i>"
                 % (int(DOM_MIN_USD), int(DOM_MIN_SHARE * 100),
                    ("%.2f" % DOM_MIN_QUOTE).replace(".", ","),
                    ", belegte Wallet" if DOM_NUR_SHARP else "", _wann))
    return "\n".join(lines)


def markt_stempel(pos, broad) -> dict:
    """{totalUsd, anteil} des Markts im Moment des Sendens — leer, wenn nicht bestimmbar. REIN.

    🔴 11.09.2026 (Lucas: „mich wuerde interessieren, ob bei kleinen Maerkten mit grossem Anteil
    die Trefferquote hoch ist"). Die Frage war nicht zu beantworten: der Marktanteil steht auf
    JEDER Karte, aber in KEINER abgerechneten Zeile. Von 64 Public-Pushs liess sich das Volumen
    nachtraeglich nur bei 40 rekonstruieren — bei 24 war der Markt aus `poly_money_broad_close`
    verschwunden und in der Historie nicht mehr auffindbar.

    Dieselbe Lehre wie beim Serien-Stempel (04.09.) und beim `cond`-Stempel (10.09.): eine
    Momentaufnahme laesst sich nicht rueckwirkend rekonstruieren, also wird sie im Moment des
    Sendens festgehalten. Fehlt das Volumen, steht hier NICHTS — kein 0, kein 100 %. Ein
    Anteil ohne Nenner waere schlimmer als kein Anteil.
    """
    a = markt_anteil(pos, broad)
    sa = seiten_anteil(pos, broad)
    m = (broad or {}).get(pos.get("key")) if isinstance(broad, dict) else None
    tot = (m or {}).get("totalUsd")
    aus = {}
    if isinstance(tot, (int, float)) and tot > 0:
        aus["totalUsd"] = round(float(tot), 2)
    if a is not None:
        aus["anteil"] = round(float(a), 4)          # am Gesamtmarkt — Favoriten-Drall, s. seiten_anteil
    if sa is not None:
        aus["seitenAnteil"] = round(float(sa), 4)   # an der eigenen Seite — das Mass des Bands
    _seite = ((m or {}).get("shares") or {}).get(pos.get("side")) if isinstance(m, dict) else None
    if isinstance(_seite, (int, float)) and _seite > 0:
        aus["seiteUsd"] = round(float(_seite), 2)   # der Nenner, damit beides nachrechenbar bleibt
    # ⏱️ 11.09.2026: WANN der Anteil gemessen wurde, gehoert zur Zahl dazu. Ein Anteil bei 2,8 h
    # vor Anpfiff und einer bei 0,3 h sind nicht dasselbe Mass — der Nenner ist im Median 54 %
    # gegen 100 % voll. Ohne diesen Stempel liessen sich die beiden spaeter nicht trennen, und
    # die Auswertung wuerde zwei verschiedene Dinge zusammenruehren.
    htk = (m or {}).get("hoursToKickoff")
    if isinstance(htk, (int, float)) and not isinstance(htk, bool):
        aus["htkMess"] = round(float(htk), 2)
    hf = pos.get("htkFirst")
    if isinstance(hf, (int, float)) and not isinstance(hf, bool):
        aus["htkFirst"] = round(float(hf), 2)   # Vorlauf der WALLET — anderes Mass, eigene Frage
    lg = pos.get("league")
    if lg:
        aus["league"] = str(lg)                 # fuer die spaetere Frage: ist $10K in EPL dasselbe
    return aus                                  # wie $10K in Cricket? (Median EPL $103K, Cricket $12K)


def _log_public_push(pkey, pos, scores, restock, ts, broad=None) -> None:
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
        # 11.09.2026: Marktgroesse und Anteil im Moment des Sendens — s. markt_stempel().
        **markt_stempel(pos, broad),
    })
    try:
        _save(PUB_LEDGER_FILE, led[-PUB_LEDGER_KEEP:])
    except Exception as e:
        print("Public-Ledger-Schreibfehler:", e)


def _dom_freigabe_stempel(pos, broad, now=None) -> dict:
    """{fruehFreigabe, fuellgrad, anteilKons} — leer, wenn nichts davon bestimmbar ist. REIN.

    `anteilKons` ist der konservativ gerechnete Anteil (Anteil × Fuellgrad). Bei einer reifen
    Zeile ist er gleich dem Anteil; bei einer fruehen ist er die Zahl, auf die hin entschieden
    wurde. Beide zu buchen kostet nichts und beantwortet spaeter die Frage, ob die fruehe
    Freigabe getragen hat — ohne sie liesse sich das nicht mehr rekonstruieren.
    """
    fr = dom_freigabe(pos, broad, now=now)
    if fr is None:
        return {}
    htk, frueh = fr
    aus = {"fruehFreigabe": bool(frueh)}
    f = fuellgrad(htk)
    a = seiten_anteil(pos, broad)
    if f is not None:
        aus["fuellgrad"] = round(float(f), 3)
        if a is not None:
            aus["anteilKons"] = round(float(a) * float(f), 4)
    return aus


def _log_dominanz_push(pkey, pos, scores, anteil, broad, ts) -> None:
    """Eine gesendete Dominanz-Beobachtung buchen — dieselbe Form wie der Whale-Ledger, damit
    `poly_public_eval.settle()` sie ohne Sonderfall abrechnen kann. Ein Eintrag je posKey."""
    led = _load(DOM_LEDGER_FILE, [])
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
        "walletRank": rank, "sentAt": ts, "status": "pending",
        **markt_stempel(pos, broad),
        # 11.09.2026: WIE die Zeile freigegeben wurde, gehoert ins Buch. Eine frueh freigegebene
        # Zeile hat einen geschaetzten Nenner (Fuellgrad-Median), eine reife einen gemessenen.
        # Ungetrennt liesse sich spaeter nicht sagen, ob eine Trefferquote von den einen oder
        # den anderen kommt — und der Fuellgrad ist ein Median, kein Versprechen.
        **_dom_freigabe_stempel(pos, broad),
        # Aus welcher Spur die Zeile kommt. Die Kleinmarkt-Spur kennt den Einstieg des Wals
        # nicht und hat einen anderen Marktgroessen-Bereich — zusammengerechnet waeren es zwei
        # Dinge unter einer Trefferquote.
        "quelle": pos.get("quelle") or "track",
    })
    try:
        _save(DOM_LEDGER_FILE, led[-DOM_LEDGER_KEEP:])
    except Exception as e:
        print("Dominanz-Ledger-Schreibfehler:", e)


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


# Polymarket schreibt die Linie als „…: O/U 3.5", nie als „over 3.5". Gemessen am 05.09.2026:
# von 344 Maerkten mit rein generischen Ausgaengen tragen 42 eine Marktfrage — und die alte
# Regex (\bover\s*3.5) griff bei **0 von 42**. Sie fiel also IMMER auf „gib die ganze Frage
# zurueck" durch, und der Aufrufer ERSETZTE damit die Seite. Auf der Karte stand deshalb
# „$32.7K auf Manchester City FC vs. Coventry City FC: O/U 3.5" — Linie sichtbar, Seite weg.
_LINIE = _re.compile(
    r"(?:\bo\s*/\s*u\b|\bover\s*/\s*under\b|\b(?:over|under|ueber|über)\b)"
    r"[^0-9]{0,12}(\d+(?:[.,]\d+)?)", _re.I)


_OU_SEITEN = {"over", "under", "ueber", "über", "unter"}


def _linie_zahl(frage):
    """Die Linie aus der Marktfrage — „3.5". None, wenn keine dasteht. REIN/testbar."""
    if not frage:
        return None
    m = _LINIE.search(str(frage))
    return m.group(1).replace(",", ".") if m else None


def _frage_kurz(frage, max_len=52):
    """Die Marktfrage ohne den Paarungs-Vorspann („A vs. B: X" -> „X"). REIN."""
    t = str(frage or "").strip()
    if ":" in t:
        t = t.split(":", 1)[1].strip() or t
    return t if len(t) <= max_len else t[:max_len - 1].rstrip() + "…"


def ausgang_label(side, frage):
    """Wie heisst der bespielte Ausgang auf der Karte? None = nicht benennbar.

    05.09.2026 (Lucas): „nun sieht man zwar line aber nicht welche Seite — Over oder Under".
    Die Seite wird nie mehr ersetzt, nur ergaenzt. Ein nacktes „Over" bleibt verboten (der
    Leeds-Brentford-Fall), aber die Antwort darauf ist „Over 3.5", nicht die ganze Frage.
    """
    s = str(side or "").strip()
    if not s:
        return None
    if s.lower() not in _PUB_GENERISCH:
        return s
    if not frage:
        return None                      # generischer Ausgang ohne Frage: nicht benennbar
    # Die Linie gehoert NUR an eine Over/Under-Seite. „Yes 3.5" waere Unsinn — und genau die
    # Sorte Beinahe-Richtigkeit, die den Leeds-Brentford-Fall verursacht hat.
    if s.lower() in _OU_SEITEN:
        z = _linie_zahl(frage)
        if z:
            return "%s %s" % (s, z)
    return "%s — %s" % (s, _frage_kurz(frage))


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
            _log_public_push(pkey, pos, scores, restock, now_iso, broad)
    _save(PUB_SEEN_FILE, pub_seen)
    print(f"  🐋 Public-Whale: {len(pub_cand)} Kandidat(en), {pub_sent} gesendet.")

    # ── Marktdominanz: das Beobachtungsband in den TRADES-Kanal (11.09.2026) ────────────────
    # Eigener Dedup-Stand, eigenes Buch, eigener Kanal-Platz. Bewusst NACH dem Whale-Block und
    # mit eigenem `seen`: eine Position, die schon als Whale rausging, soll nicht ein zweites
    # Mal als Dominanz kommen — deshalb steht der Public-Dedup-Stand mit in der Sperre.
    dom_seen = _load(DOM_SEEN_FILE, {})
    if not isinstance(dom_seen, dict):
        dom_seen = {}
    klein = _load(DOM_KLEIN_FILE, {})     # 11.09.2026: Maerkte unter $7.500 — s. DOM_KLEIN_FILE
    if not isinstance(klein, dict):
        klein = {}
    dom_cand = dominanz_kandidaten(track, broad, seen=dom_sperre(dom_seen, seen, pub_seen),
                                   now=now, klein=klein, blocked=_blocked)
    # Dieselbe Marktsicht wie die Auswahl — sonst baut die Karte einen Markt, den die Auswahl
    # nicht gemeint hat, und die Kleinmarkt-Zeilen rendern mit leeren Feldern.
    dom_sicht = getattr(dominanz_kandidaten, "sicht", broad)
    # 12.09.2026: Der Whale-Block darueber laeuft seit jeher ueber `cand[:MAX_ALERTS]`, die
    # Dominanz-Schleife nicht — `DOM_MAX_ALERTS` begrenzte nur die AUSWAHL in
    # `dominanz_kandidaten` (Z. 1359). Steht dort einmal eine laengere Liste (neuer Datenstand,
    # zurueckgesetzter Dedup), sendet diese Schleife sie ganz. Deckel drum.
    dom_send = PD.Deckel(tg_send, DOM_MAX_ALERTS, "Markt-Dominanz")
    dom_sent = 0
    for pkey, pos, anteil in dom_cand:
        if dom_send(build_dominanz_card(pos, scores, dom_sicht, anteil, now)):
            dom_sent += 1
            dom_seen[pkey] = {"usd": float(pos.get("usd") or 0), "anteil": round(anteil, 4),
                              "ts": now_iso}
            _log_dominanz_push(pkey, pos, scores, anteil, dom_sicht, now_iso)
    _save(DOM_SEEN_FILE, dom_seen)
    print("  " + dom_send.bericht())
    print(f"  🔬 Kleinmarkt-Spur: {len(klein)} Maerkte unter ${int(DOM_MIN_MARKET)}")
    print(f"  🎯 Markt-Dominanz: {len(dom_cand)} Kandidat(en), {dom_sent} gesendet "
          f"(ab ${int(DOM_MIN_USD)} und {int(DOM_MIN_SHARE*100)} % Anteil).")


if __name__ == "__main__":
    main()
