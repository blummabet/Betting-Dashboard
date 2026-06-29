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

# Tor-/BTTS-/Team-Märkte aus form (mit venueSeq). (key, seq-Feld, Ziel, Markt, Grundrate, target_false)
FORM_MARKETS = [
    ("over25",     "o25Seq",    True,  "Über 2,5 Tore",        "over25Rate",     False),
    ("under25",    "o25Seq",    False, "Unter 2,5 Tore",       "over25Rate",     True),
    ("bttsYes",    "bttsSeq",   True,  "Beide Teams treffen",  "bttsRate",       False),
    ("bttsNo",     "bttsSeq",   False, "Beide treffen — Nein", "bttsRate",       True),
    ("scored",     "scoredSeq", True,  "Team trifft",          "scoredRate",     False),
    ("cleanSheet", "csSeq",     True,  "Zu null",              "cleanSheetRate", False),
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


def _filter_venue(seq, venue_seq, venue):
    """Sequenz auf Heim ('H') / Auswärts ('A') filtern (Reihenfolge erhalten). 'all' = ganze Reihe.
    Ohne/fehljustierte venue_seq → ganze Reihe (Fallback)."""
    if venue == "all" or not venue_seq or len(venue_seq) != len(seq):
        return seq
    return [seq[i] for i in range(len(seq)) if venue_seq[i] == venue]


def _next_fixtures(wm):
    """Team-ID → nächstes anstehendes Spiel {oppId, oppName, atHome, date} (frühestes ab heute)."""
    from datetime import date as _date
    today = _date.today().isoformat()
    teams = {}
    for g in (wm.get("groups") or {}).values():
        for t in (g.get("teams") or []):
            teams[str(t.get("id"))] = t.get("name") or str(t.get("id"))
    nf = {}
    for g in (wm.get("groups") or {}).values():
        for fx in (g.get("fixtures") or []):
            d = fx.get("date") or ""
            if not d or d < today:
                continue
            ko = fx.get("kickoff") or (d + "T00:00:00Z")
            for tid, opp, at_home in ((fx.get("home"), fx.get("away"), True),
                                      (fx.get("away"), fx.get("home"), False)):
                if not tid:
                    continue
                prev = nf.get(str(tid))
                if not prev or ko < prev["_ko"]:
                    nf[str(tid)] = {"oppId": str(opp), "oppName": teams.get(str(opp), str(opp)),
                                    "atHome": at_home, "date": d, "_ko": ko}
    for v in nf.values():
        v.pop("_ko", None)
    return nf


def _opp_rate_pct(key, opp_id, form, cf):
    """Komplementäre Grundrate des nächsten Gegners (adamchoi-Paarung) in %."""
    of = form.get(str(opp_id)) or {}
    oc = cf.get(str(opp_id)) or {}
    if key in ("over25", "under25"):
        r = of.get("over25Rate")
    elif key in ("bttsYes", "bttsNo"):
        r = of.get("bttsRate")
    elif key == "scored":                      # Team trifft → Gegner kassiert (1 − clean sheet)
        r = of.get("cleanSheetRate"); r = (1.0 - r) if r is not None else None
    elif key == "cleanSheet":                  # zu null → Gegner trifft nicht (1 − scored)
        r = of.get("scoredRate"); r = (1.0 - r) if r is not None else None
    elif key in ("cornersOver", "cornersUnder"):
        r = oc.get("overLineRate")
    elif key == "cards":
        r = oc.get("cardOverRate")
    else:
        r = None
    return round(r * 100) if r is not None else None


def build_streaks(wm: dict) -> dict:
    form = wm.get("form") or {}
    cf = wm.get("cornersForm") or {}
    lookup = {}
    for gkey, g in (wm.get("groups") or {}).items():
        gname = g.get("name") or gkey
        for t in (g.get("teams") or []):
            lookup[str(t.get("id"))] = {"team": t.get("name") or str(t.get("id")),
                                        "league": gkey, "leagueName": gname}
    next_fx = _next_fixtures(wm)
    streaks = []

    def _emit(tid, seq, venue_seq, target, market, rate, target_false, key):
        meta = lookup.get(str(tid)) or {"team": str(tid), "league": "?", "leagueName": "?"}
        _has_venue = bool(venue_seq) and len(venue_seq) == len(seq)
        for venue in ("all", "H", "A"):
            if venue != "all" and not _has_venue:
                continue   # ohne venueSeq keine Heim/Auswärts-Duplikate
            length = _lead_run(_filter_venue(seq, venue_seq, venue), target)
            if length < MIN_LEN:
                continue
            cont = _continuation(rate, target_false, length)
            s = {
                "teamId": str(tid), "team": meta["team"],
                "league": meta["league"], "leagueName": meta["leagueName"],
                "type": key, "market": market, "length": length, "venue": venue,
                "strong": length >= STRONG_LEN, "continuation": cont,
                "ratePct": cont["ratePct"],
            }
            nf = next_fx.get(str(tid))
            if nf:
                s["next"] = {**nf, "oppRatePct": _opp_rate_pct(key, nf["oppId"], form, cf)}
            streaks.append(s)

    # Tor-/BTTS-/Team-Märkte (form, venueSeq)
    for tid, f in form.items():
        if not isinstance(f, dict):
            continue
        vseq = f.get("venueSeq")
        for key, seqfield, target, market, ratefield, tf in FORM_MARKETS:
            seq = f.get(seqfield)
            if seq:
                _emit(tid, seq, vseq, target, market, f.get(ratefield), tf, key)

    # Ecken + Karten (cornersForm)
    for tid, c in cf.items():
        if not isinstance(c, dict):
            continue
        cline = c.get("cornerLine", 9.5)
        cl_s = str(cline).replace(".", ",")
        cseq, cvenue, crate = c.get("cornerOverSeq"), c.get("cornerVenueSeq"), c.get("overLineRate")
        if cseq:
            _emit(tid, cseq, cvenue, True,  f"Über {cl_s} Ecken",  crate, False, "cornersOver")
            _emit(tid, cseq, cvenue, False, f"Unter {cl_s} Ecken", crate, True,  "cornersUnder")
        kline = c.get("cardLine", 3.5)
        kl_s = str(kline).replace(".", ",")
        kseq, kvenue, krate = c.get("cardOverSeq"), c.get("cardVenueSeq"), c.get("cardOverRate")
        if kseq:
            _emit(tid, kseq, kvenue, True, f"Über {kl_s} Karten", krate, False, "cards")

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
