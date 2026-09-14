#!/usr/bin/env python3
"""
shortlist_auto_bet.py — 14.09.2026 (Lucas: „Ich will die quasi heute spielenswert, diese
Public-Kandidaten, automatisch nachspielen jetzt mal eine Zeit und wir schauen, was dann
rauskommt ein paar Wochen").

Setzt ECHTES Geld auf genau die Plays, die im Trades-Channel als „🔥 Heute spielenswert"
standen. Parameter, wie bestellt:

    Einsatz   fest $5 je Wette
    Deckel    $100 offene Exposure — GEMEINSAM mit dem Pinnacle-Trader (eine Wallet)
    Stopp     laeuft, bis Lucas ihn abdreht (Schalter SHORTLIST_AUTO_BET / Kill-Switch)

━━ Die eine Entscheidung, die zaehlt ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dieses Skript waehlt NICHTS aus. Es liest `shortlist_push_ledger.json` — das Buch der
tatsaechlich gesendeten Pushes — und setzt auf dessen Zeilen. Damit gilt per Konstruktion:

    ** gesetzt wird, was im Channel stand. Nichts anderes, nie mehr. **

Eine eigene Auswahl waere eine FUENFTE Menge neben Uebersicht, Public-Tor, Paper-Track und
Push (der Vierer-Zoo vom 07.09. hat genau das gekostet). Und weil das Buch nur schreibt,
was wirklich rausging (`gesendet=True`), setzt ein Vorschau-Lauf ohne Telegram-Token auch
kein Geld — die Kopplung ist nicht Konvention, sondern Mechanik.

━━ Abrechnung ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ebenfalls fremdbestimmt: der Ausgang kommt aus `poly_shortlist_track.json` (settled/
unaufloesbar), wo der Paper-Tracker ihn nach den Regeln von poly_slug_urteil.py schon
festgestellt hat. Zwei Abrechnungen mit zwei Regeln waren der Fehler, den poly_slug_urteil
aufgeraeumt hat — hier wird nur der Ausgang uebernommen und mit dem ECHTEN Fuellpreis und
dem ECHTEN Einsatz durchgerechnet.

⚠️ Ein Play, den der Tracker als „unaufloesbar" abschreibt, gibt hier KEIN Geld frei. Auf
Papier verfaellt eine Zeile; in der Wallet liegt die Position weiter. Solche Wetten bleiben
als `haengt` in der Exposure stehen und werden gemeldet — ein Deckel, der Phantom-Freiraum
erfindet, ist kein Deckel (s. poly_offen.py, derselbe Fehler in gross).

Env:
  SHORTLIST_AUTO_BET=1        Hauptschalter. FEHLT ER, WIRD NICHT GESETZT (nur Trockenlauf).
  SHORTLIST_AUTO_STAKE        Einsatz je Wette (Default 5.0)
  SHORTLIST_AUTO_MAX_OFFEN    gemeinsamer Exposure-Deckel (Default 100.0)
  SHORTLIST_AUTO_MAX_LAUF     max Wetten je Lauf (Default 3)
  SHORTLIST_AUTO_MAX_ALTER_M  max Alter des Pushs in Minuten (Default 90)
  SHORTLIST_AUTO_MAX_SLIP_PP  max Aufschlag des Asks auf den Push-Preis (Default 3.0)
  POLY_PRIVATE_KEY + POLY_*   wie beim Pinnacle-Trader; ohne Key: Trockenlauf
  TELEGRAM_TOKEN + TELEGRAM_TRADES_CHAT_ID
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import poly_offen as PO
import push_deckel as PD
from safe_write import write_json_atomic

BASE = Path(__file__).resolve().parent

LEDGER_FILE  = BASE / "shortlist_push_ledger.json"
PLACED_FILE  = BASE / "shortlist_auto_bets_placed.json"
TRACK_FILE   = BASE / "poly_shortlist_track.json"
OFFEN_FILE   = BASE / "poly_money_broad_offen.json"
CLOSE_FILE   = BASE / "poly_money_broad_close.json"

AN            = os.environ.get("SHORTLIST_AUTO_BET", "").strip() in ("1", "true", "yes", "on")
STAKE         = float(os.environ.get("SHORTLIST_AUTO_STAKE") or 5.0)
MAX_OFFEN     = float(os.environ.get("SHORTLIST_AUTO_MAX_OFFEN") or 100.0)
MAX_LAUF      = int(os.environ.get("SHORTLIST_AUTO_MAX_LAUF") or 3)
MAX_ALTER_M   = float(os.environ.get("SHORTLIST_AUTO_MAX_ALTER_M") or 90)
MAX_SLIP_PP   = float(os.environ.get("SHORTLIST_AUTO_MAX_SLIP_PP") or 3.0)
MIN_PREIS     = float(os.environ.get("SHORTLIST_AUTO_MIN_PREIS") or 0.15)
MAX_PREIS     = float(os.environ.get("SHORTLIST_AUTO_MAX_PREIS") or 0.92)
BALANCE_PUFFER = float(os.environ.get("SHORTLIST_AUTO_BALANCE_PUFFER") or 1.0)
MAX_TG        = int(os.environ.get("SHORTLIST_AUTO_MAX_TG") or 6)
HAENGT_WARN_ANTEIL = 0.25      # ab so viel haengender Exposure am Deckel: melden


# ── Lesen/Schreiben ────────────────────────────────────────────────────────────────────────
def _laden(pfad, default):
    try:
        return json.loads(Path(pfad).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception as exc:
        print(f"  ⚠️  {Path(pfad).name} nicht lesbar: {exc}")
        return None          # None = kaputt, NICHT „leer" (der Aufrufer haelt an)


def _jetzt():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _jetzt()).isoformat()


def _parse(ts):
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


# ── Reine Entscheidungen (testbar, kein Netz, keine Datei) ─────────────────────────────────
def bet_key(zeile) -> str:
    """Ein Play = eine Position. `k` ist schon `key|side` aus dem Push-Buch."""
    return str(zeile.get("k") or "%s|%s" % (zeile.get("key"), zeile.get("side")))


def faellige_zeilen(ledger, schon_gesetzt, jetzt=None, max_alter_m=None) -> list:
    """Push-Zeilen, die jetzt gesetzt werden duerfen. REIN/testbar.

    Drei Gruende, eine Zeile NICHT zu nehmen:
      · schon gesetzt (ein Play, eine Position — auch nach einem zweiten Push bei hoeherer
        Conviction: nachkaufen war nicht bestellt)
      · aelter als `max_alter_m` — ein Push von gestern ist kein Auftrag von heute. Ohne das
        wuerde ein Lauf nach einer Panne das ganze Buch auf einmal nachsetzen (genau die
        Klasse, die im August die Push-Flut ausgeloest hat)
      · unbrauchbar (kein key/side/Preis)
    """
    jetzt = jetzt or _jetzt()
    grenze = float(max_alter_m if max_alter_m is not None else MAX_ALTER_M)
    gesetzt = set(schon_gesetzt or ())
    aus = []
    for z in (ledger or []):
        if not isinstance(z, dict) or not z.get("key") or not z.get("side"):
            continue
        if bet_key(z) in gesetzt:
            continue
        ts = _parse(z.get("sentAt"))
        if ts is None:
            continue                                  # ohne Zeit kein Alter → nicht setzen
        if (jetzt - ts).total_seconds() / 60.0 > grenze:
            continue
        try:
            p = float(z.get("pushPreis"))
        except (TypeError, ValueError):
            continue                                  # ohne Push-Preis kein Slippage-Mass
        if not (0.0 < p < 1.0):
            continue
        aus.append(z)
    aus.sort(key=lambda z: (-(z.get("conv") or 0), str(z.get("sentAt"))))
    return aus


def token_aus_feed(feed, key, side):
    """Der CLOB-Token zu (key, side) aus dem poly_money_broad-Feed. REIN/testbar.

    Kein Raten: steht der Token nicht da, gibt es None und der Aufrufer laesst die Zeile
    liegen. Einen falschen Token zu setzen hiesse, auf einen anderen Ausgang zu wetten.
    """
    m = (feed or {}).get(key)
    if not isinstance(m, dict):
        return None
    tok = (m.get("tokens") or {}).get(side)
    return str(tok) if tok else None


def preis_urteil(push_preis, ask, max_slip_pp=None, min_p=None, max_p=None):
    """Darf zu diesem Ask gekauft werden? → (ok, grund). REIN/testbar.

    Der Push nannte einen Preis. Kauft der Bot spaeter deutlich teurer, ist die gemessene
    Bilanz nicht mehr die des Pushs — und genau die soll dieser Versuch beantworten.
    """
    slip = float(max_slip_pp if max_slip_pp is not None else MAX_SLIP_PP)
    lo = float(min_p if min_p is not None else MIN_PREIS)
    hi = float(max_p if max_p is not None else MAX_PREIS)
    try:
        a = float(ask)
        p = float(push_preis)
    except (TypeError, ValueError):
        return False, "kein Preis"
    if not (0.0 < a < 1.0):
        return False, "Ask unplausibel"
    if a < lo:
        return False, f"Ask {a:.3f} unter Mindestpreis {lo:.2f}"
    if a > hi:
        return False, f"Ask {a:.3f} ueber Hoechstpreis {hi:.2f}"
    auf_pp = (a - p) * 100.0
    if auf_pp > slip:
        return False, f"Ask {auf_pp:.1f}pp ueber Push-Preis (max {slip:.1f}pp)"
    return True, ""


def liquide(buch, stake, preis) -> bool:
    """Liegt genug Ask-Volumen fuer diesen Einsatz im Buch? REIN/testbar.

    Fehlt das Buch, gilt NICHT als liquide: bei einer Order mit echtem Geld ist der
    harmlose Default „nicht setzen".
    """
    asks = (buch or {}).get("asks") or []
    try:
        p = float(preis)
        noetig = float(stake) / p if p > 0 else None
    except (TypeError, ValueError, ZeroDivisionError):
        return False
    if not noetig:
        return False
    shares = 0.0
    for lvl in asks:
        try:
            lp, ls = float(lvl[0]), float(lvl[1])
        except (TypeError, ValueError, IndexError):
            continue
        if lp <= p + 1e-9:
            shares += ls
    return shares >= noetig


def handeln_erlaubt(balance, offen, stake, max_offen=None, puffer=None):
    """Darf ueberhaupt noch eine Wette dieser Groesse platziert werden? → (ok, grund). REIN."""
    deckel = float(max_offen if max_offen is not None else MAX_OFFEN)
    puf = float(puffer if puffer is not None else BALANCE_PUFFER)
    try:
        b, o, s = float(balance), float(offen), float(stake)
    except (TypeError, ValueError):
        return False, "Zahlen unlesbar"
    if s <= 0:
        return False, "Einsatz 0"
    if o + s > deckel:
        return False, f"Exposure-Deckel (${o:.2f} + ${s:.2f} > ${deckel:.2f})"
    if b - s < puf:
        return False, f"Balance zu knapp (${b:.2f} - ${s:.2f} < ${puf:.2f} Puffer)"
    return True, ""


# ── Abrechnung: Ausgang kommt vom Paper-Tracker, Geld rechnet dieses Skript ────────────────
def _track_index(track):
    """(settled, unaufloesbar) als Nachschlagewerk key|side → Zeile. REIN/testbar."""
    settled, tot = {}, {}
    for z in ((track or {}).get("settled") or []):
        if isinstance(z, dict) and z.get("key") and z.get("side"):
            settled["%s|%s" % (z["key"], z["side"])] = z
    for z in ((track or {}).get("unaufloesbar") or []):
        if isinstance(z, dict) and z.get("key") and z.get("side"):
            tot["%s|%s" % (z["key"], z["side"])] = z
    return settled, tot


def abgleichen(bets, track, jetzt=None) -> int:
    """Offene Wetten gegen den Paper-Tracker abrechnen. Aendert `bets` in place → Anzahl.

    P&L auf den ECHTEN Fuellpreis: Treffer zahlt 1 je Share, also stake/fill - stake.
    Ein „unaufloesbar" beim Tracker macht die Wette NICHT terminal (das Geld liegt weiter
    auf Poly) — sie bekommt `haengt: true` und bleibt in der Exposure.
    """
    jetzt = jetzt or _jetzt()
    settled, tot = _track_index(track)
    n = 0
    for b in (bets or []):
        if not isinstance(b, dict) or not PO.ist_offen(b):
            continue
        k = b.get("betKey")
        s = settled.get(k)
        if s:
            res = str(s.get("result") or "").lower()
            try:
                fill = float(b.get("polyPrice") or 0)
                stake = float(b.get("stake") or 0)
            except (TypeError, ValueError):
                continue
            if res == "win" and fill > 0:
                b["status"], b["result"] = "won", "WIN"
                b["pnl"] = round(stake / fill - stake, 4)
            elif res == "loss":
                b["status"], b["result"] = "lost", "LOSS"
                b["pnl"] = round(-stake, 4)
            else:
                b["status"], b["result"] = "void", "VOID"
                b["pnl"] = 0.0
            b["resolvedAt"] = _iso(jetzt)
            b["winner"] = s.get("winner")
            b.pop("haengt", None)
            n += 1
        elif k in tot and not b.get("haengt"):
            # Papier gibt auf, Geld nicht. Kein Terminal-Merkmal → bleibt in der Exposure.
            b["haengt"] = True
            b["haengtGrund"] = tot[k].get("grund") or "vom Tracker abgeschrieben"
            b["haengtSeit"] = _iso(jetzt)
            n += 1
    return n


def haengende(bets) -> tuple[float, int]:
    """Wieviel Exposure haengt (Tracker hat aufgegeben, Position lebt)? REIN/testbar."""
    s, n = 0.0, 0
    for b in (bets or []):
        if isinstance(b, dict) and b.get("haengt") and PO.ist_offen(b):
            try:
                s += float(b.get("stake") or 0)
            except (TypeError, ValueError):
                continue
            n += 1
    return round(s, 4), n


# ── Kill-Switch: jedes Stopp-Signal der gemeinsamen Wallet gilt auch hier ──────────────────
def kill_switch(base_dir=None) -> tuple[bool, str]:
    """(gestoppt, grund). Fail-closed wie beim Pinnacle-Trader: kaputte Datei = Stopp.

    Geprueft werden ALLE Kill-Switches derselben Wallet. Wer den Handel abdreht, meint
    nicht „ausser dem Shortlist-Bot"."""
    bd = str(base_dir or BASE)
    for pfx in PO.DATENSATZ_PRAEFIXE:
        p = os.path.join(bd, f"{pfx}kill_switch.json")
        if not os.path.exists(p):
            continue
        try:
            ks = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception as exc:
            return True, f"{pfx}kill_switch.json korrupt ({exc}) — fail-closed"
        if isinstance(ks, dict) and ks.get("enabled") is False:
            return True, f"{pfx}kill_switch: {ks.get('reason') or 'manuell pausiert'}"
    return False, ""


def _balance(base_dir=None) -> tuple[float, str]:
    """Frischeste Balance ueber alle Datensatz-Dateien — es ist physisch dieselbe Wallet."""
    bd = str(base_dir or BASE)
    best, best_ts, src = None, "", "—"
    for pfx in PO.DATENSATZ_PRAEFIXE:
        d = _laden(os.path.join(bd, f"{pfx}poly_balance.json"), None)
        if not isinstance(d, dict) or d.get("usdc") is None:
            continue
        ts = str(d.get("updatedAt") or "")
        if best is None or ts > best_ts:
            best, best_ts, src = d, ts, f"{pfx}poly_balance.json"
    try:
        return float((best or {}).get("usdc") or 0), src
    except (TypeError, ValueError):
        return 0.0, src


# ── Netz (duenn gehalten, damit die Entscheidungen oben trocken testbar bleiben) ───────────
def buch_holen(token_id):
    """Orderbuch eines Tokens vom CLOB. None bei Fehler (→ nicht setzen)."""
    try:
        import requests
        r = requests.get("https://clob.polymarket.com/book",
                         params={"token_id": str(token_id)}, timeout=15)
        r.raise_for_status()
        d = r.json()
    except Exception as exc:
        print(f"    ⚠️  Buch nicht abrufbar: {exc}")
        return None
    def _lvls(raw):
        out = []
        for x in (raw or []):
            try:
                out.append((float(x["price"]), float(x["size"])))
            except (KeyError, TypeError, ValueError):
                continue
        return out
    bids = sorted(_lvls(d.get("bids")), key=lambda t: -t[0])
    asks = sorted(_lvls(d.get("asks")), key=lambda t: t[0])
    return {"bids": [list(x) for x in bids], "asks": [list(x) for x in asks],
            "bid": bids[0][0] if bids else None, "ask": asks[0][0] if asks else None}


def _melden(zeile, bet, dry):
    """Trades-Channel-Meldung fuer eine gesetzte Shortlist-Wette."""
    from telegram_trades import notify_shortlist_opened
    return notify_shortlist_opened(
        match=zeile.get("match") or zeile.get("key"),
        side=zeile.get("side"),
        league=zeile.get("league"),
        conv=zeile.get("conv"),
        stake=bet.get("stake"),
        fill=bet.get("polyPrice"),
        push_preis=zeile.get("pushPreis"),
        order_id=bet.get("orderId"),
        slug=zeile.get("key"),
        offen=bet.get("_offenNachher"),
        deckel=MAX_OFFEN,
        dry_run=dry,
    )


def main() -> int:
    print("=== shortlist_auto_bet.py ===")
    placed_roh = _laden(PLACED_FILE, {"bets": []})
    if placed_roh is None:
        print("  🛑 shortlist_auto_bets_placed.json nicht lesbar — NICHTS gesetzt. "
              "Ohne das Buch kennt niemand die offene Exposure.")
        return 0
    bets = list((placed_roh or {}).get("bets") or [])

    track = _laden(TRACK_FILE, {})
    if track:
        n_ab = abgleichen(bets, track)
        if n_ab:
            print(f"  📒 {n_ab} Position(en) abgeglichen (Ausgang vom Paper-Tracker).")

    exp = PO.wallet_exposure(str(BASE))
    if exp["unlesbar"]:
        print(f"  🛑 Wett-Datei(en) nicht lesbar: {', '.join(exp['unlesbar'])} — NICHTS gesetzt. "
              "Eine kaputte Datei heisst nicht „keine offenen Positionen\".")
        _speichern(bets)
        return 0
    offen = exp["offen"]
    haengt_s, haengt_n = haengende(bets)
    print(f"  📈 Offene Exposure (ganze Wallet): ${offen:.2f} / ${MAX_OFFEN:.2f}  "
          f"({exp['n']} Position(en))")
    for datei, (s, c) in sorted(exp["je"].items()):
        print(f"     · {datei}: ${s:.2f} ({c})")
    if haengt_n:
        print(f"  ⚠️  davon haengend (Tracker hat aufgegeben, Geld liegt weiter): "
              f"${haengt_s:.2f} in {haengt_n} Position(en)")

    gestoppt, grund = kill_switch()
    if gestoppt:
        print(f"  🛑 Kill-Switch: {grund} — nichts gesetzt.")
        _speichern(bets)
        return 0

    ledger = _laden(LEDGER_FILE, [])
    if ledger is None:
        print("  🛑 Push-Buch nicht lesbar — nichts gesetzt.")
        _speichern(bets)
        return 0
    schon = {b.get("betKey") for b in bets if isinstance(b, dict)}
    faellig = faellige_zeilen(ledger if isinstance(ledger, list) else [], schon)
    if not faellig:
        print(f"  ℹ️  kein frischer Push zum Nachspielen (Fenster {MAX_ALTER_M:.0f} Min).")
        _speichern(bets)
        return 0
    print(f"  🎯 {len(faellig)} Push-Zeile(n) im Fenster, max {MAX_LAUF} je Lauf.")

    balance, bal_src = _balance()
    print(f"  💼 Balance: ${balance:.2f}  (Quelle: {bal_src})")

    feed = _laden(OFFEN_FILE, {}) or {}
    feed2 = _laden(CLOSE_FILE, {}) or {}
    key = os.environ.get("POLY_PRIVATE_KEY", "").strip()
    dry = not (AN and key)
    if not AN:
        print("  🔒 SHORTLIST_AUTO_BET ist AUS — Trockenlauf, es wird NICHTS gesetzt.")
    elif not key:
        print("  🔒 kein POLY_PRIVATE_KEY — Trockenlauf, es wird NICHTS gesetzt.")

    # Der Deckel umschliesst den ECHTEN Sender: eine fehlgeschlagene Meldung verbraucht dann
    # kein Kontingent (Vertrag von push_deckel.Deckel).
    melde = PD.Deckel(lambda arg: _melden(arg[0], arg[1], dry=False), MAX_TG, "shortlist-auto-bet")
    neu, lauf_offen, dran = [], offen, 0
    for z in faellig:
        # Der Lauf-Deckel zaehlt im Trockenlauf MIT. Sonst zeigt die Vorschau neun Wetten, wo
        # der echte Lauf drei setzt — und eine Vorschau, die etwas anderes tut als der Ernstfall,
        # ist keine Vorschau.
        if dran >= MAX_LAUF:
            print(f"  ⏹  Lauf-Deckel {MAX_LAUF} erreicht — Rest beim naechsten Lauf.")
            break
        bk = bet_key(z)
        titel = f"{z.get('key')} · {z.get('side')} (conv {z.get('conv')})"
        ok, grund = handeln_erlaubt(balance, lauf_offen, STAKE)
        if not ok:
            print(f"  🛑 {grund} — Schluss fuer diesen Lauf.")
            break
        tok = token_aus_feed(feed, z.get("key"), z.get("side")) or \
              token_aus_feed(feed2, z.get("key"), z.get("side"))
        if not tok:
            print(f"  ⏭  {titel}: kein Token im Feed — nicht geraten, uebersprungen.")
            continue
        buch = buch_holen(tok) if not dry else None
        if buch is None and not dry:
            print(f"  ⏭  {titel}: kein Buch — uebersprungen.")
            continue
        ask = (buch or {}).get("ask") if buch else z.get("pushPreis")
        ok, grund = preis_urteil(z.get("pushPreis"), ask)
        if not ok:
            print(f"  ⏭  {titel}: {grund}.")
            continue
        if buch is not None and not liquide(buch, STAKE, ask):
            print(f"  ⏭  {titel}: zu wenig Ask-Volumen fuer ${STAKE:.2f}.")
            continue

        if dry:
            dran += 1
            lauf_offen += STAKE
            print(f"  🧪 WUERDE setzen: {titel} · ${STAKE:.2f} @ {ask:.3f} "
                  f"(Push {float(z['pushPreis']):.3f})")
            continue

        from polymarket_bet import place_market_order
        res = place_market_order(tok, STAKE, key, price_hint=ask,
                                 best_bid=(buch or {}).get("bid"), best_ask=ask)
        if res.get("status") not in ("placed", "dry-run"):
            print(f"  ❌ {titel}: {str(res.get('error') or '')[:200]}")
            continue
        lauf_offen += STAKE
        balance -= STAKE
        dran += 1
        bet = {
            "betKey": bk, "key": z.get("key"), "side": z.get("side"),
            "match": z.get("match"), "league": z.get("league"), "cat": z.get("cat"),
            "conv": z.get("conv"), "pushPreis": z.get("pushPreis"), "pushAt": z.get("sentAt"),
            "polyPrice": ask, "entryAsk": ask, "stake": STAKE,
            "tokenId": tok, "orderId": res.get("orderId"),
            "status": res.get("status"), "placedAt": _iso(),
            "source": "auto_shortlist", "slug": z.get("key"),
            "_offenNachher": round(lauf_offen, 2),
        }
        neu.append(bet)
        print(f"  ✅ gesetzt: {titel} · ${STAKE:.2f} @ {ask:.3f} — Order {res.get('orderId')}")
        try:
            melde((z, bet))
        except Exception as exc:
            print(f"    ⚠️  Trades-Meldung fehlgeschlagen: {exc}")

    for b in neu:
        b.pop("_offenNachher", None)
    bets.extend(neu)
    _speichern(bets)
    if melde.bericht():
        print("  " + melde.bericht())
    wort = "wuerden gesetzt" if dry else "neue Position(en)"
    print(f"  → {dran if dry else len(neu)} {wort}, offene Exposure "
          f"{'waere' if dry else 'jetzt'} ${lauf_offen:.2f}.")
    return 0


def _speichern(bets) -> None:
    try:
        write_json_atomic(str(PLACED_FILE), {"updatedAt": _iso(), "bets": bets})
    except Exception as exc:
        print(f"  ⚠️  Wett-Buch nicht geschrieben: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
