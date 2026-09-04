#!/usr/bin/env python3
# poly_whale_follow.py — 24.08.2026 (Lucas): Papier-Depot fürs NACHSPIELEN der Top-20-Whales.
#
# Der Whales-Tab im Betting-Menü zeigt die noch spielbaren offenen Positionen der schärfsten Wallets.
# Die spannende Frage ist aber nicht „was halten die gerade", sondern **bringt Nachspielen etwas** —
# und zwar zu UNSEREM Einstiegspreis, nicht ihrem. Die Whales sind früher drin; wenn der Move bis zu
# uns gelaufen ist, ist die Kante weg. Genau diese Lücke misst dieses Depot: Einstieg = der Preis, den
# WIR beim ersten Sehen zahlen würden.
#
# ⚠️ Methodischer Vorbehalt, der hier hingehört: die Top-20 werden mit Rückblick auf dieselbe Historie
# ausgewählt, aus der ihre P&L stammt. Dass sie in der Vergangenheit gewonnen haben, ist also KEIN
# Beweis für die Zukunft. Dieses Depot ist der einzige Weg, das vorwärts zu prüfen.
#
# Rechenweg IDENTISCH zum Shortlist-Depot (poly_shortlist_track): Aktien = stake/entry, Gewinner
# zahlt 1.00/Aktie, CLV = (Schluss − Einstieg) × 100. Nur so sind die Flächen vergleichbar.
# Setzt und sendet NICHTS.
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from poly_shortlist_track import _agg_one, _age_days, _ok_price, load_emit
from safe_write import write_json_atomic   # 25.08.2026: temp+replace statt halber Datei
from poly_slug_urteil import aufloesbar   # 04.09.2026: Buendel-Slugs nicht raten

BASE = Path(__file__).resolve().parent

CLOSE_FILE = "poly_money_broad_close.json"
RES_FILE = "poly_resolutions.json"
TRACK_FILE = "poly_whale_follow_track.json"

STAKE = float(os.environ.get("WHALE_FOLLOW_STAKE") or 10.0)
SETTLED_KEEP = 500
UNTRACKED_TTL_D = float(os.environ.get("WHALE_FOLLOW_UNTRACKED_TTL_D") or 2)
STALE_TTL_D = float(os.environ.get("WHALE_FOLLOW_STALE_TTL_D") or 14)


def _now():
    return datetime.now(timezone.utc)


def _load(name, base=None):
    try:
        return json.loads(((base or BASE) / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def update_track(prev, emit, close, resolutions, now=None, stake=STAKE) -> dict:
    """REIN/testbar. Öffnet neue Whale-Plays, zieht lastPrice mit, rechnet auf. Ein Play = (key, side).

    `consensusAtEntry` friert ein, wie viele Top-Wallets beim ERSTEN Sehen auf der Seite lagen —
    steigt der Konsens später, ändert das den Play nicht mehr (sonst wäre es Rückblick).
    """
    now = now or _now()
    prev = prev if isinstance(prev, dict) else {}
    open_ = {k: dict(v) for k, v in (prev.get("open") or {}).items() if isinstance(v, dict)}
    settled = [dict(s) for s in (prev.get("settled") or []) if isinstance(s, dict)]
    settled_keys = {(s.get("key"), s.get("side")) for s in settled}

    # 1) Neue Plays öffnen — Einstieg ist UNSER Preis jetzt, nicht der der Whales.
    for pl in ((emit or {}).get("whales") or []):
        key, side = pl.get("key"), pl.get("side")
        if not key or not side:
            continue
        ok = f"{key}|{side}"
        if ok in open_ or (key, side) in settled_keys:
            continue
        price = pl.get("price")
        if not _ok_price(price):
            price = ((close.get(key) or {}).get("prices") or {}).get(side)
        if not _ok_price(price):
            continue                      # kein sauberer Einstiegspreis → nicht öffnen
        open_[ok] = {
            "key": key, "side": side, "league": pl.get("league"), "cat": pl.get("cat"),
            "entryPrice": round(float(price), 4), "lastPrice": round(float(price), 4),
            "firstTs": now.isoformat(), "lastTs": now.isoformat(),
            "consensusAtEntry": int(pl.get("n") or 1),
            # 24.08.2026 (Lucas' INOX-Fall): stand beim Einstieg eine andere Top-Wallet auf der
            # Gegenseite? Eingefroren wie der Konsens — sonst wäre es Rückblick. Damit lässt sich
            # später MESSEN, ob Konflikt-Plays wirklich schlechter laufen, statt es anzunehmen.
            "conflictAtEntry": bool(pl.get("conflict")),
            "againstRankAtEntry": pl.get("againstRank"),
            "bestRankAtEntry": int(pl.get("bestRank") or 0) or None,
            "whaleEntryAvg": pl.get("entryAvg"), "whaleUsd": pl.get("usd"),
            "htkAtEntry": pl.get("htk"), "stake": stake,
        }

    # 2) lastPrice nachziehen (Schluss-Referenz für den CLV)
    for e in open_.values():
        cp = ((close.get(e["key"]) or {}).get("prices") or {}).get(e["side"]) if isinstance(close, dict) else None
        if _ok_price(cp):
            e["lastPrice"] = round(float(cp), 4)
            e["lastTs"] = now.isoformat()

    # 3) Abrechnen, sobald der Slug aufgelöst ist
    for ok in list(open_.keys()):
        e = open_[ok]
        r = resolutions.get(e["key"]) if isinstance(resolutions, dict) else None
        winner = (r or {}).get("winner")
        # 04.09.2026: ein Buendel-Slug ("-more-markets") kann Over 1,5 und Over 2,5 nicht
        # auseinanderhalten. Wo der Sieger-Name die Linie nicht traegt, wird NICHT
        # abgerechnet — der Eintrag bleibt offen statt einen Ausgang zu erfinden.
        if winner and not aufloesbar(e["key"], e.get("side"), winner):
            winner = None
        if not winner:
            continue
        entry, st = float(e["entryPrice"]), float(e.get("stake") or stake)
        win = (e["side"] == winner)
        pnl = (st / entry - st) if win else -st
        close_ref = float(e.get("lastPrice") or entry)
        settled.append({
            "key": e["key"], "side": e["side"], "league": e.get("league"), "cat": e.get("cat"),
            "entryPrice": round(entry, 4), "closePrice": round(close_ref, 4),
            "result": "win" if win else "loss", "winner": winner,
            "pnl": round(pnl, 2), "clvPP": round((close_ref - entry) * 100, 2), "stake": st,
            "consensusAtEntry": e.get("consensusAtEntry"), "bestRankAtEntry": e.get("bestRankAtEntry"),
            "conflictAtEntry": e.get("conflictAtEntry"), "againstRankAtEntry": e.get("againstRankAtEntry"),
            # Die Kernzahl: wie viel vom Move war schon weg, als wir eingestiegen sind?
            "whaleEntryAvg": e.get("whaleEntryAvg"),
            "lagPP": (round((entry - float(e["whaleEntryAvg"])) * 100, 2)
                      if _ok_price(e.get("whaleEntryAvg")) else None),
            "firstTs": e.get("firstTs"), "settledTs": now.isoformat(), "resolvedTs": (r or {}).get("ts"),
        })
        del open_[ok]

    # 4) Unauflösbares verfallen lassen — KEIN Fake-Ergebnis (wie im Shortlist-Depot).
    n_expired = 0
    for ok in list(open_.keys()):
        e = open_[ok]
        age = _age_days(e.get("firstTs"), now)
        if age is None:
            continue
        tracked = isinstance(close, dict) and e.get("key") in close
        if age > (STALE_TTL_D if tracked else UNTRACKED_TTL_D):
            del open_[ok]
            n_expired += 1

    settled = settled[-SETTLED_KEEP:]
    return {"updatedAt": now.isoformat(), "stake": stake, "expired": n_expired,
            "open": open_, "settled": settled, "agg": aggregate(settled)}


def aggregate(settled) -> dict:
    rows = [r for r in (settled or []) if isinstance(r, dict) and r.get("result")]
    solo = [r for r in rows if int(r.get("consensusAtEntry") or 1) < 2]
    cons = [r for r in rows if int(r.get("consensusAtEntry") or 1) >= 2]
    by_cat = {}
    for r in rows:
        by_cat.setdefault(str(r.get("cat") or "?"), []).append(r)
    confl = [r for r in rows if r.get("conflictAtEntry")]
    clean = [r for r in rows if not r.get("conflictAtEntry")]
    lags = [float(r["lagPP"]) for r in rows if isinstance(r.get("lagPP"), (int, float))]
    out = _agg_one(rows) if rows else {"n": 0, "wins": 0, "hit": 0.0, "pnl": 0.0,
                                       "stake": 0.0, "roi": 0.0, "clvAvg": 0.0}
    out["lagAvg"] = round(sum(lags) / len(lags), 2) if lags else None   # Ø verpasster Move in pp
    return {"all": out,
            "solo": _agg_one(solo) if solo else None,
            "consensus": _agg_one(cons) if cons else None,
            # Die eigentliche Frage hinter dem Konflikt-Flag: laufen diese Plays messbar schlechter?
            "conflict": (_agg_one(confl) if confl else None),
            "clean": (_agg_one(clean) if clean else None),
            "byCat": {k: _agg_one(v) for k, v in sorted(by_cat.items())}}


def write_from_emit(emit, close=None, resolutions=None, now=None, base=None) -> dict:
    """Aus einem BEREITS geladenen Emitter-Output schreiben. So muss der Scan node/jsdom nur EINMAL
    starten (poly_shortlist_track ruft das mit demselben `emit` auf).

    `base` MUSS durchgereicht werden: die main()-Tests von poly_shortlist_track monkeypatchen
    dessen BASE auf ein tmp-Verzeichnis. Ohne das schreibt der Hook beim Testlauf in die echte
    Repo-Wurzel — Pipeline-Output lokal erzeugt, genau was hier verboten ist.
    """
    base = base or BASE
    close = close if isinstance(close, dict) else _load(CLOSE_FILE, base)
    resolutions = resolutions if isinstance(resolutions, dict) else _load(RES_FILE, base)
    track = update_track(_load(TRACK_FILE, base), emit or {}, close, resolutions, now=now)
    write_json_atomic((base / TRACK_FILE), track, indent=1)
    a = track["agg"]["all"]
    c = track["agg"].get("consensus")
    print(f"🐋 Whale-Nachspiel-Depot: {len(track['open'])} offen · {a['n']} abgerechnet"
          + (f" · Treffer {a['hit']*100:.0f}% · ROI {a['roi']*100:+.1f}% · Ø CLV {a['clvAvg']:+.1f}pp"
             + (f" · Ø verpasster Move {a['lagAvg']:+.1f}pp" if a.get("lagAvg") is not None else "")
             if a["n"] else "")
          + (f" · Konsens {c['n']}: ROI {c['roi']*100:+.1f}%" if c else ""))
    return track


def main() -> int:
    emit = load_emit()
    if emit is None:
        print("ℹ️  Kein Emitter-Output — keine neuen Whale-Plays, offene werden weiter abgerechnet.")
        emit = {"whales": []}
    write_from_emit(emit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
