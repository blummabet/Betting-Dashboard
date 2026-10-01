#!/usr/bin/env python3
"""serien_wetten_buch.py — das Buch zur Serien-Wetten-Tafel (01.10.2026, Lucas: „ja" zu Punkt 5).

Die Tafel „🎯 Serien-Wetten" zeigt je Serie die Trefferchance und eine Quote. Beides ist eine
BEHAUPTUNG: „82 % laut Markt", „71 % laut Modell". Dieses Buch prueft sie vorwaerts:

  • vormerken: jede Zeile der Wettliste wird beim ERSTEN Erscheinen mit Chance und Quote
    festgeschrieben (`erst*`). Spaeter gesehene Werte laufen bis zum Anpfiff in `letzt*` mit —
    die erste Quote ist die, zu der man beim Lesen der Tafel gespielt haette.
  • abrechnen: nach Spielende ueber Team + Datum (nicht ueber einen Schluessel, s.
    telegram_streak_watch._fixture_fuer) und `streak_held` — dieselbe Regel wie das Serien-Buch.
  • bilanz: Trefferquote GEGEN die angezeigte Chance (stimmt die Zahl?) und Rendite zur
    angezeigten Quote (lohnt es?) — getrennt nach Markt- und Modell-Chance. Urteil ueber die
    Grenzen, nicht ueber den Punktschaetzer; das Urteil steht im Artefakt, Frontends lesen nur.

Erwartung vorab (Backtest Top-5, 7.156 Spiele): Markt-Chancen treffen so oft wie angezeigt,
die Rendite liegt um die Buchmacher-Marge im Minus. Ein anderes Ergebnis waere der Fund.

Ecken/Karten stehen nicht im Endstand: sie werden als `unaufloesbar` gebucht und bleiben im
Nenner sichtbar, statt still zu verschwinden.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cocobet_dataset as D
from telegram_streak_watch import _fixture_finished, _fixture_fuer, _parse_ko, _wilson, streak_held

BASE = Path(__file__).parent
STREAKS_FILE = D.file("wm_streaks.json", "liga_streaks.json")
BUCH_FILE = BASE / f"{D.prefix()}serien_wetten_buch.json"
BILANZ_MIN_N = 30
# Kein Ergebnis X Tage nach Anpfiff = verschoben/abgesagt oder Feed-Luecke: als unaufloesbar
# schliessen, damit „offen" nicht endlos waechst und der Nenner ehrlich bleibt.
OFFEN_MAX_TAGE = 7
Z = 1.645


def _key(r: dict) -> str:
    return f"{r.get('teamId')}:{r.get('type')}:{str(r.get('kickoff') or '')[:10]}"


def vormerken(buch: dict, wettliste: list, now: datetime) -> int:
    """Wettliste ins Buch. Neue Zeilen bekommen erst*, bekannte offene nur letzt*. REIN bis auf `buch`."""
    zeilen = buch.setdefault("zeilen", [])
    idx = {z.get("key"): z for z in zeilen}
    neu = 0
    for r in wettliste or []:
        ko = _parse_ko(r.get("kickoff"))
        if not ko or ko <= now or r.get("trefferPct") is None:
            continue
        k = _key(r)
        z = idx.get(k)
        if z is None:
            z = {"key": k, "teamId": r.get("teamId"), "team": r.get("team"), "type": r.get("type"),
                 "serie": r.get("serie"), "length": r.get("length"), "gegner": r.get("gegner"),
                 "heim": r.get("heim"), "kickoff": r.get("kickoff"),
                 "league": r.get("league"), "leagueName": r.get("leagueName"),
                 "markt": r.get("markt"), "chanceAus": r.get("chanceAus"),
                 "erstPct": r.get("trefferPct"), "erstQuote": r.get("quote"),
                 "erstFair": r.get("fairQuote"), "erstGesehen": now.isoformat(),
                 "status": "offen"}
            zeilen.append(z)
            idx[k] = z
            neu += 1
        if z.get("status") == "offen":
            z["letztPct"], z["letztQuote"] = r.get("trefferPct"), r.get("quote")
            z["letztGesehen"] = now.isoformat()
    return neu


def _spiel(wm: dict, team_id, ko: datetime):
    """Das Spiel zum Anpfiff. `date` im Datensatz ist teils der LOKALE Tag (MLS: 2 von 510 Spielen
    weichen vom UTC-Tag des Anpfiffs ab) — deshalb auch die Nachbartage, Anpfiff-Tag zuerst."""
    for d in (0, -1, 1):
        fx = _fixture_fuer(wm, team_id, (ko + timedelta(days=d)).date().isoformat())
        if fx:
            return fx
    return None


def abrechnen(buch: dict, wm: dict, now: datetime) -> int:
    """Offene Zeilen mit fertigem Spiel abrechnen. Rendite je Einheit zur ERSTEN Quote."""
    n = 0
    for z in buch.get("zeilen") or []:
        if z.get("status") != "offen":
            continue
        ko = _parse_ko(z.get("kickoff"))
        if not ko or ko > now:
            continue
        fx = _spiel(wm, z.get("teamId"), ko)
        if fx and _fixture_finished(fx):
            # Die ID so uebergeben, wie sie im Spiel steht (int oder str) — streak_held vergleicht mit ==.
            tid = fx.get("home") if str(fx.get("home")) == str(z.get("teamId")) else fx.get("away")
            held = streak_held(z.get("type"), tid, fx)
            z["erfuellt"] = held
            z["status"] = "abgerechnet" if isinstance(held, bool) else "unaufloesbar"
        elif now - ko > timedelta(days=OFFEN_MAX_TAGE):
            z["erfuellt"] = None
            z["status"] = "unaufloesbar"
        else:
            continue
        q = z.get("erstQuote")
        if isinstance(z.get("erfuellt"), bool) and isinstance(q, (int, float)) and q > 1:
            z["rendite"] = round(q - 1, 4) if z["erfuellt"] else -1.0
        z["abgerechnetAm"] = now.isoformat()
        n += 1
    return n


def _mittel_grenzen(werte):
    if len(werte) < 2:
        return None, None
    m = sum(werte) / len(werte)
    sd = math.sqrt(sum((x - m) ** 2 for x in werte) / (len(werte) - 1))
    h = Z * sd / math.sqrt(len(werte))
    return m - h, m + h


def _teil(zeilen) -> dict:
    auf = [z for z in zeilen if z.get("status") == "abgerechnet" and isinstance(z.get("erfuellt"), bool)]
    n = len(auf)
    treffer = sum(1 for z in auf if z["erfuellt"])
    _e = [float(z["erstPct"]) for z in auf if isinstance(z.get("erstPct"), (int, float))]
    erw = sum(_e) / len(_e) if _e else None
    ren = [float(z["rendite"]) for z in auf if isinstance(z.get("rendite"), (int, float))]
    aus = {"n": n, "treffer": treffer,
           "unaufloesbar": sum(1 for z in zeilen if z.get("status") == "unaufloesbar"),
           "offen": sum(1 for z in zeilen if z.get("status") == "offen"),
           "trefferPct": round(100.0 * treffer / n, 1) if n else None,
           "erwartetPct": round(erw, 1) if erw is not None else None,
           "mitQuote": len(ren), "roiPct": round(100 * sum(ren) / len(ren), 1) if ren else None}
    if n < BILANZ_MIN_N:
        aus["urteil"] = "sammelt"
        aus["grund"] = f"{n} von {BILANZ_MIN_N} abgerechneten Wetten — darunter sagt der Vergleich nichts"
        return aus
    ug, og = _wilson(treffer, n), 1.0 - _wilson(n - treffer, n)
    aus["ugPct"], aus["ogPct"] = round(100 * ug, 1), round(100 * og, 1)
    if erw is None:
        aus["chance"] = "ohne Erwartung"
    elif ug * 100 > erw:
        aus["chance"] = "trifft öfter als angezeigt"
    elif og * 100 < erw:
        aus["chance"] = "trifft seltener als angezeigt"
    else:
        aus["chance"] = "stimmt"
    r_ug, r_og = _mittel_grenzen(ren) if len(ren) >= BILANZ_MIN_N else (None, None)
    if r_ug is not None:
        aus["roiUgPct"], aus["roiOgPct"] = round(100 * r_ug, 1), round(100 * r_og, 1)
        aus["geld"] = "trägt" if r_ug > 0 else ("verliert" if r_og < 0 else "offen")
    else:
        aus["geld"] = "ohne Quote" if not ren else "sammelt"
    aus["urteil"] = aus["chance"] + (" · Geld " + aus["geld"] if aus["geld"] not in ("ohne Quote",) else "")
    aus["grund"] = (f"getroffen {aus['trefferPct']} % ({aus['ugPct']}..{aus['ogPct']} %) gegen angezeigt "
                    f"{aus['erwartetPct']} %" + (f" · ROI {aus['roiPct']:+.1f} % ({aus['roiUgPct']:+.1f}..{aus['roiOgPct']:+.1f})"
                                                 if r_ug is not None else ""))
    return aus


def bilanz(zeilen) -> dict:
    """Gesamt + getrennt nach Markt-/Modell-Chance. REIN."""
    rows = [z for z in (zeilen or []) if isinstance(z, dict)]
    return {"gesamt": _teil(rows),
            "markt": _teil([z for z in rows if z.get("chanceAus") == "markt"]),
            "modell": _teil([z for z in rows if z.get("chanceAus") != "markt"])}


def _load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def main(now=None) -> None:
    now = now or datetime.now(timezone.utc)
    streaks = _load(STREAKS_FILE, {}) or {}
    wm = _load(D.data_file(), {}) or {}
    buch = _load(BUCH_FILE, {"zeilen": []})
    if not isinstance(buch, dict):
        buch = {"zeilen": []}
    neu = vormerken(buch, streaks.get("wettliste") or [], now)
    ab = abrechnen(buch, wm, now)
    buch["bilanz"] = bilanz(buch["zeilen"])
    buch["updatedAt"] = now.isoformat()
    BUCH_FILE.write_text(json.dumps(buch, ensure_ascii=False, indent=1), encoding="utf-8")
    g = buch["bilanz"]["gesamt"]
    print(f"📒 Serien-Wetten-Buch ({D.active_dataset()}): +{neu} vorgemerkt · {ab} abgerechnet · "
          f"{g['offen']} offen · {g['urteil']}: {g['grund']}")


if __name__ == "__main__":
    main()
