#!/usr/bin/env python3
"""
telegram_wm_preseason.py — CocoBet WM 2026 Pre-Season Telegram Posts
=====================================================================
Sendet täglich einen Hype-/Analyse-Post vom 31. Mai bis 10. Juni (D-11 bis D-1).
Läuft täglich über fetch-wm-data.yml. Interner Dedup verhindert Doppel-Posts.

Content-Kalender:
  D-11  Countdown & Gruppen-Übersicht
  D-10  Top-5 Favoriten (Elo-Ranking)
  D-9   Geheimfavoriten & Außenseiter
  D-8   Co-Gastgeber im Check (USA/MEX/CAN)
  D-7   Gruppe des Todes — wer kommt weiter?
  D-6   Die gefährlichsten Stürmer
  D-5   Unsere Wett-Strategie erklärt
  D-4   Steam Lag & Polymarket erklärt
  D-3   Erste Picks — Spieltag 1 Vorschau
  D-2   Einstimmung — was erwartet uns?
  D-1   Morgen geht's los! 🚀

Umgebungsvariablen:
  TELEGRAM_TOKEN   — Bot Token
  TELEGRAM_CHAT_ID — Channel ID
  DRY_RUN=true     — nur ausgeben, nicht senden
"""

import json
import os
import urllib.request
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
HAIKU_MODEL       = "claude-haiku-4-5-20251001"


def haiku(prompt: str, max_tokens: int = 250) -> str | None:
    """Kurzer Claude Haiku Call — gibt None zurück wenn kein Key oder Fehler."""
    if not ANTHROPIC_API_KEY:
        return None
    url  = "https://api.anthropic.com/v1/messages"
    body = json.dumps({
        "model":      HAIKU_MODEL,
        "max_tokens": max_tokens,
        "messages":   [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type":      "application/json",
        "x-api-key":         ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())["content"][0]["text"].strip()
    except Exception as e:
        print(f"  ⚠️  Haiku fehlgeschlagen: {e}")
        return None

BASE         = Path(__file__).parent
WM_FILE      = BASE / "wm2026-data.json"
SENT_FILE    = BASE / "wm_preseason_sent.json"
LOG_FILE     = BASE / "telegram-log.json"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or "-1003819239615"
DRY_RUN        = os.environ.get("DRY_RUN", "").lower() == "true"

WM_START = date(2026, 6, 11)   # Erster WM-Spieltag


# ── Telegram Sender ───────────────────────────────────────────────────────────

def tg_send(text: str) -> bool:
    if not TELEGRAM_TOKEN or DRY_RUN:
        print("📋 VORSCHAU (DRY_RUN):\n")
        print(text)
        print("\n" + "─"*50)
        return True
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id":    CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = json.loads(resp.read()).get("ok", False)
            if ok:
                print("✅ Telegram gesendet")
            return ok
    except urllib.error.HTTPError as e:
        print(f"❌ Telegram HTTP {e.code}: {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"❌ Telegram Fehler: {e}")
        return False


# ── Dedup ─────────────────────────────────────────────────────────────────────

def already_sent_today() -> bool:
    today_str = date.today().isoformat()
    if not SENT_FILE.exists():
        return False
    try:
        data = json.loads(SENT_FILE.read_text())
        return data.get("lastSent") == today_str
    except Exception:
        return False


def mark_sent():
    today_str = date.today().isoformat()
    data = {}
    if SENT_FILE.exists():
        try:
            data = json.loads(SENT_FILE.read_text())
        except Exception:
            pass
    data["lastSent"] = today_str
    data.setdefault("history", [])
    if today_str not in data["history"]:
        data["history"].append(today_str)
    SENT_FILE.write_text(json.dumps(data, indent=2))


# ── Data Loader ───────────────────────────────────────────────────────────────

def load_data() -> dict:
    try:
        return json.loads(WM_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ wm2026-data.json nicht lesbar: {e}")
        return {}


def get_teams_sorted(wm: dict) -> list[dict]:
    """Alle 48 Teams nach Elo sortiert."""
    teams = []
    for gname, gdata in wm.get("groups", {}).items():
        for t in gdata.get("teams", []):
            teams.append({
                "id":    t.get("id", ""),
                "name":  t.get("name", "?"),
                "flag":  t.get("flag", "🏳"),
                "elo":   t.get("elo", 1500),
                "group": gname,
            })
    teams.sort(key=lambda x: x["elo"], reverse=True)
    return teams


def get_group_difficulty(wm: dict) -> list[dict]:
    """Gruppen nach durchschnittlicher Elo sortiert."""
    groups = []
    for gname, gdata in wm.get("groups", {}).items():
        gteams = gdata.get("teams", [])
        elos   = [t.get("elo", 1500) for t in gteams]
        avg    = sum(elos) / len(elos) if elos else 0
        groups.append({
            "name":   gname,
            "avg":    avg,
            "teams":  gteams,
        })
    groups.sort(key=lambda x: x["avg"], reverse=True)
    return groups


def get_top_scorers(wm: dict) -> list[dict]:
    """Spieler nach Toren sortiert."""
    squads = wm.get("squads", {})
    players = []
    for tid, p in squads.items():
        if not isinstance(p, dict) or not p.get("goals"):
            continue
        mins  = p.get("minutes", 0)
        goals = p.get("goals", 0)
        per90 = round(goals / (mins / 90), 2) if mins > 0 else 0
        team_info = {}
        for gdata in wm.get("groups", {}).values():
            for t in gdata.get("teams", []):
                if t.get("id") == tid:
                    team_info = t
        players.append({
            "name":     p.get("name", "?"),
            "tid":      tid,
            "flag":     team_info.get("flag", "🏳"),
            "team":     team_info.get("name", tid),
            "pos":      p.get("position", "?"),
            "goals":    goals,
            "assists":  p.get("assists", 0),
            "per90":    per90,
        })
    players.sort(key=lambda x: x["goals"], reverse=True)
    return players


def get_june11_picks(wm: dict) -> list[dict]:
    """Picks für Spiele am 11. Juni (Spieltag 1)."""
    picks = wm.get("picks", {})
    result = []
    for key, pick_list in picks.items():
        for p in (pick_list if isinstance(pick_list, list) else []):
            if p.get("verdict") in ("BET", "ABWÄGEN") and p.get("date", "").startswith("2026-06-11"):
                result.append(p)
    result.sort(key=lambda x: x.get("verdict") == "BET", reverse=True)
    return result[:6]  # Max 6


# ── Content Generatoren ───────────────────────────────────────────────────────

def post_d11(wm: dict, days_left: int) -> str:
    """D-11: Countdown & Gruppen-Übersicht"""
    groups = wm.get("groups", {})
    group_lines = []
    for gname in sorted(groups.keys()):
        gdata = groups[gname]
        tnames = [t.get("flag","🏳") + " " + t.get("name","?") for t in gdata.get("teams",[])]
        group_lines.append(f"<b>Gruppe {gname}:</b> {' · '.join(tnames)}")

    return (
        f"🌍 <b>WM 2026 — Noch {days_left} Tage!</b>\n\n"
        f"Am 11. Juni geht's los — 48 Teams, 12 Gruppen, 104 Spiele. "
        f"Das größte Fußball-Turnier aller Zeiten startet in den USA, Mexiko und Kanada.\n\n"
        f"📋 <b>Die Gruppen im Überblick:</b>\n\n"
        + "\n".join(group_lines) +
        f"\n\n💡 Ab morgen analysieren wir täglich: Favoriten, Geheimtipps, "
        f"Wett-Strategie und unsere Picks.\n\n"
        f"🔔 Abonniere den Channel um nichts zu verpassen!\n\n"
        f"<i>CocoBet · WM 2026</i>"
    )


def post_d10(wm: dict, days_left: int) -> str:
    """D-10: Top-5 Favoriten"""
    teams = get_teams_sorted(wm)[:5]
    lines = []
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, t in enumerate(teams):
        lines.append(
            f"{medals[i]} {t['flag']} <b>{t['name']}</b> — Elo {t['elo']} (Gruppe {t['group']})"
        )

    return (
        f"🏆 <b>WM 2026 — Die Top-5 Favoriten</b>\n"
        f"<i>Noch {days_left} Tage bis zum Anpfiff</i>\n\n"
        + "\n".join(lines) +
        f"\n\n📊 <b>Das Elo-Modell</b> bewertet Teams anhand aller Länderspiel-Ergebnisse "
        f"der letzten Jahre — gewichtet nach Gegner-Stärke und Turnier-Wichtigkeit.\n\n"
        f"🇫🇷 Frankreich startet als Nummer 1 ins Turnier. Mit Mbappé, Griezmann und "
        f"einer der tiefsten Kader-Qualitäten weltweit ist das kein Zufall.\n\n"
        f"🇧🇷 Brasilien und 🇬🇧 England folgen dicht dahinter — beide mit klaren "
        f"Titelchancen und ausgeglichenen Gruppen.\n\n"
        f"💡 Morgen: <b>Die Geheimfavoriten</b> — wer traut sich, die Großen zu schlagen?\n\n"
        f"<i>CocoBet · WM 2026</i>"
    )


def post_d9(wm: dict, days_left: int) -> str:
    """D-9: Geheimfavoriten & Außenseiter — mit Haiku-Analyse"""
    teams = get_teams_sorted(wm)
    dark_horses = [t for t in teams if 1800 <= t["elo"] < 1940][2:6]
    underdogs   = [t for t in teams if t["elo"] < 1600][:3]
    squads      = wm.get("squads", {})

    # Haiku: kurze Begründung pro Dark Horse
    dh_lines = []
    for t in dark_horses:
        squad  = squads.get(t["id"], {})
        player = squad.get("name", "") if isinstance(squad, dict) else ""
        ai_reason = haiku(
            f"WM 2026: Warum ist {t['name']} (Elo {t['elo']}, Gruppe {t['group']}) "
            f"ein Geheimfavorit?{f' Schlüsselspieler: {player}.' if player else ''} "
            f"Schreib 1 prägnanten deutschen Satz (max 20 Wörter), journalistisch, kein Hype."
        )
        reason = ai_reason or "Starke Defensive, unterschätzte Offensive — gefährlicher als die Quoten zeigen."
        dh_lines.append(
            f"{t['flag']} <b>{t['name']}</b> (Elo {t['elo']})\n"
            f"   <i>{reason}</i>"
        )

    ud_lines = [f"{t['flag']} {t['name']} (Elo {t['elo']})" for t in underdogs]

    return (
        f"💎 <b>WM 2026 — Geheimfavoriten & Außenseiter</b>\n"
        f"<i>Noch {days_left} Tage bis zum Anpfiff</i>\n\n"
        f"🔍 <b>Dark Horses — wer überrascht das Turnier?</b>\n\n"
        + "\n\n".join(dh_lines) +
        f"\n\n🎲 <b>Die größten Außenseiter:</b>\n"
        + "\n".join(ud_lines) +
        f"\n\nBei Upset-Spielen entstehen die interessantesten Wett-Edges — unser Modell erkennt sie automatisch.\n\n"
        f"💡 Morgen: <b>Co-Gastgeber USA, Mexiko, Kanada</b>\n\n"
        f"<i>CocoBet · WM 2026</i>"
    )


def post_d8(wm: dict, days_left: int) -> str:
    """D-8: Co-Gastgeber im Check"""
    teams = get_teams_sorted(wm)
    cohost_ids = {"USA", "MEX", "CAN"}
    cohosts = {t["id"]: t for t in teams if t["id"] in cohost_ids}

    usa = cohosts.get("USA", {})
    mex = cohosts.get("MEX", {})
    can = cohosts.get("CAN", {})

    return (
        f"🇺🇸🇲🇽🇨🇦 <b>WM 2026 — Die Co-Gastgeber im Check</b>\n"
        f"<i>Noch {days_left} Tage bis zum Anpfiff</i>\n\n"
        f"Zum ersten Mal in der Geschichte wird die WM von <b>drei Nationen</b> gemeinsam "
        f"ausgetragen. Das verändert die Dynamik — Heimvorteil für alle drei.\n\n"
        f"{usa.get('flag','🇺🇸')} <b>USA</b> — Elo {usa.get('elo','?')} · Gruppe {usa.get('group','?')}\n"
        f"Stärkster Co-Gastgeber. Eigene Fans in riesigen Stadien, "
        f"Pulisic, McKennie und eine hungrige Generation. Klarer Viertelfinale-Kandidat.\n\n"
        f"{mex.get('flag','🇲🇽')} <b>Mexiko</b> — Elo {mex.get('elo','?')} · Gruppe {mex.get('group','?')}\n"
        f"Historisch immer Achtelfinale — diesmal mit Heimvorteil in Dallas, "
        f"Guadalajara und Monterrey. Jiménez als Anführer. Kann das die Runde-der-16-Barriere fallen?\n\n"
        f"{can.get('flag','🇨🇦')} <b>Kanada</b> — Elo {can.get('elo','?')} · Gruppe {can.get('group','?')}\n"
        f"Erste WM seit 1986. Junge Generation um Jonathan David, "
        f"Buchanan und Davies. Die schwächste der drei — aber mit Heimstimmung alles möglich.\n\n"
        f"📊 Unser Modell gewichtet den Co-Host-Bonus bei allen Spielen dieser Teams.\n\n"
        f"💡 Morgen: <b>Gruppe des Todes</b> — welche Gruppe ist die härteste?\n\n"
        f"<i>CocoBet · WM 2026</i>"
    )


def post_d7(wm: dict, days_left: int) -> str:
    """D-7: Gruppe des Todes"""
    groups = get_group_difficulty(wm)
    hardest = groups[0]
    second  = groups[1]

    def group_line(g):
        ts = g["teams"]
        parts = []
        for t in sorted(ts, key=lambda x: x.get("elo", 0), reverse=True):
            parts.append(f"{t.get('flag','🏳')} {t.get('name','?')} ({t.get('elo','?')})")
        return "\n".join(f"  · {p}" for p in parts)

    return (
        f"💀 <b>WM 2026 — Gruppe des Todes</b>\n"
        f"<i>Noch {days_left} Tage bis zum Anpfiff</i>\n\n"
        f"📊 Sortiert nach durchschnittlicher Elo-Stärke:\n\n"
        f"🔴 <b>Gruppe {hardest['name']}</b> — härteste Gruppe (Ø Elo {hardest['avg']:.0f})\n"
        + group_line(hardest) +
        f"\n\nAus dieser Gruppe kommt nur das beste Team sicher weiter — "
        f"jedes Spiel ist ein Endspiel.\n\n"
        f"🟠 <b>Gruppe {second['name']}</b> — zweit-schwierigste (Ø Elo {second['avg']:.0f})\n"
        + group_line(second) +
        f"\n\n💡 Unser Modell berechnet für jedes Spiel die exakten Wahrscheinlichkeiten "
        f"und vergleicht sie mit den Buchmacher-Quoten — so finden wir den <b>Edge</b>.\n\n"
        f"Morgen: <b>Die gefährlichsten Stürmer</b> der WM 2026 ⚽\n\n"
        f"<i>CocoBet · WM 2026</i>"
    )


def post_d6(wm: dict, days_left: int) -> str:
    """D-6: Die gefährlichsten Stürmer"""
    players = get_top_scorers(wm)[:8]
    lines = []
    for i, p in enumerate(players, 1):
        lines.append(
            f"{i}. {p['flag']} <b>{p['name']}</b> ({p['team']})\n"
            f"   {p['goals']} Tore · {p['assists']} Assists · <b>{p['per90']}</b> Tore/90min"
        )

    return (
        f"⚽ <b>WM 2026 — Die Top-Torjäger</b>\n"
        f"<i>Noch {days_left} Tage bis zum Anpfiff</i>\n\n"
        f"Wer schießt das Turnier in Gold? Die besten Angreifer nach Tore/90min:\n\n"
        + "\n\n".join(lines) +
        f"\n\n🎯 <b>Anytime Scorer</b> ist unser bevorzugter Player-Markt: "
        f"wir vergleichen die modellierte Tref­ferwahrscheinlichkeit mit den Buchmacher-Quoten "
        f"und wetten nur wenn ein echter Edge besteht.\n\n"
        f"Die Quoten erscheinen ca. 1 Woche vor dem Spieltag — wir senden dann automatisch Alerts.\n\n"
        f"Morgen: <b>Unsere Wett-Strategie</b> erklärt — wie wir den Edge finden 📊\n\n"
        f"<i>CocoBet · WM 2026</i>"
    )


def post_d5(wm: dict, days_left: int) -> str:
    """D-5: Wett-Strategie erklärt"""
    return (
        f"📊 <b>WM 2026 — Unsere Wett-Strategie erklärt</b>\n"
        f"<i>Noch {days_left} Tage bis zum Anpfiff</i>\n\n"
        f"Wie finden wir profitable Wetten? Hier das System dahinter:\n\n"
        f"<b>1️⃣ Elo-Modell</b>\n"
        f"Wir berechnen für jedes Spiel die echten Wahrscheinlichkeiten — "
        f"basierend auf Elo-Rating, Form, Heimvorteil, xG und Head-to-Head.\n\n"
        f"<b>2️⃣ Edge = Modell vs. Markt</b>\n"
        f"Wenn unser Modell sagt 45% Chance, der Buchmacher aber 38% impliziert "
        f"(Quote 2.63) → Edge von +7pp. Das ist ein statistischer Vorteil.\n\n"
        f"<b>3️⃣ Nur BET bei ≥5pp Edge</b>\n"
        f"·  <b>BET</b> = Edge ≥5pp + starkes Signal → wir platzieren\n"
        f"·  <b>ABWÄGEN</b> = 3-5pp Edge → interessant aber nicht stark genug\n"
        f"·  <b>SKIP</b> = kein Edge → kein Bet\n\n"
        f"<b>4️⃣ Sharp Money Alert</b>\n"
        f"Wenn Pinnacle (der schärfste Buchmacher weltweit) die Quote um ≥5% kürzt, "
        f"folgt eine professionelle Wett-Bewegung. Wir senden sofort einen Alert.\n\n"
        f"<b>5️⃣ Flat Stakes</b>\n"
        f"Jeder Bet: gleicher Einsatz. Kein Martingale, kein Overbet. "
        f"Langfristig gewinnt der Edge.\n\n"
        f"Morgen: <b>Steam Lag & Polymarket</b> — wie wir Preis-Verzögerungen traden 💹\n\n"
        f"<i>CocoBet · WM 2026</i>"
    )


def post_d4(wm: dict, days_left: int) -> str:
    """D-4: Steam Lag & Polymarket erklärt"""
    return (
        f"💹 <b>WM 2026 — Steam Lag & Polymarket erklärt</b>\n"
        f"<i>Noch {days_left} Tage bis zum Anpfiff</i>\n\n"
        f"Neben klassischen Bookmaker-Wetten nutzen wir auch <b>Polymarket</b> — "
        f"einen dezentralen Prognose-Markt auf der Blockchain.\n\n"
        f"<b>Was ist Polymarket?</b>\n"
        f"Nutzer kaufen Ja/Nein-Anteile auf Ereignisse. Der Preis spiegelt die "
        f"kollektive Wahrscheinlichkeit. Polymarket gilt als einer der "
        f"effizientesten Märkte weltweit.\n\n"
        f"<b>Was ist Steam Lag?</b>\n"
        f"Wenn Pinnacle (der schärfste Buchmacher) die Quote ändert, reagiert "
        f"Polymarket oft mit Verzögerung — manchmal 10-30 Minuten. In diesem "
        f"Zeitfenster ist der Polymarket-Preis günstig.\n\n"
        f"<b>Unser Steam Lag Trade:</b>\n"
        f"1. Pinnacle kürzt Quote → Sharp Money Bewegung erkannt\n"
        f"2. Polymarket-Preis noch nicht angepasst → Edge von ≥3pp\n"
        f"3. Wir kaufen den unterbewerteten Anteil auf Polymarket\n"
        f"4. Wenn Polymarket konvergiert → Verkauf mit Profit\n"
        f"5. Vor Spielbeginn schließen wir alle Positionen\n\n"
        f"<b>Das Ziel:</b> Preiskonvergenz als Profit, unabhängig vom Spielausgang.\n\n"
        f"Morgen: <b>Erste WM-Picks</b> — Spieltag 1 Vorschau 🎯\n\n"
        f"<i>CocoBet · WM 2026</i>"
    )


def post_d3(wm: dict, days_left: int) -> str:
    """D-3: Erste Picks Vorschau Spieltag 1 — mit Haiku-Kommentar"""
    picks = get_june11_picks(wm)

    if not picks:
        ai_text = haiku(
            "WM 2026 startet in 3 Tagen. Schreib 2 packende deutsche Sätze über die Vorfreude "
            "auf das Turnier und was Fußballfans erwartet. Journalistisch, keine Emojis, max 40 Wörter."
        ) or "In drei Tagen beginnt das größte Fußball-Turnier aller Zeiten. 48 Nationen, ein Ziel."
        return (
            f"🎯 <b>WM 2026 — Spieltag 1 in {days_left} Tagen</b>\n\n"
            f"{ai_text}\n\n"
            f"Unsere vollständige Pick-Analyse erscheint am Spieltag selbst "
            f"— dann mit aktuellen Quoten und Modell-Daten.\n\n"
            f"🔔 Morgen: letzte Einstimmung.\n\n"
            f"<i>CocoBet · WM 2026</i>"
        )

    lines = []
    for p in picks:
        verdict  = p.get("verdict", "?")
        icon     = "⚡" if verdict == "BET" else "📈"
        market   = p.get("market", p.get("label", "?"))
        edge     = p.get("edgePP")
        odds     = p.get("odds")
        edge_str = f" · +{edge:.1f}pp Edge" if edge else ""
        odds_str = f" @ {odds:.2f}" if odds else ""
        home     = p.get("home", "?")
        away     = p.get("away", "?")
        lines.append(f"{icon} <b>{verdict}</b> — {home} vs {away}\n   {market}{odds_str}{edge_str}")

    # Haiku fasst die Picks in einem Satz zusammen
    picks_summary = "; ".join([f"{p.get('home')} vs {p.get('away')} ({p.get('market')})" for p in picks[:3]])
    ai_comment = haiku(
        f"WM 2026 Spieltag 1. Unsere Picks: {picks_summary}. "
        f"Schreib 1-2 deutsche Sätze die erklären warum das Modell Edges in diesen Spielen sieht. "
        f"Sachlich, tipster-Stil, max 35 Wörter."
    ) or "Das Modell hat mehrere Spiele mit positivem Edge identifiziert — die Eröffnungsspiele bieten oft Overreactions der Buchmacher."

    return (
        f"🎯 <b>WM 2026 — Spieltag 1 Vorschau</b>\n"
        f"<i>Noch {days_left} Tage bis zum Anpfiff</i>\n\n"
        f"{ai_comment}\n\n"
        f"<b>Erste Picks mit positivem Edge:</b>\n\n"
        + "\n\n".join(lines) +
        f"\n\n⚠️ <i>Vorläufige Picks — finale Analyse am Spieltag mit aktuellen Quoten.</i>\n\n"
        f"Morgen: <b>Finale Einstimmung</b>\n\n"
        f"<i>CocoBet · WM 2026</i>"
    )


def post_d2(wm: dict, days_left: int) -> str:
    """D-2: Einstimmung — was erwartet uns?"""
    teams = get_teams_sorted(wm)
    top3  = teams[:3]
    top3_str = " · ".join(f"{t['flag']} {t['name']}" for t in top3)

    return (
        f"👀 <b>WM 2026 — Was erwartet uns?</b>\n"
        f"<i>Noch {days_left} Tage bis zum Anpfiff</i>\n\n"
        f"<b>Übermorgen startet das größte Fußball-Turnier aller Zeiten.</b> "
        f"48 Nationen, 3 Länder, 16 Spielorte — von den eisigen Abenden in "
        f"Vancouver bis zur Hitze in Dallas und Mexico City.\n\n"
        f"🏆 <b>Unsere Favoriten:</b> {top3_str}\n\n"
        f"📊 <b>Was wir ab morgen senden:</b>\n"
        f"· ⚡ <b>Morning Card</b> täglich um 09:00 — alle Picks des Tages\n"
        f"· 📡 <b>Sharp Move Alerts</b> — wenn professionelles Geld fließt\n"
        f"· 💹 <b>Steam Lag Signals</b> — Polymarket-Edges in Echtzeit\n"
        f"· 🌟 <b>Player Spotlight</b> — gefährliche Torjäger vor ihren Spielen\n"
        f"· ✅ <b>Pick Recap</b> — Ergebnisse und P&amp;L nach jedem Spieltag\n\n"
        f"🔔 Teile diesen Channel mit Freunden die mitwetten wollen!\n\n"
        f"Morgen: <b>Die große WM-Eröffnungsparty</b> 🚀\n\n"
        f"<i>CocoBet · WM 2026</i>"
    )


def post_d1(wm: dict, days_left: int) -> str:
    """D-1: Morgen geht's los! — mit Haiku-Eröffnungstext"""
    teams = get_teams_sorted(wm)
    champ = teams[0] if teams else {}
    top3  = teams[:3]
    top3_str = ", ".join(f"{t['flag']} {t['name']}" for t in top3)

    # Haiku schreibt den Eröffnungstext
    ai_opener = haiku(
        f"WM 2026 startet morgen. Top-Favoriten laut Elo-Modell: {top3_str}. "
        f"Schreib 2-3 packende deutsche Sätze die die Vorfreude und Spannung einfangen. "
        f"Journalistisch, mitreißend, keine Emojis, max 55 Wörter.",
        max_tokens=150,
    ) or (
        "104 Spiele. 48 Nationen. Drei Gastgeberländer. Und ein einziger Weltmeister am Ende. "
        "Das größte Fußball-Turnier der Geschichte beginnt morgen — "
        "und das Modell hat alle Spiele bereits analysiert."
    )

    return (
        f"🚀 <b>MORGEN GEHT'S LOS — WM 2026!</b>\n\n"
        f"{ai_opener}\n\n"
        f"🏆 Favorit Nr. 1: {champ.get('flag','')} <b>{champ.get('name','?')}</b> "
        f"(Elo {champ.get('elo','?')})\n\n"
        f"<b>Ab morgen früh in diesem Channel:</b>\n"
        f"⚡ Morning Card mit allen Picks\n"
        f"📡 Sharp Move Alerts wenn Profis wetten\n"
        f"💹 Polymarket Steam Lag Signals\n"
        f"🌟 Player Spotlight Di/Do/Sa\n"
        f"✅ Recap nach jedem Spieltag\n\n"
        f"<b>LET'S GO! ⚽🌍</b>\n\n"
        f"<i>CocoBet · WM 2026</i>"
    )


# ── Content Router ────────────────────────────────────────────────────────────

CONTENT_MAP = {
    11: post_d11,
    10: post_d10,
    9:  post_d9,
    8:  post_d8,
    7:  post_d7,
    6:  post_d6,
    5:  post_d5,
    4:  post_d4,
    3:  post_d3,
    2:  post_d2,
    1:  post_d1,
}


def main():
    today     = date.today()
    days_left = (WM_START - today).days

    print(f"=== telegram_wm_preseason.py ===")
    print(f"  Heute: {today.isoformat()} | WM-Start: {WM_START.isoformat()} | D-{days_left}")

    # Nur im Pre-Season-Fenster aktiv (D-11 bis D-1)
    if days_left < 1 or days_left > 11:
        print(f"  ℹ️  Außerhalb Pre-Season-Fenster (D-{days_left}) — nichts zu tun.")
        return

    # Dedup: nur einmal pro Tag
    if not DRY_RUN and already_sent_today():
        print(f"  ℹ️  Bereits heute gesendet — Abbruch.")
        return

    # Content generieren
    content_fn = CONTENT_MAP.get(days_left)
    if not content_fn:
        print(f"  ⚠️  Kein Content für D-{days_left} definiert.")
        return

    wm   = load_data()
    text = content_fn(wm, days_left)

    print(f"\n  📝 Content-Typ: D-{days_left}")
    print(f"  📏 Länge: {len(text)} Zeichen\n")

    ok = tg_send(text)
    if ok and not DRY_RUN:
        mark_sent()
        # Ins telegram-log.json schreiben damit der Verlauf-Tab es anzeigt
        try:
            existing = json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else []
            existing.append({
                "type":    "preseason",
                "sentAt":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "preview": text.split("\n")[0].replace("<b>","").replace("</b>","")[:160],
                "chatId":  CHAT_ID,
                "day":     f"D-{days_left}",
            })
            LOG_FILE.write_text(json.dumps(existing[-200:], ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"  ⚠️  Log fehlgeschlagen: {e}")
        print(f"  ✅ Gesendet und als gesent markiert.")


if __name__ == "__main__":
    main()
