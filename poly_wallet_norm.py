#!/usr/bin/env python3
"""
poly_wallet_norm.py — was ist fuer DIESES Konto ein normaler Einsatz?
=====================================================================
05.09.2026 (Lucas, zur Karte „🐋 Großer Whale-Einstieg · $250,9K auf Leverkusen"):
„250.000 ist fuer mich ein Vermoegen, fuer den wahrscheinlich ein normaler Bet. Man muesste
halt schauen, wie hoch der Einsatz im Vergleich zu seinen anderen ist."

Genau. Die Schwelle war absolut: `usd >= 50.000` — ein fester Dollar-Betrag gegen alle Wallets
der Welt. Ein Konto, das immer 400.000 setzt, loest damit **jedes Mal** aus; eines, das sonst
20.000 setzt und ploetzlich 80.000 schiebt, faellt durch. Gemeldet wird also, wer gross ist,
nicht wer etwas Ungewoehnliches tut.

Dieselbe Bauform wie `stake_seltenheit.py` einen Tag vorher: eine absolute Groesse gegen einen
globalen Boden statt gegen die eigene Verteilung. Dort war es `max/median` je Liga, hier der
Dollar-Betrag je Wallet. Beide Male sortiert die Zahl nach etwas anderem als dem, was
draufsteht.

## Die Wallet aus der Meldung, gemessen
    n=6 Positionen · Median-Ticket $263.803 · p90 $441.788 · groesste $523.731
    Die gemeldeten $250.900 sind das **0,95-fache** ihres Median-Tickets.
Es war ihre Normalgroesse. Die Karte nannte es „Großer Einstieg".

## Warum das SOFORT geht und nicht erst in Wochen
Ein Ergebnis muss man abwarten, eine Einsatzhoehe nicht: sie steht in dem Moment fest, in dem
wir die Position sehen. `poly_money_broad_close.json` haelt bereits **8.509 Wal-Positionen ueber
1.469 Wallets** — 193 davon mit >= 8 Positionen, 37 mit >= 40. Die Norm laesst sich also aus dem
bestehenden Bestand erzeugen, nicht erst aufsammeln. Und getroffen sind genau die Vielsetzer,
also die, die den Feed zumuellen.

Der Track Record bleibt davon unberuehrt: er braucht weiter Abrechnungen und weiter n>=30.
Das hier ist die andere Frage — nicht „ist das Konto gut?", sondern „ist das fuer dieses Konto
viel?".

## Drei Zustaende, und keiner rendert als harmlose Zahl
    n >= TAIL_MIN_N (40)  ->  Seltenheitsurteil ueber stake_seltenheit (zufallPct)
    n >= MIN_N (8)        ->  Vielfaches des eigenen Median-Tickets. BESCHREIBUNG, kein Urteil:
                              ein Median aus 8 Werten ist grob, und ein Maximum-Vielfaches
                              waechst mit n (der Befund vom 04.09.).
    darunter              ->  gar nichts. „Erste Positionen dieses Kontos" ist etwas anderes
                              als „normal fuer dieses Konto".

## Env
  POLY_WNORM_MIN_N       ab wie vielen Positionen es ein Vielfaches gibt (Default 8)
  POLY_WNORM_MAX         wie viele Positionen je Wallet behalten werden (Default 400)
  POLY_WNORM_ALTER_TAGE  wie alt eine Position werden darf (Default 120)
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from stake_seltenheit import schwanz

CLOSE_FILE = BASE / "poly_money_broad_close.json"
LIVE_FILE = BASE / "poly_live_signal_track.json"
STATE_FILE = BASE / "poly_wallet_norm_state.json"
OUT_FILE = BASE / "poly_wallet_norm.json"

MIN_N = int(os.environ.get("POLY_WNORM_MIN_N") or 8)
JE_WALLET_MAX = int(os.environ.get("POLY_WNORM_MAX") or 400)
ALTER_MAX_TAGE = int(os.environ.get("POLY_WNORM_ALTER_TAGE") or 120)

_DATUM = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _lade(pfad, standard):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return standard


def _schreibe(pfad, daten):
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, separators=(",", ":"))


def _ts_aus_key(key, fallback_ms):
    """Der Markt-Key traegt das Anpfiff-Datum („fl1-hac-asm-2026-08-23"). Ohne Datum gilt der
    Fallback — NICHT „heute", denn das wuerde alte Positionen ewig frisch halten."""
    m = _DATUM.search(str(key or ""))
    if not m:
        return fallback_ms
    try:
        d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
    except ValueError:
        return fallback_ms
    return d.timestamp() * 1000.0


def positionen_sammeln(close: dict, live: dict, fallback_ms: float) -> list:
    """Alle Wal-Positionen aus den vorhandenen Artefakten. -> [(wallet, ts_ms, usd, posKey)]

    Dedupliziert wird spaeter ueber posKey = key|wallet: dieselbe Position taucht in beiden
    Dateien auf und darf die Norm nicht zweimal beschweren."""
    out = []
    for key, v in (close or {}).items():
        if not isinstance(v, dict):
            continue
        ts = _ts_aus_key(key, fallback_ms)
        for w in (v.get("whales") or []):
            wal, usd = w.get("wallet"), w.get("usd")
            if wal and isinstance(usd, (int, float)) and usd > 0:
                out.append((str(wal).lower(), ts, float(usd), "%s|%s" % (key, str(wal).lower())))
    for e in ((live or {}).get("ledger") or []):
        wal, usd, key = e.get("wallet"), e.get("usd"), e.get("key")
        if wal and isinstance(usd, (int, float)) and usd > 0:
            out.append((str(wal).lower(), _ts_aus_key(key, fallback_ms), float(usd),
                        "%s|%s" % (key, str(wal).lower())))
    return out


def nachtragen(state: dict, positionen: list, jetzt: datetime = None) -> dict:
    """Neue Positionen in den Stand einarbeiten. Dedupliziert ueber posKey."""
    jetzt = jetzt or datetime.now(timezone.utc)
    proben = {k: list(v) for k, v in (state.get("samples") or {}).items()}
    zugang = 0
    for wal, ts, usd, pkey in positionen:
        reihe = proben.setdefault(wal, [])
        if any(p[2] == pkey for p in reihe):
            continue
        reihe.append([ts, round(usd, 2), pkey])
        zugang += 1
    grenze = (jetzt - timedelta(days=ALTER_MAX_TAGE)).timestamp() * 1000.0
    for wal in list(proben):
        reihe = [p for p in proben[wal] if p[0] and p[0] >= grenze]
        reihe.sort(key=lambda p: p[0])
        if len(reihe) > JE_WALLET_MAX:
            reihe = reihe[-JE_WALLET_MAX:]
        if reihe:
            proben[wal] = reihe
        else:
            del proben[wal]
    return {"generatedAt": jetzt.isoformat().replace("+00:00", "Z"),
            "zugangLetzterLauf": zugang, "samples": proben}


def norm_bauen(state: dict) -> dict:
    """Je Wallet die Kennzahlen. Unter MIN_N: nur die Zaehlung, keine Zahl."""
    out = {}
    for wal, reihe in (state.get("samples") or {}).items():
        betraege = sorted(p[1] for p in reihe)
        n = len(betraege)
        e = {"n": n}
        if n < MIN_N:
            e.update({"basis": "zu duenn", "median": None, "p90": None, "max": None,
                      "schwanz": None})
        else:
            e.update({
                "basis": "gelernt",
                "median": round(statistics.median(betraege), 2),
                "p90": round(betraege[min(n - 1, int(round(0.9 * (n - 1))))], 2),
                "max": round(betraege[-1], 2),
                "schwanz": schwanz(betraege),     # None unter 40 — kein Ersatzwert
            })
        out[wal] = e
    return out


def ticket_vergleich(usd, eintrag: dict) -> dict | None:
    """Wie gross ist dieser Einsatz FUER DIESES KONTO?

    -> {"faktor", "median", "n", "basis"}  oder None, wenn nichts bekannt ist.
       basis "gelernt" = Vielfaches des eigenen Median-Tickets (Beschreibung).
       None            = wir wissen ueber dieses Konto zu wenig. Das ist NICHT „normal".
    """
    # bool ist in Python ein int — ohne diese Klammer waere `True` ein gueltiger Einsatz
    # und ergaebe „0,01x das uebliche Ticket". Dieselbe Falle wie in stake_seltenheit.py.
    if not isinstance(usd, (int, float)) or isinstance(usd, bool) or usd <= 0:
        return None
    if not eintrag or eintrag.get("basis") != "gelernt" or not eintrag.get("median"):
        return None
    return {"faktor": round(usd / eintrag["median"], 2), "median": eintrag["median"],
            "n": eintrag["n"], "basis": "gelernt"}


def main() -> int:
    print("=== poly_wallet_norm.py ===")
    jetzt = datetime.now(timezone.utc)
    pos = positionen_sammeln(_lade(CLOSE_FILE, {}), _lade(LIVE_FILE, {}),
                             jetzt.timestamp() * 1000.0)
    if not pos:
        print("  ℹ️  keine Positionen gefunden — nichts nachzutragen (kein Wipe).")
        return 0
    state = nachtragen(_lade(STATE_FILE, {}), pos, jetzt)
    _schreibe(STATE_FILE, state)
    norm = norm_bauen(state)
    _schreibe(OUT_FILE, {"generatedAt": state["generatedAt"], "minN": MIN_N,
                         "jeWalletMax": JE_WALLET_MAX, "alterMaxTage": ALTER_MAX_TAGE,
                         "wallets": norm})
    gelernt = [k for k, v in norm.items() if v["basis"] == "gelernt"]
    mit_schwanz = [k for k in gelernt if norm[k].get("schwanz")]
    print("  %d neue Positionen · %d Wallets im Stand · %d mit Norm (ab n=%d) · %d mit Schwanz"
          % (state["zugangLetzterLauf"], len(norm), len(gelernt), MIN_N, len(mit_schwanz)))
    for k in sorted(gelernt, key=lambda k: -norm[k]["n"])[:6]:
        v = norm[k]
        print("   %s… n=%-4d Median $%-10s p90 $%-10s max $%s"
              % (k[:10], v["n"], f'{v["median"]:,.0f}', f'{v["p90"]:,.0f}', f'{v["max"]:,.0f}'))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
