#!/usr/bin/env python3
"""
runner_state.py — Zwischenstaende, die nur der Mac-Runner braucht, liegen NICHT im Repo.
=========================================================================================
🔴 06.10.2026 (Lucas: „wieso funktioniert der mist nicht mehr, bricht immer an dieser Stelle").
Betfair-Lauf 14:46 UTC: Beleg lokal committet, dann `git fetch` → „curl 28 Operation too slow",
Push abgelehnt, Wiederholung, wieder Frist. Dieselbe Stelle am 30.09., 01.10. und 03.10. —
dreimal wurde an der FRIST gedreht, nie an der MENGE.

Gemessen: jeder Poly-Global-Scan schreibt alle 30 Min ~47 MB Blobs neu ins Repo. Jeder andere
Lauf auf dem Mac muss das vor seinem Push abholen, mit 150 s Frist; ein abgebrochener fetch wirft
den halben Pack weg, die naechste Runde faengt bei null an. Je mehr Daten, desto oefter reisst es.
Zwei der vier groessten Posten fetcht KEINE Seite und liest KEIN anderer Workflow:
  · poly_wallet_norm_state.json  ~9 MB  (nur poly_wallet_norm.py)
  · poly_price_path.json         ~8 MB  (poly_price_path.py, poly_shortlist_track.py)
Beide laufen ausschliesslich im Global-Scan auf dem self-hosted Mac (concurrency: poly-global-scan,
also nie zwei gleichzeitig). Sie liegen jetzt in ~/.cocobet_state — derselbe Ort wie der
Beleg-Spiegel, den beide Mac-Runner teilen und den actions/checkout nicht anfasst.

Fehlerklasse: Arbeitsspeicher eines Jobs, der als Repo-Inhalt versioniert wird — jede Aenderung
kostet jeden anderen Job Leitung.

Uebergang: die alte Repo-Fassung bleibt eingefroren im Checkout liegen und dient genau einmal als
Startwert, falls der Runner-Stand fehlt (neuer Runner, geloeschtes Verzeichnis). Danach gewinnt
immer der Runner-Stand.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def state_dir() -> Path:
    d = os.environ.get("COCOBET_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".cocobet_state")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return Path(d)


def pfad(name: str) -> Path:
    return state_dir() / name


def lesen(name: str, repo_base, standard=None):
    """Runner-Stand; fehlt er, die eingefrorene Repo-Fassung als Startwert; sonst `standard`."""
    for p in (pfad(name), Path(repo_base) / name):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {} if standard is None else standard


def schreiben(name: str, daten) -> Path:
    """Atomar und kompakt in den Runner-Stand. Nie ins Repo."""
    ziel = pfad(name)
    fd, tmp = tempfile.mkstemp(dir=str(ziel.parent), prefix="." + name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, ziel)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return ziel
