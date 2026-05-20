#!/usr/bin/env python3
"""
telegram_wm.py — CocoBet WM 2026 Telegram Publisher

Postet täglich eine Morning-Card mit den WM-Picks für heute.
Läuft als GitHub Action jeden Morgen (ab 1. Juni 2026).

Format:
  🌍 WM 2026 — Heute · N Spiele
  ━━ GRUPPE X · SPIELTAG N ━━
  🔥 UPSET ALERT (wenn Elo-Gap klein)
  🏠 Team A vs 🌍 Team B · Zeit · Venue
  🎯 BET: Markt @Odds → +Xpp Edge | Modell: Y% vs. Markt: Z%
  ⚖️ ABWÄGEN: Markt @Odds (+Xpp)
  📈 WM-Bilanz: W-L-P | ROI: X%

Umgebungsvariablen:
  TELEGRAM_TOKEN     — Bot-Token
  TELEGRAM_CHAT_ID   — Channel-ID (Standard: CocoBet)
  TG_WM_MODE         — 'morning' | 'recap' | 'all' (Standard: 'morning')
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID", "-1003819239615")
TG_WM_MODE     = os.environ.get("TG_WM_MODE", "morning")

WM_FILE        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wm2026-data.json")
LOG_FILE       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram-log.json")

# Minimaler Edge für Pick-Aufnahme im Telegram
MIN_BET_EDGE   = 4   # pp
MIN_ABW_EDGE   = 4   # pp

# ── Telegram API ───────────────────────────────────────────────────────────────
def _log_send(type_: str, preview: str, meta: dict = None):
    """Append a send event to telegram-log.json (max 200 entries)."""
    try:
        existing = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, encoding="utf-8") as f:
                existing = json.load(f)
        entry = {
            "type":    type_,
            "sentAt":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "preview": preview[:160],
            "chatId":  CHAT_ID,
        }
        if meta:
            entry.update(meta)
        existing.append(entry)
        existing = existing[-200:]
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  ⚠️  Log failed: {e}")


def tg_send(text: str) -> bool:
    if not TELEGRAM_TOKEN:
        print("⚠️  Kein TELEGRAM_TOKEN — Vorschau:")
        print(text)
        print()
        return True  # Preview-Modus gilt als OK
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id":    CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
    }).encode("utf-8")
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


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────
def pct(odds: float | None) -> str:
    """Odds → implied probability als String '42%'."""
    if not odds or odds <= 0:
        return "?"
    return f"{round(100 / odds)}%"

def model_pct(model_odds: float | None) -> str:
    """Modell-Odds → Wahrscheinlichkeit als String."""
    if not model_odds or model_odds <= 0:
        return "?"
    return f"{round(100 / model_odds)}%"

def upset_label(score: int) -> str:
    if score >= 8: return "🔥🔥 GROSSER UPSET MÖGLICH"
    if score >= 6: return "🔥 UPSET ALERT"
    if score >= 4: return "⚠️ Ausgeglichenes Spiel"
    return ""

def short_venue(venue: str) -> str:
    """Kürzt Venue auf max 35 Zeichen."""
    if not venue: return ""
    # Nur Stadion-Name ohne Stadt (nach dem letzten Komma)
    if "," in venue:
        parts = [p.strip() for p in venue.split(",")]
        # Zeige: "Estadio Azteca · Mexico City"
        if len(parts) >= 2:
            return f"{parts[0]} · {parts[-1]}"
    return venue[:35]

def bilanz_footer(wm: dict) -> str:
    """Berechnet WM P&L aus recorded results."""
    picks_all = wm.get("picks", {})
    w = l = push = 0
    pnl = 0.0
    stake = 5.0  # €5 pro Pick
    for pick_list in picks_all.values():
        for p in pick_list:
            r = p.get("result")
            if r == "won":
                w += 1
                pnl += (p.get("odds", 1) - 1) * stake
            elif r == "lost":
                l += 1
                pnl -= stake
            elif r == "push":
                push += 1
    total = w + l + push
    if total == 0:
        return "📈 WM-Bilanz: Picks ab dem ersten Spieltag"
    roi = (pnl / (total * stake) * 100) if total > 0 else 0
    pnl_str = f"+€{pnl:.2f}" if pnl >= 0 else f"-€{abs(pnl):.2f}"
    roi_str = f"+{roi:.1f}%" if roi >= 0 else f"{roi:.1f}%"
    return f"📈 WM-Bilanz: {w}W-{l}L-{push}P | ROI: {roi_str} | P&L: {pnl_str}"


# ── Morning Card ───────────────────────────────────────────────────────────────
def build_morning_card(wm: dict, target_date: str) -> str | None:
    """Baut die Morning-Card für alle WM-Spiele am target_date."""

    groups      = wm.get("groups", {})
    all_picks   = wm.get("picks", {})
    upset_scores = wm.get("upsetScores", {})
    ai_previews  = wm.get("aiPreviews", {})

    # Alle Fixtures am target_date sammeln
    matches_today = []
    for gkey, gdata in groups.items():
        teams_map = {t["id"]: t for t in gdata.get("teams", [])}
        for fx in gdata.get("fixtures", []):
            if fx.get("date") == target_date:
                pick_key = f"{gkey}-{fx['matchday']}-{fx['home']}-{fx['away']}"
                home_t   = teams_map.get(fx["home"], {})
                away_t   = teams_map.get(fx["away"], {})
                matches_today.append({
                    "group":      gkey,
                    "matchday":   fx["matchday"],
                    "time":       fx.get("time", ""),
                    "venue":      fx.get("venue", ""),
                    "home":       fx["home"],
                    "away":       fx["away"],
                    "homeName":   home_t.get("name", fx["home"]),
                    "awayName":   away_t.get("name", fx["away"]),
                    "homeFlag":   home_t.get("flag", "🏳"),
                    "awayFlag":   away_t.get("flag", "🏳"),
                    "homeElo":    home_t.get("elo"),
                    "awayElo":    away_t.get("elo"),
                    "picks":      all_picks.get(pick_key, []),
                    "pick_key":   pick_key,
                    "upsetScore": upset_scores.get(pick_key, 0),
                    "aiSnippet":  ai_previews.get(pick_key, {}).get("tgSnippet"),
                })

    if not matches_today:
        return None  # Keine Spiele heute

    # Sortieren nach Uhrzeit
    matches_today.sort(key=lambda x: x["time"])

    # Header
    bet_count = sum(
        1 for m in matches_today
        for p in m["picks"] if p.get("verdict") == "BET" and p.get("edgePP", 0) >= MIN_BET_EDGE
    )
    lines = [
        f"🌍 <b>WM 2026 — Heute · {len(matches_today)} Spiel{'e' if len(matches_today) != 1 else ''}</b>",
    ]
    if bet_count > 0:
        lines.append(f"🎯 {bet_count} BET{'s' if bet_count != 1 else ''} mit Edge identifiziert\n")
    else:
        lines.append("👀 Heute im Blick — kein klarer BET\n")

    for m in matches_today:
        bet_picks = [p for p in m["picks"] if p.get("verdict") == "BET" and p.get("edgePP", 0) >= MIN_BET_EDGE]
        abw_picks = [p for p in m["picks"] if p.get("verdict") == "ABWÄGEN" and p.get("edgePP", 0) >= MIN_ABW_EDGE]

        # Spiel-Block
        us = m["upsetScore"]
        lines.append(f"━━ Gruppe {m['group']} · Spieltag {m['matchday']} ━━")

        if us >= 6:
            lines.append(f"{upset_label(us)} · Elo-Gap {abs((m['homeElo'] or 0) - (m['awayElo'] or 0))} Pkt")

        lines.append(
            f"{m['homeFlag']} <b>{m['homeName']}</b> vs {m['awayFlag']} <b>{m['awayName']}</b>"
        )
        venue_str = short_venue(m["venue"])
        lines.append(f"📅 {m['time']} Uhr{' · ' + venue_str if venue_str else ''}")

        # Elo-Info wenn vorhanden
        if m["homeElo"] and m["awayElo"]:
            elo_diff = m["homeElo"] - m["awayElo"]
            fav = m["homeName"] if elo_diff > 0 else m["awayName"]
            lines.append(f"⚡ Elo: {m['homeElo']} vs {m['awayElo']} → Favorit: {fav}")

        # AI Snippet (1-2 Sätze Vorschau)
        if m.get("aiSnippet"):
            lines.append(f"\n✦ <i>{m['aiSnippet']}</i>")

        if not bet_picks and not abw_picks:
            lines.append("🔇 Kein Pick mit ausreichend Edge")
        else:
            # BET-Picks zuerst
            for p in bet_picks:
                mp = model_pct(p.get("modelOdds"))
                mkp = pct(p.get("odds"))
                edge = p.get("edgePP", "?")
                info = p.get("info", "")
                lines.append(
                    f"🎯 <b>BET: {p['market']} @{p.get('odds', '?')}</b>"
                )
                lines.append(
                    f"   💡 Edge: <b>+{edge}pp</b> | Modell: {mp} vs. Markt: {mkp}"
                )
                if info:
                    lines.append(f"   📊 {info}")

            # ABWÄGEN-Picks
            for p in abw_picks:
                edge = p.get("edgePP", "?")
                lines.append(
                    f"⚖️ ABWÄGEN: {p['market']} @{p.get('odds', '?')} (+{edge}pp)"
                )

        lines.append("")  # Leerzeile zwischen Spielen

    # Footer
    lines.append(bilanz_footer(wm))
    lines.append("\n🤖 Powered by CocoBet · Elo · Poisson · 3-Signal-Verdict")

    return "\n".join(lines)


# ── Recap Card (nach Spieltag) ─────────────────────────────────────────────────
def build_recap_card(wm: dict, target_date: str) -> str | None:
    """Baut eine Recap-Card für Picks des gestrigen/angegebenen Datums."""

    all_picks = wm.get("picks", {})
    groups    = wm.get("groups", {})

    # Fixture-Lookup für Datum
    fix_lookup: dict[str, dict] = {}
    for gkey, gdata in groups.items():
        teams_map = {t["id"]: t for t in gdata.get("teams", [])}
        for fx in gdata.get("fixtures", []):
            pk = f"{gkey}-{fx['matchday']}-{fx['home']}-{fx['away']}"
            if fx.get("date") == target_date:
                home_t = teams_map.get(fx["home"], {})
                away_t = teams_map.get(fx["away"], {})
                fix_lookup[pk] = {
                    "homeName": home_t.get("name", fx["home"]),
                    "awayName": away_t.get("name", fx["away"]),
                    "homeFlag": home_t.get("flag", "🏳"),
                    "awayFlag": away_t.get("flag", "🏳"),
                    "group":    gkey,
                    "matchday": fx["matchday"],
                }

    if not fix_lookup:
        return None

    lines = [f"📊 <b>WM 2026 Recap — {target_date}</b>\n"]
    day_pnl = 0.0
    stake   = 5.0
    had_any = False

    for pick_key, fix_info in fix_lookup.items():
        fix_picks = all_picks.get(pick_key, [])
        pick_results = [(p, p.get("result")) for p in fix_picks
                        if p.get("verdict") in ("BET", "ABWÄGEN") and p.get("result")]
        if not pick_results:
            continue
        had_any = True
        lines.append(
            f"{fix_info['homeFlag']} {fix_info['homeName']} vs "
            f"{fix_info['awayFlag']} {fix_info['awayName']}"
        )
        for p, result in pick_results:
            if result == "won":
                profit = (p.get("odds", 1) - 1) * stake
                day_pnl += profit
                lines.append(f"  ✅ {p['market']} @{p.get('odds','?')} → +€{profit:.2f}")
            elif result == "lost":
                day_pnl -= stake
                lines.append(f"  ❌ {p['market']} @{p.get('odds','?')} → -€{stake:.2f}")
            elif result == "push":
                lines.append(f"  🔄 {p['market']} @{p.get('odds','?')} → Push")
        lines.append("")

    if not had_any:
        return None

    pnl_str = f"+€{day_pnl:.2f}" if day_pnl >= 0 else f"-€{abs(day_pnl):.2f}"
    lines.append(f"💰 Heutiger Tag: {pnl_str}")
    lines.append(bilanz_footer(wm))
    lines.append("\n🤖 CocoBet WM 2026")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("=== telegram_wm.py ===")

    try:
        with open(WM_FILE, encoding="utf-8") as f:
            wm = json.load(f)
    except FileNotFoundError:
        print(f"❌ {WM_FILE} nicht gefunden")
        return

    now = datetime.now(timezone.utc)
    today     = now.date().isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()

    mode = TG_WM_MODE.lower()

    if mode in ("morning", "all"):
        print(f"\n📅 Morning Card für {today}…")
        card = build_morning_card(wm, today)
        if card:
            ok = tg_send(card)
            print(f"  {'✅ Gesendet' if ok else '❌ Fehler'}")
            if ok:
                _log_send("morning_card", card.split("\n")[0], {"date": today, "mode": mode})
        else:
            print(f"  ○ Keine WM-Spiele am {today}")

    if mode in ("recap", "all"):
        print(f"\n📊 Recap für {yesterday}…")
        card = build_recap_card(wm, yesterday)
        if card:
            ok = tg_send(card)
            print(f"  {'✅ Gesendet' if ok else '❌ Fehler'}")
            if ok:
                _log_send("recap", card.split("\n")[0], {"date": yesterday, "mode": mode})
        else:
            print(f"  ○ Keine Picks mit Ergebnissen am {yesterday}")


if __name__ == "__main__":
    main()
