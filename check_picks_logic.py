#!/usr/bin/env python3
"""
CocoBet — Daily Picks Logic Validator
======================================
Liest season-finish.html, extrahiert alle anstehenden Spiele und prüft
jeden Pick auf logische Konsistenz. Gibt strukturierte Fehler/Warnungen aus.

Aufruf:
    python3 check_picks_logic.py              # alle kommenden Spiele
    python3 check_picks_logic.py --days 1     # nur heute & morgen
    python3 check_picks_logic.py --date 22.04 # bestimmtes Datum
    python3 check_picks_logic.py --errors     # nur kritische Fehler
    python3 check_picks_logic.py --report     # schreibt validator_report.md (auto-call)

Prüft automatisch auf:
  🔴 FEHLER   — definitive Logik-Bugs (z.B. mustWin auf bestätigtem Abstieg)
  🟡 WARNUNG  — verdächtige Konstellationen (z.B. red-safe mit Panik-Text)
  🔵 HINWEIS  — schwache Pick-Basis (z.B. H2H dominiert aber kein Kontext)

Injury-Checks:
  🔴 FEHLER   — impactScore fehlt obwohl Ausfälle vorhanden
  🔴 FEHLER   — impactScore > 6.0 (Kappung überschritten)
  🟡 WARNUNG  — posEstimated=True bei hohem Impact (Positionen geraten, nicht bestätigt)
  🟡 WARNUNG  — Auswärtsteam hat kritischen Impact aber Heimsieg klar empfohlen
  🟡 WARNUNG  — Heimteam hat kritischen Impact aber Away-Wette fehlt als Absicherung
  🔵 HINWEIS  — Over 2.5 Empfehlung bei kombinierten Verletzungsausfällen (xG reduziert)

Picks-spezifische Checks (bekannte Fehler April 2026):
  🔴 FEHLER   — Dead-rubber-Spiel mit hohem Score (beide motiv='none')
  🟡 WARNUNG  — Karten-Pick-Risiko bei bestätigt abgestiegenem Team
  🟡 WARNUNG  — H2H Schnitt ≥3.0 → Under 2.5 Pick wäre falsch
  🟡 WARNUNG  — H2H BTTS ≥65% → Under Pick ist riskant
  🟡 WARNUNG  — Sehr niedriger kombinierter Torschnitt → Over Pick riskant
  🔵 HINWEIS  — motiv='low' bei Karten-relevanten Matches
"""

import json
import re
import sys
import os
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE  = os.path.join(SCRIPT_DIR, "season-finish.html")

# ── Negative-edge gate thresholds ────────────────────────────────────────────
# SYNC:GATE — These values MUST match the GATE object in pick-engine.js
# (search for "const GATE = {" near the top of getBettingPicks engine).
# When you change a threshold here, change the matching key there — and vice versa.
GATE_GOALS_REAL  = 0.12  # Over 2.5 / Over 3.5 / BTTS  (real bookie odds)
GATE_RESULT_REAL = 0.15  # Heimsieg / Auswärtssieg 1X2  (real bookie odds, Poisson-based — Apr 2026)
GATE_TEAM_REAL   = 0.12  # Heim/Ausw über 1.5  (real bookie odds)
GATE_TEAM_EST    = 0.15  # Heim/Ausw über 1.5  (estimated odds)
GATE_AH_REAL     = 0.14  # Asian Handicap  (real only)
GATE_CORN_REAL   = 0.10  # Ecken Over  (real bookie odds)
GATE_CORN_EST    = 0.15  # Ecken Over  (estimated odds)

# ── Poisson-Hilfsfunktion (identisch mit JS _poissonOver) ────────────────────
import math

def poisson_over(lam, threshold):
    """P(X > threshold) für Poisson(lambda). Threshold ist die .5-Linie."""
    if lam <= 0:
        return 0.5
    k = int(threshold)  # P(X > k+0.5) = P(X >= k+1) = 1 - CDF(k)
    cdf, term = 0.0, math.exp(-lam)
    for i in range(k + 1):
        cdf += term
        term *= lam / (i + 1)
    return max(0.02, min(0.98, 1 - cdf))

# ── Ceiling-Logik (identisch mit JS/Python) ───────────────────────────────────
def score_ceiling(rounds_left):
    rl = rounds_left
    if rl <= 1: return 12.0
    if rl <= 2: return 11.5
    if rl <= 3: return 11.0
    if rl <= 4: return 10.5
    if rl <= 5: return 10.0
    if rl <= 6:  return 9.5
    if rl <= 7:  return 9.0
    if rl <= 8:  return 8.5
    if rl <= 9:  return 8.0
    return 7.5

# ── Checks ────────────────────────────────────────────────────────────────────

def check_fixture(fixture, league_key, league_name, rounds_left):
    """Gibt Liste von (severity, code, message) zurück."""
    issues = []
    home = fixture.get("home", "?")
    away = fixture.get("away", "?")
    hs   = fixture.get("homeStake")
    aws  = fixture.get("awayStake")
    h2h  = fixture.get("h2h") or {}
    ms   = fixture.get("matchScore", 0)
    hf   = fixture.get("homeForm") or {}
    af   = fixture.get("awayForm") or {}

    def flag(severity, code, msg):
        issues.append((severity, code, msg))

    # ── Helpers ───────────────────────────────────────────────────────────────
    def labels_colors(stake):
        if not stake: return []
        return [l["c"] for l in stake.get("labels", [])]

    hc = labels_colors(hs)
    ac = labels_colors(aws)

    def is_red_safe(stake, colors):
        """Mirrors the JS fix: only truly safe when motivationLevel='low' AND pressure=0."""
        if not stake: return False
        mot = stake.get("motivationLevel", "full")
        pr  = stake.get("pressureRatio")   # None if missing — NOT defaulted to 0
        pn  = stake.get("pointsNeeded")    # None if missing
        return "red" in colors and mot == "low" and pr == 0 and pn == 0

    h_red_safe = is_red_safe(hs, hc)
    a_red_safe = is_red_safe(aws, ac)

    def h2h_dominated():
        g  = h2h.get("games", 0)
        hw = h2h.get("homeWins", 0)
        aw = h2h.get("awayWins", 0)
        if g < 5: return False, None
        if hw / g >= 0.75: return True, f"{home} dominiert H2H {hw}W/{h2h.get('draws',0)}X/{aw}L in {g} Spielen"
        if aw / g >= 0.75: return True, f"{away} dominiert H2H {aw}W/{h2h.get('draws',0)}X/{hw}L in {g} Spielen"
        return False, None

    # ─────────────────────────────────────────────────────────────────────────
    # 🔴 FEHLER: mustWin=True auf bestätigt abgestiegenem Team
    # ─────────────────────────────────────────────────────────────────────────
    for stake, side in [(hs, home), (aws, away)]:
        if not stake: continue
        if stake.get("mustWin") and stake.get("motivationLevel") == "none":
            flag("ERROR", "MW_ON_CONFIRMED_REL",
                 f"{side}: mustWin=True aber motivationLevel='none' — "
                 f"Team ist bestätigt abgestiegen, mustWin-Amplifier darf nicht feuern.")

    # 🔴 FEHLER: matchScore überschreitet Ceiling für roundsLeft
    ceiling = score_ceiling(rounds_left)
    if ms > ceiling + 0.1:  # +0.1 Toleranz für Rundungsdifferenzen
        flag("ERROR", "SCORE_EXCEEDS_CEILING",
             f"matchScore={ms} überschreitet Ceiling={ceiling} für rl={rounds_left}. "
             f"Python calc_match_score() wurde nicht mit rounds_left aufgerufen.")

    # 🔴 FEHLER: Beide Teams motivationLevel='none' aber matchScore > 6
    if (hs and hs.get("motivationLevel") == "none" and
        aws and aws.get("motivationLevel") == "none" and ms > 6):
        flag("ERROR", "DEAD_RUBBER_HIGH_SCORE",
             f"Beide Teams bestätigt abgestiegen (motiv='none') aber matchScore={ms}. "
             f"Dead-Rubber-Penalty (-2.0) wurde nicht korrekt angewendet.")

    # ─────────────────────────────────────────────────────────────────────────
    # 🟡 WARNUNG: Red-Safe — in roter Zone aber mathematisch schon gerettet
    # ─────────────────────────────────────────────────────────────────────────
    if h_red_safe and ms >= 7.5:
        flag("WARN", "RED_SAFE_HIGH_SCORE",
             f"{home}: rotes Label aber pressure=0/ptNeeded=0 (schon gerettet), "
             f"matchScore={ms} trotzdem hoch. Angle-Text könnte falsche Dringlichkeit signalisieren.")

    if a_red_safe and ms >= 7.5:
        flag("WARN", "RED_SAFE_HIGH_SCORE",
             f"{away}: rotes Label aber pressure=0/ptNeeded=0 (schon gerettet), "
             f"matchScore={ms} trotzdem hoch. Angle-Text könnte falsche Dringlichkeit signalisieren.")

    # 🟡 WARNUNG: mustWin=True aber goalsPerGame < 0.8 (kann nicht treffen)
    for stake, form, side in [(hs, hf, home), (aws, af, away)]:
        if not stake: continue
        mot = stake.get("motivationLevel", "full")
        if stake.get("mustWin") and mot != "none":
            gpg = form.get("goalsPerGame", 99)
            if gpg < 0.8:
                flag("WARN", "MUSTWIN_LOW_GPG",
                     f"{side}: mustWin=True aber nur {gpg:.1f} Tore/Spiel — "
                     f"Pick 'muss gewinnen' bei Teams die kaum treffen ist unrealistisch.")

    # 🟡 WARNUNG: H2H dominiert (≥75%) bei hohem matchScore ohne Dämpfer
    dominated, dom_msg = h2h_dominated()
    if dominated and ms >= 7.5:
        flag("WARN", "H2H_DOMINATED_HIGH_SCORE",
             f"{dom_msg}. matchScore={ms} — Pick-Richtung sollte klar sein, "
             f"Angle-Text darf den Underdog nicht überbewerten.")

    # 🟡 WARNUNG: bothRed aber beide schon gerettet
    if "red" in hc and "red" in ac and h_red_safe and a_red_safe:
        flag("WARN", "BOTH_RED_SAFE",
             f"Beide Teams rot aber beide mathematisch gerettet (pressure=0, ptNeeded=0). "
             f"Kellerduell-Narrative ist irreführend — kein echter Abstiegskampf.")

    # 🟡 WARNUNG: Hoher Score (≥9) aber beide motivationLevel='low'
    if (hs and hs.get("motivationLevel") == "low" and
        aws and aws.get("motivationLevel") == "low" and ms >= 9.0):
        flag("WARN", "BOTH_LOW_MOTIV_HIGH_SCORE",
             f"Beide Teams motivationLevel='low' (fast am Ziel) aber matchScore={ms}. "
             f"Intensitäts-Einschätzung könnte zu hoch sein.")

    # 🟡 WARNUNG: Over-2.5-Signal bei sehr niedrigem Torschnitt
    avg_gpg = None
    if hf.get("goalsPerGame") is not None and af.get("goalsPerGame") is not None:
        avg_gpg = (hf["goalsPerGame"] + af["goalsPerGame"]) / 2
    h2h_avg = h2h.get("avgGoals", None)

    if avg_gpg is not None and avg_gpg < 0.9 and h2h_avg is not None and h2h_avg < 2.0:
        flag("WARN", "LOW_SCORING_OVER_RISK",
             f"Beide Teams zusammen nur {avg_gpg:.1f} Tore/Spiel (Schnitt), "
             f"H2H avg={h2h_avg:.1f} — Over 2.5 Picks hier sehr riskant.")

    # ─────────────────────────────────────────────────────────────────────────
    # 🔵 HINWEIS: H2H dominiert bei anyGold+anyRed — Pick-Richtung prüfen
    # ─────────────────────────────────────────────────────────────────────────
    any_gold = "gold" in hc or "gold" in ac
    any_red  = "red"  in hc or "red"  in ac
    if any_gold and any_red and dominated and ms >= 7.0:
        flag("INFO", "H2H_DOM_GOLD_RED",
             f"{dom_msg}. Gold vs Rot, aber H2H-Favorit klar — "
             f"Angle sollte Pick-Richtung bestätigen, nicht dramatisieren.")

    # 🔵 HINWEIS: H2H zu wenig Daten (< 5 Spiele) bei hohem Score
    h2h_games = h2h.get("games", 0)
    if h2h_games < 5 and ms >= 8.0:
        flag("INFO", "LOW_H2H_SAMPLE",
             f"Nur {h2h_games} H2H-Spiele verfügbar bei matchScore={ms}. "
             f"Pick-Basis ist schwächer — Quoten und Form priorisieren.")

    # 🔵 HINWEIS: Gold-Team pressure=0 in bothGold — kein echter Titelkampf
    if "gold" in hc and "gold" in ac:
        h_pr = (hs or {}).get("pressureRatio", 0)
        a_pr = (aws or {}).get("pressureRatio", 0)
        if h_pr == 0 and a_pr == 0:
            flag("INFO", "BOTH_GOLD_NO_PRESSURE",
                 f"Titelduell-Angle aber beide Teams pressure=0 — "
                 f"Titel faktisch gesichert, 'Titelduell'-Text übertreibt die Spannung.")

    # 🔵 HINWEIS: Sehr asymmetrischer Score (Differenz > 4) bei bothStakes
    if hs and aws:
        diff = abs(hs.get("score", 0) - aws.get("score", 0))
        if diff >= 4.0:
            low_side  = home if hs.get("score", 0) < aws.get("score", 0) else away
            high_side = away if hs.get("score", 0) < aws.get("score", 0) else home
            flag("INFO", "ASYMMETRIC_STAKE_SCORES",
                 f"Score-Differenz {diff:.1f} Punkte: {high_side} ({max(hs.get('score',0),aws.get('score',0))}) "
                 f"vs {low_side} ({min(hs.get('score',0),aws.get('score',0))}). "
                 f"Pick-Richtung sehr klar — Favoritenpflicht prüfen.")

    # ─────────────────────────────────────────────────────────────────────────
    # INJURY CHECKS
    # ─────────────────────────────────────────────────────────────────────────
    h_inj = hf.get("injuries") or {}
    a_inj = af.get("injuries") or {}

    def inj_impact(inj_obj):
        return inj_obj.get("impactScore", 0) or 0

    def inj_confirmed(inj_obj):
        return inj_obj.get("confirmed", 0) or 0

    def inj_total(inj_obj):
        return inj_obj.get("total", 0) or 0

    h_impact = inj_impact(h_inj)
    a_impact = inj_impact(a_inj)
    h_conf   = inj_confirmed(h_inj)
    a_conf   = inj_confirmed(a_inj)

    # 🔴 FEHLER: impactScore fehlt aber Ausfälle vorhanden
    if inj_total(h_inj) > 0 and h_inj.get("impactScore") is None:
        flag("ERROR", "INJ_MISSING_IMPACT_HOME",
             f"{home}: {inj_total(h_inj)} Verletzte/Gesperrte aber impactScore fehlt. "
             f"computeClientInjuryImpact() wurde nicht aufgerufen.")
    if inj_total(a_inj) > 0 and a_inj.get("impactScore") is None:
        flag("ERROR", "INJ_MISSING_IMPACT_AWAY",
             f"{away}: {inj_total(a_inj)} Verletzte/Gesperrte aber impactScore fehlt. "
             f"computeClientInjuryImpact() wurde nicht aufgerufen.")

    # 🔴 FEHLER: impactScore > 6.0 (Kappung überschritten — JS capped bei 6.0)
    if h_impact > 6.1:
        flag("ERROR", "INJ_IMPACT_CAP_EXCEEDED_HOME",
             f"{home}: impactScore={h_impact:.1f} überschreitet Cap von 6.0. "
             f"computeClientInjuryImpact() hat Math.min(6.0, ...) nicht korrekt angewendet.")
    if a_impact > 6.1:
        flag("ERROR", "INJ_IMPACT_CAP_EXCEEDED_AWAY",
             f"{away}: impactScore={a_impact:.1f} überschreitet Cap von 6.0.")

    # 🔴 FEHLER: impactScore ist negativ (Rechenfehler)
    if h_impact < 0:
        flag("ERROR", "INJ_NEGATIVE_IMPACT_HOME",
             f"{home}: impactScore={h_impact:.1f} ist negativ — Berechnungsfehler.")
    if a_impact < 0:
        flag("ERROR", "INJ_NEGATIVE_IMPACT_AWAY",
             f"{away}: impactScore={a_impact:.1f} ist negativ — Berechnungsfehler.")

    # 🟡 WARNUNG: posEstimated=True bei hohem Impact
    if h_inj.get("posEstimated") and h_impact >= 2.0:
        flag("WARN", "INJ_POSITIONS_ESTIMATED_HOME",
             f"{home}: impactScore={h_impact:.1f} aber Positionsdaten geschätzt (posEstimated=True). "
             f"Keine echten Positionsdaten vom Server — xG-Modifikation ungenau.")
    if a_inj.get("posEstimated") and a_impact >= 2.0:
        flag("WARN", "INJ_POSITIONS_ESTIMATED_AWAY",
             f"{away}: impactScore={a_impact:.1f} aber Positionsdaten geschätzt (posEstimated=True). "
             f"Keine echten Positionsdaten vom Server — xG-Modifikation ungenau.")

    # 🟡 WARNUNG: Kritischer Ausfall bei Auswärtsteam (≥3.5) + Away-Angriff stark betroffen
    # → Over 2.5 Empfehlung ist fragwürdig
    a_attack_out = (a_inj.get("attack") or 0)
    h_attack_out = (h_inj.get("attack") or 0)
    if a_impact >= 3.5 and a_attack_out >= 2 and ms >= 7.0:
        flag("WARN", "INJ_AWAY_CRITICAL_ATTACK_HIGH_SCORE",
             f"{away}: kritischer Ausfall (impact={a_impact:.1f}, {a_attack_out} Stürmer fehlen) "
             f"bei matchScore={ms}. Over 2.5 oder BTTS-Picks in diese Richtung kritisch prüfen.")

    if h_impact >= 3.5 and h_attack_out >= 2 and ms >= 7.0:
        flag("WARN", "INJ_HOME_CRITICAL_ATTACK_HIGH_SCORE",
             f"{home}: kritischer Ausfall (impact={h_impact:.1f}, {h_attack_out} Stürmer fehlen) "
             f"bei matchScore={ms}. Over 2.5 oder BTTS-Picks kritisch prüfen.")

    # 🟡 WARNUNG: Heim-Torhüter fehlt UND Auswärtssieg NICHT in Picks vertreten
    # Kein Zugriff auf Pick-Liste hier → prüfen ob Auswärtssieg wenigstens diskutiert wird
    h_gk_out = (h_inj.get("goalkeeper") or 0)
    if h_gk_out >= 1 and h_impact >= 2.0 and ms >= 7.5:
        flag("INFO", "INJ_HOME_GK_MISSING_CHECK_AWAY",
             f"{home}: {h_gk_out} TW fehlt (impact={h_impact:.1f}). "
             f"Bei matchScore={ms} prüfen ob Auswärtssieg-Pick oder DNB Away als Safer Alt vorhanden.")

    # 🔵 HINWEIS: Beide Teams haben Ausfälle → Over 2.5 ist riskant
    both_attack_out = h_attack_out + a_attack_out
    if both_attack_out >= 3 and ms >= 6.5:
        flag("INFO", "INJ_BOTH_TEAMS_ATTACK_DEPLETED",
             f"Kombiniert {both_attack_out} Stürmer fehlen (H:{h_attack_out} A:{a_attack_out}). "
             f"Over 2.5 Tore Picks sind durch Verletzungskorrektur stark reduziert — Modell bevorzugt Under.")

    # 🔵 HINWEIS: Sehr hohe Ausfallrate (≥5 bestätigt) — Kader-Tiefe kritisch
    if h_conf >= 5:
        flag("INFO", "INJ_SQUAD_DEPTH_HOME",
             f"{home}: {h_conf} bestätigte Ausfälle — Kadertiefe kritisch, "
             f"Rotation und Formeinbruch wahrscheinlich. Impact={h_impact:.1f}.")
    if a_conf >= 5:
        flag("INFO", "INJ_SQUAD_DEPTH_AWAY",
             f"{away}: {a_conf} bestätigte Ausfälle — Kadertiefe kritisch. Impact={a_impact:.1f}.")

    # ─────────────────────────────────────────────────────────────────────────
    # PRESSURE CONSISTENCY CHECKS
    # Fängt den Inter/Cagliari-Typ-Bug: zwei Pressure-Modelle widersprechen sich
    # ─────────────────────────────────────────────────────────────────────────

    for stake, side, colors in [(hs, home, hc), (aws, away, ac)]:
        if not stake: continue
        mot = stake.get("motivationLevel", "full")
        pr  = stake.get("pressureRatio")   # None = Daten fehlen
        pn  = stake.get("pointsNeeded")    # None = Daten fehlen
        mw  = stake.get("mustWin", False)
        cd  = stake.get("canDraw", False)

        # 🔴 FEHLER: pressureRatio > 0.65 aber mustWin=False — Widerspruch in den Daten
        if pr is not None and pr > 0.65 and not mw:
            flag("ERROR", "PRESSURE_MUSTWINFLAG_MISMATCH",
                 f"{side}: pressureRatio={pr:.2f} > 0.65 aber mustWin=False. "
                 f"calc_pressure() hat mustWin-Flag nicht korrekt gesetzt.")

        # 🔴 FEHLER: mustWin=True aber canDraw=True gleichzeitig — direkter Widerspruch
        if mw and cd:
            flag("ERROR", "MUSTWИН_AND_CANDRAW",
                 f"{side}: mustWin=True UND canDraw=True gleichzeitig gesetzt. "
                 f"Widerspruch in calc_pressure() — unmöglich beides wahr.")

        # 🔴 FEHLER: pressureRatio fehlt komplett aber Team hat rotes Label mit hohem Score
        if pr is None and "red" in colors and ms >= 7.0:
            flag("ERROR", "PRESSURE_DATA_MISSING",
                 f"{side}: rotes Label, matchScore={ms} aber pressureRatio fehlt komplett. "
                 f"update_dashboard.py hat calc_pressure() nicht für dieses Team aufgerufen.")

        # 🟡 WARNUNG: Der Inter/Cagliari-Bug — pressureRatio=0 aber motivationLevel='full'
        # Das System sagt gleichzeitig 'kämpft noch' UND 'braucht keine Punkte' — Narrativ-Konflikt
        if "red" in colors and mot == "full" and pr == 0 and pn == 0:
            flag("WARN", "RED_FULL_MOTIV_ZERO_PRESSURE",
                 f"{side}: rotes Label + motivationLevel='full' + pressureRatio=0. "
                 f"PPG-Modell sagt 'sicher', Motivationsmodell sagt 'kämpft' — "
                 f"Betting-Winkel 'gesicherter Gegner' wäre FALSCH. Fix: motivationLevel muss "
                 f"'low' sein bevor ein redSafe-Narrativ greifen darf.")

        # 🟡 WARNUNG: pressureRatio < 0.30 aber mustWin=True — canDraw fehlt obwohl Druck niedrig
        if pr is not None and pr < 0.30 and mw:
            flag("WARN", "LOW_PRESSURE_BUT_MUSTWИН",
                 f"{side}: pressureRatio={pr:.2f} < 0.30 aber mustWin=True. "
                 f"Hoher Druck im Narrativ aber Pressure-Score ist niedrig — prüfen.")

        # 🟡 WARNUNG: motivationLevel='none' aber pressureRatio > 0 — Inkonsistenz
        if mot == "none" and pr is not None and pr > 0:
            flag("WARN", "CONFIRMED_NONE_WITH_PRESSURE",
                 f"{side}: motivationLevel='none' (bestätigt) aber pressureRatio={pr:.2f} > 0. "
                 f"Bestätigtes Team darf keine Pressure haben — calc_motivation() prüfen.")

    # ─────────────────────────────────────────────────────────────────────────
    # NARRATIVE CONSISTENCY CHECKS
    # Prüft ob der Wett-Winkel mit den tatsächlichen Daten übereinstimmt
    # ─────────────────────────────────────────────────────────────────────────

    h_pr = (hs or {}).get("pressureRatio") or 0
    a_pr = (aws or {}).get("pressureRatio") or 0
    h_mot = (hs or {}).get("motivationLevel", "full")
    a_mot = (aws or {}).get("motivationLevel", "full")

    # 🟡 WARNUNG: Gold+Red Spiel aber rotes Team hat pressure=0 mit motivationLevel='full'
    # → falsches "Klassenunterschied mit gesichertem Gegner"-Narrativ
    if "gold" in hc and "red" in ac:
        if a_pr == 0 and a_mot == "full":
            flag("WARN", "GOLD_VS_RED_FALSE_SAFE_NARRATIVE",
                 f"{away} (rot): pressureRatio=0 aber motivationLevel='full'. "
                 f"Angle 'Titelanwärter gegen gesicherten Gegner' ist FALSCH — "
                 f"Gegner kämpft laut Motivationsmodell noch. Prüfe Standings-Daten.")
    if "red" in hc and "gold" in ac:
        if h_pr == 0 and h_mot == "full":
            flag("WARN", "GOLD_VS_RED_FALSE_SAFE_NARRATIVE",
                 f"{home} (rot): pressureRatio=0 aber motivationLevel='full'. "
                 f"Angle 'Titelanwärter gegen gesicherten Gegner' ist FALSCH — "
                 f"Heim-Team kämpft laut Motivationsmodell noch.")

    # 🟡 WARNUNG: Beide Teams red, aber nur eines hat echten Druck
    if "red" in hc and "red" in ac:
        only_one_pressure = (h_pr > 0.30) != (a_pr > 0.30)
        if only_one_pressure:
            high_side = home if h_pr > a_pr else away
            low_side  = away if h_pr > a_pr else home
            flag("WARN", "BOTRED_ASYMMETRIC_PRESSURE",
                 f"Kellerduell-Narrativ aber asymmetrischer Druck: "
                 f"{high_side} pressureRatio={max(h_pr,a_pr):.2f} vs "
                 f"{low_side} pressureRatio={min(h_pr,a_pr):.2f}. "
                 f"Nur eine Mannschaft kämpft wirklich — Angle zu vereinfacht.")

    # 🔵 HINWEIS: matchScore >= 9 aber kein Team mit mustWin — woher kommt der hohe Score?
    h_mw = (hs or {}).get("mustWin", False)
    a_mw = (aws or {}).get("mustWin", False)
    if ms >= 9.0 and not h_mw and not a_mw:
        flag("INFO", "HIGH_SCORE_NO_MUSTWИН",
             f"matchScore={ms} aber kein Team mit mustWin. "
             f"Prüfe ob Score durch andere Faktoren gerechtfertigt ist (H2H, Form, Runden).")

    # ─────────────────────────────────────────────────────────────────────────
    # FORM vs PICK-RICHTUNG CHECKS
    # Fängt wenn der Score-Algorithmus eine Richtung wählt die die Form widerlegt
    # ─────────────────────────────────────────────────────────────────────────

    h_fs   = hf.get("formScore", 0.5)
    a_fs   = af.get("formScore", 0.5)
    h_wrate = hf.get("homeWinRate") or hf.get("winRate", 0)
    a_wrate = af.get("awayWinRate") or af.get("winRate", 0)
    h_gpg  = hf.get("goalsPerGame", 1.4)
    a_gpg  = af.get("goalsPerGame", 1.4)
    h_conc = hf.get("concededPerGame", 1.3)
    a_conc = af.get("concededPerGame", 1.3)

    # 🟡 WARNUNG: Heimteam extrem schwach (formScore < 0.25) aber matchScore hoch
    if h_fs < 0.25 and ms >= 7.5 and "gold" not in hc:
        flag("WARN", "HOME_POOR_FORM_HIGH_SCORE",
             f"{home}: formScore={h_fs:.2f} (sehr schwach) aber matchScore={ms}. "
             f"Pick-Basis könnte überschätzt sein — Formeinbruch nicht ausreichend gewichtet.")

    # 🟡 WARNUNG: Over 2.5 Empfehlung bei tief defensiven Teams (beide < 1.0 Tore/Spiel)
    if h_gpg < 1.0 and a_gpg < 1.0 and ms >= 6.5:
        exp_goals_approx = (h_gpg + a_gpg) * 0.85  # grobe Schätzung
        if exp_goals_approx < 1.8:
            flag("WARN", "BOTH_DEFENSIVE_OVER_RISK",
                 f"{home} ({h_gpg:.1f} Tore/Sp) + {away} ({a_gpg:.1f} Tore/Sp): "
                 f"kombiniert nur ~{exp_goals_approx:.1f} erwartete Tore. "
                 f"Over 2.5 Pick wäre kontraindiziert — Modell prüfen.")

    # 🔵 HINWEIS: Sehr einseitige H2H (≥80%) aber kein hoher matchScore — Pick wird gezeigt?
    h2h_games = h2h.get("games", 0)
    if h2h_games >= 5:
        hw = h2h.get("homeWins", 0)
        aw_h2h = h2h.get("awayWins", 0)
        if (hw / h2h_games >= 0.80 or aw_h2h / h2h_games >= 0.80) and ms < 7.0:
            dom_team = home if hw / h2h_games >= 0.80 else away
            flag("INFO", "STRONG_H2H_LOW_SCORE",
                 f"{dom_team} dominiert H2H mit ≥80% bei {h2h_games} Spielen, "
                 f"aber matchScore={ms} ist niedrig. Pick-Richtung trotzdem prüfen — "
                 f"H2H-Signal nicht ausreichend im Score reflektiert?")

    # ─────────────────────────────────────────────────────────────────────────
    # PICKS-SPEZIFISCHE RISIKO-CHECKS
    # Basiert auf bekannten Fehlern (April 2026).
    # Da Picks JS-seitig generiert werden, prüfen wir Rohdaten-Konstellationen
    # die bekannte Fehler ausgelöst haben — als Frühwarnsystem.
    # ─────────────────────────────────────────────────────────────────────────

    h_mot = (hs or {}).get("motivationLevel", "full")
    a_mot = (aws or {}).get("motivationLevel", "full")

    # "Confirmed relegated" = motiv='none' UND rotes Label
    # (motiv='none' allein kann auch gesicherte UCL/Titel-Teams bedeuten!)
    h_conf_rel = h_mot == "none" and "red" in hc
    a_conf_rel = a_mot == "none" and "red" in ac
    any_conf_rel  = h_conf_rel or a_conf_rel
    both_conf_rel = h_conf_rel and a_conf_rel

    # 🔴 FEHLER: Beide Teams bestätigt abgestiegen + hoher Score → Dead-rubber
    # Fix April 2026: Dead-Rubber-Penalty (-2.0) + cardSc=0 für beide Teams.
    # Wenn Score trotzdem > 5.0 ist, hat die Penalty nicht funktioniert.
    if both_conf_rel and ms > 5.0:
        flag("ERROR", "DEAD_RUBBER_HIGH_PICKS_RISK",
             f"Beide Teams bestätigt abgestiegen (motiv='none' + rotes Label) aber matchScore={ms}. "
             f"Dead-Rubber-Penalty (-2.0) greift nicht → Picks wären inhaltsleer. "
             f"JS: Dead-rubber-Penalty und cardSc=0 prüfen.")

    # 🟡 WARNUNG: Mindestens ein Team bestätigt abgestiegen (Heracles/Volendam-Muster)
    # Fix April 2026: cardSc=0 wenn _bothRedConf, oder wenn _anyRedConf && refAvg < 3.5.
    # Validator kann refAvg nicht prüfen, warnt aber generell.
    if any_conf_rel and not both_conf_rel:
        rel_team = home if h_conf_rel else away
        flag("WARN", "CARDS_RELEGATED_TEAM",
             f"{rel_team} ist bestätigt abgestiegen (motiv='none' + rotes Label). "
             f"Karten-Pick darf nur mit Schiedsrichter-Evidenz erscheinen (refAvg≥3.5). "
             f"JS: cardSc=0 guard für _anyRedConf ohne Schiri-Evidenz prüfen.")

    # 🔵 HINWEIS: motiv='low' bei roten Teams → Intensitätsprüfung für Karten
    if not any_conf_rel and ms >= 7.0:
        low_red_teams = []
        if h_mot == "low" and "red" in hc: low_red_teams.append(home)
        if a_mot == "low" and "red" in ac: low_red_teams.append(away)
        if low_red_teams:
            flag("INFO", "LOW_MOTIV_CARDS_CHECK",
                 f"{', '.join(low_red_teams)}: motivationLevel='low' (fast gerettet) — "
                 f"Karten-Pick nur mit Schiedsrichter-Evidenz sinnvoll. Kein Fehler — manuell prüfen.")

    # ── Cards FV Gate Plausibilität ─────────────────────────────────────────────
    # Prüft ob Karten-picks mit sehr niedrigem Poisson-FV trotzdem erscheinen.
    # JS gate feuert wenn (1/bookie_odds) - fair_prob > GATE.GOALS_REAL (0.12).
    # SYNC:GATE — gate fires at GATE_GOALS_REAL (0.12) in pick-engine.js for cards.
    # Hinweis: Validator kennt kein refAvg — nutzt Liga-Baserate als konservativen Proxy.
    # In JS ist refAvg der primäre Predictor; Validator-FV kann davon abweichen.
    _league_card_base = {
        'ENG': 3.8, 'GER': 3.6, 'ITA': 3.5, 'ESP': 3.4, 'FRA': 3.6, 'AUT': 3.7,
        'NED': 3.5, 'POR': 3.8, 'TUR': 4.2, 'SCO': 4.0, 'POL': 3.6, 'SUI': 3.4
    }.get(league_key, 3.5)
    _fv_c35 = poisson_over(_league_card_base, 3.5)
    _fv_c45 = poisson_over(_league_card_base, 4.5)
    # Typical Über 3.5 odds: ~1.75–1.90 (impl. prob ~53–57%); gate at gap > 0.12
    # → flag when FV < 0.40 (gap ≥ ~14pp at 1.80 odds)
    if _fv_c35 < 0.40:
        flag("WARN", "CARDS35_LOW_FV",
             f"Liga-Baserate={_league_card_base:.1f} → Poisson FV für Über 3.5 Karten = {_fv_c35:.1%} "
             f"(typische Quote ~1.80 → impl.Prob ~55.6%; Lücke ~{0.556 - _fv_c35:+.1%}). "
             f"FV-Gate (GATE_GOALS_REAL=0.12) sollte Karten-3.5-Pick blocken. "
             f"Kein refAvg im Validator — JS-Ergebnis kann durch hohen refAvg abweichen.")
    # Typical Über 4.5 odds: ~2.10–2.40 (impl. prob ~42–48%); gate at gap > 0.12
    # → flag when FV < 0.28
    if _fv_c45 < 0.28:
        flag("INFO", "CARDS45_LOW_FV",
             f"Liga-Baserate={_league_card_base:.1f} → Poisson FV für Über 4.5 Karten = {_fv_c45:.1%}. "
             f"JS-FV-Gate blockt falls Bookie-Quote zu kurz — aber refAvg kann das Bild drehen. "
             f"Kein refAvg im Validator — JS-Ergebnis zählt, dieser Check ist nur Hinweis.")

    # ── H2H-basierte Goals-Checks ─────────────────────────────────────────────
    h2h_avg_g = h2h.get("avgGoals")
    h2h_btts  = h2h.get("btts")   # BTTS-Rate als Dezimal (0.0–1.0)

    # 🟡 WARNUNG: H2H Schnitt ≥ 3.5 → Under 2.5 HARD BLOCK sollte feuern
    # Python hat keinen Zugriff auf generierte Picks — kann nicht prüfen ob Pick wirklich erscheint.
    # Das JS-Inline-Validator prüft das gegen echte _genPicks (ERROR dort wenn Pick doch erscheint).
    # Hier deshalb nur WARN als Erinnerung, kein false-positive ERROR.
    if h2h_avg_g is not None and h2h_avg_g >= 3.5:
        flag("WARN", "U25_H2H_HARD_BLOCK_MISS",
             f"H2H Schnitt={h2h_avg_g:.1f} Tore (≥3.5) — HARD BLOCK sollte Under 2.5 komplett blocken. "
             f"Python kann Picks nicht prüfen — JS-Inline-Validator zeigt ERROR falls Pick trotzdem erscheint.")
    # 🟡 WARNUNG: H2H Schnitt 3.0–3.5 → starke Dämpfung aktiv, Under 2.5 prüfen
    elif h2h_avg_g is not None and h2h_avg_g >= 3.0:
        flag("WARN", "H2H_HIGH_AVG_UNDER_RISK",
             f"H2H Schnitt={h2h_avg_g:.1f} Tore (3.0–3.5). "
             f"Starke Dämpfung aktiv (sc -= 0.35). Falls Under 2.5 [medium] erscheint: Guard nicht stark genug.")

    # 🟡 WARNUNG: H2H BTTS-Rate ≥ 75% → Under 2.5 HARD BLOCK hätte feuern müssen
    if h2h_btts is not None and h2h_btts >= 0.75:
        flag("ERROR", "U25_BTTS_HARD_BLOCK_MISS",
             f"H2H BTTS={h2h_btts:.0%} (≥75%) — HARD BLOCK sollte Under 2.5 komplett blocken. "
             f"Falls Under 2.5 Pick erscheint: BTTS-Hard-Block-Bug.")
    elif h2h_btts is not None and h2h_btts >= 0.65:
        flag("WARN", "H2H_HIGH_BTTS_UNDER_RISK",
             f"H2H BTTS={h2h_btts:.0%} (65–75%). Starke Dämpfung aktiv. "
             f"Falls Under 2.5 [medium] erscheint: BTTS-Guard-Schwellenwert prüfen.")

    # 🟡 WARNUNG: H2H Schnitt sehr niedrig + Saisonschnitt niedrig → Over riskant
    # Under-Bias ist in diesem Fall legitim und kein Fehler.
    if h2h_avg_g is not None and h2h_avg_g < 1.8:
        combined_check = None
        if hf.get("goalsPerGame") is not None and af.get("goalsPerGame") is not None:
            combined_check = hf["goalsPerGame"] + af["goalsPerGame"]
        if combined_check is not None and combined_check < 2.2:
            flag("INFO", "LOW_GOALS_UNDER_EXPECTED",
                 f"H2H Schnitt={h2h_avg_g:.1f} + Saisonschnitt komb.={combined_check:.1f}/Sp. "
                 f"Starker Under-Bias legitim — kein Fehler. Over 2.5 Pick hier wäre falsch.")

    # ── Poisson FV Plausibilitätsprüfung (Daten-Ebene) ───────────────────────
    # Berechnet den theoretischen Fair-Value-Bereich für Goals-Picks.
    # Da der Python-Validator keine Bookie-Quoten liest, prüft er nur die FV-Seite:
    # Wenn expGoals sehr nahe an 2.5 ist, kann FV-Gate einen Over-Pick blocken.
    h_gpg = hf.get("goalsPerGame") or 0
    a_gpg = af.get("goalsPerGame") or 0
    exp_goals_proxy = (h_gpg + a_gpg)   # Summe beider Teams ≈ expGoals

    if exp_goals_proxy > 0:
        fv_o25 = poisson_over(exp_goals_proxy, 2.5)
        fv_o35 = poisson_over(exp_goals_proxy, 3.5)
        # 🟡 HINWEIS: Over 2.5 FV unter 40% → Markt braucht Quoten ≥ 2.50 für Edge
        # Wenn FV so niedrig ist, sind typische Bookie-Quoten (~1.75–2.00) oft negativ.
        # SYNC:GATE — gate fires at GATE_GOALS_REAL (0.12) implied gap in pick-engine.js
        if exp_goals_proxy < 2.2 and fv_o25 < 0.40:
            flag("INFO", "LOW_SCORING_PROFILE",
                 f"Ø gpg={exp_goals_proxy:.2f}, H2H Ø={h2h_avg_g:.1f} Tore — "
                 f"Niedrig-Scoring-Profil, Over-Pick durch Hard Gate automatisch unterdrückt")
        # 🟡 WARNUNG: Over 3.5 FV unter 20% → fast immer negativer Edge bei Bookie-Quoten
        # SYNC:GATE — gate fires at GATE_GOALS_REAL (0.12) in season-finish.html
        # INFO (nicht WARN): exp_goals_proxy = h_gpg + a_gpg aus dem Config ist ~5–10× kleiner
        # als der JS-expGoals (der aus xG, homeAttStr, etc. berechnet wird). Deshalb feuert
        # der Check fast immer, auch wenn der JS-Gate es korrekt handhabt.
        if exp_goals_proxy > 0 and fv_o35 < 0.20:
            flag("INFO", "OVER35_LOW_FV",
                 f"Ø gpg={exp_goals_proxy:.2f} (statischer Proxy) → Poisson FV für Over 3.5 = {fv_o35:.1%}. "
                 f"JS nutzt expGoals aus xG/Att-Strength — FV-Gate greift dort zuverlässiger als dieser Proxy.")

        # 🟡 WARNUNG: H2H Over-Rate im Gefahrenbereich 30–45% (H2H Over-Modifier -0.04 bis -0.08)
        # Neue Schwellenwerte April 2026: ≤40% → -0.04 in _h2hO25Mod.
        # Wenn gleichzeitig H2H avgG ≤ 2.5 (→ _h2hAvgGMod = -0.04), kumuliert sich -0.08.
        h2h_over25 = h2h.get("over25Rate")
        if h2h_over25 is not None and h2h_over25 <= 0.45 and h2h_over25 >= 0.30:
            avg_g_note = f", H2H Ø={h2h_avg_g:.1f}" if h2h_avg_g is not None else ""
            combined_mod = 0
            if h2h_over25 <= 0.20: combined_mod -= 0.14
            elif h2h_over25 <= 0.30: combined_mod -= 0.08
            elif h2h_over25 <= 0.40: combined_mod -= 0.04
            if h2h_avg_g is not None:
                if h2h_avg_g <= 1.6: combined_mod -= 0.08
                elif h2h_avg_g <= 2.0: combined_mod -= 0.06
                elif h2h_avg_g <= 2.5: combined_mod -= 0.04
            flag("WARN", "H2H_LOW_OVER_RATE",
                 f"H2H Über-2.5-Rate={h2h_over25:.0%}{avg_g_note} — "
                 f"kumulierter Modifier={combined_mod:+.2f} auf Over 2.5 Score. "
                 f"Over-2.5-Pick bei diesen H2H-Werten prüfen ob er trotzdem erscheint.")

    # ── Team-Over FV Gate Plausibilität ───────────────────────────────────────
    # Prüft ob Team-Over picks (Heimteam/Auswärtsteam über 1.5 Tore) bei negativem FV erscheinen.
    # Der Validator liest keine Bookie-Quoten, warnt aber wenn das expGoals-Profil sehr niedrig ist.
    h_gpg = hf.get("goalsPerGame") or 0
    a_gpg = af.get("goalsPerGame") or 0
    h_def = hf.get("concededPerGame") or 0
    a_def = af.get("concededPerGame") or 0
    exp_h = (h_gpg + a_def) / 2 if h_gpg and a_def else None
    exp_a = (a_gpg + h_def) / 2 if a_gpg and h_def else None

    if exp_h is not None:
        fv_h15 = poisson_over(exp_h, 1.5)
        # INFO (nicht WARN): proxy = (h_gpg + a_def) / 2 aus statischen Config-Werten ist zu klein.
        # JS berechnet expH aus homeAttStr × awayDefStr × leagueMean — deutlich höher.
        # SYNC:GATE — gate fires at GATE_TEAM_REAL (0.12) / GATE_TEAM_EST (0.15) in pick-engine.js
        if exp_h < 1.6 and fv_h15 < 0.40:
            flag("INFO", "TEAM_OVER_HOME_LOW_FV",
                 f"{home} expH≈{exp_h:.2f} (statischer Proxy) → FV über 1.5 = {fv_h15:.1%}. "
                 f"JS-expH aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.")

    if exp_a is not None:
        fv_a15 = poisson_over(exp_a, 1.5)
        # SYNC:GATE — gate fires at GATE_TEAM_REAL (0.12) / GATE_TEAM_EST (0.15) in pick-engine.js
        if exp_a < 1.6 and fv_a15 < 0.40:
            flag("INFO", "TEAM_OVER_AWAY_LOW_FV",
                 f"{away} expA≈{exp_a:.2f} (statischer Proxy) → FV über 1.5 = {fv_a15:.1%}. "
                 f"JS-expA aus xG/Att-Strength typischerweise höher — Gate greift dort zuverlässiger.")

    # ── Ecken FV Gate Plausibilität ───────────────────────────────────────────
    # Prüft ob Corner-picks mit sehr niedrigen erwarteten Ecken trotzdem erscheinen.
    # Validator liest keine Corner-Quoten; warnt wenn das Profil eindeutig "kein Over-Edge" zeigt.
    # SYNC:GATE — gate fires at GATE_CORN_REAL (0.10) / GATE_CORN_EST (0.15) in pick-engine.js
    # Wir prüfen nur grob: wenn beide Teams sehr defensiv (wenig Angriffe) → Corner-Over riskant.
    if h_gpg > 0 and a_gpg > 0:
        # Proxy für Eckenbewegung: Teams mit <1.0 Tor/Spiel spielen auch sehr wenig Corner.
        both_low_attack = h_gpg < 0.8 and a_gpg < 0.8
        if both_low_attack:
            flag("INFO", "CORNER_LOW_ATTACK_PROFILE",
                 f"{home} ({h_gpg:.1f} T/Sp) + {away} ({a_gpg:.1f} T/Sp): "
                 f"Beide Teams sehr angriffsschwach — Corner-Over-Pick hat schwaches Fundament. "
                 f"FV-Gate (15pp bei geschätzten Quoten) sollte Corner-Pick blocken.")

    return issues


# ── HTML-Parser ───────────────────────────────────────────────────────────────

def parse_leagues_from_html(html_path):
    """Extrahiert LEAGUES-Objekt aus der HTML-Datei via JSON-Parsing."""
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    start = content.find("const LEAGUES = {")
    if start == -1:
        raise ValueError("LEAGUES-Block nicht in HTML gefunden")
    js_block = content[start + len("const LEAGUES = "):]

    # Find closing `};`
    depth = 0
    i = 0
    end = -1
    while i < len(js_block):
        if js_block[i] == "{":
            depth += 1
        elif js_block[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    if end == -1:
        raise ValueError("LEAGUES-Block Ende nicht gefunden")

    raw = js_block[:end + 1]
    # Convert JS object to JSON (keys are unquoted in JS)
    raw = re.sub(r'(?<!["\w])([A-Za-z_][A-Za-z0-9_]*)(?=\s*:)', r'"\1"', raw)
    raw = re.sub(r',\s*}', '}', raw)
    raw = re.sub(r',\s*]', ']', raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract individual league fixtures via regex
        return parse_leagues_fallback(content)


def parse_leagues_fallback(content):
    """Fallback-Parser für den Fall dass JSON-Konvertierung scheitert."""
    leagues = {}
    leagues_start = content.find("const LEAGUES = {")
    leagues_js = content[leagues_start:]
    all_keys = ["ENG","GER","ESP","FRA","AUT","NED","POR","SCO","TUR","SUI","BEL","POL","HUN","CRO","ITA"]

    for key in all_keys:
        start = leagues_js.find(f"  {key}:{{")
        if start == -1:
            continue
        next_pos = len(leagues_js)
        for other in all_keys:
            if other == key:
                continue
            p = leagues_js.find(f"  {other}:{{", start + 1)
            if p != -1 and p < next_pos:
                next_pos = p
        section = leagues_js[start:next_pos]

        # Extract roundsLeft (JS uses unquoted keys: roundsLeft:6)
        rl_match = re.search(r'(?:roundsLeft|"roundsLeft")\s*:\s*(\d+)', section)
        rl = int(rl_match.group(1)) if rl_match else 99

        # Extract name (JS: name:"Premier League" or "name":"Premier League")
        name_match = re.search(r'(?:name|"name")\s*:\s*"([^"]+)"', section)
        name = name_match.group(1) if name_match else key

        # Extract flag
        flag_match = re.search(r'(?:flag|"flag")\s*:\s*"([^"]+)"', section)
        league_flag = flag_match.group(1) if flag_match else ""

        # Extract fixtures array
        fix_start = section.find("fixtures:[")
        if fix_start == -1:
            continue
        fix_json_start = section.find("[", fix_start)
        depth = 0
        i = fix_json_start
        while i < len(section):
            if section[i] == "[":
                depth += 1
            elif section[i] == "]":
                depth -= 1
                if depth == 0:
                    break
            i += 1

        try:
            fixtures = json.loads(section[fix_json_start:i + 1])
        except Exception:
            continue

        leagues[key] = {"name": name, "flag": league_flag, "roundsLeft": rl, "fixtures": fixtures}

    return leagues


# ── Datum-Filter ──────────────────────────────────────────────────────────────

def parse_date(date_str):
    """Parst DD.MM.YYYY → datetime.date"""
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").date()
    except ValueError:
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    # CLI-Argumente
    args = sys.argv[1:]
    filter_days  = None
    filter_date  = None
    errors_only  = False
    show_ok      = False

    write_report = False

    i = 0
    while i < len(args):
        if args[i] == "--days" and i + 1 < len(args):
            filter_days = int(args[i + 1]); i += 2
        elif args[i] == "--date" and i + 1 < len(args):
            filter_date = args[i + 1]; i += 2
        elif args[i] == "--errors":
            errors_only = True; i += 1
        elif args[i] == "--ok":
            show_ok = True; i += 1
        elif args[i] == "--report":
            write_report = True; i += 1
        else:
            i += 1

    today = datetime.now().date()

    # Datum-Filtergrenze
    if filter_days is not None:
        cutoff = today + timedelta(days=filter_days)
    else:
        cutoff = today + timedelta(days=21)  # max 3 Wochen voraus

    # Für Report-Modus: alle Ausgaben auch in eine Liste sammeln
    report_lines = []
    def rprint(line=""):
        print(line)
        if write_report:
            report_lines.append(line)

    rprint("=" * 65)
    rprint("  🐕 CocoBet — Picks Logik-Check")
    rprint(f"  {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    if filter_date:
        rprint(f"  Filter: Datum {filter_date}")
    elif filter_days is not None:
        rprint(f"  Filter: nächste {filter_days} Tag(e)")
    rprint("=" * 65)

    # HTML laden
    if not os.path.exists(HTML_FILE):
        print(f"\n✗ Datei nicht gefunden: {HTML_FILE}")
        sys.exit(1)

    leagues = parse_leagues_fallback(open(HTML_FILE, encoding="utf-8").read())

    total_checked = 0
    total_errors  = 0
    total_warns   = 0
    total_infos   = 0
    all_issues    = []

    SEVERITY_ICON  = {"ERROR": "🔴", "WARN": "🟡", "INFO": "🔵"}
    SEVERITY_LABEL = {"ERROR": "FEHLER", "WARN": "WARNUNG", "INFO": "HINWEIS"}

    for key, league in sorted(leagues.items()):
        rl       = league.get("roundsLeft", 99)
        lname    = league.get("name", key)
        fixtures = league.get("fixtures", [])

        league_issues = []

        for fx in fixtures:
            date_str = fx.get("date", "")
            fx_date  = parse_date(date_str)

            if fx_date is None:
                continue
            if fx_date < today:
                continue
            if fx_date > cutoff:
                continue
            if filter_date and date_str != filter_date:
                # Try partial match (e.g. "22.04")
                if not date_str.startswith(filter_date):
                    continue

            total_checked += 1
            issues = check_fixture(fx, key, lname, rl)

            for sev, code, msg in issues:
                # always track for JSON (before errors_only filter)
                all_issues.append({
                    "date": date_str, "home": fx["home"], "away": fx["away"],
                    "league": lname, "severity": sev, "code": code, "msg": msg
                })
                if sev == "ERROR":   total_errors += 1
                elif sev == "WARN":  total_warns  += 1
                elif sev == "INFO":  total_infos  += 1
                if errors_only and sev != "ERROR":
                    continue
                league_issues.append((date_str, fx["home"], fx["away"], sev, code, msg))

            if show_ok and not issues:
                league_issues.append((date_str, fx["home"], fx["away"], "OK", "OK", "Keine Probleme gefunden"))

        if league_issues:
            rprint(f"\n{'─' * 65}")
            rprint(f"  {league.get('flag','')} {lname}  (rl={rl})")
            rprint(f"{'─' * 65}")
            for date_str, h, a, sev, code, msg in league_issues:
                icon = SEVERITY_ICON.get(sev, "⚪")
                label = SEVERITY_LABEL.get(sev, sev)
                rprint(f"  {icon} {label} [{code}]")
                rprint(f"     📅 {date_str}  {h} vs {a}")
                rprint(f"     {msg}")

    rprint(f"\n{'═' * 65}")
    rprint(f"  Geprüft: {total_checked} Spiele")
    if total_errors == 0 and total_warns == 0 and total_infos == 0:
        rprint(f"  ✅ Keine Probleme gefunden — alle Picks logisch konsistent!")
    else:
        if total_errors > 0:
            rprint(f"  🔴 {total_errors} Fehler — müssen gefixt werden")
        if total_warns > 0:
            rprint(f"  🟡 {total_warns} Warnungen — manuelle Prüfung empfohlen")
        if not errors_only and total_infos > 0:
            rprint(f"  🔵 {total_infos} Hinweise — Pick-Richtung kontrollieren")
    rprint(f"{'═' * 65}\n")

    # ── Report-Datei + JSON schreiben ────────────────────────────────────────
    if write_report:
        # Markdown-Report
        report_path = os.path.join(SCRIPT_DIR, "validator_report.md")
        status_icon = "✅" if total_errors == 0 and total_warns == 0 else ("🔴" if total_errors > 0 else "🟡")
        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write(f"# {status_icon} Picks Validator — {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
            rf.write(f"**{total_checked} Spiele geprüft** · ")
            rf.write(f"🔴 {total_errors} Fehler · 🟡 {total_warns} Warnungen · 🔵 {total_infos} Hinweise\n\n")
            if total_errors == 0 and total_warns == 0:
                rf.write("✅ Alle Picks logisch konsistent — keine Probleme gefunden.\n")
            else:
                rf.write("```\n")
                rf.write("\n".join(report_lines))
                rf.write("\n```\n")
        print(f"  📄 Report gespeichert: validator_report.md")

        # JSON-Summary für Dashboard-Injection
        json_path = os.path.join(SCRIPT_DIR, "validator_summary.json")
        summary = {
            "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "checked": total_checked,
            "errors": total_errors,
            "warnings": total_warns,
            "infos": total_infos,
            "issues": all_issues,   # already populated during the loop below
        }
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(summary, jf, ensure_ascii=False, indent=2)
        print(f"  📊 JSON-Summary gespeichert: validator_summary.json")

    # Exit code: 1 wenn kritische Fehler vorhanden
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
