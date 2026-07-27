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

BASE = Path(__file__).parent
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
# `or`-Fallback statt .get(key, default): ein GESETZTER-aber-LEERER Env-Wert (Secret
# TELEGRAM_CHAT_ID nicht gesetzt → Workflow injiziert "") überschreibt sonst den Default
# und der Guard feuert „CHAT_ID fehlt". telegram_wm.py macht es genauso → morning/recap
# überleben ein leeres Secret, der Digest tat es nicht. (06.07.2026, Lucas)
CHAT_ID = (os.environ.get("TELEGRAM_CHAT_ID") or "-1003819239615").strip()
TOP_N = 5
MIN_LEN = 5
# 27.07.2026 (Lucas: „WM-Streaks obwohl vorbei" + „immer die selben"):
STALE_DAYS = int(os.environ.get("STREAKS_STALE_DAYS") or 3)   # toter Datensatz (frozen) → kein Digest
STATE_FILE = BASE / f"{D.prefix()}streaks_digest_state.json"  # Woche-über-Woche: nur neue/gewachsene

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


def _stale_days(path) -> float | None:
    """Alter der Daten in Tagen aus _meta.generatedAt (None = unbekannt/lesbar)."""
    try:
        m = (json.loads(Path(path).read_text(encoding="utf-8")) or {}).get("_meta") or {}
        ga = m.get("generatedAt")
        if not ga:
            return None
        from datetime import datetime, timezone
        return (datetime.now(timezone.utc) - datetime.fromisoformat(str(ga).replace("Z", "+00:00"))).total_seconds() / 86400.0
    except Exception:
        return None


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  ⚠️  State-Save fehlgeschlagen: {e}")


def _skey(s: dict) -> str:  return f"{s.get('teamId')}:{s.get('type')}:{s.get('venue') or 'all'}"   # Venue-aware (all/home/away sind eigene Serien)
def _pkey(s: dict) -> str:  return f"P:{s.get('playerId')}:{s.get('type')}"


def _novel(items: list, state: dict, keyfn) -> list:
    """Nur Serien, die seit dem letzten Digest NEU sind oder GEWACHSEN — sonst „nichts hat sich getan"."""
    return [s for s in (items or []) if (s.get("length") or 0) > (state.get(keyfn(s)) or 0)]


def build_streaks_digest(streaks: list, top_n: int = TOP_N, players: list | None = None) -> str | None:
    """Top-N heiße Gesamt-Serien (intakt, ≥MIN_LEN), je Team nur die stärkste, + optionale
    Spieler-Serien-Sektion. Reiner Builder (testbar). None wenn WEDER Team- NOCH Spieler-Serien."""
    # `next` erforderlich: ein Team OHNE nächstes Spiel ist ausgeschieden → Serie wertlos
    # (06.07.2026, Lucas: Brasilien/Deutschland/Elfenbeinküste standen im Digest, obwohl raus).
    hot = [s for s in (streaks or [])
           if (s.get("venue") or "all") == "all"
           and (s.get("continuation") or {}).get("state") == "intakt"
           and s.get("next")
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
    player_lines = build_player_section(players or [])
    if not top and not player_lines:
        return None
    lines = ["🔥 <b>Serien der Woche</b>\n"]
    for s in top:
        ic = _ICON.get(s.get("type"), "🔥")
        opp = (s.get("next") or {}).get("oppName")
        nxt = f"  ·  nächster Test: {opp}" if opp else ""
        sig = (s.get("signalInfo") or {}).get("state") == "confirm"
        flame = " 🔥" if sig else ""
        lines.append(f"{ic} <b>{s.get('team')}</b> — {s.get('length')}× in Folge {s.get('market')}{flame}{nxt}")
    lines.extend(player_lines)
    lines.append("\nReine Form-Serien — keine Wettempfehlung. #cocobet")
    return "\n".join(lines)


_P_ICON = {"goals": "⚽", "involvement": "🅰️", "cleanSheet": "🧤"}
_P_VERB = {"goals": "in Folge getroffen", "involvement": "mit Torbeteiligung in Folge",
           "cleanSheet": "Spiele zu Null in Folge"}


def build_player_section(players: list, top_n: int = 5) -> list:
    """Spieler-Serien-Sektion (Torserie/Torbeteiligung/Zu-Null) für den Digest. Reiner Builder.
    Je Spieler nur die stärkste Serie, längste zuerst. Returns Zeilen-Liste (leer wenn nichts)."""
    seen, top = set(), []
    for s in sorted(players or [], key=lambda x: -(x.get("length") or 0)):
        pid = s.get("playerId")
        if pid in seen:
            continue
        seen.add(pid)
        top.append(s)
        if len(top) >= top_n:
            break
    if not top:
        return []
    out = ["", "👤 <b>Spieler in Form</b>\n"]
    for s in top:
        ic = _P_ICON.get(s.get("type"), "🔥")
        verb = _P_VERB.get(s.get("type"), "in Folge")
        opp = (s.get("next") or {}).get("oppName")
        nxt = f"  ·  gegen {opp}" if opp else ""
        flag = s.get("flag") or ""
        out.append(f"{ic} <b>{s.get('name')}</b> ({flag} {s.get('team')}) — "
                   f"{s.get('length')}× {verb}{nxt}")
    return out


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


def _read(path, key):
    try:
        p = Path(path)
        return json.loads(p.read_text(encoding="utf-8")).get(key) or [] if p.exists() else []
    except Exception as e:
        print(f"  ⚠️  {getattr(path, 'name', path)} nicht lesbar: {e}")
        return []


def main():
    streaks_path = D.file("wm_streaks.json", "liga_streaks.json")
    # (1) Frische-Guard: eingefrorener/toter Datensatz (z.B. WM nach Turnierende, generatedAt alt)
    # postet NIE — sonst kommen Woche für Woche dieselben toten Serien (Lucas: „WM obwohl vorbei").
    age = _stale_days(streaks_path)
    if age is not None and age > STALE_DAYS:
        print(f"ℹ️  {streaks_path.name} ist {age:.1f} Tage alt (>{STALE_DAYS}) — Datensatz eingefroren, kein Digest.")
        return
    streaks = _read(streaks_path, "streaks")
    players = _read(BASE / f"{D.prefix()}player_streaks.json", "players")
    # (2) Woche-über-Woche-Dedup: nur NEUE oder GEWACHSENE Serien — sonst „seit letzter Woche nichts getan".
    state = _load_state()
    fresh_streaks = _novel(streaks, state, _skey)
    fresh_players = _novel(players, state, _pkey)
    msg = build_streaks_digest(fresh_streaks, players=fresh_players)
    if not msg:
        print("ℹ️  Keine neuen/gewachsenen Serien seit letztem Digest — kein Post.")
        return
    print(msg)
    if tg_send(msg):
        print("✅ Serien-Digest gesendet (Public).")
        for s in fresh_streaks:
            if s.get("teamId") is not None:
                state[_skey(s)] = s.get("length") or 0
        for s in fresh_players:
            if s.get("playerId") is not None:
                state[_pkey(s)] = s.get("length") or 0
        _save_state(state)


if __name__ == "__main__":
    main()
