#!/usr/bin/env python3
"""pick_announce_state.py — geteilter Ankündigungs-Status für Picks (03.07.2026, Lucas:
„Intraday-Neuer-Pick-Noti").

Problem: der Morgen-Digest (telegram_wm morning) postet die Tages-Slate einmal. Späte Steam-
Picks, die NACH dem Digest reinkommen (z.B. das Ghana-Spiel), tauchten nur noch stumm im
Tracking auf — kein Follower erfuhr davon. notify_new_picks.py schließt die Lücke.

Damit Digest und Noti sich nicht doppeln, teilen sie EINEN Status:
  • Pick-Identität = "{pick_key}|{market}"  (es gibt kein id/selection-Feld am Pick).
  • Der Digest markiert beim Senden die komplette bekannte Slate als „announced" + setzt
    lastDigestDate=heute.
  • notify_new_picks sendet nur, was NACH dem heutigen Digest neu ist. Läuft es vor dem
    Digest, setzt es stumm die Basis (kein Send) — so bleibt der Digest der Erst-Ankündiger.

Dataset-aware: WM → pick_announce_state.json, MLS → mls_pick_announce_state.json, usw.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).parent
STATE_FILE = BASE / f"{D.prefix()}pick_announce_state.json"

# Nur diese Verdicts sind „Picks", die man ankündigt (NOBET/SKIP nie).
ANNOUNCE_VERDICTS = {"BET", "ABWÄGEN"}

# ── Der Gegensignal-Filter (30.08.2026, Lucas) ──────────────────────────────────────────
# Lucas: „ich schick bei ABWÄGEN nicht die 1X2-Märkte, weil die schwächer sind" — die Vermutung
# war, der MARKT trennt. Gemessen an 220 abgerechneten ABWÄGEN trennt er nicht: pro Markt liegen
# nur 17–46 Zeilen vor, die Fehlerspanne ist ±25–35pp ROI, und 1X2 kippt je nach Ausschnitt von
# +8,8% auf −1,5%. Das Vorzeichen wechselt mit der Auswahl — das ist Rauschen, kein Befund.
#
# Was sauber trennt, ist die SIGNAL-ZUSAMMENSETZUNG:
#     kein einziges Gegensignal   n=47   78,7% Treffer   ROI +40,0%   Untergrenze +19,3%
#     positive UND negative       n=143  49,7%           ROI −11,7%   Untergrenze −24,9%
#     keine oder nur negative     n=30   43,3%           ROI −12,6%   Untergrenze −46,5%
# Das hält in JEDEM Markt einzeln (Ü/U 87,5 vs 55,1 · 1X2 85,7 vs 41,0 · BTTS 68,8 vs 27,3) und
# in Ligen wie WM getrennt. Bootstrap: 0 von 4.000 Resamples unter null. Ausgerechnet 1X2 hat
# die beste saubere Teilmenge — Lucas' ursprünglicher Filter hätte sie weggeworfen.
#
# Ein BET ist davon NICHT betroffen: dort hat das Verdikt-Gate schon entschieden.
# Die aussortierten ABWÄGEN laufen im Schattenbuch (pick_push_ledger.py) weiter mit und werden
# abgerechnet — dieser Schnitt muss sich vor freigabe.py verantworten wie jede andere Regel.
def _sig_zahlen(p: dict):
    """(positive, negative) Signalzahl. Fehlen die Zähler, aus der Signal-Liste rekonstruieren."""
    pos, neg = p.get("signalCountPos"), p.get("signalCountNeg")
    if isinstance(pos, int) and isinstance(neg, int):
        return pos, neg
    sig = p.get("signals") or []
    return (sum(1 for s in sig if (s or {}).get("score", 0) > 0),
            sum(1 for s in sig if (s or {}).get("score", 0) < 0))


def hat_gegensignal(p: dict) -> bool:
    """Widerspricht dem Pick mindestens ein Signal? Ohne jede Signal-Angabe: ja (fail-closed —
    keine Information ist keine Erlaubnis, dieselbe Regel wie im Freigabe-Register)."""
    pos, neg = _sig_zahlen(p)
    return neg > 0 or pos == 0


def push_ok(p: dict) -> bool:
    """DIE eine Antwort auf „geht dieser Pick raus?" — für Digest UND Intraday-Noti.

    Vorher gab es zwei Definitionen (ANNOUNCE_VERDICTS hier, _is_posted in telegram_wm) und sie
    unterschieden sich bereits (boldAlt). Genau dieses Auseinanderlaufen hat sharp_gate.py für
    die Wallets beseitigt; hier gilt dasselbe Prinzip: eine Definition, eine Datei."""
    if not p or p.get("trackingExcluded") or p.get("boldAlt"):
        return False
    v = p.get("verdict")
    if v not in ANNOUNCE_VERDICTS:
        return False
    if v == "BET":
        return True
    return not hat_gegensignal(p)

_KO_LABELS = {"R32": "Sechzehntelfinale", "R16": "Achtelfinale", "QF": "Viertelfinale",
              "SF": "Halbfinale", "F": "Finale", "3P": "Spiel um Platz 3"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load() -> dict:
    if not STATE_FILE.exists():
        return {"announced": {}, "lastDigestDate": None, "seeded": False}
    try:
        d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        d.setdefault("announced", {})
        d.setdefault("lastDigestDate", None)
        d.setdefault("seeded", False)
        return d
    except Exception:
        return {"announced": {}, "lastDigestDate": None, "seeded": False}


def save(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def mark(state: dict, ids, ts: str | None = None) -> None:
    ts = ts or _now().isoformat()
    for i in ids:
        state.setdefault("announced", {})[i] = ts


def is_announced(state: dict, pick_id: str) -> bool:
    return pick_id in (state.get("announced") or {})


def _fixture_upcoming(fx, now) -> bool:
    """True, wenn das Spiel noch nicht angepfiffen/fertig ist (kickoff in Zukunft)."""
    res = fx.get("result") or {}
    if str(res.get("status") or "").upper() in {"FT", "AET", "PEN", "AWD", "WO"}:
        return False
    ko = fx.get("kickoff")
    if ko:
        try:
            return datetime.fromisoformat(str(ko).replace("Z", "+00:00")) > now
        except Exception:
            pass
    return True   # ohne kickoff/Ergebnis vorsichtshalber als offen behandeln


def iter_pick_units(wm: dict, now=None, alle: bool = False):
    """Yield ein dict pro announce-fähigem Pick auf einem KOMMENDEN Spiel.

    Genau EINE Quelle für Digest-Seeding und die Noti → keine Drift. Liefert Anzeige-
    Felder gleich mit (Namen/Flaggen/Runde), damit die Noti nichts nachschlagen muss.

    `alle=True` liefert AUCH die vom Gegensignal-Filter aussortierten Picks (jede Zeile trägt
    `push`). Das braucht nur das Schattenbuch — gesendet wird nie daraus.
    """
    now = now or _now()
    groups = wm.get("groups", {})
    picks = wm.get("picks", {})

    # Team-Nachschlag (KO-Fixtures tragen nur IDs)
    all_teams = {}
    for gd in groups.values():
        for t in gd.get("teams", []):
            all_teams[t["id"]] = t

    def _emit(pick_key, home, away, kickoff, round_label):
        home_t = all_teams.get(home, {})
        away_t = all_teams.get(away, {})
        for p in picks.get(pick_key, []):
            if p.get("verdict") not in ANNOUNCE_VERDICTS or p.get("trackingExcluded"):
                continue
            raus = push_ok(p)
            if not (raus or alle):
                continue
            pos, neg = _sig_zahlen(p)
            market = p.get("market") or ""
            yield {
                "id": f"{pick_key}|{market}",
                "pick_key": pick_key,
                "market": market,
                "verdict": p.get("verdict"),
                "push": raus, "sigPos": pos, "sigNeg": neg,
                "odds": p.get("odds"), "result": p.get("result"),
                "convictionScore": p.get("convictionScore"),
                "source": p.get("source"),
                "home": home, "away": away,
                "homeName": home_t.get("name", home), "awayName": away_t.get("name", away),
                "homeFlag": home_t.get("flag", "🏳"), "awayFlag": away_t.get("flag", "🏳"),
                "kickoff": kickoff, "roundLabel": round_label,
            }

    for gkey, gdata in groups.items():
        for fx in gdata.get("fixtures", []):
            if not (fx.get("home") and fx.get("away")):
                continue
            if not _fixture_upcoming(fx, now):
                continue
            pk = f"{gkey}-{fx['matchday']}-{fx['home']}-{fx['away']}"
            yield from _emit(pk, fx["home"], fx["away"], fx.get("kickoff", ""), None)

    for kf in (wm.get("koFixtures") or []):
        if not (kf.get("home") and kf.get("away")):
            continue
        if not _fixture_upcoming(kf, now):
            continue
        rnd = kf.get("round")
        pk = f"KO-{rnd}-{kf['home']}-{kf['away']}"
        label = kf.get("roundLabel") or _KO_LABELS.get(rnd, "K.-o.-Runde")
        yield from _emit(pk, kf["home"], kf["away"], kf.get("kickoff", ""), label)


def current_pick_ids(wm: dict, now=None) -> set:
    return {u["id"] for u in iter_pick_units(wm, now)}
