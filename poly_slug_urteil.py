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
