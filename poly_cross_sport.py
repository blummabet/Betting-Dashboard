#!/usr/bin/env python3
"""
poly_cross_sport.py — Cross-Sport-Radar: Poly vs. scharfe Pinnacle über mehrere Sportarten (19.07.2026, Lucas).

## Idee

Unabhängig von unserem Fußball-Trading (Top-5 + MLS): alle Poly-Sportmärkte, die wir kriegen,
gegen die SCHARFE Pinnacle stellen (nicht gegen weiche Bücher wie Bet365/William Hill — die sind
selbst Publikum). Wo Poly stark von der de-viggten Pinnacle-Fair abweicht, ist ein Kandidat.

## Warum überhaupt vorsichtig

Lucas' Krypto-Projekt hat „Poly vs eine Fair" schon widerlegt, WEIL die Fair (ein Modell) nicht
schärfer war als Poly. Hier ist die Fair ein scharfes BUCH — bessere Chance. Aber:
  · Weiche Bücher taugen NICHT als Anker (deshalb nur Pinnacle/Betfair).
  · Outright/Futures (Torschützenkönig, Turniersieger) sind eine Falle: fette Marge + andere
    Settlement-Regeln je Venue → große Lücken sind meist Regel-Artefakte, kein Edge. Dieser Radar
    startet daher auf STANDARDISIERTEN Märkten (Moneyline / h2h).

## Der eigentliche Wert: Konvergenz messen, nicht glauben

Eine gelistete Lücke ist erst dann echt, wenn sie sich über die Tage SCHLIESST (Poly läuft zur
Pinnacle). Bleibt sie stehen, ist sie ein Artefakt (andere Regel, veralteter Preis). `update_history`
verfolgt je Markt die erste gesehene Lücke gegen die aktuelle → `convergePP`. Genau wie beim
Markout-Test: erst messen, dann glauben. Read-only, kein Geld.

Fetch-Schicht (Poly Gamma + TheOddsAPI/Pinnacle) ist best-effort und muss auf dem Mac-Runner
scharf gemacht werden (Poly ist EU-geoblockt). Der reine Kern (`compute_discrepancies`,
`update_history`) ist ohne Netz testbar.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent

# TheOddsAPI-Sport-Keys, die Poly ebenfalls liquide listet. Bewusst klein starten (Lucas:
# „ein bisschen tracken"), erweiterbar über cocobet_config poly.cross_sport_keys.
DEFAULT_SPORTS = ["basketball_nba", "americanfootball_nfl", "baseball_mlb", "icehockey_nhl"]

MIN_GAP_PP  = 6.0      # darunter ist die Abweichung im Rahmen von Marge/Rundung
MIN_VOL_USD = 5_000    # dünner Poly-Markt → Preis nicht handelbar, jede Lücke ist Rauschen
PRUNE_DAYS  = 21       # Historien-Einträge, die so lange nicht gesehen wurden, fallen raus


def _now():
    return datetime.now(timezone.utc)


def norm(s: str) -> str:
    """Team-/Event-Name normalisieren fürs Matching über Venues (klein, nur a-z0-9)."""
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def devig_2way(p_a, p_b):
    """Zwei-Wege-de-Vig: rohe implizite Wahrscheinlichkeiten → faire (Summe 1)."""
    try:
        a, b = float(p_a), float(p_b)
    except (TypeError, ValueError):
        return None, None
    s = a + b
    if s <= 0:
        return None, None
    return a / s, b / s


def compute_discrepancies(poly_rows, pinn_index, cfg=None) -> list:
    """Poly-Zeilen gegen den de-viggten Pinnacle-Index halten. REIN, testbar.

    poly_rows : [{sport, event, market, outcome, prob, vol, eventKey, outcomeKey}]
    pinn_index: {(eventKey, outcomeKey): fair_prob}   (bereits de-viggt)
    """
    cfg = cfg or {}
    min_gap = cfg.get("min_gap_pp", MIN_GAP_PP)
    min_vol = cfg.get("min_vol_usd", MIN_VOL_USD)
    out = []
    for r in poly_rows:
        try:
            poly_p = float(r.get("prob"))
            vol = float(r.get("vol") or 0)
        except (TypeError, ValueError):
            continue
        if not (0.0 < poly_p < 1.0) or vol < min_vol:
            continue
        fair = pinn_index.get((r.get("eventKey"), r.get("outcomeKey")))
        if fair is None:
            continue                       # kein scharfes Gegenstück → nicht bewertbar
        gap = round((poly_p - fair) * 100, 2)
        if abs(gap) < min_gap:
            continue
        out.append({
            "id": f"{r.get('sport')}|{r.get('eventKey')}|{r.get('outcomeKey')}",
            "sport": r.get("sport"), "event": r.get("event"),
            "market": r.get("market", "Moneyline"), "outcome": r.get("outcome"),
            "polyPP": round(poly_p * 100, 1), "pinnPP": round(fair * 100, 1),
            "gapPP": gap, "vol": round(vol),
            # gap > 0: Poly zu HOCH → auf Poly faden (Gegenseite) · gap < 0: Poly zu NIEDRIG → backen
            "richtung": "Poly zu hoch → faden" if gap > 0 else "Poly zu niedrig → backen",
        })
    out.sort(key=lambda d: -abs(d["gapPP"]))
    return out


def update_history(history: dict, discrepancies: list, now=None) -> dict:
    """Konvergenz je Markt verfolgen: erste gesehene Lücke vs. aktuelle. REIN.

    convergePP > 0 heißt: die Lücke ist seit dem ersten Sehen GESCHRUMPFT (Poly läuft zur
    Pinnacle) → die Lücke war echt. ≤ 0 heißt: bleibt stehen/wächst → Artefakt-Verdacht."""
    now = now or _now()
    hist = dict(history or {})
    seen = set()
    for d in discrepancies:
        seen.add(d["id"])
        prev = hist.get(d["id"])
        if prev is None:
            hist[d["id"]] = {"firstGapPP": d["gapPP"], "firstSeen": now.isoformat(),
                             "lastGapPP": d["gapPP"], "lastSeen": now.isoformat(),
                             "event": d["event"], "outcome": d["outcome"], "sport": d["sport"]}
        else:
            prev["lastGapPP"] = d["gapPP"]
            prev["lastSeen"] = now.isoformat()
        # Konvergenz in den aktuellen Befund schreiben (Betrag der Lücke geschrumpft?)
        h = hist[d["id"]]
        d["convergePP"] = round(abs(h["firstGapPP"]) - abs(d["gapPP"]), 2)
        d["firstSeen"] = h["firstSeen"]

    # Alte, lange nicht gesehene Einträge prunen (Markt aufgelöst / verschwunden).
    grenze = now - timedelta(days=PRUNE_DAYS)
    for k in [k for k, v in hist.items() if _before(v.get("lastSeen"), grenze)]:
        hist.pop(k, None)
    return hist


def _before(iso, grenze) -> bool:
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")) < grenze
    except Exception:
        return False


# ── Fetch-Schicht (best-effort, Mac-Runner) ──────────────────────────────────

def _sports() -> list:
    try:
        raw = json.loads((BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        return raw.get("poly", {}).get("cross_sport_keys") or DEFAULT_SPORTS
    except Exception:
        return DEFAULT_SPORTS


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def fetch_pinnacle_index(sports, fetch=None) -> dict:
    """{(eventKey, outcomeKey): fair_prob} aus TheOddsAPI-Pinnacle-h2h. best-effort.

    fetch(sport_key) → Liste TheOddsAPI-Events (für Tests injizierbar)."""
    import os
    import urllib.request
    key = os.environ.get("ODDS_API_KEY", "")

    def _default_fetch(sk):
        url = (f"https://api.the-odds-api.com/v4/sports/{sk}/odds?apiKey={key}"
               f"&regions=eu,uk&markets=h2h&oddsFormat=decimal&bookmakers=pinnacle")
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                return json.loads(r.read())
        except Exception as e:
            print(f"  ⚠️  Pinnacle-Fetch {sk}: {e}")
            return []

    fetch = fetch or _default_fetch
    index = {}
    for sk in sports:
        for ev in (fetch(sk) or []):
            home, away = ev.get("home_team"), ev.get("away_team")
            ekey = f"{norm(home)}-{norm(away)}"
            books = ev.get("bookmakers") or []
            pin = next((b for b in books if b.get("key") == "pinnacle"), None)
            if not pin:
                continue
            mk = next((m for m in (pin.get("markets") or []) if m.get("key") == "h2h"), None)
            if not mk:
                continue
            outs = mk.get("outcomes") or []
            # 2-Wege (die meisten US-Sportarten haben kein Remis) de-viggen
            if len(outs) == 2:
                pa = 1.0 / float(outs[0]["price"]) if outs[0].get("price") else None
                pb = 1.0 / float(outs[1]["price"]) if outs[1].get("price") else None
                fa, fb = devig_2way(pa, pb)
                for o, f in ((outs[0], fa), (outs[1], fb)):
                    if f is not None:
                        index[(ekey, norm(o.get("name")))] = f
    return index


def fetch_poly_rows(sports) -> list:
    """Poly-Sportmärkte normalisieren. Placeholder: Poly ist EU-geoblockt, echte Umsetzung läuft
    am Mac-Runner (Gamma per tag_slug je Sport + Vol + Preise). Gibt hier [] zurück, damit das
    Skript in der Cloud/Sandbox sauber no-oppt."""
    # TODO(Runner): Gamma /events?tag_slug=<sport> je Sport, Moneyline-Outcomes → rows mit
    # eventKey=f"{norm(home)}-{norm(away)}", outcomeKey=norm(outcome_team), prob, vol.
    return []


def main() -> int:
    sports = _sports()
    poly_rows = fetch_poly_rows(sports)
    if not poly_rows:
        print("ℹ️  Keine Poly-Sportmärkte (läuft scharf nur am Mac-Runner) — nichts zu vergleichen")
        # Trotzdem: bestehende Datei nicht anfassen, damit die Frontend-Anzeige stehen bleibt.
        return 0
    pinn = fetch_pinnacle_index(sports)
    disc = compute_discrepancies(poly_rows, pinn)
    hist = update_history(_load("poly_cross_sport_history.json"), disc)

    (BASE / "poly_cross_sport.json").write_text(json.dumps({
        "generatedAt": _now().isoformat(), "sports": sports,
        "minGapPP": MIN_GAP_PP, "discrepancies": disc,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (BASE / "poly_cross_sport_history.json").write_text(
        json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"=== Cross-Sport-Radar: {len(disc)} Lücken über {len(sports)} Sportarten ===")
    for d in disc[:15]:
        conv = d.get("convergePP")
        cs = "" if conv is None else f" · konvergiert {conv:+.1f}pp"
        print(f"  {d['sport']:20} {d['event'][:28]:28} {d['outcome'][:14]:14} "
              f"Poly {d['polyPP']:.0f} vs Pinn {d['pinnPP']:.0f} = {d['gapPP']:+.1f}pp{cs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
