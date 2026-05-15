#!/usr/bin/env python3
"""
telegram_bot.py — CocoBet Telegram Pick Publisher

Liest picks_output.json + prematch-data.json und postet täglich:
  - 🎯 PICK       → Einzelne Picks mit positivem Edge (conf=high, ep≥4pp, echte Odds)
  - 👀 IM BLICK   → Letzte-Runde-Spiele gruppiert nach Liga, ohne bestätigten Pick
  - 📊 RECAP      → Abends: gestrige Ergebnisse aus picks_history.json

Umgebungsvariablen:
  TELEGRAM_TOKEN     — Bot-Token von @BotFather
  TELEGRAM_CHAT_ID   — Channel-ID
  TG_MODE            — 'picks' | 'watch' | 'recap' | 'all' (Standard: 'all')
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, date, timedelta
from collections import defaultdict

# ── Konfiguration ─────────────────────────────────────────────────────────────
TELEGRAM_TOKEN        = os.environ.get('TELEGRAM_TOKEN', '')
CHAT_ID               = os.environ.get('TELEGRAM_CHAT_ID', '-1003819239615')
TG_MODE               = os.environ.get('TG_MODE', 'all')
SENT_LOG              = 'telegram_sent.json'

MIN_EDGE_PP           = 4.0   # Mindest-Edge für PICK-Post
MIN_MATCH_SCORE_WATCH = 6.0   # Mindest-Score für IM BLICK
MAX_ROUNDS_LEFT_WATCH = 1     # Nur letzte Runde(n) für IM BLICK
MIN_CONF_PICK         = 'high'

STAKE_MITTEL_PP       = 7.0
STAKE_KLEIN_PP        = 4.0

LEAGUE_ORDER = [
    'ENG', 'ESP', 'GER', 'ITA', 'FRA', 'NED', 'POR',
    'TUR', 'SCO', 'GER2', 'ENG2', 'HUN', 'POL', 'CRO', 'SUI', 'BEL',
]

# ── Telegram API ───────────────────────────────────────────────────────────────
def tg_send(text: str) -> bool:
    if not TELEGRAM_TOKEN:
        print('⚠️  Kein TELEGRAM_TOKEN — Vorschau:')
        print(text)
        print()
        return True   # im Testmodus als Erfolg werten
    url  = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    body = json.dumps({
        'chat_id':    CHAT_ID,
        'text':       text,
        'parse_mode': 'HTML',
    }).encode('utf-8')
    req = urllib.request.Request(
        url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get('ok', False)
    except urllib.error.HTTPError as e:
        print(f'❌ Telegram HTTP {e.code}: {e.read().decode()[:200]}')
        return False
    except Exception as e:
        print(f'❌ Telegram Fehler: {e}')
        return False


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def edge_pp(odds: float, model_odds: float) -> float:
    if not odds or not model_odds or model_odds <= 0 or odds <= 0:
        return 0.0
    return round((1.0 / model_odds - 1.0 / odds) * 100, 1)


def stake_label(ep: float) -> str:
    if ep >= STAKE_MITTEL_PP:
        return '🟡 Mittel'
    if ep >= STAKE_KLEIN_PP:
        return '🟢 Klein'
    return '⬜ Minimal'


def market_icon(market_key: str) -> str:
    k = market_key.lower()
    if 'corners' in k or 'ecken' in k: return '🚩'
    if 'btts' in k or 'beide' in k:    return '⚽'
    if 'over' in k or 'tore' in k:     return '⚽'
    if 'under' in k or 'unter' in k:   return '⚽'
    if 'dc' in k or 'doppelte' in k:   return '🎯'
    if 'homewin' in k:                  return '🏠'
    if 'awaywin' in k:                  return '✈️'
    if 'draw' in k:                     return '🤝'
    return '📌'


def fmt_time(pm_fx: dict | None) -> str:
    if not pm_fx: return ''
    t = pm_fx.get('time', '')
    return t[:5] if t else ''


def build_pm_index(pm_fxs: list) -> dict:
    idx = {}
    for fx in pm_fxs:
        h = fx.get('homeTeamName', '')
        a = fx.get('awayTeamName', '')
        if h and a:
            idx[f'{h}|{a}'] = fx
    return idx


def importance_emoji(score: float) -> str:
    if score >= 10: return '🚨'
    if score >= 8.5: return '🔥'
    if score >= 7:   return '⚽'
    return '▪️'


# ── Pick-Selektion ────────────────────────────────────────────────────────────
def best_pick(fx: dict) -> dict | None:
    """Bester Pick: conf=high, echte Odds, edge ≥ MIN_EDGE_PP."""
    best, best_ep = None, 0.0
    for p in fx.get('picks', []):
        if p.get('conf') != MIN_CONF_PICK: continue
        if p.get('oddsIsEst', False): continue
        odds = p.get('odds')
        if not odds: continue
        ep = edge_pp(odds, p.get('modelOdds', 0))
        if ep >= MIN_EDGE_PP and ep > best_ep:
            best, best_ep = p, ep
    return best


def is_watch_game(fx: dict) -> bool:
    return (fx.get('roundsLeft', 99) <= MAX_ROUNDS_LEFT_WATCH
            and fx.get('matchScore', 0) >= MIN_MATCH_SCORE_WATCH)


# ── Pick-Beschreibung ─────────────────────────────────────────────────────────
def pick_description(pick: dict, fx: dict, pm_fx: dict | None) -> str:
    market = pick.get('market', '')
    mk     = pick.get('marketKey', '').lower()
    home   = fx.get('home', '')
    away   = fx.get('away', '')
    ep     = edge_pp(pick.get('odds', 0), pick.get('modelOdds', 0))

    h2h_avg = None
    if pm_fx:
        h2h = pm_fx.get('h2h', {})
        if isinstance(h2h, dict):
            g = h2h.get('avgGoals') or h2h.get('avg_goals')
            if g: h2h_avg = round(float(g), 1)

    if 'over' in mk and 'ecken' not in mk:
        line = market.replace('Over ', '').replace(' Tore', '').strip()
        if h2h_avg and h2h_avg > float(line.split()[0]) if line[0].isdigit() else True:
            return f'H2H-Schnitt Ø {h2h_avg} Tore — historisch torreich. Modell sieht über {line} Tore.'
        return f'Beide Defensiven anfällig. Modell erwartet über {line} Tore.'
    if 'under' in mk and 'ecken' not in mk:
        return f'Defensiv solide auf beiden Seiten. Modell sieht wenig Tore.'
    if 'btts' in mk and 'nein' not in market.lower():
        return f'Beide Teams treffen regelmäßig — BTTS Wahrscheinlichkeit hoch.'
    if 'btts' in mk and 'nein' in market.lower():
        return f'Mindestens ein Team trifft selten — BTTS Nein als Defensivtipp.'
    if 'dc' in mk or 'doppelte' in market.lower():
        fav = home if '1x' in mk else away
        return f'{fav} oder Remis genügt — zwei Gewinnergebnisse abgesichert.'
    if 'homewin' in mk:
        return f'{home} als Favorit im Heimspiel. Modell sieht klaren Heimvorteil.'
    if 'awaywin' in mk:
        return f'{away} mit starker Auswärtsform. Modell sieht Auswärtssieg-Vorteil.'
    return f'Modell-Edge +{ep:.0f}pp gegenüber Bookie.'


# ── Nachrichtenformate ────────────────────────────────────────────────────────
def format_pick_post(fx: dict, pick: dict, pm_fx: dict | None) -> str:
    flag   = fx.get('leagueFlag', '')
    league = fx.get('leagueName', fx.get('league', ''))
    home   = fx.get('home', '')
    away   = fx.get('away', '')
    market = pick.get('market', '')
    odds   = pick.get('odds', 0)
    ep     = edge_pp(odds, pick.get('modelOdds', 0))
    icon   = market_icon(pick.get('marketKey', ''))
    sl     = stake_label(ep)
    desc   = pick_description(pick, fx, pm_fx)
    t      = fmt_time(pm_fx)
    time_s = f' · {t} Uhr' if t else ''

    return '\n'.join([
        f'🎯 <b>PICK</b> · {flag} {league}{time_s}',
        '',
        f'🏠 <b>{home}</b>',
        f'✈️ <b>{away}</b>',
        '',
        f'{icon} <b>{market} @ {odds}</b>',
        f'   Edge +{ep:.0f}pp · Stake: {sl}',
        '',
        desc,
        '',
        '#CocoBet',
    ])


def format_watch_league_post(league_code: str, games: list, pm_index: dict) -> str:
    """Ein Post pro Liga mit allen IM BLICK Spielen der Liga."""
    # Metadaten aus erstem Spiel
    first = games[0]
    flag   = first.get('leagueFlag', '')
    league = first.get('leagueName', first.get('league', league_code))
    rl     = first.get('roundsLeft', 1)

    # Situation
    if rl == 1:
        situation = '🚨 <b>Letzter Spieltag der Saison</b>'
    else:
        situation = f'🔥 <b>Noch {rl} Runden</b>'

    # Kickoff-Zeiten sammeln
    times = {}
    for g in games:
        pm = pm_index.get(f"{g['home']}|{g['away']}")
        t  = fmt_time(pm)
        times[f"{g['home']}|{g['away']}"] = t

    # Alle Kickoffs gleich?
    unique_times = set(v for v in times.values() if v)
    single_time  = list(unique_times)[0] if len(unique_times) == 1 else None
    time_header  = f' · {single_time} Uhr' if single_time else ''

    # Spiele sortiert nach matchScore absteigend
    sorted_games = sorted(games, key=lambda g: g.get('matchScore', 0), reverse=True)

    game_lines = []
    for g in sorted_games:
        emo    = importance_emoji(g.get('matchScore', 0))
        t      = times[f"{g['home']}|{g['away']}"]
        t_str  = f'<i>{t}</i>  ' if t and not single_time else ''
        game_lines.append(f'{emo} {t_str}{g["home"]} vs {g["away"]}')

    # Inplay-Hinweis
    avg_score = sum(g.get('matchScore', 0) for g in games) / len(games)
    if avg_score >= 9:
        hint = 'Hochspannung — wer zurückliegt muss kommen. Over/BTTS Live prüfen wenn ein Team pusht.'
    else:
        hint = 'Letzter Spieltag — Rückständige Teams drücken aufs Gas. Over/BTTS Live interessant.'

    lines = [
        f'👀 <b>IM BLICK</b> · {flag} {league}{time_header}',
        situation,
        '',
    ] + game_lines + [
        '',
        f'⚡ {hint}',
        '',
        '#CocoBet',
    ]
    return '\n'.join(lines)


def format_recap_post(yesterday_entries: list) -> str:
    """Tagesrückblick aus picks_history.json."""
    yesterday = (date.today() - timedelta(days=1)).strftime('%d.%m.%Y')
    wins = losses = voids = 0
    lines = [f'📊 <b>Rückblick {yesterday}</b>', '']

    for entry in yesterday_entries:
        home  = entry.get('home', '')
        away  = entry.get('away', '')
        flag  = entry.get('leagueFlag', '')
        score = entry.get('finalScore', '')
        score_s = f' <i>({score})</i>' if score else ''

        # Besten Pick mit echten Odds + Ergebnis
        top_picks = [
            p for p in entry.get('picks', [])
            if p.get('result') in ('win', 'loss', 'void') and p.get('odds')
        ]
        if not top_picks:
            continue

        # Sortiert: win zuerst, dann nach odds
        top_picks.sort(key=lambda p: (p.get('result') != 'win', -(p.get('odds') or 0)))
        p = top_picks[0]

        result  = p.get('result', '')
        market  = p.get('market', '?')
        odds    = p.get('odds', '?')

        if result == 'win':
            icon = '✅'
            wins += 1
        elif result == 'loss':
            icon = '❌'
            losses += 1
        else:
            icon = '↩️'
            voids += 1

        lines.append(
            f'{icon} {flag} {home} vs {away}{score_s}\n'
            f'   {market} @ {odds}'
        )

    if wins + losses + voids == 0:
        return ''

    total = wins + losses
    pct   = round(wins / total * 100) if total > 0 else 0
    pct_s = f' · {pct}% Trefferquote' if total > 0 else ''

    lines += [
        '',
        f'<b>Bilanz: {wins}✅  {losses}❌' +
        (f'  {voids}↩️' if voids else '') +
        pct_s + '</b>',
        '',
        '#CocoBet',
    ]
    return '\n'.join(lines)


# ── Sent Log ──────────────────────────────────────────────────────────────────
def load_sent_log() -> dict:
    try:
        with open(SENT_LOG, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_sent_log(log: dict):
    with open(SENT_LOG, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def fkey(fx: dict, suffix: str) -> str:
    return f"{fx.get('dateIso')}|{fx.get('home')}|{fx.get('away')}|{suffix}"


def league_watch_key(league_code: str, date_iso: str) -> str:
    return f"{date_iso}|league_watch|{league_code}"


# ── Recap-Daten laden ─────────────────────────────────────────────────────────
def load_yesterday_entries() -> list:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    try:
        with open('picks_history.json', 'r', encoding='utf-8') as f:
            h = json.load(f)
        entries = h if isinstance(h, list) else h.get('picks', [])
    except Exception:
        return []
    return [
        e for e in entries
        if e.get('dateIso', '') == yesterday
        and e.get('resolved', False)
    ]


# ── Hauptprogramm ─────────────────────────────────────────────────────────────
def main():
    today_iso = date.today().isoformat()

    # picks_output.json laden
    try:
        with open('picks_output.json', 'r', encoding='utf-8') as f:
            raw = json.load(f)
        fixtures = raw if isinstance(raw, list) else raw.get('fixtures', [])
    except FileNotFoundError:
        print('⚠️  picks_output.json nicht gefunden')
        return
    except json.JSONDecodeError as e:
        print(f'❌ picks_output.json Fehler: {e}')
        return

    # prematch-data.json laden (Uhrzeit + H2H)
    pm_index = {}
    try:
        with open('prematch-data.json', 'r', encoding='utf-8') as f:
            pm_raw = json.load(f)
        pm_fxs   = pm_raw if isinstance(pm_raw, list) else pm_raw.get('fixtures', [])
        pm_index = build_pm_index(pm_fxs)
    except Exception as e:
        print(f'⚠️  prematch-data.json: {e}')

    sent_log = load_sent_log()

    # Heutige Fixtures filtern + sortieren
    today_fx = sorted(
        [fx for fx in fixtures
         if fx.get('dateIso') == today_iso and fx.get('roundsLeft', 99) < 99],
        key=lambda fx: (
            LEAGUE_ORDER.index(fx.get('league', ''))
            if fx.get('league', '') in LEAGUE_ORDER else 99,
            fx.get('home', '')
        )
    )

    picks_count = watch_count = 0

    # ── 🎯 PICK Posts ─────────────────────────────────────────────────────────
    if TG_MODE in ('picks', 'all'):
        for fx in today_fx:
            k = fkey(fx, 'pick')
            if k in sent_log:
                continue
            pick = best_pick(fx)
            if not pick:
                continue
            pm_fx = pm_index.get(f"{fx['home']}|{fx['away']}")
            msg   = format_pick_post(fx, pick, pm_fx)
            if tg_send(msg):
                sent_log[k] = {'ts': datetime.now(timezone.utc).isoformat(), 'type': 'pick'}
                picks_count += 1
                ep = edge_pp(pick.get('odds', 0), pick.get('modelOdds', 0))
                print(f'✅ PICK: {fx["home"]} vs {fx["away"]} — {pick["market"]} +{ep:.0f}pp')

    # ── 👀 IM BLICK Posts (gruppiert nach Liga) ───────────────────────────────
    if TG_MODE in ('watch', 'all'):
        # Spiele ohne guten Pick sammeln
        watch_games = [
            fx for fx in today_fx
            if not best_pick(fx) and is_watch_game(fx)
        ]

        # Nach Liga gruppieren
        by_league: dict[str, list] = defaultdict(list)
        for fx in watch_games:
            by_league[fx.get('league', '?')].append(fx)

        # Ligen in definierter Reihenfolge posten
        for league_code in LEAGUE_ORDER + [l for l in by_league if l not in LEAGUE_ORDER]:
            if league_code not in by_league:
                continue
            games = by_league[league_code]
            k     = league_watch_key(league_code, today_iso)
            if k in sent_log:
                continue
            msg = format_watch_league_post(league_code, games, pm_index)
            if tg_send(msg):
                sent_log[k] = {'ts': datetime.now(timezone.utc).isoformat(), 'type': 'watch',
                               'games': len(games)}
                watch_count += 1
                print(f'👀 IM BLICK: {league_code} — {len(games)} Spiele')

    # ── 📊 RECAP Post ─────────────────────────────────────────────────────────
    if TG_MODE in ('recap', 'all'):
        recap_key = f"recap|{(date.today() - timedelta(days=1)).isoformat()}"
        if recap_key not in sent_log:
            entries = load_yesterday_entries()
            if entries:
                msg = format_recap_post(entries)
                if msg and tg_send(msg):
                    sent_log[recap_key] = {
                        'ts': datetime.now(timezone.utc).isoformat(), 'type': 'recap'}
                    print(f'📊 RECAP: {len(entries)} gestrige Fixtures')
            else:
                print('ℹ️  Keine gestrigen aufgelösten Picks für Recap')

    save_sent_log(sent_log)
    print(f'\n📤 Fertig: {picks_count} Picks · {watch_count} Watch-Liga-Posts')


if __name__ == '__main__':
    main()
