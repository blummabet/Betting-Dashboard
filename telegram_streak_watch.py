#!/usr/bin/env python3
"""telegram_streak_watch.py — Serien-Watch + Serie-gehalten/gerissen (04.07.2026, Lucas).

Zwei zeitnahe, spielbezogene Serien-Formate für den Public-Channel (ergänzt den wöchentlichen
„Serien der Woche"-Digest):

  • MODE=watch (pre-match): Team mit heißer Serie geht in sein nächstes Spiel → kurze Vorschau
    „🔥 Serien-Watch · X geht mit N× … ins Spiel gegen Y" inkl. xG-Deckungs-Siegel.
  • MODE=recap (post-match): das bewachte Spiel ist gelaufen → „✅ Serie hält (jetzt N+1×)" oder
    „❌ nach N Spielen gerissen". Macht aus Einzel-Cards eine fortlaufende Story.

State {prefix}streak_watch.json koppelt beide: watch merkt sich die bewachte Serie + ihr Spiel,
recap löst sie nach Spielende auf. TikTok-safe (keine Quoten/€). Dataset-aware (WM/MLS/Liga).

Env: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID (Public), TG_STREAK_MODE=watch|recap, SKIP_TELEGRAM=true.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).parent
STREAKS_FILE = D.file("wm_streaks.json", "liga_streaks.json")
WM_FILE = D.data_file()
STATE_FILE = BASE / f"{D.prefix()}streak_watch.json"

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
MODE = (os.environ.get("TG_STREAK_MODE") or "watch").lower()
SKIP_TELEGRAM = os.environ.get("SKIP_TELEGRAM", "").lower() == "true"

WATCH_MIN_LEN = int(os.environ.get("STREAK_WATCH_MIN_LEN", "5"))   # nur starke Serien bewachen

# Nur tor-basierte Typen (aus dem Endstand deterministisch aufzulösen). Ecken/Karten brauchen
# Stats-Coverage → hier bewusst aus (kein unsicheres „gerissen").
_PHRASE = {
    "over25":     "Über-2,5-Tore", "under25":   "Unter-2,5-Tore",
    "bttsYes":    "Beide-treffen",  "bttsNo":    "Kein-Gegentor-Duell",
    "scored":     "Tor",            "cleanSheet": "Zu-Null",
}
_ICON = {"over25": "⚽", "under25": "🧱", "bttsYes": "🤝", "bttsNo": "🚫",
         "scored": "🎯", "cleanSheet": "🛡️"}


def tg_send(text: str) -> bool:
    # SKIP_TELEGRAM = expliziter lokaler Dry-Run → True, damit main() den Flow (State) durchläuft.
    if SKIP_TELEGRAM:
        print("ℹ️  Telegram-Send geskippt (SKIP_TELEGRAM) — Vorschau:\n" + text)
        return True
    # Fehlender Token/Chat in einem ECHTEN Lauf ist ein FEHLER, kein Skip: False zurückgeben,
    # sonst markiert main() die Serie fälschlich als „bewacht" (Phantom-Dedup) und sendet nie nach.
    # (06.07.2026, Lucas: Serien-Watch schrieb Marker ohne echten Send → still verschluckt.)
    if not (TOKEN and CHAT_ID):
        print("⚠️  TELEGRAM_TOKEN/CHAT_ID fehlt — kein Send (nicht als bewacht markiert)")
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    body = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"❌ Telegram-Send fehlgeschlagen: {e}")
        return False


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_fixture(wm: dict, home: str, away: str) -> dict | None:
    for g in (wm.get("groups") or {}).values():
        for fx in (g.get("fixtures") or []):
            if fx.get("home") == home and fx.get("away") == away:
                return fx
    for kf in (wm.get("koFixtures") or []):
        if kf.get("home") == home and kf.get("away") == away:
            return kf
    return None


def _fixture_finished(fx: dict) -> bool:
    return str(((fx or {}).get("result") or {}).get("status") or "").upper() in {"FT", "AET", "PEN"}


def streak_held(stype: str, team_id: str, fx: dict) -> bool | None:
    """Hat die Serie im (fertigen) Spiel gehalten? Aus dem 90-Min-/Endstand. None wenn unklar."""
    r = (fx or {}).get("result") or {}
    hs, as_ = r.get("home_score"), r.get("away_score")
    if not isinstance(hs, (int, float)) or not isinstance(as_, (int, float)):
        return None
    total = hs + as_
    is_home = fx.get("home") == team_id
    own, opp = (hs, as_) if is_home else (as_, hs)
    if stype == "over25":    return total > 2.5
    if stype == "under25":   return total < 2.5
    if stype == "bttsYes":   return hs > 0 and as_ > 0
    if stype == "bttsNo":    return not (hs > 0 and as_ > 0)
    if stype == "scored":    return own > 0
    if stype == "cleanSheet": return opp == 0
    return None


# ── MODE=watch ────────────────────────────────────────────────────────────────
def build_watch(streaks: list, wm: dict, watched: dict, today: str) -> list:
    """Zu bewachende Serien: all-venue, intakt, ≥WATCH_MIN_LEN, nächstes Spiel HEUTE, tor-basiert,
    noch nicht bewacht. Returns [(key, entry, message)]."""
    out = []
    for s in streaks or []:
        if (s.get("venue") or "all") != "all":
            continue
        if (s.get("continuation") or {}).get("state") != "intakt":
            continue
        stype = s.get("type")
        if stype not in _PHRASE:
            continue
        if (s.get("length") or 0) < WATCH_MIN_LEN:
            continue
        nx = s.get("next") or {}
        gdate = str(nx.get("date") or "")[:10]
        if gdate != today:
            continue   # nur Spiele HEUTE
        key = f"{s.get('teamId')}:{stype}:{gdate}"
        if key in watched:
            continue
        entry = {"teamId": str(s.get("teamId")), "team": s.get("team"), "type": stype,
                 "length": s.get("length"), "market": s.get("market"),
                 "pickKey": nx.get("pickKey"), "oppName": nx.get("oppName"),
                 "date": gdate, "xgBacked": s.get("xgBacked"),
                 "postedAt": datetime.now(timezone.utc).isoformat()}
        out.append((key, entry, _watch_msg(s, nx)))
    return out


def _watch_msg(s: dict, nx: dict) -> str:
    icon = _ICON.get(s.get("type"), "🔥")
    flag = s.get("flag") or ""
    phrase = s.get("market") or _PHRASE.get(s.get("type"), "Serie")
    lines = [f"🔥 <b>Serien-Watch</b>",
             f"{flag} <b>{s.get('team')}</b> geht mit <b>{s.get('length')}× {phrase}</b> "
             f"in Folge ins Spiel gegen {nx.get('oppName') or '—'}."]
    xgb = s.get("xgBacked")
    if xgb is True:
        lines.append("✓ Echte Serie — auch per xG gedeckt.")
    elif xgb is False:
        lines.append("⚠️ Vorsicht: zuletzt mehr Glück als xG.")
    opp_pct = nx.get("oppRatePct")
    if isinstance(opp_pct, (int, float)):
        lines.append(f"Gegner-Grundrate passt in {opp_pct}% seiner Spiele.")
    return "\n".join(lines)


# ── MODE=recap ────────────────────────────────────────────────────────────────
def build_recap(wm: dict, watched: dict, today: str) -> tuple[list, list]:
    """Bewachte Serien, deren Spiel gelaufen ist → (Nachrichten, erledigte Keys)."""
    msgs, done = [], []
    for key, w in list(watched.items()):
        if str(w.get("date") or "")[:10] >= today:
            continue   # Spieltag noch nicht vorbei
        pk = w.get("pickKey") or ""
        parts = pk.split("-")
        fx = _find_fixture(wm, parts[-2], parts[-1]) if len(parts) >= 2 else None
        if not fx or not _fixture_finished(fx):
            continue   # noch kein Endstand → beim nächsten Lauf erneut prüfen
        held = streak_held(w.get("type"), w.get("teamId"), fx)
        if held is None:
            done.append(key)   # nicht auflösbar → aus dem Watch nehmen, nicht posten
            continue
        msgs.append(_recap_msg(w, held))
        done.append(key)
    return msgs, done


def _recap_msg(w: dict, held: bool) -> str:
    icon = _ICON.get(w.get("type"), "🔥")
    phrase = w.get("market") or _PHRASE.get(w.get("type"), "Serie")
    if held:
        return (f"✅ <b>{w.get('team')}s {phrase}-Serie hält</b> — "
                f"jetzt {(w.get('length') or 0) + 1}× in Folge. {icon}")
    return (f"❌ <b>{w.get('team')}s {phrase}-Serie gerissen</b> — "
            f"nach {w.get('length')} Spielen ist Schluss.")


def main() -> None:
    if not STREAKS_FILE.exists() or not WM_FILE.exists():
        print("❌ Streak-/Daten-Datei fehlt"); return
    streaks = (_load(STREAKS_FILE, {}) or {}).get("streaks") or []
    wm = _load(WM_FILE, {})
    state = _load(STATE_FILE, {"watched": {}})
    watched = state.setdefault("watched", {})
    today = date.today().isoformat()

    if MODE == "recap":
        msgs, done = build_recap(wm, watched, today)
        for m in msgs:
            tg_send(m)
        for k in done:
            watched.pop(k, None)
        print(f"📊 Serien-Recap: {len(msgs)} gepostet, {len(done)} abgeschlossen.")
    else:  # watch
        new = build_watch(streaks, wm, watched, today)
        for key, entry, msg in new:
            if tg_send(msg):
                watched[key] = entry
        print(f"🔥 Serien-Watch: {len(new)} neue Serie(n) bewacht.")

    _save_state(state)


if __name__ == "__main__":
    main()
