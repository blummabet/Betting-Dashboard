#!/usr/bin/env python3
"""fetch_wm_player_stats.py — Per-Spieler-Match-Stats-Backfill fürs player_form_ledger (06.07.2026, Lucas).

Problem: das Ledger wird sonst nur als Nebeneffekt von fetch_wm_nt_xg.py fortgeschrieben (Cache
`refresh_age_days`=3 pro Team) → die neuesten (KO-)Spiele fehlen tagelang → die Spieler-Serien
(compute_player_streaks.py) rechnen auf veralteter Basis.

Lösung (chirurgisch + API-sparsam): Fixture-IDs kommen aus wm_lineups.json (behält vergangene
Spiele mit numerischer fixture_id). Für jedes BEENDETE Spiel, das noch NICHT im Ledger steht:
`/fixtures/players?fixture=ID` holen → Zeilen anhängen (dedup nach playerId|fixtureId). Nur die
Lücke wird gefetcht (heute typ. 2-4 Spiele), gedeckelt via MAX_FIXTURES. Dataset-aware.

`ts` wird auf den ANPFIFF gesetzt (nicht Fetch-Zeit) → korrekte chronologische Reihenfolge für die
Serien-Berechnung.

Env: APISPORTS_KEY. Run: python3 fetch_wm_player_stats.py
"""
from __future__ import annotations

import http.client
import json
import os
from datetime import datetime, timedelta, timezone

import cocobet_dataset as D
import player_form as PF

APIF_HOST = "v3.football.api-sports.io"
APIF_KEY = os.environ.get("APISPORTS_KEY", "").strip()

LINEUPS_FILE = D.file("wm_lineups.json", "liga_lineups.json")

MAX_FIXTURES = int(os.environ.get("PLAYER_STATS_MAX_FIXTURES", "12"))  # Deckel je Lauf (API-Budget)
FINISHED_AFTER_HOURS = 3.0   # Anpfiff + 3h → Spiel (inkl. Verlängerung) sicher vorbei, Stats verfügbar


def _apif_get(path: str, timeout: int = 15) -> dict | None:
    if not APIF_KEY:
        print("   ⚠️  APISPORTS_KEY fehlt — kein Fetch")
        return None
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=timeout)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        if resp.status != 200:
            print(f"   ⚠️  HTTP {resp.status} bei {path[:80]}: {body[:160]}")
            return None
        return json.loads(body)
    except Exception as e:
        print(f"   ⚠️  Fetch-Fehler {path[:80]}: {e}")
        return None


def _parse_kickoff(iso: str):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:
        return None


def missing_finished_fixtures(lineups: dict, ledger: dict, now: datetime) -> list:
    """(fixture_id, kickoff_iso) aller BEENDETEN Lineup-Spiele, die noch nicht im Ledger stehen.
    Reine Funktion → testbar. Älteste zuerst (korrekte Append-Reihenfolge)."""
    have = {r.get("fixtureId") for r in (ledger.get("records") or [])}
    out = []
    for fx in (lineups or {}).values():
        if not isinstance(fx, dict):
            continue
        fid = fx.get("fixture_id")
        ko = _parse_kickoff(fx.get("kickoff"))
        if fid is None or fid in have or ko is None:
            continue
        if ko + timedelta(hours=FINISHED_AFTER_HOURS) > now:
            continue   # noch nicht (sicher) beendet → Stats evtl. leer
        out.append((fid, fx.get("kickoff"), ko))
    out.sort(key=lambda t: t[2])   # chronologisch
    return [(fid, iso) for fid, iso, _ in out]


def main() -> int:
    ledger = json.loads(PF.LEDGER_FILE.read_text(encoding="utf-8")) \
        if PF.LEDGER_FILE.exists() else {"_meta": {}, "records": []}
    try:
        lineups = json.loads(LINEUPS_FILE.read_text(encoding="utf-8"))
    except Exception:
        print(f"ℹ️  {LINEUPS_FILE.name} fehlt — nichts zu tun.")
        return 0

    now = datetime.now(timezone.utc)
    todo = missing_finished_fixtures(lineups, ledger, now)[:MAX_FIXTURES]
    if not todo:
        print("✅ Ledger aktuell — keine fehlenden beendeten Spiele.")
        return 0

    total_added = 0
    for fid, ko_iso in todo:
        data = _apif_get(f"/fixtures/players?fixture={fid}")
        if not data or not data.get("response"):
            print(f"   ⚠️  keine Spieler-Stats für Fixture {fid}")
            continue
        rows = PF.rows_from_fixture_players(fid, data["response"])
        for r in rows:
            r["ts"] = ko_iso   # Anpfiff als Zeitanker (nicht Fetch-Zeit)
        added = PF.append_records(ledger, rows)
        total_added += added
        print(f"   ✅ Fixture {fid} ({str(ko_iso)[:10]}): +{added} Spieler-Zeilen")

    if total_added:
        PF.LEDGER_FILE.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
    print(f"✅ player_form_ledger fortgeschrieben: +{total_added} Zeilen aus {len(todo)} Spiel(en) "
          f"({D.active_dataset()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
