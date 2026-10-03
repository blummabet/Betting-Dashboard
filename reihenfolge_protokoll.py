#!/usr/bin/env python3
"""
reihenfolge_protokoll.py — wer zeigt zuerst: Poly, Betfair oder Pinnacle? 03.10.2026.

Lucas: „wer war zuerst pini/betfair/poly … dickes Wallet … danach Betfair-Push". Die Idee: das
Geld, das ZUERST kommt, traegt die Information; wer danach kommt, folgt nur. Wenn das stimmt,
muesste ein Muster wie „poly>betfair" anders abschneiden als „betfair>poly".

🔴 Warum es ein eigenes Buch braucht. Die Money Map ist ein SCHNAPPSCHUSS: sie sagt, wo das Geld
JETZT liegt, nicht seit wann. Das Ledger der Money Map friert die Seite ein, aber nicht die
Reihenfolge. Die Frage „wer war zuerst" ist also mit keinem vorhandenen Buch beantwortbar — und
nachtraeglich auch nie mehr, weil die Zwischenstaende weg sind. Fehlerklasse: *eine Frage ueber
den Verlauf, gestellt an Daten, die nur den Endstand kennen.*

Je Lauf (nach betfair_consensus.py) und je Spiel VOR Anpfiff wird der erste Zeitpunkt jedes
Signals je Seite festgehalten:

    betfair   Geldseite der Boerse mit >= 65 % des Geldes
    poly      Geldseite auf Polymarket mit >= 65 %
    pinn      Pinnacle-Wahrscheinlichkeit der Seite >= 3 pp ueber dem ersten gesehenen Wert

Was beim ERSTEN Blick auf ein Spiel schon da ist, hat keine bekannte Reihenfolge — es steht mit
„=" im Muster („betfair=poly"), nicht in einer erfundenen Abfolge. Ab Anpfiff wird nichts mehr
ergaenzt (dieselbe Lehre wie die Money Map am 03.10.: Live-Zeilen machten aus −23 % ein +39 %).

Quote je Signal: Betfair-Quote, wenn die Boersen-Geldseite dieselbe Seite ist, sonst die faire
Pinnacle-Quote (1/p). Gewertet wird zur Quote des Signals, das das Muster komplett macht (bei
einem Signal: dessen Quote). Betfair minus 2 % Kommission.
Abrechnung ueber money_map_ledger.json (winner), sonst ft aus betfair_track_results.json.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
AUSGABE_FILE = "reihenfolge_protokoll.json"
QUELLEN = ("betfair", "poly", "pinn")
SEITEN = ("home", "draw", "away")
ANTEIL_MIN = 65
PINN_PP = 0.03
KOMMISSION = 0.02
VERFALL_TAGE = 4
Z = 1.645
UG_MIN_N = 30


def _laden(pfad, leer=None):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return leer


def _zeit(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _quote(row, seite):
    bf = row.get("betfair") or {}
    if bf.get("side") == seite and isinstance(bf.get("odd"), (int, float)) and bf["odd"] > 1:
        return float(bf["odd"]), "betfair"
    p = (row.get("pinn") or {}).get(seite)
    if isinstance(p, (int, float)) and p > 0:
        return round(1 / p, 3), "pinn"
    return None, None


# ── Erfassen ───────────────────────────────────────────────────────────────────────────────
def erfassen(spiele, rows, jetzt) -> dict:
    """Erste Signal-Zeitpunkte je (Spiel, Seite) fortschreiben. REIN (gibt neues dict zurueck)."""
    spiele = json.loads(json.dumps(spiele or {}))
    ts = jetzt.isoformat()
    for row in rows or []:
        if not isinstance(row, dict) or row.get("live"):
            continue
        ko = _zeit(row.get("kickoff"))
        mid = str(row.get("matchId") or "")
        if not mid or ko is None or jetzt >= ko:
            continue
        s = spiele.get(mid)
        neu = s is None
        if neu:
            s = spiele[mid] = {"home": row.get("home"), "away": row.get("away"),
                               "league": row.get("league"), "kickoff": row.get("kickoff"),
                               "ersterBlick": ts, "pinnStart": None, "seiten": {}}
        pinn = row.get("pinn") or {}
        if s.get("pinnStart") is None and all(isinstance(pinn.get(x), (int, float)) for x in SEITEN):
            s["pinnStart"] = {x: pinn[x] for x in SEITEN}
            s["pinnStartTs"] = ts
        an = []
        bf, po = row.get("betfair") or {}, row.get("poly") or {}
        if bf.get("side") in SEITEN and (bf.get("sharePct") or 0) >= ANTEIL_MIN:
            an.append((bf["side"], "betfair"))
        if po.get("side") in SEITEN and (po.get("sharePct") or 0) >= ANTEIL_MIN:
            an.append((po["side"], "poly"))
        if s.get("pinnStart"):
            for x in SEITEN:
                p, p0 = pinn.get(x), s["pinnStart"].get(x)
                if isinstance(p, (int, float)) and isinstance(p0, (int, float)) and p - p0 >= PINN_PP:
                    an.append((x, "pinn"))
        for seite, quelle in an:
            sig = s["seiten"].setdefault(seite, {})
            if quelle in sig:
                continue
            q, qq = _quote(row, seite)
            sig[quelle] = {"ts": ts, "ersterBlick": neu, "quote": q, "quoteAus": qq}
    return spiele


def muster(sig) -> str:
    """'poly>betfair', 'betfair=poly>pinn' … Gleicher Zeitpunkt = unbekannte Reihenfolge. REIN."""
    gruppen = {}
    for q, e in sig.items():
        gruppen.setdefault(e["ts"], []).append(q)
    return ">".join("=".join(sorted(gruppen[t])) for t in sorted(gruppen))


def erster(sig) -> str | None:
    """Quelle, die ALLEIN zuerst kam — None, wenn der erste Zeitpunkt geteilt ist. REIN."""
    if len(sig) < 2:
        return None
    t0 = min(e["ts"] for e in sig.values())
    zuerst = [q for q, e in sig.items() if e["ts"] == t0]
    return zuerst[0] if len(zuerst) == 1 else None


def wertungsquote(sig):
    """Quote des Signals, das das Muster komplett macht (das letzte). REIN."""
    letzte = max(sig.values(), key=lambda e: e["ts"])
    return letzte.get("quote"), letzte.get("quoteAus")


# ── Abrechnen ───────────────────────────────────────────────────────────────────────────────
def sieger_aus_ft(ft):
    if not (isinstance(ft, (list, tuple)) and len(ft) == 2):
        return None
    h, a = ft
    return "home" if h > a else "away" if a > h else "draw"


def abrechnen(spiele, settled, sieger, jetzt):
    """Spiele mit Ergebnis ins Buch, zu alte ohne Ergebnis als 'unaufgeloest'. REIN."""
    spiele = dict(spiele)
    settled = list(settled or [])
    for mid in list(spiele):
        s = spiele[mid]
        ko = _zeit(s.get("kickoff"))
        if ko is None or jetzt < ko:
            continue
        w = sieger.get(mid)
        if w is None and jetzt < ko + timedelta(days=VERFALL_TAGE):
            continue
        for seite, sig in (s.get("seiten") or {}).items():
            q, qq = wertungsquote(sig)
            e = {"matchId": mid, "seite": seite, "home": s.get("home"), "away": s.get("away"),
                 "league": s.get("league"), "kickoff": s.get("kickoff"),
                 "muster": muster(sig), "erster": erster(sig), "nSignale": len(sig),
                 "quote": q, "quoteAus": qq}
            if w is None:
                e["result"] = "unaufgeloest"
            else:
                e["result"] = "win" if w == seite else "loss"
                if q:
                    e["r"] = round((q - 1) * (1 - KOMMISSION if qq == "betfair" else 1), 4) \
                        if e["result"] == "win" else -1.0
            settled.append(e)
        del spiele[mid]
    return spiele, settled


# ── Bericht ─────────────────────────────────────────────────────────────────────────────────
def kennzahlen(werte):
    n = len(werte)
    if not n:
        return {"n": 0, "roi": None, "ug": None}
    m = sum(werte) / n
    ug = None
    if n >= UG_MIN_N:
        ug = round((m - Z * math.sqrt(sum((w - m) ** 2 for w in werte) / (n - 1) / n)) * 100, 1)
    return {"n": n, "roi": round(m * 100, 1), "ug": ug}


def bericht(settled):
    gewertet = [e for e in settled if isinstance(e.get("r"), (int, float))]
    je_muster, je_erster, je_anzahl = {}, {}, {}
    for e in gewertet:
        je_muster.setdefault(e["muster"], []).append(e["r"])
        je_anzahl.setdefault(str(e["nSignale"]), []).append(e["r"])
        if e.get("erster"):
            je_erster.setdefault(e["erster"], []).append(e["r"])
    sortiert = lambda d: dict(sorted(((k, kennzahlen(v)) for k, v in d.items()),
                                     key=lambda kv: -kv[1]["n"]))
    return {"n": len(settled), "gewertet": len(gewertet),
            "unaufgeloest": sum(1 for e in settled if e.get("result") == "unaufgeloest"),
            "zweiPlusMitErstem": sum(1 for e in gewertet if e.get("erster")),
            "jeMuster": sortiert(je_muster), "jeErster": sortiert(je_erster),
            "jeAnzahlSignale": sortiert(je_anzahl)}


def sieger_laden(base_dir) -> dict:
    sieger = {}
    try:
        import betfair_track_store
        for z in betfair_track_store.load(os.path.join(base_dir, "betfair_track_results.json")):
            w = sieger_aus_ft(z.get("ft")) if isinstance(z, dict) else None
            if w:
                sieger[str(z.get("matchId"))] = w
    except Exception as ex:  # noqa: BLE001 — Abrechnung faellt auf das Ledger zurueck
        print(f"[reihenfolge] Track nicht lesbar: {ex}")
    for e in _laden(os.path.join(base_dir, "money_map_ledger.json"), []) or []:
        if isinstance(e, dict) and e.get("winner") in SEITEN:
            sieger[str(e.get("matchId"))] = e["winner"]
    return sieger


def main(base_dir=BASE, jetzt=None) -> int:
    jetzt = jetzt or datetime.now(timezone.utc)
    stand = _laden(os.path.join(base_dir, AUSGABE_FILE), {}) or {}
    rows = (_laden(os.path.join(base_dir, "money_map.json"), {}) or {}).get("rows") or []
    spiele = erfassen(stand.get("spiele") or {}, rows, jetzt)
    spiele, settled = abrechnen(spiele, stand.get("settled") or [], sieger_laden(base_dir), jetzt)
    aus = {"updatedAt": jetzt.isoformat(), "start": stand.get("start") or jetzt.isoformat(),
           "regel": {"anteilMin": ANTEIL_MIN, "pinnPP": PINN_PP, "kommission": KOMMISSION},
           "bericht": bericht(settled), "spiele": spiele, "settled": settled}
    from pathlib import Path
    from safe_write import write_json_atomic
    write_json_atomic(Path(base_dir) / AUSGABE_FILE, aus, indent=None)
    b = aus["bericht"]
    print(f"[reihenfolge] offen={len(spiele)} abgerechnet={b['n']} gewertet={b['gewertet']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
