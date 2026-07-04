#!/usr/bin/env python3
"""notify_new_picks.py — Intraday-„Neuer Pick"-Telegram-Noti (03.07.2026, Lucas).

Der Morgen-Digest postet die Slate einmal. Späte Steam-Picks, die danach reinkommen
(z.B. Ghana am Nachmittag), erreichten keinen Follower mehr. Dieses Skript läuft bei jedem
Daten-Refresh und meldet KOMPAKT nur die Picks, die seit dem heutigen Digest neu dazukamen —
in den Public-Channel, TikTok-/Compliance-safe (keine Quoten/€).

Zusammenspiel mit dem Digest (siehe [[pick_announce_state]]):
  • Digest markiert beim Senden die ganze Slate + setzt lastDigestDate=heute.
  • Vor dem heutigen Digest: dieses Skript setzt STUMM die Basis (kein Send) → der Digest
    bleibt Erst-Ankündiger, kein Doppel-Post der Tages-Slate.
  • Nach dem Digest: nur echte Nachzügler werden gemeldet.

Dataset-aware (WM/MLS/Liga). Env:
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID   — Public-Channel (wie der Digest)
  SKIP_TELEGRAM=true                 — nur Vorschau, kein Send
  FORCE_SEND=true                    — Digest-Gate ignorieren (Test/manuell)
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D
import pick_announce_state as S

BASE    = Path(__file__).parent
WM_FILE = D.data_file()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
SKIP_TELEGRAM  = os.environ.get("SKIP_TELEGRAM", "").lower() == "true"
FORCE_SEND     = os.environ.get("FORCE_SEND", "").lower() == "true"

# Wie viele neue Picks einzeln zeigen, bevor „… und N weitere" (gegen Wall-of-Text).
MAX_LIST = 6

_LEAGUE_LABEL = {"wm": "WM 2026", "mls": "MLS", "liga": "Top-Liga"}


def tg_send(text: str) -> bool:
    if SKIP_TELEGRAM or not (TELEGRAM_TOKEN and CHAT_ID):
        print("ℹ️  Telegram-Send geskippt (SKIP_TELEGRAM / Token / ChatID) — Vorschau:")
        print(text)
        return not (TELEGRAM_TOKEN and CHAT_ID) is False  # Vorschau gilt als OK
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": CHAT_ID, "text": text,
                       "parse_mode": "HTML", "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as e:
        print(f"❌ Telegram-Send fehlgeschlagen: {e}")
        return False


def _conv_word(u: dict) -> str:
    """Kurzes, quotenloses Konfidenz-Wort (TikTok-safe)."""
    cs = u.get("convictionScore")
    if u.get("verdict") == "BET":
        return "🟢 Klarer Pick" if isinstance(cs, int) and cs >= 8 else "🟢 Pick"
    return "🟡 Auf dem Zettel"   # ABWÄGEN


def _kickoff_wien(u: dict) -> str:
    ko = u.get("kickoff")
    if not ko:
        return ""
    try:
        dt = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        from datetime import timedelta
        return " · " + (dt + timedelta(hours=2)).strftime("%H:%M")   # Wien (CEST)
    except Exception:
        return ""


def build_message(new_units: list) -> str:
    league = _LEAGUE_LABEL.get(D.active_dataset(), "")
    n = len(new_units)
    head = "🆕 <b>Neuer Pick</b>" if n == 1 else f"🆕 <b>{n} neue Picks</b>"
    if league:
        head += f" · {league}"
    lines = [head, ""]
    for u in new_units[:MAX_LIST]:
        rl = f" <i>({u['roundLabel']})</i>" if u.get("roundLabel") else ""
        lines.append(
            f"{u['homeFlag']} <b>{u['homeName']} – {u['awayName']}</b>{rl}{_kickoff_wien(u)}"
        )
        lines.append(f"   {_conv_word(u)} · {u['market']}")
    if n > MAX_LIST:
        lines.append(f"\n… und {n - MAX_LIST} weitere im Dashboard")
    lines.append("\n<i>Kam nach dem Morgen-Update rein.</i>")
    return "\n".join(lines)


def main() -> None:
    if not WM_FILE.exists():
        print(f"❌ {WM_FILE} nicht gefunden"); sys.exit(0)
    wm = json.loads(WM_FILE.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    state = S.load()
    units = list(S.iter_pick_units(wm, now))
    by_id = {u["id"]: u for u in units}
    current_ids = set(by_id)

    digest_ran_today = (state.get("lastDigestDate") == today)

    # Vor dem heutigen Digest (oder allererster Lauf): stumm Basis setzen, NICHT senden.
    if not (digest_ran_today or FORCE_SEND):
        S.mark(state, current_ids, now.isoformat())
        state["seeded"] = True
        S.save(state)
        print(f"○ Digest heute noch nicht gelaufen ({state.get('lastDigestDate')}) — "
              f"Basis gesetzt ({len(current_ids)} Picks), kein Send.")
        return

    new_ids = [i for i in current_ids if not S.is_announced(state, i)]
    if not new_ids:
        print(f"○ Keine neuen Picks seit dem Digest ({len(current_ids)} bekannt).")
        return

    # Neue zuerst nach Anpfiff sortieren (früheste zuerst)
    new_units = sorted((by_id[i] for i in new_ids), key=lambda u: u.get("kickoff") or "~")
    msg = build_message(new_units)
    ok = tg_send(msg)
    print(f"{'✅' if ok else '❌'} Neuer-Pick-Noti: {len(new_units)} Pick(s)")
    if ok:
        S.mark(state, new_ids, now.isoformat())
        S.save(state)


if __name__ == "__main__":
    main()
