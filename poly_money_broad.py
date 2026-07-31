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
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import poly_money_accuracy as PMA

BASE = Path(__file__).resolve().parent

MIN_VOL_USD = 7_500     # „5-10k oben liegen" — Mitte
MIN_ODDS    = 1.35      # Lucas: triviale Favoriten (≤1.35) raus
CLOSE_FILE  = "poly_money_broad_close.json"
OUT_FILE    = "poly_money_broad.json"
# 25.07.2026 (Lucas ① Momentum): globale Poly-Preis-ZEITREIHE je Markt — fortgeschrieben bei jedem
# Lauf, damit „was bewegt sich gerade" (Steam vs Reversal) über ALLE Sportarten sichtbar wird. Wie
# damals die Wale: die Erfassung startet jetzt, die Ansicht füllt sich über die nächsten Läufe.
HIST_FILE   = "poly_money_broad_history.json"
HIST_MAX_POINTS = 48     # je Markt ~1 Tag Punkte (Runner alle ~30 min) — reicht für kurzfristiges Steam
HIST_KEEP_H     = 96.0   # Märkte, die 4 Tage nicht mehr gesehen wurden, fallen raus (aufgelöst/vorbei)
# ② Sharp-Wallet-Track (25.07.2026, Lucas): je Whale den EINSTIEGSPREIS je Markt merken; bei
# Auflösung CLV (Einstieg→Close) + Treffer werten → wer schlägt systematisch die Linie („scharf",
# nicht bloß groß). Wie [[project_wallet_track_record]], aber GLOBAL über alle Sportarten.
WTRACK_FILE = "poly_wallet_track.json"


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
# 28.07.2026 (Lucas: „CLV misst 0"): der Whale-EINSTIEGSPREIS. /holders liefert nur AKTUELLE Shares →
# firstPrice ≈ Close ≈ CLV 0 (strukturell, 67/71 Positionen). Der ECHTE Ø-Einstieg steht in /positions
# (avgPrice je asset). Damit wird CLV = Close − echter Einstieg endlich messbar. Gedeckelt + abschaltbar.
POSITIONS = "https://data-api.polymarket.com/positions?user={user}&sizeThreshold=1&limit=500"
# 31.07.2026 (Lucas): echte Lebenszeit-P&L je Wallet (kumuliert, inkl. geschlossener Positionen) →
# damit die „schärfste Wallets"-Rangliste nach TATSÄCHLICHEM Gewinn geht, nicht nur nach CLV-Timing.
# Antwort: Liste {t,p}; letzter p = aktuelle Gesamt-Bilanz in USD (verifiziert gegen das Poly-Profil).
PNL_API = "https://user-pnl-api.polymarket.com/user-pnl?user_address={user}&interval=all&fidelity=1d"
MAX_POSITION_CALLS = int(os.environ.get("POLY_MAX_POSITION_CALLS") or 150)
FETCH_AVGPRICE = (os.environ.get("POLY_FETCH_AVGPRICE") or "1") == "1"


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


WHALES_PER_MARKET = 4   # 25.07.2026 (Lucas: „was setzen einzelne Wale") — Top-N je Markt mitschreiben


def _market_money(outcomes):
    """Aus EINEM Holders-Fetch je Ausgang beides ableiten (quota-schonend):
      shares = Geld-Split {label: usd} (Shares × Preis)
      whales = die größten EINZELNEN Wallets [{wallet, side, usd}] über alle Ausgänge
    → {"shares":…, "whales":…} oder None. 25.07.2026 (Lucas): globale Einzel-Wale (c)."""
    try:
        from fetch_wm_poly_smartmoney import _http_get, _holders_for_token
    except Exception:
        return None
    usd, whales = {}, []
    for o in outcomes:
        if not (o.get("cond") and o.get("token") and isinstance(o.get("price"), (int, float)) and o["price"] > 0):
            continue
        data = _http_get(HOLDERS.format(cond=o["cond"]))
        holders = _holders_for_token(data, o["token"]) if data else []
        price = float(o["price"])
        usd[o["label"]] = sum(a for _, a in holders) * price
        for w, a in holders:
            whales.append({"wallet": w, "side": o["label"], "usd": round(a * price)})
    if sum(usd.values()) <= 0:
        return None
    whales.sort(key=lambda x: -x["usd"])
    return {"shares": usd, "whales": whales[:WHALES_PER_MARKET]}


def _money_shares(outcomes):
    """Rückwärtskompatibel: nur der Geld-Split. Delegiert an _market_money."""
    mm = _market_money(outcomes)
    return mm["shares"] if mm else None


def _avg_from_positions(data, token):
    """Poly /positions-Antwort → Ø-Einstiegspreis (avgPrice) der Position auf `token` (asset).
    None, wenn nicht gefunden oder außerhalb (0,1). REIN/testbar."""
    for p in (data or []):
        if not isinstance(p, dict):
            continue
        if str(p.get("asset") or p.get("token") or p.get("tokenId") or "") == str(token):
            ap = p.get("avgPrice", p.get("avg_price"))
            try:
                ap = float(ap)
            except (TypeError, ValueError):
                return None
            return round(ap, 4) if 0 < ap < 1 else None
    return None


def _lifetime_pnl(data):
    """user-pnl-Antwort (Liste {t,p} kumulierte P&L) → letzter p = Lebenszeit-P&L (USD, kann negativ).
    None wenn leer/unlesbar. REIN/testbar."""
    if not isinstance(data, list) or not data:
        return None
    last = data[-1]
    if not isinstance(last, dict):
        return None
    try:
        return round(float(last.get("p")), 2)
    except (TypeError, ValueError):
        return None


def enrich_wallet_pnl(scores, get, budget, min_n=5):
    """Lebenszeit-P&L je bewertetem Wallet nachziehen → scores[w]['pnl'] (USD). Priorisiert Wallets mit
    der meisten getrackten Historie, hart per budget[0] (Mutable-Counter) gedeckelt. Wer nicht drankommt,
    behält seinen vorherigen pnl (aus prev — update_wallet_track kopiert prev-scores). REIN/testbar."""
    if not isinstance(scores, dict):
        return 0
    cand = sorted((w for w, sc in scores.items() if isinstance(sc, dict) and (sc.get("n") or 0) >= min_n),
                  key=lambda w: -(scores[w].get("n") or 0))
    n = 0
    for w in cand:
        if budget[0] <= 0:
            break
        budget[0] -= 1
        pnl = _lifetime_pnl(get(PNL_API.format(user=w)))
        if pnl is not None:
            scores[w]["pnl"] = pnl
            n += 1
    return n


def _enrich_whales_avg(whales, label_token, cache, get, budget):
    """Top-Whales um ihren ECHTEN Ø-Einstieg (avgPrice aus /positions) anreichern → wh['avgPrice'].
    cache {wallet: positions-data} (je Wallet EIN Call, marktübergreifend); budget=[rest_calls]
    (Mutable-Counter, deckelt die Calls je Lauf). get(url)->data. REIN/testbar (get injizierbar)."""
    for wh in (whales or []):
        tok = label_token.get(wh.get("side"))
        w = wh.get("wallet")
        if not tok or not w:
            continue
        if w not in cache:
            if budget[0] <= 0:
                continue
            budget[0] -= 1
            cache[w] = get(POSITIONS.format(user=w)) or []
        ap = _avg_from_positions(cache[w], tok)
        if ap is not None:
            wh["avgPrice"] = ap
    return whales


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
    # Ø-Einstieg-Anreicherung (CLV-Fix): eine /positions-Abfrage je Wallet, marktübergreifend gecacht,
    # hart gedeckelt. Fällt der Import/Fetch aus, läuft alles wie bisher weiter (nur ohne avgPrice).
    _pos_cache, _pos_budget = {}, [MAX_POSITION_CALLS]
    _avg_get = None
    if FETCH_AVGPRICE:
        try:
            from fetch_wm_poly_smartmoney import _http_get as _avg_get
        except Exception:
            _avg_get = None
    for vol, key, league, htk, oc in candidates:
        if holder_calls >= MAX_HOLDER_CALLS:
            break
        try:
            mm = _market_money(oc)     # 25.07.2026: EIN Fetch → Shares + Einzel-Wale
        except Exception:
            mm = None
        holder_calls += 1
        if not mm:
            continue     # ohne Geld-Split keine Aussage über „liegt das Geld richtig"
        shares = mm["shares"]
        prices = {o["label"]: o["price"] for o in oc if o["price"] is not None}
        _whales = mm.get("whales") or []
        if _avg_get and _whales:
            try:
                _enrich_whales_avg(_whales, {o["label"]: o.get("token") for o in oc if o.get("token")},
                                   _pos_cache, _avg_get, _pos_budget)
            except Exception:
                pass
        markets.append({"key": key, "league": league,
                        "hoursToKickoff": htk, "totalUsd": round(vol),
                        "shares": shares, "prices": prices, "whales": _whales,
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
                    "whales": m.get("whales") or [],   # 25.07.2026 (Lucas): Einzel-Wale je Markt (c)
                    "hoursToKickoff": round(htk, 2), "capturedAt": now.isoformat()}
    return out


def append_history(prev, markets, now=None, min_vol=MIN_VOL_USD,
                   max_points=HIST_MAX_POINTS, keep_h=HIST_KEEP_H):
    """Globale Poly-Preis-Zeitreihe fortschreiben. REIN/testbar. je Markt eine Liste von
    {ts, p:{label:preis}, v:volumen, htk, league}; deckelt auf max_points, prunt Märkte, die
    seit keep_h nicht mehr gesehen wurden (aufgelöst/vorbei). 25.07.2026 (Lucas ① Momentum)."""
    now = now or _now()
    out = {k: list(v) for k, v in (prev or {}).items() if isinstance(v, list)}
    seen = set()
    for m in markets or []:
        if m.get("resolved"):
            continue
        key = m.get("key")
        prices = m.get("prices") or {}
        if not key or not prices or float(m.get("totalUsd") or 0) < min_vol:
            continue
        htk = m.get("hoursToKickoff")
        pt = {"ts": now.isoformat(),
              "p": {k: round(float(v), 4) for k, v in prices.items() if isinstance(v, (int, float))},
              "v": round(float(m.get("totalUsd") or 0)),
              "htk": round(float(htk), 2) if isinstance(htk, (int, float)) else None,
              "league": m.get("league")}
        arr = out.get(key) or []
        arr.append(pt)
        out[key] = arr[-max_points:]
        seen.add(key)
    cutoff = now - timedelta(hours=keep_h)
    for k in list(out.keys()):
        if k in seen:
            continue
        arr = out[k]
        try:
            last = datetime.fromisoformat(str(arr[-1]["ts"]).replace("Z", "+00:00")) if arr else None
        except Exception:
            last = None
        if not last or last < cutoff:
            del out[k]
    return out


def update_wallet_track(prev, markets, now=None, keep_h=HIST_KEEP_H, frozen=None):
    """② Sharp-Wallet-Track. REIN/testbar. Merkt je (wallet,markt,seite) den Einstiegspreis (erster
    beobachteter Preis, als der Wal auftauchte); bei Markt-Auflösung wird die Position gewertet:
      clvPP = (Close − Einstieg)·100   (positiv = früh billig rein, Linie geschlagen → scharf)
      win   = Seite == Gewinner
    Rückgabe {open, scores{wallet:{n,clvSumPP,wins,usd}}, updatedAt}. Global über alle Sportarten."""
    now = now or _now()
    prev = prev or {}
    openp = {k: dict(v) for k, v in (prev.get("open") or {}).items()}
    scores = {w: dict(s) for w, s in (prev.get("scores") or {}).items()}

    # 1) offene Whale-Positionen aus KOMMENDEN Märkten erfassen/auffrischen
    for m in markets or []:
        if m.get("resolved"):
            continue
        key, prices = m.get("key"), m.get("prices") or {}
        if not key or not prices:
            continue
        for wh in m.get("whales") or []:
            w, side = wh.get("wallet"), wh.get("side")
            price = prices.get(side)
            if not w or side is None or not isinstance(price, (int, float)):
                continue
            ok = f"{w}|{key}|{side}"
            _avg = wh.get("avgPrice")
            _avg = round(float(_avg), 4) if isinstance(_avg, (int, float)) and 0 < _avg < 1 else None
            e = openp.get(ok)
            if e is None:
                openp[ok] = {"wallet": w, "key": key, "side": side, "league": m.get("league"),
                             "firstPrice": round(float(price), 4), "firstTs": now.isoformat(),
                             "lastPrice": round(float(price), 4), "usd": round(float(wh.get("usd") or 0))}
                if _avg is not None:
                    openp[ok]["entryPrice"] = _avg
            else:
                e["lastPrice"] = round(float(price), 4)
                e["usd"] = round(float(wh.get("usd") or 0))
                e["league"] = m.get("league")
                if _avg is not None:
                    e["entryPrice"] = _avg   # Ø-Einstieg mitziehen (Wal stockt evtl. auf)

    # 2) Positionen werten, deren Markt gerade aufgelöst ist
    winners = {m.get("key"): winner_from_prices(m.get("resolvedPrices") or {})
               for m in (markets or []) if m.get("resolved")}
    for ok in list(openp.keys()):
        e = openp[ok]
        if e["key"] not in winners:
            continue
        # 26.07.2026 (Lucas: „CLV misst nicht"): CLV gegen die EINGEFRORENE Closing-Linie, nicht
        # gegen lastPrice. Der lastPrice wird vor Auflösung oft nur EINMAL gesehen (Holder-Call-Cap +
        # Top-N-Wale-Cutoff + schnelle Märkte) → bliebe = firstPrice → CLV fälschlich 0. Der Close
        # aus poly_money_broad_close.json ist der echte Schlusskurs. Fallback: lastPrice (Alt-Verhalten).
        _close = ((frozen or {}).get(e["key"]) or {}).get("prices") or {}
        _cp = _close.get(e["side"])
        close_ref = float(_cp) if isinstance(_cp, (int, float)) else e["lastPrice"]
        # Einstiegsanker: der ECHTE Ø-Einstieg (entryPrice aus /positions avgPrice), sonst der erste
        # gesehene Preis (Alt-Verhalten, strukturell ~0 — s. 28.07.2026-Fix). CLV = Close − Einstieg.
        entry = e.get("entryPrice")
        if entry is None:
            entry = e["firstPrice"]
        clv = (close_ref - entry) * 100
        s = scores.setdefault(e["wallet"], {"n": 0, "clvSumPP": 0.0, "wins": 0, "usd": 0})
        s["n"] += 1
        s["clvSumPP"] = round(s["clvSumPP"] + clv, 2)
        if winners[e["key"]] and e["side"] == winners[e["key"]]:
            s["wins"] += 1
        s["usd"] += e.get("usd") or 0
        del openp[ok]

    # 3) verwaiste offene Positionen prunen (Markt seit keep_h nicht mehr gesehen)
    cutoff = now - timedelta(hours=keep_h)
    seen = {m.get("key") for m in (markets or [])}
    for ok in list(openp.keys()):
        e = openp[ok]
        if e["key"] in seen:
            continue
        try:
            first = datetime.fromisoformat(str(e["firstTs"]).replace("Z", "+00:00"))
        except Exception:
            first = None
        if not first or first < cutoff:
            del openp[ok]

    return {"open": openp, "scores": scores, "updatedAt": now.isoformat()}


def sharp_entries(prev, cur, min_n=4):
    """🔔 Sharp-im-Markt (25.07.2026, Lucas). REIN/testbar. NEUE offene Positionen (in cur, aber
    NICHT in prev) von bewiesen-scharfen Wallets (Score n≥min_n & Ø CLV > 0). Prev-vs-cur-Vergleich
    statt Zeitstempel → robust. Rückgabe absteigend nach Einsatz."""
    prev_open = set((prev or {}).get("open") or {})
    scores = (cur or {}).get("scores") or {}
    out = []
    for ok, e in ((cur or {}).get("open") or {}).items():
        if ok in prev_open:
            continue
        s = scores.get(e.get("wallet"))
        if not s or s.get("n", 0) < min_n:
            continue
        avg = s["clvSumPP"] / s["n"] if s["n"] else 0
        if avg <= 0:
            continue
        out.append({"wallet": e["wallet"], "key": e["key"], "side": e["side"], "league": e.get("league"),
                    "price": e.get("firstPrice"), "usd": e.get("usd") or 0, "avgClv": round(avg, 1),
                    "hit": round(s.get("wins", 0) / s["n"], 2), "n": s["n"]})
    out.sort(key=lambda x: -x["usd"])
    return out


def _format_sharp_alert(entries):
    lines = ["🔔 <b>Sharp im Markt</b> — bewiesen scharfe Wallet(s) frisch eingestiegen:", ""]
    for e in entries[:8]:
        w = e["wallet"]; short = w[:6] + "…" + w[-4:]
        lines.append(f"• {short} → <b>{e['side']}</b> @ {round((e.get('price') or 0) * 100)}¢ "
                     f"· {(e.get('league') or '').upper()} · ~${int(e.get('usd') or 0):,}")
        lines.append(f"   Track: Ø CLV +{e['avgClv']}pp · {round(e['hit'] * 100)}% Treffer · n{e['n']}")
    lines += ["", "Kein Auto-Bet — nur ein Signal. Selbst prüfen."]
    return "\n".join(lines)


def maybe_alert_sharp(prev, cur, min_n=4) -> int:
    """Alarm senden, wenn neue scharfe Einstiege da sind. Kür — darf den Lauf NIE kippen.
    Nutzt telegram_trades (Silent-Guard: leerer Token → False). Rückgabe: Anzahl alarmierter Einstiege."""
    ents = sharp_entries(prev, cur, min_n=min_n)
    if not ents:
        return 0
    try:
        import telegram_trades
        telegram_trades.send_trades_message(_format_sharp_alert(ents))
    except Exception as exc:
        print("ℹ️  Sharp-Alarm übersprungen:", exc)
    return len(ents)


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

    # ① Momentum (25.07.2026): globale Preis-Zeitreihe fortschreiben (Steam/Reversal über alle Sportarten)
    hist = append_history(_load(HIST_FILE), markets, min_vol=min_vol)
    (BASE / HIST_FILE).write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")

    # ② Sharp-Wallet-Track (25.07.2026): Einstieg→Close/Outcome je Whale werten (CLV/Treffer)
    prev_wtrack = _load(WTRACK_FILE)
    wtrack = update_wallet_track(prev_wtrack, markets, frozen=frozen)
    # 💰 Echte Lebenszeit-P&L je bewertetem Wallet nachziehen (user-pnl-api) — macht die „schärfste
    # Wallets"-Rangliste nach TATSÄCHLICHEM Gewinn möglich. Gedeckelt (POLY_PNL_MAX, Default 60),
    # defensiv gekapselt: fällt der Call/Endpoint aus, bleibt alles wie bisher (nur ohne pnl-Feld).
    try:
        _pnl_budget = [int(os.environ.get("POLY_PNL_MAX") or 60)]
        _n_pnl = enrich_wallet_pnl(wtrack.get("scores") or {}, _get, _pnl_budget, min_n=5)
        if _n_pnl:
            print(f"\U0001f4b0 Lifetime-P&L aktualisiert: {_n_pnl} Wallets")
    except Exception as _e:
        print(f"  P&L-Enrich uebersprungen (nicht fatal): {_e}")
    (BASE / WTRACK_FILE).write_text(json.dumps(wtrack, ensure_ascii=False, indent=1), encoding="utf-8")
    # 🔔 Sharp-im-Markt-Alarm: neue Einstiege bewiesen-scharfer Wallets → Telegram (Kür, nie fatal)
    n_alert = maybe_alert_sharp(prev_wtrack, wtrack)
    if n_alert:
        print(f"🔔 Sharp-Alarm: {n_alert} neue scharfe Einstiege gemeldet")

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
