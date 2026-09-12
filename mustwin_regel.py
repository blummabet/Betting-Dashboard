#!/usr/bin/env python3
"""Die eine Regel, wann `mustWin` gesetzt sein darf — und wer sie kennen muss.

🔴 12.09.2026 (Lucas, Plattform-Audit). `calc_pressure()` setzt `mustWin = pressureRatio > 0.65`.
Beim Bauen des Stakes wird das aber noch einmal eingeschraenkt (update_dashboard.py):

    "mustWin": h_pressure.get("mustWin", False) and h_motiv == 'full'

Begruendung dort: bestaetigte ('none') und praktisch erledigte ('low') Teams spielen nicht mit
Must-Win-Intensitaet, auch wenn die Tabellenrechnung hohen Druck ergibt.

Der Validator kannte diese Einschraenkung nicht. Er prueft `pressureRatio > 0.65 and not mustWin`
und meldete das als **Fehler in calc_pressure**. Gemessen am echten Datenstand: **53 Faelle, alle
mit motivationLevel='low'** — also 53 Fehlalarme und kein einziger echter Fund.

Das ist nicht harmlos. Es waere der erste Befund gewesen, den die neue Validator-Karte in der
Status-Uebersicht gezeigt haette: 26 rote Fehler, die keine sind. Genau so wird ein Waechter
abgeschaltet.

Deshalb steht die Regel ab jetzt an EINER Stelle, und beide Seiten fragen hier nach, statt sie
zu wiederholen:

  · `update_dashboard.py` beim Bauen des Stakes
  · `check_picks_logic.py` beim Pruefen des Stakes

Fehlerklasse: eine Regel, die zwei Module unabhaengig voneinander kennen muessen, driftet. Immer.
"""

# Nur bei voller Motivation zaehlt hoher Tabellendruck als Must-Win.
MOTIV_MIT_MUSTWIN = ("full",)


def mustwin_erlaubt(motivation_level) -> bool:
    """Darf `mustWin` bei dieser Motivationslage ueberhaupt True sein?"""
    return (motivation_level or "full") in MOTIV_MIT_MUSTWIN


def mustwin_setzen(roher_mustwin, motivation_level) -> bool:
    """Der gesetzte Wert — genau so, wie ihn das Dashboard in den Stake schreibt."""
    return bool(roher_mustwin) and mustwin_erlaubt(motivation_level)


def widerspruch(pressure_ratio, mustwin, motivation_level) -> bool:
    """Ist `pressureRatio > 0.65 ohne mustWin` hier wirklich ein Widerspruch?

    Nur wenn die Motivationslage Must-Win zulassen WUERDE. Sonst ist das genau der Zustand, den
    die Unterdrueckung oben absichtlich herstellt — und ein Fehler ist es dann nicht.
    """
    if pressure_ratio is None or pressure_ratio <= 0.65 or mustwin:
        return False
    return mustwin_erlaubt(motivation_level)
