#!/usr/bin/env python3
"""killer.py — das Konjunktions-Element: nur wo mehrere Ströme GLEICHZEITIG zustimmen.

29.08.2026 (Lucas): „Also dort kommst halt nur rein wenn / Pini move da / Betfair geld oben
und quoten mitziehen / Poly geld oben / ggf noch so sachen wie / Streak muss auch passen."

Was die Messung zu dieser Idee gesagt hat, bevor eine Zeile Code entstand:

1) Die Konjunktion 1:1 auf die 40 Spiele des Tages angewendet ergab DREI Spiele — alle live,
   alle auf haushohe Favoriten (Galatasaray @1.15). Wo sich alle einig sind, ist der Preis
   fertig. Eine reine Konjunktion ist eine Maschine zum Kauf entschiedener Favoriten.

2) Poly deckt ~10 von 40 Spielen ab. Als Pflichtbedingung schrumpft die Sektion auf unter ein
   Spiel pro Tag und wird nie messbar.

3) Drei von Lucas' Bedingungen liegen aber seit dem 23.08. abgerechnet vor — in
   betfair_track_results.json, 8.000 Zeilen, nur vor Anpfiff erfasst:
       conc   = Geld-Favorit hält >= 65% des Marktgeldes   („Betfair Geld oben")
       inflow = >= 2.000 EUR frisch in den Markt geflossen  („frisches Geld")
       dir    = 'in', die Quote kürzt sich                  („Quoten ziehen mit")
   ROI zur Closing-Quote (Signal und Preis im selben Moment, also ohne Look-ahead):
       alles                     -1,58%   n=8000
       nur dir=in                -0,13%   n=1974
       + conc                    +1,44%   n=1351
       + inflow (Konjunktion)    +8,60%   n=115
           davon nur Match Odds +12,93%   n=81   CLV +3,5pp
   Jede zusätzliche Bedingung hebt es. Das ist das Tor.

4) Eine Preis-Bedingung (pinnFair × Quote >= 1) hatte ich vorgeschlagen und wieder verworfen:
   in den Daten steht sie ANDERSHERUM (Wert>=0: -29,4% bei n=30 · Wert<0: +16,1% bei n=83).
   Die Stichprobe ist klein und die Bänder sind weit — aber es gibt keinen Beleg dafür, so zu
   filtern, und einen schwachen dagegen. Also wird der Wert nur MITGESCHRIEBEN, nicht gefiltert.

Daraus die zwei Stufen (Lucas' Entscheidung: „Zwei Stufen sichtbar"):

   Stufe 1  „Voll gedeckt"  = Kern + Poly-Geld auf derselben Seite + Pinnacle-Favorit stimmt zu
   Stufe 2  „Betfair-Kern"  = das gemessene Tor allein

Die Verstärker (Pinnacle-Bewegung, Serie/Form, Liga-Track) heben den Rang und stehen als Chip
an der Zeile — sie sind KEINE Bedingung, weil sie nur für die Top-5-Ligen überhaupt vorliegen.

Alle Schwellen sind aus betfair_track_record.py gespiegelt, nicht nachgebaut: die Sektion muss
per Konstruktion dieselbe Menge treffen, die dort später abgerechnet wird. Läuft sie auseinander,
misst das Tracking etwas anderes als die Empfehlung — genau der Fehler, den sharp_gate.py für
die Wallets beseitigt hat.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import betfair_track_store as _store   # 01.09.2026: Ledger liegt kompakt, load() nimmt beide Formate

BASE = Path(__file__).resolve().parent
OUT_FILE = "killer.json"
STATE_FILE = "killer_state.json"      # gehaltene Treffer bis zum Anpfiff
LEDGER_FILE = "killer_ledger.json"    # abgerechnete gehaltene Treffer (eigene Messung)

# ── Warum gehalten wird (30.08.2026, Lucas: „das wechselt auch ohne dass ich die Seite
# aktualisiere") ──────────────────────────────────────────────────────────────────────────
# Die Sektion zeigte die Bedingungen LIVE. `inflow` ist aber kein Zustand, sondern ein
# Intervall-Delta: „seit dem letzten Scan sind ≥2.000 € in den Markt geflossen". Kommt das Geld
# in Schüben — und so kommt es —, steht das Flag einen Lauf an und den nächsten aus, obwohl das
# Geld weiter im Markt liegt. Gemessen über 40 Läufe (~10 Stunden):
#
#     · in mehr als der Hälfte der Läufe war die Sektion LEER
#     · 15 verschiedene Spiele haben irgendwann getroffen
#     · 6 davon (40%) waren in GENAU EINEM Lauf sichtbar, also ~15 Minuten
#     · Chelsea–Brighton traf 13-mal, aber nicht am Stück — es blinkte
#
# Für eine Sektion, aus der man blind spielen soll, ist das unbrauchbar: eine Empfehlung, die
# drei Minuten später weg ist, kann man nicht setzen. Also wird gehalten: hat ein Spiel die drei
# Bedingungen vor Anpfiff EINMAL gleichzeitig erfüllt, bleibt es bis zum Anpfiff stehen — mit
# dem Preis von damals und dem Zeitpunkt.
#
# Das ist bewusst eine ANDERE Menge als die, die betfair_track_record abrechnet (dort zählt der
# letzte Vor-Anpfiff-Schnappschuss). Deshalb bekommt sie ihr eigenes Buch: killer_ledger.json
# rechnet die gehaltenen Treffer zum Preis ab, der beim Halten wirklich dastand — dem einzigen
# Preis, den man tatsächlich hätte nehmen können.

# ── Schwellen: gespiegelt, nicht nachgebaut ─────────────────────────────────────────────
try:
    from betfair_track_record import CONC_THRESHOLD, INFLOW_MIN_EUR
except Exception:                       # pragma: no cover — nur falls das Modul fehlt
    CONC_THRESHOLD, INFLOW_MIN_EUR = 0.65, 2000

MARKT = "Match Odds"        # die gemessene Fläche (+12,9% n=81); andere Märkte sind dünner belegt
MIN_QUOTE = 1.30            # darunter zahlt keine Kante die Varianz
MAX_QUOTE = 15.0            # darüber ist es eine Lotterie, kein Geld-Signal
POLY_MIN_ANTEIL = 60        # „Poly Geld oben" — Anteil in Prozent
PINN_MIN_MOVE_PP = 1.0      # Verstärker: ab so viel pp gilt die Pinnacle-Bewegung als Bewegung
AKTIV_FENSTER_MIN = 25      # so lange nach dem letzten Treffer gilt eine Zeile noch als „läuft gerade"

SEITE = {"H": "home", "D": "draw", "A": "away"}


def _load(name, default=None):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def _now():
    return datetime.now(timezone.utc)


def _ts(x):
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None


# ── Das Tor ─────────────────────────────────────────────────────────────────────────────
def kern_ok(sig) -> bool:
    """Die drei gemessenen Bedingungen. Fehlt eine Angabe, ist das kein Ja."""
    if not isinstance(sig, dict):
        return False
    odd = sig.get("odd")
    if not isinstance(odd, (int, float)) or not (MIN_QUOTE <= odd <= MAX_QUOTE):
        return False
    return bool(sig.get("conc")) and bool(sig.get("inflow")) and sig.get("dir") == "in"


def _track_urteil(track, league, market):
    """Liga × Markt aus dem Track — dieselben Schwellen wie im Radar und auf der Übersicht."""
    d = ((track or {}).get("byLeagueMarket") or {}).get("%s|%s" % (league, market))
    if not isinstance(d, dict) or (d.get("n") or 0) < 15 or d.get("roi") is None:
        return None
    roi = d["roi"]
    return {"n": d["n"], "roi": round(roi, 4),
            "traegt": roi >= 0.05, "verliert": roi <= -0.10}


# 30.08.2026 (Lucas-Checkup, dritte Runde) — der Serien-Chip war in drei Punkten falsch:
#
#  1. KEIN MARKTBEZUG. An der Chelsea-SIEGWETTE hing „Über 3,5 Karten ×7". Eine Kartenserie
#     sagt nichts darüber, wer gewinnt. Die Funktion nahm einfach die erste intakte Serie des
#     Teams, egal welcher Markt.
#  2. KEINE MINDESTLÄNGE. Lazio trug „Team trifft ×3" — eine Dreier-Serie mit Grundrate 67%.
#     Die Serien-Kachel auf derselben Seite filtert seit jeher bei length >= 4.
#  3. DIE ERSTE STATT DER STÄRKSTEN. Inter hat „Ungeschlagen ×15" UND „Team trifft ×15";
#     angezeigt wurde, was zufällig zuerst im Array stand.
#
# Der Markt-Filter ist der wichtigste Teil. Gezählt über liga_streaks + mls_streaks sind von
# 205 „Team trifft"-Serien 192 intakt — 94%. Ein Chip, der bei fast jedem Team feuert, ist kein
# Verstärker, sondern Tapete; dieselbe Lehre wie beim Torjäger-Signal. Übrig bleibt, was
# wirklich vom AUSGANG handelt.
SERIEN_MAERKTE = ("ungeschlagen", "sieg-serie", "zu null")   # nur ausgangsbezogene Serien
SERIEN_MIN_LAENGE = 4                                        # wie in der Serien-Kachel


def _streak(streaks, team):
    """Längste intakte, AUSGANGSBEZOGENE Serie des Teams. Fehlt sie, ist das kein Minus."""
    treffer = []
    for s in ((streaks or {}).get("streaks") or []):
        if str(s.get("team") or "").lower() != str(team or "").lower():
            continue
        if (s.get("continuation") or {}).get("state") != "intakt":
            continue
        markt = str(s.get("market") or "").lower()
        if not any(m in markt for m in SERIEN_MAERKTE):
            continue                       # Tore/Karten/Ecken sagen nichts über den Sieger
        if (s.get("length") or 0) < SERIEN_MIN_LAENGE:
            continue
        treffer.append(s)
    if not treffer:
        return None
    s = max(treffer, key=lambda x: x.get("length") or 0)
    return {"art": s.get("market"), "laenge": s.get("length"),
            "quote": (s.get("continuation") or {}).get("ratePct"), "liga": s.get("leagueName")}


def zeile(mid, eintrag, sig, cons_game, track, streaks):
    """Eine Kandidaten-Zeile bauen. Reines Zusammensetzen, keine Entscheidung."""
    fav = sig.get("fav")
    seite = SEITE.get(fav)
    home, away = eintrag.get("home"), eintrag.get("away")
    name = {"home": home, "draw": "Remis", "away": away}.get(seite)
    liga = eintrag.get("league")
    g = cons_game or {}
    poly = g.get("poly") or {}
    pinn = g.get("pinn") or {}
    pm = g.get("pinnMove") or {}

    # Poly zählt nur, wenn es DIESELBE Seite meint. Die Konsens-Zeile hat das schon geprüft
    # (verdict konsens/teil = Anker und Geld sehen dieselbe Seite vorn); zusätzlich muss die
    # Betfair-Geld-Seite dieselbe sein wie die, auf der unser Signal steht.
    # 🔴 01.09.2026 (Lucas: „poly taucht da mmn nie aktiv auf?"). Er hatte recht, und der Grund war
    # ein Doktrin-Verstoss mitten im Geld-Pfad: hier stand `(poly.get("sharePct") or 0) >= 60`.
    # Das `or 0` macht aus einem UNBEKANNTEN Anteil eine 0 — also ein NEIN.
    #
    # Unbekannt ist er oefter, als man denkt: die Holder-Anteile kommen aus
    # `poly_money_broad_close.json`, und dieser Freeze reicht nur bis ~2,8h vor Anpfiff (Median
    # 0,3h). Weiter draussen faellt `pick_poly` auf `poly_money_upcoming.json` zurueck — und die
    # Datei hat ueberhaupt kein `shares`-Feld (0 von 120 Eintraegen), nur Preis und Volumen.
    # Folge: bei 22% der gelatchten Zeilen KANN Poly nicht zustimmen, weil niemand gefragt hat —
    # angezeigt wurde das identisch zu „Poly ist dagegen".
    #
    # Drei Zustaende statt zwei. Stufe 1 verlangt weiterhin ein echtes JA (fehlende Information ist
    # keine Erlaubnis) — aber die Zeile sagt jetzt, ob sie ein Nein oder ein Achselzucken ist.
    _poly_anteil = (poly or {}).get("sharePct")
    _poly_bekannt = isinstance(_poly_anteil, (int, float))
    poly_status = ("unbekannt" if not (poly and _poly_bekannt)
                   else "ja" if (g.get("moneySide") == seite and _poly_anteil >= POLY_MIN_ANTEIL)
                   else "nein")
    poly_gleich = poly_status == "ja"
    pinn_gleich = bool(pinn) and pinn.get("fav") == seite

    verst = []
    if poly_gleich:
        verst.append({"art": "poly", "text": "Poly %d%%" % round(poly.get("sharePct") or 0),
                      "gewicht": 12})
    if pinn_gleich:
        verst.append({"art": "pinn", "text": "Pinnacle stimmt zu", "gewicht": 10})
    if pm.get("move") and (pm.get("movePP") or 0) >= PINN_MIN_MOVE_PP:
        verst.append({"art": "pinnMove",
                      "text": "Pinnacle zieht mit +%.1fpp" % pm["movePP"],
                      "gewicht": 14 if pm.get("laeuft") else 8})
    tr = _track_urteil(track, liga, MARKT)
    if tr and tr["traegt"]:
        verst.append({"art": "track", "text": "Liga trägt (%+d%% · n%d)" % (round(tr["roi"] * 100), tr["n"]),
                      "gewicht": 10})
    st = _streak(streaks, name) if seite in ("home", "away") else None
    if st:
        verst.append({"art": "streak",
                      "text": "%s ×%s" % (st.get("art") or "Serie", st.get("laenge")),
                      "gewicht": 8})

    # Rang: das Tor ist bestanden (Grundwert), darüber zählen die Verstärker. Der Geldanteil
    # geht bewusst nur schwach ein — 90% Anteil ist meist ein Favorit, kein Vorteil.
    rang = 50 + sum(v["gewicht"] for v in verst) + min(10, (sig.get("share") or 0) * 10)

    return {
        "matchId": str(mid), "home": home, "away": away, "league": liga,
        "kickoff": eintrag.get("kickoff"), "markt": MARKT,
        "seite": seite, "name": name, "odd": sig.get("odd"), "entryOdd": sig.get("entryOdd"),
        "anteilPct": round((sig.get("share") or 0) * 100),
        "stufe": 1 if (poly_gleich and pinn_gleich) else 2,
        "verstaerker": verst, "rang": round(rang, 1),
        "track": tr, "streak": st,
        "poly": ({"anteilPct": round(poly.get("sharePct") or 0), "usd": poly.get("vol"),
                  "odd": poly.get("odd")} if poly_gleich else None),
        # Damit die Oberflaeche „dagegen" von „nicht gefragt" unterscheiden kann.
        "polyStatus": poly_status,
        "pinnMovePP": pm.get("movePP"),
        # nur mitschreiben, nicht filtern — s. Kopf, Punkt 4
        "wertVsPinn": (round(sig["pinnFair"] * sig["odd"] - 1, 4)
                       if isinstance(sig.get("pinnFair"), (int, float)) and sig.get("odd") else None),
    }


def _halten(latch: dict, zeilen: list, now) -> dict:
    """Treffer aufnehmen bzw. auffrischen. Der Preis wird beim ERSTEN Halten festgeschrieben —
    er ist der Preis, den die Sektion gezeigt hat. Verstärker dürfen dazukommen (sie machen die
    Zeile stärker, nie schwächer); der Kern-Beleg bleibt der vom ersten Mal."""
    out = dict(latch or {})
    for z in zeilen:
        k = "%s|%s" % (z["matchId"], z["markt"])
        alt = out.get(k)
        if alt is None:
            z = dict(z)
            z["gehaltenSeit"] = now.isoformat()
            z["zuletztAktiv"] = now.isoformat()
            z["haltePreis"] = z.get("odd")
            out[k] = z
        else:
            alt["zuletztAktiv"] = now.isoformat()
            alt["odd"] = z.get("odd")            # aktueller Preis, zum Vergleich mit haltePreis
            alt["kickoff"] = z.get("kickoff") or alt.get("kickoff")
            if len(z.get("verstaerker") or []) > len(alt.get("verstaerker") or []):
                alt["verstaerker"] = z["verstaerker"]
                alt["stufe"] = min(alt.get("stufe", 2), z.get("stufe", 2))
                alt["poly"] = z.get("poly") or alt.get("poly")
                alt["rang"] = max(alt.get("rang", 0), z.get("rang", 0))
    return out


def _faellig(latch: dict, now):
    """(bleibt, angepfiffen) — angepfiffene Zeilen wandern ins Ledger."""
    bleibt, weg = {}, []
    for k, z in (latch or {}).items():
        ko = _ts(z.get("kickoff"))
        (weg.append(z) if (ko and ko <= now) else bleibt.setdefault(k, z))
    return bleibt, weg


def _ledger_fortschreiben(ledger: list, angepfiffen: list, results=None, now=None) -> list:
    """Angepfiffene Halte-Zeilen eintragen und aus dem Betfair-Ergebnis abrechnen.

    Gewinn/Verlust kommt aus betfair_track_results (dieselbe Abrechnung, die auch das
    Liga×Markt-Ergebnis speist) — aber zum HALTEPREIS, nicht zur Schlussquote. Wer der Sektion
    folgt, setzt zu dem Preis, der dastand."""
    now = now or _now()
    ledger = [dict(r) for r in (ledger or [])]
    bekannt = {r["k"] for r in ledger}
    for z in angepfiffen:
        k = "%s|%s" % (z["matchId"], z["markt"])
        if k in bekannt:
            continue
        ledger.append({"k": k, "matchId": z["matchId"], "markt": z["markt"],
                       "liga": z.get("league"), "seite": z.get("seite"), "name": z.get("name"),
                       "haltePreis": z.get("haltePreis"), "schlussPreis": z.get("odd"),
                       "stufe": z.get("stufe"), "gehaltenSeit": z.get("gehaltenSeit"),
                       "zuletztAktiv": z.get("zuletztAktiv"), "kickoff": z.get("kickoff"),
                       "status": "offen", "win": None, "settledAt": None})
        bekannt.add(k)
    if results is None:
        results = _store.load(BASE / "betfair_track_results.json")
    erg = {}
    for r in (results or []):
        if r.get("matchId") and r.get("market"):
            erg["%s|%s" % (r["matchId"], r["market"])] = r
    for r in ledger:
        if r.get("status") != "offen":
            continue
        e = erg.get(r["k"])
        if e is not None and isinstance(e.get("win"), bool):
            r.update(status="abgerechnet", win=e["win"], settledAt=now.isoformat())
            if r.get("schlussPreis") is None:
                r["schlussPreis"] = e.get("odd")
    return ledger[-2000:]


# 30.08.2026: der Badge oben rechts sprang auf GRUEN, sobald das eigene Buch 20 Zeilen hatte und
# der ROI-Punktschaetzer ueber null lag — waehrend die Fusszeile direkt darunter weiter
# „Beobachtungsliste, keine Freigabe" sagte. Bei n=32 / ROI +7,2% liegt die einseitige
# 95%-Untergrenze bei -20,1%: das ist kein Beleg, das ist Rauschen mit Vorzeichen. Genau der
# Fehler, den ich hier schon zweimal gemacht habe (+12,9% wurde +2,4%). Die Sektion liefert die
# Untergrenze jetzt mit, damit die Anzeige denselben Richter benutzt wie freigabe.py.
def _untergrenze(renditen, z: float = 1.645):
    """Einseitige 95%-Untergrenze des mittleren ROI (Normalapproximation). None unter n=2."""
    n = len(renditen)
    if n < 2:
        return None
    m = sum(renditen) / n
    var = sum((x - m) ** 2 for x in renditen) / (n - 1)
    return round(m - z * (var ** 0.5) / (n ** 0.5), 4)


def bilanz(ledger=None, letzte=25):
    """Die eigene Bilanz der Sektion — was sie gezeigt hat und wie es ausging.

    30.08.2026 (Lucas: „sollten wir das nicht mittracken, damit ich seh wie gut es performt?").
    Das Buch lief seit gestern mit, war aber nirgends sichtbar: der Badge oben rechts zeigte die
    Zahl der SCHLUSS-Definition aus betfair_track_record (n=70) — eine verwandte, aber andere
    Menge als das, was in der Sektion wirklich stand. Wer wissen will, ob die Sektion trägt,
    braucht die Bilanz DER SEKTION.

    Gerechnet wird zum HALTEPREIS, also zu dem Preis, der dastand, als die Zeile erschien —
    nicht zur Schlussquote. Nur der ist tatsächlich nehmbar gewesen. Einsatz: flach 1 Einheit
    je Zeile, damit die Zahl nicht von einer Staking-Entscheidung abhängt, die es hier nicht gibt.
    """
    rows = ledger if ledger is not None else _load(LEDGER_FILE, [])

    def leer():
        return {"n": 0, "gewonnen": 0, "verloren": 0, "einheiten": 0.0, "roi": None,
                "roiLb": None, "renditen": []}

    def zu(b, r, o):
        b["n"] += 1
        if r.get("win"):
            b["gewonnen"] += 1; b["einheiten"] += (o - 1.0); b["renditen"].append(o - 1.0)
        else:
            b["verloren"] += 1; b["einheiten"] -= 1.0; b["renditen"].append(-1.0)

    gesamt, je_stufe, zeilen, offen = leer(), {"1": leer(), "2": leer()}, [], 0
    for r in (rows or []):
        if r.get("status") == "offen":
            offen += 1
            continue
        if r.get("status") != "abgerechnet":
            continue                      # void zählt weder als Treffer noch als Fehlschlag
        o = r.get("haltePreis")
        if not isinstance(o, (int, float)) or not (MIN_QUOTE <= o <= MAX_QUOTE):
            continue
        zu(gesamt, r, o)
        zu(je_stufe.get(str(r.get("stufe")), je_stufe["2"]), r, o)
        zeilen.append({"name": r.get("name"), "liga": r.get("liga"), "stufe": r.get("stufe"),
                       "haltePreis": o, "schlussPreis": r.get("schlussPreis"),
                       "win": bool(r.get("win")), "settledAt": r.get("settledAt")})
    for b in [gesamt] + list(je_stufe.values()):
        b["roi"] = round(b["einheiten"] / b["n"], 4) if b["n"] else None
        b["roiLb"] = _untergrenze(b.pop("renditen"))
        b["einheiten"] = round(b["einheiten"], 2)
    zeilen.sort(key=lambda z: z.get("settledAt") or "", reverse=True)
    return {"gesamt": gesamt, "jeStufe": je_stufe, "offen": offen, "zeilen": zeilen[:letzte]}


def schublade_gehalten(ledger=None):
    """ROI der GEHALTENEN Treffer zum Haltepreis — die Menge, die die Sektion wirklich zeigt.

    Getrennt von schublade(): die misst die Schluss-Definition von betfair_track_record. Beide
    nebeneinander im Freigabe-Register beantworten die Frage, ob das Halten die Kante kostet."""
    rows = ledger if ledger is not None else _load(LEDGER_FILE, [])
    renditen, letzter = [], None
    for r in (rows or []):
        if r.get("status") != "abgerechnet":
            continue
        o = r.get("haltePreis")
        if not isinstance(o, (int, float)) or not (MIN_QUOTE <= o <= MAX_QUOTE):
            continue
        renditen.append((o - 1.0) if r.get("win") else -1.0)
        s = r.get("settledAt")
        if s and (letzter is None or s > letzter):
            letzter = s
    return {"renditen": renditen, "clvs": [], "letzter": letzter}


def baue(state=None, consensus=None, track=None, streaks=None, now=None,
         latch_state=None) -> dict:
    now = now or _now()
    if latch_state is None:
        latch_state = _load(STATE_FILE, {})
    state = state if state is not None else _load("betfair_track_state.json")
    cons = consensus if consensus is not None else _load("betfair_consensus.json")
    track = track if track is not None else _load("betfair_track_record.json")
    if streaks is None:
        streaks = {"streaks": (_load("liga_streaks.json").get("streaks") or [])
                   + (_load("mls_streaks.json").get("streaks") or [])}

    spiele = {str(g.get("matchId")): g for g in ((cons or {}).get("games") or [])}
    zeilen = []
    for mid, e in ((state or {}).get("pending") or {}).items():
        sig = (e.get("signals") or {}).get(MARKT)
        if not kern_ok(sig):
            continue
        ko = _ts(e.get("kickoff"))
        if ko and ko <= now:
            continue                       # angepfiffen: der Track erfasst nur vor Anpfiff
        z = zeile(mid, e, sig, spiele.get(str(mid)), track, streaks)
        tr = z.get("track")
        if tr and tr["verliert"]:
            continue                       # belegt verlierender Eimer gehört nicht in eine Empfehlung
        zeilen.append(z)

    # Halten statt live zeigen — Begründung oben bei STATE_FILE.
    latch = _halten((latch_state or {}).get("latch") or {}, zeilen, now)
    latch, angepfiffen = _faellig(latch, now)

    gezeigt = sorted(latch.values(), key=lambda r: (r["stufe"], -(r.get("rang") or 0)))
    for z in gezeigt:
        za = _ts(z.get("zuletztAktiv"))
        z["aktiv"] = bool(za and (now - za).total_seconds() <= AKTIV_FENSTER_MIN * 60)
    return {
        "generatedAt": now.isoformat(),
        "stufe1": [z for z in gezeigt if z["stufe"] == 1],
        "stufe2": [z for z in gezeigt if z["stufe"] == 2],
        "_latch": latch, "_angepfiffen": angepfiffen,
        "regeln": {
            "markt": MARKT, "minAnteil": CONC_THRESHOLD, "minZuflussEur": INFLOW_MIN_EUR,
            "quote": [MIN_QUOTE, MAX_QUOTE], "polyMinAnteilPct": POLY_MIN_ANTEIL,
            "haeltBisAnpfiff": True,
            "text": "Stufe 2 = Geldanteil ≥%d%% UND frischer Zufluss ≥€%d UND Quote zieht mit — "
                    "einmal erfüllt, bleibt der Treffer bis zum Anpfiff stehen. "
                    "Stufe 1 = zusätzlich Poly-Geld ≥%d%% und Pinnacle-Favorit auf derselben Seite."
                    % (round(CONC_THRESHOLD * 100), INFLOW_MIN_EUR, POLY_MIN_ANTEIL),
        },
    }


# ── Freigabe-Schublade: rechnet sich aus DEMSELBEN Ledger, das die Zeilen abrechnet ──────
# ── Ligen-Zuschnitt (31.08.2026, Lucas: „nur die Top 5 lassen oder erweitert?") ─────────────
# Gemessen über die 8.000 abgerechneten Track-Zeilen, Konjunktion auf Match Odds:
#
#   Top-5 + MLS   n= 10   ROI +21,8% (UG -25,1%)   CLV +1,65pp (UG -0,12)
#   uebrige Ligen n= 70   ROI  -3,1% (UG -21,1%)   CLV +3,61pp (UG +2,76)
#
# Zwei Dinge, die gegen ein schnelles Urteil sprechen: die Konjunktion feuert in den Top-5
# DREIMAL haeufiger (16,1% der Match-Odds-Zeilen gegen 5,9%) — Einschraenken hungert die Sektion
# also weniger aus als gedacht. Aber der einzige Beleg, dessen Untergrenze ueber null liegt,
# sitzt im Rest. Bei n=10 gegen n=70 ist das heute nicht entscheidbar.
#
# Also nicht einschraenken, sondern TRENNEN: zwei Schubladen, die sich getrennt qualifizieren.
# In ein paar Wochen beantwortet die Frage sich selbst — und bis dahin wird nichts weggeworfen
# ([[feedback_blocked_segments_observe]]: sperren, nie loeschen).
#
# ⚠️ Das sind die BETFAIR-Schreibweisen, nicht die Codes aus stats_scope.json. Dieselbe Liga
# heisst hier „US MLS" und dort „MLS" — die beiden Listen haben verschiedene Aufgaben und
# duerfen NICHT zusammengelegt werden: stats_scope entscheidet ueber die CARD-Bilanz, diese
# hier ueber den Zuschnitt einer Geld-Sektion.
TOP5_LIGEN = frozenset({
    "English Premier League", "Spanish La Liga", "German Bundesliga",
    "Italian Serie A", "French Ligue 1", "US MLS",
})


def im_zuschnitt(liga, scope) -> bool:
    """Gehoert diese Liga in den Zuschnitt? `scope` None = alles, 'top5', 'rest'. REIN."""
    if scope is None:
        return True
    drin = str(liga or "") in TOP5_LIGEN
    return drin if scope == "top5" else (not drin)


def schublade(results=None, scope=None):
    """ROI und CLV je Zeile für die Konjunktion — Rohwerte, damit freigabe.bewerte urteilen kann.

    `scope`: None = alle Ligen, 'top5' = Top-5 + MLS, 'rest' = alles andere (s. TOP5_LIGEN).

    Der grosse Unterschied zu den bisherigen Betfair-Schubladen: die rechnen auf Aggregaten
    (byLeagueMarket) und kommen deshalb nie über „geprueft" hinaus, weil dort kein CLV je
    Signal steht. Hier liegen die Rohzeilen vor — inklusive clvBf. Damit kann diese Schublade
    tatsächlich freigegeben werden, statt es nur zu behaupten."""
    rows = results if results is not None else _store.load(BASE / "betfair_track_results.json")
    renditen, clvs, letzter = [], [], None
    for r in (rows or []):
        if r.get("market") != MARKT:
            continue
        if not (r.get("conc") and r.get("inflow") and r.get("dir") == "in"):
            continue
        if not im_zuschnitt(r.get("league"), scope):
            continue
        odd = r.get("odd")               # Closing-Quote: Signal und Preis im selben Moment
        if not isinstance(odd, (int, float)) or odd <= 1:
            continue
        if not (MIN_QUOTE <= odd <= MAX_QUOTE):
            continue
        renditen.append((odd - 1.0) if r.get("win") else -1.0)
        if isinstance(r.get("clvBf"), (int, float)):
            clvs.append(r["clvBf"])
        s = r.get("settledAt")
        if s and (letzter is None or s > letzter):
            letzter = s
    return {"renditen": renditen, "clvs": clvs, "letzter": letzter}


def main():
    out = baue()
    latch = out.pop("_latch", {})
    angepfiffen = out.pop("_angepfiffen", [])
    (BASE / STATE_FILE).write_text(json.dumps({"latch": latch}, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    led = _ledger_fortschreiben(_load(LEDGER_FILE, []), angepfiffen)
    (BASE / LEDGER_FILE).write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
    # Die eigene Bilanz reist mit der Sektion mit — sonst müsste das Frontend ein zweites Buch
    # laden, nur um sagen zu können, wie gut das hier läuft. Sie wird NACH dem Fortschreiben
    # gerechnet: baue() lief vorher und kannte die Zeilen dieses Laufs noch nicht, die Bilanz
    # wäre sonst dauerhaft einen Lauf alt (aufgefallen als „offen 4" bei 11 Zeilen im Buch).
    out["bilanz"] = bilanz(led)
    (BASE / OUT_FILE).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    ab = sum(1 for r in led if r.get("status") == "abgerechnet")
    print("killer: Stufe1=%d Stufe2=%d · gehalten %d · Ledger %d (%d abgerechnet)"
          % (len(out["stufe1"]), len(out["stufe2"]), len(latch), len(led), ab))


if __name__ == "__main__":
    main()
