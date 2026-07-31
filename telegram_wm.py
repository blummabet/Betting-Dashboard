#!/usr/bin/env python3
"""
telegram_wm.py — CocoBet WM 2026 Telegram Publisher

Postet täglich eine Morning-Card mit den WM-Picks für heute.
Läuft als GitHub Action jeden Morgen (ab 1. Juni 2026).

Format:
  🌍 WM 2026 — Heute · N Spiele
  ━━ GRUPPE X · SPIELTAG N ━━
  🔥 UPSET ALERT (wenn Elo-Gap klein)
  🏠 Team A vs 🌍 Team B · Zeit · Venue
  🎯 BET: Markt @Odds → +Xpp Edge | Modell: Y% vs. Markt: Z%
  ⚖️ ABWÄGEN: Markt @Odds (+Xpp)
  📈 WM-Bilanz: W-L-P | ROI: X%

Umgebungsvariablen:
  TELEGRAM_TOKEN     — Bot-Token
  TELEGRAM_CHAT_ID   — Channel-ID (Standard: CocoBet)
  TG_WM_MODE         — 'morning' | 'recap' | 'all' (Standard: 'morning')
"""

import json
from tg_safe import safe_flag
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
CHAT_ID        = (os.environ.get("TELEGRAM_CHAT_ID") or "-1003819239615").strip()
TG_WM_MODE     = os.environ.get("TG_WM_MODE", "morning")

# 01.07.2026 (Lucas: „Content für MLS/Liga"): dataset-aware. WM_FILE = aktives Daten-File; LOG_FILE
# per Dataset (WM = telegram-log.json unverändert, mls/liga eigenes Log → keine Kreuz-Kontamination).
import cocobet_dataset as D  # noqa: E402
import telegram_i18n as I18N  # noqa: E402  (04.07.2026, Lucas: DE+EN Public-Picks)

# Public-Sprachen: erst DE, dann EN (beide in denselben Channel). Via env override-bar.
TG_LANGS = [s.strip() for s in os.environ.get("TG_LANGS", "de,en").split(",") if s.strip()]
# (31.07.2026, Lucas) Öffentliche Bilanz erst ab belastbarer Stichprobe zeigen (sonst -24% aus 8 Picks im Public).
RECORD_MIN_N = int(os.environ.get("RECORD_MIN_N") or 20)
WM_FILE        = str(D.data_file())
LOG_FILE       = str(D.file("telegram-log.json", "liga-telegram-log.json"))

# ── Refactor 2026-06-06: Konstanten aus cocobet_config.json (Profile-aware) ──
try:
    from cocobet_config import CONFIG as _CFG
except Exception:
    _CFG = {}

def _cfg(section: str, key: str, default):
    if isinstance(_CFG, dict):
        return _CFG.get(section, {}).get(key, default)
    return default

# Minimaler Edge (Alt-Schwellen, NICHT mehr Gate fürs Posting — siehe unten).
MIN_BET_EDGE   = _cfg("telegram", "min_bet_edge_pp", 4)   # pp
MIN_ABW_EDGE   = _cfg("telegram", "min_abw_edge_pp", 4)   # pp
# 17.06.2026 (Lucas, „Zwei-Flächen"-Konzept): Card-Posting ist NICHT edge-getrieben.
# Ein bestätigter Steam-Move hat am Spieltag edgePP ~0/negativ BY DESIGN — der Wert
# steckt in der Drop-Bestätigung durch Signale, nicht im Preis. Daher gilt:
#   BET posten  = verdict == "BET" (Conviction-Schwelle steckt schon im Verdict).
#   ABWÄGEN     = Conviction-Floor statt Edge-Floor.
# Der alte edgePP≥4-Gate killte genau die bestätigten BETs (z.B. ENG-CRO BET/Conv 7
# mit edge −4 → „heute kein BET"). [[feedback_two_surfaces_concept]].
MIN_ABW_CONVICTION = _cfg("telegram", "min_abw_conviction", 4)   # 0-10


# ── Tages-Dedup (Audit-Fix 06.06.2026) ────────────────────────────────────────
# Verhindert dass Morning/Recap-Cards mehrfach pro Tag verschickt werden,
# wenn der Workflow 5×/Tag triggert.
# Dedizierter Dedup-State — NUR von telegram_wm geschrieben.
# FIX 11.06.2026: Vorher las der Dedup telegram-log.json, das aber von ZWEI
# Workflows (fetch-wm-data + daily-wm-story) committet wird. Der `-X ours`-Merge
# beim Push clobberte den morning_card-Marker → Dedup sah nichts → Morning-Card
# wurde bei jedem Lauf erneut gesendet (Spam). Eigene Single-Writer-Datei behebt das.
# 13.07.2026 (MLS-Audit) — STILLER UNTERDRÜCKER. SENT_STATE hing hart auf wm_telegram_sent.json,
# und der Dedup-Key ist `f"{type_}:{datum}"` — OHNE Datensatz. Hatte die WM an einem Tag ihre
# Morning-Card gesendet, galt derselbe Marker auch für MLS und Liga: deren Digest wurde für dieses
# Datum still verworfen. Kein Fehler im Log, einfach keine Nachricht. Gehört in dieselbe Familie wie
# der „stille Telegram-Send"-Bug (leeres CHAT_ID-Secret).
# Jetzt eigene Datei je Datensatz → jeder Datensatz hat seinen eigenen Tages-Marker.
SENT_STATE = str(D.file("wm_telegram_sent.json", "liga_telegram_sent.json"))


def _already_sent_today(type_: str, target_date: str) -> bool:
    """True wenn type_ heute schon für target_date gesendet wurde."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{type_}:{target_date}"
    # 1) Dedizierter State (robust, Single-Writer)
    try:
        if os.path.exists(SENT_STATE):
            with open(SENT_STATE, encoding="utf-8") as f:
                st = json.load(f)
            if str(st.get(key, ""))[:10] == today_str:
                return True
    except Exception:
        pass
    # 2) Fallback: telegram-log.json (Altzustände)
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, encoding="utf-8") as f:
                log = json.load(f)
            if isinstance(log, list):
                for entry in reversed(log):
                    if entry.get("type") != type_:
                        continue
                    if (entry.get("sentAt") or "")[:10] == today_str and (entry.get("date") or "") == target_date:
                        return True
    except Exception:
        pass
    return False


def _mark_sent(type_: str, target_date: str) -> None:
    """Schreibt den Dedup-Marker in den dedizierten State (überlebt Merges)."""
    try:
        st = {}
        if os.path.exists(SENT_STATE):
            with open(SENT_STATE, encoding="utf-8") as f:
                st = json.load(f)
        if not isinstance(st, dict):
            st = {}
        st[f"{type_}:{target_date}"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(SENT_STATE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  ⚠️  Dedup-State schreiben fehlgeschlagen: {e}")


# ── Telegram API ───────────────────────────────────────────────────────────────
def _log_send(type_: str, preview: str, meta: dict = None):
    """Append a send event to telegram-log.json (max 200 entries)."""
    try:
        existing = []
        if os.path.exists(LOG_FILE):
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


def tg_send(text: str) -> bool:
    if not TELEGRAM_TOKEN:
        print("⚠️  Kein TELEGRAM_TOKEN — Vorschau:")
        print(text)
        print()
        return True  # Preview-Modus gilt als OK
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id":    CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("ok", False)
    except urllib.error.HTTPError as e:
        print(f"❌ Telegram HTTP {e.code}: {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"❌ Telegram Fehler: {e}")
        return False


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────
def pct(odds: float | None) -> str:
    """Odds → implied probability als String '42%'."""
    if not odds or odds <= 0:
        return "?"
    return f"{round(100 / odds)}%"

def model_pct(model_odds: float | None) -> str:
    """Modell-Odds → Wahrscheinlichkeit als String."""
    if not model_odds or model_odds <= 0:
        return "?"
    return f"{round(100 / model_odds)}%"

def upset_label(score: int, lang: str = "de") -> str:
    return I18N.upset_label(score, lang)

def short_venue(venue: str) -> str:
    """Kürzt Venue auf max 35 Zeichen."""
    if not venue: return ""
    # Nur Stadion-Name ohne Stadt (nach dem letzten Komma)
    if "," in venue:
        parts = [p.strip() for p in venue.split(",")]
        # Zeige: "Estadio Azteca · Mexico City"
        if len(parts) >= 2:
            return f"{parts[0]} · {parts[-1]}"
    return venue[:35]

# FIX 12.06.2026: resolve_wm_picks schreibt UPPERCASE WIN/LOSS/VOID — Recap/Bilanz
# vergleichen aber lowercase → normalisieren. + Conviction-Stake: BET höher als
# ABWÄGEN (flat verzerrte die Bilanz, da viele schwächere ABWÄGEN). Poly bleibt flat.
def _norm_result(r):
    if not r:
        return r
    u = str(r).upper()
    return {"WIN": "won", "LOSS": "lost", "VOID": "push", "PUSH": "push"}.get(u, str(r).lower())


def _pick_stake(p) -> float:
    """Edge-Staking (28.06.2026): primär pick['stake'] (fraktionales Kelly, pick_staking.py).
    Fallback auf altes Flat (BET €10 / ABWÄGEN €5) nur für Alt-Picks ohne stake."""
    s = (p or {}).get("stake")
    if isinstance(s, (int, float)) and s > 0:
        return float(s)
    return 10.0 if (p or {}).get("verdict") == "BET" else 5.0


def _stake_str(p) -> str:
    """Einsatz-Chip für Card-Zeilen (07.07.2026, Lucas): der Recap zeigt €-Beträge, die
    Picks bisher nicht → Inkonsistenz. Zeigt den Edge-Stake (fraktionales Kelly, pick_staking).
    Sprach-agnostisch (€X gleich in DE/EN). Ganze € ohne Nachkomma, sonst 1 Stelle."""
    v = _pick_stake(p)
    return f" · 💶 €{v:.0f}" if float(v).is_integer() else f" · 💶 €{v:.1f}"


def _is_posted(p) -> bool:
    """Zeigt/wertet Telegram diesen Pick? EXAKT dieselbe Auswahl wie die Dashboard-Card
    (wm2026-renderer._livePicks): BET/ABWÄGEN, nicht trackingExcluded, nicht boldAlt (Safer-Line-
    Alternative wird inline gezeigt, kein eigener Pick). KEIN Conviction-Floor — die Card hat auch
    keinen. (07.07.2026, Lucas: „posten alles auf Telegram was auch in der Card ist" → Morning-Card,
    Recap und kumulative Bilanz nutzen dieselbe Auswahl → nie mehr „gewertet aber nicht gepostet".)"""
    if not p or p.get("trackingExcluded") or p.get("boldAlt"):
        return False
    return p.get("verdict") in ("BET", "ABWÄGEN")


def bilanz_footer(wm: dict, lang: str = "de") -> str:
    """Berechnet WM P&L aus recorded results (conviction-gewichtet, case-robust). Nur GEPOSTETE
    Picks (dieselbe Auswahl wie die Morning-Card) — sonst zählen nie gesendete Low-Conviction-
    ABWÄGEN in die öffentliche Bilanz."""
    picks_all = wm.get("picks", {})
    w = l = push = 0
    pnl = 0.0
    staked = 0.0
    for pick_list in picks_all.values():
        for p in pick_list:
            # (31.07.2026, Lucas) Public-Track-Record wertet NUR BET. Abwägen wird im Push angezeigt,
            # zählt aber nicht in die öffentliche Bilanz (auf dem Dashboard bleibt es voll getrackt).
            if not _is_posted(p) or p.get("verdict") != "BET":
                continue
            r = _norm_result(p.get("result"))
            stake = _pick_stake(p)
            fac = p.get("resultStakeFactor", 1.0)  # 0.5 bei AH-Viertel-Halb-Ergebnis
            if r == "won":
                w += 1
                staked += stake
                pnl += (p.get("odds", 1) - 1) * stake * fac
            elif r == "lost":
                l += 1
                staked += stake
                pnl -= stake * fac
            elif r == "push":
                push += 1
                staked += stake
    total = w + l + push
    # (31.07.2026, Lucas) Bilanz im Public erst ab belastbarer Stichprobe — ein -24% aus 8 Picks
    # untergräbt genau das Vertrauen, das der Channel aufbauen soll. Unter der Schwelle: keine Zeile.
    if total < RECORD_MIN_N:
        return ""
    roi = (pnl / staked * 100) if staked > 0 else 0
    pnl_str = f"+€{pnl:.2f}" if pnl >= 0 else f"-€{abs(pnl):.2f}"
    roi_str = f"+{roi:.1f}%" if roi >= 0 else f"{roi:.1f}%"
    # EN lässt das €-P&L weg (Währung passt für internationales Publikum nicht — ROI reicht).
    return I18N.L[lang]["record"].format(rec=I18N.comp_record(lang), w=w, l=l, p=push, roi=roi_str, pnl=pnl_str)


# ── Morning Card ───────────────────────────────────────────────────────────────
def _pick_intro(hero: dict | None, home_name: str, away_name: str, fav: str | None) -> str | None:
    """Pick-KONSISTENTE 1-Satz-Einleitung (FIX 13.06.2026).
    Vorher zeigte die Karte eine generische Favoriten-Vorschau (rohe Form-Tore),
    die den Picks widersprach — z.B. „Brasilien offensivstärker" über einem Unter-/
    Marokko-Handicap-Pick. Verwirrte Leser. Diese Einleitung richtet sich nach dem
    HAUPT-Pick: was wird tatsächlich bespielt + auf welcher Seite."""
    if not hero:
        return None
    m  = (hero.get("market", "") or "").lower()
    mk = hero.get("market", "")
    favc = f"{fav} ist favorisiert, aber " if fav else ""
    # Tor-Märkte (richtungs-unabhängig vom Team)
    if "unter" in m or "under" in m:
        return f"{favc}das Modell erwartet ein enges, torarmes Spiel — Value auf <b>{mk}</b>."
    if "über" in m or "uber" in m or "over" in m:
        return f"Das Modell erwartet ein offenes, torreiches Spiel — Value auf <b>{mk}</b>."
    if "beide teams treffen" in m or "btts" in m:
        return f"Das Modell sieht Treffer auf beiden Seiten — Value auf <b>{mk}</b>."
    # Team-Märkte: welche Seite stützt der Pick?
    backs = None
    if any(t in m for t in ("heimsieg", "ah heim", "dnb: heim", "dnb: heimteam")) or "1x" in m:
        backs = home_name
    elif any(t in m for t in ("auswärtssieg", "auswaertssieg", "ah auswärt", "ah auswarts",
                              "dnb: auswärt", "dnb: auswärtsteam")) or "x2" in m:
        backs = away_name
    if backs:
        if fav and backs != fav:
            return f"{favc}{backs} wird vom Markt unterschätzt — Value auf die Außenseiter-Seite <b>{mk}</b>."
        return f"{backs} setzt sich laut Modell durch — Value auf <b>{mk}</b>."
    return None


def build_morning_card(wm: dict, target_date: str, lang: str = "de") -> str | None:
    """Baut die Morning-Card für alle WM-Spiele am target_date. lang='de' unverändert, 'en' übersetzt."""
    T = I18N.L[lang]

    groups      = wm.get("groups", {})
    all_picks   = wm.get("picks", {})
    upset_scores = wm.get("upsetScores", {})
    ai_previews  = wm.get("aiPreviews", {})

    # Spiele der „Fußball-Nacht" per Anpfiff-Zeitfenster sammeln (FIX 13.06.2026).
    # Vorher: fx.date == target_date (Kalendertag) → späte Nacht-Spiele (4/6 Uhr Wien =
    # 02-04 UTC des Folgetags) rollten ins nächste Datum und fehlten in der Karte
    # (z.B. AUS-TUR 06:00), obwohl sie noch zur heutigen Slate gehören. Jetzt: Anpfiff
    # in [target_date 08:00 UTC, +1 Tag 08:00 UTC) — deckt 21:00 bis ~06:00 Wien ab,
    # ohne die nächste Nacht zu doppeln. Fallback auf fx.date wenn kein kickoff.
    try:
        _win_start = datetime.fromisoformat(target_date + "T08:00:00+00:00")
        _win_end   = _win_start + timedelta(days=1)
    except Exception:
        _win_start = _win_end = None

    def _in_slate(fx) -> bool:
        ko = fx.get("kickoff")
        if ko and _win_start:
            try:
                dt = datetime.fromisoformat(ko.replace("Z", "+00:00")).astimezone(timezone.utc)
                return _win_start <= dt < _win_end
            except Exception:
                pass
        return fx.get("date") == target_date   # Fallback ohne kickoff

    matches_today = []
    for gkey, gdata in groups.items():
        teams_map = {t["id"]: t for t in gdata.get("teams", [])}
        for fx in gdata.get("fixtures", []):
            if _in_slate(fx):
                pick_key = f"{gkey}-{fx['matchday']}-{fx['home']}-{fx['away']}"
                home_t   = teams_map.get(fx["home"], {})
                away_t   = teams_map.get(fx["away"], {})
                matches_today.append({
                    "group":      gkey,
                    "matchday":   fx["matchday"],
                    "time":       fx.get("time", ""),
                    "kickoff":    fx.get("kickoff", ""),
                    "venue":      fx.get("venue", ""),
                    "home":       fx["home"],
                    "away":       fx["away"],
                    "homeName":   home_t.get("name", fx["home"]),
                    "awayName":   away_t.get("name", fx["away"]),
                    "homeFlag":   home_t.get("flag", "🏳"),
                    "awayFlag":   away_t.get("flag", "🏳"),
                    "homeElo":    home_t.get("elo"),
                    "awayElo":    away_t.get("elo"),
                    "picks":      all_picks.get(pick_key, []),
                    "pick_key":   pick_key,
                    "upsetScore": upset_scores.get(pick_key, 0),
                    "aiSnippet":  ai_previews.get(pick_key, {}).get("tgSnippet"),
                })

    # KO-Fixtures (28.06.2026, Lucas: KO-Picks wurden NIE in Telegram gepostet — nur Gruppen).
    # Gleiche Slate-Logik (_in_slate). Teams aus allen Gruppen sammeln (KO-Fixtures haben nur IDs).
    _all_teams = {}
    for gdata in groups.values():
        for t in gdata.get("teams", []):
            _all_teams[t["id"]] = t
    _KO_LABELS = {"R32": "Sechzehntelfinale", "R16": "Achtelfinale", "QF": "Viertelfinale",
                  "SF": "Halbfinale", "F": "Finale", "3P": "Spiel um Platz 3"}
    for kf in (wm.get("koFixtures") or []):
        if not kf.get("bothResolved") or not _in_slate(kf):
            continue
        rnd = kf.get("round")
        pick_key = f"KO-{rnd}-{kf['home']}-{kf['away']}"
        home_t = _all_teams.get(kf["home"], {})
        away_t = _all_teams.get(kf["away"], {})
        matches_today.append({
            "group": "KO", "matchday": rnd, "isKO": True,
            "roundLabel": kf.get("roundLabel") or _KO_LABELS.get(rnd, "K.O.-Runde"),
            "time": kf.get("time", ""), "kickoff": kf.get("kickoff", ""),
            "venue": kf.get("venue", ""), "home": kf["home"], "away": kf["away"],
            "homeName": home_t.get("name", kf["home"]), "awayName": away_t.get("name", kf["away"]),
            "homeFlag": home_t.get("flag", "🏳"), "awayFlag": away_t.get("flag", "🏳"),
            "homeElo": home_t.get("elo"), "awayElo": away_t.get("elo"),
            "picks": all_picks.get(pick_key, []), "pick_key": pick_key,
            "upsetScore": upset_scores.get(pick_key, 0),
            "aiSnippet": ai_previews.get(pick_key, {}).get("tgSnippet"),
        })

    if not matches_today:
        return None  # Keine Spiele heute

    # Sortierung + Anzeige-Zeit aus echtem kickoff (UTC → Wien CEST UTC+2).
    # FIX 11.06.2026: fx.time ist unzuverlässig (mal Wien, mal Venue-Local —
    # BRA-MAR "18:00" = NY statt 00:00 Wien, KOR-CZE 00:00-Platzhalter). kickoff
    # (Polymarket gamma startTime) ist die einzige verlässliche Quelle.
    # Fallback: alte HH:MM-Heuristik mit Mitternachts-Umbruch (00:00 = Nacht-Spiel).
    def _ko_key(t):
        try:
            h, m = map(int, (t or "").split(":")); mins = h * 60 + m
            return mins + 1440 if mins < 360 else mins
        except Exception:
            return 9999
    def _ko_dt(ko):
        try:
            return datetime.fromisoformat((ko or "").replace("Z", "+00:00"))
        except Exception:
            return None
    try:
        _day_base = datetime.fromisoformat(target_date + "T00:00:00+00:00").timestamp()
    except Exception:
        _day_base = 0
    for _m in matches_today:
        _dt = _ko_dt(_m.get("kickoff"))
        if _dt is not None:
            _m["_sort"]    = _dt.timestamp()
            _m["dispTime"] = (_dt + timedelta(hours=2)).strftime("%H:%M")  # Wien (CEST)
        else:
            _m["_sort"]    = _day_base + _ko_key(_m.get("time")) * 60
            _m["dispTime"] = _m.get("time", "")
    matches_today.sort(key=lambda x: x["_sort"])

    # Header
    bet_count = sum(
        1 for m in matches_today
        for p in m["picks"] if p.get("verdict") == "BET"
        and not p.get("trackingExcluded")
    )
    _np = T["morning_n_plural"] if len(matches_today) != 1 else ""
    lines = [T["morning_head"].format(n=len(matches_today), p=_np, comp=I18N.comp(lang))]
    if bet_count > 0:
        lines.append(T["bets_line"].format(n=bet_count, p=("s" if bet_count != 1 else "")))
    else:
        lines.append(T["no_bet"])

    for m in matches_today:
        # FIX 11.06.2026: trackingExcluded raus (Cross-Market-Konflikte). Der Dashboard-
        # Renderer filtert das seit 06.06., der Telegram-Sender hat es nie getan →
        # widersprüchliche Picks (z.B. Auswärtssieg + AH Heim −0.5) landeten im Card.
        # 07.07.2026 (Lucas): SELBE Auswahl wie die Dashboard-Card (_is_posted) — kein Conviction-
        # Floor mehr, boldAlt raus. Telegram zeigt exakt was die Card zeigt → Recap/Bilanz konsistent.
        bet_picks = [p for p in m["picks"] if p.get("verdict") == "BET" and _is_posted(p)]
        abw_picks = [p for p in m["picks"] if p.get("verdict") == "ABWÄGEN" and _is_posted(p)]

        # Spiel-Block
        us = m["upsetScore"]
        if m.get("isKO"):
            lines.append(f"━━ 🏆 {I18N.round_label(m.get('roundLabel', 'K.O.-Runde'), lang)} ━━")
        else:
            lines.append(T["group_head"].format(g=I18N.group_label(m['group'], lang), md=m['matchday']))

        if us >= 6:
            lines.append(f"{upset_label(us, lang)}")   # ohne Elo-Gap-Zahl (21.06.2026, Lucas)

        _hn = I18N.team_name(m.get("home"), m["homeName"], lang)
        _an = I18N.team_name(m.get("away"), m["awayName"], lang)
        lines.append(f"{safe_flag(m['homeFlag'])} <b>{_hn}</b> vs {safe_flag(m['awayFlag'])} <b>{_an}</b>")
        venue_str = short_venue(m["venue"])
        _uhr = " Uhr" if lang == "de" else ""
        lines.append(f"📅 {m['dispTime']}{_uhr}{' · ' + venue_str if venue_str else ''}")

        # KEIN roher Elo-Block mehr (21.06.2026, Lucas: „das ganze Elo-Ding ist nicht
        # notwendig"). Der Favorit fließt nur intern in die pick-konsistente Einleitung.
        _hero = (bet_picks or abw_picks or [None])[0]
        _fav = None
        if m["homeElo"] and m["awayElo"]:
            _fav = m["homeName"] if m["homeElo"] >= m["awayElo"] else m["awayName"]

        # Content (21.06.2026, reicher): ZWEI Zeilen — erst das Elo-freie Szene-Snippet
        # (Kontext/Stimmung), dann die pick-KONSISTENTE Pick-Zeile. Das Snippet macht keine
        # Richtungs-Wette mehr (Generator pick-aware) → kein Widerspruch zur Pick-Zeile.
        # DE: AI-Szene-Snippet (deutsch) + pick-konsistentes Intro. EN: Szene weglassen (deutscher
        # AI-Text), nur das übersetzte Intro (Szene-Snippet-Übersetzung ist Phase 2).
        _fav_disp = I18N.team_name(m.get("home") if _fav == m["homeName"] else m.get("away"),
                                   _fav, lang) if _fav else None
        if lang == "de":
            _scene = m.get("aiSnippet")
            _intro = _pick_intro(_hero, m["homeName"], m["awayName"], _fav)
            _first = True
            if _scene:
                lines.append(f"\n✦ <i>{_scene}</i>")
                _first = False
            if _intro:
                lines.append((f"\n✦ <i>{_intro}</i>" if _first else f"✦ <i>{_intro}</i>"))
        else:
            _intro = I18N.pick_intro_en(
                (_hero or {}).get("market", ""),
                I18N.market_label((_hero or {}).get("market", ""), lang),
                _hn, _an, _fav_disp) if _hero else None
            if _intro:
                lines.append(f"\n✦ <i>{_intro}</i>")

        if not bet_picks and not abw_picks:
            lines.append(T["no_edge"])
        else:
            # Narrative Engine-Signal-Beschreibungen (kein "+1.4pp"-Geblubber)
            SIG_NARRATIVE = I18N.sig_narrative(lang) or {
                "weather_signal":    "🌡 Wetter stützt",
                "travel_burden":     "✈ Reise belastet Gegner" ,
                "pressure_index":    "🎯 Tabellen-Druck",
                "form_trend":        "📈 Form passt",
                "xg_strength":       "🥅 xG-Stärke da",
                "h2h_pattern":       "🤝 H2H-Muster passt",
                "injury":            "🩹 Verletzungen helfen",
                "apif_predictions":  "📊 Externes Modell bestätigt",
                "lead_lag_bias":     "📡 Sharp-Lag (Bet365 hinterher)",
                "public_static_bias":"🎲 Public-Bias gegen Pick",
                "incentive_signal":  "🏆 Anreiz stützt",
                "lineup_signal":     "📋 Lineup bestätigt",
            }
            def _top_signals_narrative(p, n=2):
                """Top-N positiv-wirkende Engine-Signale, narrativ statt mit pp-Werten."""
                sigs = p.get("signals") or []
                sigs_sorted = sorted(sigs, key=lambda s: abs(s.get("score", 0)), reverse=True)
                out = []
                for s in sigs_sorted[:n]:
                    sc = s.get("score", 0)
                    if abs(sc) < 0.5: continue   # nur substantielle Signale
                    name = s.get("name", "")
                    if name not in SIG_NARRATIVE: continue
                    label = SIG_NARRATIVE[name]
                    # Bei Gegen-Signalen Negativ-Markierung (sprachabhängig)
                    if sc < 0:
                        if lang == "en":
                            label = re.sub(r" (helps|fits|backs it|confirms|agrees)$", " vs pick", label)
                        else:
                            label = label.replace(" stützt", " gegen Pick").replace(" passt", " gegen Pick")
                    out.append(label)
                return out

            # BET-Picks zuerst
            for p in bet_picks:
                edge = p.get("edgePP", "?")
                conv_score = p.get("convictionScore")

                # Header-Zeile: nur Markt + Quote + (optional) Conviction-Badge
                # Sprache neutralisiert (NEU 09.06.2026): keine X/10-Skala in der UI
                # — das klingt nach Stake-Speak ("8 Units") + erzeugt Halt-Stop-Gefühl.
                # Wort-Labels statt Score. Quantifizierung kommt über Signal-Count.
                # Public-Channel (12.06.2026): NUR positive Badges. Keine „Edge ohne
                # Bestätigung"-/„wenig Bestätigung"-Warnungen — die untergraben den
                # eigenen Pick und verwirren ("hää, wieso postet ihr das dann").
                conv_badge = ""
                if isinstance(conv_score, int):
                    if conv_score >= 8:
                        conv_badge = f" · <b>{T['top_pick']}</b>"
                    elif conv_score >= 6:
                        conv_badge = f" · {T['main_pick']}"

                _mkt = I18N.market_label(p['market'], lang)
                lines.append(
                    f"🟢 <b>{T['bet']}: {_mkt} @{p.get('odds', '?')}</b>{conv_badge}{_stake_str(p)}"
                )
                # Signal-Bestätigung NUR wenn welche stützen. KEIN fixer Nenner mehr
                # (21.06.2026, Lucas: „/14" war veraltet — wir haben 19 Signale, und nicht
                # jedes ist je Markt anwendbar). Echte Zahlen statt fragilem Hardcode.
                n_pos = p.get("signalCountPos") or 0
                n_neg = p.get("signalCountNeg") or 0
                if n_pos > 0:
                    _neg = T["signals_neg"].format(n=n_neg) if n_neg else ""
                    lines.append(T["signals_for"].format(n=n_pos, neg=_neg))

                # Sharp-Move als eigene Zeile mit narrativem Text
                if p.get("sharpMoveActive"):
                    sm = p.get("sharpMoveDetails") or {}
                    mv = sm.get("pinn_move_pp", 0)
                    days = sm.get("move_age_days")
                    if isinstance(mv, (int, float)) and abs(mv) >= 1:
                        direction = T["pinn_for"] if mv > 0 else T["pinn_against"]
                        age_note = ""
                        if days and days <= 3:
                            age_note = T["pinn_fresh"]
                        elif days and days > 14:
                            age_note = T["pinn_old"]
                        lines.append(T["pinn_line"].format(dir=direction, age=age_note))

                # Top-2 narrative Engine-Signale (kein pp-Zahlen-Salat)
                top_sigs = _top_signals_narrative(p, n=2)
                if top_sigs:
                    lines.append(f"   🧠 " + " · ".join(top_sigs))

                # Sicherere Alternative wenn vorhanden — knapp formuliert
                bold_alt = p.get("boldAlt")
                if bold_alt:
                    lines.append(T["safer"].format(
                        market=I18N.market_label(bold_alt.get('market'), lang),
                        odds=bold_alt.get('odds')))

            # ABWÄGEN-Picks — minimalistisch
            for p in abw_picks:
                edge = p.get("edgePP", "?")
                conv_score = p.get("convictionScore")
                n_pos = p.get("signalCountPos") or 0
                # Nur positive Badges (keine „wenig Bestätigung"-Warnung im Public-Channel).
                badges = []
                if isinstance(conv_score, int):
                    if conv_score >= 8:
                        badges.append(T["top_pick"])
                    elif conv_score >= 6:
                        badges.append(T["main_pick"])
                if n_pos > 0:
                    badges.append(f"{n_pos} {T['signals_short']}")
                if p.get("sharpMoveActive"):
                    badges.append("🔥")
                if p.get("synthetic"):
                    badges.append(T["insurance"])
                badge_str = "  " + " · ".join(badges) if badges else ""
                lines.append(
                    f"🟡 <b>{T['lean']}</b> {I18N.market_label(p['market'], lang)} @{p.get('odds', '?')}{badge_str}{_stake_str(p)}"
                )

        lines.append("")  # Leerzeile zwischen Spielen

    # Footer
    _bf = bilanz_footer(wm, lang)
    if _bf:
        lines.append(_bf)
    lines.append(T["footer"])

    return "\n".join(lines)


# ── Recap Card (nach Spieltag) ─────────────────────────────────────────────────
def build_recap_card(wm: dict, target_date: str, lang: str = "de") -> str | None:
    """Baut eine Recap-Card für Picks des gestrigen/angegebenen Datums. lang='de'|'en'."""
    T = I18N.L[lang]
    all_picks = wm.get("picks", {})
    groups    = wm.get("groups", {})

    # Fixture-Lookup für Datum
    fix_lookup: dict[str, dict] = {}
    for gkey, gdata in groups.items():
        teams_map = {t["id"]: t for t in gdata.get("teams", [])}
        for fx in gdata.get("fixtures", []):
            pk = f"{gkey}-{fx['matchday']}-{fx['home']}-{fx['away']}"
            if fx.get("date") == target_date:
                home_t = teams_map.get(fx["home"], {})
                away_t = teams_map.get(fx["away"], {})
                fix_lookup[pk] = {
                    "homeName": home_t.get("name", fx["home"]),
                    "awayName": away_t.get("name", fx["away"]),
                    "homeFlag": home_t.get("flag", "🏳"),
                    "awayFlag": away_t.get("flag", "🏳"),
                    "group":    gkey,
                    "matchday": fx["matchday"],
                }

    # KO-Fixtures auch im Recap (28.06.2026, Lucas: KO wurde nie gepostet). Teams aus allen Gruppen.
    _all_teams = {}
    for gdata in groups.values():
        for t in gdata.get("teams", []):
            _all_teams[t["id"]] = t
    for kf in (wm.get("koFixtures") or []):
        if not kf.get("bothResolved") or kf.get("date") != target_date:
            continue
        pk = f"KO-{kf.get('round')}-{kf['home']}-{kf['away']}"
        home_t = _all_teams.get(kf["home"], {})
        away_t = _all_teams.get(kf["away"], {})
        fix_lookup[pk] = {
            "homeName": home_t.get("name", kf["home"]), "awayName": away_t.get("name", kf["away"]),
            "homeFlag": home_t.get("flag", "🏳"), "awayFlag": away_t.get("flag", "🏳"),
            "group": "KO", "matchday": kf.get("round"),
        }

    if not fix_lookup:
        return None

    lines = [T["recap_head"].format(date=target_date, comp=I18N.comp(lang))]
    day_pnl = 0.0
    had_any = False

    for pick_key, fix_info in fix_lookup.items():
        fix_picks = all_picks.get(pick_key, [])
        pick_results = [(p, _norm_result(p.get("result"))) for p in fix_picks
                        if _is_posted(p) and p.get("verdict") == "BET" and p.get("result")]
        if not pick_results:
            continue
        had_any = True
        _pp = pick_key.split("-")
        _hid, _aid = (_pp[-2], _pp[-1]) if len(_pp) >= 2 else ("", "")
        _hn = I18N.team_name(_hid, fix_info['homeName'], lang)
        _an = I18N.team_name(_aid, fix_info['awayName'], lang)
        lines.append(f"{safe_flag(fix_info['homeFlag'])} {_hn} vs {safe_flag(fix_info['awayFlag'])} {_an}")
        for p, result in pick_results:
            stake = _pick_stake(p)   # BET €10 / ABWÄGEN €5
            fac = p.get("resultStakeFactor", 1.0)  # 0.5 bei AH-Viertel-Halb-Ergebnis
            _mkt = I18N.market_label(p['market'], lang)
            if result == "won":
                profit = (p.get("odds", 1) - 1) * stake * fac
                day_pnl += profit
                lines.append(f"  ✅ {_mkt} @{p.get('odds','?')} → +€{profit:.2f}")
            elif result == "lost":
                day_pnl -= stake * fac
                lines.append(f"  ❌ {_mkt} @{p.get('odds','?')} → -€{stake * fac:.2f}")
            elif result == "push":
                lines.append(f"  🔄 {_mkt} @{p.get('odds','?')} → {T['recap_push']}")
        lines.append("")

    if not had_any:
        return None

    pnl_str = f"+€{day_pnl:.2f}" if day_pnl >= 0 else f"-€{abs(day_pnl):.2f}"
    lines.append(T["recap_today"].format(pnl=pnl_str))
    _bf = bilanz_footer(wm, lang)
    if _bf:
        lines.append(_bf)
    lines.append(T["recap_footer"].format(comp=I18N.comp(lang)))

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("=== telegram_wm.py ===")

    try:
        with open(WM_FILE, encoding="utf-8") as f:
            wm = json.load(f)
    except FileNotFoundError:
        print(f"❌ {WM_FILE} nicht gefunden")
        return

    now = datetime.now(timezone.utc)
    today     = now.date().isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()

    mode = TG_WM_MODE.lower()

    if mode in ("morning", "all"):
        # AUDIT-Fix 06.06.2026: Tages-Dedup — Morning-Card max 1× pro Tag
        if _already_sent_today("morning_card", today):
            print(f"\n⛔ Morning Card für {today} heute schon gesendet — geskippt")
        else:
            print(f"\n📅 Morning Card für {today} ({', '.join(TG_LANGS)})…")
            # DE zuerst, dann EN (beide in denselben Public-Channel — 04.07.2026, Lucas).
            any_ok = False
            first_card = None
            for _lang in TG_LANGS:
                card = build_morning_card(wm, today, _lang)
                if not card:
                    continue
                first_card = first_card or card
                _ok = tg_send(card)
                any_ok = any_ok or _ok
                print(f"  [{_lang}] {'✅ Gesendet' if _ok else '❌ Fehler'}")
            if any_ok:
                    _log_send("morning_card", (first_card or "").split("\n")[0], {"date": today, "mode": mode})
                    _mark_sent("morning_card", today)
                    # Basis für die Intraday-„Neuer Pick"-Noti setzen (03.07.2026, Lucas):
                    # der Digest ist Erst-Ankündiger → alles Bekannte als announced markieren,
                    # lastDigestDate=heute. notify_new_picks meldet danach nur Nachzügler.
                    try:
                        import pick_announce_state as _S
                        _st = _S.load()
                        _S.mark(_st, _S.current_pick_ids(wm))
                        _st["lastDigestDate"] = today
                        _st["seeded"] = True
                        _S.save(_st)
                    except Exception as _e:
                        print(f"  ⚠️  Pick-Announce-Basis nicht gesetzt: {_e}")
            else:
                print(f"  ○ Keine WM-Spiele am {today}")

    if mode in ("recap", "all"):
        # AUDIT-Fix 06.06.2026: Tages-Dedup — Recap max 1× pro Tag
        if _already_sent_today("recap", yesterday):
            print(f"\n⛔ Recap für {yesterday} heute schon gesendet — geskippt")
        else:
            print(f"\n📊 Recap für {yesterday} ({', '.join(TG_LANGS)})…")
            any_ok = False
            first_card = None
            for _lang in TG_LANGS:
                card = build_recap_card(wm, yesterday, _lang)
                if not card:
                    continue
                first_card = first_card or card
                _ok = tg_send(card)
                any_ok = any_ok or _ok
                print(f"  [{_lang}] {'✅ Gesendet' if _ok else '❌ Fehler'}")
            if any_ok:
                _log_send("recap", (first_card or "").split("\n")[0], {"date": yesterday, "mode": mode})
                _mark_sent("recap", yesterday)
            else:
                print(f"  ○ Keine Picks mit Ergebnissen am {yesterday}")


if __name__ == "__main__":
    main()
