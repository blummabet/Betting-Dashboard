#!/usr/bin/env python3
"""
wm_data_integrity.py — Härtung der Daten-Pipeline (erweiterbare Guard-Registry).

Eine Prüf-Batterie über GENAU die Felder, die Picks/Signale/Trades treiben — und
die uns reihenweise wehgetan haben (Venue, Kickoff, Home/Away, Stale-Edge,
Schedule-Datum). Jeder Check liefert ein strukturiertes Ergebnis, das
pre_match_readiness in wm_status.json["checks"] schreibt und die Status-Seite als
benannten Guard mit ✅/🔴 + Fehlerliste rendert.

Leitprinzip: Wenn ein Datenpunkt kippt, auf dem Lucas Geld setzt, MUSS es sichtbar
werden — nicht still weggeguardet.

═══════════════════════════════════════════════════════════════════════════════
  NEUEN GUARD HINZUFÜGEN (wenn wir einen neuen schweren Fehler finden):
  ───────────────────────────────────────────────────────────────────────────
  1. Funktion schreiben, mit @integrity_check dekorieren:

       @integrity_check
       def check_mein_neuer_guard(ctx):
           fails = []
           for gkey, fx in ctx.fixtures:
               if <etwas stimmt nicht>:
                   fails.append(f"{ctx.mk(fx)}: <was genau falsch ist>")
           return _chk("mein_guard", "Lesbares Label", "error", fails,
                       "Warum es zählt / welcher Bug dahinter steckt.")

  2. Fertig. Erscheint automatisch in wm_status.json["checks"] + auf der
     Status-Seite. severity: "error" (geld-kritisch) | "warn" | "info".
     ctx hat: .wm .poly .schedule .venues .fixtures .odds .poly_prices
              .poly_all .venue_ids  + Helfer ctx.mk(fx), ctx.venue_id(v).
     Ein Check der crasht killt die Batterie NICHT (wird als warn gemeldet).
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

# Venue-Name/City-Substring → venue_id (Spiegel von generate_wm_picks._VENUE_NAME_TO_ID).
_VENUE_NAME_TO_ID = {
    "azteca": "mexico_city", "mexico city": "mexico_city", "monterrey": "monterrey",
    "guadalajara": "guadalajara", "akron": "guadalajara", "bbva": "monterrey",
    "rose bowl": "los_angeles", "sofi": "los_angeles", "inglewood": "los_angeles",
    "los angeles": "los_angeles", "at&t": "dallas", "arlington": "dallas", "dallas": "dallas",
    "nrg": "houston", "houston": "houston", "mercedes-benz": "atlanta", "mercedes benz": "atlanta",
    "atlanta": "atlanta", "gillette": "boston", "foxborough": "boston", "boston": "boston",
    "metlife": "new_york", "east rutherford": "new_york", "new york": "new_york", "new jersey": "new_york",
    "lincoln": "philadelphia", "philadelphia": "philadelphia", "levi": "san_francisco",
    "santa clara": "san_francisco", "san francisco": "san_francisco", "lumen": "seattle",
    "seattle": "seattle", "hard rock": "miami", "miami": "miami", "arrowhead": "kansas_city",
    "kansas city": "kansas_city", "bc place": "vancouver", "vancouver": "vancouver",
    "bmo": "toronto", "toronto": "toronto",
}
TOURNEY_START = "2026-06-11"
TOURNEY_END   = "2026-07-20"


def _venue_id(venue):
    if not isinstance(venue, str) or not venue.strip():
        return None
    n = venue.lower()
    for key, vid in _VENUE_NAME_TO_ID.items():
        if key in n:
            return vid
    return None


def _chk(cid, label, severity, failures, note=""):
    failures = list(failures)
    return {"id": cid, "label": label, "severity": severity,
            "ok": len(failures) == 0, "nFail": len(failures),
            "failures": failures[:25], "note": note}


class IntegrityCtx:
    """Geteilter Kontext für alle Checks — einmal gebaut, an jeden Guard gereicht."""
    def __init__(self, wm, poly, schedule, venues, lineups=None, now=None):
        self.wm = wm or {}
        self.poly = poly or {}
        self.schedule = schedule or {}
        self.venues = venues or {}
        self.lineups = lineups or {}
        self.now = now or datetime.now(timezone.utc)
        self.fixtures = [(g, fx) for g, gd in (self.wm.get("groups") or {}).items()
                         for fx in (gd.get("fixtures") or [])]
        self.odds = self.wm.get("odds") or {}
        self.poly_prices = (self.poly.get("prices") if isinstance(self.poly, dict) else {}) or {}
        self.poly_all = (self.poly.get("allFixtures") if isinstance(self.poly, dict) else []) or []
        self.venue_ids = set((self.venues.get("venues") or {}).keys())

    @staticmethod
    def mk(fx):
        return f"{fx.get('home')}-{fx.get('away')}"

    @staticmethod
    def venue_id(v):
        return _venue_id(v)


# ── Registry ────────────────────────────────────────────────────────────────
INTEGRITY_CHECKS = []
def integrity_check(fn):
    INTEGRITY_CHECKS.append(fn)
    return fn


# ── Die Guards (je @integrity_check) ─────────────────────────────────────────
@integrity_check
def check_venue_resolves(ctx):
    fails = []
    for _g, fx in ctx.fixtures:
        vid = ctx.venue_id(fx.get("venue"))
        if vid is None:
            fails.append(f"{ctx.mk(fx)}: Venue '{fx.get('venue')}' → kein venue_id")
        elif vid not in ctx.venue_ids:
            fails.append(f"{ctx.mk(fx)}: venue_id '{vid}' fehlt in wm_venues.json")
    return _chk("venue_resolves", "Venue → venue_id auflösbar", "error", fails,
                "Treibt travel_burden/altitude/weather. Fallback = falsche Signale.")


@integrity_check
def check_venue_matches_schedule(ctx):
    if not ctx.schedule:
        return None
    fails = []
    for _g, fx in ctx.fixtures:
        s = ctx.schedule.get(ctx.mk(fx))
        if s and s.get("venue") and fx.get("venue") != s["venue"]:
            fails.append(f"{ctx.mk(fx)}: '{fx.get('venue')}' ≠ Schedule '{s['venue']}'")
    return _chk("venue_matches_schedule", "Venue == API-Football-Schedule", "error", fails,
                "Seed-Venues waren reihenweise falsch (KOR-CZE SoFi statt Guadalajara).")


@integrity_check
def check_kickoff_present(ctx):
    fails = []
    for _g, fx in ctx.fixtures:
        ko = fx.get("kickoff")
        if not ko:
            fails.append(f"{ctx.mk(fx)}: kein kickoff (Platzhalter {fx.get('date')} {fx.get('time')})")
            continue
        try:
            dt = datetime.fromisoformat(str(ko).replace("Z", "+00:00")).astimezone(timezone.utc)
            d10 = dt.strftime("%Y-%m-%d")
            if not (TOURNEY_START <= d10 <= TOURNEY_END):
                fails.append(f"{ctx.mk(fx)}: kickoff {d10} außerhalb Turnier-Fenster")
        except Exception:
            fails.append(f"{ctx.mk(fx)}: kickoff '{ko}' nicht parsebar")
    return _chk("kickoff_present", "Kickoff-Zeit real + plausibel", "error", fails,
                "00:00-Platzhalter führten zu falschem Betting-Tab-Listing.")


@integrity_check
def check_time_matches_kickoff(ctx):
    fails = []
    for _g, fx in ctx.fixtures:
        ko = fx.get("kickoff")
        if not ko:
            continue   # fehlender kickoff fängt check_kickoff_present ab
        try:
            v = (datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
                 + timedelta(hours=2)).strftime("%H:%M")   # Wien CEST (WM-Fenster Juni/Juli)
        except Exception:
            continue   # unparsebarer kickoff ebenfalls bei check_kickoff_present
        t = fx.get("time")
        if t != v:
            fails.append(f"{ctx.mk(fx)}: time={t} ≠ Wien(kickoff) {v}")
    return _chk("time_matches_kickoff", "Anpfiff-Zeit (time) == Wien(kickoff)", "warn", fails,
                "fx.time war Seed-Müll (mal Wien, mal Venue-Local, mal 00:00-Platzhalter — "
                "65/72 falsch). Anzeige leitet aus kickoff ab; Drift hier = Quelle "
                "(fetch_wm_venues/fetch_wm_poly_prices) hat time nicht normalisiert.")


def _real_match_keys(ctx):
    return {ctx.mk(fx) for _g, fx in ctx.fixtures}


@integrity_check
def check_odds_sane(ctx):
    real = _real_match_keys(ctx)
    fails = []
    for mk, o in ctx.odds.items():
        if mk not in real:
            continue   # Phantom-Keys separat (check_no_phantom_odds)
        hw, dr, aw = o.get("hw"), o.get("dr"), o.get("aw")
        if not all(isinstance(x, (int, float)) and x > 1.0 for x in (hw, dr, aw)):
            fails.append(f"{mk}: 1X2 unvollständig hw={hw} dr={dr} aw={aw}")
            continue
        margin = 1/hw + 1/dr + 1/aw
        if margin < 1.0 or margin > 1.30:
            fails.append(f"{mk}: Margin {margin:.3f} unplausibel")
    return _chk("odds_sane", "Pinnacle-1X2 vollständig + plausibel", "warn", fails,
                "Quelle für Modell-Baseline + Edge.")


@integrity_check
def check_homeaway_consistent(ctx):
    fails = []
    for mk, o in ctx.odds.items():
        hw, aw = o.get("hw"), o.get("aw")
        pj = ctx.poly_prices.get(mk) or {}
        phw, paw = pj.get("hw"), pj.get("aw")
        if not all(isinstance(x, (int, float)) and x > 1.0 for x in (hw, aw, phw, paw)):
            continue
        if abs(hw - aw) > 0.3 and (hw < aw) != (phw > paw):
            fails.append(f"{mk}: Pinnacle-Fav {'Heim' if hw < aw else 'Ausw'} ≠ "
                         f"Poly-Fav {'Heim' if phw > paw else 'Ausw'} (Swap-Verdacht)")
    return _chk("homeaway_consistent", "Home/Away nicht vertauscht (Pinn vs Poly)", "error", fails,
                "fetch_wm_odds:241 hatte hw↔aw-Swap → Mexiko als Underdog gelistet.")


@integrity_check
def check_edge_consistent(ctx):
    fails = []
    for fx in ctx.poly_all:
        for m in ("hw", "dr", "aw", "o25", "u25"):
            fair, pol, ed = fx.get(f"fair_{m}"), fx.get(f"poly_{m}"), fx.get(f"edge_{m}")
            if not all(isinstance(v, (int, float)) for v in (fair, pol, ed)):
                continue
            live = round((fair - pol) * 100, 1)
            if abs(live - ed) > 0.5:
                fails.append(f"{fx.get('homeId')}-{fx.get('awayId')} {m}: edge {ed:+.1f} ≠ live {live:+.1f}")
    return _chk("edge_consistent", "Edge == fair − poly (kein Stale-Edge)", "error", fails,
                "Stale edge_aw=-1.4 vs live +7.1 hat einen echten Trade blockiert.")


@integrity_check
def check_schedule_date(ctx):
    fails = []
    seed = {ctx.mk(fx): (fx.get("date") or "")[:10] for _g, fx in ctx.fixtures}
    for mk, od in ctx.poly_prices.items():
        pd = (od.get("date") or "")[:10]
        sd = seed.get(mk)
        if pd and sd and pd != sd:
            fails.append(f"{mk}: Seed {sd} ≠ Poly {pd}")
    return _chk("schedule_date", "Spielplan-Datum == Polymarket", "error", fails,
                "Seed war ~1 Tag verschoben → Picks am falschen Tag.")


@integrity_check
def check_lineup_present(ctx):
    from datetime import timedelta
    horizon = ctx.now + timedelta(minutes=90)
    fails = []
    for _g, fx in ctx.fixtures:
        ko = None
        if fx.get("kickoff"):
            try:
                ko = datetime.fromisoformat(str(fx["kickoff"]).replace("Z", "+00:00"))
            except Exception:
                ko = None
        if ko is None or not (ctx.now <= ko <= horizon):
            continue   # nur Spiele die in <90min anpfeifen
        ent = ctx.lineups.get(ctx.mk(fx))
        starting = ((ent or {}).get("home") or {}).get("starting") or []
        if not ent or not starting:
            mins = int((ko - ctx.now).total_seconds() / 60)
            fails.append(f"{ctx.mk(fx)}: Anpfiff in {mins}min, KEINE Aufstellung")
    return _chk("lineup_present", "Aufstellung da vor Anpfiff (T-90min)", "warn", fails,
                "lineup_signal braucht die Startelf. War leer wegen Namens-Match + Wien-Zeit-Bug.")


@integrity_check
def check_public_consensus(ctx):
    real = _real_match_keys(ctx)
    fails = [f"{mk}: kein public_hw" for mk, o in ctx.odds.items()
             if mk in real and not o.get("public_hw")]
    return _chk("public_consensus", "Public-Konsens (Soft-Books) vorhanden", "warn", fails,
                "Ohne public_* feuert public_static_bias nicht.")


@integrity_check
def check_public_is_multibook(ctx):
    """FIX 12.06.2026: public_* soll der MEDIAN-KONSENS (fetch_wm_multibook_odds,
    'Konsens (N Books)') sein, nicht der alte verrauschte Einzel-Soft-Book
    (williamhill/bet365 aus fetch_wm_odds). check_public_consensus prüft nur ob
    public_hw DA ist → blind dafür, ob der Konsens wirklich aktiv ist. Dieser
    Check flaggt Fixtures, deren public_* noch vom Einzel-Book stammt (= Multibook-
    Step hat nicht geschrieben, z.B. APIF /odds leer oder Step-Fail)."""
    real = _real_match_keys(ctx)
    fails = []
    for mk, o in ctx.odds.items():
        if mk not in real or not o.get("public_hw"):
            continue
        bk = str(o.get("public_bookmaker") or "")
        if not bk.lower().startswith("konsens"):
            fails.append(f"{mk}: public aus Einzel-Book '{bk or '?'}' statt Konsens")
    return _chk("public_is_multibook", "Public = Multi-Book-Konsens (nicht Einzel-Book)",
                "warn", fails,
                "public_static_bias soll auf Median-Konsens laufen, nicht 1 verrauschtem "
                "Soft-Book. Single-Book = fetch_wm_multibook_odds hat (noch) nicht geschrieben.")


@integrity_check
def check_no_phantom_odds(ctx):
    """Odds-Keys, die KEINEM echten Fixture entsprechen — meist verkehrte
    Heim/Auswärts-Reihenfolge (SUI-CAN statt CAN-SUI), leer. Daten-Hygiene:
    so ein Phantom-Key kann bei Reverse-Lookups falsch matchen."""
    real = _real_match_keys(ctx)
    fails = [f"{mk}: kein echtes Fixture (Spiegel-Key?)" for mk in ctx.odds if mk not in real]
    return _chk("no_phantom_odds", "Keine Phantom-Odds-Keys (verkehrte Reihenfolge)", "warn", fails,
                "84 Odds-Keys vs 72 Fixtures = 12 leere Spiegel-Einträge. Quelle prüfen.")


@integrity_check
def check_result_score_final(ctx):
    """result.home_score darf NUR gesetzt sein, wenn das Spiel beendet ist
    (FT/AET/PEN). Sonst ist ein Live-Zwischenstand gespeichert, den das
    Dashboard als „Endstand" rendert (USA-PRY 1H 2:0 vs echtem 4:1, 13.06.2026)."""
    finished = {"FT", "AET", "PEN"}
    fails = []
    for _g, fx in ctx.fixtures:
        r = fx.get("result") or {}
        st = str(r.get("status") or "").upper()
        if r.get("home_score") is not None and st not in finished:
            fails.append(f"{ctx.mk(fx)}: Score {r.get('home_score')}:{r.get('away_score')} "
                         f"bei Status {st or '—'} (nicht beendet)")
    return _chk("result_score_final", "Endstand nur bei beendetem Spiel", "error", fails,
                "Live-Zwischenstand im result → wird als Endstand gerendert.")


# ── Runner ───────────────────────────────────────────────────────────────────
def run_checks(wm, poly, schedule, venues, lineups=None, now=None):
    """Führt die ganze Registry aus. Pure. Ein crashender Check killt den Rest nicht."""
    ctx = IntegrityCtx(wm, poly, schedule, venues, lineups=lineups, now=now)
    out = []
    for fn in INTEGRITY_CHECKS:
        try:
            r = fn(ctx)
            if r:
                out.append(r)
        except Exception as e:
            out.append(_chk(fn.__name__, fn.__name__, "warn",
                            [f"Check-Code-Fehler: {e}"], "Guard selbst gecrasht — bitte prüfen."))
    return out


if __name__ == "__main__":
    import json
    from pathlib import Path
    B = Path(__file__).resolve().parent
    load = lambda f: json.loads((B / f).read_text(encoding="utf-8")) if (B / f).exists() else {}
    res = run_checks(load("wm2026-data.json"), load("wm_poly_prices.json"),
                     load("wm_venue_schedule.json"), load("wm_venues.json"))
    nfail = sum(1 for c in res if not c["ok"])
    print(f"=== Daten-Integrität: {len(res)-nfail}/{len(res)} Checks ok ({len(INTEGRITY_CHECKS)} Guards registriert) ===\n")
    for c in res:
        icon = "✅" if c["ok"] else ("🔴" if c["severity"] == "error" else "🟡")
        print(f"{icon} [{c['severity']}] {c['label']}: {c['nFail']} Fehler")
        for f in c["failures"][:6]:
            print(f"     · {f}")
