#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freigabe.py — 29.08.2026 (Lucas: „eine Sektion auf der Seite, die ich blind nehmen kann,
waere mir das Wichtigste").

## Warum das anders funktioniert als eine Bestenliste

Eine Sektion, der man blind folgt, darf NICHT „die staerksten Plays von heute" zeigen. Die
staerksten Plays von heute gibt es jeden Tag — auch an Tagen, an denen nichts taugt. Was sie
zeigen muss, sind Plays aus einer SCHUBLADE, die sich bewiesen hat.

Schublade heisst je Strom das, was dort natuerlich ist: bei Poly der Conviction-Bucket bzw. der
Signal-Mix, bei den Cards Verdict x Datensatz, bei Betfair Liga x Markt. Nicht der einzelne Play
wird freigegeben, sondern die Schublade, aus der er kommt. Ein Play aus einer freigegebenen
Schublade ist blind spielbar; derselbe Play aus einer ungeprueften ist es nicht.

## Der Stand am Tag, an dem das hier entstand

Gerechnet ueber alle drei Ledger war GENAU EINE Schublade belegt positiv: Poly Conviction 9
(n=14, ROI +40,8%, Untergrenze +10,9%). Alles andere — inklusive der Public-Kandidaten (n=190,
ROI +2,4%, Untergrenze -6,7%) — ist von null nicht unterscheidbar. Das ist der ehrliche Stand,
und diese Datei ist gebaut, um ihn auszuhalten: sie darf leer ausgehen, und dann sagt sie, wie
weit jede Schublade noch ist. Leer ist ein Ergebnis.

## Warum CLV als zweites Kriterium, nicht nur ROI

Um +2% ROI statistisch zu belegen, braucht es auf diesen Maerkten viele hundert Plays — die
Streuung der Einstiegspreise frisst das Signal. CLV hat ein Zehntel der Varianz und steht schon
beim Anpfiff fest, ist also die schnelle Spur.

Wichtiger noch: CLV ist der Gluecks-Filter. Die Cards standen bei ROI +3,2% und sahen damit
spielbar aus — ihr CLV lag aber bei -2,01pp mit Untergrenze -2,43 ueber 216 Picks. Positiver ROI
bei sicher negativem CLV heisst: wir kaufen systematisch schlechtere Preise als der Markt am Ende
sagt, und der Gewinn kam aus der Varianz. Ohne CLV-Bedingung waere genau das freigegeben worden.

## Was hier NICHT passiert

Nichts wird gesetzt, gesendet oder veraendert. Diese Datei rechnet und schreibt freigabe.json.
Netzfrei, rein, testbar.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_FILE = "freigabe.json"

# ── Die Freigabe-Bedingungen ────────────────────────────────────────────────────────────
# Alle vier muessen gelten. Faellt eine, faellt die Freigabe — automatisch, ohne Zutun.
MIN_N        = int(os.environ.get("FREIGABE_MIN_N") or 30)    # genug Historie
Z            = 1.645                                          # einseitige 95%-Grenze
MIN_ROI_LB   = 0.0                                            # ROI-Untergrenze ueber null
MIN_CLV_LB   = 0.0                                            # CLV-Untergrenze nicht negativ
# Ab so vielen Plays wird eine Schublade ueberhaupt als „Kandidat" gefuehrt (darunter: sammelt).
KANDIDAT_N   = int(os.environ.get("FREIGABE_KANDIDAT_N") or 10)
# 29.08.2026 (Lucas: „Was heisst bis WM BET? Was WM?") — DIE LEBENDIG-BEDINGUNG.
# Erste Fassung fuehrte „WM · BET" als Kandidat mit „noch 5 Plays". Die WM ist seit dem 28.06.
# durch: die fuenf Plays kommen nie, und selbst freigegeben waere die Schublade nicht spielbar.
# Freigegeben muss heissen „das kannst du MORGEN spielen", nicht „das hat mal funktioniert".
# Also: der juengste abgerechnete Play einer Schublade darf nicht aelter sein als das hier.
# Aeltere Schubladen bekommen den Status „ruht" — sie verschwinden nicht (die Historie bleibt
# lesbar), sie stehen nur nicht mehr in der Warteschlange auf eine Freigabe.
MAX_ALTER_TAGE = int(os.environ.get("FREIGABE_MAX_ALTER_TAGE") or 21)


def _now():
    return datetime.now(timezone.utc)


def _load(name, default=None):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def untergrenze(werte, z: float = Z):
    """Einseitige 95%-Untergrenze des Mittelwerts (Normalapproximation).

    Bewusst simpel: bei n>=30 ist die Approximation gutmuetig genug, und die Alternative
    (Bootstrap) macht das Ergebnis nicht belastbarer, nur schwerer nachzurechnen. Unter drei
    Werten gibt es keine Streuungsschaetzung -> None statt einer erfundenen Zahl."""
    n = len(werte)
    if n < 3:
        return None
    m = sum(werte) / n
    var = sum((x - m) ** 2 for x in werte) / (n - 1)
    return m - z * math.sqrt(var) / math.sqrt(n)


def _mittel(werte):
    return (sum(werte) / len(werte)) if werte else None


def _alter_tage(letzter, now):
    """Tage seit dem juengsten abgerechneten Play. None, wenn kein Zeitstempel da ist —
    und None wird wie „unbekannt alt" behandelt, nicht wie „frisch"."""
    if not letzter:
        return None
    try:
        t = datetime.fromisoformat(str(letzter).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (now - t).total_seconds() / 86400.0


def bewerte(name: str, strom: str, renditen, clvs, meta=None, letzter=None, now=None) -> dict:
    """Eine Schublade -> ein Urteil. `renditen` sind Renditen JE PLAY (pnl/stake), nicht die
    Summe: nur so misst die Streuung das, was sie messen soll. `letzter` = Zeitstempel des
    juengsten abgerechneten Plays; ohne ihn kann die Lebendig-Bedingung nicht greifen."""
    n = len(renditen)
    roi, roi_lb = _mittel(renditen), untergrenze(renditen)
    clv, clv_lb = _mittel(clvs), untergrenze(clvs)
    alter = _alter_tage(letzter, now or _now())

    if alter is not None and alter > MAX_ALTER_TAGE:
        # Zuerst pruefen: eine tote Schublade braucht keine ROI-Diskussion.
        return {"schublade": name, "strom": strom, "n": n, "status": "ruht",
                "grund": "letzter Play vor %d Tagen — die Schublade liefert nichts mehr" % round(alter),
                "roi": round(roi, 4) if roi is not None else None,
                "roiLb": round(roi_lb, 4) if roi_lb is not None else None,
                "clv": round(clv, 3) if clv is not None else None,
                "clvLb": round(clv_lb, 3) if clv_lb is not None else None,
                "fehltN": 0, "alterTage": round(alter, 1), **(meta or {})}

    if n < KANDIDAT_N:
        status, grund = "sammelt", f"{n} von {MIN_N} Plays"
    elif n < MIN_N:
        status, grund = "kandidat", f"{n} von {MIN_N} Plays — noch {MIN_N - n}"
    elif roi_lb is None or roi_lb <= MIN_ROI_LB:
        status, grund = "geprueft", "ROI nicht belegt über null"
    elif clv_lb is None:
        status, grund = "geprueft", "kein CLV messbar — ohne den bleibt Glück und Kante ununterscheidbar"
    elif clv_lb < MIN_CLV_LB:
        status, grund = "geprueft", "CLV negativ belegt — der ROI kam aus der Varianz, nicht aus einer Kante"
    elif alter is None:
        # 29.08.2026: kein Zeitstempel -> die Lebendig-Bedingung ist nicht pruefbar. Fail-closed,
        # wie bei fehlendem CLV: nicht wissen ist keine Erlaubnis. Aufgefallen an den Picks des
        # Spiels um Platz 3 (KO-3RD-FRA-SEN), zu denen im Datensatz gar kein Fixture existiert —
        # ohne diese Klausel koennte eine undatierbare Schublade freigegeben werden.
        status, grund = "geprueft", "kein Datum am Play — Lebendigkeit nicht prüfbar"
    else:
        status, grund = "freigegeben", "ROI und CLV belegt"

    return {
        "schublade": name, "strom": strom, "n": n, "status": status, "grund": grund,
        "roi": round(roi, 4) if roi is not None else None,
        "roiLb": round(roi_lb, 4) if roi_lb is not None else None,
        "clv": round(clv, 3) if clv is not None else None,
        "clvLb": round(clv_lb, 3) if clv_lb is not None else None,
        "fehltN": max(0, MIN_N - n),
        "alterTage": round(alter, 1) if alter is not None else None,
        **(meta or {}),
    }


# ── Strom 1: Poly-Shortlist (Papier-Depot) ──────────────────────────────────────────────
_ENGINE_PROBE = 25       # so viele juengste Plays entscheiden, welche Engine gerade laeuft
_ENGINE_MIN_BELEG = 3    # so oft muss ein Stempel darin vorkommen, um zu zaehlen


def aktuelle_engine(track) -> str | None:
    """Welcher Engine-Stempel laeuft gerade? Aus den DATEN gelesen, nicht aus einer Env. REIN.

    ⚠️ 01.09.2026 — der Grund fuer diese Funktion: `poly_schubladen` konnte schon immer auf eine
    Engine-Version filtern, aber der Schalter hing an `FREIGABE_ENGINE`, und die Variable wurde
    NIRGENDS gesetzt (`freigabe.json` trug `engine: null`). Das Register mischte deshalb
    monatelang Engine-Versionen — die staerkste Schublade („Conviction 9", n=12, ROI +16%)
    bestand ausschliesslich aus Plays einer Engine, die es nicht mehr gibt. Sie konnte n=30 nie
    erreichen und schrumpfte stattdessen aus dem rollierenden Fenster heraus.
    Dieselbe Bauform wie beim x-Norm-Badge: eingebaut, feuert nie.

    Eine Env, die jemand setzen MUSS, ist keine Quelle — die Daten sind eine.

    Die Regel: der JUENGSTE Stempel, der im Fenster mindestens `_ENGINE_MIN_BELEG` mal vorkommt.
    Nicht die Mehrheit — die waere direkt nach einem Versionssprung noch beim ALTEN Stempel, und
    das Register wuerde einen halben Tag lang genau die Plays als aktuell zaehlen, die es gerade
    aussortieren soll. Nicht die letzte Zeile — eine einzelne Ausreisser-Zeile darf das Register
    nicht umschalten. Ein paar Belege sind der Kompromiss: umschalten, sobald der neue Stempel
    wirklich laeuft, und nicht wegen eines Zufalls.

    Findet sich gar kein Stempel, gibt es None: dann wird NICHT gefiltert — eine alte Datei ohne
    Stempel soll das Register nicht leeren.
    """
    st = (track or {}).get("settled") or []
    st = list(st.values()) if isinstance(st, dict) else list(st)
    kandidaten = [str(x.get("ev")) for x in st[-_ENGINE_PROBE:] if isinstance(x, dict) and x.get("ev")]
    if not kandidaten:
        op = (track or {}).get("open") or {}
        op = list(op.values()) if isinstance(op, dict) else list(op)
        kandidaten = [str(x.get("ev")) for x in op if isinstance(x, dict) and x.get("ev")]
    if not kandidaten:
        return None
    from collections import Counter
    zaehler = Counter(kandidaten)
    for ev in reversed(kandidaten):                     # von der juengsten Zeile rueckwaerts
        if zaehler[ev] >= _ENGINE_MIN_BELEG:
            return ev
    return zaehler.most_common(1)[0][0]                  # niemand hat genug Belege -> haeufigster


def poly_schubladen(track=None, engine=None) -> list:
    """Conviction-Buckets und Signal-Mixe.

    Plays aus einer aelteren Gewichtung sind fuer eine FREIGABE keine Zeugen — anders als beim
    Kalibrierer, der sie halb gewichtet weiterlaufen laesst. Hier geht es um eine Erlaubnis, nicht
    um eine Rangfolge; da ist Halbwissen keine Grundlage.

    ⚠️ Sie werden trotzdem NICHT verschwiegen. Wuerde man sie einfach wegfiltern, verschwaende die
    Schublade komplett aus dem Register und saehe aus wie „gab es nie" statt wie „die Datenbasis
    ist veraltet". Deshalb: das URTEIL rechnet nur auf der aktuellen Engine, die Alt-Plays laufen
    als Kontext mit (`nAlt`, `roiAlt`, `clvAlt`, `engineAlt`).

    `engine=None` -> aus den Daten bestimmen (s. `aktuelle_engine`). `engine=False` -> gar nicht
    filtern (fuer Tests und Rueckblicke)."""
    d = track if track is not None else _load("poly_shortlist_track.json")
    st = (d or {}).get("settled") or []
    st = list(st.values()) if isinstance(st, dict) else st
    if engine is None:
        engine = aktuelle_engine(d)
    out = []

    def _teile(rows):
        """(aktuell, alt) — ohne Filter zaehlt alles als aktuell."""
        if not engine:
            return list(rows), []
        akt = [x for x in rows if x.get("ev") == engine]
        return akt, [x for x in rows if x.get("ev") != engine]

    def _kennzahlen(rows):
        r = [float(x.get("pnl") or 0) / float(x["stake"]) for x in rows if x.get("stake")]
        c = [float(x["clvPP"]) for x in rows if isinstance(x.get("clvPP"), (int, float))]
        return r, c

    def _rows(rows, name, meta=None):
        akt, alt = _teile(rows)
        r, c = _kennzahlen(akt)
        ra, ca = _kennzahlen(alt)
        if not r and not ra:
            return
        letzter = max((str(x.get("settledTs") or "") for x in akt), default="") or None
        z = bewerte(name, "poly", r, c, meta, letzter=letzter)
        if ra:
            z["nAlt"] = len(ra)
            z["roiAlt"] = round(sum(ra) / len(ra), 4)
            z["clvAlt"] = round(sum(ca) / len(ca), 3) if ca else None
            z["engineAlt"] = True
            if not r:
                # Die ganze Datenbasis ist alt. Das ist etwas anderes als „noch keine Daten" —
                # und der Unterschied gehoert in den Grund, nicht in eine Fussnote.
                z["grund"] = ("0 von %d Plays auf der aktuellen Engine — die %d vorhandenen "
                              "stammen aus einer frueheren Bewertung und zaehlen nicht"
                              % (MIN_N, len(ra)))
        out.append(z)

    for conv in sorted({x.get("conv") for x in st if x.get("conv") is not None}, reverse=True):
        _rows([x for x in st if x.get("conv") == conv], f"Conviction {conv}",
              {"art": "conviction", "wert": conv})
    CORE = {"money", "sharp", "steam", "pinn", "gvp", "bf"}
    mixe = {}
    for x in st:
        k = "+".join(sorted(t for t in (x.get("signals") or []) if t in CORE)) or "(ohne)"
        mixe.setdefault(k, []).append(x)
    for k, rows in mixe.items():
        _rows(rows, f"Mix {k}", {"art": "mix", "wert": k})
    _rows([x for x in st if x.get("public")], "Public-Kandidaten", {"art": "gate"})
    return out


# ── Strom 2: Cards ──────────────────────────────────────────────────────────────────────
CARD_DATEIEN = (("liga-data.json", "Liga"), ("mls-data.json", "MLS"), ("wm2026-data.json", "WM"))
STAKE_BET, STAKE_ABW = 10.0, 5.0


def _card_plays(dateien=CARD_DATEIEN) -> list:
    """Abgerechnete Card-Picks in dieselbe Form wie das Poly-Depot: Rendite je Play + CLV.
    NOBET, trackingExcluded und boldAlt fliegen raus — das sind keine Wetten (gleiche Regel
    wie im Tracking-Tab, sonst misst die Freigabe etwas anderes als die Anzeige)."""
    out = []
    for datei, label in dateien:
        d = _load(datei)
        # Pick-Keys tragen kein Datum — das steht am Fixture. Ohne Datum kann die
        # Lebendig-Bedingung nicht greifen, und genau daran ist die WM-Schublade aufgefallen.
        _fx_datum = {}
        for gk, g in ((d or {}).get("groups") or {}).items():
            for fx in (g.get("fixtures") or []):
                _fx_datum[f"{gk}-{fx.get('matchday')}-{fx.get('home')}-{fx.get('away')}"] = fx.get("date")
        # K.O.-Picks haengen unter „KO-{Runde}-{Heim}-{Gast}" und stehen NICHT in groups.fixtures.
        # Ohne sie blieben zwei WM-Picks ohne Datum und damit ohne Alter — dieselbe blinde Stelle
        # wie heute frueh im Tracking, wo die K.O.-Zeilen ihr result nicht mitfuehrten.
        for kf in ((d or {}).get("koFixtures") or []):
            _fx_datum[f"KO-{kf.get('round')}-{kf.get('home')}-{kf.get('away')}"] = (
                kf.get("date") or (str(kf.get("kickoff") or "")[:10] or None))
        for key, arr in ((d or {}).get("picks") or {}).items():
            for p in arr:
                res = str(p.get("result") or "").upper()
                if res not in ("WIN", "LOSS"):
                    continue
                if p.get("verdict") == "NOBET" or p.get("trackingExcluded") or p.get("boldAlt"):
                    continue
                odds = p.get("odds")
                if not isinstance(odds, (int, float)) or odds <= 1:
                    continue
                stake = float(p.get("stake") or (STAKE_BET if p.get("verdict") == "BET" else STAKE_ABW))
                pnl = (odds - 1) * stake if res == "WIN" else -stake
                out.append({"ds": label, "verdict": p.get("verdict") or "?",
                            "r": pnl / stake, "clv": p.get("clvPP"), "ts": _fx_datum.get(key)})
    return out


def card_schubladen(plays=None) -> list:
    plays = _card_plays() if plays is None else plays
    out, gruppen = [], {}
    for p in plays:
        gruppen.setdefault((p["ds"], p["verdict"]), []).append(p)
    for (ds, v), rows in gruppen.items():
        letzter = max((str(x.get("ts") or "") for x in rows), default="") or None
        out.append(bewerte(f"{ds} · {v}", "cards",
                           [x["r"] for x in rows],
                           [float(x["clv"]) for x in rows if isinstance(x.get("clv"), (int, float))],
                           {"art": "verdict", "wert": v, "datensatz": ds},
                           letzter=(letzter + "T12:00:00+00:00") if letzter else None))
    return out


# ── Strom 3: Betfair ────────────────────────────────────────────────────────────────────
def _betfair_streuung(n, hit, roi):
    """Betfair fuehrt kein Play-fuer-Play-Ledger, nur Aggregate (n/hitRate/roi je Liga x Markt).
    Ohne Einzelwerte gibt es keine echte Streuung — sie laesst sich aber aus der Binaerstruktur
    rekonstruieren: aus ROI und Trefferquote folgt die mittlere Quote o = (roi+1)/hit, und die
    Rendite je Play ist dann entweder o-1 (Treffer) oder -1. Die Standardabweichung davon ist
    o*sqrt(p(1-p)). Das ist eine NAEHERUNG und im Ergebnis als solche markiert — sie ueberschaetzt
    die Praezision nicht, weil sie die Quotenstreuung innerhalb der Schublade ignoriert und damit
    eher zu KLEINE Fehler liefert. Deshalb gilt Betfair nie allein als Freigabe-Beleg."""
    if not n or not hit or hit <= 0 or hit >= 1:
        return None
    o = (roi + 1.0) / hit
    sd = o * math.sqrt(hit * (1 - hit))
    return sd / math.sqrt(n)


def betfair_schubladen(rec=None, min_n=None) -> list:
    d = rec if rec is not None else _load("betfair_track_record.json")
    min_n = MIN_N if min_n is None else min_n
    out = []
    for quelle, art in (("byMarket", "markt"), ("byLeagueMarket", "liga_markt")):
        for name, v in ((d or {}).get(quelle) or {}).items():
            n, hit, roi = v.get("n") or 0, v.get("hitRate"), v.get("roi")
            if n < min_n or hit is None or roi is None:
                continue
            se = _betfair_streuung(n, hit, roi)
            roi_lb = (roi - Z * se) if se is not None else None
            # Betfair fuehrt kein CLV je Signal -> die CLV-Bedingung kann hier NICHT geprueft
            # werden. Fail-closed: ohne CLV keine Freigabe. Der Strom kann Kandidat werden,
            # freigegeben wird er erst, wenn das Ledger CLV je Signal mitschreibt.
            eintrag = bewerte(name.replace("|", " · "), "betfair", [], [],
                              {"art": art, "naeherung": True})
            eintrag.update({"n": n, "roi": round(roi, 4),
                            "roiLb": round(roi_lb, 4) if roi_lb is not None else None,
                            "fehltN": max(0, MIN_N - n)})
            if roi_lb is None or roi_lb <= 0:
                eintrag["status"], eintrag["grund"] = "geprueft", "ROI nicht belegt über null"
            else:
                eintrag["status"] = "geprueft"
                eintrag["grund"] = "ROI belegt, aber kein CLV je Signal im Ledger — ohne den keine Freigabe"
            out.append(eintrag)
    return out


def killer_schublade(results=None, now=None) -> list:
    """Die Konjunktion aus killer.py als eigene Schublade.

    29.08.2026: die übrigen Betfair-Schubladen rechnen auf Aggregaten und können deshalb nie
    über „geprueft" hinauskommen — im Aggregat steht kein CLV je Signal. Die Konjunktion
    rechnet auf den Rohzeilen von betfair_track_results.json, dort liegt clvBf je Zeile.
    Sie kann also wirklich freigegeben werden. Genau das ist der Punkt: die Sektion, die Lucas
    blind spielen können soll, muss sich selbst freigeben statt behauptet zu werden."""
    try:
        from killer import schublade
    except Exception:
        return []
    out = []
    # 31.08.2026 (Lucas: „nur die Top 5 lassen oder erweitert?"): statt einer Schublade ueber
    # alle Ligen zwei getrennte. Gemessen war die Frage nicht entscheidbar — Top-5 hat den
    # besseren ROI-Punktschaetzer (n=10), der Rest den einzigen CLV mit Untergrenze ueber null
    # (n=70). Getrennt qualifiziert sich jede selbst, und keine Zeile geht verloren.
    # Beide Zuschnitte werden IMMER gemeldet, auch leer — „Top-5 sammelt noch" ist eine
    # Aussage, ein fehlender Eintrag waere keine.
    for scope, name in (("top5", "Konjunktion · Top-5 + MLS"),
                        ("rest", "Konjunktion · übrige Ligen")):
        s = schublade(results, scope=scope)
        if s["renditen"]:
            out.append(bewerte(name, "betfair", s["renditen"], s["clvs"],
                               {"art": "konjunktion", "quelle": "killer.py", "zuschnitt": scope},
                               s["letzter"], now))
    # 30.08.2026 (Lucas: „das wechselt auch ohne dass ich die Seite aktualisiere"): die Sektion
    # HÄLT ihre Treffer jetzt bis zum Anpfiff, weil `inflow` ein Intervall-Delta ist und sonst
    # im Minutentakt blinkt. Das ist eine andere Menge als die oben gemessene (dort zählt der
    # letzte Vor-Anpfiff-Schnappschuss), und sie wird zum HALTEPREIS abgerechnet — dem Preis,
    # den die Sektion wirklich gezeigt hat. Beide stehen nebeneinander, damit sichtbar wird,
    # ob das Halten die Kante kostet.
    try:
        from killer import schublade_gehalten
        g = schublade_gehalten()
        if g["renditen"]:
            out.append(bewerte("Konjunktion · gehalten (Haltepreis)", "betfair",
                               g["renditen"], g["clvs"],
                               {"art": "konjunktion_gehalten", "quelle": "killer_ledger.json"},
                               g["letzter"], now))
    except Exception:
        pass
    return out


def push_schubladen(ledger=None, now=None) -> list:
    """Das Schattenbuch des Card-Pushes: „ABWÄGEN · gepusht" gegen „ABWÄGEN · aussortiert".

    30.08.2026 (Lucas): der Gegensignal-Filter schneidet rund vier Fünftel der ABWÄGEN aus dem
    Public-Push. Damit dieser Schnitt sich nicht selbst bestätigt, laufen die Aussortierten im
    Schattenbuch weiter mit — und stehen hier nebeneinander. Wären sie in Wahrheit die besseren,
    stünde es in dieser Tabelle.

    Ohne CLV je Pick bleibt beides höchstens „geprueft" — die Cards führen keinen. Das ist
    gewollt: der Schnitt darf sichtbar besser dastehen, ohne allein deshalb freigegeben zu sein."""
    try:
        from pick_push_ledger import schubladen
    except Exception:
        return []
    out = []
    for name, d in sorted((schubladen(ledger) or {}).items()):
        if not d["renditen"]:
            continue
        out.append(bewerte(name, "cards", d["renditen"], [],
                           {"art": "push_filter", "quelle": "pick_push_ledger.py"},
                           d["letzter"], now))
    return out


# ── Zusammenbau ─────────────────────────────────────────────────────────────────────────
RANG = {"freigegeben": 0, "kandidat": 1, "geprueft": 2, "sammelt": 3, "ruht": 4}


def baue(engine=None, track=None, cards=None, betfair=None, now=None) -> dict:
    now = now or _now()
    # 01.09.2026: die Datei muss sagen, WORAUF sie gefiltert hat. Vorher stand hier der rohe
    # Parameter — bei `engine=None` also `null`, obwohl gefiltert wurde. Eine Datei, die ueber
    # ihre eigene Filterung schweigt, ist genau der Grund, warum der tote Filter monatelang
    # niemandem auffiel.
    if engine is None:
        _t = track if track is not None else _load("poly_shortlist_track.json")
        engine_benutzt = aktuelle_engine(_t)
    else:
        engine_benutzt = engine or None          # False (= bewusst nicht filtern) -> null
    zeilen = (poly_schubladen(track, engine) + card_schubladen(cards)
              + betfair_schubladen(betfair) + killer_schublade(now=now)
              + push_schubladen(now=now))
    zeilen.sort(key=lambda r: (RANG.get(r["status"], 9), -(r.get("roiLb") or -9), -r["n"]))
    frei = [r for r in zeilen if r["status"] == "freigegeben"]
    kand = [r for r in zeilen if r["status"] == "kandidat"]
    return {
        "generatedAt": now.isoformat(),
        "engine": engine_benutzt,
        "engineGefiltert": bool(engine_benutzt),
        "regeln": {"minN": MIN_N, "z": Z, "kandidatAbN": KANDIDAT_N,
                   "maxAlterTage": MAX_ALTER_TAGE,
                   "text": "freigegeben = n>=%d UND ROI-Untergrenze>0 UND CLV-Untergrenze>=0 UND "
                           "juengster Play juenger als %d Tage, alles auf der aktuellen "
                           "Engine-Version" % (MIN_N, MAX_ALTER_TAGE)},
        "freigegeben": frei,
        "kandidaten": kand,
        "alle": zeilen,
        "zusammenfassung": {
            "schubladen": len(zeilen), "freigegeben": len(frei), "kandidaten": len(kand),
            "ruhend": len([r for r in zeilen if r["status"] == "ruht"]),
            "naechsteFreigabe": min([r["fehltN"] for r in kand], default=None),
        },
    }


def main() -> int:
    from safe_write import write_json_atomic
    # 01.09.2026: Default ist NICHT mehr „kein Filter". Die Engine kommt aus den Daten
    # (s. aktuelle_engine); `FREIGABE_ENGINE=<stempel>` erzwingt eine bestimmte, `=off` schaltet
    # das Filtern ab. Vorher war der Default „gar nicht filtern", und weil die Variable nirgends
    # gesetzt wurde, mischte das Register monatelang Engine-Versionen.
    _ev = os.environ.get("FREIGABE_ENGINE")
    ev = False if str(_ev).lower() == "off" else (_ev or None)
    d = baue(engine=ev)
    write_json_atomic(BASE / OUT_FILE, d, indent=1)
    z = d["zusammenfassung"]
    print("=== freigabe.py ===")
    print(f"  {z['schubladen']} Schubladen · {z['freigegeben']} freigegeben · {z['kandidaten']} Kandidaten")
    for r in d["alle"][:14]:
        roi = f"{100*r['roi']:+6.1f}%" if r["roi"] is not None else "   —  "
        lb = f"{100*r['roiLb']:+6.1f}%" if r["roiLb"] is not None else "   —  "
        clv = f"{r['clv']:+5.2f}" if r["clv"] is not None else "  —  "
        print(f"  [{r['status']:<11}] {r['strom']:<8} {r['schublade']:<26} n={r['n']:>4} "
              f"ROI {roi} (UG {lb})  CLV {clv}  · {r['grund']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
