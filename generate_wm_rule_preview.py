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
    # 21.06.2026 (Lucas): KEINE Elo-Wörter/Zahlen mehr — klingt nach Tabellenkalkulation.
    # Favoriten-Framing in normaler Fußball-Sprache.
    if gap >= 250:
        opts = [
            f"{fav} geht als haushoher Favorit in diese Partie",
            f"{fav} ist auf dem Papier klar überlegen",
            f"Alles andere als ein Sieg von {fav} wäre eine Überraschung",
        ]
    elif gap >= 150:
        opts = [
            f"{fav} ist der klare Favorit in diesem Duell",
            f"{fav} geht mit der Favoritenrolle ins Spiel",
            f"Die Rollen sind verteilt: {fav} ist vorne",
        ]
    elif gap >= 75:
        opts = [
            f"{fav} geht als leichter Favorit ins Rennen",
            f"{fav} hat einen kleinen Qualitätsvorteil",
            f"Ein hauchdünner Vorteil für {fav}",
        ]
    else:
        opts = [
            "Auf dem Papier ein offenes Duell",
            "Ein ausgeglichenes Spiel — beide Seiten haben ihre Chance",
            "Schwer auszurechnen: hier ist alles drin",
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

    # KO-fest (06.07.2026): in der KO-Phase ist matchday ein Runden-Code ("R16"/"QF"…), kein int
    # → die Gruppen-Spieltag-Logik (int-Vergleich) crasht sonst (TypeError) und killt den KO-Preview.
    if isinstance(matchday, int):
        if matchday >= 3:
            parts.append(f"Im entscheidenden Spieltag {matchday} der Gruppe {group} steht für beide Teams viel auf dem Spiel")
        elif matchday == 2:
            parts.append(f"In Spieltag {matchday} wollen beide Teams wichtige Punkte für die Achtelfinal-Qualifikation sammeln")
    else:
        _ko_lbl = {"R16": "Achtelfinale", "R32": "Sechzehntelfinale", "QF": "Viertelfinale",
                   "SF": "Halbfinale", "F": "Finale", "3P": "Spiel um Platz 3"}.get(str(matchday), "der K.-o.-Runde")
        parts.append(f"Im {_ko_lbl} gilt: wer verliert, fliegt raus — beide Teams müssen alles investieren")

    # Form-Kontext als ZUSÄTZLICHE Farbe (richer) — aber PICK-SICHER (21.06.2026): die
    # Tor-Richtungs-Behauptung darf dem Haupt-Pick NICHT widersprechen (kein „torreich" über
    # einem Unter-Pick). Richtung des Haupt-Picks aus den Picks ableiten und nur konsistente
    # Aussage zulassen.
    _pk = " ".join((p.get("market") or "").lower() for p in (info.get("picks") or [])
                   if not p.get("trackingExcluded") and p.get("verdict") in ("BET", "ABWÄGEN"))
    _wants_over  = any(t in _pk for t in ("über", "over")) or ("beide teams treffen" in _pk and "nein" not in _pk)
    _wants_under = any(t in _pk for t in ("unter", "under")) or ("treffen — nein" in _pk or "btts — nein" in _pk)
    hf = info.get("homeForm")
    af = info.get("awayForm")
    if hf and af:
        hg = hf.get("avgGoals", 0) or 0
        ag = af.get("avgGoals", 0) or 0
        if hg + ag >= 3.2 and not _wants_under:
            parts.append("beide Teams trafen zuletzt regelmäßig — ein torreiches Spiel ist drin")
        elif 0 < hg + ag <= 2.0 and not _wants_over:
            parts.append("zuletzt taten sich beide vor dem Tor schwer — eher eine zähe Partie")

    if not parts:
        opts = [
            "beide Teams wollen früh ein Zeichen setzen",
            "auf der großen WM-Bühne will keiner als Verlierer vom Platz gehen",
            "der Auftakt in die Gruppe ist für beide Mannschaften richtungsweisend",
        ]
        parts.append(random.choice(opts))

    # Bis zu 2 Kontext-Teile für mehr Substanz (richer)
    sel = parts[:2]
    return ". ".join(s[0].upper() + s[1:] for s in sel)


def _pick_phrase(picks: list, home: str, away: str) -> str:
    # 21.06.2026 (Lucas, Single-Source): Pick-Auswahl wie im Telegram/Card-Renderer —
    # BET vor ABWÄGEN, trackingExcluded raus, KEIN edge-Floor (Cards sind nicht edge-gated).
    # So nennt die Vorschau denselben Haupt-Pick wie die Karten darunter (kein Widerspruch).
    live = [p for p in picks
            if not p.get("trackingExcluded") and not p.get("boldAlt")
            and p.get("verdict") in ("BET", "ABWÄGEN")]
    bet_picks = [p for p in live if p.get("verdict") == "BET"]
    abw_picks = [p for p in live if p.get("verdict") == "ABWÄGEN"]

    if bet_picks:
        p    = bet_picks[0]
        edge = p.get("edgePP", "?")
        odds = p.get("odds", "?")
        mkt  = p.get("market", "")
        edge_part = f" — der Markt unterschätzt das um {edge}pp" if isinstance(edge, (int, float)) and edge > 0 else ""
        opts = [
            f"Unser stärkstes Signal heute: {mkt} @{odds}{edge_part}",
            f"Klarer Fall für uns — {mkt} @{odds}{edge_part}",
            f"Wir setzen auf {mkt} @{odds}{edge_part}",
        ]
        return random.choice(opts)
    elif abw_picks:
        p    = abw_picks[0]
        odds = p.get("odds", "?")
        mkt  = p.get("market", "")
        opts = [
            f"Einen genaueren Blick wert: {mkt} @{odds} — hier sieht das Modell Value",
            f"Spannend wird {mkt} @{odds}, wo unser Modell eine Chance erkennt",
            f"Auf der Beobachtungsliste: {mkt} @{odds}",
        ]
        return random.choice(opts)
    else:
        opts = [
            "Heute kein klarer Markt-Vorteil — wir warten auf den besseren Moment",
            "Das Modell sieht hier keine Fehlbewertung — kein Pick",
            "Diesmal halten wir uns zurück: kein ausreichender Vorteil",
        ]
        return random.choice(opts)


def _upset_phrase(score: int, fav: str, underdog: str, gap: int) -> str:
    # Ohne Elo-Zahl (21.06.2026).
    if score >= 8:
        return f"Vorsicht trotz Papierform: {underdog} ist brandgefährlich — ein Upset ist absolut realistisch"
    elif score >= 6:
        return f"Ein Überraschungsergebnis ist nicht ausgeschlossen — {underdog} hat das Zeug dazu"
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

    # 06.07.2026 (Lucas: „keine Previews für anstehende KO-Spiele"): der Fallback iterierte NUR
    # groups → KO-Spiele (koFixtures) bekamen NIE eine Regel-Preview, selbst wenn der Haiku-Lauf
    # (generate_wm_ai_preview) für sie nichts erzeugte. Jetzt Gruppen + bothResolved KO (globale
    # Team-Union, gkey="KO", md=Runden-Code → pick_key "KO-R16-…" wie generate_wm_ai_preview /
    # _iter_match_contexts). Siehe wiederkehrende KO-Datenpfad-Regel. (groups vs koFixtures)
    iter_units = [(gk, {t["id"]: t for t in gd.get("teams", [])}, gd.get("fixtures", []))
                  for gk, gd in groups.items()]
    _all_teams = {}
    for gd in groups.values():
        for t in gd.get("teams", []):
            _all_teams[t["id"]] = t
    _ko = [f for f in (wm.get("koFixtures") or []) if f.get("home") and f.get("away")]
    if _ko:
        iter_units.append(("KO", _all_teams, _ko))

    for gkey, teams_map, fixtures in iter_units:
        for fx in fixtures:
            home_id  = fx["home"]
            away_id  = fx["away"]
            md       = fx.get("matchday") or fx.get("round") or "KO"
            pick_key = f"{gkey}-{md}-{home_id}-{away_id}"

            try:
                fx_date = datetime.strptime(fx["date"], "%Y-%m-%d").date()
            except Exception:
                continue

            if fx_date > cutoff:
                continue

            # FALLBACK-Semantik: nur LÜCKEN füllen — eine bestehende (AI-)Preview mit tgSnippet
            # NICHT mit der schwächeren Regel-Version überschreiben.
            if (previews.get(pick_key) or {}).get("tgSnippet"):
                skipped += 1
                continue

            home_t = teams_map.get(home_id, {})
            away_t = teams_map.get(away_id, {})

            info = {
                "home":       home_t.get("name", home_id),
                "away":       away_t.get("name", away_id),
                "date":       fx["date"],
                "group":      gkey,
                "matchday":   md,
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
