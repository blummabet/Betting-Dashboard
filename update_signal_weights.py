#!/usr/bin/env python3
"""
update_signal_weights.py — Bayesian Lern-Loop für sharp_signals

Wird nach build_signal_ledger.py aufgerufen:
  · Liest das Lern-Ledger (wm_signal_ledger.json) — je aufgelöster Card-Pick ein
    Snapshot der gefeuerten Signale + Outcome (WIN/LOSS).
  · Für jeden Record mit signals[]: pro Signal eine Beobachtung (won/lost)
  · Bayesian-Update der Weights in signal_weights.json

FIX 12.06.2026: Vorher las dieses Script wm_results.json — das ist aber der
TRADE-P&L der platzierten Polymarket-Bets (Key `bets`, ohne signals[], oft
PENDING), NICHT die aufgelösten Card-Picks. Ergebnis: 0 Beobachtungen, alle
Gewichte blieben ewig 1.0. Die Beobachtungs-Erfassung liegt jetzt in
build_signal_ledger.py; dieses Script konsumiert nur noch den Ledger.

Math (Beta-Binomial mit Prior α=β=2 für "vorsichtigen Start"):
  posterior_mean = (α + wins) / (α + β + n)
  weight = posterior_mean / 0.5   # 0.5 = neutrale Win-Rate-Annahme
  → weight > 1.0 = Signal predicted besser als Coin-Flip
  → weight < 1.0 = Signal ist schlechter als Coin-Flip → Signal-Score wird gedämpft

Smoothing-Idee:
  Erst ab n_observations ≥ MIN_OBSERVATIONS_FOR_TRUST aktualisiert das Update
  spürbar (vorher kleiner Schritt). So überreagiert die Engine nicht auf die
  ersten 3 Spiele.

Run:
  python3 update_signal_weights.py
  → Updates signal_weights.json (commit kommt vom Workflow)
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
import cocobet_dataset as D  # noqa: E402
# Dataset-Modus (Single Source: cocobet_dataset): Liga → eigene Liga-Gewichte/-Ledger.
_IS_LIGA = D.is_liga()

# Prior-Parameter (Beta-Binomial)
PRIOR_ALPHA = 2.0
PRIOR_BETA  = 2.0
MIN_OBS_FOR_TRUST = 10  # davor: konservatives Update (50% weight zur Prior)

# ── Wogegen wird gemessen? (30.08.2026, Lucas-Checkup) ──────────────────────────────────
# Das Gewicht war `posterior_mean / 0.5` — der Massstab war der MUENZWURF. Unsere Picks sind
# aber keine Muenzwuerfe: sie gewinnen im Schnitt 55,6% (WM+MLS+Liga zusammen, 248 aufgeloeste
# Picks). Damit belohnte der Loop den Hausvorteil statt den Beitrag des Signals:
#
#   · Ein Signal, das auf genau durchschnittlichen Picks feuert (55,6%), bekam Gewicht 1,11 —
#     einen Bonus dafuer, nichts beizutragen.
#   · topscorer_momentum feuerte auf Picks mit 48,4% — sieben Punkte UNTER dem Hausschnitt —
#     und stand trotzdem bei 0,974, also praktisch unbestraft, weil 48% ungefaehr 50% ist.
#
# Gemessen wird jetzt gegen die eigene Trefferquote. Zwei Feinheiten, ohne die es falsch waere:
#
#  1. Der CLV-Strom hat einen ANDEREN neutralen Punkt. _clv_outcome_score bildet CLV=0 auf 0,5
#     ab — 0,5 ist dort per Konstruktion „Linie stand still", nicht „Muenzwurf". Diese
#     Beobachtungen bleiben deshalb gegen 0,5 gemessen; nur der Ergebnis-Strom (inkl.
#     Backtest-Prior) wird gegen die Trefferquote gemessen. Der effektive Nullpunkt ist das
#     mit den Stroemen gewichtete Mittel.
#  2. Unter BASIS_MIN_N ist die eigene Quote selbst zu verrauscht, um Massstab zu sein — dann
#     bleibt es beim Muenzwurf. Und sie wird gedeckelt: eine Basis von 80% aus einer Gluecks-
#     serie wuerde sonst jedes Signal unter Wasser druecken.
BASIS_MIN_N = 40      # darunter ist die eigene Trefferquote kein belastbarer Massstab
BASIS_MIN   = 0.45    # Deckel nach unten
BASIS_MAX   = 0.70    # Deckel nach oben — Glueckssträhnen sollen den Massstab nicht kippen


def basisquote(picks):
    """(quote, n) — Anteil gewonnener aufgeloester Picks. (0.5, n) wenn zu duenn."""
    werte = [_process_outcome_score(p) for p in (picks or [])]
    werte = [w for w in werte if w is not None]
    n = len(werte)
    if n < BASIS_MIN_N:
        return 0.5, n
    return max(BASIS_MIN, min(BASIS_MAX, sum(werte) / n)), n

# 23.06.2026 (Lucas): Runde 1 (alte Engine) aus dem Lern-Loop ausschließen — die ST1-Picks liefen
# teils auf alter Engine und würden die neuen Gewichte verwässern. Ledger behält die Historie
# (Audit), aber das Lernen startet ab Matchday 2. Höher setzen, um Slate weiter einzuschränken.
# Liga hat keine „alte Engine in Runde 1" → ab Spieltag 1 lernen. WM bleibt bei 2.
MIN_LEARN_MATCHDAY = 1 if _IS_LIGA else 2

LEDGER_FILE  = D.file("wm_signal_ledger.json", "liga_signal_ledger.json")
WEIGHTS_FILE = D.file("signal_weights.json", "liga_signal_weights.json")

# ─────────────────────────────────────────────────────────────────────────────────────
# CLV als ZWEITER Beobachtungsstrom (18.07.2026, Lucas)
#
# Problem: ein aufgelöster Pick liefert genau EINE won/lost-Beobachtung je Signal. Bei ~100
# Picks auf 30 Signale hungert der Loop — deshalb bewegen sich die Gewichte kaum. CLV ist
# stetig statt binär, hat viel kleinere Varianz und steht schon beim Anpfiff fest.
#
# ⚠️ NICHT als Ersatz, sondern als zweiter Strom — und NICHT für jedes Signal. Lucas' Einwand:
# „CLV ist der Maßstab, wenn du plump nach Odd-Drops spielst; wenn du Signale hast, die dagegen
# schießen, ist das was anderes und kann so nicht 1:1 gesagt werden." Genau das bildet
# CLV_LEARNING_GROUPS ab:
#
#   · sharp_money-Signale (lead_lag, steam_lag, polymarket_sharp, reverse_line_move, opener_move,
#     multi_book_steam) behaupten wörtlich „dieser Move ist echt und läuft weiter" → CLV ist der
#     DIREKTE Test dieser Behauptung. Ob der Ball reingeht, ist dafür fast nebensächlich.
#   · form/context/incentive-Signale behaupten „diese Mannschaft ist besser als der Markt denkt".
#     Das ist eine Ergebnis-Aussage. Sie feuern oft bewusst GEGEN den Move — sie an CLV zu
#     messen würde genau das bestrafen, wofür sie da sind.
#
# Ein CLV-Datenpunkt zählt bewusst weniger als ein echtes Ergebnis (CLV_OBS_WEIGHT): er ist
# präziser, aber indirekt — er misst die Markt-Zustimmung, nicht die Realität.
CLV_LEARNING_GROUPS = {"sharp_money"}
CLV_FULL_PP     = 5.0   # ±5pp ⇒ Score 1.0 / 0.0. Darüber wird geklippt (Ausreißer dominieren nicht).
CLV_OBS_WEIGHT  = 0.5   # eine CLV-Beobachtung zählt als halbe Ergebnis-Beobachtung
CLV_DEADBAND_PP = 0.5   # darunter ist es Rauschen, keine Markt-Zustimmung


def _clv_outcome_score(pick: dict) -> float | None:
    """CLV → Score ∈ [0,1]. 0.5 = Linie stand still (neutral), 1.0 = +5pp unser Weg.

    None bedeutet „keine verwertbare Beobachtung" — bei fehlendem CLV (Markt ohne Closing-
    Erfassung, z.B. BTTS/DC/AH) und innerhalb der Deadband. Bewusst kein Default 0.5: eine
    erfundene neutrale Beobachtung würde echte Signale Richtung 1.0 verwässern."""
    v = pick.get("clvPP")
    if v is None:
        return None
    try:
        pp = float(v)
    except (TypeError, ValueError):
        return None
    if abs(pp) < CLV_DEADBAND_PP:
        return None
    return max(0.0, min(1.0, 0.5 + pp / (2.0 * CLV_FULL_PP)))


def _learns_on_clv(signal_name: str) -> bool:
    try:
        from sharp_signals.registry import SIGNAL_GROUPS
    except Exception:
        return False
    return SIGNAL_GROUPS.get(signal_name, "unique") in CLV_LEARNING_GROUPS


def _matchday_of(pick: dict) -> int | None:
    """Matchday aus dem Record. Bevorzugt explizites Feld, sonst aus matchKey
    'GKEY-MD-HOME-AWAY' (2. Segment). None wenn nicht ableitbar."""
    md = pick.get("matchday")
    if isinstance(md, int):
        return md
    parts = str(pick.get("matchKey") or pick.get("key") or "").split("-")
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return None


def _load_results() -> list[dict]:
    """Lern-Beobachtungen aus dem Signal-Ledger (records[]). Jeder Record hat
    result (WIN/LOSS/VOID) + signals[] (name/score) — genau was update_weights braucht.
    Runde < MIN_LEARN_MATCHDAY (alte Engine) wird ausgefiltert."""
    if not LEDGER_FILE.exists():
        return []
    try:
        d = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        recs = d if isinstance(d, list) else (
            d.get("records") or d.get("picks") or d.get("resolved") or [])
    except Exception as e:
        print(f"⚠️  wm_signal_ledger.json laden fehlgeschlagen: {e}")
        return []
    # Version-aware (04.07.2026, Lucas): nur auf der AKTUELLEN Engine-Version lernen. Records mit
    # engineVersion != aktuell (von einer alten Engine) fallen raus — so vergiftet ein Fix den
    # Ledger nicht. Legacy-Records OHNE Stempel fallen auf das Matchday-Gate zurück (alte WM-Logik).
    current_ev = D.engine_version()
    kept, skipped_md, skipped_ver = [], 0, 0
    for r in recs:
        ev = r.get("engineVersion")
        if ev is not None:
            if ev != current_ev:
                skipped_ver += 1
                continue
            kept.append(r)   # aktuelle Version → lernen (Matchday-Gate greift NICHT mehr)
            continue
        # Legacy ohne Stempel → Matchday-Fallback (Elo-Ära ausschließen)
        md = _matchday_of(r)
        if md is not None and md < MIN_LEARN_MATCHDAY:
            skipped_md += 1
            continue
        kept.append(r)
    if skipped_ver:
        print(f"  ⏭️  {skipped_ver} Records aus alter Engine-Version (≠ {current_ev}) übersprungen")
    if skipped_md:
        print(f"  ⏭️  {skipped_md} Legacy-Records aus Runde < MD{MIN_LEARN_MATCHDAY} übersprungen")
    return kept


def _load_weights() -> dict:
    if not WEIGHTS_FILE.exists():
        return {"_meta": {}}
    try:
        return json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"_meta": {}}


PRIORS_FILE = D.file("signal_priors.json", "liga_signal_priors.json")  # dataset-aware (29.06.2026): mls liest mls_signal_priors statt liga (keine Kontamination)


def _load_priors() -> dict:
    """Backtest-als-Prior (nur Liga): {sig: {nPrior, winsPrior}}. Pseudo-Beobachtungen aus
    prime_liga_priors.py, die zu den Live-Counts addiert werden → informierter Start, verblasst mit
    wachsender Live-Stichprobe. Bei WM oder fehlender Datei leer (Verhalten unverändert)."""
    if not _IS_LIGA or not PRIORS_FILE.exists():
        return {}
    try:
        d = json.loads(PRIORS_FILE.read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if not k.startswith("_")}
    except Exception:
        return {}


def _save_weights(weights: dict) -> None:
    tmp = WEIGHTS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(weights, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(WEIGHTS_FILE)


def _result_is_win(pick: dict) -> bool | None:
    """True = Win, False = Loss, None = Push/Void/unresolved (kein Lern-Update)."""
    r = (pick.get("result") or "").lower()
    if r == "win":  return True
    if r == "loss": return False
    return None


# Prozess-justierter Outcome ∈ [0,1] (FIX 14.06.2026): 1 = per xG verdient gewonnen,
# 0 = per xG verdient verloren. Trennt Können von Varianz — ein verlorener-aber-
# verdienter Pick (UNLUCKY, z.B. QAT-SUI Over) bestraft die Signale nur teilweise,
# ein glücklicher Win (LUCKY) belohnt sie nur teilweise.
PROCESS_OUTCOME = {
    "JUSTIFIED":     1.0,
    "LUCKY":         0.65,
    "UNLUCKY":       0.35,
    "DESERVED_LOSS": 0.0,
}


def _process_outcome_score(pick: dict) -> float | None:
    """Kontinuierlicher Outcome-Score. Ohne processVerdict (keine Match-xG) Fallback
    aufs binäre Ergebnis (WIN=1.0, LOSS=0.0) → identisch zum alten Verhalten."""
    pv = pick.get("processVerdict")
    if pv in PROCESS_OUTCOME:
        return PROCESS_OUTCOME[pv]
    w = _result_is_win(pick)
    return None if w is None else (1.0 if w else 0.0)


def _preis_justierter_outcome(pick: dict) -> float | None:
    """Wie hat der Pick gegen SEINEN EIGENEN PREIS abgeschnitten? -> [0,1] oder None.

    06.09.2026. Bis heute lernte dieser Loop an der Trefferquote — erst gegen den Muenzwurf,
    seit 30.08. gegen die eigene Basisquote. Beides sind Trefferquoten, und **eine Trefferquote
    ohne die Quoten ist keine Zahl**. Ein Signal, das auf 1,30-Favoriten feuert und 70 % trifft,
    schlaegt jede Basisquote und wird belohnt — bei rund -9 % Rendite. Ein Signal, das auf 3,00
    feuert und 35 % trifft, wird bestraft — bei +5 %.

    Messbare Folge im Bestand: `lead_lag_bias`, das Signal mit dem staerksten gemessenen
    CLV-Zusammenhang (r = +0,495), stand in liga auf 0,901 (gedaempft); `xg_strength`
    (r = +0,058) auf 1,034. Der Loop hat die Preis-Signale abtrainiert und die
    Staerke-Signale hochgezogen — und damit genau die Favoriten-Verzerrung erzeugt, die wir
    am 06.09. gemessen haben (59,5 % Treffer gegen 71,4 % implizit, Obergrenze 65,1 %).

    Der Massstab ist jetzt der Preis selbst:

        wert = prozess-justierter Ausgang (0..1)  -  implizite Wahrscheinlichkeit (1/Quote)
        score = 0,5 + wert/2

    0,5 heisst damit per Konstruktion **„genau so ausgegangen, wie der Preis es sagte"** — der
    neutrale Punkt faellt aus der Rechnung, statt aus einer geschaetzten Basisquote zu kommen.
    Ueber 1 hinaus ist kein Kredit moeglich, unter 0 keine Strafe.

    Die 1/Quote traegt die Marge des Buches; alle Signale werden dadurch gleich stark nach
    unten gezogen, die RANGFOLGE bleibt unberuehrt. Das ist der konservative Fehler.

    Ohne Quote gibt es KEINE Beobachtung — nicht ersatzweise die alte Trefferquote.
    *Fehlende Information ist keine Erlaubnis.* Der Ledger stempelt die Quote seit dem
    06.09. mit (`build_signal_ledger`), der Altbestand wurde nachgetragen.
    """
    o = _process_outcome_score(pick)
    if o is None:
        return None
    q = pick.get("entryOdd")
    if isinstance(q, bool) or not isinstance(q, (int, float)) or q <= 1.0:
        q = pick.get("odds")
    if isinstance(q, bool) or not isinstance(q, (int, float)) or q <= 1.0:
        return None
    implizit = 1.0 / float(q)
    return max(0.0, min(1.0, 0.5 + (o - implizit) / 2.0))


def update_weights() -> dict:
    """Hauptlogik: Bayesian-Update aller Signal-Weights."""
    weights = _load_weights()
    picks   = _load_results()

    # Counts pro Signal — aus den resolved Picks aggregieren
    # Jedes Mal wenn ein Signal getriggered hat (score != 0), ist das eine
    # Beobachtung. Ob das Signal "richtig lag", entscheidet das pick-Outcome
    # GEWICHTET nach Signal-Direction:
    #   score > 0 = Signal sagte "guter Pick" → Win = predicted correctly
    #   score < 0 = Signal sagte "schlechter Pick" → Loss = predicted correctly
    counts: dict[str, dict] = {}
    for pick in picks:
        # 06.09.2026: gegen den PREIS, nicht gegen die Trefferquote (s. _preis_justierter_outcome).
        o     = _preis_justierter_outcome(pick)
        o_clv = _clv_outcome_score(pick)       # ∈ [0,1], Markt-Zustimmung (18.07.2026)

        # CLV-Strom: getrennt gezählt, damit ein Pick OHNE Ergebnis (noch nicht gespielt, aber
        # Closing steht) schon lernbar ist — das ist der halbe Punkt der Übung.
        if o_clv is not None:
            for s in pick.get("signals") or []:
                name, score = s.get("name"), s.get("score", 0.0)
                if not name or score == 0.0 or not _learns_on_clv(name):
                    continue
                c = counts.setdefault(name, {"n": 0, "predicted_correctly": 0.0,
                                             "n_clv": 0.0, "clv_correct": 0.0})
                c.setdefault("n_clv", 0.0)
                c.setdefault("clv_correct", 0.0)
                c["n_clv"] += CLV_OBS_WEIGHT
                c["clv_correct"] += CLV_OBS_WEIGHT * (o_clv if score > 0 else (1.0 - o_clv))

        if o is None:
            continue
        for s in pick.get("signals") or []:
            name  = s.get("name")
            score = s.get("score", 0.0)
            if not name or score == 0.0:
                continue
            counts.setdefault(name, {"n": 0, "predicted_correctly": 0.0})
            counts[name]["n"] += 1
            # Signal-Korrektheit FRAKTIONAL: score>0 sagte „guter Pick" → Gutschrift =
            # wie verdient der Win war (o); score<0 sagte „schlechter Pick" →
            # Gutschrift = wie verdient der Loss war (1-o). Binär-Fallback (o∈{0,1})
            # reproduziert exakt das alte „predicted_win == outcome".
            predicted_win = score > 0
            counts[name]["predicted_correctly"] += o if predicted_win else (1.0 - o)

    # 06.09.2026: Der Massstab ist der PREIS des Picks, und der steckt seit
    # `_preis_justierter_outcome` in jeder einzelnen Beobachtung. Damit ist der neutrale Punkt
    # 0,5 per Konstruktion — „genau so ausgegangen, wie bepreist". Die geschaetzte Basisquote
    # (30.08.) war der Zwischenschritt dorthin und wird nicht mehr als Nullpunkt gebraucht; sie
    # wird nur noch berichtet, damit die Verschiebung im Log sichtbar bleibt.
    basis, basis_n = basisquote(picks)
    NEUTRAL_ERGEBNIS = 0.5

    # Backtest-Prior (nur Liga): Pseudo-Beobachtungen, die zu den Live-Counts addiert werden.
    # Signale ganz ohne Live-Trigger bekommen trotzdem ihren Prior-Vorsprung.
    priors = _load_priors()
    for sig_name, p in priors.items():
        counts.setdefault(sig_name, {"n": 0, "predicted_correctly": 0.0})

    # Update jeder Signal-Entry
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for sig_name, c in counts.items():
        n_live      = c["n"]
        wins_live   = c["predicted_correctly"]
        pr          = priors.get(sig_name) or {}
        n_prior     = float(pr.get("nPrior") or 0.0)
        wins_prior  = float(pr.get("winsPrior") or 0.0)
        # CLV-Strom (nur sharp_money-Familie, siehe CLV_LEARNING_GROUPS). Bereits mit
        # CLV_OBS_WEIGHT skaliert — geht als vollwertige, aber leichtere Beobachtung ein.
        n_clv       = float(c.get("n_clv") or 0.0)
        wins_clv    = float(c.get("clv_correct") or 0.0)
        # Prior + Live + CLV verschmolzen (Prior verblasst mit wachsendem n).
        n           = n_live + n_prior + n_clv
        wins        = wins_live + wins_prior + wins_clv
        losses      = n - wins
        # Posterior Mean mit Prior
        post_mean   = (PRIOR_ALPHA + wins) / (PRIOR_ALPHA + PRIOR_BETA + n)
        # Neutrale Erwartung: Ergebnis-Beobachtungen gegen die eigene Trefferquote, CLV-
        # Beobachtungen gegen 0.5 (dort heisst 0.5 „Linie stand still"). Siehe Kopf.
        _n_erg = n_live + n_prior
        neutral = ((_n_erg * NEUTRAL_ERGEBNIS + n_clv * 0.5) / n) if n > 0 else NEUTRAL_ERGEBNIS
        neutral = max(0.30, min(0.80, neutral))     # kein Nullpunkt jenseits des Sinnvollen
        raw_weight  = post_mean / neutral

        # Sanity-Bound: weight ∈ [0.3, 1.7] damit ein einzelnes Signal das
        # System nie komplett dominiert oder neutralisiert
        clamped_weight = max(0.3, min(1.7, raw_weight))

        # Smoothing: bei wenig Daten näher zum neutralen 1.0. Der Backtest-Prior zählt mit (n),
        # ein geprimtes Signal wird also von Anfang an vertraut.
        if n < MIN_OBS_FOR_TRUST:
            blend = n / MIN_OBS_FOR_TRUST   # 0..1
            clamped_weight = 1.0 * (1.0 - blend) + clamped_weight * blend

        prev = weights.get(sig_name) or {}
        weights[sig_name] = {
            "weight":              round(clamped_weight, 3),
            "n_observations":      round(n_live, 2),     # ECHTE Live-Beobachtungen (Ergebnis)
            "n_prior":             round(n_prior, 2),    # Backtest-Pseudo-Obs (verblassen)
            # Getrennt ausgewiesen, damit im Lern-Panel sichtbar bleibt, WORAUS ein Signal gelernt
            # hat. Ein Gewicht, das nur auf CLV beruht, ist eine andere Aussage als eines aus
            # echten Ergebnissen — das darf nicht in einer Zahl verschwinden.
            "n_clv":               round(n_clv, 2),
            "wins_when_triggered": round(wins, 2),       # fraktional (Live + Prior)
            "losses_when_triggered": round(losses, 2),
            "posterior_mean":      round(post_mean, 3),
            # Wogegen wurde gemessen? Ohne das ist ein Gewicht nicht nachrechenbar.
            "basis":               round(basis, 3),
            "basisN":              basis_n,
            "neutral":             round(neutral, 3),
            "last_updated":        now_iso,
            "notes":               prev.get("notes") or "",
        }

    _save_weights(weights)
    return weights


def main():
    print("📊 update_signal_weights.py")
    weights = update_weights()
    for name, entry in weights.items():
        if name.startswith("_"):
            continue
        if isinstance(entry, dict) and "weight" in entry:
            n = entry.get("n_observations", 0)
            w = entry.get("weight", 1.0)
            wr = entry.get("posterior_mean", 0.5)
            print(f"  · {name}: weight={w:.3f}  (n={n}, posterior={wr:.2f})")


if __name__ == "__main__":
    main()
