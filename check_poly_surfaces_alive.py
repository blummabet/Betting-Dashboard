#!/usr/bin/env python3
"""
check_poly_surfaces_alive.py — Guard gegen TOTE Poly-Flächen (20.07.2026, Lucas).

ANLASS (Audit 20.07.): Zwei „fertige" Poly-Features lieferten seit Bau NIE Daten und niemandem fiel
es auf — der Cross-Sport-Radar (fetch_poly_rows war ein Stub `return []`) und der E-Sport-Tab
(0 Commits). Exakt die Klasse, die uns beim CLV schon WOCHENLANG unbemerkt tot dalag: eine Fläche
ist verdrahtet, das Frontend liest brav — aber hinten kommt nie etwas an, und kein Guard sah hin.

## Semantik — und warum sie anders ist als „Datei existiert"

Der Wert steckt in der UNTERSCHEIDUNG:
  · frisch-aber-LEER  → GRÜN. Poly listet gerade nichts / ist geoblockt; der Produzent LIEF und hat
    ehrlich einen `emptyReason`/Leer-Stub geschrieben. Das ist ein legitimer Zustand, kein Fehler.
  · STEHT (nie erzeugt ODER lange nicht aktualisiert) → ROT. Der Produzent crasht/läuft nicht mehr.
    Genau das, was man wochenlang übersieht, wenn man nur prüft „ist es verdrahtet".

Deshalb prüft dieser Guard NICHT „hat die Datei Inhalt", sondern „hat der Produzent kürzlich
geschrieben" — Freshness des Zeitstempels. Ein leerer, aber frischer Stub ist gesund; ein voller,
aber tagealter Stand ist krank.

Nicht-blockierend: läuft in der Integritäts-Batterie (Status-Panel, severity=warn), NICHT als
Pre-Commit-Stopp — eine gestandene Tracking-Fläche darf den MLS-Daten-Commit nicht rot machen.
Reiner Kern (`evaluate`) ohne Disk/Netz testbar.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Fläche → (Datei, Zeitstempel-Feld). Global (vom MLS-Runner erzeugt), nicht datensatz-spezifisch.
# Feld mit '*'-Präfix = kein Top-Level-Stempel, sondern MAX über alle Einträge (dict of markets):
# so fängt der Guard Dateien, deren Nebenstand (generatedAt) frisch ist, deren eigentlicher
# CAPTURE aber steht. 25.07.2026 (Lucas): poly_money_broad_close fror seit 19.07. nichts ein,
# während poly_money_broad.json (generatedAt) jeden Lauf frisch schrieb → alter Guard sah GRÜN.
SURFACES = [
    ("Cross-Sport-Radar", "poly_cross_sport.json",       "generatedAt"),
    ("E-Sport",           "esports_poly_status.json",    "updatedAt"),
    ("Poly-Geld breit",   "poly_money_broad.json",       "generatedAt"),
    ("Poly-Geld Freeze",  "poly_money_broad_close.json", "*capturedAt"),
]

# manage-mls-poly läuft mind. 12:00 + 22:00–05:00 UTC → schlimmster Lücken-Abstand ~10–12h. 30h fängt
# erst „mehrere Läufe hintereinander ausgefallen" (= wirklich tot), nicht einen ausgelassenen Cron.
STALE_HOURS = 30.0


def _parse(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def evaluate(surfaces, now=None, stale_hours=STALE_HOURS) -> list:
    """REIN/testbar. surfaces: [{name, ts}] → Liste von Problemen (leer = alle Flächen leben).

    ts=None  → nie erzeugt (Produzent lief nie erfolgreich).
    ts alt   → Produzent steht seit >stale_hours."""
    now = now or datetime.now(timezone.utc)
    problems = []
    for s in surfaces:
        name, ts = s.get("name"), s.get("ts")
        if not ts:
            problems.append(f"{name}: nie erzeugt — Produzent lief nie erfolgreich durch")
            continue
        dt = _parse(ts)
        if dt is None:
            problems.append(f"{name}: Zeitstempel '{ts}' nicht parsebar")
            continue
        age_h = (now - dt).total_seconds() / 3600
        if age_h > stale_hours:
            problems.append(f"{name}: {age_h:.0f}h alt (>{stale_hours:.0f}h) — Produzent steht")
    return problems


def _newest_over_entries(d, field):
    """MAX-Zeitstempel über die Werte eines dict-of-markets (jeder Wert hat `field`)."""
    if not isinstance(d, dict):
        return None
    best = None
    for v in d.values():
        if not isinstance(v, dict):
            continue
        dt = _parse(v.get(field))
        if dt is not None and (best is None or dt > best):
            best = dt
    return best.isoformat() if best else None


def _load_ts(fname, field):
    try:
        d = json.loads((BASE / fname).read_text(encoding="utf-8"))
        if field.startswith("*"):          # '*capturedAt' → max über alle Einträge
            return _newest_over_entries(d, field[1:])
        return d.get(field) if isinstance(d, dict) else None
    except Exception:
        return None


def collect(surfaces=SURFACES) -> list:
    """Zeitstempel der realen Flächen-Dateien von Disk lesen → evaluate-Eingabe."""
    return [{"name": name, "ts": _load_ts(fname, field)} for name, fname, field in surfaces]


# 13.08.2026 (Lucas-Audit): Freshness allein sieht nicht, dass {ds}_poly_wallets.json zwar frisch ist,
# aber bigTradesAll dauerhaft leer bleibt (60 Positionen, 0 Trades) -> Flow-Tape/Ledger-Trades kommen nie
# an. Separater, nicht-blockierender Check auf genau dieses Muster.
WALLET_FILES = ["mls_poly_wallets.json", "liga_poly_wallets.json", "esports_poly_wallets.json", "wm_poly_wallets.json"]
MIN_POS_FOR_TRADES_WARN = 10


def check_wallet_trades(files=WALLET_FILES) -> list:
    """Positionen gefuellt, aber bigTradesAll leer = die Trade-/Nachkauf-Achse kommt nicht an
    (Producer schreibt sie nicht). Non-blocking. Liest Disk, sonst rein."""
    out = []
    for fn in files:
        try:
            d = json.loads((BASE / fn).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        npos = len(d.get("topPositionsAll") or [])
        ntr = len(d.get("bigTradesAll") or [])
        if npos >= MIN_POS_FOR_TRADES_WARN and ntr == 0:
            out.append("%s: %d Positionen, aber 0 grosse Trades - Flow-Tape/Ledger-Trades kommen nicht an (Producer pruefen)" % (fn, npos))
    return out


# 25.08.2026 (Audit-Befund 12): dieselbe Klasse eine Ebene tiefer. E-Sport schrieb 60 Positionen
# und 60 Trades - aber clustersAll war hartkodiert [] und einen matches-Schluessel gab es gar nicht.
# Der Conviction-Score fand fuer JEDEN E-Sport-Markt nichts (-> null) und die Exit-Warnung rendert
# nie. Frisch, gefuellt, und trotzdem tot: genau das sieht die Freshness-Pruefung nicht.
MIN_TRADES_FOR_CLUSTER_WARN = 10


def check_wallet_clusters(files=WALLET_FILES) -> list:
    """Trades da, aber clustersAll/matches leer = die Konsens-Achse kommt nicht an.
    Non-blocking. Liest Disk, sonst rein."""
    out = []
    for fn in files:
        try:
            d = json.loads((BASE / fn).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        npos = len(d.get("topPositionsAll") or [])
        ntr = len(d.get("bigTradesAll") or [])
        if ntr >= MIN_TRADES_FOR_CLUSTER_WARN and not (d.get("clustersAll") or []):
            out.append("%s: %d grosse Trades, aber 0 Konsens-Cluster - clustersAll kommt nicht an "
                       "(Conviction-Score bleibt fuer jeden Markt null)" % (fn, ntr))
        if npos >= MIN_POS_FOR_TRADES_WARN and not (d.get("matches") or {}):
            out.append("%s: %d Positionen, aber kein matches-Schluessel - der Tab kann keine "
                       "Markt-Sicht bauen (Exit-Warnung rendert nie)" % (fn, npos))
    return out


def main() -> int:
    problems = evaluate(collect()) + check_wallet_trades() + check_wallet_clusters()
    if not problems:
        print("✅ Alle Poly-Flächen leben (frisch geschrieben, auch wenn evtl. leer).")
        return 0
    print("⚠️  Gestandene Poly-Flächen (Produzent liefert nicht):")
    for p in problems:
        print("   ·", p)
    # Nicht-blockierend by design: der Aufrufer entscheidet (Panel: warn). Exit 0, Report zählt.
    return 0


if __name__ == "__main__":
    sys.exit(main())
