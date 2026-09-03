#!/usr/bin/env python3
"""
stake_settle.py — Stake-Wetten abrechnen
================================================================================
03.09.2026 (Lucas: 'bitte alles umsetzen'). Der Schritt, nach dem wir zum ersten Mal eine
gemessene Zahl haben statt einer Vermutung.

## Warum das der wichtigste Baustein ist
Stakes Schnittstelle lässt jede Wette nachschlagen:

    bet(iid: "sport:648199979") { ... on SportBet {
        status payout payoutMultiplier outcomes { status odds outcome { name } } } }

und antwortet mit `status: "settled"`, `payout: 0` und je Bein `"won"` / `"lost"`. Damit
brauchen wir für den Stake-Fluss **keine Ergebnis-Pipeline und kein Namens-Matching** — die
Wahrheit kommt aus derselben Quelle wie die Wette. Bei Betfair und Polymarket müssen wir
Ergebnisse selbst beschaffen und Namen brücken; hier fragen wir einfach nach.

## Was die Messeinheit ist — und was nicht
Gezählt wird das **BEIN** (ein Bein = eine Meinung zu einem Spiel), nicht die Wette. Bei
einer Einzelwette ist beides dasselbe. Bei einer Kombi ist jedes Bein eine Meinung, aber der
Einsatz hängt an allen zugleich — deshalb:

  · Trefferquote  → über alle Beine (Kombi-Beine zählen mit)
  · Geld / Rendite → NUR über Einzelwetten (bei einer Kombi ist kein Betrag zurechenbar)

Das ist dieselbe Trennung wie im Dashboard, wo Kombis sichtbar bleiben, aber nicht ins
Spielgeld zählen.

## Abrechnung heisst nicht „gewonnen"
`status` kennt neben won/lost auch void/cancelled/cashout. Ein annullierte Wette ist KEIN
Verlust und kein Treffer — sie fällt aus der Quote heraus und wird getrennt gezählt. Eine
Wette, die nach der Frist immer noch offen ist, bleibt als `unaufloesbar` sichtbar, statt
stillschweigend zu verschwinden (dieselbe Regel wie in poly_public_eval.py).

## Env
  STAKE_SETTLE_MAX        Wieviele Wetten je Lauf nachfragen (Default 300)
  STAKE_SETTLE_BATCH      Wieviele je GraphQL-Anfrage (Default 25, per Alias gebündelt)
  STAKE_SETTLE_REIF_H     Ab wieviel Stunden nach Anpfiff nachgefragt wird (Default 3)
  STAKE_SETTLE_AUFGEBEN_D Ab wann eine offene Wette als unaufloesbar gilt (Default 5)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import stake_highroller_fetch as SH   # Endpunkt, _post, Kurse, Ledger-IO — eine Quelle

LEDGER_FILE = BASE / "stake_bet_ledger.json"
KURS_FILE = BASE / "stake_kurse.json"
QUERY_FILE = BASE / "stake_query.json"

MAX_JE_LAUF = int(os.environ.get("STAKE_SETTLE_MAX") or 300)
BATCH = int(os.environ.get("STAKE_SETTLE_BATCH") or 25)
REIF_H = float(os.environ.get("STAKE_SETTLE_REIF_H") or 3)
AUFGEBEN_D = float(os.environ.get("STAKE_SETTLE_AUFGEBEN_D") or 5)

# Was NICHT abgerechnet ist. Am echten Endpunkt gepruefte Zustaende (03.09.2026):
#   "settled"   → fertig, payout steht, Beine tragen won/lost
#   "confirmed" → angenommen, laeuft noch (Beine "pending") ← waere fast durchgerutscht
# Die Liste ist bewusst eine Liste des OFFENEN, nicht des Fertigen: taucht morgen ein neuer
# Zwischenzustand auf, gilt er als offen und die Wette wird weiter nachgefragt. Andersherum
# waere ein unbekannter Zustand stillschweigend „abgerechnet" — und die Quote falsch.
OFFEN = {"active", "pending", "open", "confirmed", "placed", "accepted", "cashout_pending",
         None, ""}
NEUTRAL = {"void", "cancelled", "canceled", "refunded", "push", "tie"}

BEIN_FELDER = "status odds outcome { name } fixtureName"
WETT_FELDER = ("__typename ... on SportBet { amount currency status active payout "
               "payoutMultiplier potentialMultiplier createdAt updatedAt outcomes { %s } }"
               % BEIN_FELDER)


def _zeit(s):
    return SH._zeit(s)


def _parse(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def faellig(w: dict, jetzt: datetime) -> bool:
    """Ist diese Wette reif zum Nachfragen?

    Reif heisst: das Spiel ist lange genug her. Ohne Anpfiff-Angabe zählt der Zeitpunkt der
    Wette plus eine grosszuegige Frist — lieber einmal zu frueh gefragt (kostet eine Anfrage)
    als eine Wette nie abgerechnet (kostet die Messung).
    """
    if (w.get("abrechnung") or {}).get("endstand"):
        return False
    anker = _parse(w.get("anpfiff")) or _parse(w.get("ts"))
    if not anker:
        return False
    return jetzt >= anker + timedelta(hours=REIF_H)


def aufgegeben(w: dict, jetzt: datetime) -> bool:
    anker = _parse(w.get("anpfiff")) or _parse(w.get("ts"))
    return bool(anker and jetzt >= anker + timedelta(days=AUFGEBEN_D))


def _alias(i: int) -> str:
    return "b%d" % i


def frage_batch(url: str, iids: list):
    """Mehrere Wetten in EINER Anfrage — GraphQL-Aliase machen das möglich.
    300 Wetten einzeln wären 300 Anfragen; so sind es zwölf."""
    if not iids:
        return {}, None
    teile, vars_, werte = [], [], {}
    for i, iid in enumerate(iids):
        teile.append('%s: bet(iid: $i%d) { id iid bet { %s } }' % (_alias(i), i, WETT_FELDER))
        vars_.append("$i%d: String!" % i)
        werte["i%d" % i] = iid
    q = "query S(%s) { %s }" % (", ".join(vars_), " ".join(teile))
    st, d, err = SH._post(url, {"query": q, "variables": werte}, timeout=40)
    if not d or not d.get("data"):
        return {}, err or json.dumps((d or {}).get("errors"))[:200]
    out = {}
    for i, iid in enumerate(iids):
        knoten = (d["data"] or {}).get(_alias(i))
        if knoten:
            out[iid] = knoten
    return out, None


def lies_abrechnung(knoten: dict, kurse: dict = None) -> dict:
    """Aus der Antwort den Endstand ziehen. Kein Raten: was Stake nicht sagt, bleibt None."""
    b = (knoten or {}).get("bet") or {}
    status = (b.get("status") or "").lower() or None
    beine = []
    for o in (b.get("outcomes") or []):
        s = (o.get("status") or "").lower() or None
        beine.append({
            "status": s,
            "quote": o.get("odds"),
            "auswahl": ((o.get("outcome") or {}).get("name")),
            "event": o.get("fixtureName"),
            "treffer": None if (s in OFFEN or s in NEUTRAL) else (s == "won"),
            "neutral": s in NEUTRAL,
        })
    offen = status in OFFEN or any(x["status"] in OFFEN for x in beine)
    betrag = b.get("amount")
    waehrung = (b.get("currency") or "").lower() or None
    auszahlung = b.get("payout")
    einsatz_usd, _g1 = SH._usd(betrag, waehrung, {}, kurse)
    aus_usd, _g2 = SH._usd(auszahlung, waehrung, {}, kurse)
    return {
        "endstand": (not offen) and bool(status),
        "status": status,
        "beine": beine,
        "auszahlung": auszahlung,
        "auszahlungUsd": aus_usd,
        "auszahlungFaktor": b.get("payoutMultiplier"),
        "einsatzUsdGeprueft": einsatz_usd,
        # Gewinn/Verlust NUR bei Einzelwetten — bei einer Kombi haengt der Einsatz an
        # mehreren Spielen und ist keinem davon zurechenbar.
        "pnlUsd": (round(aus_usd - einsatz_usd, 2)
                   if (len(beine) == 1 and aus_usd is not None and einsatz_usd is not None)
                   else None),
        "geprueft": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def bilanz(wetten: list) -> dict:
    """Was steht im Ledger — ohne jede Bewertung, nur gezählt."""
    beine = treffer = daneben = neutral = 0
    offen = unaufloesbar = 0
    einzel_pnl, einzel_einsatz = 0.0, 0.0
    n_einzel = 0
    for w in wetten:
        a = w.get("abrechnung") or {}
        if not a.get("endstand"):
            if a.get("unaufloesbar"):
                unaufloesbar += 1
            else:
                offen += 1
            continue
        for x in a.get("beine") or []:
            beine += 1
            if x.get("neutral"):
                neutral += 1
            elif x.get("treffer") is True:
                treffer += 1
            elif x.get("treffer") is False:
                daneben += 1
        if a.get("pnlUsd") is not None and w.get("einsatzUsd"):
            n_einzel += 1
            einzel_pnl += a["pnlUsd"]
            einzel_einsatz += w["einsatzUsd"]
    gewertet = treffer + daneben
    return {
        "beine": beine, "treffer": treffer, "daneben": daneben, "neutral": neutral,
        "gewertet": gewertet,
        "quote": round(treffer / gewertet, 4) if gewertet else None,
        "offen": offen, "unaufloesbar": unaufloesbar,
        "einzelN": n_einzel,
        "einzelEinsatzUsd": round(einzel_einsatz, 2),
        "einzelPnlUsd": round(einzel_pnl, 2),
        "einzelRoi": round(einzel_pnl / einzel_einsatz, 4) if einzel_einsatz else None,
    }


def main() -> int:
    print("=== stake_settle.py ===")
    jetzt = datetime.now(timezone.utc)
    led = SH._lade(LEDGER_FILE, {})
    wetten = led.get("wetten") or []
    if not wetten:
        print("  ℹ️  leeres Ledger — nichts abzurechnen.")
        return 0

    url = (SH._lade(QUERY_FILE, {}) or {}).get("url") or SH.ENDPUNKTE[0]
    kurse = SH._lade(KURS_FILE, {})

    dran = [w for w in wetten if faellig(w, jetzt) and w.get("id")]
    dran.sort(key=lambda w: w.get("ts") or "")        # aelteste zuerst
    dran = dran[:MAX_JE_LAUF]
    print("  %d von %d Wetten sind reif (>= %.0fh nach Anpfiff)." % (len(dran), len(wetten), REIF_H))

    nach_id = {w["id"]: w for w in wetten if w.get("id")}
    geholt = fehler = 0
    for i in range(0, len(dran), BATCH):
        stapel = [w["id"] for w in dran[i:i + BATCH]]
        antw, err = frage_batch(url, stapel)
        if err:
            fehler += 1
            print("  ⚠️  Stapel %d: %s" % (i // BATCH + 1, err[:120]))
            continue
        for iid, knoten in antw.items():
            w = nach_id.get(iid)
            if not w:
                continue
            w["abrechnung"] = lies_abrechnung(knoten, kurse)
            geholt += 1

    # Wer nach der Frist immer noch offen ist, wird als unaufloesbar MARKIERT — nicht
    # geloescht. Eine Wette, die verschwindet, faelscht jede Quote nach oben.
    aufgeg = 0
    for w in wetten:
        a = w.get("abrechnung") or {}
        if not a.get("endstand") and aufgegeben(w, jetzt) and not a.get("unaufloesbar"):
            a["unaufloesbar"] = True
            a.setdefault("geprueft", jetzt.isoformat().replace("+00:00", "Z"))
            w["abrechnung"] = a
            aufgeg += 1

    led["wetten"] = wetten
    led["bilanz"] = bilanz(wetten)
    led["abgerechnet"] = jetzt.isoformat().replace("+00:00", "Z")
    SH._schreibe(LEDGER_FILE, led)

    b = led["bilanz"]
    print("  %d nachgefragt, %d als unaufloesbar markiert, %d Stapel mit Fehler." % (geholt, aufgeg, fehler))
    print("  Beine: %d gewertet (%d Treffer, %d daneben, %d neutral) · offen %d · unaufloesbar %d"
          % (b["gewertet"], b["treffer"], b["daneben"], b["neutral"], b["offen"], b["unaufloesbar"]))
    if b["quote"] is not None:
        print("  Rohe Trefferquote: %.1f%% auf n=%d — ein Punktschaetzer, kein Beleg."
              % (b["quote"] * 100, b["gewertet"]))
    if b["einzelRoi"] is not None:
        print("  Einzelwetten: ROI %.1f%% auf $%.0f Einsatz (n=%d)"
              % (b["einzelRoi"] * 100, b["einzelEinsatzUsd"], b["einzelN"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
