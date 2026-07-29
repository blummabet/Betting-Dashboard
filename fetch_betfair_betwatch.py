#!/usr/bin/env python3
"""
fetch_betfair_betwatch.py — Betfair-Exchange-Odds + gematchte VOLUMINA via Betwatch (28.07.2026, Lucas).

Betfair direkt geht aus Österreich nicht (Konto-Geoblock) → Umweg über Betwatch (betwatch.fr), ein
EU-Aggregator, der Betfair-Odds UND Volumina liefert. Nur Football (100€-Tarif = alle Fußball-Ligen).

Zwei Produkte hängen dran:
  A) Top-5 + MLS: volumen-gewichtetes Sharp-Signal (Steam, Betfair-vs-Pinnacle, besserer CLV).
  B) Alle anderen Ligen (HT-Fokus): wo liegt das Geld / auffällige einseitige Bewegungen +
     Liga-Profitabilitäts-Backtest.

## API (Django REST) — an echten Antworten verifiziert 29.07.2026
  Auth:    ?key={BETWATCH_KEY}  (Query-Param! Authorization-Header → HTTP 403)
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
import re
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
# Top-5 + MLS mit LÄNGEREM Vorlauf erfassen (72h statt 26h), sonst tauchen sie erst ~1 Tag vor
# Anpfiff auf — für Signale/Triple zu spät (29.07.2026, Lucas). Betwatch-Namen sind land-präfixiert
# ("German Bundesliga" …). Modest gehalten: 3 Tage, keine 2 Wochen.
PRIORITY_WINDOW_H = float(os.environ.get("BETWATCH_PRIO_WINDOW_H") or 72)
PRIORITY_RX = re.compile(r"(german bundesliga|english premier league|spanish la ?liga|italian serie a|"
                         r"french ligue 1|major league soccer|\bmls\b)", re.I)
HIST_KEEP_H = 72
HIST_MAX_POINTS = 80
# Für den „frisches Geld"-Zufluss im Dashboard: je Snapshot das Markt-Volumen der Dashboard-Märkte
# mitschreiben (mkv). Nur diese 7 (kompakt) — und nur auf den letzten 2 History-Punkten behalten
# (Delta = letzter minus vorletzter), damit die History nicht aufbläht.
TRACKED_MARKETS = ["Match Odds", "Over/Under 2.5 Goals", "Over/Under 3.5 Goals",
                   "Both teams to Score?", "Half Time", "First Half Goals 0.5", "First Half Goals 1.5"]
MKV_KEEP_POINTS = 2


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
        # Runner als geordnete Liste MIT Einzel-Volumen (das ECHTE gematchte Geld je Ausgang —
        # wie in Betwatchs Money-Ansicht).
        runners = [
            {"name": r.get("name"), "odd": r.get("odd"), "vol": r.get("volume")}
            for r in (m.get("runners") or []) if isinstance(r, dict) and r.get("name")
        ]
        # Markt-Geld = SUMME der Runner-Volumina. NICHT average_volume — das ist eine andere,
        # viel größere Kennzahl (33–1261× je Markt) und passt nie zur Ausgangs-Verteilung (29.07.2026,
        # Lucas: „24K oben, aber 10€ je Ausgang?"). Verifiziert an echten Betwatch-Antworten.
        rsum = sum((r["vol"] or 0) for r in runners if isinstance(r.get("vol"), (int, float)))
        total_vol += rsum
        markets[m["name"]] = {"vol": round(rsum, 2), "runners": runners}
    mo = markets.get("Match Odds")
    hw = dr = aw = vol1x2 = fair = None
    if mo:
        rr = {x["name"]: x["odd"] for x in mo["runners"]}   # name→odd für 1X2-Ableitung
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


def select_ids(parsed, now=None, window_h=WINDOW_H, cap=MAX_DETAIL, prio_window_h=PRIORITY_WINDOW_H):
    """Welche Matches bekommen einen (teuren) Detail-Call: alle LIVE zuerst, dann Top-5/MLS im WEITEN
    Fenster (prio_window_h, ~3 Tage), dann alle anderen im Standard-Fenster (window_h, 26h). So werden
    die Signal-Ligen früh erfasst, ohne den Cap mit obskuren Ligen zu fluten. Gedeckelt. REIN/testbar."""
    now = now or _now()
    horizon = now + timedelta(hours=window_h)
    prio_horizon = now + timedelta(hours=prio_window_h)

    def _ko(e):
        try:
            return datetime.fromisoformat(str(e.get("kickoff")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    live = [e for e in parsed if e.get("live")]
    prio, pre = [], []
    for e in parsed:
        if e.get("live"):
            continue
        k = _ko(e)
        if k is None:
            continue
        if PRIORITY_RX.search(str(e.get("league") or "")) and now <= k <= prio_horizon:
            prio.append((k, e))
        elif now <= k <= horizon:
            pre.append((k, e))
    prio.sort(key=lambda x: x[0])
    pre.sort(key=lambda x: x[0])
    ordered = ([e["matchId"] for e in live] + [e["matchId"] for _, e in prio]
               + [e["matchId"] for _, e in pre])
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
    # Markt-Volumina der Dashboard-Märkte (für „frisches Geld"-Zufluss).
    mkv = {}
    for name in TRACKED_MARKETS:
        mk = (snap.get("markets") or {}).get(name)
        if isinstance(mk, dict) and isinstance(mk.get("vol"), (int, float)):
            mkv[name] = mk["vol"]
    pt = {"ts": now.isoformat(), "totalVol": snap.get("totalVol"),
          "mo": {k: (snap.get("mo") or {}).get(k) for k in ("hw", "dr", "aw", "vol")},
          "kickoff": snap.get("kickoff"), "mkv": mkv}
    arr = list(hist.get(mid) or [])
    arr.append(pt)
    arr = arr[-max_points:]
    # mkv nur auf den letzten MKV_KEEP_POINTS Punkten behalten (Platz sparen — Delta braucht nur 2).
    for p in arr[:-MKV_KEEP_POINTS]:
        if isinstance(p, dict):
            p.pop("mkv", None)
    hist[mid] = arr
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
# Cloudflare weist Requests ohne echten User-Agent teils mit 403 ab → Browser-Header mitschicken.
_BASE_HEADERS = {
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-AT,de;q=0.9,en;q=0.8",
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
}
# Auth-Varianten in Reihenfolge probieren; die erste, die 200 liefert, wird gemerkt + geloggt.
_AUTH_ORDER = ["query", "token", "apikey", "bearer"]
_AUTH = {"mode": None}


def _build_req(path, mode):
    headers = dict(_BASE_HEADERS)
    url = API_BASE + path
    if mode == "query":
        sep = "&" if "?" in path else "?"
        url = f"{url}{sep}key={KEY}"
    elif mode == "token":
        headers["Authorization"] = f"Token {KEY}"
    elif mode == "apikey":
        headers["X-API-Key"] = KEY
    elif mode == "bearer":
        headers["Authorization"] = f"Bearer {KEY}"
    return urllib.request.Request(url, headers=headers)


def _get(path):
    modes = [_AUTH["mode"]] if _AUTH["mode"] else _AUTH_ORDER
    last_code = None
    for mode in modes:
        try:
            with urllib.request.urlopen(_build_req(path, mode), timeout=HTTP_TIMEOUT) as r:
                data = json.loads(r.read().decode("utf-8"))
                if _AUTH["mode"] != mode:
                    _AUTH["mode"] = mode
                    print(f"  🔑 Auth-Methode akzeptiert: {mode}")
                return data
        except urllib.error.HTTPError as e:
            last_code = e.code
            continue   # nächste Auth-Variante probieren
        except Exception as e:
            print(f"  ⚠️  Betwatch Fehler bei {path[:48]}: {e}")
            return None
    print(f"  ⚠️  Betwatch HTTP {last_code} bei {path[:48]} — alle Auth-Methoden abgelehnt "
          f"(Key falsch/abgelaufen?)")
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
