#!/usr/bin/env python3
"""
generate_wm_rule_preview.py — CocoBet WM 2026 Regelbasierte Match-Vorschau

Drop-in Ersatz für generate_wm_ai_preview.py — kein API Key nötig.
Generiert natürlich klingende deutsche Vorschauen aus den Match-Daten.

Schreibt in das gleiche wm2026-data.json["aiPreviews"] Format.
"""

import json
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE    = Path(__file__).parent
WM_FILE = BASE / "wm2026-data.json"

CO_HOSTS     = {"MEX", "USA", "CAN"}
PREVIEW_DAYS = 60   # Abdeckung für gesamte WM inkl. KO-Runden (bis 19. Juli)


# ── Textbausteine ──────────────────────────────────────────────────────────────

def _fav_phrase(fav: str, gap: int) -> str:
    if gap >= 250:
        opts = [
            f"{fav} geht als haushoher Favorit in diese Partie",
            f"{fav} ist der mit Abstand stärkste Gegner im Duell",
            f"Auf dem Papier ist {fav} klar überlegen",
        ]
    elif gap >= 150:
        opts = [
            f"{fav} ist deutlicher Favorit laut Elo-Modell",
            f"{fav} hat einen komfortablen Elo-Vorsprung",
            f"Das Modell sieht {fav} klar vorne",
        ]
    elif gap >= 75:
        opts = [
            f"{fav} geht als leichter Favorit ins Rennen",
            f"{fav} hat einen moderaten Qualitätsvorteil",
            f"Leichte Überlegenheit für {fav} laut Elo",
        ]
    else:
        opts = [
            "Auf dem Papier ein offenes Duell",
            "Die Elo-Werte liegen eng beieinander",
            "Ausgeglichene Partie — alles ist möglich",
        ]
    return random.choice(opts)


def _context_phrase(home: str, away: str, info: dict) -> str:
    co_host = info.get("coHostBonus")
    h2h     = info.get("h2h")
    matchday = info.get("matchday", 1)
    group   = info.get("group", "")
    home_elo = info.get("homeElo", 1500)
    away_elo = info.get("awayElo", 1500)
    fav = home if home_elo >= away_elo else away

    parts = []

    if co_host:
        parts.append(f"{home} genießt als Co-Gastgeber den Heimvorteil vor eigenem Publikum")

    if h2h and h2h.get("games", 0) >= 3:
        g   = h2h["games"]
        hw  = h2h.get("homeWins", 0)
        dr  = h2h.get("draws", 0)
        aw  = h2h.get("awayWins", 0)
        if hw > aw + dr:
            parts.append(f"Im Direktvergleich ({g} Spiele) hat {home} die Nase klar vorne ({hw}S-{dr}U-{aw}N)")
        elif aw > hw + dr:
            parts.append(f"{away} dominiert den Direktvergleich ({aw}S-{dr}U-{hw}N aus {g} Spielen)")
        elif dr >= hw and dr >= aw:
            parts.append(f"Historisch oft Unentschieden zwischen diesen Teams ({dr} von {g} Spielen)")
        else:
            parts.append(f"Enger Direktvergleich: {hw}S-{dr}U-{aw}N aus {g} Spielen")

    if matchday >= 3:
        parts.append(f"Im entscheidenden Spieltag {matchday} der Gruppe {group} steht für beide Teams viel auf dem Spiel")
    elif matchday == 2:
        parts.append(f"In Spieltag {matchday} wollen beide Teams wichtige Punkte für die Achtelfinal-Qualifikation sammeln")

    if not parts:
        # Fallback: Form
        hf = info.get("homeForm")
        af = info.get("awayForm")
        if hf and af:
            hg = hf.get("avgGoals", 0) or 0
            ag = af.get("avgGoals", 0) or 0
            if hg > ag + 0.5:
                parts.append(f"{home} zeigt die offensivstärkere Form der letzten Wochen ({hg:.1f} vs {ag:.1f} Tore/Spiel)")
            elif ag > hg + 0.5:
                parts.append(f"{away} kommt in besserer Torform in dieses Spiel ({ag:.1f} vs {hg:.1f} Tore/Spiel)")
            else:
                parts.append(f"Beide Teams kommen mit ähnlicher Torquote in diese Partie")
        else:
            opts = [
                f"Beide Teams wollen früh ein Zeichen setzen",
                f"Auf der großen WM-Bühne will keiner als Verlierer vom Platz gehen",
                f"Der Auftakt in die Gruppe ist für beide Mannschaften richtungsweisend",
            ]
            parts.append(random.choice(opts))

    return parts[0] if parts else ""


def _pick_phrase(picks: list, home: str, away: str) -> str:
    bet_picks = [p for p in picks if p.get("verdict") == "BET" and p.get("edgePP", 0) >= 4]
    abw_picks = [p for p in picks if p.get("verdict") == "ABWÄGEN" and p.get("edgePP", 0) >= 4]

    if bet_picks:
        p    = bet_picks[0]
        edge = p.get("edgePP", "?")
        odds = p.get("odds", "?")
        mkt  = p.get("market", "")
        opts = [
            f"Unser Modell sieht klar Edge auf {mkt} @{odds} (+{edge}pp gegenüber dem Markt)",
            f"Das stärkste Signal: {mkt} @{odds} mit einem Edge von +{edge}pp",
            f"Konkret empfehlen wir {mkt} @{odds} — der Markt unterschätzt diese Option um {edge}pp",
        ]
        return random.choice(opts)
    elif abw_picks:
        p    = abw_picks[0]
        odds = p.get("odds", "?")
        mkt  = p.get("market", "")
        return f"Potenzielle Value-Option bei {mkt} @{odds} — die Quote ist interessant, aber Edge knapp"
    else:
        opts = [
            "Kein klarer Markt-Edge identifiziert — beobachten und abwarten",
            "Das Modell sieht keine ausreichende Fehlbewertung durch den Markt",
            "Wir verzichten heute auf eine konkrete Wettempfehlung",
        ]
        return random.choice(opts)


def _upset_phrase(score: int, fav: str, underdog: str, gap: int) -> str:
    if score >= 8:
        return f"Trotz der Papierform ist {underdog} gefährlich — Elo-Gap von nur {gap} Punkten macht einen Upset realistisch"
    elif score >= 6:
        return f"Ein Überraschungsergebnis ist nicht ausgeschlossen — {underdog} hat das Potenzial zu überraschen"
    return ""


# ── Haupt-Generator ────────────────────────────────────────────────────────────

def build_preview(info: dict) -> tuple[str, str]:
    """Gibt (full_text, tg_snippet) zurück."""
    home     = info["home"]
    away     = info["away"]
    home_elo = info.get("homeElo", 1500)
    away_elo = info.get("awayElo", 1500)
    gap      = abs(home_elo - away_elo)
    fav      = home if home_elo >= away_elo else away
    underdog = away if home_elo >= away_elo else home
    upset    = info.get("upsetScore", 2)
    picks    = info.get("picks", [])

    s1 = _fav_phrase(fav, gap) + "."
    s2 = _context_phrase(home, away, info) + "."
    s3 = _pick_phrase(picks, home, away) + "."

    # Optionaler 4. Satz bei Upset-Potenzial
    s4 = ""
    if upset >= 6:
        s4_raw = _upset_phrase(upset, fav, underdog, gap)
        if s4_raw:
            s4 = " " + s4_raw + "."

    full = f"{s1} {s2} {s3}{s4}".strip()

    # TG Snippet: Satz 1 + 2 (oder 1 + 3 wenn S2 redundant)
    tg = f"{s1} {s2}".strip()

    return full, tg


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== generate_wm_rule_preview.py ===")

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    previews = wm.setdefault("aiPreviews", {})
    groups   = wm.get("groups", {})
    picks_all    = wm.get("picks", {})
    odds_all     = wm.get("odds", {})
    upset_scores = wm.get("upsetScores", {})
    form_all     = wm.get("form", {})
    h2h_all      = wm.get("h2h", {})

    now     = datetime.now(timezone.utc)
    cutoff  = (now + timedelta(days=PREVIEW_DAYS)).date()

    generated = skipped = 0

    for gkey, gdata in groups.items():
        teams_map = {t["id"]: t for t in gdata.get("teams", [])}

        for fx in gdata.get("fixtures", []):
            home_id  = fx["home"]
            away_id  = fx["away"]
            pick_key = f"{gkey}-{fx['matchday']}-{home_id}-{away_id}"

            try:
                fx_date = datetime.strptime(fx["date"], "%Y-%m-%d").date()
            except Exception:
                continue

            if fx_date > cutoff:
                continue

            home_t = teams_map.get(home_id, {})
            away_t = teams_map.get(away_id, {})

            info = {
                "home":       home_t.get("name", home_id),
                "away":       away_t.get("name", away_id),
                "date":       fx["date"],
                "group":      gkey,
                "matchday":   fx["matchday"],
                "homeElo":    home_t.get("elo", 1500),
                "awayElo":    away_t.get("elo", 1500),
                "upsetScore": upset_scores.get(pick_key, 2),
                "picks":      picks_all.get(pick_key, []),
                "homeForm":   form_all.get(home_id),
                "awayForm":   form_all.get(away_id),
                "h2h":        h2h_all.get(f"{home_id}-{away_id}"),
                "coHostBonus": home_id in CO_HOSTS,
            }

            full, tg = build_preview(info)
            previews[pick_key] = {
                "text":        full,
                "tgSnippet":   tg,
                "generatedAt": now.isoformat(),
                "hash":        "rule-based",
            }
            generated += 1
            print(f"  ✓ {info['home']} vs {info['away']}")
            print(f"    → {full}")
            print()

    wm["aiPreviews"] = previews
    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    print(f"✅ {generated} Previews generiert → wm2026-data.json")


if __name__ == "__main__":
    main()
