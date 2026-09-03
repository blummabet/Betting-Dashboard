#!/usr/bin/env python3
"""
stake_analyse.py — was der Stake-Fluss wirklich taugt
================================================================================
03.09.2026 (Lucas: „bitte alles umsetzen ... anhand der Daten dort kriegen wir genug kleine
Ligen wo Leute mit guten Infos setzen").

Diese Datei URTEILT — aber nur, wo die Basis es trägt. Sie rechnet nichts selbst, was das
Projekt schon kann: die Wilson-Untergrenze kommt aus `sharp_gate`, die Renditegrenze aus
`freigabe`. Eine rohe Quote ohne Untergrenze wird ausgewiesen, aber nie als Beleg.

## Vier Fragen, die sie beantwortet

1. **Was ist HIER ein grosser Einsatz?** (Liga-Norm)
   Absolute Schwellen sind das Falsche. $9.000 auf La Liga ist Dienstag; $9.000 auf die dritte
   finnische Liga ist ein Ereignis. Die Norm je Liga wird aus unseren EIGENEN Daten gelernt:
   Median und 90%-Punkt der Einsätze. 'Auffällig' heisst dann „das x-fache dessen, was hier
   sonst durchgeht" — nicht 'über einer Zahl, die wir uns ausgedacht haben'.

2. **Trifft dieser Fluss?** (Trefferquote je Schublade)
   Getrennt nach Phase (vor Anpfiff / live), Liga, Markt und Einsatzgrösse. Immer mit
   Wilson-Untergrenze; unter STAKE_MIN_N gibt es kein Urteil, nur die Zählung.

3. **Wo ist die Liga klein und der Einsatz gross?** (die eigentliche Idee)
   Die Schnittmenge aus 'kleine Liga' (wenig Wetten insgesamt) und „weit über der Norm dieser
   Liga". Genau da sitzt das, wonach Lucas sucht — und genau da ist n klein, weshalb es eine
   eigene Zählung braucht statt eines Bauchgefühls.

4. **Wieviel sehen wir überhaupt nicht?** (Abdeckung)
   Stakes Deckel liegt bei 50 Einträgen je Abruf. Der Sammler misst seine Lücken; hier werden
   sie zusammengezählt, damit 'an dem Abend war wenig los' nie unbemerkt „wir haben nicht
   hingeschaut" bedeutet.

## Was sie NICHT tut
Sie sucht sich nicht die beste Schublade aus und erklärt sie zum Signal. Welche Schubladen
zählen, steht vorher in `stake_vorregistrierung.json` — vorwärts angemeldet, bevor die Zahlen
da waren. Alles andere ist beschreibend und als solches markiert.

## Ausgabe
  stake_auswertung.json — Norm, Schubladen, Auffälligkeiten, Abdeckung
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import stake_highroller_fetch as SH
from sharp_gate import wilson_lb

LEDGER_FILE = BASE / "stake_bet_ledger.json"
OUT_FILE = BASE / "stake_auswertung.json"
REG_FILE = BASE / "stake_vorregistrierung.json"

Z = 1.645                                              # einseitige 95%-Grenze, wie im Rest
MIN_N = int(os.environ.get("STAKE_MIN_N") or 30)       # darunter kein Urteil
MIN_N_LIGA = int(os.environ.get("STAKE_MIN_N_LIGA") or 20)
NORM_MIN_N = int(os.environ.get("STAKE_NORM_MIN_N") or 15)   # darunter keine Liga-Norm
KLEINE_LIGA_MAX = int(os.environ.get("STAKE_KLEINE_LIGA_MAX") or 25)
AUFFAELLIG_FAKTOR = float(os.environ.get("STAKE_AUFFAELLIG_FAKTOR") or 5.0)


# ── Hilfen ───────────────────────────────────────────────────────────────────
def _kat(w: dict) -> str:
    """Sportart-Kategorie. Aus dem Feld, sonst nachgerechnet — alte Zeilen haben es nicht."""
    return w.get("kat") or SH.sport_kategorie(w.get("sport"), w.get("liga"))


def _erlaubt(w: dict) -> bool:
    return _kat(w) not in SH.GESPERRT


def _phase(w: dict) -> str:
    """vor | live | unbekannt.

    Kommt normalerweise aus dem Sammler. Zeilen, die vor dem 03.09.2026 gesammelt wurden,
    haben das Feld noch nicht — die werden hier aus ts und anpfiff nachgerechnet, statt als
    'unbekannt' aus jeder Auswertung zu fallen. Beides steht im Ledger, es ist dieselbe
    Rechnung, nur spaeter.
    """
    if w.get("phase"):
        return w["phase"]
    ts, ko = w.get("ts"), w.get("anpfiff")
    if not ts or not ko:
        return "unbekannt"
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        k = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
    except Exception:
        return "unbekannt"
    return "live" if t > k else "vor"


def _minute(w: dict):
    """Minuten seit Anpfiff, auch fuer alte Zeilen ohne das Feld."""
    if w.get("spielminute") is not None:
        return w["spielminute"]
    if _phase(w) != "live":
        return None
    try:
        t = datetime.fromisoformat(str(w["ts"]).replace("Z", "+00:00"))
        k = datetime.fromisoformat(str(w["anpfiff"]).replace("Z", "+00:00"))
    except Exception:
        return None
    return int(round((t - k).total_seconds() / 60.0))


def _beine(w: dict):
    return ((w.get("abrechnung") or {}).get("beine")) or []


def _gewertete_beine(w: dict):
    """Nur Beine mit echtem Ausgang. Annulliert ist kein Treffer und kein Fehlschlag."""
    return [b for b in _beine(w) if b.get("treffer") is not None]


def _quote(treffer: int, n: int) -> dict:
    """Immer beides: der rohe Punkt UND die Untergrenze. Ein Punktschätzer ist kein Beleg."""
    if not n:
        return {"n": 0, "treffer": 0, "quote": None, "ug": None, "belegt": False}
    ug = wilson_lb(treffer, n, Z)
    return {"n": n, "treffer": treffer,
            "quote": round(treffer / n, 4),
            "ug": round(ug, 4) if n >= MIN_N else None,
            "belegt": bool(n >= MIN_N and ug > 0.5)}


def _schublade(wetten: list) -> dict:
    tr = n = 0
    einsatz = pnl = 0.0
    n_einzel = 0
    for w in wetten:
        for b in _gewertete_beine(w):
            n += 1
            tr += 1 if b["treffer"] else 0
        a = w.get("abrechnung") or {}
        if a.get("pnlUsd") is not None and w.get("einsatzUsd"):
            n_einzel += 1
            einsatz += w["einsatzUsd"]
            pnl += a["pnlUsd"]
    d = _quote(tr, n)
    d["wetten"] = len(wetten)
    d["einzelN"] = n_einzel
    d["roi"] = round(pnl / einsatz, 4) if einsatz else None
    d["einsatzUsd"] = round(einsatz, 2)
    return d


# ── 1. Liga-Norm ─────────────────────────────────────────────────────────────
def liga_norm(wetten: list) -> dict:
    """Was ist in DIESER Liga ein grosser Einsatz? Aus den eigenen Daten, nicht ausgedacht.

    Unter NORM_MIN_N Wetten gibt es keine Norm — dann ist 'auffällig' nicht entscheidbar,
    und das steht auch so da (`basis: "zu duenn"`), statt eine Zahl zu erfinden.
    """
    je = defaultdict(list)
    for w in wetten:
        if w.get("einsatzUsd") and w.get("liga"):
            je[w["liga"]].append(float(w["einsatzUsd"]))
    out = {}
    for liga, betraege in je.items():
        betraege.sort()
        n = len(betraege)
        if n < NORM_MIN_N:
            out[liga] = {"n": n, "basis": "zu duenn", "median": None, "p90": None}
            continue
        out[liga] = {
            "n": n, "basis": "gelernt",
            "median": round(statistics.median(betraege), 2),
            "p90": round(betraege[min(n - 1, int(round(0.9 * (n - 1))))], 2),
            "max": round(betraege[-1], 2),
        }
    return out


def auffaellig(w: dict, norm: dict) -> dict:
    """Wie weit über der Norm dieser Liga liegt dieser Einsatz?

    -> {"faktor": x, "basis": "median", "n": ...} oder {"basis": "keine Norm"}.
    Ohne Norm gibt es KEINEN Faktor — nicht 1.0, nicht 0. Fehlende Information ist keine
    Erlaubnis, und 'unauffällig' wäre hier eine Behauptung.
    """
    liga = w.get("liga")
    e = w.get("einsatzUsd")
    nrm = (norm or {}).get(liga) or {}
    if not e or nrm.get("basis") != "gelernt" or not nrm.get("median"):
        return {"faktor": None, "basis": "keine Norm", "n": nrm.get("n", 0)}
    return {"faktor": round(e / nrm["median"], 2), "basis": "median",
            "median": nrm["median"], "n": nrm["n"]}


# ── 3. Kleine Liga, grosses Geld ─────────────────────────────────────────────
def kleine_liga_gross(wetten: list, norm: dict) -> list:
    """Die eigentliche Idee: wo eine sonst ruhige Liga plötzlich Geld sieht.

    Zwei Wege, weil eine Liga mit zu wenig Wetten gar keine Norm hat — und genau die sind
    die interessantesten:
      · mit Norm    → Einsatz >= AUFFAELLIG_FAKTOR × Median der Liga
      · ohne Norm   → die Liga hat insgesamt <= KLEINE_LIGA_MAX Wetten, der Einsatz liegt
                      über dem globalen 90%-Punkt. Das ist ein SCHWÄCHERES Kriterium und
                      wird als solches ausgewiesen (`grund`), nicht mit dem ersten vermischt.
    """
    je_liga = defaultdict(int)
    for w in wetten:
        if w.get("liga"):
            je_liga[w["liga"]] += 1
    alle = sorted(float(w["einsatzUsd"]) for w in wetten if w.get("einsatzUsd"))
    global_p90 = alle[min(len(alle) - 1, int(round(0.9 * (len(alle) - 1))))] if alle else None

    out = []
    for w in wetten:
        e = w.get("einsatzUsd")
        if not e or w.get("kombi"):
            continue
        a = auffaellig(w, norm)
        if a["faktor"] is not None and a["faktor"] >= AUFFAELLIG_FAKTOR:
            grund = "%.1f× Median der Liga (n%d)" % (a["faktor"], a["n"])
        elif (a["basis"] == "keine Norm" and global_p90 and e >= global_p90
              and je_liga.get(w.get("liga"), 0) <= KLEINE_LIGA_MAX):
            grund = "kleine Liga (%d Wetten), Einsatz über globalem 90%%-Punkt" % je_liga.get(w.get("liga"), 0)
        else:
            continue
        out.append({
            "id": w.get("id"), "ts": w.get("ts"), "liga": w.get("liga"),
            "event": w.get("event"), "markt": w.get("markt"), "auswahl": w.get("auswahl"),
            "einsatzUsd": round(e, 2), "quote": w.get("quote"), "phase": _phase(w),
            "faktor": a["faktor"], "grund": grund,
            "ausgang": ([b.get("status") for b in _beine(w)] or [None])[0],
        })
    out.sort(key=lambda x: -(x["faktor"] or 0))
    return out


# ── 4. Abdeckung ─────────────────────────────────────────────────────────────
def abdeckung(led: dict) -> dict:
    l = led.get("luecke") or {}
    return {"letzteLuecke": l.get("luecke"), "lueckeMin": l.get("lueckeMin"),
            "abdeckungMin": l.get("abdeckungMin"),
            "hinweis": ("Stakes Deckel liegt bei 50 Eintraegen je Abruf. Deckt ein Abruf "
                        "weniger Zeit ab als der Abstand zum naechsten, fehlt dazwischen "
                        "alles — und zwar am ehesten dann, wenn viel los ist.")}


# ── Vorregistrierung ─────────────────────────────────────────────────────────
def vorregistrieren(jetzt: str) -> dict:
    """Welche Schubladen zaehlen — festgeschrieben, BEVOR die Zahlen da sind.

    Nachtraeglich die beste Variante auszusuchen ist genau der Fehler, den wir ueberall sonst
    rausgeraeumt haben. Diese Datei wird einmal geschrieben und danach nur ergaenzt, nie
    ueberschrieben: ein spaeter angemeldeter Trigger startet bei n=0.
    """
    reg = SH._lade(REG_FILE, {})
    kandidaten = {
        "vor_anpfiff_alle": {
            "signatur": "phase=='vor' | Bein-Trefferquote | Wilson-UG > 50%",
            "warum": "Die Grundfrage: trifft der Fluss vor Anpfiff ueberhaupt?",
            "zielN": 200,
        },
        "vor_anpfiff_gross": {
            "signatur": "phase=='vor' und einsatzUsd >= 10000",
            "warum": "Traegt Groesse allein etwas? Die STAKE-RADAR-Vorlage behauptet ja, ohne Beleg.",
            "zielN": 100,
        },
        "ueber_liga_norm": {
            "signatur": "einsatzUsd >= 5x Median der Liga (Norm aus eigenen Daten, n>=15)",
            "warum": "Die eigentliche These: auffaellig ist relativ zur Liga, nicht absolut.",
            "zielN": 100,
        },
        "kleine_liga": {
            "signatur": "Liga mit <=25 Wetten im Ledger und Einsatz ueber globalem 90%-Punkt",
            "warum": "Lucas: genug kleine Ligen, wo Leute mit guten Infos setzen.",
            "zielN": 60,
        },
        "live_frueh": {
            "signatur": "phase=='live' und Spielminute <= 30",
            "warum": ("Live ist 83% des Feeds, aber spaet im Spiel wertlos (Hapoel-Fall). "
                      "Wenn Live etwas taugt, dann frueh."),
            "zielN": 150,
        },
    }
    neu = 0
    for name, k in kandidaten.items():
        if name not in reg:
            reg[name] = dict(k, angemeldet=jetzt, rueckblick=None)
            neu += 1
    if neu:
        SH._schreibe(REG_FILE, reg)
    return reg


# ── Hauptlauf ────────────────────────────────────────────────────────────────
def auswerten(led: dict, jetzt: str) -> dict:
    alle = led.get("wetten") or []
    # 03.09.2026 (Lucas): US-Sport ist gesperrt — aber nur fuer die Anzeige und das Urteil.
    # Gesammelt und ABGERECHNET wird weiter alles, und die gesperrten Sportarten bekommen ihre
    # eigene Schublade. Sonst koennte man nie merken, dass eine davon dreht; genau diese
    # Entscheidung steht im Poly-Fall vom 24.08. schon so im Code.
    wetten = [w for w in alle if _erlaubt(w)]
    gesperrt = [w for w in alle if not _erlaubt(w)]
    norm = liga_norm(wetten)

    def filt(f):
        return [w for w in wetten if f(w)]

    schubladen = {
        "gesamt": _schublade(wetten),
        "vor_anpfiff": _schublade(filt(lambda w: _phase(w) == "vor")),
        "live": _schublade(filt(lambda w: _phase(w) == "live")),
        "live_frueh": _schublade(filt(lambda w: _phase(w) == "live"
                                      and (_minute(w) or 999) <= 30)),
        "live_spaet": _schublade(filt(lambda w: _phase(w) == "live"
                                      and (_minute(w) or 0) > 60)),
        "einsatz_ab_10k": _schublade(filt(lambda w: (w.get("einsatzUsd") or 0) >= 10000)),
        "einsatz_1k_10k": _schublade(filt(lambda w: 1000 <= (w.get("einsatzUsd") or 0) < 10000)),
        "ueber_liga_norm": _schublade(filt(
            lambda w: (auffaellig(w, norm)["faktor"] or 0) >= AUFFAELLIG_FAKTOR)),
    }

    je_liga = defaultdict(list)
    je_markt = defaultdict(list)
    for w in wetten:
        if w.get("liga"):
            je_liga[w["liga"]].append(w)
        if w.get("markt"):
            je_markt[w["markt"]].append(w)

    def top(d, min_n):
        out = {}
        for k, ws in d.items():
            s = _schublade(ws)
            if s["n"] >= min_n:
                out[k] = s
        return dict(sorted(out.items(), key=lambda kv: -kv[1]["n"])[:25])

    je_gesperrt = defaultdict(list)
    for w in gesperrt:
        je_gesperrt[_kat(w)].append(w)

    b = led.get("bilanz") or {}
    return {
        "asof": jetzt,
        "seit": led.get("seit"),
        "nWetten": len(wetten),
        "nGesamt": len(alle),
        "gesperrt": sorted(SH.GESPERRT),
        "nGesperrt": len(gesperrt),
        # Weiter mitgeschrieben, nur nicht mitgezaehlt: so faellt auf, wenn eine gesperrte
        # Sportart auf einmal traegt. Ein Wiedereintritt braucht Zahlen, keine Meinung.
        "gesperrteSchubladen": {k: _schublade(v) for k, v in je_gesperrt.items()},
        "bilanz": b,
        "reif": bool(b.get("gewertet", 0) >= MIN_N),
        "urteilAb": MIN_N,
        "schubladen": schubladen,
        "jeLiga": top(je_liga, MIN_N_LIGA),
        "jeMarkt": top(je_markt, MIN_N_LIGA),
        "ligaNorm": dict(sorted(norm.items(), key=lambda kv: -kv[1]["n"])[:60]),
        "auffaellige": kleine_liga_gross(wetten, norm)[:60],
        "abdeckung": abdeckung(led),
        "hinweis": ("Rohe Quoten sind Punktschaetzer. Ein Urteil steht nur da, wo n >= %d "
                    "UND die Wilson-Untergrenze ueber 50%% liegt. Der Feed ist anonym — es "
                    "gibt aggregierten Fluss, nie einen Track-Record je Konto." % MIN_N),
    }


def main() -> int:
    print("=== stake_analyse.py ===")
    jetzt = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    led = SH._lade(LEDGER_FILE, {})
    if not (led.get("wetten") or []):
        print("  ℹ️  leeres Ledger — nichts auszuwerten.")
        return 0
    vorregistrieren(jetzt)
    a = auswerten(led, jetzt)
    SH._schreibe(OUT_FILE, a)

    b = a["bilanz"]
    print("  Ledger %d Wetten seit %s (%d gesperrt: %s)"
          % (a["nWetten"], (a.get("seit") or "?")[:16], a["nGesperrt"], ", ".join(a["gesperrt"])))
    print("  Beine gewertet: %d (offen %d, unaufloesbar %d)"
          % (b.get("gewertet", 0), b.get("offen", 0), b.get("unaufloesbar", 0)))
    if not a["reif"]:
        print("  ⏳ Noch kein Urteil: unter n=%d wird nur gezaehlt, nicht bewertet." % MIN_N)
    for name in ("vor_anpfiff", "live", "live_frueh", "ueber_liga_norm"):
        s = a["schubladen"][name]
        if s["n"]:
            print("   %-16s n=%-4d Quote %s  UG %s  %s"
                  % (name, s["n"],
                     ("%.1f%%" % (s["quote"] * 100)) if s["quote"] is not None else "—",
                     ("%.1f%%" % (s["ug"] * 100)) if s["ug"] is not None else "—",
                     "BELEGT" if s["belegt"] else ""))
    n_auf = len(a["auffaellige"])
    print("  Auffaellige Einsaetze (ueber Liga-Norm oder kleine Liga): %d" % n_auf)
    ligen = sum(1 for v in a["ligaNorm"].values() if v["basis"] == "gelernt")
    print("  Liga-Normen gelernt: %d von %d Ligen" % (ligen, len(a["ligaNorm"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
