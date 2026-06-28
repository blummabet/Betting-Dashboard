#!/usr/bin/env python3
"""
fetch_liga_odds.py — Pinnacle-Quoten für die Top-5-Ligen in liga-data.json (25.06.2026, Lucas).

Phase 1 des Liga-auf-WM-Stack-Umbaus: holt 1X2 + Über/Unter 2.5 + BTTS via TheOddsAPI und schreibt
sie in EXAKT die Odds-Form, die die WM-Pick-Engine + der WM-Renderer erwarten (key "{homeId}-{awayId}",
Felder hw/dr/aw/odds_open/o25/u25/bttsY/bttsN/odds_closing). Opening-Carry + Closing-Snapshot werden
aus fetch_wm_odds wiederverwendet → identisches CLV-Verhalten.

Der KERN ist das Liga-Team-NAMENS-MATCHING (TheOddsAPI-Namen ↔ unsere API-Football-Teamnamen) — genau
das hat das alte Liga-Frontend dauernd zerschossen. Darum hier robust + unit-getestet (match_event_to_
fixture / _norm_name). Live-Fetch braucht ODDS_API_KEY (läuft im Workflow).
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
LIGA_FILE = os.path.join(BASE, "liga-data.json")
# Zeitreihe der Pinnacle-/Public-Snapshots (für Sharp Radar + detect_wm_sharp_moves, 26.06.2026).
# Format identisch zu wm2026-odds-history.json: {key: [{ts,bk,hw,dr,aw}...], _meta:{oddsFetchedAt}}.
LIGA_HISTORY = os.path.join(BASE, "liga-odds-history.json")

# TheOddsAPI-Sport-Keys der Top 5 (stabil etabliert).
LEAGUE_SPORT_KEYS = {
    "ENG": "soccer_epl",
    "ESP": "soccer_spain_la_liga",
    "GER": "soccer_germany_bundesliga",
    "ITA": "soccer_italy_serie_a",
    "FRA": "soccer_france_ligue_one",
}
BOOK_PRIORITY = ["pinnacle", "betfair_ex_eu", "marathonbet", "williamhill"]
# Soft-/Public-Buchmacher für den Konsens (public_hw/dr/aw → public_static_bias-Signal +
# „Soft-Konsens folgte"-Bestätigung im Steam). Bewusst NICHT pinnacle (das ist der Sharp-Anker).
SOFT_PRIORITY = ["bet365", "williamhill", "unibet", "betclic", "marathonbet", "betfair_ex_eu"]

# Bekannte harte Alias-Fälle (TheOddsAPI ↔ API-Football). Erweiterbar bei Fehlmatches.
NAME_ALIASES = {
    "internazionale": "inter", "inter milan": "inter",
    "wolverhampton wanderers": "wolves",
    "paris saint germain": "psg", "paris saint-germain": "psg",
    "brighton and hove albion": "brighton", "brighton & hove albion": "brighton",
    "tottenham hotspur": "tottenham", "spurs": "tottenham",
    "borussia monchengladbach": "gladbach", "borussia mgladbach": "gladbach",
    "1899 hoffenheim": "hoffenheim", "tsg hoffenheim": "hoffenheim",
    # Sprach-Varianten (TheOddsAPI englisch ↔ API-Football lokal)
    "bayern munich": "bayern", "bayern munchen": "bayern", "fc bayern munchen": "bayern",
    "fc bayern munich": "bayern",
}
# Tokens, die bei der Normalisierung wegfallen (Rechtsform/Präfixe).
_STOP = {"fc", "cf", "ac", "sc", "ssc", "as", "rc", "cd", "ud", "sd", "afc", "bsc",
         "club", "calcio", "1", "1846", "1899", "1900", "04", "05", "09", "the", "de"}


def _norm_name(name: str) -> str:
    """Teamname → vergleichbarer Kern: ohne Akzente, Rechtsform, Kleinschreibung, Alias aufgelöst."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = s.lower().strip()
    if s in NAME_ALIASES:
        s = NAME_ALIASES[s]
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if t and t not in _STOP]
    return " ".join(toks) or s.strip()


def _names_match(a: str, b: str) -> bool:
    """Zwei Teamnamen gleich? Normalisiert; Treffer bei Gleichheit, Substring oder Token-Überlapp."""
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    # signifikanter Überlapp (z.B. „real madrid" vs „real madrid cf" / „athletic" vs „athletic club")
    inter = ta & tb
    return bool(inter) and len(inter) >= min(len(ta), len(tb))


def match_event_to_fixture(event: dict, home_name: str, away_name: str) -> str | None:
    """TheOddsAPI-Event ↔ unsere Paarung. Gibt 'direct' (Event-Home==unser Home),
    'swapped' (vertauscht) oder None zurück — orientierungs-bewusst (wie beim WM-Result-Fix)."""
    eh, ea = event.get("home_team", ""), event.get("away_team", "")
    if _names_match(eh, home_name) and _names_match(ea, away_name):
        return "direct"
    if _names_match(eh, away_name) and _names_match(ea, home_name):
        return "swapped"
    return None


MATCH_DATE_TOL_DAYS = 4   # Event-Datum muss ±4 Tage am Fixture-Datum liegen (s. pick_event_for_fixture)


def _event_date(ev: dict) -> str:
    return (ev.get("commence_time") or "")[:10]


def _days_apart(d1: str, d2: str):
    from datetime import date
    try:
        return abs((date.fromisoformat(d1[:10]) - date.fromisoformat(d2[:10])).days)
    except Exception:
        return None


def pick_event_for_fixture(events: list, home_name: str, away_name: str, fx_date: str,
                           tol_days: int = MATCH_DATE_TOL_DAYS):
    """Bestes TheOddsAPI-Event für unsere Paarung: Team-Match UND nächstes Datum (±tol_days).
    KRITISCH für Liga (Bug 26.06.2026 „Spieltag 1 dann 20"): jede Paarung spielt zweimal
    (Hin/Rück). match_event_to_fixture akzeptiert 'swapped' → ein Hinrunden-Event („A vs B")
    matchte sonst auch das Rückspiel-Fixture („B-A", andere Runde, Monate später) → Odds landeten
    auf der falschen Runde. Datum-Nähe trennt die beiden eindeutig. Reine Funktion (testbar)."""
    best = None
    for ev in events:
        o = match_event_to_fixture(ev, home_name, away_name)
        if not o:
            continue
        dd = _days_apart(_event_date(ev), fx_date) if fx_date else 0
        if fx_date and (dd is None or dd > tol_days):
            continue
        d = dd if dd is not None else 0
        if best is None or d < best[0]:
            best = (d, ev, o)
    return (best[1], best[2]) if best else None


def _best_book(bookmakers: list, market_key: str, priority: list | None = None):
    """Erstes Bookmaker-Market nach Prioritäten. Gibt (bk_key, outcomes). priority=None → Sharp."""
    prio = priority or BOOK_PRIORITY
    by_key = {b.get("key"): b for b in (bookmakers or [])}
    # Bei expliziter Soft-Priorität NUR diese Bücher (sonst fiele es auf Sharp/Pinnacle zurück).
    order = prio if priority else (prio + [k for k in by_key if k not in prio])
    for bk in order:
        b = by_key.get(bk)
        if not b:
            continue
        for m in (b.get("markets") or []):
            if m.get("key") == market_key and m.get("outcomes"):
                return bk, m["outcomes"]
    return None, None


def _map_1x2(outs: list, home_name: str, away_name: str):
    """h2h-Outcomes → (hw, dr, aw), per Name zugeordnet (orientierungs-agnostisch).
    Einmal definiert, von Sharp/Public/Betfair genutzt (28.06.2026: Entdopplung)."""
    hw = dr = aw = None
    for o in (outs or []):
        nm, price = o.get("name", ""), o.get("price")
        if (nm or "").lower() == "draw":
            dr = price
        elif _names_match(nm, home_name):
            hw = price
        elif _names_match(nm, away_name):
            aw = price
    return hw, dr, aw


def extract_prices(event: dict, orientation: str, home_name: str, away_name: str) -> dict:
    """1X2 + O/U 2.5 + BTTS aus einem Event ziehen, Heim/Auswärts korrekt zugeordnet."""
    out = {}
    bks = event.get("bookmakers") or []
    # ── 1X2 (h2h) — Sharp-Anker ──
    bk, outs = _best_book(bks, "h2h")
    hw, dr, aw = _map_1x2(outs, home_name, away_name)
    if hw and dr and aw:
        out.update({"hw": hw, "dr": dr, "aw": aw, "bookmaker": bk})
    # ── Public/Soft-Konsens 1X2 (für public_static_bias + Soft-Bestätigung) ──
    pbk, pouts = _best_book(bks, "h2h", priority=SOFT_PRIORITY)
    phw, pdr, paw = _map_1x2(pouts, home_name, away_name)
    if phw and pdr and paw:
        out.update({"public_hw": phw, "public_dr": pdr, "public_aw": paw,
                    "public_bookmaker": pbk})
    # ── Betfair Exchange = 2. Sharp-Anker (Preis-Cross-Check, 28.06.2026, Lucas) ──
    # Eigenständig gezogen (NICHT nur als Fallback in BOOK_PRIORITY), um Pinnacle gegenzuchecken.
    _, bfouts = _best_book(bks, "h2h", priority=["betfair_ex_eu"])
    bhw, bdr, baw = _map_1x2(bfouts, home_name, away_name)
    if bhw and bdr and baw:
        out.update({"bf_hw": bhw, "bf_dr": bdr, "bf_aw": baw})
    # ── Über/Unter 2.5 ──
    _, t_outs = _best_book(bks, "totals")
    if t_outs:
        for o in t_outs:
            if abs((o.get("point") or 0) - 2.5) < 1e-6:
                nm = (o.get("name") or "").lower()
                if nm == "over":
                    out["o25"] = o.get("price")
                elif nm == "under":
                    out["u25"] = o.get("price")
    # ── BTTS ──
    _, b_outs = _best_book(bks, "btts")
    if b_outs:
        for o in b_outs:
            nm = (o.get("name") or "").lower()
            if nm == "yes":
                out["bttsY"] = o.get("price")
            elif nm == "no":
                out["bttsN"] = o.get("price")
    return out


def build_odds_entry(prices: dict, existing: dict, now_iso: str) -> dict:
    """Preise → gespeicherte Odds-Form (wie fetch_wm_odds.new_entry). Opening-Carry + Closing."""
    import fetch_wm_odds as W   # carry_soft_open + compute_closing wiederverwenden
    existing = existing or {}
    # Opening seeden (1×) bzw. aus altem Eintrag halten.
    odds_open = dict(existing.get("odds_open") or {})
    for k in ("hw", "dr", "aw", "o25", "u25", "bttsY", "bttsN"):
        if prices.get(k) and not odds_open.get(k):
            odds_open[k] = prices[k]
    entry = {
        "hw": prices.get("hw"), "dr": prices.get("dr"), "aw": prices.get("aw"),
        "bookmaker": prices.get("bookmaker"),
        "odds_open": odds_open, "updatedAt": now_iso,
    }
    for k in ("o25", "u25", "bttsY", "bttsN"):
        if prices.get(k):
            entry[k] = prices[k]
    # Public/Soft-Konsens 1X2 durchreichen (public_static_bias liest public_hw/dr/aw).
    for k in ("public_hw", "public_dr", "public_aw", "public_bookmaker"):
        if prices.get(k) is not None:
            entry[k] = prices[k]
    # Betfair-Exchange-Anker 1X2 durchreichen (Sharp-Konsens-Cross-Check im Radar).
    for k in ("bf_hw", "bf_dr", "bf_aw"):
        if prices.get(k) is not None:
            entry[k] = prices[k]
    W.carry_soft_open(existing, entry)   # trägt vorhandene public_*_open mit (Soft-Opening-Fix)
    # Soft-Opening seeden (1×), falls nicht aus existing getragen — sonst „Opening==Jetzt".
    for k in ("hw", "dr", "aw"):
        if entry.get(f"public_{k}_open") is None and prices.get(f"public_{k}"):
            entry[f"public_{k}_open"] = prices[f"public_{k}"]
    # Closing-Snapshot (pre-match laufend, nach Anpfiff eingefroren) — gleiche Mechanik wie WM.
    cur = {k: prices[k] for k in ("hw", "dr", "aw", "o25", "u25", "bttsY", "bttsN") if prices.get(k)}
    try:
        _closing = W.compute_closing(existing.get("odds_closing"), cur, None, now_iso)
        if _closing is not None:
            entry["odds_closing"] = _closing
    except Exception:
        pass
    return entry


def _snap_changed(last: dict | None, hw, dr, aw) -> bool:
    if not last:
        return True
    return (last.get("hw") != hw or last.get("dr") != dr or last.get("aw") != aw)


def _kickoff_passed(kickoff_iso) -> bool:
    """Anpfiff vorbei? (28.06.2026, Lucas: Anpfiff-Freeze für die History — keine In-Play-Snaps.)"""
    if not kickoff_iso:
        return False
    from datetime import datetime, timezone
    try:
        kt = datetime.fromisoformat(str(kickoff_iso).replace("Z", "+00:00"))
        if kt.tzinfo is None:
            kt = kt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= kt
    except Exception:
        return False


def append_snapshot(history: dict, key: str, prices: dict, now_iso: str, post_ko: bool = False) -> int:
    """Hängt Pinnacle- + Public-Snapshot an die Zeitreihe an, wenn sich 1X2 geändert hat.
    Gibt Anzahl neuer Snaps zurück. Rein/testbar (gleiches Format wie wm2026-odds-history).
    post_ko=True (Anpfiff vorbei) → KEIN Snapshot mehr (In-Play würde den Sharp Radar verfälschen)."""
    if post_ko:
        return 0
    added = 0
    snaps = history.setdefault(key, [])
    hw, dr, aw = prices.get("hw"), prices.get("dr"), prices.get("aw")
    if hw and dr and aw:
        last_pinn = next((s for s in reversed(snaps) if s.get("bk") != "public"), None)
        if _snap_changed(last_pinn, hw, dr, aw):
            snaps.append({"ts": now_iso, "bk": "pinnacle", "hw": hw, "dr": dr, "aw": aw})
            added += 1
    phw, pdr, paw = prices.get("public_hw"), prices.get("public_dr"), prices.get("public_aw")
    if phw and pdr and paw:
        last_pub = next((s for s in reversed(snaps) if s.get("bk") == "public"), None)
        if _snap_changed(last_pub, phw, pdr, paw):
            snaps.append({"ts": now_iso, "bk": "public", "hw": phw, "dr": pdr, "aw": paw})
            added += 1
    return added


# ───────────────────────── Live-Fetch ─────────────────────────

def _fetch_events(sport_key: str) -> list:
    # WICHTIG: odds_get hängt den apiKey NICHT an — der Pfad muss ?apiKey=… enthalten (wie WM).
    # btts/double_chance brauchen den per-Event-Endpoint (/events/{id}/odds), NICHT den Batch →
    # im Bulk-Call nur die Featured-Markets h2h,totals (1X2 + O/U). BTTS später per-Event (Phase 2).
    import fetch_wm_odds as W
    path = (f"/v4/sports/{sport_key}/odds?apiKey={W.ODDS_KEY}"
            f"&regions=eu,uk&markets=h2h,totals&oddsFormat=decimal")
    data = W.odds_get(path)
    return data if isinstance(data, list) else []


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    print("=== fetch_liga_odds.py ===")
    if not os.environ.get("ODDS_API_KEY"):
        print("  ❌  ODDS_API_KEY nicht gesetzt — übersprungen (läuft nur im Workflow).")
        sys.exit(0)
    if not os.path.exists(LIGA_FILE):
        print("  ❌  liga-data.json fehlt — erst build_liga_data.py laufen lassen.")
        sys.exit(1)
    with open(LIGA_FILE, encoding="utf-8") as f:
        wm = json.load(f)
    groups = wm.get("groups") or {}
    odds_out = wm.setdefault("odds", {})
    # Odds-History laden (Zeitreihe für Sharp Radar / detect_wm_sharp_moves).
    history = {}
    if os.path.exists(LIGA_HISTORY):
        try:
            with open(LIGA_HISTORY, encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}
    snaps_added = 0
    total = 0
    matched_keys = set()
    for lk, sport_key in LEAGUE_SPORT_KEYS.items():
        gd = groups.get(lk) or {}
        fixtures = gd.get("fixtures") or []
        if not fixtures:
            continue
        events = _fetch_events(sport_key)
        print(f"  {lk}: {len(events)} Events von TheOddsAPI")
        for fx in fixtures:
            if (fx.get("result") or {}).get("status") in ("FT", "AET", "PEN"):
                continue   # gespielt
            hn, an = fx.get("homeName"), fx.get("awayName")
            # Datum-nächstes Event (verhindert Hin-/Rückrunden-Verwechslung, s. pick_event_for_fixture).
            matched = pick_event_for_fixture(events, hn, an, fx.get("date") or "")
            if not matched:
                continue
            ev, orient = matched
            prices = extract_prices(ev, orient, hn, an)
            if not prices.get("hw"):
                continue
            key = f"{fx['home']}-{fx['away']}"
            odds_out[key] = build_odds_entry(prices, odds_out.get(key), now_iso)
            snaps_added += append_snapshot(history, key, prices, now_iso, post_ko=_kickoff_passed(fx.get("kickoff")))
            matched_keys.add(key)
            total += 1
    # Altlasten-Pruning (Bug 26.06.2026): früher fehl-gematchte Odds (falsche Runde) aus odds_out
    # entfernen. Behalten: diesen Lauf gematchte + gespielte Spiele (für Resolve/CLV). Nur prunen,
    # wenn der Lauf überhaupt etwas matchte (sonst API-Ausfall → nichts löschen).
    if total > 0:
        played_keys = {f"{fx['home']}-{fx['away']}"
                       for g in groups.values() for fx in (g.get("fixtures") or [])
                       if (fx.get("result") or {}).get("status") in ("FT", "AET", "PEN")}
        for k in list(odds_out.keys()):
            if k not in matched_keys and k not in played_keys:
                del odds_out[k]
    wm.setdefault("_meta", {})["oddsUpdatedAt"] = now_iso
    with open(LIGA_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)
    history.setdefault("_meta", {})["oddsFetchedAt"] = now_iso
    with open(LIGA_HISTORY, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  ✅ {total} Liga-Spiele bepreist · {snaps_added} neue Odds-Snapshots")


if __name__ == "__main__":
    main()
