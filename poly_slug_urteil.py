#!/usr/bin/env python3
"""
poly_slug_urteil.py — welcher Slug-Sieger darf eine Wette überhaupt entscheiden?
================================================================================
04.09.2026. Lucas hatte einen Public-Push als Verlust gebucht, unser Buch als Treffer:

    💰 $41K auf Over      →  Leeds United FC v Brentford FC, Endstand 1:1

Er hat nachgesehen — **der Preis gehörte zu Over 2,5**. 1:1 sind zwei Tore, die Wette war also
verloren. `poly_resolutions.json` sagte trotzdem `epl-lee-bre-2026-08-30-more-markets → "Over"`,
und unser Buch hat daraus einen Treffer gemacht. **Wir haben einen Gewinn erfunden.**

## Warum das kein Einzelfall ist
Ein `-more-markets`-Slug ist auf Polymarket kein Markt, sondern ein **Bündel**: Over/Under auf
mehreren Linien, BTTS, Ecken. Ein einziger Eintrag `{key: "…-more-markets", winner: "Over"}` kann
diese Linien nicht auseinanderhalten — bei 1:1 gewinnt Over 1,5 und verliert Over 2,5, und beide
heißen im Sieger-Feld gleich.

Im Bestand stecken **3.103 Bündel-Auflösungen, davon 3.029 mit „Over" oder „Under"** (1.518
Under, 1.511 Over). Jede davon kann eine Wette auf dieselbe Seite falsch entscheiden — in beide
Richtungen. Betroffen ist nicht nur das Public-Buch: `poly_wallet_track.json` führt solche
Positionen offen mit, und aus deren Abrechnung entsteht die Wallet-Trefferquote, die wiederum
darüber entscheidet, **wer überhaupt in den Public-Kanal gepusht wird**. Ein falscher Treffer
dort macht eine Wallet „scharf", die es nicht ist.

## Die Regel
Wo der Sieger-Name die Linie nicht trägt, wird **nicht abgerechnet** — weder als Treffer noch als
Fehlschlag. Der Eintrag bleibt offen und läuft nach der üblichen Frist in `unaufloesbar`. Das
senkt den Nenner sichtbar, statt ein Ergebnis zu erfinden: fehlende Information ist keine
Erlaubnis, und die falsche Richtung wäre hier besonders teuer, weil ein erfundener Treffer die
Rangliste nach oben verzerrt.

Bündel-Slugs mit einem ECHTEN Ausgang (`…-more-markets → "England"`, ein Torschütze) bleiben
abrechenbar — gesperrt wird, was mehrdeutig ist, nicht was einen bestimmten Slug hat.

REIN/testbar, keine Datei-Zugriffe.
"""
from __future__ import annotations

# Ausgangs-Namen, die ohne die Marktfrage nichts bezeichnen. „Draw" steht bewusst NICHT drin:
# im Moneyline-Markt ist das Unentschieden ein eindeutiger Ausgang.
GENERISCH = {"over", "under", "über", "ueber", "unter", "yes", "no", "ja", "nein"}

# Slug-Endungen, hinter denen auf Polymarket ein Bündel mehrerer Märkte liegt.
BUENDEL = ("-more-markets",)


def ist_generisch(name) -> bool:
    """Trägt dieser Ausgangs-Name für sich genommen eine Bedeutung? REIN."""
    return str(name or "").strip().lower() in GENERISCH


def ist_buendel(key) -> bool:
    """Steckt hinter dem Slug ein Bündel mehrerer Märkte? REIN."""
    k = str(key or "")
    return any(k.endswith(e) or (e + "|") in k for e in BUENDEL)


def aufloesbar(key, seite, sieger=None, cond=None) -> bool:
    """Darf dieser Slug-Sieger über eine Wette auf `seite` entscheiden? REIN.

    False genau dann, wenn der Slug ein Bündel ist UND die Bedeutung an einer Linie hängt, die
    im Namen nicht steht — dann ist „Over" gegen „Over" kein Vergleich, sondern ein Zufall.

    `cond` ist der Ausweg: die conditionId nagelt EINEN Markt des Bündels fest. Ist sie da, wurde
    bei der Erfassung und bei der Auflösung derselbe Markt gelesen, und „Over" bezeichnet
    dieselbe Linie. Genau das war vorher nicht garantiert — `_outcomes` wählt den Markt mit dem
    meisten Volumen, und Volumen verschiebt sich zwischen Anpfiff und Abrechnung.
    """
    if not ist_buendel(key):
        return True
    if cond:
        return True
    return not (ist_generisch(seite) or ist_generisch(sieger))


# ── Der Ausweg über den Endstand (22.09.2026) ────────────────────────────────────────────
# 🔴 Lucas' Störungsmeldung vom 22.09., 06:02 UTC, unter „Kostet Geld":
#
#     spl-haz-taa-2026-09-08-more-markets: seit 13.6 Tagen offen — Bündel: der Eintrag kennt
#     seinen Markt, die Auflösung nicht (Altbestand)
#     ucl-aek1-lin2-2026-09-08-more-markets: seit 13.5 Tagen offen — dasselbe
#
# Der Riegel ist richtig: die Auflösung sagt „Under", und in einem `-more-markets`-Bündel liegen
# Under 1,5 und Under 3,5 nebeneinander. Ohne `cond` auf BEIDEN Seiten ist „Under" kein Ergebnis,
# sondern ein Münzwurf mit Etikett. Abgerechnet wird deshalb nicht — und nach 14 Tagen verfällt
# der Eintrag als „unauflösbar".
#
# Nur: der Ausgang steht daneben. Die Auflösung `…-exact-score` desselben Spiels trägt den
# ENDSTAND („AEK 1 - 0 LASK Linz"), und der Eintrag trägt seit dem 10.09. die LINIE im Klartext
# („AEK vs. LASK Linz: O/U 3.5"). Eine Torlinie gegen eine Torzahl ist keine Schätzung, sondern
# Arithmetik: 1 Tor, Linie 3,5 → Under. Gemessen am Buch: 13 der 17 verfallenen Einträge sind
# Bündel, bei 10 davon lag der Endstand die ganze Zeit vor.
#
# Fehlerklasse: **eine Frage für unbeantwortbar erklärt, während ihre Antwort in der Datei
# daneben steht.**
#
# Die Regel rechnet NUR, wo sie eindeutig ist, und schweigt sonst:
#   · genau EINE Linie im Text, sonst None
#   · genau EIN Endstand-Muster, sonst None — Vereinsnamen tragen Ziffern („Schalke 04")
#   · eine GANZZAHLIGE Linie (O/U 3) kann push sein → None, kein geratener Sieger
import re as _re

_LINIE = _re.compile(r"(?:O\s*/?\s*U|Over\s*/?\s*Under|Total(?:s)?)\s*([0-9]+(?:[.,][0-9]+)?)", _re.I)
_ENDSTAND = _re.compile(r"(?<![0-9])([0-9]{1,2})\s*[-–:]\s*([0-9]{1,2})(?![0-9])")


def linie(frage):
    """Die Torlinie aus der Marktfrage. REIN. None = nicht eindeutig.

    „AEK vs. LASK Linz: O/U 3.5" -> 3.5. Zwei Linien im Text heissen zwei Maerkte und damit
    keine Antwort.
    """
    t = str(frage or "")
    tref = _LINIE.findall(t)
    if len(tref) != 1:
        return None
    try:
        return float(tref[0].replace(",", "."))
    except ValueError:
        return None


def endstand(sieger):
    """Die Tore aus einer `exact-score`-Aufloesung. REIN. None = nicht eindeutig.

    „AEK 1 - 0 LASK Linz" -> (1, 0). Gegen Ziffern in Vereinsnamen helfen zwei Dinge: das
    Muster verlangt einen Trenner ZWISCHEN zwei Zahlen (in „FC Schalke 04 2 - 1 Hertha" passt
    nur „2 - 1"), und es nimmt hoechstens zwei Stellen je Seite (eine Jahreszahl wie
    „FC 1899 - 2000" faellt damit raus). Bleiben trotzdem zwei Treffer, gilt der Endstand als
    nicht eindeutig — lieber keine Abrechnung als eine aus dem Vereinsnamen.
    """
    tref = _ENDSTAND.findall(str(sieger or ""))
    if len(tref) != 1:
        return None
    try:
        return int(tref[0][0]), int(tref[0][1])
    except ValueError:
        return None


def ausgang_aus_endstand(frage, exact_sieger):
    """„Over" | „Under" | None — der Ausgang eines Totals-Marktes aus dem Endstand. REIN.

    None heisst „nicht entscheidbar" und nie „Under": eine ganzzahlige Linie, die genau
    getroffen wird, ist ein Push und hat keinen Sieger.
    """
    ln = linie(frage)
    es = endstand(exact_sieger)
    if ln is None or es is None:
        return None
    tore = es[0] + es[1]
    if tore == ln:
        return None                      # Push — kein Sieger, also auch kein geratener
    return "Over" if tore > ln else "Under"
