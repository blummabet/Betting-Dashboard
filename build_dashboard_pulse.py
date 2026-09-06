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


def _poly_pulse(track=None, record=None) -> dict | None:
    """Poly Public-Kandidaten (poly_shortlist_track.py → agg.public).

    12.08.2026 (Lucas): der Puls zeigt die HART GEGATETEN Public-Kandidaten (Conv>=7 + bewiesene
    Wallet + Mehrheit) statt der ganzen Shortlist — das ist die Stufe, die wir senden WUERDEN.

    🔴 04.09.2026 (Lucas-Uebersicht-Check). Genau dieses „wuerden" war das Problem. Die Kachel
    hiess „🎮 Poly Public" und stand mit n=155 / 70 % / +5,0 % ganz oben im Puls — als waere das
    die Bilanz des oeffentlichen Kanals. Sie ist es nicht: `poly-wallets.js` sagt an der Stelle
    selbst „NUR Vorschau (sendet nicht)". Was wirklich in den Kanal geht, sind die Whale-Pushs
    aus `poly_whale_watch.py`, und deren Buch (`poly_public_record.json`, seit 02.09.) stand an
    dem Tag bei n=3.

    Dieselbe Verwechslung hatte Lucas am Morgen im Track-Record gemeldet; dort steht die
    Trennung seither auf dem Board — hier stand sie noch nicht. Also: die Kachel behaelt ihre
    Zahlen (die Stufe ist eine sinnvolle Messgroesse), heisst aber nach dem, was sie misst, und
    traegt die Zahl des ECHTEN Push-Buchs als eigenes Feld daneben.
    """
    d = track if track is not None else _load("poly_shortlist_track.json")
    a = ((d or {}).get("agg") or {}).get("public") or {}
    if not a.get("n"):
        return None
    open_public = sum(1 for e in ((d or {}).get("open") or {}).values()
                      if isinstance(e, dict) and e.get("public"))
    rec = record if record is not None else _load("poly_public_record.json")
    gesendet = (rec or {}).get("gesamt")
    return {"n": a.get("n"),
            "hitPct": round(100.0 * (a.get("hit") or 0), 1),
            "roiPct": round(100.0 * (a.get("roi") or 0), 1),
            "clvAvg": a.get("clvAvg"),
            "openN": open_public,
            # Was tatsaechlich gesendet wurde — getrennt gezaehlt, damit die Vorschau nie wieder
            # als Kanal-Bilanz gelesen wird. None = das Buch gibt es (noch) nicht.
            "sendet": False,
            "gesendetN": gesendet if isinstance(gesendet, int) else None}


# 29.08.2026 (Lucas-Checkup, „C"): stand auf 8, waehrend poly-wallets.js fuer DIESELBE Datei
# (_PW_TRACK_MIN_N) 20 als belastbar ansetzt. Folge: die Uebersicht warb prominent mit
# „Beste Stufe Conv 9 · +40,8% ROI · n14", waehrend derselbe Track im Wallets-Tab bei n<20
# „zu wenig Daten" sagt. Dazu ist _best_bucket ein Maximum ueber ~10 Buckets — bei n=8-14
# gewinnt ueberwiegend das Rauschen. Mit 20 zeigt die Leiste Conv 6 (n=139, +4,3%) statt
# Conv 9 (n=14, +40,8%); die Nachbarstufe Conv 8 hat n=21 bei -6,6% — das passt zusammen.
STRIP_MIN_N = 20  # ab so vielen Plays gilt eine Conviction-Stufe / ein Signal als belastbar (Auto-Bet-Kandidat)


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


# 03.09.2026 (Lucas-Checkup der Uebersicht). Zwei Dinge stimmten an dieser Leiste nicht, und
# beide standen direkt UEBER dem Register, das es besser weiss:
#
#  1. `agg.byConv` aggregiert den GANZEN Bestand — 500 abgerechnete Plays ueber mehrere
#     Engine-Versionen (`ev`: 70x 2026-09-01, 76x 2026-08-29b, 8x 2026-08-29, 346 ohne Stempel).
#     Die Leiste warb mit „Beste Stufe Conv 7 · +2.5% ROI · n149", waehrend Ebene 1 fuer dieselbe
#     Stufe `4/30` zeigt und ausdruecklich sagt: „Plays aelterer Versionen zaehlen nicht fuer eine
#     Freigabe". Zwei Flaechen, zwei Regeln, eine davon in der Kopfzeile.
#  2. `_best_bucket` nimmt das MAXIMUM ueber ~10 Buckets und zeigt einen Punktschaetzer. Ein
#     Maximum ueber viele Buckets ist selbst eine Auswahl — ohne Untergrenze steht dort die
#     glucklichste Stufe, nicht die beste.
#
# Beides behoben: gerechnet wird auf der aktuellen Engine, und ob das Ergebnis TRAEGT, entscheidet
# dieselbe Untergrenze wie im Register. Traegt es nicht, steht es weiter da — aber als
# „nicht belegt", nicht als Empfehlung.
def _aktuelle_zeilen(track):
    """Die abgerechneten Plays der AKTUELLEN Engine-Version. → (zeilen, stempel). REIN/testbar.

    Ohne erkennbaren Stempel wird NICHT gefiltert (wie im Register: eine alte Datei ohne Stempel
    soll die Leiste nicht leeren) — der Rueckgabewert sagt dann `None`, damit der Aufrufer es
    kennzeichnen kann.
    """
    st = (track or {}).get("settled") or []
    st = list(st.values()) if isinstance(st, dict) else list(st)
    st = [r for r in st if isinstance(r, dict)]
    try:
        from freigabe import aktuelle_engine
        ev = aktuelle_engine(track)
    except Exception:
        ev = None
    if not ev:
        return st, None
    return [r for r in st if r.get("ev") == ev], ev


def _rendite(r):
    """Rendite je Play (pnl/stake) — dieselbe Groesse, auf der das Register rechnet."""
    try:
        stake = float(r.get("stake") or 0)
        return float(r.get("pnl") or 0) / stake if stake else None
    except (TypeError, ValueError):
        return None


def _bucket_renditen(rows, art):
    """{bucket: [rendite, …]} nach denselben Regeln wie poly_shortlist_track.aggregate:
    `conv` per int-Gleichheit, `signals` per Mitgliedschaft (ein Play zaehlt in mehreren).
    REIN/testbar."""
    out = {}
    for r in (rows or []):
        w = _rendite(r)
        if w is None:
            continue
        if art == "conv":
            try:
                out.setdefault(str(int(r.get("conv") or 0)), []).append(w)
            except (TypeError, ValueError):
                continue
        else:
            for tg in (r.get("signals") or []):
                out.setdefault(str(tg), []).append(w)
    return out


def _best_bucket(buckets) -> dict | None:
    """Stufe/Signal mit dem hoechsten ROI, der >0 ist und >= STRIP_MIN_N Plays hat.

    `buckets` ist {name: [rendite, …]}. `belegt` sagt, ob die Untergrenze ueber null liegt —
    dieselbe Funktion und dieselbe Mindest-Stichprobe wie im Freigabe-Register. REIN/testbar.
    """
    try:
        from freigabe import untergrenze
    except Exception:
        untergrenze = lambda w: None            # noqa: E731 — ohne Register keine Untergrenze
    best = None
    for name, werte in (buckets or {}).items():
        n = len(werte or [])
        if n < STRIP_MIN_N:
            continue
        roi = sum(werte) / n
        if roi <= 0 or (best is not None and roi <= best[1]):
            continue
        best = (name, roi, n, untergrenze(werte))
    if not best:
        return None
    name, roi, n, ug = best
    return {"key": name, "roiPct": round(100.0 * roi, 1), "n": n,
            "roiUgPct": (round(100.0 * ug, 1) if ug is not None else None),
            "belegt": bool(ug is not None and ug > 0)}


def _strip(track=None, bf_ledger=None, cards_open=0) -> dict:
    """Leiste unter dem Puls: wo lohnt sich Setzen (beste Stufe/Signal) + was laeuft gerade."""
    t = track if track is not None else _load("poly_shortlist_track.json")
    bl = bf_ledger if bf_ledger is not None else _load("betfair_public_ledger.json")
    zeilen, stempel = _aktuelle_zeilen(t)
    return {
        "engine": stempel,
        "engineGefiltert": bool(stempel),
        "bestConv": _best_bucket(_bucket_renditen(zeilen, "conv")),
        "bestSignal": _best_bucket(_bucket_renditen(zeilen, "signal")),
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
    # 06.09.2026 (Lucas: „auf der Uebersicht hast auch mal was eingebaut, das sollte man nicht
    # vergessen") — und beim Hinsehen stand dort dieselbe Krankheit, die wir heute aus dem
    # Lern-Loop entfernt haben: `edge = Win%dafuer - Win%dagegen`. **Eine Trefferquote ohne die
    # Quoten ist keine Zahl** (Bug-Klasse 6). „Form-Rating +53 %" kam aus 62 % gegen 9 % — bei
    # eir Gegen-Seite von elf Faellen, ohne jede Untergrenze.
    #
    # Der Docstring oben sagte selbst: „ROI bewusst NICHT: die Ledger speichern keine Quote je
    # Pick. Kommt, sobald wir Quoten mitschreiben." Seit dem 06.09. schreiben wir sie mit.
    #
    # Das Urteil kommt jetzt aus `signal_bilanz` — derselben Rechnung, die der Guard und der
    # Lern-Loop benutzen. Eine Definition von „traegt bei", nicht drei. Die Win-Quoten bleiben
    # als BESCHREIBUNG stehen; sie sind kein Urteil und heissen auch nicht mehr so.
    bil = {}
    try:
        import signal_bilanz as _SB
        from update_signal_weights import _preis_justierter_outcome as _po
        bil = _SB.bilanz(graded, _po)
    except Exception as e:
        print(f"  ⚠️  Signal-Bilanz nicht rechenbar: {e}")

    rows = []
    for nm, a in agg.items():
        sr = round(100.0 * a["suppW"] / a["supp"]) if a["supp"] else None
        orr = round(100.0 * a["oppW"] / a["opp"]) if a["opp"] else None
        b = bil.get(nm) or {}
        rows.append({"name": nm, "fire": a["fire"],
                     "supp": a["supp"], "suppWinPct": sr,
                     "opp": a["opp"], "oppWinPct": orr,
                     # Das gemessene Urteil: Unterschied im CLV zu den Picks, auf denen dieses
                     # Signal SCHWIEG — geschichtet nach der Zahl der uebrigen Signale.
                     "clvDiff": b.get("clvDiff"),
                     "clvDiffUG": b.get("clvDiffUG"),
                     "clvUrteil": b.get("clvUrteil") or "kein Urteil",
                     "ausgangDiff": b.get("ausgangDiff"),
                     "ausgangUrteil": b.get("ausgangUrteil") or "kein Urteil",
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
    # 03.09.2026 (Lucas-Checkup): `clvPP` steht auf jedem Pick — angelegt mit 0.0, gefuellt erst
    # mit einer Closing-Linie. Ohne `clvResolved` zaehlten die Platzhalter-Nullen voll mit: sie
    # zogen den Ø CLV Richtung null (die Zahl sah BESSER aus als sie ist) und sassen im Nenner
    # von „schlaegt Close", wo sie per Konstruktion nie zaehlen koennen. Im Fenster vom 03.09.
    # waren 7 von 30 Werten exakt 0.0; ueber den ganzen Bestand 61 von 281.
    # Dieselbe Regel wie in compute_clv_summary — dort steht sie seit jeher: „kein Closing
    # erfasst → zaehlt nur in die Abdeckung". Aeltere Ledger-Zeilen ohne das Feld gelten als
    # unbelegt: nicht wissen ist keine Erlaubnis (nach einem Lauf von build_signal_ledger tragen
    # alle Zeilen den Stempel).
    clvs = [r.get("clvPP") for r in last_chrono
            if isinstance(r.get("clvPP"), (int, float)) and r.get("clvResolved")]
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
