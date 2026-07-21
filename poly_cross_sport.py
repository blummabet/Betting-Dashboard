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


def event_key(a: str, b: str) -> str:
    """Reihenfolge-UNABHÄNGIGER Event-Schlüssel aus zwei Team-Namen.

    Kritisch fürs Cross-Venue-Matching: TheOddsAPI kennt Heim/Auswärts, Polymarket listet die zwei
    Moneyline-Ausgänge in beliebiger Reihenfolge. Ein `f"{home}-{away}"`-Key würde bei gedrehter
    Poly-Reihenfolge NIE matchen (genau die Klasse, die den Radar leer ließ). Sortiert normalisiert →
    beide Seiten erzeugen denselben Key; der `outcomeKey` (Team) unterscheidet den Ausgang."""
    return "-".join(sorted([norm(a), norm(b)]))


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
            ekey = event_key(home, away)   # reihenfolge-unabhängig, matcht Poly egal welche Seite zuerst
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


# TheOddsAPI-Sport-Key → Polymarket-Gamma-tag_slug. Beide Seiten müssen dieselben Events treffen.
_ODDSAPI_TO_POLY_TAG = {
    "basketball_nba":     "nba",
    "americanfootball_nfl": "nfl",
    "baseball_mlb":       "mlb",
    "icehockey_nhl":      "nhl",
    "soccer_epl":         "epl",
    "soccer_uefa_champs_league": "ucl",
    "tennis":             "tennis",
}


def _poly_tag_for(sport_key: str) -> str:
    """Sport-Key auf Poly-Tag mappen; Fallback: letztes Segment (soccer_xyz → xyz)."""
    return _ODDSAPI_TO_POLY_TAG.get(sport_key) or sport_key.split("_")[-1]


def fetch_poly_rows(sports, gamma_fetch=None) -> list:
    """Poly-Sportmärkte je Sport über Gamma holen und zu Vergleichs-Zeilen normalisieren.

    Nutzt dieselbe, am Mac-Runner erprobte Fetch-Schicht wie poly_money_broad (`_gamma_events` +
    `_outcomes`) — die produziert nachweislich Daten (u.a. ESPORTS-Märkte). Nur 2-Wege-Moneyline
    (US-Sport): Preis = implizite Poly-Wahrscheinlichkeit, Volumen aus dem Event.

    gamma_fetch(tag) → Liste roher Gamma-Events (für Tests injizierbar). Default: Runner-Gamma.
    Gibt [] zurück, wenn Poly nicht erreichbar ist (Cloud/Sandbox EU-Geoblock) — dann no-oppt main()
    ohne ein bestehendes gutes File zu überschreiben."""
    if gamma_fetch is None:
        try:
            import poly_money_broad as _BR
            gamma_fetch = lambda tag: _BR._gamma_events(tag, closed=False)
        except Exception as e:
            print(f"  ⚠️  Poly-Gamma-Schicht nicht ladbar: {e}")
            return []

    def _outcomes(ev):
        try:
            import poly_money_broad as _BR
            return _BR._outcomes(ev)
        except Exception:
            return []

    rows, seen = [], set()
    for sk in sports:
        tag = _poly_tag_for(sk)
        for ev in (gamma_fetch(tag) or []):
            try:
                oc = _outcomes(ev)
                if len(oc) != 2:
                    continue                       # nur klare 2-Wege-Moneyline (Pinnacle-Seite ist 2-Wege)
                a, b = oc[0], oc[1]
                if a.get("price") is None or b.get("price") is None:
                    continue
                ek = event_key(a["label"], b["label"])
                dedup = (sk, ek)
                if dedup in seen:
                    continue
                seen.add(dedup)
                vol = float(ev.get("volume") or 0)
                event_name = f'{a["label"]} vs {b["label"]}'
                for o in (a, b):
                    rows.append({
                        "sport": sk, "event": event_name, "market": "Moneyline",
                        "outcome": o["label"], "prob": o["price"], "vol": vol,
                        "eventKey": ek, "outcomeKey": norm(o["label"]),
                    })
            except Exception:
                continue
    return rows


def main() -> int:
    sports = _sports()
    poly_rows = fetch_poly_rows(sports)
    if not poly_rows:
        # Poly nicht erreichbar (Cloud/Sandbox EU-Geoblock, oder Runner-Hiccup). WICHTIG (Wipe-Klasse):
        # ein bestehendes gutes File NICHT mit Leere überschreiben. Nur wenn noch keins existiert,
        # einen EHRLICHEN Stub schreiben — damit das Frontend „warum leer" zeigen kann statt 404.
        existing = _load("poly_cross_sport.json")
        if existing.get("discrepancies"):
            print("ℹ️  Keine frischen Poly-Rows — bestehendes Cross-Sport-File bleibt unangetastet")
            return 0
        (BASE / "poly_cross_sport.json").write_text(json.dumps({
            "generatedAt": _now().isoformat(), "sports": sports, "minGapPP": MIN_GAP_PP,
            "polyRowsSeen": 0, "discrepancies": [],
            "emptyReason": "Keine Poly-Sportmärkte erreichbar (läuft scharf nur am Mac-Runner; "
                           "Cloud/EU-IP ist bei Polymarket geoblockt).",
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print("ℹ️  Keine Poly-Sportmärkte — ehrlichen Leer-Stub geschrieben")
        return 0
    pinn = fetch_pinnacle_index(sports)
    # 21.07.2026 (Lucas: „hängt da was?") — messbar machen, ob die 188 Poly-Rows überhaupt ein
    # Pinnacle-Gegenstück finden. „0 Diskrepanzen" ist sonst mehrdeutig: echt einig ODER das
    # Cross-Venue-Namens-Matching verbindet nichts. matched=0 bei pinnKeys>0 → Matching kaputt.
    matched = sum(1 for r in poly_rows
                  if pinn.get((r.get("eventKey"), r.get("outcomeKey"))) is not None)
    disc = compute_discrepancies(poly_rows, pinn)
    hist = update_history(_load("poly_cross_sport_history.json"), disc)

    (BASE / "poly_cross_sport.json").write_text(json.dumps({
        "generatedAt": _now().isoformat(), "sports": sports,
        "minGapPP": MIN_GAP_PP, "polyRowsSeen": len(poly_rows),
        "pinnKeys": len(pinn), "matched": matched, "discrepancies": disc,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (BASE / "poly_cross_sport_history.json").write_text(
        json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"=== Cross-Sport-Radar: {len(disc)} Lücken über {len(sports)} Sportarten "
          f"({matched}/{len(poly_rows)} Poly-Rows mit Pinnacle gematcht, {len(pinn)} Pinn-Keys) ===")
    if matched == 0 and len(pinn) > 0:
        print("  ⚠️  0 Paare trotz Pinnacle-Daten — Cross-Venue-Namens-Matching prüfen "
              "(Poly- vs. TheOddsAPI-Teamnamen weichen ab).")
    for d in disc[:15]:
        conv = d.get("convergePP")
        cs = "" if conv is None else f" · konvergiert {conv:+.1f}pp"
        print(f"  {d['sport']:20} {d['event'][:28]:28} {d['outcome'][:14]:14} "
              f"Poly {d['polyPP']:.0f} vs Pinn {d['pinnPP']:.0f} = {d['gapPP']:+.1f}pp{cs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
