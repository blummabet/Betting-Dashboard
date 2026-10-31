"""Soll der Betfair-Lauf den Aufstellungs-Lauf (liga-aufstellungen.yml) anstossen? Exit 0 = ja, 1 = nein.

31.10.2026 (Lucas: „bau das mit Aufstellung so um, dass es klappt").
Der eigene Zeitplan von liga-aufstellungen.yml ('5,25,45 9-21') hat am ersten Tag in 80 Minuten
KEIN EINZIGES Mal gefeuert — GitHubs Scheduler drosselt dieses Repo (der dichte Odds-Lauf mit
'17 */2' kommt ~4x am Tag statt 12x). Der Betfair-Lauf dagegen kommt verlässlich alle 15 Min
(per workflow_dispatch). Also stösst ER den Aufstellungs-Lauf an — dasselbe Muster wie beim
Live-Scan (scripts/live_scan_faellig.py), inkl. Mengenbremse: nur wenn ein Top-5-Spiel in
FENSTER_MIN anpfeift. Ein Spiel liegt damit 3–4 Betfair-Läufe lang im Fenster, und genau dort
(T-60 bis T-10) erscheinen die Aufstellungen bei API-Football. Der Cron bleibt als Rückfall.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

TOP5 = ("ENG", "ESP", "GER", "ITA", "FRA")
VON_MIN = float(os.environ.get("AUFSTELLUNG_VON_MIN") or 5)    # bis 5 Min vor Anpfiff
BIS_MIN = float(os.environ.get("AUFSTELLUNG_BIS_MIN") or 75)   # ab 75 Min vor Anpfiff


def faellige(data, now=None, von=VON_MIN, bis=BIS_MIN):
    """Top-5-Spiele, deren Anpfiff in [now+von, now+bis] liegt. REIN."""
    now = now or datetime.now(timezone.utc)
    lo, hi = now + timedelta(minutes=von), now + timedelta(minutes=bis)
    raus = []
    for g, gd in ((data or {}).get("groups") or {}).items():
        if g not in TOP5:
            continue
        for fx in (gd or {}).get("fixtures") or []:
            try:
                ko = datetime.fromisoformat(str(fx.get("kickoff")).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            ko = ko if ko.tzinfo else ko.replace(tzinfo=timezone.utc)
            if lo <= ko <= hi:
                raus.append(f"{g} {fx.get('home')}-{fx.get('away')} {ko:%H:%M}Z")
    return raus


def main(pfad="liga-data.json"):
    try:
        with open(pfad, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"Aufstellung: {pfad} nicht lesbar ({exc}) — kein Anstoss")
        return 1
    f = faellige(data)
    print(f"Aufstellung: {len(f)} Top-5-Spiel(e) im Fenster T-{BIS_MIN:.0f}..T-{VON_MIN:.0f} Min" + (": " + ", ".join(f) if f else ""))
    return 0 if f else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
