#!/usr/bin/env python3
"""
capture_dense_odds.py — Dichte Pinnacle + Soft-Book 1X2-Snapshots, NUR ZUR ANALYSE.

ISOLIERT vom Live-System: schreibt ausschließlich in wm_dense_odds_log.json. Keine Picks,
keine Verdicts, keine Trades, KEINE Schreibzugriffe auf wm2026-data.json / wm2026-odds-
history.json / signal_weights.json o.ä. Das bestehende System bleibt unberührt.

Zweck (Lucas 14.06.2026): Post-Match-Move-These backtesten — bewegt ein Spielende die
Linien der FOLGE-Spiele der beteiligten Teams, und hinkt Polymarket dabei nach? Dafür
brauchen wir eine DICHTE Zeitreihe (alle ~30 Min im Match-Fenster), nicht die grobe
Change-Detection-Historie (Median 19h). Hier wird JEDER Lauf gespeichert (auch wenn sich
nichts bewegt) — nur so ist „kein Move" zeitlich sichtbar.

1 TheOddsAPI-h2h-Batch-Call (regions eu,uk, ~2 Quota-Einheiten) → alle WC-Fixtures →
Pinnacle + bester Soft-Book (bet365>williamhill>…) 1X2. Append-only, Retention 7 Tage.

Läuft via .github/workflows/capture-dense-odds.yml dicht im Wiener Abend-/Nacht-Fenster.
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent
OUT = BASE / "wm_dense_odds_log.json"
RETENTION_DAYS = 7   # ältere Snapshots prunen → Datei bleibt klein (~1 MB)

# Stabile Helfer aus dem bestehenden Fetch wiederverwenden (kein Duplikat, gleiche API).
# Import löst nur Modul-Konstanten/Funktionen aus, KEIN main() (steht hinter __main__).
try:
    from fetch_wm_odds import (
        odds_get, _find_sport_key, _best_odds, _name_to_id, BOOKMAKERS, ODDS_KEY,
    )
except Exception as e:  # pragma: no cover
    print(f"❌ Import aus fetch_wm_odds fehlgeschlagen: {e}")
    sys.exit(1)


def _load() -> dict:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _prune(log: dict, now: datetime) -> None:
    cutoff = (now - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for key, arr in list(log.items()):
        if key == "_meta" or not isinstance(arr, list):
            continue
        log[key] = [e for e in arr if (e.get("ts") or "") >= cutoff]
        if not log[key]:
            del log[key]


def main() -> None:
    print(f"📸 capture_dense_odds.py — {datetime.now(timezone.utc).isoformat()[:19]} UTC")
    if not ODDS_KEY:
        print("  ❌ ODDS_API_KEY nicht gesetzt — Abbruch")
        return
    sport_key = _find_sport_key()
    if not sport_key:
        print("  ⚠️ Kein aktiver Sport-Key (WC evtl. noch nicht gelistet) — Abbruch")
        return

    path = (f"/v4/sports/{sport_key}/odds"
            f"?apiKey={ODDS_KEY}&regions=eu,uk&markets=h2h&oddsFormat=decimal"
            f"&bookmakers={','.join(BOOKMAKERS)}")
    events = odds_get(path)
    if not events or not isinstance(events, list):
        print("  ⚠️ Keine Events erhalten — Abbruch (kein Schreibvorgang)")
        return

    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    log = _load()
    added = 0
    for ev in events:
        hid = _name_to_id(ev.get("home_team", ""))
        aid = _name_to_id(ev.get("away_team", ""))
        if not hid or not aid:
            continue
        res = _best_odds(ev.get("bookmakers", []), BOOKMAKERS)
        if not res or not res.get("_oc"):
            continue
        oc = res["_oc"]
        poc = res.get("_public_oc") or {}
        entry = {
            "ts":     now_iso,
            "pinn":   {"hw": oc.get("home"), "dr": oc.get("draw"), "aw": oc.get("away")},
            "pinnBk": res.get("bookmaker"),
        }
        if poc:
            entry["soft"]   = {"hw": poc.get("home"), "dr": poc.get("draw"), "aw": poc.get("away")}
            entry["softBk"] = res.get("_public_bk")
        log.setdefault(f"{hid}-{aid}", []).append(entry)
        added += 1

    if added == 0:
        print("  ⚠️ 0 Fixtures aufgelöst — kein Schreibvorgang")
        return

    _prune(log, now)
    log["_meta"] = {"updatedAt": now_iso, "fixturesThisRun": added,
                    "retentionDays": RETENTION_DAYS,
                    "note": "Analyse-only · Post-Match-Move-These · isoliert vom Live-System"}
    OUT.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ {added} Fixtures gesnapshottet → {OUT.name} "
          f"({sum(len(v) for k, v in log.items() if k != '_meta')} Snaps gesamt)")


if __name__ == "__main__":
    main()
