#!/usr/bin/env python3
"""
verlauf_nachtragen.py — den Wallet-Verlauf aus der Git-Historie nachtragen (21.09.2026).

🔴 Anlass: Lucas, 01:04 UTC — „Das kam. Aber auf poly wurde nicht gesetzt." Zwei Zeilen im
Shortlist-Buch waren mit je -5,00 $ abgerechnet, ohne dass sich das Wallet je bewegt hat.
`wallet_abgleich.entbuchen` nimmt solche Zeilen jetzt aus der Bilanz — aber nur, wenn der
Wallet-Verlauf ihren Zeitpunkt ABDECKT. `*_poly_verlauf.json` gibt es erst seit heute
Nachmittag; die beiden Zeilen sind von heute Nacht. Der Beweis, der sie entlastet, waere also
da und liegt doch ausserhalb der Reichweite.

Er liegt in der Git-Historie: `*_poly_balance.json` wird alle ~15 Minuten geschrieben und
committet, seit Monaten. Dieses Skript liest diese Staende zurueck und traegt sie in den
Verlauf nach. Keine einzige API-Abfrage, keine erfundene Zahl — jeder Punkt stand so im Repo.

Fehlerklasse, gegen die es gebaut ist: **eine Gegenprobe, deren Beweismittel juenger ist als
das, was sie beweisen soll.**

Laeuft NICHT im Takt: ein Nachtrag ist ein einmaliger Vorgang. Der Workflow
`verlauf-nachtragen.yml` startet es von Hand und braucht dafuer `fetch-depth: 0` — die
Minuten-Workflows holen bewusst nur den letzten Commit.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Welcher Stand gehoert in welchen Verlauf. Dieselben Paare wie in `fetch_wm_poly_balance.py`.
PAARE = (("wm_poly_balance.json", "wm_poly_verlauf.json"),
         ("liga_poly_balance.json", "liga_poly_verlauf.json"),
         ("mls_poly_balance.json", "mls_poly_verlauf.json"))

MAX_COMMITS = 4000
VERLAUF_KEEP = 3000          # dieselbe Kappung wie beim Produzenten


def punkt(stand) -> dict | None:
    """Ein Balance-Stand als Verlaufs-Punkt. REIN. None = unbrauchbar.

    Ein Stand ohne `updatedAt` ist wertlos: der Abgleich sucht Bewegungen in der ZEIT. Und ein
    Stand ohne `usdc` erst recht — das ist die Groesse, die ein Kauf bewegt.
    """
    if not isinstance(stand, dict):
        return None
    ts, usdc = stand.get("updatedAt"), stand.get("usdc")
    if not ts or not isinstance(usdc, (int, float)):
        return None
    return {"ts": ts, "usdc": usdc, "positions": stand.get("positions"),
            "total": stand.get("total")}


def zusammenfuehren(alt, neu, keep: int = VERLAUF_KEEP) -> list:
    """Bestehender Verlauf + nachgetragene Punkte -> eine Reihe. REIN.

    Der bestehende Verlauf gewinnt bei gleichem Zeitstempel: er kommt vom Produzenten selbst,
    der Nachtrag ist die Rekonstruktion. Unveraenderte Staende werden zusammengefasst — der
    Abgleich sucht BEWEGUNGEN, und tausend identische Zeilen machen die Suche nur langsam.

    🔴 Beim ersten Anlauf behielt die Zusammenfassung den LETZTEN Stand einer Ruhephase. Damit
    wanderte der Kauf, der die Phase eroeffnete, an ihr Ende: ein Abgang um 01:15 stand nach
    drei Stunden Stille als 04:39 in der Reihe, und `entbuchen` erklaerte die dazugehoerige
    Wette fuer unbelegt — der Nachtrag haette also genau das Gegenteil dessen bewiesen, wofuer
    es ihn gibt. Derselbe Fehler steckte im Produzenten (`verlauf_anhaengen`).
    Fehlerklasse: eine Reihe, die festhaelt, wann zuletzt geschaut wurde, statt wann sich etwas
    geaendert hat.

    Behalten wird deshalb der ERSTE Stand einer Phase; `bisTs` sagt, bis wann er galt.
    """
    nach_ts = {}
    for p in (neu or []):
        if isinstance(p, dict) and p.get("ts"):
            nach_ts.setdefault(str(p["ts"]), p)
    for p in (alt or []):                      # der Produzent ueberschreibt den Nachtrag
        if isinstance(p, dict) and p.get("ts"):
            nach_ts[str(p["ts"])] = dict(p)
    reihe = sorted(nach_ts.values(), key=lambda x: str(x.get("ts")))
    raus = []
    for p in reihe:
        if raus and raus[-1].get("usdc") == p.get("usdc"):
            raus[-1]["bisTs"] = p.get("bisTs") or p.get("ts")
            raus[-1]["positions"], raus[-1]["total"] = p.get("positions"), p.get("total")
            continue
        raus.append(dict(p))
    return raus[-keep:]


# ── ab hier I/O ──────────────────────────────────────────────────────────────────────────
def _git(*args) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=str(BASE), capture_output=True,
                           text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def staende_aus_historie(datei: str, max_commits: int = MAX_COMMITS) -> list:
    """Alle je committeten Staende dieser Datei als Verlaufs-Punkte."""
    shas = [s for s in _git("log", "--format=%H", "-n", str(max_commits), "--", datei).split()
            if s]
    raus = []
    for sha in shas:
        roh = _git("show", "%s:%s" % (sha, datei))
        if not roh:
            continue
        try:
            p = punkt(json.loads(roh))
        except (ValueError, TypeError):
            continue
        if p:
            raus.append(p)
    return raus


def main(argv=None) -> int:
    print("=== verlauf_nachtragen.py ===")
    if not _git("rev-parse", "--is-inside-work-tree").strip():
        print("  🛑 kein Git-Baum — ohne Historie gibt es nichts nachzutragen.")
        return 0
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        # Ein flacher Checkout sieht genau einen Commit. Still „0 nachgetragen" zu melden waere
        # eine Meldung, die einen anderen Grund nennt als den, der zutrifft.
        print("  🛑 flacher Checkout (fetch-depth: 1) — die Historie fehlt, nichts nachgetragen. "
              "Dieser Lauf braucht `fetch-depth: 0`.")
        return 1
    gesamt = 0
    for stand_datei, verlauf_datei in PAARE:
        if not (BASE / stand_datei).exists():
            continue
        alt = []
        p = BASE / verlauf_datei
        if p.exists():
            try:
                v = json.loads(p.read_text(encoding="utf-8"))
                alt = v if isinstance(v, list) else []
            except (ValueError, OSError):
                alt = []
        nach = staende_aus_historie(stand_datei)
        neu = zusammenfuehren(alt, nach)
        dazu = len(neu) - len(alt)
        print("  · %s: %d Stand(e) aus der Historie, Verlauf %d → %d (%+d)"
              % (stand_datei, len(nach), len(alt), len(neu), dazu))
        if neu != alt:
            p.write_text(json.dumps(neu, ensure_ascii=False), encoding="utf-8")
            gesamt += max(dazu, 0)
    print("  → %d Punkt(e) nachgetragen." % gesamt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
