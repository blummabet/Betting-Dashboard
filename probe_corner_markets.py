#!/usr/bin/env python3
"""probe_corner_markets.py — Coverage-Probe: welche Bücher liefern Corner- + Halbzeit-Märkte? (28.06.2026)

Entscheidet die Architektur, BEVOR wir Corner/HT bauen (Lehre aus dem News-Probe):
The Odds API listet die Markt-Keys, aber Zusatzmärkte sind „limited to US bookmakers" — die
Frage ist, ob für die 5 EU-Ligen überhaupt (und v.a. **Pinnacle / Betfair**) Quoten kommen.

Pro Liga: erstes anstehendes Event holen, dann /events/{id}/odds mit den Zusatzmarkt-Keys
abfragen (regions=eu,uk) und auflisten, WELCHE Bookmaker WELCHE Märkte liefern.

Probe-Märkte:
  Corner : alternate_totals_corners, corners_1x2, alternate_spreads_corners
  HT     : totals_h1 (Über/Unter HT), h2h_3_way_h1 (1X2 HT)

ENV: ODDS_API_KEY. Schreibt corner_probe.json. Nur manuell laufen (workflow_dispatch); kostet
ein paar API-Calls. Pre-Season → evtl. keine Events: dann meldet die Probe genau das.
"""
from __future__ import annotations
import json
from pathlib import Path

import fetch_wm_odds as W  # ODDS_KEY + odds_get (Single Source)
from fetch_liga_odds import LEAGUE_SPORT_KEYS

BASE = Path(__file__).parent
OUT = BASE / "corner_probe.json"

CORNER_MARKETS = ["alternate_totals_corners", "corners_1x2", "alternate_spreads_corners"]
HT_MARKETS = ["totals_h1", "h2h_3_way_h1"]
ALL_MARKETS = CORNER_MARKETS + HT_MARKETS
SHARP_BOOKS = {"pinnacle", "betfair_ex_eu", "betfair_ex_uk"}


def _events(sport_key: str) -> list:
    data = W.odds_get(f"/v4/sports/{sport_key}/events?apiKey={W.ODDS_KEY}")
    return data if isinstance(data, list) else []


def _event_odds(sport_key: str, event_id: str) -> dict | None:
    markets = ",".join(ALL_MARKETS)
    path = (f"/v4/sports/{sport_key}/events/{event_id}/odds?apiKey={W.ODDS_KEY}"
            f"&regions=eu,uk&oddsFormat=decimal&markets={markets}")
    return W.odds_get(path)


def summarize_event_odds(event_odds: dict) -> dict:
    """Reine Funktion (testbar): welche Bücher liefern welche Markt-Keys?"""
    by_market: dict[str, list] = {m: [] for m in ALL_MARKETS}
    for bk in (event_odds or {}).get("bookmakers", []):
        bkey = bk.get("key")
        for m in (bk.get("markets") or []):
            mk = m.get("key")
            if mk in by_market and m.get("outcomes"):
                by_market[mk].append(bkey)
    return {
        "byMarket": {m: sorted(set(bks)) for m, bks in by_market.items()},
        "cornerBooks": sorted({b for m in CORNER_MARKETS for b in by_market[m]}),
        "htBooks": sorted({b for m in HT_MARKETS for b in by_market[m]}),
        "sharpCorner": sorted({b for m in CORNER_MARKETS for b in by_market[m]} & SHARP_BOOKS),
        "sharpHt": sorted({b for m in HT_MARKETS for b in by_market[m]} & SHARP_BOOKS),
    }


def main() -> None:
    print("=== probe_corner_markets.py — Corner + HT Coverage ===")
    report = {}
    for lk, sport_key in LEAGUE_SPORT_KEYS.items():
        evs = _events(sport_key)
        if not evs:
            report[lk] = {"sport_key": sport_key, "events": 0, "note": "keine Events (pre-season?)"}
            print(f"  {lk:4} {sport_key:30} → keine Events")
            continue
        ev = evs[0]
        eid = ev.get("id")
        odds = _event_odds(sport_key, eid)
        summ = summarize_event_odds(odds or {})
        report[lk] = {"sport_key": sport_key, "events": len(evs),
                      "sample": f"{ev.get('home_team')} v {ev.get('away_team')}", **summ}
        print(f"  {lk:4} {ev.get('home_team')} v {ev.get('away_team')}")
        print(f"        Corner-Bücher: {summ['cornerBooks'] or '—'}  (sharp: {summ['sharpCorner'] or '—'})")
        print(f"        HT-Bücher:     {summ['htBooks'] or '—'}  (sharp: {summ['sharpHt'] or '—'})")
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Voll-Report → {OUT.name}")
    # Verdikt
    any_corner = any(r.get("cornerBooks") for r in report.values())
    any_sharp = any(r.get("sharpCorner") for r in report.values())
    print(f"Verdikt Corner: {'Quoten vorhanden' if any_corner else 'KEINE Corner-Quoten'}"
          f" · {'Pinnacle/Betfair dabei → Steam möglich' if any_sharp else 'kein Sharp-Anker → nur Modell-Markt'}")


if __name__ == "__main__":
    main()
