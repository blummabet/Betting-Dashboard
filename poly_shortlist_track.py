#!/usr/bin/env python3
# poly_shortlist_track.py — 02.08.2026 (Lucas): Paper-Track-Record für die „Heute spielenswert"-
# Shortlist. Snapshottet bei jedem Global-Scan die EXAKTEN Empfehlungen (via node-Emitter, der die
# echte Frontend-Engine lädt → kein Drift), rechnet bei Markt-Auflösung ab: fixer Einsatz $10 zum
# Einstiegspreis, Abrechnung 0/1, plus CLV (Einstieg→Schluss). Zwei Sichten aus EINEM File: die
# ganze Shortlist UND die Public-Kandidaten-Teilmenge (public-Flag je Play). Setzt/sendet NICHTS —
# reines Mitschreiben, damit Lucas sieht, ob sich das echte Nachspielen (Auto-Bet) lohnt.
#
# Datenfluss (alles read-only ggü. Poly, nur Track-File wird geschrieben):
#   node scripts/emit_shortlist.mjs  → Plays (key, side, verdict, conv, price, public, …)
#   poly_money_broad_close.json      → lastPrice-Update offener Plays (Schluss-Referenz für CLV)
#   poly_resolutions.json            → {key:{winner,ts}} (von poly_money_broad geschrieben)
#   poly_shortlist_track.json        → vorheriger Stand (open/settled/agg)
from __future__ import annotations

import json
import os
import glob
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from safe_write import write_json_atomic   # 25.08.2026: temp+replace statt halber Datei
from poly_slug_urteil import aufloesbar   # 04.09.2026: Buendel-Slugs nicht raten

BASE = Path(__file__).resolve().parent
CLOSE_FILE = "poly_money_broad_close.json"
RES_FILE = "poly_resolutions.json"
TRACK_FILE = "poly_shortlist_track.json"
EMITTER = "scripts/emit_shortlist.mjs"

STAKE = float(os.environ.get("SHORTLIST_STAKE") or 10.0)   # fixer Einsatz je Play (USD-Notional)
# 04.09.2026 (Lucas: „ist das eh kein hard cap sondern lernt weiter auch wenn 500 erreicht?").
# Es lernt weiter — aber nur aus den letzten SETTLED_KEEP Plays, und das war ein engeres Fenster,
# als die Zahl aussehen laesst: 500 abgerechnete Plays entsprachen bei gemessenen 27/Tag genau
# **18,4 Tagen** (16.08. bis 04.09.).
#
# Fuer die haeufigen Signal-Mixe ist das egal — money+sharp (197), money+steam (91), bf+money (78)
# und sharp (65) saettigen das Vertrauensgewicht n/(n+25) ohnehin. Das Problem sind die SELTENEN:
#
#   bf+money+sharp     n=12   0,65/Tag  →  16 Roh-Plays braeuchten 25 Tage   (Fenster: 18)
#   sharp+steam        n=11   0,60/Tag  →                        27 Tage
#   steam              n=13   0,71/Tag  →                        23 Tage
#
# Die sammeln langsamer, als das Fenster sie verdraengt, und stehen deshalb DAUERHAFT bei
# „sammelt · n<8" — ein Gleichgewicht knapp unter der Schwelle. Ausgerechnet bf+money+sharp
# stand dabei mit +77,1% ROI als beste Zeile auf dem Lern-Board und konnte nie bestaetigt werden.
#
# 2000 sind rund 75 Tage Gedaechtnis. Die Datei waechst von ~266 KB auf ~1 MB (gegen 122 MB
# Artefakt vernachlaessigbar). Drift ist schon abgefangen: Plays aus einer aelteren Engine
# zaehlen halb (PW_CALIB_LEGACY_W), das haengt an der Engine-Version, nicht am Alter.
SETTLED_KEEP = int(os.environ.get("SHORTLIST_SETTLED_KEEP") or 2000)   # rollierend, ~75 Tage
# 10.08.2026 (Lucas): Stale-Cleanup gegen ewig offene Plays. Ein Play, dessen Markt poly_money_broad
# gar nicht trackt (nicht im close-file), bekommt NIE eine Auflösung → nach kurzer Frist verfallen
# lassen. Getrackte-aber-ewig-unaufgelöste erst nach langem Backstop. KEIN Fake-Ergebnis.
UNTRACKED_TTL_D = float(os.environ.get("SHORTLIST_UNTRACKED_TTL_D") or 2)    # nicht getrackt → nie auflösbar
STALE_TTL_D     = float(os.environ.get("SHORTLIST_STALE_TTL_D") or 14)       # getrackt, aber hängt → Backstop

# 24.08.2026 (Lucas: „was ist, wenn die mal wieder besser werden?"). Gesperrte Sportarten fliegen
# NICHT aus dem Depot — sie werden weiter mitgeschrieben und auf Wiedereintritt geprüft. Kriterium
# ist der CLV, NICHT der ROI: CLV ist der Frühindikator (misst, ob wir besser als der Schluss
# kaufen), ROI der verrauschte Nachlauf. Nur Zeilen mit ECHT erfasstem Schluss zählen — ein clvPP
# von 0 heißt „keine Schluss-Referenz", nicht „flach" (Lehre vom 07.08., Poly-Shortlist-CLV).
REENTRY_MIN_N     = int(os.environ.get("SHORTLIST_REENTRY_MIN_N") or 50)     # so viele frische Plays mindestens
REENTRY_MIN_CLV_N = int(os.environ.get("SHORTLIST_REENTRY_MIN_CLV_N") or 25) # davon mit echter Schluss-Referenz
REENTRY_WINDOW    = int(os.environ.get("SHORTLIST_REENTRY_WINDOW") or 200)   # nur die jüngsten N je Sportart


def _now():
    return datetime.now(timezone.utc)


def _age_days(ts, now):
    """Alter eines ISO-Zeitstempels in Tagen; None wenn unlesbar."""
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (now - t).total_seconds() / 86400.0
    except (ValueError, TypeError):
        return None


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _node_bin():
    """node robust finden. 06.08.2026 (Lucas: node nicht gefunden): der self-hosted
    Mac-Runner hat node NICHT immer auf dem PATH des Steps (Homebrew unter /opt/homebrew/bin). Erst
    $NODE_BIN, dann PATH, dann bekannte Absolut-Pfade — so laeuft der Emitter unabhaengig vom PATH."""
    cand = os.environ.get("NODE_BIN") or shutil.which("node")
    if cand:
        return cand
    for c in ("/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node"):
        if os.path.exists(c):
            return c
    # nvm: versionierter Pfad ~/.nvm/versions/node/vX.Y.Z/bin/node (06.08.2026, Lucas: node nicht an Standard-Pfaden)
    nvm = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
    if nvm:
        return nvm[-1]
    return "node"


def load_emit():
    """Emitter-Output holen. Test/Offline: $SHORTLIST_EMIT_JSON = Pfad zu fertigem JSON.
    Sonst: node-Emitter laufen lassen (lädt die echte poly-wallets.js-Engine). None bei Fehler."""
    override = os.environ.get("SHORTLIST_EMIT_JSON")
    if override:
        try:
            return json.loads(Path(override).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  Emit-Override nicht lesbar: {e}")
            return None
    try:
        out = subprocess.run([_node_bin(), str(BASE / EMITTER)], cwd=str(BASE),
                             capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            print(f"  Emitter-Fehler (rc={out.returncode}): {out.stderr.strip()[:400]}")
            return None
        return json.loads(out.stdout)
    except Exception as e:
        print(f"  Emitter nicht ausführbar (nicht fatal): {e}")
        return None


# Spiegel von `_pwSportCategory` (poly-wallets.js) — NUR für Alt-Zeilen, die noch kein `cat` tragen.
# Neue Plays bekommen die Kategorie vom Emitter, der die echte Frontend-Funktion lädt (kein Drift).
# Bewusst grob: hier zählt allein, ob eine Zeile in eine GESPERRTE Kategorie fällt.
def _cat_from_league(lg):
    x = str(lg or "").lower()
    if any(t in x for t in ("esport", "cs2", "csgo", "lol", "dota", "valorant")):
        return "E-Sport"
    if any(t in x for t in ("nba", "nfl", "mlb", "nhl", "wnba", "ncaa", "basketball", "baseball", "hockey")):
        return "US-Sport"
    if any(t in x for t in ("tennis", "wta", "atp")):
        return "Tennis"
    if any(t in x for t in ("ufc", "mma", "boxing")):
        return "Kampfsport"
    if "golf" in x:
        return "Golf"
    if "cricket" in x:
        return "Cricket"
    return "Fußball"


def _row_cat(r):
    """Kategorie einer Zeile: was der Emitter gestempelt hat, sonst aus der Liga abgeleitet."""
    return r.get("cat") or _cat_from_league(r.get("league"))


def _ok_price(p):
    return isinstance(p, (int, float)) and 0.0 < float(p) < 1.0


# Marken, die der LERNER an einen Play haengt — keine Ausloeser-Signale (s. aggregate()).
KALIB_MARKEN = frozenset({"calib+", "calib-", "turned"})


def _ug(werte):
    """Einseitige 95%-Untergrenze — dieselbe Rechnung wie ueberall sonst im Haus.

    `freigabe.untergrenze` haelt die harte Mindestzahl (UG_MIN_N) und gibt darunter None
    zurueck: *kein Urteil ist etwas anderes als ein gemessenes Nein*. Ohne diese Sperre faellt
    die Schranke bei wenigen aehnlichen Ergebnissen auf den Punktschaetzer zusammen — genau
    der Fehler vom 03.09. („UG +74 %" aus drei Plays).
    """
    try:
        from freigabe import untergrenze
    except Exception:
        return None
    try:
        return untergrenze([float(w) for w in (werte or [])])
    except Exception:
        return None


def _agg_one(rows):
    """Kennzahlen einer Menge Plays — MIT einseitiger 95%-Untergrenze.

    06.09.2026 (Lucas-Checkup des Poly-Boards). Das Board schreibt an einer Stelle selbst:
    *„Die Spalte UG entscheidet, nicht ROI — ein ROI ohne Untergrenze ist ein Punktschaetzer"*
    — und meldet bei den Whale-Pushes korrekt „kein Urteil: n=6". Direkt darueber standen aber
    die Zahlen, an denen wirklich etwas haengt, ohne jede Schranke:

        bespielbar   n=555  ROI +0,1 %
        public       n=172  ROI +6,0 %
        Conviction 9/10  n=11  ROI +9,9 %
        Signal calib+    n=19  ROI +26,9 %

    Und der Anleitungstext sagt: „erst wenn eine Stufe ueber genug Spiele klar im Plus ist,
    lohnt das echte Nachspielen". „Klar im Plus" ohne Schranke ist genau die Klasse
    *ein Punktschaetzer entscheidet* — die Empfehlung zum echten Setzen haengt daran.

    Die Schranke gehoert dorthin, wo die Zahl entsteht (nicht ins Frontend, sonst steht sie
    zweimal da). `belegt` ist wahr, wenn die ganze Untergrenze ueber null liegt.
    """
    n = len(rows)
    wins = sum(1 for r in rows if r.get("result") == "win")
    stake = sum(float(r.get("stake") or 0) for r in rows)
    pnl = sum(float(r.get("pnl") or 0) for r in rows)
    clv = sum(float(r.get("clvPP") or 0) for r in rows)
    roi = (pnl / stake) if stake else 0.0
    # Rendite je Play (nicht der Gesamt-ROI) traegt die Streuung — nur daraus wird eine Schranke.
    renditen = []
    for r in rows:
        st = float(r.get("stake") or 0)
        if st > 0:
            renditen.append(float(r.get("pnl") or 0) / st)
    roi_ug = _ug(renditen)
    clv_werte = [float(r.get("clvPP")) for r in rows
                 if isinstance(r.get("clvPP"), (int, float))]
    return {"n": n, "wins": wins,
            "hit": round(wins / n, 4) if n else 0.0,
            "pnl": round(pnl, 2), "stake": round(stake, 2),
            "roi": round(roi, 4),
            "roiUg": (round(roi_ug, 4) if roi_ug is not None else None),
            "belegt": bool(roi_ug is not None and roi_ug > 0),
            "clvAvg": round(clv / n, 2) if n else 0.0,
            "clvUg": (lambda u: round(u, 2) if u is not None else None)(_ug(clv_werte))}


def aggregate(settled, blocked=()):
    allr = settled
    pub = [r for r in settled if r.get("public")]
    # Die Vergleichsgruppe zum Public-Gate: gleiche Conviction, gleiche Geld-Mehrheit, nur ohne
    # bewiesene Wallet. Erst der Unterschied dieser beiden Zeilen beantwortet, ob das Wallet-Tor
    # die Auswahl verbessert — oder sie nur verkleinert.
    pub_ow = [r for r in settled if r.get("ohneWallet")]
    # 24.08.2026 (Lucas): die Gesamt-Kennzahl mischte Sportarten, auf die nie gesetzt wird, mit
    # denen, auf die gesetzt wird — dadurch sah das Depot schlechter aus als das, was man wirklich
    # spielt. `all` bleibt unverändert (Kalibrierungs-Basis im Frontend hängt daran); `bettable`
    # ist die ehrliche Schlagzeile, `blocked` die Beobachtungs-Zeile.
    _bl = set(blocked or ())
    bet = [r for r in settled if _row_cat(r) not in _bl]
    blk = [r for r in settled if _row_cat(r) in _bl]
    by_cat = {}
    for r in settled:
        by_cat.setdefault(_row_cat(r), []).append(r)
    by_cat = {k: _agg_one(v) for k, v in sorted(by_cat.items())}
    by_conv = {}
    for c in range(0, 11):
        rows = [r for r in settled if int(r.get("conv") or 0) == c]
        if rows:
            by_conv[str(c)] = _agg_one(rows)
    by_verdict = {}
    for v in ("BET", "FADE"):
        rows = [r for r in settled if r.get("verdict") == v]
        if rows:
            by_verdict[v] = _agg_one(rows)
    # 05.08.2026 (Lucas): Attribution je Ausloeser-Signal (welches Signal traegt die Kante?). Ein Play
    # kann mehrere Signale haben und zaehlt dann in mehreren Buckets (bewusste Ueberlappung).
    by_signal = {}
    by_kalib = {}
    _sig_universe = set()
    for r in settled:
        for tg in (r.get("signals") or []):
            _sig_universe.add(tg)
    for tg in sorted(_sig_universe):
        rows = [r for r in settled if tg in (r.get("signals") or [])]
        if not rows:
            continue
        # 06.09.2026 (Lucas-Checkup): `calib+`, `calib-` und `turned` standen in der Tabelle
        # „Welches Signal traegt die Kante?" zwischen money/sharp/steam/bf — mit `calib+` bei
        # +26,9 % ganz oben. Das sind aber keine AUSLOESER, sondern die Marken, die der Lerner
        # selbst an einen Play haengt, nachdem er ihn hoch- oder runtergestuft hat.
        #
        # Damit benotete die Kalibrierung ihre eigene Hausaufgabe und stand als Beleg da, dass
        # ein Signal die Kante traegt. Klasse: *eine Kennzahl urteilt ueber sich selbst.*
        # Getrennt ausgewiesen — nicht geloescht, die Zahl ist als Selbstkontrolle interessant,
        # nur nicht als Signal.
        (by_kalib if tg in KALIB_MARKEN else by_signal)[tg] = _agg_one(rows)
    return {"all": _agg_one(allr), "public": _agg_one(pub),
            "publicOhneWallet": _agg_one(pub_ow),
            "bettable": _agg_one(bet), "blocked": _agg_one(blk), "byCat": by_cat,
            "byConv": by_conv, "byVerdict": by_verdict, "bySignal": by_signal,
            "byKalibrierung": by_kalib}


def reentry_status(settled, blocked, min_n=REENTRY_MIN_N, min_clv_n=REENTRY_MIN_CLV_N,
                   window=REENTRY_WINDOW):
    """Je gesperrter Sportart: verdient sie einen zweiten Blick? REIN/testbar.

    Bewertet NUR die jüngsten `window` abgerechneten Plays dieser Kategorie — eine Sportart, die
    vor einem halben Jahr schlecht war, soll sich freilaufen können. Kriterium ist Ø CLV ≥ 0 über
    genug Zeilen MIT echter Schluss-Referenz. `eligible` schaltet NICHTS frei: es ist ein Hinweis,
    die Sperre legt Lucas selbst um (echtes Geld auf verrauschten Daten automatisch freizuschalten
    wäre der falsche Automatismus).
    """
    out = {}
    for cat in sorted(set(blocked or ())):
        rows = [r for r in settled if _row_cat(r) == cat][-window:]
        clvs = [float(r["clvPP"]) for r in rows
                if isinstance(r.get("clvPP"), (int, float)) and r["clvPP"] != 0]
        avg = round(sum(clvs) / len(clvs), 2) if clvs else None
        a = _agg_one(rows) if rows else None
        out[cat] = {
            "n": len(rows), "clvN": len(clvs), "clvAvg": avg,
            "roi": (a["roi"] if a else None), "hit": (a["hit"] if a else None),
            "eligible": bool(len(rows) >= min_n and len(clvs) >= min_clv_n
                             and avg is not None and avg >= 0),
            "needN": max(0, min_n - len(rows)), "needClvN": max(0, min_clv_n - len(clvs)),
        }
    return out


def update_track(prev, emit, close, resolutions, now=None, stake=STAKE, blocked=None):
    """REIN/testbar. Öffnet neue Plays, zieht lastPrice mit, rechnet aufgelöste ab. Ein Play =
    (marketKey, side); der Einstieg (firstTs/entryPrice) ist der ERSTE Zeitpunkt, an dem der Play
    in der Shortlist auftauchte — genau das, was man live gesetzt hätte."""
    now = now or _now()
    # Sperrliste kommt aus dem Emitter (= poly-wallets.js, eine Quelle). Faellt der Emitter aus,
    # gilt der zuletzt bekannte Stand aus dem Track-File statt einer leeren Liste.
    _bl = blocked if blocked is not None else list(
        (emit or {}).get("blockedCats") or (prev or {}).get("blockedCats") or [])
    open_ = {k: dict(v) for k, v in (prev.get("open") or {}).items() if isinstance(v, dict)}
    settled = [dict(s) for s in (prev.get("settled") or []) if isinstance(s, dict)]
    # 05.09.2026 (Lucas: „ich check's trotzdem nicht, was da passiert ist") — beim Nachrechnen
    # der Delle kam ich auf 549 bespielbare Plays und -118 $, die Datei sagte 512 und +60 $.
    # Der Grund war nicht die Delle, sondern `cat`: das Feld wird erst seit dem 24.08. gestempelt
    # und stand in **207 von 563** Zeilen auf null. `_row_cat()` faengt das ab, indem es die
    # Kategorie aus der Liga ableitet — wer aber `cat` direkt liest, haelt jede alte Zeile fuer
    # bespielbar, gesperrte Sportarten eingeschlossen. Fehlende Information als harmloser Default,
    # und diesmal bin ich selbst darauf hereingefallen.
    #
    # Also wird das Feld nachgetragen, statt sich auf die Disziplin jedes Lesers zu verlassen —
    # dieselbe Loesung wie `ledger_mischen()` fuer die Stake-Sportarten am 04.09.
    _kat_nachgetragen = 0
    for _r in list(open_.values()) + settled:
        if not _r.get("cat"):
            _r["cat"] = _cat_from_league(_r.get("league"))
            _kat_nachgetragen += 1
    settled_keys = {(s.get("key"), s.get("side")) for s in settled}

    # 1) Neue Plays öffnen (fixer Einsatz, Entry = Snapshot-Preis der empfohlenen Seite)
    for pl in (emit.get("plays") or []):
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
            continue                                  # kein sauberer Einstiegspreis → nicht öffnen
        open_[ok] = {
            "key": key, "side": side, "verdict": pl.get("verdict"),
            "conv": pl.get("conv"), "league": pl.get("league"),
            "cat": pl.get("cat") or _cat_from_league(pl.get("league")),   # 24.08.2026: Sportart mitführen
            "entryPrice": round(float(price), 4), "firstTs": now.isoformat(),
            "lastPrice": round(float(price), 4), "lastTs": now.isoformat(),
            "htkAtEntry": pl.get("htk"), "public": bool(pl.get("public")),
            # 06.09.2026: Schatten-Gruppe — alles am Public-Gate ausser der Wallet-Bedingung.
            # Von 172 abgerechneten Public-Kandidaten waren 172 sharp; ohne Vergleichsgruppe ist
            # nicht messbar, ob die Wallet-Pruefung etwas beitraegt. Diese Zeilen liefern sie.
            "ohneWallet": bool(pl.get("ohneWallet")),
            "reasons": (pl.get("reasons") or [])[:3], "signals": list(pl.get("signals") or []), "stake": stake,
            # 29.08.2026 (Lucas): Engine-Version des Emits mitfuehren. Der Kalibrierer gewichtet
            # damit Plays aus einer aelteren Engine niedriger, statt sie fuer bare Muenze zu nehmen.
            # Fehlt der Wert (Alt-Emit), bleibt er None -> gilt als Alt-Engine.
            "ev": pl.get("ev"),
        }

    # 2) lastPrice aller offenen Plays aus dem Close-File nachziehen (beste Schluss-Referenz für CLV)
    for e in open_.values():
        cp = ((close.get(e["key"]) or {}).get("prices") or {}).get(e["side"])
        if _ok_price(cp):
            e["lastPrice"] = round(float(cp), 4)
            e["lastTs"] = now.isoformat()

    # 3) Aufgelöste Plays abrechnen
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
        entry = float(e["entryPrice"])
        st = float(e.get("stake") or stake)
        win = (e["side"] == winner)
        pnl = (st / entry - st) if win else -st       # Aktien = st/entry, Gewinner zahlt 1.00/Aktie
        close_ref = float(e.get("lastPrice") or entry)
        clv = round((close_ref - entry) * 100, 2)
        settled.append({
            "key": e["key"], "side": e["side"], "verdict": e.get("verdict"),
            "conv": e.get("conv"), "league": e.get("league"), "cat": _row_cat(e),
            "entryPrice": round(entry, 4), "closePrice": round(close_ref, 4),
            "result": "win" if win else "loss", "winner": winner,
            "pnl": round(pnl, 2), "clvPP": clv, "stake": st,
            "public": bool(e.get("public")), "ohneWallet": bool(e.get("ohneWallet")),
            "signals": list(e.get("signals") or []), "firstTs": e.get("firstTs"),
            "ev": e.get("ev"),   # 29.08.2026: Engine-Stempel ueberlebt die Abrechnung
            "settledTs": now.isoformat(), "resolvedTs": (r or {}).get("ts"),
        })
        del open_[ok]

    # 4) Stale-Cleanup: unauflösbare Plays verfallen lassen statt ewig offen halten (10.08.2026, Lucas).
    #    Nicht getrackt (nicht im close-file, poly_money_broad sieht den Markt nicht) → bekommt nie eine
    #    Auflösung, kurze Frist. Getrackt-aber-ewig-offen → langer Backstop. KEIN Fake-Ergebnis: verfallene
    #    Plays zählen NICHT als win/loss, sie werden nur aus open entfernt (raus aus der Integritäts-Warnung).
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
            "katNachgetragen": _kat_nachgetragen,
            "blockedCats": _bl, "reentry": reentry_status(settled, _bl),
            "open": open_, "settled": settled, "agg": aggregate(settled, _bl)}


def main() -> int:
    emit = load_emit()
    if emit is None:
        # Emitter ist umgebungs-flaky (node_modules/jsdom im CI weggewischt). FRÜHER hing die
        # ganze Abrechnung daran (früher return) → aufgelöste Plays blieben ewig „offen", obwohl
        # poly_resolutions.json den Sieger längst kennt. Abrechnung braucht den Emitter NICHT:
        # ohne Emit einfach keine NEUEN Plays öffnen, offene aber weiter abrechnen. (02.08.2026, Lucas)
        print("ℹ️  Kein Emitter-Output — keine neuen Plays, aber offene werden weiter abgerechnet.")
        emit = {"plays": []}
    close = _load(CLOSE_FILE)
    resolutions = _load(RES_FILE)
    prev = _load(TRACK_FILE)
    track = update_track(prev, emit, close if isinstance(close, dict) else {},
                         resolutions if isinstance(resolutions, dict) else {})
    write_json_atomic((BASE / TRACK_FILE), track, indent=1)
    # 24.08.2026 (Lucas): Whale-Nachspiel-Depot auf DEMSELBEN Emitter-Output mitschreiben — sonst
    # müsste der Scan node+jsdom ein zweites Mal starten. Defensiv gekapselt: fällt es aus,
    # bleibt der Shortlist-Track heil (er ist die ältere, wichtigere Fläche).
    try:
        import poly_whale_follow as _WF
        _WF.write_from_emit(emit, close if isinstance(close, dict) else {},
                            resolutions if isinstance(resolutions, dict) else {},
                            base=BASE)   # NICHT weglassen: main()-Tests patchen BASE auf tmp
    except Exception as _e:
        print(f"  ⚠️  Whale-Nachspiel-Depot übersprungen (nicht fatal): {_e}")

    a = track["agg"]["all"]
    print(f"📈 Shortlist-Paper-Track: {len(track['open'])} offen · {a['n']} abgerechnet · "
          f"Treffer {a['hit']*100:.0f}% · ROI {a['roi']*100:+.1f}% · Ø CLV {a['clvAvg']:+.1f}pp "
          f"(Public: {track['agg']['public']['n']}) · {track.get('expired', 0)} verfallen (unauflösbar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
