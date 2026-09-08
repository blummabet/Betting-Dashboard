#!/usr/bin/env python3
"""
spielzentrale.py — der Stake-Join fuer den Buecher-Punktestand (Ebene 2).

⚠️ 08.09.2026, am selben Tag zurueckgebaut. Diese Datei war eine eigene Uebersichts-Ebene
(„Spielzentrale", Ebene 0). Lucas nach einem Tag damit: *„da seh ich aber eben nicht den
Mehrwert zu Ebene 2."* Nachgemessen hatte er recht — **24 von 25** Zeilen der Zentrale standen
ohnehin in `killer.alleBewertet`. Es war dieselbe Frage, zweimal gestellt, mit zwei verschiedenen
Massstaeben. Was die Zentrale wirklich konnte, waren zwei Dinge, und beide sind jetzt in Ebene 2:
der Stake-Highroller als viertes Buch, und die Spalten mit den Betraegen.

Geblieben ist der Teil, der Arbeit war und stimmt: der **Namens-Join** zwischen Stake-Events und
Betfair-Paarungen, inklusive `gleiche_elf` (Nachwuchs ist nicht die erste Mannschaft). `killer.py`
benutzt ihn; `baue()` und das Artefakt gibt es nicht mehr.

Vorgeschichte (08.09.2026, Lucas): *„Mir ist wichtig einerseits alle sources zu sehen aber auch
Empfehlungen was deckt sich, was sinnvoll zu wetten ohne da jede source extra zu checken."*

Die Uebersicht zeigte an diesem Tag 19 Spiele auf 16 Kacheln — Real Madrid v Inter stand in vier
davon, und `money_map.json` schrieb fuer dieses Spiel selbst `verdict: konsens, nSources: 3`.
Gesagt hat es keine Flaeche. Die beiden Elemente, die dafuer gebaut sind, konnten es auch nicht:

  · Ebene 2 („Wie viele Buecher sind sich einig?") haengt am Tor
    `Konzentration UND frischer Zufluss UND Quote zieht rein`. „Frischer Zufluss" heisst
    >= 2.000 EUR zwischen zwei Snapshots im Abstand von ~15 Minuten. Gemessen ueber die 192
    Spiele im Bestand: conc 114, dir=in 10, **inflow 0** — groesster 15-Minuten-Zufluss im
    ganzen Feld 1.178 EUR. Im Ledger tauchten **76 % aller Zeilen erst < 3 h vor Anpfiff** auf
    (Median 0,7 h). Die Ebene misst BEWEGUNG, nicht Uebereinstimmung, und ist morgens leer.
  · Ebene 3 nahm die Money Map ausdruecklich nur bei `verdict == "uneinig"`. Die eine Zeile, die
    „einig" sagte, fiel genau deshalb raus.

Diese Ebene beantwortet die dritte Frage: **auf welche Spiele schauen heute ueberhaupt mehrere
Quellen — und liegen sie auf derselben Seite?** Sie braucht keine Bewegung und funktioniert
deshalb acht Stunden vor Anpfiff.

Doktrin, die hier gilt:

  ⭐ Das Urteil entsteht, wo die Zahlen entstehen. Das Frontend liest `urteil` und rechnet nichts
    nach — sonst driften zwei Flaechen auseinander, sobald eine angefasst wird.

  ⭐ Pinnacle stiftet keine Einigkeit. Das Geld liegt fast immer auf dem Favoriten; „Geld-Seite ==
    Favorit" ist der Normalfall und kein Befund. Der Anker kann deshalb nur BESTAETIGEN oder
    WIDERSPRECHEN, nie zaehlen. Einig sind sich ausschliesslich **unabhaengige Geldquellen**
    (Betfair, Polymarket, Stake-Highroller).

  ⭐ Eine fehlende Quelle ist kein Widerspruch. Wer schweigt, stimmt nicht dagegen — er kommt in
    keiner der beiden Listen vor, und die Zeile sagt, wie viele ueberhaupt gesprochen haben.

  ⭐ Ein reiner Poly-PREIS ist keine Geldquelle (dieselbe Regel wie in der Money Map: `polyGeld`).
    Er bleibt sichtbar, stimmt aber nicht mit ab.

  ⭐ Die kurze Liste traegt ihre Restmenge. Von 119 Spielen vor Anpfiff haben am 08.09. genau 15
    ueberhaupt >= 1.000 EUR 1X2-Geld. Eine Liste mit acht Zeilen ohne die Zahl daneben liest sich
    wie ein Ausfall — und ist eine Messung.

REIN/testbar: `baue(...)` bekommt alle Artefakte als Argumente und fasst keine Datei an.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from betfair_consensus import _name_score, gleiche_elf

BASE = Path(__file__).resolve().parent

FENSTER_H = 24.0          # so weit nach vorn schaut die Ebene
GELDQUELLEN = ("betfair", "poly", "stake")   # unabhaengige Geldstroeme — nur die stimmen ab
STAKE_MIN_USD = 500.0     # darunter ist eine Einzelwette kein Geldstrom, sondern Rauschen
NAME_MIN = 0.55           # Summe beider Namens-Scores fuer einen Stake/Card-Join


def _ts(x):
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None


def _now():
    return datetime.now(timezone.utc)


# ── Namens-Join fuer die Quellen ohne matchId ────────────────────────────────
# Stake und die eigenen Cards fuehren keine Betfair-matchId. Gejoint wird deshalb ueber die
# Namen — mit derselben Mechanik wie der Poly-Join, inklusive `gleiche_elf`: seit dem 08.09.
# steht fest, dass ein Altersmarker die Identitaet traegt und nicht der Score.
def paart(home_a, away_a, home_b, away_b, min_summe: float = NAME_MIN) -> bool:
    """Beschreiben zwei Paarungen dasselbe Spiel? REIN. Ohne beide Namen: nein (kein Raten)."""
    if not (home_a and away_a and home_b and away_b):
        return False
    if not (gleiche_elf(home_a, home_b) and gleiche_elf(away_a, away_b)):
        return False
    return (_name_score(home_a, home_b) + _name_score(away_a, away_b)) > min_summe


_REMIS = ("draw", "the draw", "tie", "remis", "unentschieden", "x")


def _seite_aus_name(name, home, away):
    """Team-Name -> home/draw/away. None, wenn er zu keiner Seite gehoert (nicht geraten)."""
    n = str(name or "").strip().lower()
    if not n:
        return None
    if n in _REMIS:
        return "draw"
    sh, sa = _name_score(name, home or ""), _name_score(name, away or "")
    if sh == sa:
        return None
    return "home" if sh > sa else "away"


# ── Stake-Geld je Spiel ──────────────────────────────────────────────────────
_STAKE_1X2 = ("1x2", "match odds", "full time result", "1 x 2")


def stake_je_spiel(wetten, now=None, fenster_h: float = FENSTER_H):
    """Stake-Einzelwetten -> je Spiel {event, liga, anpfiff, usd, n, seiten}. REIN.

    Kombis zaehlen nicht: ihr Einsatz haengt an mehreren Spielen und gehoert keinem davon
    (dieselbe Regel wie auf der Stake-Kachel). Eine SEITE entsteht nur aus dem 1X2-Markt —
    „Over 1.5" traegt Geld, aber keine vergleichbare Seite, und darf deshalb nicht mitstimmen.

    Die angezeigte Summe hat KEINEN Boden: sie ist das Geld, das auf diesem Spiel liegt, und
    es gibt sie nur einmal. `STAKE_MIN_USD` entscheidet ausschliesslich, ob Stake mitSTIMMT —
    sonst stuenden zwei verschiedene Stake-Zahlen fuer dasselbe Spiel auf einem Bildschirm,
    und niemand koennte sagen, welche gilt.
    """
    now = now or _now()
    aus = {}
    for w in (wetten or []):
        if not isinstance(w, dict) or w.get("kombi"):
            continue
        usd = w.get("einsatzUsd")
        if not isinstance(usd, (int, float)) or usd <= 0:
            continue
        ko = _ts(w.get("anpfiff"))
        if ko is None or ko <= now or ko > now + timedelta(hours=fenster_h):
            continue
        ev = str(w.get("event") or "")
        if " - " not in ev:
            continue
        key = w.get("eventId") or ev
        e = aus.setdefault(key, {"event": ev, "liga": w.get("liga"), "anpfiff": w.get("anpfiff"),
                                 "usd": 0.0, "n": 0, "seiten": {}, "ohneSeite": 0.0})
        e["usd"] += float(usd)
        e["n"] += 1
        if str(w.get("markt") or "").strip().lower() in _STAKE_1X2:
            nm = str(w.get("auswahl") or "")
            e["seiten"][nm] = e["seiten"].get(nm, 0.0) + float(usd)
        else:
            e["ohneSeite"] += float(usd)
    return aus


def stake_fuer(home, away, index):
    """Stake-Eintrag zu einer Betfair-Paarung -> {usd, n, seite, seiteUsd, event} oder None. REIN."""
    for e in index.values():
        h, a = [t.strip() for t in e["event"].split(" - ", 1)]
        if not paart(home, away, h, a):
            continue
        seite, seite_usd = None, 0.0
        for nm, usd in sorted(e["seiten"].items(), key=lambda kv: -kv[1]):
            s = _seite_aus_name(nm, h, a)
            if s:
                seite, seite_usd = s, usd
                break
        # Unter dem Boden bleibt das Geld SICHTBAR, aber Stake stimmt nicht mit ab: eine
        # 80-Dollar-Wette ist kein Geldstrom neben 100.000 EUR auf Betfair.
        if seite_usd < STAKE_MIN_USD:
            seite = None
        return {"usd": round(e["usd"]), "n": e["n"], "seite": seite,
                "seiteUsd": round(seite_usd), "event": e["event"],
                "ohneSeiteUsd": round(e["ohneSeite"])}
    return None


# ── Eigene Cards ─────────────────────────────────────────────────────────────
# Die Engine schreibt den Markt als Text („Heimsieg", „Doppelte Chance — X2"). Nur die drei
# reinen 1X2-Ausgaenge sind mit den Geldquellen vergleichbar; alles andere (Ueber/Unter,
# Handicap, Doppelte Chance) beantwortet eine ANDERE Frage und bekommt keine Seite. Die Card
# stimmt ohnehin nicht mit ab — sie ist unsere eigene Meinung, kein Marktgeld —, aber eine
# Seite anzuzeigen, die es nicht gibt, waere schlimmer als keine.
_MARKT_SEITE = {"heimsieg": "home", "auswärtssieg": "away", "unentschieden": "draw"}


def card_fuer(home, away, fixtures):
    """Bester eigener BET-Pick zu dieser Paarung -> {markt, seite, conv, odd} oder None. REIN."""
    for f in (fixtures or []):
        if not paart(home, away, f.get("home"), f.get("away")):
            continue
        best = None
        for p in (f.get("picks") or []):
            if not isinstance(p, dict) or p.get("verdict") != "BET":
                continue
            conv = float(p.get("convictionScore") or 0)
            if best is None or conv > best["conv"]:
                best = {"markt": p.get("market"),
                        "seite": _MARKT_SEITE.get(str(p.get("market") or "").strip().lower()),
                        "conv": conv, "odd": p.get("odds")}
        return best
    return None


# ── Das Urteil ───────────────────────────────────────────────────────────────
_LABEL = {"betfair": "Betfair", "poly": "Polymarket", "stake": "Stake-Highroller",
          "pinn": "Pinnacle", "card": "eigene Card"}
_SEITE = {"home": "Heim", "draw": "Remis", "away": "Auswärts"}


def urteil(zeile) -> dict:
    """Wer sagt was — und deckt es sich? REIN.

    Rueckgabe: {urteil, seite, dafuer[], gegen[], nGeld, anker, text}
      · „einig"           — >= 2 unabhaengige Geldquellen auf derselben Seite
      · „uneinig"         — >= 2 Geldquellen, aber nicht auf derselben Seite
      · „eine Geldquelle" — genau eine spricht; ein Hinweis, keine Deckung
      · „keine Seite"     — Geld da, aber keine vergleichbare Seite (nur Ueber/Unter o. ae.)
      · „keine Quelle"    — niemand hat zu diesem Spiel etwas
    """
    stimmen = {}
    bf = zeile.get("betfair") or {}
    if bf.get("seite"):
        stimmen["betfair"] = bf["seite"]
    pl = zeile.get("poly") or {}
    # Ein reiner Preis fuellt die Spalte, stimmt aber nicht ab (Money-Map-Regel `polyGeld`).
    if pl.get("seite") and pl.get("art") == "geld":
        stimmen["poly"] = pl["seite"]
    stk = zeile.get("stake") or {}
    if stk.get("seite"):
        stimmen["stake"] = stk["seite"]

    pinn = zeile.get("pinn") or {}
    fav = pinn.get("fav")

    if not stimmen:
        art = "keine Seite" if (bf or pl or stk) else "keine Quelle"
        txt = ("Geld ist da, aber keine Quelle nennt eine vergleichbare Seite."
               if art == "keine Seite" else "Keine Quelle hat zu diesem Spiel etwas.")
        return {"urteil": art, "seite": None, "dafuer": [], "gegen": [], "nGeld": 0,
                "anker": None, "text": txt}

    gruppen = {}
    for q, s in stimmen.items():
        gruppen.setdefault(s, []).append(q)
    seite, dafuer = max(gruppen.items(), key=lambda kv: len(kv[1]))
    gegen = [q for q, s in stimmen.items() if s != seite]
    anker = ("passt" if fav == seite else "dagegen") if fav else None

    if len(stimmen) == 1:
        art = "eine Geldquelle"
        text = ("Nur %s nennt eine Seite (%s) — das ist ein Hinweis, keine Deckung."
                % (_LABEL[dafuer[0]], _SEITE.get(seite, seite)))
    elif not gegen:
        art = "einig"
        text = ("%s liegen auf derselben Seite (%s)."
                % (" und ".join(_LABEL[q] for q in sorted(dafuer)), _SEITE.get(seite, seite)))
        if anker == "dagegen":
            text += " Pinnacle sieht einen anderen Favoriten — das Geld steht gegen den Anker."
    else:
        art = "uneinig"
        text = ("%s auf %s, %s dagegen — kein Konsens, sondern eine Divergenz."
                % (" und ".join(_LABEL[q] for q in sorted(dafuer)), _SEITE.get(seite, seite),
                   " und ".join(_LABEL[q] for q in sorted(gegen))))
    return {"urteil": art, "seite": seite, "dafuer": sorted(dafuer), "gegen": sorted(gegen),
            "nGeld": len(stimmen), "anker": anker, "text": text}


def _zeile(mm, stake_idx, fixtures):
    """money_map_row-Zeile + Stake + Card -> Zentrale-Zeile MIT Urteil. REIN."""
    bf, pl, pn = mm.get("betfair"), mm.get("poly"), mm.get("pinn")
    home, away = mm.get("home"), mm.get("away")
    z = {
        "matchId": mm.get("matchId"), "home": home, "away": away,
        "league": mm.get("league"), "kickoff": mm.get("kickoff"), "live": bool(mm.get("live")),
        "betfair": ({"seite": bf.get("side"), "name": bf.get("name"),
                     "anteilPct": bf.get("sharePct"), "eur": round(bf.get("eur") or 0),
                     "odd": bf.get("odd")} if bf else None),
        "poly": ({"seite": pl.get("side"), "name": pl.get("name"),
                  "anteilPct": pl.get("sharePct"), "usd": round(pl.get("usd") or 0),
                  "art": "geld" if mm.get("polyGeld") else "preis"} if pl else None),
        "pinn": ({"fav": pn.get("fav"), "home": pn.get("home"), "draw": pn.get("draw"),
                  "away": pn.get("away")} if pn else None),
        "stake": stake_fuer(home, away, stake_idx),
        "card": card_fuer(home, away, fixtures),
    }
    z.update(urteil(z))
    z["nQuellen"] = sum(1 for k in ("betfair", "poly", "pinn", "stake", "card") if z.get(k))
    return z


_RANG = {"einig": 0, "uneinig": 1, "eine Geldquelle": 2, "keine Seite": 3, "keine Quelle": 4}

# Ab wie viel Geld eine Quelle ueberhaupt etwas AUSSAGT. 95 % von 627 EUR ist keine Mehrheit,
# sondern ein leerer Markt — und eine Zeile „Betfair und Poly sind sich einig" darueber sieht
# genauso aus wie eine ueber 102.861 EUR. Die Zeile faellt deshalb nicht raus (sie ist ja
# richtig), sie wird als `duenn` markiert und sortiert unten.
DUENN_EUR = 2000.0
DUENN_USD = 2000.0


def _duenn(z) -> bool:
    """Traegt mindestens eine der abstimmenden Geldquellen zu wenig Geld? REIN."""
    for q in (z.get("dafuer") or []) + (z.get("gegen") or []):
        if q == "betfair" and ((z.get("betfair") or {}).get("eur") or 0) < DUENN_EUR:
            return True
        if q == "poly" and ((z.get("poly") or {}).get("usd") or 0) < DUENN_USD:
            return True
        if q == "stake" and ((z.get("stake") or {}).get("seiteUsd") or 0) < DUENN_USD:
            return True
    return False


def baue(mm_rows, stake_wetten=None, fixtures=None, now=None, fenster_h: float = FENSTER_H) -> dict:
    """Die Zeilen, die etwas sagen — plus die gezaehlte Restmenge. REIN.

    `mm_rows` sind money_map_row-Zeilen fuer JEDES Spiel im Feed, nicht die gefilterte Money Map.

    In die Liste kommt nur, wo sich mindestens zwei Geldquellen VERGLEICHEN lassen (einig oder
    uneinig) — oder wo eine eigene Card liegt. Alles andere ist keine Aussage, sondern eine
    einzelne Beobachtung, und wandert gezaehlt in `rest`. Gemessen am 08.09.: von 123 Spielen im
    Feed haben 77 genau eine Geldquelle. Eine Liste mit 100 Zeilen, von denen 77 nichts
    vergleichen, ist genau die Flaeche, die Lucas heute jede Quelle einzeln nachschauen laesst.
    """
    now = now or _now()
    grenze = now + timedelta(hours=fenster_h)
    stake_idx = stake_je_spiel(stake_wetten, now=now, fenster_h=fenster_h)

    zeilen, einzeln, rest_spaet, rest_gelaufen, rest_stumm = [], [], 0, 0, 0
    for mm in (mm_rows or []):
        if not isinstance(mm, dict):
            continue
        ko = _ts(mm.get("kickoff"))
        if ko is None or ko <= now:
            rest_gelaufen += 1
            continue
        if ko > grenze:
            rest_spaet += 1
            continue
        z = _zeile(mm, stake_idx, fixtures)
        z["duenn"] = _duenn(z)
        if z["urteil"] in ("einig", "uneinig") or z.get("card"):
            zeilen.append(z)
        elif z["urteil"] == "eine Geldquelle":
            einzeln.append(z)
        else:
            rest_stumm += 1

    # Duenne Zeilen nach unten, sonst steht ein 627-EUR-Markt ueber Real Madrid v Inter.
    zeilen.sort(key=lambda z: (bool(z.get("duenn")), _RANG.get(z["urteil"], 9),
                               -(z.get("nGeld") or 0),
                               -((z.get("betfair") or {}).get("eur") or 0)))
    einzeln.sort(key=lambda z: -((z.get("betfair") or {}).get("eur") or 0))
    return {
        "generatedAt": now.isoformat(),
        "fensterH": fenster_h,
        "n": len(zeilen),
        "rest": {"einzeln": len(einzeln), "stumm": rest_stumm,
                 "spaeter": rest_spaet, "gelaufen": rest_gelaufen},
        # Die groessten Einzelquellen-Spiele bleiben abrufbar — sie sind kein Vergleich, aber
        # sie sind auch nicht nichts. Nur eben nicht in der Hauptliste.
        "einzeln": einzeln[:8],
        "regeln": {
            "geldquellen": list(GELDQUELLEN),
            "text": "Einig heisst: mindestens zwei unabhaengige Geldquellen auf derselben Seite. "
                    "Pinnacle zaehlt nicht mit — das Geld liegt fast immer auf dem Favoriten, "
                    "diese Uebereinstimmung waere der Normalfall. Der Anker kann nur bestaetigen "
                    "oder widersprechen. Eine fehlende Quelle ist kein Widerspruch.",
            "stakeMinUsd": STAKE_MIN_USD,
            "duennEur": DUENN_EUR, "duennUsd": DUENN_USD,
        },
        "zeilen": zeilen,
    }


def _lade(name, default=None):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return default


def fixtures_aus(liga, mls):
    """Fixtures MIT ihren Picks aus liga-data/mls-data. REIN.

    Die Picks haengen nicht am Fixture, sondern in einer eigenen Map unter `picks`, verschluesselt
    als `<GRUPPE>-<Spieltag>-<homeId>-<awayId>` — genau der Join, der am 28.08. im Frontend fehlte
    und dort alles lahmlegte, was auf Fixtures steht. Hier wird er einmal gemacht, damit die
    Zentrale dieselbe Falle nicht noch einmal aufstellt.
    """
    out = []
    for d in (liga, mls):
        if not isinstance(d, dict):
            continue
        picks = d.get("picks") or {}

        def _add(code, f, _picks=picks):
            if not isinstance(f, dict):
                return
            ps = _picks.get("%s-%s-%s-%s" % (code, f.get("matchday"), f.get("home"), f.get("away")))
            if not ps:
                return
            out.append({"home": f.get("homeName") or f.get("home"),
                        "away": f.get("awayName") or f.get("away"),
                        "kickoff": f.get("kickoff"), "picks": ps})

        for code, g in (d.get("groups") or {}).items():
            for f in ((g or {}).get("fixtures") or []):
                _add(code, f)
        for f in (d.get("koFixtures") or []):
            _add(str((f or {}).get("round") or "KO"), f)
    return out


# Kein `main()` mehr: diese Datei erzeugt kein Artefakt. Wer sie ausfuehrt, soll das merken,
# statt eine leere Datei zu schreiben.
def main() -> int:
    print("spielzentrale.py erzeugt seit dem 08.09.2026 kein Artefakt mehr — der Stake-Join "
          "wohnt hier, gerechnet wird er in killer.py (Buecher-Punktestand, Ebene 2).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
