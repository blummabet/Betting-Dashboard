#!/usr/bin/env python3
"""
signal_verlauf.py — welches Urteil haelt, und seit wann?
========================================================
06.09.2026 (Lucas: „wenn wir draufkommen, ein Signal ist zum Scheissen, dann wird es
runtergewichtet und nur mehr beobachtet").

Genau das macht dieses Modul moeglich — mit einer Bremse, die ich fuer noetig halte.

## Warum nicht sofort abwerten

Die Bilanz prueft ~30 Signale gleichzeitig, jedes einseitig auf 95 %. Rein zufaellig sind damit
1-2 falsche Urteile pro Lauf zu erwarten. Wer daraufhin sofort abwertet, baut einen Loop, der
Rauschen hinterherlaeuft — dieselbe Krankheit wie der alte Loop, nur schneller.

Und die Bilanz hat sich am Tag ihrer Entstehung zweimal selbst korrigiert (fester Nullpunkt →
Gruppenvergleich → Schichtung nach Signalzahl). Ein Urteil aus EINEM Lauf ist eine Momentaufnahme
einer Rechnung, die selbst noch jung ist.

Deshalb: **ein Urteil wirkt erst, wenn es ueber mehrere Messungen an verschiedenen Tagen und
ueber ein Mindest-Zeitfenster gehalten hat.** Kippt es dazwischen auch nur einmal, faengt die
Zaehlung von vorn an. Das ist langsam — und langsam ist hier richtig: ein zu Unrecht
abgewertetes Signal kostet uns Information, und wir merken es nicht, weil es dann schweigt.

## Was hier NICHT passiert
Keine Gewichte. Dieses Modul sagt nur, welches Urteil belastbar ist; das Anwenden gehoert in
`update_signal_weights`.

REIN/testbar, kein I/O.
"""
from __future__ import annotations

from datetime import datetime, timezone

# So viele Messungen an VERSCHIEDENEN Tagen muessen dasselbe sagen.
MIN_MESSUNGEN = 3
# Und sie muessen mindestens so weit auseinanderliegen (Tage), damit nicht drei Laeufe
# desselben Wochenendes als „stabil" durchgehen.
MIN_SPANNE_TAGE = 14.0
# So viele Eintraege je Signal werden aufbewahrt.
MAX_VERLAUF = 40


def _tag(wert):
    if not wert:
        return None
    try:
        t = datetime.fromisoformat(str(wert).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    return t.date().isoformat()


def _zeit(tag):
    try:
        return datetime.fromisoformat(tag + "T00:00:00+00:00")
    except (TypeError, ValueError):
        return None


def fortschreiben(verlauf, bilanz, stand) -> dict:
    """Eine neue Messung anhaengen. -> neuer Verlauf {signal: [{tag, clv, ausgang}, ...]}.

    Pro Tag nur EIN Eintrag je Signal: laeuft die Pipeline mehrmals taeglich, zaehlt der
    letzte Stand des Tages. Sonst waeren drei Laeufe eines Nachmittags schon „drei Messungen".
    """
    tag = _tag(stand)
    if tag is None:
        return dict(verlauf or {})
    neu = {k: list(v) for k, v in (verlauf or {}).items() if isinstance(v, list)}
    for name, v in (bilanz or {}).items():
        if not isinstance(v, dict):
            continue
        eintrag = {"tag": tag,
                   "clv": v.get("clvUrteil") or "kein Urteil",
                   "ausgang": v.get("ausgangUrteil") or "kein Urteil"}
        reihe = [e for e in neu.get(name, []) if isinstance(e, dict) and e.get("tag") != tag]
        reihe.append(eintrag)
        reihe.sort(key=lambda e: e.get("tag") or "")
        neu[name] = reihe[-MAX_VERLAUF:]
    return neu


def stabil(reihe, urteil, min_messungen=MIN_MESSUNGEN, min_spanne=MIN_SPANNE_TAGE) -> bool:
    """Hat `urteil` in den letzten Messungen ununterbrochen gehalten — lang genug?

    Gezaehlt wird vom juengsten Eintrag rueckwaerts. Ein einziger abweichender Eintrag
    beendet die Serie: wir wollen ein Urteil, das haelt, nicht eines, das ueberwiegt.
    """
    r = [e for e in (reihe or []) if isinstance(e, dict) and e.get("tag")]
    if len(r) < min_messungen:
        return False
    r.sort(key=lambda e: e["tag"])
    serie = []
    for e in reversed(r):
        if e.get("clv") == urteil or e.get("ausgang") == urteil:
            serie.append(e)
        else:
            break
    if len(serie) < min_messungen:
        return False
    a, b = _zeit(serie[-1]["tag"]), _zeit(serie[0]["tag"])
    if a is None or b is None:
        return False
    return (b - a).total_seconds() / 86400.0 >= min_spanne


def stabile_urteile(verlauf, **kw) -> dict:
    """-> {"schadet": [...], "traegt bei": [...]} — nur was die Bremse passiert hat."""
    out = {"schadet": [], "traegt bei": []}
    for name, reihe in (verlauf or {}).items():
        for urteil in out:
            if stabil(reihe, urteil, **kw):
                out[urteil].append(name)
    for k in out:
        out[k] = sorted(out[k])
    # Ein Signal kann nicht beides sein. Passiert das doch (CLV sagt das eine, Ausgang das
    # andere, beide stabil), gilt KEINES — ein Widerspruch ist kein Urteil.
    beide = set(out["schadet"]) & set(out["traegt bei"])
    if beide:
        out["schadet"] = [n for n in out["schadet"] if n not in beide]
        out["traegt bei"] = [n for n in out["traegt bei"] if n not in beide]
        out["widersprüchlich"] = sorted(beide)
    return out
