#!/usr/bin/env python3
"""
betfair_card_link.py — unsere Card neben die Börsen-Zeile (26.08.2026, Lucas)

## Warum

Das Terminal zeigt in der Spalte „Pick" die **Geld-Seite von Betfair** — nicht unseren Pick. Man
sieht dort also nirgends, ob die Börse mit uns übereinstimmt oder gegen uns steht. Genau das ist
aber die Frage, die man kurz vor Anpfiff hat: „unsere Card sagt Auswärtssieg — und das Geld?"

Dieses Skript legt die Brücke: Betfair-Spiel → unsere gepostete Card. Es entscheidet NICHTS und
stuft NICHTS herab. Die Engine bleibt die einzige Instanz, die Picks bewertet
([[feedback_engine_sole_demotion_authority]]); das Terminal bekommt nur Information dazu.

Bewusst die **gepostete** Card aus picks_output.json, nicht eine im Browser neu gerechnete: was
einmal veröffentlicht ist, bleibt stehen ([[feedback_posted_picks_immutable]]).

Read-only, kein Geld.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import betfair_name_bridge as BR
from safe_write import write_json_atomic

BASE = Path(__file__).resolve().parent
CONSENSUS_FILE = BASE / "betfair_consensus.json"
PICKS_FILE     = BASE / "picks_output.json"
OUT_FILE       = BASE / "betfair_card_link.json"

# Welche Seite des 1X2 behauptet ein Pick? Nur DIESE Märkte lassen sich mit der Geld-Seite der
# Börse (home/draw/away) überhaupt vergleichen. Alles andere — Tore, Ecken, BTTS, Halbzeit —
# liegt auf einer anderen Achse und bekommt bewusst KEIN Urteil statt eines erfundenen.
SIDE_OF = {
    "homeWin": ("home",),
    "awayWin": ("away",),
    "dc1X":    ("home", "draw"),
    "dcX2":    ("draw", "away"),
}
# Asiatische Handicaps sind Heim-/Auswärts-Wetten mit Vorgabe — die Richtung ist eindeutig.
_AH_PREFIX = {"ah_home:": ("home",), "ah_away:": ("away",)}


def sides_of(market_key) -> tuple:
    """marketKey → Seiten des 1X2, die der Pick behauptet. Leer = andere Achse. REIN."""
    k = str(market_key or "")
    if k in SIDE_OF:
        return SIDE_OF[k]
    for pre, sides in _AH_PREFIX.items():
        if k.startswith(pre):
            return sides
    return ()


def best_pick(picks) -> dict | None:
    """Die Card eines Spiels kann mehrere Picks tragen. Für die Terminal-Zeile zählt der mit der
    höchsten Konviktion — und bei Gleichstand der, der eine 1X2-Seite behauptet (nur der lässt
    sich mit dem Geld vergleichen). REIN."""
    best, best_key = None, None
    for p in (picks or []):
        if not isinstance(p, dict):
            continue
        try:
            sc = float(p.get("sc") or 0)
        except (TypeError, ValueError):
            sc = 0.0
        key = (round(sc, 6), 1 if sides_of(p.get("marketKey")) else 0)
        if best_key is None or key > best_key:
            best, best_key = p, key
    return best


def verdict(sides, money_side):
    """True = Geld liegt auf unserer Seite, False = dagegen, None = nicht vergleichbar. REIN."""
    if not sides or not money_side:
        return None
    return money_side in sides


def link(games, events, now=None) -> dict:
    """Betfair-Spiele × unsere Card-Events → {matchId: Kartenzeile}. REIN.

    Ohne Treffer steht das Spiel schlicht nicht drin — das Terminal zeigt die Zeile dann wie
    bisher. Ein falscher Treffer waere schlimmer als keiner, deshalb ist die Bruecke eng.
    """
    snaps, fuzzy = {}, {}
    for ev in (events or []):
        if not isinstance(ev, dict):
            continue
        snaps[BR.event_key(ev.get("home"), ev.get("away"))] = ev
        fuzzy.setdefault(str(ev.get("dateIso") or "")[:10], []).append(ev)

    out, n_exact, n_bridge = {}, 0, 0
    for g in (games or []):
        if not isinstance(g, dict):
            continue
        mid = str(g.get("matchId") or "")
        if not mid:
            continue
        day = str(g.get("kickoff") or "")[:10]
        exact = snaps.get(BR.event_key(g.get("home"), g.get("away")))
        ev = exact or BR.find(snaps, fuzzy, g.get("home"), g.get("away"), day)
        if not ev:
            continue
        p = best_pick(ev.get("picks"))
        if not p:
            continue
        sides = sides_of(p.get("marketKey"))
        n_exact, n_bridge = (n_exact + 1, n_bridge) if exact else (n_exact, n_bridge + 1)
        out[mid] = {
            "market": p.get("market"), "marketKey": p.get("marketKey"),
            "odds": p.get("odds"), "sc": p.get("sc"), "conf": p.get("conf"),
            "icon": p.get("icon"), "sides": list(sides),
            "moneySide": g.get("moneySide"),
            "agree": verdict(sides, g.get("moneySide")),
            "nPicks": len([x for x in (ev.get("picks") or []) if isinstance(x, dict)]),
            "matchedBy": "exakt" if exact else "bruecke",
            "cardHome": ev.get("home"), "cardAway": ev.get("away"),
        }
    return {"links": out, "nExact": n_exact, "nBridge": n_bridge}


def candidates(games, events) -> int:
    """Wie viele Boersen-Spiele finden am selben Tag ueberhaupt eine Card-Partie? REIN.

    Nur dafuer da, „0 verlinkt" von „0 verlinkbar" zu unterscheiden. Ohne das sieht ein kaputter
    Link (falscher Pfad, veraltete picks_output) im Terminal genauso aus wie ein ruhiger Dienstag
    ohne Top-5-Spiele — und genau diese Verwechslung ist die tote-Kette-Klasse
    ([[project_poly_surfaces_audit]]: Verdrahtung ist nicht Ankunft).
    """
    days = {str(e.get("dateIso") or "")[:10] for e in (events or []) if isinstance(e, dict)}
    days.discard("")
    return sum(1 for g in (games or [])
               if isinstance(g, dict) and str(g.get("kickoff") or "")[:10] in days)


def _load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "fehlt"
    except Exception as e:
        return None, str(e)


def main() -> int:
    cx, err = _load(CONSENSUS_FILE)
    if err:
        print("ℹ️  %s: %s — kein Kartenlink." % (CONSENSUS_FILE.name, err))
        return 0
    pk, err = _load(PICKS_FILE)
    if err:
        print("ℹ️  %s: %s — kein Kartenlink." % (PICKS_FILE.name, err))
        return 0

    games = (cx or {}).get("games") or []
    events = pk if isinstance(pk, list) else (pk or {}).get("events") or []
    res = link(games, events)
    links = res["links"]

    write_json_atomic(OUT_FILE, {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "nGames": len(games), "nLinked": len(links),
        "nExact": res["nExact"], "nBridge": res["nBridge"],
        "links": links,
    }, indent=1)

    agree = sum(1 for v in links.values() if v.get("agree") is True)
    against = sum(1 for v in links.values() if v.get("agree") is False)
    print("🔗 Terminal-Kartenlink: %d von %d Börsen-Spielen haben eine Card "
          "(%d exakt, %d über die Namens-Brücke)"
          % (len(links), len(games), res["nExact"], res["nBridge"]))
    print("   Geld auf unserer Seite: %d · dagegen: %d · andere Achse: %d"
          % (agree, against, len(links) - agree - against))
    n_cand = candidates(games, events)
    if n_cand and not links:
        # Es gab Spiele am selben Tag wie unsere Cards, aber keinen einzigen Treffer. Das ist
        # kein ruhiger Dienstag, das ist ein Bruch — laut sagen statt still leer bleiben.
        print("⚠️  %d Börsen-Spiele lagen am selben Tag wie unsere Cards, verlinkt wurde KEINES. "
              "Namens-Brücke oder picks_output.json prüfen." % n_cand)
    print("💾 %s" % OUT_FILE.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
