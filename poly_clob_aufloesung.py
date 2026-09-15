#!/usr/bin/env python3
"""
poly_clob_aufloesung.py — 15.09.2026 (Lucas): ZWEITE Quelle fuer Markt-Auflösungen — der CLOB.

🔴 Warum es das gibt. Am 14.09. lief $5 echtes Geld auf `lol-big1-koia-2026-09-14|BIG`. Das Spiel
war laengst vorbei, die Position stand weiter auf `placed`. Grund: `poly_resolutions.json` wird auf
genau zwei Wegen gefuellt, und BEIDE haben denselben blinden Fleck.

    update_resolutions()          aus den Maerkten des AKTUELLEN Scans. Ein beendeter Markt
                                  taucht in den Tag-Seiten nicht mehr auf -> nie.
    backfill_resolutions_by_slug  schlaegt gezielt per Slug nach — iteriert aber AUSSCHLIESSLICH
                                  ueber Keys aus poly_money_broad_close.json.

Der Broad-Scan friert nur Maerkte ueber MIN_VOL_USD = 7500 ein. Der Shortlist-Emitter findet seine
Plays unabhaengig davon. Ein Play, den nur der Emitter kennt, steht nie im Close-File — und wird
deshalb NIE nachgeschlagen. Nicht „nicht gefunden": nicht gefragt.

Der Befund am 15.09.2026 in den echten Dateien:

    unaufloesbar verfallen, Grund „nicht getrackt"                       4 Plays
    davon lol-gx-navi-2026-09-11 — von Gamma JETZT voll aufgeloest       (wir haben nie gefragt)
    offen und auf demselben Weg (BIG $5 echtes Geld, Shakhtar)           2 Plays

Deshalb hier ein Nachschlag, der an der conditionId haengt statt am Close-File:

  * `cond` haben wir bei JEDER Position — der Emitter schreibt sie, und gekauft haben wir ueber
    genau diesen Markt. Sie nagelt EINEN Markt eines Buendels fest (siehe poly_slug_urteil).
  * Der CLOB ist die Quelle, ueber die der Handel lief. Gamma kann einen Event nicht ausliefern
    (fuer BIG kam eine leere Liste zurueck) — der CLOB lieferte `closed: true` und `winner: true`
    auf ⁠Movistar KOI Fénix in EINEM Call.

Grundsatz wie ueberall im Repo: ein Waechter, der raet, ist keiner. Zwei Gewinner-Flags, ein
offener Markt oder ein uneindeutiger Preis ergeben KEINE Auflösung, sondern einen Grund.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import poly_offen as PO
from poly_slug_urteil import aufloesbar

BASE = Path(__file__).resolve().parent

CLOB_MARKT = "https://clob.polymarket.com/markets/{cond}"
RES_FILE = "poly_resolutions.json"
TRACK_FILE = "poly_shortlist_track.json"

# Deckel je Lauf. Der Scan laeuft haeufig; was heute nicht drankommt, kommt naechsten Lauf dran.
MAX_CALLS = int(os.environ.get("POLY_CLOB_RESOLVE_MAX") or 40)
# Settlement-Preise liegen bei 0.0/1.0. Toleranz wie in poly_money_broad.winner_from_prices.
PREIS_TOL = 0.02


def _jetzt():
    return datetime.now(timezone.utc)


# ── Urteil ─────────────────────────────────────────────────────────────────────────────────
def sieger_aus_markt(payload, tol: float = PREIS_TOL) -> tuple:
    """(Sieger-Label | None, Grund). REIN/testbar.

    Reihenfolge mit Absicht: erst das ausdrueckliche `winner`-Flag des CLOB, dann ersatzweise der
    Settlement-Preis. Ein Markt ohne `closed` hat KEINEN Sieger — auch wenn ein Preis schon bei
    0.99 steht. Unklarheit gibt einen Grund zurueck, nie eine Vermutung.
    """
    if not isinstance(payload, dict):
        return None, "keine Antwort"
    toks = payload.get("tokens")
    if not isinstance(toks, list) or not toks:
        return None, "keine Outcomes"
    if not payload.get("closed"):
        return None, "Markt noch offen"

    gewinner = [t for t in toks if isinstance(t, dict) and t.get("winner") is True]
    if len(gewinner) > 1:
        # Darf nicht vorkommen — und wenn doch, ist Raten schlimmer als Warten.
        return None, "mehrere Gewinner-Flags"
    if len(gewinner) == 1:
        label = str(gewinner[0].get("outcome") or "").strip()
        return (label, "") if label else (None, "Gewinner ohne Namen")

    preise = {}
    for t in toks:
        if not isinstance(t, dict):
            continue
        label = str(t.get("outcome") or "").strip()
        if not label:
            continue
        try:
            preise[label] = float(t.get("price"))
        except (TypeError, ValueError):
            continue
    nah = [k for k, p in preise.items() if p >= 1.0 - tol]
    if len(nah) == 1:
        return nah[0], ""
    return None, "nicht eindeutig aufgeloest"


# ── Kandidaten ─────────────────────────────────────────────────────────────────────────────
def _laden(pfad):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        return False


def offene_kandidaten(base_dir) -> list:
    """Offene Positionen, die eine Auflösung brauchen. → [{key, cond, seite, echt, seit}]

    Zwei Quellen, absichtlich beide: der Paper-Track (dort steht die `cond`) und die echten
    Wett-Dateien (dort liegt das Geld). Eine Position, die nur in der Wett-Datei steht, faellt
    sonst wieder durch — genau der Fehler, den dieses Modul schliesst.
    """
    nach_key = {}

    def _merken(key, cond, seite, echt, seit):
        if not key:
            return
        e = nach_key.setdefault(str(key), {"key": str(key), "cond": None, "seite": None,
                                           "echt": False, "seit": None})
        if cond and not e["cond"]:
            e["cond"] = str(cond)
        if seite and not e["seite"]:
            e["seite"] = str(seite)
        if echt:
            e["echt"] = True
        if seit and (e["seit"] is None or str(seit) < e["seit"]):
            e["seit"] = str(seit)

    track = _laden(os.path.join(base_dir, TRACK_FILE))
    if isinstance(track, dict):
        for e in (track.get("open") or {}).values():
            if isinstance(e, dict):
                _merken(e.get("key"), e.get("cond"), e.get("side"), False, e.get("firstTs"))

    for pfx in PO.DATENSATZ_PRAEFIXE:
        d = _laden(os.path.join(base_dir, f"{pfx}auto_bets_placed.json"))
        if not isinstance(d, dict):
            continue
        for b in (d.get("bets") or []):
            if isinstance(b, dict) and PO.ist_offen(b):
                _merken(b.get("key"), b.get("cond"), b.get("side"), True, b.get("placedAt"))

    # Echtes Geld zuerst, dann das Aelteste — das Call-Budget gehoert den Positionen, bei denen
    # eine fehlende Auflösung tatsaechlich etwas kostet.
    return sorted(nach_key.values(),
                  key=lambda e: (not e["echt"], e["seit"] or "9999"))


# ── Nachschlag ─────────────────────────────────────────────────────────────────────────────
def nachschlagen(kandidaten, get, schon=None, cap: int = MAX_CALLS, jetzt=None) -> tuple:
    """(neue Auflösungen {key: {winner, ts, quelle}}, offene Faelle [{key, echt, grund}]).

    REIN/testbar (`get` injizierbar), defensiv (wirft nie), gedeckelt (cap Calls je Lauf).
    """
    jetzt = jetzt or _jetzt()
    schon = schon if isinstance(schon, dict) else {}
    neu, probleme, calls = {}, [], 0
    for e in (kandidaten or []):
        if not isinstance(e, dict):
            continue
        key = e.get("key")
        if not key or key in schon or key in neu:
            continue
        cond = e.get("cond")
        if not cond:
            probleme.append({"key": key, "echt": bool(e.get("echt")),
                             "grund": "keine conditionId"})
            continue
        if calls >= cap:
            probleme.append({"key": key, "echt": bool(e.get("echt")),
                             "grund": "Call-Budget erschoepft"})
            continue
        calls += 1
        try:
            payload = get(CLOB_MARKT.format(cond=cond))
        except Exception as exc:
            probleme.append({"key": key, "echt": bool(e.get("echt")),
                             "grund": f"Abruf fehlgeschlagen: {exc}"})
            continue
        sieger, grund = sieger_aus_markt(payload)
        if not sieger:
            probleme.append({"key": key, "echt": bool(e.get("echt")),
                             "grund": grund or "kein Sieger"})
            continue
        # Buendel-Schutz: mit `cond` ist derselbe Markt gemeint wie beim Erfassen. Ohne sie waeren
        # wir hier gar nicht — die Pruefung steht trotzdem da, damit die Regel EINE bleibt.
        if not aufloesbar(key, e.get("seite") or sieger, sieger, cond=cond):
            probleme.append({"key": key, "echt": bool(e.get("echt")),
                             "grund": "Buendel ohne festgenagelten Markt"})
            continue
        neu[key] = {"winner": sieger, "ts": jetzt.isoformat(), "quelle": "clob"}
    return neu, probleme


def bericht(neu, probleme) -> str:
    """Eine Zeile je Lauf, plus die echten Faelle namentlich. REIN/testbar."""
    zeilen = [f"🔎 CLOB-Nachschlag: {len(neu)} Auflösung(en) gefunden, "
              f"{len(probleme)} offen geblieben"]
    for k, v in sorted(neu.items()):
        zeilen.append(f"   ✅ {k} → {v['winner']}")
    for p in probleme:
        if p.get("echt"):
            zeilen.append(f"   ⚠️  {p['key']} (ECHTES GELD): {p['grund']}")
    return "\n".join(zeilen)


def main() -> int:
    print("=== poly_clob_aufloesung.py ===")
    from poly_money_broad import _get                     # dieselbe HTTP-Schicht (Retry/Backoff)
    from safe_write import write_json_atomic

    res = _laden(os.path.join(str(BASE), RES_FILE))
    if res is False:
        print("  🛑 poly_resolutions.json nicht lesbar — nichts nachgeschlagen. "
              "Eine kaputte Datei heisst nicht „keine Auflösungen\".")
        return 0
    res = res if isinstance(res, dict) else {}

    kand = offene_kandidaten(str(BASE))
    echt_n = sum(1 for e in kand if e["echt"])
    print(f"  {len(kand)} offene Position(en) geprueft, davon {echt_n} mit echtem Geld")

    neu, probleme = nachschlagen(kand, _get, schon=res)
    print(bericht(neu, probleme))
    if neu:
        res.update(neu)
        write_json_atomic((BASE / RES_FILE), res, indent=1)
        print(f"  💾 poly_resolutions.json fortgeschrieben ({len(res)} Eintraege)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
