#!/usr/bin/env python3
"""
steam_engine.py — Lucas' echtes Modell: Pinnacle-Move-Following (14.06.2026).

Kein Fair-Value. Trigger = Pinnacle-Quote ist seit Opening auf einer Seite gefallen
(Sharp Money / Info im Markt). Daraus wird EIN bettbarer Pick je Spiel abgeleitet:
  • mäßiger Drop → gerade Seite (1X2 / O/U / BTTS) zur aktuellen Quote
  • starker Favoriten-Drop (Quote unbettbar kurz, z.B. ESP 1,13→1,09) → Handicap-Linie
    in der 1,5-1,8-Region (ESP -2 @1,60), analog Lucas' Safe-Variant-Logik.

Angezeigt/getrackt wird die SOFTBOOK-Quote, wenn vorhanden (1X2/O25/BTTS), sonst Pini
(AH gibt's nur bei Pini). Pini ist das Benzin (Trigger), Softbook der Preis.

Reines Modul: nur Funktionen auf einem odds_snap-Dict (wie wm["odds"][fixture]). Schreibt
nichts. Die Verdrahtung in generate_wm_picks + das CLV-Log macht der nächste Schritt.

Steam-Schwelle/Sweet-Spot: Backtest 01.06. → 3-5pp bester Bereich, große Moves oft schon
durchgepreist. Defaults entsprechend.
"""
from __future__ import annotations

TRIGGER_PP = 3.0                 # ab hier gilt ein Move als Steam
# Variante A (20.06.2026, Lucas): Quote der gesteamten Seite über diesem Wert = Longshot →
# KEIN Trigger. Auf Außenseitern (z.B. Haiti 51→22 gg. Brasilien) ist der de-vig-pp-Move fast
# nur Favoriten-Festigung + Vig-Umverteilung, kein echtes Sharp-Money. Verhindert Nonsens-Karten
# wie „X2 @7.10 gegen den Must-Win-Favoriten". Mainline-Steam (BTTS @2.08, Favoriten, O/U) bleibt.
MAX_TRIGGER_ODDS = 6.0           # ~<17% implied → drüber ist der Move Rauschen
SWEET = (3.0, 6.0)               # beste Zone; darüber Vorsicht (durchgepreist)
TARGET_ODDS = (1.45, 1.95)       # Ziel-Quotenregion für den abgeleiteten Pick
TARGET_MID = 1.65
STRAIGHT_MIN = 1.40              # darunter ist die gerade Seite unbettbar → Linie ableiten

# 1X2-Seiten: (Quoten-Key, Anzeigename, Seite, AH-Leiter-Präfix für Favoriten-Ableitung)
_SIDES_1X2 = [
    ("hw", "Heimsieg", "home", "ahH_n"),
    ("aw", "Auswärtssieg", "away", "ahA_n"),
]
# O/U + BTTS: (Key, Gegen-Key, Anzeigename, Soft-Key)
_SIDES_OU = [
    ("o15", "u15", "Über 1.5 Tore", "public_o15"),
    ("u15", "o15", "Unter 1.5 Tore", "public_u15"),
    ("o25", "u25", "Über 2.5 Tore", "public_o25"),
    ("u25", "o25", "Unter 2.5 Tore", "public_u25"),
    ("o35", "u35", "Über 3.5 Tore", "public_o35"),
    ("u35", "o35", "Unter 3.5 Tore", "public_u35"),
    ("bttsY", "bttsN", "Beide Teams treffen — Ja", "public_bttsY"),
    ("bttsN", "bttsY", "Beide Teams treffen — Nein", "public_bttsN"),
]
# AH-Leiter: Feld → (Linienwert, Anzeige-Suffix)
# Viertel-Linien (09.07.2026, Lucas): komplette 0.25-Leiter, damit _best_ah bei einem
# unbettbar kurzen Favoriten die IDEALE Cover-Linie in der Zielzone (1.45–1.95) treffen
# kann — z.B. −1.25 wenn −1.0 zu kurz (1.39) und −1.5 zu lang (1.91) ist.
_AH_LADDER = {
    "ahH_n025": (-0.25, "AH Heim −0.25"),
    "ahH_n050": (-0.5, "AH Heim −0.5"), "ahH_n075": (-0.75, "AH Heim −0.75"),
    "ahH_n100": (-1.0, "AH Heim −1"),
    "ahH_n125": (-1.25, "AH Heim −1.25"),
    "ahH_n150": (-1.5, "AH Heim −1.5"),
    "ahH_n175": (-1.75, "AH Heim −1.75"),
    "ahH_n200": (-2.0, "AH Heim −2"),
    "ahH_n225": (-2.25, "AH Heim −2.25"),
    "ahA_n025": (-0.25, "AH Auswärts −0.25"),
    "ahA_n050": (-0.5, "AH Auswärts −0.5"), "ahA_n075": (-0.75, "AH Auswärts −0.75"),
    "ahA_n100": (-1.0, "AH Auswärts −1"),
    "ahA_n125": (-1.25, "AH Auswärts −1.25"),
    "ahA_n150": (-1.5, "AH Auswärts −1.5"),
    "ahA_n175": (-1.75, "AH Auswärts −1.75"),
    "ahA_n200": (-2.0, "AH Auswärts −2"),
    "ahA_n225": (-2.25, "AH Auswärts −2.25"),
}


def _imp(o):
    return (1.0 / o) if (o and o > 1.0) else None


def _plausible_1x2(hw, dr, aw) -> bool:
    """Bildet ein 1X2-Opening einen ECHTEN Markt? (09.07.2026, Lucas: MLS Chicago–Vancouver zeigte
    Opening 1.17/1.01/1.17, Overround 270% → Fake-Steam +25pp → Fake-Pick.) Platzhalter-Openings
    (dr≈1.01, gleiche hw/aw) dürfen keinen Steam-Move auslösen. Gleicher Filter wie fetch_liga_odds:
    kein Outcome <1.05, Remis ≥1.5, Overround plausibel [1.0, 1.30]."""
    if not (hw and dr and aw):
        return False
    if hw < 1.05 or aw < 1.05 or dr < 1.5:
        return False
    return 1.0 <= (1.0 / hw + 1.0 / dr + 1.0 / aw) <= 1.30


def detect_steam(snap: dict, trigger_pp: float = TRIGGER_PP,
                 drift: dict | None = None,
                 max_trigger_odds: float = MAX_TRIGGER_ODDS) -> list[dict]:
    """Alle Seiten mit spielspezifischem Pinnacle-Drop (Opening → jetzt) ≥ trigger_pp.
    drift = markt-weiter Median-Move je Seite; wird abgezogen, damit nur die Bewegung
    ZÄHLT, die ÜBER den Marktschnitt hinausgeht (echtes spielspezifisches Sharp-Money,
    nicht WM-weiter Tor-Markt-Drift). move_pp = bereinigt, move_raw_pp = roh (open→jetzt).
    max_trigger_odds (Variante A): Seiten mit aktueller Quote über diesem Wert (Longshots)
    triggern NICHT — dort ist der pp-Move Rauschen, kein Sharp-Money."""
    op = snap.get("odds_open") or {}
    drift = drift or {}
    out = []

    def _add(key, label, cur, opn, kind, extra=None):
        ci, oi = _imp(cur), _imp(opn)
        if ci is None or oi is None:
            return
        if max_trigger_odds and cur and cur > max_trigger_odds:
            return                              # Longshot → kein Trigger (Variante A)
        move_raw = (ci - oi) * 100.0
        move = move_raw - drift.get(key, 0.0)   # markt-weiten Drift entfernen
        if move < trigger_pp:
            return
        d = {"key": key, "label": label, "cur": cur, "open": opn,
             "move_pp": round(move, 1), "move_raw_pp": round(move_raw, 1),
             "sweet": SWEET[0] <= move <= SWEET[1], "kind": kind}
        if extra:
            d.update(extra)
        out.append(d)

    # 1X2-Move nur nehmen, wenn SOWOHL der aktuelle ALS AUCH der Opening-Satz ein PLAUSIBLER Markt
    # ist. Ein Platzhalter-Satz (Overround ≫ 1.3, dr≈1.01) — egal ob im Opening (MLS Chicago 09.07.:
    # Opening 1.17/1.01/1.17) oder im aktuellen Snap (MLS Nashville 09.07.: jetzt 1.04/1.02/1.04) —
    # würde sonst einen erfundenen Riesen-Move + Fake-Steam-Pick erzeugen. Implausibel → opn=None →
    # kein 1X2-Trigger (Self-Defense unabhängig von der Fetch-Heilung/Reihenfolge). Teil-Sätze (nur
    # eine Seite, wie in echten Snaps/Tests) werden NICHT beurteilt → Altverhalten.
    def _full_ok(d):
        full = bool(d.get("hw") and d.get("dr") and d.get("aw"))
        return (not full) or _plausible_1x2(d.get("hw"), d.get("dr"), d.get("aw"))
    _op_1x2_ok = _full_ok(snap) and _full_ok(op)
    for key, label, side, ah_pref in _SIDES_1X2:
        _opn = op.get(key) if _op_1x2_ok else None
        _add(key, label, snap.get(key), _opn, "1x2", {"side": side, "ah_pref": ah_pref})
    for key, _opp, label, soft_key in _SIDES_OU:
        _add(key, label, snap.get(key), op.get(key), "ou", {"soft_key": soft_key})

    out.sort(key=lambda t: (not t["sweet"], -t["move_pp"]))
    return out


def _best_ah(snap: dict, ah_pref: str):
    """Wählt aus der AH-Leiter die Linie, deren Pini-Quote am nächsten an TARGET_MID liegt
    und in TARGET_ODDS fällt. Fallback: höchste verfügbare Quote unter TARGET[1]."""
    cands = []
    for field, (line, disp) in _AH_LADDER.items():
        if not field.startswith(ah_pref):
            continue
        o = snap.get(field)
        if o and o > 1.0:
            cands.append((o, line, disp))
    if not cands:
        return None
    in_band = [c for c in cands if TARGET_ODDS[0] <= c[0] <= TARGET_ODDS[1]]
    if in_band:
        return min(in_band, key=lambda c: abs(c[0] - TARGET_MID))
    # keine in der Zone → die mit der höchsten Quote (sicherste bettbare Annäherung)
    return max(cands, key=lambda c: c[0])


def derive_pick(trig: dict, snap: dict) -> dict | None:
    """Aus einem Steam-Trigger EINEN bettbaren Pick ableiten. None wenn keine
    bettbare Linie existiert (z.B. Auswärts-Favorit ohne Minus-Leiter)."""
    cur = trig["cur"]
    # Softbook-KONSENS der gesteamten Seite (jetzt + Opening): 1X2 → public_hw/dr/aw,
    # O/U/BTTS → soft_key. Opening (…_open) erlaubt die echte FOLLOW-Bestätigung:
    # ist der Soft-Konsens dem Pinnacle-Move gefolgt? (Median-Konsens, nicht Einzelbuch.)
    if trig["kind"] == "1x2":
        soft_now = snap.get(f"public_{trig['key']}")
        soft_open = snap.get(f"public_{trig['key']}_open")
    else:
        soft_key = trig.get("soft_key")
        soft_now = snap.get(soft_key) if soft_key else None
        soft_open = snap.get(f"{soft_key}_open") if soft_key else None

    # Soft-Follow (Bestätigung): + = Soft-Konsens seit Opening Richtung Pick gelaufen.
    soft_follow = None
    if soft_now and soft_open and soft_now > 1.0 and soft_open > 1.0:
        soft_follow = round((_imp(soft_now) - _imp(soft_open)) * 100, 1)
    soft_confirmed = soft_follow is not None and soft_follow >= 1.5
    # Soft-Lag (Value): + = Soft hinkt der aktuellen Pinnacle-Quote noch hinterher.
    soft_lag = None
    if soft_now and soft_now > 1.0:
        soft_lag = round((_imp(cur) - _imp(soft_now)) * 100, 1)

    # Starker 1X2-Favorit, gerade Seite unbettbar kurz → Handicap ableiten (kein Soft-AH)
    if trig["kind"] == "1x2" and cur < STRAIGHT_MIN:
        ah = _best_ah(snap, trig.get("ah_pref", ""))
        if ah is None:
            return None   # keine Linie → kein Pick (sauber übersprungen)
        odd, line, disp = ah
        return {"market": disp, "ah_line": line, "entry_odd": odd, "book": "pini",
                "derived": True, "trigger": trig, "soft_lagging": None,
                "soft_follow_pp": soft_follow, "soft_confirmed": soft_confirmed,
                "soft_open": None, "soft_now": None}

    # Sonst: gerade Seite. Softbook-Quote bevorzugt (Anzeige/Einstieg), sonst Pini.
    # soft_open/soft_now (17.06.2026): rohe Soft-Konsens-Quoten Opening→jetzt — der Renderer
    # zeichnet daraus den ECHTEN Soft-Streifen (der Pinnacle-Streifen kommt aus dem Trigger).
    entry, book = (soft_now, "soft") if (soft_now and soft_now > 1.0) else (cur, "pini")
    return {"market": trig["label"], "ah_line": None, "entry_odd": round(entry, 3),
            "book": book, "derived": False, "trigger": trig, "soft_lagging": soft_lag,
            "soft_follow_pp": soft_follow, "soft_confirmed": soft_confirmed,
            "soft_open": round(soft_open, 3) if soft_open else None,
            "soft_now": round(soft_now, 3) if soft_now else None}


def _trigger_category(trig: dict) -> str:
    """result (1X2/AH) | totals (O/U) | btts — für Dedup je Card."""
    if trig["kind"] == "1x2":
        return "result"
    if trig["key"].startswith("btts"):
        return "btts"
    return "totals"


_DRIFT_SIDES = ("hw", "dr", "aw", "o15", "u15", "o25", "u25",
                "o35", "u35", "bttsY", "bttsN")


def market_drift(odds: dict, min_samples: int = 5) -> dict:
    """Markt-weiter Median-Move je Seite (Opening→jetzt) über ALLE Fixtures. Wird in
    detect_steam abgezogen → isoliert spielspezifisches Sharp-Money vom WM-weiten Drift
    (z.B. Tor-Markt driftet überall Richtung Under). Nur Seiten mit ≥min_samples zählen."""
    import statistics
    acc = {s: [] for s in _DRIFT_SIDES}
    for o in (odds or {}).values():
        if not isinstance(o, dict):
            continue
        op = o.get("odds_open") or {}
        for s in _DRIFT_SIDES:
            ci, oi = _imp(o.get(s)), _imp(op.get(s))
            if ci is not None and oi is not None:
                acc[s].append((ci - oi) * 100.0)
    return {s: round(statistics.median(v), 2)
            for s, v in acc.items() if len(v) >= min_samples}


# Tor-Linien-Leitern nach STEIGENDER Quote (für Sub-Floor-Promotion).
_OVER_LADDER  = ["o15", "o25", "o35"]   # Über: höhere Linie = höhere Quote
_UNDER_LADDER = ["u35", "u25", "u15"]   # Unter: niedrigere Linie = höhere Quote


def _promote_to_floor(trig, trigs, snap, floor):
    """Sub-Floor Tor-Trigger (z.B. Über 1.5 @1.29) → die nächst-höhere Linie, die AUCH
    getriggert hat (sich bewegt hat) UND deren Quote ≥ floor ist. None, wenn keine solche
    Linie existiert → Pick fällt weg (nichts unter floor zeigen, Lucas 17.06.2026)."""
    key = trig.get("key", "")
    ladder = _OVER_LADDER if key in _OVER_LADDER else (_UNDER_LADDER if key in _UNDER_LADDER else None)
    if not ladder:
        return None
    triggered = {t.get("key") for t in trigs}
    i = ladder.index(key)
    for nk in ladder[i + 1:]:
        if nk not in triggered:
            continue   # diese höhere Linie hat sich NICHT bewegt → nicht hochbiegen
        nt = next((t for t in trigs if t.get("key") == nk), None)
        if nt is None:
            continue
        p = derive_pick(nt, snap)
        if p and p.get("entry_odd", 0) >= floor:
            return p
    return None


def build_steam_picks(snap: dict, *, days_to_ko: float | None = None,
                      trigger_pp: float = TRIGGER_PP, max_picks: int = 3,
                      drift: dict | None = None, min_odds: float = 0.0,
                      max_trigger_odds: float = MAX_TRIGGER_ODDS) -> list[dict]:
    """Bis zu max_picks Steam-Picks je Spiel, dedupliziert nach Kategorie
    (result/totals/btts). Häufiger Fall: Home-Favorit dropt → oft dropt auch das Over
    → beide werden gezeigt. Aber nie 2× dieselbe Kategorie (keine 5 Abwägungen).
    drift = markt-weiter Median-Move (aus market_drift) → spielspezifisch isolieren.
    min_odds (17.06.2026, Lucas): getriggerte Linie unter min_odds (z.B. Über 1.5 @1.29) →
    auf die nächst-höhere Linie hochgehen, die AUCH getriggert hat (≥ min_odds); gibt's keine,
    Pick weglassen (nichts unter min_odds anzeigen)."""
    out, seen = [], set()
    all_trigs = detect_steam(snap, trigger_pp, drift=drift, max_trigger_odds=max_trigger_odds)
    for trig in all_trigs:
        cat = _trigger_category(trig)
        if cat in seen:
            continue
        pick = derive_pick(trig, snap)
        if not pick:
            continue
        # Sub-Floor-Schutz: zu kurze Linie → nächst-höhere getriggerte (≥min_odds) oder weg.
        if min_odds and pick.get("entry_odd", 0) < min_odds:
            promoted = _promote_to_floor(trig, all_trigs, snap, min_odds)
            if promoted is None:
                seen.add(cat)   # Kategorie verbraucht — nichts unter Floor zeigen
                continue
            pick = promoted
        late = (days_to_ko is not None and days_to_ko < 2.0)
        if pick.get("soft_lagging") is not None and pick["soft_lagging"] <= 0.5:
            late = True   # Soft schon konvergiert → Late/no-edge-Hinweis
        pick["lateEntry"] = late
        out.append(pick)
        seen.add(cat)
        if len(out) >= max_picks:
            break
    return out


def build_steam_pick(snap: dict, *, days_to_ko: float | None = None,
                     trigger_pp: float = TRIGGER_PP, drift: dict | None = None) -> dict | None:
    """Stärkster einzelner Steam-Pick (Rückwärtskompatibilität)."""
    picks = build_steam_picks(snap, days_to_ko=days_to_ko, trigger_pp=trigger_pp,
                              max_picks=1, drift=drift)
    return picks[0] if picks else None


def clv_record(snap: dict, pick: dict, fixture_key: str, ts: str) -> dict:
    """Einstiegs-Datensatz fürs CLV-Tracking (open + Einstiegsquote festhalten;
    Closing wird später beim Resolve nachgetragen → CLV = Einstieg vs Closing)."""
    t = pick["trigger"]
    return {
        "fixture": fixture_key, "market": pick["market"], "side_key": t["key"],
        "entry_ts": ts, "entry_odd": pick["entry_odd"], "entry_book": pick["book"],
        "pini_open": t["open"], "pini_at_entry": t["cur"], "move_pp": t["move_pp"],
        "late_entry": pick.get("lateEntry", False), "closing_odd": None, "clv_pp": None,
    }
