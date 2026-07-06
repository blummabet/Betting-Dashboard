#!/usr/bin/env python3
"""
telegram_streaks.py — „Serien der Woche"-Digest in den PUBLIC-Channel (29.06.2026, Lucas).

Wöchentlich (Cadence steuert der Workflow). Liest {wm_,liga_,mls_}streaks.json (dataset-aware) und
postet die Top-N heißen Serien als sauberen Text. TikTok-safe: KEINE Quoten/€, reine Form-Serien.

Env: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID (Public-Channel).
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

import cocobet_dataset as D

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
# `or`-Fallback statt .get(key, default): ein GESETZTER-aber-LEERER Env-Wert (Secret
# TELEGRAM_CHAT_ID nicht gesetzt → Workflow injiziert "") überschreibt sonst den Default
# und der Guard feuert „CHAT_ID fehlt". telegram_wm.py macht es genauso → morning/recap
# überleben ein leeres Secret, der Digest tat es nicht. (06.07.2026, Lucas)
CHAT_ID = (os.environ.get("TELEGRAM_CHAT_ID") or "-1003819239615").strip()
TOP_N = 5
MIN_LEN = 5

_ICON = {"over25": "⚽", "under25": "🧱", "bttsYes": "🤝", "bttsNo": "🚫",
         "cornersOver": "🚩", "cornersUnder": "🚩", "scored": "🎯", "cleanSheet": "🛡️", "cards": "🟨"}


def _heat(s: dict) -> int:
    h = s.get("length", 0) or 0
    if (s.get("continuation") or {}).get("state") == "intakt":
        h += 2
    si = s.get("signalInfo") or {}
    if si.get("state") == "confirm":
        h += si.get("count", 0) or 0
    return h


def build_streaks_digest(streaks: list, top_n: int = TOP_N) -> str | None:
    """Top-N heiße Gesamt-Serien (intakt, ≥MIN_LEN), je Team nur die stärkste. Reiner Builder (testbar).
    Returns HTML-Text oder None wenn nichts qualifiziert."""
    hot = [s for s in (streaks or [])
           if (s.get("venue") or "all") == "all"
           and (s.get("continuation") or {}).get("state") == "intakt"
           and (s.get("length") or 0) >= MIN_LEN]
    hot.sort(key=lambda s: -_heat(s))
    seen, top = set(), []
    for s in hot:
        tid = s.get("teamId")
        if tid in seen:
            continue
        seen.add(tid)
        top.append(s)
        if len(top) >= top_n:
            break
    if not top:
        return None
    lines = ["🔥 <b>Serien der Woche</b>\n"]
    for s in top:
        ic = _ICON.get(s.get("type"), "🔥")
        opp = (s.get("next") or {}).get("oppName")
        nxt = f"  ·  nächster Test: {opp}" if opp else ""
        sig = (s.get("signalInfo") or {}).get("state") == "confirm"
        flame = " 🔥" if sig else ""
        lines.append(f"{ic} <b>{s.get('team')}</b> — {s.get('length')}× in Folge {s.get('market')}{flame}{nxt}")
    lines.append("\nReine Form-Serien — keine Wettempfehlung. #cocobet")
    return "\n".join(lines)


def tg_send(text: str) -> bool:
    if not TOKEN or not CHAT_ID:
        print("  ⚠️  TELEGRAM_TOKEN/CHAT_ID fehlt — kein Send")
        return False
    data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                                 data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        print(f"  ⚠️  Send fehlgeschlagen: {e}")
        return False


def main():
    f = D.file("wm_streaks.json", "liga_streaks.json")
    streaks = []
    try:
        if Path(f).exists():
            streaks = json.loads(Path(f).read_text(encoding="utf-8")).get("streaks") or []
    except Exception as e:
        print(f"  ⚠️  {f.name} nicht lesbar: {e}")
    msg = build_streaks_digest(streaks)
    if not msg:
        print("ℹ️  Keine heißen Serien — kein Digest.")
        return
    print(msg)
    if tg_send(msg):
        print("✅ Serien-Digest gesendet (Public).")


if __name__ == "__main__":
    main()
