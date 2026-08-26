#!/usr/bin/env python3
"""
betfair_coherence_watch.py — WANN liegt Geld in den Tormärkten? (26.08.2026, Lucas)

## Warum es das gibt

`betfair_coherence` hat seit dem Bau **kein einziges Mal** gefeuert (`n_observations: 0` in allen
drei Gewichtsdateien). Die naheliegende Antwort wäre „Schwellen zu streng" — die Messung sagt
etwas anderes:

    Real Madrid – Real Sociedad, 7h vor Anpfiff:
        Match Odds   80.644 €      ← das Geld ist da
        Ü/U 2.5         365 €      ← der Tormarkt ist leer
        BTTS          1.726 €

    Valencia – Betis, angepfiffen:
        Ü/U 2.5      38.736 €
        BTTS          6.688 €

Das Geld fließt zuerst in den Hauptmarkt und in die Tormärkte erst kurz vor Anpfiff. Das Signal
fragt also einen Markt ab, der zu seinem Zeitpunkt noch leer ist — **kein Kalibrierungsproblem,
ein Zeitpunkt-Problem.** Und weil gepostete Picks nicht mehr angefasst werden, kann ein Signal,
das erst kurz vor Anpfiff Material hat, eine Card grundsätzlich nicht mehr beeinflussen.

Das ist die These. Dieses Skript belegt oder widerlegt sie — mit Daten statt mit einem Snapshot.
Es schreibt bei jedem Betfair-Lauf mit, WORAN die Prüfung gescheitert ist und WIE WEIT der
Anpfiff weg war. Nach ein paar Tagen steht da eine Kurve, und die Entscheidung („ins Terminal
verschieben" oder „abschalten") trifft sich von selbst.

Read-only, kein Geld, nicht-blockierend.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import sharp_signals.betfair_coherence as C
from safe_write import write_json_atomic

BASE = Path(__file__).resolve().parent
SNAP_FILE = BASE / "betfair_prices.json"
OUT_FILE  = BASE / "betfair_coherence_watch.json"

# Nur diese Märkte kann ein Pick überhaupt treffen (sharp_signals/betfair_money._pick_target).
# „Half Time" & Co. stehen zwar in den Daten, werden aber nie abgefragt.
WATCHED = ("Over/Under 2.5 Goals", "Over/Under 3.5 Goals", "Both teams to Score?")

# Fenster bis Anpfiff. Grob genug, dass die Buckets sich füllen, fein genug um die Stelle zu
# sehen, an der das Geld kommt.
BUCKETS = ((0.0, 1.0, "0-1h"), (1.0, 3.0, "1-3h"), (3.0, 6.0, "3-6h"),
           (6.0, 12.0, "6-12h"), (12.0, 24.0, "12-24h"), (24.0, 1e9, ">24h"))
LIVE_BUCKET = "live/danach"

KEEP_DAYS = 45      # Beobachtungen älter als das fliegen raus
MAX_ROWS  = 20_000  # harte Kappung, damit die Datei nie explodiert


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def bucket_of(hours):
    """Stunden bis Anpfiff → Bucket-Label. None (unbekannt) bleibt None."""
    if hours is None:
        return None
    if hours <= 0:
        return LIVE_BUCKET
    for lo, hi, lab in BUCKETS:
        if lo <= hours < hi:
            return lab
    return ">24h"


def gate_for(game: dict, market_name: str, lam=None):
    """An welcher Hürde scheitert die Kohärenz-Prüfung für DIESEN Markt? REIN.

    Gibt (grund, geld, abweichung) zurück. grund ist einer von:
      wenig_sprossen · kein_lambda · wenig_geld · kein_preis · zu_kleine_abweichung · feuert
    Die Reihenfolge ist dieselbe wie im Signal — sonst zählen wir eine Hürde, die nie drankäme.
    """
    markets = game.get("markets") or {}
    rungs = C._ou_rungs(markets)
    if len(rungs) < C.MIN_RUNGS:
        return "wenig_sprossen", None, None
    if lam is None:
        fit = C._fit_lambda(rungs)
        if not fit:
            return "kein_lambda", None, None
        lam = fit[0]

    mk = markets.get(market_name)
    if not mk:
        return "kein_preis", None, None
    money = C._market_vol(mk)
    if money < C.MIN_MONEY_EUR:
        return "wenig_geld", money, None

    if market_name.startswith("Over/Under"):
        try:
            line = float(market_name.split("Over/Under ")[1].split(" Goals")[0])
        except Exception:
            return "kein_preis", money, None
        o = C._runner(mk, lambda s: s.startswith("Over"))
        u = C._runner(mk, lambda s: s.startswith("Under"))
        mkt = C._devig2(o and o.get("odd"), u and u.get("odd"))
        if mkt is None:
            return "kein_preis", money, None
        dev = abs(C._pois_over(line, lam) - mkt)
    else:
        sup = C._fit_supremacy(lam, (game.get("mo") or {}).get("fair"))
        if not sup:
            return "kein_preis", money, None
        _s, lh, la = sup
        y = C._runner(mk, lambda s: s.lower().startswith("yes"))
        n = C._runner(mk, lambda s: s.lower().startswith("no"))
        mkt = C._devig2(y and y.get("odd"), n and n.get("odd"))
        if mkt is None:
            return "kein_preis", money, None
        dev = abs(C._btts_p(lh, la) - mkt)

    if dev < C.MIN_EDGE:
        return "zu_kleine_abweichung", money, dev
    return "feuert", money, dev


def observe(snapshot: dict, now=None) -> list:
    """Snapshot → Beobachtungszeilen. REIN.

    `now` kommt aus dem Snapshot selbst, nicht von der Wanduhr — sonst misst ein spät gelesener
    Snapshot falsche Stunden bis Anpfiff ([[feedback_injected_now_not_wallclock]]).
    """
    # `snapshot.get("matches") or snapshot` wäre hier falsch: bei einem LEEREN matches-Dict
    # fällt das auf den ganzen Snapshot zurueck und zählt "generatedAt" als Spiel.
    games = snapshot.get("matches") if isinstance(snapshot, dict) and "matches" in snapshot else snapshot
    items = list(games.values()) if isinstance(games, dict) else (games or [])
    ref = now or _parse(snapshot.get("generatedAt")) or _now()
    out = []
    for g in items:
        if not isinstance(g, dict):
            continue
        ko = _parse(g.get("kickoff"))
        hours = round((ko - ref).total_seconds() / 3600.0, 2) if ko else None
        b = bucket_of(hours)
        rungs = C._ou_rungs(g.get("markets") or {})
        fit = C._fit_lambda(rungs) if len(rungs) >= C.MIN_RUNGS else None
        lam = fit[0] if fit else None
        for mk in WATCHED:
            reason, money, dev = gate_for(g, mk, lam)
            out.append({
                "matchId": str(g.get("matchId") or ""), "league": g.get("league"),
                "match": "%s – %s" % (g.get("home"), g.get("away")),
                "market": mk, "hours": hours, "bucket": b, "reason": reason,
                "moneyEur": None if money is None else round(money),
                "dev": None if dev is None else round(dev, 4),
                "seenAt": ref.isoformat(),
            })
    return out


def merge(old_rows, new_rows, now=None, keep_days=KEEP_DAYS, max_rows=MAX_ROWS) -> list:
    """Alt + neu, dedupliziert auf (matchId, markt, bucket). REIN.

    Pro Spiel und Bucket zählt EINE Beobachtung — sonst gewichtet ein Spiel, das zufällig
    zehnmal im selben Fenster gescannt wurde, die Statistik schief.
    """
    ref = now or _now()
    keep = {}
    for r in list(old_rows or []) + list(new_rows or []):
        if not isinstance(r, dict):
            continue
        seen = _parse(r.get("seenAt"))
        if seen and (ref - seen).days > keep_days:
            continue
        k = (r.get("matchId"), r.get("market"), r.get("bucket"))
        prev = keep.get(k)
        if prev is None or str(r.get("seenAt") or "") >= str(prev.get("seenAt") or ""):
            keep[k] = r
    rows = sorted(keep.values(), key=lambda r: str(r.get("seenAt") or ""))
    return rows[-max_rows:]


_ORDER = [lab for _lo, _hi, lab in BUCKETS] + [LIVE_BUCKET]


def summarize(rows) -> dict:
    """Zeilen → Auswertung je Bucket. REIN. Die Zahl, auf die es ankommt: Anteil, der die
    Geld-Hürde nimmt — und davon der Anteil, der auch die Abweichung schafft."""
    per = {}
    for r in (rows or []):
        b = r.get("bucket")
        if not b:
            continue
        d = per.setdefault(b, {"n": 0, "wenig_geld": 0, "geld_ok": 0, "feuert": 0,
                               "wenig_sprossen": 0, "kein_preis": 0, "kein_lambda": 0,
                               "zu_kleine_abweichung": 0})
        d["n"] += 1
        reason = r.get("reason")
        if reason in d:
            d[reason] += 1
        if reason in ("feuert", "zu_kleine_abweichung", "kein_preis") and r.get("moneyEur") is not None:
            d["geld_ok"] += 1
    for d in per.values():
        d["geldQuote"] = round(d["geld_ok"] / d["n"], 3) if d["n"] else None
        d["feuerQuote"] = round(d["feuert"] / d["n"], 3) if d["n"] else None
    return {"byBucket": {b: per[b] for b in _ORDER if b in per},
            "n": sum(d["n"] for d in per.values())}


def main() -> int:
    try:
        snap = json.loads(SNAP_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print("ℹ️  %s gibt es noch nicht — nichts zu beobachten." % SNAP_FILE.name)
        return 0
    except Exception as e:
        # Kaputt ist nicht leer: den alten Stand jetzt zu überschreiben wäre der Datenverlust.
        print("⚠️  %s nicht lesbar (%s) — Beobachtung bleibt unangetastet." % (SNAP_FILE.name, e))
        return 0

    old = {}
    try:
        old = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass
    except Exception as e:
        print("⚠️  %s nicht lesbar (%s) — wird NICHT überschrieben." % (OUT_FILE.name, e))
        return 0

    rows = merge(old.get("rows") or [], observe(snap))
    rep = summarize(rows)
    write_json_atomic(OUT_FILE, {"updatedAt": _now().isoformat(),
                                 "minMoneyEur": C.MIN_MONEY_EUR, "minEdge": C.MIN_EDGE,
                                 "minRungs": C.MIN_RUNGS, "summary": rep, "rows": rows}, indent=1)

    print("🔎 Kohärenz-Beobachter — wann liegt Geld in den Tormärkten?")
    print("   Hürden: %.0f € im Markt · %.0fpp Abweichung · %d Sprossen"
          % (C.MIN_MONEY_EUR, C.MIN_EDGE * 100, C.MIN_RUNGS))
    if not rep["n"]:
        print("   noch keine Beobachtungen.")
        return 0
    print("   %-12s %6s  %10s  %10s" % ("bis Anpfiff", "n", "Geld reicht", "feuert"))
    for b, d in rep["byBucket"].items():
        print("   %-12s %6d  %9.0f%%  %9.0f%%"
              % (b, d["n"], (d["geldQuote"] or 0) * 100, (d["feuerQuote"] or 0) * 100))
    print("💾 %s (%d Beobachtungen)" % (OUT_FILE.name, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
