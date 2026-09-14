#!/usr/bin/env python3
"""
push_shortlist_trades.py — 05.08.2026 (Lucas): die „Heute spielenswert"-Plays (die Shortlist ganz
oben im Screen) in den TRADES-Channel schicken, damit er die paar starken Plays immer mitkriegt.

Nutzt DENSELBEN Emitter wie der Paper-Tracker (scripts/emit_shortlist.mjs → echte poly-wallets.js-
Engine) → kein Drift zwischen Screen und Push. Dedup je Play (key|side): ein Play wird EINMAL
gepusht, erneut nur, wenn die Conviction steigt. Read-only auf die Daten, sendet nur Telegram.

Env:
  SHORTLIST_PUSH_MIN_CONV — Mindest-Conviction (Default 8 = „die klarsten")
  SHORTLIST_PUSH_MAX      — max Plays je Nachricht (Default 6)
  TELEGRAM_TOKEN + TELEGRAM_TRADES_CHAT_ID — ohne Token = Vorschau (stdout)
"""
from __future__ import annotations
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from telegram_trades import send_trades_message
from poly_shortlist_track import load_emit

BASE = Path(__file__).resolve().parent
SEEN_FILE = BASE / "shortlist_push_seen.json"

# 🔴 10.09.2026 (Lucas: „Heute spielenswert Trades — wird das erst seit kurzem getrackt? weil nur
# 23 in KW 37 und sonst nichts").
#
# Nein — es VERGISST. Die Stats-Seite las bis heute `shortlist_push_seen.json`, und das ist kein
# Ledger, sondern ein Dedup-Buch mit drei Tagen TTL: es raeumt sich bei jedem Lauf selbst auf.
# Mehr als drei Tage KANN dort nie stehen, und ein Ergebnis traegt es auch nicht. KW 36 war also
# nicht leer, weil nichts gepusht wurde, sondern weil die Datei es weggeworfen hatte.
#
# „Heute spielenswert" war damit als einziger der fuenf Push-Kanaele ohne eigenes Buch —
# Betfair-Public, Poly-Whales, Konjunktion und die Picks haben eins. Der Satz dazu steht in
# killer_push.py: **wer pusht, misst den Push.**
#
# Das Buch haelt fest, was zum Zeitpunkt des Sendens galt: den Preis, den ein Leser IN DEM MOMENT
# bekommen haette (nicht den aelteren Scan-Preis der Shortlist) und die Conviction von da.
# ⭐ Es rechnet NICHT selbst ab. Der Ausgang steht in `poly_shortlist_track.json`, das seit heute
# frueh weiss, wann ein Buendel-Markt ueberhaupt abrechnen darf — zwei Abrechnungen mit zwei
# Regeln waeren genau der Fehler, den poly_slug_urteil.py aufgeraeumt hat.
LEDGER_FILE = BASE / "shortlist_push_ledger.json"
LEDGER_KEEP = int(os.environ.get("SHORTLIST_PUSH_LEDGER_KEEP") or 800)

# 29.08.2026 (Lucas-Checkup, „D"): Default 8 → 7. Nicht weil die Latte sinken soll, sondern weil
# die Skala darunter weggerutscht ist: die Wallet-Neugewichtung nimmt gewichteten Plays rund einen
# Punkt. 8 auf der neuen Skala waere das alte 9 — also eine stille Verschaerfung, die niemand
# beschlossen hat. 7 haelt die Strenge, die vorher 8 war. Ueber SHORTLIST_PUSH_MIN_CONV weiter
# ueberschreibbar; zurueck auf die alte Zahl heisst: diese 7 wieder auf 8 setzen.
# 07.09.2026: 7 -> 6. Nicht als Lockerung — die Auswahl trifft ab jetzt das PUBLIC-TOR (s.
# select()), und dessen eigene Untergrenze ist 6. Bliebe hier 7 stehen, waere die Conviction
# heimlich das schaerfere Kriterium und das Tor haette nur die Haelfte seiner Wirkung.
MIN_CONV = int(os.environ.get("SHORTLIST_PUSH_MIN_CONV") or 6)
MAX_PLAYS = int(os.environ.get("SHORTLIST_PUSH_MAX") or 6)
MAX_PRICE = float(os.environ.get("SHORTLIST_PUSH_MAX_PRICE") or 0.92)   # Quasi-Locks raus (kein handelbarer Raum)
SEEN_TTL_DAYS = 3

_SPORT = {"TENNIS": "🎾", "ESPORTS": "🎮", "MLB": "⚾", "NBA": "🏀", "WNBA": "🏀",
          "NFL": "🏈", "NHL": "🏒", "MMA": "🥊", "UFC": "🥊", "GOLF": "⛳", "CRICKET": "🏏"}


def _icon(league) -> str:
    x = str(league or "").upper()
    if x in _SPORT:
        return _SPORT[x]
    if x.startswith("SOCCER") or any(t in x for t in ("LIGA", "MLS", "EPL", "UCL", "UEL", "BUNDES", "SERIE", "LIGUE", "EREDIV", "PRIMEIRA")):
        return "⚽"
    return "🎯"


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _cents(p) -> str:
    try:
        return "%d¢" % round(float(p) * 100)
    except (TypeError, ValueError):
        return ""


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def select(plays, blocked_cats=None):
    """Top-Plays der Shortlist: Conviction >= MIN_CONV, staerkste zuerst, gedeckelt. REIN/testbar.

    29.08.2026 (Lucas-Audit): die Sperrliste fehlte hier komplett. US-Sport und Kampfsport sind
    seit dem 24.08. vom Setzen und aus dem oeffentlichen Schaufenster ausgeschlossen — im
    Papier-Depot brachten sie ueber 78 Plays -29,6% ROI. Der Trades-Push zog sie trotzdem weiter,
    weil er `_pwTopPlays(0,false,false)` roh uebernahm. Die Kategorie steht seit dem 24.08. als
    `cat` an jedem Play und die Sperrliste als `blockedCats` im selben Emit — es wurde nur nie
    verglichen. Fehlt `cat` (aeltere Emits), bleibt der Play drin: nicht wissen ist kein Verbot,
    aber wir wissen es hier praktisch immer."""
    blocked = {str(c) for c in (blocked_cats or []) if c}

    def _ok_price(p):
        pr = p.get("price")
        return not (isinstance(pr, (int, float)) and pr >= MAX_PRICE)

    def _erlaubt(p):
        cat = p.get("cat")
        return not (cat and str(cat) in blocked)

    # 07.09.2026 (Lucas: „das haett ich gern dann halt auch als Push in den Trades Channel").
    #
    # Hier stand nur `conv >= MIN_CONV`. Damit war der Trades-Push eine VIERTE Menge — verschieden
    # von der Uebersichts-Kachel (Top 3 nach Score) und von den Public-Kandidaten (das Tor).
    # Nachgerechnet an 570 abgerechneten, spielbaren Plays:
    #
    #     Topf: alle spielbaren BET-Plays          n=570   63,3 %   +6,85 EUR    ROI +0,1 %
    #     Trades-Push bisher (conv>=7)             n=165   64,8 %   +42,86 EUR   ROI +2,6 %
    #     Public-Kandidaten (das Tor)              n=167   70,7 %   +107,22 EUR  ROI +6,4 %
    #
    # Praktisch dasselbe Volumen (7,5 gegen 8,0 Plays je Tag), zweieinhalbfacher Gewinn. Die
    # Conviction-Schwelle war eine Naeherung an „stark"; das Tor MISST es (Conviction >= 6 UND
    # Geld-Mehrheit >= 60 % UND bewiesene Wallet — bei E-Sport ab 55 Cent ohne die Wallet, weil
    # sie dort nachweislich nichts trennt).
    #
    # `public` steht seit dem 06.09. an jedem Play im selben Emit. MIN_CONV bleibt als zweite,
    # schwaechere Schranke stehen: das Tor beginnt bei 6, der Push soll nicht darunter rutschen,
    # falls jemand PW_PUBLIC_MIN_CONV senkt.
    _hat_flag = any(isinstance(p, dict) and "public" in p for p in (plays or []))

    def _tor(p):
        # Faellt das Feld (Alt-Emit), wird NICHT stillschweigend auf conv>=7 zurueckgefallen —
        # das waere die alte Menge unter neuem Namen. Dann pusht dieser Lauf lieber nichts und
        # sagt es (s. main). Fehlende Information ist keine Erlaubnis.
        return bool(p.get("public"))

    if not _hat_flag:
        return []
    out = [p for p in (plays or []) if isinstance(p, dict)
           and _tor(p) and (p.get("conv") or 0) >= MIN_CONV
           and p.get("verdict") in ("BET", "FADE")
           and _ok_price(p) and _erlaubt(p)]
    out.sort(key=lambda p: -(p.get("conv") or 0))
    return out[:MAX_PLAYS]


def _signale(x) -> set:
    """Die Signal-Menge eines Plays bzw. eines Buch-Eintrags. REIN."""
    if isinstance(x, dict):
        roh = x.get("signals") or x.get("sig") or []
    else:
        roh = []
    return {str(t) for t in roh if t}


def _angepfiffen(play) -> bool:
    """Laeuft das Spiel schon? `htk` ist die Zeit bis Anpfiff in Stunden, negativ ab Anpfiff.

    Fehlt die Zahl, gilt das Spiel als angepfiffen — bei einem RE-Push ist Schweigen der
    harmlose Default, nicht eine weitere Nachricht.
    """
    htk = play.get("htk")
    return not isinstance(htk, (int, float)) or htk < 0


def seen_eintrag(play, ts) -> dict:
    """Was ueber einen gepushten Play im Dedup-Buch stehen muss. REIN/testbar.

    Die Signal-Menge gehoert dazu: ohne sie kann der naechste Lauf „neue Evidenz" nicht von
    „dieselbe Evidenz, nur groessere Zahl" unterscheiden — und dann ist die Re-Push-Schranke
    zahnlos, ohne dass irgendwo etwas auffiele.
    """
    return {"conv": play.get("conv") or 0, "ts": ts, "sig": sorted(_signale(play))}


def fresh_plays(sel, seen):
    """NEU, oder vor Anpfiff mit NEUER Evidenz staerker geworden. REIN/testbar.

    🔴 14.09.2026 (Lucas: „aja der kam nun 3. mal — wieso wird der so wild in die Hoehe
    gepusht?"). Ostersunds FK, drei Karten in einer Stunde:

        16:20  conv 7   55,5¢
        16:50  conv 8   61,0¢
        17:20  conv 10  59,5¢   🔴 LIVE, 12. Minute

    Die alte Regel war „Conviction gestiegen". Das klang nach neuer Erkenntnis, ist es aber
    meistens nicht: das schwerste Einzelsignal der Karte ist `steam`, und Steam misst die
    Bewegung gegen ein festes 6-Stunden-Fenster (PW_MOVE_FENSTER_H). Dieselbe Bewegung waechst
    in diesem Fenster von selbst weiter — +2,5pp, +8,0pp, +8,5pp — und schiebt die Conviction
    mit hoch, ohne dass ein einziges neues Argument dazugekommen waere. Ein Mass, das sich
    selbst nachlaedt, wird so zum Wiederhol-Motor. Dieselbe Klasse wie der kumulative Drift
    im Sharp Radar, nur mit Geld dahinter.

    Zwei Bedingungen also, beide notwendig:
      · VOR Anpfiff. Nach dem Anpfiff ist „mehr Geld auf der fuehrenden Seite" keine Erkenntnis,
        sondern der Spielstand — und handeln kann man darauf ohnehin nicht mehr wie geplant.
      · NEUE Evidenz. Es muss ein Signal dazugekommen sein, das beim letzten Push nicht dabei
        war. Nur groesser gewordene Zahlen derselben Signale reichen nicht.

    Der erste Push eines Plays bleibt unberuehrt — auch live. Hier geht es allein um das
    Wiederholen.
    """
    seen = seen if isinstance(seen, dict) else {}
    out = []
    for p in sel:
        k = "%s|%s" % (p.get("key"), p.get("side"))
        prev = seen.get(k)
        if prev is None:
            out.append(p)                       # erster Push: unveraendert
            continue
        prev_conv = (prev.get("conv") if isinstance(prev, dict) else prev) or 0
        if (p.get("conv") or 0) <= prev_conv:
            continue
        if _angepfiffen(p):
            continue
        if not isinstance(prev, dict) or "sig" not in prev:
            # Alt-Eintrag ohne Signal-Liste: „neue Evidenz" ist nicht entscheidbar. Dann lieber
            # still — das Buch raeumt sich nach SEEN_TTL_DAYS selbst auf, der Fall heilt von
            # allein. Nicht wissen ist kein Grund zu senden.
            continue
        neue = _signale(p) - _signale(prev)
        if not neue:
            continue                            # dieselben Argumente, nur groessere Zahlen
        out.append(p)
    return out


def _spielminute(htk):
    """Aus den Stunden bis Anpfiff die gelaufene Spielzeit. htk ist negativ, wenn angepfiffen."""
    if not isinstance(htk, (int, float)) or htk >= 0:
        return None
    return int(round(-htk * 60))


def _line(p, vorher=None, position=None) -> str:
    conv = p.get("conv") or 0
    # 03.09.2026 (Lucas): „nur da war das Spiel schon 3:0 und in der 92. Minute oder so".
    # Ein blosses „🔴 LIVE" sagt nicht, ob gerade angepfiffen wurde oder nachgespielt wird.
    # Die Minute steht jetzt dran — und wo der Preis herkommt auch, denn genau das war der
    # Fehler: die Zahlen jener Nachricht stammten aus dem Close-Satz VOR Anpfiff.
    _min = _spielminute(p.get("htk"))
    live = ""
    if _min is not None:
        live = " 🔴 <b>LIVE</b> · %d. Min" % _min
        if p.get("preisQuelle") and p["preisQuelle"] != "live":
            live += " <i>(Preis aus dem Vorspiel-Satz)</i>"
    match = _esc(p.get("match") or p.get("key") or "?")
    price = _cents(p.get("price"))
    price_txt = (" @%s" % price) if price else ""
    reasons = " · ".join(_esc(r) for r in (p.get("reasons") or [])[:2])
    head = "<b>%d/10 · %s</b> · %s %s%s" % (conv, _esc(p.get("verdict") or ""), _icon(p.get("league")), match, live)
    pick = "→ <b>%s</b>%s" % (_esc(p.get("side") or "?"), price_txt)
    zeilen = [head, "   " + pick]
    zeilen += ["   " + z for z in kontext_zeilen(p, vorher, position)]
    if reasons:
        zeilen.append("   <i>%s</i>" % reasons)
    return "\n".join(zeilen)


def _uhr(ts) -> str:
    """HH:MM UTC aus einem ISO-Zeitstempel. Leer, wenn unlesbar — keine erfundene Uhrzeit."""
    from datetime import datetime as _d
    try:
        t = _d.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return ""
    return t.strftime("%H:%M")


def kontext_zeilen(play, vorher=None, position=None) -> list:
    """Was diese Karte ueber sich selbst wissen muss. REIN/testbar.

    🔴 14.09.2026 (Lucas: „A hso ich Trottel — das ja selbe Spiel"). Er war es nicht: der zweite
    Push zu Ostersunds FK (Conviction 7 -> 8, 55,5¢ -> 61¢) sah aus wie ein neuer Play. Die Karte
    sagte nirgends, dass sie eine VERSTAERKUNG ist und dass er seit einer halben Stunde drin ist.

    Beides steht laengst da, nur nicht in der Nachricht: das Dedup-Buch kennt die vorige
    Conviction (nur deshalb feuert der Push ueberhaupt erneut), und das Wett-Buch kennt die
    Position mit Preis und Zeit. Eine Nachricht, die den Leser zum Nachschlagen zwingt, hat ihre
    Aufgabe nicht erfuellt.

    Und die zweite Zeile beugt dem naechsten Missverstaendnis vor: der Auto-Play kauft NICHT
    nach (ein Play, eine Position). Wer „Verstaerkung" liest, erwartet sonst einen zweiten Trade.
    """
    aus = []
    v_conv = (vorher or {}).get("conv")
    if isinstance(v_conv, (int, float)) and (play.get("conv") or 0) > v_conv:
        wann = _uhr((vorher or {}).get("ts"))
        aus.append("🔁 <b>Verstärkung</b> — Conviction %d→%d%s"
                   % (v_conv, play.get("conv") or 0,
                      (" · erstmals %s UTC" % wann) if wann else ""))
    if position:
        preis = _cents(position.get("polyPrice"))
        wann = _uhr(position.get("placedAt"))
        try:
            einsatz = "$%.2f" % float(position.get("stake"))
        except (TypeError, ValueError):
            einsatz = "gesetzt"
        aus.append("🤖 du bist drin: %s%s%s — <b>kein Nachkauf</b>"
                   % (einsatz, (" @%s" % preis) if preis else "",
                      (" seit %s UTC" % wann) if wann else ""))
    return aus


# 14.09.2026: seit heute laeuft auf GENAU diese Plays ein Auto-Play ($5 je Wette). Die Fusszeile
# „Kein Auto-Bet" stand darunter weiter — zwei Nachrichten im selben Channel, die sich innerhalb
# von Sekunden widersprechen (der erste Live-Fall: Ostersunds FK, Push 16:20, Auto-Play 16:20).
# Der Schalter ist derselbe, den shortlist_auto_bet.py liest: eine Quelle, kein zweiter Zustand.
AUTO_AN = os.environ.get("SHORTLIST_AUTO_BET", "").strip() in ("1", "true", "yes", "on")


def fusszeile(auto_an=None, n_plays=None, n_gehalten=0) -> str:
    """Was unter dem Push steht — und es muss stimmen. REIN/testbar.

    Der Satz haengt an ZWEI Dingen, nicht an einem: laeuft der Auto-Play ueberhaupt, und sind
    die Plays dieser Nachricht schon im Depot? Eine reine Verstaerkungs-Karte darf nicht
    „werden automatisch nachgespielt" sagen — dann wartet der Leser auf eine Bestaetigung,
    die nie kommt (ein Play, eine Position).
    """
    an = AUTO_AN if auto_an is None else auto_an
    if not an:
        return "Kein Auto-Bet — deine Watchlist von oben. Selbst prüfen."
    n = n_plays if isinstance(n_plays, int) else None
    if n is not None and n_gehalten >= n > 0:
        return ("🤖 Alles oben läuft bereits — es wird <b>nicht</b> nachgekauft. "
                "Ein Play, eine Position.")
    if n_gehalten:
        return ("🤖 Die neuen Plays werden automatisch mit $5 nachgespielt (Bestätigung folgt "
                "als eigene Meldung); die bereits laufenden nicht.")
    return ("🤖 Diese Plays werden automatisch mit $5 nachgespielt — die Bestätigung kommt "
            "gleich als eigene Meldung. Der Einstieg dort kann leicht abweichen.")


def offene_positionen(pfad=None) -> dict:
    """{play-Schluessel: Wette} der OFFENEN Auto-Play-Positionen. Nie fatal — kann die Datei
    nicht gelesen werden, fehlt nur die Zeile „du bist drin", der Push geht trotzdem raus."""
    try:
        roh = _load(pfad or (BASE / "shortlist_auto_bets_placed.json"), {})
        aus = {}
        for b in (roh or {}).get("bets") or []:
            if isinstance(b, dict) and b.get("betKey") and not b.get("soldAt") \
                    and str(b.get("status") or "").lower() == "placed":
                aus[b["betKey"]] = b
        return aus
    except Exception:
        return {}


def build_message(plays, auto_an=None, seen=None, positionen=None) -> str:
    seen = seen if isinstance(seen, dict) else {}
    positionen = positionen if isinstance(positionen, dict) else {}

    def _k(p):
        return "%s|%s" % (p.get("key"), p.get("side"))

    def _vorher(p):
        v = seen.get(_k(p))
        return v if isinstance(v, dict) else ({"conv": v} if v else None)

    body = "\n\n".join(_line(p, _vorher(p), positionen.get(_k(p))) for p in plays)
    gehalten = sum(1 for p in plays if positionen.get(_k(p)))
    return ("🔥 <b>Heute spielenswert</b> — die klarsten Plays\n\n"
            + body
            + "\n\n" + fusszeile(auto_an, len(plays), gehalten))


def _push_preis(p):
    """Der Preis, den ein Leser im Moment des Pushs bekommen haette. REIN.

    `price` ist der Stand aus dem Emit, aus dem die Nachricht gebaut wird — genau der, der auch
    in der Push-Zeile steht. Ein spaeter besserer Einstieg gehoert nicht ins Buch: gemessen wird,
    was der Push wert war, nicht was mit perfektem Timing moeglich gewesen waere.
    """
    try:
        v = float(p.get("price"))
    except (TypeError, ValueError):
        return None
    return round(v, 4) if 0.0 < v < 1.0 else None


def buch_zeilen(plays, ts, gesendet=True) -> list:
    """Die Push-Zeilen zu diesen Plays. REIN/testbar.

    `gesendet=False` (Vorschau-Lauf ohne Token, oder Telegram hat abgelehnt) schreibt KEINE
    Zeile: ein Buch der Pushes darf nur enthalten, was gepusht wurde. „Wir haetten gesendet"
    ist keine Handlung, und eine Bilanz darauf waere erfunden.
    """
    if not gesendet:
        return []
    aus = []
    for p in (plays or []):
        if not isinstance(p, dict) or not p.get("key") or not p.get("side"):
            continue
        aus.append({"k": "%s|%s" % (p.get("key"), p.get("side")),
                    "key": p.get("key"), "side": p.get("side"),
                    # 14.09.2026: die lesbare Paarung mitschreiben. Der Slug ist als Schluessel
                    # richtig, aber als Anzeige unbrauchbar — „cs2-withou-lag-2026-09-13" sagt
                    # niemandem, welches Spiel das war. Der Auto-Play und das Trading-Cockpit
                    # zeigen sie jetzt; ohne dieses Feld muessten sie sie nachschlagen oder raten.
                    "match": p.get("match"),
                    "sentAt": ts, "conv": p.get("conv"),
                    "pushPreis": _push_preis(p),
                    "cat": p.get("cat"), "league": p.get("league")})
    return aus


def _buche_pushes(plays, ts, gesendet=True) -> int:
    """Die neuen Zeilen ans Buch haengen (rollierend). Nie fatal — ein Buchungsfehler darf den
    Push nicht nachtraeglich zum Fehlschlag machen."""
    zeilen = buch_zeilen(plays, ts, gesendet)
    if not zeilen:
        return 0
    try:
        alt = _load(LEDGER_FILE, [])
        alt = alt if isinstance(alt, list) else []
        _save(LEDGER_FILE, (alt + zeilen)[-LEDGER_KEEP:])
    except Exception as exc:
        print("  ℹ️  Push-Buch nicht geschrieben:", exc)
        return 0
    return len(zeilen)


def main() -> int:
    print("=== push_shortlist_trades.py ===")
    emit = load_emit()
    if not emit:
        print("  ℹ️  kein Emit — Shortlist-Push uebersprungen (nicht fatal).")
        return 0
    _plays = emit.get("plays") or []
    if _plays and not any(isinstance(p, dict) and "public" in p for p in _plays):
        # Alt-Emit ohne das `public`-Feld. Auf conv>=MIN_CONV zurueckzufallen waere die ALTE
        # Menge unter neuem Namen — und niemand wuerde es merken. Lieber nichts senden und es
        # sagen: der naechste Emit hat das Feld wieder.
        print("  ⚠️  Emit ohne `public`-Feld — es wird NICHTS gepusht. Der Push haengt seit dem "
              "07.09. am Public-Tor, nicht mehr an der Conviction; ein stiller Rueckfall waere "
              "eine andere Auswahl unter demselben Namen.")
        return 0
    sel = select(_plays, emit.get("blockedCats"))
    if not sel:
        print("  ℹ️  kein Play durch das Public-Tor (Conviction >= %d, Geld-Mehrheit, Wallet "
              "bzw. E-Sport ab 55 Cent)." % MIN_CONV)
        return 0
    seen = _load(SEEN_FILE, {})
    if not isinstance(seen, dict):
        seen = {}
    fresh = fresh_plays(sel, seen)
    if not fresh:
        print("  ℹ️  nichts Neues — alle %d Top-Plays schon gepusht." % len(sel))
        return 0
    sent = False
    try:
        sent = bool(send_trades_message(build_message(fresh, seen=seen,
                                                      positionen=offene_positionen())))
    except Exception as exc:
        print("  ℹ️  Shortlist-Push uebersprungen:", exc)
    now_iso = _now().isoformat()
    # 10.09.2026: gebucht wird, was WIRKLICH rausging (`fresh`), nicht die ganze Auswahl — `sel`
    # enthaelt auch die schon gepushten, die nur den Dedup-Stempel auffrischen.
    _buche_pushes(fresh, now_iso, sent)
    # alle aktuellen Top-Plays als „gesehen" markieren (auch die nicht-frischen → frischer ts, kein Re-Push)
    for p in sel:
        seen["%s|%s" % (p.get("key"), p.get("side"))] = seen_eintrag(p, now_iso)
    cutoff = _now().timestamp() - SEEN_TTL_DAYS * 86400
    seen = {k: v for k, v in seen.items()
            if not (isinstance(v, dict) and _parse(v.get("ts")) and _parse(v.get("ts")) < cutoff)}
    _save(SEEN_FILE, seen)
    print("  🔥 Shortlist-Push: %d neue Play(s) %s." % (len(fresh), "gesendet" if sent else "(Vorschau)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
