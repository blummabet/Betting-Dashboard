#!/usr/bin/env python3
"""
build_signal_bilanz.py — schreibt die woechentliche Signal-Bilanz.

06.09.2026 (Lucas: „wenn wir draufkommen, ein Signal ist zum Scheissen, dann wird es
runtergewichtet und nur mehr beobachtet"). Genau dafuer braucht es erst einmal eine Messung,
die BELEGT sagen kann, ob ein Signal schadet — der Lern-Loop kann das nicht: er vergibt
Gewichte, aber keine Konfidenz.

Liest den Signal-Ledger des aktiven Datensatzes, rechnet je Signal CLV und preis-justierten
Ausgang mit einseitiger 95%-Grenze und legt das Ergebnis als Artefakt ab. Urteilt nur, wo das
Intervall die Neutrale meidet — der Rest bleibt „kein Urteil".

Run:  python3 build_signal_bilanz.py        (COCOBET_DATASET steuert den Ledger)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

import cocobet_dataset as D                      # noqa: E402
import signal_bilanz as SB                       # noqa: E402
import signal_verlauf as SV                      # noqa: E402
from update_signal_weights import _preis_justierter_outcome  # noqa: E402

LEDGER = D.file("wm_signal_ledger.json", "liga_signal_ledger.json")
OUT = D.file("wm_signal_bilanz.json", "liga_signal_bilanz.json")
VERLAUF = D.file("wm_signal_verlauf.json", "liga_signal_verlauf.json")


def _records() -> list:
    if not LEDGER.exists():
        return []
    try:
        d = json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️  {LEDGER.name} nicht lesbar: {e}")
        return []
    return d.get("records") or [] if isinstance(d, dict) else (d or [])


def main() -> int:
    recs = _records()
    bil = SB.bilanz(recs, _preis_justierter_outcome)
    schlecht = SB.schaedliche(bil)
    gut = SB.tragende(bil)

    # Verlauf fortschreiben — ein Urteil wirkt erst, wenn es haelt (s. signal_verlauf).
    jetzt = datetime.now(timezone.utc).isoformat()
    alt_verlauf = {}
    if VERLAUF.exists():
        try:
            alt_verlauf = (json.loads(VERLAUF.read_text(encoding="utf-8")) or {}).get("signale") or {}
        except Exception as e:
            print(f"⚠️  {VERLAUF.name} nicht lesbar: {e}")
    verlauf = SV.fortschreiben(alt_verlauf, bil, jetzt)
    stabil = SV.stabile_urteile(verlauf)
    VERLAUF.write_text(json.dumps({
        "generatedAt": jetzt,
        "regel": ("Ein Urteil gilt als stabil nach %d Messungen an verschiedenen Tagen ueber "
                  "mindestens %.0f Tage, ohne Unterbrechung." % (SV.MIN_MESSUNGEN, SV.MIN_SPANNE_TAGE)),
        "stabil": stabil,
        "signale": verlauf,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT.write_text(json.dumps({
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "nRecords": len(recs),
        "minN": SB.MIN_N,
        "hinweis": ("Urteil nur, wenn das ganze einseitige 95%-Intervall die Neutrale meidet "
                    "(CLV gegen 0, Ausgang gegen 0,5 = 'genau wie bepreist'). "
                    "Ein Punktschaetzer ist kein Beleg."),
        "mehrfachtest": SB.MEHRFACHTEST_HINWEIS,
        "traegtBei": gut,
        "schadetBelegt": schlecht,
        "signale": bil,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== Signal-Bilanz ({LEDGER.name}, {len(recs)} Records) ===\n")
    print(f"{'Signal':24s} {'nCLV':>5s} {'Ø CLV':>8s} {'UG':>7s} {'OG':>7s}  {'Urteil':12s} "
          f"{'nAus':>5s} {'Ausgang':>8s}  Urteil")
    for name, v in sorted(bil.items(), key=lambda kv: -(kv[1]["nClv"] + kv[1]["nAusgang"])):
        f = lambda x, b="{:8.2f}": "       —" if x is None else b.format(x)
        print(f"{name:24s} {v['nClv']:5d} {f(v['clvPP'])} {f(v['clvUG'],'{:7.2f}')} "
              f"{f(v['clvOG'],'{:7.2f}')}  {v['clvUrteil']:12s} {v['nAusgang']:5d} "
              f"{f(v['ausgang'])}  {v['ausgangUrteil']}")
    print(f"\ntraegt belegt bei: {gut or '—'}")
    print(f"schadet belegt:    {schlecht or '—'}")
    print(f"\nSTABIL (wirkt auf die Gewichte):")
    print(f"  schadet:    {stabil.get('schadet') or '—'}")
    print(f"  traegt bei: {stabil.get('traegt bei') or '—'}")
    if stabil.get("widersprüchlich"):
        print(f"  widersprüchlich (wirkt nicht): {stabil['widersprüchlich']}")
    print(f"{VERLAUF.name} geschrieben.")
    print(f"\n{OUT.name} geschrieben.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
