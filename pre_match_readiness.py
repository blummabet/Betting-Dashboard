#!/usr/bin/env python3
"""
pre_match_readiness.py — Pre-Match Readiness Check (gebaut 11.06.2026)
=====================================================================

Beantwortet täglich automatisch die Frage: "Feuern unsere Signale, wenn die
heutigen/anstehenden Spiele kommen — und sind alle Daten-Feeds frisch?"

Prüft zwei Dinge und alarmiert bei echten Lücken:

  1. FEED-FRISCHE — existiert jede Input-Datei, ist sie aktuell und befüllt?
     (weather mit Temps · apif mit Predictions · lineups bei nahen Spielen ·
      nt_xg · odds-history · poly-prices)

  2. SIGNAL-FEUERN — feuert jedes der 15 Signale in den aktuellen Picks?
     Mit kontext-bewusster Erwartung: manche Signale feuern erst spät
     (lineup T-1h), erst ab MD2 (incentive) oder nur bei Quotenbewegung
     (steam/lead-lag) — die werden NICHT als Fehler gewertet.

Output: Klartext-Report + (bei Errors) Telegram-Alert an den Trades-Channel.
Exit-Code 1 bei echten Lücken (Workflow-Step wird rot, continue-on-error
lässt den Rest laufen).

Env:
  TELEGRAM_TOKEN, TELEGRAM_TRADES_CHAT_ID — für Alert (ohne = Print-Vorschau)
  READINESS_WINDOW_DAYS — wie viele Tage voraus geprüft werden (default 2)
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

BASE = Path(__file__).parent
WM_FILE = BASE / "wm2026-data.json"

TELEGRAM_TOKEN = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
ALERT_CHAT_ID  = (os.environ.get("TELEGRAM_TRADES_CHAT_ID")
                  or os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
WINDOW_DAYS = int(os.environ.get("READINESS_WINDOW_DAYS", "2"))

# Lineup-Signal lohnt sich erst, wenn ein Spiel in <= N Stunden ist
LINEUP_WINDOW_H = 3.0
# Feed gilt als "stale", wenn älter als N Stunden (mtime-Fallback)
STALE_HOURS = 18.0


def tg_send(text: str) -> bool:
    if not (TELEGRAM_TOKEN and ALERT_CHAT_ID):
        print("\n⚠️  Kein TELEGRAM_TOKEN/CHAT_ID — Alert-Vorschau:\n" + text)
        return True
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": ALERT_CHAT_ID, "text": text,
                       "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as e:
        print(f"❌ Telegram-Alert fehlgeschlagen: {e}")
        return False


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _mtime_age_h(path: Path) -> float | None:
    try:
        return (datetime.now().timestamp() - path.stat().st_mtime) / 3600.0
    except Exception:
        return None


def weather_is_blocker(has_upcoming: bool) -> bool:
    """Wetter-Lücke (forecastAvailable=False / Datei leer) ist nur eine ECHTE Lücke (failt den
    Workflow), wenn tatsächlich Spiele im Fenster anstehen — weather_signal ist ein Kickoff-
    Temperatur-Modifier und braucht ein anstehendes Spiel zum Gewichten. 30.06.2026 (Lucas: WM-Update-
    Action failte zwischen R32 und R16 bei 0 anstehenden Spielen). Universell, nicht fixture-spezifisch."""
    return bool(has_upcoming)


def main() -> int:
    if not WM_FILE.exists():
        print("❌ wm2026-data.json fehlt — Abbruch")
        return 1
    wm = _load(WM_FILE) or {}
    picks = wm.get("picks", {}) or {}

    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=WINDOW_DAYS)

    # ── Anstehende Fixtures im Fenster ───────────────────────────────────
    upcoming = []          # (matchKey-ish, home, away, matchday, date, hours_until)
    for gk, gd in (wm.get("groups") or {}).items():
        for fx in gd.get("fixtures", []):
            ds = (fx.get("date") or "")[:10]
            try:
                d = date.fromisoformat(ds)
            except Exception:
                continue
            if today <= d <= horizon:
                hrs = None
                try:
                    ko = datetime.fromisoformat((fx.get("date") or "").replace("Z", "+00:00"))
                    if ko.tzinfo is None:
                        ko = ko.replace(tzinfo=timezone.utc)
                    hrs = (ko - datetime.now(timezone.utc)).total_seconds() / 3600
                except Exception:
                    pass
                upcoming.append({"gk": gk, "home": fx["home"], "away": fx["away"],
                                 "md": fx.get("matchday"), "date": ds, "hrs": hrs})

    errors: list[str] = []
    warns:  list[str] = []
    oks:    list[str] = []

    # ── 1) FEED-FRISCHE ──────────────────────────────────────────────────
    # Weather: muss für anstehende Spiele Temperaturen haben. 30.06.2026 (Lucas: „WM-Action
    # fehlgeschlagen"): weather_signal ist ein Kickoff-Temperatur-Modifier → ohne anstehende Spiele
    # gibt es nichts zu gewichten. Eine fehlende/leere Wetterdatei ist dann nur ein Hinweis, KEINE
    # echte Lücke (sonst failt der WM-Update-Workflow zwischen den KO-Runden grundlos). Universell:
    # Wetter-Lücke ist nur Error, wenn tatsächlich Spiele im Fenster anstehen.
    _w_sink = errors if weather_is_blocker(bool(upcoming)) else warns
    wfile = BASE / "wm_weather.json"
    wdata = _load(wfile) or {}
    wmatches = wdata.get("matches", {}) if isinstance(wdata, dict) else {}
    if not wmatches:
        _w_sink.append("🌡️ Weather: wm_weather.json fehlt/leer → weather_signal kann nicht feuern"
                       + ("" if upcoming else " (keine Spiele im Fenster — kein Blocker)"))
    else:
        with_temp = sum(1 for v in wmatches.values()
                        if v.get("forecastAvailable") and v.get("tempMax") is not None)
        age = _mtime_age_h(wfile)
        if with_temp == 0:
            _w_sink.append("🌡️ Weather: 0 Spiele mit Temperatur (forecastAvailable=False überall) "
                           "→ Fetch prüfen (WEATHERAPI_KEY / Actions-Log)"
                           + ("" if upcoming else " (keine Spiele im Fenster — kein Blocker)"))
        elif age is not None and age > STALE_HOURS:
            warns.append(f"🌡️ Weather: {with_temp} Spiele mit Forecast, aber Datei ~{age:.0f}h alt")
        else:
            oks.append(f"🌡️ Weather: {with_temp} Spiele mit Forecast")

    # Pinnacle-Odds-Frische (WICHTIGSTES Feed — Basis für Edge, Cards UND Trading)
    odds = wm.get("odds", {}) or {}
    newest_odds_h = None
    for v in odds.values():
        ts = v.get("updatedAt") if isinstance(v, dict) else None
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        age = (datetime.now(timezone.utc) - t).total_seconds() / 3600
        if newest_odds_h is None or age < newest_odds_h:
            newest_odds_h = age
    if newest_odds_h is None:
        errors.append("🎲 Pinnacle-Odds: keine updatedAt-Timestamps → fetch_wm_odds prüfen")
    elif newest_odds_h > STALE_HOURS:
        errors.append(f"🎲 Pinnacle-Odds EINGEFROREN: frischeste {newest_odds_h:.0f}h alt "
                      f"(fetch_wm_odds tot?) → Edges/Cards/Trading laufen auf veralteten Preisen!")
    else:
        oks.append(f"🎲 Pinnacle-Odds: frischeste {newest_odds_h:.1f}h alt")

    # APIF Predictions — KEIN Code/Auth-Fehler wenn leer: derselbe APISPORTS_KEY
    # liefert für wm_nt_xg Daten. API-Football listet WC-2026-Fixtures/Predictions
    # (/fixtures?league=1&season=2026 + /predictions) erst näher am Turnier. Darum
    # nur WARN (kontextabhängig), kein roter Blocker.
    afile = BASE / "wm_apif_predictions.json"
    adata = _load(afile)
    if not adata:
        warns.append("📊 APIF-Predictions leer — API-Football listet WC2026 noch nicht "
                     "(kein Code-Fehler; apif_predictions-Signal aktiviert sich näher am Turnier)")
    else:
        n = len([k for k in adata if isinstance(adata.get(k), dict)])
        oks.append(f"📊 APIF-Predictions: {n} Spiele")

    # Lineups — nur relevant wenn ein Spiel in <= LINEUP_WINDOW_H Stunden
    imminent = [u for u in upcoming if u["hrs"] is not None and 0 <= u["hrs"] <= LINEUP_WINDOW_H]
    lfile = BASE / "wm_lineups.json"
    ldata = _load(lfile) or {}
    if imminent:
        if not ldata:
            errors.append(f"📋 Lineups: {len(imminent)} Spiel(e) in <{LINEUP_WINDOW_H:.0f}h, "
                          "aber wm_lineups.json fehlt/leer → lineup_signal feuert nicht")
        else:
            oks.append(f"📋 Lineups: {len(ldata)} Spiele geladen ({len(imminent)} imminent)")
    else:
        oks.append("📋 Lineups: kein Spiel im T-1h-Fenster (Watcher feuert näher am Anpfiff)")

    # NT-xG
    nfile = BASE / "wm_nt_xg.json"
    ndata = _load(nfile) or {}
    if not ndata:
        warns.append("📈 NT-xG: wm_nt_xg.json fehlt/leer → xG-Fallback für Nicht-Europa schwächer")
    else:
        oks.append(f"📈 NT-xG: {len(ndata)} Teams")

    # Odds-History (für steam/lead-lag/CLV)
    hfile = BASE / "wm2026-odds-history.json"
    hdata = _load(hfile) or {}
    if hdata:
        avg = sum(len(v) for v in hdata.values() if isinstance(v, list)) / max(len(hdata), 1)
        oks.append(f"📉 Odds-History: {len(hdata)} Fixtures, Ø {avg:.1f} Snapshots")
    else:
        warns.append("📉 Odds-History fehlt → steam_lag/lead_lag/CLV ohne Basis")

    # Poly-Preise (für Auto-Trade-Edge)
    pfile = BASE / "wm_poly_prices.json"
    pdata = _load(pfile) or {}
    if (pdata.get("prices") if isinstance(pdata, dict) else None):
        oks.append(f"💹 Poly-Preise: {len(pdata['prices'])} Fixtures")
    else:
        warns.append("💹 Poly-Preise fehlen/leer → Auto-Trade & polymarket_sharp ohne Basis")

    # ── Stale-Edge-Konsistenz (11.06.2026) ─────────────────────────────────
    # Das gespeicherte edge_X muss IMMER (fair_X - poly_X)*100 entsprechen.
    # Real beobachtet: JPN-SWE edge_aw=-1.4 obwohl fair-poly=+7.1pp → Auto-Trader
    # handelte auf veraltetem Edge und ließ einen fetten Trade liegen. Der Trigger
    # rechnet jetzt live, ABER dieser Check schreit, falls die Datei selbst wieder
    # inkonsistent geschrieben wird — damit es nie wieder unbemerkt passiert.
    stale_edges = []
    for fx in (pdata.get("allFixtures") or []):
        for m in ("hw", "dr", "aw", "o25", "u25"):
            fair = fx.get(f"fair_{m}"); pol = fx.get(f"poly_{m}"); ed = fx.get(f"edge_{m}")
            if not all(isinstance(v, (int, float)) for v in (fair, pol, ed)):
                continue
            live = round((fair - pol) * 100, 1)
            if abs(live - ed) > 0.5:
                stale_edges.append(
                    f"{fx.get('homeId')}-{fx.get('awayId')} {m}: gespeichert {ed:+.1f}pp ≠ live {live:+.1f}pp")
    if stale_edges:
        head = stale_edges[:6]
        errors.append("⚠️ Stale Edges in wm_poly_prices.json (edge_X ≠ fair-poly): "
                      + "; ".join(head) + (f" … +{len(stale_edges)-6} weitere" if len(stale_edges) > 6 else ""))

    # Poly-Balance (Trading-kritisch — ohne Balance keine korrekte Stake-Cap-Logik)
    bfile = BASE / "wm_poly_balance.json"
    bdata = _load(bfile)
    if bdata is None:
        warns.append("💼 Poly-Balance: wm_poly_balance.json fehlt → Bankroll-Caps ohne Basis")
    else:
        bage = _mtime_age_h(bfile)
        if bage is not None and bage > STALE_HOURS:
            warns.append(f"💼 Poly-Balance: ~{bage:.0f}h alt — fetch_wm_poly_balance läuft?")
        else:
            oks.append(f"💼 Poly-Balance: ${float(bdata.get('usdc') or 0):.2f}")

    # ── Generischer Feed-Frische-Scan (Catch-all für still versagende Fetches) ──
    # Die meisten Fetch-Scripts melden Fehler NICHT — dieser Scan fängt jedes
    # Feed, das zu lange nicht aktualisiert wurde (mtime), als Sicherheitsnetz.
    feed_files = {
        "wm2026-data.json":          ("Kern-Daten (Picks/Odds/Form/Injuries)", True),
        "wm_poly_prices.json":       ("Polymarket-Preise", True),
        "wm2026-odds-history.json":  ("Odds-History", False),
        "wm_nt_xg.json":             ("NT-xG", False),
        "wm_weather.json":           ("Wetter", False),
    }
    for fn, (label, critical) in feed_files.items():
        p = BASE / fn
        if not p.exists():
            (errors if critical else warns).append(f"📂 {label} ({fn}) fehlt komplett")
            continue
        age = _mtime_age_h(p)
        if age is not None and age > STALE_HOURS:
            line = f"📂 {label}: Datei ~{age:.0f}h alt (> {STALE_HOURS:.0f}h) — Fetch hängt?"
            (errors if critical else warns).append(line)

    # ── Spielplan-Konsistenz: Seed-Datum vs echtes Polymarket-Datum ──────
    # 11.06.2026: Seed-Spielplan war ~1 Tag verschoben (56/60 Fixtures) → Picks
    # gingen für Spiele raus, die erst am nächsten Tag waren. Polymarket hat die
    # echten Anpfiff-Daten → jede Abweichung ist ein echter Spielplan-Fehler.
    poly_prices = (pdata.get("prices") if isinstance(pdata, dict) else None) or {}
    if poly_prices:
        seed_date = {}
        for gd in (wm.get("groups") or {}).values():
            for fx in gd.get("fixtures", []):
                seed_date[f"{fx.get('home')}-{fx.get('away')}"] = (fx.get("date") or "")[:10]
        date_mismatch = []
        for key, od in poly_prices.items():
            pd_ = (od.get("date") or "")[:10]
            sd_ = seed_date.get(key)
            if pd_ and sd_ and pd_ != sd_:
                date_mismatch.append(f"{key}: Seed {sd_} ≠ real {pd_}")
        if date_mismatch:
            errors.append(f"📅 Spielplan falsch datiert: {len(date_mismatch)} Fixture(s) "
                          f"weichen vom echten Polymarket-Datum ab (z.B. {date_mismatch[0]}) "
                          "→ Picks könnten am falschen Tag rausgehen!")
        else:
            oks.append("📅 Spielplan: Daten stimmen mit Polymarket überein")

    # ── 2) SIGNAL-FEUERN (aus aktuellen Picks) ───────────────────────────
    try:
        from sharp_signals.registry import ACTIVE_SIGNALS
        signal_names = [s.name() for s in ACTIVE_SIGNALS]
    except Exception:
        signal_names = ["lead_lag_bias", "public_static_bias", "travel_burden", "injury",
                        "form_trend", "h2h_pattern", "xg_strength", "polymarket_sharp",
                        "steam_lag", "pressure_index", "lineup_signal", "apif_predictions",
                        "weather_signal", "incentive_signal", "altitude_signal"]

    fire = {n: 0 for n in signal_names}
    for plist in picks.values():
        if not isinstance(plist, list):
            continue
        for p in plist:
            for s in (p.get("signals") or []):
                if s.get("name") in fire:
                    fire[s["name"]] += 1

    max_md = max((u["md"] or 0) for u in upcoming) if upcoming else 0
    # Erwartung pro Signal: ('core' = muss feuern, sonst kontextabhängig OK bei 0)
    CORE = {"form_trend", "xg_strength", "travel_burden", "pressure_index"}
    CONDITIONAL_OK = {
        "lineup_signal":    "feuert erst T-1h",
        "incentive_signal": "feuert ab MD2",
        "injury":           "nur bei gemeldeten Ausfällen",
        "steam_lag":        "nur bei Quotenbewegung",
        "lead_lag_bias":    "nur bei Quotenbewegung",
        "polymarket_sharp": "nur bei Poly↔Pinnacle-Divergenz",
        "h2h_pattern":      "nur bei ≥3 H2H-Spielen",
        "altitude_signal":  "nur Höhen-Venues",
        "public_static_bias": "nur bei Sharp-vs-Public-Divergenz",
        "weather_signal":   "nur bei ≥30°C + Klima-Asymmetrie",
        "apif_predictions": "nur wenn APIF-Daten vorhanden",
        # 07.07.2026 (Lucas: Status aufräumen): Liga/kontext-Signale sind in der WM per Design still —
        # National-Teams haben keine Liga-Tabelle, kein Transferfenster, keine Trainerwechsel-Feeds.
        "league_pressure":    "nur Liga (WM: nicht anwendbar)",
        "topscorer_momentum": "nur Liga/kontextabhängig",
        "coach_change":       "nur bei Trainerwechsel (Liga)",
        "transfer_shift":     "nur bei Kader-Abgängen (Liga)",
        "streak_momentum":    "nur bei laufender Serie",
        "smart_money":        "nur bei Big-Wallet-Konzentration",
        "chance_creation":    "nur bei xG-Detailabdeckung",
        "form_rating":        "nur bei Rating-Abdeckung",
        # 20.07.2026 — kontextabhängige/dataset-spezifische Signale: still ist ERWARTET, kein Engine-
        # Bug. mls_travel gibt für WM/Liga per Design None (Venue-Tabelle nur MLS); die beiden anderen
        # feuern nur bei passender Marktlage. Ohne diese Einträge warnten sie fälschlich „unerwartet still".
        "mls_travel":         "nur MLS (Reise/Höhe/Rasen; WM/Liga → None)",
        "game_state_openness": "nur bei offener Spielanlage (Über / BTTS-Ja)",
        "multi_book_steam":   "nur bei Multi-Buch-Steam-Bestätigung",
    }
    for n in signal_names:
        if fire[n] > 0:
            continue
        if n in CORE:
            errors.append(f"🧠 Signal '{n}' feuert in 0 Picks — sollte als Kern-Signal feuern!")
        elif n not in CONDITIONAL_OK:
            # Nur GENUINE Anomalien warnen (nicht-Kern, aber ohne bekannten Kontext-Grund).
            # Erwartbar stille Signale (CONDITIONAL_OK) erzeugen KEIN Gelb mehr — den echten
            # „Signal verstummt trotz Historie"-Fall fängt check_signal_coverage (history-basiert).
            warns.append(f"🧠 Signal '{n}' feuert nicht — unerwartet still, Engine prüfen")

    # ── Report ───────────────────────────────────────────────────────────
    fired = [n for n in signal_names if fire[n] > 0]

    # ── wm_signal_history.json: täglicher Snapshot für Status-Trend-Graph ────
    # Erlaubt der Status-Seite zu zeigen, ob mit Turnierverlauf mehr Signale
    # feuern + wie sich die Bayesian-Gewichte verschieben. 1 Eintrag/Tag (upsert).
    try:
        hist_file = BASE / "wm_signal_history.json"
        hist = []
        if hist_file.exists():
            try:
                hist = json.loads(hist_file.read_text(encoding="utf-8"))
            except Exception:
                hist = []
        if not isinstance(hist, list):
            hist = []
        picks_with_sig = sum(1 for pl in picks.values() if isinstance(pl, list)
                             for p in pl if (p.get("signals") or []))
        total_picks = sum(1 for pl in picks.values() if isinstance(pl, list) for _ in pl)
        weights = {}
        try:
            wf = json.loads((BASE / "signal_weights.json").read_text(encoding="utf-8"))
            weights = {n: (wf.get(n) or {}).get("weight")
                       for n in signal_names if isinstance(wf.get(n), dict)}
        except Exception:
            pass
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = {
            "date":            today_str,
            "ts":              datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fired":           len(fired),
            "total":           len(signal_names),
            "picksWithSignal": picks_with_sig,
            "totalPicks":      total_picks,
            "perSignal":       {n: fire[n] for n in signal_names},
            "weights":         weights,
        }
        hist = [h for h in hist if h.get("date") != today_str]   # upsert (1/Tag)
        hist.append(entry)
        hist = hist[-120:]
        hist_file.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"📈 wm_signal_history.json: {today_str} → {len(fired)}/{len(signal_names)} feuern, "
              f"{picks_with_sig}/{total_picks} Picks mit Signal")
    except Exception as e:
        print(f"⚠️  wm_signal_history schreiben fehlgeschlagen: {e}")

    print("=== Pre-Match Readiness Check ===")
    print(f"Stand: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · Fenster: +{WINDOW_DAYS}d")
    print(f"Anstehende Spiele: {len(upcoming)}"
          + (f" (nächstes in {min((u['hrs'] for u in upcoming if u['hrs'] is not None), default=0):.1f}h)"
             if upcoming else ""))
    print(f"Signale feuern: {len(fired)}/{len(signal_names)} — {', '.join(fired) or 'keine'}")
    print()
    if oks:
        print("✅ OK:")
        for o in oks:
            print("   " + o)
    if warns:
        print("\n⚠️  Hinweise (erwartbar / kein Blocker):")
        for w in warns:
            print("   " + w)
    if errors:
        print("\n❌ ECHTE LÜCKEN:")
        for e in errors:
            print("   " + e)
    else:
        print("\n✅ Keine echten Lücken — Engine ist bereit.")

    # ── Daten-Integrität (Pipeline-Härtung) ──────────────────────────────────
    # Benannte Guards über die Felder, die Picks/Signale/Trades treiben. Werden
    # auf der Status-Seite als ✅/🔴 sichtbar gemacht — kein stilles Weg-Guarden.
    integrity = []
    try:
        from wm_data_integrity import run_checks as _run_integrity
        _sched   = _load(BASE / "wm_venue_schedule.json") or {}
        _venues  = _load(BASE / "wm_venues.json") or {}
        _lineups = _load(BASE / "wm_lineups.json") or {}
        integrity = _run_integrity(wm, pdata if isinstance(pdata, dict) else {}, _sched, _venues,
                                   lineups=_lineups)
        for c in integrity:
            if not c["ok"]:
                ex = c["failures"][0] if c["failures"] else "—"
                msg = f"🛡️ {c['label']}: {c['nFail']} Fehler (z.B. {ex})"
                (errors if c["severity"] == "error" else warns).append(msg)
        n_int_fail = sum(1 for c in integrity if not c["ok"])
        print(f"\n🛡️ Daten-Integrität: {len(integrity)-n_int_fail}/{len(integrity)} Checks ok")
    except Exception as e:
        print(f"⚠️  Integritäts-Check fehlgeschlagen: {e}")

    # ── wm_status.json schreiben (Single Source of Truth für Status-Seite) ─
    # Die Dashboard-Status-Seite rendert diese Datei: autoritative Health aus
    # der echten Cron-Umgebung (Datei-mtimes, API-Keys, Spielplan-Konsistenz),
    # die der Browser nicht selbst prüfen kann. Browser ergänzt Live-Checks.
    status = {
        "generatedAt":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "windowDays":    WINDOW_DAYS,
        "upcoming":      len(upcoming),
        "signalsFired":  fired,
        "signalsTotal":  len(signal_names),
        "perSignal":     fire,   # 14.06.2026: echte Feuer-Zähler pro Signal → Status-Seite
                                 # zeigt Matrix authoritativ (statt aus data.picks abzuleiten)
        "verdict":       "error" if errors else ("warn" if warns else "ok"),
        "errors":        errors,
        "warns":         warns,
        "oks":           oks,
        "checks":        integrity,
    }
    try:
        with open(BASE / "wm_status.json", "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        print("\n💾 wm_status.json geschrieben")
    except Exception as e:
        print(f"\n⚠️  wm_status.json schreiben fehlgeschlagen: {e}")

    # ── Telegram-Alert nur bei echten Lücken ─────────────────────────────
    if errors:
        lines = [f"⚠️ <b>Readiness-Check: {len(errors)} Lücke(n)</b>",
                 f"<i>Signale feuern: {len(fired)}/{len(signal_names)} · "
                 f"{len(upcoming)} Spiele im Fenster</i>", ""]
        lines += ["• " + e for e in errors[:8]]
        if warns:
            lines += ["", "<i>Hinweise:</i>"] + ["· " + w for w in warns[:4]]
        tg_send("\n".join(lines))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
