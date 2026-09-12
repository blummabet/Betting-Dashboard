#!/usr/bin/env python3
"""push_deckel.py — wie viele Nachrichten ein Lauf hoechstens schickt.

## Warum es das gibt

12.09.2026 (Lucas: „Ich hab grad knapp 20 pushes in public bekommen — irgendwelche einzelner zu
Serien. Sowas gabs in der Form noch nie."). Ausloeser war ein Fix am Serien-Buch: bis dahin
hatte es NIE etwas abgerechnet, danach raeumte ein einziger Lauf den Rueckstau aus sechs Wochen
ab — und die Schleife schickte je abgerechneter Zeile eine Nachricht.

Die Fehlerklasse ist nicht „das Serien-Skript". Sie ist:

    Eine Schleife sendet je Element, und die Laenge der Liste haengt an einem Zustand, der sich
    sprunghaft aendern kann — ein erster erfolgreicher Lauf, ein nachgeholter Import, ein
    repariertes Feld, ein Tag mit ungewoehnlich vielen Spielen.

Dedup schuetzt dagegen NICHT. Dedup verhindert, dass dieselbe Sache zweimal kommt; ein Rueckstau
besteht aber aus lauter verschiedenen Sachen, die alle zum ersten Mal dran sind. Genau deshalb
war der Vorfall trotz intaktem Dedup moeglich.

## Was der Deckel tut — und was ausdruecklich nicht

Er begrenzt die Anzahl Nachrichten JE LAUF. Er entscheidet nicht, WELCHE wichtig sind: die
Reihenfolge kommt aus der Auswahl davor, der Deckel schneidet nur hinten ab. Was er abschneidet,
ist nicht verloren — es traegt keinen Dedup-Stempel und steht beim naechsten Lauf wieder an.
Ein Rueckstau flieszt damit ab, statt auf einmal zu kippen.

Und er ZAEHLT das Abgeschnittene. „wer pusht, misst den Push": ein stiller Deckel ist nur eine
andere Art, Information zu verlieren — man saehe nicht, dass ein Kanal dauerhaft an der Grenze
klebt.
"""
from __future__ import annotations


class Deckel:
    """Umschlag um einen Sender: laesst die ersten `max_n` durch, zaehlt den Rest.

        send = Deckel(tg_send, MAX_PUSH, "steam-lag")
        for x in kandidaten:
            if send(karte(x)):
                seen[x] = ...
        print(send.bericht())

    Gibt bei erreichtem Deckel `False` zurueck — also dasselbe wie ein fehlgeschlagener Send.
    Das ist Absicht: der Aufrufer setzt seinen Dedup-Stempel dann nicht, und der Kandidat kommt
    beim naechsten Lauf wieder. Ein Deckel, der `True` lieferte, wuerde Nachrichten still
    vernichten.
    """

    def __init__(self, sender, max_n: int, name: str = ""):
        if not callable(sender):
            raise TypeError("Deckel braucht einen Sender")
        m = int(max_n)
        if m < 1:
            raise ValueError("Ein Deckel unter 1 schaltet den Kanal ab — das ist eine "
                             "Konfigurationsentscheidung und keine Begrenzung")
        self._sender, self.max, self.name = sender, m, name
        self.gesendet = 0
        self.unterdrueckt = 0

    def __call__(self, text) -> bool:
        if self.gesendet >= self.max:
            self.unterdrueckt += 1
            return False
        ok = bool(self._sender(text))
        if ok:
            self.gesendet += 1
        return ok

    @property
    def voll(self) -> bool:
        return self.gesendet >= self.max

    def bericht(self) -> str:
        if not self.unterdrueckt:
            return f"📤 {self.name or 'Push'}: {self.gesendet}/{self.max} gesendet."
        return (f"📤 {self.name or 'Push'}: {self.gesendet}/{self.max} gesendet · "
                f"{self.unterdrueckt} durch den Deckel zurueckgehalten (kommen beim naechsten "
                f"Lauf wieder — pruefen, ob die Auswahl zu breit ist).")
