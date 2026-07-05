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

import cocobet_dataset as D

BASE    = Path(__file__).parent
# Dataset-Modus (Single Source: cocobet_dataset). COCOBET_DATASET=liga → läuft auf liga-data.json
# mit Liga-Sibling-Dateien (liga_*.json); fehlende → graceful kein-Signal (kein WM-Datenleck).
# KO/Quali-Schritte werden für Liga gegatet. Default bleibt WM (unverändert).
IS_LIGA      = D.is_liga()
WM_FILE      = D.data_file()
_FILE_PREFIX = "liga_" if IS_LIGA else "wm_"
_HISTORY_FILE = D.file("wm2026-odds-history.json", "liga-odds-history.json").name
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
# Steam-Confirmed-Sichtbarkeit (17.06.2026, Lucas): Ein Pick, dessen Linie stark in
# unsere Richtung gelaufen ist (clvPP ≥ N), ist ein BESTÄTIGTER Steam-Move. Auch wenn
# die Karten-Edge dadurch auf ~0 konvergiert ist (Wert am Buch weg), bleibt er auf der
# Card sichtbar — der Move IST das Signal (auf Poly wird er geritten). Sonst verschwindet
# genau die Wette, die unsere These bestätigt hat.
STEAM_CONFIRM_PP = _cfg("edge", "steam_confirm_pp",      5.0)

# Steam-Engine (Lucas' Modell): Picks pro Card + Conviction-BET-Schwelle.
# WM lockerer als Liga (weniger Spiele) — Liga-Profil setzt steam_bet_threshold höher.
MAX_STEAM_PICKS_PER_CARD = _cfg("conviction_score", "max_steam_picks_per_card", 3)
STEAM_BET_THRESHOLD      = _cfg("conviction_score", "steam_bet_threshold",      6)
# Season-Opener-Dämpfung (01.07.2026, Lucas): die ersten Liga-Spieltage laufen auf cross-season Form/
# H2H/xG. Die bleiben VOLL gewichtet (tragen echtes Signal) — aber die Gesamt-Conviction bekommt eine
# kleine Vorsicht (−1), solange die Datenbasis dünn ist. Nur Liga/MLS (is_liga), nur MD ≤ N. Verhindert
# v.a. voreilige ABWÄGEN→BET-Upgrades in verrauschter Anfangsphase. Tunebar pro Profil.
EARLY_SEASON_MATCHDAYS          = _cfg("conviction_score", "early_season_matchdays", 3)
EARLY_SEASON_CONVICTION_PENALTY = _cfg("conviction_score", "early_season_conviction_penalty", 1.0)
# Variante A (20.06.2026): Quote der gesteamten Seite über diesem Wert = Longshot → kein Trigger
# (z.B. Haiti 51→22 gg. Brasilien → keine X2-Nonsens-Karte). Mainline-Steam bleibt unberührt.
STEAM_MAX_TRIGGER_ODDS   = _cfg("steam", "max_trigger_odds", 6.0)

# ── Lern-Ebene 2: Segment-Kalibrierung (20.06.2026, Lucas) ───────────────────────────────
# Sehr kleiner, gedeckelter Conviction-Nudge je Pick-Segment (steam/model) aus der prozess-
# justierten Performance (pick_calibration.json). Erst ab CAL_MIN_PICKS aktiv (WM 50, bewusst
# niedriger Effekt — selbst 50 ist dünn). Liga später hochschraubbar (Config-Profil).
CAL_ENABLED   = _cfg("pick_calibration", "enabled",       True)
CAL_MIN_PICKS = _cfg("pick_calibration", "min_picks",     50)
CAL_MIN_SEG_N = _cfg("pick_calibration", "min_segment_n", 15)
CAL_SCALE     = _cfg("pick_calibration", "scale",         5.0)
CAL_MAX_NUDGE = _cfg("pick_calibration", "max_nudge",     0.5)
try:
    _PICK_CALIBRATION = json.loads((BASE / "pick_calibration.json").read_text(encoding="utf-8"))
except Exception:
    _PICK_CALIBRATION = {}


def _calibration_nudge(pick: dict) -> float:
    """Kleiner, gedeckelter Conviction-Nudge aus der Segment-Performance (prozess-justiert).
    0.0 wenn deaktiviert, zu wenig Gesamt-Sample (<min_picks) oder Segment zu dünn (<min_seg_n)."""
    if not CAL_ENABLED:
        return 0.0
    meta = _PICK_CALIBRATION.get("_meta") or {}
    if (meta.get("totalN") or 0) < CAL_MIN_PICKS:
        return 0.0
    seg = "steam" if pick.get("source") == "steam" else "model"
    s = (_PICK_CALIBRATION.get("segments") or {}).get(seg) or {}
    if (s.get("n") or 0) < CAL_MIN_SEG_N:
        return 0.0
    delta = s.get("delta") or 0.0
    return round(max(-CAL_MAX_NUDGE, min(CAL_MAX_NUDGE, delta * CAL_SCALE)), 2)

# Safer-Line-Ableitung Phase 1 (17.06.2026, Lucas): ein riskanter Steam-Pick (Über 3.5,
# Heimsieg) wird auf die nächst-sicherere Linie als WETTE umgelegt — der Move bleibt die
# These. ABER nur wenn die sichere Linie ihre Quote ≥ SAFE_LINE_MIN_ODDS hält; sonst (zu
# kurz, kein Reiz) bleibt's bei der Original-Linie. snap hat echte Quoten für alle Ziele.
SAFE_LINE_MIN_ODDS = _cfg("edge", "safe_line_min_odds", 1.35)
# Frische-Modell / Reverser-Guard (18.06.2026, Lucas): der „Move seit Eröffnung" ist oft
# alter Drift. Was zählt ist die FRISCHE Bewegung. Statt eines fixen Uhr-Fensters (24h ist
# willkürlich — bei 30-Min-Snaps kann der frische Move auch 5 Tage vor Anpfiff passieren)
# erkennen wir den LETZTEN Bewegungs-Abschnitt (latest leg): die dichte Pinnacle-Reihe rück-
# wärts bis die Richtung kippt (Pivot), Netto-Move SEIT dem Pivot. Drei Zustände:
#   BESTÄTIGT  frische Leg ≥ +CONFIRM in Pick-Richtung  → Geld läuft weiter für uns
#   DRIFT      |frische Leg| < Schwellen                → Move ruht / nur alte Drift
#   REVERSER   frische Leg ≤ −REVERSER gegen Pick       → frisches Geld dreht gegen uns
# (Analyse: CZE-ZAF +1.9 Eröffnung aber Leg −3.5; JOR-DZA +4.4 aber Leg −6.1.)
REVERSER_THRESHOLD_PP  = _cfg("edge", "reverser_threshold_pp",  3.0)   # Eltern zurückstufen (warn)
REVERSER_FLIP_PP       = _cfg("edge", "reverser_flip_pp",       5.0)   # höhere Hürde: Gegen-Konter ableiten
CONFIRM_THRESHOLD_PP   = _cfg("edge", "confirm_threshold_pp",   3.0)
LEG_NOISE_PP           = _cfg("edge", "leg_noise_pp",           0.4)
# Dünn-Daten-Guard: ein vertrauenswürdiges reverse/confirm braucht genug DICHTE Snaps. Die
# Leg-Erkennung stoppt zudem an großen Zeitlücken (alte, spärliche Vor-Turnier-Daten) — sonst
# läuft der Pivot über 19-Tage-„Legs" (PAN-CRO-Phantom). Persistenz für den Flip: min Snaps.
MIN_LEG_SNAPS          = _cfg("edge", "min_leg_snaps",          3)
MAX_LEG_GAP_H          = _cfg("edge", "max_leg_gap_h",          96)   # nur echte Mehr-Tage-Lücken (De-Vig erledigt die Phantome)
MIN_FLIP_SNAPS         = _cfg("edge", "min_flip_snaps",         4)
# Zeitbewusster BET-Lebenszyklus (18.06.2026, Lucas): ENTER BET nur bei FRISCHEM Move
# (letzter echter Move ≤ Hürde), HOLD bis ein Reverser kommt (auch wenn der Move ruht),
# EXIT bei Reverser. Verhindert dass ein alter Drift-Move neu BET auslöst.
BET_ENTRY_HURDLE_H     = _cfg("edge", "bet_entry_hurdle_h",     48)
# Aktualität: misst NICHT welcher Move zählt (das macht die latest leg), sondern ob die
# Linie ÜBERHAUPT noch aktiv ist. Ein großer Move vor 5 Tagen, seither flach, ist „bestätigt"
# der Form nach — aber alter Drift, nicht frisch. Liegt der letzte echte Move länger zurück,
# fällt ein Für-Pick-Leg auf DRIFT zurück (Reverser bleibt Reverser, egal wie alt).
STALE_AFTER_H          = _cfg("edge", "stale_after_h",          72)
_STEAM_SAFER_MAP = {
    "Über 3.5 Tore":  ("o25",  "Über 2.5 Tore"),
    "Über 2.5 Tore":  ("o15",  "Über 1.5 Tore"),
    "Unter 1.5 Tore": ("u25",  "Unter 2.5 Tore"),
    "Unter 2.5 Tore": ("u35",  "Unter 3.5 Tore"),
    "Heimsieg":       ("dc1X", "Doppelte Chance — 1X"),
    "Auswärtssieg":   ("dcX2", "Doppelte Chance — X2"),
}
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


# Markt → (Pick-Seiten-Key, Gegen-Key) für O/U + BTTS. Modul-Konstante (von _steam_model_odds &
# Co. genutzt; 26.06.2026 beim Entfernen des toten Elo-Pfads hier wieder einsortiert).
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
    # Doppelte Chance (17.06.2026 für Safer-Line-Ableitung): fair aus de-viggtem 1X2.
    if market in ("Doppelte Chance — 1X", "Doppelte Chance — X2", "Doppelte Chance — 12"):
        hw, dr, aw = snap.get("hw"), snap.get("dr"), snap.get("aw")
        if hw and dr and aw and min(hw, dr, aw) > 1.0:
            ph, pd, pa = devig_1x2(hw, dr, aw)
            p = {"Doppelte Chance — 1X": ph + pd,
                 "Doppelte Chance — X2": pd + pa,
                 "Doppelte Chance — 12": ph + pa}[market]
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
        "softOpen": pick.get("soft_open"), "softNow": pick.get("soft_now"),
        "entryBook": pick["book"], "entryOdd": round(odds, 2),
        "lateEntry": bool(pick.get("lateEntry")), "steamDerived": bool(pick.get("derived")),
        "softConfirmed": soft_confirmed, "softFollowPP": soft_follow,
        "ahLine": pick.get("ah_line"),
    }


_REVERSER_KEY = {
    "heimsieg": "hw", "auswärtssieg": "aw", "auswartssieg": "aw", "unentschieden": "dr",
    "ah heim": "hw", "ah auswärts": "aw", "ah auswarts": "aw",
    "doppelte chance — 1x": "hw", "doppelte chance — x2": "aw",
    "über 1.5": "o15", "über 2.5": "o25", "über 3.5": "o35",
    "unter 1.5": "u15", "unter 2.5": "u25", "unter 3.5": "u35",
    "beide teams treffen — ja": "bttsY", "beide teams treffen — nein": "bttsN",
}


def _reverser_key(market):
    m = (market or "").lower()
    for frag, key in _REVERSER_KEY.items():
        if m.startswith(frag) or frag in m:
            return key
    return None


# De-Vig-Geschwister je Key: Bewegung soll die ECHTE Wkt-Änderung messen, nicht den
# Margin-Drift von Pinnacle (engt/weitet die Marge → 1/Quote bewegt sich ohne Wkt-Move).
_DEVIG_SIBLINGS = {
    "hw": ["hw", "dr", "aw"], "dr": ["hw", "dr", "aw"], "aw": ["hw", "dr", "aw"],
    "o15": ["o15", "u15"], "u15": ["o15", "u15"],
    "o25": ["o25", "u25"], "u25": ["o25", "u25"],
    "o35": ["o35", "u35"], "u35": ["o35", "u35"],
    "bttsY": ["bttsY", "bttsN"], "bttsN": ["bttsY", "bttsN"],
}


def _devigged_implied(snap, key):
    """De-viggte implizite Wkt für key aus den Geschwister-Quoten des Snapshots.
    Fehlen die Geschwister → roher 1/Quote-Fallback (ehrlich, nur ohne Margin-Korrektur)."""
    try:
        v = float(snap.get(key))
    except (TypeError, ValueError):
        return None
    if not v or v <= 1.0:
        return None
    sibs = _DEVIG_SIBLINGS.get(key)
    if sibs:
        denom, ok = 0.0, True
        for s in sibs:
            try:
                sv = float(snap.get(s))
            except (TypeError, ValueError):
                ok = False
                break
            if not sv or sv <= 1.0:
                ok = False
                break
            denom += 1.0 / sv
        if ok and denom > 0:
            return (1.0 / v) / denom
    return 1.0 / v


def _pinn_implied_series(hist, key):
    """Sortierte [(ts, de-viggte implizite Wkt)] aus bk=='pinnacle'-Snaps für key.
    Höhere implizite Wkt = FÜR den Pick (niedrigere Quote)."""
    snaps = []
    for s in hist or []:
        if not isinstance(s, dict) or s.get("bk") != "pinnacle":
            continue
        t = s.get("ts")
        if not t:
            continue
        imp = _devigged_implied(s, key)
        if imp is None:
            continue
        try:
            ti = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        except Exception:
            continue
        snaps.append((ti, imp))
    snaps.sort()
    return snaps


def _latest_leg_move_pp(series, noise_pp, max_gap_h=None):
    """Netto-Bewegung (pp implizite Wkt) des JÜNGSTEN zusammenhängenden Abschnitts.
    series = [(ts, implied)] chronologisch. Läuft rückwärts vom letzten Snap bis die Richtung
    kippt (Pivot) ODER eine Zeitlücke > max_gap_h auftritt (dann endet der dichte Abschnitt —
    schützt vor Legs über alte, spärliche Daten). + = FÜR den Pick, − = gegen.
    Gibt (movePP, pivot_idx, last_move_idx) — last_move_idx = Index des jüngsten echten Moves."""
    n = len(series)
    if n < 2:
        return None, None, None
    noise = noise_pp / 100.0
    probs = [p for _, p in series]
    ts    = [t for t, _ in series]

    def _gap_too_big(a, b):  # Stunden zwischen Snap a-1 und a
        if max_gap_h is None:
            return False
        return (ts[a] - ts[b]).total_seconds() / 3600.0 > max_gap_h

    i = n - 1
    # Richtung des jüngsten Nicht-Rausch-Schritts (stoppt an großer Lücke)
    dirn, j = 0, i
    while j > 0:
        if _gap_too_big(j, j - 1):
            break
        d = probs[j] - probs[j - 1]
        if abs(d) >= noise:
            dirn = 1 if d > 0 else -1
            break
        j -= 1
    if dirn == 0:                       # alles Rauschen → keine echte Bewegung
        return 0.0, i, i
    # rückwärts solange die Bewegung in dirn weiterläuft (kleines Gegen-Rauschen toleriert)
    # und keine große Zeitlücke kommt
    pivot, k = j - 1, j - 1
    while k > 0:
        if _gap_too_big(k, k - 1):
            break
        d = probs[k] - probs[k - 1]
        if d * dirn >= -noise:
            pivot, k = k - 1, k - 1
        else:
            break
    return round((probs[i] - probs[pivot]) * 100, 1), pivot, j


def analyze_recent_move(hist, market):
    """Frische-Analyse eines Picks aus der dichten Pinnacle-History.
    Returns {movePP, legHours, state} oder None (Markt nicht mappbar / Key fehlt in History).
    state ∈ {'confirm','drift','reverse'} aus dem letzten Bewegungs-Abschnitt (latest leg)."""
    key = _reverser_key(market)
    if not key:
        return None
    series = _pinn_implied_series(hist, key)
    if len(series) < 2:
        return None
    move_pp, pivot, last_move_idx = _latest_leg_move_pp(series, LEG_NOISE_PP, MAX_LEG_GAP_H)
    if move_pp is None:
        return None
    leg_snaps = len(series) - pivot          # Snaps im jüngsten Abschnitt (Dichte/Persistenz)
    leg_h = round((series[-1][0] - series[pivot][0]).total_seconds() / 3600.0, 1)
    # Aktualität: Stunden seit dem letzten ECHTEN (Nicht-Rausch) Move
    last_move_h = round((series[-1][0] - series[last_move_idx][0]).total_seconds() / 3600.0, 1)
    # Dünn-Daten-Guard: zu wenige dichte Snaps → kein vertrauenswürdiges reverse/confirm
    # (dann „drift" = neutral, kein Demote/Konter und keine Confirm-Gutschrift).
    trustworthy = len(series) >= MIN_LEG_SNAPS and leg_snaps >= MIN_LEG_SNAPS
    if move_pp <= -REVERSER_THRESHOLD_PP and trustworthy:
        state = "reverse"                       # Reversal zählt immer, egal wie alt
    elif move_pp >= CONFIRM_THRESHOLD_PP and last_move_h <= STALE_AFTER_H and trustworthy:
        state = "confirm"                       # für uns UND Linie noch aktiv
    else:
        state = "drift"                         # zu klein / alt / zu dünn
    # Flip-Bereitschaft: NUR bei deutlichem Reverser (höhere Schwelle) der über genug Snaps
    # hält → erst dann lohnt die Gegen-Linie (sonst nur warnen, A zurückstufen).
    flip_ready = bool(state == "reverse"
                      and move_pp <= -REVERSER_FLIP_PP
                      and leg_snaps >= MIN_FLIP_SNAPS)
    return {"movePP": move_pp, "legHours": leg_h, "lastMoveH": last_move_h,
            "legSnaps": leg_snaps, "state": state, "flipReady": flip_ready}


def recent_pinn_move_pp(hist, market, window_h=None):
    """Dünner Wrapper (Tests/Altpfad): nur die frische Leg-Bewegung in pp. window_h ignoriert
    (das Modell ist jetzt fenster-frei via latest leg)."""
    a = analyze_recent_move(hist, market)
    return a["movePP"] if a else None


def _derive_safer_steam_line(card, snap):
    """Phase 1 (17.06.2026, Lucas): riskante Steam-Linie → nächst-sicherere Linie als WETTE,
    SOLANGE deren Quote ≥ SAFE_LINE_MIN_ODDS (1.35) bleibt. Sonst (zu kurz) Original behalten.
    Der Steam-Move bleibt als These erhalten (safeThesisMarket/safeThesisOdds + steamOpen/Cur).

    Beispiele: Über 3.5 → Über 2.5 · Heimsieg → Doppelte Chance 1X. Echte Quoten aus snap
    (o25/o15/u25/u35/dc1X/dcX2). Greift NICHT für AH/BTTS (Phase 2 / keine saubere Mapping)."""
    orig_market = card.get("market")
    mapping = _STEAM_SAFER_MAP.get(orig_market)
    if not mapping:
        return card
    key, safe_label = mapping
    safe_odds = snap.get(key)
    if not (isinstance(safe_odds, (int, float)) and safe_odds > 1.0):
        return card  # sichere Linie nicht verfügbar → Original
    safe_odds = round(float(safe_odds), 2)
    orig_odds = card.get("odds") or 0
    # Lucas-Regel: sichere Linie nur nehmen wenn Quote ≥ 1.35 UND echt niedriger als Original.
    if safe_odds < SAFE_LINE_MIN_ODDS or safe_odds >= orig_odds:
        return card
    safe_model = _steam_model_odds(snap, safe_label) or safe_odds
    edge_pp = 0
    if safe_model > 1.0 and safe_odds > 1.0:
        edge_pp = round(((1.0 / safe_model) * MODEL_MARGIN - (1.0 / safe_odds) * 1.03) * 100)
    # Original-Linie als These behalten, sichere Linie wird die Wette.
    card["safeThesisMarket"] = orig_market
    card["safeThesisOdds"]   = round(float(orig_odds), 2)
    card["safeDerived"]      = True
    card["market"]    = safe_label
    card["odds"]      = safe_odds
    card["entryOdd"]  = safe_odds
    card["modelOdds"] = round(safe_model, 3)
    card["edgePP"]    = edge_pp
    card["info"] = (card.get("info", "")
                    + f" · ✅ Sichere Linie abgeleitet: {safe_label} @{safe_odds:g} "
                      f"(These: {orig_market} @{card['safeThesisOdds']:g})")
    return card


# Reverser-Konter: bei frischem Geld GEGEN den Pick die SICHERE Linie auf der jetzt
# favorisierten Gegenseite (nicht der nackte Gegen-Sieg — gespiegelte Safer-Line-Logik).
_REVERSER_COUNTER_MAP = {
    "Heimsieg":             ("dcX2", "Doppelte Chance — X2"),
    "Auswärtssieg":         ("dc1X", "Doppelte Chance — 1X"),
    "Doppelte Chance — 1X": ("dcX2", "Doppelte Chance — X2"),
    "Doppelte Chance — X2": ("dc1X", "Doppelte Chance — 1X"),
    "Über 3.5 Tore":  ("u35", "Unter 3.5 Tore"),
    "Über 2.5 Tore":  ("u35", "Unter 3.5 Tore"),
    "Über 1.5 Tore":  ("u25", "Unter 2.5 Tore"),
    "Unter 1.5 Tore": ("o25", "Über 2.5 Tore"),
    "Unter 2.5 Tore": ("o35", "Über 3.5 Tore"),
    "Unter 3.5 Tore": ("o35", "Über 3.5 Tore"),
}


def _reverser_counter_target(market):
    m = market or ""
    if m in _REVERSER_COUNTER_MAP:
        return _REVERSER_COUNTER_MAP[m]
    if m.startswith("AH Heim"):
        return ("dcX2", "Doppelte Chance — X2")
    if m.startswith("AH Auswärts") or m.startswith("AH Auswarts"):
        return ("dc1X", "Doppelte Chance — 1X")
    return None


def _derive_reverser_counter(parent, snap, move_pp):
    """Bei REVERSER: sichere Gegen-Linie als eigenen Pick (ABWÄGEN, läuft durch die Signal-
    Engine → reift nur via Conviction zu BET, wenn Signale sie tragen). Floor 1.35. None wenn
    Gegen-Linie nicht mappbar/verfügbar oder zu kurz (< Floor → kein Mehrwert, nur Warnung)."""
    tgt = _reverser_counter_target(parent.get("market"))
    if not tgt:
        return None
    key, label = tgt
    odds = snap.get(key)
    if not (isinstance(odds, (int, float)) and odds >= SAFE_LINE_MIN_ODDS):
        return None
    odds = round(float(odds), 2)
    model = _steam_model_odds(snap, label) or odds
    edge_pp = 0
    if model > 1.0 and odds > 1.0:
        edge_pp = round(((1.0 / model) * MODEL_MARGIN - (1.0 / odds) * 1.03) * 100)
    return {
        "market": label, "odds": odds, "modelOdds": round(model, 3),
        "conf": "medium", "verdict": "ABWÄGEN",
        "modSig": 0, "mktSig": 0, "storySig": 0,
        "edgePP": edge_pp, "icon": "↩️",
        "info": (f"↩️ Reverser-Konter zu {parent.get('market')}: frisches Pinnacle-Geld "
                 f"{move_pp:+.1f}pp dreht auf diese Seite — sichere Linie {label} @{odds:g}"),
        "result": None, "clvPP": 0.0, "dataQuality": "steam",
        "lamH": None, "lamA": None, "lamTotal": None,
        "source": "steam", "reverserCounter": True,
        "counterOf": parent.get("market"), "counterMovePP": move_pp,
        "entryBook": parent.get("entryBook", "pinnacle"), "entryOdd": odds,
    }


def _early_season_penalty(fx: dict) -> float:
    """Kleine Conviction-Vorsicht für die ersten Liga-Spieltage einer Saison (01.07.2026, Lucas):
    Form/H2H/xG sind da noch cross-season — bleiben voll gewichtet (Signal ist echt), aber die
    Datenbasis ist dünn → Gesamt-Conviction leicht dämpfen. Nur Liga/MLS (is_liga), nur MD ≤ N."""
    if not D.is_liga():
        return 0.0
    try:
        md = int(fx.get("matchday") or 0)
    except (TypeError, ValueError):
        return 0.0
    if 1 <= md <= EARLY_SEASON_MATCHDAYS:
        return EARLY_SEASON_CONVICTION_PENALTY
    return 0.0


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
                                     max_picks=MAX_STEAM_PICKS_PER_CARD, drift=drift,
                                     min_odds=SAFE_LINE_MIN_ODDS,
                                     max_trigger_odds=STEAM_MAX_TRIGGER_ODDS)
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
        # Phase 1 (17.06.2026): riskante Linie → sichere Linie ableiten (Floor 1.35).
        card = _derive_safer_steam_line(card, snap)
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
    # Rollendes Posted-Fenster (28.06.2026, Lucas): ein BEREITS existierender Pick, dessen Anpfiff
    # heute/morgen ist, wird NICHT mehr umgebaut → Markt-Lock (nur Signale/Conviction refreshen).
    # Sonst durfte ein Pick spät pre-match das Marktziel wechseln (KO ZAF-CAN: Auswärtssieg→Unter,
    # der gewinnende Markt wurde nachträglich „der Pick" → unehrlicher Track-Record). fx_date<=tomorrow
    # ist exakt das Immutability-Fenster aus [[feedback_posted_picks_immutable]].
    if has_pick and fx_date and today:
        try:
            from datetime import date as _date, timedelta as _td
            _tomorrow = (_date.fromisoformat(today) + _td(days=1)).isoformat()
            if fx_date <= _tomorrow:
                return "refresh"
        except Exception:
            pass
    # Launch-Schutz (15.06-Cutover): vor dem Cutover gepostete Spiele bleiben refresh (Fallback).
    if has_pick and cutover_dt is not None and ko is not None and ko <= cutover_dt:
        return "refresh"
    return "rebuild"


_VERDICT_RANK = {"BET": 3, "ABWÄGEN": 2, "BEOBACHTEN": 1, "SKIP": 0}


def _carry_nobet(existing_pk, new_picks, odds_snap, now_iso):
    """NOBET-Karten (23.06.2026, Lucas): ein Markt, der mal BET/ABWÄGEN war und jetzt KEIN echter
    Pick mehr ist (z.B. COL-COD Unter — Edge gekippt), verschwindet nicht lautlos, sondern bleibt
    als verdict='NOBET' mit Begründung in Cards + Tracking. Schatten-Ergebnis setzt der Resolver.
    Zählt NICHT in P&L/Win-Rate/Lernen/Trading (result bleibt None). Nur ex-BET/ABWÄGEN (oder schon
    NOBET) werden behalten — SKIP/BEOBACHTEN nicht. Persistiert über Rebuilds bis Anpfiff."""
    existing_pk = existing_pk or []
    out = list(new_picks or [])
    new_markets = {p.get("market") for p in out if isinstance(p, dict)}
    for old in existing_pk:
        if not isinstance(old, dict):
            continue
        m = old.get("market")
        if not m or m in new_markets:
            continue   # weiterhin echter Pick → kein NOBET
        was_real  = old.get("verdict") in ("BET", "ABWÄGEN")
        was_nobet = old.get("verdict") == "NOBET"
        if not (was_real or was_nobet):
            continue
        nb = dict(old)
        if was_real:
            nb["origVerdict"] = old.get("verdict")
            nb["origOdds"]    = old.get("odds")
            nb["nobetSince"]  = now_iso
        nb["verdict"] = "NOBET"
        nb["result"]  = None
        nb.pop("trackingExcluded", None)
        # Grund ableiten: aktuelle Quote (über _reverser_key-Mapping) vs Original
        cur = None
        try:
            k = _reverser_key(m)
            v = (odds_snap or {}).get(k) if k else None
            cur = float(v) if isinstance(v, (int, float)) else None
        except Exception:
            cur = None
        orig = nb.get("origOdds")
        if isinstance(cur, (int, float)) and isinstance(orig, (int, float)) and cur > orig + 0.01:
            nb["nobetReason"] = f"Edge weg — Linie gegen den Pick gelaufen ({orig:g}→{cur:g})"
        elif isinstance(cur, (int, float)) and isinstance(orig, (int, float)) and cur < orig - 0.01:
            nb["nobetReason"] = f"Quote zu kurz geworden ({orig:g}→{cur:g}) — kein Value mehr"
        else:
            nb["nobetReason"] = "Kein Value mehr — Move ausgelaufen / Konsens konvergiert"
        out.append(nb)
        new_markets.add(m)
    return out


def _dedup_picks_by_market(picks: list) -> list:
    """Genau EINE Karte je (Markt) pro Spiel (23.06.2026, Lucas: PAN-CRO 2× „Beide Teams
    treffen — Ja"). Defensiver Write-Boundary-Dedup gegen Refresh-/Merge-Altlasten. Bei Kollision
    bleibt der stärkere: BET > ABWÄGEN > BEOBACHTEN, dann höhere Conviction, dann höhere Quote.
    Reihenfolge des ersten Auftretens bleibt erhalten."""
    if not isinstance(picks, list) or len(picks) < 2:
        return picks
    best, order = {}, []
    for p in picks:
        if not isinstance(p, dict):
            continue
        m = p.get("market")
        rank = (_VERDICT_RANK.get(p.get("verdict"), 0),
                p.get("convictionScore") or 0, p.get("odds") or 0)
        if m not in best:
            best[m] = (rank, p)
            order.append(m)
        elif rank > best[m][0]:
            best[m] = (rank, p)
    return [best[m][1] for m in order]


def _md3_qual_status(wm: dict, group_id: str, team_id: str) -> dict:
    """Szenario-basierter MD3-Qualifikations-Status (23.06.2026, Lucas — „England braucht Sieg für
    besten Dritten" war Blödsinn, England spielt um Platz 1). Rechnet die 2 verbleibenden Gruppen-
    spiele wirklich durch (3×3 Ausgänge) statt naiv die Max-Punkte ALLER anderen zu summieren
    (die spielen ja gegeneinander → können nicht alle gewinnen). Berücksichtigt Platz 1 + Platz 2,
    nicht nur „bester Dritter". GD-Tiebreak per aktuellem Stand + ±1 je Sieg/Niederlage (Proxy)."""
    st = (wm.get("standings") or {}).get(group_id) or []
    rows = {r.get("team"): r for r in st if r.get("team")}
    if team_id not in rows or len(rows) < 4:
        return {"label": "unknown"}
    teams = list(rows.keys())
    FIN = {"FT", "AET", "PEN", "AWD", "WO"}
    rem = []
    for fx in ((wm.get("groups") or {}).get(group_id) or {}).get("fixtures", []):
        h, a = fx.get("home"), fx.get("away")
        if h in rows and a in rows and \
           str((fx.get("result") or {}).get("status") or "").upper() not in FIN:
            rem.append((h, a))
    involved = {t for g in rem for t in g}
    if len(rem) != 2 or len(involved) != 4 or team_id not in involved:
        return {"label": "unknown"}   # nicht die saubere „2 Spiele übrig"-MD3-Lage
    my_game = next(g for g in rem if team_id in g)
    opp = my_game[1] if my_game[0] == team_id else my_game[0]
    oa, ob = next(g for g in rem if team_id not in g)
    base = {t: (int(rows[t].get("points") or 0), int(rows[t].get("gd") or 0)) for t in teams}

    def _rank(pts, gd):
        order = sorted(teams, key=lambda t: (-pts[t], -gd[t], t))
        return order.index(team_id) + 1

    my_out = {"W": (3, 0, 1), "D": (1, 1, 0), "L": (0, 3, -1)}      # myPts, oppPts, myGdΔ
    ot_out = {"a": (3, 0, 1), "d": (1, 1, 0), "b": (0, 3, -1)}      # oaPts, obPts, oaGdΔ
    ranks_by_my = {"W": [], "D": [], "L": []}
    all_ranks = []
    for mk, (mp, op_, mgd) in my_out.items():
        for _ok, (ap, bp, agd) in ot_out.items():
            pts = {t: base[t][0] for t in teams}
            gd = {t: base[t][1] for t in teams}
            pts[team_id] += mp; pts[opp] += op_; gd[team_id] += mgd; gd[opp] -= mgd
            pts[oa] += ap; pts[ob] += bp; gd[oa] += agd; gd[ob] -= agd
            r = _rank(pts, gd)
            ranks_by_my[mk].append(r)
            all_ranks.append(r)

    locked        = all(r <= 2 for r in all_ranks)
    draw_secures  = all(r <= 2 for r in ranks_by_my["D"])
    win_secures   = all(r <= 2 for r in ranks_by_my["W"])
    win_top2_poss = any(r <= 2 for r in ranks_by_my["W"])
    first_if_win  = any(r == 1 for r in ranks_by_my["W"])
    third_poss    = any(r <= 3 for r in ranks_by_my["W"])
    own_max_pts   = base[team_id][0] + 3

    # Best-Dritter braucht in der 48er-WM realistisch ≥4 Punkte → 3-Pkt-Drittplatzierte = raus.
    third_realistic = third_poss and own_max_pts >= 4
    if locked:
        label = "qualified"
    elif not win_top2_poss and not third_realistic:
        label = "eliminated"
    elif draw_secures:
        label = "leader_can_draw" if first_if_win else "can_draw"
    elif win_secures:
        label = "win_secures_top2"
    elif win_top2_poss:
        label = "must_win_top2"
    elif third_realistic:
        label = "third_chase"
    else:
        label = "eliminated"

    return {"label": label, "current_position": _rank(
                {t: base[t][0] for t in teams}, {t: base[t][1] for t in teams}),
            "current_points": base[team_id][0], "first_if_win": bool(first_if_win),
            "draw_secures": bool(draw_secures)}


def _attach_qualification_states(wm: dict) -> None:
    """Hängt pro MD3-Fixture den szenario-basierten Qualifikations-Status BEIDER Teams ans Fixture
    (fx['qualHome']/fx['qualAway']) — via _md3_qual_status (rechnet die 2 Rest-Spiele durch, achtet
    auf Platz 1+2, nicht nur „bester Dritter"). Der Renderer rendert daraus „wer ist durch / Remis
    reicht / muss für Top 2 gewinnen / …". 23.06.2026, Lucas."""
    standings = wm.get("standings") or {}
    if not standings:
        return
    KEEP = ("label", "current_position", "current_points", "first_if_win", "draw_secures")
    n = 0
    for gk, gd in (wm.get("groups") or {}).items():
        for fx in (gd.get("fixtures") or []):
            if (fx.get("matchday") or 0) < 3:
                continue
            for field, tid in (("qualHome", fx.get("home")), ("qualAway", fx.get("away"))):
                if not tid:
                    continue
                try:
                    stt = _md3_qual_status(wm, gk, tid)
                    if stt.get("label") in (None, "unknown"):
                        continue
                    fx[field] = {k: stt.get(k) for k in KEEP if k in stt}
                    n += 1
                except Exception:
                    continue
    if n:
        print(f"  🎯 Qualifikations-Status an {n} MD3-Team-Slots gehängt (Renderer-Narrativ)")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=== generate_wm_picks.py ===\n")

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    # Gruppentabellen aus beendeten Ergebnissen bauen (17.06.2026): füllt wm["standings"]
    # + wm["thirdRanking"] VOR der Signal-Auswertung → incentive_signal + pressure_index
    # bekommen endlich Daten (waren mangels Tabelle tot). Idempotent, persistiert im Write.
    try:
        import wm_standings as _wmst
        _st = _wmst.apply_to_wm(wm)
        _played = sum(r["played"] for v in _st.values() for r in v) // 2
        print(f"  📊 Standings gebaut: {len(_st)} Gruppen, {_played} Spiele verbucht")
    except Exception as _e:
        print(f"  ⚠️  Standings-Build fehlgeschlagen: {_e}")

    # KO-Bracket + Quali-Status sind WM-spezifisch → für Liga gegatet (25.06.2026, Lucas).
    if not IS_LIGA:
      # KO-Bracket auflösen: wm["koFixtures"] mit echten Paarungen, sobald eine Gruppe komplett ist.
      try:
        import resolve_wm_bracket as _wmko
        _ko = _wmko.apply_to_wm(wm)
        _ko_res = sum(1 for f in _ko if f.get("bothResolved"))
        print(f"  🏆 KO-Bracket: {len(_ko)} Slots, {_ko_res} mit beiden Teams fix")
      except Exception as _e:
        print(f"  ⚠️  KO-Bracket-Auflösung fehlgeschlagen: {_e}")

    # 23.06.2026 (Lucas): mathematisch korrekten Qualifikations-Status pro MD3-Fixture ans Fixture
    # hängen (Single Source = incentive_signal._compute_qualification_state). Der Renderer zeigt das
    # nur noch an, statt es aus der Tabellen-POSITION zu erraten (Bug: pos<=2='sicher' / pos>3='muss'
    # → Iran/Uruguay mit 2 Pkt fälschlich „schon Achtelfinale", obwohl noch Vierter möglich).
      _attach_qualification_states(wm)

    groups   = wm.get("groups",   {})
    mkt      = wm.get("odds",     {})
    form         = wm.get("form",        {})
    h2h_data     = wm.get("h2h",         {})
    xg_stats     = wm.get("xgStats",     {})   # Understat xG (Europa-Teams)

    # Serien (compute_streaks) als Pick-Signal-Input (29.06.2026, Lucas: streak_momentum).
    # Aus dem separaten {wm_,liga_,mls_}streaks.json, nach teamId indiziert. Fehlt es → {} (Signal no-op).
    streaks_idx: dict = {}
    try:
        import cocobet_dataset as _D
        _sf = _D.file("wm_streaks.json", "liga_streaks.json")
        if _sf.exists():
            for _s in (json.loads(_sf.read_text(encoding="utf-8")).get("streaks") or []):
                streaks_idx.setdefault(str(_s.get("teamId")), []).append(_s)
    except Exception:
        streaks_idx = {}

    # ── NT-xG aus API-Football als Fallback für fehlende Teams (08.06.2026) ──
    # Understat hat nur ~15 von 48 Teams (Europa-fokussiert). wm_nt_xg.json
    # liefert NT-xG aus den letzten Nationalmannschafts-Spielen für die
    # ~33 fehlenden Teams (CONMEBOL/AFC/Afrika/CONCACAF/OFC).
    # Merge: Understat hat Priorität, NT-xG füllt nur Lücken.
    try:
        nt_xg_file = os.path.join(os.path.dirname(WM_FILE), f"{_FILE_PREFIX}nt_xg.json")
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
                    rec["xgGames"]      = entry.get("xgGames") or 0   # echte xG-Abdeckung (Z.f. thin-xG-Dämpfer)
                    rec["source"]       = "apif_real"
                    merged += 1
                elif entry.get("xgSimForAvg") is not None:
                    rec["xgForAvg"]     = entry["xgSimForAvg"]
                    rec["xgAgainstAvg"] = entry.get("xgSimAgainstAvg")
                    rec["games"]        = entry.get("games", 0)
                    rec["xgGames"]      = entry.get("xgGames") or 0   # Proxy → meist 0 echte xG-Spiele
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
        lineups_file = os.path.join(os.path.dirname(WM_FILE), f"{_FILE_PREFIX}lineups.json")
        if os.path.exists(lineups_file):
            with open(lineups_file, encoding="utf-8") as f:
                lineups_data = json.load(f)
            print(f"  📋 Lineups geladen: {len(lineups_data)} Spiele\n")
    except Exception as e:
        print(f"  ⚠️  Lineups-Load fehlgeschlagen: {e}")

    # ── Per-Spieler-Form (player_form.py) — skaliert lineup_signal importance ──
    # Liga-tauglich (Spieler-ID-basiert). Leer/fehlend = neutral (Faktor 1.0).
    player_form_data: dict = {}
    try:
        _pf_file = os.path.join(os.path.dirname(WM_FILE),
                                "liga_player_form.json" if IS_LIGA else "player_form.json")
        if os.path.exists(_pf_file):
            with open(_pf_file, encoding="utf-8") as f:
                player_form_data = (json.load(f) or {}).get("players", {})
            if player_form_data:
                print(f"  📈 Spieler-Form geladen: {len(player_form_data)} Spieler\n")
    except Exception as e:
        print(f"  ⚠️  player_form-Load fehlgeschlagen: {e}")

    # ── API-Football Predictions (externes Cross-Model, täglich) ────────
    # Drittes Modell unabhängig von Skellam+Elo und Pinnacle. apif_predictions
    # Signal vergleicht pro 1X2/DNB-Pick gegen Pinnacle implied.
    apif_predictions_data: dict = {}
    try:
        apif_file = os.path.join(os.path.dirname(WM_FILE), f"{_FILE_PREFIX}apif_predictions.json")
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
        weather_file = os.path.join(os.path.dirname(WM_FILE), f"{_FILE_PREFIX}weather.json")
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
    travel_file = os.path.join(os.path.dirname(WM_FILE), f"{_FILE_PREFIX}travel_burden.json")
    if os.path.exists(travel_file):
        try:
            with open(travel_file, encoding="utf-8") as tf:
                travel_data = json.load(tf)
        except Exception as e:
            print(f"  ⚠️  Travel-Burden nicht ladbar: {e}")

    # Odds-History (für Signal-Engine LeadLag-Bias + Steam-Lag)
    odds_history = {}
    hist_file = os.path.join(os.path.dirname(WM_FILE), _HISTORY_FILE)
    if os.path.exists(hist_file):
        try:
            with open(hist_file, encoding="utf-8") as hf:
                odds_history = json.load(hf)
        except Exception as e:
            print(f"  ⚠️  Odds-History nicht ladbar: {e}")

    # Polymarket-Snapshot (für Polymarket-Sharp + Steam-Lag-Signal)
    poly_snapshots = {}
    poly_file = os.path.join(os.path.dirname(WM_FILE), f"{_FILE_PREFIX}poly_prices.json")
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

    # Smart-Money-Verteilung (19.06.2026): Geld-Split + Wallet-Konzentration je Spiel aus
    # fetch_wm_poly_smartmoney.py (data-api /holders+/trades, läuft am Mac-Runner). Optional
    # — fehlt die Datei, feuert das smart_money-Signal einfach nicht.
    smartmoney = {}
    _sm_file = os.path.join(os.path.dirname(WM_FILE), f"{_FILE_PREFIX}poly_smartmoney.json")
    if os.path.exists(_sm_file):
        try:
            with open(_sm_file, encoding="utf-8") as smf:
                _smraw = json.load(smf)
            smartmoney = _smraw.get("matches", _smraw) if isinstance(_smraw, dict) else {}
        except Exception as e:
            print(f"  ⚠️  Smart-Money nicht ladbar: {e}")

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

    # ── KO-Phase als synthetische Gruppe (25.06.2026, Lucas: „sobald beide Teams feststehen kann er
    # schon eine Card generieren"). Zweistufig: ist ein koFixture mit beiden Teams aufgelöst, läuft es
    # durch DENSELBEN Pick-Körper wie Gruppenspiele. Ohne KO-Quoten liefert die Steam-Engine nichts →
    # leere Picks = reine Vorschau-Card (Renderer zeigt sie aus koFixtures). Mit Quoten → echter Pick.
    # WICHTIG: NUR lokal iteriert, NICHT in wm["groups"] geschrieben (sonst baut wm_standings eine
    # Geister-Gruppe „KO"). gkey="KO", matchday=Runden-Code (R32/R16/QF/SF) → pick_key "KO-R32-A-B".
    _all_teams = []
    _seen_tid = set()
    for _gd in groups.values():
        for _t in (_gd.get("teams") or []):
            _tid = _t.get("id") if isinstance(_t, dict) else _t
            if _tid and _tid not in _seen_tid:
                _seen_tid.add(_tid)
                _all_teams.append(_t)
    _ko_fixtures = []
    for _kf in (wm.get("koFixtures") or []):
        if not _kf.get("bothResolved"):
            continue
        _ko_fixtures.append({
            "home":       _kf["home"],
            "away":       _kf["away"],
            "matchday":   _kf["round"],          # "R32"/"R16"/"QF"/"SF"
            "date":       _kf.get("date"),
            "kickoff":    _kf.get("kickoff"),
            "venue":      _kf.get("venue"),
            "koMatchKey": _kf.get("matchKey"),
            "koRoundLabel": _kf.get("roundLabel"),
        })
    _iter_groups = list(groups.items())
    if _ko_fixtures:
        _iter_groups.append(("KO", {"teams": _all_teams, "fixtures": _ko_fixtures}))

    # Spielplan je Team (für fixture_congestion / Erschöpfung): {team_id: [sortierte Datumsstrings]}.
    # Einmal aus allen Fixtures gebaut, in den Signal-Kontext gereicht (Ruhetage = Datum-Abstand zum
    # letzten Spiel). Rein aus dem Plan, kein API-Call.
    _team_dates: dict = {}
    for _gd in groups.values():
        for _fx in (_gd.get("fixtures") or []):
            _d = _fx.get("date")
            if not _d:
                continue
            for _tid in (_fx.get("home"), _fx.get("away")):
                if _tid:
                    _team_dates.setdefault(_tid, []).append(_d)
    for _tid in _team_dates:
        _team_dates[_tid] = sorted(set(_team_dates[_tid]))

    for gkey, gdata in _iter_groups:
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
                # via Freeze (oben) unangetastet. (Der alte Elo-Edge-Pfad
                # generate_picks_for_fixture wurde 26.06.2026 entfernt — toter Code.)
                new_picks = generate_steam_picks_for_fixture(
                    fx, mkt.get(f"{fx['home']}-{fx['away']}", {}), today,
                    drift=_steam_drift,
                )

            # ── Frische-Modell (18.06.2026, Lucas) ────────────────────────
            # Jedem Steam-Pick die FRISCHE Bewegung (letzter Bewegungs-Abschnitt der
            # Pinnacle-Reihe) anhängen: confirm/drift/reverse. Läuft VOR der Signal-Engine,
            # damit ein abgeleiteter Reverser-Konter dieselben Signale + Conviction bekommt
            # (Lucas: „feuern die Signale dann dafür?"). Reverser-Eltern werden zurückgestuft;
            # der Konter wird als eigener ABWÄGEN-Pick angehängt (reift nur via Conviction→BET).
            # Immutability (feedback_posted_picks_immutable): gepostete Picks (Anpfiff
            # heute/morgen) komplett unangetastet lassen — kein Frische-Feld, keine Conviction-
            # Wirkung, kein Demote/Konter. Das Frische-Modell greift erst übermorgen+ (fx_date
            # > tomorrow), damit eine veröffentlichte Wette nicht rückwirkend kippt.
            _fr_posted = bool(fx.get("date") and fx.get("date") <= tomorrow)
            try:
                _fr_ha   = f"{fx['home']}-{fx['away']}"
                _fr_hist = odds_history.get(_fr_ha, []) if odds_history else []
                _fr_snap = mkt.get(_fr_ha, {})
                _counters = []
                for _p in (new_picks or []):
                    if _fr_posted:
                        continue
                    if _p.get("source") != "steam" or _p.get("reverserCounter"):
                        continue
                    _an = analyze_recent_move(_fr_hist, _p.get("market", ""))
                    if not _an:
                        continue
                    _p["recentMovePP"]   = _an["movePP"]
                    _p["freshnessState"] = _an["state"]
                    _p["legHours"]       = _an["legHours"]
                    _p["legSnaps"]       = _an.get("legSnaps")
                    _p["lastMoveH"]      = _an.get("lastMoveH")
                    _p["flipReady"]      = bool(_an.get("flipReady"))
                    if _an["state"] == "reverse":
                        _p["reverser"]    = True
                        _p["reverserPP"]  = _an["movePP"]
                        # frisch = letzter echter Gegen-Move ≤ STALE_AFTER_H; sonst alter
                        # Move gegen uns (trotzdem zurückstufen, aber ehrlich anders labeln).
                        _lmh = _an.get("lastMoveH")
                        _p["reverserFresh"]     = bool(_lmh is not None and _lmh <= STALE_AFTER_H)
                        _p["reverserLastMoveH"] = _lmh
                        # Eltern zurückstufen (überschreibt spätere Conviction-Upgrades,
                        # da downgradedReason gesetzt). Starker Reverser (≤ −6pp) ODER wenn wir
                        # die Gegen-Linie zeigen (flipReady) → BEOBACHTEN: der Eltern-Pick soll
                        # nicht als zweites, widersprüchliches ABWÄGEN neben dem Konter stehen.
                        if _an["movePP"] <= -2 * REVERSER_THRESHOLD_PP or _an.get("flipReady"):
                            _p["verdict"] = "BEOBACHTEN"
                        elif _p.get("verdict") == "BET":
                            _p["verdict"] = "ABWÄGEN"
                        _p["downgradedReason"] = (
                            f"Reverser: frisches Geld {_an['movePP']:+.1f}pp (letzter "
                            f"Bewegungs-Abschnitt) GEGEN den Pick — Move seit Eröffnung überholt"
                        )
                        # Gegen-Linie NUR bei deutlichem, persistentem Reverser (flipReady):
                        # höhere Schwelle + genug Snaps. Schwacher Reverser → nur warnen.
                        if _an.get("flipReady"):
                            _ctr = _derive_reverser_counter(_p, _fr_snap, _an["movePP"])
                            if _ctr:
                                _counters.append(_ctr)
                if _counters:
                    new_picks = list(new_picks) + _counters
            except Exception as _fr_err:
                print(f"  ⚠️  Frische-Modell crashed für {fx['home']}-{fx['away']}: {_fr_err}")

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
                        _vpath = _os.path.join(_os.path.dirname(WM_FILE), f"{_FILE_PREFIX}venues.json")
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
                    "smartmoney":    smartmoney,
                    "travel":       travel_data,
                    "injuries":     injuries,
                    "form":         form,
                    "h2h":          h2h_data.get(ha_key, {}),
                    "xg_stats":         xg_stats,
                    "streaks":          streaks_idx,   # streak_momentum-Signal

                    "lineups":          lineups_data,
                    "player_form":      player_form_data,
                    "squads":           wm.get("squads", {}),
                    "topscorers":       wm.get("topScorers", {}),   # topscorer_momentum
                    "coach_change":     wm.get("coachChange", {}),  # coach_change
                    "key_departures":   wm.get("keyDepartures", {}),  # transfer_shift
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
                    "team_schedule":      _team_dates,   # für fixture_congestion (Ruhetage)
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

                        # ── Trade-Variante OHNE freshness_leg (18.06.2026, Lucas-Audit) ──
                        # Zwei Flächen: die Card-Frische darf das Trading NICHT treiben. Der
                        # Auto-Trader liest signalAdj/effectiveEdge — ein confirm würde sonst
                        # den effectiveEdge über die Schwelle pumpen, ein reverse doppelt zählen
                        # (die Umkehr steckt schon im live-recomputeten Pinnacle-fair). Daher
                        # Trade-Felder ohne den freshness_leg-Beitrag.
                        # Card-only-Signale aus dem Trade-Pfad raus (zwei Flächen): freshness_leg
                        # (würde Trade-Edge pumpen) + smart_money (Poly-Geld über Poly-Trades zu
                        # entscheiden wäre ZIRKULÄR/reflexiv). Sie treiben nur Cards + Lern-Loop.
                        _CARD_ONLY = ("freshness_leg", "smart_money")
                        _fresh_pp = sum(s.get("score", 0.0) for s in sig_out["signals"]
                                        if s.get("name") in _CARD_ONLY)
                        p["signalAdjustmentPP_trade"] = round(
                            sig_out["combined_score_pp"] - _fresh_pp, 1)
                        # auch aus dem Signal-ZÄHLER raus (Trader nutzt signalPos für einen
                        # Schwellen-Bonus) — sonst hilft ein confirm dem Trade über die Hintertür.
                        _fresh_pos = sum(1 for s in sig_out["signals"]
                                         if s.get("name") in _CARD_ONLY and s.get("score", 0) > 0)
                        _fresh_neg = sum(1 for s in sig_out["signals"]
                                         if s.get("name") in _CARD_ONLY and s.get("score", 0) < 0)
                        p["signalCountPos_trade"] = max(0, sig_out["n_positive_signals"] - _fresh_pos)
                        p["signalCountNeg_trade"] = max(0, sig_out["n_negative_signals"] - _fresh_neg)

                        # ── Edge-Adjustment Integration ─────────────────
                        # Echter Edge (model vs market) wird um Engine-Output
                        # justiert. Damit kann der Renderer einen "echten" Edge
                        # nach Engine-Korrektur zeigen.
                        if isinstance(p.get("edgePP"), (int, float)):
                            p["effectiveEdgePP"] = round(p["edgePP"] + sig_out["combined_score_pp"], 1)
                            p["effectiveEdgePP_trade"] = round(
                                p["edgePP"] + p["signalAdjustmentPP_trade"], 1)

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
                        # Lern-Ebene 2: gedeckelter Segment-Nudge auf die Conviction (sehr klein,
                        # erst ab CAL_MIN_PICKS). Raw + Nudge transparent festhalten.
                        _cal_nudge = _calibration_nudge(p)
                        _conv_raw = conv["score"]
                        _early_pen = _early_season_penalty(fx)   # 0 außer Liga-MD ≤ 3
                        p["convictionScore"]   = max(0, min(10, int(round(_conv_raw + _cal_nudge - _early_pen))))
                        if _cal_nudge:
                            p["convictionRaw"]    = _conv_raw
                            p["calibrationNudge"] = _cal_nudge
                        if _early_pen:
                            p["earlySeasonPenalty"] = _early_pen
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
                        # BET-Entry-Hürde (18.06.2026): NEU auf BET nur bei FRISCHEM Move —
                        # letzter echter Move ≤ BET_ENTRY_HURDLE_H. lastMoveH None (unmappbarer
                        # Markt / Nicht-Steam) → Hürde aus (Altverhalten). Ein alter Drift-Move
                        # kann so nie neu BET auslösen, egal wie stark die Fundamentals sind.
                        _lmh = p.get("lastMoveH")
                        _move_fresh = (_lmh is None) or (_lmh <= BET_ENTRY_HURDLE_H)
                        if (p.get("verdict") == "ABWÄGEN"
                                and (conv["score"] - _early_pen) >= _conv_threshold
                                and not p.get("downgradedReason")
                                and _move_fresh):
                            p["verdict"] = "BET"
                            p["pickTriggerReason"] = (
                                f"Conviction {conv['score']}/10 (≥{_conv_threshold}) — "
                                f"frischer Move + Signale bestätigen den Pick"
                            )
                            p.setdefault("firstBetAt", now_dt.isoformat())
                        elif (p.get("verdict") == "ABWÄGEN"
                                and conv["score"] >= _conv_threshold
                                and not p.get("downgradedReason")
                                and not _move_fresh):
                            # Conviction reicht, aber der Move ist nicht mehr frisch (> Hürde).
                            # Kein NEUER BET — der Hold-Schritt (unten) hebt ihn nur, wenn er
                            # schon BET war und kein Reverser dagegensteht.
                            p["staleForEntry"] = True
                        elif p.get("verdict") == "BET":
                            p["pickTriggerReason"] = "Edge-getrieben"
                            p.setdefault("firstBetAt", now_dt.isoformat())

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

            # firstBetAt IMMER aus dem alten Pick mitnehmen (Audit-Fix a, 18.06.2026):
            # nur ein Timestamp, ändert kein Verdict — auch für kurzfristige/posted Picks,
            # die den Hold-Block (unten, posted-gated) nicht durchlaufen. Sonst resettet
            # „BET seit X" jeden Lauf.
            if existing_pk:
                _old_fb = {op.get("market"): op.get("firstBetAt") for op in existing_pk
                           if isinstance(op, dict) and op.get("firstBetAt")}
                for p in new_picks:
                    if p.get("verdict") == "BET" and _old_fb.get(p.get("market")):
                        p["firstBetAt"] = _old_fb[p.get("market")]

            # ── BET-Hold über Läufe (18.06.2026, Lucas) ───────────────────
            # Einmal BET, bleibt BET — solange KEIN Reverser (frisches Gegen-Geld) kommt,
            # auch wenn der Move ruht (settled). „Wenn nichts dagegen spricht, bleibt er."
            # Memory = der alte Pick (existing_pk) vor dem Überschreiben. Nur künftige Picks
            # (fx_date > tomorrow); gepostete bleiben unangetastet. Exit-Gründe (Reverser /
            # harte Engine-Warnung / CLV gegen) heben den Hold NICHT auf.
            _hold_posted = bool(fx.get("date") and fx.get("date") <= tomorrow)
            if not _hold_posted and existing_pk:
                _old_bet = {op.get("market"): op for op in existing_pk
                            if isinstance(op, dict) and op.get("verdict") == "BET"}
                for p in new_picks:
                    old = _old_bet.get(p.get("market"))
                    if not old:
                        continue
                    # Kein Grandfathering (Lucas 18.06.): nur Picks halten, die schon UNTER
                    # der neuen Logik BET wurden (firstBetAt vorhanden). Alt-BETs aus dem
                    # Vor-Frische-Stand müssen sich frisch requalifizieren, nicht durchrutschen.
                    if not old.get("firstBetAt"):
                        continue
                    if p.get("reverser") or p.get("freshnessState") == "reverse":
                        continue                     # Reverser → Exit (Demote bleibt)
                    if p.get("verdict") == "BET":
                        if old.get("firstBetAt"):    # firstBetAt mitnehmen
                            p["firstBetAt"] = old["firstBetAt"]
                        continue
                    # War BET, ist jetzt < BET (Move ruht / Conviction knapp). Halten —
                    # ABER nur wenn keine harte Warnung dagegen steht (downgradedReason aus
                    # Engine-SKIP/CLV). staleForEntry (nur „nicht frisch genug für NEU-Entry")
                    # ist kein Exit-Grund.
                    if (p.get("verdict") in ("ABWÄGEN", "BEOBACHTEN")
                            and not p.get("downgradedReason")):
                        p["verdict"]      = "BET"
                        p["betHeld"]      = True
                        p["firstBetAt"]   = old.get("firstBetAt") or now_dt.isoformat()
                        p["pickTriggerReason"] = (
                            "Hält BET: war bestätigt, Move ruht — aber kein Reverser dagegen "
                            "(bleibt bis frisches Gegen-Geld kommt)"
                        )

            # Smart-Money-Split (Poly-Geldverteilung) für die violette Card-Anzeige an jeden
            # Pick hängen — reine Anzeige, ändert kein Verdict (19.06.2026).
            _sm_match = smartmoney.get(f"{fx['home']}-{fx['away']}")
            if _sm_match and isinstance(_sm_match, dict):
                for _p in (new_picks or []):
                    _p["smartMoney"] = _sm_match

            # Write-Boundary-Dedup (23.06.2026, Lucas: PAN-CRO hatte 2× „Beide Teams treffen — Ja"):
            # genau EINE Karte je (Markt) — defensiv gegen Refresh-/Merge-Altlasten aus jeder Quelle.
            new_picks = _dedup_picks_by_market(new_picks)
            # NOBET-Karten (23.06.2026): ex-BET/ABWÄGEN ohne aktuellen Pick als NOBET behalten.
            new_picks = _carry_nobet(existing_pk, new_picks,
                                     mkt.get(f"{fx['home']}-{fx['away']}", {}), now_dt.isoformat())
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

    # Edge-Staking (28.06.2026, Lucas): pick["stake"] nach Conviction×Odds (fraktionales Kelly).
    # NACH der trackingExcluded-Logik, damit ausgeschlossene Picks keinen Stake bekommen.
    try:
        import pick_staking
        _ns = pick_staking.apply(wm)
        print(f"  💶 Edge-Stake gesetzt für {_ns} Pick(s).")
    except Exception as _e:
        print(f"  ⚠️  Edge-Staking übersprungen: {_e}")

    # engineVersion-Stempel (04.07.2026, Lucas): jeder Pick OHNE Stempel bekommt die aktuelle
    # Engine-Version des Profils. NIE überschreiben → immutabilitäts-sicher (gepostete Picks
    # behalten ihren Stand, [[feedback_posted_picks_immutable]]). Der Lern-Loop lernt nur auf der
    # aktuellen Version → künftige Engine-Änderungen (Version hochzählen) vergiften den Ledger nicht.
    _ev = D.engine_version()
    _stamped = 0
    for _plist in (wm.get("picks") or {}).values():
        if not isinstance(_plist, list):
            continue
        for _p in _plist:
            if not _p.get("engineVersion"):
                _p["engineVersion"] = _ev
                _stamped += 1
    if _stamped:
        print(f"  🏷️  engineVersion={_ev} gestempelt auf {_stamped} neue(n) Pick(s).")
    wm["_meta"] = wm.get("_meta", {})
    wm["_meta"]["picksUpdatedAt"] = datetime.now(timezone.utc).isoformat()
    wm["_meta"]["engineVersion"] = _ev   # aktuelle Version des Datensatzes (für Guard/Anzeige)

    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    print(f"✅ {os.path.basename(str(WM_FILE))} gespeichert.")


if __name__ == "__main__":
    main()
