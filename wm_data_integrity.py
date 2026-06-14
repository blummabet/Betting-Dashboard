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
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path as _Path

_BASE = _Path(__file__).resolve().parent


def _lazy(fname):
    """Best-effort-Load einer JSON neben diesem Modul (für Guards, die nicht über
    run_checks injiziert werden — z.B. Auto-Bets/Odds-History)."""
    try:
        import json as _json
        p = _BASE / fname
        return _json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}

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
    def __init__(self, wm, poly, schedule, venues, lineups=None, now=None,
                 auto_bets=None, history=None):
        self.wm = wm or {}
        self.poly = poly or {}
        self.schedule = schedule or {}
        self.venues = venues or {}
        self.lineups = lineups or {}
        self.now = now or datetime.now(timezone.utc)
        # Auto-Bets + Odds-History (14.06.2026): injizierbar (Tests) oder lazy von Disk.
        _ab = auto_bets if auto_bets is not None else _lazy("wm_auto_bets_placed.json")
        self.auto_bets = (_ab.get("bets") if isinstance(_ab, dict) else _ab) or []
        self.history = (history if history is not None else _lazy("wm2026-odds-history.json")) or {}
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


_AH_FAV_RE = re.compile(r"AH (?:Heim|Auswärts) −([\d.]+)")


def _ah_fav_line(market):
    """Magnitude einer AH-Favoriten-Linie (−1.5 → 1.5). 0 wenn kein AH-Favorit."""
    m = _AH_FAV_RE.search(market or "")
    return float(m.group(1)) if m else 0.0


@integrity_check
def check_pick_safe_variant(ctx):
    """FIX 14.06.2026: Kein BET-Pick darf eine RISKANTE Variante (AH-Handicap ≤ −1.5
    ODER Quote > 3.0) als Empfehlung haben, ohne dass eine SICHERE Variante angeboten
    wird (saferAltFor/boldAlt). Fing den Bug, den Lucas per Auge fand: Favoriten bekamen
    „AH Heim −1.5 @2.9" als Haupt-Pick statt normalem Sieg, weil die Substitutions-Map
    AH-Linien nicht kannte. Greift universell (auch dynamische Leiter + Auswärts)."""
    picks = ctx.wm.get("picks") or {}
    fails = []
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        for p in plist:
            if p.get("verdict") != "BET":
                continue
            odds = p.get("odds") or 0
            # Steam-Picks leiten die AH-Linie bewusst auf eine sichere Quote ab
            # (build_steam_pick → 1,4-1,95) → die Linien-Höhe ist hier kein Risiko,
            # nur eine Quote > 3,0 zählt. Sonst: AH ≤ −1.5 ODER Quote > 3,0.
            if p.get("source") == "steam":
                risky = odds > 3.0
            else:
                risky = odds > 3.0 or _ah_fav_line(p.get("market")) >= 1.5
            if risky and not p.get("saferAltFor") and not p.get("boldAlt"):
                fails.append(f"{key}: BET {p.get('market')} @{odds} — keine sichere Variante")
    return _chk("pick_safe_variant", "Riskanter BET hat sichere Variante", "warn", fails,
                "AH ≤ −1.5 / Quote > 3.0 als BET-Headline braucht eine sicherere Alternative "
                "(generate_wm_picks: SUBSTITUTION_MAP + _safer_alternatives + Renderer-Demotion).")


# Spiegel von generate_wm_picks: MODEL_MARGIN (0.96) + O/U-Markt → Pinnacle-Linien-Paar.
_MODEL_MARGIN = 0.96
_OU_PINN_PAIR = {
    "Über 1.5 Tore": ("o15", "u15", "o"), "Unter 1.5 Tore": ("o15", "u15", "u"),
    "Über 2.5 Tore": ("o25", "u25", "o"), "Unter 2.5 Tore": ("o25", "u25", "u"),
    "Über 3.5 Tore": ("o35", "u35", "o"), "Unter 3.5 Tore": ("o35", "u35", "u"),
    "Beide Teams treffen — Ja":   ("bttsY", "bttsN", "o"),
    "Beide Teams treffen — Nein": ("bttsY", "bttsN", "u"),
}


@integrity_check
def check_ou_pinnacle_anchored(ctx):
    """FIX 14.06.2026: O/U + BTTS sind seit heute an Pinnacle geankert (wie 1X2 seit
    13.06.) — Baseline P(Über/Unter/BTTS) = de-viggte Pinnacle-Linie, nicht mehr das
    Poisson-Tor-Modell. Sonst schlug das Modell Pinnacle und erzeugte Phantom-Edges
    (DEU-CUW Unter 3.5: Poisson 48 % statt Pinnacle-fair 39 %).
    Tripwire gegen Regression: für JEDES NEU gebaute O/U/BTTS-Pick (Spiel ab übermorgen,
    Pinnacle-Linie vorhanden) muss modelOdds ≈ prob_to_odds(de-vig Pinnacle) sein. Liegt
    es stattdessen beim Poisson-Wert → der Anker wurde versehentlich entfernt.
    AUSGENOMMEN: gepostete Spiele (heute + morgen). Die werden bewusst eingefroren und
    NICHT umgeankert, damit veröffentlichte Picks trackbar bleiben (Lucas 14.06.)."""
    picks = ctx.wm.get("picks") or {}
    # Datum + Pinnacle-Odds je pick_key auflösen.
    date_by_key, odds_by_key = {}, {}
    for _g, fx in ctx.fixtures:
        pk = f"{_g}-{fx.get('matchday')}-{fx.get('home')}-{fx.get('away')}"
        date_by_key[pk] = fx.get("date")
        odds_by_key[pk] = ctx.odds.get(f"{fx.get('home')}-{fx.get('away')}") or {}
    tomorrow = (ctx.now.date() + timedelta(days=1)).isoformat()
    fails = []
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        dt = date_by_key.get(key)
        if not dt or dt <= tomorrow:
            continue   # gepostet/eingefroren → bewusst unangerührt
        osnap = odds_by_key.get(key) or {}
        for p in plist:
            if p.get("verdict") not in ("BET", "ABWÄGEN"):
                continue
            pair = _OU_PINN_PAIR.get(p.get("market"))
            if not pair:
                continue
            ov, un = osnap.get(pair[0]), osnap.get(pair[1])
            if not ov or not un or ov <= 1.0 or un <= 1.0:
                continue   # keine Pinnacle-Linie → Poisson-Fallback erlaubt, nicht prüfbar
            io, iu = 1.0 / ov, 1.0 / un
            fair = (io if pair[2] == "o" else iu) / (io + iu)
            expected = round((1.0 / fair) * _MODEL_MARGIN, 3)
            mo = p.get("modelOdds")
            if not isinstance(mo, (int, float)) or abs(mo - expected) > 0.20:
                fails.append(f"{key}: {p.get('market')} modelOdds={mo} ≠ Pinnacle-Anker "
                             f"{expected} (Poisson-Regression?)")
    return _chk("ou_pinnacle_anchored", "O/U + BTTS an Pinnacle geankert", "warn", fails,
                "generate_wm_picks: _devig2-Block (Z.~930). Baseline = de-viggte Pinnacle, "
                "Poisson nur Fallback. Gepostete Spiele (≤morgen) ausgenommen.")


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


_FINISHED = {"FT", "AET", "PEN"}


@integrity_check
def check_autobet_kickoff_present(ctx):
    """Offene Auto-Bets MÜSSEN eine auflösbare Anpfiffzeit haben (bet.kickoff ODER
    Fixture-Kickoff). Sonst greift der 2h-Pre-Match-Close nicht und der Trade rutscht
    LIVE ins In-Play (QAT-SUI 13.06.2026, −€5.50). GELD-KRITISCH."""
    ko_by_ha = {ctx.mk(fx): fx.get("kickoff") for _g, fx in ctx.fixtures if fx.get("kickoff")}
    fails = []
    for b in ctx.auto_bets:
        is_open = ((b.get("status") or "").lower() == "placed"
                   and not b.get("soldAt") and b.get("result") is None)
        if not is_open:
            continue
        ha = f"{b.get('homeId')}-{b.get('awayId')}"
        if not (b.get("kickoff") or ko_by_ha.get(ha)):
            fails.append(f"{ha} {b.get('market','')}: offener Auto-Bet ohne auflösbaren Kickoff")
    return _chk("autobet_kickoff", "Offene Auto-Bets haben Anpfiffzeit", "error", fails,
                "Ohne Kickoff feuert der 2h-Close nicht → Trade rutscht ins In-Play.")


@integrity_check
def check_resolved_status_propagated(ctx):
    """Ein beendetes Spiel darf keinen Auto-Bet mehr auf status='placed' haben — sonst
    klebt er als '🔴 läuft' in den offenen Positionen (QAT-SUI nach LOSS, 13.06.2026).
    resolve_wm_results muss won/lost/void zurückschreiben."""
    finished_ha = {f"{fx.get('home')}-{fx.get('away')}" for _g, fx in ctx.fixtures
                   if str((fx.get("result") or {}).get("status") or "").upper() in _FINISHED}
    fails = []
    for b in ctx.auto_bets:
        ha = f"{b.get('homeId')}-{b.get('awayId')}"
        if ha in finished_ha and (b.get("status") or "").lower() == "placed":
            fails.append(f"{ha} {b.get('market','')}: Spiel beendet, Auto-Bet noch 'placed'")
    return _chk("resolved_status_propagated", "Beendete Spiele: Auto-Bet-Status aktualisiert", "warn", fails,
                "Sonst hängt die Wette ewig in 'Offene Positionen · Live'.")


@integrity_check
def check_ah_ladder_coverage(ctx):
    """Bepreiste, anstehende Spiele sollten eine ahLadder haben — sonst der AH-'klappt-
    nie'-Bug (ahLadder wurde nie ins gespeicherte Odds-Entry kopiert, 13.06.2026).
    Nur Spiele mit 1X2-Odds + Anpfiff in den nächsten 5 Tagen (kein Rauschen)."""
    fails = []
    horizon = ctx.now + timedelta(days=5)
    for _g, fx in ctx.fixtures:
        mk = ctx.mk(fx)
        od = ctx.odds.get(mk) or {}
        if not od.get("hw"):
            continue
        try:
            dt = datetime.fromisoformat(str(fx.get("kickoff")).replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            continue
        if ctx.now <= dt <= horizon and not od.get("ahLadder"):
            fails.append(f"{mk}: bepreist + Anpfiff nah, aber keine ahLadder")
    return _chk("ah_ladder_coverage", "AH-Leiter bei nahen bepreisten Spielen", "warn", fails,
                "ahLadder fehlte → AH-Picks fielen durchs Raster (Mismatches ohne AH).")


@integrity_check
def check_finished_has_stats(ctx):
    """Beendete Spiele sollten result.stats (echte Match-xG) haben — sonst fehlt dem
    Prozess-Lernen (verdient/Pech) die Datenbasis (14.06.2026)."""
    fails = []
    for _g, fx in ctx.fixtures:
        r = fx.get("result") or {}
        if str(r.get("status") or "").upper() in _FINISHED and not r.get("stats"):
            fails.append(f"{ctx.mk(fx)}: beendet, aber keine result.stats (xG)")
    return _chk("finished_has_stats", "Beendete Spiele haben Match-Stats (xG)", "warn", fails,
                "Ohne Match-xG lernt der Bayesian-Loop nur aus Glück/Pech, nicht aus dem Prozess.")


@integrity_check
def check_soft_book_history(ctx):
    """Die Odds-History muss Soft-Book-Snapshots (bk='public') enthalten — sonst kann
    lead_lag_bias NIE feuern (nur Pinnacle → Sharp-Money-Conviction strukturell tot,
    13.06.2026). Erst ab genug History relevant."""
    hist = ctx.history if isinstance(ctx.history, dict) else {}
    total = sum(len(v) for v in hist.values() if isinstance(v, list))
    if total < 20:
        return None   # zu wenig History für ein Urteil
    public = sum(1 for v in hist.values() if isinstance(v, list)
                 for s in v if isinstance(s, dict) and s.get("bk") == "public")
    fails = []
    if public == 0:
        fails.append(f"0 'public'-Snapshots in {total} History-Einträgen → lead_lag kann nie feuern")
    return _chk("soft_book_history", "Soft-Book-Snapshots in Odds-History", "warn", fails,
                "Ohne Soft-Book-Zeitreihe ist die Sharp-Money-Conviction-Familie tot.")


# ── Runner ───────────────────────────────────────────────────────────────────
def run_checks(wm, poly, schedule, venues, lineups=None, now=None,
               auto_bets=None, history=None):
    """Führt die ganze Registry aus. Pure. Ein crashender Check killt den Rest nicht."""
    ctx = IntegrityCtx(wm, poly, schedule, venues, lineups=lineups, now=now,
                       auto_bets=auto_bets, history=history)
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
