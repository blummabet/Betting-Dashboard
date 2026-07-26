#!/usr/bin/env python3
"""
weekly_sharp_recap.py — Sharp-Radar Wochenrückblick (Telegram, Trades-Channel)
================================================================================
25.07.2026 (Lucas: „Eventuell am Ende der Woche ein Rückblick"). Pendant/Ergänzung zu
detect_wm_sharp_moves.py: statt Einzel-Alerts fasst dieser Job die WOCHE zusammen und
beantwortet die einzige Frage, die zählt — trugen die gemeldeten Moves Edge?
Der Maßstab ist CLV (Closing Line Value = North Star): eine Bewegung, die bis zum Close
weiterläuft, hätte man geschlagen; eine, die zurückdreht, war Rauschen.

Quellen (alle dataset-aware über cocobet_dataset):
  · {ds}_sharp_moves_log.json  — die in der Woche erkannten Moves (Aktivität)
  · {ds}-odds-history.json     — Snapshots → Entry-Quote zum Move-Zeitpunkt
  · {ds}_closing_lines.json    — eingefrorene Closing-Linie → CLV-Auflösung
  · {ds}-data.json             — Team-Namen (via detect.team_info)

Ausgabe: EIN HTML-Post in den Trades-Channel (TELEGRAM_TRADES_CHAT_ID).

Env:
  COCOBET_DATASET / COCOBET_PROFILE  — Datensatz (liga | mls | wm)
  TELEGRAM_TOKEN / TELEGRAM_TRADES_CHAT_ID — ohne Token = Vorschau (stdout)
  RECAP_LOOKBACK_DAYS   — Fenster (Default 7)
  FORCE_RECAP=1         — Wochen-Dedup umgehen (für manuelle Läufe)

Dedup: {ds}_recap_state.json speichert die zuletzt gepostete ISO-Woche → derselbe
Wochen-Cron feuert nie doppelt (Retry/Dispatch-sicher).
"""
import json, os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cocobet_dataset as D
import detect_wm_sharp_moves as det   # team_info, tg_send, _log_send, Datei-Konstanten

BASE          = Path(__file__).resolve().parent
LOOKBACK_DAYS = int(os.environ.get("RECAP_LOOKBACK_DAYS") or 7)
FORCE         = os.environ.get("FORCE_RECAP", "") == "1"

MOVES_LOG    = det.MOVES_LOG
HISTORY_FILE = det.HISTORY_FILE
DATA_FILE    = det.WM_FILE
CLOSE_FILE   = D.file("wm_closing_lines.json", "liga_closing_lines.json")
STATE_FILE   = D.file("wm_recap_state.json",   "liga_recap_state.json")

# Menschlicher Datensatz-Name für die Überschrift.
_DS_LABEL = {"wm": "WM 2026", "liga": "Top-5-Ligen", "mls": "MLS"}
DS        = D.active_dataset()
DS_LABEL  = _DS_LABEL.get(DS, DS.upper())

SIDE_DE   = {"hw": "Heim", "dr": "Remis", "aw": "Auswärts"}
CLV_EPS   = 0.05   # Neutralband: |CLV| < 0.05pp = Push (weder geschlagen noch verloren)


# ── Helpers ────────────────────────────────────────────────────────────────────
def _iso(t: str) -> datetime:
    return datetime.fromisoformat(t.replace("Z", "+00:00"))

def _imp(o):
    return (1.0 / o) if o else None

def _steamed_side(m: dict):
    """Die Seite mit dem größten POSITIVEN Implied-Shift = Quote kürzeste = Geld kam rein."""
    c = {"hw": m.get("hwShift", 0) or 0, "dr": m.get("drShift", 0) or 0, "aw": m.get("awShift", 0) or 0}
    s = max(c, key=c.get)
    return (s, c[s]) if c[s] > 0 else (None, 0.0)

def _load(path: Path, default):
    try:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def _fmt_range(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%d.%m.')}–{end.strftime('%d.%m.%Y')}"


# ── CLV-Auflösung ───────────────────────────────────────────────────────────────
def _entry_odds(snaps: list, side: str, ts: datetime):
    """Quote der gesteamten Seite zum Move-Zeitpunkt: letzter Snapshot ≤ ts, Pinnacle bevorzugt."""
    pinn = [s for s in snaps if s.get("bk") == "pinnacle"]
    cand = [s for s in pinn if _iso(s["ts"]) <= ts] or [s for s in snaps if _iso(s["ts"]) <= ts]
    if not cand:
        return None
    return cand[-1].get(side)

def _closing_odds(key: str, side: str, close: dict, snaps: list):
    """Closing-Quote: bevorzugt eingefrorene Closing-Linie, sonst letzter Pinnacle-Snapshot."""
    cl = close.get(key)
    if cl and cl.get("final") and cl.get(side):
        return cl.get(side)
    pinn = [s for s in snaps if s.get("bk") == "pinnacle"]
    return pinn[-1].get(side) if pinn else None


def analyze(moves, hist, close, cutoff):
    recent = [m for m in moves if _iso(m["ts"]) >= cutoff]
    counts = {"steam": 0, "cumul": 0, "sharp": 0}
    rows   = []          # (maxShift, name, side, shift, clv|None)
    clvs   = []
    for m in recent:
        counts[m.get("type", "sharp")] = counts.get(m.get("type", "sharp"), 0) + 1
        side, sh = _steamed_side(m)
        hn = det.team_info(json_wm, m["homeId"], m["awayId"])[1]
        clv = None
        if side:
            snaps = hist.get(m["key"]) or []
            e = _entry_odds(snaps, side, _iso(m["ts"])) if snaps else None
            co = _closing_odds(m["key"], side, close, snaps) if snaps else None
            ei, ci = _imp(e), _imp(co)
            if ei and ci:
                clv = (ci - ei) * 100.0
                clvs.append(clv)
        rows.append((abs(m.get("maxShift", 0) or 0), hn, side, m.get("maxShift", 0) or 0, clv))
    rows.sort(key=lambda r: r[0], reverse=True)
    held = sum(1 for c in clvs if c > CLV_EPS)
    return {
        "n": len(recent), "counts": counts, "rows": rows,
        "clv_n": len(clvs), "clv_held": held,
        "clv_hold_rate": (held / len(clvs) * 100.0) if clvs else None,
        "clv_avg": (sum(clvs) / len(clvs)) if clvs else None,
    }


def _clv_mark(clv: float) -> str:
    if clv > CLV_EPS:  return "✅"
    if clv < -CLV_EPS: return "❌"
    return "➖"


# ── Nachricht ───────────────────────────────────────────────────────────────────
def build_message(stats, start, end) -> str:
    c = stats["counts"]
    L = [
        f"📊 <b>Sharp-Radar Wochenrückblick — {DS_LABEL}</b>",
        f"{_fmt_range(start, end)}",
        "",
        f"🔔 <b>{stats['n']} Move(s)</b> erkannt "
        f"({c.get('steam',0)} Steam · {c.get('cumul',0)} Drift · {c.get('sharp',0)} Sharp)",
    ]

    if stats["clv_n"]:
        rate = stats["clv_hold_rate"]
        avg  = stats["clv_avg"]
        L += [
            "",
            f"🎯 <b>CLV-Check</b> ({stats['clv_n']} mit Closing-Linie)",
            f"Bewegung hielt bis Close: <b>{stats['clv_held']}/{stats['clv_n']} ({rate:.0f}%)</b>",
            f"Ø CLV: <b>{avg:+.2f}pp</b>",
        ]
        # Ehrliche Einordnung — kein Overclaiming (kleine MLS-Märkte = oft Rauschen).
        if rate >= 58 and avg > 0.3:
            L.append("→ Die gemeldeten Moves trugen diese Woche Edge. ✅")
        elif rate <= 52 or avg < -0.3:
            L.append("→ Diese Woche war der Steam eher Rauschen — vorsichtig folgen.")
        else:
            L.append("→ Gemischt: Signal vorhanden, aber dünn.")

    top = [r for r in stats["rows"] if r[2]][:5]   # nur mit klarer gesteamter Seite
    if top:
        L += ["", "🔥 <b>Größte Moves</b>"]
        for i, (_, name, side, shift, clv) in enumerate(top, 1):
            tag = ""
            if clv is not None:
                tag = f" · CLV {clv:+.1f}pp {_clv_mark(clv)}"
            L.append(f"{i}. {name} ({SIDE_DE.get(side, side)}) {shift:+.1f}pp{tag}")

    L += ["", "<i>CLV = Closing Line Value. „Hielt bis Close“ = die Bewegung lief weiter, "
          "man hätte die Linie geschlagen.</i>"]
    return "\n".join(L)


# ── Wochen-Dedup ─────────────────────────────────────────────────────────────────
def _week_id(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"

def _already_posted(week: str) -> bool:
    st = _load(STATE_FILE, {})
    return st.get("lastWeek") == week

def _mark_posted(week: str):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"lastWeek": week, "postedAt":
                   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, f,
                  ensure_ascii=False, indent=2)


# ── Main ─────────────────────────────────────────────────────────────────────────
json_wm = None   # von main gesetzt (team_info braucht die Datendatei)

def main():
    global json_wm
    print(f"=== weekly_sharp_recap.py · {DS_LABEL} · {LOOKBACK_DAYS}d ===")

    now  = datetime.now(timezone.utc)
    week = _week_id(now)
    if _already_posted(week) and not FORCE:
        print(f"  ⏭️  Woche {week} bereits gepostet — Skip (FORCE_RECAP=1 zum Erzwingen).")
        return

    if not MOVES_LOG.exists():
        print("  ℹ️  Kein Moves-Log — nichts zu berichten."); return

    moves   = _load(MOVES_LOG, [])
    hist    = _load(HISTORY_FILE, {})
    close   = _load(CLOSE_FILE, {})
    json_wm = _load(DATA_FILE, {})

    cutoff = now - timedelta(days=LOOKBACK_DAYS)
    stats  = analyze(moves, hist, close, cutoff)

    if stats["n"] == 0 and not FORCE:
        print("  ✅  Keine Moves im Fenster — ruhige Woche, kein Post."); return

    start = cutoff
    msg   = build_message(stats, start, now)
    ok    = det.tg_send(msg)

    if ok:
        det._log_send("weekly_recap", msg.split("\n")[0],
                      {"dataset": DS, "week": week, "moves": stats["n"],
                       "clv_n": stats["clv_n"], "clv_avg": stats["clv_avg"]})
        _mark_posted(week)
        print(f"  ✅  Recap gepostet ({DS}, {week}).")
    else:
        print("  ❌  Senden fehlgeschlagen — Woche NICHT als gepostet markiert.")


if __name__ == "__main__":
    main()
