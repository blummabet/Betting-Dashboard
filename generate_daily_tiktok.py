#!/usr/bin/env python3
"""
generate_daily_tiktok.py — Tägliche TikTok-Cards für CocoBet
================================================================

Erzeugt jeden Morgen:
  · 2 Cards für die Story-Serie (Hook + Info) — aus tiktok_story_plan.py
  · 2 Cards für den Daily Killer-Stat (Hook + Info) — auto aus wm2026-data.json

Rendert jede HTML zu PNG (Playwright/Chromium) und schickt alle 4 PNGs
in den Cocobet-Trades-Telegram-Channel.

Env-Variablen:
  TELEGRAM_TOKEN              — Bot-Token
  TELEGRAM_TRADES_CHAT_ID     — Cocobet-Trading-Channel-ID
  DAILY_TIKTOK_DATE           — Override-Datum (optional, ISO)
  SKIP_RENDER                 — wenn "true": kein PNG-Render (nur HTML)
  SKIP_TELEGRAM               — wenn "true": kein Send (nur lokal speichern)

Run: python3 generate_daily_tiktok.py
Cron: .github/workflows/daily-tiktok.yml — 06:00 UTC (08:00 Wien)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from tiktok_card_templates import hook_card, info_card, bizarre_info_card, player_pick_card, daily_picks_card, match_preview_card, match_review_card, streak_card
from tiktok_story_plan import get_story_for_date
from bizarre_quote_picker import get_daily_bizarre_card
from player_pick_picker import get_daily_player_pick, save_dedup as save_player_dedup, _load_dedup as _load_player_dedup

def _pick_hook_config(hero: dict) -> dict:
    """Baut den Mystery-Hook (große Zahl + Curiosity-Gap) für die Pick-Card —
    datengetrieben nach Markt-Typ, OHNE den Markt zu verraten (Auflösung erst in
    der Pick-Card). Stil = hook_card() (Lucas' Yamal-Look). Hinzugefügt 13.06.2026:
    die Pick-Card war die einzige Card-Art ohne Hook (fact/story/bizarre hatten alle)."""
    m    = (hero.get("market") or "").lower()
    edge = hero.get("edge_pp") or 0
    lam  = hero.get("lamTotal")
    nh   = hero.get("name_h", "Heim")
    na   = hero.get("name_a", "Auswärts")
    time = (hero.get("time") or "").strip()
    is_totals = ("über" in m or "uber" in m or "unter" in m)
    if is_totals and isinstance(lam, (int, float)) and lam > 0:
        big = f"{lam:.2f}".rstrip("0").rstrip(".")
        sub = "erwartete Tore · unser Modell"
        if "unter" in m:
            h1 = 'Unser Modell sieht ein <span class="acc">enges Spiel</span>.'
            h2 = 'Der Markt preist <span class="yellow">zu viele Tore</span> ein.'
        else:
            h1 = 'Unser Modell sieht <span class="acc">Tore fallen</span>.'
            h2 = 'Der Markt hat das <span class="yellow">noch nicht kapiert</span>.'
    else:
        big = f"+{int(round(edge))}"
        sub = "Punkte Vorsprung · gegen die Markterwartung"
        h1 = 'Ein Team wird <span class="acc">unterschätzt</span>.'
        h2 = 'Unser Modell <span class="yellow">sieht die Chance</span>.'
    return dict(
        theme="daily_picks",
        big_number=big,
        sub_title=sub,
        hook_line_1=h1,
        hook_line_2=h2,
        mystery_question="Ein Spiel sticht heraus. Welches?",
        highlight_fact=f"{nh} – {na} · heute {time}".strip(" ·"),
        cta="ANALYSE IM VIDEO →",
        series_tag="WM 2026 · DAILY ANALYSE",
    )


BASE       = Path(__file__).parent
# 01.07.2026 (Lucas: „Content für MLS/Liga"): dataset-aware. WM_FILE = aktives Daten-File; OUTPUT/DEDUP
# per Dataset-Prefix (WM = kein Prefix → unverändert, mls/liga eigene Dateien → keine Kreuz-Kontamination).
import cocobet_dataset as D  # noqa: E402
WM_FILE    = D.data_file()
OUTPUT_DIR = BASE / f"{D.prefix()}daily-tiktok"
DEDUP_FILE = BASE / f"{D.prefix()}tiktok_sent.json"   # Tracking was schon gepostet wurde
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Refactor 2026-06-06: Konstanten aus cocobet_config.json (Profile-aware) ──
try:
    from cocobet_config import CONFIG as _CFG
except Exception:
    _CFG = {}

def _cfg(section: str, key: str, default):
    if isinstance(_CFG, dict):
        return _CFG.get(section, {}).get(key, default)
    return default

# Dedup-Fenster: ein Team das in den letzten N Tagen Killer-Stat war,
# wird nicht erneut gewählt (auch nicht von einer anderen Strategie).
DEDUP_WINDOW_DAYS = _cfg("tiktok", "dedup_window_days", 7)

# Hand-Override: Teams die du manuell auf TikTok schon abgehandelt hast
# und die NIE als Daily-Killer-Stat triggern sollen.
# Wird beim Setup einmal befüllt, dann automatisch via DEDUP_FILE.
MANUAL_POSTED_TEAMS = {"MAR", "ESP", "CRO", "BEL", "BRA", "ARG", "POR"}
# Marokko, Spanien (Yamal), Kroatien (Modric), Belgien (manuell 03.06.),
# Brasilien (Endrick 03.06.), Argentinien (manuell 04.06.), Portugal (Ronaldo)


def _pick_story_line(hero: dict) -> str:
    """Markt-korrekte Card-Story (FIX 12.06.2026). Vorher: hartes "Edge auf den
    Underdog" bei Edge≥10 — falsch für Tor-Märkte (Über/Unter) und Favoriten-Picks.
    Beschreibt jetzt den tatsächlichen Markt; "Underdog" NUR bei Auswärts-Pick."""
    m = (hero.get("market") or "").lower()
    edge = hero.get("edge_pp") or 0
    s = "Starker" if edge >= 10 else "Solider" if edge >= 5 else "Knapper"
    h = hero.get("name_h", "Heim")
    a = hero.get("name_a", "Auswärts")
    if "über" in m or "ueber" in m or "over" in m:
        return f"{s} Tor-Edge: Modell erwartet mehr Tore als der Markt."
    if "unter" in m or "under" in m:
        return f"{s} Tor-Edge: Modell erwartet weniger Tore als der Markt."
    if "btts" in m or "beide" in m:
        return f"{s} Edge bei Beide-treffen — Modell über dem Markt."
    if "heimsieg" in m or m == "1":
        return f"{s} Edge auf {h} im Heimspiel."
    if "auswärtssieg" in m or "auswaertssieg" in m or m == "2":
        return f"{s} Edge auf Außenseiter {a}."
    if "dnb" in m or "no bet" in m:
        return f"{s} Absicherungs-Edge (Draw-No-Bet)."
    if "doppelte" in m or "double" in m or m.startswith("dc"):
        return f"{s} Doppelte-Chance-Edge."
    return f"{s} Edge — Modell über dem Markt."


def _story_market_consistent(story: str, market: str) -> bool:
    """Guard: 'Underdog'/'Außenseiter' darf NUR bei einem echten Auswärts-Pick
    stehen — nie bei Tor-Märkten (Über/Unter), Heimsieg, BTTS etc. Schützt die
    Card-Story vor inhaltlichen Widersprüchen (FIX 12.06.2026)."""
    st = (story or "").lower()
    mk = (market or "").lower()
    is_away = ("auswärtssieg" in mk or "auswaertssieg" in mk or mk == "2"
               or ("dnb" in mk and ("auswärts" in mk or "auswaerts" in mk)))
    if ("underdog" in st or "außenseiter" in st or "aussenseiter" in st) and not is_away:
        return False
    return True


def load_dedup() -> dict:
    if DEDUP_FILE.exists():
        try:
            return json.loads(DEDUP_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"history": []}


def save_dedup(state: dict) -> None:
    DEDUP_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def recently_sent_team_ids(state: dict, today_iso: str) -> set[str]:
    """Liefert Team-IDs die in den letzten DEDUP_WINDOW_DAYS gepostet wurden."""
    from datetime import timedelta
    cutoff = date.fromisoformat(today_iso) - timedelta(days=DEDUP_WINDOW_DAYS)
    return {
        h["teamId"] for h in state.get("history", [])
        if h.get("teamId") and date.fromisoformat(h.get("date", "1900-01-01")) >= cutoff
    }

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "").strip()
TRADES_CHAT_ID   = os.environ.get("TELEGRAM_TRADES_CHAT_ID", "").strip()
SKIP_RENDER      = os.environ.get("SKIP_RENDER", "").lower() == "true"
SKIP_TELEGRAM    = os.environ.get("SKIP_TELEGRAM", "").lower() == "true"
# 14.06.2026 (Lucas): Umstellung auf Match-Preview-Cards. Daily-Picks-Sammelkarte
# bleibt im Code, wird aber NICHT mehr gesendet (Flag default false). Previews on.
SEND_DAILY_PICKS = os.environ.get("SEND_DAILY_PICKS", "").lower() == "true"
SEND_PREVIEWS    = os.environ.get("SEND_PREVIEWS", "true").lower() == "true"
SEND_REVIEWS     = os.environ.get("SEND_REVIEWS", "true").lower() == "true"   # Vortags-Nachbericht
SEND_STREAKS     = os.environ.get("SEND_STREAKS", "true").lower() == "true"   # Serien-Spotlight (gegated)
# 30.06.2026 (Lucas: „Killer-Stat brauchen wir nicht, ist komisch"): Default AUS. Reviews/Previews +
# Serien sind der Content; Killer-Stat nur noch opt-in via SEND_KILLER_STAT=true.
SEND_KILLER_STAT = os.environ.get("SEND_KILLER_STAT", "").lower() == "true"
# 16.06.2026 (Lucas): Bizarre-Quote-Card PAUSIERT — fad geworden + zeigt Quote/Chance
# (Quoten-Leak). Default AUS. Wieder an via SEND_BIZARRE=true, falls reaktiviert.
SEND_BIZARRE     = os.environ.get("SEND_BIZARRE", "").lower() == "true"


# ═══════════════════════════════════════════════════════════════════════════
#  DAILY KILLER-STAT — findet automatisch den krassesten Datenpunkt
# ═══════════════════════════════════════════════════════════════════════════

def pick_daily_killer_stat(wm: dict, today_iso: str, exclude_team_ids: set[str] = None) -> dict | None:
    """
    Sucht durch wm2026-data.json den 'besten' Standalone-Killer-Fakt für heute.
    Strategie: zyklisch zwischen Stat-Typen rotieren (täglich anderer Style),
    pro Typ den extremsten Datenpunkt wählen.

    exclude_team_ids: Teams die NICHT als Killer-Stat verwendet werden sollen
    (z.B. schon manuell gepostet oder in den letzten 7 Tagen schon Daily).
    """
    exclude = exclude_team_ids or set()
    day_idx = (date.fromisoformat(today_iso) - date(2026, 6, 2)).days
    stat_strategies = [
        _strat_best_attack,        # Tag 0 — stärkster Angriff in Quali
        _strat_best_defense,       # Tag 1 — beste Defense
        _strat_top_form,           # Tag 2 — heißeste Form
        _strat_highest_h2h_ou,     # Tag 3 — H2H mit krassester Ü2.5-Rate
        _strat_biggest_elo_gap,    # Tag 4 — größter Elo-Unterschied im Spielplan
        _strat_top_xg_player,      # Tag 5 — Top-Scorer der Quali
        _strat_zero_loss,          # Tag 6 — unbesiegtes Team
    ]
    # Erst Primary-Strategie, dann andere als Fallback wenn Primary auf
    # ausgeschlossenes Team trifft.
    primary_idx = day_idx % len(stat_strategies)
    order = [primary_idx] + [(primary_idx + i) % len(stat_strategies) for i in range(1, len(stat_strategies))]
    for idx in order:
        result = stat_strategies[idx](wm, exclude)
        if result:
            return result
    return None


def _strat_best_attack(wm: dict, exclude: set = None) -> dict | None:
    exclude = exclude or set()
    """Team mit höchstem avgScored in Form."""
    best = None
    for tid, f in (wm.get("form") or {}).items():
        if not isinstance(f, dict): continue
        sc = f.get("avgScored") or 0
        if best is None or sc > best[1]:
            best = (tid, sc, f)
    if not best or best[1] < 2.0:
        return None
    tid, sc, f = best
    if tid in exclude: return None
    team = _find_team(wm, tid)
    return {
        "teamId": tid,
        "theme": "killer_stat",
        "hook": {
            "big_number": f"{sc:.1f}",
            "sub_title":  "Tore pro Spiel",
            "hook_line_1": f'<span class="acc">{team["name"]}</span> trifft',
            "hook_line_2": f'in fast jedem Spiel.',
            "mystery_question": "Wer stoppt sie?",
            "highlight_fact": f"{f.get('games',0)} Spiele · {round(sc*f.get('games',0))} Tore · Quali 2024/25",
        },
        "info": {
            "flag": team.get("flag","🏳"),
            "name": team["name"],
            "role_line": "WM-Quali Tor-Rakete",
            "stat1_val": f"{sc:.1f}", "stat1_lbl": "Tore Ø",
            "stat2_val": str(f.get('games',0)), "stat2_lbl": "Spiele",
            "stat3_val": f"{round((f.get('over25Rate') or 0)*100)}%", "stat3_lbl": "Ü2.5-Rate",
            "closing_line": f'<strong>{team["name"]}</strong> liegt in der Tor-Statistik vor Brasilien & England. Bookies preisen das nicht ein — Ü2.5 Quoten zu hoch.',
            "quote_line": f'Form-Rakete <span class="acc">{team["name"]}</span>. Markt schläft. 🚀',
            "data_source": "Daten: WM-Quali 2024/25",
        },
    }


def _strat_best_defense(wm: dict, exclude: set = None) -> dict | None:
    exclude = exclude or set()
    best = None
    for tid, f in (wm.get("form") or {}).items():
        if not isinstance(f, dict): continue
        if (f.get("games") or 0) < 6: continue
        c = f.get("avgConceded")
        if c is None: continue
        if best is None or c < best[1]:
            best = (tid, c, f)
    if not best or best[1] > 0.5:
        return None
    tid, c, f = best
    if tid in exclude: return None
    team = _find_team(wm, tid)
    btts_rate = f.get("bttsRate") or 0
    clean_sheets = round((1 - btts_rate) * f.get("games", 1))
    return {
        "teamId": tid,
        "theme": "killer_stat",
        "hook": {
            "big_number": f"{c:.1f}",
            "sub_title":  "Gegentore Ø",
            "hook_line_1": f'<span class="acc">{team["name"]}</span> hat',
            "hook_line_2": 'die beste Defense.',
            "mystery_question": "Wer kommt da durch?",
            "highlight_fact": f"{clean_sheets} Zu-Null in {f.get('games')} Spielen",
        },
        "info": {
            "flag": team.get("flag","🏳"),
            "name": team["name"],
            "role_line": "Defensiv-Festung der Quali",
            "stat1_val": f"{c:.1f}", "stat1_lbl": "Gegen Ø",
            "stat2_val": f"{clean_sheets}/{f.get('games')}", "stat2_lbl": "Zu Null",
            "stat3_val": f"{round((1-btts_rate)*100)}%", "stat3_lbl": "Kein BTTS",
            "closing_line": f'<strong>{team["name"]}</strong> kassiert weniger als jede europäische Top-Defense in der Quali. Unter 2.5 Quoten gegen sie sind zu hoch.',
            "quote_line": f'<span class="acc">{team["name"]}</span> = Bookmaker-Albtraum. 🛡',
            "data_source": "Daten: WM-Quali 2024/25",
        },
    }


def _strat_top_form(wm: dict, exclude: set = None) -> dict | None:
    exclude = exclude or set()
    """Team mit längster Win-Streak."""
    best = None
    for tid, f in (wm.get("form") or {}).items():
        if not isinstance(f, dict): continue
        l = f.get("last10") or []
        s = 0
        for r in reversed(l):
            if r == "W": s += 1
            else: break
        if best is None or s > best[1]:
            best = (tid, s, f)
    if not best or best[1] < 4:
        return None
    tid, streak, f = best
    if tid in exclude: return None
    team = _find_team(wm, tid)
    return {
        "teamId": tid,
        "theme": "hidden_gem",
        "hook": {
            "big_number": f"{streak}W",
            "sub_title":  "Siege in Folge",
            "hook_line_1": f'<span class="acc">{team["name"]}</span> auf',
            "hook_line_2": 'der heißesten Form-Welle.',
            "mystery_question": "Wer bricht den Lauf?",
            "highlight_fact": f"Letzten {streak} Spiele gewonnen · keine Defizite",
        },
        "info": {
            "flag": team.get("flag","🏳"),
            "name": team["name"],
            "role_line": "Form-Welle der Quali",
            "stat1_val": f"{streak}W", "stat1_lbl": "in Folge",
            "stat2_val": f"{f.get('avgScored', 0):.1f}", "stat2_lbl": "Tore Ø",
            "stat3_val": f"{f.get('avgConceded', 0):.1f}", "stat3_lbl": "Gegen Ø",
            "closing_line": f'<strong>{team["name"]}</strong> reist als heißeste Mannschaft der Welt zur WM. Quoten haben den Run noch nicht eingepreist.',
            "quote_line": f'Bookies hinken. <span class="acc">{team["name"]}</span> rennt. 🔥',
            "data_source": "Daten: last 10 Spiele",
        },
    }


def _strat_highest_h2h_ou(wm: dict, exclude: set = None) -> dict | None:
    exclude = exclude or set()
    """H2H-Pairing mit höchster Ü2.5-Rate."""
    best = None
    for k, h2h in (wm.get("h2h") or {}).items():
        if not isinstance(h2h, dict): continue
        if (h2h.get("games") or 0) < 4: continue
        rate = h2h.get("over25Rate") or 0
        if best is None or rate > best[1]:
            best = (k, rate, h2h)
    if not best or best[1] < 0.75:
        return None
    k, rate, h2h = best
    home_id, away_id = k.split("-")[:2]
    if home_id in exclude or away_id in exclude: return None
    home = _find_team(wm, home_id)
    away = _find_team(wm, away_id)
    return {
        "teamIds": [home_id, away_id],
        "theme": "killer_stat",
        "hook": {
            "big_number": f"{round(rate*100)}%",
            "sub_title":  f"Ü2.5 H2H · {home['name']} vs {away['name']}",
            "hook_line_1": f'<span class="acc">{round(rate*100)}%</span> Tor-Festival',
            "hook_line_2": f'in {h2h.get("games")} Direktduellen.',
            "mystery_question": "Ist die Quote nicht viel zu hoch?",
            "highlight_fact": f"Letzte {h2h.get('games')} H2H: Ø {h2h.get('avgGoals',0):.1f} Tore",
        },
        "info": {
            "flag": f"{home.get('flag','🏳')} {away.get('flag','🏳')}",
            "name": f"{home['name']} vs {away['name']}",
            "role_line": "H2H Tor-Bilanz historisch",
            "stat1_val": f"{round(rate*100)}%", "stat1_lbl": "Ü2.5 H2H",
            "stat2_val": f"{h2h.get('avgGoals',0):.1f}", "stat2_lbl": "Ø Tore",
            "stat3_val": str(h2h.get('games',0)), "stat3_lbl": "Duelle",
            "closing_line": f'In den letzten <strong>{h2h.get("games")} Direktduellen</strong> fielen Ø {h2h.get("avgGoals",0):.1f} Tore. WM-Spiel im Gruppen-Programm.',
            "quote_line": 'H2H-Stats lügen <span class="acc">selten</span>. ⚽',
            "data_source": "Daten: H2H letzten 10 Jahre",
        },
    }


def _strat_biggest_elo_gap(wm: dict, exclude: set = None) -> dict | None:
    exclude = exclude or set()
    """Spielpaarung mit größtem Elo-Gap (krasse Klassen-Unterschiede)."""
    pairs = []
    for g in (wm.get("groups") or {}).values():
        teams = {t["id"]: t for t in g.get("teams", [])}
        for fx in g.get("fixtures", []):
            h = teams.get(fx.get("home")); a = teams.get(fx.get("away"))
            if not h or not a: continue
            eh, ea = h.get("elo"), a.get("elo")
            if eh and ea:
                pairs.append((abs(eh-ea), h, a, fx))
    if not pairs: return None
    # FIX 11.06.2026: nur nach Elo-Gap sortieren. Vorher pairs.sort(reverse=True) →
    # bei gleichem Gap verglich Python die Team-Dicts dahinter → TypeError
    # "'<' not supported between instances of 'dict' and 'dict'" → Killer-Stat
    # crashte → KEINE Daily-Cards. Key fixt das.
    pairs.sort(key=lambda p: p[0], reverse=True)
    pairs = [p for p in pairs if p[1]["id"] not in exclude and p[2]["id"] not in exclude]
    if not pairs: return None
    gap, h, a, fx = pairs[0]
    fav = h if h["elo"] > a["elo"] else a
    und = a if fav is h else h
    return {
        "teamIds": [h["id"], a["id"]],
        "theme": "killer_stat",
        "hook": {
            "big_number": str(gap),
            "sub_title":  "Elo-Punkte Differenz",
            "hook_line_1": f'<span class="acc">{fav["name"]}</span> trifft auf',
            "hook_line_2": f'das schwächste Team {und["name"]}.',
            "mystery_question": "Wieso ist die Quote so?",
            "highlight_fact": f"{fav['name']} Elo {fav['elo']} vs {und['name']} Elo {und['elo']}",
        },
        "info": {
            "flag": f"{fav.get('flag','🏳')} vs {und.get('flag','🏳')}",
            "name": f"{fav['name']} vs {und['name']}",
            "role_line": f"WM 2026 · {fx.get('date','?')}",
            "stat1_val": str(fav["elo"]), "stat1_lbl": f"Elo {fav.get('flag','')}",
            "stat2_val": str(und["elo"]), "stat2_lbl": f"Elo {und.get('flag','')}",
            "stat3_val": f"+{gap}", "stat3_lbl": "Elo-Diff",
            "closing_line": f'<strong>Klassen-Unterschied der absoluten Spitze.</strong> Über 3.5 Tore @{1.95 if gap < 400 else 2.30} ist hier die echte Wahrheit.',
            "quote_line": f'David gegen <span class="acc">Goliath</span>. 🎯',
            "data_source": "Daten: Elo Mai 2026",
        },
    }


def _strat_top_xg_player(wm: dict, exclude: set = None) -> dict | None:
    exclude = exclude or set()
    """Top-Scorer Quali aus squads."""
    best = None
    for tid, p in (wm.get("squads") or {}).items():
        if not isinstance(p, dict) or not p.get("name"): continue
        goals = p.get("goals") or 0
        mins  = p.get("minutes") or 0
        if mins < 270: continue
        per90 = goals/(mins/90) if mins else 0
        if best is None or per90 > best[1]:
            best = (tid, per90, p)
    if not best or best[1] < 0.8:
        return None
    tid, per90, p = best
    if tid in exclude: return None
    team = _find_team(wm, tid)
    return {
        "teamId": tid,
        "theme": "naechste_aera",
        "hook": {
            "big_number": f"{per90:.2f}",
            "sub_title": "Tore pro 90 Min",
            "hook_line_1": f'<span class="acc">{p["name"]}</span> trifft',
            "hook_line_2": 'in fast jedem Spiel.',
            "mystery_question": "Wer ist Top-Scorer-Kandidat Nr. 1?",
            "highlight_fact": f"{p.get('goals')} Tore in {p.get('minutes')} Minuten",
        },
        "info": {
            "flag": team.get("flag","🏳"),
            "name": p["name"],
            "role_line": f"{team['name']} · {p.get('position','?')}",
            "stat1_val": str(p.get("goals", 0)), "stat1_lbl": "Tore",
            "stat2_val": str(p.get("assists", 0)), "stat2_lbl": "Assists",
            "stat3_val": f"{per90:.2f}", "stat3_lbl": "T / 90",
            "closing_line": f'<strong>{p["name"]} skaliert besser als Mbappé in der Quali.</strong> Top-Scorer-Quote vermutlich zu hoch — Modell sieht Edge.',
            "quote_line": f'<span class="acc">{p["name"]}</span> — Geheimtipp 2026. 🎯',
            "data_source": "Daten: WM-Quali 2024/25",
        },
    }


def _strat_zero_loss(wm: dict, exclude: set = None) -> dict | None:
    exclude = exclude or set()
    """Team ohne Niederlage in last 10."""
    candidates = []
    for tid, f in (wm.get("form") or {}).items():
        if not isinstance(f, dict): continue
        l = f.get("last10") or []
        if len(l) < 8: continue
        losses = sum(1 for r in l if r == "L")
        if losses == 0:
            wins = sum(1 for r in l if r == "W")
            candidates.append((tid, wins, f))
    if not candidates: return None
    candidates.sort(key=lambda x: -x[1])
    tid, wins, f = candidates[0]
    if tid in exclude: return None
    team = _find_team(wm, tid)
    return {
        "teamId": tid,
        "theme": "hidden_gem",
        "hook": {
            "big_number": f"{wins}",
            "sub_title":  "Siege · 0 Niederlagen",
            "hook_line_1": f'<span class="acc">{team["name"]}</span> seit',
            "hook_line_2": '10 Spielen unbesiegt.',
            "mystery_question": "Wieso unter dem Radar?",
            "highlight_fact": f"{wins}W in 10 Spielen · Form besser als Quoten",
        },
        "info": {
            "flag": team.get("flag","🏳"),
            "name": team["name"],
            "role_line": "Unbesiegt-Serie",
            "stat1_val": f"{wins}W", "stat1_lbl": "Siege",
            "stat2_val": f"{sum(1 for r in (f.get('last10') or []) if r=='D')}D", "stat2_lbl": "Remis",
            "stat3_val": "0L", "stat3_lbl": "Niederlagen",
            "closing_line": f'<strong>{team["name"]} reist mit ungeschlagener Bilanz zur WM.</strong> Markt rechnet damit nicht — Sieg-Quoten zeigen Edge.',
            "quote_line": f'<span class="acc">{team["name"]}</span> = stilles Wasser, tiefer Edge. 🌊',
            "data_source": "Daten: last 10 Spiele",
        },
    }


def _find_team(wm: dict, team_id: str) -> dict:
    for g in (wm.get("groups") or {}).values():
        for t in g.get("teams", []):
            if t.get("id") == team_id:
                return t
    return {"id": team_id, "name": team_id, "flag": "🏳"}


# ═══════════════════════════════════════════════════════════════════════════
#  RENDER + WRITE
# ═══════════════════════════════════════════════════════════════════════════

def write_cards(prefix: str, config: dict, today_iso: str, series_tag_override: str | None = None) -> dict:
    """Schreibt Hook + Info HTML in OUTPUT_DIR/<today>_<prefix>_*.html"""
    series_tag = series_tag_override if series_tag_override is not None else config.get("series_tag")

    hook_html = hook_card(theme=config["theme"], series_tag=series_tag, **config["hook"])
    info_html = info_card(theme=config["theme"], series_tag=series_tag, **config["info"])

    hook_path = OUTPUT_DIR / f"{today_iso}_{prefix}_hook.html"
    info_path = OUTPUT_DIR / f"{today_iso}_{prefix}_info.html"
    hook_path.write_text(hook_html, encoding="utf-8")
    info_path.write_text(info_html, encoding="utf-8")
    return {"hook_html": hook_path, "info_html": info_path}


def render_to_png(html_path: Path) -> Path | None:
    """HTML → PNG via Playwright Chromium. 360×640 mit DPI×2."""
    if SKIP_RENDER:
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"  ⚠️  playwright nicht installiert — überspringe PNG für {html_path.name}")
        return None

    png_path = html_path.with_suffix(".png")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(
                viewport={"width": 360, "height": 640},
                device_scale_factor=2,
            )
            page = context.new_page()
            page.goto(f"file://{html_path.absolute()}")
            page.wait_for_load_state("networkidle")
            # Screenshot nur des .card-Elements für saubere Ränder
            card = page.locator(".card")
            card.screenshot(path=str(png_path), omit_background=False)
            browser.close()
        print(f"  ✓ Render {png_path.name}")
        return png_path
    except Exception as e:
        print(f"  ❌ Render-Fehler {html_path.name}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════

def tg_send_photo(png_path: Path, caption: str = "") -> bool:
    if SKIP_TELEGRAM or not TELEGRAM_TOKEN or not TRADES_CHAT_ID:
        print(f"  ↪ Telegram skip ({png_path.name})")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    import http.client, mimetypes
    boundary = "----CocoBetBoundary"
    body_parts = []
    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{TRADES_CHAT_ID}\r\n")
    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"parse_mode\"\r\n\r\nHTML\r\n")
    if caption:
        body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n")
    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{png_path.name}\"\r\nContent-Type: image/png\r\n\r\n".encode("utf-8"))
    body = b""
    for part in body_parts:
        body += part.encode("utf-8") if isinstance(part, str) else part
    body += png_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            ok = json.loads(resp.read()).get("ok", False)
            print(f"  {'✓' if ok else '❌'} Telegram {png_path.name}")
            return ok
    except Exception as e:
        print(f"  ❌ Telegram-Fehler {png_path.name}: {e}")
        return False


def tg_send_text(text: str) -> bool:
    if SKIP_TELEGRAM or not TELEGRAM_TOKEN or not TRADES_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": TRADES_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"  ❌ Telegram-Text-Fehler: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

# ── Match-Preview-Cards (NEU 14.06.2026, Lucas) ───────────────────────────────
# Pro Match eine Story-Preview-Card (KEINE Quoten). Story = aiPreviews tgSnippet,
# Facts = Auto-Top-4 aus form/xgStats/elo/Wetter, Angle aus Spielcharakter.
_PREVIEW_ANGLES = {
    "torfest":  ("⚽ TOR-FEST ERWARTET",  "#3fb950", "63,185,80"),
    "defensiv": ("🛡 DEFENSIV-DUELL",     "#4cc9f0", "76,201,240"),
    "klasse":   ("🏆 KLASSEN-UNTERSCHIED", "#f0883e", "240,136,62"),
    "gruppe":   ("⚖️ GRUPPENSPIEL",        "#00d4a1", "0,212,161"),
}


def _preview_angle(form_h: dict, form_a: dict, elo_diff: float) -> str:
    fh, fa = form_h or {}, form_a or {}
    over = ((fh.get("over25Rate") or 0) + (fa.get("over25Rate") or 0)) / 2
    goals = (fh.get("avgGoals") or 0) + (fa.get("avgGoals") or 0)
    conc = ((fh.get("avgConceded") if fh.get("avgConceded") is not None else 9)
            + (fa.get("avgConceded") if fa.get("avgConceded") is not None else 9)) / 2
    if abs(elo_diff) >= 250:
        return "klasse"
    if over >= 0.60 or goals >= 5.6:
        return "torfest"
    if conc <= 0.85 or over <= 0.42:
        return "defensiv"
    return "gruppe"


def _preview_facts(fx, flag_h, name_h, flag_a, name_a,
                   form_h, form_a, xg_h, xg_a, elo_diff) -> list:
    """Sammelt Fact-Kandidaten mit Interessantheits-Score, gibt Top-4-Strings zurück."""
    cand = []  # (score, text)

    def team_facts(tflag, tname, f, xg):
        f = f or {}
        l5 = f.get("last5") or []
        w, l = l5.count("W"), l5.count("L")
        if len(l5) >= 5 and w == 5:
            cand.append((9.0, f"🔥 {tflag} {tname}: 5 Siege in Folge"))
        elif w >= 4:
            cand.append((6.0, f"📈 {tflag} {tname}: {w} von 5 gewonnen"))
        if l >= 4:
            cand.append((5.0, f"📉 {tflag} {tname}: {l} Pleiten in 5"))
        ac = f.get("avgConceded")
        if ac is not None and ac <= 0.7:
            cand.append((7.0, f"🛡 {tflag} {tname}: nur {ac:.1f} Gegentore Ø"))
        asc = f.get("avgScored")
        if asc and asc >= 2.3:
            cand.append((6.0, f"⚽ {tflag} {tname}: {asc:.1f} Tore Ø"))
        o = f.get("over25Rate")
        if o is not None:
            if o >= 0.65:
                cand.append((5.0, f"📊 {tflag} {tname}: {round(o*100)}% Über 2.5"))
            elif o <= 0.34:
                cand.append((5.0, f"🔒 {tflag} {tname}: {round(o*100)}% Über 2.5"))
        if xg:
            r = xg.get("ratingAvg")
            if r and r >= 7.3:
                cand.append((4.5, f"📋 {tflag} {tname}: Form-Rating {r:.1f}"))

    team_facts(flag_h, name_h, form_h, xg_h)
    team_facts(flag_a, name_a, form_a, xg_a)

    # Match-Level
    if abs(elo_diff) >= 150:
        fav_flag, fav_name = (flag_h, name_h) if elo_diff > 0 else (flag_a, name_a)
        cand.append((min(8.0, abs(elo_diff) / 60), f"📊 {fav_flag} {fav_name}: +{round(abs(elo_diff))} Elo"))
    wx = (fx.get("weather") or {})
    temp = wx.get("tempAtKickoff") if wx.get("tempAtKickoff") is not None else wx.get("tempMax")
    if isinstance(temp, (int, float)) and temp >= 30:
        cand.append((4.0, f"🌡 {round(temp)}°C im Stadion"))
    ven = (fx.get("venue") or "")
    if "Mexico City" in ven or "Azteca" in ven:
        cand.append((5.5, "🏔 Höhe: 2.240m über dem Meer"))

    cand.sort(key=lambda x: -x[0])
    out, seen = [], set()
    for _, txt in cand:
        if txt in seen:
            continue
        seen.add(txt)
        out.append(txt)
        if len(out) == 4:
            break
    return out


STREAK_MILESTONES = [6, 8, 10, 12, 15]


def _streak_heat(s: dict) -> int:
    h = s.get("length", 0) or 0
    st = (s.get("continuation") or {}).get("state")
    if st == "intakt":
        h += 2
    elif st == "wackelt":
        h -= 3
    si = s.get("signalInfo") or {}
    if si.get("state") == "confirm":
        h += si.get("count", 0) or 0
    return h


def _streak_milestone(length: int):
    ms = [m for m in STREAK_MILESTONES if (length or 0) >= m]
    return ms[-1] if ms else None


def _streak_short_date(iso):
    p = str(iso or "")[:10].split("-")
    return f"{p[2]}.{p[1]}." if len(p) == 3 else ""


def pick_streak_for_card(streaks: list, posted_keys: set):
    """Reiner Selektor (testbar): heißeste Serie wählen, die (a) Gesamt-Serie, (b) intakt, (c) einen
    Meilenstein erreicht und (d) für diesen Meilenstein noch NICHT gepostet wurde. Returns (s,key)|None."""
    cands = []
    for s in (streaks or []):
        if (s.get("venue") or "all") != "all":
            continue   # nur Gesamt-Serien (keine H/A-Duplikate)
        if (s.get("continuation") or {}).get("state") != "intakt":
            continue   # nur heiße Serien
        ms = _streak_milestone(s.get("length", 0))
        if ms is None:
            continue
        key = f"streak:{s.get('teamId')}:{s.get('type')}:{ms}"
        if key in (posted_keys or set()):
            continue   # diesen Meilenstein schon gepostet
        cands.append((s, key))
    if not cands:
        return None
    # 04.07.2026 (Lucas: „Card kommt immer nach dem Spiel"): forward-looking bevorzugen — eine
    # Serie MIT anstehendem Spiel (next.date, aus _next_fixtures inkl. KO) wird zur Vorschau
    # „Hält die Serie gegen X?". Ausgeschiedene Teams (kein next) nur als Evergreen-Fallback,
    # wenn es an einem ruhigen Tag keine forward-looking Serie gibt.
    forward = [c for c in cands if (c[0].get("next") or {}).get("date")]
    pool = forward or cands
    return max(pool, key=lambda c: _streak_heat(c[0]))


def build_streak_cards(today_iso: str, dedup: dict) -> list:
    """Bis zu 1 Serien-Spotlight/Tag — NUR wenn eine Serie heiß ist (intakt) UND einen neuen
    Meilenstein (6/8/10/12/15×) erreicht (Meilenstein-Dedup → nie täglich dieselbe Serie). An starken
    Tagen near-daily, an ruhigen weniger — aber nie eine schwache Pflicht-Card. TikTok-safe (29.06.2026,
    Lucas). Liest wm_streaks.json (compute_streaks). Returns [(label, png, caption)] oder []."""
    try:
        data = json.loads(D.file("wm_streaks.json", "liga_streaks.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    posted = {h.get("streakKey") for h in (dedup.get("history") or []) if h.get("streakKey")}
    chosen = pick_streak_for_card(data.get("streaks") or [], posted)
    if not chosen:
        return []
    s, key = chosen
    si = s.get("signalInfo") or {}
    nx = s.get("next") or {}
    opp = nx.get("oppName")
    hook = f"Hält die Serie{(' gegen ' + opp) if opp else ''}?"
    html = streak_card(
        team=s.get("team", ""), team_id=s.get("teamId"), market=s.get("market", ""),
        length=s.get("length", 0), seq=s.get("seq"),
        state=(s.get("continuation") or {}).get("state", "neutral"),
        signal_confirm=(si.get("state") == "confirm"),
        next_opp=opp, next_date=_streak_short_date(nx.get("date")),
        hook=hook, league_name=s.get("leagueName", ""), flag=s.get("flag", ""),
    )
    path = OUTPUT_DIR / f"{today_iso}_streak_{s.get('teamId')}_{s.get('type')}.html"
    path.write_text(html, encoding="utf-8")
    png = render_to_png(path)
    if not png:
        return []
    caption = (f"🔥 <b>Serie · {s.get('team')}</b> — {s.get('length')}× in Folge "
               f"{s.get('market')}. {hook}")
    dedup.setdefault("history", []).append({"date": today_iso, "streakKey": key})
    return [(f"streak_{s.get('teamId')}_{s.get('type')}", png, caption)]


def _iter_match_contexts(wm: dict):
    """Yields (fx, teams, group_label, pkey) über Gruppenspiele + bothResolved KO-Spiele.
    29.06.2026 (Lucas: „keine Review/Preview, aber Killer-Stat"): in der KO-Phase liegen die Spiele in
    koFixtures statt groups → Preview/Review fanden nichts → Killer-Stat-Fallback feuerte. KO: globale
    Team-Union (KO-Fixtures haben nur IDs), roundLabel statt Gruppe, pkey wie generate_wm_picks (KO-…)."""
    for gkey, gdata in (wm.get("groups") or {}).items():
        teams = {t["id"]: t for t in gdata.get("teams", [])}
        for fx in gdata.get("fixtures", []):
            yield fx, teams, f"Gruppe {gkey} · ST {fx.get('matchday')}", \
                f"{gkey}-{fx.get('matchday')}-{fx['home']}-{fx['away']}"
    all_teams = {}
    for gd in (wm.get("groups") or {}).values():
        for t in gd.get("teams", []):
            all_teams[t["id"]] = t
    for fx in (wm.get("koFixtures") or []):
        if not (fx.get("home") and fx.get("away")):
            continue   # offene Paarung (TBD) → keine Card
        rnd = fx.get("round") or "KO"
        yield fx, all_teams, f"🏆 {fx.get('roundLabel') or rnd}", \
            f"KO-{rnd}-{fx['home']}-{fx['away']}"


def build_match_preview_cards(wm: dict, today_iso: str) -> list:
    """Baut pro heutigem Match eine Preview-Card → Liste (label, png_path, caption). Inkl. KO-Spiele."""
    produced = []
    forms = wm.get("form") or {}
    xgs = wm.get("xgStats") or {}
    previews = wm.get("aiPreviews") or {}
    from datetime import datetime as _dt
    try:
        date_obj = _dt.fromisoformat(today_iso)
        wd = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][date_obj.weekday()]
        date_label = f"{wd} · {date_obj.strftime('%d.%m.%Y')}"
    except Exception:
        date_label = today_iso

    for fx, teams, group_label, pkey in _iter_match_contexts(wm):
            if fx.get("date") != today_iso:
                continue
            hid, aid = fx["home"], fx["away"]
            h, a = teams.get(hid, {}), teams.get(aid, {})
            prev = previews.get(pkey) or {}
            story = (prev.get("tgSnippet") or "").strip()
            if not story:
                continue   # ohne Story keine Card
            form_h, form_a = forms.get(hid, {}), forms.get(aid, {})
            elo_diff = (h.get("elo") or 0) - (a.get("elo") or 0)
            angle_key = _preview_angle(form_h, form_a, elo_diff)
            angle_label, accent, rgb = _PREVIEW_ANGLES[angle_key]
            flag_h, flag_a = h.get("flag", "🏳️"), a.get("flag", "🏳️")
            name_h, name_a = h.get("name", hid), a.get("name", aid)
            facts = _preview_facts(fx, flag_h, name_h, flag_a, name_a,
                                   form_h, form_a, xgs.get(hid), xgs.get(aid), elo_diff)
            kickoff_label = (fx.get("time", "") + " Uhr").strip()
            venue = (fx.get("venue") or "").split("·")[0].strip()[:34]
            html = match_preview_card(
                date_label=date_label, flag_h=flag_h, name_h=name_h,
                flag_a=flag_a, name_a=name_a, kickoff_label=kickoff_label,
                venue=venue, group_label=group_label,
                angle_label=angle_label, accent=accent, accent_rgb=rgb,
                story_text=story, facts=facts,
            )
            path = OUTPUT_DIR / f"{today_iso}_preview_{hid}_{aid}.html"
            path.write_text(html, encoding="utf-8")
            png = render_to_png(path)
            if png:
                produced.append((f"preview_{hid}_{aid}", png,
                                 f"🎬 <b>Preview · {name_h} vs {name_a}</b> · {kickoff_label}"))
    return produced


# ── Match-Review-Cards (NEU 20.06.2026, Lucas) ────────────────────────────────
# Nachbericht der VORTAGS-Spiele (die wir am Tag davor als Preview hatten). KEINE Quoten,
# kein Wett-Inhalt — Endstand + Chancen-Analyse (xG vs Ergebnis) + Stat-Chips. Ersetzt die
# schwächeren Killer-Stat/Story-Cards als Daily-Content (die bleiben Fallback).
_REVIEW_ANGLES = {
    "verdient":    ("✅ VERDIENTER SIEG",         "#3fb950", "63,185,80"),
    "raubzug":     ("🍀 GLÜCKLICHER SIEG",        "#f0883e", "240,136,62"),
    "unglueck":    ("😤 LEISTUNG OHNE LOHN",      "#e3b341", "227,179,65"),
    "torfest":     ("⚽ TOR-FESTIVAL",            "#3fb950", "63,185,80"),
    "abwehr":      ("🛡 ABWEHRSCHLACHT",          "#4cc9f0", "76,201,240"),
    "nachbericht": ("📊 NACHBERICHT",             "#00d4a1", "0,212,161"),
}


def _review_angle(sh: int, sa: int, xgh, xga) -> str:
    """Spielcharakter aus Ergebnis + xG (verdient/glücklich/unglücklich/torfest/abwehr)."""
    xgh, xga = (xgh or 0.0), (xga or 0.0)
    g = sh + sa
    if sh == sa:  # Remis
        if abs(xgh - xga) >= 1.0:
            return "unglueck"        # einer dominierte die Chancen, nur Remis
        if g >= 4:
            return "torfest"
        if g <= 1 and (xgh + xga) <= 1.6:
            return "abwehr"
        return "nachbericht"
    win_xg, los_xg = (xgh, xga) if sh > sa else (xga, xgh)
    if win_xg + 0.4 < los_xg:
        return "raubzug"             # Sieger hatte weniger xG als der Verlierer
    if g >= 4:
        return "torfest"
    if abs(sh - sa) >= 2 or (win_xg - los_xg) >= 0.5:
        return "verdient"            # klare Tordifferenz ODER deutliches Chancen-Plus
    return "nachbericht"


def _review_recap(angle: str, name_h: str, sh: int, name_a: str, sa: int, xgh, xga) -> str:
    """Lockerer 1-2-Satz-Nachbericht, datengetrieben, ohne Jargon."""
    xg = (f"xG {(xgh or 0):.1f}:{(xga or 0):.1f}") if (xgh or xga) else ""
    win = name_h if sh > sa else name_a
    los = name_a if sh > sa else name_h
    big, small = max(sh, sa), min(sh, sa)
    if angle == "raubzug":
        return (f"{win} nimmt die drei Punkte mit, obwohl {los} das bessere Spiel machte — "
                f"die Chancen ({xg}) sprachen für die andere Seite. Effizienz schlägt Übergewicht.")
    if angle == "unglueck":
        return (f"Leistung ohne Lohn: trotz klarer Chancen-Überlegenheit ({xg}) bleibt es beim "
                f"{sh}:{sa}. Das hätte deutlich mehr verdient gehabt.")
    if angle == "torfest":
        return (f"Spektakel mit {sh + sa} Toren — {name_h} und {name_a} liefern sich einen "
                f"offenen Schlagabtausch, am Ende steht es {sh}:{sa}.")
    if angle == "abwehr":
        return (f"Zähe Defensiv-Partie mit kaum echten Chancen ({xg}) — am Ende ein enges {sh}:{sa}.")
    if angle == "verdient":
        return (f"{win} gewinnt verdient {big}:{small} — die klar bessere Mannschaft, "
                f"auch nach den Chancen ({xg}).")
    if sh == sa:
        return f"Punkteteilung beim {sh}:{sa} — die Chancen hielten sich die Waage ({xg})."
    return f"{win} setzt sich {big}:{small} gegen {los} durch ({xg})."


def _review_facts(stats: dict, sh: int, sa: int) -> list:
    """Stat-Chips aus result.stats (echte API-Werte: Schüsse/aufs Tor/Strafraum + xG)."""
    def _i(v):
        try: return int(round(float(v)))
        except (TypeError, ValueError): return None
    f = [f"⚽ Tore {sh}:{sa}"]
    if stats.get("homeXg") is not None and stats.get("awayXg") is not None:
        f.append(f"📊 xG {stats['homeXg']:.1f}:{stats['awayXg']:.1f}")
    sh_, sa_ = _i(stats.get("homeShots")), _i(stats.get("awayShots"))
    if sh_ is not None and sa_ is not None:
        f.append(f"🎯 Schüsse {sh_}:{sa_}")
    so_h, so_a = _i(stats.get("homeSot")), _i(stats.get("awaySot"))
    if so_h is not None and so_a is not None:
        f.append(f"🥅 aufs Tor {so_h}:{so_a}")
    in_h, in_a = _i(stats.get("homeInside")), _i(stats.get("awayInside"))
    if in_h is not None and in_a is not None:
        f.append(f"📍 im Strafraum {in_h}:{in_a}")
    return f[:5]


def build_match_review_cards(wm: dict, today_iso: str) -> list:
    """Baut pro GESTRIGEM fertigem Match eine Review-Card → Liste (label, png_path, caption)."""
    produced = []
    from datetime import datetime as _dt, timedelta as _td
    try:
        yest_obj = _dt.fromisoformat(today_iso).date() - _td(days=1)
        yest = yest_obj.isoformat()
        wd = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][yest_obj.weekday()]
        date_label = f"{wd} · {yest_obj.strftime('%d.%m.%Y')}"
    except Exception:
        return produced

    for fx, teams, group_label, _pkey in _iter_match_contexts(wm):
            if fx.get("date") != yest:
                continue
            r = fx.get("result") or {}
            if r.get("status") not in ("FT", "AET", "PEN"):
                continue
            sh, sa = r.get("home_score"), r.get("away_score")
            if sh is None or sa is None:
                continue
            stats = r.get("stats") or {}
            hid, aid = fx["home"], fx["away"]
            h, a = teams.get(hid, {}), teams.get(aid, {})
            flag_h, flag_a = h.get("flag", "🏳️"), a.get("flag", "🏳️")
            name_h, name_a = h.get("name", hid), a.get("name", aid)
            xgh, xga = stats.get("homeXg"), stats.get("awayXg")
            angle = _review_angle(sh, sa, xgh, xga)
            angle_label, accent, rgb = _REVIEW_ANGLES[angle]
            recap = _review_recap(angle, name_h, sh, name_a, sa, xgh, xga)
            facts = _review_facts(stats, sh, sa)
            html = match_review_card(
                date_label=date_label, flag_h=flag_h, name_h=name_h, score_h=sh,
                flag_a=flag_a, name_a=name_a, score_a=sa,
                group_label=group_label,
                angle_label=angle_label, accent=accent, accent_rgb=rgb,
                recap_text=recap, facts=facts,
            )
            path = OUTPUT_DIR / f"{today_iso}_review_{hid}_{aid}.html"
            path.write_text(html, encoding="utf-8")
            png = render_to_png(path)
            if png:
                produced.append((f"review_{hid}_{aid}", png,
                                 f"📊 <b>Review · {name_h} {sh}:{sa} {name_a}</b>"))
    return produced


def main():
    override = os.environ.get("DAILY_TIKTOK_DATE", "").strip()
    today_iso = override or date.today().isoformat()
    print(f"=== generate_daily_tiktok.py · {today_iso} ===\n")

    # ─── Anti-Double-Send Guard (Backup-Cron-Schutz) ──────────────────────────
    # Wenn der primäre Cron (04:00 UTC) heute schon Cards generiert + gesendet
    # hat, würde der Backup-Cron (05:30 UTC) sonst Bizarre/Story doppelt senden
    # (Story-Plan ist pro-Datum fix, Bizarre-Picker hat keine Tages-Dedup).
    # Marker: heute_iso in tiktok_sent.json.history?
    # Plus: Force-Override via SKIP_GUARD=true (für Smoketests).
    skip_guard = os.environ.get("SKIP_GUARD", "").lower() == "true"
    if not skip_guard and not override:
        _early_dedup = load_dedup()
        _today_done = any(h.get("date") == today_iso for h in _early_dedup.get("history", []))
        _existing_pngs = list(OUTPUT_DIR.glob(f"{today_iso}_*.png"))
        if _today_done and _existing_pngs:
            print(f"⏭️  Cards für {today_iso} bereits generiert ({len(_existing_pngs)} PNGs) "
                  f"und gesendet → Backup-Cron skipt. SKIP_GUARD=true zum Forcieren.")
            return

    # wm einmal laden
    wm = None
    if WM_FILE.exists():
        try:
            wm = json.loads(WM_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️  wm2026-data.json nicht lesbar: {e}")

    # 1. Vortags-Reviews = PRIMÄRER Daily-Content (20.06.2026, Lucas). Nachbericht der Spiele,
    #    die wir am Tag davor als Preview hatten — Endstand + Chancen-Analyse + Stats.
    reviews = []
    if SEND_REVIEWS and wm:
        try:
            reviews = build_match_review_cards(wm, today_iso)
            print(f"📊 Match-Review-Cards (Vortag): {len(reviews)} Spiel(e)")
        except Exception as e:
            print(f"⚠️  Match-Review-Cards fehlgeschlagen: {e}")

    dedup = load_dedup()
    excluded = MANUAL_POSTED_TEAMS | recently_sent_team_ids(dedup, today_iso)

    # 2. Story-Serie + Killer-Stat — nur FALLBACK, wenn es heute KEINE Reviews gibt.
    story, fact = None, None
    if reviews:
        print("📖⚡ Story + Killer-Stat heute übersprungen — Reviews sind der Content (Fallback aus)")
    else:
        story = get_story_for_date(today_iso)
        print(f"📖 Story für heute: {story.get('series_tag','?')}" if story
              else "📖 Keine Story für heute geplant")
        print(f"🚫 Ausgeschlossen (manuell + letzte {DEDUP_WINDOW_DAYS} Tage): {sorted(excluded)}")
        if wm and SEND_KILLER_STAT:
            try:
                fact = pick_daily_killer_stat(wm, today_iso, exclude_team_ids=excluded)
            except Exception as e:
                print(f"⚠️  Killer-Stat fehlgeschlagen: {e}")
        if not SEND_KILLER_STAT:
            print("⚡ Killer-Stat aus (SEND_KILLER_STAT=false) — Lucas: brauchen wir nicht")
        else:
            print(f"⚡ Daily Killer-Stat: {fact['info']['name']}" if fact
                  else "⚡ Kein Killer-Stat heute")

    if not story and not fact and not reviews:
        print("\nNichts zu posten. Ende.")
        return

    # 3. HTML + PNG erzeugen
    print()
    produced = []  # list of (label, png_path, caption)
    produced.extend(reviews)   # Vortags-Reviews (schon gerendert in build_match_review_cards)
    if story:
        paths = write_cards("story", story, today_iso)
        for kind in ("hook", "info"):
            html = paths[f"{kind}_html"]
            png = render_to_png(html)
            if png:
                caption = (
                    f"📖 <b>Story · {story.get('series_tag','')}</b> · {kind.upper()}"
                    if kind == "hook" else
                    f"📖 <b>Story · {story.get('series_tag','')}</b> · DETAIL"
                )
                produced.append((f"story_{kind}", png, caption))

    if fact:
        paths = write_cards("fact", fact, today_iso, series_tag_override="DAILY KILLER-STAT")
        for kind in ("hook", "info"):
            html = paths[f"{kind}_html"]
            png = render_to_png(html)
            if png:
                caption = (
                    f"⚡ <b>Daily Killer-Stat · {kind.upper()}</b>"
                    if kind == "hook" else
                    f"⚡ <b>Daily Killer-Stat · DETAIL</b>"
                )
                produced.append((f"fact_{kind}", png, caption))

    # ── 3. Bizarre-Quote (PAUSIERT 16.06.2026, Lucas: fad + Quoten-Leak) ──
    bizarre = get_daily_bizarre_card(today_iso) if SEND_BIZARRE else None
    if not SEND_BIZARRE:
        print("🤡 Bizarre-Quote pausiert (SEND_BIZARRE=false)")
    if bizarre:
        print(f"🤡 Bizarre Quote: {bizarre['target']['name']} ({bizarre['info']['quote_str']} = {bizarre['info']['chance_pct']})")
        # Bizarre nutzt eigenes bizarre_info_card statt info_card
        # Hook nutzt das gleiche hook_card-Template
        b_hook_html = hook_card(series_tag="BIZARRE-QUOTE", **bizarre["hook"])
        b_info_html = bizarre_info_card(series_tag="BIZARRE-QUOTE", **bizarre["info"])
        b_hook_path = OUTPUT_DIR / f"{today_iso}_bizarre_hook.html"
        b_info_path = OUTPUT_DIR / f"{today_iso}_bizarre_info.html"
        b_hook_path.write_text(b_hook_html, encoding="utf-8")
        b_info_path.write_text(b_info_html, encoding="utf-8")

        for kind, path in (("hook", b_hook_path), ("info", b_info_path)):
            png = render_to_png(path)
            if png:
                caption = (
                    f"🤡 <b>Bizarre-Quote · {bizarre['target']['name']}</b> · {kind.upper()}"
                    if kind == "hook" else
                    f"🤡 <b>Bizarre-Quote · {bizarre['target']['name']}</b> · DETAIL"
                )
                produced.append((f"bizarre_{kind}", png, caption))
    else:
        print("🤡 Keine Bizarre-Card heute (Targets-File leer oder fehlt)")

    # ── 3b. Match-Preview-Cards (NEU 14.06.2026) — je Match eine Story-Card ──
    if SEND_PREVIEWS and WM_FILE.exists():
        try:
            wm_prev = json.loads(WM_FILE.read_text(encoding="utf-8"))
            preview_cards = build_match_preview_cards(wm_prev, today_iso)
            produced.extend(preview_cards)
            print(f"🎬 Match-Preview-Cards: {len(preview_cards)} Spiel(e)")
        except Exception as e:
            print(f"⚠️  Match-Preview-Cards fehlgeschlagen: {e}")

    # ── 3c. Serien-Spotlight (29.06.2026, Lucas) — heiß + neuer Meilenstein, sonst nichts ──
    if SEND_STREAKS:
        try:
            streak_cards = build_streak_cards(today_iso, dedup)
            produced.extend(streak_cards)
            print(f"🔥 Serien-Spotlight: {len(streak_cards)} Card"
                  if streak_cards else "🔥 Keine qualifizierende Serie heute (gegated)")
        except Exception as e:
            print(f"⚠️  Serien-Card fehlgeschlagen: {e}")

    # ── 4. Daily-Picks-Card (Top-Pick + bis zu 3 weitere) ──
    # Sammelt alle Picks für today_iso aus wm2026-data.json und rendert
    # eine zusammenfassende Card im CocoBet-Style (360×640).
    # Nur wenn mind. 1 BET oder ABWÄGEN vorhanden — sonst kein Posting.
    daily_picks_data = None
    if WM_FILE.exists():
        try:
            wm = json.loads(WM_FILE.read_text(encoding="utf-8"))
            collected = []
            for gkey, gdata in (wm.get("groups") or {}).items():
                teams = {t["id"]: t for t in gdata.get("teams", [])}
                for fx in gdata.get("fixtures", []):
                    if fx.get("date") != today_iso:
                        continue
                    pkey = f"{gkey}-{fx['matchday']}-{fx['home']}-{fx['away']}"
                    plist = (wm.get("picks") or {}).get(pkey, [])
                    # FIX 11.06.2026: trackingExcluded (Cross-Market-Konflikte) + synthetische
                    # Insurance-Picks raus — nie als "Pick des Tages" auf eine TikTok-Card.
                    bets = [p for p in plist if p.get("verdict") == "BET"
                            and not p.get("trackingExcluded") and not p.get("synthetic")]
                    abws = [p for p in plist if p.get("verdict") == "ABWÄGEN"
                            and not p.get("trackingExcluded") and not p.get("synthetic")]
                    bets.sort(key=lambda p: -(p.get("edgePP") or 0))
                    abws.sort(key=lambda p: -(p.get("edgePP") or 0))
                    best = (bets + abws)[:1]
                    if not best:
                        continue
                    h = teams.get(fx["home"], {})
                    a = teams.get(fx["away"], {})
                    p = best[0]
                    # Top-Signal extrahieren (höchster |score|)
                    SIG_LABELS = {
                        "weather_signal": "🌡 Hitze", "travel_burden": "✈ Reise",
                        "pressure_index": "🎯 Druck", "form_trend": "📈 Form",
                        "xg_strength": "🥅 xG", "h2h_pattern": "🤝 H2H",
                        "injury": "🩹 Verletzung", "apif_predictions": "📊 APIF",
                        "lead_lag_bias": "📡 Sharp-Lag", "public_static_bias": "🎲 Public-Bias",
                        "incentive_signal": "🏆 Anreiz", "lineup_signal": "📋 Lineup",
                    }
                    top_sig = None
                    sigs = p.get("signals") or []
                    if sigs:
                        s_best = max(sigs, key=lambda s: abs(s.get("score", 0)), default=None)
                        if s_best and abs(s_best.get("score", 0)) >= 0.5:
                            lbl = SIG_LABELS.get(s_best.get("name"), s_best.get("name", "")[:10])
                            top_sig = f"{lbl} {s_best['score']:+.1f}pp"
                    collected.append({
                        "flag_h": h.get("flag", "🏳️"),
                        "name_h": h.get("name", fx["home"]),
                        "flag_a": a.get("flag", "🏳️"),
                        "name_a": a.get("name", fx["away"]),
                        "time": fx.get("time", "21:00") + " Uhr",
                        "venue": (fx.get("venue") or "").split("·")[0].strip()[:30],
                        "market": p.get("market", "?"),
                        "odds": float(p.get("odds") or 0),
                        "edge_pp": p.get("edgePP", 0),
                        "verdict": p.get("verdict"),
                        # Engine-Felder (NEU 09.06.2026) — werden vom Template gerendert
                        "convictionScore": p.get("convictionScore"),
                        "sharpMoveActive": bool(p.get("sharpMoveActive")),
                        "topSignal": top_sig,
                        "lamTotal": p.get("lamTotal"),   # für Pick-Hook-Card (Tor-Märkte)
                        "_edge_score": (p.get("edgePP") or 0) + (10 if p.get("verdict") == "BET" else 0),
                    })
            if collected:
                collected.sort(key=lambda p: -p["_edge_score"])
                hero = collected[0]
                # Story-Snippet markt-abhängig ableiten (FIX 12.06.2026: vorher
                # stand bei Edge≥10 IMMER "Edge auf den Underdog" — komplett falsch
                # für Tor-Märkte (Über/Unter) und wenn der Pick auf den FAVORITEN
                # geht (z.B. USA Über 1.5). Jetzt: beschreibt den echten Markt.)
                hero["story"] = _pick_story_line(hero)
                # Selbst-Schutz: falls die Story je wieder „Underdog/Außenseiter"
                # bei einem Nicht-Auswärts-Markt behauptet → auf neutral zurückfallen.
                if not _story_market_consistent(hero["story"], hero.get("market")):
                    hero["story"] = "Modell sieht Edge über dem Markt."
                    print(f"⚠️  Card-Story-Guard: Underdog-Text bei Markt "
                          f"'{hero.get('market')}' verhindert")
                daily_picks_data = {
                    "hero": hero,
                    "others": collected[1:4],
                    "n_matches": len(collected),
                }
        except Exception as e:
            print(f"⚠️  Daily-Picks-Card-Daten konnten nicht geladen werden: {e}")

    if daily_picks_data and SEND_DAILY_PICKS:
        from datetime import datetime as _dt
        date_obj = _dt.fromisoformat(today_iso)
        wd = ["Mo","Di","Mi","Do","Fr","Sa","So"][date_obj.weekday()]
        date_label = f"{wd} · {date_obj.strftime('%d.%m.%Y')}"
        # ── Pick-Hook-Card (NEU 13.06.2026) ──────────────────────────────────
        # Mystery-Hook VOR der Pick-Card (3-5 Sek Curiosity-Gap → Retention).
        # Verrät den Markt bewusst nicht. Gleicher Stil wie fact/story/bizarre-Hooks.
        try:
            dph_html = hook_card(**_pick_hook_config(daily_picks_data["hero"]))
            dph_path = OUTPUT_DIR / f"{today_iso}_daily_picks_hook.html"
            dph_path.write_text(dph_html, encoding="utf-8")
            dph_png = render_to_png(dph_path)
            if dph_png:
                _h = daily_picks_data["hero"]
                produced.append(("daily_picks_hook",
                                 dph_png,
                                 f"🎯 Hook · {_h['name_h']} vs {_h['name_a']} — Pick im Video"))
                print("⚡ Pick-Hook-Card gerendert")
        except Exception as _e:
            print(f"⚠️  Pick-Hook-Card fehlgeschlagen: {_e}")

        dp_html = daily_picks_card(
            date_label=date_label,
            n_matches=daily_picks_data["n_matches"],
            hero_pick=daily_picks_data["hero"],
            other_picks=daily_picks_data["others"],
            closing_line='Picks aus eigenem Modell · jeder mit Edge-Begründung. <strong>cocobet.</strong>',
            season_phase="WM 2026 · Gruppenphase",
            series_tag="DAILY PICKS",
        )
        dp_path = OUTPUT_DIR / f"{today_iso}_daily_picks.html"
        dp_path.write_text(dp_html, encoding="utf-8")
        png = render_to_png(dp_path)
        if png:
            hero = daily_picks_data["hero"]
            caption = (
                f"⚡ <b>Daily Picks · {date_label}</b>\n"
                f"Top-Pick: {hero['name_h']} vs {hero['name_a']} — {hero['market']} @{hero['odds']:.2f} (+{hero['edge_pp']}pp)\n"
                f"{daily_picks_data['n_matches']} Spiele heute · weitere im Blick"
            )
            produced.append(("daily_picks", png, caption))
        print(f"⚡ Daily-Picks-Card: {daily_picks_data['hero']['name_h']} vs {daily_picks_data['hero']['name_a']} (+{daily_picks_data['hero']['edge_pp']}pp)")
    else:
        print("⚡ Keine Daily-Picks-Card heute (keine BET/ABWÄGEN für today_iso)")

    # ── 5. Spieler-Pick (TheOddsAPI Player Props — kommt erst 1-3 Tage vor Anpfiff) ──
    player_pick = None
    try:
        player_pick = get_daily_player_pick(today_iso)
    except Exception as e:
        print(f"⚠️  Spieler-Pick-Picker fehlgeschlagen: {e}")

    if player_pick:
        cfg = player_pick["config"]
        print(f"🎯 Spieler-Pick: {cfg['player_name']} · {cfg['market_label']} @{cfg['odds']}")
        pp_html = player_pick_card(series_tag="SPIELER-PICK", **cfg)
        pp_path = OUTPUT_DIR / f"{today_iso}_player_pick.html"
        pp_path.write_text(pp_html, encoding="utf-8")
        png = render_to_png(pp_path)
        if png:
            caption = (
                f"🎯 <b>Spieler-Pick · {cfg['player_name']}</b>\n"
                f"{cfg['market_label']} @{cfg['odds']:.2f} ({cfg['bookmaker'].title()})"
            )
            produced.append(("player_pick", png, caption))
    else:
        print("🎯 Kein Spieler-Pick heute (Props noch nicht offen oder kein PICK-verdict)")

    # 5. Telegram Header + alle PNGs senden
    sent_to_telegram = False
    if produced:
        if not SKIP_TELEGRAM and TELEGRAM_TOKEN and TRADES_CHAT_ID:
            tg_send_text(
                f"🎬 <b>CocoBet · TikTok-Cards · {today_iso}</b>\n"
                f"Screen machen → posten. Reihenfolge: Hook → Info."
            )
            for label, png, caption in produced:
                tg_send_photo(png, caption)
            sent_to_telegram = True
            print(f"\n✅ {len(produced)} Cards generiert und gepusht")
        else:
            print(f"\n✅ {len(produced)} Cards generiert (Telegram skip — SKIP_TELEGRAM oder Token fehlt)")
    else:
        print("\n⚠️  Keine Renderings — vermutlich Playwright fehlt oder SKIP_RENDER aktiv")

    # 5. Dedup-State updaten — NUR wenn auch wirklich auf Telegram gesendet wurde.
    # Damit Smoketests (SKIP_TELEGRAM=true) keinen falschen Eintrag erzeugen
    # der nachher den nächsten Live-Lauf blockt.
    #
    # Bug-Fix 09.06.2026: Vorher wurde der dedup-Marker NUR bei `fact`
    # (Killer-Stat) geschrieben. Wenn nur Story-Cards gesendet wurden, fehlte
    # der Tages-Marker → Backup-Cron um 05:30 UTC sah "heute noch nicht
    # gesendet" und sendete die Cards nochmal. Jetzt: Marker IMMER schreiben
    # sobald ETWAS auf Telegram raus ist.
    if sent_to_telegram:
        if fact and fact.get("teamId"):
            dedup.setdefault("history", []).append({"date": today_iso, "teamId": fact["teamId"]})
        elif fact and fact.get("teamIds"):
            for tid in fact["teamIds"]:
                dedup.setdefault("history", []).append({"date": today_iso, "teamId": tid})
        else:
            # Story-only oder ähnliches — leerer Marker damit Guard heute_iso findet
            dedup.setdefault("history", []).append({"date": today_iso, "teamId": None})
        # Trim auf letzte 30 Tage
        from datetime import timedelta
        cutoff = (date.fromisoformat(today_iso) - timedelta(days=30)).isoformat()
        dedup["history"] = [h for h in dedup["history"] if h.get("date", "") >= cutoff]
        save_dedup(dedup)
        print(f"💾 Dedup-State aktualisiert ({len(dedup['history'])} Einträge)")

    # 6. Player-Pick Dedup (Spielername, 14 Tage)
    if player_pick and sent_to_telegram:
        pdedup = _load_player_dedup()
        pdedup.setdefault("history", []).append({
            "date":   today_iso,
            "player": player_pick["player"],
            "match":  player_pick["match_key"],
        })
        # Trim auf letzte 30 Tage
        from datetime import timedelta as _td
        cutoff = (date.fromisoformat(today_iso) - _td(days=30)).isoformat()
        pdedup["history"] = [h for h in pdedup["history"] if h.get("date", "") >= cutoff]
        save_player_dedup(pdedup)
        print(f"💾 Player-Pick-Dedup aktualisiert ({len(pdedup['history'])} Einträge)")


if __name__ == "__main__":
    main()
