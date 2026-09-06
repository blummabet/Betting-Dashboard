#!/usr/bin/env python3
"""
signal_bilanz.py — was traegt jedes einzelne Signal bei?
========================================================
06.09.2026 (Lucas: „ich dachte, die Signale lernen nach jedem Match und werden neu gewichtet,
und wenn eins zum Scheissen ist, wird es runtergewichtet — ich dachte, das funktioniert
sowieso").

Es lief. 164 Laeufe seit dem 26.06. Es konnte nur nie sagen, dass etwas GUT ist.

## Warum der Lern-Loop nichts bewegen konnte

Der Massstab war bis heute die eigene Trefferquote (~0,55-0,60). `weight = posterior / neutral`
landete damit fast zwangslaeufig unter 1. Nachgerechnet ueber die Gewichtsdatei:

    Spanne aller Liga-Gewichte am 05.09.:   0,590 .. 1,034
    erlaubt waere:                          0,300 .. 1,700
    mediane Bewegung in 2,5 Monaten:        0,185

**Kein einziges Signal kam je nennenswert ueber 1,0.** Der Loop konnte abwerten und praktisch
nicht aufwerten — die Haelfte, die du erwartet hast („das Starke wird hoeher gewichtet"), gab
es nie. Dazu kam: er sah die Quote nicht (behoben am 06.09.), und mehrere Signale, ueber die er
lernte, waren defekt oder abgeschaltet.

Und selbst wo er sich bewegte, war der Hebel klein. Im Picker gilt

    weighted_score = score * weight * confidence

mit `weight` zwischen 0,59 und 1,03 und `confidence` zwischen 0,35 und 0,9. **Die confidence,
die jedes Signal sich selbst gibt, bewegte mehr als alles Gelernte.**

## Was dieses Modul macht

Es beantwortet je Signal die Frage, die der Loop nicht stellt: *traegt es bei, und ist das
belegt?* Zwei Masse, weil sie verschiedene Fragen sind:

  · **CLV** — hat der Markt dem Signal recht gegeben? Steht beim Anpfiff fest, kleine Varianz,
    braucht ein Zehntel der Stichprobe von ROI.
  · **preis-justierter Ausgang** — hat der Pick seinen eigenen Preis geschlagen? 0,5 heisst
    „genau wie bepreist" (siehe `update_signal_weights._preis_justierter_outcome`).

Beide mit einseitiger 95%-Grenze, und ein Urteil gibt es nur, wenn das ganze Intervall auf
einer Seite liegt. *Ein Punktschaetzer ist kein Beleg.* Ein Signal mit n=12 und Ø CLV +3 pp
bekommt „kein Urteil", nicht „gut".

Die Richtung zaehlt mit: ein Signal mit negativem Score behauptet „schlechter Pick" — sein
Beitrag ist dann der umgekehrte Ausgang.

REIN/testbar, kein I/O.
"""
from __future__ import annotations

import math

# Unter dieser Zahl Beobachtungen gibt es kein Urteil, nur eine Beschreibung.
MIN_N = 25

# ── Was diese Tabelle NICHT sagt ────────────────────────────────────────────────────────────
# Es werden ~30 Signale gleichzeitig geprueft, jedes einseitig auf 95 %. Rein zufaellig sind
# damit rund 1-2 falsche „traegt bei" zu erwarten. Ein Eintrag knapp ueber der Grenze
# (Untergrenze +0,2 pp) ist deshalb KEIN Beleg, sondern ein Kandidat fuer die naechste Woche.
# Wer hier abwerten will, nimmt die, deren Intervall deutlich und ueber mehrere Wochen haelt.
MEHRFACHTEST_HINWEIS = ("~30 Signale gleichzeitig geprueft — 1-2 falsche Treffer sind zu "
                        "erwarten. Nur was ueber mehrere Wochen haelt, ist ein Befund.")
Z = 1.645          # einseitig 95 %


def _zahl(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


def _grenzen(werte):
    """(mittel, untergrenze, obergrenze) — einseitige 95%-Grenzen. None bei zu wenig."""
    w = [v for v in werte if v is not None]
    n = len(w)
    if n < MIN_N:
        return None
    m = sum(w) / n
    if n < 2:
        return None
    var = sum((v - m) ** 2 for v in w) / (n - 1)
    se = math.sqrt(var / n)
    return m, m - Z * se, m + Z * se


def _urteil(g, neutral=0.0):
    """'traegt bei' | 'schadet' | 'kein Urteil' — nur wenn das Intervall die Neutrale meidet."""
    if g is None:
        return "kein Urteil"
    _m, ug, og = g
    if ug > neutral:
        return "traegt bei"
    if og < neutral:
        return "schadet"
    return "kein Urteil"


def _geschichtet(paare_mit, paare_ohne):
    """Differenz zweier Gruppen, geschichtet nach der Zahl der UEBRIGEN Signale.

    06.09.2026, zweite Korrektur am selben Tag. Nach der Umstellung auf den Gruppenvergleich
    meldete die Bilanz 13 von 33 Signalen als „traegt bei" und **kein einziges** als schaedlich.
    Das war zu schoen, und es war ein Artefakt:

        r(Anzahl gefeuerter Signale je Pick, CLV) = +0,131

        Signale/Pick   1     2     3     4     5     6     7     8     9
        Ø CLV       -4,18 -3,68 -2,42 -2,32 -2,30 -1,53 -3,64 -2,44 -1,06

    Picks, auf denen VIELE Signale feuern, haben besseren CLV — vermutlich, weil dort ueberhaupt
    mehr Marktdaten vorliegen. Die „gefeuert"-Gruppe eines jeden Signals ist damit systematisch
    signalreicher als die Vergleichsgruppe, und jedes Signal erbt den Vorteil, ohne ihn
    verdient zu haben.

    Die Schichtung nimmt ihn heraus: verglichen wird nur innerhalb gleicher Zahl **uebriger**
    Signale, danach wird ueber die Schichten invers-varianz-gewichtet gepoolt. Wo eine Schicht
    zu duenn ist, faellt sie weg statt zu raten.
    """
    von_mit: dict = {}
    von_ohne: dict = {}
    for k, v in (paare_mit or []):
        von_mit.setdefault(k, []).append(v)
    for k, v in (paare_ohne or []):
        von_ohne.setdefault(k, []).append(v)

    zaehler = nenner = 0.0
    n_mit = n_ohne = 0
    for k, a in von_mit.items():
        b = von_ohne.get(k) or []
        if len(a) < 5 or len(b) < 5:
            continue
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
        vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
        var = va / len(a) + vb / len(b)
        if var <= 0:
            continue
        gew = 1.0 / var
        zaehler += gew * (ma - mb)
        nenner += gew
        n_mit += len(a)
        n_ohne += len(b)
    if nenner <= 0 or n_mit < MIN_N or n_ohne < MIN_N:
        return None
    d = zaehler / nenner
    se = math.sqrt(1.0 / nenner)
    return d, d - Z * se, d + Z * se


def _diff_grenzen(mit, ohne):
    """(Differenz, UG, OG) zwischen zwei Gruppen — einseitige 95%-Grenzen. None bei zu wenig.

    06.09.2026, unmittelbar nach dem ersten Lauf. Die erste Fassung mass jedes Signal gegen
    einen FESTEN Nullpunkt (CLV gegen 0, Ausgang gegen 0,5) — und meldete prompt fuenf Signale
    gleichzeitig als „schadet" (CLV) UND „traegt bei" (Ausgang).

    Der Widerspruch war meiner, nicht der der Daten: unsere Picks steigen im Schnitt 2,2 pp
    unter dem Schlusskurs ein (gemessen ueber 281 Steam-Picks). Diesen Sockel erbt JEDES Signal,
    das auf unseren Picks feuert — er sagt etwas ueber die Pick-Auswahl, nichts ueber das
    Signal. Gegen einen festen Nullpunkt gemessen, waeren am Ende alle 33 „schaedlich" gewesen.

    Die Frage ist nicht „ist der CLV positiv", sondern **„ist er besser, wenn dieses Signal
    spricht, als wenn es schweigt"**. Also: Differenz zweier Gruppen mit eigener Streuung.
    """
    a = [v for v in (mit or []) if v is not None]
    b = [v for v in (ohne or []) if v is not None]
    if len(a) < MIN_N or len(b) < MIN_N:
        return None
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((v - ma) ** 2 for v in a) / (len(a) - 1)
    vb = sum((v - mb) ** 2 for v in b) / (len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    if se <= 0:
        return None
    d = ma - mb
    return d, d - Z * se, d + Z * se


def beitraege(records, preis_outcome):
    """Je Signal die Beobachtungen sammeln.

    `preis_outcome` ist eine Funktion record -> [0,1] oder None (in der Produktion
    `update_signal_weights._preis_justierter_outcome`) — hereingereicht statt importiert,
    damit dieses Modul rein bleibt und der Test die Rechnung selbst stellen kann.

    -> {signal: {"clv": [...], "ausgang": [...]}}
    """
    out: dict = {}
    # Erst alle Namen sammeln, damit auch die Vergleichsgruppe („Signal schwieg") entsteht.
    namen = set()
    zeilen = []
    for r in (records or []):
        if not isinstance(r, dict):
            continue
        clv = _zahl(r.get("clvPP")) if r.get("clvResolved") else None
        try:
            aus = preis_outcome(r)
        except Exception:
            aus = None
        aus = _zahl(aus)
        gefeuert = {}
        for s in (r.get("signals") or []):
            if not isinstance(s, dict):
                continue
            name, w = s.get("name"), _zahl(s.get("score"))
            if not name or not w:
                continue
            gefeuert[name] = w
            namen.add(name)
        zeilen.append((clv, aus, gefeuert))
    for name in namen:
        d = out.setdefault(name, {"clv": [], "ausgang": [], "clvOhne": [], "ausgangOhne": [],
                                  "clvPaare": [], "ausgangPaare": [],
                                  "clvPaareOhne": [], "ausgangPaareOhne": []})
        for clv, aus, gef in zeilen:
            w = gef.get(name)
            # Schicht = Zahl der UEBRIGEN Signale auf diesem Pick (s. _geschichtet).
            uebrig = len(gef) - (1 if w is not None else 0)
            if w is None:
                if clv is not None:
                    d["clvOhne"].append(clv); d["clvPaareOhne"].append((uebrig, clv))
                if aus is not None:
                    d["ausgangOhne"].append(aus); d["ausgangPaareOhne"].append((uebrig, aus))
                continue
            # Richtung: ein Signal mit negativem Score behauptet „schlechter Pick".
            if clv is not None:
                v = clv if w > 0 else -clv
                d["clv"].append(v); d["clvPaare"].append((uebrig, v))
            if aus is not None:
                v = aus if w > 0 else (1.0 - aus)
                d["ausgang"].append(v); d["ausgangPaare"].append((uebrig, v))
    return out


def bilanz(records, preis_outcome) -> dict:
    """Die vollstaendige Tabelle. -> {signal: {...}} inkl. Urteil je Mass."""
    roh = beitraege(records, preis_outcome)
    erg = {}
    for name, d in roh.items():
        gc = _grenzen(d["clv"])
        ga = _grenzen(d["ausgang"])
        # Das URTEIL faellt gegen die Vergleichsgruppe, nicht gegen einen festen Nullpunkt.
        dc = _geschichtet(d["clvPaare"], d["clvPaareOhne"])
        da = _geschichtet(d["ausgangPaare"], d["ausgangPaareOhne"])
        erg[name] = {
            "nClv": len(d["clv"]),
            "nAusgang": len(d["ausgang"]),
            "nClvOhne": len(d["clvOhne"]),
            "nAusgangOhne": len(d["ausgangOhne"]),
            # Beschreibung: der rohe Wert, damit die Zahl lesbar bleibt.
            "clvPP": round(gc[0], 3) if gc else None,
            "clvUG": round(gc[1], 3) if gc else None,
            "clvOG": round(gc[2], 3) if gc else None,
            "ausgang": round(ga[0], 4) if ga else None,
            # Urteil: der Unterschied zu den Picks, auf denen dieses Signal schwieg.
            "clvDiff": round(dc[0], 3) if dc else None,
            "clvDiffUG": round(dc[1], 3) if dc else None,
            "clvDiffOG": round(dc[2], 3) if dc else None,
            "clvUrteil": _urteil(dc, 0.0),
            "ausgangDiff": round(da[0], 4) if da else None,
            "ausgangDiffUG": round(da[1], 4) if da else None,
            "ausgangDiffOG": round(da[2], 4) if da else None,
            "ausgangUrteil": _urteil(da, 0.0),
        }
    return erg


def schaedliche(bil) -> list:
    """Signale, die auf mindestens einem Mass BELEGT schaden. Das sind die Kandidaten zum
    Abwerten — nicht die mit dem schlechtesten Punktschaetzer."""
    out = []
    for name, v in (bil or {}).items():
        if v.get("clvUrteil") == "schadet" or v.get("ausgangUrteil") == "schadet":
            out.append(name)
    return sorted(out)


def tragende(bil) -> list:
    """Signale, die auf mindestens einem Mass BELEGT beitragen."""
    out = []
    for name, v in (bil or {}).items():
        if v.get("clvUrteil") == "traegt bei" or v.get("ausgangUrteil") == "traegt bei":
            out.append(name)
    return sorted(out)


def befunde(bil) -> list:
    """Lesbare Zeilen fuer den Guard. Nur BELEGTE Schaeden — der Rest ist Beschreibung."""
    zeilen = []
    for name in schaedliche(bil):
        v = bil[name]
        teile = []
        if v.get("clvUrteil") == "schadet":
            teile.append("CLV %.2f pp schlechter als ohne dieses Signal (OG %.2f, n=%d/%d)"
                         % (v["clvDiff"], v["clvDiffOG"], v["nClv"], v["nClvOhne"]))
        if v.get("ausgangUrteil") == "schadet":
            teile.append("Ausgang %.3f schlechter als ohne (OG %.3f, n=%d/%d)"
                         % (v["ausgangDiff"], v["ausgangDiffOG"],
                            v["nAusgang"], v["nAusgangOhne"]))
        zeilen.append("%s schadet belegt: %s — abwerten oder nur noch beobachten"
                      % (name, "; ".join(teile)))
    return zeilen
