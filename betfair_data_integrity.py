#!/usr/bin/env python3
"""
betfair_data_integrity.py — Ausgabe-Korrektheits-Batterie fuer die Betfair-Seite.

Vorgeschichte (10.08.2026, Lucas): Zur WM haben wir die Daten-Pipeline mit einer
Guard-Batterie hart abgesichert (wm_data_integrity.py, ~50 Guards), und die
Poly-Seite hat spaeter ihre eigene bekommen (poly_data_integrity.py, 9 Guards).
Die BETFAIR-Pipeline — inzwischen das groesste neue System (fetch → direction →
consensus → track-record → alerts → public-eval) — hatte NULL Ausgabe-Checks.
Auf der Status-Seite gab es zu Betfair nur Datei-Frische ("laeuft der Fetch
noch"), aber keinerlei inhaltliche Pruefung, ob die Daten stimmen. Und das ist
ausgerechnet das System, auf dessen Money-Flow-Pushs Lucas direkt Geld setzt.

Leitprinzip (wie WM): Wenn ein Datenpunkt kippt, auf dem Lucas Geld setzt, MUSS
es sichtbar werden — nicht still weggeguardet.

Konkret gefaehrlich und hier abgesichert: die zwei Push-Guards vom 09.08.2026
(Vor-Sprung-Quote-Anzeige + Sub-Schwellen-Braga-Filter) haengen BEIDE an
`leadPrev` aus betfair_direction.json. Kippt diese Datei still (Name-Drift, leer,
prev ueberall null), laufen beide Guards blind — und genau die Braga-Push geht
wieder raus, unbemerkt. `check_direction_covers_money` macht das sichtbar.

Ergebnis wird nach betfair_status.json geschrieben (gleiches {checks:[…], nFail}-
Schema wie wm_status.json / poly_status.json) und von der Status-Seite unter
"🟡 Betfair" als 🔴/🟡/✅-Zeilen gerendert.

═══════════════════════════════════════════════════════════════════════════════
  NEUEN BETFAIR-GUARD HINZUFUEGEN:
    1. Funktion mit @betfair_check dekorieren, ctx nutzen, _chk(...) zurueckgeben.
    2. Fertig — erscheint automatisch in betfair_status.json + Status-Seite.
    ctx hat: .now .prices .matches .history .direction .consensus .record
             .results .state .overview  + Helfer ctx.age_h(ts), ctx.money_games().
    Ein Check, der crasht, killt die Batterie NICHT (wird als warn gemeldet).
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent

import betfair_track_store as _store   # 01.09.2026: Ledger liegt kompakt, load() nimmt beide Formate

# ── Datei-Namen (alle read-only ausser betfair_status.json) ──────────────────
PRICES_FILE     = "betfair_prices.json"        # {_meta:{generatedAt,n,live}, matches:[snapshot…]}
HISTORY_FILE    = "betfair_history.json"        # {matchId:[{ts,totalVol,mo,kickoff,mkv,min}…]}
DIRECTION_FILE  = "betfair_direction.json"      # {matchId:{market:{runner:{dir,prev,odd}}}}
CONSENSUS_FILE  = "betfair_consensus.json"      # {generatedAt,count,covered,games:[…]}
RECORD_FILE     = "betfair_track_record.json"   # {generatedAt,n,byLeagueMarket,byTeamMarket}
LNORM_FILE      = "betfair_league_norm.json"    # {generatedAt,byLeagueStage:{"Liga|Phase":{med,n}}}
RESULTS_FILE    = "betfair_track_results.json"  # [{league,market,fav,odd,win,settledAt,…}]
STATE_FILE      = "betfair_track_state.json"    # {pending:{matchId:{kickoff,signals,…}}}
OVERVIEW_FILE   = "betfair_overview.json"        # {generatedAt,steam,flow}
PUBREC_FILE     = "betfair_public_record.json"  # Public-Push-Auswertung (Schema defensiv behandelt)
STATUS_FILE     = "betfair_status.json"          # ← Ausgabe

# ── Schwellen (Radar-Scan ~alle 15 Min, self-hosted Mac) ─────────────────────
FRESH_WARN_H     = float(os.environ.get("BF_FRESH_WARN_H")   or 0.75)  # Prices/Direction erwartet < 45 Min
FRESH_ERR_H      = float(os.environ.get("BF_FRESH_ERR_H")    or 3.0)   # > 3 h = Feed steht
DERIVED_WARN_H   = float(os.environ.get("BF_DERIVED_WARN_H") or 1.5)   # abgeleitete Feeds (Consensus/Record) laxer
DERIVED_ERR_H    = float(os.environ.get("BF_DERIVED_ERR_H")  or 6.0)
MONEY_MIN_VOL    = float(os.environ.get("BF_MONEY_MIN_VOL")  or 10000) # = betfair_consensus.MIN_VOL: Spiel mit echtem 1X2-Geld
COVER_MIN_N      = int(os.environ.get("BF_COVER_MIN_N")      or 5)     # Coverage-Quoten erst ab so vielen Spielen bewerten
DIR_PREV_FLOOR   = float(os.environ.get("BF_DIR_PREV_FLOOR") or 0.60)  # Anteil aufgewaermter Geld-Spiele mit leadPrev, unter dem es rot wird
MIN_ODD          = float(os.environ.get("BF_MIN_ODD")        or 1.01)  # unter 1.01 ist eine Quote unmoeglich
MAX_ODD          = float(os.environ.get("BF_MAX_ODD")        or 1001)  # Betfair-Deckel
GREEN_LO         = float(os.environ.get("BF_GREEN_LO")       or 0.30)  # plausibles Band der Gesamt-Trefferquote (Geld-Favorit gewinnt)
GREEN_HI         = float(os.environ.get("BF_GREEN_HI")       or 0.90)
GRADE_MIN_N      = int(os.environ.get("BF_GRADE_MIN_N")      or 40)    # Trefferquoten-Band erst ab so vielen abgerechneten Signalen
STUCK_PENDING_H  = float(os.environ.get("BF_STUCK_PENDING_H")or 72)    # > PENDING_TTL_H (60) + Puffer: bis 60 h ist pending NORMAL (Spiele ohne 'finished', die per TTL fallen). Erst DANACH haette der Prune greifen muessen.
MIN_MINUTE       = 0
MAX_MINUTE       = int(os.environ.get("BF_MAX_MINUTE")      or 130)    # inkl. langer Nachspielzeit


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_ts(t):
    if not isinstance(t, str) or not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except Exception:
        return None


def _money_side(m):
    """Seite mit dem meisten gematchten 1X2-Geld — Kopie von betfair_consensus.money_side, damit
    die Guard-Batterie 100% selbststaendig ist (kein Import, der sie mitreissen kann)."""
    mk = (m.get("markets") or {}).get("Match Odds")
    rs = (mk or {}).get("runners") or []
    if not rs:
        return None
    tot = sum((r.get("vol") or 0.0) for r in rs) or 1.0
    lead = max(rs, key=lambda r: (r.get("vol") or 0.0))
    name = lead.get("name")
    if name == "The Draw":
        side = "draw"
    elif name == m.get("away"):
        side = "away"
    else:
        side = "home"
    return {"side": side, "name": name, "share": (lead.get("vol") or 0.0) / tot,
            "odd": lead.get("odd"), "totVol": tot}


def _chk(cid, label, severity, failures, note=""):
    """Exakt das Schema von wm_data_integrity._chk / poly_data_integrity._chk — die Status-Seite
    rendert es 1:1 (id/label/severity/ok/nFail/failures/note)."""
    failures = list(failures)
    return {"id": cid, "label": label, "severity": severity,
            "ok": len(failures) == 0, "nFail": len(failures),
            "failures": failures[:25], "note": note}


class BetfairCtx:
    """Einmal gebaut, an jeden Guard gereicht. Alles bereits geladen/getrimmt."""
    def __init__(self, now=None, prices=None, history=None, direction=None,
                 consensus=None, record=None, results=None, state=None,
                 overview=None, pubrec=None, lnorm=None):
        self.now = now or datetime.now(timezone.utc)
        self.prices = prices if isinstance(prices, dict) else {}
        self.matches = self.prices.get("matches") or []
        self.history = history if isinstance(history, dict) else {}
        self.direction = direction if isinstance(direction, dict) else {}
        self.consensus = consensus if isinstance(consensus, dict) else {}
        self.record = record if isinstance(record, dict) else {}
        self.results = results if isinstance(results, list) else []
        self.state = state if isinstance(state, dict) else {}
        self.overview = overview if isinstance(overview, dict) else {}
        self.pubrec = pubrec  # Schema unklar → defensiv, kein Cast
        self.lnorm = lnorm if isinstance(lnorm, dict) else {}

    def age_h(self, ts_str):
        t = _parse_ts(ts_str)
        if t is None:
            return None
        return (self.now - t).total_seconds() / 3600.0

    def newest_capture(self):
        caps = [_parse_ts(m.get("capturedAt")) for m in self.matches if isinstance(m, dict)]
        caps = [c for c in caps if c]
        return max(caps) if caps else None

    def n_hist_points(self, mid):
        arr = self.history.get(str(mid))
        return len(arr) if isinstance(arr, list) else 0

    def money_games(self):
        """[(m, ms)] fuer nicht-beendete Spiele mit echtem 1X2-Geld (>= MONEY_MIN_VOL). Das sind die
        Spiele, aus denen Signale/Pushs entstehen — die, deren Daten stimmen MUESSEN."""
        out = []
        for m in self.matches:
            if not isinstance(m, dict):
                continue
            if (m.get("liveInfo") or {}).get("finished"):
                continue
            ms = _money_side(m)
            if ms and (ms.get("totVol") or 0) >= MONEY_MIN_VOL:
                out.append((m, ms))
        return out


# ── Registry ─────────────────────────────────────────────────────────────────
BETFAIR_CHECKS = []
def betfair_check(fn):
    BETFAIR_CHECKS.append(fn)
    return fn


def _fresh_fail(age_h, label_ts, warn_h=FRESH_WARN_H, err_h=FRESH_ERR_H):
    """Gemeinsame Frisch-Logik: (failures, severity)."""
    if age_h is None:
        return ([f"kein/kaputter Zeitstempel ({label_ts})"], "error")
    if age_h > err_h:
        return ([f"juengster Stand vor {age_h:.1f} h (> {err_h:.0f} h → Feed steht)"], "error")
    if age_h > warn_h:
        return ([f"juengster Stand vor {age_h:.1f} h (> {warn_h:.1f} h erwartet)"], "warn")
    return ([], "error")


# ── Die Guards ────────────────────────────────────────────────────────────────
@betfair_check
def check_prices_fresh(ctx):
    """Kommt der Roh-Feed ueberhaupt noch? betfair_prices.json ist die Wurzel von ALLEM (Direction,
    Consensus, Track-Record, Alerts). Steht der Fetch, ist die ganze Betfair-Seite blind — ohne dass
    irgendwo ein Fehler geloggt wuerde."""
    newest = ctx.newest_capture()
    age = None if newest is None else (ctx.now - newest).total_seconds() / 3600.0
    if age is None:  # Fallback auf _meta.generatedAt
        age = ctx.age_h((ctx.prices.get("_meta") or {}).get("generatedAt"))
    fails, sev = _fresh_fail(age, "capturedAt")
    if fails:
        fails = [f"Roh-Feed: {fails[0]} · {len(ctx.matches)} Spiele im File"]
    return _chk("prices_fresh", "Roh-Feed frisch (Betwatch-Fetch laeuft)", sev, fails,
                "Juengster erfasster Snapshot. Radar-Scan ~alle 15 Min — steht er, ist ALLES darunter alt.")


@betfair_check
def check_feed_populated(ctx):
    """Liefert der Feed echte Maerkte/Volumen — oder eine leere Huelle? Ein Fetch, der 200 zurueckgibt
    aber 0 Spiele oder ueberall totalVol=0 hat (Auth-Drift, API-Formatwechsel), ist genauso tot wie
    gar kein Fetch, faellt aber durch die reine Datei-Frische."""
    fails = []
    n = len(ctx.matches)
    if n == 0:
        fails.append("Feed hat 0 Spiele — Fetch liefert leere Liste (Auth/Format?)")
    else:
        with_vol = sum(1 for m in ctx.matches if isinstance(m, dict) and (m.get("totalVol") or 0) > 0)
        if with_vol == 0:
            fails.append(f"{n} Spiele, aber KEINES mit Volumen (totalVol=0 ueberall) — Money-Ansicht kaputt")
    return _chk("feed_populated", "Feed hat echte Spiele + Volumen", "error", fails,
                "200 mit leerer/volumenloser Liste ist ein stiller Totalausfall — reine Datei-Frische sieht ihn nicht.")


@betfair_check
def check_history_mkv_present(ctx):
    """Der 'Frisches Geld'-Push berechnet den Zufluss als Delta der letzten ZWEI mkv-Snapshots
    (per-Markt-Volumen). Fehlt mkv auf den letzten beiden History-Punkten eines Geld-Spiels, liefert
    fresh_alert fuer dieses Spiel NICHTS — still. Der Fetch haelt mkv bewusst nur auf den letzten
    MKV_KEEP_POINTS=2 Punkten; dieser Check bestaetigt, dass genau das noch funktioniert."""
    checked = blind = 0
    ex = []
    for m, ms in ctx.money_games():
        mid = str(m.get("matchId"))
        arr = ctx.history.get(mid)
        if not isinstance(arr, list) or len(arr) < 2:
            continue  # noch nicht aufgewaermt → kein Delta erwartet
        checked += 1
        last2 = arr[-2:]
        if not all(isinstance(p, dict) and isinstance(p.get("mkv"), dict) and p["mkv"] for p in last2):
            blind += 1
            if len(ex) < 6:
                ex.append(f"{m.get('home')} v {m.get('away')}: mkv fehlt auf den letzten 2 Punkten")
    fails = []
    if checked >= COVER_MIN_N and blind / checked > 0.20:
        fails = [f"{blind}/{checked} aufgewaermte Geld-Spiele ohne mkv auf den letzten 2 Punkten "
                 f"→ 'Frisches Geld'-Push fuer sie blind"] + ex
    return _chk("history_mkv_present", "Frisch-Geld-Basis (mkv-Delta) vorhanden", "error", fails,
                "mkv (per-Markt-Volumen) auf den letzten 2 History-Punkten ist die einzige Quelle des "
                "Zufluss-Deltas. Fehlt es, sendet der Frisch-Push fuer das Spiel nichts.")


@betfair_check
def check_live_minute_sane(ctx):
    """Die Zufluss-Fenster-Anzeige (55'→66') nutzt das neue History-Feld 'min' (Live-Minute). Zwei
    Lecks: (a) korrupte Minuten (negativ / > MAX_MINUTE) verfaelschen die Spanne; (b) Live-Spiele
    ohne Minute → Fenster faellt still auf die Zeit-Variante zurueck. (a) ist ein Fehler, (b) nur ein
    Hinweis (der Feed liefert die Minute nicht immer)."""
    bad = []
    for mid, arr in ctx.history.items():
        if not isinstance(arr, list):
            continue
        for p in arr:
            if isinstance(p, dict) and isinstance(p.get("min"), (int, float)):
                if p["min"] < MIN_MINUTE or p["min"] > MAX_MINUTE:
                    bad.append(f"{mid}: min={p['min']} ausserhalb {MIN_MINUTE}–{MAX_MINUTE}")
                    break
    live_missing = 0
    for m in ctx.matches:
        li = m.get("liveInfo") or {}
        if li.get("finished") or not isinstance(li.get("time"), (int, float)) or li["time"] <= 0:
            continue
        arr = ctx.history.get(str(m.get("matchId")))
        if isinstance(arr, list) and arr and isinstance(arr[-1], dict) and arr[-1].get("min") is None:
            live_missing += 1
    fails = list(bad[:12])
    sev = "error" if bad else "warn"
    if not bad and live_missing:
        fails.append(f"{live_missing} Live-Spiele ohne Minute im juengsten Punkt — Fenster nutzt die Zeit-Variante")
    return _chk("live_minute_sane", "Live-Minute plausibel (Zufluss-Fenster)", sev, fails,
                "Feld 'min' speist die Spielminuten-Spanne der Frisch-Push. Korrupte Werte verfaelschen sie, "
                "fehlende degradieren still auf die Zeit-Dauer.")


@betfair_check
def check_direction_covers_money(ctx):
    """🔴 DER wichtigste Betfair-Guard. Die Push-Guards vom 09.08.2026 (Vor-Sprung-Quote + Sub-
    Schwellen-Braga-Filter) brauchen `leadPrev` = die vorherige Quote des Geld-Fuehrers aus
    betfair_direction.json. Kippt diese Datei still (Name-Drift, leer, prev ueberall null), laufen
    BEIDE Guards blind und die Braga-Push (Geld @1.05, dann Tor → 42.00) geht wieder raus. Gemessen:
    von den aufgewaermten Geld-Spielen (>= 2 History-Punkte), fuer wie viele liefert die Direction-
    Datei tatsaechlich eine Vor-Quote des Fuehrers?"""
    warmed = have_prev = 0
    ex = []
    for m, ms in ctx.money_games():
        mid = str(m.get("matchId"))
        if ctx.n_hist_points(mid) < 2:
            continue  # erst ab dem 2. Sichten kann es eine Vor-Quote geben
        warmed += 1
        e = (((ctx.direction.get(mid) or {}).get("Match Odds") or {}).get(ms.get("name")) or {})
        if isinstance(e.get("prev"), (int, float)) and e["prev"] > 0:
            have_prev += 1
        elif len(ex) < 6:
            ex.append(f"{m.get('home')} v {m.get('away')}: keine Vor-Quote fuer '{ms.get('name')}'")
    fails = []
    if warmed >= COVER_MIN_N:
        share = have_prev / warmed
        if share < DIR_PREV_FLOOR:
            fails = [f"nur {have_prev}/{warmed} aufgewaermte Geld-Spiele mit Vor-Quote ({share*100:.0f}% "
                     f"< {DIR_PREV_FLOOR*100:.0f}%) → Sprung-/Sub-Schwellen-Guards laufen blind"] + ex
    return _chk("direction_covers_money", "Richtung/Vor-Quote deckt Geld-Spiele (Braga-Schutz)", "error", fails,
                "leadPrev aus betfair_direction.json traegt die Sprung-Erkennung UND den Sub-Schwellen-Filter. "
                "Ohne Vor-Quote koennen beide die Post-Tor-Push nicht mehr abfangen.")


@betfair_check
def check_direction_present(ctx):
    """Grober Lebens-Check der Direction-Datei selbst: Bei nicht-leerem Feed darf sie nicht leer sein
    (Wipe/Crash von betfair_direction.py), und sie darf nicht komplett 'flat/prev=null' sein (First-
    Run-Symptom, das nach dem ersten Lauf verschwinden muss)."""
    fails = []
    if ctx.matches:
        if not ctx.direction:
            fails.append("betfair_direction.json leer, obwohl Feed Spiele hat — Direction-Schritt tot/gewiped")
        else:
            total = withprev = 0
            for mk in ctx.direction.values():
                if not isinstance(mk, dict):
                    continue
                for rr in mk.values():
                    if not isinstance(rr, dict):
                        continue
                    for e in rr.values():
                        if not isinstance(e, dict):
                            continue
                        total += 1
                        if isinstance(e.get("prev"), (int, float)):
                            withprev += 1
            if total >= 50 and withprev == 0:
                fails.append(f"{total} Runner, aber KEINER mit Vor-Quote — Direction sieht aus wie First-Run "
                             "(Referenz-Datei verloren?)")
    return _chk("direction_present", "Richtungs-Datei lebt", "error", fails,
                "betfair_direction.json ist die Referenz fuer Back/Lay UND die Vor-Quote. Leer / ueberall "
                "prev=null bedeutet: der Direction-Schritt schreibt nicht mehr sauber fort.")


@betfair_check
def check_consensus_fresh(ctx):
    """Der Konsens (Zweitmeinung Pinnacle/Soft/Poly) wird jeden Lauf neu gebaut. Friert generatedAt
    ein, laeuft betfair_consensus.py nicht mehr durch (Crash statt continue-on-error-Skip) und die
    Zweitmeinung an der Trades-Push ist veraltet."""
    age = ctx.age_h(ctx.consensus.get("generatedAt"))
    fails, sev = _fresh_fail(age, "generatedAt", DERIVED_WARN_H, DERIVED_ERR_H)
    if fails:
        fails = [f"Konsens: {fails[0]} · {ctx.consensus.get('count', 0)} Spiele, "
                 f"{ctx.consensus.get('covered', 0)} mit Anker"]
    return _chk("consensus_fresh", "Konsens frisch (Zweitmeinung wird gebaut)", sev, fails,
                "betfair_consensus.json speist die Zweitmeinung der Trades-Frisch-Push. Steht generatedAt, "
                "ist die Zweitmeinung alt.")


@betfair_check
def check_consensus_anchor_coverage(ctx):
    """Findet der Konsens ueberhaupt noch Odds-Anker? Wenn in gecoverten Ligen Spiele laufen, aber
    KEINES einen Pinnacle/Soft-Anker bekommt (verdict != no_anchor), ist entweder der the-odds-api-
    Key tot oder das Namens-Matching gebrochen — die Zweitmeinung waere dann durchgehend leer, ohne
    dass es auffiele."""
    games = ctx.consensus.get("games") or []
    if not isinstance(games, list) or not games:
        return _chk("consensus_anchor_coverage", "Konsens findet Odds-Anker", "warn", [],
                    "Keine Konsens-Spiele zu bewerten (kein Feed / kein Geld) — kein Urteil.")
    covered = ctx.consensus.get("covered")
    if not isinstance(covered, int):
        covered = sum(1 for g in games if isinstance(g, dict) and g.get("verdict") != "no_anchor")
    # nur relevant, wenn genug Spiele in gecoverten Ligen ueberhaupt einen Anker haben KOENNTEN:
    # 13.08.2026 (Lucas-Audit): nur Ligen, die ueberhaupt einen Odds-Anker haben KOENNEN (in
    # LEAGUE_ODDS_KEY gemappt) zaehlen. Vorher zaehlte JEDE Liga -> in Sommer-/Friendly-Fenstern
    # (Super Cup, Leagues Cup, U19) permanenter Fehlalarm, der einen echten Key-Tod verdeckt haette.
    try:
        from betfair_consensus import LEAGUE_ODDS_KEY as _LOK
    except Exception:
        _LOK = {}
    if _LOK:
        anchorable = [g for g in games if isinstance(g, dict) and g.get("league") in _LOK]
    else:
        anchorable = [g for g in games if isinstance(g, dict) and g.get("league")]
    fails = []
    if len(anchorable) >= COVER_MIN_N and covered == 0:
        fails.append(f"0 von {len(games)} Konsens-Spielen mit Odds-Anker — the-odds-api-Key tot "
                     "oder Namens-Match gebrochen?")
    return _chk("consensus_anchor_coverage", "Konsens findet Odds-Anker", "warn", fails,
                "Anker = Pinnacle/Soft-Quote gematcht. Durchgehend 0 trotz laufender Spiele = API-Key tot "
                "oder Namens-Matching kaputt (Zweitmeinung waere leer).")


@betfair_check
def check_track_record_fresh(ctx):
    """Der Track-Record (Trefferquote je Liga×Markt, Basis der Radar-Bilanz) wird jeden Lauf neu
    aggregiert. Friert generatedAt ein, rechnet betfair_track_record.py nicht mehr ab."""
    age = ctx.age_h(ctx.record.get("generatedAt"))
    fails, sev = _fresh_fail(age, "generatedAt", DERIVED_WARN_H, DERIVED_ERR_H)
    if fails:
        fails = [f"Track-Record: {fails[0]} · n={ctx.record.get('n', 0)} abgerechnet"]
    return _chk("track_record_fresh", "Track-Record frisch (wird abgerechnet)", sev, fails,
                "betfair_track_record.json aggregiert die abgerechneten Signale. Steht es, wird die "
                "Radar-Bilanz nicht mehr aktualisiert.")


@betfair_check
def check_track_record_grading_sane(ctx):
    """Wertet die Abrechnung plausibel aus? Zwei Lecks: (a) korrupte Einzel-Ergebnisse (kein win-Bool,
    Quote < 1.01, fehlendes fav-Token); (b) eine Gesamt-Trefferquote ausserhalb eines plausiblen Bandes
    (Geld-Favorit gewinnt ~40–65% — 0% oder 100% waere ein Grading-Bug, kein Ergebnis)."""
    fails = []
    bad = 0
    for r in ctx.results:
        if not isinstance(r, dict):
            bad += 1; continue
        if not isinstance(r.get("win"), bool):
            bad += 1
        elif not isinstance(r.get("odd"), (int, float)) or r["odd"] < MIN_ODD or r["odd"] > MAX_ODD:
            bad += 1
        elif not r.get("fav"):
            bad += 1
    if bad:
        fails.append(f"{bad}/{len(ctx.results)} abgerechnete Signale korrupt (kein win-Bool / Quote unmoeglich / kein fav)")
    n = ctx.record.get("n")
    if isinstance(n, int) and n >= GRADE_MIN_N:
        wins = sum(1 for r in ctx.results if isinstance(r, dict) and r.get("win") is True)
        rate = wins / len(ctx.results) if ctx.results else None
        if rate is not None and (rate < GREEN_LO or rate > GREEN_HI):
            fails.append(f"Gesamt-Trefferquote {rate*100:.0f}% ausserhalb {GREEN_LO*100:.0f}–{GREEN_HI*100:.0f}% "
                         f"(n={len(ctx.results)}) → Grading-Bug statt Ergebnis?")
    return _chk("track_record_grading_sane", "Track-Record-Abrechnung plausibel", "warn", fails,
                "Einzel-Ergebnisse muessen ein win-Bool, eine moegliche Quote und ein fav-Token haben; die "
                "Gesamtquote muss in einem plausiblen Band liegen — sonst rechnet das Grading falsch ab.")


@betfair_check
def check_league_norm_usable(ctx):
    """24.08.2026 (Lucas: „bei PL und Serie A steht das x-Norm immer noch so extrem"): das Badge misst
    ein Spiel gegen den gelernten Median seiner Liga+Phase aus betfair_league_norm.json. Faellt der
    Lernschritt aus (er laeuft mit continue-on-error), friert die Basis ein und das Badge misst still
    gegen einen veralteten Massstab — sichtbar wird das NIE von selbst, weil das Badge weiter erscheint.
    Zwei Lecks: (a) Datei alt/kaputt, (b) Datei da, aber leer gelernt (z.B. Liga-Join gerissen)."""
    if not ctx.lnorm:
        return _chk("league_norm_usable", "Liga-Basis fuers x-Norm-Badge gelernt", "warn",
                    ["betfair_league_norm.json fehlt — das Badge faellt auf den heutigen Schnappschuss "
                     "zurueck und verschwindet fuer die meisten Ligen"],
                    "betfair_league_norm.py laeuft im Betfair-Workflow.")
    age = ctx.age_h(ctx.lnorm.get("generatedAt"))
    fails, sev = _fresh_fail(age, "generatedAt", DERIVED_WARN_H, DERIVED_ERR_H)
    usable = int(ctx.lnorm.get("usable") or 0)
    if usable < 20:
        fails = fails + [f"nur {usable} belastbare Liga|Phase-Buckets (n>=4) — Liga-Join gerissen?"]
        sev = "error"
    return _chk("league_norm_usable", "Liga-Basis fuers x-Norm-Badge gelernt", sev, fails,
                "Ohne belastbare Basis zeigt der Radar bewusst gar kein x-Norm-Badge — ein falsches "
                "waere schlimmer. Faellt der Guard, ist die Ursache fast immer der Lernschritt.")


@betfair_check
def check_no_stuck_pending(ctx):
    """Prunt/settlet die Track-Record-Maschine noch? Ein pending-Spiel bleibt bis PENDING_TTL_H (60 h)
    NORMAL liegen (Spiele ohne 'finished'-Flag, die zu frueh aus dem Feed verschwanden). Erst DANACH
    haette der TTL-Prune in settle() greifen muessen. Ein Spiel > STUCK_PENDING_H (> TTL + Puffer) noch
    pending = der Prune/Settle-Lauf hakt (Poly-Settlement-Leck-Analogon) — bei laufender Pipeline
    unmoeglich, also ein echtes Signal, kein normaler Rueckstand."""
    fails = []
    pending = (ctx.state.get("pending") or {})
    for mid, pend in pending.items():
        if not isinstance(pend, dict):
            continue
        kt = _parse_ts(pend.get("kickoff"))
        if kt is None:
            continue
        age_h = (ctx.now - kt).total_seconds() / 3600.0
        if age_h > STUCK_PENDING_H:
            fails.append(f"{pend.get('home')} v {pend.get('away')}: seit {age_h:.0f} h nach Anpfiff pending — "
                         "haette langst geprunt/abgerechnet sein")
    return _chk("no_stuck_pending", "Settlement/Prune lebt (kein Ueber-TTL-Stau)", "warn", fails,
                f"pending-Spiele mit Anpfiff > {STUCK_PENDING_H:.0f} h her (ueber TTL {STUCK_PENDING_H:.0f} h). "
                "Bis 60 h ist pending normal; darueber haette settle() prunen muessen — der Lauf hakt.")


@betfair_check
def check_odds_and_shape_sane(ctx):
    """Roh-Plausibilitaet der Spiele, aus denen Signale entstehen: jedes Geld-Spiel braucht matchId,
    Teams und Anpfiff (kein Geister-Eintrag), und seine Match-Odds-Quoten muessen im moeglichen
    Bereich liegen (>= 1.01, <= Deckel) bei Volumen >= 0. Korruptes Roh-Datum hier vergiftet jedes
    nachgelagerte Signal."""
    phantom = []
    badodd = []
    for m, ms in ctx.money_games():
        if not m.get("matchId") or not m.get("home") or not m.get("away") or not m.get("kickoff"):
            phantom.append(f"{m.get('home')} v {m.get('away')} (id={m.get('matchId')}): Pflichtfeld fehlt")
            continue
        for r in ((m.get("markets") or {}).get("Match Odds") or {}).get("runners") or []:
            o, v = r.get("odd"), r.get("vol")
            if isinstance(o, (int, float)) and (o < MIN_ODD or o > MAX_ODD):
                badodd.append(f"{m.get('home')} v {m.get('away')}: {r.get('name')} @{o} unmoeglich")
            if isinstance(v, (int, float)) and v < 0:
                badodd.append(f"{m.get('home')} v {m.get('away')}: {r.get('name')} Volumen {v} < 0")
    fails = (phantom + badodd)[:20]
    sev = "error" if phantom else "warn"
    return _chk("odds_and_shape_sane", "Geld-Spiele sauber (kein Geist, Quoten moeglich)", sev, fails,
                "Jedes signaltreibende Spiel braucht matchId/Teams/Anpfiff und moegliche Quoten. Korruptes "
                "Roh-Datum vergiftet Direction, Consensus, Track-Record und Alerts zugleich.")


@betfair_check
def check_public_eval_alive(ctx):
    """Weiche Lebens-Pruefung der Public-Push-Auswertung (betfair_public_eval.py schreibt
    betfair_public_record.json). Nur bewertet, wenn die Datei einen generatedAt-Zeitstempel hat —
    sonst still uebersprungen (Schema kann sich aendern, kein Fehlalarm)."""
    fails = []
    if isinstance(ctx.pubrec, dict):
        gen = ctx.pubrec.get("generatedAt") or ctx.pubrec.get("updatedAt")
        if isinstance(gen, str):
            age = ctx.age_h(gen)
            f2, _ = _fresh_fail(age, "generatedAt", DERIVED_WARN_H, DERIVED_ERR_H)
            if f2:
                fails = [f"Public-Auswertung: {f2[0]}"]
    return _chk("public_eval_alive", "Public-Push-Auswertung lebt", "warn", fails,
                "betfair_public_eval.py wertet Treffer/ROI der oeffentlichen Moneyflow-Signale aus. "
                "Nur geprueft, wenn die Datei einen Zeitstempel fuehrt.")


# ── Ausfuehrung ────────────────────────────────────────────────────────────────
def run_checks(ctx):
    """Fuehrt die ganze Registry aus. Pure. Ein crashender Check killt den Rest nicht."""
    out = []
    for fn in BETFAIR_CHECKS:
        try:
            r = fn(ctx)
            if r:
                out.append(r)
        except Exception as e:
            out.append(_chk(fn.__name__, fn.__name__, "warn",
                            [f"Check-Code-Fehler: {e}"], "Guard selbst gecrasht — bitte pruefen."))
    return out


def build_ctx_from_disk(now=None):
    return BetfairCtx(
        now=now,
        prices=_load(PRICES_FILE),
        history=_load(HISTORY_FILE),
        direction=_load(DIRECTION_FILE),
        consensus=_load(CONSENSUS_FILE),
        record=_load(RECORD_FILE),
        results=_store.load(BASE / RESULTS_FILE),   # 01.09.2026: kompaktes Ledger-Format
        state=_load(STATE_FILE),
        overview=_load(OVERVIEW_FILE),
        pubrec=_load(PUBREC_FILE),
        lnorm=_load(LNORM_FILE),
    )


def main() -> int:
    ctx = build_ctx_from_disk()
    res = run_checks(ctx)
    nfail = sum(1 for c in res if not c["ok"])
    print(f"=== Betfair-Daten-Integritaet: {len(res) - nfail}/{len(res)} Checks ok "
          f"({len(BETFAIR_CHECKS)} Guards registriert) ===\n")
    for c in res:
        icon = "OK " if c["ok"] else ("ERR" if c["severity"] == "error" else "warn")
        print(f"[{icon}] {c['label']}: {c['nFail']} Fehler ({c['severity']})")
        for f in c["failures"][:6]:
            print(f"     - {f}")
    (BASE / STATUS_FILE).write_text(json.dumps(
        {"checks": res, "nFail": nfail,
         "generatedAt": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{STATUS_FILE} geschrieben ({nfail} Warnungen/Fehler).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
