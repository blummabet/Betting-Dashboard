#!/usr/bin/env python3
"""
fetch_betfair_betwatch.py — Betfair-Exchange-Odds + gematchte VOLUMINA via Betwatch (28.07.2026, Lucas).

Betfair direkt geht aus Österreich nicht (Konto-Geoblock) → Umweg über Betwatch (betwatch.fr), ein
EU-Aggregator, der Betfair-Odds UND Volumina liefert. Nur Football (100€-Tarif = alle Fußball-Ligen).

Zwei Produkte hängen dran:
  A) Top-5 + MLS: volumen-gewichtetes Sharp-Signal (Steam, Betfair-vs-Pinnacle, besserer CLV).
  B) Alle anderen Ligen (HT-Fokus): wo liegt das Geld / auffällige einseitige Bewegungen +
     Liga-Profitabilitäts-Backtest.

## API (Django REST, Token-Auth) — an echten Antworten verifiziert 28.07.2026
  Header:  Authorization: Token {BETWATCH_KEY}
  Base:    https://betwatch.fr/api/v1
  GET /football/events            → [{match_id, teams{v1,v2}, league, country, kickoff, live_info}]
  GET /football/event/{match_id}  → {..., league_id, markets:[{market_id, name, average_volume,
                                     last_checked, runners:[{runner_id, name, odd, volume}]}]}
  GET /football/live              → wie events + live_info{time,is_ht,goal_v1,goal_v2,red_*,finished} + markets
  Märkte: "Match Odds" · "Both teams to Score?" · "Over/Under X.5 Goals" (0.5–8.5) · "Correct Score" ·
          "Draw no Bet" · "Half Time" · "First Half Goals 0.5/1.5/2.5" · "Half Time/Full Time".
  average_volume = gematchtes £-Volumen je Markt (der Money-Indikator). runner.odd = Betfair-Preis.

## Ausgabe
  betfair_prices.json   — {matches:[snapshot...], _meta:{generatedAt, n, live}}.
  betfair_history.json  — {matchId: [{ts, totalVol, mo:{hw,dr,aw,vol}}...], _meta}. Für Steam + Volumen-Delta.

## Env
  BETWATCH_KEY          — API-Token (GitHub-Secret). Ohne Key: No-Op (kein Wipe).
  BETWATCH_MAX_DETAIL   — Deckel für /event/{id}-Detailcalls je Lauf (Default 150).
  BETWATCH_WINDOW_H     — Prematch-Fenster in Std. für Detailcalls (Default 26).

Reiner Kern (parse_events, devig_1x2, build_snapshot, select_ids, append_history) ist netz-frei/testbar;
nur main() ruft die API. Defensiv: bei Fetch-Fehler NIE gute Daten überschreiben (Wipe-Guard).
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRICES_FILE = BASE / "betfair_prices.json"
HISTORY_FILE = BASE / "betfair_history.json"
API_BASE = "https://betwatch.fr/api/v1"
KEY = (os.environ.get("BETWATCH_KEY") or "").strip()
HTTP_TIMEOUT = 20
MAX_DETAIL = int(os.environ.get("BETWATCH_MAX_DETAIL") or 150)
WINDOW_H = float(os.environ.get("BETWATCH_WINDOW_H") or 26)
HIST_KEEP_H = 72
HIST_MAX_POINTS = 80


def _now():
    return datetime.now(timezone.utc)


# ── pure parsing / helpers (netz-frei, testbar) ───────────────────────────────
def parse_events(data):
    """events/live-Liste → [{matchId, home, away, league, country, kickoff, live}]."""
    out = []
    for e in (data or []):
        if not isinstance(e, dict):
            continue
        mid = e.get("match_id")
        if mid is None:
            continue
        t = e.get("teams") or {}
        out.append({
            "matchId": mid, "home": t.get("v1"), "away": t.get("v2"),
            "league": e.get("league"), "country": e.get("country"),
            "kickoff": e.get("kickoff"), "live": bool(e.get("live_info") or {}),
        })
    return out


def devig_1x2(hw, dr, aw):
    """Betfair-1X2-Odds → faire Wahrscheinlichkeit (Overround raus). None wenn unvollständig/unplausibel.
    Exchange-Overround ist winzig (~1.00–1.05); grobe Plausibilitätsgrenze fängt Platzhalter ab."""
    try:
        ih, idr, ia = 1.0 / float(hw), 1.0 / float(dr), 1.0 / float(aw)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    s = ih + idr + ia
    if not (0.90 < s < 1.60):
        return None
    return {"home": round(ih / s, 4), "draw": round(idr / s, 4), "away": round(ia / s, 4)}


def build_snapshot(ev, now=None):
    """event/{id}-Antwort → kompakter Snapshot mit ALLEN Märkten (roh) + abgeleitetem 1X2-Fair +
    Gesamt-Volumen. REIN/testbar. Behält HT/First-Half/O-U für die Signal-/Dashboard-Schicht."""
    now = now or _now()
    teams = ev.get("teams") or {}
    home, away = teams.get("v1"), teams.get("v2")
    markets, total_vol = {}, 0.0
    for m in (ev.get("markets") or []):
        if not isinstance(m, dict) or not m.get("name"):
            continue
        av = m.get("average_volume")
        if isinstance(av, (int, float)):
            total_vol += av
        markets[m["name"]] = {
            "vol": av,
            "runners": {r.get("name"): r.get("odd")
                        for r in (m.get("runners") or []) if isinstance(r, dict) and r.get("name")},
        }
    mo = markets.get("Match Odds")
    hw = dr = aw = vol1x2 = fair = None
    if mo:
        rr = mo["runners"]
        vol1x2 = mo["vol"]
        hw, dr, aw = rr.get(home), rr.get("The Draw"), rr.get(away)
        fair = devig_1x2(hw, dr, aw)
    return {
        "matchId": ev.get("match_id"), "home": home, "away": away,
        "league": ev.get("league"), "leagueId": ev.get("league_id"), "country": ev.get("country"),
        "kickoff": ev.get("kickoff"), "liveInfo": ev.get("live_info") or {},
        "capturedAt": now.isoformat(), "totalVol": round(total_vol),
        "mo": {"hw": hw, "dr": dr, "aw": aw, "vol": vol1x2, "fair": fair},
        "markets": markets,
    }


def select_ids(parsed, now=None, window_h=WINDOW_H, cap=MAX_DETAIL):
    """Welche Matches bekommen einen (teuren) Detail-Call: alle LIVE (haben HT-Märkte + In-Play-
    Volumen) zuerst, dann Prematch mit Anpfiff im Fenster. Gedeckelt. REIN/testbar."""
    now = now or _now()
    horizon = now + timedelta(hours=window_h)

    def _ko(e):
        try:
            return datetime.fromisoformat(str(e.get("kickoff")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    live = [e for e in parsed if e.get("live")]
    pre = []
    for e in parsed:
        if e.get("live"):
            continue
        k = _ko(e)
        if k is not None and now <= k <= horizon:
            pre.append((k, e))
    pre.sort(key=lambda x: x[0])
    ordered = [e["matchId"] for e in live] + [e["matchId"] for _, e in pre]
    # dedup, Reihenfolge erhalten
    seen, out = set(), []
    for mid in ordered:
        if mid not in seen:
            seen.add(mid)
            out.append(mid)
    return out[:cap]


def append_history(hist, snap, now=None, keep_h=HIST_KEEP_H, max_points=HIST_MAX_POINTS):
    """Zeitreihe je Match fortschreiben (totalVol + 1X2 + Anpfiff) → Steam/Volumen-Delta später.
    REIN/testbar. Prunt Matches, die seit keep_h nicht mehr gesehen wurden."""
    now = now or _now()
    hist = dict(hist or {})
    mid = str(snap.get("matchId"))
    if mid in ("None", ""):
        return hist
    pt = {"ts": now.isoformat(), "totalVol": snap.get("totalVol"),
          "mo": {k: (snap.get("mo") or {}).get(k) for k in ("hw", "dr", "aw", "vol")},
          "kickoff": snap.get("kickoff")}
    arr = list(hist.get(mid) or [])
    arr.append(pt)
    hist[mid] = arr[-max_points:]
    return hist


def prune_history(hist, now=None, keep_h=HIST_KEEP_H):
    now = now or _now()
    cutoff = now - timedelta(hours=keep_h)
    out = {}
    for mid, arr in (hist or {}).items():
        if mid == "_meta" or not isinstance(arr, list) or not arr:
            continue
        try:
            last = datetime.fromisoformat(str(arr[-1].get("ts")).replace("Z", "+00:00"))
        except (ValueError, TypeError, AttributeError):
            last = None
        if last is None or last >= cutoff:
            out[mid] = arr
    return out


# ── network (nur main) ────────────────────────────────────────────────────────
def _get(path):
    req = urllib.request.Request(API_BASE + path,
                                 headers={"Authorization": f"Token {KEY}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  ⚠️  Betwatch HTTP {e.code} bei {path[:48]}")
        return None
    except Exception as e:
        print(f"  ⚠️  Betwatch Fehler bei {path[:48]}: {e}")
        return None


def _load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    print("=== fetch_betfair_betwatch.py ===")
    if not KEY:
        print("  ℹ️  BETWATCH_KEY nicht gesetzt — übersprungen (kein Wipe).")
        return 0
    now = _now()
    events = _get("/football/events")
    live = _get("/football/live")
    if events is None and live is None:
        print("  ⚠️  Betwatch nicht erreichbar — bestehende Dateien bleiben (kein Wipe).")
        return 1
    by_id = {}
    for e in parse_events(events or []):
        by_id[e["matchId"]] = e
    for e in parse_events(live or []):
        by_id[e["matchId"]] = e   # live überschreibt prematch
    ids = select_ids(list(by_id.values()), now=now)
    print(f"  {len(by_id)} Events · {sum(1 for e in by_id.values() if e['live'])} live · "
          f"{len(ids)} Detail-Calls (Fenster {WINDOW_H:.0f}h, Cap {MAX_DETAIL})")

    snaps, hist = [], prune_history(_load(HISTORY_FILE), now=now)
    for mid in ids:
        d = _get(f"/football/event/{mid}")
        if not isinstance(d, dict) or not d.get("markets"):
            continue
        snap = build_snapshot(d, now=now)
        snaps.append(snap)
        hist = append_history(hist, snap, now=now)

    if not snaps:
        print("  ⚠️  Keine Snapshots gebaut — bestehende Preise bleiben (kein Wipe).")
        return 1

    PRICES_FILE.write_text(json.dumps(
        {"_meta": {"generatedAt": now.isoformat(), "n": len(snaps),
                   "live": sum(1 for s in snaps if s.get("liveInfo"))},
         "matches": snaps}, ensure_ascii=False, indent=1), encoding="utf-8")
    hist.setdefault("_meta", {})["updatedAt"] = now.isoformat()
    HISTORY_FILE.write_text(json.dumps(hist, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  ✅  {len(snaps)} Match-Snapshots → betfair_prices.json · History fortgeschrieben")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
