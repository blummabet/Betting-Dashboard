#!/usr/bin/env python3
"""
messungen.py — 15.09.2026 (Lucas: „wo sehen wir den Outcome dieser Messungen?").

🔴 Warum es das gibt. Die Antwort auf seine Frage war: nirgends. Am 14. und 15.09. wurden fuenf
Fragen bewusst offen gelassen — der Anpfiff-Abstand, der Auto-Bet gegen sein Papier, die De-vig-
Methode, eine Betfair-Schublade, die Sharp-Radar-Pushes. Genau EINE davon hatte eine Erinnerung
(die De-vig-Aufgabe am 04.10.), und die lebt ausserhalb des Repos. Die anderen vier standen nur
im Gespraechsprotokoll.

Das ist dieselbe Fehlerklasse, die der Shortlist-Track am 10.09. bereits geschlossen hat:

    „VERFALLEN IST EIN ERGEBNIS, ALSO MUSS ES DASTEHEN."

Eine offene Frage, die nur im Log steht, ist keine offene Frage — sie ist eine vergessene. Also
bekommt sie hier ein Buch, das die Pipeline fortschreibt und das Board anzeigt.

Zwei Dateien, mit Absicht getrennt:

    messungen_register.json   QUELLE. Handgepflegt: Frage, Termin, Quelle, Mindestmenge.
    messungen.json            AUSGABE. Register + gemessener Stand + Zustand. Gehoert der Pipeline.

Der wichtigste Zustand ist nicht „fertig", sondern **ueberfaellig**: Termin da, Menge nicht
erreicht. Ohne ihn verschwindet eine Messung, die nie genug Daten bekam, genauso lautlos wie
frueher ein unaufloesbarer Play — und niemand erfaehrt, dass die Frage nie beantwortet wurde.
Eine Messung ohne eingebauten Zaehler meldet „wartet auf Einbau" und NICHT „0 von 60": ein
Fortschrittsbalken, der Fortschritt behauptet, wo gar nichts zaehlt, ist eine Luege in Gruen.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent

REGISTER_FILE = "messungen_register.json"
AUSGABE_FILE = "messungen.json"

ZUSTAENDE = ("entschieden", "quelle unlesbar", "wartet auf Einbau",
             "sammelt", "bereit", "faellig", "ueberfaellig")


# ── Hilfen ─────────────────────────────────────────────────────────────────────────────────
def _laden(pfad):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        return False


def _heute(jetzt=None) -> str:
    return (jetzt or datetime.now(timezone.utc)).date().isoformat()


def _tage_bis(faellig, heute) -> int | None:
    """Tage bis zum Termin (negativ = ueberfaellig). None wenn unlesbar. REIN."""
    try:
        return (date.fromisoformat(str(faellig)) - date.fromisoformat(str(heute))).days
    except (TypeError, ValueError):
        return None


# ── Zaehler ────────────────────────────────────────────────────────────────────────────────
# Jeder Zaehler gibt die Anzahl brauchbarer Beobachtungen zurueck — oder None, wenn die Quelle
# nicht lesbar ist. None heisst NICHT null: „ich weiss es nicht" darf nicht wie „nichts da"
# aussehen, sonst zeigt das Board Fortschritt, wo eine Datei kaputt ist.
def _zaehle_track(base_dir, feld) -> int | None:
    d = _laden(os.path.join(base_dir, "poly_shortlist_track.json"))
    if not isinstance(d, dict):
        return None
    return sum(1 for r in (d.get("settled") or [])
               if isinstance(r, dict) and r.get(feld) is not None)


def _zaehle_wetten(base_dir, feld, praefixe=None) -> int | None:
    try:
        import poly_offen as PO
        praefixe = praefixe or PO.DATENSATZ_PRAEFIXE
    except Exception:
        praefixe = praefixe or ("wm_", "liga_", "mls_", "shortlist_")
    gesehen, irgendwas = 0, False
    for pfx in praefixe:
        d = _laden(os.path.join(base_dir, f"{pfx}auto_bets_placed.json"))
        if d is None:
            continue
        if d is False:
            return None
        irgendwas = True
        for b in (d.get("bets") or []):
            if isinstance(b, dict) and b.get(feld) is not None:
                gesehen += 1
    return gesehen if irgendwas else None


def zaehler_htk_shortlist(base_dir):
    """Abgerechnete Shortlist-Plays, bei denen der Anpfiff-Abstand beim Einstieg feststeht."""
    return _zaehle_track(base_dir, "htkAtEntry")


def zaehler_htk_trader(base_dir):
    """Wetten des Pinnacle-Traders mit festgehaltenem Anpfiff-Abstand."""
    return _zaehle_wetten(base_dir, "htkAtEntry", ("wm_", "liga_", "mls_"))


def zaehler_echte_fills(base_dir):
    """Auto-Bets, deren CLV auf dem ECHTEN Fill gemessen wurde (nicht auf dem Papier-Preis)."""
    return _zaehle_wetten(base_dir, "clvPP", ("shortlist_",))


def zaehler_reaktiv_faelle(base_dir):
    """Verworfene Betfair-Alarme (Ausgang schon entschieden) im Buch."""
    d = _laden(os.path.join(base_dir, "betfair_reaktiv_ledger.json"))
    if d is None:
        return 0            # Buch noch nicht angelegt = noch kein Fall, nicht „unbekannt"
    if not isinstance(d, dict):
        return None
    f = d.get("faelle")
    return len(f) if isinstance(f, list) else None


def zaehler_einigkeit_schatten(base_dir):
    """Beobachtete (nicht gesendete) Einigkeits-Kandidaten im Schattenbuch.

    18.09.2026: das Buch entsteht, damit die Frage NICHT in der Rueckschau beantwortet wird —
    dort war sie zirkulaer. Gezaehlt wird, wie viele Faelle aus der Zukunft schon dastehen.
    """
    d = _laden(os.path.join(base_dir, "poly_einigkeit_schatten.json"))
    if d is None:
        return 0            # Buch noch nicht angelegt = noch kein Fall, nicht „unbekannt"
    if not isinstance(d, list):
        return None
    # 🔴 Gezaehlt werden nur ABGERECHNETE Zeilen. Alle zu zaehlen waere derselbe Fehler, den das
    # Board schon einmal hatte: ein Wort, das etwas anderes benennt als die Zahl daneben. Ein
    # offener Kandidat ist keine Beobachtung — er kann noch in beide Richtungen ausgehen, und
    # „40 von 40 erreicht" haette dann keinen einzigen Ausgang gesehen.
    return sum(1 for e in d if isinstance(e, dict) and e.get("status") == "settled")


def zaehler_bf_leadshare(base_dir):
    """Abgerechnete Betfair-Public-Pushes AUSSERHALB der Top-5-Ligen, die ihren Einseitigkeits-
    Anteil mitfuehren.

    19.09.2026: `leadShare` steht erst seit kurzem in der Ledger-Zeile. Ohne das Feld laesst
    sich die Frage nur nachbauen — und der Nachbau war verzerrt. Gezaehlt wird deshalb, wie
    viele Zeilen die Frage ueberhaupt beantworten koennen.
    """
    TOP5 = {"English Premier League", "Italian Serie A", "German Bundesliga",
            "Spanish La Liga", "French Ligue 1"}
    d = _laden(os.path.join(base_dir, "betfair_public_ledger.json"))
    if d is None:
        return 0
    if not isinstance(d, list):
        return None
    return sum(1 for r in d if isinstance(r, dict)
               and r.get("status") in ("won", "lost")
               and r.get("scenario") == "fresh"
               and r.get("league") not in TOP5
               and isinstance(r.get("leadShare"), (int, float)))


ZAEHLER = {
    "bf_leadshare": zaehler_bf_leadshare,
    "einigkeit_schatten": zaehler_einigkeit_schatten,
    "htk_shortlist": zaehler_htk_shortlist,
    "htk_trader": zaehler_htk_trader,
    "echte_fills": zaehler_echte_fills,
    "reaktiv_faelle": zaehler_reaktiv_faelle,
}


# ── Urteil ─────────────────────────────────────────────────────────────────────────────────
def zustand(eintrag, stand_n, heute) -> tuple:
    """(Zustand, Klartext). REIN/testbar.

    Reihenfolge mit Absicht: eine getroffene Entscheidung schliesst den Eintrag, egal was der
    Zaehler sagt. Danach kommt die Ehrlichkeit ueber die Quelle — erst zuletzt der Fortschritt.
    """
    if not isinstance(eintrag, dict):
        return "quelle unlesbar", "Eintrag unlesbar"
    if eintrag.get("entscheidung"):
        return "entschieden", str(eintrag["entscheidung"])

    messer = eintrag.get("messer")
    mindest = eintrag.get("mindestN")
    tage = _tage_bis(eintrag.get("faellig"), heute)

    # Offene Entscheidungen haben keine Menge — nur einen Termin.
    if mindest in (None, 0) and not messer:
        if tage is None:
            return "sammelt", "kein Termin hinterlegt"
        if tage > 0:
            return "sammelt", "Entscheidung offen · in %d Tag(en) faellig" % tage
        return "faellig", "Entscheidung faellig%s" % (
            " (seit %d Tagen)" % -tage if tage < 0 else "")

    if messer and messer not in ZAEHLER:
        return "wartet auf Einbau", 'Zaehler "%s" gibt es noch nicht \u2014 es wird nichts erfasst' % messer
    if stand_n is None:
        return "quelle unlesbar", "Quelle nicht lesbar — Stand unbekannt"

    genug = mindest is None or stand_n >= int(mindest)
    menge = "%d von %s" % (stand_n, mindest if mindest else "—")
    if tage is None:
        return ("bereit" if genug else "sammelt"), "%s Beobachtungen · kein Termin" % menge
    if tage > 0:
        return (("bereit" if genug else "sammelt"),
                "%s Beobachtungen · faellig in %d Tag(en)" % (menge, tage))
    if genug:
        return "faellig", "%s Beobachtungen · Entscheidung faellig" % menge
    return ("ueberfaellig",
            "Termin erreicht, aber nur %s Beobachtungen — die Frage ist NICHT beantwortet" % menge)


def fortschritt(stand_n, mindest) -> float | None:
    """Anteil 0..1 fuer den Balken. None = nichts zu zeigen (kein Balken statt falscher Balken)."""
    try:
        m = int(mindest)
    except (TypeError, ValueError):
        return None
    if m <= 0 or stand_n is None:
        return None
    return max(0.0, min(1.0, float(stand_n) / m))


def buch(register, base_dir, heute=None) -> dict:
    """Register + gemessener Stand + Zustand. Defensiv: ein kaputter Eintrag kippt nie das Buch."""
    heute = heute or _heute()
    eintraege = []
    if isinstance(register, dict):
        roh = register.get("messungen") or []
    elif isinstance(register, list):
        roh = register
    else:
        roh = []
    for e in roh:
        if not isinstance(e, dict):
            continue
        messer = e.get("messer")
        stand_n = None
        if messer in ZAEHLER:
            try:
                stand_n = ZAEHLER[messer](base_dir)
            except Exception:
                stand_n = None
        z, text = zustand(e, stand_n, heute)
        zeile = dict(e)
        zeile.update({"standN": stand_n, "zustand": z, "stand": text,
                      "fortschritt": fortschritt(stand_n, e.get("mindestN")),
                      "tageBisFaellig": _tage_bis(e.get("faellig"), heute)})
        eintraege.append(zeile)
    # Was Aufmerksamkeit braucht, steht oben.
    rang = {"ueberfaellig": 0, "faellig": 1, "quelle unlesbar": 2, "wartet auf Einbau": 3,
            "bereit": 4, "sammelt": 5, "entschieden": 6}
    eintraege.sort(key=lambda z: (rang.get(z["zustand"], 9),
                                  z.get("tageBisFaellig") if z.get("tageBisFaellig") is not None else 9999))
    offen = [z for z in eintraege if z["zustand"] != "entschieden"]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "heute": heute,
        "messungen": eintraege,
        "n": len(eintraege),
        "nOffen": len(offen),
        "nHandlung": sum(1 for z in eintraege
                         if z["zustand"] in ("faellig", "ueberfaellig", "wartet auf Einbau",
                                             "quelle unlesbar")),
    }


def main() -> int:
    print("=== messungen.py ===")
    from safe_write import write_json_atomic
    reg = _laden(os.path.join(str(BASE), REGISTER_FILE))
    if reg is False:
        print("  🛑 messungen_register.json nicht lesbar — Buch unveraendert gelassen.")
        return 0
    if reg is None:
        print("  ℹ️  Kein Register — nichts zu fuehren.")
        reg = {"messungen": []}
    b = buch(reg, str(BASE))
    write_json_atomic((BASE / AUSGABE_FILE), b, indent=1)
    print(f"  🔬 {b['n']} Messung(en) · {b['nOffen']} offen · {b['nHandlung']} brauchen Aufmerksamkeit")
    for z in b["messungen"]:
        mark = "⚠️ " if z["zustand"] in ("faellig", "ueberfaellig", "wartet auf Einbau",
                                         "quelle unlesbar") else "   "
        print(f"  {mark}[{z['zustand']}] {z.get('id')}: {z['stand']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
