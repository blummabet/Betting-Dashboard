#!/usr/bin/env python3
"""
poly_book_probe.py — Würden 5 $ überhaupt gefüllt? (26.08.2026, Lucas)

## Warum

Der Auto-Trader lehnt ein Signal als ERSTES am Volumen ab (`trade.min_vol_usdc`, 1.500 $) und
kommt deshalb bei genau den Spielen, die Steam-Lag meldet, nie bis zum Orderbuch. Ergebnis:
50 geloggte Steam-Lag-Signale, 0 Trades — und niemand weiß, ob das richtig war.

Lucas' Einwand ist berechtigt: wir setzen 5 $ pro Trade. Bei 489 $ im Markt sollte das
unterzubringen sein. Aber `vol` ist Gammas `event.volume` — der **kumulierte Umsatz über die
Lebensdauer**, nicht die Tiefe, die gerade im Buch liegt. Die 489 $ können drei alte Trades sein.

Also messen statt schätzen. Diese Sonde fragt für abgelehnte Steam-Lag-Signale einmal das echte
Orderbuch ab und schreibt mit, was drin lag. Nach ein paar Tagen steht da, ob 5 $ gefüllt worden
wären und zu welchem Preis — und dann ist die Schwellen-Entscheidung trivial statt mutig.

## Sicherheit

**Diese Sonde platziert NICHTS.** Sie liest Gamma (Event → Token) und den CLOB (Buch) und
schreibt eine Log-Datei. Kein Private Key, keine Order-Funktion, kein Verkauf. Der Test
`test_keine_order_funktion_importiert` hält das fest.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D
from safe_write import write_json_atomic

BASE = Path(__file__).resolve().parent
PRICES_FILE = Path(str(D.file("wm_poly_prices.json", "liga_poly_prices.json")))
OUT_FILE    = Path(str(D.file("wm_poly_book_probe.json", "liga_poly_book_probe.json")))
LOG_FILE    = Path(str(D.file("steam_lag_log.json", "liga_steam_lag_log.json")))

GAMMA_SLUG_URL = "https://gamma-api.polymarket.com/events?slug={slug}"
# hw/dr/aw → Gammas groupItemThreshold. Dieselbe Zuordnung wie in manage_wm_poly_positions;
# NICHT über Namens-Fuzzy, das ist auf Poly die Fehlerquelle Nummer eins.
KEY_TO_THRESHOLD = {"hw": "0", "dr": "1", "aw": "2"}
MARKET_LABEL = {"hw": "Heimsieg", "dr": "Unentschieden", "aw": "Auswärtssieg"}

MAX_PROBES = int(os.environ.get("BOOK_PROBE_MAX", "6"))   # Netz-Budget je Lauf
# Unter dem Vielfachen unseres Einsatzes lohnt die Frage nicht: bei 8 $ Lebenszeit-Umsatz
# braucht niemand ein Orderbuch, um 5,50 $ auszuschließen. Hält das Netz-Budget frei für
# die Fälle, in denen die Antwort offen ist.
MIN_VOL_MULTIPLE = 3.0
KEEP_DAYS  = 45
MAX_ROWS   = 20_000


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def trader_cfg(attr, default):
    """Zahl aus dem Auto-Trader lesen — EINE Quelle. Hier noch einmal getippt, driften Sonde
    und Trader auseinander, sobald einer angefasst wird, und die Messung misst das Falsche."""
    try:
        import auto_wm_poly_trigger as T
        v = getattr(T, attr, default)
        return v if isinstance(v, (int, float)) else default
    except Exception:
        return default


def open_steam_keys(log) -> set:
    """Match-Keys mit einem LAUFENDEN Steam-Lag-Signal. REIN.

    26.08.2026: erst über `fx["steamLag"]` gebaut — das Flag im Preis-File ist aber flüchtig
    und stand beim Bau auf 0 von 62 Spielen, während im Log 18 Signale offen waren. Gemessen
    hätte die Sonde damit nie etwas. Das Log ist der dauerhafte Datensatz und genau das, was
    Lucas im Telegram-Kanal sieht.
    """
    out = set()
    for sig in ((log or {}).get("signals") or []):
        if isinstance(sig, dict) and sig.get("status") == "OPEN" and sig.get("matchKey"):
            out.add(str(sig["matchKey"]))
    return out


def candidates(fixtures, min_vol, stake, steam_keys=None, max_n=MAX_PROBES) -> list:
    """Welche Spiele sind es wert, das Buch anzufragen? REIN.

    Genau die Lücke, um die es geht: ein Steam-Lag-Signal liegt an, aber das Volumen ist unter
    der Trader-Hürde — der Trader schaut also nie hin. Nach unten begrenzt MIN_VOL_MULTIPLE:
    bei 8 $ Lebenszeit-Umsatz ist die Frage nicht offen, und jede Anfrage kostet Netz-Budget.
    """
    out = []
    for fx in (fixtures or []):
        if not isinstance(fx, dict):
            continue
        if not (fx.get("steamLag") or str(fx.get("key") or "") in (steam_keys or set())):
            continue
        try:
            vol = float(fx.get("vol") or 0)
        except (TypeError, ValueError):
            continue
        if vol >= min_vol or vol < stake * MIN_VOL_MULTIPLE:
            continue
        best, key = None, None
        for k in KEY_TO_THRESHOLD:
            e = fx.get("edge_" + k)
            if isinstance(e, (int, float)) and (best is None or e > best):
                best, key = e, k
        if key is None or (best or 0) <= 0:
            continue
        out.append({"key": fx.get("key"), "slug": fx.get("slug"), "market": key,
                    "home": fx.get("homeName") or fx.get("home"),
                    "away": fx.get("awayName") or fx.get("away"),
                    "vol": vol, "edgePp": round(best, 2),
                    "fair": fx.get("fair_" + key), "polyMid": fx.get("poly_" + key),
                    "matchDate": str(fx.get("date") or "")[:10]})
    out.sort(key=lambda r: -(r["edgePp"] or 0))
    return out[:max_n]


def token_from_event(event, market_key) -> str | None:
    """Gamma-Event + hw/dr/aw → CLOB-Token des JA-Outcomes. REIN.

    Über groupItemThreshold, nicht über Teamnamen — Namens-Matching ist auf Poly die
    zuverlässigste Art, sich den falschen Markt einzufangen.
    """
    thr = KEY_TO_THRESHOLD.get(market_key)
    if not thr or not isinstance(event, dict):
        return None
    for m in (event.get("markets") or []):
        if str(m.get("groupItemThreshold", "")) != thr:
            continue
        raw = m.get("clobTokenIds")
        try:
            ids = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            return None
        if isinstance(ids, list) and ids:
            return str(ids[0])
    return None


def assess(book, stake, fair) -> dict:
    """Was sagt das Buch über unseren 5-$-Einstieg? REIN.

    `liqUSD` ist Top-of-Book (bester Bid + bester Ask in $). Es ist eine UNTERGRENZE für die
    verfügbare Tiefe, kein Gesamtbuch — deshalb heißt das Feld `fitsTopOfBook` und nicht
    „füllt sicher". Kein Buch = keine Aussage, nicht „passt schon".
    """
    if not isinstance(book, dict):
        return {"book": False, "fitsTopOfBook": None, "askEdgePp": None,
                "ask": None, "bid": None, "spreadPP": None, "liqUSD": None}
    ask, bid = book.get("ask"), book.get("bid")
    liq = book.get("liqUSD")
    edge = None
    if isinstance(fair, (int, float)) and isinstance(ask, (int, float)):
        edge = round((fair - ask) * 100, 2)
    fits = None
    if isinstance(liq, (int, float)):
        fits = liq >= stake
    return {"book": True, "fitsTopOfBook": fits, "askEdgePp": edge,
            "ask": ask, "bid": bid, "spreadPP": book.get("spreadPP"), "liqUSD": liq}


def merge(old_rows, new_rows, now=None, keep_days=KEEP_DAYS, max_rows=MAX_ROWS) -> list:
    """Alt + neu. Dedupe auf (Spiel, Markt, Zeitstempel) — die Zeitreihe IST hier das Ergebnis,
    anders als beim Kohärenz-Beobachter wird also nicht je Fenster zusammengefasst. REIN."""
    ref = now or _now()
    keep = {}
    for r in list(old_rows or []) + list(new_rows or []):
        if not isinstance(r, dict):
            continue
        seen = _parse(r.get("ts"))
        if seen and (ref - seen).days > keep_days:
            continue
        keep[(r.get("key"), r.get("market"), r.get("ts"))] = r
    rows = sorted(keep.values(), key=lambda r: str(r.get("ts") or ""))
    return rows[-max_rows:]


def summarize(rows) -> dict:
    """Die eine Frage: wie oft hätte unser Einsatz ins Top-of-Book gepasst? REIN."""
    n = len(rows or [])
    mit_buch = [r for r in (rows or []) if r.get("book")]
    passt = [r for r in mit_buch if r.get("fitsTopOfBook")]
    spreads = sorted(r["spreadPP"] for r in mit_buch if isinstance(r.get("spreadPP"), (int, float)))
    liqs = sorted(r["liqUSD"] for r in mit_buch if isinstance(r.get("liqUSD"), (int, float)))
    med = lambda xs: xs[len(xs) // 2] if xs else None
    return {"n": n, "mitBuch": len(mit_buch), "passt": len(passt),
            "medianSpreadPP": med(spreads), "medianLiqUSD": med(liqs)}


# ── I/O ──────────────────────────────────────────────────────────────────────

def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "fehlt"
    except Exception as e:
        return None, str(e)


def main() -> int:
    from manage_wm_poly_positions import fetch_token_book, _http_get

    stake   = trader_cfg("FLAT_STAKE_USDC", 5.5)
    min_vol = trader_cfg("MIN_VOL", 1500)

    data, err = _load(PRICES_FILE)
    if err:
        print("ℹ️  %s: %s — keine Sonde." % (PRICES_FILE.name, err))
        return 0
    log, log_err = _load(LOG_FILE)
    keys = open_steam_keys(log or {})
    if log_err and log_err != "fehlt":
        print("⚠️  %s nicht lesbar (%s) — nur das flüchtige steamLag-Flag als Auslöser."
              % (LOG_FILE.name, log_err))
    cands = candidates((data or {}).get("allFixtures") or [], min_vol, stake, steam_keys=keys)
    print("🔬 Buch-Sonde — würden $%.2f gefüllt? (Hürde des Traders: $%s)" % (stake, f"{min_vol:,.0f}"))
    if not cands:
        print("   Keine Steam-Lag-Signale unter der Volumen-Hürde — nichts zu messen. "
              "(%d offene Signale im Log)" % len(keys))

    now = _now()
    rows = []
    for c in cands:
        ev = _http_get(GAMMA_SLUG_URL.format(slug=c["slug"])) if c.get("slug") else None
        event = ev[0] if isinstance(ev, list) and ev else None
        token = token_from_event(event, c["market"])
        book = fetch_token_book(token) if token else None
        a = assess(book, stake, c.get("fair"))
        rows.append({"ts": now.isoformat(), "key": c["key"], "market": c["market"],
                     "marketLabel": MARKET_LABEL.get(c["market"], c["market"]),
                     "match": "%s – %s" % (c["home"], c["away"]), "matchDate": c["matchDate"],
                     "vol": c["vol"], "edgePp": c["edgePp"], "stake": stake,
                     "token": (token or "")[:16], **a})
        if not token:
            print("   ⚠️  %s: kein Token über den Slug auflösbar" % c["slug"])
            continue
        if not a["book"]:
            print("   🚫 %-34s kein beidseitiges Buch (dünn)" % (rows[-1]["match"])[:34])
            continue
        print("   %s %-30s Vol $%-8.0f Ask %.3f · Spread %4.1fpp · Top-of-Book $%-7.0f · Ask-Edge %s"
              % ("✅" if a["fitsTopOfBook"] else "❌", (rows[-1]["match"])[:30], c["vol"],
                 a["ask"] or 0, a["spreadPP"] or 0, a["liqUSD"] or 0,
                 ("%+.1fpp" % a["askEdgePp"]) if a["askEdgePp"] is not None else "—"))

    old, err = _load(OUT_FILE)
    if err and err != "fehlt":
        print("⚠️  %s nicht lesbar (%s) — wird NICHT überschrieben." % (OUT_FILE.name, err))
        return 0
    merged = merge((old or {}).get("rows") or [], rows, now=now)
    rep = summarize(merged)
    write_json_atomic(OUT_FILE, {"updatedAt": now.isoformat(), "stakeUsdc": stake,
                                 "traderMinVolUsdc": min_vol, "summary": rep,
                                 "rows": merged}, indent=1)
    print("   Bilanz: %d Messungen · %d mit Buch · %d davon hätten $%.2f getragen"
          % (rep["n"], rep["mitBuch"], rep["passt"], stake))
    print("💾 %s" % OUT_FILE.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
