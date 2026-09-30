"""Soll der Betfair-Lauf den Live-Scan anstossen? Exit 0 = ja, 1 = nein.

🔴 30.09.2026 (Lucas: „jetzt schon mehrmals am Tag … irgendwas wurde da verschlimmbessert").
Stimmt. Seit dem 29.09. stiess JEDER Betfair-Lauf (alle 15 Min) einen Live-Scan an: Live-Scan-
Commits 6-10/Tag vorher, 51 am 29.09., 103 am 30.09. Alles auf demselben Mac-Runner — Betfair
brauchte zeitweise 800+ s statt ~100 s, Pull und Scan hingen bis zum 12-Min-Deckel, vier
Abbrueche an einem Vormittag. Der Fix vom 29.09. hat das eine Problem (Scan lief ~5x am Tag)
gegen das Gegenteil getauscht.
Fehlerklasse: ein Ausloeser ohne Mengenbremse. Jetzt nur, wenn der letzte Live-Scan laenger als
ABSTAND_MIN zurueckliegt — groesste Luecke damit ~40 + 15 Min + Laufzeit, sicher unter dem Alarm
`live_scan_laeuft` (90 Min), und hoechstens ~30 Laeufe am Tag statt ~100.
"""
import json
import os
import sys
from datetime import datetime, timezone

ABSTAND_MIN = float(os.environ.get("LIVE_SCAN_ABSTAND_MIN") or 40)
HEALTH = "health/poly-live-scan.json"


def alter_min(health, now=None):
    """Minuten seit dem letzten Live-Scan-Lauf, None = unbekannt. REIN."""
    now = now or datetime.now(timezone.utc)
    runs = (health or {}).get("runs") if isinstance(health, dict) else None
    if not runs:
        return None
    # 🔴 30.09.2026: hier stand `runs[-1]` — die Liste steht aber NEUESTE ZUERST. Gelesen wurde
    # also der aelteste Lauf, der immer > 40 Min alt ist: die Drossel griff nie, der Live-Scan
    # tickte nach dem Push weiter alle 15 Min. Der juengste Zeitstempel, egal in welcher
    # Reihenfolge die Liste steht.
    zeiten = []
    for r in runs:
        try:
            t = datetime.fromisoformat(str((r or {}).get("ts") or (r or {}).get("startedAt")).replace("Z", "+00:00"))
        except (TypeError, ValueError, AttributeError):
            continue
        zeiten.append(t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t)
    if not zeiten:
        return None
    return (now - max(zeiten)).total_seconds() / 60.0


def faellig(health, now=None, abstand_min=ABSTAND_MIN) -> bool:
    """Unbekannt heisst anstossen — ein fehlender Stempel darf den Scan nicht stilllegen."""
    a = alter_min(health, now)
    return a is None or a >= abstand_min


if __name__ == "__main__":
    try:
        h = json.load(open(HEALTH, encoding="utf-8"))
    except (OSError, ValueError):
        h = None
    a = alter_min(h)
    ja = faellig(h)
    print("Letzter Live-Scan vor %s Min — %s" % ("?" if a is None else "%.0f" % a,
          "anstossen" if ja else "kein Anstoss (unter %.0f Min)" % ABSTAND_MIN))
    sys.exit(0 if ja else 1)
