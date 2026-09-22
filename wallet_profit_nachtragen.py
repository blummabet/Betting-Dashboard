#!/usr/bin/env python3
"""
wallet_profit_nachtragen.py — den Wallet-Profit aus der Git-Historie nachtragen (22.09.2026).

🔴 Lucas, zweimal am selben Tag: „Mir ist wirklich wichtig, dass wir den Profit und den ROI der
letzten sieben und 30 Tage mit tracken … Lifetime ist nett, sagt aber wenig aus, vor allem bei
alten Wallets."

Seit heute rechnet `poly_money_broad` je abgerechneter Wallet-Position Gewinn und Einsatz mit.
Nur: eine Wallet bekommt ihre erste Geld-Zeile erst, wenn eine ihrer Positionen NACH heute
auflöst. Eine 30-Tage-Bilanz wäre damit erst Ende Oktober vollständig — und bis dahin stünde
genau die Zahl, auf die es ankommt, leer daneben.

Sie muss aber nicht leer stehen. `poly_wallet_track.json` wird bei jedem Scan committet und
trägt in `open` je Position Wallet, Einstieg, Größe und Preis. Verschwindet eine Position, ist
sie abgerechnet; der Ausgang steht in `poly_resolutions.json`. Gemessen über 35 Tage:

    1.561 Commits  ->  33.258 verschiedene Positionen
    davon geschlossen 32.480, mit eindeutiger Auflösung **15.085**

Fünfzehntausend abgerechnete Positionen, die die ganze Zeit im Repo standen.
Fehlerklasse: **eine Messung, die bei null anfängt, obwohl ihre Vergangenheit erfasst ist.**

Zwei Dinge halten die Rekonstruktion ehrlich:

  · Sie schreibt in ein EIGENES Feld (`tageNachtrag`), nie in das des laufenden Betriebs. Was
    rekonstruiert ist, bleibt als rekonstruiert erkennbar — `zeitraum_bilanz` weist es getrennt
    aus. Ein Weg, den niemand nachzählen kann, ist keiner.
  · Sie hört beim heutigen Tag auf. Der laufende Betrieb schreibt ab heute; alles davor kann er
    nicht mehr nachholen. Damit kann sich nichts doppeln, und zwar per Bauart und nicht per
    Sorgfalt.

Mehrdeutige Bündel-Auflösungen werden wie überall abgelehnt (`aufloesbar`) — 1.889 Positionen
fallen so heraus, statt einen geratenen Ausgang zu bekommen.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from poly_money_broad import geld_aus_position
from poly_slug_urteil import aufloesbar

BASE = Path(__file__).resolve().parent
TRACK = BASE / "poly_wallet_track.json"
RES = BASE / "poly_resolutions.json"

TAGE_ZURUECK = int(__import__("os").environ.get("WALLET_NACHTRAG_TAGE") or 45)


def tag_von(res_eintrag) -> str | None:
    """Der Tag, an dem der Markt aufloeste. REIN. None = unbrauchbar."""
    ts = (res_eintrag or {}).get("ts")
    t = str(ts or "")[:10]
    return t if len(t) == 10 and t[4] == "-" else None


def nachtrag_tage(positionen, resolutions, offen_jetzt, bis_tag) -> dict:
    """{wallet: {tag: [nGeld, gewinn, einsatz]}} aus geschlossenen Positionen. REIN.

    `bis_tag` ist ausschliessend: der laufende Betrieb schreibt ab diesem Tag selbst, und was
    beide schrieben, stuende doppelt in der Bilanz.
    """
    raus: dict = {}
    for schluessel, e in (positionen or {}).items():
        if not isinstance(e, dict) or schluessel in (offen_jetzt or ()):
            continue
        r = (resolutions or {}).get(e.get("key")) or {}
        sieger = r.get("winner")
        if not sieger or not aufloesbar(e.get("key"), e.get("side"), sieger, cond=e.get("cond")):
            continue
        tag = tag_von(r)
        if not tag or tag >= str(bis_tag):
            continue
        gewinn, einsatz = geld_aus_position(e.get("usd"), e.get("lastPrice"),
                                            e.get("entryPrice") or e.get("firstPrice"),
                                            e.get("side") == sieger)
        if gewinn is None:
            continue
        w = str(e.get("wallet") or "").lower()
        if not w:
            continue
        b = raus.setdefault(w, {}).setdefault(tag, [0, 0.0, 0.0])
        b[0] += 1
        b[1] = round(b[1] + gewinn, 2)
        b[2] = round(b[2] + einsatz, 2)
    return raus


def einpflegen(track, nachtrag) -> int:
    """Traegt den Nachtrag in die scores ein. Ersetzt `tageNachtrag` ganz -> idempotent. -> Wallets."""
    scores = (track or {}).get("scores")
    if not isinstance(scores, dict):
        return 0
    n = 0
    for w, tage in (nachtrag or {}).items():
        s = scores.get(w)
        if not isinstance(s, dict):
            continue
        s["tageNachtrag"] = {k: list(v) for k, v in sorted(tage.items())}
        n += 1
    return n


# ── ab hier I/O ──────────────────────────────────────────────────────────────────────────
def _git(*args) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=str(BASE), capture_output=True,
                           text=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def positionen_aus_historie(tage_zurueck: int = TAGE_ZURUECK) -> dict:
    """Jede je gesehene offene Position, im ZULETZT gesehenen Zustand."""
    shas = [x for x in _git("log", "--format=%H", "--since=%d days ago" % tage_zurueck,
                            "--", TRACK.name).split() if x]
    letzt: dict = {}
    for sha in reversed(shas):          # aelteste zuerst -> der letzte Stand gewinnt
        roh = _git("show", "%s:%s" % (sha, TRACK.name))
        if not roh:
            continue
        try:
            d = json.loads(roh)
        except ValueError:
            continue
        for k, v in (d.get("open") or {}).items():
            if isinstance(v, dict):
                letzt[k] = v
    print("  · %d Commits gelesen, %d verschiedene Positionen" % (len(shas), len(letzt)))
    return letzt


def main(argv=None) -> int:
    print("=== wallet_profit_nachtragen.py ===")
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        print("  🛑 flacher Checkout — die Historie fehlt. Dieser Lauf braucht `fetch-depth: 0`.")
        return 1
    if not TRACK.exists() or not RES.exists():
        print("  🛑 poly_wallet_track.json oder poly_resolutions.json fehlt.")
        return 1
    track = json.loads(TRACK.read_text(encoding="utf-8"))
    res = json.loads(RES.read_text(encoding="utf-8"))
    heute = datetime.now(timezone.utc).date().isoformat()
    pos = positionen_aus_historie()
    nach = nachtrag_tage(pos, res, set(track.get("open") or {}), heute)
    n = einpflegen(track, nach)
    gew = sum(v[1] for t in nach.values() for v in t.values())
    zeilen = sum(v[0] for t in nach.values() for v in t.values())
    print("  · %d abgerechnete Position(en) rekonstruiert, %d Wallet(s), Summe %+.0f $"
          % (zeilen, n, gew))
    TRACK.write_text(json.dumps(track, ensure_ascii=False), encoding="utf-8")
    print("  → %s" % TRACK.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
