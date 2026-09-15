"""odds_plausibility.py — ist ein 1X2-Snapshot ein ECHTER Markt oder ein Platzhalter?

13.07.2026 (Lucas: „schau dir den Sharp Radar nochmal an"). Befund: die MLS-History enthielt
Eröffnungs-Snapshots wie hw=1.04 / dr=1.01 / aw=1.04 — Overround **291 %**. Ein echter 1X2-Markt
liegt bei 102–110 %. Das sind Platzhalter der Quellen-API beim Markt-Opening, keine Quoten.

Folgen (alle drei real eingetreten):
  · Sharp Radar zeigte Fake-Mover (PSG „1.02 → 1.40", +37pp)
  · detect_wm_sharp_moves meldete **80,8pp „STEAM"** und hat dafür schon Telegram-Alerts gesendet
  · jede CLV-/Drift-Rechnung auf snaps[0] war verseucht

`odds_open` in {ds}-data.json ist bereits geheilt (fetch_liga_odds friert das Opening kohärent ein).
Verseucht ist die **History** — und genau die lesen Radar und Detektor (`snaps[0]` / `prev`).

Diese Datei ist die EINE Quelle für die Regel. Vorher lag `_plausible_1x2` doppelt in
steam_engine.py und fetch_liga_odds.py — beide delegieren jetzt hierher, damit die Schwellen nie
auseinanderlaufen.

Regel (bewusst konservativ — lieber einen echten Extremmarkt verwerfen als einen Geist melden):
  · alle drei Quoten vorhanden
  · hw ≥ 1.05, aw ≥ 1.05  (kürzer gibt es real praktisch nicht)
  · dr ≥ 1.50            (ein Remis unter 1.50 existiert nicht)
  · Overround 1.00–1.30  (unter 1.0 = Arbitrage-Geschenk = Fehler; über 1.30 = Platzhalter)

Teil-Snapshots (nur hw gesetzt, kein volles 1X2) werden NICHT verworfen — dort lässt sich die
Marge nicht prüfen, und ein Fehlurteil wäre schlimmer als keins.
"""
from __future__ import annotations

MIN_SIDE_ODDS = 1.05
MIN_DRAW_ODDS = 1.50
MIN_OVERROUND = 1.00
MAX_OVERROUND = 1.30


def plausible_1x2(hw, dr, aw) -> bool:
    """True = echter Markt. Nur für VOLLE 1X2-Sätze aussagekräftig."""
    if not (hw and dr and aw):
        return False
    try:
        hw, dr, aw = float(hw), float(dr), float(aw)
    except (TypeError, ValueError):
        return False
    if hw < MIN_SIDE_ODDS or aw < MIN_SIDE_ODDS or dr < MIN_DRAW_ODDS:
        return False
    overround = 1.0 / hw + 1.0 / dr + 1.0 / aw
    return MIN_OVERROUND <= overround <= MAX_OVERROUND


# 07.09.2026 — die BESTPREIS-Linie braucht eine eigene Untergrenze, und zwar aus genau dem
# Grund, aus dem die obere Regel richtig ist. `plausible_1x2` verwirft alles unter Overround 1,00
# als „Arbitrage-Geschenk = Fehler". Fuer EIN Buch stimmt das. Die Best-of-N-Linie (Maximum ueber
# ~29 Buecher je Ausgang) summiert dagegen regelmaessig UNTER 1,00 — das ist kein Fehler, das ist
# ihr ganzer Zweck: nur dann gibt es ueberhaupt Value. Schon mit drei Buechern kam im Test
# Booksum 0,9868 heraus.
#
# Deshalb eine zweite Regel statt einer aufgeweichten ersten: die alte Schwelle schuetzt weiter
# die Steam-/CLV-Maschinerie (die auf Einzelbuch-Linien rechnet) unveraendert, und die neue laesst
# genau das zu, was sie zulassen soll. Nach unten bleibt eine Grenze — eine Booksum unter 0,90
# ueber 29 Buecher ist kein Markt, sondern ein Mapping-Fehler (falsche Seite, falsche Linie).
MIN_OVERROUND_BEST = 0.90   # Best-of-N summiert bewusst unter 100 %


def plausible_best_1x2(hw, dr, aw) -> bool:
    """True = plausible BESTPREIS-Linie (Maximum ueber mehrere Buecher). Wie plausible_1x2,
    aber mit gesenkter Overround-Untergrenze — s. Kommentar oben."""
    if not (hw and dr and aw):
        return False
    try:
        hw, dr, aw = float(hw), float(dr), float(aw)
    except (TypeError, ValueError):
        return False
    if hw < MIN_SIDE_ODDS or aw < MIN_SIDE_ODDS or dr < MIN_DRAW_ODDS:
        return False
    return MIN_OVERROUND_BEST <= (1.0 / hw + 1.0 / dr + 1.0 / aw) <= MAX_OVERROUND


def devig_1x2(hw, dr, aw):
    """De-viggte faire Wahrscheinlichkeiten {home,draw,away} — ODER None bei Platzhalter-Quoten.

    19.07.2026 (Lucas: „ich hasse es, wenn Fehler mehrfach auftauchen"). Die Bug-Klasse „aus
    Platzhalter-Quoten wird eine Fake-Fair/-Edge gerechnet" ist mehrfach an NEUEN Stellen
    aufgetaucht (Sharp Radar, Picks, market_drift, Telegram-Edge-Alerts), weil jede Stelle die
    De-Vig neu inline schrieb — mal mit, mal OHNE Plausibilitätsprüfung. Das ist die EINE sichere
    De-Vig: sie gibt gar nichts zurück, wenn die Quoten kein echter Markt sind. Wer sie benutzt,
    KANN den Fehler nicht mehr machen. Der Regression-Guard (tests/test_no_unguarded_1x2_devig.py)
    verhindert, dass jemand wieder eine rohe De-Vig einschmuggelt."""
    if not plausible_1x2(hw, dr, aw):
        return None
    hw, dr, aw = float(hw), float(dr), float(aw)
    margin = 1.0 / hw + 1.0 / dr + 1.0 / aw
    return {"home": round((1.0 / hw) / margin, 4),
            "draw": round((1.0 / dr) / margin, 4),
            "away": round((1.0 / aw) / margin, 4)}


def devig_power(odds, tol=1e-12, schritte=200):
    """De-Vig nach der POWER-Methode: p_i = (1/o_i)^k, k so gewaehlt, dass die Summe 1 ergibt.

    🔴 14.09.2026 (Logik-Check Trading, Lucas: „miss die devig mit"). Die faire
    Wahrscheinlichkeit entsteht bisher proportional — jede implizite durch die Marge geteilt.
    Das verteilt die Marge gleichmaessig, obwohl Buchmacher sie bekanntlich staerker auf die
    Aussenseiter legen. Gemessen an den echten Pinnacle-Quoten (proportional MINUS power):

        1X2   unter 20 %  +0,88pp        Over/Under  20–40 %  +1,36pp
              ueber 60 %  −1,81pp                    ueber 60 %  −1,53pp

    Ueber alle Ausgaenge hebt sich das auf — es ist eine Umverteilung. Aber gesetzt wird nur, wo
    die Edge POSITIV und ueber der Schwelle ist, also auf der billigen Seite: fuer Ausgaenge unter
    40 Cent betraegt der Aufschlag im Schnitt **+1,47pp**. Genau dort lagen alle drei bisherigen
    Auto-Trades (40¢, 35¢, 36¢), und die groesste gemeldete Edge war +3,7pp.

    ⚠️ Diese Funktion ENTSCHEIDET NICHTS. Welche De-Vig naeher an der Wahrheit liegt, ist eine
    Modellwahl und keine Tatsache; sie auf Verdacht umzustellen hiesse, eine unbelegte Zahl durch
    eine andere zu ersetzen. Sie laeuft ab dem 14.09.2026 nur mit, damit in ein paar Wochen der
    CLV entscheiden kann — welcher faire Wert naeher am Schlusskurs lag. Bis dahin bleibt
    `devig_1x2` der scharfe Pfad.

    Gibt None, wenn die Quoten kein echter Markt sind (gleiche Gate-Logik wie devig_1x2) oder die
    Summe der impliziten Wahrscheinlichkeiten nicht ueber 1 liegt (dann gibt es keine Marge).
    """
    try:
        o = [float(x) for x in odds]
    except (TypeError, ValueError):
        return None
    if len(o) < 2 or any(x <= 1.0 for x in o):
        return None
    imp = [1.0 / x for x in o]
    if sum(imp) <= 1.0:
        return None
    lo, hi = 0.5, 4.0
    for _ in range(schritte):
        k = (lo + hi) / 2
        s = sum(x ** k for x in imp)
        if abs(s - 1.0) < tol:
            break
        if s > 1.0:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    return [round(x ** k, 4) for x in imp]


def devig_1x2_power(hw, dr, aw):
    """Power-De-Vig fuer 1X2 — hinter demselben Plausibilitaets-Gate wie devig_1x2. NUR Messung."""
    if not plausible_1x2(hw, dr, aw):
        return None
    p = devig_power([hw, dr, aw])
    if not p:
        return None
    return {"home": p[0], "draw": p[1], "away": p[2]}


def derive_double_chance(hw, dr, aw):
    """Doppelte Chance {dc1X, dc12, dcX2} aus dem 1X2 ableiten — ODER None bei Platzhaltern.

    25.07.2026 (Lucas: „bei Sieg-Quote >2 nehmen wir doch die sichere Linie — war bei WM so").
    Die sichere-Linien-Ableitung (Heimsieg → Doppelte Chance 1X) braucht DC-Quoten. WM holt DC
    per Event-Endpoint; fetch_liga_odds (MLS/Liga) holt nur h2h/totals/spreads → DC fehlte → die
    sichere Linie feuerte für MLS/Liga NIE. DC ist deterministisch aus dem 1X2: die Buchmacher
    bepreisen sie genauso (implizite Wahrscheinlichkeiten der zwei Ausgänge addiert, Vig bleibt
    proportional erhalten). Gegatet über plausible_1x2 — nie aus Platzhalter-Quoten ableiten."""
    if not plausible_1x2(hw, dr, aw):
        return None
    hw, dr, aw = float(hw), float(dr), float(aw)
    ih, idr, ia = 1.0 / hw, 1.0 / dr, 1.0 / aw
    return {"dc1X": round(1.0 / (ih + idr), 3),   # Heim oder Remis
            "dc12": round(1.0 / (ih + ia), 3),    # Heim oder Auswärts
            "dcX2": round(1.0 / (idr + ia), 3)}   # Remis oder Auswärts


def snap_ok(snap) -> bool:
    """Darf dieser History-Snapshot für Move-/Drift-Rechnungen benutzt werden?

    Teil-Snapshots (kein volles 1X2) → True (nicht beurteilbar, nicht verwerfen).
    Volles 1X2 → nur wenn plausibel.
    """
    if not isinstance(snap, dict):
        return False
    hw, dr, aw = snap.get("hw"), snap.get("dr"), snap.get("aw")
    if not (hw and dr and aw):
        return True
    return plausible_1x2(hw, dr, aw)


def clean_snaps(snaps):
    """Platzhalter aus einer History-Liste werfen — DIE Stelle, an der Geister sterben.

    Wichtig: Reihenfolge bleibt erhalten, damit snaps[0] weiterhin „Opening" heißt (dann eben das
    erste ECHTE Opening) und prev/curr weiterhin echte Nachbarn sind.
    """
    if not snaps:
        return []
    return [s for s in snaps if snap_ok(s)]


def first_plausible(snaps):
    """Erster echter Snapshot (= geheiltes Opening) oder None."""
    for s in (snaps or []):
        if isinstance(s, dict) and s.get("hw") and s.get("dr") and s.get("aw"):
            if plausible_1x2(s["hw"], s["dr"], s["aw"]):
                return s
    return None
