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
    return "—" if v is None else ("%+d%%" % round(float(v) * 100))


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


def _zeile(r) -> str:
    """Immer ROI UND Untergrenze — der Punktschätzer allein hat hier schon dreimal getäuscht.
    Der `grund` aus freigabe.py sagt bei einer Rücknahme, WELCHE Bedingung gekippt ist; ohne ihn
    wäre die Nachricht ein Alarm ohne Ursache."""
    zeilen = ["🔓 <b>%s</b>" % _esc(r.get("schublade"))]
    zeilen.append("📊 n=%s · ROI %s · <b>Untergrenze %s</b>"
                  % (r.get("n", "—"), _pct(r.get("roi")), _pct(r.get("roiLb"))))
    clv = r.get("clv")
    if clv is not None:
        zeilen.append("📈 CLV %+.1fpp%s" % (float(clv),
                      ("  (UG %+.2f)" % float(r["clvLb"])) if r.get("clvLb") is not None else ""))
    if r.get("grund"):
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
        teile += ["✅ <b>FREIGEGEBEN</b>", TRENNER,
                  "<i>Ab jetzt blind spielbar — die Untergrenze liegt über null.</i>", "",
                  "\n\n".join(_zeile(r) for r in rauf)]
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
    erstlauf = state is None
    rauf, runter, neuer = wechsel(fg, state)

    if rauf or runter:
        ok = True if trocken else TG.send_trades_message(nachricht(rauf, runter, fg))
        if not ok:
            print("[freigabe_push] Senden fehlgeschlagen — Zustand NICHT fortgeschrieben, "
                  "nächster Lauf meldet denselben Wechsel erneut")
            return 0                              # Zustand bleibt, damit die Meldung nicht verfällt
        print("[freigabe_push] %d freigegeben, %d zurückgenommen%s"
              % (len(rauf), len(runter), " (DRY_RUN)" if trocken else ""))
    else:
        print("[freigabe_push] kein Wechsel" + (" (Erstlauf: Zustand gelernt)" if erstlauf else ""))
    _save(STATE_FILE, neuer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
