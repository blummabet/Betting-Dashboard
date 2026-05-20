#!/usr/bin/env python3
"""
detect_wm_sharp_moves.py — CocoBet WM 2026 Sharp Radar

Vergleicht den neuesten Odds-Snapshot mit dem vorherigen.
Bei signifikanter Linienbewegung → Telegram Alert Card.

Schwellenwerte:
  ALERT_PP    ≥ 5pp  implied prob shift → normaler Alert
  ALERT_PP_BIG≥ 10pp                   → Steam Move (besonders hervorgehoben)

Läuft nach fetch_wm_odds.py in der GitHub Action.

Umgebungsvariablen:
  TELEGRAM_TOKEN     — Bot-Token (optional, ohne = Vorschau-Modus)
  TELEGRAM_CHAT_ID   — Channel-ID
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
BASE         = Path(__file__).parent
HISTORY_FILE = BASE / "wm2026-odds-history.json"
WM_FILE      = BASE / "wm2026-data.json"
LOG_FILE     = BASE / "telegram-log.json"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID", "-1003819239615")

ALERT_PP     = 5    # pp implied prob shift → Alert
ALERT_PP_BIG = 10   # pp → Steam Move


# ── Send Log ──────────────────────────────────────────────────────────────────
def _log_send(type_: str, preview: str, meta: dict = None):
    try:
        existing = []
        if LOG_FILE.exists():
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


# ── Telegram ──────────────────────────────────────────────────────────────────
def tg_send(text: str) -> bool:
    if not TELEGRAM_TOKEN:
        print("⚠️  Kein TELEGRAM_TOKEN — Vorschau:")
        print(text)
        print()
        return True
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


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────
def impl_prob(odds: float | None) -> float | None:
    """Dezimal-Odds → Implied Probability in %."""
    if not odds or odds <= 0:
        return None
    return round(100 / odds, 2)


def pp_shift(old_odds: float | None, new_odds: float | None) -> float:
    """Implied-Prob-Verschiebung in Prozentpunkten (positiv = Favorit wurde stärker)."""
    old_p = impl_prob(old_odds)
    new_p = impl_prob(new_odds)
    if old_p is None or new_p is None:
        return 0.0
    return round(new_p - old_p, 2)


def odds_arrow(shift: float) -> str:
    if shift > 0:
        return "⬆️"   # Wahrscheinlichkeit gestiegen = Quote gefallen
    elif shift < 0:
        return "⬇️"   # Wahrscheinlichkeit gesunken = Quote gestiegen
    return "➡️"


def format_odds_change(market: str, old_o: float, new_o: float, shift: float) -> str:
    direction = odds_arrow(shift)
    sign = f"+{shift:.1f}" if shift > 0 else f"{shift:.1f}"
    return f"  {direction} {market}: {old_o:.2f} → {new_o:.2f}  ({sign}pp)"


def find_active_picks(wm: dict, match_key: str) -> list[dict]:
    """Gibt aktive BET/ABWÄGEN-Picks für ein Spiel zurück."""
    picks = wm.get("picks", {})
    result = []
    for pk, pick_list in picks.items():
        # pick_key Format: "A-1-MEX-ZAF" — enthält home-away
        parts = pk.split("-")
        if len(parts) >= 4:
            pk_match = f"{parts[2]}-{parts[3]}"
            if pk_match == match_key:
                for p in pick_list:
                    if p.get("verdict") in ("BET", "ABWÄGEN") and not p.get("result"):
                        result.append(p)
    return result


def pick_market_to_field(market: str) -> str | None:
    """Mapped Pick-Market-Namen auf history-Felder (hw/dr/aw)."""
    m = market.lower()
    if "heimsieg" in m or "home" in m:
        return "hw"
    if "auswärtssieg" in m or "away" in m:
        return "aw"
    if "unentschieden" in m or "draw" in m or "remis" in m:
        return "dr"
    return None


def team_info(wm: dict, home_id: str, away_id: str) -> tuple[str, str, str, str]:
    """Gibt (homeFlag, homeName, awayFlag, awayName) zurück."""
    for gdata in wm.get("groups", {}).values():
        teams = {t["id"]: t for t in gdata.get("teams", [])}
        if home_id in teams and away_id in teams:
            h = teams[home_id]
            a = teams[away_id]
            return h.get("flag", "🏳"), h.get("name", home_id), a.get("flag", "🏳"), a.get("name", away_id)
    return "🏳", home_id, "🏳", away_id


def match_date(wm: dict, home_id: str, away_id: str) -> str:
    """Gibt das Datum des Spiels zurück."""
    for gdata in wm.get("groups", {}).values():
        for fx in gdata.get("fixtures", []):
            if fx["home"] == home_id and fx["away"] == away_id:
                return fx.get("date", "")
    return ""


# ── Haupt-Analyse ─────────────────────────────────────────────────────────────
def analyze_moves(history: dict, wm: dict) -> list[dict]:
    """
    Vergleicht jeweils letzten zwei Snapshots.
    Gibt Liste von Moves zurück, die den Alert-Schwellenwert überschreiten.
    """
    moves = []

    for key, snaps in history.items():
        if len(snaps) < 2:
            continue   # Noch kein Vergleich möglich

        prev = snaps[-2]
        curr = snaps[-1]

        parts = key.split("-")
        if len(parts) < 2:
            continue
        home_id, away_id = parts[0], parts[1]

        # Shifts berechnen
        hw_shift = pp_shift(prev.get("hw"), curr.get("hw"))
        dr_shift = pp_shift(prev.get("dr"), curr.get("dr"))
        aw_shift = pp_shift(prev.get("aw"), curr.get("aw"))

        # Maximaler absoluter Shift über alle Märkte
        max_shift = max(abs(hw_shift), abs(dr_shift), abs(aw_shift))

        if max_shift < ALERT_PP:
            continue

        # Zeit seit letztem Snapshot
        try:
            ts_prev = datetime.fromisoformat(prev["ts"].replace("Z", "+00:00"))
            ts_curr = datetime.fromisoformat(curr["ts"].replace("Z", "+00:00"))
            hours_since = round((ts_curr - ts_prev).total_seconds() / 3600, 1)
        except Exception:
            hours_since = None

        # Aktive Picks für dieses Spiel?
        active_picks = find_active_picks(wm, key)
        pick_affected = []
        for p in active_picks:
            field = pick_market_to_field(p.get("market", ""))
            if field == "hw" and abs(hw_shift) >= ALERT_PP:
                pick_affected.append((p, hw_shift, "hw"))
            elif field == "dr" and abs(dr_shift) >= ALERT_PP:
                pick_affected.append((p, dr_shift, "dr"))
            elif field == "aw" and abs(aw_shift) >= ALERT_PP:
                pick_affected.append((p, aw_shift, "aw"))

        moves.append({
            "key":          key,
            "home_id":      home_id,
            "away_id":      away_id,
            "prev":         prev,
            "curr":         curr,
            "hw_shift":     hw_shift,
            "dr_shift":     dr_shift,
            "aw_shift":     aw_shift,
            "max_shift":    max_shift,
            "hours_since":  hours_since,
            "active_picks": active_picks,
            "pick_affected": pick_affected,
            "is_steam":     max_shift >= ALERT_PP_BIG,
        })

    # Stärkste Moves zuerst
    moves.sort(key=lambda x: x["max_shift"], reverse=True)
    return moves


# ── Telegram Card Builder ─────────────────────────────────────────────────────
def build_alert_card(move: dict, wm: dict) -> str:
    home_id  = move["home_id"]
    away_id  = move["away_id"]
    hf, hn, af, an = team_info(wm, home_id, away_id)
    date     = match_date(wm, home_id, away_id)
    prev     = move["prev"]
    curr     = move["curr"]
    is_steam = move["is_steam"]
    hours    = move["hours_since"]

    header = "🔥 <b>STEAM MOVE</b>" if is_steam else "📡 <b>Sharp Move detektiert</b>"
    time_str = f" · {hours}h" if hours else ""
    date_str = f" · {date}" if date else ""

    lines = [
        header,
        f"{hf} <b>{hn}</b> vs {af} <b>{an}</b>{date_str}",
        "",
    ]

    # Märkte mit signifikanter Bewegung
    for field, label, old_o, new_o, shift in [
        ("hw", "Heimsieg",        prev.get("hw"), curr.get("hw"), move["hw_shift"]),
        ("dr", "Unentschieden",   prev.get("dr"), curr.get("dr"), move["dr_shift"]),
        ("aw", "Auswärtssieg",    prev.get("aw"), curr.get("aw"), move["aw_shift"]),
    ]:
        if old_o and new_o and abs(shift) >= ALERT_PP:
            lines.append(format_odds_change(label, old_o, new_o, shift))

    lines.append("")

    # Context: Pick betroffen?
    for p, shift, field in move["pick_affected"]:
        if shift > 0:
            # Markt bewegt sich IN Richtung unseres Picks → Bestätigung
            lines.append(f"✅ <b>Markt bestätigt unseren Pick:</b> {p['market']} @{p.get('odds', '?')}")
        else:
            # Markt bewegt sich GEGEN unseren Pick → Warnung
            lines.append(f"⚠️ <b>Markt läuft GEGEN unseren Pick:</b> {p['market']} @{p.get('odds', '?')}")

    if not move["pick_affected"]:
        lines.append("ℹ️ Kein aktiver Pick betroffen")

    if hours:
        lines.append(f"\n⏱️ Snapshot-Abstand: {hours}h · Bookmaker: {curr.get('bk', '?')}")

    lines.append("\n🤖 CocoBet Sharp Radar · WM 2026")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=== detect_wm_sharp_moves.py ===")

    if not HISTORY_FILE.exists():
        print("  ℹ️  Keine History-Datei — noch keine Snapshots vorhanden")
        return

    with open(HISTORY_FILE, encoding="utf-8") as f:
        history = json.load(f)

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    print(f"  History: {len(history)} Fixtures mit Snapshots")

    moves = analyze_moves(history, wm)

    if not moves:
        print("  ✅  Keine signifikanten Moves detektiert")
        return

    print(f"\n  🔔  {len(moves)} Move(s) über Schwellenwert ({ALERT_PP}pp):")
    for m in moves:
        steam_tag = " 🔥 STEAM" if m["is_steam"] else ""
        print(f"    {m['key']}  max={m['max_shift']:.1f}pp{steam_tag}")

    # Alerts senden
    sent = 0
    for m in moves:
        card = build_alert_card(m, wm)
        ok = tg_send(card)
        if ok:
            sent += 1
            _log_send(
                "sharp_alert" if not m["is_steam"] else "steam_alert",
                card.split("\n")[0],
                {"match": m["key"], "shift": round(m["max_shift"], 1), "steam": m["is_steam"]},
            )

    print(f"\n  ✅  {sent}/{len(moves)} Alerts gesendet")


if __name__ == "__main__":
    main()
