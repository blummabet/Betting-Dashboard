#!/usr/bin/env python3
"""scripts/json_kompakt.py — Einrueckung aus den grossen Uebersichts-Artefakten nehmen.

🔴 22.09.2026 (Lucas: „Was ist da jetzt mit diesen 12 Megabyte, liga-data.json — was kann man
da machen, oder wo fuehrt das zu Problemen?").

Gemessen wurden drei Kosten, die vorher als eine gezaehlt wurden:
  · ueber die Leitung gehen 1,2 MB (gzip) — das Netz ist NICHT das Problem
  · zu parsen und im Speicher: 12,7 MB — DAS ist es, und zwar am Handy
  · davon sind **3,85 MB reine Einrueckung**

    liga-data.json       5,12 → 3,02 MB   (−2,10)
    mls-data.json        1,92 → 1,15 MB   (−0,78)
    liga_streaks.json    0,80 → 0,53 MB   (−0,26)
    betfair_prices.json  1,12 → 0,62 MB   (−0,51)

## Warum hier und nicht am Schreiber
liga-data.json wird von **mindestens fuenfzehn** Stellen geschrieben (generate_wm_picks,
build_liga_data, pick_staking, fetch_liga_elo, fetch_liga_xg, fetch_liga_odds,
fetch_liga_topscorers, fetch_liga_team_changes, fetch_liga_match_stats …), fast alle mit
`indent=2`. Die einzeln umzustellen waere genau die Fehlerklasse, die in diesem Repo staendig
zuschlaegt: *eine Regel an vielen Stellen, repariert an einer.* Und die vergessene Stelle waere
hier besonders teuer — die Datei spraenge bei jedem Lauf zwischen zwei Formaten hin und her.

Deshalb EIN Schritt kurz vor `git add`, idempotent: er liest, prueft dass es gueltiges JSON ist,
und schreibt es ohne Leerraum zurueck. Wer die Datei danach wieder eingerueckt schreibt,
aendert nichts am Ergebnis — der naechste Lauf normalisiert erneut.

## Was er NICHT tut
Er sortiert keine Schluessel und aendert keinen Wert. `ensure_ascii=False` bleibt, sonst
blaehen Umlaute die Datei wieder auf. Faellt eine Datei nicht als JSON auf, bleibt sie
unveraendert liegen und der Schritt meldet das — ein Normalisierer, der bei Zweifel schreibt,
waere ein Datenverlust-Werkzeug.

Aufruf:  python3 scripts/json_kompakt.py liga-data.json mls-data.json …
Faellt NIE hart aus: der aufrufende Lauf soll weiterlaufen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def kompakt(pfad) -> tuple[int, int] | None:
    """Schreibt die Datei ohne Leerraum zurueck. Gibt (vorher, nachher) in Bytes zurueck,
    oder None, wenn nichts zu tun war oder die Datei kein gueltiges JSON ist. REIN genug zum
    Testen: nur diese eine Datei wird angefasst."""
    p = Path(pfad)
    if not p.exists():
        return None
    roh = p.read_bytes()
    try:
        daten = json.loads(roh.decode("utf-8"))
    except Exception:
        return None
    neu = json.dumps(daten, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(neu) >= len(roh):
        return None                      # schon kompakt (oder kuerzer geht nicht) — nicht anfassen
    # Erst schreiben, wenn der neue Inhalt nachweislich dasselbe ergibt. Ein Normalisierer, der
    # den Inhalt aendert, ist schlimmer als einer, der nichts tut.
    if json.loads(neu.decode("utf-8")) != daten:
        return None
    tmp = p.with_suffix(p.suffix + ".kompakt.tmp")
    tmp.write_bytes(neu)
    tmp.replace(p)
    return len(roh), len(neu)


def main(argv=None) -> int:
    namen = list(argv if argv is not None else sys.argv[1:])
    if not namen:
        print("json_kompakt: keine Datei genannt — nichts zu tun.")
        return 0
    gespart = 0
    for n in namen:
        r = kompakt(n)
        if r is None:
            continue
        vor, nach = r
        gespart += vor - nach
        print("   %-32s %6.2f → %6.2f MB" % (n, vor / 1e6, nach / 1e6))
    if gespart:
        print("🪶 json_kompakt: %.2f MB Einrueckung entfernt." % (gespart / 1e6))
    else:
        print("ℹ️  json_kompakt: nichts zu kuerzen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
