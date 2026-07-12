#!/usr/bin/env python3
"""
monitor_open_positions.py — Position-Health-Monitor für offene Polymarket-Trades

Berechnet pro offener Position einen Health-Score (0-100) basierend auf:
  • Edge-Persistenz   (30%) — ist der ursprüngliche Edge noch da?
  • Pinnacle-Drift    (20%) — hat Pinnacle sich gegen uns bewegt?
  • CLV-Status        (15%) — sind wir noch CLV+ oder vom Markt überholt?
  • Time-Pressure      (5%) — wie nah am Anpfiff?
  • (Phase 2: Verletzungen, Form-Veränderung — kommen wenn Live-Pipelines stabil)

Schreibt position_health.json:
  {
    "lastRun": ISO,
    "positions": [
      {
        "key": "MEX-ZAF-Heimsieg",
        "matchKey": "MEX-ZAF",
        "market": "Heimsieg",
        "score": 47,
        "status": "warning",          # ok | watch | warning | critical
        "factors": [...],
        "recommendation": "Soft-Close überlegen",
        "alert_sent": False,
      }
    ]
  }

Sendet Telegram-Alert wenn Score < 60 (warnung) oder < 40 (kritisch),
mit Dedup pro Position+Status um Spam zu verhindern.

Läuft in manage-wm-poly.yml (5× täglich) — nach manage_wm_poly_positions.py.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent
# DATASET-AWARE (12.07.2026, Lucas: „MLS auf Polymarket"). Positions-Health muss je Datensatz
# getrennt laufen — sonst würde ein MLS-Lauf die WM-Positionen bewerten (und umgekehrt).
import cocobet_dataset as D  # noqa: E402
BETS_FILE     = Path(str(D.file("wm_auto_bets_placed.json",     "liga_auto_bets_placed.json")))
POLY_FILE     = Path(str(D.file("wm_poly_prices.json",          "liga_poly_prices.json")))
WM_FILE       = Path(str(D.data_file()))
HEALTH_FILE   = Path(str(D.file("position_health.json",         "liga_position_health.json")))
DEDUP_FILE    = Path(str(D.file("position_health_alerts.json",  "liga_position_health_alerts.json")))

# ── Refactor 2026-06-06: Konstanten aus cocobet_config.json (Profile-aware) ──
try:
    from cocobet_config import CONFIG as _CFG
except Exception:
    _CFG = {}

def _cfg(section: str, key: str, default):
    """Sicherer Config-Lookup mit Default-Fallback (=aktueller Hardcode-Wert)."""
    if isinstance(_CFG, dict):
        return _CFG.get(section, {}).get(key, default)
    return default

# ── Score-Schwellen ───────────────────────────────────────────────
SCORE_OK       = _cfg("monitor", "score_ok",       80)   # >= 80: alles gut, kein Alert
SCORE_WATCH    = _cfg("monitor", "score_watch",    60)   # 60-79: Daily-Heartbeat erwähnt
SCORE_WARNING  = _cfg("monitor", "score_warning",  40)   # 40-59: Telegram-Warnung
SCORE_CRITICAL = _cfg("monitor", "score_critical",  0)   # <40:  Telegram-Kritisch + Sell-Empfehlung

# ── Faktor-Gewichte (Summen sich auf 75 — Phase 2 ergänzt um 25 für Lineup/Form) ──
W_EDGE   = _cfg("monitor", "w_edge", 30)
W_PINN   = _cfg("monitor", "w_pinn", 20)
W_CLV    = _cfg("monitor", "w_clv",  15)
W_TIME   = _cfg("monitor", "w_time",  5)
W_TOTAL  = W_EDGE + W_PINN + W_CLV + W_TIME   # = 70 in Phase 1

# ── Telegram ──────────────────────────────────────────────────────
TELEGRAM_TOKEN = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
TRADES_CHAT_ID = (os.environ.get("TELEGRAM_TRADES_CHAT_ID") or "").strip()
SKIP_SEND      = os.environ.get("SKIP_SEND", "").lower() == "true"


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


# Team-Flaggen aus wm2026-data (id→🇽🇽). Behebt 🏳🏳 im Position-Alert:
# current_fx (wm_poly_prices) hat keine Flagge, der Bet-Record auch nicht.
_TEAM_FLAGS: dict | None = None
def _flag(team_id: str | None) -> str | None:
    global _TEAM_FLAGS
    if _TEAM_FLAGS is None:
        _TEAM_FLAGS = {}
        wm = _load(WM_FILE, {})
        for g in (wm.get("groups") or {}).values():
            for t in (g.get("teams") or []):
                if t.get("id") and t.get("flag"):
                    _TEAM_FLAGS[t["id"]] = t["flag"]
    return _TEAM_FLAGS.get(team_id) if team_id else None


# ── Faktor-Berechnung ─────────────────────────────────────────────
def _score_edge_persistence(entry_edge_pp: float, current_edge_pp) -> tuple[float, str]:
    """100 = voller Erhalt, 0 = Edge weg/negativ."""
    if current_edge_pp is None:
        return 70.0, "Edge aktuell nicht bewertbar (Markt nicht aufgelöst)"
    if not entry_edge_pp or entry_edge_pp <= 0:
        return 50.0, "Entry-Edge ≤0pp — nicht bewertbar"
    if current_edge_pp <= 0:
        return 0.0, f"Edge ist NEGATIV ({current_edge_pp:.1f}pp) — Markt gegen uns"
    ratio = current_edge_pp / entry_edge_pp
    score = min(100.0, max(0.0, ratio * 100))
    if ratio >= 0.9:
        msg = f"Edge erhalten: {current_edge_pp:.1f}/{entry_edge_pp:.1f}pp ({ratio:.0%})"
    elif ratio >= 0.6:
        msg = f"Edge teilweise erodiert: {current_edge_pp:.1f}/{entry_edge_pp:.1f}pp ({ratio:.0%})"
    elif ratio >= 0.3:
        msg = f"Edge stark erodiert: {current_edge_pp:.1f}/{entry_edge_pp:.1f}pp ({ratio:.0%})"
    else:
        msg = f"Edge fast weg: nur noch {current_edge_pp:.1f}pp vs Entry {entry_edge_pp:.1f}pp"
    return score, msg


def _score_pinn_drift(entry_pinn_fair: float, current_pinn_fair: float) -> tuple[float, str]:
    """
    Pinnacle bewegt sich GEGEN uns wenn sich pinn_fair von unserem Entry entfernt.
    Wir wetten auf YES → höherer pinn_fair = besser für uns, niedriger = gegen uns.
    """
    if not entry_pinn_fair or not current_pinn_fair:
        return 70.0, "Pinnacle-Drift nicht bewertbar"
    drift_pp = (entry_pinn_fair - current_pinn_fair) * 100   # positiv = gegen uns
    if drift_pp <= -2:
        return 100.0, f"Pinnacle hat sich +{abs(drift_pp):.1f}pp FÜR uns bewegt ✨"
    if drift_pp <= 1:
        return 90.0, f"Pinnacle stabil ({drift_pp:+.1f}pp seit Entry)"
    if drift_pp <= 3:
        return 65.0, f"Pinnacle leicht gegen uns: {drift_pp:+.1f}pp"
    if drift_pp <= 6:
        return 30.0, f"Pinnacle deutlich gegen uns: {drift_pp:+.1f}pp"
    return 0.0, f"Pinnacle massiv gegen uns: {drift_pp:+.1f}pp — Sharps verkaufen"


def _score_clv(entry_poly_price: float, current_pinn_fair: float) -> tuple[float, str]:
    """
    CLV+ = wir haben einen besseren Preis bekommen als der aktuelle Pinnacle-Fair.
    entry_poly_price ist was wir bezahlt haben, current_pinn_fair ist aktueller fair.
    Wenn current_pinn_fair > entry_poly_price → CLV+ (gut).
    """
    if not entry_poly_price or not current_pinn_fair:
        return 70.0, "CLV nicht bewertbar"
    clv_pp = (current_pinn_fair - entry_poly_price) * 100
    if clv_pp >= 4:
        return 100.0, f"CLV+ {clv_pp:+.1f}pp — Sharps bestätigen unsere Sicht"
    if clv_pp >= 1:
        return 80.0, f"CLV+ {clv_pp:+.1f}pp"
    if clv_pp >= -1:
        return 55.0, f"CLV neutral ({clv_pp:+.1f}pp)"
    if clv_pp >= -3:
        return 30.0, f"CLV− {clv_pp:.1f}pp — Markt sieht es anders"
    return 10.0, f"CLV stark negativ {clv_pp:.1f}pp — wir sind auf der falschen Seite"


def _score_time_pressure(hours_until_match: float) -> tuple[float, str]:
    """Bei wenig Zeit zum Anpfiff: weniger Raum für Erholung wenn Edge schwach."""
    if hours_until_match is None:
        return 70.0, "Anpfiff-Zeit nicht bekannt"
    if hours_until_match > 24:
        return 100.0, f"{hours_until_match:.0f}h bis Anpfiff — viel Zeit"
    if hours_until_match > 6:
        return 85.0, f"{hours_until_match:.0f}h bis Anpfiff"
    if hours_until_match > 2:
        return 60.0, f"Nur {hours_until_match:.0f}h bis Anpfiff — wenig Raum"
    if hours_until_match >= 0:
        return 100.0, f"{hours_until_match:.0f}h — Hard-Close greift bald automatisch"
    return 100.0, "Match läuft / vorbei"


def _line_close(a, b, tol=0.01) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def resolve_current_market(bet: dict, current_fx: dict):
    """(current_edge_pp, current_poly, current_pinn_fair) für die Position — robust für
    ALLE Markttypen (16.06.2026). AH/BTTS über den EXAKTEN Token (mirror-immun), sonst
    Moneyline/O-U über fair_X/edge_X.

    WICHTIG: 'AH Heim -2.5' / 'AH Auswärts +0.5' dürfen NICHT als hw/aw klassifiziert
    werden — der frühere `"heim" in label`-Check fing sie fälschlich → die 1X2-Heimsieg-
    fair (z.B. 0.66) statt der AH-fair (~0.18) → Phantom-CLV +50pp / Phantom-Drift +46pp.
    Gibt (None, None, None) wenn nicht auflösbar → die Scores werten das als neutral."""
    lbl = (bet.get("market") or "").strip().lower()
    tok = bet.get("tokenId") or ""

    # ── Asian Handicap ──
    if lbl.startswith("ah "):
        ah = current_fx.get("ah_edges") or []
        for e in ah:                                   # 1) per exaktem Token
            toks = e.get("tokens") or []
            if tok and toks and toks[0] == tok:
                return (e.get("edge"), e.get("poly"), e.get("fair"))
        side = "home" if "heim" in lbl else ("away" if "ausw" in lbl else None)
        m = re.search(r"[-+]?\d+(?:[.,]\d+)?", lbl)    # 2) Fallback: Seite + Linie
        line = float(m.group().replace(",", ".")) if m else None
        if side and line is not None:
            for e in ah:
                if e.get("side") == side and _line_close(e.get("line"), line):
                    return (e.get("edge"), e.get("poly"), e.get("fair"))
        return (None, None, None)

    # ── BTTS (Ja/Nein) ──
    if lbl.startswith("beide teams"):
        bt = current_fx.get("poly_btts_tokens") or []
        if tok and len(bt) >= 2 and tok == bt[1]:
            return (current_fx.get("edge_btts_no"), current_fx.get("poly_btts_no"), current_fx.get("fair_btts_no"))
        if tok and len(bt) >= 1 and tok == bt[0]:
            return (current_fx.get("edge_btts"), current_fx.get("poly_btts"), current_fx.get("fair_btts"))
        if "nein" in lbl:                              # Fallback per Label
            return (current_fx.get("edge_btts_no"), current_fx.get("poly_btts_no"), current_fx.get("fair_btts_no"))
        return (current_fx.get("edge_btts"), current_fx.get("poly_btts"), current_fx.get("fair_btts"))

    # ── Moneyline / Over-Under ──
    market_key = (bet.get("marketKey") or "").lower()
    if market_key in ("hw", "aw", "dr", "o25", "u25", "o15", "u15", "o35", "u35"):
        mkt_k = market_key
    elif "heim" in lbl or "dnb: heim" in lbl: mkt_k = "hw"
    elif "ausw" in lbl or "dnb: ausw" in lbl: mkt_k = "aw"
    elif "unentsch" in lbl or "remis" in lbl: mkt_k = "dr"
    elif "über 2.5" in lbl or "over 2.5" in lbl: mkt_k = "o25"
    elif "unter 2.5" in lbl or "under 2.5" in lbl: mkt_k = "u25"
    elif "über 1.5" in lbl or "over 1.5" in lbl: mkt_k = "o15"
    elif "unter 1.5" in lbl or "under 1.5" in lbl: mkt_k = "u15"
    elif "über 3.5" in lbl or "over 3.5" in lbl: mkt_k = "o35"
    elif "unter 3.5" in lbl or "under 3.5" in lbl: mkt_k = "u35"
    else: mkt_k = "hw"
    return (current_fx.get(f"edge_{mkt_k}"), current_fx.get(f"poly_{mkt_k}"), current_fx.get(f"fair_{mkt_k}"))


# ── Health-Score-Berechnung ───────────────────────────────────────
def compute_health(bet: dict, current_fx: dict) -> dict:
    """
    Berechnet Health-Score für eine Position.
    bet: Eintrag aus wm_auto_bets_placed.bets[*]
    current_fx: Eintrag aus wm_poly_prices.allFixtures[*] (aktuell)
    """
    entry_edge_pp     = bet.get("edgePP") or bet.get("entryEdgePp") or 0
    entry_poly_price  = bet.get("polyPrice") or bet.get("entryPolyPrice") or 0
    entry_pinn_fair   = bet.get("pinnFair") or bet.get("entryPinnFair") or 0
    # Markt robust auflösen — AH/BTTS über Token, sonst Moneyline/O-U (16.06.2026).
    _edge, _poly, _fair = resolve_current_market(bet, current_fx)
    current_edge_pp   = _edge if isinstance(_edge, (int, float)) else None
    current_poly      = _poly if isinstance(_poly, (int, float)) else 0
    current_pinn_fair = _fair if isinstance(_fair, (int, float)) else None

    # Hours bis Match
    match_date = bet.get("matchDate") or current_fx.get("date") or ""
    hours_left = None
    if match_date:
        try:
            # Versuche ISO mit Zeit, sonst nur Datum
            if "T" in match_date:
                dt = datetime.fromisoformat(match_date.replace("Z", "+00:00"))
            else:
                dt = datetime.fromisoformat(f"{match_date[:10]}T19:00:00+00:00")
            hours_left = (dt - datetime.now(timezone.utc)).total_seconds() / 3600
        except Exception:
            pass

    # Faktor-Scores
    e_score, e_msg = _score_edge_persistence(entry_edge_pp, current_edge_pp)
    p_score, p_msg = _score_pinn_drift(entry_pinn_fair, current_pinn_fair)
    c_score, c_msg = _score_clv(entry_poly_price, current_pinn_fair)
    t_score, t_msg = _score_time_pressure(hours_left)

    factors = [
        {"name": "Edge-Persistenz",  "weight": W_EDGE,  "score": round(e_score, 1), "note": e_msg},
        {"name": "Pinnacle-Drift",   "weight": W_PINN,  "score": round(p_score, 1), "note": p_msg},
        {"name": "CLV-Status",       "weight": W_CLV,   "score": round(c_score, 1), "note": c_msg},
        {"name": "Time-Pressure",    "weight": W_TIME,  "score": round(t_score, 1), "note": t_msg},
    ]
    weighted = sum(f["weight"] * f["score"] for f in factors) / W_TOTAL
    total_score = round(weighted, 1)

    # Status + Recommendation
    if total_score >= SCORE_OK:
        status, reco = "ok", "Position halten — These intakt"
    elif total_score >= SCORE_WATCH:
        status, reco = "watch", "Beobachten — keine Aktion nötig"
    elif total_score >= SCORE_WARNING:
        status, reco = "warning", "Soft-Close überlegen — These bröckelt"
    else:
        status, reco = "critical", "Sell empfohlen — These zerbrochen"

    return {
        "key":            f"{current_fx.get('key','?')}-{bet.get('market','?')}",
        "matchKey":       current_fx.get("key"),
        "home":           current_fx.get("home") or bet.get("home"),
        "away":           current_fx.get("away") or bet.get("away"),
        "homeFlag":       current_fx.get("homeFlag") or _flag(current_fx.get("homeId") or bet.get("homeId")) or "🏳",
        "awayFlag":       current_fx.get("awayFlag") or _flag(current_fx.get("awayId") or bet.get("awayId")) or "🏳",
        "market":         bet.get("market", "?"),
        "score":          total_score,
        "status":         status,
        "factors":        factors,
        "recommendation": reco,
        "hoursLeft":      round(hours_left, 1) if hours_left is not None else None,
        "entryEdgePp":    entry_edge_pp,
        "currentEdgePp":  round(current_edge_pp, 1) if current_edge_pp else 0,
        "entryPolyPrice": entry_poly_price,
        "currentPolyPrice": round(current_poly, 4) if current_poly else 0,
        "lastUpdate":     _now_iso(),
    }


# ── Telegram ──────────────────────────────────────────────────────
def tg_send(text: str) -> bool:
    if SKIP_SEND or not TELEGRAM_TOKEN or not TRADES_CHAT_ID:
        print(f"ℹ️  Telegram-Send geskippt")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":                  TRADES_CHAT_ID,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode()).get("ok", False)
    except Exception as e:
        print(f"❌ TG-Send failed: {e}")
        return False


def format_alert(h: dict) -> str:
    icon = "🟠" if h["status"] == "warning" else "🔴"
    lines = [
        f"{icon} <b>POSITION-CHECK · {h['status'].upper()}</b>",
        "",
        f"{h['homeFlag']} <b>{h['home']}</b> vs <b>{h['away']}</b> {h['awayFlag']}",
        f"Pick: <b>{h['market']}</b>",
        f"Health-Score: <b>{h['score']}/100</b>",
        "",
        "<b>Was sich seit Entry geändert hat:</b>"
    ]
    for f in h["factors"]:
        if f["score"] >= 80: emoji = "✅"
        elif f["score"] >= 60: emoji = "🟡"
        elif f["score"] >= 40: emoji = "🟠"
        else: emoji = "🔴"
        lines.append(f"  {emoji} <b>{f['name']}</b> ({f['score']:.0f}): {f['note']}")
    if h.get("hoursLeft") is not None:
        lines.append(f"  ⏰ {h['hoursLeft']}h bis Anpfiff")
    lines.append("")
    lines.append(f"<b>Empfehlung:</b> {h['recommendation']}")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────
def main():
    bets_data = _load(BETS_FILE, {"bets": []})
    bets = bets_data.get("bets") or []
    open_bets = [b for b in bets if b.get("status") in (None, "open", "placed")
                                  and not b.get("sellPrice")]

    if not open_bets:
        print("ℹ️  Keine offenen Positionen — kein Health-Check nötig")
        _save(HEALTH_FILE, {"lastRun": _now_iso(), "positions": []})
        return

    poly_data = _load(POLY_FILE, {})
    poly_lookup = {f.get("key"): f for f in poly_data.get("allFixtures", []) if f.get("key")}

    # Dedup-State laden
    dedup = _load(DEDUP_FILE, {})

    print(f"📊 Position-Health-Check für {len(open_bets)} offene Positionen…")
    health_entries = []
    sent = 0
    skipped_dedup = 0

    for bet in open_bets:
        # Match key aus bet
        mk = bet.get("matchKey") or f"{bet.get('homeId','?')}-{bet.get('awayId','?')}"
        fx = poly_lookup.get(mk, {})
        if not fx:
            print(f"  ⚠️  {mk}: kein Polymarket-Eintrag — übersprungen")
            continue

        h = compute_health(bet, fx)
        health_entries.append(h)

        status_emoji = {"ok": "🟢", "watch": "🟡", "warning": "🟠", "critical": "🔴"}.get(h["status"], "⚪")
        print(f"  {status_emoji} {mk} {h['market']}: {h['score']}/100 ({h['status']})")

        # Telegram-Alert nur bei warning/critical, mit Dedup
        if h["status"] in ("warning", "critical"):
            dedup_key = f"{h['key']}_{h['status']}"
            last_sent = dedup.get(dedup_key)
            send = True
            if last_sent:
                # Re-Alert frühestens nach 6h (oder nie wenn status nicht eskaliert)
                try:
                    last_dt = datetime.fromisoformat(last_sent)
                    if (datetime.now(timezone.utc) - last_dt).total_seconds() < 6 * 3600:
                        send = False
                        skipped_dedup += 1
                except Exception:
                    pass
            if send:
                ok = tg_send(format_alert(h))
                if ok:
                    dedup[dedup_key] = _now_iso()
                    sent += 1

    _save(HEALTH_FILE, {"lastRun": _now_iso(), "positions": health_entries})
    _save(DEDUP_FILE, dedup)

    print(f"\n✅ {len(health_entries)} Positionen geprüft · {sent} Alerts gesendet · {skipped_dedup} dedup-skip")


if __name__ == "__main__":
    main()
