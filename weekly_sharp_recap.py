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
    rows   = []          # {abs, name, side, shift, clv, e, c}
    clvs   = []
    for m in recent:
        counts[m.get("type", "sharp")] = counts.get(m.get("type", "sharp"), 0) + 1
        side, sh = _steamed_side(m)
        hn = det.team_info(json_wm, m["homeId"], m["awayId"])[1]
        clv = e = co = None
        if side:
            snaps = hist.get(m["key"]) or []
            e = _entry_odds(snaps, side, _iso(m["ts"])) if snaps else None
            co = _closing_odds(m["key"], side, close, snaps) if snaps else None
            ei, ci = _imp(e), _imp(co)
            if ei and ci:
                clv = (ci - ei) * 100.0
                clvs.append(clv)
        mx = m.get("maxShift", 0) or 0
        rows.append({"abs": abs(mx), "name": hn, "side": side,
                     "shift": mx, "clv": clv, "e": e, "c": co})
    rows.sort(key=lambda r: r["abs"], reverse=True)
    held = sum(1 for c in clvs if c > CLV_EPS)
    return {
        "n": len(recent), "counts": counts, "rows": rows,
        "clv_n": len(clvs), "clv_held": held,
        "clv_hold_rate": (held / len(clvs) * 100.0) if clvs else None,
        "clv_avg": (sum(clvs) / len(clvs)) if clvs else None,
    }


SIDE_LONG = {"hw": "Heimsieg", "dr": "Unentschieden", "aw": "Auswärtssieg"}

def _clv_mark(clv: float) -> str:
    if clv > CLV_EPS:  return "✅"
    if clv < -CLV_EPS: return "❌"
    return "➖"

def _verdict_words(clv):
    """Klartext-Urteil für die freundliche Form."""
    if clv is None:      return ("•", "noch offen")
    if clv > CLV_EPS:    return ("✅", "bestätigt")
    if clv < -CLV_EPS:   return ("❌", "drehte zurück")
    return ("➖", "unverändert")


# ── Nachricht ───────────────────────────────────────────────────────────────────
def build_message(stats, start, end) -> str:
    """Freundliche Form: echte Quoten statt pp, Alltagssprache, ohne Fachjargon.
    25.07.2026 (Lucas: „so, dass es auch jemand versteht") — Zielgruppe Telegram-Gruppe."""
    L = [
        f"📊 <b>Sharp-Radar — die Woche in Kürze ({DS_LABEL})</b>",
        f"{_fmt_range(start, end)}",
        "",
        "Wir beobachten, wo plötzlich viel Geld auf eine Seite fließt und die Quote "
        "dadurch kippt — solche Bewegungen kommen oft von Leuten, die wissen, was sie tun.",
        "",
        f"🔔 <b>Diese Woche: {stats['n']} solcher Bewegungen.</b>",
    ]

    if stats["clv_n"]:
        rate = stats["clv_hold_rate"]
        avg  = stats["clv_avg"]
        L += [
            "",
            "Der Test ist simpel: Läuft die Quote bis zum Anpfiff weiter in dieselbe "
            "Richtung? Dann lag das frühe Geld richtig — man hätte die bessere Quote "
            "bekommen als alle, die erst kurz vor dem Spiel getippt haben.",
            "",
            f"✅ Das war bei <b>{stats['clv_held']} von {stats['clv_n']} Spielen</b> so "
            f"({rate:.0f}%).",
        ]
        if rate >= 58 and avg > 0.3:
            L.append("Eine starke Woche — die früh erkannten Bewegungen lagen meist richtig.")
        elif rate <= 52 or avg < -0.3:
            L.append("Diese Woche eher durchwachsen — die Bewegungen waren klein und oft "
                     "Zufall. Richtig spannend wird's mit den großen Ligen ab August.")
        else:
            L.append("Solide, aber kein klares Bild. In kleinen Märkten sind viele "
                     "Bewegungen noch Zufall — mit den großen Ligen ab August wird's "
                     "aussagekräftiger.")

    # Pushes (unverändert, |CLV|≤EPS) raus — für Laien verwirrend als „auffällige" Bewegung.
    top = [r for r in stats["rows"] if r["side"] and r["e"] and r["c"]
           and r["clv"] is not None and abs(r["clv"]) > CLV_EPS][:3]
    if top:
        L += ["", "🔥 <b>Die auffälligsten Bewegungen:</b>"]
        for r in top:
            mark, word = _verdict_words(r["clv"])
            L.append(f"{mark} {r['name']} ({SIDE_LONG.get(r['side'], r['side'])}): "
                     f"Quote {r['e']:.2f} → {r['c']:.2f} — {word}")

    L += ["", "<i>Fallende Quote = mehr Geld auf diese Seite. Bleibt sie bis zum "
          "Anpfiff unten, lag das frühe Geld richtig.</i>"]
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
