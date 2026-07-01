#!/usr/bin/env python3
"""
detect_wm_sharp_moves.py — CocoBet WM 2026 Sharp Radar  (v2)

Verbesserungen gegenüber v1:
  · Kumulativer Drift (Opening Line vs. aktuell) — nicht nur letzten 2 Snapshots
  · Deduplication: gleiches Signal wird nicht mehrfach gesendet
  · Bewegungs-Log: wm_sharp_moves_log.json speichert alle detektierten Moves
  · Cross-Reference: prüft ob Polymarket Edge in gleicher Richtung existiert
  · Datums-Filter: abgelaufene Spiele werden übersprungen
  · Mehr Kontext in Telegram-Karte

Schwellenwerte:
  ALERT_PP         ≥ 5pp  vs. letztem Snapshot  → normaler Sharp Alert
  ALERT_PP_BIG     ≥ 10pp vs. letztem Snapshot  → Steam Move (🔥)
  CUMUL_PP         ≥ 8pp  vs. Opening Line       → kumulativer Drift-Alert
  SNAP_WINDOW_DAYS  7     — wie viele Tage Snapshots in letzten N Tagen ansehen

Umgebungsvariablen:
  TELEGRAM_TOKEN          — Bot-Token (optional, ohne = Vorschau-Modus)
  TELEGRAM_TRADES_CHAT_ID — Privater Trades-Channel
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
import cocobet_dataset as D

BASE         = Path(__file__).parent
# Dataset-Modus (Single Source: cocobet_dataset): Liga → Liga-Moves.
_IS_LIGA     = D.is_liga()
HISTORY_FILE = D.file("wm2026-odds-history.json", "liga-odds-history.json")
WM_FILE      = D.data_file()
POLY_FILE    = BASE / "wm_poly_prices.json"
LOG_FILE     = BASE / "telegram-log.json"
MOVES_LOG    = D.file("wm_sharp_moves_log.json", "liga_sharp_moves_log.json")
DEDUP_FILE   = D.file("wm_sharp_dedup.json", "liga_sharp_dedup.json")

TELEGRAM_TOKEN = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
# CHANNEL-FIX 05.06.2026: Sharp-Move-Alerts wurden vom PUBLIC CocoBet-Channel
# in den privaten Trades-Channel verschoben — Pinnacle-Drift ist Trade-Info,
# nicht Community-Content. Folgt dem gleichen Pattern wie Auto-Bets/Sell-Alerts.
# GitHub Actions setzt fehlende Secrets als leeren String → `or "default"` Pattern.
CHAT_ID        = (os.environ.get("TELEGRAM_TRADES_CHAT_ID") or "").strip()

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

ALERT_PP         = _cfg("telegram", "alert_edge_min_pp",         5)
ALERT_PP_BIG     = _cfg("telegram", "alert_steam_pp",            10)
CUMUL_PP         = _cfg("telegram", "alert_cumul_pp",            8)
SNAP_WINDOW_DAYS = _cfg("telegram", "snap_window_days",          14)
MAX_ALERTS       = _cfg("telegram", "max_sharp_alerts_per_run",  6)


# ── Deduplication ─────────────────────────────────────────────────────────────
def _load_dedup() -> dict:
    """Lädt den Dedup-Store: {key → {"shift": x, "ts": ISO, "type": str}}"""
    try:
        if DEDUP_FILE.exists():
            with open(DEDUP_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_dedup(store: dict) -> None:
    with open(DEDUP_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)

def _dedup_key(match_key: str, alert_type: str) -> str:
    return f"{match_key}::{alert_type}"

def _is_duplicate(store: dict, dkey: str, new_shift: float) -> bool:
    """
    True wenn dasselbe Signal schon gesendet wurde UND der neue Shift
    nicht ≥2pp größer ist als der bereits gesendete.
    """
    entry = store.get(dkey)
    if not entry:
        return False
    old_shift = entry.get("shift", 0)
    # Erlaubt Re-Alert wenn Bewegung signifikant weitergeht (+2pp Progression)
    if new_shift >= old_shift + 2.0:
        return False
    # Gleiche Bewegungsrichtung und ähnliche Größe → Duplikat
    return True


# ── Moves-Log ────────────────────────────────────────────────────────────────
def _log_move(move: dict, alert_type: str) -> None:
    """Speichert erkannten Move in wm_sharp_moves_log.json."""
    try:
        log = []
        if MOVES_LOG.exists():
            with open(MOVES_LOG, encoding="utf-8") as f:
                log = json.load(f)
        entry = {
            "ts":         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type":       alert_type,
            "key":        move["key"],
            "homeId":     move["home_id"],
            "awayId":     move["away_id"],
            "maxShift":   move["max_shift"],
            "cumShift":   move.get("cumul_shift"),
            "hwShift":    move["hw_shift"],
            "drShift":    move["dr_shift"],
            "awShift":    move["aw_shift"],
            "isSteam":    move["is_steam"],
            "isCumul":    move.get("is_cumul", False),
            "polyEdge":   move.get("poly_edge"),
            "polyEdgeDir": move.get("poly_edge_dir"),
        }
        log.append(entry)
        log = log[-500:]   # Keep last 500 entries
        with open(MOVES_LOG, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  ⚠️  Move-Log failed: {e}")


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
    """Implied-Prob-Verschiebung in Prozentpunkten (positiv = Favorit wurde stärker).
    Delegiert seit 09.06.2026 an conviction_score.compute_pp_shift — single source of truth.
    """
    try:
        from conviction_score import compute_pp_shift
        return compute_pp_shift(old_odds, new_odds)
    except ImportError:
        # Fallback (Tests, isolierte Calls)
        old_p = impl_prob(old_odds)
        new_p = impl_prob(new_odds)
        if old_p is None or new_p is None:
            return 0.0
        return round(new_p - old_p, 2)


def odds_arrow(shift: float) -> str:
    if shift > 0:
        return "⬆️"
    elif shift < 0:
        return "⬇️"
    return "➡️"


def format_odds_change(market: str, old_o: float, new_o: float, shift: float,
                       cumul: float | None = None) -> str:
    direction = odds_arrow(shift)
    sign = f"+{shift:.1f}" if shift > 0 else f"{shift:.1f}"
    line = f"  {direction} {market}: {old_o:.2f} → {new_o:.2f}  ({sign}pp)"
    if cumul is not None and abs(cumul) > abs(shift) + 1:
        cumul_sign = f"+{cumul:.1f}" if cumul > 0 else f"{cumul:.1f}"
        line += f"  [kumulativ: {cumul_sign}pp]"
    return line


def find_active_picks(wm: dict, match_key: str) -> list[dict]:
    """Gibt aktive BET/ABWÄGEN-Picks für ein Spiel zurück."""
    picks = wm.get("picks", {})
    result = []
    for pk, pick_list in picks.items():
        parts = pk.split("-")
        if len(parts) >= 4:
            pk_match = f"{parts[2]}-{parts[3]}"
            if pk_match == match_key:
                for p in pick_list:
                    if p.get("verdict") in ("BET", "ABWÄGEN") and not p.get("result"):
                        result.append(p)
    return result


def pick_market_to_field(market: str) -> str | None:
    """Maps Pick-Market-String auf Odds-Snapshot-Feld.
    Granular: O15/O25/O35, U15/U25/U35, BTTS, Corner-Lines."""
    m = (market or "").lower()
    # Corners (vor "über"/"unter"-Check)
    if "ecken" in m or "corner" in m:
        return "cOver" if ("über" in m or "over" in m) else "cUnder"
    # BTTS
    if "beide" in m or "btts" in m:
        return "bttsN" if ("nein" in m or "no" in m) else "bttsY"
    # Tor-Linien (granular)
    if "über" in m or "uber" in m or "over" in m:
        if "1.5" in m or "1,5" in m: return "o15"
        if "3.5" in m or "3,5" in m: return "o35"
        return "o25"
    if "unter" in m or "under" in m:
        if "1.5" in m or "1,5" in m: return "u15"
        if "3.5" in m or "3,5" in m: return "u35"
        return "u25"
    # 1X2 / DC / DNB / AH (alle hängen am gleichen Outcome)
    if "heimsieg" in m or "home" in m:
        return "hw"
    if "auswärtssieg" in m or "away" in m:
        return "aw"
    if "unentschieden" in m or "draw" in m or "remis" in m:
        return "dr"
    return None


def _all_teams(wm: dict) -> dict:
    """Globale Team-Map über ALLE Gruppen. 30.06.2026 (Lucas: „🏳 CIV vs 🏳 NOR"-Alert): team_info
    verlangte beide Teams in DERSELBEN Gruppe → KO-Gegner stehen aber in verschiedenen Gruppen → 🏳."""
    t = {}
    for gdata in wm.get("groups", {}).values():
        for tm in gdata.get("teams", []):
            t[tm["id"]] = tm
    return t


def _find_fixture(wm: dict, home_id: str, away_id: str):
    """Fixture über Gruppen + KO-Runde. 30.06.2026 (Lucas: Steam-Alert für beendetes KO-Spiel): KO-Spiele
    liegen in koFixtures, nicht groups → match_kickoff fand nichts → der Anpfiff-Filter griff nicht →
    In-Play-Bewegung wurde als Steam-Move gepostet."""
    for gdata in wm.get("groups", {}).values():
        for fx in gdata.get("fixtures", []):
            if fx.get("home") == home_id and fx.get("away") == away_id:
                return fx
    for fx in (wm.get("koFixtures") or []):
        if fx.get("home") == home_id and fx.get("away") == away_id:
            return fx
    return None


def team_info(wm: dict, home_id: str, away_id: str) -> tuple[str, str, str, str]:
    teams = _all_teams(wm)
    h, a = teams.get(home_id), teams.get(away_id)
    if h and a:
        return h.get("flag", "🏳"), h.get("name", home_id), a.get("flag", "🏳"), a.get("name", away_id)
    return "🏳", home_id, "🏳", away_id


def match_date(wm: dict, home_id: str, away_id: str) -> str:
    fx = _find_fixture(wm, home_id, away_id)
    return fx.get("date", "") if fx else ""


def match_kickoff(wm: dict, home_id: str, away_id: str) -> str:
    """Echte UTC-Kickoff-Zeit (fx.kickoff) für ein Match (Gruppen + KO), falls vorhanden."""
    fx = _find_fixture(wm, home_id, away_id)
    return (fx.get("kickoff") or "") if fx else ""


def _load_poly_edges() -> dict:
    """
    Lädt Polymarket-Edge-Daten aus wm_poly_prices.json.
    Returns dict: {match_key → {edge_hw, edge_dr, edge_aw, bestEdge}}
    """
    if not POLY_FILE.exists():
        return {}
    try:
        with open(POLY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        result = {}
        for fx in data.get("allFixtures", []):
            key = fx.get("key", "")
            if key:
                result[key] = {
                    "edge_hw":  fx.get("edge_hw"),
                    "edge_dr":  fx.get("edge_dr"),
                    "edge_aw":  fx.get("edge_aw"),
                    "bestEdge": fx.get("bestEdge", 0),
                    "bestEdgeKey": fx.get("bestEdgeKey"),
                }
        return result
    except Exception as e:
        print(f"  ⚠️  Poly-Edges laden fehlgeschlagen: {e}")
        return {}


def _poly_context(poly_edges: dict, match_key: str, hw_shift: float, aw_shift: float) -> tuple[float | None, str | None]:
    """
    Gibt (poly_edge, direction_agreement) zurück:
      direction_agreement: "confirms" | "conflicts" | None
    """
    fx = poly_edges.get(match_key)
    if not fx:
        return None, None

    best = fx.get("bestEdge", 0) or 0
    if best < 2:
        return None, None

    best_key = fx.get("bestEdgeKey")
    if not best_key:
        return best, None

    # Prüfe ob Richtung der Pinn-Bewegung mit Poly-Edge übereinstimmt
    # hw_shift > 0 = Heimsieg wahrscheinlicher geworden
    # edge_hw > 0 = Poly unterbewertet Heimsieg
    hw_edge = fx.get("edge_hw", 0) or 0
    aw_edge = fx.get("edge_aw", 0) or 0

    if abs(hw_shift) >= ALERT_PP and hw_edge > 0 and hw_shift > 0:
        return best, "confirms"
    if abs(aw_shift) >= ALERT_PP and aw_edge > 0 and aw_shift > 0:
        return best, "confirms"
    if abs(hw_shift) >= ALERT_PP and hw_edge < 0 and hw_shift > 0:
        return best, "conflicts"
    if abs(aw_shift) >= ALERT_PP and aw_edge < 0 and aw_shift > 0:
        return best, "conflicts"

    return best, None


# ── Haupt-Analyse ─────────────────────────────────────────────────────────────
def analyze_moves(history: dict, wm: dict, poly_edges: dict) -> list[dict]:
    """
    Zwei Erkennungsmodi:
      1. Snapshot-zu-Snapshot: letzten 2 Snapshots → >= ALERT_PP
      2. Kumulativer Drift: Opening vs. aktuell → >= CUMUL_PP
    Gibt kombinierte Liste zurück, sortiert nach Stärke.
    """
    moves = []
    now_utc = datetime.now(timezone.utc)
    cutoff  = now_utc - timedelta(days=SNAP_WINDOW_DAYS)

    for key, raw_snaps in history.items():
        if key == "_meta" or not isinstance(raw_snaps, list):
            continue   # _meta (oddsFetchedAt) ist kein Fixture-Snapshot-Array
        # FIX 23.06.2026 (Lucas): Sharp Radar NUR auf dem Pinnacle-Strom rechnen. Seit dem
        # lead_lag-Fix (14.06.) liegen public/soft-Snaps in DERSELBEN History-Liste → der Radar
        # mischte beide Bücher: prev=Pinnacle vs curr=public ergab Phantom-Moves (reine Buch-
        # Margen-Differenz), und opening_snap war der älteste (Pinnacle-)Snap während curr ein
        # public war → falscher kumulativer Drift (DZA-AUT „29 Tage/62 Snaps/public", 2.37→2.30).
        # Soft-Bestätigung läuft separat über die Card-Soft-Bar. bk fehlt (Legacy) → als sharp werten.
        snaps = [s for s in raw_snaps if isinstance(s, dict) and s.get("bk") != "public"]
        if len(snaps) < 2:
            continue

        parts = key.split("-")
        if len(parts) < 2:
            continue
        home_id, away_id = parts[0], parts[1]

        # Spiel bereits ANGEPFIFFEN (live/vorbei)? Überspringen.
        # FIX 11.06.2026: vorher nur Datum < heute → ein heute schon laufendes
        # Spiel rutschte durch und löste „Steam"-Alerts auf In-Game-Bewegung aus
        # (Mexiko 1:0 → Live-Quoten crashen ≠ Pre-Match-Sharp-Money). Jetzt: echte
        # UTC-kickoff; ab Anpfiff kein Alert mehr.
        ko_str = match_kickoff(wm, home_id, away_id)
        if ko_str:
            try:
                if datetime.fromisoformat(str(ko_str).replace("Z", "+00:00")) <= now_utc:
                    continue
            except Exception:
                pass
        game_date_str = match_date(wm, home_id, away_id)
        if game_date_str:
            try:
                gd = date.fromisoformat(game_date_str[:10])
                if gd < date.today():
                    continue
            except Exception:
                pass

        # Filtere Snapshots auf relevantes Zeitfenster
        recent_snaps = [s for s in snaps
                        if _parse_ts(s.get("ts", "")) and _parse_ts(s.get("ts")) >= cutoff]
        if len(recent_snaps) < 2:
            # Fall back to last 2 available
            recent_snaps = snaps[-2:]

        prev = recent_snaps[-2]
        curr = recent_snaps[-1]

        # ── Modus 1: Snapshot-zu-Snapshot (1X2 + O/U + BTTS + Corner) ──────
        hw_shift   = pp_shift(prev.get("hw"),    curr.get("hw"))
        dr_shift   = pp_shift(prev.get("dr"),    curr.get("dr"))
        aw_shift   = pp_shift(prev.get("aw"),    curr.get("aw"))
        o15_shift  = pp_shift(prev.get("o15"),   curr.get("o15"))
        u15_shift  = pp_shift(prev.get("u15"),   curr.get("u15"))
        o25_shift  = pp_shift(prev.get("o25"),   curr.get("o25"))
        u25_shift  = pp_shift(prev.get("u25"),   curr.get("u25"))
        o35_shift  = pp_shift(prev.get("o35"),   curr.get("o35"))
        u35_shift  = pp_shift(prev.get("u35"),   curr.get("u35"))
        btts_shift = pp_shift(prev.get("bttsY"), curr.get("bttsY"))
        # Corner-Shifts: nur wenn beide Snapshots dieselbe cornerLine haben
        c_over_shift = c_under_shift = 0
        if prev.get("cornerLine") == curr.get("cornerLine"):
            c_over_shift  = pp_shift(prev.get("cOver"),  curr.get("cOver"))
            c_under_shift = pp_shift(prev.get("cUnder"), curr.get("cUnder"))
        max_shift  = max(abs(hw_shift), abs(dr_shift), abs(aw_shift),
                         abs(o15_shift), abs(u15_shift),
                         abs(o25_shift), abs(u25_shift),
                         abs(o35_shift), abs(u35_shift),
                         abs(btts_shift),
                         abs(c_over_shift), abs(c_under_shift))

        # ── Modus 2: Kumulativer Drift (Opening → Aktuell) ─────────────────
        opening_snap = snaps[0]
        cumul_hw   = pp_shift(opening_snap.get("hw"),    curr.get("hw"))
        cumul_dr   = pp_shift(opening_snap.get("dr"),    curr.get("dr"))
        cumul_aw   = pp_shift(opening_snap.get("aw"),    curr.get("aw"))
        cumul_o15  = pp_shift(opening_snap.get("o15"),   curr.get("o15"))
        cumul_u15  = pp_shift(opening_snap.get("u15"),   curr.get("u15"))
        cumul_o25  = pp_shift(opening_snap.get("o25"),   curr.get("o25"))
        cumul_u25  = pp_shift(opening_snap.get("u25"),   curr.get("u25"))
        cumul_o35  = pp_shift(opening_snap.get("o35"),   curr.get("o35"))
        cumul_u35  = pp_shift(opening_snap.get("u35"),   curr.get("u35"))
        cumul_btts = pp_shift(opening_snap.get("bttsY"), curr.get("bttsY"))
        cumul_cOv = cumul_cUn = 0
        if opening_snap.get("cornerLine") == curr.get("cornerLine"):
            cumul_cOv = pp_shift(opening_snap.get("cOver"),  curr.get("cOver"))
            cumul_cUn = pp_shift(opening_snap.get("cUnder"), curr.get("cUnder"))
        cumul_max  = max(abs(cumul_hw), abs(cumul_dr), abs(cumul_aw),
                         abs(cumul_o15), abs(cumul_u15),
                         abs(cumul_o25), abs(cumul_u25),
                         abs(cumul_o35), abs(cumul_u35),
                         abs(cumul_btts),
                         abs(cumul_cOv), abs(cumul_cUn))
        is_cumul = (cumul_max >= CUMUL_PP and max_shift < ALERT_PP)  # nur wenn nicht bereits snap-alert

        if max_shift < ALERT_PP and not is_cumul:
            continue

        # Zeit seit letztem Snapshot
        ts_prev = _parse_ts(prev.get("ts", ""))
        ts_curr = _parse_ts(curr.get("ts", ""))
        hours_since = None
        if ts_prev and ts_curr:
            hours_since = round((ts_curr - ts_prev).total_seconds() / 3600, 1)

        # Days since first snapshot (age of drift)
        ts_first = _parse_ts(snaps[0].get("ts", ""))
        drift_days = None
        if ts_first:
            drift_days = max(1, round((now_utc - ts_first).total_seconds() / 86400, 0))

        # Aktive Picks
        active_picks = find_active_picks(wm, key)
        pick_affected = []
        for p in active_picks:
            field = pick_market_to_field(p.get("market", ""))
            # Field → entsprechender Shift-Wert. Dict-Lookup statt verschachtelte ifs.
            _shifts = {
                "hw": hw_shift, "dr": dr_shift, "aw": aw_shift,
                "o15": o15_shift, "u15": u15_shift,
                "o25": o25_shift, "u25": u25_shift,
                "o35": o35_shift, "u35": u35_shift,
                "bttsY": btts_shift, "bttsN": -btts_shift,  # invertiert
                "cOver": c_over_shift, "cUnder": c_under_shift,
            }
            shift_val = _shifts.get(field)
            if shift_val is not None and abs(shift_val) >= ALERT_PP:
                pick_affected.append((p, shift_val, field))

        # Poly-Cross-Reference
        poly_edge, poly_dir = _poly_context(poly_edges, key, hw_shift, aw_shift)

        effective_shift = cumul_max if is_cumul else max_shift

        moves.append({
            "key":          key,
            "home_id":      home_id,
            "away_id":      away_id,
            "prev":         prev,
            "curr":         curr,
            "opening_snap": opening_snap,
            "hw_shift":     hw_shift,
            "dr_shift":     dr_shift,
            "aw_shift":     aw_shift,
            "o15_shift":    o15_shift,
            "u15_shift":    u15_shift,
            "o25_shift":    o25_shift,
            "u25_shift":    u25_shift,
            "o35_shift":    o35_shift,
            "u35_shift":    u35_shift,
            "btts_shift":   btts_shift,
            "c_over_shift": c_over_shift,
            "c_under_shift": c_under_shift,
            "corner_line":  curr.get("cornerLine"),
            "cumul_hw":     cumul_hw,
            "cumul_dr":     cumul_dr,
            "cumul_aw":     cumul_aw,
            "cumul_o15":    cumul_o15,
            "cumul_u15":    cumul_u15,
            "cumul_o25":    cumul_o25,
            "cumul_u25":    cumul_u25,
            "cumul_o35":    cumul_o35,
            "cumul_u35":    cumul_u35,
            "cumul_btts":   cumul_btts,
            "cumul_c_over": cumul_cOv,
            "cumul_c_under": cumul_cUn,
            "cumul_shift":  cumul_max,
            "max_shift":    max_shift,
            "effective_shift": effective_shift,
            "hours_since":  hours_since,
            "drift_days":   drift_days,
            "active_picks": active_picks,
            "pick_affected": pick_affected,
            "is_steam":     max_shift >= ALERT_PP_BIG,
            "is_cumul":     is_cumul,
            "poly_edge":    poly_edge,
            "poly_edge_dir": poly_dir,
            "snap_count":   len(snaps),
        })

    # Stärkste Moves zuerst (Steam > Cumul > Sharp)
    moves.sort(key=lambda x: (x["is_steam"], x["effective_shift"]), reverse=True)
    return moves


def _parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return None


# ── Telegram Card Builder ─────────────────────────────────────────────────────
def build_alert_card(move: dict, wm: dict) -> str:
    home_id  = move["home_id"]
    away_id  = move["away_id"]
    hf, hn, af, an = team_info(wm, home_id, away_id)
    g_date   = match_date(wm, home_id, away_id)
    prev     = move["prev"]
    curr     = move["curr"]
    is_steam = move["is_steam"]
    is_cumul = move["is_cumul"]
    hours    = move["hours_since"]
    drift_d  = move.get("drift_days")

    if is_steam:
        header = "🔥 <b>STEAM MOVE</b>"
    elif is_cumul:
        header = "📈 <b>Kumulativer Drift erkannt</b>"
    else:
        header = "📡 <b>Sharp Move detektiert</b>"

    date_str = f" · {g_date}" if g_date else ""

    lines = [
        header,
        f"{hf} <b>{hn}</b> vs {af} <b>{an}</b>{date_str}",
        "",
    ]

    # Märkte mit signifikanter Snapshot-Bewegung (1X2 + O/U + BTTS)
    snap_shown = False
    for field, label, old_o, new_o, shift, cumul in [
        ("hw",    "Heimsieg",       prev.get("hw"),    curr.get("hw"),    move["hw_shift"],   move["cumul_hw"]),
        ("dr",    "Unentschieden",  prev.get("dr"),    curr.get("dr"),    move["dr_shift"],   move["cumul_dr"]),
        ("aw",    "Auswärtssieg",   prev.get("aw"),    curr.get("aw"),    move["aw_shift"],   move["cumul_aw"]),
        ("o25",   "Over 2.5",       prev.get("o25"),   curr.get("o25"),   move["o25_shift"],  move["cumul_o25"]),
        ("u25",   "Under 2.5",      prev.get("u25"),   curr.get("u25"),   move["u25_shift"],  move["cumul_u25"]),
        ("bttsY", "BTTS Ja",        prev.get("bttsY"), curr.get("bttsY"), move["btts_shift"], move["cumul_btts"]),
    ]:
        if old_o and new_o and (abs(shift) >= ALERT_PP or abs(cumul) >= CUMUL_PP):
            lines.append(format_odds_change(
                label, old_o, new_o, shift,
                cumul if abs(cumul) >= CUMUL_PP else None
            ))
            snap_shown = True

    # Kumulativer Drift auch bei kleinen Einzelschritten anzeigen
    if is_cumul and not snap_shown:
        op = move["opening_snap"]
        for field, label, old_o, new_o, cumul in [
            ("hw",    "Heimsieg",      op.get("hw"),    curr.get("hw"),    move["cumul_hw"]),
            ("dr",    "Unentschieden", op.get("dr"),    curr.get("dr"),    move["cumul_dr"]),
            ("aw",    "Auswärtssieg",  op.get("aw"),    curr.get("aw"),    move["cumul_aw"]),
            ("o25",   "Over 2.5",      op.get("o25"),   curr.get("o25"),   move["cumul_o25"]),
            ("u25",   "Under 2.5",     op.get("u25"),   curr.get("u25"),   move["cumul_u25"]),
            ("bttsY", "BTTS Ja",       op.get("bttsY"), curr.get("bttsY"), move["cumul_btts"]),
        ]:
            if old_o and new_o and abs(cumul) >= CUMUL_PP:
                sign = f"+{cumul:.1f}" if cumul > 0 else f"{cumul:.1f}"
                lines.append(f"  {odds_arrow(cumul)} {label}: {old_o:.2f} → {new_o:.2f}  ({sign}pp seit Erstnotiz)")

    lines.append("")

    # Drift context
    if drift_d and drift_d > 1:
        lines.append(f"⏳ Zeitraum: {int(drift_d)} Tage · {move['snap_count']} Snapshots")

    # Poly Cross-Reference
    poly_edge = move.get("poly_edge")
    poly_dir  = move.get("poly_edge_dir")
    if poly_edge and poly_edge >= 2:
        if poly_dir == "confirms":
            lines.append(f"✅ <b>Polymarket Edge +{poly_edge:.1f}pp</b> — bestätigt Sharp Move!")
        elif poly_dir == "conflicts":
            lines.append(f"⚡ <b>Polymarket Edge +{poly_edge:.1f}pp</b> — läuft gegensätzlich zur Pinn-Bewegung")
        else:
            lines.append(f"💹 Polymarket Edge +{poly_edge:.1f}pp vorhanden")

    # Context: Pick betroffen?
    if move["pick_affected"]:
        for p, shift, field in move["pick_affected"]:
            if shift > 0:
                lines.append(f"✅ <b>Markt bestätigt unseren Pick:</b> {p['market']} @{p.get('odds', '?')}")
            else:
                lines.append(f"⚠️ <b>Markt läuft GEGEN unseren Pick:</b> {p['market']} @{p.get('odds', '?')}")
    else:
        lines.append("ℹ️ Kein aktiver Pick betroffen")

    bk = curr.get("bk") or curr.get("bookmaker", "?")
    if hours:
        lines.append(f"\n⏱️ Letzte Bewegung: vor {hours}h · {bk}")
    else:
        lines.append(f"\n📚 Bookmaker: {bk}")

    lines.append("\n🤖 CocoBet Sharp Radar · WM 2026")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=== detect_wm_sharp_moves.py v2 ===")

    if not HISTORY_FILE.exists():
        print("  ℹ️  Keine History-Datei — noch keine Snapshots vorhanden")
        return

    with open(HISTORY_FILE, encoding="utf-8") as f:
        history = json.load(f)

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    poly_edges = _load_poly_edges()
    dedup      = _load_dedup()

    print(f"  History: {len(history)} Fixtures mit Snapshots")
    print(f"  Poly-Edges geladen: {len(poly_edges)} Fixtures")

    moves = analyze_moves(history, wm, poly_edges)

    if not moves:
        print("  ✅  Keine signifikanten Moves detektiert")
        return

    print(f"\n  🔔  {len(moves)} Move(s) gefunden:")
    for m in moves:
        tags = []
        if m["is_steam"]:   tags.append("🔥 STEAM")
        if m["is_cumul"]:   tags.append("📈 DRIFT")
        print(f"    {m['key']:<16}  snap={m['max_shift']:.1f}pp  cumul={m['cumul_shift']:.1f}pp  {' '.join(tags)}")

    # ── Dedup + Senden ────────────────────────────────────────────────────────
    sent  = 0
    skipped = 0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for m in moves[:MAX_ALERTS]:
        alert_type = "steam" if m["is_steam"] else ("cumul" if m["is_cumul"] else "sharp")
        dkey = _dedup_key(m["key"], alert_type)
        eff  = m["effective_shift"]

        if _is_duplicate(dedup, dkey, eff):
            print(f"  ⏭️  Duplikat: {m['key']} ({alert_type}, {eff:.1f}pp — bereits gesendet)")
            skipped += 1
            continue

        card = build_alert_card(m, wm)
        ok   = tg_send(card)

        if ok:
            sent += 1
            dedup[dkey] = {"shift": eff, "ts": now_iso, "type": alert_type}
            _log_move(m, alert_type)
            _log_send(
                alert_type + "_alert",
                card.split("\n")[0],
                {"match": m["key"], "shift": round(eff, 1), "steam": m["is_steam"], "cumul": m["is_cumul"]},
            )

    _save_dedup(dedup)
    print(f"\n  ✅  {sent} gesendet  ·  {skipped} Duplikate übersprungen")


if __name__ == "__main__":
    main()
