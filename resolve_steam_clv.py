#!/usr/bin/env python3
"""
resolve_steam_clv.py — CLV-Tracking für Steam-Card-Picks (Lucas' Modell, 14.06.2026).

Closing Line Value ist der ehrliche Nordstern für Steam-Following: hat der scharfe
Schluss-Kurs unseren Einstieg bestätigt? Pro gespieltem Steam-Pick:
    clvPP = (Pinnacle-Closing-Wahrscheinlichkeit der Pick-Seite − 1/Einstiegsquote) · 100
  • positiv = Linie ist NACH unserem Einstieg weiter in Pick-Richtung gelaufen → wir haben
    den Closing-Kurs geschlagen (gut, unabhängig vom Spielausgang).
  • Über viele Picks misst der Durchschnitt, ob die Steam-These echten Vorsprung hat —
    verlässlicher als Win/Loss (rechnet die Varianz raus).

ISOLIERT: liest/schreibt nur wm2026-data.json (clvPP auf Steam-Picks). Rührt den
komplexen Bets-/Trade-Resolver NICHT an. Wiederverwendet dessen geprüfte Helfer
(build_result_lookup, get_pinn_close_for_market) als single source of truth.

Lauf nach den Ergebnissen (z.B. in fetch-results-Workflow nach resolve_wm_results).
"""
from __future__ import annotations
import json
import os
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).parent
# Dataset-Modus (Single Source: cocobet_dataset): Liga → CLV auf liga-data.json.
WM = D.data_file()

try:
    from resolve_wm_results import build_result_lookup, get_pinn_close_for_market
except Exception as e:  # pragma: no cover
    build_result_lookup = None
    get_pinn_close_for_market = None
    _IMPORT_ERR = e


def steam_clv_pp(pinn_close_prob, entry_odd):
    """CLV in pp: Pinnacle-Closing-Prob der Pick-Seite vs implizite Einstiegsquote.

    ⚠️ Diese Zahl vergleicht ENTVIGT gegen VIGT und ist deshalb systematisch zu niedrig —
    Erklaerung und Messung stehen bei `fair_clv_pp()`. Sie bleibt unveraendert, damit die
    Historie eine Definition behaelt; die ehrliche Zahl steht daneben in `clvFairPP`.
    """
    if not pinn_close_prob or not entry_odd or entry_odd <= 1.0:
        return None
    return round((pinn_close_prob - 1.0 / entry_odd) * 100, 2)


# ── 🔴 12.09.2026 (Lucas: „wir koennen keine guten CLV haben wenn wir die picks erst am selben
#     tag posten — wie soll das gehen?") ────────────────────────────────────────────────────────
#
# Der Einwand stimmte im Ergebnis, aber nicht in der Ursache. Ein spaeter Einstieg macht den CLV
# KLEINER in beide Richtungen, nicht systematisch negativ. Die Systematik kam von hier:
#
#     clvPP = Pinnacle-Closing-FAIR-Wahrscheinlichkeit − 1/Einstiegsquote
#                                ^^^^                    ^^^^^^^^^^^^^^^^
#                          power-entvigt               ROH, mit voller Marge
#
# Wir ziehen uns also die Marge unseres eigenen Buchs vom CLV ab. Der Fingerabdruck ist eindeutig:
#
#     Einstieg bei soft     (Overround 6,6 %)   n=90   Ø CLV −1,56 pp   Median −1,15
#     Einstieg bei Pinnacle (Overround 4,4 %)   n=12   Ø CLV −0,41 pp   Median  ±0,00
#
# Kaeme es vom Postzeitpunkt, traefe es beide Buecher gleich. Es skaliert aber mit der Marge.
# An den 29 Liga-1X2-Picks mit eindeutig zuordenbarem Einstiegs-Snapshot, beide Seiten
# power-entvigt: aus Ø −1,60 pp wird **+0,32 pp** (Band −0,77 … +1,41), und wir schlagen den
# Close in 62 % statt 31 % der Picks. Also: nicht negativ, aber auch nicht belegt positiv.
#
# `clvPP` bleibt wie es war — eine Zahl mitten in der Historie umzudefinieren wuerde alte und
# neue Zeilen vermischen. Die ehrliche Zahl kommt als `clvFairPP` daneben, mit `clvBasis`, das
# sagt, woher die Einstiegs-Wahrscheinlichkeit stammt. Welche Zahl Stats-Seite und Lernstrom
# benutzen, ist eine eigene Entscheidung und keine Nebenwirkung dieses Fixes.

# Welche Felder im Snapshot bilden den Markt, und welches davon ist UNSERE Seite?
# 1X2 und Doppelte Chance teilen sich dieselben drei Quoten — die DC-Wahrscheinlichkeit ist die
# Summe zweier entvigter 1X2-Seiten und damit exakt, nicht geschaetzt.
_MAERKTE = {
    "Heimsieg":             (("hw", "dr", "aw"), (0,)),
    "Unentschieden":        (("hw", "dr", "aw"), (1,)),
    "Auswärtssieg":         (("hw", "dr", "aw"), (2,)),
    "Auswartssieg":         (("hw", "dr", "aw"), (2,)),
    "Doppelte Chance — 1X": (("hw", "dr", "aw"), (0, 1)),
    "Doppelte Chance — X2": (("hw", "dr", "aw"), (1, 2)),
    "Doppelte Chance — 12": (("hw", "dr", "aw"), (0, 2)),
    "Über 1.5 Tore":        (("o15", "u15"), (0,)),
    "Unter 1.5 Tore":       (("o15", "u15"), (1,)),
    "Über 2.5 Tore":        (("o25", "u25"), (0,)),
    "Unter 2.5 Tore":       (("o25", "u25"), (1,)),
    "Über 3.5 Tore":        (("o35", "u35"), (0,)),
    "Unter 3.5 Tore":       (("o35", "u35"), (1,)),
    "BTTS Ja":              (("bttsY", "bttsN"), (0,)),
    "BTTS Nein":            (("bttsY", "bttsN"), (1,)),
}
# Das Feld, ueber das wir den Einstiegs-Snapshot wiederfinden (unser eigener Preis).
_EIGENES_FELD = {name: felder[idx[0]] for name, (felder, idx) in _MAERKTE.items()
                 if len(idx) == 1}


def _markt_felder(markt_name):
    return _MAERKTE.get(str(markt_name))


def fair_entry_prob(markt, markt_name, devig=None):
    """Faire (entvigte) Wahrscheinlichkeit UNSERER Seite aus dem vollen Einstiegsmarkt.

    `markt` ist ein Snapshot desselben Buchs zum Einstiegszeitpunkt. None, wenn der Markt nicht
    vollstaendig ist — geraten wird nichts.

    12.09.2026: anfangs nur 1X2. Gemessen am Liga-Ledger deckte das **29 von 87** Zeilen mit
    gemessenem CLV ab; die restlichen 58 waren Ueber/Unter (34), Doppelte Chance (21) und AH (3).
    Der Quotenverlauf traegt o15/u15, o25/u25, o35/u35 und BTTS seit dem 06.09. mit — sie fehlten
    hier, nicht in den Daten. Asian Handicap bleibt draussen: dafuer gibt es keine Gegenseite im
    Verlauf, und eine geschaetzte waere genau die erfundene Zahl, die dieser ganze Fix beseitigt.
    """
    spez = _markt_felder(markt_name)
    if spez is None or not isinstance(markt, dict):
        return None
    felder, idx = spez
    quoten = [markt.get(f) for f in felder]
    if not all(isinstance(q, (int, float)) and q > 1 for q in quoten):
        return None
    if devig is None:
        try:
            from resolve_wm_results import power_devig as devig
        except Exception:
            return None
    fair = devig(*quoten)
    if len(fair) != len(felder):
        return None
    return sum(fair[i] for i in idx)


def fair_clv_pp(pinn_close_prob, entry_fair_prob):
    """CLV in pp mit beiden Seiten auf derselben Basis: fair gegen fair."""
    if not pinn_close_prob or not entry_fair_prob:
        return None
    return round((pinn_close_prob - entry_fair_prob) * 100, 2)


def einstiegs_markt(verlauf, entry_odd, markt_name, buch, toleranz=0.06):
    """Den Snapshot suchen, dessen Preis fuer UNSERE Seite dem Einstieg am naechsten liegt.

    Ohne Treffer innerhalb der Toleranz: None. Ein „ungefaehr passender" Markt waere hier
    schlimmer als keiner — er wuerde die Korrektur erfinden statt sie zu messen.

    Doppelte Chance hat im Verlauf keinen eigenen Preis (sie wird aus 1X2 abgeleitet). Dafuer
    laesst sich der Einstieg nicht ueber den Preis wiederfinden — solche Zeilen bleiben ohne
    faire Zahl, statt an einem beliebigen Snapshot festgemacht zu werden.
    """
    spez = _markt_felder(markt_name)
    feld = _EIGENES_FELD.get(str(markt_name))
    if spez is None or feld is None or not isinstance(verlauf, list) or not entry_odd:
        return None
    felder = spez[0]
    bester, abstand = None, None
    for s in verlauf:
        if not isinstance(s, dict) or str(s.get("bk")) != str(buch):
            continue
        if not all(isinstance(s.get(k), (int, float)) and s[k] > 1 for k in felder):
            continue
        d = abs(s[feld] - entry_odd)
        if abstand is None or d < abstand:
            bester, abstand = s, d
    return bester if (abstand is not None and abstand <= toleranz) else None


def _verlauf_laden():
    """Quotenverlauf des aktiven Datensatzes ({} wenn es ihn nicht gibt). Nur fuer clvFairPP."""
    try:
        pfad = D.file("wm2026-odds-history.json", "liga-odds-history.json")
        if not pfad.exists():
            return {}
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        return daten if isinstance(daten, dict) else {}
    except Exception:
        return {}


def resolve(wm: dict, verlauf: dict = None) -> int:
    """Setzt clvPP auf jedem aufgelösten Steam-Pick. Gibt die Anzahl gesetzter CLVs zurück.

    Zusaetzlich `clvFairPP` — beide Seiten entvigt — wo der Einstiegsmarkt auffindbar ist.
    `clvBasis` sagt, welche der beiden Zahlen worauf beruht; „roh" heisst: kein Einstiegsmarkt
    gefunden, also gibt es keine faire Zahl und wir erfinden auch keine.
    """
    if build_result_lookup is None:
        return 0
    if verlauf is None:
        verlauf = _verlauf_laden()
    lookup = build_result_lookup(wm)
    picks = wm.get("picks") or {}
    n = 0
    for key, plist in picks.items():
        if not isinstance(plist, list):
            continue
        parts = key.split("-")
        res = lookup.get(f"{parts[2]}-{parts[3]}", {}) if len(parts) >= 4 else {}
        if not res:
            continue   # Spiel noch nicht aufgelöst
        for p in plist:
            if p.get("source") != "steam":
                continue
            entry = p.get("entryOdd") or p.get("odds")
            pinn_close = get_pinn_close_for_market(res, p.get("market", ""))
            clv = steam_clv_pp(pinn_close, entry)
            if clv is not None:
                p["clvPP"] = clv
                p["clvResolved"] = True
                n += 1
                # Die ehrliche Zahl daneben — nur wenn der Einstiegsmarkt wirklich gefunden wird.
                spiel = "-".join(key.split("-")[-2:])
                buch = "pinnacle" if str(p.get("entryBook")) == "pini" else "public"
                markt = einstiegs_markt(verlauf.get(spiel), entry, p.get("market"), buch)
                fair = fair_entry_prob(markt, p.get("market"))
                fclv = fair_clv_pp(pinn_close, fair)
                if fclv is not None:
                    p["clvFairPP"] = fclv
                    p["clvBasis"] = "fair"
                else:
                    p["clvBasis"] = "roh"
    return n


def main() -> None:
    if build_result_lookup is None:
        print(f"❌ Import aus resolve_wm_results fehlgeschlagen: {_IMPORT_ERR}")
        return
    wm = json.loads(WM.read_text(encoding="utf-8"))
    n = resolve(wm)
    if n:
        WM.write_text(json.dumps(wm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Steam-CLV gesetzt für {n} aufgelöste Pick(s)")


if __name__ == "__main__":
    main()
