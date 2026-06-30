#!/usr/bin/env python3
"""
generate_wm_ai_preview.py — CocoBet WM 2026 AI Match Previews

Generates 3-4 sentence German match previews for each WM fixture using
the Claude API (claude-haiku-4-5 — fast and cost-efficient).

Caching: each fixture gets a picks+odds hash stored alongside the preview.
If the hash hasn't changed since last run, the preview is not regenerated
(saves API calls when nothing is new).

Only generates previews for:
  - Fixtures within the next PREVIEW_DAYS days (default: 14)
  - OR all fixtures if FORCE_ALL=true env var is set

Output: writes aiPreviews into wm2026-data.json under ["aiPreviews"][pick_key]
  {
    "text":        "3-4 Sätze...",
    "tgSnippet":   "1-2 Sätze für Telegram...",
    "generatedAt": "ISO timestamp",
    "hash":        "sha256 of input data"
  }

Umgebungsvariablen:
  ANTHROPIC_API_KEY   — Claude API Key (required)
  FORCE_ALL           — 'true' regeneriert alle Spiele, ignoriert Cache
  PREVIEW_DAYS        — wie viele Tage voraus generiert wird (Standard: 14)
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
BASE     = Path(__file__).parent
WM_FILE  = BASE / "wm2026-data.json"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FORCE_ALL         = os.environ.get("FORCE_ALL", "").lower() == "true"
PREVIEW_DAYS      = int(os.environ.get("PREVIEW_DAYS", "14"))

MODEL = "claude-haiku-4-5-20251001"   # Schnell + günstig für strukturierte Outputs

# Rate limit: max 5 req/s bei Haiku — wir machen 1/s um sicher zu sein
DELAY_BETWEEN_CALLS = 1.2  # Sekunden


# ── Anthropic API (ohne SDK-Dependency-Problem im GH Action) ─────────────────
import urllib.request
import urllib.error

def claude_complete(prompt: str) -> str | None:
    """Ruft die Claude API direkt via HTTP auf (kein anthropic-Paket nötig im Edge-Case)."""
    if not ANTHROPIC_API_KEY:
        return None
    url  = "https://api.anthropic.com/v1/messages"
    body = json.dumps({
        "model":      MODEL,
        "max_tokens": 400,
        "messages":   [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type":      "application/json",
        "x-api-key":         ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        print(f"  ❌ Claude API HTTP {e.code}: {e.read().decode()[:200]}")
        return None
    except Exception as e:
        print(f"  ❌ Claude API Fehler: {e}")
        return None


# ── Input-Hash für Cache ──────────────────────────────────────────────────────
def compute_hash(data: dict) -> str:
    """SHA-256 über die relevanten Felder — ändert sich wenn Picks/Odds/xG aktualisiert.

    H6 Fix 05.06.2026 — Cache-Buster erweitert:
    Vorher fehlten modelOdds, injuries, h2h, form_games, corners_exp im Hash →
    wenn das Modell sich änderte (z.B. neue Devig-Math, neue Travel-Discount-
    Faktoren), wurden ALTE AI-Previews ausgespielt obwohl der Pick-Inhalt
    eigentlich umgewichtet werden müsste. Jetzt: alle Input-Signale die der
    Prompt verwendet, gehen in den Hash.
    """
    relevant = {
        "picks":   [
            (
                p.get("market"),
                p.get("verdict"),
                p.get("edgePP"),
                p.get("odds"),
                p.get("modelOdds"),     # H6: model-only Änderungen erkennen
                p.get("dataQuality"),   # H6: dataQ-Wechsel = neue Konfidenz
                p.get("convictionScore"),    # v5 (09.06): Conviction-Score in Prompt
                p.get("sharpMoveActive"),    # v5 (09.06): Sharp-Move-Flag
            )
            for p in data.get("picks", [])
        ],
        "hw":          data.get("hw"),
        "aw":          data.get("aw"),
        "dr":          data.get("dr"),
        "homeElo":     data.get("homeElo"),
        "awayElo":     data.get("awayElo"),
        "upsetScore":  data.get("upsetScore"),
        "xgHome":      data.get("xgHome"),
        "xgAway":      data.get("xgAway"),
        # H6: weitere Modell-Inputs die Prompt v3 referenziert
        "injuries":    sorted([
            (i.get("playerId") or i.get("name", ""), i.get("status", ""))
            for i in (data.get("injuries") or [])
        ]),
        "h2hGames":    (data.get("h2h") or {}).get("games"),
        "formHGames":  (data.get("formHome") or {}).get("games"),
        "formAGames":  (data.get("formAway") or {}).get("games"),
        "cornersExp":  data.get("cornersExp"),
        # Prompt-Version erhöht → erzwingt globale Regeneration aller alten Previews
        "_promptVersion": 5,   # v5 (09.06.2026): Conviction-Score + Sharp-Move + Familien im Prompt
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ── Prompt Builder ────────────────────────────────────────────────────────────
def build_prompt(info: dict) -> str:
    """
    Baut den strukturierten Prompt aus den Match-Daten.
    info enthält: home, away, date, group, matchday, homeElo, awayElo,
                  upsetScore, picks, homeForm, awayForm, h2h, coHostBonus,
                  xgHome, xgAway, xgSource, cornersHome, cornersAway
    """
    home     = info["home"]
    away     = info["away"]
    date_str = info.get("date", "")
    group    = info.get("group", "")
    matchday = info.get("matchday", 1)
    h_elo    = info.get("homeElo", 1500)
    a_elo    = info.get("awayElo", 1500)
    elo_diff = abs(h_elo - a_elo)
    fav      = home if h_elo > a_elo else away
    upset    = info.get("upsetScore", 2)

    picks     = info.get("picks", [])
    bet_picks = [p for p in picks if p.get("verdict") == "BET"]
    abw_picks = [p for p in picks if p.get("verdict") == "ABWÄGEN"]

    home_form    = info.get("homeForm") or {}
    away_form    = info.get("awayForm") or {}
    h2h          = info.get("h2h") or {}
    co_host      = info.get("coHostBonus", False)
    xg_home      = info.get("xgHome")
    xg_away      = info.get("xgAway")
    xg_source    = info.get("xgSource", "poisson")
    corners_home = info.get("cornersHome") or {}
    corners_away = info.get("cornersAway") or {}

    lines = []

    # ── Spielinfo ─────────────────────────────────────────────────────────────
    lines.append(f"Spiel: {home} vs {away} | WM 2026 Gruppe {group}, Spieltag {matchday} | {date_str}")
    lines.append(f"Elo-Rating: {home} {h_elo} vs {away} {a_elo} | Favorit: {fav} (Differenz: {elo_diff})")

    if co_host:
        lines.append(f"WICHTIG: {home} ist Co-Gastgeber — spielt praktisch zuhause (Heimvorteil).")

    # ── Formcheck ─────────────────────────────────────────────────────────────
    if home_form.get("games", 0) >= 3:
        h_scored  = home_form.get("avgScored", home_form.get("avgGoals", "?"))
        h_conc    = home_form.get("avgConceded", "?")
        h_o25     = home_form.get("over25Rate")
        h_btts    = home_form.get("bttsRate")
        h_last5   = home_form.get("last5", "")
        h_games   = home_form.get("games", "?")
        form_parts = [f"{home} (letzte {h_games} Spiele): {h_scored} Tore/Spiel erzielt, {h_conc} kassiert"]
        if h_last5:
            form_parts.append(f"Form: {h_last5}")
        if h_o25 is not None:
            form_parts.append(f"Over 2.5: {round(h_o25*100)}% der Spiele")
        if h_btts is not None:
            form_parts.append(f"BTTS: {round(h_btts*100)}%")
        lines.append(" | ".join(form_parts))

    if away_form.get("games", 0) >= 3:
        a_scored  = away_form.get("avgScored", away_form.get("avgGoals", "?"))
        a_conc    = away_form.get("avgConceded", "?")
        a_o25     = away_form.get("over25Rate")
        a_btts    = away_form.get("bttsRate")
        a_last5   = away_form.get("last5", "")
        a_games   = away_form.get("games", "?")
        form_parts = [f"{away} (letzte {a_games} Spiele): {a_scored} Tore/Spiel erzielt, {a_conc} kassiert"]
        if a_last5:
            form_parts.append(f"Form: {a_last5}")
        if a_o25 is not None:
            form_parts.append(f"Over 2.5: {round(a_o25*100)}% der Spiele")
        lines.append(" | ".join(form_parts))

    # ── Verletzungen & Sperren ────────────────────────────────────────────────
    injuries_home = info.get("injuriesHome") or []
    injuries_away = info.get("injuriesAway") or []
    inj_lines = []
    for inj in injuries_home[:3]:
        name   = inj.get("name", "?")
        reason = inj.get("reason", inj.get("type", ""))
        inj_lines.append(f"{name} ({home}, {reason})")
    for inj in injuries_away[:3]:
        name   = inj.get("name", "?")
        reason = inj.get("reason", inj.get("type", ""))
        inj_lines.append(f"{name} ({away}, {reason})")
    if inj_lines:
        lines.append(f"WICHTIG — Verletzungen/Sperren: {'; '.join(inj_lines)}. "
                     f"Das muss in der Vorschau erwähnt werden.")

    # ── xG ────────────────────────────────────────────────────────────────────
    if xg_home is not None and xg_away is not None:
        if xg_source == "api_football":
            lines.append(f"xG (API-Football, echte Daten): {home} {xg_home} — {away} {xg_away} erwartet")
        else:
            # Poisson = Schätzung, nicht als echte xG präsentieren
            lines.append(f"Torerwartung (Modell-Schätzung, kein API-Football xG verfügbar): "
                         f"{home} ca. {xg_home} — {away} ca. {xg_away}")

    # ── Ecken ─────────────────────────────────────────────────────────────────
    h_c_for   = corners_home.get("forAvg")
    h_c_games = corners_home.get("games", 0)
    a_c_for   = corners_away.get("forAvg")
    if h_c_for and a_c_for and h_c_games >= 3:
        total_c = round((h_c_for or 0) + (a_c_for or 0), 1)
        lines.append(f"Ecken-Schnitt: {home} {h_c_for}/Spiel, {away} {a_c_for}/Spiel → Summe ~{total_c}/Spiel")

    # ── H2H ───────────────────────────────────────────────────────────────────
    if h2h.get("games", 0) >= 3:
        g  = h2h["games"]
        hw = h2h.get("homeWins", 0)
        dr = h2h.get("draws", 0)
        aw = h2h.get("awayWins", 0)
        ag = h2h.get("avgGoals")
        h2h_str = f"H2H ({g} Spiele): {home} {hw}S-{dr}U-{aw}N"
        if ag:
            h2h_str += f" | Schnitt {ag} Tore/Spiel"
        lines.append(h2h_str)

    # ── Upset-Wahrscheinlichkeit ───────────────────────────────────────────────
    if upset >= 7:
        lines.append(f"Upset-Score: {upset}/10 — Überraschung trotz {elo_diff} Elo-Differenz möglich")
    elif upset >= 5:
        lines.append(f"Ausgeglichener als Elo nahelegt — Upset-Score {upset}/10")

    # ── Picks + Engine-Kontext (Conviction, Sharp-Move, Familien) ────────
    pick_lines = []
    for p in (bet_picks + abw_picks)[:3]:
        v     = p.get("verdict", "")
        mkt   = p.get("market", "")
        odds  = p.get("odds", "?")
        edge  = p.get("edgePP", "?")
        dq    = p.get("dataQuality", "")
        conv  = p.get("convictionScore")
        fams  = p.get("convictionFamilies") or {}
        sm    = p.get("sharpMoveActive")
        dq_note = " [nur Elo-Daten]" if dq == "elo_only" else ""
        extras = []
        if conv is not None:
            extras.append(f"Conviction {conv}/10")
        if sm:
            sm_d = p.get("sharpMoveDetails") or {}
            mv = sm_d.get("pinn_move_pp", 0)
            extras.append(f"Sharp-Move Pinnacle {mv:+.1f}pp seit Eröffnung")
        # Steam-Move zuverlässig aus dem Trigger (17.06.2026) — nicht nur odds_history.
        smv = p.get("steamMovePP")
        if smv and not sm:
            extras.append(f"Pinnacle-Move {p.get('steamOpen')}→{p.get('steamCur')} (+{smv}pp seit Eröffnung)")
        if p.get("softConfirmed"):
            extras.append("Soft-Konsens bestätigt den Move")
        elif p.get("softFollowPP") is not None and p.get("softFollowPP", 0) > 0:
            extras.append(f"Soft-Konsens folgt (+{p.get('softFollowPP')}pp)")
        if p.get("safeDerived"):
            extras.append(f"sichere Linie abgeleitet (These war {p.get('safeThesisMarket')} @{p.get('safeThesisOdds')})")
        if fams:
            active_fams = [f"{k}={v}" for k, v in fams.items() if v > 0]
            if active_fams:
                extras.append("Familien aktiv: " + ", ".join(active_fams))
        extra_str = f" [{'; '.join(extras)}]" if extras else ""
        pick_lines.append(f"{v}: {mkt} @{odds} (Edge +{edge}pp){dq_note}{extra_str}")
    if pick_lines:
        lines.append("Picks/Edge: " + " | ".join(pick_lines))
    else:
        lines.append("Picks: Kein klarer Edge identifiziert — kein aktiver Pick.")

    # ── Engine-Signal-Adjustments (auf den Top-Pick) ─────────────────────
    top_pick = (bet_picks + abw_picks)[:1]
    if top_pick:
        signals = top_pick[0].get("signals") or []
        if signals:
            sig_parts = []
            for s in signals[:5]:
                name = (s.get("name") or "").replace("_signal", "").replace("_", " ")
                score = s.get("score", 0)
                if abs(score) >= 0.3:
                    sig_parts.append(f"{name} {score:+.1f}pp")
            if sig_parts:
                lines.append("Engine-Signale (Top-Pick): " + ", ".join(sig_parts))
            adj = top_pick[0].get("signalAdjustmentPP")
            if isinstance(adj, (int, float)) and abs(adj) >= 0.5:
                lines.append(f"Engine-Netto-Adjustment: {adj:+.1f}pp auf rohen Edge")

    context = "\n".join(lines)

    return f"""Du bist CocoBet, ein deutschsprachiger Sportwetten-Analyst für die WM 2026. Schreibe eine prägnante Match-Vorschau.

MATCH-DATEN:
{context}

AUFGABE:
Schreibe exakt 4 Sätze auf Deutsch. Stil: journalistisch, sachlich, konkret — wie ein erfahrener Tipster, nicht ein Nachrichtenreporter.

SATZ 1: Kräfteverhältnis — Wer ist Favorit, wie groß ist der Abstand, was sagen Elo und Form?
SATZ 2: Spielcharakter — Was erwarten wir taktisch/statistisch? (Tore, Ecken, BTTS, Stil basierend auf Form)
SATZ 3: Wetthinweis — Nenne den konkreten Pick. WICHTIG zur Begründung: unser Modell ist
        Steam-Following, NICHT Pinnacle-schlagen. Die Begründung ist also NICHT ein Preis-Edge
        (der ist bei einem bestätigten Move bauartbedingt ~0 — schreibe NIE "kein Value", wenn
        ein Pinnacle-Move + Signale da sind!), sondern: Pinnacle hat die Quote in Pick-Richtung
        bewegt (Sharp Money) UND die Signale bestätigen die Richtung. Conviction einbauen:
        8+/10 = "stark bestätigt", 6-7 = "solide gestützt", 4-5 = "Beobachten, Bestätigung dünn".
        Wenn eine sichere Linie abgeleitet wurde: kurz erklären, dass der Move zwar auf der
        riskanten Linie kam, wir aber die sicherere Linie spielen (höhere Trefferquote).
        Nur wenn WIRKLICH kein Move und kein Pick da ist: ehrlich "heute kein klares Signal".
SATZ 4: Kontext — Co-Gastgeber-Vorteil, H2H-Besonderheit, Upset-Risiko, Gruppenrelevanz, ODER
        wenn ein Engine-Signal (Hitze/Klima-Dome, Travel, Höhe, Anreiz, Druck, Aufstellung) stark
        feuert: das konkret nennen.

REGELN:
- Kein "Laut Modell" oder "Laut Daten" — schreibe aus Analysten-Perspektive
- Kein Hype, keine Emojis, kein Clickbait
- Der Pinnacle-Move + Signal-Bestätigung ist die Story, nicht der Preis-Edge
- Wenn kein Pick: trotzdem einen interessanten Aspekt über das Spiel erwähnen
- Wenn Conviction-Score sehr niedrig (≤3) bei BET: ehrlich auf "noch dünne Bestätigung" hinweisen
- Maximal 130 Wörter gesamt
- Nur die 4 Sätze, nichts davor oder danach"""


def build_tg_snippet(full_text: str) -> str:
    """
    Wählt den informativen Satz für Telegram aus.
    Strategie: Satz 3 (Wetthinweis/Pick) ist am wertvollsten.
    Falls kein Pick → Satz 1 (Kräfteverhältnis) + Satz 2 (Spielcharakter).
    """
    sentences = [s.strip() for s in full_text.split(".") if len(s.strip()) > 10]
    if not sentences:
        return full_text[:200]

    # Satz 3 = Wetthinweis (Index 2) bevorzugen wenn er Pick-Keywords enthält
    pick_keywords = ("BET", "ABWÄGEN", "@", "Edge", "Value", "Quote", "Pick",
                     "kein klarer", "kein Value", "empfehlen", "setzen", "Tipp")
    pick_sentence = None
    for s in sentences:
        if any(kw.lower() in s.lower() for kw in pick_keywords):
            pick_sentence = s.strip()
            break

    if pick_sentence:
        # Pick-Satz + Kontext-Satz (Satz 1 als Einleitung)
        intro = sentences[0].strip() if sentences else ""
        if intro and intro != pick_sentence:
            return intro + ". " + pick_sentence + "."
        return pick_sentence + "."

    # Kein Pick: Satz 1 + 2
    return ". ".join(sentences[:2]) + "."


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=== generate_wm_ai_preview.py ===")

    if not ANTHROPIC_API_KEY:
        print("  ❌  ANTHROPIC_API_KEY nicht gesetzt — abgebrochen")
        sys.exit(0)   # Nicht als Fehler werten, Action läuft weiter

    if not WM_FILE.exists():
        print(f"  ❌  {WM_FILE} nicht gefunden")
        sys.exit(1)

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    previews: dict = wm.setdefault("aiPreviews", {})
    groups       = wm.get("groups", {})
    picks_all    = wm.get("picks", {})
    odds_all     = wm.get("odds", {})
    upset_scores = wm.get("upsetScores", {})
    form_all     = wm.get("form", {})
    h2h_all      = wm.get("h2h", {})
    xg_stats     = wm.get("xgStats", {})       # from fetch_wm_corners.py
    corners_form = wm.get("cornersForm", {})    # from fetch_wm_corners.py

    now = datetime.now(timezone.utc)
    cutoff = (now + timedelta(days=PREVIEW_DAYS)).date()

    CO_HOSTS = {"MEX", "USA", "CAN"}

    total = generated = skipped = errors = 0

    # 29.06.2026 (Lucas: „keine Preview in der KO-Phase"): KO-Spiele liegen in koFixtures, nicht groups
    # → bisher nie bepreviewt. Iteration vereinheitlicht: Gruppen + bothResolved KO (globale Team-Union,
    # gkey="KO", matchday=Runden-Code → pick_key "KO-R32-…" wie generate_wm_picks).
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
            odds_key = f"{home_id}-{away_id}"

            # Datum prüfen
            try:
                fx_date = datetime.strptime(fx["date"], "%Y-%m-%d").date()
            except Exception:
                continue

            if not FORCE_ALL and fx_date > cutoff:
                continue   # Zu weit in der Zukunft

            total += 1
            home_t = teams_map.get(home_id, {})
            away_t = teams_map.get(away_id, {})
            fx_picks = picks_all.get(pick_key, [])
            fx_odds  = odds_all.get(odds_key, {})

            # xG: compute expected goals from xgStats (API-Football) if available
            xg_h_data = xg_stats.get(home_id, {})
            xg_a_data = xg_stats.get(away_id, {})
            xg_home = xg_away = None
            xg_source = "poisson"
            if (xg_h_data.get("games", 0) >= 3 and xg_a_data.get("games", 0) >= 3):
                xg_home   = round((xg_h_data["xgForAvg"] + xg_a_data["xgAgainstAvg"]) / 2, 2)
                xg_away   = round((xg_a_data["xgForAvg"] + xg_h_data["xgAgainstAvg"]) / 2, 2)
                xg_source = "api_football"

            info = {
                "home":         home_t.get("name", home_id),
                "away":         away_t.get("name", away_id),
                "date":         fx["date"],
                "group":        gkey,
                "matchday":     md,
                "homeElo":      home_t.get("elo", 1500),
                "awayElo":      away_t.get("elo", 1500),
                "upsetScore":   upset_scores.get(pick_key, 2),
                "picks":        fx_picks,
                "hw":           fx_odds.get("hw"),
                "aw":           fx_odds.get("aw"),
                "homeForm":     form_all.get(home_id),
                "awayForm":     form_all.get(away_id),
                "h2h":          h2h_all.get(f"{home_id}-{away_id}"),
                "coHostBonus":  home_id in CO_HOSTS,
                # xG (API-Football when available, else None)
                "xgHome":       xg_home,
                "xgAway":       xg_away,
                "xgSource":     xg_source,
                # Corner averages per team
                "cornersHome":  corners_form.get(home_id),
                "cornersAway":  corners_form.get(away_id),
                # Verletzungen & Sperren (ab WM-Start via fetch_wm_injuries.py)
                "injuriesHome": wm.get("injuries", {}).get(home_id, {}).get("players"),
                "injuriesAway": wm.get("injuries", {}).get(away_id, {}).get("players"),
            }

            new_hash = compute_hash(info)
            existing = previews.get(pick_key, {})

            # Cache-Check: überspringen wenn Hash identisch
            if not FORCE_ALL and existing.get("hash") == new_hash and existing.get("text"):
                skipped += 1
                print(f"  ○ {info['home']} vs {info['away']} — Cache OK")
                continue

            print(f"  🤖 {info['home']} vs {info['away']} ({fx['date']})…", end="", flush=True)

            prompt = build_prompt(info)
            text   = claude_complete(prompt)

            if not text:
                errors += 1
                print(" ❌ Fehler")
                continue

            tg_snippet = build_tg_snippet(text)
            previews[pick_key] = {
                "text":        text,
                "tgSnippet":   tg_snippet,
                "generatedAt": now.isoformat(),
                "hash":        new_hash,
            }
            generated += 1
            print(f" ✅ ({len(text)} Zeichen)")

            # Rate limiting
            time.sleep(DELAY_BETWEEN_CALLS)

    # Zurückschreiben
    wm["aiPreviews"] = previews
    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Fertig: {generated} neu generiert, {skipped} gecacht, {errors} Fehler")
    print(f"   Scope: {total} Fixtures innerhalb {PREVIEW_DAYS} Tagen")
    print(f"   Saved: {WM_FILE}")


if __name__ == "__main__":
    main()
