#!/usr/bin/env python3
"""
fetch_liga_news_probe.py — DIAGNOSE: was liefert API-Football „News" für die 5 Top-Ligen?
(26.06.2026, Lucas: „News muss man sich anschauen, was man da kriegt").

KEIN Signal, kein Pipeline-Teil — nur ein Abklopfer. Wir kennen die genauen /news-Parameter nicht,
darum probiert das Script mehrere plausible Varianten, protokolliert HTTP-Status + Antwort-Form +
ein Sample und schreibt alles nach liga_news_probe.json. Danach entscheiden wir, ob Datenqualität +
ein harter Engine-Hook ein News-Signal rechtfertigen (sonst NLP/Rausch-Risiko → bleibt liegen).

Einmalig via workflow_dispatch laufen lassen (braucht APISPORTS_KEY).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).parent
OUT = BASE / "liga_news_probe.json"
APIF_HOST = "v3.football.api-sports.io"
APIF_KEY = os.environ.get("APISPORTS_KEY", "").strip()
LIGA_LEAGUES = {"ENG": 39, "ESP": 140, "GER": 78, "ITA": 135, "FRA": 61}
LIGA_SEASON = int(os.environ.get("LIGA_SEASON") or 2025)


def summarize(payload: dict) -> dict:
    """Roh-Response → kompakte Form-Beschreibung (Status, results, Top-Level-Keys, 1 Sample).
    Reine Funktion (testbar)."""
    if not isinstance(payload, dict):
        return {"shape": type(payload).__name__}
    resp = payload.get("response")
    out = {
        "results": payload.get("results"),
        "errors": payload.get("errors"),
        "topKeys": sorted(payload.keys()),
        "responseType": type(resp).__name__,
        "count": len(resp) if isinstance(resp, list) else None,
    }
    if isinstance(resp, list) and resp:
        first = resp[0]
        out["sampleItemKeys"] = sorted(first.keys()) if isinstance(first, dict) else str(type(first))
        out["sampleItem"] = first
    return out


def _apif_get(path: str):
    """(status, json|None). Auch Nicht-200 zurückgeben, damit wir 404/leeren Endpoint SEHEN."""
    import http.client
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        r = conn.getresponse()
        raw = r.read().decode("utf-8", "replace")
        conn.close()
        try:
            return r.status, json.loads(raw)
        except Exception:
            return r.status, {"_raw": raw[:500]}
    except Exception as e:
        return None, {"_error": str(e)}


def main():
    print("=== fetch_liga_news_probe.py (DIAGNOSE) ===")
    if not APIF_KEY:
        print("  ❌  APISPORTS_KEY nicht gesetzt — übersprungen.")
        sys.exit(0)
    eng = LIGA_LEAGUES["ENG"]
    # Mehrere plausible Varianten — wir wissen die echten Parameter nicht.
    variants = {
        "bare":            "/news",
        "league_eng":      f"/news?league={eng}",
        "league_season":   f"/news?league={eng}&season={LIGA_SEASON}",
        "team_arsenal":    "/news?team=42",
        "search_premier":  "/news?search=premier",
    }
    result = {}
    for name, path in variants.items():
        status, payload = _apif_get(path)
        result[name] = {"path": path, "status": status, "summary": summarize(payload)}
        s = result[name]["summary"]
        print(f"  {name:16} {path:34} → HTTP {status} · results={s.get('results')} "
              f"· count={s.get('count')} · errors={s.get('errors')}")
        time.sleep(0.8)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ Voll-Sample → {OUT.name} (im Repo ansehen)")


if __name__ == "__main__":
    main()
