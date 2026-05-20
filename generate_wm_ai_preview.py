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
        "max_tokens": 300,
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
    """SHA-256 über die relevanten Felder — ändert sich wenn Picks/Odds aktualisiert."""
    relevant = {
        "picks":  [(p.get("market"), p.get("verdict"), p.get("edgePP"), p.get("odds"))
                   for p in data.get("picks", [])],
        "hw":     data.get("hw"),
        "aw":     data.get("aw"),
        "homeElo": data.get("homeElo"),
        "awayElo": data.get("awayElo"),
        "upsetScore": data.get("upsetScore"),
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:16]


# ── Prompt Builder ────────────────────────────────────────────────────────────
def build_prompt(info: dict) -> str:
    """
    Baut den strukturierten Prompt aus den Match-Daten.
    info enthält: home, away, date, group, matchday, homeElo, awayElo,
                  upsetScore, picks, homeForm, awayForm, h2h, coHostBonus
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
    underdog = away if h_elo > a_elo else home
    upset    = info.get("upsetScore", 2)

    picks    = info.get("picks", [])
    bet_picks = [p for p in picks if p.get("verdict") == "BET"]
    abw_picks = [p for p in picks if p.get("verdict") == "ABWÄGEN"]

    home_form = info.get("homeForm")
    away_form = info.get("awayForm")
    h2h       = info.get("h2h")
    co_host   = info.get("coHostBonus", False)

    # Picks-Zusammenfassung
    picks_text = ""
    if bet_picks:
        p = bet_picks[0]
        picks_text = (f"Unser Modell sieht Edge bei {p['market']} @{p.get('odds','?')} "
                      f"(+{p.get('edgePP','?')}pp). ")
    elif abw_picks:
        p = abw_picks[0]
        picks_text = f"Möglicher Wert bei {p['market']} @{p.get('odds','?')} — abwägen. "

    # Form-Zusammenfassung
    form_text = ""
    if home_form and away_form:
        h_pts = home_form.get("avgGoals", "?")
        a_pts = away_form.get("avgGoals", "?")
        form_text = (f"{home} erzielt im Schnitt {h_pts} Tore/Spiel, "
                     f"{away} {a_pts}. ")

    # H2H
    h2h_text = ""
    if h2h and h2h.get("games", 0) >= 3:
        g = h2h["games"]
        hw = h2h.get("homeWins", 0)
        dr = h2h.get("draws", 0)
        aw = h2h.get("awayWins", 0)
        h2h_text = f"Direktvergleich ({g} Spiele): {hw}W-{dr}U-{aw}A für {home}. "

    # Co-Host
    cohost_text = f"{home} genießt als Co-Gastgeber Heimvorteil. " if co_host else ""

    # Upset
    upset_text = ""
    if upset >= 7:
        upset_text = (f"Trotz des Elo-Unterschieds von {elo_diff} Punkten ist ein Upset möglich "
                      f"(Upset Score: {upset}/10). ")
    elif upset >= 5:
        upset_text = f"Ausgeglichenes Spiel auf dem Papier (Elo-Gap: {elo_diff}). "

    context = (
        f"Spiel: {home} vs {away} | Gruppe {group}, Spieltag {matchday} | {date_str}\n"
        f"Elo: {home} {h_elo} vs {away} {a_elo} | Favorit: {fav} (Gap {elo_diff})\n"
        f"{cohost_text}"
        f"{form_text}"
        f"{h2h_text}"
        f"{picks_text}"
        f"{upset_text}"
    ).strip()

    return f"""Du bist CocoBet, ein deutschsprachiger Sportwetten-Analyst. Schreibe eine prägnante Match-Vorschau für die WM 2026.

Daten:
{context}

Regeln:
- Genau 3 Sätze, kein Mehr, kein Weniger
- Deutsch, journalistischer Stil, sachlich und direkt
- Kein Hype, keine Emojis, kein Clickbait
- Erwähne den Favoritstatus, einen taktischen Aspekt, und einen konkreten Wetthinweis (falls vorhanden)
- Kein "Laut unserem Modell" — schreibe aus Analysten-Perspektive
- Maximal 80 Wörter gesamt

Schreibe nur die 3 Sätze, nichts davor oder danach."""


def build_tg_snippet(full_text: str) -> str:
    """Kürzt auf max 2 Sätze für Telegram (kompakter Intro)."""
    sentences = [s.strip() for s in full_text.split(".") if s.strip()]
    return ". ".join(sentences[:2]) + ("." if len(sentences) >= 2 else "")


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
    groups = wm.get("groups", {})
    picks_all = wm.get("picks", {})
    odds_all  = wm.get("odds", {})
    upset_scores = wm.get("upsetScores", {})
    form_all  = wm.get("form", {})
    h2h_all   = wm.get("h2h", {})

    now = datetime.now(timezone.utc)
    cutoff = (now + timedelta(days=PREVIEW_DAYS)).date()

    CO_HOSTS = {"MEX", "USA", "CAN"}

    total = generated = skipped = errors = 0

    for gkey, gdata in groups.items():
        teams_map = {t["id"]: t for t in gdata.get("teams", [])}

        for fx in gdata.get("fixtures", []):
            home_id  = fx["home"]
            away_id  = fx["away"]
            pick_key = f"{gkey}-{fx['matchday']}-{home_id}-{away_id}"
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

            info = {
                "home":       home_t.get("name", home_id),
                "away":       away_t.get("name", away_id),
                "date":       fx["date"],
                "group":      gkey,
                "matchday":   fx["matchday"],
                "homeElo":    home_t.get("elo", 1500),
                "awayElo":    away_t.get("elo", 1500),
                "upsetScore": upset_scores.get(pick_key, 2),
                "picks":      fx_picks,
                "hw":         fx_odds.get("hw"),
                "aw":         fx_odds.get("aw"),
                "homeForm":   form_all.get(home_id),
                "awayForm":   form_all.get(away_id),
                "h2h":        h2h_all.get(f"{home_id}-{away_id}"),
                "coHostBonus": home_id in CO_HOSTS,
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
