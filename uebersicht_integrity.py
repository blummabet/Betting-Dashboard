#!/usr/bin/env python3
"""
uebersicht_integrity.py — Ausgabe-Korrektheits-Batterie fuer die Uebersicht.

Vorgeschichte (04.09.2026, Lucas): „mir waere es wichtig fehlerfrei zu sein, weil sonst ist die
ganze Arbeit in Wahrheit umsonst."

Die Betfair-, Poly- und WM-Pipelines haben je eine Guard-Batterie auf ihre eigenen Daten. Die
UEBERSICHT hatte keine — dabei ist sie die Flaeche, auf die Lucas zuerst schaut, und sie ist die
einzige, die Daten aus ELF Engines zu Saetzen verdichtet. Genau dort entstehen die Fehler:

    04.09.2026, drei Funde an einem Tag, alle derselben Bauart —
    ein Satz oder ein Ranking behauptet etwas, das die Zahl daneben widerlegt:

      · „Beste Streaks" sortierte nach Laenge und schrieb die Grundrate dazu — fuenfmal
        derselbe Markt, der haeufigste im Angebot, als „heisseste Serien".
      · „keine Schublade hat ihre Untergrenze ueber null" — Liga·ABWAEGEN stand bei
        ROI-UG +3,7 %; blockiert hatte die CLV-Bedingung.
      · „🎮 Poly Public n155 · 70 % · +5,0 %" — das ist die Vorschau, die NICHTS sendet;
        das echte Push-Buch stand bei n=3.

Kein einziger davon war ein Absturz, eine Fehlrechnung oder ein Datenfehler. Es waren immer
BEHAUPTUNGEN, die zum Schreibzeitpunkt stimmten und danach still veralteten. Ein Unit-Test faengt
davon nur, was jemand zu testen dachte; diese Batterie prueft die LIVE-Artefakte bei jedem Lauf.

Leitprinzip (wie bei den anderen dreien): Wenn eine Aussage auf der Uebersicht von den Daten nicht
mehr gedeckt ist, MUSS es sichtbar werden — nicht still danebenstehen.

REIN/testbar: `run_checks(ctx)` bekommt die Artefakte als dict und macht keine Datei-Zugriffe.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATUS_FILE = "uebersicht_integrity.json"


# 🔴 19.09.2026: welche Artefakte DA, aber unlesbar waren. Vorher war das nicht unterscheidbar
# — `except Exception: return default` machte aus einer zerschossenen Datei eine leere.
UNLESBAR = []


def _lade(name: str, default=None):
    """Artefakt lesen. FEHLT die Datei -> default (legitim). Ist sie da und unlesbar -> default,
    aber gemerkt (s. check_artefakte_sind_lesbar).

    19.09.2026 (Lucas: „Heut kein einziger polymarket Push in public (kann nicht sein)"):
    15 Poly-Artefakte trugen Git-Konfliktmarker, alle Leser bekamen still {} zurueck, und die
    Poly-Seite schwieg drei Stunden ohne einen roten Lauf."""
    pfad = BASE / name
    try:
        roh = pfad.read_text(encoding="utf-8")
    except OSError:
        return default                      # nicht da = noch kein Zustand, kein Befund
    try:
        return json.loads(roh)
    except ValueError as e:
        UNLESBAR.append((name, "Konfliktmarker im Artefakt"
                         if "\n<<<<<<< " in roh or roh.startswith("<<<<<<< ")
                         else type(e).__name__))
        return default


# ── Die Guards ────────────────────────────────────────────────────────────────
# Jeder traegt den Vorfall, aus dem er entstanden ist. Ein Guard ohne Vorfall ist eine Meinung.

def _c(label, severity, failures, hinweis=""):
    return {"label": label, "severity": severity, "failures": failures,
            "nFail": len(failures), "ok": not failures, "hinweis": hinweis}


def check_serien_rangfolge(ctx):
    """04.09.2026 — „Beste Streaks" zeigte fuenfmal „Team trifft 15x · Grundrate 82 %".

    Die Kachel sortierte nach LAENGE und schrieb die Grundrate selbst daneben. Laenge ist ueber
    Maerkte hinweg nicht vergleichbar: „Team trifft" gelingt im Liga-Schnitt in vier von fuenf
    Spielen, „Zu null" in einem von vier. Ohne `zufallPct` faellt die Uebersicht auf genau diese
    Sortierung zurueck — der Guard schlaegt an, BEVOR das jemand auf dem Board sieht.
    """
    fails = []
    for name in ("ligaStreaks", "mlsStreaks"):
        d = ctx.get(name) or {}
        st = d.get("streaks") or []
        if not st:
            continue
        ohne = [s for s in st if not isinstance(s.get("zufallPct"), (int, float))]
        if len(ohne) > len(st) * 0.5:
            fails.append(f"{name}: {len(ohne)}/{len(st)} Serien ohne zufallPct — die Uebersicht "
                         f"faellt auf die Laengen-Sortierung zurueck (der Fehler vom 04.09.)")
        if (d.get("_meta") or {}).get("sortiert") != "zufallPct":
            fails.append(f"{name}: _meta.sortiert ist '{(d.get('_meta') or {}).get('sortiert')}' "
                         f"statt 'zufallPct' — Produzent und Anzeige rangieren verschieden")
    return _c("Serien werden nach Seltenheit rangiert, nicht nach Laenge", "error", fails)


def check_freigabe_grund(ctx):
    """04.09.2026 — „keine Schublade hat ihre Untergrenze ueber null" war schlicht falsch.

    Liga·ABWAEGEN stand bei n=46, ROI +24,4 %, ROI-UG +3,7 %; gescheitert ist sie an der
    CLV-Bedingung. Der Satz wird seither aus den Daten bestimmt — dieser Guard prueft, dass die
    DATEN das ueberhaupt hergeben: ohne `roiLb`/`clvLb` je Schublade kann die Uebersicht den
    Grund nicht nennen und faellt auf eine Behauptung zurueck.
    """
    f = ctx.get("freigabe") or {}
    alle = f.get("alle") or []
    fails = []
    if not alle:
        return _c("Freigabe-Grund ist aus den Daten ableitbar", "warn",
                  ["freigabe.json hat keine Schubladen — Ebene 1 kann nichts begruenden"])
    minN = ((f.get("regeln") or {}).get("minN")) or 30
    reif = [r for r in alle if (r.get("n") or 0) >= minN]
    ohne_roi = [r for r in reif if "roiLb" not in r]
    if ohne_roi:
        fails.append(f"{len(ohne_roi)}/{len(reif)} reife Schubladen ohne Feld roiLb — "
                     f"der Blockierungsgrund waere wieder geraten")
    # Und die inhaltliche Probe: wenn eine reife Schublade die ROI-Huerde nimmt, darf nirgends
    # mehr „keine hat ihre Untergrenze ueber null" stehen. Das prueft der Frontend-Test; hier
    # wird nur gemeldet, DASS der Fall vorliegt — damit er nicht unbemerkt bleibt.
    roi_ok = [r for r in reif if isinstance(r.get("roiLb"), (int, float)) and r["roiLb"] > 0]
    hinweis = ""
    if roi_ok:
        hinweis = ("Fall liegt aktuell vor: " + ", ".join(r["schublade"] for r in roi_ok[:3])
                   + " nehmen die ROI-Huerde und scheitern an CLV — der Satz auf Ebene 1 muss das sagen")
    return _c("Freigabe-Grund ist aus den Daten ableitbar", "error", fails, hinweis)


def check_poly_kachel_ist_keine_kanalbilanz(ctx):
    """04.09.2026 — „🎮 Poly Public n155 · 70 % · +5,0 %" ganz oben im Puls.

    Das ist der Track der Public-KANDIDATEN — eine Vorschau, die nichts sendet (poly-wallets.js
    sagt es selbst). Das echte Push-Buch stand bei n=3. Lucas hatte dieselbe Verwechslung am
    Morgen im Track-Record gemeldet; in der Uebersicht stand sie noch.
    """
    p = (ctx.get("pulse") or {}).get("poly")
    fails = []
    if not p:
        return _c("Poly-Kachel gibt sich nicht als Kanal-Bilanz aus", "warn",
                  [], "kein Poly-Block im Puls — nichts zu pruefen")
    if p.get("sendet") is not False:
        fails.append("pulse.poly.sendet ist nicht False — die Vorschau kann wieder als "
                     "Kanal-Bilanz gelesen werden (Fund vom 04.09.)")
    if "gesendetN" not in p:
        fails.append("pulse.poly.gesendetN fehlt — die Zahl der WIRKLICH gesendeten Pushs "
                     "steht nicht daneben")
    return _c("Poly-Kachel gibt sich nicht als Kanal-Bilanz aus", "error", fails)


def check_stake_kategorien(ctx):
    """04.09.2026 — „Chicago Cubs – Milwaukee Brewers" stand trotz US-Sport-Sperre in einer Kachel.

    Die Alt-Zeile trug keine Kategorie, der Filter las `kat || ''` und liess sie durch. Seit
    `ledger_mischen()` nachtraegt, verlaesst sich das Frontend darauf. Faellt das Nachtragen aus,
    fliegen die Zeilen jetzt still RAUS statt durch — besser, aber trotzdem meldenswert.
    """
    fails = []
    d = ctx.get("stake") or {}
    w = d.get("wetten") or []
    ohne = [x for x in w if not x.get("kat")]
    if ohne:
        fails.append(f"{len(ohne)}/{len(w)} Stake-Wetten ohne kat — das Frontend blendet sie "
                     f"aus (unbekannt ist keine Erlaubnis), aber der Feed verliert sie")
    return _c("Jede Stake-Wette traegt ihre Sportart", "error", fails)


def check_betfair_urteil(ctx):
    """04.09.2026 — die Fade-Schwelle stand an VIER Stellen, drei davon von einem Test gleich
    gehalten, die vierte (`_tMute`) bei -0,05 statt -0,10.

    Das Urteil faellt seither einmal im Produzenten und wandert als `urteil` mit. Fehlt das Feld,
    lesen drei Flaechen nichts — und irgendwer baut die Schwelle nach.
    """
    t = ctx.get("bfTrack") or {}
    fails = []
    g = t.get("global")
    if not isinstance(g, dict):
        return _c("Betfair-Buckets tragen ihr Urteil mit", "warn", [], "kein bfTrack geladen")
    if "urteil" not in g:
        fails.append("betfair_track_record.json ohne Feld `urteil` — die drei Verbraucher "
                     "koennen nur noch selbst vergleichen (Fund vom 04.09.)")
    blm = t.get("byLeagueMarket") or {}
    mit_ug = [v for v in blm.values() if isinstance(v.get("roiUg"), (int, float))]
    ohne_urteil = [v for v in mit_ug if not v.get("urteil")]
    if ohne_urteil:
        fails.append(f"{len(ohne_urteil)} Buckets mit Untergrenze, aber ohne Urteil")
    # 07.09.2026 (Uebersicht-Check) — der zweite Teil derselben Geschichte. Das Urteil fiel zwar
    # nur noch an EINER Stelle, aber es fiel falsch: „verliert" haengte an der UNTERgrenze
    # (<= -10 %), und eine tiefe Untergrenze belegt Unsicherheit, keinen Verlust. Gemessen an
    # dem Tag: 40 Buckets mit „verliert", **37 davon mit einer Obergrenze ueber null**, 18 mit
    # positivem Punktschaetzer — bis +32,6 % (Argentinian Primera Nacional | Over/Under 3.5,
    # n=36, UG -14,3 %, OG +79,5 %). Das Urteil nahm Zeilen aus der Rangliste und mutete
    # Terminal-Zeilen.
    #
    # Dieselbe Regel steht seit dem 07.09. in stake_liga_stufe.kreuz: folgen belegt die
    # UNTERgrenze ueber null, dagegenhalten die OBERgrenze unter null.
    falsch = [v for v in blm.values()
              if v.get("urteil") == "verliert" and isinstance(v.get("roiOg"), (int, float))
              and v["roiOg"] >= 0]
    if falsch:
        beispiel = max(falsch, key=lambda v: v.get("roi") or -9)
        fails.append(f"{len(falsch)} Buckets mit Urteil „verliert\u201c, deren OBERgrenze ueber "
                     f"null liegt — das ist kein Verlustbeleg (schlimmster Fall: ROI "
                     f"{100 * (beispiel.get('roi') or 0):+.1f} %, OG {100 * beispiel['roiOg']:+.1f} %, "
                     f"n{beispiel.get('n')})")
    fehlt_og = [v for v in mit_ug if v.get("roiOg") is None and (v.get("n") or 0) >= 30]
    if len(fehlt_og) == len(mit_ug) and mit_ug:
        fails.append("kein einziger Bucket traegt eine Obergrenze — ohne sie laesst sich "
                     "„verliert\u201c gar nicht belegen (Produzent noch nicht neu gelaufen?)")
    return _c("Betfair-Buckets tragen ihr Urteil mit", "error", fails)


def check_quellen_haben_zeitstempel(ctx):
    """03.09.2026 — die Frische-Anzeige war „erfuellt, aber nicht gemessen".

    `_ageMin` konnte `asof` nicht lesen, also war das Alter immer null: der Guard galt als
    erfuellt (Feld in der Liste), gemessen wurde nie. Eine Quelle ohne lesbaren Zeitstempel
    verschwindet still aus der Frische-Zeile, statt als veraltet aufzufallen.
    """
    ZEIT = ("generatedAt", "updatedAt", "asof", "aktualisiert", "capturedAt", "stand")
    fails = []
    for name in ("betfair", "bfTrack", "bfOverview", "freigabe", "pulse", "moneyMap",
                 "ligaStreaks", "mlsStreaks", "stake", "stakeAus"):
        d = ctx.get(name)
        if not isinstance(d, dict):
            continue
        flach = {k for k in d}
        tief = set((d.get("_meta") or {}) if isinstance(d.get("_meta"), dict) else {})
        if not (flach | tief) & set(ZEIT):
            fails.append(f"{name}: kein lesbarer Zeitstempel ({'/'.join(ZEIT[:3])}…) — "
                         f"faellt still aus der Frische-Zeile")
    return _c("Jede Quelle der Uebersicht traegt einen Zeitstempel", "warn", fails)


def check_serie_seltenheit_nennt_ihren_nenner(ctx):
    """05.09.2026 — auf der Uebersicht stand „Parma · Unter 2,5 Tore · intakt · vorher 83% ·
    1 von 4.541". Die beiden Zahlen gehoeren nicht zueinander: 0,83^9 waere 1 von 5.
    `zufallPct` rechnet IMMER gegen die Liga-Grundrate (hier 39 % → 0,39^9 = 1 von 4.541),
    waehrend `basis`/`ratePct` beschreiben, worauf der ZUSTAND beruht.

    Der Guard prueft die Rechnung selbst: `zufallPct` muss aus `ligaBasisPct` und `length`
    folgen. Weicht sie ab, rechnet jemand wieder mit einer anderen Rate als der, die
    danebensteht.
    """
    fails = []
    for quelle in ("ligaStreaks", "mlsStreaks"):
        for s in ((ctx.get(quelle) or {}).get("streaks") or []):
            z, lb, ln = s.get("zufallPct"), s.get("ligaBasisPct"), s.get("length")
            if z is None or lb is None or not ln:
                continue
            # `ligaBasisPct` ist GERUNDET (39 statt 39,37). Bei p^9 wird aus 1 % Rundung
            # ~9 % Abweichung — ein fester Toleranzwert waere hier eine Fehlalarm-Maschine
            # (erster Entwurf dieses Guards meldete prompt 8 gesunde Serien). Deshalb wird
            # gegen das Intervall geprueft, das die Rundung ueberhaupt zulaesst.
            lo = (max(lb - 0.5, 0.0) / 100.0) ** ln * 100
            hi = (min(lb + 0.5, 100.0) / 100.0) ** ln * 100
            if hi <= 0:
                continue
            if not (lo * 0.999 <= z <= hi * 1.001):
                fails.append(f"{quelle}: {s.get('team')} {s.get('type')} {ln}x — zufallPct {z} "
                             f"liegt ausserhalb dessen, was ligaBasisPct {lb}% zulaesst "
                             f"({lo:.5f}..{hi:.5f}) — es wurde mit einer anderen Rate gerechnet")
    return _c("Serien-Seltenheit folgt aus der Liga-Basis, die danebensteht", "error", fails[:8])


def check_serie_seltenheit_rechnet_mit_der_eigenen_rate(ctx):
    """08.09.2026 — externes Feedback zur Serien-Seite, an den Artefakten nachgerechnet und
    bestaetigt: „Parma · Unter 2,5, 10er-Serie: 1 von 11.990 (Liga-Basis 39 %)" stand direkt
    neben „Eigenrate vor der Serie 80 %". Mit 0,8^10 sind das 1 von 9. Faktor 1.290.

    ⭐ Der aeltere Guard `check_serie_seltenheit_nennt_ihren_nenner` war GRUEN dabei — er prueft,
    dass `zufallPct` sauber aus der Liga-Basis folgt, und das tat sie. Ein Guard, der die
    Arithmetik einer Zahl bewacht, die die falsche Frage beantwortet, meldet nichts. Deshalb
    dieser hier: er prueft nicht die Rechnung, sondern den NENNER.

    Drei Saetze:
      1. Wo eine eigene Vor-Serien-Rate existiert, ist sie der Nenner — nicht der Liga-Schnitt.
      2. Eine Seltenheit ohne eigene Vorgeschichte heisst „nicht belegbar". Die Liga-Rate gilt
         fuer ein Durchschnittsteam; ob dieses Team eines ist, wissen wir dann gerade nicht.
      3. „auffaellig" gibt es nur mit eigener Rate UND einem Erwartungswert unter 1 im Suchfeld.
         Ohne die Feldgroesse ist jede Seltenheit ein Fund, den die Suche selbst erzeugt hat.
    """
    fails = []
    for quelle in ("ligaStreaks", "mlsStreaks"):
        for s in ((ctx.get(quelle) or {}).get("streaks") or []):
            se = s.get("seltenheit")
            wer = "%s: %s %s %sx" % (quelle, s.get("team"), s.get("type"), s.get("length"))
            if not isinstance(se, dict):
                fails.append("%s — keine `seltenheit` im Artefakt (alter Produzentenstand?)" % wer)
                continue
            # 1) eigene Rate schlaegt Liga-Schnitt
            if s.get("basis") == "prior" and se.get("basis") != "eigen":
                fails.append("%s — eigene Vor-Serien-Rate vorhanden, gerechnet wurde aber gegen "
                             "den Liga-Schnitt" % wer)
            # 2) ohne Vorgeschichte kein Urteil
            if se.get("basis") == "liga" and se.get("urteil") != "nicht belegbar":
                fails.append("%s — ohne eigene Vorgeschichte als '%s' ausgewiesen"
                             % (wer, se.get("urteil")))
            # 3) auffaellig braucht die Feldgroesse und einen Erwartungswert unter 1
            if se.get("urteil") == "auffaellig":
                if not se.get("familie"):
                    fails.append("%s — 'auffaellig' ohne Feldgroesse: ohne sie ist jede "
                                 "Seltenheit ein Fund der Suche selbst" % wer)
                _b = se.get("erwartetBand")
                if not (isinstance(_b, list) and len(_b) == 2 and _b[1] < 1.0):
                    fails.append("%s — 'auffaellig', obwohl die guenstigste eigene Rate "
                                 "mindestens einen solchen Lauf im Feld erwarten laesst" % wer)
            # 4) die Zahl muss aus der genannten Rate folgen (gerundet -> Intervall)
            r, ln, eins = se.get("ratePct"), s.get("length"), se.get("einsZu")
            if r and ln and eins:
                # `ratePct` ist gerundet (82 statt 81,6) und `einsZu` ebenfalls (2 statt 2,21).
                # Beides zusammen macht bei kleinen Werten die Rundung groesser als jede echte
                # Abweichung — der erste Entwurf dieses Guards meldete prompt 8 gesunde Serien
                # (Arsenal „Sieg-Serie 3x", 0,67^3 = 1 von 3,3 -> gerundet 3). Geprueft wird
                # deshalb gegen das Intervall, das die Rundung ueberhaupt zulaesst, plus die
                # eine Einheit, die das Runden von `einsZu` selbst kostet.
                lo = (max(r - 0.5, 0.0) / 100.0) ** ln
                hi = (min(r + 0.5, 100.0) / 100.0) ** ln
                if lo > 0 and not (round(1.0 / hi) - 1 <= eins <= round(1.0 / lo) + 1):
                    fails.append("%s — '1 von %s' folgt nicht aus der genannten Rate %s%% "
                                 "(zulaessig %d..%d)"
                                 % (wer, eins, r, round(1.0 / hi) - 1, round(1.0 / lo) + 1))
    return _c("Serien-Seltenheit rechnet mit der Rate, die danebensteht", "error", fails[:8],
              "Eigene Vor-Serien-Rate schlaegt den Liga-Schnitt; ohne Vorgeschichte kein Urteil.")


def check_money_map_meldet_ihre_luecken(ctx):
    """05.09.2026 — Brighton v Leeds stand in der Money Map mit „Poly · kein Markt" und 2/3
    Quellen, waehrend dieselbe Uebersicht zwei Kacheln weiter $439.712 Poly-Geld auf Brighton
    zeigte. Ursache: Polymarket schreibt den dritten 1X2-Ausgang als
    „Draw (Brighton & Hove Albion FC vs. Leeds United FC)"; die Nicht-Team-Liste wurde exakt
    verglichen und erkannte ihn als TEAMNAME. Damit hatte `team_keys` drei statt zwei
    Eintraege und der Abkuerzungs-Rueckfall vom 12.08. konnte fuer **543 von 565 1X2-Maerkten
    (96 %)** nie greifen — tot seit dem Tag seiner Einfuehrung.

    Schlimmer: der Miss-Zaehler prueft(e) gegen den GEWAEHLTEN Pool, und das ist im Fehlerfall
    gerade der Rueckfall-Pool, der ausgewaehlt wurde, WEIL nichts matchte. Der Zaehler war
    blind fuer genau die Faelle, die er zaehlen soll — Brighton stand nicht in der Liste.

    Der Guard misst deshalb nicht die Liste, sondern die Sache: eine Zeile mit Betfair-Geld,
    ohne Poly, aber mit vorhandenem Poly-Markt ist eine stille Luecke.
    """
    fails = []
    mm = ctx.get("moneyMap") or {}
    rows = mm.get("rows") or []
    poly = ctx.get("polyClose") or {}
    if not rows or not poly:
        return _c("Money Map meldet ihre Luecken", "warn", [])
    # Erster Entwurf dieses Guards suchte nur den HEIM-Namen irgendwo in den Ausgaengen und
    # meldete prompt „Villarreal v Deportivo" — getroffen hatte er ein Villarreal-Spiel vom
    # 16.08. Die Bedingung muss die PAARUNG sein: beide Teams im selben Markt.
    maerkte = [set(str(a).lower() for a in v["prices"])
               for v in poly.values() if isinstance(v, dict) and v.get("prices")]
    for r in rows:
        if not r.get("betfair") or r.get("poly"):
            continue
        heim, gast = str(r.get("home") or "").lower(), str(r.get("away") or "").lower()
        if len(heim) < 4 or len(gast) < 4:
            continue
        for aus in maerkte:
            if any(heim in a for a in aus) and any(gast in a for a in aus):
                fails.append(f"{r.get('home')} v {r.get('away')}: Money Map ohne Poly, aber ein "
                             f"Poly-Markt mit BEIDEN Teams existiert — stille Luecke, nicht Abwesenheit")
                break
    return _c("Money Map meldet ihre Luecken", "error", fails[:8])


def check_money_map_poly_gehoert_zum_spiel(ctx):
    """07.09.2026 (Uebersicht-Check) — die Money Map zeigte fuer **Al-Ahed v Al Ahli Akhaa Aley**
    (Lebanese FA Cup, live) „Poly $267.964 · Konsens einig auf Al-Ahed · 2/3".

    Das Geld gehoerte zu `spl-hil-ahl-2026-09-01` — Al Hilal gegen Al Ahli (Saudi Pro League),
    einem Markt, der **sechs Tage vorher abgerechnet** war und im selben Board zwei Kacheln
    weiter mit $257K unter „Volumen ueber Norm" stand. Der Join lief ueber den
    Abkuerzungs-Rueckfall: „Al Ahli Akhaa Aley" gegen „Al Ahli Saudi Club" ergab 0,50, „Al-Ahed"
    gegen „Al Hilal Saudi Club" teilte nur „al" — Summe 0,83 ueber der Rueckfall-Schwelle 0,60.

    Zwei Ursachen, beide in `betfair_consensus` behoben: der Kandidaten-Pool enthielt jeden
    abgerechneten Snapshot (2.494 von 2.557 — der Close-Feed haelt sie 30 Tage fuer die
    Auswertung), und der Rueckfall liess ein Zwei-Buchstaben-Token als Beleg gelten.

    Der Guard prueft nicht den Weg, sondern das Ergebnis: der Poly-Outcome-Name einer Zeile
    muss zu einem der beiden Teams dieser Zeile gehoeren. Ein Konsens aus fremdem Geld ist
    schlimmer als gar kein Konsens — er sieht nach Bestaetigung aus.
    """
    import re as _re
    import unicodedata as _ud

    def _tok(x):
        x = _ud.normalize("NFKD", str(x or "")).encode("ascii", "ignore").decode().lower()
        return {t for t in _re.split(r"[^a-z0-9]+", x) if len(t) >= 3}

    fails = []
    for r in ((ctx.get("moneyMap") or {}).get("rows") or []):
        p = r.get("poly") or {}
        nm = p.get("name")
        if not nm:
            continue
        _seiten = _tok(r.get("home")) | _tok(r.get("away"))
        if _tok(nm) & _seiten:
            continue
        # 14.09.2026 (Status-Seite): FEHLALARM. „Inter v Udinese" stand hier rot, weil die
        # Poly-Seite „FC Internazionale Milano" heisst — dasselbe Team, anderer Name. Der
        # Vergleich auf ganze Wortmarken kennt nur Gleichheit, und „inter" ist nicht
        # „internazionale". Das Geld lag zu 96 % auf der Heimseite und gehoerte genau dorthin.
        #
        # Ein Waechter, der bei korrekten Daten dauerhaft rot steht, wird weggeschaut — und dann
        # faellt der echte Fall (Al-Hilal-Geld in einer Al-Ahed-Zeile) mit durch. Deshalb: eine
        # Wortmarke gilt auch, wenn sie den ANFANG der anderen bildet — aber erst ab fuenf
        # Zeichen. Genau das war die Luecke damals: „al" als Beleg. Fuenf Zeichen sind lang
        # genug, dass ein Praefix den Verein benennt und nicht bloss seine Sprache.
        if any(a.startswith(b) or b.startswith(a)
               for a in _tok(nm) for b in _seiten
               if min(len(a), len(b)) >= 5):
            continue
        fails.append(f"{r.get('home')} v {r.get('away')} ({r.get('league')}): Poly-Seite heisst "
                     f"„{nm}\u201c und gehoert zu keinem der beiden Teams — "
                     f"${p.get('usd')} fremdes Geld in einer Konsens-Zeile")
    return _c("Money Map: die Poly-Seite gehoert zum Spiel", "error", fails[:8])


def check_stake_kachel_zeigt_das_gemessene_urteil(ctx):
    """05.09.2026 — die Uebersichts-Kachel „Stake · über der Norm" zeigte rechts weiter
    `faktor` (× Median der Liga): „4,7× über Erwartung … ×42,7" ueber
    „4,9× über Erwartung … ×129,9". Der laengste Balken gehoerte dem schwaecheren Fund.
    `faktor` waechst mit der Stichprobengroesse (r = +0,68, Befund vom 04.09.) und wurde
    deshalb abgesetzt; `stake-radar.js` war umgestellt, die Uebersicht nicht — eine
    Rollout-Luecke.

    Der Guard haelt fest, dass jede Zeile mit gemessenem Urteil dieses auch mitliefert.
    """
    fails = []
    rows = ((ctx.get("stakeAus") or {}).get("auffaellige") or [])
    for r in rows[:12]:
        if r.get("ueberErwartung") is not None and r.get("zufallPct") is None:
            fails.append(f"{r.get('event')}: ueberErwartung gesetzt, aber kein zufallPct — "
                         f"die Kachel haette nur den abgesetzten Median-Faktor zu zeigen")
    return _c("Stake-Auffaelligkeiten tragen ihr gemessenes Urteil", "error", fails[:8])


def check_stake_spielklasse(ctx):
    """07.09.2026 — Lucas: „ne 50k Wette auf Arsenal sagt 0 / Eine 50k Wette auf ein
    2-3. Liga Team ist zumindest jemand der mehr dran glaubt."

    Die Spielklasse steht in keinem Feld des Stake-Feeds; sie kommt aus einer Tabelle
    (`stake_liga_stufe.py`). Eine Tabelle veraltet still: Stake nimmt laufend neue Ligen auf,
    und eine Liga, die nicht drinsteht, verschwindet aus jeder Zeile der Ansicht — ohne dass
    irgendwo etwas rot wird. Genau die Klasse „fehlende Information rendert als harmloser
    Default", nur eine Ebene hoeher: hier ist der harmlose Default die LEERE.

    Zweitens: die beiden Richtungen duerfen nicht zusammenfallen. Gemessen am 07.09. laufen
    Ebene 1 und Ebene 2/3 gegenlaeufig (-2,1 % -> -13,9 % gegen +7,5 % -> +46,7 %). Steht in
    der Auswertung nur noch eine gemeinsame Schublade, ist der Unterschied weggemittelt — und
    der ganze Punkt der Ansicht damit weg.
    """
    a = ctx.get("stakeAus") or {}
    r = a.get("randliga")
    if not isinstance(r, dict):
        return _c("Stake-Spielklasse: Tabelle vollstaendig?", "warn", [],
                  hinweis="kein randliga-Block in stake_auswertung.json — dann ist ueber die "
                          "Spielklassen nichts gesagt.")
    fails = []
    n_ohne = r.get("nOhneEbene") or 0
    if n_ohne:
        fails.append("%d Fussball-Ligen ohne Eintrag in stake_liga_stufe.py (%s) — sie fallen "
                     "aus jeder Zeile der Ansicht, statt aufzufallen"
                     % (n_ohne, ", ".join((r.get("ohneEbene") or [])[:6])))
    # 🔴 22.09.2026 (Lucas schickt einen Fremd-Post aus der uzbekischen Pro League). Der
    # Wachhund oben findet Ligen, die FEHLEN. Er findet nicht, was falsch drinsteht: unter
    # `pro-league` lag die uzbekische ZWEITE Liga als Ebene 1, unter `1st-division` lagen
    # daenische Zweitligen neben der zyprischen Ersten. Gefunden wurde das nur, weil jemand
    # einen fremden Radar-Post geschickt hat — das ist keine Methode.
    # Die Turnier-ID aus dem Feed macht es zaehlbar; sie sammelt sich seit dem 22.09.
    md = r.get("mehrdeutig") or {}
    kand = md.get("kandidaten") or {}
    if kand:
        fails.append("%d Liga-Schluessel bezeichnen mehrere Turniere und tragen trotzdem eine "
                     "Spielklasse (%s) — eine Zahl davon ist fuer die Haelfte der Spiele falsch"
                     % (len(kand), ", ".join(sorted(kand)[:6])))
    sch = a.get("schubladen") or {}
    for name in ("randliga_hoher_einsatz", "topliga_hoher_einsatz"):
        if name not in sch:
            fails.append("Schublade %s fehlt — die beiden Richtungen sind gegenlaeufig und "
                         "duerfen nicht in einer Zahl zusammenfallen" % name)
    for name in ("randliga_hoher_einsatz", "topliga_hoher_einsatz"):
        d = sch.get(name) or {}
        if d.get("belegt") and d.get("beinRoiUg") is None:
            fails.append("%s heisst belegt, ohne Untergrenze — ein Punktschaetzer ist kein "
                         "Beleg" % name)
    return _c("Stake-Spielklasse: Tabelle vollstaendig, Richtungen getrennt", "error", fails[:8])


def check_poly_deckung(ctx):
    """06.09.2026 — Lucas zeigte einen Polymarket-Screenshot: Bologna-Sassuolo $49,99K,
    Juventus-Milan $94,62K. Beide standen bei uns als „kein Markt". Ich hatte aus „nicht in
    unseren Artefakten" auf „gibt es nicht" geschlossen.

    Das Problem hinter dem Problem: **ein Scanner kann nicht melden, was er nie gesehen hat.**
    `health/poly-global.json` und `poly_status.json` standen beide auf gruen — sie messen, ob
    der Lauf DURCHLIEF, nicht ob er VOLLSTAENDIG war. Eine Lueckenmessung braucht eine zweite,
    unabhaengige Quelle: `liga_poly_prices.json` vom Liga-Fetcher.

    Gemessen am 06.09.: 9 Maerkte fehlten, 5 davon im 8h-Latch-Fenster, alle unter dem
    Volumen-Boden von $7.500 — der auch fuer die kostenlosen PREIS-Zweige galt, obwohl er nur
    das Holder-Budget schuetzen soll.
    """
    import poly_deckung as PD
    lp = ctx.get("ligaPoly") or {}
    if not (lp.get("prices")):
        return _c("Poly-Deckung: Money-Scan gegen Liga-Fetcher", "warn", [])
    keys = set(ctx.get("polyClose") or {}) | set(ctx.get("polyUpcoming") or {}) \
        | set(ctx.get("polyHistory") or {})
    if not keys:
        return _c("Poly-Deckung: Money-Scan gegen Liga-Fetcher", "warn", [])
    nah = PD.nah(PD.luecken(lp, keys))
    fails = ["%s (%s v %s, Anpfiff in %.1fh) — der Liga-Fetcher hat den Markt, der Money-Scan nie"
             % (r["slug"], r["home"], r["away"], r["htk"]) for r in nah]
    # 🔴 20.09.2026: diese Messung ist ein MOMENT. Der Fund vom selben Tag
    # („sea-mil-lec-2026-09-20, Anpfiff in 0.1h") war zwanzig Minuten spaeter verschwunden —
    # mit dem Anpfiff faellt die Luecke aus dem Fenster. Auf „passiert das oft?" gab es deshalb
    # nie eine Zahl, nur „gerade keine".
    # Fehlerklasse: eine Luecke, die sich durch Zeitablauf selbst erledigt, hinterlaesst keine
    # Statistik. Der Scanner fuehrt jetzt ein Buch; hier steht, was es sagt.
    buch = ctx.get("polyDeckungBuch") or {}
    if buch:
        b = PD.bilanz(buch)
        bis_anpfiff = [z for z in (buch.get("slugs") or {}).values()
                       if isinstance(z, dict) and not z.get("nachgeholt")
                       and (z.get("minHtk") is not None and z["minHtk"] <= PD.NAH_H)]
        if bis_anpfiff:
            fails.append("Buch: %d Markt/Maerkte wurden bis zum Anpfiff nie erfasst (%s) — dort "
                         "entstanden Picks blind zum Geld"
                         % (len(bis_anpfiff),
                            "; ".join("%s (%.1fh)" % (z.get("slug"), z.get("minHtk"))
                                      for z in sorted(bis_anpfiff,
                                                      key=lambda x: x.get("minHtk") or 0)[:4])))
        elif b["quotePct"] is not None and b["nLaeufeMitLuecke"]:
            fails.append("Buch: in %d von %d Laeufen (%d %%) war eine Deckungsluecke offen — "
                         "alle wurden noch vor dem Anpfiff nachgeholt (%s)"
                         % (b["nLaeufeMitLuecke"], b["nLaeufe"], b["quotePct"], b["urteil"]))
    return _c("Poly-Deckung: Money-Scan gegen Liga-Fetcher", "error", fails[:8])


def check_preis_signal_deckung(ctx):
    """06.09.2026 — Lucas: „ich kann mir nicht vorstellen, dass wir mit all den Infos nichts
    Vernuenftiges machen koennen." Konnte man; es lag nur nicht am Modell.

    Gemessen ueber die drei Signal-Ledger: die Preis/Geld-Signale sind die EINZIGE Familie mit
    belegtem CLV-Zusammenhang (r = +0,353, p = 0,0001, n = 156, Bootstrap-KI [+0,21; +0,48]).
    Die Staerke-Signale (Form, xG, Serien) liegen bei r = +0,003. Und **162 von 318 Picks
    trugen kein einziges Preis-Signal** — die blinde Haelfte war fast vollstaendig Ueber/Unter
    und BTTS.

    Die Ursache lag nicht in der Engine, sondern in der Zuleitung: `append_snapshot` schrieb
    BTTS nie in die Zeitreihe (0 von 27.086 Snapshots) und legte ueberhaupt nur dann einen
    Snapshot an, wenn sich das 1X2 bewegt hatte. Beides am 06.09. behoben.

    Dieser Guard misst, ob der Fix ANKOMMT. Ein gruener Test an einer Funktion sagt nur, dass
    die Funktion tut, was sie soll — nicht, dass ihr Ergebnis bei den Picks landet. Er sieht
    nur die letzten `FENSTER_TAGE`, weil sich die Zeitreihe nicht rueckwirkend fuellen laesst
    und der Altbestand den Befund sonst monatelang verduennt.
    """
    import preis_deckung as PD
    recs = []
    for k in ("ligaLedger", "mlsLedger"):
        recs += ((ctx.get(k) or {}).get("records") or [])
    d = PD.deckung(recs)
    if d is None:
        return _c("Preis-Signal-Deckung: entstehen Picks blind zum Markt?", "warn", [],
                  hinweis="Noch keine %d abgerechneten Picks im %d-Tage-Fenster — kein Urteil."
                          % (PD.MIN_N, int(PD.FENSTER_TAGE)))
    return _c("Preis-Signal-Deckung: entstehen Picks blind zum Markt?", "error",
              PD.befunde(d),
              hinweis="%d Picks im Fenster, %.0f %% ohne Preis-Signal." % (d["n"], d["blindPct"]))


def check_stumme_signale(ctx):
    """06.09.2026 — `polymarket_sharp` las das Poly-Volumen unter `poly_vol`, die Produktion
    schreibt es unter `vol`. Default 0, Gate bei 5.000 USD: **nie gefeuert**, in keinem von 318
    abgerechneten Picks — waehrend in unserer eigenen Datei Everton–Manchester United mit
    7,87 Mio. USD stand. Dasselbe bei `steam_lag`.

    Auffallen konnte das nicht: ein defektes Signal sieht von aussen aus wie ein Signal, das
    gerade nichts zu sagen hat. Stille meldet sich nicht von selbst.

    Der Guard urteilt NICHT, ob ein Signal zu Recht schweigt — `mls_travel` hat in der Liga
    nichts zu suchen, `altitude_signal` in den Top 5 auch nicht. Er stellt die Liste hin.
    Deshalb `warn` und nicht `error`: die Deutung gehoert an den Menschen, das Hinsehen an die
    Maschine.
    """
    import signal_stille as SS
    try:
        from sharp_signals.registry import SIGNAL_GROUPS
    except Exception as e:
        return _c("Stumme Signale: wer hat nie gefeuert?", "warn", [],
                  hinweis="Registry nicht ladbar: %s" % e)
    recs = []
    for k in ("ligaLedger", "mlsLedger"):
        recs += ((ctx.get(k) or {}).get("records") or [])
    st = SS.stumme(recs, list(SIGNAL_GROUPS))
    if st is None:
        return _c("Stumme Signale: wer hat nie gefeuert?", "warn", [],
                  hinweis="Weniger als %d abgerechnete Picks — Stille sagt hier nichts."
                          % SS.MIN_RECORDS)
    # NICHT ueber registry._load_disabled_signals: das liest COCOBET_PROFILE aus der Umgebung.
    # Dieser Guard laeuft mal mit, mal ohne gesetztes Profil — dann haette er die WM-Liste
    # gemeldet und behauptet, nichts sei abgeschaltet. Der Ledger hier ist liga+mls, also
    # werden beide Profile direkt aus der Konfiguration gelesen.
    aus = set()
    try:
        _cfg = json.loads((BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        for _p in ("liga_default", "mls_default"):
            aus |= set(((_cfg.get("profiles") or {}).get(_p) or {}).get("disabled_signals") or [])
    except Exception:
        pass
    geteilt = SS.abgeschaltet_und_stumm(st, aus)
    zeilen = SS.befunde(geteilt["stumm_trotz_an"], recs)
    return _c("Stumme Signale: wer hat nie gefeuert?", "warn", zeilen,
              hinweis="%d von %d Signalen schweigen ueber %d Picks — davon %d bewusst "
                      "abgeschaltet (%s), %d an und trotzdem stumm."
                      % (len(st), len(SIGNAL_GROUPS), len(recs),
                         len(geteilt["abgeschaltet"]), ", ".join(geteilt["abgeschaltet"]) or "—",
                         len(geteilt["stumm_trotz_an"])))


def check_signal_bilanz(ctx):
    """06.09.2026 — Lucas: „ich dachte, wenn ein Signal zum Scheissen ist, wird es
    runtergewichtet; ich dachte, das funktioniert sowieso."

    Der Lern-Loop lief (164 Laeufe seit dem 26.06.), aber er konnte nie sagen, dass etwas GUT
    ist: der Massstab war die eigene Trefferquote, und damit landeten alle Gewichte unter 1 —
    gemessene Spanne am 05.09.: **0,590 bis 1,034**, erlaubt waeren 0,300 bis 1,700. Er konnte
    abwerten und praktisch nicht aufwerten. Ausserdem vergibt er Gewichte, aber keine Konfidenz:
    ein Gewicht von 0,9 sagt nicht, ob das belegt ist.

    Dieser Guard liest die Bilanz (`build_signal_bilanz.py`) und meldet, was BELEGT schadet —
    geschichtet nach der Zahl der uebrigen Signale, damit nicht jedes Signal den Vorteil
    signalreicher Picks erbt (r = +0,131 zwischen Signalzahl und CLV).
    """
    import signal_bilanz as SB
    bil = dict((ctx.get("signalBilanz") or {}).get("signale") or {})
    # MLS-Bilanz nur ergaenzend: Signale, die dort gemessen sind und in der Liga nicht.
    for k, v in ((ctx.get("signalBilanzMls") or {}).get("signale") or {}).items():
        bil.setdefault(k, v)
    if not bil:
        return _c("Signal-Bilanz: schadet ein Signal belegt?", "warn", [],
                  hinweis="Keine Bilanz vorhanden — build_signal_bilanz.py laeuft nicht.")
    gut, schlecht = SB.tragende(bil), SB.schaedliche(bil)
    return _c("Signal-Bilanz: schadet ein Signal belegt?", "warn", SB.befunde(bil),
              hinweis="%d Signale belegt beitragend, %d belegt schaedlich. %s"
                      % (len(gut), len(schlecht), SB.MEHRFACHTEST_HINWEIS))


def check_fade_kontrolle(ctx):
    """06.09.2026 — der Fade-Unter-Befund haengt an seiner Kontrollgruppe.

    Die Regel („Geld auf UNTER einer Ganzspiel-Torlinie → wir spielen ÜBER") kam aus einer Suche
    ueber 16 Markt×Seite-Schnitte. Was sie von einem Zufallsfund unterscheidet, ist NICHT der
    ROI, sondern dass dieselbe Rechnung auf drei Kontrollmaerkten korrekt VERLIERT:

        Match Odds H                Geldseite +1,2 pp besser als implizit  →  Fade -4,6 %
        Both teams to Score? YES               +1,8 pp besser              →  Fade -6,9 %
        First Half Goals 1.5 UNDER             +1,1 pp besser              →  Fade -7,5 %

    Gewinnt der Fade dort auch, dann erzeugt die Konstruktion eine Kante aus sich selbst — am
    wahrscheinlichsten, weil der angenommene Overround verrutscht ist. Dann ist der Befund oben
    wertlos, und das muss auffallen, BEVOR jemand danach spielt.

    Zweitens: die Zeile darf nicht behaupten, belegt zu sein, solange sie nur aus dem Rueckblick
    lebt. Der Rueckblick ist der Fund, nicht der Beleg.
    """
    d = ctx.get("fadeUnter")
    if not isinstance(d, dict) or not d.get("regel"):
        return _c("Fade-Unter: haelt die Kontrollgruppe?", "warn", [],
                  hinweis="fade_unter.json fehlt — dann ist ueber die Regel nichts gesagt.")
    # 🔴 16.09.2026: hier stand `k["roi"] > 0` — ein PUNKTSCHAETZER. Match Odds H kippte an dem
    # Tag auf +0,47 % mit Untergrenze −4,18 % (n=2.329) und haette den Guard rot gemacht, ohne
    # dass irgendetwas belegt waere. Dieselbe Korrektur wie am 07.09. am Betfair-Urteil
    # „verliert": die Aussage haengt an der Schranke, nicht am Schnitt. Der Schnitt steht
    # weiterhin in der Meldung — als Bewegung, nicht als Urteil.
    fails = []
    for k in (d.get("kontrolle") or []):
        if isinstance(k.get("roiUg"), (int, float)) and k["roiUg"] > 0:
            fails.append("%s %s: der Fade gewinnt hier BELEGT (%+.1f %%, UG %+.1f %%, Geldseite "
                         "%+.1f pp) — die Rechnung misst sich selbst, der Befund traegt nicht"
                         % (k.get("markt"), k.get("seite"), 100 * (k.get("roi") or 0),
                            100 * k["roiUg"], k.get("vorsprungPP") or 0))
    if not (d.get("kontrolle") or []):
        fails.append("keine Kontrollmaerkte im Artefakt — ein Befund ohne Kontrollgruppe ist "
                     "eine Behauptung")
    vr = d.get("vorreg") or {}
    rb = d.get("rueckblick") or {}
    if vr.get("belegt") is False and rb.get("belegt"):
        pass   # normal: der Rueckblick sieht gut aus, der Beleg fehlt noch — genau so gedacht
    return _c("Fade-Unter: haelt die Kontrollgruppe?", "error", fails,
              hinweis="seit Vorregistrierung n=%d (%s) · Rueckblick n=%d, nicht Teil des Urteils."
                      % (vr.get("n") or 0,
                         ("UG %+.1f %%" % (100 * vr["roiUg"])) if vr.get("roiUg") is not None
                         else "kein Urteil",
                         rb.get("n") or 0))


def check_poly_markt_gehoert_zur_selben_mannschaft(ctx):
    """08.09.2026 (Uebersicht-Check) — `betfair_anker.json` hing den SENIOREN-Markt an das
    Nachwuchsspiel: „Real Madrid U19 v Inter U19" (UEFA Youth League) fuehrte
    `ucl-rma-int-2026-09-08` mit **$294.571** — dem Geld von Real Madrid v Inter am selben Abend.
    Fuenf Faelle in einer Datei; `ucl-por-mnc-2026-09-08` hing sogar gleichzeitig an Porto U19
    **und** an Man City, also an zwei Betfair-Spielen auf einmal.

    Der bestehende Guard `check_money_map_poly_gehoert_zum_spiel` sieht das nicht: „Real Madrid
    U19" und „Real Madrid CF" teilen sehr wohl Tokens — sie sind ja fast derselbe Name. Genau
    das ist der Punkt. Ein Altersmarker (U19, II, W, Jong) ist keine Namensvariante, sondern
    eine andere Mannschaft, und ein Namens-Score kann das grundsaetzlich nicht trennen.

    Zwei Saetze werden hier geprueft, beide am fertigen Artefakt statt am Weg dorthin:
      1. Die Mannschafts-Ebene der Poly-Seite stimmt mit der des Betfair-Teams ueberein.
      2. Ein Poly-Markt haengt an hoechstens EINEM Spiel — derselbe Topf zweimal ist immer falsch.
    """
    try:
        from betfair_consensus import elf_marker
    except Exception as e:                                   # pragma: no cover
        return _c("Poly-Markt gehoert zur selben Mannschaft", "warn",
                  [f"elf_marker nicht ladbar: {e}"])

    fails = []
    anker = (ctx.get("bfAnker") or {}).get("anker") or {}
    belegt = {}
    for mid, v in anker.items():
        if not isinstance(v, dict):
            continue
        p = v.get("poly") or {}
        key, name = p.get("key"), p.get("sideKey") or p.get("name")
        if not key:
            continue
        belegt.setdefault(key, []).append((mid, v))
        seite = v.get("moneyName")
        if name and seite and elf_marker(seite) != elf_marker(name):
            fails.append(f"{v.get('league')}: Betfair-Seite „{seite}\u201c gegen Poly „{name}\u201c — "
                         f"andere Mannschaftsebene ({sorted(elf_marker(seite)) or 'erste Elf'} vs "
                         f"{sorted(elf_marker(name)) or 'erste Elf'}), ${p.get('vol')} fremdes Geld")
    for key, zeilen in belegt.items():
        if len(zeilen) > 1:
            wo = ", ".join(f"{v.get('league')}/{v.get('moneyName')}" for _, v in zeilen)
            fails.append(f"Poly-Markt {key} haengt an {len(zeilen)} Betfair-Spielen: {wo}")
    return _c("Poly-Markt gehoert zur selben Mannschaft", "error", fails[:8],
              "Nachwuchs- und Frauenteams teilen fast alle Tokens mit der ersten Mannschaft — "
              "der Namens-Score kann sie nicht trennen, der Marker schon.")


def check_buecher_punktestand(ctx):
    """08.09.2026 — Ebene 2 zeigt seit heute die Spitze aller bewerteten Spiele, mit den vier
    Buechern als Spalten. Der Guard, der vorher die Spielzentrale pruefte, prueft jetzt dieselbe
    Aussage an der Stelle, an der sie steht.

    Vier Saetze, jeder aus einem Fehler, der die Tafel ohne sichtbaren Unterschied entwerten wuerde:
      1. `punkte` ist die Summe der Teile — sonst steht eine Zahl da, die niemand nachrechnen kann.
      2. `moeglich` ist die Summe der Nenner. Ein nicht erhobenes Buch senkt den NENNER und kostet
         keine Punkte; steht es trotzdem im Nenner, sieht ein vollstaendiges Spiel schlechter aus
         als ein halb erhobenes.
      3. Tiefe zaehlt nur, wo das Buch auch zustimmt — sonst waere „viel Geld auf der GEGENSEITE"
         ein Pluspunkt.
      4. Jede Zeile traegt ihre `teile`. Ohne sie kann die Tafel Punkte zeigen, aber nicht warum —
         und genau das war der Grund, warum die 145 bewerteten Spiele monatelang unsichtbar blieben.
    """
    fails = []
    for r in ((ctx.get("killer") or {}).get("alleBewertet") or []):
        if not isinstance(r, dict):
            continue
        wer = "%s (%s)" % (r.get("name"), r.get("liga"))
        teile = r.get("teile")
        if not teile:
            fails.append("%s: keine Aufschluesselung (`teile`) — Punkte ohne Begruendung" % wer)
            continue
        summe = sum((t.get("punkte") or 0) for t in teile if isinstance(t, dict))
        nenner = sum((t.get("moeglich") or 0) for t in teile if isinstance(t, dict))
        if r.get("punkte") != summe:
            fails.append("%s: punkte %s, Summe der Teile %s" % (wer, r.get("punkte"), summe))
        if r.get("moeglich") != nenner:
            fails.append("%s: moeglich %s, Summe der Nenner %s" % (wer, r.get("moeglich"), nenner))
        for t in teile:
            if not isinstance(t, dict):
                continue
            if t.get("status") == "unbekannt" and (t.get("moeglich") or 0) != 0:
                fails.append("%s: Buch %s ist nicht erhoben, steht aber im Nenner"
                             % (wer, t.get("buch")))
            _g = (t.get("grund") or {}).get("ok")
            _t = (t.get("tiefe") or {}).get("ok")
            if _t and not _g:
                fails.append("%s: Buch %s zaehlt Tiefe, obwohl es nicht zustimmt"
                             % (wer, t.get("buch")))
    return _c("Buecher-Punktestand: die Zahl stimmt mit ihrer Begruendung ueberein", "error",
              fails[:8],
              "Nicht erhobene Buecher senken den Nenner, Tiefe zaehlt nur bei Zustimmung.")


def check_clv_urteil_passt_zur_zahl(ctx):
    """15.09.2026 (Lucas-Uebersicht-Check) — im Register standen 8 von 200 Zeilen mit einer
    CLV-Zahl NEBEN dem Urteil „· kein CLV": „Public-Pushes −2,35 pp · kein CLV",
    „Public · Halbzeit −18,18 pp · kein CLV", dazu 5 Betfair-Markt-Schubladen.

    Ursache war die Reihenfolge, nicht die Rechnung: die Aggregat-Quellen rufen `bewerte()` mit
    einer LEEREN CLV-Liste (Betfair fuehrt kein Closing je Signal) und setzen `clv` erst danach
    aus `avgClvBf` nach. Das Urteil beschrieb einen Stand, den die Zeile nicht mehr hatte.
    Zweiter Fall am selben Tag: der „ruht"-Zweig von `bewerte()` baute seine Zeile selbst und
    liess `clvOg`/`clvUrteil` ganz weg — „WM · ABWAEGEN … CLV −2,2 pp" stand ohne jedes Urteil
    auf dem Board, obwohl die Obergrenze (−1,7 pp) unter null liegt, also GEGEN die Schublade.

    Der Guard prueft die Aussage, nicht den Code: das Wort auf der Zeile und die Zahl daneben
    muessen dasselbe sagen. Die Regel dazu steht einmal in `freigabe.clv_urteil`.
    """
    f = ctx.get("freigabe") or {}
    zeilen = [z for z in (f.get("alle") or []) if isinstance(z, dict)]
    if not zeilen:
        return _c("CLV-Urteil passt zur CLV-Zahl", "warn", [], "kein freigabe.json geladen")
    fails = []
    ohne = [z for z in zeilen if "clvUrteil" not in z]
    if ohne:
        fails.append(f"{len(ohne)} Zeilen ohne `clvUrteil` — eine Leerstelle sieht auf dem Board "
                     f"aus wie \u201ekein CLV\u201c, ist aber keine Auskunft (z. B. "
                     f"{ohne[0].get('schublade')}, CLV {ohne[0].get('clv')})")
    stumm = [z for z in zeilen
             if z.get("clv") is not None and z.get("clvUrteil") == "nicht erhoben"]
    if stumm:
        schlimm = max(stumm, key=lambda z: abs(z.get("clv") or 0))
        fails.append(f"{len(stumm)} Zeilen sagen \u201ekein CLV erhoben\u201c und tragen eine CLV-Zahl "
                     f"(schlimmster Fall: {schlimm.get('schublade')} {schlimm.get('clv'):+.2f} pp, "
                     f"n{schlimm.get('n')}) — Fund vom 15.09.")
    leer = [z for z in zeilen
            if z.get("clv") is None and z.get("clvUrteil") not in (None, "nicht erhoben")]
    if leer:
        fails.append(f"{len(leer)} Zeilen ohne CLV-Zahl tragen trotzdem ein CLV-Urteil "
                     f"(z. B. {leer[0].get('schublade')}: \u201e{leer[0].get('clvUrteil')}\u201c)")
    # Die Gegenrichtung des zweiten Falls: ein Urteil „gemessen, nicht belegt" behauptet, dass
    # WEDER Unter- noch Obergrenze die Null ausschliesst. Ohne berechnete Obergrenze ist das
    # eine Behauptung ueber eine Zahl, die es nicht gibt.
    halb = [z for z in zeilen
            if z.get("clvUrteil") == "gemessen, nicht belegt" and "clvOg" not in z]
    if halb:
        fails.append(f"{len(halb)} Zeilen mit \u201eCLV offen\u201c, aber ohne Feld `clvOg` — das Urteil "
                     f"redet ueber eine Obergrenze, die nie gerechnet wurde "
                     f"(z. B. {halb[0].get('schublade')})")
    return _c("CLV-Urteil passt zur CLV-Zahl", "error", fails)


DECKEL_ENG_PCT = 75.0     # ab hier ist der Deckel keine Reserve mehr


def _timeout_minuten(workflow_text: str):
    """Der Job-Deckel in Minuten. REIN. None = keiner gesetzt (dann gilt GitHubs 360)."""
    import re
    m = re.search(r"^\s*timeout-minutes:\s*([0-9]+)", workflow_text or "", re.M)
    return float(m.group(1)) if m else None


def _laufzeiten_s(health: dict):
    """Die gemessenen Laufzeiten aus einem Gesundheits-Protokoll. REIN. -> [Sekunden]"""
    raus = []
    for r in (health or {}).get("runs") or []:
        v = r.get("laeuftSeitS") if isinstance(r, dict) else None
        if isinstance(v, (int, float)) and v > 0:
            raus.append(float(v))
    return raus


def deckel_auslastung(health: dict, timeout_min):
    """Wie viel seines Deckels braucht der Lauf. REIN. -> (pct, median_s, max_s) oder None.

    `laeuftSeitS` misst vom Job-Start bis zum vorletzten Schritt — der Rest ist der
    End-Commit. Als Auslastung wird der LAENGSTE beobachtete Lauf gerechnet, nicht der
    mittlere: ein Deckel muss den schlechten Tag aushalten, nicht den guten.
    """
    if not timeout_min:
        return None
    xs = _laufzeiten_s(health)
    if len(xs) < 3:
        return None
    xs_s = sorted(xs)
    med = xs_s[len(xs_s) // 2]
    mx = xs_s[-1]
    return (100.0 * mx / (timeout_min * 60.0), med, mx)


def check_der_deckel_hat_luft(ctx):
    """🔴 23.09.2026 (Lucas: „betfair action hat scheinbar abgebrochen").

    Der Lauf um 13:00 UTC endete mit „The operation was canceled" — im Schritt `ci_sichern.sh`,
    nach dem Commit des Belegs und vor dessen Push. Der Beleg lag nur lokal auf dem Runner und
    war mit dem naechsten `actions/checkout` weg. Die Alarme waren da schon raus; fuer den
    naechsten Lauf gelten sie als nie gesendet.

    Aus den Commit-Zeiten von zwoelf Laeufen desselben Tages: Median 6,3 Minuten bei einem
    Deckel von 8. Anderthalb Minuten Luft — und genau die verbraucht der Beleg-Push, wenn er
    sich den Branch teilen muss. Der Deckel schnitt also bevorzugt an der teuersten Stelle.

    Fehlerklasse: *ein Deckel, den der Lauf regelmaessig streift, ist kein Deckel, sondern ein
    Wuerfel.* Und weil ein abgebrochener Lauf keinen Gesundheits-Eintrag mehr schreibt, sieht
    man ihn hinterher nirgends — man sieht nur, dass etwas fehlt.

    Deshalb misst jeder Lauf ab jetzt selbst mit (`laeuftSeitS`), und diese Zahl wird gegen den
    Deckel gehalten, BEVOR der naechste Abbruch kommt.
    """
    import re
    basis = BASE
    wf_dir = basis / ".github" / "workflows"
    h_dir = basis / "health"
    if not wf_dir.is_dir() or not h_dir.is_dir():
        return _c("Der Deckel hat Luft", "warn", [], "keine Workflows/Protokolle gefunden")
    slug2wf = {}
    for f in sorted(wf_dir.glob("*.y*ml")):
        t = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"--slug\s+([a-z0-9\-]+)", t):
            slug2wf[m.group(1)] = (f.name, t)
    fails = []
    geprueft = 0
    for f in sorted(h_dir.glob("*.json")):
        wf = slug2wf.get(f.stem)
        if not wf:
            continue
        try:
            health = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        deckel = _timeout_minuten(wf[1])
        u = deckel_auslastung(health, deckel)
        if not u:
            continue
        geprueft += 1
        pct, med, mx = u
        if pct >= DECKEL_ENG_PCT:
            fails.append("%s: laengster Lauf %.1f Min (Median %.1f) bei einem Deckel von "
                         "%.0f Min — %.0f %% ausgelastet. Ein Abbruch trifft den letzten "
                         "Schritt, und das ist der, der die Belege sichert."
                         % (wf[0], mx / 60.0, med / 60.0, deckel, pct))
    return _c("Der Deckel hat Luft", "warn", fails,
              "" if geprueft else "noch keine Laufzeiten im Protokoll (laeuftSeitS)")


def check_takt_stimmt_mit_dem_cron(ctx):
    """🔴 17.09.2026 (Lucas: „der Betfair-Cron sollte alle 10 min, tut er aber nicht, weil damals
    irgendwas nicht ging — in Wahrheit rennt er alle 15 min, falls das irgendwo wichtig ist").

    Es war an vier Stellen wichtig, und keine davon hat es gemerkt:
      · `test_cron_schedule_hygiene` rechnete betfair.yml mit 144 Laeufen/Tag gegen einen Deckel
        von 540 — geliefert hat er 96. 48 Slots waren auf dem Papier belegt und in Wahrheit frei.
      · `stake_burst_push.MAX_ALTER_MIN` (30 Min) war mit „der Runner laeuft alle 10 Minuten"
        begruendet — der Puffer ist in Wahrheit zwei Laeufe, nicht drei.
      · `betfair_track_store` und `betfair_track_record` rechneten Commit-Groessen „alle 10 Min".
      · `reconcile_poly_positions` begruendete seine 60-Minuten-Schranke mit einem 15-Minuten-Takt,
        laeuft aber selbst alle 30 Minuten und nur zwischen 10 und 21 Uhr.

    Ein behaupteter Takt, den niemand misst, wandert durch das ganze Repo. Der echte steht in
    `health/<slug>.json`: jeder Lauf traegt sich dort ein.

    ⚠️ Die gemessene Kadenz ist eine OBERGRENZE der Haeufigkeit, keine Zaehlung: der
    Gesundheits-Eintrag wird am Ende des Laufs committet, und ein gescheiterter Push verliert ihn.
    Deshalb `warn` und nicht `error` — und deshalb steht der Vorbehalt in der Meldung.
    """
    import re
    fails = []
    basis = BASE
    wf_dir = basis / ".github" / "workflows"
    if not wf_dir.is_dir():
        return _c("Takt: Cron gegen gemessene Laeufe", "warn", [], "keine Workflows gefunden")
    slug2wf = {}
    for f in sorted(wf_dir.glob("*.y*ml")):
        t = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"--slug\s+([a-z0-9\-]+)", t):
            slug2wf[m.group(1)] = (f.name, t)
    for f in sorted((basis / "health").glob("*.json")) if (basis / "health").is_dir() else []:
        slug = f.stem
        wf = slug2wf.get(slug)
        if not wf:
            continue
        crons = re.findall(r"^\s*-\s*cron:\s*['\"]([^'\"]+)['\"]", wf[1], re.M)
        # 20.09.2026: Fenster-Crons werden nicht mehr uebersprungen, sondern IM Fenster
        # gemessen — siehe `_cron_stunden`. Nur Tages-/Wochen-Felder bleiben draussen.
        gewaehlt = _dichtester_cron(_messbare_crons(crons))
        if not gewaehlt:
            continue
        soll, stunden = gewaehlt
        ist = _health_abstand(f, stunden if len(stunden) < 24 else None)
        if soll is None or ist is None:
            continue
        if ist > soll * 1.4:
            fenster = _schliessfenster_min(wf[1])
            zusatz = ""
            if fenster and ist > fenster:
                zusatz = (" Dieser Workflow hat ein %.0f-Minuten-Fenster zu treffen — bei einem "
                          "gemessenen Abstand von %.0f Min kann er es nicht sicher treffen."
                          % (fenster, ist))
            fails.append("%s: Cron sagt alle %.0f Min, gemessen alle %.0f Min (%s%s) — die "
                         "Schedule-Bilanz rechnet mit %.0f Laeufen/Tag, geliefert werden eher %.0f.%s "
                         "Gesundheits-Eintraege koennen bei gescheitertem Push fehlen, die Zahl ist "
                         "also eine Obergrenze der Haeufigkeit."
                         % (wf[0], soll, ist, slug,
                            ", im Zeitfenster gemessen" if len(stunden) < 24 else "",
                            # Bei einem Fenster-Cron ist der Tagessoll nicht 1440/Abstand,
                            # sondern nur das Fenster: sonst steht neben einer im Fenster
                            # gemessenen Zahl ein Soll fuer den ganzen Tag.
                            len(stunden) * 60.0 / soll, len(stunden) * 60.0 / ist, zusatz))
    return _c("Takt: Cron gegen gemessene Laeufe", "warn", fails)


def _schliessfenster_min(workflow_text: str):
    """Das im Workflow deklarierte Zeitfenster in Minuten (RUN_HEALTH_FENSTER_MIN). REIN.

    Es steht dort, weil nur der Workflow es kennt — und es steht ueberhaupt dort, damit „alle
    30 Min, damit garantiert ein Lauf ins Fenster faellt" eine pruefbare Zusage wird statt
    eines Kommentars.
    """
    import re
    m = re.search(r"RUN_HEALTH_FENSTER_MIN:\s*['\"]?([0-9.]+)", workflow_text or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _cron_minuten(cron: str):
    """Abstand zweier Laeufe in Minuten fuer einen einfachen Minuten-Cron. REIN."""
    import re
    teil = str(cron).split()
    if len(teil) != 5:
        return None
    m = teil[0]
    if m.startswith("*/"):
        try:
            return float(m[2:])
        except ValueError:
            return None
    if re.match(r"^\d+(,\d+)*$", m):
        werte = sorted(int(x) for x in m.split(","))
        if len(werte) == 1:
            return 60.0
        # gleichmaessig verteilt? Dann ist der Abstand aussagekraeftig, sonst nicht.
        d = {werte[i + 1] - werte[i] for i in range(len(werte) - 1)}
        d.add(60 - werte[-1] + werte[0])
        return float(next(iter(d))) if len(d) == 1 else None
    return None


def _cron_stunden(cron: str):
    """Die aktiven Stunden eines Crons als Menge. REIN. None = nicht deutbar.

    🔴 20.09.2026. Der Guard darueber sprang bisher nur bei Crons an, die rund um die Uhr
    laufen (`^\S+ \* \* \* \*`) — mit gutem Grund: bei „0,30 10-21" ist die Luecke ueber
    Nacht 13 Stunden, und daraus einen Ausfall zu lesen waere genau der Fehler, den er fangen
    soll. Die Folge war aber, dass er die Workflows mit der SCHAERFSTEN Zeitanforderung gar
    nicht ansah: `manage-liga-poly` (0,30 10-21) hat ein 40-Minuten-Schliessfenster und liefert
    5,0 statt 25 Laeufe am Tag — bei 0 von 7 Positionen lag je ein Lauf im Fenster.

    Fehlerklasse: ein Waechter, der die Faelle ueberspringt, fuer die er gebaut wurde.

    Der Ausweg ist nicht, die Nachtluecke mitzuzaehlen, sondern nur INNERHALB des Fensters zu
    messen.
    """
    import re
    teil = str(cron).split()
    if len(teil) != 5:
        return None
    h = teil[1]
    if h == "*":
        return set(range(24))
    if h.startswith("*/"):
        try:
            n = int(h[2:])
        except ValueError:
            return None
        return set(range(0, 24, n)) if n else None
    raus = set()
    for stueck in h.split(","):
        m = re.match(r"^(\d{1,2})-(\d{1,2})$", stueck)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if not (0 <= a <= 23 and 0 <= b <= 23):
                return None
            raus |= set(range(a, b + 1)) if a <= b else (set(range(a, 24)) | set(range(0, b + 1)))
        elif re.match(r"^\d{1,2}$", stueck):
            if int(stueck) > 23:
                return None
            raus.add(int(stueck))
        else:
            return None
    return raus or None


def _messbare_crons(crons):
    """Welche Crons dieser Guard ueberhaupt messen kann. REIN.

    Minute und Stunde duerfen alles Deutbare sein — Tag, Monat und Wochentag muessen `*` sein.
    Ein Wochen- oder Monats-Cron laesst sich aus 20 Laeufen nicht beurteilen.

    Bis zum 20.09.2026 verlangte der Aufrufer hier zusaetzlich ein `*` in der STUNDE und genau
    EINEN Cron. Damit fielen alle Workflows mit Arbeitsfenster heraus — und das sind die, deren
    Taktung ueberhaupt etwas zusagt.
    """
    import re
    return [c for c in (crons or []) if re.match(r"^\S+\s+\S+\s+\*\s+\*\s+\*$", str(c))]


def _dichtester_cron(crons):
    """Von mehreren Crons der haeufigste — der, dessen Takt die Zusagen traegt. REIN.

    Ein Housekeeping-Cron („0 8 * * *") neben dem Arbeits-Cron darf nicht dazu fuehren, dass
    gar nicht geprueft wird; er wird hier schlicht nicht zum Massstab.
    """
    bester = None
    for c in crons or []:
        ab = _cron_minuten(c)
        st = _cron_stunden(c)
        if ab is None or not st:
            continue
        if bester is None or ab < bester[0]:
            bester = (ab, st)
    return bester


def _health_abstand(pfad, stunden=None):
    """Das 25-%-Quantil der Laufabstaende aus einer Gesundheitsdatei. REIN(-genug: liest eine
    Datei). Das Quantil statt des Mittels, damit einzelne Ausfaelle den Wert nicht tragen."""
    try:
        d = json.loads(pfad.read_text(encoding="utf-8"))
    except Exception:
        return None
    ts = sorted(str(r.get("ts")) for r in (d.get("runs") or []) if r.get("ts"))
    if len(ts) < 8:
        return None
    try:
        punkte = [datetime.fromisoformat(x.replace("Z", "+00:00")) for x in ts]
    except ValueError:
        return None
    roh = []
    for i in range(len(punkte) - 1):
        a, b = punkte[i], punkte[i + 1]
        if stunden is not None:
            # Beide Enden im Fenster UND am selben Tag — sonst misst man die Nacht.
            if a.hour not in stunden or b.hour not in stunden or a.date() != b.date():
                continue
        roh.append((b - a).total_seconds() / 60.0)
    if len(roh) < 4:
        return None
    ab = sorted(roh)
    return ab[len(ab) // 4]


def check_geschlossen_heisst_belegt(ctx):
    """18.09.2026 (Lucas: „Schalke–Elversberg ist aber noch offen, Brentford–Chelsea auch").

    Zwei Wetten standen als `closed_manual` im Buch, beide mit `sellPrice: null`, `pnl: null`,
    `pnlSource: "manual_unknown"` — und beide mit einem Anpfiff, der noch bevorstand. Das ist
    keine Schliessung, das ist eine Behauptung: die Positions-API hatte den Token in einem Lauf
    nicht geliefert, und daraus wurde eine Zustandsaenderung.

    Der Schaden hat eine Rechnung: eine so fehlgebuchte Zeile ist fuer den Verkaufs-Manager
    unsichtbar (er sieht nur `status == "placed"`). Seattle Sounders–Austin lief am 20.08. genau
    so ins Spiel und verlor den vollen Einsatz. Brentford–Chelsea stand drei Tage und acht
    Laeufe lang falsch da, Anpfiff 18.09.

    Der Guard prueft den Zustand der Flaeche, nicht den Code drumherum: eine geschlossene Wette
    ohne jeden Verkaufs-Beleg, deren Spiel noch nicht angepfiffen ist, gibt es nicht.
    """
    fails = []
    for name, key in (("liga_auto_bets_placed.json", "autoBetsLiga"),
                      ("mls_auto_bets_placed.json", "autoBetsMls")):
        d = (ctx.get(key) or {})
        for b in (d.get("bets") or []):
            if not isinstance(b, dict) or b.get("status") != "closed_manual":
                continue
            if b.get("sellPrice") is not None or b.get("pnl") is not None:
                continue
            ko = b.get("kickoff")
            if not ko:
                continue
            try:
                k = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if k.tzinfo is None:
                k = k.replace(tzinfo=timezone.utc)
            if k <= datetime.now(timezone.utc):
                continue
            fails.append("%s: %s–%s %s als 'manuell geschlossen' gebucht, aber ohne Verkaufs-Beleg "
                         "(sellPrice/pnl leer) und Anpfiff erst %s — fuer den Verkaufs-Manager "
                         "unsichtbar" % (name, b.get("home"), b.get("away"), b.get("market"),
                                         str(ko)[:16]))
    return _c("geschlossen heisst belegt", "error", fails)


def check_positionswert_ist_frisch(ctx):
    """18.09.2026 — `liga_poly_balance.json` meldete $10,12 an Positionen ueber fuenf Laeufe und
    zwei Tage, danach $9,28 ueber vier weitere, waehrend die Kurse liefen. Der Positions-Fetch
    faellt bei einem API-Fehler auf den alten Wert zurueck (richtig — auf null zu fallen waere
    schlimmer), aber die Datei trug nur `updatedAt`, und das ist der Zeitpunkt des SCHREIBENS.

    Ich selbst bin am 16.09. darauf hereingefallen und habe aus diesem eingefrorenen Wert
    geschlossen, die Wallet halte Brentford–Chelsea noch. Fehlende Information rendert als
    harmloser Default; hier als eine Zahl, die aussieht wie gemessen.
    """
    fails = []
    jetzt = datetime.now(timezone.utc)
    for name, key in (("liga_poly_balance.json", "balanceLiga"),
                      ("mls_poly_balance.json", "balanceMls")):
        d = (ctx.get(key) or {})
        if not d:
            continue
        stand = d.get("positionsStand")
        if stand is None:
            fails.append("%s: kein `positionsStand` — dann sagt die Datei nicht, wann der "
                         "Positionswert zuletzt wirklich gemessen wurde" % name)
            continue
        try:
            t = datetime.fromisoformat(str(stand).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            fails.append("%s: `positionsStand` unlesbar (%r)" % (name, stand))
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        alter_h = (jetzt - t).total_seconds() / 3600.0
        if alter_h > 12:
            # 🔴 21.09.2026. Hier stand pauschal „die Positions-API antwortet seither nicht".
            # Nachgemessen am echten Fall: `liga_poly_balance.json` war 15,5 h alt, weil
            # `manage-liga-poly` von 25 geplanten Laeufen rund 5 liefert — die Datei wurde gar
            # nicht geschrieben. Die API hatte damit nichts zu tun.
            # Die Unterscheidung steht in der Datei selbst und war nur nie gelesen worden:
            #   `positionsStand` ~ `updatedAt`  -> der Produzent lief nicht
            #   `positionsStand` < `updatedAt`  -> er lief, die API antwortete nicht
            # Fehlerklasse: ein Befund, der seine eigene Unterscheidung nicht trifft, obwohl
            # die Zahl daneben steht. (Zweites Mal an diesem Tag — der Anker-Waechter hatte
            # dieselbe Krankheit.)
            warum = "Grund nicht bestimmbar (`updatedAt` fehlt oder ist unlesbar)"
            geschrieben = _zeit(d.get("updatedAt"))
            if geschrieben is not None:
                verzug_min = (geschrieben - t).total_seconds() / 60.0
                if verzug_min > 5:
                    warum = ("die Datei wurde vor %.0f h geschrieben, der Positionswert aber "
                             "%.0f Min frueher gemessen — die Positions-API antwortet nicht, "
                             "der Wert wird mitgeschleppt"
                             % ((jetzt - geschrieben).total_seconds() / 3600.0, verzug_min))
                else:
                    warum = ("die Datei selbst ist %.0f h alt — der Produzent laeuft nicht, "
                             "das ist kein API-Problem"
                             % ((jetzt - geschrieben).total_seconds() / 3600.0))
            fails.append("%s: Positionswert $%.2f stammt aus einem Lauf vor %.0f h — %s"
                         % (name, d.get("positions") or 0.0, alter_h, warum))
    return _c("Positionswert ist frisch", "warn", fails)


def _zeit(wert):
    """ISO-Zeitstempel -> aware datetime, oder None. REIN."""
    try:
        t = datetime.fromisoformat(str(wert).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def check_public_stille_ist_erklaert(ctx):
    """19.09.2026 (Lucas: „Gestern kam kein einziger Betfair-Push in Public. Was komisch ist.").

    Es war nicht komisch: der Nachbau des 18.09. aus 40 Preis-Staenden zeigt 39 Alarme am
    Leader-Gate, von denen nur 8 die 80-%-Einseitigkeit schafften (17.09.: 22 von 34), und die
    letzten vier starben an `drift` und `under_tore`. Der Trades-Kanal lief normal weiter — 20
    neue Alarme, so viele wie am 16.09. Ein Tag ohne einseitiges Geld, kein Ausfall.

    Das Problem ist die Ununterscheidbarkeit: ein stummer Kanal sieht gleich aus, ob er nichts
    zu sagen hat oder kaputt ist. Diese Woche war er beides — der Poly-Public-Kanal schwieg drei
    Tage, und DAS war ein Defekt (eine Rangliste, die ich selbst umgestellt hatte).

    EIN stiller Tag ist deshalb kein Befund. Mehrere hintereinander, waehrend oben Alarme
    ankommen, sind einer. Der Guard nennt dann auch gleich die Stufe, an der sie haengen bleiben
    — sonst beginnt die Suche wieder bei null.
    """
    t = ctx.get("bfTrichter") or {}
    if not isinstance(t, dict) or not t:
        return _c("Public-Stille ist erklaert", "warn", [])
    tage = sorted(t)[:-1]          # der laufende Tag zaehlt nicht mit, er ist noch nicht vorbei
    strecke, gruende = [], {}
    for tag in reversed(tage):
        e = t.get(tag) or {}
        if not isinstance(e, dict) or not e.get("roh"):
            break
        if e.get("gesendet"):
            break
        strecke.append(tag)
        for k, v in (e.get("gruende") or {}).items():
            gruende[k] = gruende.get(k, 0) + int(v or 0)
    if len(strecke) < 2:
        return _c("Public-Stille ist erklaert", "warn", [])
    top = sorted(gruende.items(), key=lambda kv: -kv[1])[:3]
    return _c("Public-Stille ist erklaert", "warn", [
        "Betfair-Public schweigt seit %d Tagen (%s), obwohl Alarme ankamen — sie bleiben haengen "
        "an: %s" % (len(strecke), strecke[-1],
                    ", ".join("%s (%d)" % (k, v) for k, v in top) or "unbekannt")])


def check_jeder_push_hat_seinen_beleg(ctx):
    """🔴 20.09.2026 (Lucas: „Beide Spiele stehen nicht in der Betfair-Public-Bilanz. Beide
    haben gewonnen.").

    Eines davon — Lyon v Rennes — WAR gesendet: der Dedup-Stand trug `fresh:36039873`, und den
    bekommt ein Spiel nur bei erfolgreichem Versand. Eine Ledger-Zeile hat es nie gegeben, in
    keinem der letzten 40 Commits. Ueber alle Eintraege geprueft: 4 von 277 gesendeten
    Public-Pushes haben keine Zeile (1,4 %).

    Nachtragen geht nicht — von einem verlorenen Push steht die Quote beim Senden nirgends, und
    ausgerechnet die eine zurueckzuholen, die jemandem aufgefallen ist (weil sie gewonnen hat),
    waere eine Auswahl nach Ausgang. Also bleibt die Luecke und wird stattdessen gezaehlt: eine
    Bilanz, die ihre eigene Unvollstaendigkeit nennt, ist ehrlicher als eine, die sie
    verschweigt. Waechst die Zahl weiter, ist der Sicherungsschritt in betfair.yml wirkungslos
    und das gehoert gesehen.
    """
    r = ctx.get("bfPublicRecord")
    if not isinstance(r, dict) or "gesendetOhneBeleg" not in r:
        return _c("Jeder Push hat seinen Beleg", "warn", [])
    n = int(r.get("gesendetOhneBeleg") or 0)
    if not n:
        return _c("Jeder Push hat seinen Beleg", "warn", [])
    # 🔴 20.09.2026, zweiter Teil: die Ursache ist behoben (der Beleg wird jetzt sofort nach dem
    # Senden committet). Ob die Reparatur HAELT, stand aber in derselben Zahl wie die alte Narbe —
    # 4 wuerde bei einem fuenften Verlust zu 5, und das sieht in einer Warn-Zeile niemand.
    # Fehlerklasse: eine Narbe und eine frische Wunde in derselben Zahl.
    # Der Dedup-Stand stempelt seit dem 20.09. die Sendezeit; jeder DATIERTE Verlust ist also
    # einer von NACH der Reparatur. Kein gepflegter Ausnahmen-Katalog noetig.
    neu = int(r.get("gesendetOhneBelegNeu") or 0)
    alt = max(0, n - neu)
    fails = []
    if neu:
        nk = ", ".join("%s (%s)" % (z.get("key"), str(z.get("t"))[:16])
                       for z in (r.get("gesendetOhneBelegNeuKeys") or [])[:4])
        fails.append("%d Public-Push(es) SEIT der letzten Reparatur (%s) ohne Ledger-Zeile (%s) — "
                     "der Beleg-Pfad leckt weiter"
                     % (neu, str(r.get("belegReparaturAb") or "?")[:16], nk or "—"))
    if alt:
        # 23.09.2026: hier stand `gesendetOhneBelegKeys` — ALLE Schluessel, auch die frischen.
        # Die Zeile sagte „4 aeltere" und druckte fuenf darunter. Fehlerklasse: eine Beschriftung,
        # die etwas anderes verspricht als die Liste daneben.
        keys = ", ".join(r.get("gesendetOhneBelegAltKeys")
                         or r.get("gesendetOhneBelegKeys") or [])[:120]
        fails.append("%d aeltere(r) Push(es) ohne Ledger-Zeile aus der Zeit vor der Sofort-"
                     "Sicherung (%s) — nicht nachtragbar: von einem verlorenen Push steht die "
                     "Quote beim Senden nirgends, und nur die aufgefallenen zurueckzuholen waere "
                     "eine Auswahl nach Ausgang. Die Bilanz nennt ihre Luecke stattdessen."
                     % (alt, keys or "—"))
    return _c("Jeder Push hat seinen Beleg", "warn", fails)


def check_artefakte_sind_lesbar(ctx):
    """🔴 19.09.2026 (Lucas: „Heut kein einziger polymarket Push in public (kann nicht sein)").

    Konnte sehr wohl sein. Der Lauf „🐋 Poly Global-Scan 18:05 UTC" hatte 15 Poly-Artefakte MIT
    Git-Konfliktmarkern committet — `<<<<<<< Updated upstream`, die Sprache von `git stash pop`,
    also vom `--autostash` im Push-Retry. poly_wallet_track.json (13 Konflikte),
    poly_money_broad_close.json (30), poly_money_upcoming.json (621) und zwoelf weitere waren
    damit kein JSON mehr.

    Und JEDER Leser im Repo hat dieselbe Zeile: `except Exception: return default`. Aus der
    zerschossenen Datei wurde ein leeres Dict, select() fand null Kandidaten, der Kanal schwieg.
    Kein Absturz, kein roter Lauf, keine Zeile im Log — drei Stunden lang, und aufgefallen ist es
    einem Menschen, nicht der Maschine.

    Dieser Guard ist die Maschine, die es beim naechsten Mal merkt. Er urteilt NICHT ueber den
    Inhalt, nur darueber, ob die Datei ueberhaupt gelesen werden konnte — das ist die Frage, die
    vor allen anderen kommt.
    """
    if not UNLESBAR:
        return _c("Artefakte sind lesbar", "error", [])
    return _c("Artefakte sind lesbar", "error",
              ["%s ist DA, aber nicht lesbar (%s) — jeder Leser bekommt dafuer still einen "
               "leeren Default und tut dann nichts" % (name, grund)
               for name, grund in UNLESBAR])


def check_schattenbuch_fuellt_sich(ctx):
    """19.09.2026 (Lucas: „ich glaube, wir haben einfach noch nicht die optimale Einstellung …
    da muessten wir rumtuefteln und das dann rueckrechnen").

    Rueckrechnen ging nicht, weil wir nur sehen, was durchkommt: Trichter vom 19.09. — roh 69,
    gesendet 3, davon 43 gestorben an der 80-%-Einseitigkeit. Wie diese 43 ausgegangen waeren,
    stand nirgends. Seit heute schreibt betfair_alerts sie ins Schattenbuch und
    betfair_public_eval rechnet sie mit derselben Kette ab wie echte Pushes.

    Der Guard passt auf die stille Variante des Scheiterns: eine Datei, die da ist, aber nicht
    mehr waechst oder nie abgerechnet wird. Die faellt niemandem auf — bis in drei Monaten
    jemand die Schwellen-Frage stellt und wieder nichts dasteht. Ein Guard ohne Vorfall waere
    eine Meinung; dieser hat seinen Vorfall in genau der Luecke, die er offenhalten soll.
    """
    b = ctx.get("bfSchatten")
    if not isinstance(b, list) or not b:
        return _c("Schattenbuch fuellt sich", "warn",
                  ["betfair_public_schatten.json ist leer oder fehlt — die Unterseite der "
                   "Schwellen wird nicht mitgeschrieben"])
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    jetzt = _dt.now(_tz.utc)
    def _ts(e):
        try:
            return _dt.fromisoformat(str(e.get("sentAt")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    zeiten = [t for t in (_ts(e) for e in b if isinstance(e, dict)) if t]
    fehler = []
    if not zeiten:
        fehler.append("keine Zeile im Schattenbuch traegt einen lesbaren Zeitstempel")
    elif max(zeiten) < jetzt - _td(hours=48):
        fehler.append("juengste Zeile im Schattenbuch ist %s alt — es waechst nicht mehr"
                      % _alter_kurz(jetzt - max(zeiten)))
    offen = sum(1 for e in b if isinstance(e, dict) and e.get("status") == "pending")
    fertig = sum(1 for e in b if isinstance(e, dict) and e.get("status") in ("won", "lost"))
    if zeiten and min(zeiten) < jetzt - _td(days=4) and not fertig:
        fehler.append("%d Zeilen im Schattenbuch, die aelteste seit %s — aber KEINE abgerechnet; "
                      "ein Buch ohne Ausgang beantwortet keine Schwellenfrage"
                      % (len(b), _alter_kurz(jetzt - min(zeiten))))
    if fehler:
        return _c("Schattenbuch fuellt sich", "warn", fehler)
    return _c("Schattenbuch fuellt sich", "warn", [],
              hinweis="%d Zeilen · %d abgerechnet · %d offen" % (len(b), fertig, offen))


def check_offene_wette_hat_den_anpfiff_ueberlebt(ctx):
    """19.09.2026 (Lucas: „es wurde vorm spielstart nicht geschlossen und ist nun lost").

    Toulouse–Le Havre, `Under 2.5 Tore`, 5,50 $. Anpfiff 18:45 UTC. Der Positions-Manager
    lief um 17:06 UTC — mitten im eigenen 2-h-Hard-Close-Fenster — und schrieb in genau
    diesem Lauf `valuedAt`, hat die Position also gesehen. Verkauft wurde nicht, und ins
    Buch kam nichts: `status: "placed"`, kein `sellError`, kein Versuch. Eine Wirkung, die
    ausbleibt, hinterlaesst keine Spur; danach sieht der Schaden aus wie jede andere offene
    Wette.

    Dieser Guard prueft den Zustand der Flaeche, nicht den Code: eine Wette, die als offen
    im Buch steht, obwohl ihr Spiel laengst angepfiffen hat, gibt es nicht. Entweder sie
    wurde verkauft (dann `sold`), oder sie ist abgerechnet (`won`/`lost`), oder jemand hat
    von Hand geschlossen (`closed_manual`). `placed` nach Anpfiff heisst: der Exit ist
    ausgefallen und niemand hat es gemerkt.

    Das Gegenstueck zu `check_geschlossen_heisst_belegt` (18.09.), das die andere Richtung
    faengt — geschlossen behauptet, ohne Beleg. Zusammen decken sie beide Seiten desselben
    Buchs ab.

    Die rechtzeitige Warnung ist NICHT Aufgabe dieses Guards: er laeuft in update-liga.yml
    (3x taeglich). Dafuer gibt es `poly_offene_wache.py` im 15-Minuten-Takt von betfair.yml.
    Hier steht der Nachweis, dass es passiert ist.
    """
    fails = []
    jetzt = datetime.now(timezone.utc)
    for name, key in (("liga_auto_bets_placed.json", "autoBetsLiga"),
                      ("mls_auto_bets_placed.json", "autoBetsMls")):
        for b in ((ctx.get(key) or {}).get("bets") or []):
            if not isinstance(b, dict) or b.get("status") != "placed":
                continue
            ko = b.get("kickoff")
            if not ko:
                continue
            try:
                k = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if k.tzinfo is None:
                k = k.replace(tzinfo=timezone.utc)
            if k > jetzt:
                continue
            try:
                nv = int(b.get("sellVersuche") or 0)
            except (TypeError, ValueError):
                nv = 0
            beleg = ("%d Verkaufsversuch(e), zuletzt: %s"
                     % (nv, b.get("sellVersuchGrund") or b.get("sellFehler") or "ohne Grund")
                     ) if nv else "kein einziger Verkaufsversuch im Buch"
            fails.append("%s: %s–%s %s steht seit %s offen, Anpfiff war %s — %s"
                         % (name, b.get("home"), b.get("away"), b.get("market"),
                            _alter_kurz(jetzt - k), str(ko)[:16], beleg))
    return _c("offene Wette hat den Anpfiff ueberlebt", "error", fails)


def check_ergebnisse_kommen_an(ctx):
    """19.09.2026 (Lucas: „es ist ins spiel gelaufen und verloren weil 5 tore oder so").

    Toulouse–Le Havre endete mit fuenf Toren, `Under 2.5 Tore` war verloren. Am naechsten
    Mittag stand die Wette immer noch als `placed` im Buch — nicht, weil der Resolver
    versagt haette, sondern weil in liga-data.json `"result": null` steht. Er kann nichts
    abrechnen, wozu kein Ergebnis da ist.

    Ergebnisse schreibt allein `build_liga_data.py` in update-liga.yml, drei Crons am Tag.
    Der letzte erfolgreiche Lauf war am 19.09. um 20:34 UTC, sechs Minuten VOR dem
    Schlusspfiff; die beiden Crons am 20.09. fielen aus (health/liga.json kennt fuer den
    20.09. keinen Lauf). Gemessen am Bestand: 6 von 23 abgepfiffenen Spielen des 19.09.
    ohne Ergebnis, Levante–Athletic vom 16.09. seit vier Tagen.

    Die teure Haelfte der Fehlerklasse ist nicht das fehlende Ergebnis, sondern: eine
    Zeile, die nicht abgerechnet werden kann, faellt aus der Rechnung und nicht negativ
    auf. Das liga-Buch zeigte einen Verlust, tatsaechlich waren es zwei. Ein Buch, das nur
    die Spiele bucht, deren Ergebnis rechtzeitig ankommt, wird systematisch zu gut.

    Der Guard liest die Zahl beim Produzenten (`fetch_liga_ergebnisse.py` schreibt sie in
    seinen Bericht), statt sie aus den 4,7 MB von liga-data.json nachzubauen.
    """
    fails = []
    jetzt = datetime.now(timezone.utc)
    for name, key in (("liga_ergebnis_nachlauf.json", "ergebnisNachlaufLiga"),
                      ("mls_ergebnis_nachlauf.json", "ergebnisNachlaufMls")):
        b = ctx.get(key) or {}
        if not b:
            continue   # kein Bericht = der Nachlauf lief hier nie; das sagt dieser Guard nicht
        gen = b.get("generatedAt")
        try:
            t = datetime.fromisoformat(str(gen).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            fails.append("%s: `generatedAt` unlesbar (%r) — dann sagt der Bericht nicht, "
                         "wann zuletzt nachgesehen wurde" % (name, gen))
            continue
        if jetzt - t > timedelta(hours=12):
            fails.append("%s: juengster Nachlauf ist %s alt — es sieht niemand mehr nach"
                         % (name, _alter_kurz(jetzt - t)))
            continue
        offen = [z for z in (b.get("offen") or []) if isinstance(z, dict)]
        # Ein frisch angepfiffenes Spiel darf kurz fehlen: die API braucht ihre Zeit.
        reif = [z for z in offen if (z.get("stundenHer") or 0) >= 6]
        if reif:
            # 🔴 20.09.2026: hier stand „abgepfiffene Spiele". Levante–Athletic wurde 95 Stunden
            # lang so gemeldet — und war nie angepfiffen worden, sondern eine halbe Stunde vor
            # Beginn wegen Starkregen abgesagt. Wir kennen den geplanten Anpfiff, nicht das
            # Ereignis; der Satz behauptete mehr, als die Zahl hergibt.
            # Fehlerklasse: ein Anpfiff, der nur im Kalender stattgefunden hat.
            fails.append("%s: %d Spiele mit vergangenem Anpfiff ohne Ergebnis (%s) — der "
                         "Resolver kann sie nicht abrechnen, sie fallen aus jeder Bilanz heraus"
                         % (name, len(reif),
                            "; ".join("%s seit %.0f h%s"
                                      % (z.get("paarung"), z.get("stundenHer") or 0,
                                         ", %s" % z["grund"] if z.get("grund") else "")
                                      for z in reif[:4])))
        # Abgesagte Spiele sind KEINE ausstehenden Ergebnisse. Sie loesen sich nie von selbst,
        # und eine offene Wette darauf braucht eine Entscheidung statt Geduld — deshalb eine
        # eigene Meldung und nicht dieselbe.
        ab = [z for z in (b.get("abgesagt") or []) if isinstance(z, dict)]
        if ab:
            fails.append("%s: %d abgesagtes/verlegtes Spiel (%s) — es kommt an diesem Termin zu "
                         "keinem Ergebnis; offene Wetten darauf brauchen eine Entscheidung"
                         % (name, len(ab),
                            "; ".join("%s (%s)" % (z.get("paarung"), z.get("status"))
                                      for z in ab[:4])))
        if b.get("apiLeer"):
            fails.append("%s: API lieferte fuer %s 0 Fixtures — Quota, Key oder Saison"
                         % (name, ", ".join(map(str, b["apiLeer"]))))
    return _c("Ergebnisse kommen an", "error", fails)


def check_datenbau_ist_nicht_stehengeblieben(ctx):
    """20.09.2026, derselbe Vorfall von der anderen Seite.

    `_meta.dataUpdatedAt` in liga-data.json stand am 20.09. um 08:00 UTC auf dem 19.09.
    12:02 — zwanzig Stunden alt, bei drei geplanten Crons am Tag. Gesehen hat das niemand,
    weil ein veraltetes Artefakt genauso aussieht wie ein aktuelles: die Zahlen darin sind
    ja alle richtig, nur eben von gestern.

    Zwei Ursachen laufen hier zusammen, und beide erzeugen dasselbe Bild:
      · die Crons fallen aus (am 20.09. beide),
      · ein anderer Workflow committet seinen aelteren Stand darueber. Belegt fuer den
        19.09.: update-liga schrieb um 20:43:44 einen frischen Bau (dataUpdatedAt 20:34)
        mit 17 Ergebnissen; 31 Sekunden spaeter stellte der Odds-Refresh mit `-X ours`
        seinen 10 Minuten alten Stand wieder her — dataUpdatedAt zurueck auf 12:02, alle
        17 Ergebnisse weg, null dazugekommen.

    Fehlerklasse: ein Zeitstempel, der rueckwaerts laeuft, ist ein ueberschriebener Lauf —
    und ohne Wecker faellt er nicht auf, weil nichts falsch AUSSIEHT.

    18 h Schwelle, gemessen statt geraten: die Laeufe kommen unregelmaessig (18.09. um
    11:11, 12:41, 20:58; 19.09. um 11:51, 12:09, 20:43), der groesste normale Abstand lag
    bei rund 15 h. Der heutige steht bei 20 h. 18 h liegt ueber dem Ueblichen und unter
    dem Vorfall.
    """
    fails = []
    jetzt = datetime.now(timezone.utc)
    for name, key in (("liga-data.json", "ergebnisNachlaufLiga"),
                      ("mls-data.json", "ergebnisNachlaufMls")):
        b = ctx.get(key) or {}
        stand = b.get("datenbauAt")
        if not b or not stand:
            continue
        try:
            t = datetime.fromisoformat(str(stand).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            fails.append("%s: `_meta.dataUpdatedAt` unlesbar (%r)" % (name, stand))
            continue
        if jetzt - t > timedelta(hours=18):
            fails.append("%s: der Datenbau hat zuletzt vor %s geschrieben — entweder ist der "
                         "Cron ausgefallen oder ein anderer Workflow hat einen aelteren Stand "
                         "darueber committet" % (name, _alter_kurz(jetzt - t)))
    return _c("Datenbau ist nicht stehengeblieben", "error", fails)


def check_serienbuch_zeigt_beide_buecher(ctx):
    """20.09.2026 (Uebersicht-Check). Auf dem Board stand:

        📒 Serien-Buch · Erwartung zu duenn — erfuellt in 75.0 % (65.8..82.4 %),
           aber nur 22 von 72 Zeilen tragen eine vor dem Spiel festgeschriebene Erwartung

    Diese Zahlen sind die des LIGA-Buchs. Daneben steht ein zweites, das MLS-Buch, mit n=64 und
    81,2 % — es kommt auf der Flaeche nicht vor. `_mdStreakBuch` summiert zwar `n` und
    `unaufloesbar` ueber beide Buecher, zeigt dann aber nur `urteil` und `grund` desjenigen mit
    dem groesseren n; die summierte Zahl wird nirgends ausgegeben.

    Heute faellt das nicht auf, weil beide Buecher dasselbe Urteil tragen („Erwartung zu duenn").
    Genau deshalb steht hier ein Waechter und kein Umbau: solange sie uebereinstimmen, ist die
    verkuerzte Anzeige harmlos, und ein Umbau waere eine Loesung ohne Vorfall. Widersprechen sie
    sich, behauptet die Flaeche unter einer Ueberschrift im Singular das Urteil des groesseren
    Buchs und verschweigt das andere — dann ist es einer.

    Fehlerklasse: eine zusammengefasste Ueberschrift ueber einer Zahl, die nur aus einem Teil
    stammt.

    Derselbe Kopf traegt uebrigens auch den Altersstempel: „aelteste Quelle Serien-Buch MLS vor
    23,3 h" im Seitenkopf gegen „Stand vor 14,7 h" am Block. Beide Zahlen sind richtig — 23,5 h
    fuers MLS-Buch, 14,7 h fuers Liga-Buch — aber der Block stempelt sich mit dem juengeren
    seiner beiden Teile und sieht damit 8,8 h frischer aus, als er ist.
    """
    a = (ctx.get("ligaStreakRec") or {}).get("bilanz") or {}
    b = (ctx.get("mlsStreakRec") or {}).get("bilanz") or {}
    if not a or not b:
        return _c("Serien-Buch zeigt beide Buecher", "warn", [])
    fails = []
    ua, ub = a.get("urteil"), b.get("urteil")
    if ua and ub and ua != ub:
        fails.append("Liga-Buch urteilt '%s' (n=%s), MLS-Buch '%s' (n=%s) — die Flaeche zeigt nur "
                     "das groessere und verschweigt das andere unter einer Ueberschrift, die nach "
                     "beiden klingt" % (ua, a.get("n"), ub, b.get("n")))
    # Der Altersstempel: der Block darf sich nicht mit dem juengeren Teil ausweisen.
    ta = _zeitstempel_alter(ctx.get("ligaStreakRec"))
    tb = _zeitstempel_alter(ctx.get("mlsStreakRec"))
    if ta is not None and tb is not None and abs(ta - tb) > 6:
        fails.append("die beiden Serien-Buecher sind %.1f h auseinander (Liga %.1f h, MLS %.1f h) "
                     "— ein gemeinsamer Stempel unterschlaegt den aelteren"
                     % (abs(ta - tb), ta, tb))
    return _c("Serien-Buch zeigt beide Buecher", "warn", fails,
              hinweis="Liga n=%s · MLS n=%s · Urteil beide '%s'" % (a.get("n"), b.get("n"), ua)
              if ua == ub else None)


def _zeitstempel_alter(d):
    """Alter des `updatedAt` in Stunden, oder None. REIN."""
    v = (d or {}).get("updatedAt")
    if not v:
        return None
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0


def _alter_kurz(d):
    st = int(d.total_seconds() // 3600)
    return "%d h" % st if st < 48 else "%d Tagen" % (st // 24)


UEBERSICHT_CHECKS = [
    check_serien_rangfolge,
    check_freigabe_grund,
    check_poly_kachel_ist_keine_kanalbilanz,
    check_stake_kategorien,
    check_betfair_urteil,
    check_quellen_haben_zeitstempel,
    check_serie_seltenheit_nennt_ihren_nenner,
    check_serie_seltenheit_rechnet_mit_der_eigenen_rate,
    check_money_map_meldet_ihre_luecken,
    check_money_map_poly_gehoert_zum_spiel,
    check_poly_markt_gehoert_zur_selben_mannschaft,
    check_buecher_punktestand,
    check_stake_kachel_zeigt_das_gemessene_urteil,
    check_stake_spielklasse,
    check_poly_deckung,
    check_preis_signal_deckung,
    check_stumme_signale,
    check_signal_bilanz,
    check_fade_kontrolle,
    check_clv_urteil_passt_zur_zahl,
    check_takt_stimmt_mit_dem_cron,
    check_der_deckel_hat_luft,
    check_geschlossen_heisst_belegt,
    check_positionswert_ist_frisch,
    check_public_stille_ist_erklaert,
    check_schattenbuch_fuellt_sich,
    check_artefakte_sind_lesbar,
    check_jeder_push_hat_seinen_beleg,
    check_offene_wette_hat_den_anpfiff_ueberlebt,
    check_ergebnisse_kommen_an,
    check_datenbau_ist_nicht_stehengeblieben,
    check_serienbuch_zeigt_beide_buecher,
]


def run_checks(ctx: dict) -> list:
    """REIN: alle Guards gegen einen Artefakt-Kontext. Ein abstuerzender Guard darf die
    Batterie nicht kippen — er meldet sich selbst als Fehler."""
    out = []
    for fn in UEBERSICHT_CHECKS:
        try:
            out.append(fn(ctx or {}))
        except Exception as e:
            out.append(_c(fn.__name__, "error", [f"Guard selbst gecrasht: {e}"]))
    return out


def build_ctx_from_disk() -> dict:
    return {
        "betfair": _lade("betfair_prices.json", {}),
        "bfTrack": _lade("betfair_track_record.json", {}),
        "bfOverview": _lade("betfair_overview.json", {}),
        "freigabe": _lade("freigabe.json", {}),
        "pulse": _lade("dashboard_pulse.json", {}),
        "moneyMap": _lade("money_map.json", {}),
        "bfAnker": _lade("betfair_anker.json", {}),
        "killer": _lade("killer.json", {}),
        "ligaStreaks": _lade("liga_streaks.json", {}),
        "mlsStreaks": _lade("mls_streaks.json", {}),
        "stake": _lade("stake_highroller.json", {}),
        "stakeAus": _lade("stake_auswertung.json", {}),
        "polyClose": _lade("poly_money_broad_close.json", {}),
        "polyUpcoming": _lade("poly_money_upcoming.json", {}),
        "polyHistory": _lade("poly_money_broad_history.json", {}),
        "ligaPoly": _lade("liga_poly_prices.json", {}),
        "polyDeckungBuch": _lade("poly_deckung_buch.json", {}),
        "ligaLedger": _lade("liga_signal_ledger.json", {}),
        "mlsLedger": _lade("mls_signal_ledger.json", {}),
        "signalBilanz": _lade("liga_signal_bilanz.json", {}),
        "fadeUnter": _lade("fade_unter.json", {}),
        "signalBilanzMls": _lade("mls_signal_bilanz.json", {}),
        "autoBetsLiga": _lade("liga_auto_bets_placed.json", {}),
        "autoBetsMls": _lade("mls_auto_bets_placed.json", {}),
        "balanceLiga": _lade("liga_poly_balance.json", {}),
        "balanceMls": _lade("mls_poly_balance.json", {}),
        "bfTrichter": _lade("betfair_public_trichter.json", {}),
        "bfSchatten": _lade("betfair_public_schatten.json", []),
        "bfPublicRecord": _lade("betfair_public_record.json", {}),
        "ergebnisNachlaufLiga": _lade("liga_ergebnis_nachlauf.json", {}),
        "ergebnisNachlaufMls": _lade("mls_ergebnis_nachlauf.json", {}),
        "ligaStreakRec": _lade("liga_streak_record.json", {}),
        "mlsStreakRec": _lade("mls_streak_record.json", {}),
    }


def main() -> int:
    res = run_checks(build_ctx_from_disk())
    nfail = sum(1 for c in res if not c["ok"])
    print(f"=== Uebersicht-Integritaet: {len(res) - nfail}/{len(res)} Checks ok "
          f"({len(UEBERSICHT_CHECKS)} Guards registriert) ===\n")
    for c in res:
        icon = "OK " if c["ok"] else ("ERR" if c["severity"] == "error" else "warn")
        print(f"[{icon}] {c['label']}: {c['nFail']} Fehler ({c['severity']})")
        for f in c["failures"][:6]:
            print(f"     - {f}")
        if c.get("hinweis"):
            print(f"     ℹ️  {c['hinweis']}")
    (BASE / STATUS_FILE).write_text(json.dumps(
        {"checks": res, "nFail": nfail,
         "generatedAt": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{STATUS_FILE} geschrieben ({nfail} Warnungen/Fehler).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
