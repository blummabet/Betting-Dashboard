#!/usr/bin/env python3
"""
poly_money_accuracy.py — Liegt das Poly-Geld richtig? (19.07.2026, Lucas).

## Die Frage

Wir kennen für jeden Poly-Markt den PREIS und die GELD-VERTEILUNG (wie viel USDC auf jeder Seite
liegt). Der Preis ist die letzte gehandelte Meinung; das Geld ist die aufgelaufene Positionierung.
Auf einem CLOB können die auseinanderlaufen — viel Geld sitzt auf einer Seite, während der Preis
woanders steht. Frage: **gewinnt die Seite mit dem Geld auch?** Und schärfer: **sagt das Geld mehr
als der Preis, oder ist es nur Rauschen, das der Preis eh schon enthält?**

Das ist der empirische Test unserer eigenen These „Polymarket ist die Trade-Gegenseite, kein
Sharp-Anker". Liegt das Geld systematisch richtig → es ist ein Signal. Liegt es nicht besser als
der Preis → bestätigt, dass es dummes Geld ist, das wir faden dürfen.

## Wie gemessen wird — zwei Schritte

1. **Einfrieren (`capture`)**: Die Geld-Verteilung ist flüchtig (Snapshot). Wie bei den
   Closing-Lines frieren wir sie NAH AM ANPFIFF ein (`{ds}_poly_money_close.json`) — pro Ausgang
   den Geld-Anteil UND den Poly-Preis. So haben wir eine faire, zeitkonsistente Momentaufnahme.
2. **Auflösen (`evaluate`)**: gegen den Ausgang. Metriken:
   · Geld-Mehrheit-Trefferquote: gewinnt die Seite mit dem meisten Geld?
   · Preis-Favorit-Trefferquote: die Baseline (gewinnt der günstigste Preis?).
   · **Brier Geld vs. Brier Preis**: wer ist besser kalibriert (niedriger = besser)? DAS ist die
     eigentliche Antwort — ist das Geld schärfer als der Preis oder nicht.
   · Uneinigkeits-Bucket: wenn Geld-Favorit ≠ Preis-Favorit, wer gewinnt öfter? Der reinste Test.

⚠️ Daten-Hunger: es zählt nur, was wir SEIT dem Einfrieren gesammelt haben. Anfangs winzige
Stichprobe — Urteil erst über Wochen, wie beim Wallet-Track-Record. Read-only, kein Geld.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).resolve().parent

CAPTURE_WINDOW_H = 3.0   # so nah am Anpfiff frieren wir die Geld-Verteilung ein
MIN_TOTAL_USD    = 5_000  # dünner Markt → Verteilung nicht aussagekräftig
_OUT = ("home", "draw", "away")


def _now():
    return datetime.now(timezone.utc)


def _norm3(vals: dict):
    """{home,draw,away} → faire Wahrscheinlichkeiten (Summe 1). Fehlende Seite = 0."""
    xs = {k: float(vals.get(k) or 0) for k in _OUT}
    s = sum(xs.values())
    if s <= 0:
        return None
    return {k: v / s for k, v in xs.items()}


def capture(smartmoney: dict, prices: dict, frozen: dict, now=None) -> dict:
    """Geld-Verteilung + Preis nah am Anpfiff einfrieren. REIN.

    Aktualisiert bis zum Anpfiff immer den KLASSENBESTEN (dichtesten) Snapshot — so steht am Ende
    die ehrlichste Nah-am-Anpfiff-Momentaufnahme, nicht ein 3h-alter Zwischenstand."""
    now = now or _now()
    out = dict(frozen or {})
    pmap = (prices or {}).get("prices") or {}

    for key, m in (smartmoney.get("matches") or {}).items():
        htk = m.get("hoursToKickoff")
        try:
            htk = float(htk)
        except (TypeError, ValueError):
            continue
        if not (0 < htk <= CAPTURE_WINDOW_H):
            continue                      # nur im Anpfiff-Fenster, nach Anpfiff nicht mehr anfassen
        try:
            total = float(m.get("totalUsd") or 0)
        except (TypeError, ValueError):
            total = 0.0
        if total < MIN_TOTAL_USD:
            continue

        prev = out.get(key)
        if prev is not None and prev.get("hoursToKickoff", 99) <= htk:
            continue                      # wir haben schon einen dichteren Snapshot

        oc = m.get("outcomes") or {}
        shares = {k: (oc.get(k) or {}).get("share") for k in _OUT}
        pe = pmap.get(key) or {}
        prices_oc = {"home": pe.get("hw"), "draw": pe.get("dr"), "away": pe.get("aw")}
        out[key] = {
            "shares": {k: shares.get(k) for k in _OUT},
            "prices": prices_oc,
            "totalUsd": round(total),
            "hoursToKickoff": round(htk, 2),
            "capturedAt": now.isoformat(),
        }
    return out


def evaluate(frozen: dict, results: dict) -> dict:
    """Eingefrorene Geld-/Preis-Verteilungen gegen den Ausgang. REIN.

    results: {matchKey: "home"|"draw"|"away"}  (Gewinner-Ausgang)."""
    n = 0
    money_hit = price_hit = 0
    brier_money = brier_price = 0.0
    disagree = {"n": 0, "moneyWon": 0, "priceWon": 0, "neither": 0}
    rows = []

    for key, f in (frozen or {}).items():
        winner = results.get(key)
        if winner not in _OUT:
            continue
        mp = _norm3(f.get("shares") or {})
        pp = _norm3(f.get("prices") or {})
        if not mp or not pp:
            continue
        n += 1
        onehot = {k: (1.0 if k == winner else 0.0) for k in _OUT}
        brier_money += sum((mp[k] - onehot[k]) ** 2 for k in _OUT)
        brier_price += sum((pp[k] - onehot[k]) ** 2 for k in _OUT)

        money_fav = max(_OUT, key=lambda k: mp[k])
        price_fav = max(_OUT, key=lambda k: pp[k])
        m_ok, p_ok = (money_fav == winner), (price_fav == winner)
        money_hit += m_ok
        price_hit += p_ok
        if money_fav != price_fav:
            disagree["n"] += 1
            if m_ok:
                disagree["moneyWon"] += 1
            elif p_ok:
                disagree["priceWon"] += 1
            else:
                disagree["neither"] += 1
        rows.append({"key": key, "winner": winner, "moneyFav": money_fav, "priceFav": price_fav,
                     "moneyShare": round(mp[money_fav], 3), "priceProb": round(pp[price_fav], 3),
                     "moneyOK": m_ok, "priceOK": p_ok, "totalUsd": f.get("totalUsd")})

    if n == 0:
        return {"n": 0, "verdict": "zu wenig Daten"}

    bm, bp = brier_money / n, brier_price / n
    # Niedrigerer Brier = besser kalibriert. Marge, damit Rauschen kein Urteil auslöst.
    if bm < bp - 0.01:
        verdict = "geld_schaerfer"       # Geld sagt mehr als der Preis → echtes Signal
    elif bm > bp + 0.01:
        verdict = "preis_besser"         # Geld schlechter als Preis → dummes Geld, faden ok
    else:
        verdict = "gleichauf"            # Geld schon im Preis → kein Zusatznutzen

    return {
        "n": n,
        "moneyHitRate": round(money_hit / n, 3),
        "priceHitRate": round(price_hit / n, 3),
        "brierMoney": round(bm, 4),
        "brierPrice": round(bp, 4),
        "disagree": disagree,
        "verdict": verdict,
        "rows": sorted(rows, key=lambda r: -(r.get("totalUsd") or 0))[:40],
    }


# ── Ergebnis-Lookup ──────────────────────────────────────────────────────────

def results_lookup(data: dict) -> dict:
    """{homeId-awayId: winner} aus den aufgelösten Fixtures (groups + koFixtures)."""
    out = {}
    fixtures = []
    for g in (data.get("groups") or {}).values():
        fixtures += g.get("fixtures") or []
    fixtures += data.get("koFixtures") or []
    for fx in fixtures:
        r = fx.get("result") or {}
        if r.get("status") not in ("FT", "AET", "PEN"):
            continue
        hs, as_ = r.get("home_score"), r.get("away_score")
        if hs is None or as_ is None:
            continue
        winner = "home" if hs > as_ else "away" if as_ > hs else "draw"
        out[f"{fx.get('home')}-{fx.get('away')}"] = winner
    return out


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    sm = _load(D.file("wm_poly_smartmoney.json", "liga_poly_smartmoney.json").name)
    pr = _load(D.file("wm_poly_prices.json", "liga_poly_prices.json").name)
    data = _load(D.data_file().name)

    close_file = D.file("wm_poly_money_close.json", "liga_poly_money_close.json")
    frozen = capture(sm, pr, _load(close_file.name)) if sm else _load(close_file.name)
    close_file.write_text(json.dumps(frozen, ensure_ascii=False, indent=1), encoding="utf-8")

    rep = evaluate(frozen, results_lookup(data))
    rep["dataset"] = D.active_dataset()
    rep["generatedAt"] = _now().isoformat()
    out = D.file("wm_poly_money_accuracy.json", "liga_poly_money_accuracy.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"=== Liegt das Poly-Geld richtig? ({rep['dataset'].upper()}) ===")
    print(f"Eingefroren: {len(frozen)} Märkte · aufgelöst: {rep['n']}")
    if rep["n"]:
        print(f"Geld-Mehrheit trifft: {rep['moneyHitRate']*100:.0f}%  ·  "
              f"Preis-Favorit trifft: {rep['priceHitRate']*100:.0f}%")
        print(f"Brier Geld {rep['brierMoney']} vs. Preis {rep['brierPrice']}  →  {rep['verdict']}")
        d = rep["disagree"]
        if d["n"]:
            print(f"Uneinig ({d['n']}): Geld gewann {d['moneyWon']}, Preis {d['priceWon']}")
    print(f"💾 {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
