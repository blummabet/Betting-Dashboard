#!/usr/bin/env python3
"""telegram_streak_watch.py — Serien-Watch + Serie-gehalten/gerissen (04.07.2026, Lucas).

Zwei zeitnahe, spielbezogene Serien-Formate für den Public-Channel (ergänzt den wöchentlichen
„Serien der Woche"-Digest):

  • MODE=watch (pre-match): Team mit heißer Serie geht in sein nächstes Spiel → kurze Vorschau
    „🔥 Serien-Watch · X geht mit N× … ins Spiel gegen Y" inkl. xG-Deckungs-Siegel.
  • MODE=recap (post-match): das bewachte Spiel ist gelaufen → „✅ Serie hält (jetzt N+1×)" oder
    „❌ nach N Spielen gerissen". Macht aus Einzel-Cards eine fortlaufende Story.

State {prefix}streak_watch.json koppelt beide: watch merkt sich die bewachte Serie + ihr Spiel,
recap löst sie nach Spielende auf. TikTok-safe (keine Quoten/€). Dataset-aware (WM/MLS/Liga).

Env: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID (Public), TG_STREAK_MODE=watch|recap, SKIP_TELEGRAM=true.
"""
from __future__ import annotations
from tg_safe import safe_flag

import json
import math
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import cocobet_dataset as D
import push_deckel as PD   # 12.09.2026: Nachrichten-Deckel je Lauf

BASE = Path(__file__).parent
STREAKS_FILE = D.file("wm_streaks.json", "liga_streaks.json")
WM_FILE = D.data_file()
STATE_FILE = BASE / f"{D.prefix()}streak_watch.json"
# 09.09.2026 — das Buch: eine Zeile je abgerechneter Serie. Getrennt vom Watch-Zustand, weil der
# Watch fluechtig ist (Eintraege fallen nach dem Spiel raus) und das Buch dauerhaft.
RECORD_FILE = BASE / f"{D.prefix()}streak_record.json"
BILANZ_MIN_N = int(os.environ.get("STREAK_BILANZ_MIN_N", "30"))
# Wie viele Zeilen muessen eine VOR dem Spiel festgeschriebene Erwartung tragen, damit der
# Vergleich ueberhaupt einer ist? Zusaetzlich muss mindestens die Haelfte der Zeilen sie tragen —
# sonst wird ein Mittel aus wenigen Zeilen an viele angelegt (s. bilanz()).
ERWARTUNG_MIN_N = int(os.environ.get("STREAK_ERWARTUNG_MIN_N", "20"))

# 🔴 12.09.2026 (Lucas: „Ich hab grad knapp 20 pushes in public bekommen — irgendwelche einzelner
# zu Serien. Sowas gabs in der Form noch nie."). Das war MEIN Fix vom selben Tag: bis dahin hatte
# das Serien-Buch NIE eine Zeile abgerechnet (alle `pickKey` null), der Fix machte die Abrechnung
# ueber Team+Datum moeglich — und raeumte damit in einem Lauf den kompletten Rueckstau ab. `main`
# schickte je abgerechneter Serie eine Nachricht: 52 Zeilen = 52 Pushes.
#
# Zwei Regeln, beide gegen die FEHLERKLASSE, nicht gegen diesen Lauf:
#   1. Nur FRISCHE Abrechnungen werden gepostet. Was laenger her ist, wandert ins Buch — ein
#      Ergebnis von vor sechs Wochen ist ein Messpunkt, keine Nachricht.
#   2. Ein Recap-Lauf sendet HOECHSTENS EINE Nachricht (s. recap_nachrichten). Nicht „selten
#      viele", sondern strukturell nie mehr als eine — dieselbe Konsequenz, die der Watch-Zweig
#      im August gezogen hat („reicht 1 Nachricht am Tag").
RECAP_MAX_ALTER_H = float(os.environ.get("STREAK_RECAP_MAX_ALTER_H", "36"))
RECAP_DIGEST_MAX_ZEILEN = int(os.environ.get("STREAK_RECAP_MAX_ZEILEN", "12"))


def _wilson(treffer, n, z: float = 1.645):
    """Einseitige 95-%-Wilson-Untergrenze. Dieselbe Definition wie in sharp_gate."""
    n = int(n or 0)
    if n <= 0:
        return 0.0
    ph = (treffer or 0) / n
    d = 1 + z * z / n
    mitte = (ph + z * z / (2 * n)) / d
    rand = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return mitte - rand

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
# `or`-Fallback + echter Public-Default (nicht ""): ein leeres TELEGRAM_CHAT_ID-Secret
# injiziert einen leeren String, der .get(key,"") NICHT durch den Default ersetzt → Send
# scheiterte still. Wie telegram_wm.py. (06.07.2026, Lucas)
CHAT_ID = (os.environ.get("TELEGRAM_CHAT_ID") or "-1003819239615").strip()
MODE = (os.environ.get("TG_STREAK_MODE") or "watch").lower()
SKIP_TELEGRAM = os.environ.get("SKIP_TELEGRAM", "").lower() == "true"

WATCH_MIN_LEN = int(os.environ.get("STREAK_WATCH_MIN_LEN", "10"))  # 26.07.2026 (Lucas): Public-Channel nur RICHTIG lange Serien (≥10) — 7-8 war zu viel Rauschen
# 02.08.2026 (Lucas: „Spiele waren heute Nacht"): Vorlauf-Fenster statt zeitzonen-blindem `date == today`.
# Nur ansagen, wenn der Anpfiff noch WATCH_LEAD_MIN..WATCH_HORIZON_H entfernt ist (echter Zeitpunkt, nicht Datum).
WATCH_LEAD_MIN  = int(os.environ.get("STREAK_WATCH_LEAD_MIN", "30"))      # min. Vorlauf: noch spielbar
WATCH_HORIZON_H = float(os.environ.get("STREAK_WATCH_HORIZON_H", "18"))   # max. Vorlauf: nur die kommende Nacht, nicht Tage voraus

# Nur tor-basierte Typen (aus dem Endstand deterministisch aufzulösen). Ecken/Karten brauchen
# Stats-Coverage → hier bewusst aus (kein unsicheres „gerissen").
_PHRASE = {
    "over25":     "Über-2,5-Tore", "under25":   "Unter-2,5-Tore",
    "bttsYes":    "Beide-treffen",  "bttsNo":    "Kein-Gegentor-Duell",
    "scored":     "Tor",            "cleanSheet": "Zu-Null",
}
_ICON = {"over25": "⚽", "under25": "🧱", "bttsYes": "🤝", "bttsNo": "🚫",
         "scored": "🎯", "cleanSheet": "🛡️"}


def tg_send(text: str) -> bool:
    # SKIP_TELEGRAM = expliziter lokaler Dry-Run → True, damit main() den Flow (State) durchläuft.
    if SKIP_TELEGRAM:
        print("ℹ️  Telegram-Send geskippt (SKIP_TELEGRAM) — Vorschau:\n" + text)
        return True
    # Fehlender Token/Chat in einem ECHTEN Lauf ist ein FEHLER, kein Skip: False zurückgeben,
    # sonst markiert main() die Serie fälschlich als „bewacht" (Phantom-Dedup) und sendet nie nach.
    # (06.07.2026, Lucas: Serien-Watch schrieb Marker ohne echten Send → still verschluckt.)
    if not (TOKEN and CHAT_ID):
        print("⚠️  TELEGRAM_TOKEN/CHAT_ID fehlt — kein Send (nicht als bewacht markiert)")
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    body = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"❌ Telegram-Send fehlgeschlagen: {e}")
        return False


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_fixture(wm: dict, home: str, away: str) -> dict | None:
    for g in (wm.get("groups") or {}).values():
        for fx in (g.get("fixtures") or []):
            if fx.get("home") == home and fx.get("away") == away:
                return fx
    for kf in (wm.get("koFixtures") or []):
        if kf.get("home") == home and kf.get("away") == away:
            return kf
    return None


def _fixture_fuer(wm: dict, team_id, datum) -> dict | None:
    """Das Spiel dieses Teams an diesem Tag — ohne Umweg ueber einen Schluessel.

    🔴 12.09.2026 (Lucas, Plattform-Audit). `build_recap` suchte das Spiel ueber `pickKey`:
    String zerlegen, die letzten zwei Teile als Heim/Auswaerts lesen. Nur stand in **allen 132**
    bewachten Serien `pickKey: null` — `compute_streaks.py` baut den Schluessel intern, kopiert
    ihn aber nicht in `s["next"]`, und von dort holt ihn der Watch. Ergebnis: `parts` hatte ein
    Element, `fx` blieb None, jede Zeile fiel in `continue`. **Das Serien-Buch hat seit seiner
    Einfuehrung keine einzige Zeile bekommen** — `streak_record.json` existiert nicht,
    `streak-log.json` ist 0 Bytes.

    Der Schluessel wird jetzt zwar mitgeschrieben, aber die Abrechnung haengt nicht mehr an ihm.
    Team und Datum stehen ohnehin im Watch-Eintrag und sind die Sache selbst; ein zusammengesetzter
    String ist nur eine Abkuerzung dorthin — und eine Abkuerzung, die durch zwei Module reisen
    muss, geht irgendwo verloren. Fehlerklasse statt Instanz.
    """
    if not team_id or not datum:
        return None
    tid, tag = str(team_id), str(datum)[:10]
    for g in (wm.get("groups") or {}).values():
        for fx in (g.get("fixtures") or []):
            if str(fx.get("date") or "")[:10] != tag:
                continue
            if str(fx.get("home")) == tid or str(fx.get("away")) == tid:
                return fx
    for kf in (wm.get("koFixtures") or []):
        _d = str(kf.get("date") or kf.get("kickoff") or "")[:10]
        if _d == tag and (str(kf.get("home")) == tid or str(kf.get("away")) == tid):
            return kf
    return None


def _fixture_finished(fx: dict) -> bool:
    return str(((fx or {}).get("result") or {}).get("status") or "").upper() in {"FT", "AET", "PEN"}


def streak_held(stype: str, team_id: str, fx: dict) -> bool | None:
    """Hat die Serie im (fertigen) Spiel gehalten? Aus dem 90-Min-/Endstand. None wenn unklar."""
    r = (fx or {}).get("result") or {}
    hs, as_ = r.get("home_score"), r.get("away_score")
    if not isinstance(hs, (int, float)) or not isinstance(as_, (int, float)):
        return None
    total = hs + as_
    is_home = fx.get("home") == team_id
    own, opp = (hs, as_) if is_home else (as_, hs)
    if stype == "over25":    return total > 2.5
    if stype == "under25":   return total < 2.5
    if stype == "bttsYes":   return hs > 0 and as_ > 0
    if stype == "bttsNo":    return not (hs > 0 and as_ > 0)
    if stype == "scored":    return own > 0
    if stype == "cleanSheet": return opp == 0
    # 09.09.2026: Sieg- und Ungeschlagen-Serien stehen im Endstand genauso drin wie die
    # Tor-Maerkte. Sie fehlten hier nur — und fielen deshalb still aus jeder Abrechnung.
    if stype == "win":       return own > opp
    if stype == "unbeaten":  return own >= opp
    # Ecken und Karten stehen NICHT im Endstand. Sie bleiben None und werden als
    # „unaufloesbar" gebucht, statt still zu verschwinden — ein Markt, den wir nicht
    # abrechnen koennen, muss im Nenner sichtbar bleiben.
    return None


# ── MODE=watch ────────────────────────────────────────────────────────────────
def _parse_ko(v):
    """ISO-Anpfiff → aware UTC-datetime; None wenn leer/unparsbar."""
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        return None

def build_watch(streaks: list, wm: dict, watched: dict, today: str, now=None) -> list:
    """Zu bewachende Serien: all-venue, intakt, ≥WATCH_MIN_LEN, tor-basiert, noch nicht bewacht —
    und (NEU 02.08.2026, Lucas) deren ANPFIFF noch bevorsteht (WATCH_LEAD_MIN..WATCH_HORIZON_H).
    Der alte `date == today`-Filter war zeitzonen-blind: MLS-Spiele stoßen nachts an (UTC-früh),
    tragen aber das UTC-Datum von HEUTE → der 19:00-UTC-Lauf feuerte ~20 h NACH Abpfiff. Jetzt
    zählt der echte Anpfiff-Zeitpunkt (fixt auch die Spät-Spiele, deren UTC-Datum morgen ist).
    Returns [(key, entry, message)]."""
    now = now or datetime.now(timezone.utc)
    out = []
    for s in streaks or []:
        if (s.get("venue") or "all") != "all":
            continue
        if (s.get("continuation") or {}).get("state") != "intakt":
            continue
        stype = s.get("type")
        if stype not in _PHRASE:
            continue
        if (s.get("length") or 0) < WATCH_MIN_LEN:
            continue
        nx = s.get("next") or {}
        gdate = str(nx.get("date") or "")[:10]
        ko = _parse_ko(nx.get("kickoff"))
        if ko is None:
            continue   # ohne echten Anpfiff-Zeitstempel NICHT bewachen (lieber still als falsch)
        mins = (ko - now).total_seconds() / 60.0
        if mins < WATCH_LEAD_MIN:
            continue   # Anpfiff vorbei/zu knapp → nicht mehr spielbar (der „heute Nacht"-Bug)
        if mins > WATCH_HORIZON_H * 60:
            continue   # noch zu weit weg → erst näher am Spiel ansagen
        key = f"{s.get('teamId')}:{stype}:{gdate}"
        if key in watched:
            continue
        # ⭐ 09.09.2026 — DIE ERWARTUNG WIRD VOR DEM SPIEL FESTGESCHRIEBEN.
        # Ohne sie ist eine Trefferquote hinterher nur eine Zahl: „62 % erfuellt" heisst nichts,
        # solange nicht danebensteht, was ohne jede Serie zu erwarten gewesen waere. Die Rate
        # spaeter nachzuschlagen waere kein Vergleich, sondern ein Rueckblick auf einen Wert,
        # den dasselbe Spiel schon veraendert hat. Dieselbe Regel wie in `vorregistrierung.py`.
        _se = s.get("seltenheit") or {}
        entry = {"teamId": str(s.get("teamId")), "team": s.get("team"), "type": stype,
                 "length": s.get("length"), "market": s.get("market"),
                 "pickKey": nx.get("pickKey"), "oppName": nx.get("oppName"),
                 "date": gdate, "kickoff": nx.get("kickoff"), "xgBacked": s.get("xgBacked"),
                 "flag": safe_flag(s.get("flag")), "oppRatePct": nx.get("oppRatePct"),
                 "erwartetPct": _se.get("ratePct"), "erwartetBasis": _se.get("basis"),
                 "erwartetPreN": _se.get("preN"),
                 "postedAt": now.isoformat()}
        out.append((key, entry, _watch_msg(s, nx)))
    return out


def _watch_msg(s: dict, nx: dict) -> str:
    icon = _ICON.get(s.get("type"), "🔥")
    flag = safe_flag(s.get("flag"))
    phrase = s.get("market") or _PHRASE.get(s.get("type"), "Serie")
    lines = [f"🔥 <b>Serien-Watch</b>",
             f"{flag} <b>{s.get('team')}</b> geht mit <b>{s.get('length')}× {phrase}</b> "
             f"in Folge ins Spiel gegen {nx.get('oppName') or '—'}."]
    xgb = s.get("xgBacked")
    if xgb is True:
        lines.append("✓ Echte Serie — auch per xG gedeckt.")
    elif xgb is False:
        lines.append("⚠️ Vorsicht: zuletzt mehr Glück als xG.")
    opp_pct = nx.get("oppRatePct")
    if isinstance(opp_pct, (int, float)):
        lines.append(f"Gegner-Grundrate passt in {opp_pct}% seiner Spiele.")
    return "\n".join(lines)


def build_watch_digest(entries: list) -> str:
    """EIN gebündelter Public-Push für ALLE heute anstehenden Serien (22.08.2026, Lucas:
    „reicht 1 Nachricht am Tag"). Ersetzt die frühere Eine-Nachricht-je-Serie-Flut. Heißeste
    Serie zuerst, kompakte 2-Zeilen-Blöcke, TikTok-safe (keine Quoten/€)."""
    rows = sorted(entries or [], key=lambda e: (e.get("length") or 0), reverse=True)
    n = len(rows)
    head = ["🔥 <b>Serien-Watch</b> — heute",
            f"<i>{n} {'Team' if n == 1 else 'Teams'} mit heißer Serie vor dem Anpfiff</i>"]
    blocks = ["\n".join(head)]
    for e in rows:
        icon = _ICON.get(e.get("type"), "🔥")
        flag = e.get("flag") or ""
        phrase = e.get("market") or _PHRASE.get(e.get("type"), "Serie")
        top = (f"{icon} {flag} <b>{e.get('team')}</b> · "
               f"<b>{e.get('length')}×</b> {phrase}")
        det = f"↳ gegen {e.get('oppName') or '—'}"
        pct = e.get("oppRatePct")
        if isinstance(pct, (int, float)):
            det += f" · Grundrate {pct}%"
        xgb = e.get("xgBacked")
        if xgb is True:
            det += " · ✓ xG"
        elif xgb is False:
            det += " · ⚠️ Glück"
        blocks.append(f"{top}\n{det}")
    blocks.append("🤖 <i>CocoBet · Serien-Modell</i>")
    return "\n\n".join(blocks)


# ── MODE=recap ────────────────────────────────────────────────────────────────
def build_recap(wm: dict, watched: dict, today: str, now=None) -> tuple[list, list, list]:
    """Bewachte Serien, deren Spiel gelaufen ist → (Nachrichten, erledigte Keys, Buchungen).

    🔴 09.09.2026 (Lucas: „die Frage ist einfach — wurde Serie erfuellt ja oder nein").
    Genau das rechnete diese Funktion seit August jeden Tag aus — und warf es weg. Der Recap
    postete „Serie haelt" bzw. „gerissen" und `main` loeschte den Eintrag danach aus dem Watch.
    Gemessen am 08.09.: 50 bewachte Serien, **0 Ergebnisse**. Die Antwort auf „machen die Serien
    Sinn" wurde taeglich berechnet und nie aufgeschrieben.

    Ab jetzt geht jede aufgeloeste Serie als Zeile ins Buch. Die dritte Rueckgabe ist diese
    Zeile — `main` haengt sie an `streak_record.json`.
    """
    jetzt = now or datetime.now(timezone.utc)
    msgs, done, buchungen = [], [], []
    for key, w in list(watched.items()):
        if str(w.get("date") or "")[:10] >= today:
            continue   # Spieltag noch nicht vorbei
        # Team + Datum zuerst — das steht immer im Eintrag. `pickKey` nur noch als zweiter Weg,
        # fuer den Fall, dass ein Spiel verlegt wurde und das Datum im Watch veraltet ist.
        fx = _fixture_fuer(wm, w.get("teamId"), w.get("date"))
        if fx is None:
            pk = str(w.get("pickKey") or "")
            parts = pk.split("-")
            fx = _find_fixture(wm, parts[-2], parts[-1]) if len(parts) >= 3 else None
        if not fx or not _fixture_finished(fx):
            continue   # noch kein Endstand → beim nächsten Lauf erneut prüfen
        held = streak_held(w.get("type"), w.get("teamId"), fx)
        buchungen.append(_buchung(key, w, held))
        done.append(key)
        if held is None:
            # Nicht aufloesbar (Ecken, Karten): raus aus dem Watch, aber MIT Zeile im Buch.
            # Ein Markt, den wir nicht abrechnen koennen, muss im Nenner sichtbar bleiben —
            # sonst sieht das Buch vollstaendiger aus, als es ist.
            continue
        if not _frisch(w, fx, jetzt):
            continue   # Rueckstau: wird gebucht, aber NICHT gepostet (s. RECAP_MAX_ALTER_H)
        msgs.append(_recap_msg(w, held))
    return msgs, done, buchungen


def _abpfiff_etwa(w: dict, fx) -> "datetime | None":
    """Grober Abpfiff-Zeitpunkt einer bewachten Serie — Anpfiff + 2 h, sonst Spieltag + 24 h."""
    ko = _parse_ko(w.get("kickoff")) or _parse_ko((fx or {}).get("kickoff"))
    if ko is not None:
        return ko + timedelta(hours=2)
    d = str(w.get("date") or "")[:10]
    try:
        return datetime.fromisoformat(d).replace(tzinfo=timezone.utc) + timedelta(hours=24)
    except Exception:
        return None


def _frisch(w: dict, fx, jetzt: datetime) -> bool:
    """Ist diese Abrechnung noch eine Nachricht wert?

    Ohne bestimmbaren Zeitpunkt: NEIN. Fehlende Information rendert hier als harmloser Default,
    und harmlos heisst beim Push „nicht senden" — die Zeile geht trotzdem ins Buch, es geht also
    kein Messpunkt verloren. Der umgekehrte Default waere genau der Lauf vom 12.09.
    """
    ab = _abpfiff_etwa(w, fx)
    if ab is None:
        return False
    return (jetzt - ab) <= timedelta(hours=RECAP_MAX_ALTER_H)


def recap_nachrichten(msgs: list) -> list:
    """Aus N Einzel-Abrechnungen HOECHSTENS EINE Nachricht.

    Der Deckel ist hier keine Zahl, die man verstellen kann, sondern die Form der Funktion: sie
    gibt nie mehr als ein Element zurueck. Ein Zaehler-Limit haette den 12.09. auf „nur" fuenf
    Pushes gedeckelt; die Frage war aber nie, wie viele — sondern dass ein Rueckstau ueberhaupt
    je Zeile sendet. Gleiche Antwort wie im Watch-Zweig: ein Block, alles drin.
    """
    rows = [m for m in (msgs or []) if m]
    if not rows:
        return []
    if len(rows) == 1:
        return [rows[0]]
    zeilen = rows[:RECAP_DIGEST_MAX_ZEILEN]
    rest = len(rows) - len(zeilen)
    kopf = f"\U0001F4D2 <b>Serien-Abrechnung</b>\n<i>{len(rows)} bewachte Serien sind gelaufen</i>"
    body = "\n".join(zeilen)
    if rest:
        body += f"\n<i>… und {rest} weitere</i>"
    return ["\n\n".join([kopf, body, "\U0001F916 <i>CocoBet · Serien-Modell</i>"])]


def _buchung(key: str, w: dict, held) -> dict:
    """Eine Zeile fuers Buch. Traegt die VOR dem Spiel festgeschriebene Erwartung mit."""
    return {"key": key, "teamId": w.get("teamId"), "team": w.get("team"),
            "type": w.get("type"), "market": w.get("market"), "length": w.get("length"),
            "oppName": w.get("oppName"), "date": w.get("date"), "kickoff": w.get("kickoff"),
            "erwartetPct": w.get("erwartetPct"), "erwartetBasis": w.get("erwartetBasis"),
            "erwartetPreN": w.get("erwartetPreN"),
            "erfuellt": held, "gebuchtAm": datetime.now(timezone.utc).isoformat()}


# ── Die Bilanz: traegt eine lange Serie sich selbst? ─────────────────────────────────────
def bilanz(zeilen) -> dict:
    """Aus den gebuchten Zeilen die eine Zahl, um die es geht. REIN/testbar.

    ⭐ Die Trefferquote ALLEIN sagt hier nichts — „62 % erfuellt" ist gut oder schlecht, je
    nachdem, was ohne jede Serie zu erwarten war. Deshalb steht die vor dem Spiel
    festgeschriebene Erwartung daneben, und das Urteil vergleicht die UNTERGRENZE der
    beobachteten Quote mit ihr:

        Untergrenze > Erwartung   →  die Serie traegt sich selbst (Hot Hand)
        Obergrenze  < Erwartung   →  sie kehrt um (Regression)
        sonst                     →  kein Unterschied messbar

    Ein Punktschaetzer entscheidet hier nichts: 8 von 12 sind 67 %, mit einer Untergrenze von
    42 % — das ist mit „die Serie sagt gar nichts" voll vereinbar.

    (Preise bleiben ausdruecklich draussen. Lucas: „der Preis ist da egal, die Frage ist einfach,
    wurde die Serie erfuellt ja oder nein." Diese Bilanz beantwortet damit NICHT, ob Serien Geld
    bringen — sie beantwortet, ob sie ueberhaupt Information tragen. Ohne das Ja ist die
    Geldfrage sinnlos; mit dem Ja ist sie die naechste.)
    """
    rows = [z for z in (zeilen or []) if isinstance(z, dict)]
    auf = [z for z in rows if isinstance(z.get("erfuellt"), bool)]
    offen = len(rows) - len(auf)
    n = len(auf)
    treffer = sum(1 for z in auf if z["erfuellt"])
    # Erwartung: nach Stichprobe gewichtetes Mittel der VOR dem Spiel festgeschriebenen Raten.
    _e = [float(z["erwartetPct"]) for z in auf if isinstance(z.get("erwartetPct"), (int, float))]
    erwartet = (sum(_e) / len(_e)) if _e else None
    aus = {"n": n, "treffer": treffer, "unaufloesbar": offen,
           "quotePct": round(100.0 * treffer / n, 1) if n else None,
           "erwartetPct": round(erwartet, 1) if erwartet is not None else None,
           "mitErwartung": len(_e)}
    if n < BILANZ_MIN_N:
        aus["urteil"] = "sammelt"
        aus["grund"] = ("%d von %d abgerechneten Serien — unter %d sagt der Vergleich nichts"
                        % (n, BILANZ_MIN_N, BILANZ_MIN_N))
        return aus
    ug = _wilson(treffer, n)
    og = 1.0 - _wilson(n - treffer, n)
    aus["ugPct"], aus["ogPct"] = round(100 * ug, 1), round(100 * og, 1)
    if erwartet is None:
        aus["urteil"] = "kein Vergleich"
        aus["grund"] = "keine vor dem Spiel festgeschriebene Erwartung in den Zeilen"
    elif len(_e) < ERWARTUNG_MIN_N or len(_e) * 2 < n:
        # 🔴 12.09.2026 (Plattform-Audit). Als das Serien-Buch zum ersten Mal Zeilen bekam, standen
        # sofort 52 Liga-Zeilen drin — aber nur **2** davon trugen eine Erwartung (das Feld gibt es
        # erst seit dem 09.09.). Das Urteil lautete trotzdem „die Erwartung von 71,0 % liegt im
        # Band", als waere die Erwartung aus denselben 52 Zeilen gerechnet.
        #
        # Ein Mittel aus 2 Zeilen, angelegt an 52, ist kein Vergleich, sondern eine Zahl, die
        # zufaellig danebensteht. Dieselbe Regel wie ueberall hier: was nichts entscheiden kann,
        # darf nicht als Urteil auftreten.
        aus["urteil"] = "Erwartung zu duenn"
        aus["grund"] = ("erfuellt in %.1f %% (%.1f..%.1f %%), aber nur %d von %d Zeilen tragen "
                        "eine vor dem Spiel festgeschriebene Erwartung — daraus laesst sich kein "
                        "Vergleich rechnen" % (aus["quotePct"], aus["ugPct"], aus["ogPct"],
                                               len(_e), n))
    elif ug * 100 > erwartet:
        aus["urteil"] = "traegt sich selbst"
        aus["grund"] = ("erfuellt in %.1f %% (Untergrenze %.1f %%) gegen %.1f %% Erwartung"
                        % (aus["quotePct"], aus["ugPct"], erwartet))
    elif og * 100 < erwartet:
        aus["urteil"] = "kehrt um"
        aus["grund"] = ("erfuellt in %.1f %% (Obergrenze %.1f %%) gegen %.1f %% Erwartung"
                        % (aus["quotePct"], aus["ogPct"], erwartet))
    else:
        aus["urteil"] = "kein Unterschied"
        aus["grund"] = ("erfuellt in %.1f %% (%.1f..%.1f %%) — die Erwartung von %.1f %% liegt "
                        "im Band" % (aus["quotePct"], aus["ugPct"], aus["ogPct"], erwartet))
    return aus


def _recap_msg(w: dict, held: bool) -> str:
    icon = _ICON.get(w.get("type"), "🔥")
    phrase = w.get("market") or _PHRASE.get(w.get("type"), "Serie")
    if held:
        return (f"✅ <b>{w.get('team')}s {phrase}-Serie hält</b> — "
                f"jetzt {(w.get('length') or 0) + 1}× in Folge. {icon}")
    return (f"❌ <b>{w.get('team')}s {phrase}-Serie gerissen</b> — "
            f"nach {w.get('length')} Spielen ist Schluss.")


def main() -> None:
    if not STREAKS_FILE.exists() or not WM_FILE.exists():
        print("❌ Streak-/Daten-Datei fehlt"); return
    streaks = (_load(STREAKS_FILE, {}) or {}).get("streaks") or []
    wm = _load(WM_FILE, {})
    state = _load(STATE_FILE, {"watched": {}})
    watched = state.setdefault("watched", {})
    today = date.today().isoformat()

    if MODE == "recap":
        msgs, done, buchungen = build_recap(wm, watched, today)
        pushes = recap_nachrichten(msgs)
        # `recap_nachrichten` gibt bauartbedingt hoechstens EINEN Eintrag zurueck. Der Deckel
        # hier ist trotzdem kein Doppelmoppel, sondern der maschinenlesbare Beleg dafuer:
        # `tests/test_push_deckel.py` prueft JEDE Sende-Schleife im Repo auf eine Grenze, die
        # an der Schleife selbst steht — ein Versprechen zwei Funktionen weiter oben kann der
        # Waechter nicht lesen, und genau so ein Versprechen ist am 12.09. gebrochen.
        send = PD.Deckel(tg_send, 1, "Serien-Recap")
        for m in pushes:
            send(m)
        for k in done:
            watched.pop(k, None)
        # `updatedAt` bei JEDEM Recap-Lauf setzen, auch ohne neue Zeile: sonst meldet die
        # Frische-Rechnung der Uebersicht das Buch als veraltet, obwohl es nur gerade nichts
        # abzurechnen gab. „Nichts passiert" und „laeuft nicht mehr" duerfen nicht gleich
        # aussehen — dieselbe Unterscheidung wie ueberall sonst hier.
        if buchungen or RECORD_FILE.exists():
            # Das Buch wird ANGEHAENGT, nie neu geschrieben: eine Zeile, die einmal drinsteht,
            # ist ein Messpunkt und kein Zwischenstand. Doppelte Keys koennen nicht entstehen,
            # weil der Eintrag im selben Lauf aus dem Watch faellt — geprueft wird es trotzdem.
            buch = _load(RECORD_FILE, {"zeilen": []})
            bekannt = {str(z.get("key")) for z in (buch.get("zeilen") or [])}
            neu_z = [b for b in buchungen if str(b.get("key")) not in bekannt]
            buch["zeilen"] = (buch.get("zeilen") or []) + neu_z
            buch["bilanz"] = bilanz(buch["zeilen"])
            buch["geprueftAm"] = datetime.now(timezone.utc).isoformat()
            buch["updatedAt"] = datetime.now(timezone.utc).isoformat()
            RECORD_FILE.write_text(json.dumps(buch, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
            print(f"📒 Serien-Buch: +{len(neu_z)} Zeilen, Bilanz: {buch['bilanz'].get('grund')}")
        # „wer pusht, misst den Push": die Zeile trennt abgerechnet / gepostet / stumm gebucht.
        # Am 12.09. stand hier „abgerechnet: 52 · Nachrichten: 52" und ich habe nur auf die
        # erste Zahl geschaut. Jetzt steht die stumme Menge explizit daneben.
        aufgeloest = sum(1 for b in buchungen if isinstance(b.get("erfuellt"), bool))
        print(f"📊 Serien-Recap: {len(done)} abgeschlossen · {aufgeloest} abgerechnet · "
              f"{len(msgs)} frisch · {aufgeloest - len(msgs)} stumm gebucht (Rueckstau) · "
              f"{len(pushes)} Nachricht(en) gesendet.")
    else:  # watch
        new = build_watch(streaks, wm, watched, today)
        if new:
            # 22.08.2026 (Lucas: „reicht 1 Nachricht am Tag"): EIN gebündelter Serien-Watch-Digest
            # statt einer Nachricht je Serie. Alle enthaltenen Serien werden NUR bei erfolgreichem
            # Send als bewacht markiert (all-or-nothing) → Recap-Kopplung bleibt intakt.
            digest = build_watch_digest([e for _k, e, _m in new])
            if tg_send(digest):
                for key, entry, _m in new:
                    watched[key] = entry
        print(f"🔥 Serien-Watch: {len(new)} Serie(n) → " + ("1 Sammel-Push" if new else "kein Push") + ".")

    _save_state(state)


if __name__ == "__main__":
    main()
