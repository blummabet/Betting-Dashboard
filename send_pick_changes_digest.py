#!/usr/bin/env python3
"""
send_pick_changes_digest.py — Tägliches Telegram-Digest der relevanten Pick-Änderungen

Läuft 1× täglich (12:00 UTC = 14:00 Wien) im fetch-wm-data-Workflow.

Sammelt aus pick_changes_log.json:
  - Nur deltaKind in {upgrade, downgrade, new_pick, removed, edge_up, edge_down}
  - Nur Änderungen seit letzter Digest-Sendung (oder fallback: 24h)
  - Nur zukünftige Spiele
  - Aggregiert pro matchKey um Lärm zu reduzieren

Sendet an TELEGRAM_TRADES_CHAT_ID.

Idempotenz: Speichert lastDigest-Timestamp in pick_changes_digest_state.json.
Wenn keine relevanten Changes → kein Telegram-Send (kein Empty-Digest-Spam).
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE         = Path(__file__).parent
LOG_FILE     = BASE / "pick_changes_log.json"
STATE_FILE   = BASE / "pick_changes_digest_state.json"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID        = os.environ.get("TELEGRAM_TRADES_CHAT_ID", "").strip()
SKIP_SEND      = os.environ.get("SKIP_SEND", "").lower() == "true"

# Fallback-Fenster wenn kein lastDigest (Erst-Lauf): 24h
FALLBACK_WINDOW_HOURS = 24

KIND_ICON = {
    "upgrade":   "▲",
    "downgrade": "▼",
    "new_pick":  "🆕",
    "removed":   "✕",
    "edge_up":   "↑",
    "edge_down": "↓",
}
KIND_LABEL = {
    "upgrade":   "aufgewertet",
    "downgrade": "zurückgestuft",
    "new_pick":  "neuer Pick",
    "removed":   "entfernt",
    "edge_up":   "Edge gestiegen",
    "edge_down": "Edge gefallen",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def tg_send(text: str) -> bool:
    # M3 Fix 05.06.2026 — explizit auflisten was fehlt, statt silent skip.
    # Vorher: Digest scheiterte still wenn TELEGRAM_TRADES_CHAT_ID nicht gesetzt war,
    # Lucas hätte sich gewundert wieso der 14:00-Digest nicht ankommt. Jetzt:
    # konkreter Hinweis welches Secret fehlt.
    if SKIP_SEND:
        print("ℹ️  Telegram-Send geskippt (SKIP_SEND=true)")
        print(text)
        return False
    missing = []
    if not TELEGRAM_TOKEN: missing.append("TELEGRAM_TOKEN")
    if not CHAT_ID:        missing.append("TELEGRAM_TRADES_CHAT_ID")
    if missing:
        print(f"⚠️  Telegram-Send NICHT möglich — fehlende Secrets: {', '.join(missing)}")
        print(f"    → Setze sie in GitHub Actions Secrets (Settings → Secrets and variables)")
        print(f"--- Digest-Inhalt (würde gesendet werden) ---\n{text}")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":                  CHAT_ID,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read().decode())
            return bool(j.get("ok"))
    except Exception as e:
        print(f"❌ Telegram-Send failed: {e}")
        return False


def main():
    log_data = _load(LOG_FILE, {"changes": []})
    all_changes = log_data.get("changes") or []
    state = _load(STATE_FILE, {})
    last_digest = state.get("lastDigest")

    # Fenster bestimmen
    if last_digest:
        try:
            since = datetime.fromisoformat(last_digest.replace("Z", "+00:00"))
        except Exception:
            since = datetime.now(timezone.utc) - timedelta(hours=FALLBACK_WINDOW_HOURS)
    else:
        since = datetime.now(timezone.utc) - timedelta(hours=FALLBACK_WINDOW_HOURS)

    # Filter: seit Fenster + relevant + nicht-vergangene Spiele
    now = datetime.now(timezone.utc)
    by_match: dict[str, list[dict]] = {}
    for c in all_changes:
        try:
            ts = datetime.fromisoformat(c.get("ts", "").replace("Z", "+00:00"))
        except Exception:
            continue
        if ts < since:
            continue
        if not c.get("relevant"):
            continue
        ko_iso = c.get("kickoff", "")
        if ko_iso:
            try:
                ko = datetime.fromisoformat(ko_iso.replace("Z", "+00:00"))
                if ko < now:
                    continue
            except Exception:
                pass
        by_match.setdefault(c["matchKey"], []).append(c)

    if not by_match:
        print(f"ℹ️  Keine relevanten Pick-Änderungen seit {since.isoformat()} — kein Digest")
        return

    # Pro matchKey: nur neueste pro market
    total_changes = 0
    lines = []
    for mk in sorted(by_match.keys(), key=lambda k: (by_match[k][0].get("kickoff", ""), k)):
        latest_per_market: dict[str, dict] = {}
        for c in by_match[mk]:
            mkt = c.get("market", "?")
            if mkt not in latest_per_market or c.get("ts", "") > latest_per_market[mkt].get("ts", ""):
                latest_per_market[mkt] = c

        # Header für dieses Match
        any_change = next(iter(latest_per_market.values()))
        fixture = any_change.get("fixture", mk)
        ko_iso = any_change.get("kickoff", "")
        ko_label = ""
        if ko_iso:
            try:
                ko = datetime.fromisoformat(ko_iso.replace("Z", "+00:00"))
                ko_label = f" · {ko.strftime('%d.%m. %H:%M')}"
            except Exception:
                pass

        lines.append(f"\n<b>{fixture}</b>{ko_label}")
        for mkt, c in latest_per_market.items():
            icon = KIND_ICON.get(c["deltaKind"], "·")
            lines.append(f"  {icon} <b>{mkt}</b> — {c.get('reason','')}")
            total_changes += 1

    header = f"🔄 <b>Pick-Updates · {now.strftime('%d.%m.%Y')}</b>\n{total_changes} relevante Änderung{'en' if total_changes != 1 else ''} seit letzter Meldung."
    body = "\n".join(lines)
    msg = f"{header}\n{body}\n\n<i>Details + Klick-Sprung im Dashboard oben.</i>"

    ok = tg_send(msg)
    if ok:
        print(f"✅ Digest gesendet ({total_changes} Changes, {len(by_match)} Matches)")
        _save(STATE_FILE, {
            "lastDigest":  now.isoformat(),
            "lastCount":   total_changes,
            "lastMatches": len(by_match),
        })
    else:
        print(f"⚠️  Digest NICHT gesendet — State NICHT aktualisiert (wird beim nächsten Run erneut versucht)")


if __name__ == "__main__":
    main()
