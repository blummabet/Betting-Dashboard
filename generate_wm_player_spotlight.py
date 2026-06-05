#!/usr/bin/env python3
"""
generate_wm_player_spotlight.py — CocoBet WM 2026 Player Spotlight

Wählt 2-3 Spieler pro Woche aus und generiert:
  - Telegram Player Spotlight Card
  - JSON-Daten für Event Page Section

Spieler-Auswahl-Algorithmus:
  1. Nur Spieler deren Team in den nächsten SPOTLIGHT_DAYS Tagen spielt
  2. Scoring-Rate-Modell: goals / (minutes / 90) → Tore/Spiel
  3. Spotlight-Score: Scoring-Rate × Positions-Bonus × Popularitäts-Bonus
  4. Edge vs. Marktquote (wenn Player Props vorhanden)
  5. Keine Wiederholung: bereits gepostete Spieler (diese Woche) werden übersprungen

Edge-Modell (wenn Player Props vorhanden):
  model_prob = scoring_rate × elo_factor (Gegner-Stärke-Korrekturfaktor)
  market_prob = 100 / player_odds
  edge_pp = model_prob - market_prob

Ohne Player Props: zeigt Scoring-Rate + Favoriten-Status ohne Wett-Empfehlung.

Output:
  - wm2026-data.json["playerSpotlights"][week_key] = [list of spotlight entries]
  - Telegram Karte(n) via tg_send

Umgebungsvariablen:
  TELEGRAM_TOKEN     — Bot Token
  TELEGRAM_CHAT_ID   — Channel ID
  SPOTLIGHT_DAYS     — Spiele innerhalb von N Tagen (Standard: 7)
  MAX_SPOTLIGHTS     — max. Spotlights pro Lauf (Standard: 3)
  DRY_RUN            — 'true' = nur ausgeben, nicht senden
"""

import json
import os
import math
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE         = Path(__file__).parent
WM_FILE      = BASE / "wm2026-data.json"
PROPS_FILE   = BASE / "wm2026-player-props.json"
LOG_FILE     = BASE / "telegram-log.json"

TELEGRAM_TOKEN = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
CHAT_ID        = (os.environ.get("TELEGRAM_CHAT_ID") or "-1003819239615").strip()
SPOTLIGHT_DAYS = int(os.environ.get("SPOTLIGHT_DAYS", "7"))
MAX_SPOTLIGHTS = int(os.environ.get("MAX_SPOTLIGHTS", "3"))
DRY_RUN        = os.environ.get("DRY_RUN", "").lower() == "true"

# Positions-Bonus für Spotlight-Score
POS_BONUS = {"ST": 1.5, "CF": 1.4, "LW": 1.2, "RW": 1.2,
             "CAM": 1.1, "AM": 1.1, "10": 1.1,
             "MF": 0.9, "CM": 0.9, "DM": 0.7,
             "DF": 0.5, "CB": 0.5, "LB": 0.6, "RB": 0.6}

# Bekannte Stars bekommen Bonus (Engagement)
STAR_BONUS: dict[str, float] = {
    "mbappé": 1.4, "mbappe": 1.4, "ronaldo": 1.3,
    "son": 1.2, "heung-min": 1.2, "kane": 1.25,
    "david": 1.15, "schick": 1.1, "dzeko": 1.1,
    "jiménez": 1.1, "jimenez": 1.1, "salah": 1.25,
    "eriksen": 1.1, "de bruyne": 1.3, "bruyne": 1.3,
    "lewandowski": 1.3, "vinicius": 1.2, "osimhen": 1.15,
    "saka": 1.15, "bellingham": 1.2, "rodri": 1.1,
    "pedri": 1.1, "yamal": 1.2, "lamine": 1.2,
}

CO_HOSTS = {"MEX", "USA", "CAN"}


# ── Send Log ──────────────────────────────────────────────────────────────────
def _log_send(type_: str, preview: str, meta: dict = None):
    try:
        existing = []
        if LOG_FILE.exists():
            with open(LOG_FILE, encoding="utf-8") as f:
                existing = json.load(f)
        entry = {
            "type":    type_,
            "sentAt":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "preview": preview[:160],
            "chatId":  CHAT_ID,
        }
        if meta:
            entry.update(meta)
        existing.append(entry)
        existing = existing[-200:]
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  ⚠️  Log failed: {e}")


# ── Telegram ──────────────────────────────────────────────────────────────────
def tg_send(text: str) -> bool:
    if not TELEGRAM_TOKEN:
        print("⚠️  Kein Token — Vorschau:")
        print(text)
        return True
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    req  = urllib.request.Request(url, data=body,
                                   headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("ok", False)
    except urllib.error.HTTPError as e:
        print(f"❌ TG HTTP {e.code}: {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"❌ TG Fehler: {e}")
        return False


# ── Scoring-Rate-Modell ───────────────────────────────────────────────────────
def scoring_rate(goals: int, minutes: int) -> float:
    """Tore pro 90 Minuten."""
    if not minutes or minutes < 90:
        return 0.0
    return goals / (minutes / 90)


def elo_factor(opp_elo: int) -> float:
    """
    Korrekturfaktor basierend auf Gegner-Elo.
    Gegner mit Elo 1400 → Factor ~1.3 (leichterer Gegner)
    Gegner mit Elo 1900 → Factor ~0.7 (starker Gegner)
    Pivot: 1650 (Mittelfeld WM-Team)
    """
    return max(0.4, min(1.6, 1.0 + (1650 - opp_elo) / 1000))


def model_goal_prob(player: dict, opp_elo: int) -> float:
    """
    Schätzt P(Spieler erzielt mind. 1 Tor) über 90 Minuten.
    Verwendet Poisson: P(X >= 1) = 1 - e^(-λ)
    λ = scoring_rate × elo_factor × WM-Discount (0.80)
    """
    rate = scoring_rate(player.get("goals", 0), player.get("minutes", 0))
    if rate <= 0:
        return 0.0
    lam  = rate * elo_factor(opp_elo) * 0.80   # WM ist tighter als Quali
    prob = (1 - math.exp(-lam)) * 100
    return round(prob, 1)


def spotlight_score(player: dict, opp_elo: int, has_props: bool) -> float:
    """Gesamt-Score für Spotlight-Priorisierung."""
    rate  = scoring_rate(player.get("goals", 0), player.get("minutes", 0))
    pos   = player.get("position", "")
    pb    = POS_BONUS.get(pos, 0.8)
    name  = player.get("name", "").lower()
    sb    = max((v for k, v in STAR_BONUS.items() if k in name), default=1.0)
    ef    = elo_factor(opp_elo)
    # Bonus wenn Props vorhanden (konkrete Wettempfehlung möglich)
    prop_bonus = 1.2 if has_props else 1.0
    return rate * pb * sb * ef * prop_bonus


# ── Spieler aus Player Props matchen ─────────────────────────────────────────
def match_player_to_props(player_name: str, props_players: list[dict]) -> dict | None:
    """Fuzzy-Match: unser Spielername → TheOddsAPI Spielername."""
    name_parts = player_name.lower().replace(".", "").split()

    best      = None
    best_score = 0
    for pp in props_players:
        pp_name  = pp["name"].lower().replace(".", "")
        pp_parts = pp_name.split()

        # Score: Anzahl übereinstimmender Namens-Teile (Nachname gewichtet)
        matches = sum(1 for part in name_parts if any(part in pp_p or pp_p in part
                                                       for pp_p in pp_parts))
        # Nachname-Match besonders wichtig
        if name_parts and (name_parts[-1] in pp_name or any(p in name_parts[-1] for p in pp_parts)):
            matches += 2

        if matches > best_score:
            best_score = matches
            best       = pp

    # Mindest-Score damit kein zufälliger Match passiert
    return best if best_score >= 2 else None


# ── Telegram Card Builder ─────────────────────────────────────────────────────
def build_spotlight_card(entry: dict) -> str:
    player   = entry["player"]
    home     = entry["home"]
    away     = entry["away"]
    home_f   = entry["homeFlag"]
    away_f   = entry["awayFlag"]
    team_f   = entry["teamFlag"]
    team_n   = entry["teamName"]
    date_str = entry["date"]
    time_str = entry["time"]
    opp_name = entry["opponentName"]
    opp_elo  = entry["opponentElo"]
    model_p  = entry["modelProb"]
    rate     = entry["scoringRate"]
    has_bet  = entry.get("hasBet", False)
    odds     = entry.get("betOdds")
    edge     = entry.get("edgePP")
    book     = entry.get("bookmaker", "")

    name    = player.get("name", "?")
    pos     = player.get("position", "")
    goals   = player.get("goals", 0)
    assists = player.get("assists", 0)
    minutes = player.get("minutes", 0)
    apps    = round(minutes / 90) if minutes else 0

    # Positions-Label
    pos_labels = {
        "ST": "Stürmer", "CF": "Stürmer", "LW": "Linksaußen", "RW": "Rechtsaußen",
        "CAM": "Offensives Mittelfeld", "AM": "Offensives Mittelfeld",
        "MF": "Mittelfeld", "CM": "Mittelfeld", "DM": "Defensives Mittelfeld",
    }
    pos_label = pos_labels.get(pos, pos or "Spieler")

    # Scoring-Rate-Label
    rate_label = "stark" if rate >= 0.5 else "solide" if rate >= 0.3 else "moderat"

    lines = [
        f"⚽ <b>PLAYER SPOTLIGHT</b>  ·  WM 2026",
        f"",
        f"{team_f} <b>{name}</b> — {team_n}",
        f"📊 {pos_label} · {goals} Tore · {assists} Assists · ~{apps} Spiele",
        f"",
        f"🗓️ {home_f} {home} vs {away_f} {away}",
        f"📅 {date_str} · {time_str} Uhr",
        f"",
    ]

    # Modell-Analyse
    lines.append(f"🧮 <b>Scoring-Analyse</b>")
    lines.append(f"  Rate: {rate:.2f} Tore/90min ({rate_label})")
    lines.append(f"  Modell-Prob Anytime Scorer: <b>{model_p:.0f}%</b>")

    if opp_elo:
        elo_desc = "schwacher" if opp_elo < 1600 else "mittelstarker" if opp_elo < 1720 else "starker"
        lines.append(f"  Gegner-Elo: {opp_elo} ({elo_desc} Gegner)")

    lines.append("")

    # Wett-Empfehlung
    if has_bet and odds and edge is not None:
        market_p = round(100 / odds, 1)
        edge_str = f"+{edge:.1f}pp" if edge >= 0 else f"{edge:.1f}pp"
        verdict  = "🎯 <b>BET</b>" if edge >= 5 else "⚖️ <b>ABWÄGEN</b>" if edge >= 2 else "🔇 Kein Edge"
        lines += [
            f"💰 <b>Player Bet: Anytime Scorer</b>",
            f"  Quote: @{odds:.2f} [{book}]",
            f"  Markt: {market_p:.0f}% | Modell: {model_p:.0f}% | Edge: {edge_str}",
            f"  {verdict}: Anytime Scorer @{odds:.2f}",
            f"",
        ]
    else:
        lines += [
            f"⏳ Player Props noch nicht verfügbar",
            f"  Modell-Prob: {model_p:.0f}% — Quote beobachten wenn sie erscheint",
            f"",
        ]

    # Kurze narrative Einschätzung
    narrative = _narrative(entry)
    if narrative:
        lines.append(f"<i>{narrative}</i>")
        lines.append("")

    lines.append("🤖 CocoBet Player Spotlight · WM 2026")
    return "\n".join(lines)


def _narrative(entry: dict) -> str:
    """Regelbasierte 1-2 Satz Einschätzung."""
    player  = entry["player"]
    name    = player.get("name", "").split(".")[-1].strip()  # Nachname
    rate    = entry["scoringRate"]
    opp_elo = entry["opponentElo"] or 1600
    model_p = entry["modelProb"]
    team    = entry["teamName"]
    opp     = entry["opponentName"]
    is_cohost = entry.get("isCoHost", False)

    parts = []

    if rate >= 0.6:
        parts.append(f"{name} ist einer der treffsichersten WM-Teilnehmer mit {rate:.1f} Toren pro 90 Minuten")
    elif rate >= 0.35:
        parts.append(f"{name} bringt eine solide Scoring-Rate von {rate:.1f} Toren/90min für {team} mit")
    else:
        parts.append(f"{name} ist der wichtigste Angriffsspieler von {team}")

    if opp_elo < 1600:
        parts.append(f"Gegen den schwächeren Gegner {opp} (Elo {opp_elo}) erhöhen sich seine Chancen auf einen Treffer deutlich")
    elif opp_elo < 1720:
        parts.append(f"Der Gegner {opp} ist solide, aber {name} hat die Qualität um auch gegen kompakte Defensiven zu treffen")
    else:
        parts.append(f"Gegen den starken Gegner {opp} (Elo {opp_elo}) wird es schwieriger, aber bei {model_p:.0f}% Modell-Prob lohnt ein Blick auf die Quote")

    if is_cohost:
        parts[0] += f" und genießt Heimvorteil als Spieler des Co-Gastgebers"

    return ". ".join(parts[:2]) + "."


# ── Spieler-Auswahl ───────────────────────────────────────────────────────────
def select_spotlights(wm: dict, props: dict, now: datetime) -> list[dict]:
    """
    Wählt die besten N Spieler für Spotlight aus.
    """
    cutoff    = (now + timedelta(days=SPOTLIGHT_DAYS)).date()
    week_key  = now.strftime("%Y-W%W")

    # Bereits gepostete Spotlights dieser Woche überspringen
    existing  = wm.get("playerSpotlights", {}).get(week_key, [])
    posted    = {e["playerName"] for e in existing}

    candidates: list[dict] = []

    for gkey, gdata in wm.get("groups", {}).items():
        teams_map = {t["id"]: t for t in gdata.get("teams", [])}

        for fx in gdata.get("fixtures", []):
            try:
                fx_date = datetime.strptime(fx["date"], "%Y-%m-%d").date()
            except Exception:
                continue
            if fx_date > cutoff:
                continue

            home_id = fx["home"]
            away_id = fx["away"]

            for team_id, opp_id in [(home_id, away_id), (away_id, home_id)]:
                team_t  = teams_map.get(team_id, {})
                opp_t   = teams_map.get(opp_id, {})
                player  = wm.get("squads", {}).get(team_id)

                if not player:
                    continue
                if player["name"] in posted:
                    continue

                opp_elo  = opp_t.get("elo", 1600)
                odds_key = f"{home_id}-{away_id}"
                fx_props = props.get(odds_key, {})
                prop_players = fx_props.get("players", [])

                # Player Props matchen
                matched_prop = match_player_to_props(player["name"], prop_players) if prop_players else None

                # Edge berechnen
                model_p  = model_goal_prob(player, opp_elo)
                edge_pp  = None
                bet_odds = None
                book     = None
                has_bet  = False

                if matched_prop:
                    bet_odds  = matched_prop["odds"]
                    book      = matched_prop.get("bookmaker", "")
                    market_p  = 100 / bet_odds
                    edge_pp   = round(model_p - market_p, 1)
                    has_bet   = True

                score = spotlight_score(player, opp_elo, has_bet)

                candidates.append({
                    "score":        score,
                    "player":       player,
                    "playerName":   player["name"],
                    "teamId":       team_id,
                    "teamName":     team_t.get("name", team_id),
                    "teamFlag":     team_t.get("flag", "🏳"),
                    "opponentId":   opp_id,
                    "opponentName": opp_t.get("name", opp_id),
                    "opponentElo":  opp_elo,
                    "home":         teams_map.get(home_id, {}).get("name", home_id),
                    "away":         teams_map.get(away_id, {}).get("name", away_id),
                    "homeFlag":     teams_map.get(home_id, {}).get("flag", "🏳"),
                    "awayFlag":     teams_map.get(away_id, {}).get("flag", "🏳"),
                    "date":         fx["date"],
                    "time":         fx.get("time", ""),
                    "scoringRate":  round(scoring_rate(player.get("goals", 0), player.get("minutes", 0)), 3),
                    "modelProb":    model_p,
                    "hasBet":       has_bet,
                    "betOdds":      bet_odds,
                    "edgePP":       edge_pp,
                    "bookmaker":    book,
                    "isCoHost":     team_id in CO_HOSTS,
                    "weekKey":      week_key,
                })

    # Sortieren: erst nach Edge (wenn vorhanden), dann nach Score
    candidates.sort(key=lambda x: (
        -(x.get("edgePP") or -99),
        -x["score"]
    ))

    # Duplikate (selber Spieler, verschiedene Spiele) entfernen
    seen_players: set[str] = set()
    result = []
    for c in candidates:
        if c["playerName"] not in seen_players:
            seen_players.add(c["playerName"])
            result.append(c)
        if len(result) >= MAX_SPOTLIGHTS:
            break

    return result


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=== generate_wm_player_spotlight.py ===")

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    props: dict = {}
    if PROPS_FILE.exists():
        with open(PROPS_FILE, encoding="utf-8") as f:
            props = json.load(f)
        print(f"  Player Props: {len(props)} Matches mit Daten")
    else:
        print("  ℹ️  Keine Player Props — Scoring-Rate-Modell only")

    now = datetime.now(timezone.utc)
    spotlights = select_spotlights(wm, props, now)

    if not spotlights:
        print(f"\n  ○ Keine Spieler in den nächsten {SPOTLIGHT_DAYS} Tagen / alles bereits gepostet")
        return

    print(f"\n  ⚽ {len(spotlights)} Spotlight(s) ausgewählt:\n")

    # In wm2026-data.json speichern
    week_key = now.strftime("%Y-W%W")
    spots_store = wm.setdefault("playerSpotlights", {})
    spots_store.setdefault(week_key, [])

    sent = 0
    for entry in spotlights:
        name = entry["playerName"]
        print(f"  🌟 {name} ({entry['teamName']})")
        print(f"     Score: {entry['score']:.2f} | Rate: {entry['scoringRate']:.2f}/90 | "
              f"Model: {entry['modelProb']:.0f}%"
              + (f" | Edge: {entry['edgePP']:+.1f}pp @{entry['betOdds']}" if entry["hasBet"] else " | No props"))

        card = build_spotlight_card(entry)
        print()
        print(card)
        print()

        if not DRY_RUN:
            ok = tg_send(card)
            if ok:
                sent += 1
                _log_send("player_spotlight", card.split("\n")[0], {
                    "player": name, "teamId": entry["teamId"],
                    "matchDate": entry["date"],
                    "edge": round(entry.get("edgePP", 0), 1) if entry.get("hasBet") else None,
                })
                # Speichern damit wir nicht doppelt posten
                spots_store[week_key].append({
                    "playerName": name,
                    "teamId":     entry["teamId"],
                    "date":       entry["date"],
                    "postedAt":   now.isoformat(),
                })
        else:
            print("  [DRY_RUN — nicht gesendet]")

    # Speichern
    wm["playerSpotlights"] = spots_store
    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    if not DRY_RUN:
        print(f"\n✅ {sent}/{len(spotlights)} Spotlight(s) gesendet")
    else:
        print(f"\n✅ {len(spotlights)} Spotlight(s) generiert (DRY_RUN)")


if __name__ == "__main__":
    main()
