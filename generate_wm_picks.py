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

import json, math, os, re, sys
from datetime import datetime, timezone, timedelta
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

# Steam-Engine (Lucas' Modell): Picks pro Card + Conviction-BET-Schwelle.
# WM lockerer als Liga (weniger Spiele) — Liga-Profil setzt steam_bet_threshold höher.
MAX_STEAM_PICKS_PER_CARD = _cfg("conviction_score", "max_steam_picks_per_card", 3)
STEAM_BET_THRESHOLD      = _cfg("conviction_score", "steam_bet_threshold",      6)
# Steam-Cutover (Launch-Grenze 14.→15.06.2026): Spiele mit Anpfiff BIS hierher sind
# bereits veröffentlicht (DEU-CUW, NED-JPN, CIV-ECU) → Picks eingefroren/getrackt. Alles
# DANACH (ab SWE-TUN 02:00Z / BEL-EGY) wird mit Steam neu gebaut. Einmaliger Übergang.
STEAM_CUTOVER_UTC        = _cfg("steam", "cutover_after_utc", "2026-06-15T00:00:00Z")

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

    Discount-Skala (Sportwissenschaft zu Long-Haul-Travel bei NTs: -5% bis -15% xG):
      - critical:    factor 0.85 (-15%)
      - significant: factor 0.90 (-10%)
      - moderate:    factor 0.95 (-5%)
      - low/none:    1.0
    Plus Höhen-Penalty wenn alt_shift ≥ 1500m. Die Faktor-Logik lebt zentral in
    sharp_signals/travel_common.factor_from_leg() — geteilt mit der Signal-Engine,
    damit Pick-Bau und Adjustment NIE wieder driften (Drift-Fix 15.06.2026).
    """
    if not travel_data:
        return 1.0, ""
    from sharp_signals.travel_common import factor_from_leg, leg_for_matchday
    leg = leg_for_matchday(travel_data.get(team_id, {}), matchday)
    if not leg:
        return 1.0, ""

    factor, meta = factor_from_leg(leg)
    if not meta:   # same_venue o.ä. → kein Discount
        return 1.0, ""

    label = f"{meta['km']}km/{meta['rest_days']}d"
    if meta.get("carry_km"):
        label += f"/+{meta['carry_km']}km carry"
    if meta.get("alt_shift", 0) >= 1500:
        label += f"/+{meta['alt_shift']}m"
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
    # Breitere Linien für Mismatches (13.06.2026) — sicherere Underdog-Absicherung
    ("ahH_n150",  "AH Heim −1.5",               EDGE_MIN_AH),
    ("ahA_p150",  "AH Auswärts +1.5",           EDGE_MIN_AH),
    ("ahH_n200",  "AH Heim −2.0",               EDGE_MIN_AH),
    ("ahA_p200",  "AH Auswärts +2.0",           EDGE_MIN_AH),
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


# ──────────────────────────────────────────────────────────────────────────
#  Venue-Name → wm_venues.json venue_id Mapping
#  (für incentive_signal Komp C — Distanz-Berechnung)
# ──────────────────────────────────────────────────────────────────────────
_VENUE_NAME_TO_ID = {
    # Stadium-Name-Substrings → venue_id in wm_venues.json
    "azteca":          "mexico_city",
    "mexico city":     "mexico_city",
    "monterrey":       "monterrey",
    "guadalajara":     "guadalajara",
    "rose bowl":       "los_angeles",
    "sofi":            "los_angeles",
    "inglewood":       "los_angeles",
    "los angeles":     "los_angeles",
    "at&t":            "dallas",
    "arlington":       "dallas",
    "dallas":          "dallas",
    "nrg":             "houston",
    "houston":         "houston",
    "mercedes-benz":   "atlanta",
    "mercedes benz":   "atlanta",
    "atlanta":         "atlanta",
    "gillette":        "boston",
    "foxborough":      "boston",
    "boston":          "boston",
    "metlife":         "new_york",
    "east rutherford": "new_york",
    "new york":        "new_york",
    "new jersey":      "new_york",
    "lincoln":         "philadelphia",
    "philadelphia":    "philadelphia",
    "levi":            "san_francisco",
    "santa clara":     "san_francisco",
    "san francisco":   "san_francisco",
    "lumen":           "seattle",
    "seattle":         "seattle",
    "hard rock":       "miami",
    "miami gardens":   "miami",
    "miami":           "miami",
    "arrowhead":       "kansas_city",
    "kansas city":     "kansas_city",
    "bc place":        "vancouver",
    "vancouver":       "vancouver",
    "bmo":             "toronto",
    "toronto":         "toronto",
}


def _wm_venue_id_from_name(venue_name) -> str | None:
    """
    Mappt einen Venue-String aus wm2026-data.json auf venue_id in wm_venues.json.
    Substring-Match — robust gegen Schreibweisen ("Mexico City" / "Estadio Azteca, Mexico City" / "Azteca").
    Returns None wenn nicht erkannt.
    """
    if not isinstance(venue_name, str) or not venue_name.strip():
        return None
    needle = venue_name.lower()
    for key, vid in _VENUE_NAME_TO_ID.items():
        if key in needle:
            return vid
    return None


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

    # ── Pinnacle-Anker für 1X2/DC/DNB (Fix 13.06.2026) ───────────────────────
    # Vorher: 1X2/DC/DNB-Modell-Quoten kamen rein aus dem Elo-Modell. Das wich bei
    # klaren Favoriten stark von Pinnacle UND vom eigenen Tormodell ab und erzeugte
    # PHANTOM-Edges (QAT-SUI: Elo sah „Katar oder Remis" mit 31.5%, Pinnacle 19.6%,
    # Tormodell 18% → fake edge +10pp auf DC 1X). Philosophie (Lucas): Pinnacle ist
    # der Anker, NICHT zu schlagen; eigene Daten wirken als Modifikatoren — und zwar
    # über die Signal-Engine (effectiveEdgePP), nicht über eine abweichende Baseline.
    # Daher: Baseline pH/pD/pA = de-viggte Pinnacle-1X2. Elo bleibt Fallback wenn
    # keine Marktquote da ist (Pre-Tournament). O/U + BTTS werden seit 14.06.2026
    # ebenfalls an Pinnacle geankert (siehe _devig2-Block unten). AH-Linien laufen
    # noch über das Tor-Modell (lam_h/lam_a) — Kandidat für den nächsten Schritt.
    probs_elo = probs   # für Evidence/Debug behalten
    if bk_hw and bk_dr and bk_aw:
        _ph, _pd, _pa = devig_1x2(bk_hw, bk_dr, bk_aw)
        probs = {"pH": _ph, "pD": _pd, "pA": _pa, "anchored": True}

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
        "ahH_n150": odds_snap.get("ahH_n150"),
        "ahA_p150": odds_snap.get("ahA_p150"),
        "ahH_n200": odds_snap.get("ahH_n200"),
        "ahA_p200": odds_snap.get("ahA_p200"),
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
        "ahH_n150": open_snap.get("ahH_n150"),
        "ahA_p150": open_snap.get("ahA_p150"),
        "ahH_n200": open_snap.get("ahH_n200"),
        "ahA_p200": open_snap.get("ahA_p200"),
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

    # ── Pinnacle-Anker für O/U + BTTS (Fix 14.06.2026) ───────────────────────
    # ZWEITE HÄLFTE der 13.06.-Umstellung (Lucas): die Sieg-Märkte (1X2/DC/DNB) sind
    # seit 13.06. an Pinnacle geankert, die TOR-Märkte liefen aber WEITER über das
    # Poisson-λ → das Modell schlug Pinnacle und erzeugte Phantom-Edges (DEU-CUW Unter
    # 3.5: λ→48%, Pinnacle fair 39% → fake +7pp, obwohl Deutschland Curaçao zerlegt).
    # Jetzt: Baseline P(Über/Unter/BTTS) = de-viggte Pinnacle-Linie. Poisson bleibt
    # Fallback wenn Pinnacle die Linie nicht listet. Signale wirken obendrauf (Modifikator).
    def _devig2(o_over, o_under):
        """Faire P(over/yes) aus 2-Weg-Markt (Vig entfernt)."""
        if not o_over or not o_under or o_over <= 1.0 or o_under <= 1.0:
            return None
        io, iu = 1.0 / o_over, 1.0 / o_under
        return io / (io + iu)
    p_o15_elo, p_o25_elo, p_o35_elo, p_b_elo = p_o15, p_o25, p_o35, p_b   # Fallback/Debug
    ou_anchored = {}
    for _pname, _ov, _un in (("o15", "o15", "u15"), ("o25", "o25", "u25"),
                             ("o35", "o35", "u35"), ("btts", "bttsY", "bttsN")):
        _fair = _devig2(odds_snap.get(_ov), odds_snap.get(_un))
        if _fair is not None:
            ou_anchored[_pname] = True
            if   _pname == "o15": p_o15 = _fair
            elif _pname == "o25": p_o25 = _fair
            elif _pname == "o35": p_o35 = _fair
            elif _pname == "btts": p_b = _fair

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
                elif line == -1.5 and diff >= 2: p += ph * pa
                elif line == -2.0 and diff >= 3: p += ph * pa
                elif line == -2.0 and diff == 2: p += ph * pa * 0.5  # Push-Anteil
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
    p_ah_h_n150 = _p_ah_home(-1.5)
    p_ah_a_p150 = 1.0 - p_ah_h_n150
    p_ah_h_n200 = _p_ah_home(-2.0)
    p_ah_a_p200 = 1.0 - p_ah_h_n200

    # Margin-Discount 3% (typisch für AH-Märkte)
    def _ah_odds(p: float) -> float | None:
        return prob_to_odds(p * 0.97) if p > 0.05 else None

    # Generelle AH-Deckungs-„Units" (Win=1, Push=0.5, Loss=0) für JEDE Linie —
    # auch −2.75/−3.25 (Blowout-Bande). Viertel-Linien = Mittel zweier Halb-Wetten.
    # Basis für die dynamische Leiter-Wahl (13.06.2026).
    import math as _math
    _max_g = max(10, int(lam_total) + 6)
    _php = [_math.exp(-lam_h) * lam_h ** g / _math.factorial(g) for g in range(_max_g)]
    _pap = [_math.exp(-lam_a) * lam_a ** g / _math.factorial(g) for g in range(_max_g)]
    def _ah_units(line: float) -> float:
        def leg(L: float) -> float:
            u = 0.0
            for h in range(_max_g):
                ph = _php[h]
                for a in range(_max_g):
                    adj = (h - a) + L
                    if adj > 0:    u += ph * _pap[a]
                    elif adj == 0: u += 0.5 * ph * _pap[a]
            return u
        if round(line * 4) % 2 == 1:        # Viertel-Linie
            return (leg(line - 0.25) + leg(line + 0.25)) / 2.0
        return leg(line)

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
        "ahH_n150": _ah_odds(p_ah_h_n150),
        "ahA_p150": _ah_odds(p_ah_a_p150),
        "ahH_n200": _ah_odds(p_ah_h_n200),
        "ahA_p200": _ah_odds(p_ah_a_p200),
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

    # ── Dynamische AH-Linien aus der angebotenen Leiter (13.06.2026) ──────────
    # Pinnacle bietet AH als schmale Bande um die faire Linie (keine festen Buckets) —
    # bei Blowouts z.B. −2.75…−3.75. Wir lesen die GANZE Leiter und erzeugen pro
    # angebotener Linie einen Heim- + Auswärts-Markt (Modell-Prob via _ah_units, beliebige
    # Linie inkl. Viertel). Begrenzt auf kompetitive Linien (Units 0.15–0.85), damit die
    # Karte nicht mit Fast-Sicher-Linien überläuft. Ersetzt die festen ahH_n*/ahA_p*-Buckets.
    def _fmt_ah_line(x: float) -> str:
        s = f"{x:+.2f}".rstrip("0").rstrip(".")
        return s.replace("-", "−")   # Anzeige-Minus
    dyn_ah_markets = []
    _ladder = odds_snap.get("ahLadder") or {}
    if _ladder and lam_h and lam_a:
        for lk, pair in _ladder.items():
            try:
                L = float(lk)
            except (TypeError, ValueError):
                continue
            hp = (pair or [None, None])[0]
            ap = (pair or [None, None])[1] if pair and len(pair) > 1 else None
            u_home = _ah_units(L)
            if not (0.15 <= u_home <= 0.85):
                continue   # zu einseitig (Fast-Sicher) → uninteressant
            if hp:
                mk = f"ahH_dyn:{lk}"
                model_odds[mk]  = _ah_odds(u_home)
                market_odds[mk] = hp
                open_odds[mk]   = None
                dyn_ah_markets.append((mk, f"AH Heim {_fmt_ah_line(L)}", EDGE_MIN_AH))
            if ap:
                mk = f"ahA_dyn:{lk}"
                model_odds[mk]  = _ah_odds(1.0 - u_home)
                market_odds[mk] = ap
                open_odds[mk]   = None
                dyn_ah_markets.append((mk, f"AH Auswärts {_fmt_ah_line(-L)}", EDGE_MIN_AH))

    # Feste AH-Buckets durch dynamische Leiter ersetzen — ABER nur wenn die Leiter
    # tatsächlich Linien liefert. FIX 13.06.2026: Sind die Odds eingefroren/alt (kein
    # ahLadder, z.B. wenn TheOddsAPI diesen Lauf nicht neu gefetcht wurde), FALLBACK auf
    # die festen Buckets — sonst kollabieren die AH-Picks (60→6). Kein Entweder-Oder-Bruch.
    if dyn_ah_markets:
        _markets_iter = [m for m in MARKET_CFG
                         if not (m[0].startswith("ahH_") or m[0].startswith("ahA_"))] + dyn_ah_markets
    else:
        _markets_iter = list(MARKET_CFG)   # Leiter fehlt → feste Buckets behalten

    picks = []
    for mkey, label, min_edge in _markets_iter:
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
            # Echte Modell-Tor-Erwartung (das λ, auf dem O/U-/BTTS-Quoten beruhen).
            # FIX 12.06.2026: Card zeigte bisher eine FREMDE xG (matchPage) neben der
            # Modell-Prob → wirkte unstimmig (z.B. xG 2.87 neben P(Ü1.5)=85%). Jetzt
            # kann der Renderer die Zahl zeigen, auf der die Quote WIRKLICH basiert.
            "lamH":        round(lam_h, 2),
            "lamA":        round(lam_a, 2),
            "lamTotal":    round(lam_h + lam_a, 2),
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
        # FIX 14.06.2026: AH-Heim-Handicaps (Favoriten-Picks) hatten KEINE Substitution
        # → riskante „AH Heim −1.5 @2.90"-Heroes (Belgien, Iran, CIV) blieben Haupt-Pick,
        # obwohl AH −0.5 / Doppelte Chance 1X mit viel niedrigerer Quote verfügbar waren.
        # Ladder von riskant → sicher: −2.0 → −1.0 → −0.5 → DC 1X (Sieg-oder-Remis).
        "AH Heim −2.0":       ["AH Heim −1.0", "AH Heim −0.5", "Doppelte Chance — 1X"],
        "AH Heim −1.5":       ["AH Heim −0.5", "AH Heim −1.0", "Doppelte Chance — 1X"],
        "AH Heim −1.0":       ["AH Heim −0.5", "Doppelte Chance — 1X"],
        "AH Heim −0.75":      ["AH Heim −0.5", "Doppelte Chance — 1X"],
        "AH Heim −0.5":       ["Doppelte Chance — 1X"],
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
        if is_ou and edge >= EDGE_OU_BET_MAX:
            # FIX 12.06.2026: > → >= . Genau-10pp-O/U (z.B. USA-PRY Über 1.5, 85%/
            # λ≈3.3 vs xG 2.87) ist Grenzfall-Überkonfidenz → vorsichtshalber ABWÄGEN
            # statt Confidence-BET. Echte Mismatches mit kleinerer Edge bleiben BET.
            p["verdict"] = "ABWÄGEN"
            p["downgradedReason"] = (
                f"O/U Edge {edge:.0f}pp ≥ {EDGE_OU_BET_MAX}pp Modell-Bias-Schwelle"
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

    # Market-Label → Odds-Key Map für synthetische saferAlt
    # (wenn Alt-Markt in Odds verfügbar aber kein eigener Pick existiert)
    LABEL_TO_KEY = {
        "Doppelte Chance — 1X":  "dc1X",
        "Doppelte Chance — X2":  "dcX2",
        "Doppelte Chance — 12":  "dc12",
        "AH Heim −0.5":          "ahH_n050",
        "AH Heim −0.75":         "ahH_n075",
        "AH Heim −1.0":          "ahH_n100",
        "AH Auswärts +0.5":      "ahA_p050",
        "AH Auswärts +0.75":     "ahA_p075",
        "Über 2.5 Tore":         "o25",
        "Über 1.5 Tore":         "o15",
        "Unter 2.5 Tore":        "u25",
        "Unter 3.5 Tore":        "u35",
    }

    def _safer_alternatives(market: str) -> list:
        """Sichere Varianten für einen Markt. Statische Map zuerst; sonst generisch für
        die DYNAMISCHE AH-Leiter (−0.25, −2.25, −2.5, Auswärts −X …), die keine festen
        Labels hat. FIX 14.06.2026: vorher fielen alle dyn. AH-Linien durch → riskante
        Handicap-Heroes (BEL-NZL −2.5, SCO-MAR Auswärts −2) ohne sichere Alternative."""
        if market in SUBSTITUTION_MAP:
            return SUBSTITUTION_MAP[market]
        # Heim-Favorit (jede −X-Linie): normaler Sieg (AH −0.5) → flachere Linie (−1) →
        # DC 1X (Sieg/Remis). Beide Linien-Formate listen: dyn. Leiter strippt Nullen
        # („−1"), feste Buckets nicht („−1.0") → so greift CASE 1 (existierenden Pick
        # wiederverwenden) statt ein Duplikat zu synthetisieren.
        if market.startswith("AH Heim −"):
            return ["AH Heim −0.5", "AH Heim −1", "AH Heim −1.0", "Doppelte Chance — 1X"]
        # Auswärts-Favorit (negative Linie): analog. „+X" = Underdog-Absicherung → safe.
        if market.startswith("AH Auswärts −"):
            return ["AH Auswärts −0.5", "AH Auswärts −1", "AH Auswärts −1.0", "Doppelte Chance — X2"]
        return []

    def _alt_market_odds(alt_market: str):
        """(market_odds, model_odds) für ein Alt-Label. Erst feste Keys (LABEL_TO_KEY),
        dann die DYNAMISCHE AH-Leiter (ahH_dyn:/ahA_dyn:) — sonst sind safere Away-/
        Quarter-Linien (z.B. „AH Auswärts −1.0") unerreichbar (FIX 14.06.2026)."""
        key = LABEL_TO_KEY.get(alt_market)
        if key and market_odds.get(key):
            return market_odds.get(key), model_odds.get(key)
        m = re.match(r"AH (Heim|Auswärts) (.+)", alt_market)
        if m:
            side = m.group(1)
            try:
                val = float(m.group(2).replace("−", "-"))
            except ValueError:
                return None, None
            target_L = val if side == "Heim" else -val   # Leiter-Key ist Heim-Perspektive
            prefix = "ahH_dyn:" if side == "Heim" else "ahA_dyn:"
            for mk in market_odds:
                if not mk.startswith(prefix):
                    continue
                try:
                    if abs(float(mk.split(":", 1)[1]) - target_L) < 1e-9:
                        return market_odds.get(mk), model_odds.get(mk)
                except ValueError:
                    continue
        return None, None

    safer_picks_to_add = []
    for p in picks:
        if p["verdict"] not in ("BET", "ABWÄGEN"):
            continue
        if (p.get("odds") or 0) <= 2.30:
            continue
        alternatives = _safer_alternatives(p["market"])
        for alt_market in alternatives:
            alt_pick = market_to_pick.get(alt_market)
            # CASE 1: Alt-Pick existiert bereits mit eigenem Verdict
            if alt_pick and alt_pick["verdict"] in ("BET", "ABWÄGEN"):
                pass  # weiter zur Quoten-Prüfung unten
            else:
                # CASE 2 (Lucas 09.06.2026): Alt-Pick existiert nicht oder ist SKIP/WATCH
                # → synthetischen Pick aus odds/model_odds bauen wenn Quote verfügbar
                alt_odds, alt_model = _alt_market_odds(alt_market)
                if not alt_odds or alt_odds <= 1.0:
                    continue
                # FIX 14.06.2026: „signifikant niedriger"-Check VOR die Synthese ziehen.
                # Vorher wurde der synthetische Safer-Pick angelegt und erst danach geprüft
                # → eine HÖHERE/gleiche Quote (z.B. AH −0.25 → „safer" −0.5 @5.8 bei PAN-CRO,
                # eine HÄRTERE Linie!) landete trotzdem als saferAltFor in der Liste und wurde
                # zum Hero. Eine sichere Variante MUSS echt niedrigere Quote haben.
                if alt_odds >= (p["odds"] * 0.80):
                    continue
                # Edge optional — auch ohne eigene Edge als "Insurance" anbieten.
                # FIX 09.06.2026 Agent-Audit: Edge-Floor von -2pp verhindert
                # synthetische Picks die garantiert -EV sind (DC/AH-Märkte haben
                # oft höhere Vig als 1X2, daher gefährlich ohne Floor).
                alt_edge = 0.0
                if alt_model and alt_model > 1.0:
                    # FIX 10.06.2026 (Audit): Vorzeichen war invertiert + Margins fehlten.
                    # compute_verdict() rechnet model_prob - market_prob mit
                    # model_prob=(1/model)*MODEL_MARGIN, market_prob=(1/markt)*1.03.
                    # Alt: (1/alt_odds - 1/alt_model) = market - model OHNE Margin
                    # → negiertes Vorzeichen → SYNTH_EDGE_FLOOR wirkte verkehrt herum.
                    alt_edge = ((1.0/alt_model) * MODEL_MARGIN
                                - (1.0/alt_odds) * 1.03) * 100  # 1:1 wie compute_verdict
                SYNTH_EDGE_FLOOR_PP = -2.0
                if alt_edge < SYNTH_EDGE_FLOOR_PP:
                    continue  # Alt-Quote zu schlecht — kein Insurance-Anbieten
                # FIX 09.06.2026 — Dedup: Wenn ein anderer Pick schon DIESE saferAlt
                # vorgeschlagen hat, nicht 2× pushen. Stattdessen Original an die
                # saferAltFor-Liste hängen (kommagetrennt, für Info-Text).
                existing = next((sp for sp in safer_picks_to_add
                                 if sp["market"] == alt_market
                                 and abs((sp.get("odds") or 0) - alt_odds) < 1e-6), None)
                if existing:
                    prev = existing.get("saferAltFor", "")
                    if p["market"] not in prev.split(" + "):
                        existing["saferAltFor"] = f"{prev} + {p['market']}" if prev else p["market"]
                        existing["info"] = (f"Synthetisch als sicherere Alternative zu "
                                            f"„{existing['saferAltFor']}\" — eigene Edge "
                                            f"{existing['edgePP']:+.1f}pp")
                    # Original an boldAlt hängen, dann nächste Iteration
                    p["boldAlt"] = {
                        "market": existing["market"],
                        "odds":   existing["odds"],
                        "edgePP": existing["edgePP"],
                    }
                    # FIX 14.06.2026: riskante Variante ist durch die sichere ERSETZT →
                    # nicht mehr separat tracken/anzeigen (sonst tauchen die hohen Quoten
                    # weiter in „Weitere Picks" + Tracking auf, Lucas-Befund).
                    p["trackingExcluded"] = True
                    break
                alt_pick = {
                    "market":     alt_market,
                    "odds":       alt_odds,
                    "modelOdds":  alt_model,
                    "verdict":    "ABWÄGEN",
                    "edgePP":     round(alt_edge, 1),
                    "modSig":     1,
                    "mktSig":     0,
                    "storySig":   0,
                    "info":       f"Synthetisch als sicherere Alternative zu „{p['market']}\" — eigene Edge {alt_edge:+.1f}pp",
                    "icon":       "🛡️",
                    "synthetic":  True,
                    "saferAltFor": p["market"],
                    "result":     None,
                    "clvPP":      0.0,
                    "dataQuality": data_quality,
                }
                safer_picks_to_add.append(alt_pick)
            if (alt_pick.get("odds") or 0) >= (p["odds"] * 0.80):
                continue   # nicht signifikant niedriger
            # Substitution: markiere Original als "boldAlt" der safer Variante
            alt_pick["saferAltFor"] = p["market"]
            alt_pick["icon"] = "🛡️"
            p["boldAlt"] = {
                "market": alt_pick["market"],
                "odds":   alt_pick["odds"],
                "edgePP": alt_pick["edgePP"],
            }
            # FIX 14.06.2026: riskante Variante ist durch die sichere ERSETZT → nicht mehr
            # separat tracken/anzeigen (hohe Quoten sonst weiter in Weitere Picks + Tracking).
            p["trackingExcluded"] = True
            # Auch im saferAlt-Feld speichern (bidirektional)
            alt_pick["riskierAlt"] = {
                "market": p["market"],
                "odds":   p["odds"],
                "edgePP": p["edgePP"],
            }
            break   # erstbeste safer Variante reicht
    # Synthetische saferAlt-Picks ans Ende der Liste anhängen
    picks.extend(safer_picks_to_add)
    # AH-Linien-Dedup läuft als Final-Pass über ALLE Spiele am Ende (deckt auch heutige
    # Signal-Refresh-Spiele ab, bei denen dieser Builder übersprungen wird). Siehe main().

    # ── Cross-Market-Konflikt-Filter (FIX 09.06.2026) ─────────────────────────
    # Bisher: validate_wm_picks fängt nur BET-vs-BET-Konflikte. ABWÄGEN-vs-ABWÄGEN
    # blieb unentdeckt — Card zeigte z.B. CAN-Auswärtssieg + AH Heim −0.5 nebeneinander.
    # Jetzt: schwächeren Konflikt-Pick als trackingExcluded markieren (Card-Renderer
    # blendet die aus). Synthetische saferAlts werden NICHT excluded (sind Insurance).
    try:
        from pick_helpers import (get_pick_direction as _gd,
                                  are_directions_incompatible as _inc)
        def _strength(p):
            # Höherer Wert = stärker. Conviction zählt am meisten, dann Edge.
            return ((p.get("convictionScore") or 0) * 100.0
                    + (p.get("edgePP") or 0))
        for i, a in enumerate(picks):
            if a.get("trackingExcluded") or a.get("synthetic"):
                continue
            if a.get("verdict") not in ("BET", "ABWÄGEN"):
                continue
            d_a = _gd(a.get("market"))
            if not d_a:
                continue
            for b in picks[i+1:]:
                if b.get("trackingExcluded") or b.get("synthetic"):
                    continue
                if b.get("verdict") not in ("BET", "ABWÄGEN"):
                    continue
                d_b = _gd(b.get("market"))
                if not d_b or not _inc(d_a, d_b):
                    continue
                # Schwächeren excluden — bei Gleichstand den späteren
                loser = b if _strength(a) >= _strength(b) else a
                loser["trackingExcluded"] = True
                # FIX 11.06.2026: HART auf SKIP setzen, nicht nur trackingExcluded.
                # Vorher blieb verdict=ABWÄGEN → jeder Sender, der nur nach Verdict
                # filtert (telegram_wm, tiktok), zeigte den Widerspruch trotzdem.
                # SKIP ist für ALLE Renderer unsichtbar (alle filtern BET/ABWÄGEN).
                # Eine Engine darf NIE Heim- UND Auswärtssieg gleichzeitig zeigen.
                loser["verdict"] = "SKIP"
                loser["excludeReason"] = (
                    f"Cross-Market-Konflikt mit „{(a if loser is b else b).get('market')}\""
                )
    except Exception as _e:
        print(f"   ⚠️  cross-market-filter skipped: {_e}")

    # ── Corner-Beobachtungs-Marker: Falls Modell eine starke Erwartung hat
    # aber noch KEINE Markt-Quoten verfügbar sind, schreibe einen Info-Eintrag
    # damit Card/Modal das anzeigen können. Verdict="WATCH" → kein BET, kein ABWÄGEN.
    # Profile-gated: wenn alle Corner-Markets disabled (z.B. WM2026), wird auch
    # kein WATCH-Marker geschrieben — Cards bleiben Corner-frei.
    _corners_all_disabled = all(k in DISABLED_MARKETS for k in ("o_corners85", "o_corners95", "o_corners105"))
    if corners_exp and not _corners_all_disabled:
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


# ════════════════════════════════════════════════════════════════════════════
# STEAM-ENGINE (Lucas' echtes Modell, 14.06.2026) — Pinnacle-Move-Following.
# Ersetzt den Poisson/Elo-Edge-Trigger als Pick-Quelle für NEU gebaute Spiele.
# Trigger = Pinnacle-Drop (open→jetzt). Kein Fair-Value. Pick = gesteamte Seite zur
# Softbook-Quote (bzw. abgeleitete sichere Linie bei heftigen Favoriten). Die nachge-
# lagerte Signal- + Conviction-Maschine bleibt UNVERÄNDERT: sie feuert die 17 Signale
# auf den Pick, die Sharp-Money-Familie erkennt den Move, Conviction ≥8 hebt ABWÄGEN→BET.
# modelOdds = de-viggte Pinnacle-Baseline der Pick-Seite → hält den O/U-Anker-Guard grün
# und liefert einen ehrlichen (kleinen) Softbook-vs-Pinnacle-Edge.
# ════════════════════════════════════════════════════════════════════════════
_STEAM_OU_PAIR = {
    "Über 1.5 Tore": ("o15", "u15"), "Unter 1.5 Tore": ("u15", "o15"),
    "Über 2.5 Tore": ("o25", "u25"), "Unter 2.5 Tore": ("u25", "o25"),
    "Über 3.5 Tore": ("o35", "u35"), "Unter 3.5 Tore": ("u35", "o35"),
    "Beide Teams treffen — Ja": ("bttsY", "bttsN"),
    "Beide Teams treffen — Nein": ("bttsN", "bttsY"),
}


def _steam_model_odds(snap, market):
    """modelOdds = prob_to_odds(de-viggte Pinnacle-Fair der Pick-Seite).
    1X2 → 3-Weg-Devig, O/U/BTTS → 2-Weg-Devig. AH → None (keine saubere Fair-Linie,
    Caller nutzt dann die Quote selbst → Edge ~0, ehrlich)."""
    if market in ("Heimsieg", "Unentschieden", "Auswärtssieg"):
        hw, dr, aw = snap.get("hw"), snap.get("dr"), snap.get("aw")
        if hw and dr and aw and min(hw, dr, aw) > 1.0:
            ph, pd, pa = devig_1x2(hw, dr, aw)
            p = {"Heimsieg": ph, "Unentschieden": pd, "Auswärtssieg": pa}[market]
            return prob_to_odds(p)
        return None
    pair = _STEAM_OU_PAIR.get(market)
    if pair:
        a, b = snap.get(pair[0]), snap.get(pair[1])
        if a and b and a > 1.0 and b > 1.0:
            ia, ib = 1.0 / a, 1.0 / b
            return prob_to_odds(ia / (ia + ib))
    return None


def _steam_card_pick(snap, pick):
    """Ein steam_engine-Pick → Card-Dict im Standard-Format (Signal/Conviction-Stufe
    hängt danach signals/convictionScore an)."""
    t = pick["trigger"]
    market = pick["market"]
    odds = float(pick["entry_odd"])
    model_odds = _steam_model_odds(snap, market) or odds
    edge_pp = 0
    if model_odds > 1.0 and odds > 1.0:
        edge_pp = round(((1.0 / model_odds) * MODEL_MARGIN - (1.0 / odds) * 1.03) * 100)

    move = t["move_pp"]
    soft_lag = pick.get("soft_lagging")
    soft_follow = pick.get("soft_follow_pp")
    soft_confirmed = bool(pick.get("soft_confirmed"))
    parts = [f"📉 Pinnacle {t['open']}→{t['cur']} (Sharp-Money-Drop +{move}pp)"]
    # Soft-Bestätigung: ist der Soft-Konsens dem Move gefolgt? (echte Bestätigung)
    if soft_confirmed:
        parts.append(f"✅ Soft-Konsens folgte +{soft_follow}pp (bestätigt)")
    elif soft_lag is not None and soft_lag > 0.5:
        parts.append(f"Soft-Konsens hinkt +{soft_lag}pp (Value, noch nicht bestätigt)")
    if pick.get("derived"):
        parts.append(f"sichere Linie abgeleitet: {market} @{odds:g}")
    if pick.get("lateEntry"):
        parts.append("⏱️ Late Entry — Lernwert, weniger CLV")
    info = " · ".join(parts)
    conf = "high" if (t["sweet"] and move >= 4) else "medium"

    return {
        "market": market, "odds": round(odds, 2), "modelOdds": round(model_odds, 3),
        "conf": conf, "verdict": "ABWÄGEN",        # Lebenszyklus: reift via Conviction→BET
        "modSig": 0, "mktSig": 0, "storySig": 0,
        "edgePP": edge_pp, "info": info, "icon": "🔥",
        "result": None, "clvPP": 0.0, "dataQuality": "steam",
        "lamH": None, "lamA": None, "lamTotal": None,
        # ── Steam-Metadaten (Anzeige + CLV-Tracking) ──
        "source": "steam", "steamMovePP": move,
        "steamOpen": t["open"], "steamCur": t["cur"],
        "entryBook": pick["book"], "entryOdd": round(odds, 2),
        "lateEntry": bool(pick.get("lateEntry")), "steamDerived": bool(pick.get("derived")),
        "softConfirmed": soft_confirmed, "softFollowPP": soft_follow,
        "ahLine": pick.get("ah_line"),
    }


def generate_steam_picks_for_fixture(fx, snap, today_iso, drift=None):
    """Bis zu MAX_STEAM_PICKS_PER_CARD Steam-Picks je Spiel im Card-Format (oder []).
    Mehrere, wenn verschiedene Kategorien droppen (z.B. Home-HC + Over). Die Signal/
    Conviction-Stufe danach hängt signals/convictionScore an und hebt ABWÄGEN→BET.
    drift = markt-weiter Median-Move → spielspezifisches Sharp-Money isolieren."""
    if not snap:
        return []
    import steam_engine as _steam
    try:
        days = (datetime.fromisoformat(str(fx.get("date"))).date()
                - datetime.fromisoformat(str(today_iso)).date()).days
    except Exception:
        days = None
    picks = _steam.build_steam_picks(snap, days_to_ko=days,
                                     max_picks=MAX_STEAM_PICKS_PER_CARD, drift=drift)
    # Multi-Pick: widersprüchliche Kombis vermeiden (z.B. Unter 3.5 + BTTS Ja). Stärkster
    # Pick zuerst (detect_steam sortiert nach Sweet+Move) — schwächere Widersprüche raus.
    # Nutzt die zentrale Inkompatibilitäts-Logik (pick_helpers = single source of truth).
    try:
        from pick_helpers import picks_are_incompatible
    except Exception:
        picks_are_incompatible = lambda a, b: False  # noqa: E731
    cards = []
    for p in picks:
        card = _steam_card_pick(snap, p)
        if any(picks_are_incompatible(card, kept) for kept in cards):
            continue
        cards.append(card)
    return cards


def _parse_kickoff(kt):
    """fx.kickoff (UTC-ISO) → aware datetime, oder None. fx.time ist unzuverlässig
    (siehe [[feedback_fx_time_unreliable]]), daher immer kickoff."""
    if not kt:
        return None
    try:
        return datetime.fromisoformat(str(kt).replace("Z", "+00:00"))
    except Exception:
        return None


def fixture_pick_state(fx, has_pick, today, now_dt, cutover_dt):
    """Single Source of Truth: was passiert mit den Picks eines Fixtures?

    Returns einen von vier Zuständen:
      'past'           — Spiel-Datum < today → unangetastet lassen.
      'kickoff_passed' — Anpfiff vorbei (Spiel läuft/beendet) → nie (neu) bauen, nur tracken.
      'refresh'        — veröffentlicht (Anpfiff ≤ Cutover) UND Pick existiert → Märkte/Quoten
                         reuse, Signale/Conviction neu (Launch-Schutz, kein Pick-Drift).
      'rebuild'        — sonst (künftig ODER heute Post-Cutover) → mit Steam neu bauen.

    FIX 15.06.2026 (Lucas): KEIN `fx_date == today`-Gate mehr. Nur die Anpfiff-Zeit
    gegen den Steam-Cutover entscheidet, ob ein Spiel als veröffentlicht gilt. Vorher
    fror das Datum-Gate auch heutige NOCH-NICHT-veröffentlichte Post-Cutover-Spiele
    (ESP abends, BEL) ein. Fehlender/unparsebarer Anpfiff → wie upcoming behandeln
    (lieber rebuild als versehentlich freezen). Siehe [[feedback_posted_picks_immutable]]."""
    fx_date = fx.get("date")
    if fx_date and today and fx_date < today:
        return "past"
    ko = _parse_kickoff(fx.get("kickoff"))
    if ko is not None and now_dt is not None and ko <= now_dt:
        return "kickoff_passed"
    if has_pick and cutover_dt is not None and ko is not None and ko <= cutover_dt:
        return "refresh"
    return "rebuild"


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
    xg_stats     = wm.get("xgStats",     {})   # Understat xG (Europa-Teams)

    # ── NT-xG aus API-Football als Fallback für fehlende Teams (08.06.2026) ──
    # Understat hat nur ~15 von 48 Teams (Europa-fokussiert). wm_nt_xg.json
    # liefert NT-xG aus den letzten Nationalmannschafts-Spielen für die
    # ~33 fehlenden Teams (CONMEBOL/AFC/Afrika/CONCACAF/OFC).
    # Merge: Understat hat Priorität, NT-xG füllt nur Lücken.
    try:
        nt_xg_file = os.path.join(os.path.dirname(WM_FILE), "wm_nt_xg.json")
        if os.path.exists(nt_xg_file):
            with open(nt_xg_file, encoding="utf-8") as f:
                nt_xg = json.load(f)
            merged = 0
            sim_filled = 0
            # Zusatzfelder, die IMMER durchgereicht werden (auch wenn Understat das
            # echte xG stellt) — sie speisen die neuen Signale (chance_creation,
            # defense/rating) für ALLE Teams, nicht nur die ohne Understat.
            EXTRA = ("xgSimForAvg", "xgSimAgainstAvg", "shotsInsideForAvg",
                     "sotForAvg", "savesForAvg", "blocksForAvg",
                     "keyPassesForAvg", "ratingAvg")
            for tid, entry in nt_xg.items():
                if not isinstance(entry, dict):
                    continue
                rec = xg_stats.get(tid)
                understat_real = (rec is not None
                                  and rec.get("games", 0) >= 3
                                  and rec.get("xgForAvg") is not None
                                  and rec.get("source", "understat") == "understat")
                if rec is None:
                    rec = {}
                    xg_stats[tid] = rec
                # Zusatzfelder immer überlagern (für die neuen Signale)
                for k in EXTRA:
                    if entry.get(k) is not None:
                        rec[k] = entry[k]
                if understat_real:
                    continue  # echtes Understat-xG behält Priorität für xgForAvg/Against
                # xG-Werte aus NT-xG: echtes API-xG, sonst Schuss-Proxy (xGsim)
                real_for = entry.get("xgForAvg")
                if real_for is not None:
                    rec["xgForAvg"]     = real_for
                    rec["xgAgainstAvg"] = entry.get("xgAgainstAvg")
                    rec["games"]        = entry.get("xgGames") or entry.get("games", 0)
                    rec["source"]       = "apif_real"
                    merged += 1
                elif entry.get("xgSimForAvg") is not None:
                    rec["xgForAvg"]     = entry["xgSimForAvg"]
                    rec["xgAgainstAvg"] = entry.get("xgSimAgainstAvg")
                    rec["games"]        = entry.get("games", 0)
                    rec["source"]       = "shot_proxy"   # kalibrierter xGsim (R²=0.78)
                    sim_filled += 1
            if merged or sim_filled:
                print(f"  ⊕ NT-xG gemerged: {merged} echt + {sim_filled} via xGsim-Proxy\n")
    except Exception as e:
        print(f"  ⚠️  NT-xG-Merge fehlgeschlagen: {e}")
    injuries     = wm.get("injuries",    {})   # Verletzungen/Sperren
    corners_form = wm.get("cornersForm", {})   # Eckball-Stats pro Team (fetch_wm_corners.py)

    # ── Aufstellungen aus wm_lineups.json (T-1h, fetch_wm_lineups.py) ──────
    # Nur wenige Spiele pro Run haben aktuelle Lineups (nur die nächsten 1-3h).
    # Signal lineup_signal feuert dann pro Pick.
    lineups_data: dict = {}
    try:
        lineups_file = os.path.join(os.path.dirname(WM_FILE), "wm_lineups.json")
        if os.path.exists(lineups_file):
            with open(lineups_file, encoding="utf-8") as f:
                lineups_data = json.load(f)
            print(f"  📋 Lineups geladen: {len(lineups_data)} Spiele\n")
    except Exception as e:
        print(f"  ⚠️  Lineups-Load fehlgeschlagen: {e}")

    # ── API-Football Predictions (externes Cross-Model, täglich) ────────
    # Drittes Modell unabhängig von Skellam+Elo und Pinnacle. apif_predictions
    # Signal vergleicht pro 1X2/DNB-Pick gegen Pinnacle implied.
    apif_predictions_data: dict = {}
    try:
        apif_file = os.path.join(os.path.dirname(WM_FILE), "wm_apif_predictions.json")
        if os.path.exists(apif_file):
            with open(apif_file, encoding="utf-8") as f:
                apif_predictions_data = json.load(f)
            print(f"  📊 API-Football Predictions geladen: "
                  f"{len(apif_predictions_data)} Spiele\n")
    except Exception as e:
        print(f"  ⚠️  APIF-Predictions-Load fehlgeschlagen: {e}")

    # ── Wettervorhersage aus wm_weather.json (fetch_wm_weather.py) ────────
    # Open-Meteo liefert tempMax/Min/Wind/Niederschlag/WeatherCode pro Spieltag.
    # weather_signal nutzt das für Hitze-Penalty bei Cold-Climate-Teams.
    # Außerdem schreiben wir das in fixture.weather damit Renderer-Pille
    # (cc-env-heat ab 32°C) endlich anzeigen kann.
    weather_data: dict = {}
    try:
        weather_file = os.path.join(os.path.dirname(WM_FILE), "wm_weather.json")
        if os.path.exists(weather_file):
            with open(weather_file, encoding="utf-8") as f:
                weather_data = json.load(f).get("matches", {}) or {}
            n_with_forecast = sum(
                1 for v in weather_data.values()
                if isinstance(v, dict) and v.get("forecastAvailable")
            )
            print(f"  🌡️ Wetter geladen: {n_with_forecast}/{len(weather_data)} "
                  f"Spiele mit Vorhersage\n")
    except Exception as e:
        print(f"  ⚠️  Weather-Load fehlgeschlagen: {e}")

    # Travel-Burden (compute_wm_travel_burden.py) — separates File
    travel_data = {}
    travel_file = os.path.join(os.path.dirname(WM_FILE), "wm_travel_burden.json")
    if os.path.exists(travel_file):
        try:
            with open(travel_file, encoding="utf-8") as tf:
                travel_data = json.load(tf)
        except Exception as e:
            print(f"  ⚠️  Travel-Burden nicht ladbar: {e}")

    # Odds-History (für Signal-Engine LeadLag-Bias + Steam-Lag)
    odds_history = {}
    hist_file = os.path.join(os.path.dirname(WM_FILE), "wm2026-odds-history.json")
    if os.path.exists(hist_file):
        try:
            with open(hist_file, encoding="utf-8") as hf:
                odds_history = json.load(hf)
        except Exception as e:
            print(f"  ⚠️  Odds-History nicht ladbar: {e}")

    # Polymarket-Snapshot (für Polymarket-Sharp + Steam-Lag-Signal)
    poly_snapshots = {}
    poly_file = os.path.join(os.path.dirname(WM_FILE), "wm_poly_prices.json")
    if os.path.exists(poly_file):
        try:
            with open(poly_file, encoding="utf-8") as pf:
                poly_data = json.load(pf)
            for _fx in poly_data.get("allFixtures", []):
                k = _fx.get("key")
                if k:
                    poly_snapshots[k] = _fx
        except Exception as e:
            print(f"  ⚠️  Polymarket-Snapshot nicht ladbar: {e}")

    xg_count = sum(1 for v in xg_stats.values() if v and v.get("games", 0) >= 3)
    inj_count = sum(1 for k, v in injuries.items()
                    if k != "_meta" and isinstance(v, dict) and v.get("players"))
    travel_critical = sum(1 for k, v in travel_data.items()
                          if isinstance(v, dict) and any(
                              (l.get("burden") or "").lower() in ("critical", "significant")
                              for l in v.get("legs", [])))
    print(f"  xgStats: {xg_count} Teams | Injuries: {inj_count} Teams | "
          f"Travel: {travel_critical} Teams mit kritischer Anreise\n")

    wm.setdefault("picks", {})

    today    = datetime.now(timezone.utc).date().isoformat()
    tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    now_dt   = datetime.now(timezone.utc)

    # Markt-weiter Median-Move je Seite (Opening→jetzt) über ALLE Fixtures. Wird vom
    # Steam-Trigger abgezogen → nur spielspezifisches Sharp-Money zählt, nicht der
    # WM-weite Tor-Markt-Drift (sonst triggert fast jedes Spiel „Unter/BTTS-Nein").
    try:
        import steam_engine as _steam_mod
        _steam_drift = _steam_mod.market_drift(mkt)
        if _steam_drift:
            print(f"  Steam-Markt-Drift (abgezogen): "
                  + ", ".join(f"{k} {v:+.1f}" for k, v in sorted(_steam_drift.items())))
    except Exception as _e:
        _steam_drift = {}
        print(f"  ⚠️  Steam-Markt-Drift nicht berechenbar: {_e}")

    try:
        _steam_cutover_dt = datetime.fromisoformat(STEAM_CUTOVER_UTC.replace("Z", "+00:00"))
    except Exception:
        _steam_cutover_dt = None

    # Freeze/Refresh/Rebuild-Entscheidung lebt modulweit in fixture_pick_state()
    # (Single Source of Truth, testbar) — keine verteilten Closures mehr.

    total_with_picks = 0
    total_no_picks   = 0
    total_frozen     = 0
    total_past       = 0
    total_refreshed  = 0

    wm.setdefault("upsetScores", {})

    for gkey, gdata in groups.items():
        teams_map = {t["id"]: t for t in gdata.get("teams", [])}

        for fx in gdata.get("fixtures", []):
            pick_key = f"{gkey}-{fx['matchday']}-{fx['home']}-{fx['away']}"
            fx_date  = fx["date"]

            # Wetter pro Fixture pipen → Renderer-Pille (_weatherPill) wird endlich
            # sichtbar. Slug-Match wie generate_wm_match_pages.py es baut:
            # "wm-{home_lc}-vs-{away_lc}-{date}". Defensiv: nur wenn forecast da.
            if weather_data:
                slug = f"wm-{fx['home'].lower()}-vs-{fx['away'].lower()}-{fx_date}"
                w_entry = weather_data.get(slug) or {}
                if w_entry.get("forecastAvailable") and w_entry.get("tempMax") is not None:
                    # FIX 13.06.2026: Card-Pille zeigt die echte Anpfiff-Temperatur
                    # (tempAtKickoff), nicht das Tagesmax — sonst stand z.B. bei QAT-SUI
                    # „34°C" obwohl es zum Mittags-Anpfiff ~26°C sind. Fallback tempMax.
                    _temp_disp = w_entry.get("tempAtKickoff")
                    if _temp_disp is None:
                        _temp_disp = w_entry.get("tempMax")
                    fx["weather"] = {
                        "temp":      _temp_disp,
                        "tempMax":   w_entry.get("tempMax"),
                        "tempMin":   w_entry.get("tempMin"),
                        "condition": (w_entry.get("condition") or "").lower(),
                        "icon":      w_entry.get("icon"),
                        "windKph":   w_entry.get("windKmh"),
                        "precipMm":  w_entry.get("precipMm"),
                    }

            # Upset Score für jedes Fixture berechnen (immer, auch ohne Picks)
            elo_h = teams_map.get(fx["home"], {}).get("elo")
            elo_a = teams_map.get(fx["away"], {}).get("elo")
            if elo_h and elo_a:
                gap = abs(elo_h - elo_a)
                us  = (9 if gap < 50 else 7 if gap < 100 else 6 if gap < 150
                       else 4 if gap < 200 else 2 if gap < 300 else 1)
                wm["upsetScores"][pick_key] = us

            # ── Freeze/Refresh/Rebuild-Entscheidung (Single Source of Truth) ──
            # fixture_pick_state() kapselt die gesamte Logik (Fix 15.06.2026, Lucas):
            #   past           → unangetastet
            #   kickoff_passed → nur tracken, nie (neu) bauen
            #   refresh        → veröffentlicht (Anpfiff ≤ Cutover) + Pick da: Märkte/Quoten
            #                    reuse, aber Signale/Conviction neu (T-1h lineup_signal fließt
            #                    in Conviction + Bayesian-Ledger, Pick bleibt pre-kickoff stabil)
            #   rebuild        → künftig ODER heute Post-Cutover (ESP abends, BEL): Steam neu.
            # Vorher fror ein `fx_date == today`-Gate auch die heutigen Post-Cutover-Spiele
            # ein. Jetzt entscheidet nur die Anpfiff-Zeit gegen STEAM_CUTOVER.
            existing_pk = wm["picks"].get(pick_key)
            state = fixture_pick_state(
                fx, existing_pk is not None, today, now_dt, _steam_cutover_dt
            )
            if state == "past":
                total_past += 1
                continue
            if state == "kickoff_passed":
                if existing_pk is not None:
                    total_frozen += 1
                continue

            refresh_existing = (state == "refresh")
            if refresh_existing:
                new_picks = existing_pk

            if not refresh_existing:
                # ── STEAM-ENGINE als Pick-Quelle (Umstellung 14.06.2026) ──────
                # Lucas: alte Edge/Poisson-Picks komplett killen, neue Cards = Steam.
                # Nicht-eingefrorene (künftige) Spiele bekommen genau EINEN Steam-Pick
                # aus dem Pinnacle-Move; die gepostete Vergangenheit/heute+morgen bleibt
                # via Freeze (oben) unangetastet. Der alte generate_picks_for_fixture
                # bleibt im Code (Referenz/Tests), wird aber für neue Picks nicht mehr
                # aufgerufen.
                new_picks = generate_steam_picks_for_fixture(
                    fx, mkt.get(f"{fx['home']}-{fx['away']}", {}), today,
                    drift=_steam_drift,
                )

            # ── Signal-Engine: jedem Pick die signals[] Liste anhängen ────
            # Modulare Sharp-Signal-Adjustments (sharp_signals/). Jede Iteration
            # ruft alle aktiven Signale auf, sammelt scores + evidence pro Pick.
            # Bayesian-Weight-Update läuft post-resolve via update_signal_weights.py.
            try:
                from sharp_signals.registry import evaluate_signals
                ha_key = f"{fx['home']}-{fx['away']}"

                # ── Incentive-Signal-Inputs: group_id + standings + team_elo +
                # venue-id + match-date. Werden in sig_ctx gepackt damit
                # incentive_signal seine Komponenten A/B/C/D füllen kann.
                # Wenn Felder fehlen (Pre-Tournament, fehlende Standings) liefert
                # das Signal None — kein Crash, kein false-positive.
                _team_elo_map = {}
                for _g, _gd in groups.items():
                    for _t in _gd.get("teams", []):
                        _tid = _t.get("id")
                        _elo = _t.get("elo")
                        if _tid and isinstance(_elo, (int, float)):
                            _team_elo_map[_tid] = float(_elo)

                # Venue-Name → venue_id (für wm_venues.json Lookup)
                _venue_id = _wm_venue_id_from_name(fx.get("venue"))
                # Venue-Höhe für altitude_signal (09.06.2026)
                _venue_altitude_m = 0
                try:
                    if _venue_id and isinstance(wm.get("_venues_cache"), dict):
                        _venue_altitude_m = int(wm["_venues_cache"].get(_venue_id, {}).get("altitude_m") or 0)
                    elif _venue_id:
                        import json as _json, os as _os
                        _vpath = _os.path.join(_os.path.dirname(WM_FILE), "wm_venues.json")
                        if _os.path.exists(_vpath):
                            with open(_vpath, encoding="utf-8") as _vf:
                                _vraw = _json.load(_vf)
                            _venues = (_vraw.get("venues") or _vraw) if isinstance(_vraw, dict) else {}
                            wm["_venues_cache"] = _venues
                            _venue_altitude_m = int(_venues.get(_venue_id, {}).get("altitude_m") or 0)
                except Exception:
                    _venue_altitude_m = 0

                sig_ctx = {
                    "matchKey":     ha_key,
                    "home_id":      fx["home"],
                    "away_id":      fx["away"],
                    "matchday":     fx["matchday"],
                    "odds_history": odds_history.get(ha_key, []) if odds_history else [],
                    "odds_snapshot": mkt.get(ha_key, {}),
                    "poly_snapshot": poly_snapshots.get(ha_key, {}),
                    "travel":       travel_data,
                    "injuries":     injuries,
                    "form":         form,
                    "h2h":          h2h_data.get(ha_key, {}),
                    "xg_stats":         xg_stats,
                    "lineups":          lineups_data,
                    "squads":           wm.get("squads", {}),
                    "apif_predictions": apif_predictions_data,
                    "weather":          weather_data,
                    "venue":            fx.get("venue"),
                    "venue_altitude_m": _venue_altitude_m,   # für altitude_signal
                    "kickoff_time":     fx.get("time"),   # CEST/Wien lokale Zeit
                    "snapshot_ts":      None,   # → evaluate_signals nutzt now()
                    # incentive_signal-Inputs:
                    "group_id":           gkey,
                    "standings":          wm.get("standings") or {},
                    "team_elo":           _team_elo_map,
                    "current_venue_id":   _venue_id,
                    "current_match_date": fx.get("date"),
                    # next_match_date (KO-Phase) — heute leer, kommt mit live K.O.-Auslosung
                    "next_match_date":    fx.get("next_match_date"),
                }
                for p in new_picks:
                    # Idempotenz (Match-Day-Refresh): Engine-Verdict-Overrides immer
                    # vom Basis-Verdict neu anwenden, nicht auf einem bereits
                    # überschriebenen Verdict aufsetzen. Beim ersten Mal Basis merken.
                    if "baseVerdict" not in p:
                        p["baseVerdict"] = p.get("verdict")
                    else:
                        p["verdict"] = p["baseVerdict"]
                        p.pop("downgradedReason", None)
                        p.pop("pickTriggerReason", None)
                        p.pop("modelHallucinationWarning", None)
                    sig_out = evaluate_signals(p, sig_ctx)
                    # Conviction-Score läuft AUCH wenn signals=[] (Modell-Sanity + Sharp-Move
                    # können unabhängig Punkte geben — Fix 09.06.2026)
                    if sig_out["signals"]:
                        p["signals"] = sig_out["signals"]
                        p["signalAdjustmentPP"] = sig_out["combined_score_pp"]
                        p["signalCountPos"] = sig_out["n_positive_signals"]
                        p["signalCountNeg"] = sig_out["n_negative_signals"]

                        # ── Edge-Adjustment Integration ─────────────────
                        # Echter Edge (model vs market) wird um Engine-Output
                        # justiert. Damit kann der Renderer einen "echten" Edge
                        # nach Engine-Korrektur zeigen.
                        if isinstance(p.get("edgePP"), (int, float)):
                            p["effectiveEdgePP"] = round(p["edgePP"] + sig_out["combined_score_pp"], 1)

                        # ── Verdict-Override durch Engine ───────────────
                        # Regel 1: BET → ABWÄGEN wenn Netto-Adjustment ≤ -3pp
                        #   (Engine warnt deutlich gegen den Pick)
                        # Regel 2: BET → ABWÄGEN wenn weniger als MIN_POSITIVE_SIGNALS
                        #   positive Signale (kein quantifizierbarer Grund für BET)
                        # Anti-Drift-Fix 09.06.2026:
                        # Regel 3: BET ODER ABWÄGEN → SKIP wenn Adjustment ≤ -5pp
                        #   (massive Engine-Warnung — auch für saferAlt-Picks die als
                        #   ABWÄGEN starten. Vorher: nur BET-Picks wurden downgraded,
                        #   ABWÄGEN-SaferAlts ignorierten Engine-Warnung komplett.
                        #   Konkret-Beispiel: AUT-JOR Pick X2 mit Engine -3.5pp.)
                        # Regel 4: BET → ABWÄGEN wenn CLV ≤ -3pp (Markt bewegt sich
                        #   deutlich gegen unseren Pick — starkes Anti-Signal).
                        MIN_POSITIVE_SIGNALS = 2
                        ENGINE_DOWNGRADE_PP   = -3.0
                        ENGINE_SKIP_PP        = -5.0
                        CLV_NEG_DOWNGRADE_PP  = -3.0
                        adj   = sig_out["combined_score_pp"]
                        n_pos = sig_out["n_positive_signals"]
                        clv_pp = p.get("clvPP")
                        if p.get("verdict") in ("BET", "ABWÄGEN"):
                            # Regel 3 zuerst (härteste): vollständiges SKIP
                            if adj <= ENGINE_SKIP_PP:
                                p["verdict"] = "BEOBACHTEN"
                                p["downgradedReason"] = (
                                    f"Engine warnt massiv: Signal-Adjustment {adj:+.1f}pp "
                                    f"≤ {ENGINE_SKIP_PP}pp — Pick wird ausgeblendet"
                                )
                            elif p.get("verdict") == "BET":
                                if adj <= ENGINE_DOWNGRADE_PP:
                                    p["verdict"] = "ABWÄGEN"
                                    p["downgradedReason"] = (
                                        f"Engine warnt: Signal-Adjustment {adj:+.1f}pp "
                                        f"≤ {ENGINE_DOWNGRADE_PP}pp Schwelle"
                                    )
                                elif n_pos < MIN_POSITIVE_SIGNALS:
                                    p["verdict"] = "ABWÄGEN"
                                    p["downgradedReason"] = (
                                        f"Engine: nur {n_pos} positive Signal(e), "
                                        f"Mindest-Threshold {MIN_POSITIVE_SIGNALS} für BET"
                                    )
                                elif (isinstance(clv_pp, (int, float))
                                      and clv_pp <= CLV_NEG_DOWNGRADE_PP):
                                    p["verdict"] = "ABWÄGEN"
                                    p["downgradedReason"] = (
                                        f"Markt bewegt sich gegen Pick (CLV {clv_pp:+.1f}pp) — "
                                        f"Pinnacle sieht Pick schwächer als bei Eröffnung"
                                    )

                    # ── Conviction-Score (Phase 1, 09.06.2026 — läuft IMMER) ──
                    # Bewertet Pick-Qualität 0-10. Auch wenn signals=[] (z.B. AH-Picks
                    # die viele Outcome-Signale nicht treffen) gibt Modell-Sanity +
                    # Sharp-Move Punkte.
                    try:
                        from conviction_score import compute_conviction_score
                        conv = compute_conviction_score(p, sig_out, sig_ctx)
                        p["convictionScore"]   = conv["score"]
                        p["convictionVerdict"] = conv["verdict"]
                        p["convictionLabel"]   = conv["label"]
                        p["convictionFamilies"] = conv["family_scores"]
                        if conv.get("sharp_move") and conv["sharp_move"].get("triggered"):
                            p["sharpMoveActive"] = True
                            p["sharpMoveDetails"] = conv["sharp_move"]
                        if conv.get("opening_movement"):
                            p["openingMovement"] = conv["opening_movement"]

                        # Steam-Picks reifen via Conviction zu BET. WM-Schwelle niedriger
                        # als Liga (weniger Spiele) — STEAM_BET_THRESHOLD aus Config-Profil.
                        # Nicht-Steam (Altpfad) bleibt bei 8. Disziplin bleibt: BET braucht
                        # Move + zusätzliche Signal-Bestätigung, nur die Schwelle ist profil-abh.
                        _conv_threshold = (STEAM_BET_THRESHOLD
                                           if p.get("source") == "steam" else 8)
                        if (p.get("verdict") == "ABWÄGEN"
                                and conv["score"] >= _conv_threshold
                                and not p.get("downgradedReason")):
                            p["verdict"] = "BET"
                            p["pickTriggerReason"] = (
                                f"Conviction {conv['score']}/10 (≥{_conv_threshold}) — "
                                f"Move + Signale bestätigen den Pick"
                            )
                        elif p.get("verdict") == "BET":
                            p["pickTriggerReason"] = "Edge-getrieben"

                        if (p.get("verdict") == "BET"
                                and conv["score"] < 4):
                            p["modelHallucinationWarning"] = (
                                f"Edge gegen Pinnacle vorhanden, aber Conviction nur "
                                f"{conv['score']}/10 — Signale stützen Pick wenig"
                            )
                    except Exception as conv_err:
                        print(f"  ⚠️  Conviction-Score crashed: {conv_err}")
            except Exception as e:
                print(f"  ⚠️  Signal-Engine crashed für {fx['home']}-{fx['away']}: {e}")

            # Immer überschreiben — auch leere Liste löscht veraltete Picks
            wm["picks"][pick_key] = new_picks

            if refresh_existing:
                total_refreshed += 1

            if new_picks:
                total_with_picks += 1
                _tag = " ↻ Signal-Refresh" if refresh_existing else ""
                print(f"  ✅ {fx['home']} vs {fx['away']} (ST{fx['matchday']}, {fx_date}): "
                      f"{len(new_picks)} Pick(s){_tag}")
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
          f"{total_refreshed} Signal-Refresh (pre-kickoff) · "
          f"{total_frozen} eingefroren (post-kickoff) · "
          f"{total_past} vergangen")

    # ── AH-Linien-Dedup über ALLE Spiele (Final-Pass, 14.06.2026, Lucas) ──────
    # Pro Seite+Vorzeichen nur EINE Handicap-Linie („AH Auswärts +0.5" UND „+0.75"
    # sind redundant — eine Cover-Linie reicht). Läuft hier am Ende, damit es AUCH
    # heutige Signal-Refresh-/eingefrorene Spiele erfasst (Builder wird da übersprungen).
    # Beste Edge behalten (Tie → niedrigere Quote = sicherer), Rest trackingExcluded.
    _VRANK = {"BET": 0, "ABWÄGEN": 1, "BEOBACHTEN": 2}
    for _plist in (wm.get("picks") or {}).values():
        if not isinstance(_plist, list):
            continue
        _grp: dict = {}
        for _p in _plist:
            # ALLE Verdicts (auch BEOBACHTEN!) — sonst flutet die BEOBACHTEN-AH-Leiter
            # (+0.5…+2.75) das Tracking (Lucas „wild", IRQ-NOR). SKIP bleibt eh unsichtbar.
            if _p.get("trackingExcluded") or _p.get("boldAlt") or _p.get("verdict") == "SKIP":
                continue
            _m = re.match(r"(AH (?:Heim|Auswärts) [+−])", _p.get("market") or "")
            if _m:
                _grp.setdefault(_m.group(1), []).append(_p)
        for _members in _grp.values():
            if len(_members) <= 1:
                continue
            # Handlungsrelevanteste behalten: BET > ABWÄGEN > BEOBACHTEN, dann höchste Edge.
            _members.sort(key=lambda x: (_VRANK.get(x.get("verdict"), 3),
                                         -(x.get("edgePP") or 0), (x.get("odds") or 99)))
            for _extra in _members[1:]:
                _extra["trackingExcluded"] = True
                _extra["dedupAHLine"] = True

    # ── Riskanter-Hero-ohne-Safe-Variante → ganzes Spiel auf Beobachtung (14.06.2026) ──
    # Repliziert die Renderer-Demotion IN DEN DATEN, damit ALLE Konsumenten (Card,
    # Tracking, Telegram, TikTok) einig sind. Vorher demotete nur der Dashboard-Renderer
    # → CIV-ECU „AH Heim −0.5 @3.55" ging trotzdem als ABWÄGEN ins Telegram (Lucas-Befund).
    # Hero-Wahl = gleiche Sortierung wie Renderer: saferAlt zuerst, dann BET>ABWÄGEN,
    # dann Conviction, dann Edge. Hero riskant (Quote >3.0 ODER AH-Favorit ≤ −1.5) UND
    # ohne sichere Alternative → alle Live-Picks des Spiels trackingExcluded.
    _VR2 = {"BET": 0, "ABWÄGEN": 1}
    _AHF = re.compile(r"AH (?:Heim|Auswärts) −([\d.]+)")
    for _plist in (wm.get("picks") or {}).values():
        if not isinstance(_plist, list):
            continue
        _live = [p for p in _plist
                 if not p.get("trackingExcluded") and not p.get("boldAlt")
                 and p.get("verdict") in ("BET", "ABWÄGEN")]
        if not _live:
            continue
        _hero = sorted(_live, key=lambda p: (
            0 if p.get("saferAltFor") else 1,
            _VR2.get(p.get("verdict"), 2),
            -(p.get("convictionScore") or 0),
            -(p.get("edgePP") or 0),
        ))[0]
        _ahm = _AHF.search(_hero.get("market") or "")
        # Steam-Picks leiten die AH-Linie bewusst auf eine SICHERE Quote ab (1,4-1,95) →
        # die Linien-Höhe (−1,5/−2) ist hier kein Risiko, nur eine Quote > 3,0 wäre eins.
        _is_steam = _hero.get("source") == "steam"
        _risky = (_hero.get("odds") or 0) > 3.0 or (
            not _is_steam and _ahm and float(_ahm.group(1)) >= 1.5)
        if _risky and not _hero.get("saferAltFor") and not _hero.get("boldAlt"):
            for p in _live:
                p["trackingExcluded"] = True
                p["demotedRiskyGame"] = True

    wm["_meta"] = wm.get("_meta", {})
    wm["_meta"]["picksUpdatedAt"] = datetime.now(timezone.utc).isoformat()

    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    print("✅ wm2026-data.json gespeichert.")


if __name__ == "__main__":
    main()
