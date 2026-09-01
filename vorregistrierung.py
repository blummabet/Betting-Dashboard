"""Vorangemeldete Kandidaten — eingefroren am Tag der Idee, gemessen erst ab dann.

01.09.2026 (Lucas: „ja bau es mal"). Anlass war eine Zahl, die zum ersten Mal in diesem Projekt
eine ROI-Untergrenze ueber null zeigte: die Teilmenge der Poly-Rangliste, bei der ZUSAETZLICH
Betfair dieselbe Seite bestaetigt — n=75, ROI +18,1%, UG +1,1%.

Und genau deshalb darf sie noch nichts belegen. **57 dieser 75 Plays sind dieselben, aus denen die
Hypothese am 31.08. ueberhaupt erst gezogen wurde.** Ein Ausschnitt, den man nachtraeglich schneidet,
weil er gut aussieht, sieht immer gut aus — man hat ihn ja danach ausgesucht. Aus 500 Plays lassen
sich Dutzende solcher Teilmengen schneiden, und die beste davon liegt per Konstruktion oben.

Der einzige ehrliche Test ist deshalb: Zuschnitt, Richter und Ziel-n HEUTE festschreiben — und nur
zaehlen, was danach abgerechnet wird.

Drei Dinge macht dieses Modul, und jedes einzelne verhindert eine bekannte Selbsttaeuschung:

  1. **Vorwaerts messen.** Plays, die vor der Anmeldung abgerechnet wurden, gehen NIE ins Urteil.
     Sie laufen als `rueckblick` mit — sichtbar, aber ausdruecklich als Anlass gekennzeichnet, nicht
     als Beleg. (Dasselbe Muster wie `nAlt` bei den Engine-Versionen in freigabe.py: nicht
     verschweigen, aber auch nicht mitzaehlen.)
  2. **Den Zuschnitt einfrieren.** Die Definition wird bei der Anmeldung als Signatur abgelegt.
     Aendert sie jemand spaeter — auch nur eine Schwelle —, meldet die Schublade `ungueltig` statt
     stillschweigend etwas anderes zu messen. Ohne das waere „vorangemeldet" nur ein Wort: man
     verschiebt die Grenze, bis die Zahl passt, und nennt es weiterhin einen Vorwaerts-Test.
  3. **Das Ziel vorher nennen.** `zielN` steht bei der Anmeldung fest. Sonst hoert man auf zu
     messen, sobald es gut aussieht — der haeufigste Weg, aus Rauschen einen Beleg zu machen.

Das Urteil selbst faellt weiterhin freigabe.bewerte(): ROI-Untergrenze ueber null UND CLV-Untergrenze
nicht negativ. Ein Punktschaetzer ist kein Beleg — hier so wenig wie sonst.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
REG_FILE = "vorregistrierung.json"


def _now():
    return datetime.now(timezone.utc)


# ── Die Zuschnitte ───────────────────────────────────────────────────────────
# `pruef` bekommt EINEN abgerechneten Play und sagt ja/nein. `signatur` beschreibt den Zuschnitt in
# Worten UND in Parametern — sie wird bei der Anmeldung eingefroren. Wer den Zuschnitt aendert, muss
# die Signatur aendern, und dann faellt die Schublade auf `ungueltig`: eine stille Verschiebung der
# Grenze ist damit unmoeglich.
ZUSCHNITTE = {
    "poly_bf_bestaetigt": {
        "name": "Poly-Auswahl · von Betfair bestätigt",
        "strom": "poly",
        "quelle": "poly_shortlist_track.json → settled",
        "zielN": 60,
        "signatur": "signals enthaelt 'bf' | quelle=poly_shortlist_track.settled | rendite=pnl/stake | clv=clvPP",
        "warum": ("Die einzige Untergruppe der Rangliste mit einer ROI-Untergrenze ueber null. "
                  "Traegt nicht die Menge der Poly-Signale, sondern die eine FREMDE Stimme: "
                  "ohne Betfair liegen dieselben Plays bei -5,1% (n=425)."),
        "pruef": lambda x: "bf" in (x.get("signals") or []),
    },
    "buecher_score_hoch": {
        "name": "Bücher-Score ≥7 von 10",
        "strom": "betfair",
        "quelle": "punkte_ledger.json (killer.punkte_bilanz)",
        "zielN": 40,
        "signatur": "punkte>=7 und moeglich==10 | quelle=punkte_ledger | rendite=(odd-1|-1) | kein CLV",
        "warum": ("Lucas' These: wenn Betfair, Polymarket und Pinnacle sich EINIG sind, ist das eine "
                  "gute Wette. Gestuetzt durch die Messung „mehr Buecher traegt (+11,5%), mehr Signale "
                  "aus einem Buch nicht (-1,1%)\" — aber nie am Score selbst geprueft, den es vorher "
                  "nicht gab. Verlangt volle 10 moegliche Punkte: eine 7 aus 7 ist eine andere "
                  "Aussage als eine 7 aus 10 und darf den Test nicht verwaessern."),
        "pruef": lambda x: (x.get("moeglich") == 10 and isinstance(x.get("punkte"), int)
                            and x["punkte"] >= 7),
    },
}


# ── Anmeldung ────────────────────────────────────────────────────────────────
def anmelden(reg, kennung, now=None, rueckblick=None):
    """Einen Zuschnitt anmelden, falls noch nicht geschehen. Gibt das (evtl. neue) Register zurueck.

    Eine bestehende Anmeldung wird NIE ueberschrieben — der Zeitstempel ist der ganze Wert dieser
    Datei. Wer neu anmelden will, muss die alte Anmeldung sichtbar loeschen."""
    reg = dict(reg or {})
    if kennung in reg:
        return reg
    z = ZUSCHNITTE.get(kennung)
    if not z:
        return reg
    reg[kennung] = {
        "angemeldet": (now or _now()).isoformat(),
        "signatur": z["signatur"],
        "zielN": z["zielN"],
        # Der Anlass wird MITGESCHRIEBEN, damit spaeter niemand die Ruecksicht fuer den Beleg haelt
        # — und damit man sieht, ob die Vorwaerts-Messung den Rueckblick bestaetigt oder widerlegt.
        "rueckblick": rueckblick or None,
    }
    return reg


def _rendite(x):
    """Rendite je Play — zwei Buchformen, eine Zahl. REIN.

    Das Poly-Depot fuehrt `pnl`/`stake`, der Buecher-Gradient `odd`/`win`. Beide muessen hier
    ankommen: ein Zuschnitt, dessen Buch eine andere Form hat, wuerde sonst still LEER messen und
    ewig „0 von 40" melden — der Defekt, der sich als Geduld tarnt."""
    st = x.get("stake")
    try:
        st = float(st) if st is not None else None
    except (TypeError, ValueError):
        st = None
    p = x.get("pnl")
    if st and isinstance(p, (int, float)):
        return float(p) / st
    o, w = x.get("odd"), x.get("win")
    if isinstance(o, (int, float)) and o > 1 and isinstance(w, bool):
        return (o - 1.0) if w else -1.0
    return None


def _nach(ts, grenze):
    """True, wenn der Play NACH der Anmeldung abgerechnet wurde. Ohne lesbaren Zeitstempel: False —
    ein Play, dessen Zeitpunkt wir nicht kennen, koennte von vorher sein. Fehlende Information ist
    keine Erlaubnis, auch nicht hier."""
    if not ts or not grenze:
        return False
    try:
        a = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(grenze).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return a > b


def teilen(plays, kennung, eintrag):
    """(seit der Anmeldung, davor) fuer einen Zuschnitt. REIN.

    Gibt ([], []) zurueck, wenn die Signatur nicht mehr passt — dann misst hier niemand mehr etwas,
    und die Schublade meldet das ausdruecklich, statt einen anderen Zuschnitt weiterzuzaehlen."""
    z = ZUSCHNITTE.get(kennung)
    if not z or not isinstance(eintrag, dict):
        return [], []
    if eintrag.get("signatur") != z["signatur"]:
        return [], []
    grenze = eintrag.get("angemeldet")
    passt = [x for x in (plays or []) if isinstance(x, dict) and z["pruef"](x)]
    # settledTs (Poly-Depot) | settledAt (Buecher-Gradient) | resolvedTs (Altbestand)
    seit = [x for x in passt
            if _nach(x.get("settledTs") or x.get("settledAt") or x.get("resolvedTs"), grenze)]
    davor = [x for x in passt if x not in seit]
    return seit, davor


def kennzahlen(rows):
    """(Renditen, CLVs) — dieselbe Form, die freigabe.bewerte() erwartet. REIN."""
    r = [v for v in (_rendite(x) for x in rows) if v is not None]
    c = [float(x["clvPP"]) for x in rows if isinstance(x.get("clvPP"), (int, float))]
    return r, c


def signatur_bruch(reg, kennung):
    """True, wenn der Zuschnitt seit der Anmeldung geaendert wurde."""
    e = (reg or {}).get(kennung)
    z = ZUSCHNITTE.get(kennung)
    return bool(e and z and e.get("signatur") != z["signatur"])


def laden(pfad=None):
    try:
        return json.loads(Path(pfad or (BASE / REG_FILE)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def schreiben(reg, pfad=None):
    from safe_write import write_json_atomic
    write_json_atomic(Path(pfad or (BASE / REG_FILE)), reg, indent=1)
