#!/usr/bin/env python3
"""
poly_money_broad.py — Liegt das Geld richtig? BREIT über ALLE Poly-Ligen (19.07.2026, Lucas).

## Idee

`poly_money_accuracy.py` misst das für unsere Datensätze (WM/MLS) gegen unsere Ergebnisdaten.
Lucas will es breiter: **alles, was Polymarket anbietet** (min. Volumen), um zu sehen, wo die Masse
mehr recht hat — je Liga aufgeschlüsselt, und ohne triviale Favoriten (Quote < 1.35).

Der Clou: für fremde Ligen brauchen wir GAR KEINE eigenen Ergebnisse — **Polymarket löst seine
Märkte selbst auf** (die Gewinner-Seite settlet auf 1.00). Also: Geld-Verteilung + Preis nah am
Anpfiff einfrieren, später Polys eigene Auflösung lesen. Kein externer Anker nötig.

## Filter (Lucas)

  · Volumen ≥ Schwelle (5–10k) — darunter ist die Geld-Verteilung nicht aussagekräftig.
  · Favorit-Quote ≥ 1.35 — „dass ein 1.1-Favorit öfter recht hat, ist logo"; nur kompetitive
    Märkte sagen etwas über die Klugheit der Masse.

Teilt sich `evaluate` (min_odds + byLeague) mit poly_money_accuracy — dieselbe, getestete Mathematik.

⚠️ Die Fetch-/Auflösungs-Schicht (Gamma über alle Sport-Tags + Poly-Resolution + Holders je Markt)
läuft scharf NUR am Mac-Runner (Poly EU-geoblockt) und muss dort validiert werden. Die reinen
Helfer (`winner_from_prices`, Aggregation via `evaluate`) sind ohne Netz getestet. Read-only.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import poly_money_accuracy as PMA
from safe_write import write_json_atomic   # 25.08.2026: temp+replace statt halber Datei

BASE = Path(__file__).resolve().parent

MIN_VOL_USD = float(os.environ.get("POLY_MIN_VOL_USD") or 7500)     # „5-10k oben liegen" — Mitte
MIN_ODDS    = float(os.environ.get("POLY_MIN_ODDS") or 1.35)      # Lucas: triviale Favoriten (≤1.35) raus
# 02.08.2026 (Lucas, streng): „Sharp im Markt" hatte nur n≥4 & CLV>0 — dadurch wurden Wallets mit
# +0,05pp CLV und sogar bestätigte Millionen-Verlierer (−$4,3 Mio) als „bewiesen scharf" gepusht.
# Jetzt: Close SPÜRBAR geschlagen (Ø CLV ≥ Schwelle) UND Trefferquote ≥ Schwelle UND kein bestätigter
# Verlierer (Lifetime-P&L bekannt & < 0). Konsistent mit dem _is_smart-Gate im Whale-Channel.
# 29.08.2026 (Lucas-Audit): diese zwei bedienen NUR noch die alte Sharp-Textliste, die seit dem
# 05.08. per Default aus ist (SHARP_LIST_PUSH). Sie sind damit eine VIERTE Definition von „scharf"
# im Repo gewesen (CLV>=1.5pp gegen die 0.0pp des lebenden Gates). Sie bleiben stehen, weil die
# Liste ueber das Env-Flag reaktivierbar ist — aber ausdruecklich als das, was sie sind: die
# Schwellen DIESER abgeschalteten Liste, nicht die Sharp-Definition des Systems. Die steht in
# sharp_gate.py und gilt fuer Dashboard, Shortlist, Push, Whale-Watch und Live-Watch.
SHARP_LIST_MIN_CLV = float(os.environ.get("SHARP_MIN_CLV") or 1.5)   # Ø CLV pp — Linie real geschlagen
SHARP_LIST_MIN_HIT = float(os.environ.get("SHARP_MIN_HIT") or 0.5)   # Mindest-Trefferquote
CLOSE_FILE  = "poly_money_broad_close.json"
OUT_FILE    = "poly_money_broad.json"
# 25.07.2026 (Lucas ① Momentum): globale Poly-Preis-ZEITREIHE je Markt — fortgeschrieben bei jedem
# Lauf, damit „was bewegt sich gerade" (Steam vs Reversal) über ALLE Sportarten sichtbar wird. Wie
# damals die Wale: die Erfassung startet jetzt, die Ansicht füllt sich über die nächsten Läufe.
HIST_FILE   = "poly_money_broad_history.json"
HIST_MAX_POINTS = 48     # je Markt ~1 Tag Punkte (Runner alle ~30 min) — reicht für kurzfristiges Steam
HIST_KEEP_H     = 96.0   # Märkte, die 4 Tage nicht mehr gesehen wurden, fallen raus (aufgelöst/vorbei)
# ② Sharp-Wallet-Track (25.07.2026, Lucas): je Whale den EINSTIEGSPREIS je Markt merken; bei
# Auflösung CLV (Einstieg→Close) + Treffer werten → wer schlägt systematisch die Linie („scharf",
# nicht bloß groß). Wie [[project_wallet_track_record]], aber GLOBAL über alle Sportarten.
WTRACK_FILE = "poly_wallet_track.json"
RESOLUTIONS_FILE = "poly_resolutions.json"   # 02.08.2026 (Lucas): rollierende {key:{winner,ts}} für den
RESOLUTIONS_KEEP_DAYS = 14                    # Shortlist-Paper-Tracker — abrechnen ohne Re-Fetch.
# 06.08.2026 (Lucas, Geister-Maerkte): der Close-Feed setzte kein resolved-Flag und prunte nie ->
# fertige Spiele blieben ewig 'live' (796/815 Maerkte >6h nach Anpfiff, ~$23M Whale-Geld auf toten
# Spielen). Jetzt wirft capture() unaufgeloeste Maerkte raus, sobald sie GHOST_GRACE_H nach Anpfiff
# sind -- GLEICHE Schwelle wie die Integrity-Pruefung (POLY_KICKOFF_GRACE_H), damit der Feed die eine
# saubere Quelle fuer alle Views ist. Aufgeloeste Snapshots bleiben (fuer die Treffer-Auswertung).
GHOST_GRACE_H = float(os.environ.get("POLY_KICKOFF_GRACE_H") or 6)
# 24.08.2026 (Lucas, "$41 Mio Whale-Geld auf fertigen Spielen"): aufgeloeste Snapshots bleiben fuer
# die Treffer-Auswertung -- aber nicht ewig. Danach ist die Wette laengst abgerechnet und der
# Eintrag nur noch Ballast in einer Datei, die JEDE Flaeche parst.
CLOSE_RESOLVED_KEEP_DAYS = float(os.environ.get("POLY_CLOSE_RESOLVED_KEEP_DAYS") or 30)

# 11.08.2026 (Lucas, Stufe 1 Live-Erfassung): Maerkte auch NACH Anpfiff weiter abgreifen -> eigener
# Live-Speicher, GETRENNT vom Vor-Spiel-Freeze (der bleibt die Auswertungs-Basis). Kostet nur mehr
# Calls auf die FREIE Poly-API (kein Geld); der Live-Deckel ist additiv, damit Pre nie verdraengt wird.
LIVE_FILE             = "poly_money_broad_live.json"
LIVE_HIST_FILE        = "poly_money_broad_live_history.json"
LIVE_TAIL_H           = float(os.environ.get("POLY_LIVE_TAIL_H") or 3.0)            # so lange NACH Anpfiff weiter erfassen
MAX_HOLDER_CALLS_LIVE = int(os.environ.get("POLY_MAX_HOLDER_CALLS_LIVE") or 40)     # eigener Live-Deckel (additiv zu MAX_HOLDER_CALLS)
LIVE_KEEP_H           = float(os.environ.get("POLY_LIVE_KEEP_H") or 6.0)            # Live-Eintrag prunen, wenn X h nicht mehr gesehen
LIVE_HIST_MAX_POINTS  = 24                                                          # Live-Historie: Spiele sind kurz -> weniger Punkte
LIVE_HIST_KEEP_H      = 12.0

# 12.08.2026 (Lucas, Money-Map): breitere "upcoming"-Erfassung fuer die Money Map. Poly listet marquee-
# Spiele (Super Cup, Pokal) frueh mit echtem Geld, aber die Geld-Erfassung oben greift erst <=3h vor
# Anpfiff (Holder-Budget). Preis + Volumen stehen aber schon in den Basis-Event-Daten des Sweeps ->
# GRATIS. Diese Datei haelt je Sport-Markt bis UPCOMING_WINDOW_H nur {league, htk, totalUsd, prices}
# (KEIN Holder-Call, KEINE Shares/Whales) -> die Money Map zeigt die Poly-Blase (Seite via Preis) auch
# weit vor Anpfiff. Getrennt vom Close-Freeze (der bleibt die Auswertungs-Basis).
# ── Vor-Fenster (01.09.2026) ──────────────────────────────────────────────────────────────────
# Lucas: „poly taucht da mmn nie aktiv auf?" Ursache war, dass Holder-Anteile NUR fuer Maerkte
# innerhalb PMA.CAPTURE_WINDOW_H (3h) geholt werden — die Konjunktion latcht aber bei 22% ihrer
# Zeilen frueher. Fuer die konnte Poly nie zustimmen.
#
# ⚠️ NICHT geloest durch Aufbohren von CAPTURE_WINDOW_H. Zwei Gruende:
#   · Das Holder-Budget (90) wird nach VOLUMEN vergeben. Ein weiteres Fenster laesst weit
#     entfernte Maerkte um dieselben 90 Calls konkurrieren — nahe Maerkte wuerden verdraengt und
#     der Close-Freeze duenner. Der ist aber die AUSWERTUNGS-Basis (poly_money_accuracy).
#   · Der Freeze bedeutet „Geldverteilung kurz vor Anpfiff". Weitet man ihn, aendert sich
#     rueckwirkend, was die Zahlen heissen.
# Stattdessen ein EIGENES, kleines Budget mit eigenem Fenster, dessen Ergebnis in die
# upcoming-Datei geschrieben wird — genau die Quelle, auf die `pick_poly` ausserhalb des Freeze
# zurueckfaellt. Der Close-Freeze bleibt unberuehrt.
VOR_WINDOW_H          = float(os.environ.get("POLY_VOR_WINDOW_H") or 8.0)
MAX_HOLDER_CALLS_VOR  = int(os.environ.get("POLY_MAX_HOLDER_CALLS_VOR") or 22)
# ⭐ Und das Budget wird GEZIELT ausgegeben. Gemessen am 01.09.: von 58 Maerkten im Vor-Fenster
# sind nur 20 Fussball — der Rest ist Tennis/Esport/US-Sport. Nach reinem Volumen sortiert gingen
# 13 der 25 Calls an Tennis, also an Maerkte, die die Konjunktion NIE benutzt (killer.py sieht
# ausschliesslich Betfair-Fussball-Match-Odds; Tennis/Esport bekommen ihre Anteile ohnehin im
# 3h-Freeze, und ihre Events sind kurz). Fussball zuerst, dann Volumen — damit deckt ein
# kleineres Budget ALLE relevanten Maerkte ab statt der Haelfte.
_VOR_FUSS_LIGEN = ("EPL", "LIGA", "BUNDESLIGA", "SERIE", "LIGUE", "CHAMPIONSHIP", "MLS", "UCL",
                   "UEL", "EREDIVISIE", "PRIMEIRA", "CUP", "EFL", "SPL")


def _vor_ist_fussball(league, sport) -> bool:
    """Grobe, absichtlich grosszuegige Fussball-Erkennung fuers Vor-Budget. Im Zweifel JA — ein
    Call zu viel kostet wenig, ein fehlender kostet die Poly-Bedingung. REIN/testbar."""
    s, lg = str(sport or "").upper(), str(league or "").upper()
    return "SOCCER" in s or "SOCCER" in lg or any(x in lg for x in _VOR_FUSS_LIGEN)

UPCOMING_FILE         = "poly_money_upcoming.json"
UPCOMING_WINDOW_H     = float(os.environ.get("POLY_UPCOMING_WINDOW_H") or 120.0)
# 25.08.2026 (Lucas zeigte den Poly-Link auf Barcelona–Athletic, den wir „nicht gelistet" genannt
# hatten): 48h war zu eng. Das Spiel lag 55h vor Anpfiff, hatte auf Poly aber schon $21,7K —
# der Event-Page fehlte der Poly-Block nur wegen dieses Fensters. Weiten kostet NICHTS: die
# Events sind im Sweep ohnehin geholt, hier wird nur gefiltert, welche wir uns merken.


def update_resolutions(prev, markets, now=None, keep_days=RESOLUTIONS_KEEP_DAYS):
    """Aufgelöste Märkte dieses Laufs in eine rollierende {key:{winner,ts}} mergen; alte prunen.
    REIN/testbar. Der Shortlist-Tracker liest das statt selbst Poly abzufragen."""
    now = now or _now()
    out = {k: dict(v) for k, v in (prev or {}).items() if isinstance(v, dict)}
    for key, winner in resolutions(markets).items():
        if not key or not winner:
            continue
        if key not in out:                       # erste Auflösung gewinnt (Zeitstempel = zuerst gesehen)
            out[key] = {"winner": winner, "ts": now.isoformat()}
        else:
            out[key]["winner"] = winner
    cutoff = now - timedelta(days=keep_days)
    for k in list(out.keys()):
        try:
            ts = datetime.fromisoformat(str(out[k].get("ts", "")).replace("Z", "+00:00"))
        except Exception:
            ts = None
        if not ts or ts < cutoff:
            del out[k]
    return out


def _now():
    return datetime.now(timezone.utc)


def _cfg():
    try:
        raw = json.loads((BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        p = raw.get("poly", {})
        return float(p.get("money_broad_min_vol", MIN_VOL_USD)), float(p.get("money_broad_min_odds", MIN_ODDS))
    except Exception:
        return MIN_VOL_USD, MIN_ODDS


def winner_from_prices(price_by_outcome: dict, tol: float = 0.02):
    """Aus Polys AUFGELÖSTEN Outcome-Preisen die Gewinner-Seite ableiten: die, die ~1.00 settlet.
    None, wenn (noch) nicht eindeutig aufgelöst (kein Preis nahe 1.0)."""
    best, best_p = None, 0.0
    for k, v in (price_by_outcome or {}).items():
        try:
            p = float(v)
        except (TypeError, ValueError):
            continue
        if p > best_p:
            best, best_p = k, p
    return best if best_p >= 1.0 - tol else None


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Fetch-/Capture-Schicht (Mac-Runner) ──────────────────────────────────────
# Läuft scharf nur am Mac-Runner (Poly EU-geoblockt). Reuse der bewährten Bausteine:
# Gamma-Events (wie fetch_wm_poly_prices) + Holders-Geld-Split (wie fetch_wm_poly_smartmoney).
# ⚠️ Erster Runner-Lauf = Validierung: Feldnamen/Antwortform per Log prüfen.

import json as _json
import urllib.request as _url
import urllib.error as _urlerr
import time as _time
from datetime import timedelta as _td

# Sport-Tags, die Poly liquide listet. Erweiterbar über cocobet_config poly.money_broad_tags.
# 19.07.2026 (Lucas): E-Sport dazu — Poly deckt CS2/LoL/Dota/Valorant inzwischen breit ab.
# 21.07.2026 (Lucas: „sollte da nicht mehr Sport sein?"): um die ganzjährigen/Sommer-Poly-Sportarten
# erweitert (UFC/MMA/Boxen/Golf/F1/Cricket). Welche Tag-Slugs Poly WIRKLICH liefert, zeigt die neue
# rawByTag-Diagnose im nächsten Lauf — tote Tags fliegen dann wieder raus. Saisonale (NBA/NFL/NHL/EPL)
# bleiben drin und füllen sich von selbst, sobald ihre Saison startet.
# 23.07.2026 (Lucas: „bei ‚Liegt das Geld richtig' viel zu wenig Fußball — MLS fehlt"). MLS war
# NICHT gelistet → wurde gar nicht erst von Gamma geholt, obwohl es die aktive Fußball-Liga mit
# echter Poly-Liquidität ist (Matches clearen die $7.5K-Schwelle, ~$8–13k). 3-Wege wird korrekt
# verarbeitet (capture akzeptiert len(oc)>=2). Die europäischen Top-5 laufen im Sommer nicht; wenn
# ihre Saison startet (August), gehören ihre Poly-Tags (la-liga, serie-a, bundesliga, ligue-1) hier
# dazu — rawByTag im Output zeigt dann, welcher Slug echt Events liefert.
SPORT_TAGS = ["nba", "nfl", "mlb", "nhl", "mls", "epl", "soccer", "tennis", "ucl",
              "la-liga", "bundesliga", "serie-a", "ligue-1", "primeira-liga",
              "brazil-serie-a", "brasileirao", "belgium-pro-league", "eredivisie", "super-lig",   # 03.08.2026 (Lucas): Poly listet Top-Ligen einzeln (/sports/laliga/…), nicht (nur) unter "soccer"
              "esports", "cs2", "lol", "dota", "valorant",
              "ufc", "mma", "boxing", "golf", "f1", "cricket"]
GAMMA = "https://gamma-api.polymarket.com/events"
HOLDERS = "https://data-api.polymarket.com/holders?market={cond}&limit=200"
_HTTP_TIMEOUT = 12
MAX_HOLDER_CALLS = 90   # Deckel gegen API-Last: die VOLUMENSTÄRKSTEN near-KO-Märkte bekommen den Geld-Split
# 28.07.2026 (Lucas: „CLV misst 0"): der Whale-EINSTIEGSPREIS. /holders liefert nur AKTUELLE Shares →
# firstPrice ≈ Close ≈ CLV 0 (strukturell, 67/71 Positionen). Der ECHTE Ø-Einstieg steht in /positions
# (avgPrice je asset). Damit wird CLV = Close − echter Einstieg endlich messbar. Gedeckelt + abschaltbar.
POSITIONS = "https://data-api.polymarket.com/positions?user={user}&sizeThreshold=1&limit=500"
# 31.07.2026 (Lucas): echte Lebenszeit-P&L je Wallet (kumuliert, inkl. geschlossener Positionen) →
# damit die „schärfste Wallets"-Rangliste nach TATSÄCHLICHEM Gewinn geht, nicht nur nach CLV-Timing.
# Antwort: Liste {t,p}; letzter p = aktuelle Gesamt-Bilanz in USD (verifiziert gegen das Poly-Profil).
PNL_API = "https://user-pnl-api.polymarket.com/user-pnl?user_address={user}&interval=all&fidelity=1d"
MAX_POSITION_CALLS = int(os.environ.get("POLY_MAX_POSITION_CALLS") or 150)
FETCH_AVGPRICE = (os.environ.get("POLY_FETCH_AVGPRICE") or "1") == "1"

# 18.08.2026 (Lucas, Arkham-Inspiration): Orderbuch (Spread/Tiefe) + letzte Trades je money-fav-Seite.
# Fuers Poly-Terminal-Drilldown. Buch-Snapshot ~5 Min -> Liquiditaets-/Spread-Indikator, keine Live-Leiter.
BOOK_URL      = "https://clob.polymarket.com/book?token_id={token_id}"
TRADES_URL    = "https://data-api.polymarket.com/trades?market={cond}&limit=50"
FETCH_BOOK    = (os.environ.get("POLY_FETCH_BOOK") or "1") == "1"
MAX_BOOK_CALLS = int(os.environ.get("POLY_MAX_BOOK_CALLS") or 40)   # 2 Calls/Markt -> ~Top-20 Vol-Maerkte
TRADE_MIN_USD = int(os.environ.get("POLY_TRADE_MIN_USD") or 300)
BOOK_LEVELS   = 6


def _enrich_book_trades(m_row, oc, get, budget):
    """m_row['book'] (Top-of-Book + Spread der money-fav-Seite) + m_row['trades'] (letzte nennenswerte
    Kaeufe/Verkaeufe). Defensiv: kein Token/Budget/Fehler -> still, nichts gesetzt. budget=[rest] (mutable,
    2 Calls je Markt). get(url)->JSON|None. REIN (Netz nur via get)."""
    shares = m_row.get("shares") or {}
    prices = m_row.get("prices") or {}
    if shares:
        fav = max(shares.items(), key=lambda kv: kv[1] or 0)[0]
    elif prices:
        fav = max(prices.items(), key=lambda kv: kv[1] or 0)[0]
    else:
        return
    o = next((x for x in (oc or []) if x.get("label") == fav), None)
    if not o:
        return
    tok, cond = o.get("token"), o.get("cond")
    tok2lbl = {x.get("token"): x.get("label") for x in (oc or []) if x.get("token")}
    # --- Orderbuch ---
    if tok and budget[0] > 0:
        budget[0] -= 1
        data = get(BOOK_URL.format(token_id=tok))
        if isinstance(data, dict):
            try:
                bids = sorted(((float(b["price"]), float(b.get("size", 0) or 0))
                               for b in (data.get("bids") or [])
                               if isinstance(b, dict) and b.get("price") is not None), key=lambda x: -x[0])
                asks = sorted(((float(a["price"]), float(a.get("size", 0) or 0))
                               for a in (data.get("asks") or [])
                               if isinstance(a, dict) and a.get("price") is not None), key=lambda x: x[0])
            except (TypeError, ValueError):
                bids = asks = []
            if bids and asks:
                bid, ask = bids[0][0], asks[0][0]
                m_row["book"] = {
                    "side": fav, "bid": round(bid, 4), "ask": round(ask, 4),
                    "spreadC": round((ask - bid) * 100, 2),
                    "spreadPct": round((ask - bid) / ask * 100, 2) if ask else None,
                    "bids": [[round(p, 4), round(s)] for p, s in bids[:BOOK_LEVELS]],
                    "asks": [[round(p, 4), round(s)] for p, s in asks[:BOOK_LEVELS]],
                }
    # --- letzte Trades ---
    if cond and budget[0] > 0:
        budget[0] -= 1
        tr = get(TRADES_URL.format(cond=cond))
        if isinstance(tr, list) and tr:
            out = []
            for t in tr:
                if not isinstance(t, dict):
                    continue
                try:
                    sz = float(t.get("size") or 0)
                    pr = float(t.get("price") or 0)
                except (TypeError, ValueError):
                    continue
                usd = round(sz * pr)
                if usd < TRADE_MIN_USD:
                    continue
                side_lbl = (t.get("outcome") or t.get("outcomeName")
                            or tok2lbl.get(t.get("asset")) or tok2lbl.get(t.get("token")) or "")
                out.append({
                    "wallet": t.get("proxyWallet") or t.get("proxy_wallet") or t.get("wallet") or "",
                    "action": ("SELL" if str(t.get("side") or "").upper() == "SELL" else "BUY"),
                    "side": side_lbl, "price": round(pr, 4), "usd": usd, "ts": t.get("timestamp"),
                })
                if len(out) >= 8:
                    break
            if out:
                m_row["trades"] = out



def _tags():
    try:
        raw = _json.loads((BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        return raw.get("poly", {}).get("money_broad_tags") or SPORT_TAGS
    except Exception:
        return SPORT_TAGS

# 16.08.2026 (Lucas): Self-Discovery der Fussball-Liga-Tags — persistente Registry.
LEAGUE_TAGS_FILE = "poly_football_tags.json"
_GENERIC_TAG_SKIP = {"sports", "games", "soccer", "football", "all", "live", "match", "matches",
                     "sport", "world", "international", "recurring", "weekly", "daily", "new",
                     "trending", "featured", "hide-from-new", "esports"}
# 16.08.2026 (Lucas): NUR echte Liga-/Wettbewerb-Tags aufnehmen. Poly-Events tragen Dutzende Tags
# (Team/Spieler/Thema) — ohne diesen Filter explodiert die Registry (380 Junk statt ~36 Ligen).
_LEAGUE_PAT = r"(liga|league|ligue|bundesliga|serie-[abc]|eredivisie|eliteserien|allsvenskan|superettan|ekstraklasa|championship|premier|division|veikkausliiga|superliga)"


def _discover_football_tags(events):
    """Aus Poly-Events die Fussball-Liga-Tag-Slugs ziehen. NUR Events mit 'soccer'-Tag zaehlen (kein
    anderer Sport rein); daraus jeder nicht-generische Tag-Slug (= die Liga, z.B. 'la-liga',
    'primeira-liga', 'brazil-serie-a'). REIN/defensiv."""
    out = set()
    for ev in events or []:
        try:
            slugs = set()
            for t in (ev.get("tags") or []):
                s = str((t.get("slug") if isinstance(t, dict) else t) or "").strip().lower()
                if s:
                    slugs.add(s)
            if "soccer" not in slugs:
                continue
            for s in slugs:
                if s in _GENERIC_TAG_SKIP or s.isdigit() or not (2 <= len(s) <= 40):
                    continue
                if _re.search(_LEAGUE_PAT, s):   # 16.08.2026 (Lucas): nur echte Liga-Tags, kein Team/Spieler/Thema-Junk
                    out.add(s)
        except Exception:
            continue
    return out


def _load_league_registry():
    try:
        d = _json.loads((BASE / LEAGUE_TAGS_FILE).read_text(encoding="utf-8"))
        return set(x for x in d if isinstance(x, str)) if isinstance(d, list) else set()
    except Exception:
        return set()


def _save_league_registry(new_slugs):
    """Merge-on-write: Live- UND Global-Scan schreiben -> nie clobbern, nur Union."""
    try:
        cur = _load_league_registry()
        allslugs = cur | {str(s).strip().lower() for s in (new_slugs or set()) if s}
        if allslugs != cur:
            (BASE / LEAGUE_TAGS_FILE).write_text(
                _json.dumps(sorted(allslugs), ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


# 16.08.2026 (Lucas, nach dem Poly-Rate-Limit-Update): _get war ein Einzelversuch — bei 429/5xx still
# None und KEIN Backoff (hämmerte weiter). Jetzt 429-/5xx-bewusst: Retry-After respektieren (gedeckelt,
# der Scan hat ein Workflow-Timeout), sonst kurzer Backoff, EIN Retry. 404/andere -> sofort None wie bisher.
_HTTP_MAX_RETRIES = 2
_HTTP_BACKOFF_CAP = 3.0   # Sek — Retry-After respektieren, aber deckeln (kein Timeout-Sprengen)
def _get(url):
    for _attempt in range(_HTTP_MAX_RETRIES):
        try:
            req = _url.Request(url, headers={"User-Agent": "BetEdge/1.0", "Accept": "application/json"})
            with _url.urlopen(req, timeout=_HTTP_TIMEOUT) as r:
                return _json.loads(r.read())
        except _urlerr.HTTPError as e:
            if e.code == 404:
                return None                       # nicht vorhanden -> kein Retry
            if (e.code == 429 or 500 <= e.code < 600) and _attempt < _HTTP_MAX_RETRIES - 1:
                ra = e.headers.get("Retry-After") if getattr(e, "headers", None) else None
                try:
                    wait = float(ra)
                except (TypeError, ValueError):
                    wait = 2 ** _attempt
                _time.sleep(min(max(wait, 0.0), _HTTP_BACKOFF_CAP))
                continue
            print(f"  HTTP {e.code} {url[:70]}… : {e}")
            return None
        except Exception as e:
            if _attempt < _HTTP_MAX_RETRIES - 1:
                _time.sleep(min(2 ** _attempt, _HTTP_BACKOFF_CAP))
                continue
            print(f"  HTTP {url[:70]}… : {e}")
            return None
    return None


def _gamma_events(tag, closed, now=None):
    """Events eines Sport-Tags. OFFEN: nach ANPFIFF-Nähe sortiert (endDate aufsteigend ab jetzt
    minus Live-Puffer) statt nach Listing-Datum — 12.08.2026 (Lucas Money-Map): order=startDate&desc
    verpasste Spiele, die vor Wochen gelistet wurden aber HEUTE spielen (UEFA Super Cup: gelistet
    30.07., Anpfiff 12.08. → fiel hinter den 400er-Tag-Deckel, nie erfasst → Money-Map ohne Poly).
    endDate ~ Spielzeit → die nächsten Spiele stehen vorn, der 400er-Deckel greift die richtigen ab.
    GESCHLOSSEN: unverändert (order=startDate&desc = zuletzt gelistete/aufgelöste zuerst)."""
    out, offset = [], 0
    if closed:
        qorder = "&order=startDate&ascending=false"
    else:
        floor = (now or _now()) - timedelta(hours=LIVE_KEEP_H)
        qorder = "&order=endDate&ascending=true&end_date_min=" + floor.strftime("%Y-%m-%dT%H:%M:%SZ")
    for _ in range(4):   # bis 400 Events je Tag
        url = (f"{GAMMA}?tag_slug={tag}&limit=100&offset={offset}"
               f"&active=true&closed={'true' if closed else 'false'}{qorder}")
        page = _get(url)
        if not isinstance(page, list) or not page:
            break
        out += page
        if len(page) < 100:
            break
        offset += 100
    return out


# 23.07.2026 (Lucas: „alles nehmen wo Volumen drauf ist, egal welche Sportart"). Statt nur eine
# hartcodierte Tag-Liste abzugrasen (die schon 2× eine ganze Liga verpasst hat — E-Sport, dann MLS):
# tag-LOS die volumenstärksten Events holen. Der Sport-Filter passiert von selbst über das
# Anpfiff-Fenster (0<htk<=3h) im Ingest — Politik/Krypto haben keinen unmittelbaren Anpfiff
# (startDate liegt in der Vergangenheit → htk<0 → raus). Liga = Slug-Präfix (mls-… → MLS).
SWEEP_PAGES = 5   # bis 500 Events je Richtung, nach Volumen sortiert


def _gamma_top(closed):
    """Tag-LOS die volumenstärksten Events (offen bzw. aufgelöst). Defensiv — [] bei Fehler."""
    out, offset = [], 0
    for _ in range(SWEEP_PAGES):
        url = (f"{GAMMA}?limit=100&offset={offset}"
               f"&active=true&closed={'true' if closed else 'false'}&order=volume&ascending=false")
        page = _get(url)
        if not isinstance(page, list) or not page:
            break
        out += page
        if len(page) < 100:
            break
        offset += 100
    return out


# Poly-Slug-Präfixe, die NICHT gleich dem Frontend-Liga-Label sind (03.08.2026, Lucas: La-Liga-
# Slug ist "lal-ala-get-…" → ohne Mapping „LAL" → Sonstige → aus allen Poly-Views gefiltert).
_SLUG_LEAGUE_ALIAS = {"lal": "LALIGA"}
def _league_from_slug(key):
    """Liga-Label aus dem Event-Slug-Präfix (mls-phi-nyr-… → MLS). Fallback: OTHER."""
    head = str(key or "").split("-", 1)[0].strip().lower()
    if not head or head.isdigit():
        return "OTHER"
    return _SLUG_LEAGUE_ALIAS.get(head, head.upper())


# 16.08.2026 (Lucas): Sport-Kategorie beim ERFASSEN stempeln. Der Frontend-Rateversuch aus dem Liga-
# String verfehlte abgekuerzte Bewerbe (ERE=Eredivisie, BEL1, RUS, AZE1, CLF, EFL-Championship …) -> sie
# landeten als "Sonstige"/🎯 und flogen aus Play-Liste/Neu + falschem Sport-Topf. Der Runner WEISS die
# Sportart (Tag, unter dem er den Markt holt) -> hart stempeln.
_SPORT_BY_TAG = {
    "nba": "US-Sport", "nfl": "US-Sport", "mlb": "US-Sport", "nhl": "US-Sport",
    "esports": "E-Sport", "cs2": "E-Sport", "csgo": "E-Sport", "lol": "E-Sport", "dota": "E-Sport", "valorant": "E-Sport",
    "tennis": "Tennis", "atp": "Tennis", "wta": "Tennis",
    "ufc": "Kampfsport", "mma": "Kampfsport", "boxing": "Kampfsport",
    "golf": "Golf", "f1": "Motorsport", "nascar": "Motorsport", "cricket": "Cricket",
}
_FOOT_TAGS = ("soccer", "football", "epl", "ucl", "uel", "mls", "la-liga", "laliga", "bundesliga",
              "serie-a", "ligue-1", "primeira-liga", "eredivisie", "super-lig", "brazil-serie-a", "brasileirao")
def _tag_category(tag):
    """Kategorie des Sport-Tags, unter dem der Markt geholt wurde. SPORT_TAGS + entdeckte Liga-Registry
    sind bis auf die _SPORT_BY_TAG-Liste alle Fußball -> Default Fußball."""
    return _SPORT_BY_TAG.get(str(tag or "").lower().strip(), "Fußball")
def _event_sport(ev):
    """Sport eines Events aus SEINEN Tags (fuer den tag-losen Volumen-Sweep). Bekannter Sport-Tag ->
    Kategorie; Fußball-Tag -> Fußball; sonst None (Politik/Krypto -> Frontend entscheidet = Sonstige)."""
    for _t in (ev.get("tags") or []):
        slug = str((_t.get("slug") if isinstance(_t, dict) else _t) or "").lower()
        if slug in _SPORT_BY_TAG:
            return _SPORT_BY_TAG[slug]
        if slug in _FOOT_TAGS:
            return "Fußball"
    return None


def _hours_to_ko(ev, now):
    ko = ev.get("startTime") or ev.get("gameStartTime") or ev.get("startDate")
    try:
        t = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        return (t - now).total_seconds() / 3600
    except Exception:
        return None


def _capture_class(htk):
    """Klassifiziert nach Zeit-bis-Anpfiff: 'pre' (0<htk<=Fenster), 'live' (Anpfiff bis LIVE_TAIL_H
    danach), sonst None (zu frueh / lange vorbei / kein Anpfiff). REIN/testbar. 11.08.2026 (Lucas Stufe 1)."""
    try:
        h = float(htk)
    except (TypeError, ValueError):
        return None
    if 0 < h <= PMA.CAPTURE_WINDOW_H:
        return "pre"
    if -LIVE_TAIL_H < h <= 0:
        return "live"
    # 01.09.2026: „vor" — jenseits des Freeze, aber nah genug, dass die Konjunktion dort latcht.
    # Eigenes Budget, eigener Speicher (upcoming); der Close-Freeze nimmt sie NICHT auf.
    if PMA.CAPTURE_WINDOW_H < h <= VOR_WINDOW_H:
        return "vor"
    return None


import re as _re

_MAP_PROP_RE = _re.compile(
    r"\b(map|game|karte|spiel)\s*\d"                       # "Map 1", "Game 2", "Karte 3"
    r"|handicap|spread|over\s*/?\s*under|correct\s*score"   # Handicap / Totals / exaktes Ergebnis
    r"|first\s*blood|\bduration\b|\bkills?\b|\brounds?\b"  # eSport-Props
    r"|to\s*win\s*(map|game)\b",
    _re.I)


def _market_rows(m):
    """Ein Gamma-Markt -> [{label,price,cond,token}] (echte Team-Ausgaenge, Struktur 1) oder []."""
    try:
        names = _json.loads(m.get("outcomes", "[]") or "[]")
        prices = _json.loads(m.get("outcomePrices", "[]") or "[]")
        tokens = _json.loads(m.get("clobTokenIds", "[]") or "[]")
    except Exception:
        return []
    if len(names) < 2 or len(prices) != len(names):
        return []
    if {str(n).strip().lower() for n in names} == {"yes", "no"}:
        return []
    cond = m.get("conditionId")
    rows = []
    for i, nm in enumerate(names):
        try:
            p = float(prices[i])
        except (TypeError, ValueError, IndexError):
            p = None
        rows.append({"label": str(nm), "price": p, "cond": cond,
                     "token": tokens[i] if i < len(tokens) else None})
    return rows


def _is_map_prop(m):
    """True, wenn der Markt eine einzelne Map / ein Handicap / ein Prop ist (NICHT der Serien-Sieger).
    15.08.2026 (Lucas): eine laufende Map laeuft gegen 99¢ -> darf den Serien-Markt nicht verdraengen."""
    txt = " ".join(str(m.get(k) or "") for k in ("question", "groupItemTitle", "slug"))
    return bool(_MAP_PROP_RE.search(txt))


def _mkt_vol(m):
    v = m.get("volumeNum")
    if v is None:
        v = m.get("volume")
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _tokens_of(oc):
    """{Ausgangs-Label: CLOB-Token-ID} aus den Outcomes. REIN.

    24.08.2026 (Lucas, „Heute"-Tab: „kriegen wir das hin, dass ich von dort gleich die Wette
    ausloese?"): Der Token lag bisher nur transient in `oc` (fuer Holders/Orderbuch) und wurde
    danach verworfen. Das Frontend musste den Play deshalb ueber Slug+Teamnamen an einen
    gestempelten Card-Pick matchen, damit der Placer den Token per Gamma aufloesen konnte --
    ging nur fuer Fussball MIT Pick (~7% der Plays). Mit dem Token IM Feed traegt jeder Play
    alles, was der Placer braucht: keine Namens-Aufloesung, jede Sportart.
    Key-gleich zu `shares`/`prices`, also direkt mit der empfohlenen Seite (`side`) lookupbar.
    """
    return {o["label"]: o["token"] for o in (oc or [])
            if isinstance(o, dict) and o.get("label") and o.get("token")}


def _outcomes(ev):
    """Moneyline-Ausgaenge eines Events → [{label, price, cond, token}]. ZWEI Poly-Strukturen:
    (1) EIN Markt mit Team-Ausgaengen (US-Sport, viele Soccer): outcomes = [Team1, (Draw,) Team2].
    (2) Gruppierte Ja/Nein-Maerkte (12.08.2026, Lucas: UEFA Super Cup u.v.a.): je Ausgang EIN Markt
        „Gewinnt X?" Yes/No, der Ausgangs-Name steht im groupItemTitle, die Wahrscheinlichkeit ist der
        Ja-Preis. Ohne (2) fielen solche Spiele als „Yes/No" durch → nie gegen Teamnamen matchbar
        (poly:null in der Money-Map). REIN."""
    markets = ev.get("markets") or []
    # (1) echte Team-Ausgang-Maerkte: unter ALLEN den SERIEN/Moneyline-Markt waehlen, NICHT eine
    # laufende Map. 15.08.2026 (Lucas): bei Best-of-3-eSport lieferte "erster 2-Wege-Markt" die gerade
    # laufende Map, die gegen Map-Ende auf 99¢ laeuft (TEAM VISION 0.99 statt Serie ~0.74 / Quote 1.35).
    cand = [(m, _market_rows(m)) for m in markets]
    cand = [(m, r) for m, r in cand if r]
    if cand:
        series = [(m, r) for m, r in cand if not _is_map_prop(m)]   # Map/Handicap/Totals raus
        pool = series or cand                                        # nichts uebrig -> altes Verhalten
        pool.sort(key=lambda mr: -_mkt_vol(mr[0]))                   # Serie hat i.d.R. das meiste Volumen
        return pool[0][1]
    # (2) gruppierte Ja/Nein-Maerkte: groupItemTitle = Ausgang, Ja-Preis = Wahrscheinlichkeit
    rows = []
    for m in markets:
        title = m.get("groupItemTitle")
        if not title:
            continue
        try:
            names = _json.loads(m.get("outcomes", "[]") or "[]")
            prices = _json.loads(m.get("outcomePrices", "[]") or "[]")
            tokens = _json.loads(m.get("clobTokenIds", "[]") or "[]")
        except Exception:
            continue
        low = [str(n).strip().lower() for n in names]
        if "yes" not in low:
            continue
        yi = low.index("yes")
        try:
            p = float(prices[yi])
        except (TypeError, ValueError, IndexError):
            p = None
        rows.append({"label": str(title), "price": p, "cond": m.get("conditionId"),
                     "token": tokens[yi] if yi < len(tokens) else None})
    return rows if len(rows) >= 2 else []


def _market_volume(ev, oc, fallback):
    """15.08.2026 (Lucas): Volumen NUR der Markt(e), aus denen _outcomes die Ausgaenge zog (per
    conditionId) — statt des ganzen Event-Volumens. Ein Best-of-3-eSport-Event summiert Serie + Map1
    + Map2 + Map3 (+ Handicaps) -> Event-Volumen bis ~8x hoeher als der Moneyline-Markt (TEAM VISION:
    Event $1.24M, Markt ~$150K). totalUsd muss denselben Markt beschreiben, aus dem die Wale kommen,
    sonst ist der usd>totalUsd-Guard wertlos. Fallback: Event-Volumen, wenn kein Markt-Volumen lesbar.
    REIN/testbar."""
    conds = {o.get("cond") for o in (oc or []) if o.get("cond")}
    if not conds:
        return fallback
    tot, hit = 0.0, False
    for m in (ev.get("markets") or []):
        if m.get("conditionId") in conds:
            v = m.get("volumeNum")
            if v is None:
                v = m.get("volume")
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if v >= 0:
                tot += v
                hit = True
    return tot if hit else fallback


_EXHIBITION_RE = _re.compile(
    r"\blegends\b|all[- ]?stars?\b|\bexhibition\b|\btestimonial\b|charity\s*match"
    r"|\bveterans?\b|\bold\s*boys\b|\bmasters\b|\blegends?\s+xi\b",
    _re.I)


def _is_exhibition(oc):
    """15.08.2026 (Lucas): Legenden-/Show-/Benefiz-Spiel? Am Ausgangs-Namen erkannt ("... Legends",
    "All-Star", "Exhibition", "Testimonial", ...). 'legends' bewusst im PLURAL -> das eSport-Team
    "Anyone's Legend" (Singular) bleibt drin. Kein Wettsignal -> aus allen Poly-Views. REIN."""
    for o in (oc or []):
        if _EXHIBITION_RE.search(str(o.get("label") or "")):
            return True
    return False


WHALES_PER_MARKET = 4   # 25.07.2026 (Lucas: „was setzen einzelne Wale") — Top-N je Markt mitschreiben


def _market_money(outcomes):
    """Aus EINEM Holders-Fetch je Ausgang beides ableiten (quota-schonend):
      shares = Geld-Split {label: usd} (Shares × Preis)
      whales = die größten EINZELNEN Wallets [{wallet, side, usd}] über alle Ausgänge
    → {"shares":…, "whales":…} oder None. 25.07.2026 (Lucas): globale Einzel-Wale (c)."""
    try:
        from fetch_wm_poly_smartmoney import _http_get, _holders_for_token
    except Exception:
        return None
    usd, whales = {}, []
    for o in outcomes:
        if not (o.get("cond") and o.get("token") and isinstance(o.get("price"), (int, float)) and o["price"] > 0):
            continue
        data = _http_get(HOLDERS.format(cond=o["cond"]))
        holders = _holders_for_token(data, o["token"]) if data else []
        price = float(o["price"])
        usd[o["label"]] = sum(a for _, a in holders) * price
        for w, a in holders:
            whales.append({"wallet": w, "side": o["label"], "usd": round(a * price)})
    if sum(usd.values()) <= 0:
        return None
    whales.sort(key=lambda x: -x["usd"])
    return {"shares": usd, "whales": whales[:WHALES_PER_MARKET]}


def _money_shares(outcomes):
    """Rückwärtskompatibel: nur der Geld-Split. Delegiert an _market_money."""
    mm = _market_money(outcomes)
    return mm["shares"] if mm else None


def _avg_from_positions(data, token):
    """Poly /positions-Antwort → Ø-Einstiegspreis (avgPrice) der Position auf `token` (asset).
    None, wenn nicht gefunden oder außerhalb (0,1). REIN/testbar."""
    for p in (data or []):
        if not isinstance(p, dict):
            continue
        if str(p.get("asset") or p.get("token") or p.get("tokenId") or "") == str(token):
            ap = p.get("avgPrice", p.get("avg_price"))
            try:
                ap = float(ap)
            except (TypeError, ValueError):
                return None
            return round(ap, 4) if 0 < ap < 1 else None
    return None


def _lifetime_pnl(data):
    """user-pnl-Antwort (Liste {t,p} kumulierte P&L) → letzter p = Lebenszeit-P&L (USD, kann negativ).
    None wenn leer/unlesbar. REIN/testbar."""
    if not isinstance(data, list) or not data:
        return None
    last = data[-1]
    if not isinstance(last, dict):
        return None
    try:
        return round(float(last.get("p")), 2)
    except (TypeError, ValueError):
        return None


# ── Gedaechtnis je Wallet (01.09.2026) ────────────────────────────────────────────────────────
# Lucas: „die Whales Wallets aendern sich eh, sobald z.B. eine bessere erscheinen wuerde, oder?"
# Ja — der Pool waechst automatisch (2.956 Wallets, jede neue Grossposition legt eine an). Beim
# Nachsehen fiel aber auf, was der Track NICHT konnte: `{n, wins, clvSumPP, usd, pnl}` trug keinen
# einzigen Zeitstempel. Folgen:
#   · Man konnte nicht sagen, WANN eine gerankte Wallet zuletzt aktiv war (15 der Top-20 hatten
#     keine offene Position — ob seit zwei Tagen oder zwei Monaten still, war nicht feststellbar).
#   · Und das Urteil hatte kein Gedaechtnis: eine Wallet mit n=622 wird auf ihrer gesamten
#     Lebenszeit beurteilt. Wer im Juni brillant war und seit August mittelmaessig, behaelt seinen
#     guten Schnitt — die schwache Phase geht im Mittel unter. Genau der Fehler, den das
#     rollierende Fenster bei der Conviction-Tabelle schon behebt.
# Deshalb ab jetzt: firstTs/lastTs und ein gleitendes Fenster der letzten Auflösungen.
#
# ⚠️ Das Fenster ist heute LEER und fuellt sich erst mit neuen Auflösungen — Vergangenheit laesst
# sich nicht nachtragen, die Einzelergebnisse wurden nie gespeichert. Es wird deshalb vorerst nur
# MITGESCHRIEBEN, nicht bewertet (dieselbe Doktrin wie `wertVsPinn` im Killer). Wer es spaeter
# auswertet, muss `wnRoh` pruefen: ein Fenster mit 3 Eintraegen ist kein Urteil.
WALLET_FENSTER = int(os.environ.get("WALLET_FENSTER") or 30)   # so viele Auflösungen behaelt das Fenster
WALLET_FENSTER_AB_N = int(os.environ.get("WALLET_FENSTER_AB_N") or 8)   # erst ab Ranglisten-Reife sammeln


def _wallet_zeit(s: dict, clv: float, win: bool, now) -> dict:
    """Zeitstempel und gleitendes Fenster einer Wallet fortschreiben. REIN/testbar.

    `recent` haelt die letzten WALLET_FENSTER Auflösungen als kompakte Tripel
    [ISO-Datum, CLV in pp, 1/0] — lesbar genug zum Debuggen, klein genug fuers Repo. Gesammelt
    wird erst ab WALLET_FENSTER_AB_N, weil nur ranglistenreife Wallets ein Fenster brauchen und
    2.573 Wallets mit n<8 die Datei sonst verdreifachen wuerden.
    """
    tag = (now.isoformat()[:10] if hasattr(now, "isoformat") else str(now)[:10])
    if not s.get("firstTs"):
        s["firstTs"] = tag
    s["lastTs"] = tag
    if (s.get("n") or 0) < WALLET_FENSTER_AB_N:
        return s
    # WICHTIG: neue Liste statt in-place. update_wallet_track kopiert die scores nur flach
    # (dict(s)) — die Liste waere sonst dieselbe wie in `prev` und wuerde rueckwirkend mutiert.
    fenster = list(s.get("recent") or [])
    fenster.append([tag, round(float(clv), 2), 1 if win else 0])
    s["recent"] = fenster[-WALLET_FENSTER:]
    return s


def fenster_bilanz(s: dict) -> dict | None:
    """Was die Wallet in ihren letzten Auflösungen geliefert hat — None, wenn das Fenster leer ist.

    Bewusst KEIN Urteil: liefert nur die Zahlen samt `n`, damit der Aufrufer selbst entscheidet,
    ab wann er sie ernst nimmt."""
    r = (s or {}).get("recent") or []
    # Nur wohlgeformte Tripel zaehlen. `von`/`bis` kommen aus DIESEN Eintraegen, nicht blind aus
    # r[0]/r[-1] — sonst kippt eine einzige kaputte Zeile in der Datei die ganze Bilanz.
    gut = [x for x in r if isinstance(x, (list, tuple)) and len(x) >= 3]
    if not gut:
        return None
    try:
        clv = [float(x[1]) for x in gut]
    except (TypeError, ValueError):
        return None
    wins = sum(1 for x in gut if x[2])
    return {"n": len(clv), "clv": round(sum(clv) / len(clv), 2),
            "hit": round(wins / len(clv), 4), "von": gut[0][0], "bis": gut[-1][0]}


def enrich_wallet_pnl(scores, get, budget, min_n=5):
    """Lebenszeit-P&L je bewertetem Wallet nachziehen → scores[w]['pnl'] (USD). Priorisiert Wallets mit
    der meisten getrackten Historie, hart per budget[0] (Mutable-Counter) gedeckelt. Wer nicht drankommt,
    behält seinen vorherigen pnl (aus prev — update_wallet_track kopiert prev-scores). REIN/testbar."""
    if not isinstance(scores, dict):
        return 0
    # 29.08.2026 (Lucas, Status-Tab: „408 'bewiesene' Wallets ohne P&L-Daten") — 🔴 DAS BUDGET
    # WURDE JEDEN LAUF AN DIESELBEN WALLETS VERFUETTERT. Sortiert wurde rein nach Historie (-n),
    # also holte jeder Lauf erneut die Top-60 nach n — und wer auf Platz 61 stand, bekam nie einen
    # P&L. Gemessen: von 159 Wallets oberhalb des echten Push-Gates hatten 48 einen Wert und 111
    # keinen, und daran haette sich durch blosses Weiterlaufen nichts geaendert.
    # Jetzt zuerst die, zu denen wir noch KEIN pnl kennen; erst danach werden bekannte
    # aufgefrischt. Damit ist die Abdeckung nach zwei, drei Laeufen vollstaendig statt nie.
    cand = sorted((w for w, sc in scores.items() if isinstance(sc, dict) and (sc.get("n") or 0) >= min_n),
                  key=lambda w: (isinstance(scores[w].get("pnl"), (int, float)),
                                 -(scores[w].get("n") or 0)))
    n = 0
    for w in cand:
        if budget[0] <= 0:
            break
        budget[0] -= 1
        pnl = _lifetime_pnl(get(PNL_API.format(user=w)))
        if pnl is not None:
            scores[w]["pnl"] = pnl
            n += 1
    return n


def _enrich_whales_avg(whales, label_token, cache, get, budget):
    """Top-Whales um ihren ECHTEN Ø-Einstieg (avgPrice aus /positions) anreichern → wh['avgPrice'].
    cache {wallet: positions-data} (je Wallet EIN Call, marktübergreifend); budget=[rest_calls]
    (Mutable-Counter, deckelt die Calls je Lauf). get(url)->data. REIN/testbar (get injizierbar)."""
    for wh in (whales or []):
        tok = label_token.get(wh.get("side"))
        w = wh.get("wallet")
        if not tok or not w:
            continue
        if w not in cache:
            if budget[0] <= 0:
                continue
            budget[0] -= 1
            cache[w] = get(POSITIONS.format(user=w)) or []
        ap = _avg_from_positions(cache[w], tok)
        if ap is not None:
            wh["avgPrice"] = ap
    return whales


RESOLVE_LOOKUP_MAX = int(os.environ.get("POLY_RESOLVE_LOOKUP_MAX") or 60)


def backfill_resolutions_by_slug(prev_close, seen_keys, get=_get, cap=RESOLVE_LOOKUP_MAX):
    """(02.08.2026, Lucas) Settlement-Key-Fix an der Wurzel: Der Key IST der rohe Event-Slug, und dieselbe
    Partie kann unter mehreren Slugs laufen (kuratierter Kurz-Slug offen, voller Event-Slug bei Auflösung)
    → die Auflösung landete unter einem ANDEREN Key als die offene Position → Wallet-/Shortlist-Track
    rechnete v.a. Esports nie ab. Fix: getrackte Märkte (waren in prev broad_close offen), die im aktuellen
    Lauf NICHT mehr auftauchen (= angepfiffen/vorbei), GEZIELT per EIGENEM Slug nachschlagen und, wenn
    aufgelöst, als resolved-Zeile unter DEMSELBEN Key zurückgeben. So matcht die Auflösung garantiert die
    offene Position. REIN/testbar (get injizierbar), defensiv (nie werfen), gedeckelt (cap Calls/Lauf)."""
    out = []
    if not isinstance(prev_close, dict):
        return out
    # broad_close wächst über die Zeit → Budget den ZULETZT erfassten (gerade angepfiffenen) Märkten
    # geben, nicht uralten hängengebliebenen Keys. Sort: neuestes capturedAt zuerst.
    cand = [(k, str(v.get("capturedAt") or "")) for k, v in prev_close.items()
            if isinstance(v, dict) and not v.get("resolved") and k not in seen_keys]
    cand.sort(key=lambda kv: kv[1], reverse=True)
    for key, _cap_ts in cand[:cap]:
        try:
            page = get(f"{GAMMA}?slug={key}&closed=true")
            ev = page[0] if isinstance(page, list) and page else None
            if not isinstance(ev, dict):
                continue
            oc = _outcomes(ev)
            rp = {o["label"]: o["price"] for o in oc if o.get("price") is not None}
            if rp and winner_from_prices(rp):   # nur eindeutig aufgelöst (ein Preis ~1.00)
                out.append({"key": key, "league": _league_from_slug(key),
                            "resolved": True, "resolvedPrices": rp,
                            "hoursToKickoff": None, "totalUsd": 0, "shares": {}, "prices": {}})
        except Exception:
            continue
    return out


def fetch_markets(live_only=False):
    """Alle Poly-Sportmärkte über die Sport-Tags. Real, defensiv, gedeckelt. Rückgabeformat siehe
    capture()/resolutions(): {key, league, hoursToKickoff, totalUsd, shares, prices,
    resolved, resolvedPrices}. Bei jedem Fehler wird der Markt übersprungen, nie geworfen."""
    now = _now()
    min_vol, _ = _cfg()
    tags = _tags()
    # 16.08.2026 (Lucas): entdeckte Fussball-Ligen mitfetchen -> JEDE Liga voll erfasst, nicht nur hartkodierte.
    _discovered = set()
    tags = list(dict.fromkeys(list(tags) + sorted(_load_league_registry())))
    markets = []
    raw_by_tag = {}                      # je Tag: wie viele ROH-Events kamen (offen+aufgelöst)
    seen = set()                         # Dedup: ein Markt kann unter mehreren Tags liegen (cs2 ⊂ esports)
    candidates = []                      # near-kickoff 2-Wege-Kandidaten, VOR den Holders-Calls
    upcoming = {}                        # money-map: weiter draussen liegende Sport-Maerkte, NUR Preis+Vol (kein Holder-Call)

    def _ingest(open_evs, closed_evs, league_of, sport_of):
        """Ein Fetch-Ergebnis einsammeln. `league_of(ev, key)` liefert das Liga-Label.
        Anpfiff-Fenster (0<htk<=3h) + Volumen sind der eigentliche Sport-Filter."""
        # 1) Offene, near-kickoff Märkte SAMMELN (Holders-Call später, nach Volumen priorisiert)
        for ev in open_evs:
            try:
                key = ev.get("slug") or ev.get("id")
                if not key or (key, False) in seen:
                    continue
                htk = _hours_to_ko(ev, now)
                cls = _capture_class(htk)
                # 01.09.2026: „vor"-Maerkte bekommen wie bisher ihren Preis/Volumen-Eintrag in
                # upcoming — und ZUSAETZLICH eine Chance auf den Holder-Call (eigenes Budget unten).
                # Reihenfolge wichtig: erst der gratis Eintrag, dann der Kandidat. Faellt der Call
                # aus (Budget leer), bleibt die Zeile trotzdem mit Preis+Volumen stehen.
                if cls == "vor" and not live_only:
                    uvol0 = float(ev.get("volume") or 0)
                    if uvol0 >= min_vol:
                        uoc0 = _outcomes(ev)
                        if len(uoc0) >= 2 and not _is_exhibition(uoc0):
                            up0 = {o["label"]: o["price"] for o in uoc0 if o["price"] is not None}
                            umv0 = _market_volume(ev, uoc0, uvol0)
                            if up0 and (key not in upcoming or umv0 > upcoming[key]["totalUsd"]):
                                upcoming[key] = {"league": league_of(ev, key), "sport": sport_of(ev, key),
                                                 "hoursToKickoff": round(htk, 2),
                                                 "totalUsd": round(umv0), "prices": up0}
                if cls is None:
                    # Money-Map (12.08.2026, Lucas): Sport-Markt weiter draussen (bis UPCOMING_WINDOW_H)
                    # GRATIS mit Preis+Vol mitnehmen -> Poly-Blase auch 12h vor Anpfiff, ohne Holder-Budget.
                    if not live_only and isinstance(htk, (int, float)) and 0 < htk <= UPCOMING_WINDOW_H:
                        uvol = float(ev.get("volume") or 0)
                        if uvol >= min_vol:
                            uoc = _outcomes(ev)
                            if len(uoc) >= 2 and not _is_exhibition(uoc):
                                uprices = {o["label"]: o["price"] for o in uoc if o["price"] is not None}
                                umvol = _market_volume(ev, uoc, uvol)   # 15.08.2026 (Lucas): Markt- statt Event-Volumen
                                if uprices and (key not in upcoming or umvol > upcoming[key]["totalUsd"]):
                                    upcoming[key] = {"league": league_of(ev, key), "sport": sport_of(ev, key), "hoursToKickoff": round(htk, 2),
                                                     "totalUsd": round(umvol), "prices": uprices}
                    continue        # ausserhalb Erfassungs-(Holder-)Fenster
                if live_only and cls != "live":
                    continue        # Live-only Schnell-Lauf: Vor-Spiel-Maerkte ueberspringen        # kein unmittelbarer Anpfiff → kein Sportspiel (Politik/Krypto raus)
                vol = float(ev.get("volume") or 0)
                if vol < min_vol:
                    continue
                oc = _outcomes(ev)
                if len(oc) < 2:
                    continue
                if _is_exhibition(oc):
                    continue                 # 15.08.2026 (Lucas): Legenden-/Show-Match = kein Signal
                seen.add((key, False))
                mvol = _market_volume(ev, oc, vol)   # 15.08.2026 (Lucas): Markt- statt Event-Volumen
                candidates.append((vol, key, league_of(ev, key), sport_of(ev, key), htk, oc, cls == "live", mvol, cls))
            except Exception:
                continue

        # 2) Kürzlich aufgelöste Märkte → Gewinner (settlet auf 1.00) — kein Holders-Call nötig
        for ev in (() if live_only else closed_evs):
            try:
                key = ev.get("slug") or ev.get("id")
                if not key or (key, True) in seen:
                    continue
                oc = _outcomes(ev)
                rp = {o["label"]: o["price"] for o in oc if o["price"] is not None}
                if rp and not _is_exhibition(oc):
                    seen.add((key, True))
                    markets.append({"key": key, "league": league_of(ev, key), "sport": sport_of(ev, key),
                                    "resolved": True, "resolvedPrices": rp,
                                    "hoursToKickoff": None, "totalUsd": 0, "shares": {}, "prices": {}})
            except Exception:
                continue

    # A) Kuratierte Sport-Tags (präzises Liga-Label = Tag)
    for tag in tags:
        open_evs = _gamma_events(tag, closed=False)
        closed_evs = _gamma_events(tag, closed=True)
        raw_by_tag[tag] = len(open_evs) + len(closed_evs)
        _ingest(open_evs, closed_evs, lambda ev, key, _t=tag: _t.upper(), lambda ev, key, _t=tag: _tag_category(_t))
        _discovered |= _discover_football_tags(open_evs) | _discover_football_tags(closed_evs)

    # B) Tag-LOSER Volumen-Sweep — fängt JEDE Sportart mit Volumen ein, auch ohne kuratierten Tag
    # (nimmt der „Liga fehlt still"-Klasse die Grundlage). Dedup gegen A über `seen`; Liga aus Slug.
    sweep_open = _gamma_top(closed=False)
    sweep_closed = _gamma_top(closed=True)
    before = len(candidates) + len(markets)
    _ingest(sweep_open, sweep_closed, lambda ev, key: _league_from_slug(key), lambda ev, key: _event_sport(ev))
    _discovered |= _discover_football_tags(sweep_open) | _discover_football_tags(sweep_closed)
    sweep_added = (len(candidates) + len(markets)) - before

    # 21.07.2026 (Lucas: „mehr Sport?"): das Holders-Budget nach VOLUMEN vergeben — die größten
    # near-kickoff-Märkte zuerst, EGAL welche Sportart. Vorher lief es in Tag-Reihenfolge → die
    # täglichen Ligen (MLB/Tennis/Esport) fraßen die 60 Calls, ein UFC-Main-Event am Listen-Ende
    # bekam nie einen Geld-Split. Jetzt kriegt der wertvollste Markt jeder Sportart seine Chance.
    # Nicht-„vor" wie bisher rein nach Volumen. „vor" zusaetzlich mit Fussball-Vorrang — s. oben.
    candidates.sort(key=lambda c: (0 if c[8] != "vor" else (0 if _vor_ist_fussball(c[2], c[3]) else 1), -c[0]))
    holder_calls = 0
    live_calls = 0     # 11.08.2026 (Lucas Stufe 1): eigener Live-Deckel, additiv zu pre
    # Ø-Einstieg-Anreicherung (CLV-Fix): eine /positions-Abfrage je Wallet, marktübergreifend gecacht,
    # hart gedeckelt. Fällt der Import/Fetch aus, läuft alles wie bisher weiter (nur ohne avgPrice).
    _pos_cache, _pos_budget = {}, [MAX_POSITION_CALLS]
    # Orderbuch/Trades-Getter (Poly-Terminal). Defensiv: Import faellt aus -> keine Buecher, Rest laeuft.
    _bt_get, _book_budget = None, [MAX_BOOK_CALLS]
    if FETCH_BOOK:
        try:
            from fetch_wm_poly_smartmoney import _http_get as _bt_get
        except Exception:
            _bt_get = None
    _avg_get = None
    if FETCH_AVGPRICE and not live_only:
        try:
            from fetch_wm_poly_smartmoney import _http_get as _avg_get
        except Exception:
            _avg_get = None
    vor_calls = 0
    for vol, key, league, sport, htk, oc, is_live, mvol, _cls in candidates:
        # 15.08.2026 (Lucas): Budget erschoepft ODER kein Geld-Split -> trotzdem Preis+Vol-Zeile fuer die
        # Money-Map (ohne Whale-Split). Sonst verschwindet ein near-KO-Spiel wie Sevilla-Rayo komplett,
        # obwohl Poly den Markt hat (fiel nur aus dem 90er-Holder-Budget). REIN additiv.
        _over = (live_calls >= MAX_HOLDER_CALLS_LIVE) if is_live \
            else (vor_calls >= MAX_HOLDER_CALLS_VOR) if _cls == "vor" \
            else (holder_calls >= MAX_HOLDER_CALLS)
        if _over:
            _pv = {o["label"]: o["price"] for o in oc if o["price"] is not None}
            if _pv:
                markets.append({"key": key, "league": league, "sport": sport, "hoursToKickoff": htk,
                                "totalUsd": round(mvol), "shares": {}, "prices": _pv, "whales": [],
                                "live": is_live, "resolved": False, "resolvedPrices": {}, "tokens": _tokens_of(oc)})
            continue
        try:
            mm = _market_money(oc)     # 25.07.2026: EIN Fetch → Shares + Einzel-Wale
        except Exception:
            mm = None
        if is_live:
            live_calls += 1
        elif _cls == "vor":
            vor_calls += 1          # eigenes Budget — kann den Close-Freeze nicht aushungern
        else:
            holder_calls += 1
        if not mm:
            _pv = {o["label"]: o["price"] for o in oc if o["price"] is not None}
            if _pv:
                markets.append({"key": key, "league": league, "sport": sport, "hoursToKickoff": htk,
                                "totalUsd": round(mvol), "shares": {}, "prices": _pv, "whales": [],
                                "live": is_live, "resolved": False, "resolvedPrices": {}, "tokens": _tokens_of(oc)})
            continue
        shares = mm["shares"]
        prices = {o["label"]: o["price"] for o in oc if o["price"] is not None}
        _whales = mm.get("whales") or []
        # 01.09.2026 — „vor"-Markt: die Anteile gehen NUR in die upcoming-Datei, nicht in `markets`.
        # `markets` speist Close-Freeze, Live-Store und Historie; ein Markt 5h vor Anpfiff hat dort
        # nichts verloren (der Freeze wuerde ihn ohnehin verwerfen, aber die anderen Verbraucher
        # nicht). So bleibt die Aenderung auf genau die Quelle beschraenkt, aus der `pick_poly`
        # ausserhalb des Freeze liest — minimale Angriffsflaeche.
        if _cls == "vor":
            _u = upcoming.get(key)
            if _u is not None:
                _u["shares"] = shares
                _u["whales"] = _whales[:12]     # gedeckelt: die Datei wird committet
            continue
        if _avg_get and _whales:
            try:
                _enrich_whales_avg(_whales, {o["label"]: o.get("token") for o in oc if o.get("token")},
                                   _pos_cache, _avg_get, _pos_budget)
            except Exception:
                pass
        _mrow = {"key": key, "league": league, "sport": sport,
                 "hoursToKickoff": htk, "totalUsd": round(mvol),
                 "shares": shares, "prices": prices, "whales": _whales,
                 "live": is_live,
                 "resolved": False, "resolvedPrices": {}, "tokens": _tokens_of(oc)}
        if _bt_get and _book_budget[0] > 0:
            try:
                _enrich_book_trades(_mrow, oc, _bt_get, _book_budget)
            except Exception:
                pass
        markets.append(_mrow)
    fetch_markets.sweep_stats = {"sweepOpen": len(sweep_open), "sweepClosed": len(sweep_closed),
                                 "sweepAdded": sweep_added}
    fetch_markets.upcoming = upcoming

    live = {t: n for t, n in raw_by_tag.items() if n}
    _sw = fetch_markets.sweep_stats
    print(f"  Gamma: {len(markets)} Markt-Zeilen über {len(tags)} Tags + Volumen-Sweep · "
          f"{len(candidates)} near-KO-Kandidaten · {holder_calls} Pre- + {live_calls} Live-Holders-Calls (nach Volumen)")
    print(f"  Roh-Events je Tag (nur >0): {live}")
    print(f"  Volumen-Sweep (tag-los): {_sw['sweepOpen']} offen · {_sw['sweepClosed']} aufgelöst "
          f"· {_sw['sweepAdded']} zusätzlich gefunden (Ligen, die kein Tag abdeckte)")
    # (02.08.2026, Lucas) Getrackte, aber verschwundene Märkte GEZIELT per eigenem Slug auflösen —
    # die Auflösung landet damit unter DEMSELBEN Key wie die offene Position (fixt den Settlement-
    # Key-Mismatch, v.a. Esports). Additiv/defensiv: schlägt es fehl, bleibt alles wie bisher.
    try:
        _seen_open = {c[1] for c in candidates} | {m.get("key") for m in markets}
        _bf = backfill_resolutions_by_slug(_load(CLOSE_FILE), _seen_open)
        if _bf:
            markets += _bf
            print(f"  \U0001f501 {len(_bf)} getrackte Markt-Auflösung(en) per Slug nachgezogen (Key-Match)")
    except Exception as _e:
        print(f"  Resolution-Backfill übersprungen (nicht fatal): {_e}")
    _save_league_registry(_discovered)   # 16.08.2026 (Lucas): neu entdeckte Fussball-Ligen persistieren -> naechster Lauf fetcht sie voll
    fetch_markets.discovered = sorted(_discovered)   # Diagnose
    fetch_markets.raw_by_tag = raw_by_tag   # 21.07.2026: für die Diagnose im Output
    return markets


def _entry_age_days(entry, now):
    """Alter eines Frozen-Eintrags in Tagen (capturedAt). None = nicht bestimmbar. REIN."""
    try:
        ct = datetime.fromisoformat(str(entry.get("capturedAt")).replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return None
    return (now - ct).total_seconds() / 86400.0


def _stamp_resolutions(out, markets, resolutions, now):
    """Aufloesung IN den Frozen-Eintrag stempeln (resolved/resolvedPrices/resolvedAt). REIN.

    24.08.2026 (Lucas, "$41 Mio Whale-Geld auf fertigen Spielen"): Der Geister-Prune von 06.08.
    lief ins Leere. Er verschont Maerkte, die in DIESEM Lauf abrechnen (`key in resolving`) --
    Gamma liefert aber jeden geschlossenen Event bei JEDEM Lauf wieder mit, also war fast jeder
    Geister-Key dauerhaft prune-immun, ohne dass die Aufloesung je im Eintrag ankam (919 von 928
    Geistern hatten sie laengst in poly_resolutions.json). Erst das Stempeln macht den Eintrag
    ehrlich: aufgeloest statt still "live" -- Guard, Views und Wallet-Track sehen dasselbe.
    Zwei Quellen: die resolved-Zeilen dieses Laufs (mit Preisen) und das rollierende
    Aufloesungs-Ledger (Nachzuegler, nur Gewinner). Stempelt nie ueber ein bestehendes resolved.
    """
    res = {}
    for m in markets or []:
        if isinstance(m, dict) and m.get("resolved") and m.get("key"):
            res[m["key"]] = {"prices": m.get("resolvedPrices") or {}}
    for k, v in (resolutions or {}).items():
        if k in res or not isinstance(v, dict):
            continue
        w = v.get("winner")
        if w:
            res[k] = {"winner": w}
    n = 0
    for key, info in res.items():
        e = out.get(key)
        if not isinstance(e, dict) or e.get("resolved"):
            continue
        e["resolved"] = True
        if info.get("prices"):
            e["resolvedPrices"] = info["prices"]
        if info.get("winner"):
            e["resolvedWinner"] = info["winner"]
        e["resolvedAt"] = now.isoformat()
        n += 1
    return n


def capture(markets, frozen, now=None, min_vol=MIN_VOL_USD, grace_h=GHOST_GRACE_H,
            resolutions=None, resolved_keep_days=CLOSE_RESOLVED_KEEP_DAYS):
    """Nah am Anpfiff einfrieren (Geld-Verteilung + Preis + Liga). REIN, testbar."""
    now = now or _now()
    out = dict(frozen or {})
    for m in markets or []:
        htk = m.get("hoursToKickoff")
        try:
            htk = float(htk)
        except (TypeError, ValueError):
            continue
        if not (0 < htk <= PMA.CAPTURE_WINDOW_H) or float(m.get("totalUsd") or 0) < min_vol:
            continue
        key = m.get("key")
        prev = out.get(key)
        if prev is not None and prev.get("hoursToKickoff", 99) <= htk:
            continue
        out[key] = {"shares": m.get("shares") or {}, "prices": m.get("prices") or {},
                    "league": m.get("league"), "sport": m.get("sport"), "totalUsd": round(float(m.get("totalUsd") or 0)),
                    "whales": m.get("whales") or [],   # 25.07.2026 (Lucas): Einzel-Wale je Markt (c)
                    "hoursToKickoff": round(htk, 2), "capturedAt": now.isoformat(),
                    # 24.08.2026: Token mitfrieren (Direkt-Order aus „Heute") — nur fuer offene
                    # Maerkte relevant, aufgeloeste Eintraege tragen ihn nie -> Datei bleibt schlank.
                    **({"tokens": m["tokens"]} if m.get("tokens") else {}),
                    **({"book": m["book"]} if m.get("book") else {}),
                    **({"trades": m["trades"]} if m.get("trades") else {})}
    # 06.08.2026 (Lucas): Geister-Maerkte prunen. ko = capturedAt + hoursToKickoff; liegt der mehr als
    # grace_h in der Vergangenheit UND ist der Markt nicht resolved -> raus. Aufgeloeste Snapshots bleiben
    # (Treffer-Auswertung); ebenso Maerkte, die GERADE in diesem Lauf abrechnen (deren frozen-Close braucht
    # der Wallet-Track als CLV-Referenz). Nicht parsebare Zeit/htk bleibt konservativ drin.
    resolving = {m.get("key") for m in (markets or []) if m.get("resolved")}
    # 24.08.2026: ERST die Aufloesung in den Eintrag stempeln -- sonst bleibt ein aufgeloester
    # Markt via `resolving` ewig prune-immun UND sieht fuer jede Flaeche weiter "live" aus.
    _stamp_resolutions(out, markets, resolutions, now)
    for key in list(out.keys()):
        e = out.get(key)
        if not isinstance(e, dict):
            continue
        if e.get("resolved"):
            _age_d = _entry_age_days(e, now)
            if _age_d is not None and _age_d > resolved_keep_days:
                del out[key]      # abgerechnet und alt -> raus (Retention)
            continue
        if key in resolving:
            continue
        htk_e = e.get("hoursToKickoff")
        if not isinstance(htk_e, (int, float)):
            continue
        try:
            ct = datetime.fromisoformat(str(e.get("capturedAt")).replace("Z", "+00:00"))
            past_h = (now - (ct + timedelta(hours=float(htk_e)))).total_seconds() / 3600.0
        except (TypeError, ValueError):
            continue
        if past_h > grace_h:
            del out[key]
    return out


def capture_live(markets, prev, now=None, min_vol=MIN_VOL_USD, keep_h=LIVE_KEEP_H):
    """Live-Snapshot-Speicher fuer LAUFENDE Maerkte. REIN/testbar. Anders als capture(): KEIN Einfrieren
    -- ein Live-Markt bewegt sich, also immer der jeweils AKTUELLE Stand (shares/prices/whales). Prunt
    Eintraege, die seit keep_h nicht mehr gesehen wurden (Spiel vorbei/aufgeloest). Getrennt vom Vor-
    Spiel-Freeze in capture(), damit die Auswertungs-Basis unangetastet bleibt. 11.08.2026 (Lucas Stufe 1)."""
    now = now or _now()
    out = {k: dict(v) for k, v in (prev or {}).items() if isinstance(v, dict)}
    seen = set()
    for m in markets or []:
        if m.get("resolved"):
            continue
        key = m.get("key")
        if not key or float(m.get("totalUsd") or 0) < min_vol:
            continue
        htk = m.get("hoursToKickoff")
        out[key] = {"shares": m.get("shares") or {}, "prices": m.get("prices") or {},
                    "whales": m.get("whales") or [], "league": m.get("league"), "sport": m.get("sport"),
                    "totalUsd": round(float(m.get("totalUsd") or 0)),
                    "hoursToKickoff": round(float(htk), 2) if isinstance(htk, (int, float)) else None,
                    "capturedAt": now.isoformat(), "live": True,
                    # 24.08.2026: Token auch live mitschreiben — Live-Plays sollen genauso
                    # direkt setzbar sein wie Vor-Spiel-Plays.
                    **({"tokens": m["tokens"]} if m.get("tokens") else {}),
                    **({"book": m["book"]} if m.get("book") else {}),
                    **({"trades": m["trades"]} if m.get("trades") else {})}
        seen.add(key)
    cutoff = now - timedelta(hours=keep_h)
    for k in list(out.keys()):
        if k in seen:
            continue
        e = out.get(k)
        try:
            last = datetime.fromisoformat(str(e.get("capturedAt")).replace("Z", "+00:00")) if isinstance(e, dict) else None
        except (TypeError, ValueError):
            last = None
        if not last or last < cutoff:
            del out[k]
    return out


def append_history(prev, markets, now=None, min_vol=MIN_VOL_USD,
                   max_points=HIST_MAX_POINTS, keep_h=HIST_KEEP_H):
    """Globale Poly-Preis-Zeitreihe fortschreiben. REIN/testbar. je Markt eine Liste von
    {ts, p:{label:preis}, v:volumen, htk, league}; deckelt auf max_points, prunt Märkte, die
    seit keep_h nicht mehr gesehen wurden (aufgelöst/vorbei). 25.07.2026 (Lucas ① Momentum)."""
    now = now or _now()
    out = {k: list(v) for k, v in (prev or {}).items() if isinstance(v, list)}
    seen = set()
    for m in markets or []:
        if m.get("resolved"):
            continue
        key = m.get("key")
        prices = m.get("prices") or {}
        if not key or not prices or float(m.get("totalUsd") or 0) < min_vol:
            continue
        htk = m.get("hoursToKickoff")
        pt = {"ts": now.isoformat(),
              "p": {k: round(float(v), 4) for k, v in prices.items() if isinstance(v, (int, float))},
              "v": round(float(m.get("totalUsd") or 0)),
              "htk": round(float(htk), 2) if isinstance(htk, (int, float)) else None,
              "league": m.get("league")}
        arr = out.get(key) or []
        arr.append(pt)
        out[key] = arr[-max_points:]
        seen.add(key)
    cutoff = now - timedelta(hours=keep_h)
    for k in list(out.keys()):
        if k in seen:
            continue
        arr = out[k]
        try:
            last = datetime.fromisoformat(str(arr[-1]["ts"]).replace("Z", "+00:00")) if arr else None
        except Exception:
            last = None
        if not last or last < cutoff:
            del out[k]
    return out


def update_wallet_track(prev, markets, now=None, keep_h=HIST_KEEP_H, frozen=None):
    """② Sharp-Wallet-Track. REIN/testbar. Merkt je (wallet,markt,seite) den Einstiegspreis (erster
    beobachteter Preis, als der Wal auftauchte); bei Markt-Auflösung wird die Position gewertet:
      clvPP = (Close − Einstieg)·100   (positiv = früh billig rein, Linie geschlagen → scharf)
      win   = Seite == Gewinner
    Rückgabe {open, scores{wallet:{n,clvSumPP,wins,usd,firstTs,lastTs,recent}}, updatedAt}.
    Global über alle Sportarten."""
    now = now or _now()
    prev = prev or {}
    openp = {k: dict(v) for k, v in (prev.get("open") or {}).items()}
    scores = {w: dict(s) for w, s in (prev.get("scores") or {}).items()}

    # 1) offene Whale-Positionen aus KOMMENDEN Märkten erfassen/auffrischen
    for m in markets or []:
        if m.get("resolved"):
            continue
        key, prices = m.get("key"), m.get("prices") or {}
        if not key or not prices:
            continue
        for wh in m.get("whales") or []:
            w, side = wh.get("wallet"), wh.get("side")
            price = prices.get(side)
            if not w or side is None or not isinstance(price, (int, float)):
                continue
            ok = f"{w}|{key}|{side}"
            _avg = wh.get("avgPrice")
            _avg = round(float(_avg), 4) if isinstance(_avg, (int, float)) and 0 < _avg < 1 else None
            e = openp.get(ok)
            if e is None:
                openp[ok] = {"wallet": w, "key": key, "side": side, "league": m.get("league"),
                             "firstPrice": round(float(price), 4), "firstTs": now.isoformat(),
                             "lastPrice": round(float(price), 4), "usd": round(float(wh.get("usd") or 0))}
                if _avg is not None:
                    openp[ok]["entryPrice"] = _avg
            else:
                e["lastPrice"] = round(float(price), 4)
                e["usd"] = round(float(wh.get("usd") or 0))
                e["league"] = m.get("league")
                if _avg is not None:
                    e["entryPrice"] = _avg   # Ø-Einstieg mitziehen (Wal stockt evtl. auf)

    # 2) Positionen werten, deren Markt gerade aufgelöst ist
    winners = {m.get("key"): winner_from_prices(m.get("resolvedPrices") or {})
               for m in (markets or []) if m.get("resolved")}
    for ok in list(openp.keys()):
        e = openp[ok]
        if e["key"] not in winners:
            continue
        # 26.07.2026 (Lucas: „CLV misst nicht"): CLV gegen die EINGEFRORENE Closing-Linie, nicht
        # gegen lastPrice. Der lastPrice wird vor Auflösung oft nur EINMAL gesehen (Holder-Call-Cap +
        # Top-N-Wale-Cutoff + schnelle Märkte) → bliebe = firstPrice → CLV fälschlich 0. Der Close
        # aus poly_money_broad_close.json ist der echte Schlusskurs. Fallback: lastPrice (Alt-Verhalten).
        _close = ((frozen or {}).get(e["key"]) or {}).get("prices") or {}
        _cp = _close.get(e["side"])
        close_ref = float(_cp) if isinstance(_cp, (int, float)) else e["lastPrice"]
        # Einstiegsanker: der ECHTE Ø-Einstieg (entryPrice aus /positions avgPrice), sonst der erste
        # gesehene Preis (Alt-Verhalten, strukturell ~0 — s. 28.07.2026-Fix). CLV = Close − Einstieg.
        entry = e.get("entryPrice")
        if entry is None:
            entry = e["firstPrice"]
        clv = (close_ref - entry) * 100
        s = scores.setdefault(e["wallet"], {"n": 0, "clvSumPP": 0.0, "wins": 0, "usd": 0})
        s["n"] += 1
        s["clvSumPP"] = round(s["clvSumPP"] + clv, 2)
        _win = bool(winners[e["key"]] and e["side"] == winners[e["key"]])
        if _win:
            s["wins"] += 1
        s["usd"] += e.get("usd") or 0
        _wallet_zeit(s, clv, _win, now)
        del openp[ok]

    # 3) verwaiste offene Positionen prunen (Markt seit keep_h nicht mehr gesehen)
    cutoff = now - timedelta(hours=keep_h)
    seen = {m.get("key") for m in (markets or [])}
    for ok in list(openp.keys()):
        e = openp[ok]
        if e["key"] in seen:
            continue
        try:
            first = datetime.fromisoformat(str(e["firstTs"]).replace("Z", "+00:00"))
        except Exception:
            first = None
        if not first or first < cutoff:
            del openp[ok]

    return {"open": openp, "scores": scores, "updatedAt": now.isoformat()}


def sharp_entries(prev, cur, min_n=4):
    """🔔 Sharp-im-Markt (25.07.2026, Lucas). REIN/testbar. NEUE offene Positionen (in cur, aber
    NICHT in prev) von bewiesen-scharfen Wallets (Score n≥min_n & Ø CLV > 0). Prev-vs-cur-Vergleich
    statt Zeitstempel → robust. Rückgabe absteigend nach Einsatz."""
    prev_open = set((prev or {}).get("open") or {})
    scores = (cur or {}).get("scores") or {}
    out = []
    for ok, e in ((cur or {}).get("open") or {}).items():
        if ok in prev_open:
            continue
        s = scores.get(e.get("wallet"))
        n = (s or {}).get("n", 0)
        if not s or n < min_n:
            continue
        avg = s["clvSumPP"] / n if n else 0
        hit = s.get("wins", 0) / n if n else 0
        pnl = s.get("pnl")
        if avg < SHARP_LIST_MIN_CLV:                       # Close nicht spürbar geschlagen → kein Beweis
            continue
        if hit < SHARP_LIST_MIN_HIT:                       # zu wenige Treffer
            continue
        if isinstance(pnl, (int, float)) and pnl < 0:  # bestätigter Verlierer → NICHT "scharf"
            continue
        out.append({"wallet": e["wallet"], "key": e["key"], "side": e["side"], "league": e.get("league"),
                    "price": e.get("firstPrice"), "usd": e.get("usd") or 0, "avgClv": round(avg, 1),
                    "hit": round(hit, 2), "n": n})
    out.sort(key=lambda x: -x["usd"])
    return out


def _format_sharp_alert(entries):
    lines = ["🔔 <b>Sharp im Markt</b> — bewiesen scharfe Wallet(s) frisch eingestiegen:", ""]
    for e in entries[:8]:
        w = e["wallet"]; short = w[:6] + "…" + w[-4:]
        lines.append(f"• {short} → <b>{e['side']}</b> @ {round((e.get('price') or 0) * 100)}¢ "
                     f"· {(e.get('league') or '').upper()} · ~${int(e.get('usd') or 0):,}")
        lines.append(f"   Track: Ø CLV +{e['avgClv']}pp · {round(e['hit'] * 100)}% Treffer · n{e['n']}")
    lines += ["", "Kein Auto-Bet — nur ein Signal. Selbst prüfen."]
    return "\n".join(lines)


def maybe_alert_sharp(prev, cur, min_n=4) -> int:
    """Alarm senden, wenn neue scharfe Einstiege da sind. Kür — darf den Lauf NIE kippen.
    Nutzt telegram_trades (Silent-Guard: leerer Token → False). Rückgabe: Anzahl alarmierter Einstiege."""
    ents = sharp_entries(prev, cur, min_n=min_n)
    if not ents:
        return 0
    # 05.08.2026 (Lucas): der bewiesen-scharfe frische Einstieg wird jetzt vom Whale-Watcher als volle
    # Karte (Paarung/Anpfiff/Preis/Link, strenges Wilson-Gate) mitgezogen - diese Textliste war redundant
    # + ein zweiter Push. Standard AUS; SHARP_LIST_PUSH=1 reaktiviert die alte Liste.
    if (os.environ.get("SHARP_LIST_PUSH") or "").strip().lower() not in ("1", "true", "yes", "on"):
        print("ℹ️  Sharp-Liste deaktiviert (Whale-Watcher uebernimmt scharfe Einstiege) -",
              len(ents), "Einstieg(e) nicht als Liste gepusht")
        return 0
    try:
        import telegram_trades
        telegram_trades.send_trades_message(_format_sharp_alert(ents))
    except Exception as exc:
        print("ℹ️  Sharp-Alarm übersprungen:", exc)
    return len(ents)


def resolutions(markets) -> dict:
    """{key: winner} aus den aufgelösten Poly-Märkten (settlet auf 1.00)."""
    out = {}
    for m in markets or []:
        if not m.get("resolved"):
            continue
        w = winner_from_prices(m.get("resolvedPrices") or {})
        if w:
            out[m.get("key")] = w
    return out


def prune_upcoming(prev, fresh, now=None, window_h=UPCOMING_WINDOW_H):
    """Money-Map (12.08.2026, Lucas): frische upcoming-Erfassung ueber die alte legen + Vergangenes prunen.
    Prunt Eintraege, deren rekonstruierter Anpfiff schon vorbei ist (dann greift ohnehin close/live) oder
    deren capturedAt aelter als window_h ist (Fetch fiel lange aus). REIN/testbar."""
    now = now or _now()
    out = {k: dict(v) for k, v in (prev or {}).items() if isinstance(v, dict)}
    for k, v in (fresh or {}).items():
        e = dict(v); e["capturedAt"] = now.isoformat(); out[k] = e
    cutoff = now - timedelta(hours=window_h)
    for k in list(out.keys()):
        e = out[k]
        try:
            cap = datetime.fromisoformat(str(e.get("capturedAt")).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            cap = None
        htk = e.get("hoursToKickoff")
        real_htk = (htk - (now - cap).total_seconds() / 3600.0) if (cap and isinstance(htk, (int, float))) else None
        if cap is None or cap < cutoff or (real_htk is not None and real_htk <= 0):
            del out[k]
    return out


def main_live() -> int:
    """Live-only Schnell-Lauf (11.08.2026, Lucas Stufe 1/A): NUR die Live-Erfassung -- laufende Maerkte
    holen, capture_live, Live-History. Ueberspringt den schweren Vor-Spiel-Teil (Wallet-P&L, Eval, Cross-
    Sport, jsdom); laeuft in Sekunden statt Minuten -> eng taktbar, ohne den Runner zu blockieren."""
    min_vol, _ = _cfg()
    # 12.08.2026 (Lucas): Poly-Fetch kann am Runner scheitern (Geoblock/Rate-Limit). Frueher crashte
    # main_live dann VOR dem Schreiben -> die Live-Datei fror auf dem letzten Stand ein (Spiele standen
    # 13h spaeter noch als "live"). Jetzt: bei Fetch-Fehler leer weiterlaufen -> capture_live prunt die
    # alten Eintraege (>LIVE_KEEP_H) raus, die Datei wird ehrlich leer statt eingefroren.
    try:
        markets = fetch_markets(live_only=True)
    except Exception as e:
        print(f"[LIVE-only] fetch_markets fehlgeschlagen ({e!r}) -> nur pruning, kein Freeze auf altem Stand")
        markets = []
    live = [m for m in markets if m.get("live")]
    live_store = capture_live(live, _load(LIVE_FILE), min_vol=min_vol)
    write_json_atomic((BASE / LIVE_FILE), live_store, indent=1)
    live_hist = append_history(_load(LIVE_HIST_FILE), live, min_vol=min_vol,
                               max_points=LIVE_HIST_MAX_POINTS, keep_h=LIVE_HIST_KEEP_H)
    write_json_atomic((BASE / LIVE_HIST_FILE), live_hist, indent=1)
    print(f"[LIVE-only] {len(live_store)} laufende Maerkte erfasst (Tail {LIVE_TAIL_H}h, Deckel {MAX_HOLDER_CALLS_LIVE})")
    return 0


def main() -> int:
    min_vol, min_odds = _cfg()
    markets = fetch_markets()
    if not markets:
        # 10.08.2026 (Lucas): FRÜHER hier ganz abgebrochen — auf Leer-Läufen (Fetch scheitert: Quota/429/
        # Timeout) lief der Geister-Prune NIE, und der Close-Feed wuchs auf ~96% fertige Spiele (Integritäts-
        # Warnung „Geister-Märkte"). Jetzt auch OHNE frischen Fetch prunen: capture([], frozen) fügt nichts
        # hinzu, wirft nur die Märkte raus, die > GHOST_GRACE_H nach Anpfiff und unaufgelöst sind.
        frozen = capture([], _load(CLOSE_FILE), resolutions=_load(RESOLUTIONS_FILE))
        write_json_atomic((BASE / CLOSE_FILE), frozen, indent=1)
        live_store = capture_live([], _load(LIVE_FILE))   # Live-Speicher auch auf Leer-Laeufen prunen
        write_json_atomic((BASE / LIVE_FILE), live_store, indent=1)
        _upc = prune_upcoming(_load(UPCOMING_FILE), {})   # Money-Map: nur Vergangenes prunen (kein frischer Fetch)
        write_json_atomic((BASE / UPCOMING_FILE), _upc, indent=1)
        print(f"ℹ️  Keine Poly-Märkte — Close-Feed nur von Geistern gepruned ({len(frozen)} bleiben).")
        return 0
    pre  = [m for m in markets if not m.get("live")]   # Vor-Spiel + aufgeloest: bestehende Pipeline unveraendert
    live = [m for m in markets if m.get("live")]        # 11.08.2026 (Lucas Stufe 1): laufende Spiele, eigener Datenpfad
    frozen = capture(pre, _load(CLOSE_FILE), min_vol=min_vol, resolutions=_load(RESOLUTIONS_FILE))
    write_json_atomic((BASE / CLOSE_FILE), frozen, indent=1)

    # ① Momentum (25.07.2026): globale Preis-Zeitreihe fortschreiben (Steam/Reversal über alle Sportarten)
    # Live-Datenpfad (11.08.2026, Lucas Stufe 1): laufende Maerkte in EIGENEN Speicher, getrennt vom
    # Vor-Spiel-Freeze oben. capture_live friert NICHT ein (Live bewegt sich) -> immer der aktuelle Stand.
    live_store = capture_live(live, _load(LIVE_FILE), min_vol=min_vol)
    write_json_atomic((BASE / LIVE_FILE), live_store, indent=1)
    live_hist = append_history(_load(LIVE_HIST_FILE), live, min_vol=min_vol,
                               max_points=LIVE_HIST_MAX_POINTS, keep_h=LIVE_HIST_KEEP_H)
    write_json_atomic((BASE / LIVE_HIST_FILE), live_hist, indent=1)
    print(f"[LIVE] {len(live_store)} laufende Maerkte erfasst (Tail {LIVE_TAIL_H}h, Deckel {MAX_HOLDER_CALLS_LIVE})")

    hist = append_history(_load(HIST_FILE), pre, min_vol=min_vol)
    write_json_atomic((BASE / HIST_FILE), hist, indent=1)

    # ② Sharp-Wallet-Track (25.07.2026): Einstieg→Close/Outcome je Whale werten (CLV/Treffer)
    prev_wtrack = _load(WTRACK_FILE)
    wtrack = update_wallet_track(prev_wtrack, pre, frozen=frozen)
    # 💰 Echte Lebenszeit-P&L je bewertetem Wallet nachziehen (user-pnl-api) — macht die „schärfste
    # Wallets"-Rangliste nach TATSÄCHLICHEM Gewinn möglich. Gedeckelt (POLY_PNL_MAX, Default 60),
    # defensiv gekapselt: fällt der Call/Endpoint aus, bleibt alles wie bisher (nur ohne pnl-Feld).
    try:
        _pnl_budget = [int(os.environ.get("POLY_PNL_MAX") or 60)]
        _n_pnl = enrich_wallet_pnl(wtrack.get("scores") or {}, _get, _pnl_budget, min_n=5)
        if _n_pnl:
            print(f"\U0001f4b0 Lifetime-P&L aktualisiert: {_n_pnl} Wallets")
    except Exception as _e:
        print(f"  P&L-Enrich uebersprungen (nicht fatal): {_e}")
    write_json_atomic((BASE / WTRACK_FILE), wtrack, indent=1)
    # 🔔 Sharp-im-Markt-Alarm: neue Einstiege bewiesen-scharfer Wallets → Telegram (Kür, nie fatal)
    # 📒 Rollierende Auflösungen (02.08.2026, Lucas) für den Shortlist-Paper-Tracker mitschreiben.
    try:
        _res = update_resolutions(_load(RESOLUTIONS_FILE), pre)
        write_json_atomic((BASE / RESOLUTIONS_FILE), _res, indent=1)
    except Exception as _e:
        print(f"  Resolutions-Update uebersprungen (nicht fatal): {_e}")
    n_alert = maybe_alert_sharp(prev_wtrack, wtrack)
    if n_alert:
        print(f"🔔 Sharp-Alarm: {n_alert} neue scharfe Einstiege gemeldet")

    rep = PMA.evaluate(frozen, resolutions(pre), min_odds=min_odds)
    rep["generatedAt"] = _now().isoformat()
    rep["minVolUsd"] = min_vol
    rep["scope"] = "broad_all_leagues"
    # 21.07.2026: welche Sport-Tags liefern überhaupt Events (statt zu raten, welche Poly hat)?
    rep["rawByTag"] = getattr(fetch_markets, "raw_by_tag", {})
    rep["sweepStats"] = getattr(fetch_markets, "sweep_stats", {})
    write_json_atomic((BASE / OUT_FILE), rep, indent=1)

    # Money-Map (12.08.2026, Lucas): breitere upcoming-Erfassung schreiben (Preis+Vol, kein Holder-Call)
    _upc = prune_upcoming(_load(UPCOMING_FILE), getattr(fetch_markets, "upcoming", {}) or {})
    write_json_atomic((BASE / UPCOMING_FILE), _upc, indent=1)
    print(f"[UPCOMING] {len(_upc)} Maerkte fuer die Money-Map (Preis+Vol, <={UPCOMING_WINDOW_H:.0f}h, kein Holder-Call)")

    print(f"=== Liegt das Geld richtig? BREIT · min Vol ${min_vol:.0f} · min Quote {min_odds} ===")
    print(f"Eingefroren {len(frozen)} · aufgelöst {rep['n']}")
    for lg in rep.get("byLeague", [])[:20]:
        print(f"  {lg['league']:18} n={lg['n']:3}  Geld {lg['moneyHitRate']*100:.0f}%  "
              f"Brier G {lg['brierMoney']} vs P {lg['brierPrice']}  → {lg['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main_live() if "--live-only" in sys.argv else main())
