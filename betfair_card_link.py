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

⚠️ 28.08.2026 (Lucas): Erst las das hier `picks_output.json` — das ist das ALTE breite
20-Ligen-System. Im Terminal stand bei Bayern–Stuttgart deshalb „1. HZ: Over 0.5 Tore", ein
Markt, den wir gar nicht mehr anbieten, während die echte Card „Über 3.5 Tore" sagt. Es gibt
ZWEI parallele Pick-Systeme im Repo; die National-Cards kommen aus `liga-data.json`
([[project_verdict_flip_sichtbar]]). Quelle korrigiert.

Read-only, kein Geld.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import betfair_name_bridge as BR
import cocobet_dataset as D
from safe_write import write_json_atomic

BASE = Path(__file__).resolve().parent
CONSENSUS_FILE = BASE / "betfair_consensus.json"
SNAP_FILE      = BASE / "betfair_prices.json"   # Roh-Snapshot mit der ganzen Markt-Leiter
PICKS_FILE     = Path(str(D.data_file()))   # liga-data.json — die Quelle der National-Cards
OUT_FILE       = BASE / "betfair_card_link.json"

# Welche Seite des 1X2 behauptet ein Pick? `liga-data.json` fuehrt nur das deutsche Label,
# keinen marketKey — deshalb ueber das Label. Nur DIESE Maerkte lassen sich mit der Geld-Seite
# der Boerse (home/draw/away) vergleichen. Tore, Ecken, BTTS liegen auf einer anderen Achse und
# bekommen bewusst KEIN Urteil statt eines erfundenen.
SIDE_BY_LABEL = {
    "heimsieg":            ("home",),
    "auswaertssieg":       ("away",),
    "unentschieden":       ("draw",),
    "doppelte chance - 1x": ("home", "draw"),
    "doppelte chance - x2": ("draw", "away"),
}
_UML = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                      "\u2014": "-", "\u2013": "-", "\u2212": "-"})


def _norm_label(x) -> str:
    return " ".join(str(x or "").lower().translate(_UML).split())


def sides_of(market_label) -> tuple:
    """Markt-Label -> Seiten des 1X2, die der Pick behauptet. Leer = andere Achse. REIN."""
    lbl = _norm_label(market_label)
    if lbl in SIDE_BY_LABEL:
        return SIDE_BY_LABEL[lbl]
    # Asiatische Handicaps sind Heim-/Auswaertswetten mit Vorgabe - Richtung eindeutig.
    if lbl.startswith("ah heim"):
        return ("home",)
    if lbl.startswith("ah auswaerts"):
        return ("away",)
    return ()


# ── Tor-/BTTS-Achse (28.08.2026, Lucas) ──────────────────────────────────────
# Zuerst bekamen Ue/U- und BTTS-Picks GAR KEIN Urteil, weil die Konsens-Zeile nur die
# 1X2-Geldseite fuehrt. Lucas: „aber es liegt was oben, 6k — wieso wird das nicht verglichen?"
# Zu Recht: der Roh-Snapshot hat die ganze Leiter. Bayern-Stuttgart, Ue/U 3.5: 7.039 EUR
# gematcht, davon 6.140 auf Over — 87 % auf unserer Seite. Diese Aussage haben wir verschenkt.
_OU_LABEL = re.compile(r"^(ueber|unter)\s+(\d+(?:[.,]5))\s+tore$")


def betfair_target(market_label):
    """Unser Label -> (Betfair-Marktname, Runner-Praefix). None = keine Entsprechung. REIN."""
    lbl = _norm_label(market_label)
    m = _OU_LABEL.match(lbl)
    if m:
        linie = m.group(2).replace(",", ".")
        return ("Over/Under %s Goals" % linie, "Over" if m.group(1) == "ueber" else "Under")
    if lbl.startswith("beide teams treffen"):
        return ("Both teams to Score?", "Yes" if lbl.endswith("ja") else "No")
    return None


def goal_market_money(snap, market_label):
    """Wie viel gematchtes Geld liegt auf UNSERER Seite dieses Tor-/BTTS-Marktes? REIN.

    Konvention wie in der 1X2-Spalte: „Geld-Seite" = der Runner mit dem groesseren gematchten
    Volumen. Auf einer Boerse hat jede gematchte Wette zwei Seiten — das hier ist also eine
    Konvention, keine Naturaussage. Sie ist dieselbe wie nebenan, und darauf kommt es an.

    Gibt {marketName, side, eur, sharePct, agree} oder None (Markt fehlt / kein Geld).
    """
    ziel = betfair_target(market_label)
    if not ziel or not isinstance(snap, dict):
        return None
    name, praefix = ziel
    mk = (snap.get("markets") or {}).get(name)
    if not isinstance(mk, dict):
        return None
    unser = gesamt = 0.0
    for r in (mk.get("runners") or []):
        if not isinstance(r, dict):
            continue          # eine kaputte Zeile darf den ganzen Markt nicht kippen
        try:
            v = float(r.get("vol") or 0)
        except (TypeError, ValueError):
            continue
        gesamt += v
        if str(r.get("name") or "").strip().lower().startswith(praefix.lower()):
            unser += v
    if gesamt <= 0:
        return None
    anteil = unser / gesamt
    return {"marketName": name, "side": praefix, "eur": round(gesamt),
            "sharePct": round(anteil * 100), "agree": anteil > 0.5}


# Nur diese Verdicts sind ueberhaupt „unsere Card" - NOBET ist ausdruecklich KEIN Pick.
LIVE_VERDICTS = ("BET", "ABWÄGEN")


def best_pick(picks) -> dict | None:
    """Die Card eines Spiels traegt mehrere Picks. Fuer die Terminal-Zeile zaehlt: BET vor
    ABWAEGEN, dann hoehere Conviction, dann der, der eine 1X2-Seite behauptet (nur der laesst
    sich mit dem Geld vergleichen). NOBET faellt ganz raus. REIN."""
    best, best_key = None, None
    for p in (picks or []):
        if not isinstance(p, dict) or p.get("verdict") not in LIVE_VERDICTS:
            continue
        try:
            conv = float(p.get("convictionScore") or 0)
        except (TypeError, ValueError):
            conv = 0.0
        key = (1 if p.get("verdict") == "BET" else 0, round(conv, 4),
               1 if sides_of(p.get("market")) else 0)
        if best_key is None or key > best_key:
            best, best_key = p, key
    return best


def verdict(sides, money_side):
    """True = Geld liegt auf unserer Seite, False = dagegen, None = nicht vergleichbar. REIN."""
    if not sides or not money_side:
        return None
    return money_side in sides


def fixtures_index(data) -> list:
    """liga-data.json -> [{home, away, dateIso, picks}]. REIN.

    Der Pick-Schluessel ist `<LIGA>-<Spieltag>-<homeId>-<awayId>` (auch KO-Fixtures mitnehmen —
    dass die in `koFixtures` statt `groups` liegen, hat uns schon mehrfach Picks gekostet,
    [[feedback_ko_datapath]]).
    """
    picks = (data or {}).get("picks") or {}
    out = []

    def _add(code, fx):
        if not isinstance(fx, dict):
            return
        key = "%s-%s-%s-%s" % (code, fx.get("matchday"), fx.get("home"), fx.get("away"))
        out.append({"home": fx.get("homeName") or fx.get("home"),
                    "away": fx.get("awayName") or fx.get("away"),
                    "dateIso": str(fx.get("date") or "")[:10],
                    "kickoff": fx.get("kickoff"),
                    "picks": picks.get(key) or []})

    for code, g in ((data or {}).get("groups") or {}).items():
        for fx in (g.get("fixtures") or []):
            _add(code, fx)
    for fx in ((data or {}).get("koFixtures") or []):
        _add(str(fx.get("round") or "KO"), fx)
    return out


def link(games, fixtures, snaps_by_id=None, now=None) -> dict:
    """Betfair-Spiele × unsere Liga-Fixtures → {matchId: Kartenzeile}. REIN.

    Ohne Treffer steht das Spiel schlicht nicht drin — das Terminal zeigt die Zeile dann wie
    bisher. Ein falscher Treffer waere schlimmer als keiner, deshalb ist die Bruecke eng.
    """
    snaps, fuzzy = {}, {}
    for ev in (fixtures or []):
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
        sides = sides_of(p.get("market"))   # liga-data hat keinen marketKey, nur das Label
        # Liegt der Pick nicht auf der 1X2-Achse, gegen den passenden Tor-/BTTS-Markt pruefen
        # statt gar kein Urteil zu faellen (28.08.2026, Lucas).
        tor = None
        if not sides:
            tor = goal_market_money((snaps_by_id or {}).get(mid), p.get("market"))
        n_exact, n_bridge = (n_exact + 1, n_bridge) if exact else (n_exact, n_bridge + 1)
        out[mid] = {
            "market": p.get("market"),
            "odds": p.get("odds"), "sc": p.get("convictionScore"), "conf": p.get("conf"),
            "icon": p.get("icon"), "sides": list(sides),
            "moneySide": g.get("moneySide"),
            "agree": verdict(sides, g.get("moneySide")) if sides else (tor["agree"] if tor else None),
            "achse": "1X2" if sides else ("tor" if tor else None),
            "torMarkt": (tor or {}).get("marketName"),
            "torSeite": (tor or {}).get("side"),
            "torEur": (tor or {}).get("eur"),
            "torSharePct": (tor or {}).get("sharePct"),
            "verdict": p.get("verdict"),
            "nPicks": len([x for x in (ev.get("picks") or [])
                           if isinstance(x, dict) and x.get("verdict") in LIVE_VERDICTS]),
            "matchedBy": "exakt" if exact else "bruecke",
            "cardHome": ev.get("home"), "cardAway": ev.get("away"),
        }
    return {"links": out, "nExact": n_exact, "nBridge": n_bridge}


def candidates(games, fixtures) -> int:
    """Wie viele Boersen-Spiele finden am selben Tag ueberhaupt eine Card-Partie? REIN.

    Nur dafuer da, „0 verlinkt" von „0 verlinkbar" zu unterscheiden. Ohne das sieht ein kaputter
    Link (falscher Pfad, veraltete picks_output) im Terminal genauso aus wie ein ruhiger Dienstag
    ohne Top-5-Spiele — und genau diese Verwechslung ist die tote-Kette-Klasse
    ([[project_poly_surfaces_audit]]: Verdrahtung ist nicht Ankunft).
    """
    days = {str(e.get("dateIso") or "")[:10] for e in (fixtures or []) if isinstance(e, dict)}
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

    snap, snap_err = _load(SNAP_FILE)
    if snap_err:
        print("ℹ️  %s: %s — Tor-Märkte werden nicht verglichen." % (SNAP_FILE.name, snap_err))
    _ms = (snap or {}).get("matches") if isinstance(snap, dict) else snap
    _items = list(_ms.values()) if isinstance(_ms, dict) else (_ms or [])
    snaps_by_id = {str(m.get("matchId")): m for m in _items
                   if isinstance(m, dict) and m.get("matchId")}

    games = (cx or {}).get("games") or []
    fixtures = fixtures_index(pk)
    res = link(games, fixtures, snaps_by_id)
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
    n_tor = sum(1 for v in links.values() if v.get("achse") == "tor")
    print("   Geld auf unserer Seite: %d · dagegen: %d · ohne Urteil: %d   (davon %d über den Tor-Markt beurteilt)"
          % (agree, against, len(links) - agree - against, n_tor))
    n_cand = candidates(games, fixtures)
    if n_cand and not links:
        # Es gab Spiele am selben Tag wie unsere Cards, aber keinen einzigen Treffer. Das ist
        # kein ruhiger Dienstag, das ist ein Bruch — laut sagen statt still leer bleiben.
        print("⚠️  %d Börsen-Spiele lagen am selben Tag wie unsere Cards, verlinkt wurde KEINES. "
              "Namens-Brücke oder picks_output.json prüfen." % n_cand)
    print("💾 %s" % OUT_FILE.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
