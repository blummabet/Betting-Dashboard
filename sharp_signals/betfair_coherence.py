"""
sharp_signals/betfair_coherence.py — Markt-KOHÄRENZ als Sharp-Signal (29.07.2026, Lucas v5-Idee).

Anders als `betfair_money` (bewertet die Geld-VERTEILUNG), fragt dieses Signal, ob der Pick-Markt
mit dem Rest der Betfair-Märkte desselben Spiels KOHÄRENT ist. Es fittet ein Poisson-Tor-λ an die
Über/Unter-Leiter (und Supremacy an die de-viggten 1X2-Fairs) und leitet daraus die faire
Wahrscheinlichkeit für den Pick-Markt ab. Weicht der gehandelte Preis von dieser modell-impliziten
Wahrscheinlichkeit ab, ist der Markt in sich inkonsistent — genau dort liegt oft die Kante.

Nur für Über/Unter- und BTTS-Picks: 1X2 ist ans Modell geankert (Supremacy wird AN die 1X2-Fairs
gefittet) → dort gäbe es per Konstruktion keine Abweichung, also None.

„Hart"-Bewusstsein: liegt eine echte arithmetische Leiter-Verletzung (P(Ü höher) > P(Ü niedriger))
in der Leiter, ist das ein modellfreier Widerspruch → confidence-Bonus.

GLOBAL lernt die Lernschleife das Signalgewicht generisch (wie jedes Signal, via signal_weights.json).
Kein eigener Track-Record — betfair_track_record.json misst das GELD-Folgen, nicht die Preis-Kohärenz.

Context erwartet:
  betfair_snapshot: der rohe Betwatch-Match-Dict (von generate_wm_picks per Namens-Matching gesetzt),
                    inkl. `mo.fair` (de-viggte 1X2) und `markets` mit der Ü/U-Leiter. Fehlt → None.
"""
from __future__ import annotations
import math
from typing import Optional
from sharp_signals.base import Signal, SignalResult
from sharp_signals.betfair_money import _pick_target

OU_LADDER   = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5]
MIN_MONEY_EUR = 2000.0   # Pick-Markt-Geld mind. so hoch, sonst nicht handelbar
MIN_EDGE      = 0.04     # |Modell-Prob − Markt-Prob| mind. so groß
SCALE         = 22.0     # Edge 0.10 → 2.2pp
MAX_PP        = 3.0      # Modell-Signal bewusst kleiner gedeckelt als Geld-Signal
MIN_RUNGS     = 3        # so viele bepreiste Ü/U-Sprossen für einen belastbaren λ-Fit

# ── Fit-Schranke (06.09.2026) ───────────────────────────────────────────────────────────────
# Gemessen ueber die 119 Betfair-Matches mit Ue/U-Leiter:
#
#     r(RMSE des Poisson-Fits, groesste gemeldete "Kante") = +0,985
#
# Die "Kante" dieses Signals WAR zu 97 % der eigene Misfit. Wo unser Ein-Lambda-Poisson die
# Leiter nicht beschreiben kann (Bundesliga 2, Segunda, Thai League 2: RMSE 6-14 pp), meldete
# es Abweichungen von 12-29 pp — und `rmse` senkte nur die `confidence`, blockte nie den
# `score`. Ein Modell, das den Markt nicht abbilden kann, sprach ihm Inkohaerenz zu.
# Das ist Bug-Klasse 5: eine Metrik, die sich selbst beurteilt.
#
# Die Schranke faellt nicht nach Geschmack, sondern aus der Messung:
#
#     RMSE <= 0,02  ->  84 Spiele,  0 davon mit "Kante" >= 4 pp   (groesste 3,9 pp)
#     RMSE <= 0,03  ->  90 Spiele,  5 davon
#     RMSE <= 0,06  -> 106 Spiele, 21 davon
#
# Wo wir die Leiter beschreiben koennen, stimmen wir mit ihr ueberein. Das ist der eigentliche
# Befund: **die Betfair-Tormarkt-Leiter ist auf unserer Aufloesung arbitragefrei.** Mit dieser
# Schranke wird das Signal fast nie feuern — richtigerweise. Ein Signal, das schweigt, weil es
# nachgesehen und nichts gefunden hat, ist etwas anderes als eines, das nicht hinsehen konnte.
MAX_RMSE      = 0.02     # schlechter Fit -> KEIN Urteil (nicht: schwaches Urteil)
MIN_REST_RUNGS = 4       # so viele ANDERE Sprossen muessen das Lambda tragen (s. unten)

# ── Leave-one-out (06.09.2026) ──────────────────────────────────────────────────────────────
# Die Schranke allein hatte einen zweiten Fehler in sich: sie fittet Lambda ueber ALLE Sprossen
# — auch ueber die, gegen die anschliessend geprueft wird. Eine echte Fehlbepreisung zieht das
# Lambda zu sich, verschlechtert den RMSE und blockt damit ihre eigene Entdeckung.
#
# Nachgerechnet an einer sauberen Poisson-Leiter mit EINER um 7 pp verschobenen Sprosse:
#   voller Fit  -> RMSE 0,0249  ->  geblockt, Kante unsichtbar
#   ohne die geprueigte Sprosse -> RMSE 0,00000, Kante +7,00 pp  ->  gefunden
#
# Deshalb: Lambda aus den ANDEREN Sprossen, dann die geprueigte dagegen halten. Am echten
# Betfair-Bestand (633 Sprossen aus 150 Spielen): 234 mit zu grobem Rest-Fit aussortiert,
# **8 echte Kanten >= 4 pp** uebrig — alle in duennen Ligen (Kasachstan, Litauen, Norwegen 2,
# Estland), **keine einzige in den Top 5**. Der volle Fit fand null.
#
# MIN_REST_RUNGS = 4, weil ein Rest von genau MIN_RUNGS unterbestimmt ist: er saugt die
# Verzerrung ins Lambda und meldet sie als Kante (an der alten Test-Fixture nachgewiesen).


def _devig2(a, b) -> Optional[float]:
    if not (isinstance(a, (int, float)) and isinstance(b, (int, float)) and a > 1 and b > 1):
        return None
    ia, ib = 1.0 / a, 1.0 / b
    return ia / (ia + ib)


def _pois(k: int, l: float) -> float:
    p = math.exp(-l)
    for i in range(1, k + 1):
        p *= l / i
    return p


def _pois_over(n: float, l: float) -> float:
    cum = 0.0
    for k in range(0, int(math.floor(n)) + 1):
        cum += _pois(k, l)
    return 1.0 - cum


def _market_vol(mk: dict) -> float:
    return sum((r.get("vol") or 0.0) for r in (mk.get("runners") or []))


def _runner(mk: dict, test) -> Optional[dict]:
    for r in (mk.get("runners") or []):
        if test(str(r.get("name") or "")):
            return r
    return None


def _ou_rungs(markets: dict) -> dict:
    out = {}
    for n in OU_LADDER:
        mk = markets.get("Over/Under %s Goals" % n)
        if not mk:
            continue
        o = _runner(mk, lambda s: s.startswith("Over"))
        u = _runner(mk, lambda s: s.startswith("Under"))
        p = _devig2(o and o.get("odd"), u and u.get("odd"))
        if p is not None:
            out[n] = p
    return out


def _fit_lambda(rungs: dict):
    ks = list(rungs.keys())
    if len(ks) < 2:
        return None
    best = None
    l = 0.20
    while l <= 6.60:
        e = 0.0
        for n in ks:
            d = _pois_over(n, l) - rungs[n]
            e += d * d
        if best is None or e < best[1]:
            best = (round(l, 2), e, math.sqrt(e / len(ks)))
        l += 0.01
    return best  # (lambda, sse, rmse)


def _outcome(lh: float, la: float, N: int = 12):
    ph = [_pois(i, lh) for i in range(N + 1)]
    pa = [_pois(i, la) for i in range(N + 1)]
    h = d = a = 0.0
    for i in range(N + 1):
        for j in range(N + 1):
            p = ph[i] * pa[j]
            if i > j:
                h += p
            elif i == j:
                d += p
            else:
                a += p
    return h, d, a


def _fit_supremacy(lam: float, fair: dict):
    if not lam or not fair:
        return None
    fh, fa = fair.get("home"), fair.get("away")
    if not (isinstance(fh, (int, float)) and isinstance(fa, (int, float))):
        return None
    best = None
    s = -3.2
    while s <= 3.2:
        lh, la = (lam + s) / 2.0, (lam - s) / 2.0
        if lh > 0.01 and la > 0.01:
            oh, od, oa = _outcome(lh, la)
            e = (oh - fh) ** 2 + (oa - fa) ** 2
            if best is None or e < best[1]:
                best = ((round(s, 2), lh, la), e)
        s += 0.02
    return best[0] if best else None  # (s, lh, la)


def _btts_p(lh: float, la: float) -> float:
    return (1 - math.exp(-lh)) * (1 - math.exp(-la))


def _ladder_has_hard_conflict(rungs: dict) -> bool:
    ks = sorted(rungs.keys())
    for i in range(len(ks) - 1):
        if (rungs[ks[i + 1]] - rungs[ks[i]]) > 0.004:   # mehr Tore wahrscheinlicher als weniger
            return True
    return False


class BetfairCoherenceSignal(Signal):
    def name(self) -> str:
        return "betfair_coherence"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        bf = context.get("betfair_snapshot")
        if not bf:
            return None
        target = _pick_target(pick.get("market", ""))
        if not target:
            return None
        market_name, tok = target
        if tok in ("H", "A", "D"):
            return None   # 1X2 ist ans Modell geankert → keine Kohärenz-Kante

        markets = bf.get("markets") or {}
        rungs = _ou_rungs(markets)
        if len(rungs) < MIN_RUNGS:
            return None

        # Lambda OHNE die Sprosse, gegen die gleich geprueft wird (s. Kopf). Fuer BTTS gibt es
        # keine eigene Sprosse — dort traegt die ganze Leiter.
        _eigene = None
        if tok in ("OVER", "UNDER"):
            try:
                _eigene = float(market_name.split("Over/Under ")[1].split(" Goals")[0])
            except Exception:
                return None
        _basis = {l: p for l, p in rungs.items() if l != _eigene} if _eigene is not None else rungs
        _min = MIN_REST_RUNGS if _eigene is not None else MIN_RUNGS
        if len(_basis) < _min:
            return None
        fit = _fit_lambda(_basis)
        if not fit:
            return None
        lam, _sse, rmse = fit
        # Ohne brauchbaren Fit hat das Modell keine Grundlage, den Markt falsch zu nennen.
        # Vorher senkte ein schlechter Fit nur die confidence — der score lief voll durch,
        # und die gemeldete "Kante" war zu 97 % der eigene Misfit (r = +0,985).
        if not isinstance(rmse, (int, float)) or rmse > MAX_RMSE:
            return None

        pick_mk = markets.get(market_name)
        if not pick_mk:
            return None
        total = _market_vol(pick_mk)
        if total < MIN_MONEY_EUR:
            return None

        model_prob = None
        market_prob = None
        detail = ""

        if tok in ("OVER", "UNDER"):
            line = _eigene
            o = _runner(pick_mk, lambda s: s.startswith("Over"))
            u = _runner(pick_mk, lambda s: s.startswith("Under"))
            mkt_over = _devig2(o and o.get("odd"), u and u.get("odd"))
            if mkt_over is None:
                return None
            model_over = _pois_over(line, lam)
            if tok == "OVER":
                model_prob, market_prob = model_over, mkt_over
            else:
                model_prob, market_prob = 1 - model_over, 1 - mkt_over
            detail = "Ü/U %.1f" % line

        else:  # BTTS YES/NO
            fair = (bf.get("mo") or {}).get("fair")
            sup = _fit_supremacy(lam, fair)
            if not sup:
                return None
            _s, lh, la = sup
            y = _runner(pick_mk, lambda s: s.lower().startswith("yes"))
            n = _runner(pick_mk, lambda s: s.lower().startswith("no"))
            mkt_yes = _devig2(y and y.get("odd"), n and n.get("odd"))
            if mkt_yes is None:
                return None
            model_yes = _btts_p(lh, la)
            if tok == "YES":
                model_prob, market_prob = model_yes, mkt_yes
            else:
                model_prob, market_prob = 1 - model_yes, 1 - mkt_yes
            detail = "BTTS"

        edge = model_prob - market_prob        # + = Modell haelt den Pick fuer wahrscheinlicher als der Preis
        if abs(edge) < MIN_EDGE:
            return None

        score = max(-MAX_PP, min(MAX_PP, edge * SCALE))

        fit_q = max(0.0, 1.0 - min(1.0, rmse / 0.06))
        vol_q = min(1.0, total / 15000.0)
        rung_q = min(1.0, (len(rungs) - MIN_RUNGS) / 4.0 + 0.5)
        confidence = min(0.85, 0.35 + 0.22 * fit_q + 0.18 * vol_q + 0.10 * rung_q)

        hard = _ladder_has_hard_conflict(rungs)
        hard_note = ""
        if hard:
            confidence = min(0.9, confidence + 0.08)
            hard_note = " · ⚠️ Leiter enthaelt harten Widerspruch"

        stance = "stuetzt" if score > 0 else "warnt gegen"
        ev = ("🧩 Kohaerenz %s %s: Modell %.0f%% vs. Markt %.0f%% (λ%.2f, RMSE %.1fpp)%s"
              % (stance, detail, model_prob * 100, market_prob * 100, lam, rmse * 100, hard_note))

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=ev,
            metadata={"market": market_name, "token": tok, "detail": detail,
                      "model_prob": round(model_prob, 3), "market_prob": round(market_prob, 3),
                      "edge_pp": round(edge * 100, 2), "lambda": round(lam, 2),
                      "rmse_pp": round(rmse * 100, 2), "total_eur": round(total),
                      "hard_conflict": hard},
        )
