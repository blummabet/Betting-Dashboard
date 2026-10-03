#!/usr/bin/env python3
"""poly_wallet_clv_follow.py — vorangemeldetes Papierbuch: Wallets mit BELEGTEM CLV nachspielen,
aber nur, wenn wir hoechstens 1 Punkt schlechter einsteigen als sie (03.10.2026, Lucas: „Ja").

## Warum es das braucht
Die Poly-Gesamtschau vom 03.10. ergab zweierlei, das sich zu widersprechen scheint:
  · Von 560 Wallets mit >= 20 gewerteten Positionen schlagen 54 den Schlusskurs belegt
    (CLV-Untergrenze > 0, im in sich geschlossenen Fenster gerechnet). Per Zufall waeren ~28 zu
    erwarten. Es gibt also Koennen — schwach, aber messbar.
  · Das Nachspiel-Depot der Top-20 (Auswahl nach P&L) verliert: n=500, ROI −8,8 %.
Offen ist, ob man das Koennen MITNEHMEN kann. Dieses Buch prueft genau das, mit zwei Unterschieden
zum Top-20-Depot: Auswahl nach CLV-Untergrenze statt nach P&L, und ein Einstieg nur nahe am Preis
der Wallet.

## Zuschnitt (vor der ersten Zeile festgelegt, Register `poly-wallet-clv`)
  · Wallet: clvFenN >= MIN_N und CLV-Untergrenze (einseitig, z=1,645) > 0 — eingefroren beim Einstieg.
  · Position: vor Anpfiff, frisch (erstes Sehen <= FRISCH_MIN), Wallet-Einstieg (Ø /positions) bekannt,
    Sportart nicht gesperrt.
  · Unser Preis = aktueller Preis beim Sehen. Arm „nehmbar": unser Preis − Wallet-Einstieg <= 1 Punkt.
    Arm „zu spaet": mehr als 1 Punkt — wird GENAUSO abgerechnet. Er ist die Gegenprobe: zeigt er
    dasselbe, ist es nicht der Einstieg, der traegt.
  · je (Markt, Seite) EIN Play, erste qualifizierte Wallet gewinnt. Einsatz $10 Papier.
Setzt und sendet NICHTS.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from poly_shortlist_track import _age_days, _agg_one, _ok_price
from poly_slug_urteil import aufloesbar
from safe_write import write_json_atomic

BASE = Path(__file__).resolve().parent
WTRACK_FILE = "poly_wallet_track.json"
CLOSE_FILE = "poly_money_broad_close.json"
RES_FILE = "poly_resolutions.json"
SHORTLIST_FILE = "poly_shortlist_track.json"
BUCH_FILE = "poly_wallet_clv_follow.json"

MIN_N = int(os.environ.get("WALLET_CLV_MIN_N") or 20)
Z = 1.645
MAX_ABSTAND = 0.01          # 1 Punkt
FRISCH_MIN = 90.0           # aelter gesehene Positionen sind kein Einstieg mehr, den wir haetten
STAKE = 10.0
STALE_TAGE = 14.0
GESPERRT_FALLBACK = ("Cricket", "Kampfsport", "US-Sport")


def _now():
    return datetime.now(timezone.utc)


def _load(name, base=None, default=None):
    try:
        return json.loads(((base or BASE) / name).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def wallet_clv(score) -> dict | None:
    """{n, clv, ug} aus dem geschlossenen Fenster (clvFenN/clvFenSum/clvSqSum). REIN.

    NICHT aus `n`/`clvSumPP`: die zaehlen seit jeher, die Quadratsumme erst seit 02.09. — gemischt
    ergibt das eine kuenstlich kleine Streuung (der Fehler steht in poly_money_broad dokumentiert,
    und ich bin am 03.10. beim ersten Ueberschlag selbst hineingefallen: 120 statt 54 Wallets)."""
    s = score or {}
    n = int(s.get("clvFenN") or 0)
    if n < 2 or "clvSqSum" not in s or "clvFenSum" not in s:
        return None
    m = float(s["clvFenSum"]) / n
    var = max(0.0, (float(s["clvSqSum"]) - n * m * m) / (n - 1))
    return {"n": n, "clv": round(m, 3), "ug": round(m - Z * math.sqrt(var / n), 3)}


def qualifiziert(score, min_n=MIN_N) -> dict | None:
    q = wallet_clv(score)
    return q if q and q["n"] >= min_n and q["ug"] > 0 else None


# 03.10.2026, zweite Auswahl (Lucas: „wenn ein Wallet gut performt, mitschwimmen — trifft es zwei,
# drei Tage nichts, nach hinten reihen"). Gemessen vorab auf den Tagesdaten 17.09.-03.10.: Wallets
# mit 7-Tage-CLV > +1 Punkt lagen in den 4 Tagen danach bei +0,10 Punkten, neutrale bei −0,13,
# kalte bei −0,25. Die Richtung stimmt, der Abstand ist klein. Die Rotation passiert von selbst:
# `fenster7` rechnet poly_money_broad bei jedem Lauf neu, wer abkuehlt, faellt heraus.
HEISS_MIN_N = 8
HEISS_MIN_CLV = 1.0


def heiss(score) -> dict | None:
    f = (score or {}).get("fenster7") or {}
    n, clv = int(f.get("n") or 0), f.get("clv")
    if n >= HEISS_MIN_N and isinstance(clv, (int, float)) and clv > HEISS_MIN_CLV:
        return {"n7": n, "clv7": clv}
    return None


def update_buch(prev, wtrack, close, resolutions, gesperrt, now=None, stake=STAKE) -> dict:
    """Neue Plays oeffnen, Schlusskurs nachziehen, abrechnen. REIN."""
    now = now or _now()
    prev = prev if isinstance(prev, dict) else {}
    open_ = {k: dict(v) for k, v in (prev.get("open") or {}).items() if isinstance(v, dict)}
    settled = [dict(s) for s in (prev.get("settled") or []) if isinstance(s, dict)]
    gesehen = set(prev.get("gesehen") or [])
    scores = (wtrack or {}).get("scores") or {}
    zaehler = {"ohneEinstieg": 0, "gesperrt": 0, "alt": 0}

    # 1) neue Plays — je (key, side) einmal
    for pos in ((wtrack or {}).get("open") or {}).values():
        if not isinstance(pos, dict):
            continue
        key, side, w = pos.get("key"), pos.get("side"), pos.get("wallet")
        ok = f"{key}|{side}"
        if not key or side is None or ok in gesehen or ok in open_:
            continue
        q = qualifiziert(scores.get(w))
        h = heiss(scores.get(w))
        if not q and not h:
            continue
        if pos.get("sport") in gesperrt:
            zaehler["gesperrt"] += 1
            continue
        alter = _age_days(pos.get("firstTs"), now)
        if alter is None or alter * 1440 > FRISCH_MIN:
            zaehler["alt"] += 1
            continue
        if not ((pos.get("htkFirst") or 0) > 0):
            continue                                  # nur vor Anpfiff
        unser, ihr = pos.get("lastPrice"), pos.get("entryPrice")
        if not (_ok_price(unser) and _ok_price(ihr)):
            zaehler["ohneEinstieg"] += 1
            continue
        abstand = float(unser) - float(ihr)
        gesehen.add(ok)
        open_[ok] = {"key": key, "side": side, "cat": pos.get("sport"), "league": pos.get("league"),
                     "wallet": w, "belegt": bool(q), "heiss": bool(h),
                     "walletN": (q or {}).get("n"), "walletClv": (q or {}).get("clv"),
                     "walletUg": (q or {}).get("ug"), "clv7": (h or {}).get("clv7"),
                     "n7": (h or {}).get("n7"),
                     "walletEntry": round(float(ihr), 4), "entryPrice": round(float(unser), 4),
                     "abstandPP": round(abstand * 100, 2),
                     "arm": "nehmbar" if abstand <= MAX_ABSTAND else "zu_spaet",
                     "lastPrice": round(float(unser), 4), "htkAtEntry": pos.get("htkFirst"),
                     "firstTs": now.isoformat(), "stake": stake}

    # 2) Schlusskurs nachziehen (eingefrorener Close, sonst letzter Preis)
    for e in open_.values():
        cp = (((close or {}).get(e["key"]) or {}).get("prices") or {}).get(e["side"])
        if _ok_price(cp):
            e["lastPrice"] = round(float(cp), 4)

    # 3) abrechnen
    for ok in list(open_):
        e = open_[ok]
        r = (resolutions or {}).get(e["key"]) if isinstance(resolutions, dict) else None
        winner = (r or {}).get("winner")
        if winner and not aufloesbar(e["key"], e["side"], winner):
            winner = None
        if not winner:
            if (_age_days(e.get("firstTs"), now) or 0) > STALE_TAGE:
                del open_[ok]                          # unaufloesbar verfallen, kein Fake-Ergebnis
            continue
        entry, st = float(e["entryPrice"]), float(e.get("stake") or stake)
        win = e["side"] == winner
        settled.append(dict(e, result="win" if win else "loss", winner=winner,
                            pnl=round((st / entry - st) if win else -st, 2),
                            closePrice=e.get("lastPrice"),
                            clvPP=round((float(e.get("lastPrice") or entry) - entry) * 100, 2),
                            settledTs=now.isoformat()))
        del open_[ok]

    gesehen = sorted(gesehen)[-20000:]
    return {"updatedAt": now.isoformat(), "stake": stake, "regel": {
                "minN": MIN_N, "maxAbstandPP": MAX_ABSTAND * 100, "frischMin": FRISCH_MIN},
            "zaehler": zaehler, "open": open_, "settled": settled, "gesehen": gesehen,
            "agg": aggregate(settled)}


def aggregate(settled) -> dict:
    rows = [r for r in settled or [] if isinstance(r, dict) and r.get("result")]
    aus = {}
    # Auswahl x Einstieg — „belegt" (CLV-Untergrenze ueber alles) gegen „heiss" (7-Tage-Form).
    for auswahl in ("belegt", "heiss"):
        for arm in ("nehmbar", "zu_spaet"):
            a = [r for r in rows if r.get(auswahl, auswahl == "belegt") and r.get("arm") == arm]
            aus["%s_%s" % (auswahl, arm)] = _agg_one(a) if a else {"n": 0}
    for arm in ("nehmbar", "zu_spaet"):
        a = [r for r in rows if r.get("arm") == arm]
        aus[arm] = _agg_one(a) if a else {"n": 0}
        if a:
            aus[arm]["byCat"] = {c: _agg_one([r for r in a if r.get("cat") == c])
                                 for c in sorted({str(r.get("cat")) for r in a})}
    return aus


def main(base=None) -> int:
    base = base or BASE
    sl = _load(SHORTLIST_FILE, base)
    gesperrt = set((sl or {}).get("blockedCats") or GESPERRT_FALLBACK)
    buch = update_buch(_load(BUCH_FILE, base), _load(WTRACK_FILE, base), _load(CLOSE_FILE, base),
                       _load(RES_FILE, base), gesperrt)
    write_json_atomic(base / BUCH_FILE, buch, indent=1)
    a = buch["agg"]
    print("👛 Wallet-CLV-Nachspiel: %d offen · nehmbar %d abgerechnet · zu spaet %d · %s"
          % (len(buch["open"]), a["nehmbar"].get("n", 0), a["zu_spaet"].get("n", 0), buch["zaehler"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
