#!/usr/bin/env python3
"""
BetEdge — Daily Picks Logic Validator
======================================
Liest season-finish.html, extrahiert alle anstehenden Spiele und prüft
jeden Pick auf logische Konsistenz. Gibt strukturierte Fehler/Warnungen aus.

Aufruf:
    python3 check_picks_logic.py              # alle kommenden Spiele
    python3 check_picks_logic.py --days 1     # nur heute & morgen
    python3 check_picks_logic.py --date 22.04 # bestimmtes Datum
    python3 check_picks_logic.py --errors     # nur kritische Fehler

Prüft automatisch auf:
  🔴 FEHLER   — definitive Logik-Bugs (z.B. mustWin auf bestätigtem Abstieg)
  🟡 WARNUNG  — verdächtige Konstellationen (z.B. red-safe mit Panik-Text)
  🔵 HINWEIS  — schwache Pick-Basis (z.B. H2H dominiert aber kein Kontext)
"""

import json
import re
import sys
import os
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE  = os.path.join(SCRIPT_DIR, "season-finish.html")

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
        if not stake: return False
        mot = stake.get("motivationLevel", "full")
        pr  = stake.get("pressureRatio", 0)
        pn  = stake.get("pointsNeeded", 0)
        return "red" in colors and mot != "none" and pr == 0 and pn == 0

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
        else:
            i += 1

    today = datetime.now().date()

    # Datum-Filtergrenze
    if filter_days is not None:
        cutoff = today + timedelta(days=filter_days)
    else:
        cutoff = today + timedelta(days=21)  # max 3 Wochen voraus

    print("=" * 65)
    print("  BetEdge — Picks Logik-Check")
    print(f"  {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    if filter_date:
        print(f"  Filter: Datum {filter_date}")
    elif filter_days is not None:
        print(f"  Filter: nächste {filter_days} Tag(e)")
    print("=" * 65)

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

    SEVERITY_ICON = {"ERROR": "🔴", "WARN": "🟡", "INFO": "🔵"}
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
                if errors_only and sev != "ERROR":
                    continue
                league_issues.append((date_str, fx["home"], fx["away"], sev, code, msg))
                if sev == "ERROR":   total_errors += 1
                elif sev == "WARN":  total_warns  += 1
                elif sev == "INFO":  total_infos  += 1

            if show_ok and not issues:
                league_issues.append((date_str, fx["home"], fx["away"], "OK", "OK", "Keine Probleme gefunden"))

        if league_issues:
            print(f"\n{'─' * 65}")
            print(f"  {league.get('flag','')} {lname}  (rl={rl})")
            print(f"{'─' * 65}")
            for date_str, h, a, sev, code, msg in league_issues:
                icon = SEVERITY_ICON.get(sev, "⚪")
                label = SEVERITY_LABEL.get(sev, sev)
                print(f"  {icon} {label} [{code}]")
                print(f"     📅 {date_str}  {h} vs {a}")
                print(f"     {msg}")

    print(f"\n{'═' * 65}")
    print(f"  Geprüft: {total_checked} Spiele")
    if total_errors == 0 and total_warns == 0 and total_infos == 0:
        print(f"  ✅ Keine Probleme gefunden — alle Picks logisch konsistent!")
    else:
        if total_errors > 0:
            print(f"  🔴 {total_errors} Fehler — müssen gefixt werden")
        if total_warns > 0:
            print(f"  🟡 {total_warns} Warnungen — manuelle Prüfung empfohlen")
        if not errors_only and total_infos > 0:
            print(f"  🔵 {total_infos} Hinweise — Pick-Richtung kontrollieren")
    print(f"{'═' * 65}\n")

    # Exit code: 1 wenn kritische Fehler vorhanden
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
