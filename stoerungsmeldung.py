#!/usr/bin/env python3
"""
stoerungsmeldung.py — einmal am Tag: was nicht stimmt. Sonst Stille.
====================================================================
🔴 20.09.2026 (Lucas: „ich weiß dann nicht, funktioniert das eigentlich, was tracken wir da …
es ist halt sehr viel aktuell").

Die Antwort darauf gibt es längst. Drei Guard-Batterien laufen 57 Prüfungen und schreiben sie
nach `uebersicht_integrity.json`, `poly_status.json` und `betfair_status.json` — und sonst
nirgendwohin. Am Abend des 20.09. meldeten sie zusammen 14 Dinge, darunter ein Spiel, das seit
95 Stunden nicht abgerechnet werden konnte.

Fehlerklasse: ein Messgerät, dessen Zeiger niemand ansieht. Das Instrument war nicht das
Problem, die Zustellung war es.

## Was diese Meldung anders macht als eine weitere Fläche

1. **Sie kommt nur, wenn etwas kaputt ist.** Eine tägliche „alles gut"-Nachricht wird nach einer
   Woche weggewischt, und dann auch die, in der etwas steht.
2. **Sie sortiert nach Geld, nicht nach Reihenfolge der Dateien.** Ein Spiel, das nicht
   abgerechnet werden kann, steht über einer Taktung, die zu langsam ist.
3. **Ein veraltetes Messgerät ist selbst ein Befund.** Wäre eine Batterie zwölf Stunden alt und
   die Meldung bliebe still, hiesse „keine Nachricht" fälschlich „alles in Ordnung" — genau die
   Klasse, die diesen Tag über dreimal zugeschlagen hat (fehlende Information rendert als
   harmloser Default).
4. **Sie fügt keinen Workflow hinzu.** Die Runner sind gesättigt (zwei Workflows liefern über
   Soll, alle anderen 2–7 Läufe am Tag). Sie hängt an einem Lauf, der ohnehin zuverlässig
   fährt, und schickt nur im Zeitfenster und nur einmal je Tag.

REIN/testbar bis auf `main()`: Einstufung, Sortierung, Text und Sende-Entscheidung sind reine
Funktionen.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
# 🔴 21.09.2026 (Lucas: „Wie kann so eine Nachricht aber in public gehen"). Die Meldung vom
# 06:14 UTC stand im oeffentlichen Kanal — Wallet-Adressen, Markt-Keys, der Stand der Buecher.
# `tg_send` faellt ohne gesetzte `TELEGRAM_CHAT_ID` auf die feste oeffentliche Kanal-ID zurueck,
# und dieses Secret ist seit dem 04.08. bewusst leer, damit der oeffentliche Pfad laeuft.
# Fehlerklasse: ein Standard-Empfaenger, der der oeffentliche Kanal ist.
#
# Diese Marke sagt es fuer jeden spaeteren Leser und fuer den Test in
# tests/test_interne_meldungen_bleiben_intern.py: was hier entsteht, geht NUR an den internen
# Kanal. Wer dieses Modul anfasst und `tg_send` einsetzt, faellt dort durch.
NUR_INTERN = True

# 🔴 21.09.2026 (Lucas: „ich merke mir nicht, wo was ist"). Hier stand eine LISTE mit drei
# Namen. Die groesste Batterie im Haus — `wm_data_integrity` mit rund 80 Waechtern — schreibt
# je Datensatz nach `{praefix}_status.json`, und keine davon stand darin. Wer nur die Meldung
# las, sah 3 von 5 Batterien; der Rest war nur auf der Statusseite zu finden, also genau dort,
# wo Lucas nicht taeglich hinsieht. Der Satz unter der Meldung („kommt nichts, ist nichts
# kaputt") war damit nicht wahr.
#
# Mein erster Anlauf war, die Liste zu verlaengern — und er ging daneben: ich trug
# `wm_status.json` hart ein und vergass `mls_status.json`, die genauso eine Batterie ist.
# `tests/test_tote_quellen.py` fing den hartkodierten toten Namen. Den FEHLENDEN haette
# niemand gefangen: eine zu kurze Liste wirft nichts, sie schweigt bloss.
#
# Fehlerklasse: eine Zusammenfassung, die ihre Quellen aufzaehlt statt sie zu finden. Eine
# Liste vergisst immer genau die Datei, die neu ist. Gesucht wird deshalb nach der FORM —
# ein Artefakt mit einer Liste unter `checks` ist eine Batterie, alles andere nicht. Damit
# steht hier kein einziger Datensatz-Name mehr, und die naechste Batterie meldet sich selbst.
# Heute sind es sechs (uebersicht, poly, betfair, liga, mls, wm); `esports_poly_status.json`
# heisst wie eine und traegt nur einen Feed-Stand. Dass die WM-Batterie seit dem 19.07. steht,
# entscheidet nicht `quellen()`, sondern `sammeln()` — sie landet unter „ruht".
STAND_FILE = "stoerungsmeldung_stand.json"

# Die einzige Batterie ohne `_status`-Namen. Alles andere wird gefunden.
EXTRA_QUELLEN = ("uebersicht_integrity.json",)
QUELL_MUSTER = "*_status.json"


def ist_batterie(inhalt) -> bool:
    """Traegt dieses Artefakt eine Pruefbatterie? REIN.

    Am Inhalt, nicht am Namen: eine Liste unter `checks`. `esports_poly_status.json` heisst
    wie eine Batterie und traegt einen Feed-Stand. Ein Name kann luegen, das Schema nicht.
    """
    return isinstance(inhalt, dict) and isinstance(inhalt.get("checks"), list)


_UNLESBAR = object()


def _laden(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return _UNLESBAR


def quellen(basis=None) -> dict:
    """{Dateiname: Inhalt} aller Batterien unter `basis`. Gefunden, nicht gelistet.

    Eine Datei, die es gibt und die sich NICHT lesen laesst, bleibt drin — `sammeln` meldet
    sie als „blind". Sie stillschweigend zu uebergehen waere der Fehler, gegen den die ganze
    Meldung gebaut ist: fehlende Information, die als harmloser Default rendert.
    """
    basis = Path(basis) if basis else BASE
    namen = set(EXTRA_QUELLEN) | {p.name for p in basis.glob(QUELL_MUSTER)}
    raus = {}
    for n in sorted(namen):
        p = basis / n
        if not p.exists():
            continue
        d = _laden(p)
        if d is _UNLESBAR:
            raus[n] = None
        elif ist_batterie(d):
            raus[n] = d
    return raus

# Ab wann ist eine Batterie selbst ein Befund? update-liga laeuft dreimal taeglich, die
# Poly- und Betfair-Batterien oefter — 14 h laesst einen ausgefallenen Lauf durch und faengt
# einen ausgefallenen Tag.
ALT_H = 14.0
# Ab wann ruht eine Batterie, statt blind zu sein? 14 Tage — dieselbe Grenze wie auf der
# Statusseite (`_ST_RUHEND_H`). Lang genug, dass kein Wochenende und keine Cron-Luecke
# hineinfaellt; kurz genug, dass ein echter Ausfall vorher als „blind" auffaellt.
RUHEND_H = 14.0 * 24
# Das Fenster, in dem gesendet wird (UTC). Frueh genug, dass der Tag noch etwas bringt.
FENSTER = (6, 10)

# ── Was ist Geld? ────────────────────────────────────────────────────────────
#
# Die Reihenfolge ist die ganze Leistung dieser Meldung. Sie steht deshalb hier als LISTE und
# nicht als Stichwortsuche: „Geld" ist eine Entscheidung, keine Zeichenkette.
#
# Ein neuer Check landet per Default unter „Messung". Damit das kein stiller Default wird,
# prueft `tests/test_stoerungsmeldung.py`, dass jeder Check mit einem geldnahen Wort im Namen
# entweder hier oder in GEPRUEFT_KEIN_GELD steht — ein neuer Check zwingt also zu einer
# Entscheidung, statt unten zu verschwinden.
GELD = {
    # offene Positionen und ihr Ausgang
    "offene wette hat den anpfiff ueberlebt",
    "geschlossen heisst belegt",
    "positionswert ist frisch",
    # was nicht abgerechnet werden kann, faellt aus jeder Bilanz
    "ergebnisse kommen an",
    "settlement_alive",
    "resolutions_match_open_keys",
    "direct_bets_settling",
    "track_record_grading_sane",
    # wer handelt, schreibt sofort — fehlt der Beleg, ist die Bilanz unvollstaendig
    "jeder push hat seinen beleg",
    "public_push_buch",
    "trades_push_buch",
    "shortlist_tracker_writes",
    # 21.09.2026: eine ruhende Order, die als Position gebucht ist, steht mit Geld im Buch,
    # das nie bewegt wurde — genau der Toluca-Fall.
    "ruhende_order_ist_keine_position",
    # 21.09.2026: eine Zeile, die abgerechnet wurde, ohne dass die Wallet sich bewegt hat —
    # das ist Geld im Buch, das nie geflossen ist (Toluca, -5,00 $ fuer eine Order, die die
    # Kasse nie beruehrt hat).
    "wette_hat_die_kasse_beruehrt",
    # 21.09.2026: ohne Odds-Zugang gibt es keinen Anker, und ohne Anker entscheidet die
    # Zweitmeinung nichts mehr. Der Schluessel war einen Tag lang tot, ohne dass es auffiel.
    "odds_zugang_lebt",
    # blind zum Geld gesetzt
    "poly-deckung: money-scan gegen liga-fetcher",
    "money map: die poly-seite gehoert zum spiel",
    "preis-signal-deckung: entstehen picks blind zum markt?",
    # ohne frische Aufloesungen rechnet niemand etwas ab
    "resolutions_fresh",
    "close_resolution_stamped",
    "track_record_fresh",

    # ── 21.09.2026: die Waechter aus liga_status/mls_status, eingestuft ────────────────
    # Der Massstab: kostet ein falscher Wert HIER Geld, das bewegt oder gebucht wird?
    # Alles andere — Abdeckung, Lernen, Anzeige — ist Messung. Die Geld-Sektion bleibt nur
    # glaubwuerdig, solange sie kurz ist.
    #
    # was nicht abrechnet, faellt aus der Bilanz:
    "absagen_abgerechnet", "picks_resolved", "played_games_resolved",
    "result_score_final", "resolved_status_propagated", "ko_settlement_ninety_min",
    # was den Preis bestimmt, zu dem gekauft/verkauft wurde:
    "entry_priced_at_ask", "profit_sell_real", "ah_btts_position_priced",
    # eine Wette auf die falsche Seite oder aus einem Platzhalter:
    "homeaway_consistent", "no_ghost_picks", "no_phantom_odds", "odds_sane",
    "opening_plausible", "btts_not_templated_traded", "ah_edge_sane", "btts_edge_sane",
    # ein Edge gegen veraltete oder falsche Preise:
    "edge_consistent", "odds_freshness", "steam_longshot_ceiling",
    # offene Position, die niemand mehr sieht oder schliessen kann:
    "autobet_kickoff", "live_scan_laeuft",
    # Belege und Buecher, ohne die die Bilanz unvollstaendig ist:
    "wallet_ledger_growing", "killer_push_buch", "data_not_wiped", "inputs_readable",
    "run_health",
    # 21.09.2026, zweiter Durchgang: ohne frische Preise/Feeds handelt der scharfe Pfad blind.
    "prices_fresh", "close_feed_fresh", "feed_populated", "consensus_fresh",
    "wallet_track_fresh", "stale_live_markets", "no_stuck_pending", "live_minute_sane",
    "artefakte sind lesbar", "datenbau ist nicht stehengeblieben",
    "poly-markt gehoert zur selben mannschaft",
}
GEPRUEFT_KEIN_GELD = {
    # angesehen und bewusst NICHT als Geld eingestuft — mit dem Grund daneben.
    "poly-kachel gibt sich nicht als kanal-bilanz aus",   # Anzeige, keine Wette
    "jede stake-wette traegt ihre sportart",              # Zuordnung, kein Ausgang
    "buecher-punktestand: die zahl stimmt mit ihrer begruendung ueberein",
    "stake-auffaelligkeiten tragen ihr gemessenes urteil",
    "signal-bilanz: schadet ein signal belegt?",          # Messung ueber Messungen
    "fade-unter: haelt die kontrollgruppe?",              # laeuft mit, sendet nie
    "clv-urteil passt zur clv-zahl",
    "money map meldet ihre luecken",                      # meldet selbst, kein Ausfall
    "freigabe-grund ist aus den daten ableitbar",
    "shortlist_nachschub",
    "proven_wallets_profitable",
    # 21.09.2026: eine Annahme ueber die Daten, kein Ausgang. Er sagt, ob der Markt-Stempel-
    # Nachtrag noch tragen darf — schlaegt er an, rechnet nichts falsch ab, sondern der
    # Nachtrag gehoert geprueft, bevor wieder abgerechnet wird.
    "buendel_cond_stabil",
    "grosses_geld_bleibt_im_feed",
    "direction_covers_money",

    # ── 21.09.2026: angesehen und BEWUSST nicht als Geld eingestuft ────────────────────
    # Abdeckung und Vollstaendigkeit — fehlt etwas, wird weniger gemessen, nicht falsch
    # abgerechnet:
    "clv_card_coverage", "trade_clv_coverage", "signal_coverage", "soft_book_history",
    "soft_opening_captured", "ah_ladder_coverage", "liga_market_coverage",
    "ko_apif_coverage", "finished_has_stats", "history_snaps_plausible",
    "injuries_plausible", "lineup_present", "standings_built", "ko_odds_present",
    "ko_bracket_consistency", "liga_leagues_populated", "liga_odds_round_sane",
    "poly_vorfenster", "buecher_punkte", "smartmoney_sane", "smartmoney_cluster_sane",
    "streaks_fresh", "card_link_alive", "betfair_ledger",
    # Zuordnung und Zeitstempel — wichtig, aber kein Ausgang:
    "kickoff_present", "time_matches_kickoff", "schedule_date", "venue_resolves",
    "venue_matches_schedule", "closing_prematch", "closing_capture_fresh",
    "closing_capture_alive", "odds_field_plausible", "public_consensus",
    "public_is_multibook", "ou_pinnacle_anchored", "ou_anchor_source",
    # Lernen und Einstufung — beeinflusst kuenftige Picks, bewegt heute kein Geld:
    "learning_loop_alive", "engine_version_stamped", "freshness_learning_coupled",
    "bet_move_fresh", "reverser_demoted", "pick_safe_variant", "safer_line_applied",
    "card_only_not_in_trade", "no_duplicate_picks", "steam_lag_no_dupes",
    "vorregistrierung", "betfair_liefert", "poly_global_liefert", "pinn_anker",
    # 22.09.2026: kam mit dem ersten Pipeline-Lauf nach dem Bau von `check_stake_sammelt`
    # herein — die Rollout-Luecke, nicht ein neuer Waechter. Der Stake-Radar sammelt fremde
    # Grosswetten fuers Lernen; bleibt er stehen, wird weniger gemessen, es rechnet aber nichts
    # falsch ab. Dass sein WORKFLOW nicht mehr laeuft, meldet ohnehin `run_health` unter Geld.
    "stake_sammelt",

    # 21.09.2026, dritter Durchgang: kam mit `mls_status.json` dazu, als die Quellen nicht mehr
    # aufgezaehlt, sondern gefunden werden. Eine stehende Poly-Flaeche starrt einen Eingang aus
    # — Radar, E-Sport-Tab, Geld-Karte —, sie schreibt aber keine falsche Zahl ins Buch. Der
    # Guard ist selbst als `warn` und ausdruecklich nicht-blockierend gebaut.
    "poly_surfaces_alive",

    # 21.09.2026, zweiter Durchgang: Messung ueber die Messung, Anzeige, Abdeckung.
    "accuracy_backtest_fresh", "consensus_anchor_coverage", "direction_present",
    "history_mkv_present", "league_norm_usable", "odds_and_shape_sane",
    "public_eval_alive", "split_vollstaendig",
    "betfair-buckets tragen ihr urteil mit",
    "jede quelle der uebersicht traegt einen zeitstempel",
    "public-stille ist erklaert", "schattenbuch fuellt sich",
    "serien werden nach seltenheit rangiert, nicht nach laenge",
    "serien-buch zeigt beide buecher",
    "serien-seltenheit folgt aus der liga-basis, die danebensteht",
    "serien-seltenheit rechnet mit der rate, die danebensteht",
    "stake-spielklasse: tabelle vollstaendig, richtungen getrennt",
    "stumme signale: wer hat nie gefeuert?",
    "takt: cron gegen gemessene laeufe",
}
GELD_WORTE = ("wette", "position", "order", "push", "beleg", "ergebnis", "bilanz",
              "geld", "money", "settle", "resolution", "track_record", "deckung")


def _zeit(wert):
    if not wert:
        return None
    try:
        t = datetime.fromisoformat(str(wert).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def alter_h(wert, jetzt=None):
    t = _zeit(wert)
    if t is None:
        return None
    return round(((jetzt or datetime.now(timezone.utc)) - t).total_seconds() / 3600.0, 1)


def schluessel(check: dict) -> str:
    return str(check.get("id") or check.get("label") or "").strip().lower()


def ist_geld(check: dict) -> bool:
    return schluessel(check) in GELD


def braucht_entscheidung(check: dict) -> bool:
    """Ein Check, der weder als Geld noch als geprueft dasteht. REIN.

    🔴 21.09.2026. Hier stand zusaetzlich `return any(w in k for w in GELD_WORTE)` —
    eine Einstufung war also nur noetig, wenn der NAME geldnah klang. `absagen_abgerechnet`
    traegt keines dieser Woerter und ist trotzdem Geld: ein Spiel, das nie abrechnet, faellt
    aus der Bilanz. Beim Mutationstest liess sich der Eintrag ersatzlos entfernen, ohne dass
    etwas rot wurde.

    Der Kopf dieser Datei sagt es selbst: „Geld ist eine Entscheidung, keine Zeichenkette."
    Die Wortliste blieb trotzdem das Tor. Jetzt braucht JEDER Check eine Entscheidung; die
    Wortliste entscheidet nur noch, in welchen Eimer ein noch nicht eingestufter faellt.
    Fehlerklasse: ein Wächter, der nur die Faelle einfordert, die er ohnehin erkennt.
    """
    return schluessel(check) not in GELD and schluessel(check) not in GEPRUEFT_KEIN_GELD


def sammeln(artefakte: dict, jetzt=None) -> dict:
    """{quelle: inhalt} -> {"geld": [...], "messung": [...], "offen": [...], "blind": [...]}.

    REIN. `blind` sind Batterien, die zu alt sind, um etwas zu behaupten — sie sind selbst ein
    Befund und nie ein stilles Gruen.
    """
    geld, messung, offen, blind, ruht = [], [], [], [], []
    for quelle, inhalt in sorted((artefakte or {}).items()):
        if not isinstance(inhalt, dict):
            blind.append({"quelle": quelle, "grund": "nicht lesbar"})
            continue
        a = alter_h(inhalt.get("generatedAt"), jetzt)
        if a is None:
            blind.append({"quelle": quelle, "grund": "ohne Zeitstempel"})
            continue
        if a > RUHEND_H:
            # 🔴 21.09.2026 (Lucas: „Der WM Mist ist vorbei, interessiert niemand"). Eine
            # Batterie, deren Datensatz ausgelaufen ist, friert ein und bleibt lesbar. Als
            # „blind" gemeldet stuende sie ab dann JEDEN Tag in der Nachricht, mit derselben
            # Zeile, und zwar fuer immer. Blind heisst „diese Pruefung sagt gerade nichts, und
            # das ist ein Problem"; hier ist kein Problem, hier ist eine Saison vorbei.
            #
            # Der Anlass ist die WM: 57 echte Waechter in `wm_status.json`, eingefroren am
            # 19.07. Sie wird gefunden wie jede andere Batterie — das ist richtig so, sie IST
            # eine — und erst hier, am Alter, als ruhend erkannt. Der naechste Fall kommt
            # bestimmt: `mls_status.json` friert ein, sobald die Saison endet.
            # Dieselbe Unterscheidung wie auf der Statusseite (`_stFeedStufe`) und in
            # `freigabe.py` (`status: "ruht"`). Ein ruhender Datensatz wird still uebergangen.
            # Fehlerklasse: ein abgeschlossener Zustand, der als Stoerung gemeldet wird.
            ruht.append({"quelle": quelle, "alterH": a})
            continue
        if a > ALT_H:
            blind.append({"quelle": quelle, "grund": "%.0f h alt" % a, "alterH": a})
            continue
        for c in (inhalt.get("checks") or []):
            if not isinstance(c, dict) or c.get("ok"):
                continue
            zeile = {"quelle": quelle, "label": c.get("label") or c.get("id"),
                     "severity": c.get("severity"), "nFail": c.get("nFail") or 0,
                     "failures": [str(f) for f in (c.get("failures") or [])][:2]}
            if braucht_entscheidung(c):
                offen.append(zeile)
            elif ist_geld(c):
                geld.append(zeile)
            else:
                messung.append(zeile)
    schwer = lambda z: (0 if z.get("severity") == "error" else 1, -(z.get("nFail") or 0))
    return {"geld": sorted(falten(geld), key=schwer), "messung": sorted(falten(messung), key=schwer),
            "offen": falten(offen), "blind": blind, "ruht": ruht}


def falten(rows) -> list:
    """Dieselbe Stoerung aus mehreren Batterien ist EINE Stoerung. REIN.

    🔴 21.09.2026, direkt nach dem Umbau auf `quellen()`. Mit liga UND mls in der Meldung stand
    „Stake Radar: seit 337 h kein Lauf" zweimal da, und „Poly-Live-Scan taktet" auch — einmal
    mit 3,7 h, einmal mit 3,4 h. Beide Batterien pruefen denselben globalen Workflow; es ist
    EIN Vorfall, und wer ihn zweimal liest, liest die Meldung beim naechsten Mal gar nicht.
    Fehlerklasse: eine Zaehlung, die die Quellen zaehlt statt die Vorfaelle.

    `nFail` wird deshalb auch nicht summiert, sondern gemaxt: derselbe Ausfall, zweimal
    gesehen, ist nicht doppelt so schlimm.
    """
    raus, index = [], {}
    for z in rows or []:
        k = str(z.get("label") or "")
        t = index.get(k)
        if t is None:
            t = dict(z)
            t["quellen"] = [z.get("quelle")]
            t["failures"] = list(z.get("failures") or [])
            index[k] = t
            raus.append(t)
            continue
        if z.get("quelle") not in t["quellen"]:
            t["quellen"].append(z.get("quelle"))
        t["nFail"] = max(t.get("nFail") or 0, z.get("nFail") or 0)
        if z.get("severity") == "error":
            t["severity"] = "error"
        for f in z.get("failures") or []:
            if f not in t["failures"] and len(t["failures"]) < 2:
                t["failures"].append(f)
    return raus


def _quellen_kurz(zeile) -> str:
    """„liga, mls" — aber nur, wenn es mehr als eine ist. Bei einer sagt der Name nichts."""
    qs = [q for q in (zeile.get("quellen") or []) if q]
    if len(qs) < 2:
        return ""
    kurz = [str(q).replace("_status.json", "").replace("_integrity.json", "").replace(".json", "")
            for q in qs]
    return " (%s)" % ", ".join(kurz)


def _kurz(text: str, n: int = 150) -> str:
    t = " ".join(str(text).split())
    return t if len(t) <= n else t[:n - 1] + "…"


def baue_meldung(befund: dict, jetzt=None) -> str:
    """Der Text. REIN. Leer = nichts zu melden, dann wird nicht gesendet."""
    b = befund or {}
    if not (b.get("geld") or b.get("messung") or b.get("blind") or b.get("offen")):
        return ""
    jetzt = jetzt or datetime.now(timezone.utc)
    z = ["🩺 <b>Störungsmeldung</b> · %s" % jetzt.strftime("%d.%m. %H:%M UTC")]
    if b.get("blind"):
        z.append("")
        z.append("⚫️ <b>Blind</b> — diese Prüfung sagt gerade gar nichts:")
        for x in b["blind"]:
            z.append("   · %s (%s)" % (x["quelle"], x["grund"]))
    # Geld steht vollstaendig da — das ist der Zweck. Die Messung wird gekappt: eine Nachricht,
    # die man scrollen muss, wird wie eine Fläche behandelt, also weggewischt.
    for name, titel, zeichen, deckel in (("geld", "Kostet Geld", "🔴", None),
                                         ("offen", "Nicht eingestuft", "🟠", None),
                                         ("messung", "Messung", "🟡", 4)):
        rows = b.get(name) or []
        if not rows:
            continue
        z.append("")
        z.append("%s <b>%s</b>" % (zeichen, titel))
        zeigen = rows if deckel is None else rows[:deckel]
        for x in zeigen:
            z.append("   · <b>%s</b>%s" % (_kurz(x["label"], 70), _quellen_kurz(x)))
            for f in (x.get("failures") or [])[:1 if name == "messung" else 2]:
                z.append("       %s" % _kurz(f))
        if deckel is not None and len(rows) > deckel:
            z.append("   · <i>und %d weitere</i>" % (len(rows) - deckel))
    z.append("")
    # Eine ruhende Batterie wird NICHT als Stoerung gemeldet — aber auch nicht verschwiegen.
    # Eine Luecke, die sich durch Zeitablauf selbst erledigt, hinterlaesst sonst keine Spur,
    # und in drei Monaten weiss niemand mehr, dass diese Pruefung existiert.
    if b.get("ruht"):
        z.append("<i>Ruht: %s — wird nicht geprüft, ist auch kein Fehler.</i>"
                 % ", ".join("%s (%.0f Tage)" % (x["quelle"], x["alterH"] / 24)
                             for x in b["ruht"]))
    z.append("<i>Nur Störungen. Kommt nichts, ist nichts kaputt — außer die Prüfung selbst "
             "steht oben unter „Blind\".</i>")
    return "\n".join(z)


def soll_senden(stand: dict, jetzt=None, fenster=FENSTER) -> bool:
    """Einmal am Tag, im Fenster. REIN.

    Kein eigener Workflow: die Runner sind gesaettigt. Diese Meldung haengt an einem Lauf, der
    ohnehin oft faehrt, und entscheidet selbst, ob sie dran ist.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    if not (fenster[0] <= jetzt.hour < fenster[1]):
        return False
    return str((stand or {}).get("zuletzt") or "") != jetzt.date().isoformat()


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    probe = "--probe" in argv
    jetzt = datetime.now(timezone.utc)

    artefakte = quellen()
    befund = sammeln(artefakte, jetzt)
    text = baue_meldung(befund, jetzt)

    stand_p = BASE / STAND_FILE
    try:
        stand = json.loads(stand_p.read_text(encoding="utf-8"))
    except Exception:
        stand = {}

    print("=== stoerungsmeldung ===")
    print("  Geld %d · Messung %d · nicht eingestuft %d · blind %d"
          % (len(befund["geld"]), len(befund["messung"]),
             len(befund["offen"]), len(befund["blind"])))
    if probe:
        print(text or "  (nichts zu melden)")
        return 0
    if not text:
        print("  nichts zu melden — keine Nachricht.")
        return 0
    if not soll_senden(stand, jetzt):
        print("  ausserhalb des Fensters oder heute schon gesendet.")
        return 0
    try:
        from telegram_bot import tg_send_ops
    except Exception as e:                       # noqa: BLE001
        print("  Telegram nicht verfuegbar: %s" % e)
        return 0
    if tg_send_ops(text):
        stand["zuletzt"] = jetzt.date().isoformat()
        stand["geld"] = len(befund["geld"])
        stand_p.write_text(json.dumps(stand, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  gesendet.")
    else:
        print("  Versand fehlgeschlagen — Stand NICHT gesetzt, naechster Lauf versucht es erneut.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
