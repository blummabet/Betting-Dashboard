#!/usr/bin/env python3
"""pick_announce_state.py — geteilter Ankündigungs-Status für Picks (03.07.2026, Lucas:
„Intraday-Neuer-Pick-Noti").

Problem: der Morgen-Digest (telegram_wm morning) postet die Tages-Slate einmal. Späte Steam-
Picks, die NACH dem Digest reinkommen (z.B. das Ghana-Spiel), tauchten nur noch stumm im
Tracking auf — kein Follower erfuhr davon. notify_new_picks.py schließt die Lücke.

Damit Digest und Noti sich nicht doppeln, teilen sie EINEN Status:
  • Pick-Identität = "{pick_key}|{market}"  (es gibt kein id/selection-Feld am Pick).
  • Der Digest markiert beim Senden die komplette bekannte Slate als „announced" + setzt
    lastDigestDate=heute.
  • notify_new_picks sendet nur, was NACH dem heutigen Digest neu ist. Läuft es vor dem
    Digest, setzt es stumm die Basis (kein Send) — so bleibt der Digest der Erst-Ankündiger.

Dataset-aware: WM → pick_announce_state.json, MLS → mls_pick_announce_state.json, usw.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).parent
STATE_FILE = BASE / f"{D.prefix()}pick_announce_state.json"

# Nur diese Verdicts sind „Picks", die man ankündigt (NOBET/SKIP nie).
ANNOUNCE_VERDICTS = {"BET", "ABWÄGEN"}

_KO_LABELS = {"R32": "Sechzehntelfinale", "R16": "Achtelfinale", "QF": "Viertelfinale",
              "SF": "Halbfinale", "F": "Finale", "3P": "Spiel um Platz 3"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load() -> dict:
    if not STATE_FILE.exists():
        return {"announced": {}, "lastDigestDate": None, "seeded": False}
    try:
        d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        d.setdefault("announced", {})
        d.setdefault("lastDigestDate", None)
        d.setdefault("seeded", False)
        return d
    except Exception:
        return {"announced": {}, "lastDigestDate": None, "seeded": False}


def save(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def mark(state: dict, ids, ts: str | None = None) -> None:
    ts = ts or _now().isoformat()
    for i in ids:
        state.setdefault("announced", {})[i] = ts


def is_announced(state: dict, pick_id: str) -> bool:
    return pick_id in (state.get("announced") or {})


def _fixture_upcoming(fx, now) -> bool:
    """True, wenn das Spiel noch nicht angepfiffen/fertig ist (kickoff in Zukunft)."""
    res = fx.get("result") or {}
    if str(res.get("status") or "").upper() in {"FT", "AET", "PEN", "AWD", "WO"}:
        return False
    ko = fx.get("kickoff")
    if ko:
        try:
            return datetime.fromisoformat(str(ko).replace("Z", "+00:00")) > now
        except Exception:
            pass
    return True   # ohne kickoff/Ergebnis vorsichtshalber als offen behandeln


def iter_pick_units(wm: dict, now=None):
    """Yield ein dict pro announce-fähigem Pick auf einem KOMMENDEN Spiel.

    Genau EINE Quelle für Digest-Seeding und die Noti → keine Drift. Liefert Anzeige-
    Felder gleich mit (Namen/Flaggen/Runde), damit die Noti nichts nachschlagen muss.
    """
    now = now or _now()
    groups = wm.get("groups", {})
    picks = wm.get("picks", {})

    # Team-Nachschlag (KO-Fixtures tragen nur IDs)
    all_teams = {}
    for gd in groups.values():
        for t in gd.get("teams", []):
            all_teams[t["id"]] = t

    def _emit(pick_key, home, away, kickoff, round_label):
        home_t = all_teams.get(home, {})
        away_t = all_teams.get(away, {})
        for p in picks.get(pick_key, []):
            if p.get("verdict") not in ANNOUNCE_VERDICTS:
                continue
            if p.get("trackingExcluded"):
                continue
            market = p.get("market") or ""
            yield {
                "id": f"{pick_key}|{market}",
                "pick_key": pick_key,
                "market": market,
                "verdict": p.get("verdict"),
                "convictionScore": p.get("convictionScore"),
                "source": p.get("source"),
                "home": home, "away": away,
                "homeName": home_t.get("name", home), "awayName": away_t.get("name", away),
                "homeFlag": home_t.get("flag", "🏳"), "awayFlag": away_t.get("flag", "🏳"),
                "kickoff": kickoff, "roundLabel": round_label,
            }

    for gkey, gdata in groups.items():
        for fx in gdata.get("fixtures", []):
            if not (fx.get("home") and fx.get("away")):
                continue
            if not _fixture_upcoming(fx, now):
                continue
            pk = f"{gkey}-{fx['matchday']}-{fx['home']}-{fx['away']}"
            yield from _emit(pk, fx["home"], fx["away"], fx.get("kickoff", ""), None)

    for kf in (wm.get("koFixtures") or []):
        if not (kf.get("home") and kf.get("away")):
            continue
        if not _fixture_upcoming(kf, now):
            continue
        rnd = kf.get("round")
        pk = f"KO-{rnd}-{kf['home']}-{kf['away']}"
        label = kf.get("roundLabel") or _KO_LABELS.get(rnd, "K.-o.-Runde")
        yield from _emit(pk, kf["home"], kf["away"], kf.get("kickoff", ""), label)


def current_pick_ids(wm: dict, now=None) -> set:
    return {u["id"] for u in iter_pick_units(wm, now)}
