#!/usr/bin/env python3
"""
hz_finder.py — Halbzeit 0:0 in Spielen, die vor dem Anpfiff Tore oder einen Heimsieg erwarten liessen. 04.10.2026.

Lucas: „wenn zb inplay 0:0 steht zur Pause, es aber ein Over-2.5-Spiel war bzw. Home win … dann
2. Halbzeit ok zu wetten. Mach ich selbst oft, nur such ich die Spiele dann immer manuell."

WAS GEMESSEN IST (03.10.2026, Betfair-Ledger, Spiele mit HZ 0:0):
    alle                                   n=1.737   Tor in 2. HZ 78 %   Heimsieg 36 %
    Over 2.5 erwartet (Geld-Seite OVER, Quote <= 1,75)   n=504   Tor in 2. HZ 85 %  >=2 Tore 56 %
    Heimfavorit (Heimquote vor Anpfiff <= 1,60)          n=216   Heimsieg 63 %
Fuer den Heimsieg liess sich die HZ-Quote nachmessen (Live-Match-Odds in der Historie): der Markt
preist es ein — Quote sagt 55-65 %, getroffen 56-63 %, ROI je nach Schwelle -2 % bis +9 %, ab
19.09. +1 %. Fuer die Tore gibt es KEINE gespeicherte HZ-Quote. Ob 85 % mehr sind, als die
Over-0.5-Quote zur Pause sagt, ist also offen — genau das misst dieses Buch.

Jeder Fund wird zur Quote IM MOMENT DER PAUSE gebucht (Over 0.5 / Over 1.5 / Heimsieg) und
gegen den Endstand abgerechnet. Am Endstand gesucht, am Signalzeitpunkt gefeuert — dieser Fehler
hat am 03.10. zwei Kandidaten gekostet; hier gibt es keine Schlussquote, nur die Quote zur Pause.

Die Erwartung vor dem Spiel kommt aus denselben Quellen wie die Messung oben:
    Tore    betfair_track_state.json (eingefrorene letzte Vor-Anpfiff-Seite + Quote, O/U 2.5)
    Heim    betfair_history.json (letzte Vor-Anpfiff-Heimquote der Match Odds)
Serien kommen aus team_archiv.json (Betfair-Ergebnisse, auch kleine Ligen).

Ausgabe hz_finder.json (Money Map -> Reiter „⏸️ HZ 0:0"), Push je Lauf gebuendelt in den
Trades-Kanal (HZ_PUSH=0 schaltet ab). Urteil am Erzeuger.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
AUSGABE_FILE = "hz_finder.json"
SEEN_FILE = "hz_finder_seen.json"
TORE_MAX_QUOTE = 1.75
HEIM_MAX_QUOTE = 1.60
SPAET_MIN, SPAET_MAX = 46, 55          # 2. HZ laeuft schon, steht aber noch 0:0 (Lauf hat die Pause verpasst)
KOMMISSION = 0.02
VERFALL_TAGE = 3
KEEP = 3000
MINDEST_N = 100
Z = 1.645
UG_MIN_N = 30
PUSH_DECKEL = 8
WETTEN = {"tore": ("over05", "over15"), "heim": ("heim",)}
WETT_TEXT = {"over05": "Over 0.5 (Tor in 2. HZ)", "over15": "Over 1.5 (2+ Tore)", "heim": "Heimsieg"}


def _laden(pfad, leer=None):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return leer


def _runner(m, markt, test):
    for r in (((m.get("markets") or {}).get(markt) or {}).get("runners") or []):
        if test(str(r.get("name") or "")) and isinstance(r.get("odd"), (int, float)) and r["odd"] > 1:
            return float(r["odd"])
    return None


def vor_heimquote(hist_punkte):
    """Letzte Vor-Anpfiff-Heimquote aus betfair_history (Punkte ohne Minute). REIN."""
    best = None
    for p in hist_punkte or []:
        if not isinstance(p, dict) or p.get("min") is not None:
            continue
        hw = (p.get("mo") or {}).get("hw")
        if isinstance(hw, (int, float)) and hw > 1 and (best is None or str(p.get("ts")) >= str(best[0])):
            best = (p.get("ts"), float(hw))
    return best[1] if best else None


def phase(li):
    """'HZ' | '2.HZ' | None — nur bei 0:0. REIN."""
    if not li or li.get("finished") or li.get("goal_v1") != 0 or li.get("goal_v2") != 0:
        return None
    if li.get("is_ht"):
        return "HZ"
    t = li.get("time")
    if isinstance(t, (int, float)) and SPAET_MIN <= t <= SPAET_MAX:
        return "2.HZ"
    return None


def kandidat(m, state_pend, hist_punkte, archiv=None):
    """Ein Spiel -> Fund oder None. REIN."""
    li = m.get("liveInfo") or {}
    ph = phase(li)
    if not ph:
        return None
    sig = ((state_pend or {}).get("signals") or {}).get("Over/Under 2.5 Goals") or {}
    gruppen, vor = [], {}
    if sig.get("fav") == "OVER" and isinstance(sig.get("odd"), (int, float)) and sig["odd"] <= TORE_MAX_QUOTE:
        gruppen.append("tore")
        vor["over25"] = sig["odd"]
    hw = vor_heimquote(hist_punkte)
    if hw is not None and hw <= HEIM_MAX_QUOTE:
        gruppen.append("heim")
        vor["heim"] = hw
    if not gruppen:
        return None
    home = m.get("home")
    quoten = {"over05": _runner(m, "Over/Under 0.5 Goals", lambda s: s.startswith("Over")),
              "over15": _runner(m, "Over/Under 1.5 Goals", lambda s: s.startswith("Over")),
              "heim": _runner(m, "Match Odds", lambda s: s == str(home))}
    serie = None
    if archiv is not None:
        import team_archiv
        serie = {"heim": team_archiv.serie(archiv, home), "gast": team_archiv.serie(archiv, m.get("away"))}
    return {"k": "hz:%s" % m.get("matchId"), "matchId": str(m.get("matchId")), "home": home,
            "away": m.get("away"), "league": m.get("league"), "country": m.get("country"),
            "kickoff": m.get("kickoff"), "phase": ph, "minute": li.get("time"),
            "gruppen": gruppen, "vor": vor, "quoten": quoten, "serie": serie}


# ── Abrechnen ───────────────────────────────────────────────────────────────────────────────
def ergebnis(ft):
    h, a = ft
    return {"over05": h + a >= 1, "over15": h + a >= 2, "heim": h > a}


def abrechnen(eintraege, endstaende, jetzt) -> list:
    """endstaende: matchId -> (ft, ht). REIN."""
    aus = []
    for e in eintraege:
        if e.get("status") != "pending":
            aus.append(e)
            continue
        e = dict(e)
        es = endstaende.get(e["matchId"])
        if es and es[0]:
            ft, ht = es
            if e.get("phase") == "HZ" and ht is not None and list(ht) != [0, 0]:
                e["status"] = "ungueltig"          # Feed sagte 0:0 zur Pause, das Ergebnis nicht
                e["grund"] = "HZ laut Ergebnis %s" % ht
            else:
                erg = ergebnis(ft)
                e["status"], e["ft"], e["wetten"] = "abgerechnet", ft, {}
                for g in e.get("gruppen") or []:
                    for w in WETTEN[g]:
                        q = (e.get("quoten") or {}).get(w)
                        e["wetten"][w] = {"win": erg[w], "quote": q,
                                          "r": (round((q - 1) * (1 - KOMMISSION), 4) if erg[w] else -1.0) if q else None}
        else:
            try:
                alt = datetime.fromisoformat(str(e.get("gebuchtAt")).replace("Z", "+00:00"))
            except ValueError:
                alt = jetzt
            if jetzt - alt > timedelta(days=VERFALL_TAGE):
                e["status"] = "unaufgeloest"
        aus.append(e)
    return aus


def kennzahlen(paare) -> dict:
    """paare: [(win, quote, r)]. REIN."""
    n = len(paare)
    if not n:
        return {"n": 0, "trefferPct": None, "erwartetPct": None, "roi": None, "ug": None, "og": None}
    rs = [p[2] for p in paare]
    m = sum(rs) / n
    k = {"n": n, "trefferPct": round(100 * sum(1 for p in paare if p[0]) / n, 1),
         "erwartetPct": round(100 * sum(1 / p[1] for p in paare) / n, 1),
         "roi": round(100 * m, 1), "ug": None, "og": None}
    if n >= UG_MIN_N:
        se = math.sqrt(sum((r - m) ** 2 for r in rs) / (n - 1) / n)
        k["ug"], k["og"] = round(100 * (m - Z * se), 1), round(100 * (m + Z * se), 1)
    return k


def urteil(k) -> str:
    if k["n"] < MINDEST_N or k["ug"] is None:
        return "sammelt"
    if k["ug"] > 0:
        return "traegt"
    if k["og"] < 0:
        return "traegt nicht"
    return "offen"


def bericht(eintraege) -> dict:
    aus = {}
    for g, wetten in WETTEN.items():
        for w in wetten:
            paare = [(x["win"], x["quote"], x["r"]) for e in eintraege
                     if e.get("status") == "abgerechnet" and g in (e.get("gruppen") or ())
                     for ww, x in (e.get("wetten") or {}).items() if ww == w and x.get("r") is not None]
            k = kennzahlen(paare)
            aus["%s/%s" % (g, w)] = {"gruppe": g, "wette": w, "text": WETT_TEXT[w], **k, "urteil": urteil(k)}
    return aus


# ── Push ────────────────────────────────────────────────────────────────────────────────────
def _esc(s):
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _serie_txt(s):
    if not s:
        return "–"
    return "%s · O2.5 %d/%d · Ø %.1f Tore" % (s["form"], s["over25"], s["n"], s["toreSchnitt"])


def nachricht(funde, bericht_=None) -> str:
    t = ["⏸️ <b>HZ 0:0</b> · vor dem Spiel war mehr erwartet\n━━━━━━━━━━━━━━\n"]
    for f in funde[:PUSH_DECKEL]:
        q, v = f.get("quoten") or {}, f.get("vor") or {}
        erw = []
        if "tore" in f["gruppen"]:
            erw.append("Over 2.5 @%.2f" % v["over25"])
        if "heim" in f["gruppen"]:
            erw.append("Heim @%.2f" % v["heim"])
        jetzt = []
        for w, lab in (("over05", "O0.5"), ("over15", "O1.5"), ("heim", "Heim")):
            if q.get(w):
                jetzt.append("%s @%.2f" % (lab, q[w]))
        t.append("<b>%s</b> v <b>%s</b>%s\n<i>%s</i>\nvorher: %s\njetzt: %s\n"
                 % (_esc(f["home"]), _esc(f["away"]),
                    "" if f["phase"] == "HZ" else " · <i>%s' (2. HZ läuft)</i>" % f.get("minute"),
                    _esc(str(f.get("league") or "")[:40]), " · ".join(erw), " · ".join(jetzt) or "–"))
        s = f.get("serie") or {}
        if s.get("heim") or s.get("gast"):
            t.append("Serie H: %s\nSerie G: %s\n" % (_serie_txt(s.get("heim")), _serie_txt(s.get("gast"))))
        t.append("\n")
    if len(funde) > PUSH_DECKEL:
        t.append("<i>+%d weitere in der Money Map → ⏸️ HZ 0:0</i>\n" % (len(funde) - PUSH_DECKEL))
    b = (bericht_ or {}).get("tore/over05") or {}
    if b.get("n"):
        t.append("🔬 <i>Buch Tor in 2. HZ: %d abgerechnet · %s %% getroffen, Quote sagte %s %% · ROI %+.1f %%</i>"
                 % (b["n"], b["trefferPct"], b["erwartetPct"], b["roi"]))
    else:
        t.append("🔬 <i>Testlauf: jeder Fund wird zur Quote der Pause gebucht — Urteil ab n=%d.</i>" % MINDEST_N)
    return "".join(t)


# ── Lauf ────────────────────────────────────────────────────────────────────────────────────
def main(base_dir=BASE, jetzt=None, senden=None) -> int:
    jetzt = jetzt or datetime.now(timezone.utc)
    pj = lambda n: os.path.join(base_dir, n)
    import betfair_track_store
    import team_archiv
    archiv = team_archiv.aktualisieren(base_dir, jetzt)
    prices = _laden(pj("betfair_prices.json"), {}) or {}
    pend = (_laden(pj("betfair_track_state.json"), {}) or {}).get("pending") or {}
    hist = _laden(pj("betfair_history.json"), {}) or {}
    stand = _laden(pj(AUSGABE_FILE), {}) or {}
    eintraege = list(stand.get("eintraege") or [])
    haben = {e.get("k") for e in eintraege}

    import betfair_alerts as BA          # Seen mit Runner-Spiegel (~/.cocobet_state)
    seen = BA._load_seen(pj(SEEN_FILE))
    neu = []
    for m in prices.get("matches") or []:
        mid = str(m.get("matchId"))
        f = kandidat(m, pend.get(mid), hist.get(mid), archiv)
        if not f or f["k"] in haben or f["k"] in seen:
            continue
        f["gebuchtAt"], f["status"] = jetzt.isoformat(), "pending"
        eintraege.append(f)
        haben.add(f["k"])
        neu.append(f)

    endst = {}
    for z in betfair_track_store.load(pj("betfair_track_results.json")):
        if isinstance(z, dict) and z.get("ft"):
            endst[str(z.get("matchId"))] = (z.get("ft"), z.get("ht"))
    for mid, s in archiv.items():
        endst.setdefault(mid, (s.get("ft"), s.get("ht")))
    eintraege = abrechnen(eintraege, endst, jetzt)[-KEEP:]
    ber = bericht(eintraege)

    grenze = (jetzt - timedelta(hours=36)).isoformat()
    aus = {"updatedAt": jetzt.isoformat(),
           "regel": {"toreMaxQuote": TORE_MAX_QUOTE, "heimMaxQuote": HEIM_MAX_QUOTE,
                     "kommission": KOMMISSION, "mindestN": MINDEST_N},
           "bericht": ber,
           "zuletzt": [e for e in reversed(eintraege) if str(e.get("gebuchtAt") or "") >= grenze][:60],
           "eintraege": eintraege}
    from pathlib import Path
    from safe_write import write_json_atomic
    write_json_atomic(Path(base_dir) / AUSGABE_FILE, aus, indent=None)   # Buch ZUERST, dann senden

    for f in neu:
        seen[f["k"]] = jetzt.isoformat()
    alt = (jetzt - timedelta(days=VERFALL_TAGE)).isoformat()
    seen = {k: v for k, v in seen.items() if str(v) >= alt}
    BA._save_seen(pj(SEEN_FILE), seen)
    if neu and os.environ.get("HZ_PUSH", "1") != "0":
        if senden is None:
            from telegram_trades import send_trades_message as senden
        senden(nachricht(neu, ber))
    print("[hz_finder] %d neu, %d im Buch, Tor 2.HZ: %s" % (len(neu), len(eintraege), ber["tore/over05"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
