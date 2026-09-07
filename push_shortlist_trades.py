#!/usr/bin/env python3
"""
push_shortlist_trades.py — 05.08.2026 (Lucas): die „Heute spielenswert"-Plays (die Shortlist ganz
oben im Screen) in den TRADES-Channel schicken, damit er die paar starken Plays immer mitkriegt.

Nutzt DENSELBEN Emitter wie der Paper-Tracker (scripts/emit_shortlist.mjs → echte poly-wallets.js-
Engine) → kein Drift zwischen Screen und Push. Dedup je Play (key|side): ein Play wird EINMAL
gepusht, erneut nur, wenn die Conviction steigt. Read-only auf die Daten, sendet nur Telegram.

Env:
  SHORTLIST_PUSH_MIN_CONV — Mindest-Conviction (Default 8 = „die klarsten")
  SHORTLIST_PUSH_MAX      — max Plays je Nachricht (Default 6)
  TELEGRAM_TOKEN + TELEGRAM_TRADES_CHAT_ID — ohne Token = Vorschau (stdout)
"""
from __future__ import annotations
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from telegram_trades import send_trades_message
from poly_shortlist_track import load_emit

BASE = Path(__file__).resolve().parent
SEEN_FILE = BASE / "shortlist_push_seen.json"

# 29.08.2026 (Lucas-Checkup, „D"): Default 8 → 7. Nicht weil die Latte sinken soll, sondern weil
# die Skala darunter weggerutscht ist: die Wallet-Neugewichtung nimmt gewichteten Plays rund einen
# Punkt. 8 auf der neuen Skala waere das alte 9 — also eine stille Verschaerfung, die niemand
# beschlossen hat. 7 haelt die Strenge, die vorher 8 war. Ueber SHORTLIST_PUSH_MIN_CONV weiter
# ueberschreibbar; zurueck auf die alte Zahl heisst: diese 7 wieder auf 8 setzen.
# 07.09.2026: 7 -> 6. Nicht als Lockerung — die Auswahl trifft ab jetzt das PUBLIC-TOR (s.
# select()), und dessen eigene Untergrenze ist 6. Bliebe hier 7 stehen, waere die Conviction
# heimlich das schaerfere Kriterium und das Tor haette nur die Haelfte seiner Wirkung.
MIN_CONV = int(os.environ.get("SHORTLIST_PUSH_MIN_CONV") or 6)
MAX_PLAYS = int(os.environ.get("SHORTLIST_PUSH_MAX") or 6)
MAX_PRICE = float(os.environ.get("SHORTLIST_PUSH_MAX_PRICE") or 0.92)   # Quasi-Locks raus (kein handelbarer Raum)
SEEN_TTL_DAYS = 3

_SPORT = {"TENNIS": "🎾", "ESPORTS": "🎮", "MLB": "⚾", "NBA": "🏀", "WNBA": "🏀",
          "NFL": "🏈", "NHL": "🏒", "MMA": "🥊", "UFC": "🥊", "GOLF": "⛳", "CRICKET": "🏏"}


def _icon(league) -> str:
    x = str(league or "").upper()
    if x in _SPORT:
        return _SPORT[x]
    if x.startswith("SOCCER") or any(t in x for t in ("LIGA", "MLS", "EPL", "UCL", "UEL", "BUNDES", "SERIE", "LIGUE", "EREDIV", "PRIMEIRA")):
        return "⚽"
    return "🎯"


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _cents(p) -> str:
    try:
        return "%d¢" % round(float(p) * 100)
    except (TypeError, ValueError):
        return ""


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def select(plays, blocked_cats=None):
    """Top-Plays der Shortlist: Conviction >= MIN_CONV, staerkste zuerst, gedeckelt. REIN/testbar.

    29.08.2026 (Lucas-Audit): die Sperrliste fehlte hier komplett. US-Sport und Kampfsport sind
    seit dem 24.08. vom Setzen und aus dem oeffentlichen Schaufenster ausgeschlossen — im
    Papier-Depot brachten sie ueber 78 Plays -29,6% ROI. Der Trades-Push zog sie trotzdem weiter,
    weil er `_pwTopPlays(0,false,false)` roh uebernahm. Die Kategorie steht seit dem 24.08. als
    `cat` an jedem Play und die Sperrliste als `blockedCats` im selben Emit — es wurde nur nie
    verglichen. Fehlt `cat` (aeltere Emits), bleibt der Play drin: nicht wissen ist kein Verbot,
    aber wir wissen es hier praktisch immer."""
    blocked = {str(c) for c in (blocked_cats or []) if c}

    def _ok_price(p):
        pr = p.get("price")
        return not (isinstance(pr, (int, float)) and pr >= MAX_PRICE)

    def _erlaubt(p):
        cat = p.get("cat")
        return not (cat and str(cat) in blocked)

    # 07.09.2026 (Lucas: „das haett ich gern dann halt auch als Push in den Trades Channel").
    #
    # Hier stand nur `conv >= MIN_CONV`. Damit war der Trades-Push eine VIERTE Menge — verschieden
    # von der Uebersichts-Kachel (Top 3 nach Score) und von den Public-Kandidaten (das Tor).
    # Nachgerechnet an 570 abgerechneten, spielbaren Plays:
    #
    #     Topf: alle spielbaren BET-Plays          n=570   63,3 %   +6,85 EUR    ROI +0,1 %
    #     Trades-Push bisher (conv>=7)             n=165   64,8 %   +42,86 EUR   ROI +2,6 %
    #     Public-Kandidaten (das Tor)              n=167   70,7 %   +107,22 EUR  ROI +6,4 %
    #
    # Praktisch dasselbe Volumen (7,5 gegen 8,0 Plays je Tag), zweieinhalbfacher Gewinn. Die
    # Conviction-Schwelle war eine Naeherung an „stark"; das Tor MISST es (Conviction >= 6 UND
    # Geld-Mehrheit >= 60 % UND bewiesene Wallet — bei E-Sport ab 55 Cent ohne die Wallet, weil
    # sie dort nachweislich nichts trennt).
    #
    # `public` steht seit dem 06.09. an jedem Play im selben Emit. MIN_CONV bleibt als zweite,
    # schwaechere Schranke stehen: das Tor beginnt bei 6, der Push soll nicht darunter rutschen,
    # falls jemand PW_PUBLIC_MIN_CONV senkt.
    _hat_flag = any(isinstance(p, dict) and "public" in p for p in (plays or []))

    def _tor(p):
        # Faellt das Feld (Alt-Emit), wird NICHT stillschweigend auf conv>=7 zurueckgefallen —
        # das waere die alte Menge unter neuem Namen. Dann pusht dieser Lauf lieber nichts und
        # sagt es (s. main). Fehlende Information ist keine Erlaubnis.
        return bool(p.get("public"))

    if not _hat_flag:
        return []
    out = [p for p in (plays or []) if isinstance(p, dict)
           and _tor(p) and (p.get("conv") or 0) >= MIN_CONV
           and p.get("verdict") in ("BET", "FADE")
           and _ok_price(p) and _erlaubt(p)]
    out.sort(key=lambda p: -(p.get("conv") or 0))
    return out[:MAX_PLAYS]


def fresh_plays(sel, seen):
    """NEU oder STAERKER geworden: pusht einen Play einmal und dann erneut nur, wenn seine Conviction
    seit dem letzten Push GESTIEGEN ist (05.08.2026, Lucas: „wenn 7->8 steigt, trotzdem schicken — im
    Trades-Chat stoert es nicht"). Kein Re-Push bei gleicher/niedrigerer Conviction -> kein 30-Min-Spam,
    aber echte Verstaerkung kommt durch. Nur neue Hoechststaende feuern (kein 8<->9-Flattern). REIN/testbar."""
    seen = seen if isinstance(seen, dict) else {}
    out = []
    for p in sel:
        k = "%s|%s" % (p.get("key"), p.get("side"))
        prev = seen.get(k)
        prev_conv = (prev.get("conv") if isinstance(prev, dict) else prev) or 0
        if prev is None or (p.get("conv") or 0) > prev_conv:
            out.append(p)
    return out


def _spielminute(htk):
    """Aus den Stunden bis Anpfiff die gelaufene Spielzeit. htk ist negativ, wenn angepfiffen."""
    if not isinstance(htk, (int, float)) or htk >= 0:
        return None
    return int(round(-htk * 60))


def _line(p) -> str:
    conv = p.get("conv") or 0
    # 03.09.2026 (Lucas): „nur da war das Spiel schon 3:0 und in der 92. Minute oder so".
    # Ein blosses „🔴 LIVE" sagt nicht, ob gerade angepfiffen wurde oder nachgespielt wird.
    # Die Minute steht jetzt dran — und wo der Preis herkommt auch, denn genau das war der
    # Fehler: die Zahlen jener Nachricht stammten aus dem Close-Satz VOR Anpfiff.
    _min = _spielminute(p.get("htk"))
    live = ""
    if _min is not None:
        live = " 🔴 <b>LIVE</b> · %d. Min" % _min
        if p.get("preisQuelle") and p["preisQuelle"] != "live":
            live += " <i>(Preis aus dem Vorspiel-Satz)</i>"
    match = _esc(p.get("match") or p.get("key") or "?")
    price = _cents(p.get("price"))
    price_txt = (" @%s" % price) if price else ""
    reasons = " · ".join(_esc(r) for r in (p.get("reasons") or [])[:2])
    head = "<b>%d/10 · %s</b> · %s %s%s" % (conv, _esc(p.get("verdict") or ""), _icon(p.get("league")), match, live)
    pick = "→ <b>%s</b>%s" % (_esc(p.get("side") or "?"), price_txt)
    return head + "\n   " + pick + (("\n   <i>%s</i>" % reasons) if reasons else "")


def build_message(plays) -> str:
    body = "\n\n".join(_line(p) for p in plays)
    return ("🔥 <b>Heute spielenswert</b> — die klarsten Plays\n\n"
            + body
            + "\n\nKein Auto-Bet — deine Watchlist von oben. Selbst prüfen.")


def main() -> int:
    print("=== push_shortlist_trades.py ===")
    emit = load_emit()
    if not emit:
        print("  ℹ️  kein Emit — Shortlist-Push uebersprungen (nicht fatal).")
        return 0
    _plays = emit.get("plays") or []
    if _plays and not any(isinstance(p, dict) and "public" in p for p in _plays):
        # Alt-Emit ohne das `public`-Feld. Auf conv>=MIN_CONV zurueckzufallen waere die ALTE
        # Menge unter neuem Namen — und niemand wuerde es merken. Lieber nichts senden und es
        # sagen: der naechste Emit hat das Feld wieder.
        print("  ⚠️  Emit ohne `public`-Feld — es wird NICHTS gepusht. Der Push haengt seit dem "
              "07.09. am Public-Tor, nicht mehr an der Conviction; ein stiller Rueckfall waere "
              "eine andere Auswahl unter demselben Namen.")
        return 0
    sel = select(_plays, emit.get("blockedCats"))
    if not sel:
        print("  ℹ️  kein Play durch das Public-Tor (Conviction >= %d, Geld-Mehrheit, Wallet "
              "bzw. E-Sport ab 55 Cent)." % MIN_CONV)
        return 0
    seen = _load(SEEN_FILE, {})
    if not isinstance(seen, dict):
        seen = {}
    fresh = fresh_plays(sel, seen)
    if not fresh:
        print("  ℹ️  nichts Neues — alle %d Top-Plays schon gepusht." % len(sel))
        return 0
    sent = False
    try:
        sent = bool(send_trades_message(build_message(fresh)))
    except Exception as exc:
        print("  ℹ️  Shortlist-Push uebersprungen:", exc)
    now_iso = _now().isoformat()
    # alle aktuellen Top-Plays als „gesehen" markieren (auch die nicht-frischen → frischer ts, kein Re-Push)
    for p in sel:
        seen["%s|%s" % (p.get("key"), p.get("side"))] = {"conv": p.get("conv") or 0, "ts": now_iso}
    cutoff = _now().timestamp() - SEEN_TTL_DAYS * 86400
    seen = {k: v for k, v in seen.items()
            if not (isinstance(v, dict) and _parse(v.get("ts")) and _parse(v.get("ts")) < cutoff)}
    _save(SEEN_FILE, seen)
    print("  🔥 Shortlist-Push: %d neue Play(s) %s." % (len(fresh), "gesendet" if sent else "(Vorschau)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
