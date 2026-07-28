#!/usr/bin/env python3
"""
poly_cross_sport_watch.py — Cross-Sport-Edge-Alert (Telegram Trades-Channel)
================================================================================
28.07.2026 (Lucas: „cross sport … als telegram alert"). Geschwister zu poly_whale_watch.py,
aber ein GANZ anderes Signal: nicht „wer setzt", sondern „wo liegt Polymarket messbar neben
der SCHARFEN Pinnacle" — über alle Sportarten.

## Warum das das einzige echte Preis-Edge-Signal ist
Auf Polymarket IST der Preis die Geldverteilung → „der Masse folgen" hat keinen Edge. Hier
stellen wir Poly gegen ein SCHARFES Buch (de-viggte Pinnacle). Eine Lücke allein ist aber noch
kein Edge — sie kann ein Regel-/Settlement-Artefakt sein. Der Beweis ist die KONVERGENZ: schließt
sich die Lücke über die Tage (Poly läuft zur Pinnacle), war sie echt. Genau darauf alertet dieser
Service — NICHT auf rohe Lücken. Erst messen, dann melden.

## Quelle
poly_cross_sport.json (vom Mac-Runner, poly_cross_sport.py):
  discrepancies: [{id, sport, event, market, outcome, polyPP, pinnPP, gapPP, vol, richtung,
                   convergePP, firstSeen}]
  · convergePP  > 0  → Lücke schrumpft (echt)   · = None → erst einmal gesehen (noch kein Urteil)

## Ausgabe
Ein HTML-Post je konvergierender Edge in den Trades-Channel (TELEGRAM_TRADES_CHAT_ID).

## Env
  TELEGRAM_TOKEN / TELEGRAM_TRADES_CHAT_ID  — ohne Token = Vorschau (stdout)
  XSPORT_MIN_GAP        — Mindest-Lücke in pp (Default 7)
  XSPORT_MIN_CONVERGE   — Mindest-Konvergenz in pp: nur schrumpfende Lücken (Default 1.0)
  XSPORT_MIN_VOL        — Mindest-Poly-Volumen USD (Default 20000)
  XSPORT_MAX_ALERTS     — max Alerts je Lauf (Default 6)
  XSPORT_RECONVERGE     — erneuter Alert erst, wenn die Lücke seit dem letzten um ≥N pp WEITER
                          geschlossen hat (Default 2.0) → keine Wiederholung derselben Edge

## Dedup
poly_cross_sport_seen.json {id → {gapPP, convergePP, ts}}: je Edge EINMAL alerten; erneut nur,
wenn die Konvergenz seit dem letzten Alert um ≥ XSPORT_RECONVERGE pp gewachsen ist (Edge festigt sich).
"""
import json, os, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "poly_cross_sport.json"
SEEN_FILE = BASE / "poly_cross_sport_seen.json"
LOG_FILE  = BASE / "telegram-log.json"

TELEGRAM_TOKEN = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
CHAT_ID        = (os.environ.get("TELEGRAM_TRADES_CHAT_ID") or "").strip()

MIN_GAP      = float(os.environ.get("XSPORT_MIN_GAP")      or 7)
MIN_CONVERGE = float(os.environ.get("XSPORT_MIN_CONVERGE") or 1.0)
MIN_VOL      = float(os.environ.get("XSPORT_MIN_VOL")      or 20000)
MAX_ALERTS   = int(os.environ.get("XSPORT_MAX_ALERTS")     or 6)
RECONVERGE   = float(os.environ.get("XSPORT_RECONVERGE")   or 2.0)

# TheOddsAPI-Sport-Key (z.B. "soccer_mls", "basketball_nba") → (Emoji, Klartext). Substring-Match.
_SPORT_ICON = [
    ("soccer", ("⚽", "Fußball")), ("basketball", ("🏀", "Basketball")),
    ("americanfootball", ("🏈", "Football")), ("baseball", ("⚾", "Baseball")),
    ("icehockey", ("🏒", "Eishockey")), ("mma", ("🥊", "MMA")), ("boxing", ("🥊", "Boxen")),
    ("tennis", ("🎾", "Tennis")), ("cricket", ("🏏", "Cricket")), ("golf", ("⛳", "Golf")),
    ("esports", ("🎮", "E-Sport")), ("rugby", ("🏉", "Rugby")),
]


def _sport(sport_key: str):
    s = str(sport_key or "").lower()
    for frag, val in _SPORT_ICON:
        if frag in s:
            return val
    return ("🎯", (sport_key or "Sport").split("_")[-1].upper())


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


def _usd(v):
    try:
        n = float(v)
    except Exception:
        return "$0"
    if n >= 1e6:
        return f"${n/1e6:.2f}M"
    if n >= 1e3:
        return f"${n/1e3:.1f}K".replace(".0K", "K")
    return f"${round(n)}"


def build_card(d: dict) -> str:
    emoji, sport = _sport(d.get("sport"))
    gap = d.get("gapPP")
    conv = d.get("convergePP")
    ev = d.get("event") or d.get("id") or "?"
    outcome = d.get("outcome") or ""
    gap_txt = f"+{gap}" if isinstance(gap, (int, float)) and gap > 0 else f"{gap}"
    lines = [
        f"⚖️ <b>Cross-Sport-Edge</b> · {emoji} {sport}",
        f"<b>{ev}</b>" + (f" — {outcome}" if outcome else ""),
        f"Poly <b>{d.get('polyPP')}%</b> vs faire Pinnacle <b>{d.get('pinnPP')}%</b>",
        f"Lücke <b>{gap_txt}pp</b> → {d.get('richtung') or ''}",
    ]
    if isinstance(conv, (int, float)):
        lines.append(f"✅ <b>Lücke schließt sich</b>: −{conv:.1f}pp seit erster Sichtung "
                     f"(läuft zur Pinnacle → echt, kein Artefakt)")
    lines.append(f"💧 Volumen {_usd(d.get('vol'))}")
    lines.append("\n🤖 CocoBet Cross-Sport · kein Auto-Bet, ein Ausgangspunkt")
    return "\n".join(lines)


# ── Telegram ────────────────────────────────────────────────────────────────────
def tg_send(text: str) -> bool:
    if not TELEGRAM_TOKEN:
        print("⚠️  Kein TELEGRAM_TOKEN — Vorschau:")
        print(text)
        print()
        return True
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
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
        if not isinstance(log, list):
            log = []
        entry = {"type": "poly_cross_sport",
                 "sentAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "preview": preview[:160], "chatId": CHAT_ID}
        entry.update(meta or {})
        log.append(entry)
        log = log[-200:]
        _save(LOG_FILE, log)
    except Exception:
        pass


# ── Auswahl ─────────────────────────────────────────────────────────────────────
def select(data: dict, seen: dict, now: datetime):
    """Liefert die Liste alertwürdiger Cross-Sport-Edges. REIN/testbar.

    Alertwürdig = Lücke ≥ MIN_GAP · Volumen ≥ MIN_VOL · UND KONVERGENZ ≥ MIN_CONVERGE (die Lücke
    schließt sich → echt). Frisch-„neu" (convergePP None) wird bewusst NICHT gemeldet — ohne ein
    zweites Sehen ist die Lücke nicht bewertbar. Dedup: je id einmal; erneut nur, wenn die
    Konvergenz seit dem letzten Alert um ≥ RECONVERGE pp gewachsen ist."""
    disc = (data or {}).get("discrepancies") or []
    seen = seen or {}
    out = []
    for d in disc:
        if not isinstance(d, dict):
            continue
        gap = d.get("gapPP")
        conv = d.get("convergePP")
        vol = d.get("vol")
        if not isinstance(gap, (int, float)) or abs(gap) < MIN_GAP:
            continue
        if not isinstance(conv, (int, float)) or conv < MIN_CONVERGE:
            continue                      # nur schließende Lücken (echt), keine rohen/stehenden
        try:
            if float(vol) < MIN_VOL:
                continue
        except (TypeError, ValueError):
            continue
        prev = seen.get(d.get("id"))
        if prev is not None:
            prev_conv = prev.get("convergePP")
            if isinstance(prev_conv, (int, float)) and (conv - prev_conv) < RECONVERGE:
                continue                  # schon gemeldet, nicht wesentlich weiter geschlossen
        out.append(d)
    out.sort(key=lambda d: (-(d.get("convergePP") or 0), -abs(d.get("gapPP") or 0)))
    return out


def main():
    print("=== poly_cross_sport_watch.py ===")
    data = _load(DATA_FILE, {})
    disc = (data or {}).get("discrepancies") or []
    if not disc:
        print(f"  ℹ️  Keine Diskrepanzen in {DATA_FILE.name} — nichts zu tun.")
        return
    seen = _load(SEEN_FILE, {})
    now = datetime.now(timezone.utc)

    cand = select(data, seen, now)
    print(f"  {len(cand)} konvergierende Edge(s) ≥{int(MIN_GAP)}pp Lücke, ≥{MIN_CONVERGE}pp Konvergenz, "
          f"≥{_usd(MIN_VOL)} Vol")

    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sent = 0
    for d in cand[:MAX_ALERTS]:
        card = build_card(d)
        if tg_send(card):
            sent += 1
            seen[d.get("id")] = {"gapPP": d.get("gapPP"), "convergePP": d.get("convergePP"), "ts": now_iso}
            _log_send(card.split("\n")[1] if "\n" in card else card,
                      {"id": d.get("id"), "gapPP": d.get("gapPP"), "sport": d.get("sport")})
    _save(SEEN_FILE, seen)
    print(f"  ✅  {sent} Cross-Sport-Alert(s) gesendet.")


if __name__ == "__main__":
    main()
