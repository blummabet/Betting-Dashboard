#!/usr/bin/env python3
"""
poly_public_eval.py — Auswertung der ÖFFENTLICHEN Polymarket-Whale-Pushs
(02.09.2026, Lucas: „Schaffst du irgendwie die Polymarket pushes auch auszuwerten die in diesen
Channel kommen?").

Gegenstück zu betfair_public_eval.py. poly_whale_watch.py legt jeden gesendeten Public-Push als
`pending` in poly_whale_public_ledger.json ab (mit dem Preis, den ein LESER im Moment des Pushs
bekommen hätte). Hier wird gegen den Slug-Sieger aus poly_resolutions.json abgerechnet:
Trefferquote mit einseitiger 95%-Untergrenze, ROI zu $10 Einsatz je Push, CLV gegen den
eingefrorenen Schlusskurs — dieselben Kennzahlen wie im Direkt-Bet-Depot, damit die Zahlen
vergleichbar bleiben.

Zwei Ehrlichkeitsregeln, die hier bewusst hart verdrahtet sind:

  · Ein Push ohne Auflösung wird nach PENDING_TTL_D Tagen `unaufloesbar` — er verschwindet NICHT
    still, sondern steht im Report als eigener Zähler. Fehlende Information ist keine Erlaubnis:
    sie senkt den Nenner sichtbar, statt als Nulltreffer oder als Nichts durchzugehen.
  · Rückwirkend rekonstruierte Einträge (`quelle: "retro"`) zählen NIE in die Vorwärts-Bilanz.
    Sie stehen getrennt unter `retro` als Kontext. Der Ledger startet am Tag seiner Einführung.

Läuft im poly-global-scan.yml direkt NACH poly_whale_watch.py. REIN/testbar.
"""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from safe_write import write_json_atomic
from freigabe import untergrenze   # 04.09.2026: dieselbe Schranke wie ueberall sonst

BASE = Path(__file__).resolve().parent
LEDGER_FILE = BASE / "poly_whale_public_ledger.json"
RES_FILE    = BASE / "poly_resolutions.json"
CLOSE_FILE  = BASE / "poly_money_broad_close.json"
OUT_FILE    = BASE / "poly_public_record.json"

STAKE = 10.0            # Einheits-Einsatz je Push (wie im Papier-Depot) — macht ROI vergleichbar
PENDING_TTL_D = 10      # nie aufgelöst nach 10 Tagen → unaufloesbar (poly_resolutions hält Wochen)
SIG_Z = 1.645           # einseitige 95%-Untergrenze — ein Punktschätzer ist kein Beleg


def _now():
    return datetime.now(timezone.utc)


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _ts(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _age_d(ts, now):
    t = _ts(ts)
    return None if t is None else (now - t).total_seconds() / 86400.0


def _ok_price(p):
    return isinstance(p, (int, float)) and 0.0 < float(p) < 1.0


def wilson_lb(wins, n, z=SIG_Z):
    """Einseitige untere Schranke der Trefferquote. n=0 → 0.0 (kein Beleg ist kein Vorteil)."""
    if not n:
        return 0.0
    p = wins / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m)


def _close_price(close, key, side):
    if not isinstance(close, dict):
        return None
    p = ((close.get(key) or {}).get("prices") or {}).get(side)
    return float(p) if _ok_price(p) else None


def settle(ledger, resolutions, close, now=None) -> list[dict]:
    """Jeden pending-Eintrag gegen den Slug-Sieger abrechnen. Verändert den Ledger IN PLACE-frei:
    gibt eine neue Liste zurück. Einmal abgerechnet bleibt abgerechnet (kein Nachbewerten)."""
    now = now or _now()
    out = []
    for e in (ledger or []):
        if not isinstance(e, dict):
            continue
        e = dict(e)
        if e.get("status") != "pending":
            out.append(e)
            continue
        r = (resolutions or {}).get(e.get("key")) if isinstance(resolutions, dict) else None
        winner = (r or {}).get("winner")
        if not winner:
            age = _age_d(e.get("sentAt"), now)
            if age is not None and age > PENDING_TTL_D:
                e["status"] = "unaufloesbar"
                e["ageDays"] = round(age, 2)
            out.append(e)
            continue
        entry = e.get("pushPrice")
        cl = _close_price(close, e.get("key"), e.get("side"))
        win = (e.get("side") == winner)
        e["status"] = "settled"
        e["result"] = "win" if win else "loss"
        e["winner"] = winner
        e["closePrice"] = round(cl, 4) if cl is not None else None
        if _ok_price(entry):
            e["stake"] = STAKE
            e["pnl"] = round((STAKE / float(entry) - STAKE) if win else -STAKE, 2)
            e["clvPP"] = round(((cl if cl is not None else float(entry)) - float(entry)) * 100, 2)
        else:
            # Preis unbekannt → Treffer zählt, Geld NICHT. Kein erfundener Einstieg.
            e["stake"] = None
            e["pnl"] = None
            e["clvPP"] = None
        e["settledTs"] = now.isoformat()
        e["resolvedTs"] = (r or {}).get("ts")
        out.append(e)
    return out


def bilanz(rows) -> dict:
    """Kennzahlen über abgerechnete Zeilen. Trefferquote über ALLE settled (auch ohne Preis),
    ROI/CLV nur über die mit Preis — die Differenz steht als `nOhnePreis` sichtbar dabei.

    🔴 04.09.2026 — der Fund, der heute schon `stake_analyse.py` umgebaut hat, gilt hier genauso:

        EINE TREFFERQUOTE OHNE DIE PREISE IST KEINE ZAHL.

    Dieses Buch gab bisher `hit` und `hitUg` aus und daneben einen ROI ohne jede Schranke. Das
    ist die falsche Reihenfolge: 91% Treffer im Retro-Block klingen nach Beleg, aber dort ist
    `nOhnePreis == n` — bei ALLEN elf fehlt der Einstiegspreis. Elf Treffer zu unbekannten
    Quoten können +40% oder −40% Rendite sein; die Trefferquote unterscheidet die beiden Fälle
    nicht. Deshalb:

      · `roiUg` ist ab jetzt die Untergrenze der RENDITE (freigabe.untergrenze, dieselbe
        Normalapproximation und dieselbe n≥30-Grenze wie im Rest des Repos).
      · `belegt` hängt AUSSCHLIESSLICH an `roiUg > 0` — nie an der Trefferquote. Eine Serie
        von Favoritensiegen zu 0,93 hat eine glänzende Quote und verliert Geld.
      · `geldurteil` sagt beim Namen, ob über das Geld überhaupt geredet werden kann. Wo jede
        Zeile ohne Preis dasteht, ist die Antwort „nein" — und das steht dann auch da, statt
        dass eine Trefferquote die Lücke füllt.
      · Die CLV-Untergrenze lief bisher über eine eigene Inline-Formel ab n>1. Genau die
        Krankheit hat freigabe.untergrenze am 03.09. behandelt: drei ähnliche Werte ergeben
        eine Streuung nahe null, und die „Untergrenze" fällt auf den Mittelwert zusammen. Im
        gespeicherten Record stand deshalb `clvUg: -0.65` aus n=3. Jetzt dieselbe Schranke.
    """
    rows = [r for r in (rows or []) if isinstance(r, dict) and r.get("result")]
    n = len(rows)
    leer = {"n": 0, "wins": 0, "hit": None, "hitUg": None, "nOhnePreis": 0,
            "pnl": 0.0, "stake": 0.0, "roi": None, "roiUg": None, "belegt": False,
            "geldurteil": False, "clvAvg": None, "clvUg": None}
    if not n:
        return leer
    wins = sum(1 for r in rows if r["result"] == "win")
    mit = [r for r in rows if isinstance(r.get("stake"), (int, float)) and r["stake"]]
    pnl = sum(float(r.get("pnl") or 0) for r in mit)
    stake = sum(float(r["stake"]) for r in mit)
    clvs = [float(r["clvPP"]) for r in mit if isinstance(r.get("clvPP"), (int, float))]

    # Rendite je Push — nicht die Gesamtsumme. Für eine Streuung braucht es die Einzelwerte.
    renditen = [float(r["pnl"]) / float(r["stake"]) for r in mit
                if isinstance(r.get("pnl"), (int, float))]
    roi_ug = untergrenze(renditen) if renditen else None
    clv_ug = untergrenze(clvs) if clvs else None

    return {"n": n, "wins": wins, "hit": round(wins / n, 4),
            "hitUg": round(wilson_lb(wins, n), 4), "nOhnePreis": n - len(mit),
            "pnl": round(pnl, 2), "stake": round(stake, 2),
            "roi": (round(pnl / stake, 4) if stake else None),
            "roiUg": (round(roi_ug, 4) if roi_ug is not None else None),
            "belegt": bool(roi_ug is not None and roi_ug > 0),
            # Über Geld lässt sich nur reden, wo Preise da sind. Sonst zählt nur der Treffer.
            "geldurteil": bool(mit),
            "clvAvg": (round(sum(clvs) / len(clvs), 2) if clvs else None),
            "clvUg": (round(clv_ug, 2) if clv_ug is not None else None)}


def bilanz_nach(rows, field) -> dict:
    b = {}
    for r in (rows or []):
        if isinstance(r, dict) and r.get("result"):
            b.setdefault(str(r.get(field) if r.get(field) not in (None, "") else "?"), []).append(r)
    return {k: bilanz(v) for k, v in sorted(b.items())}


def report(ledger, now=None) -> dict:
    """Vorwärts-Buch und Retro-Kontext strikt getrennt. `retro` ist Kontext, kein Beleg."""
    now = now or _now()
    vor = [e for e in ledger if isinstance(e, dict) and e.get("quelle") != "retro"]
    retro = [e for e in ledger if isinstance(e, dict) and e.get("quelle") == "retro"]
    settled = [e for e in vor if e.get("status") == "settled"]
    return {
        "updatedAt": now.isoformat(),
        "startAb": min([e.get("sentAt") for e in vor if e.get("sentAt")] or [None]),
        "gesamt": len(vor),
        "offen": sum(1 for e in vor if e.get("status") == "pending"),
        "unaufloesbar": sum(1 for e in vor if e.get("status") == "unaufloesbar"),
        "agg": bilanz(settled),
        "byCat": bilanz_nach(settled, "cat"),
        "byRestock": bilanz_nach(settled, "restock"),
        "retro": {"n": len(retro),
                  "unaufloesbar": sum(1 for e in retro if e.get("status") == "unaufloesbar"),
                  "agg": bilanz([e for e in retro if e.get("status") == "settled"]),
                  "byCat": bilanz_nach([e for e in retro if e.get("status") == "settled"], "cat")},
    }


def main() -> int:
    led = _load(LEDGER_FILE, [])
    if not isinstance(led, list):
        print("⚠️  poly_whale_public_ledger.json ist keine Liste — nichts ausgewertet.")
        return 0
    led = settle(led, _load(RES_FILE, {}), _load(CLOSE_FILE, {}))
    write_json_atomic(LEDGER_FILE, led, indent=0)
    rep = report(led)
    write_json_atomic(OUT_FILE, rep, indent=1)
    a = rep["agg"]
    kopf = (f"🐋 Public-Pushs: {rep['gesamt']} gesendet · {rep['offen']} offen · "
            f"{rep['unaufloesbar']} unauflösbar · {a['n']} abgerechnet")
    if a["n"]:
        # Reihenfolge mit Absicht: erst das Geld, dann die Trefferquote. Die Quote ohne die
        # Preise sagt nichts ueber die Rendite, und was zuerst dasteht, wird zuerst geglaubt.
        if a["roi"] is not None:
            kopf += f" · ROI {a['roi']*100:+.1f}%"
            kopf += (f" (UG {a['roiUg']*100:+.1f}% — BELEGT)" if a["belegt"]
                     else f" (UG {a['roiUg']*100:+.1f}%)" if a["roiUg"] is not None
                     else " (kein Urteil, n zu klein)")
        elif not a["geldurteil"]:
            kopf += " · kein Geldurteil moeglich (kein Einstiegspreis)"
        kopf += f" · Treffer {a['hit']*100:.0f}% (UG {a['hitUg']*100:.0f}%)"
        if a["clvAvg"] is not None:
            kopf += f" · CLV {a['clvAvg']:+.2f} pp"
    print(kopf)
    if rep["retro"]["n"]:
        ra = rep["retro"]["agg"]
        hinweis = ""
        if ra["n"]:
            hinweis = f" (Treffer {ra['hit']*100:.0f}% auf n={ra['n']}"
            hinweis += (", ohne Einstiegspreis → keine Rendite berechenbar)"
                        if not ra["geldurteil"] else f", ROI {ra['roi']*100:+.1f}%)")
            hinweis += " — zählen NICHT ins Buch."
        print(f"   ℹ️  {rep['retro']['n']} rückwirkende Einträge als Kontext" + hinweis)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
