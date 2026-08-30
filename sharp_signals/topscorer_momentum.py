"""
sharp_signals/topscorer_momentum.py — Top-Torjäger-Bedrohung (26.06.2026, Lucas Spieler-Layer).

Ein Team mit einem treffsicheren Top-Torjäger (hohe Tore/Spiel) trägt eine konzentrierte Angriffs-
Bedrohung, die das Team-xG/-Form manchmal unterschätzt. Boostet den eigenen Sieg + Über; der Stürmer
des Gegners dämpft leicht. Daten: liga-data.json["topScorers"] (fetch_liga_topscorers).

In der „form"-Familie (Anti-Korr mit form_trend/xg_strength/chance_creation) → der Angriffs-Edge
zählt nicht doppelt. Konservativ gedeckelt; früh in der Saison (wenige Spiele) ~neutral.
"""
from __future__ import annotations

from typing import Optional

from sharp_signals.base import Signal, SignalResult, market_side

# ── Überarbeitet 30.08.2026 (Lucas-Checkup: „Torjäger 37% dafür") ──────────────────────────
# Gemessen über die Signal-Ledger (248 aufgelöste Picks, davon 36 mit diesem Signal):
#
#   Basisquote aller Picks         55,6%
#   Torjäger stützt den Pick       48,4%   (n=31, praktisch nur MLS)
#   Signal feuert gar nicht        56,6%
#   davon schwacher Score 0,3–0,6  60,0%   (n=15)
#   davon starker Score 0,65–1,2   37,5%   (n=16)
#
# Die Umkehrung nach Score-Höhe ist der eigentliche Befund: je lauter das Signal, desto
# schlechter der Ausgang. Zwei Konstruktionsfehler erklären das:
#
#  1. Der gegnerische Stürmer zählte nur HALB (`mine - 0.5*theirs`). Damit war das Signal ein
#     nahezu bedingungsloses „dieses Team hat einen Torjäger → drauf" — dagegen sprechen konnte
#     es nur, wenn der Gegner mehr als doppelt so bedrohlich war. Auf Über-Märkten konnte es
#     ÜBERHAUPT nicht widersprechen (Score dort immer positiv). Ein Signal, das fast nie Nein
#     sagt, trägt keine Richtungsinformation — es addiert eine Konstante auf die Seite, die
#     ohnehin schon gewählt war, und verbraucht dabei in der form-Familie Anti-Korrelations-
#     Budget, das den Signalen fehlt, die wirklich unterscheiden.
#  2. MIN_APPS=3 bei ELITE_GPG=0.7: drei Tore in vier Spielen lasen sich als „100% elite".
#     Früh in der Saison ist das reines Kleinstichproben-Rauschen — und genau diese Fälle
#     bildeten die starke Hälfte mit 37,5%.
#
# Beides ist jetzt behoben: der Gegner zählt voll, Über/Unter sind symmetrisch, und die
# Mindest-Stichprobe steigt. Das Signal bleibt an und wird weiter gemessen — abschalten hätte
# die Frage nie beantwortet, weil ein stummes Signal keine Daten sammelt. Die Entscheidung
# ruht ohnehin auf n=31; das Ledger urteilt in ein paar Wochen belastbarer als ich heute.
MAX_PP = 1.2
MIN_APPS = 6          # 30.08.2026: von 3 hoch. Drei Tore in vier Spielen sind keine Form.
ELITE_GPG = 0.7       # Tore/Spiel die als „elite" 1.0 zählen
GEGNER_GEWICHT = 1.0  # 30.08.2026: von 0.5 auf voll — sonst kann das Signal kaum widersprechen


def threat(entry: dict) -> float:
    """Top-Torjäger-Eintrag → Bedrohung 0..1 (Tore/Spiel, ab MIN_APPS, auf ELITE_GPG normiert)."""
    if not entry:
        return 0.0
    goals = entry.get("goals") or 0.0
    apps = entry.get("appearances") or 0.0
    if apps < MIN_APPS or goals <= 0:
        return 0.0
    return round(min(1.0, (goals / apps) / ELITE_GPG), 3)


class TopscorerMomentumSignal(Signal):
    def name(self) -> str:
        return "topscorer_momentum"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        ts = context.get("topscorers") or {}
        if not ts:
            return None
        home_id, away_id = context.get("home_id"), context.get("away_id")
        ht, at = threat(ts.get(home_id)), threat(ts.get(away_id))
        if ht == 0.0 and at == 0.0:
            return None

        side = market_side(pick.get("market", ""))
        if side is None:
            return None

        score, ev = 0.0, ""
        if side in ("home", "away"):
            mine, theirs = (ht if side == "home" else at), (at if side == "home" else ht)
            score = (mine - GEGNER_GEWICHT * theirs) * MAX_PP
            wer = ts.get(home_id if side == "home" else away_id) or {}
            geg = ts.get(away_id if side == "home" else home_id) or {}
            seite = "Heim" if side == "home" else "Auswärts"
            if score >= 0:
                ev = (f"Top-Torjäger {wer.get('name', '?')} (Bedrohung {mine:.0%}) stützt {seite}"
                      + (f" — Gegner {geg.get('name', '?')} {theirs:.0%}" if theirs else ""))
            else:
                ev = (f"Gegnerischer Torjäger {geg.get('name', '?')} ({theirs:.0%}) ist die größere "
                      f"Bedrohung als {wer.get('name', '?')} ({mine:.0%}) — spricht gegen {seite}")
        elif side in ("over", "under"):
            # 30.08.2026: „under" lieferte vorher immer None — das Signal konnte auf der Tor-Achse
            # nur zustimmen, nie widersprechen. Treffsichere Stürmer sprechen GEGEN Unter, das ist
            # dieselbe Aussage mit umgekehrtem Vorzeichen.
            roh = ((ht + at) / 2.0) * MAX_PP * 0.7
            score = roh if side == "over" else -roh
            ev = (f"Treffsichere Stürmer auf dem Platz (Heim {ht:.0%} / Auswärts {at:.0%}) → "
                  + ("Tor-Tendenz" if side == "over" else "spricht gegen Unter"))
        else:
            return None

        score = max(-MAX_PP, min(MAX_PP, round(score, 2)))
        if abs(score) < 0.3:
            return None
        conf = round(min(0.6, 0.35 + max(ht, at) * 0.25), 2)
        return SignalResult(score=score, confidence=conf, evidence=ev,
                            metadata={"homeThreat": ht, "awayThreat": at})
