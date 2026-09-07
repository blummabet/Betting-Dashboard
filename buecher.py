"""buecher.py — welche Buchmacher kann Lucas wirklich bespielen?

07.09.2026, Lucas: „das heisst dann wir geben diese picks wo an? mit den quoten dann quasi von
softbookies oder wie?"

Die Frage hat einen Fehler in meinem eigenen Bau aufgedeckt, bevor irgendetwas davon live war.

`fetch_liga_odds.py` holt `regions=eu,uk,us` — im Bestand stehen Konsense aus bis zu **46
Büchern**. Das Maximum ueber ALLE waere systematisch bei US-Buchmachern gelandet (DraftKings,
FanDuel, BetMGM …), bei denen man aus Niederoesterreich kein Konto eroeffnen kann. Das Board
haette dann echte, korrekt gerechnete Value-Funde gezeigt, die **nicht spielbar** sind.

Das ist genau die Klasse, gegen die dieses Repo sonst antritt — nur eine Ebene hoeher: nicht
eine falsche Zahl, sondern eine richtige Zahl, auf die man nicht handeln kann. Ein Bestpreis bei
einem unerreichbaren Buch ist kein Preis.

Deshalb: eine ausdrueckliche Liste. Sie ist bewusst KONSERVATIV — lieber ein spielbares Buch zu
wenig als ein Fund, der beim Anklicken verpufft. Wer ein Konto dazubekommt, traegt es hier ein;
wer eines verliert (das ist bei dieser Strategie der Normalfall, s. wert_scanner.py), nimmt es
raus. Die Liste ist damit auch die ehrlichste Stelle, an der der Kontenbestand dokumentiert ist.

⚠️ Diese Datei entscheidet NICHT, ob eine Quote gut ist — nur, ob man sie nehmen kann. Die
Bewertung passiert in wert_scanner.py gegen den entvigten Sharp-Anker.
"""
from __future__ import annotations

# TheOddsAPI-Schluessel. Nur Buecher, die aus Oesterreich/EU regulaer erreichbar sind.
# Sharp-Buecher stehen NICHT hier: Pinnacle ist der Massstab, nicht der Ort, an dem gespielt
# wird — und die Boersen laufen ueber ihren eigenen Pfad (fade_unter.py).
SPIELBAR = frozenset({
    "bet365", "betsson", "betvictor", "bwin", "coolbet", "everygame",
    "interwetten", "leovegas", "marathonbet", "mrgreen", "nordicbet",
    "onexbet", "betclic", "betfair", "unibet", "unibet_eu", "unibet_nl",
    "unibet_it", "unibet_fr", "williamhill",
    "tipico", "betano", "winamax_de", "winamax_fr", "sport888", "888sport",
})

# Ausdruecklich NICHT spielbar — hier nur dokumentiert, damit niemand sie versehentlich
# aufnimmt, weil sie im Feed „gute" Quoten zeigen.
NICHT_SPIELBAR_HINWEIS = (
    "US-Buecher (draftkings, fanduel, betmgm, caesars, pointsbetus, betrivers, "
    "williamhill_us, superbook, wynnbet, betonlineag, lowvig, mybookieag, bovada) und "
    "UK-only-Marken sind im Feed enthalten, aber aus der EU nicht regulaer bespielbar."
)


def spielbar(key) -> bool:
    """Kann man bei diesem Buch ein Konto haben? REIN/testbar."""
    return str(key or "").strip().lower() in SPIELBAR


def filtern(bookmakers) -> list:
    """Nur die spielbaren Buecher aus einer TheOddsAPI-bookmakers-Liste."""
    return [b for b in (bookmakers or []) if spielbar((b or {}).get("key"))]
