#!/usr/bin/env python3
"""
build_dashboard_pulse.py — winziger Performance-Puls für die Übersicht (30.07.2026, Lucas).

Liest die drei Signal-Ledger (liga/mls/wm), nimmt die LETZTEN 30 abgerechneten Picks (nach
resolvedAt) und verdichtet sie zu einer ~1-KB-Datei `dashboard_pulse.json`, die die Übersicht
ohne die schweren Ledger (WM allein ~113 KB) laden kann. Metriken:
  · avgClvPP    — Ø Closing Line Value (schlagen wir die Schlussquote?)  ← der Nordstern
  · pctBeatClose— Anteil Picks mit CLV > 0
  · winPct      — WIN / (WIN+LOSS), VOID/offene raus
  · series      — die 30 Einzel-CLVs (alt→neu) für die Sparkline
ROI bewusst NICHT: die Ledger speichern keine Quote je Pick. Kommt, sobald wir Quoten mitschreiben.
"""
from __future__ import annotations
import json, datetime as dt
from pathlib import Path

BASE = Path(__file__).resolve().parent
LEDGERS = ["liga_signal_ledger.json", "mls_signal_ledger.json", "wm_signal_ledger.json"]
N = 30


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _betfair_pulse(rec=None) -> dict | None:
    """Betfair-Geld-Signal-Bilanz (betfair_track_record.py → global). Win/Loss + ROI, KEIN CLV
    (Betfair-Track speichert kein Closing je Signal). Zeigt die Gesamt-Trefferquote/ROI aller
    abgerechneten Betfair-Signale."""
    g = ((rec if rec is not None else _load("betfair_track_record.json")) or {}).get("global") or {}
    if not g.get("n"):
        return None
    return {"n": g.get("n"),
            "hitPct": round(100.0 * (g.get("hitRate") or 0), 1),
            "roiPct": round(100.0 * (g.get("roi") or 0), 1)}


def _poly_pulse(track=None) -> dict | None:
    """Poly Public-Kandidaten (poly_shortlist_track.py → agg.public). 12.08.2026 (Lucas): der Puls zeigt
    jetzt die HART GEGATETEN Public-Kandidaten (Conv≥7 + bewiesene Wallet + Mehrheit) statt der ganzen
    Shortlist — das ist die Stufe, die wir wirklich senden wuerden. n/Treffer/ROI/Ø CLV + offene Public-Plays."""
    d = track if track is not None else _load("poly_shortlist_track.json")
    a = ((d or {}).get("agg") or {}).get("public") or {}
    if not a.get("n"):
        return None
    open_public = sum(1 for e in ((d or {}).get("open") or {}).values()
                      if isinstance(e, dict) and e.get("public"))
    return {"n": a.get("n"),
            "hitPct": round(100.0 * (a.get("hit") or 0), 1),
            "roiPct": round(100.0 * (a.get("roi") or 0), 1),
            "clvAvg": a.get("clvAvg"),
            "openN": open_public}


STRIP_MIN_N = 8   # ab so vielen Plays gilt eine Conviction-Stufe / ein Signal als belastbar (Auto-Bet-Kandidat)


def _moneymap_pulse(rec=None) -> dict | None:
    """Money-Map-Konsens-Bilanz (betfair_consensus.py -> money_map_record.json). Folgt man der
    Betfair-Geld-Seite: globale Trefferquote + Konsens-Trefferquote (nur 3/3-einige Faelle) + offen.
    Additiv, faellt sauber auf None, solange nichts abgerechnet ist. 11.08.2026 (Lucas)."""
    d = rec if rec is not None else _load("money_map_record.json")
    if not isinstance(d, dict):
        return None
    g = d.get("global") or {}
    if not g.get("n"):
        return None
    kon = (d.get("byVerdict") or {}).get("konsens") or {}
    return {"n": g.get("n"),
            "hitPct": round(100.0 * (g.get("hitRate") or 0), 1),
            "konHitPct": (round(100.0 * kon["hitRate"], 1) if kon.get("hitRate") is not None else None),
            "konN": kon.get("n") or 0,
            "openN": d.get("pending") or 0}


def _best_bucket(buckets) -> dict | None:
    """Stufe/Signal mit dem hoechsten ROI, der >0 ist und >= STRIP_MIN_N Plays hat. REIN/testbar."""
    best = None
    for name, b in (buckets or {}).items():
        if not isinstance(b, dict):
            continue
        n, roi = b.get("n") or 0, b.get("roi")
        if n >= STRIP_MIN_N and isinstance(roi, (int, float)) and roi > 0 and (best is None or roi > best[1]):
            best = (name, roi, n)
    return {"key": best[0], "roiPct": round(100.0 * best[1], 1), "n": best[2]} if best else None


def _strip(track=None, bf_ledger=None, cards_open=0) -> dict:
    """Leiste unter dem Puls: wo lohnt sich Setzen (beste Stufe/Signal) + was laeuft gerade."""
    t = track if track is not None else _load("poly_shortlist_track.json")
    bl = bf_ledger if bf_ledger is not None else _load("betfair_public_ledger.json")
    a = (t or {}).get("agg") or {}
    return {
        "bestConv": _best_bucket(a.get("byConv")),
        "bestSignal": _best_bucket(a.get("bySignal")),
        "inflight": {
            "poly": len((t or {}).get("open") or {}),
            "betfair": sum(1 for x in (bl or []) if isinstance(x, dict) and x.get("status") == "pending"),
            "cards": cards_open,
        },
    }


SIG_SUPP_TH  = 0.5   # ab |score| >= 0.5 zaehlt ein Signal als DAFUER / DAGEGEN
SIG_MIN_FIRE = 6     # darunter: „zu wenig Daten" (Ampel grau)


# 22.08.2026 (Lucas): WM raus — die hat mit dem Liga-Betrieb nichts zu tun. Board zaehlt nur die
# Ligen mit laufenden Cards (Top-5 + MLS). Anfangs kleine n; fuellt sich Wochenende fuer Wochenende.
BOARD_EXCLUDE = ("wm_signal_ledger.json",)


def _signal_scoreboard(recs, exclude=BOARD_EXCLUDE) -> dict | None:
    """22.08.2026 (Lucas: „checken ob die Signale ueberhaupt funktionieren"). Pro Signal ueber
    ALLE abgerechneten Cards: wie oft gefeuert, und Win% wenn es DAFUER (score>=TH) vs. DAGEGEN
    (score<=-TH) stand. edge = Win%dafuer − Win%dagegen (>0 = Signal traegt Richtungsinfo). Plus
    Ø CLV je Signal. Voller Ledger-Bestand (nicht nur die letzten 30), damit Samples belastbar sind."""
    graded = [r for r in recs if str(r.get("result")).upper() in ("WIN", "LOSS")
              and r.get("_ledger") not in exclude]
    if not graded:
        return None
    base_w = sum(1 for r in graded if str(r.get("result")).upper() == "WIN")
    agg = {}
    for r in graded:
        win = str(r.get("result")).upper() == "WIN"
        clv = r.get("clvPP")
        for s in (r.get("signals") or []):
            nm = s.get("name")
            if not nm:
                continue
            sc = s.get("score") or 0
            a = agg.setdefault(nm, {"fire": 0, "supp": 0, "suppW": 0, "opp": 0, "oppW": 0, "clvSum": 0.0, "clvN": 0})
            a["fire"] += 1
            if isinstance(clv, (int, float)):
                a["clvSum"] += clv; a["clvN"] += 1
            if sc >= SIG_SUPP_TH:
                a["supp"] += 1; a["suppW"] += 1 if win else 0
            elif sc <= -SIG_SUPP_TH:
                a["opp"] += 1; a["oppW"] += 1 if win else 0
    rows = []
    for nm, a in agg.items():
        sr = round(100.0 * a["suppW"] / a["supp"]) if a["supp"] else None
        orr = round(100.0 * a["oppW"] / a["opp"]) if a["opp"] else None
        edge = (sr - orr) if (sr is not None and orr is not None) else None
        rows.append({"name": nm, "fire": a["fire"],
                     "supp": a["supp"], "suppWinPct": sr,
                     "opp": a["opp"], "oppWinPct": orr,
                     "edge": edge,
                     "clvAvg": round(a["clvSum"] / a["clvN"], 2) if a["clvN"] else None})
    rows.sort(key=lambda x: -x["fire"])
    return {"n": len(graded), "baseWinPct": round(100.0 * base_w / len(graded)),
            "minFire": SIG_MIN_FIRE, "rows": rows}


# ── NOBET-Bilanz (23.08.2026, Lucas: „wenn ein NOBET stark positiv wäre, was macht man?") ──────
# Waren unsere Abstufungen richtig? Pro Kipp-Grund die Schatten-Trefferquote UND den Schatten-CLV
# der demoteten Picks (verdict=NOBET + shadowResult). STRENG getrennt vom echten P&L — reines
# Kalibrier-Signal. CLV ist der Nordstern: lief die Linie NACH dem Kippen weiter GEGEN uns
# (Ø CLV < 0) → richtig gekippt; weiter FÜR uns (Ø CLV > 0) → zu früh raus = Sieger weggeworfen.
NOBET_MIN_FIRE = 6      # darunter: „zu wenig Daten" (grau)
NOBET_CLV_BAND = 1.0    # |Ø CLV| >= 1pp entscheidet grün/rot; dazwischen gelb
DATA_FILES = ["liga-data.json", "mls-data.json", "wm2026-data.json"]


def _nobet_bucket(reason) -> str:
    r = (reason or "").lower()
    if "conviction" in r:                                   return "Conviction zu dünn"
    if "engine-netto" in r or "modell gegen" in r:          return "Engine gegen den Pick"
    if "linie gegen" in r or "edge weg" in r:               return "Linie weggelaufen"
    if "zu kurz" in r:                                       return "Quote zu kurz geworden"
    if "value" in r or "ausgelaufen" in r or "konsens" in r: return "Value ausgelaufen"
    return "Sonstige"


def _nobet_scoreboard(data_files=None) -> dict | None:
    files = data_files if data_files is not None else DATA_FILES
    buckets, tot = {}, {"n": 0, "w": 0, "clvSum": 0.0, "clvN": 0}
    for f in files:
        d = _load(f)
        picks = d.get("picks") if isinstance(d, dict) else None
        if not isinstance(picks, dict):
            continue
        for pl in picks.values():
            if not isinstance(pl, list):
                continue
            for p in pl:
                if not isinstance(p, dict) or p.get("verdict") != "NOBET":
                    continue
                sr = str(p.get("shadowResult") or "").upper()
                if sr not in ("WIN", "LOSS"):
                    continue
                a = buckets.setdefault(_nobet_bucket(p.get("nobetReason")),
                                       {"n": 0, "w": 0, "clvSum": 0.0, "clvN": 0})
                a["n"] += 1; tot["n"] += 1
                if sr == "WIN":
                    a["w"] += 1; tot["w"] += 1
                clv = p.get("clvPP")
                if isinstance(clv, (int, float)):
                    a["clvSum"] += clv; a["clvN"] += 1
                    tot["clvSum"] += clv; tot["clvN"] += 1
    if not tot["n"]:
        return None
    rows = []
    for bk, a in buckets.items():
        rows.append({"reason": bk, "n": a["n"], "wins": a["w"],
                     "winPct": round(100.0 * a["w"] / a["n"]) if a["n"] else None,
                     "clvAvg": round(a["clvSum"] / a["clvN"], 2) if a["clvN"] else None})
    rows.sort(key=lambda x: -x["n"])
    return {"n": tot["n"], "wins": tot["w"],
            "winPct": round(100.0 * tot["w"] / tot["n"]) if tot["n"] else None,
            "clvAvg": round(tot["clvSum"] / tot["clvN"], 2) if tot["clvN"] else None,
            "minFire": NOBET_MIN_FIRE, "clvBand": NOBET_CLV_BAND, "rows": rows}


def build() -> dict:
    recs, cards_open = [], 0
    for lf in LEDGERS:
        d = _load(lf)
        for r in (d.get("records") or []) if isinstance(d, dict) else []:
            if not isinstance(r, dict):
                continue
            if r.get("resolvedAt"):
                r["_ledger"] = lf          # Herkunft merken (fuer Board-Filter)
                recs.append(r)
            else:
                cards_open += 1
    recs.sort(key=lambda r: str(r.get("resolvedAt")), reverse=True)
    last = recs[:N]
    last_chrono = list(reversed(last))                    # alt→neu für die Sparkline
    clvs = [r.get("clvPP") for r in last_chrono if isinstance(r.get("clvPP"), (int, float))]
    wins = sum(1 for r in last if str(r.get("result")).upper() == "WIN")
    losses = sum(1 for r in last if str(r.get("result")).upper() == "LOSS")
    graded = wins + losses
    avg = round(sum(clvs) / len(clvs), 2) if clvs else None
    beat = round(100.0 * sum(1 for c in clvs if c > 0) / len(clvs), 1) if clvs else None
    win = round(100.0 * wins / graded, 1) if graded else None
    return {
        "_meta": {"description": "Übersicht-Puls: letzte %d abgerechnete Picks (CLV/Trefferquote)." % N,
                  "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "updated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
        "n": len(last), "nClv": len(clvs), "nGraded": graded,
        "avgClvPP": avg, "pctBeatClose": beat, "winPct": win, "wins": wins, "losses": losses,
        "series": [round(c, 2) for c in clvs],
        "oldest": (last_chrono[0].get("resolvedAt") if last_chrono else None),
        "newest": (last[0].get("resolvedAt") if last else None),
        "betfair": _betfair_pulse(),   # 07.08.2026 (Lucas): Betfair-Tracking mit in den Puls
        "poly": _poly_pulse(),         # 07.08.2026 (Lucas): Poly „Heute wetten" mit in den Puls
        "moneymap": _moneymap_pulse(),  # 11.08.2026 (Lucas): Money-Map-Konsens mit in den Puls
        "strip": _strip(cards_open=cards_open),   # 07.08.2026 (Lucas): wo lohnt Setzen + was laeuft
        "signalBoard": _signal_scoreboard(recs),  # 22.08.2026 (Lucas): pro-Signal-Bilanz (funktionieren sie?)
        "nobetBoard": _nobet_scoreboard(),  # 23.08.2026 (Lucas): NOBET-Bilanz — waren die Abstufungen richtig (Schatten-Win + CLV je Grund)?
    }


def main():
    out = build()
    (BASE / "dashboard_pulse.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print("dashboard_pulse.json:", {k: out[k] for k in ("n", "avgClvPP", "pctBeatClose", "winPct")},
          "| betfair", out.get("betfair"), "| poly", out.get("poly"))


if __name__ == "__main__":
    main()
