#!/usr/bin/env python3
"""
poly_data_integrity.py — Ausgabe-Korrektheits-Batterie für die Polymarket-Seite.

Lucas' Skepsis (02.08.2026): „ich bin skeptisch dass das ganze Zeug überhaupt
funktioniert … wird noch mehr falsch sein, nur wir merkens nicht, und die 100
Guards merkens auch nicht." — genau richtig: die WM/Liga-Pinnacle-Seite ist mit
53 Guards hart abgesichert (wm_data_integrity.py), die POLY-Seite hatte NULL
Ausgabe-Checks. Vier der fünf stillen Bugs, die wir zufällig fanden, waren
Poly-seitig (Settlement-Key-Mismatch, Geister-Steam, still toter Shortlist-
Emitter, „bewiesene" Wallets netto-negativ).

Diese Batterie prüft NICHT, ob eine Zahl schön ist, sondern ob die Poly-Maschine
ihren JOB tut: Kommt frisches Geld rein? Werden Märkte abgerechnet? Schreibt der
Paper-Tracker? Sind „bewiesene" Wallets wirklich im Plus? Matchen unsere Keys die
Auflösungen? Jeder Check ist so gebaut, dass er GENAU DANN feuert, wenn etwas
still kaputt geht — nicht wenn es nur ungewohnt aussieht.

Ergebnis wird nach poly_status.json geschrieben (gleiches {checks:[…], nFail}-
Schema wie wm_status.json) und von der Status-Seite unter „🐋 Polymarket" als
🔴/🟡/✅-Zeilen gerendert.

═══════════════════════════════════════════════════════════════════════════════
  NEUEN POLY-GUARD HINZUFÜGEN:
    1. Funktion mit @poly_check dekorieren, ctx nutzen, _chk(...) zurückgeben.
    2. Fertig — erscheint automatisch in poly_status.json + Status-Seite.
    ctx hat: .now .close .resolutions .wallet_track .shortlist .broad
             .cross_sport .trader  + Helfer ctx.age_h(ts_str).
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent

# ── Datei-Namen (alle read-only außer poly_status.json) ─────────────────────
CLOSE_FILE      = "poly_money_broad_close.json"     # {key:{prices,league,capturedAt,hoursToKickoff,…}}
RES_FILE        = "poly_resolutions.json"           # {key:{winner,ts}}
WALLET_FILE     = "poly_wallet_track.json"          # {open,scores:{addr:{n,wins,usd,pnl?}},updatedAt}
SHORTLIST_FILE  = "poly_shortlist_track.json"       # {updatedAt,open,settled,agg,stake}
BROAD_FILE      = "poly_money_broad.json"           # {generatedAt,n,rows,byLeague,…}
CROSS_FILE      = "poly_cross_sport.json"           # {generatedAt,…}
TRADER_FILE     = "poly_trader_data.json"           # {updated,candidates}
STATUS_FILE     = "poly_status.json"                # ← Ausgabe

# ── Schwellen (Scan läuft alle 30 Min via poly-global-scan.yml, self-hosted Mac) ─
FRESH_WARN_H     = float(os.environ.get("POLY_FRESH_WARN_H")   or 3)    # frisch erwartet < 3 h
FRESH_ERR_H      = float(os.environ.get("POLY_FRESH_ERR_H")    or 12)   # > 12 h = Feed tot
LAG_WARN_H       = float(os.environ.get("POLY_LAG_WARN_H")     or 2.5)  # Tracker darf Scan so weit nachlaufen
KICKOFF_GRACE_H  = float(os.environ.get("POLY_KICKOFF_GRACE_H")or 6)    # ab so vielen h nach Anpfiff „sollte aufgelöst sein"
STALE_OPEN_DAYS  = float(os.environ.get("POLY_STALE_OPEN_DAYS")or 3)    # offene Paper-Position älter → hängt
GHOST_SHARE_FLOOR = float(os.environ.get("POLY_GHOST_SHARE_FLOOR")or 0.5) # >so viel der Live-Geld-Märkte schon durch = Feed voller Geister
GHOST_MIN_N      = int(os.environ.get("POLY_GHOST_MIN_N")     or 20)    # erst ab so vielen Geld-Märkten bewerten
OVERLAP_FLOOR    = float(os.environ.get("POLY_OVERLAP_FLOOR")  or 0.60) # Auflösungs-Trefferquote je Liga
OVERLAP_MIN_N    = int(os.environ.get("POLY_OVERLAP_MIN_N")    or 8)    # Liga erst ab so vielen fälligen Keys bewerten
PROVEN_MIN_TR    = int(os.environ.get("POLY_PROVEN_MIN_TR")    or 3)    # = poly_whale_watch MIN_TR
PROVEN_MIN_HIT   = float(os.environ.get("POLY_PROVEN_MIN_HIT") or 0.50) # = poly_whale_watch MIN_HITRATE
PROVEN_NEG_FLOOR = float(os.environ.get("POLY_PROVEN_NEG_FLOOR")or 0.25)# Anteil netto-negativer „bewiesener" Wallets, ab dem es gelb wird
BACKTEST_MIN_N   = int(os.environ.get("POLY_BACKTEST_MIN_N")   or 30)   # Genauigkeits-Stichprobe darf nicht kollabieren


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_ts(t):
    if not isinstance(t, str) or not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except Exception:
        return None


def _league_of(key, fallback=None):
    if fallback:
        return str(fallback).upper()
    m = re.match(r"^([a-z0-9]+)-", str(key or ""))
    if not m:
        return "?"
    tag = m.group(1).lower()
    _MAP = {"cs2": "ESPORTS", "lol": "ESPORTS", "dota2": "ESPORTS", "dota": "ESPORTS",
            "val": "ESPORTS", "valorant": "ESPORTS", "atp": "TENNIS", "wta": "TENNIS"}
    return _MAP.get(tag, tag.upper())


def _chk(cid, label, severity, failures, note=""):
    """Exakt das Schema von wm_data_integrity._chk — die Status-Seite rendert es 1:1."""
    failures = list(failures)
    return {"id": cid, "label": label, "severity": severity,
            "ok": len(failures) == 0, "nFail": len(failures),
            "failures": failures[:25], "note": note}


class PolyCtx:
    """Einmal gebaut, an jeden Guard gereicht. Alles bereits geladen/getrimmt."""
    def __init__(self, now=None, close=None, resolutions=None, wallet_track=None,
                 shortlist=None, broad=None, cross_sport=None, trader=None):
        self.now = now or datetime.now(timezone.utc)
        self.close = close if isinstance(close, dict) else {}
        self.resolutions = resolutions if isinstance(resolutions, dict) else {}
        self.wallet_track = wallet_track if isinstance(wallet_track, dict) else {}
        self.shortlist = shortlist if isinstance(shortlist, dict) else {}
        self.broad = broad if isinstance(broad, dict) else {}
        self.cross_sport = cross_sport if isinstance(cross_sport, dict) else {}
        self.trader = trader if isinstance(trader, dict) else {}

    def age_h(self, ts_str):
        """Alter in Stunden eines ISO-Zeitstempels; None wenn nicht parsbar."""
        t = _parse_ts(ts_str)
        if t is None:
            return None
        return (self.now - t).total_seconds() / 3600.0

    def newest_close_capture(self):
        caps = [_parse_ts(v.get("capturedAt")) for v in self.close.values()
                if isinstance(v, dict)]
        caps = [c for c in caps if c]
        return max(caps) if caps else None


# ── Registry ─────────────────────────────────────────────────────────────────
POLY_CHECKS = []
def poly_check(fn):
    POLY_CHECKS.append(fn)
    return fn


def _fresh_fail(age_h, label_ts):
    """Gemeinsame Frisch-Logik: liefert (failures, severity)."""
    if age_h is None:
        return ([f"kein/kaputter Zeitstempel ({label_ts})"], "error")
    if age_h > FRESH_ERR_H:
        return ([f"jüngster Stand vor {age_h:.1f} h (> {FRESH_ERR_H:.0f} h → Feed steht)"], "error")
    if age_h > FRESH_WARN_H:
        return ([f"jüngster Stand vor {age_h:.1f} h (> {FRESH_WARN_H:.0f} h erwartet)"], "warn")
    return ([], "error")


# ── Die Guards ────────────────────────────────────────────────────────────────
@poly_check
def check_close_feed_fresh(ctx):
    """Kommt überhaupt frisches Geld rein? Der Close-Feed (poly_money_broad_close) ist die
    Referenz für JEDEN Einstiegs-/Schlusspreis (CLV, Paper-Track, Whale-Volumen). Steht er,
    ist die halbe Poly-Seite blind — ohne dass irgendwo ein Fehler geloggt würde."""
    newest = ctx.newest_close_capture()
    age = None if newest is None else (ctx.now - newest).total_seconds() / 3600.0
    fails, sev = _fresh_fail(age, "capturedAt")
    if fails:
        fails = [f"Close-Feed: {fails[0]} · {len(ctx.close)} Märkte im File"]
    return _chk("close_feed_fresh", "Close-Feed frisch (frisches Geld kommt rein)", sev, fails,
                "Jüngster erfasster Markt. Scan alle 30 Min — steht der Feed, sind Preise/CLV/Volumen alt.")


@poly_check
def check_resolutions_fresh(ctx):
    """Werden Märkte überhaupt noch abgerechnet? poly_resolutions treibt jede Settlement
    (Wallet-Track, Paper-Track, Genauigkeits-Backtest). Friert der Auflösungs-Feed ein,
    bleibt ALLES auf 'offen' stehen — und keine Trefferquote wird je wieder besser."""
    ts = [_parse_ts(v.get("ts")) for v in ctx.resolutions.values() if isinstance(v, dict)]
    ts = [t for t in ts if t]
    newest = max(ts) if ts else None
    age = None if newest is None else (ctx.now - newest).total_seconds() / 3600.0
    fails, sev = _fresh_fail(age, "ts")
    if fails:
        fails = [f"Auflösungs-Feed: {fails[0]} · {len(ctx.resolutions)} Auflösungen gesamt"]
    return _chk("resolutions_fresh", "Auflösungs-Feed lebt (Märkte werden abgerechnet)", sev, fails,
                "Jüngste Markt-Auflösung. Friert er ein, bleiben alle Positionen ewig offen.")


@poly_check
def check_wallet_track_fresh(ctx):
    """Das Wallet-Lernen (poly_wallet_track) ist die Basis jeder 'bewiesene Wallet'-Aussage im
    Trades- und Public-Channel. Veraltet es, pushen wir Wallets auf Grundlage alter Bilanzen."""
    age = ctx.age_h(ctx.wallet_track.get("updatedAt"))
    fails, sev = _fresh_fail(age, "updatedAt")
    n_scores = len(ctx.wallet_track.get("scores") or {})
    if fails:
        fails = [f"Wallet-Track: {fails[0]} · {n_scores} Wallets bewertet"]
    return _chk("wallet_track_fresh", "Wallet-Lernen frisch", sev, fails,
                "Grundlage der 'bewiesene Wallet'-Pushes — veraltet = Pushes auf alten Bilanzen.")


@poly_check
def check_shortlist_tracker_writes(ctx):
    """🔴 GENAU DER STILLE BUG, den wir gefunden haben: poly_shortlist_track.py läuft im Scan
    mit, aber der node/jsdom-Emitter kann still None liefern → Track-File bleibt unangetastet.
    Symptom: der Scan-Feed ist frisch, der Tracker hängt Stunden zurück UND rechnet nie ab.
    Der Check feuert, wenn der Tracker dem frischen Scan hinterherhinkt oder 0 Plays hält."""
    fails = []
    upd = ctx.shortlist.get("updatedAt")
    t_age = ctx.age_h(upd)
    newest_close = ctx.newest_close_capture()
    close_age = None if newest_close is None else (ctx.now - newest_close).total_seconds() / 3600.0
    n_open = len(ctx.shortlist.get("open") or {})
    n_settled = len(ctx.shortlist.get("settled") or [])
    feed_fresh = close_age is not None and close_age <= FRESH_WARN_H
    if t_age is None:
        fails.append("Tracker hat keinen/kaputten Zeitstempel — läuft er überhaupt?")
    elif feed_fresh and t_age is not None and (t_age - close_age) > LAG_WARN_H:
        fails.append(f"Tracker {t_age:.1f} h alt, Scan-Feed nur {close_age:.1f} h → "
                     f"Emitter liefert seit {t_age - close_age:.1f} h nichts (still tot?)")
    if feed_fresh and n_open == 0 and n_settled == 0:
        fails.append("Feed frisch, aber Tracker hat 0 offene UND 0 abgerechnete Plays — Emitter liefert 0")
    sev = "error"
    return _chk("shortlist_tracker_writes", "Shortlist-Paper-Tracker schreibt", sev, fails,
                "Der Emitter (node/jsdom) kann still ausfallen. Hinkt der Tracker dem frischen Scan "
                "nach, schreibt er nicht — die Auto-Bet-Entscheidung liefe auf Blindflug.")


@poly_check
def check_settlement_alive(ctx):
    """Offene Paper-Positionen, deren Spiel längst gelaufen ist, die aber nie abrechnen — das
    Settlement-Key-Mismatch-Symptom (die 10/10-Hanwha-Wette gewann, blieb aber offen, weil sie
    unter einem anderen Slug auflöste). Feuert je Play, dessen Markt-Datum > N Tage zurückliegt."""
    fails = []
    open_pl = ctx.shortlist.get("open") or {}
    for ok, e in open_pl.items():
        if not isinstance(e, dict):
            continue
        key = e.get("key", "")
        m = re.search(r"(\d{4}-\d{2}-\d{2})$", str(key))
        ref = None
        if m:
            ref = _parse_ts(m.group(1) + "T00:00:00+00:00")
        if ref is None:
            ref = _parse_ts(e.get("firstTs"))
        if ref is None:
            continue
        age_d = (ctx.now - ref).total_seconds() / 86400.0
        if age_d > STALE_OPEN_DAYS:
            has_res = key in ctx.resolutions
            fails.append(f"{key}: seit {age_d:.1f} Tagen offen"
                         + (" — Auflösung existiert, matcht aber den Key nicht!" if has_res
                            else " — keine Auflösung gefunden"))
    return _chk("settlement_alive", "Settlement lebt (keine ewig offenen Positionen)", "error", fails,
                f"Paper-Positionen älter als {STALE_OPEN_DAYS:.0f} Tage, die nie abrechnen = "
                "Settlement-Key-Mismatch (Markt löst unter anderem Slug auf).")


@poly_check
def check_resolutions_match_open_keys(ctx):
    """Matchen unsere Markt-Keys die Auflösungen? Je Liga: von den Keys, die längst angepfiffen
    haben (capturedAt + hoursToKickoff + Karenz < jetzt), wie viele finden ihre Auflösung? Bei
    39 % Esports/16 % Tennis läuft die Hälfte unserer Settlements ins Leere. Genau die Ligen,
    auf denen die aktuelle Shortlist steht (E-Sport)."""
    from collections import Counter
    total = Counter(); ok = Counter()
    for k, v in ctx.close.items():
        if not isinstance(v, dict):
            continue
        cap = _parse_ts(v.get("capturedAt")); htk = v.get("hoursToKickoff")
        if cap is None or not isinstance(htk, (int, float)):
            continue
        ko = cap + timedelta(hours=htk)
        if (ctx.now - ko).total_seconds() / 3600.0 <= KICKOFF_GRACE_H:
            continue                                    # noch nicht (sicher) fällig
        lg = _league_of(k, v.get("league"))
        total[lg] += 1
        if k in ctx.resolutions:
            ok[lg] += 1
    fails = []
    for lg, n in sorted(total.items(), key=lambda kv: -kv[1]):
        if n < OVERLAP_MIN_N:
            continue
        rate = ok[lg] / n
        if rate < OVERLAP_FLOOR:
            fails.append(f"{lg}: nur {ok[lg]}/{n} fällige Märkte aufgelöst ({rate*100:.0f}%)")
    return _chk("resolutions_match_open_keys", "Auflösungen matchen unsere Keys", "warn", fails,
                f"Fällige Märkte je Liga, die ihre Auflösung finden. < {OVERLAP_FLOOR*100:.0f}% = "
                "Settlement läuft ins Leere (Slug-Mismatch), Trefferquoten dieser Liga sind unvollständig.")


@poly_check
def check_proven_wallets_profitable(ctx):
    """Sind 'bewiesene' Wallets (n≥Schwelle & Trefferquote≥50 %, exakt das Whale-Push-Kriterium)
    wirklich im Plus? Nein: bei bekanntem P&L sind ~39 % netto-negativ — hohe Trefferquote,
    aber klein gewinnen / groß verlieren. Der Confirmed-Loser-Gate hilft nur, wenn P&L bekannt
    ist — für die meisten Wallets fehlt er. Der Check macht beide Lecks sichtbar."""
    scores = (ctx.wallet_track.get("scores") or {})
    proven = []
    for addr, s in scores.items():
        if not isinstance(s, dict):
            continue
        n = s.get("n") or 0
        hit = (s.get("wins") or 0) / n if n else 0.0
        if n >= PROVEN_MIN_TR and hit >= PROVEN_MIN_HIT:
            proven.append((addr, s, hit))
    with_pnl = [(a, s, h) for a, s, h in proven if isinstance(s.get("pnl"), (int, float))]
    neg = [(a, s, h) for a, s, h in with_pnl if s["pnl"] < 0]
    fails = []
    if with_pnl:
        share = len(neg) / len(with_pnl)
        if share > PROVEN_NEG_FLOOR:
            fails.append(f"{len(neg)}/{len(with_pnl)} 'bewiesene' Wallets mit bekanntem P&L sind "
                         f"netto-NEGATIV ({share*100:.0f}%) — Trefferquote allein trügt")
            for a, s, h in sorted(neg, key=lambda x: x[1]["pnl"])[:4]:
                fails.append(f"   {a[:12]}… n={s['n']} Treffer {h*100:.0f}% P&L ${s['pnl']:,.0f}")
    blind = len(proven) - len(with_pnl)
    if proven and blind / len(proven) > 0.5:
        fails.append(f"{blind}/{len(proven)} 'bewiesene' Wallets ohne P&L-Daten — "
                     "Confirmed-Loser-Gate ist für sie blind")
    return _chk("proven_wallets_profitable", "'Bewiesene' Wallets wirklich profitabel", "warn", fails,
                "Whale-Pushes gehen nach Trefferquote. Hohe Quote ≠ Profit. Der Check zeigt, wie viele "
                "'bewiesenen' Wallets in Wahrheit Geld verlieren bzw. gar keine P&L-Historie haben.")


@poly_check
def check_accuracy_backtest_fresh(ctx):
    """Der Genauigkeits-Backtest (poly_money_broad: 'folgt dem Geld / dem Preis?') ist die
    Grundüberzeugung der ganzen Seite. Er muss frisch sein UND eine belastbare Stichprobe haben —
    eine auf n=2 kollabierte 'Trefferquote 100%' wäre gefährlicher Unsinn."""
    fails = []
    age = ctx.age_h(ctx.broad.get("generatedAt"))
    f_fresh, sev = _fresh_fail(age, "generatedAt")
    if f_fresh:
        fails.append(f"Backtest: {f_fresh[0]}")
    n = ctx.broad.get("n")
    if isinstance(n, int) and n < BACKTEST_MIN_N:
        fails.append(f"Stichprobe auf n={n} geschrumpft (< {BACKTEST_MIN_N}) — Trefferquoten nicht belastbar")
        sev = "warn" if sev != "error" else sev
    if not isinstance(n, int):
        fails.append("Backtest hat keine Stichprobengröße n — Datei leer/kaputt?")
        sev = "error"
    return _chk("accuracy_backtest_fresh", "Genauigkeits-Backtest frisch & belastbar", sev, fails,
                "poly_money_broad muss frisch sein und n groß genug, sonst ist 'folgt dem Geld' Zufall.")


@poly_check
def check_stale_live_markets(ctx):
    """„Schon vorbei, aber steht noch als live“ — genau die Klasse Bug, die Lucas an mehreren Views
    fand (Neu, einzelne Wale). Der Close-Feed setzt KEIN resolved-Flag → fertige Spiele bleiben
    ‚live’. Jede View, die nicht auf den Anpfiff filtert, zeigt dann Geister. Gemessen: von den
    Märkten, die der Feed als live führt (resolved==null) UND auf denen Whale-Geld liegt, wie viele
    sind in Wahrheit längst angepfiffen (> Karenz nach rekonstruiertem Anpfiff)? Hoher Anteil = die
    Views MÜSSEN auf Anpfiff filtern (tun sie seit 03.08.2026)."""
    money = 0; ghost = 0; ghost_usd = 0.0
    for k, v in ctx.close.items():
        if not isinstance(v, dict) or v.get("resolved") is not None:
            continue
        whales = v.get("whales") or []
        if not whales:
            continue
        money += 1
        cap = _parse_ts(v.get("capturedAt")); htk = v.get("hoursToKickoff")
        if cap is None or not isinstance(htk, (int, float)):
            continue
        ko = cap + timedelta(hours=htk)
        if (ctx.now - ko).total_seconds() / 3600.0 > KICKOFF_GRACE_H:
            ghost += 1
            ghost_usd += sum(float(w.get("usd") or 0) for w in whales if isinstance(w, dict))
    share = ghost / money if money else 0.0
    fails = []
    if money >= GHOST_MIN_N and share > GHOST_SHARE_FLOOR:
        fails.append(f"{ghost}/{money} 'live' Geld-Märkte sind schon >{KICKOFF_GRACE_H:.0f}h nach "
                     f"Anpfiff ({share*100:.0f}%) — ${ghost_usd:,.0f} Whale-Geld auf fertigen Spielen")
    return _chk("stale_live_markets", "Live-Feed frei von Geister-Märkten", "warn", fails,
                "Der Close-Feed setzt kein resolved-Flag; fertige Spiele bleiben 'live'. Alle Views filtern "
                "jetzt auf den rekonstruierten Anpfiff — dieser Check misst den Geister-Anteil im Roh-Feed "
                "(steigt er, prunt/löst der Feed nicht mehr auf; jede ungegatete View zeigt dann fertige Spiele).")


# ── Ausführung ────────────────────────────────────────────────────────────────
def run_checks(ctx):
    """Führt die ganze Registry aus. Pure. Ein crashender Check killt den Rest nicht."""
    out = []
    for fn in POLY_CHECKS:
        try:
            r = fn(ctx)
            if r:
                out.append(r)
        except Exception as e:
            out.append(_chk(fn.__name__, fn.__name__, "warn",
                            [f"Check-Code-Fehler: {e}"], "Guard selbst gecrasht — bitte prüfen."))
    return out


def build_ctx_from_disk(now=None):
    return PolyCtx(
        now=now,
        close=_load(CLOSE_FILE),
        resolutions=_load(RES_FILE),
        wallet_track=_load(WALLET_FILE),
        shortlist=_load(SHORTLIST_FILE),
        broad=_load(BROAD_FILE),
        cross_sport=_load(CROSS_FILE),
        trader=_load(TRADER_FILE),
    )


def main() -> int:
    ctx = build_ctx_from_disk()
    res = run_checks(ctx)
    nfail = sum(1 for c in res if not c["ok"])
    print(f"=== Poly-Daten-Integrität: {len(res) - nfail}/{len(res)} Checks ok "
          f"({len(POLY_CHECKS)} Guards registriert) ===\n")
    for c in res:
        icon = "✅" if c["ok"] else ("🔴" if c["severity"] == "error" else "🟡")
        sev = {"error": "ERR", "warn": "warn"}.get(c["severity"], c["severity"])
        print(f"{icon} {c['label']}: {c['nFail']} Fehler ({sev})")
        for f in c["failures"][:6]:
            print(f"     · {f}")
    (BASE / STATUS_FILE).write_text(json.dumps(
        {"checks": res, "nFail": nfail,
         "generatedAt": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 {STATUS_FILE} geschrieben ({nfail} Warnungen/Fehler).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
