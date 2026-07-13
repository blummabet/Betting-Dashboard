"""
sharp_signals/fixture_congestion.py — Erschöpfungs-/Spielstau-Signal (26.06.2026, Lucas).

Liga-Edge: Teams mit englischer Woche (Di/Mi → Sa) oder Europapokal-Reise spielen mit müden/
rotierten Beinen. Das frisch ausgeruhte Team hat einen realen Vorteil; ein erschöpftes Team wird
eher gefadet. Rein aus dem Spielplan (Ruhetage = Datum-Abstand zum letzten Spiel) — KEIN API-Call.

Modular: liest context["team_schedule"] (in generate_wm_picks gebaut). Früh in der Saison / bei
erstem Spiel gibt es keinen Vorgänger → None (Schläfer). Über/Unter konservativ: müde Beine eher
weniger Tore → leichter Unter-Hebel; Über bewusst KEIN Boost (Erschöpfung ≠ Torfestival).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sharp_signals.base import Signal, SignalResult, market_side

MAX_PP = 1.5
SHORT_REST_DAYS = 3   # ≤ 3 Tage Pause = englische Woche / Stau


def build_team_schedule(groups: dict) -> dict:
    """{team_id: [sortierte Datums-Strings]} aus allen Fixtures. Rein aus dem Plan, kein API-Call.

    13.07.2026 (Lucas: „MLS startet Freitag — haben wir die Saisondaten am Schirm?"): Diese Logik
    lag NUR in generate_wm_picks. signal_check (der „Analyse"-Tab) baute sie nicht nach → dort war
    `team_schedule` leer → fixture_congestion blieb für JEDES Spiel still, und der Tab zeigte
    weniger Signale, als die Engine wirklich benutzt. Genau das soll signal_check aber spiegeln.
    Jetzt EINE Funktion, die beide Seiten aufrufen — das Format kann nicht mehr auseinanderlaufen.

    Für die MLS besonders relevant: dort wird viel unter der Woche gespielt (englische Wochen sind
    die Regel, nicht die Ausnahme), Ruhetage sind also ein echter Faktor.
    """
    out: dict = {}
    for gd in (groups or {}).values():
        for fx in (gd.get("fixtures") or []):
            d = fx.get("date")
            if not d:
                continue
            for tid in (fx.get("home"), fx.get("away")):
                if tid:
                    out.setdefault(tid, []).append(d)
    for tid in out:
        out[tid] = sorted(set(out[tid]))
    return out


def rest_days(schedule: list, match_date: str) -> Optional[int]:
    """Tage seit dem letzten Spiel vor match_date (aus sortierter Datums-Liste). None wenn kein
    Vorgänger (erstes Saisonspiel) oder Datum unparsebar. Reine Funktion (testbar)."""
    if not schedule or not match_date:
        return None
    try:
        cur = date.fromisoformat(str(match_date)[:10])
    except ValueError:
        return None
    prev = None
    for d in schedule:
        try:
            dd = date.fromisoformat(str(d)[:10])
        except ValueError:
            continue
        if dd < cur and (prev is None or dd > prev):
            prev = dd
    return (cur - prev).days if prev is not None else None


def congestion_factor(rest: Optional[int]) -> float:
    """Ruhetage → Erschöpfungs-Faktor 0..1. ≤2d=1.0 (2-Tage-Turnaround), 3d=0.6, 4d=0.25, ≥5d=0."""
    if rest is None:
        return 0.0
    if rest <= 2:
        return 1.0
    if rest == 3:
        return 0.6
    if rest == 4:
        return 0.25
    return 0.0


class FixtureCongestionSignal(Signal):
    def name(self) -> str:
        return "fixture_congestion"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        sched = context.get("team_schedule") or {}
        md_date = context.get("current_match_date")
        home_id, away_id = context.get("home_id"), context.get("away_id")
        if not sched or not md_date or not home_id or not away_id:
            return None

        h_rest = rest_days(sched.get(home_id) or [], md_date)
        a_rest = rest_days(sched.get(away_id) or [], md_date)
        hc, ac = congestion_factor(h_rest), congestion_factor(a_rest)
        if hc == 0.0 and ac == 0.0:
            return None   # beide ausgeruht → kein Stau → Schläfer

        side = market_side(pick.get("market", ""))
        if side is None:
            return None

        score, ev = 0.0, ""
        if side in ("home", "away"):
            my_c = hc if side == "home" else ac
            opp_c = ac if side == "home" else hc
            score = (opp_c - my_c) * MAX_PP   # Gegner müde → Boost; eigenes Team müde → Fade
            lbl = "Heim" if side == "home" else "Auswärts"
            ev = (f"Ruhetage {lbl} {h_rest if side=='home' else a_rest}d vs Gegner "
                  f"{a_rest if side=='home' else h_rest}d — "
                  f"{'Gegner im Spielstau' if opp_c > my_c else 'eigenes Team im Spielstau'}")
        elif side == "under":
            score = max(hc, ac) * MAX_PP * 0.5
            ev = f"Müde Beine (Ruhetage Heim {h_rest}d / Auswärts {a_rest}d) → eher weniger Tore"
        else:   # over: Erschöpfung ist kein Über-Argument
            return None

        score = max(-MAX_PP, min(MAX_PP, round(score, 2)))
        if abs(score) < 0.3:
            return None
        conf = round(min(0.7, 0.4 + max(hc, ac) * 0.25), 2)
        return SignalResult(score=score, confidence=conf, evidence=ev,
                            metadata={"homeRest": h_rest, "awayRest": a_rest,
                                      "homeCongestion": hc, "awayCongestion": ac})
