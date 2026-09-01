"""killer_push.py — die Konjunktion (Ebene ② der Übersicht) in den Trades-Channel.

01.09.2026, Lucas: „macht es dann Sinn, dieses Element auch als Telegram-Push in den Trades-Channel
zu schicken, damit ich aktiv drauf aufmerksam werde und das besser beobachten kann? … und tracken
wir da alles schon, damit wir wissen, ob's funktioniert?"

GEMESSEN, bevor gebaut wurde — beide Zahlen haben den Zuschnitt entschieden:

  · MENGE. Das Konjunktions-Buch nimmt 20–58 Zeilen pro Tag auf (Stufe 1 + 2). Als Push wäre das
    ein Bombardement, und Stufe 2 trägt in der eigenen Bilanz nur +0,2% (n=67). Gepusht wird
    deshalb NUR Stufe 1: ~5/Tag, Betfair UND Poly UND Pinnacle gleichzeitig, Bilanz 8–2.
  · ZEIT. Der Median-Abstand zwischen Latch und Anpfiff liegt bei **48 Minuten** (Stufe 1: 0,8h,
    9 von 10 innerhalb 12h). Die Konjunktion feuert also kurz vor Anpfiff — ein Push ist genau
    deshalb sinnvoll (man würde es sonst verpassen) und genau deshalb zeitkritisch. Der Job muss
    eng getaktet laufen; in `betfair.yml` sind es ~15 Minuten.

⭐ WARUM DER PUSH SEIN EIGENES BUCH BEKOMMT
`killer_ledger.json` misst, was in der SEKTION stand — zum Haltepreis, gelatcht bis zum Anpfiff.
Der Push ist etwas anderes: er geht zu EINEM Zeitpunkt raus, mit dem Preis von genau da, und wer
ihm folgt, setzt zu genau dem. Die beiden driften auseinander (Latch früher als Push, Preis läuft
zwischen Latch und Versand). Ein Channel-Track auf dem Sektions-Buch würde also etwas belegen, das
mit dem gepushten Preis nichts zu tun hat. Dieselbe Lehre wie beim Pick-Schattenbuch und beim
Shortlist-Snapshot: **wer pusht, misst den Push — nicht die Fläche, aus der er kam.**

⭐ WAS DIE NACHRICHT NICHT DARF
Behaupten, das sei freigegeben. Die Konjunktion steht auf „beobachten": eigenes Buch n=77,
ROI +3,7%, **Untergrenze −13,0%**. Jede Nachricht trägt den Stand mit, damit der Channel nie
mehr verspricht als das Register hergibt.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:                                        # Anpfiff in Lucas' Zeit, nicht in UTC — eine
    from zoneinfo import ZoneInfo           # Uhrzeit, die man erst umrechnen muss, ist keine.
    LOKAL = ZoneInfo("Europe/Vienna")
except Exception:                           # ohne tzdata lieber ehrlich UTC als falsche Ortszeit
    LOKAL = timezone.utc

import killer
import telegram_trades as TG

BASE = Path(__file__).resolve().parent
SEEN_FILE = BASE / "killer_push_seen.json"       # was schon rausging (Dedup)
LEDGER_FILE = BASE / "killer_push_ledger.json"   # das Buch DES PUSHES, zum Push-Preis

# Unter 10 Minuten Vorlauf ist eine Nachricht kein Signal mehr, sondern Lärm: bis sie gelesen ist,
# läuft das Spiel. Über 12h ist der Preis, den sie nennt, bis zum Anpfiff längst ein anderer —
# dasselbe Fenster, das auch die Sektion benutzt (KL_FENSTER_H).
PUSH_MIN_VORLAUF_MIN = int(os.environ.get("KILLER_PUSH_MIN_MIN") or 10)
PUSH_MAX_VORLAUF_H = float(os.environ.get("KILLER_PUSH_MAX_H") or 12)
SEEN_TTL_TAGE = 3
NUR_STUFE = 1
# 01.09.2026 (Lucas: „ehrlicherweise brauch ich in der Message ja keinen Link aufs Dashboard"):
# kein Link. Er hat recht — ein Deep-Link waere ohnehin nicht moeglich (das Dashboard kennt keine
# Hash-Routen), ein Link auf die Startseite haette also nur „irgendwo da drin" bedeutet. Und die
# Nachricht muss allein tragen: bei 48 Minuten Median-Vorlauf liest man sie am Handy und
# entscheidet, ohne eine Seite nachzuladen. Steht alles Noetige drin, ist der Link ueberfluessig;
# steht es nicht drin, rettet ihn der Link auch nicht.
TRENNER = "━━━━━━━━━━━━━━━━━━━"


def _now():
    return datetime.now(timezone.utc)


def _ts(x):
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except Exception:
        return None


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def schluessel(z) -> str:
    return "%s|%s" % (z.get("matchId"), z.get("markt"))


def auswahl(killer_daten, seen, now=None) -> list:
    """Stufe-1-Zeilen, die noch nicht gepusht wurden und im Vorlauf-Fenster liegen."""
    now = now or _now()
    raus = []
    for z in ((killer_daten or {}).get("stufe%d" % NUR_STUFE) or []):
        if schluessel(z) in (seen or {}):
            continue
        ko = _ts(z.get("kickoff"))
        if not ko:
            continue          # ohne Anpfiff wird nicht geraten (dieselbe Regel wie in der Übersicht)
        vor = (ko - now).total_seconds() / 60.0
        if vor < PUSH_MIN_VORLAUF_MIN or vor > PUSH_MAX_VORLAUF_H * 60:
            continue
        raus.append(z)
    raus.sort(key=lambda z: _ts(z.get("kickoff")) or now)
    return raus


def _stand_zeile(bil) -> str:
    """Der ehrliche Beipackzettel. Ohne ihn liest sich jede Nachricht wie eine Freigabe."""
    g = (bil or {}).get("gesamt") or {}
    if not g.get("n"):
        return "📓 Eigenes Buch: noch nichts abgerechnet — reine Beobachtung."
    roi = g.get("roi")
    lb = g.get("roiLb")
    f = lambda v: "—" if v is None else ("%+d%%" % round(v * 100))
    beleg = "belegt" if (lb is not None and lb > 0) else "NICHT belegt"
    belegt = lb is not None and lb > 0
    return ("📓 Eigenes Buch: %d–%d · ROI %s (Untergrenze %s)\n%s"
            % (g.get("gewonnen", 0), g.get("verloren", 0), f(roi), f(lb),
               "✅ Belegt — die Untergrenze liegt über null."
               if belegt else "⚠️ NICHT belegt — Beobachtung, keine Freigabe."))


def _esc(s) -> str:
    """Telegram sendet mit parse_mode=HTML — ein Vereinsname mit & oder < zerlegt sonst die
    Nachricht. Eigene Funktion, weil telegram_trades keine exportiert."""
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _uhrzeit(ko, now):
    """„20:45 (in 8h 12m)" — absolute Zeit ZUERST, weil die Nachricht auch später gelesen wird."""
    if not ko:
        return "—"
    m = int((ko - now).total_seconds() / 60)
    rest = ("%dh %dm" % (m // 60, m % 60)) if m >= 60 else ("%dm" % max(m, 0))
    return "%s (in %s)" % (ko.astimezone(LOKAL).strftime("%H:%M"), rest)


def _stroeme(z) -> str:
    """Die drei Belege als eine Zeile — dieselbe Reihenfolge wie im Deckungs-Profil der Sektion,
    damit zwei Nachrichten untereinander vergleichbar sind."""
    teile = []
    a = z.get("anteilPct")
    teile.append("💷 Betfair %d%%" % round(a) if a is not None else "💷 Betfair —")
    p = (z.get("poly") or {}).get("anteilPct")
    teile.append("💜 Poly %d%%" % round(p) if p is not None else "💜 Poly —")
    # Das LABEL ist fest, das Detail variabel — sonst hiesse derselbe Platz mal „Pinnacle stimmt
    # zu", mal „zieht mit +2.0pp", und zwei Nachrichten waeren nicht mehr vergleichbar.
    pinn = next((v for v in (z.get("verstaerker") or []) if v.get("art") in ("pinn", "pinnMove")), None)
    if not pinn:
        teile.append("📡 Pinnacle —")
    else:
        d = str(pinn.get("text") or "").replace("Pinnacle", "").strip(" ·")
        teile.append("📡 Pinnacle" + (" " + _esc(d) if d else ""))
    return "  ·  ".join(teile)


def _zeile(z, now, nr=None) -> str:
    ko = _ts(z.get("kickoff"))
    preis = z.get("odd")
    kopf = ("<b>%d.</b> " % nr) if nr else ""
    return "\n".join([
        "%s🏆 %s" % (kopf, _esc(z.get("league") or "—")),
        "%s v %s" % (_esc(z.get("home") or "?"), _esc(z.get("away") or "?")),
        "📋 %s" % _esc(z.get("markt") or "—"),
        "🎯 <b>%s</b>%s" % (_esc(z.get("name") or "—"), (" @ <b>%.2f</b>" % preis) if preis else ""),
        "⏱ Anpfiff %s" % _uhrzeit(ko, now),
        _stroeme(z),
    ])


def nachricht(zeilen, bil, now=None) -> str:
    """Aufbau bewusst wie die uebrigen Trades-Pushes (Titel · Trenner · Block · Fusszeile):
    der Channel soll nach EINEM Absender aussehen, nicht nach vier Werkzeugen.

    Reihenfolge im Block ist die Lesereihenfolge beim Nachspielen: Wettbewerb → Spiel → Markt →
    was genau → wie lange noch → warum. Der Preis steht bei „was genau", nicht am Ende: er ist
    der Grund, warum die Nachricht jetzt kommt und nicht in einer Stunde.
    """
    now = now or _now()
    mehrere = len(zeilen) > 1
    titel = "🔒 <b>MEHRFACH GEDECKT · Stufe 1</b>"
    if mehrere:
        titel += "  (%d Spiele)" % len(zeilen)
    bloecke = [_zeile(z, now, (i + 1) if mehrere else None) for i, z in enumerate(zeilen)]
    return "\n".join([
        titel, TRENNER,
        "<i>Alle drei Geldströme liegen gleichzeitig an.</i>", "",
        "\n\n".join(bloecke), "",
        _stand_zeile(bil),
        "🕐 %s" % now.astimezone(LOKAL).strftime("%d.%m.%Y %H:%M %Z"),
    ])


def ledger_eintragen(ledger, zeilen, now=None) -> list:
    """Jede gepushte Zeile friert IHREN Preis ein — den, der in der Nachricht stand."""
    now = now or _now()
    ledger = [dict(r) for r in (ledger or [])]
    bekannt = {r.get("k") for r in ledger}
    for z in zeilen:
        k = schluessel(z)
        if k in bekannt:
            continue
        ledger.append({
            "k": k, "matchId": z.get("matchId"), "markt": z.get("markt"),
            "liga": z.get("league"), "seite": z.get("seite"), "name": z.get("name"),
            # pushPreis ≠ haltePreis: der eine stand in der Nachricht, der andere beim Latch.
            "pushPreis": z.get("odd"), "haltePreis": z.get("haltePreis"),
            "stufe": z.get("stufe"), "gepushtAm": now.isoformat(), "kickoff": z.get("kickoff"),
            "status": "offen", "win": None, "settledAt": None,
        })
        bekannt.add(k)
    return ledger[-2000:]


def ledger_abrechnen(ledger, results=None, now=None) -> list:
    """Abrechnung aus derselben Quelle wie das Sektions-Buch — aber zum PUSH-Preis."""
    now = now or _now()
    ledger = [dict(r) for r in (ledger or [])]
    if results is None:
        results = _load(BASE / "betfair_track_results.json", [])
    erg = {"%s|%s" % (r["matchId"], r["market"]): r
           for r in (results or []) if r.get("matchId") and r.get("market")}
    for r in ledger:
        if r.get("status") != "offen":
            continue
        e = erg.get(r.get("k"))
        if e is not None and isinstance(e.get("win"), bool):
            r.update(status="abgerechnet", win=e["win"], settledAt=now.isoformat())
    return ledger


def bilanz_push(ledger=None):
    """Bilanz des CHANNELS: flach eine Einheit je Nachricht, gerechnet zum Push-Preis."""
    rows = ledger if ledger is not None else _load(LEDGER_FILE, [])
    ab = [r for r in rows if r.get("status") == "abgerechnet" and isinstance(r.get("win"), bool)]
    offen = sum(1 for r in rows if r.get("status") == "offen")
    if not ab:
        return {"gesamt": {"n": 0, "gewonnen": 0, "verloren": 0, "einheiten": 0.0,
                           "roi": None, "roiLb": None}, "offen": offen, "zeilen": []}
    renditen = []
    for r in ab:
        p = r.get("pushPreis")
        renditen.append((float(p) - 1.0) if r["win"] and p else (-1.0 if not r["win"] else 0.0))
    n = len(renditen)
    einh = sum(renditen)
    return {"gesamt": {"n": n, "gewonnen": sum(1 for r in ab if r["win"]),
                       "verloren": sum(1 for r in ab if not r["win"]),
                       "einheiten": round(einh, 2), "roi": round(einh / n, 4),
                       "roiLb": killer._untergrenze(renditen)},
            "offen": offen, "zeilen": ab[-25:]}


def main() -> int:
    now = _now()
    trocken = str(os.environ.get("DRY_RUN") or "").lower() in ("1", "true", "yes")
    seen = _load(SEEN_FILE, {})
    kd = _load(BASE / "killer.json", {})

    # Erst abrechnen, dann senden: eine abgerechnete Zeile darf nicht auf den nächsten Lauf warten.
    ledger = ledger_abrechnen(_load(LEDGER_FILE, []), now=now)

    neu = auswahl(kd, seen, now)
    if neu:
        text = nachricht(neu, killer.bilanz(), now)
        ok = True if trocken else TG.send_trades_message(text)
        if ok:
            # Nur was WIRKLICH rausging, kommt ins Buch. Ein fehlgeschlagener Send darf weder als
            # gesendet gelten noch als Zeile im Track — sonst misst der Channel Phantome.
            ledger = ledger_eintragen(ledger, neu, now)
            for z in neu:
                seen[schluessel(z)] = now.isoformat()
            print("[killer_push] %d Zeile(n) gesendet%s" % (len(neu), " (DRY_RUN)" if trocken else ""))
        else:
            print("[killer_push] Senden fehlgeschlagen — nichts vermerkt, nächster Lauf versucht es erneut")
    else:
        print("[killer_push] nichts Neues im Fenster")

    grenze = (now - timedelta(days=SEEN_TTL_TAGE)).isoformat()
    seen = {k: v for k, v in seen.items() if str(v) >= grenze}
    _save(SEEN_FILE, seen)
    _save(LEDGER_FILE, ledger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
