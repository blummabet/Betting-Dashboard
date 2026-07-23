#!/usr/bin/env python3
"""
poly_money_broad.py — Liegt das Geld richtig? BREIT über ALLE Poly-Ligen (19.07.2026, Lucas).

## Idee

`poly_money_accuracy.py` misst das für unsere Datensätze (WM/MLS) gegen unsere Ergebnisdaten.
Lucas will es breiter: **alles, was Polymarket anbietet** (min. Volumen), um zu sehen, wo die Masse
mehr recht hat — je Liga aufgeschlüsselt, und ohne triviale Favoriten (Quote < 1.35).

Der Clou: für fremde Ligen brauchen wir GAR KEINE eigenen Ergebnisse — **Polymarket löst seine
Märkte selbst auf** (die Gewinner-Seite settlet auf 1.00). Also: Geld-Verteilung + Preis nah am
Anpfiff einfrieren, später Polys eigene Auflösung lesen. Kein externer Anker nötig.

## Filter (Lucas)

  · Volumen ≥ Schwelle (5–10k) — darunter ist die Geld-Verteilung nicht aussagekräftig.
  · Favorit-Quote ≥ 1.35 — „dass ein 1.1-Favorit öfter recht hat, ist logo"; nur kompetitive
    Märkte sagen etwas über die Klugheit der Masse.

Teilt sich `evaluate` (min_odds + byLeague) mit poly_money_accuracy — dieselbe, getestete Mathematik.

⚠️ Die Fetch-/Auflösungs-Schicht (Gamma über alle Sport-Tags + Poly-Resolution + Holders je Markt)
läuft scharf NUR am Mac-Runner (Poly EU-geoblockt) und muss dort validiert werden. Die reinen
Helfer (`winner_from_prices`, Aggregation via `evaluate`) sind ohne Netz getestet. Read-only.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import poly_money_accuracy as PMA

BASE = Path(__file__).resolve().parent

MIN_VOL_USD = 7_500     # „5-10k oben liegen" — Mitte
MIN_ODDS    = 1.35      # Lucas: triviale Favoriten (≤1.35) raus
CLOSE_FILE  = "poly_money_broad_close.json"
OUT_FILE    = "poly_money_broad.json"


def _now():
    return datetime.now(timezone.utc)


def _cfg():
    try:
        raw = json.loads((BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        p = raw.get("poly", {})
        return float(p.get("money_broad_min_vol", MIN_VOL_USD)), float(p.get("money_broad_min_odds", MIN_ODDS))
    except Exception:
        return MIN_VOL_USD, MIN_ODDS


def winner_from_prices(price_by_outcome: dict, tol: float = 0.02):
    """Aus Polys AUFGELÖSTEN Outcome-Preisen die Gewinner-Seite ableiten: die, die ~1.00 settlet.
    None, wenn (noch) nicht eindeutig aufgelöst (kein Preis nahe 1.0)."""
    best, best_p = None, 0.0
    for k, v in (price_by_outcome or {}).items():
        try:
            p = float(v)
        except (TypeError, ValueError):
            continue
        if p > best_p:
            best, best_p = k, p
    return best if best_p >= 1.0 - tol else None


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Fetch-/Capture-Schicht (Mac-Runner) ──────────────────────────────────────
# Läuft scharf nur am Mac-Runner (Poly EU-geoblockt). Reuse der bewährten Bausteine:
# Gamma-Events (wie fetch_wm_poly_prices) + Holders-Geld-Split (wie fetch_wm_poly_smartmoney).
# ⚠️ Erster Runner-Lauf = Validierung: Feldnamen/Antwortform per Log prüfen.

import json as _json
import urllib.request as _url
from datetime import timedelta as _td

# Sport-Tags, die Poly liquide listet. Erweiterbar über cocobet_config poly.money_broad_tags.
# 19.07.2026 (Lucas): E-Sport dazu — Poly deckt CS2/LoL/Dota/Valorant inzwischen breit ab.
# 21.07.2026 (Lucas: „sollte da nicht mehr Sport sein?"): um die ganzjährigen/Sommer-Poly-Sportarten
# erweitert (UFC/MMA/Boxen/Golf/F1/Cricket). Welche Tag-Slugs Poly WIRKLICH liefert, zeigt die neue
# rawByTag-Diagnose im nächsten Lauf — tote Tags fliegen dann wieder raus. Saisonale (NBA/NFL/NHL/EPL)
# bleiben drin und füllen sich von selbst, sobald ihre Saison startet.
# 23.07.2026 (Lucas: „bei ‚Liegt das Geld richtig' viel zu wenig Fußball — MLS fehlt"). MLS war
# NICHT gelistet → wurde gar nicht erst von Gamma geholt, obwohl es die aktive Fußball-Liga mit
# echter Poly-Liquidität ist (Matches clearen die $7.5K-Schwelle, ~$8–13k). 3-Wege wird korrekt
# verarbeitet (capture akzeptiert len(oc)>=2). Die europäischen Top-5 laufen im Sommer nicht; wenn
# ihre Saison startet (August), gehören ihre Poly-Tags (la-liga, serie-a, bundesliga, ligue-1) hier
# dazu — rawByTag im Output zeigt dann, welcher Slug echt Events liefert.
SPORT_TAGS = ["nba", "nfl", "mlb", "nhl", "mls", "epl", "soccer", "tennis", "ucl",
              "esports", "cs2", "lol", "dota", "valorant",
              "ufc", "mma", "boxing", "golf", "f1", "cricket"]
GAMMA = "https://gamma-api.polymarket.com/events"
HOLDERS = "https://data-api.polymarket.com/holders?market={cond}&limit=200"
_HTTP_TIMEOUT = 12
MAX_HOLDER_CALLS = 90   # Deckel gegen API-Last: die VOLUMENSTÄRKSTEN near-KO-Märkte bekommen den Geld-Split


def _tags():
    try:
        raw = _json.loads((BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        return raw.get("poly", {}).get("money_broad_tags") or SPORT_TAGS
    except Exception:
        return SPORT_TAGS


def _get(url):
    try:
        req = _url.Request(url, headers={"User-Agent": "BetEdge/1.0", "Accept": "application/json"})
        with _url.urlopen(req, timeout=_HTTP_TIMEOUT) as r:
            return _json.loads(r.read())
    except Exception as e:
        print(f"  HTTP {url[:70]}… : {e}")
        return None


def _gamma_events(tag, closed):
    """Offene (near-kickoff) bzw. geschlossene (aufgelöste) Events eines Sport-Tags."""
    out, offset = [], 0
    for _ in range(4):   # bis 400 Events je Tag
        url = (f"{GAMMA}?tag_slug={tag}&limit=100&offset={offset}"
               f"&active=true&closed={'true' if closed else 'false'}&order=startDate&ascending=false")
        page = _get(url)
        if not isinstance(page, list) or not page:
            break
        out += page
        if len(page) < 100:
            break
        offset += 100
    return out


# 23.07.2026 (Lucas: „alles nehmen wo Volumen drauf ist, egal welche Sportart"). Statt nur eine
# hartcodierte Tag-Liste abzugrasen (die schon 2× eine ganze Liga verpasst hat — E-Sport, dann MLS):
# tag-LOS die volumenstärksten Events holen. Der Sport-Filter passiert von selbst über das
# Anpfiff-Fenster (0<htk<=3h) im Ingest — Politik/Krypto haben keinen unmittelbaren Anpfiff
# (startDate liegt in der Vergangenheit → htk<0 → raus). Liga = Slug-Präfix (mls-… → MLS).
SWEEP_PAGES = 5   # bis 500 Events je Richtung, nach Volumen sortiert


def _gamma_top(closed):
    """Tag-LOS die volumenstärksten Events (offen bzw. aufgelöst). Defensiv — [] bei Fehler."""
    out, offset = [], 0
    for _ in range(SWEEP_PAGES):
        url = (f"{GAMMA}?limit=100&offset={offset}"
               f"&active=true&closed={'true' if closed else 'false'}&order=volume&ascending=false")
        page = _get(url)
        if not isinstance(page, list) or not page:
            break
        out += page
        if len(page) < 100:
            break
        offset += 100
    return out


def _league_from_slug(key):
    """Liga-Label aus dem Event-Slug-Präfix (mls-phi-nyr-… → MLS). Fallback: OTHER."""
    head = str(key or "").split("-", 1)[0].strip().lower()
    return head.upper() if head and not head.isdigit() else "OTHER"


def _hours_to_ko(ev, now):
    ko = ev.get("startTime") or ev.get("gameStartTime") or ev.get("startDate")
    try:
        t = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        return (t - now).total_seconds() / 3600
    except Exception:
        return None


def _outcomes(ev):
    """Moneyline-Markt eines Events generisch parsen → [{label, price, cond, token}].
    Nimmt den ersten Markt mit ≥2 Ausgängen und Preisen (US-Sport = 2-Wege, Fußball = 3-Wege)."""
    for m in (ev.get("markets") or []):
        try:
            names = _json.loads(m.get("outcomes", "[]") or "[]")
            prices = _json.loads(m.get("outcomePrices", "[]") or "[]")
            tokens = _json.loads(m.get("clobTokenIds", "[]") or "[]")
        except Exception:
            continue
        cond = m.get("conditionId")
        if len(names) >= 2 and len(prices) == len(names):
            rows = []
            for i, nm in enumerate(names):
                try:
                    p = float(prices[i])
                except (TypeError, ValueError, IndexError):
                    p = None
                rows.append({"label": str(nm), "price": p, "cond": cond,
                             "token": tokens[i] if i < len(tokens) else None})
            return rows
    return []


def _money_shares(outcomes):
    """Geld-Split je Ausgang aus der Holders-API (Shares × Preis = $-Wert). {label: usd} oder None."""
    try:
        from fetch_wm_poly_smartmoney import _http_get, _holders_for_token
    except Exception:
        return None
    usd = {}
    for o in outcomes:
        if not (o.get("cond") and o.get("token") and isinstance(o.get("price"), (int, float)) and o["price"] > 0):
            continue
        data = _http_get(HOLDERS.format(cond=o["cond"]))
        holders = _holders_for_token(data, o["token"]) if data else []
        usd[o["label"]] = sum(a for _, a in holders) * float(o["price"])
    return usd if sum(usd.values()) > 0 else None


def fetch_markets():
    """Alle Poly-Sportmärkte über die Sport-Tags. Real, defensiv, gedeckelt. Rückgabeformat siehe
    capture()/resolutions(): {key, league, hoursToKickoff, totalUsd, shares, prices,
    resolved, resolvedPrices}. Bei jedem Fehler wird der Markt übersprungen, nie geworfen."""
    now = _now()
    min_vol, _ = _cfg()
    tags = _tags()
    markets = []
    raw_by_tag = {}                      # je Tag: wie viele ROH-Events kamen (offen+aufgelöst)
    seen = set()                         # Dedup: ein Markt kann unter mehreren Tags liegen (cs2 ⊂ esports)
    candidates = []                      # near-kickoff 2-Wege-Kandidaten, VOR den Holders-Calls

    def _ingest(open_evs, closed_evs, league_of):
        """Ein Fetch-Ergebnis einsammeln. `league_of(ev, key)` liefert das Liga-Label.
        Anpfiff-Fenster (0<htk<=3h) + Volumen sind der eigentliche Sport-Filter."""
        # 1) Offene, near-kickoff Märkte SAMMELN (Holders-Call später, nach Volumen priorisiert)
        for ev in open_evs:
            try:
                key = ev.get("slug") or ev.get("id")
                if not key or (key, False) in seen:
                    continue
                htk = _hours_to_ko(ev, now)
                if htk is None or not (0 < htk <= PMA.CAPTURE_WINDOW_H):
                    continue        # kein unmittelbarer Anpfiff → kein Sportspiel (Politik/Krypto raus)
                vol = float(ev.get("volume") or 0)
                if vol < min_vol:
                    continue
                oc = _outcomes(ev)
                if len(oc) < 2:
                    continue
                seen.add((key, False))
                candidates.append((vol, key, league_of(ev, key), htk, oc))
            except Exception:
                continue

        # 2) Kürzlich aufgelöste Märkte → Gewinner (settlet auf 1.00) — kein Holders-Call nötig
        for ev in closed_evs:
            try:
                key = ev.get("slug") or ev.get("id")
                if not key or (key, True) in seen:
                    continue
                oc = _outcomes(ev)
                rp = {o["label"]: o["price"] for o in oc if o["price"] is not None}
                if rp:
                    seen.add((key, True))
                    markets.append({"key": key, "league": league_of(ev, key),
                                    "resolved": True, "resolvedPrices": rp,
                                    "hoursToKickoff": None, "totalUsd": 0, "shares": {}, "prices": {}})
            except Exception:
                continue

    # A) Kuratierte Sport-Tags (präzises Liga-Label = Tag)
    for tag in tags:
        open_evs = _gamma_events(tag, closed=False)
        closed_evs = _gamma_events(tag, closed=True)
        raw_by_tag[tag] = len(open_evs) + len(closed_evs)
        _ingest(open_evs, closed_evs, lambda ev, key, _t=tag: _t.upper())

    # B) Tag-LOSER Volumen-Sweep — fängt JEDE Sportart mit Volumen ein, auch ohne kuratierten Tag
    # (nimmt der „Liga fehlt still"-Klasse die Grundlage). Dedup gegen A über `seen`; Liga aus Slug.
    sweep_open = _gamma_top(closed=False)
    sweep_closed = _gamma_top(closed=True)
    before = len(candidates) + len(markets)
    _ingest(sweep_open, sweep_closed, lambda ev, key: _league_from_slug(key))
    sweep_added = (len(candidates) + len(markets)) - before

    # 21.07.2026 (Lucas: „mehr Sport?"): das Holders-Budget nach VOLUMEN vergeben — die größten
    # near-kickoff-Märkte zuerst, EGAL welche Sportart. Vorher lief es in Tag-Reihenfolge → die
    # täglichen Ligen (MLB/Tennis/Esport) fraßen die 60 Calls, ein UFC-Main-Event am Listen-Ende
    # bekam nie einen Geld-Split. Jetzt kriegt der wertvollste Markt jeder Sportart seine Chance.
    candidates.sort(key=lambda c: -c[0])
    holder_calls = 0
    for vol, key, league, htk, oc in candidates:
        if holder_calls >= MAX_HOLDER_CALLS:
            break
        try:
            shares = _money_shares(oc)
        except Exception:
            shares = None
        holder_calls += 1
        if not shares:
            continue     # ohne Geld-Split keine Aussage über „liegt das Geld richtig"
        prices = {o["label"]: o["price"] for o in oc if o["price"] is not None}
        markets.append({"key": key, "league": league,
                        "hoursToKickoff": htk, "totalUsd": round(vol),
                        "shares": shares, "prices": prices,
                        "resolved": False, "resolvedPrices": {}})
    fetch_markets.sweep_stats = {"sweepOpen": len(sweep_open), "sweepClosed": len(sweep_closed),
                                 "sweepAdded": sweep_added}

    live = {t: n for t, n in raw_by_tag.items() if n}
    _sw = fetch_markets.sweep_stats
    print(f"  Gamma: {len(markets)} Markt-Zeilen über {len(tags)} Tags + Volumen-Sweep · "
          f"{len(candidates)} near-KO-Kandidaten · {holder_calls} Holders-Calls (nach Volumen)")
    print(f"  Roh-Events je Tag (nur >0): {live}")
    print(f"  Volumen-Sweep (tag-los): {_sw['sweepOpen']} offen · {_sw['sweepClosed']} aufgelöst "
          f"· {_sw['sweepAdded']} zusätzlich gefunden (Ligen, die kein Tag abdeckte)")
    fetch_markets.raw_by_tag = raw_by_tag   # 21.07.2026: für die Diagnose im Output
    return markets


def capture(markets, frozen, now=None, min_vol=MIN_VOL_USD):
    """Nah am Anpfiff einfrieren (Geld-Verteilung + Preis + Liga). REIN, testbar."""
    now = now or _now()
    out = dict(frozen or {})
    for m in markets or []:
        htk = m.get("hoursToKickoff")
        try:
            htk = float(htk)
        except (TypeError, ValueError):
            continue
        if not (0 < htk <= PMA.CAPTURE_WINDOW_H) or float(m.get("totalUsd") or 0) < min_vol:
            continue
        key = m.get("key")
        prev = out.get(key)
        if prev is not None and prev.get("hoursToKickoff", 99) <= htk:
            continue
        out[key] = {"shares": m.get("shares") or {}, "prices": m.get("prices") or {},
                    "league": m.get("league"), "totalUsd": round(float(m.get("totalUsd") or 0)),
                    "hoursToKickoff": round(htk, 2), "capturedAt": now.isoformat()}
    return out


def resolutions(markets) -> dict:
    """{key: winner} aus den aufgelösten Poly-Märkten (settlet auf 1.00)."""
    out = {}
    for m in markets or []:
        if not m.get("resolved"):
            continue
        w = winner_from_prices(m.get("resolvedPrices") or {})
        if w:
            out[m.get("key")] = w
    return out


def main() -> int:
    min_vol, min_odds = _cfg()
    markets = fetch_markets()
    if not markets:
        print("ℹ️  Keine Poly-Märkte (läuft scharf nur am Mac-Runner) — Dateien unangetastet")
        return 0
    frozen = capture(markets, _load(CLOSE_FILE), min_vol=min_vol)
    (BASE / CLOSE_FILE).write_text(json.dumps(frozen, ensure_ascii=False, indent=1), encoding="utf-8")

    rep = PMA.evaluate(frozen, resolutions(markets), min_odds=min_odds)
    rep["generatedAt"] = _now().isoformat()
    rep["minVolUsd"] = min_vol
    rep["scope"] = "broad_all_leagues"
    # 21.07.2026: welche Sport-Tags liefern überhaupt Events (statt zu raten, welche Poly hat)?
    rep["rawByTag"] = getattr(fetch_markets, "raw_by_tag", {})
    rep["sweepStats"] = getattr(fetch_markets, "sweep_stats", {})
    (BASE / OUT_FILE).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"=== Liegt das Geld richtig? BREIT · min Vol ${min_vol:.0f} · min Quote {min_odds} ===")
    print(f"Eingefroren {len(frozen)} · aufgelöst {rep['n']}")
    for lg in rep.get("byLeague", [])[:20]:
        print(f"  {lg['league']:18} n={lg['n']:3}  Geld {lg['moneyHitRate']*100:.0f}%  "
              f"Brier G {lg['brierMoney']} vs P {lg['brierPrice']}  → {lg['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
