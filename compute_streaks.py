#!/usr/bin/env python3
"""compute_streaks.py — Serien-/Streak-Content (28.06.2026, Lucas).

Aktive Team-Serien aus den Form-Sequenzen (fetch_wm_form: o25Seq/bttsSeq, most-recent-first):
  • Über 2,5 / Unter 2,5 Tore in Folge
  • Beide treffen (Ja/Nein) in Folge

EHRLICH: eine Serie allein ist KEIN Edge (Gambler's Fallacy). Darum bekommt jede Serie einen
daten-basierten **Continuation-Indikator** aus der Grundrate (over25Rate/bttsRate über ~15 Spiele):
stützt die Grundrate die Serie → „intakt"; läuft die Serie gegen die Grundrate → „wackelt"
(eher Zufall/Regression). So wird aus Content ein begründeter Hinweis.

Reine Content-Schicht: NICHT im P&L/Lern-Loop. Dataset-aware. Schreibt {wm_,liga_}streaks.json.
Ecken-Serien folgen, sobald Ecken pro Spiel erfasst sind (cornersForm hat nur Schnitte).
Lauf 1×/Woche (engl. Woche 2×) nach fetch_wm_form.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone

import cocobet_dataset as D

OUT = D.file("wm_streaks.json", "liga_streaks.json")

MIN_LEN = 3     # ab dieser Länge zeigen
STRONG_LEN = 5  # ab hier „starke" Serie (für die Cards-Sektion)

# (key, seq-Feld, Ziel-Bool, Anzeige-Markt, welche Grundrate stützt)
MARKETS = [
    ("over25",  "o25Seq",  True,  "Über 2,5 Tore",          "over25Rate", False),
    ("under25", "o25Seq",  False, "Unter 2,5 Tore",         "over25Rate", True),
    ("bttsYes", "bttsSeq", True,  "Beide Teams treffen",    "bttsRate",   False),
    ("bttsNo",  "bttsSeq", False, "Beide treffen — Nein",   "bttsRate",   True),
]


def _lead_run(seq: list, target: bool) -> int:
    """Länge der führenden (jüngsten) Serie, in der seq[i] == target."""
    n = 0
    for v in (seq or []):
        if bool(v) == target:
            n += 1
        else:
            break
    return n


def _continuation(rate, target_is_false: bool, length: int) -> dict:
    """Stützt die Grundrate die Serie? rate = Roh-Rate des Marktes (z.B. over25Rate)."""
    if rate is None:
        return {"state": "neutral", "ratePct": None, "label": "zu wenig Daten"}
    underlying = (1.0 - rate) if target_is_false else rate   # Rate FÜR die Serien-Richtung
    pct = round(underlying * 100)
    if underlying >= 0.60:
        state = "intakt"
    elif underlying <= 0.45 or (length >= 8 and underlying < 0.55):
        state = "wackelt"
    else:
        state = "neutral"
    return {"state": state, "ratePct": pct, "label": f"Grundrate dafür {pct}%"}


def build_streaks(wm: dict) -> dict:
    form = wm.get("form") or {}
    # Team-ID → {name, league, leagueName}
    lookup = {}
    for gkey, g in (wm.get("groups") or {}).items():
        gname = g.get("name") or gkey
        for t in (g.get("teams") or []):
            lookup[str(t.get("id"))] = {"team": t.get("name") or str(t.get("id")),
                                        "league": gkey, "leagueName": gname}
    streaks = []
    for tid, f in form.items():
        if not isinstance(f, dict):
            continue
        meta = lookup.get(str(tid)) or {"team": str(tid), "league": "?", "leagueName": "?"}
        for key, seqfield, target, market, ratefield, target_false in MARKETS:
            length = _lead_run(f.get(seqfield) or [], target)
            if length < MIN_LEN:
                continue
            cont = _continuation(f.get(ratefield), target_false, length)
            streaks.append({
                "teamId": str(tid), "team": meta["team"],
                "league": meta["league"], "leagueName": meta["leagueName"],
                "type": key, "market": market, "length": length,
                "strong": length >= STRONG_LEN, "continuation": cont,
            })
    # längste zuerst; bei Gleichstand „intakt" vor dem Rest
    _order = {"intakt": 0, "neutral": 1, "wackelt": 2}
    streaks.sort(key=lambda s: (-s["length"], _order.get(s["continuation"]["state"], 1)))
    return {
        "_meta": {"dataset": D.active_dataset(), "generatedAt": datetime.now(timezone.utc).isoformat(),
                  "minLen": MIN_LEN, "strongLen": STRONG_LEN},
        "streaks": streaks,
    }


def main() -> None:
    wm = json.loads(D.data_file().read_text(encoding="utf-8"))
    out = build_streaks(wm)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(out["streaks"])
    strong = sum(1 for s in out["streaks"] if s["strong"])
    print(f"✅ Streaks ({D.active_dataset()}): {n} aktive Serien (≥{MIN_LEN}), {strong} stark (≥{STRONG_LEN}) → {OUT.name}")


if __name__ == "__main__":
    main()
