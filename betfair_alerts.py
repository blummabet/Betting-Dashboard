#!/usr/bin/env python3
"""
betfair_alerts.py — Telegram-Pushes (Trades-Channel) für Betfair-Signale (29.07.2026, Lucas).

Testweise, 2 Szenarien (erweiterbar, sobald wir mehr gelernt haben):
  1. Halbzeit-Geld (30.07.2026 tier-aware, egal ob HZ-1X2 ODER Über/Unter 1,5 erste HZ): ein HZ-Markt
     hat ≥ Schwelle gematcht (Top/Int. 10K · Rest 5K) UND davon liegen ≥ HT_MIN_SHARE (85 %) auf EINEM
     Ausgang (sonst kein Signal, nur Liquidität). Es zählt der HZ-Markt mit dem meisten Geld.
  2. Frisches Geld: Zufluss auf dem GRÖSSTEN Zufluss-Markt (aus mkv) ≥ Schwelle (Top 30K / Rest 20K)
     — pro Markt, NICHT Spiel-Gesamt (sonst spiegelt die Zahl alle Märkte statt des einen Marktes).

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

HT_TOP_EUR     = 10000.0  # Halbzeit-Geld-Schwelle Top-Liga + International (Lucas 30.07.2026)
HT_REST_EUR    = 5000.0   # ... und Rest-Ligen
HT_MIN_SHARE   = 0.85     # ... und davon min. dieser Anteil auf EINEN Ausgang (einseitig)
MIN_LEAD_ODD   = 1.30     # Geld auf einen Favoriten mit Quote < 1.30 (führt schon, wenig Value) = kein Push (Lucas 30.07.2026, vorher 1.15)
FRESH_TOP_EUR  = 30000.0  # frisches Geld Top-Liga
FRESH_REST_EUR = 20000.0  # ... und Rest-Ligen
DEDUP_FACTOR   = 1.5
SEEN_FILE      = "betfair_alerts_seen.json"
HT_MARKETS     = ("Half Time", "First Half Goals 1.5")   # HZ-1X2 ODER Über/Unter 1,5 erste Halbzeit
HT_LABEL       = {"Half Time": "HZ-1X2", "First Half Goals 1.5": "HZ Ü/U 1.5", "First Half Goals 0.5": "HZ Ü/U 0.5"}

UEFA_RX  = re.compile(r"(champions league|europa league|europa conference|conference league|uefa)", re.I)
TOP5_RX  = re.compile(r"(german bundesliga|english premier league|spanish la ?liga|italian serie a|french ligue 1|\bmls\b|major league soccer)", re.I)
TOP5_NEG = re.compile(r"(summer series|friendl|reserve|women|u1[0-9]\b|youth|amateur)", re.I)


def is_top5(league) -> bool:
    l = str(league or "")
    return bool(TOP5_RX.search(l)) and not TOP5_NEG.search(l)


def _is_intl_country(cc) -> bool:
    return bool(re.match(r"^(int|international|eu|europe)$", str(cc or ""), re.I))


def tier_of(m) -> str:
    # Top-Tier = Top-5 + MLS UND internationale Bewerbe (UEFA/Länderspiele) — Lucas 30.07.2026:
    # „internationale Bewerbe verhalten sich wie Top". Alles andere = Rest.
    if is_top5(m.get("league")):
        return "top"
    if UEFA_RX.search(str(m.get("league") or "")) or _is_intl_country(m.get("country")):
        return "top"
    return "rest"


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


def _ht_label(name, home, away):
    n = str(name or "")
    if n == "The Draw":
        return "Remis (X)"
    if n == home:
        return "%s (Heim)" % home
    if n == away:
        return "%s (Ausw.)" % away
    return n


def _ht_thr(m) -> float:
    return HT_TOP_EUR if tier_of(m) == "top" else HT_REST_EUR


def _ht_one(m, market_name):
    """Ein einzelner HZ-Markt (HZ-1X2 oder Über/Unter 1,5 HZ1): ≥ tier-Schwelle UND ≥85 % einseitig."""
    mk = (m.get("markets") or {}).get(market_name)
    if not mk:
        return None
    total = _vol(mk)
    if total <= 0 or total < _ht_thr(m):
        return None
    runners = mk.get("runners") or []
    lead = max(runners, key=lambda r: (r.get("vol") or 0.0), default=None)
    if not lead:
        return None
    lead_share = (lead.get("vol") or 0.0) / total
    if lead_share < HT_MIN_SHARE:          # ≥85 % auf einer Seite, sonst nur Liquidität → kein Push
        return None
    lo = lead.get("odd")
    if isinstance(lo, (int, float)) and lo < MIN_LEAD_ODD:   # 85 % auf einem ~1.0-Favoriten = keine Info
        return None
    home, away = m.get("home"), m.get("away")
    is_x2 = market_name == "Half Time"

    def share(test):
        for r in runners:
            if test(str(r.get("name") or "")):
                return (r.get("vol") or 0.0) / total
        return None

    return {"scenario": "ht", "matchId": str(m.get("matchId")), "value": total,
            "home": home, "away": away, "league": m.get("league"), "flag": _flag(m),
            "market": market_name, "mktLabel": HT_LABEL.get(market_name, _short_mk(market_name)), "isX2": is_x2,
            "total": total, "hs": share(lambda s: s == home),
            "ds": share(lambda s: s == "The Draw"), "as_": share(lambda s: s == away),
            "leadName": lead.get("name"), "leadLabel": _ht_label(lead.get("name"), home, away),
            "leadShare": lead_share, "leadOdd": lead.get("odd")}


def ht_alert(m):
    """Szenario 1: bester HZ-Markt (HZ-1X2 ODER Über/Unter 1,5 erste HZ) über tier-Schwelle + einseitig."""
    best = None
    for name in HT_MARKETS:
        a = _ht_one(m, name)
        if a and (best is None or a["total"] > best["total"]):
            best = a
    return best


def _market_lead(m, name):
    """Führender Ausgang + Anteil des Marktes aus den aktuellen Preisen."""
    mk = (m.get("markets") or {}).get(name)
    if not mk:
        return None, None, None
    rs = mk.get("runners") or []
    tot = sum((r.get("vol") or 0.0) for r in rs)
    if tot <= 0 or not rs:
        return None, None, None
    top = max(rs, key=lambda r: (r.get("vol") or 0.0))
    return top.get("name"), (top.get("vol") or 0.0) / tot, top.get("odd")


def fresh_alert(m, hist):
    """Szenario 2: Zufluss auf dem GRÖSSTEN Zufluss-Markt (aus mkv) ≥ tier-Schwelle — pro Markt."""
    pts = (hist or {}).get(str(m.get("matchId")))
    if not isinstance(pts, list) or len(pts) < 2:
        return None
    pmk, lmk = pts[-2].get("mkv"), pts[-1].get("mkv")
    if not isinstance(pmk, dict) or not isinstance(lmk, dict):
        return None   # ohne per-Markt-History (mkv) kein per-Markt-Signal — irreführende Gesamt-Zahl vermeiden
    thr = FRESH_TOP_EUR if tier_of(m) == "top" else FRESH_REST_EUR
    best = None                                   # (Marktname, Zufluss, aktuelles Markt-Volumen)
    for name, lv in lmk.items():
        inflow = (lv or 0.0) - (pmk.get(name) or 0.0)
        if best is None or inflow > best[1]:
            best = (name, inflow, lv or 0.0)
    if not best or best[1] < thr:
        return None
    market_name, inflow, mkt_total = best
    lead_name, lead_share, lead_odd = _market_lead(m, market_name)
    if isinstance(lead_odd, (int, float)) and lead_odd < MIN_LEAD_ODD:   # Geld auf ~1.0-Favoriten = sinnlos
        return None
    return {"scenario": "fresh", "matchId": str(m.get("matchId")), "value": mkt_total,
            "home": m.get("home"), "away": m.get("away"), "league": m.get("league"), "flag": _flag(m),
            "market": market_name, "inflow": inflow, "total": mkt_total, "tier": tier_of(m),
            "leadName": lead_name, "leadShare": lead_share, "leadOdd": lead_odd}


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
        odd = (" @%.2f" % a["leadOdd"]) if isinstance(a.get("leadOdd"), (int, float)) else ""
        lbl = a.get("mktLabel") or "HZ"
        msg = ("🟡 <b>Betfair · Halbzeit-Geld (einseitig)</b>\n" + head
               + "💷 %s: <b>%s</b> gematcht · <b>%.0f%%</b> auf %s%s"
                 % (_esc(lbl), _euro(a["total"]), a["leadShare"] * 100, _esc(a["leadLabel"]), odd))
        if a.get("isX2"):
            pct = lambda x: "—" if x is None else "%.0f%%" % (x * 100)
            msg += ("\n%s %s · X %s · %s %s" % (_esc(a["home"]), pct(a["hs"]), pct(a["ds"]),
                                                _esc(a["away"]), pct(a["as_"])))
        return msg
    tl = "Top-Liga" if a["tier"] == "top" else "Rest-Liga"
    msg = ("🟡 <b>Betfair · Frisches Geld</b> · %s\n" % tl + head
           + "💶 <b>%s</b>: +<b>%s</b> frisch → jetzt <b>%s</b>"
             % (_esc(_short_mk(a["market"])), _euro(a["inflow"]), _euro(a["total"])))
    if a.get("leadName"):
        odd = (" @%.2f" % a["leadOdd"]) if isinstance(a.get("leadOdd"), (int, float)) else ""
        msg += "\nführt: %s (%.0f%%)%s" % (_esc(a["leadName"]), (a.get("leadShare") or 0.0) * 100, odd)
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
