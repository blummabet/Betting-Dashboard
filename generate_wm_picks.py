#!/usr/bin/env python3
"""
generate_wm_picks.py — WM 2026 Match Pick Generator.

Liest aus wm2026-data.json:
  · groups   — Fixtures + Teams inkl. Elo-Ratings
  · odds     — Marktquoten von TheOddsAPI (hw/dr/aw/o25/u25/bttsY + odds_open)
  · form     — Letzte 15 Spiele pro Team (avgScored, avgConceded, last5 etc.)
  · h2h      — Kopf-an-Kopf pro Fixture-Paar

Pick-Logik (3 Signale — Port von pick-verdict.js computeVerdict()):
  Signal 1 — Model Edge:   Elo-Modell odds vs Marktquoten (edge in pp)
  Signal 2 — Line Movement: Opening vs. aktuelle Quote
  Signal 3 — H2H Story:    Historische Trefferquote für den Markt

Märkte:
  Heimsieg / Unentschieden / Auswärtssieg     (1X2, wenn Edge ≥ 4pp)
  Über 2.5 Tore / Unter 2.5 Tore             (Poisson, wenn Edge ≥ 4pp)
  Beide Teams treffen — Ja                    (Poisson, wenn Edge ≥ 4pp)
  DNB Heim / DNB Auswärts                    (abgeleitet, wenn Edge ≥ 5pp)

Picks werden eingefroren sobald ein Spiel gestartet hat.
Schreibt wm2026-data.json["picks"].

Run:   python3 generate_wm_picks.py [--verbose]
Cron:  Täglich via fetch-wm-data.yml (nach fetch_wm_form.py)
"""

import json, math, sys
from datetime import datetime, timezone
from pathlib import Path

BASE    = Path(__file__).parent
WM_FILE = BASE / "wm2026-data.json"
VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

# ── Modell-Parameter ──────────────────────────────────────────────────────
# Internationaler Durchschnitt Tore pro Team pro Spiel (WM-Gruppenphase ~2.5 gesamt)
INTL_AVG_GOALS = 1.25   # pro Team/Spiel

# WM-spezifische Draw-Baseline (historisch ~22-24% im Turnier)
DRAW_BASE      = 0.24
DRAW_MAX       = 0.30
DRAW_MIN       = 0.10

# Margin auf Modellquoten (~4% = zwischen Pinnacle 3% und Softbook)
MODEL_MARGIN   = 0.96

# Co-Gastgeber Heimvorteil (neutrales Gelände, aber Heimkurve)
CO_HOSTS       = {"MEX", "USA", "CAN"}
HOME_BONUS_PP  = 0.03   # +3pp auf Heimsieg-Wahrscheinlichkeit

# Edge-Schwellen
EDGE_MIN_1X2   = 4    # Minimum pp für 1X2-Picks
EDGE_MIN_OU    = 4    # Minimum pp für Over/Under + BTTS
EDGE_MIN_DNB   = 5    # Minimum pp für DNB (braucht mehr Edge, da abgeleitet)
EDGE_HIGH      = 10   # ≥10pp → high confidence
EDGE_MED       = 6    # ≥6pp  → medium confidence


# ═══════════════════════════════════════════════════════════════════════════
#  ELO-MODELL → Wahrscheinlichkeiten
# ═══════════════════════════════════════════════════════════════════════════

def elo_probabilities(elo_h: float, elo_a: float, home_is_cohost: bool) -> dict:
    """
    Konvertiert Elo-Ratings in Win/Draw/Loss-Wahrscheinlichkeiten.

    Basis: Standard Elo-Expected-Score P = 1/(1 + 10^(-diff/400))
    Draw-Anteil: kalibriert für Länderspiele (sinkt mit größerer Elo-Differenz)
    """
    diff       = elo_h - elo_a
    p_expected = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))   # P(Heim gewinnt)

    if home_is_cohost:
        p_expected = min(0.93, p_expected + HOME_BONUS_PP)

    # Draw-Wahrscheinlichkeit: sinkt bei großer Differenz
    abs_diff = abs(diff)
    p_draw   = DRAW_BASE * max(0.35, 1.0 - abs_diff / 600.0)
    p_draw   = max(DRAW_MIN, min(DRAW_MAX, p_draw))

    # Nicht-Unentschieden aufteilen
    p_no_draw = 1.0 - p_draw
    p_home    = p_expected * p_no_draw
    p_away    = (1.0 - p_expected) * p_no_draw

    # Normalisieren
    total = p_home + p_draw + p_away
    return {
        "pH": p_home / total,
        "pD": p_draw / total,
        "pA": p_away / total,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  EXPECTED GOALS (Dixon-Coles-Stil)
# ═══════════════════════════════════════════════════════════════════════════

def expected_goals(form_h: dict, form_a: dict) -> tuple[float, float]:
    """
    λ_heim, λ_ausw aus Form-Daten.
    Normalisiert auf INTL_AVG_GOALS als Basis.
    Wenn keine Form-Daten: Basis-λ verwenden.
    """
    def rate(form: dict) -> tuple[float, float]:
        if not form or form.get("games", 0) < 3:
            return 1.0, 1.0
        scored   = form.get("avgScored",   INTL_AVG_GOALS)
        conceded = form.get("avgConceded", INTL_AVG_GOALS)
        att = max(0.35, min(3.0, scored   / INTL_AVG_GOALS))
        def_ = max(0.35, min(3.0, conceded / INTL_AVG_GOALS))
        return att, def_

    h_att, h_def = rate(form_h)
    a_att, a_def = rate(form_a)

    lam_h = INTL_AVG_GOALS * h_att * a_def   # Heimangriff vs Auswärtsabwehr
    lam_a = INTL_AVG_GOALS * a_att * h_def   # Auswärtsangriff vs Heimabwehr

    return (
        max(0.25, min(4.0, lam_h)),
        max(0.25, min(4.0, lam_a)),
    )


# ═══════════════════════════════════════════════════════════════════════════
#  POISSON
# ═══════════════════════════════════════════════════════════════════════════

def _pmf(lam: float, k: int) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def poisson_over(lam: float, threshold: float) -> float:
    """P(X > threshold) mit Halbzeit-Line (z.B. 2.5 → P(X >= 3))."""
    k   = int(threshold)
    cdf = sum(_pmf(lam, i) for i in range(k + 1))
    return max(0.01, min(0.99, 1.0 - cdf))

def p_btts(lam_h: float, lam_a: float) -> float:
    """P(beide Teams treffen mindestens 1 Mal)."""
    return max(0.01, min(0.99,
        (1.0 - math.exp(-lam_h)) * (1.0 - math.exp(-lam_a))
    ))


# ═══════════════════════════════════════════════════════════════════════════
#  QUOTEN-HILFEN
# ═══════════════════════════════════════════════════════════════════════════

def prob_to_odds(prob: float) -> float | None:
    if prob <= 0:
        return None
    return round((1.0 / prob) * MODEL_MARGIN, 3)

def derive_dnb(ph: float, pd: float, pa: float) -> tuple[float | None, float | None]:
    """
    DNB (Draw No Bet) Quoten aus devigged 1X2-Wahrscheinlichkeiten.
    DNB-Heim: P(Heim) / (P(Heim) + P(Ausw))
    """
    denom = ph + pa
    if denom <= 0:
        return None, None
    return prob_to_odds(ph / denom), prob_to_odds(pa / denom)

def devig_1x2(hw: float, dr: float, aw: float) -> tuple[float, float, float]:
    """Devigged Wahrscheinlichkeiten aus Marktquoten."""
    tot = 1/hw + 1/dr + 1/aw
    return (1/hw)/tot, (1/dr)/tot, (1/aw)/tot


# ═══════════════════════════════════════════════════════════════════════════
#  3-SIGNAL VERDICT — Python-Port von pick-verdict.js computeVerdict()
# ═══════════════════════════════════════════════════════════════════════════

def compute_verdict(model_odds: float | None, market_odds: float | None,
                    odds_open:  float | None, h2h: dict | None,
                    mkey: str) -> dict:
    """
    Exakter Port der JS-Logik in pick-verdict.js.

    model_odds  — Modell-Fair-Value (mit Margin)
    market_odds — aktuelle Buchmacher-Quote
    odds_open   — Eröffnungsquote für diesen Markt
    h2h         — { games, homeWins, draws, awayWins, over25Rate, bttsRate }
    mkey        — 'home'|'draw'|'away'|'over25'|'under25'|'btts'|'dnbH'|'dnbA'
    """
    # ── Signal 1: Model Edge ──────────────────────────────────────────────
    mod_sig  = 0
    edge_pp  = 0
    if model_odds and market_odds and model_odds > 1 and market_odds > 1:
        edge_pp = round((1/model_odds - (1/market_odds) * 1.03) * 100)
        if   edge_pp >= 7:  mod_sig =  1
        elif edge_pp >= 0:  mod_sig =  0
        elif edge_pp >= -4: mod_sig = -1
        else:               mod_sig = -1

    # ── Signal 2: Line Movement ───────────────────────────────────────────
    mkt_sig = 0
    if odds_open and market_odds and odds_open > 1 and market_odds > 1:
        pp_d = round(((1/market_odds) - (1/odds_open)) * 100)
        if abs(pp_d) >= 2:
            mkt_sig = 1 if market_odds < odds_open else -1

    # ── Signal 3: H2H Story ───────────────────────────────────────────────
    story_sig = 0
    if h2h and h2h.get("games", 0) >= 3:
        n  = h2h["games"]
        hw = h2h.get("homeWins", 0)
        dw = h2h.get("draws",    0)
        aw = h2h.get("awayWins", 0)
        rate = thresh = None

        if   mkey == "home":    rate, thresh = hw / n, 0.45
        elif mkey == "draw":    rate, thresh = dw / n, 0.28
        elif mkey == "away":    rate, thresh = aw / n, 0.40
        elif mkey == "dnbH":    rate, thresh = (hw + dw) / n, 0.55
        elif mkey == "dnbA":    rate, thresh = (aw + dw) / n, 0.55
        elif mkey == "over25":  rate, thresh = h2h.get("over25Rate", 0.5), 0.50
        elif mkey == "under25": rate, thresh = 1 - h2h.get("over25Rate", 0.5), 0.50
        elif mkey == "btts":    rate, thresh = h2h.get("bttsRate",   0.4), 0.45

        if rate is not None:
            if   rate >= thresh + 0.10: story_sig =  1
            elif rate >= thresh - 0.10: story_sig =  0
            else:                       story_sig = -1

    # ── Finale Entscheidung (exakt wie JS) ───────────────────────────────
    score     = mod_sig + mkt_sig + story_sig
    hard_skip = mod_sig == -1 and mkt_sig == -1

    if hard_skip or score <= -1:
        verdict = "SKIP"
    elif score >= 2 or (score == 1 and mod_sig == 1):
        verdict = "BET"
    else:
        verdict = "ABWÄGEN"

    return {
        "modSig":   mod_sig,
        "mktSig":   mkt_sig,
        "storySig": story_sig,
        "verdict":  verdict,
        "edgePP":   edge_pp,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  KONFIDENZ
# ═══════════════════════════════════════════════════════════════════════════

def edge_to_conf(edge_pp: int, verdict: str) -> str:
    if verdict == "BET":
        if edge_pp >= EDGE_HIGH: return "high"
        if edge_pp >= EDGE_MED:  return "medium"
        return "low"
    return "medium"


# ═══════════════════════════════════════════════════════════════════════════
#  INFO-ZEILE
# ═══════════════════════════════════════════════════════════════════════════

def build_info(elo_diff: int, form_h: dict, form_a: dict,
               h2h: dict | None, mkey: str,
               lam_h: float, lam_a: float) -> str:
    parts = []

    # Elo
    if elo_diff:
        sign = "+" if elo_diff > 0 else ""
        parts.append(f"Elo {sign}{elo_diff}")

    # Form (letzte 5)
    f5h = "".join(form_h.get("last5", []))
    f5a = "".join(form_a.get("last5", []))
    if f5h or f5a:
        parts.append(f"Form {f5h or '?'}·{f5a or '?'}")

    # H2H
    if h2h and h2h.get("games", 0) >= 3:
        n = h2h["games"]
        if   mkey == "home":
            parts.append(f"H2H {round(h2h.get('homeWins',0)/n*100)}% H")
        elif mkey == "draw":
            parts.append(f"H2H {round(h2h.get('draws',0)/n*100)}% X")
        elif mkey == "away":
            parts.append(f"H2H {round(h2h.get('awayWins',0)/n*100)}% A")
        elif mkey in ("over25", "under25"):
            parts.append(f"H2H {round(h2h.get('over25Rate',0)*100)}% Ü2.5")
        elif mkey == "btts":
            parts.append(f"H2H {round(h2h.get('bttsRate',0)*100)}% BTTS")
        elif mkey in ("dnbH", "dnbA"):
            parts.append(f"H2H {round(h2h.get('homeWins',0)/n*100)}% H")

    # xG
    parts.append(f"xG {lam_h:.1f}:{lam_a:.1f}")

    return " · ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
#  PICK-GENERATOR FÜR EIN FIXTURE
# ═══════════════════════════════════════════════════════════════════════════

MARKET_CFG = [
    # (key, label, min_edge)
    ("home",    "Heimsieg",                   EDGE_MIN_1X2),
    ("draw",    "Unentschieden",              EDGE_MIN_1X2),
    ("away",    "Auswärtssieg",               EDGE_MIN_1X2),
    ("dnbH",    "DNB: Heimteam",              EDGE_MIN_DNB),
    ("dnbA",    "DNB: Auswärtsteam",          EDGE_MIN_DNB),
    ("over25",  "Über 2.5 Tore",              EDGE_MIN_OU),
    ("under25", "Unter 2.5 Tore",             EDGE_MIN_OU),
    ("btts",    "Beide Teams treffen — Ja",   EDGE_MIN_OU),
]


def generate_picks_for_fixture(
    fx: dict, gdata: dict,
    mkt: dict, form: dict, h2h_data: dict,
    today_iso: str,
) -> list[dict]:
    """Generiert Picks für ein einzelnes Fixture. Gibt [] zurück wenn kein Pick."""

    # Kickoff-Check: kein Pick für vergangene/heutige Spiele (wird in main gehandhabt)
    teams    = {t["id"]: t for t in gdata.get("teams", [])}
    home_t   = teams.get(fx["home"], {})
    away_t   = teams.get(fx["away"], {})
    elo_h    = home_t.get("elo")
    elo_a    = away_t.get("elo")

    if not elo_h or not elo_a:
        print(f"  ⚠️  Keine Elo für {fx['home']}/{fx['away']}")
        return []

    elo_diff    = round(elo_h - elo_a)
    home_cohost = fx["home"] in CO_HOSTS
    probs       = elo_probabilities(elo_h, elo_a, home_cohost)

    form_h  = form.get(fx["home"], {})
    form_a  = form.get(fx["away"], {})
    h2h_key = f"{fx['home']}-{fx['away']}"
    h2h     = h2h_data.get(h2h_key) or {}

    lam_h, lam_a = expected_goals(form_h, form_a)

    # Marktquoten aus TheOddsAPI
    odds_snap = mkt.get(f"{fx['home']}-{fx['away']}", {})
    open_snap = odds_snap.get("odds_open", {})

    bk_hw = odds_snap.get("hw")
    bk_dr = odds_snap.get("dr")
    bk_aw = odds_snap.get("aw")

    # DNB aus devigged 1X2 ableiten (wenn Marktquoten vorhanden)
    bk_dnb_h = bk_dnb_a = None
    if bk_hw and bk_dr and bk_aw:
        ph_mkt, pd_mkt, pa_mkt = devig_1x2(bk_hw, bk_dr, bk_aw)
        denom = ph_mkt + pa_mkt
        if denom > 0:
            bk_dnb_h = round((1 / (ph_mkt / denom)) * 0.97, 2)
            bk_dnb_a = round((1 / (pa_mkt / denom)) * 0.97, 2)

    # Marktquoten je Market-Key
    market_odds: dict[str, float | None] = {
        "home":    bk_hw,
        "draw":    bk_dr,
        "away":    bk_aw,
        "over25":  odds_snap.get("o25"),
        "under25": odds_snap.get("u25"),
        "btts":    odds_snap.get("bttsY"),
        "dnbH":    bk_dnb_h,
        "dnbA":    bk_dnb_a,
    }

    # Eröffnungsquoten
    open_odds: dict[str, float | None] = {
        "home":    open_snap.get("hw"),
        "draw":    open_snap.get("dr"),
        "away":    open_snap.get("aw"),
        "over25":  open_snap.get("o25"),
        "under25": open_snap.get("u25"),
        "btts":    open_snap.get("bttsY"),
        "dnbH":    open_snap.get("dnbH"),
        "dnbA":    open_snap.get("dnbA"),
    }

    # Modell-Quoten (Elo + Poisson)
    lam_total = lam_h + lam_a
    p_over    = poisson_over(lam_total, 2.5)
    p_under   = 1.0 - p_over
    p_b       = p_btts(lam_h, lam_a)
    dnb_h_mod, dnb_a_mod = derive_dnb(probs["pH"], probs["pD"], probs["pA"])

    model_odds: dict[str, float | None] = {
        "home":    prob_to_odds(probs["pH"]),
        "draw":    prob_to_odds(probs["pD"]),
        "away":    prob_to_odds(probs["pA"]),
        "over25":  prob_to_odds(p_over),
        "under25": prob_to_odds(p_under),
        "btts":    prob_to_odds(p_b),
        "dnbH":    dnb_h_mod,
        "dnbA":    dnb_a_mod,
    }

    picks = []
    for mkey, label, min_edge in MARKET_CFG:
        m_odds  = model_odds.get(mkey)
        bk      = market_odds.get(mkey)
        op      = open_odds.get(mkey)

        # Ohne Marktquoten kein Pick (kein Edge-Vergleich möglich)
        if not m_odds or not bk:
            continue

        v = compute_verdict(m_odds, bk, op, h2h if h2h.get("games", 0) >= 3 else None, mkey)

        # Nur NICHT-SKIP Picks mit ausreichend Edge
        if v["verdict"] == "SKIP":
            continue
        if v["edgePP"] < min_edge:
            continue

        conf = edge_to_conf(v["edgePP"], v["verdict"])
        info = build_info(elo_diff, form_h, form_a, h2h or None, mkey, lam_h, lam_a)

        picks.append({
            "market":    label,
            "odds":      round(bk, 2),
            "modelOdds": m_odds,
            "conf":      conf,
            "verdict":   v["verdict"],
            "modSig":    v["modSig"],
            "mktSig":    v["mktSig"],
            "storySig":  v["storySig"],
            "edgePP":    v["edgePP"],
            "info":      info,
            "icon":      "🎯",
            "result":    None,
        })

    return picks


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=== generate_wm_picks.py ===\n")

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    groups   = wm.get("groups",   {})
    mkt      = wm.get("odds",     {})
    form     = wm.get("form",     {})
    h2h_data = wm.get("h2h",      {})
    wm.setdefault("picks", {})

    today = datetime.now(timezone.utc).date().isoformat()

    total_with_picks = 0
    total_no_picks   = 0
    total_frozen     = 0
    total_past       = 0

    wm.setdefault("upsetScores", {})

    for gkey, gdata in groups.items():
        teams_map = {t["id"]: t for t in gdata.get("teams", [])}

        for fx in gdata.get("fixtures", []):
            pick_key = f"{gkey}-{fx['matchday']}-{fx['home']}-{fx['away']}"
            fx_date  = fx["date"]

            # Upset Score für jedes Fixture berechnen (immer, auch ohne Picks)
            elo_h = teams_map.get(fx["home"], {}).get("elo")
            elo_a = teams_map.get(fx["away"], {}).get("elo")
            if elo_h and elo_a:
                gap = abs(elo_h - elo_a)
                us  = (9 if gap < 50 else 7 if gap < 100 else 6 if gap < 150
                       else 4 if gap < 200 else 2 if gap < 300 else 1)
                wm["upsetScores"][pick_key] = us

            # Vergangene Spiele — eingefroren
            if fx_date < today:
                total_past += 1
                continue

            # Heutige Spiele — eingefroren wenn Picks schon vorhanden
            if fx_date == today:
                if wm["picks"].get(pick_key):
                    total_frozen += 1
                    continue
                # Noch keine Picks für heute → generieren (Spiel noch nicht gestartet)

            new_picks = generate_picks_for_fixture(fx, gdata, mkt, form, h2h_data, today)

            if new_picks:
                wm["picks"][pick_key] = new_picks
                total_with_picks += 1
                print(f"  ✅ {fx['home']} vs {fx['away']} (ST{fx['matchday']}, {fx_date}): "
                      f"{len(new_picks)} Pick(s)")
                if VERBOSE:
                    for p in new_picks:
                        edge = p.get("edgePP", "?")
                        print(f"     [{p['verdict']:8s}] {p['market']:35s} "
                              f"@ {p['odds']:.2f}  edge +{edge}pp  conf={p['conf']}")
            else:
                total_no_picks += 1
                if VERBOSE:
                    print(f"  ○  {fx['home']} vs {fx['away']} (ST{fx['matchday']}): "
                          f"kein Pick (kein Markt oder Edge < Schwelle)")

    print(f"\n[Picks] {total_with_picks} Fixtures mit Picks · "
          f"{total_no_picks} ohne Picks · "
          f"{total_frozen} eingefroren · "
          f"{total_past} vergangen")

    wm["_meta"] = wm.get("_meta", {})
    wm["_meta"]["picksUpdatedAt"] = datetime.now(timezone.utc).isoformat()

    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    print("✅ wm2026-data.json gespeichert.")


if __name__ == "__main__":
    main()
