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
JUMP_REL = 0.40   # 08.08.2026 (Lucas, Viking-Fall 1.23->3.60 nach 1:1): springt die Quote zwischen zwei
                  # Scans um >= 40%, ist das fast sicher ein Spielereignis (Tor/Karte), KEIN Order-Flow.
                  # Ueber so einen Sprung ist die Back/Lay-Lesart nicht gueltig (der Sprung ist mechanisch,
                  # nicht von Backern/Layern) -> Richtung "unklar" statt eines falschen Back-/Lay-Urteils.
                  # Gilt in BEIDE Richtungen: ein Tor kann die Quote auch crashen und ein falsches "Back" faken.

HT_TOP_EUR     = 10000.0  # Halbzeit-Geld-Schwelle Top-Liga + International (Lucas 30.07.2026)
HT_REST_EUR    = 5000.0   # ... und Rest-Ligen
HT_MIN_SHARE   = 0.85     # ... und davon min. dieser Anteil auf EINEN Ausgang (einseitig)
MIN_LEAD_ODD   = 1.30     # Geld auf einen Favoriten mit Quote < 1.30 (führt schon, wenig Value) = kein Push (Lucas 30.07.2026, vorher 1.15)
FRESH_TOP_EUR  = 30000.0  # frisches Geld Top-Liga
FRESH_REST_EUR = 20000.0  # ... und Rest-Ligen
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
    return {"scenario": "fresh", "matchId": str(m.get("matchId")), "value": mkt_total,
            "home": m.get("home"), "away": m.get("away"), "league": m.get("league"), "flag": _flag(m),
            "market": market_name, "inflow": inflow, "total": mkt_total, "tier": tier_of(m),
            "kickoff": m.get("kickoff"), "live": m.get("liveInfo") or {},
            "leadName": lead_name, "leadShare": lead_share, "leadOdd": lead_odd, "onLeader": on_leader}


def _dir_event_jump(a) -> bool:
    """08.08.2026 (Lucas): Sprang die Favoriten-Quote zwischen den beiden verglichenen Scans um >= JUMP_REL,
    ist das ein Spielereignis (Tor/Karte), kein Order-Flow -> die Back/Lay-Lesart ist ungueltig."""
    prev, odd = a.get("leadPrev"), a.get("leadOdd")
    try:
        if prev and odd:
            return abs(float(odd) - float(prev)) / float(prev) >= JUMP_REL
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return False


def _dir_line(a) -> str:
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


def build_message(a) -> str:
    head = ("%s <b>%s</b> v <b>%s</b>\n<i>%s</i>\n"
            % (a["flag"], _esc(a["home"]), _esc(a["away"]), _esc(str(a["league"])[:48])))
    if a["scenario"] == "ht":
        odd = (" @%.2f" % a["leadOdd"]) if isinstance(a.get("leadOdd"), (int, float)) else ""
        lbl = a.get("mktLabel") or "HZ"
        msg = ("🔵 <b>Betfair · Halbzeit-Geld (einseitig)</b>\n" + head   # 31.07.2026 (Lucas): blaue Kugel fuer HZ = schneller erkennbar; Frisches Geld bleibt gelb
               + "💷 %s: <b>%s</b> gematcht · <b>%.0f%%</b> auf %s%s"
                 % (_esc(lbl), _euro(a["total"]), a["leadShare"] * 100, _esc(a["leadLabel"]), odd))
        if a.get("isX2"):
            pct = lambda x: "—" if x is None else "%.0f%%" % (x * 100)
            msg += ("\n%s %s · X %s · %s %s" % (_esc(a["home"]), pct(a["hs"]), pct(a["ds"]),
                                                _esc(a["away"]), pct(a["as_"])))
        return msg + _fuehrt_line(a) + _dir_line(a)
    tl = "Top-Liga" if a["tier"] == "top" else "Rest-Liga"
    msg = ("🟡 <b>Betfair · Frisches Geld</b> · %s\n" % tl + head
           + "💶 <b>%s</b>: +<b>%s</b> frisch → jetzt <b>%s</b>"
             % (_esc(_short_mk(a["market"])), _euro(a["inflow"]), _euro(a["total"])))
    if a.get("leadName"):
        odd = (" @%.2f" % a["leadOdd"]) if isinstance(a.get("leadOdd"), (int, float)) else ""
        msg += "\nführt: %s (%.0f%%)%s" % (_esc(a["leadName"]), (a.get("leadShare") or 0.0) * 100, odd)
    return msg + _fuehrt_line(a) + _dir_line(a)


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


def build_public_message(a) -> str:
    """Oeffentliches Format (05.08.2026, Lucas: schoener + informativer): Anpfiff/Live-Status +
    Spielstand, Zufluss-Anteil am Markt, visuelle Geld-Leiste, Quote. Telegram-HTML (b/i, Unicode)."""
    league = _esc(str(a.get("league") or "")[:60])
    status = _flow_status(a)
    status_line = ("\n" + status) if status else ""
    teams = ("%s <b>%s</b> v <b>%s</b>\n🏆 <i>%s</i>%s"
             % (a["flag"], _esc(a["home"]), _esc(a["away"]), league, status_line))
    odd = (" @%.2f" % a["leadOdd"]) if isinstance(a.get("leadOdd"), (int, float)) else ""

    live_badge = "🔴 <b>LIVE</b> · " if _is_live(a) else ""
    if a["scenario"] == "ht":
        share = a.get("leadShare") or 0.0
        return (live_badge + "🔵 <b>Betfair Halftime Flow</b>\n\n" + teams + "\n\n"
                + "💷 <b>%s</b> — Halbzeit-Geld\n<b>%s</b> gematcht\n\n"
                  % (_esc(_short_mk(a["market"])), _euro(a["total"]))
                + "📊 <b>%s</b>  %s %.0f%%%s"
                  % (_esc(a["leadLabel"]), _bar(share), share * 100, odd)
                + _fuehrt_line(a) + _dir_line(a))

    share = a.get("leadShare") or 0.0
    total = a.get("total") or 0.0
    inflow = a.get("inflow") or 0.0
    pct = (" (%.0f%% frisch)" % (inflow / total * 100)) if total else ""
    lead = a.get("leadName") or "—"
    return (live_badge + "🟡 <b>Betfair Moneyflow</b>\n\n" + teams + "\n\n"
            + "💶 <b>%s</b> — frischer Zufluss\n+<b>%s</b> → Markt <b>%s</b>%s\n\n"
              % (_esc(_short_mk(a["market"])), _euro(inflow), _euro(total), pct)
            + "📊 <b>%s</b>  %s %.0f%%%s"
              % (_esc(lead), _bar(share), share * 100, odd)
            + _fuehrt_line(a) + _dir_line(a))


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


def _log_public_push(a) -> None:
    """Jeden GESENDETEN Public-Push in betfair_public_ledger.json festhalten → betfair_public_eval.py
    rechnet ihn später gegen den Endstand ab. Ein Eintrag je Spiel+Szenario+Markt (kein Doppelzählen)."""
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
                "status": "pending", "htScore": None})
    try:
        json.dump(led[-800:], open(PUB_LEDGER_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    except Exception as e:
        print("Public-Ledger-Schreibfehler:", e)


def collect_alerts(prices: dict, hist: dict, ht_top=HT_TOP_EUR, ht_rest=HT_REST_EUR,
                   fresh_top=FRESH_TOP_EUR, fresh_rest=FRESH_REST_EUR) -> list:
    out = []
    for m in (prices.get("matches") or []):
        a = ht_alert(m, ht_top, ht_rest)
        if a:
            out.append(a)
        f = fresh_alert(m, hist, fresh_top, fresh_rest)
        if f:
            out.append(f)
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
    try:
        seen = json.load(open(SEEN_FILE, encoding="utf-8"))
    except Exception:
        seen = {}

    try:
        direction = json.load(open(DIRECTION_FILE, encoding="utf-8"))
        if not isinstance(direction, dict):
            direction = {}
    except Exception:
        direction = {}

    alerts = _leader_gate(attach_direction(collect_alerts(prices, hist), direction))
    sent = 0
    for a in alerts:
        key = a["scenario"] + ":" + a["matchId"]
        if should_send(seen, key, a["value"]):
            if send_trades_message(build_message(a)):
                seen[key] = a["value"]     # nur bei Erfolg merken (Preview/Fehler → nächster Lauf retry)
                sent += 1
    try:
        json.dump(seen, open(SEEN_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    except Exception as e:
        print("konnte Seen-State nicht schreiben:", e)
    print("Betfair-Alerts: %d Kandidaten, %d gesendet" % (len(alerts), sent))

    # 🟡 Öffentlicher Moneyflow (kuratierte, höhere Schwellen) → CocoBet-Community-Channel.
    # Eigener Dedup-State, damit die höhere Public-Schwelle unabhängig vom Trades-Channel greift.
    try:
        pub_seen = json.load(open(PUB_SEEN_FILE, encoding="utf-8"))
    except Exception:
        pub_seen = {}
    pub_alerts = _leader_gate(attach_direction(
        collect_alerts(prices, hist, PUB_HT_TOP, PUB_HT_REST, PUB_FRESH_TOP, PUB_FRESH_REST), direction),
        PUB_HT_TOP, PUB_HT_REST, PUB_FRESH_TOP, PUB_FRESH_REST)
    # (Lucas 05.08.2026) Public-Kuratierung: frisches Geld nur pushen, wenn es klar einseitig ist
    # (>=PUB_FRESH_MIN_SHARE auf einer Seite) — reines Volumen ohne Richtung raus. HT hat schon sein
    # 85%-Gate; Trades bleibt ungefiltert (obskure Ligen bewusst drin — dort oft Sharp Money).
    pub_alerts = [a for a in pub_alerts
                  if a.get("scenario") != "fresh" or (a.get("leadShare") or 0.0) >= PUB_FRESH_MIN_SHARE]
    # (Lucas 09.08.2026) NUR Public: nach einem Spielereignis (Tor/Karte) neu bepreiste Maerkte raus.
    # Wenn die Quote gerade durch ein Tor gesprungen ist (_dir_event_jump), ist die Richtung unklar und
    # der Push reaktiv/gewagt - nichts fuer den oeffentlichen Kanal. Trades sieht ihn weiter (mit Richtung-
    # unklar-Hinweis). Greift nur, wenn wir die Richtung tatsaechlich haben (sonst ist kein Sprung erkennbar).
    pub_alerts = [a for a in pub_alerts if not _dir_event_jump(a)]
    pub_sent = 0
    for a in pub_alerts:
        key = a["scenario"] + ":" + a["matchId"]
        if should_send(pub_seen, key, a["value"]):
            if _tg_public(build_public_message(a)):
                pub_seen[key] = a["value"]
                pub_sent += 1
                _log_public_push(a)   # fürs Tracking/Auswerten (betfair_public_eval.py)
    try:
        json.dump(pub_seen, open(PUB_SEEN_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    except Exception as e:
        print("konnte Public-Seen nicht schreiben:", e)
    print("Betfair Public-Moneyflow: %d Kandidaten, %d gesendet" % (len(pub_alerts), pub_sent))


if __name__ == "__main__":
    main()
