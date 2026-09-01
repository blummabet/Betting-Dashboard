#!/usr/bin/env python3
"""scripts/calib_walkforward.py — trägt die Conviction-Kalibrierung out of sample?

01.09.2026, Lucas: „schau dir das mal an, ob der Lerneffekt dort eh greift."

Der Kalibrierer (`_pwCalibConv` in poly-wallets.js) misst je Signal-MIX den realen ROI des
Papier-Depots und verschiebt die Conviction dorthin. Ob das hilft, kann man NICHT daran ablesen,
dass die Eimer unterschiedliche Renditen zeigen — das tun zufällige Eimer auch. Die einzige
ehrliche Prüfung ist: hätte die Anpassung, mit dem Wissen von DAMALS getroffen, die Plays von
DANACH besser sortiert?

Deshalb Walk-Forward: für jeden Play werden die Eimer ausschließlich aus den Plays davor gebaut.
Kein Blick nach vorn, kein In-Sample-Effekt.

Ergebnis am 01.09.2026 (500 Plays, 14.08.–01.09.): **sechs von sechs Startpunkten NEIN** — die
abgestuften Plays schlugen jedes Mal die hochgestuften. Daraufhin wurde `PW_CALIB_AKTIV=false`
gesetzt: der Lerner beobachtet, bewegt aber keine Conviction mehr.

⭐ Vor jedem Wiedereinschalten dieses Skript laufen lassen. „Die Eimer sehen plausibel aus" ist
kein Beleg; „hoch schlägt runter über mehrere Startpunkte" ist einer.

    python3 scripts/calib_walkforward.py [--min-n 8] [--z 1.645]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TRACK = BASE / "poly_shortlist_track.json"
# Muss mit _PW_CALIB_CORE in poly-wallets.js übereinstimmen — sonst misst das Skript andere Eimer,
# als der Lerner benutzt, und das Ergebnis wäre wertlos.
CORE = {"money", "sharp", "steam", "pinn", "gvp", "bf"}


def lade():
    st = json.loads(TRACK.read_text(encoding="utf-8")).get("settled") or []
    st = list(st.values()) if isinstance(st, dict) else list(st)
    st = [x for x in st if isinstance(x, dict) and x.get("settledTs")]
    st.sort(key=lambda x: str(x.get("settledTs")))
    return st


def mix(x) -> str:
    return "+".join(sorted(t for t in (x.get("signals") or []) if t in CORE)) or "(none)"


def rendite(x):
    """Rendite EINES Plays, auf den Einsatz normiert. None, wenn kein Einsatz vermerkt ist."""
    s = float(x.get("stake") or 0)
    return (float(x.get("pnl") or 0) / s) if s > 0 else None


def untergrenze(v, z=1.645):
    n = len(v)
    if n < 2:
        return None
    m = sum(v) / n
    var = sum((a - m) ** 2 for a in v) / (n - 1)
    return m - z * (var ** 0.5) / (n ** 0.5)


def anpassung(hist, play, min_n, richter, z):
    """Die Anpassung, die der Lerner mit dem Wissen von DAMALS berechnet hätte."""
    eimer = {}
    for x in hist:
        eimer.setdefault(mix(x), []).append(x)
    alle = [r for r in (rendite(x) for x in hist) if r is not None]
    basis = sum(alle) / len(alle) if alle else 0.0
    rows = eimer.get(mix(play))
    if not rows or len(rows) < min_n:
        return 0.0
    rr = [r for r in (rendite(x) for x in rows) if r is not None]
    if len(rr) < 2:
        return 0.0
    schaetzer = (sum(rr) / len(rr)) if richter == "punkt" else untergrenze(rr, z)
    if schaetzer is None:
        return 0.0
    conf = len(rows) / (len(rows) + 25)
    return max(-3.0, min(2.0, (schaetzer - basis) * 15 * conf))


def lauf(st, start, min_n, richter, z):
    g = {"hoch": [], "runter": [], "gleich": []}
    for i in range(start, len(st)):
        a = anpassung(st[:i], st[i], min_n, richter, z)
        v = rendite(st[i])
        if v is None:
            continue
        g["hoch" if round(a) > 0 else "runter" if round(a) < 0 else "gleich"].append(v)
    return g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-n", type=int, default=8, help="Mindest-Stichprobe je Eimer (Code: 8)")
    ap.add_argument("--z", type=float, default=1.645)
    args = ap.parse_args()

    st = lade()
    if len(st) < 120:
        print(f"Zu wenig abgerechnete Plays ({len(st)}) — der Test braucht Vergangenheit.")
        return 0
    print(f"{len(st)} abgerechnete Plays · {st[0]['settledTs'][:10]} → {st[-1]['settledTs'][:10]}")
    print(f"Eimer = Signal-Mix aus {sorted(CORE)} · Mindest-n {args.min_n}\n")

    mittel = lambda v: (sum(v) / len(v) * 100) if v else None
    for richter, label in (("punkt", "roher ROI (wie im Code)"), ("ug", "mit Untergrenze")):
        print(f"── Richter: {label} " + "─" * (44 - len(label)))
        print(f'{"ab Play":>8} | {"↑ hochgestuft":>18} | {"↓ abgestuft":>18} | trägt?')
        treffer = gesamt = 0
        for start in (100, 150, 200, 250, 300):
            if start >= len(st) - 10:
                continue
            g = lauf(st, start, args.min_n, richter, args.z)
            h, r = mittel(g["hoch"]), mittel(g["runter"])
            if h is None or r is None:
                print(f"{start:>8} | {'zu wenig':>18} | {'zu wenig':>18} |")
                continue
            gesamt += 1
            ok = h > r
            treffer += 1 if ok else 0
            print(f"{start:>8} | {h:+8.1f}% (n{len(g['hoch']):3d}) | "
                  f"{r:+8.1f}% (n{len(g['runter']):3d}) | {'JA' if ok else 'NEIN'}")
        print(f'  → „hoch schlägt runter": {treffer}/{gesamt}\n')

    print("Lesart: erst wenn EIN Richter über die MEISTEN Startpunkte trägt, darf")
    print("PW_CALIB_AKTIV in poly-wallets.js wieder auf true. Ein einzelner guter")
    print("Schnitt genügt nicht — er war am 01.09. bereits irreführend positiv.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
