#!/usr/bin/env python3
"""
scripts/archiv_aufraeumen.py — Wachstumsbremse für die beiden Archive im Repo
(02.09.2026, Lucas: „Haben diese Tik Tok irgendwie die wir generieren auch da ein Speicher
Problem / Und die Event Seiten, kann man die vergangenen die älter wie eine Woche sind löschen?")

Gemessen am 02.09.2026:

  · TikTok-Karten: 145 MB im Arbeitsbaum, alle in git. `daily-tiktok` (83 MB) ist seit dem
    20.07. tot — sechs Wochen keine neue Datei. `mls_daily-tiktok` (39 MB) und
    `liga_daily-tiktok` (23 MB) laufen und wachsen um ~2,2 MB/Tag. Es gab NIRGENDS eine
    Aufraeum-Logik. Niemand liest alte Karten: generate_daily_tiktok prueft beim Dedup nur
    Dateien von HEUTE (`OUTPUT_DIR.glob(f"{today_iso}_*.png")`).
  · Match-Daten: `matches/data` hielt 1.373 JSONs mit 65 MB. Die eigentlichen Event-SEITEN
    sind dagegen nur 2,9 MB (120 Stueck) — sie zu loeschen brächte nichts und kostet genau
    das, was langfristig zaehlt.

Was hier geloescht wird, ist deshalb NICHT „alles Alte", sondern nur, was nachweislich
niemand mehr anfasst:

  TikTok  → Karten aelter als KARTEN_TAGE. Nichts liest sie, der Dedup schaut nur auf heute.
  Matches → eine `matches/data/<slug>.json` NUR, wenn alle drei zutreffen:
              (a) kein `matches/<slug>.html` existiert  → keine Event-Seite braucht sie,
              (b) kein `matches/*index*.json` nennt den Slug → das Dashboard laedt sie nicht,
              (c) das Datum im Slug liegt ueber DATEN_TAGE zurueck.
            Bedingung (c) ist die Sicherung gegen einen Generator-Aussetzer: faellt ein Index
            einmal leer aus, verschwinden nicht sofort die frischen Daten.

⚠️ Was das NICHT tut: `.git` schrumpfen. Die Historie (1,3 GB) behaelt jede je committete
Datei; dagegen hilft nur ein History-Rewrite, und der ist eine eigene Entscheidung. Was diese
Regel leistet: der Arbeitsbaum, jeder frische Klon-Checkout und das Deploy-Artefakt hoeren auf
zu wachsen.

Aufruf:
    python3 scripts/archiv_aufraeumen.py              # nur zeigen
    python3 scripts/archiv_aufraeumen.py --loeschen   # wirklich
"""
from __future__ import annotations
import argparse
import json
import os
import re
from datetime import date, datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KARTEN_ORDNER = ("daily-tiktok", "mls_daily-tiktok", "liga_daily-tiktok")
KARTEN_TAGE = 14      # so viel Rueckschau reicht fuer „was haben wir letzte Woche gepostet"
DATEN_TAGE = 7        # Lucas: „die vergangenen die aelter wie eine Woche sind"

_DATUM = re.compile(r"(20\d\d)-?(\d\d)-?(\d\d)")


def _datum_aus_name(name):
    """Datum aus dem Dateinamen. None, wenn keins drinsteht — und ohne Datum wird NICHT
    geloescht: ein unlesbarer Name ist kein Beleg fuer Alter."""
    m = _DATUM.search(name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def alte_karten(heute=None, repo=REPO, tage=KARTEN_TAGE):
    """Karten-Dateien, die aelter als `tage` sind. REIN/testbar."""
    heute = heute or datetime.now(timezone.utc).date()
    raus = []
    for ordner in KARTEN_ORDNER:
        pfad = os.path.join(repo, ordner)
        if not os.path.isdir(pfad):
            continue
        for f in sorted(os.listdir(pfad)):
            d = _datum_aus_name(f)
            if d is not None and (heute - d).days > tage:
                raus.append(os.path.join(ordner, f))
    return raus


def _index_slugs(repo=REPO):
    """Alle Slugs, die irgendein matches/*index*.json nennt."""
    ordner = os.path.join(repo, "matches")
    slugs = set()
    if not os.path.isdir(ordner):
        return slugs
    for f in os.listdir(ordner):
        if not (f.endswith(".json") and "index" in f):
            continue
        try:
            with open(os.path.join(ordner, f), encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            # Ein unlesbarer Index heisst NICHT „nichts referenziert". Dann lieber gar nichts
            # loeschen, als anhand einer halben Liste zu entscheiden.
            raise
        for s in (d.get("slugs") or []):
            slugs.add(str(s))
    return slugs


def verwaiste_matchdaten(heute=None, repo=REPO, tage=DATEN_TAGE):
    """matches/data-JSONs ohne Seite, ohne Index-Eintrag und aelter als `tage`. REIN/testbar."""
    heute = heute or datetime.now(timezone.utc).date()
    ordner = os.path.join(repo, "matches")
    daten = os.path.join(ordner, "data")
    if not os.path.isdir(daten):
        return []
    seiten = {f[:-5] for f in os.listdir(ordner) if f.endswith(".html")}
    idx = _index_slugs(repo)
    raus = []
    for f in sorted(os.listdir(daten)):
        if not f.endswith(".json"):
            continue
        slug = f[:-5]
        if slug in seiten or slug in idx:
            continue
        d = _datum_aus_name(slug)
        if d is None or (heute - d).days <= tage:
            continue
        raus.append(os.path.join("matches", "data", f))
    return raus


def _mb(pfade, repo=REPO):
    t = 0
    for p in pfade:
        try:
            t += os.path.getsize(os.path.join(repo, p))
        except OSError:
            pass
    return t / 1e6


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--loeschen", action="store_true")
    ap.add_argument("--karten-tage", type=int, default=KARTEN_TAGE)
    ap.add_argument("--daten-tage", type=int, default=DATEN_TAGE)
    a = ap.parse_args(argv)

    karten = alte_karten(tage=a.karten_tage)
    daten = verwaiste_matchdaten(tage=a.daten_tage)
    # VOR dem Loeschen messen — danach gibt getsize() nur noch Fehler.
    mb_karten, mb_daten = _mb(karten), _mb(daten)
    print(f"🎬 TikTok-Karten aelter als {a.karten_tage} Tage: {len(karten)} Dateien, {mb_karten:.1f} MB")
    print(f"📄 verwaiste Match-Daten aelter als {a.daten_tage} Tage: {len(daten)} Dateien, {mb_daten:.1f} MB")
    if not a.loeschen:
        print("(nur gezeigt — mit --loeschen wirklich entfernen)")
        return 0
    n = 0
    for p in karten + daten:
        try:
            os.remove(os.path.join(REPO, p))
            n += 1
        except OSError as e:
            print(f"   ⚠️ {p}: {e}")
    print(f"🧹 {n} Datei(en) entfernt, {mb_karten + mb_daten:.1f} MB frei.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
