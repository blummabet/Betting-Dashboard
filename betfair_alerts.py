#!/usr/bin/env python3
"""
betfair_alerts.py — Telegram-Pushes (Trades-Channel) für Betfair-Signale (29.07.2026, Lucas).

Testweise, 2 Szenarien (erweiterbar, sobald wir mehr gelernt haben):
  1. Halbzeit-1X2-Geld: der „Half Time"-Markt (HZ 1X2) hat ≥ HT_MIN_EUR gematcht.
  2. Frisches Geld: Zufluss seit dem letzten Snapshot ≥ Schwelle (Top-Liga 20K / Rest 10K).

Anti-Spam (Lucas: „einmal, dann nur bei deutlicher Steigerung"): pro Spiel+Szenario wird der
Wert beim letzten Push in betfair_alerts_seen.json gemerkt; erneut gepusht wird erst, wenn der
Wert um ≥ DEDUP_FACTOR (×1.5 = +50 %) gestiegen ist.

Läuft im betfair.yml-Workflow direkt nach dem Fetch (Mac-Runner, alle 15 Min).
Env: TELEGRAM_TOKEN + TELEGRAM_TRADES_CHAT_ID (privater Trades-Channel).
"""
from __future__ import annotations
import json
import os
import re
import html

from telegram_trades import send_trades_message

HT_MIN_EUR     = 7000.0
FRESH_TOP_EUR  = 20000.0
FRESH_REST_EUR = 10000.0
DEDUP_FACTOR   = 1.5
SEEN_FILE      = "betfair_alerts_seen.json"

UEFA_RX  = re.compile(r"(champions league|europa league|europa conference|conference league|uefa)", re.I)
TOP5_RX  = re.compile(r"(german bundesliga|english premier league|spanish la ?liga|italian serie a|french ligue 1|\bmls\b|major league soccer)", re.I)
TOP5_NEG = re.compile(r"(summer series|friendl|reserve|women|u1[0-9]\b|youth|amateur)", re.I)


def is_top5(league) -> bool:
    l = str(league or "")
    return bool(TOP5_RX.search(l)) and not TOP5_NEG.search(l)


def tier_of(m) -> str:
    # Top-Liga = Top-5 + MLS (20K-Schwelle). Alles andere inkl. UEFA = Rest (10K). (Lucas-Vorgabe.)
    return "top" if is_top5(m.get("league")) else "rest"


def _vol(mk) -> float:
    return sum((r.get("vol") or 0.0) for r in (mk.get("runners") or []))


def _euro(v) -> str:
    v = float(v or 0)
    if v >= 1e6: return "€%.2fM" % (v / 1e6)
    if v >= 1e3: return "€%.1fK" % (v / 1e3)
    return "€%d" % round(v)


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _flag(m) -> str:
    if UEFA_RX.search(str(m.get("league") or "")):
        return "🇪🇺"
    cc = str(m.get("country") or "").upper()
    if len(cc) == 2 and cc.isalpha():
        try:
            return chr(0x1F1E6 + ord(cc[0]) - 65) + chr(0x1F1E6 + ord(cc[1]) - 65)
        except Exception:
            return "🌍"
    return "🌍"


def _short_mk(k) -> str:
    return (str(k).replace("Over/Under", "Ü/U").replace(" Goals", "")
            .replace("Both teams to Score?", "BTTS").replace("Match Odds", "1X2")
            .replace("First Half", "HZ1").replace("Half Time/Full Time", "HZ/EZ")
            .replace("Half Time", "HZ1 1X2").replace("Correct Score", "Exakt")
            .replace("Draw no Bet", "DNB"))


def ht_alert(m):
    """Szenario 1: Half-Time-1X2-Markt ≥ HT_MIN_EUR."""
    mk = (m.get("markets") or {}).get("Half Time")
    if not mk:
        return None
    total = _vol(mk)
    if total < HT_MIN_EUR:
        return None
    home, away = m.get("home"), m.get("away")
    runners = mk.get("runners") or []

    def share(test):
        for r in runners:
            if test(str(r.get("name") or "")):
                return (r.get("vol") or 0.0) / total if total else None
        return None

    return {"scenario": "ht", "matchId": str(m.get("matchId")), "value": total,
            "home": home, "away": away, "league": m.get("league"), "flag": _flag(m),
            "total": total, "hs": share(lambda s: s == home),
            "ds": share(lambda s: s == "The Draw"), "as_": share(lambda s: s == away)}


def fresh_alert(m, hist):
    """Szenario 2: Zufluss seit letztem Snapshot ≥ tier-Schwelle."""
    pts = (hist or {}).get(str(m.get("matchId")))
    if not isinstance(pts, list) or len(pts) < 2:
        return None
    fv, lv = pts[-2].get("totalVol"), pts[-1].get("totalVol")
    if fv is None or lv is None:
        return None
    inflow = lv - fv
    thr = FRESH_TOP_EUR if tier_of(m) == "top" else FRESH_REST_EUR
    if inflow < thr:
        return None
    best = None
    for name, mk in (m.get("markets") or {}).items():
        v = _vol(mk)
        if best is None or v > best[1]:
            best = (name, v, mk)
    lead = ""
    if best and best[1] > 0:
        rs = best[2].get("runners") or []
        top_r = max(rs, key=lambda r: (r.get("vol") or 0), default=None)
        if top_r:
            lead = "%s → %s (%.0f%%)" % (_short_mk(best[0]), top_r.get("name"),
                                         (top_r.get("vol") or 0) / best[1] * 100)
    return {"scenario": "fresh", "matchId": str(m.get("matchId")), "value": lv,
            "home": m.get("home"), "away": m.get("away"), "league": m.get("league"),
            "flag": _flag(m), "inflow": inflow, "total": lv, "tier": tier_of(m), "lead": lead}


def should_send(seen: dict, key: str, value: float) -> bool:
    prev = seen.get(key)
    if prev is None:
        return True
    try:
        return value >= prev * DEDUP_FACTOR
    except Exception:
        return True


def build_message(a) -> str:
    head = ("%s <b>%s</b> v <b>%s</b>\n<i>%s</i>\n"
            % (a["flag"], _esc(a["home"]), _esc(a["away"]), _esc(str(a["league"])[:48])))
    if a["scenario"] == "ht":
        pct = lambda x: "—" if x is None else "%.0f%%" % (x * 100)
        return ("🟡 <b>Betfair · Halbzeit-Geld</b>\n" + head
                + "💷 HZ-1X2: <b>%s</b> gematcht\n" % _euro(a["total"])
                + "%s %s · X %s · %s %s" % (_esc(a["home"]), pct(a["hs"]), pct(a["ds"]),
                                            _esc(a["away"]), pct(a["as_"])))
    tl = "Top-Liga" if a["tier"] == "top" else "Rest-Liga"
    msg = ("🟡 <b>Betfair · Frisches Geld</b> · %s\n" % tl + head
           + "💶 <b>+%s</b> seit letztem Update (jetzt %s)" % (_euro(a["inflow"]), _euro(a["total"])))
    if a["lead"]:
        msg += "\nmeistes Geld: %s" % _esc(a["lead"])
    return msg


def collect_alerts(prices: dict, hist: dict) -> list:
    out = []
    for m in (prices.get("matches") or []):
        a = ht_alert(m)
        if a:
            out.append(a)
        f = fresh_alert(m, hist)
        if f:
            out.append(f)
    return out


def main():
    try:
        prices = json.load(open("betfair_prices.json", encoding="utf-8"))
    except Exception as e:
        print("betfair_prices.json fehlt/kaputt:", e)
        return
    try:
        hist = json.load(open("betfair_history.json", encoding="utf-8"))
    except Exception:
        hist = {}
    try:
        seen = json.load(open(SEEN_FILE, encoding="utf-8"))
    except Exception:
        seen = {}

    alerts = collect_alerts(prices, hist)
    sent = 0
    for a in alerts:
        key = a["scenario"] + ":" + a["matchId"]
        if should_send(seen, key, a["value"]):
            if send_trades_message(build_message(a)):
                seen[key] = a["value"]     # nur bei Erfolg merken (Preview/Fehler → nächster Lauf retry)
                sent += 1
    try:
        json.dump(seen, open(SEEN_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    except Exception as e:
        print("konnte Seen-State nicht schreiben:", e)
    print("Betfair-Alerts: %d Kandidaten, %d gesendet" % (len(alerts), sent))


if __name__ == "__main__":
    main()
