#!/usr/bin/env python3
"""claude_picks.py — Claudes eigene Picks: senden, abrechnen, bewerten (12.10.2026).

Lucas: „Mich wuerde wirklich nur interessieren, wie du es siehst … da sehe ich enormes Potenzial,
wenn man aus dem eine Methode macht." Und: „Das mit dir und den Picks ist mir wichtiger."

EINGABE  claude_picks.json      — schreibt nur Claude (von Hand, mit Begruendung).
AUSGABE  claude_picks_buch.json — schreibt nur dieser Lauf (Status, CLV, Ergebnis, Bilanz).
Zwei Dateien, damit der Pipeline-Commit nie mit einem neuen Pick kollidiert.

⭐ DIE ZAHL, AN DER SICH DAS MESSEN LAESST, IST DER CLV — NICHT DIE TREFFERQUOTE.
Ein Pick ist richtig, wenn der faire Pinnacle-Preis bis Anpfiff in seine Richtung laeuft.
Das sagt schon nach 50-100 Picks etwas; Treffer und ROI brauchen Hunderte. Beides steht im
Buch, aber das Urteil haengt am CLV und seiner Untergrenze.

Gerechnet wird mit `kurs` — dem Preis, den der Pick als „lohnt ab" nennt. Darunter hat der
Pick nach eigener Aussage keinen Wert; wer zu einem schlechteren Preis spielt, spielt einen
anderen Pick.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
EINGABE = "claude_picks.json"
BUCH = "claude_picks_buch.json"
HIST = "betfair_consensus_history.json"
ERGEBNISSE = "betfair_track_results.json"
ARCHIV = "team_archiv.json"
Z = 1.645
UG_MIN_N = 30
SEITEN = {"home": 0, "draw": 1, "away": 2}


def _load(name, default=None):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return default


def _ts(x):
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def seiten_p(p3, markt, seite):
    """Faire Wahrscheinlichkeit der Pick-Seite. Draw No Bet: ohne das Remis renormiert. REIN."""
    if not (isinstance(p3, (list, tuple)) and len(p3) == 3) or seite not in SEITEN:
        return None
    i = SEITEN[seite]
    if markt == "dnb":
        if seite == "draw":
            return None
        a, b = p3[i], p3[2 - i]
        return a / (a + b) if (a + b) > 0 else None
    return p3[i]


def schlusskurs(hist_punkte, anpfiff):
    """Letzter Pinnacle-Stand VOR Anpfiff aus der Konsens-Historie. REIN."""
    ko = _ts(anpfiff)
    best = None
    for p in hist_punkte or []:
        t = _ts((p or {}).get("ts"))
        if t and ko and t <= ko and isinstance(p.get("pinn"), list):
            if best is None or t > best[0]:
                best = (t, p["pinn"])
    return best[1] if best else None


def ausgang(markt, seite, ft):
    """'win' | 'push' | 'loss' | None. REIN."""
    if not (isinstance(ft, (list, tuple)) and len(ft) == 2):
        return None
    h, a = ft
    erg = "home" if h > a else ("away" if a > h else "draw")
    if markt == "dnb" and erg == "draw":
        return "push"
    return "win" if erg == seite else "loss"


def rendite(ergebnis, kurs):
    if ergebnis is None or not isinstance(kurs, (int, float)):
        return None
    return {"win": kurs - 1.0, "push": 0.0, "loss": -1.0}[ergebnis]


def endstaende():
    out = {}
    try:
        import betfair_track_store
        for z in betfair_track_store.load(str(BASE / ERGEBNISSE)):
            if isinstance(z, dict) and z.get("ft"):
                out[str(z.get("matchId"))] = z["ft"]
    except Exception:
        pass
    for mid, s in ((_load(ARCHIV, {}) or {}).get("spiele") or {}).items():
        out.setdefault(str(mid), s.get("ft"))
    return out


def bewerte(pick, hist, ft_map, jetzt):
    """Ein Pick -> seine Buchzeile (ohne Versandfelder). REIN."""
    z = {k: pick.get(k) for k in ("id", "gesetztAm", "matchId", "spiel", "liga", "anpfiff",
                                  "markt", "seite", "auswahl", "kurs", "grund")}
    p0 = seiten_p(pick.get("pinnBeimPick"), pick.get("markt"), pick.get("seite"))
    z["pBeimPick"] = round(p0, 4) if p0 is not None else None
    ko = _ts(pick.get("anpfiff"))
    if ko and jetzt >= ko:
        sk = schlusskurs(hist.get(str(pick.get("matchId"))) or [], pick.get("anpfiff"))
        p1 = seiten_p(sk, pick.get("markt"), pick.get("seite")) if sk else None
        z["pSchluss"] = round(p1, 4) if p1 is not None else None
        z["clvPP"] = round((p1 - p0) * 100, 2) if (p0 is not None and p1 is not None) else None
    erg = ausgang(pick.get("markt"), pick.get("seite"), ft_map.get(str(pick.get("matchId"))))
    z["ergebnis"] = erg
    z["ft"] = ft_map.get(str(pick.get("matchId")))
    z["rendite"] = rendite(erg, pick.get("kurs"))
    z["status"] = ("abgerechnet" if erg else
                   ("laeuft" if ko and jetzt >= ko else "offen"))
    return z


def bilanz(zeilen):
    """n, Treffer, ROI und CLV mit Untergrenze. Das Urteil haengt am CLV. REIN."""
    ab = [z for z in zeilen if z.get("rendite") is not None]
    clv = [z["clvPP"] for z in zeilen if isinstance(z.get("clvPP"), (int, float))]
    b = {"n": len(zeilen), "abgerechnet": len(ab),
         "gewonnen": sum(1 for z in ab if z["ergebnis"] == "win"),
         "push": sum(1 for z in ab if z["ergebnis"] == "push"),
         "verloren": sum(1 for z in ab if z["ergebnis"] == "loss"),
         "roi": round(100 * sum(z["rendite"] for z in ab) / len(ab), 1) if ab else None,
         "nClv": len(clv),
         "clvSchnittPP": round(sum(clv) / len(clv), 2) if clv else None,
         "clvPositivPct": round(100 * sum(1 for c in clv if c > 0) / len(clv)) if clv else None,
         "clvUgPP": None}
    if len(clv) >= UG_MIN_N:
        m = sum(clv) / len(clv)
        sd = math.sqrt(sum((c - m) ** 2 for c in clv) / (len(clv) - 1))
        b["clvUgPP"] = round(m - Z * sd / math.sqrt(len(clv)), 2)
    if b["clvUgPP"] is not None:
        b["urteil"] = "schlägt den Markt" if b["clvUgPP"] > 0 else "nicht belegt"
    else:
        b["urteil"] = "sammelt (Urteil ab %d Picks mit Schlusskurs)" % UG_MIN_N
    return b


def nachricht(pick):
    try:
        from zoneinfo import ZoneInfo
        uhr = _ts(pick.get("anpfiff")).astimezone(ZoneInfo("Europe/Vienna")).strftime("%H:%M")
    except Exception:
        uhr = str(pick.get("anpfiff") or "")[11:16] + " UTC"
    e = lambda s: str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return ("🤖 <b>CLAUDE-PICK</b>\n"
            "⚽ %s · %s · %s\n"
            "→ <b>%s</b> · lohnt ab @%.2f\n\n"
            "%s" % (e(pick.get("spiel")), e(pick.get("liga")), uhr,
                    e(pick.get("auswahl")), float(pick.get("kurs") or 0), e(pick.get("grund"))))


def main(jetzt=None, senden=None) -> int:
    jetzt = jetzt or datetime.now(timezone.utc)
    picks = (_load(EINGABE, {}) or {}).get("picks") or []
    alt = {z.get("id"): z for z in ((_load(BUCH, {}) or {}).get("zeilen") or []) if isinstance(z, dict)}
    hist = _load(HIST, {}) or {}
    ft_map = endstaende()
    zeilen = []
    for p in picks:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        z = bewerte(p, hist, ft_map, jetzt)
        a = alt.get(p["id"]) or {}
        # Einmal gemessen, bleibt gemessen: ein spaeter fehlender Verlauf loescht keinen CLV.
        for k in ("pSchluss", "clvPP", "ergebnis", "ft", "rendite"):
            if z.get(k) is None and a.get(k) is not None:
                z[k] = a[k]
        if a.get("ergebnis") and z["status"] != "abgerechnet":
            z["status"] = "abgerechnet"
        for k in ("gesendetAm", "versand"):
            if a.get(k):
                z[k] = a[k]
        ko = _ts(p.get("anpfiff"))
        if not z.get("versand"):
            if ko and jetzt < ko and os.environ.get("CLAUDE_PICKS_PUSH", "1") != "0":
                if senden is None:
                    from telegram_trades import send_trades_message as senden
                ok = senden(nachricht(p))
                z["versand"] = "gesendet" if ok else "nicht_konfiguriert"
                z["gesendetAm"] = jetzt.isoformat()
            elif ko and jetzt >= ko:
                z["versand"] = "zu_spaet"     # erst nach Anpfiff im Repo — nicht nachtraeglich senden
        zeilen.append(z)
    zeilen.sort(key=lambda z: str(z.get("anpfiff") or ""), reverse=True)
    aus = {"generatedAt": jetzt.isoformat(), "bilanz": bilanz(zeilen), "zeilen": zeilen,
           "ausgelassen": (_load(EINGABE, {}) or {}).get("ausgelassen") or {}}
    from safe_write import write_json_atomic
    write_json_atomic(BASE / BUCH, aus, indent=None)
    b = aus["bilanz"]
    print("[claude_picks] %d Picks · %d abgerechnet · CLV %s pp (n=%d) · %s"
          % (b["n"], b["abgerechnet"], b["clvSchnittPP"], b["nClv"], b["urteil"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
