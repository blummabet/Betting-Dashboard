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
# 19.09.2026 (Lucas: „ich glaube, wir haben einfach noch nicht die optimale Einstellung … da
# muessten wir rumtuefteln und das dann rueckrechnen"). Das ging nicht, und der Grund ist nicht
# die Rechnung, sondern der Ausschnitt: wir sehen nur die Alarme, die DURCHKOMMEN. Der Trichter
# vom 19.09. — roh 69, gesendet 3, davon 43 gestorben an der 80-%-Einseitigkeit. Wie die 43
# ausgegangen waeren, weiss niemand, und darum laesst sich 0,80 nur blind senken, nie begruendet
# verschieben. Ab jetzt wird jeder Beinahe-Treffer mitgeschrieben und wie ein echter Push
# abgerechnet — gesendet wird er NIE.
SCHATTEN_FILE = "betfair_public_schatten.json"
SCHATTEN_KEEP = 4000

# -- 📉 Kursrutsch (19.09.2026, Lucas) --------------------------------------------------------
# „Alerts wo wir die Schwelle etwas senken, aber dafuer nur schicken, wenn die Quote auch
# wirklich sinkt ... wirklich Spiele wo die Quote nachweislich gesunken ist um 10 % oder so.
# Das dann doch ein starkes Signal mmn."
#
# Sein Einwand war, das 15-Minuten-Fenster sei zu grob. Gemessen an 605 Vor-Anpfiff-Reihen
# (18.651 Einzelschritte) stimmt das nicht:
#   * Abstand zwischen zwei Staenden: Median 15,0 min (10 %/90 %: 13,7 / 15,2)
#   * Rutsch >= 10 % in EINEM Schritt:            46 von 18.651 = 0,2 %
#   * Rutsch >= 10 % ueber das GANZE Fenster:     45 von 605 Reihen = 7,4 %
# Der Rutsch passiert also fast nie innerhalb eines Fensters, er sammelt sich ueber Stunden an.
# Deshalb misst dieser Alarm die KUMULATIVE Bewegung seit dem ersten Sehen (entryOdd aus
# betfair_track_state.json) statt Schritt gegen Schritt. Genau daran ist `dir` (in/out/flat) als
# Signal gescheitert: betfair_direction.classify vergleicht Schritt gegen Schritt und sieht damit
# nur jene 0,2 %.
# Zu spaet kommen wir davon nicht: nach einem >= 10-%-Sprung laeuft der Preis bis Anpfiff im
# Median +-0,0 % weiter (28 % rutschen weiter, 26 % springen zurueck), und der Sprung passiert im
# Median 95 Minuten vor Anpfiff.
#
# WAS GEMESSEN IST, und was nicht. 30.918 Ledger-Zeilen, Rendite am SCHLUSSkurs gerechnet (dem
# kuerzesten Preis -- wer mitten im Fenster einsteigt, bekommt mehr):
#   * Rutsch >= 10 % UND Geld NICHT konzentriert:  n=203, ROI +18,3 % [UG +2,3, OG +34,4]
#   * Rutsch >= 10 % UND Geld konzentriert:        n=675, ROI  -2,6 % [-8,7, +3,5]
# Der Fund haelt die Zeitprobe (erste Haelfte +15,5 %, zweite +21,2 %), ueberlebt das Streichen
# der drei groessten Gewinner (+11,4 %) und den Cluster-Bootstrap ueber Spiele (UG +2,0 %).
# ABER: 22 Schnitte angeschaut, und ein Nullmodell ohne jeden Quoten-Effekt liefert in 39 % der
# Buecher mindestens ein „belegt tragend" -- p = 0,125. Kein Beweis, sondern der beste Kandidat
# aus einem Tag Messen. Deshalb NUR Trades, nie Public, und jeder Alarm wird abgerechnet
# (Messung `betfair-kursrutsch` im Register).
RUTSCH_MIN_FALL    = float(os.environ.get("BF_RUTSCH_MIN_FALL")  or 0.10)
# 19.09.2026, NACHGEMESSEN und korrigiert: der erste Entwurf verlangte einen frischen Zufluss von
# der halben Geldschwelle. Das haette das Signal erschlagen -- von den 203 gemessenen Faellen
# hatten nur 19 ueberhaupt einen frischen Zufluss ueber 2.000 EUR, 184 keinen. Der Effekt lebt
# also GENAU dort, wo kein Geld nachkommt (ROI ohne Zufluss +20,0 % [UG +2,8] gegen +18,3 %
# insgesamt) -- das ist die Aussage des Signals, nicht sein Nebeneffekt. Statt einer Geldschwelle
# steht hier deshalb nur noch ein Liquiditaetsboden, damit kein toter Markt alarmiert.
# Der Boden ist GERATEN, nicht gemessen: das gematchte Volumen steht erst seit heute im Ledger
# (mktVol, s. betfair_track_record.capture). Er wandert in jede Ledger-Zeile mit und wird in
# sechs Wochen kalibriert statt weiter geschaetzt.
RUTSCH_MIN_VOL     = float(os.environ.get("BF_RUTSCH_MIN_VOL")   or 5000.0)
RUTSCH_MAX_SHARE   = float(os.environ.get("BF_RUTSCH_MAX_SHARE") or 0.65)
RUTSCH_SEEN_FILE   = "betfair_rutsch_seen.json"
RUTSCH_LEDGER_FILE = "betfair_rutsch_ledger.json"
RUTSCH_LEDGER_KEEP = 800
RUTSCH_STATE_FILE  = "betfair_track_state.json"   # dort steht entryOdd, beim ERSTEN Sehen eingefroren
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


# Bis wann ein Halbzeit-Markt ueberhaupt noch spielbar ist. Nachspielzeit der ersten Haelfte
# meldet Betfair weiter als 45 — die Pause trennt `is_ht`, nicht die Minute.
HT_MAX_MIN = int(os.environ.get("BF_HT_MAX_MIN") or 45)


def tore_gefallen(m):
    """Tore im laufenden Spiel — oder None, wenn der Feed sie nicht meldet. REIN/testbar."""
    li = m.get("liveInfo") or {}
    a, b = li.get("goal_v1"), li.get("goal_v2")
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return None
    if isinstance(a, bool) or isinstance(b, bool):
        return None
    return int(a) + int(b)


def _linie_aus_name(name):
    """Die Torlinie aus dem Marktnamen („First Half Goals 1.5" -> 1.5). None, wenn keine drin
    steht (z. B. „Half Time" — ein 1X2-Markt hat keine Linie). REIN/testbar."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*$", str(name or "").strip())
    try:
        return float(m.group(1)) if m else None
    except (TypeError, ValueError):
        return None


def ht_linie_offen(m, market_name) -> bool:
    """Ist dieser HZ-Tormarkt noch UNENTSCHIEDEN? REIN/testbar.

    🔴 12.09.2026 (Lucas: „aja und die push kam grad in public … nur dort ist grad pause oder so
    und die tore alle schon ewig her").

    Gemeldet wurde „HZ Over/Under 1.5 · Over 1.5 @1,47 · 85 % · €24,1K gematcht" fuer
    Al Ahli - Al-Hazm. Im Feed stand zu dem Zeitpunkt: **Minute 33, Stand 2:1 — also drei Tore,
    alle in der ersten Halbzeit.** „Over 1.5" war damit laengst gewonnen, und die €20,5K auf
    Over sind Geld von VOR den Toren. Die Karte las eine abgeschlossene Tatsache als Fluss.

    `ht_fenster_offen` liess es durch, und zwar voellig korrekt: Minute 33 <= 45, `is_ht` false.
    Das Fenster war offen — der MARKT war es nicht.

    Das ist dieselbe Familie wie der Fix vom 05.09. („die Information war da und wurde nicht
    gefragt"), eine Ebene tiefer: damals fehlte die Minute, jetzt der SPIELSTAND. Beide standen
    die ganze Zeit in `liveInfo`.

    Solange das HZ-Fenster offen ist, sind die gefallenen Tore per Definition Halbzeit-Tore —
    deshalb reicht der aktuelle Stand. Nach der Pause greift ohnehin `ht_fenster_offen`.

    Ein Markt OHNE Linie (`Half Time`, also HZ-1X2) kann so nicht entschieden werden; dort gilt
    weiter nur das Fenster. Und ein Feed ohne Torangabe sperrt NICHT — sonst faellt der ganze
    Kanal aus, sobald ein Anbieter das Feld weglaesst; die Minute deckt diesen Fall schon ab.
    """
    linie = _linie_aus_name(market_name)
    if linie is None:
        return True                       # kein Tormarkt -> hier nichts zu entscheiden
    tore = tore_gefallen(m)
    if tore is None:
        return True                       # keine Torangabe -> das Fenster entscheidet allein
    # Entschieden ist der Markt erst, wenn „Over" nicht mehr verlieren KANN, also `tore > linie`.
    # Bei X,5-Linien ist das dasselbe wie `tore < linie` (Tore sind ganzzahlig) — bei einer
    # ganzzahligen Linie NICHT: „Over 2" bei 2 Toren ist Push, und ein drittes Tor entscheidet
    # noch. `<` haette dort zu frueh gesperrt. Aufgefallen erst beim Provozieren, weil der
    # Unterschied an X,5-Linien unsichtbar ist.
    return tore <= linie


def ht_fenster_offen(m) -> bool:
    """Laeuft die erste Halbzeit noch? REIN/testbar.

    05.09.2026 (Lucas): „🔵 Betfair Halftime Flow · HZ Over/Under 1.5 · Over 1.5 @1.74 …
    da ist grad 50 min. Und kommt als Push in public."

    Der Markt war zu dem Zeitpunkt **entschieden**. `ht_alert` feuerte in der 20., in der
    PAUSE und in der 70. exakt gleich — die Spielminute stand die ganze Zeit in
    `liveInfo.time`, dazu ein eigenes `is_ht`-Flag, und beides wurde nirgends gelesen.
    Gemessen im Bestand: **36 von 36** Live-Spielen jenseits der 46. fuehren weiter
    HZ-Maerkte mit Volumen im Feed — die Quelle raeumt sie nicht ab, also muessen wir es.

    Das ist die Familie „fehlende Information ist keine Erlaubnis", nur andersherum: die
    Information war da und wurde nicht gefragt.

    Vor Anpfiff (keine Live-Minute) ist der HZ-Markt regulaer spielbar — dort gibt es kein
    Fenster zu schliessen.
    """
    li = m.get("liveInfo") or {}
    if li.get("finished"):
        return False
    if li.get("is_ht"):
        return False                      # Pause: die erste Haelfte ist vorbei
    t = li.get("time")
    if t is None:
        return True                       # vor Anpfiff
    try:
        return float(t) <= HT_MAX_MIN
    except (TypeError, ValueError):
        return False                      # unlesbare Minute ist keine Erlaubnis


def _ht_one(m, market_name, top_thr=HT_TOP_EUR, rest_thr=HT_REST_EUR):
    """Ein einzelner HZ-Markt (HZ-1X2 oder Über/Unter 1,5 HZ1): ≥ tier-Schwelle UND ≥85 % einseitig."""
    if not ht_fenster_offen(m):
        return None                       # erste Haelfte vorbei -> der Markt ist entschieden
    if not ht_linie_offen(m, market_name):
        return None                       # Linie schon gerissen -> s. ht_linie_offen
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
    # 05.09.2026: derselbe Fenster-Check wie in `_ht_one` — ein „HZ > FT"-Vergleich auf einem
    # entschiedenen HZ-Markt vergleicht eine Tatsache mit einer Wahrscheinlichkeit.
    if not ht_fenster_offen(m):
        return None
    for name in FIX_HT_MARKETS:
        mk = mkts.get(name)
        if not mk:
            continue
        if not ht_linie_offen(m, name):
            continue                      # entschiedener Tormarkt — s. ht_linie_offen
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


def einstiegsquoten(state) -> dict:
    """{(matchId, markt): (entryOdd, favToken)} aus dem Track-Zustand. REIN/testbar.

    betfair_track_record.capture friert `entryOdd` beim ERSTEN Sehen ein und setzt es bei einem
    Favoritenwechsel zurueck -- ein Rutsch kann hier also nie ein Seitenwechsel sein. Der Lauf
    schreibt diesen Zustand VOR den Alerts (betfair.yml: Track-Record Schritt 137, Alerts 205),
    die Datei ist beim Lesen frisch."""
    out = {}
    for mid, pend in ((state or {}).get("pending") or {}).items():
        for markt, sig in ((pend or {}).get("signals") or {}).items():
            eo = (sig or {}).get("entryOdd")
            if isinstance(eo, (int, float)) and eo > 1:
                out[(str(mid), markt)] = (float(eo), (sig or {}).get("fav"))
    return out


def _fav_token(markt, runner, home, away):
    """Runner-Name -> dasselbe Kuerzel, das betfair_track_record.capture ablegt.

    Import erst hier drin, damit ein Alarm-Lauf nicht am Import des Track-Moduls haengt. Faellt
    er, wird die Seite NICHT geprueft und der Alarm unterbleibt -- lieber kein Push als einer
    auf der falschen Seite."""
    try:
        from betfair_track_record import fav_token
    except Exception:
        return None
    try:
        return fav_token(markt, runner, home, away)
    except Exception:
        return None


def rutsch_alert(m, einstieg, min_fall=RUTSCH_MIN_FALL, max_share=RUTSCH_MAX_SHARE,
                 min_vol=RUTSCH_MIN_VOL):
    """Szenario 4 (19.09.2026, Lucas): keine Geldschwelle, dafuer muss die Quote nachweislich
    gefallen sein -- und das Geld darf NICHT einseitig liegen. REIN/testbar.

    Geprueft wird JEDER Markt des Spiels; gemeldet wird der mit dem groessten Rutsch. Herleitung
    samt Zahlen oben bei RUTSCH_MIN_FALL."""
    li = m.get("liveInfo") or {}
    # 🔴 19.09.2026, eine Stunde nach dem Bau (Lucas, zum ersten Alarm, den er gesehen hat):
    #   „Angers 2.28 → 1.50 (−34,2 %), ⚽ läuft … Der Kursrutsch weil 1:0 gemacht mmn.
    #    Dann wertlos."
    # Er hat recht, und der Fehler ist groesser als die eine Karte: ALLE DREI Alarme des ersten
    # Abends kamen aus laufenden Spielen (live 22., 63., 44. Minute). Gemessen habe ich aber
    # ausschliesslich VOR-ANPFIFF-Daten — betfair_track_record.capture aktualisiert die Signale
    # nur `if _is_prematch(m, now)`; entryOdd ist die erste Vor-Anpfiff-Quote, `odd` die letzte.
    # Die n=203 mit ROI +18,3 % beschreiben also eine Population, in der dieser Alarm gar nicht
    # gefeuert hat.
    # Live ist der Rutsch auch inhaltlich etwas anderes: nach einem Tor preist der Markt neu, die
    # Quote faellt WEGEN des Ereignisses, nicht davor. Das ist Nachlaufen, kein Vorlauf — dieselbe
    # Einsicht, die `_dir_event_jump` und `geld_ist_altbestand` fuer die anderen Szenarien schon
    # festhalten.
    # Eine Regel auf einer Population zu fahren, die man nicht gemessen hat, ist kein Testlauf,
    # sondern Raten mit Beleg-Anstrich.
    if li.get("finished") or li.get("is_ht") or li.get("time") is not None:
        return None
    ko = m.get("kickoff")
    if not ko:
        return None                  # ohne Anpfiff kein Beleg, dass es davor ist
    # (streng genommen faengt das except unten denselben Fall — die Zeile steht als Absicht da,
    #  nicht als Zusicherung; eine Mutation an ihr aendert nichts und faengt folglich kein Test.)
    try:
        if datetime.fromisoformat(str(ko).replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            return None              # Anpfiff vorbei, auch wenn der Feed noch keine Minute zeigt
    except (ValueError, TypeError):
        return None                  # unlesbarer Anpfiff heisst: wir wissen es nicht, also nicht senden
    mid = str(m.get("matchId"))
    bester = None
    for markt, mk in ((m.get("markets") or {}).items()):
        eo = einstieg.get((mid, markt))
        if not eo:
            continue                      # ohne Einstiegsquote kein Rutsch -- er wird nicht geschaetzt
        entry_odd, fav = eo[0], eo[1]
        lead_name, lead_share, lead_odd = _market_lead(m, markt)
        if not isinstance(lead_odd, (int, float)) or lead_odd < MIN_LEAD_ODD:
            continue
        if not isinstance(lead_share, (int, float)) or lead_share >= max_share:
            continue                      # einseitiges Geld ist die gemessen SCHLECHTERE Haelfte (-2,6 %)
        # Dieselbe Seite? capture legt `fav` als Kuerzel ab; ohne diese Pruefung vergleicht man
        # zwei verschiedene Runner. Beim ersten Trockenlauf war GENAU das der einzige Kandidat:
        # Kilmarnock jetzt @1.45 gegen einen Einstieg von 1.79, der Hearts gehoerte -- "-19 %",
        # die es nie gab.
        if fav is not None and _fav_token(markt, lead_name, m.get("home"), m.get("away")) != fav:
            continue
        vol = sum((r.get("vol") or 0.0) for r in (mk.get("runners") or []))
        if vol < min_vol:
            continue                      # toter Markt: ein Preis ohne Gegenpartei ist kein Signal
        fall = (entry_odd - lead_odd) / entry_odd
        if fall < min_fall:
            continue
        if bester is None or fall > bester["fall"]:
            bester = {"scenario": "rutsch", "matchId": mid, "value": vol,
                      "home": m.get("home"), "away": m.get("away"), "league": m.get("league"),
                      "flag": _flag(m), "market": markt, "total": vol, "tier": tier_of(m),
                      "kickoff": m.get("kickoff"), "live": li,
                      "leadName": lead_name, "leadShare": lead_share, "leadOdd": lead_odd,
                      "entryOdd": entry_odd, "fall": fall,
                      "onLeader": _money_on_leader(m, lead_name)}
    return bester


def _lade_json(name, default):
    """Ein Artefakt lesen. FEHLT es -> default. Ist es DA und unlesbar -> ebenfalls default,
    aber mit einer Zeile im Log.

    19.09.2026: an genau dieser Unterscheidung hing der Poly-Ausfall -- 15 Artefakte mit
    Git-Konfliktmarkern wurden von `except Exception: return default` still zu {}, und drei
    Stunden lang sendete niemand etwas. Hier ist der Default vertretbar (ohne Einstiegsquoten
    entfaellt nur der Rutsch-Alarm), still darf er nicht sein."""
    try:
        with open(name, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        print("  \U0001f534 %s ist DA, aber nicht lesbar (%s) -- der Kursrutsch-Alarm entfaellt "
              "diesen Lauf, statt auf leeren Daten zu urteilen" % (name, type(e).__name__))
        return default


def _log_rutsch(a) -> None:
    """Jeden gesendeten Kursrutsch ins eigene Buch. Ein Kandidat ohne Abrechnung waere eine
    Behauptung -- und bei p = 0,125 ist das Abrechnen der halbe Sinn der Sache."""
    try:
        led = json.load(open(RUTSCH_LEDGER_FILE, encoding="utf-8"))
        if not isinstance(led, list):
            led = []
    except Exception:
        led = []
    k = "rutsch:%s:%s" % (a.get("matchId"), a.get("market"))
    if any(e.get("k") == k for e in led):
        return
    led.append({"k": k, "matchId": a.get("matchId"), "scenario": "rutsch",
                "market": a.get("market"), "league": a.get("league"),
                "home": a.get("home"), "away": a.get("away"),
                "leadName": a.get("leadName"), "leadOdd": a.get("leadOdd"),
                "entryOdd": a.get("entryOdd"), "fall": round(a.get("fall") or 0.0, 4),
                "leadShare": a.get("leadShare"), "value": a.get("value"),
                "mktVol": a.get("total"), "tier": a.get("tier"),
                "sentAt": datetime.now(timezone.utc).isoformat(),
                "status": "pending", "htScore": None,
                "live": {"time": ((a.get("live") or {}).get("time")),
                         "score": [(a.get("live") or {}).get("goal_v1"),
                                   (a.get("live") or {}).get("goal_v2")]}})
    try:
        json.dump(led[-RUTSCH_LEDGER_KEEP:], open(RUTSCH_LEDGER_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=0)
    except Exception as e:
        print("Rutsch-Ledger-Schreibfehler:", e)


def build_rutsch_message(a) -> str:
    """Die Karte. Optisch bewusst unverwechselbar (Lucas: „optisch auch eindeutig damit ich den
    seh") -- kein gelber/blauer/schwarzer Punkt wie die drei bestehenden Szenarien."""
    fall = (a.get("fall") or 0.0) * 100
    st = _flow_status(a)
    t = []
    t.append("\U0001f4c9\U0001f4c9 <b>KURSRUTSCH</b> · der Preis fällt, das Geld folgt (noch) nicht\n")
    t.append("━━━━━━━━━━━━━━\n")
    t.append("<b>%s</b>   <s>%.2f</s> → <b>%.2f</b>   <b>−%.1f %%</b>\n"
             % (_esc(a.get("leadName") or "?"), a.get("entryOdd") or 0.0,
                a.get("leadOdd") or 0.0, fall))
    t.append("%s <b>%s</b> v <b>%s</b>\n<i>%s · %s</i>\n"
             % (a.get("flag") or "", _esc(a.get("home")), _esc(a.get("away")),
                _esc(str(a.get("league"))[:40]), _esc(_short_mk(a.get("market")))))
    if st:
        t.append(st + "\n")
    t.append("\U0001f4b6 <b>%s</b> im Markt gematcht\n" % _euro(a.get("total") or 0.0))
    # abgeschnitten statt gerundet: bei einer Schranke von 65 % darf auf der Karte keine
    # 65 stehen, sonst behauptet die Anzeige genau das, was die Regel ausschliesst.
    t.append("\U0001f9ca Geld <b>nicht</b> einseitig (%d %%) — genau die Hälfte, die gemessen trägt\n"
             % int((a.get("leadShare") or 0.0) * 100))
    t.append("\U0001f52c <i>Testlauf, nur Trades · gemessen +18,3 % (UG +2,3) auf n=203 — "
             "nicht belegt (p=0,13). Jeder dieser Alarme wird abgerechnet.</i>")
    return "".join(t)


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


# 🔴 15.09.2026, zweiter Anlauf (Lucas). Erster Anlauf war zu stumpf und haette einen RICHTIGEN
# Alarm mitgerissen — der Beleg kam von Lucas selbst:
#
#   Public  16:16   HZ Over/Under 0.5 · Over 0.5 @1.51   bei Stand 0:1  → FALSCH, laengst entschieden
#   Trades  16:16   HZ Over/Under 1.5 · Over 1.5 @1.54   bei Stand 0:1  → RICHTIG, Ausgang lebt
#
# Dasselbe Spiel, dieselbe Minute, dasselbe Tor im Zufluss-Fenster. Ein Gate auf „Ereignis im
# Fenster" haette BEIDE verworfen. Das Tor war also nie das Unterscheidungsmerkmal.
#
# Das Merkmal ist die LINIE: Over 0.5 steht bei einem Tor bereits fest, Over 1.5 nicht. Ein Push
# auf einen Ausgang, der schon entschieden ist, ist kein schlechtes Signal — er ist gar keine
# Wette mehr.
#
# Und wieder lag alles vor: `_ou_under_alive` liest seit dem 14.08. genau diese Linie aus dem
# Label und vergleicht sie mit dem echten Stand (`liveInfo.goal_v1/goal_v2`) — aber nur fuer
# UNDER, und nur um eine Drift-Formulierung zu waehlen. Nie, um einen Push zu verhindern.
ENTSCHIEDEN_LEDGER = "betfair_reaktiv_ledger.json"
ENTSCHIEDEN_KEEP = int(os.environ.get("BETFAIR_ENTSCHIEDEN_KEEP") or 500)
_BASIS = os.path.dirname(os.path.abspath(__file__))
# Rueckwaerts-kompatible Namen (das Buch heisst weiter so, damit kein Artefakt umzieht).
REAKTIV_LEDGER = ENTSCHIEDEN_LEDGER
REAKTIV_KEEP = ENTSCHIEDEN_KEEP


def ou_linie(label):
    """Die Ueber/Unter-Linie aus einem Label ("Over 1.5 Goals" -> 1.5). None = keine. REIN."""
    t = str(label or "").lower()
    if "over" not in t and "under" not in t and "über" not in t and "unter" not in t:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", t)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def ist_halbzeit_markt(a) -> bool:
    """Bezieht sich der Markt auf die ERSTE HALBZEIT? REIN."""
    t = (str((a or {}).get("market") or "") + " " + str((a or {}).get("leadLabel") or "")).lower()
    return any(k in t for k in ("hz ", "hz:", "halbzeit", "half time", "half-time", "1st half",
                                "first half", "ht "))


def _tore(a):
    li = (a or {}).get("live") or {}
    g1, g2 = li.get("goal_v1"), li.get("goal_v2")
    if isinstance(g1, int) and isinstance(g2, int):
        return g1 + g2
    return None


def ausgang_schon_entschieden(a):
    """Steht der gepushte Ausgang durch den aktuellen Stand bereits fest? REIN/testbar.

    True  = entschieden (gewonnen ODER verloren) -> es gibt nichts mehr zu wetten
    False = lebt noch
    None  = nicht beurteilbar (kein O/U-Markt, kein Stand) -> im Zweifel durchlassen, ein
            Waechter, der raet, wirft gute Alarme weg
    """
    if not isinstance(a, dict):
        return None
    li = a.get("live") or {}
    hz = ist_halbzeit_markt(a)
    # Eine erste Halbzeit, die vorbei ist, entscheidet JEDEN HZ-Markt — unabhaengig von der Linie.
    if hz:
        t = li.get("time")
        if li.get("finished") or li.get("is_ht") or (isinstance(t, (int, float)) and t > 45):
            return True
    linie = ou_linie(a.get("leadLabel") or a.get("leadName")) 
    if linie is None:
        linie = ou_linie(a.get("market"))
    if linie is None:
        return None
    tore = _tore(a)
    if tore is None:
        return None
    # Bei einem HZ-Markt sind die Tore nur AUSSAGEKRAEFTIG, solange die erste Halbzeit laeuft —
    # und genau dann ist der Live-Stand der Halbzeitstand. Danach hat der Zweig oben schon True
    # zurueckgegeben.
    return tore >= linie


def entschieden_gate(alerts) -> tuple:
    """(durchgelassen, verworfen). REIN/testbar. Nur ein klares True verwirft."""
    durch, raus = [], []
    for a in (alerts or []):
        (raus if ausgang_schon_entschieden(a) is True else durch).append(a)
    return durch, raus


def entschieden_zeile(a, jetzt=None) -> dict:
    """Ein verworfener Fall fuers Buch. REIN/testbar."""
    jetzt = jetzt or datetime.now(timezone.utc)
    li = (a or {}).get("live") or {}
    return {"ts": jetzt.isoformat(), "matchId": str((a or {}).get("matchId") or ""),
            "spiel": "%s v %s" % ((a or {}).get("home") or "?", (a or {}).get("away") or "?"),
            "league": (a or {}).get("league"), "market": (a or {}).get("market"),
            "leadName": (a or {}).get("leadName"), "leadOdd": (a or {}).get("leadOdd"),
            "stand": [li.get("goal_v1"), li.get("goal_v2")], "minute": li.get("time"),
            "inflow": (a or {}).get("inflow"),
            "grund": "Ausgang durch den Spielstand bereits entschieden"}


def entschieden_buch_schreiben(raus, basis, jetzt=None, keep=ENTSCHIEDEN_KEEP) -> int:
    """Verworfene Faelle rollierend mitschreiben. Nie fatal.

    Warum ueberhaupt mitschreiben, wo die Faelle doch wertlos SIND: weil die Zahl etwas ueber die
    Markt-Auswahl weiter oben sagt. Pusht der Radar jede Woche zwanzig entschiedene Ausgaenge,
    liegt der Fehler nicht hier, sondern dort."""
    if not raus:
        return 0
    try:
        from pathlib import Path as _P
        from safe_write import write_json_atomic
        pfad = _P(basis) / ENTSCHIEDEN_LEDGER
        try:
            alt = json.loads(pfad.read_text(encoding="utf-8"))
            zeilen = alt.get("faelle") if isinstance(alt, dict) else None
        except Exception:
            zeilen = None
        zeilen = list(zeilen or [])
        zeilen += [entschieden_zeile(a, jetzt) for a in raus]
        write_json_atomic(pfad, {"updatedAt": (jetzt or datetime.now(timezone.utc)).isoformat(),
                                 "n": len(zeilen[-keep:]), "faelle": zeilen[-keep:]}, indent=1)
        return len(raus)
    except Exception as exc:
        print("  ℹ️  Entschieden-Buch nicht geschrieben: %s" % exc)
        return 0


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
        return msg + _fuehrt_line(a) + _dir_line(a, ou_fade=True) + _draw_inplay_note(a) + altbestand_note(a) + altbestand_note(a)
    tl = "Top-Liga" if a["tier"] == "top" else "Rest-Liga"
    msg = ("🟡 <b>Betfair · Frisches Geld</b> · %s\n" % tl + head
           + "💶 <b>%s</b>: +<b>%s</b> frisch → jetzt <b>%s</b>"
             % (_esc(_short_mk(a["market"])), _euro(a["inflow"]), _euro(a["total"])))
    if a.get("leadName"):
        odd = _lead_odd_txt(a)
        msg += "\nführt: %s (%.0f%%)%s" % (_esc(a["leadName"]), (a.get("leadShare") or 0.0) * 100, odd)
    return msg + _fuehrt_line(a) + _dir_line(a, ou_fade=True) + _draw_inplay_note(a) + altbestand_note(a)


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


def _stand_bekannt(m) -> bool:
    """Steht zum Push-Zeitpunkt ueberhaupt ein Live-Stand zur Verfuegung?"""
    li = m.get("liveInfo") or {}
    return isinstance(li.get("goal_v1"), int) and isinstance(li.get("goal_v2"), int)


def _leader_team(m):
    """Aktuell fuehrende Mannschaft aus dem Live-Stand (None bei Gleichstand/keinem Stand)."""
    li = m.get("liveInfo") or {}
    g1, g2 = li.get("goal_v1"), li.get("goal_v2")
    if not (isinstance(g1, int) and isinstance(g2, int)) or g1 == g2:
        return None
    return m.get("home") if g1 > g2 else m.get("away")


def _money_on_leader(m, lead_name):
    """Reaktives Geld: die Seite mit dem meisten Geld IST die bereits fuehrende Mannschaft
    (Lucas: „1:0 fuehrt und Kohle kommt = eher wertlos"). Greift nur, wenn der Ausgang eine
    Mannschaft ist (Ueber/Unter, BTTS matchen den Team-Namen nicht -> nicht betroffen).

    🔴 12.09.2026 (Lucas: „Team in Fuehrung und dann kommt das trotzdem — meinst du, das ist
    stark positiv?"). Diese Funktion gab **bool** zurueck und warf damit zwei verschiedene Lagen
    in denselben Topf: „steht gleich / liegt zurueck" und „wir kennen den Stand gar nicht".

    Gemessen an den 25 gestempelten Pushs: bei **7** war der Live-Stand unbekannt — alle sieben
    stehen als `onLeader: False` im Buch und damit in der Vergleichsgruppe „nicht auf den
    Fuehrenden". Sie verwaessern genau die Zahl, mit der die Frage beantwortet werden soll.

    Dieselbe Fehlerklasse wie ueberall hier: **fehlende Information darf nicht als harmloser
    Default rendern.** Ab jetzt drei Zustaende — True / False / None.
    """
    if not _stand_bekannt(m):
        return None
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
            + _fuehrt_line(a) + _dir_line(a, ou_fade=trades) + (_draw_inplay_note(a) if trades else "")
            + altbestand_note(a))


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


def schatten_zeile(a, raus, quelle, ht_top, ht_rest, fresh_top, fresh_rest, jetzt=None) -> dict:
    """Ein nicht gesendeter Kandidat als Ledger-Zeile. REIN/testbar.

    Gleiche Form wie eine Zeile in betfair_public_ledger.json, damit betfair_public_eval sie mit
    DERSELBEN settle()-Mechanik abrechnet — ein zweiter Abrechner waere ein zweites Urteil.
    Dazu die Zahlen, an denen die Schwellen haengen: `magnitude` (das Geld, an dem gemessen wird),
    `schwelle` (was es haette sein muessen) und `leadShare`. Ohne diese drei ist die Zeile nur
    die Feststellung, dass etwas rausfiel, und nicht der Beleg, um wie viel."""
    jetzt = jetzt or datetime.now(timezone.utc)
    mag = _lead_magnitude(a)
    thr = _lead_base_thr(a, ht_top, ht_rest, fresh_top, fresh_rest)
    return {"k": "%s:%s:%s" % (a.get("scenario"), a.get("matchId"), a.get("market")),
            "matchId": a.get("matchId"), "scenario": a.get("scenario"), "market": a.get("market"),
            "league": a.get("league"), "home": a.get("home"), "away": a.get("away"),
            "leadName": a.get("leadName"), "leadOdd": a.get("leadOdd"), "value": a.get("value"),
            # sentAt heisst hier „gesehen am" — der Name bleibt, weil settle() danach greift.
            "sentAt": jetzt.isoformat(), "status": "pending", "htScore": None,
            "leadShare": a.get("leadShare"), "leadDir": a.get("leadDir"),
            "onLeader": a.get("onLeader"), "tier": a.get("tier"),
            "magnitude": round(mag, 1), "schwelle": round(thr, 1),
            "anteilSchwelle": (round(mag / thr, 3) if thr else None),
            "raus": raus, "quelle": quelle, "gesendet": False,
            "live": {"time": ((a.get("live") or {}).get("time")),
                     "score": [(a.get("live") or {}).get("goal_v1"),
                               (a.get("live") or {}).get("goal_v2")]}}


def erste_stufe(a, stufen_filter):
    """An welcher Stufe stirbt dieser Alarm zuerst? REIN. None = er hat alle ueberlebt.

    Die REIHENFOLGE ist dieselbe Liste, die auch der Trichter zaehlt — zwei Listen waeren zwei
    Wahrheiten darueber, warum ein Alarm rausfiel."""
    for name, raus in (stufen_filter or []):
        try:
            if raus(a):
                return name
        except Exception:
            continue
    return None


def schatten_buch(roh, gesendet_keys, stufen_filter, alt=None, ht_top=PUB_HT_TOP, ht_rest=PUB_HT_REST,
                  fresh_top=PUB_FRESH_TOP, fresh_rest=PUB_FRESH_REST, quelle="public",
                  jetzt=None, keep=SCHATTEN_KEEP) -> list:
    """Das Schattenbuch um die Beinahe-Treffer dieses Laufs ergaenzen. REIN/testbar.

    Ein Eintrag je scenario:matchId:market, ERSTSICHTUNG gewinnt — der Zustand, in dem der
    Kandidat zum ersten Mal Kandidat war, ist der, ueber den die Schwelle entschieden haette.
    Wird ein Schlusselsatz spaeter doch gesendet, bekommt die Zeile `gesendet: True` statt zu
    verschwinden: sonst faende die Auswertung spaeter einen Beinahe-Treffer, der in Wahrheit ein
    Push war, und zaehlte ihn doppelt."""
    buch = list(alt or [])
    bekannt = {e.get("k"): e for e in buch if isinstance(e, dict)}
    for a in (roh or []):
        k = "%s:%s:%s" % (a.get("scenario"), a.get("matchId"), a.get("market"))
        if k in gesendet_keys:
            if k in bekannt:
                bekannt[k]["gesendet"] = True     # war Beinahe-Treffer, ist jetzt Push
            continue
        if k in bekannt:
            continue
        z = schatten_zeile(a, erste_stufe(a, stufen_filter) or "dedup", quelle,
                           ht_top, ht_rest, fresh_top, fresh_rest, jetzt=jetzt)
        buch.append(z); bekannt[k] = z
    return buch[-keep:]


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
                "serie": _serie_fuer_push(a),
                # 06.09.2026 (Lucas: „bitte unterbinde solche Pushes, wo einfach einer Fuehrung
                # gefolgt wird — oder kannst du das widerlegen"). Konnte ich, aber nur ueber
                # einen UMWEG: `onLeader` stand nirgends im Ledger, also musste ich aus
                # `htScore` + `leadName` rekonstruieren, wer zur Halbzeit vorn lag. Fuer
                # In-Play-Pushes zu beliebigen Minuten ist das ein Naeherungswert — ein Push in
                # der 70. bei 1:0, aber 0:0 zur Pause, faellt in die falsche Gruppe.
                #
                # Das Ergebnis war deutlich genug, um trotzdem zu tragen (n=52, Treffer 80,8 %,
                # ROI +27,8 %, einseitige Untergrenze +12,5 %), aber die naechste Antwort soll
                # exakt sein statt naeherungsweise. Also stempeln wir die Fuehrungs-Lage jetzt
                # im Moment des Sendens — dieselbe Lehre wie beim Serien-Stempel am 04.09.:
                # eine Momentaufnahme laesst sich nicht rueckwirkend rekonstruieren.
                # 12.09.2026: KEIN bool() mehr — None heisst „Stand unbekannt" und muss beim
                # Auswerten aus beiden Gruppen fallen, statt als „nicht auf den Fuehrenden" zu
                # zaehlen (s. _money_on_leader).
                "onLeader": a.get("onLeader"),
                "leadDir": a.get("leadDir"),
                "leadShare": a.get("leadShare"),
                "live": {"time": ((a.get("live") or {}).get("time")),
                         "score": [(a.get("live") or {}).get("goal_v1"),
                                   (a.get("live") or {}).get("goal_v2")]}})
    try:
        json.dump(led[-800:], open(PUB_LEDGER_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    except Exception as e:
        print("Public-Ledger-Schreibfehler:", e)


# 13.08.2026 (Lucas-Audit): dem In-Play-Draw-Geld zur bereits kollabierten X-Quote hinterherlaufen
# verliert nachweislich (-31..-79% ROI, betfair_draw_tracker). Pre-Match-Draw (~3.5) ist ~break-even.
# ⚠️ 08.09.2026: die Zahl „-31..-79 %" ist WIDERLEGT — sie kam aus `betfair_draw_tracker`, das die
# In-Play-Eimer gegen `lastDrawOddInplay` rechnete, also gegen die Quote beim SCHLUSSPFIFF
# (Mittel @96,80, Max @1.000). Mit der Quote beim Gleichstand ergibt derselbe Eimer +24,2 %. Der
# Tracker weist seither beide Raender aus und `backRoi: None`. Die Sperre bleibt trotzdem — sie
# steht ab heute auf dem Signal-Track (konzentriertes Remis-Geld: n=135, ROI −29,3 %, OG −10,0 %)
# und auf dem eigenen Public-Buch (10 Remis-Pushs, 3 Treffer, ROI −32 %).
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


# 🔴 08.09.2026 (Lucas: „ich hab wieder eine Push bekommen bei einem portugiesischen U23-Match …
# und jetzt noch im Trades-Channel beim Jugend-Champions-League-Spiel, Man City zwei null hinten,
# da kam auch was auf Unentschieden"). Beide Spiele standen zu dem Zeitpunkt so im Feed:
#
#   Estoril U23 v Famalicao U23   Min 87, 3:2   The Draw  86 % Anteil  @ 6,60  → implizit 15 %
#   Porto U19  v Man City U19     Min 45, 2:0   The Draw  48 % Anteil  @14,00  → implizit  7 %
#
# ⭐ Der ANTEIL ist kumulierter Umsatz ueber die ganze Marktlaufzeit, der PREIS ist von jetzt.
# Bei 2:2 in der 70. Minute wird auf das Remis gehandelt; faellt danach das 3:2, bleibt das Geld
# in der Statistik stehen und die Quote springt auf 6,6. „86 % des Geldes liegen auf dem Remis"
# beschreibt dann nichts Gegenwaertiges mehr — es ist ein Fossil. Niemand backt gerade ein
# 15-%-Ereignis mit 86 % des Marktes; die Zahl misst, was frueher einmal wahrscheinlich war.
#
# Gemessen am Feed dieses Laufs: von 6 laufenden Spielen tragen GENAU DIESE ZWEI einen
# Geld-Fuehrer mit >=40 % Anteil und einer Quote >=5,0 — der Guard trifft die beiden Faelle,
# ueber die Lucas gestolpert ist, und sonst nichts.
#
# Das ist bewusst eine LOGIK-Sperre, keine statistische: eine Quote von 14,0 neben 48 % Anteil
# ist unabhaengig von jeder Stichprobe keine Ueberzeugung. Die statistische Seite steht separat
# in `_draw_mo_public_raus`.
#
# Es gibt bereits `_pub_incoherent` (Anteil >=70 % auf Quote >=3,0) — beide Faelle rutschten
# durch, und zwar aus zwei verschiedenen Gruenden: Man City hatte nur 48 % Anteil (unter 70),
# und der Filter laeuft ausserdem NUR auf dem Public-Pfad, waehrend dieser Push in TRADES kam.
# Der neue Guard ist auf der Anteils-Seite lockerer (40 %), auf der Preis-Seite strenger (5,0)
# und gilt in BEIDEN Kanaelen. Er ersetzt `_pub_incoherent` nicht, er schliesst dessen Luecke.
STALE_SHARE_MIN = 0.40    # so viel Anteil behauptet „hier liegt das Geld"
STALE_ODD_MIN   = 5.0     # ... und so lang ist der Preis, der dem widerspricht (<= 20 % implizit)


def geld_ist_altbestand(a) -> bool:
    """Widerspricht der Geld-Anteil dem eigenen aktuellen Preis? REIN/testbar.

    Nur IN-PLAY: vor Anpfiff kann der Anteil nicht veralten, weil sich der Spielstand nicht
    geaendert hat. Ohne Anteil oder ohne Quote wird nichts behauptet — fehlende Angabe ist
    kein Widerspruch.
    """
    li = a.get("live") or {}
    if li.get("time") is None or li.get("finished"):
        return False
    sh, od = a.get("leadShare"), a.get("leadOdd")
    if not isinstance(sh, (int, float)) or not isinstance(od, (int, float)) or od <= 1:
        return False
    return sh >= STALE_SHARE_MIN and od >= STALE_ODD_MIN


def altbestand_note(a) -> str:
    """Die Zeile dazu — fuer den Fall, dass die Sperre irgendwo NICHT greift."""
    if not geld_ist_altbestand(a):
        return ""
    sh, od = a.get("leadShare"), a.get("leadOdd")
    return ("\n⛔ <b>Der Anteil ist Altbestand</b>: %.0f %% des Marktgeldes stehen auf einem Ausgang, "
            "den der Preis mit @%.2f (%.0f %%) fuehrt. Der Anteil summiert die ganze Marktlaufzeit, "
            "die Quote ist von jetzt — nach einem Tor bleibt das alte Geld stehen." 
            % (sh * 100, od, 100.0 / od))


# 🔴 08.09.2026 — die zweite Haelfte derselben Frage: was sagt unser eigenes Buch ueber
# Match-Odds-Remis-Pushs? Gemessen am Track (`betfair_track_results`, Preis = `entryOdd`):
#
#   Geld auf Heim          n=1482   53,3 %  Ø@2,10 (BE 47,7 %)   ROI  +3,9 %
#   Geld auf Auswaerts     n= 868   49,0 %  Ø@2,57 (BE 39,0 %)   ROI  +1,4 %
#   Geld auf Unentschieden n= 296   25,0 %  Ø@3,68 (BE 27,2 %)   ROI −14,1 %   [−28,8 % … +0,6 %]
#
# Und die Teilmengen, die eine PUSH-Bedingung beschreiben, verlieren belegt (Obergrenze < 0):
#
#   konzentriert (conc)          n=135   ROI −29,3 %   OG −10,0 %
#   Quote zieht rein (dir=in)    n= 79   ROI −31,3 %   OG  −4,9 %
#   konzentriert & Quote >= 3,4  n= 57   ROI −54,7 %   OG −28,0 %
#
# Das eigene Public-Buch sagt dasselbe: 10 Remis-Pushs, 3 Treffer, ROI −32 % (mit dem Estoril-4:2).
# Halbzeit-Remis ist ausdruecklich NICHT betroffen (n=804, ROI +4,1 %) — bei Anpfiff steht 0:0,
# das ist der Normalzustand und ein anderes Ereignis.
#
# ⚠️ Zur alten Begruendung: die Zahl „−31…−79 % ROI" in den Kommentaren unten stammt aus
# `betfair_draw_record`, Eimer `inplayOddTightened`/`inplayLevelMoney*` — und die rechnen mit
# `lastDrawOddInplay`, der LETZTEN In-Play-Quote. Bei einem 4:2 ist das ein Preis um 1.000
# (Durchschnitt des Eimers: @181). Zu dem Preis konnte nie jemand einsteigen; die Zahl ist ein
# Rueckblick-Artefakt. Die Richtung stimmt, die Zahl nicht — deshalb stehen oben die Werte aus
# dem Einstiegspreis.
def _draw_mo_public_raus(a) -> bool:
    """Match-Odds-Remis geht nicht mehr in den PUBLIC-Kanal. REIN.

    Trades behaelt es (dort entscheidet Lucas selbst und sieht die Warnzeile); Public ist der
    Kanal, in dem ein Fehlalarm Glaubwuerdigkeit kostet, und dort gilt der strenge Schalter.
    Halbzeit-Remis bleibt in beiden Kanaelen.
    """
    return str(a.get("leadName") or "") == "The Draw" and a.get("market") == "Match Odds"


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
                "wahrscheinlicher, der fallende Kurs ist die Falle. Im eigenen Buch verliert "
                "konzentriertes Remis-Geld belegt: n=135, ROI −29 %, Obergrenze −10 %.")
    g1, g2 = li.get("goal_v1"), li.get("goal_v2")
    tail = ", Remis wird von allein wahrscheinlicher" if (g1 == 0 and g2 == 0) else ""
    return ("\n⚠️ <b>Aber:</b> In-Play-Remis-Nachlauf — die fallende X-Quote ist hier kein Rückenwind, "
            "sondern der Zeit-Effekt" + tail + ". Match-Odds-Remis ist im eigenen Buch die einzige "
            "Seite ohne Kante: ROI −14 % gegen +4 % (Heim) und +1 % (Auswärts).")


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


TRICHTER_FILE = "betfair_public_trichter.json"
TRICHTER_TAGE = 30


def trichter_stufen(alerts, filter_paare) -> list:
    """Wie viele Alarme ueberleben jede Stufe? REIN/testbar. -> [(name, uebrig, raus)]

    🔴 19.09.2026 (Lucas: „Gestern kam kein einziger Betfair-Push in Public. Was komisch ist.").

    Es war nicht komisch, und es war kein Ausfall — der Nachbau des 18.09. aus 40 Preis-Staenden
    zeigt das:

        Stufe                      18.09.        17.09. (6 Pushes)
        Leader-Gate                   39            34
        Einseitigkeit >= 80 %          8            22      <- hier bricht der Tag
        kein Ereignis-Sprung           4            17
        Kohaerenz-Filter               0             9
        gesendet                       0             6

    Der Tag hatte schlicht kein einseitiges frisches Geld: 21 % der Alarme kamen durch die
    80-%-Schranke statt 65 % wie am Vortag. Die letzten vier starben an `under_goals` (2) und
    `drift` (2). Der Trades-Kanal lief derweil normal weiter — 20 neue Alarme, genauso viele wie
    am 16.09.

    Das Problem ist also nicht die Stille, sondern dass man sie nicht lesen kann. Ein stummer
    Kanal sieht genau gleich aus, ob er nichts zu sagen hat oder kaputt ist — und diese Woche war
    er beides: der Poly-Public-Kanal schwieg drei Tage, DAS war ein Defekt. Deshalb schreibt der
    Lauf ab jetzt mit, wo die Alarme geblieben sind.
    """
    out = []
    uebrig = list(alerts or [])
    out.append(("roh", len(uebrig), 0))
    for name, raus in filter_paare:
        vorher = len(uebrig)
        uebrig = [a for a in uebrig if not raus(a)]
        out.append((name, len(uebrig), vorher - len(uebrig)))
    return out


def trichter_buchen(stufen, gesendet, gruende, jetzt=None, alt=None, tage=TRICHTER_TAGE) -> dict:
    """Die Stufen eines Laufs in die Tagesbilanz addieren. REIN/testbar."""
    from datetime import datetime, timezone as _tz
    jetzt = jetzt or datetime.now(_tz.utc)
    tag = jetzt.strftime("%Y-%m-%d")
    buch = dict(alt or {})
    e = dict(buch.get(tag) or {})
    for name, uebrig, raus in stufen:
        e[name] = int(e.get(name, 0)) + int(uebrig if name == "roh" else raus)
    e["gesendet"] = int(e.get("gesendet", 0)) + int(gesendet)
    e["laeufe"] = int(e.get("laeufe", 0)) + 1
    g = dict(e.get("gruende") or {})
    for k, v in (gruende or {}).items():
        g[k] = int(g.get(k, 0)) + int(v)
    e["gruende"] = g
    e["updatedAt"] = jetzt.isoformat()
    buch[tag] = e
    return {k: buch[k] for k in sorted(buch)[-tage:]}


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
    # 08.09.2026: dazu der Altbestands-Guard — er gilt in BEIDEN Kanaelen, weil ein Anteil, der
    # dem eigenen Preis widerspricht, auch auf dem eigenen Schreibtisch nichts wert ist. Genau so
    # kam der Man-City-U19-Push (48 % auf @14,00 bei 2:0) in den Trades-Kanal.
    alerts = [a for a in alerts if not _draw_inplay_chase(a) and not _trades_reactive_backed_under(a)
              and not geld_ist_altbestand(a)]
    # 15.09.2026: ein Ausgang, den der Spielstand schon entschieden hat, ist keine Wette mehr —
    # raus aus BEIDEN Kanaelen, aber ins Buch (s. entschieden_gate).
    alerts, _entschieden = entschieden_gate(alerts)
    if _entschieden:
        n = entschieden_buch_schreiben(_entschieden, _BASIS)
        print("  🔇 %d Alarm(e) verworfen: Ausgang durch den Spielstand entschieden" % n)
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

    # -- 📉 Kursrutsch (19.09.2026, Lucas) -- keine Geldschwelle, dafuer muss die Quote
    # nachweislich gefallen sein. NUR Trades: gemessen +18,3 % (UG +2,3) auf n=203, aber nach
    # Korrektur fuer 22 angesehene Schnitte p = 0,125 -- das ist ein Kandidat, kein Beleg.
    # Herleitung samt Zahlen bei RUTSCH_MIN_FALL.
    try:
        _rs_seen = _load_seen(RUTSCH_SEEN_FILE)
        _einstieg = einstiegsquoten(_lade_json(RUTSCH_STATE_FILE, {}))
        _rutsch = [r for r in (rutsch_alert(m, _einstieg)
                               for m in (prices.get("matches") or [])) if r]
        _rs_sent = 0
        for a in _rutsch:
            key = "rutsch:" + a["matchId"] + ":" + str(a.get("market"))
            if should_send(_rs_seen, key, a["value"]):
                if send_trades_message(build_rutsch_message(a)):
                    _rs_seen[key] = a["value"]
                    _rs_sent += 1
                    _log_rutsch(a)
        _save_seen(RUTSCH_SEEN_FILE, _rs_seen)
        print("  \U0001f4c9 Kursrutsch: %d Kandidat(en), %d gesendet (nur Trades, %d Einstiegsquoten gelesen)"
              % (len(_rutsch), _rs_sent, len(_einstieg)))
    except Exception as _e:
        print("  ⚠️  Kursrutsch-Alarm uebersprungen:", _e)

    # 🟡 Öffentlicher Moneyflow (kuratierte, höhere Schwellen) → CocoBet-Community-Channel.
    # Eigener Dedup-State, damit die höhere Public-Schwelle unabhängig vom Trades-Channel greift.
    pub_seen = _load_seen(PUB_SEEN_FILE)
    _pub_roh = attach_direction(
        collect_alerts(prices, hist, PUB_HT_TOP, PUB_HT_REST, PUB_FRESH_TOP, PUB_FRESH_REST), direction)
    _pub_nach_leader = _leader_gate(_pub_roh, PUB_HT_TOP, PUB_HT_REST, PUB_FRESH_TOP, PUB_FRESH_REST)
    pub_alerts = _pub_nach_leader
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
    # 08.09.2026: Match-Odds-Remis komplett raus aus Public (Buch: 10 Pushs, 3 Treffer, ROI −32 %;
    # der Signal-Track: konzentriertes Remis-Geld ROI −29,3 % mit Obergrenze −10,0 %, also belegt
    # verlierend). Halbzeit-Remis bleibt (n=804, ROI +4,1 %). Trades sieht beides weiter.
    pub_alerts = [a for a in pub_alerts if not _draw_mo_public_raus(a) and not geld_ist_altbestand(a)]
    # 14.08.2026 (Lucas): unnoetige HT/Live-Pushs raus, wo die Geld-% der Quote widersprechen
    # (Galatasaray 85%@13.50; Wolves Under 87% aber Quote driftet). Trades sieht sie weiter.
    pub_alerts = [a for a in pub_alerts if not _pub_incoherent(a) and not _pub_drift(a) and not _pub_ht_useless(a) and not _pub_unconfirmed_fav(a) and not _pub_under_goals(a)]   # 16.08.2026 (Lucas): Under-Tore aus Public, live UND vor Anpfiff
    pub_sent = 0
    _gesendet_k = set()          # scenario:matchId:market — dieselbe Form wie im Schattenbuch
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
                _gesendet_k.add("%s:%s:%s" % (a.get("scenario"), a.get("matchId"), a.get("market")))
                _log_public_push(a, cidx)   # fürs Tracking/Auswerten (+ Konsens-Zweitmeinung)
    _save_seen(PUB_SEEN_FILE, pub_seen)

    # 19.09.2026: mitschreiben, WO die Alarme geblieben sind. Ohne das ist ein stummer Tag von
    # einem kaputten Kanal nicht zu unterscheiden — s. `trichter_stufen`.
    _stufen_filter = [
        ("leader", lambda a: a not in _pub_nach_leader),
        ("einseitig", lambda a: a.get("scenario") == "fresh"
                                and (a.get("leadShare") or 0.0) < PUB_FRESH_MIN_SHARE),
        ("fix", lambda a: a.get("scenario") == "fix"),
        ("ereignis_sprung", _dir_event_jump),
        ("draw_inplay", _draw_inplay_chase),
        ("mo_remis", _draw_mo_public_raus),
        ("altbestand", geld_ist_altbestand),
        ("inkohaerent", _pub_incoherent),
        ("drift", _pub_drift),
        ("ht_nutzlos", _pub_ht_useless),
        ("fav_unbestaetigt", _pub_unconfirmed_fav),
        ("under_tore", _pub_under_goals),
    ]
    _stufen = trichter_stufen(_pub_roh, _stufen_filter)
    _gruende = {name: raus for name, _uebrig, raus in _stufen if raus}

    # ── 19.09.2026: das Schattenbuch der Beinahe-Treffer ─────────────────────────────────
    # Der Trichter zaehlt, WIE VIELE an welcher Stufe sterben. Er sagt nicht, wie sie ausgegangen
    # waeren — und ohne das ist jede Schwelle unverschiebbar. Hier wird jeder nicht gesendete
    # Kandidat mit seinen Zahlen abgelegt; betfair_public_eval rechnet ihn spaeter mit derselben
    # settle()-Mechanik ab wie einen echten Push. GESENDET WIRD HIER NICHTS.
    # Zwei Quellen, weil die Schwelle in zwei Richtungen falsch stehen kann:
    #   · "public" — war ueber der Geldschwelle, starb an einer Kurationsstufe (0,80 usw.),
    #   · "trades" — haette gereicht, waere die Geldschwelle niedriger; sagt, was ein Absenken
    #     brachte. Ohne diese Haelfte kann man die Schwelle nur erhoehen, nie begruenden.
    try:
        try:
            _sch_alt = json.load(open(SCHATTEN_FILE, encoding="utf-8"))
        except Exception:
            _sch_alt = []
        if not isinstance(_sch_alt, list):
            _sch_alt = []
        _sch = schatten_buch(_pub_roh, _gesendet_k, _stufen_filter, alt=_sch_alt)
        _pub_k = {"%s:%s:%s" % (a.get("scenario"), a.get("matchId"), a.get("market"))
                  for a in _pub_roh}
        _unter = [a for a in alerts
                  if "%s:%s:%s" % (a.get("scenario"), a.get("matchId"), a.get("market")) not in _pub_k]
        _sch = schatten_buch(_unter, _gesendet_k, [("unter_geldschwelle", lambda _a: True)],
                             alt=_sch, quelle="trades")
        json.dump(_sch, open(SCHATTEN_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        print("  🕯️  Schattenbuch: %d Zeilen (%d neu in diesem Lauf)"
              % (len(_sch), len(_sch) - len(_sch_alt)))
    except Exception as _e:
        print("  ⚠️  Schattenbuch nicht geschrieben:", _e)
    try:
        _alt = json.load(open(TRICHTER_FILE, encoding="utf-8"))
    except Exception:
        _alt = {}
    try:
        json.dump(trichter_buchen(_stufen, pub_sent, _gruende, alt=_alt if isinstance(_alt, dict) else {}),
                  open(TRICHTER_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as _e:
        print("  ⚠️  Trichter nicht geschrieben:", _e)
    print("Betfair Public-Moneyflow: %d Kandidaten, %d gesendet" % (len(pub_alerts), pub_sent))
    if not pub_sent and _stufen[0][1]:
        _wo = ", ".join("%s −%d" % (n, r) for n, _u, r in _stufen if r)
        print("  ℹ️  nichts gesendet. Wo die %d Alarme geblieben sind: %s"
              % (_stufen[0][1], _wo or "—"))


if __name__ == "__main__":
    main()
