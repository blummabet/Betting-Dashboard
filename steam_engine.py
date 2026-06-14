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
    ("o15", "u15", "Über 1.5 Tore", None),
    ("u15", "o15", "Unter 1.5 Tore", None),
    ("o25", "u25", "Über 2.5 Tore", "public_o25"),
    ("u25", "o25", "Unter 2.5 Tore", "public_u25"),
    ("o35", "u35", "Über 3.5 Tore", None),
    ("u35", "o35", "Unter 3.5 Tore", None),
    ("bttsY", "bttsN", "Beide Teams treffen — Ja", "public_bttsY"),
    ("bttsN", "bttsY", "Beide Teams treffen — Nein", "public_bttsN"),
]
# AH-Leiter: Feld → (Linienwert, Anzeige-Suffix)
_AH_LADDER = {
    "ahH_n050": (-0.5, "AH Heim −0.5"), "ahH_n075": (-0.75, "AH Heim −0.75"),
    "ahH_n100": (-1.0, "AH Heim −1"),   "ahH_n150": (-1.5, "AH Heim −1.5"),
    "ahH_n200": (-2.0, "AH Heim −2"),
    "ahA_n050": (-0.5, "AH Auswärts −0.5"), "ahA_n075": (-0.75, "AH Auswärts −0.75"),
    "ahA_n100": (-1.0, "AH Auswärts −1"),   "ahA_n150": (-1.5, "AH Auswärts −1.5"),
    "ahA_n200": (-2.0, "AH Auswärts −2"),
}


def _imp(o):
    return (1.0 / o) if (o and o > 1.0) else None


def detect_steam(snap: dict, trigger_pp: float = TRIGGER_PP) -> list[dict]:
    """Alle Seiten mit Pinnacle-Drop (Opening → jetzt) ≥ trigger_pp. + = Quote gefallen."""
    op = snap.get("odds_open") or {}
    out = []

    def _add(key, label, cur, opn, kind, extra=None):
        ci, oi = _imp(cur), _imp(opn)
        if ci is None or oi is None:
            return
        move = (ci - oi) * 100.0
        if move < trigger_pp:
            return
        d = {"key": key, "label": label, "cur": cur, "open": opn,
             "move_pp": round(move, 1), "sweet": SWEET[0] <= move <= SWEET[1], "kind": kind}
        if extra:
            d.update(extra)
        out.append(d)

    for key, label, side, ah_pref in _SIDES_1X2:
        _add(key, label, snap.get(key), op.get(key), "1x2", {"side": side, "ah_pref": ah_pref})
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
    # Softbook-Quote der gesteamten Seite: 1X2 → public_hw/dr/aw, O/U/BTTS → soft_key.
    if trig["kind"] == "1x2":
        soft = snap.get(f"public_{trig['key']}")
    else:
        soft_key = trig.get("soft_key")
        soft = snap.get(soft_key) if soft_key else None

    # Starker 1X2-Favorit, gerade Seite unbettbar kurz → Handicap ableiten
    if trig["kind"] == "1x2" and cur < STRAIGHT_MIN:
        ah = _best_ah(snap, trig.get("ah_pref", ""))
        if ah is None:
            return None   # keine Linie → kein Pick (sauber übersprungen)
        odd, line, disp = ah
        return {"market": disp, "ah_line": line, "entry_odd": odd, "book": "pini",
                "derived": True, "trigger": trig, "soft_lagging": None}

    # Sonst: gerade Seite. Softbook-Quote bevorzugt (Anzeige/Einstieg), sonst Pini.
    entry, book = (soft, "soft") if (soft and soft > 1.0) else (cur, "pini")
    soft_lag = None
    if soft and soft > 1.0:
        soft_lag = round((_imp(cur) - _imp(soft)) * 100, 1)  # + = Soft hinkt nach (Value)
    return {"market": trig["label"], "ah_line": None, "entry_odd": round(entry, 3),
            "book": book, "derived": False, "trigger": trig, "soft_lagging": soft_lag}


def _trigger_category(trig: dict) -> str:
    """result (1X2/AH) | totals (O/U) | btts — für Dedup je Card."""
    if trig["kind"] == "1x2":
        return "result"
    if trig["key"].startswith("btts"):
        return "btts"
    return "totals"


def build_steam_picks(snap: dict, *, days_to_ko: float | None = None,
                      trigger_pp: float = TRIGGER_PP, max_picks: int = 3) -> list[dict]:
    """Bis zu max_picks Steam-Picks je Spiel, dedupliziert nach Kategorie
    (result/totals/btts). Häufiger Fall: Home-Favorit dropt → oft dropt auch das Over
    → beide werden gezeigt. Aber nie 2× dieselbe Kategorie (keine 5 Abwägungen)."""
    out, seen = [], set()
    for trig in detect_steam(snap, trigger_pp):
        cat = _trigger_category(trig)
        if cat in seen:
            continue
        pick = derive_pick(trig, snap)
        if not pick:
            continue
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
                     trigger_pp: float = TRIGGER_PP) -> dict | None:
    """Stärkster einzelner Steam-Pick (Rückwärtskompatibilität)."""
    picks = build_steam_picks(snap, days_to_ko=days_to_ko, trigger_pp=trigger_pp, max_picks=1)
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
