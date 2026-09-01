#!/usr/bin/env python3
"""
wm_data_integrity.py — Härtung der Daten-Pipeline (erweiterbare Guard-Registry).

Eine Prüf-Batterie über GENAU die Felder, die Picks/Signale/Trades treiben — und
die uns reihenweise wehgetan haben (Venue, Kickoff, Home/Away, Stale-Edge,
Schedule-Datum). Jeder Check liefert ein strukturiertes Ergebnis, das
pre_match_readiness in wm_status.json["checks"] schreibt und die Status-Seite als
benannten Guard mit ✅/🔴 + Fehlerliste rendert.

Leitprinzip: Wenn ein Datenpunkt kippt, auf dem Lucas Geld setzt, MUSS es sichtbar
werden — nicht still weggeguardet.

═══════════════════════════════════════════════════════════════════════════════
  NEUEN GUARD HINZUFÜGEN (wenn wir einen neuen schweren Fehler finden):
  ───────────────────────────────────────────────────────────────────────────
  1. Funktion schreiben, mit @integrity_check dekorieren:

       @integrity_check
       def check_mein_neuer_guard(ctx):
           fails = []
           for gkey, fx in ctx.fixtures:
               if <etwas stimmt nicht>:
                   fails.append(f"{ctx.mk(fx)}: <was genau falsch ist>")
           return _chk("mein_guard", "Lesbares Label", "error", fails,
                       "Warum es zählt / welcher Bug dahinter steckt.")

  2. Fertig. Erscheint automatisch in wm_status.json["checks"] + auf der
     Status-Seite. severity: "error" (geld-kritisch) | "warn" | "info".
     ctx hat: .wm .poly .schedule .venues .fixtures .odds .poly_prices
              .poly_all .venue_ids  + Helfer ctx.mk(fx), ctx.venue_id(v).
     Ein Check der crasht killt die Batterie NICHT (wird als warn gemeldet).
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path as _Path

import cocobet_dataset as D   # 29.06.2026: dataset-aware (mls neben wm/liga)

_BASE = _Path(__file__).resolve().parent


# Dateien, die in diesem Lauf nicht gelesen werden konnten (siehe check_inputs_readable).
_LAZY_FAILED: set = set()


def _lazy(fname):
    """Best-effort-Load einer JSON neben diesem Modul (für Guards, die nicht über
    run_checks injiziert werden — z.B. Auto-Bets/Odds-History)."""
    try:
        import json as _json
        p = _BASE / fname
        if not p.exists():
            return {}
        data = _json.loads(p.read_text(encoding="utf-8"))
        _LAZY_FAILED.discard(fname)
        return data
    except Exception as e:
        # 25.08.2026 (Audit-Befund 14): vorher still `{}` — und fuenf als GELD-KRITISCH markierte
        # Guards meldeten daraufhin gruen, weil sie ueber eine leere Liste iterierten. Ein Guard,
        # der seine Datei nicht lesen konnte, hat NICHTS geprueft und darf das nicht verschweigen.
        print(f"  ⚠️  {fname} nicht lesbar: {e}")
        _LAZY_FAILED.add(fname)
        return {}

# Venue-Name/City-Substring → venue_id (Spiegel von generate_wm_picks._VENUE_NAME_TO_ID).
_VENUE_NAME_TO_ID = {
    "azteca": "mexico_city", "mexico city": "mexico_city", "monterrey": "monterrey",
    "guadalajara": "guadalajara", "akron": "guadalajara", "bbva": "monterrey",
    "rose bowl": "los_angeles", "sofi": "los_angeles", "inglewood": "los_angeles",
    "los angeles": "los_angeles", "at&t": "dallas", "arlington": "dallas", "dallas": "dallas",
    "nrg": "houston", "houston": "houston", "mercedes-benz": "atlanta", "mercedes benz": "atlanta",
    "atlanta": "atlanta", "gillette": "boston", "foxborough": "boston", "boston": "boston",
    "metlife": "new_york", "east rutherford": "new_york", "new york": "new_york", "new jersey": "new_york",
    "lincoln": "philadelphia", "philadelphia": "philadelphia", "levi": "san_francisco",
    "santa clara": "san_francisco", "san francisco": "san_francisco", "lumen": "seattle",
    "seattle": "seattle", "hard rock": "miami", "miami": "miami", "arrowhead": "kansas_city",
    "kansas city": "kansas_city", "bc place": "vancouver", "vancouver": "vancouver",
    "bmo": "toronto", "toronto": "toronto",
}
TOURNEY_START = "2026-06-11"
TOURNEY_END   = "2026-07-20"


def _venue_id(venue):
    if not isinstance(venue, str) or not venue.strip():
        return None
    n = venue.lower()
    for key, vid in _VENUE_NAME_TO_ID.items():
        if key in n:
            return vid
    return None


def _chk(cid, label, severity, failures, note=""):
    failures = list(failures)
    return {"id": cid, "label": label, "severity": severity,
            "ok": len(failures) == 0, "nFail": len(failures),
            "failures": failures[:25], "note": note}


class IntegrityCtx:
    """Geteilter Kontext für alle Checks — einmal gebaut, an jeden Guard gereicht."""
    def __init__(self, wm, poly, schedule, venues, lineups=None, now=None,
                 auto_bets=None, history=None, streaks=None):
        self.wm = wm or {}
        # Klub-Modus (25.06.2026, Lucas): einige Guards sind WM-spezifisch (venue_id gegen WM-Stadien,
        # Kickoff-Turnier-Fenster Juni/Juli, time-Feld) → feuern auf Liga/MLS falsch. is_liga lässt sie
        # passen. 29.06.2026: gilt jetzt für JEDES Nicht-WM-Profil (liga_default UND mls_default), sonst
        # tripten alle WM-Stadion-/Kickoff-Guards die MLS-Daten.
        self.is_liga = ((self.wm.get("_meta") or {}).get("profile", "wm2026") != "wm2026")
        self.poly = poly or {}
        self.schedule = schedule or {}
        self.venues = venues or {}
        self.lineups = lineups or {}
        self.now = now or datetime.now(timezone.utc)
        # Auto-Bets + Odds-History (14.06.2026): injizierbar (Tests) oder lazy von Disk.
        # 13.07.2026 — 🔴 GELD-KRITISCH. War hart `wm_auto_bets_placed.json`: unter
        # COCOBET_DATASET=mls prüften damit FÜNF Guards die WM-Wetten statt der MLS-Positionen —
        # darunter check_autobet_kickoff_present, der nach dem In-Play-Verlust QAT–SUI (−€5,50)
        # gebaut wurde. Sobald der MLS-Auto-Trader scharf ist, schreibt er nach
        # mls_auto_bets_placed.json — und KEIN Guard hätte je hingesehen. Genau der Schutz, der
        # greifen soll, wäre in dem Moment blind, in dem Geld fließt.
        _ab = auto_bets if auto_bets is not None else _lazy(
            D.file("wm_auto_bets_placed.json", "liga_auto_bets_placed.json").name)
        self.auto_bets = (_ab.get("bets") if isinstance(_ab, dict) else _ab) or []
        # Odds-History dataset-bewusst (26.06.2026): Liga-Guards (z.B. soft_opening_captured) liefen
        # sonst gegen die WM-History → effektiv tot. is_liga kommt aus _meta.profile (oben gesetzt).
        # dataset-aware (29.06.2026): wm2026-/liga-/mls-odds-history.json je COCOBET_DATASET.
        _hist_default = D.file("wm2026-odds-history.json", "liga-odds-history.json").name
        self.history = (history if history is not None else _lazy(_hist_default)) or {}
        # Serien-File dataset-aware (29.06.2026): {wm_,liga_,mls_}streaks.json. Injizierbar (Tests).
        _streaks_default = D.file("wm_streaks.json", "liga_streaks.json").name
        self.streaks = (streaks if streaks is not None else _lazy(_streaks_default)) or {}
        self.fixtures = [(g, fx) for g, gd in (self.wm.get("groups") or {}).items()
                         for fx in (gd.get("fixtures") or [])]
        self.odds = self.wm.get("odds") or {}
        self.poly_prices = (self.poly.get("prices") if isinstance(self.poly, dict) else {}) or {}
        self.poly_all = (self.poly.get("allFixtures") if isinstance(self.poly, dict) else []) or []
        self.venue_ids = set((self.venues.get("venues") or {}).keys())

    @staticmethod
    def mk(fx):
        return f"{fx.get('home')}-{fx.get('away')}"

    @staticmethod
    def venue_id(v):
        return _venue_id(v)


# ── Registry ────────────────────────────────────────────────────────────────
INTEGRITY_CHECKS = []
def integrity_check(fn):
    INTEGRITY_CHECKS.append(fn)
    return fn


# ── Die Guards (je @integrity_check) ─────────────────────────────────────────

@integrity_check
def check_inputs_readable(ctx):
    """25.08.2026 (Audit-Befund 14): Konnte diese Guard-Batterie ihre Eingaben ueberhaupt lesen?

    `_lazy` gibt bei einem Lesefehler `{}` zurueck. Fuenf im Code als GELD-KRITISCH markierte Guards
    iterieren dann ueber eine leere Liste, finden nichts zu bemaengeln und melden GRUEN — genau in
    dem Moment, in dem sie am dringendsten gebraucht wuerden. Dieser Guard macht den Zustand
    sichtbar, statt ihn den anderen zu ueberlassen.

    Bewusst `error`: eine Batterie, die blind ist, ist keine Warnung wert, sondern ein Stopp-Signal.
    """
    fails = [f"{f} nicht lesbar — jeder Guard, der sie braucht, hat NICHTS geprueft"
             for f in sorted(_LAZY_FAILED)]
    return _chk("inputs_readable", "Guard-Eingaben lesbar", "error", fails,
                "Ein leeres Ergebnis kann 'nichts zu bemaengeln' ODER 'Datei kaputt' heissen. "
                "Solange dieser Guard rot ist, sind die gruenen Haken der anderen wertlos.")


RESOLVE_STALE_DAYS = 3     # so lange darf ein gespieltes Match unaufgelöst bleiben
RESOLVE_MAX_OPEN   = 25    # darüber ist es kein Rückstand mehr, sondern ein Ausfall


def _picks_history_open(history, today=None):
    """(offene Alt-Einträge, aeltester Tag). REIN — wirft nie, auch bei Müll-Zeilen."""
    import datetime as _dt
    today = today or _dt.date.today()
    offen, aeltester = 0, None
    try:
        import stats_scope as _scope
        umfang = _scope.load()
    except Exception:
        umfang = {}
    for e in (history or []):
        if not isinstance(e, dict) or e.get("resolved"):
            continue
        # 27.08.2026 (Lucas): nur zählen, was auch in die Bilanz zählt. picks_history schleppt
        # 20 Ligen aus dem alten breiten Card-System mit; ein Guard, der über Ungarn und
        # Schottland meckert, wird nach drei Tagen ignoriert — und dann übersieht man den Tag,
        # an dem er recht hat.
        if umfang and not _scope.counts(e.get("league"), e.get("dateIso"), umfang):
            continue
        raw = str(e.get("dateIso") or "")[:10]
        d = None
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                d = _dt.datetime.strptime(raw or str(e.get("date") or "")[:10], fmt).date()
                break
            except ValueError:
                continue
        if d is None or (today - d).days < RESOLVE_STALE_DAYS:
            continue
        offen += 1
        if aeltester is None or d < aeltester:
            aeltester = d
    return offen, aeltester


@integrity_check
def check_picks_resolved(ctx):
    """27.08.2026 (Lucas: „Real Madrid war noch nicht ausgewertet"): resolve_picks.py starb an
    einem KeyError, weil ZWEI Poly-Direktwetten kein `dateIso` hatten. Der Workflow-Schritt
    steht auf `continue-on-error: true` — der Job lief grün weiter, committete die anderen
    Dateien, und seit dem 31.05. wurde KEIN Pick mehr aufgelöst. 315 Einträge, zwei Monate,
    kein einziges rotes Licht.

    Ohne Auflösung hungert der Lern-Loop, die Trefferquoten frieren ein und die Recaps sind
    leer — alles Symptome, die man einzeln für sich erklaert. Dieser Guard nennt die Ursache.
    """
    hist = _lazy("picks_history.json")
    if not isinstance(hist, list):
        return _chk("picks_resolved", "Picks aufgelöst", "warn", [],
                    "picks_history.json ist keine Liste — nichts zu prüfen.")
    offen, aeltester = _picks_history_open(hist)
    fails = []
    if offen > RESOLVE_MAX_OPEN:
        fails.append("%d gespielte Matches älter als %d Tage sind unaufgelöst (ältestes %s) "
                     "— resolve_picks.py läuft nicht durch"
                     % (offen, RESOLVE_STALE_DAYS, aeltester))
    return _chk("picks_resolved", "Picks aufgelöst", "error", fails,
                "Ein Rückstand von ein paar Spielen ist normal. Dreistellig heißt: der "
                "Resolver stirbt still, und alles was auf Ergebnissen aufbaut lernt nichts mehr.")


RUN_HEALTH_DIR = "health"
# Ab wann gilt ein Workflow als „meldet sich nicht mehr"? 26 h laesst einen taeglichen Lauf
# einmal ausfallen, ohne zu schreien — zwei Ausfaelle hintereinander sind ein Muster.
RUN_HEALTH_STALE_H = 26


def _alter_h(ts, jetzt):
    """Alter eines ISO-Zeitstempels in Stunden — None, wenn er nicht lesbar ist.

    None heisst hier bewusst „unbekannt", nicht „frisch": der Aufrufer prueft dann keine
    Ueberfaelligkeit, statt sie faelschlich als bestanden zu melden.
    """
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (jetzt - d).total_seconds() / 3600.0


def _run_health_dateien():
    ordner = _BASE / RUN_HEALTH_DIR
    try:
        return sorted(ordner.glob("*.json"))
    except Exception:
        return []


@integrity_check
def check_run_health(ctx):
    """28.08.2026 (Lucas: „stehen da Fehler die wir gar nicht mitkriegen?") — ja, 135 Stueck.

    So viele Steps stehen auf `continue-on-error: true`; dazu 279 `|| true`. Ein Job kann
    komplett gruen durchlaufen, waehrend ein Drittel davon gescheitert ist. Genau so war
    resolve_picks.py drei Monate lang tot, ohne ein einziges rotes Licht.

    run_health.py fragt am Ende jedes Laufs ueber die GitHub-API die eigenen Steps ab und legt
    das Ergebnis in health/<slug>.json. Dieser Guard holt es auf die Status-Seite — sonst waere
    es wieder nur verdrahtet und nicht angekommen.

    Drei Dinge gelten als Fehler:
      * ein Step des letzten Laufs ist gescheitert (auch wenn der Job gruen war),
      * der Waechter konnte die API nicht fragen (dann wissen wir es NICHT — und das ist kein Gruen),
      * eine Health-Datei ist ueberfaellig, der Workflow meldet sich also gar nicht mehr.
    """
    import json as _json
    dateien = _run_health_dateien()
    if not dateien:
        return _chk("run_health", "Workflow-Laeufe fehlerfrei", "warn", [],
                    "Noch keine health/*.json — run_health.py laeuft in keinem Workflow.")
    jetzt = ctx.now if getattr(ctx, "now", None) else datetime.now(timezone.utc)
    fails = []
    for pfad in dateien:
        try:
            d = _json.loads(pfad.read_text(encoding="utf-8"))
        except Exception as e:
            fails.append("%s nicht lesbar: %s" % (pfad.name, e))
            continue
        name = d.get("workflow") or d.get("slug") or pfad.stem
        laeufe = d.get("runs") or []
        if not laeufe:
            fails.append("%s: keine Laeufe verzeichnet" % name)
            continue
        letzter = laeufe[0]
        if letzter.get("apiError"):
            fails.append("%s: Lauf-Gesundheit UNBEKANNT (%s)" % (name, letzter["apiError"]))
        for f in (letzter.get("failures") or [])[:5]:
            fails.append("%s: Step '%s' %s — Job trotzdem gruen"
                         % (name, f.get("step"), f.get("conclusion")))
        alter = _alter_h(letzter.get("ts"), jetzt)
        if alter is not None and alter > RUN_HEALTH_STALE_H:
            fails.append("%s: seit %.0f h kein Lauf mehr verzeichnet" % (name, alter))
    return _chk("run_health", "Workflow-Laeufe fehlerfrei", "error", fails,
                "Quelle: health/*.json (run_health.py). Leere Liste heisst hier wirklich "
                "'nichts gescheitert' — ein nicht abfragbarer Lauf steht oben als UNBEKANNT.")


@integrity_check
def check_poly_surfaces_alive(ctx):
    """20.07.2026 — die globalen Poly-Tracking-Flächen (Cross-Sport-Radar, E-Sport, Poly-Geld breit)
    dürfen nicht STILL sterben. Zwei lagen seit Bau tot da, ohne dass ein Guard hinsah. Prüft NICHT
    „hat Inhalt" (leer-aber-frisch ist ok), sondern „hat der Produzent kürzlich geschrieben".

    Nur unter MLS (der Mac-Runner, der diese globalen Dateien erzeugt) — sonst dreifach gemeldet.
    severity=warn: eine gestandene Tracking-Fläche ist ein Hinweis, kein Geld-Stopp."""
    if (ctx.wm.get("_meta") or {}).get("profile") != "mls_default":
        return None
    try:
        import check_poly_surfaces_alive as PSA
        fails = PSA.evaluate(PSA.collect(), now=ctx.now)
    except Exception as e:
        fails = [f"Guard selbst gescheitert: {e}"]
    return _chk("poly_surfaces_alive", "Poly-Flächen liefern (kein stiller Tod)", "warn", fails,
                note="Cross-Sport-Radar, E-Sport, Poly-Geld breit — frisch geschrieben (leer ok, tot nicht).")


@integrity_check
def check_learning_loop_alive(ctx):
    """20.07.2026 (MLS-Audit) — sobald Picks auflösen, MUSS der Signal-Ledger wachsen und Closing/CLV
    ankommen. Tut es das nicht, ist der Lern-Loop still tot (CLV-für-Liga+MLS-war-tot-Klasse). Jung =
    noch keine Resolves = grün; Resolves aber leerer Ledger/kein Closing = rot. Datensatz-aware."""
    try:
        import check_learning_loop_alive as LLA
        ledger_file = D.file("wm_signal_ledger.json", "liga_signal_ledger.json").name
        clv_file = D.file("wm_clv_summary.json", "liga_clv_summary.json").name
        data_file = D.data_file().name
        m = LLA.collect(ledger_file, clv_file, data_file)
        # 27.07.2026 (Lucas: „lernt MLS?"): jetzt auch graded (0 bewertet trotz Einträge) + xG-Coverage
        fails = LLA.evaluate(m["resolved"], m["ledger_records"], m["with_closing"],
                             graded=m["graded"], finished=m["finished"],
                             finished_with_xg=m["finished_with_xg"])
    except Exception as e:
        fails = [f"Guard selbst gescheitert: {e}"]
    return _chk("learning_loop_alive", "Lern-Loop lernt (Ledger + CLV bei Resolves)", "warn", fails,
                note="Jung/keine Resolves = ok; aufgelöste Picks ohne Ledger/Closing = tot.")


@integrity_check
def check_odds_field_plausible(ctx):
    """22.07.2026 (Lucas: „fix das EIN FÜR ALLE MAL") — die wiederkehrende Platzhalter-Klasse
    (1.04/1.04/1.04, dr=1.01 …) rutschte 5×+ still ins `odds`-Feld, weil jeder Writer separat
    geprüft wurde und keiner die ANKUNFT im Feld prüfte. Fair/Edge/Steam/Trade rechnen alle gegen
    dieses aktuelle 1X2 — ein Platzhalter dort ist ein stiller Geld-Bug. Dieser Guard ist die EINE
    Quelle: scannt das geschriebene odds-Feld auf implausible aktuelle 1X2, egal welcher Fetcher es
    schrieb. Jede künftige Leck-Stelle fällt hier auf, nicht erst in einem Fake-Pick.
    severity=error: ein Platzhalter im aktiven Odds-Anker ist kein kosmetisches Problem."""
    try:
        from odds_plausibility import plausible_1x2 as _pl
    except Exception as e:
        return _chk("odds_field_plausible", "Odds-Feld 1X2 plausibel (kein Platzhalter-Leck)",
                    "error", [f"Guard selbst gescheitert: {e}"])
    fails = []
    for key, snap in (ctx.odds or {}).items():
        if not isinstance(snap, dict):
            continue
        hw, dr, aw = snap.get("hw"), snap.get("dr"), snap.get("aw")
        if hw is None and dr is None and aw is None:
            continue   # 1X2 bewusst abwesend (gate ließ nichts Plausibles durch) → korrekt, kein Leck
        if not _pl(hw, dr, aw):
            ov = None
            try:
                ov = round(sum(1.0 / x for x in (hw, dr, aw) if x), 3)
            except Exception:
                pass
            fails.append(f"{key}: aktuelles 1X2 hw={hw} dr={dr} aw={aw} implausibel"
                         + (f" (Overround {ov})" if ov else ""))
    return _chk("odds_field_plausible", "Odds-Feld 1X2 plausibel (kein Platzhalter-Leck)",
                "error", fails,
                note="EINE Quelle gegen die Platzhalter-Klasse. Schreibquelle = build_odds_entry "
                     "(gate+carry). Leck hier = ein Fetcher schrieb rohes 1X2 ohne Gate.")


@integrity_check
def check_venue_resolves(ctx):
    if ctx.is_liga:
        return None   # WM-Venue-Map gilt nicht für Liga-Stadien
    fails = []
    for _g, fx in ctx.fixtures:
        vid = ctx.venue_id(fx.get("venue"))
        if vid is None:
            fails.append(f"{ctx.mk(fx)}: Venue '{fx.get('venue')}' → kein venue_id")
        elif vid not in ctx.venue_ids:
            fails.append(f"{ctx.mk(fx)}: venue_id '{vid}' fehlt in wm_venues.json")
    return _chk("venue_resolves", "Venue → venue_id auflösbar", "error", fails,
                "Treibt travel_burden/altitude/weather. Fallback = falsche Signale.")


@integrity_check
def check_venue_matches_schedule(ctx):
    if not ctx.schedule:
        return None
    fails = []
    for _g, fx in ctx.fixtures:
        s = ctx.schedule.get(ctx.mk(fx))
        if not (s and s.get("venue")):
            continue
        fxv, sv = fx.get("venue"), s["venue"]
        if fxv == sv:
            continue
        # Stadt-/Marketing-Labels weichen oft ab (Levi's „Santa Clara" vs
        # „San Francisco Bay Area", SoFi „Inglewood" vs „Los Angeles"). Nur ECHT
        # verschiedene Stadien (verschiedene venue_id) sind ein Fehler — gleicher
        # venue_id = bloßes Label-Rauschen, kein Daten-Problem (16.06.2026).
        vid_fx, vid_s = _venue_id(fxv), _venue_id(sv)
        if vid_fx and vid_s and vid_fx == vid_s:
            continue
        detail = (f" (venue_id {vid_fx}≠{vid_s})" if vid_fx and vid_s else " (nicht auflösbar)")
        fails.append(f"{ctx.mk(fx)}: '{fxv}' ≠ Schedule '{sv}'{detail}")
    return _chk("venue_matches_schedule", "Venue == API-Football-Schedule", "warn", fails,
                "Nur echte Stadion-Abweichung (verschiedene venue_id) zählt; reine "
                "Stadt-Label-Unterschiede (gleiches venue_id) werden ignoriert. "
                "Seed-Venues waren reihenweise falsch (KOR-CZE SoFi statt Guadalajara).")


def _finished_keys(ctx):
    """Match-Keys (HOME-AWAY) BEENDETER Spiele (07.07.2026, Lucas: Status aufräumen). Readiness-
    Guards, die eine Write-Seiten-Aktion einfordern, sollen nur AKTIONABLE (anstehende/live) Spiele
    flaggen — auf ein beendetes Spiel lässt sich Closing/Safer-Line/Odds nicht mehr anwenden; die
    historische CLV-Wirkung trägt compute_clv_summary. Live-Lecks werden weiter geflaggt."""
    FINAL = {"FT", "AET", "PEN", "AWD", "WO"}
    done = set()
    for gd in (ctx.wm.get("groups") or {}).values():
        for fx in gd.get("fixtures", []):
            if fx.get("home") and str((fx.get("result") or {}).get("status") or "").upper() in FINAL:
                done.add(f"{fx['home']}-{fx['away']}")
    for kf in (ctx.wm.get("koFixtures") or []):
        if kf.get("home") and str((kf.get("result") or {}).get("status") or "").upper() in FINAL:
            done.add(f"{kf['home']}-{kf['away']}")
    return done


@integrity_check
def check_closing_prematch(ctx):
    """In-Play-Schutz für den CLV (16.06.2026 → QAT-SUI-Phantom).

    Ein Closing-Snapshot, der NACH Anpfiff eingefroren wurde, enthält Live-Quoten
    (QAT-SUI o25=21.0 / hw=81.0 bei spätem 1:1) → −55pp CLV-Phantom, das den
    Dashboard-avgCLV verzerrt. Der Resolver verwirft solche Snapshots inzwischen
    (resolve_wm_results.closing_is_prematch); dieser Guard macht die Lecks sichtbar,
    damit die Write-Seite (Closing-Freeze) nachgezogen werden kann.
    """
    cl = _lazy(D.file("wm_closing_lines.json", "liga_closing_lines.json").name)
    if not isinstance(cl, dict) or not cl:
        return None
    ko_by_key = {ctx.mk(fx): fx.get("kickoff") for _g, fx in ctx.fixtures}
    finished = _finished_keys(ctx)
    fails = []
    for key, snap in cl.items():
        if not isinstance(snap, dict) or key in finished:
            continue   # beendete Spiele: historisch, nicht mehr aktionierbar (CLV-Summary trägt es)
        frozen, ko = snap.get("frozenAt"), ko_by_key.get(key)
        if not frozen or not ko:
            continue
        try:
            fz = datetime.fromisoformat(str(frozen).replace("Z", "+00:00"))
            kk = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        except Exception:
            continue
        if fz.tzinfo is None: fz = fz.replace(tzinfo=timezone.utc)
        if kk.tzinfo is None: kk = kk.replace(tzinfo=timezone.utc)
        late_min = (fz - kk).total_seconds() / 60.0
        if late_min > 10:
            fails.append(f"{key}: Closing +{late_min:.0f}min nach Anpfiff eingefroren "
                         f"(In-Play → CLV verworfen)")
    return _chk("closing_prematch", "Closing-Snapshot vor Anpfiff (kein In-Play-Leck)", "warn", fails,
                "frozenAt nach Anpfiff = Live-Quoten. Resolver nullt den CLV; "
                "Write-Seite sollte Closing spätestens bei Anpfiff einfrieren.")


# Wie nah am Anpfiff muss das Closing spätestens eingefroren sein, damit es die ECHTE Schlusslinie
# ist? capture-closing.yml läuft alle 15 min in Anpfiff-Bändern → Closing sollte ≤~30 min alt sein.
CLOSING_FRESH_TOL_MIN = 45.0


@integrity_check
def check_closing_capture_fresh(ctx):
    """07.07.2026 (Lucas: „Guard der im Status zeigt, ob wir die Odds nah am Anpfiff holen").
    Gegenstück zu check_closing_prematch: WARNT, wenn ein KÜRZLICH angepfiffenes Spiel (letzte 48h)
    sein Closing zu FRÜH (> CLOSING_FRESH_TOL_MIN vor Anpfiff) eingefroren hat → veraltete Linie,
    CLV misst gegen tote Quote. Zeigt live, ob capture-closing.yml (Nah-am-Anpfiff-Erfassung) greift.
    Nur letzte 48h → aktionierbar, akkumuliert nicht. Ältere Spiele sind historisch (nicht flaggbar)."""
    if ctx.is_liga:
        return None
    cl = _lazy(D.file("wm_closing_lines.json", "liga_closing_lines.json").name)
    if not isinstance(cl, dict) or not cl:
        return None
    # Anpfiff-Map über Gruppen UND koFixtures (nicht nur ctx.fixtures = Gruppen).
    ko_by_key = {}
    for gd in (ctx.wm.get("groups") or {}).values():
        for fx in gd.get("fixtures", []):
            if fx.get("home") and fx.get("away"):
                ko_by_key[f"{fx['home']}-{fx['away']}"] = fx.get("kickoff")
    for kf in (ctx.wm.get("koFixtures") or []):
        if kf.get("home") and kf.get("away"):
            ko_by_key[f"{kf['home']}-{kf['away']}"] = kf.get("kickoff")
    now = datetime.now(timezone.utc)
    fails = []
    for key, snap in cl.items():
        if not isinstance(snap, dict):
            continue
        frozen, ko = snap.get("frozenAt"), ko_by_key.get(key)
        if not frozen or not ko:
            continue
        try:
            fz = datetime.fromisoformat(str(frozen).replace("Z", "+00:00"))
            kk = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        except Exception:
            continue
        if fz.tzinfo is None: fz = fz.replace(tzinfo=timezone.utc)
        if kk.tzinfo is None: kk = kk.replace(tzinfo=timezone.utc)
        # nur kürzlich angepfiffene Spiele (letzte 48h); noch nicht angepfiffte ignorieren
        hrs_since_ko = (now - kk).total_seconds() / 3600.0
        if hrs_since_ko < 0 or hrs_since_ko > 48:
            continue
        early_min = (kk - fz).total_seconds() / 60.0
        if early_min > CLOSING_FRESH_TOL_MIN:
            fails.append(f"{key}: Closing {early_min:.0f}min VOR Anpfiff eingefroren "
                         f"(veraltet — Nah-am-Anpfiff-Capture lief nicht?)")
    return _chk("closing_capture_fresh", "Closing nah am Anpfiff erfasst (≤45min)", "warn", fails,
                "Closing weit vor Anpfiff = tote Linie → CLV unzuverlässig. "
                "capture-closing.yml (alle 15min in Anpfiff-Bändern) + ODDS_API_KEY prüfen.")


@integrity_check
def check_kickoff_present(ctx):
    fails = []
    for _g, fx in ctx.fixtures:
        ko = fx.get("kickoff")
        if not ko:
            fails.append(f"{ctx.mk(fx)}: kein kickoff (Platzhalter {fx.get('date')} {fx.get('time')})")
            continue
        try:
            dt = datetime.fromisoformat(str(ko).replace("Z", "+00:00")).astimezone(timezone.utc)
            d10 = dt.strftime("%Y-%m-%d")
            # Turnier-Fenster nur WM (Juni/Juli); Liga-Saison läuft Aug–Mai → Fenster-Check skippen,
            # aber kickoff-präsent + parsebar bleibt geprüft (25.06.2026, Lucas).
            if not ctx.is_liga and not (TOURNEY_START <= d10 <= TOURNEY_END):
                fails.append(f"{ctx.mk(fx)}: kickoff {d10} außerhalb Turnier-Fenster")
        except Exception:
            fails.append(f"{ctx.mk(fx)}: kickoff '{ko}' nicht parsebar")
    return _chk("kickoff_present", "Kickoff-Zeit real + plausibel", "error", fails,
                "00:00-Platzhalter führten zu falschem Betting-Tab-Listing.")


@integrity_check
def check_time_matches_kickoff(ctx):
    if ctx.is_liga:
        return None   # Liga-Fixtures haben kein separates time-Feld (nutzen kickoff direkt)
    fails = []
    for _g, fx in ctx.fixtures:
        ko = fx.get("kickoff")
        if not ko:
            continue   # fehlender kickoff fängt check_kickoff_present ab
        try:
            v = (datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
                 + timedelta(hours=2)).strftime("%H:%M")   # Wien CEST (WM-Fenster Juni/Juli)
        except Exception:
            continue   # unparsebarer kickoff ebenfalls bei check_kickoff_present
        t = fx.get("time")
        if t != v:
            fails.append(f"{ctx.mk(fx)}: time={t} ≠ Wien(kickoff) {v}")
    return _chk("time_matches_kickoff", "Anpfiff-Zeit (time) == Wien(kickoff)", "warn", fails,
                "fx.time war Seed-Müll (mal Wien, mal Venue-Local, mal 00:00-Platzhalter — "
                "65/72 falsch). Anzeige leitet aus kickoff ab; Drift hier = Quelle "
                "(fetch_wm_venues/fetch_wm_poly_prices) hat time nicht normalisiert.")


_AH_FAV_RE = re.compile(r"AH (?:Heim|Auswärts) −([\d.]+)")


def _ah_fav_line(market):
    """Magnitude einer AH-Favoriten-Linie (−1.5 → 1.5). 0 wenn kein AH-Favorit."""
    m = _AH_FAV_RE.search(market or "")
    return float(m.group(1)) if m else 0.0


@integrity_check
def check_pick_safe_variant(ctx):
    """FIX 14.06.2026: Kein BET-Pick darf eine RISKANTE Variante (AH-Handicap ≤ −1.5
    ODER Quote > 3.0) als Empfehlung haben, ohne dass eine SICHERE Variante angeboten
    wird (saferAltFor/boldAlt). Fing den Bug, den Lucas per Auge fand: Favoriten bekamen
    „AH Heim −1.5 @2.9" als Haupt-Pick statt normalem Sieg, weil die Substitutions-Map
    AH-Linien nicht kannte. Greift universell (auch dynamische Leiter + Auswärts)."""
    picks = ctx.wm.get("picks") or {}
    fails = []
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        for p in plist:
            if p.get("verdict") != "BET":
                continue
            odds = p.get("odds") or 0
            # Steam-Picks leiten die AH-Linie bewusst auf eine sichere Quote ab
            # (build_steam_pick → 1,4-1,95) → die Linien-Höhe ist hier kein Risiko,
            # nur eine Quote > 3,0 zählt. Sonst: AH ≤ −1.5 ODER Quote > 3,0.
            if p.get("source") == "steam":
                risky = odds > 3.0
            else:
                risky = odds > 3.0 or _ah_fav_line(p.get("market")) >= 1.5
            if risky and not p.get("saferAltFor") and not p.get("boldAlt"):
                fails.append(f"{key}: BET {p.get('market')} @{odds} — keine sichere Variante")
    return _chk("pick_safe_variant", "Riskanter BET hat sichere Variante", "warn", fails,
                "AH ≤ −1.5 / Quote > 3.0 als BET-Headline braucht eine sicherere Alternative "
                "(generate_wm_picks: SUBSTITUTION_MAP + _safer_alternatives + Renderer-Demotion).")


# Spiegelt cocobet_config steam.max_trigger_odds (generate_wm_picks: STEAM_MAX_TRIGGER_ODDS).
_STEAM_MAX_TRIGGER_ODDS = 6.0


@integrity_check
def check_steam_longshot_ceiling(ctx):
    """Variante A (20.06.2026, Lucas): Steam-Trigger auf einer Longshot-Quote (> ceiling) ist
    Rauschen, keine Sharp-Money. detect_steam blockt das jetzt am Trigger; dieser Guard ist der
    Regressions-Tripwire — fällt eine NEUE (nicht eingefrorene) Steam-Karte auf, deren Trigger-
    Quote (steamCur/steamOpen) über dem Ceiling liegt, ist der Block kaputt. Fing den BRA-HTI-
    Fall: Haiti 51→22 erzeugte ein „X2 @7.10" gegen den Must-Win-Favoriten.
    AUSGENOMMEN: gepostete Spiele (heute + morgen) — bewusst eingefroren, nicht rückwirksam."""
    picks = ctx.wm.get("picks") or {}
    date_by_key = {}
    for _g, fx in ctx.fixtures:
        pk = f"{_g}-{fx.get('matchday')}-{fx.get('home')}-{fx.get('away')}"
        date_by_key[pk] = fx.get("date")
    tomorrow = (ctx.now.date() + timedelta(days=1)).isoformat()
    fails = []
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        dt = date_by_key.get(key)
        if not dt or dt <= tomorrow:
            continue   # gepostet/eingefroren → bewusst unangerührt (Variante A gilt ab übermorgen)
        for p in plist:
            if p.get("source") != "steam":
                continue
            trig = p.get("steamCur") or p.get("steamOpen")
            if isinstance(trig, (int, float)) and trig > _STEAM_MAX_TRIGGER_ODDS:
                fails.append(f"{key}: Steam {p.get('market')} aus Longshot-Trigger @{trig} "
                             f"(> {_STEAM_MAX_TRIGGER_ODDS})")
    return _chk("steam_longshot_ceiling", "Steam-Trigger respektiert Longshot-Ceiling", "warn",
                fails, "Neue Steam-Karte aus einer Quote > Ceiling — detect_steam max_trigger_odds "
                "greift nicht (steam_engine / cocobet_config steam.max_trigger_odds).")


# Spiegel von generate_wm_picks: MODEL_MARGIN (0.96) + O/U-Markt → Pinnacle-Linien-Paar.
_MODEL_MARGIN = 0.96
_OU_PINN_PAIR = {
    "Über 1.5 Tore": ("o15", "u15", "o"), "Unter 1.5 Tore": ("o15", "u15", "u"),
    "Über 2.5 Tore": ("o25", "u25", "o"), "Unter 2.5 Tore": ("o25", "u25", "u"),
    "Über 3.5 Tore": ("o35", "u35", "o"), "Unter 3.5 Tore": ("o35", "u35", "u"),
    "Beide Teams treffen — Ja":   ("bttsY", "bttsN", "o"),
    "Beide Teams treffen — Nein": ("bttsY", "bttsN", "u"),
}


@integrity_check
def check_ou_pinnacle_anchored(ctx):
    """FIX 14.06.2026: O/U + BTTS sind seit heute an Pinnacle geankert (wie 1X2 seit
    13.06.) — Baseline P(Über/Unter/BTTS) = de-viggte Pinnacle-Linie, nicht mehr das
    Poisson-Tor-Modell. Sonst schlug das Modell Pinnacle und erzeugte Phantom-Edges
    (DEU-CUW Unter 3.5: Poisson 48 % statt Pinnacle-fair 39 %).
    Tripwire gegen Regression: für JEDES NEU gebaute O/U/BTTS-Pick (Spiel ab übermorgen,
    Pinnacle-Linie vorhanden) muss modelOdds ≈ prob_to_odds(de-vig Pinnacle) sein. Liegt
    es stattdessen beim Poisson-Wert → der Anker wurde versehentlich entfernt.
    AUSGENOMMEN: gepostete Spiele (heute + morgen). Die werden bewusst eingefroren und
    NICHT umgeankert, damit veröffentlichte Picks trackbar bleiben (Lucas 14.06.)."""
    picks = ctx.wm.get("picks") or {}
    # Datum + Pinnacle-Odds je pick_key auflösen.
    date_by_key, odds_by_key = {}, {}
    for _g, fx in ctx.fixtures:
        pk = f"{_g}-{fx.get('matchday')}-{fx.get('home')}-{fx.get('away')}"
        date_by_key[pk] = fx.get("date")
        odds_by_key[pk] = ctx.odds.get(f"{fx.get('home')}-{fx.get('away')}") or {}
    tomorrow = (ctx.now.date() + timedelta(days=1)).isoformat()
    fails = []
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        dt = date_by_key.get(key)
        if not dt or dt <= tomorrow:
            continue   # gepostet/eingefroren → bewusst unangerührt
        osnap = odds_by_key.get(key) or {}
        for p in plist:
            if p.get("verdict") not in ("BET", "ABWÄGEN"):
                continue
            pair = _OU_PINN_PAIR.get(p.get("market"))
            if not pair:
                continue
            ov, un = osnap.get(pair[0]), osnap.get(pair[1])
            if not ov or not un or ov <= 1.0 or un <= 1.0:
                continue   # keine Pinnacle-Linie → Poisson-Fallback erlaubt, nicht prüfbar
            io, iu = 1.0 / ov, 1.0 / un
            fair = (io if pair[2] == "o" else iu) / (io + iu)
            expected = round((1.0 / fair) * _MODEL_MARGIN, 3)
            mo = p.get("modelOdds")
            if not isinstance(mo, (int, float)) or abs(mo - expected) > 0.20:
                fails.append(f"{key}: {p.get('market')} modelOdds={mo} ≠ Pinnacle-Anker "
                             f"{expected} (Poisson-Regression?)")
    return _chk("ou_pinnacle_anchored", "O/U + BTTS an Pinnacle geankert", "warn", fails,
                "generate_wm_picks: _devig2-Block (Z.~930). Baseline = de-viggte Pinnacle, "
                "Poisson nur Fallback. Gepostete Spiele (≤morgen) ausgenommen.")


@integrity_check
def check_ou_anchor_source(ctx):
    """FIX 15.06.2026 (Lucas): Der Tor-Anker (o25/bttsY…) BEVORZUGT Pinnacle, fällt
    aber still auf einen Soft-Book zurück, wenn Pinnacle die Linie nicht listet —
    der De-Vig würde diese Soft-Linie dann als „Pinnacle-fair" behandeln. fetch_wm_odds
    taggt jetzt die Quelle je Markt (o15_src/o25_src/o35_src/btts_src). Dieser Guard
    macht den stillen Fallback SICHTBAR: warnt für jeden O/U/BTTS-Pick (BET/ABWÄGEN),
    dessen Anker NICHT von Pinnacle stammt. Severity warn → 🛡️-Panel, kein Block."""
    picks = ctx.wm.get("picks") or {}
    odds_by_key = {}
    for _g, fx in ctx.fixtures:
        pk = f"{_g}-{fx.get('matchday')}-{fx.get('home')}-{fx.get('away')}"
        odds_by_key[pk] = ctx.odds.get(f"{fx.get('home')}-{fx.get('away')}") or {}
    fails = []
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        osnap = odds_by_key.get(key) or {}
        for p in plist:
            if p.get("verdict") not in ("BET", "ABWÄGEN"):
                continue
            pair = _OU_PINN_PAIR.get(p.get("market"))
            if not pair:
                continue
            base = pair[0]
            src_key = ("btts" if base.startswith("btts") else base) + "_src"
            src = osnap.get(src_key)
            if src is None:
                continue   # kein Tag (alte Daten / keine Linie) → nicht prüfbar
            if src != "pinnacle":
                fails.append(f"{key}: {p.get('market')} Tor-Anker von '{src}' statt Pinnacle "
                             f"(de-viggter Soft-Preis als Sharp-Fair behandelt)")
    return _chk("ou_anchor_source", "Tor-Anker stammt von Pinnacle", "warn", fails,
                "fetch_wm_odds: _pick_total_line/_pick_bk Fallback auf Soft-Book wenn "
                "Pinnacle die Linie nicht listet. Soft-Anker = unzuverlässige Fair-Schätzung.")


def _real_match_keys(ctx):
    # 04.07.2026 (Lucas: „24 Phantom-Odds-Keys"): ctx.fixtures kennt nur groups. KO-Spiele
    # liegen in koFixtures → ihre Odds-Keys (BRA-JPN …) galten fälschlich als leere Spiegel-
    # Einträge. KO-Match-Keys mitzählen → alle 4 Guards, die _real_match_keys nutzen, sehen
    # KO-Spiele jetzt als echte Fixtures.
    keys = {ctx.mk(fx) for _g, fx in ctx.fixtures}
    for kf in (ctx.wm.get("koFixtures") or []):
        if kf.get("home") and kf.get("away"):
            keys.add(ctx.mk(kf))
    return keys


# Wie nah muss ein Anpfiff sein, damit „Pinnacle hat noch gar nicht eroeffnet" als Fehler gilt?
# Innerhalb dieser Frist ist es einer: ein Spiel uebermorgen ohne Pinnacle-Linie ist nicht
# handelbar, und das gehoert gemeldet. Davor ist es nur der normale Lauf der Dinge.
NICHT_EROEFFNET_FRIST_D = 3


def _pinnacle_nie_eroeffnet(o) -> bool:
    """True, wenn zu diesem Spiel NOCH GAR KEINE Pinnacle-Zahl geschrieben wurde.

    Unterscheidet die zwei Faelle, die der Guard bisher in einen Topf warf:
      * kein hw/dr/aw UND kein bookmaker  → der Fetcher hat nie etwas gefunden (noch nicht eroeffnet)
      * ein Teil davon da                 → halber Eintrag, das ist ein echter Fehler
    Felder anderer Quellen (poly_*, bf_*, ah*) zaehlen bewusst NICHT als Pinnacle-Eroeffnung —
    Betfair und die AH-Leiter listen frueher als Pinnacle.
    """
    if not isinstance(o, dict):
        return True
    if o.get("bookmaker"):
        return False
    return not any(isinstance(o.get(x), (int, float)) for x in ("hw", "dr", "aw"))


def _nie_eroeffnet_keys(ctx, tage: int = NICHT_EROEFFNET_FRIST_D):
    """Keys, die man nicht bemaengeln kann: weiter als `tage` weg UND von Pinnacle nie eroeffnet.

    29.08.2026 (Lucas, Status-Tab): der 1X2- und der Public-Guard standen dauerhaft auf Gelb —
    11 Liga- und 13 MLS-„Fehler", allesamt Spiele 5,5 bis 7,7 Tage in der Zukunft, zu denen
    Polymarket laengst listet und Pinnacle noch nicht. Der bestehende 7-Tage-Deckel griff dafuer
    nicht: gemessen reichen bepreiste Anpfiffe bis 9,5 Tage, unbepreiste beginnen schon bei 5,5 —
    die Zonen ueberlappen, ein reiner Tages-Schwellenwert kann sie also gar nicht trennen.
    Das Kriterium ist nicht die Entfernung, sondern ob ueberhaupt schon jemand bepreist hat.
    Dauer-Gelb ist nicht harmlos: es erzieht dazu, die Statusseite zu ueberblaettern — und genau
    das hat am 28.08. einen halben Tag gekostet.
    """
    jetzt = ctx.now if getattr(ctx, "now", None) else datetime.now(timezone.utc)
    grenze = jetzt + timedelta(days=tage)
    out = set()
    fx_by_key = {}
    for _g, fx in ctx.fixtures:
        fx_by_key[f"{fx.get('home')}-{fx.get('away')}"] = fx
    for mk, o in (ctx.odds or {}).items():
        if not _pinnacle_nie_eroeffnet(o):
            continue
        fx = fx_by_key.get(mk)
        ko = (fx or {}).get("kickoff")
        if not ko:
            continue
        try:
            t = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        except ValueError:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        if t > grenze:
            out.add(mk)
    return out


def _far_future_keys(ctx, tage: int = 7):
    """Fixtures, deren Anpfiff weiter als `tage` entfernt ist.

    14.07.2026: Buchmacher eröffnen ihre Linien erst rund eine Woche vorher — Polymarket listet
    früher. Dadurch entstehen Odds-Einträge, die (noch) nur poly_*-Felder haben. Der 1X2- und der
    Public-Guard meldeten dafür 15 „Fehler" (alle MLS-Spiele am 25.07.), obwohl schlicht noch
    niemand bepreist hat. Solches Dauer-Gelb ist schädlich: es stumpft gegen echte Warnungen ab.
    """
    out = set()
    for _g, fx in ctx.fixtures:
        ko = fx.get("kickoff")
        if not ko:
            continue
        try:
            t = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        except ValueError:
            continue
        if (t - ctx.now).days > tage:
            out.add(f"{fx.get('home')}-{fx.get('away')}")
    return out


def _angepfiffen_keys(ctx):
    """29.08.2026 (Lucas-Checkup, Dauergelb Teil 2): Spiele, deren Anpfiff DURCH ist.

    `_finished_keys` verlangt result.status in FT/AET/... — das schreibt der Resolver aber erst
    nach Abpfiff. Dazwischen liegt die ganze Spieldauer, und in dieser Zeit hat der Buchmacher
    seine Vor-Spiel-Quoten laengst abgeraeumt: hw/dr/aw sind None, waehrend die Poly-Felder noch
    dastehen. Genau das flaggte der 1X2-Guard — gemessen an Liverpool-Nottm Forest (Anpfiff
    11:30, geprueft 14:30): „1X2 unvollstaendig hw=None dr=None aw=None". Es ist nichts kaputt,
    das Spiel laeuft. Ein Guard, der jeden Spieltagnachmittag gelb wird, ist genau die Sorte
    Dauergelb, die man sich abgewoehnt anzuschauen."""
    out = set()
    for _g, fx in ctx.fixtures:
        ko = fx.get("kickoff")
        if not ko:
            continue
        try:
            t = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        except ValueError:
            continue
        if t <= ctx.now:
            out.add(f"{fx.get('home')}-{fx.get('away')}")
    return out


@integrity_check
def check_odds_sane(ctx):
    real = _real_match_keys(ctx)
    finished = _finished_keys(ctx) | _angepfiffen_keys(ctx)
    zu_frueh = _far_future_keys(ctx) | _nie_eroeffnet_keys(ctx)
    fails = []
    for mk, o in ctx.odds.items():
        if mk not in real or mk in finished or mk in zu_frueh:
            continue   # Phantom-Keys separat; beendete = historisch; weit weg = noch nicht bepreist
        hw, dr, aw = o.get("hw"), o.get("dr"), o.get("aw")
        if not all(isinstance(x, (int, float)) and x > 1.0 for x in (hw, dr, aw)):
            fails.append(f"{mk}: 1X2 unvollständig hw={hw} dr={dr} aw={aw}")
            continue
        margin = 1/hw + 1/dr + 1/aw
        if margin < 1.0 or margin > 1.30:
            fails.append(f"{mk}: Margin {margin:.3f} unplausibel")
    return _chk("odds_sane", "Pinnacle-1X2 vollständig + plausibel", "warn", fails,
                "Quelle für Modell-Baseline + Edge.")


@integrity_check
def check_opening_plausible(ctx):
    """08.07.2026 (Lucas: Liga-Sharp-Radar zeigte Fake-Drops bis -84pp). odds_open MUSS ein echter
    1X2-Markt sein — Platzhalter-Eröffnungen (dr=1.01, aw=1.06, Overround >1.25) beim Markt-Opening
    erzeugen erfundene Drifts im Radar. fetch_liga_odds friert das 1X2-Opening jetzt kohärent ein +
    heilt Müll aus der History; dieser Guard macht Reste/Regression im Status sichtbar."""
    fails = []
    for mk, o in ctx.odds.items():
        oo = o.get("odds_open") or {}
        hw, dr, aw = oo.get("hw"), oo.get("dr"), oo.get("aw")
        if not (hw and dr and aw):
            continue   # kein 1X2-Opening gesetzt → kein Fake-Drift, nichts zu flaggen
        orr = 1.0 / hw + 1.0 / dr + 1.0 / aw
        if hw < 1.05 or aw < 1.05 or dr < 1.5 or orr > 1.25:
            fails.append(f"{mk}: Opening unplausibel hw={hw} dr={dr} aw={aw} (Overround {orr:.2f}) "
                         f"→ erfundener Drift im Sharp Radar")
    return _chk("opening_plausible", "Opening-Odds = echter 1X2-Markt (kein Platzhalter)", "warn", fails,
                "fetch_liga_odds friert 1X2-Opening kohärent + heilt aus History (erster plausibler Snap).")


@integrity_check
def check_closing_capture_alive(ctx):
    """17.07.2026 — 🔴 CLV WAR FÜR LIGA + MLS WOCHENLANG TOT, ohne dass es jemand merkte.

    Ursache: fetch_liga_odds übergab `hours_to_ko=None` an compute_closing → die Funktion fiel durch
    alle Zweige und gab None zurück → `odds_closing` wurde NIE gesetzt → keine closing_lines →
    **kein CLV**. Die WM nutzt einen eigenen Fetcher und war nie betroffen (100/104 Odds mit
    Closing), deshalb sah der Status immer gesund aus.

    Die Lehre: Alle bisherigen Guards prüften, ob DATEIEN richtig verdrahtet sind — keiner, ob am
    Ende auch DATEN ankommen. Dieser Check fragt genau das: Gibt es bepreiste, angepfiffene Spiele,
    aber KEIN einziges Closing? Dann ist die CLV-Kette tot, egal wie sauber die Pfade aussehen.
    """
    # ⚠️ NICHT über ctx.odds gehen: gespielte Spiele werden dort weggeprunt. Genau deshalb gibt es
    # die persistente {ds}_closing_lines.json — sie überlebt das Pruning und IST die CLV-Quelle.
    # (Mein erster Versuch fragte ctx.odds ab und fand deshalb nichts — derselbe Fehler, den dieser
    #  Guard aufdecken soll.)
    from datetime import datetime as _d, timedelta as _td

    cl = _lazy(D.file("wm_closing_lines.json", "liga_closing_lines.json").name) or {}

    # Wie viele Spiele wurden zuletzt gespielt? (Nur die zählen — vorher kann nichts erfasst sein.)
    grenze = (ctx.now - _td(days=14)).date().isoformat()
    kuerzlich = 0
    for _g, fx in ctx.fixtures:
        if (fx.get("result") or {}).get("status") in ("FT", "AET", "PEN") \
                and str(fx.get("date", "")) >= grenze:
            kuerzlich += 1

    fails = []
    if kuerzlich >= 3 and not cl:
        fails.append(
            f"{kuerzlich} Spiele in 14 Tagen gespielt, aber die Closing-Datei ist LEER → "
            f"CLV-Kette tot. Prüfen: bekommt compute_closing ein hours_to_ko? Läuft capture-closing-*?")
    elif kuerzlich >= 5 and len(cl) < kuerzlich * 0.4:
        fails.append(f"nur {len(cl)} Closing-Einträge bei {kuerzlich} gespielten Spielen — "
                     f"Capture greift nur sporadisch, CLV bleibt lückenhaft")
    return _chk("closing_capture_alive", "Closing-Erfassung liefert Daten (CLV lebt)",
                "warn", fails,
                "fetch_liga_odds reicht kickoff → compute_closing; capture-closing-* läuft alle 15min "
                "in den Anpfiff-Bändern.")


@integrity_check
def check_wallet_ledger_growing(ctx):
    """18.07.2026 — Der Wallet-Ledger sammelt Längsschnittdaten, die nicht nachholbar sind.

    Die Polymarket-API liefert nur das AKTUELLE Fenster (Top-Holder + jüngste große Trades).
    Was `build_poly_wallet_ledger.py` nicht wegschreibt, ist beim nächsten Lauf weg — und der
    spätere Wallet-Track-Record hat diese Beobachtung dann für immer nicht.

    Genau deshalb dieser Guard: der Ledger-Step läuft mit `continue-on-error: true` (er darf den
    Datenlauf nie kippen), das heißt ein Fehler ist STILL. Und die Datei existiert dann trotzdem,
    nur eingefroren — die Klasse Bug, die uns bei CLV wochenlang unentdeckt blieb
    (siehe check_closing_capture_alive). Wir fragen deshalb nicht „gibt es die Datei", sondern
    „steht da neuer Bestand drin, obwohl es frischen Input gab".

    25.08.2026 (Audit-Befund 07): der Liga-Sonderfall ist WEG. „Liga hat bewusst kein Polymarket"
    stimmte bis zum 19.08.; seitdem tradet Liga real dort (manage-liga-poly.yml, echte Balance).
    Der abgeschaltete Check war der EINZIGE Poly-Guard für Liga — deshalb meldete liga_status.json
    54 grüne Haken, ohne je hinzusehen, während die Analyseschicht gar nicht lief.
    Ohne frischen Snapshot bleibt der Check weiterhin still (der Zweig darunter greift), es gibt
    also kein Dauer-Gelb in einer Spielpause.
    """
    from datetime import datetime as _d, timedelta as _td

    snap = _lazy(D.file("wm_poly_wallets.json", "liga_poly_wallets.json").name) or {}
    hat_input = bool(snap.get("topPositionsAll") or snap.get("bigTradesAll"))
    if not hat_input:
        # Kein frischer Input (Runner aus, Spielpause) → nichts zu sammeln, kein Alarm.
        return _chk("wallet_ledger_growing", "Wallet-Ledger wächst", "warn", [],
                    "Kein frischer Wallet-Snapshot — nichts zu sammeln.")

    led = _lazy(D.file("wm_poly_wallet_ledger.json", "liga_poly_wallet_ledger.json").name) or {}
    fails = []
    if not led:
        fails.append("Wallet-Snapshot hat Daten, aber der Ledger fehlt komplett → "
                     "build_poly_wallet_ledger.py läuft nicht (oder committet nicht). "
                     "Jeder Lauf ohne Ledger ist unwiederbringlich verlorene Historie.")
    else:
        try:
            alter_h = (ctx.now - _d.fromisoformat(
                str(led.get("updatedAt")).replace("Z", "+00:00"))).total_seconds() / 3600
        except Exception:
            alter_h = None
        # Der dichteste Takt ist 2h; 24h ohne Fortschreibung sind also ~12 verpasste Läufe.
        if alter_h is not None and alter_h > 24:
            fails.append(f"Ledger seit {alter_h:.0f}h nicht fortgeschrieben, obwohl frische "
                         f"Wallet-Daten vorliegen → Sammlung steht still")
        if not (led.get("trades") or led.get("positions")):
            fails.append("Ledger existiert, ist aber leer — Snapshot-Format geändert? "
                         "(erwartet: bigTradesAll / topPositionsAll)")

    return _chk("wallet_ledger_growing", "Wallet-Ledger wächst (Track-Record-Basis)",
                "warn", fails,
                "build_poly_wallet_ledger.py läuft direkt nach jedem fetch_wm_poly_smartmoney.py.")


@integrity_check
def check_no_ghost_picks(ctx):
    """14.07.2026 — Picks, die aus einer PLATZHALTER-Quote geboren wurden.

    Die beiden ersten MLS-Picks trugen Texte wie „Pinnacle 1.17→2.27 · Sharp-Money-Drop +25pp" —
    einen Move, den es nie gab. Ursache: die Quellen-API eröffnete mit 1.17/1.01/1.17 (Overround
    270 %). Der Plausibilitäts-Guard in steam_engine verhindert die Geburt neuer Geister; dieser
    Check hier macht sichtbar, wenn trotzdem einer in den Daten steht (z.B. Altbestand, den
    _carry_nobet noch mitschleppt).

    Ein echter Sharp-Move liegt bei 2–8pp. Alles jenseits von 20pp ist kein Marktereignis.
    Aufgelöste Picks bleiben ausgenommen — was gelaufen ist, bleibt in der Bilanz.
    """
    from generate_wm_picks import _is_ghost_pick    # EINE Quelle für die Regel

    fails = []
    for key, plist in (ctx.wm.get("picks") or {}).items():
        fx_key = "-".join(key.split("-")[-2:])       # Pick-Key → Fixture-Key
        snap = ctx.odds.get(fx_key) or {}
        for pk in (plist if isinstance(plist, list) else [plist]):
            if not isinstance(pk, dict):
                continue
            if _is_ghost_pick(pk, snap):
                fails.append(f"{key} {pk.get('market')}: Eröffnung {pk.get('steamOpen')} → "
                             f"{pk.get('steamCur')} stammt aus einer Platzhalter-Quote "
                             f"(echte Eröffnung: {(snap.get('odds_open') or {}).get('hw')}/"
                             f"{(snap.get('odds_open') or {}).get('dr')}/"
                             f"{(snap.get('odds_open') or {}).get('aw')})")
    return _chk("no_ghost_picks", "Keine Picks aus Platzhalter-Quoten", "warn", fails,
                "steam_engine blockt implausible Openings; _carry_nobet sortiert Altbestand aus.")


@integrity_check
def check_injuries_plausible(ctx):
    """13.07.2026 (Lucas: „MLS startet Freitag — haben wir die Saisondaten am Schirm?").

    BEFUND: Die MLS-Verletzungsdaten listeten **116 Ausfälle für einen 30-Mann-Kader** — mehr
    „Verletzte" als Spieler. /injuries?league&season liefert einen Eintrag JE FIXTURE, über eine
    Saison entsteht daraus ein ARCHIV aller je gefehlten Spieler statt des aktuellen Stands.
    Jüngster Eintrag: Mai. Wir schrieben Juli.

    Dass das injury-Signal trotzdem schwieg, war Glück — kein Schutz. Hätte es gefeuert, hätten wir
    jedem Team dauerhaft eine halbe Mannschaft „verletzt" gerechnet und Favoriten grundlos abgewertet.

    Dieser Guard macht zwei stille Fehler sichtbar:
      · MEHR Ausfälle als Kaderspieler → unmöglich, also Datenmüll
      · Ausfalldaten VERALTET (jüngster Eintrag älter als 45 Tage) → Fetcher liefert nichts Neues
    """
    from datetime import datetime as _dt, timezone as _tz

    inj = (ctx.wm.get("injuries") or {})
    squads = (ctx.wm.get("squads") or {})
    if not inj:
        return _chk("injuries_plausible", "Ausfall-Liste = aktueller Stand (kein Archiv)",
                    "warn", [], "keine Verletzungsdaten (früh in der Saison normal)")

    fails = []
    neuestes = None
    for tid, entry in inj.items():
        players = (entry or {}).get("players") or []
        n = len(players)

        # Kadergröße ermitteln (Struktur variiert je Datensatz → defensiv).
        sq = squads.get(tid)
        kader = 0
        if isinstance(sq, dict):
            kader = len(sq.get("players") or [])
        elif isinstance(sq, list):
            kader = len(sq)

        if kader and n > kader:
            fails.append(f"{tid}: {n} Ausfälle bei {kader} Kaderspielern → Archiv statt "
                         f"Ausfallstand (/injuries liefert je Fixture einen Eintrag)")
        elif n > 25:   # ohne Kaderdaten: 25+ Ausfälle sind nie ein echter Ausfallstand
            fails.append(f"{tid}: {n} Ausfälle — unplausibel hoch")

        for p in players:
            d = (p.get("fixture") or "")[:10]
            if d and (neuestes is None or d > neuestes):
                neuestes = d

    if neuestes:
        try:
            alter = (_dt.now(_tz.utc).date() - _dt.fromisoformat(neuestes).date()).days
            if alter > 45:
                fails.append(f"jüngster Ausfall-Eintrag ist {alter} Tage alt ({neuestes}) → "
                             f"Fetcher liefert keine aktuellen Daten mehr")
        except ValueError:
            pass

    return _chk("injuries_plausible", "Ausfall-Liste = aktueller Stand (kein Archiv)",
                "warn", fails,
                "fetch_wm_injuries dedupliziert je Spieler (jüngster gewinnt) + verwirft Einträge "
                f"älter als INJURY_RECENT_DAYS.")


@integrity_check
def check_history_snaps_plausible(ctx):
    """13.07.2026 (Lucas: „schau dir den Sharp Radar nochmal an").

    BLINDER FLECK des Guards oben: der prüft nur `odds_open` — und das war bei MLS sauber geheilt
    (Marge 1.09), also meldete er GRÜN. Sharp Radar und detect_wm_sharp_moves lesen aber gar nicht
    odds_open, sondern die **History** (snaps[0] als Opening, prev für Snap-zu-Snap). Und dort lagen
    die Platzhalter weiter drin: hw=1.04 / dr=1.01 / aw=1.04 → Overround **291 %**.

    Folge: Geister-Mover im Radar und **80,8pp „🔥 STEAM"-Alerts, die bereits per Telegram
    rausgingen**. Ein Guard, der die falsche Datei prüft, ist schlimmer als keiner — er beruhigt.

    Dieser Check schaut dorthin, wo die Verbraucher wirklich lesen. Konsumenten filtern jetzt
    (odds_plausibility.clean_snaps / _sharpCleanSnaps), aber verseuchte History bleibt ein
    Datenfehler der Quelle → sichtbar machen, nicht verstecken.
    """
    import odds_plausibility as OP
    hist = ctx.history if isinstance(getattr(ctx, "history", None), dict) else None
    if not hist:
        return _chk("history_snaps_plausible", "History-Snapshots = echte Märkte (kein Platzhalter)",
                    "warn", [], "keine Odds-History im Kontext")
    fails = []
    for mk, snaps in hist.items():
        if mk == "_meta" or not isinstance(snaps, list):
            continue
        bad = [s for s in snaps
               if isinstance(s, dict) and s.get("hw") and s.get("dr") and s.get("aw")
               and not OP.plausible_1x2(s["hw"], s["dr"], s["aw"])]
        if bad:
            b = bad[0]
            orr = 1.0 / b["hw"] + 1.0 / b["dr"] + 1.0 / b["aw"]
            fails.append(f"{mk}: {len(bad)} Platzhalter-Snap(s), z.B. {b['hw']}/{b['dr']}/{b['aw']} "
                         f"(Overround {orr:.2f}) → Geister-Move im Radar + Fake-Steam-Alert")
    return _chk("history_snaps_plausible", "History-Snapshots = echte Märkte (kein Platzhalter)",
                "warn", fails,
                "Verbraucher filtern via odds_plausibility.clean_snaps; verseuchte Snaps bleiben "
                "trotzdem ein Quellen-Fehler und werden hier sichtbar.")


@integrity_check
def check_liga_leagues_populated(ctx):
    """NEU 26.06.2026 (Lucas): jede der 5 Top-Ligen muss Teams + Fixtures haben. La Liga/Bundesliga
    veröffentlichen ihren Spielplan oft später als EPL/Serie A/Ligue 1 → bis dahin liefert
    API-Football leer (kein Bug bei uns, upstream-Timing). Dieser Guard macht eine leere Liga im
    Status SICHTBAR — bleibt sie kurz vor Saisonstart leer, ist es ein echtes Problem zum Nachgehen."""
    if not ctx.is_liga:
        return None
    fails = []
    for gkey, gd in (ctx.wm.get("groups") or {}).items():
        n_tm = len(gd.get("teams") or [])
        n_fx = len(gd.get("fixtures") or [])
        if n_fx == 0 or n_tm == 0:
            fails.append(f"{gkey}: {n_tm} Teams / {n_fx} Fixtures — Spielplan noch nicht veröffentlicht?")
    return _chk("liga_leagues_populated", "Alle Liga-Gruppen haben Teams + Fixtures", "warn", fails,
                "Leer = API-Football hat den Spielplan noch nicht (La Liga/Bundesliga spät). "
                "Kurz vor Saisonstart = echtes Problem.")


@integrity_check
def check_ko_odds_present(ctx):
    """NEU 27.06.2026 (Bug „R32-Cards ohne Pick"): bothResolved + ungespielte KO-Paarungen mit
    Odds-History dürfen ihre top-level Odds NICHT verlieren. fetch_wm_poly_prices löschte KO-Keys
    als „Phantom", weil real_keys nur Gruppen-Fixtures enthielt (nicht koFixtures) → KO-Odds bei
    jedem Lauf weg → keine Steam-Picks. Guard fängt die Regression: History da, top-level Odds fehlen."""
    if ctx.is_liga:
        return None
    fails = []
    for kf in (ctx.wm.get("koFixtures") or []):
        if not kf.get("bothResolved"):
            continue
        h, a = kf.get("home"), kf.get("away")
        if not (h and a):
            continue
        if str((kf.get("result") or {}).get("status") or "").upper() in {"FT", "AET", "PEN", "AWD", "WO"}:
            continue
        key = f"{h}-{a}"
        if len(ctx.history.get(key) or []) >= 2 and key not in ctx.odds:
            fails.append(f"{key}: Odds-History vorhanden, aber keine top-level Odds — als Phantom geprunt?")
    return _chk("ko_odds_present", "KO-Odds bleiben erhalten (nicht als Phantom geprunt)", "warn", fails,
                "fetch_wm_poly_prices.real_keys muss bothResolved koFixtures enthalten.")


@integrity_check
def check_ko_apif_coverage(ctx):
    """06.07.2026 (Lucas: „nicht wieder KO-Bugs einzeln finden"). Safety-Net gegen die WIEDERKEHRENDE
    KO-Datenpfad-Bug-Klasse bei SEPARAT gefetchten Daten: fetch_wm_apifootball_predictions iterierte
    nur `groups` → apif-Prognose fehlte für anstehende Achtel-/Viertelfinals (Signal apif_predictions
    + KO-Previews tot). Gefixt via koFixtures. Dieser Guard fängt eine Regression: WARNT, wenn ein
    anstehendes bothResolved-KO-Spiel (Anpfiff < 72h) keine apif-Prognose hat. So muss die Lücke nie
    wieder von Hand gesucht werden. Siehe feedback_ko_datapath."""
    if ctx.is_liga:
        return None   # Liga/MLS haben keine koFixtures → No-Op
    import json as _j
    try:
        apif = _j.loads((_BASE / D.file("wm_apif_predictions.json", "liga_apif_predictions.json").name).read_text(encoding="utf-8"))
    except Exception:
        return None   # File fehlt → anderer Guard/Job zuständig, kein False-Positive
    now = datetime.now(timezone.utc)
    fails = []
    for kf in (ctx.wm.get("koFixtures") or []):
        h, a = kf.get("home"), kf.get("away")
        if not (kf.get("bothResolved") and h and a):
            continue
        if str((kf.get("result") or {}).get("status") or "").upper() in {"FT", "AET", "PEN", "AWD", "WO"}:
            continue
        try:
            dt = datetime.fromisoformat(str(kf.get("kickoff")).replace("Z", "+00:00"))
        except Exception:
            continue
        hrs = (dt - now).total_seconds() / 3600.0
        if hrs < 0 or hrs > 72:
            continue   # nur anstehende < 3 Tage — weiter entfernte holt apif erst später (kein False-Positive)
        if f"{h}-{a}" not in apif:
            fails.append(f"{h}-{a}: anstehendes KO-Spiel ({hrs:.0f}h) ohne apif-Prognose")
    return _chk("ko_apif_coverage", "Anstehende KO-Spiele haben apif-Prognose", "warn", fails,
                "fetch_wm_apifootball_predictions._load_wm_fixtures muss koFixtures iterieren (KO-Datenpfad).")


@integrity_check
def check_ko_settlement_ninety_min(ctx):
    """NEU 03.07.2026 (Lucas: ARG-CPV 1:1 nach 90 → Verlängerung 3:2 → „Unter 2.5/3.5" fälschlich
    verloren; BEL-SEN hatte denselben Bug latent, nur ohne Tor-Pick). UNSERE Märkte settlen auf 90
    MINUTEN, NICHT inkl. Verlängerung — Verlängerung/Elfmeter zählen nur für den Aufstieg. `result.
    aggregateScore` hält den ET-inkl. Endstand (nur gesetzt, wenn Verlängerungstore fielen). Invariante:
    Settlement-Total (home_score+away_score = 90 Min) MUSS KLEINER sein als das aggregate-Total (die
    Verlängerung fügt nur Tore hinzu). Ist es das nicht, settlet der Resolver auf den falschen (ET-inkl.)
    Stand → Regression des _ninety_min_score-Fix. Stiller Geld-Bug → Guard."""
    if ctx.is_liga:
        return None
    fails = []
    for kf in (ctx.wm.get("koFixtures") or []):
        r = kf.get("result") or {}
        status = str(r.get("status") or "").upper()
        agg = r.get("aggregateScore")
        if status not in ("AET", "PEN") or not isinstance(agg, dict):
            continue
        h, a   = r.get("home_score"), r.get("away_score")
        ah, aa = agg.get("home"), agg.get("away")
        if None in (h, a, ah, aa):
            continue
        st, at = h + a, ah + aa
        # Settlement (90 Min) kann NIE mehr Tore haben als der Gesamtstand (Verlängerung fügt nur hinzu).
        if st > at:
            fails.append(f"{kf.get('home')}-{kf.get('away')}: Settlement {h}:{a} ({st}) > Gesamt {ah}:{aa} ({at})")
        # AET = in der Verlängerung entschieden → dort fielen Tore → 90-Min-Total MUSS strikt kleiner sein.
        # Gleichheit = die Verlängerungstore sind fälschlich im Settlement gelandet (der ARG-CPV-Bug).
        elif status == "AET" and st >= at:
            fails.append(f"{kf.get('home')}-{kf.get('away')}: AET, aber Settlement {h}:{a} ({st}) "
                         f"nicht < Gesamt {ah}:{aa} ({at}) — Verlängerungstore im 90-Min-Stand?")
    return _chk("ko_settlement_ninety_min",
                "KO-Settlement auf 90-Min-Stand (nicht inkl. Verlängerung)", "error", fails,
                "fetch_wm_match_results._ninety_min_score muss score.fulltime nutzen (score.fulltime).")


@integrity_check
def check_liga_odds_round_sane(ctx):
    """26.06.2026 (Bug „Spieltag 1 dann 20"): Odds dürfen nicht auf einem Fixture landen, das
    Monate entfernt ist — ein Hinrunden-Event matchte sonst das Rückspiel (gleiche Teams, ferne
    Runde). Der eigentliche Fix sitzt in fetch_liga_odds.pick_event_for_fixture (±4-Tage-
    Datumsnähe); dieser Guard ist der Backstop gegen eine Regression.

    27.07.2026 — von RUNDEN- auf DATUMS-basiert (Lucas, Status „Spieltag-Mismatch"). Der alte
    Check maß den Abstand in Spieltag-NUMMERN (md − Front > 4). Das gilt nur für kalender-synchrone
    Ligen (Bundesliga & Co.: Runde N läuft überall dieselbe Woche). Die MLS nummeriert Runden NICHT
    synchron — ein Aug-1-Spiel ist „Runde 18", ein Aug-15-Spiel „Runde 19", ein verlegtes
    Frühjahrsspiel trägt „Runde 3", obwohl es zeitlich nah liegt. Folge: 32 korrekt (per Datum)
    zugeordnete MLS-Odds wurden gelb, obwohl nichts falsch war. Das Signal für einen Fehlmatch ist
    der KALENDER-Abstand, nicht die Rundennummer — der trennt legitime Vorab-Preisung (~2-3 Wochen)
    sauber vom Rückspiel-Fehlmatch (Monate)."""
    if not ctx.is_liga:
        return None
    from datetime import date

    def _fx_date(fx):
        raw = (fx.get("date") or str(fx.get("kickoff") or ""))[:10]
        try:
            return date.fromisoformat(raw)
        except (ValueError, TypeError):
            return None

    dt_by_key, played = {}, set()
    for _g, fx in ctx.fixtures:
        k = ctx.mk(fx)
        dt_by_key[k] = _fx_date(fx)
        if (fx.get("result") or {}).get("status") in ("FT", "AET", "PEN"):
            played.add(k)
    # Nur Keys mit ECHTEN 1X2-Odds datums-prüfen — leere poly-only-Shells (kein hw) sind keine
    # „Odds auf Runde X" und dürfen weder den Front verschieben noch geflaggt werden.
    priced = [k for k, o in ctx.odds.items()
              if k not in played and o.get("hw") and dt_by_key.get(k) is not None]
    dates = [dt_by_key[k] for k in priced]
    if not dates:
        return None   # keine datierten, bepreisten, ungespielten Odds → nichts zu prüfen
    front = min(dates)
    MAX_DAYS = 45   # legit Vorab-Preisung ~2-3 Wochen; ein Rückspiel-Fehlmatch liegt Monate entfernt.
    fails = []
    for k in priced:
        gap = (dt_by_key[k] - front).days
        if gap > MAX_DAYS:
            fails.append(f"{k}: Odds auf {dt_by_key[k].isoformat()} — {gap} Tage nach Front "
                         f"{front.isoformat()} (Hin/Rück-Fehlmatch?)")
    return _chk("liga_odds_round_sane", "Liga/MLS-Odds nur auf nahen Terminen (≤45 Tage)", "warn",
                fails, "fetch_liga_odds.pick_event_for_fixture trennt Hin/Rück per Datum; dieser "
                "Backstop misst den Kalender-Abstand (runden-agnostisch → MLS-tauglich).")


@integrity_check
def check_data_not_wiped(ctx):
    """NEU 12.07.2026 (Lucas: „Cards für Liga kaputt" — API-Zugang lief nachts ab). Ein Fetcher
    hatte mls-data.json mit LEEREN groups überschrieben (0 Teams/0 Fixtures), die picks-Leichen
    blieben → Liga-Cards kippten. Wipe-Schutz sitzt jetzt in den Fetchern (safe_write); DIESER
    Guard ist das Sicherheitsnetz: er macht einen durchgerutschten Wipe im Status SOFORT sichtbar,
    statt dass er tagelang still im Frontend blutet. ERROR, nicht warn — das ist Datenverlust."""
    fails = []
    n_fx = sum(len(g.get("fixtures") or []) for g in (ctx.wm.get("groups") or {}).values())
    n_tm = sum(len(g.get("teams") or []) for g in (ctx.wm.get("groups") or {}).values())
    n_picks = len(ctx.wm.get("picks") or {})
    if n_fx == 0:
        fails.append("0 Fixtures in groups — Datensatz leer/gewiped (API-Ausfall?)")
    if n_tm == 0:
        fails.append("0 Teams in groups — Datensatz leer/gewiped (API-Ausfall?)")
    # Verwaiste Picks: picks-Keys da, aber keine Fixtures → genau das Muster, das die Cards killte
    if n_picks > 0 and n_fx == 0:
        fails.append(f"{n_picks} picks-Keys ohne EIN einziges Fixture — verwaiste Pick-Leichen "
                     f"(genau das Muster, das die Liga-Cards gekillt hat)")
    return _chk("data_not_wiped", "Datensatz nicht leer-geschrieben", "error", fails,
                f"{n_tm} Teams · {n_fx} Fixtures · {n_picks} pick-Keys. "
                f"Fetcher-Wipe-Schutz: safe_write.py + build_liga_data.merge_groups_preserve.")


@integrity_check
def check_liga_market_coverage(ctx):
    """NEU 09.07.2026 (Lucas: „Liga auf top" — AH + Softbook-O/U ergänzt). Fängt einen STILLEN
    Ausfall der neuen Märkte: wenn Liga-Odds fließen, aber die AH-Leiter (spreads-Markt) oder die
    Public/Softbook-O/U komplett fehlen (falsche Book-Region, API-Markt weg, Extraktions-Regression),
    würden AH-Picks + die O/U-Softbook-Signale still verstummen. Warnt nur bei TOTALER Abwesenheit
    (einzelne Spiele ohne AH sind normal). Braucht ≥5 bepreiste Spiele, sonst No-Op (Vorsaison)."""
    if not ctx.is_liga:
        return None
    played = {ctx.mk(fx) for _g, fx in ctx.fixtures
              if (fx.get("result") or {}).get("status") in ("FT", "AET", "PEN")}
    priced = [e for k, e in (ctx.odds or {}).items()
              if k not in played and isinstance(e, dict) and e.get("hw")]
    if len(priced) < 5:
        return None   # zu wenig bepreist (Vorsaison) → nichts Aussagekräftiges
    n_ah = sum(1 for e in priced
               if e.get("ahLadder") or any(k.startswith("ahH_n") for k in e))
    n_pub_ou = sum(1 for e in priced
                   if e.get("public_o15") or e.get("public_o25") or e.get("public_o35"))
    fails = []
    if n_ah == 0:
        fails.append(f"AH-Leiter fehlt bei ALLEN {len(priced)} bepreisten Spielen "
                     f"— spreads-Markt/Region prüfen (fetch_liga_odds)")
    if n_pub_ou == 0:
        fails.append(f"Public/Softbook-O/U fehlt bei ALLEN {len(priced)} Spielen "
                     f"— SOFT_PRIORITY-Buch/Region prüfen")
    return _chk("liga_market_coverage", "Liga AH + Softbook-O/U vorhanden", "warn", fails,
                f"{n_ah}/{len(priced)} mit AH · {n_pub_ou}/{len(priced)} mit Public-O/U.")


# Frische-Schwelle für Pinnacle-Odds (Stunden). Der Auto-Trader stoppt erst hart
# bei 24h (max_odds_age_hours) — dieser Guard WARNT viel früher, damit eingefrorene
# fetch_wm_odds-Läufe im 🛡️-Panel sichtbar werden, BEVOR auf 13h alten Preisen
# getradet wird. Befund Lucas 16.06.2026 (Sharp Radar zeigte 13h).
ODDS_FRESHNESS_WARN_H = 6.0


@integrity_check
def check_odds_freshness(ctx):
    """NEU 16.06.2026: Pinnacle-Odds müssen halbwegs frisch sein. Edge = Pinnacle-fair
    vs Live-Poly — sind die Odds eingefroren (fetch_wm_odds tot/Cron-Lücke), rechnet
    JEDER Edge gegen veraltete Preise (gefährlich für Auto-Trades). Der bisherige
    24h-Hard-Stop im Trader liess 13h durch; nichts machte es sichtbar. Dieser Guard
    nimmt die frischeste updatedAt aller Odds und warnt ab ODDS_FRESHNESS_WARN_H."""
    newest = None
    for v in ctx.odds.values():
        ts = v.get("updatedAt") if isinstance(v, dict) else None
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if newest is None or t > newest:
            newest = t
    fails = []
    if newest is not None:
        age_h = (ctx.now - newest).total_seconds() / 3600
        if age_h > ODDS_FRESHNESS_WARN_H:
            fails.append(f"Frischeste Pinnacle-Odds {age_h:.1f}h alt "
                         f"(> {ODDS_FRESHNESS_WARN_H:.0f}h) — fetch_wm_odds eingefroren? "
                         f"Edges laufen gegen veraltete Preise.")
    return _chk("odds_freshness", "Pinnacle-Odds frisch (< {:.0f}h)".format(ODDS_FRESHNESS_WARN_H),
                "warn", fails,
                "Auto-Trader stoppt hart erst bei max_odds_age_hours (24h) — dieser Guard "
                "warnt früh. Root-Cause: fetch_wm_odds-Workflow/Cron prüfen.")


SWAP_HISTORY_FILE = _BASE / D.file("wm_swap_history.json", "liga_swap_history.json").name


def _record_swap_history(fails, now):
    """Append-only Verlauf der Home/Away-Swap-Treffer (20.06.2026, Lucas: „schauen ob's öfter
    kommt"). Dedup pro (Tag, Spiel), prunt > 120 Tage. Returns (gesamt, distinkte Tage, zuletzt)."""
    import json
    try:
        try:
            hist = json.loads(open(SWAP_HISTORY_FILE, encoding="utf-8").read())
        except Exception:
            hist = {"events": []}
        events = hist.get("events", [])
        today = now.date().isoformat()
        seen = {(e.get("date"), e.get("fixture")) for e in events}
        for f in fails:
            fx = f.split(":", 1)[0].strip()
            if (today, fx) not in seen:
                events.append({"date": today, "fixture": fx})
                seen.add((today, fx))
        # Prune > 120 Tage
        from datetime import timedelta
        cutoff = (now.date() - timedelta(days=120)).isoformat()
        events = [e for e in events if (e.get("date") or "") >= cutoff]
        hist["events"] = events
        with open(SWAP_HISTORY_FILE, "w", encoding="utf-8") as fh:
            json.dump(hist, fh, ensure_ascii=False, indent=2)
        days = sorted({e["date"] for e in events})
        return len(events), len(days), (events[-1] if events else None)
    except Exception:
        return 0, 0, None


@integrity_check
def check_homeaway_consistent(ctx):
    fails = []
    for mk, o in ctx.odds.items():
        hw, aw = o.get("hw"), o.get("aw")
        pj = ctx.poly_prices.get(mk) or {}
        phw, paw = pj.get("hw"), pj.get("aw")
        # FIX 16.06.2026 (TOTER GUARD): Pinnacle sind Dezimalquoten (>1.0), Poly aber
        # WAHRSCHEINLICHKEITEN (0–1). Der alte all(... x>1.0)-Filter verlangte auch von
        # phw/paw >1.0 → traf NIE zu → der Guard übersprang JEDES Spiel und war effektiv
        # tot (immer grün). Darum fing der Pick-Validator CPV-SAU, die Integritäts-
        # Tabelle aber nicht. Jetzt getrennt validiert: Odds >1.0, Poly 0<p<1.
        if not (isinstance(hw, (int, float)) and isinstance(aw, (int, float)) and hw > 1.0 and aw > 1.0):
            continue
        if not (isinstance(phw, (int, float)) and isinstance(paw, (int, float)) and 0 < phw < 1 and 0 < paw < 1):
            continue
        # Schwelle 0.3 → 0.15. CPV-SAU (hw 2.40/aw 2.63, Δ0.23,
        # Pinn-Fav Heim vs Poly-Fav Ausw) rutschte bei 0.3 durch, der Pick-Validator
        # (Schwelle 0.05) fing es aber → Status zeigte „1 Fehler", Integritäts-Tabelle
        # aber grün. 0.15 schliesst die Lücke ohne Coin-Flip-False-Positives (verifiziert:
        # CPV-SAU war der EINZIGE Konflikt im Slate).
        if abs(hw - aw) > 0.15 and (hw < aw) != (phw > paw):
            fails.append(f"{mk}: Pinnacle-Fav {'Heim' if hw < aw else 'Ausw'} (hw {hw}/aw {aw}) ≠ "
                         f"Poly-Fav {'Heim' if phw > paw else 'Ausw'} (Swap-Verdacht)")
    hint = ("fetch_wm_odds:241 hatte hw↔aw-Swap → Mexiko als Underdog gelistet. "
            "Bei knappen Quoten ggf. echte Markt-Uneinigkeit — Fixture-Orientierung prüfen.")
    if fails:
        total, ndays, last = _record_swap_history(fails, ctx.now)
        if total:
            last_s = f" (zuletzt {last['fixture']} am {last['date'][5:]})" if last else ""
            hint += f" · Verlauf: {total}× an {ndays} Tag(en){last_s} — erst bei Muster fixen."
    return _chk("homeaway_consistent", "Home/Away nicht vertauscht (Pinn vs Poly)", "error", fails, hint)


# Coverage-Guard (21.06.2026, Lucas: „ich hab Angst dass wir Fehler haben und die Guards
# das nicht erkennen"). Die übrige Batterie prüft DATEN-Konsistenz, nicht Signal-ABDECKUNG.
# Dieser Guard liest die tägliche Feuer-History (wm_signal_history.json) und schlägt an, wenn
# ein Signal, das zuletzt ZUVERLÄSSIG feuerte (jeder der letzten 3 Tage > 0), heute slatewide
# auf 0 fällt — das Muster eines Fetcher-Ausfalls oder einer Code-Regression, das sonst still
# im „greift hier nicht" untergeht. Bewusst WARN (kein error): kann auch ein legitimer Tag
# ohne passende Spiele sein — der Mensch schaut drauf. min(letzte 3)>0 filtert intermittierende
# Signale (z.B. Wetter an einem kühlen Spieltag) raus, damit kein Dauer-Fehlalarm entsteht.
SIGCOV_MIN_BASELINE = 3     # Median-Feuer im Fenster, damit ein Signal überhaupt „beobachtet" wird
SIGCOV_BASELINE_DAYS = 7    # Trailing-Fenster

@integrity_check
def check_signal_coverage(ctx):
    import statistics
    hist = _lazy(D.file("wm_signal_history.json", "liga_signal_history.json").name)
    if not isinstance(hist, list) or len(hist) < 4:
        return _chk("signal_coverage", "Kein Signal still verstummt", "warn", [],
                    "Zu wenig History (<4 Tage) für Coverage-Vergleich — sammelt sich an.")
    latest   = hist[-1]
    baseline = hist[-(SIGCOV_BASELINE_DAYS + 1):-1]   # bis zu 7 Tage VOR dem letzten
    per_now  = latest.get("perSignal") or {}
    fails = []
    for name, today in sorted(per_now.items()):
        if not isinstance(today, (int, float)):
            continue
        counts = [(h.get("perSignal") or {}).get(name, 0) for h in baseline]
        counts = [c for c in counts if isinstance(c, (int, float))]
        if len(counts) < 3:
            continue
        recent3 = counts[-3:]
        if today == 0 and min(recent3) > 0 and statistics.median(counts) >= SIGCOV_MIN_BASELINE:
            med = statistics.median(counts)
            active = sum(1 for c in counts if c > 0)
            fails.append(f"{name}: heute 0 gefeuert, zuletzt Ø {med:.0f}/Tag "
                         f"({active}/{len(counts)} Tage aktiv, letzte 3 Tage durchgehend) — verstummt?")
    hint = ("Ein Signal das die letzten Tage zuverlässig feuerte und heute slatewide 0 zeigt = "
            "Verdacht auf Daten-/Fetcher-Ausfall oder Code-Regression. Engine prüfen, nicht ignorieren. "
            "WARN, weil auch ein Spieltag ohne passende Lage sein kann.")
    return _chk("signal_coverage", "Kein Signal still verstummt", "warn", fails, hint)


@integrity_check
def check_trade_clv_coverage(ctx):
    # Mess-Schicht-Guard (21.06.2026, Lucas: „lass mich vorher die Mess-Schicht schließen").
    # CLV (Entry vs Pinnacle-Closing) ist der Frühindikator für +EV — ohne ihn ist die Trade-
    # Auswertung blind. Dieser Guard meldet, wenn geschlossene Trades keine CLV/Closing-Daten
    # haben (Closing-Snapshot nicht zuverlässig bei Anpfiff erfasst) → Post-Mortem teilblind.
    import json
    res = _lazy(D.file("wm_results.json", "liga_results.json").name)
    pm = ((res.get("summary") or {}).get("postmortem") or {}) if isinstance(res, dict) else {}
    closed = pm.get("closedN") or 0
    fails = []
    if closed >= 5:
        cov = str(pm.get("clvCoverage") or "0/0")
        try:
            got, tot = (int(x) for x in cov.split("/"))
        except Exception:
            got, tot = 0, closed
        if tot > 0 and got / tot < 0.5:
            fails.append(f"CLV nur bei {cov} geschlossenen Trades erfasst — Closing-Snapshot "
                         f"lückenhaft → Auswertung teilblind")
        if (pm.get("heldToClose") or {}).get("n", 0) == 0:
            fails.append("polyClose fehlt durchgängig → 'halten bis Closing'-Gegenrechnung "
                         "nicht möglich (Poly-Closing-Snapshot nicht erfasst)")
    hint = ("CLV (Entry vs Pinnacle-Closing) ist DER Frühindikator für +EV; ohne ihn lässt sich "
            "nicht sagen ob die Strategie Wert holt. Lücke = Closing-Snapshot wird nicht "
            "zuverlässig bei Anpfiff eingefroren (pinnClose/polyClose). Schließt an den "
            "Closing-In-Play-Guard an — die Write-Seite muss bei Anpfiff einfrieren.")
    return _chk("trade_clv_coverage", "Trade-Auswertung: CLV/Closing erfasst", "warn", fails, hint)


@integrity_check
def check_clv_card_coverage(ctx):
    """NEU 28.06.2026 (Lucas: „CLV als Nordstern"): aufgelöste Steam-CARD-Picks müssen eine
    Closing-Linie (clvPP) haben, sonst ist die CLV-Bilanz (compute_clv_summary) blind. Anders als
    check_trade_clv_coverage (PLATZIERTE Polymarket-Trades) zielt das auf die Card-Picks selbst.
    Erst ab MIN_N aufgelösten Picks bewertet (vorher zu wenig Signal)."""
    MIN_N = 10
    picks = ctx.wm.get("picks") or {}
    resolved = with_clv = 0
    for plist in picks.values():
        if not isinstance(plist, list):
            continue
        for p in plist:
            if not isinstance(p, dict) or p.get("source") != "steam" or p.get("trackingExcluded"):
                continue
            if str(p.get("result") or "").upper() not in ("WIN", "LOSS", "VOID"):
                continue
            resolved += 1
            if p.get("clvResolved") and p.get("clvPP") is not None:
                with_clv += 1
    fails = []
    if resolved >= MIN_N:
        pct = with_clv / resolved * 100
        if pct < 70:
            fails.append(f"Nur {with_clv}/{resolved} aufgelöste Steam-Picks haben eine Closing-Linie "
                         f"({pct:.0f}%) — CLV-Bilanz unvollständig.")
    return _chk("clv_card_coverage", "CLV: Closing-Abdeckung der Steam-Card-Picks", "warn", fails,
                "resolve_steam_clv + Closing-Capture prüfen (closing_is_prematch / Anpfiff-Snapshot). "
                "Ohne Closing-Linie kann compute_clv_summary den Pick nicht werten.")


@integrity_check
def check_edge_consistent(ctx):
    fails = []
    for fx in ctx.poly_all:
        for m in ("hw", "dr", "aw", "o25", "u25"):
            fair, pol, ed = fx.get(f"fair_{m}"), fx.get(f"poly_{m}"), fx.get(f"edge_{m}")
            if not all(isinstance(v, (int, float)) for v in (fair, pol, ed)):
                continue
            live = round((fair - pol) * 100, 1)
            if abs(live - ed) > 0.5:
                fails.append(f"{fx.get('homeId')}-{fx.get('awayId')} {m}: edge {ed:+.1f} ≠ live {live:+.1f}")
    return _chk("edge_consistent", "Edge == fair − poly (kein Stale-Edge)", "error", fails,
                "Stale edge_aw=-1.4 vs live +7.1 hat einen echten Trade blockiert.")


@integrity_check
def check_schedule_date(ctx):
    fails = []
    seed = {ctx.mk(fx): (fx.get("date") or "")[:10] for _g, fx in ctx.fixtures}
    for mk, od in ctx.poly_prices.items():
        pd = (od.get("date") or "")[:10]
        sd = seed.get(mk)
        if pd and sd and pd != sd:
            fails.append(f"{mk}: Seed {sd} ≠ Poly {pd}")
    return _chk("schedule_date", "Spielplan-Datum == Polymarket", "error", fails,
                "Seed war ~1 Tag verschoben → Picks am falschen Tag.")


@integrity_check
def check_lineup_present(ctx):
    from datetime import timedelta
    horizon = ctx.now + timedelta(minutes=90)
    fails = []
    for _g, fx in ctx.fixtures:
        ko = None
        if fx.get("kickoff"):
            try:
                ko = datetime.fromisoformat(str(fx["kickoff"]).replace("Z", "+00:00"))
            except Exception:
                ko = None
        if ko is None or not (ctx.now <= ko <= horizon):
            continue   # nur Spiele die in <90min anpfeifen
        ent = ctx.lineups.get(ctx.mk(fx))
        starting = ((ent or {}).get("home") or {}).get("starting") or []
        if not ent or not starting:
            mins = int((ko - ctx.now).total_seconds() / 60)
            fails.append(f"{ctx.mk(fx)}: Anpfiff in {mins}min, KEINE Aufstellung")
    return _chk("lineup_present", "Aufstellung da vor Anpfiff (T-90min)", "warn", fails,
                "lineup_signal braucht die Startelf. War leer wegen Namens-Match + Wien-Zeit-Bug.")


@integrity_check
def check_public_consensus(ctx):
    real = _real_match_keys(ctx)
    # 14.07.2026: weit entfernte Anpfiffe raus — Softbooks eröffnen erst ~1 Woche vorher,
    # Polymarket listet früher. Sonst Dauer-Gelb für Spiele, die schlicht noch niemand bepreist hat.
    _zu_frueh = _far_future_keys(ctx) | _nie_eroeffnet_keys(ctx)
    fails = [f"{mk}: kein public_hw" for mk, o in ctx.odds.items()
             if mk in real and mk not in _zu_frueh and not o.get("public_hw")]
    return _chk("public_consensus", "Public-Konsens (Soft-Books) vorhanden", "warn", fails,
                "Ohne public_* feuert public_static_bias nicht.")


@integrity_check
def check_public_is_multibook(ctx):
    """FIX 12.06.2026: public_* soll der MEDIAN-KONSENS (fetch_wm_multibook_odds,
    'Konsens (N Books)') sein, nicht der alte verrauschte Einzel-Soft-Book
    (williamhill/bet365 aus fetch_wm_odds). check_public_consensus prüft nur ob
    public_hw DA ist → blind dafür, ob der Konsens wirklich aktiv ist. Dieser
    Check flaggt Fixtures, deren public_* noch vom Einzel-Book stammt (= Multibook-
    Step hat nicht geschrieben, z.B. APIF /odds leer oder Step-Fail)."""
    real = _real_match_keys(ctx)
    fails = []
    for mk, o in ctx.odds.items():
        if mk not in real or not o.get("public_hw"):
            continue
        bk = str(o.get("public_bookmaker") or "")
        if not bk.lower().startswith("konsens"):
            fails.append(f"{mk}: public aus Einzel-Book '{bk or '?'}' statt Konsens")
    return _chk("public_is_multibook", "Public = Multi-Book-Konsens (nicht Einzel-Book)",
                "warn", fails,
                "public_static_bias soll auf Median-Konsens laufen, nicht 1 verrauschtem "
                "Soft-Book. Single-Book = fetch_wm_multibook_odds hat (noch) nicht geschrieben.")


@integrity_check
def check_no_phantom_odds(ctx):
    """Odds-Keys, die KEINEM echten Fixture entsprechen — meist verkehrte
    Heim/Auswärts-Reihenfolge (SUI-CAN statt CAN-SUI), leer. Daten-Hygiene:
    so ein Phantom-Key kann bei Reverse-Lookups falsch matchen."""
    real = _real_match_keys(ctx)
    fails = [f"{mk}: kein echtes Fixture (Spiegel-Key?)" for mk in ctx.odds if mk not in real]
    return _chk("no_phantom_odds", "Keine Phantom-Odds-Keys (verkehrte Reihenfolge)", "warn", fails,
                "84 Odds-Keys vs 72 Fixtures = 12 leere Spiegel-Einträge. Quelle prüfen.")


@integrity_check
def check_engine_version_stamped(ctx):
    """04.07.2026 (Lucas): jeder BET/ABWÄGEN-Pick soll eine engineVersion tragen — sonst lernt der
    Loop ihn nur über das Matchday-Fallback statt version-sauber. generate_*_picks stempelt bei
    JEDEM Lauf (set-if-absent). Ungestempelte actionable Picks = Stempel-Regression (oder Legacy von
    vor dem Feature — heilt beim nächsten Pipeline-Lauf). WARN, weil selbstheilend."""
    fails = []
    for mk, plist in (ctx.wm.get("picks") or {}).items():
        if not isinstance(plist, list):
            continue
        for p in plist:
            if p.get("verdict") in ("BET", "ABWÄGEN") and not p.get("engineVersion"):
                fails.append(f"{mk}: {p.get('market')} ohne engineVersion")
    return _chk("engine_version_stamped", "Picks tragen engineVersion (version-aware Lernen)",
                "warn", fails,
                "generate_*_picks stempelt bei jedem Lauf; ungestempelt = Regression oder Legacy "
                "(heilt beim nächsten Lauf). Version pro Profil in cocobet_config.engine_version.")


@integrity_check
def check_result_score_final(ctx):
    """result.home_score darf NUR gesetzt sein, wenn das Spiel beendet ist
    (FT/AET/PEN). Sonst ist ein Live-Zwischenstand gespeichert, den das
    Dashboard als „Endstand" rendert (USA-PRY 1H 2:0 vs echtem 4:1, 13.06.2026)."""
    finished = {"FT", "AET", "PEN"}
    fails = []
    for _g, fx in ctx.fixtures:
        r = fx.get("result") or {}
        st = str(r.get("status") or "").upper()
        if r.get("home_score") is not None and st not in finished:
            fails.append(f"{ctx.mk(fx)}: Score {r.get('home_score')}:{r.get('away_score')} "
                         f"bei Status {st or '—'} (nicht beendet)")
    return _chk("result_score_final", "Endstand nur bei beendetem Spiel", "error", fails,
                "Live-Zwischenstand im result → wird als Endstand gerendert.")


_FINISHED = {"FT", "AET", "PEN"}


@integrity_check
def check_autobet_kickoff_present(ctx):
    """Offene Auto-Bets MÜSSEN eine auflösbare Anpfiffzeit haben (bet.kickoff ODER
    Fixture-Kickoff). Sonst greift der 2h-Pre-Match-Close nicht und der Trade rutscht
    LIVE ins In-Play (QAT-SUI 13.06.2026, −€5.50). GELD-KRITISCH."""
    ko_by_ha = {ctx.mk(fx): fx.get("kickoff") for _g, fx in ctx.fixtures if fx.get("kickoff")}
    fails = []
    for b in ctx.auto_bets:
        is_open = ((b.get("status") or "").lower() == "placed"
                   and not b.get("soldAt") and b.get("result") is None)
        if not is_open:
            continue
        ha = f"{b.get('homeId')}-{b.get('awayId')}"
        if not (b.get("kickoff") or ko_by_ha.get(ha)):
            fails.append(f"{ha} {b.get('market','')}: offener Auto-Bet ohne auflösbaren Kickoff")
    return _chk("autobet_kickoff", "Offene Auto-Bets haben Anpfiffzeit", "error", fails,
                "Ohne Kickoff feuert der 2h-Close nicht → Trade rutscht ins In-Play.")


@integrity_check
def check_resolved_status_propagated(ctx):
    """Ein beendetes Spiel darf keinen Auto-Bet mehr auf status='placed' haben — sonst
    klebt er als '🔴 läuft' in den offenen Positionen (QAT-SUI nach LOSS, 13.06.2026).
    resolve_wm_results muss won/lost/void zurückschreiben."""
    finished_ha = {f"{fx.get('home')}-{fx.get('away')}" for _g, fx in ctx.fixtures
                   if str((fx.get("result") or {}).get("status") or "").upper() in _FINISHED}
    fails = []
    for b in ctx.auto_bets:
        ha = f"{b.get('homeId')}-{b.get('awayId')}"
        if ha in finished_ha and (b.get("status") or "").lower() == "placed":
            fails.append(f"{ha} {b.get('market','')}: Spiel beendet, Auto-Bet noch 'placed'")
    return _chk("resolved_status_propagated", "Beendete Spiele: Auto-Bet-Status aktualisiert", "warn", fails,
                "Sonst hängt die Wette ewig in 'Offene Positionen · Live'.")


@integrity_check
def check_standings_built(ctx):
    """Standings-Builder (17.06.2026): wenn beendete Spiele existieren, MUSS wm["standings"]
    befüllt sein (incentive_signal + pressure_index brauchen die Tabelle). Fängt eine
    Regression, falls der Build (in generate_wm_picks) ausfällt."""
    finished = sum(1 for _g, fx in ctx.fixtures
                   if str((fx.get("result") or {}).get("status") or "").upper() in _FINISHED)
    standings = ctx.wm.get("standings") or {}
    nrows = sum(len(v) for v in standings.values() if isinstance(v, list))
    fails = []
    if finished >= 2 and nrows == 0:
        fails.append(f"{finished} beendete Spiele, aber wm[standings] leer → "
                     f"incentive/pressure ohne Daten")
    return _chk("standings_built", "Gruppentabellen gebaut (wenn Ergebnisse da)", "warn", fails,
                "wm_standings.apply_to_wm läuft in generate_wm_picks; leer trotz Ergebnissen = Build-Ausfall.")


@integrity_check
def check_safer_line_applied(ctx):
    """Phase-1-Safer-Line (17.06.2026, Lucas): ein Steam-Pick auf einer riskanten Linie
    (Über 3.5, Heimsieg, Auswärtssieg …) MUSS die nächst-sichere Linie abgeleitet haben,
    wenn eine mit Quote ≥ 1.35 und echt niedriger verfügbar war. Macht sichtbar, wenn die
    Ableitung nicht greift. Spiegel von generate_wm_picks._STEAM_SAFER_MAP. (Frozen/gepostete
    Picks von vor dem Fix können hier auftauchen, bis sie neu gebaut werden — erwartetes
    Übergangsrauschen.)"""
    SAFER = {
        "Über 3.5 Tore": ("o25", "Über 2.5 Tore"), "Über 2.5 Tore": ("o15", "Über 1.5 Tore"),
        "Unter 1.5 Tore": ("u25", "Unter 2.5 Tore"), "Unter 2.5 Tore": ("u35", "Unter 3.5 Tore"),
        "Heimsieg": ("dc1X", "Doppelte Chance — 1X"), "Auswärtssieg": ("dcX2", "Doppelte Chance — X2"),
    }
    FLOOR = 1.35
    picks = ctx.wm.get("picks") or {}
    odds = ctx.odds
    finished = _finished_keys(ctx)
    fails = []
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        parts = key.split("-")
        if len(parts) < 4:
            continue
        ha = f"{parts[-2]}-{parts[-1]}"
        if ha in finished:
            continue   # beendetes Spiel: Pick immutable, Safer-Line nicht mehr ableitbar (Übergangsrauschen)
        o = odds.get(ha) or {}
        for p in plist:
            if p.get("source") != "steam" or p.get("trackingExcluded"):
                continue
            if p.get("result"):
                continue  # aufgelöst → egal
            if p.get("safeDerived"):
                so = p.get("odds")
                if isinstance(so, (int, float)) and so < FLOOR:
                    fails.append(f"{ha} {p.get('market')}: safeDerived aber Quote {so} < {FLOOR}")
                continue
            mp = SAFER.get(p.get("market"))
            if not mp:
                continue
            sk, lbl = mp
            so, po = o.get(sk), p.get("odds") or 0
            if isinstance(so, (int, float)) and FLOOR <= so < po:
                fails.append(f"{ha} {p.get('market')} @{po}: sichere Linie {lbl} @{so} "
                             f"verfügbar (≥{FLOOR}), nicht abgeleitet")
    return _chk("safer_line_applied", "Safer-Line abgeleitet wo verfügbar (≥1.35)", "warn", fails,
                "Steam-Pick auf riskanter Linie obwohl sichere Linie ≥1.35 verfügbar — "
                "Ableitung greift nicht (oder Pick ist frozen von vor dem Fix).")


@integrity_check
def check_reverser_demoted(ctx):
    """Reverser-Guard (18.06.2026, Lucas): ein Steam-Pick, dessen FRISCHES Geld gegen ihn
    dreht (freshnessState == 'reverse' / reverser=True), darf NICHT mehr als BET sichtbar
    sein — er muss auf ABWÄGEN/BEOBACHTEN zurückgestuft sein. Macht Lecks sichtbar, wo der
    frische Reverser den Move seit Eröffnung nicht überschrieben hat. Gepostete/frozen Picks
    von vor dem Fix können bis zum Neu-Bau auftauchen (erwartetes Übergangsrauschen)."""
    picks = ctx.wm.get("picks") or {}
    fails = []
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        for p in plist:
            if p.get("result") or p.get("trackingExcluded"):
                continue
            is_rev = p.get("reverser") or p.get("freshnessState") == "reverse"
            if is_rev and p.get("verdict") == "BET":
                fails.append(f"{key} {p.get('market')}: Reverser "
                             f"({p.get('reverserPP', p.get('recentMovePP'))}pp) aber noch BET")
    return _chk("reverser_demoted", "Reverser-Picks zurückgestuft (nicht BET)", "warn", fails,
                "Frisches Geld dreht gegen den Pick → Move seit Eröffnung überholt. "
                "Erwartung: generate_wm_picks stuft auf ABWÄGEN/BEOBACHTEN zurück "
                "(downgradedReason 'Reverser').")


@integrity_check
def check_bet_move_fresh(ctx):
    """BET-Lebenszyklus (18.06.2026, Lucas): ein Steam-BET muss entweder auf einem FRISCHEN
    Move eingestiegen sein (lastMoveH ≤ Hürde) ODER ein bewusst GEHALTENER BET sein (betHeld,
    war schon BET, kein Reverser). Ein BET auf einem stale Move OHNE Hold-Flag ist ein Leck —
    der Entry-Hürden-Gate hat nicht gegriffen. lastMoveH None (unmappbar/Nicht-Steam) =
    ausgenommen (Hürde greift dort bewusst nicht)."""
    HURDLE = 48 + 1   # kleine Toleranz; echte Schwelle ist config (wm 48)
    picks = ctx.wm.get("picks") or {}
    fails = []
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        for p in plist:
            if p.get("source") != "steam" or p.get("verdict") != "BET":
                continue
            if p.get("result") or p.get("trackingExcluded"):
                continue
            lmh = p.get("lastMoveH")
            if lmh is None or p.get("betHeld"):
                continue
            if lmh > HURDLE:
                fails.append(f"{key} {p.get('market')}: BET aber Move stale "
                             f"(lastMoveH={lmh}h > Hürde) und kein betHeld")
    return _chk("bet_move_fresh", "BET frisch eingestiegen oder gehalten", "warn", fails,
                "Neuer BET braucht frischen Move (≤ bet_entry_hurdle_h). Alter Move darf nur "
                "via Hold (betHeld) BET bleiben. Stale-BET ohne Hold = Entry-Gate-Leck.")


@integrity_check
def check_freshness_learning_coupled(ctx):
    """Lern-Kopplung (18.06.2026, Lucas): ein Steam-Pick mit frischem confirm/reverse-Zustand
    MUSS das `freshness_leg`-Signal in signals[] tragen — sonst kommt die Frische NICHT im
    Bayesian-Ledger an und das System lernt nie, ob Reverser wirklich verlieren. Drift (Score 0)
    wird bewusst nicht geledgert (neutral), daher hier ausgenommen. Picks ohne freshnessState
    (Altpfad/gepostet) werden ignoriert — kein Übergangsrauschen."""
    picks = ctx.wm.get("picks") or {}
    fails = []
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        for p in plist:
            if p.get("source") != "steam" or p.get("reverserCounter"):
                continue
            if p.get("freshnessState") not in ("confirm", "reverse"):
                continue
            names = {s.get("name") for s in (p.get("signals") or []) if isinstance(s, dict)}
            if "freshness_leg" not in names:
                fails.append(f"{key} {p.get('market')}: freshnessState="
                             f"{p.get('freshnessState')} aber kein freshness_leg-Signal "
                             f"(Lern-Loop bekommt die Frische nicht)")
    return _chk("freshness_learning_coupled", "Frische landet im Lern-Ledger", "warn", fails,
                "freshness_leg-Signal muss bei confirm/reverse feuern, damit der Bayesian-Loop "
                "das Gewicht lernt. Fehlt es → Signal-Engine lief vor dem Frische-Block oder "
                "Signal nicht registriert.")


# Spread-Gate-Härtung ging am 17.06.2026 abends live (entryAsk-Recording + REQUIRE_BOOK_FOR_
# ENTRY). Positionen DAVOR wurden teils zum Mid eingebucht (entryAsk=None) — bekannter Alt-
# Bestand, läuft aus, kein neuer Fehler. Der Guard meldet daher nur Positionen AB diesem
# Stichtag: ein neuer Mid-Entry = echte Regression (Gate umgangen). Alt-Bestand = stumm.
ENTRY_ASK_GUARD_SINCE = "2026-06-18"


@integrity_check
def check_smartmoney_sane(ctx):
    """Smart-Money-Daten-Sanity (19.06.2026, Lucas): wm_poly_smartmoney.json (data-api /holders+
    /trades vom Mac-Runner) muss kohärent sein — Outcome-Shares summieren ~1, totalUsd da. Fängt
    kaputte/partielle Aggregation, bevor das (niedrig gewichtete) smart_money-Signal darauf läuft.
    Fehlt die Datei → still (Feature noch nicht am Runner deployt)."""
    sm = _lazy(D.file("wm_poly_smartmoney.json", "liga_poly_smartmoney.json").name)
    if not isinstance(sm, dict):
        return None
    matches = sm.get("matches", sm)
    if not isinstance(matches, dict) or not matches:
        return None
    fails = []
    for key, m in matches.items():
        if not isinstance(m, dict):
            continue
        outs = m.get("outcomes") or {}
        shares = [o.get("share") for o in outs.values()
                  if isinstance(o, dict) and isinstance(o.get("share"), (int, float))]
        if shares:
            s = sum(shares)
            if not (0.9 <= s <= 1.1):
                fails.append(f"{key}: Outcome-Shares summieren {s:.2f} (≠ ~1.0) — Aggregation kaputt?")
        if m.get("totalUsd") in (None, 0):
            fails.append(f"{key}: totalUsd fehlt/0 — Holder/Trade-Fetch leer?")
    return _chk("smartmoney_sane", "Smart-Money-Daten kohärent", "warn", fails,
                "Shares müssen ~1 summieren + totalUsd da. Sonst läuft das smart_money-Signal "
                "auf Müll. Quelle: fetch_wm_poly_smartmoney.py (data-api, Mac-Runner).")


@integrity_check
def check_btts_not_templated_traded(ctx):
    """Tripwire (23.06.2026, Lucas): eine als templated markierte BTTS-Linie (generische Pinnacle-
    Platzhalter-Linie, auf vielen Spielen identisch) darf KEINEN handelbaren Edge produzieren.
    Vorfall: CPV-SAU/PRY-AUS/JPN-SWE — fair=0.5148 aus der 1.91/1.80-Standardlinie → Phantom-Edge
    +3.5–5pp, real negativ, echtes Geld gesetzt. fetch_wm_poly_prices.compute_btts_edges nullt
    fair/edge bei btts_templated → hier prüfen, dass das auch greift."""
    fails = []
    for fx in (ctx.poly_all or []):
        if not isinstance(fx, dict) or not fx.get("btts_templated"):
            continue
        for ekey in ("edge_btts", "edge_btts_no"):
            if isinstance(fx.get(ekey), (int, float)):
                fails.append(f"{fx.get('homeId')}-{fx.get('awayId')}: {ekey}={fx[ekey]} trotz "
                             f"templated BTTS-Linie (sollte None sein)")
    return _chk("btts_not_templated_traded", "BTTS-Platzhalter nicht handelbar", "warn", fails,
                "Templated Pinnacle-BTTS-Linien (auf vielen Spielen identisch) sind kein echter "
                "Sharp-Preis → fair/edge müssen None sein, sonst tradet der Auto-Trader Phantom-Edges.")


@integrity_check
def check_ko_bracket_consistency(ctx):
    """KO-Paarungen plausibel (25.06.2026, Lucas: KO-Runden). Sobald eine Gruppe komplett ist, müssen
    deren Gruppenplatz-Slots aufgelöst sein; aufgelöste KO-Spiele dürfen nicht Team gegen sich selbst
    sein. Fängt Resolver-Ausfälle sichtbar (warn)."""
    ko = ctx.wm.get("koFixtures") or []
    if not ko:
        return _chk("ko_bracket_consistency", "KO-Bracket plausibel", "warn", [],
                    "Noch keine koFixtures (vor Gruppen-Abschluss normal).")
    FIN = {"FT", "AET", "PEN", "AWD", "WO"}
    groups = ctx.wm.get("groups") or {}
    complete = {g for g, gd in groups.items()
                if (gd.get("fixtures") and
                    all(str((fx.get("result") or {}).get("status", "")).upper() in FIN
                        for fx in gd["fixtures"]))}
    fails = []
    for f in ko:
        if f.get("bothResolved") and f.get("home") and f.get("home") == f.get("away"):
            fails.append(f"{f.get('matchKey')}: Team gegen sich selbst ({f.get('home')})")
    # Gruppe komplett, aber ein direkter Gruppenplatz-Slot dieser Gruppe noch TBD?
    for f in ko:
        if f.get("round") != "R32" or f.get("bothResolved"):
            continue
        for side, ref in (("home", f.get("homeRef", "")), ("away", f.get("awayRef", ""))):
            for g in complete:
                if (ref.endswith(f"Gruppe {g}") and not f.get(f"{side}Resolved")):
                    fails.append(f"{f.get('matchKey')}: Gruppe {g} komplett, {side} ({ref}) "
                                 f"noch nicht aufgelöst — Resolver prüfen")
    return _chk("ko_bracket_consistency", "KO-Bracket plausibel", "warn", fails,
                "resolve_wm_bracket muss Gruppenplätze auflösen sobald die Gruppe durch ist.")


@integrity_check
def check_played_games_resolved(ctx):
    """Gespielte Spiele müssen einen Endstand haben (25.06.2026, Lucas: MD3 alle pending). Kickoff
    > 5h her, aber kein FT/AET/PEN-Ergebnis → der Result-Fetch (fetch_wm_match_results) hat's nicht
    geschrieben (z.B. Heim/Auswärts-Orientierung ≠ API-Football → Match scheitert). 5h-Puffer deckt
    den 4×/Tag-Abruf-Zeitplan ab, ohne frisch-fertige Spiele fälschlich zu flaggen."""
    fails = []
    # 28.06.2026 (Lucas: KO-Tracking offen): auch koFixtures prüfen — die liegen in wm['koFixtures'],
    # nicht in groups → der Guard meldete „sauber", obwohl gespielte KO-Spiele ohne Ergebnis blieben.
    _all = list(ctx.fixtures) + [(None, fx) for fx in (ctx.wm.get("koFixtures") or [])
                                 if fx.get("home") and fx.get("away")]
    for _g, fx in _all:
        ko = fx.get("kickoff")
        if not ko:
            continue
        try:
            kt = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        except Exception:
            continue
        if (ctx.now - kt).total_seconds() < 5 * 3600:
            continue   # zu frisch — Result-Fetch (4×/Tag) hatte evtl. noch keinen Lauf
        st = str((fx.get("result") or {}).get("status") or "").upper()
        if st not in ("FT", "AET", "PEN", "AWD", "WO"):
            fails.append(f"{fx.get('home')}-{fx.get('away')}: Anpfiff {str(ko)[:16]} vorbei, "
                         f"aber Ergebnis-Status '{st or 'leer'}' — Result-Fetch-Lücke?")
    return _chk("played_games_resolved", "Gespielte Spiele haben Endstand", "warn", fails,
                "fetch_wm_match_results muss FT-Endstände schreiben. Fehlt's > 5h nach Anpfiff: "
                "Team-Matching (Orientierung/Team-ID) oder API-Football-Lag prüfen.")


@integrity_check
def check_no_duplicate_picks(ctx):
    """Eine Karte pro (Spiel, Markt) — kein doppelter Pick (23.06.2026, Lucas: PAN-CRO hatte 2×
    „Beide Teams treffen — Ja" in Cards + Tracking). Entsteht durch Refresh-/Merge-Altlasten;
    generate_wm_picks._dedup_picks_by_market fängt es am Write-Boundary, hier als Tripwire sichtbar."""
    picks = ctx.wm.get("picks") or {}
    fails = []
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        seen = {}
        for p in plist:
            if not isinstance(p, dict):
                continue
            m = p.get("market")
            seen[m] = seen.get(m, 0) + 1
        for m, n in seen.items():
            if n > 1:
                fails.append(f"{key}: '{m}' {n}× (soll 1)")
    return _chk("no_duplicate_picks", "Kein doppelter Pick je Spiel/Markt", "warn", fails,
                "Je (Spiel, Markt) genau EINE Karte. Mehrfach → _dedup_picks_by_market greift nicht "
                "(Refresh-/Merge-Altlast).")


@integrity_check
def check_steam_lag_no_dupes(ctx):
    """Steam-Lag: 1 Position pro Wette (23.06.2026, Lucas). steam_lag_log.json darf je
    (matchKey, market) nur EINEN Tracking-Eintrag haben — anderer Markt im selben Spiel ist eine
    eigene Position, aber dasselbe Match+Markt nie doppelt. Mehrfach = Dedup-Bug (vorher fand der
    Monitor nach Konvergenz den Eintrag nicht mehr → neue ID je Tag, JOR-DZA hw lag 6× im Log)."""
    if ctx.is_liga:
        return None   # steam_lag_log.json ist das WM-Log (Liga-Steam noch nicht separat) → kein Liga-Check
    log = _lazy("steam_lag_log.json")
    sigs = log.get("signals") if isinstance(log, dict) else None
    if not isinstance(sigs, list) or not sigs:
        return None
    counts = {}
    for s in sigs:
        if not isinstance(s, dict):
            continue
        k = (s.get("matchKey"), s.get("market"))
        counts[k] = counts.get(k, 0) + 1
    fails = [f"{mk} {mkt}: {c} Einträge (soll 1)" for (mk, mkt), c in counts.items() if c > 1]
    return _chk("steam_lag_no_dupes", "Steam-Lag: 1 Position pro Wette", "warn", fails,
                "Je (Match, Markt) nur EINE Tracking-Position. Mehrfach → make_signal_id/Status-"
                "Filter in steam_lag_monitor.update_log defekt (Re-Detektion legt Duplikat an).")


@integrity_check
def check_soft_opening_captured(ctx):
    """Soft-Eröffnung echt erfasst (22.06.2026, Lucas: „Opening==Jetzt auf fast jeder Card").
    Bug: fetch_wm_odds baute den Odds-Eintrag je Lauf neu OHNE public_*_open zu übernehmen →
    fetch_wm_multibook_odds (set-once-if-None) re-initialisierte das Soft-Opening auf den AKTUELLEN
    Konsens → 0pp Soft-Bewegung überall.

    PRÄZISE statt heuristisch: Beleg ist die Soft-ZEITREIHE selbst (wm2026-odds-history.json, bk=
    'public'). Nur flaggen, wenn die Soft-Linie sich real bewegt hat (oldest≠latest), das gespeicherte
    Soft-Opening aber == aktueller Soft-Quote ist → dann wurde die Bewegung nicht eingefroren. Soft
    genuin flach (Pinnacle bewegt, Soft nicht) ist KEIN Bug → wird nicht geflaggt. Fertige/laufende
    Spiele raus (historisch, gepostete Picks immutable)."""
    odds = ctx.odds or {}
    skip = set()
    for _g, fx in ctx.fixtures:
        h, a = fx.get("home"), fx.get("away")
        if not (h and a):
            continue
        fin = str((fx.get("result") or {}).get("status") or "").upper() in \
            {"FT", "AET", "PEN", "AWD", "WO"}
        passed = False
        ko = fx.get("kickoff")
        if ko:
            try:
                passed = ctx.now >= datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
            except Exception:
                passed = False
        if fin or passed:
            skip.add(f"{h}-{a}")
    hist = ctx.history or {}
    checked, frozen = 0, []
    for key, o in odds.items():
        if not isinstance(o, dict) or key in skip:
            continue
        ph = o.get("public_hw")
        po = o.get("public_hw_open")
        if not (isinstance(ph, (int, float)) and isinstance(po, (int, float))):
            continue
        snaps = [s for s in (hist.get(key) or [])
                 if s.get("bk") == "public" and isinstance(s.get("hw"), (int, float))]
        if len(snaps) < 2:
            continue                       # keine Soft-Zeitreihe → keine Aussage
        soft_first, soft_last = snaps[0]["hw"], snaps[-1]["hw"]
        if abs(soft_first - soft_last) <= 0.03:
            continue                       # Soft-Linie real flach → Opening==Jetzt ist korrekt
        checked += 1
        if abs(ph - po) < 1e-9:
            frozen.append(f"{key}: Soft bewegte sich {soft_first}→{soft_last}, aber "
                          f"Opening==Jetzt ({po}) — nicht eingefroren")
    if checked < 3:
        return None                        # zu wenig bewegte Soft-Linien → keine Aussage
    return _chk("soft_opening_captured", "Soft-Eröffnung echt erfasst", "warn", frozen,
                "Wenn die Soft-Zeitreihe sich bewegt hat, darf public_*_open nicht == aktuelle "
                "Soft-Quote sein. fetch_wm_odds.carry_soft_open muss es wie odds_open übernehmen "
                "(sonst re-initialisiert fetch_wm_multibook_odds das Opening je Lauf auf Jetzt).")


@integrity_check
def check_smartmoney_cluster_sane(ctx):
    """Cluster/Net-Flow-Sanity (22.06.2026, PolymarketScan-Idee): die je Outcome geschriebenen
    Konsens-Cluster-Felder (cluster/buyUsd/sellUsd/netFlowUsd, fetch_wm_poly_smartmoney.py) müssen
    plausibel sein, BEVOR das smart_money-Signal Cluster-Boost/Exit-Penalty darauf rechnet:
      · cluster ist ein nicht-negativer Integer und NIE größer als die Holder-Zahl der Seite
      · buyUsd/sellUsd ≥ 0 und netFlowUsd ≈ buyUsd − sellUsd
    Fehlt die Datei / hat noch keine Cluster-Felder (alter Runner-Stand) → still."""
    sm = _lazy(D.file("wm_poly_smartmoney.json", "liga_poly_smartmoney.json").name)
    if not isinstance(sm, dict):
        return None
    matches = sm.get("matches", sm)
    if not isinstance(matches, dict) or not matches:
        return None
    fails, saw_cluster = [], False
    for key, m in matches.items():
        if not isinstance(m, dict):
            continue
        for side, o in (m.get("outcomes") or {}).items():
            if not isinstance(o, dict) or "cluster" not in o:
                continue
            saw_cluster = True
            cl, hold = o.get("cluster"), o.get("holders")
            buy, sell, net = o.get("buyUsd"), o.get("sellUsd"), o.get("netFlowUsd")
            if not isinstance(cl, int) or cl < 0:
                fails.append(f"{key} {side}: cluster {cl!r} kein nicht-negativer Integer")
            if isinstance(cl, int) and isinstance(hold, int) and cl > hold:
                fails.append(f"{key} {side}: cluster {cl} > holders {hold} — unmöglich")
            for nm, v in (("buyUsd", buy), ("sellUsd", sell)):
                if v is not None and (not isinstance(v, (int, float)) or v < 0):
                    fails.append(f"{key} {side}: {nm} {v!r} negativ/kaputt")
            if all(isinstance(x, (int, float)) for x in (buy, sell, net)) \
               and abs(net - (buy - sell)) > 1.0:
                fails.append(f"{key} {side}: netFlowUsd {net} ≠ buy {buy} − sell {sell}")
    if not saw_cluster:
        return None                       # Runner schreibt Cluster-Felder noch nicht → still
    return _chk("smartmoney_cluster_sane", "Smart-Money-Cluster kohärent", "warn", fails,
                "cluster ∈ ℕ₀, ≤ holders; buy/sell ≥ 0; netFlow = buy − sell. Sonst rechnet der "
                "Cluster-Boost/Exit-Penalty im smart_money-Signal auf Müll.")


# Card-only-Signale (zwei Flächen): treiben NUR Cards + Lern-Loop, NIE das Polymarket-Trading.
# Der Auto-Trader liest signalAdj_<field> ← signalAdjustmentPP_trade. Diese Trade-Felder MÜSSEN
# den Card-only-Beitrag abziehen (generate_wm_picks _CARD_ONLY). Spiegelbild hier als Tripwire.
_CARD_ONLY_SIGNALS = ("freshness_leg", "smart_money")


@integrity_check
def check_card_only_not_in_trade(ctx):
    """ZWEI-FLÄCHEN-INVARIANTE (20.06.2026, Lucas: „Poly-Signale KEINERLEI Auswirkung aufs
    Polymarket-Trading"). freshness_leg + smart_money sind Card-only. Der Auto-Trader liest die
    _trade-Felder (signalAdjustmentPP_trade → signalAdj_<field>), die den Card-only-Score abziehen.
    Dieser Guard ist der harte Tripwire: für JEDES noch OFFENE Pick mit Card-only-Signal muss
    signalAdjustmentPP_trade ≈ signalAdjustmentPP − Σ(card-only score) sein. Weicht es ab, leckt
    ein Card-Signal in den Trade-Pfad (= Zirkel bei smart_money: Poly-Geld entscheidet Poly-Trade).

    Nur OFFENE Picks (nur die kann der Auto-Trader noch handeln): aufgelöste/beendete Picks werden
    nie neu gebaut, daher friert ihr _trade-Wert den Build-Snapshot ein — freshness_leg zerfällt
    nach Anpfiff auf 0, der Snapshot bleibt aber stehen → harmlose Alt-Differenz, kein Live-Leck
    (22.08.2026: einziger Treffer war ein längst resolvtes ESP-2-Doppelte-Chance, nie ein Handelsmarkt)."""
    picks = ctx.wm.get("picks") or {}
    fails = []
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        for p in plist:
            if p.get("result") or p.get("resolvedAt") or p.get("clvResolved"):
                continue   # aufgelöst → nie neu gebaut, _trade ist ein Alt-Snapshot, nicht mehr handelbar
            sigs = p.get("signals")
            adj, trade = p.get("signalAdjustmentPP"), p.get("signalAdjustmentPP_trade")
            if not isinstance(sigs, list) or not isinstance(adj, (int, float)) \
               or not isinstance(trade, (int, float)):
                continue
            co = sum(s.get("score", 0.0) for s in sigs
                     if isinstance(s, dict) and s.get("name") in _CARD_ONLY_SIGNALS)
            expected = round(adj - co, 1)
            if abs(trade - expected) > 0.11:
                fails.append(f"{key} {p.get('market')}: signalAdj_trade {trade} ≠ erwartet "
                             f"{expected} (adj {round(adj,1)} − card-only {round(co,1)}) — "
                             f"Card-Signal leckt in den Trade-Pfad")
    return _chk("card_only_not_in_trade", "Card-Signale nicht im Trade-Pfad", "warn", fails,
                "freshness_leg/smart_money müssen aus signalAdjustmentPP_trade abgezogen sein "
                "(generate_wm_picks _CARD_ONLY). Sonst treibt ein Card-Signal den Auto-Trader.")


@integrity_check
def check_book_fetch_healthy(ctx):
    """Buch-Fetch-Gesundheit (19.06.2026, Lucas: „der Guard muss sowas sehen"). Anlass:
    `fetch_token_book` rief monatelang `/books` (Mehrzahl) → HTTP 400 → JEDER Buch-Fetch
    scheiterte still → 0 Trades seit 17.06 + cache_mid-Phantom, ohne dass die Batterie es sah.
    Der Trigger/Manage schreiben jetzt wm_book_health.json {attempts, transport_fail, ok}.
    Hier: Versuche>0 aber 0 echte Bücher = Endpoint/Netz tot → ERROR (Transport-Fehler) bzw.
    WARN (alles leer/dünn). Macht den stillen Totalausfall sofort sichtbar."""
    bh = _lazy(D.file("wm_book_health.json", "liga_book_health.json").name)
    if not isinstance(bh, dict):
        return None                       # nie gelaufen / keine Daten → kein Signal
    att = bh.get("attempts") or 0
    ok  = bh.get("ok") or 0
    tf  = bh.get("transport_fail") or 0
    if att <= 0 or ok > 0:
        return None                       # gesund (mind. ein echtes Buch) oder nichts geprüft
    # att>0 und ok==0 → kein einziges echtes Buch
    if tf > 0:
        sev = "error"
        msg = (f"Buch-Fetch TOT: 0/{att} echte Bücher, {tf} Transport-Fehler "
               f"(HTTP/Netz) — CLOB-Endpoint prüfen (war Root-Cause des 17.06-Trade-Stopps)")
    else:
        sev = "warn"
        msg = (f"Buch-Fetch: 0/{att} Bücher, alle leer/einseitig — evtl. zu dünn/zu früh, "
               f"aber falls dauerhaft: Endpoint/Token-Format prüfen")
    return _chk("book_fetch_healthy", "Polymarket-Orderbuch erreichbar", sev, [msg],
                "Ohne echtes Buch wird JEDER Trade übersprungen (REQUIRE_BOOK) und jede "
                "Bewertung fällt auf cache_mid. wm_book_health.json aus Trigger/Manage.")


@integrity_check
def check_entry_priced_at_ask(ctx):
    """Entry-Mid-Phantom (18.06.2026, Lucas — „Handicap-Phantom"): eine OFFENE Auto-Position
    OHNE entryAsk wurde zum MITTELPREIS eingebucht statt zum gezahlten Ask → P&L-Baseline zu
    niedrig, „Gewinn" überzeichnet (ESP-SAU AH −3.5 „+10%" war real ~flat). Forward gefixt
    (Spread-Gate + REQUIRE_BOOK_FOR_ENTRY → Ask oder skip). Dieser Guard ist ein REGRESSIONS-
    Melder: nur Positionen ab ENTRY_ASK_GUARD_SINCE (= nach der Härtung) zählen — der bekannte
    Alt-Bestand davor ist bewusst stumm (läuft aus, Exit über Bid + cache_mid-Veto gesichert)."""
    fails = []
    for b in ctx.auto_bets:
        st = (b.get("status") or "").lower()
        if st in ("sold", "resolved") or b.get("soldAt") or b.get("resolved"):
            continue
        placed = (b.get("placedAt") or "")[:10]
        if not placed or placed < ENTRY_ASK_GUARD_SINCE:
            continue                       # Alt-Bestand vor der Härtung → stumm
        if b.get("entryAsk") is None:
            fails.append(f"{b.get('homeId')}-{b.get('awayId')} {b.get('market','')} "
                         f"({placed}): entryAsk fehlt — NEUER Mid-Entry, Spread-Gate umgangen")
    return _chk("entry_priced_at_ask", "Neue Entries am Ask eingebucht (nicht Mid)",
                "warn", fails,
                f"Regressions-Melder ab {ENTRY_ASK_GUARD_SINCE}: ein neuer Entry ohne entryAsk "
                "heißt das Spread-Gate (REQUIRE_BOOK_FOR_ENTRY) wurde umgangen. Alt-Positionen "
                "davor sind bewusst stumm (bekannt, laufen aus).")


@integrity_check
def check_profit_sell_real(ctx):
    """NEU 17.06.2026 (Geld-Bug): Eine Profit-Mitnahme muss REAL sein — der
    Verkaufspreis muss über dem Einstieg liegen. Anlass: USA-TUR „BTTS Nein" wurde
    am MITTELPREIS bewertet (Mid +10%), real war's am Bid −4% (Kauf 43¢ / Verkauf 41¢).
    Fängt die Spread-Phantom-Klasse aus den gespeicherten Trades. Bewertung läuft jetzt
    am Bid + Profit-Sell-Veto in manage_wm_poly_positions; dieser Guard macht Regressionen
    sichtbar."""
    fails = []
    for b in ctx.auto_bets:
        if (b.get("status") or "").lower() != "sold":
            continue
        rsn = (b.get("sellReason") or "").lower()
        is_profit = ("profit" in rsn) or ("konvergiert" in rsn) or ("age-decay" in rsn)
        sp, ent = b.get("sellPrice"), b.get("polyPrice")
        if (is_profit and isinstance(sp, (int, float)) and isinstance(ent, (int, float))
                and sp <= ent):
            fails.append(f"{b.get('home')}-{b.get('away')} {b.get('market','')}: "
                         f"Profit-Sell {sp:.3f} ≤ Entry {ent:.3f} (Spread-Phantom)")
    return _chk("profit_sell_real", "Profit-Sell ist real (Verkauf > Einstieg)", "warn", fails,
                "Mid-Gewinn der beim echten Bid ein Verlust ist. Fix: Bewertung am Bid "
                "(fetch_token_book) + Profit-Sell-Veto.")


@integrity_check
def check_ah_btts_position_priced(ctx):
    """NEU 16.06.2026 (Geld-Bug): Offene AH/BTTS-Auto-Bets müssen über ihren EXAKTEN
    Token im Preis-Cache bewertbar sein. Anlass: USA-AUS „AH Heim -1.5" hatte keinen
    Moneyline-Preis-Key → wurde mit der Heimsieg-Quote (0.615) statt dem AH-Token
    (0.345) bewertet → Schein-Profit +80% → fälschlich auto-verkauft. Jetzt bewertet
    manage_wm_poly_positions über den Token; dieser Guard macht sichtbar, wenn ein
    offener AH/BTTS-Bet NICHT im Cache auflösbar ist (Auto-Sell würde blind laufen)."""
    # Alle bekannten Token im Preis-Cache sammeln (AH-Yes + BTTS Ja/Nein)
    known = set()
    for fx in (ctx.poly_all or []):
        for e in (fx.get("ah_edges") or []):
            toks = e.get("tokens") or []
            if toks:
                known.add(toks[0])
        for t in (fx.get("poly_btts_tokens") or []):
            known.add(t)
    if not known:
        return _chk("ah_btts_position_priced", "AH/BTTS-Positionen bewertbar", "warn", [],
                    "Preis-Cache hat noch keine AH/BTTS-Token (erster Fetch ausstehend).")
    fails = []
    for b in ctx.auto_bets:
        mkt = b.get("market", "") or ""
        if (b.get("status") or "").lower() != "placed":
            continue
        if not (mkt.startswith("AH ") or mkt.startswith("Beide Teams treffen")):
            continue
        tok = b.get("tokenId") or ""
        if tok not in known:
            fails.append(f"{b.get('homeId')}-{b.get('awayId')} {mkt}: Token nicht im "
                         f"Preis-Cache — Auto-Sell kann nicht korrekt bewerten")
    return _chk("ah_btts_position_priced", "AH/BTTS-Positionen über Token bewertbar", "warn", fails,
                "manage_wm_poly_positions bewertet AH/BTTS über den Token. Fehlt er im "
                "Cache → kein Sell (sicher), aber Position hängt. fetch_wm_poly_prices prüfen.")


@integrity_check
def check_ah_ladder_coverage(ctx):
    """Bepreiste, anstehende Spiele sollten eine ahLadder haben — sonst der AH-'klappt-
    nie'-Bug (ahLadder wurde nie ins gespeicherte Odds-Entry kopiert, 13.06.2026).
    Nur Spiele mit 1X2-Odds + Anpfiff in den nächsten 5 Tagen (kein Rauschen)."""
    fails = []
    horizon = ctx.now + timedelta(days=5)
    for _g, fx in ctx.fixtures:
        mk = ctx.mk(fx)
        od = ctx.odds.get(mk) or {}
        if not od.get("hw"):
            continue
        try:
            dt = datetime.fromisoformat(str(fx.get("kickoff")).replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            continue
        if ctx.now <= dt <= horizon and not od.get("ahLadder"):
            fails.append(f"{mk}: bepreist + Anpfiff nah, aber keine ahLadder")
    return _chk("ah_ladder_coverage", "AH-Leiter bei nahen bepreisten Spielen", "warn", fails,
                "ahLadder fehlte → AH-Picks fielen durchs Raster (Mismatches ohne AH).")


@integrity_check
def check_finished_has_stats(ctx):
    """Beendete Spiele sollten result.stats (echte Match-xG) haben — sonst fehlt dem
    Prozess-Lernen (verdient/Pech) die Datenbasis (14.06.2026)."""
    fails = []
    for _g, fx in ctx.fixtures:
        r = fx.get("result") or {}
        if str(r.get("status") or "").upper() in _FINISHED and not r.get("stats"):
            fails.append(f"{ctx.mk(fx)}: beendet, aber keine result.stats (xG)")
    return _chk("finished_has_stats", "Beendete Spiele haben Match-Stats (xG)", "warn", fails,
                "Ohne Match-xG lernt der Bayesian-Loop nur aus Glück/Pech, nicht aus dem Prozess.")


@integrity_check
def check_soft_book_history(ctx):
    """Die Odds-History muss Soft-Book-Snapshots (bk='public') enthalten — sonst kann
    lead_lag_bias NIE feuern (nur Pinnacle → Sharp-Money-Conviction strukturell tot,
    13.06.2026). Erst ab genug History relevant."""
    hist = ctx.history if isinstance(ctx.history, dict) else {}
    total = sum(len(v) for v in hist.values() if isinstance(v, list))
    if total < 20:
        return None   # zu wenig History für ein Urteil
    public = sum(1 for v in hist.values() if isinstance(v, list)
                 for s in v if isinstance(s, dict) and s.get("bk") == "public")
    fails = []
    if public == 0:
        fails.append(f"0 'public'-Snapshots in {total} History-Einträgen → lead_lag kann nie feuern")
    return _chk("soft_book_history", "Soft-Book-Snapshots in Odds-History", "warn", fails,
                "Ohne Soft-Book-Zeitreihe ist die Sharp-Money-Conviction-Familie tot.")


@integrity_check
def check_ah_edge_sane(ctx):
    """FIX 15.06.2026: AH-Handicap-Edges (Poly-Spreads vs Pinnacle-AH-Leiter) müssen
    plausibel sein. Ein echter Edge ist klein (wenige pp); ein Riesen-Edge ist fast
    sicher ein Datenfehler — v.a. der MIRROR-Bug (Poly listet z.B. ENG-PAN als PAN-ENG
    → Spread der falschen Seite vs fair der richtigen → Phantom 30–56pp). Macht solche
    Edges SICHTBAR im 🛡️-Panel. Der Auto-Trader blockt sie zusätzlich via AH_MAX_EDGE_PP."""
    CAP = 12.0
    fails = []
    for fx in (ctx.poly_all or []):
        for e in (fx.get("ah_edges") or []):
            edge = e.get("edge")
            poly = e.get("poly")
            # Settled/degenerierte Märkte (Spiel gelaufen → poly ~0/1) sind nur ein
            # Resolution-Artefakt, kein echtes Edge-Signal → nicht als Phantom werten.
            # (Trader blockt sie eh via Entry-Price/Timing.) Nur Anomalien in normaler
            # Preis-Range (z.B. Mirror: poly 0.04 vs fair 0.35) sollen rot werden.
            if not isinstance(poly, (int, float)) or poly <= 0.02 or poly >= 0.98:
                continue
            if isinstance(edge, (int, float)) and abs(edge) > CAP:
                fails.append(f"{fx.get('homeId')}-{fx.get('awayId')}: AH {e.get('side')} "
                             f"{e.get('line')} Edge {edge:+.1f}pp (poly {poly} / "
                             f"fair {e.get('fair')}) — Phantom/Mirror-Verdacht")
    return _chk("ah_edge_sane", "AH-Handicap-Edges plausibel (kein Mirror)", "warn", fails,
                "fetch_wm_poly_prices: poly_ah_by_team team-ID-geschlüsselt (mirror-immun). "
                "Riesen-Edge = falsche Seite/Daten. Auto-Trader blockt via AH_MAX_EDGE_PP.")


@integrity_check
def check_btts_edge_sane(ctx):
    """NEU 15.06.2026 (BTTS-Auto-Trade verdrahtet): Die BTTS-Edges (Poly poly_btts/
    poly_btts_no vs de-viggte Pinnacle-Baseline) müssen plausibel sein. Ein echter
    Edge ist klein; ein Riesen-Edge ist fast sicher ein Datenfehler (z.B. fehlender/
    vertauschter Pinnacle-bttsY-Wert oder ein settled-Markt). Macht das im 🛡️-Panel
    SICHTBAR. Der Auto-Trader blockt zusätzlich via BTTS_MAX_EDGE_PP."""
    CAP = 12.0
    fails = []
    for fx in (ctx.poly_all or []):
        for side, ekey, pkey in (("Ja", "edge_btts", "poly_btts"),
                                  ("Nein", "edge_btts_no", "poly_btts_no")):
            edge = fx.get(ekey)
            poly = fx.get(pkey)
            # Settled/degeneriert (Spiel gelaufen → poly ~0/1) = Resolution-Artefakt,
            # kein echtes Edge-Signal → überspringen (wie AH).
            if not isinstance(poly, (int, float)) or poly <= 0.02 or poly >= 0.98:
                continue
            if isinstance(edge, (int, float)) and abs(edge) > CAP:
                fails.append(f"{fx.get('homeId')}-{fx.get('awayId')}: BTTS {side} "
                             f"Edge {edge:+.1f}pp (poly {poly} / fair "
                             f"{fx.get('fair_btts' if side=='Ja' else 'fair_btts_no')}) "
                             f"— Datenfehler-Verdacht")
    return _chk("btts_edge_sane", "BTTS-Edges plausibel", "warn", fails,
                "fetch_wm_poly_prices: fair_btts aus de-viggter Pinnacle-bttsY/N. "
                "Riesen-Edge = Daten kaputt. Auto-Trader blockt via BTTS_MAX_EDGE_PP.")


STREAKS_STALE_H = 30.0

@integrity_check
def check_streaks_fresh(ctx):
    """NEU 29.06.2026 (Lucas: „seit gestern keine Serien-Änderungen"): Das Serien-File muss frisch
    sein UND das aktuelle Schema tragen (ratePct aus compute_streaks). Alt-Schema oder stale =
    compute_streaks lief nicht / die Fetcher haben die neuen Sequenzen nicht geschrieben. Genau der
    Fall, der die Serien-Seite veraltet aussehen liess. Content-Feature → WARN. Dataset-aware."""
    data = ctx.streaks or {}
    if not data:
        return _chk("streaks_fresh", "Serien frisch + aktuelles Schema", "warn",
                    ["Serien-File fehlt/leer — compute_streaks lief nicht?"],
                    "compute_streaks.py nach fetch_wm_form/_corners laufen lassen.")
    fails = []
    gen = (data.get("_meta") or {}).get("generatedAt")
    if gen:
        try:
            t = datetime.fromisoformat(str(gen).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            age_h = (ctx.now - t).total_seconds() / 3600
            if age_h > STREAKS_STALE_H:
                fails.append(f"Serien {age_h:.0f}h alt (> {STREAKS_STALE_H:.0f}h) — compute_streaks-Lauf prüfen.")
        except Exception:
            pass
    streaks = data.get("streaks") or []
    if streaks and not any(isinstance(s, dict) and "ratePct" in s for s in streaks):
        fails.append("Serien im ALT-Schema (kein ratePct/Matchup) — fetch_wm_form/_corners + "
                     "compute_streaks neu laufen lassen (Schema-stale erzwingt den Re-Fetch).")
    return _chk("streaks_fresh", "Serien frisch + aktuelles Schema", "warn", fails,
                "compute_streaks schreibt {wm_,liga_,mls_}streaks.json mit ratePct/venue/next/signalInfo.")


LIVE_SCAN_STALE_MIN = 90


@integrity_check
def check_live_scan_laeuft(ctx):
    """NEU 31.08.2026: laeuft der Poly-Live-Scan ueberhaupt?

    Gemessen ueber die Commit-Historie 26.-31.08.: der Live-Scan erreichte **8 bis 29%** seiner
    Soll-Laeufe, mit Luecken von drei bis zwoelf Stunden — sechs Tage lang, ohne dass irgendwo
    etwas rot wurde. Auf derselben Maschine liegen Betfair-Radar und Global-Scan bei ~100%; der
    Runner war nie das Problem, der lang haltende Loop war es.

    Warum die Datei und nicht die Daten: `poly_money_broad_live.json` steht auch dann still,
    wenn schlicht kein Spiel laeuft — ein Alters-Guard darauf wuerde jede ruhige Nacht anschlagen.
    `health/<slug>.json` dagegen schreibt run_health bei JEDEM Lauf (`if: always()`), auch wenn
    es nichts zu committen gab. Sie beantwortet damit genau die Frage, die sechs Tage lang
    niemand gestellt hat: ist der Job ueberhaupt gestartet.

    Ein Guard im Live-Job selbst kann das nicht leisten — ein Lauf, der nie startet, schreibt
    nichts ([[project_card_link_zwei_brueche]]: eine Warnung mit Vorbedingung ist erst dann eine
    Warnung, wenn die Vorbedingung eintritt). Deshalb sitzt er hier, in einer Batterie, die aus
    anderen Workflows heraus laeuft."""
    fname = "health/poly-live-scan.json"
    data = _lazy(fname)
    if fname in _LAZY_FAILED:
        return _chk("live_scan_laeuft", "Poly-Live-Scan taktet", "warn",
                    [f"❔ {fname} nicht lesbar — Live-Scan-Takt UNBEKANNT, nicht gruen."],
                    "run_health.py schreibt sie am Ende jedes Live-Scan-Laufs.")
    ts = (data or {}).get("updatedAt")
    if not ts:
        return _chk("live_scan_laeuft", "Poly-Live-Scan taktet", "warn",
                    [f"{fname} fehlt/ohne updatedAt — der Live-Scan hat noch nie gemeldet."],
                    "Erster Lauf schreibt sie an; danach ist Schweigen ein Befund.")
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        alter_min = (ctx.now - t).total_seconds() / 60
    except Exception:
        return _chk("live_scan_laeuft", "Poly-Live-Scan taktet", "warn",
                    [f"❔ updatedAt unlesbar ({ts!r}) — Takt UNBEKANNT."], "")
    fails = []
    if alter_min > LIVE_SCAN_STALE_MIN:
        fails.append(f"Letzter Live-Scan vor {alter_min/60:.1f}h (Takt: 15 Min) — der Job "
                     f"startet nicht. Runner belegt? Workflow deaktiviert?")
    return _chk("live_scan_laeuft", "Poly-Live-Scan taktet", "error", fails,
                f"Erwartet alle 15 Min; Alarm ab {LIVE_SCAN_STALE_MIN} Min. Live-Preise sind die "
                f"Schluss-Referenz fuer den CLV — fehlen sie, misst der Nordstern nicht.")


# 01.09.2026 (Lucas: „damit ich aktiv drauf aufmerksam werde … und tracken wir da alles, damit
# wir wissen ob's funktioniert?"). Ein Push-Kanal ist die eine Sorte Fehler, die sich als GUTE
# Nachricht tarnt: bleibt er stumm, sieht das aus wie „gerade nichts los" — und genau so sah der
# Live-Scan sechs Tage lang aus. Deshalb wird nicht geprueft, ob Nachrichten kommen (das darf
# ruhig tagelang nichts sein), sondern ob es zu einem gepushten Spiel spaeter auch ein ERGEBNIS
# gibt. Ein Buch, das nur waechst und nie abrechnet, ist kein Buch.
KILLER_PUSH_OFFEN_MAX_H = 48


# 01.09.2026 (Lucas: „poly taucht da mmn nie aktiv auf?"). Antwort war: die Holder-Anteile werden
# nur fuer Maerkte <=3h vor Anpfiff geholt, die Konjunktion latcht bei 22% ihrer Zeilen frueher.
# Seither gibt es ein Vor-Fenster (3-8h) mit eigenem, fussball-priorisiertem Budget, dessen Ergebnis
# in poly_money_upcoming.json landet. Dieser Guard prueft, ob dort tatsaechlich Anteile ANKOMMEN —
# „eingebaut" ist nicht „feuert" ([[project_betfair_norm_league_basis]]).
VOR_ANTEILE_MIN = 1     # mindestens so viele Vor-Maerkte muessen shares tragen, wenn es welche gibt


@integrity_check
def check_poly_vorfenster(ctx):
    """Kommen im Vor-Fenster wirklich Geld-Anteile an?

    Die Datei traegt Maerkte bis 120h vor Anpfiff; nur die im Vor-Fenster (3-8h) bekommen einen
    Holder-Call. Sind dort Maerkte, aber KEINER mit `shares`, ist das Budget nicht angekommen —
    dann faellt die Poly-Bedingung der Konjunktion still wieder aus, so wie monatelang zuvor.
    Keine Maerkte im Fenster = ruhige Stunde, kein Fehler."""
    fname = "poly_money_upcoming.json"
    data = _lazy(fname)
    if fname in _LAZY_FAILED:
        return _chk("poly_vorfenster", "Poly-Vorfenster liefert Anteile", "warn",
                    [f"❔ {fname} nicht lesbar — ob Anteile ankommen, ist UNBEKANNT."], "")
    if not isinstance(data, dict) or not data:
        return _chk("poly_vorfenster", "Poly-Vorfenster liefert Anteile", "warn",
                    [f"❔ {fname} fehlt/leer — nicht unterscheidbar von „gerade nichts im Fenster\"."],
                    "poly_money_broad.py schreibt sie bei jedem Lauf.")
    im_fenster, mit_anteilen = 0, 0
    for v in data.values():
        if not isinstance(v, dict):
            continue
        h = v.get("hoursToKickoff")
        if not isinstance(h, (int, float)) or not (3.0 < h <= 8.0):
            continue
        im_fenster += 1
        if v.get("shares"):
            mit_anteilen += 1
    fails = []
    if im_fenster >= 5 and mit_anteilen < VOR_ANTEILE_MIN:
        fails.append(f"{im_fenster} Maerkte im Vor-Fenster (3-8h), aber KEINER mit Geld-Anteilen — "
                     f"das Vor-Budget kommt nicht an. Die Poly-Bedingung der Konjunktion faellt "
                     f"damit still aus.")
    return _chk("poly_vorfenster", "Poly-Vorfenster liefert Anteile", "error", fails,
                f"{mit_anteilen} von {im_fenster} Vor-Maerkten mit Anteilen. Leeres Fenster ist "
                f"kein Fehler; Maerkte ohne einen einzigen Anteil schon.")


@integrity_check
def check_killer_push_buch(ctx):
    """Das Schattenbuch des Trades-Pushes muss abrechnen, nicht nur sammeln.

    `killer_push_ledger.json` haelt fest, was WIRKLICH in den Channel ging — zum Preis, der in
    der Nachricht stand (`pushPreis`), nicht zum Haltepreis der Flaeche. Zwei Arten, wie das
    still kaputtgeht:
      · Die Abrechnung findet den Treffer nicht (Markt-/ID-Schreibweise driftet gegen
        `betfair_track_results`) → Zeilen bleiben ewig „offen".
      · `pushPreis` fehlt → die Zeile zaehlt nie in die Bilanz, das Buch sieht kleiner aus als
        es ist und niemand merkt es.
    Fehlt die Datei ganz, ist das KEIN Fehler: solange nie ein Stufe-1-Treffer im Fenster lag,
    gibt es nichts zu schreiben. Dann ❔, nie gruen und nie rot."""
    fname = "killer_push_ledger.json"
    rows = _lazy(fname)
    if fname in _LAZY_FAILED:
        return _chk("killer_push_buch", "Trades-Push fuehrt sein Buch", "warn",
                    [f"❔ {fname} nicht lesbar — ob der Push-Track stimmt, ist UNBEKANNT."],
                    "killer_push.py schreibt sie bei jedem Lauf.")
    if rows is None:
        return _chk("killer_push_buch", "Trades-Push fuehrt sein Buch", "warn",
                    [f"❔ {fname} fehlt — noch nie ein Stufe-1-Treffer gepusht, oder der Job "
                     f"laeuft nicht. Nicht unterscheidbar, also nicht gruen."],
                    "Erster Push legt sie an.")
    if not isinstance(rows, list):
        return _chk("killer_push_buch", "Trades-Push fuehrt sein Buch", "error",
                    [f"{fname} ist kein Array."], "")
    fails = []
    ohne_preis = [r for r in rows if isinstance(r, dict) and r.get("pushPreis") in (None, 0)]
    if ohne_preis:
        fails.append(f"{len(ohne_preis)} Zeile(n) ohne pushPreis — sie zaehlen nie in die "
                     f"Bilanz, das Buch waere still zu klein.")
    lange_offen = []
    for r in rows:
        if not isinstance(r, dict) or r.get("status") != "offen":
            continue
        ko = r.get("kickoff")
        try:
            t = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if (ctx.now - t).total_seconds() / 3600 > KILLER_PUSH_OFFEN_MAX_H:
            lange_offen.append(r.get("k"))
    if lange_offen:
        fails.append(f"{len(lange_offen)} gepushte Zeile(n) seit ueber {KILLER_PUSH_OFFEN_MAX_H}h "
                     f"angepfiffen und immer noch 'offen' (z.B. {lange_offen[0]}) — die "
                     f"Abrechnung findet sie nicht in betfair_track_results.")
    return _chk("killer_push_buch", "Trades-Push fuehrt sein Buch", "error", fails,
                "Was gepusht wurde, muss abgerechnet werden — sonst weiss niemand, ob der "
                "Channel traegt. Gerechnet wird zum pushPreis, nicht zum Haltepreis.")


@integrity_check
def check_card_link_alive(ctx):
    """NEU 31.08.2026: der Terminal-Kartenlink (`betfair_card_link.json`) muss ANKOMMEN.

    Am 31.08. stand die Datei auf nGames 12 / nLinked 0 — und sah damit aus wie ein ruhiger Tag
    ohne Top-5-Spiele. Tatsaechlich war der Fixture-Index nur nach dem Team-PAAR geschluesselt;
    `event_key` ist reihenfolge-unabhaengig, also ueberschrieb das pickfreie Rueckspiel im
    Fruehjahr das heutige Spiel. Der Bruch war seit dem 26.08. unsichtbar, weil die Zahl, die
    ihn zeigt (`nCandidates`), nur im Log stand.

    Regel: lagen Boersen-Spiele am selben Tag wie unsere Cards und wurde KEINES verlinkt, ist
    das ein Bruch, kein leerer Tag. Und wer die Datei nicht lesen kann, meldet ❔ statt gruen
    ([[project_audit_stille_fehler_25_08]] — fehlende Information ist keine Erlaubnis)."""
    fname = "betfair_card_link.json"
    data = _lazy(fname)
    if fname in _LAZY_FAILED:
        return _chk("card_link_alive", "Terminal-Kartenlink kommt an", "warn",
                    [f"❔ {fname} nicht lesbar — Kartenlink UNBEKANNT, nicht gruen."],
                    "Datei pruefen; betfair.yml schreibt sie am Ende des Radar-Laufs.")
    if not data:
        return _chk("card_link_alive", "Terminal-Kartenlink kommt an", "warn",
                    [f"{fname} fehlt/leer — betfair_card_link.py lief nicht."],
                    "Laeuft in .github/workflows/betfair.yml nach dem Konsens-Schritt.")
    cand = data.get("nCandidates")
    linked = data.get("nLinked")
    if cand is None or linked is None:
        return _chk("card_link_alive", "Terminal-Kartenlink kommt an", "warn",
                    ["❔ nCandidates/nLinked fehlen — alte Datei, Aussage UNBEKANNT."],
                    "betfair_card_link.py ab 31.08.2026 schreibt beide Zahlen mit.")
    fails = []
    if cand and not linked:
        fails.append(f"{cand} Boersen-Spiele lagen am selben Tag wie unsere Cards, verlinkt "
                     f"wurde KEINES — Namens-Bruecke oder Fixture-Index gebrochen.")
    return _chk("card_link_alive", "Terminal-Kartenlink kommt an", "error", fails,
                "0 von 0 ist ein ruhiger Tag. 0 von N ist ein Bruch.")


# ── Runner ───────────────────────────────────────────────────────────────────
def run_checks(wm, poly, schedule, venues, lineups=None, now=None,
               auto_bets=None, history=None, streaks=None):
    """Führt die ganze Registry aus. Pure. Ein crashender Check killt den Rest nicht."""
    ctx = IntegrityCtx(wm, poly, schedule, venues, lineups=lineups, now=now,
                       auto_bets=auto_bets, history=history, streaks=streaks)
    out = []
    for fn in INTEGRITY_CHECKS:
        try:
            r = fn(ctx)
            if r:
                out.append(r)
        except Exception as e:
            out.append(_chk(fn.__name__, fn.__name__, "warn",
                            [f"Check-Code-Fehler: {e}"], "Guard selbst gecrasht — bitte prüfen."))
    return out


if __name__ == "__main__":
    import json
    import os
    from datetime import datetime, timezone
    from pathlib import Path
    B = Path(__file__).resolve().parent
    import cocobet_dataset as D
    load = lambda f: json.loads((B / f).read_text(encoding="utf-8")) if (B / f).exists() else {}
    # Dataset-Modus (Single Source: cocobet_dataset): Liga → Guards auf liga-data.json + Ergebnis
    # nach liga_status.json (Liga-Health sichtbar). WM-/Poly-only Guards no-oppen mangels Daten.
    _is_liga = D.is_liga()
    # 13.07.2026 — BUG: hier stand hart `liga-data.json` / `liga_lineups.json` für JEDEN Nicht-WM-
    # Datensatz. Unter COCOBET_DATASET=mls liefen damit ALLE Guards gegen die LIGA-Daten und das
    # Ergebnis landete in liga_status.json. Der MLS-Status war nie echt — und mein neuer
    # Ausfall-Guard meldete „0 Fehler", obwohl die MLS-Verletzungsdaten nachweislich kaputt sind:
    # er hat schlicht die falsche Datei geprüft. Jetzt über cocobet_dataset (D.data_file/D.file),
    # damit jeder Datensatz seine eigenen Daten prüft und in {prefix}_status.json schreibt.
    if _is_liga:
        res = run_checks(load(D.data_file().name), {}, {}, {},
                         lineups=load(D.file("wm_lineups.json", "liga_lineups.json").name))
    else:
        res = run_checks(load("wm2026-data.json"), load("wm_poly_prices.json"),
                         load("wm_venue_schedule.json"), load("wm_venues.json"))
    nfail = sum(1 for c in res if not c["ok"])
    print(f"=== Daten-Integrität ({D.active_dataset().upper()}): {len(res)-nfail}/{len(res)} Checks ok "
          f"({len(INTEGRITY_CHECKS)} Guards registriert) ===\n")
    for c in res:
        icon = "✅" if c["ok"] else ("🔴" if c["severity"] == "error" else "🟡")
        # KEIN "[error]"-Literal im Output (25.06.2026, Lucas): GitHub Actions zog Zeilen mit dem
        # Severity-Wort als „Error:"-Annotation hoch, obwohl die Checks ok waren. Severity = Icon.
        sev = {"error": "ERR", "warn": "warn"}.get(c["severity"], c["severity"])
        print(f"{icon} {c['label']}: {c['nFail']} Fehler ({sev})")
        for f in c["failures"][:6]:
            print(f"     · {f}")
    if _is_liga:
        # 13.07.2026: war hart liga_status.json → MLS überschrieb den LIGA-Status mit MLS-Ergebnissen
        # (bzw. umgekehrt) und mls_status.json wurde nie aktualisiert. Jetzt datensatz-eigen.
        _status = D.file("wm_status.json", "liga_status.json")
        _status.write_text(json.dumps(
            {"checks": res, "nFail": nfail,
             "generatedAt": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n💾 {_status.name} geschrieben ({nfail} Warnungen/Fehler).")
