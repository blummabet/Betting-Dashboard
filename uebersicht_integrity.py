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
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATUS_FILE = "uebersicht_integrity.json"


def _lade(name: str, default=None):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
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
        if _tok(nm) & (_tok(r.get("home")) | _tok(r.get("away"))):
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
    fails = []
    for k in (d.get("kontrolle") or []):
        if isinstance(k.get("roi"), (int, float)) and k["roi"] > 0:
            fails.append("%s %s: der Fade GEWINNT hier (%+.1f %%, Geldseite %+.1f pp) — die "
                         "Rechnung misst sich selbst, der Befund traegt nicht"
                         % (k.get("markt"), k.get("seite"), 100 * k["roi"], k.get("vorsprungPP") or 0))
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
        "ligaLedger": _lade("liga_signal_ledger.json", {}),
        "mlsLedger": _lade("mls_signal_ledger.json", {}),
        "signalBilanz": _lade("liga_signal_bilanz.json", {}),
        "fadeUnter": _lade("fade_unter.json", {}),
        "signalBilanzMls": _lade("mls_signal_bilanz.json", {}),
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
