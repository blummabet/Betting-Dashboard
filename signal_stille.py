#!/usr/bin/env python3
"""
signal_stille.py — welches Signal schweigt, und seit wann?
==========================================================
06.09.2026.

Der Anlass war `polymarket_sharp`: das Signal las das Poly-Volumen unter `poly_vol`, die
Produktion schreibt es unter `vol`. Der Default war 0, das Gate lag bei 5.000 USD — also
**nie gefeuert, in keinem einzigen von 318 abgerechneten Picks**, waehrend in unserer eigenen
Datei Everton–Manchester United mit 7,87 Mio. USD stand. Dasselbe bei `steam_lag`.

Auffallen konnte das nicht. Ein Signal, das nichts liefert, sieht von aussen genauso aus wie
ein Signal, fuer das es gerade nichts zu sagen gibt. **Stille ist kein Fehlerzustand, den
irgendwer meldet** — sie ist die Abwesenheit von Meldungen.

Dieses Modul macht die Stille sichtbar. Es urteilt bewusst NICHT darueber, ob ein Signal zu
Recht schweigt — `altitude_signal` hat in den Top-5-Ligen nichts zu suchen, `mls_travel` in
der Liga auch nicht. Es sagt nur: *dieses Signal hat in n Picks kein einziges Mal gefeuert*,
und ueberlaesst die Deutung dem Menschen. Eine Liste, die man einmal pro Woche ansieht, haette
den Fehler in der ersten Woche gefunden statt nach Monaten.

REIN/testbar, kein I/O.
"""
from __future__ import annotations

# Unter so vielen Records sagt Stille nichts — dann hat einfach noch nichts stattgefunden.
MIN_RECORDS = 60


def feuerungen(records) -> dict:
    """{Signalname: Anzahl Feuerungen} ueber die uebergebenen Ledger-Records."""
    out: dict[str, int] = {}
    for r in (records or []):
        if not isinstance(r, dict):
            continue
        for s in (r.get("signals") or []):
            if not isinstance(s, dict):
                continue
            name = s.get("name")
            if not name:
                continue
            w = s.get("score")
            if isinstance(w, bool) or not isinstance(w, (int, float)) or w == 0:
                continue
            out[name] = out.get(name, 0) + 1
    return out


def stumme(records, registrierte, min_records: int = MIN_RECORDS) -> list | None:
    """Registrierte Signale, die in diesen Records NIE gefeuert haben.

    -> sortierte Liste von Namen, oder None, wenn zu wenige Records fuer eine Aussage
       vorliegen. Kein Urteil ist etwas anderes als ein gemessenes „alle sprechen".
    """
    recs = [r for r in (records or []) if isinstance(r, dict)]
    if len(recs) < min_records:
        return None
    f = feuerungen(recs)
    return sorted(n for n in (registrierte or []) if not f.get(n))


def abgeschaltet_und_stumm(stumme_liste, abgeschaltete) -> dict:
    """Trennt die Stille in ihre zwei Ursachen.

    06.09.2026: `liga_default` hatte NEUN Signale in `disabled_signals` — darunter
    `smart_money` und `polymarket_sharp`, die beide zusaetzlich **defekt** waren (falscher
    Feldname, falscher Lookup-Schluessel). Die zwei Zustaende verstaerken sich: ein
    abgeschaltetes Signal kann nicht zeigen, dass es kaputt ist, und ein kaputtes Signal sieht
    aus wie eines, das nichts zu sagen hat — also schaltet man es ab.

    -> {"abgeschaltet": [...], "stumm_trotz_an": [...]}
    Die zweite Liste ist die interessante: an, mit Zustaendigkeit, und trotzdem kein Wort.
    """
    st = list(stumme_liste or [])
    ab = set(abgeschaltete or [])
    return {"abgeschaltet": sorted(n for n in st if n in ab),
            "stumm_trotz_an": sorted(n for n in st if n not in ab)}


def befunde(stumme_liste, records) -> list:
    """Eine Zeile je stummem Signal. Leere Liste = nichts zu melden."""
    if not stumme_liste:
        return []
    n = len([r for r in (records or []) if isinstance(r, dict)])
    return ["%s: 0 Feuerungen in %d abgerechneten Picks — entweder ohne Zustaendigkeit "
            "in diesem Datensatz oder stumm defekt (wie polymarket_sharp bis 06.09.)" % (s, n)
            for s in stumme_liste]
