#!/usr/bin/env python3
"""
fetch_wm_poly_prices.py
Fetches all WM 2026 Polymarket prices from the Gamma API.
  - Moneyline (1X2) via series_slug=soccer-fifwc
  - Totals (O/U) + BTTS + Spreads via {slug}-more-markets child events
Output: wm_poly_prices.json  — keyed by "{HOME_ID}-{AWAY_ID}"

Runs daily via GitHub Action to keep Polymarket prices current.
No API key required — Gamma API is public.
"""

import json
import os
import sys
import collections
import re
import urllib.request
import urllib.error

# 01.07.2026 (Lucas: „Poly-Odds die's nie gab" — z.B. Argentinien-Sieg @1.45): der GAMMA_URL-Fix
# (closed=false) holt jetzt auch KIND-/Spezialmärkte pro Spiel rein (…-first-to-score,
# …-second-half-result, …-first-half-result …). Die alte Blockliste kennt diese Suffixe nicht → sie
# wurden als Vollzeit-Moneyline gelabelt → Phantom-Edges. Robuste Allowlist statt endloser Blockliste:
# ein Basis-Moneyline-Event endet auf das Datum (…-YYYY-MM-DD). Kommt NACH dem Datum noch ein Suffix,
# ist es ein Kind-/Spezialmarkt → raus. (Slugs ohne Datum bleiben unangetastet → MLS-formatsicher.)
_DERIVED_SLUG_RE = re.compile(r"-\d{4}-\d{2}-\d{2}-")
from datetime import datetime, timezone, timedelta


def _vienna_hhmm(kickoff_iso):
    """HH:MM in Wiener Zeit (CEST UTC+2, WM-Fenster Juni/Juli) aus kickoff (UTC ISO).
    Normalisiert das unzuverlässige fx.time-Seed-Feld (mal Wien, mal Venue-Local,
    mal 00:00-Platzhalter) an der Quelle — kickoff ist die einzige Wahrheit."""
    try:
        return (datetime.fromisoformat(str(kickoff_iso).replace("Z", "+00:00"))
                + timedelta(hours=2)).strftime("%H:%M")
    except Exception:
        return None


def _flip_poly_orientation(p):
    """Dreht ein Poly-Ergebnis auf die umgekehrte Heim/Auswärts-Reihenfolge
    (Polymarket-Spiegel: Poly-Heim = unser Auswärts). Nur home/away-spezifische
    Felder swappen (hw↔aw + Tokens + ids/names); symmetrische Märkte (dr, O/U,
    BTTS) bleiben unverändert."""
    q = dict(p)
    q["homeId"],   q["awayId"]   = p.get("awayId"),   p.get("homeId")
    q["homeName"], q["awayName"] = p.get("awayName"), p.get("homeName")
    q["hw"],       q["aw"]       = p.get("aw"),       p.get("hw")
    q["hwTokens"], q["awTokens"] = p.get("awTokens"), p.get("hwTokens")
    q["hwCondition"], q["awCondition"] = p.get("awCondition"), p.get("hwCondition")
    return q


def _kickoff_passed(fx):
    """True wenn der Anpfiff vorbei ist. Edge-Alerts sind PRE-MATCH-Signale —
    ab Anpfiff ist eine Bewegung In-Game, kein handelbares Lag → kein Alert.
    Fehlender/unparsebarer kickoff → False (nicht versehentlich unterdrücken)."""
    ko = fx.get("kickoff")
    if not ko:
        return False
    try:
        return datetime.fromisoformat(str(ko).replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except Exception:
        return False


import cocobet_dataset as D   # 29.06.2026: dataset-aware (WM / Liga / MLS-Poly-Dry-Run)
from odds_plausibility import plausible_1x2, devig_1x2   # 19.07.2026: Platzhalter-Quoten raus
try:                                  # 28.08.2026: Slug-Gedächtnis atomar schreiben
    from safe_write import write_json_atomic
except Exception:                     # safe_write fehlt → lieber schreiben als abbrechen
    def write_json_atomic(path, data, *, indent=2):
        with open(path, "w", encoding="utf-8") as _f:
            json.dump(data, _f, ensure_ascii=False, indent=indent)

BASE         = os.path.dirname(os.path.abspath(__file__))
# Dataset-aware: wm_* | liga_* | mls_* je COCOBET_DATASET. WM-Verhalten unverändert.
OUT_FILE     = str(D.file("wm_poly_prices.json",      "liga_poly_prices.json"))
WM_FILE      = str(D.data_file())
POLY_HIST    = str(D.file("wm2026-poly-history.json", "liga-poly-history.json"))  # Poly price snapshots
ODDS_HIST    = str(D.file("wm2026-odds-history.json", "liga-odds-history.json"))  # Pinnacle odds snapshots

# ── Refactor 2026-06-06: Konstanten aus cocobet_config.json (Profile-aware) ──
try:
    from cocobet_config import CONFIG as _CFG
except Exception:
    _CFG = {}

def _cfg(section: str, key: str, default):
    """Sicherer Config-Lookup mit Default-Fallback (=aktueller Hardcode-Wert)."""
    if isinstance(_CFG, dict):
        return _CFG.get(section, {}).get(key, default)
    return default

# Edge-Momentum: Snapshot-Alter in Stunden für Vergleich (24h-Fenster)
# Bleibt hardcoded — reine Computation-Konstante, nicht Profil-relevant
DELTA_WINDOW_H = 24

# Edge-Alerts: Minimum Edge für Telegram-Notification
ALERT_EDGE_MIN_PP = float(_cfg("telegram", "alert_edge_min_pp", 5.0))
# 25.07.2026 (Lucas: „sind die Alerts valide?"). NEIN, wenn sie aus einem dünnen/illiquiden Poly-
# Markt kommen — dort ist der Poly-Preis Rauschen, kein Signal (StL-Colorado feuerte bei $369 Vol,
# LAFC-Auswärts als Longshot bei Poly 20.00). Zwei Gates, die im Alert-Pfad fehlten, obwohl der Rest
# der Poly-Logik sie längst hat: Mindest-Volumen + Longshot-Deckel auf der ALARMIERTEN Seite.
ALERT_MIN_VOL_USD   = float(_cfg("telegram", "alert_min_vol_usd", 5000.0))   # dünner Markt = kein Signal
ALERT_MAX_POLY_ODDS = float(_cfg("telegram", "alert_max_poly_odds", 6.0))    # Longshot-Preis unzuverlässig


def alert_market_liquid(fx, min_vol=None, max_odds=None) -> bool:
    """Ist der Poly-Markt liquide genug, dass die alarmierte Edge ein handelbares Signal ist?
    Poly-Volumen ≥ Schwelle UND die alarmierte Seite kein Longshot (Poly-Quote ≤ Deckel).
    REIN + testbar — dieselbe Prüfung fürs Alert-Gate (neue Edge + Steam-Lag)."""
    mv = ALERT_MIN_VOL_USD if min_vol is None else min_vol
    mo = ALERT_MAX_POLY_ODDS if max_odds is None else max_odds
    if (fx.get("vol") or 0) < mv:
        return False                          # dünner Markt → kein handelbares Signal
    pk = fx.get("bestEdgeKey")
    pp = fx.get(f"poly_{pk}") if pk else None
    if not pp or pp <= 0 or (1.0 / pp) > mo:
        return False                          # Longshot / kein Preis → Poly-Preis unzuverlässig
    return True

# Polymarket-Serie pro Datensatz (29.06.2026): WM=soccer-fifwc, MLS=soccer-mls (am 1. Live-Lauf
# am self-hosted Runner verifizieren — Gamma ist geoblockt, aus der Sandbox nicht prüfbar).
POLY_SERIES_SLUG = _cfg("poly", "series_slug", "soccer-fifwc")
# 12.07.2026 (Lucas, 1. MLS-Live-Lauf: „0 events received from Gamma API"): Der MLS-Filter ist
# KEIN series_slug. Gegen die echte API verifiziert:
#   · series_slug=soccer-mls  → 0 Events (existiert nicht)
#   · tag_slug=mls            → alle MLS-Spiele ✅
# Die MLS-Serie heißt „mls-2025" (saison-spezifisch → als Dauerfilter untauglich, bricht jede
# Saison). Der TAG „mls" ist stabil. Darum: Profile können statt series_slug einen tag_slug setzen
# (mls_default.poly.tag_slug = "mls"); kommende Ligen laufen vermutlich genauso über Tags.
POLY_TAG_SLUG = _cfg("poly", "tag_slug", "")
# 01.07.2026 (Lucas: „ich wette den KO-Modus seit Tagen auf Polymarket, natürlich haben sie die Spiele"):
# Die KO-Events FEHLTEN in unseren Daten (endeten am letzten Gruppenspieltag). Ursache war NICHT
# Polymarket — die R32-Events sind live+handelbar (verifiziert via /events?slug=fifwc-esp-aut-…) und
# unser parse_event verarbeitet sie sauber (teams-Array befüllt, Namen in POLY_NAME_TO_ID). Sie kamen
# nur nie im BATCH an: series_slug=…&limit=100&active=true ohne `closed=false`/Sortierung liefert bei
# 100+ Events (die Serie läuft seit März) die ÄLTESTEN 100 (Gruppenphase) → die neuesten KO-Events
# werden abgeschnitten. Fix: closed=false (nur offene Spiele) + newest-first + mehr Headroom.
# 04.08.2026 (Lucas, La-Liga-Trading): Polymarkets NEUE Sport-Ligen (LaLiga-Partnerschaft) laufen
# NICHT ueber tag_slug/series_slug (Namen), sondern ueber eine numerische series_id. Im Browser
# gegen gamma /sports verifiziert: La Liga = 10193 -> /events?series_id=10193 liefert die 30 Spiele
# (tag_slug=laliga -> 0). Profile koennen series_id setzen (komma-separiert fuer mehrere Ligen);
# das schlaegt tag_slug/series_slug. Mehrere IDs -> mehrere series_id=-Parameter (Gamma merged sie).
POLY_SERIES_ID = str(_cfg("poly", "series_id", "") or "").strip()
if POLY_SERIES_ID:
    _ids = [x.strip() for x in POLY_SERIES_ID.split(",") if x.strip()]
    _GAMMA_FILTER = "&".join(f"series_id={i}" for i in _ids)
elif POLY_TAG_SLUG:
    _GAMMA_FILTER = f"tag_slug={POLY_TAG_SLUG}"
else:
    _GAMMA_FILTER = f"series_slug={POLY_SERIES_SLUG}"
# 18.07.2026 (Lucas: „MLS-Trading muss laufen") — 🔴 DER FALSCHE SPIELTAG KAM AN.
# `order=startDate&ascending=false` sortiert nach dem ERSTELLUNGSDATUM des Marktes, nicht nach dem
# Anpfiff. Und die Gamma-API deckelt bei **100 Events pro Request** — `limit=300` wird ignoriert.
# Folge: wir bekamen nur die ZULETZT ANGELEGTEN Märkte (Spieltag 25./26.07.), während die Spiele am
# 22./23.07. — die einzigen mit Pinnacle-Quoten — hinten rausfielen. Ergebnis: NULL Überschneidung
# zwischen Poly und Pinnacle → keine Edge berechenbar → der Auto-Trader fand nie einen Kandidaten.
# Fix: paginieren (offset) statt auf einen Request zu hoffen. Verifiziert gegen die Live-API:
# Seite 1 liefert 25./26.07., Seite 2 die Spiele vom 22./23.07.
GAMMA_PAGE_LIMIT = 100          # hartes Server-Maximum
GAMMA_MAX_PAGES = 6             # 600 Events Headroom; bricht früher ab, wenn eine Seite kurz ist
# 28.08.2026 (Lucas: „wieso ist das von heute Bayern - Stuttgart nicht aufgelistet?") — 🔴 DIE
# SPIELNAHEN MÄRKTE FIELEN HINTEN RAUS. Beweis aus der Git-Historie von liga_poly_prices.json:
#   23.08. 21:49 UTC → 75 Fixtures, Spanne 24.08.–05.09. (bun-bay-stu-2026-08-28 drin, Vol 6.501 $)
#   24.08. 07:58 UTC → 73 Fixtures, Spanne 29.08.–06.09.
# In EINEM Lauf: 14 Spiele weg (alle sechs vom 28.08. + vier Serie A vom 29.08.), 12 neue vom
# 06.09. dazu — davon 11 mit Volumen 0. Rausgeflogen ist immer das ANPFIFF-NÄCHSTE Ende, neu
# dazugekommen immer das fernste. Das ist die Signatur einer harten Obergrenze plus
# `ascending=false` (fernste zuerst): oben kommt rein, unten — am Anpfiff — fällt raus.
# Zwei Ursachen kommen dafür in Frage, und beide werden hier behandelt:
#   (a) Gamma ignoriert `offset`, wenn MEHRERE `series_id` in einem Request stehen. Dann bricht
#       die Paginierung nach Seite 1 ab (`neu == 0`) und wir sehen nie mehr als ~100 Rohevents —
#       genau der beobachtete Deckel (Maximum über die ganze Historie: 75 Fixtures).
#   (b) Polymarket listet je Serie nur ein rollierendes Fenster.
# Fix (a): JE SERIE ein eigener paginierter Lauf statt eines gemergten Requests — keine Liga kann
# eine andere aushungern. Fix Sortierung: `ascending=true` — schneidet eine Kappung dann am fernen
# Ende ab (leere Märkte in 9 Tagen), nicht am handelbaren. Fix (b): der Slug-Rescue weiter unten.
# NICHT „nur die Sortierung drehen": das 01.07.-Problem (KO-Events fielen ab) war der
# spiegelverkehrte Fall. Deshalb holt fetch_gamma_events das ferne Ende NACH, sobald das
# Seitenbudget einer Serie tatsächlich ausgeschöpft wurde.
_GAMMA_RAW_TMPL = (
    "https://gamma-api.polymarket.com/events"
    "?{flt}&limit={limit}&offset={offset}&active=true&closed=false"
    "&order=startDate&ascending={asc}"
)


def gamma_url(limit=GAMMA_PAGE_LIMIT, offset=0, flt=None, ascending=True) -> str:
    return _GAMMA_RAW_TMPL.format(
        flt=flt or _GAMMA_FILTER, limit=limit, offset=offset,
        asc="true" if ascending else "false",
    )


# Rückwärtskompatibel (Tests/Logging): derselbe String mit fest gebackenem Filter.
GAMMA_URL_TMPL = _GAMMA_RAW_TMPL.replace("{flt}", _GAMMA_FILTER).replace("{asc}", "true")
GAMMA_URL = GAMMA_URL_TMPL.format(limit=GAMMA_PAGE_LIMIT, offset=0)   # nur fürs Logging/Tests

# Ein Filter pro Serie — NICHT gemergt (s. Ursache (a) oben).
GAMMA_SERIES_FILTERS = (
    [f"series_id={i}" for i in _ids] if POLY_SERIES_ID and _ids else [_GAMMA_FILTER]
)


def _gamma_pages(_get, flt, ascending):
    """(events, abgeschnitten) für EINEN Filter in EINER Richtung.

    `abgeschnitten` ist True, wenn die zuletzt geholte Seite VOLL war — dann wissen wir nicht,
    ob dahinter noch etwas liegt (Seitenbudget aus ODER `offset` wird ignoriert).
    """
    out, gesehen, voll = [], set(), False
    for seite in range(GAMMA_MAX_PAGES):
        page = _get(gamma_url(offset=seite * GAMMA_PAGE_LIMIT, flt=flt, ascending=ascending)) or []
        neu = 0
        for e in page:
            eid = e.get("id") or e.get("slug")
            if eid in gesehen:
                continue        # Überlappung zwischen Seiten ignorieren
            gesehen.add(eid)
            out.append(e)
            neu += 1
        voll = len(page) >= GAMMA_PAGE_LIMIT
        if not voll or neu == 0:
            break               # letzte Seite erreicht (oder offset wird ignoriert)
    return out, voll


def fetch_gamma_all(fetch=None, gamma_filter=None, ascending=True) -> list:
    """Alle offenen Events EINER Serie/eines Tags — über Seiten hinweg.

    Ohne Paginierung fehlten ganze Spieltage (s. Kommentar oben). `fetch` ist injizierbar (Tests).
    """
    return _gamma_pages(fetch or fetch_gamma, gamma_filter or _GAMMA_FILTER, ascending)[0]


def _event_datum(e) -> str:
    """YYYY-MM-DD eines Gamma-Events — eventDate, sonst startDate, sonst aus dem Slug."""
    for feld in ("eventDate", "startDate"):
        wert = str(e.get(feld) or "")[:10]
        if len(wert) == 10 and wert[4] == "-":
            return wert
    return slug_datum(e.get("slug")) or ""


def fetch_gamma_events(fetch=None) -> list:
    """Alle offenen Events ALLER konfigurierten Serien — je Serie ein eigener Lauf.

    Diagnose je Serie (Anzahl + Datumsspanne) steht bewusst im Log: der Ausfall vom 24.08. war
    fünf Tage lang unsichtbar, weil nur EINE Gesamtzahl geloggt wurde.
    """
    _get = fetch or fetch_gamma
    out, gesehen = [], set()
    for flt in GAMMA_SERIES_FILTERS:
        got, abgeschnitten = _gamma_pages(_get, flt, True)
        if abgeschnitten:
            print(f"  ⚠️  {flt}: Seitenbudget ausgeschöpft — hole zusätzlich das ferne Ende")
            got = got + _gamma_pages(_get, flt, False)[0]
        neu = 0
        for e in got:
            eid = e.get("id") or e.get("slug")
            if eid in gesehen:
                continue
            gesehen.add(eid)
            out.append(e)
            neu += 1
        _d = sorted(x for x in (_event_datum(e) for e in got) if x)
        spanne = f"  {_d[0]} … {_d[-1]}" if _d else ""
        print(f"  · {flt}: {len(got)} Events ({neu} neu){spanne}")
    return out
GAMMA_SLUG_URL = "https://gamma-api.polymarket.com/events?slug={slug}&markets=true"
CLOB_URL = "https://clob.polymarket.com/books?token_id={token_id}"

# ── Slug-Gedächtnis + Rescue (28.08.2026) ────────────────────────────────────
# Wenn ein Spiel aus dem Batch fällt (Ursache (a) ODER (b) oben), ist es NICHT weg: sein
# Gamma-Slug ist deterministisch und wir haben ihn schon einmal gesehen. Also merken wir jeden
# je gelieferten Slug und holen anpfiff-nahe Spiele, die im Batch fehlen, EINZELN per Slug nach.
# Das wirkt unabhängig davon, ob der Deckel bei uns oder bei Polymarket liegt.
SLUG_MEMO_FILE = str(D.file("wm_poly_slugs.json", "liga_poly_slugs.json"))
# Wie weit im Voraus gerettet wird. 3 Tage deckt Fr–So-Spieltage ab; alles darüber ist ohnehin
# illiquide (die am 24.08. neu dazugekommenen 06.09.-Märkte hatten 11 von 12 mal Volumen 0).
RESCUE_HORIZON_DAYS = int(_cfg("poly", "rescue_horizon_days", 3))
# Abgelaufene Slugs verfallen — sonst wächst die Datei über eine Saison auf tausende Einträge.
SLUG_MEMO_KEEP_DAYS = 2

_SLUG_DATE_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})$")


def slug_datum(slug):
    """YYYY-MM-DD aus einem Basis-Moneyline-Slug (…-2026-08-28) — sonst None.

    Kind-/Spezialmärkte (…-2026-08-28-more-markets) haben das Datum NICHT am Ende und liefern
    hier bewusst None: sie dürfen nie als eigenes Spiel ins Gedächtnis wandern.
    """
    m = _SLUG_DATE_RE.search(str(slug or ""))
    return m.group(1) if m else None


def lade_slug_memo(pfad=None) -> dict:
    """{key: {"slug": …, "date": …}} — fehlende/kaputte Datei ist kein Fehler, nur leer."""
    try:
        with open(pfad or SLUG_MEMO_FILE, encoding="utf-8") as f:
            memo = json.load(f)
        return memo if isinstance(memo, dict) else {}
    except Exception:
        return {}


def merke_slugs(memo, prices, heute=None) -> dict:
    """Neue Slugs aufnehmen, abgelaufene verwerfen. Gibt ein NEUES dict zurück.

    `prices` ist der fertige key→result-Dict des Laufs. Ein Lauf, der (wegen genau des Bugs, den
    das hier heilen soll) ein Spiel nicht geliefert hat, darf den gemerkten Slug NICHT löschen —
    deshalb wird nur ergänzt und rein nach Datum aufgeräumt, nie „nicht gesehen → raus".
    """
    heute = heute or datetime.now(timezone.utc).date().isoformat()
    grenze = (datetime.fromisoformat(heute).date() - timedelta(days=SLUG_MEMO_KEEP_DAYS)).isoformat()
    out = {}
    for key, eintrag in (memo or {}).items():
        if isinstance(eintrag, dict) and (eintrag.get("date") or "") >= grenze:
            out[key] = eintrag
    for key, p in (prices or {}).items():
        d = slug_datum((p or {}).get("slug"))
        if d and d >= grenze:
            out[key] = {"slug": p["slug"], "date": d}
    return out


def rescue_kandidaten(memo, gesehene_slugs, heute=None, tage=None) -> list:
    """Slugs anpfiff-naher Spiele, die im Batch FEHLEN — nach Datum sortiert.

    Fenster ist [heute, heute+tage]. „heute" ist bewusst inklusive: Bayern–Stuttgart fehlte am
    Spieltag selbst.
    """
    tage = RESCUE_HORIZON_DAYS if tage is None else tage
    heute = heute or datetime.now(timezone.utc).date().isoformat()
    bis = (datetime.fromisoformat(heute).date() + timedelta(days=tage)).isoformat()
    gesehen = set(gesehene_slugs or ())
    raus = []
    for eintrag in (memo or {}).values():
        if not isinstance(eintrag, dict):
            continue
        slug, d = eintrag.get("slug"), eintrag.get("date") or ""
        if not slug or slug in gesehen:
            continue
        if heute <= d <= bis:
            raus.append((d, slug))
    return [slug for _, slug in sorted(set(raus))]


def fehlende_nah_fixtures(wm, prices, jetzt=None, stunden=48) -> list:
    """Fixtures mit Anpfiff in den nächsten `stunden`, für die KEIN Poly-Preis vorliegt.

    Der Rescue oben kann nur Slugs holen, die wir schon einmal gesehen haben. Ein Spiel, das nie
    im Batch war, bliebe damit still unsichtbar — genau die Stille, die den Ausfall vom 24.08.
    fünf Tage lang verdeckt hat. Diese Liste ist die laute Variante.
    """
    if not isinstance(wm, dict):
        return []
    jetzt = jetzt or datetime.now(timezone.utc)
    bis = jetzt + timedelta(hours=stunden)
    haben = set(prices or {})
    raus = []
    fixtures = []
    for g in (wm.get("groups") or {}).values():
        fixtures.extend((g or {}).get("fixtures") or [])
    fixtures.extend(wm.get("koFixtures") or [])
    for fx in fixtures:
        ko = fx.get("kickoff")
        if not ko:
            continue
        try:
            kod = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        except Exception:
            continue
        if not (jetzt <= kod <= bis):
            continue
        h, a = str(fx.get("home")), str(fx.get("away"))
        # Poly spiegelt Spiele — beide Richtungen zählen als „vorhanden".
        if f"{h}-{a}" in haben or f"{a}-{h}" in haben:
            continue
        raus.append({
            "key": f"{h}-{a}",
            "kickoff": ko,
            "home": fx.get("homeName") or h,
            "away": fx.get("awayName") or a,
        })
    return sorted(raus, key=lambda x: x["kickoff"])


def hole_event_per_slug(slug, fetch=None):
    """Ein einzelnes Gamma-Event per Slug. Bereits aufgelöste Events werden verworfen —
    der Batch filtert `closed=false`, die Slug-Abfrage kann das nicht."""
    _get = fetch or fetch_gamma
    try:
        treffer = _get(GAMMA_SLUG_URL.format(slug=slug)) or []
    except Exception as e:
        print(f"  ⚠️  Rescue {slug} fehlgeschlagen: {e}")
        return None
    for ev in treffer:
        if ev.get("closed") is True or ev.get("active") is False:
            continue
        return ev
    return None

# ── Polymarket English team name → our WM team ID ─────────────────────────────
POLY_NAME_TO_ID = {
    "Germany":             "GER",
    "Curaçao":             "CUW",
    "Curacao":             "CUW",
    "Mexico":              "MEX",
    "South Africa":        "ZAF",
    "Korea Republic":      "KOR",
    "Czechia":             "CZE",
    "Czech Republic":      "CZE",
    "Canada":              "CAN",
    "Bosnia-Herzegovina":  "BIH",
    "Bosnia Herzegovina":  "BIH",
    "United States":       "USA",
    "USA":                 "USA",
    "Paraguay":            "PRY",
    "Qatar":               "QAT",
    "Switzerland":         "SUI",
    "Brazil":              "BRA",
    "Morocco":             "MAR",
    "Haiti":               "HTI",
    "Scotland":            "SCO",
    "Australia":           "AUS",
    "Türkiye":             "TUR",
    "Turkey":              "TUR",
    "Netherlands":         "NED",
    "Japan":               "JPN",
    "Côte d'Ivoire":       "CIV",
    "Cote d'Ivoire":       "CIV",
    "Ivory Coast":         "CIV",
    "Ecuador":             "ECU",
    "Sweden":              "SWE",
    "Tunisia":             "TUN",
    "Spain":               "ESP",
    "Cabo Verde":          "CPV",
    "Cape Verde":          "CPV",
    "Belgium":             "BEL",
    "Egypt":               "EGY",
    "Saudi Arabia":        "SAU",
    "Uruguay":             "URU",
    "Argentina":           "ARG",
    "France":              "FRA",
    "England":             "ENG",
    "Portugal":            "POR",
    "Algeria":             "DZA",
    "DR Congo":            "COD",
    "Democratic Republic of Congo": "COD",
    "Croatia":             "CRO",
    "Norway":              "NOR",
    "New Zealand":         "NZL",
    "Iran":                "IRN",
    "IR Iran":             "IRN",
    "Iraq":                "IRQ",
    "Jordan":              "JOR",
    "Ghana":               "GHA",
    "Senegal":             "SEN",
    "Colombia":            "COL",
    "Panama":              "PAN",
    "Uzbekistan":          "UZB",
    "Austria":             "AUT",
    "Indonesia":           "IDN",
}


def fetch_gamma(url: str) -> list:
    headers = {
        "User-Agent": "BetEdge/1.0 (+https://github.com/blummabet)",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} fetching {url}")
        raise
    except urllib.error.URLError as e:
        print(f"  URL error: {e.reason}")
        raise


def fetch_clob_depth(token_id: str) -> dict | None:
    """
    Fetches top-of-book bid/ask from Polymarket CLOB API.
    Returns dict with bid, ask, spreadPP, topLiqUSD — or None on failure.
    Only called for high-priority fixtures (bestEdge >= 3pp) to limit API load.
    """
    if not token_id:
        return None
    url = CLOB_URL.format(token_id=token_id)
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "BetEdge/1.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        bids = data.get("bids") or []
        asks = data.get("asks") or []
        if not bids or not asks:
            return None
        # Poly returns bids sorted desc, asks sorted asc — first item is best
        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
        bid_liq  = float(bids[0].get("size", 0))
        ask_liq  = float(asks[0].get("size", 0))
        return {
            "bid":       round(best_bid, 4),
            "ask":       round(best_ask, 4),
            "spreadPP":  round((best_ask - best_bid) * 100, 1),
            "topLiqUSD": round(bid_liq + ask_liq, 0),
        }
    except Exception as e:
        print(f"  ⚠️  CLOB depth fehlgeschlagen ({str(token_id)[:12]}…): {e}")
        return None


# Wie weit darf ein Poly-Datum den Spielplan-Eintrag verschieben? Siehe Kommentar am
# Kickoff-Patch weiter unten.
KO_PATCH_MAX_DRIFT_D = 14


def _tage_auseinander(a, b):
    """|a - b| in Tagen, None wenn eines der Daten nicht lesbar ist (dann nicht urteilen)."""
    from datetime import date as _date
    try:
        return abs((_date.fromisoformat(a) - _date.fromisoformat(b)).days)
    except Exception:
        return None


# ── Gegenprobe gegen den Spielplan (28.08.2026) ──────────────────────────────
# Der PSG-Fall zeigt die Luecke im Resolver: bei GENAU EINEM Fuzzy-Treffer greift die
# Mehrdeutigkeits-Bremse nicht, auch wenn dieser eine Treffer das falsche Team ist. Ein
# Namensvergleich kann das prinzipiell nicht ausschliessen — der Spielplan aber schon:
# eine Paarung, die es an dem Datum gar nicht gibt, ist falsch aufgeloest. Fail-closed,
# aber nur dort, wo wir ueberhaupt urteilen koennen (siehe `daten_bekannt`).
_SPIELPLAN_CACHE = {}


def spielplan_paare(pfad=None) -> tuple:
    """({(home,away,datum)}, {datum}) aus dem Fixture-Datensatz.

    Zweites Element sind die Daten, fuer die wir ueberhaupt Fixtures haben. Nur an diesen
    Tagen darf eine unbekannte Paarung als Fehler gelten — sonst wuerde ein luckenhafter
    Spielplan gute Poly-Daten wegwerfen.
    """
    pfad = pfad or WM_FILE
    if pfad in _SPIELPLAN_CACHE:
        return _SPIELPLAN_CACHE[pfad]
    paare, tage = set(), set()
    try:
        with open(pfad, encoding="utf-8") as f:
            wm = json.load(f)
        fixtures = []
        for g in (wm.get("groups") or {}).values():
            fixtures.extend((g or {}).get("fixtures") or [])
        fixtures.extend(wm.get("koFixtures") or [])
        for fx in fixtures:
            d = str(fx.get("date") or (fx.get("kickoff") or ""))[:10]
            if len(d) != 10:
                continue
            h, a = str(fx.get("home")), str(fx.get("away"))
            paare.add((h, a, d))
            tage.add(d)
    except Exception as e:
        print(f"  ⚠️  Spielplan fuer die Gegenprobe nicht lesbar: {e}")
        return (set(), set())        # nichts bekannt → nie urteilen
    _SPIELPLAN_CACHE[pfad] = (paare, tage)
    return (paare, tage)


def paarung_im_spielplan(home_id, away_id, datum, paare=None, tage=None):
    """True = passt, False = existiert nicht, None = koennen wir nicht beurteilen.

    Polymarket spiegelt Paarungen, deshalb zaehlt auch die umgekehrte Reihenfolge. Und ein
    Datum um einen Tag daneben (Zeitzone/Anpfiff nach Mitternacht) gilt als Treffer.
    """
    if paare is None or tage is None:
        paare, tage = spielplan_paare()
    if not paare or not datum:
        return None
    from datetime import date as _date
    try:
        d0 = _date.fromisoformat(datum)
    except Exception:
        return None
    # Wenn wir fuer den Tag selbst einen Spielplan haben, zaehlt NUR das exakte Datum. Die
    # Nachbartage sind der Notnagel fuer Zeitzonen-Faelle an Tagen, an denen wir sonst gar
    # nichts wissen — als Toleranz im Normalfall haben sie den PSG-Fehler durchgewunken.
    if datum in tage:
        nachbarn = [datum]
    else:
        nachbarn = [(d0 - timedelta(days=1)).isoformat(),
                    (d0 + timedelta(days=1)).isoformat()]
        if not any(t in tage for t in nachbarn):
            return None              # fuer diese Tage haben wir gar keinen Spielplan
    h, a = str(home_id), str(away_id)
    for t in nachbarn:
        if (h, a, t) in paare or (a, h, t) in paare:
            return True
    return False


def _build_name_map_from_data() -> dict:
    """Non-WM (Liga/MLS): Name→ID-Map aus den Team-Namen des Datensatzes (Polymarket nennt Klubs,
    nicht Länder → die hartkodierte WM-Ländermap greift nicht). 29.06.2026."""
    m = {}
    try:
        with open(WM_FILE, encoding="utf-8") as f:
            wm = json.load(f)
        for g in (wm.get("groups") or {}).values():
            for t in (g.get("teams") or []):
                nm, tid = t.get("name"), t.get("id")
                if nm and tid:
                    m[str(nm)] = str(tid)
    except Exception:
        pass
    return m

# Aktive Name→ID-Map: WM = hartkodierte Ländermap, sonst dynamisch aus dem Datensatz.
# 04.08.2026 (Lucas, La-Liga-Live): Polymarket nennt einige Klubs laenger als API-Football, sodass
# _names_match mehrdeutig wird oder leer laeuft. Exakte Poly->ID-Aliase (im Browser gegen gamma
# /events?series_id=10193 verifiziert), greifen VOR dem Fuzzy-Match. Bei neuen Ligen ggf. erweitern.
_POLY_NAME_ALIASES = {
    "RCD Espanyol de Barcelona": "540",   # Espanyol (nicht Barcelona 529 - "Barcelona" im Namen kollidiert)
    "Real Racing Club":          "4665",  # Racing Santander (kein Token-Overlap mit "Racing Santander")
    # 28.08.2026 (Lucas' Runner-Log): fünf Namen liefen JEDEN Lauf ins Leere. Zwei davon
    # mehrdeutig — und zwar als Nebenwirkung der Espanyol-Zeile eine Ebene höher: sobald
    # "RCD Espanyol de Barcelona" in der Map steht, matcht "FC Barcelona" per Token-Überlapp
    # auf 529 UND 540, der Resolver gibt (korrekt) None zurück und das Spiel fliegt raus.
    # Ergebnis: Barcelona und Inter waren seit Saisonstart NIE handelbar; in einem einzigen
    # Lauf gingen so 9 Fixtures verloren. Exakte Aliase greifen VOR dem Fuzzy-Match.
    "FC Barcelona":              "529",   # vs 540 Espanyol ("… de Barcelona")
    "FC Internazionale Milano":  "505",   # vs 489 AC Milan ("Milan" im Namen)
    "Stade Rennais FC 1901":      "94",   # Rennes — Jahreszahl + Rechtsform, kein Token-Treffer
    "ES Troyes AC":              "110",   # Estac Troyes
    "RC Deportivo A Coruña":     "544",   # Deportivo La Coruna (A Coruña vs La Coruna)
    # 28.08.2026, aus dem ersten Lauf mit dem Abdeckungs-Alarm — und der schlimmste Fall bisher:
    # „Paris Saint-Germain FC" loeste auf 114 = PARIS FC auf. Nicht mehrdeutig, sondern EINDEUTIG
    # FALSCH: gegen „Paris Saint Germain" (85) scheitert der Token-Match am Bindestrich, gegen
    # „Paris FC" trifft er — genau ein Treffer, also greift die Mehrdeutigkeits-Bremse nicht und
    # der Resolver liefert selbstbewusst das falsche Team. Folge: der Lille-PSG-Markt mit
    # 367.924 $ Volumen lag unter Paris FC, PSGs echte Paarung hatte gar keine Poly-Daten, und
    # eine Edge aus 114 verglich Paris-FC-Quoten mit PSG-Preisen. Beide Namen jetzt exakt.
    "Paris Saint-Germain FC":     "85",   # NICHT 114 — das ist Paris FC
    "Paris FC":                  "114",
}
_ACTIVE_NAME_MAP = (_build_name_map_from_data() if D.is_liga() else dict(POLY_NAME_TO_ID))
if D.is_liga():
    _ACTIVE_NAME_MAP.update(_POLY_NAME_ALIASES)


def resolve_team_id(name: str) -> str | None:
    """Map Polymarket team name → our team ID.

    12.07.2026 (Lucas: „MLS ist auf Polymarket da"): Der alte Resolver war exakt + naiver
    Teilstring — für MLS reicht das NICHT. Polymarket nennt die Klubs anders als API-Football
    („LA Galaxy" / „Sporting KC" / „CF Montréal" / „D.C. United" / „NYCFC"), die Zuordnung wäre
    still ins Leere gelaufen (keine Poly-Edges, keine smart_money/polymarket_sharp-Signale).
    Schlimmer: „Los Angeles FC" → norm „los angeles" hätte per Teilstring auf „Los Angeles
    Galaxy" gematcht → Wette auf das FALSCHE LA-Team.

    Jetzt: exakt → getrimmt → robuster Matcher aus fetch_liga_odds (_names_match: Akzente,
    Interpunktion, Rechtsform-Stoppwörter, Alias-Map inkl. kollisionsfreier LA-Aliase,
    Token-Überlapp). Fällt NUR auf einen eindeutigen Treffer zurück: matchen mehrere Teams,
    geben wir lieber None zurück (kein Trade) als das falsche Team.
    """
    nm_map = _ACTIVE_NAME_MAP
    tid = nm_map.get(name) or nm_map.get((name or "").strip())
    if tid:
        return tid
    try:
        from fetch_liga_odds import _names_match
    except Exception:
        return None
    hits = {team_id for our_name, team_id in nm_map.items() if _names_match(name, our_name)}
    if len(hits) == 1:
        return hits.pop()
    if len(hits) > 1:
        print(f"  ⚠️  Poly-Name '{name}' passt auf MEHRERE Teams {sorted(hits)} — "
              f"kein eindeutiger Treffer, übersprungen (lieber kein Trade als der falsche).")
    return None


def parse_event(event: dict) -> dict | None:
    """
    Parse one Polymarket event into our format.
    Returns dict or None if parsing fails.
    """
    slug  = event.get("slug", "")
    title = event.get("title", "")
    date  = event.get("eventDate", "")
    # Echte Anpfiff-Zeit (UTC ISO) von Polymarket-Gamma. eventDate ist nur das
    # Datum (US-Konvention) — startTime/gameStartTime hat die präzise Kickoff-Zeit,
    # z.B. KOR-CZE "2026-06-12T02:00:00Z" (= 20:00 Guadalajara). Ersetzt die
    # 00:00-Platzhalter im Seed-Spielplan (11.06.2026).
    kickoff = event.get("startTime") or event.get("gameStartTime") or None
    vol   = event.get("volume", 0)

    # Identify home and away teams from teams array
    teams_arr = event.get("teams", [])
    if len(teams_arr) < 2:
        print(f"  SKIP {slug}: only {len(teams_arr)} team(s)")
        return None

    home_name = teams_arr[0].get("name", "")
    away_name = teams_arr[1].get("name", "")
    home_id   = resolve_team_id(home_name)
    away_id   = resolve_team_id(away_name)

    if not home_id or not away_id:
        print(f"  SKIP {slug}: unresolved team(s) '{home_name}' → {home_id}, '{away_name}' → {away_id}")
        return None

    key = f"{home_id}-{away_id}"

    # Parse markets
    hw = dr = aw = None
    hw_tokens = dr_tokens = aw_tokens = []
    hw_cond = dr_cond = aw_cond = None          # conditionId je Outcome (für data-api /holders + /trades)
    neg_risk_market_id = event.get("negRiskMarketID")

    for m in event.get("markets", []):
        gt     = m.get("groupItemTitle", "")
        prices = json.loads(m.get("outcomePrices", "[]") or "[]")
        tokens = json.loads(m.get("clobTokenIds", "[]") or "[]")
        cond   = m.get("conditionId")
        yes_price = float(prices[0]) if prices else None

        if yes_price is None:
            continue

        gt_lower = gt.lower()
        if "draw" in gt_lower:
            dr = yes_price
            dr_tokens = tokens; dr_cond = cond
        elif resolve_team_id(gt) == home_id:
            hw = yes_price
            hw_tokens = tokens; hw_cond = cond
        elif resolve_team_id(gt) == away_id:
            aw = yes_price
            aw_tokens = tokens; aw_cond = cond
        else:
            # Fallback: try by groupItemThreshold (0=home,1=draw,2=away) if present
            threshold = str(m.get("groupItemThreshold", ""))
            if threshold == "0":
                hw = yes_price; hw_tokens = tokens; hw_cond = cond
            elif threshold == "1":
                dr = yes_price; dr_tokens = tokens; dr_cond = cond
            elif threshold == "2":
                aw = yes_price; aw_tokens = tokens; aw_cond = cond

    if hw is None or aw is None:
        print(f"  WARN {slug}: missing hw={hw} aw={aw} dr={dr}")
        return None

    return {
        "homeId":    home_id,
        "awayId":    away_id,
        "homeName":  home_name,
        "awayName":  away_name,
        "hw":        round(hw, 4),
        "dr":        round(dr, 4) if dr is not None else None,
        "aw":        round(aw, 4),
        "slug":      slug,
        "title":     title,
        "date":      date,
        "kickoff":   kickoff,
        "vol":       round(vol, 2),
        "negRiskMarketId": neg_risk_market_id,
        "hwTokens":  hw_tokens,
        "drTokens":  dr_tokens,
        "awTokens":  aw_tokens,
        "hwCondition": hw_cond,
        "drCondition": dr_cond,
        "awCondition": aw_cond,
    }


def fetch_more_markets(slug: str) -> dict:
    """
    Fetch the {slug}-more-markets child event and return extracted prices.
    Returns dict with keys: totals (by line), btts, spreads. Empty dict on failure.
    """
    mm_slug = f"{slug}-more-markets"
    url = GAMMA_SLUG_URL.format(slug=mm_slug)
    try:
        data = fetch_gamma(url)
    except Exception:
        return {}

    if not data or not isinstance(data, list):
        return {}

    event = data[0]
    result = {"totals": {}, "btts": None, "btts_no": None, "btts_tokens": [], "spreads": {}}

    for m in event.get("markets", []):
        smt    = m.get("sportsMarketType", "")
        line   = m.get("line")
        prices = json.loads(m.get("outcomePrices", "[]") or "[]")
        if len(prices) < 2:
            continue
        over_price = float(prices[0])
        under_price = float(prices[1])

        if smt == "totals" and line is not None:
            result["totals"][float(line)] = {
                "over":  round(over_price, 4),
                "under": round(under_price, 4),
            }
        elif smt == "both_teams_to_score":
            result["btts"]    = round(over_price, 4)   # Yes price
            result["btts_no"] = round(under_price, 4)  # No price
            # clobTokenIds: token[0] = Yes-Outcome, token[1] = No-Outcome
            # (gleiche Reihenfolge wie outcomePrices) → für Auto-Trade-Platzierung.
            try:
                result["btts_tokens"] = json.loads(m.get("clobTokenIds", "[]") or "[]")
            except Exception:
                result["btts_tokens"] = []
        elif smt == "spreads" and line is not None:
            # Handicap (15.06.2026): groupItemTitle = "Scotland (-1.5)" → Team + Linie.
            # Markt ist binär: Yes = Team deckt das Handicap (prices[0]). clobTokenIds
            # für die Trade-Platzierung. Pro Team eine Linien-Map.
            git  = m.get("groupItemTitle", "") or ""
            team = git.split("(")[0].strip()
            if not team:
                continue
            try:
                tokens = json.loads(m.get("clobTokenIds", "[]") or "[]")
            except Exception:
                tokens = []
            result["spreads"].setdefault(team, {})[float(line)] = {
                "yes":    round(over_price, 4),   # Team deckt das Handicap
                "tokens": tokens,
            }

    return result


def _devig_2way(o_a, o_b):
    """Faire P(Seite A) aus 2-Weg-Quoten (Vig entfernt)."""
    if not o_a or not o_b or o_a <= 1 or o_b <= 1:
        return None
    ia, ib = 1.0 / o_a, 1.0 / o_b
    return ia / (ia + ib)


def _ladder_get(ah_ladder, target_line):
    """Pinnacle-AH-Leiter [home_odds, away_odds] für eine Heim-Linie (Float-Match)."""
    for k, v in (ah_ladder or {}).items():
        try:
            if abs(float(k) - target_line) < 1e-6 and v and v[0] and v[1]:
                return v
        except (TypeError, ValueError):
            continue
    return None


def compute_ah_edges(poly_ah_home: dict, poly_ah_away: dict, ah_ladder: dict) -> list:
    """Handicap-Edges (15.06.2026): pro Poly-Linie fair aus Pinnacle-AH-Leiter de-viggen.
    Pinnacle-Leiter ist nach HEIM-Linie geschlüsselt: Poly „Heim (L)" → Leiter L;
    Poly „Auswärts (L)" = Heim +|L| → Leiter −L. Nur EXAKTE Linien-Treffer (kein
    Schätzen über mismatched lines). edge = fair − poly_yes (positiv = Poly unterbewertet)."""
    out = []
    for side, poly_lines in (("home", poly_ah_home or {}), ("away", poly_ah_away or {})):
        for line, info in poly_lines.items():
            poly_yes = (info or {}).get("yes")
            if not poly_yes:
                continue
            pinn_key = line if side == "home" else -line
            lad = _ladder_get(ah_ladder, pinn_key)
            if not lad:
                continue
            home_odds, away_odds = lad[0], lad[1]
            fair = _devig_2way(home_odds, away_odds) if side == "home" \
                else _devig_2way(away_odds, home_odds)
            if fair is None:
                continue
            out.append({
                "side":   side,
                "line":   line,
                "poly":   poly_yes,
                "fair":   round(fair, 4),
                "edge":   round((fair - poly_yes) * 100, 1),
                "tokens": (info or {}).get("tokens", []),
            })
    return out


# Templated/Platzhalter-BTTS-Linien (23.06.2026, Lucas): Pinnacle (bzw. der Feed) liefert für viele
# WM-Spiele eine GENERISCHE Standard-BTTS-Linie (z.B. 1.91/1.80 auf 5 Spielen) statt eines echten
# Spiel-Sharp-Preises. Die de-vig davon (fair 0.4852/0.5148) ist mathematisch sauber, aber inhaltlich
# wertlos → Phantom-Edge → Auto-Trader setzte echtes Geld (CPV-SAU/PRY-AUS/JPN-SWE, real negativer Edge).
BTTS_TEMPLATE_MIN = 3   # dieselbe (bttsY,bttsN) über >= N Spiele = Platzhalter → nicht handelbar


def compute_btts_edges(pinn_bttsY, pinn_bttsN, poly_btts, poly_btts_no, templated=False):
    """De-viggte Pinnacle-BTTS-Fair + Edge je Seite. Liefert bei fehlender Linie ODER templated
    (generische Standardlinie, kein echter Sharp-Preis) überall None → der Auto-Trader handelt sie
    NICHT (edge=None → skip). Echte Linie: fair_Ja + fair_Nein = 1.0."""
    if templated or not (isinstance(pinn_bttsY, (int, float)) and isinstance(pinn_bttsN, (int, float))
                         and pinn_bttsY > 1 and pinn_bttsN > 1):
        return None, None, None, None
    margin = 1 / pinn_bttsY + 1 / pinn_bttsN
    fair    = round((1 / pinn_bttsY) / margin, 4)
    fair_no = round((1 / pinn_bttsN) / margin, 4)
    edge    = round((fair - poly_btts) * 100, 1) if poly_btts else None
    edge_no = round((fair_no - poly_btts_no) * 100, 1) if poly_btts_no else None
    return fair, fair_no, edge, edge_no


def main():
    print("=== fetch_wm_poly_prices.py ===")

    print(f"  Fetching {GAMMA_URL} (+ Folgeseiten, je Serie einzeln)")
    try:
        events = fetch_gamma_events()
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    print(f"  {len(events)} events received from Gamma API")

    # ── Rescue anpfiff-naher Spiele, die im Batch fehlen (28.08.2026) ────────
    slug_memo = lade_slug_memo()
    _fehlend = rescue_kandidaten(slug_memo, {e.get("slug") for e in events})
    if _fehlend:
        print(f"  🛟 Rescue: {len(_fehlend)} anpfiff-nahe(s) Spiel(e) fehlt(en) im Batch — "
              f"hole einzeln per Slug: {', '.join(_fehlend[:6])}"
              f"{'…' if len(_fehlend) > 6 else ''}")
        for _slug in _fehlend:
            _ev = hole_event_per_slug(_slug)
            if _ev:
                events.append(_ev)
                print(f"    ✓ nachgeholt: {_slug}")
            else:
                print(f"    ✗ nicht (mehr) offen: {_slug}")
    # Diagnose (01.07.2026): Datumsspanne der empfangenen Events — zeigt sofort, ob KO-Spiele (nach dem
    # letzten Gruppenspieltag) durchkommen. Wenn hier nur ≤ Gruppenphase steht, greift der Batch-Filter
    # nicht wie gewollt.
    _dates = sorted(e.get("eventDate", "") for e in events if e.get("eventDate"))
    if _dates:
        print(f"  📅 Event-Datumsspanne: {_dates[0]} … {_dates[-1]}  ({len(_dates)} datiert)")

    prices: dict[str, dict] = {}
    ok = 0
    skip = 0

    # ── Filter: only process pure moneyline events (negRisk=true, no suffix in slug) ──
    # The Gamma batch API can return exact-score, halftime-result, more-markets
    # child events mixed in. We only want the root 1X2 moneyline events.
    SLUG_SUFFIXES_TO_SKIP = (
        "-exact-score", "-halftime-result", "-more-markets",
        "-exact-goals", "-both-teams-to-score",
    )

    for ev in events:
        slug_raw = ev.get("slug", "")
        # Kind-/Spezialmarkt (Suffix nach dem Datum) → nie als Moneyline verarbeiten (s. _DERIVED_SLUG_RE)
        if _DERIVED_SLUG_RE.search(slug_raw):
            print(f"  SKIP Kind-/Spezialmarkt (Suffix nach Datum): {slug_raw}")
            skip += 1
            continue
        if any(slug_raw.endswith(sfx) for sfx in SLUG_SUFFIXES_TO_SKIP):
            print(f"  SKIP non-moneyline event: {slug_raw}")
            skip += 1
            continue
        # Also skip events without negRisk (= they're child/more-markets events)
        if ev.get("negRisk") is False:
            print(f"  SKIP negRisk=False event: {slug_raw}")
            skip += 1
            continue

        result = parse_event(ev)
        if result:
            # Gegenprobe: gibt es diese Paarung an dem Tag ueberhaupt? Ein Namensfehler faellt
            # hier auf, den kein Namensvergleich finden kann (PSG → Paris FC, 28.08.2026).
            _ok = paarung_im_spielplan(result["homeId"], result["awayId"],
                                       str(result.get("date") or "")[:10])
            if _ok is False:
                print(f"  🛑 SKIP {result['slug']}: {result['homeName']} vs {result['awayName']} "
                      f"→ [{result['homeId']}-{result['awayId']}] steht am "
                      f"{str(result.get('date'))[:10]} NICHT im Spielplan — Namensaufloesung "
                      f"vermutlich falsch (lieber keine Daten als die des falschen Teams).")
                skip += 1
                continue
            key  = f"{result['homeId']}-{result['awayId']}"
            slug = result["slug"]

            # Fetch more-markets (O/U, BTTS, Spreads) — separate child event
            mm = fetch_more_markets(slug)
            totals = mm.get("totals", {})

            # Standard soccer totals — O/U 2.5 is the reference market
            result["poly_o25"]    = totals.get(2.5, {}).get("over")
            result["poly_u25"]    = totals.get(2.5, {}).get("under")
            result["poly_o15"]    = totals.get(1.5, {}).get("over")
            result["poly_u15"]    = totals.get(1.5, {}).get("under")
            result["poly_o35"]    = totals.get(3.5, {}).get("over")
            result["poly_u35"]    = totals.get(3.5, {}).get("under")
            result["poly_btts"]   = mm.get("btts")
            result["poly_btts_no"] = mm.get("btts_no")
            result["poly_btts_tokens"] = mm.get("btts_tokens") or []
            # Handicap-Linien (15.06.2026): mm["spreads"] keyed by Poly-Teamname.
            # FIX 15.06.2026 (Mirror-Bug): NICHT nach Poly-Heim/Auswärts speichern —
            # Poly spiegelt Spiele (PAN-ENG vs unser ENG-PAN), dann landeten Panamas
            # Spreads unter „home" während fair für England gerechnet wurde → Phantom-
            # Edge 50pp. Stattdessen nach UNSERER Team-ID schlüsseln → orientierungs-
            # immun. compute_ah_edges (im Patch-Loop) löst home/away per Key auf.
            _spreads = mm.get("spreads") or {}
            result["poly_ah_by_team"] = {
                tid: lines for team, lines in _spreads.items()
                if (tid := resolve_team_id(team))
            }
            result["moreMktSlug"] = f"{slug}-more-markets" if mm else None

            prices[key] = result
            ou_str = f" | O2.5={result['poly_o25']}" if result["poly_o25"] else ""
            print(f"  ✓ {result['homeName']} vs {result['awayName']}  [{key}]"
                  f"  hw={result['hw']:.3f} dr={result['dr']} aw={result['aw']:.3f}"
                  f"  vol=${result['vol']:,.0f}{ou_str}")
            ok += 1
        else:
            skip += 1

    # Slug-Gedächtnis fortschreiben — Basis für den Rescue im nächsten Lauf.
    try:
        write_json_atomic(SLUG_MEMO_FILE, merke_slugs(slug_memo, prices))
    except Exception as e:
        print(f"  ⚠️  Slug-Gedächtnis schreiben fehlgeschlagen: {e}")

    # ── Patch wm2026-data.json mit aktuellen Poly-Preisen ────────────────────
    wm = None

    if ok > 0 and os.path.exists(WM_FILE):
        with open(WM_FILE, encoding="utf-8") as f:
            wm = json.load(f)

        wm_odds = wm.setdefault("odds", {})

        # Build team name lookup: id → German name
        team_names: dict[str, str] = {}
        for gdata in wm.get("groups", {}).values():
            for t in gdata.get("teams", []):
                team_names[t["id"]] = t.get("name", t["id"])

        # ── Polymarket-Spiegel normalisieren (FIX 12.06.2026) ────────────────
        # Bei ~12 Spielen (v.a. MD3) listet Polymarket Heim/Auswärts vertauscht
        # (SUI-CAN statt CAN-SUI) → poly landete unter einem Phantom-Key, das
        # echte Fixture (CAN-SUI) blieb ohne Poly-Daten/Edge/Trade. 84 odds-keys
        # statt 72. Fix: auf UNSERE Fixture-Reihenfolge drehen (hw↔aw) + re-keyen.
        real_keys = {
            f"{f.get('home')}-{f.get('away')}"
            for gdata in wm.get("groups", {}).values()
            for f in gdata.get("fixtures", [])
        }
        # KO-Paarungen sind ECHTE Fixtures (nur ohne Poly-Markt) — sonst löscht das Phantom-Pruning
        # unten ihre Pinnacle-Odds bei JEDEM Lauf → R32-Cards verlieren Quote + Pick (Bug 27.06.2026).
        real_keys |= {
            f"{k.get('home')}-{k.get('away')}"
            for k in (wm.get("koFixtures") or [])
            if k.get("bothResolved") and k.get("home") and k.get("away")
        }
        _norm, _flipped = {}, 0
        for k, p in prices.items():
            rk = f"{p.get('awayId')}-{p.get('homeId')}"
            if k not in real_keys and rk in real_keys:
                p = _flip_poly_orientation(p)
                k = rk
                _flipped += 1
            _norm[k] = p
        prices = _norm
        if _flipped:
            print(f"  ↔ {_flipped} Poly-Spiegel auf Fixture-Reihenfolge normalisiert")

        # Alt-Phantom-Keys aus früheren Läufen entfernen (Spiegel ohne echtes Fixture)
        _ph = [k for k in wm_odds if k not in real_keys]
        for pk in _ph:
            del wm_odds[pk]
        if _ph:
            print(f"  🧹 {len(_ph)} Phantom-Odds-Keys entfernt: {', '.join(_ph[:6])}{'…' if len(_ph)>6 else ''}")

        patched = 0
        for key, p in prices.items():
            existing = wm_odds.get(key, {})
            existing["poly_hw"]   = p["hw"]
            existing["poly_dr"]   = p["dr"]
            existing["poly_aw"]   = p["aw"]
            existing["poly_vol"]  = p["vol"]
            existing["poly_slug"] = p["slug"]
            wm_odds[key] = existing
            patched += 1

        # Echte Kickoff-Zeit (UTC) in die Gruppen-Fixtures schreiben — ersetzt die
        # 00:00-Platzhalter. Der Polymarket-Betting-Tab blendet Spiele mit
        # vergangenem Anpfiff aus; mit der echten Zeit zeigt er Spätspiele korrekt
        # als heute-Abend statt sie fälschlich zu verstecken/als Mitternacht.
        ko_patched = 0
        ko_verweigert = []
        for gdata in wm.get("groups", {}).values():
            for fx in gdata.get("fixtures", []):
                p = prices.get(f"{fx.get('home')}-{fx.get('away')}")
                # 28.08.2026 — DIESE Stelle hat den PSG-Fehler in den Spielplan geschrieben.
                # „Paris Saint-Germain FC" loeste auf 114 (Paris FC) auf, der Lille-PSG-Markt
                # landete unter dem Key 79-114, und der Patch unten stempelte dessen Anpfiff
                # (28.08. 18:45) auf Lille–Paris FC, ein Spiel vom 17. Spieltag. Danach standen
                # zwei Lille-Spiele am selben Tag im Spielplan — und die Gegenprobe, die genau
                # solche Fehler finden soll, bestaetigte den falschen Treffer mit den eigenen
                # kaputten Daten. Ein Namensfehler, der sich selbst plausibel macht.
                # Deshalb: Poly darf einen Anpfiff praezisieren, aber ein Spiel nicht in einen
                # anderen Monat verschieben. 14 Tage lassen die legitime Seed-Korrektur zu
                # (12.06.2026: Seed-Datum ~5 Tage zu frueh), stoppen aber den Sprung ueber
                # Spieltage hinweg.
                if p and p.get("date") and fx.get("date"):
                    _drift = _tage_auseinander(str(fx["date"])[:10], str(p["date"])[:10])
                    if _drift is not None and _drift > KO_PATCH_MAX_DRIFT_D:
                        ko_verweigert.append(
                            f"{fx.get('home')}-{fx.get('away')} ({fx['date']} → "
                            f"{str(p['date'])[:10]}, {_drift} Tage)")
                        continue
                if p and p.get("kickoff"):
                    fx["kickoff"] = p["kickoff"]
                    _t = _vienna_hhmm(p["kickoff"])
                    if _t:
                        fx["time"] = _t   # time-Feld aus kickoff normalisieren
                    # Match-Datum aus Polymarket eventDate (authoritativ). FIX 12.06.2026:
                    # 12 MD3-Spiele hatten ein Seed-Datum ~5 Tage zu früh (CAN-SUI Seed
                    # 06-19 ≠ real 06-24) → Picks am falschen Tag. eventDate = was der
                    # schedule_date-Integritäts-Check als Wahrheit nutzt.
                    pd = str(p.get("date") or "")[:10]
                    if pd:
                        fx["date"] = pd
                    ko_patched += 1
        print(f"   ⏰ {ko_patched} Fixture-Kickoff-Zeiten aus Polymarket gesetzt")
        if ko_verweigert:
            print(f"   🛑 {len(ko_verweigert)} Kickoff-Patch(es) verweigert — Poly wollte ein "
                  f"Spiel um mehr als {KO_PATCH_MAX_DRIFT_D} Tage verschieben (Namensfehler?): "
                  + "; ".join(ko_verweigert[:5]))

    if wm is not None:
        # FORMAT-FIX (12.07.2026, Lucas' 1. MLS-Poly-Lauf: „38552 deletions"): Dieser Writer war der
        # EINZIGE, der die Datendatei KOMPAKT (separators, eine Zeile) schrieb — alle anderen
        # (fetch_wm_odds, fetch_liga_odds, build_liga_data, generate_wm_picks) nutzen indent=2.
        # Folge: jeder Poly-Lauf kippte die Datei auf 1 Zeile, der nächste update-Lauf zurück →
        # 38k-Zeilen-Diff hin und her. Nicht nur Churn: bei einem Merge-Konflikt auf so einer Datei
        # kann das `git pull -X ours` im Retry-Loop echte Daten des anderen Workflows verwerfen.
        # Jetzt gleiches Format wie alle → minimale, lesbare Diffs, kaum Konfliktfläche.
        with open(WM_FILE, "w", encoding="utf-8") as f:
            json.dump(wm, f, ensure_ascii=False, indent=2)
        print(f"  Patched {patched} fixtures in {os.path.basename(str(WM_FILE))} (poly_hw/dr/aw fields)")

    # ── Build allFixtures (all 72 games, Pinnacle + Poly + Edge — for dashboard table) ──
    # allFixtures shows everything so the
    # dashboard can apply its own filters and display all markets.
    all_fixtures: list[dict] = []

    wm_odds_ref = wm.get("odds", {}) if wm is not None else {}
    team_names_ref: dict[str, str] = {}
    if wm is not None:
        for gdata in wm.get("groups", {}).values():
            for t in gdata.get("teams", []):
                team_names_ref[t["id"]] = t.get("name", t["id"])

    # ── Build picks lookup: {HOME-AWAY: {market_label: {verdict, edgePP, dataQuality}}} ──
    # Used to enrich allFixtures with pick verdicts so auto-trigger respects pick logic.
    #
    # KRITISCH: picks-Keys in wm2026-data.json sind "GROUP-MATCHDAY-HOME-AWAY"
    # (z.B. "A-1-MEX-ZAF"), aber allFixtures-Keys sind "HOME-AWAY" (z.B. "MEX-ZAF").
    # Wir bauen den Lookup mit "HOME-AWAY"-Keys damit der nachfolgende Zugriff matched.
    # Vorher: alle verdict_xx waren None → Auto-Trigger feuerte NIE einen Bet.
    picks_lookup: dict[str, dict] = {}
    if wm is not None:
        for match_key, pick_list in wm.get("picks", {}).items():
            # Extract HOME-AWAY aus "GROUP-MATCHDAY-HOME-AWAY"
            parts = match_key.split("-", 3)
            if len(parts) < 4:
                continue
            ha_key = f"{parts[2]}-{parts[3]}"
            if ha_key not in picks_lookup:
                picks_lookup[ha_key] = {}
            for pk in pick_list:
                mkt = pk.get("market", "")
                picks_lookup[ha_key][mkt] = {
                    "verdict":             pk.get("verdict"),
                    "edgePP":              pk.get("edgePP"),
                    "dataQuality":         pk.get("dataQuality", "elo_only"),
                    # ── Signal-Engine Felder (08.06.2026) ──────────────────
                    # Auto-Trigger nutzt diese: ohne diese hat Auto-Trigger
                    # die Engine komplett ignoriert (raw edge + verdict only).
                    "signalAdjustmentPP":  pk.get("signalAdjustmentPP"),
                    "signalCountPos":      pk.get("signalCountPos"),
                    "signalCountNeg":      pk.get("signalCountNeg"),
                    "effectiveEdgePP":     pk.get("effectiveEdgePP"),
                    "downgradedReason":    pk.get("downgradedReason"),
                    # Conviction-Score (09.06.2026): wird vom Auto-Trigger
                    # als zusätzliches Gate genutzt — Trade nur bei ≥3/10.
                    "convictionScore":     pk.get("convictionScore"),
                    "synthetic":           pk.get("synthetic"),
                    "trackingExcluded":    pk.get("trackingExcluded"),
                }

    # Market label → edge_key / allFixtures field name
    # Both English and German label variants are accepted — generate_wm_picks.py
    # writes German labels ("Über 2.5 Tore") while legacy data may use English.
    _MARKET_TO_FIELD = {
        "Heimsieg":                  "hw",
        "Unentschieden":             "dr",
        "Auswärtssieg":              "aw",
        "Over 2.5 Tore":             "o25",
        "Über 2.5 Tore":             "o25",   # German alias (generate_wm_picks.py)
        "Under 2.5 Tore":            "u25",
        "Unter 2.5 Tore":            "u25",   # German alias
        "Beide Teams treffen":        "btts",
        "Beide Teams treffen — Ja":   "btts",      # Yes-Seite
        "Beide Teams treffen — Nein": "btts_no",   # No-Seite
    }
    # Märkte, für die Engine-Felder (verdict/conviction/signal…) durchgereicht werden.
    _ENGINE_FIELDS = ("hw", "dr", "aw", "o25", "u25", "btts", "btts_no")

    # Templated-BTTS-Erkennung: zähle jede (bttsY,bttsN)-Linie über ALLE Spiele. Eine Linie, die
    # auf >= BTTS_TEMPLATE_MIN Spielen identisch auftaucht, ist eine generische Platzhalter-Linie
    # (kein echter Spiel-Sharp-Preis) → unten von der BTTS-Fair/Edge ausgeschlossen.
    _btts_line_counts = collections.Counter()
    for _o in (wm_odds_ref or {}).values():
        if isinstance(_o, dict):
            _y, _n = _o.get("bttsY"), _o.get("bttsN")
            if isinstance(_y, (int, float)) and isinstance(_n, (int, float)):
                _btts_line_counts[(_y, _n)] += 1

    for key, p in prices.items():
        home_id, away_id = key.split("-", 1)
        pinn = wm_odds_ref.get(key, {})

        pinn_hw  = pinn.get("hw")
        pinn_dr  = pinn.get("dr")
        pinn_aw  = pinn.get("aw")
        pinn_o25 = pinn.get("o25")   # available once TheOddsAPI lists WM totals
        pinn_u25 = pinn.get("u25")

        fair_hw = fair_dr = fair_aw = None
        edge_hw = edge_dr = edge_aw = None
        best_edge      = None
        best_edge_key  = None

        # 19.07.2026 — PLATZHALTER-QUOTEN (Lucas: Telegram-Edge-Alerts mit „Pinn 1.01 Remis").
        # Remis 1.01 / Auswärts 1.04 sind keine echten Pinnacle-Quoten → daraus wurde eine
        # Fake-Edge +13-17pp gerechnet und gesendet. `devig_1x2` ist die EINE gegatete De-Vig:
        # implausibel → None → gar keine 1X2-Edge (dieselbe Bug-Klasse wie 13.07.).
        _fair = devig_1x2(pinn_hw, pinn_dr, pinn_aw)
        if _fair:
            fair_hw, fair_dr, fair_aw = _fair["home"], _fair["draw"], _fair["away"]
            edge_hw = round((fair_hw - p["hw"]) * 100, 1)
            edge_dr = round((fair_dr - (p["dr"] or 0)) * 100, 1) if p["dr"] else None
            edge_aw = round((fair_aw - p["aw"]) * 100, 1)
            # Best positive edge across outcomes
            edges = {
                "hw": edge_hw,
                "dr": edge_dr,
                "aw": edge_aw,
            }
            pos_edges = {k: v for k, v in edges.items() if v is not None and v > 0}
            if pos_edges:
                best_edge_key = max(pos_edges, key=pos_edges.get)
                best_edge     = pos_edges[best_edge_key]

        # ── O/U Pinnacle edge vs Polymarket (when pinn_o25 available) ──────────
        poly_o25   = p.get("poly_o25")
        poly_u25   = p.get("poly_u25")
        edge_o25   = None
        edge_u25   = None
        fair_o25   = None
        fair_u25   = None

        if pinn_o25 and pinn_u25 and pinn_o25 > 1 and poly_o25:
            ou_margin  = 1/pinn_o25 + 1/pinn_u25
            fair_o25   = round((1/pinn_o25) / ou_margin, 4)
            fair_u25   = round((1/pinn_u25) / ou_margin, 4)
            edge_o25   = round((fair_o25 - poly_o25) * 100, 1)
            edge_u25   = round((fair_u25 - (poly_u25 or 0)) * 100, 1) if poly_u25 else None

        # ── BTTS Pinnacle edge (15.06.2026): de-vig Pinnacle bttsY/bttsN ───────
        # Binärer Markt: Poly poly_btts (Ja) / poly_btts_no (Nein). Fair aus der
        # de-viggten Pinnacle-Baseline (wie 1X2/O-U, NICHT Poisson). Beide Seiten
        # getrennt handelbar — Pick kann „Ja" ODER „Nein" sein.
        poly_btts    = p.get("poly_btts")
        poly_btts_no = p.get("poly_btts_no")
        pinn_bttsY   = pinn.get("bttsY")
        pinn_bttsN   = pinn.get("bttsN")
        btts_templated = (
            isinstance(pinn_bttsY, (int, float)) and isinstance(pinn_bttsN, (int, float))
            and _btts_line_counts[(pinn_bttsY, pinn_bttsN)] >= BTTS_TEMPLATE_MIN
        )
        fair_btts, fair_btts_no, edge_btts, edge_btts_no = compute_btts_edges(
            pinn_bttsY, pinn_bttsN, poly_btts, poly_btts_no, templated=btts_templated)
        if btts_templated:
            print(f"  ⏭️  BTTS templated ({pinn_bttsY}/{pinn_bttsN} auf "
                  f"{_btts_line_counts[(pinn_bttsY, pinn_bttsN)]} Spielen) → {key} nicht handelbar")

        # ── Handicap-Edges (15.06.2026): Poly-Spreads vs Pinnacle-AH-Leiter ──────
        # home_id/away_id aus dem (normalisierten) Key → poly_ah_by_team auflösen.
        # Orientierungs-immun: egal wie Poly das Spiel spiegelt, die Spreads landen
        # bei der richtigen Seite (per Team-ID, nicht Poly-Heim/Auswärts).
        _ah_by_team = p.get("poly_ah_by_team") or {}
        ah_edges = compute_ah_edges(_ah_by_team.get(home_id, {}),
                                    _ah_by_team.get(away_id, {}),
                                    pinn.get("ahLadder"))

        all_fixtures.append({
            "key":          key,
            "homeId":       home_id,
            "awayId":       away_id,
            "home":         team_names_ref.get(home_id, p["homeName"]),
            "away":         team_names_ref.get(away_id, p["awayName"]),
            "homeName":     p["homeName"],
            "awayName":     p["awayName"],
            "date":         p["date"],
            "kickoff":      p.get("kickoff"),
            "slug":         p["slug"],
            "moreMktSlug":  p.get("moreMktSlug"),
            "vol":          round(p["vol"], 0),
            # Polymarket 1X2 (probability 0-1, convert to decimal odds with 1/p)
            "poly_hw":      p["hw"],
            "poly_dr":      p.get("dr"),
            "poly_aw":      p["aw"],
            # Polymarket O/U + BTTS (from -more-markets child event)
            "poly_o25":     poly_o25,
            "poly_u25":     poly_u25,
            "poly_o15":     p.get("poly_o15"),
            "poly_u15":     p.get("poly_u15"),
            "poly_o35":     p.get("poly_o35"),
            "poly_u35":     p.get("poly_u35"),
            "poly_btts":    p.get("poly_btts"),
            "poly_btts_no": p.get("poly_btts_no"),
            "poly_btts_tokens": p.get("poly_btts_tokens", []),
            # Pinnacle 1X2 (decimal odds, e.g. 1.85)
            "pinn_hw":      pinn_hw,
            "pinn_dr":      pinn_dr,
            "pinn_aw":      pinn_aw,
            # Pinnacle O/U reference (when TheOddsAPI provides WM totals)
            "pinn_o25":     pinn_o25,
            "pinn_u25":     pinn_u25,
            # Pinnacle devigged fair probabilities (1X2)
            "fair_hw":      fair_hw,
            "fair_dr":      fair_dr,
            "fair_aw":      fair_aw,
            # Pinnacle devigged fair probabilities (O/U)
            "fair_o25":     fair_o25,
            "fair_u25":     fair_u25,
            # Pinnacle devigged fair probabilities (BTTS)
            "fair_btts":    fair_btts,
            "fair_btts_no": fair_btts_no,
            "btts_templated": btts_templated,   # generische Platzhalter-Linie → nicht handelbar
            # Edge per outcome in percentage points (positive = Poly underpriced)
            "edge_hw":      edge_hw,
            "edge_dr":      edge_dr,
            "edge_aw":      edge_aw,
            "edge_o25":     edge_o25,
            "edge_u25":     edge_u25,
            "edge_btts":    edge_btts,
            "edge_btts_no": edge_btts_no,
            # Handicap-Edges (Liste {side,line,poly,fair,edge,tokens}) — Poly-Spreads
            "ah_edges":     ah_edges,
            # Best positive edge of this fixture
            "bestEdge":     best_edge,
            "bestEdgeKey":  best_edge_key,
            "hasPinnacle":  bool(pinn_hw),
            "hasMoreMarkets": bool(p.get("poly_o25")),
            # ── CLOB token IDs (for market depth fetching) ───────────────────────
            # First token in each pair is the YES token (used for bid/ask lookup)
            "hwTokens":     p.get("hwTokens", []),
            "drTokens":     p.get("drTokens", []),
            "awTokens":     p.get("awTokens", []),
            # conditionId je Outcome (data-api /holders + /trades → smart_money)
            "hwCondition":  p.get("hwCondition"),
            "drCondition":  p.get("drCondition"),
            "awCondition":  p.get("awCondition"),
            # ── Pick verdicts from generate_wm_picks.py ─────────────────────────
            # verdict_hw/dr/aw/o25/u25: "BET" | "ABWÄGEN" | "SKIP" | null
            # auto_wm_poly_trigger.py filters to BET/ABWÄGEN only
            **{
                f"verdict_{field}": picks_lookup.get(key, {}).get(mkt_label, {}).get("verdict")
                for mkt_label, field in _MARKET_TO_FIELD.items()
                if field in _ENGINE_FIELDS
            },
            # ── Engine-Felder pro Markt (08.06.2026) ──────────────────────────
            # Erlaubt Auto-Trigger über Signal-Adjustment, Min-Signal-Threshold
            # und effectiveEdge zu filtern statt blind über raw edgePP.
            # Trade-Variante OHNE freshness_leg (Lucas-Audit 18.06.2026, zwei Flächen):
            # die Card-Frische darf das Trading nicht treiben. signalAdjustmentPP_trade ist
            # die Signal-Summe minus dem freshness_leg-Beitrag. Fallback auf die volle Summe,
            # falls das Feld (Altpick / Nicht-Steam) fehlt.
            **{
                f"signalAdj_{field}": (
                    picks_lookup.get(key, {}).get(mkt_label, {}).get("signalAdjustmentPP_trade")
                    if picks_lookup.get(key, {}).get(mkt_label, {}).get("signalAdjustmentPP_trade") is not None
                    else picks_lookup.get(key, {}).get(mkt_label, {}).get("signalAdjustmentPP"))
                for mkt_label, field in _MARKET_TO_FIELD.items()
                if field in _ENGINE_FIELDS
            },
            **{
                f"signalPos_{field}": (
                    picks_lookup.get(key, {}).get(mkt_label, {}).get("signalCountPos_trade")
                    if picks_lookup.get(key, {}).get(mkt_label, {}).get("signalCountPos_trade") is not None
                    else picks_lookup.get(key, {}).get(mkt_label, {}).get("signalCountPos"))
                for mkt_label, field in _MARKET_TO_FIELD.items()
                if field in _ENGINE_FIELDS
            },
            **{
                f"effectiveEdge_{field}": (
                    picks_lookup.get(key, {}).get(mkt_label, {}).get("effectiveEdgePP_trade")
                    if picks_lookup.get(key, {}).get(mkt_label, {}).get("effectiveEdgePP_trade") is not None
                    else picks_lookup.get(key, {}).get(mkt_label, {}).get("effectiveEdgePP"))
                for mkt_label, field in _MARKET_TO_FIELD.items()
                if field in _ENGINE_FIELDS
            },
            **{
                f"engineDowngrade_{field}": picks_lookup.get(key, {}).get(mkt_label, {}).get("downgradedReason")
                for mkt_label, field in _MARKET_TO_FIELD.items()
                if field in _ENGINE_FIELDS
            },
            # Conviction-Score pro Markt (09.06.2026 — Auto-Trigger Gate)
            **{
                f"conviction_{field}": picks_lookup.get(key, {}).get(mkt_label, {}).get("convictionScore")
                for mkt_label, field in _MARKET_TO_FIELD.items()
                if field in _ENGINE_FIELDS
            },
            # Synthetic + trackingExcluded pro Markt (09.06.2026 — Auto-Trigger Gate)
            **{
                f"synthetic_{field}": picks_lookup.get(key, {}).get(mkt_label, {}).get("synthetic")
                for mkt_label, field in _MARKET_TO_FIELD.items()
                if field in _ENGINE_FIELDS
            },
            **{
                f"trackingExcluded_{field}": picks_lookup.get(key, {}).get(mkt_label, {}).get("trackingExcluded")
                for mkt_label, field in _MARKET_TO_FIELD.items()
                if field in _ENGINE_FIELDS
            },
            "dataQuality": next(
                (v.get("dataQuality") for v in picks_lookup.get(key, {}).values()), "elo_only"
            ),
        })

    # ── Edge-Momentum: Load Poly price history + Pinnacle history ────────────────
    # wm2026-poly-history.json: {matchKey: [{ts, poly_hw, poly_aw, poly_dr, poly_o25, edge_hw, ...}]}
    # Used to compute edge delta (growing/shrinking) and detect steam-lag situations.

    poly_hist: dict = {}
    if os.path.exists(POLY_HIST):
        try:
            with open(POLY_HIST, encoding="utf-8") as f:
                poly_hist = json.load(f)
        except Exception as e:
            print(f"  ⚠️  Poly-History laden fehlgeschlagen: {e}")

    pinn_hist: dict = {}
    if os.path.exists(ODDS_HIST):
        try:
            with open(ODDS_HIST, encoding="utf-8") as f:
                pinn_hist = json.load(f)
        except Exception as e:
            print(f"  ⚠️  Pinnacle-History laden fehlgeschlagen: {e}")

    now_ts = datetime.now(timezone.utc)
    now_iso = now_ts.isoformat()
    delta_cutoff = (now_ts.timestamp() - DELTA_WINDOW_H * 3600)

    # ── Append current Poly snapshot to history + compute edge momentum ───────
    for fx in all_fixtures:
        key = fx["key"]

        # Current snapshot to store
        snap = {
            "ts":       now_iso,
            "poly_hw":  fx.get("poly_hw"),
            "poly_dr":  fx.get("poly_dr"),
            "poly_aw":  fx.get("poly_aw"),
            "poly_o25": fx.get("poly_o25"),
            "poly_u25": fx.get("poly_u25"),
            "edge_hw":  fx.get("edge_hw"),
            "edge_dr":  fx.get("edge_dr"),
            "edge_aw":  fx.get("edge_aw"),
            "edge_o25": fx.get("edge_o25"),
            "edge_u25": fx.get("edge_u25"),
        }

        # Append to history (keep max 200 snapshots per match = ~40 days @ 5/day)
        hist = poly_hist.setdefault(key, [])
        hist.append(snap)
        if len(hist) > 200:
            hist[:] = hist[-200:]

        # ── Find comparison snapshot ~24h ago ─────────────────────────────────
        prev = None
        for old in reversed(hist[:-1]):  # skip the one we just appended
            try:
                old_ts = datetime.fromisoformat(old["ts"].replace("Z", "+00:00")).timestamp()
                if old_ts <= delta_cutoff:
                    prev = old
                    break
            except Exception:
                continue

        # ── Edge delta (pp change since ~24h ago) ─────────────────────────────
        def _delta(field: str) -> float | None:
            cur = fx.get(field)
            if prev is None or cur is None:
                return None
            old_v = prev.get(field)
            if old_v is None:
                return None
            return round(cur - old_v, 1)

        fx["edgeDelta_hw"]  = _delta("edge_hw")
        fx["edgeDelta_aw"]  = _delta("edge_aw")
        fx["edgeDelta_dr"]  = _delta("edge_dr")
        fx["edgeDelta_o25"] = _delta("edge_o25")
        fx["edgeDelta_u25"] = _delta("edge_u25")

        # ── Edge trend label ──────────────────────────────────────────────────
        # Based on the best-edge market's delta
        best_key = fx.get("bestEdgeKey")
        best_delta = fx.get(f"edgeDelta_{best_key}") if best_key else None
        if best_delta is None:
            fx["edgeTrend"] = "new"      # No history yet — appeared for first time
        elif best_delta >= 1.5:
            fx["edgeTrend"] = "growing"  # Edge increasing → Poly lagging behind Pinnacle
        elif best_delta <= -1.5:
            fx["edgeTrend"] = "closing"  # Edge shrinking → Poly catching up → act or skip
        else:
            fx["edgeTrend"] = "stable"   # Edge stable

        # ── Steam-Lag detection ───────────────────────────────────────────────
        # A "steam lag" is when:
        #   1. Pinnacle had a meaningful line move in the last 24h (≥2pp on any outcome)
        #   2. Poly hasn't caught up yet (edge_delta is growing or this is a new edge)
        # This is the highest-quality trade: fresh information, Poly hasn't reacted.
        steam_lag = False
        pinn_move = 0  # reset per fixture — avoids bleed-through from previous iteration
        pinn_snaps = pinn_hist.get(key, [])
        if len(pinn_snaps) >= 2:
            latest_pinn  = pinn_snaps[-1]
            # Find a Pinnacle snapshot that's ≥1h old but ≤48h old for comparison
            pinn_prev = None
            for ps in reversed(pinn_snaps[:-1]):
                try:
                    ps_ts = datetime.fromisoformat(ps["ts"].replace("Z", "+00:00")).timestamp()
                    age_h = (now_ts.timestamp() - ps_ts) / 3600
                    if 1 <= age_h <= 48:
                        pinn_prev = ps
                        break
                except Exception:
                    continue

            if pinn_prev:
                # Check if any 1X2 market moved ≥2pp on Pinnacle
                def _pinn_pp(odds_new, odds_old):
                    if not odds_new or not odds_old or odds_new <= 1 or odds_old <= 1:
                        return 0
                    return abs(round((1/odds_new - 1/odds_old) * 100, 1))

                pinn_move = max(
                    _pinn_pp(latest_pinn.get("hw"), pinn_prev.get("hw")),
                    _pinn_pp(latest_pinn.get("dr"), pinn_prev.get("dr")),
                    _pinn_pp(latest_pinn.get("aw"), pinn_prev.get("aw")),
                )
                # Steam lag: Pinnacle moved AND Poly edge is new or growing
                if pinn_move >= 2.0 and fx.get("edgeTrend") in ("growing", "new"):
                    steam_lag = True

        fx["steamLag"]      = steam_lag
        fx["pinnSteamMove"] = round(pinn_move, 1) if pinn_move > 0 else None

    # ── Compute momentum score for sorting ────────────────────────────────────
    # Prioritises: steam-lag > growing edge > high raw edge > stable edge > closing edge
    for fx in all_fixtures:
        base_edge = fx.get("bestEdge") or 0
        trend     = fx.get("edgeTrend", "stable")
        steam     = fx.get("steamLag", False)
        trend_bonus = {"growing": 3, "new": 2, "stable": 0, "closing": -2}.get(trend, 0)
        steam_bonus = 5 if steam else 0
        fx["momentumScore"] = round(base_edge + trend_bonus + steam_bonus, 1)

    # ── Sort: momentum score first (best opportunities top), then date ─────────
    all_fixtures.sort(key=lambda x: (
        -x.get("momentumScore", 0),
        x.get("date") or ""
    ))

    # Save updated poly history
    try:
        with open(POLY_HIST, "w", encoding="utf-8") as f:
            json.dump(poly_hist, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  📊 Poly-History aktualisiert: {sum(len(v) for v in poly_hist.values())} Snapshots total")
    except Exception as e:
        print(f"  ⚠️  Poly-History schreiben fehlgeschlagen: {e}")

    n_pinn   = sum(1 for f in all_fixtures if f['hasPinnacle'])
    n_edge   = sum(1 for f in all_fixtures if (f['bestEdge'] or 0) >= 3)
    n_steam  = sum(1 for f in all_fixtures if f.get('steamLag'))
    n_grow   = sum(1 for f in all_fixtures if f.get('edgeTrend') == 'growing')
    n_ou     = sum(1 for f in all_fixtures if f.get('poly_o25'))
    print(f"  allFixtures: {len(all_fixtures)} total"
          f" | {n_pinn} Pinnacle | edge≥3pp: {n_edge}"
          f" | 🔥 SteamLag: {n_steam} | 📈 growing: {n_grow}"
          f" | O/U: {n_ou}")

    # ── Abdeckungs-Alarm (28.08.2026): fehlt ein Spiel, dessen Anpfiff bevorsteht? ──
    _luecken = fehlende_nah_fixtures(wm, prices)
    if _luecken:
        print(f"  🚨 {len(_luecken)} Fixture(s) mit Anpfiff <48h ohne Polymarket-Markt:")
        for _l in _luecken[:8]:
            print(f"     – {_l['home']} vs {_l['away']}  [{_l['key']}]  {_l['kickoff']}")
    elif wm is None:
        # Ohne Fixture-Datei ist „keine Lücke" keine Aussage — fail-closed formulieren.
        print("  ⚠️  Abdeckung nicht prüfbar — keine Fixture-Datei geladen")
    else:
        print("  ✅ Alle Fixtures mit Anpfiff <48h haben einen Polymarket-Markt")

    # ── Market Depth: CLOB bid/ask für Top-Edge-Fixtures ─────────────────────
    # Nur Fixtures mit bestEdge ≥ 3pp → max 15 CLOB-Requests pro Run
    _CLOB_EDGE_MIN = 3.0
    _CLOB_MAX_FIXTURES = 15
    _TOKEN_FIELD_MAP = {"hw": "hwTokens", "dr": "drTokens", "aw": "awTokens"}

    depth_candidates = [
        fx for fx in all_fixtures
        if (fx.get("bestEdge") or 0) >= _CLOB_EDGE_MIN and fx.get("bestEdgeKey") in _TOKEN_FIELD_MAP
    ][:_CLOB_MAX_FIXTURES]

    if depth_candidates:
        print(f"  📊 CLOB Depth fetching für {len(depth_candidates)} Fixtures…")
        for fx in depth_candidates:
            best_key    = fx["bestEdgeKey"]
            token_field = _TOKEN_FIELD_MAP[best_key]
            tokens      = fx.get(token_field, [])
            yes_token   = tokens[0] if tokens else None
            if not yes_token:
                continue
            depth = fetch_clob_depth(yes_token)
            if depth:
                fx["clobBid"]      = depth["bid"]
                fx["clobAsk"]      = depth["ask"]
                fx["clobSpreadPP"] = depth["spreadPP"]
                fx["clobTopLiq"]   = depth["topLiqUSD"]
                fx["clobMarket"]   = best_key

    # ── Telegram Edge Alerts — neue Edges über Schwellenwert ─────────────────
    # Feuert nur für edgeTrend='new' (= erstmals in diesem Run aufgetaucht).
    # Keine Tracking-Datei nötig — 'new' tritt genau einmal pro Fixture auf.
    _ALERT_MARKET_LABELS = {
        "hw": "Heimsieg", "dr": "Unentschieden", "aw": "Auswärtssieg",
        "o25": "Over 2.5", "u25": "Under 2.5",
    }
    _tg_token  = os.environ.get("TELEGRAM_TOKEN", "").strip()
    _tg_chat   = os.environ.get("TELEGRAM_TRADES_CHAT_ID", "").strip()

    if _tg_token and _tg_chat:
        # AUDIT-Fix 06.06.2026: Per-Match-per-Day-Dedup für Edge-Alerts.
        # Vorher: alle 4h würde derselbe Edge erneut gemeldet → 5×/Tag Spam.
        # Jetzt: jede (matchKey × bestEdgeKey) max 1× pro 12h via dedup-state file.
        # CRITICAL Bug-Fix 08.06.2026: Lokaler `from datetime import datetime`
        # triggerte Python's local scope rule — Line 625 (`datetime.now()`) crashte
        # mit UnboundLocalError ein paar 100 Zeilen FRÜHER. Resultat: wm_poly_prices.json
        # seit 2+ Tagen nicht geschrieben → Steam-Lag-Monitor las stale Daten.
        # Fix: timedelta global oben importiert, lokaler Import entfernt.
        EDGE_ALERT_DEDUP_FILE = str(D.file("wm_edge_alert_dedup.json", "liga_edge_alert_dedup.json"))
        EDGE_DEDUP_HOURS = _cfg("dedup_hours", "edge_alert", 12)
        dedup_state = {}
        if os.path.exists(EDGE_ALERT_DEDUP_FILE):
            try:
                with open(EDGE_ALERT_DEDUP_FILE) as f:
                    dedup_state = json.load(f)
            except Exception:
                dedup_state = {}
        now_iso = datetime.now(timezone.utc).isoformat()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=EDGE_DEDUP_HOURS)).isoformat()

        def _was_alerted_recently(fx) -> bool:
            dedup_key = f"{fx.get('key', '?')}|{fx.get('bestEdgeKey', '?')}"
            last = dedup_state.get(dedup_key)
            return bool(last) and last >= cutoff

        # FIX 25.07.2026 (Lucas): Alerts nur aus LIQUIDEN Poly-Märkten (siehe alert_market_liquid) —
        # sonst ist der Poly-Preis Rauschen und die „Edge" ein Artefakt. Gilt für neue Edges + Steam.
        _alert_liquid = alert_market_liquid

        # FIX 12.06.2026: _kickoff_passed-Guard — KEINE Edge-Alerts nach Anpfiff.
        # MEX-ZAF feuerte 22:18 UTC (Spiel 19:00 UTC vorbei). Edge-Alert ist Pre-Match.
        alert_queue = [
            fx for fx in all_fixtures
            if fx.get("edgeTrend") == "new" and (fx.get("bestEdge") or 0) >= ALERT_EDGE_MIN_PP
               and _alert_liquid(fx)
               and not _kickoff_passed(fx)
               and not _was_alerted_recently(fx)
        ]
        steam_alerts = [
            fx for fx in all_fixtures
            if fx.get("steamLag") and fx.get("edgeTrend") in ("growing",)
               and (fx.get("bestEdge") or 0) >= ALERT_EDGE_MIN_PP
               and _alert_liquid(fx)
               and not _kickoff_passed(fx)
               and fx not in alert_queue
               and not _was_alerted_recently(fx)
        ]
        _max_alerts = _cfg("telegram", "max_alerts_per_run", 4)
        alert_queue = (alert_queue + steam_alerts)[:_max_alerts]  # max N Alerts pro Run

        for fx in alert_queue:
            is_steam   = fx.get("steamLag") and fx.get("edgeTrend") == "growing"
            signal     = "🔥 Steam Lag" if is_steam else "🆕 Neue Edge"
            best_key   = fx.get("bestEdgeKey", "hw")
            market     = _ALERT_MARKET_LABELS.get(best_key, best_key)
            edge       = fx.get("bestEdge") or 0
            poly_field = f"poly_{best_key}"
            poly_p     = fx.get(poly_field)
            poly_odds  = f"{1/poly_p:.2f}" if poly_p and poly_p > 0 else "?"
            slug       = fx.get("slug", "")
            # 19.07.2026: generischer /event/-Deep-Link (der alte /sports/fifa-world-cup/-Pfad war
            # für MLS-Slugs schlicht falsch).
            poly_url   = f"https://polymarket.com/event/{slug}" if slug else ""
            pinn_field = f"pinn_{best_key}"
            pinn_raw   = fx.get(pinn_field)
            pinn_str   = f" | Pinn {pinn_raw:.2f}" if pinn_raw else ""
            clob_str   = ""
            if fx.get("clobBid") and fx.get("clobMarket") == best_key:
                clob_str = (f"\n📋 Orderbook: Bid {round(fx['clobBid']*100)}¢"
                            f" | Ask {round(fx['clobAsk']*100)}¢"
                            f" | Spread {fx['clobSpreadPP']}pp"
                            f" | Liq ${fx.get('clobTopLiq',0):,.0f}")
            mom = fx.get("momentumScore", 0)

            # 19.07.2026: Label datensatz-aware — die Alerts liefen unter „WM" auch für MLS-Spiele.
            _ds_label = {"wm": "WM", "liga": "Liga", "mls": "MLS"}.get(D.active_dataset(), D.active_dataset().upper())
            msg = (
                f"⚡ <b>{_ds_label} Edge Alert — {signal}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🏆 {fx.get('home')} vs {fx.get('away')}\n"
                f"📋 Markt: <b>{market}</b>\n"
                f"🎯 Edge: <b>+{edge:.1f}pp</b> vs Pinnacle fair\n"
                f"📊 Poly: {poly_odds}{pinn_str}\n"
                f"⚡ Momentum: {mom:.1f}"
                f"{clob_str}"
                + (f"\n🔗 {poly_url}" if poly_url else "")
            )

            try:
                import urllib.parse
                tg_payload = json.dumps({
                    "chat_id": _tg_chat, "text": msg,
                    "parse_mode": "HTML", "disable_web_page_preview": True,
                }).encode()
                tg_req = urllib.request.Request(
                    f"https://api.telegram.org/bot{_tg_token}/sendMessage",
                    data=tg_payload, headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(tg_req, timeout=10):
                    pass
                print(f"  📱 Edge Alert: {fx.get('home')} vs {fx.get('away')} "
                      f"+{edge:.1f}pp [{signal}]")
            except Exception as e_tg:
                print(f"  ⚠️  Telegram Edge Alert fehlgeschlagen: {e_tg}")
            else:
                # AUDIT-Fix 06.06.2026: Dedup-State updaten nach erfolgreichem Send
                dedup_key = f"{fx.get('key', '?')}|{fx.get('bestEdgeKey', '?')}"
                dedup_state[dedup_key] = now_iso

        # Dedup-State persistieren (alte Einträge wegmüllen)
        dedup_state = {k: v for k, v in dedup_state.items() if v >= cutoff}
        try:
            with open(EDGE_ALERT_DEDUP_FILE, "w") as f:
                json.dump(dedup_state, f, indent=2)
        except Exception as e:
            print(f"  ⚠️  Konnte Edge-Dedup-State nicht speichern: {e}")
    else:
        if not _tg_chat:
            print("  📵 TELEGRAM_TRADES_CHAT_ID nicht gesetzt — Edge Alerts deaktiviert")

    # ── Write output JSON ─────────────────────────────────────────────────────
    # WIPE-SCHUTZ (12.07.2026, Wipe-Audit): Gamma kann 200 + LEERE Liste liefern (Geoblock,
    # geänderter Serien-Slug/Tag) → ok == 0. Vorher wurde die Datei trotzdem mit
    # {"prices": {}, "count": 0} überschrieben → Poly-Tab, Edge-Board und die Smart-Money-Kette
    # (die auf wm_poly_prices.json aufsetzt) waren tot. Bei 0 Märkten NICHT schreiben.
    if ok == 0 and os.path.exists(str(OUT_FILE)):
        print(f"\n❌ 0 Märkte von Gamma (Geoblock/Slug/Ausfall?) — {os.path.basename(str(OUT_FILE))} "
              f"NICHT überschrieben, alter Stand bleibt erhalten.")
        return
    out = {
        "prices":      prices,
        "allFixtures": all_fixtures, # All 72 games — momentum scores, edge trends, CLOB depth
        "count":       ok,
        "generatedAt": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {ok} matches written → {os.path.basename(str(OUT_FILE))}  ({skip} skipped)")


if __name__ == "__main__":
    main()
