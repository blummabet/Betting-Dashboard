#!/usr/bin/env python3
"""
scripts/pages_ballast.py — welche Wurzel-JSONs braucht die statische Seite NICHT?
(02.09.2026, Lucas: „was nun mit diesem MB Größen Problem")

Der Pages-Deploy hat diese Krankheit dreimal gehabt: 01.07. (TikTok-PNGs, Uploads 10–18 Min,
„Deployment cancelled"), 28.08. („auf der Seite ist nichts" — zwei neue TikTok-Varianten, die die
NAMENSLISTE im Workflow nicht kannte), und am 02.09. stand das Artefakt bei 169,3 von 170 MB.
Beim ersten Mal half eine Namensliste, beim zweiten Mal war genau sie das Problem: eine Liste
veraltet still.

Deshalb hier eine REGEL statt einer Liste. Ein Wurzel-JSON fliegt aus dem Deploy, wenn keine
ausgelieferte HTML/JS-Datei seinen Namen erwaehnt. Alles andere bleibt — im Zweifel bleibt es.

Warum das sicher ist: die Live-Seite holt ihre Daten seit jeher PRIMAER von
raw.githubusercontent.com/main (main-dashboard.js, betfair-radar.js, poly-wallets.js,
status-checks.js, polymarket-tab.js — jeweils `raw` zuerst, Pages-Kopie nur als Rueckfall). Fuer
eine Datei, die keine Zeile Frontend-Code je anfasst, gibt es auch keinen Rueckfall.

Die eine echte Gefahr sind DYNAMISCH gebaute Dateinamen (`ds + '_poly_prices.json'`). Dagegen
zwei Sicherungen:
  1. Es wird nicht nur der volle Name gesucht, sondern auch jedes Namens-Endstueck ab einem
     Unterstrich — `mls_poly_prices.json` bleibt also auch, wenn im Code nur `_poly_prices.json`
     oder `poly_prices.json` steht.
  2. tests/test_pages_artifact_size.py faehrt dieselbe Regel und prueft gegen, dass nichts
     Geloeschtes irgendwo referenziert ist. Faellt jemandem spaeter ein, eine dieser Dateien doch
     zu fetchen, faellt der Test — nicht die Live-Seite.

Aufruf im Workflow (nur im ephemeren Runner-Checkout, das Repo bleibt unberuehrt):
    python3 scripts/pages_ballast.py --loeschen
Ohne Flag wird nur aufgelistet.
"""
from __future__ import annotations
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tracked(repo=REPO):
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, cwd=repo).stdout
    return [f.decode("utf-8", "replace") for f in out.split(b"\0") if f]


def _frontend_text(dateien, repo=REPO):
    """Alles, was ausgeliefert wird und Dateinamen enthalten koennte. Tests zaehlen NICHT —
    ein Testfixture ist kein Grund, eine Datei auszuliefern."""
    teile = []
    for f in dateien:
        if not f.endswith((".js", ".html", ".css")) or f.startswith("tests/"):
            continue
        try:
            with open(os.path.join(repo, f), encoding="utf-8", errors="replace") as fh:
                teile.append(fh.read())
        except OSError:
            pass
    return "\n".join(teile)


def _namensvarianten(name):
    """`mls_poly_prices.json` → der volle Name plus jedes Endstueck ab einem Unterstrich.
    Faengt dynamisch zusammengesetzte Namen (`ds + '_poly_prices.json'`)."""
    varianten = {name}
    rest = name
    while "_" in rest:
        rest = rest.split("_", 1)[1]
        varianten.add(rest)
        varianten.add("_" + rest)
    return varianten


def unbenutzte_wurzel_jsons(dateien=None, repo=REPO):
    """Die Wurzel-JSONs, die keine ausgelieferte HTML/JS/CSS-Datei erwaehnt. REIN/testbar."""
    dateien = dateien if dateien is not None else tracked(repo)
    text = _frontend_text(dateien, repo)
    raus = []
    for f in dateien:
        if "/" in f or not f.endswith(".json"):
            continue
        if any(v in text for v in _namensvarianten(f)):
            continue
        raus.append(f)
    return sorted(raus)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    loeschen = "--loeschen" in argv
    raus = unbenutzte_wurzel_jsons()
    mb = 0.0
    for f in raus:
        try:
            mb += os.path.getsize(os.path.join(REPO, f)) / 1e6
        except OSError:
            pass
    print(f"Ballast: {len(raus)} Wurzel-JSON(s) ohne Frontend-Referenz, {mb:.1f} MB")
    for f in sorted(raus, key=lambda x: -os.path.getsize(os.path.join(REPO, x))
                    if os.path.exists(os.path.join(REPO, x)) else 0)[:10]:
        try:
            print(f"   {os.path.getsize(os.path.join(REPO, f))/1e6:6.1f} MB  {f}")
        except OSError:
            pass
    if not loeschen:
        print("(nur aufgelistet — mit --loeschen wirklich entfernen)")
        return 0
    for f in raus:
        try:
            os.remove(os.path.join(REPO, f))
        except OSError as e:
            print(f"   ⚠️ {f}: {e}")
    print(f"🧹 {len(raus)} Datei(en) aus dem Deploy-Artefakt entfernt ({mb:.1f} MB).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
