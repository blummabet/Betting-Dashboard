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

import json, math, os, sys
from datetime import datetime, timezone
from pathlib import Path

BASE    = Path(__file__).parent
WM_FILE = BASE / "wm2026-data.json"
VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

# ── Modell-Parameter ──────────────────────────────────────────────────────
# ── Refactor 2026-06-06: Konstanten aus cocobet_config.json (Profile-aware) ──
# Backwards-compatible: wenn cocobet_config fehlt, greift der Fallback-Default
# pro Konstante — Output bleibt identisch zur Pre-Refactor-Version.
try:
    from cocobet_config import CONFIG as _CFG
except Exception:
    _CFG = {}

def _cfg(section: str, key: str, default):
    """Sicherer Config-Lookup mit Default-Fallback."""
    if isinstance(_CFG, dict):
        return _CFG.get(section, {}).get(key, default)
    return default

# Internationaler Durchschnitt Tore pro Team pro Spiel (WM-Gruppenphase ~2.5 gesamt)
INTL_AVG_GOALS = 1.25   # pro Team/Spiel — Naturkonstante, nicht in Config

# Draw-Baseline (historisch ~22-24% in Länderspielen)
DRAW_BASE      = 0.24
DRAW_MAX       = 0.30
DRAW_MIN       = 0.10

# Margin auf Modellquoten (~4% = zwischen Pinnacle 3% und Softbook)
MODEL_MARGIN   = 0.96

# Co-Gastgeber Heimvorteil (WM-spezifisch — neutrales Gelände, aber Heimkurve)
CO_HOSTS       = {"MEX", "USA", "CAN"}
HOME_BONUS_PP  = 0.03   # +3pp auf Heimsieg-Wahrscheinlichkeit

# Edge-Schwellen (aus Config — siehe cocobet_config.json profiles.<active>.edge)
EDGE_MIN_1X2     = _cfg("edge", "min_1x2_for_pick",        5)
EDGE_MIN_OU      = _cfg("edge", "min_ou_for_pick",         4)
EDGE_MIN_DNB     = _cfg("edge", "min_dnb_for_pick",        6)
EDGE_MIN_DC      = _cfg("edge", "min_dc_for_pick",         4)
EDGE_MIN_AH      = _cfg("edge", "min_ah_for_pick",         4)
EDGE_BET_1X2     = _cfg("edge", "bet_threshold_1x2",       8)
EDGE_BET_OU      = _cfg("edge", "bet_threshold_ou",        6)
EDGE_HIGH        = 10   # confidence-Tier — UI-Indicator, kein Risk-Knopf
EDGE_MED         = 6
EDGE_MAX_SANE    = _cfg("edge", "max_edge_sane",          18)
EDGE_OU_BET_MAX  = _cfg("edge", "ou_bet_max",             10)
EDGE_AH_BET_MAX  = _cfg("edge", "ah_bet_max",             12)
ODDS_MAX         = _cfg("odds", "max_for_pick",          6.5)
ODDS_BET_MAX     = _cfg("odds", "max_for_bet",           4.5)
ODDS_BET_MAX_OU  = _cfg("odds", "max_for_bet_ou",        3.0)
ODDS_BET_MAX_DNB = _cfg("odds", "max_for_bet_dnb",       4.0)

# Underdog-Filter
UNDERDOG_ELO_SOFT = _cfg("underdog", "elo_soft_threshold", 100)
UNDERDOG_ELO_HARD = _cfg("underdog", "elo_hard_threshold", 200)

# Deaktivierte Märkte (Backtest 07.06.2026 — Skellam-Modell verliert systematisch
# auf BTTS −15% ROI bei n=141, hohe Corner-Linien −65% bei n=10).
# Bis das Modell überarbeitet ist, generieren wir keine Picks für diese Märkte.
# Re-enable: Eintrag aus cocobet_config.json profiles.wm2026.disabled_markets entfernen.
def _get_disabled_markets():
    # cocobet_config._resolve_active_profile() merged nur DEFAULT_FALLBACK-Sections,
    # daher zusätzlich-Sections wie disabled_markets verschwinden. Wir lesen die
    # rohe JSON direkt für diese Liste.
    try:
        import os, json
        from pathlib import Path
        raw = json.loads((Path(__file__).parent / "cocobet_config.json").read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        return set(raw["profiles"].get(active, {}).get("disabled_markets") or [])
    except Exception:
        return set()
DISABLED_MARKETS = _get_disabled_markets()


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

def travel_factor(team_id: str, matchday: int, travel_data: dict) -> tuple[float, str]:
    """
    Berechnet xG-Discount basierend auf Anreise für DIESEN Spieltag.

    Returns (factor, label):
      factor:  Multiplikator auf λ (Angriffsstärke). 0.85-1.0.
      label:   Kurzbeschreibung für Story/Logging ("3942km · 4d rest" o.ä.)

    Discount-Skala (basiert auf Sportwissenschafts-Studien zu Long-Haul-Travel
    bei Fußball-Nationalteams: -5% bis -15% xG in den ersten 90 Min):
      - critical (≥ 3000km UND rest ≤ 3 Tage):       factor 0.85 (-15%)
      - high     (≥ 3000km ODER rest ≤ 3 Tage):     factor 0.90 (-10%)
      - medium   (≥ 1500km):                         factor 0.95 (-5%)
      - low/none: 1.0
    Plus +5% Penalty wenn alt_shift ≥ 1500m (Höhenwechsel).
    """
    if not travel_data:
        return 1.0, ""
    tb = travel_data.get(team_id, {})
    if not tb or not tb.get("legs"):
        return 1.0, ""

    leg = next((l for l in tb["legs"] if l.get("matchday_to") == matchday), None)
    if not leg or leg.get("same_venue"):
        return 1.0, ""

    km        = leg.get("km", 0) or 0
    rest_days = leg.get("rest_days", 99) or 99
    alt_shift = abs(leg.get("alt_shift", 0) or 0)
    burden    = (leg.get("burden", "") or "").lower()

    # Basis-Discount aus burden-Label (vorberechnet von compute_wm_travel_burden.py)
    if burden == "critical":
        factor = 0.85
    elif burden == "high":
        factor = 0.90
    elif burden == "medium":
        factor = 0.95
    else:
        # Fallback: km/rest_days selbst beurteilen
        if km >= 3000 and rest_days <= 3:   factor = 0.85
        elif km >= 3000 or rest_days <= 3:  factor = 0.90
        elif km >= 1500:                    factor = 0.95
        else:                               factor = 1.0

    # Höhen-Penalty zusätzlich (Mexico City 2200m etc.)
    if alt_shift >= 1500:
        factor = max(0.80, factor - 0.03)

    label = f"{km}km/{rest_days}d"
    if alt_shift >= 1500:
        label += f"/+{alt_shift}m"
    return factor, label


def expected_goals(form_h: dict, form_a: dict,
                   xg_h: dict = None, xg_a: dict = None,
                   injury_factor_h: float = 1.0,
                   injury_factor_a: float = 1.0,
                   travel_factor_h: float = 1.0,
                   travel_factor_a: float = 1.0) -> tuple[float, float]:
    """
    λ_heim, λ_ausw für Poisson-Modell.

    AUDIT-FIX 05.06.2026 — 3 kritische Bugs gefixt:
      M1) xG-Mindestspiele 3 → 8. Bei nur 6 xG-Spielen (z.B. SUI) wurden Werte
          akzeptiert die massiv von form (15 Spiele) abwichen → Modell-Output
          unzuverlässig. Beispiel CAN-SUI: lam_total=1.47 → Modell sagt 98.7%
          Unter 3.5 → +12pp Edge artifiziell.
      M2) Konsistente Quelle für BEIDE Teams. Vorher: ein Team form, anderes xG
          → asymmetrische Stärke-Bewertung. Jetzt: wenn xG nur für ein Team
          verfügbar → fallback auf form für beide.
      M3) lam_total Sanity-Bounds: WM-Spiele liegen historisch zwischen 2.0
          und 4.0 expected goals. Cap auf [1.8, 4.2] verhindert Extremwerte.

    Datenpriorität (nach Fix):
      1. xgStats wenn BEIDE Teams ≥ 8 Spiele haben
      2. Form avgScored/avgConceded für beide Teams (letzten 15 Spiele)
      3. INTL_AVG_GOALS als Fallback (asymmetrisch markiert)
    """
    XG_MIN_GAMES   = 8   # M1: vorher 3
    FORM_MIN_GAMES = 3

    def rate_from_form(form: dict) -> tuple[float, float] | None:
        if form and form.get("games", 0) >= FORM_MIN_GAMES and form.get("avgScored") is not None:
            scored   = form.get("avgScored",   INTL_AVG_GOALS)
            conceded = form.get("avgConceded", INTL_AVG_GOALS)
            return (
                max(0.35, min(3.0, scored   / INTL_AVG_GOALS)),
                max(0.35, min(3.0, conceded / INTL_AVG_GOALS)),
            )
        return None

    def rate_from_xg(xg: dict) -> tuple[float, float] | None:
        if xg and xg.get("games", 0) >= XG_MIN_GAMES:
            scored   = xg.get("xgForAvg",     INTL_AVG_GOALS)
            conceded = xg.get("xgAgainstAvg",  INTL_AVG_GOALS)
            return (
                max(0.35, min(3.0, scored   / INTL_AVG_GOALS)),
                max(0.35, min(3.0, conceded / INTL_AVG_GOALS)),
            )
        return None

    # M2: Konsistente Quelle — beide xG ODER beide form. Kein Mix.
    h_xg = rate_from_xg(xg_h)
    a_xg = rate_from_xg(xg_a)
    if h_xg and a_xg:
        h_att, h_def = h_xg
        a_att, a_def = a_xg
    else:
        # Fallback: form für beide
        h_form = rate_from_form(form_h)
        a_form = rate_from_form(form_a)
        if h_form and a_form:
            h_att, h_def = h_form
            a_att, a_def = a_form
        elif h_form:
            h_att, h_def = h_form
            a_att, a_def = 1.0, 1.0   # neutral (INTL_AVG_GOALS)
        elif a_form:
            a_att, a_def = a_form
            h_att, h_def = 1.0, 1.0
        else:
            h_att, h_def = 1.0, 1.0
            a_att, a_def = 1.0, 1.0

    # Travel + Injury werden als unabhängige Multiplier auf die Angriffsstärke angewandt
    lam_h = INTL_AVG_GOALS * h_att * a_def * injury_factor_h * travel_factor_h
    lam_a = INTL_AVG_GOALS * a_att * h_def * injury_factor_a * travel_factor_a

    # M3: lam_total Sanity-Bounds für WM-Kontext (2-4 Tore historisch)
    lam_h = max(0.50, min(3.5, lam_h))
    lam_a = max(0.50, min(3.5, lam_a))
    total = lam_h + lam_a
    if total < 1.8:
        # Skalieren um auf min 1.8 zu kommen — proportional anheben
        factor = 1.8 / total
        lam_h *= factor
        lam_a *= factor
    elif total > 4.2:
        # Skalieren um auf max 4.2 zu reduzieren
        factor = 4.2 / total
        lam_h *= factor
        lam_a *= factor

    return (lam_h, lam_a)


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


def derive_dc(ph: float, pd: float, pa: float) -> tuple[float | None, float | None, float | None]:
    """
    Doppelte Chance (DC) Modell-Quoten aus devigged 1X2.
    Liefert (dc1X, dc12, dcX2):
      • 1X = Heim oder Remis     → P = ph + pd
      • 12 = Heim oder Auswärts  → P = ph + pa
      • X2 = Remis oder Auswärts → P = pd + pa
    Margin-Abschlag 3% (typisch für Bookies bei DC-Märkten).
    Sicheres Pick-Format: niedrigere Quoten = höhere Hit-Rate-Erwartung.
    """
    if not (ph and pd and pa):
        return None, None, None
    dc1x = (ph + pd) * 0.97   # 3% Margin-Discount
    dc12 = (ph + pa) * 0.97
    dcx2 = (pd + pa) * 0.97
    return (prob_to_odds(dc1x), prob_to_odds(dc12), prob_to_odds(dcx2))

def devig_1x2(hw: float, dr: float, aw: float) -> tuple[float, float, float]:
    """Devigged Wahrscheinlichkeiten aus Marktquoten."""
    tot = 1/hw + 1/dr + 1/aw
    return (1/hw)/tot, (1/dr)/tot, (1/aw)/tot


def compute_public_bias(odds_snap: dict) -> dict | None:
    """
    Vergleicht Sharp (Pinnacle) vs Public (bet365) implied probability.

    Returns:
        None wenn Public-Daten fehlen
        {
            "hw": +X (pp),   # positiv = Public überbettet Heimsieg
            "dr": +X,
            "aw": +X,
            "max_abs": X,    # absoluter Max-Bias über alle 3 Outcomes
            "max_outcome": "hw" | "dr" | "aw",
            "max_direction": "over" | "under",   # Public über- oder unter-bettet
            "public_bk": str,
        }
    """
    # Sharp: Pinnacle aus den Standard-Feldern
    s_hw, s_dr, s_aw = odds_snap.get("hw"), odds_snap.get("dr"), odds_snap.get("aw")
    p_hw, p_dr, p_aw = odds_snap.get("public_hw"), odds_snap.get("public_dr"), odds_snap.get("public_aw")
    if not all([s_hw, s_dr, s_aw, p_hw, p_dr, p_aw]):
        return None

    sharp = devig_1x2(s_hw, s_dr, s_aw)
    public = devig_1x2(p_hw, p_dr, p_aw)

    # Public - Sharp in pp (positiv = Public sieht höhere Wahrscheinlichkeit)
    diff_hw = round((public[0] - sharp[0]) * 100, 1)
    diff_dr = round((public[1] - sharp[1]) * 100, 1)
    diff_aw = round((public[2] - sharp[2]) * 100, 1)

    diffs = {"hw": diff_hw, "dr": diff_dr, "aw": diff_aw}
    max_oc = max(diffs, key=lambda k: abs(diffs[k]))
    max_val = diffs[max_oc]

    return {
        "hw": diff_hw, "dr": diff_dr, "aw": diff_aw,
        "max_abs": round(abs(max_val), 1),
        "max_outcome": max_oc,
        "max_direction": "over" if max_val > 0 else "under",
        "public_bk": odds_snap.get("public_bookmaker", "?"),
    }


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
        # model_odds enthält MODEL_MARGIN: model_odds = MODEL_MARGIN / p
        # → 1/model_odds = p / MODEL_MARGIN → * MODEL_MARGIN gibt rohes p zurück
        # Markt: * 1.03 ≈ devig für Pinnacle (~3% Vig)
        model_prob  = (1.0 / model_odds) * MODEL_MARGIN
        market_prob = (1.0 / market_odds) * 1.03
        edge_pp = round((model_prob - market_prob) * 100)
        if   edge_pp >= 7:  mod_sig =  1
        elif edge_pp >= 0:  mod_sig =  0
        elif edge_pp >= -4: mod_sig = -1
        else:               mod_sig = -1

    # ── Signal 2: Pinnacle Line Movement (CLV-Proxy) ─────────────────────
    # Positive clv_pp = Quote kürzer geworden = Markt glaubt mehr daran = Sharp Money bestätigt
    mkt_sig = 0
    clv_pp  = 0.0
    if odds_open and market_odds and odds_open > 1 and market_odds > 1:
        clv_pp = round(((1/market_odds) - (1/odds_open)) * 100, 1)
        if   clv_pp >= 5:   mkt_sig =  2   # Starke Bestätigung durch Sharp Money
        elif clv_pp >= 2:   mkt_sig =  1   # Moderate Bestätigung
        elif clv_pp >= -2:  mkt_sig =  0   # Neutrale Bewegung
        elif clv_pp >= -5:  mkt_sig = -1   # Bewegung gegen Pick-Richtung
        else:               mkt_sig = -2   # Starke Bewegung gegen Pick

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

    # ── Finale Entscheidung — exakter Port von pick-verdict.js computeVerdict() ──
    # WICHTIG: Logik muss 1:1 mit pick-verdict.js übereinstimmen (Single Source of Truth).
    score     = mod_sig + mkt_sig + story_sig
    # Hard skip: Modell UND Markt zeigen stark gegen Pick
    hard_skip = mod_sig <= -1 and mkt_sig <= -1

    # JS: if (_hardSkip || _score <= -1) → SKIP
    # JS: else if (_score >= 2 || (_score === 1 && modSig === 1)) → BET
    # JS: else → ABWÄGEN
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
        "clvPP":    clv_pp,
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
               lam_h: float, lam_a: float,
               travel_h: tuple = None, travel_a: tuple = None,
               home_flag: str = "", away_flag: str = "",
               pub_bias: dict = None) -> str:
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

    # Travel-Anreise (nur wenn signifikant — Discount aktiv)
    if travel_h and travel_h[0] < 1.0:
        parts.append(f"✈️ {home_flag or 'H'} {travel_h[1]} ({int((1-travel_h[0])*100)}%-xG)")
    if travel_a and travel_a[0] < 1.0:
        parts.append(f"✈️ {away_flag or 'A'} {travel_a[1]} ({int((1-travel_a[0])*100)}%-xG)")

    # Public-vs-Sharp Bias (nur wenn signifikant ≥4pp)
    if pub_bias and pub_bias.get("max_abs", 0) >= 4:
        oc_de = {"hw":"HW","dr":"X","aw":"AW"}.get(pub_bias["max_outcome"], pub_bias["max_outcome"])
        sign = "+" if pub_bias["max_direction"] == "over" else "-"
        parts.append(f"💸 Public {sign}{pub_bias['max_abs']}pp {oc_de}")

    return " · ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
#  PICK-GENERATOR FÜR EIN FIXTURE
# ═══════════════════════════════════════════════════════════════════════════

MARKET_CFG = [
    # (key, label, min_edge)
    ("home",      "Heimsieg",                   EDGE_MIN_1X2),
    ("draw",      "Unentschieden",              EDGE_MIN_1X2),
    ("away",      "Auswärtssieg",               EDGE_MIN_1X2),
    ("dnbH",      "DNB: Heimteam",              EDGE_MIN_DNB),
    ("dnbA",      "DNB: Auswärtsteam",          EDGE_MIN_DNB),
    # ── Doppelte Chance (sicherer Markt — höhere Hit-Rate-Erwartung) ──
    ("dc1X",      "Doppelte Chance — 1X",       EDGE_MIN_DC),
    ("dc12",      "Doppelte Chance — 12",       EDGE_MIN_DC),
    ("dcX2",      "Doppelte Chance — X2",       EDGE_MIN_DC),
    # ── Tor-Märkte ──
    ("over15",    "Über 1.5 Tore",              EDGE_MIN_OU),
    ("over25",    "Über 2.5 Tore",              EDGE_MIN_OU),
    ("over35",    "Über 3.5 Tore",              EDGE_MIN_OU),
    ("under15",   "Unter 1.5 Tore",             EDGE_MIN_OU),
    ("under25",   "Unter 2.5 Tore",             EDGE_MIN_OU),
    ("under35",   "Unter 3.5 Tore",             EDGE_MIN_OU),
    ("btts",      "Beide Teams treffen — Ja",   EDGE_MIN_OU),
    # ── Asian Handicap (sicherer Markt für Underdogs) ──
    ("ahH_n050",  "AH Heim −0.5",               EDGE_MIN_AH),
    ("ahA_p050",  "AH Auswärts +0.5",           EDGE_MIN_AH),
    ("ahH_n075",  "AH Heim −0.75",              EDGE_MIN_AH),
    ("ahA_p075",  "AH Auswärts +0.75",          EDGE_MIN_AH),
    ("ahH_n100",  "AH Heim −1.0",               EDGE_MIN_AH),
    ("ahA_p100",  "AH Auswärts +1.0",           EDGE_MIN_AH),
    # ── Corner-Picks (Pinnacle listet 1-3 Tage vor Anpfiff) ──
    ("o_corners85",  "Über 8.5 Ecken",          EDGE_MIN_OU),
    ("o_corners95",  "Über 9.5 Ecken",          EDGE_MIN_OU),
    ("o_corners105", "Über 10.5 Ecken",         EDGE_MIN_OU),
]


def expected_corners(home_id: str, away_id: str, corners_form: dict) -> tuple[float, float, float] | None:
    """
    Schätzt erwartete Eckball-Anzahl basierend auf Form-Daten.
    Liefert (home_corners, away_corners, total) oder None wenn Daten unvollständig.

    Mathematik:
      home_corners ≈ (home.forAvg + away.againstAvg) / 2
      away_corners ≈ (away.forAvg + home.againstAvg) / 2
      → Mittelt das Angriffs-Volumen mit der Defense-Anfälligkeit des Gegners
    """
    h = (corners_form or {}).get(home_id) or {}
    a = (corners_form or {}).get(away_id) or {}
    # Min-Games Schwelle: 5 Spiele beidseitig sonst unzuverlässig
    if h.get("games", 0) < 5 or a.get("games", 0) < 5:
        return None
    h_for  = h.get("forAvg")
    h_ag   = h.get("againstAvg")
    a_for  = a.get("forAvg")
    a_ag   = a.get("againstAvg")
    if not all(isinstance(x, (int, float)) for x in (h_for, h_ag, a_for, a_ag)):
        return None
    home_c = (h_for + a_ag) / 2
    away_c = (a_for + h_ag) / 2
    total  = home_c + away_c
    return (home_c, away_c, total)


def poisson_over_int(lam: float, threshold: float) -> float:
    """
    Wahrscheinlichkeit dass eine Poisson-Variable mit Erwartungswert lam
    STRIKT größer als threshold (typisch X.5) ist.
    Direkt einsetzbar für Corner-Märkte: P(Corners > 8.5).
    """
    if lam <= 0:
        return 0.0
    import math
    cutoff = int(threshold)   # 8.5 → cutoff=8: sum P(0..8), then 1 - sum
    p_le_cutoff = 0.0
    log_lam = math.log(lam) if lam > 0 else 0
    log_fact = 0.0
    p_k = math.exp(-lam)   # k=0
    p_le_cutoff += p_k
    for k in range(1, cutoff + 1):
        # P(k) = P(k-1) * lam / k
        p_k = p_k * lam / k
        p_le_cutoff += p_k
    return max(0.0, min(1.0, 1.0 - p_le_cutoff))


def injury_discount(team_id: str, injuries: dict) -> float:
    """
    Gibt einen Multiplikator für die Angriffsstärke zurück.
    1.0 = kein Ausfall, 0.85 = Schlüsselangreifer fehlt.
    """
    inj_data = injuries.get(team_id, {})
    if not inj_data or not inj_data.get("players"):
        return 1.0
    # Nur Angreifer / offensive Positionen reduzieren Lambda
    attacking_positions = {"ST", "CF", "FW", "LW", "RW", "CAM", "AM", "10", "SS"}
    for p in inj_data["players"]:
        # Wenn Verletzungstyp "Injury" oder "Suspension" und kein Positionsfilter nötig
        # → immer reduzieren da wir nur Key-Player tracken
        return 0.85   # 15% Abschlag bei jedem geloggten Ausfall
    return 1.0


def generate_picks_for_fixture(
    fx: dict, gdata: dict,
    mkt: dict, form: dict, h2h_data: dict,
    today_iso: str,
    xg_stats: dict = None,
    injuries: dict = None,
    travel_data: dict = None,
    corners_form: dict = None,
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

    # xgStats bevorzugen wenn verfügbar (echte API-Football xG > Toraverage)
    xg_h = (xg_stats or {}).get(fx["home"])
    xg_a = (xg_stats or {}).get(fx["away"])

    # Injury-Discount für Angriffsstärke
    inj = injuries or {}
    inj_h = injury_discount(fx["home"], inj)
    inj_a = injury_discount(fx["away"], inj)
    if inj_h < 1.0 and VERBOSE:
        print(f"  ⚠️  Injury-Discount {fx['home']}: {inj_h:.0%}")
    if inj_a < 1.0 and VERBOSE:
        print(f"  ⚠️  Injury-Discount {fx['away']}: {inj_a:.0%}")

    # Travel-Discount für Angriffsstärke (Anreise zu DIESEM Spieltag)
    trv_h, trv_h_lbl = travel_factor(fx["home"], fx["matchday"], travel_data)
    trv_a, trv_a_lbl = travel_factor(fx["away"], fx["matchday"], travel_data)
    if trv_h < 1.0 and VERBOSE:
        print(f"  ✈️  Travel-Discount {fx['home']}: {trv_h:.0%} ({trv_h_lbl})")
    if trv_a < 1.0 and VERBOSE:
        print(f"  ✈️  Travel-Discount {fx['away']}: {trv_a:.0%} ({trv_a_lbl})")

    lam_h, lam_a = expected_goals(form_h, form_a, xg_h, xg_a, inj_h, inj_a, trv_h, trv_a)

    # Marktquoten aus TheOddsAPI
    odds_snap = mkt.get(f"{fx['home']}-{fx['away']}", {})
    open_snap = odds_snap.get("odds_open", {})

    bk_hw = odds_snap.get("hw")
    bk_dr = odds_snap.get("dr")
    bk_aw = odds_snap.get("aw")

    # Public-vs-Sharp Bias (Pinnacle vs bet365) — wenn beide Bookies verfügbar
    pub_bias = compute_public_bias(odds_snap)
    if pub_bias and pub_bias["max_abs"] >= 4 and VERBOSE:
        oc_de = {"hw":"Heimsieg","dr":"Unentsch.","aw":"Auswärts"}[pub_bias["max_outcome"]]
        dir_de = "ÜBER-bettet" if pub_bias["max_direction"] == "over" else "UNTER-bettet"
        print(f"  💸 Public-Bias {pub_bias['public_bk']}: {oc_de} {dir_de} um {pub_bias['max_abs']}pp")

    # DNB aus devigged 1X2 ableiten (wenn Marktquoten vorhanden)
    bk_dnb_h = bk_dnb_a = None
    if bk_hw and bk_dr and bk_aw:
        ph_mkt, pd_mkt, pa_mkt = devig_1x2(bk_hw, bk_dr, bk_aw)
        denom = ph_mkt + pa_mkt
        if denom > 0:
            bk_dnb_h = round((1 / (ph_mkt / denom)) * 0.97, 2)
            bk_dnb_a = round((1 / (pa_mkt / denom)) * 0.97, 2)

    # ── Data Quality Assessment ───────────────────────────────────────────
    # Bug-Fix 05.06.2026: Vorher OR → reichte wenn EIN Team Form-Daten hatte,
    # dann wurde "elo+form" gelabelt obwohl der GEGNER unbekannt war.
    # Beispiel: CAN hat 15 Games Form, BIH hat 0 → Label "elo+form" → BET-Picks
    # mit künstlichen +14pp Edges weil Modell BIH-Default-Werte vs CAN-Live-Form
    # gegenüberstellt. Jetzt: BEIDE Teams müssen Mindest-Form haben.
    form_games_h = (form_h or {}).get("games", 0)
    form_games_a = (form_a or {}).get("games", 0)
    h2h_games    = (h2h or {}).get("games", 0)
    odds_present = bool(bk_hw and bk_dr and bk_aw)
    has_h_form   = (form_h or {}).get("avgScored") is not None and form_games_h >= 3
    has_a_form   = (form_a or {}).get("avgScored") is not None and form_games_a >= 3

    if form_games_h >= 5 and form_games_a >= 5 and odds_present and h2h_games >= 3 \
            and (form_h or {}).get("avgScored") is not None \
            and (form_a or {}).get("avgScored") is not None:
        data_quality = "full"       # Elo + Form (beide) + H2H + Odds
    elif has_h_form and has_a_form:
        data_quality = "elo+form"   # Elo + Form für BEIDE Teams
    elif has_h_form or has_a_form:
        # Asymmetrisch — höhere Edge-Schwelle nötig, kennzeichnen
        data_quality = "elo+form_asym"
    else:
        data_quality = "elo_only"   # Nur Elo, sehr unsicher

    # ── Corner-Erwartung (fließt in Markt-Quoten o_corners* ein) ─────
    corners_exp  = expected_corners(fx["home"], fx["away"], corners_form or {})

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
        # Doppelte Chance (gespeichert in fetch_wm_odds.py)
        "dc1X":    odds_snap.get("dc1X"),
        "dc12":    odds_snap.get("dc12"),
        "dcX2":    odds_snap.get("dcX2"),
        # Über/Unter weitere Linien
        "over15":  odds_snap.get("o15"),
        "over35":  odds_snap.get("o35"),
        "under15": odds_snap.get("u15"),
        "under35": odds_snap.get("u35"),
        # Asian Handicap (Heim = negative Linie für Favorit, Auswärts = positive für Underdog)
        "ahH_n050": odds_snap.get("ahH_n050"),
        "ahA_p050": odds_snap.get("ahA_p050"),
        "ahH_n075": odds_snap.get("ahH_n075"),
        "ahA_p075": odds_snap.get("ahA_p075"),
        "ahH_n100": odds_snap.get("ahH_n100"),
        "ahA_p100": odds_snap.get("ahA_p100"),
        # Corner-Markets
        "o_corners85":  odds_snap.get("cOver") if odds_snap.get("cornerLine") == 8.5  else None,
        "o_corners95":  odds_snap.get("cOver") if odds_snap.get("cornerLine") == 9.5  else None,
        "o_corners105": odds_snap.get("cOver") if odds_snap.get("cornerLine") == 10.5 else None,
    }

    # Eröffnungsquoten (für CLV/Drift-Tracking)
    open_odds: dict[str, float | None] = {
        "home":    open_snap.get("hw"),
        "draw":    open_snap.get("dr"),
        "away":    open_snap.get("aw"),
        "over25":  open_snap.get("o25"),
        "under25": open_snap.get("u25"),
        "btts":    open_snap.get("bttsY"),
        "dnbH":    open_snap.get("dnbH"),
        "dnbA":    open_snap.get("dnbA"),
        "dc1X":    open_snap.get("dc1X"),
        "dc12":    open_snap.get("dc12"),
        "dcX2":    open_snap.get("dcX2"),
        "over15":  open_snap.get("o15"),
        "over35":  open_snap.get("o35"),
        "under15": open_snap.get("u15"),
        "under35": open_snap.get("u35"),
        "ahH_n050": open_snap.get("ahH_n050"),
        "ahA_p050": open_snap.get("ahA_p050"),
        "ahH_n075": open_snap.get("ahH_n075"),
        "ahA_p075": open_snap.get("ahA_p075"),
        "ahH_n100": open_snap.get("ahH_n100"),
        "ahA_p100": open_snap.get("ahA_p100"),
        "o_corners85":  open_snap.get("cOver") if open_snap.get("cornerLine") == 8.5  else None,
        "o_corners95":  open_snap.get("cOver") if open_snap.get("cornerLine") == 9.5  else None,
        "o_corners105": open_snap.get("cOver") if open_snap.get("cornerLine") == 10.5 else None,
    }

    # Modell-Quoten (Elo + Poisson)
    lam_total = lam_h + lam_a
    p_o15 = poisson_over(lam_total, 1.5)
    p_o25 = poisson_over(lam_total, 2.5)
    p_o35 = poisson_over(lam_total, 3.5)
    p_b   = p_btts(lam_h, lam_a)
    dnb_h_mod, dnb_a_mod = derive_dnb(probs["pH"], probs["pD"], probs["pA"])

    # Doppelte Chance Modell-Quoten
    dc1x_mod, dc12_mod, dcx2_mod = derive_dc(probs["pH"], probs["pD"], probs["pA"])

    # Asian Handicap Modell-Quoten — basieren auf Skellam-Verteilung (Goal Difference)
    # Vereinfacht: P(home_goals - away_goals > line) für Heim-AH
    def _p_ah_home(line: float) -> float:
        """P(Heim deckt AH-Linie). line=-0.5 → P(home wins by ≥1)."""
        # Approximation via Poisson-Differenz mit lam_h vs lam_a
        # P(home_g - away_g >= ceil(-line)) für line < 0
        import math
        p = 0.0
        max_g = max(8, int(lam_total) + 5)
        for h_g in range(max_g):
            ph = math.exp(-lam_h) * (lam_h ** h_g) / math.factorial(h_g)
            for a_g in range(max_g):
                pa = math.exp(-lam_a) * (lam_a ** a_g) / math.factorial(a_g)
                diff = h_g - a_g
                # Quarter-Lines: 0.25-Schritte ergeben Halb-Stake-Push
                if line == -0.5 and diff >= 1: p += ph * pa
                elif line == -0.75 and diff >= 1: p += ph * pa * (1.0 if diff >= 2 else 0.5)
                elif line == -1.0 and diff >= 2: p += ph * pa
                elif line == -1.0 and diff == 1: p += ph * pa * 0.5  # Push-Anteil
                elif line == 0.5 and diff >= 0: p += ph * pa
                elif line == 0.75 and diff >= 0: p += ph * pa * (1.0 if diff >= 1 else 0.5)
                elif line == 1.0 and diff >= -1 and diff != 0: p += ph * pa
                elif line == 1.0 and diff == 0: p += ph * pa * 0.5
        return min(1.0, max(0.0, p))

    p_ah_h_n050 = _p_ah_home(-0.5)
    p_ah_a_p050 = 1.0 - _p_ah_home(-0.5)   # AH +0.5 Away ist Komplement von -0.5 Heim
    p_ah_h_n075 = _p_ah_home(-0.75)
    p_ah_a_p075 = 1.0 - p_ah_h_n075
    p_ah_h_n100 = _p_ah_home(-1.0)
    p_ah_a_p100 = 1.0 - p_ah_h_n100

    # Margin-Discount 3% (typisch für AH-Märkte)
    def _ah_odds(p: float) -> float | None:
        return prob_to_odds(p * 0.97) if p > 0.05 else None

    # Modell-Quoten für Corner-Märkte
    if corners_exp:
        total_c = corners_exp[2]
        m_c_85  = prob_to_odds(poisson_over_int(total_c, 8.5))
        m_c_95  = prob_to_odds(poisson_over_int(total_c, 9.5))
        m_c_105 = prob_to_odds(poisson_over_int(total_c, 10.5))
    else:
        m_c_85 = m_c_95 = m_c_105 = None

    model_odds: dict[str, float | None] = {
        "home":    prob_to_odds(probs["pH"]),
        "draw":    prob_to_odds(probs["pD"]),
        "away":    prob_to_odds(probs["pA"]),
        "over15":  prob_to_odds(p_o15),
        "over25":  prob_to_odds(p_o25),
        "over35":  prob_to_odds(p_o35),
        "under15": prob_to_odds(1.0 - p_o15),
        "under25": prob_to_odds(1.0 - p_o25),
        "under35": prob_to_odds(1.0 - p_o35),
        "btts":    prob_to_odds(p_b),
        "dnbH":    dnb_h_mod,
        "dnbA":    dnb_a_mod,
        "dc1X":    dc1x_mod,
        "dc12":    dc12_mod,
        "dcX2":    dcx2_mod,
        "ahH_n050": _ah_odds(p_ah_h_n050),
        "ahA_p050": _ah_odds(p_ah_a_p050),
        "ahH_n075": _ah_odds(p_ah_h_n075),
        "ahA_p075": _ah_odds(p_ah_a_p075),
        "ahH_n100": _ah_odds(p_ah_h_n100),
        "ahA_p100": _ah_odds(p_ah_a_p100),
        "o_corners85":  m_c_85,
        "o_corners95":  m_c_95,
        "o_corners105": m_c_105,
    }

    # ── Underdog-Stärke: ist das gepickte Team laut Elo deutlich schlechter? ─
    # Wird pro-Pick berechnet (Heimsieg vs Auswärtssieg haben entgegengesetzte Logik)
    def underdog_elo_gap(mkey: str) -> int:
        """Wie viele Elo-Punkte ist das gepickte Team schwächer? 0 = Favorit gepickt."""
        if mkey in ("home", "dnbH"):
            return max(0, -elo_diff)   # positiv wenn Heim schwächer
        if mkey in ("away", "dnbA"):
            return max(0, elo_diff)    # positiv wenn Auswärts schwächer
        return 0  # O/U, BTTS, Draw: kein Underdog-Konzept

    picks = []
    for mkey, label, min_edge in MARKET_CFG:
        # Bug-Fix 07.06.2026: Märkte die historisch Geld verloren haben (Backtest)
        # generieren keine Picks bis das Modell überarbeitet ist.
        if mkey in DISABLED_MARKETS:
            continue

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

        # ── Underdog-Sanity-Filter ────────────────────────────────────────
        elo_gap = underdog_elo_gap(mkey)

        # Hard: Elo-Gap >200 → immer SKIP (niemand wettet auf 200-Punkte-Underdog)
        if elo_gap > UNDERDOG_ELO_HARD:
            if VERBOSE:
                print(f"     ⛔  {label}: Elo-Gap {elo_gap} > {UNDERDOG_ELO_HARD} "
                      f"— Underdog zu schwach, übersprungen")
            continue

        # Soft: Elo-Gap >100 → kein BET, nur ABWÄGEN wenn Form-Stärke des Underdogs belegt
        if elo_gap > UNDERDOG_ELO_SOFT:
            # Underdog-Form prüfen: scored mehr als conceded in letzten Spielen?
            underdog_form = form_a if mkey in ("away", "dnbA") else form_h
            scored   = (underdog_form or {}).get("avgScored",   0)
            conceded = (underdog_form or {}).get("avgConceded", 9)
            form_ok  = scored > conceded * 0.85  # zumindest nicht viel schlechter als Schnitt

            # BET zurückstufen zu ABWÄGEN
            if v["verdict"] == "BET":
                v["verdict"] = "ABWÄGEN"
                if VERBOSE:
                    print(f"     ℹ️  {label}: Elo-Gap {elo_gap} > {UNDERDOG_ELO_SOFT} "
                          f"— BET→ABWÄGEN (Underdog {elo_gap}Elo schwächer)")

            # Wenn Form auch schwach: SKIP
            if not form_ok and (underdog_form or {}).get("games", 0) >= 5:
                if VERBOSE:
                    print(f"     ⛔  {label}: Elo-Gap {elo_gap} + schwache Underdog-Form "
                          f"({scored:.2f}:{conceded:.2f}) — SKIP")
                continue

        # ── BTTS-Spezialfilter: kein BTTS wenn ein Team 0 Form + Elo-Gap >150 ──
        # Ohne Form-Daten des schwächeren Teams schätzt das Modell dessen Torerfolg
        # über die Defensiv-Stats des Gegners — das ist für BTTS irreführend.
        if mkey == "btts":
            a_games = (form_a or {}).get("games", 0)
            h_games = (form_h or {}).get("games", 0)
            if (a_games == 0 and elo_diff > 150) or (h_games == 0 and elo_diff < -150):
                if VERBOSE:
                    print(f"     ⚠️  BTTS: Kein Form-Daten für Underdog + Elo-Gap > 150 — SKIP")
                continue

        # ── Globale Sanity-Checks ─────────────────────────────────────────

        # Edge > EDGE_MAX_SANE → suspect (falsche/invertierte Quoten)
        if v["edgePP"] > EDGE_MAX_SANE:
            if VERBOSE:
                print(f"     ⚠️  {label}: Edge {v['edgePP']}pp > {EDGE_MAX_SANE}pp — SKIP")
            continue

        # Marktquote > ODDS_MAX → kein liquider Markt
        if bk > ODDS_MAX:
            if VERBOSE:
                print(f"     ⚠️  {label}: Quote {bk:.2f} > {ODDS_MAX} — kein Markt, SKIP")
            continue

        # BET bei hohen Quoten (>ODDS_BET_MAX) → ABWÄGEN
        if bk > ODDS_BET_MAX and v["verdict"] == "BET":
            v["verdict"] = "ABWÄGEN"
            if VERBOSE:
                print(f"     ℹ️  {label}: Quote {bk:.2f} > {ODDS_BET_MAX} → BET→ABWÄGEN")

        # AUDIT-Fix 05.06.2026: Marktspezifische Quoten-Caps
        # O/U mit Quote >3.0 ist statistisch wackelig (z.B. HTI-SCO Über 3.5 @3.40)
        # DNB mit Quote >4.0 = klassische Underdog-DNB-Falle
        is_ou_market = mkey in ("over15", "over25", "over35", "under15", "under25", "under35", "btts")
        is_dnb_market = mkey in ("dnbH", "dnbA")
        if is_ou_market and bk > ODDS_BET_MAX_OU and v["verdict"] == "BET":
            v["verdict"] = "ABWÄGEN"
            if VERBOSE:
                print(f"     ℹ️  {label}: O/U-Quote {bk:.2f} > {ODDS_BET_MAX_OU} → BET→ABWÄGEN")
        elif is_dnb_market and bk > ODDS_BET_MAX_DNB and v["verdict"] == "BET":
            v["verdict"] = "ABWÄGEN"
            if VERBOSE:
                print(f"     ℹ️  {label}: DNB-Quote {bk:.2f} > {ODDS_BET_MAX_DNB} → BET→ABWÄGEN")

        # Modell stark favorisiert aber Markt gibt Außenseiter → invertierte Quoten
        if m_odds < 1.55 and bk > 3.5:
            if VERBOSE:
                print(f"     ⚠️  {label}: Modell={m_odds:.2f} vs Markt={bk:.2f} "
                      f"— Richtungskonflikt, SKIP")
            continue

        conf = edge_to_conf(v["edgePP"], v["verdict"])
        info = build_info(elo_diff, form_h, form_a, h2h or None, mkey, lam_h, lam_a,
                          travel_h=(trv_h, trv_h_lbl), travel_a=(trv_a, trv_a_lbl),
                          home_flag=home_t.get("flag",""), away_flag=away_t.get("flag",""),
                          pub_bias=pub_bias)

        pick_dict = {
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
            "clvPP":       round(v.get("clvPP", 0.0), 1),
            "dataQuality": data_quality,
        }
        # Public-Bias als strukturiertes Feld — Renderer kann's für Story nutzen
        if pub_bias and pub_bias.get("max_abs", 0) >= 4:
            pick_dict["publicBias"] = {
                "outcome":   pub_bias["max_outcome"],
                "direction": pub_bias["max_direction"],
                "pp":        pub_bias["max_abs"],
                "bookmaker": pub_bias.get("public_bk"),
            }

        # Corner-Erwartung anhängen wenn es sich um einen Corner-Pick handelt
        if mkey.startswith("o_corners") and corners_exp:
            pick_dict["cornersExpected"] = {
                "home":   round(corners_exp[0], 1),
                "away":   round(corners_exp[1], 1),
                "total":  round(corners_exp[2], 1),
            }
            pick_dict["icon"] = "🚩"

        picks.append(pick_dict)

    # ═══════════════════════════════════════════════════════════════════════
    #  SMART-SUBSTITUTION — sicherere Variante bevorzugen
    # ═══════════════════════════════════════════════════════════════════════
    # Profi-Logik: bei BET-Picks mit hoher Quote (>2.50) prüfen ob es eine
    # niedrigere Variante mit gleichem Outcome-Sentiment gibt UND positiv Edge.
    # → Niedrigere Quote = höhere Hit-Rate-Erwartung = besser für Community-Cards.
    #
    # Substitutions-Regeln (von risky → sicher):
    #   DNB Heim       → Doppelte Chance 1X (Heim oder Remis)
    #   DNB Auswärts   → Doppelte Chance X2 (Remis oder Auswärts)
    #   Heimsieg       → Doppelte Chance 1X    (wenn dort Edge da)
    #   Auswärtssieg   → Doppelte Chance X2    (wenn dort Edge da)
    #   Heimsieg       → AH Heim −0.5/−0.75    (wenn Edge da, niedrigere Quote)
    #   Auswärtssieg   → AH Auswärts +0.5/+0.75
    #   Über 2.5       → Über 1.5              (sicherer wenn beide Edge haben)
    #   Unter 2.5      → Unter 3.5             (sicherer)
    #
    # Substitution erfolgt NUR wenn:
    #   • Original-Pick verdict ∈ {BET, ABWÄGEN}
    #   • Original-Quote > 2.30 (sonst nicht "risky")
    #   • Safer-Pick existiert und hat verdict ∈ {BET, ABWÄGEN}
    #   • Safer-Quote < Original-Quote × 0.80 (mind. 20% niedriger)
    SUBSTITUTION_MAP = {
        "DNB: Heimteam":      ["Doppelte Chance — 1X", "AH Heim −0.5", "AH Heim −0.75"],
        "DNB: Auswärtsteam":  ["Doppelte Chance — X2", "AH Auswärts +0.5", "AH Auswärts +0.75"],
        "Heimsieg":           ["Doppelte Chance — 1X", "AH Heim −0.5"],
        "Auswärtssieg":       ["Doppelte Chance — X2", "AH Auswärts +0.5"],
        # AUDIT-Fix 05.06.2026: O/U-Substitution erweitert.
        # Vorher fehlte z.B. "Über 3.5 → Über 2.5" → Haiti-Schottland Über 3.5 @3.40
        # hatte keine Alternative. Jetzt: jede hohe O/U-Quote bekommt sicherere
        # Linien als Alternative angeboten.
        "Über 3.5 Tore":      ["Über 2.5 Tore", "Über 1.5 Tore"],
        "Über 2.5 Tore":      ["Über 1.5 Tore"],
        "Unter 1.5 Tore":     ["Unter 2.5 Tore", "Unter 3.5 Tore"],
        "Unter 2.5 Tore":     ["Unter 3.5 Tore"],
    }

    market_to_pick = {p["market"]: p for p in picks}

    # ── B2 Fix 05.06.2026: Cross-Market-Konsistenz-Check ──
    # Verhindert dass widersprüchliche Picks gleichzeitig BET sind.
    # Beispiel CAN-BIH 11.06.: "AH Heim −0.5" (Kanada gewinnt mit 1+) UND
    # "DNB: Auswärtsteam" (Bosnien gewinnt oder Remis) waren BEIDE BET → logisch
    # unmöglich. Ursache: jeder Markt rechnet isoliert ohne globale Sicht.
    # Lösung: pick_constants.DIRECTION_MAP + are_directions_incompatible.
    # Single Source of Truth — keine Inline-Duplikate mehr.
    from pick_constants import get_pick_direction as _get_dir
    from pick_constants import are_directions_incompatible as _is_incompatible_dir

    def _is_incompatible(d1: str, d2: str) -> bool:
        return _is_incompatible_dir(d1, d2)

    def _pick_confidence(p: dict) -> float:
        """Konfidenz-Score für Konflikt-Auflösung: Edge × dataQ × Konfidenz-Label."""
        edge = float(p.get("edgePP") or 0)
        dq   = p.get("dataQuality", "elo_only")
        dq_mult = {"full": 1.0, "elo+form": 0.8, "elo+form_asym": 0.5, "elo_only": 0.3}.get(dq, 0.5)
        conf_label = p.get("conf", "low")
        conf_mult = {"high": 1.0, "medium": 0.75, "low": 0.5}.get(conf_label, 0.5)
        return edge * dq_mult * conf_mult

    # ── B3 Fix 05.06.2026: BET nur bei vollständiger Datenbasis ──
    # Wenn dataQuality == "elo+form_asym" (nur EIN Team hat Form-Daten), ist das
    # Modell systematisch unzuverlässig — der fehlende Team-Datensatz wird mit
    # Default-Werten ersetzt, was künstliche Edges erzeugt. CAN-BIH zeigte +14pp
    # Edge auf DNB-Aus, obwohl BIH komplett unbekannt war.
    # Regel: BET nur bei dataQuality in {"full", "elo+form"}. "elo+form_asym"
    # und "elo_only" können maximal ABWÄGEN sein.
    asym_downgrades = []
    for p in picks:
        dq = p.get("dataQuality", "")
        if p.get("verdict") == "BET" and dq in ("elo+form_asym", "elo_only"):
            p["verdict"] = "ABWÄGEN"
            p["downgradedReason"] = f"BET→ABWÄGEN: dataQuality={dq} (Form-Daten fehlen ein Team)"
            asym_downgrades.append(p.get("market"))
    if asym_downgrades:
        print(f"  📉 Datenbasis-Sicherung: {len(asym_downgrades)} BETs→ABWÄGEN "
              f"(asymmetrische Form-Daten)")
        for m in asym_downgrades[:5]:
            print(f"     · {m}")

    # ── Modell-Bias-Schutz für O/U + AH ──────────────────────────────────────
    # Edge > 10pp auf O/U bzw. >12pp auf AH ist meist Modell-Bias gegen
    # Pinnacle's xG-Calibration, kein echter Edge. Auf ABWÄGEN downgraden.
    bias_downgrades = []
    for p in picks:
        if p.get("verdict") != "BET":
            continue
        m = (p.get("market") or "").lower()
        edge = float(p.get("edgePP") or 0)
        is_ou   = ("über" in m or "unter" in m or "beide teams" in m)
        is_ah   = ("ah " in m or "handicap" in m)
        if is_ou and edge > EDGE_OU_BET_MAX:
            p["verdict"] = "ABWÄGEN"
            p["downgradedReason"] = (
                f"O/U Edge {edge:.0f}pp > {EDGE_OU_BET_MAX}pp Modell-Bias-Schwelle"
            )
            bias_downgrades.append((p.get("market"), edge))
        elif is_ah and edge > EDGE_AH_BET_MAX:
            p["verdict"] = "ABWÄGEN"
            p["downgradedReason"] = (
                f"AH Edge {edge:.0f}pp > {EDGE_AH_BET_MAX}pp Modell-Bias-Schwelle"
            )
            bias_downgrades.append((p.get("market"), edge))
    if bias_downgrades:
        print(f"  🎯 Modell-Bias-Schutz: {len(bias_downgrades)} O/U+AH BETs→ABWÄGEN")
        for m, e in bias_downgrades[:5]:
            print(f"     · {m}: {e:+.0f}pp")

    # Iteriere alle BET-Pick-Paare und löse Konflikte
    bet_picks = [p for p in picks if p.get("verdict") == "BET"]
    downgraded = []
    for i, p_a in enumerate(bet_picks):
        if p_a.get("verdict") != "BET":
            continue   # könnte schon downgegraded sein
        dir_a = _get_dir(p_a.get("market", ""))
        if not dir_a:
            continue
        for p_b in bet_picks[i+1:]:
            if p_b.get("verdict") != "BET":
                continue
            dir_b = _get_dir(p_b.get("market", ""))
            if not dir_b:
                continue
            if not _is_incompatible(dir_a, dir_b):
                continue
            # Konflikt — schwächeren downgrade
            conf_a = _pick_confidence(p_a)
            conf_b = _pick_confidence(p_b)
            if conf_a >= conf_b:
                loser = p_b
            else:
                loser = p_a
            loser["verdict"] = "ABWÄGEN"
            loser["downgradedReason"] = (
                f"Konflikt mit '{(p_a if loser is p_b else p_b).get('market')}' "
                f"(unvereinbare Direction)"
            )
            downgraded.append((loser.get("market"), loser["downgradedReason"]))
    if downgraded:
        print(f"  ⚖️  Cross-Market-Konsistenz: {len(downgraded)} Picks downgegraded")
        for m, r in downgraded[:5]:
            print(f"     · {m}: {r}")

    # ── Cross-Model-Konsistenz: Elo (DNB) ↔ Skellam (AH +0.5) ─────────────
    # Bug-Fix 07.06.2026 (IRN-NZL Case):
    # DNB-Outcome und AH +0.5-Outcome decken FAKTISCH denselben Outcome ab
    # (Team gewinnt oder X). DNB nutzt Elo-Modell, AH +0.5 nutzt Skellam.
    # Wenn die beiden Modelle für den gleichen Outcome stark divergieren
    # (≥ MODEL_DIVERGENCE_PP), ist die Wahrscheinlichkeit nicht vertrauenswürdig.
    # → DNB-BET wird auf ABWÄGEN runtergesetzt.
    #
    # IRN-NZL: Elo sagt P(NZL no_loss)=58%, Skellam sagt 42% → 16pp Diff
    # → DNB Auswärts BET wäre fragwürdig. Lieber ABWÄGEN.
    DNB_AH_PAIRS = [
        # (dnb-market, ah-key (model_odds key), team-side für no_loss-Berechnung)
        ("DNB: Heimteam",     "ahH_n050", "home"),
        ("DNB: Auswärtsteam", "ahA_p050", "away"),
    ]
    MODEL_DIVERGENCE_PP = _cfg("edge", "dnb_ah_divergence_pp", 8)
    model_inconsistencies = []
    for dnb_label, ah_key, side in DNB_AH_PAIRS:
        dnb_p = market_to_pick.get(dnb_label)
        if not dnb_p or dnb_p.get("verdict") != "BET":
            continue
        ah_model_q = model_odds.get(ah_key)
        if not ah_model_q:
            continue
        # P(no_loss) aus Skellam: 1/ah_model_q × 0.97 (rückrechnen aus margin)
        # Code: model_odds_ah = prob_to_odds(p * 0.97) → p = 1/(odds * 0.97)
        p_skellam = 1.0 / (ah_model_q * 0.97)
        # P(no_loss) aus Elo: Win + Draw je nach side
        # 1X2-Modell-Quoten in model_odds["home"]/"draw"/"away"
        m_home = model_odds.get("home")
        m_draw = model_odds.get("draw")
        m_away = model_odds.get("away")
        if not (m_home and m_draw and m_away):
            continue
        p_home_elo = 1.0 / m_home
        p_draw_elo = 1.0 / m_draw
        p_away_elo = 1.0 / m_away
        p_elo = (p_home_elo if side == "home" else p_away_elo) + p_draw_elo
        diff_pp = (p_elo - p_skellam) * 100
        # Wenn Elo deutlich optimistischer als Skellam für den gepickten Team
        # → DNB-Edge ist wahrscheinlich überschätzt durch Elo-Bias
        if abs(diff_pp) >= MODEL_DIVERGENCE_PP:
            dnb_p["verdict"] = "ABWÄGEN"
            dnb_p["downgradedReason"] = (
                f"Modell-Inkonsistenz: Elo schätzt P(no_loss)={p_elo*100:.0f}%, "
                f"Skellam (AH +0.5) sagt {p_skellam*100:.0f}% — "
                f"Diff {diff_pp:+.0f}pp ≥ {MODEL_DIVERGENCE_PP}pp Schwelle"
            )
            model_inconsistencies.append((dnb_label, diff_pp))
    if model_inconsistencies:
        print(f"  🔀 Cross-Model-Konsistenz: {len(model_inconsistencies)} DNB-BETs→ABWÄGEN")
        for m, d in model_inconsistencies:
            print(f"     · {m}: Elo↔Skellam-Diff {d:+.0f}pp")

    safer_picks_to_add = []
    for p in picks:
        if p["verdict"] not in ("BET", "ABWÄGEN"):
            continue
        if (p.get("odds") or 0) <= 2.30:
            continue
        alternatives = SUBSTITUTION_MAP.get(p["market"], [])
        for alt_market in alternatives:
            alt_pick = market_to_pick.get(alt_market)
            if not alt_pick:
                continue
            if alt_pick["verdict"] not in ("BET", "ABWÄGEN"):
                continue
            if (alt_pick.get("odds") or 0) >= (p["odds"] * 0.80):
                continue   # nicht signifikant niedriger
            # Substitution: markiere Original als "boldAlt" der safer Variante
            alt_pick["saferAltFor"] = p["market"]
            alt_pick["icon"] = "🛡️"
            # Falls nicht bereits drin: zur safer-Liste hinzufügen
            # (alt_pick ist ja schon in picks, wir markieren nur)
            p["boldAlt"] = {
                "market": alt_pick["market"],
                "odds":   alt_pick["odds"],
                "edgePP": alt_pick["edgePP"],
            }
            # Auch im saferAlt-Feld speichern (bidirektional)
            alt_pick["riskierAlt"] = {
                "market": p["market"],
                "odds":   p["odds"],
                "edgePP": p["edgePP"],
            }
            break   # erstbeste safer Variante reicht

    # ── Corner-Beobachtungs-Marker: Falls Modell eine starke Erwartung hat
    # aber noch KEINE Markt-Quoten verfügbar sind, schreibe einen Info-Eintrag
    # damit Card/Modal das anzeigen können. Verdict="WATCH" → kein BET, kein ABWÄGEN.
    if corners_exp:
        any_corner_pick = any(p["market"].lower().startswith("über") and "ecken" in p["market"].lower() for p in picks)
        if not any_corner_pick:
            # Bestimme welche Linie das Modell am stärksten sieht (P closest to 0.55)
            total_c = corners_exp[2]
            best_line = 9.5  # Default
            best_p = 0
            for line, p_val in ((8.5, poisson_over_int(total_c, 8.5)),
                                  (9.5, poisson_over_int(total_c, 9.5)),
                                  (10.5, poisson_over_int(total_c, 10.5))):
                # 0.55-0.65 ist Sweet-Spot für Pick-Qualität
                if 0.50 <= p_val <= 0.70 and p_val > best_p:
                    best_p = p_val; best_line = line
            picks.append({
                "market":    f"Über {best_line} Ecken",
                "odds":      None,
                "modelOdds": prob_to_odds(poisson_over_int(total_c, best_line)),
                "conf":      "low",
                "verdict":   "WATCH",
                "modSig":    1,
                "mktSig":    0,
                "storySig":  0,
                "edgePP":    0,
                "info":      f"Ø {total_c:.1f} Ecken erwartet · Pick aktiv sobald Bookies Quoten öffnen",
                "icon":      "🚩",
                "result":    None,
                "clvPP":     0.0,
                "dataQuality": data_quality,
                "cornersExpected": {
                    "home":  round(corners_exp[0], 1),
                    "away":  round(corners_exp[1], 1),
                    "total": round(corners_exp[2], 1),
                },
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
    form         = wm.get("form",        {})
    h2h_data     = wm.get("h2h",         {})
    xg_stats     = wm.get("xgStats",     {})   # API-Football xG
    injuries     = wm.get("injuries",    {})   # Verletzungen/Sperren
    corners_form = wm.get("cornersForm", {})   # Eckball-Stats pro Team (fetch_wm_corners.py)

    # Travel-Burden (compute_wm_travel_burden.py) — separates File
    travel_data = {}
    travel_file = os.path.join(os.path.dirname(WM_FILE), "wm_travel_burden.json")
    if os.path.exists(travel_file):
        try:
            with open(travel_file, encoding="utf-8") as tf:
                travel_data = json.load(tf)
        except Exception as e:
            print(f"  ⚠️  Travel-Burden nicht ladbar: {e}")

    xg_count = sum(1 for v in xg_stats.values() if v and v.get("games", 0) >= 3)
    inj_count = sum(1 for k, v in injuries.items()
                    if k != "_meta" and isinstance(v, dict) and v.get("players"))
    travel_critical = sum(1 for k, v in travel_data.items()
                          if isinstance(v, dict) and any(
                              (l.get("burden") or "").lower() in ("critical", "high")
                              for l in v.get("legs", [])))
    print(f"  xgStats: {xg_count} Teams | Injuries: {inj_count} Teams | "
          f"Travel: {travel_critical} Teams mit kritischer Anreise\n")

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

            new_picks = generate_picks_for_fixture(
                fx, gdata, mkt, form, h2h_data, today,
                xg_stats=xg_stats, injuries=injuries,
                travel_data=travel_data,
                corners_form=corners_form,
            )

            # Immer überschreiben — auch leere Liste löscht veraltete Picks
            wm["picks"][pick_key] = new_picks

            if new_picks:
                total_with_picks += 1
                print(f"  ✅ {fx['home']} vs {fx['away']} (ST{fx['matchday']}, {fx_date}): "
                      f"{len(new_picks)} Pick(s)")
                if VERBOSE:
                    for p in new_picks:
                        edge = p.get("edgePP", "?")
                        print(f"     [{p['verdict']:8s}] {p['market']:35s} "
                              f"@ {p['odds']:.2f}  edge +{edge}pp  "
                              f"clv {p.get('clvPP',0):+.1f}pp  "
                              f"data={p.get('dataQuality','?')}  conf={p['conf']}")
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
