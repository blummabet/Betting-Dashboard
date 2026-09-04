#!/usr/bin/env python3
"""
betfair_alerts.py — Telegram-Pushes (Trades-Channel) für Betfair-Signale (29.07.2026, Lucas).

Testweise, 2 Szenarien (erweiterbar, sobald wir mehr gelernt haben):
  1. Halbzeit-Geld (30.07.2026 tier-aware, egal ob HZ-1X2 ODER Über/Unter 1,5 erste HZ): ein HZ-Markt
     hat ≥ Schwelle gematcht (Top/Int. 10K · Rest 5K) UND davon liegen ≥ HT_MIN_SHARE (85 %) auf EINEM
     Ausgang (sonst kein Signal, nur Liquidität). Es zählt der HZ-Markt mit dem meisten Geld.
  2. Frisches Geld: Zufluss auf dem GRÖSSTEN Zufluss-Markt (aus mkv) ≥ Schwelle (Top 30K / Rest 20K)
     — pro Markt, NICHT Spiel-Gesamt (sonst spiegelt die Zahl alle Märkte statt des einen Marktes).

Anti-Spam (Lucas: „einmal, dann nur bei deutlicher Steigerung"): pro Spiel+Szenario wird der
Wert beim letzten Push in betfair_alerts_seen.json gemerkt; erneut gepusht wird erst, wenn der
Wert um ≥ DEDUP_FACTOR (×1.5 = +50 %) gestiegen ist.

Läuft im betfair.yml-Workflow direkt nach dem Fetch (Mac-Runner, alle 15 Min).
Env: TELEGRAM_TOKEN + TELEGRAM_TRADES_CHAT_ID (privater Trades-Channel).
"""
from __future__ import annotations
import json
import os
import re
import html
import urllib.request
from datetime import datetime, timezone

from telegram_trades import send_trades_message

try:
    from betfair_direction import look as _dir_look
except Exception:   # Modul optional
    def _dir_look(direction, matchId, market, runner):
        return None

DIRECTION_FILE = "betfair_direction.json"   # 08.08.2026 (Lucas): Back/Lay-Richtung je Runner
CONSENSUS_FILE = "betfair_consensus.json"   # 09.08.2026 (Lucas): Zweitmeinung (Pinnacle/Soft/Poly) an den Trades-Frisch-Push
JUMP_REL = 0.40   # 08.08.2026 (Lucas, Viking-Fall 1.23->3.60 nach 1:1): springt die Quote zwischen zwei
                  # Scans um >= 40%, ist das fast sicher ein Spielereignis (Tor/Karte), KEIN Order-Flow.
                  # Ueber so einen Sprung ist die Back/Lay-Lesart nicht gueltig (der Sprung ist mechanisch,
                  # nicht von Backern/Layern) -> Richtung "unklar" statt eines falschen Back-/Lay-Urteils.
                  # Gilt in BEIDE Richtungen: ein Tor kann die Quote auch crashen und ein falsches "Back" faken.

HT_TOP_EUR     = float(os.environ.get("BF_HT_TOP_EUR") or 15000.0)   # Halbzeit-Geld-Schwelle Top-Liga + International (15.08.2026 Lucas: 10K->15K, Sa-Flut)
HT_REST_EUR    = float(os.environ.get("BF_HT_REST_EUR") or 10000.0)  # ... und Rest-Ligen (15.08.2026 Lucas: 5K->10K)
HT_MIN_SHARE   = 0.85     # ... und davon min. dieser Anteil auf EINEN Ausgang (einseitig)
# 21.08.2026 (Lucas): Fix-Verdacht-Push (⚫ schwarze Kugel). HZ-Geld dominiert den FT-Markt (HZ >= FT und
# >= Boden) = technisch unlogisch -> Fix-Muster. Eigene Maerkte-Sets fuer FT vs HT (wie im Radar).
FIX_HT_MIN_EUR = float(os.environ.get("BF_FIX_HT_MIN_EUR") or 2000.0)   # HZ-Geld-Boden Fix-Verdacht
FIX_RATIO_MIN  = float(os.environ.get("BF_FIX_RATIO_MIN") or 2.0)      # 22.08.2026 (Lucas): HZ muss FT KLAR dominieren (>=2x). 1.1x = nahezu ident = Rauschen.
FIX_LEAD_SHARE = float(os.environ.get("BF_FIX_LEAD_SHARE") or 0.65)    # 22.08.2026 (Lucas): der HZ-Markt muss klar EINSEITIG sein (>=65% auf einer Seite). 50/50-O/U ist Rauschen.
FIX_INPLAY_MAX_MIN = float(os.environ.get("BF_FIX_INPLAY_MAX_MIN") or 30.0)   # 23.08.2026 (Lucas, Admira „1 min später war Halbzeit"): HZ-Markt in-play nur bis Minute 30 — danach ist der HZ-Ausgang praktisch durch (Zeit entscheidet), spätes Geld auf's Sichere ist kein Fix-Signal.
FIX_LEAD_MIN_ODD = float(os.environ.get("BF_FIX_LEAD_MIN_ODD") or 1.15)       # 23.08.2026 (Lucas): die einseitig geladene Seite darf nicht schon quasi entschieden sein (@1.08 = 93 % = Naht-Lock) — dann ist es Geld auf's Offensichtliche, kein Fix-Verdacht.
FIX_FT_MARKETS = ("Match Odds", "Over/Under 2.5 Goals", "Over/Under 3.5 Goals", "Both teams to Score?")
FIX_HT_MARKETS = ("Half Time", "First Half Goals 0.5", "First Half Goals 1.5")
MIN_LEAD_ODD   = 1.30     # Geld auf einen Favoriten mit Quote < 1.30 (führt schon, wenig Value) = kein Push (Lucas 30.07.2026, vorher 1.15)
FRESH_TOP_EUR  = float(os.environ.get("BF_FRESH_TOP_EUR") or 50000.0)   # frisches Geld Top-Liga (15.08.2026 Lucas: 30K->50K)
FRESH_REST_EUR = float(os.environ.get("BF_FRESH_REST_EUR") or 35000.0)  # ... und Rest-Ligen (15.08.2026 Lucas: 20K->35K)
FRESH_LATE_MAX_MIN = float(os.environ.get("BF_FRESH_LATE_MAX_MIN") or 85.0)  # 23.08.2026 (Lucas: „schon beendet als Status"): In-Play-Moneyflow nur bis Minute 85 — danach (und bei finished) ist der Markt praktisch durch, spätes/reaktives Geld ist nicht mehr bespielbar.
# 31.07.2026 (Lucas) — kuratierte, HÖHERE Schwellen für den ÖFFENTLICHEN Channel (nur die wirklich
# dicken Bewegungen public, kein Spam). Halbzeit: Top 50K / Rest 15K gematcht. Frisch: Top 100K / Rest 30K.
PUB_HT_TOP     = 50000.0
PUB_HT_REST    = 15000.0
PUB_FRESH_TOP  = 100000.0
PUB_FRESH_REST = 30000.0
PUB_FRESH_MIN_SHARE = 0.80   # (Lucas 05.08.2026, verschaerft 09.08.2026: 0.70 -> 0.80) NUR Public: frisches Geld
                             # muss >=80% auf EINER Seite konzentriert sein. 70-79% ist bei mehrdeutigen/
                             # frisch-repricten Maerkten (z.B. nach Tor) zu gewagt fuer den oeffentlichen Kanal.
                             # Trades sieht weiter alles.
LEAD_PUSH_FACTOR = 1.75   # 08.08.2026 (Lucas): „Team fuehrt"-Geld flutet an starken Spieltagen (Sa-Nachmittag)
                          # den Push. Extra-Huerde NUR fuer Fuehrungs-Geld — es geht erst durch, wenn der Einsatz
                          # das LEAD_PUSH_FACTOR-Fache der normalen tier-Schwelle erreicht (skaliert pro Kanal:
                          # Trades an seinen, Public an seinen Schwellen). So faellt das reaktive Mitlaufen mit
                          # der Fuehrung raus, nur wirklich dicke Fuehrungs-Bewegungen bleiben. Back-Gate gilt weiter.
PUB_SEEN_FILE  = "betfair_public_seen.json"
PUB_LEDGER_FILE = "betfair_public_ledger.json"   # gesendete Public-Pushs fürs Tracking/Auswerten
DEDUP_FACTOR   = 1.5
SEEN_FILE      = "betfair_alerts_seen.json"

# 22.08.2026 (Lucas: „wieso kam die doppelt fuer HT?"): Der Dedup-State lag NUR im Repo. Im
# dauergepushten Repo kann betfair_alerts_seen.json einen Push verlieren (oder ein 1-Min-Folgelauf
# checkt vorher aus) -> prev=None -> Fix-Verdacht (Wert `ht_max` waechst nicht, ×1.5-Gate greift nie)
# feuert sofort erneut. Fix: Seen-State zusaetzlich LOKAL auf dem (immer selben) self-hosted Mac-Runner
# spiegeln; beim Laden Repo ∪ Lokal (lokal gewinnt — es ueberlebt fehlgeschlagene Pushes). STATE_DIR
# liegt in $HOME, ausserhalb des Repo-Checkouts, wird von actions/checkout nicht angetastet.
def _state_dir() -> str:
    d = os.environ.get("COCOBET_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".cocobet_state")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _local_mirror(name: str) -> str:
    return os.path.join(_state_dir(), os.path.basename(name))


def _load_seen(repo_file: str) -> dict:
    """Repo-Seen ∪ lokaler Runner-Spiegel (lokal gewinnt) -> ueberlebt fehlgeschlagene Pushes."""
    def _j(path):
        try:
            d = json.load(open(path, encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {**_j(repo_file), **_j(_local_mirror(repo_file))}


def _save_seen(repo_file: str, seen: dict) -> None:
    """In Repo-Datei (Backup/Sichtbarkeit) UND lokalen Spiegel schreiben."""
    for path in (repo_file, _local_mirror(repo_file)):
        try:
            json.dump(seen, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        except Exception as e:
            print("konnte Seen-State nicht schreiben (%s):" % path, e)
HT_MARKETS     = ("Half Time", "First Half Goals 1.5")   # HZ-1X2 ODER Über/Unter 1,5 erste Halbzeit
HT_LABEL       = {"Half Time": "HZ 1X2", "First Half Goals 1.5": "HZ Over/Under 1.5", "First Half Goals 0.5": "HZ Over/Under 0.5"}

UEFA_RX  = re.compile(r"(champions league|europa league|europa conference|conference league|uefa)", re.I)
TOP5_RX  = re.compile(r"(german bundesliga|english premier league|spanish la ?liga|italian serie a|french ligue 1|\bmls\b|major league soccer)", re.I)
TOP5_NEG = re.compile(r"(summer series|friendl|reserve|women|u1[0-9]\b|youth|amateur)", re.I)


def is_top5(league) -> bool:
    l = str(league or "")
    return bool(TOP5_RX.search(l)) and not TOP5_NEG.search(l)


def _is_intl_country(cc) -> bool:
    return bool(re.match(r"^(int|international|eu|europe)$", str(cc or ""), re.I))


def tier_of(m) -> str:
    # Top-Tier = Top-5 + MLS UND internationale Bewerbe (UEFA/Länderspiele) — Lucas 30.07.2026:
    # „internationale Bewerbe verhalten sich wie Top". Alles andere = Rest.
    if is_top5(m.get("league")):
        return "top"
    if UEFA_RX.search(str(m.get("league") or "")) or _is_intl_country(m.get("country")):
        return "top"
    return "rest"


def _vol(mk) -> float:
    return sum((r.get("vol") or 0.0) for r in (mk.get("runners") or []))


def _euro(v) -> str:
    v = float(v or 0)
    if v >= 1e6: return "€%.2fM" % (v / 1e6)
    if v >= 1e3: return "€%.1fK" % (v / 1e3)
    return "€%d" % round(v)


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _minutes_between(ts_a, ts_b):
    """09.08.2026 (Lucas): Dauer zwischen zwei History-Zeitstempeln in Minuten (gerundet). None wenn unlesbar."""
    try:
        a = datetime.fromisoformat(str(ts_a).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(ts_b).replace("Z", "+00:00"))
        d = (b - a).total_seconds() / 60.0
        return round(d) if d >= 0 else None
    except (TypeError, ValueError):
        return None


def _window_txt(a) -> str:
    """09.08.2026 (Lucas: „€/Min unschön — lieber genaue Zeit"): der Zufluss stammt aus dem Fenster
    zwischen den letzten zwei Scans. Variante 2 (Spielminuten-Spanne) wenn beide Live-Minuten da sind,
    sonst Variante 1 (Fenster-Dauer in Minuten). Nichts, wenn beides fehlt."""
    fm, tm = a.get("fromMin"), a.get("toMin")
    if isinstance(fm, (int, float)) and isinstance(tm, (int, float)) and tm >= fm and (fm > 0 or tm > 0):
        span = int(round(tm - fm))
        if span > 0:
            return " · %d'→%d' (%d Min)" % (int(fm), int(tm), span)
        return " · bei %d'" % int(tm)
    wm = a.get("windowMin")
    if isinstance(wm, (int, float)) and wm > 0:
        return " · letzte ~%d Min" % int(round(wm))
    return ""


def _flag(m) -> str:
    if UEFA_RX.search(str(m.get("league") or "")):
        return "🇪🇺"
    cc = str(m.get("country") or "").upper()
    if len(cc) == 2 and cc.isalpha():
        try:
            return chr(0x1F1E6 + ord(cc[0]) - 65) + chr(0x1F1E6 + ord(cc[1]) - 65)
        except Exception:
            return "🌍"
    return "🌍"


def _short_mk(k) -> str:
    return (str(k).replace("First Half Goals", "HZ Over/Under").replace(" Goals", "")
            .replace("Both teams to Score?", "BTTS").replace("Match Odds", "1X2")
            .replace("Half Time/Full Time", "HZ/EZ").replace("Half Time", "HZ 1X2")
            .replace("Correct Score", "Exakt").replace("Draw no Bet", "DNB"))


def _ht_label(name, home, away):
    n = str(name or "")
    if n == "The Draw":
        return "Remis (X)"
    if n == home:
        return "%s (Heim)" % home
    if n == away:
        return "%s (Ausw.)" % away
    return n


def _ht_thr(m) -> float:
    return HT_TOP_EUR if tier_of(m) == "top" else HT_REST_EUR


def _ht_one(m, market_name, top_thr=HT_TOP_EUR, rest_thr=HT_REST_EUR):
    """Ein einzelner HZ-Markt (HZ-1X2 oder Über/Unter 1,5 HZ1): ≥ tier-Schwelle UND ≥85 % einseitig."""
    mk = (m.get("markets") or {}).get(market_name)
    if not mk:
        return None
    total = _vol(mk)
    thr = top_thr if tier_of(m) == "top" else rest_thr
    if total <= 0 or total < thr:
        return None
    runners = mk.get("runners") or []
    lead = max(runners, key=lambda r: (r.get("vol") or 0.0), default=None)
    if not lead:
        return None
    lead_share = (lead.get("vol") or 0.0) / total
    if lead_share < HT_MIN_SHARE:          # ≥85 % auf einer Seite, sonst nur Liquidität → kein Push
        return None
    lo = lead.get("odd")
    if isinstance(lo, (int, float)) and lo < MIN_LEAD_ODD:   # 85 % auf einem ~1.0-Favoriten = keine Info
        return None
    # 08.08.2026 (Lucas): Geld auf den Fuehrenden NICHT mehr hart raus. Als Flag mitfuehren; in main()
    # nur pushen, wenn die Quote es bestaetigt (leadDir == "in" / Back). Sonst reaktiv/hohl -> raus.
    on_leader = _money_on_leader(m, lead.get("name"))
    home, away = m.get("home"), m.get("away")
    is_x2 = market_name == "Half Time"

    def share(test):
        for r in runners:
            if test(str(r.get("name") or "")):
                return (r.get("vol") or 0.0) / total
        return None

    return {"scenario": "ht", "matchId": str(m.get("matchId")), "value": total,
            "home": home, "away": away, "league": m.get("league"), "flag": _flag(m),
            "market": market_name, "mktLabel": HT_LABEL.get(market_name, _short_mk(market_name)), "isX2": is_x2,
            "kickoff": m.get("kickoff"), "live": m.get("liveInfo") or {},
            "total": total, "hs": share(lambda s: s == home),
            "ds": share(lambda s: s == "The Draw"), "as_": share(lambda s: s == away),
            "leadName": lead.get("name"), "leadLabel": _ht_label(lead.get("name"), home, away),
            "leadShare": lead_share, "leadOdd": lead.get("odd"), "tier": tier_of(m), "onLeader": on_leader}


def ht_alert(m, top_thr=HT_TOP_EUR, rest_thr=HT_REST_EUR):
    """Szenario 1: bester HZ-Markt (HZ-1X2 ODER Über/Unter 1,5 erste HZ) über tier-Schwelle + einseitig."""
    best = None
    for name in HT_MARKETS:
        a = _ht_one(m, name, top_thr, rest_thr)
        if a and (best is None or a["total"] > best["total"]):
            best = a
    return best


def _fix_window_ok(m) -> bool:
    """22.08.2026 (Lucas): Fix-Verdacht nur solange der HZ-Markt NOCH offen ist — vor Anpfiff oder in
    der 1. Halbzeit. Ab Halbzeit/2. HZ/Ende ist der HZ-Markt praktisch durch, „mehr Geld auf HZ" ist
    dann wertlos (Lucas: „es ist grad Pause 😂")."""
    li = m.get("liveInfo") or {}
    if li.get("finished") or li.get("is_ht"):
        return False
    t = li.get("time")
    if isinstance(t, (int, float)) and t > FIX_INPLAY_MAX_MIN:
        return False   # HZ-Markt zu weit fortgeschritten -> Ausgang praktisch durch (Zeit entscheidet)
    return True


def fix_alert(m):
    """Szenario „fix" (21.08.2026, Lucas): HZ-Geld dominiert den FT-Markt KLAR (HZ >= 2x FT UND >= FIX_HT_MIN_EUR, nur vor/in 1. HZ).
    Technisch unlogisch (FT ist normal viel liquider) -> Fix-Verdacht. Scannt jedes Spiel unabhaengig von
    der normalen Geld-Schwelle (Fix-Spiele liegen auf duennen Maerkten). ⚫ schwarze Kugel im Push."""
    mkts = m.get("markets") or {}
    if not _fix_window_ok(m):
        return None
    # FT-Baseline: groesster FT-Markt — Name mitfuehren, damit der Push zeigt WELCHER FT-Markt verglichen wird.
    ft_max, ft_name = 0.0, None
    for name in FIX_FT_MARKETS:
        mk = mkts.get(name)
        if mk:
            v = _vol(mk)
            if v > ft_max:
                ft_max, ft_name = v, name
    if ft_max <= 0:
        return None   # kein FT-Markt (Datenluecke) -> kein „HZ > FT"-Vergleich moeglich
    # HT-Markt-Wahl (22.08.2026, Lucas): NICHT der volumenstaerkste HT-Markt, sondern der mit dem
    # groessten EINSEITIGEN Geld. Ein 50/50-O/U (viel Volumen, aber ausgewogen) ist kein Fix-Signal;
    # ein klar einseitig geladener HT-Markt (z.B. 7K auf Away HT) schon. leadShare-Gate + Auswahl nach lead_vol.
    best = None   # (lead_vol, name, total, lead_runner, lead_share)
    for name in FIX_HT_MARKETS:
        mk = mkts.get(name)
        if not mk:
            continue
        total = _vol(mk)
        if total < FIX_HT_MIN_EUR:
            continue
        runners = (mk.get("runners") or [])
        lead = max(runners, key=lambda r: (r.get("vol") or 0.0), default=None)
        if not lead:
            continue
        lead_vol = lead.get("vol") or 0.0
        lead_share = (lead_vol / total) if total else 0.0
        if lead_share < FIX_LEAD_SHARE:      # ausgewogen (50/50) -> kein Signal
            continue
        _lo = lead.get("odd")
        if isinstance(_lo, (int, float)) and _lo < FIX_LEAD_MIN_ODD:
            continue   # Naht-Lock (@~1.0) -> Geld auf's Sichere/Offensichtliche, kein Fix-Signal
        if best is None or lead_vol > best[0]:
            best = (lead_vol, name, total, lead, lead_share)
    if best is None:
        return None
    lead_vol, ht_name, ht_total, lead, lead_share = best
    if ht_total < ft_max * FIX_RATIO_MIN:    # HZ muss FT klar dominieren (>=2x)
        return None
    ratio = (ht_total / ft_max) if ft_max > 0 else 99.0
    return {"scenario": "fix", "matchId": str(m.get("matchId")), "value": ht_total,
            "home": m.get("home"), "away": m.get("away"), "league": m.get("league"), "flag": _flag(m),
            "market": ht_name, "mktLabel": HT_LABEL.get(ht_name, _short_mk(ht_name)),
            "kickoff": m.get("kickoff"), "live": m.get("liveInfo") or {},
            "htEur": ht_total, "ftEur": ft_max, "ftName": ft_name, "ftLabel": _short_mk(ft_name),
            "ratio": ratio, "total": ht_total, "tier": tier_of(m),
            "leadName": lead.get("name"), "leadLabel": _ht_label(lead.get("name"), m.get("home"), m.get("away")),
            "leadShare": lead_share, "leadOdd": lead.get("odd")}


def _market_lead(m, name):
    """Führender Ausgang + Anteil des Marktes aus den aktuellen Preisen."""
    mk = (m.get("markets") or {}).get(name)
    if not mk:
        return None, None, None
    rs = mk.get("runners") or []
    tot = sum((r.get("vol") or 0.0) for r in rs)
    if tot <= 0 or not rs:
        return None, None, None
    top = max(rs, key=lambda r: (r.get("vol") or 0.0))
    return top.get("name"), (top.get("vol") or 0.0) / tot, top.get("odd")


def fresh_alert(m, hist, top_thr=FRESH_TOP_EUR, rest_thr=FRESH_REST_EUR):
    """Szenario 2: Zufluss auf dem GRÖSSTEN Zufluss-Markt (aus mkv) ≥ tier-Schwelle — pro Markt."""
    # 23.08.2026 (Lucas: „solche Push im trades wertlos, vor allem wenn schon beendet"): ein beendetes
    # oder in der Schlussphase (>=FRESH_LATE_MAX_MIN) laufendes Spiel hat kein bespielbares Fenster mehr —
    # das späte Geld läuft nur noch aufs Sichere bzw. reagiert auf ein Spielereignis (Quote neu gepreist).
    # Kein Moneyflow-Push mehr. (Vor-Anpfiff: liveInfo leer -> time None -> unberührt.)
    _li = m.get("liveInfo") or {}
    if _li.get("finished"):
        return None
    _mt = _li.get("time")
    if isinstance(_mt, (int, float)) and _mt >= FRESH_LATE_MAX_MIN:
        return None
    pts = (hist or {}).get(str(m.get("matchId")))
    if not isinstance(pts, list) or len(pts) < 2:
        return None
    pmk, lmk = pts[-2].get("mkv"), pts[-1].get("mkv")
    if not isinstance(pmk, dict) or not isinstance(lmk, dict):
        return None   # ohne per-Markt-History (mkv) kein per-Markt-Signal — irreführende Gesamt-Zahl vermeiden
    thr = top_thr if tier_of(m) == "top" else rest_thr
    best = None                                   # (Marktname, Zufluss, aktuelles Markt-Volumen)
    for name, lv in lmk.items():
        inflow = (lv or 0.0) - (pmk.get(name) or 0.0)
        if best is None or inflow > best[1]:
            best = (name, inflow, lv or 0.0)
    if not best or best[1] < thr:
        return None
    market_name, inflow, mkt_total = best
    lead_name, lead_share, lead_odd = _market_lead(m, market_name)
    if isinstance(lead_odd, (int, float)) and lead_odd < MIN_LEAD_ODD:   # Geld auf ~1.0-Favoriten = sinnlos
        return None
    on_leader = _money_on_leader(m, lead_name)   # 08.08.2026 (Lucas): s.o. — Flag statt hartem Raus, in main() per Back gegated
    window_min = _minutes_between(pts[-2].get("ts"), pts[-1].get("ts"))   # 09.08.2026 (Lucas): Fenster-Dauer (ehrlich, statt €/Min)
    from_min = pts[-2].get("min")
    to_min = pts[-1].get("min")
    if to_min is None:
        to_min = (m.get("liveInfo") or {}).get("time")
    event_win = _event_in_window(pts[-2], pts[-1])   # 10.08.2026 (Lucas): fiel ein Tor/Karte INS Delta-Fenster?
    return {"scenario": "fresh", "matchId": str(m.get("matchId")), "value": mkt_total,
            "home": m.get("home"), "away": m.get("away"), "league": m.get("league"), "flag": _flag(m),
            "market": market_name, "inflow": inflow, "total": mkt_total, "tier": tier_of(m),
            "kickoff": m.get("kickoff"), "live": m.get("liveInfo") or {},
            "leadName": lead_name, "leadShare": lead_share, "leadOdd": lead_odd, "onLeader": on_leader,
            "windowMin": window_min, "fromMin": from_min, "toMin": to_min, "eventInWindow": event_win}


def _event_in_window(p_prev, p_last) -> bool:
    """10.08.2026 (Lucas): Aenderte sich der ECHTE Spielstand ODER die roten Karten zwischen den beiden
    Scans, die den Zufluss-Delta bilden? Dann fiel ein Spielereignis (Tor/Karte) INS Fenster — die Quote/
    Richtung ist kontaminiert. Praezise Variante zum geratenen Quotensprung (Betwatch liefert sc/rc live)."""
    if not isinstance(p_prev, dict) or not isinstance(p_last, dict):
        return False
    for key in ("sc", "rc"):
        a, b = p_prev.get(key), p_last.get(key)
        if isinstance(a, list) and isinstance(b, list) and a != b:
            return True
    return False


def _dir_event_jump(a) -> bool:
    """08.08.2026 (Lucas): Spielereignis (Tor/Karte) zwischen den beiden verglichenen Scans -> die Quote
    ist mechanisch neu gepreist, die Back/Lay-Lesart ungueltig. 10.08.2026: PRAEZISE, wenn wir den echten
    Score im Fenster haben (eventInWindow); sonst Fallback auf die 40%-Quotensprung-Heuristik (Alt-Daten /
    HZ-Szenario ohne Delta-Fenster)."""
    if a.get("eventInWindow"):
        return True
    prev, odd = a.get("leadPrev"), a.get("leadOdd")
    try:
        if prev and odd:
            return abs(float(odd) - float(prev)) / float(prev) >= JUMP_REL
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return False


def _ou_under_alive(a):
    """14.08.2026 (Lucas): True, wenn der gepushte Ausgang ein UNDER ist, das noch LEBT (aktueller Stand
    unter der Linie). Nur dann ist eine Live-Drift kein normaler Zeit-Verfall, sondern ein Fade — jemand
    layt das Under / will das Tor. False bei Over/Team-Maerkten oder schon gerissener Linie; None unklar.
    Ein Under muss mit der Uhr KUERZER werden; driftet es raus, drueckt Geld GEGEN es."""
    label = str(a.get("leadLabel") or a.get("leadName") or "").lower()
    if "under" not in label:
        return False
    m = re.search(r"(\d+(?:[.,]\d+)?)", label)
    if not m:
        return None
    try:
        line = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    li = a.get("live") or {}
    g1, g2 = li.get("goal_v1"), li.get("goal_v2")
    if not (isinstance(g1, int) and isinstance(g2, int)):
        return None
    return (g1 + g2) < line


def _dir_line(a, ou_fade=False) -> str:
    """08.08.2026 (Lucas: „ist es Back oder Lay?"): Quotenbewegung des Favoriten. Matched-Volumen sagt
    nicht, ob gebackt oder gelayt wurde — die Quote schon. Kuerzer = echter Back-Rueckhalt, driftet =
    nur Volumen ohne Richtung. Nur zeigen, wenn eindeutig (in/out).
    08.08.2026: Springt die Quote extrem (Tor/Karte, siehe _dir_event_jump), ist die Richtung nicht
    lesbar -> ehrlich „neu gepreist, Richtung unklar" statt eines falschen Back-/Lay-Urteils."""
    d = a.get("leadDir")
    if d not in ("in", "out"):
        return ""
    if _dir_event_jump(a):
        return "\n⚠️ Quote nach Spielereignis neu gepreist — Richtung unklar"
    prev, odd = a.get("leadPrev"), a.get("leadOdd")
    move = (" (%.2f → %.2f)" % (prev, odd)) if isinstance(prev, (int, float)) and isinstance(odd, (int, float)) else ""
    if d == "in":
        return "\n📈 Quote bestätigt — Back%s" % move   # 08.08.2026 (Lucas): NICHT ✅ — das nutzt er selbst zum Auswerten im Channel
    if _is_live(a):   # 09.08.2026 (Lucas): in-play driftet die Quote von allein mit der Zeit (kein Tor -> Sieg-Quote steigt), egal ob jemand layt -> KEIN falsches 'kein Back'-Urteil; vor Anpfiff bleibt es (da bewegt nur Geld die Quote)
        # 14.08.2026 (Lucas, vorerst NUR Trades): Under muss mit der Uhr kuerzer werden. Driftet es RAUS,
        # obwohl der Ausgang noch lebt (Stand < Linie), drueckt Geld GEGEN das Under -> jemand layt es /
        # will das Tor. Das ist der Fade, kein normaler Zeit-Drift.
        if ou_fade and _ou_under_alive(a) is True:
            return ("\n⚠️ Geld liegt auf <b>Under</b>, aber Quote driftet raus%s — Under wird gelayt, "
                    "die Gegenseite will das Tor" % move)
        return "\n⏳ Quote driftet%s — im Spiel normal (Zeit läuft)" % move
    return "\n⚠️ Quote driftet — kein Back-Rückhalt%s" % move


def _fuehrt_line(a) -> str:
    """08.08.2026 (Lucas): Geld auf die aktuell FÜHRENDE Mannschaft. Kommt nur durch, wenn die Quote es
    bestaetigt (Back) — dann folgt das Geld dem Sieger MIT Preis-Rueckhalt = starkes Signal, nicht reaktiv."""
    return "\n▶ <b>führt</b> — Geld folgt der Führung" if a.get("onLeader") else ""


def _lead_magnitude(a) -> float:
    """Signal-Groesse, an der die Fuehrungs-Extra-Schwelle misst: HZ = gematchtes Geld auf dem HZ-Markt,
    Fresh = frischer Zufluss auf dem Markt."""
    if a.get("scenario") == "ht":
        return float(a.get("total") or 0.0)
    return float(a.get("inflow") or 0.0)


def _lead_base_thr(a, ht_top, ht_rest, fresh_top, fresh_rest) -> float:
    """Die normale tier-Schwelle des jeweiligen Szenarios/Kanals — Basis fuer die Fuehrungs-Extra-Huerde."""
    top = (a.get("tier") == "top")
    if a.get("scenario") == "ht":
        return ht_top if top else ht_rest
    return fresh_top if top else fresh_rest


def _leader_gate(alerts, ht_top=HT_TOP_EUR, ht_rest=HT_REST_EUR,
                 fresh_top=FRESH_TOP_EUR, fresh_rest=FRESH_REST_EUR):
    """08.08.2026 (Lucas): Geld auf den Fuehrenden nur pushen, wenn (1) die Quote es bestaetigt (Back =
    leadDir 'in') UND (2) der Einsatz die Fuehrungs-Extra-Schwelle erreicht (LEAD_PUSH_FACTOR x normale
    tier-Schwelle). Sonst -> reaktives/kleines Mitlaufen mit der Fuehrung, faellt raus, damit der Kanal an
    starken Spieltagen nicht geflutet wird. Nicht-Fuehrer voellig unberuehrt (normale Schwelle gilt schon)."""
    out = []
    for a in (alerts or []):
        if not a.get("onLeader"):
            out.append(a)
            continue
        if a.get("leadDir") != "in" or _dir_event_jump(a):
            continue   # kein Back ODER Back-Lesart durch Spielereignis (Tor/Karte) kontaminiert -> raus
        if _lead_magnitude(a) < _lead_base_thr(a, ht_top, ht_rest, fresh_top, fresh_rest) * LEAD_PUSH_FACTOR:
            continue   # Back, aber zu klein -> Fuehrungs-Geld erst ab Extra-Schwelle in den Push
        out.append(a)
    return out


def _drop_subthreshold_jump(alerts):
    """09.08.2026 (Lucas, Braga 2:1->2:2 in der Nachspielzeit): sprang die Quote durch ein Spielereignis
    (Tor/Karte, _dir_event_jump), lief das Geld zur Quote DAVOR rein (leadPrev), nicht zur neu gepreisten.
    Lag die Vor-Ereignis-Quote UNTER MIN_LEAD_ODD, war es Geld auf einen ~1.0-fast-sicheren Fuehrenden =
    sinnlos — ohne den Sprung haette die Push nie ueber der Schwelle gestanden und gehoert gar nicht raus.
    (Ohne Sprung filtert fresh_alert das schon, dort ist die aktuelle Quote = die Geld-Quote.)
    Greift nur, wo wir die Vor-Quote wirklich haben (sonst ist kein Sprung erkennbar)."""
    out = []
    for a in (alerts or []):
        prev = a.get("leadPrev")
        if _dir_event_jump(a) and isinstance(prev, (int, float)) and prev < MIN_LEAD_ODD:
            continue
        out.append(a)
    return out


def attach_direction(alerts, direction) -> list:
    """Jedem Alert die Richtung des Favoriten-Runners anhaengen (Join ueber matchId/market/leadName)."""
    for a in (alerts or []):
        e = _dir_look(direction, a.get("matchId"), a.get("market"), a.get("leadName")) if direction else None
        if e:
            a["leadDir"], a["leadPrev"] = e.get("dir"), e.get("prev")
    return alerts


def should_send(seen: dict, key: str, value: float) -> bool:
    prev = seen.get(key)
    if prev is None:
        return True
    try:
        return value >= prev * DEDUP_FACTOR
    except Exception:
        return True


# 22.08.2026 (Lucas: „grosse Ligen werden mit Geld geflutet"): pro Spiel kein zweiter Moneyflow-
# (fresh-)Push innerhalb der Sperre — egal wie stark der Zufluss waechst. Zeitstempel je matchId
# unter store["_freshTs"]. Gilt fuer BEIDE Kanaele (jeder Kanal hat seinen eigenen Seen-Store).
FRESH_COOLDOWN_MIN = float(os.environ.get("BF_FRESH_COOLDOWN_MIN") or 15.0)


def _fresh_cooldown_ok(store: dict, match_id, now=None) -> bool:
    if FRESH_COOLDOWN_MIN <= 0:
        return True
    now = now or datetime.now(timezone.utc)
    ts = (store.get("_freshTs") or {}).get(str(match_id))
    if not ts:
        return True
    try:
        last = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return (now - last).total_seconds() >= FRESH_COOLDOWN_MIN * 60.0
    except Exception:
        return True


def _fresh_cooldown_mark(store: dict, match_id, now=None) -> None:
    now = now or datetime.now(timezone.utc)
    store.setdefault("_freshTs", {})[str(match_id)] = now.isoformat()


def _consensus_index() -> dict:
    """betfair_consensus.json (vom Runner, betfair_consensus.py, laeuft VOR alerts) -> {matchId: game}."""
    try:
        d = json.load(open(CONSENSUS_FILE, encoding="utf-8"))
        return {str(g.get("matchId")): g for g in (d.get("games") or []) if g.get("matchId") is not None}
    except Exception:
        return {}


def _usd(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if v >= 1e6: return "$%.1fM" % (v / 1e6)
    if v >= 1e3: return "$%.0fK" % (v / 1e3)
    return "$%d" % round(v)


def _consensus_block(a, cidx) -> str:
    """09.08.2026 (Lucas): Zweitmeinung ans Trades-Frisch-Signal — Pinnacle/Soft/Poly-Quoten fuer die
    Geld-Seite + Verdikt (aus betfair_consensus.py). Leer, wenn kein Odds-Anker fuer das Spiel da ist."""
    g = (cidx or {}).get(str(a.get("matchId")))
    if not g or g.get("verdict") == "no_anchor":
        return ""
    # 14.08.2026 (Lucas): Konsens ist 1X2 (Gesamtsieger). Bei fremdem Geld-Markt (Über/Unter, BTTS, HZ) ist
    # das ein ANDERER Markt -> keine Zweitmeinung zur Wette, weglassen. Und LIVE sind die Konsens-Quoten teils
    # vom Vorspiel (stale, near-lock nach Toren) -> nur pre-match zeigen.
    if a.get("market") != "Match Odds":
        return ""
    if bool(g.get("live")) or _is_live(a):
        return ""
    live = bool(g.get("live"))
    parts = []
    if isinstance(g.get("pinnOdd"), (int, float)):
        mv = g.get("pinnMovePP")
        mvtxt = (" %s%.1fpp" % ("▲" if mv > 0 else "▼", abs(mv))) if (not live and isinstance(mv, (int, float)) and abs(mv) >= 0.1) else ""
        parts.append("Pinnacle @%.2f%s" % (g["pinnOdd"], mvtxt))
    if isinstance(g.get("softOdd"), (int, float)):
        n = g.get("softN") or 0
        parts.append("Soft @%.2f%s" % (g["softOdd"], ("×%d" % n) if n else ""))
    poly = g.get("poly") or {}
    if isinstance(poly.get("odd"), (int, float)):
        parts.append("Poly @%.2f %s" % (poly["odd"], _usd(poly.get("vol"))))
    if not parts:
        return ""
    # 02.09.2026 (Lucas: „bei Konsens der grüne Haken sollte auch weg"): ✅/❌ sind in DIESEM Channel
    # SEINE Auswertungs-Marker — er hängt sie nach Abpfiff per Hand an die Nachricht. Ein ✅ mitten
    # im Text ist damit kein Schmuck, sondern eine Verwechslungsquelle beim Zählen. Dieselbe Regel
    # steht seit 08.08. eine Ebene tiefer bei „Quote bestätigt — Back" („NICHT ✅"); sie galt nur
    # hier noch nicht. Jetzt trägt das Verdikt ein neutrales Zeichen.
    verd = {"konsens": "🧩 Konsens — alle sehen dieselbe Seite vorn",
            "teil": "➖ teils einig",
            "uneinig": "⚠️ uneinig — Buchmacher sehen die andere Seite vorn"}.get(g.get("verdict"), "")
    if live:
        verd = "\u2139\ufe0f Live \u2014 Quoten teils vom Vorspiel, nur grobe Orientierung"
    side = g.get("moneyName") or ""
    head = "\n\n🧭 <b>Zweitmeinung</b>" + ((" · 1X2 " + _esc(side)) if side else "")
    return head + "\n" + " · ".join(parts) + (("\n" + verd) if verd else "")


def _lead_odd_txt(a) -> str:
    """09.08.2026 (Lucas, Braga-Fall): Quote hinter dem Fuehrer. Normalfall: aktuelle Quote. Ist die
    Quote aber durch ein Spielereignis gesprungen (Tor/Karte, _dir_event_jump), war die JETZIGE Quote
    NICHT die, zu der das Geld lief — das lief bei der Quote DAVOR rein (leadPrev). Dann diese Vor-
    Ereignis-Quote zeigen statt der irrefuehrenden, neu gepreisten. (116k liefen unter ~1.1 bei 2:1-
    Fuehrung rein, dann 2:2 in der Nachspielzeit -> 42.00 — @42.00 waere komplett irrefuehrend.)"""
    odd = a.get("leadOdd")
    if not isinstance(odd, (int, float)):
        return ""
    if _dir_event_jump(a):
        prev = a.get("leadPrev")
        if isinstance(prev, (int, float)) and prev > 0:
            return " · Geld lief @~%.2f rein" % prev
        return ""   # keine irrefuehrende, neu gepreiste Quote zeigen
    return " @%.2f" % odd


def build_message(a) -> str:
    head = ("%s <b>%s</b> v <b>%s</b>\n<i>%s</i>\n"
            % (a["flag"], _esc(a["home"]), _esc(a["away"]), _esc(str(a["league"])[:48])))
    if a["scenario"] == "fix":
        odd = _lead_odd_txt(a)
        lbl = a.get("mktLabel") or "HZ"
        _ratio_txt = ("<b>%.1f×</b> mehr auf HZ" % a["ratio"]) if a.get("ftEur", 0) > 0 else "FT ~0"
        _st = _flow_status(a)   # 21.08.2026 (Lucas): Anpfiff/Live-Status wie in den anderen Pushes
        msg = ("\u26ab <b>Betfair · Fix-Verdacht</b> — mehr Geld auf <b>Halbzeit</b> als Full-Time\n" + head
               + ((_st + "\n") if _st else "")
               + "\U0001f4b7 %s: <b>%s</b> HZ  vs  <b>%s</b> FT%s · %s\n"
                 % (_esc(lbl), _euro(a["htEur"]), _euro(a["ftEur"]),
                    ((" (" + _esc(a.get("ftLabel")) + ")") if a.get("ftLabel") else ""), _ratio_txt)
               + "<b>%.0f%%</b> auf %s%s" % ((a.get("leadShare") or 0.0) * 100, _esc(a["leadLabel"]), odd))
        if (a.get("leadShare") or 0.0) >= 0.90:
            msg += " · sehr einseitig"
        return msg + _dir_line(a, ou_fade=False)
    if a["scenario"] == "ht":
        odd = _lead_odd_txt(a)
        lbl = a.get("mktLabel") or "HZ"
        msg = ("🔵 <b>Betfair · Halbzeit-Geld (einseitig)</b>\n" + head   # 31.07.2026 (Lucas): blaue Kugel fuer HZ = schneller erkennbar; Frisches Geld bleibt gelb
               + "💷 %s: <b>%s</b> gematcht · <b>%.0f%%</b> auf %s%s"
                 % (_esc(lbl), _euro(a["total"]), a["leadShare"] * 100, _esc(a["leadLabel"]), odd))
        msg += _fresh_inline(a)
        if a.get("isX2"):
            pct = lambda x: "—" if x is None else "%.0f%%" % (x * 100)
            msg += ("\n%s %s · X %s · %s %s" % (_esc(a["home"]), pct(a["hs"]), pct(a["ds"]),
                                                _esc(a["away"]), pct(a["as_"])))
        return msg + _fuehrt_line(a) + _dir_line(a, ou_fade=True) + _draw_inplay_note(a)
    tl = "Top-Liga" if a["tier"] == "top" else "Rest-Liga"
    msg = ("🟡 <b>Betfair · Frisches Geld</b> · %s\n" % tl + head
           + "💶 <b>%s</b>: +<b>%s</b> frisch → jetzt <b>%s</b>"
             % (_esc(_short_mk(a["market"])), _euro(a["inflow"]), _euro(a["total"])))
    if a.get("leadName"):
        odd = _lead_odd_txt(a)
        msg += "\nführt: %s (%.0f%%)%s" % (_esc(a["leadName"]), (a.get("leadShare") or 0.0) * 100, odd)
    return msg + _fuehrt_line(a) + _dir_line(a, ou_fade=True) + _draw_inplay_note(a)


def _bar(share, width=10):
    """Visuelle Geld-Leiste (Telegram-tauglich): gefuellt/leer je Anteil. share in [0,1]."""
    try:
        val = max(0.0, min(1.0, float(share or 0.0)))
    except (TypeError, ValueError):
        val = 0.0
    fill = int(round(val * width))
    return "▓" * fill + "░" * (width - fill)


def _flow_status(a) -> str:
    """Anpfiff-/Live-Status. KEIN Spielstand und KEINE exakte Minute — die waeren bei 15-Min-Scans
    oft veraltet (Lucas: „zu riskant, hatten wir schon beim Radar"). Nur der Zustand."""
    li = a.get("live") or {}
    if li.get("finished"):
        return "🏁 beendet"
    if li.get("is_ht"):
        return "⏸ Halbzeit"
    t = li.get("time")
    if isinstance(t, (int, float)) and t > 0:
        return "⚽ läuft"
    ko = a.get("kickoff")
    if ko:
        try:
            k = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
            mins = (k - datetime.now(timezone.utc)).total_seconds() / 60.0
            if mins >= 90:
                return "⏱ Anpfiff in %.1fh" % (mins / 60.0)
            if mins >= 1:
                return "⏱ Anpfiff in %d Min" % int(round(mins))
            if mins > -5:
                return "⏱ Anpfiff jetzt"
            return "⚽ läuft"   # Anpfiff vorbei, keine Minute -> laufend
        except Exception:
            pass
    return ""


def _is_live(a) -> bool:
    """In-Play (fuer die 🔴-LIVE-Kopfzeile): laeuft oder Halbzeit."""
    return _flow_status(a) in ("⚽ läuft", "⏸ Halbzeit")


def _leader_team(m):
    """Aktuell fuehrende Mannschaft aus dem Live-Stand (None bei Gleichstand/keinem Stand)."""
    li = m.get("liveInfo") or {}
    g1, g2 = li.get("goal_v1"), li.get("goal_v2")
    if not (isinstance(g1, int) and isinstance(g2, int)) or g1 == g2:
        return None
    return m.get("home") if g1 > g2 else m.get("away")


def _money_on_leader(m, lead_name) -> bool:
    """Reaktives Geld: die Seite mit dem meisten Geld IST die bereits fuehrende Mannschaft
    (Lucas: „1:0 fuehrt und Kohle kommt = eher wertlos"). Greift nur, wenn der Ausgang eine
    Mannschaft ist (Ueber/Unter, BTTS matchen den Team-Namen nicht -> nicht betroffen)."""
    ldr = _leader_team(m)
    return bool(ldr) and bool(lead_name) and str(lead_name) == str(ldr)


def _fresh_inline(a) -> str:
    """18.08.2026 (Lucas): frischen Zufluss IN die blaue HT-Nachricht schreiben (eigene 💶-Zeile),
    wenn ein fresh-Alert denselben HT-Markt betraf. Zeigt +Zufluss, %frisch und das Zeitfenster."""
    f = a.get("freshMerge")
    if not f:
        return ""
    inflow = f.get("inflow") or 0.0
    total = f.get("total") or 0.0
    seg = []
    if total:
        seg.append("%.0f%% frisch" % (inflow / total * 100.0))
    line = "\n💶 <b>+%s</b> Zufluss" % _euro(inflow)
    if seg:
        line += " · " + " · ".join(seg)
    return line + _window_txt(f)


def build_public_message(a, trades=False) -> str:
    """Oeffentliches Format (05.08.2026, Lucas: schoener + informativer): Anpfiff/Live-Status +
    Spielstand, Zufluss-Anteil am Markt, visuelle Geld-Leiste, Quote. Telegram-HTML (b/i, Unicode)."""
    league = _esc(str(a.get("league") or "")[:60])
    status = _flow_status(a)
    status_line = ("\n" + status) if status else ""
    teams = ("%s <b>%s</b> v <b>%s</b>\n🏆 <i>%s</i>%s"
             % (a["flag"], _esc(a["home"]), _esc(a["away"]), league, status_line))
    odd = _lead_odd_txt(a)

    live_badge = "🔴 <b>LIVE</b> · " if _is_live(a) else ""
    if a["scenario"] == "ht":
        share = a.get("leadShare") or 0.0
        return (live_badge + "🔵 <b>Betfair Halftime Flow</b>\n\n" + teams + "\n\n"
                + "💷 <b>%s</b> — Halbzeit-Geld\n<b>%s</b> gematcht"
                  % (_esc(_short_mk(a["market"])), _euro(a["total"]))
                + _fresh_inline(a) + "\n\n"
                + "📊 <b>%s</b>  %s %.0f%%%s"
                  % (_esc(a["leadLabel"]), _bar(share), share * 100, odd)
                + _fuehrt_line(a) + _dir_line(a, ou_fade=trades))

    share = a.get("leadShare") or 0.0
    total = a.get("total") or 0.0
    inflow = a.get("inflow") or 0.0
    pct = (" (%.0f%% frisch)" % (inflow / total * 100)) if total else ""
    lead = a.get("leadName") or "—"
    return (live_badge + "🟡 <b>Betfair Moneyflow</b>\n\n" + teams + "\n\n"
            + "💶 <b>%s</b> — frischer Zufluss%s\n+<b>%s</b> → Markt <b>%s</b>%s\n\n"
              % (_esc(_short_mk(a["market"])), _window_txt(a), _euro(inflow), _euro(total), pct)
            + "📊 <b>%s</b>  %s %.0f%%%s"
              % (_esc(lead), _bar(share), share * 100, odd)
            + _fuehrt_line(a) + _dir_line(a, ou_fade=trades) + (_draw_inplay_note(a) if trades else ""))


def _tg_public(text) -> bool:
    """An den ÖFFENTLICHEN CocoBet-Channel (TELEGRAM_CHAT_ID). Ohne Token/Chat → Vorschau (kein Send)."""
    token = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "-1003819239615").strip()   # 04.08.2026 (Lucas): Public-Channel-Fallback wie telegram_wm.py — TELEGRAM_CHAT_ID ist NICHT als Secret gesetzt; ohne Fallback lief der Public-Pfad still im Vorschau-Modus (nie gesendet).
    if not token or not chat:
        print("PUBLIC-Vorschau (kein TOKEN/CHAT_ID):\n" + text + "\n")
        return False
    body = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token,
                                 data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print("Public-Send-Fehler:", e)
        return False


def _consensus_for_push(a, cidx) -> dict:
    """10.08.2026 (Lucas): kompakter Konsens-Verdikt (Pinnacle/Soft/Poly-Zweitmeinung) fuers Push-Ledger.
    Damit kann betfair_public_eval spaeter auswerten, ob konsens-BESTAETIGTE Pushs besser laufen als
    uneinige. None, wenn zu dem Spiel kein Konsens-Eintrag existiert."""
    g = (cidx or {}).get(str(a.get("matchId"))) if isinstance(cidx, dict) else None
    if not g:
        return None
    v = g.get("verdict")
    if v in (None, "no_anchor"):
        return {"verdict": "no_anchor", "agree": None}
    return {"verdict": v, "agree": bool(g.get("agree"))}


# 04.09.2026: Serien-Abdruck beim Senden. Bewusst defensiv — ein fehlendes/kaputtes
# Serien-Artefakt darf NIE einen Push verhindern. Im Zweifel steht None im Ledger.
_SERIEN_CACHE = None


def _serien_laden():
    global _SERIEN_CACHE
    if _SERIEN_CACHE is None:
        out = []
        for datei in ("liga_streaks.json", "mls_streaks.json", "wm_streaks.json"):
            try:
                with open(datei, encoding="utf-8") as f:
                    out += (json.load(f) or {}).get("streaks") or []
            except Exception:
                pass
        _SERIEN_CACHE = out
    return _SERIEN_CACHE


def _serie_fuer_push(a):
    try:
        from push_serie import serie_fuer_push
        return serie_fuer_push(a, _serien_laden())
    except Exception as e:
        print("  Serien-Stempel uebersprungen (nicht fatal):", e)
        return None


def _log_public_push(a, cidx=None) -> None:
    """Jeden GESENDETEN Public-Push in betfair_public_ledger.json festhalten → betfair_public_eval.py
    rechnet ihn später gegen den Endstand ab. Ein Eintrag je Spiel+Szenario+Markt (kein Doppelzählen).
    10.08.2026: Konsens-Zweitmeinung mitloggen (fuer die Konsens-Auswertung)."""
    try:
        led = json.load(open(PUB_LEDGER_FILE, encoding="utf-8"))
        if not isinstance(led, list):
            led = []
    except Exception:
        led = []
    k = "%s:%s:%s" % (a.get("scenario"), a.get("matchId"), a.get("market"))
    if any(e.get("k") == k for e in led):
        return
    led.append({"k": k, "matchId": a.get("matchId"), "scenario": a.get("scenario"),
                "market": a.get("market"), "league": a.get("league"),
                "home": a.get("home"), "away": a.get("away"),
                "leadName": a.get("leadName"), "leadOdd": a.get("leadOdd"),
                "value": a.get("value"), "sentAt": datetime.now(timezone.utc).isoformat(),
                "status": "pending", "htScore": None, "consensus": _consensus_for_push(a, cidx),
                # 04.09.2026 (Lucas): „wenn der Favorit eine lange Serie hat, ist es okay, den zu
                # pushen — aber das muessten wir alles haben, die Infos." Hatten wir nicht: die
                # Serien-Dateien sind Momentaufnahmen, welche Serie an einem vergangenen Push-Tag
                # galt, stand nirgends. Deshalb hier stempeln, im Moment des Sendens.
                # None = Markt nicht abgebildet; {"gefunden": False} = erkannt, aber ohne Serie
                # bzw. kein Team-Treffer. Die drei Faelle sind beim Auswerten NICHT dasselbe.
                "serie": _serie_fuer_push(a)})
    try:
        json.dump(led[-800:], open(PUB_LEDGER_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    except Exception as e:
        print("Public-Ledger-Schreibfehler:", e)


# 13.08.2026 (Lucas-Audit): dem In-Play-Draw-Geld zur bereits kollabierten X-Quote hinterherlaufen
# verliert nachweislich (-31..-79% ROI, betfair_draw_tracker). Pre-Match-Draw (~3.5) ist ~break-even.
DRAW_INPLAY_CHASE_MAX_ODD = 2.2   # In-Play-Draw-Push nur, wenn die X-Quote NOCH nicht darunter kollabiert ist


def _draw_inplay_chase(a) -> bool:
    """True = In-Play-Moneyflow auf die Draw-Seite (Match Odds) mit schon kurzer X-Quote -> der
    verlustreiche Nachlauf. Nur diesen Fall raus; Pre-Match-Draw und Nicht-Draw bleiben. REIN/testbar."""
    if str(a.get("leadName") or "") != "The Draw" or a.get("market") != "Match Odds":
        return False
    li = a.get("live") or {}
    if li.get("time") is None or li.get("finished"):
        return False   # nicht in-play
    od = a.get("leadOdd")
    return isinstance(od, (int, float)) and od < DRAW_INPLAY_CHASE_MAX_ODD


def _draw_inplay_note(a) -> str:
    """14.08.2026 (Lucas): Warnzeile fuer In-Play-Remis-Nachlauf. Fallende X-Quote + Geld aufs Live-Remis
    SIEHT aus wie Rueckenwind ('Quote bestaetigt Back'), ist aber der Zeit-Effekt: das Remis wird mit der
    Uhr von selbst wahrscheinlicher, der fallende Kurs ist die Falle (-31..-79% ROI, betfair_draw_tracker).
    Nur In-Play + Match Odds + The Draw. Zwei Stufen: <2.2 = schon kollabiert (der belegte Verlust-Kern)."""
    if str(a.get("leadName") or "") != "The Draw" or a.get("market") != "Match Odds":
        return ""
    li = a.get("live") or {}
    if li.get("time") is None or li.get("finished"):
        return ""   # nicht in-play -> Pre-Match-Remis ist ~break-even, keine Warnung
    od = a.get("leadOdd")
    if isinstance(od, (int, float)) and od < DRAW_INPLAY_CHASE_MAX_ODD:
        return ("\n⛔ <b>Remis schon kollabiert</b> (X &lt; 2.2) — mit der Uhr wird das Remis von selbst "
                "wahrscheinlicher, der fallende Kurs ist die Falle. Nachlaufen verliert (−31…−79% ROI).")
    g1, g2 = li.get("goal_v1"), li.get("goal_v2")
    tail = ", Remis wird von allein wahrscheinlicher" if (g1 == 0 and g2 == 0) else ""
    return ("\n⚠️ <b>Aber:</b> In-Play-Remis-Nachlauf — die fallende X-Quote ist hier kein Rückenwind, "
            "sondern der Zeit-Effekt" + tail + ". Nachlaufen verliert historisch (−31…−79% ROI).")


# 14.08.2026 (Lucas): zwei Public-Filter gegen unnoetige HT/Live-Pushs, wo die Geld-% der QUOTE
# widersprechen. Trades sieht die weiter (Under-Fade-Hinweis etc.), Public nicht.
PUB_INCOHERENT_SHARE = float(os.environ.get("BF_PUB_INCOHERENT_SHARE") or 0.70)
PUB_INCOHERENT_ODD   = float(os.environ.get("BF_PUB_INCOHERENT_ODD") or 3.0)


PUB_SHORT_FAV_ODD = float(os.environ.get("BF_PUB_SHORT_FAV_ODD") or 1.35)   # 14.08.2026 (Lucas): 1.50 -> 1.35


def _pub_unconfirmed_fav(a) -> bool:
    """14.08.2026 (Lucas): kurzer Favorit (Geld-Seite < PUB_SHORT_FAV_ODD) OHNE Quoten-Bestaetigung
    (leadDir != 'in') -> erwartbares Favoriten-Geld ohne Rueckhalt, kein Signal. Nur wenn die Quote
    KUERZER wird (Back) darf es ins Public. Galatasaray @1.37 driftet raus; ein backed Favorit bleibt."""
    od = a.get("leadOdd")
    return isinstance(od, (int, float)) and od < PUB_SHORT_FAV_ODD and a.get("leadDir") != "in"


def _pub_incoherent(a) -> bool:
    """Hoher Geld-Anteil (>=70%) AUF einer langen Quote (>=3.0) — % und Preis widersprechen sich
    (85% koennen bei gesundem Markt nicht auf einem @13.50-Longshot liegen) -> Public-Artefakt."""
    sh, od = a.get("leadShare") or 0.0, a.get("leadOdd")
    return sh >= PUB_INCOHERENT_SHARE and isinstance(od, (int, float)) and od >= PUB_INCOHERENT_ODD


def _pub_drift(a) -> bool:
    """16.08.2026 (Lucas, Lens v PSG @1.73 in Public trotz „⚠️ kein Back-Rückhalt"): Geld-Seite driftet
    RAUS (leadDir 'out') = keine Quoten-Bestaetigung, der Preis laeuft GEGEN das Geld. Frueher nur LIVE
    gefiltert — der Vor-Anpfiff-1X2-Fall (PSG 84% @1.73, 1.64->1.73) rutschte durch, weil der Favorit
    ueber PUB_SHORT_FAV_ODD (1.35) lag. Jetzt live UND vor Anpfiff: driftendes Geld gehoert nie ins
    kuratierte Public. Trades sieht es weiter (mit ⚠️-Drift-Hinweis)."""
    return a.get("leadDir") == "out"


# 14.08.2026 (Lucas): HZ-Pushs nur solange die erste Halbzeit LAEUFT und der Ausgang plausibel ist.
# In der Pause (⏸ Halbzeit / is_ht) steht das HZ-Ergebnis praktisch -> zu spaet; Geld auf einen
# HZ-Longshot (Quote > HT_MAX_ODD_PUB) ist ein toter Ausgang, kein Signal. NUR Public.
HT_MAX_ODD_PUB = float(os.environ.get("BF_HT_MAX_ODD_PUB") or 4.0)


def _pub_ht_useless(a) -> bool:
    if a.get("scenario") != "ht":
        return False
    if (a.get("live") or {}).get("is_ht"):
        return True   # Halbzeitpause -> HZ-Ergebnis steht
    od = a.get("leadOdd")
    return isinstance(od, (int, float)) and od > HT_MAX_ODD_PUB


def _live_under_reactive(a) -> bool:
    """15.08.2026 (Lucas): live in-play TORE-Über/Unter (HZ 'First Half Goals X.5' ODER Voll
    'Over/Under X.5 Goals'), Geld auf UNTER = reaktiv. Mit ablaufender Zeit verkürzt sich Unter
    mechanisch, die Quote crasht (Bolton v Preston Under 2.5 @1.35, 2.16->1.35 in Min 70-84) -> die
    'Back'-Bestätigung ist Zeit-Zerfall, KEIN Signal. Über bleibt (echte Tor-Erwartung); HZ-1X2 +
    1X2-Moneyflow + Corners/Cards (kein 'Goals') + Vor-Anpfiff bleiben. Szenario-übergreifend (ht +
    fresh), BEIDE Kanäle (Trades + Public) — reaktives Unter ist überall wertlos (wie der Remis-Chase)."""
    if not _is_live(a):
        return False
    mk = str(a.get("market") or "")
    is_goals_ou = ("First Half Goals" in mk) or ("Over/Under" in mk and "Goals" in mk)
    if not is_goals_ou:
        return False
    lbl = str(a.get("leadLabel") or a.get("leadName") or "").lower()
    return "under" in lbl or "unter" in lbl


def _pub_under_goals(a) -> bool:
    """16.08.2026 (Lucas: „das mit Under haben wir schon 3x gefixt — wie gibt es das"): Der Live-Under-
    Riegel (_live_under_reactive) greift NUR in-play. VOR-Anpfiff-Tore-Über/Unter mit Geld auf UNTER
    (z.B. Girona v Leganes, Under 2.5 @2.04, 30 Min vor Anpfiff) rutschte weiter ins Public. Dieselbe
    Klasse hat über 21 Public-Under-Pushs einen katastrophalen CLV (Ø -17..-24pp): der Push laeuft dem
    schon gecrashten Preis HINTERHER, gewinnt hoechstens auf Varianz (Tore-arm ist haeufig), zahlt aber
    immer den schlechten Preis. Fuer den KURATIERTEN Public-Kanal komplett raus — jedes Tore-Über/Unter
    mit Geld auf UNTER, live ODER vor Anpfiff. Over/Team-Maerkte bleiben (echte Tor-/Sieg-Erwartung).
    Trades (Firehose) sieht Vor-Anpfiff-Under weiter; nur das live GEBACKTE Under faellt dort
    (_trades_reactive_backed_under)."""
    mk = str(a.get("market") or "")
    is_goals_ou = ("First Half Goals" in mk) or ("Over/Under" in mk and "Goals" in mk)
    if not is_goals_ou:
        return False
    lbl = str(a.get("leadLabel") or a.get("leadName") or "").lower()
    return "under" in lbl or "unter" in lbl


def _trades_reactive_backed_under(a) -> bool:
    """15.08.2026 (Lucas, B): NUR Trades — das GEBACKTE reaktive Live-Unter (Quote crasht, leadDir 'in',
    Bolton-Typ) raus. Das DRIFTENDE Unter (leadDir 'out') bleibt in Trades: das ist das Fade-/Lay-Signal
    (Geld auf Under, aber Quote driftet -> Gegenseite will das Tor), das _dir_line als Text ausweist.
    Public entfernt weiterhin ALLES live Unter (_live_under_reactive in der Public-Kette)."""
    return _live_under_reactive(a) and a.get("leadDir") == "in"


# 14.08.2026 (Lucas): eskalierende Wiederhol-Bremse fuers Public. Derselbe Markt muss zum Re-Push das
# Geld nur um DEDUP_FACTOR steigern -> in liquiden Ligen 4-5x Spam. Ab dem 3. Push wird die noetige
# Steigerung hoeher gestaffelt. Zaehler steckt im pub_seen (rueckwaerts-kompatibel: alter float = 1x).
PUB_RESEND_LADDER = [2.0, 3.0, 4.5, 6.0]   # 22.08.2026 (Lucas): 1->2 von 1.5 auf 2.0 gehaertet (grosse Ligen werden geflutet)


def _pub_seen_rec(rec):
    if isinstance(rec, (int, float)):
        return float(rec), 1
    if isinstance(rec, dict):
        return float(rec.get("v") or 0.0), int(rec.get("n") or 1)
    return 0.0, 0


def should_send_public(seen, key, value) -> bool:
    rec = seen.get(key)
    if rec is None:
        return True
    prev_v, n = _pub_seen_rec(rec)
    factor = PUB_RESEND_LADDER[min(max(n, 1) - 1, len(PUB_RESEND_LADDER) - 1)]
    try:
        return value >= prev_v * factor
    except Exception:
        return True


def _pub_seen_put(seen, key, value) -> None:
    _, n = _pub_seen_rec(seen.get(key))
    seen[key] = {"v": value, "n": n + 1}


def _pub_skip_resend(a, pub_seen) -> bool:
    """15.08.2026 (Lucas): live ODER Halbzeit-Geld -> nur EIN Public-Push pro Spiel. Ein bereits
    gesendetes Live-Spiel bzw. HZ-Signal NICHT erneut pushen, auch wenn das Volumen weiter waechst
    (Norwich live 2. mal @1.5x; Guabira HZ 15K->23.3K @1.55x, Vor-Anpfiff). Vor-Anpfiff-FRISCH
    (1X2-Moneyflow) behält die eskalierende Wiederhol-Leiter (Galatasaray-Staffelung)."""
    if not (_is_live(a) or a.get("scenario") == "ht"):
        return False
    return pub_seen.get(a["scenario"] + ":" + a["matchId"]) is not None


def collect_alerts(prices: dict, hist: dict, ht_top=HT_TOP_EUR, ht_rest=HT_REST_EUR,
                   fresh_top=FRESH_TOP_EUR, fresh_rest=FRESH_REST_EUR) -> list:
    out = []
    for m in (prices.get("matches") or []):
        a = ht_alert(m, ht_top, ht_rest)
        if a:
            out.append(a)
        f = fresh_alert(m, hist, fresh_top, fresh_rest)
        # 18.08.2026 (Lucas): kein zweiter fast identischer Push. Betrifft der frische Zufluss (fresh)
        # DENSELBEN Markt wie das HZ-Geld-Signal (ht), MERGEN wir ihn IN die blaue HT-Nachricht (blaue
        # Kugel = HT sofort erkennbar; Zufluss als eigene 💶-Zeile) statt eine zweite gelbe zu schicken.
        # Auf einem ANDEREN Markt bleibt fresh eigenstaendig (z.B. 1X2-Zufluss neben HZ-O/U-Geld).
        if f:
            if a and f.get("market") == a.get("market"):
                a["freshMerge"] = f
            else:
                out.append(f)
        # 21.08.2026 (Lucas): Fix-Verdacht (⚫) — HZ-Geld > FT-Geld. Eigenes Szenario, eigener Dedup-Key.
        x = fix_alert(m)
        if x:
            out.append(x)
    return out


def main():
    try:
        prices = json.load(open("betfair_prices.json", encoding="utf-8"))
    except Exception as e:
        print("betfair_prices.json fehlt/kaputt:", e)
        return
    try:
        hist = json.load(open("betfair_history.json", encoding="utf-8"))
    except Exception:
        hist = {}
    seen = _load_seen(SEEN_FILE)

    try:
        direction = json.load(open(DIRECTION_FILE, encoding="utf-8"))
        if not isinstance(direction, dict):
            direction = {}
    except Exception:
        direction = {}

    cidx = _consensus_index()   # 09.08.2026 (Lucas): Zweitmeinung an den Trades-Frisch-Push
    # 09.08.2026 (Lucas): Nach Quotensprung (Tor) lief das Geld zur Quote DAVOR — lag die unter der
    # Mindest-Quote, gehoert die Push gar nicht raus (auch Trades). _drop_subthreshold_jump filtert das.
    alerts = _drop_subthreshold_jump(_leader_gate(attach_direction(collect_alerts(prices, hist), direction)))
    # 14.08.2026 (Lucas): kollabiertes In-Play-Remis (X<2.2) auch aus TRADES raus — eh wertlos
    # (-31..-79% ROI). Bisher nur Public gefiltert. Andere Draws (>2.2) + Nicht-Draws bleiben (mit Warn-Note).
    alerts = [a for a in alerts if not _draw_inplay_chase(a) and not _trades_reactive_backed_under(a)]
    sent = 0
    for a in alerts:
        key = a["scenario"] + ":" + a["matchId"]
        if a["scenario"] == "fresh" and not _fresh_cooldown_ok(seen, a["matchId"]):
            continue   # 22.08.2026 (Lucas): kein zweiter Fresh-Push binnen FRESH_COOLDOWN_MIN
        if should_send(seen, key, a["value"]):
            # 09.08.2026 (Lucas): Trades-„Frisches Geld" jetzt im Public-Format (Geld-Leiste + %, auch <80%)
            # PLUS die Zweitmeinung der anderen Quellen. HT bleibt beim kompakten Format.
            msg = (build_public_message(a, trades=True) + _consensus_block(a, cidx)) if a["scenario"] == "fresh" else build_message(a)
            if send_trades_message(msg):
                seen[key] = a["value"]     # nur bei Erfolg merken (Preview/Fehler → nächster Lauf retry)
                if a["scenario"] == "fresh":
                    _fresh_cooldown_mark(seen, a["matchId"])
                sent += 1
    _save_seen(SEEN_FILE, seen)
    print("Betfair-Alerts: %d Kandidaten, %d gesendet" % (len(alerts), sent))

    # 🟡 Öffentlicher Moneyflow (kuratierte, höhere Schwellen) → CocoBet-Community-Channel.
    # Eigener Dedup-State, damit die höhere Public-Schwelle unabhängig vom Trades-Channel greift.
    pub_seen = _load_seen(PUB_SEEN_FILE)
    pub_alerts = _leader_gate(attach_direction(
        collect_alerts(prices, hist, PUB_HT_TOP, PUB_HT_REST, PUB_FRESH_TOP, PUB_FRESH_REST), direction),
        PUB_HT_TOP, PUB_HT_REST, PUB_FRESH_TOP, PUB_FRESH_REST)
    # (Lucas 05.08.2026) Public-Kuratierung: frisches Geld nur pushen, wenn es klar einseitig ist
    # (>=PUB_FRESH_MIN_SHARE auf einer Seite) — reines Volumen ohne Richtung raus. HT hat schon sein
    # 85%-Gate; Trades bleibt ungefiltert (obskure Ligen bewusst drin — dort oft Sharp Money).
    pub_alerts = [a for a in pub_alerts
                  if a.get("scenario") != "fresh" or (a.get("leadShare") or 0.0) >= PUB_FRESH_MIN_SHARE]
    pub_alerts = [a for a in pub_alerts if a.get("scenario") != "fix"]   # 21.08.2026 (Lucas): Fix-Verdacht NUR Trades, nie Public
    # (Lucas 09.08.2026) NUR Public: nach einem Spielereignis (Tor/Karte) neu bepreiste Maerkte raus.
    # Wenn die Quote gerade durch ein Tor gesprungen ist (_dir_event_jump), ist die Richtung unklar und
    # der Push reaktiv/gewagt - nichts fuer den oeffentlichen Kanal. Trades sieht ihn weiter (mit Richtung-
    # unklar-Hinweis). Greift nur, wenn wir die Richtung tatsaechlich haben (sonst ist kein Sprung erkennbar).
    pub_alerts = [a for a in pub_alerts if not _dir_event_jump(a)]
    # (Lucas 13.08.2026, Audit) NUR Public: In-Play-Draw-Nachlauf zur kollabierten X-Quote raus -
    # backen verliert dort real (-31..-79% ROI). Pre-Match-Draw und andere Seiten bleiben; Trades sieht es weiter.
    pub_alerts = [a for a in pub_alerts if not _draw_inplay_chase(a)]
    # 14.08.2026 (Lucas): unnoetige HT/Live-Pushs raus, wo die Geld-% der Quote widersprechen
    # (Galatasaray 85%@13.50; Wolves Under 87% aber Quote driftet). Trades sieht sie weiter.
    pub_alerts = [a for a in pub_alerts if not _pub_incoherent(a) and not _pub_drift(a) and not _pub_ht_useless(a) and not _pub_unconfirmed_fav(a) and not _pub_under_goals(a)]   # 16.08.2026 (Lucas): Under-Tore aus Public, live UND vor Anpfiff
    pub_sent = 0
    for a in pub_alerts:
        key = a["scenario"] + ":" + a["matchId"]
        if _pub_skip_resend(a, pub_seen):
            continue   # 15.08.2026 (Lucas): live nur EIN Public-Push pro Spiel
        if a["scenario"] == "fresh" and not _fresh_cooldown_ok(pub_seen, a["matchId"]):
            continue   # 22.08.2026 (Lucas): kein zweiter Fresh-Push binnen FRESH_COOLDOWN_MIN
        if should_send_public(pub_seen, key, _lead_magnitude(a)):   # 16.08.2026 (Lucas): Zufluss, nicht das wachsende Gesamtvolumen
            # 13.08.2026 (Lucas): Zweitmeinung (Pinnacle/Soft/Poly) auch im Public — wie im Trades-Push (nur fresh).
            pub_msg = build_public_message(a) + (_consensus_block(a, cidx) if a["scenario"] == "fresh" else "")
            if _tg_public(pub_msg):
                _pub_seen_put(pub_seen, key, _lead_magnitude(a))
                if a["scenario"] == "fresh":
                    _fresh_cooldown_mark(pub_seen, a["matchId"])
                pub_sent += 1
                _log_public_push(a, cidx)   # fürs Tracking/Auswerten (+ Konsens-Zweitmeinung)
    _save_seen(PUB_SEEN_FILE, pub_seen)
    print("Betfair Public-Moneyflow: %d Kandidaten, %d gesendet" % (len(pub_alerts), pub_sent))


if __name__ == "__main__":
    main()
