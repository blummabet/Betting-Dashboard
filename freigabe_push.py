"""freigabe_push.py — wenn eine Schublade freigegeben wird (oder es nicht mehr ist).

01.09.2026, Lucas wollte die Konjunktion im Trades-Channel mitlaufen sehen — und dazu das hier:
das EINE Ereignis, das sein Leitsatz beschreibt („ich muss wissen, was ich blind nachspielen kann,
weil das System es sagt"). Eine Schublade erreicht n≥30 mit ROI-Untergrenze über null, CLV nicht
negativ und frischer Datenbasis: ab dann darf man ihr folgen, ohne jede Zeile einzeln zu prüfen.

⭐ WARUM DAS EIN EIGENER PUSH IST UND KEIN TÄGLICHER STAND
Es passiert selten (aktuell: „nächste in 3 Plays", davor wochenlang nichts) und es ist ein
Zustands-WECHSEL, kein Wert. Ein täglicher „Stand"-Push würde ihn im Rauschen begraben; genau die
Nachricht, auf die es ankommt, sähe aus wie die 40 davor.

⭐ DIE RÜCKNAHME WIRD GENAUSO GEPUSHT
Eine Schublade kann eine Freigabe wieder VERLIEREN — das rollierende 500er-Fenster schiebt alte
Plays raus, die Untergrenze rutscht unter null, ein Engine-Sprung setzt die Stichprobe zurück.
Wer nur die Freigabe meldet und das Zurücknehmen verschweigt, baut genau die Asymmetrie ein, an
der dieses Projekt schon zweimal Geld verloren hat: gute Nachrichten kommen an, schlechte nicht.
Deshalb sind ⛔-Meldungen hier gleichberechtigt — und sie sind die wichtigeren.

Zustand in `freigabe_push_state.json`: Schublade → zuletzt gemeldeter Status. Kein Zustand heißt
ERSTLAUF, und ein Erstlauf meldet NICHTS: sonst fluteten beim ersten Start 38 Schubladen den
Channel und die erste echte Freigabe ginge darin unter.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import telegram_trades as TG

try:
    from zoneinfo import ZoneInfo
    LOKAL = ZoneInfo("Europe/Vienna")
except Exception:
    LOKAL = timezone.utc

BASE = Path(__file__).resolve().parent
STATE_FILE = BASE / "freigabe_push_state.json"
FREIGABE_FILE = BASE / "freigabe.json"
TRENNER = "━━━━━━━━━━━━━━━━━━━"
WOCHENTAG = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _now():
    return datetime.now(timezone.utc)


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _esc(s) -> str:
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _pct(v):
    # 08.09.2026: eine Nachkommastelle. Auf ganze Prozent gerundet stand bei „Liga · ABWAEGEN"
    # eine Untergrenze von +0,76 % als „+1%" da — und die beiden heute freigegebenen Schubladen
    # liegen bei +2,3 % und +0,8 %. Genau in diesem Bereich entscheidet die Nachkommastelle, ob
    # die Zahl etwas sagt. Dieselbe Korrektur wie auf dem Board.
    return "—" if v is None else ("%+.1f%%" % (float(v) * 100))


def wechsel(freigabe, state) -> tuple[list, list, dict]:
    """(neu_freigegeben, zurueckgenommen, neuer_zustand).

    Verglichen wird ausschließlich „freigegeben ja/nein" — die Zwischenstufen (sammelt, kandidat,
    geprueft) wechseln ständig und sind keine Nachricht wert.
    """
    alle = (freigabe or {}).get("alle") or []
    neuer = {}
    for r in alle:
        name = str(r.get("schublade") or "")
        if name:
            neuer[name] = bool(r.get("status") == "freigegeben")
    if not state:
        return [], [], neuer                      # Erstlauf: nur lernen, nicht melden
    zeilen = {str(r.get("schublade") or ""): r for r in alle}
    rauf, runter = [], []
    for name, ist in neuer.items():
        war = state.get(name)
        if war is None:
            continue                              # neue Schublade: erst kennenlernen
        if ist and not war:
            rauf.append(zeilen.get(name) or {"schublade": name})
        elif war and not ist:
            runter.append(zeilen.get(name) or {"schublade": name})
    return rauf, runter, neuer


# ── 08.09.2026: der Push, der Lucas wirklich fehlte ─────────────────────────────────────
# „also es wird nur das geschickt, aber nicht welche Spiele — na dann brauch ich das eher nicht."
#
# Der Wechsel „Schublade freigegeben" ist selten und richtig als eigenes Ereignis. Aber er ist
# eine Aussage ueber die Vergangenheit; handeln kann man erst mit den offenen Plays, die heute
# unter dieselbe Definition fallen. Die kommen jetzt als ZWEITE Art Nachricht.
#
# ⭐ WARUM EIN EIGENER ZUSTAND JE PLAY UND NICHT „taeglich die Liste"
# Eine taegliche Liste mit 31 Zeilen ist nach drei Tagen Tapete: 29 davon standen gestern schon
# da. Gemeldet wird deshalb, was NEU dazugekommen ist — dieselbe Regel wie bei der Schublade
# selbst, nur eine Ebene tiefer. Abgelaufene Plays verschwinden still aus dem Zustand; ein
# „Spiel angepfiffen"-Push waere Rauschen ueber etwas, das man ohnehin nicht mehr tun kann.
#
# ⚠️ NICHT AUFLOESBARE SCHUBLADEN ERZEUGEN KEINEN PLAY-PUSH und auch keinen Zustand. Sonst
# stuende beim naechsten Lauf „0 Spiele" fuer eine Schublade, ueber deren Spiele wir gar nichts
# wissen — genau die Verwechslung, gegen die `aufloesbar` gebaut ist.
PLAY_MAX = 12          # so viele Plays je Schublade in EINER Nachricht; darueber wird gezaehlt


def play_wechsel(freigabe, state) -> tuple[dict, dict]:
    """({schublade: [neue Plays]}, neuer Play-Zustand).

    Erstlauf (kein Zustand fuer diese Schublade) meldet NICHTS: sonst fluteten beim ersten Lauf
    31 Picks den Channel, und der erste echte Neuzugang ginge darin unter. Dieselbe Regel wie
    beim Schublade-Zustand, und aus demselben Grund.
    """
    alt_state = (state or {}).get("plays") or {}
    neu_state, meldung = {}, {}
    for b in ((freigabe or {}).get("spiele") or []):
        if not b.get("aufloesbar"):
            continue                                  # kein Wissen ist kein Zustand
        name = str(b.get("schublade") or "")
        if not name:
            continue
        ids = [str(p.get("id")) for p in (b.get("plays") or []) if p.get("id")]
        neu_state[name] = ids
        vorher = alt_state.get(name)
        if vorher is None:
            continue                                  # Erstlauf dieser Schublade: nur lernen
        bekannt = set(vorher)
        frisch = [p for p in (b.get("plays") or []) if str(p.get("id")) not in bekannt]
        if frisch:
            meldung[name] = frisch
    return meldung, neu_state


def _play_zeile(p) -> str:
    q = p.get("quote")
    teile = ["▸ <b>%s</b> — %s%s" % (_esc(p.get("spiel")), _esc(p.get("auswahl")),
                                     (" @%.2f" % float(q)) if isinstance(q, (int, float)) else "")]
    ko = p.get("anpfiff")
    if ko:
        try:
            t = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            _l = t.astimezone(LOKAL)
            # `%a` liefert unter der C-Locale des CI-Runners „Fri"/„Sat" — in einer sonst
            # deutschen Nachricht liest sich das wie ein Fremdkoerper, und eine Locale zu setzen
            # waere eine Abhaengigkeit vom Runner-Image. Drei Buchstaben aus einer Liste sind
            # billiger und laufen ueberall gleich.
            teile.append("   🕐 %s %s" % (WOCHENTAG[_l.weekday()], _l.strftime("%d.%m. %H:%M")))
        except (ValueError, TypeError):
            pass
    for g in (p.get("warum") or [])[:1]:
        teile.append("   %s" % _esc(g))
    return "\n".join(teile)


def play_nachricht(meldung, freigabe) -> str:
    """Die Spiele-Nachricht. Je Schublade ihr Kopf mit der Untergrenze — ohne die liest sich
    die Liste wie eine Tipp-Empfehlung statt wie „aus diesem belegten Schnitt"."""
    kopf = {str(b.get("schublade") or ""): b for b in ((freigabe or {}).get("spiele") or [])}
    bloecke = []
    for name, plays in meldung.items():
        b = kopf.get(name) or {}
        z = ["🎯 <b>%s</b>" % _esc(name)]
        _ug = b.get("roiLb")
        if _ug is not None:
            z.append("<i>freigegeben · Rendite-Untergrenze %s</i>" % _pct(_ug))
        if b.get("clvUrteil") == "negativ belegt":
            z.append("⚠️ <i>CLV spricht gegen diese Schublade — freigegeben auf die Rendite.</i>")
        z.append("")
        z.append("\n".join(_play_zeile(p) for p in plays[:PLAY_MAX]))
        if len(plays) > PLAY_MAX:
            z.append("… und %d weitere." % (len(plays) - PLAY_MAX))
        bloecke.append("\n".join(z))
    teile = ["🆕 <b>NEUE SPIELE AUS FREIGEGEBENEN SCHUBLADEN</b>", TRENNER,
             "<i>Diese offenen Plays fallen unter einen Schnitt, dessen Rendite-Untergrenze über "
             "null liegt. Es sind Kandidaten aus einer belegten Schublade — keine Einzelprüfung.</i>",
             ""] + bloecke
    teile += ["", "🕐 %s" % _now().astimezone(LOKAL).strftime("%d.%m.%Y %H:%M %Z")]
    return "\n".join(teile)


def _zeile(r, grund: bool = True) -> str:
    """Immer ROI UND Untergrenze — der Punktschätzer allein hat hier schon dreimal getäuscht.
    Der `grund` aus freigabe.py sagt bei einer Rücknahme, WELCHE Bedingung gekippt ist; ohne ihn
    wäre die Nachricht ein Alarm ohne Ursache.

    08.09.2026: bei einer FREIGABE sagt derselbe `grund` inzwischen dasselbe wie die Zeilen
    darüber (ROI-Untergrenze plus CLV-Urteil) — zweimal dieselbe Warnung liest sich beim dritten
    Push wie Formelsprache und wird überblättert. Deshalb steht er nur noch bei der Rücknahme,
    wo er die einzige Auskunft über die gekippte Bedingung ist."""
    zeilen = ["🔓 <b>%s</b>" % _esc(r.get("schublade"))]
    zeilen.append("📊 n=%s · ROI %s · <b>Untergrenze %s</b>"
                  % (r.get("n", "—"), _pct(r.get("roi")), _pct(r.get("roiLb"))))
    clv = r.get("clv")
    if clv is not None:
        zeilen.append("📈 CLV %+.1fpp%s" % (float(clv),
                      ("  (UG %+.2f)" % float(r["clvLb"])) if r.get("clvLb") is not None else ""))
    # 08.09.2026 (Lucas: „ja Freigabe locker"). Seit das Tor allein die ROI-Untergrenze ist, muss
    # der CLV in der NACHRICHT stehen — nicht nur auf dem Board. Wer den Push liest, spielt
    # danach; er darf die einzige Warnung, die es zu dieser Freigabe noch gibt, nicht nur im
    # Frontend finden. Vier Zustaende, und „nicht erhoben" ist ausdruecklich kein Nein.
    _u = r.get("clvUrteil")
    if _u == "negativ belegt":
        zeilen.append("⚠️ <b>CLV spricht dagegen</b> — Obergrenze unter null. In unseren Daten "
                      "liefen Schubladen mit negativem CLV im Schnitt −6,8 %. Freigegeben auf "
                      "die Rendite, nicht auf eine gemessene Kante.")
    elif _u == "nicht erhoben":
        zeilen.append("❔ Fuer diese Schublade wird gar kein CLV erhoben — unbekannt ist kein "
                      "Nein, aber auch kein Ja.")
    elif _u == "gemessen, nicht belegt":
        zeilen.append("❔ CLV gemessen, aber weder ueber noch unter null belegt.")
    if grund and r.get("grund"):
        zeilen.append("🧭 %s" % _esc(r["grund"]))
    return "\n".join(zeilen)


def nachricht(rauf, runter, freigabe) -> str:
    """Hausstil der übrigen Trades-Pushes: Titel · Trenner · Block · Fusszeile.

    ⭐ Steht beides an (eine rauf, eine runter), kommt die RÜCKNAHME zuerst. Sie ist die
    Nachricht, die Geld spart; die Freigabe kann warten. Eine Nachricht, die mit ✅ beginnt,
    wird überflogen — die ⛔-Zeile darunter dann mit.
    """
    teile = []
    if runter:
        teile += ["⛔ <b>FREIGABE ZURÜCKGENOMMEN</b>", TRENNER,
                  "<i>Diese Schublade ist NICHT mehr blind spielbar.</i>", "",
                  "\n\n".join(_zeile(r) for r in runter)]
    if rauf:
        if teile:
            teile.append("")
        # 08.09.2026: „die Untergrenze" war frueher eindeutig — es mussten beide stimmen.
        # Seit das Tor allein die RENDITE-Untergrenze ist, muss genau das dastehen; sonst liest
        # sich die Zeile wie eine Zusicherung, die sie nicht mehr ist.
        teile += ["✅ <b>FREIGEGEBEN</b>", TRENNER,
                  "<i>Ab jetzt blind spielbar — die <b>Rendite</b>-Untergrenze liegt über null. "
                  "Was der CLV dazu sagt, steht je Schublade darunter.</i>", "",
                  "\n\n".join(_zeile(r, grund=False) for r in rauf)]
    # Die Regel steht nur an der FREIGABE — dort ist „was heisst freigegeben eigentlich?" die
    # Frage. Bei einer Ruecknahme beantwortet der `grund` sie bereits konkret, und die lange
    # Regelzeile wuerde die eine Zeile verwaessern, auf die es ankommt.
    regel = ((freigabe or {}).get("regeln") or {}).get("text") or ""
    fuss = [""]
    if regel and rauf:
        fuss.append("📐 %s" % _esc(regel))
    eng = (freigabe or {}).get("engine")
    if eng and (freigabe or {}).get("engineGefiltert") is True:
        fuss.append("⚙️ Engine <code>%s</code> — ältere Plays zählen nicht mit." % _esc(eng))
    fuss.append("🕐 %s" % _now().astimezone(LOKAL).strftime("%d.%m.%Y %H:%M %Z"))
    return "\n".join(teile + fuss)


def main() -> int:
    trocken = str(os.environ.get("DRY_RUN") or "").lower() in ("1", "true", "yes")
    fg = _load(FREIGABE_FILE, None)
    if not fg or not (fg.get("alle") or []):
        # Fehlende Information ist keine Erlaubnis — und auch kein Anlass, den Zustand zu
        # überschreiben. Eine unlesbare Datei darf nicht wie „nichts mehr freigegeben" wirken
        # und beim nächsten Lauf ⛔-Meldungen für alles auslösen.
        print("[freigabe_push] freigabe.json fehlt oder ist leer — Zustand bleibt unangetastet")
        return 0
    state = _load(STATE_FILE, None)
    # Alte Zustandsdateien sind eine flache Abbildung {Schublade: bool}; seit dem 08.09. liegt
    # daneben `plays`. Beides in EINER Datei, damit ein Sendefehler nicht die eine Haelfte
    # fortschreibt und die andere nicht.
    if isinstance(state, dict) and "schubladen" in state:
        st_schubladen, st_plays = state.get("schubladen"), state
    elif isinstance(state, dict):
        st_schubladen, st_plays = {k: v for k, v in state.items() if isinstance(v, bool)}, {}
    else:
        st_schubladen, st_plays = None, {}
    erstlauf = state is None
    rauf, runter, neuer = wechsel(fg, st_schubladen)
    meldung, neue_plays = play_wechsel(fg, st_plays)

    gesendet = True
    if rauf or runter:
        ok = True if trocken else TG.send_trades_message(nachricht(rauf, runter, fg))
        if not ok:
            print("[freigabe_push] Senden fehlgeschlagen — Zustand NICHT fortgeschrieben, "
                  "nächster Lauf meldet denselben Wechsel erneut")
            return 0                              # Zustand bleibt, damit die Meldung nicht verfällt
        print("[freigabe_push] %d freigegeben, %d zurückgenommen%s"
              % (len(rauf), len(runter), " (DRY_RUN)" if trocken else ""))
    else:
        print("[freigabe_push] kein Schubladen-Wechsel"
              + (" (Erstlauf: Zustand gelernt)" if erstlauf else ""))

    if meldung:
        gesendet = True if trocken else TG.send_trades_message(play_nachricht(meldung, fg))
        if not gesendet:
            # Der Schubladen-Zustand ist an dieser Stelle schon gemeldet und darf fortgeschrieben
            # werden; der PLAY-Zustand nicht, sonst gelten die neuen Plays als gemeldet, ohne dass
            # sie je jemand gesehen hat. Deshalb wird nur dieser Teil zurueckgehalten.
            print("[freigabe_push] Spiele-Nachricht fehlgeschlagen — Play-Zustand NICHT "
                  "fortgeschrieben, nächster Lauf meldet dieselben Spiele erneut")
        else:
            print("[freigabe_push] %d Schubladen mit neuen Spielen (%d Plays)%s"
                  % (len(meldung), sum(len(v) for v in meldung.values()),
                     " (DRY_RUN)" if trocken else ""))
    _save(STATE_FILE, {"schubladen": neuer,
                       "plays": neue_plays if gesendet else ((st_plays or {}).get("plays") or {})})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
